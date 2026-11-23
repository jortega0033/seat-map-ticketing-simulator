# Owner decisions

Dated record of the owner's decisions for this repository. Changing any entry needs the owner; an agent that finds a decision blocking a ticket stops and says so. Entry 11 of the owner's general list (Rust verified in CI only) does not apply: this repository has no Rust.

| # | Decision | Date | Implemented in |
|---|---|---|---|
| 1 | The instructions, tooling and playbook live on the default branch (`main`). | 2026-11-22 | `CLAUDE.md`, `.claude/`, `.github/` |
| 2 | Persona agents run automatically during ticket work and carry instructions tailored to this project. | 2026-11-22 | `.claude/agents/` ("In this repository" sections), `.claude/skills/implement-ticket/SKILL.md` |
| 3 | Every open ticket is about app implementation; tooling is installed, not ticketed. | 2026-11-22 | `CLAUDE.md` (Delivery workflow), epic #1 |
| 4 | Agents may take a ticket up to a ready pull request. Only the owner merges and releases. | 2026-11-22 | `.claude/skills/next-ticket/SKILL.md`, `.claude/settings.json` (deny rules), `docs/RELEASING.md` |
| 5 | No scheduler. Ticket work starts only on the owner's go signal (`/next-ticket`), because the repository is used to train AI models. | 2026-11-22 | `.claude/skills/next-ticket/SKILL.md` (`disable-model-invocation: true`), `LOOP.md` |
| 6 | A review gate hook blocks opening or readying a pull request until the gate roles have run after the last code edit. | 2026-11-22 | `.claude/hooks/role_gate.py`, `.claude/settings.json` (hooks) |
| 7 | Loop Engineering stays at L1, report-only and unscheduled. | 2026-11-22 | `LOOP.md` |
| 8 | Continuous integration runs on Linux and Windows; the default branch requires a pull request and green checks. | 2026-11-22 | `.github/workflows/ci.yml`; branch protection is set on GitHub by the owner's orchestrator |
| 9 | Permission rules: documented commands are allowed; force pushes, pushes to the default branch, merges, releases and reads of secrets are denied; edits to CI, agent configuration and Loop files ask first. | 2026-11-22 | `.claude/settings.json` |
| 10 | Open decisions on tickets are settled with the ticket's stated default (list below). | 2026-11-22 | Epic #1, "Decisions fixed for this batch"; `.claude/skills/implement-ticket/SKILL.md` step 1 (open owner decisions) |
| 12 | The ten UI rules are binding; the `ui-ux-pro-max` and `unslop` skills are installed and used for UI work and for copy. | 2026-11-22 | `docs/ui-quality.md`, `.claude/skills/ui-ux-pro-max/`, `.claude/skills/unslop/` |
| 13 | Visual system: Pipenzo Flow look tokens (docs/design-tokens.md). SDLC kit version: jortega0033/sdlc-kit v1.0.0. | 2026-11-23 | `seat_ticketing/static/tokens.css`, `docs/design-tokens.md` |
| 14 | Yellow accent, focus ring, themes, token linking and one plan button: D1 to D5 in the entry below. | 2026-11-23 | `docs/design-tokens.md` |

## Entry 14: yellow accent and token rules (2026-11-23)

  - D1 Current selection: the yellow accent is used for the primary action, the current-step marker and the current selection (UI rule 8). Decided by the owner on 2026-11-23. How (recommended by the orchestrator, adopted under the owner's delegation of the same day): a selection uses a solid --primary fill with --on-primary text (not only a yellow border, which has about 1.5:1 against white on light), plus a second sign that is not colour (weight, icon or text) and the existing aria attribute. Never a tint with a same-hue border and never a thick one-sided border.
  - D2 Focus ring: --focus is a focus indicator, exempt from the accent limit, including where it is yellow in dark. A ticket that says the focus style stays unchanged means the rule on main after the token pull request. Recommended by the orchestrator, adopted under the owner's delegation of 2026-11-23.
  - D3 Themes: contrast and no-colour-alone checks cover both the light and the dark block of tokens.css. Recommended by the orchestrator, adopted under the owner's delegation of 2026-11-23.
  - D4 Linking: a ticket that creates a page or its static allowlist links tokens.css before any other stylesheet and serves it (allowlist and its test). Recommended by the orchestrator, adopted under the owner's delegation of 2026-11-23.
  - D5 release-dependency-planner: while a plan is open only one yellow primary button shows; "New plan" (#new-plan) becomes neutral, in ticket #11. Recommended by the orchestrator, adopted under the owner's delegation of 2026-11-23.

## Entry 10: decisions settled by the ticket's stated default

  - #1 (applies to #2, #7): How an inventory file reaches the server (PRD section 15). Default applied: JSON body of `POST /api/v1/shows/import`; the page reads a picked file and posts it; the server never opens a path from a request.
  - #1 (applies to #2): Import and existing shows. Default applied: Import creates a show and never replaces one; an existing id is refused; no edit or delete of a show in this batch.
  - #1 (applies to #3): Holding a seat you already hold (PRD section 15). Default applied: It extends the hold (baseline behavior).
  - #1 (applies to #3, #4, #8): Meaning of `version`. Default applied: One counter for the whole database; one increment per change as listed in the epic; refused and replayed idempotent requests do not raise it.
  - #1 (applies to #3, #4, #5): Hold group semantics. Default applied: Group keeps its seats and one shared expiry; expiry does not remove the group; fixed order of 404 `hold_group_not_found`, 409 `hold_expired`, 409 `hold_group_stale`.
  - #1 (applies to #4, #8): Change log versus ledger. Default applied: Separate; ledger never pruned; change log keeps the newest N entries (`--change-log-limit`, default 500).
  - #1 (applies to #9): Poll versus event stream (PRD section 15). Default applied: Stream in #9 replaces the 5 s poll; poll stays as fallback when the stream is unavailable.
  - #1 (applies to #7, #5, #10): Browser automation tooling (PRD section 15). Default applied: None added; browser checks are manual and recorded (PRD section 14).
  - #1 (all tickets): Dependencies and network. Default applied: No new dependency, build step, external request or non-loopback listener in the app, tests or harness.
  - #1 (applies to #4, #8, #9): Session tokens in output. Default applied: Never shown in a response about another session, the change log, the ledger or the stream; a derived pseudonym is used.

The defaults above live in epic #1; the tickets themselves state no other defaults.

No ticket states an open owner decision without a default.
