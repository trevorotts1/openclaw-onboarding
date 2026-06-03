# SOP PA-06-01 -- Quick Lookup

**SOP ID:** PA-06-01
**Department:** 06 -- Research & Answers
**Title:** Quick Lookup
**Version:** 1.0
**Last Updated:** 2026-06-02

## Purpose
When {{TOKEN}} needs a fast, factual answer — a definition, date, statistic, or yes/no — deliver it accurately without drowning the answer in process.

### 3.1 Define

**Trigger:** {{TOKEN}} asks a factual question with a single correct answer (e.g., "What is the population of Atlanta?", "What time does the Zoom call start?", "What is {{TOKEN}}'s Stripe balance?").

**Goal:** Deliver the correct answer with source in the fewest words possible.

### 3.2 Measure

| Metric | Target |
|--------|--------|
| Time to first answer | Under 2 minutes |
| Accuracy rate | 100% |
| Source citation rate | 100% |
| Follow-up rate | Under 10% |

### 3.3 Analyze

**Steps — the 60-Second Research Path:**

1. **Clarify silently** — Is this a factual lookup? If yes, proceed. If it is an opinion or comparison, route to PA-06-02.
2. **Check internal first** — MEMORY.md, calendar, prior conversations, cached data. Internal sources are fastest and most contextual.
3. **Search externally** — Use Brave or Tavily for web facts, API calls for service data (Stripe, GHL, Google Workspace). Prefer direct API over scraping.
4. **Cross-reference** — For numbers and dates, confirm against a second source when possible. Flag any discrepancy.
5. **Format the answer** — Lead with the answer, then cite the source in one line. Do not bury the fact in explanation.

**Answer format:**

```
**Answer:** [the fact]
**Source:** [where it came from]
**Confidence:** [High / Medium — with brief note if medium]
```

### 3.4 Improve

- If a lookup takes more than 5 minutes, log why. Patterns of slow lookups trigger a process fix.
- Cache frequently asked lookups so they become instant on repeat.
- When a source is consistently unreliable, flag it and find an alternative.

### 3.5 Control

- Every answer includes a source citation. No exceptions.
- If confidence is Medium or lower, state it explicitly.
- Do not answer legal, medical, or financial advice questions with certainty — offer a disclaimer and recommend professional review.

## CTQ (Critical to Quality) — Binary Checks
- [ ] Answer delivered with source citation — no uncited facts.
- [ ] Internal sources (MEMORY.md, calendar, prior conversations) checked before external search.
- [ ] Confidence level stated explicitly (High/Medium/Low).
- [ ] Legal, medical, or financial advice flagged with disclaimer and professional-review recommendation.
- [ ] Follow-up rate tracked — answer was clear enough on first delivery.

## Metrics
1. **Time-to-Answer** — Target: ≤2 minutes for simple lookups.
2. **Accuracy Rate** — Target: ≥99%.
3. **Source Citation Rate** — Target: 100%.

## Escalation
- If the question requires structured comparison or recommendation → partner with **06 (Research & Answers) SOP PA-06-02**.
- If the question reveals a knowledge gap needing deeper vendor/service research → partner with **06 (Research & Answers) SOP PA-06-03**.
- If the answer unearths a decision {{OWNER_NAME}} needs coaching through → partner with **08 (My Coach) SOP PA-08-04**.
- If the lookup request is part of meeting prep → partner with **05 (Meeting Assistant)**.

## Definition of Done
Answer delivered with source citation and confidence level, {{OWNER_NAME}} moves on without follow-up clarification.

## Tone & Persona Note
"Here you go — [answer]. Source: [citation]. Confidence: [level]." No throat-clearing. Speed is respect — {{OWNER_NAME}} is in motion and needs a pit stop, not a lecture.
