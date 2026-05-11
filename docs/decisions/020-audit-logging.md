# ADR-020: Audit Logging

**Status**: Accepted
**Date**: 2026-05-07

## Context

Desk is the open-source CLI for Google Workspace, distributed for
Yahoo-internal use via the atrium installer (see atrium's
[ADR-001](https://github.com/yahoo-orion/atrium/blob/main/docs/decisions/001-org-specific-layer.md)
on the org-specific layer pattern). The PSR for desk and cafe
([PPSE-43152](https://ouryahoo.atlassian.net/browse/PPSE-43152))
flagged the absence of SIEM-side observability of tool activity as a
gap. Atrium
[ADR-004](https://github.com/yahoo-orion/atrium/blob/main/docs/decisions/004-audit-logging-pattern.md)
defines the shared audit-logging pattern every atrium-managed tool
implements. This ADR records desk's adoption.

The pattern was deliberately designed to be useful for both Yahoo-corp
users and the broader OSS audience — the syslog destination degrades
naturally for non-corp users (writes to the host's syslog where it's
available, falls back silently otherwise), and the local audit file is
useful in either case.

## Decision

Desk follows atrium ADR-004. Refer there for the rationale, shared
event shape, and what is intentionally not logged (subcommand
arguments, document contents, OAuth tokens).

### Desk-specific event names

| Event | Fields | When |
|---|---|---|
| `event=auth_start` | (none) | `desk auth login` begins the OAuth flow |
| `event=auth_complete` | (none) | OAuth token stored in keychain (ADR-012) |
| `event=auth_logout` | (none) | `desk auth logout` clears the keychain entry |
| `event=auth_clear` | (none) | `desk auth clear` clears both client config and token (per ADR-019 / cherry-picked from yahoo-orion/desk#52) |
| `event=session_invalid` | (none) | Stored token detected as invalid on first API call |
| `event=cmd` | `subcmd=<top-level>` `exit=<code>` | Every command invocation |

`subcmd` is the top-level Click command name (e.g. `mail`, `drive`,
`docs`, `sheets`, `calendar`, `auth`), not the full subpath.

### Implementation

- New module `src/desk/audit.py` exposes `get_audit_logger(config_dir)`
  per atrium ADR-004's reference implementation.
- The root Click group initializes the logger and stores it on
  `ctx.obj` for subcommands.
- A `result_callback` emits `event=cmd` after every successful
  subcommand invocation.
- Auth lifecycle events are emitted from the existing `desk.auth`
  paths.

### Log destinations

- **Local**: `~/.desk/audit.log` (mode 0600, rotated at 1 MB with one
  backup).
- **Syslog tag**: `desk-audit`. Available on macOS via
  `/var/run/syslog` (unified log) and Linux via `/dev/log`. On Yahoo
  corp machines this is picked up by the corp log forwarder and
  shipped to SIEM; on non-corp machines it routes to the local syslog
  daemon as expected.

### Useful for OSS users

The audit log is not Yahoo-specific. For external users:

- Local `audit.log` records the same invocation history — useful for
  debugging "what did I run last week?" or auditing your own use.
- Syslog routing follows OS conventions; no Yahoo-specific destination.

Users who don't want audit logging can set `DESK_AUDIT_DISABLED=1`
(implementation: the logger setup checks this env var early and
returns a no-op logger).

## Consequences

- SIEM-side queries find desk activity with `tag=desk-audit`. Coherent
  with cafe (ADR-014), roast (ADR-pending), and the rest of the
  atrium suite as they adopt ADR-004.
- No new dependencies. `logging` and `logging.handlers` are stdlib.
- One follow-up: tests need to mock or skip the syslog handler since
  many CI environments don't have a syslog socket available.

## Alternatives Considered

See atrium ADR-004. The wrapper-script alternative was rejected
because desk's source is owned; an OSS-friendly audit module is a
better fit than an out-of-tree wrapper.

## References

- Atrium ADR-004 (the pattern this ADR adopts)
- ADR-012 (keychain credential storage — the data this ADR audits
  lifecycle events of)
- ADR-019 (the cherry-picked auth logout/clear/stale-token-detection
  work) — this ADR adds events covering those new commands
- PPSE-43152 (PSR for desk and cafe)
