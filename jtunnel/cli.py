"""Typer CLI entry point."""

from __future__ import annotations

from pathlib import Path

import httpx
import typer

from .auth import open_browser, poll_device_token, start_device_flow
from .config import (
    api_base,
    clear_active_tunnels,
    clear_device_token,
    device_token_path,
    get_default_service,
    get_default_tunnel_entry,
    load_active_tunnels,
    load_device_token,
    load_tunnel_config,
    public_host,
    public_url,
    save_device_token,
    save_tunnel_config,
    set_default_service,
    tunnel_config_path,
    tunnel_host,
)
from .errors import TunnelError, UserDisconnected
from .slots import MaxTunnelServicesError, resolve_services
from .tunnel import run as run_tunnel
from .ui import (
    clear_screen,
    confirm,
    header_panel,
    is_interactive,
    login_code_panel,
    menu_choice,
    pause,
    print_error,
    print_info,
    print_success,
    print_tunnels_table,
    prompt_int,
    prompt_text,
    status_panel,
)

app = typer.Typer(
    help="JT Tunnel CLI — expose local services on your allocated ports",
    invoke_without_command=True,
    no_args_is_help=False,
)


def _detect_port() -> int:
    path = Path(".jtunnel.toml")
    if path.exists():
        try:
            import tomllib

            cfg = tomllib.loads(path.read_text())
            return int(cfg.get("port", 3000))
        except Exception:
            pass
    return 3000


def _require_auth() -> bool:
    if not load_device_token():
        print_error("Not signed in. Run: jtunnel login")
        return False
    return True


def _resolve_services(
    mappings: list[tuple[str, int]],
) -> dict[str, tuple[int, int]] | None:
    tunnel = load_tunnel_config()
    if not tunnel:
        print_error(
            "No port block configured. Run jtunnel login after an admin assigns your ports."
        )
        return None

    try:
        return resolve_services(
            mappings,
            int(tunnel["port_start"]),
            int(tunnel["port_end"]),
            load_active_tunnels(),
        )
    except MaxTunnelServicesError as exc:
        print_error(str(exc))
        return None
    except ValueError as exc:
        print_error(str(exc))
        return None


def _run_expose_services(services: dict[str, tuple[int, int]]) -> bool:
    """Connect tunnels. Returns False on failure; True after a normal session end.

    Raises UserDisconnected when the user stops with Ctrl+C.
    """
    names = ", ".join(services)
    print_info(f"Connecting {names}...")
    try:
        run_tunnel(services)
        return True
    except UserDisconnected:
        raise
    except TunnelError as exc:
        print_error(str(exc))
        return False
    except Exception as exc:  # noqa: BLE001 — keep interactive menu alive
        print_error(f"Tunnel crashed: {exc}")
        return False


def _collect_expose_wizard(max_services: int = 3) -> list[tuple[str, int]]:
    """Interactive prompts for 1–3 services."""
    default_port = _detect_port()
    mappings: list[tuple[str, int]] = []
    used_names: set[str] = set()

    while len(mappings) < max_services:
        n = len(mappings) + 1
        default_name = "default" if n == 1 else f"service{n}"
        name = prompt_text(
            f"Service label [{n}/{max_services}]",
            default=default_name,
        ).strip().lower()
        if not name:
            print_error("Service name is required")
            continue
        if name in used_names:
            print_error(f"Duplicate name {name}")
            continue

        port = prompt_int(
            "Local port",
            default=default_port if n == 1 else 8000,
        )
        if port < 1 or port > 65535:
            print_error("Port must be between 1 and 65535")
            continue

        mappings.append((name, port))
        used_names.add(name)

        if len(mappings) >= max_services:
            break
        if not confirm("Add another service?", default=False):
            break

    return mappings


def _pause(message: str | None = None) -> None:
    if message:
        print_info(message)
    pause()


def _do_login() -> bool:
    try:
        data = start_device_flow()
    except (httpx.HTTPError, OSError) as exc:
        print_error(f"Could not start login: {exc}")
        return False

    login_code_panel(data["verification_uri"], data["user_code"])
    open_browser(data["verification_uri"])
    print_info("Waiting for browser approval... (Ctrl+C to cancel)")

    try:
        result = poll_device_token(
            data["device_code"],
            interval=data.get("interval", 2),
        )
    except KeyboardInterrupt:
        print_error("Login cancelled.")
        return False
    except (RuntimeError, TimeoutError, OSError) as exc:
        print_error(str(exc))
        return False

    tunnel = result.get("tunnel")
    if isinstance(tunnel, dict):
        save_tunnel_config(tunnel)

    save_device_token(result["token"])
    print_success(f"Signed in. Credentials saved to {device_token_path()}")
    tunnel = load_tunnel_config()
    if tunnel:
        print_info(
            f"  Ports {tunnel['port_start']}-{tunnel['port_end']} "
            f"on {tunnel['host']}"
        )
    return True


def _do_list() -> None:
    tunnels = load_active_tunnels()
    if not tunnels:
        print_info("No saved tunnels. Run expose to create one.")
        return

    default = get_default_service()
    entries: list[tuple[str, str, object]] = []
    for name, entry in sorted(tunnels.items()):
        if not isinstance(entry, dict):
            continue
        url = entry.get("url") or public_url(int(entry["public_port"]))
        label = f"{name} *" if name == default else name
        entries.append((label, str(url), entry.get("local_port", "?")))
    print_tunnels_table(entries, title="Saved tunnels")
    if default:
        print_info(f"* default for Expose: {default}")


def _saved_tunnel_mappings() -> list[tuple[str, int]]:
    """Return sorted (name, local_port) pairs from saved tunnels."""
    tunnels = load_active_tunnels()
    mappings: list[tuple[str, int]] = []
    for name, entry in sorted(tunnels.items()):
        if not isinstance(entry, dict) or "local_port" not in entry:
            continue
        try:
            mappings.append((name, int(entry["local_port"])))
        except (TypeError, ValueError):
            continue
    return mappings


def _start_saved_tunnel(name: str, local_port: int) -> bool:
    services = _resolve_services([(name, local_port)])
    if not services:
        return False
    set_default_service(name)
    print_info(f"Starting {name} -> local :{local_port}")
    return _run_expose_services(services)


def _start_saved_mappings(mappings: list[tuple[str, int]]) -> bool:
    if not mappings:
        print_error("No services selected")
        return False
    services = _resolve_services(mappings)
    if not services:
        return False
    set_default_service(mappings[0][0])
    names = ", ".join(f"{n} (:{p})" for n, p in mappings)
    print_info(f"Starting {names}")
    return _run_expose_services(services)


def _pick_saved_tunnel() -> tuple[str, int] | None:
    mappings = _saved_tunnel_mappings()
    if not mappings:
        print_info("No saved tunnels.")
        return None
    default = get_default_service()
    options = []
    for name, port in mappings:
        mark = " *" if name == default else ""
        options.append(f"{name}{mark} (local :{port})")
    options.append("Back")
    choice = menu_choice(options, prompt="Start which tunnel")
    if choice == "Back":
        return None
    idx = options.index(choice)
    return mappings[idx]


def _pick_saved_tunnel_for_default() -> str | None:
    mappings = _saved_tunnel_mappings()
    if not mappings:
        return None
    current = get_default_service()
    options = [
        f"{name}{' *' if name == current else ''} (local :{port})"
        for name, port in mappings
    ]
    options.append("Back")
    choice = menu_choice(options, prompt="Set default")
    if choice == "Back":
        return None
    return mappings[options.index(choice)][0]


def _pick_multiple_saved() -> list[tuple[str, int]] | None:
    """Ask Include? for each saved tunnel until 3 chosen or user stops."""
    mappings = _saved_tunnel_mappings()
    if not mappings:
        print_info("No saved tunnels.")
        return None

    _do_list()
    selected: list[tuple[str, int]] = []
    for name, port in mappings:
        if len(selected) >= 3:
            break
        include = confirm(
            f"Include {name} (local :{port})?",
            default=True,
        )
        if include:
            selected.append((name, port))
    return selected


def _do_list_menu() -> bool:
    """Show saved tunnels; start one or set default. Returns True if user disconnected."""
    clear_screen()
    tunnel = load_tunnel_config()
    default = get_default_service()
    header_panel(
        logged_in=bool(load_device_token()),
        tunnel=tunnel,
        default_service=default,
    )
    _do_list()

    mappings = _saved_tunnel_mappings()
    if not mappings:
        _pause()
        return False

    options = []
    for name, port in mappings:
        mark = " *" if name == default else ""
        options.append(f"Start {name}{mark} (:{port})")
    options.extend(["Set default", "Back"])

    choice = menu_choice(options, prompt="Action")
    if choice == "Back":
        return False
    if choice == "Set default":
        picked = _pick_saved_tunnel_for_default()
        if picked:
            set_default_service(picked)
            print_success(f"Default set to {picked}")
            _pause()
        return False

    if not _require_auth():
        _pause()
        return False
    idx = options.index(choice)
    name, local_port = mappings[idx]
    clear_screen()
    disconnected = False
    try:
        _start_saved_tunnel(name, local_port)
    except UserDisconnected:
        disconnected = True
    except KeyboardInterrupt:
        print_info("\nDisconnected.")
        disconnected = True
    except Exception as exc:  # noqa: BLE001
        print_error(f"Unexpected error: {exc}")
        _pause()
        return False
    if not disconnected:
        _pause()
    return disconnected


def _do_status() -> None:
    token = load_device_token()
    tunnel = load_tunnel_config()
    rows = [
        ("API base", api_base()),
        ("Tunnel host", tunnel_host()),
        ("Public host", public_host()),
        ("Config dir", str(device_token_path().parent)),
        ("Logged in", "yes" if token else "no"),
    ]
    if tunnel:
        rows.append(
            (
                "Port range",
                f"{tunnel['port_start']}-{tunnel['port_end']} ({tunnel_config_path().name})",
            )
        )
    else:
        rows.append(("Port range", "not configured"))
    default = get_default_service()
    rows.append(("Default tunnel", default or "not set"))
    status_panel(rows)


def _do_logout() -> None:
    clear_device_token()
    clear_active_tunnels()
    tunnel_path = tunnel_config_path()
    if tunnel_path.exists():
        tunnel_path.unlink()
    print_success("Logged out.")


def _collect_single_expose() -> tuple[str, int] | None:
    """Prompt for one local port (label defaults to default)."""
    default_port = _detect_port()
    name = prompt_text("Service label", default="default").strip().lower()
    if not name:
        print_error("Service name is required")
        return None
    port = prompt_int("Local port", default=default_port)
    if port < 1 or port > 65535:
        print_error("Port must be between 1 and 65535")
        return None
    return name, port


def _do_expose_quick() -> bool:
    """Expose a single service. Prefer default saved tunnel when available."""
    if not _require_auth():
        return False

    saved = _saved_tunnel_mappings()
    if saved and is_interactive():
        try:
            default_entry = get_default_tunnel_entry()
            if default_entry is not None:
                name, entry = default_entry
                local_port = int(entry["local_port"])
                return _start_saved_tunnel(name, local_port)

            action = menu_choice(
                ["Choose saved tunnel", "Configure new", "Cancel"],
                prompt="Expose",
            )
        except KeyboardInterrupt:
            print_info("\nCancelled.")
            return False

        if action == "Cancel":
            return False
        if action == "Choose saved tunnel":
            try:
                picked = _pick_saved_tunnel()
            except KeyboardInterrupt:
                print_info("\nCancelled.")
                return False
            if not picked:
                return False
            return _start_saved_tunnel(*picked)

    try:
        mapping = _collect_single_expose()
    except KeyboardInterrupt:
        print_info("\nCancelled.")
        return False
    if not mapping:
        return False
    services = _resolve_services([mapping])
    if not services:
        return False
    return _run_expose_services(services)


def _do_expose_wizard() -> bool:
    """Run the multi-service expose wizard. Returns False if setup failed or cancelled."""
    if not _require_auth():
        return False
    try:
        mappings = _collect_expose_wizard()
    except KeyboardInterrupt:
        print_info("\nCancelled.")
        return False
    if not mappings:
        print_error("No services selected")
        return False
    return _start_saved_mappings(mappings)


def _do_expose_multi() -> bool:
    """Expose multiple: start all / pick saved / configure new."""
    if not _require_auth():
        return False

    saved = _saved_tunnel_mappings()
    if saved and is_interactive():
        try:
            action = menu_choice(
                [
                    f"Start all saved ({min(len(saved), 3)})",
                    "Pick saved",
                    "Configure new",
                    "Cancel",
                ],
                prompt="Expose multiple",
            )
        except KeyboardInterrupt:
            print_info("\nCancelled.")
            return False

        if action == "Cancel":
            return False
        if action.startswith("Start all saved"):
            return _start_saved_mappings(saved[:3])
        if action == "Pick saved":
            try:
                selected = _pick_multiple_saved()
            except KeyboardInterrupt:
                print_info("\nCancelled.")
                return False
            if not selected:
                print_error("No services selected")
                return False
            return _start_saved_mappings(selected)

    return _do_expose_wizard()


def _run_expose_from_menu(*, multi: bool) -> None:
    clear_screen()
    disconnected = False
    try:
        if multi:
            _do_expose_multi()
        else:
            _do_expose_quick()
    except UserDisconnected:
        disconnected = True
    except KeyboardInterrupt:
        print_info("\nDisconnected.")
        disconnected = True
    except Exception as exc:  # noqa: BLE001 — return to menu
        print_error(f"Unexpected error: {exc}")
        _pause()
        return
    if not disconnected:
        _pause()


def _run_menu() -> None:
    while True:
        clear_screen()
        tunnel = load_tunnel_config()
        logged_in = bool(load_device_token())
        header_panel(
            logged_in=logged_in,
            tunnel=tunnel,
            default_service=get_default_service() if logged_in else None,
        )

        options = [
            "Expose",
            "Expose multiple",
            "List tunnels",
            "Logout" if logged_in else "Login",
            "Quit",
        ]
        try:
            choice = menu_choice(options)
        except KeyboardInterrupt:
            clear_screen()
            return
        except SystemExit:
            clear_screen()
            raise

        if choice == "Expose":
            if not logged_in:
                print_error("Not signed in. Choose Login first.")
                _pause()
                continue
            _run_expose_from_menu(multi=False)
            continue
        if choice == "Expose multiple":
            if not logged_in:
                print_error("Not signed in. Choose Login first.")
                _pause()
                continue
            _run_expose_from_menu(multi=True)
            continue
        if choice == "List tunnels":
            try:
                _do_list_menu()
            except UserDisconnected:
                continue
            except KeyboardInterrupt:
                continue
            continue
        if choice == "Login":
            clear_screen()
            _do_login()
            _pause()
            continue
        if choice == "Logout":
            clear_screen()
            _do_logout()
            _pause()
            continue
        if choice == "Quit":
            clear_screen()
            return


@app.callback()
def main(ctx: typer.Context) -> None:
    """JT Tunnel — run without a command for the interactive menu."""
    if ctx.invoked_subcommand is None:
        if is_interactive():
            _run_menu()
        else:
            print(ctx.get_help())
            raise typer.Exit(0)


@app.command("login")
def login_cmd() -> None:
    """Sign in to JT Tunnel using device approval in your browser."""
    if not _do_login():
        raise typer.Exit(1)


@app.command()
def expose(
    service: str = typer.Argument(
        None,
        help="Service label (any name; max 3 concurrent). Omit for interactive wizard.",
    ),
    port: int | None = typer.Option(
        None, "--port", "-p", help="Local service port"
    ),
    wizard: bool = typer.Option(
        False, "--wizard", "-w", help="Interactive multi-service expose wizard"
    ),
) -> None:
    """Expose local service(s) on your allocated public tunnel ports."""
    if not _require_auth():
        raise typer.Exit(1)

    use_wizard = wizard
    if use_wizard:
        try:
            ok = _do_expose_multi() if is_interactive() else _do_expose_wizard()
        except UserDisconnected:
            return
        if not ok:
            raise typer.Exit(1)
        return

    if service is None and port is None and is_interactive():
        try:
            ok = _do_expose_quick()
        except UserDisconnected:
            return
        if not ok:
            raise typer.Exit(1)
        return

    name = (service or "default").strip().lower() or "default"
    local_port = port if port is not None else _detect_port()
    services = _resolve_services([(name, local_port)])
    try:
        if not services or not _run_expose_services(services):
            raise typer.Exit(1)
    except UserDisconnected:
        return


@app.command("list")
def list_cmd() -> None:
    """List tunnels saved from recent expose sessions."""
    _do_list()


@app.command()
def status() -> None:
    """Show current CLI configuration and token status."""
    _do_status()


@app.command()
def logout() -> None:
    """Remove the saved device token and tunnel state."""
    _do_logout()


if __name__ == "__main__":
    app()
