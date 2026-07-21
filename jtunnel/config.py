"""Configuration helpers for the JT Tunnel CLI."""

import base64
import binascii
import json
from pathlib import Path
from typing import Any

API_BASE = "https://admin.new901.io"
TUNNEL_HOST = "wss://jtunnel.new901.io"
PUBLIC_HOST = "jtunnel.new901.io"
CONFIG_DIR = Path("~/.config/jtunnel").expanduser()


def api_base() -> str:
    return API_BASE.rstrip("/")


def tunnel_host() -> str:
    return TUNNEL_HOST.rstrip("/")


def public_host() -> str:
    tunnel = load_tunnel_config()
    if tunnel and tunnel.get("host"):
        return str(tunnel["host"]).strip().lower().rstrip(".")
    return PUBLIC_HOST.strip().lower().rstrip(".")


def decode_token_claims(token: str | None) -> dict[str, Any] | None:
    if not token:
        return None
    try:
        payload = token.split(".")[1]
        padding = "=" * (-len(payload) % 4)
        claims = json.loads(base64.urlsafe_b64decode(payload + padding))
    except (IndexError, ValueError, TypeError, binascii.Error, json.JSONDecodeError):
        return None
    return claims if isinstance(claims, dict) else None


def tunnel_config_from_token(token: str | None) -> dict[str, Any] | None:
    claims = decode_token_claims(token)
    if not claims:
        return None
    port_start = claims.get("port_start")
    port_end = claims.get("port_end")
    if not isinstance(port_start, int) or not isinstance(port_end, int):
        return None
    host = claims.get("tunnel_host")
    if not isinstance(host, str) or not host.strip():
        host = public_host()
    return {
        "host": host.strip().lower().rstrip("."),
        "port_start": port_start,
        "port_end": port_end,
    }


def public_url(public_port: int) -> str:
    return f"https://{public_host()}:{public_port}"


def config_dir() -> Path:
    path = CONFIG_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def device_token_path() -> Path:
    return config_dir() / "device.jwt"


def tunnel_config_path() -> Path:
    return config_dir() / "tunnel.json"


def tunnels_state_path() -> Path:
    return config_dir() / "tunnels.json"


def preferences_path() -> Path:
    return config_dir() / "preferences.json"


def load_device_token() -> str | None:
    path = device_token_path()
    if path.exists():
        return path.read_text().strip()
    return None


def save_device_token(token: str) -> None:
    device_token_path().write_text(token)


def clear_device_token() -> None:
    path = device_token_path()
    if path.exists():
        path.unlink()


def save_tunnel_config(config: dict[str, Any]) -> None:
    tunnel_config_path().write_text(json.dumps(config, indent=2) + "\n")


def load_tunnel_config() -> dict[str, Any] | None:
    path = tunnel_config_path()
    if not path.exists():
        token = load_device_token()
        return tunnel_config_from_token(token)
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def load_active_tunnels() -> dict[str, dict[str, Any]]:
    path = tunnels_state_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_active_tunnel(
    name: str,
    *,
    public_port: int,
    local_port: int,
) -> None:
    tunnels = load_active_tunnels()
    tunnels[name] = {
        "public_port": public_port,
        "local_port": local_port,
        "url": public_url(public_port),
    }
    tunnels_state_path().write_text(json.dumps(tunnels, indent=2) + "\n")
    set_default_service(name)


def clear_active_tunnels() -> None:
    path = tunnels_state_path()
    if path.exists():
        path.unlink()
    clear_default_service()


def load_preferences() -> dict[str, Any]:
    path = preferences_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_preferences(prefs: dict[str, Any]) -> None:
    preferences_path().write_text(json.dumps(prefs, indent=2) + "\n")


def get_default_service() -> str | None:
    name = load_preferences().get("default_service")
    if not isinstance(name, str) or not name.strip():
        return None
    return name.strip().lower()


def set_default_service(name: str) -> None:
    prefs = load_preferences()
    prefs["default_service"] = name.strip().lower()
    save_preferences(prefs)


def clear_default_service() -> None:
    prefs = load_preferences()
    if "default_service" not in prefs:
        return
    prefs.pop("default_service", None)
    if prefs:
        save_preferences(prefs)
    else:
        path = preferences_path()
        if path.exists():
            path.unlink()


def get_default_tunnel_entry() -> tuple[str, dict[str, Any]] | None:
    """Return (name, entry) for the default saved tunnel, if available."""
    tunnels = load_active_tunnels()
    if not tunnels:
        return None
    default = get_default_service()
    if default and isinstance(tunnels.get(default), dict):
        return default, tunnels[default]
    # Fall back to a single saved tunnel, or none if multiple without a default.
    if len(tunnels) == 1:
        name, entry = next(iter(tunnels.items()))
        if isinstance(entry, dict):
            return name, entry
    return None
