"""Tunnel client errors."""


class TunnelError(Exception):
    """Raised when the tunnel client cannot continue."""


class UserDisconnected(Exception):
    """Raised when the user stops the tunnel with Ctrl+C."""
