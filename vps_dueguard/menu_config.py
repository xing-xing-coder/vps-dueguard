from __future__ import annotations

import argparse
import os
import re
from pathlib import Path
from typing import Any

import yaml

DEFAULT_RENEWAL_DAYS = [21, 14, 7, 3]
DEFAULT_TRAFFIC_THRESHOLD = 80
DEFAULT_TRAFFIC_INTERVAL_HOURS = 6


def load_menu_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    text = path.read_text("utf-8", errors="ignore")
    text = "".join(ch for ch in text if ch in "\n\r\t" or ord(ch) >= 32)
    try:
        data = yaml.safe_load(text) or {}
    except yaml.YAMLError:
        return {}
    return data if isinstance(data, dict) else {}


def ensure_parseable_config(path: Path) -> None:
    if not path.exists():
        return
    text = path.read_text("utf-8", errors="ignore")
    text = "".join(ch for ch in text if ch in "\n\r\t" or ord(ch) >= 32)
    try:
        yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise SystemExit(f"config YAML is invalid; refusing to overwrite it: {exc}") from exc


def clean_scalar(value: Any, key: str | None = None) -> str:
    text = "" if value is None else str(value)
    for _ in range(12):
        before = text
        text = "".join(ch for ch in text if ch in "\n\r\t" or ord(ch) >= 32).strip()
        text = text.replace(r"\"", '"').replace(r"\\", "\\").strip()
        if key:
            matches = re.findall(rf"{re.escape(key)}\s*:\s*(.+)", text)
            if matches:
                text = matches[-1].strip()
                continue
        stripped = text.strip()
        if len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in {"'", '"'}:
            text = stripped[1:-1]
            continue
        if stripped.startswith(("'", '"')):
            text = stripped[1:]
            continue
        if stripped.endswith(("'", '"')):
            text = stripped[:-1]
            continue
        text = stripped
        if text == before:
            break
    if key and f"{key}:" in text:
        matches = re.findall(rf"{re.escape(key)}\s*:\s*(.+)", text)
        if matches:
            text = matches[-1].strip()
    return text.strip()


def normalize_renewal_days(value: Any) -> list[int]:
    if value in (None, ""):
        return DEFAULT_RENEWAL_DAYS.copy()
    if isinstance(value, int):
        values = [value]
    elif isinstance(value, list):
        values = []
        for item in value:
            if isinstance(item, list):
                values.extend(normalize_renewal_days(item))
            elif str(item).isdigit():
                values.append(int(item))
    elif isinstance(value, str):
        compact = value.strip()
        if not re.fullmatch(r"\d+(,\d+)*", compact):
            raise ValueError("renewal days must be comma-separated numbers, e.g. 21,14,7,3")
        values = [int(part) for part in compact.split(",")]
    else:
        raise ValueError("renewal days must be comma-separated numbers, e.g. 21,14,7,3")
    normalized = sorted({item for item in values if item >= 0}, reverse=True)
    return normalized or DEFAULT_RENEWAL_DAYS.copy()


def current_providers(data: dict[str, Any]) -> list[dict[str, str]]:
    providers = data.get("providers") or []
    if not isinstance(providers, list):
        return []
    cleaned: list[dict[str, str]] = []
    for item in providers:
        if not isinstance(item, dict):
            continue
        provider = {
            "name": clean_scalar(item.get("name")),
            "base_url": clean_scalar(item.get("base_url")),
            "username": clean_scalar(item.get("username")),
            "password": clean_scalar(item.get("password")),
        }
        if provider["name"]:
            cleaned.append(provider)
    return cleaned


def current_telegram(data: dict[str, Any]) -> dict[str, str]:
    telegram = data.get("telegram") if isinstance(data.get("telegram"), dict) else {}
    return {
        "bot_token": clean_scalar(telegram.get("bot_token"), "bot_token"),
        "chat_id": clean_scalar(telegram.get("chat_id"), "chat_id"),
    }


def current_renewal_days(data: dict[str, Any]) -> list[int]:
    notifications = data.get("notifications") if isinstance(data.get("notifications"), dict) else {}
    return normalize_renewal_days(notifications.get("renewal_days", DEFAULT_RENEWAL_DAYS))


def current_traffic_alerts(data: dict[str, Any]) -> dict[str, Any]:
    notifications = data.get("notifications") if isinstance(data.get("notifications"), dict) else {}
    traffic = notifications.get("traffic_alerts") if isinstance(notifications.get("traffic_alerts"), dict) else {}
    enabled_raw = traffic.get("enabled", True)
    enabled = bool(enabled_raw) if isinstance(enabled_raw, bool) else str(enabled_raw).lower() in ("true", "1", "yes")
    threshold_raw = traffic.get("threshold", DEFAULT_TRAFFIC_THRESHOLD)
    try:
        threshold = int(threshold_raw)
    except (TypeError, ValueError):
        threshold = DEFAULT_TRAFFIC_THRESHOLD
    if not 1 <= threshold <= 100:
        threshold = DEFAULT_TRAFFIC_THRESHOLD
    interval_raw = traffic.get("check_interval_hours", DEFAULT_TRAFFIC_INTERVAL_HOURS)
    try:
        interval = int(interval_raw)
    except (TypeError, ValueError):
        interval = DEFAULT_TRAFFIC_INTERVAL_HOURS
    if not 1 <= interval <= 168:
        interval = DEFAULT_TRAFFIC_INTERVAL_HOURS
    return {"enabled": enabled, "threshold": threshold, "check_interval_hours": interval}


def providers_from_yaml(text: str) -> list[dict[str, str]]:
    if not text.strip():
        return []
    try:
        parsed = yaml.safe_load("providers:\n" + text) or {}
    except yaml.YAMLError:
        return []
    return current_providers(parsed)


def dump_providers_yaml(providers: list[dict[str, str]]) -> str:
    if not providers:
        return ""
    dumped = yaml.safe_dump({"providers": providers}, allow_unicode=True, sort_keys=False)
    return "\n".join(dumped.splitlines()[1:]) + "\n"


def save_menu_config(
    path: Path,
    providers: list[dict[str, str]],
    bot_token: str,
    chat_id: str,
    renewal_days: list[int],
    traffic_alerts: dict[str, Any] | None = None,
) -> None:
    cleaned_token = clean_scalar(bot_token, "bot_token")
    cleaned_chat_id = clean_scalar(chat_id, "chat_id")
    if traffic_alerts is None:
        traffic_alerts = {"enabled": True, "threshold": DEFAULT_TRAFFIC_THRESHOLD, "check_interval_hours": DEFAULT_TRAFFIC_INTERVAL_HOURS}
    output = {
        "providers": providers,
        "notifications": {
            "renewal_days": renewal_days,
            "daily_report": True,
            "traffic_alerts": {
                "enabled": bool(traffic_alerts.get("enabled", True)),
                "threshold": int(traffic_alerts.get("threshold", DEFAULT_TRAFFIC_THRESHOLD)),
                "check_interval_hours": int(traffic_alerts.get("check_interval_hours", DEFAULT_TRAFFIC_INTERVAL_HOURS)),
            },
            "state_file": ".vps_dueguard_state.json",
        },
        "sessions": {"enabled": True, "session_dir": ".vps_sessions"},
    }
    if cleaned_token and cleaned_chat_id:
        output["telegram"] = {"bot_token": cleaned_token, "chat_id": cleaned_chat_id}
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.tmp")
    temp_path.write_text(yaml.safe_dump(output, allow_unicode=True, sort_keys=False), "utf-8")
    os.replace(temp_path, path)


def write_menu_config(path: Path, providers_yaml: str, bot_token: str, chat_id: str, renewal_days: str, traffic_alerts: dict[str, Any] | None = None) -> None:
    save_menu_config(
        path,
        providers_from_yaml(providers_yaml),
        bot_token,
        chat_id,
        normalize_renewal_days(renewal_days),
        traffic_alerts,
    )


def add_provider_config(
    path: Path,
    data: dict[str, Any],
    name: str,
    base_url: str,
    username: str,
    password: str,
) -> None:
    provider = {
        "name": clean_scalar(name),
        "base_url": clean_scalar(base_url),
        "username": clean_scalar(username),
        "password": clean_scalar(password),
    }
    if not provider["name"]:
        raise SystemExit("provider name is required")
    providers = current_providers(data)
    providers.append(provider)
    telegram = current_telegram(data)
    save_menu_config(
        path,
        providers,
        telegram["bot_token"],
        telegram["chat_id"],
        current_renewal_days(data),
        current_traffic_alerts(data),
    )


def set_telegram_config(path: Path, data: dict[str, Any], bot_token: str, chat_id: str, renewal_days: str) -> None:
    save_menu_config(
        path,
        current_providers(data),
        bot_token,
        chat_id,
        normalize_renewal_days(renewal_days),
        current_traffic_alerts(data),
    )


def set_renewal_days_config(path: Path, data: dict[str, Any], renewal_days: str) -> None:
    telegram = current_telegram(data)
    save_menu_config(
        path,
        current_providers(data),
        telegram["bot_token"],
        telegram["chat_id"],
        normalize_renewal_days(renewal_days),
        current_traffic_alerts(data),
    )


def set_traffic_alert_config(path: Path, data: dict[str, Any], enabled: bool, threshold: int, interval_hours: int | None = None) -> None:
    telegram = current_telegram(data)
    current = current_traffic_alerts(data)
    if interval_hours is None:
        interval_hours = current.get("check_interval_hours", DEFAULT_TRAFFIC_INTERVAL_HOURS)
    save_menu_config(
        path,
        current_providers(data),
        telegram["bot_token"],
        telegram["chat_id"],
        current_renewal_days(data),
        {"enabled": enabled, "threshold": threshold, "check_interval_hours": interval_hours},
    )


def repair_menu_config(path: Path, data: dict[str, Any]) -> None:
    ensure_parseable_config(path)
    telegram = current_telegram(data)
    save_menu_config(
        path,
        current_providers(data),
        telegram["bot_token"],
        telegram["chat_id"],
        current_renewal_days(data),
        current_traffic_alerts(data),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("action")
    parser.add_argument("args", nargs="*")
    args = parser.parse_args()
    data = load_menu_config(args.config)

    if args.action == "provider-count":
        print(len(current_providers(data)))
    elif args.action == "providers-yaml":
        print(dump_providers_yaml(current_providers(data)), end="")
    elif args.action == "providers-list":
        for item in current_providers(data):
            print(f"- {item['name']}")
            print(f"  URL: {item['base_url']}")
            print(f"  Username: {item['username']}")
            print(f"  Password: {item['password']}")
    elif args.action == "get":
        key = args.args[0]
        if key in {"bot_token", "chat_id"}:
            print(current_telegram(data)[key])
        elif key == "renewal_days":
            print(",".join(str(day) for day in current_renewal_days(data)))
        elif key == "traffic_threshold":
            print(current_traffic_alerts(data)["threshold"])
        elif key == "traffic_alerts_enabled":
            print("true" if current_traffic_alerts(data)["enabled"] else "false")
        elif key == "traffic_interval":
            print(current_traffic_alerts(data)["check_interval_hours"])
        else:
            raise SystemExit(f"unknown get key: {key}")
    elif args.action == "write":
        if len(args.args) != 4:
            raise SystemExit("write requires providers_yaml, bot_token, chat_id, renewal_days")
        write_menu_config(args.config, args.args[0], args.args[1], args.args[2], args.args[3])
    elif args.action == "add-provider":
        if len(args.args) != 4:
            raise SystemExit("add-provider requires name, base_url, username, password")
        add_provider_config(args.config, data, args.args[0], args.args[1], args.args[2], args.args[3])
    elif args.action == "set-telegram":
        if len(args.args) != 3:
            raise SystemExit("set-telegram requires bot_token, chat_id, renewal_days")
        set_telegram_config(args.config, data, args.args[0], args.args[1], args.args[2])
    elif args.action == "set-renewal-days":
        if len(args.args) != 1:
            raise SystemExit("set-renewal-days requires renewal_days")
        set_renewal_days_config(args.config, data, args.args[0])
    elif args.action == "set-traffic-alert":
        if len(args.args) < 2 or len(args.args) > 3:
            raise SystemExit("set-traffic-alert requires enabled (true/false), threshold (1-100), and optional interval_hours")
        enabled = args.args[0].lower() in ("true", "1", "yes")
        try:
            threshold = int(args.args[1])
        except ValueError:
            raise SystemExit("threshold must be a number between 1 and 100")
        if not 1 <= threshold <= 100:
            raise SystemExit("threshold must be between 1 and 100")
        interval_hours = None
        if len(args.args) == 3:
            try:
                interval_hours = int(args.args[2])
            except ValueError:
                raise SystemExit("interval_hours must be a number between 1 and 168")
            if not 1 <= interval_hours <= 168:
                raise SystemExit("interval_hours must be between 1 and 168")
        set_traffic_alert_config(args.config, data, enabled, threshold, interval_hours)
    elif args.action == "repair":
        if args.args:
            raise SystemExit("repair does not take arguments")
        repair_menu_config(args.config, data)
    else:
        raise SystemExit(f"unknown action: {args.action}")


if __name__ == "__main__":
    main()
