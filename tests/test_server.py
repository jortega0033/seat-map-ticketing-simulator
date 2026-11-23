import http.client
import json
import os
import re
import socket
import sqlite3
import tempfile
import threading
import unittest

from seat_ticketing.server import CSP, STATIC_DIR, create_server

TOKEN_RE = re.compile(r"[0-9a-f]{32}\Z")


class FakeClock:
    def __init__(self, now=1_700_000_000.0):
        self.now = now

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


def flat(state):
    return {s["id"]: s for row in state["rows"] for s in row["seats"]}


class ServerTestCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        self.dir = tmp.name
        self.clock = FakeClock()
        self.server = self.start_server()

    def start_server(self):
        server = create_server(self.dir, 0, clock=self.clock, ttl_seconds=120, quiet=True)
        server.start()
        self.addCleanup(server.close)
        return server

    def call(self, method, path, token=None, json_body=None, body=None, headers=None, server=None):
        server = server or self.server
        h = dict(headers or {})
        data = body
        if json_body is not None:
            data = json.dumps(json_body).encode("utf-8")
            h.setdefault("Content-Type", "application/json")
        if token is not None:
            h["X-Session-Token"] = token
        conn = http.client.HTTPConnection("127.0.0.1", server.port, timeout=10)
        try:
            conn.request(method, path, body=data, headers=h)
            resp = conn.getresponse()
            raw = resp.read()
        finally:
            conn.close()
        if resp.getheader("Content-Type", "").startswith("application/json"):
            payload = json.loads(raw.decode("utf-8"))
        else:
            payload = raw
        return resp.status, resp, payload

    def new_token(self, server=None):
        status, _, payload = self.call("POST", "/api/v1/session", server=server)
        self.assertEqual(status, 201)
        return payload["token"]

    def hold(self, token, seats, **kw):
        return self.call("POST", "/api/v1/shows/show-a/holds", token=token, json_body={"seats": seats}, **kw)

    def state(self, token=None, server=None):
        status, _, payload = self.call("GET", "/api/v1/shows/show-a", token=token, server=server)
        self.assertEqual(status, 200)
        return payload

    def raw_exchange(self, request_bytes):
        sock = socket.create_connection(("127.0.0.1", self.server.port), timeout=10)
        try:
            sock.sendall(request_bytes)
            chunks = []
            while True:
                data = sock.recv(4096)
                if not data:
                    break
                chunks.append(data)
        finally:
            sock.close()
        return b"".join(chunks)

    def db_hold_count(self):
        conn = sqlite3.connect(os.path.join(self.dir, "seats.sqlite3"))
        try:
            return conn.execute("SELECT COUNT(*) FROM holds").fetchone()[0]
        finally:
            conn.close()


class BasicEndpointTests(ServerTestCase):
    def test_health(self):
        status, resp, payload = self.call("GET", "/api/v1/health")
        self.assertEqual(status, 200)
        self.assertEqual(payload, {"status": "ok", "api_version": 1})

    def test_security_headers_on_api_and_errors(self):
        for path in ("/api/v1/health", "/api/v1/nope", "/nope"):
            _, resp, _ = self.call("GET", path)
            self.assertEqual(resp.getheader("X-Content-Type-Options"), "nosniff", path)
            self.assertEqual(resp.getheader("Content-Security-Policy"), CSP, path)
            self.assertIsNone(resp.getheader("Access-Control-Allow-Origin"), path)
        _, resp, _ = self.call("GET", "/api/v1/health")
        self.assertEqual(resp.getheader("Cache-Control"), "no-store")

    def test_session_tokens(self):
        a = self.new_token()
        b = self.new_token()
        self.assertRegex(a, TOKEN_RE)
        self.assertRegex(b, TOKEN_RE)
        self.assertNotEqual(a, b)
        status, _, payload = self.call("POST", "/api/v1/session", json_body={})
        self.assertEqual(status, 201)
        self.assertRegex(payload["token"], TOKEN_RE)

    def test_session_rejects_non_object_and_wrong_type(self):
        status, _, payload = self.call("POST", "/api/v1/session", json_body=[1])
        self.assertEqual((status, payload["error"]["code"]), (400, "invalid_request"))
        status, _, payload = self.call(
            "POST", "/api/v1/session", body=b"{}", headers={"Content-Type": "text/plain"}
        )
        self.assertEqual((status, payload["error"]["code"]), (415, "unsupported_media_type"))

    def test_initial_state_shape(self):
        state = self.state()
        self.assertEqual(state["show"], {"id": "show-a", "name": "Show A"})
        self.assertEqual(state["hold_ttl_seconds"], 120)
        self.assertEqual(state["server_time"], self.clock.now)
        self.assertIsInstance(state["version"], int)
        self.assertEqual([r["row"] for r in state["rows"]], ["A", "B", "C"])
        self.assertEqual(
            [s["id"] for s in state["rows"][1]["seats"]], ["B1", "B2", "B3", "B4"]
        )
        for seat in flat(state).values():
            self.assertEqual(seat["status"], "available")
            self.assertIsNone(seat["expires_at"])
        self.assertEqual(state["remaining"], {"available": 12, "held": 0, "total": 12})

    def test_state_bad_token_header(self):
        for bad in ("short", "A" * 32, "g" * 32, ""):
            status, _, payload = self.call("GET", "/api/v1/shows/show-a", token=bad)
            self.assertEqual((status, payload["error"]["code"]), (400, "invalid_request"), bad)

    def test_unknown_show_and_paths(self):
        for method, path in (
            ("GET", "/api/v1/shows/other"),
            ("POST", "/api/v1/shows/other/holds"),
            ("DELETE", "/api/v1/shows/other/holds/A1"),
        ):
            status, _, payload = self.call(method, path)
            self.assertEqual((status, payload["error"]["code"]), (404, "show_not_found"), path)
        for path in ("/api/v1/nope", "/api/v1/shows", "/api/v1/shows/show-a/holds/A1/x", "/api/v2/health"):
            status, _, payload = self.call("GET", path)
            self.assertEqual((status, payload["error"]["code"]), (404, "not_found"), path)

    def test_method_not_allowed_and_options(self):
        cases = [
            ("POST", "/api/v1/health", "GET"),
            ("PUT", "/api/v1/health", "GET"),
            ("GET", "/api/v1/session", "POST"),
            ("OPTIONS", "/api/v1/health", "GET"),
            ("OPTIONS", "/api/v1/shows/show-a/holds", "POST"),
            ("GET", "/api/v1/shows/show-a/holds", "POST"),
            ("POST", "/api/v1/shows/show-a", "GET"),
            ("PATCH", "/api/v1/shows/show-a/holds/A1", "DELETE"),
            ("POST", "/static/app.js", "GET"),
        ]
        for method, path, allow in cases:
            status, resp, payload = self.call(method, path)
            self.assertEqual(status, 405, (method, path))
            self.assertEqual(payload["error"]["code"], "method_not_allowed")
            self.assertEqual(resp.getheader("Allow"), allow, (method, path))
        status, _, _ = self.call("OPTIONS", "/nowhere")
        self.assertEqual(status, 405)


class HoldFlowTests(ServerTestCase):
    def test_hold_success_and_state(self):
        a, b = self.new_token(), self.new_token()
        before = self.state()["version"]
        status, _, payload = self.hold(a, ["B2", "A1"])
        self.assertEqual(status, 201)
        self.assertEqual(payload["held"], ["A1", "B2"])
        seats = flat(payload)
        self.assertEqual(seats["A1"]["status"], "held_own")
        self.assertEqual(seats["A1"]["expires_at"], self.clock.now + 120)
        self.assertEqual(payload["remaining"], {"available": 10, "held": 2, "total": 12})
        self.assertEqual(payload["version"], before + 1)
        other_view = flat(self.state(b))
        self.assertEqual(other_view["A1"]["status"], "held_other")
        self.assertEqual(other_view["A1"]["expires_at"], self.clock.now + 120)
        anon_view = flat(self.state())
        self.assertEqual(anon_view["B2"]["status"], "held_other")
        self.assertEqual(self.db_hold_count(), 2)

    def test_conflict_is_all_or_nothing_with_fresh_state(self):
        a, b = self.new_token(), self.new_token()
        self.assertEqual(self.hold(a, ["A1"])[0], 201)
        status, _, payload = self.hold(b, ["A2", "A1", "B1"])
        self.assertEqual(status, 409)
        error = payload["error"]
        self.assertEqual(error["code"], "seat_conflict")
        self.assertEqual(error["conflicts"], ["A1"])
        self.assertIsInstance(error["message"], str)
        fresh = flat(error["state"])
        self.assertEqual(fresh["A1"]["status"], "held_other")
        self.assertEqual(fresh["A2"]["status"], "available")
        self.assertEqual(self.db_hold_count(), 1)
        seats = flat(self.state(b))
        self.assertEqual(seats["A2"]["status"], "available")
        self.assertEqual(seats["B1"]["status"], "available")
        self.assertEqual(self.state()["remaining"]["held"], 1)

    def test_disjoint_holds_both_succeed(self):
        a, b = self.new_token(), self.new_token()
        self.assertEqual(self.hold(a, ["A1", "A2"])[0], 201)
        self.assertEqual(self.hold(b, ["C1", "C2"])[0], 201)
        self.assertEqual(self.state()["remaining"], {"available": 8, "held": 4, "total": 12})

    def test_rehold_own_is_idempotent_and_refreshes(self):
        a = self.new_token()
        self.hold(a, ["A1"])
        self.clock.advance(60)
        status, _, payload = self.hold(a, ["A1", "A2"])
        self.assertEqual(status, 201)
        self.assertEqual(flat(payload)["A1"]["expires_at"], self.clock.now + 120)
        self.assertEqual(self.db_hold_count(), 2)

    def test_expiry_via_fake_clock(self):
        a, b = self.new_token(), self.new_token()
        self.hold(a, ["A1"])
        self.clock.advance(119)
        self.assertEqual(flat(self.state(b))["A1"]["status"], "held_other")
        self.assertEqual(self.hold(b, ["A1"])[0], 409)
        self.clock.advance(1)
        view = self.state(b)
        self.assertEqual(flat(view)["A1"]["status"], "available")
        self.assertEqual(view["remaining"]["held"], 0)
        self.assertEqual(view["server_time"], self.clock.now)
        self.assertEqual(self.hold(b, ["A1"])[0], 201)

    def test_restart_retention_same_db(self):
        a = self.new_token()
        self.hold(a, ["A1", "B3"])
        version = self.state()["version"]
        self.server.close()
        second = self.start_server()
        view = self.state(a, server=second)
        self.assertEqual(view["version"], version)
        self.assertEqual(flat(view)["A1"]["status"], "held_own")
        self.assertEqual(flat(view)["B3"]["status"], "held_own")
        self.assertEqual(view["remaining"]["held"], 2)
        self.clock.advance(121)
        self.assertEqual(self.state(a, server=second)["remaining"]["held"], 0)

    def test_release_own(self):
        a = self.new_token()
        self.hold(a, ["A1", "A2"])
        status, _, payload = self.call("DELETE", "/api/v1/shows/show-a/holds/A1", token=a)
        self.assertEqual(status, 200)
        self.assertEqual(payload["released"], "A1")
        self.assertEqual(flat(payload)["A1"]["status"], "available")
        self.assertEqual(flat(payload)["A2"]["status"], "held_own")
        self.assertEqual(self.db_hold_count(), 1)

    def test_release_other_and_missing(self):
        a, b = self.new_token(), self.new_token()
        self.hold(a, ["A1"])
        status, _, payload = self.call("DELETE", "/api/v1/shows/show-a/holds/A1", token=b)
        self.assertEqual((status, payload["error"]["code"]), (404, "hold_not_found"))
        self.assertEqual(self.db_hold_count(), 1)
        status, _, payload = self.call("DELETE", "/api/v1/shows/show-a/holds/C3", token=a)
        self.assertEqual((status, payload["error"]["code"]), (404, "hold_not_found"))

    def test_release_validation(self):
        a = self.new_token()
        status, _, payload = self.call("DELETE", "/api/v1/shows/show-a/holds/A1")
        self.assertEqual((status, payload["error"]["code"]), (401, "token_required"))
        for seat in ("A5", "a1", "D1", "A1%0A", "%41%31", ""):
            status, _, payload = self.call("DELETE", "/api/v1/shows/show-a/holds/" + seat, token=a)
            self.assertEqual((status, payload["error"]["code"]), (400, "invalid_request"), seat)

    def test_unknown_seat_422(self):
        a = self.new_token()
        conn = sqlite3.connect(os.path.join(self.dir, "seats.sqlite3"))
        try:
            conn.execute("DELETE FROM seats WHERE seat_id='C4'")
            conn.commit()
        finally:
            conn.close()
        status, _, payload = self.hold(a, ["A1", "C4"])
        self.assertEqual((status, payload["error"]["code"]), (422, "unknown_seat"))
        self.assertEqual(self.db_hold_count(), 0)

    def test_concurrent_http_holds_exactly_one_winner(self):
        count = 6
        tokens = [self.new_token() for _ in range(count)]
        barrier = threading.Barrier(count, timeout=10)
        statuses = [None] * count

        def worker(i):
            try:
                barrier.wait()
                statuses[i] = self.hold(tokens[i], ["A1", "A2"])[0]
            except BaseException as exc:
                statuses[i] = repr(exc)

        threads = [threading.Thread(target=worker, args=(i,), daemon=True) for i in range(count)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
        self.assertFalse(any(t.is_alive() for t in threads))
        self.assertEqual(statuses.count(201), 1, statuses)
        self.assertEqual(statuses.count(409), count - 1, statuses)
        self.assertEqual(self.db_hold_count(), 2)


class ValidationTests(ServerTestCase):
    def setUp(self):
        super().setUp()
        self.token = self.new_token()

    def assert_error(self, result, status, code):
        got_status, _, payload = result
        self.assertEqual(got_status, status, payload)
        self.assertEqual(payload["error"]["code"], code)
        self.assertNotIn("Traceback", json.dumps(payload))
        self.assertEqual(self.db_hold_count(), 0)

    def post_raw(self, body, content_type="application/json", **kw):
        headers = {} if content_type is None else {"Content-Type": content_type}
        return self.call(
            "POST", "/api/v1/shows/show-a/holds", token=self.token, body=body, headers=headers, **kw
        )

    def test_bad_bodies(self):
        bad_bodies = [
            b"", b"not json", b"\xff\xfe", b"[]", b'"A1"', b"null", b"{}",
            b'{"seats": "A1"}', b'{"seats": []}', b'{"seats": [1]}', b'{"seats": [null]}',
            b'{"seats": ["A1", "A1"]}', b'{"seats": ["A5"]}', b'{"seats": ["a1"]}',
            json.dumps({"seats": ["A1", "A2", "A3", "A4", "B1", "B2", "B3", "B4", "C1", "C2", "C3", "C4", "A1"]}).encode(),
            b"[" * 3000,
        ]
        for body in bad_bodies:
            self.assert_error(self.post_raw(body), 400, "invalid_request")

    def test_token_header_checks(self):
        status, _, payload = self.call(
            "POST", "/api/v1/shows/show-a/holds", json_body={"seats": ["A1"]}
        )
        self.assertEqual((status, payload["error"]["code"]), (401, "token_required"))
        status, _, payload = self.call(
            "POST", "/api/v1/shows/show-a/holds", token="zz", json_body={"seats": ["A1"]}
        )
        self.assertEqual((status, payload["error"]["code"]), (400, "invalid_request"))
        self.assertEqual(self.db_hold_count(), 0)

    def test_payload_cap(self):
        base = b'{"seats":["A1"],"pad":""}'
        exact = b'{"seats":["A1"],"pad":"' + b"x" * (4096 - len(base)) + b'"}'
        self.assertEqual(len(exact), 4096)
        over = exact + b" "
        self.assert_error(self.post_raw(over), 413, "payload_too_large")
        huge = b'{"seats":["A1"],"pad":"' + b"x" * 60000 + b'"}'
        self.assert_error(self.post_raw(huge), 413, "payload_too_large")
        status, _, _ = self.post_raw(exact)
        self.assertEqual(status, 201)

    def test_content_length_and_chunked(self):
        host = "Host: 127.0.0.1:%d\r\n" % self.server.port
        tok = "X-Session-Token: %s\r\n" % self.token
        head = "POST /api/v1/shows/show-a/holds HTTP/1.0\r\n" + host + tok + "Content-Type: application/json\r\n"
        out = self.raw_exchange((head + "Transfer-Encoding: chunked\r\n\r\n0\r\n\r\n").encode())
        self.assertIn(b" 411 ", out.split(b"\r\n", 1)[0] + b" ")
        out = self.raw_exchange((head + "Content-Length: abc\r\n\r\n").encode())
        self.assertIn(b" 400 ", out.split(b"\r\n", 1)[0] + b" ")
        out = self.raw_exchange((head + "Content-Length: 5000\r\n\r\n").encode() + b"x" * 5000)
        self.assertIn(b" 413 ", out.split(b"\r\n", 1)[0] + b" ")
        self.assertEqual(self.db_hold_count(), 0)

    def test_media_type(self):
        body = b'{"seats":["A1"]}'
        for ctype in (None, "text/plain", "application/x-www-form-urlencoded", "application/jsonx"):
            self.assert_error(self.post_raw(body, content_type=ctype), 415, "unsupported_media_type")
        status, _, _ = self.post_raw(body, content_type="Application/JSON; charset=utf-8")
        self.assertEqual(status, 201)

    def test_forbidden_origin_and_host(self):
        port = self.server.port
        body = {"seats": ["A1"]}
        bad_headers = [
            {"Origin": "http://evil.example"},
            {"Origin": "null"},
            {"Origin": "http://127.0.0.1:%d" % (port + 1)},
            {"Origin": "https://127.0.0.1:%d" % port},
            {"Host": "evil.example"},
            {"Host": "127.0.0.1:%d" % (port + 1)},
            {"Host": "127.0.0.1"},
        ]
        for headers in bad_headers:
            self.assert_error(
                self.call("POST", "/api/v1/shows/show-a/holds", token=self.token, json_body=body, headers=headers),
                403, "forbidden_origin",
            )
        self.assert_error(
            self.call("POST", "/api/v1/session", headers={"Origin": "http://evil.example"}),
            403, "forbidden_origin",
        )
        status, _, payload = self.call(
            "DELETE", "/api/v1/shows/show-a/holds/A1", token=self.token,
            headers={"Origin": "http://evil.example"},
        )
        self.assertEqual((status, payload["error"]["code"]), (403, "forbidden_origin"))

    def test_allowed_origin_and_host_variants(self):
        port = self.server.port
        variants = [
            {"Origin": "http://127.0.0.1:%d" % port},
            {"Origin": "http://localhost:%d" % port, "Host": "localhost:%d" % port},
            {"Host": "localhost:%d" % port},
        ]
        for i, headers in enumerate(variants):
            seat = "A%d" % (i + 1)
            status, _, _ = self.call(
                "POST", "/api/v1/shows/show-a/holds", token=self.token,
                json_body={"seats": [seat]}, headers=headers,
            )
            self.assertEqual(status, 201, headers)
        self.assertEqual(self.db_hold_count(), 3)

    def test_get_does_not_require_origin(self):
        status, _, _ = self.call("GET", "/api/v1/shows/show-a", headers={"Origin": "http://evil.example"})
        self.assertEqual(status, 200)


class StaticTests(ServerTestCase):
    FILES = {
        "/": ("index.html", "text/html"),
        "/static/tokens.css": ("tokens.css", "text/css"),
        "/static/app.css": ("app.css", "text/css"),
        "/static/app.js": ("app.js", "text/javascript"),
    }

    def test_allowlisted_assets(self):
        for path, (name, ctype) in self.FILES.items():
            status, resp, payload = self.call("GET", path)
            self.assertTrue(os.path.isfile(os.path.join(STATIC_DIR, name)), name)
            self.assertEqual(status, 200, path)
            self.assertTrue(resp.getheader("Content-Type").startswith(ctype), path)
            self.assertEqual(resp.getheader("X-Content-Type-Options"), "nosniff")
            self.assertEqual(resp.getheader("Content-Security-Policy"), CSP)
            with open(os.path.join(STATIC_DIR, name), "rb") as f:
                self.assertEqual(payload, f.read())

    def test_not_allowlisted_and_traversal_are_404(self):
        paths = [
            "/static/index.html", "/static/", "/static", "/static/app.js/", "/static//app.js",
            "/static/../server.py", "/static/../../seat_ticketing/server.py",
            "/static/%2e%2e/server.py", "/static/..%2fserver.py", "/static/%2E%2E%5Cserver.py",
            "/static/..\\server.py", "/static/app.js%00", "/static/app.js%2f..%2fserver.py",
            "/../seat_ticketing/server.py", "/seat_ticketing/server.py", "/server.py",
            "/index.html", "//", "/static/APP.JS", "/app.js", "/.git/config", "/seats.sqlite3",
        ]
        for path in paths:
            status, _, payload = self.call("GET", path)
            self.assertEqual(status, 404, path)
            self.assertNotIn(b"def ", payload if isinstance(payload, bytes) else json.dumps(payload).encode())

    def test_query_string_ignored_for_allowlisted(self):
        plain = self.call("GET", "/static/app.css")
        queried = self.call("GET", "/static/app.css?v=1")
        self.assertEqual(plain[0], 200)
        self.assertEqual(queried[0], 200)
        self.assertEqual(plain[2], queried[2])


if __name__ == "__main__":
    unittest.main()
