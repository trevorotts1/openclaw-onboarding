# PRESENTATION DEPARTMENT — ENFORCEMENT SPEC (2026-08-24)

Supersedes prior informal QC doctrine for the presentations department. This
document states what is now MECHANICALLY ENFORCED, where, and what happens when
each check fails. Every enforcement point listed here was applied in the
2026-08-24 fix sweep (see LEDGER.md) and adversarially QC'd by Gemini 3.7 Flash
via OpenRouter (see QC_RESULTS_gemini.json).

Scope: `~/openclaw-onboarding` (engine + SOPs + intake app) and
`~/blackceo-command-center` (kanban board + jobs + API routes).

---

## 1. Design principle: fail closed

Every gate added or hardened by this sweep follows one rule: **when evidence is
missing, the gate FAILS — it does not degrade to a warning or a pass.**

| Situation | Old behavior | New behavior |
|---|---|---|
| Verifier crashes mid-run | Degraded to PASS | FAIL with AF-*-CRASH / AF-*-MISSING (F03) |
| Question bank spec mispathed | Silent no-op | Named error, exit 3; engine call sites emit AF-INTAKE-BATCH FAIL (F25) |
| qc_check.py absent at delivery | Nothing checked | FATAL pre-delivery AF-QC-CHECK (F02) |
| Attestation row hand-written | Counted as real | Ignored unless status=='done' AND substance_verified==True (F04/F04b) |
| Bundle file present but 1-byte stub | Passed FIX-8 | Must clear DELIVERABLE_AUDIT_SPEC min_bytes floor (F27) |
| Integrity gaps at close() | Cert minted anyway, DONE reached | Terminal DONE blocked (F15) |
| Dead render run (no events) | Shielded by exemption forever | Activity window (24h) shorter than age ceiling (72h); no activity → ages out (F09) |

Test-only degradation remains available but ONLY under the existing runner
contract: `PRESENTATION_ALLOW_DEGRADED_VERIFIERS=1`, `CI`, `OPENCLAW_TEST`, or
a `.test-context` marker in the run dir (F03).

---

## 2. The delivery boundary (nothing ships without proof)

Order of gates at end of run, all inside run_signature_deck.py / build_deck.py:

1. **Structure pin check** (`verify.sh` check 1a →
   `blend_voice_governance.py --prove-pin`): sacred-structure-hashes.json must
   exist, every pinned file must exist, every hash must match. Drift → rc=3
   naming the diff. (F05)
2. **Mechanical QC gate** (`qc_check.py --run-dir`, wired before prove-deck):
   all 48 manifest codes with `enforced_by:"qc_check"` now have a runtime
   caller. Violations → FATAL pre-delivery AF-QC-CHECK. Missing script → same.
   (F02)
3. **Precondition chain reader** (`build_deck.check_phase_preconditions`,
   mirrored in `canonical_render_guard.attested_phase_ids`): attestation rows
   count only when status=='done' AND substance_verified==True. Hand-written
   rows satisfy nothing downstream. (F04/F04b)
4. **FIX-8 bundle gate** (`fix_bundle_complete.py`): all ten deliverables must
   exist AND clear their per-key min_bytes floor (deck_pptx 1 MB,
   audio_mp3 512 KB, speech_md/speech_fish_md 2 KB, speech_pdf 3 KB,
   deck_pdf/guide_pdf 51.2 KB, infographic_png 102.4 KB,
   teleprompter_html 20 KB, webinar_mp4 1 MB). Undersized →
   AF-BUNDLE-INCOMPLETE enumerating the keys. Pass marker
   bundle_complete.json is removed on regression. (F27)

---

## 3. The conversation gate

- `intake_trace_check.py`: both question banks must load (present, parseable,
  non-zero). Any problem → MissingQuestionBank → exit 3 with named JSON error.
  Engine call sites convert this into AF-INTAKE-BATCH FAIL. (F25)
- `prove_sp_routing.py` Signal 4: request/brief free text is scanned
  case-insensitively for signature-presentation markers ("signature
  presentation", "signature_presentation", "signature-style presentation");
  presentation_type also honors `.normalized`. A deck that behaves like SP
  without declaring it fires AF-SP-TYPE-UNDECLARED. (F24)
- Golden example (golden-quest fixtures) teaches the true v51 five-gate plan:
  P0A-INTAKE 0.1 (director-of-presentations), P-SP-CLAIM 0.14,
  P-SP-INTAKE 0.15, P-SP-INTAKE-TRACE 0.16 (architect), P4-COPY 4
  (slide-copywriter), P-SP-STRUCTURE 4.1 (architect), P-SP-P3-HYGIENE 4.15
  (qc-specialist-signature-presentations). (F23)

---

## 4. Geometry and spelling are enforced by default

Canonical entry scripts export `PRESENTATION_SLIDE_GEOMETRY_ENFORCE` with a
`${VAR:-1}` default: AF-TEXT-OVERFLOW, AF-SPELLING, AF-TYPE-SIZE-MEASURED fire
as hard autofails on canonical runs. An explicit pre-set `=0` still opts out;
nothing else does. (F16)

---

## 5. Timeouts and hangs — every wait is bounded

| Wait | Bound |
|---|---|
| Subprocess fallbacks (executor/render/notes-sync) when reaper unimportable | Same hard cap as reaper path + loud WARNING naming the missing module (F06) |
| KIE submit 429 retry loops (batch Phase A + per-slide) | KIE_SUBMIT_MAX_429=15 consecutive 429s → slide FAILS, never hangs (env-overridable) (F07) |
| KIE poll side | Already bounded by POLL_MAX_SECONDS |
| Batch render resume | Reuses verified PNGs (completed=True + file exists + sha256 match + PNG magic); only new slides re-billed (F08) |
| Client submit fetch (interview app, repo + deployed-r2) | fetchWithTimeout: 20 s AbortController timer, 2 retries with linear backoff, friendly "took too long" message; download fallback preserved (F10/F10b) |
| Long renders vs stale sweep | Presentations in_progress tasks < 72 h old (PRESENTATIONS_RENDER_EXEMPT_HOURS) exempt ONLY if an events row exists within 24 h (PRESENTATIONS_ACTIVITY_WINDOW_HOURS — strictly shorter than the ceiling so dead runs always age out). Activity query fails closed to no-activity. (F09) |

---

## 6. Kanban movement — cards cannot die silently

1. **Intake UI parity**: deployed-r2/public/index.html QUESTIONS array is
   byte-identical to the repo canonical copy (15 questions including
   presentation_type at order 0); payload builder never fabricates a type.
   App-submitted decks can no longer crash the bridge's UngroundedDeckTypeError
   before a card exists. (F11)
2. **Worker completeness**: `/api/intake` POST validates REQUIRED_BRIEF_FIELDS
   (10 fields) + PRESENTATION_TYPE; missing → 422 naming each missing field.
   Applied to repo worker AND deployed-r2 worker. (F21/F21b)
3. **Worker router**: route conditions indexed for the leading "api" segment —
   /api/intake POST, /api/intake/list GET, /api/dept-start POST and all
   routeSessions() endpoints were unreachable 404s before this sweep. (F22)
4. **Bridge poll resilience**: dept_start_deferred sessions return rc=5 and are
   NOT marked processed (card creation retries instead of dying silently);
   each session is wrapped in try/except so one poison session cannot
   crash-loop the batch. (F12/F13)
5. **Bulk move cert gate**: the bulk task-update API route requires the
   presentations process_certificate on move→done — raw bulk UPDATE no longer
   bypasses transition(). (F01)
6. **QC scorer close-out**: done-transition reads the stored process_certificate
   from the task row; if absent it holds review with an explicit event naming
   the missing cert — cards passing QC ≥8.5 no longer throw
   PRECONDITION_PROCESS_CERTIFICATE and stall in review forever. (F14)
7. **Parent progress**: children in 'review' do not count toward the parent's
   done-count. (F26)

---

## 7. QC verdict integrity

- **Aggregation rounds DOWN**: qc_aggregate computed_average uses
  math.floor(raw*1e4)/1e4 then compares raw values. 8.49996 fails; exactly 8.5
  passes. (F20)
- **Cap-exhaustion override cannot be self-minted**: the override consults
  load_skip_approvals, which refuses QC phases outright (AF-QC-SKIP) and
  validates owner_msg_id via the Telegram oracle. ForgedApprovalError → no
  override → EXIT_QC_EXHAUSTED rc=7. Direct bd._owner_skip_approved consult
  removed from the loop body. (F17)
- **Skip approvals validate fully**: empty timestamp rejected with a named
  rejection ("a skip with no timestamp is not a verifiable owner decision");
  placeholder/timezone-free timestamps still rejected. (F19)
- **Attestation writes are atomic**: all process_manifest.json write sites use
  _atomic_write_json (temp + os.replace) so a crash cannot truncate the whole
  attestation chain. (F18)

---

## 8. Environment variables introduced or made load-bearing

| Variable | Default | Meaning |
|---|---|---|
| KIE_SUBMIT_MAX_429 | 15 | Max consecutive 429s at KIE submit before the slide FAILS |
| PRESENTATIONS_RENDER_EXEMPT_HOURS | 72 | Age ceiling for the stale-sweep long-render exemption (command center) |
| PRESENTATIONS_ACTIVITY_WINDOW_HOURS | 24 | Events-recency window for the same exemption; MUST stay < the ceiling |
| PRESENTATION_SLIDE_GEOMETRY_ENFORCE | 1 (canonical entry) | 1 = geometry/spelling/type-size gates are hard autofails |
| PRESENTATION_ALLOW_DEGRADED_VERIFIERS | unset | Test-only degraded-verifier escape hatch (also CI / OPENCLAW_TEST / .test-context) |

---

## 9. Regression tests added or updated

- test_delivery_guard_selfblock.py: fixture rewritten to the attest_phase()
  row shape (status='done', substance_verified=True) — its bare id-only rows
  were exactly the forged shape F04 now rejects, which is the fix working as
  designed.
- test_fix8_bundle_complete.py: fixtures at-floor; new
  test_undersized_stub_is_not_done_f27.
- test_webinar_builder.py: bundle fixtures converted from flat 2048-byte blobs
  to per-key min_bytes-floor writers.
- fix_bundle_complete.py --selftest: CASE F27 undersized audio stub; CASE A
  deck at its own 1 MB floor.
- intake_trace_check.py self-test Test 0: mispathed spec raises
  MissingQuestionBank.

---

## 10. QC of the sweep itself

Every fix group was reviewed by Gemini 3.7 Flash (OpenRouter direct,
reasoning_effort max) with an adversarial prompt instructed to REFUTE the fix.
Verdicts: 22/22 groups PASS. Two fixes required remediation rounds:
- F09: v1 FAIL (no activity check) → v2 FAIL (activity window defaulted equal
  to age ceiling, shielding dead runs) → v3 PASS after splitting the window
  into its own env var defaulting 24h.
- F27/F02-group first-round FAILs were diff-construction artifacts (diffs built
  from post-fix baselines missing hunks); rebuilt cumulative diffs PASS. The
  live files were independently verified (py_compile, node --check, behavioral
  proofs) regardless of diff rendering.

Full verdicts: QC_RESULTS_gemini.json. Per-fix application records with backup
paths: LEDGER.md.
