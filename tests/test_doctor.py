"""Tests for doctor checks and Windows connection-refused helpers."""

from __future__ import annotations

import errno
from pathlib import Path
from unittest.mock import MagicMock


from jtunnel.doctor import CheckResult, print_report, run_checks, run_doctor
from jtunnel.windows import (
    _netsh_firewall_status,
    _powershell_firewall_status,
    add_firewall_rule,
    check_firewall_rule,
    firewall_fix_command,
    firewall_rule_status,
    is_connection_refused,
    local_port_refused_hint,
    tunnel_server_refused_hint,
)


def test_is_connection_refused_connection_refused_error():
    assert is_connection_refused(ConnectionRefusedError())


def test_is_connection_refused_errno():
    assert is_connection_refused(OSError(errno.ECONNREFUSED, "refused"))


def test_is_connection_refused_winerror():
    exc = OSError("refused")
    exc.winerror = 10061
    assert is_connection_refused(exc)


def test_is_connection_refused_other():
    assert not is_connection_refused(OSError(errno.ETIMEDOUT, "timeout"))
    assert not is_connection_refused(ValueError("nope"))


def test_local_port_refused_hint():
    msg = local_port_refused_hint(5173)
    assert "127.0.0.1:5173" in msg
    assert "jtunnel expose -p 5173" in msg


def test_firewall_fix_command_recommends_doctor_flag():
    assert firewall_fix_command() == "jtunnel doctor --fix-firewall"


def test_tunnel_server_refused_hint_mentions_doctor(monkeypatch):
    monkeypatch.setattr("jtunnel.windows.is_windows", lambda: False)
    msg = tunnel_server_refused_hint("wss://jtunnel.new901.io")
    assert "wss://jtunnel.new901.io" in msg
    assert "jtunnel doctor" in msg
    assert "Windows Firewall" not in msg


def test_tunnel_server_refused_hint_windows(monkeypatch):
    monkeypatch.setattr("jtunnel.windows.is_windows", lambda: True)
    msg = tunnel_server_refused_hint("wss://jtunnel.new901.io")
    assert "Windows Firewall" in msg
    assert "jtunnel doctor" in msg
    assert "--fix-firewall" in msg


def test_powershell_firewall_status_ok(monkeypatch):
    monkeypatch.setattr("jtunnel.windows.is_windows", lambda: True)

    def fake_run(args, **kwargs):
        assert "Import-Module NetSecurity" in args[-1]
        result = MagicMock()
        result.stdout = "OK\n"
        result.returncode = 0
        return result

    monkeypatch.setattr("jtunnel.windows.subprocess.run", fake_run)
    assert _powershell_firewall_status(Path("C:/jtunnel/jtunnel.exe")) == "OK"


def test_powershell_firewall_status_missing(monkeypatch):
    monkeypatch.setattr("jtunnel.windows.is_windows", lambda: True)

    def fake_run(args, **kwargs):
        result = MagicMock()
        result.stdout = "MISSING\n"
        result.returncode = 0
        return result

    monkeypatch.setattr("jtunnel.windows.subprocess.run", fake_run)
    assert _powershell_firewall_status(Path("C:/jtunnel/jtunnel.exe")) == "MISSING"


def test_netsh_firewall_status_ok(monkeypatch, tmp_path):
    exe = tmp_path / "jtunnel.exe"
    exe.write_text("x")

    def fake_run(args, **kwargs):
        result = MagicMock()
        result.stdout = f'Program={exe}\n'
        result.returncode = 0
        return result

    monkeypatch.setattr("jtunnel.windows.subprocess.run", fake_run)
    assert _netsh_firewall_status(exe) == "OK"


def test_netsh_firewall_status_missing(monkeypatch):
    def fake_run(args, **kwargs):
        result = MagicMock()
        result.stdout = "No rules match the specified criteria.\n"
        result.returncode = 0
        return result

    monkeypatch.setattr("jtunnel.windows.subprocess.run", fake_run)
    assert _netsh_firewall_status(Path("C:/jtunnel/jtunnel.exe")) == "MISSING"


def test_firewall_rule_status_falls_back_to_netsh(monkeypatch):
    path = Path("C:/jtunnel/jtunnel.exe")
    monkeypatch.setattr("jtunnel.windows.is_windows", lambda: True)

    def fake_ps(path_arg):
        return "MISSING"

    def fake_netsh(path_arg):
        return "OK"

    monkeypatch.setattr("jtunnel.windows._powershell_firewall_status", fake_ps)
    monkeypatch.setattr("jtunnel.windows._netsh_firewall_status", fake_netsh)
    assert firewall_rule_status(path) == "OK"


def test_check_firewall_rule_inconclusive(monkeypatch):
    monkeypatch.setattr("jtunnel.windows.is_windows", lambda: True)
    monkeypatch.setattr("jtunnel.windows.firewall_rule_status", lambda *a, **k: "ERROR")

    ok, detail = check_firewall_rule()
    assert ok is None
    assert "Could not query firewall" in detail


def test_add_firewall_rule_success(monkeypatch, tmp_path):
    exe = tmp_path / "jtunnel.exe"
    exe.write_text("x")
    monkeypatch.setattr("jtunnel.windows.is_windows", lambda: True)
    monkeypatch.setattr("jtunnel.windows._download_firewall_script", lambda dest: dest.write_text("x"))

    def fake_run(args, **kwargs):
        result = MagicMock()
        result.returncode = 0
        result.stdout = ""
        result.stderr = ""
        return result

    monkeypatch.setattr("jtunnel.windows.subprocess.run", fake_run)
    ok, message = add_firewall_rule(exe)
    assert ok is True
    assert "added" in message.lower()


def test_run_checks_reachability(monkeypatch, tmp_path):
    monkeypatch.setattr("jtunnel.config.CONFIG_DIR", tmp_path)
    monkeypatch.setattr("jtunnel.doctor.is_windows", lambda: False)

    def connect(host: str, port: int, timeout: float) -> bool:
        if host == "127.0.0.1":
            return port == 5173
        return host in ("admin.new901.io", "jtunnel.new901.io") and port == 443

    results = run_checks(local_port=5173, connect=connect)
    by_name = {r.name: r for r in results}

    assert by_name["Signed in"].ok is False
    assert by_name["Admin API"].ok is True
    assert by_name["Tunnel server"].ok is True
    assert by_name["Local app"].ok is True
    assert "Windows Firewall" not in by_name


def test_run_checks_tunnel_unreachable(monkeypatch, tmp_path):
    monkeypatch.setattr("jtunnel.config.CONFIG_DIR", tmp_path)
    monkeypatch.setattr("jtunnel.doctor.is_windows", lambda: False)

    def connect(host: str, port: int, timeout: float) -> bool:
        return host == "admin.new901.io"

    results = run_checks(connect=connect)
    by_name = {r.name: r for r in results}
    assert by_name["Admin API"].ok is True
    assert by_name["Tunnel server"].ok is False


def test_run_checks_firewall_missing(monkeypatch, tmp_path):
    monkeypatch.setattr("jtunnel.config.CONFIG_DIR", tmp_path)
    monkeypatch.setattr("jtunnel.doctor.is_windows", lambda: True)

    def connect(host: str, port: int, timeout: float) -> bool:
        return True

    results = run_checks(
        connect=connect,
        firewall_check=lambda: (False, "Rule 'JT Tunnel' not found"),
    )
    by_name = {r.name: r for r in results}
    assert by_name["Windows Firewall"].ok is False
    assert by_name["Windows Firewall"].critical is True


def test_run_checks_firewall_inconclusive_not_critical(monkeypatch, tmp_path):
    monkeypatch.setattr("jtunnel.config.CONFIG_DIR", tmp_path)
    monkeypatch.setattr("jtunnel.doctor.is_windows", lambda: True)

    results = run_checks(
        firewall_check=lambda: (None, "Could not query firewall rule"),
    )
    fw = next(r for r in results if r.name == "Windows Firewall")
    assert fw.ok is None
    assert fw.critical is False


def test_print_report_suggests_fix_firewall(capsys, monkeypatch):
    monkeypatch.setattr("jtunnel.doctor.is_windows", lambda: True)
    results = [
        CheckResult(
            name="Windows Firewall",
            ok=False,
            detail="Rule 'JT Tunnel' not found",
            critical=True,
        )
    ]
    assert print_report(results) is False
    out = capsys.readouterr().out
    assert "--fix-firewall" in out


def test_print_report_inconclusive_firewall_passes(capsys, monkeypatch):
    monkeypatch.setattr("jtunnel.doctor.is_windows", lambda: True)
    results = [
        CheckResult(
            name="Windows Firewall",
            ok=None,
            detail="Could not query firewall rule",
            critical=False,
        ),
        CheckResult(name="Tunnel server", ok=True, detail="ok", critical=True),
    ]
    assert print_report(results) is True
    out = capsys.readouterr().out
    assert "could not be confirmed" in out.lower()


def test_print_report_fails_on_critical(capsys, monkeypatch):
    monkeypatch.setattr("jtunnel.doctor.is_windows", lambda: False)
    results = [
        CheckResult(name="Tunnel server", ok=False, detail="down", critical=True),
        CheckResult(name="Signed in", ok=False, detail="no", critical=False),
    ]
    assert print_report(results) is False
    out = capsys.readouterr().out
    assert "FAIL" in out or "failed" in out.lower()


def test_print_report_passes(capsys, monkeypatch):
    monkeypatch.setattr("jtunnel.doctor.is_windows", lambda: False)
    results = [
        CheckResult(name="Tunnel server", ok=True, detail="ok", critical=True),
        CheckResult(name="Signed in", ok=False, detail="no", critical=False),
    ]
    assert print_report(results) is True
    out = capsys.readouterr().out
    assert "passed" in out.lower()


def test_run_doctor_fix_firewall_non_windows(monkeypatch):
    monkeypatch.setattr("jtunnel.doctor.is_windows", lambda: False)
    assert run_doctor(fix_firewall=True) is False


def test_run_doctor_fix_firewall_then_checks(monkeypatch, tmp_path):
    monkeypatch.setattr("jtunnel.config.CONFIG_DIR", tmp_path)
    monkeypatch.setattr("jtunnel.doctor.is_windows", lambda: True)
    monkeypatch.setattr(
        "jtunnel.doctor.add_firewall_rule",
        lambda *a, **k: (True, "Firewall rule added"),
    )
    monkeypatch.setattr(
        "jtunnel.doctor.check_firewall_rule",
        lambda *a, **k: (True, "Rule 'JT Tunnel' allows"),
    )

    def connect(host: str, port: int, timeout: float) -> bool:
        return host in ("admin.new901.io", "jtunnel.new901.io")

    monkeypatch.setattr(
        "jtunnel.doctor.run_checks",
        lambda **kwargs: run_checks(connect=connect, firewall_check=lambda: (True, "ok")),
    )

    assert run_doctor(fix_firewall=True) is True
