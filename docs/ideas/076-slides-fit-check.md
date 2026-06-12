---
id: 076
title: Headless slides fit/overflow check (skill)
status: implemented
effort: M
value: Detect text overflow/dead-space/off-center headlessly — replaces ~60-70% of render-and-eyeball cycles
created: 2026-06-10
updated: 2026-06-10
adr: null
---

# Idea 076: Headless slides fit/overflow check

## Problem

Building a polished deck, the recurring failure was "box looks funny" — text
overflowing its box, dead space, or mis-centered — with **no programmatic signal**.
The Slides API exposes box geometry (via `inspect`, Idea 064) but **no rendered text
metrics**, so the only check was export → rasterize (Quartz) → eyeball. The test session
confirmed a headless geometry report would replace ~60-70% of its render cycles; vision is
still needed only for color/aesthetics.

## What was implemented

A **personal skill** `~/.claude/skills/slides-fit/` (not Desk-core — it needs a PDF lib and
rendering, like `workspace-image`). `fit_check.py`:

1. `desk slides export <id>` → PDF; `desk slides inspect <id> --json` → per-shape boxes.
2. Parse the PDF **text layer** (PyMuPDF). Slides pt == PDF pt, same origin, page == slide
   size, so boxes and text bboxes compare **1:1** (verified).
3. Match each text **block** to the shape its top-left starts inside (smallest box wins
   ties) — robust to overflow lines and vertical stacking.
4. Per shape: `overflowPt` + per-edge overflow (hard signal), `deadSpaceBelow/Above`,
   `offCenterInBox` dx/dy, `fillRatio`, `status` (soft hints). JSON or human; nonzero exit
   on any overflow (for fix loops).

Fix loop: run → fix overflow via `style --font-size` / `set-text` / `place --width/--height`,
fix centering via `style --align` / `format --valign` → re-run. Render only for color/aesthetics.

**Update (2026-06-10):** added `suggestedHeight` (box height that hugs the text at its current
font, keeping the box's horizontal inset as top/bottom padding) and `suggestedFontScale` (factor
to shrink the font to fit the current box height; ≥1 = already fits). This is the composition
answer to deck-builder's autofit ask — the Slides API can't *set* autofit, so the checker emits
the two concrete fix numbers (grow the box, or shrink the font) instead of adding a new command.
Live-verified: a 28pt headline in a 40pt box → `box height 210.3pt OR font ×0.134`.

## Notes

- Live-verified: a 36pt headline in a 40pt box → `overflow 313.9pt`; a roomy "Fits fine"
  box → `ok`; empty placeholders → no phantom text.
- **Matching evolved via two real test catches:** (1) an initial span/x-range matcher
  mis-attributed a tall overflow's wrapped lines to the box below → switched to block
  ownership (top-left). (2) `deck-builder` then hit side-by-side columns sharing a baseline
  (PyMuPDF merges them into one line → false right-overflow on the leftmost) → final design:
  block ownership for vertical flow + **per-span x-column re-attribution** so merged lines
  split back to their columns. Verified: 3 same-baseline cards → all ok; isolated overflow →
  still flagged. Remaining ambiguity: vertically-stacked boxes in one x-column.
- No Desk change needed (uses existing `export` + `inspect`). The optional `inspect`
  text/font enrichment was NOT done (skill works without it).
- Limits: overlapping text shapes can still be ambiguous; tables skipped; render-dependent
  (one export per run). Geometry only — color/aesthetic/composition stay with vision.
- Resolves feedback #3. Related: [[slides-phased-rollout]]; Idea 064 (inspect boxes), 075
  (place resize — a fix lever).
