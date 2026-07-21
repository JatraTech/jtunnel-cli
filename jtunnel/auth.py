"""Device-code authentication flow against JT Tunnel admin."""

from __future__ import annotations

import os
import shutil
import subprocess
import time
import webbrowser
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urljoin

import httpx

from .config import api_base, save_tunnel_config


def start_device_flow() -> dict:
    """Initiate the device code flow and return the device payload."""
    url = urljoin(api_base(), "/api/v1/tunnel/auth/device-code/")
    resp = httpx.post(url, json={}, timeout=10)
    resp.raise_for_status()
    return resp.json()


def poll_device_token(
    device_code: str,
    interval: int = 5,
    timeout: int = 600,
    *,
    on_wait: Callable[[], None] | None = None,
) -> dict:
    """Poll JT Tunnel admin until the user approves the device code."""
    url = urljoin(api_base(), "/api/v1/tunnel/auth/token/")
    start = time.time()
    while True:
        resp = httpx.post(url, json={"device_code": device_code}, timeout=10)
        data = resp.json()
        if resp.status_code == 200 and data.get("token"):
            return data
        error = data.get("error")
        if error == "no_tunnel_port_block":
            raise RuntimeError(
                "No JT Tunnel port block on your account. Ask an admin to run: "
                "python manage.py allocate_tunnel_ports"
            )
        if error == "authorization_denied":
            raise RuntimeError(
                "Approval cancelled (browser closed or Cancel pressed). "
                "Run jtunnel login again."
            )
        if error == "authorization_expired":
            raise TimeoutError(
                "Approval code expired. Run jtunnel login again."
            )
        if time.time() - start > timeout:
            raise TimeoutError(
                "Approval timed out after 10 minutes. Run jtunnel login again."
            )
        if on_wait:
            on_wait()
        time.sleep(interval)


def _running_in_wsl() -> bool:
    if os.environ.get("WSL_DISTRO_NAME") or os.environ.get("WSL_INTEROP"):
        return True
    try:
        return "microsoft" in Path("/proc/version").read_text().lower()
    except OSError:
        return False


def open_browser(verification_uri: str) -> None:
    """Open the approval URL in the user's normal browser.

    Under WSL, Python's webbrowser often launches a Linux Chrome instance.
    Prefer the Windows host browser via wslview / cmd.exe start.
    """
    try:
        if _running_in_wsl():
            wslview = shutil.which("wslview")
            if wslview:
                subprocess.Popen(  # noqa: S603
                    [wslview, verification_uri],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return
            cmd = shutil.which("cmd.exe") or "/mnt/c/Windows/System32/cmd.exe"
            if Path(cmd).exists():
                # `start` opens the default Windows browser / existing Chrome profile.
                subprocess.Popen(  # noqa: S603
                    [cmd, "/c", "start", "", verification_uri],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return
        webbrowser.open(verification_uri)
    except Exception:
        pass


def login(
    *,
    announce: Callable[[dict], None] | None = None,
    on_wait: Callable[[], None] | None = None,
) -> str:
    """Run the full login flow and return the device token."""
    data = start_device_flow()
    if announce:
        announce(data)
    else:
        print("Sign in to JT Tunnel and approve this device:")
        print(f"  {data['verification_uri']}")
        print(f"Enter this code on the approval page: {data['user_code']}")
    open_browser(data["verification_uri"])
    result = poll_device_token(
        data["device_code"],
        interval=data.get("interval", 5),
        on_wait=on_wait,
    )
    tunnel = result.get("tunnel")
    if isinstance(tunnel, dict):
        save_tunnel_config(tunnel)
    return result["token"]
