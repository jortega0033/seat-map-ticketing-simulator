"""SQLite-backed domain store for the single fixed show.

All state lives in one SQLite file. Each operation opens its own connection;
writes use BEGIN IMMEDIATE so concurrent holds are serialised by SQLite.
"""

import hmac
import re
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

SHOW_ID = "show-a"
SHOW_NAME = "Show A"
ROW_LABELS = ("A", "B", "C")
SEATS_PER_ROW = 4
MAX_SEATS_PER_REQUEST = 12
DB_FILENAME = "seats.sqlite3"
DEFAULT_TTL_SECONDS = 120

TOKEN_RE = re.compile(r"[0-9a-f]{32}")
SEAT_RE = re.compile(r"[A-C][1-4]")


class StoreError(Exception):
    """Domain error carrying the HTTP-facing status and code."""

    def __init__(self, status, code, message, conflicts=None, state=None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.conflicts = conflicts
        self.state = state


class StoreInitError(Exception):
    """The data directory or database could not be prepared."""


def prepare_data_dir(data_dir):
    """Validate and create the data directory; return it as a Path."""
    try:
        if data_dir is None or not str(data_dir).strip():
            raise StoreInitError("data directory must not be empty")
        path = Path(data_dir)
        if path.exists() and not path.is_dir():
            raise StoreInitError("data directory path is not a directory: %s" % path)
        path.mkdir(parents=True, exist_ok=True)
        if not path.is_dir():
            raise StoreInitError("data directory could not be created: %s" % path)
        return path
    except (OSError, ValueError) as exc:
        raise StoreInitError("data directory is not usable: %s" % exc) from exc


def _migrate_v1(conn):
    conn.execute(
        "CREATE TABLE seats(show_id TEXT NOT NULL, seat_id TEXT NOT NULL, "
        "row_label TEXT NOT NULL, number INTEGER NOT NULL, "
        "PRIMARY KEY(show_id, seat_id))"
    )
    conn.execute(
        "CREATE TABLE holds(show_id TEXT NOT NULL, seat_id TEXT NOT NULL, "
        "token TEXT NOT NULL CHECK(length(token)=32), "
        "created_at REAL NOT NULL, "
        "expires_at REAL NOT NULL CHECK(expires_at > created_at), "
        "PRIMARY KEY(show_id, seat_id), "
        "FOREIGN KEY(show_id, seat_id) REFERENCES seats(show_id, seat_id))"
    )
    conn.execute(
        "CREATE TABLE meta(key TEXT PRIMARY KEY, value INTEGER NOT NULL)"
    )
    for row in ROW_LABELS:
        for number in range(1, SEATS_PER_ROW + 1):
            conn.execute(
                "INSERT OR IGNORE INTO seats(show_id, seat_id, row_label, number) "
                "VALUES(?,?,?,?)",
                (SHOW_ID, "%s%d" % (row, number), row, number),
            )
    conn.execute("INSERT OR IGNORE INTO meta(key, value) VALUES('version', 0)")


MIGRATIONS = (_migrate_v1,)


class Store:
    def __init__(self, path, clock=time.time, ttl_seconds=DEFAULT_TTL_SECONDS):
        if not isinstance(ttl_seconds, (int, float)) or isinstance(ttl_seconds, bool) \
                or not ttl_seconds > 0:
            raise ValueError("ttl_seconds must be a positive number")
        self.path = str(path)
        self.clock = clock if clock is not None else time.time
        self.ttl_seconds = ttl_seconds
        self._init_db()

    # -- connection / transaction plumbing ---------------------------------

    def _connect(self):
        conn = sqlite3.connect(self.path, timeout=5.0, isolation_level=None)
        try:
            conn.execute("PRAGMA busy_timeout=5000")
            conn.execute("PRAGMA foreign_keys=ON")
        except BaseException:
            conn.close()
            raise
        return conn

    def _init_db(self):
        try:
            conn = self._connect()
        except sqlite3.Error as exc:
            raise StoreInitError("cannot open database %s: %s" % (self.path, exc)) from exc
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("BEGIN IMMEDIATE")
            try:
                version = conn.execute("PRAGMA user_version").fetchone()[0]
                if version > len(MIGRATIONS):
                    raise StoreInitError(
                        "database schema version %d is newer than supported %d"
                        % (version, len(MIGRATIONS))
                    )
                for index in range(version, len(MIGRATIONS)):
                    MIGRATIONS[index](conn)
                    conn.execute("PRAGMA user_version=%d" % (index + 1))
                conn.execute("COMMIT")
            except BaseException:
                try:
                    conn.execute("ROLLBACK")
                except sqlite3.Error:
                    pass
                raise
        except sqlite3.Error as exc:
            raise StoreInitError("cannot initialise database %s: %s" % (self.path, exc)) from exc
        finally:
            conn.close()

    @contextmanager
    def _txn(self, write):
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            try:
                yield conn
            except BaseException:
                try:
                    conn.execute("ROLLBACK")
                except sqlite3.Error:
                    pass
                raise
            else:
                conn.execute("COMMIT")
        finally:
            conn.close()

    def close(self):
        """Connections are per-operation, so there is nothing to release."""

    # -- validation ---------------------------------------------------------

    @staticmethod
    def _check_token(token):
        if not isinstance(token, str) or not TOKEN_RE.fullmatch(token):
            raise StoreError(400, "invalid_request", "Session token must be 32 lowercase hex characters.")

    @staticmethod
    def _check_seat_shape(seat):
        if not isinstance(seat, str) or not SEAT_RE.fullmatch(seat):
            raise StoreError(400, "invalid_request", "Seat ids look like A1 (rows A-C, seats 1-4).")

    def _validate_seats(self, seats):
        if not isinstance(seats, (list, tuple)):
            raise StoreError(400, "invalid_request", "'seats' must be a list of seat ids.")
        if not 1 <= len(seats) <= MAX_SEATS_PER_REQUEST:
            raise StoreError(400, "invalid_request", "'seats' must contain 1 to 12 seat ids.")
        for seat in seats:
            self._check_seat_shape(seat)
        if len(set(seats)) != len(seats):
            raise StoreError(400, "invalid_request", "'seats' must not contain duplicates.")
        return sorted(seats)

    # -- internals ----------------------------------------------------------

    @staticmethod
    def _purge(conn, now):
        cur = conn.execute("DELETE FROM holds WHERE show_id=? AND expires_at <= ?", (SHOW_ID, now))
        return cur.rowcount

    @staticmethod
    def _bump(conn):
        conn.execute("UPDATE meta SET value = value + 1 WHERE key='version'")

    def _known_seats(self, conn):
        return {r[0] for r in conn.execute("SELECT seat_id FROM seats WHERE show_id=?", (SHOW_ID,))}

    def _build_state(self, conn, token, now):
        seat_rows = conn.execute(
            "SELECT seat_id, row_label FROM seats WHERE show_id=? ORDER BY row_label, number",
            (SHOW_ID,),
        ).fetchall()
        holds = {
            seat_id: (owner, expires)
            for seat_id, owner, expires in conn.execute(
                "SELECT seat_id, token, expires_at FROM holds WHERE show_id=? AND expires_at > ?",
                (SHOW_ID, now),
            )
        }
        version_row = conn.execute("SELECT value FROM meta WHERE key='version'").fetchone()
        rows = []
        by_row = {}
        held_count = 0
        for seat_id, row_label in seat_rows:
            if row_label not in by_row:
                by_row[row_label] = []
                rows.append({"row": row_label, "seats": by_row[row_label]})
            if seat_id in holds:
                owner, expires = holds[seat_id]
                held_count += 1
                own = token is not None and hmac.compare_digest(owner, token)
                status = "held_own" if own else "held_other"
                expires_at = expires
            else:
                status = "available"
                expires_at = None
            by_row[row_label].append({"id": seat_id, "status": status, "expires_at": expires_at})
        total = len(seat_rows)
        return {
            "show": {"id": SHOW_ID, "name": SHOW_NAME},
            "version": version_row[0] if version_row else 0,
            "server_time": now,
            "hold_ttl_seconds": self.ttl_seconds,
            "rows": rows,
            "remaining": {"available": total - held_count, "held": held_count, "total": total},
        }

    # -- public operations --------------------------------------------------

    def get_state(self, token=None):
        if token is not None:
            self._check_token(token)
        now = self.clock()
        with self._txn(False) as conn:
            return self._build_state(conn, token, now)

    def hold(self, token, seats):
        """Atomically hold every seat or none. Returns state plus 'held'."""
        self._check_token(token)
        seats = self._validate_seats(seats)
        now = self.clock()
        expires = now + self.ttl_seconds
        with self._txn(True) as conn:
            self._purge(conn, now)
            known = self._known_seats(conn)
            unknown = [s for s in seats if s not in known]
            if unknown:
                raise StoreError(422, "unknown_seat", "Unknown seat: %s." % ", ".join(unknown))
            owners = dict(conn.execute(
                "SELECT seat_id, token FROM holds WHERE show_id=?", (SHOW_ID,)
            ).fetchall())
            conflicts = [s for s in seats if s in owners and owners[s] != token]
            if conflicts:
                raise StoreError(
                    409,
                    "seat_conflict",
                    "Seats already held by someone else: %s. No seats were held." % ", ".join(conflicts),
                    conflicts=conflicts,
                    state=self._build_state(conn, token, now),
                )
            for seat in seats:
                conn.execute(
                    "INSERT INTO holds(show_id, seat_id, token, created_at, expires_at) "
                    "VALUES(?,?,?,?,?) "
                    "ON CONFLICT(show_id, seat_id) DO UPDATE SET "
                    "expires_at = MAX(excluded.expires_at, holds.expires_at) "
                    "WHERE holds.token = excluded.token",
                    (SHOW_ID, seat, token, now, expires),
                )
            self._bump(conn)
            state = self._build_state(conn, token, now)
        state["held"] = seats
        return state

    def release(self, token, seat):
        """Release a hold owned by token; 404 hold_not_found otherwise."""
        self._check_token(token)
        self._check_seat_shape(seat)
        now = self.clock()
        with self._txn(True) as conn:
            self._purge(conn, now)
            if seat not in self._known_seats(conn):
                raise StoreError(422, "unknown_seat", "Unknown seat: %s." % seat)
            cur = conn.execute(
                "DELETE FROM holds WHERE show_id=? AND seat_id=? AND token=?",
                (SHOW_ID, seat, token),
            )
            if cur.rowcount == 0:
                raise StoreError(404, "hold_not_found", "You have no active hold on %s." % seat)
            self._bump(conn)
            state = self._build_state(conn, token, now)
        state["released"] = seat
        return state
