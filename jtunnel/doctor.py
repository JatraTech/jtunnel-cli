"""Connectivity and environment diagnostics for JT Tunnel CLI."""

from __future__ import annotations

import socket
from dataclasses import dataclass
from typing import Callable
from urllib.parse import urlparse

from .config import (
    api_base,
    load_device_token,
    load_tunnel_config,
    public_host,
    tunnel_host,
)
from .ui import print_error, print_info, print_success, status_panel
from .windows import (
    add_firewall_rule,
    check_firewall_rule,
    current_exe_path,
    firewall_fix_command,
    is_windows,
)

ConnectFn = Callable[[str, int, float], bool]


@dataclass
class CheckResult:
    name: str
    ok: bool | None  # None = skipped / inconclusive
    detail: str
    critical: bool = True


def tcp_reachable(host: str, port: int, timeout: float = 5.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _host_port_from_url(url: str, default_port: int) -> tuple[str, int]:
    parsed = urlparse(url)
    host = parsed.hostname or url
    port = parsed.port or default_port
    return host, port


def run_checks(
    *,
    local_port: int | None = None,
    connect: ConnectFn | None = None,
    firewall_check: Callable[[], tuple[bool | None, str]] | None = None,
) -> list[CheckResult]:
    """Run diagnostic checks. ``connect`` and ``firewall_check`` are injectable for tests."""
    connect_fn = connect or (lambda h, p, t: tcp_reachable(h, p, t))
    results: list[CheckResult] = []

    token = load_device_token()
    results.append(
        CheckResult(
            name="Signed in",
            ok=bool(token),
            detail="device.jwt present" if token else "Not signed in — run: jtunnel login",
            critical=False,
        )
    )

    tunnel = load_tunnel_config()
    if tunnel:
        results.append(
            CheckResult(
                name="Port block",
                ok=True,
                detail=f"{tunnel.get('port_start')}-{tunnel.get('port_end')} "
                f"({tunnel.get('host') or public_host()})",
                critical=False,
            )
        )
    else:
        results.append(
            CheckResult(
                name="Port block",
                ok=False,
                detail="No tunnel.json / port claims — run jtunnel login after admin assigns ports",
                critical=False,
            )
        )

    api_host, api_port = _host_port_from_url(api_base(), 443)
    api_ok = connect_fn(api_host, api_port, 5.0)
    results.append(
        CheckResult(
            name="Admin API",
            ok=api_ok,
            detail=f"{api_host}:{api_port} reachable"
            if api_ok
            else f"Cannot reach {api_host}:{api_port}",
        )
    )

    tun_host, tun_port = _host_port_from_url(tunnel_host(), 443)
    tun_ok = connect_fn(tun_host, tun_port, 5.0)
    results.append(
        CheckResult(
            name="Tunnel server",
            ok=tun_ok,
            detail=f"{tun_host}:{tun_port} reachable"
            if tun_ok
            else f"Cannot reach {tun_host}:{tun_port}",
        )
    )

    if local_port is not None:
        local_ok = connect_fn("127.0.0.1", local_port, 2.0)
        results.append(
            CheckResult(
                name="Local app",
                ok=local_ok,
                detail=f"127.0.0.1:{local_port} listening"
                if local_ok
                else f"Nothing listening on 127.0.0.1:{local_port} — start your app first",
            )
        )

    if is_windows():
        if firewall_check is not None:
            fw_ok, fw_detail = firewall_check()
        else:
            fw_ok, fw_detail = check_firewall_rule(current_exe_path())
        results.append(
            CheckResult(
                name="Windows Firewall",
                ok=fw_ok,
                detail=fw_detail,
                critical=fw_ok is False,
            )
        )

    return results


def run_doctor(
    *,
    local_port: int | None = None,
    fix_firewall: bool = False,
) -> bool:
    """Run doctor checks; optionally fix firewall first. Returns True if all critical checks pass."""
    if fix_firewall:
        if not is_windows():
            print_error("--fix-firewall is only supported on Windows.")
            return False
        print_info("Requesting Administrator approval to add the Windows Firewall rule...")
        ok, message = add_firewall_rule(current_exe_path())
        if ok:
            print_success(message)
        else:
            print_error(message)
            return False

    results = run_checks(local_port=local_port)
    return print_report(results)


def print_report(results: list[CheckResult]) -> bool:
    """Print results. Returns True if all critical checks passed."""
    rows: list[tuple[str, str]] = []
    all_ok = True
    for r in results:
        if r.ok is True:
            mark = "OK"
        elif r.ok is False:
            mark = "FAIL"
            if r.critical:
                all_ok = False
        else:
            mark = "SKIP"
        rows.append((r.name, f"{mark} — {r.detail}"))

    status_panel(rows)

    if is_windows():
        fw = next((r for r in results if r.name == "Windows Firewall"), None)
        if fw is not None and fw.ok is False:
            print_info("")
            print_info(f"Add the firewall rule: {firewall_fix_command()}")
            print_info("Also check Windows Security → Protection history for blocked apps.")
        elif fw is not None and fw.ok is None:
            print_info("")
            print_info("Firewall status could not be confirmed. Connectivity checks above are authoritative.")

    if all_ok:
        print_success("All critical checks passed.")
    else:
        print_error("One or more critical checks failed.")
    return all_ok
