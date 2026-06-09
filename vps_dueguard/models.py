from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, HttpUrl, SecretStr, field_validator


class ProviderConfig(BaseModel):
    name: str = Field(min_length=1)
    base_url: HttpUrl
    username: str = Field(min_length=1)
    password: SecretStr = Field(min_length=1)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return value.strip().lower()

    @property
    def base_url_text(self) -> str:
        return str(self.base_url).rstrip("/") + "/"


class AppConfig(BaseModel):
    providers: list[ProviderConfig] = Field(default_factory=list)
    telegram: "TelegramConfig | None" = None
    notifications: "NotificationConfig" = Field(default_factory=lambda: NotificationConfig())
    sessions: "SessionConfig" = Field(default_factory=lambda: SessionConfig())

    def provider_subset(self, provider_name: str | None) -> list[ProviderConfig]:
        if provider_name is None:
            return self.providers

        normalized = provider_name.strip().lower()
        matches = [provider for provider in self.providers if provider.name == normalized]
        if not matches:
            known = ", ".join(provider.name for provider in self.providers)
            raise ValueError(f"Unknown provider '{provider_name}'. Known providers: {known}")
        return matches


class ServiceInfo(BaseModel):
    provider: str
    service_name: str
    status: str = "unknown"
    expires_at: str = "unknown"
    traffic_usage: str = "unknown"
    traffic_remaining: str = "unknown"
    price: str = "unknown"
    billing_cycle: str = "unknown"
    detail_url: str


class TelegramConfig(BaseModel):
    bot_token: SecretStr = Field(min_length=1)
    chat_id: str = Field(min_length=1)


class NotificationConfig(BaseModel):
    renewal_days: list[int] = Field(default_factory=lambda: [21, 14, 7, 3])
    daily_report: bool = True
    traffic_alerts: "TrafficAlertConfig" = Field(default_factory=lambda: TrafficAlertConfig())
    state_file: Path = Path(".vps_dueguard_state.json")

    @field_validator("renewal_days")
    @classmethod
    def normalize_renewal_days(cls, value: list[int]) -> list[int]:
        days = sorted(set(value), reverse=True)
        if any(day < 0 for day in days):
            raise ValueError("renewal_days must be non-negative")
        return days


class TrafficAlertConfig(BaseModel):
    enabled: bool = True
    threshold: int = 80
    check_interval_hours: int = 6

    @field_validator("threshold")
    @classmethod
    def validate_threshold(cls, value: int) -> int:
        if not 1 <= value <= 100:
            raise ValueError("threshold must be between 1 and 100")
        return value

    @field_validator("check_interval_hours")
    @classmethod
    def validate_interval(cls, value: int) -> int:
        if not 1 <= value <= 168:
            raise ValueError("check_interval_hours must be between 1 and 168")
        return value


class SessionConfig(BaseModel):
    enabled: bool = True
    session_dir: Path = Path(".vps_sessions")


def load_config(path: Path) -> AppConfig:
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    try:
        with path.open("r", encoding="utf-8") as handle:
            raw: Any = yaml.safe_load(handle) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid YAML config file {path}: {exc}") from exc

    return AppConfig.model_validate(raw)
