---
id: 058
title: Bug — `desk docs export` likely passes unsupported supportsAllDrives
status: idea
effort: S
value: Fix a probable latent crash in docs export (and audit other export sites)
created: 2026-06-09
updated: 2026-06-09
adr: null
---

# Idea 058: Bug — `desk docs export` likely passes unsupported supportsAllDrives

## Problem

While live-verifying Slides export (Idea 054), `desk slides export` crashed with
`Got an unexpected keyword argument supportsAllDrives` — the Drive client's
`files().export()` does **not** accept `supportsAllDrives` (unlike `files().get()`).
Fixed in the Slides service.

`src/desk/services/docs.py::DocsClient.export` (≈ line 973) makes the identical call:

```python
self._drive.files().export(
    fileId=document_id, mimeType=mime, supportsAllDrives=True
).execute()
```

This almost certainly means `desk docs export` is broken the same way — the existing
docs export tests mock the Drive client, so they wouldn't catch a client-side argument
rejection.

## Sketch

- Remove `supportsAllDrives=True` from the `files().export` call in `docs.py`.
- Grep for other `files().export(` / `files().export_media(` sites and audit them for the
  same mistake.
- Add a test that exercises export against a non-mocked googleapiclient signature, or at
  least asserts the call doesn't pass `supportsAllDrives`, so this can't regress silently.

## Value Signal

`desk docs export` is a documented command; if it crashes on every invocation that's a
shipped regression. Low effort, clear fix.

## Effort Guess

S — One-line fix per site plus a guard test. The audit is quick.

## Notes

- Discovered during Slides Phase 1 live verification (Idea 054)
- Out of scope for the `feat/slides-support` branch (unrelated to Slides); tracked here
  so it isn't lost
