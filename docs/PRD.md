# Seat-map Ticketing Simulator: PRD and Technical Spec

Status legend: **[Implemented baseline]** = implemented in M1 (see [baseline verification](../README.md#baseline-verification)); **[Future]** = planned, not built.

Reconciliation with the code at the M1 baseline (what is implemented, planned, and still to be verified, plus findings D1 to D12 where this document and the code or the backlog differ) is in [architecture.md](architecture.md).

## 1. Intended user and workflow

A single small-event operator working offline on their own machine who wants to see how seat holds and race conditions behave in a fictional venue before any real integration.

Workflow: start the local server, open the page, select seats, hold them, open a second browser profile (another pseudonymous session), try to take the same seat from a stale view, observe the conflict, release, reload, restart the server and see holds persist, watch holds expire.

## 2. Milestones

| Milestone | Content | Status |
|---|---|---|
| M1 | Fictional Show A, rows A-C x 4 seats, keyboard seat map, per-browser token, atomic multi-seat hold, 120 s expiry, release, SQLite persistence | [Implemented baseline] |
| P1 | Seating blocks, fixture import | [Future] |
| P2 | Idempotent holds, sweep, reconciliation | [Future] |
| P3 | Simulated checkout, refunds, audit ledger | [Future] |
| P4 | Operator panel, SSE updates | [Future] |
| P5 | Seeded load harness and replay oracle | [Future] |

## 3. Epic and future stories

**Epic: Inspectable seat-hold and race behavior for multi-block fictional venues.** Each story becomes a tracked issue with fuller acceptance criteria; summaries here.

| Key | Story | Depends on | Key acceptance |
|---|---|---|---|
| P1 | As an operator I define seating blocks and import a secret-free inventory file so I can test venues beyond Show A. | none | Show B fixture = 40 seats (24+16); duplicate seat rejected atomically; limits 20 blocks / 2000 seats / 256 KiB; credential-like fields rejected. |
| P2 | As an operator I can replay a hold after a lost response and get the original result, and see expiry swept. | P1 | Same Idempotency-Key -> identical body, one row set; hold visible at t=119, gone at t=120 on fake clock; extend is all-or-nothing. |
| P3 | As an operator I can simulate checkout and cancellation with an append-only ledger in integer units. | P2 | A1+A2 at 2500 = 5000 total, 2 ledger rows atomically; refund 5000 nets order to 0; ledger UPDATE/DELETE blocked. |
| P4 | As an operator I see live updates and can recover missed versions after reconnect. | P3 | Last-Event-ID 9 -> events 10,11,12 once; `resync` beyond 500-entry log; max 8 streams. |
| P5 | As an operator I can run a seeded load and verify results with an independent oracle. | P4 | Seed 42, 8 clients, 2000 ops: one winner per seat, zero phantom transitions; broken store detected; measured throughput/latency reported. |

Dependencies: P1 -> P2 -> P3 -> P4 -> P5. No external packages are required; any later need must be offline-plannable and approved before it is staged.

## 4. Scope boundaries

In: loopback server, single user, one fictional venue in M1, SQLite file in the user's chosen data directory, static HTML/CSS/JS.
Out (all milestones): payments, cards, mail, user sign-in, remote sync, deployment, real customer data, external media or services, non-loopback listeners, build tooling.

## 5. System stack [Implemented baseline]

Python 3.12 stdlib: `http.server.ThreadingHTTPServer`, `sqlite3`, `unittest`. Static files are served from an allowlist of three paths. Browser: native JS, no framework. Package layout: `seat_ticketing/{__main__,server,store}.py`, `seat_ticketing/static/`, `tests/`.

Launch: `python -m seat_ticketing --data-dir <path> --port <port>` (Windows), `python3 -m seat_ticketing --data-dir <path> --port <port>` (Linux). Binds `127.0.0.1` only. Exit code 2 on empty or unusable data dir.

## 6. Contracts [Implemented baseline]

The sections below are the contract; `seat_ticketing/server.py` and `store.py` implement it.

### API
- `GET /api/v1/health` -> `{"status":"ok","api_version":1}`
- `POST /api/v1/session` -> 201 `{"token":"<32 hex>"}`; client sends it as `X-Session-Token`.
- `GET /api/v1/shows/show-a` -> state: `version`, `server_time`, `hold_ttl_seconds`, `rows[].seats[]{id,status,expires_at}`, `remaining{available,held,total}`. Status is `available`, `held_own`, or `held_other`.
- `POST /api/v1/shows/show-a/holds` body `{"seats":["A1","A2"]}` -> 201 with state and `held`; 409 `seat_conflict` with `conflicts` and fresh `state`.
- `DELETE /api/v1/shows/show-a/holds/{seat}` -> 200 or 404 `hold_not_found`.
- Error envelope `{"error":{"code","message"}}`; codes 400 `invalid_request`, 401 `token_required`, 403 `forbidden_origin`, 404, 405, 409, 413 `payload_too_large`, 415, 422 `unknown_seat`, 500.

### Schema (user_version 1)
`seats(show_id, seat_id, row_label, number)`, `holds(show_id, seat_id PK, token CHECK length 32, created_at, expires_at CHECK > created_at)`, `meta(key, value)` with `version` bumped per state change.

### Hold algorithm
`BEGIN IMMEDIATE`; delete holds with `expires_at <= now`; validate all requested seats; if any is held by another token roll back with 409 and insert nothing; otherwise insert new rows and refresh own existing rows; bump version; commit. Time comes from an injectable clock (default `time.time`, TTL 120 s).

### UI
One page with seat map (`#seat-map`, buttons whose accessible name starts with the seat label, e.g. "A1, available"), `#hold-button` "Hold selected seats", `#release-button`, `#reload-button`, `#selection-summary`, `#action-status` (success/conflict/error) and a separate `#remaining-status`. Token kept in `localStorage["seatmap.token"]`. A 5 s poll refreshes the map but never overwrites the action message and keeps selected seats that others took, so a stale submit still returns an explicit 409; manual Reload unselects them with a note. Server text is set via `textContent` only.

## 7. Deterministic fixture

Show A, rows A-C, seats 1-4, TTL 120, fake clock at t=1000.

| Step | Token | Action | Expected |
|---|---|---|---|
| 1 | T1 | hold A1,A2 | 201, held [A1,A2], remaining 10/2/12 |
| 2 | T2 | hold A2,B1 | 409 conflicts [A2]; B1 not held; remaining 10/2/12 |
| 3 | T2 | hold B1,B2 | 201; remaining 8/4/12 |
| 4 | T2 | release A1 | 404 hold_not_found |
| 5 | T1 | release A1 | 200; remaining 9/3/12 |
| 6 | clock -> 1120 | GET | T1's A2 and T2's B1,B2 all expired; remaining 12/0/12 |

## 8. Responsiveness and accessibility

Usable at 800x600 and 360 px wide without horizontal body overflow; system fonts; `:focus-visible`; labelled controls; status in live regions; state shown with text, not color alone; contrast >= 4.5:1; native button keyboard behavior (Tab, Enter, Space).

## 9. Errors, retry, restart, concurrency

- Conflict never leaves partial holds. The client keeps still-available selected seats after any failure and does not retry automatically; the user re-submits.
- Network failure shows a recoverable message; Reload refetches.
- Restart: same data dir retains unexpired holds; expired ones are ignored on read and deleted on next write.
- Concurrency: writes serialized by SQLite `BEGIN IMMEDIATE`; PRIMARY KEY on (show, seat) is the last-line guard. Two contexts with a stale view submitting A1: exactly one 201, the other 409.

## 10. Versioning

API under `/api/v1`; schema by `PRAGMA user_version` with ordered, idempotent migrations; state `version` is a monotonic counter.

## 11. Security and validation

Loopback bind; Host and Origin checks on mutation; no CORS headers; CSP `default-src 'self'`; body cap 4096 bytes; at most 12 seats per hold; seat id regex `^[A-C][1-4]$`; token regex `^[0-9a-f]{32}$`; static allowlist (no path joins from request); per-connection timeout 10 s; no tracebacks in responses. Tokens are random and carry no personal data. The session token is a pseudonym, not an authenticator; anyone on the local machine can reach the port.

## 12. Acceptance matrix (M1)

| # | Check | Method |
|---|---|---|
| 1 | Health and `/` return 200 | unittest |
| 2 | Disjoint holds both succeed | unittest |
| 3 | Overlapping hold -> 409, zero rows added | unittest |
| 4 | Expiry at exactly ttl via fake clock | unittest |
| 5 | Restart retains active holds | unittest |
| 6 | N threads hold the same seat -> exactly one winner | unittest |
| 7 | Foreign Host/Origin -> 403; oversize -> 413; bad shape -> 400 | unittest |
| 8 | Static traversal attempts -> 404 | unittest |
| 9 | Seat button names start with label; keyboard operable | manual / browser |
| 10 | Two contexts select A1 before submit: one success, one conflict | browser |
| 11 | No body overflow at 800x600 | manual / browser |

Status: tests authored; **none run as of this document**.

## 13. Sample demo

1. Start the server on port 8765 with a new data dir.
2. Context 1 and Context 2 (separate profiles) open `/`.
3. Both select A1. Context 1 holds: "Held A1". Context 2 holds: conflict message, remaining count unchanged by it.
4. Context 2 reloads: A1 shows "held by someone else" and is disabled.
5. Stop and restart the server on the same data dir; Context 1 reloads and still sees A1 as its own hold.
6. Release; A1 is available again.

## 14. Test plan

Unit/integration with `unittest` against a server on port 0 with a temp dir and a fake clock (no sleeps). Browser checks (acceptance 9-11) are performed manually or with a locally installed browser driver that is approved separately; none is required by the baseline.

## 15. Open choices

- Whether P1 imports from a file picker or only from the data directory (backlog assumes the data directory).
- Whether own re-hold should extend (baseline) or conflict.
- Whether the 5 s poll should be replaced by SSE earlier than P4.
- Browser automation tooling for acceptance 10, to be approved before use.
