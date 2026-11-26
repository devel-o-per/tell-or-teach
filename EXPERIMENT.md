# Pre-registered experiment: Tell Me or Teach Me

This file is committed **before** the production experiment is created in Flagsmith.
The commit timestamp shows the rules were set before any real data arrived.

## Question

After a student gets a practice question wrong, should an AI tutor **tell** them the answer,
or **teach** them to find it with guiding questions?

## Hypothesis

After a wrong answer, a tutor that asks guiding questions (`teach`) leads to higher accuracy on the
**comeback question** for the same concept than a tutor that explains the answer (`tell`).

## Design

| Item | Decision |
|---|---|
| Flag | `tutor_style`, multivariate: `tell` (control), `teach` (treatment) |
| Audience | Everyone, 100% enrolled, 50/50 split, assignment fixed per anonymous ID |
| Exposure | Recorded on the server the first time the tutor replies to a student |
| Primary metric | Comeback accuracy: event `comeback_scored` (1 or 0), aggregation **Mean**, higher is better |
| Also tracked | Practice volume (`question_answered`), comeback completion rate, AI tokens per student, tutor turns per mistake, which AI provider answered |
| Exploratory (never the headline) | Confident mistakes vs guesses; results per WhatsApp group |

## Keeping the comparison fair

- Both styles use the same AI provider chain in the same order (Groq, then NVIDIA Nemotron, then Gemini),
  the same token cap and the same chat screen. Only the system prompt differs (see `backend/tutor.py`).
- When the AI is unavailable, each style falls back to **its own** written version
  (Tell: written explanation; Teach: written hints, then a second try), so no student changes style.
- Teach replies pass an answer-leak guard. A leaking reply is regenerated once with a stricter prompt,
  then replaced by a written hint.
- The comeback question is the twin of the missed one: the same idea in new words, shown three questions later.
  Comebacks are never tutored, and retries inside the tutor are never scored.
- New subjects are released with the `question_set` flag, so both styles get new questions at the same moment.

## Decision rule

- Ship `teach` if Flagsmith reports a probability of at least **95%** that it beats `tell` on comeback accuracy,
  and practice volume is not clearly lower. Otherwise keep `tell` and report the result as it is.
- A WhatsApp group gets its own winning style (segment override on the `group` trait) only if that group's
  own data also reaches 95%.
- Analysis is frozen on **Sunday 29 November 2026, 12:00 IST**.

## Known limits

Students choose to take part (self-selection), the run lasts about three days (novelty), the sample is
whatever the groups bring, and questions cover a few subjects only.
