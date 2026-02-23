---
id: 045
title: Non-Engineer Accessibility for Install and Onboarding
status: adr-created
effort: M
value: Non-engineers can install desk without Python packaging knowledge
created: 2026-02-22
updated: 2026-02-23
adr: docs/decisions/011-non-engineer-install-and-versioning.md
---

# Idea 045: Non-Engineer Accessibility for Install and Onboarding

## Problem

The current install path assumes familiarity with Python packaging:

1. **`pip install -e .`** fails on Homebrew-managed Python (PEP 668) — the most common macOS setup
2. No guidance on `uv` or `pipx` — the tools that actually work out of the box
3. README leads with a dev-only command, not a user-facing install
4. No agent install prompt — users in Claude Code can't self-serve
5. CLAUDE.md doesn't check if desk is installed before doing work

Non-engineers hit walls at every step. Even developers find it tedious.

## What shipped

1. **README rewrite** — Installation section before Development, uv as primary path, troubleshooting for PEP 668 and PATH issues
2. **CLAUDE.md first-run check** — agents verify desk is installed before proceeding

## Deferred

- **install.sh** — standalone installer deferred because parent-suite-installer already provides suite-wide install. Revisit for open-source context.
- **CalVer versioning** — deferred to stay aligned with suite-wide SemVer convention. Revisit when desk is standalone.
- **Agent install prompt doc** — deferred; CLAUDE.md first-run check covers the agent use case.

## Notes

- Companion to idea 044 (bundled credentials) — this removes install friction, 044 removes auth friction
- Does not change any desk functionality
