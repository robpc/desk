---
id: 068
title: Local / Drive Image Source for Slides + Docs insert-image
status: idea
effort: M
value: Insert an image from a local file or Drive id, not only a public URL
created: 2026-06-09
updated: 2026-06-09
adr: null
---

# Idea 068: Local / Drive Image Source for Slides + Docs insert-image

## Problem

`desk slides insert-image --url` and `desk docs insert-image --uri` both accept **only a
publicly accessible URL**. An agent with a local image file (or a Drive file id) can't
insert it without first hosting it somewhere public. Flagged during Slides testing as "the
same image issue docs has" — it's a shared limitation, not slides-specific.

## Sketch

Add a local/Drive source path shared by both commands:

- `--file <path>`: upload the local image to Drive (reuse DriveClient upload), make it
  fetchable, then insert by the resulting URL. Consider cleanup/visibility implications.
- `--drive-id <id>`: resolve a Drive image file to a URL the Slides/Docs API can fetch.

Keep `--url`/`--uri` as-is; the new flags are alternatives.

## Open Questions

- [ ] Does Slides `createImage` accept a Drive `contentUrl`/`sourceUrl` directly, or must we
      produce a public URL? Same question for Docs `insertInlineImage`.
- [ ] Visibility/permissions: uploading then inserting may require the file be accessible to
      the API fetcher; what's the least-surprising default (and cleanup)?
- [ ] Shared helper vs per-command implementation (the two services差 in request shape).

## Value Signal

Real user friction across two services. Common case: "insert this chart I just generated."

## Effort Guess

M — Drive upload/resolve + URL plumbing in two commands; permission edge cases.

## Notes

- Related: [[slides-phased-rollout]]; Idea 055 (visual elements) noted the Drive-id question.
- Cross-cutting (docs + slides) — worth a shared approach.
