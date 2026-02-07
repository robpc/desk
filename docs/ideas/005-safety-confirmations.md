# Idea: Safety Confirmations for Destructive Operations

**Status**: idea
**Source**: Quality review of desk v0.2.0

## Context

Several desk commands perform destructive operations without confirmation:
- `desk drive trash <id>` — moves file to trash
- `desk cal delete <id>` — deletes event AND sends cancellation emails to attendees
- `desk sheets clear <id> <range>` — erases cell contents
- `desk drive download` / `desk docs export` — silently overwrite existing local files

## Idea

Add `--yes` / `-y` flag to destructive commands that skips confirmation. Without it, prompt the user. This is standard CLI practice (e.g., `rm -i`, `gh pr merge --yes`).

For file overwrites, check if dest exists and prompt or fail with `--force`.

## Tension

Unix philosophy says commands should be scriptable. Prompts break piping. The `--yes` flag resolves this — interactive by default, scriptable with `-y`.

## Priority

Low — these are all user-initiated actions on their own data. But `cal delete` sending cancellation emails is the most dangerous since it affects other people and can't be undone.
