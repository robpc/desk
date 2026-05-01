---
id: "018"
title: Tab Identifier Resolution
status: accepted
date: 2026-05-01
supersedes: []
superseded_by: null
tags: [docs, tabs, cli, agent-first, api]
---

# ADR-018: Tab Identifier Resolution

## Context

ADR-010 added Google Docs tab support. The `--tab` flag on every tab-targeted command (`read`, `update`, `inspect`, `insert`, `delete-range`, `style`, `paragraph-style`, `write-markdown`, `insert-table`, `insert-image`) accepts only an opaque tab ID — strings like `t.lqpwtjkvrbgj`. ADR-010 explicitly considered name-based targeting and rejected it on the grounds that tab names aren't unique and resolution would require an extra API call.

Issue #12 surfaces a real callsite that this rejection makes awkward. A "Notes by Gemini" doc has a tab called `Transcript`. Reading it requires:

```bash
desk docs list-tabs <doc-id> --json | jq -r '.[] | select(.title=="Transcript") | .tabId'
desk docs read <doc-id> --tab <that-id>
```

That's not expressible as a single shell command. The motivating consumer — `tape`'s pluggable-source design — wants Google Meet transcript fetching to be pure TOML config with shell-command hooks, no Python orchestration. ID-only `--tab` blocks that.

Two things have shifted since ADR-010 was written that change the calculus:

1. **The rest of the repo already does this.** `gmail.py:_resolve_label` accepts user-supplied label values, treats them as system labels (uppercase constants), then resolves them as user label names against a per-instance cache, then falls through with the value as-is. The user-facing flag is just `label` — no `--label-name` separate flag. `get_attachment_by_filename` is the same pattern: list, find by name, operate on the resolved ID. ADR-010's rejection of name resolution is inconsistent with how Desk addresses analogous concerns elsewhere.

2. **ADR-004 (agent-first) values reducing round-trips.** Forcing every name-based tab access through a `list-tabs` + parse + `read` chain costs an extra agent round-trip per call. A built-in resolver collapses that into one CLI invocation while preserving the ability to use IDs directly when an agent already has them cached.

ADR-010's concern about name uniqueness is real — Google does not enforce unique tab titles within a document. But that concern is addressable through resolution policy, not by refusing to resolve at all.

## Decision

`--tab <value>` on all tab-targeted Docs commands accepts either a tab ID or a tab title. Resolution is **optimistic-then-fallback**: the value is passed through to the underlying operation as a tab ID first; only when the API rejects it as a missing tab does the CLI fall back to title resolution.

### Resolution sequence

1. **`<value>` is None**: pass through; behavior is identical to today's first-tab default.
2. **Optimistic attempt**: the command invokes the underlying service call with `tab_id=<value>`. If the call succeeds, we are done — zero extra round-trips relative to today's ID-only behavior.
3. **On error from step 2**, the wrapper inspects the error. If it isn't a tab-shaped error (auth failure, doc-not-found, permission denied, network, etc.), the wrapper re-raises and the command's existing error path runs.
4. **Tab-shaped error**: the wrapper calls `list_tabs` (cached per-instance) and tries to recover:
   - **Exact tab-ID match in the listing**: `<value>` was a real ID, so the original error was about something else; re-raise the original error rather than masking it.
   - **Single case-insensitive title match** (whitespace-trimmed): retry the original operation with the resolved `tabId`.
   - **Multiple title matches**: emit structured error `TAB_NAME_AMBIGUOUS` with the full match list. User picks one and re-issues with the unambiguous ID.
   - **No match**: emit structured error `TAB_NOT_FOUND` with all available tabs.

Tabs are flattened across nesting for matching purposes — a child tab and its parent are both candidates. Nested-tab disambiguation is left to the user (they pick the right ID from the error output if titles collide across levels).

### Cost profile

| Caller path | Round-trips |
|---|---|
| `--tab <valid-id>` | 1 (the operation itself; same as today) |
| `--tab <valid-title>` | 3 (failed op + `list_tabs` + retried op) |
| `--tab <unknown>` | 2 (failed op + `list_tabs` to produce the structured error) |
| `--tab` omitted | 1 (today's default) |

The optimization target is the ID path — agents and scripts that already have IDs cached pay no resolver overhead. The title path costs one extra round-trip versus eager resolution, which is acceptable because the title path is the new ergonomic case, not the existing hot path.

### Scope

Applies uniformly to **all twelve tab-targeted commands** — the ten content commands from ADR-010 plus the two tab-management commands that take `--tab` as a target:

- Content: `read`, `update`, `inspect`, `insert`, `delete-range`, `style`, `paragraph-style`, `write-markdown`, `insert-table`, `insert-image`
- Management: `delete-tab`, `rename-tab`

Excluding management commands would let an agent that knows a tab by name read or update it but force them to look up the ID before deleting or renaming — gratuitous inconsistency. The resolver's error-on-ambiguity rule provides the same safety guarantee on destructive operations as on reads.

### Implementation approach

A single command-layer wrapper:

```python
def _with_tab_resolution(
    client: DocsClient,
    document_id: str,
    value: str | None,
    as_json: bool,
    fn: Callable[[str | None], T],
) -> tuple[T, str | None]:
    """Run fn(tab_id) optimistically. On a tab-shaped error, list tabs and
    retry with the title-resolved ID. Returns (result, resolved_tab_id).
    """
```

Each command wraps its first tab-using service call in `_with_tab_resolution`. Subsequent calls in the same command (e.g. `find_paragraph_boundary` followed by `insert_at`) reuse the resolved tab_id returned by the wrapper.

Service-layer signatures (`tab_id: str | None`) are unchanged — this preserves ADR-010's service-layer contract verbatim.

`list_tabs` results are cached per-`DocsClient` instance, mirroring `_labels_cache` in `gmail.py`. A single CLI invocation that needs multiple resolutions pays one `list_tabs` call total. The cache is invalidated by `add_tab` / `delete_tab` / `rename_tab` so the same client instance can mutate tabs and resolve afterwards.

### Error payload shape

Follows ADR-004's structured-error pattern. For ambiguous match:

```json
{
  "success": false,
  "error": {
    "code": "TAB_NAME_AMBIGUOUS",
    "message": "Multiple tabs match 'Transcript'.",
    "matches": [
      {"tabId": "t.abc...", "title": "Transcript"},
      {"tabId": "t.def...", "title": "Transcript"}
    ],
    "suggestions": ["Re-run with --tab <tabId> from the matches list."],
    "retryable": false
  }
}
```

For no match, `code` is `TAB_NOT_FOUND` and `matches` is replaced by `available_tabs` listing every tab in the document.

## Alternatives Considered

### Alternative 1: Status quo (ADR-010, ID-only `--tab`)

**Description**: Leave the surface as-is. Callers compose `list-tabs` + name-resolution + `read` themselves.

**Pros**:
- Maximum determinism: an ID always names exactly one tab
- No semantic change to an existing flag
- Honors ADR-010's original rejection

**Cons**:
- Inconsistent with `gmail.py`'s label and attachment handling, which already do name resolution
- Forces a round-trip per name-based access
- Blocks the single-shell-command use case in tape
- Tab IDs are opaque and not stable across re-imports of the same doc — names are usually what callers actually know

**Why rejected**: The round-trip cost is real for agent-driven callers, and the inconsistency with the rest of the codebase is harder to defend than the original "extra API call" objection.

### Alternative 2: Two flags — `--tab` (ID) and `--tab-name` (title)

**Description**: Issue #12's original proposal. `--tab` continues to mean ID; `--tab-name` is added for title-based access; the two are mutually exclusive.

**Pros**:
- Preserves ADR-010's `--tab` semantics exactly
- Explicit at the call site about which path the caller is using

**Cons**:
- Exposes a name/ID distinction that the rest of Desk deliberately hides (`mail label`, attachments)
- Doubles the surface for every tab-targeted command (10 commands × 2 flags)
- Forces agents to learn the distinction — pick the right flag, or eat a "mutually exclusive" error
- The "what if both flags are passed" question only exists because of the two-flag design

**Why rejected**: Inconsistent with the established Gmail pattern. If we wouldn't retroactively split `mail label` into `--label` and `--label-name`, we shouldn't introduce that split here.

### Alternative 3: First-match on ambiguous title

**Description**: When multiple tabs match a title, silently use the first one (by document order).

**Pros**:
- Friendlier for the common case where a doc has only one `Transcript` tab
- Matches the original issue's proposal

**Cons**:
- Non-deterministic for callers: a doc gaining a second tab with the same title silently changes which tab a script targets
- Especially dangerous for write commands (`update`, `delete-range`, `insert-table`) — the wrong tab gets mutated and there's no signal
- Agent-first design (ADR-004) prefers explicit, structured errors over silent guesses
- The error path already gives the caller everything they need to recover (list of matches)

**Why rejected**: The downside on write commands — silently mutating the wrong tab — is severe and recoveries are expensive. Erroring is uniformly safer and only marginally less convenient when the error payload is good.

### Alternative 4: Eager pre-resolution (list_tabs before every `--tab` call)

**Description**: Always call `list_tabs` first; check the value against tab IDs and titles in the cache; pass the resolved ID into the operation. This was an earlier version of this ADR's decision.

**Pros**:
- Simple control flow — single helper, no error-introspection
- Errors come earlier (before any mutation API call) so structured-error payloads are produced before any side effects could occur
- Cost profile is symmetric: every `--tab` call pays one `list_tabs`

**Cons**:
- **Adds a `list_tabs` round-trip on every `--tab` call, including the common `--tab <id>` case.** Existing scripts and agents that already have IDs cached take a latency penalty for a feature they aren't using
- Inconsistent with the cost profile of analogous Gmail patterns: `_get_label_id` is called only when the value is a name, not on every label-using operation, because the system-label fast path short-circuits

**Why rejected**: Charges every caller for the new feature. Optimistic-then-fallback charges only the title-using callers — the new ergonomic case — while preserving today's zero-overhead ID path.

### Alternative 5: Title-only addressing (drop ID support)

**Description**: Make `--tab` accept titles only; require callers to use a hypothetical `desk docs list-tabs --title-only` to discover them.

**Why rejected**: Tab IDs are stable identifiers an agent may already have cached or received from a previous call. Removing them would force a list-tabs round-trip in cases that previously didn't need one. The point is to add ergonomics, not subtract.

## Consequences

### Positive

- **Consistent with the rest of Desk.** Same shape as `mail label`, attachment-by-filename, and the implicit Gmail pattern: human-meaningful identifier in, opaque ID resolved internally.
- **Removes a forced round-trip for agent callers.** The tape callsite — and any analogous shell-driven config — becomes a single `desk docs read <id> --tab Transcript`.
- **Zero-overhead for ID callers.** Optimistic resolution means `--tab <id>` does not pay for the new feature. Existing scripts behave identically.
- **Backwards compatible.** Existing scripts that pass tab IDs continue to work unchanged; the optimistic attempt resolves them on the first call.
- **Uniform across all tab-targeted commands**, including `delete-tab` and `rename-tab` — agents that know a tab by name don't need to swap modes between operations.
- **Service contract unchanged.** Resolution lives in the command layer; `services/docs.py` keeps the `tab_id: str | None` signatures from ADR-010.
- **Per-instance caching** keeps a CLI invocation that triggers multiple resolutions to one `list_tabs` round-trip total.

### Negative

- **`--tab` semantics shift from "ID only" to "ID or title."** A subtle change to a previously-frozen flag. Documented in `--help` and called out as the explicit reversal of ADR-010's Alternative 2.
  - *Mitigation*: optimistic resolution means existing ID-based callers see no behavior change on the happy path.
- **Title path is two extra round-trips** (failed initial call + `list_tabs` + retry) instead of one (`list_tabs` + call) under eager resolution.
  - *Mitigation*: title resolution is the new ergonomic case, not the existing hot path. The trade is worth it because we don't penalize the ID path that all current callers use.
- **Failed write attempts on bad tab values** consume a `batchUpdate` round-trip before falling back. Google rejects the entire `batchUpdate` on an invalid `tabId`, so no partial mutation occurs — the cost is latency, not data integrity.
- **Error introspection is heuristic.** The wrapper inspects exception messages to decide whether to attempt fallback. If Google's error format changes in a way that no longer mentions "tab," some recoveries will be missed and the original error will surface instead.
  - *Mitigation*: the heuristic looks for "tab" + ("not found" | "invalid") in the lowercased message, covering both the read path's `RuntimeError("Tab not found: ...")` and the batchUpdate path's wrapped `HttpError`. Easy to widen if Google changes the format.

### Neutral

- Tab IDs remain canonical. Titles are sugar. Tooling that wants determinism keeps using IDs; tooling that wants ergonomics uses titles. Both are first-class.
- No new OAuth scopes; no new API surface (`list_tabs` already exists from ADR-010).

## Implementation Notes

- **`src/desk/services/docs.py`**:
  - Add a per-`document_id` tabs cache to `DocsClient.__init__`.
  - Add `get_tabs_cached()` returning the cached `list_tabs()` result, populating on first call.
  - Invalidate the cache entry inside `add_tab`, `delete_tab`, `rename_tab` so the same client instance can mutate and re-resolve correctly.
  - No changes to existing tab-targeted method signatures.
- **`src/desk/commands/docs.py`**:
  - Add `_with_tab_resolution(client, document_id, value, as_json, fn)` wrapper that calls `fn(value)`, catches tab-shaped errors, lists tabs, retries with the resolved title, and returns `(result, resolved_tab_id)`.
  - Add `_looks_like_tab_error(e)` heuristic: lowercased message contains "tab" plus ("not found" or "invalid").
  - Add private emitters for `TAB_NOT_FOUND` and `TAB_NAME_AMBIGUOUS` structured errors.
  - In each of the twelve tab-targeted commands, replace the direct `client.X(..., tab_id=tab_id)` invocation with a `_with_tab_resolution(...)` call. Commands with multiple tab-using calls (e.g. `insert`'s `find_paragraph_boundary` followed by `insert_at`) capture the resolved tab_id and reuse it.
  - Update `--tab` help text to "Tab ID or title …" on all twelve commands.
- **`src/desk/agent.py`**:
  - Add `TAB_NAME_AMBIGUOUS` and `TAB_NOT_FOUND` to `ErrorCode` with suggestion strings pointing at `desk docs list-tabs`.
- **Tests**:
  - Unit tests for `_with_tab_resolution`: ID happy path doesn't call `list_tabs`; title path calls it once; non-tab errors re-raise without listing; ambiguous and unknown values exit with structured errors.
  - Service-layer tests that the cache is per-document and is invalidated by mutating commands.
  - One end-to-end CLI test on `docs read --tab "Some Title"` to exercise the full path.

## References

- Issue #12 (robpc/desk): "Support --tab-name on `docs read` (and other tab-targeted commands)"
- ADR-010: Google Docs Tab Support — this ADR amends Alternative 2's rejection
- ADR-002: No Invented Vocabulary — tab titles are Google's vocabulary, not ours
- ADR-004: Agent-First CLI Design — round-trip cost reduction; structured errors with available-tabs context
- `src/desk/services/gmail.py`: `_resolve_label`, `_get_label_id`, `get_attachment_by_filename` — established name→ID resolution pattern
- [Google Docs API: tabs](https://developers.google.com/docs/api/concepts/tabs)
