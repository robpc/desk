---
id: 011
title: Non-Engineer Onboarding and README Restructure
status: accepted
date: 2026-02-22
updated: 2026-02-23
supersedes: []
superseded_by: null
tags: [install, onboarding, docs]
---

# ADR-011: Non-Engineer Onboarding and README Restructure

## Context

Desk's install path assumes Python packaging knowledge. The README's Quick Start began with `pip install -e .`, which:

1. Fails on Homebrew-managed Python (PEP 668 — the default on modern macOS)
2. Is a dev-only command (editable install), not appropriate for end users
3. Offers no alternatives (uv, pipx) and no guidance for users without Python

These issues block non-engineer adoption.

## Decision

### README restructure: non-engineers first

Rewrite README with this order:

1. Quick Start (3 lines: install via uv, setup, first command)
2. Installation (uv / pipx / venv / no-Python guidance)
3. Setup (gcloud / team credentials / create your own)
4. Usage (commands reference)
5. Updating
6. Development (at the bottom, not the top)

The primary install path is `uv tool install`, which handles Python isolation, PATH management, and works for users who don't already have Python.

Additionally:
- Add a "First-Run Check" section to CLAUDE.md — agents verify desk is installed before proceeding
- Add troubleshooting for common failure modes (PEP 668, PATH issues)

### Deferred: standalone install script

A POSIX `install.sh` with a uv > pipx > venv cascade was prototyped but deferred. Rationale:

- The parent-suite-installer repo already provides a suite-wide installer that installs uv and all tools (desk, cafe, buzz, relay, tape, dial) via a single curl command
- Adding a desk-specific installer would create two competing install paths that drift
- When desk is open-sourced (outside the parent suite context), a standalone installer pushing uv-only would be appropriate

### Deferred: CalVer versioning

Switching from SemVer (`0.2.0`) to CalVer (`YYYY.DDD`) was prototyped but deferred. Rationale:

- Every other tool in the parent suite uses SemVer via pyproject.toml
- A solo departure from suite convention creates friction for no immediate benefit
- Revisit when desk is standalone and the suite convention doesn't apply

## Alternatives Considered

### Alternative 1: Document pipx only

Minimal change — just swap README to say `pipx install`. Rejected: doesn't help users without pipx or Python.

### Alternative 2: Homebrew formula

`brew install desk` via a tap. Rejected: significant maintenance overhead for a small project.

### Alternative 3: Docker image

`docker run desk mail search ...`. Rejected: contradicts Unix philosophy (pipes, shell composability).

## Consequences

### Positive

- Non-engineers can install with `uv tool install` — one command, no Python knowledge needed
- README answers the first question every user has: "How do I install this?"
- Troubleshooting covers the two most common failure modes
- CLAUDE.md first-run check prevents agents from working without a working install

### Negative

- None significant — this is primarily a documentation improvement

### Neutral

- Versioning stays at SemVer `0.2.0` for now (manual bumps when meaningful)
- Standalone install script can be added later for the open-source context

## References

- [PEP 668 — Externally Managed Environments](https://peps.python.org/pep-0668/)
- parent-suite-installer — suite-wide bootstrap installer
- Idea 045 graduated to this ADR
