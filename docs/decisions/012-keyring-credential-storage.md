# ADR-012: OS Keychain Credential Storage

**Status**: Accepted
**Date**: 2026-02-24

## Context

Desk stores OAuth client credentials (`credentials.json`) and tokens (`token.json`) as plaintext JSON files in `~/.desk/`. This means secrets like `client_secret`, `token`, and `refresh_token` are readable by any process running as the user. This was flagged as a security concern in desk #11.

A sibling tool in the parent suite already uses the `keyring` library for OS keychain storage, proving the pattern works on macOS (Keychain), Linux (SecretService/KWallet), and Windows (Credential Locker).

## Decision

Use the `keyring` library to store all secrets in the OS keychain. JSON files are retained only for non-sensitive metadata to aid debugging.

### Storage layout

- **Keyring service**: `desk-google`
- **Keys**: `client:credentials` (full `{"installed": {...}}` block as JSON), `oauth:token` (token dict as JSON)
- **Metadata file**: `~/.desk/token.json` contains only non-sensitive fields (scrubs `token`, `refresh_token`, `client_secret`)

### Key API changes

- `_get_oauth_credentials()`: Uses `Credentials.from_authorized_user_info()` for keyring-sourced tokens (instead of `from_authorized_user_file()`)
- `login()`: Uses `InstalledAppFlow.from_client_config()` for keyring-sourced client credentials (instead of `from_client_secrets_file()`)
- `_save_credentials()`: Stores full token in keyring, writes scrubbed metadata to file

### Migration

Transparent, on first access:
1. If keyring is empty and a plaintext file exists, migrate secrets to keyring
2. Write to keyring first (crash-safe: next run sees keyring populated)
3. Scrub secrets from token file; delete credentials file entirely after migration

### CLI interface

`desk auth set-client --client-id X --client-secret Y [--project-id Z]` constructs the full Google `{"installed": {...}}` credentials block with standard defaults and stores it in keyring. Used by the parent suite's install script.

### gcloud ADC path

Unchanged. The gcloud flow manages its own credentials outside our control. When ADC tokens are cached via `_save_credentials()`, they route through keyring like any other token.

### No fallback to plaintext

If the keyring backend is unavailable (null/fail backend), operations fail with a clear error message. No silent downgrade to plaintext storage.

## Alternatives Considered

1. **Encrypted file with user passphrase** — Adds friction on every invocation. Keyring integrates with OS unlock transparently.
2. **Environment variables only** — Doesn't persist across sessions. Still plaintext in shell config files.
3. **Keep plaintext files with strict permissions** — `chmod 600` doesn't protect against other processes running as the same user.

## Consequences

- Depends on `keyring>=25.0` (adds ~50KB, pure Python with native backend adapters)
- Existing users are migrated transparently on first command invocation
- Install scripts use `auth set-client` instead of writing files to disk
- Prior art: KeyringTokenStorage pattern from a sibling tool in the parent suite
