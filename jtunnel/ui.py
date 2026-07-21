"""Rich console helpers for the JT Tunnel CLI."""

from __future__ import annotations

import sys
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

console = Console()
err_console = Console(stderr=True)


def is_interactive() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def clear_screen() -> None:
    """Replace previous UI with a fresh frame (interactive TTY only)."""
    if is_interactive():
        console.clear()


def print_error(message: str) -> None:
    err_console.print(f"[bold red]Error:[/] {message}")


def print_success(message: str) -> None:
    console.print(f"[bold green]✓[/] {message}")


def print_info(message: str) -> None:
    console.print(message)


def header_panel(
    *,
    logged_in: bool,
    tunnel: dict[str, Any] | None,
    default_service: str | None = None,
) -> None:
    if logged_in and tunnel:
        detail = (
            f"[green]● signed in[/] · ports "
            f"[cyan]{tunnel['port_start']}–{tunnel['port_end']}[/] · "
            f"[cyan]{tunnel.get('host', '')}[/]"
        )
        if default_service:
            detail += f" · default [cyan]{default_service}[/]"
    elif logged_in:
        detail = "[yellow]● signed in[/] · port range not configured"
        if default_service:
            detail += f" · default [cyan]{default_service}[/]"
    else:
        detail = "[dim]○ not signed in[/] · run login to get started"
    console.print(Panel(detail, title="[bold]JT Tunnel[/]", border_style="blue"))


def tunnels_table(
    entries: list[tuple[str, str, Any]],
    *,
    title: str | None = None,
) -> Table:
    """Build a table from (name, url, local_port) rows."""
    table = Table(title=title, show_header=True, header_style="bold")
    table.add_column("Service", style="cyan")
    table.add_column("Public URL", style="green")
    table.add_column("Local", justify="right")
    for name, url, local_port in entries:
        table.add_row(name, str(url), f":{local_port}")
    return table


def print_tunnels_table(
    entries: list[tuple[str, str, Any]],
    *,
    title: str | None = None,
) -> None:
    console.print(tunnels_table(entries, title=title))


def login_code_panel(verification_uri: str, user_code: str) -> None:
    body = Text()
    body.append("Open this URL and enter the code:\n\n", style="dim")
    body.append(f"  {verification_uri}\n\n", style="cyan underline")
    body.append("  Code: ", style="dim")
    body.append(user_code, style="bold yellow")
    console.print(Panel(body, title="[bold]Sign in[/]", border_style="blue"))


def status_panel(rows: list[tuple[str, str]]) -> None:
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column(style="dim")
    table.add_column()
    for label, value in rows:
        table.add_row(label, value)
    console.print(Panel(table, title="[bold]Status[/]", border_style="blue"))


def menu_choice(options: list[str], *, prompt: str = "Choose") -> str:
    """Numbered menu; returns the selected option string."""
    console.print()
    for i, option in enumerate(options, start=1):
        console.print(f"  [cyan]{i}.[/] {option}")
    console.print()
    while True:
        raw = console.input(f"[bold]{prompt}[/] [dim](1–{len(options)})[/]: ").strip()
        if raw.isdigit():
            idx = int(raw)
            if 1 <= idx <= len(options):
                return options[idx - 1]
        console.print("[red]Enter a number from the list.[/]")
