"""Tests for doctor checks and Windows connection-refused helpers."""

from __future__ import annotations

import errno

import pytest

from jtunnel.doctor import CheckResult, print_report, run_checks
from jtunnel.windows import (
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
    assert "windows-firewall.ps1" in msg


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
