# Security Policy

## Supported versions

Only the latest version on `main` is supported. There are no LTS branches.

## Reporting a vulnerability

**Please do not open public issues for security vulnerabilities.**

Use [GitHub's private security advisory](https://github.com/robpc/desk/security/advisories/new) to report. This keeps the report confidential and creates a coordinated-disclosure thread between you and the maintainer.

I'll acknowledge the report within a few business days. Disclosure timing depends on severity and complexity, but the target is a fix and public disclosure within 30 days where practical.

## Scope

Desk runs locally and stores OAuth tokens in the OS keychain (per [ADR-012](docs/decisions/012-keyring-credential-storage.md)). The threat model focuses on:

- Local credential exposure (e.g., tokens written to disk in cleartext, weak file permissions)
- Privilege escalation via crafted Google API responses
- Command injection via user-supplied flags or input
- Insecure handling of the OAuth flow

Out of scope — these are Google's surface, not desk's:

- Vulnerabilities in Google Workspace APIs themselves
- Issues with the user's GCP project configuration or OAuth consent screen
- Phishing or social engineering targeting end users

If you're unsure whether something is in scope, report it anyway — we'll figure it out together.
