---
name: implement-ticket
description: Playbook for implementing a GitHub issue in this repository from start to pull request, with the project subagents run at fixed steps. Use whenever asked to implement, start, continue or finish a ticket, an issue or an epic child, for example "implement #12" or "work on the next ticket".
argument-hint: "[issue number]"
---

# Implement a ticket

Use this playbook for every implementation ticket in this repository. `CLAUDE.md` holds the commands, the architecture boundaries, the Git workflow and the evidence rules; where this playbook and `CLAUDE.md` differ, `CLAUDE.md` wins.

The project subagents in `.claude/agents/` are part of the work. Delegate to them at the steps below without waiting to be asked. If a step names a role that is not installed, do that step yourself and say so in the pull request.

## Steps

1. **Read the ticket.** `gh issue view <number>` and the epic it belongs to. If it is labelled `tracking` or has open sub-issues, it is a container: stop and work its first open sub-issue instead. Check that every prerequisite issue is closed and that no owner decision named in the ticket is still open. If the ticket is blocked, stop and say what blocks it.
2. **Read the rules.** `CLAUDE.md`, then the architecture notes it links to.
3. **Orient and check the approach.** Delegate as the table "Before coding" says. Settle open design questions before writing code. For a ticket that changes the page (`seat_ticketing/static/`), start with the `ui-ux-pro-max` skill: run its design-system search for the product type (`python .claude/skills/ui-ux-pro-max/scripts/search.py "<query>" --design-system`) and read `docs/ui-quality.md`.
4. **Branch** as the Git workflow in `CLAUDE.md` says. Never work on the default branch.
5. **Implement** inside the ticket's stated scope. Delegate the work to the implementing role that matches the files being changed (table "While coding"). Do not widen scope; note anything else you find as a follow-up.
6. **Test.** Add or change tests for every acceptance criterion and material edge case, then run the checks listed in `CLAUDE.md`. Record each command and its result.
7. **Specialist review.** Run every role in the table "After coding" whose trigger matches the change.
8. **UI check.** For a ticket that changes a screen, check every changed screen against the ten rules of `docs/ui-quality.md` and record the result as evidence.
9. **Write the text.** Run user-facing copy and documentation through the `unslop` skill before the gates, so they judge the final diff.
10. **Changelog.** Add one line to `CHANGELOG.md` under Unreleased.
11. **Review gate, always.** Run Code Reviewer on the full diff. Fix every material finding, re-run the checks, and have the reviewer look again until no material finding is left.
12. **Acceptance gate, always.** Run Reality Checker with the ticket's acceptance criteria and the local evidence you produced. It checks that the documented checks ran locally and passed and that CI is configured to run them; it does not need a CI result. Do not open a pull request unless it passes.
13. **Hand off.** Run the pull request text through `unslop`, capture the evidence `CLAUDE.md` asks for and open a draft pull request from `.github/pull_request_template.md` that names the issue (if it is the last open sub-issue of a parent, `Closes #<sub-issue>` and `Closes #<parent>`), only after the local checks passed and both gates ran after the last code edit. Push, bind the pull request to the session if the app offers it, and end the turn with "Draft pull request #N is waiting for CI"; do not loop, sleep or poll. When woken, read `gh pr checks <n>` once. If CI fails, fix, re-run the local checks and both gates, and push. When CI is green, add the run link to the pull request description and mark it ready. Only the owner merges and releases; do not merge.

## Roles

### Before coding

| Role | Access | Delegate to it |
|---|---|---|
| Codebase Onboarding Engineer | read-only reviewer | At the start of a ticket in an unfamiliar area, to trace the relevant code paths before anything is changed |
| Software Architect | read-only reviewer | Before implementing a ticket that adds or changes a module boundary, data model, storage schema, public API or dependency, to check the approach against the architecture notes |

### While coding

| Role | Access | Delegate to it |
|---|---|---|
| Backend Architect | can edit | When a ticket changes server-side code, HTTP routes, validation, persistence or data migrations |
| Database Optimizer | read-only reviewer | When a ticket changes SQL, the schema, indexes or query paths |
| Frontend Developer | can edit | When a ticket changes browser-side code such as pages, components, client state, styling or keyboard interaction |

### After coding

| Role | Access | Delegate to it |
|---|---|---|
| Accessibility Auditor | read-only reviewer | After a ticket changes user-facing UI, keyboard handling, focus order or markup |
| API Tester | can edit | After a ticket adds or changes an HTTP endpoint, status code or request and response contract |

### Gates that run on every ticket

| Role | Access | Delegate to it |
|---|---|---|
| Code Reviewer | read-only reviewer | After implementing or changing code for a ticket, before the work is called done or a pull request is opened |
| Reality Checker | read-only reviewer | As the acceptance gate of every ticket, after Code Reviewer and before the draft pull request is opened, to check each acceptance criterion against evidence that was actually produced before the ticket is called done |

## Rules

- The session or role that wrote a change does not count as its reviewer.
- Read-only reviewers cannot run commands. Before calling them, write `git diff --stat origin/main...HEAD`, `git diff origin/main...HEAD` and the recorded check outputs to `.claude/state/review/` in the ticket worktree (git-ignored), name those files and the acceptance criteria in the request.
- Where a role's general advice (frameworks, dependencies, cloud services) conflicts with `CLAUDE.md`, `CLAUDE.md` wins.
- A criterion that needs a person (by hand in a normal browser, manual and recorded): do as much as you can (a scripted or headless run, with the evidence) and list the rest under "Owner checks" in the pull request.
- Never change agent configuration (`.claude/agents/`, `.claude/skills/`, `.claude/hooks/`, `.claude/settings.json`, `.claude/agency-agents/`) in a ticket, also not through a shell command.
- In the pull request description, add a section "Agent roles run" listing each role that ran, what it was asked and its verdict, and any step you did yourself because a role was missing.
