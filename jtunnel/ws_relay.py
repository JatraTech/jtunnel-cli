"""WebSocket relay bridging between the tunnel server and local apps."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, Awaitable, Callable

import websockets
from websockets import exceptions as ws_exc

from .protocol import OPCODE_BINARY, OPCODE_TEXT, encode_relay_frame

if TYPE_CHECKING:
    from websockets.asyncio.client import ClientConnection

SendJSON = Callable[[dict[str, Any]], Awaitable[None]]
SendBytes = Callable[[bytes], Awaitable[None]]


class WSRelay:
    """Manages browser-to-local WebSocket relays initiated by the tunnel server."""

    def __init__(self, send_json: SendJSON, send_bytes: SendBytes) -> None:
        self._send_json = send_json
        self._send_bytes = send_bytes
        self._relays: dict[str, ClientConnection] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}

    async def close_all(self) -> None:
        for relay_id in list(self._relays):
            await self.close(relay_id)

    async def handle_open(self, data: dict[str, Any]) -> None:
        relay_id = str(data.get("id") or "")
        port = data.get("port")
        path = data.get("path")
        headers = data.get("headers") or {}

        async def ack(error: str = "") -> None:
            await self._send_json({"type": "ws_relay_ack", "id": relay_id, "error": error})

        if not relay_id or not isinstance(port, int) or not path:
            await ack("missing relay fields")
            return

        header_list = [(str(k), str(v)) for k, v in headers.items() if k and v]
        uri = f"ws://127.0.0.1:{port}{path}"
        try:
            local_ws = await websockets.connect(
                uri,
                additional_headers=header_list,
                ping_interval=None,
                ping_timeout=None,
            )
        except Exception as exc:
            await ack(str(exc))
            return

        self._relays[relay_id] = local_ws
        await ack()
        self._tasks[relay_id] = asyncio.create_task(self._relay_to_server(relay_id, local_ws))

    async def handle_close(self, data: dict[str, Any]) -> None:
        await self.close(str(data.get("id") or ""))

    async def handle_data(self, frame: bytes) -> None:
        from .protocol import decode_relay_frame

        relay_id, opcode, payload = decode_relay_frame(frame)
        local_ws = self._relays.get(relay_id)
        if local_ws is None:
            return
        if opcode == OPCODE_TEXT:
            await local_ws.send(payload.decode("utf-8"))
        else:
            await local_ws.send(payload)

    async def close(self, relay_id: str) -> None:
        task = self._tasks.pop(relay_id, None)
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        local_ws = self._relays.pop(relay_id, None)
        if local_ws is not None:
            await local_ws.close()

    async def _relay_to_server(self, relay_id: str, local_ws: ClientConnection) -> None:
        try:
            async for message in local_ws:
                if isinstance(message, str):
                    frame = encode_relay_frame(relay_id, OPCODE_TEXT, message.encode("utf-8"))
                else:
                    frame = encode_relay_frame(relay_id, OPCODE_BINARY, message)
                await self._send_bytes(frame)
        except asyncio.CancelledError:
            raise
        except ws_exc.ConnectionClosed:
            pass
        finally:
            self._relays.pop(relay_id, None)
            self._tasks.pop(relay_id, None)
            try:
                await local_ws.close()
            except Exception:
                pass
