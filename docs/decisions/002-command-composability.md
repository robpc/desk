---
id: 002
title: Command Composability via Generic Modify
status: accepted
date: 2025-02-06
supersedes: []
superseded_by: null
tags: [cli, design, api]
---

# ADR-002: Command Composability via Generic Modify

## Context

Gmail CLI needs commands for common email actions: archive, trash, mark as read, etc.

Under the hood, Gmail's API has one fundamental operation: `messages.modify()` which accepts:
- `addLabelIds: []`
- `removeLabelIds: []`

All "actions" are really just label manipulations:
- **archive** = remove `INBOX`
- **trash** = add `TRASH`, remove `INBOX`
- **mark-read** = remove `UNREAD`
- **star** = add `STARRED`

This raises a design question: should we only expose Gmail's native concepts, or also create compound convenience commands like "dismiss" (archive + mark-read)?

## Decision

We will use a **primitives + generic modify** approach:

1. **Named commands** for actions Gmail explicitly supports and names:
   - `gmail archive` - remove from inbox
   - `gmail trash` - move to trash
   - `gmail mark-read` - mark as read
   - `gmail label` - add a label
   - `gmail star` - add star (future)

2. **Generic `modify` command** for arbitrary label composition:
   ```bash
   gmail modify ID --add-label LABEL --remove-label LABEL
   gmail modify ID --remove-label INBOX --remove-label UNREAD
   ```

3. **No invented vocabulary** in the core CLI. Users compose with `modify` or create their own aliases:
   ```bash
   alias gmail-dismiss='gmail modify --remove-label INBOX --remove-label UNREAD'
   ```

## Alternatives Considered

### Alternative 1: Named Commands Only (including compound actions)

**Description**: Add convenience commands like `dismiss` (archive + mark-read) directly to the CLI.

**Pros**:
- Ergonomic for common workflows
- Single command for common patterns

**Cons**:
- Invents vocabulary not in Gmail
- Unclear where to stop (dismiss? triage? snooze-and-label?)
- Users must learn our vocabulary, not Gmail's

**Why rejected**: Inventing vocabulary increases cognitive load and makes the CLI less predictable.

### Alternative 2: Only Generic Modify

**Description**: Single `gmail modify` command for everything, no named commands.

**Pros**:
- Maximum flexibility
- Minimal API surface

**Cons**:
- Verbose for common cases: `gmail modify ID --remove-label INBOX` vs `gmail archive ID`
- Less discoverable
- Doesn't match how users think about email actions

**Why rejected**: Too verbose for common operations. Users think "archive this" not "remove inbox label from this."

## Consequences

### Positive

- CLI vocabulary matches Gmail's vocabulary exactly
- Power users can compose arbitrary workflows with `modify`
- Named commands are immediately understandable
- No maintenance burden for compound commands

### Negative

- Common patterns like "archive and mark read" require two commands or a user alias
  - *Mitigation*: Document common aliases in README
- `modify` command is more complex than other commands
  - *Mitigation*: Good help text with examples

### Neutral

- Future batch support applies to both named commands and `modify`

## Implementation Notes

**Named commands to implement**:
- `mark-read` - `removeLabelIds: ["UNREAD"]`
- `trash` - `addLabelIds: ["TRASH"], removeLabelIds: ["INBOX"]`

**Generic command**:
- `modify --add-label LABEL --remove-label LABEL` (repeatable flags)

**Pattern in gmail.py**:
All commands call `messages().modify()` with different label sets.

## References

- [Gmail API messages.modify](https://developers.google.com/gmail/api/reference/rest/v1/users.messages/modify)
- Discussion in Claude Code session 2025-02-06
