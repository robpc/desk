---
id: 034
title: Scope-Aware Commands
status: accepted (§2 amended by ADR-036 — the `@requires_scope` decorator was removed as unused)
date: 2026-07-31
supersedes: []
superseded_by: null
tags: [auth, cli, agent-first, api]
---

# ADR-034: Scope-Aware Commands

Amends ADR-030 §3, whose "proactive" scope-drift detection never functioned (issue #82).

## Context

Issues #80 and #81 ask for Calendar and Meet features. The Meet half needs the Google Meet
REST API and an OAuth scope Desk doesn't request today (`meetings.space.settings`). #81
frames the real cost accurately: "this requires a scope addition and a re-consent — that is
the real cost of the feature, not the API calls."

Three facts shape the decision:

1. **Adding a scope does not break existing tokens.** A token granted N scopes keeps
   refreshing and keeps working for those N. Only calls needing the new scope fail, with a
   403. There is no flag day and no forced migration.
2. **Desk users self-serve their own consent.** Each user brings their own Google Cloud
   project (ADR-001), so the fix for a missing scope is one command they run themselves —
   unlike a Slack-style app where an admin must approve scopes and the user is hard-blocked.
3. **Desk currently cannot tell whether a scope was granted.** Issue #82: `SCOPES` is
   passed into `Credentials.from_authorized_user_info()`, which makes `creds.scopes` the
   *requested* set, and `to_json()` never serializes the *granted* set. So
   `_missing_scopes()` returned `[]` for every user and the ADR-030 §3 proactive path was
   dead on arrival.

So the blocker isn't consent mechanics, it's **legibility**: a user or agent has no way to
learn that a command can't work until it fails. Cafe hit the same problem from the other
direction (workspace admins removing `search:read`) and solved it in its ADR-006, amended
by its ADR-024. We adopt that pattern.

## Decision

### 1. Persist the granted scope set (prerequisite, issue #82)

`_save_credentials()` writes `creds.granted_scopes` under a dedicated
`granted_scopes` key, because `to_json()` drops it. A save from a credentials object that
doesn't know the granted set carries forward the previously stored value rather than
wiping it. `_get_oauth_credentials()` re-attaches the stored set on load, since
`from_authorized_user_info()` never restores it. A new `auth.granted_scopes()` accessor is
the single source of truth: credentials object first, then storage.

**`None` means "unknown", not "granted nothing".** Tokens issued before this fix carry no
record; google-auth repopulates `granted_scopes` from the next refresh response
automatically, so users recover without re-authenticating.

### 2. `enforce_scopes()`, resolved at invocation only

`agent.enforce_scopes(scopes, as_json)` checks the granted set and, if a scope is missing,
emits the existing `ErrorCode.INSUFFICIENT_SCOPES` structured error — naming the missing
scope, the affected commands, and `desk auth login` — before any API call.

**Gate service-wide scopes at the service's `_get_client()` helper, not per command.**
Desk's scopes are service-shaped: `presentations` covers all 25 `slides` commands, and every
one of them already funnels through `_get_client(as_json)`. One call there gates the whole
service, versus decorating 25 commands and keeping them in sync.

*(Amended by ADR-036 §5: this section originally also shipped a `@requires_scope` decorator
for scopes covering only part of a service, anticipating Meet. ADR-036 made Meet its own
service group, so the scope is service-wide, the decorator had no user, and it was removed.
`enforce_scopes()` is the sole mechanism.)*

**Never at decoration/import time.** `desk.cli` imports every command module at startup and
resolving scopes touches the keyring, so a decoration-time read would make bare
`desk --help` crash on hosts with no keyring backend. This is not hypothetical: it is
exactly the regression Cafe's ADR-024 was written to undo.

**The gate fails open when the granted set is unknown.** A pre-#82 token, or the gcloud ADC
path, must never block a command that would have worked.

### 3. `SCOPE_COMMANDS` map in `config.py`

Scope → targets, where a target is either a bare service name (`"slides"`, meaning every
command in it) or a specific `"service command"` pair for a scope covering part of a service.
Three resolvers read it: `scopes_for_service()`, `scopes_for_command()`, and
`commands_for_scopes()` (which renders the gate's "affected commands" list). It may list
scopes for features that don't exist yet; that's how a planned capability stays documented.

Only scopes worth gating need an entry. Most of Desk's scopes are requested together at
first login, so a user has all of them or isn't authenticated at all — gating those adds
noise without catching anything. The entries that matter are scopes added *after* a release.

### 3b. Keyring reads treat "no backend" as "nothing stored"

`keyring_store.get_token()` and `get_client_credentials()` catch
`keyring.errors.NoKeyringError` and report absence. On a host with no backend nothing *can*
be stored, so `None` is truthful.

This is load-bearing, not incidental: `--capabilities` is pure introspection but now reads
the granted set on every invocation, which turned bare `desk --capabilities` into a
`NoKeyringError` traceback on headless Linux, containers, and CI runners. Caught by running
the CLI under `PYTHON_KEYRING_BACKEND=keyring.backends.fail.Keyring`.

Writes still fail loudly — storing a secret with nowhere to put it must never be silent.
Other keyring errors (locked keychain, denied access) still propagate, since only
`NoKeyringError` is unambiguous.

### 4. `--capabilities` reports `scope` and a tri-state `enabled`

Each command entry gains `scope` (list, possibly empty) and `enabled`:
`true` / `false` / `null` when the granted set is unknown. This is the agent-facing half
(ADR-004) — an agent can tell it can't do something, and why, without a failed call.

Both fields are **derived from `SCOPE_COMMANDS` at runtime**, not written into the ~150
hand-maintained command entries in `cli.py`. The map stays the single source of truth, so
capabilities can't drift from the gate.

### 5. Reuse `INSUFFICIENT_SCOPES`; do not add a new error code

Desk already has `INSUFFICIENT_SCOPES` with the right suggestions (ADR-030). Cafe added a
distinct `MISSING_SCOPE` for pre-flight, but Desk's existing code already means "you
haven't granted this, re-auth" — a second near-identical code would just make agents
pattern-match two strings for one condition.

### 6. New scopes are requested by default, not opted into

When Desk adds a scope it goes into `config.SCOPES`, so `desk auth login` requests it.
Existing tokens are unaffected until the user re-auths; the gate and `--capabilities` keep
them honest in the meantime. No per-feature opt-in flag.

## Alternatives Considered

### Alternative 1: Hide commands whose scopes aren't granted

**Description**: Omit unscoped commands from the Click tree entirely.

**Pros**:
- `--help` shows only what works
- No error path to design

**Cons**:
- Commands vanish with no explanation of why or how to get them back
- `--help` output differs per user, so documentation and examples become unreliable
- An agent can't discover a capability exists but needs consent

**Why rejected**: Cafe explicitly rejected this (its ADR-006 Option B) and we'd inherit the
same problems. Visible-but-disabled is strictly more informative.

### Alternative 2: Annotate `--help` with `[DISABLED — missing scope: X]`

**Description**: Append disabled status to each command's help text.

**Pros**:
- Discovery right where the user is already looking

**Cons**:
- Click bakes help text when the `Command` object is constructed at import, so this forces
  scope resolution at import time — the keyring-less crash above
- Avoiding that needs a custom `Command` subclass threaded through every group

**Why rejected**: Cafe shipped this and then removed it in ADR-024 for exactly these
reasons. `--capabilities`, `auth status`, and the invocation error already cover discovery.

### Alternative 3: Two-tier scope sets (required + optional, `desk auth login --with meet`)

**Description**: Keep new scopes out of the default consent request; users opt in per
feature.

**Pros**:
- Least privilege — users grant only what they use
- Consent screen stays short

**Cons**:
- Two scope lists to keep in sync, plus flag plumbing and per-feature naming
- Most users would want the feature anyway, so the common path gains a step
- Partial-grant states multiply

**Why rejected**: not worth the machinery for a non-sensitive scope. Worth revisiting if a
sensitive or restricted scope ever lands, since those carry verification cost — noted as an
open question in idea 079.

### Alternative 4: Rely on the reactive 403 path only (ADR-030 §3 as built)

**Pros**:
- Already implemented, zero new code

**Cons**:
- Costs a round trip to learn a call was never going to work
- Agents must fail to discover a limit, which is what ADR-004 argues against
- Gives no inventory of what's disabled

**Why rejected**: it's the floor, not the ceiling. We keep it as the backstop for scopes no
gate covers.

## Consequences

### Positive

- Scope-dependent features can ship without coordinating a re-auth across all users
- `desk auth status` reports real scope drift for the first time, including the
  pre-existing `presentations` drift from ADR-026
- Agents can read `--capabilities` and explain a missing capability instead of hitting a 403
- Fast fail — no wasted API call when a scope is known-missing

### Negative

- `SCOPE_COMMANDS` needs maintenance as commands are added; a stale map means a command is
  gated on the wrong scope. Mitigation: the map is data in one file, service-level entries
  cover new commands in an existing service automatically, and the gate failing open on
  unknown limits the damage.
- Services must opt in by calling `enforce_scopes()` in their `_get_client()` — an
  un-gated service still fails reactively, so coverage is incremental rather than
  guaranteed. Only `slides` is gated today, because it's the only service with a
  post-release scope.
- A service-level gate fires in `_get_client()`, so it can't distinguish commands within a
  service that would work under a narrower grant. Fine for `presentations` (all-or-nothing);
  partial-coverage scopes must use the decorator instead.

### Neutral

- Pre-#82 tokens report `enabled: null` until their next refresh. Correct, if briefly
  uninformative.

## Implementation Notes

Key files:

- `src/desk/auth.py` — `granted_scopes()`, `_stored_granted_scopes()`,
  `_restore_granted_scopes()`, `_save_credentials()`, `_missing_scopes()`
- `src/desk/config.py` — `SCOPE_COMMANDS`, `scopes_for_service()`,
  `scopes_for_command()`, `commands_for_scopes()`
- `src/desk/agent.py` — `enforce_scopes()`
- `src/desk/cli.py` — `_get_capabilities()` / `_annotate_scopes()`
- `src/desk/commands/slides.py` — `_get_client()` gates on `presentations`
- `src/desk/keyring_store.py` — read helpers tolerate a missing backend
- `tests/test_scopes.py` — persistence, gate behavior, keyring-less host

Rollback: the gate is additive and fails open; removing the `enforce_scopes()` calls restores
prior behavior. The `granted_scopes` storage key is ignored by older versions.

The test suite runs under `PYTHON_KEYRING_BACKEND=keyring.backends.fail.Keyring` as well as
normally; keep it that way, or the import-time/read-time keyring regression returns.

## References

- Issue #82 — granted scopes never persisted
- Issues #80, #81 — the Calendar/Meet gaps motivating this
- ADR-030 §3 — the scope re-auth UX this amends
- ADR-004 — agent-first CLI
- Cafe ADR-006 (scope-aware commands) and ADR-024 (lazy scope resolution)
- [Meet API spaces.patch scopes](https://developers.google.com/workspace/meet/api/reference/rest/v2/spaces/patch)
