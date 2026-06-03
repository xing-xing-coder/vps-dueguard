from pathlib import Path

import pytest

from vps_dueguard.menu_config import (
    add_provider_config,
    current_providers,
    current_renewal_days,
    current_telegram,
    dump_providers_yaml,
    load_menu_config,
    normalize_renewal_days,
    repair_menu_config,
    set_renewal_days_config,
    set_telegram_config,
    write_menu_config,
)
from vps_dueguard.models import load_config


def test_write_menu_config_round_trips_providers_and_telegram(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    providers_yaml = """  - name: provider-a
    base_url: https://provider-a.example/
    username: user@example.com
    password: secret
"""

    write_menu_config(config_file, providers_yaml, "token", "123", "21,14,7,3")
    data = load_menu_config(config_file)

    assert current_providers(data) == [
        {
            "name": "provider-a",
            "base_url": "https://provider-a.example/",
            "username": "user@example.com",
            "password": "secret",
        }
    ]
    assert current_telegram(data) == {"bot_token": "token", "chat_id": "123"}
    assert data["notifications"]["renewal_days"] == [21, 14, 7, 3]
    assert current_renewal_days(data) == [21, 14, 7, 3]


def test_write_menu_config_omits_empty_telegram(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    providers_yaml = """  - name: provider-a
    base_url: https://provider-a.example/
    username: user@example.com
    password: secret
"""

    write_menu_config(config_file, providers_yaml, "", "", "21,14,7,3")
    data = load_menu_config(config_file)
    app_config = load_config(config_file)

    assert "telegram" not in data
    assert app_config.telegram is None
    assert len(app_config.providers) == 1


def test_write_menu_config_with_no_providers_still_loads_for_telegram_only(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"

    write_menu_config(config_file, "", "token", "123", "21,14,7,3")
    app_config = load_config(config_file)

    assert app_config.providers == []
    assert app_config.telegram is not None
    assert app_config.telegram.chat_id == "123"


def test_write_menu_config_repairs_polluted_telegram_values(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"

    write_menu_config(
        config_file,
        "",
        '  bot_token: \\"  bot_token: \\\\\\"real-token',
        '  chat_id: \\"  chat_id: \\\\\\"123456',
        "30",
    )
    data = load_menu_config(config_file)

    assert current_telegram(data) == {"bot_token": "real-token", "chat_id": "123456"}
    assert "bot_token:" not in data["telegram"]["bot_token"]
    assert data["notifications"]["renewal_days"] == [30]


def test_dump_providers_yaml_can_be_written_back(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    providers_yaml = """  - name: wap
    base_url: https://provider-b.example/
    username: user@example.com
    password: secret
"""

    write_menu_config(config_file, providers_yaml, "token", "123", "21,14")
    data = load_menu_config(config_file)
    write_menu_config(config_file, dump_providers_yaml(current_providers(data)), "token2", "456", "7,3")
    data = load_menu_config(config_file)

    assert len(current_providers(data)) == 1
    assert current_providers(data)[0]["name"] == "wap"
    assert current_telegram(data) == {"bot_token": "token2", "chat_id": "456"}
    assert data["notifications"]["renewal_days"] == [7, 3]


def test_add_provider_config_preserves_existing_config(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    providers_yaml = """  - name: provider-a
    base_url: https://provider-a.example/
    username: user-a@example.com
    password: secret-a
"""

    write_menu_config(config_file, providers_yaml, "token", "123", "21,14")
    data = load_menu_config(config_file)
    add_provider_config(
        config_file,
        data,
        "provider-b",
        "https://provider-b.example/",
        "user-b@example.com",
        "secret-b",
    )
    data = load_menu_config(config_file)

    assert current_providers(data) == [
        {
            "name": "provider-a",
            "base_url": "https://provider-a.example/",
            "username": "user-a@example.com",
            "password": "secret-a",
        },
        {
            "name": "provider-b",
            "base_url": "https://provider-b.example/",
            "username": "user-b@example.com",
            "password": "secret-b",
        },
    ]
    assert current_telegram(data) == {"bot_token": "token", "chat_id": "123"}
    assert current_renewal_days(data) == [21, 14]


def test_set_telegram_config_preserves_existing_providers(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    providers_yaml = """  - name: provider-a
    base_url: https://provider-a.example/
    username: user-a@example.com
    password: secret-a
"""

    write_menu_config(config_file, providers_yaml, "old-token", "111", "21,14")
    data = load_menu_config(config_file)
    set_telegram_config(config_file, data, "new-token", "222", "30,7")
    data = load_menu_config(config_file)

    assert len(current_providers(data)) == 1
    assert current_providers(data)[0]["name"] == "provider-a"
    assert current_telegram(data) == {"bot_token": "new-token", "chat_id": "222"}
    assert current_renewal_days(data) == [30, 7]


def test_set_renewal_days_config_preserves_existing_config(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    providers_yaml = """  - name: provider-a
    base_url: https://provider-a.example/
    username: user-a@example.com
    password: secret-a
"""

    write_menu_config(config_file, providers_yaml, "token", "123", "21,14")
    data = load_menu_config(config_file)
    set_renewal_days_config(config_file, data, "30,7,3")
    data = load_menu_config(config_file)

    assert len(current_providers(data)) == 1
    assert current_providers(data)[0]["name"] == "provider-a"
    assert current_telegram(data) == {"bot_token": "token", "chat_id": "123"}
    assert current_renewal_days(data) == [30, 7, 3]


def test_repair_menu_config_refuses_invalid_yaml(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    original = "providers:\n  - name: provider-a\n    base_url: [broken\n"
    config_file.write_text(original, "utf-8")

    with pytest.raises(SystemExit):
        repair_menu_config(config_file, {})

    assert config_file.read_text("utf-8") == original


def test_normalize_renewal_days_accepts_only_comma_separated_values() -> None:
    assert normalize_renewal_days("21,14,7,3") == [21, 14, 7, 3]
    assert normalize_renewal_days("") == [21, 14, 7, 3]

    with pytest.raises(ValueError):
        normalize_renewal_days("21 14 7")

    with pytest.raises(ValueError):
        normalize_renewal_days("[21,14,7]")
