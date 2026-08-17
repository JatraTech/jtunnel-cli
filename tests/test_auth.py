"""Tests for JT Tunnel device-code login client."""

from unittest.mock import MagicMock, patch

import pytest

from jtunnel.auth import EXPIRED_GRACE_SECONDS, open_browser, poll_device_token


def test_poll_retries_expired_during_grace_period():
    responses = [
        MagicMock(status_code=400, json=lambda: {"error": "authorization_expired"}),
        MagicMock(status_code=400, json=lambda: {"error": "authorization_expired"}),
        MagicMock(
            status_code=200,
            json=lambda: {"token": "jwt-token", "tunnel": {"port_start": 9001}},
        ),
    ]

    with (
        patch("jtunnel.auth.httpx.post", side_effect=responses) as post_mock,
        patch("jtunnel.auth.time.sleep"),
        patch("jtunnel.auth.time.time", side_effect=[0, 1, 2, 3]),
    ):
        result = poll_device_token("device-code", interval=0)

    assert result["token"] == "jwt-token"
    assert post_mock.call_count == 3


def test_poll_raises_expired_after_grace_period():
    response = MagicMock(
        status_code=400, json=lambda: {"error": "authorization_expired"}
    )

    with (
        patch("jtunnel.auth.httpx.post", return_value=response),
        patch("jtunnel.auth.time.sleep"),
        patch(
            "jtunnel.auth.time.time",
            side_effect=[0, EXPIRED_GRACE_SECONDS + 1],
        ),
        pytest.raises(TimeoutError, match="Approval code expired"),
    ):
        poll_device_token("device-code", interval=0)


def test_open_browser_uses_cmd_start_on_windows():
    with (
        patch("jtunnel.auth.is_windows", return_value=True),
        patch("jtunnel.auth._running_in_wsl", return_value=False),
        patch("jtunnel.auth._open_windows_browser", return_value=True) as open_mock,
        patch("jtunnel.auth.webbrowser.open") as webbrowser_open,
    ):
        open_browser("https://admin.example.test/tunnel/verify/?user_code=ABCD1234")

    open_mock.assert_called_once_with(
        "https://admin.example.test/tunnel/verify/?user_code=ABCD1234"
    )
    webbrowser_open.assert_not_called()


def test_open_browser_falls_back_to_webbrowser_when_cmd_start_unavailable():
    with (
        patch("jtunnel.auth.is_windows", return_value=True),
        patch("jtunnel.auth._running_in_wsl", return_value=False),
        patch("jtunnel.auth._open_windows_browser", return_value=False),
        patch("jtunnel.auth.webbrowser.open") as webbrowser_open,
    ):
        open_browser("https://admin.example.test/tunnel/verify/")

    webbrowser_open.assert_called_once_with("https://admin.example.test/tunnel/verify/")
