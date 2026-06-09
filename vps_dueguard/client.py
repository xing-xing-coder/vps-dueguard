from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

import httpx

from .models import ProviderConfig, ServiceInfo, SessionConfig
from .parser import (
    ParsedService,
    detect_login_problem,
    extract_login_action,
    extract_login_payload,
    is_active_status,
    parse_service_detail,
    parse_services,
    extract_price_from_text,
)


class ProviderError(RuntimeError):
    pass


class WHMCSClient:
    def __init__(self, provider: ProviderConfig, timeout: float = 30.0, session_config: SessionConfig | None = None) -> None:
        self.provider = provider
        self.base_url = provider.base_url_text
        self.session_config = session_config or SessionConfig(enabled=False)
        self.cookie_path = self._cookie_path()
        self.client = httpx.Client(
            base_url=self.base_url,
            follow_redirects=True,
            timeout=timeout,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/125.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Cache-Control": "no-cache",
                "Pragma": "no-cache",
            },
        )
        self._load_cookies()

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> "WHMCSClient":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def login(self) -> None:
        if self._session_is_authenticated():
            return
        self.client.cookies.clear()

        response = self._get_login_page()

        payload = extract_login_payload(
            response.text,
            self.provider.username,
            self.provider.password.get_secret_value(),
        )
        action = self._english_url(extract_login_action(response.text, self.base_url))
        login_response = self.client.post(action, data=payload, headers={"Referer": str(response.url)})
        login_response.raise_for_status()

        problem = detect_login_problem(login_response.text, str(login_response.url))
        if problem:
            raise ProviderError(f"{self.provider.name}: {problem}")
        self._save_cookies()

    def _get_login_page(self) -> httpx.Response:
        errors: list[str] = []
        for path in ("index.php?rp=%2Flogin", "index.php?rp=/login", "login", "clientarea.php"):
            login_url = self._provider_url(path)
            try:
                response = self.client.get(login_url)
                if response.status_code == 404:
                    errors.append(f"{path}: 404")
                    continue
                response.raise_for_status()
                if "password" in response.text.lower():
                    return response
                errors.append(f"{path}: no login form")
            except httpx.HTTPError as exc:
                errors.append(f"{path}: {exc}")

        raise ProviderError(f"{self.provider.name}: Could not find a login page ({'; '.join(errors)}).")

    def list_services(self) -> list[ServiceInfo]:
        services_url = self._provider_url("clientarea.php?action=services")
        response = self.client.get(services_url)
        response.raise_for_status()

        problem = detect_login_problem(response.text, str(response.url))
        if problem:
            raise ProviderError(f"{self.provider.name}: {problem}")

        parsed_services = parse_services(response.text, self.base_url)
        if not parsed_services:
            parsed_services = self._fetch_rsthemes_services()
        results: list[ServiceInfo] = []
        for service in parsed_services:
            if not is_active_status(service.status):
                continue

            expires_at = service.expires_at
            traffic_usage = service.traffic_usage
            traffic_remaining = service.traffic_remaining
            price = service.price
            billing_cycle = service.billing_cycle

            if service.detail_url:
                try:
                    detail = self.client.get(self._english_url(service.detail_url))
                    detail.raise_for_status()
                    detail_expiry, detail_usage, detail_remaining, detail_price, detail_cycle = parse_service_detail(detail.text)
                    if detail_expiry != "unknown" and (expires_at == "unknown" or re.search(r"\d{4}[-/]\d{1,2}[-/]\d{1,2}", detail_expiry)):
                        expires_at = detail_expiry
                    if detail_usage != "unknown":
                        traffic_usage = detail_usage
                    if detail_remaining != "unknown":
                        traffic_remaining = detail_remaining
                    if price == "unknown" and detail_price != "unknown":
                        price = detail_price
                    if billing_cycle == "unknown" and detail_cycle != "unknown":
                        billing_cycle = detail_cycle
                except httpx.HTTPError:
                    pass

            results.append(
                ServiceInfo(
                    provider=self.provider.name,
                    service_name=service.service_name,
                    status=service.status,
                    expires_at=expires_at,
                    traffic_usage=traffic_usage,
                    traffic_remaining=traffic_remaining,
                    price=price,
                    billing_cycle=billing_cycle,
                    detail_url=service.detail_url,
                )
            )

        return results

    def _session_is_authenticated(self) -> bool:
        if not self.session_config.enabled:
            return False
        try:
            response = self.client.get(self._provider_url("clientarea.php?action=services"))
            response.raise_for_status()
        except httpx.HTTPError:
            return False
        if detect_login_problem(response.text, str(response.url)) is not None:
            return False
        if "password" in response.text.lower():
            return False
        return bool(parse_services(response.text, self.base_url) or self._fetch_rsthemes_services())

    def _fetch_rsthemes_services(self) -> list[ParsedService]:
        api_url = self._provider_url(
            "/modules/addons/RSThemes/src/Api/clientApi.php"
            "?controller=ClientData&method=getClientServices&draw=1&start=0&length=100"
        )
        try:
            response = self.client.get(api_url, headers={"Referer": self._provider_url("clientarea.php?action=services")})
            response.raise_for_status()
            payload = json.loads(response.text)
        except (httpx.HTTPError, json.JSONDecodeError):
            return []

        services: list[ParsedService] = []
        for item in payload.get("data") or []:
            service_id = item.get("id")
            product_name = " - ".join(
                part
                for part in (str(item.get("groupName") or "").strip(), str(item.get("productName") or "").strip())
                if part
            )
            domain = str(item.get("domain") or "").strip()
            service_name = f"{product_name} {domain}".strip() or "unknown"
            status = self._rsthemes_status(item)
            expires_at = str(item.get("normalisednextduedate") or item.get("nextduedate") or "unknown")
            detail_url = self._provider_url(f"clientarea.php?action=productdetails&id={service_id}") if service_id else ""
            services.append(
                ParsedService(
                    service_name=service_name,
                    status=status,
                    expires_at=expires_at,
                    traffic_usage="unknown",
                    traffic_remaining="unknown",
                    price="unknown",
                    billing_cycle="unknown",
                    detail_url=detail_url,
                )
            )
        return services

    def _rsthemes_status(self, item: dict[str, object]) -> str:
        status = item.get("domainstatus")
        if isinstance(status, dict):
            for key in ("statusText", "status", "rawStatus"):
                value = status.get(key)
                if value:
                    return str(value)
        return str(item.get("status") or "unknown")

    def _provider_url(self, path: str) -> str:
        return self._english_url(urljoin(self.base_url, path))

    def _english_url(self, url: str) -> str:
        parts = urlsplit(url)
        query = dict(parse_qsl(parts.query, keep_blank_values=True))
        query["language"] = "english"
        return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))

    def _cookie_path(self) -> Path | None:
        if not self.session_config.enabled:
            return None
        safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", self.provider.name)
        return self.session_config.session_dir / f"{safe_name}.json"

    def _load_cookies(self) -> None:
        if self.cookie_path is None or not self.cookie_path.exists():
            return
        try:
            with self.cookie_path.open("r", encoding="utf-8") as handle:
                cookies = json.load(handle)
        except (OSError, json.JSONDecodeError):
            return
        if isinstance(cookies, dict):
            self.client.cookies.update({str(key): str(value) for key, value in cookies.items()})

    def _save_cookies(self) -> None:
        if self.cookie_path is None:
            return
        self.cookie_path.parent.mkdir(parents=True, exist_ok=True)
        cookies = {cookie.name: cookie.value for cookie in self.client.cookies.jar}
        with self.cookie_path.open("w", encoding="utf-8") as handle:
            json.dump(cookies, handle, ensure_ascii=False, indent=2)


def fetch_provider_services(provider: ProviderConfig, session_config: SessionConfig | None = None) -> list[ServiceInfo]:
    with WHMCSClient(provider, session_config=session_config) as client:
        client.login()
        return client.list_services()
