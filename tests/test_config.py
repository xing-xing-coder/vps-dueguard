from pathlib import Path

import pytest
from pydantic import ValidationError

from vps_dueguard.models import AppConfig, load_config


def test_url_is_normalized_with_trailing_slash() -> None:
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

    assert config.providers[0].name == "provider-a"
    assert config.providers[0].base_url_text == "https://provider-a.example/"


def test_missing_password_fails() -> None:
    with pytest.raises(ValidationError):
        AppConfig.model_validate(
            {
                "providers": [
                    {
                        "name": "provider-a",
                        "base_url": "https://provider-a.example",
                        "username": "user@example.com",
                    }
                ]
            }
        )


def test_provider_subset() -> None:
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
                    "name": "wap",
                    "base_url": "https://provider-b.example",
                    "username": "user@example.com",
                    "password": "secret",
                },
            ]
        }
    )

    assert [provider.name for provider in config.provider_subset("provider-a")] == ["provider-a"]
    with pytest.raises(ValueError):
        config.provider_subset("missing")


def test_load_config(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        """
providers:
  - name: provider-a
    base_url: https://provider-a.example/
    username: user@example.com
    password: secret
""",
        encoding="utf-8",
    )

    assert load_config(config_file).providers[0].name == "provider-a"


def test_load_config_allows_empty_providers_for_menu_setup(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        """
providers: []
telegram:
  bot_token: token
  chat_id: "123"
""",
        encoding="utf-8",
    )

    config = load_config(config_file)

    assert config.providers == []
    assert config.telegram is not None
    assert config.telegram.chat_id == "123"


def test_load_config_reports_yaml_reader_errors(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text("providers:\n  - name: bad\btoken\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid YAML config file"):
        load_config(config_file)


def test_notification_defaults() -> None:
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

    assert config.telegram is None
    assert config.notifications.renewal_days == [21, 14, 7, 3]
    assert config.notifications.daily_report is True
    assert config.notifications.traffic_alerts.enabled is True
    assert config.notifications.traffic_alerts.threshold == 80
    assert str(config.notifications.state_file) == ".vps_dueguard_state.json"
    assert config.sessions.enabled is True
    assert str(config.sessions.session_dir) == ".vps_sessions"


def test_telegram_config() -> None:
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
            "notifications": {"renewal_days": [7, 14, 7]},
        }
    )

    assert config.telegram is not None
    assert config.telegram.chat_id == "123"
    assert config.notifications.renewal_days == [14, 7]


def test_session_config() -> None:
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
            "sessions": {"enabled": False, "session_dir": "sessions"},
        }
    )

    assert config.sessions.enabled is False
    assert str(config.sessions.session_dir) == "sessions"


def test_traffic_alert_config() -> None:
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
            "notifications": {
                "traffic_alerts": {
                    "enabled": False,
                    "threshold": 90,
                }
            },
        }
    )

    assert config.notifications.traffic_alerts.enabled is False
    assert config.notifications.traffic_alerts.threshold == 90


def test_traffic_alert_config_invalid_threshold() -> None:
    with pytest.raises(ValidationError):
        AppConfig.model_validate(
            {
                "providers": [
                    {
                        "name": "provider-a",
                        "base_url": "https://provider-a.example",
                        "username": "user@example.com",
                        "password": "secret",
                    }
                ],
                "notifications": {
                    "traffic_alerts": {
                        "threshold": 150,
                    }
                },
            }
        )


def test_service_info_price_field() -> None:
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

    from vps_dueguard.models import ServiceInfo

    svc = ServiceInfo(
        provider="provider-a",
        service_name="Tokyo VPS",
        detail_url="https://example.com",
        price="$3.50 USD",
    )

    assert svc.price == "$3.50 USD"

    svc_default = ServiceInfo(
        provider="provider-a",
        service_name="Tokyo VPS",
        detail_url="https://example.com",
    )

    assert svc_default.price == "unknown"
