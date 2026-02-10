---
id: 5
title: Self-Update Command
status: accepted
date: 2026-02-09
supersedes: []
superseded_by: null
tags: [cli, developer-experience]
---

# ADR-005: Self-Update Command

## Context

Users currently update desk by manually running `git pull && pip install -e .` inside the repo clone. This requires knowing the internals — where the repo is cloned, that it's editable-installed, and that pip needs to be re-run after pulling.

A `desk update` command makes updating self-documenting. An agent (or user) can discover it via `desk --help` and run it without knowing how desk is installed.

Forces at play:
- Desk is installed via `pip install -e .` (editable git clone) or `pip install git+ssh://...` (pip from git URL)
- There is no PyPI distribution, so standard `pip install --upgrade desk` won't work
- Agents need a reliable, discoverable way to update the tool they depend on
- The update mechanism must detect the install method rather than assuming one

## Decision

We will add a top-level `desk update` command that:

1. **Detects the install method** using PEP 610 `direct_url.json` from `importlib.metadata` — the standards-based way to determine how a package was installed.
2. **For editable git clones**: runs `git pull --ff-only origin main` then `pip install -e .`
3. **For pip-from-git installs**: runs `pip install --upgrade <git-url>`
4. **For unknown installs**: prints a clear error with manual instructions

The command supports `--check` (only check, don't apply) and `--json` (structured output for agents).

We use `git pull --ff-only` to avoid merge commits. If the user has local changes that cause a conflict, it fails cleanly with a suggestion to resolve manually rather than silently merging.

## Alternatives Considered

### Alternative 1: GitHub API for version checking

**Description**: Use the GitHub releases API to check for new versions.

**Pros**:
- Works without git installed
- Could support binary distributions

**Cons**:
- Requires `requests` or similar HTTP library (new dependency)
- Desk isn't distributed via GitHub releases today
- Would need a GitHub token for private repos

**Why rejected**: Adds a dependency for a problem git already solves. If we distribute via GitHub releases later, we can revisit.

### Alternative 2: Separate update script

**Description**: Ship a standalone `desk-update.sh` script.

**Pros**:
- Simple, no Python code needed

**Cons**:
- Not discoverable via `desk --help`
- Can't output JSON for agents
- Another file to maintain

**Why rejected**: Breaks discoverability principle. Agents can't find it.

## Consequences

### Positive

- Agents can discover and run `desk update` without special knowledge
- `desk update --check --json` enables automated update workflows
- Install method detection means it works regardless of how desk was installed

### Negative

- Subprocess calls to git/pip are inherently fragile (mitigated by timeouts and clear error messages)
- `--ff-only` will refuse to update if the user has diverged from main (this is intentional — we don't want to silently merge)

### Neutral

- No new dependencies added — uses git and pip which are already required

## Implementation Notes

- Core logic in `src/desk/update.py`, command registration in `src/desk/cli.py`
- Error codes added to `src/desk/agent.py` for structured error handling
- All subprocess calls use explicit timeouts (30s for git, 120s for pip)
- PEP 610 detection via `importlib.metadata.distribution('desk').read_text('direct_url.json')`
