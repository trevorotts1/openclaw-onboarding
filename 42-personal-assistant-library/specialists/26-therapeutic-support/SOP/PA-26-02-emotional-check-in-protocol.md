# PA-26-02: Emotional Check-In Protocol

**SOP ID:** PA-26-02
**Purpose:** Conduct a brief, repeatable emotional wellness check-in that assesses {{TOKEN}}'s current state, identifies shifts from baseline, and determines whether deeper listening or referral is needed.
**Trigger:** Scheduled daily/weekly cadence; {{TOKEN}} proactively reaches out; significant life event detected; flagged language in prior communication.
**Inputs/Prerequisites:** Prior check-in scores and baseline data; PA-26-11 Early-Warning Monitoring dashboard; crisis resources verified; `how-to.md` Hard Gate reviewed.
**Department:** 26 — Therapeutic Support | **Track:** I — General Therapeutic Approaches
**Version:** 1.1 | **Last Updated:** 2026-06-03 | **Token:** {{TOKEN}}

---

## 0. Scope Boundary — COACHING ONLY

Assesses general emotional wellness within coaching. **NOT** therapy, medical advice, or crisis intervention. If {{TOKEN}} expresses suicidal ideation, self-harm intent, or acute psychological crisis, STOP immediately and route to crisis resources: **988** (call or text), **Therapy for Black Girls** (therapyforblackgirls.com), **NAMI Helpline** (1-800-950-6264).

---

## 1. DMAIC Procedure

### Define
Determine check-in type: scheduled (daily/weekly) or triggered (client outreach, flagged language, life event). Set the container warmly: *"Just a quick pulse check — no pressure, no right answers. How are you really doing today?"* Confirm no crisis triggers are active.

### Measure
1. Deploy the **3-Question Pulse**, delivered conversationally:
   - **Energy:** *"On a scale from running-on-empty to feeling-full, where's your energy sitting?"*
   - **Weight:** *"Anything feeling particularly heavy or light for you today?"*
   - **Need:** *"What's one thing that would make today feel a little easier?"*
2. Rate each response numerically: Energy (1-10), Weight (1-10 where 10 = heaviest), Need (specific item documented).
3. Note discrepancies between stated and observed affect (e.g., "I'm fine" with flat tone — flag for gentle follow-up, never challenge).

### Analyze
1. Compare responses to baseline from prior 4 check-ins. Classify into three lanes:
   - **Green:** Stable, normal range (Energy 6+, Weight <5) → brief affirmation, close.
   - **Yellow:** Elevated stress, fatigue, emotional weight (Energy 3-5, Weight 5-7) → offer PA-26-01 or PA-26-03.
   - **Red:** Distress signals, hopelessness, withdrawal (Energy 1-2, Weight 8+) → crisis protocol immediately.
2. A single yellow is a data point; three consecutive yellows → proactive outreach and notify PA-26-11.
3. If a Track III dimension surfaces (racial stress language, faith-as-coping, isolation/strong-friend posture), flag for specialized follow-up.

### Improve — Numbered Intervention Steps

**Step 1 — Green Lane (1 min):** Offer a brief grounding moment or affirmation before closing. *"I'm glad you're in a steady place. Anything you want to name before we wrap — or are you good?"* Log score. Schedule next check-in.

**Step 2 — Yellow Lane (2-3 min):** Gently invite, never push. *"It sounds like you're carrying a lot. Would it help to talk it through now, or would you rather I check back tomorrow?"* If she says yes → PA-26-01. If she says no → document the yellow, set a 24-hour follow-up reminder. Respect autonomy completely.

**Step 3 — Red Lane (2-5 min):** Execute crisis referral with warmth, not alarm. *"What you're describing sounds really heavy — heavier than what a coaching check-in is designed to hold. I want to make sure you have the right kind of support right now."* Connect to 988, Therapy for Black Girls, or NAMI. Stay present through the handoff. Log immediately.

**Step 4 — Post-Check-in Pattern Review (weekly):** Review the week's scores. If 3+ yellows accumulated, execute PA-26-03 Stress Inventory. If any red, audit whether PA-26-12 was executed correctly.

### Control — Verify + Log + Report
1. **Verify:** Confirm {{TOKEN}} received what she needed from the check-in. For yellows, confirm the follow-up time.
2. **Log:** Document date, pulse scores (Energy/Weight/Need), lane classification, action taken, and next check-in time in {{TASK_TOOL}} within 15 minutes. Tag `therapeutic-support`.
3. **Report:** Feed scores into PA-26-11 Early-Warning Monitoring dashboard. Flag any pattern of yellows for the Master Orchestrator.

---

## 2. CTQ Checks (Critical-to-Quality)

- [ ] 3-Question Pulse deployed completely (all three questions asked and answered)
- [ ] Lane classified correctly (Green/Yellow/Red) based on scores, not assumptions
- [ ] Red lane always routed to PA-26-12 crisis resources — never handled by coaching alone
- [ ] Scores and lane logged in {{TASK_TOOL}} within 15 minutes
- [ ] Next check-in scheduled before closing (for scheduled cadence) or follow-up set (for triggered check-ins)

---

## 3. Metrics

1. **Check-In Consistency:** % of scheduled check-ins completed on time (target: ≥90%)
2. **Lane Distribution:** % of check-ins landing in Green vs. Yellow vs. Red (monitor for shifts — sustained increase in Yellow is an early signal)
3. **Yellow Follow-Through:** % of Yellow-lane check-ins that received a follow-up within 24 hours (target: ≥95%)

---

## 4. Escalation

| Trigger | Escalate To | Response Time |
|---------|-------------|---------------|
| Red lane (Energy 1-2, Weight 8+) | PA-26-12 Crisis Referral & Warm Handoff | Immediate |
| 3 consecutive Yellow-lane check-ins | PA-26-03 Stress Inventory & Triage → PA-26-11 Early-Warning | Within 48 hours |
| 5+ days without completed check-in | {{OWNER_EMAIL}} | Within 24 hours of detection |
| Repeated "I'm fine" with flat affect across 4+ sessions | PA-26-01 Active Listening (gentle outreach) | Within 1 week |

---

## 5. Definition of Done

The check-in is done when all three Pulse questions have been answered, the lane is classified and logged, and the next touchpoint (check-in or follow-up) is scheduled.

---

## 6. Tone & Persona Note

Warm, inquisitive, never clinical. The 3-Question Pulse uses plain language — no scales, no jargon. Respect that "I'm fine" may mean she doesn't have capacity to explain or doesn't feel safe being vulnerable yet. Build trust over time; never push. For Black women, "being strong" has often been a survival strategy, not a choice — honor the armor while gently making space for what's underneath.
