---
id: "026"
title: Quiet Flag
status: idea
effort: S
value: Cleaner script output by suppressing success messages
created: 2026-02-07
updated: 2026-02-07
adr: null
---

# Idea 026: Quiet Flag

## Problem

Commands that perform actions print success messages (e.g., "Archived 3 messages", "Label added"). In scripts, these messages are noise - you only care about errors. There's no consistent way to suppress non-error output.

## Sketch

Add `--quiet` / `-q` flag to action commands:

```bash
desk mail archive <id> --quiet       # No output on success, only errors
desk mail label <id> WORK --quiet    # Silent success
desk drive trash <id> --quiet        # No "Moved to trash" message
desk cal delete <id> --yes --quiet   # No confirmation message shown
```

Behavior:
- `--quiet` suppresses success messages and informational output
- Errors still print to stderr
- Exit codes unchanged (0 for success, non-zero for errors)
- `--json` output still works (for programmatic success confirmation)

## Open Questions

- [ ] Should --quiet suppress all stdout or just success messages?
- [ ] How does --quiet interact with --dry-run? (probably still show what would happen)
- [ ] Should there be a global quiet mode (env var or config)?
- [ ] Does --quiet make sense for read commands?

## Value Signal

Quiet mode enables:
- Cleaner script output (only errors surface)
- Easier integration with other tools
- Reduced log noise in automated pipelines

Standard Unix convention for CLI tools.

## Effort Guess

**S** - Add a flag to the Click command decorator and conditionally skip print statements. Straightforward pattern that can be applied incrementally.

## Notes

- Common Unix convention: -q/--quiet for silent operation
- Pair with -v/--verbose for the opposite (more detail)
- Could be implemented via a shared decorator or context flag
- Consider: global DESK_QUIET=1 environment variable
- Action commands only (search/read commands always need to output something)
