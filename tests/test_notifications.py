from datetime import date

import httpx
import pytest

from vps_dueguard.models import AppConfig, ServiceInfo
from vps_dueguard.notifications import (
    ServiceCache,
    TelegramBot,
    TelegramError,
    build_renewal_alerts,
    format_service_date,
    format_renewals_report,
    format_summary,
    format_traffic_report,
    handle_bot_command,
    parse_service_date,
    require_telegram,
    run_bot,
)


def service(expires_at: str = "2026-06-16") -> ServiceInfo:
    return ServiceInfo(
        provider="provider-a",
        service_name="Tokyo VPS",
        status="Active",
        expires_at=expires_at,
        traffic_usage="20 GB / 1 TB",
        traffic_remaining="1004.00 GB",
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

    assert "VPS Summary" in format_summary(services)
    assert "expires 2026-06-16" in format_summary(services)
    assert "VPS Traffic" in format_traffic_report(services)
    assert "1004.00 GB" in format_traffic_report(services)
    assert "VPS Renewals" in format_renewals_report(services, today=date(2026, 6, 2))


def test_format_reports_show_provider_errors_prominently() -> None:
    summary = format_summary([], ["provider-a: login failed"])
    traffic = format_traffic_report([], ["provider-a: login failed"])
    renewals = format_renewals_report([], ["provider-a: login failed"], today=date(2026, 6, 2))

    assert "No active services were loaded." in summary
    assert "Provider errors:" in summary
    assert "- provider-a: login failed" in summary
    assert "No traffic data was loaded." in traffic
    assert "Provider errors:" in traffic
    assert "No renewal dates were loaded." in renewals
    assert "Provider errors:" in renewals


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
    assert "Unknown command" in handle_bot_command("/wat", config)


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
    assert "Provider errors:" in reply


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

        def send_message(self, text, chat_id=None):
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

        def send_message(self, text, chat_id=None):
            replies.append((text, chat_id))

    def fail_handle_bot_command(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("vps_dueguard.notifications.TelegramBot", FakeBot)
    monkeypatch.setattr("vps_dueguard.notifications.handle_bot_command", fail_handle_bot_command)

    run_bot(config, stop_after=lambda: bool(replies))

    assert replies == [("Error: boom", "123")]
