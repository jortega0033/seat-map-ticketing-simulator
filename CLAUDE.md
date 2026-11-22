# CLAUDE.md

Working instructions for this repository. Read this file first, then the documents it links to. It does not repeat them.

## What this is

An offline workbench for inspecting seat holds and race conditions in a fictional venue. One Python package, standard library only, serving a JSON API and a static page on `127.0.0.1`, with one SQLite file as storage. M1 (one show, 12 seats, atomic holds with expiry) is implemented. P1 to P5 are planned and tracked in the epic, issue #1.

## Sources of truth

| Topic | Document |
|---|---|
| Product scope, milestones, contracts, fixture, acceptance matrix | [docs/PRD.md](docs/PRD.md) |
| How the code is built, the traced hold workflow, invariants, differences between the PRD and the code | [docs/architecture.md](docs/architecture.md) |
| Launch, smoke steps, limits, baseline verification | [README.md](README.md) |
| Backlog | Epic issue #1 and its nine sub-issues (#2 to #10) on GitHub. The epic lists them in dependency order with estimates. |
| Loop setup and its limits | [LOOP.md](LOOP.md), [loop-constraints.md](loop-constraints.md) |
| Project subagents and their origin | [.claude/agency-agents/README.md](.claude/agency-agents/README.md) |

When the PRD and the code disagree, the code is the baseline and [docs/architecture.md](docs/architecture.md) records the difference. A ticket that changes a contract updates PRD section 6 in the same pull request.

## Setup

Python 3.12 or newer. Nothing to install: there is no package manifest, no virtual environment requirement, no build step and no lint step. On Windows the interpreter is `python`; on Linux it is `python3`.

## Commands

Both were run during preparation on Windows 11 with Python 3.13.14, from the repository root.

Run the tests (60 tests, about 5 seconds):

```
python -m unittest discover -s tests
```

Run the server (binds `127.0.0.1` only; the data directory is created if missing; stop with Ctrl+C):

```
python -m seat_ticketing --data-dir ./data --port 8765
```

`--port 0` picks a free port and prints it. Without `--port` the default is 8080. `data/` and `*.sqlite*` are ignored by Git; use a scratch directory outside the repository for experiments and delete it afterwards.

Quick check that a running server answers:

```
curl -s http://127.0.0.1:8765/api/v1/health
```

Expected: `{"status": "ok", "api_version": 1}`.

A single test: `python -m unittest tests.test_store.HoldTests.test_expiry_with_fake_clock`.

## Hard rules

These come from PRD sections 4 and 11. A change that breaks one needs the owner's approval first, not a pull request.

- Standard library only, in the application and in the tests. No pip or npm dependency, no build tooling, no CDN, font, image or script from another host.
- Loopback only. The server binds `127.0.0.1`. No CORS headers. No outgoing request from the server, the page, the tests or a harness.
- No real customers, payments, cards, accounts, mail or sign-in. Amounts are integer units in a simulation. The session token is a pseudonym.
- Tests use a temporary directory, port 0 and an injected fake clock. No `sleep`, no wall-clock waits, no fixed port.
- Server text reaches the page through `textContent` and attributes only, never `innerHTML`. No inline script or style (the CSP forbids it).
- Static files are served from the fixed allowlist in `seat_ticketing/server.py`. Request input is never joined into a file path.

## Architecture boundaries

Details and line references are in [docs/architecture.md](docs/architecture.md). The short form:

- `seat_ticketing/__main__.py`: command line only. Parses arguments, maps start-up failures to exit codes 2 and 1.
- `seat_ticketing/server.py`: HTTP only. Routing, request guards (Host, Origin, token header, body cap, media type), JSON encoding, static allowlist, security headers. It never runs SQL.
- `seat_ticketing/store.py`: domain rules and SQLite. Schema migrations by `PRAGMA user_version`, one connection per operation, every write inside one `BEGIN IMMEDIATE` transaction, time from the injected clock. It never touches HTTP objects. It does raise `StoreError` with an HTTP status and error code, which the server passes through; keep new domain errors in that one pattern.
- `seat_ticketing/static/`: one page, native JavaScript, no framework. It talks to the server through `/api/v1` only.
- `tests/`: `unittest`. `test_store.py` drives the store directly, `test_server.py` drives a real server on port 0 over `http.client`, `test_cli.py` drives `main()`.

Keep new code on the correct side of these lines. A new module is fine when a file would otherwise take on a second job (for example an import validator or an oracle).

Invariants that every change must keep:

- A seat has at most one live hold. `PRIMARY KEY(show_id, seat_id)` on `holds` is the last guard; the conflict check inside the write transaction is the first.
- A multi-seat hold is all or nothing. A conflict or an unknown seat writes no row.
- Existing databases open under new code. A schema change is a new entry in `MIGRATIONS`, never an edit of an old one, with a test that opens a database made by the previous version.
- Mutating routes check Host and Origin. All of them except `POST /api/v1/session`, which issues the token, need `X-Session-Token`. Error responses use the envelope `{"error": {"code", "message"}}` and never contain a traceback.
- A session token is never shown to another session: the state reports `held_own` or `held_other`, not the owner.

## Git workflow

- `main` is the default branch. CI runs on every pull request (see Delivery workflow); checks are also run locally and reported with their output.
- One branch per issue. The repository has no naming rule yet; `<issue-number>-<short-slug>` is the suggested form. Small commits with imperative subjects and a type prefix, as in the existing history (`feat:`, and by extension `fix:`, `docs:`, `test:`, `chore:`).
- Open a draft pull request that names the issue (`Part of #1`, `Closes #n`). Do not merge your own pull request and do not push to `main`.
- Never commit a data directory, a SQLite file, `.env*`, or `.prep/`.
- Do not change `.claude/agents/`, `LOOP.md`, `loop-constraints.md` or `loop-budget.md` as part of a feature ticket.

## Evidence before a ticket is called done

Put these in the pull request description. Paste real output; do not summarise a run you did not make.

1. The full output tail of `python -m unittest discover -s tests` from a clean checkout, with the Python version and the operating system. State the test count before and after the change.
2. For each acceptance criterion of the issue: the name of the test that proves it, or the exact manual step and what was observed.
3. For a schema change: the test that opens a database created by the previous schema version, and the new `user_version`.
4. For a new or changed route: one request and response pair per success and per error code, taken from a server started with `--port 0` on a scratch data directory, and the PRD section 6 diff.
5. For a change under `seat_ticketing/static/`: a browser run on `http://127.0.0.1:<port>/` with the browser name and version, the viewport sizes checked (800x600 and 360 px wide), keyboard-only operation of the changed controls, and the console free of errors and of blocked or external requests. Browser checks are manual: the repository has no approved browser automation (PRD section 14).
6. `git status` showing no stray files, and confirmation that no dependency, external URL or non-loopback listener was added.
7. Green CI on the pull request, with the run link.
8. Anything not verified, said plainly.

## Agent roles

Project subagents are in `.claude/agents/`. Nine are Agency Agents roles; `loop-verifier` belongs to the Loop below and is not part of ticket work. Sources, licence, local changes and the name collision with a user-level install are in [.claude/agency-agents/README.md](.claude/agency-agents/README.md).

Each of the nine role files starts with a section "In this repository", written for this project: the stack and hard rules that bind the role, the files it owns or reviews, its commands or the evidence it must be given, its checklist and what it hands back. That section and this file override the generic upstream text below it.

When asked to implement, continue or finish a GitHub issue, follow the playbook [`.claude/skills/implement-ticket/SKILL.md`](.claude/skills/implement-ticket/SKILL.md). Claude Code loads it on its own for ticket work; `/implement-ticket <issue number>` starts it by hand. Delegate to the roles without waiting to be asked; the "Use proactively ..." sentence at the end of each role's `description` is what makes Claude Code do so.

| When | Role and trigger | Access |
|---|---|---|
| Before coding | Codebase Onboarding Engineer (unfamiliar area); Software Architect (module boundary, data model, schema, public API or dependency) | read-only |
| While coding | Backend Architect (`seat_ticketing/*.py`); Frontend Developer (`seat_ticketing/static/`) | can edit |
| While coding | Database Optimizer (SQL, schema, migrations, indexes) | read-only |
| After coding | API Tester (new or changed route, status code or contract; writes tests in `tests/`) | can edit |
| After coding | Accessibility Auditor (page markup, keyboard handling, focus) | read-only |
| Every ticket | Code Reviewer (review gate), then Reality Checker (acceptance gate) | read-only |

- The two gates run on every ticket, however small. The other roles run when their trigger matches the change.
- Read-only roles have `tools: Read, Grep, Glob` and cannot run commands: give them the diff, the acceptance criteria and the recorded command output.
- The session or role that wrote a change does not count as its reviewer.
- The pull request description lists each role that ran, what it was asked and its verdict, under "Agent roles run".

## Delivery workflow

How a ticket gets from the backlog to a ready pull request. Each piece has one home; this part only links them.

- **Driver and playbook.** The owner starts a ticket with `/next-ticket` ([`.claude/skills/next-ticket/SKILL.md`](.claude/skills/next-ticket/SKILL.md)); it runs [`implement-ticket`](.claude/skills/implement-ticket/SKILL.md). No scheduler: the owner's go signal starts every run.
- **Review gate hook.** [`.claude/hooks/role_gate.py`](.claude/hooks/role_gate.py) blocks `gh pr create` and `gh pr ready` until Code Reviewer and Reality Checker ran after the last code edit. `ROLE_GATE=off` in the environment Claude Code is started from switches it off for that session.
- **Permissions.** [`.claude/settings.json`](.claude/settings.json): documented commands allowed; force pushes, pushes to `main`, `gh pr merge`, releases and reads of `.env` denied; edits to CI, agent configuration and Loop files ask first.
- **CI.** [`.github/workflows/ci.yml`](.github/workflows/ci.yml): job `test` on Linux and Windows, Python 3.12 and 3.13. It must be green before a pull request is marked ready.
- **Pull request.** [`.github/pull_request_template.md`](.github/pull_request_template.md). Code owner: [`.github/CODEOWNERS`](.github/CODEOWNERS).
- **Labels.** `status:ready`, `status:blocked`, `status:in-progress`, `needs-decision`. A `needs-decision` ticket is not started.
- **Changelog.** Every ticket pull request adds one line to [`CHANGELOG.md`](CHANGELOG.md) under Unreleased.
- **UI and writing.** [docs/ui-quality.md](docs/ui-quality.md) (ten binding rules; skills `ui-ux-pro-max` and `unslop` in `.claude/skills/`).
- **Decisions.** [docs/owner-decisions.md](docs/owner-decisions.md) records the owner's decisions. Changing one needs the owner; stop and say so if one blocks a ticket.
- **Merge and release.** Only the owner merges and releases ([docs/RELEASING.md](docs/RELEASING.md), [SECURITY.md](SECURITY.md)).

## Loop

Issue triage runs at L1: report-only, started by hand, no scheduler, no GitHub writes. See [LOOP.md](LOOP.md).
