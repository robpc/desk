---
id: 013
title: Safety Confirmations for Destructive Operations
status: implemented
effort: M
value: Prevent accidental destructive actions, especially those affecting others
created: 2026-02-06
updated: 2026-02-07
adr: null
---

# Idea 013: Safety Confirmations for Destructive Operations

## Problem

Several desk commands perform destructive operations without confirmation:
- `desk drive trash <id>` - moves file to trash
- `desk cal delete <id>` - deletes event AND sends cancellation emails to attendees
- `desk sheets clear <id> <range>` - erases cell contents
- `desk drive download` / `desk docs export` - silently overwrite existing local files

## Sketch

Add `--yes` / `-y` flag to destructive commands that skips confirmation. Without it, prompt the user. This is standard CLI practice (e.g., `rm -i`, `gh pr merge --yes`).

```bash
# Interactive (prompts)
desk cal delete EVENT_ID
# Are you sure? This will send cancellation emails to 5 attendees. [y/N]

# Scripted (no prompt)
desk cal delete EVENT_ID --yes
```

For file overwrites, check if dest exists and prompt or fail with `--force`.

## Open Questions

- [ ] Which commands need confirmation? (all destructive, or just ones affecting others?)
- [ ] Default to prompt or default to execute? (Unix tools vary)
- [ ] How to handle in pipes? (detect if stdin is a tty?)

## Tension

Unix philosophy says commands should be scriptable. Prompts break piping. The `--yes` flag resolves this - interactive by default, scriptable with `-y`.

## Value Signal

Source: Quality review of desk v0.2.0. The `cal delete` case is most concerning since it affects other people and can't be undone.

## Effort Guess

M - Need to add flag to multiple commands, implement tty detection, handle consistently.

## Notes

Priority is low for most commands (user's own data), but higher for `cal delete` specifically.

## Implementation (2026-02-07)

Implemented confirmation for `desk cal delete`:

```bash
# Interactive - prompts if event has attendees
desk cal delete EVENT_ID
# Shows: Event name, start time, attendee count
# Warns: "Deleting this event will send cancellation emails to all attendees."
# Prompts: "Are you sure you want to delete this event? [y/N]"

# Scripted - skips prompt
desk cal delete EVENT_ID --yes
```

**Behavior:**
- Only prompts if event has attendees (no prompt for solo events)
- Detects non-interactive mode (pipes) and requires `--yes` or fails with clear error
- Shows event details before prompting so user knows what they're deleting
- Added `get_event` method to CalendarClient to fetch event details
- Added `attendees` and `attendeeCount` to event parsing

**Not implemented (can add later if needed):**
- `desk drive trash` - user's own files, recoverable
- `desk sheets clear` - user's own data
- File overwrite protection - separate concern, less urgent
