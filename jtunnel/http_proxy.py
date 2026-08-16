"""Local HTTP forwarding for tunnel ingress requests."""

from __future__ import annotations

import atexit
import http.client
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor

from .protocol import MAX_CONCURRENT_REQUESTS, REQUEST_TIMEOUT_SECONDS
from .windows import is_connection_refused, local_port_refused_hint

EXECUTOR = ThreadPoolExecutor(max_workers=MAX_CONCURRENT_REQUESTS)
atexit.register(EXECUTOR.shutdown, wait=True)
_POOL_LIMIT = 16
# Vite advertises Keep-Alive timeout=5s; reuse a pooled conn within that but
# stay under it. (Stale reuse is retried once on a fresh connection, so a
# slightly longer TTL is safe and rebuilds fewer connections.)
_POOL_TTL_SECONDS = 4

_REQUEST_STRIP = {
    "host",
    "connection",
    "keep-alive",
    "proxy-connection",
    "transfer-encoding",
    "content-length",
    "upgrade",
    "te",
    "trailer",
}

_RESPONSE_STRIP = {
    "connection",
    "keep-alive",
    "proxy-connection",
    "transfer-encoding",
    "upgrade",
    "te",
    "trailer",
}


class HTTPProxy:
    """Forwards streamed HTTP requests to a local port with a keep-alive pool."""

    def __init__(self, services: dict[str, tuple[int, int]]) -> None:
        self.services = services
        self._pools: dict[int, deque[http.client.HTTPConnection]] = {}

    def resolve_port(self, raw_request: bytes) -> int:
        service = (self._extract_host(raw_request) or "default").split(".")[0]
        return self._local_port(service)

    def _local_port(self, service: str) -> int:
        if service in self.services:
            return self.services[service][0]
        if self.services:
            return next(iter(self.services.values()))[0]
        return 8080

    def _extract_host(self, raw_request: bytes) -> str:
        for line in raw_request.split(b"\r\n"):
            if line.lower().startswith(b"host:"):
                return line.split(b":", 1)[1].strip().decode("ascii", errors="replace")
        return ""

    def _parse_request(self, raw_request: bytes, port: int):
        head, sep, body = raw_request.partition(b"\r\n\r\n")
        lines = head.split(b"\r\n")
        first = lines[0].decode("latin-1") if lines else ""
        parts = first.split(" ")
        method = parts[0] if parts else "GET"
        path = parts[1] if len(parts) > 1 else "/"
        headers: dict[str, str] = {}
        for line in lines[1:]:
            if not line:
                continue
            k, _, v = line.decode("latin-1").partition(":")
            key = k.strip()
            if not key or key.lower() in _REQUEST_STRIP:
                continue
            if key.lower() == "host":
                headers[key] = f"127.0.0.1:{port}"
            else:
                headers[key] = v.strip()
        return method, path, headers, body

    def request(self, raw_request: bytes, port: int):
        """Send the request to the local app and return (resp, conn).

        A pooled connection may have been closed by the local app's keep-alive
        timeout; in that case retry once on a fresh connection.
        """
        method, path, headers, body = self._parse_request(raw_request, port)
        conn, from_pool = self._get_conn(port)
        try:
            resp = self._send(method, path, headers, body, conn)
            return resp, conn
        except (http.client.HTTPException, OSError) as exc:
            conn.close()
            if is_connection_refused(exc):
                raise ConnectionError(local_port_refused_hint(port)) from exc
            if from_pool and self._is_stale_error(exc):
                retry_conn = self._new_conn(port)
                try:
                    resp = self._send(method, path, headers, body, retry_conn)
                    return resp, retry_conn
                except (http.client.HTTPException, OSError) as exc2:
                    retry_conn.close()
                    if is_connection_refused(exc2):
                        raise ConnectionError(local_port_refused_hint(port)) from exc2
                    raise
            raise

    def _send(self, method, path, headers, body, conn: http.client.HTTPConnection):
        conn.request(method, path, body=body, headers=headers)
        return conn.getresponse()

    @staticmethod
    def _is_stale_error(exc: BaseException) -> bool:
        return isinstance(
            exc,
            (
                http.client.RemoteDisconnected,
                http.client.BadStatusLine,
                http.client.IncompleteRead,
                ConnectionError,
            ),
        )

    def release(self, port: int, resp, conn: http.client.HTTPConnection, reusable: bool) -> None:
        if reusable and not getattr(resp, "will_close", True):
            pool = self._pools.setdefault(port, deque())
            if len(pool) < _POOL_LIMIT:
                pool.append((conn, time.monotonic()))
                return
        conn.close()

    def response_head(self, resp) -> bytes:
        lines = [f"HTTP/1.1 {resp.status} {resp.reason or ''}".rstrip()]
        for key, value in resp.getheaders():
            if key.lower() in _RESPONSE_STRIP:
                continue
            lines.append(f"{key}: {value}")
        return ("\r\n".join(lines) + "\r\n\r\n").encode("latin-1")

    def close_pools(self) -> None:
        """Close all pooled connections (idle sockets) on shutdown."""
        for pool in self._pools.values():
            while pool:
                conn, _ = pool.popleft()
                try:
                    conn.close()
                except OSError:
                    pass
        self._pools.clear()

    def _new_conn(self, port: int) -> http.client.HTTPConnection:
        return http.client.HTTPConnection("127.0.0.1", port, timeout=REQUEST_TIMEOUT_SECONDS)

    def _get_conn(self, port: int) -> tuple[http.client.HTTPConnection, bool]:
        pool = self._pools.setdefault(port, deque())
        now = time.monotonic()
        while pool:
            conn, pooled_at = pool.popleft()
            if now - pooled_at <= _POOL_TTL_SECONDS and conn.sock is not None:
                return conn, True
            conn.close()
        return self._new_conn(port), False
