"""Loopback-only HTTP server: JSON API plus an allowlisted static UI."""

import json
import secrets
import socket
import socketserver
import sys
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .store import (
    DB_FILENAME,
    DEFAULT_TTL_SECONDS,
    SHOW_ID,
    TOKEN_RE,
    Store,
    StoreError,
    prepare_data_dir,
)

BIND_HOST = "127.0.0.1"
MAX_BODY_BYTES = 4096
SOCKET_TIMEOUT_SECONDS = 10

CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; "
    "img-src 'self' data:; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
)

STATIC_DIR = Path(__file__).resolve().parent / "static"
# Fixed allowlist: request path -> (file name inside STATIC_DIR, content type).
# User input is only ever used as a dictionary key, never joined into a path.
STATIC_ROUTES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/static/app.css": ("app.css", "text/css; charset=utf-8"),
    "/static/app.js": ("app.js", "text/javascript; charset=utf-8"),
}

STATUS_CODES = {
    400: ("invalid_request", "Malformed request."),
    404: ("not_found", "Not found."),
    405: ("method_not_allowed", "Method not allowed."),
    408: ("invalid_request", "Request timed out."),
    414: ("invalid_request", "Request target too long."),
    431: ("invalid_request", "Request headers too large."),
    501: ("method_not_allowed", "Method not supported."),
}


class ApiError(Exception):
    def __init__(self, status, code, message, extra=None, headers=None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.extra = extra or {}
        self.headers = headers or {}

    @classmethod
    def from_store(cls, exc):
        extra = {}
        if exc.conflicts is not None:
            extra["conflicts"] = exc.conflicts
        if exc.state is not None:
            extra["state"] = exc.state
        return cls(exc.status, exc.code, exc.message, extra)


class _HTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    # On Windows SO_REUSEADDR would allow port sharing, so only enable it elsewhere
    # (lets a restart on the same port succeed while old sockets sit in TIME_WAIT).
    allow_reuse_address = sys.platform != "win32"
    request_queue_size = 64

    def __init__(self, address, handler, store, quiet):
        self.store = store
        self.quiet = quiet
        super().__init__(address, handler)

    def server_bind(self):
        # Skip HTTPServer's reverse-DNS lookup; we only ever bind loopback.
        socketserver.TCPServer.server_bind(self)
        self.server_name = BIND_HOST
        self.server_port = self.server_address[1]

    def handle_error(self, request, client_address):
        if not self.quiet:
            super().handle_error(request, client_address)


class Handler(BaseHTTPRequestHandler):
    server_version = "SeatTicketing/1"
    sys_version = ""
    protocol_version = "HTTP/1.0"
    timeout = SOCKET_TIMEOUT_SECONDS

    _body_read = False

    # -- logging / low-level responses -------------------------------------

    def log_message(self, fmt, *args):
        if not self.server.quiet:
            sys.stderr.write("%s %s\n" % (self.address_string(), fmt % args))

    def _send(self, status, body, content_type, api=True, headers=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store" if api else "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", CSP)
        self.send_header("Connection", "close")
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        if getattr(self, "command", None) != "HEAD":
            self.wfile.write(body)
        self.close_connection = True

    def _send_json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8")

    def _send_api_error(self, exc):
        error = {"code": exc.code, "message": exc.message}
        error.update(exc.extra)
        body = json.dumps({"error": error}).encode("utf-8")
        self._send(exc.status, body, "application/json; charset=utf-8", headers=exc.headers)

    def send_error(self, code, message=None, explain=None):
        # Replace the stdlib HTML error page (it would reflect input).
        error_code, text = STATUS_CODES.get(code, ("invalid_request", "Request error."))
        body = json.dumps({"error": {"code": error_code, "message": text}}).encode("utf-8")
        headers = {"Allow": "GET, POST, DELETE"} if code == 501 else None
        self._send(code, body, "application/json; charset=utf-8", headers=headers)

    # -- method entry points -----------------------------------------------

    def do_GET(self):
        self._handle("GET")

    def do_POST(self):
        self._handle("POST")

    def do_DELETE(self):
        self._handle("DELETE")

    def do_PUT(self):
        self._handle("PUT")

    def do_PATCH(self):
        self._handle("PATCH")

    def do_HEAD(self):
        self._handle("HEAD")

    def do_OPTIONS(self):
        self._handle("OPTIONS")

    def _handle(self, method):
        self._body_read = False
        try:
            try:
                self._route(method)
            except ApiError as exc:
                self._send_api_error(exc)
            except StoreError as exc:
                self._send_api_error(ApiError.from_store(exc))
            except (ConnectionError, socket.timeout):
                self.close_connection = True
            except Exception:
                if not self.server.quiet:
                    traceback.print_exc()
                self._send_api_error(
                    ApiError(500, "internal_error", "Internal server error.")
                )
        except (OSError, ValueError):
            self.close_connection = True
        finally:
            self._drain()

    def _drain(self):
        """Discard an unread request body so closing does not reset the client."""
        if self._body_read:
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            length = min(max(length, 0), 65536)
            if length:
                self.rfile.read(length)
        except Exception:
            pass

    # -- routing -----------------------------------------------------------

    def _match(self, path):
        if path in STATIC_ROUTES:
            return "static", path, ("GET",)
        parts = path.split("/")
        if parts[:3] != ["", "api", "v1"]:
            return None
        rest = parts[3:]
        if rest == ["health"]:
            return "health", None, ("GET",)
        if rest == ["session"]:
            return "session", None, ("POST",)
        if rest and rest[0] == "shows" and len(rest) >= 2:
            if rest[1] != SHOW_ID:
                raise ApiError(404, "show_not_found", "Show not found.")
            tail = rest[2:]
            if tail == []:
                return "state", None, ("GET",)
            if tail == ["holds"]:
                return "holds", None, ("POST",)
            if len(tail) == 2 and tail[0] == "holds":
                return "release", tail[1], ("DELETE",)
        return None

    def _route(self, method):
        # Check the original target so the static allowlist applies before
        # BaseHTTPRequestHandler's leading-slash normalization.
        target = self.requestline.split(maxsplit=2)[1]
        path = target.split("?", 1)[0].split("#", 1)[0]
        route = self._match(path)
        if route is None:
            if method == "OPTIONS":
                raise ApiError(405, "method_not_allowed", "Method not allowed.", headers={"Allow": "GET"})
            raise ApiError(404, "not_found", "Not found.")
        name, param, allowed = route
        if method not in allowed:
            raise ApiError(
                405, "method_not_allowed", "Method not allowed.",
                headers={"Allow": ", ".join(allowed)},
            )
        getattr(self, "_h_" + name)(param)

    # -- request checks ----------------------------------------------------

    def _check_origin(self):
        port = self.server.server_address[1]
        hosts = ("127.0.0.1:%d" % port, "localhost:%d" % port)
        host = self.headers.get("Host")
        if host is None or host.strip().lower() not in hosts:
            raise ApiError(403, "forbidden_origin", "Host not allowed.")
        origin = self.headers.get("Origin")
        if origin is not None and origin not in ("http://%s" % h for h in hosts):
            raise ApiError(403, "forbidden_origin", "Origin not allowed.")

    def _token(self, required):
        token = self.headers.get("X-Session-Token")
        if token is None:
            if required:
                raise ApiError(401, "token_required", "X-Session-Token header is required.")
            return None
        if not TOKEN_RE.fullmatch(token):
            raise ApiError(400, "invalid_request", "X-Session-Token must be 32 lowercase hex characters.")
        return token

    def _read_body(self):
        if self.headers.get("Transfer-Encoding") is not None:
            raise ApiError(411, "payload_too_large", "Chunked bodies are not supported; send Content-Length.")
        length = self.headers.get("Content-Length")
        if length is None:
            self._body_read = True
            return b""
        length = length.strip()
        if not (length.isascii() and length.isdigit()):
            raise ApiError(400, "invalid_request", "Invalid Content-Length.")
        if len(length) > 9 or int(length) > MAX_BODY_BYTES:
            raise ApiError(413, "payload_too_large", "Request body exceeds %d bytes." % MAX_BODY_BYTES)
        size = int(length)
        data = self.rfile.read(size) if size else b""
        if len(data) != size:
            raise ApiError(400, "invalid_request", "Request body shorter than Content-Length.")
        self._body_read = True
        return data

    def _json_body(self):
        raw = self._read_body()
        if not raw:
            return None
        media = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if media != "application/json":
            raise ApiError(415, "unsupported_media_type", "Content-Type must be application/json.")
        if raw.count(b"[") + raw.count(b"{") > 64:
            # Valid bodies nest two levels; refuse before the parser can recurse deeply.
            raise ApiError(400, "invalid_request", "Request body is not valid JSON.")
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError, RecursionError):
            raise ApiError(400, "invalid_request", "Request body is not valid JSON.") from None

    # -- handlers ----------------------------------------------------------

    def _h_static(self, path):
        filename, content_type = STATIC_ROUTES[path]
        try:
            body = (STATIC_DIR / filename).read_bytes()
        except OSError:
            raise ApiError(404, "not_found", "Not found.") from None
        self._send(200, body, content_type, api=False)

    def _h_health(self, _):
        self._send_json(200, {"status": "ok", "api_version": 1})

    def _h_session(self, _):
        self._check_origin()
        body = self._json_body()
        if body is not None and not isinstance(body, dict):
            raise ApiError(400, "invalid_request", "Request body must be a JSON object.")
        self._send_json(201, {"token": secrets.token_hex(16)})

    def _h_state(self, _):
        token = self._token(False)
        self._send_json(200, self.server.store.get_state(token))

    def _h_holds(self, _):
        self._check_origin()
        token = self._token(True)
        body = self._json_body()
        if not isinstance(body, dict) or "seats" not in body:
            raise ApiError(400, "invalid_request", "Body must be a JSON object with a 'seats' list.")
        self._send_json(201, self.server.store.hold(token, body["seats"]))

    def _h_release(self, seat):
        self._check_origin()
        token = self._token(True)
        self._read_body()  # size-capped; content ignored
        self._send_json(200, self.server.store.release(token, seat))


class SeatServer:
    """Owns the store and HTTP server; usable from tests and the CLI."""

    def __init__(self, data_dir, port=0, clock=None, ttl_seconds=DEFAULT_TTL_SECONDS, quiet=False):
        if not isinstance(port, int) or isinstance(port, bool) or not 0 <= port <= 65535:
            raise ValueError("port must be an integer from 0 to 65535")
        directory = prepare_data_dir(data_dir)
        self.store = Store(directory / DB_FILENAME, clock=clock or time.time, ttl_seconds=ttl_seconds)
        try:
            self.httpd = _HTTPServer((BIND_HOST, port), Handler, self.store, quiet)
        except BaseException:
            self.store.close()
            raise
        self.port = self.httpd.server_address[1]
        self._thread = None
        self._serving = False
        self._closed = False
        self._lock = threading.Lock()

    def serve_forever(self):
        with self._lock:
            self._serving = True
        self.httpd.serve_forever(poll_interval=0.05)

    def start(self):
        with self._lock:
            if self._thread is not None:
                return
            self._serving = True
            self._thread = threading.Thread(
                target=self.httpd.serve_forever, kwargs={"poll_interval": 0.05},
                name="seat-server", daemon=True,
            )
            self._thread.start()

    def shutdown(self):
        with self._lock:
            serving, self._serving = self._serving, False
        if serving:
            self.httpd.shutdown()
        if self._thread is not None:
            self._thread.join(timeout=10)

    def close(self):
        with self._lock:
            if self._closed:
                return
            self._closed = True
        self.shutdown()
        self.httpd.server_close()
        self.store.close()


def create_server(data_dir, port=0, clock=None, ttl_seconds=DEFAULT_TTL_SECONDS, quiet=False):
    return SeatServer(data_dir, port, clock=clock, ttl_seconds=ttl_seconds, quiet=quiet)
