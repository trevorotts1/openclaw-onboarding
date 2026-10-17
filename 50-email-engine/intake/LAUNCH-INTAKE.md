# Launch Intake Contract: signature_launch_landing_10

This document is the human-readable half of `intake/launch-intake-contract.json`.
It defines the SHARED-LAUNCH intake path for the Signature Launch email profile.
The machine half is validated by `tools/launch_intake_adapter.py`; the brief it
emits is enforced by `tools/prove-email.py` under gate code
AF-EMAIL-LAUNCH-PROVENANCE.

## Two intake paths, kept separate on purpose

The Email Engine has two ways to reach a locked brief, and they never mix:

1. **Legacy interactive path.** One block of questions asked all at once
   (`intake/email-intake-questions.json`), proven by the brief's
   `asked_all_at_once` attestation or its `conversation_ledger`.
   `test_intake_contract_authority.py` pins this contract's required answer
   set: objective, buyer_type, offer, brand_voice, sequence_position,
   founder_name. The launch path does not edit that contract, does not read
   its questions, and does not reuse its sequencing.
2. **Launch path (this contract).** A Signature Launch client never answers
   the legacy questionnaire. Their facts were collected and approved inside
   the S49 launch intake, and the adapter imports that approved result with
   its provenance intact. A launch brief carries `intake_mode:
   "signature_launch"` and a `launch_provenance` block instead of the legacy
   attestation flags. Setting `asked_all_at_once: true` on a launch brief
   would be a fabricated attestation, so the adapter never emits it and the
   prover never asks for it on this path.

## Inputs

The adapter consumes five artifacts, all produced and approved upstream:

| Input | Owner | What it proves |
|---|---|---|
| Intake session (`signature-launch-intake/v1`) | S49 | The answer ledger (each answer carries value, state, source_ref, question_id), the approved plan hash, the client identity reference, session status |
| Launch record (`schema/launch.schema.json` v1.0) | S49 | The plan itself: offers with per-offer source_kind and source_ref, brand binding, revision, journey mode, plan_approval_ref |
| Approval record (`approval.schema.json`) | S49 | Type launch_plan_build, subject hash bound to the plan, approver identity, scope, revocation state, the platform reference of the client's own response |
| Brand facts document | The launch | brand_ref, founder_name (the founder's actual name), brand_voice, optional declared brand_hash, provenance block |
| Landing facts document | The launch | Section 5 why, section 6 who with exactly three pains carrying refs, sections 8, 9, 10, round_timing with ref and fact, testimonial_evidence (entries or an explicit null), provenance block |

The landing facts shape mirrors `examples/golden-signature-launch-10/landing-facts.json`,
with a `provenance` block and an optional `launch_id` binding added.

## Field mapping: S49 shape to locked brief

| Brief field | S49 source | Provenance recorded |
|---|---|---|
| answers.sequence_position = signature-launch-landing-10 | Profile constant (catalog record) | verified_existing, the profile record path |
| answers.objective = promotional | Profile constant | verified_existing, the profile record path |
| answers.buyer_type = all | Profile constant | verified_existing, the profile record path |
| answers.offer, answers.offer_token_ledger | Launch record main offer display_name values, in record order | The main offer's own source_kind and source_ref; offer reference, launch id, revision, and plan hash in launch_provenance |
| answers.founder_name | Brand facts founder_name | Brand facts provenance block, the document sha256, brand_ref equality with the launch record |
| answers.brand_voice | Brand facts brand_voice | Brand facts provenance block and document sha256 |
| Section 5 why (authoring fact) | Landing facts landing.section_5_why | Landing facts provenance block and document sha256; presence cross-checked against ledger answer offers.main.transformation |
| Three section 6 pains (authoring facts) | Landing facts landing.section_6_who.pains (refs landing.section6.pain.1 to .3) | Landing facts provenance; presence and approved state cross-checked against ledger answer offers.main.pains |
| Sections 8, 9, 10 (authoring facts) | Landing facts landing.section_8_what_is_inside, section_9_how_it_works, section_10_support | Landing facts provenance block and document sha256 |
| Round timing / deadline facts | Landing facts landing.round_timing (ref plus fact) | Landing facts provenance; a deadline declaration without provenance is refused |
| Testimonial evidence | Landing facts landing.testimonial_evidence, governed by ledger answer proof (question a5) | Explicit null stays null; a5 state not_applicable requires the evidence to be null |
| answers.locked_overrides (when present) | Session answers.locked_overrides ledger entries | Each channel entry's own state, source_ref, question_id; only the channels word_band_override, expected_preview_count, subject_mode exist |

## Approval discipline

The adapter replicates the S49 plan gate (`validate_launch_plan.py`
`_check_approval_record`) rather than inventing a second standard:

- The plan document hash is recomputed with the S49 canonicalization
  (the launch record minus `status` and `plan_approval_ref`, keys sorted,
  compact separators, sha256). It must equal the session plan_hash and the
  approval subject_hash. Any commercial change after approval invalidates
  the brief.
- The approval must be of type launch_plan_build, its scope list must
  contain launch_plan_build, it must not be revoked, its verification class
  must be recognized, and it must carry the platform reference of the
  client's own response.
- The approver must be the client identity recorded in the intake session,
  and must differ from the worker identity operating the adapter when one is
  supplied. A bare `"approved": true` flag anywhere is never read as
  evidence.

One deliberate difference from the S49 gate: the adapter does not apply the
gate's 72 hour default expiry. The gate checks freshness when the approval
is acted on for the build; the adapter is a downstream consumer verifying
the binding (hash, identity, scope, revocation), which does not decay, and
it refuses future-dated records. Operators who need a freshness window can
impose one at the run level.

## Field states

States follow packet doc 03: provided, verified_existing,
recommended_unapproved, approved_recommendation, unknown, not_applicable.
The adapter consumes only provided, verified_existing, and
approved_recommendation. A recommendation the client has not approved does
not become a locked email fact because the plan approval hash binds the
launch record, not the session answer ledger. Blank is not not_applicable:
the only field that may be not_applicable is testimonial evidence, and there
it produces an explicit null, never an omission.

## Refusals

The adapter fails closed (exit 2, naming the refusal) on every case listed
in the contract JSON `refusals` array, including: plan hash mismatch,
worker self-approval, revoked approval, narrowed scope, an unknown or
unapproved consumed answer, brand binding mismatch, landing facts bound to
a different launch or offer, pains that are not exactly three with distinct
refs, testimonial evidence absent rather than explicitly null, and a
deadline fact without provenance.

## Running it

```
python3 tools/launch_intake_adapter.py \
  --session launch-intake-session.json \
  --launch launch.json \
  --approval approval.json \
  --brand-facts brand-facts.json \
  --landing-facts landing-facts.json \
  --worker-identity worker:<id> \
  --out brief.json
python3 tools/prove-email.py brief.json            # intake gate, exit 0
python3 tools/prove-email.py emails.json --brief brief.json
python3 tools/launch_intake_adapter.py --self-test
python3 test_launch_intake_adapter.py
```

## Known limits

- S49 does not publish how `brand_hash` is computed in the artifacts this
  build read, so the adapter cannot recompute it. It binds brand facts by
  brand_ref equality, requires equality when the facts document declares a
  brand_hash, and always records the facts document's own sha256 in the
  brief so any later change is detectable.
- The adapter checks that the approved intake pains and the landing facts
  pains both exist in an approved state with three distinct refs. It does
  not judge whether the landing wording faithfully carries the intake
  wording; that judgment belongs to copy review, not to a hash gate.
- `schema/brief.schema.json` documents the legacy brief shape; its
  `asked_all_at_once` and `question_block_msg_id` requirements describe the
  legacy path. Launch briefs are governed by this contract and the prover's
  launch branch. The schema carries additive `intake_mode` and
  `launch_provenance` properties so the launch fields are documented there
  too; a future schema revision should express the two paths as explicit
  alternatives.
