# BUILD NOTES — Skill 80 Signature Upsell (S80-01, S80-02, S80-03)

**Room:** S80 · **Scope built in this pass:** S80-01, S80-02, S80-03 only.
**Location:** `~/workspace/signature-launch/rooms/S80/work/80-signature-upsell/`
**Status language:** local L0/L1 evidence only. Nothing here is installed,
merged, published, or live. All fixture offers, prices, IDs and copy are
**TEST ONLY** and labeled as such in every file.

Sources read in full before coding (this worker): packet
`10_SKILL_80_UPSELL_1_AND_2_SPEC.md`, `02_SHARED_CONTRACTS_AND_ARCHITECTURE.md`,
`18_END_TO_END_ACCEPTANCE_MATRIX.md`, `20_OWNER_SOURCE_MATERIAL.md`
(Phase 3 + Sample Upsell Page in full), and the reference contracts/schemas
(`reference_contracts.py`, page-request, page-result, offer, route-graph,
acceptance-cases.json — 64 cases cross-checked).

## Files (SHA-256)

| File | SHA-256 |
|---|---|
| profiles/upsell-profile.json | 074a3a6a375df76782cc07b88c1441a34999033cc77ba7d1c1014d1b1baeb37f |
| schemas/upsell-request.schema.json | e2bea6c864bcb8178e3a12ed2b50c6ba316f2095e7bc8ff05a7ec1b287cfd334 |
| schemas/upsell-result.schema.json | da4765fe4253545155d8a27f3a6ab84fc9e14b1a39279b388c7b77b401c550c9 |
| scripts/validate_upsell_copy.py | 99095b4908d765efcec3a33ef9ba6104c4c892e619a60af2c4f895760b306c61 |
| references/substantive-review-rubric.md | 978869611a1159ccf2da90e9960cfd7cee838968d21b421ac7d14c5d80d382ed |
| tests/test_validate_upsell_copy.py | b0f50e1edbffe33d99e41598765986a530588385b290259507c581d9b86af7c4 |
| fixtures/copy-owner-sample-upsell1.private.json | e8b49502d8d6b2f48fb7520b7768005279fe31e25696919d3b028479930b4a2a |
| fixtures/copy-upsell1-public.valid.json | 2fc2f757142716db205adddc31d9cc8266d1ff4e1512771c8a72df30bea3b851 |
| fixtures/copy-upsell2-public.valid.json | f47f67bc8a1f7aec583589ef775861189bf40a3c80f7ae8136688001708710cb |
| fixtures/request-upsell1.testonly.json | 6d512888869747ac667a0b06ed36ee027333fccb64f112acd1ac761d60ceb8f9 |
| fixtures/request-upsell2.testonly.json | a91c700850333df0768739e0e26ebe68cb9b4df839d9e7d6a53cf017c8ad2194 |
| fixtures/result-upsell1.testonly.json | de642a3b762908b3f400dec080d97ac19405c970c70ff0514d497275a2a043c1 |
| fixtures/result-upsell2.testonly.json | 16112be486371337c0f4372c41c6223bb69c1b211d56f1824c335c5ba5459238 |
| fixtures/negative-fixtures-manifest.json (+ 11 copy-neg-*.json, 2 request-neg-*.json) | 16c10d9c2f80d737c2a8dfec5f2533bffc9f4bd48ceee3ec6d9be409021ce33a (manifest) |

## What was built

### S80-01 — source/profile extraction
`profiles/upsell-profile.json`: the exact derivation (1–7 retained, original
8–11 excluded by name, original 12 replaced by new §8
"7 Reasons To Commit To Your {inspiring_phrase} Future"), CTA in **every**
section (explicitly overriding the main-page Who/Benefit no-CTA rules),
offer-clear-from-the-start, scarcity/FOMO **only from verified facts**,
per-instance contracts for U1 and U2 (kept separately visible), denylists,
and two recorded conflicts: S80-CONFLICT-01 (owner scarcity instruction vs
no-invention rule → verified-evidence gate) and S80-CONFLICT-02 (no
Standard/Long-Form or Skill 49 char/word bands imported into this profile).
Fixtures: the owner's sample upsell page as a private-authoring fixture
(verbatim-derived; its §1 offer alias "Go VIP" declared in `offer_aliases`),
plus TEST ONLY public U1 and U2 copies with genuinely different outcomes
(content archive vs guided implementation).

### S80-02 — instance request/result schemas
`schemas/upsell-request.schema.json` extends the reference page-request
(every base field required unchanged, `assigned_skill` const 80) and adds:
`instance`, source landing-copy ref, per-instance offer, **disclosure**
(integer `amount_minor`, currency, billing type, recurring terms object,
text, adjacent-to-CTA const), **eligibility** (verified original purchase
with adapter-only verification sources; U2 qualifying purchase enforced by
`allOf` if/then; `bump_only_qualifies` const false;
`client_side_claims_accepted_as_proof` const false — `acceptedU1=true` is
never proof), U2 `entry_context` (`from_upsell_1` | `from_downsell_1`,
null for U1), routes (pending/failed = remain recoverable), payment
capability + fallback, and factual scarcity evidence.
`schemas/upsell-result.schema.json` implements spec §7's
`upsell-result.json`: source hash, approved offer mapping, native action,
8-entry CTA map, disclosure audit, eligibility check, copy validation,
hashes, test outcomes. Example U1/U2 requests and results validate;
client-claim and bump-only U2 requests are rejected.

### S80-03 — eight-section copy validator + rubric
`scripts/validate_upsell_copy.py` (stdlib only; exit 0 pass / 2 violation /
3 fail-closed, Skill 49 convention). Checks: exactly 8 sections in derived
order/keys; CTA mapped in all 8, all bound to the instance's single guarded
action; §8 heading pattern + inspiring phrase; exactly 7 distinct
substantive reasons; three distinct pains; original §§8–11 not
reintroduced; offer named in §1; private-label leak (public output only);
invented testimonial markers (always) and scarcity markers (unless backed
by `verified_scarcity_evidence`); `--compare` U2-vs-U1 distinctness
(renamed-copy detection, whole document and §8 reasons).
`references/substantive-review-rubric.md`: the independent-review rubric
(R1–R10, auto-fails) — structural pass is not emotional quality.

## Verified (evidence in this pass)
- `python3 -m unittest discover -s tests` → **25 tests, OK** (profile facts,
  validator positives/negatives incl. all 11 manifest fixtures with expected
  codes, fail-closed paths, schema valid/invalid cases, 64-case cross-check).
- `python3 scripts/validate_upsell_copy.py --self-test` → **PASS** (6 checks).
- Direct runs: U1 public exit 0; U2 public with `--compare` U1 exit 0;
  owner-sample private exit 0; renamed-U2 exit 2 (`U80-U2-DISTINCT`, 0.99).
- U1 and U2 are separately fixtured, separately schemad (page IDs, offers,
  prices, entry contexts) and separately test-visible throughout.

## Still pending — NOT in this pass, NOT claimed
- **S80-04 / S80-05:** U1 and U2 production adapters (no pages produced).
- **S80-06:** native one-click action/disclosure integration via Skill 6 —
  result fixtures honestly carry `native_action: null`,
  `verified_by: pending_s80_06`, `disclosure_audit: pending_native_binding`.
- **S80-07:** success/decline/error routing execution (schemas encode the
  route contract only; A10/A11/A12 native proof is L3/L4, not run).
- **S80-08:** assets/visuals. **S80-09:** installed purchase tests (L3/L4).
- **S80-10:** independent review and packaging — the example results carry
  `independent_review: false`, `reviewer_session: null`, status `authored`.
- No SKILL.md entrypoint, no repo branch/worktree, no merge/push/publish,
  no GHL or payment calls were made. Skill-number reservation (INT-02) and
  batch approval remain with INTEGRATION / Trevor.

---

## Appendix A — Repair pass for independent-review defects D-01..D-09 (2026-10-15)

**Trigger:** independent review `work/review-S80-01-03.md` (reviewer session
`e25cbf65-f0b0-4b31-8855-0b5411453764`) returned PASS-WITH-DEFECTS for
S80-01/02/03. Per doc 18 §9 this appendix is a NEW attempt record appended
to the original notes; the pre-repair results and hash table above are NOT
edited into passes — the review stands as the record of the defects, and
the hashes below supersede the table above for every changed file.

### What was repaired

- **D-01 (High) — scarcity detection.** The 15-phrase denylist is now backed
  by pattern families in the profile (`validator_patterns.scarcity_claim_patterns`:
  time-bound, availability, exclusivity — e.g. "available only", "once you
  leave, the door closes", "enrollment ends on Friday", "session ends",
  "one-time opportunity"). Any hit with an empty `verified_scarcity_evidence`
  array is `U80-INVENTED-SCARCITY`. The reviewer's off-list fixture now
  fails; adding a verified evidence entry clears exactly that code.
- **D-02 (High) — testimonial detection.** Added endorsement pattern
  families (first-person result claims, collective reports) plus
  attributed-quote detection (quoted span + attribution verb window, or
  quoted first-person result language). Testimonial constructions are
  violations unless the copy carries a non-empty `verified_proof_evidence`
  array naming the supplied proof record — missing proof stays missing.
- **D-03 (High) — CTA binding is no longer self-referential.** The validator
  requires the native guarded ref form (`native-one-click:<id>`; custom
  fetch endpoints and raw charge URLs are rejected outright) AND agreement
  with an externally supplied expectation: the new `--expected-action-ref`
  CLI argument (sourced from the instance request/manifest) or the copy
  document's `action_binding` block naming its external source. The request
  schema gained a matching `action_binding` block, both request fixtures
  carry it, and a test asserts request/copy binding agreement for U1 + U2.
- **D-04 (Medium) — reason distinctness.** Measured first: lexical metrics
  could NOT honestly separate the paraphrase attack from genuine reasons
  (attack containment max 0.091 vs owner sample 0.273), so no lexical
  threshold was faked. Added concept-signature collapse detection
  (profile `reason_concept_groups`): a concept pair restated in ≥5 of 7
  reasons, or ≥5 reasons sharing one identical concept signature, is
  `U80-REASON-DISTINCT`. The attack set restates
  (availability_access, speed_progress) in 7/7 and now fails; all shipped
  valid reason sets and the owner sample pass.
- **D-05 (Medium) — unbound CTAs in body text.** Section body/heading/
  bullets/reasons (everything except the mapped CTA itself) are scanned
  for purchase directives (click/tap-to-buy constructions, "buy instantly",
  "express/separate checkout", checkout link/button phrasing). A hit is
  `U80-UNBOUND-CTA`: every purchase action must be the one mapped CTA.
- **D-06 (High) — schema.** `qualifying_purchase` now REQUIRES
  `verification_source` restricted to the same adapter/native enum as
  `original_purchase`, and `evidence_ref` carries a `not` guard against
  client-side claim text (`acceptedU1=true`, "client-side"/"client_side")
  on BOTH purchase objects. The review's ADV-S1 request (asserted
  `verified_succeeded`, evidence literally "acceptedU1=true (client-side
  URL parameter only)") is rejected on two independent grounds.
- **D-07 (Medium) — schema.** `allOf` if/then ties `entry_context` to the
  qualifying slot: `from_upsell_1` ⇒ slot `upsell_1`, `from_downsell_1`
  ⇒ slot `downsell_1`.
- **D-08 (Medium) — schema.** `allOf` if/then: `billing_type` in
  {recurring, installment, trial} ⇒ `recurring_terms` must be a non-null
  object, as the schema description always promised.
- **D-09 / ADV-S4+S5 (Low) — schema + docs.** Result schema: 
  `independent_review: true` now requires a non-null `reviewer_session`.
  Request schema: the disclosure description now states plainly that
  amount correctness is NOT proven at the L0 schema layer (no approved
  price field exists in the request); it is bound by the approval hash at
  intake and the S80-06 native price read-back.
- **O-1 (Low) — profile.** The owner sample's printed §8 heading carries a
  leading "The" that the profile pattern (following the owner's instruction
  text) omits; the normalisation is now documented in the profile's
  derivation block so a verbatim import is never silently rejected.
- **PASS wording narrowed** (review §3 fairness note): a validator PASS now
  reads "no deterministic violation found" and states it does not prove the
  absence of invented scarcity/proof or the existence of a native binding;
  independent substantive review (rubric R4/R10) and S80-06 evidence remain
  load-bearing. (O-2, the bump-only rejection surfacing as a type error,
  is unchanged behaviour with the same correct outcome; noted, not hidden.)

### Regression fixtures (copied from the review, attribution in each file)

`fixtures/copy-regression-a1-near-duplicate-reasons.json` (D-04),
`a2-self-declared-action` (D-03), `a2b-embedded-unbound-cta` (D-05),
`a3-offlist-scarcity` (D-01), `a4-offlist-testimonial` (D-02), indexed by
`fixtures/regression-fixtures-manifest.json`. New schema negatives:
`request-neg-u2-qualifying-no-source.json`,
`request-neg-u2-qualifying-client-evidence.json`,
`request-neg-u2-entry-context-mismatch.json`,
`request-neg-recurring-terms-null.json`, `result-neg-self-review.json`.

### Verification evidence (this pass, exact)

- `python3 -m unittest discover -s tests` → **39 tests, OK** (the 25
  pre-existing tests all still pass; 14 new: ReviewRegressionTests ×7,
  SchemaRepairTests ×7 — one pre-existing inline U2 fixture construction
  was updated to supply the now-required `verification_source`).
- `python3 scripts/validate_upsell_copy.py --self-test` → **PASS**,
  11/11 (6 original + 5 review regressions, each with its expected code).
- Direct CLI: valid U1 / U2-vs-U1 / owner sample exit 0; each copied
  regression fixture AND each original in /tmp/s80adv/ exits 2 with its
  expected code (U80-REASON-DISTINCT / U80-CTA-BINDING / U80-UNBOUND-CTA /
  U80-INVENTED-SCARCITY / U80-INVENTED-TESTIMONIAL); wrong
  `--expected-action-ref` exits 2, correct ref exits 0.

### Changed-file hashes (SHA-256, post-repair)

| File | SHA-256 |
|---|---|
| profiles/upsell-profile.json (now v1.1.0) | 2b48357f22147de8902f0e2bc24903c479136bbf2e2f7407cca7e9f861907141 |
| schemas/upsell-request.schema.json | d723a66ada0bc02b0ed725b2799e21c1f6093a1da3deb78fb9689860d35520bf |
| schemas/upsell-result.schema.json | 8a4c23924dc4732643b6e3e09cfb344bac6aad4ebaad0ac89e34890c852a1a36 |
| scripts/validate_upsell_copy.py | b250f325c36a2667ac2c29b3b4f362815ff859d1fcc31bd76264f4207234ada7 |
| tests/test_validate_upsell_copy.py | 6285fa8a1427cecfb22e5e9148138776427c8b0e1e77a03ea1ac0c0931c8152d |
| fixtures/regression-fixtures-manifest.json | f801aac0d0c6271993f81c5a147ad810cf5e41af6c8086089d21a92fef0c53ba |
| fixtures/request-upsell1.testonly.json | 629c870f698b435c071b152036acf69e703d1f89c2621c19f2d7ea725ac1d80c |
| fixtures/request-upsell2.testonly.json | 3a0170592193e7f58619b76e4239da9f664d4aa094b20a04adcc5a553e776fdd |
| fixtures/copy-upsell1-public.valid.json | ad2eaff4f90d1e7c201aed9c713e46de3cf7d213257717eb504db421c74cab13 |
| fixtures/copy-upsell2-public.valid.json | 56735f9a571af1226443777cc22464e5aa77a24e7cd2db47df02490f43734530 |
| fixtures/copy-owner-sample-upsell1.private.json | 5f1fde26b84bcef188b2948af548f0a7259e527c687d75f22cefedf13ddb7582 |

### Honest residual limits — NOT repaired, not claimed

- Pattern families raise detection coverage; they cannot prove the absence
  of invented scarcity or proof. A paraphrase engineered around BOTH the
  denylists and the families would still escape the deterministic gate —
  that is exactly why the rubric's independent review remains load-bearing,
  and the PASS wording now says so.
- Concept-signature collapse catches the reviewer's attack class
  (single-proposition restatement). It is a concept proxy, not semantic
  understanding: a set of seven reasons that are topically varied yet
  substantively empty would still need the human reviewer (rubric R7).
- The D-03 binding check verifies the ref's FORM and its agreement with an
  externally supplied expectation. It does not prove a native action exists
  behind the ref — that remains S80-06 / Skill 6 evidence, still pending.
- No defect was left unrepaired from D-01..D-08; D-09's two observations
  were handled as documented above (schema conditional + explicit L0
  amount disclaimer) rather than by inventing an in-schema price authority.

---

## Appendix B — R2 repair pass (re-review defects R2-01..R2-07), 2026-10-15

Appended after the independent re-review (`work/review-S80-01-03-rereview.md`)
verified D-01..D-08 CLOSED and raised second-order defects R2-01..R2-07.
The original build record above and Appendix A are unchanged. Scope was
`80-signature-upsell/` only; `work/adapters/` was not edited (impact assessed
read-only, below). No check was weakened: every original negative fixture
still exits 2 with its exact manifest code, and the shipped valid fixtures
still exit 0 (now with an external binding expectation supplied — see R2-01
harness conformance note).

## R2-01 (Medium) — self-authored binding expectation: REPAIRED

- The copy document's own `accept_action_ref` AND its in-document
  `action_binding` block are now treated as claims. The block is checked for
  internal consistency only; it can no longer serve as the trusted
  expectation. A binding PASS requires the expectation from OUTSIDE the copy
  document: `--expected-action-ref` (caller-supplied, wins) or the new
  `--binding-manifest` file, whose entries are keyed by page_id/offer_id/
  copy_id and must each carry their own `expected_action_ref` + `source_ref`
  (instance request id / S49 route-graph reference). A manifest with no
  matching entry is a `U80-CTA-BINDING` violation; a malformed manifest
  fails closed (exit 3).
- With neither external source, `binding_verification` is `unverified`: in
  the default (production) mode this is violation `U80-CTA-BINDING-UNVERIFIED`
  (exit 2). `--allow-unverified-binding` exists for explicit local fixture
  work only: it prints a LIMITATION line and the PASS output records
  `binding_verification=unverified`; it is never production binding evidence.
  Validator output always reports the binding status and, when verified, the
  expectation source. `validate_copy_report()` exposes the status
  programmatically; `validate_copy()` remains as a violations-only wrapper.
- New fixture `fixtures/binding-manifest.testonly.json` (TEST ONLY stand-in
  for the S49 graph + instance requests). Rebuilt attack fixture
  `fixtures/copy-r2-self-authored-binding.json` (copy invents
  `native-one-click:INVENTED-BY-COPY-AUTHOR` and self-"expects" it): now
  exits 2 with U80-CTA-BINDING-UNVERIFIED under the plain CLI, and with
  U80-CTA-BINDING when any real external expectation is supplied.
- Harness conformance (mirrors Appendix A's one test-data update): the three
  shipped positive CLI tests now supply the external expectation
  (`--expected-action-ref` for U1 and the owner sample, `--binding-manifest`
  for U2) and additionally assert `binding_verification=verified_external`
  in the output. Their pass assertions (exit 0, honesty wording) are
  unchanged. Bare-CLI validation of a valid copy now fails closed on the
  binding check by design; that is the repair, not a regression.

## R2-07 (Low) — action_binding required at the schema layer: REPAIRED

- `schemas/upsell-request.schema.json`: `action_binding` added to the
  top-level `required` list (both shipped request fixtures already carry it;
  their files are unchanged). A request without it is now schema-invalid, so
  the expectation chain cannot be silently absent upstream.

## R2-02 (Medium) — paraphrased unbound buy paths: REPAIRED

- Unbound-CTA detection broadened in the profile family and scanned per
  body-text segment (lines, then sentences): new patterns
  `complete_your_purchase`, `payment_page_purchase_direction` (visit/head/go
  … payment|checkout|order page), `claim_yours_off_page`, and
  `head_to_checkout_direction` ("head to checkout to get yours"). Rebuilt
  attack fixture `fixtures/copy-r2-unbound-cta-paraphrase.json` ("visit the
  payment page and complete your purchase there") now exits 2 with
  U80-UNBOUND-CTA.
- Decline/continuation copy is modelled explicitly
  (`validator_patterns.decline_continuation_allowlist`): a segment with
  decline markers (no thanks / continue without / skip / keep-my-current)
  and NO purchase verb is exempt, because the decline path routes through
  the declared decline action. A segment mixing decline wording WITH a
  purchase direction is not exempt (covered by test). Shipped fixtures stay
  green (58-test suite).

## R2-06 (Medium) — self-asserted evidence at both layers: REPAIRED

- Validator: `verified_scarcity_evidence` / `verified_proof_evidence`
  entries count only when `source_ref` is a structured external reference
  (prefixed `ledger:`/`provider-event:`/`s44:`/`native:`/`catalog:`, an
  http(s) URL, or a separator-structured record id) and neither fact nor
  source_ref hits the assertion denylist ("says so", "trust me", "this
  document", …). Invalid entries raise `U80-EVIDENCE-REF` and clear NOTHING
  (the scarcity/testimonial codes still fire). Rebuilt attack fixture
  `fixtures/copy-r2-self-asserted-evidence.json` now exits 2 with
  U80-EVIDENCE-REF + U80-INVENTED-SCARCITY.
- Schema: `evidence_ref` on `original_purchase` and `qualifying_purchase`
  (including the allOf upsell_2 branch) gained the same structured pattern;
  `provider_event_ref` gained the pattern AND the client-claim `not` guard
  (previously unguarded — "acceptedU1=true" validated there). Bare
  assertions "verified" / "trust me" are now schema-invalid.
- Residual limit, stated plainly (also in the profile): the deterministic
  layer can require the STRUCTURE of an external reference; it cannot prove
  the referenced record exists or says what the entry claims. Truth of the
  referenced record is proven at S80-06 native-binding / S44 event
  read-back, not here.

## R2-03 / R2-04 (Low) — morphology folds: REPAIRED (fixtures stay green)

- Scarcity: `door_closes` widened to `\bdoors? closes?\b`; new patterns
  `enrolment_shuts_or_closes`, `round_or_cohort_fills`, `price_rises_when_full`,
  `will_not_be_waiting`. Rebuilt fixture
  `fixtures/copy-r2-scarcity-morphology.json` exits 2 with
  U80-INVENTED-SCARCITY.
- Testimonial: new collective-result family `collective_result_claim`
  (collective noun within 90 chars of a result verb). Rebuilt fixture
  `fixtures/copy-r2-testimonial-collective.json` exits 2 with
  U80-INVENTED-TESTIMONIAL.

## R2-05 (Low) — concept rotation: DOCUMENTED RESIDUAL (not repaired)

Reason restatements that rotate concept pairings (no repeated pair and no
shared signature at the collapse thresholds) remain undetectable by the
deterministic concept-signature method, exactly as the re-review recorded.
This stays a declared residual limit of the deterministic layer; catching
semantic emptiness across rotated phrasings is rubric R7 substantive-review
work (and, at the limit, model judgment), not a pattern problem. No test was
adjusted to hide this: the limit is stated here and in the profile note.

## Verification (this repair pass, firsthand)

- `tests/test_validate_upsell_copy.py`: **58 tests OK** (39 pre-existing —
  all still passing — plus 19 new: R2RepairTests 15, R2SchemaTests 4).
- Validator self-test extended 11 → **16 checks, PASS** (U2 validated via
  the binding manifest; five R2 regression entries assert their named
  codes).
- All five rebuilt R2 attack fixtures exit 2 with their named codes under
  the plain CLI; the invented-ref copy under `--allow-unverified-binding`
  exits 0 but reports `binding_verification=unverified` with the LIMITATION
  line — it is never reported as verified.
- Valid U1/U2/owner-sample fixtures exit 0 with an external expectation and
  report `binding_verification=verified_external` with its source.
- Note: the re-reviewer's originals in `/tmp/s80rereview/` no longer exist
  (ephemeral /tmp); the shipped `fixtures/copy-r2-*.json` are byte copies
  made from those files at the start of this repair pass, each carrying a
  `regression_fixture` provenance field citing the re-review.
- Adapters impact (READ-ONLY assessment for the lead; no adapters files
  edited): the adapters suite still passes **66/66** against the repaired
  profile/schema/validator; both adapters request fixtures
  (`fixtures/request-upsell2-from-upsell1.testonly.json`,
  `request-upsell2-already-owned.testonly.json`) validate against the new
  schema and already carry `action_binding`; all adapters evidence refs are
  hyphen-structured (`TEST-ONLY-*-ledger-entry`) and pass the new pattern;
  no adapters file embeds the profile version or the pre-repair profile
  hash, and `adapter_common.py` reads the profile at runtime. Watch items
  for the lead's conformance pass: (1) re-run `produce.py` and diff bundles
  as a formality, since the sibling validator/profile changed even though
  no bundle field embeds them; (2) `adapter_common.py`'s request builder
  already emits `action_binding` (line ~515) — any future request
  construction must keep it, as the schema now requires it; (3) bundle
  metadata `evidence_ref` values that are file paths (e.g.
  `tests/test_adapters_upsell1.py`) are not schema-validated eligibility
  fields and are unaffected.

## Post-R2-repair hashes (SHA-256)

- profiles/upsell-profile.json (v1.2.0): b526aacb671c86dbd27511e82e1188e22f75db4dc9b97a27d89d24e4874ab27a
- scripts/validate_upsell_copy.py: 2a94326965b2df3457e8f684c9561e92025f56850080c015e6f7483f29f8b7c7
- schemas/upsell-request.schema.json: bd5bcea178501ebd263af8abc718b849bd113f040ea9d1fba81eb4d8508758a0
- schemas/upsell-result.schema.json: 8a4c23924dc4732643b6e3e09cfb344bac6aad4ebaad0ac89e34890c852a1a36 (unchanged)
- tests/test_validate_upsell_copy.py: c05d337f00967fc5a808db8b3b545d9085ba427a2b2c868b27f5a260ae7d105d
- fixtures/binding-manifest.testonly.json (new): 4cb86e84f6aa75ab099e88fee41a4dee252c866b48977dfdc37c038e2e613f4f
- fixtures/copy-r2-self-authored-binding.json (new): aff41a7e526a5f25b3711dfc06fb82f2807552d98b2f32ff8467adf81eed3c23
- fixtures/copy-r2-unbound-cta-paraphrase.json (new): c255465a8138d66f5ff56ccf7a0bb44b56d4c7548a518cc6ff78f49802d14913
- fixtures/copy-r2-scarcity-morphology.json (new): 22b409fbe40ca7f478e6a4f6ea8769993a0a02e6a14f0c84655ea0d74298da59
- fixtures/copy-r2-testimonial-collective.json (new): 8cf5280bbfe3b4da37548b6e8636de78a62cbee7016651ed68bebe25e0a5a1d2
- fixtures/copy-r2-self-asserted-evidence.json (new): ac257aadc07e5a5037dbedb782f51f96e99f92b0bd5daa460a223565702a8eb5
- fixtures/copy-upsell1-public.valid.json: ad2eaff4f90d1e7c201aed9c713e46de3cf7d213257717eb504db421c74cab13 (unchanged)
- fixtures/copy-upsell2-public.valid.json: 56735f9a571af1226443777cc22464e5aa77a24e7cd2db47df02490f43734530 (unchanged)
- fixtures/request-upsell1.testonly.json: 629c870f698b435c071b152036acf69e703d1f89c2621c19f2d7ea725ac1d80c (unchanged)
- fixtures/request-upsell2.testonly.json: 3a0170592193e7f58619b76e4239da9f664d4aa094b20a04adcc5a553e776fdd (unchanged)

Open after this pass (unchanged from Appendix A): independent re-review of
these R2 repairs (reviewer is never the author), S80-06 native binding,
S80-09 installed purchase tests, S80-10 packaging. These repairs raise the
deterministic floor; they are not production evidence and do not change the
reported build percent on their own.

---

## Appendix C — R3 repair pass (closing re-review defects R3-01, R3-02, R3-04; R3-03/R3-05 folds), 2026-10-15

Appended after the closing independent re-review
(`work/review-S80-R2-rereview.md`, reviewer session
`06e6b690-f02d-4f84-a94c-3ec58c12740e`) verified R2-01..R2-07 CLOSED and
raised third-order defects R3-01 (Medium), R3-02 (Medium), R3-04 (Low) and
pattern edges R3-03/R3-05 (Low). The original build record, Appendix A and
Appendix B are unchanged. Scope was `80-signature-upsell/` only;
`work/adapters/` was not edited (impact assessed read-only, below). No
check was weakened: all 58 pre-existing tests pass unchanged in assertion,
and the shipped valid fixtures still exit 0 with an external binding
expectation and report `verified_external`.

## R3-01 (Medium) — manifest provenance unauthenticated: REPAIRED

- R2-01 moved the trust anchor out of the copy document into a
  caller-supplied manifest file, but the validator authenticated nothing
  about that file: any manifest present on disk was trusted, and an
  entry's `source_ref` was checked only for non-emptiness. The
  re-reviewer's self-authored manifest (expecting the copy's invented
  ref, `source_ref: "my own say-so, not a manifest"`) produced exit 0
  with `binding_verification=verified_external` (their FA-1).
- Repair: `lookup_binding_manifest` now holds the matching entry's
  `source_ref` to the SAME structured-external-reference standard as
  evidence refs, via a shared `source_ref_problem()` helper (extracted
  from `evidence_entry_problems`, which now delegates to it): the profile
  pattern plus the assertion denylist. The admitted prefix set gains
  `request:`/`graph:` (validator-side, including the code fallback) so a
  genuine manifest can cite the S49 instance request / route graph it
  was produced from. A matching entry whose `source_ref` is prose
  self-assertion, a denylisted assertion in structured clothing
  (`request:my own say-so`), or unstructured text rejects the manifest
  with `U80-CTA-BINDING` — the same violation channel as a missing
  entry/source (exit 2); a top-level malformed manifest still fails
  closed (exit 3).
- The shipped `fixtures/binding-manifest.testonly.json` entries now carry
  structured source_refs: `request:TEST-REQ-U1/action_binding`,
  `request:TEST-REQ-U2/action_binding`,
  `graph:TEST-ROUTE-GRAPH/sample-upsell-1`, and its source note says why.
  New attack fixture `fixtures/binding-manifest-r3-self-authored.testonly.json`
  rebuilds the re-reviewer's FA-1 construction verbatim; paired with
  `fixtures/copy-r2-self-authored-binding.json` it now exits 2 with
  U80-CTA-BINDING and reports `binding_verification=unverified`.
- **Residual, stated plainly (not oversold):** structure is enforced; a
  forger can still mint structured strings (`ledger:INVENTED-ENTRY-999`
  remains indistinguishable from a real entry at this layer — the
  re-review's FA-4). The truth anchor for binding remains the S49 graph /
  S80-06 native read-back, not this layer. The repair removes the
  unauthenticated-prose hole and forces every manifest to cite a
  well-formed external record; it does not and cannot prove that record
  exists or that it issued the manifest.

## R3-02 (Medium) — decline-exemption smuggling: REPAIRED

- The R2-02 exemption tested a decline segment only against
  `purchase_verb_regex` (buy/purchase/checkout/order/pay/claim yours/get
  yours/complete your purchase), which is narrower than the unbound-CTA
  families it exempted from: "No thanks is available, or tap the
  enrolment link on the next screen to activate the upgrade instantly"
  trips `tap_to_buy` yet was exempted (no listed verb); the identical
  sentence without the decline prefix failed U80-UNBOUND-CTA (the
  re-reviewer's control, their FA-2).
- Repair: the scan now collects ALL pattern hits per segment first. A
  decline segment is exempt ONLY when (a) it matches the decline
  allowlist, (b) it contains no purchase verb, AND (c) every hit belongs
  to `decline_continuation_allowlist.descriptive_direction_pattern_ids`
  — currently only `payment_page_purchase_direction`, the one family
  whose hit can be a descriptive mention rather than a directive ("the
  payment page is only for buyers who want the extra" — the re-reviewer's
  legitimate-decline control, still zero violations). Any
  directive-family hit (tap/click-to-buy, complete-your-purchase,
  head-to-checkout, the R3-03 families, …) defeats the exemption
  regardless of decline wording; so does a purchase verb beside even a
  descriptive hit ("visit the payment page and pay there instead" is not
  exempt). New attack fixture `fixtures/copy-r3-decline-smuggled-cta.json`
  (the re-reviewer's sentence in §2) now exits 2 with U80-UNBOUND-CTA;
  regression tests cover the smuggle, the no-prefix control, the
  legitimate mention, and the decline+direction+verb case (both
  directions, as required).

## R3-04 (Low) — unpatterned request evidence fields: REPAIRED + full enumeration

- `schemas/upsell-request.schema.json`: `factual_scarcity_evidence[].source_ref`
  and `payment_capability.evidence_ref` (string branch of the nullable
  field) now carry the same structured pattern as the purchase evidence
  fields (R2-06). "trust me" / "verified" are invalid in both; structured
  refs and (for payment_capability) null stay valid; the shipped request
  fixtures are unchanged and still valid.
- Enumeration of every other evidence/reference-bearing field in both
  schemas, with disposition:
  - Request `eligibility.original_purchase.evidence_ref` /
    `provider_event_ref` and `eligibility.qualifying_purchase.evidence_ref`
    / `provider_event_ref` — already patterned plus the client-claim
    `not` guard (R2-06). No change.
  - Request `action_binding.source_ref` — NOT patterned, deliberately: it
    is the request-side declaration whose agreement with the
    copy/manifest is checked at validation time, and its shipped values
    are provenance labels in file-reference form
    (`fixtures/…#action_binding` in this room;
    `80-signature-upsell/fixtures/…#action_binding` in the adapters'
    requests). The structured pattern would reject those legitimate
    values (dots in file names fail the separator-id branch) and break
    cross-room fixtures this room does not own. Patterning it is an
    S49-intake / S80-10 packaging decision — recorded here rather than
    silently skipped.
  - Request identity/intake references (`approval_ref`, `approval_hash`,
    `brand_ref`, `brand_hash`, `route_graph_ref`, `route_graph_hash`,
    `input_hash`, `source_landing_copy_ref`, `offer.native_product_id`,
    `disclosure.native_price_id`) — reference/identifier fields, not
    evidence claims; minLength-governed. Their truth is intake /
    approval-hash and S80-06 read-back territory, the standing note the
    disclosure block already carries. No change.
  - Result `test_outcomes[].evidence_ref` — NOT patterned, deliberately:
    at L0/L1 its values are LOCAL evidence artifact paths
    (`tests/test_validate_upsell_copy.py` in the shipped fixtures), a
    different semantic from an external verification record; the
    structured-external pattern would reject the honest local form. If
    L3+ outcomes begin citing external records, this field should be
    split or patterned then — a named follow-up, not a hidden gap.
  - Result `native_action.action_id` / `settings_ref` /
    `binding_screenshot_ref` and `native_bindings_ref` — S80-06 evidence
    slots, null until Skill 6 evidence exists (honest pending state); no
    pattern imposed on fields whose legitimate values do not exist yet.
    `hashes.*` / `source_hash` / `artifacts[].sha256` already carry the
    sha256 pattern.

## R3-03 / R3-05 (Low) — pattern edges: FOLDED where cheap, one documented residual

- New unbound-CTA families in the profile (profile 1.2.0 → 1.3.0); all
  three re-review constructions are rebuilt in
  `fixtures/copy-r3-unbound-buy-paths.json` (one per section) and each now
  fails U80-UNBOUND-CTA: `qr_code_buy_path` ("Scan the QR code … to pay
  for the upgrade instantly"), `settle_up_buy_path` ("Settle up on the
  payment screen to activate the upgrade…"), `payment_screen_path` (the
  R2-02 direction families named only the payment/checkout/order *page*;
  the *screen* noun is now covered verb-first and verb-after),
  `email_link_buy_path` ("Use the link in your confirmation email to pay
  for the upgrade on another screen").
- Scarcity fold (R3-05b): `pause_or_halt_enrolments` — "We pause new
  enrolments after this weekend and reopen only when a place frees up"
  (rebuilt in `fixtures/copy-r3-scarcity-pause-enrolments.json`) now
  fails U80-INVENTED-SCARCITY. A pause/halt on enrolment is a scarcity
  claim (implied deadline, reopening uncertainty) and needs verified
  evidence like any other.
- **Documented residual (R3-05a, NOT pattern-chased):** the
  named-individual transformation story — "Meet Jordan, who went from
  two clients to twenty in a single quarter after joining the
  programme" — still escapes the deterministic families, and no pattern
  was added for it. Reason: its surface form (a named person, a
  before/after result, no quote, no collective noun, no denylisted
  name) is identical to a LAWFUL supplied success story; the only thing
  that makes it a violation is the absence of a `verified_proof_evidence`
  record — a judgment about the proof file, not about the sentence. That
  is rubric R4/R10 substantive-review territory, and the profile's
  `validator_patterns` note now says so explicitly. Pattern-chasing it
  (e.g. banning "meet <name>") would false-positive legitimate
  introductions and still miss the next name. It stays a declared,
  measured residual — not a silent gap.
- R2-05 (concept rotation) remains a documented residual, unchanged.

## Verification (this repair pass, firsthand)

- `python3 -m unittest discover -s tests` → **74 tests OK** (58
  pre-existing, all still passing, plus 16 new: R3RepairTests ×12,
  R3SchemaTests ×4).
- `python3 scripts/validate_upsell_copy.py --self-test` → **PASS, 20/20**
  (16 prior + 4 R3 entries asserting their named codes:
  U80-CTA-BINDING for the self-authored manifest, U80-UNBOUND-CTA for
  the smuggle and the buy-paths fixture, U80-INVENTED-SCARCITY for the
  pause-enrolments fixture).
- Direct CLI: valid U1 exit 0 via `--expected-action-ref` and via the
  shipped manifest (`binding_verification=verified_external`, source
  `request:TEST-REQ-U1/action_binding`); valid U2 with `--compare` +
  shipped manifest exit 0 `verified_external`; owner sample exit 0. The
  FA-1 attack pairing exits 2. Each R3-03 sentence individually and the
  combined shipped fixture exit 2 U80-UNBOUND-CTA. The R3-02 smuggle and
  its no-prefix control exit 2; the legitimate decline control validates
  with zero violations.
- Adapters impact (READ-ONLY assessment; no adapters files edited): the
  adapters suite still passes **66/66** against the repaired
  profile/schema/validator, and both adapters request fixtures
  (`fixtures/request-upsell2-from-upsell1.testonly.json`,
  `request-upsell2-already-owned.testonly.json`) validate against the
  R3-04-tightened request schema with **0 errors** — their
  `factual_scarcity_evidence` is empty and `payment_capability.evidence_ref`
  is null (the two newly patterned fields), and their
  `action_binding.source_ref` file-path values are unaffected (see the
  R3-04 enumeration). No adapters fixture impact to report.
- Profile version 1.2.0 → 1.3.0 (pattern families, decline model,
  evidence standard). The result schema was not touched (hash unchanged
  from Appendix B). No shipped valid copy or request fixture changed.

## Post-R3-repair hashes (SHA-256)

- profiles/upsell-profile.json (v1.3.0): 1002c372ec4e6702904bdaf7a634050d9b8199044fe6bec0a63dab5c080598e4
- scripts/validate_upsell_copy.py: d9be291a314aa4ed680b399e191bc3ebd1491984b022833a3b617671c58d2d89
- schemas/upsell-request.schema.json: db11ad6495feae69ac486411a5f164c33bccfae48f510b252e558030f7409fd9
- schemas/upsell-result.schema.json: 8a4c23924dc4732643b6e3e09cfb344bac6aad4ebaad0ac89e34890c852a1a36 (unchanged)
- tests/test_validate_upsell_copy.py: fbbc2d372ba01afba29787c546312db12a7c6d8f272755b7ee79e90e073b4be0
- fixtures/binding-manifest.testonly.json: f8aca3f8ea0809d094d097c0c160e28c6bfbcaa82b03cb8ecc668922143e2d28
- fixtures/binding-manifest-r3-self-authored.testonly.json (new): 9b2c68451ad2cf3228a5f99c998f2cbebdc7b0ee69154a7011b9cae168583659
- fixtures/copy-r3-decline-smuggled-cta.json (new): 34fc8ee8a138400733d18fd49e2f0387bd9a8c132157fad45497435297c1ee3e
- fixtures/copy-r3-unbound-buy-paths.json (new): 99171cfc86b1e9daf8b89b5eefc0e6de62db10271b274c4d5b136282d32e87a1
- fixtures/copy-r3-scarcity-pause-enrolments.json (new): 5a076a03443bf79934f9aa330cdec75e1e14538cdf18fe78a0d2816028b7e184
- fixtures/copy-upsell1-public.valid.json: ad2eaff4f90d1e7c201aed9c713e46de3cf7d213257717eb504db421c74cab13 (unchanged)
- fixtures/copy-upsell2-public.valid.json: 56735f9a571af1226443777cc22464e5aa77a24e7cd2db47df02490f43734530 (unchanged)
- fixtures/request-upsell1.testonly.json: 629c870f698b435c071b152036acf69e703d1f89c2621c19f2d7ea725ac1d80c (unchanged)
- fixtures/request-upsell2.testonly.json: 3a0170592193e7f58619b76e4239da9f664d4aa094b20a04adcc5a553e776fdd (unchanged)

Open after this pass (unchanged in kind): independent re-review of these
R3 repairs (reviewer is never the author), S80-06 native binding, S80-09
installed purchase tests, S80-10 packaging. Per the closing re-review's
recommendation, R3-01 and R3-02 were the named pre-production repairs;
both are now repaired at the deterministic layer, subject to re-review.
These repairs raise the deterministic floor; they are not production
evidence and do not change the reported build percent on their own.

---

## Appendix D — R4 fold pass (closing R3 re-review defects R4-01, R4-02; both Low), 2026-10-15

Appended after the closing independent re-review of the R3 repairs
(`work/review-S80-R3-rereview.md`, reviewer session
`51f4357c-2e5a-4384-a0aa-eac20e87ceeb`) verified R3-01, R3-02 and R3-04
CLOSED (R3-02 with a measured narrowing), R3-03 closed as specified, and
the R3-05 scarcity fold holding for its named constructions, and raised
fourth-order defects R4-01..R4-04 — all Low, explicitly judged by the
reviewer as NOT production blockers, with R4-01 and R4-02 named as the
cheap folds worth doing before production copy is trusted on a
validator PASS. This pass fixes ONLY R4-01 and R4-02. The original
build record and Appendices A, B and C are unchanged. Scope was
`80-signature-upsell/` only; `work/adapters/` was not edited (verified
read-only, below). No check was weakened: all 74 pre-existing tests
pass unchanged in assertion, and the shipped valid fixtures still exit
0 with an external binding expectation and report `verified_external`.
Both escapes were reproduced before repair (the reviewer's four
sentences appended to the valid U1 fixture produced zero violations)
and verified closed after.

## R4-01 (Low) — subject-first scarcity inversions escaped the folds: REPAIRED

- The R3-05 fold `pause_or_halt_enrolments` was verb-first only
  (`pause/halt/suspend … enrolments`), so inverting subject and verb —
  a trivial rewording of the very sentence the fold was built from —
  escaped: "Admissions halt on Sunday and reopen in the spring." and
  "Enrolment pauses after this weekend while we review the waiting
  list." both validated with zero violations (the re-reviewer's FA-A).
- Repair (profile only): `pause_or_halt_enrolments` now carries a
  subject-first alternation — enrolment noun + verb, including the
  passive forms `is/are paused|suspended|halted`. Sibling inversions
  folded alongside where cheap, each as its own named family so a hit
  names the construction it caught: `enrolment_closes_subject_first`
  ("Admissions close at the end of the month"; the mirror of the
  verb-first `enrolment_shuts_or_closes`), `capacity_fills_subject_first`
  ("Places are filling quickly this week", "spots are running out"; the
  mirror of `round_or_cohort_fills`), and `price_rises_subject_first`
  (articled and progressive forms: "The price is going up…"; the base
  family was already subject-anchored for the bare subject).
- One deliberate exclusion, recorded rather than silent: `intake` is
  NOT a scarcity subject noun, although "intake closes/pauses" reads as
  scarcity in isolation. Intake is the governed name of this build's
  own intake process (S49 intake); copy describing that process ("Our
  intake pauses over the public holiday…") is a process statement, and
  a regression test pins it clean. A genuinely scarcity-flavoured
  intake claim remains rubric territory.
- Attack fixture `fixtures/copy-r4-scarcity-subject-first.json` rebuilds
  both FA-A sentences verbatim (§1, §2) plus the passive form (§3); it
  now exits 2 with U80-INVENTED-SCARCITY only (three hits, one per
  section). The fold widens detection, not the evidence standard: a
  subject-first claim backed by a structured verified evidence entry
  clears exactly like the verb-first forms (regression test), and the
  R3 verb-first fixture is byte-unchanged and still fails.

## R4-02 (Low) — decline exemption shielded imperative directions: REPAIRED

- R3-02 narrowed the decline exemption to segments whose every pattern
  hit is the descriptive direction family, but that family's regex
  cannot distinguish a descriptive MENTION of the payment page from a
  true IMPERATIVE spoken through the same family, so "No thanks is an
  option; go to the payment page." and "No thanks, keep my current
  plan; head to the payment page whenever you are ready." were exempted
  with zero violations (the re-reviewer's FA-B / FA-G). Bounded harm,
  as the reviewer measured: the direction half escaped, never a full
  buy path.
- Repair: the exemption gains condition (d) — the segment must contain
  NO imperative direction. The profile's decline model carries a new
  `imperative_direction_regex` (go to / head to / visit / navigate to /
  proceed to / continue to / click through to, or bare go / proceed /
  continue / follow, + a payment/checkout/order page, screen or step,
  plus the bare "go to checkout" form), and the validator voids the
  exemption on any match, regardless of the segment's other content.
  The exemption now covers descriptive mentions only, never directions,
  which is the split the reviewer recommended. The legitimate decline
  control stays green by construction: its "go" is "go BACK" — followed
  by no destination noun, so it is not an imperative direction — and
  its payment-page hit is a descriptive mention ("the payment page is
  only for buyers who want the extra"). The validator compiles the new
  field optionally, so a pre-R4 profile keeps the R3-02 exemption shape
  rather than failing closed on a missing key.
- Attack fixture `fixtures/copy-r4-decline-shielded-imperative.json`
  rebuilds FA-B (§6) and FA-G (§7) verbatim; it now exits 2 with
  U80-UNBOUND-CTA only. Regression tests cover both reviewer sentences,
  four imperative variants (visit / proceed to / navigate to / payment
  screen), the legitimate descriptive control, a direction-free decline
  sentence, and the no-decline imperative control (still rejected).

## R4-03 / R4-04 — NOT repaired in this pass, by design (declared residuals)

Per the task scope and the reviewer's own judgment, neither is
pattern-chased here:

- **R4-03** (press/grab buy verbs; "freeze" scarcity): further edges of
  the standing paraphrase classes. Each new verb folded in invites the
  next synonym; the class is open by nature and is carried by the
  independent substantive review (rubric R4/R10), as the profile's
  pattern note has declared since the D pass. The new edges are
  measured and named in the re-review; they are not silent.
- **R4-04** (fabricated quote engineered around the attributed-quote
  window / attribution-verb list): the quote-form sibling of the
  R3-05a named-story residual. The violation is the missing
  `verified_proof_evidence` record, not the sentence's surface; a
  deterministic window/verb list can be widened but never completed,
  and widening it here would still leave the class open while risking
  false positives on lawful quoted copy. Rubric R4/R10 territory.

## Closing statement — remaining declared residuals after this pass

With R4-01 and R4-02 folded, the deterministic layer's known limits
are exactly the declared residuals, each stated in the artifacts
themselves (profile notes, PASS wording, prior appendices) and none
disguised as coverage:

1. **Structure is not truth** (binding and evidence): the validator
   enforces the FORM of an external reference — structured, sourced
   from outside the copy document, free of bare self-assertion — and
   cannot prove the referenced record exists, says what is claimed, or
   issued the manifest (a forger can mint structured strings; the
   re-reviews' FA-4 / FA-E class). Truth of the binding and of purchase
   evidence is proven at S49 graph read-back, S80-06 native-binding
   evidence, and S44 event read-back — none of which exists yet, and
   none of which this layer simulates.
2. **Substantive story/proof judgment** (rubric R4/R10): a fabricated
   named-individual story (R3-05a) or engineered quote (R4-04) is
   surface-identical to a lawful supplied one; the violation is the
   missing proof record. The deterministic layer flags the
   constructions it can name and gates them on
   `verified_proof_evidence`; judging the proof file is the
   independent substantive reviewer's burden, permanently.
3. **Concept rotation** (R2-05): seven reasons restating one idea
   through rotating concept pairs defeat pair/signature thresholds by
   construction (measured in the D/R2 passes); rubric R7 carries it.
4. **Paraphrase edges** (R4-03, and the class generally): press/grab
   buy verbs, "freeze" scarcity, and the next synonym after them.
   Pattern families raise coverage; they cannot prove the absence of
   an alternate buy path or a scarcity claim in arbitrary prose.

A validator PASS therefore continues to mean exactly what its printed
wording says: no deterministic violation found — never proof that
scarcity/proof are absent, and never proof that the native binding
exists.

## Verification (this fold pass, firsthand)

- Escapes reproduced pre-repair: the reviewer's FA-A(a), FA-A(b),
  FA-B and FA-G sentences each produced zero violations against
  profile 1.3.0; post-repair each produces its named code
  (U80-INVENTED-SCARCITY / U80-UNBOUND-CTA) and the descriptive decline
  control still produces none.
- `python3 -m unittest discover -s tests` → **85 tests OK** (74
  pre-existing, all still passing, plus 11 new R4RepairTests covering
  both shipped fixtures, both verbatim reviewer construction sets,
  subject-first and imperative variants, the evidence-clears fold, the
  intake exclusion, and both controls).
- `python3 scripts/validate_upsell_copy.py --self-test` → **PASS,
  22/22** (20 prior + 2 R4 entries asserting their named codes).
- Direct CLI: valid U1 exit 0 via `--expected-action-ref` and via the
  shipped manifest (`verified_external`, source
  `request:TEST-REQ-U1/action_binding`); valid U2 with `--compare` +
  shipped manifest exit 0 `verified_external`; owner sample exit 0
  `verified_external`. Both R4 fixtures under the plain CLI exit 2
  with their named codes (plus the standing
  U80-CTA-BINDING-UNVERIFIED, as every plain-CLI negative does since
  R2-01).
- Adapters impact (READ-ONLY; no adapters files edited): the adapters
  suite still passes **66/66** against the repaired profile/validator.
  This pass touched no schema, so no fixture conformance question
  arises.
- Profile version 1.3.0 → 1.4.0 (subject-first scarcity families,
  decline-model imperative condition). Neither schema was touched; the
  binding manifest, both R3 fixtures, both valid copy fixtures and
  both request fixtures are byte-identical to the Appendix C table.

## Post-R4-fold hashes (SHA-256)

- profiles/upsell-profile.json (v1.4.0): c7bf8fa0b625dd8f6a67a0ed4bd496f77fd84fc8cc581ef93aefc4eecac47f2a
- scripts/validate_upsell_copy.py: fbd84a3499dc93e3e748df334161c55be1eb904ff822dc6a26e82fa61efe0ade
- schemas/upsell-request.schema.json: db11ad6495feae69ac486411a5f164c33bccfae48f510b252e558030f7409fd9 (unchanged)
- schemas/upsell-result.schema.json: 8a4c23924dc4732643b6e3e09cfb344bac6aad4ebaad0ac89e34890c852a1a36 (unchanged)
- tests/test_validate_upsell_copy.py: 912b318644b7eb1b4d1359d41605a3c5f9b7e5a6b5e3333b47f7986aaa1a1292
- fixtures/binding-manifest.testonly.json: f8aca3f8ea0809d094d097c0c160e28c6bfbcaa82b03cb8ecc668922143e2d28 (unchanged)
- fixtures/copy-r4-scarcity-subject-first.json (new): 024308ff107a3adde30d5d5610f9fc00d4a2c412bf84cc0a635698c061f24fbe
- fixtures/copy-r4-decline-shielded-imperative.json (new): b45f0701d83ccea6ff8cd25c53373d76b81540486f49c29fc952c9f4496ff068
- fixtures/copy-r3-scarcity-pause-enrolments.json: 5a076a03443bf79934f9aa330cdec75e1e14538cdf18fe78a0d2816028b7e184 (unchanged)
- fixtures/copy-r3-decline-smuggled-cta.json: 34fc8ee8a138400733d18fd49e2f0387bd9a8c132157fad45497435297c1ee3e (unchanged)
- fixtures/copy-upsell1-public.valid.json: ad2eaff4f90d1e7c201aed9c713e46de3cf7d213257717eb504db421c74cab13 (unchanged)
- fixtures/copy-upsell2-public.valid.json: 56735f9a571af1226443777cc22464e5aa77a24e7cd2db47df02490f43734530 (unchanged)
- fixtures/request-upsell1.testonly.json: 629c870f698b435c071b152036acf69e703d1f89c2621c19f2d7ea725ac1d80c (unchanged)
- fixtures/request-upsell2.testonly.json: 3a0170592193e7f58619b76e4239da9f664d4aa094b20a04adcc5a553e776fdd (unchanged)

Open after this pass (unchanged in kind): independent re-review of
these R4 folds (reviewer is never the author), S80-06 native binding,
S80-09 installed purchase tests, S80-10 packaging — including the two
named deferrals the R3 re-review judged sound (`action_binding.source_ref`
patterning at S49-intake/S80-10; result `test_outcomes[].evidence_ref`
patterning when the first L3+ outcome is recorded). The reviewer
judged none of the R4 findings a production blocker and none blocks
S80-06; with R4-01/R4-02 folded, the remaining deterministic-layer
limits are the declared residuals listed above. These folds raise the
deterministic floor; they are not production evidence and do not
change the reported build percent on their own.
