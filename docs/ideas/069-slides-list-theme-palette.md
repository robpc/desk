---
id: 069
title: Slides — list the active theme palette
status: idea
effort: S
value: Let agents see what ACCENT1..6 / DARK1 / LIGHT1 resolve to in this deck
created: 2026-06-09
updated: 2026-06-09
adr: null
---

# Idea 069: Slides — list the active theme palette

## Problem

`style`/`format` accept theme color names (`ACCENT1..6`, `DARK1/2`, `LIGHT1/2`) — great for
"match the deck" — but an agent has **no way to see what those names resolve to** in the
current presentation, or even discover the names beyond the help text. Reported from the
styling pass.

## Sketch

Surface the deck's color scheme: either `desk slides theme <id>` or `inspect --theme`,
dumping each theme color name → its rgb value, read from the presentation/master color
scheme (`pres.masters[].pageProperties.colorScheme` / slide-level overrides).

## Open Questions

- [ ] Where to read the authoritative scheme (master vs layout vs slide overrides)?
- [ ] Standalone `theme` command vs a flag on `inspect`. (Lean: `inspect --theme` keeps it
      with the rest of the structure dump.)
- [ ] Untested: does `--color` accept CSS names like `red`? Document the accepted forms.

## Value Signal

Direct ask from the styling test pass; small and self-contained.

## Effort Guess

S — read the color scheme from the presentation and format it.

## Notes

- Related: [[slides-phased-rollout]]; ADR-028 (color vocabulary).
