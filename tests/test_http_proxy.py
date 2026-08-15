import http.server
import threading

import pytest

from jtunnel.http_proxy import HTTPProxy


class MockHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def do_GET(self):
        body = b"hello world"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("ETag", '"abc"')
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        data = self.rfile.read(length)
        self.send_response(200)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


@pytest.fixture
def server():
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), MockHandler)
    port = srv.server_address[1]
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    yield port
    srv.shutdown()
    thread.join(timeout=2)


def _proxy(port):
    return HTTPProxy({"default": (port, 0)})


def test_request_and_stream(server):
    proxy = _proxy(server)
    raw = b"GET / HTTP/1.1\r\nHost: default.local\r\n\r\n"
    resp, conn = proxy.request(raw, server)
    head = proxy.response_head(resp)
    assert b"200 OK" in head
    assert b'ETag: "abc"' in head
    assert b"Content-Length: 11" in head

    first = resp.read(4)
    rest = resp.read(100)
    assert first + rest == b"hello world"
    proxy.release(server, resp, conn, reusable=True)


def test_post_echo(server):
    proxy = _proxy(server)
    body = b"x" * 100000
    raw = (
        f"POST /echo HTTP/1.1\r\nHost: default.local\r\nContent-Length: {len(body)}\r\n\r\n"
        .encode()
        + body
    )
    resp, conn = proxy.request(raw, server)
    assert resp.read() == body
    proxy.release(server, resp, conn, reusable=True)


def test_connection_reuse(server):
    proxy = _proxy(server)
    raw = b"GET / HTTP/1.1\r\nHost: default.local\r\n\r\n"

    resp, conn = proxy.request(raw, server)
    resp.read()
    proxy.release(server, resp, conn, reusable=True)

    resp2, conn2 = proxy.request(raw, server)
    assert conn2 is conn
    resp2.read()
    proxy.release(server, resp2, conn2, reusable=True)


def test_resolve_port(server):
    proxy = _proxy(server)
    assert proxy.resolve_port(b"GET / HTTP/1.1\r\nHost: default.local\r\n\r\n") == server
    assert proxy.resolve_port(b"GET / HTTP/1.1\r\nHost: api.local\r\n\r\n") == server


def test_connection_refused_error():
    proxy = HTTPProxy({"default": (1, 0)})
    raw = b"GET / HTTP/1.1\r\nHost: default.local\r\n\r\n"
    with pytest.raises(ConnectionError):
        proxy.request(raw, 1)


class _StaleConnServer:
    """Accepts connections, answers ONE request, then closes the socket while
    advertising keep-alive — simulating a local app idle-timeout."""

    def __init__(self):
        import socket
        self._srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._srv.bind(("127.0.0.1", 0))
        self._srv.listen(16)
        self.port = self._srv.getsockname()[1]
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        while True:
            try:
                conn, _ = self._srv.accept()
            except OSError:
                return
            conn.settimeout(5)
            try:
                conn.recv(65536)
                conn.sendall(
                    b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n"
                    b"Connection: keep-alive\r\n\r\nok"
                )
            except OSError:
                pass
            finally:
                conn.close()

    def stop(self):
        self._srv.close()


def test_retry_on_stale_pooled_connection():
    server = _StaleConnServer()
    try:
        proxy = HTTPProxy({"default": (server.port, 0)})
        raw = b"GET / HTTP/1.1\r\nHost: default.local\r\n\r\n"

        # Request 1: fresh conn; advertised keep-alive -> pooled.
        resp, conn = proxy.request(raw, server.port)
        assert resp.status == 200
        resp.read()
        proxy.release(server.port, resp, conn, reusable=True)

        # Request 2: pooled conn is stale (server closed it) -> must retry
        # on a fresh connection and still succeed.
        resp2, conn2 = proxy.request(raw, server.port)
        assert resp2.status == 200
        assert conn2 is not conn
        assert resp2.read() == b"ok"
        proxy.release(server.port, resp2, conn2, reusable=True)
    finally:
        server.stop()
