---
id: 036
title: Calendar Date Flag
status: planned
effort: S
value: Agents can query any day's events without over-fetching from `cal next`
created: 2026-02-08
updated: 2026-02-08
adr: null
---

# Idea 036: Calendar Date Flag

## Problem

`desk cal today` only shows today. `desk cal week` only shows this week. There's no way to ask "what's on my calendar tomorrow?" or "show me Thursday" without using `cal next` and manually filtering. Agents end up over-fetching and parsing dates themselves.

## Sketch

- Add `--date YYYY-MM-DD` option to `cal today` (show events for that specific day)
- Add `--date YYYY-MM-DD` option to `cal week` (show the week containing that date)
- No flag = current behavior (today / this week)

This stays within Google Calendar's vocabulary — it's just "list events for a time range" with a user-specified anchor date.

## Value Signal

Hit this immediately when trying to answer "what's on my docket tomorrow morning?" — had to grab 15 upcoming events and filter manually.

## Effort Guess

S — add a Click option, parse the date, pass it to the service layer which already accepts arbitrary time ranges via `_list_events`.
