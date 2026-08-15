"""Wire protocol constants and frame helpers shared by HTTP proxy and WS relay."""

from __future__ import annotations

REQUEST_ID_LEN = 16
MAX_CONCURRENT_REQUESTS = 128
REQUEST_TIMEOUT_SECONDS = 300
MAX_WS_MESSAGE_SIZE = 32 * 1024 * 1024
RELAY_MARKER = 0x01
RELAY_ID_LEN = 16
OPCODE_TEXT = 1
OPCODE_BINARY = 2
HEARTBEAT_INTERVAL_SECONDS = 25

# Negotiated on the auth message; server rejects mismatches with a clear error.
PROTOCOL_VERSION = 2

# Request stream frames (server -> CLI).
FRAME_REQUEST_HEAD = 0x10
FRAME_REQUEST_BODY = 0x11
FRAME_REQUEST_END = 0x12

# Response stream frames (CLI -> server).
FRAME_RESPONSE_HEAD = 0x20
FRAME_RESPONSE_BODY = 0x21
FRAME_RESPONSE_END = 0x22
FRAME_RESPONSE_ERROR = 0x23

# Body chunk size for local app reads / control-socket frames.
REQUEST_BODY_CHUNK = 64 * 1024


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


def encode_frame(req_id: str, opcode: int, payload: bytes = b"") -> bytes:
    req_bytes = req_id.encode("ascii")
    if len(req_bytes) != REQUEST_ID_LEN:
        raise ValueError(f"invalid request id length {len(req_bytes)}")
    return req_bytes + bytes([opcode]) + payload


def decode_frame(frame: bytes) -> tuple[str, int, bytes]:
    if len(frame) < REQUEST_ID_LEN + 1:
        raise ValueError("frame too short")
    req_id = frame[:REQUEST_ID_LEN].decode("ascii", errors="replace")
    opcode = frame[REQUEST_ID_LEN]
    payload = frame[REQUEST_ID_LEN + 1 :]
    return req_id, opcode, payload
