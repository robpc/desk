# Contributing to Desk

Thanks for your interest! Desk is a personal open-source project that welcomes outside contributions.

## License

By contributing, you agree your contributions are licensed under [Apache 2.0](LICENSE), per Apache 2.0 §5.

## Dev setup

```bash
git clone https://github.com/robpc/desk
cd desk
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Tests and lint

```bash
pytest                # tests
ruff check src/       # lint
ruff format src/      # auto-format
```

Run both locally before pushing.

## Submitting changes

1. Fork and create a feature branch
2. Make your change with tests
3. Run `pytest` and `ruff check src/`
4. Open a PR — CI runs CodeQL + dependency review automatically
5. PRs require one approving review. Squash merge is the only merge method.

## Project conventions

Read these before any non-trivial change:

- [`docs/decisions/`](docs/decisions/) — ADRs for significant choices already made. Especially [ADR-002](docs/decisions/002-command-composability.md), [ADR-003](docs/decisions/003-unified-workspace-cli.md), and [ADR-004](docs/decisions/004-agent-first-cli.md) — they constrain what kinds of additions fit (toolkit primitives, not invented vocabulary or composed productivity commands).
- [`docs/ideas/`](docs/ideas/) — lightweight captures of future work. Lifecycle: `idea → exploring → planned → adr-created → implement`.

If your change involves a meaningful architectural choice — new command, new service, naming convention, library swap, reversing an existing ADR — write an ADR alongside the implementation. Templates are at `docs/decisions/_template.md` and `docs/ideas/_template.md`.

## Code style

- Python 3.10+
- Type hints throughout
- `click` for CLI, `rich` for terminal output
- Minimal dependencies — propose new runtime deps in an issue first
- Prefer Unix-philosophy primitives over composed convenience commands (per ADR-003)
- `--json` output for any new command that returns structured data

## Reporting

- Bugs and feature requests: GitHub Issues
- Security issues: see [SECURITY.md](SECURITY.md) — please don't open public issues for these
