# Design tokens

The page uses the Pipenzo "Flow look" tokens: a black page in dark mode, Flow-style alpha layers, one accent (Pipenzo yellow `#FECE02`, used as described under "Where yellow is used"), and red only for danger.

## Source and resync

- Source: `jortega0033/clip-to-reel-studio`, `extension/sidepanel/tokens.css` at commit `a13378ce73e5b27213c9a200fc960ec93afef054` (2026-11-21).
- Copy: `seat_ticketing/static/tokens.css`, served at `/static/tokens.css`. Do not edit it.
- Resync: copy the file over the old one. Nothing else.

## Token names by role

- Surfaces: `--bg`, `--bg-raised`, `--surface`, `--bg-sunken`, `--hero-bg`, `--ink`.
- Text: `--fg`, `--muted`, `--faint`, `--on-ink`, `--on-ink-muted`, `--on-hero`, `--on-hero-muted`, `--on-primary`, `--on-media`.
- Lines and focus: `--border`, `--hairline`, `--control-border`, `--input-border`, `--ink-border`, `--focus`.
- Accent: `--primary`, `--primary-press`, `--primary-edge`.
- Status: `--success`, `--ok`, `--ok-bg`, `--warn-fg`, `--warn-bg`, `--danger`, `--danger-bg`, `--info`.
- Alpha layers: `--glass*`, `--scrim`, `--state-hover`, `--state-selected`, `--btn-secondary*`, `--ring-accent`.
- Shadow, type, space, radius, motion: `--shadow-*`, `--font*`, `--mono`, `--space-*`, `--radius-*`, `--dur-*`, `--ease-*`.

## Rule

New UI uses these tokens. No new colour literals (hex, `rgb()`, `hsl()`, named colours) in `app.css`, `app.js` or `index.html`. Text never sits on a bare alpha layer (see the header of `tokens.css`).

## Where yellow is used

- The yellow accent (`--primary`) is used for the primary action, the current-step marker and the current selection (UI rule 8 in [ui-quality.md](ui-quality.md)). Decided by the owner on 2026-11-23.
- A selection is marked with a solid `--primary` fill and `--on-primary` text. A yellow border alone is not enough: it has about 1.5:1 contrast against white in the light theme. A selection also carries a second sign that is not colour (weight, an icon or text) and the matching aria attribute (for example `aria-pressed` or `aria-selected`). Never a tint with a border of the same hue, and never a thick border on one side.
- `--focus` is a focus indicator and is exempt from the accent limit, including where it is yellow in the dark theme. A ticket that says the focus style stays unchanged means the rule on `main` after the token pull request.
- Contrast and no-colour-alone checks cover both themes: the light block (`:root`) and the dark block of `tokens.css`.
- This document takes precedence over the header comment of `tokens.css`. That comment is narrower: it lists yellow only on the primary button, the current-step node and a few small marks, and does not mention selection. It is left as it is, because the copy must stay identical to the source.
- Status: the page does not follow this yet. It still marks a selected seat in a neutral colour (a double border in `app.css`). The page follows in ticket work.

## Light and dark

Dark is the primary design. The `:root` block holds the light theme; a `prefers-color-scheme: dark` block overrides it. The operating system colour scheme decides, with no switch in the page and no script. `tokens.css` is linked before any other stylesheet, so `app.css` loads after it in `index.html`. A ticket that creates a page or its static allowlist links `tokens.css` first and serves it (the allowlist and its test).
