"""Wire protocol constants and frame helpers shared by HTTP proxy and WS relay."""

from __future__ import annotations

REQUEST_ID_LEN = 16
MAX_CONCURRENT_REQUESTS = 16
RELAY_MARKER = 0x01
RELAY_ID_LEN = 16
OPCODE_TEXT = 1
OPCODE_BINARY = 2
HEARTBEAT_INTERVAL_SECONDS = 25


def encode_relay_frame(relay_id: str, opcode: int, payload: bytes) -> bytes:
    relay_bytes = relay_id.encode("ascii")
    if len(relay_bytes) != RELAY_ID_LEN:
        raise ValueError(f"invalid relay id length {len(relay_bytes)}")
    return bytes([RELAY_MARKER]) + relay_bytes + bytes([opcode]) + payload


def decode_relay_frame(frame: bytes) -> tuple[str, int, bytes]:
    if len(frame) < 1 + RELAY_ID_LEN + 1 or frame[0] != RELAY_MARKER:
        raise ValueError("invalid relay frame")
    relay_id = frame[1 : 1 + RELAY_ID_LEN].decode("ascii")
    opcode = frame[1 + RELAY_ID_LEN]
    payload = frame[1 + RELAY_ID_LEN + 1 :]
    return relay_id, opcode, payload


def is_relay_frame(frame: bytes) -> bool:
    return bool(frame) and frame[0] == RELAY_MARKER
