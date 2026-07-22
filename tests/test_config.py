import json

import pytest

from jtunnel.config import (
    delete_active_tunnel,
    get_default_service,
    load_active_tunnels,
    public_url,
    save_active_tunnel,
    set_default_service,
)


def test_public_url_uses_public_host(monkeypatch, tmp_path):
    monkeypatch.setattr("jtunnel.config.CONFIG_DIR", tmp_path)
    monkeypatch.setattr("jtunnel.config.PUBLIC_HOST", "jt-tunnel.example.com")

    assert public_url(9001) == "https://jt-tunnel.example.com:9001"


def test_public_url_uses_tunnel_config_host(monkeypatch, tmp_path):
    monkeypatch.setattr("jtunnel.config.CONFIG_DIR", tmp_path)
    (tmp_path / "tunnel.json").write_text(
        json.dumps({"host": "jtunnel.new901.io", "port_start": 9001, "port_end": 9003})
    )

    assert public_url(9002) == "https://jtunnel.new901.io:9002"


def test_delete_active_tunnel_removes_entry(monkeypatch, tmp_path):
    monkeypatch.setattr("jtunnel.config.CONFIG_DIR", tmp_path)
    save_active_tunnel("api", public_port=9001, local_port=8000)
    save_active_tunnel("web", public_port=9002, local_port=3000)

    assert delete_active_tunnel("api") is True
    assert load_active_tunnels() == {
        "web": {
            "public_port": 9002,
            "local_port": 3000,
            "url": "https://jtunnel.new901.io:9002",
        }
    }


def test_delete_active_tunnel_clears_default(monkeypatch, tmp_path):
    monkeypatch.setattr("jtunnel.config.CONFIG_DIR", tmp_path)
    save_active_tunnel("api", public_port=9001, local_port=8000)
    set_default_service("api")

    assert delete_active_tunnel("api") is True
    assert load_active_tunnels() == {}
    assert get_default_service() is None


def test_delete_active_tunnel_missing_returns_false(monkeypatch, tmp_path):
    monkeypatch.setattr("jtunnel.config.CONFIG_DIR", tmp_path)
    assert delete_active_tunnel("missing") is False
