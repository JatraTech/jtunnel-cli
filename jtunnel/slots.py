"""Tunnel service name to public port mapping."""

from __future__ import annotations


class MaxTunnelServicesError(Exception):
    """Raised when all ports in the user's block are in use."""


def resolve_public_port(
    slot: str,
    port_start: int,
    port_end: int,
    active_tunnels: dict | None = None,
    used_public_ports: set[int] | None = None,
) -> int:
    """Map a service name to a public port in the user's allocated block.

    Names are labels only. Reuse a sticky mapping if present; otherwise take
    the first free port in the block.
    """
    normalized = slot.strip().lower()
    if not normalized:
        raise ValueError("service name is required")

    active = active_tunnels or {}
    used = set(used_public_ports or set())

    existing = active.get(normalized)
    if isinstance(existing, dict) and "public_port" in existing:
        return int(existing["public_port"])

    for port in range(port_start, port_end + 1):
        if port not in used:
            return port

    max_services = port_end - port_start + 1
    raise MaxTunnelServicesError(
        f"All {max_services} JT Tunnel slots in use "
        f"(ports {port_start}-{port_end}). Run jtunnel list and stop one."
    )


def resolve_services(
    mappings: list[tuple[str, int]],
    port_start: int,
    port_end: int,
    active_tunnels: dict | None = None,
) -> dict[str, tuple[int, int]]:
    """Resolve multiple (name, local_port) pairs to name → (local_port, public_port).

    Sticky ports are reused per name; newly assigned ports are marked used so
    later services in the same batch get distinct ports.
    """
    if not mappings:
        raise ValueError("at least one service is required")

    active = active_tunnels or {}
    used = {
        int(entry["public_port"])
        for entry in active.values()
        if isinstance(entry, dict) and "public_port" in entry
    }
    resolved: dict[str, tuple[int, int]] = {}
    seen_names: set[str] = set()

    for name, local_port in mappings:
        normalized = name.strip().lower()
        if not normalized:
            raise ValueError("service name is required")
        if normalized in seen_names:
            raise ValueError(f"duplicate service name: {normalized}")
        seen_names.add(normalized)

        public_port = resolve_public_port(
            normalized, port_start, port_end, active, used
        )
        used.add(public_port)
        resolved[normalized] = (int(local_port), public_port)

    return resolved
