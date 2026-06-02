---
id: 025
title: Person smart-chips in Sheets cells
status: accepted
date: 2026-06-02
supersedes: []
superseded_by: null
tags: [sheets, api, cli, chips]
---

# ADR-025: Person smart-chips in Sheets cells

## Context

Agents building owner/assignee columns in spreadsheets need to tag real
people, not just type plain-text names. A plain string ("Alice") is
ambiguous (name collisions, typos, no link to identity) and never
notifies anyone. Google Sheets supports **person smart-chips** — the same
`@person` chip you get in the UI — which resolve against the directory
(canonical display name, hover card, and the notification behavior of an
@-mention).

`desk sheets` today only writes plain values via the Values API
(`write`, `update-cell`, `append`). Smart-chips are not values; they live
in `CellData.chipRuns` and can only be written through the lower-level
`spreadsheets.batchUpdate` (`updateCells`) call. There was no way to set
one through desk, so callers had to drop to raw `googleapiclient` against
desk's credentials — exactly the kind of workflow desk should expose as a
primitive.

This need is real: it came out of building an ADR-review tracker where
each row's owner had to be a tappable person, and the only path was a
one-off script.

## Decision

Add `desk sheets chip <spreadsheet_id> <cell> <email>` — sets a single
**person** smart-chip in one cell, replacing the cell's contents.

- One chip, one cell. A single cell argument in A1 notation
  (`"Sheet1!D2"`); no ranges. Agents loop for multiple cells (Unix
  composition, and one chip per call sidesteps the API's 10-people-chips-
  per-`batchUpdate` cap).
- `--format DEFAULT|EMAIL|LAST_NAME_COMMA_FIRST_NAME` controls the chip's
  display, mirroring the API's `PersonChip.displayFormat`. Defaults to
  `DEFAULT` (directory "First Last").
- Standard `--json` / `--quiet` and an operation receipt, like every other
  mutating sheets command.

The implementation parses the A1 cell to a `GridCoordinate`
(sheet name → `sheetId`, plus 0-based row/column), then issues an
`updateCells` request with `userEnteredValue.stringValue = "@"` and a
matching `chipRuns` entry carrying `personProperties.email`.

## Alternatives Considered

### Alternative 1: Range + list of emails in one command

**Description**: `desk sheets chip <id> <range> <emails_json>` to chip many
cells at once.

**Pros**:
- Fewer process spawns for bulk tagging.

**Cons**:
- The Sheets API caps people-chip requests at 10 per `batchUpdate`, so the
  command would need internal chunking — hidden complexity.
- Breaks the one-cell-one-call mental model of `update-cell`.

**Why rejected**: Violates the single-primitive principle (ADR-003).
Agents compose loops; desk shouldn't hide a batching/limit dance.

### Alternative 2: A `--chip` flag on the existing `write`/`update-cell`

**Description**: Overload an existing command to optionally emit a chip.

**Pros**:
- No new command.

**Cons**:
- `write`/`update-cell` go through the Values API; chips require
  `batchUpdate`. Overloading would fork their implementation on a flag.
- Muddies two distinct concepts (cell value vs. chip).

**Why rejected**: Different API surface and a distinct concept deserve a
distinct command.

## Consequences

### Positive

- Agents can build owner/assignee columns of real, directory-linked people
  through a first-class primitive instead of a raw-API script.
- Chip resolution self-corrects names from the email (a misspelled display
  name becomes the directory's canonical name).
- "Smart chip" is Google's own vocabulary, so the command satisfies
  ADR-002 (no invented vocabulary).

### Negative

- Inserting a chip **overwrites** the cell's prior contents (documented in
  `--help`). No undo command; the prior value is not recoverable.
- File chips and other chip types are out of scope — person chips only for
  now.

### Neutral

- Adds one `batchUpdate` path to `SheetsClient`; the existing
  `add_sheet`/`delete_sheet`/`rename_sheet` already use `batchUpdate`, so
  no new dependency.

## Implementation Notes

- `src/desk/services/sheets.py`: `set_person_chip()` plus A1-cell parse
  helpers (`_parse_a1_cell`, `_column_to_index`, `_resolve_sheet_id`).
- `src/desk/commands/sheets.py`: `chip` command.
- `CLAUDE.md`: architecture diagram updated under `sheets`.

## References

- [Sheets API — Smart chips](https://developers.google.com/workspace/sheets/api/guides/chips)
- ADR-002 (command composability / no invented vocabulary)
- ADR-003 (toolkit, not productivity app)
