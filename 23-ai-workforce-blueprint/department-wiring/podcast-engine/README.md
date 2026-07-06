# Podcast Production Engine: Department, Persona, and Kanban Wiring

Slice: department-persona-kanban-wiring (WAVE-PLAN W4.1, W4.2, W4.3). Binding on
PRD Sections 3.5, 3.6, and 13. This is the sibling wiring document that
webhook-design.md Section 7 defers to when it says "Exact department and persona
wiring lives in the department design." The machine-readable source of truth is
`wiring.json` in this folder; this README is its plain-language companion. The
enforcement pointer is `verify-podcast-engine-wiring.py` in this folder.

Writing rules honored here: zero em dashes, no triple-backtick code fences.

## 1. Wire in, never duplicate

The Podcast department already exists on the 28-department universal floor. It is
the `podcast` department, in the content-creator vertical pack, flagged
`universal_primary: true` in `23-ai-workforce-blueprint/department-naming-map.json`.
`department-floor.py` counts it among the six universal-primary verticals that ride
on top of the 22 mandatory departments (22 + 6 = 28).

This slice attaches the engine (skill 58) to that existing department. Per PRD
Section 3.5, creating a second podcast department is a build failure. This slice
does not edit the naming map, so the floor count is provably unchanged at 28 and
`department-floor.py` still returns rc 0 with podcast recognized as a universal
primary. Run it to confirm:

    python3 23-ai-workforce-blueprint/scripts/department-floor.py --json

## 2. Canonical skill binding

The one machine-readable source binding a skill to its owning department and
specialist roles is `23-ai-workforce-blueprint/skill-department-map.json`
(see universal-sops/native-skill-invocation.md). This slice adds the skill 58
entry there:

- skill 58, slug podcast-production-engine, client_facing true
- departments: podcast
- owning roles: director-of-podcast (primary), podcast-host, audio-post-producer,
  qc-specialist-podcast
- intent triggers: plain-language podcast production intents so the department can
  operate the engine natively, exactly as skill 38 (the webhook-driven
  conversational AI system) is modeled

The skill directory `58-podcast-production-engine/` is authored by the
core-skill-authoring slice (W1.1). The `check-skill-department-map.py` map-to-disk
coverage assertion goes green once that folder and this map entry co-land in the
serial merge train (skill directory at train step 2, this wiring at step 3). On an
isolated wiring branch, that one coverage line is the only expected miss; every
other assertion (orphan check, one primary, live role pairs, intent triggers)
already passes.

## 3. Intake sessionKey to the department agent

The inbound webhook route drives one bound session:

    sessionKey: podcast:intake:<client-slug>

That session belongs to the client's podcast department agent, which embodies the
director-of-podcast head. It is never shared with any other skill's inbound
traffic. `allowedAgentIds` is the podcast agent only and
`allowedSessionKeyPrefixes` is the podcast session namespace only. Each accepted
submission becomes one TaskFlow whose flow key is the job_key. When the route lands
its turn on this session, the correct persona picks the job up and the job appears
on the kanban through the ledger and status contract. Source: webhook-design.md
Sections 6.1 and 7.

## 4. Persona binding and pipeline ownership

Access follows the pipeline chain of custody (PRD Section 13). Four owning personas
come from role-library/podcast/ and three supporting personas come from
role-library/audio/. Exact slugs are verified against
templates/role-library/_index.json by the enforcement script.

Owning personas (podcast department):

- director-of-podcast (owner). Owns the run end to end, the kanban card, output-type
  preset selection, and the 3-strike escalation to the founder. This is the head the
  sessionKey agent embodies. Statuses received, researching, publishing
  orchestration, enrolling, complete, plus failed and queued_credit_out ownership.
- podcast-host (drafting). Voice and framing across Steps 5 to 8. This is the
  drafting persona for the QC independence rule. Status writing.
- audio-post-producer (production). Steps 10 and 11: art finalization, Fish Audio
  render, seamless stitch, and loudness mastering to minus 14 to minus 16 LUFS
  integrated, plus media QC on upload. Statuses generating_art, producing_audio,
  publishing. Media QC here is production QC, not the episode QC gate.
- qc-specialist-podcast (qc). Step 9, the episode QC gate. Status in_qc. Bound by
  the independence rule in Section 5.

Supporting personas (audio department, same universal floor, supporting capacity,
not owners):

- podcast-editor supports audio-post-producer at Step 11 on repair passes.
- audio-mastering-specialist is the mastering role named in PRD Section 3.6; it
  supports audio-post-producer at Step 11 on loudness mastering.
- podcast-producer supports director-of-podcast on the Season-Strategy output-type
  preset (a planning deliverable that runs research and document QC and skips
  Steps 6 to 17).

These three cross-department supporters live in `wiring.json` rather than the map's
owning-roles list because the map records owning specialists, and audio roles
support rather than own. This keeps the orphan check clean (all map roles are
podcast-department roles) while still recording the full persona picture.

### 4.1 The full access matrix (PRD Section 13)

Access is default-deny. A department gets access only if it executes a pipeline step
or consumes a published deliverable; everything else is denied because every extra
consumer is attack surface, token burn, and QC ambiguity. The complete decision lives
in `wiring.json` under `access_matrix` and is enforced by
`verify-podcast-engine-wiring.py`:

- Owner (write): the podcast department, embodying director-of-podcast, podcast-host,
  audio-post-producer, and qc-specialist-podcast.
- Supporting (write, at an owner's invitation): the audio department, through
  podcast-editor, podcast-producer, and audio-mastering-specialist.
- Routing only (no write, no steps): the master agent dispatches an inbound podcast job
  to the podcast department per the master routing doctrine and never runs a pipeline
  step. The dispatch rule itself is WAVE-PLAN W4.14; this wiring only declares the
  access so the decision is single-sourced.
- Read only, downstream (no write): social-media reads completed episode records and
  published links to feed Skill 57 social packaging (the Episode Asset Pack preset is
  the sanctioned handoff); marketing reads published links and the Episode Package for
  promotion planning. Neither can touch the pipeline or its state.
- No access (everything else): sales, billing-finance, legal, personal-assistant,
  customer-support, and every other floor department. Customer messaging belongs to
  Convert and Flow workflows, so not even the personal-assistant department may message
  about episodes. Client-side humans interact only through the dashboard and Convert and
  Flow, never with the engine directly.

The enforcement script fails if any no-access department is also granted access, if a
non-owner tier claims write access, or if routing-only claims to execute steps.

## 5. QC independence rule

qc-specialist-podcast is never the persona that drafted the episode. The drafting
persona is podcast-host; the QC persona is qc-specialist-podcast; the two sets are
disjoint. In addition, the judge model tier that scores QC is distinct from the
writer model tier, so the writer never grades its own work as the deciding vote.
`verify-podcast-engine-wiring.py` asserts the disjointness and the is_drafting and
is_qc flags. At runtime the two-tier episode gate and qc-attempt-gate.py enforce it.
Source: PRD Section 13.1 and QC-PROTOCOL-AND-MATRIX.md Gate B.

Note on the two gates, never conflated: this wiring concerns Gate B, the EPISODE
gate (16 Tier 1 hard-fail checks, then the 10-dimension rubric at 8 or higher per
dimension, then the 3-strike cap). It is separate from Gate A, the 8.5 ten-category
BUILD gate that decides whether this wiring merges.

## 6. Kanban mapping

The kanban board is display-only. No drag-and-drop and no pipeline mutation from the
dashboard (dashboard-design.md Section 7.1). Columns render the status written by the
single writer podcast_state.py; they never recompute state. The status enum is the
one declared in dashboard-design.md Section 5, and it is the same vocabulary as the
intake ledger (webhook-design.md Section 3). One state system, two layers: the file
ledger is the webhook layer atomic claim, and podcast-engine.db is the queryable
source for dashboard and kanban.

Forward board, nine columns (also the nine-segment progress meter):

1. received, client label Received, Steps 0 to 1, owner director-of-podcast
2. researching, client label Researching, Step 3, owner director-of-podcast
3. writing, client label Writing, Steps 2 and 4 to 8, owner podcast-host
4. in_qc, client label Quality review, Step 9, owner qc-specialist-podcast
5. generating_art, client label Creating artwork, Step 10, owner audio-post-producer
6. producing_audio, client label Producing audio, Step 11, owner audio-post-producer
7. publishing, client label Publishing, Steps 12 to 16, owner audio-post-producer
8. enrolling, client label Finalizing, Step 17, owner director-of-podcast
9. complete, client label Live, Step 18, owner director-of-podcast

Off-board columns:

- queued_credit_out, client label On hold. queue_state held; resumes at resume_stage.
- failed, client label Needs attention. Three-strike stop or unrecoverable failure;
  founder already alerted through alert-dedup.py.

Overlay:

- aged_out is a queue_state, not a status. It renders as an Expired badge on the
  Needs attention column when the 60-day credit-out cap drops the job.

The kanban never defines transitions. The legal-transition matrix is authoritative in
dashboard-design.md Section 5.2 and enforced by podcast_state.py.

## 7. Proof

- Build-gate proof for this slice: `department-floor.py` returns rc 0 with podcast
  present and the floor count unchanged at 28; `verify-podcast-engine-wiring.py`
  returns rc 0; `check-skill-department-map.py` returns only the expected skill 58
  coverage line until the skill directory co-lands.
- Card-lifecycle proof: see `card-lifecycle-proof-plan.md`. The end-to-end observed
  card move is exercised on the operator box in WAVE-PLAN W5.4.
