# Architecture and PRD reconciliation

Written 2026-11-22 against commit `12b1a48` (the M1 baseline). It records how the code is built, one workflow traced from its entry point to storage, the invariants, and where [PRD.md](PRD.md) and the code differ. Line references are to that commit.

Each statement carries one of these marks:

- **Implemented (run)**: observed in a test run or over HTTP during preparation.
- **Implemented (read)**: read in source, not exercised separately.
- **Planned**: in the PRD or an issue, not in the code.
- **Needs verification**: claimed by a document, not reproduced during preparation.

What was run during preparation, on Windows 11 with Python 3.13.14:

- `python -m unittest discover -s tests`: `Ran 60 tests in 4.574s`, `OK`.
- `python -m seat_ticketing --data-dir <scratch> --port 8791`, then steps 1 to 5 of the PRD section 7 fixture with `curl` against `127.0.0.1`. Results are in section 2.

No browser was started. Everything about the page in a browser is marked "Needs verification".

## 1. Shape of the system

A three-layer monolith on the Python standard library, plus a static page.

| Layer | File | Job | Must not |
|---|---|---|---|
| Command line | `seat_ticketing/__main__.py` | Parse `--data-dir` and `--port`, start the server, map start-up errors to exit codes (2 for an unusable data directory, 1 for a port that cannot be bound) | Contain domain or HTTP logic |
| HTTP adapter | `seat_ticketing/server.py` | `ThreadingHTTPServer` on `127.0.0.1`, hand-written router, request guards, JSON envelope, static allowlist, security headers | Run SQL |
| Domain and storage | `seat_ticketing/store.py` | Schema and migrations, hold and release rules, state view, expiry, all SQLite access | Touch HTTP request or response objects |
| Page | `seat_ticketing/static/{index.html,app.js,app.css}` | Seat map, selection, hold, release, reload, 5 second poll | Use anything outside `/api/v1` and its own three files |
| Tests | `tests/test_{store,server,cli}.py` | `unittest` against the store, a real server on port 0, and `main()` | Sleep, use a fixed port, write outside a temporary directory |

Known leak across the boundary: `StoreError` carries an HTTP status and an error code (`store.py:26-35`), and `ApiError.from_store` passes them through (`server.py:62-69`). The store therefore knows HTTP status numbers. This is deliberate in the baseline and cheap; new domain errors should follow the same single pattern instead of adding a second one.

## 2. Traced workflow: hold A1 and A2, then lose a race on A2

| Step | What happens | Where | Mark |
|---|---|---|---|
| Start | `python -m seat_ticketing --data-dir D --port N` runs `main()`, which calls `prepare_data_dir` and `create_server` | `__main__.py:20-31`, `store.py:42-55`, `server.py:389-390` | Implemented (run) |
| Storage start-up | `SeatServer.__init__` builds a `Store` on `D/seats.sqlite3`. `_init_db` switches to WAL, reads `PRAGMA user_version` and applies missing migrations inside one `BEGIN IMMEDIATE`. Migration 1 creates `seats`, `holds`, `meta` and seeds the 12 seats of Show A from constants | `server.py:339-353`, `store.py:110-138`, `store.py:58-85`, `store.py:14-17` | Implemented (run) |
| Listen | `_HTTPServer` binds `127.0.0.1` and skips the reverse DNS lookup | `server.py:72-88`, `server.py:345` | Implemented (run) |
| Page start | `app.js` reads `localStorage["seatmap.token"]`; if absent it calls `POST /api/v1/session`, which returns `secrets.token_hex(16)` | `app.js:37-45`, `app.js:75-86`, `server.py:310-315` | Server side: Implemented (run). Browser side: Needs verification |
| First load and poll | `GET /api/v1/shows/show-a`, then a 5 second poll that refreshes the map without touching the action message | `app.js:359-375`, `app.js:203-217` | Needs verification (browser) |
| Hold request | `doHold` posts `{"seats": [...]}` with `X-Session-Token` | `app.js:269-302` | Needs verification (browser); the same request over `curl` is Implemented (run) |
| Routing | `_route` takes the path from the raw request line, `_match` maps it to a handler and its allowed methods | `server.py:223-239`, `server.py:200-221` | Implemented (run) |
| Guards | `_h_holds` checks Host and Origin, requires a well-formed token, reads a body of at most 4096 bytes, requires `application/json`, refuses more than 64 opening brackets, parses JSON | `server.py:321-327`, `server.py:243-295` | Implemented (run): `ValidationTests` in `tests/test_server.py` passed; the Origin check was also seen over HTTP |
| Transaction | `Store.hold` validates shapes, then inside one `BEGIN IMMEDIATE`: delete expired holds, reject unknown seats with 422, collect seats held by another token and raise 409 with the conflicts and a fresh state, otherwise upsert one row per seat (own rows keep the later expiry), bump `meta.version`, build the state | `store.py:247-283`, `store.py:140-156` | Implemented (run) |
| Result | 201 with the state plus `held`. A `StoreError` becomes the error envelope | `server.py:164-184`, `server.py:128-132` | Implemented (run) |
| Storage | Rows in `holds` of `D/seats.sqlite3` | `store.py:64-71` | Implemented (run): the file was created |

Observed over HTTP (two tokens, new data directory):

| PRD section 7 step | Observed |
|---|---|
| 1. T1 holds A1, A2 | 201, held A1 A2, remaining 10/2/12, version 1 |
| 2. T2 holds A2, B1 | 409 `seat_conflict`, conflicts A2, remaining 10/2/12, version still 1 |
| 3. T2 holds B1, B2 | 201, remaining 8/4/12, version 2 |
| 4. T2 releases A1 | 404 `hold_not_found` |
| 5. T1 releases A1 | 200, remaining 9/3/12, version 3 |
| 6. Clock to 1120 | Not run over HTTP (needs the fake clock). Covered by `tests/test_store.py` `test_expiry_with_fake_clock` and `tests/test_server.py` `test_expiry_via_fake_clock`, which passed |

Also observed: `POST /api/v1/session` with `Origin: http://example.invalid` returned 403 `forbidden_origin`; `GET /api/v1/shows/show-b` returned 404 `show_not_found`.

## 3. Data ownership and invariants

- **Single source of truth.** One SQLite file, `seats.sqlite3`, in the data directory. Every operation opens and closes its own connection with `busy_timeout=5000` and `foreign_keys=ON` (`store.py:100-108`). There is no in-process cache or shared state besides the file. Implemented (read).
- **Schema version.** `PRAGMA user_version`, with ordered migrations in `MIGRATIONS` (`store.py:85`). A database newer than the code is refused at start-up (`store.py:120-124`). Implemented (run, `SchemaTests`).
- **State version.** `meta.version` is bumped once per successful hold and per successful release (`store.py:191-193`, `store.py:280`, `store.py:300`). See finding D5 for what it does not count.
- **Time.** All time comes from the `clock` passed to `Store` (`store.py:89-95`). Tests inject a fake clock.
- **One hold per seat.** `PRIMARY KEY(show_id, seat_id)` on `holds` (`store.py:69`). Implemented (run, `ConcurrencyTests`).
- **All or nothing.** A conflict or an unknown seat raises inside the transaction, which rolls back (`store.py:147-152`). Implemented (run).
- **Row guards.** `CHECK(length(token)=32)` and `CHECK(expires_at > created_at)` (`store.py:66-68`). Implemented (run).
- **Expiry.** A hold is expired when `expires_at <= now`. Reads filter expired rows (`store.py:206`); writes delete them first (`store.py:187-189`). Implemented (run).
- **Own re-hold.** Holding a seat you already hold keeps the later of the two expiry times and does not change `created_at` (`store.py:272-278`). Implemented (run).
- **Request guards.** Host and Origin are checked on mutating routes only (`server.py:243-251`). `GET` routes have no Host check. Body cap 4096 bytes (`server.py:25`, `server.py:273`). Chunked bodies are refused (`server.py:264-265`). Socket timeout 10 s (`server.py:26`, `server.py:99`). Implemented (run, `ValidationTests`).
- **Responses.** Every response carries `Content-Security-Policy`, `X-Content-Type-Options: nosniff`, `Cache-Control` and `Connection: close` (`server.py:109-122`). The handler speaks HTTP/1.0 (`server.py:98`). Implemented (run, `test_security_headers_on_api_and_errors`).
- **Static files.** A dictionary of three paths (`server.py:36-40`). Implemented (run, `StaticTests`).

## 4. PRD compared with the code

| PRD item | Status | Evidence |
|---|---|---|
| M1: Show A, rows A to C, four seats each | Implemented (run) | `store.py:14-17`, `test_seed_and_schema` |
| Per-browser token | Server: Implemented (run). Storage in the browser: Needs verification | `server.py:315`, `app.js:37-45` |
| Atomic multi-seat hold | Implemented (run) | `store.py:247-283`, HTTP steps 1 to 3 above |
| 120 second expiry | Implemented (run) | `store.py:20`, fake-clock tests |
| Release | Implemented (run) | `store.py:285-303`, HTTP steps 4 and 5 |
| Persistence across restart | Implemented (run) | `test_restart_retains_holds`, `test_restart_retention_same_db` |
| API v1 and error envelope (section 6) | Implemented (run), with the omissions in D3 and D4 | `server.py:200-221`, `server.py:128-139` |
| Security and validation (section 11) | Implemented (run), with the addition in D7 | `server.py:24-40`, `server.py:243-295` |
| Acceptance matrix rows 1 to 8 | Implemented (run) | the 60 tests |
| Acceptance matrix rows 9 to 11 (keyboard, two-context race, 800x600) | Needs verification | README reports a Chrome 157 run; not reproduced |
| Section 8, responsiveness and accessibility | Needs verification | `app.css` has `:focus-visible` (line 74) and one breakpoint at 420 px (line 111); not checked in a browser |
| P1: seating blocks and import | Planned | no import route, seats seeded from constants; issue #2 |
| P2: idempotent holds, sweep, reconciliation | Planned | no `Idempotency-Key` handling anywhere; issue #3 |
| P3: checkout, refunds, ledger | Planned | no order or ledger table; issue #4 |
| P4: operator panel, server-sent events | Planned | the page polls every 5 s; issue #5 |
| P5: load harness and replay oracle | Planned | no such module; issue #6 |

### Findings

| Id | Finding | Effect | Evidence |
|---|---|---|---|
| D1 | PRD section 12 ends with "tests authored; none run as of this document". The README records 60 passing tests, and 60 passed during preparation. | The PRD status line is stale. | `PRD.md:116`, `README.md:47` |
| D2 | PRD section 15 says the backlog assumes import from the data directory. Issue #2 specifies `POST /api/v1/shows/import` with a JSON body. | The two disagree on how an inventory file reaches the server. The issue is the more specific text. | `PRD.md:133`, issue #2 |
| D3 | The state object also contains `show {id, name}`; a successful release adds `released`. PRD section 6 lists neither. | Contract text is incomplete. | `store.py:229-236`, `store.py:302` |
| D4 | The server also returns 404 `show_not_found`, 411 with code `payload_too_large` for a chunked body, and 500 `internal_error`. PRD section 6 lists only the status numbers 404, 413 and 500. | Contract text is incomplete. | `server.py:213`, `server.py:265`, `server.py:179` |
| D5 | Expiry never changes `version`. Reads filter by time and write nothing. A write deletes expired rows, but if the operation then fails the delete is rolled back with it, and if it succeeds only the operation's own bump happens. `_purge` returns a row count that no caller uses. | A seat can go from held to available with no version change. PRD section 6 says `version` is "bumped per state change". This matters for anything that treats `version` as a complete change history: the sweep in P2, the event stream in P4 and the replay oracle in P5. | `store.py:187-189`, `store.py:254`, `store.py:291`; `test_expiry_with_fake_clock` asserts the unchanged version |
| D6 | The seat id grammar `[A-C][1-4]`, the limit of 12 seats per request and the wording of two error messages are constants. | P1 must replace all of them together with the schema. | `store.py:18`, `store.py:23`, `store.py:171`, `store.py:177` |
| D7 | A JSON body with more than 64 `[` or `{` characters is refused with 400 before parsing. PRD section 11 does not list this guard. | The guard counts raw bytes, so a `[` or `{` inside a string counts too. The planned Show B inventory (6 structural brackets, a few hundred bytes) would pass both this guard and the 4096 byte cap, and even 20 blocks need only 42 structural brackets. A valid inventory can still exceed either limit: bracket characters in names count towards the 64, and 20 blocks with long names and many row labels pass 4096 bytes. The cap and the guard must become per-route. | `server.py:25`, `server.py:273`, `server.py:289-291` |
| D8 | One show is assumed in every layer: `SHOW_ID` is a constant used in every query, the router accepts only `show-a`, the page hard-codes the path, the title and the heading. | "Multi-block" in the epic title needs changes in the store, the router and the page. Issue #2 names only the store and the import route. | `store.py:14`, `store.py:188-207`, `server.py:212`, `app.js:5`, `index.html:6`, `index.html:12` |
| D9 | The handler speaks HTTP/1.0 and closes every connection; each request has its own thread and a 10 s socket timeout. | A long-lived event stream needs its own response path, its own timeout handling and a cap on open streams. | `server.py:98-99`, `server.py:116-122` |
| D10 | The command line default port is 8080; the README and the PRD use 8765 in their examples. | No conflict. Noted so that nobody "fixes" one of them. | `__main__.py:26` |
| D11 | Issue #5 keeps a change log of 500 entries for reconnecting clients. Issue #6 replays "the change log" of a run of 2000 operations. | A log bounded at 500 cannot hold a 2000 operation run. One of the two needs a different retention rule or a different source. | issues #5 and #6 |
| D12 | No issue covers the page for more than one show: choosing a show, drawing blocks, or sending an import. | Without it Show B is reachable only with `curl`. | issues #2 to #6, `app.js:5` |

D1 to D4 are documentation fixes. D5 to D9 are facts an implementer must design around. D11 and D12 are gaps in the backlog. The batch plan attached to the epic (#1) assigns each of them to a ticket.

## 5. Risks for the planned work

- **P1 changes four things at once**: the schema (migration 2 on a database that already has holds), the seat id grammar, the routes and the body reader. The migration test must start from a real version 1 file.
- **Idempotency must share the hold transaction.** A stored result written outside the `BEGIN IMMEDIATE` that creates the holds can disagree with them after a crash.
- **The ledger and the change history are two different things.** The ledger in P3 records amounts per order. The oracle in P5 needs every seat transition, including expiry (D5).
- **Lock waits under load.** Eight clients writing through per-operation connections wait on `busy_timeout=5000`. A `database is locked` error surfaces as a 500 today (`server.py:175-180`). The load harness will show whether that happens; do not assume it does not.
- **Event streams hold threads.** `ThreadingHTTPServer` starts one daemon thread per request (`server.py:72-77`). Streams must be counted and must end on shutdown.
- **No browser automation.** Every change to the page is checked by hand. PRD section 14 requires separate approval for a browser driver.
- **Windows and port reuse.** `allow_reuse_address` is off on Windows (`server.py:76`), so a test that restarts a server on the same fixed port can fail there. Tests use port 0.
