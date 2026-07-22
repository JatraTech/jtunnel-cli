"""Local HTTP forwarding for tunnel ingress requests."""

from __future__ import annotations

import http.client
import socket
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO

from .protocol import MAX_CONCURRENT_REQUESTS, REQUEST_ID_LEN, REQUEST_TIMEOUT_SECONDS

_EXECUTOR = ThreadPoolExecutor(max_workers=MAX_CONCURRENT_REQUESTS)


class HTTPProxy:
    """Forwards raw HTTP requests to a local port and returns raw responses."""

    def __init__(self, services: dict[str, tuple[int, int]]) -> None:
        self.services = services

    async def handle(self, frame: bytes, loop) -> bytes:
        if len(frame) < REQUEST_ID_LEN:
            return b""
        raw_request = frame[REQUEST_ID_LEN:]
        try:
            return await loop.run_in_executor(_EXECUTOR, self._sync_forward, raw_request)
        except Exception as exc:
            return self._error_response(str(exc))

    def _sync_forward(self, raw_request: bytes) -> bytes:
        host = self._extract_host(raw_request)
        service = host.split(".")[0] if host else "default"
        port = self._local_port(service)
        prepared = self._prepare_request(raw_request, port)
        with socket.create_connection(("127.0.0.1", port), timeout=REQUEST_TIMEOUT_SECONDS) as sock:
            sock.sendall(prepared)
            return self._read_response(sock)

    def _local_port(self, service: str) -> int:
        if service in self.services:
            return self.services[service][0]
        if self.services:
            return next(iter(self.services.values()))[0]
        return 8080

    def _prepare_request(self, raw_request: bytes, port: int) -> bytes:
        head, sep, body = raw_request.partition(b"\r\n\r\n")
        lines = head.split(b"\r\n")
        if not lines:
            return raw_request

        new_lines = [lines[0]]
        has_host = False
        has_connection = False
        for line in lines[1:]:
            lower = line.lower()
            if lower.startswith(b"host:"):
                new_lines.append(f"Host: 127.0.0.1:{port}".encode())
                has_host = True
            elif lower.startswith(b"connection:"):
                new_lines.append(b"Connection: close")
                has_connection = True
            else:
                new_lines.append(line)

        if not has_host:
            new_lines.append(f"Host: 127.0.0.1:{port}".encode())
        if not has_connection:
            new_lines.append(b"Connection: close")

        return b"\r\n".join(new_lines) + sep + body

    def _read_response(self, sock: socket.socket) -> bytes:
        response = http.client.HTTPResponse(sock)
        response.begin()
        out = BytesIO()
        out.write(f"HTTP/1.1 {response.status} {response.reason}\r\n".encode())
        for header, value in response.getheaders():
            out.write(f"{header}: {value}\r\n".encode())
        out.write(b"\r\n")
        out.write(response.read())
        return out.getvalue()

    def _extract_host(self, raw_request: bytes) -> str:
        for line in raw_request.split(b"\r\n"):
            if line.lower().startswith(b"host:"):
                return line.split(b":", 1)[1].strip().decode("ascii", errors="replace")
        return ""

    @staticmethod
    def _error_response(message: str) -> bytes:
        body = message.encode("utf-8")
        return (
            b"HTTP/1.1 502 Bad Gateway\r\n"
            b"Content-Type: text/plain\r\n"
            + f"Content-Length: {len(body)}\r\n".encode()
            + b"Connection: close\r\n\r\n"
            + body
        )
