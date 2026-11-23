# Design tokens

The page uses the Pipenzo "Flow look" tokens: a black page in dark mode, Flow-style alpha layers, one accent (Pipenzo yellow `#FECE02`), and red only for danger.

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

New UI uses these tokens. No new colour literals (hex, `rgb()`, `hsl()`, named colours) in `app.css`, `app.js` or `index.html`. Yellow only on the primary action and the current-step marker; text never sits on a bare alpha layer (see the header of `tokens.css`).

## Light and dark

Dark is the primary design. The `:root` block holds the light theme; a `prefers-color-scheme: dark` block overrides it. The operating system colour scheme decides, with no switch in the page and no script. `app.css` is loaded after `tokens.css` in `index.html`.
