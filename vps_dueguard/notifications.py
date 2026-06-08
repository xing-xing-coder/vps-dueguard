from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from html import escape as html_escape
from pathlib import Path
from typing import Callable

import httpx

from .client import ProviderError, fetch_provider_services
from .models import AppConfig, ServiceInfo, TelegramConfig, load_config


class TelegramError(RuntimeError):
    pass


BOT_COMMANDS = [
    ("summary", "All active VPS services"),
    ("traffic", "Traffic usage and remaining traffic"),
    ("renewals", "Renewal dates and days left"),
    ("providers", "List configured providers"),
    ("provider", "Query one provider, e.g. /provider provider-a"),
    ("refresh", "Refresh cached VPS data"),
    ("help", "Show help"),
]


class TelegramBot:
    def __init__(self, config: TelegramConfig, timeout: float = 45.0) -> None:
        self.config = config
        self.base_url = f"https://api.telegram.org/bot{config.bot_token.get_secret_value()}"
        self.client = httpx.Client(timeout=timeout)

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> "TelegramBot":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def send_message(self, text: str, chat_id: str | None = None, reply_markup: dict[str, object] | None = None) -> None:
        payload: dict[str, object] = {
            "chat_id": chat_id or self.config.chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        response = self.client.post(
            f"{self.base_url}/sendMessage",
            json=payload,
        )
        response.raise_for_status()
        payload = response.json()
        if not payload.get("ok"):
            raise TelegramError(str(payload))

    def answer_callback_query(self, callback_query_id: str, text: str | None = None) -> None:
        payload: dict[str, object] = {"callback_query_id": callback_query_id}
        if text:
            payload["text"] = text
        response = self.client.post(
            f"{self.base_url}/answerCallbackQuery",
            json=payload,
        )
        response.raise_for_status()
        payload = response.json()
        if not payload.get("ok"):
            raise TelegramError(str(payload))

    def get_updates(self, offset: int | None = None, timeout: int = 30) -> list[dict[str, object]]:
        params: dict[str, object] = {"timeout": timeout}
        if offset is not None:
            params["offset"] = offset
        response = self.client.get(f"{self.base_url}/getUpdates", params=params)
        response.raise_for_status()
        payload = response.json()
        if not payload.get("ok"):
            raise TelegramError(str(payload))
        return list(payload.get("result") or [])

    def set_commands(self) -> None:
        response = self.client.post(
            f"{self.base_url}/setMyCommands",
            json={
                "commands": [
                    {"command": command, "description": description}
                    for command, description in BOT_COMMANDS
                ]
            },
        )
        response.raise_for_status()
        payload = response.json()
        if not payload.get("ok"):
            raise TelegramError(str(payload))


def require_telegram(config: AppConfig) -> TelegramConfig:
    if config.telegram is None:
        raise TelegramError("Missing telegram config. Add telegram.bot_token and telegram.chat_id to config.yaml.")
    return config.telegram


def collect_services(config: AppConfig, provider_name: str | None = None) -> tuple[list[ServiceInfo], list[str]]:
    services: list[ServiceInfo] = []
    errors: list[str] = []
    try:
        providers = config.provider_subset(provider_name)
    except ValueError as exc:
        return [], [str(exc)]

    for provider in providers:
        try:
            services.extend(normalize_service_dates(fetch_provider_services(provider, config.sessions)))
        except ProviderError as exc:
            errors.append(str(exc))
        except Exception as exc:
            errors.append(f"{provider.name}: {exc}")
    return services, errors


def normalize_service_dates(services: list[ServiceInfo]) -> list[ServiceInfo]:
    normalized: list[ServiceInfo] = []
    for service in services:
        expires_at = format_service_date(service.expires_at)
        if expires_at != service.expires_at:
            service = service.model_copy(update={"expires_at": expires_at})
        normalized.append(service)
    return normalized


def format_summary(services: list[ServiceInfo], errors: list[str] | None = None) -> str:
    lines = ["<b>VPS Summary</b>"]
    if services:
        for service in services:
            lines.extend(_service_block(service, include_traffic=True, include_expiry=True))
    elif errors:
        lines.extend(["", "No active services were loaded."])
    else:
        lines.extend(["", "No active services found."])
    lines.extend(_error_lines(errors))
    return _join_lines(lines)


def format_traffic_report(services: list[ServiceInfo], errors: list[str] | None = None) -> str:
    lines = ["<b>VPS Traffic</b>"]
    if services:
        for service in services:
            lines.extend(_service_block(service, include_traffic=True, include_expiry=False))
    elif errors:
        lines.extend(["", "No traffic data was loaded."])
    else:
        lines.extend(["", "No active services found."])
    lines.extend(_error_lines(errors))
    return _join_lines(lines)


def format_renewals_report(services: list[ServiceInfo], errors: list[str] | None = None, today: date | None = None) -> str:
    today = today or date.today()
    lines = ["<b>VPS Renewals</b>"]
    dated = [(service, parse_service_date(service.expires_at)) for service in services]
    dated = [(service, expires_at) for service, expires_at in dated if expires_at is not None]
    dated.sort(key=lambda item: item[1])
    if dated:
        lines.append("")
        for service, expires_at in dated:
            days = (expires_at - today).days
            lines.extend(
                [
                    f"<b>{_html(service.provider)}</b> - {_html(service.service_name)}",
                    f"Expires: {_html(expires_at.isoformat())}",
                    f"Days left: <b>{days}</b>",
                    "",
                ]
            )
    elif errors:
        lines.extend(["", "No renewal dates were loaded."])
    else:
        lines.extend(["", "No services with known renewal dates found."])
    lines.extend(_error_lines(errors))
    return _join_lines(lines)


def format_help() -> str:
    return (
        "<b>Commands</b>\n"
        "/summary - all active VPS services\n"
        "/traffic - traffic usage and remaining traffic\n"
        "/renewals - renewal dates and days left\n"
        "/providers - list configured providers\n"
        "/provider &lt;name&gt; - query one provider\n"
        "/refresh - refresh cached VPS data"
    )


def format_provider_list(config: AppConfig) -> str:
    if not config.providers:
        return (
            "<b>No providers configured.</b>\n"
            "Run vpsm, open provider management, add at least one provider, then send /refresh."
        )
    lines = ["<b>Providers</b>", ""]
    lines.extend(f"- {_html(provider.name)}" for provider in config.providers)
    return _join_lines(lines)


def main_menu_markup() -> dict[str, object]:
    return {
        "inline_keyboard": [
            [
                {"text": "Summary", "callback_data": "cmd:summary"},
                {"text": "Traffic", "callback_data": "cmd:traffic"},
            ],
            [
                {"text": "Renewals", "callback_data": "cmd:renewals"},
                {"text": "Providers", "callback_data": "cmd:providers"},
            ],
            [{"text": "Refresh", "callback_data": "cmd:refresh"}],
        ]
    }


def providers_menu_markup(config: AppConfig) -> dict[str, object]:
    rows = [
        [{"text": provider.name, "callback_data": f"provider:{index}"}]
        for index, provider in enumerate(config.providers)
    ]
    rows.append([{"text": "Main menu", "callback_data": "cmd:help"}])
    return {"inline_keyboard": rows}


def reply_markup_for_command(command: str, config: AppConfig) -> dict[str, object] | None:
    name = _command_name(command)
    if name in {"/help", "/start"}:
        return main_menu_markup()
    if name == "/providers":
        return providers_menu_markup(config) if config.providers else main_menu_markup()
    return None


def build_renewal_alerts(
    services: list[ServiceInfo],
    thresholds: list[int],
    state_path: Path,
    today: date | None = None,
) -> list[str]:
    today = today or date.today()
    state = _load_state(state_path)
    sent: set[str] = set(state.get("sent_renewals") or [])
    alerts: list[str] = []

    for service in services:
        expires_at = parse_service_date(service.expires_at)
        if expires_at is None:
            continue
        days_left = (expires_at - today).days
        if days_left < 0:
            continue
        matching_thresholds = [threshold for threshold in thresholds if threshold >= days_left]
        if not matching_thresholds:
            continue
        threshold = min(matching_thresholds)

        key = _renewal_key(service, expires_at, threshold)
        if key in sent:
            continue
        sent.add(key)
        alerts.append(
            "<b>Renewal Reminder</b>\n"
            f"{_html(service.provider)} - {_html(service.service_name)}\n"
            f"Expires: {_html(expires_at.isoformat())} ({days_left} days left)\n"
            f"Traffic: {_html(service.traffic_usage)}, remaining {_html(service.traffic_remaining)}"
        )

    state["sent_renewals"] = sorted(sent)
    _save_state(state_path, state)
    return alerts


def parse_service_date(value: str) -> date | None:
    value = value.strip()
    for pattern in ("%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(value, pattern).date()
        except ValueError:
            pass

    cleaned = re.sub(r"(\d+)(st|nd|rd|th)", r"\1", value)
    for pattern in ("%A, %B %d, %Y", "%B %d, %Y", "%d %B %Y"):
        try:
            return datetime.strptime(cleaned, pattern).date()
        except ValueError:
            pass
    return None


def format_service_date(value: str) -> str:
    parsed = parse_service_date(value)
    return parsed.isoformat() if parsed else value


@dataclass
class ServiceCache:
    ttl_seconds: int = 300
    services: list[ServiceInfo] | None = None
    errors: list[str] | None = None
    fetched_at: float = 0.0

    def get(self) -> tuple[list[ServiceInfo], list[str]] | None:
        if self.services is None or self.errors is None:
            return None
        if time.time() - self.fetched_at > self.ttl_seconds:
            return None
        return self.services, self.errors

    def set(self, services: list[ServiceInfo], errors: list[str]) -> None:
        self.services = services
        self.errors = errors
        self.fetched_at = time.time()

    def clear(self) -> None:
        self.services = None
        self.errors = None
        self.fetched_at = 0.0


@dataclass
class CallbackDeduper:
    ttl_seconds: int = 60
    seen: dict[str, float] = field(default_factory=dict)

    def accept(self, chat_id: str, data: str) -> bool:
        now = time.time()
        for key, timestamp in list(self.seen.items()):
            if now - timestamp > self.ttl_seconds:
                del self.seen[key]
        key = f"{chat_id}|{data}"
        if key in self.seen:
            return False
        self.seen[key] = now
        return True


def handle_bot_command(command: str, config: AppConfig, cache: ServiceCache | None = None) -> str:
    parts = command.strip().split()
    name = _command_name(command)
    known_commands = {"/summary", "/traffic", "/renewals", "/providers", "/provider", "/refresh", "/help", "/start"}

    if name in {"/help", "/start"}:
        return format_help()
    if name not in known_commands:
        return "Unknown command. Send /help for available commands."
    if name == "/providers":
        return format_provider_list(config)
    if not config.providers:
        return (
            "<b>No providers configured.</b>\n"
            "Run vpsm, open provider management, add at least one provider, then send /refresh."
        )

    provider_name = parts[1] if name == "/provider" and len(parts) > 1 else None
    if name == "/provider":
        if provider_name is None:
            return "Usage: /provider <name>"
        services, errors = collect_services(config, provider_name)
    elif name == "/refresh":
        services, errors = collect_services(config)
        if cache is not None:
            cache.set(services, errors)
        return format_summary(services, errors)
    else:
        cached = cache.get() if cache is not None else None
        if cached is None:
            services, errors = collect_services(config)
            if cache is not None:
                cache.set(services, errors)
        else:
            services, errors = cached

    if name == "/summary":
        return format_summary(services, errors)
    if name == "/traffic":
        return format_traffic_report(services, errors)
    if name == "/renewals":
        return format_renewals_report(services, errors)
    if name == "/provider":
        return format_summary(services, errors)
    return "Unknown command. Send /help for available commands."


def handle_bot_callback(data: str, config: AppConfig, cache: ServiceCache | None = None) -> tuple[str, dict[str, object] | None]:
    if data.startswith("cmd:"):
        command = f"/{data.removeprefix('cmd:')}"
        return handle_bot_command(command, config, cache), reply_markup_for_command(command, config)

    if data.startswith("provider:"):
        raw_index = data.removeprefix("provider:")
        try:
            index = int(raw_index)
        except ValueError:
            return "Provider selection is no longer valid. Send /providers to load the latest list.", providers_menu_markup(config)
        if index < 0 or index >= len(config.providers):
            return "Provider selection is no longer valid. Send /providers to load the latest list.", providers_menu_markup(config)
        provider = config.providers[index]
        return handle_bot_command(f"/provider {provider.name}", config, cache), None

    return "Unknown button. Send /help for available commands.", main_menu_markup()


def callback_needs_progress(data: str) -> bool:
    if data.startswith("provider:"):
        return True
    if not data.startswith("cmd:"):
        return False
    return data.removeprefix("cmd:") in {"summary", "traffic", "renewals", "refresh"}


def callback_progress_message(data: str) -> str:
    if data == "cmd:refresh":
        return "<b>Refreshing</b>\nFetching fresh VPS data. Please wait."
    return "<b>Querying</b>\nFetching VPS data. Please wait."


def run_bot(
    config: AppConfig,
    stop_after: Callable[[], bool] | None = None,
    config_path: Path | None = None,
) -> None:
    telegram = require_telegram(config)
    offset: int | None = None
    cache = ServiceCache()
    callback_deduper = CallbackDeduper()
    runtime_config = config
    config_mtime: float | None = None
    stop_after = stop_after or (lambda: False)

    def latest_config() -> AppConfig:
        nonlocal runtime_config, config_mtime
        if config_path is None:
            return runtime_config
        mtime = config_path.stat().st_mtime
        if config_mtime != mtime:
            runtime_config = load_config(config_path)
            config_mtime = mtime
            cache.clear()
        return runtime_config

    with TelegramBot(telegram) as bot:
        try:
            bot.set_commands()
        except Exception:
            pass
        while not stop_after():
            try:
                updates = bot.get_updates(offset=offset, timeout=30)
            except (httpx.ReadTimeout, httpx.HTTPError, TelegramError):
                time.sleep(1)
                continue
            for update in updates:
                update_id = update.get("update_id")
                if isinstance(update_id, int):
                    offset = update_id + 1
                app_config: AppConfig | None = None
                message = update.get("message")
                if isinstance(message, dict):
                    chat = message.get("chat")
                    if not isinstance(chat, dict):
                        continue
                    chat_id = str(chat.get("id"))
                    text = str(message.get("text") or "").strip()
                    if not text.startswith("/"):
                        continue
                    try:
                        app_config = latest_config()
                        if chat_id != require_telegram(app_config).chat_id:
                            continue
                        reply = handle_bot_command(text, app_config, cache)
                        reply_markup = reply_markup_for_command(text, app_config)
                    except Exception as exc:
                        reply = _runtime_error(exc)
                        reply_markup = None
                    try:
                        bot.send_message(reply, chat_id=chat_id, reply_markup=reply_markup)
                    except Exception:
                        continue
                    continue

                callback = update.get("callback_query")
                if not isinstance(callback, dict):
                    continue
                callback_id = str(callback.get("id") or "")
                message = callback.get("message")
                chat = message.get("chat") if isinstance(message, dict) else None
                if not isinstance(chat, dict):
                    continue
                chat_id = str(chat.get("id"))
                data = str(callback.get("data") or "")
                try:
                    app_config = latest_config()
                    if chat_id != require_telegram(app_config).chat_id:
                        continue
                    if callback_id:
                        if not callback_deduper.accept(chat_id, data):
                            _safe_answer_callback_query(bot, callback_id, "Request already received. Please wait.")
                            continue
                        _safe_answer_callback_query(
                            bot,
                            callback_id,
                            "Querying, please wait..." if callback_needs_progress(data) else None,
                        )
                    if callback_needs_progress(data):
                        try:
                            bot.send_message(callback_progress_message(data), chat_id=chat_id)
                        except Exception:
                            pass
                    reply, reply_markup = handle_bot_callback(data, app_config, cache)
                except Exception as exc:
                    reply = _runtime_error(exc)
                    reply_markup = None
                try:
                    bot.send_message(reply, chat_id=chat_id, reply_markup=reply_markup)
                except Exception:
                    continue
            if not updates:
                time.sleep(1)


def _service_block(service: ServiceInfo, include_traffic: bool, include_expiry: bool) -> list[str]:
    lines = [
        "",
        f"<b>{_html(service.provider)}</b> - {_html(service.service_name)}",
        f"Status: {_html(service.status)}",
    ]
    if include_expiry:
        lines.append(f"Expires: {_html(format_service_date(service.expires_at))}")
    if include_traffic:
        lines.append(f"Traffic: {_html(service.traffic_usage)}")
        lines.append(f"Remaining: {_html(service.traffic_remaining)}")
    return lines


def _error_lines(errors: list[str] | None) -> list[str]:
    if not errors:
        return []
    lines = ["", "<b>Provider errors</b>"]
    lines.extend(f"- {_html(error)}" for error in errors)
    return lines


def _runtime_error(exc: Exception) -> str:
    return f"<b>Error:</b> {_html(exc)}"


def _safe_answer_callback_query(bot: TelegramBot, callback_id: str, text: str | None = None) -> None:
    try:
        bot.answer_callback_query(callback_id, text)
    except Exception:
        pass


def _command_name(command: str) -> str:
    parts = command.strip().split()
    return parts[0].split("@", 1)[0].lower() if parts else "/help"


def _html(value: object) -> str:
    return html_escape(str(value), quote=False)


def _join_lines(lines: list[str]) -> str:
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines)


def _renewal_key(service: ServiceInfo, expires_at: date, threshold: int) -> str:
    return f"{service.provider}|{service.service_name}|{expires_at.isoformat()}|{threshold}"


def _load_state(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _save_state(path: Path, state: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(state, handle, ensure_ascii=False, indent=2)
