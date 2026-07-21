"""Plain ASCII terminal helpers with high-contrast ANSI colors."""

from __future__ import annotations

import os
import re
import sys
from typing import Any

WIDTH = 42
NEST = "  "

# Bright ANSI — readable on Ubuntu dark terminals and PowerShell blue background.
_RESET = "\033[0m"
_BOLD = "\033[1m"
_DIM = "\033[2m"
_RED = "\033[91m"
_GREEN = "\033[92m"
_YELLOW = "\033[93m"
_WHITE = "\033[97m"

_ANSI_RE = re.compile(r"\033\[[0-9;]*m")
_vt_ready = False


def _want_color() -> bool:
    if os.environ.get("TERM", "") == "dumb":
        return False
    return sys.stdout.isatty()


def _enable_windows_vt() -> None:
    """Turn on ANSI processing for Windows CMD / PowerShell."""
    global _vt_ready
    if _vt_ready or sys.platform != "win32":
        _vt_ready = True
        return
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        mode = ctypes.c_uint32()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
            kernel32.SetConsoleMode(handle, mode.value | ENABLE_VIRTUAL_TERMINAL_PROCESSING)
    except Exception:
        pass
    _vt_ready = True


def _c(text: str, *codes: str) -> str:
    if not _want_color():
        return text
    _enable_windows_vt()
    return f"{''.join(codes)}{text}{_RESET}"


def _plain(text: str) -> str:
    return _ANSI_RE.sub("", text)


def is_interactive() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def clear_screen() -> None:
    """Replace previous UI with a fresh frame (interactive TTY only)."""
    if not is_interactive():
        return
    if sys.platform == "win32":
        os.system("cls")
    else:
        sys.stdout.write("\033[2J\033[H")
    sys.stdout.flush()


def _hline(char: str = "-") -> str:
    line = "+" + (char * (WIDTH - 2)) + "+"
    return _c(line, _DIM, _WHITE)


def _row(text: str = "", *styles: str) -> str:
    content = _plain(text)[: WIDTH - 4]
    padded = f"{content:<{WIDTH - 4}}"
    if styles:
        padded = _c(padded, *styles)
    border = _c("|", _DIM, _WHITE)
    return f"{border} {padded} {border}"


def _main_box(title: str, lines: list[str]) -> None:
    """Primary framed panel (app header only)."""
    print(_hline("="))
    print(_row(title, _BOLD, _WHITE))
    if lines:
        print(_hline("-"))
        for line in lines:
            if line == "":
                print(_row(""))
                continue
            style = (_WHITE,)
            lower = line.lower()
            if lower.startswith("status") and "signed in" in lower and "not" not in lower:
                style = (_GREEN,)
            elif lower.startswith("status") and "not signed" in lower:
                style = (_YELLOW,)
            elif lower.startswith("hint"):
                style = (_YELLOW,)
            while line:
                chunk, line = line[: WIDTH - 4], line[WIDTH - 4 :]
                print(_row(chunk, *style))
    print(_hline("="))


def _nested_title(title: str) -> None:
    """Secondary section heading — lighter than the main box."""
    print()
    print(f"{NEST}{_c(f'*** {title} ***', _BOLD, _WHITE)}")
    print(f"{NEST}{_c('-' * (WIDTH - 4), _DIM, _WHITE)}")


def _nested_line(text: str = "", *styles: str) -> None:
    body = _c(text, *styles) if styles and text else text
    print(f"{NEST}{body}")


def print_error(message: str) -> None:
    print(_c(f"Error: {message}", _BOLD, _RED), file=sys.stderr)


def print_success(message: str) -> None:
    print(_c(f"OK: {message}", _BOLD, _GREEN))


def print_info(message: str) -> None:
    print(message)


def pause(message: str = "Press Enter to continue...") -> None:
    if is_interactive():
        try:
            input(_c(message, _DIM, _WHITE))
        except EOFError:
            pass


def prompt_text(prompt: str, *, default: str | None = None) -> str:
    suffix = f" [{default}]" if default is not None else ""
    raw = input(f"{prompt}{suffix}: ").strip()
    if not raw and default is not None:
        return default
    return raw


def prompt_int(prompt: str, *, default: int | None = None) -> int:
    while True:
        suffix = f" [{default}]" if default is not None else ""
        raw = input(f"{prompt}{suffix}: ").strip()
        if not raw and default is not None:
            return default
        try:
            return int(raw)
        except ValueError:
            print(_c("Enter a whole number.", _YELLOW))


def confirm(prompt: str, *, default: bool = False) -> bool:
    hint = "Y/n" if default else "y/N"
    while True:
        raw = input(f"{prompt} ({hint}): ").strip().lower()
        if not raw:
            return default
        if raw in ("y", "yes"):
            return True
        if raw in ("n", "no"):
            return False
        print(_c("Enter y or n.", _YELLOW))


def header_panel(
    *,
    logged_in: bool,
    tunnel: dict[str, Any] | None,
    default_service: str | None = None,
) -> None:
    lines: list[str] = []
    if logged_in and tunnel:
        lines.append("status : signed in")
        lines.append(
            f"ports  : {tunnel['port_start']}-{tunnel['port_end']}"
        )
        host = str(tunnel.get("host", "") or "")
        if host:
            lines.append(f"host   : {host}")
        if default_service:
            lines.append(f"default: {default_service}")
    elif logged_in:
        lines.append("status : signed in")
        lines.append("ports  : not configured")
        if default_service:
            lines.append(f"default: {default_service}")
    else:
        lines.append("status : not signed in")
        lines.append("hint   : choose Login to get started")

    _main_box("JT Tunnel", lines)


def print_tunnels_table(
    entries: list[tuple[str, str, Any]],
    *,
    title: str | None = None,
) -> None:
    _nested_title(title or "Tunnels")
    if not entries:
        _nested_line("(none)", _DIM, _WHITE)
        return
    for name, url, local_port in entries:
        _nested_line(f"* {name}", _BOLD, _WHITE)
        _nested_line(f"  {url}", _WHITE)
        _nested_line(f"  local :{local_port}", _DIM, _WHITE)
        _nested_line("")


def login_code_panel(verification_uri: str, user_code: str) -> None:
    _nested_title("Sign in")
    _nested_line("Open this URL and enter the code:", _WHITE)
    _nested_line("")
    _nested_line(verification_uri, _BOLD, _WHITE)
    _nested_line("")
    _nested_line(f"Code: {user_code}", _BOLD, _YELLOW)
    _nested_line("")


def status_panel(rows: list[tuple[str, str]]) -> None:
    width = max((len(label) for label, _ in rows), default=8)
    _nested_title("Status")
    for label, value in rows:
        _nested_line(f"{label:<{width}} : {value}", _WHITE)
    _nested_line("")


def menu_choice(options: list[str], *, prompt: str = "Choose") -> str:
    """Numbered menu; returns the selected option string."""
    _nested_title("Menu")
    for i, option in enumerate(options, start=1):
        num = _c(f"{i}.", _BOLD, _YELLOW)
        print(f"{NEST}{num} {option}")
    print()
    while True:
        raw = input(f"{NEST}{prompt} (1-{len(options)}): ").strip()
        if raw.isdigit():
            idx = int(raw)
            if 1 <= idx <= len(options):
                return options[idx - 1]
        print(f"{NEST}{_c(f'Enter a number from 1 to {len(options)}.', _YELLOW)}")
