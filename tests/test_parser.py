from vps_dueguard.parser import (
    detect_login_problem,
    extract_billing_cycle,
    extract_login_action,
    extract_login_payload,
    extract_price_from_detail,
    extract_price_from_text,
    parse_service_detail,
    parse_services,
    parse_size_to_mb,
    soup_from_html,
    find_traffic_remaining,
)


LOGIN_HTML = """
<form method="post" action="/dologin.php">
  <input type="hidden" name="token" value="abc123">
  <input type="email" name="username">
  <input type="password" name="password">
  <input type="checkbox" name="rememberme" value="1">
</form>
"""


def test_extract_login_payload() -> None:
    payload = extract_login_payload(LOGIN_HTML, "user@example.com", "secret")

    assert payload["token"] == "abc123"
    assert payload["username"] == "user@example.com"
    assert payload["password"] == "secret"
    assert payload["rememberme"] == "on"


def test_extract_login_action() -> None:
    assert extract_login_action(LOGIN_HTML, "https://provider-a.example/") == "https://provider-a.example/dologin.php"


def test_detect_login_problems() -> None:
    assert "captcha" in detect_login_problem("<form><input type='password'></form><p>reCAPTCHA required</p>", "https://example.com/login").lower()
    assert "Login failed" in detect_login_problem("<p>Login Details Incorrect</p>", None)


def test_parse_services_from_table() -> None:
    html = """
    <table>
      <tr><th>Product/Service</th><th>Status</th><th>Next Due Date</th><th></th></tr>
      <tr>
        <td>Tokyo VPS 1G</td>
        <td>Active</td>
        <td>2026-12-31</td>
        <td><a href="clientarea.php?action=productdetails&id=42">Manage</a></td>
      </tr>
    </table>
    """

    services = parse_services(html, "https://provider-a.example/")

    assert len(services) == 1
    assert services[0].service_name == "Tokyo VPS 1G"
    assert services[0].status == "Active"
    assert services[0].expires_at == "2026-12-31"
    assert services[0].traffic_usage == "unknown"
    assert services[0].traffic_remaining == "unknown"
    assert services[0].detail_url == "https://provider-a.example/clientarea.php?action=productdetails&id=42"


def test_parse_service_detail() -> None:
    html = """
    <table>
      <tr><th>Next Due Date</th><td>2026-08-01</td></tr>
      <tr><th>Traffic Remaining</th><td>512 GB</td></tr>
    </table>
    """

    assert parse_service_detail(html) == ("2026-08-01", "unknown", "512 GB", "unknown", "unknown")


def test_find_traffic_from_text_and_ratio() -> None:
    assert find_traffic_remaining(soup_from_html("<p>Traffic Remaining: 1.5 TB</p>")) == "1.5 TB"
    assert find_traffic_remaining(soup_from_html("<p>Bandwidth 20 GB / 1 TB</p>")) == "1004.00 GB"
    assert find_traffic_remaining(soup_from_html("<p>Bandwidth Usage 2389 M / 102400 M</p>")) == "97.67 GB"


def test_parse_services_keeps_used_total_and_remaining() -> None:
    html = """
    <table>
      <tr><th>Product/Service</th><th>Next Due Date</th><th>Traffic Usage</th><th>Status</th><th></th></tr>
      <tr data-url="clientarea.php?action=productdetails&id=42">
        <td>Tokyo VPS</td>
        <td>2026-12-31</td>
        <td>20 GB / 1 TB 1.95%</td>
        <td>Active</td>
        <td><a href="clientarea.php?action=productdetails&id=42">Manage</a></td>
      </tr>
    </table>
    """

    service = parse_services(html, "https://example.com/")[0]

    assert service.traffic_usage == "20 GB / 1 TB"
    assert service.traffic_remaining == "1004.00 GB"


def test_parse_service_detail_unknown_traffic() -> None:
    assert parse_service_detail("<p>Next Due Date: 2026-08-01</p>") == ("2026-08-01", "unknown", "unknown", "unknown", "unknown")


def test_parse_service_detail_with_price() -> None:
    html = """
    <table>
      <tr><th>Next Due Date</th><td>2026-08-01</td></tr>
      <tr><th>Recurring Amount</th><td>$3.50 USD</td></tr>
      <tr><th>Traffic</th><td>20 GB / 1 TB</td></tr>
    </table>
    """
    expiry, usage, remaining, price, cycle = parse_service_detail(html)

    assert expiry == "2026-08-01"
    assert price == "$3.50 USD"


def test_parse_services_from_table_with_price_column() -> None:
    html = """
    <table>
      <tr><th>Product/Service</th><th>Status</th><th>Next Due Date</th><th>Amount</th><th></th></tr>
      <tr>
        <td>Tokyo VPS 1G</td>
        <td>Active</td>
        <td>2026-12-31</td>
        <td>$5.00 USD</td>
        <td><a href="clientarea.php?action=productdetails&id=42">Manage</a></td>
      </tr>
    </table>
    """

    services = parse_services(html, "https://provider-a.example/")

    assert len(services) == 1
    assert services[0].price == "$5.00 USD"


def test_parse_services_price_cleans_extra_text() -> None:
    html = """
    <table>
      <tr><th>Product/Service</th><th>Status</th><th>Next Due Date</th><th>Amount</th><th></th></tr>
      <tr>
        <td>Tokyo VPS 1G</td>
        <td>Active</td>
        <td>2026-12-31</td>
        <td>$3.50 USD Monthly</td>
        <td><a href="clientarea.php?action=productdetails&id=42">Manage</a></td>
      </tr>
    </table>
    """

    services = parse_services(html, "https://provider-a.example/")

    assert len(services) == 1
    assert services[0].price == "$3.50 USD"
    assert "Monthly" not in services[0].price


def test_extract_price_from_text() -> None:
    assert extract_price_from_text("$3.50 USD") == "$3.50 USD"
    assert extract_price_from_text("Price: €10.00") == "€10.00"
    assert extract_price_from_text("CNY 25.00") == "CNY 25.00"
    assert extract_price_from_text("no price here") == "unknown"


def test_parse_size_to_mb() -> None:
    assert parse_size_to_mb("1 GB") == 1024
    assert parse_size_to_mb("512 MB") == 512
    assert parse_size_to_mb("1 TB") == 1024 * 1024
    assert parse_size_to_mb("20 GB") == 20 * 1024
    assert parse_size_to_mb("unknown") is None


def test_extract_billing_cycle() -> None:
    assert extract_billing_cycle("Monthly") == "Monthly"
    assert extract_billing_cycle("monthly") == "Monthly"
    assert extract_billing_cycle("/mo") == "Monthly"
    assert extract_billing_cycle("Annually") == "Annually"
    assert extract_billing_cycle("yearly") == "Annually"
    assert extract_billing_cycle("/yr") == "Annually"
    assert extract_billing_cycle("Quarterly") == "Quarterly"
    assert extract_billing_cycle("Semi-Annually") == "Semi-Annually"
    assert extract_billing_cycle("Free") == "Free"
    assert extract_billing_cycle("unknown") == "unknown"
    assert extract_billing_cycle("") == "unknown"


def test_parse_service_detail_with_billing_cycle() -> None:
    html = """
    <table>
      <tr><th>Next Due Date</th><td>2026-08-01</td></tr>
      <tr><th>Recurring Amount</th><td>$3.50 USD</td></tr>
      <tr><th>Billing Cycle</th><td>Monthly</td></tr>
    </table>
    """
    expiry, usage, remaining, price, cycle = parse_service_detail(html)

    assert price == "$3.50 USD"
    assert cycle == "Monthly"


def test_parse_services_from_table_with_billing_cycle() -> None:
    html = """
    <table>
      <tr><th>Product/Service</th><th>Status</th><th>Next Due Date</th><th>Amount</th><th>Billing Cycle</th><th></th></tr>
      <tr>
        <td>Tokyo VPS 1G</td>
        <td>Active</td>
        <td>2026-12-31</td>
        <td>$5.00 USD</td>
        <td>Annually</td>
        <td><a href="clientarea.php?action=productdetails&id=42">Manage</a></td>
      </tr>
    </table>
    """

    services = parse_services(html, "https://provider-a.example/")

    assert len(services) == 1
    assert services[0].price == "$5.00 USD"
    assert services[0].billing_cycle == "Annually"
