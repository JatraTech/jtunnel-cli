"""WebSocket control connection orchestration."""

from __future__ import annotations

import asyncio
import json
import socket
import sys
from urllib.parse import urlparse

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
from .http_proxy import EXECUTOR, HTTPProxy
from .protocol import (
    FRAME_REQUEST_BODY,
    FRAME_REQUEST_END,
    FRAME_REQUEST_HEAD,
    FRAME_RESPONSE_BODY,
    FRAME_RESPONSE_END,
    FRAME_RESPONSE_ERROR,
    FRAME_RESPONSE_HEAD,
    HEARTBEAT_INTERVAL_SECONDS,
    MAX_CONCURRENT_REQUESTS,
    MAX_WS_MESSAGE_SIZE,
    PROTOCOL_VERSION,
    REQUEST_BODY_CHUNK,
    REQUEST_ID_LEN,
    encode_frame,
    is_relay_frame,
)
from .ui import print_info, print_tunnels_table
from .windows import is_connection_refused, tunnel_server_refused_hint
from .ws_relay import WSRelay

_SOCKET_BUFFER_SIZE = 1024 * 1024
_DNS_CACHE: dict[str, str] = {}


def _resolve_host(host: str) -> str:
    cached = _DNS_CACHE.get(host)
    if cached:
        return cached
    try:
        infos = socket.getaddrinfo(host, None, socket.AF_INET, socket.SOCK_STREAM)
        if infos:
            ip = infos[0][4][0]
            _DNS_CACHE[host] = ip
            return ip
    except OSError:
        pass
    return host


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
                cause = exc.__cause__ or exc.__context__
                if is_connection_refused(exc) or (
                    cause is not None and is_connection_refused(cause)
                ):
                    raise TunnelError(tunnel_server_refused_hint(tunnel_host())) from exc
                print(
                    f"Failed to connect to tunnel server: {exc}. "
                    f"Retrying in {backoff}s...",
                    file=sys.stderr,
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30)

    async def _connect_and_serve(self) -> None:
        uri = tunnel_host()
        if not (uri.startswith("ws://") or uri.startswith("wss://")):
            uri = "wss://" + uri
        try:
            self.ws = await _connect_tunnel(uri)
        except (OSError, ws_exc.WebSocketException) as exc:
            cause = exc.__cause__ or exc.__context__
            if is_connection_refused(exc) or (
                cause is not None and is_connection_refused(cause)
            ):
                raise TunnelError(tunnel_server_refused_hint(tunnel_host())) from exc
            raise TunnelError(f"Cannot reach JT Tunnel ({tunnel_host()}): {exc}") from exc

        self._relay = WSRelay(self.send, self.send_bytes)

        await self.send({"type": "auth", "token": self.token, "proto": PROTOCOL_VERSION})
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
        pending: dict[str, bytearray] = {}
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
                        self._handle_request_frame(message, pending)
        except ws_exc.ConnectionClosed:
            raise

    def _handle_request_frame(self, frame: bytes, pending: dict[str, bytearray]) -> None:
        if len(frame) < REQUEST_ID_LEN + 1:
            return
        req_id = frame[:REQUEST_ID_LEN].decode("ascii", errors="replace")
        opcode = frame[REQUEST_ID_LEN]
        payload = frame[REQUEST_ID_LEN + 1 :]

        if opcode == FRAME_REQUEST_HEAD:
            pending[req_id] = bytearray(payload)
        elif opcode == FRAME_REQUEST_BODY:
            buf = pending.get(req_id)
            if buf is None:
                return
            buf += payload
        elif opcode == FRAME_REQUEST_END:
            buf = pending.pop(req_id, None)
            if buf is None:
                return
            asyncio.create_task(self._handle_request(req_id, bytes(buf)))

    async def _handle_request(self, req_id: str, raw_request: bytes) -> None:
        loop = asyncio.get_running_loop()
        port = self._http.resolve_port(raw_request)

        async with self._request_semaphore:
            try:
                resp, conn = await loop.run_in_executor(
                    EXECUTOR, self._http.request, raw_request, port
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                # Local app failure must surface as a 502, never as a
                # dangling task exception.
                try:
                    await self.send_bytes(
                        encode_frame(req_id, FRAME_RESPONSE_ERROR, str(exc).encode("utf-8"))
                    )
                except ws_exc.ConnectionClosed:
                    pass
                return

            try:
                head = await loop.run_in_executor(EXECUTOR, self._http.response_head, resp)
                # Head goes first so the browser gets status+headers as soon as
                # the tunnel round trip completes; the body streams behind it.
                await self.send_bytes(encode_frame(req_id, FRAME_RESPONSE_HEAD, head))
                first = await loop.run_in_executor(EXECUTOR, resp.read, REQUEST_BODY_CHUNK)
                if first:
                    await self.send_bytes(encode_frame(req_id, FRAME_RESPONSE_BODY, first))

                while True:
                    chunk = await loop.run_in_executor(EXECUTOR, resp.read, REQUEST_BODY_CHUNK)
                    if not chunk:
                        break
                    await self.send_bytes(encode_frame(req_id, FRAME_RESPONSE_BODY, chunk))

                await self.send_bytes(encode_frame(req_id, FRAME_RESPONSE_END))
                self._http.release(port, resp, conn, reusable=True)
            except asyncio.CancelledError:
                self._http.release(port, resp, conn, reusable=False)
                raise
            except Exception as exc:
                self._http.release(port, resp, conn, reusable=False)
                try:
                    await self.send_bytes(
                        encode_frame(req_id, FRAME_RESPONSE_ERROR, str(exc).encode("utf-8"))
                    )
                except ws_exc.ConnectionClosed:
                    pass

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
        self._http.close_pools()


async def _connect_tunnel(uri: str):
    """Connect to the control WebSocket with DNS caching and TCP tuning."""
    parsed = urlparse(uri)
    host = parsed.hostname or ""
    port = parsed.port or (443 if parsed.scheme == "wss" else 80)
    ip = _resolve_host(host)
    sock = socket.create_connection((ip, port), timeout=30)
    try:
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, _SOCKET_BUFFER_SIZE)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, _SOCKET_BUFFER_SIZE)
    except OSError:
        pass
    return await websockets.connect(
        uri,
        sock=sock,
        ping_interval=None,
        ping_timeout=None,
        max_size=MAX_WS_MESSAGE_SIZE,
    )


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
