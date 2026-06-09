from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError
from rich.console import Console
from rich.table import Table

from .client import ProviderError, fetch_provider_services
from .models import ServiceInfo, load_config
from .notifications import (
    TelegramBot,
    TelegramError,
    build_renewal_alerts,
    build_traffic_alerts,
    collect_services,
    format_cost_summary,
    format_summary,
    format_service_date,
    normalize_service_dates,
    require_telegram,
    run_bot,
)

app = typer.Typer(
    help="Manage VPS services across WHMCS-like providers.",
    no_args_is_help=True,
)
console = Console()
notify_app = typer.Typer(help="Send Telegram notifications.")
app.add_typer(notify_app, name="notify")


@app.callback()
def main() -> None:
    """Manage VPS services across WHMCS-like providers."""


@app.command("list")
def list_services(
    config: Annotated[Path, typer.Option("--config", "-c", help="Path to config YAML.")] = Path("config.yaml"),
    provider: Annotated[str | None, typer.Option("--provider", "-p", help="Only query one provider.")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output JSON instead of a table.")] = False,
) -> None:
    """List VPS services, due dates, and remaining traffic."""
    try:
        app_config = load_config(config)
        providers = app_config.provider_subset(provider)
    except (FileNotFoundError, ValueError, ValidationError) as exc:
        _fail(str(exc))

    all_services: list[ServiceInfo] = []
    errors: list[str] = []

    for provider_config in providers:
        try:
            all_services.extend(fetch_provider_services(provider_config, app_config.sessions))
        except ProviderError as exc:
            errors.append(str(exc))
        except Exception as exc:  # Keep one broken merchant from hiding the others.
            errors.append(f"{provider_config.name}: {exc}")

    all_services = normalize_service_dates(all_services)

    if json_output:
        payload = {
            "services": [service.model_dump() for service in all_services],
            "errors": errors,
        }
        console.print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        _print_table(all_services)
        for error in errors:
            console.print(f"[red]Error:[/red] {error}")

    if errors and not all_services:
        raise typer.Exit(code=1)


@notify_app.command("test")
def notify_test(
    config: Annotated[Path, typer.Option("--config", "-c", help="Path to config YAML.")] = Path("config.yaml"),
) -> None:
    """Send a Telegram test message."""
    app_config = _load_app_config(config)
    try:
        with TelegramBot(require_telegram(app_config)) as bot:
            bot.send_message("VPS DueGuard Telegram test message.")
    except (TelegramError, Exception) as exc:
        _fail(str(exc))
    console.print("[green]Telegram test message sent.[/green]")


@notify_app.command("daily")
def notify_daily(
    config: Annotated[Path, typer.Option("--config", "-c", help="Path to config YAML.")] = Path("config.yaml"),
) -> None:
    """Send a daily VPS summary to Telegram."""
    app_config = _load_app_config(config)
    try:
        services, errors = collect_services(app_config)
        with TelegramBot(require_telegram(app_config)) as bot:
            bot.send_message(format_summary(services, errors))
    except (TelegramError, Exception) as exc:
        _fail(str(exc))
    console.print("[green]Daily report sent.[/green]")


@notify_app.command("renewals")
def notify_renewals(
    config: Annotated[Path, typer.Option("--config", "-c", help="Path to config YAML.")] = Path("config.yaml"),
) -> None:
    """Send renewal reminders to Telegram, deduplicated by local state."""
    app_config = _load_app_config(config)
    try:
        services, errors = collect_services(app_config)
        alerts = build_renewal_alerts(
            services,
            app_config.notifications.renewal_days,
            app_config.notifications.state_file,
        )
        with TelegramBot(require_telegram(app_config)) as bot:
            for alert in alerts:
                bot.send_message(alert)
            if errors:
                bot.send_message(format_summary([], errors))
    except (TelegramError, Exception) as exc:
        _fail(str(exc))
    console.print(f"[green]Renewal reminders sent: {len(alerts)}[/green]")


@notify_app.command("traffic-alerts")
def notify_traffic_alerts(
    config: Annotated[Path, typer.Option("--config", "-c", help="Path to config YAML.")] = Path("config.yaml"),
) -> None:
    """Send traffic usage alerts to Telegram when threshold is exceeded."""
    app_config = _load_app_config(config)
    traffic_config = app_config.notifications.traffic_alerts
    if not traffic_config.enabled:
        console.print("[yellow]Traffic alerts are disabled in config.[/yellow]")
        return
    try:
        services, errors = collect_services(app_config)
        alerts = build_traffic_alerts(
            services,
            traffic_config.threshold,
            app_config.notifications.state_file,
        )
        with TelegramBot(require_telegram(app_config)) as bot:
            for alert in alerts:
                bot.send_message(alert)
            if errors:
                bot.send_message(format_summary([], errors))
    except (TelegramError, Exception) as exc:
        _fail(str(exc))
    console.print(f"[green]Traffic alerts sent: {len(alerts)}[/green]")


@app.command("bot")
def bot(
    config: Annotated[Path, typer.Option("--config", "-c", help="Path to config YAML.")] = Path("config.yaml"),
) -> None:
    """Run the Telegram long-polling command bot."""
    app_config = _load_app_config(config)
    try:
        console.print("[green]Telegram bot started. Press Ctrl+C to stop.[/green]")
        run_bot(app_config, config_path=config)
    except KeyboardInterrupt:
        console.print("[yellow]Telegram bot stopped.[/yellow]")
    except (TelegramError, Exception) as exc:
        _fail(str(exc))


@app.command("cost")
def cost_summary(
    config: Annotated[Path, typer.Option("--config", "-c", help="Path to config YAML.")] = Path("config.yaml"),
    provider: Annotated[str | None, typer.Option("--provider", "-p", help="Only query one provider.")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output JSON instead of a table.")] = False,
) -> None:
    """Show cost summary across providers."""
    try:
        app_config = load_config(config)
        providers = app_config.provider_subset(provider)
    except (FileNotFoundError, ValueError, ValidationError) as exc:
        _fail(str(exc))

    all_services: list[ServiceInfo] = []
    errors: list[str] = []

    for provider_config in providers:
        try:
            all_services.extend(fetch_provider_services(provider_config, app_config.sessions))
        except ProviderError as exc:
            errors.append(str(exc))
        except Exception as exc:
            errors.append(f"{provider_config.name}: {exc}")

    all_services = normalize_service_dates(all_services)

    if json_output:
        from .notifications import parse_price_amount

        providers_costs: dict[str, dict[str, object]] = {}
        for svc in all_services:
            if svc.provider not in providers_costs:
                providers_costs[svc.provider] = {"services": [], "total": 0.0, "currency": ""}
            amount, currency = parse_price_amount(svc.price)
            providers_costs[svc.provider]["services"].append({
                "service_name": svc.service_name,
                "price": svc.price,
                "amount": amount,
                "currency": currency,
            })
            if amount > 0:
                providers_costs[svc.provider]["total"] = float(providers_costs[svc.provider]["total"]) + amount
                if currency:
                    providers_costs[svc.provider]["currency"] = currency

        grand_total = sum(float(p["total"]) for p in providers_costs.values())
        payload = {
            "providers": providers_costs,
            "grand_total": grand_total,
            "errors": errors,
        }
        console.print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        from .notifications import parse_price_amount

        table = Table(title="VPS Cost Summary")
        table.add_column("Provider")
        table.add_column("Service")
        table.add_column("Price")

        provider_groups: dict[str, list[ServiceInfo]] = {}
        for svc in all_services:
            provider_groups.setdefault(svc.provider, []).append(svc)

        grand_total = 0.0
        grand_currency = ""

        for provider_name, services in sorted(provider_groups.items()):
            provider_total = 0.0
            provider_currency = ""
            for svc in services:
                amount, currency = parse_price_amount(svc.price)
                if amount > 0:
                    provider_total += amount
                    provider_currency = currency
                table.add_row(svc.provider, svc.service_name, svc.price)
            if provider_total > 0:
                table.add_row("", f"[bold]Subtotal[/bold]", f"[bold]{provider_total:.2f} {provider_currency}[/bold]")
                grand_total += provider_total
                grand_currency = provider_currency

        if grand_total > 0:
            table.add_row("", f"[bold]Grand Total[/bold]", f"[bold]{grand_total:.2f} {grand_currency}[/bold]")

        if all_services:
            console.print(table)
        else:
            console.print("[yellow]No services found.[/yellow]")

        for error in errors:
            console.print(f"[red]Error:[/red] {error}")


def _print_table(services: list[ServiceInfo]) -> None:
    table = Table(title="VPS Services")
    table.add_column("Provider")
    table.add_column("Service")
    table.add_column("Status")
    table.add_column("Expires")
    table.add_column("Traffic Used / Total")
    table.add_column("Traffic Remaining")
    table.add_column("Price")
    table.add_column("Cycle")

    for service in services:
        price_str = service.price
        if service.billing_cycle and service.billing_cycle != "unknown":
            price_str = f"{service.price} ({service.billing_cycle})"
        table.add_row(
            service.provider,
            service.service_name,
            service.status,
            format_service_date(service.expires_at),
            service.traffic_usage,
            service.traffic_remaining,
            price_str,
            service.billing_cycle if service.billing_cycle != "unknown" else "",
        )

    if services:
        console.print(table)
    else:
        console.print("[yellow]No services found.[/yellow]")


def _fail(message: str) -> None:
    console.print(f"[red]Error:[/red] {message}")
    raise typer.Exit(code=1)


def _load_app_config(path: Path):
    try:
        return load_config(path)
    except (FileNotFoundError, ValueError, ValidationError) as exc:
        _fail(str(exc))
