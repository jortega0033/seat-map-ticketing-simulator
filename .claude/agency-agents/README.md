# Agency Agents roles used in this repository

The Markdown files in `.claude/agents/` whose names start with `engineering-` or `testing-` are copies of role definitions from Agency Agents. They are project-local Claude Code subagents. The file `loop-verifier.md` in the same folder is not from Agency Agents; it belongs to the Loop Engineering setup described in [`LOOP.md`](../../LOOP.md).

## Source and licence

- Upstream: https://github.com/msitarzewski/agency-agents
- Pinned revision: `8ae6164602c95ca78828b148b9052460ee426885` (upstream `main`, committed 2026-11-09)
- Licence: MIT, "Copyright (c) 2025 AgentLand Contributors". The upstream licence text at the pinned revision is kept unchanged in [`LICENSE`](LICENSE) next to this file (SHA-256 `9a45258434d5cedf0af73c9ad4771373701225038d246c49219026c33677f66f`). It covers only the copied role files, not the rest of this repository.
- Fetched with `gh api -H "Accept: application/vnd.github.raw" "repos/msitarzewski/agency-agents/contents/<path>?ref=<revision>"`.

## Installed roles

"Upstream SHA-256" is the hash of the file as fetched at the pinned revision. Reviewer roles have one added frontmatter line, `tools: Read, Grep, Glob`, so they cannot edit files or run commands. Nothing else in any file was changed.

| File in `.claude/agents/` | `name:` | Upstream path | Upstream SHA-256 | Local change |
|---|---|---|---|---|
| `engineering-software-architect.md` | Software Architect | `engineering/engineering-software-architect.md` | `b85121691776147bacde26673e68fbbacd6a7f0816d1ca8e203c264d25ce1d30` | added `tools: Read, Grep, Glob` |
| `engineering-code-reviewer.md` | Code Reviewer | `engineering/engineering-code-reviewer.md` | `7509fcc3ea1dda46511b2801996305bf3d4a125576f9655ff0b63df25602f446` | added `tools: Read, Grep, Glob` |
| `engineering-codebase-onboarding-engineer.md` | Codebase Onboarding Engineer | `engineering/engineering-codebase-onboarding-engineer.md` | `07aa548b45887c3ad768efad5fdbf6e57bea639df4f1b74c7e383142f454e2a1` | added `tools: Read, Grep, Glob` |
| `engineering-database-optimizer.md` | Database Optimizer | `engineering/engineering-database-optimizer.md` | `6d773003e3b9251068ab537be94d6827c118201e0e17c11d789cb29dc245bf99` | added `tools: Read, Grep, Glob` |
| `testing-accessibility-auditor.md` | Accessibility Auditor | `testing/testing-accessibility-auditor.md` | `362935907af23839775b9c6162f38c0c5a740542ab4350cb5c5b5a0d9f9a4268` | added `tools: Read, Grep, Glob` |
| `testing-reality-checker.md` | Reality Checker | `testing/testing-reality-checker.md` | `6d32fcdb114233e13902ec6372d50293b120e85d490b5e81d372c29808f988a1` | added `tools: Read, Grep, Glob` |
| `engineering-backend-architect.md` | Backend Architect | `engineering/engineering-backend-architect.md` | `ac717bde4848d7663fff8a3c7edc711fd119256de6a7ce38c036619372f42c99` | none |
| `engineering-frontend-developer.md` | Frontend Developer | `engineering/engineering-frontend-developer.md` | `1ae4cc10b2e0163bd3ed921ad54080b865cd02e591becd8919b64b73fab06dad` | none |
| `testing-api-tester.md` | API Tester | `testing/testing-api-tester.md` | `ab91de9188d48bd9c417282c33673a37b066215e90e08c0f1b270d036084e3bb` | none |

## Why these roles

| Role | Use in this repository |
|---|---|
| Software Architect (read-only) | Review a ticket's design against the layering in [`docs/architecture.md`](../../docs/architecture.md) before code is written: where show and block data lives, how idempotency shares the hold transaction, how the change history and the ledger differ, how an event stream fits a thread-per-request server. |
| Code Reviewer (read-only) | Review a diff for correctness, missed edge cases and broken invariants (one hold per seat, all-or-nothing writes, request guards on new routes, no traceback in responses). |
| Codebase Onboarding Engineer (read-only) | Trace a code path and report facts with file and line citations. |
| Database Optimizer (read-only) | Review schema changes, migrations, triggers, indexes and transaction scope in `seat_ticketing/store.py`. Four planned tickets add tables, and the product is about write contention on one SQLite file. |
| Accessibility Auditor (read-only) | Review keyboard operation, focus return, labels, live regions and text alternatives to colour. PRD section 8 makes these requirements, and the operator panel ticket carries them as acceptance criteria. |
| Reality Checker (read-only) | Compare claimed evidence with what was actually run before a ticket or the epic is called done. |
| Backend Architect | Implement work in `seat_ticketing/*.py` (HTTP layer, storage and migrations, validation, harness). |
| Frontend Developer | Implement work in `seat_ticketing/static/`. |
| API Tester | Write the HTTP-level `unittest` cases in `tests/` for new and existing routes. |

Most of these roles are written for larger stacks. Backend Architect, Frontend Developer and API Tester mention frameworks, cloud services, Postman, k6 and Playwright; Database Optimizer is written around PostgreSQL and MySQL. In this repository the rules in [`CLAUDE.md`](../../CLAUDE.md) win: Python standard library only, SQLite, native HTML, CSS and JavaScript, `unittest`, no pip or npm dependencies, no external requests.

Roles that were considered and left out: Performance Benchmarker (its method is built on k6 and Core Web Vitals; the planned load harness is a standard-library module with its own acceptance criteria), Test Automation Engineer and Evidence Collector (browser automation needs a dependency this repository does not allow; browser checks are manual and recorded).

## Name collision with user-level agents

A developer who has installed Agency Agents in `~/.claude/agents/` already has agents with the same `name:` values. Claude Code gives the project-level definition precedence, so inside this repository the copies here are used, including the read-only tool limits. The upstream names were kept on purpose so that the roles stay recognisable and can be compared with upstream.

A Claude Code session that was already running when these files were added keeps the definitions it loaded at start. Start a new session to pick up the project copies.

## Check that the roles load

From the repository root, in a new session:

```text
claude -p "List the project-level subagents defined in .claude/agents with the tools each one may use. Then run the Reality Checker subagent and ask it which tools it has."
```

The six reviewer roles and `loop-verifier` must report exactly `Read, Grep, Glob`.

### What was observed, and what was not

Observed on 2026-11-22 with Claude Code 2.1.323, headless (`claude -p`, model requested: haiku, no MCP servers), from the repository root, on a machine that also has a user-level Agency Agents install:

- All ten names were listed. Software Architect, Code Reviewer, Codebase Onboarding Engineer, Database Optimizer, Accessibility Auditor, Reality Checker and `loop-verifier` were listed with `Read, Grep, Glob`. Backend Architect, Frontend Developer and API Tester were listed with all tools.
- A launched Reality Checker and a launched Database Optimizer each reported exactly `Read`, `Grep`, `Glob`. The user-level copies of the six reviewer roles are identical to the pinned upstream files and have no `tools:` line, so the tool limits show that the project copies were the ones loaded.
- The user-level copies of the three implementing roles on that machine are an older upstream revision with different example code. Each role was launched and asked to quote its own instructions, and each quoted text that exists only in the project copy: Backend Architect listed the tables `users`, `categories`, `products` (the user-level copy has no `categories` table), Frontend Developer quoted the comment "Renderable cell values and stable IDs keep the example self-contained.", and API Tester quoted `import { randomUUID } from 'node:crypto';`. This shows project precedence for these three on that machine.
- **Not shown:** behaviour in an interactive session, and behaviour on a machine without a user-level install (there the ten names must simply be listed).
- The listing gives names and tools only, not the file a definition comes from. The statements above about which copy was loaded rest on the tool limits and the quoted text.

## Updating

Fetch the same paths at a newer revision, re-apply the `tools:` line to the six reviewer roles, and update the revision and hashes in this file in the same commit.
