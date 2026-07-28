"""Windows-specific helpers for firewall hints and connection errors."""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Literal

FirewallStatus = Literal["OK", "MISSING", "MISMATCH", "ERROR"]

FIREWALL_RULE_NAME = "JT Tunnel"
FIREWALL_SCRIPT_URL = (
    "https://raw.githubusercontent.com/JatraTech/jtunnel-cli/main/scripts/windows-firewall.ps1"
)


def is_windows() -> bool:
    return sys.platform == "win32"


def powershell_exe() -> str:
    system_root = os.environ.get("SystemRoot", r"C:\Windows")
    return str(
        Path(system_root) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    )


def _ps_escape_single_quoted(value: str) -> str:
    return value.replace("'", "''")


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
    _ = program_path or current_exe_path()
    return "jtunnel doctor --fix-firewall"


def tunnel_server_refused_hint(tunnel_uri: str) -> str:
    lines = [
        f"Cannot reach JT Tunnel ({tunnel_uri}).",
        "Windows Firewall or antivirus may be blocking jtunnel.exe."
        if is_windows()
        else "A firewall or network policy may be blocking the connection.",
        "Run: jtunnel doctor",
    ]
    if is_windows():
        lines.append(f"Or add a firewall rule: {firewall_fix_command()}")
    return "\n".join(lines)


def local_port_refused_hint(port: int) -> str:
    return (
        f"Nothing is listening on 127.0.0.1:{port}.\n"
        "Start your local app first, or check the port with: "
        f"jtunnel expose -p {port}"
    )


def _powershell_firewall_status(path: Path) -> FirewallStatus:
    target = _ps_escape_single_quoted(str(path))
    rule_name = _ps_escape_single_quoted(FIREWALL_RULE_NAME)
    ps = (
        f"Import-Module NetSecurity -ErrorAction Stop; "
        f"$r = Get-NetFirewallRule -DisplayName '{rule_name}' -ErrorAction SilentlyContinue; "
        f"if (-not $r) {{ Write-Output 'MISSING'; exit 0 }}; "
        f"$apps = $r | Get-NetFirewallApplicationFilter -ErrorAction SilentlyContinue; "
        f"$target = [System.IO.Path]::GetFullPath('{target}'); "
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
                powershell_exe(),
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
    except (OSError, subprocess.TimeoutExpired):
        return "ERROR"

    out = (result.stdout or "").strip().splitlines()
    status = out[-1].strip() if out else ""
    if status in ("OK", "MISSING", "MISMATCH"):
        return status  # type: ignore[return-value]
    return "ERROR"


def _netsh_firewall_status(path: Path) -> FirewallStatus:
    try:
        result = subprocess.run(
            [
                "netsh",
                "advfirewall",
                "firewall",
                "show",
                "rule",
                f"name={FIREWALL_RULE_NAME}",
                "verbose",
            ],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "ERROR"

    output = result.stdout or ""
    if "No rules match the specified criteria" in output:
        return "MISSING"

    target = str(path.resolve()).lower()
    program_lines = [
        line.strip()
        for line in output.splitlines()
        if line.strip().lower().startswith("program=")
    ]
    if not program_lines:
        return "ERROR"

    for line in program_lines:
        program = line.split("=", 1)[1].strip().strip('"')
        if program and Path(program).resolve() == path.resolve():
            return "OK"

    return "MISMATCH"


def firewall_rule_status(
    program_path: Path | None = None,
    *,
    run_powershell: bool = True,
    run_netsh: bool = True,
) -> FirewallStatus:
    """Return firewall rule status for the given program path."""
    if not is_windows():
        return "ERROR"

    path = (program_path or current_exe_path()).resolve()
    ps_status: FirewallStatus | None = None
    if run_powershell:
        ps_status = _powershell_firewall_status(path)

    if ps_status in ("OK", "MISMATCH"):
        return ps_status
    if ps_status == "MISSING":
        if run_netsh:
            netsh_status = _netsh_firewall_status(path)
            if netsh_status != "ERROR":
                return netsh_status
        return "MISSING"

    if run_netsh:
        netsh_status = _netsh_firewall_status(path)
        if netsh_status != "ERROR":
            return netsh_status

    return "ERROR"


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
    status = firewall_rule_status(path, run_powershell=run_powershell)

    if status == "OK":
        return True, f"Rule '{FIREWALL_RULE_NAME}' allows {path}"
    if status == "MISSING":
        return False, f"Rule '{FIREWALL_RULE_NAME}' not found"
    if status == "MISMATCH":
        return False, f"Rule '{FIREWALL_RULE_NAME}' exists but points to a different program"
    return None, "Could not query firewall rule (try running as a normal user in PowerShell)"


def _download_firewall_script(dest: Path) -> None:
    import urllib.request

    dest.parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(FIREWALL_SCRIPT_URL, dest)


def add_firewall_rule(program_path: Path | None = None) -> tuple[bool, str]:
    """Add the outbound firewall rule, prompting for UAC if needed."""
    if not is_windows():
        return False, "Not supported on this platform"

    path = (program_path or current_exe_path()).resolve()
    if not path.exists():
        return False, f"Program not found: {path}"

    fw_script = Path(tempfile.gettempdir()) / "jtunnel-fw.ps1"
    try:
        _download_firewall_script(fw_script)
    except OSError as exc:
        return False, f"Could not download firewall script: {exc}"

    ps_script = _ps_escape_single_quoted(str(fw_script))
    ps_program = _ps_escape_single_quoted(str(path))
    ps = (
        f"$fw = '{ps_script}'; "
        f"$exe = '{ps_program}'; "
        f"$proc = Start-Process -FilePath '{_ps_escape_single_quoted(powershell_exe())}' "
        f"-Verb RunAs -Wait -PassThru -ArgumentList @("
        f"'-NoProfile','-ExecutionPolicy','Bypass','-File',$fw,'-Action','Add','-ProgramPath',$exe"
        f"); exit $proc.ExitCode"
    )
    try:
        result = subprocess.run(
            [
                powershell_exe(),
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                ps,
            ],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"Could not add firewall rule: {exc}"
    finally:
        if fw_script.exists():
            fw_script.unlink(missing_ok=True)

    if result.returncode == 0:
        return True, f"Firewall rule added for {path}"

    detail = (result.stderr or result.stdout or "UAC declined or script failed").strip()
    detail = re.sub(r"\s+", " ", detail)
    return False, f"Could not add firewall rule: {detail or 'unknown error'}"
