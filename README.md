# Seat-map Ticketing Simulator

A small offline workbench for inspecting seat holds and race conditions in a fictional venue. Everything runs on your own machine at `127.0.0.1`. There are no customers, payments, accounts or external services.

M1 implements local seat holds. See the baseline verification below.

## Requirements
Python 3.12 or newer. No third-party packages.

## Launch

Linux:
```
python3 -m seat_ticketing --data-dir ./data --port 8765
```
Windows:
```
python -m seat_ticketing --data-dir .\data --port 8765
```
Then open http://127.0.0.1:8765/. The data directory is created if missing. An empty or unusable path exits with code 2.

## M1 smoke steps
1. Open the page. Show A appears with rows A-C and four seats each. Tab to a seat and press Space or Enter to select it.
2. Select A1 and A2, press **Hold selected seats**. The action status says the seats are held; the remaining status reads 10 available, 2 held, 12 total.
3. Open the page in a second browser profile (or private window). A1 and A2 show as held by someone else and are disabled.
4. Stale-view race: with both profiles loaded and A3 available, select A3 in both before pressing hold in either. Hold in the first, then the second. The second shows a conflict and holds nothing.
5. Press **Reload seats** in the second profile to see the current state. Press **Release my holds** in the first to free its seats.
6. Stop the server (Ctrl+C), start it again with the same `--data-dir`, reload: unexpired holds are still present. Holds expire after 120 seconds.

## Limits
One fictional show, 12 seats; max 12 seats per request; 4096-byte request bodies; loopback only; the session token is a pseudonym stored in the browser, not a login. Anyone on the same machine can reach the port.

## Tests
```
python -m unittest discover -s tests
```
(`python3` on Linux.) Tests use temporary directories and an injected fake clock instead of sleeps. Browser-level checks, including the two-context race, are not automated in the baseline.

## Local persistence
SQLite file `seats.sqlite3` inside the data directory, WAL mode. Delete the directory to reset.

## Planned scope
Seating blocks and fixture import; idempotent holds with expiry sweep; simulated checkout and refunds with an append-only ledger; operator panel with live updates; seeded load harness with an independent replay oracle. Details are in [docs/PRD.md](docs/PRD.md).

## Baseline verification

- Windows with Python 3.13.14 and Ubuntu 24.04 WSL with Python 3.12.3 each passed 60 unit and API tests. WSL unit tests used temporary storage on tmpfs.
- Chrome 157 blocked external requests. Two browser contexts competing for seat A1 got one success and one conflict. The winning hold survived a server restart and release restored availability.
