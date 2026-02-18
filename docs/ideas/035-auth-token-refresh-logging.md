---
id: 035
title: Auth Token Refresh Logging
status: implemented
effort: S
value: Agents and users see "Not authenticated" with no explanation when token refresh fails silently
created: 2026-02-08
updated: 2026-02-08
adr: null
---

# Idea 035: Auth Token Refresh Logging

## Problem

When `token.json` exists but the refresh token is expired/revoked, `get_credentials()` returns `None` silently. The user sees "Not authenticated" and has no idea whether they need to re-login, fix their credentials, or something else. This is especially bad for agent workflows where the agent can't diagnose the issue.

## Sketch

- Log the specific reason token refresh failed (expired, revoked, scope mismatch, network error)
- Surface a user-facing hint alongside "Not authenticated" (e.g., "Token expired — run `desk auth login` to re-authenticate")
- Keep the debug-level logging for full tracebacks

## Value Signal

Hit this in practice — desk stopped working between sessions, no indication why. Had to read the source to understand what happened.

## Effort Guess

S — small change to auth.py error handling paths.
