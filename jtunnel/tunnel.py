"""WebSocket control connection orchestration."""

from __future__ import annotations

import asyncio
import json
import sys
from urllib.parse import urljoin

import websockets
from websockets import exceptions as ws_exc

from .config import (
    load_device_token,
    load_tunnel_config,
    public_url,
    save_active_tunnel,
    tunnel_host,
)
from .errors import TunnelError, UserDisconnected
from .http_proxy import HTTPProxy
from .protocol import (
    HEARTBEAT_INTERVAL_SECONDS,
    MAX_CONCURRENT_REQUESTS,
    MAX_WS_MESSAGE_SIZE,
    REQUEST_ID_LEN,
    is_relay_frame,
)
from .ui import print_info, print_tunnels_table
from .ws_relay import WSRelay


def _format_server_error(step: str, error: str) -> str:
    if step == "authentication" and error == "authentication failed":
        return "JT Tunnel rejected your credentials. Run jtunnel login."
    return f"JT Tunnel error during {step}: {error}"


class TunnelClient:
    """Maintains the WebSocket control connection and proxies traffic locally."""

    def __init__(
        self,
        services: dict[str, tuple[int, int]],
        token: str | None = None,
    ) -> None:
        self.services = services
        self.token = token or load_device_token()
        self.ws = None
        self._stop = asyncio.Event()
        self._send_lock = asyncio.Lock()
        self._request_semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
        self._http = HTTPProxy(services)
        self._relay: WSRelay | None = None

    async def run(self) -> None:
        if not self.token:
            raise TunnelError("Not signed in. Run: jtunnel login")

        backoff = 3
        while not self._stop.is_set():
            try:
                await self._connect_and_serve()
                return
            except ws_exc.ConnectionClosed as exc:
                if self._stop.is_set():
                    return
                print(
                    f"Tunnel disconnected: {exc}. Reconnecting in {backoff}s...",
                    file=sys.stderr,
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30)
            except (OSError, ws_exc.WebSocketException) as exc:
                if self._stop.is_set():
                    return
                print(
                    f"Failed to connect to tunnel server: {exc}. "
                    f"Retrying in {backoff}s...",
                    file=sys.stderr,
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30)

    async def _connect_and_serve(self) -> None:
        uri = urljoin(tunnel_host(), "/")
        try:
            self.ws = await websockets.connect(
                uri,
                ping_interval=None,
                ping_timeout=None,
                max_size=MAX_WS_MESSAGE_SIZE,
            )
        except (OSError, ws_exc.WebSocketException) as exc:
            raise TunnelError(f"Cannot reach JT Tunnel ({tunnel_host()}): {exc}") from exc

        self._relay = WSRelay(self.send, self.send_bytes)

        await self.send({"type": "auth", "token": self.token})
        await self._wait_for_ack("authentication")

        await self.send(
            {
                "type": "register",
                "services": [
                    {
                        "name": name,
                        "port": local_port,
                        "public_port": public_port,
                    }
                    for name, (local_port, public_port) in self.services.items()
                ],
            }
        )
        await self._wait_for_ack("service registration")

        entries = []
        for name, (local_port, public_port) in self.services.items():
            save_active_tunnel(name, public_port=public_port, local_port=local_port)
            entries.append((name, public_url(public_port), local_port))
        print_tunnels_table(entries, title="Connected")
        print_info("Press Ctrl+C to disconnect")

        try:
            await asyncio.gather(
                self._read_loop(),
                self._heartbeat_loop(),
                self._wait_stop(),
            )
        finally:
            if self._relay is not None:
                await self._relay.close_all()
            if self.ws is not None:
                await self.ws.close()
                self.ws = None

    async def send(self, payload: dict) -> None:
        if self.ws:
            async with self._send_lock:
                await self.ws.send(json.dumps(payload))

    async def send_bytes(self, data: bytes) -> None:
        if self.ws:
            async with self._send_lock:
                await self.ws.send(data)

    async def _wait_for_ack(self, step: str, timeout: float = 10.0) -> None:
        try:
            raw = await asyncio.wait_for(self.ws.recv(), timeout=timeout)
        except asyncio.TimeoutError as exc:
            raise TunnelError(f"Timed out waiting for {step} response from tunnel server.") from exc
        except ws_exc.ConnectionClosed as exc:
            raise TunnelError(f"Tunnel server closed the connection during {step}: {exc}") from exc

        if isinstance(raw, bytes):
            raise TunnelError(f"Unexpected binary frame during {step}.")

        data = json.loads(raw)
        if data.get("type") == "ack" and data.get("error"):
            raise TunnelError(_format_server_error(step, data["error"]))
        if data.get("type") != "ack":
            raise TunnelError(f"Unexpected server message during {step}: {data}")

    async def _read_loop(self) -> None:
        assert self._relay is not None
        try:
            async for message in self.ws:
                if isinstance(message, str):
                    data = json.loads(message)
                    msg_type = data.get("type")
                    if msg_type == "ws_relay_open":
                        await self._relay.handle_open(data)
                    elif msg_type == "ws_relay_close":
                        await self._relay.handle_close(data)
                    elif msg_type == "ack" and data.get("error"):
                        raise TunnelError(f"Server error: {data['error']}")
                elif isinstance(message, bytes):
                    if is_relay_frame(message):
                        await self._relay.handle_data(message)
                    else:
                        asyncio.create_task(self._handle_request(message))
        except ws_exc.ConnectionClosed:
            raise

    async def _handle_request(self, frame: bytes) -> None:
        if len(frame) < REQUEST_ID_LEN:
            return
        req_id = frame[:REQUEST_ID_LEN].decode("ascii", errors="replace")

        async with self._request_semaphore:
            response_bytes = await self._http.handle(frame, asyncio.get_running_loop())

        out = req_id.encode("ascii") + response_bytes
        try:
            await self.send_bytes(out)
        except ws_exc.ConnectionClosed:
            raise

    async def _heartbeat_loop(self) -> None:
        while not self._stop.is_set():
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=HEARTBEAT_INTERVAL_SECONDS)
            except asyncio.TimeoutError:
                try:
                    await self.send({"type": "heartbeat"})
                except ws_exc.ConnectionClosed:
                    return

    async def _wait_stop(self) -> None:
        await self._stop.wait()

    def stop(self) -> None:
        self._stop.set()


def run(services: dict[str, tuple[int, int]]) -> None:
    """Entry point used by the CLI."""
    if not load_tunnel_config():
        raise TunnelError(
            "No port block configured. Run jtunnel login after an admin assigns your ports."
        )
    client = TunnelClient(services)
    try:
        asyncio.run(client.run())
    except KeyboardInterrupt as exc:
        client.stop()
        print_info("\nDisconnecting...")
        raise UserDisconnected from exc
