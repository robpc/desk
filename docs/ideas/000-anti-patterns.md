# Anti-Patterns: What NOT to Build

This document captures patterns we've explicitly decided against. Read this before proposing new features.

## Cross-Service Convenience Commands

**Example**: `desk brief` - a "morning brief" combining today's calendar events with unread emails.

**Why it seems like a good idea**:
- Common workflow
- Demonstrates value of unified CLI
- Convenient for users

**Why we rejected it** (see ADR-003):

1. **Desk is a toolkit for agents, not a productivity app.** Agents should compose workflows from primitives, tailored to each user.

2. **It encodes opinions.** A "brief" decides what matters (today's events + unread). But users differ: one wants unread from specific senders, another wants tomorrow's events, another wants starred Drive files.

3. **It limits agent creativity.** If `desk brief` exists, agents use it lazily instead of composing `desk cal today` + `desk mail search "is:unread from:important"` + whatever else is relevant.

4. **It violates "no invented vocabulary" (ADR-002).** "Brief" is our term, not Google's.

**The principle**: Desk provides vocabulary (service operations). Agents write sentences (workflows).

**What to do instead**:
- Users can create shell aliases for their personal workflows
- Agents can compose commands for each user's specific needs
- Skills/recipes can encode reusable patterns outside the core CLI

## Compound Commands Within a Service

**Example**: `desk mail dismiss` - archive + mark-read in one command.

**Why we rejected it** (see ADR-002):
- "Dismiss" is vocabulary we invented, not Gmail's
- Users can compose with `desk mail modify --remove-label INBOX --remove-label UNREAD`
- Or create an alias: `alias desk-dismiss='desk mail modify --remove-label INBOX --remove-label UNREAD'`

**The test**: If you're naming a command with a word that doesn't appear in the service's UI or API docs, it's probably invented vocabulary.
