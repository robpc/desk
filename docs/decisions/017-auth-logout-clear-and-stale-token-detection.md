---
id: 017
title: Auth logout/clear commands and stale-token detection
status: accepted
date: 2026-04-27
supersedes: []
superseded_by: null
tags: [auth, cli, recoverability, keyring]
---

# ADR-017: Auth logout/clear commands and stale-token detection

## Context

Desk's auth state lives in the OS keychain (per ADR-012) under two keys: `client:credentials` (the OAuth client config) and `oauth:token` (the user's refreshable token). When these get out of sync — e.g. the stored token was minted against a different OAuth client than the one currently configured, or scopes drift after a `SCOPES` change — `desk` will fail with refresh errors and the user has no first-class way to recover.

Today, the only way to fully reset is manual keychain surgery using the `security` CLI (and digging through Keychain Access). The underlying keyring helpers (`keyring_store.delete_token()`, `keyring_store.clear_all()`) already exist but are not exposed via the CLI. `auth status` doesn't surface enough to even diagnose the mismatch — it shows "credentials in keyring" as a boolean but not the `client_id` or scopes.

This is a high-severity recoverability issue: when auth breaks, the user is stuck.

## Decision

Add two new commands and enrich `auth status`:

### `desk auth logout`

- Removes only the OAuth token from the keychain (preserves client config).
- Idempotent: prints "no token to remove" rather than erroring when nothing is stored.
- Also scrubs any legacy `~/.desk/token.json` so a stale plaintext token can't keep authenticating after logout.
- Supports `--json` for structured output.

### `desk auth clear`

- Removes both the OAuth token and the stored client credentials.
- Confirmation prompt by default; `--yes` to skip.
- In non-interactive mode (no TTY), require `--yes` rather than hanging on the prompt — same pattern as `desk docs delete-tab`.
- `--token` flag to clear only the token.
- `--client` flag to clear only the client config.
- Passing both flags is equivalent to passing neither (clears both).
- Supports `--json`.

### `auth status` enrichments

Adds the following fields to the status payload:

- `client_id`: The OAuth client_id currently configured (from keyring client credentials, or bundled credentials, or token if that's the only source). This is the single most useful field for diagnosing "which client am I authenticating against?"
- `token_client_id`: The client_id baked into the stored token, if different from the configured one. When these differ, the token will not refresh.
- `token_source`: Where the token came from — `keyring`, `file`, `gcloud_adc`, or `none`.
- `scopes`: The scopes attached to the stored token (list of strings).

### Stale-token detection on `set-client`

When `desk auth set-client` runs and the new `client_id` differs from the `client_id` baked into the existing token, automatically delete the stored token (it cannot refresh against a different client). Print a one-line note: `Cleared stored token (was issued for a different client_id).` Only emit the note when a token actually existed and was deleted.

## Alternatives Considered

### Alternative 1: Document the manual keychain surgery in README

**Description**: Tell users to run `security delete-generic-password -s desk-google -a oauth:token` when things break.

**Pros**:
- Zero implementation cost.

**Cons**:
- Requires platform-specific knowledge (Linux uses SecretService, Windows Credential Locker).
- Users who hit this aren't going to read docs first.
- Yahoo security has flagged broad use of the `security` CLI as a risk.

**Why rejected**: Not a real solution. The capability exists in the codebase already; just expose it.

### Alternative 2: `auth reset` instead of `logout` + `clear`

**Description**: One command with subcommands or modes.

**Pros**:
- Single entry point.

**Cons**:
- "logout" is the universal verb users reach for first; not having it is surprising.
- Conflates the common case (sign out, keep client config) with the recovery case (nuke everything).

**Why rejected**: `logout` is muscle memory. `clear` signals "more destructive". Two commands with clear distinct semantics is better.

### Alternative 3: Make `set-client` invalidation opt-in via a flag

**Description**: Require `--reset-token` on `set-client` to clear the existing token.

**Pros**:
- Explicit.

**Cons**:
- The token literally cannot work against a different client_id. Keeping it stored is misleading state, not "preserved" state.
- Users who hit this case will be confused about why login is failing after set-client.

**Why rejected**: Auto-invalidation is the safer default. The one-line stdout note keeps it visible.

## Consequences

### Positive

- Users have a clean recovery path when auth breaks.
- `auth status` is now actually diagnostic (you can see the client_id mismatch instead of guessing).
- `set-client` is self-healing for the most common failure mode it causes.
- No more `security` CLI surgery required.

### Negative

- Slightly larger CLI surface (two new commands, more fields on status).
- `auth status` now reads from keyring more aggressively, which may add a small latency on platforms with slow keyring backends (negligible in practice).

### Neutral

- The legacy `~/.desk/token.json` fallback still exists (per ADR-012's migration path); `logout` now scrubs it explicitly so the semantics match user expectation.

## Implementation Notes

- New helper `keyring_store.delete_client_credentials()` mirrors `delete_token()` (idempotent, returns bool).
- `auth_status` reads from a new helper `_get_status_details()` that resolves `client_id`, `token_client_id`, `token_source`, and `scopes`.
- Tests cover: logout idempotence, clear flag matrix, non-interactive `--yes` enforcement, status field shape, set-client invalidation path.

## References

- ADR-012: OS Keychain Credential Storage
- `src/desk/auth.py`, `src/desk/cli.py`, `src/desk/keyring_store.py`
