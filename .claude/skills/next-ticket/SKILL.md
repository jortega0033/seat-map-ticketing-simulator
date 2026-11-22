---
name: next-ticket
description: Owner-started driver that takes one ready ticket of epic #1 up to a ready pull request. Starting it is the owner's go signal.
argument-hint: "[issue number]"
disable-model-invocation: true
---

# Next ticket

Runs exactly one ticket of epic #1 (#2 to #10 and #13) and stops. Only the owner starts it, with `/next-ticket` or `/next-ticket <issue number>`; that is the go signal. It never merges and never starts another run by itself. `CLAUDE.md` wins where this file and it differ.

## Steps

1. **Refresh the queue.** `gh issue list --state open --limit 100 --label status:blocked`. A `status:blocked` ticket whose blockers (the "Depends on" column of the table in epic #1) are all closed becomes `status:ready`. Then check parents: for each open ticket that has sub-issues (`gh api repos/jortega0033/seat-map-ticketing-simulator/issues/<n>/sub_issues`), if all sub-issues are closed, close it with a comment. Report each change; labels, comments and closing such parents are the only GitHub writes this step makes.
2. **Pick, leaf tickets only.** A ticket labelled `tracking` or with open sub-issues is a container and is never picked. With an issue number: if it is a `tracking` parent, refuse and list its open sub-issues; stop and say why if it is `status:blocked`, `status:in-progress` or `needs-decision`. Without one, take the first `status:ready` leaf ticket in the order of the epic table (#2, #7, #3, #8, #4, #9, #5, #6, #13, #10), a parent's sub-issues in their order inside the parent, that is not `status:in-progress` and not `needs-decision`. If none qualifies, say so and stop.
3. **Claim.** Label it `status:in-progress` (remove `status:ready`).
4. **Branch in a fresh worktree.** `git fetch origin`, then `git worktree add ../seat-map-ticketing-simulator-<issue> -b <issue>-<short-slug> origin/main`, as the Git workflow in `CLAUDE.md` says. Work only in that worktree. Never work on `main`.
5. **Implement.** Follow the [`implement-ticket`](../implement-ticket/SKILL.md) playbook from step 1 to the end, including both gates. Before the gates, write `git diff --stat origin/main...HEAD`, `git diff origin/main...HEAD` and the check outputs to `.claude/state/review/` in the worktree and name those files to Code Reviewer and Reality Checker, which have no shell.
6. **Finish.** The draft pull request is opened only after the local checks passed and both gates ran after the last code edit. If this is the last open sub-issue of a parent, its pull request says `Closes #<sub-issue>` and `Closes #<parent>`. After `gh pr create --draft` and `git push`, bind the pull request to the session when the app offers it and end the turn with the line "Draft pull request #N is waiting for CI". Do not loop, sleep or watch. When woken (a CI event or the owner says "continue"), read `gh pr checks <n>` once: green, then mark it ready with `gh pr ready` (the gate hook blocks this until both gates ran) and comment on the issue with the pull request link, the CI run link and the evidence summary; red, then fix, re-run local checks and both gates, push and end the turn again; still running, end the turn again with the same line. List steps a person must do under "Owner checks" in the pull request.
7. **Stop.** One ticket per run. Do not merge, do not pick the next ticket, do not release.

## Never

- Merge, push to `main`, release, or edit the epic's ticket text.
- Take a ticket labelled `needs-decision`; an open owner decision is the owner's.
- Take a `tracking` ticket or one with open sub-issues.
- Change `.claude/agents/`, `LOOP.md`, `loop-constraints.md` or `loop-budget.md`.
