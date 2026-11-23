# UI quality rules

Binding for every screen, page and piece of user-facing copy in this repository. Decided by the owner on 2026-11-22 (see [owner-decisions.md](owner-decisions.md)). The page here is plain HTML, CSS and native JavaScript served by `seat_ticketing/static/`; the rules apply to `app.css`, `index.html` and the strings in `app.js`.

## The rules

1. No thick accent border on one side of a card, callout, alert, list item or quote (for example `border-left: 4px solid <accent>`). Use spacing, type weight, an icon or a full hairline border instead.
2. No "soft tinted background with a thin border of the same hue" as the default way to mark a status, tag, callout or card. One neutral surface and one clear signal (text, icon or a solid chip) is enough.
3. No gradient text and no purple-to-blue gradient as a default accent.
4. No blur or glass panels, and no drop shadow plus large radius on every card.
5. No emoji used as icons or bullets, and no sparkle marks.
6. No pill or badge on things that are not states. No all-caps, letter-spaced micro labels as section decoration.
7. No centred hero with a slogan in an application screen. Screens open on the user's task.
8. One accent colour, used for the primary action and the current selection. Status colours only for status.
9. Dense, aligned layouts on a consistent spacing scale. No card grid where a table or a list is the right form.
10. User-facing copy is plain and specific: no filler, no exclamation marks, and the same word for the same thing everywhere.

## How they are applied

- A UI ticket starts with the `ui-ux-pro-max` skill (`.claude/skills/ui-ux-pro-max/`): run a design-system search for the product type before designing, with `python .claude/skills/ui-ux-pro-max/scripts/search.py "<query>" --design-system`.
- A UI ticket ends with a check of every changed screen against the ten rules above. The pull request lists the result under Evidence.
- User-facing copy, documentation and pull request text go through the `unslop` skill (`.claude/skills/unslop/`) before the pull request is opened.
- The Frontend Developer, UI Designer (where installed), UX Architect (where installed), Accessibility Auditor and Code Reviewer roles name this file in their checklists.
- Enforcement is by the review gate (Code Reviewer on every ticket), not by a script. Rule 1 can be linted; rule 2 cannot be detected reliably from CSS.
- Rule 8 is read with the "Where yellow is used" section of [design-tokens.md](design-tokens.md) and owner decision 14 in [owner-decisions.md](owner-decisions.md): the accent also marks the current step, and `--focus` is a focus indicator, exempt from the accent limit.
- Colours come from the Pipenzo tokens in [design-tokens.md](design-tokens.md); new UI adds no colour literals.
- The repository rules in `CLAUDE.md` still apply: no external font, image or script, no `innerHTML`, no inline style or script.
