# Skill 44 — Workflow-Quality Rubric (8-Dimension Weighted Grade)

## Purpose

WF-1..WF-21 (`references/workflow-build-checklist-template.md`) is a **binary PASS/FAIL on
settings** — it answers "are the settings correct?" but never "is this the RIGHT workflow / how
well does it serve the client's stated goal?"

This rubric is a **graded 1–10 quality score** that sits **on top of** WF-1..WF-21. It is a
deliberate **SUPERSET OVERLAY**, NOT a replacement:

- Every dimension below **cites an EXISTING WF-1..WF-21 item (or `link_steps()`)** as its
  evidence source. The rubric reads the SAME artifacts WF-1..WF-21 reads; it adds no new
  infrastructure and **cannot contradict** the current QC.
- WF-1..WF-21 remains the **hard pass/fail gate**. The rubric is the **quality grade on top**.
- The rubric **reads outputs only** — it does NOT alter `workflow_builder.py`,
  `safety_gate.py`, `VERIFIED_ACTIONS`, or `link_steps()`. This guarantees it is non-breaking.

**Ordering at Step 9 QC GATE:** WF-1..WF-21 runs FIRST (via `qc-built-workflow.sh`). The
weighted rubric is computed AFTER, and only on a workflow whose mechanical WF items pass. The
rubric **never runs instead of** WF-1..WF-21.

---

## How to score

1. Run WF-1..WF-21 first (`qc-built-workflow.sh <wf-id> --json`). If any mechanical WF item
   FAILs, the build is not ready — fix and re-run; the rubric is not the place to "buy back" a
   hard WF failure.
2. For each of the 8 dimensions below, choose the **anchor** the built workflow most closely
   matches: **1**, **5**, or **10**. Interpolate to the nearest integer between anchors when the
   evidence sits between two anchors (e.g. a dimension that clears the 5-anchor and partially
   meets the 10-anchor = 7 or 8).
3. Multiply each dimension's 1–10 score by its weight, sum the weighted contributions, and
   divide by 100 → a single **weighted 1–10 score**.
4. **Ship threshold: weighted score ≥ 8.5** (aligns with the binding OpenClaw QC Protocol 8.5
   threshold). Below 8.5 → loop, **naming the specific low dimension** and the anchor it fell to.

```
weighted_score = (D1*20 + D2*15 + D3*15 + D4*12 + D5*12 + D6*10 + D7*8 + D8*8) / 100
```

A dimension that is genuinely **N/A** (e.g. D4 branching on a workflow with no branches) scores
**10** (a clean N/A is not a defect) and its anchor note records "N/A — no branches present".

---

## Dimension table (weights + evidence sources)

| #  | Dimension                              | Weight | Evidence source (existing)                       |
|----|----------------------------------------|--------|--------------------------------------------------|
| D1 | Goal-fit to stated intent              | 20%    | PLAN Step A1/A2 vs `caf workflows export`        |
| D2 | Trigger correctness                    | 15%    | WF-3, WF-4                                       |
| D3 | Action/step completeness & ordering    | 15%    | WF-7, WF-15, `link_steps()`                      |
| D4 | Branching & conditional logic          | 12%    | WF-8, WF-16                                      |
| D5 | Edge-case & failure handling           | 12%    | WF-9 (timeouts), WF-16, WF-17                    |
| D6 | Deliverability integrity               | 10%    | WF-12 (SMS from-#), WF-13, WF-2/10/11 deps       |
| D7 | Idempotency / re-entry safety          | 8%     | WF-6, WF-16 Stop-on-Response                     |
| D8 | Naming, labeling & testability         | 8%     | WF-1, WF-5, WF-18/21 snapshot, WF-20             |

Weights sum to 100%.

---

## D1 — Goal-fit to stated intent (20%)
**Evidence source:** PLAN Step A1 (the client's stated outcome) and Step A2 (the client's
pinned constraints / verbatim values) diffed against `caf workflows export <id>`.

- **1:** Built workflow does not produce the client's A1 outcome, OR it solves a goal the client
  never stated (invented scope).
- **5:** Achieves the literal ask but ignores an explicit A2 constraint (e.g. client pinned
  "email only," build added SMS), OR honors copy/wait values **approximately** rather than
  verbatim.
- **10:** Every A1 outcome reached AND every hyper-specific A2 value (exact copy, wait durations,
  tag names, channel, business-hours) reproduced **verbatim**; nothing the client pinned was
  silently "improved."

> **Partial mechanization (cheap to assert):** where the client pinned exact A2 values (copy,
> wait durations, tag names, channel), a verbatim string compare of those pinned values against
> the exported built workflow JSON can be machine-asserted. `qc-built-workflow.sh` emits this as
> the `D1_goalfit_pinned_values` hint when a `--pinned-values <file.json>` map is supplied;
> otherwise D1 stays `REQUIRES_HUMAN_REVIEW` for the QC sub-agent to grade.

## D2 — Trigger correctness (15%)
**Evidence source:** WF-3 (trigger present + correct type + filters), WF-4 (trigger ACTIVE
state — the WF-ACTIVE gate).

- **1:** Wrong trigger type, OR trigger active-state contradicts the publish decision so the
  workflow silently never fires (the WF-4 WF-ACTIVE failure mode).
- **5:** Correct trigger type but filters incomplete (fires on any tag-add instead of the
  specific tag), OR active-state defaulted rather than matched to the PUBLISH answer.
- **10:** Trigger type + filters exactly match the plan; `active` flag matches gating-question-1
  PUBLISH decision (`true` only if LIVE).

## D3 — Action/step completeness & ordering (15%)
**Evidence source:** WF-7 (action sequence matches outline), WF-15 (delivery chain wired
end-to-end), `link_steps()` (order/parentKey/next).

- **1:** Missing nodes, orphaned steps, or an action type outside the 56 `VERIFIED_ACTIONS`
  (build rejected/empty).
- **5:** All nodes present but order drifts from the Step C outline, OR a multi-step chain
  verified only by text-grep.
- **10:** Node set + order match the outline exactly; `link_steps` ordering confirmed (no 400
  "corrupted order"); delivery chain wired trigger→steps→exit with no orphans (WF-15 CONFIRMED).

## D4 — Branching & conditional logic (12%)
**Evidence source:** WF-8 (If/Else conditions), WF-16 (advanced settings affecting branch
behavior).

- **1:** If/Else references a field/operator that doesn't exist, OR only one branch configured
  (other path dead-ends).
- **5:** Branches configured but one path is a stub, OR AND/OR logic ambiguous vs the plan.
- **10:** Every branch has both paths defined, correct field/operator/value, each path advances
  to a deliberate outcome. **N/A clean (= 10) if the workflow has no branches.**

## D5 — Edge-case & failure handling (12%)
**Evidence source:** WF-9 (Wait timeouts), WF-16 (business-hours/time-window), WF-17 (edge cases
covered/decided).

- **1:** No WF-17 edge cases considered; Wait nodes with no timeout branch; no failed-send path;
  reply-mid-sequence ignored.
- **5:** Common cases handled (re-entry, reply) but one named edge case (empty field on trigger
  contact, wait spanning outside business hours, failed-send) left undecided.
- **10:** Every WF-17 edge case explicitly DECIDED (handled-by-branch or accepted-by-client on
  record), Wait timeouts addressed (WF-9), business-hours windows set where relevant (WF-16).

## D6 — Deliverability integrity (10%)
**Evidence source:** WF-12 (SMS From-number — the WF-SMS-FROM gate), WF-13 (email sender),
WF-2/WF-10/WF-11 (tag/field/value dependencies GET-verified), WF-18 (deps pre-existed).

- **1:** SMS node with empty From-number (silent fail — the WF-12 gate); email missing sender;
  referenced tag/field/value does not exist in GHL.
- **5:** Senders set but one dependency assumed rather than GET-verified, OR email tracking
  options at unreviewed defaults.
- **10:** Every SMS From-number non-empty, every email sender set, all tags/fields/values
  GET-verified pre-build (WF-2/10/11/18).

> **WF-12 carry-over (RESOLVED):** the engine's `sms_step` now emits an explicit `fromNumber`
> field, resolved from `CAF_SMS_FROM_NUMBER` / `GOHIGHLEVEL_SMS_FROM_NUMBER` when set, else the
> empty string is left for GHL's location-default send-time resolution. `qc-built-workflow.sh`
> WF-12 mechanically asserts every published SMS node carries the `fromNumber` **key**, and a
> D6=10 additionally requires the From-number to be **non-empty** on a LIVE/published workflow.
> See CHANGELOG entry for the `sms_step` `fromNumber` hardening.

## D7 — Idempotency / re-entry safety (8%)
**Evidence source:** WF-6 (re-entry / allow-multiple), WF-16 (Stop-on-Response).

- **1:** Contact can re-enter and get double-messaged; no Stop-on-Response; no re-entry rule
  decided.
- **5:** Re-entry rule set but Stop-on-Response missing on a reply-sensitive sequence.
- **10:** Re-entry rule matches the plan (allow/deny), Stop-on-Response set where replies should
  halt the sequence (WF-6, WF-16).

## D8 — Naming, labeling & testability (8%)
**Evidence source:** WF-1 (workflow name), WF-5 (publish state), WF-18/WF-21 (snapshot), WF-20
(no hallucinated artifacts / testability of claims).

- **1:** Workflow/step names are defaults ("Workflow 1"), no `ZHC-`/`zhc` provenance, no
  snapshot taken.
- **5:** Named but inconsistent, OR snapshot taken without a documented rollback point.
- **10:** Clear human-readable names, `ZHC-`/`zhc` provenance prefix present (carries standing
  build approval per `safety_gate`), WF-18/21 snapshot stored, WF-20 test-instructions recorded.

---

## Worked example

A purely-mechanical (no-branch) re-engagement workflow that hit every A2 value, correct trigger
matched to a DRAFT decision, ordered chain, no branches (N/A=10), all edge cases decided, SMS
From-number present, re-entry=ONCE with Stop-on-Response, ZHC-named with a snapshot:

```
D1=10, D2=10, D3=10, D4=10(N/A), D5=10, D6=10, D7=10, D8=10
weighted = (10*20+10*15+10*15+10*12+10*12+10*10+10*8+10*8)/100 = 10.0  → SHIP
```

A workflow that hit the outcome but silently added an SMS the client never asked for (D1=5) and
left one edge case undecided (D5=5):

```
D1=5, D2=10, D3=10, D4=10, D5=5, D6=10, D7=10, D8=10
weighted = (5*20+10*15+10*15+10*12+5*12+10*10+10*8+10*8)/100
         = (100+150+150+120+60+100+80+80)/100 = 8.40  → BELOW 8.5: LOOP
loop note: "Lowest dimensions: D1 Goal-fit (5/10 — added SMS not in A2) and
            D5 Edge-case handling (5/10 — failed-send path undecided). Fix both, re-grade."
```

---

## Cross-reference

- Hard gate (must all PASS): `references/workflow-build-checklist-template.md` (WF-1..WF-21).
- Mechanical assertions: `qc-built-workflow.sh` (WF-3/4/5/6/7/12/15/18/21 + the rubric score).
- Step 9 QC GATE sequence: `INSTRUCTIONS.md` Step 9 (WF-1..21 first, then this rubric, ≥ 8.5 to
  ship, below 8.5 loops naming the low dimension).
