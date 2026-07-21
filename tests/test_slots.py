import pytest

from jtunnel.slots import MaxTunnelServicesError, resolve_public_port, resolve_services


def test_resolve_first_free_regardless_of_name():
    assert resolve_public_port("frontend", 9001, 9003) == 9001
    assert resolve_public_port("api", 9004, 9006) == 9004
    assert resolve_public_port("default", 9001, 9003) == 9001


def test_resolve_custom_name_uses_first_free():
    assert resolve_public_port("storybook", 9001, 9003) == 9001
    assert resolve_public_port("admin", 9001, 9003, used_public_ports={9001}) == 9002


def test_resolve_reuses_active_tunnel_port():
    active = {"storybook": {"public_port": 9003, "local_port": 6006}}
    assert resolve_public_port("storybook", 9001, 9003, active, {9001, 9002}) == 9003


def test_resolve_raises_when_block_full():
    used = {9001, 9002, 9003}
    with pytest.raises(MaxTunnelServicesError):
        resolve_public_port("storybook", 9001, 9003, used_public_ports=used)


def test_resolve_services_assigns_distinct_ports():
    result = resolve_services(
        [("default", 5173), ("api", 8000)],
        9001,
        9003,
    )
    assert result == {
        "default": (5173, 9001),
        "api": (8000, 9002),
    }


def test_resolve_services_respects_sticky_and_used():
    active = {"default": {"public_port": 9001, "local_port": 3000}}
    result = resolve_services(
        [("default", 5173), ("api", 8000)],
        9001,
        9003,
        active,
    )
    assert result["default"] == (5173, 9001)
    assert result["api"] == (8000, 9002)


def test_resolve_services_rejects_duplicate_names():
    with pytest.raises(ValueError, match="duplicate"):
        resolve_services([("api", 8000), ("API", 8001)], 9001, 9003)


def test_resolve_services_raises_when_block_full():
    active = {
        "a": {"public_port": 9001},
        "b": {"public_port": 9002},
        "c": {"public_port": 9003},
    }
    with pytest.raises(MaxTunnelServicesError):
        resolve_services([("extra", 9000)], 9001, 9003, active)
