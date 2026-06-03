from pathlib import Path

from vps_dueguard.client import WHMCSClient
from vps_dueguard.models import ProviderConfig, SessionConfig


def provider() -> ProviderConfig:
    return ProviderConfig.model_validate(
        {
            "name": "provider-a-test",
            "base_url": "https://provider-a.example",
            "username": "user@example.com",
            "password": "secret",
        }
    )


def test_cookie_path_is_per_provider(tmp_path: Path) -> None:
    client = WHMCSClient(provider(), session_config=SessionConfig(session_dir=tmp_path))

    assert client.cookie_path == tmp_path / "provider-a-test.json"
    client.close()


def test_save_and_load_cookies(tmp_path: Path) -> None:
    session = SessionConfig(session_dir=tmp_path)
    first = WHMCSClient(provider(), session_config=session)
    first.client.cookies.set("WHMCS", "abc", domain="provider-a.example")
    first._save_cookies()
    first.close()

    second = WHMCSClient(provider(), session_config=session)

    assert second.client.cookies.get("WHMCS") == "abc"
    second.close()
