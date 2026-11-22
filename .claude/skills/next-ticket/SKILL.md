---
name: next-ticket
description: Owner-started driver that takes one ready ticket of epic #1 up to a ready pull request. Starting it is the owner's go signal.
argument-hint: "[issue number]"
disable-model-invocation: true
---

# Next ticket

Runs exactly one ticket of epic #1 (#2 to #10) and stops. Only the owner starts it, with `/next-ticket` or `/next-ticket <issue number>`; that is the go signal. It never merges and never starts another run by itself. `CLAUDE.md` wins where this file and it differ.

## Steps

1. **Refresh the queue.** `gh issue list --state open --limit 100 --label status:blocked`. A `status:blocked` ticket whose blockers (the "Depends on" column of the table in epic #1) are all closed becomes `status:ready`. Report each change; the labels are the only GitHub write this step makes.
2. **Pick.** With an issue number, use it, but stop and say why if it is `status:blocked`, `status:in-progress` or `needs-decision`. Without one, take the first `status:ready` ticket in the dependency order of the epic table (#2, #7, #3, #8, #4, #9, #5, #6, #10) that is not `status:in-progress` and not `needs-decision`. If none qualifies, say so and stop.
3. **Claim.** Label it `status:in-progress` (remove `status:ready`).
4. **Branch in a fresh worktree.** `git fetch origin`, then `git worktree add ../seat-map-ticketing-simulator-<issue> -b <issue>-<short-slug> origin/main`, as the Git workflow in `CLAUDE.md` says. Work only in that worktree. Never work on `main`.
5. **Implement.** Follow the [`implement-ticket`](../implement-ticket/SKILL.md) playbook from step 1 to the end, including both gates.
6. **Finish.** The draft pull request is opened only after the local checks passed and Code Reviewer and Reality Checker ran after the last code edit. Then wait for CI on the draft. When CI is green (you check this, not Reality Checker), mark it ready with `gh pr ready` (the gate hook blocks this until both gates ran) and comment on the issue with the pull request link and the evidence summary. If CI is red or a gate does not pass, leave the pull request as a draft and comment with what failed.
7. **Stop.** One ticket per run. Do not merge, do not pick the next ticket, do not release.

## Never

- Merge, push to `main`, release, or edit the epic's ticket text.
- Take a ticket labelled `needs-decision`; an open owner decision is the owner's.
- Change `.claude/agents/`, `LOOP.md`, `loop-constraints.md` or `loop-budget.md`.
