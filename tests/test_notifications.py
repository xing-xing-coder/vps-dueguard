from datetime import date

import httpx
import pytest

from vps_dueguard.models import AppConfig, ServiceInfo
from vps_dueguard.notifications import (
    CallbackDeduper,
    ServiceCache,
    TelegramBot,
    TelegramError,
    _split_message,
    build_renewal_alerts,
    build_traffic_alerts,
    calculate_traffic_percentage,
    format_cost_summary,
    format_service_date,
    format_renewals_report,
    format_summary,
    format_traffic_report,
    handle_bot_callback,
    handle_bot_command,
    parse_price_amount,
    parse_service_date,
    require_telegram,
    run_bot,
)


def service(expires_at: str = "2026-06-16", price: str = "unknown") -> ServiceInfo:
    return ServiceInfo(
        provider="provider-a",
        service_name="Tokyo VPS",
        status="Active",
        expires_at=expires_at,
        traffic_usage="20 GB / 1 TB",
        traffic_remaining="1004.00 GB",
        price=price,
        detail_url="https://example.com/service",
    )


def test_require_telegram_missing() -> None:
    config = AppConfig.model_validate(
        {
            "providers": [
                {
                    "name": "provider-a",
                    "base_url": "https://provider-a.example",
                    "username": "user@example.com",
                    "password": "secret",
                }
            ]
        }
    )

    with pytest.raises(TelegramError):
        require_telegram(config)


def test_parse_service_date() -> None:
    assert parse_service_date("2026-06-16") == date(2026, 6, 16)
    assert parse_service_date("2026/06/16") == date(2026, 6, 16)
    assert parse_service_date("Thursday, July 23rd, 2026") == date(2026, 7, 23)
    assert parse_service_date("unknown") is None
    assert format_service_date("2026/06/16") == "2026-06-16"
    assert format_service_date("unknown") == "unknown"


def test_renewal_alerts_deduplicate(tmp_path) -> None:
    state_file = tmp_path / "state.json"
    services = [service("2026-06-16")]

    first = build_renewal_alerts(services, [14, 7], state_file, today=date(2026, 6, 2))
    second = build_renewal_alerts(services, [14, 7], state_file, today=date(2026, 6, 2))

    assert len(first) == 1
    assert "14 days left" in first[0]
    assert second == []


def test_renewal_alerts_escape_dynamic_html(tmp_path) -> None:
    state_file = tmp_path / "state.json"
    services = [
        ServiceInfo(
            provider="provider-<a>",
            service_name="Tokyo & Osaka VPS",
            status="Active",
            expires_at="2026-06-16",
            traffic_usage="20 GB < 1 TB",
            traffic_remaining="1004 GB & counting",
            detail_url="https://example.com/service",
        )
    ]

    alerts = build_renewal_alerts(services, [14], state_file, today=date(2026, 6, 2))

    assert "provider-&lt;a&gt;" in alerts[0]
    assert "Tokyo &amp; Osaka VPS" in alerts[0]
    assert "20 GB &lt; 1 TB" in alerts[0]
    assert "1004 GB &amp; counting" in alerts[0]


def test_renewal_alerts_trigger_inside_threshold_window(tmp_path) -> None:
    state_file = tmp_path / "state.json"
    services = [service("2026-06-23")]

    alerts = build_renewal_alerts(services, [30], state_file, today=date(2026, 6, 2))

    assert len(alerts) == 1
    assert "21 days left" in alerts[0]


def test_renewal_alerts_use_smallest_matching_threshold_for_state(tmp_path) -> None:
    state_file = tmp_path / "state.json"
    services = [service("2026-06-23")]

    first = build_renewal_alerts(services, [30, 14], state_file, today=date(2026, 6, 2))
    second = build_renewal_alerts(services, [30, 14], state_file, today=date(2026, 6, 2))

    assert len(first) == 1
    assert second == []
    assert "30" in state_file.read_text(encoding="utf-8")


def test_expired_service_skips_renewal_alert(tmp_path) -> None:
    alerts = build_renewal_alerts([service("2026-06-01")], [30], tmp_path / "state.json", today=date(2026, 6, 2))

    assert alerts == []


def test_unknown_expiry_skips_renewal_alert(tmp_path) -> None:
    alerts = build_renewal_alerts([service("unknown")], [14, 7], tmp_path / "state.json", today=date(2026, 6, 2))

    assert alerts == []


def test_format_reports() -> None:
    services = [service()]

    assert "<b>VPS Summary</b>" in format_summary(services)
    assert "Expires: 2026-06-16" in format_summary(services)
    assert "<b>VPS Traffic</b>" in format_traffic_report(services)
    assert "1004.00 GB" in format_traffic_report(services)
    assert "<b>VPS Renewals</b>" in format_renewals_report(services, today=date(2026, 6, 2))
    assert "Days left: <b>14</b>" in format_renewals_report(services, today=date(2026, 6, 2))


def test_format_summary_includes_price() -> None:
    services = [service(price="$3.50 USD")]

    summary = format_summary(services)

    assert "Price: $3.50 USD" in summary


def test_format_traffic_report_includes_price() -> None:
    services = [service(price="$5.00 USD")]

    report = format_traffic_report(services)

    assert "Price: $5.00 USD" in report


def test_format_renewals_report_includes_price() -> None:
    services = [service(price="$10.00 USD")]

    report = format_renewals_report(services, today=date(2026, 6, 2))

    assert "Price: $10.00 USD" in report


def test_format_reports_hide_unknown_price() -> None:
    services = [service(price="unknown")]

    summary = format_summary(services)
    traffic = format_traffic_report(services)
    renewals = format_renewals_report(services, today=date(2026, 6, 2))

    assert "Price:" not in summary
    assert "Price:" not in traffic
    assert "Price:" not in renewals


def test_renewals_report_skips_unknown_dates() -> None:
    services = [service("unknown"), service("2026-06-16")]
    report = format_renewals_report(services, today=date(2026, 6, 2))

    assert "Days left: <b>14</b>" in report
    assert "unknown" not in report


def test_format_reports_escape_dynamic_html() -> None:
    services = [
        ServiceInfo(
            provider="provider-<a>",
            service_name="Tokyo & Osaka VPS",
            status="Active",
            expires_at="2026-06-16",
            traffic_usage="20 GB < 1 TB",
            traffic_remaining="1004 GB & counting",
            detail_url="https://example.com/service",
        )
    ]
    summary = format_summary(services, ["provider-a: bad <token> & retry"])

    assert "provider-&lt;a&gt;" in summary
    assert "Tokyo &amp; Osaka VPS" in summary
    assert "20 GB &lt; 1 TB" in summary
    assert "bad &lt;token&gt; &amp; retry" in summary


def test_format_reports_show_provider_errors_prominently() -> None:
    summary = format_summary([], ["provider-a: login failed"])
    traffic = format_traffic_report([], ["provider-a: login failed"])
    renewals = format_renewals_report([], ["provider-a: login failed"], today=date(2026, 6, 2))

    assert "No active services were loaded." in summary
    assert "<b>Provider errors</b>" in summary
    assert "- provider-a: login failed" in summary
    assert "No traffic data was loaded." in traffic
    assert "<b>Provider errors</b>" in traffic
    assert "No renewal dates were loaded." in renewals
    assert "<b>Provider errors</b>" in renewals


def test_telegram_send_message_payload(monkeypatch) -> None:
    requests = []

    class FakeResponse:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict[str, object]:
            return {"ok": True}

    class FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def post(self, url, json):
            requests.append((url, json))
            return FakeResponse()

    monkeypatch.setattr("vps_dueguard.notifications.httpx.Client", FakeClient)
    config = AppConfig.model_validate(
        {
            "providers": [
                {
                    "name": "provider-a",
                    "base_url": "https://provider-a.example",
                    "username": "user@example.com",
                    "password": "secret",
                }
            ],
            "telegram": {"bot_token": "token", "chat_id": "123"},
        }
    )

    bot = TelegramBot(require_telegram(config))
    bot.send_message("hello")

    assert requests[0][0] == "https://api.telegram.org/bottoken/sendMessage"
    assert requests[0][1]["chat_id"] == "123"
    assert requests[0][1]["text"] == "hello"
    assert requests[0][1]["parse_mode"] == "HTML"


def test_telegram_send_message_accepts_reply_markup(monkeypatch) -> None:
    requests = []

    class FakeResponse:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict[str, object]:
            return {"ok": True}

    class FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def post(self, url, json):
            requests.append((url, json))
            return FakeResponse()

    monkeypatch.setattr("vps_dueguard.notifications.httpx.Client", FakeClient)
    config = AppConfig.model_validate(
        {
            "providers": [],
            "telegram": {"bot_token": "token", "chat_id": "123"},
        }
    )
    markup = {"inline_keyboard": [[{"text": "Summary", "callback_data": "cmd:summary"}]]}

    bot = TelegramBot(require_telegram(config))
    bot.send_message("hello", reply_markup=markup)

    assert requests[0][1]["reply_markup"] == markup


def test_telegram_answer_callback_query_payload(monkeypatch) -> None:
    requests = []

    class FakeResponse:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict[str, object]:
            return {"ok": True}

    class FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def post(self, url, json):
            requests.append((url, json))
            return FakeResponse()

    monkeypatch.setattr("vps_dueguard.notifications.httpx.Client", FakeClient)
    config = AppConfig.model_validate(
        {
            "providers": [],
            "telegram": {"bot_token": "token", "chat_id": "123"},
        }
    )

    bot = TelegramBot(require_telegram(config))
    bot.answer_callback_query("callback-1")
    bot.answer_callback_query("callback-2", "Querying, please wait...")

    assert requests[0][0] == "https://api.telegram.org/bottoken/answerCallbackQuery"
    assert requests[0][1] == {"callback_query_id": "callback-1"}
    assert requests[1][1] == {"callback_query_id": "callback-2", "text": "Querying, please wait..."}


def test_telegram_set_commands_payload(monkeypatch) -> None:
    requests = []

    class FakeResponse:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict[str, object]:
            return {"ok": True}

    class FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def post(self, url, json):
            requests.append((url, json))
            return FakeResponse()

    monkeypatch.setattr("vps_dueguard.notifications.httpx.Client", FakeClient)
    config = AppConfig.model_validate(
        {
            "providers": [
                {
                    "name": "provider-a",
                    "base_url": "https://provider-a.example",
                    "username": "user@example.com",
                    "password": "secret",
                }
            ],
            "telegram": {"bot_token": "token", "chat_id": "123"},
        }
    )

    bot = TelegramBot(require_telegram(config))
    bot.set_commands()

    assert requests[0][0] == "https://api.telegram.org/bottoken/setMyCommands"
    assert {"command": "summary", "description": "All active VPS services"} in requests[0][1]["commands"]
    assert {"command": "providers", "description": "List configured providers"} in requests[0][1]["commands"]


def test_bot_static_commands() -> None:
    config = AppConfig.model_validate(
        {
            "providers": [
                {
                    "name": "provider-a",
                    "base_url": "https://provider-a.example",
                    "username": "user@example.com",
                    "password": "secret",
                }
            ],
            "telegram": {"bot_token": "token", "chat_id": "123"},
        }
    )

    assert "/summary" in handle_bot_command("/help", config)
    assert "/summary" in handle_bot_command("/start", config)
    assert "/providers" in handle_bot_command("/help", config)
    assert "/provider &lt;name&gt;" in handle_bot_command("/start", config)
    assert "/provider <name>" not in handle_bot_command("/start", config)
    assert "Unknown command" in handle_bot_command("/wat", config)


def test_providers_command_does_not_query_services(monkeypatch) -> None:
    config = AppConfig.model_validate(
        {
            "providers": [
                {
                    "name": "provider-a",
                    "base_url": "https://provider-a.example",
                    "username": "user@example.com",
                    "password": "secret",
                },
                {
                    "name": "provider-b",
                    "base_url": "https://provider-b.example",
                    "username": "user@example.com",
                    "password": "secret",
                },
            ],
            "telegram": {"bot_token": "token", "chat_id": "123"},
        }
    )

    def fail_collect_services(*_args, **_kwargs):
        raise AssertionError("/providers should not query providers")

    monkeypatch.setattr("vps_dueguard.notifications.collect_services", fail_collect_services)

    reply = handle_bot_command("/providers", config, ServiceCache())

    assert "<b>Providers</b>" in reply
    assert "- provider-a" in reply
    assert "- provider-b" in reply


def test_unknown_bot_command_does_not_query_services(monkeypatch) -> None:
    config = AppConfig.model_validate(
        {
            "providers": [
                {
                    "name": "provider-a",
                    "base_url": "https://provider-a.example",
                    "username": "user@example.com",
                    "password": "secret",
                }
            ],
            "telegram": {"bot_token": "token", "chat_id": "123"},
        }
    )

    def fail_collect_services(*_args, **_kwargs):
        raise AssertionError("unknown commands should not query providers")

    monkeypatch.setattr("vps_dueguard.notifications.collect_services", fail_collect_services)

    assert "Unknown command" in handle_bot_command("/wat", config, ServiceCache())


def test_bot_command_with_no_providers_gives_setup_hint(monkeypatch) -> None:
    config = AppConfig.model_validate(
        {
            "providers": [],
            "telegram": {"bot_token": "token", "chat_id": "123"},
        }
    )

    def fail_collect_services(*_args, **_kwargs):
        raise AssertionError("empty provider config should not query providers")

    monkeypatch.setattr("vps_dueguard.notifications.collect_services", fail_collect_services)

    reply = handle_bot_command("/summary", config, ServiceCache())

    assert "No providers configured." in reply
    assert "vpsm" in reply


def test_provider_command_unknown_provider_reports_error() -> None:
    config = AppConfig.model_validate(
        {
            "providers": [
                {
                    "name": "provider-a",
                    "base_url": "https://provider-a.example",
                    "username": "user@example.com",
                    "password": "secret",
                }
            ],
            "telegram": {"bot_token": "token", "chat_id": "123"},
        }
    )

    reply = handle_bot_command("/provider missing", config, ServiceCache())

    assert "Unknown provider 'missing'" in reply
    assert "Known providers: provider-a" in reply
    assert "<b>Provider errors</b>" in reply


def test_bot_cache_and_refresh(monkeypatch) -> None:
    calls = []
    config = AppConfig.model_validate(
        {
            "providers": [
                {
                    "name": "provider-a",
                    "base_url": "https://provider-a.example",
                    "username": "user@example.com",
                    "password": "secret",
                }
            ],
            "telegram": {"bot_token": "token", "chat_id": "123"},
        }
    )

    def fake_collect_services(config, provider_name=None):
        calls.append(provider_name)
        return [service()], []

    monkeypatch.setattr("vps_dueguard.notifications.collect_services", fake_collect_services)
    cache = ServiceCache()

    assert "Tokyo VPS" in handle_bot_command("/summary", config, cache)
    assert "Tokyo VPS" in handle_bot_command("/summary@MyBot", config, cache)
    assert "Tokyo VPS" in handle_bot_command("/traffic", config, cache)
    assert "Tokyo VPS" in handle_bot_command("/refresh", config, cache)
    assert calls == [None, None]


def test_run_bot_reloads_config_from_disk(monkeypatch, tmp_path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
providers:
  - name: provider-a
    base_url: https://provider-a.example
    username: user@example.com
    password: secret
telegram:
  bot_token: token
  chat_id: "123"
""".strip(),
        encoding="utf-8",
    )
    initial_config = AppConfig.model_validate(
        {
            "providers": [],
            "telegram": {"bot_token": "token", "chat_id": "123"},
        }
    )
    replies = []

    class FakeBot:
        def __init__(self, telegram) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def set_commands(self) -> None:
            pass

        def get_updates(self, offset=None, timeout=30):
            return [
                {
                    "update_id": 1,
                    "message": {
                        "chat": {"id": 123},
                        "text": "/summary",
                    },
                }
            ]

        def send_message(self, text, chat_id=None, reply_markup=None):
            replies.append((text, chat_id))

    def fake_handle_bot_command(_text, config, _cache):
        return f"providers={len(config.providers)}"

    monkeypatch.setattr("vps_dueguard.notifications.TelegramBot", FakeBot)
    monkeypatch.setattr("vps_dueguard.notifications.handle_bot_command", fake_handle_bot_command)

    run_bot(initial_config, stop_after=lambda: bool(replies), config_path=config_path)

    assert replies == [("providers=1", "123")]


def test_provider_command_does_not_use_global_cache(monkeypatch) -> None:
    calls = []
    config = AppConfig.model_validate(
        {
            "providers": [
                {
                    "name": "provider-a",
                    "base_url": "https://provider-a.example",
                    "username": "user@example.com",
                    "password": "secret",
                }
            ],
            "telegram": {"bot_token": "token", "chat_id": "123"},
        }
    )

    def fake_collect_services(config, provider_name=None):
        calls.append(provider_name)
        return [service()], []

    monkeypatch.setattr("vps_dueguard.notifications.collect_services", fake_collect_services)

    assert "Tokyo VPS" in handle_bot_command("/provider provider-a", config, ServiceCache())
    assert calls == ["provider-a"]


def test_bot_callback_command_reuses_command_handler(monkeypatch) -> None:
    calls = []
    config = AppConfig.model_validate(
        {
            "providers": [
                {
                    "name": "provider-a",
                    "base_url": "https://provider-a.example",
                    "username": "user@example.com",
                    "password": "secret",
                }
            ],
            "telegram": {"bot_token": "token", "chat_id": "123"},
        }
    )

    def fake_collect_services(config, provider_name=None):
        calls.append(provider_name)
        return [service()], []

    monkeypatch.setattr("vps_dueguard.notifications.collect_services", fake_collect_services)
    cache = ServiceCache()

    reply, markup = handle_bot_callback("cmd:summary", config, cache)
    traffic_reply, _markup = handle_bot_callback("cmd:traffic", config, cache)

    assert "Tokyo VPS" in reply
    assert "1004.00 GB" in traffic_reply
    assert calls == [None]
    assert markup is not None
    assert markup["inline_keyboard"][0][0]["text"] == "Summary"


def test_bot_callback_providers_menu_and_provider_index(monkeypatch) -> None:
    calls = []
    config = AppConfig.model_validate(
        {
            "providers": [
                {
                    "name": "provider-a",
                    "base_url": "https://provider-a.example",
                    "username": "user@example.com",
                    "password": "secret",
                },
                {
                    "name": "provider-b",
                    "base_url": "https://provider-b.example",
                    "username": "user@example.com",
                    "password": "secret",
                },
            ],
            "telegram": {"bot_token": "token", "chat_id": "123"},
        }
    )

    def fake_collect_services(config, provider_name=None):
        calls.append(provider_name)
        return [service()], []

    monkeypatch.setattr("vps_dueguard.notifications.collect_services", fake_collect_services)

    list_reply, markup = handle_bot_callback("cmd:providers", config, ServiceCache())
    provider_reply, provider_markup = handle_bot_callback("provider:1", config, ServiceCache())

    assert "<b>Providers</b>" in list_reply
    assert markup is not None
    assert markup["inline_keyboard"][1][0]["callback_data"] == "provider:1"
    assert "Tokyo VPS" in provider_reply
    assert provider_markup is None
    assert calls == ["provider-b"]


def test_bot_callback_stale_provider_index_is_clear() -> None:
    config = AppConfig.model_validate(
        {
            "providers": [
                {
                    "name": "provider-a",
                    "base_url": "https://provider-a.example",
                    "username": "user@example.com",
                    "password": "secret",
                }
            ],
            "telegram": {"bot_token": "token", "chat_id": "123"},
        }
    )

    reply, markup = handle_bot_callback("provider:9", config, ServiceCache())

    assert "Provider selection is no longer valid" in reply
    assert markup is not None


def test_callback_deduper_releases_after_short_settle_window(monkeypatch) -> None:
    now = [100.0]
    monkeypatch.setattr("vps_dueguard.notifications.time.time", lambda: now[0])
    deduper = CallbackDeduper(settle_seconds=3)

    assert deduper.accept("123", "cmd:summary") is True
    assert deduper.accept("123", "cmd:summary") is False

    deduper.release("123", "cmd:summary")

    assert deduper.accept("123", "cmd:summary") is False

    now[0] += 3.1

    assert deduper.accept("123", "cmd:summary") is True


def test_run_bot_ignores_read_timeout(monkeypatch) -> None:
    config = AppConfig.model_validate(
        {
            "providers": [
                {
                    "name": "provider-a",
                    "base_url": "https://provider-a.example",
                    "username": "user@example.com",
                    "password": "secret",
                }
            ],
            "telegram": {"bot_token": "token", "chat_id": "123"},
        }
    )
    calls = {"updates": 0}

    class FakeBot:
        def __init__(self, telegram) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def set_commands(self) -> None:
            pass

        def get_updates(self, offset=None, timeout=30):
            calls["updates"] += 1
            raise httpx.ReadTimeout("timeout")

    monkeypatch.setattr("vps_dueguard.notifications.TelegramBot", FakeBot)

    run_bot(config, stop_after=lambda: calls["updates"] >= 1)

    assert calls["updates"] == 1


def test_run_bot_ignores_set_commands_failure(monkeypatch) -> None:
    config = AppConfig.model_validate(
        {
            "providers": [],
            "telegram": {"bot_token": "token", "chat_id": "123"},
        }
    )
    calls = {"updates": 0}

    class FakeBot:
        def __init__(self, telegram) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def set_commands(self) -> None:
            raise RuntimeError("cannot set commands")

        def get_updates(self, offset=None, timeout=30):
            calls["updates"] += 1
            return []

    monkeypatch.setattr("vps_dueguard.notifications.TelegramBot", FakeBot)

    run_bot(config, stop_after=lambda: calls["updates"] >= 1)

    assert calls["updates"] == 1


def test_run_bot_ignores_polling_http_errors(monkeypatch) -> None:
    config = AppConfig.model_validate(
        {
            "providers": [],
            "telegram": {"bot_token": "token", "chat_id": "123"},
        }
    )
    calls = {"updates": 0}

    class FakeBot:
        def __init__(self, telegram) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def set_commands(self) -> None:
            pass

        def get_updates(self, offset=None, timeout=30):
            calls["updates"] += 1
            raise httpx.ConnectError("network")

    monkeypatch.setattr("vps_dueguard.notifications.TelegramBot", FakeBot)

    run_bot(config, stop_after=lambda: calls["updates"] >= 1)

    assert calls["updates"] == 1


def test_run_bot_replies_to_command_errors(monkeypatch) -> None:
    config = AppConfig.model_validate(
        {
            "providers": [
                {
                    "name": "provider-a",
                    "base_url": "https://provider-a.example",
                    "username": "user@example.com",
                    "password": "secret",
                }
            ],
            "telegram": {"bot_token": "token", "chat_id": "123"},
        }
    )
    replies = []

    class FakeBot:
        def __init__(self, telegram) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def set_commands(self) -> None:
            pass

        def get_updates(self, offset=None, timeout=30):
            return [
                {
                    "update_id": 1,
                    "message": {
                        "chat": {"id": 123},
                        "text": "/summary",
                    },
                }
            ]

        def send_message(self, text, chat_id=None, reply_markup=None):
            replies.append((text, chat_id))

    def fail_handle_bot_command(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("vps_dueguard.notifications.TelegramBot", FakeBot)
    monkeypatch.setattr("vps_dueguard.notifications.handle_bot_command", fail_handle_bot_command)

    run_bot(config, stop_after=lambda: bool(replies))

    assert replies == [("<b>Error:</b> boom", "123")]


def test_run_bot_ignores_unauthorized_message_and_callback(monkeypatch) -> None:
    config = AppConfig.model_validate(
        {
            "providers": [
                {
                    "name": "provider-a",
                    "base_url": "https://provider-a.example",
                    "username": "user@example.com",
                    "password": "secret",
                }
            ],
            "telegram": {"bot_token": "token", "chat_id": "123"},
        }
    )
    sent = []
    answered = []
    calls = {"updates": 0}

    class FakeBot:
        def __init__(self, telegram) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def set_commands(self) -> None:
            pass

        def get_updates(self, offset=None, timeout=30):
            calls["updates"] += 1
            return [
                {
                    "update_id": 1,
                    "message": {
                        "chat": {"id": 999},
                        "text": "/summary",
                    },
                },
                {
                    "update_id": 2,
                    "callback_query": {
                        "id": "cb-1",
                        "message": {"chat": {"id": 999}},
                        "data": "cmd:summary",
                    },
                },
            ]

        def answer_callback_query(self, callback_query_id, text=None):
            answered.append((callback_query_id, text))

        def send_message(self, text, chat_id=None, reply_markup=None):
            sent.append((text, chat_id, reply_markup))

    def fail_handle_bot_command(*_args, **_kwargs):
        raise AssertionError("unauthorized updates should not be handled")

    monkeypatch.setattr("vps_dueguard.notifications.TelegramBot", FakeBot)
    monkeypatch.setattr("vps_dueguard.notifications.handle_bot_command", fail_handle_bot_command)

    run_bot(config, stop_after=lambda: calls["updates"] >= 1)

    assert sent == []
    assert answered == []


def test_run_bot_handles_authorized_callback(monkeypatch) -> None:
    config = AppConfig.model_validate(
        {
            "providers": [
                {
                    "name": "provider-a",
                    "base_url": "https://provider-a.example",
                    "username": "user@example.com",
                    "password": "secret",
                }
            ],
            "telegram": {"bot_token": "token", "chat_id": "123"},
        }
    )
    sent = []
    answered = []

    class FakeBot:
        def __init__(self, telegram) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def set_commands(self) -> None:
            pass

        def get_updates(self, offset=None, timeout=30):
            return [
                {
                    "update_id": 1,
                    "callback_query": {
                        "id": "cb-1",
                        "message": {"chat": {"id": 123}},
                        "data": "cmd:providers",
                    },
                }
            ]

        def answer_callback_query(self, callback_query_id, text=None):
            answered.append((callback_query_id, text))

        def send_message(self, text, chat_id=None, reply_markup=None):
            sent.append((text, chat_id, reply_markup))

    monkeypatch.setattr("vps_dueguard.notifications.TelegramBot", FakeBot)

    run_bot(config, stop_after=lambda: bool(sent))

    assert answered == [("cb-1", None)]
    assert sent[0][0].startswith("<b>Providers</b>")
    assert sent[0][1] == "123"
    assert sent[0][2]["inline_keyboard"][0][0]["callback_data"] == "provider:0"


def test_run_bot_sends_progress_message_for_slow_callback(monkeypatch) -> None:
    config = AppConfig.model_validate(
        {
            "providers": [
                {
                    "name": "provider-a",
                    "base_url": "https://provider-a.example",
                    "username": "user@example.com",
                    "password": "secret",
                }
            ],
            "telegram": {"bot_token": "token", "chat_id": "123"},
        }
    )
    sent = []
    answered = []

    class FakeBot:
        def __init__(self, telegram) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def set_commands(self) -> None:
            pass

        def get_updates(self, offset=None, timeout=30):
            return [
                {
                    "update_id": 1,
                    "callback_query": {
                        "id": "cb-1",
                        "message": {"chat": {"id": 123}},
                        "data": "cmd:summary",
                    },
                }
            ]

        def answer_callback_query(self, callback_query_id, text=None):
            answered.append((callback_query_id, text))

        def send_message(self, text, chat_id=None, reply_markup=None):
            sent.append((text, chat_id, reply_markup))

    def fake_handle_bot_callback(_data, _config, _cache):
        return "final result", None

    monkeypatch.setattr("vps_dueguard.notifications.TelegramBot", FakeBot)
    monkeypatch.setattr("vps_dueguard.notifications.handle_bot_callback", fake_handle_bot_callback)

    run_bot(config, stop_after=lambda: len(sent) >= 2)

    assert answered == [("cb-1", "Querying, please wait...")]
    assert sent[0] == ("<b>Querying</b>\nFetching VPS data. Please wait.", "123", None)
    assert sent[1] == ("final result", "123", None)


def test_run_bot_suppresses_duplicate_callback_clicks(monkeypatch) -> None:
    config = AppConfig.model_validate(
        {
            "providers": [
                {
                    "name": "provider-a",
                    "base_url": "https://provider-a.example",
                    "username": "user@example.com",
                    "password": "secret",
                }
            ],
            "telegram": {"bot_token": "token", "chat_id": "123"},
        }
    )
    calls = []
    sent = []
    answered = []
    updates_seen = {"done": False}

    class FakeBot:
        def __init__(self, telegram) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def set_commands(self) -> None:
            pass

        def get_updates(self, offset=None, timeout=30):
            updates_seen["done"] = True
            return [
                {
                    "update_id": 1,
                    "callback_query": {
                        "id": "cb-1",
                        "message": {"chat": {"id": 123}},
                        "data": "cmd:summary",
                    },
                },
                {
                    "update_id": 2,
                    "callback_query": {
                        "id": "cb-2",
                        "message": {"chat": {"id": 123}},
                        "data": "cmd:summary",
                    },
                },
            ]

        def answer_callback_query(self, callback_query_id, text=None):
            answered.append((callback_query_id, text))

        def send_message(self, text, chat_id=None, reply_markup=None):
            sent.append((text, chat_id, reply_markup))

    def fake_handle_bot_callback(data, _config, _cache):
        calls.append(data)
        return "final result", None

    monkeypatch.setattr("vps_dueguard.notifications.TelegramBot", FakeBot)
    monkeypatch.setattr("vps_dueguard.notifications.handle_bot_callback", fake_handle_bot_callback)

    run_bot(config, stop_after=lambda: updates_seen["done"])

    assert calls == ["cmd:summary"]
    assert answered == [
        ("cb-1", "Querying, please wait..."),
        ("cb-2", "Request already received. Please wait."),
    ]
    assert [message[0] for message in sent] == [
        "<b>Querying</b>\nFetching VPS data. Please wait.",
        "final result",
    ]


def test_run_bot_ignores_expired_duplicate_callback_ack(monkeypatch) -> None:
    config = AppConfig.model_validate(
        {
            "providers": [
                {
                    "name": "provider-a",
                    "base_url": "https://provider-a.example",
                    "username": "user@example.com",
                    "password": "secret",
                }
            ],
            "telegram": {"bot_token": "token", "chat_id": "123"},
        }
    )
    calls = []
    sent = []
    answered = []
    updates_seen = {"done": False}

    class FakeBot:
        def __init__(self, telegram) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def set_commands(self) -> None:
            pass

        def get_updates(self, offset=None, timeout=30):
            updates_seen["done"] = True
            return [
                {
                    "update_id": 1,
                    "callback_query": {
                        "id": "cb-1",
                        "message": {"chat": {"id": 123}},
                        "data": "cmd:summary",
                    },
                },
                {
                    "update_id": 2,
                    "callback_query": {
                        "id": "cb-2",
                        "message": {"chat": {"id": 123}},
                        "data": "cmd:summary",
                    },
                },
            ]

        def answer_callback_query(self, callback_query_id, text=None):
            answered.append((callback_query_id, text))
            if callback_query_id == "cb-2":
                raise httpx.HTTPStatusError("400 Bad Request", request=httpx.Request("POST", "https://example.test"), response=httpx.Response(400))

        def send_message(self, text, chat_id=None, reply_markup=None):
            sent.append((text, chat_id, reply_markup))

    def fake_handle_bot_callback(data, _config, _cache):
        calls.append(data)
        return "final result", None

    monkeypatch.setattr("vps_dueguard.notifications.TelegramBot", FakeBot)
    monkeypatch.setattr("vps_dueguard.notifications.handle_bot_callback", fake_handle_bot_callback)

    run_bot(config, stop_after=lambda: updates_seen["done"])

    assert calls == ["cmd:summary"]
    assert answered == [
        ("cb-1", "Querying, please wait..."),
        ("cb-2", "Request already received. Please wait."),
    ]
    assert [message[0] for message in sent] == [
        "<b>Querying</b>\nFetching VPS data. Please wait.",
        "final result",
    ]
    assert all("Error:" not in message[0] for message in sent)


def test_calculate_traffic_percentage() -> None:
    assert calculate_traffic_percentage("20 GB / 1 TB", "1004.00 GB") is not None
    pct = calculate_traffic_percentage("20 GB / 1 TB", "1004.00 GB")
    assert 1.0 < pct < 3.0

    assert calculate_traffic_percentage("800 GB / 1 TB", "224.00 GB") is not None
    pct = calculate_traffic_percentage("800 GB / 1 TB", "224.00 GB")
    assert 78.0 < pct < 82.0

    assert calculate_traffic_percentage("unknown", "1004.00 GB") is None
    assert calculate_traffic_percentage("20 GB / 1 TB", "unknown") is not None
    assert calculate_traffic_percentage("unknown", "unknown") is None


def test_build_traffic_alerts_basic(tmp_path) -> None:
    state_file = tmp_path / "state.json"
    svc = ServiceInfo(
        provider="provider-a",
        service_name="Tokyo VPS",
        status="Active",
        expires_at="2026-12-31",
        traffic_usage="850 GB / 1 TB",
        traffic_remaining="174.00 GB",
        detail_url="https://example.com/service",
    )

    alerts = build_traffic_alerts([svc], 80, state_file)

    assert len(alerts) == 1
    assert "Traffic Alert" in alerts[0]
    assert "85" in alerts[0]


def test_build_traffic_alerts_below_threshold(tmp_path) -> None:
    state_file = tmp_path / "state.json"
    svc = ServiceInfo(
        provider="provider-a",
        service_name="Tokyo VPS",
        status="Active",
        expires_at="2026-12-31",
        traffic_usage="20 GB / 1 TB",
        traffic_remaining="1004.00 GB",
        detail_url="https://example.com/service",
    )

    alerts = build_traffic_alerts([svc], 80, state_file)

    assert alerts == []


def test_build_traffic_alerts_deduplication(tmp_path) -> None:
    state_file = tmp_path / "state.json"
    svc = ServiceInfo(
        provider="provider-a",
        service_name="Tokyo VPS",
        status="Active",
        expires_at="2026-12-31",
        traffic_usage="850 GB / 1 TB",
        traffic_remaining="174.00 GB",
        detail_url="https://example.com/service",
    )

    first = build_traffic_alerts([svc], 80, state_file)
    second = build_traffic_alerts([svc], 80, state_file)

    assert len(first) == 1
    assert second == []


def test_build_traffic_alerts_new_bracket(tmp_path) -> None:
    state_file = tmp_path / "state.json"
    svc_85 = ServiceInfo(
        provider="provider-a",
        service_name="Tokyo VPS",
        status="Active",
        expires_at="2026-12-31",
        traffic_usage="850 GB / 1 TB",
        traffic_remaining="174.00 GB",
        detail_url="https://example.com/service",
    )
    svc_95 = ServiceInfo(
        provider="provider-a",
        service_name="Tokyo VPS",
        status="Active",
        expires_at="2026-12-31",
        traffic_usage="950 GB / 1 TB",
        traffic_remaining="74.00 GB",
        detail_url="https://example.com/service",
    )

    first = build_traffic_alerts([svc_85], 80, state_file)
    second = build_traffic_alerts([svc_95], 80, state_file)

    assert len(first) == 1
    assert len(second) == 1
    assert "95" in second[0]


def test_build_traffic_alerts_unknown_traffic(tmp_path) -> None:
    state_file = tmp_path / "state.json"
    svc = ServiceInfo(
        provider="provider-a",
        service_name="Tokyo VPS",
        status="Active",
        expires_at="2026-12-31",
        traffic_usage="unknown",
        traffic_remaining="unknown",
        detail_url="https://example.com/service",
    )

    alerts = build_traffic_alerts([svc], 80, state_file)

    assert alerts == []


def test_format_cost_summary() -> None:
    services = [
        ServiceInfo(
            provider="provider-a",
            service_name="Tokyo VPS",
            status="Active",
            expires_at="2026-12-31",
            traffic_usage="20 GB / 1 TB",
            traffic_remaining="1004.00 GB",
            price="$3.50 USD",
            detail_url="https://example.com/1",
        ),
        ServiceInfo(
            provider="provider-a",
            service_name="Osaka VPS",
            status="Active",
            expires_at="2026-12-31",
            traffic_usage="10 GB / 500 GB",
            traffic_remaining="502.00 GB",
            price="$5.00 USD",
            detail_url="https://example.com/2",
        ),
        ServiceInfo(
            provider="provider-b",
            service_name="Singapore VPS",
            status="Active",
            expires_at="2026-12-31",
            traffic_usage="50 GB / 2 TB",
            traffic_remaining="2000.00 GB",
            price="$10.00 USD",
            detail_url="https://example.com/3",
        ),
    ]

    report = format_cost_summary(services)

    assert "<b>VPS Cost Summary</b>" in report
    assert "provider-a" in report
    assert "provider-b" in report
    assert "$3.50 USD" in report
    assert "$5.00 USD" in report
    assert "$10.00 USD" in report
    assert "Subtotal" in report
    assert "Grand Total" in report


def test_format_cost_summary_no_prices() -> None:
    services = [
        ServiceInfo(
            provider="provider-a",
            service_name="Tokyo VPS",
            status="Active",
            expires_at="2026-12-31",
            traffic_usage="20 GB / 1 TB",
            traffic_remaining="1004.00 GB",
            price="unknown",
            detail_url="https://example.com/1",
        ),
    ]

    report = format_cost_summary(services)

    assert "No price data available" in report


def test_format_cost_summary_empty() -> None:
    report = format_cost_summary([])

    assert "No active services found" in report


def test_parse_price_amount() -> None:
    assert parse_price_amount("$3.50 USD") == (3.5, "USD")
    assert parse_price_amount("€10.00") == (10.0, "EUR")
    assert parse_price_amount("£25.00 GBP") == (25.0, "GBP")
    assert parse_price_amount("¥100.00") == (100.0, "CNY")
    assert parse_price_amount("CNY 25.00") == (25.0, "CNY")
    assert parse_price_amount("unknown") == (0.0, "")
    assert parse_price_amount("") == (0.0, "")
    assert parse_price_amount("$1,234.56 USD") == (1234.56, "USD")


def test_format_cost_summary_escape_html() -> None:
    services = [
        ServiceInfo(
            provider="provider-<a>",
            service_name="Tokyo & Osaka VPS",
            status="Active",
            expires_at="2026-12-31",
            traffic_usage="20 GB / 1 TB",
            traffic_remaining="1004.00 GB",
            price="$3.50 USD",
            detail_url="https://example.com/1",
        ),
    ]

    report = format_cost_summary(services)

    assert "provider-&lt;a&gt;" in report
    assert "Tokyo &amp; Osaka VPS" in report


def test_bot_cost_command(monkeypatch) -> None:
    config = AppConfig.model_validate(
        {
            "providers": [
                {
                    "name": "provider-a",
                    "base_url": "https://provider-a.example",
                    "username": "user@example.com",
                    "password": "secret",
                }
            ],
            "telegram": {"bot_token": "token", "chat_id": "123"},
        }
    )

    def fake_collect_services(config, provider_name=None):
        return [service(price="$3.50 USD")], []

    monkeypatch.setattr("vps_dueguard.notifications.collect_services", fake_collect_services)

    reply = handle_bot_command("/cost", config, ServiceCache())

    assert "VPS Cost Summary" in reply
    assert "$3.50 USD" in reply


def test_split_message_short() -> None:
    text = "Hello world"
    assert _split_message(text) == ["Hello world"]


def test_split_message_long() -> None:
    lines = [f"Line {i}" for i in range(1000)]
    text = "\n".join(lines)

    parts = _split_message(text)

    assert len(parts) > 1
    for part in parts:
        assert len(part) <= 4096
    assert "\n".join(parts) == text


def test_split_message_preserves_line_boundaries() -> None:
    lines = [f"<b>Line {i}</b>" for i in range(500)]
    text = "\n".join(lines)

    parts = _split_message(text)

    for part in parts:
        assert len(part) <= 4096
    reassembled = "\n".join(parts)
    assert reassembled == text


def test_split_message_avoids_cutting_html_tags() -> None:
    long_line = "<b>" + "x" * 4090 + "</b>"
    parts = _split_message(long_line)

    assert len(parts) >= 2
    for part in parts:
        assert len(part) <= 4096


def test_format_cost_summary_multi_currency() -> None:
    services = [
        ServiceInfo(
            provider="provider-a",
            service_name="Tokyo VPS",
            status="Active",
            expires_at="2026-12-31",
            traffic_usage="20 GB / 1 TB",
            traffic_remaining="1004.00 GB",
            price="$3.50 USD",
            detail_url="https://example.com/1",
        ),
        ServiceInfo(
            provider="provider-b",
            service_name="Frankfurt VPS",
            status="Active",
            expires_at="2026-12-31",
            traffic_usage="10 GB / 500 GB",
            traffic_remaining="502.00 GB",
            price="€5.00 EUR",
            detail_url="https://example.com/2",
        ),
    ]

    report = format_cost_summary(services)

    assert "$3.50 USD" in report
    assert "€5.00 EUR" in report
    assert report.count("Grand Total") == 2
