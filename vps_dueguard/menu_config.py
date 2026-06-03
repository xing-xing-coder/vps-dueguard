from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

import yaml

DEFAULT_RENEWAL_DAYS = [21, 14, 7, 3]


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


def write_menu_config(path: Path, providers_yaml: str, bot_token: str, chat_id: str, renewal_days: str) -> None:
    days = normalize_renewal_days(renewal_days)
    cleaned_token = clean_scalar(bot_token, "bot_token")
    cleaned_chat_id = clean_scalar(chat_id, "chat_id")
    output = {
        "providers": providers_from_yaml(providers_yaml),
        "notifications": {
            "renewal_days": days,
            "daily_report": True,
            "state_file": ".vps_dueguard_state.json",
        },
        "sessions": {"enabled": True, "session_dir": ".vps_sessions"},
    }
    if cleaned_token and cleaned_chat_id:
        output["telegram"] = {"bot_token": cleaned_token, "chat_id": cleaned_chat_id}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(output, allow_unicode=True, sort_keys=False), "utf-8")


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
        else:
            raise SystemExit(f"unknown get key: {key}")
    elif args.action == "write":
        if len(args.args) != 4:
            raise SystemExit("write requires providers_yaml, bot_token, chat_id, renewal_days")
        write_menu_config(args.config, args.args[0], args.args[1], args.args[2], args.args[3])
    else:
        raise SystemExit(f"unknown action: {args.action}")


if __name__ == "__main__":
    main()
