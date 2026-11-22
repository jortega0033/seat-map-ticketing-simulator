# AGENTS.md

The full repository instructions are in [CLAUDE.md](CLAUDE.md). This file repeats only what an agent needs before it reads that.

## Test commands

```
python -m unittest discover -s tests
```

(`python3` on Linux.) Python 3.12 or newer, standard library only. There is no lint step, no build step and no package manifest. Do not add pip or npm dependencies.

## Run

```
python -m seat_ticketing --data-dir ./data --port 8765
```

The server binds `127.0.0.1` only. Stop it with Ctrl+C.

## Loop conventions

- The loop runs at L1: report-only, started by hand. It proposes; it does not label, comment, close, edit source, push or merge.
- No scheduler and no workflow file is installed. Do not add one without the owner's approval.
- See [LOOP.md](LOOP.md) for the manual command and the human gates.
