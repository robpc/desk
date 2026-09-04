---
id: "036"
title: Build Provenance in `--version`
status: accepted
date: 2026-09-03
supersedes: []
superseded_by: null
tags: [cli, agent-first, build, versioning]
---

# ADR-036: Build Provenance in `--version`

## Context

`desk --version` reports `0.3.0`, and reported `0.3.0` across changes that
altered what commands do. [#88](https://github.com/robpc/desk/issues/88)
added `-c/--calendar` to the write commands and
[#89](https://github.com/robpc/desk/issues/89) changed the wall-clock time
a naive `--start` resolves to — after `uv tool upgrade desk`, the version
string was unchanged. The same string names a build where
`cal create --start 2026-11-11T17:30:00` produces 4:30pm and one where it
produces 5:30pm. See
[`robpc/desk#93`](https://github.com/robpc/desk/issues/93).

Bumping the version per release helps and is worth doing, but does not
close this. desk is commonly installed straight from git:

```
uv tool install git+https://github.com/robpc/desk
```

which tracks a branch, not a release. Between tags — which is most of the
time for a tool under active fixing — no amount of diligence with the
version string distinguishes two builds.

Two concrete costs. An operator cannot record which desk a deployment is
running. And `uv tool upgrade desk` is unverifiable: it reports that it
did something, the version afterwards is identical, and the only way to
confirm the new behavior is to exercise it.

[ADR-011](011-non-engineer-install-and-versioning.md) keeps SemVer in
`pyproject.toml`, deferring CalVer to stay aligned with the surrounding
tool suite. Nothing here disturbs that: the version number keeps its
current scheme and source.

## Decision

Capture the commit at **build time** and surface it in `--version`:

```
$ desk --version
desk, version 0.3.0 (a837d65, 2026-09-03)
```

### How it is captured

A hatchling custom build hook (`hatch_build.py`) resolves the commit and
its date from git, and injects a generated `desk/_build_info.py` into the
wheel and sdist via `force_include`.

`force_include` matters: the file is **never written into the source
tree**. A hook that wrote `src/desk/_build_info.py` would either dirty
the working tree on every local build, or — if gitignored — risk being
excluded from the sdist by hatchling's VCS-aware file selection. Injecting
at package time sidesteps both.

When git is unavailable but a previously generated `_build_info.py`
exists (the sdist → wheel path), the existing values are carried through
rather than overwritten with unknowns.

### Runtime resolution order

1. **`desk._build_info`** — baked at build time. Authoritative, and works
   from an installed wheel with no repository present.
2. **`git rev-parse` against the package's own directory** — only when
   step 1 found nothing *and* the package sits inside a git work tree.
   This is the editable-install case (`uv tool install --editable .`),
   where build-time capture cannot apply because there is no build.
3. **Nothing** — version prints alone, exactly as today.

Step 2 is a deliberate narrowing of the issue's "build time rather than
shelling out to git at runtime." That instruction is about not depending
on git in an installed wheel, which step 1 satisfies. Step 2 fires only
where step 1 structurally cannot, costs one subprocess on a dev machine,
and is wrapped so that no git failure can ever break `--version`.

### `--version --json`

```json
{
  "version": "0.3.0",
  "commit": "a837d65",
  "commit_date": "2026-09-03",
  "source": "build"
}
```

`commit` and `commit_date` are `null` when unknown. `source` is one of
`build`, `git` or `unknown`, so a caller can tell a reproducible build
stamp from a dev checkout's live read.

This replaces `click.version_option`, which cannot vary its output by
another flag.

### `--capabilities` carries the commit too

`_get_capabilities()` already reports `version`; it gains `commit`. An
agent checking whether a fix is present reads capabilities, not
`--version`, so the provenance belongs in both.

## Alternatives Considered

### Alternative 1: `hatch-vcs` / `setuptools-scm`

**Description**: Derive the version itself from git tags, yielding
strings like `0.3.1.dev5+ga837d65`.

**Pros**:
- Solves the problem natively; no custom hook to maintain.
- The version string alone becomes unique per commit.

**Cons**:
- Changes the version *scheme*, which ADR-011 deliberately holds to
  SemVer-from-`pyproject.toml` to match the surrounding suite.
- `0.3.1.dev5+ga837d65` is worse to read aloud and worse in a
  bug report than `0.3.0 (a837d65)`.
- Makes the version depend on tag hygiene; an untagged repo produces
  surprising numbers.

**Why rejected**: It solves provenance by changing something ADR-011
settled for unrelated reasons. Keeping the number and adding the commit
beside it gets the same information at no cost to the scheme.

### Alternative 2: Shell out to git at runtime, always

**Description**: Resolve the commit on every `--version` from the
package's directory.

**Pros**:
- No build hook at all; one function.
- Always current in a dev checkout.

**Cons**:
- Returns nothing from an installed wheel, which is the case that
  motivated the issue.
- Worse: in a checkout it reports the *working tree's* HEAD, which may
  not be the commit the installed code was built from — confidently
  wrong rather than merely absent.
- A subprocess on every invocation.

**Why rejected**: Wrong for the primary case and actively misleading for
a non-editable install made from a since-moved checkout.

### Alternative 3: Bump the version on every behavior change

**Description**: Discipline instead of tooling — no release without a
version bump.

**Pros**:
- Zero code.
- Good practice regardless.

**Cons**:
- Does nothing for `install git+https://…`, which tracks a branch. Two
  builds from the same branch at different commits still report the same
  version.
- Relies on remembering, on every change, forever.

**Why rejected**: Worth doing and orthogonal. It does not address the
install path desk actually documents.

## Consequences

### Positive

- **A build is identifiable.** `desk --version` names the commit it was
  built from, and `--json` hands it to a script.
- **`uv tool upgrade desk` becomes verifiable** — the commit changes even
  when the version does not.
- **Agents can check for a fix** before relying on it, via
  `--capabilities`.
- **The version scheme is untouched**, so ADR-011 stands.

### Negative

- **A build hook is a moving part** that can fail on an unusual build
  host.
  - *Mitigation*: every git call is wrapped; a failure degrades to
    unknown values and never fails the build.
- **`--version` output changes shape**, which could break a caller
  parsing it.
  - *Mitigation*: the version number stays first and in the same
    position; the addition is a parenthetical suffix. `--json` exists
    precisely so nobody needs to parse prose.
- **Editable installs report the working tree's HEAD**, which may be
  ahead of the code as last imported.
  - *Mitigation*: `source: "git"` in the JSON marks exactly this case.

### Neutral

- A wheel built outside a repository reports the version alone, which is
  today's behavior.

## Implementation Notes

### Files affected

- `hatch_build.py` (new) — custom build hook; `force_include`s the
  generated `desk/_build_info.py`.
- `pyproject.toml` — register the hook for the `wheel` and `sdist`
  targets.
- `src/desk/version.py` (new) — `get_version_info()` implementing the
  three-step resolution, and the human-readable formatter.
- `src/desk/cli.py` — replace `click.version_option` with a `--version`
  flag handled in `main()`, add `--json`, add `commit` to
  `_get_capabilities()`.

## References

- [Issue #93](https://github.com/robpc/desk/issues/93) — bug report
- [ADR-011](011-non-engineer-install-and-versioning.md) — SemVer via
  `pyproject.toml`, CalVer deferred
- [ADR-004](004-agent-first-cli.md) — machine-readable introspection
- [Hatchling build hooks](https://hatch.pypa.io/latest/plugins/build-hook/custom/)
