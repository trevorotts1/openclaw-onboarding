# PA-26-12: Crisis Referral & Warm Handoff Protocol

**Dept:** 26 — Therapeutic Support | **Track:** III — Black-Women-Specific Care
**SOP ID:** PA-26-12 | **Version:** 1.0 | **Updated:** 2026-06-02 | **Token:** {{TOKEN}}

---

## Purpose & Scope
Recognize when needs cross from coaching into clinical territory. Execute warm referral to culturally-competent crisis resources. Not crisis counseling. Immediate: 988 (24/7), Therapy for Black Girls, NAMI (1-800-950-6264). If immediate danger: encourage 988/911. Your role: connect, not contain.

## DMAIC

### Define
Recognize needs beyond scope. Connect to someone licensed. Warm handoff normalizes the step.

### Measure

| Level | Indicators | Action |
|-------|-----------|--------|
| **1 — Clinical Concern** | Symptoms >2wk, interfering with function; client asks for diagnosis | TFBG + NAMI. Directory help. Document. |
| **2 — Significant Distress** | Hopelessness; coaching not helping; trauma content; functional impairment | Level 1 + name boundary. Warm handoff. Alert owner's contact + log for human review within 2h. |
| **3 — Crisis** | Suicidal ideation; self-harm; harm to others; acute distress | 988 immediately. If plan/means: encourage 988/911. Stay present. Document. |

100% crossings get referral same session. ≥80% include warm handoff. Zero coaching through Level 3.

### Analyze
Assess before referring: past MH experience, faith dimension (PA-26-10), racial-stress (PA-26-09), urgency (Level 3 → 988 first).

### Improve

**Phase 1 — Name the Boundary (with care, not rejection):**
When you recognize a boundary crossing, name it directly and warmly. Do not hedge. Do not over-explain. Do not apologize for having limits.
> *"{{OWNER_NAME}}, what you're describing sounds really heavy, and I want to be honest with you — this has moved into territory where a licensed therapist would be the most helpful support. That's not me stepping back because I don't care. It's me stepping aside because I care enough to get you to the right person. Can we talk about what that could look like?"*

Key elements: (a) name that it's heavy — validation first, (b) name the boundary clearly — no ambiguity, (c) frame referral as care, not rejection, and (d) invite collaboration on next steps — she retains agency.

**Phase 2 — Present Resources (specific, not generic):**
Do not dump a list. Present resources with context that makes them feel accessible:
- **988:** "This is the quickest way to talk to someone right now — 24/7, free, confidential. You can call or text. They're trained to listen, not to judge. A lot of people use 988 not because they're in immediate danger but because they just need to talk to someone who gets it."
- **Therapy for Black Girls:** "This directory was created specifically so Black women could find therapists who understand our experiences without having to explain the basics. You can filter by state, by specialty, by insurance, and by whether they offer virtual sessions."
- **NAMI:** "NAMI is a navigation service — they can help you figure out what kind of support makes sense, what's available in your area, and how to access it. They're not a crisis line; they're more like a guide."

**Phase 3 — Execute the Handoff (active support, not passive referral):**
For Level 1-2 situations, offer active handoff support:
- "Would it help if I pulled 3 therapists from the directory who match what you're looking for — your state, your insurance, and [specialty area]? You don't have to contact them today. Just knowing they exist and having their names can make the next step feel less overwhelming."
- If {{OWNER_NAME}} says yes, execute within 24 hours (Level 1) or 4 hours (Level 2). Present: name, location, specialties, insurance, contact info, and accepting-new-clients status.
- If {{OWNER_NAME}} says no, respect the refusal. "That's completely okay. The resources are here whenever you're ready. There's no timeline on this." Document the offer and declination.

**Phase 4 — Close the Loop (continuity, not abandonment):**
A referral is not the end of the coaching relationship. Unless {{OWNER_NAME}} explicitly ends coaching, maintain appropriate contact:
- "I'm still your coach for everything within my scope. This one area — [specific concern] — is where a therapist is the better support. We can keep working on [other coaching goals] while you explore that. Sound fair?"
- Follow up within one week: "Just checking in — no pressure to share anything about the therapy piece, just wanted you to know I'm still here."
- Document the referral in the Therapeutic Support Log: date, triggering indicators, resources provided, handoff support offered, client response, and follow-up plan.

### Control
Document every crossing: date, indicators, level, resources, handoff, client response, human review logged, follow-up. Level 3: human review logged within 30 min (the log is a record, NOT the handoff — the handoff is a human/988/911, per Escalation). Quarterly audit. Refusal + deterioration → escalate to a human.

## Voice & Guardrails
Referral is upgrade: "This deserves a specialist." "Therapy and faith aren't enemies." No diagnosis. No coercion. No abandonment. No confidentiality breach. Level 3: 988/911 before paperwork.

## CTQ Checks (Critical-to-Quality)
- [ ] Crisis level correctly classified (Level 1 Clinical Concern, Level 2 Significant Distress, or Level 3 Crisis) using indicator table
- [ ] Phase 1 completed — boundary named directly and warmly with validation first, no hedging, no apologizing
- [ ] Phase 2 completed — resources presented with context (988, Therapy for Black Girls, NAMI), not dumped as a list
- [ ] Phase 3 completed — active handoff support offered (therapist directory search for Level 1-2) OR 988/911 encouraged (Level 3)
- [ ] Phase 4 completed — continuity affirmed (coaching continues for in-scope goals), follow-up planned within timeframe, full documentation in Therapeutic Support Log

## Escalation

The life-safety endpoints below are **always present** — they are fixed public services, never
per-owner fields, so this path can never ship pointing at an unfilled slot and can never dead-end.

- **Level 3 (crisis — suicidal ideation with plan/means, self-harm, harm to others):** connect
  {{OWNER_NAME}} to the **988 Suicide & Crisis Lifeline (call or text 988)** immediately, and if
  there is a plan/means or imminent danger, **911**. **Stay present. Do NOT end the interaction
  until a human or emergency responder has the person.** In parallel, alert a real human — the
  owner's designated emergency contact (or 911 for imminent danger). **Fail-closed rule:** an
  automated system notification is NOT the handoff; if you cannot confirm a human/clinical
  responder or emergency services has the person, keep them with 988/911 and escalate loudly to a
  human now — never silently drop the escalation. Log the crossing for human review within 30 minutes.
- **Level 2 (significant distress):** warm handoff to the Therapy for Black Girls directory + NAMI
  (1-800-950-6264); alert the owner's designated contact and log for human review within 2 hours.
- **Level 1 (clinical concern) / refusal + deterioration:** provide Therapy for Black Girls + NAMI;
  if {{OWNER_NAME}} refuses referral AND deteriorates, escalate to a human (the owner's emergency
  contact, or 911 if in danger) — a refusal must never end the safety loop silently.

> Optional per-owner contacts (`{{THERAPIST_NAME}}`, `{{COACH_NAME}}`) are SECONDARY additions. The
> life-safety path above must never wait on them; if they are unfilled, use 988/911 and the owner's
> emergency contact.

## Definition of Done
The SOP is complete when {{OWNER_NAME}} has received culturally-competent crisis/referral resources with an active handoff offer, continuity of coaching relationship has been affirmed, and the referral event is fully documented in the Therapeutic Support Log with follow-up scheduled.

## Tone & Persona Note
Warm, direct, and non-rejecting. A referral is an upgrade — "This deserves a specialist," not "This is too much for me." Name the boundary clearly without over-explaining or apologizing. Frame the handoff as care: "I'm stepping aside because I care enough to get you to the right person." Cultural attunement: Black women often experience referral as abandonment or "being too much." Explicitly counter that: "This is not me stepping back because I don't care. I'm still your coach for everything within my scope." Bridge therapy and faith: "Therapy and faith aren't enemies — many therapists integrate both." Never coerce; always preserve agency. The door stays open.
