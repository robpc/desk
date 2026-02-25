---
id: 13
title: Remove Self-Update Command
status: accepted
date: 2026-02-25
supersedes: [5]
superseded_by: null
tags: [cli, developer-experience]
---

# ADR-013: Remove Self-Update Command

## Context

ADR-005 introduced `desk update` to make updating self-documenting. It supported two install methods: editable git clones (`pip install -e .`) and pip-from-git (`pip install git+ssh://...`).

The primary install path is now `uv tool install` (recommended in README and CLAUDE.md), which `detect_install()` cannot handle — `direct_url.json` doesn't contain the metadata patterns the detection logic looks for. The command shows up in `--help` but fails for most users with "Cannot determine how desk was installed."

Rather than chasing every install method (uv, pipx, parent-suite installer, etc.), we remove the command entirely and let users update through whatever mechanism they installed with:

- `uv tool upgrade desk` for uv installs
- `pipx upgrade desk` for pipx installs
- `git pull && pip install -e .` for dev clones

## Decision

We will remove the `desk update` command and all supporting code:

1. Delete `src/desk/update.py`
2. Remove the `update` command from `src/desk/cli.py`
3. Remove the `utility_commands` block from `_get_capabilities()`
4. Remove `UPDATE_*` error codes from `src/desk/agent.py`
5. Remove the "Updating" section from `README.md`
6. Update `CLAUDE.md` architecture diagram and key files list

## Alternatives Considered

### Alternative 1: Extend detect_install() for uv/pipx

**Description**: Add detection for `uv tool install` and `pipx install` patterns in `direct_url.json`.

**Pros**:
- Keeps update discoverable via `desk --help`
- Agents can call `desk update` without knowing the install method

**Cons**:
- Each tool manager has its own update mechanism (`uv tool upgrade`, `pipx upgrade`)
- Shelling out to `uv` or `pipx` from within a managed environment is fragile
- New install methods will keep appearing, requiring ongoing maintenance

**Why rejected**: Ongoing maintenance cost with diminishing returns — the install tool already knows how to update itself.

### Alternative 2: desk update as a hint/redirect

**Description**: Keep `desk update` but have it print "run `uv tool upgrade desk`" (or equivalent) based on detected install method.

**Pros**:
- Still discoverable
- No fragile subprocess calls

**Cons**:
- Still requires detect_install() to work for each method
- Adds complexity for a message that could go in docs

**Why rejected**: Documentation is a better place for install-method-specific instructions.

## Consequences

### Positive

- Removes code that fails for the majority of users
- Eliminates ongoing maintenance as install methods evolve
- Simplifies CLI surface area

### Negative

- Users who relied on `desk update` need to learn their tool manager's upgrade command (mitigated: this is standard practice for CLI tools)

### Neutral

- Agents lose a single-command update path but can compose the right command from install context

## Implementation Notes

- Supersedes ADR-005
- No migration needed — the command simply stops existing
- No tests imported `update.py`, so no test changes required
