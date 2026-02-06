---
id: 001
title: OAuth and Credential Strategy
status: accepted
date: 2025-02-06
supersedes: []
superseded_by: null
tags: [auth, security, config]
---

# ADR-001: OAuth and Credential Strategy

## Context

Gmail CLI needs to authenticate with Gmail API. Gmail requires OAuth 2.0 - there's no API key option for user mailbox access.

Key considerations:
- Tool will be used by a small team (coworkers)
- Must not trigger company security scanners (no secrets in repos)
- Should be simple to set up and maintain
- Users should authenticate once and stay authenticated

OAuth distribution models:
1. **Shared OAuth client** - Developer ships client_id/secret, users just login
2. **User-owned credentials** - Each user creates their own OAuth client

For Gmail specifically, shared OAuth clients require Google verification (expensive, time-consuming) or are limited to 100 manually-added test users with a scary "unverified app" warning.

## Decision

We will use the **user-owned credentials** model:

1. Users create their own Google Cloud project (or share a project as Editors)
2. Each user creates their own OAuth client credentials
3. Credentials stored in `~/.gm/credentials.json`
4. Tokens (including long-lived refresh token) stored in `~/.gm/token.json`
5. CLI reads credentials from config dir, never from repo

Token lifecycle:
- Access tokens: 1 hour (auto-refreshed by library)
- Refresh tokens: Effectively indefinite (until revoked or unused for 6 months)

## Alternatives Considered

### Alternative 1: Shared OAuth Client (Ship credentials with CLI)

**Description**: Embed client_id/secret in the CLI, users just run `gmail auth login`

**Pros**:
- Simplest user experience
- No Google Cloud setup per user
- How `gcloud` CLI works

**Cons**:
- Gmail is "sensitive scope" - requires Google verification
- Verification costs $15k-$75k for security audit
- Unverified apps limited to 100 test users, scary warning
- Secrets in repo would trigger security scanners

**Why rejected**: Verification cost and security scanner issues make this impractical for an internal tool.

### Alternative 2: Service Account with Domain-Wide Delegation

**Description**: Admin grants service account access to all users' mailboxes

**Pros**:
- No per-user OAuth flow
- Centralized management
- Works for Google Workspace orgs

**Cons**:
- Requires Workspace admin privileges
- Only works for Workspace accounts (not personal Gmail)
- Over-privileged (service account can access all mailboxes)

**Why rejected**: Not all users are on Workspace, and requires admin involvement.

### Alternative 3: App Passwords

**Description**: Users create Gmail app-specific passwords, CLI uses IMAP/SMTP

**Pros**:
- No OAuth complexity
- Simple username/password auth

**Cons**:
- Requires 2FA enabled
- Less secure pattern (password storage)
- IMAP/SMTP more limited than Gmail API
- Google discourages this approach

**Why rejected**: Inferior security model and API limitations.

## Consequences

### Positive

- No secrets in repo - security scanners happy
- No Google verification needed
- Each user has full control over their credentials
- Revocation is per-user (user can revoke in their Google account)
- Works for both Workspace and personal Gmail accounts

### Negative

- More setup friction per user (~10 minutes first time)
  - *Mitigation*: Clear setup documentation with screenshots
- Each user needs to understand Google Cloud Console basics
  - *Mitigation*: Step-by-step guide in README

### Neutral

- Users can share a Google Cloud project (as Editors) but create separate OAuth clients
- Config stored in `~/.gm/` following XDG-ish conventions

## Implementation Notes

**Setup flow for users**:
1. Create Google Cloud project (or get added to shared project)
2. Enable Gmail API
3. Create OAuth client (Desktop app type)
4. Download `credentials.json` to `~/.gm/`
5. Run `gmail auth login` - browser opens, user approves
6. Token saved to `~/.gm/token.json`
7. Done - subsequent commands use stored token

**Key files**:
- `src/gm/auth.py` - OAuth flow implementation
- `src/gm/config.py` - Config directory paths

**Libraries**:
- `google-auth-oauthlib` - OAuth flow
- `google-api-python-client` - Gmail API client

## References

- [Gmail API OAuth quickstart](https://developers.google.com/gmail/api/quickstart/python)
- [Google OAuth 2.0 for Desktop Apps](https://developers.google.com/identity/protocols/oauth2/native-app)
- Conversation discussing trade-offs: 2025-02-06
