import json

import pytest

from jtunnel.config import public_url


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
