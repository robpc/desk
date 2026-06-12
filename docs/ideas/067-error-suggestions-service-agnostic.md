---
id: 067
title: Service-Agnostic INVALID_INPUT Suggestions (stop leaking Gmail help)
status: implemented
effort: S
value: Non-mail errors no longer suggest "desk mail search" / "Message IDs are hex"
created: 2026-06-09
updated: 2026-06-09
adr: docs/decisions/030-slides-authoring-refinements-and-scope-ux.md
---

# Idea 067: Service-Agnostic INVALID_INPUT Suggestions

## Problem

`ERROR_SUGGESTIONS[INVALID_INPUT]` in `agent.py` was Gmail-specific (legacy from the
project's Gmail-CLI origin): "Message IDs are hex strings… use `desk mail search`". Because
INVALID_INPUT is the generic validation code used by every service, docs/forms/drive/cal
**and** slides all leaked Gmail guidance on validation/API errors. The deck-builder hit it
on slides (`insert-text`/`place` on a table emitted mail help); confirmed pervasive.

## What was implemented

- Made the global `INVALID_INPUT` default service-agnostic ("Check the command's arguments
  and any IDs…", "See the command's --help…").
- Preserved mail's genuinely-useful message-ID guidance by setting it **explicitly** in
  `mail`'s `_handle_api_error` (mail's own inline flag-validation errors, which were never
  about IDs, are now correctly generic too).

Fixes slides/docs/forms/drive/cal at the root in one change; no tests asserted the mail
text; mail behavior preserved by a guard test.

## Notes

- Live-verified: slides table error now shows generic suggestions, no "desk mail search".
- Exit codes were also reported as unreliable, but could NOT be reproduced — all slides
  error paths return exit 1 when measured directly (the "exit 0" was a PIPESTATUS artifact).
- Related: [[slides-phased-rollout]].
