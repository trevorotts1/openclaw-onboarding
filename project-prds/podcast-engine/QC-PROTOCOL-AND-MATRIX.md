# QC PROTOCOL AND MATRIX, PODCAST PRODUCTION ENGINE
### The two gates, spelled out separately, plus the stage-by-stage check matrix
### Version 1.0, Fable, 2026-07-06. Zero em dashes. No triple backtick fences in produced outputs.

THE CARDINAL RULE: there are TWO quality control gates in this project and they are never conflated, never substituted, and never averaged into each other. One decides whether BUILD WORK merges. The other decides whether an EPISODE ships. A build unit scoring 9.0 says nothing about an episode, and a perfect episode says nothing about merge readiness.

---

## GATE A: THE BUILD/MERGE GATE (fleet standard, binding on /goal execution)

- Instrument: the fleet 10-category QC rubric (the binding OpenClaw QC protocol).
- Threshold: 8.5. Below 8.5 the executing agent fixes the work itself and re-runs the gate; at or above 8.5 the work pushes and merges. The rubric decides quality; nobody asks the founder for a green light the rubric already grants.
- Scope: every merged unit of the build (skill runbook, each script, the dashboard, each SOP, the wiring, the docs).
- Additional mechanical merge gates that ride with Gate A: guard-no-anthropic-runtime.py (zero Anthropic in shipped runtime), guard-cron-inventory.py (recurring-job audit), the content-hash gate (_index.json content_sha restamped), the G1 tag gate (annotated tag exists BEFORE merge), the fleet-wide repo grep (no client identifiers), and the update.sh skill-count check.
- Loop: fix, re-run, merge; failed or rate-limited agents re-dispatch with state passed forward. The gate is self-administered and logged per unit in SESSION-LOG.md.

## GATE B: THE EPISODE GATE (companion document, binding at runtime, shipped inside the skill)

- Instrument 1, Tier 1: 16 hard-fail binary checks (full text in CHECKLIST.md Part B). Any single failure means the episode is NOT deliverable. Checks 1 to 11, 15, 16 are deterministic string and count work executed by qc-tier1-mechanical.py at zero model cost. Checks 12 (fabrication), 13 (mode perspective), and 14 (pronoun correctness) are semantic and run on the cheap judge tier (Gemini 3.1 Flash Lite or GLM 5.2), never on the writer model.
- Instrument 2, Tier 2: the 10-dimension quality rubric, minimum 8 on EVERY dimension, no averaging, scored only after Tier 1 fully passes.
- Instrument 3: the per-episode checklist (CHECKLIST.md Part A), honestly completed and reproduced in the delivery report.
- Independence: the QC persona is qc-specialist-podcast and must not be the persona that drafted; the judge model tier is distinct from the writer tier. The writer never grades its own work as the deciding vote.
- Read protocol: three passes with different jobs (A mechanics and forbidden content, B structure and fidelity, C full read-aloud at speaking pace). No pass skipped because the episode feels done.
- Failure loop: targeted revision (only failing sections and dimensions; the frozen research package is reused; a full rewrite is allowed only on attempt 2 when more than 4 rubric dimensions failed). qc-attempt-gate.py owns the counter. Hard stop at three failed attempts: stop, notify the founder through alert-dedup with the failing checks and the best draft. Standards are never relaxed to resolve a three-strike failure.
- Cost bounds: all attempts share one 400,000-token episode budget; a fabrication failure unlocks at most one supplemental research pass of 4 calls.

---

## THE MATRIX: EVERY PIPELINE STAGE AND BUILD DELIVERABLE MAPPED TO ITS CHECKS

### Runtime matrix (per episode)

| Stage / deliverable | Checks applied | Proving instrument |
|---|---|---|
| Webhook delivery | Auth (route secret), body cap, method | OpenClaw platform plus WAF rule |
| Intake mapping | Alias and fuzzy mapping, value-shape validation, required-field gate, tenant location_id equality | Deterministic mapper plus fixture unit tests |
| Dedup and claim | Job-key collision on redelivery, divergence on changed answers, exclusive-create claim | Ledger module tests; T5 and T6 verification |
| Step 0 smoke test | Credential resolution all aliases all stores, PIT prefix and pairing proof, fingerprint anti-commingling, required custom fields exact keys, rate floor | ghl_credential_gate.py exit codes 0/2/3/4/5 |
| Research package | Real and verified sources only, demographic match, 12-call cap, package frozen | Cost ledger precheck; Tier 1 check 12 downstream |
| Blueprint | Title rules, thesis traceability, budgets sum to total, immutable title | Blueprint self-check; Tier 1 checks 5 and 9 downstream |
| Draft and improvement | Final Draft format, tag syntax and density, tone enforcement, no inflation | Tier 1 checks 1 to 8, 15, 16 |
| QC stage | All 16 Tier 1 plus 10-dimension rubric plus checklist | qc-tier1-mechanical.py, judge tier, qc-attempt-gate.py |
| Cover art | Square, 1400 to 3000 range, JPEG RGB, under 512 kilobytes, filename rule, poll bounds | ffmpeg and ffprobe assertions; polling config |
| Audio | s2.1-pro header, client reference_id, no free tier, seamless joins, loudness doctrine, honest duration | Render module assertions plus ffprobe |
| Documents | Rendered rich formatting (Package), clean text only (Script), sharing set, font floors | Document module checks; delivery report |
| Book teaser | Interview mode only, 3-page cap, 14-point floor, fabrication boundary, cliffhanger present | Teaser module checks; Tier 1 check 12 |
| Media storage | Folder reuse not recreation, upload success, public HEAD 200 with matching content type | Upload module; reachability probe |
| Podbean publish | Own credentials, episode numbering, idempotent permalink guard, schedule vs publish | Publish module; ledger permalink check |
| Link-back | Exact field keys, batch first, URL alone and last, byte-for-byte read-back | Field writer plus read-back verification |
| Enrollment | Publish-and-writes precondition, discovered trigger honored, double-enrollment guard, Personal-mode hard refusal, boundary stop | Enrollment module; caf verification reads |
| Delivery | Report completeness, checklist reproduced, operator channel only | Delivery module; silence audit |
| Every stage | State transition legality, cost metering, ceiling enforcement, alert dedup | podcast_state.py, podcast-cost-ledger.py, alert-dedup.py |
| Daily (per client) | Funded reachability of all paid services at or under 1 cent, queue age check, 60-day age-out | podcast-smoke-test.py self-metered |

### Build matrix (per /goal deliverable)

| Build deliverable | Gate A rubric | Additional mechanical gates |
|---|---|---|
| Skill runbook and prompts | 8.5 | Episode gate exercised on golden fixture; em dash and fence scan |
| Webhook layer code | 8.5 | Fixture unit tests green; T1 to T9 executed on canary |
| Convert and Flow layer code | 8.5 | Gate script live pass; shared-resolver restamp; MCP-free static check |
| Guardrail script suite | 8.5 | Each script's own failure modes forced and observed |
| Dashboard | 8.5 | The fourteen dashboard acceptance criteria; read-only proof; serializer matrix proof |
| Cloudflare scripts | 8.5 | Provision gate and revocation verification on canary; zone-name refusal check |
| Department, persona, kanban wiring | 8.5 | department-floor.py pass; kanban card observed moving; persona binding proof |
| SOP set and doc updates | 8.5 | Enforcement pointer present in each SOP; cross-references resolve |
| Repo mechanics | n/a (mechanical) | update.sh count, content_sha restamp, v18.0.0 annotated tag before merge, fresh-clone verify, fleet-wide grep |
| Whole build | n/a | CHECKLIST.md Part C, all 18 items, independently verified on the canary |
