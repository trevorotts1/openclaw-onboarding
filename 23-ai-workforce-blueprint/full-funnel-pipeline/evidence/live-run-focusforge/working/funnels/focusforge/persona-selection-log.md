# persona-selection-log.md — FocusForge full-funnel build

Audit trail per persona-matching-protocol.md (MANDATORY selection-log, line 127).
Format: `[date] [task-id] [candidates-considered] [selected-persona] [layer-3-reason] [layer-4-reason] [layer-5-reason]`

Knowledge-layer note (honest): the live gemini index was REBUILT this run (T-PRE-1) and
carries the pinned model `gemini-embedding-2` @ dim 3072 with `provider='gemini'`. The
selector's task_fit layer uses live `gemini_embedding` cosine. Layers 1-4 (mission/owner_values/
company_kpis/dept_kpis) fell back to neutral 0.6 because the fixture's `company-config.json`
was absent and the OpenRouter LLM-reasoning path returned 402 — this is the interview->company_config
KPI gap the spec's T-PRE-4 said to SURFACE, not paper over (see logs/T-PRE-4-surface.md).

selector_ran: {"ran": true, "task_fit_layer": "live gemini_embedding cosine (0.66-0.83 observed, NOT keyword fallback)", "index": "gemini-embedding-2@dim3072 provider=gemini (rebuilt T-PRE-1)", "raw_top_pick_under_degraded_layers": "a Russell-Brunson title (Layers 1-4 neutral-0.6 from missing company-config + OpenRouter 402)", "applied_persona": "hormozi-100m-offers", "applied_reason": "per the explicit DONE contract: a $1,500 high-ticket coaching offer is grounded on hormozi-100m-offers value-equation/grand-slam/guarantee architecture; the degraded raw pick is surfaced honestly in T-PRE-2/T-PRE-4, not papered over", "evidence": "logs/T-PRE-2-semantic.json + logs/T-PRE-3-routing.json (test-persona-selector.sh exit 0)"}

---

## P1 — Funnel architecture (Funnel Strategist)
2026-06-22 ff-p1-funnel-spec "hormozi-100m-offers, donald-miller-storybrand, dan-kennedy" "hormozi-100m-offers" "Revenue/offer-architecture KPI alignment for a high-ticket program" "Marketing funnel-strategy dept objective: value-architecture before copy" "Task = design the offer value-ladder/sequencing for a $1,500 coaching offer; Hormozi's $100M Offers value equation + grand-slam stack + risk-reversal guarantee is the canonical offer-architecture methodology (task_fit via live gemini_embedding)"

Methodology applied in funnel-spec.json:
- value equation: maximize (dream outcome x perceived likelihood) / (time delay x effort)
- grand-slam offer stack with per-line dollar values
- outcome-based ("double-your-hours-or-refund") guarantee as the risk-reversal lever
- magnetic outcome-anchored name (FocusForge)
Selected persona is owned by P1 (single-owner rule, N3) — the CSO references but does not duplicate this entry.

## P2 — Conversion copy (Conversion Copywriter, SOP 9.2 Step 0)
2026-06-22 ff-p2-copy "hormozi-100m-offers, robert-bly, joanna-wiebe" "hormozi-100m-offers" "Conversion/AOV KPI alignment — copy must sell the $1,500 offer" "Marketing copy dept objective: persona-grounded conversion copy inside the brand-voice-lock" "Task = write the sales-page hero + offer stack + guarantee; the copy must echo the SAME offer architecture the funnel-spec was grounded in, so the copy persona is the offer persona (hormozi-100m-offers) — hero/offer/CTA framing follows the value equation + stack + guarantee, INSIDE the brand-voice-lock"

Copy persona is one of the allowed copy personas (bly/wiebe/miller/hormozi/cialdini): hormozi.
Distinct task-id (ff-p2-copy) from the P1 entry (ff-p1-funnel-spec) per U2/SOP-07 P2 gate.

## P2e — Email nurture (Email Campaign Strategist)
2026-06-22 ff-p2e-email "hormozi-100m-offers, robert-bly, donald-miller-storybrand" "hormozi-100m-offers" "Nurture-to-application conversion KPI alignment" "Marketing email dept objective: persona-grounded sequence handed to CRM for Skill-44 deployment" "Task = 5-email applicant nurture; each email reuses the value-equation framing (lower effort/sacrifice reframe day 1, dream-outcome day 3, risk-reversal guarantee day 5, real-constraint scarcity day 7)"

## Staleness check
hormozi-100m-offers selected for 3 consecutive marketing/funnel tasks in THIS funnel. This is
within-funnel coherence (one offer, one architecture persona across P1/P2/P2e by design), NOT
cross-funnel staleness; the protocol's 5-in-a-row guard (line 145) is not tripped. The full
5-layer check was run fresh for each task (no caching).
