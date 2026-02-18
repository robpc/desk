---
id: 042
title: Forms — Quiz Mode
status: idea
effort: M
value: Agents can create quizzes with correct answers, point values, and grading
created: 2026-02-18
updated: 2026-02-18
adr: null
---

# Idea 042: Forms — Quiz Mode

## Problem

The Forms API supports quizzes natively — forms that grade responses against correct answers and assign point values. Desk has no way to create or manage quizzes. An agent building a training assessment, homework assignment, or knowledge check can't set correct answers, assign point values, or retrieve scores.

## Sketch

### New flags on existing commands

- `desk forms create --quiz` — Create a form in quiz mode (`isQuiz: true` in form settings)
- `desk forms add-question ... --answer "correct value" --points 10` — Set correct answer and point value
- `desk forms update-question ... --answer "new answer" --points 5` — Update correct answer/points

### New or updated output

- `desk forms read` — Show correct answers and point values when present (quiz-aware output)
- `desk forms responses` — Include score data when the form is a quiz

### API surface

All quiz features use the existing `batchUpdate` endpoint:
- `updateFormInfo` with `updateSettings` to enable quiz mode
- `createItem` / `updateItem` with `grading` field for correct answers and point values
- Responses API already returns score data for quizzes

## Open Questions

- [ ] How should correct answers be specified for different question types? (text match, choice selection, multiple correct answers for checkbox)
- [ ] Should we support answer feedback (explanation shown after grading)?
- [ ] Should `desk forms update` gain a `--quiz / --no-quiz` flag to toggle quiz mode on existing forms?
- [ ] How to handle partial credit (e.g., checkbox with 3 correct, student picks 2)?

## Value Signal

Education and training are common form use cases. Agents building onboarding flows, assessment tools, or study aids would use this immediately.

## Effort Guess

M — The API surface is straightforward (`grading` field on questions, `isQuiz` setting). The complexity is in the UX: how to specify correct answers for different question types (especially checkbox with multiple correct answers) and how to display grading data clearly.

## Notes

- Split from idea 040, which originally bundled mutations, pagination, and quiz mode
- ADR-007 documents the initial Forms scope decisions
- The Forms API `grading` field supports `correctAnswers` and `pointValue` per question
