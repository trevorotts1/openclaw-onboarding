# EMAIL-SEQUENCE-BUILDER-SOP -- Skill 50 email sequences as an election-gated delivery option

Cluster: Presentations -- optional delivery branches (upsells)
Status: LIVE in code on the Item 33c branch (intake election + delivery preparation
module + tests); manifest phase registration specified in section 3, sequenced
post-merge with the manifest lockstep (see STATUS, section 8).
Phase id: P-U-EMAIL-PREP (order 9.1; registration pending, section 3)
Owning role: media-librarian-ghl-updater (delivery roles; same owner as the
P-U-SALES-BUILD / P-U-VSL-BUILD branches)
Executor: `python3 scripts/email_followup.py --run-dir {run_dir}` (stdlib only;
no network, no provider spend, no canonical-entry nonce required)
Push mechanism: NONE. This branch never sends and never arms. The prepared
draft package is handed to Skill 44's operator surface for HUMAN approval;
Skill 50 runs only after that approval, and its deploy stays DRAFT-ONLY.

Fix-plan source: FIX-PLAN.md Item 33c (B13 ecosystem re-survey, Candidate 3).
Doctrine twin: `50-email-engine/SKILL.md`, section "Presentations department
integration (election-gated delivery option)". Both texts state the election
gate, the draft-only posture, and the human approval step identically.

---

## 0. THE DELIVERABLE

When a client elects the option, the delivery phase PREPARES a draft package
for Skill 50 (the Email Engine) and hands it to Skill 44's operator surface:

    working/email/email-brief.json        the DRAFT brief package (one entry
                                          per sequence: definition, audience,
                                          trigger, brief answers)
    working/email/skill44-handoff.json    the Skill 44 operator handoff
                                          record (approval step + record-back)
    working/checkpoints/email.json        the RUN RECORD for this branch,
                                          written on EVERY outcome

The one election covers TWO Skill 50 sequences:

| Sequence | Skill 50 shape | Serves | Prepared when |
|---|---|---|---|
| landing-page-10-promo | 10-email promo sequence (objective: promotional) | the elected sales/checkout page launch | the run also elected the sales/checkout page (`WANT_SALES_CHECKOUT` == "yes") |
| high-ticket-appointment | 12-email appointment sequence (buyer_type "all") | post-delivery follow-up to the deck's call to action | every elected run |

The draft package is an OPERATOR handoff, not a client-package file: it is
never part of the AF-DH1 seven-file client package and never added to
delivery_gate.py's whitelist. It also adds no department deliverable and no
registered phase in this change, so DEPARTMENT-COUNTS-CANONICAL.md's counts
are unchanged by it (its "15" tier counts the upsell PAGES in
upsell-questions.json, which this election is not).

## 1. THE WAIVER MECHANIC (the election is a waiver-gated branch)

Quoted discipline, identical in intake/upsell-questions.json and
intake/deck-intake-questions.json (waiver_field_mapping.email_sequences):

* `want_email_sequences` (upsell order 7.9; standard-bank alias row 20.03;
  captured in the merged growth_assets turn): kind text, allowed yes/no,
  value_labels, required, block_gate. DEFAULT "no" everywhere: the option is
  opt-in, and silence is NOT consent.
* `email_sequences_declined_reason` (upsell order 7.91; standard-bank alias
  row 22.07; captured in the merged decline_context turn): asked ONLY when
  the toggle is "no" (conditional_on equals "no"), required, block_gate,
  stored VERBATIM as the waiver's client_request_quote. No default, no
  assistant-authored fallback; an empty answer is re-asked and --complete
  cannot pass while a triggered follow-up is unanswered.
* Engine carriage: the pair stores canonically under
  pre_presentation_capture.WANT_EMAIL_SEQUENCES /
  pre_presentation_capture.EMAIL_SEQUENCES_DECLINED_REASON (the PRES-006
  contract, schema/intake_fields.js orders 11.2 / 11.3), rides the hosted
  curated payload in lockstep (payload/build_questions_payload.py), the
  writer mirror (bridge/intake_writer.py: PRE_CAPTURE_FIELDS carries BOTH
  fields from the start, so this branch never has the sales/VSL known gap),
  the manifest defer resolver (presentation_job/defers.py _WANT_KEYS,
  waiver_rule "email_sequences", default "no"), and the intake resolver
  (presentation_job/resolve_intake.py _UPSELL_FIELDS).

## 2. THE DELIVERY GATE

scripts/email_followup.py resolve_email_gate(intake) mirrors the sales/VSL
builder gates exactly (nested pre_presentation_capture first, flat top level
as fallback, dict values unwrapped):

| WANT_EMAIL_SEQUENCES | Outcome | Exit |
|---|---|---|
| absent / blank | DEFER: nothing prepared; the run record says the election was never answered. Never treated as a decline, never as an election. | 0 |
| "yes" | PREPARE (section 3) | 0 |
| "no" + verbatim reason (>= 3 chars) | WAIVED: nothing prepared; the run record carries the waiver {rule: "email_sequences", client_request_quote: the client's exact words} | 0 |
| "no" without a reason / blank reason | FAIL CLOSED, AF-EMAIL-WAIVER-MISSING | 3 |
| any other value | FAIL CLOSED, AF-EMAIL-VALUE-UNRECOGNIZED | 3 |

## 3. THE DRAFT PACKAGE (what "prepare" writes, and what it never writes)

Per prepared sequence, email-brief.json carries: the sequence definition
(Skill 50 sequence_position, email_count 10 or 12, objective), the audience
(deck_brief.AUDIENCE, with its source field named), the trigger, the
approval block (status AWAITING_HUMAN_APPROVAL), and brief answers sourced
ONLY from the run record (offer = deck_brief.OFFER_NAME, brand_voice =
deck_brief.TONE, founder_name = the record's client name, delivered page and
deck links read from the run's own receipts only).

Honesty rules baked into the module:

* Brief answers the record cannot supply are null and named in
  missing_inputs as approval-time inputs. Nothing is invented.
* The package is NOT Skill 50's locked brief. Skill 50's brief contract
  (50-email-engine/schema/brief.schema.json) requires its one-block intake
  attestation (asked_all_at_once + question_block_msg_id); that attestation
  is captured by Skill 50's own intake at approval time and is NEVER
  fabricated by this department.
* The promo sequence is recorded not_applicable (with the reason) when no
  page launch was elected; the appointment sequence still prepares.

SKILL 50 UNAVAILABLE: if no 50-email-engine install is found on the box, an
elected run prepares NOTHING and the run record carries the fallback: the
election was answered, Skill 50 is unavailable on this install, no email
follow-up is prepared (the B13 re-survey fallback: today's state, with the
reason on record).

## 4. MANIFEST REGISTRATION SPEC (post-merge step, exact)

Registration is deliberately NOT in the Item 33c branch (the B30 precedent:
the seam module lands first; registration lands with the manifest lockstep,
and the manifest version line is contended by parallel branches). When this
branch merges, register in universal-sops/presentation-slide-craft/
PIPELINE-MANIFEST.json and run the full manifest lockstep
(presentations-drift-gates.sh, manifest_assert.py, phase_doc_sync,
MANIFEST-SOURCE.txt, role-library restamp):

    id:            P-U-EMAIL-PREP
    order:         9.1 (delivery order; after P9-DELIVER 9.0, beside
                   P-U-QC 9.05 -- the brief needs the delivered links)
    defers_unless: intake.want_email_sequences == "yes"
    executor:      script: python3 scripts/email_followup.py --run-dir {run_dir}
    owning role:   media-librarian-ghl-updater
    produces:      working/email/email-brief.json,
                   working/email/skill44-handoff.json,
                   working/checkpoints/email.json

Until registration lands, the module is directly runnable by an operator
with the command above; the defers expression already resolves correctly
against presentation_job/defers.py.

## 5. THE SKILL 44 APPROVAL HANDOFF

skill44-handoff.json is the operator-surface record: what was prepared, the
approval step, and the record-back. A human reviews the draft package at
Skill 44's operator surface. On approval: Skill 50 runs P1 SELECT, P2
GENERATE, P3 QC, P4 DEPLOY through email-engine-entry.sh; its P4 emits the
DRAFT-ONLY build-plan.json that Skill 44 executes (every workflow status
"draft"; Skill 50 never emits a published workflow; the Skill-44
built-workflow QC gate >= 8.5 runs on the draft). The approval (approver +
time) and the resulting workflow id are recorded back into
working/checkpoints/email.json. On decline, the operator decision is
recorded in the same checkpoint. When Item 33a's two-way seam
(ghl-ops-request.json out, ghl-ops-receipt.json back) lands, this handoff
record is the object that seam carries; the approval and workflow-id return
path lands in the same checkpoint either way.

WIRING GATE NOTE: per object, the wiring evidence for this branch is the
handoff record + the checkpoint's approval block + (after approval) the
workflow id recorded back. The presentations engine creates no workflow,
sends nothing, and arms nothing; a run record may never show a sent or
live state for an object Skill 44 has not approved.

## 6. RULES

1. DRAFT-ONLY, always. Nothing in this branch sends email or arms a
   sequence; there is no send path in the executor (structurally asserted
   by scripts/tests/test_email_followup.py: no network/process imports, no
   send-like calls).
2. The election is the client's. Default NO; a recommendation is never a
   hidden election. Only an explicit "yes" prepares anything.
3. A decline without the client's own verbatim reason is not a waiver; it
   fails closed (AF-EMAIL-WAIVER-MISSING). Never author, infer, summarize,
   or fill a reason.
4. Absence defers. An unanswered election is recorded as deferred, never
   as a decline and never as consent.
5. Brief answers come from the run record only; gaps are named in
   missing_inputs, never invented. Skill 50's intake attestation is never
   fabricated (section 3).
6. Human approval happens at Skill 44's operator surface BEFORE Skill 50
   runs, and the approval + workflow id land in the run record (section 5).

## 7. VERIFY

    python3 scripts/email_followup.py --selftest
    python3 -m pytest scripts/tests/test_email_followup.py
    python3 -m pytest scripts/tests/test_upsell_intake_shape.py
    python3 intake/interview-app/payload/build_questions_payload.py --selftest
    node intake/interview-app/tools/gen_ui_questions.mjs --check
    python3 -m pytest intake/interview-app/test/test_email_election_flow.py \
                      intake/interview-app/test/test_payload.py
    bash 50-email-engine/verify.sh        (repo root; Skill 50 side unchanged)

## 8. STATUS

| Piece | State | Evidence |
|---|---|---|
| Election pair in both question banks + waiver mapping | LIVE (this branch) | intake/upsell-questions.json 7.9/7.91; intake/deck-intake-questions.json v1.13.0 |
| Hosted payload + writer + PRES-006 contract lockstep | LIVE (this branch) | payload selftest; gen_ui_questions --check; test_email_election_flow.py |
| Delivery gate + draft-package preparation | LIVE (this branch) | scripts/email_followup.py --selftest; test_email_followup.py |
| Engine carriage (defers + resolve) | LIVE (this branch) | test_email_followup.py TestEngineCarriage |
| Skill 50 doctrine twin | LIVE (this branch) | 50-email-engine/SKILL.md integration section; verify.sh |
| Manifest phase P-U-EMAIL-PREP | PENDING (specified, section 4) | sequenced post-merge with the manifest lockstep |
| Skill 44 live approval + workflow record-back | PENDING (operator surface) | handoff record shape shipped; live approval happens per run, post Item 33a seam |
| Live proof on a real run | PENDING | the Item 28 proof run |

## 9. HANDBACK

working/checkpoints/email.json (written on every outcome):

    {
      "deck_slug": ...,
      "recorded_at": ...,
      "source": "presentations/scripts/email_followup.py",
      "election": {"field": "WANT_EMAIL_SEQUENCES", "value": <raw answer>},
      "gate": {<resolve_email_gate result>},
      "outcome": "prepared_awaiting_human_approval" |
                 "waived_nothing_prepared" |
                 "deferred_nothing_prepared" |
                 "gate_blocked_nothing_prepared" |
                 "elected_skill50_unavailable_nothing_prepared" |
                 "elected_nothing_applicable_prepared",
      "waiver": {"rule": "email_sequences",
                 "client_request_quote": <verbatim>}   // declined only
      "skill50": {"available": bool, "path": ...},      // elected only
      "packages": [{"sequence_id": ..., "status":
                    "prepared_draft" | "not_applicable" | "not_prepared",
                    "detail": ...}],
      "approval": {"status": "AWAITING_HUMAN_APPROVAL" |
                             "NOT_APPLICABLE", ...},
      "artifacts": {"brief_package": "working/email/email-brief.json",
                    "handoff": "working/email/skill44-handoff.json"}
    }
