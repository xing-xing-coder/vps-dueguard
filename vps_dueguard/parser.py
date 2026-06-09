from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag


SIZE_RE = r"[0-9.]+\s*(?:TiB|GiB|MiB|TB|GB|MB|KB|T|G|M|K)"

CHALLENGE_PATTERNS = (
    "captcha",
    "recaptcha",
    "hcaptcha",
    "two-factor",
    "two factor",
    "2fa",
    "verification code",
)

LOGIN_FAILURE_PATTERNS = (
    "login details incorrect",
    "invalid login",
    "incorrect email",
    "password is incorrect",
)

EXPIRY_LABELS = (
    "next due date",
    "expiry date",
    "expiration date",
    "due date",
)

PRICE_LABELS = (
    "recurring amount",
    "amount",
    "price",
    "cost",
    "billing amount",
    "next due",
)

TRAFFIC_LABELS = ("traffic", "bandwidth", "data")


BILLING_CYCLE_LABELS = (
    "billing cycle",
    "billing",
    "cycle",
)

BILLING_CYCLE_MAP = {
    "monthly": "Monthly",
    "month": "Monthly",
    "mo": "Monthly",
    "/mo": "Monthly",
    "/month": "Monthly",
    "quarterly": "Quarterly",
    "quarter": "Quarterly",
    "semi-annually": "Semi-Annually",
    "semiannually": "Semi-Annually",
    "semi-annual": "Semi-Annually",
    "half-yearly": "Semi-Annually",
    "annually": "Annually",
    "annual": "Annually",
    "yearly": "Annually",
    "year": "Annually",
    "/yr": "Annually",
    "/year": "Annually",
    "free": "Free",
    "one time": "One-Time",
    "one-time": "One-Time",
    "triennially": "Triennially",
    "triennial": "Triennially",
    "biennially": "Biennially",
    "biennial": "Biennially",
}


@dataclass(frozen=True)
class ParsedService:
    service_name: str
    status: str
    expires_at: str
    traffic_usage: str
    traffic_remaining: str
    price: str
    billing_cycle: str
    detail_url: str


def soup_from_html(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


def extract_login_payload(html: str, username: str, password: str) -> dict[str, str]:
    soup = soup_from_html(html)
    form = _find_login_form(soup)
    payload: dict[str, str] = {}

    for field in form.find_all("input"):
        if not isinstance(field, Tag):
            continue
        name = field.get("name")
        if name:
            payload[str(name)] = str(field.get("value", ""))

    payload[_find_field_name(form, ("email", "username", "user", "loginemail"))] = username
    payload[_find_field_name(form, ("password", "passwd"))] = password

    remember = _find_field_name(form, ("rememberme", "remember", "remember_me"), required=False)
    if remember:
        payload[remember] = "on"

    return payload


def extract_login_action(html: str, base_url: str) -> str:
    soup = soup_from_html(html)
    form = _find_login_form(soup)
    return urljoin(base_url, str(form.get("action") or "login"))


def detect_login_problem(html: str, final_url: str | None = None) -> str | None:
    soup = soup_from_html(html)
    text = _clean_text(soup).lower()
    password_field = soup.find("input", {"type": "password"})
    is_login_url = bool(final_url and "login" in final_url.lower())

    if (password_field or is_login_url) and any(pattern in text for pattern in CHALLENGE_PATTERNS):
        return "Login requires captcha, email verification, or 2FA."

    if any(pattern in text for pattern in LOGIN_FAILURE_PATTERNS):
        return "Login failed. Check the configured username and password."

    if password_field and is_login_url:
        return "Login did not leave the login page. Check credentials or site-specific login requirements."

    return None


def parse_services(html: str, base_url: str) -> list[ParsedService]:
    soup = soup_from_html(html)
    services = _parse_services_from_table(soup, base_url)
    return services or _parse_services_from_cards(soup, base_url)


def parse_service_detail(html: str) -> tuple[str, str, str, str, str]:
    soup = soup_from_html(html)
    expires_at = find_labeled_value(soup, EXPIRY_LABELS) or "unknown"
    traffic_usage, traffic_remaining = find_traffic_usage_and_remaining(soup)
    price = extract_price_from_detail(soup)
    billing_cycle = extract_billing_cycle_from_detail(soup)
    return _date_or_unknown(expires_at), traffic_usage, traffic_remaining, price, billing_cycle


def find_labeled_value(soup: BeautifulSoup, labels: tuple[str, ...]) -> str | None:
    for row in soup.find_all("tr"):
        cells = [_clean_text(cell) for cell in row.find_all(["th", "td"])]
        if len(cells) >= 2 and _matches_any(cells[0], labels):
            return cells[1]

    for definition in soup.find_all("dt"):
        if not _matches_any(_clean_text(definition), labels):
            continue
        sibling = definition.find_next_sibling("dd")
        if sibling:
            return _clean_text(sibling)

    for element in soup.find_all(["div", "span", "p", "li"]):
        value = _split_label_value(_clean_text(element), labels)
        if value:
            return value

    return None


def find_traffic_remaining(soup: BeautifulSoup) -> str | None:
    remaining = find_traffic_usage_and_remaining(soup)[1]
    return None if remaining == "unknown" else remaining


def find_traffic_usage_and_remaining(soup: BeautifulSoup) -> tuple[str, str]:
    for row in soup.find_all("tr"):
        cells = [_clean_text(cell) for cell in row.find_all(["th", "td"])]
        if len(cells) >= 2 and _matches_any(cells[0], TRAFFIC_LABELS):
            return _clean_traffic_values(" ".join(cells))

    for progress in soup.find_all(attrs={"aria-valuenow": True}):
        container = progress.parent if isinstance(progress.parent, Tag) else progress
        usage, remaining = _extract_traffic_values(_clean_text(container))
        if remaining != "unknown":
            return usage, remaining

    return _extract_traffic_values(_clean_text(soup))


def extract_price_from_detail(soup: BeautifulSoup) -> str:
    for label in PRICE_LABELS:
        value = find_labeled_value(soup, (label,))
        if value and _looks_like_money(value):
            cleaned = extract_price_from_text(value)
            if cleaned != "unknown":
                return cleaned
            return _clean_spaces(value)
    return "unknown"


def extract_price_from_text(text: str) -> str:
    match = re.search(r"[$€£¥]\s*[0-9.,]+(?:\s*(?:USD|EUR|GBP|CNY|RMB|AUD|CAD))?", text, re.I)
    if match:
        return _clean_spaces(match.group(0))
    match = re.search(r"(?:USD|EUR|GBP|CNY|RMB|AUD|CAD)\s*[0-9.,]+", text, re.I)
    if match:
        return _clean_spaces(match.group(0))
    return "unknown"


def extract_billing_cycle(text: str) -> str:
    if not text or text == "unknown":
        return "unknown"
    cleaned = text.strip().lower()
    for pattern, normalized in BILLING_CYCLE_MAP.items():
        if pattern in cleaned:
            return normalized
    return _clean_spaces(text)


def extract_billing_cycle_from_detail(soup: BeautifulSoup) -> str:
    for label in BILLING_CYCLE_LABELS:
        value = find_labeled_value(soup, (label,))
        if value:
            cycle = extract_billing_cycle(value)
            if cycle != "unknown":
                return cycle
    return "unknown"


def parse_size_to_mb(value: str) -> float | None:
    return _parse_size_to_mb(value)


def is_active_status(status: str) -> bool:
    return status.strip().lower() == "active"


def _find_login_form(soup: BeautifulSoup) -> Tag:
    forms = [form for form in soup.find_all("form") if isinstance(form, Tag)]
    for form in forms:
        if form.find("input", {"type": "password"}) is not None:
            return form
    if forms:
        return forms[0]
    raise ValueError("No login form found on login page.")


def _find_field_name(form: Tag, candidates: tuple[str, ...], required: bool = True) -> str | None:
    for field in form.find_all("input"):
        if not isinstance(field, Tag):
            continue
        name = str(field.get("name") or "")
        field_id = str(field.get("id") or "")
        field_type = str(field.get("type") or "")
        haystack = f"{name} {field_id} {field_type}".lower()
        if any(candidate in haystack for candidate in candidates):
            return name
    if required:
        raise ValueError(f"Could not find login field matching: {', '.join(candidates)}")
    return None


def _parse_services_from_table(soup: BeautifulSoup, base_url: str) -> list[ParsedService]:
    services: list[ParsedService] = []
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if len(rows) < 2:
            continue

        headers = [_clean_text(cell).lower() for cell in rows[0].find_all(["th", "td"])]
        if not headers:
            continue

        for row in rows[1:]:
            cells = [_clean_text(cell) for cell in row.find_all(["td", "th"])]
            if not cells:
                continue

            traffic_usage, traffic_remaining = _clean_traffic_values(
                _value_by_header(headers, cells, ("traffic", "bandwidth", "data")) or "unknown"
            )
            raw_price = _value_by_header(headers, cells, ("amount", "price", "cost", "billing", "recurring")) or "unknown"
            price = extract_price_from_text(raw_price) if raw_price != "unknown" else "unknown"
            raw_cycle = _value_by_header(headers, cells, ("billing cycle", "cycle", "billing")) or "unknown"
            billing_cycle = extract_billing_cycle(raw_cycle) if raw_cycle != "unknown" else "unknown"
            if billing_cycle == "unknown" and raw_price != "unknown":
                billing_cycle = extract_billing_cycle(raw_price)
            services.append(
                ParsedService(
                    service_name=_service_name_from_cells(cells),
                    status=_value_by_header(headers, cells, ("status",)) or _guess_status(cells),
                    expires_at=_first_date_or_text(
                        _value_by_header(headers, cells, ("next due date", "expiry", "due date")) or "unknown"
                    ),
                    traffic_usage=traffic_usage,
                    traffic_remaining=traffic_remaining,
                    price=price,
                    billing_cycle=billing_cycle,
                    detail_url=_detail_url_from_row(row, base_url),
                )
            )

    return _dedupe_services(services)


def _parse_services_from_cards(soup: BeautifulSoup, base_url: str) -> list[ParsedService]:
    services: list[ParsedService] = []
    for link in soup.find_all("a", href=True):
        href = str(link["href"])
        if "clientarea.php?action=productdetails" not in href.lower():
            continue
        container = _service_container(link)
        text = _clean_text(container)
        services.append(
            ParsedService(
                service_name=_clean_text(link) or _first_nonempty_line(text),
                status=_guess_status([text]),
                expires_at=_extract_date(text) or "unknown",
                traffic_usage="unknown",
                traffic_remaining="unknown",
                price="unknown",
                billing_cycle="unknown",
                detail_url=urljoin(base_url, href),
            )
        )
    return _dedupe_services(services)


def _service_name_from_cells(cells: list[str]) -> str:
    for text in cells:
        cleaned = re.sub(r"\blagomshowservice\b", "", text, flags=re.I).strip()
        if cleaned and not _looks_like_status(cleaned) and not _extract_date(cleaned) and not _looks_like_money(cleaned):
            return cleaned
    return "unknown"


def _value_by_header(headers: list[str], values: list[str], needles: tuple[str, ...]) -> str | None:
    for index, header in enumerate(headers):
        if index < len(values) and any(needle in header for needle in needles):
            return values[index]
    return None


def _guess_status(values: list[str]) -> str:
    text = " ".join(values).lower()
    for status in ("active", "suspended", "terminated", "cancelled", "canceled", "pending"):
        if status in text:
            return "Cancelled" if status == "canceled" else status.title()
    return "unknown"


def _looks_like_status(text: str) -> bool:
    return _guess_status([text]) != "unknown"


def _looks_like_money(text: str) -> bool:
    return bool(re.search(r"(?:[$]\s*\d)|(?:\b(?:usd|cny|rmb|eur)\b)", text, re.I))


def _detail_url_from_row(row: Tag, base_url: str) -> str:
    for attr in ("data-url", "data-href"):
        value = row.get(attr)
        if value:
            return urljoin(base_url, str(value))

    onclick = str(row.get("onclick") or "")
    match = re.search(r"['\"]([^'\"]*clientarea\.php\?action=productdetails[^'\"]*)['\"]", onclick, re.I)
    if match:
        return urljoin(base_url, match.group(1))

    for link in row.find_all("a", href=True):
        href = str(link["href"])
        if "clientarea.php?action=productdetails" in href.lower():
            return urljoin(base_url, href)

    return ""


def _service_container(tag: Tag) -> Tag:
    for parent in tag.parents:
        if isinstance(parent, Tag) and parent.name in {"tr", "li", "div", "article"} and len(_clean_text(parent)) > 20:
            return parent
    return tag


def _dedupe_services(services: list[ParsedService]) -> list[ParsedService]:
    seen: set[str] = set()
    deduped: list[ParsedService] = []
    for service in services:
        key = service.detail_url or f"{service.service_name}|{service.expires_at}|{service.status}"
        if key not in seen:
            seen.add(key)
            deduped.append(service)
    return deduped


def _extract_traffic_values(text: str) -> tuple[str, str]:
    labeled_ratio = re.search(
        rf"(?:bandwidth|traffic|data)\D{{0,40}}({SIZE_RE})\s*/\s*({SIZE_RE})",
        text,
        re.I,
    )
    if labeled_ratio:
        return _format_usage_and_remaining(labeled_ratio.group(1), labeled_ratio.group(2))

    ratio = re.search(rf"({SIZE_RE})\s*/\s*({SIZE_RE})", text, re.I)
    if ratio:
        return _format_usage_and_remaining(ratio.group(1), ratio.group(2))

    remaining = re.search(
        rf"(?:remaining|left|available)\s+(?:traffic|bandwidth|data)\s*[:：]?\s*({SIZE_RE})",
        text,
        re.I,
    )
    if remaining:
        return "unknown", _clean_spaces(remaining.group(1))

    remaining = re.search(
        rf"(?:traffic|bandwidth|data)\s+(?:remaining|left|available)\s*[:：]?\s*({SIZE_RE})",
        text,
        re.I,
    )
    if remaining:
        return "unknown", _clean_spaces(remaining.group(1))

    return "unknown", "unknown"


def _clean_traffic_values(text: str) -> tuple[str, str]:
    if not text:
        return "unknown", "unknown"
    usage, remaining = _extract_traffic_values(text)
    if usage != "unknown" or remaining != "unknown":
        return usage, remaining
    return "unknown", _clean_spaces(re.sub(r"\b\d+(?:\.\d+)?%\b", "", text)) or "unknown"


def _format_usage_and_remaining(used_text: str, total_text: str) -> tuple[str, str]:
    usage = _clean_spaces(f"{used_text} / {total_text}")
    used = _parse_size_to_mb(used_text)
    total = _parse_size_to_mb(total_text)
    if used is None or total is None or total < used:
        return usage, "unknown"
    return usage, _format_size_from_mb(total - used)


def _parse_size_to_mb(value: str) -> float | None:
    match = re.search(r"([0-9.]+)\s*(TiB|GiB|MiB|TB|GB|MB|KB|T|G|M|K)", value, re.I)
    if not match:
        return None

    factors = {
        "k": 1 / 1024,
        "kb": 1 / 1024,
        "m": 1,
        "mb": 1,
        "mib": 1,
        "g": 1024,
        "gb": 1024,
        "gib": 1024,
        "t": 1024 * 1024,
        "tb": 1024 * 1024,
        "tib": 1024 * 1024,
    }
    return float(match.group(1)) * factors[match.group(2).lower()]


def _format_size_from_mb(value: float) -> str:
    if value >= 1024 * 1024:
        return f"{value / 1024 / 1024:.2f} TB"
    if value >= 1024:
        return f"{value / 1024:.2f} GB"
    return f"{value:.0f} MB"


def _first_date_or_text(text: str) -> str:
    return _extract_date(text) or _clean_spaces(text) or "unknown"


def _date_or_unknown(text: str) -> str:
    return _extract_date(text) or "unknown"


def _extract_date(text: str) -> str | None:
    for pattern in (
        r"\b\d{4}[-/]\d{1,2}[-/]\d{1,2}\b",
        r"\b[A-Za-z]+,\s+[A-Za-z]+\s+\d{1,2}(?:st|nd|rd|th)?,\s+\d{4}\b",
        r"\b\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4}\b",
    ):
        match = re.search(pattern, text)
        if match:
            return match.group(0)
    return None


def _split_label_value(text: str, labels: tuple[str, ...]) -> str | None:
    lowered = text.lower()
    for label in labels:
        index = lowered.find(label.lower())
        if index != -1:
            return text[index + len(label) :].strip(" :：-") or None
    return None


def _matches_any(text: str, needles: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(needle.lower() in lowered for needle in needles)


def _clean_text(tag_or_text: Tag | str) -> str:
    if isinstance(tag_or_text, Tag):
        text = tag_or_text.get_text(" ", strip=True)
    else:
        text = tag_or_text
    return _clean_spaces(text)


def _clean_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _first_nonempty_line(text: str) -> str:
    for line in text.splitlines():
        if line.strip():
            return line.strip()
    return text
