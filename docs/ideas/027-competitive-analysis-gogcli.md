# Idea 027: Competitive Analysis — gogcli

**Status**: adr-created
**Created**: 2025-02-07
**Tags**: strategy, competitive-analysis

## Context

Discovered [gogcli](https://github.com/steipete/gogcli), an open-source Google Workspace CLI written in Go. It's more mature and feature-complete than Desk.

## Comparison

| Aspect | Desk | gogcli |
|--------|------|--------|
| Language | Python | Go |
| Services | 5 (Gmail, Drive, Sheets, Docs, Calendar) | 12+ (adds Chat, Classroom, Contacts, Tasks, People, Groups, Keep, Slides) |
| Auth storage | Plain file (`~/.desk/token.json`) | OS Keychain or encrypted file |
| Multi-account | No | Yes, with aliases |
| Service accounts | No | Yes, with domain-wide delegation |
| Scope control | Fixed at auth time | Per-command `--readonly`, `--drive-scope` |
| Installation | pip | Homebrew, Go build |

## Honest Assessment

Desk's stated design principles ("toolkit not app", "no invented vocabulary", "agent-first") don't create meaningful differentiation — gogcli follows the same principles implicitly.

### What gogcli Does Better
- More services covered
- Better credential security (OS keychain)
- Enterprise-ready (service accounts, domain delegation)
- Multi-account workflows
- Granular, least-privilege scopes
- Mature, actively maintained

### What Desk Offers
- Python ecosystem (if you need to extend/embed it)
- That's about it currently

## The Hard Question

**Why should Desk exist?**

Options:
1. **Deprecate it** — Use gogcli instead, don't reinvent the wheel
2. **Narrow focus** — Pick a few services and do them exceptionally well (but gogcli already does them well)
3. **Different audience** — Target Python developers who want a library, not just CLI users
4. **True agent differentiation** — Build features specifically for LLM agents that gogcli doesn't have

## Potential Differentiating Features (if continuing)

If we decide Desk should continue, here are features that could create real differentiation:

### Agent-Specific Features
- **Structured error responses** — Errors as JSON with suggested fixes, not just text
- **Context-aware output** — `--context` flag that includes metadata an LLM needs to take next actions
- **Batch operations** — Process multiple items in one call to reduce agent round-trips
- **Dry-run mode** — `--dry-run` on destructive operations so agents can preview before committing

### Python Library
- Expose `GmailClient`, `DriveClient`, etc. as a proper Python API
- Enable programmatic use in agent frameworks (LangChain tools, etc.)
- This is something a Go CLI can't easily provide to Python users

### Simpler Auth Story
- Zero-config auth for personal use (like `gh auth login`)
- Embed a default OAuth client for non-commercial use
- Trade security for convenience in the personal/hobby tier

## Decision Needed

Before investing more time in Desk, we should decide:

1. Is there a real audience that needs this over gogcli?
2. If yes, what specific features justify the investment?
3. If no, should we archive the project and document gogcli as the recommendation?

## Next Steps

- [ ] Review with stakeholders
- [ ] If continuing: write ADR for chosen differentiation strategy
- [ ] If not continuing: archive gracefully with pointer to gogcli

## Related

- **ADR-004: Agent-First CLI Design** — Decision made based on this analysis
- ADR-003: Toolkit, Not Productivity App
- ADR-002: No Invented Vocabulary
