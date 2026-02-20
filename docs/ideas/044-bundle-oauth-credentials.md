---
id: 044
title: Bundle OAuth Client Credentials for Zero-Friction Onboarding
status: idea
effort: M
value: Users can install and auth without touching GCP — just `desk auth login` and a browser consent
created: 2026-02-20
updated: 2026-02-20
adr: null
---

# Idea 044: Bundle OAuth Client Credentials for Zero-Friction Onboarding

## Problem

Today, users must obtain `credentials.json` from a Google Cloud project before they can run `desk auth login`. This requires either:

1. Creating their own GCP project, enabling APIs, and configuring an OAuth consent screen
2. Getting `credentials.json` from a teammate who already has one

This is the single biggest onboarding friction point. Non-technical users can't self-serve, and even developers find it tedious.

## Sketch

OAuth client IDs are not secrets — they identify the application, not the user. The user's own OAuth consent (the browser prompt) is the security boundary. Google's own tools (gcloud CLI, Chrome, etc.) ship with bundled client IDs.

Proposal:

1. Create a dedicated GCP project (e.g., `desk-agent-tools`) for the parent agent-tool suite
2. Configure OAuth consent screen, enable Gmail/Drive/Sheets/Docs/Calendar/Forms APIs
3. Bundle `credentials.json` as package data inside `src/desk/data/credentials.json`
4. Update `auth.py` to use bundled credentials by default, with `--credentials` flag to override
5. Users run `desk auth login` → browser opens → consent → done

The bundled credentials would be included in the wheel via `pyproject.toml` package data configuration.

Users who want their own GCP project can still provide `--credentials path/to/credentials.json` or place it at `~/.desk/credentials.json` (which would take precedence).

## Open Questions

- [ ] Should the bundled client ID be scoped narrowly (just Gmail) or broadly (all Workspace APIs desk supports)?
- [ ] Do we need a shared GCP project, or can one person's project credentials be reused? (Answer: shared project is cleaner — avoids single-person dependency)
- [ ] Rate limit implications of all users sharing one client ID? Google's per-user quotas should handle this, but worth verifying.
- [ ] Should `desk setup` (the interactive onboarding command) detect bundled credentials and skip the "provide credentials.json" step?

## Value Signal

This is the #1 onboarding blocker. Every new user hits it. Part of the broader parent suite onboarding initiative to make all agent-first tools installable and runnable in minutes.

## Effort Guess

M — Mostly config and packaging work. The auth flow itself doesn't change much. Main effort is creating the GCP project, testing the bundled flow, and updating the setup command.

## Notes

- Companion to cafe idea 024 (bundle Slack app credentials)
- Part of the parent suite onboarding initiative
- `uv tool install git+https://github.com/robpc/desk` already works — this idea removes the post-install auth friction
