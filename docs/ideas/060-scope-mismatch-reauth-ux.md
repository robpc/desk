---
id: 060
title: Scope-Mismatch Re-Auth UX
status: implemented
effort: S
value: When a new scope is added, tell the user to re-auth instead of a misleading "request access" error
created: 2026-06-09
updated: 2026-06-09
adr: docs/decisions/030-slides-authoring-refinements-and-scope-ux.md
---

# Idea 060: Scope-Mismatch Re-Auth UX

## Problem

When Desk adds a new OAuth scope (e.g. `presentations` for Slides, ADR-026), an existing
token that predates the scope keeps working for old services but fails new ones with a
Google 403 "insufficient authentication scopes". The command handlers classify any 403 as
`PERMISSION_DENIED` and emit the suggestions "You may not have access… / Request access
from the owner" — which are **actively misleading**: the user owns the resource, they just
haven't granted the new scope. The real fix is `desk auth login`, and nothing says so.

This is cross-cutting (every future scope addition hits it), not Slides-specific. Surfaced
by real-world Slides testing (2026-06-09).

## Sketch

Two complementary moves:

1. **Classify the error correctly.** When a 403's payload mentions
   "insufficient authentication scopes" / "ACCESS_TOKEN_SCOPE_INSUFFICIENT", map it to the
   existing `ErrorCode.INSUFFICIENT_SCOPES` (whose suggestions already say "Run
   `desk auth login` to re-authenticate with updated scopes") instead of
   `PERMISSION_DENIED`. This is a small change in each service's `_handle_api_error`
   (or a shared classifier).
2. **Proactively detect scope drift.** Compare the token's granted scopes against
   `config.SCOPES` (the granted set is on the stored credentials). Surface it in
   `desk auth status` ("missing scopes: presentations — run `desk auth login`"), and
   optionally warn before a call that needs a missing scope.

## Open Questions

- [ ] Are granted scopes reliably available on the stored credentials object across auth
      methods (OAuth file vs gcloud ADC vs keyring)?
- [ ] Should a missing-scope situation auto-prompt re-auth in interactive mode, or just
      message clearly? (Probably message only — don't surprise-launch a browser.)
- [ ] Centralize the 403 classification so every service benefits, vs per-service edits.

## Value Signal

Direct user feedback: the current error sends users down the wrong path (sharing/access)
when the answer is a one-command re-auth. Affects onboarding to every new capability.

## Effort Guess

S — Error reclassification is small; `auth status` scope-diff is a modest addition.

## Notes

- `ErrorCode.INSUFFICIENT_SCOPES` and its suggestions already exist in `agent.py`; this is
  mostly about routing to it and detecting drift.
- Related: [[slides-phased-rollout]].
