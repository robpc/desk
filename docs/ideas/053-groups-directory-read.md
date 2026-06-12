---
id: "053"
title: Groups / Distribution List Read via Admin Directory
status: parked
effort: M
value: Expand a distribution list ("who's on orionteam@?") without hand-copying from the Admin console — but only viable for Workspace admins
created: 2026-06-03
updated: 2026-06-03
adr: null
---

# Idea 053: Groups / Distribution List Read via Admin Directory

## Status: parked

Built and verified end-to-end in **PR #45** (`feat/groups-command`,
closed unmerged), with a draft ADR-026 and 11 unit tests. The
implementation is sound; it's parked because live verification proved
the feature is **admin-gated and unusable for the typical desk user**,
and shipping it would force every user through a re-consent to
admin-directory scopes they can't benefit from. Revisit if/when there's
a concrete admin or domain-wide-delegated use case, ideally behind
opt-in scopes (see "Path forward").

## Problem

Agents repeatedly need to expand a distribution list — "who is on
`orionteam@`?" — to reconcile rosters, draft messages, or audit access.
Group membership lives only in the Admin SDK Directory API
(`directory_v1`), a different surface from the Gmail/Drive/Calendar APIs
desk wraps. Today desk can't read it, so callers drop to a raw
`googleapiclient` script.

## What was built (PR #45)

A read-only `desk groups` command group over a new `GroupsClient`:

- `desk groups members <group>` — expand membership (`--role` filter, pagination)
- `desk groups find [query]` — search/list groups (`my_customer` default, `--domain` override)
- `desk groups get <group>` — group metadata

Plus: two read-only directory scopes added to the default `SCOPES`, a
`verify_service_access` probe, a `GROUP_NOT_FOUND` error code, and the
capabilities entry. Followed the "Adding a New Service" checklist
faithfully. CI green, ruff clean.

## Why it's parked — the verification result

Verified live on `2026-06-03` against `yahooinc.com` with a regular
(non-admin) employee account. The full chain:

| Precondition | Result |
|--------------|--------|
| Org policy allows the `admin.directory.group*.readonly` scopes | ✅ consent succeeded (scopes were *not* blocked) |
| Admin SDK API enabled in the user's GCP project | ✅ enabled via console (was off by default) |
| Non-admin account can read the directory | ❌ **403 "Not Authorized to access this resource/api"** |

The 403 was **total**: `find` (both `my_customer` and `--domain`),
`get`, and `members` all failed — including `members orionteam@`, a
group the caller belongs to. The Directory API requires Workspace
**admin or domain-wide delegation**; per-group reads are not a
lower-privilege escape hatch on this domain.

So the cost/benefit is lopsided: merging forces **every** desk user
through a re-consent to scarier admin-directory scopes (one-time browser
round-trip, a more alarming consent screen) in exchange for a feature
**only Workspace admins can use**. desk's audience is mostly regular
users, not admins.

## Path forward (if revisited)

The verification substantially strengthens the **opt-in scopes**
alternative that draft ADR-026 rejected as "disproportionate." Concrete
options, best-first:

1. **Opt-in scope bundle.** Keep the directory scopes out of the default
   `SCOPES`; add them only when a user opts in (e.g.
   `desk auth login --scopes directory` or a named bundle). Non-admins
   never see the scope; admins who need it pull it in deliberately. This
   needs net-new auth machinery desk doesn't have yet — but it's the
   honest fit given who can use the feature. (See ADR-001 for the
   credential strategy this touches.)
2. **Domain-wide delegation path.** Document a service-account / DWD
   setup for admins who want this org-wide. Heavier; only worth it with
   real demand.
3. **Leave parked** until someone with admin/delegated access has a
   concrete recurring need.

## Findings to fold in when reviving PR #45

- **`SERVICE_DISABLED` mis-maps to `PERMISSION_DENIED`.** When the Admin
  SDK API is disabled, `_handle_api_error` maps the 403 to
  `PERMISSION_DENIED` and the `suggestions` lead with "requires admin /
  request access from owner." The actual fix ("enable the Admin SDK
  API") survives only in the raw `message`. An agent reading
  `suggestions` is misdirected. Add a distinct `API_NOT_ENABLED` /
  `SERVICE_DISABLED` branch with an "enable the API" suggestion.
- **Document the total admin-gating.** The draft ADR's "Negative" note
  ("members/find will 403 on admin-gated domains") undersells it —
  single-group `get`/`members` fail too, even for a member of the group.

## References

- PR #45 (`feat/groups-command`) — implementation + draft ADR-026 (closed unmerged)
- [Admin SDK Directory API — Members](https://developers.google.com/admin-sdk/directory/reference/rest/v1/members)
- [Admin SDK Directory API — Groups](https://developers.google.com/admin-sdk/directory/reference/rest/v1/groups)
- ADR-001 (credential / scope strategy — opt-in scopes would touch this)
- ADR-002 (no invented vocabulary — "groups"/"members" satisfy it)
