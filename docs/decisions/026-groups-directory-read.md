---
id: "026"
title: Groups / Distribution List Read via Admin Directory
status: accepted
date: 2026-06-03
supersedes: []
superseded_by: null
tags: [cli, api, scopes, directory, groups]
---

# ADR-026: Groups / Distribution List Read via Admin Directory

## Context

Agents repeatedly need to expand a distribution list — "who is on
`orionteam@`?" — to reconcile rosters, draft messages, or audit access.
Today desk has no way to do this. The membership lives in Google Groups,
exposed only through the Admin SDK Directory API (`directory_v1`), which
is a different surface from the Gmail/Drive/Calendar APIs desk already
wraps.

Two forces shape the decision:

1. **Scopes are shared.** desk keeps a single flat `SCOPES` list in
   `config.py`; `GCLOUD_SCOPES` derives from it. Adding any scope forces
   every existing user to re-consent on their next `desk auth login`.
2. **Directory reads are frequently admin-gated.** Depending on the
   Workspace domain's configuration, `members.list` / `groups.list` can
   return `403` for non-admin accounts even when the OAuth scope is
   granted. The feature's viability is per-domain, not per-desk.

## Decision

Add a read-only `desk groups` command group backed by a new
`GroupsClient` over `admin/directory_v1`, with three primitives:

- `desk groups members <group>` — expand a group's membership
- `desk groups find [query]` — search/list groups (defaults to the
  caller's customer via `my_customer`)
- `desk groups get <group>` — group metadata

Add the two **read-only** Directory scopes to the default `SCOPES` list:
`admin.directory.group.readonly` and
`admin.directory.group.member.readonly`. Surface `403` with a tailored
suggestion explaining that Directory reads often require admin or
delegated access, so the failure mode is legible rather than looking
like a desk bug.

## Alternatives Considered

### Alternative 1: Gate directory scopes behind an opt-in flag/scope group

**Description**: Keep directory scopes out of the default set; add them
only when the user opts in (e.g. `desk auth login --scopes ...` or a
named scope bundle).

**Pros**:
- No forced re-consent for users who never touch groups
- Smaller default consent screen / least privilege

**Cons**:
- desk has no existing notion of optional scope bundles — it would be
  net-new auth machinery for one command
- Read-only directory scopes are low-risk; the consent text is benign
- Agents would hit confusing "insufficient scope" errors until they
  discover the opt-in

**Why rejected**: Disproportionate complexity for two read-only scopes;
contradicts desk's single-`SCOPES`-list simplicity.

### Alternative 2: Derive membership from Gmail/Contacts instead of Directory

**Description**: Avoid the Directory API by inferring membership from
other surfaces.

**Pros**:
- No new scope

**Cons**:
- No API actually exposes group membership outside Directory
- Would be guesswork, not authoritative

**Why rejected**: Technically can't deliver the feature.

## Consequences

### Positive

- Agents can expand distribution lists directly (`desk groups members
  orionteam@yahooinc.com`), no manual paste from the Admin console.
- Read-only scopes keep the blast radius minimal.

### Negative

- All existing users re-consent on next auth (one-time browser round
  trip). Mitigation: scopes are read-only and clearly labeled.
- On domains where Directory is admin-gated, `members`/`find` will `403`.
  Mitigation: tailored error suggestion names the likely cause.

### Neutral

- `verify_service_access` now reports a `groups` entry; `False` for
  non-admins is expected, not a bug.

## Implementation Notes

Key files:
- `src/desk/services/groups.py` — `GroupsClient` (new)
- `src/desk/commands/groups.py` — `groups` command group (new)
- `src/desk/cli.py` — registration + capabilities
- `src/desk/config.py` — two read-only directory scopes
- `src/desk/auth.py` — `groups` probe in `verify_service_access`
- `src/desk/agent.py` — `GROUP_NOT_FOUND` error code + suggestions

Rollback: remove the command group and the two scopes; users re-consent
back down on next auth.

## References

- [Admin SDK Directory API — Members](https://developers.google.com/admin-sdk/directory/reference/rest/v1/members)
- [Admin SDK Directory API — Groups](https://developers.google.com/admin-sdk/directory/reference/rest/v1/groups)
