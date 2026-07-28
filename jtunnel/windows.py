"""Windows-specific helpers for firewall hints and connection errors."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

FIREWALL_RULE_NAME = "JT Tunnel"
FIREWALL_SCRIPT_URL = (
    "https://raw.githubusercontent.com/JatraTech/jtunnel-cli/main/scripts/windows-firewall.ps1"
)


def is_windows() -> bool:
    return sys.platform == "win32"


def is_connection_refused(exc: BaseException) -> bool:
    """True for ConnectionRefusedError or Windows WinError 10061."""
    if isinstance(exc, ConnectionRefusedError):
        return True
    if isinstance(exc, OSError):
        # Windows: WSAECONNREFUSED = 10061
        if getattr(exc, "winerror", None) == 10061:
            return True
        if exc.errno in (111, 61):  # ECONNREFUSED on Linux / macOS
            return True
    return False


def default_install_path() -> Path:
    local = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(local) / "jtunnel" / "jtunnel.exe"


def current_exe_path() -> Path:
    """Best-effort path to the running binary (PyInstaller or python -m)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve()
    return default_install_path()


def firewall_fix_command(program_path: Path | None = None) -> str:
    path = program_path or current_exe_path()
    return (
        f'irm {FIREWALL_SCRIPT_URL} -OutFile $env:TEMP\\jtunnel-fw.ps1; '
        f'powershell -ExecutionPolicy Bypass -File $env:TEMP\\jtunnel-fw.ps1 '
        f'-Action Add -ProgramPath "{path}"'
    )


def tunnel_server_refused_hint(tunnel_uri: str) -> str:
    lines = [
        f"Cannot reach JT Tunnel ({tunnel_uri}).",
        "Windows Firewall or antivirus may be blocking jtunnel.exe."
        if is_windows()
        else "A firewall or network policy may be blocking the connection.",
        "Run: jtunnel doctor",
    ]
    if is_windows():
        lines.append(
            "Or add a firewall rule (PowerShell as Administrator):\n"
            f"  {firewall_fix_command()}"
        )
    return "\n".join(lines)


def local_port_refused_hint(port: int) -> str:
    return (
        f"Nothing is listening on 127.0.0.1:{port}.\n"
        "Start your local app first, or check the port with: "
        f"jtunnel expose -p {port}"
    )


def check_firewall_rule(
    program_path: Path | None = None,
    *,
    run_powershell: bool = True,
) -> tuple[bool | None, str]:
    """Return (ok, message). ok is None if the check could not run."""
    if not is_windows():
        return None, "Skipped (not Windows)"
    if not run_powershell:
        return None, "Skipped"

    path = (program_path or current_exe_path()).resolve()
    # PowerShell: find rule by display name, then check program path.
    ps = (
        f"$r = Get-NetFirewallRule -DisplayName '{FIREWALL_RULE_NAME}' "
        f"-ErrorAction SilentlyContinue; "
        f"if (-not $r) {{ Write-Output 'MISSING'; exit 0 }}; "
        f"$apps = $r | Get-NetFirewallApplicationFilter -ErrorAction SilentlyContinue; "
        f"$target = [System.IO.Path]::GetFullPath('{str(path).replace(chr(39), chr(39)+chr(39))}'); "
        f"foreach ($a in $apps) {{ "
        f"  if ($a.Program -and ([System.IO.Path]::GetFullPath($a.Program) -eq $target)) {{ "
        f"    Write-Output 'OK'; exit 0 "
        f"  }} "
        f"}}; "
        f"Write-Output 'MISMATCH'"
    )
    try:
        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                ps,
            ],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, f"Could not query firewall: {exc}"

    out = (result.stdout or "").strip().splitlines()
    status = out[-1].strip() if out else ""
    if status == "OK":
        return True, f"Rule '{FIREWALL_RULE_NAME}' allows {path}"
    if status == "MISSING":
        return False, f"Rule '{FIREWALL_RULE_NAME}' not found"
    if status == "MISMATCH":
        return False, f"Rule '{FIREWALL_RULE_NAME}' exists but points to a different program"
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "unknown error").strip()
        return None, f"Could not query firewall: {err}"
    return None, f"Unexpected firewall check result: {status or '(empty)'}"
