import contextlib
import io
import os
import tempfile
import unittest
from unittest import mock

from seat_ticketing import __main__ as cli


class FakeServer:
    port = 4321

    def __init__(self, interrupt=True):
        self.closed = False
        self.served = False
        self.interrupt = interrupt

    def serve_forever(self):
        self.served = True
        if self.interrupt:
            raise KeyboardInterrupt

    def close(self):
        self.closed = True


class CliTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        self.dir = tmp.name

    def run_main(self, argv):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = cli.main(argv)
        return code, err.getvalue()

    def test_empty_data_dir_exits_2(self):
        code, err = self.run_main(["--data-dir", "", "--port", "0"])
        self.assertEqual(code, 2)
        self.assertIn("error", err)

    def test_data_dir_is_existing_file_exits_2(self):
        path = os.path.join(self.dir, "afile")
        with open(path, "w") as f:
            f.write("x")
        code, err = self.run_main(["--data-dir", path, "--port", "0"])
        self.assertEqual(code, 2)
        self.assertIn("error", err)
        with open(path) as f:
            self.assertEqual(f.read(), "x")

    def test_uncreatable_data_dir_exits_2(self):
        path = os.path.join(self.dir, "afile")
        with open(path, "w") as f:
            f.write("x")
        code, err = self.run_main(["--data-dir", os.path.join(path, "sub"), "--port", "0"])
        self.assertEqual(code, 2)
        self.assertIn("error", err)

    def test_corrupt_database_exits_2(self):
        with open(os.path.join(self.dir, "seats.sqlite3"), "wb") as f:
            f.write(b"definitely not sqlite " * 20)
        code, err = self.run_main(["--data-dir", self.dir, "--port", "0"])
        self.assertEqual(code, 2)
        self.assertIn("error", err)

    def test_bad_usage_exits_2(self):
        for argv in ([], ["--data-dir", self.dir, "--port", "70000"], ["--data-dir", self.dir, "--port", "x"],
                     ["--port", "0"]):
            with self.assertRaises(SystemExit) as ctx:
                self.run_main(argv)
            self.assertEqual(ctx.exception.code, 2, argv)

    def test_success_creates_dir_serves_and_closes(self):
        target = os.path.join(self.dir, "nested", "data")
        fake = FakeServer()
        with mock.patch.object(cli, "create_server", return_value=fake) as factory:
            code, err = self.run_main(["--data-dir", target, "--port", "0"])
        self.assertEqual(code, 0)
        self.assertTrue(os.path.isdir(target))
        factory.assert_called_once_with(target, 0)
        self.assertTrue(fake.served)
        self.assertTrue(fake.closed)
        self.assertIn("127.0.0.1:4321", err)

    def test_real_server_creates_database(self):
        # create_server is real here; serve_forever is never entered because we
        # intercept it through a wrapper that closes immediately.
        from seat_ticketing.server import create_server

        def factory(data_dir, port):
            server = create_server(data_dir, port, quiet=True)
            server.serve_forever = lambda: None
            return server

        target = os.path.join(self.dir, "fresh")
        with mock.patch.object(cli, "create_server", side_effect=factory):
            code, _ = self.run_main(["--data-dir", target, "--port", "0"])
        self.assertEqual(code, 0)
        self.assertTrue(os.path.isfile(os.path.join(target, "seats.sqlite3")))


if __name__ == "__main__":
    unittest.main()
