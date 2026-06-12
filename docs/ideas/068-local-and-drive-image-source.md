---
id: 068
title: Local / Drive Image Source for Slides + Docs insert-image
status: parked
effort: M
value: Insert an image from a local file or Drive id, not only a public URL
created: 2026-06-09
updated: 2026-06-09
adr: null
---

> **UPDATE (2026-06-09) — SOLVED via GCS signed URLs (proven end-to-end).** The earlier
> "impossible in a restricted domain" conclusion was wrong. Verified working recipe in
> `media-orion-d`:
> 1. `gcpfed` as the project power user → active identity `fed-power-user@media-orion-d`,
>    which already holds `roles/iam.serviceAccountTokenCreator` at the project level (no new
>    grant, no Gacco/PSR exception — signing via impersonation is the sanctioned path; SA
>    keys are what's banned, SBC-GCP-1004).
> 2. `gcloud storage cp <local> gs://<private-bucket>/obj` (private; no public access).
> 3. `gcloud storage sign-url … --duration=10m --impersonate-service-account=fed-power-user@…`
>    → ~820-char v4 signed URL (well under the 2 KB cap).
> 4. `desk slides insert-image <id> <slide> --url "<signed-url>"` → Slides fetches it
>    anonymously (curl confirmed HTTP 200 image/png) and copies the bytes; the URL can then
>    expire. Verified: image inserted successfully.
>
> Non-prod, non-public, not `s.yimg.com`, Paranoids-sanctioned. Caveats: the proof used the
> broad `fed-power-user`; a real automation should use a **dedicated least-privilege signing
> SA**. It needs GCP creds (`gcpfed`) alongside Workspace OAuth — two auth contexts — so it
> stays a **compose step / thin helper**, NOT bundled into Desk.
>
> **Decision (2026-06-09):** Desk core ships **public `--url` only** (Workspace-only, no GCP
> deps). The signed-URL upload→sign→URL step composes with `desk ... --url` and, if built,
> lives in its **own small tool / runbook** (now de-risked — proven viable).
>
> **Parked 2026-06-09 — blocked for restricted Workspace domains; no REST API path.**
> Implemented `--file`/`--drive-id` (upload → anyone-with-link → createImage → delete temp),
> but it **cannot work in this org** and the happy path is **unverified anywhere from here**.
> The code was reverted off `feat/slides-support` (kept public `--url`, which works).
>
> **Findings (all verified live against the Slides REST API + OAuth):**
> - `createImage` fetches the image **anonymously** — it does NOT use the caller's
>   OAuth/Drive scope. A private Drive file is rejected via every URL form:
>   `…/drive/v3/files/{id}?alt=media` → *"Access to the provided image was forbidden"*;
>   `uc?export=download` and `drive.usercontent.google.com/download` → *"should be publicly
>   accessible"*. (So a service account wouldn't help either — still anonymous.)
> - Making the temp file `anyone`-with-link is **blocked by domain policy** here
>   (`publishOutNotPermitted` — yahooinc forbids external link sharing).
> - **data: URIs are rejected** (tested a 118-char tiny PNG → 400). The `url` field is
>   capped at 2 KB and must be a public HTTP(S) URL (PNG/JPEG/GIF, <50MB, <25MP).
> - There is **no direct-bytes upload** in the Slides REST API.
> - The only runtime that can insert a private/local image is **Apps Script**
>   (`slide.insertImage(blob)` runs inside the org and accepts raw bytes) — a different
>   runtime Desk (REST/OAuth CLI) cannot use.
>
> **Net:** in a domain that blocks public sharing, inserting a local image into Slides via
> the REST API is impossible; only a genuinely public off-Drive `--url` works. Revive this
> only to verify `--file` against a *permissive* account (personal Google / org allowing
> link-sharing), where the upload→share→insert→delete flow should work.
>
> **Docs `insert-image` shares the exact same limitation** (URL-only, same anonymous fetch)
> — the "make the same fix in docs later" follow-up is blocked by the same wall; only worth
> doing alongside a verified slides `--file`.

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
