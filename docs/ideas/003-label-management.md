---
id: 003
title: Label Management
status: partial
effort: S
value: Complete label workflow without leaving CLI
created: 2025-02-06
updated: 2025-02-06
adr: null
---

# Idea 003: Label Management

## Problem

When trying to add a label that doesn't exist, the CLI errors with "Label not found". There's no way to create a new label from the CLI - you have to go to Gmail's web UI.

Real use case: Organizing project emails (e.g., Gemini meeting notes, shared docs) into a new "Orion" label, but the label doesn't exist yet and can't be created from the CLI.

## Sketch

### Core: `create-label` command
```bash
gmail create-label "Orion"
gmail create-label "Projects/Orion"   # nested label
gmail create-label "Work" --color red  # optional: label color
```

### Bonus: Auto-create on `label` command
```bash
gmail label --create "NewLabel" ID    # create if missing
# Or by default with opt-out:
gmail label "NewLabel" ID             # auto-create
gmail label --no-create "MustExist" ID  # fail if missing
```

Similar to `git checkout -b` creating a branch if it doesn't exist.

### Possible additions
```bash
gmail delete-label "OldLabel"         # remove a label
gmail rename-label "Old" "New"        # rename a label
gmail labels --json                   # already exists - list labels
```

## Technical Notes

Gmail API supports label creation:
```
POST /gmail/v1/users/me/labels
{
  "name": "Projects/Orion",
  "labelListVisibility": "labelShow",
  "messageListVisibility": "show"
}
```

Nested labels use "/" in the name (e.g., "Projects/Orion" appears nested under "Projects" in Gmail UI).

Label colors are optional and use a specific set of color IDs.

## Open Questions

- [ ] Should `gmail label` auto-create by default? (git-like) Or require `--create` flag? (safer)
- [ ] Should we support label colors? (adds complexity, low value?)
- [ ] Should we support `delete-label`? (destructive, needs confirmation)
- [ ] Should we support `rename-label`? (Gmail API: update label name)
- [ ] Idempotency: Should `create-label` fail or no-op if label exists?

## Value Signal

Real request from an agent using the CLI in production. They wanted to organize Orion project emails but hit a wall because label creation required the web UI.

## Effort Guess

S for basic `create-label` command - straightforward API call.
M if we add auto-create, delete, rename, colors.

## Notes

This completes the "label lifecycle" - users can now manage labels entirely from CLI:
1. `gmail labels` - list labels (exists)
2. `gmail create-label` - create new label (this idea)
3. `gmail label` - apply label to messages (exists)
4. `gmail remove-label` - remove label from messages (exists)
5. `gmail delete-label` - delete label entirely (optional)

## Implementation (2025-02-06)

Implemented `create-label` command:

```bash
gmail create-label "Orion"
gmail create-label "Projects/Orion"   # nested labels
gmail create-label "Work" --json      # outputs label details
```

**Behavior**:
- Errors if label already exists (non-destructive, clear feedback)
- Supports nested labels via "/" in name
- No auto-create on `label` command (per ADR-002: no invented vocabulary)

**Not implemented** (can revisit if needed):
- `--create` flag on `gmail label`
- `delete-label` command
- `rename-label` command
- Label colors
