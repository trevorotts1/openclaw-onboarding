# SOP-SLIDE-05: THE PROCESS MANIFEST (per-run attestation that the full SOP stack ran)

**Cluster:** Slide-Craft Rules
**Master authority:** universal-sops/CLIENT-WEBINAR-DECK-SOP.md (the pipeline map, §0) + presentation-slide-craft/MASTER-QC-AUTOFAIL-RULESET.md (Section 2.6 renderer + process-manifest auto-fails)
**Owning role:** every phase's owning role APPENDS its entry; the Director finalizes it at closeout; the QC Specialist - Presentations reads it.
**Canonical renderer:** `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/build_deck.py` (the deterministic Phase-4 renderer + Phase-8 assembler; it WRITES this manifest's render/assembly entries).
**Status:** DRAFT for integration. Defines the single attestation artifact the renderer auto-fails (AF-RENDERER / AF-MODEL-SOVEREIGNTY / AF-NO-VISION-QC / AF-CONVERTER-PARITY) and AF-COVERAGE-1 assert against.

---

## 0. WHY THIS SOP EXISTS (the defect it kills)

A deck can ship looking finished while whole phases were silently skipped: no copy QC, no vision image-QC, an ad-hoc renderer instead of the canonical one, a non-manifest model quietly substituted, or a Mode B deck compressed below its source. Prose that says "run all phases" does not stop a skipped phase. The fix is a single machine-readable artifact that each phase APPENDS to as it runs, finalized at closeout, that the QC gate reads to PROVE the full SOP stack actually executed. A phase with no manifest entry is treated as a phase that did not run, and the corresponding deck-level auto-fail fires.

This is build doctrine. NONE of its content is ever printed on a slide.

---

## 1. THE FILE

`working/checkpoints/process_manifest.json` — one JSON object per run, created at Phase A and appended to through closeout. It lives in the run's `working/checkpoints/` subtree (the same `working/` tree `build_deck.py` walks up to for its process preflight). It is the single per-run attestation that the full SOP stack ran.

Top-level shape:

```json
{
  "run_id": "<deck slug + date, e.g. webinar-decks/[CLIENT_SLUG]/[DECK_SLUG]/[DATE]>",
  "mode": "A | B",
  "source_slide_count": 0,
  "slide_count_final": 0,
  "model_manifest": "gpt-image-2 (per CLIENT-WEBINAR-DECK-SOP §9.0)",
  "phases": [ /* one PHASE ENTRY per phase that ran, in order */ ],
  "finalized": false,
  "finalized_at": null
}
```

`source_slide_count` is copied from `mission_prd.json` (Mode B = the count of existing source slides; Mode A = 0). `slide_count_final = client_requested_slide_count` **when the client stated an explicit slide count** (honored EXACTLY — 25 -> 25, 50 -> 50, 500 -> 500 — never floored up, capped down, defaulted, or substituted; the client is never asked to accept a different number; it OVERRIDES both the duration sizing and the `source_slide_count` floor, enforced by `AF-SLIDE-COUNT-EXACT`); **otherwise** `slide_count_final = max(duration_target, source_slide_count)`. These fields are what AF-COVERAGE-1 and AF-SLIDE-COUNT-EXACT read.

---

## 2. THE PHASE ENTRY (appended once per phase, the moment that phase completes)

Each phase, as it finishes, APPENDS exactly one object to `phases[]`:

```json
{
  "phase": "1Q",
  "role": "QC Specialist - Presentations",
  "artifact_path": "working/qc/copy_qc_report.json",
  "ran": true,
  "qc_score": 9.1,
  "qc_pass": true,
  "gate_codes_checked": ["AF-HOOK-1", "AF-AUD-4", "AF-OBI-2", "AF-DEN-1", "AF-COVERAGE-1"],
  "timestamp": "2026-06-16T14:03:00Z"
}
```

Field rules:
- **phase** (string): the pipeline-map phase id (`A`, `B`, `1`, `1Q`, `1A`, `1.5`, `2`, `3`, `4`, `5`, `6`, `POST-6`).
- **role** (string): the owning role that ran the phase (spell it out, no acronyms).
- **artifact_path** (string): the primary artifact this phase produced, relative to the run dir (e.g. `working/copy/slides_copy.md`, `working/renders/`, the assembled `.pptx`). For the render/assembly phases this points at the canonical `scripts/build_deck.py` invocation and its outputs.
- **ran** (bool): true only if the phase actually executed. A phase that was skipped either has no entry or `ran: false` (both fail the corresponding gate).
- **qc_score** (number): the phase's QC score where a QC gate applies (Phase 1Q, 3, 5, 6); use `null` for non-QC phases.
- **qc_pass** (bool): whether the phase's gate passed (>= 8.5 and no auto-fail). `null` where no gate applies.
- **gate_codes_checked** (array of string): the exact auto-fail codes this phase evaluated. The render phases MUST include the render gate codes (AF-I*, AF-PLACEHOLDER, AF-HOOK render codes) so AF-NO-VISION-QC can confirm the vision read happened.
- **timestamp** (string, ISO-8601 UTC): when the entry was appended.

---

## 3. WHAT EACH GATE READS FROM THE MANIFEST

These are the assertions the MASTER-QC-AUTOFAIL-RULESET Section 2.5/2.6 gates make against this file (all DECK-level vetoes):

| Gate | Reads | Fails when |
|---|---|---|
| AF-COVERAGE-1 | `source_slide_count`, assembled page count | `final_slide_count < source_slide_count` (Mode B add-only; Mode A `source==0` always passes) |
| AF-RENDERER | the Phase-4/6 entry: `role == build_deck`, `ran == true`, not adhoc | no canonical-renderer entry, or `build_deck.py` ran with `--adhoc-no-process` on a real deliverable |
| AF-MODEL-SOVEREIGNTY | the Phase-4 generation entry's model id vs `model_manifest` | a non-manifest model id recorded |
| AF-NO-VISION-QC | the Phase-5 image-QC entry: `ran == true` + render `gate_codes_checked` | no Phase-5 image-QC entry, or it did not record a multimodal vision read of every rendered slide |
| AF-CONVERTER-PARITY | the assembly-phase page count vs count of Phase-5-passed `slide-NN.png` | assembled PPTX page count != QC-passed render count |

There is no `render_manifest.json`, no `render_deck.py`, and no `vision_qc_log.json` in this system. Every renderer/coverage assertion reads `working/checkpoints/process_manifest.json` and only it.

---

## 4. FINALIZATION (closeout)

At closeout (after Phase 6 final deck QC passes), the Director:
1. Confirms every required phase (`A`, `B`, `1`, `1Q`, `1A`, `1.5`, `2`, `3`, `4`, `5`, `6`) has an entry with `ran: true`.
2. Confirms every QC phase (`1Q`, `3`, `5`, `6`) has `qc_pass: true`.
3. Confirms the render/assembly entries name the canonical `scripts/build_deck.py` and a manifest-compliant model.
4. Sets `finalized: true` and `finalized_at` to the closeout timestamp.

A deck whose `process_manifest.json` is not finalized, or is missing any required phase entry, is NOT final regardless of how the rendered slides look. The manifest is the single per-run attestation that the full SOP stack ran.

---

## 5. ESCALATION / REPAIR PATH

1. A missing or `ran: false` phase entry at Phase 6: the QC Specialist fails the DECK with the matching auto-fail code and routes the missing phase back to its owning role to actually run it (not to backfill the manifest).
2. A renderer entry naming anything other than `scripts/build_deck.py` (AF-RENDERER): re-render and re-assemble through the canonical renderer; the manifest entry is rewritten by `build_deck.py` itself, never hand-edited to pass.
3. A non-manifest model id (AF-MODEL-SOVEREIGNTY): halt; per the master SOP a model outage means PAUSE and escalate, never substitute. The Director escalates to the operator.
4. Hand-editing the manifest to fake a `ran: true` entry is a process-integrity violation (the manifest must reflect what actually executed); on detection, escalate to the Director and re-run the phase.
5. 3 loops on the same missing-phase failure: escalate to the Director, then the operator. File a bug ticket.

---

## 6. RESEARCH BASE

- The pipeline map (CLIENT-WEBINAR-DECK-SOP §0): the ordered phase list this manifest attests to.
- `scripts/build_deck.py` process preflight: the deterministic renderer already refuses to render without the upstream dept artifacts; this manifest extends that guarantee across the WHOLE stack and makes the attestation machine-readable at the QC gate.
- The lesson that description alone fails (MASTER-QC-AUTOFAIL-RULESET §0): a phase that is merely told to run can be skipped; a phase whose execution is attested in a gate-read artifact cannot be silently skipped.

---

## 7. DETERMINISTIC RUNNER + PHASE PRECONDITIONS + PHASE-0 PRE-FLIGHT (Decision 3C)

`scripts/run_signature_deck.py` is the deterministic signature-deck runner — a state-machine over `PIPELINE-MANIFEST.json` that ORCHESTRATES the pipeline around `build_deck.py` (which it invokes as a subprocess for the render phase; the render path is never re-implemented or broken).

**Phase order + attestation.** The runner reads `phases[]` from the manifest and walks them in ascending `order`. Each phase's completion is proven by an attestation appended to `working/checkpoints/process_manifest.json` (the same cumulative file Section 1 defines). The runner appends a `phase_attestations[]` entry `{phase_id, owning_role, status, artifact_sha, attested_at}` as each phase clears.

**Phase preconditions — skipping/reordering is structurally impossible (AF-PHASE-SKIPPED).** Before dispatching phase N, the runner asserts (via the shared checker `build_deck.check_phase_preconditions`) that EVERY phase with a lower `order` has an attestation in `process_manifest.json` AND its `produces_artifact` is present. A missing prior attestation is a HARD ABORT (exit 2, **AF-PHASE-SKIPPED**) naming the missing phase. Phase N+1 literally reads phase N's attestation as a precondition, so a phase cannot be silently skipped or reordered.

**Owner-authorized skip (the only exception — NOT a free flag).** A phase may be skipped ONLY with a logged owner approval in `working/checkpoints/phase_skip_approvals.json`:
```json
{ "approvals": [
  { "phase_id": "P3-ARC", "owner_approved": true,
    "approved_by": "<owner id>", "reason": "pitchless deck — no offer arc",
    "timestamp": "2026-06-20T00:00:00Z" } ] }
```
The runner records the skipped phase as `status: "skipped_owner_authorized"`. Absent the signed record, the precondition is unmet and the run aborts — the approval file is the only thing that authorizes a skip.

**Phase-0 pre-flight (mandatory, before ANY dispatch/render).**
1. `detect_platform(run_dir)` records `box_type` (mac -> fewer render workers; vps -> more) into the brief/attestation. REUSED from `build_deck.py`, not re-implemented.
2. **Kie.ai balance pre-flight (AF-KIE-BALANCE):** `GET https://api.kie.ai/api/v1/chat/credit` reads the live credit balance; if `balance < estimated_floor` (`slide_count x PER_SLIDE_CREDIT_ESTIMATE x KIE_BALANCE_FLOOR_MULTIPLIER`) the runner HARD-ABORTS (exit 4) BEFORE a single slide is dispatched, so a run never dies mid-deck and burns credits on a partial render. This is the shared `build_deck.kie_balance_preflight` — `build_deck.py main()` runs the same gate at Phase-0 before its own render fan-out.

**`--adhoc` escape (owner-authorized + logged).** `--adhoc` is REFUSED unless `working/checkpoints/adhoc_authorization.json` carries `{owner_approved:true, approved_by, reason, timestamp}`. With it, the runner prints the loud non-deliverable banner and relaxes the phase preconditions + balance pre-flight; the output is explicitly NOT a process-compliant client deliverable. Without the logged record, `--adhoc` is not a free flag.

**Lockstep.** `AF-PHASE-SKIPPED` is `enforced_by: runner` (py_symbol null — out of the build_deck Guard-A set by design); `AF-KIE-BALANCE` is `enforced_by: build_deck` (py_symbol `kie_balance_preflight`, with `KIE_CREDIT_URL` / `PER_SLIDE_CREDIT_ESTIMATE` / `KIE_BALANCE_FLOOR_MULTIPLIER` / `_fetch_kie_balance` as secondary symbols), and has a negative test in `scripts/test_preflight.py`.
