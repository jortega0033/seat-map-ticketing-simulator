import os
import sqlite3
import tempfile
import threading
import unittest

from seat_ticketing.store import Store, StoreError, StoreInitError

TOKEN_A = "a" * 32
TOKEN_B = "b" * 32
ALL_SEATS = ["%s%d" % (r, n) for r in "ABC" for n in range(1, 5)]


class FakeClock:
    def __init__(self, now=1_700_000_000.0):
        self.now = now

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


def flat(state):
    return {s["id"]: s for row in state["rows"] for s in row["seats"]}


class StoreTestCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        self.dir = tmp.name
        self.path = os.path.join(self.dir, "seats.sqlite3")
        self.clock = FakeClock()

    def make_store(self, ttl=120):
        return Store(self.path, clock=self.clock, ttl_seconds=ttl)

    def raw(self, sql, params=()):
        conn = sqlite3.connect(self.path)
        try:
            rows = conn.execute(sql, params).fetchall()
            conn.commit()
            return rows
        finally:
            conn.close()


class SchemaTests(StoreTestCase):
    def test_seed_and_schema(self):
        store = self.make_store()
        state = store.get_state()
        self.assertEqual([r["row"] for r in state["rows"]], ["A", "B", "C"])
        self.assertEqual(list(flat(state)), ALL_SEATS)
        self.assertEqual(state["remaining"], {"available": 12, "held": 0, "total": 12})
        self.assertEqual(self.raw("PRAGMA user_version")[0][0], 1)
        self.assertEqual(self.raw("PRAGMA journal_mode")[0][0].lower(), "wal")

    def test_reopen_is_idempotent(self):
        self.make_store()
        self.make_store()
        self.assertEqual(self.raw("SELECT COUNT(*) FROM seats")[0][0], 12)
        self.assertEqual(self.raw("SELECT value FROM meta WHERE key='version'")[0][0], 0)

    def test_newer_schema_rejected(self):
        self.make_store()
        self.raw("PRAGMA user_version=99")
        with self.assertRaises(StoreInitError):
            self.make_store()

    def test_garbage_file_rejected(self):
        with open(self.path, "wb") as f:
            f.write(b"this is not a database " * 20)
        with self.assertRaises(StoreInitError):
            self.make_store()

    def test_directory_at_db_path_rejected(self):
        os.mkdir(self.path)
        with self.assertRaises(StoreInitError):
            self.make_store()

    def test_token_length_check_enforced_by_schema(self):
        self.make_store()
        with self.assertRaises(sqlite3.IntegrityError):
            self.raw(
                "INSERT INTO holds VALUES('show-a','A1','short',1.0,2.0)"
            )

    def test_invalid_ttl(self):
        for ttl in (0, -1, "x", None):
            with self.assertRaises(ValueError):
                Store(self.path, clock=self.clock, ttl_seconds=ttl)


class HoldTests(StoreTestCase):
    def test_all_or_nothing_conflict_inserts_nothing(self):
        store = self.make_store()
        store.hold(TOKEN_A, ["A1"])
        version = store.get_state()["version"]
        before = self.raw("SELECT seat_id, token FROM holds ORDER BY seat_id")
        with self.assertRaises(StoreError) as ctx:
            store.hold(TOKEN_B, ["A2", "A1", "B1"])
        err = ctx.exception
        self.assertEqual((err.status, err.code), (409, "seat_conflict"))
        self.assertEqual(err.conflicts, ["A1"])
        self.assertEqual(self.raw("SELECT seat_id, token FROM holds ORDER BY seat_id"), before)
        fresh = flat(err.state)
        self.assertEqual(fresh["A2"]["status"], "available")
        self.assertEqual(fresh["A1"]["status"], "held_other")
        self.assertEqual(store.get_state()["version"], version)

    def test_disjoint_holds_both_succeed(self):
        store = self.make_store()
        a = store.hold(TOKEN_A, ["A1", "A2"])
        b = store.hold(TOKEN_B, ["B1", "C4"])
        self.assertEqual(a["held"], ["A1", "A2"])
        self.assertEqual(b["held"], ["B1", "C4"])
        seats = flat(b)
        self.assertEqual(seats["A1"]["status"], "held_other")
        self.assertEqual(seats["B1"]["status"], "held_own")
        self.assertEqual(b["remaining"], {"available": 8, "held": 4, "total": 12})
        self.assertEqual(b["version"], a["version"] + 1)
        self.assertEqual(seats["B1"]["expires_at"], self.clock.now + 120)

    def test_same_token_rehold_refreshes_expiry(self):
        store = self.make_store()
        store.hold(TOKEN_A, ["A1"])
        self.clock.advance(60)
        state = store.hold(TOKEN_A, ["A1", "A2"])
        seats = flat(state)
        self.assertEqual(seats["A1"]["expires_at"], self.clock.now + 120)
        self.assertEqual(seats["A2"]["expires_at"], self.clock.now + 120)
        self.assertEqual(state["remaining"]["held"], 2)
        self.assertEqual(self.raw("SELECT COUNT(*) FROM holds")[0][0], 2)

    def test_expiry_with_fake_clock(self):
        store = self.make_store()
        store.hold(TOKEN_A, ["A1"])
        self.clock.advance(119)
        self.assertEqual(flat(store.get_state(TOKEN_B))["A1"]["status"], "held_other")
        with self.assertRaises(StoreError):
            store.hold(TOKEN_B, ["A1"])
        self.clock.advance(1)  # now == expires_at: expired
        version = store.get_state()["version"]
        state = store.get_state(TOKEN_B)
        self.assertEqual(flat(state)["A1"]["status"], "available")
        self.assertIsNone(flat(state)["A1"]["expires_at"])
        self.assertEqual(state["version"], version)  # reads do not write
        taken = store.hold(TOKEN_B, ["A1"])
        self.assertEqual(flat(taken)["A1"]["status"], "held_own")
        self.assertEqual(flat(store.get_state(TOKEN_A))["A1"]["status"], "held_other")

    def test_restart_retains_holds(self):
        store = self.make_store()
        store.hold(TOKEN_A, ["A1", "C3"])
        version = store.get_state()["version"]
        store.close()
        reopened = self.make_store()
        state = reopened.get_state(TOKEN_A)
        self.assertEqual(state["version"], version)
        self.assertEqual(flat(state)["A1"]["status"], "held_own")
        self.assertEqual(flat(reopened.get_state(TOKEN_B))["C3"]["status"], "held_other")
        self.assertEqual(self.raw("SELECT COUNT(*) FROM seats")[0][0], 12)
        self.clock.advance(500)
        self.assertEqual(reopened.get_state()["remaining"]["held"], 0)

    def test_validation_errors(self):
        store = self.make_store()
        bad_inputs = [
            [], "A1", None, {"A1": 1}, ["A1", "A1"], ["a1"], ["A5"], ["D1"], ["A0"],
            [1], ["A1\n"], ["A1 "], ALL_SEATS + ["A1"],
        ]
        for seats in bad_inputs:
            with self.assertRaises(StoreError, msg=repr(seats)) as ctx:
                store.hold(TOKEN_A, seats)
            self.assertEqual((ctx.exception.status, ctx.exception.code), (400, "invalid_request"))
        for token in (None, "", "A" * 32, "a" * 31, "a" * 33, TOKEN_A + "\n"):
            with self.assertRaises(StoreError, msg=repr(token)) as ctx:
                store.hold(token, ["A1"])
            self.assertEqual(ctx.exception.status, 400)
        self.assertEqual(self.raw("SELECT COUNT(*) FROM holds")[0][0], 0)

    def test_all_twelve_seats_allowed(self):
        store = self.make_store()
        state = store.hold(TOKEN_A, ALL_SEATS)
        self.assertEqual(state["remaining"], {"available": 0, "held": 12, "total": 12})

    def test_unknown_seat_422_and_no_partial_insert(self):
        store = self.make_store()
        self.raw("DELETE FROM seats WHERE seat_id='C4'")
        with self.assertRaises(StoreError) as ctx:
            store.hold(TOKEN_A, ["A1", "C4"])
        self.assertEqual((ctx.exception.status, ctx.exception.code), (422, "unknown_seat"))
        self.assertEqual(self.raw("SELECT COUNT(*) FROM holds")[0][0], 0)

    def test_failed_hold_leaves_store_usable(self):
        store = self.make_store()
        with self.assertRaises(StoreError):
            store.hold(TOKEN_A, ["A1", "A1"])
        self.assertEqual(store.hold(TOKEN_A, ["A1"])["held"], ["A1"])


class ReleaseTests(StoreTestCase):
    def test_release_own(self):
        store = self.make_store()
        store.hold(TOKEN_A, ["A1", "A2"])
        state = store.release(TOKEN_A, "A1")
        self.assertEqual(state["released"], "A1")
        self.assertEqual(flat(state)["A1"]["status"], "available")
        self.assertEqual(flat(state)["A2"]["status"], "held_own")
        self.assertEqual(state["remaining"]["held"], 1)

    def test_release_other_is_404_and_keeps_hold(self):
        store = self.make_store()
        store.hold(TOKEN_A, ["A1"])
        version = store.get_state()["version"]
        with self.assertRaises(StoreError) as ctx:
            store.release(TOKEN_B, "A1")
        self.assertEqual((ctx.exception.status, ctx.exception.code), (404, "hold_not_found"))
        state = store.get_state(TOKEN_A)
        self.assertEqual(flat(state)["A1"]["status"], "held_own")
        self.assertEqual(state["version"], version)

    def test_release_unheld_and_expired(self):
        store = self.make_store()
        with self.assertRaises(StoreError) as ctx:
            store.release(TOKEN_A, "B2")
        self.assertEqual(ctx.exception.code, "hold_not_found")
        store.hold(TOKEN_A, ["B2"])
        self.clock.advance(120)
        with self.assertRaises(StoreError) as ctx:
            store.release(TOKEN_A, "B2")
        self.assertEqual(ctx.exception.code, "hold_not_found")

    def test_release_validation(self):
        store = self.make_store()
        with self.assertRaises(StoreError) as ctx:
            store.release(TOKEN_A, "Z9")
        self.assertEqual(ctx.exception.status, 400)
        with self.assertRaises(StoreError) as ctx:
            store.release("bad", "A1")
        self.assertEqual(ctx.exception.status, 400)

    def test_released_seat_can_be_held_by_other(self):
        store = self.make_store()
        store.hold(TOKEN_A, ["A1"])
        store.release(TOKEN_A, "A1")
        self.assertEqual(store.hold(TOKEN_B, ["A1"])["held"], ["A1"])


class ConcurrencyTests(StoreTestCase):
    def run_threads(self, count, work):
        barrier = threading.Barrier(count, timeout=10)
        results = [None] * count

        def runner(i):
            try:
                barrier.wait()
                work(i)
                results[i] = "ok"
            except StoreError as exc:
                results[i] = exc.code
            except BaseException as exc:  # surfaced via assertions below
                results[i] = repr(exc)

        threads = [threading.Thread(target=runner, args=(i,), daemon=True) for i in range(count)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
        self.assertFalse(any(t.is_alive() for t in threads))
        return results

    def test_same_seats_exactly_one_winner(self):
        store = self.make_store()
        count = 8
        results = self.run_threads(count, lambda i: store.hold("%032x" % (i + 1), ["A1", "A2", "B1"]))
        self.assertEqual(results.count("ok"), 1, results)
        self.assertEqual(results.count("seat_conflict"), count - 1, results)
        rows = self.raw("SELECT seat_id, token FROM holds")
        self.assertEqual(len(rows), 3)
        self.assertEqual(len({t for _, t in rows}), 1)
        self.assertEqual(store.get_state()["version"], 1)

    def test_overlapping_sets_are_all_or_nothing(self):
        store = self.make_store()
        ring = ["A1", "A2", "A3", "A4"]
        count = 4

        def work(i):
            store.hold("%032x" % (i + 1), [ring[i], ring[(i + 1) % 4]])

        results = self.run_threads(count, work)
        self.assertTrue(all(r in ("ok", "seat_conflict") for r in results), results)
        self.assertGreaterEqual(results.count("ok"), 1)
        per_token = {}
        for _, token in self.raw("SELECT seat_id, token FROM holds"):
            per_token[token] = per_token.get(token, 0) + 1
        self.assertEqual(set(per_token.values()), {2})
        self.assertEqual(len(per_token), results.count("ok"))


if __name__ == "__main__":
    unittest.main()
