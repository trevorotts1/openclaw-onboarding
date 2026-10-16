# BUILD NOTES — Skill 80 Adapters (S80-04, S80-05, S80-07 local)

**Room:** S80 · **Scope built in this pass:** S80-04 (U1 production adapter),
S80-05 (U2 production adapter + shared-entry truth), and the LOCAL part of
S80-07 (success/decline/error routing state logic).
**Location:** `~/workspace/signature-launch/rooms/S80/work/adapters/`
**Status language:** local L0/L1 evidence only. Nothing here is installed,
merged, published, or live. No GHL or payment calls were made; no native
action ID exists anywhere in this directory. All fixture offers, prices,
IDs, journeys and copy are **TEST ONLY** and labeled as such.
**Sibling artifacts:** `../80-signature-upsell/` (S80-01/02/03) was read
and consumed read-only; it was NOT modified (verified: no sibling file is
newer than this pass's first file). No defects were found in it, so no
change note was needed.

Sources read in full before coding (this worker): packet
`10_SKILL_80_UPSELL_1_AND_2_SPEC.md` (esp. §§3, 5, 6, 7),
`02_SHARED_CONTRACTS_AND_ARCHITECTURE.md` §4 (all of it read),
`reference/reference_contracts.py`, `reference/acceptance-cases.json`
(64 cases), `reference/launch-example.json` (price map), and the sibling
`profiles/upsell-profile.json`, `schemas/upsell-request.schema.json`,
`schemas/upsell-result.schema.json` plus its request/result/copy fixtures.

## Files (SHA-256)

> **SUPERSEDED (review defect R80-D01, corrected 2026-10-15):** this original
> table predates the adapter conformance repair. For the 16 files that repair
> changed, the hashes below are stale; use **Appendix A**, whose hashes were
> verified against disk by the independent reviewer. Files not listed in
> Appendix A are unchanged and their hashes below stand.

| File | SHA-256 |
|---|---|
| routing_state.py | 9f7081ce23009c044bc6c63a9c2c486b62b83e53dd41453cdf3e83996c508979 |
| adapter_common.py | 915d5fd3f4a1f0f37dfa04799a63911cca4b7cad81f39081e3501c65d7881e0a |
| upsell1_adapter.py | 1dc7e23c61d363f25a58f44e02a5a9dca428cbc9fc7aaacc8cb13da4de84c192 |
| upsell2_adapter.py | 91e17203818d86b2b28b996b3e680c9e8c5666ef985db07cce3ad99423180dfa |
| produce.py | 1658a45d1da8baaf55a2e6ec7ba718cb05349e0d826f08a32d3478b4582083f0 |
| fixtures/expected-bundle-upsell1.testonly.json | b9089d32f0a26f40df33537a2533a61730931a22397df617f36a19dd199d3361 |
| fixtures/expected-bundle-upsell2-from-upsell1.testonly.json | 83d9fc2c24fe97a02bf14c4c8a0d372b781b33cb8788e05635104751c2342099 |
| fixtures/expected-bundle-upsell2-from-downsell1.testonly.json | c755f41c89f2744190e061795e308b1b45013a0de941314142db95e5616c04a1 |
| fixtures/request-upsell2-from-upsell1.testonly.json | 94e4435f4d6b9d9a27f017d38e63339fe3b729ffdfa670358a99616fbb4005a6 |
| fixtures/request-upsell2-already-owned.testonly.json | d8a04a18f5c35bfc0629c9f0aa47f192d6b4e0b28235c7ecd92d033778a6e956 |
| fixtures/journey-main-only.testonly.json | d8cff7038ad0d04f709b7efd89085216690a6247d54edd98e40e4d1e11a07c84 |
| fixtures/journey-upsell2-from-upsell1.testonly.json | a08116bf8056f0bcab0fdaf560c1020fe108222ed572e0f922efb7d5bcedf9df |
| fixtures/journey-upsell2-from-downsell1.testonly.json | 54e9197e527cf177a92bb80e2e627f6d4fae9d52c1f9fe1789aba28ca959221c |
| fixtures/journey-upsell2-bump-only.testonly.json | ab2461e4672d771d93c2260270e5ff482bc224c08bd871076015f980a57617ce |
| fixtures/journey-upsell2-client-claim.testonly.json | d5c0d36697e4d53362705811da40b7d503a9c5f7a918ccdf673c358db79fef01 |
| fixtures/journey-upsell2-already-owned.testonly.json | b764acf82693af52d2a0e1f476277bf49892245e55f33351bff6bc46cb78cfe5 |
| fixtures/journey-upsell2-incompatible.testonly.json | 095f12ca37450a453d6550f5a58611a0c44c8b4d4f433ff55c85571082824e25 |
| tests/test_routing_state.py | 6ab8c25d0b97dcda02c5718c9bde42e5eecd3b9dae03df72467e16382cbaafe5 |
| tests/test_adapters_upsell1.py | 9fe7e7208670dba3b57f529a22906a15f5c8c907b8a61a126dd14278bdddf935 |
| tests/test_adapters_upsell2.py | b5005243c49ae99a53fd5841575bc1b47f195934ca00b2d80d25df04b757478c |

(BUILD-NOTES-ADAPTERS.md itself is excluded from its own table; its hash
is reported with the delivery message.)

## What was built

### S80-07 (local) — `routing_state.py`
Deterministic, stdlib-only state machine for the doc 02 §4 edges of
checkout / upsell_1 / downsell_1 / upsell_2:

- `RouteConfig` — enabled flags + canonical page-ID map; enforces the
  doc 02 invariant (U1 disabled ⇒ D1 and U2 cannot remain enabled) and
  exactly one canonical U2 page ID.
- `edges(config)` — the explicit edge list, including recoverable stay
  edges (pending / failed / requires-customer-action) and the
  separately-recorded continue-without edges; a disabled U2 produces no
  edges at all (no orphan node).
- `resolve(state, config, event, payment_verified=...)` — U1 paid → U2
  if enabled else thank-you; U1 decline → D1 if enabled else thank-you;
  D1 paid → the SAME U2 page ID; U2 paid or declined → thank-you;
  decline-both can never reach U2 (stage guard requires a verified U1
  or D1 token); a bump token alone never qualifies; pending / failed /
  requires-action STAY with record classification
  `neither_acceptance_nor_decline` and grant nothing; unverified
  "success" raises instead of transitioning; `tab_closed` records
  abandonment, never a decline; unknown events raise.
- `PaymentAttemptGuard` — single-flight processing guard (double-click
  protection) and `ensure_trigger_may_purchase` — page load, scroll,
  timer expiry and close-icon clicks can never purchase (spec §6).

### S80-04 — `upsell1_adapter.py` (+ `adapter_common.py`, `produce.py`)
Given a valid upsell_1 request + the eight-section copy fixture + a
verified journey, it emits a deterministic bundle
`{"result": ..., "page_plan": ...}`:

- `result` validates against the sibling S80-02 result schema
  (test-asserted with jsonschema): 8-entry CTA map where every CTA binds
  the SAME guarded action placeholder `native-one-click:<offer_id>`;
  `native_action.action_id` is null and `verified_by` is
  `pending_s80_06` — no action ID is invented; disclosure audit verdict
  `pending_native_binding`.
- `page_plan` declares the adjacent disclosure RENDERED from integer
  `amount_minor` / currency / billing terms (never float money; currency
  minor-unit exponents are not hardcoded to 2 — doc 02 §3), plus the
  processing state (repeat triggering disabled while pending), the
  visible no-charge decline route, the failure/pending/requires-action
  stays, the expired-context and one-click-unavailable fallbacks, and
  the already-owned suppression behaviour.
- Eligibility: verified original purchase only, cross-checked between the
  request and trusted-adapter journey evidence (matching evidence_ref,
  adapter-only verification sources). Client-side claims block the page.
  Missing or float prices fail closed. Already-owned U1 is suppressed
  with `charge_action_emitted: false`.

### S80-05 — `upsell2_adapter.py`
Same skill, distinct instance, kept separately visible in code, fixtures
and tests:

- ONE canonical U2 page ID (`TEST-UPSELL_2` in fixtures) and ONE approved
  offer mapping serve both entry contexts; test-asserted identical
  across the `from_upsell_1` and `from_downsell_1` bundles, including the
  recurring disclosure rendered from terms (USD 47.00 today, then per
  month, 3 payments total).
- Eligibility gate: verified original purchase PLUS verified U1-or-D1
  purchase, with slot AND evidence_ref cross-checked against journey
  state, and `entry_context` required to agree with the verified slot.
  Bump-only → blocked bundle naming the rule; client-claim request →
  the checker returns unverified problems AND the adapter fails closed
  with `AdapterError` (it also fails the S80-02 request schema:
  `client_side_claims_accepted_as_proof` const false) — a schema-level
  lie errors out, a genuine lack of qualification returns a blocked
  result; both paths are test-asserted.
- Conditional acknowledgement blocks use ONLY names from verified
  journey records. The from_downsell_1 block says the downsell choice is
  confirmed "at its own terms. You chose that alternative instead of the
  full first-upgrade package…" — tests assert the U1 offer name and any
  "your first upgrade is confirmed" phrasing are ABSENT on the D1 path
  and PRESENT on the U1 path (false prior-purchase statement = automatic
  fail, spec §10).
- Already-owned U2 and incompatible-entitlement journeys →
  `route_to_final_thank_you` disposition with
  `charge_action_emitted: false`; never a duplicate charge.

## Semantic differences: reference_contracts.py vs doc 02 / spec 10

Doc 02 §4 and spec 10 govern; the reference helper was followed wherever
it agrees. Recorded differences (also in the `routing_state.py`
docstring):

- **D1 — `continue_without_extra` event added.** The reference has no
  such event (unknown events raise). Doc 02 §4 explicitly requires a
  deliberate continue-without after a failure to be an explicit decline
  RECORDED SEPARATELY. Ours routes it exactly like `explicit_decline`
  but writes a distinct `recorded_decline` history record, so a failure
  record and the later decline record never merge.
- **D2 — `tab_closed` event added.** The reference would raise. Doc 02
  §4: closing a tab is abandonment, not a fabricated decline. Ours stays
  in place with kind `abandonment` and records no decline.
- **D3 — Presentation only.** The reference returns bare
  `(stage, purchased)` pairs. Ours returns page-ID-resolved transitions
  (one canonical U2 page ID for both entry paths), the U2
  `entry_context`, and an append-only auditable history. Transition
  semantics are unchanged — proven by the differential test below.
- **Aligned, not differences:** the Extras invariant (U1 off ⇒ D1/U2
  off) is doc 02 §4 verbatim and implemented in both; checkout success
  requires pre-existing trusted main-purchase evidence (a `MAIN-*` token
  recorded by the trusted S44/S06 adapter) and no implementation mints
  purchase tokens for checkout; `payment_verified=False` on a claimed
  success is an error in both.

## Verified (evidence in this pass)

Exact command, run from `~/workspace/signature-launch/rooms/S80/work/adapters`:

```
python3 -m unittest discover -s tests
```

Output: **60 tests, OK** (`Ran 60 tests in 0.415s` on the final run) —
routing edge/transition/stay/guard suites (incl. the differential suite
against `reference_contracts.resolve_after`, 13 scenarios), the full
64-case packet cross-check (visited page-role tails, purchased offer
sets, integer-minor totals from `launch-example.json`, canonical U2 page
ID, U1/D1 mutual exclusion, no U2 visit when disabled), U1 adapter suite
(schema validation, CTA map, disclosure rendering, negatives), and U2
adapter suite (both entry paths, acknowledgement truth, eligibility
gate, suppression). `python3 -m py_compile` passes on all modules.
Determinism: all three expected bundles were regenerated through
`produce.py` and are byte-identical; the suites assert in-memory output
equals the stored bundles.

U1 and U2 are separately fixtured (distinct page IDs, offers, prices,
entry contexts), separately coded (`upsell1_adapter.py` /
`upsell2_adapter.py`), and separately tested
(`test_adapters_upsell1.py` / `test_adapters_upsell2.py`).

## Still pending — NOT in this pass, NOT claimed

- **S80-06:** native one-click action/disclosure integration via Skill 6
  — every bundle honestly carries `native_action: null`,
  `verified_by: pending_s80_06`, `disclosure_audit:
  pending_native_binding`, and the required native configuration
  screenshot does not exist yet.
- **S80-07 (installed part):** the routing logic here is LOCAL (L1). The
  installed route execution with S49/S06 (A10/A11/A12 at L3) and sandbox
  payment proof (L4) are not run and remain `not_run` in the bundles'
  test outcomes.
- **S80-08:** assets/visuals. **S80-09:** installed purchase tests
  (double click, expired native payment context, customer authentication
  required — declared as states, proven only locally; refresh/back
  navigation is NOT a declared page_plan state — it is an L4 S80-09 case,
  status `not_run`, recorded in the bundles' test outcomes; corrected per
  review defect R80-D02, 2026-10-15).
- **S80-10:** independent review and packaging — bundles carry
  `independent_review: false`, `reviewer_session: null`, status
  `authored` (or `blocked` for suppressed/unverified cases).
- Adapter request validation is a stdlib mirror of the load-bearing
  S80-02 schema rules; full JSON Schema validation is asserted in the
  test suites (jsonschema), not inside the adapters, keeping the
  adapters stdlib-only.
- No SKILL.md entrypoint, no repo branch/worktree, no merge/push/
  publish, no GHL or payment calls were made in this pass.

---

## Appendix A — Adapter conformance repair (post D-06/D-07/D-08 schema repair)

**Pass:** adapter conformance repair, appended after the S80-02 sibling
schemas were repaired (defects D-06/D-07/D-08 plus the D-03
`action_binding` repair). The original record above is NOT rewritten;
the hash table above is superseded for the files listed below. Work was
confined to this `adapters/` directory; no sibling artifact was edited.

### Failure investigation (field-level, before any regeneration)

Reproduced firsthand: `python3 -m unittest discover -s tests` in
`adapters/` → 60 tests, FAILED (failures=2, errors=1).

- **ERROR** `test_both_entry_requests_validate_against_request_schema`:
  `fixtures/request-upsell2-from-upsell1.testonly.json` —
  `eligibility.qualifying_purchase` lacked the now-required
  `verification_source` (repaired schema requires
  `['slot', 'status', 'verification_source', 'evidence_ref']` with the
  source restricted to `native_purchase_ledger` /
  `provider_event_readback` / `s44_event_adapter`).
- **FAIL ×2** deterministic-bundle tests (U1 and U2): a recursive
  field-level diff of freshly generated bundles against the stored
  expected bundles showed the ONLY differing fields were the four
  copy-hash fields in each bundle — `/result/artifacts[0]/sha256`,
  `/result/source_hash`, `/result/copy_validation/copy_sha256`,
  `/result/hashes/copy_sha256` — moving from the pre-repair copy hashes
  (U1 copy `2fc2f757…`, U2 copy `f47f67bc…`) to the post-repair copy
  hashes (U1 copy `ad2eaff4…`, U2 copy `56735f9a…`). The sibling copy
  fixtures changed because the D-03 repair added their `action_binding`
  blocks. **Hash-only diff; no semantic bundle change existed, and none
  was regenerated over.**

### Changes made (all inside `adapters/`)

- `fixtures/request-upsell2-from-upsell1.testonly.json` and
  `fixtures/request-upsell2-already-owned.testonly.json`:
  `eligibility.qualifying_purchase.verification_source` added
  (`s44_event_adapter` — the source the paired verified journey record
  was recorded under), and a top-level `action_binding` block added
  (`expected_action_ref: native-one-click:TEST-ONLY-U2`,
  `binding_kind: native_one_click_guarded`,
  `source_ref: 80-signature-upsell/fixtures/copy-upsell2-public.valid.json#action_binding`),
  mirroring the sibling request fixtures' convention.
- `fixtures/journey-*.testonly.json` (all 7): every
  `verified_purchases` record gained `verification_source` — the source
  that record's evidence was recorded under (adapter/native enum only;
  main records mirror the paired requests' original-purchase source:
  `native_purchase_ledger` for the U1 pair, `s44_event_adapter` for the
  U2 pairs). This is what the request's stated source is now checked
  against, so the source is sourced from journey evidence, never merely
  asserted by the request, and never a client claim.
- `adapter_common.py`:
  - `validate_request` now enforces a declared `action_binding`:
    `binding_kind` must be `native_one_click_guarded` and
    `expected_action_ref` must equal this offer's guarded action ref;
    a mismatch fails closed (D-03).
  - `build_cta_map` cross-checks the copy document's own
    `action_binding.expected_action_ref` against the same ref.
  - `original_purchase_check` additionally requires the journey
    main-purchase record to carry an adapter `verification_source`; an
    unsourced journey record is not verified evidence.
- `upsell2_adapter.py` (`check_u2_eligibility`): the qualifying
  purchase now carries the same verification discipline as the original
  purchase (D-06): `verification_source` must be in the adapter/native
  enum; an `evidence_ref` carrying client-claim markers
  (`acceptedU1=true`, `client-side`, `client_side` — mirroring the
  repaired schema's `not` guard) is rejected as a claim, not proof;
  and the request's stated source must equal the verified journey
  record's recorded source for the qualifying slot. Entry-context /
  qualifying-slot agreement (D-07) and recurring-terms (D-08) were
  already enforced by the checker/schema and are covered by the suites.
- Tests (+6, 60 → 66): already-owned adapters request now
  schema-validated; qualifying-source mismatch with the journey record
  blocks U2 with no charge action; missing qualifying
  `verification_source` is not proof; client-claim qualifying
  `evidence_ref` is not proof; `action_binding` mismatch fails closed
  for both U2 and U1.

### Bundle regeneration

The three expected bundles were regenerated through `produce.py` with
exactly the inputs the tests use. Field-level diff of regenerated vs
pre-repair stored bundles: **only the four copy-hash fields per bundle
listed above changed** — the direct consequence of the D-03 copy-fixture
repair. No other result or page_plan field changed.

### Post-repair hashes (supersede the table above for these files)

| File | SHA-256 |
|---|---|
| adapter_common.py | 831f0cf84cb4447565e33c7e242e412846514d3111a4baf165a56db2cbb8b556 |
| upsell2_adapter.py | 55a46e9b0f2e4826ebe58340e2b7175cf0d4544d17bf8005e8f47fbb04d13e04 |
| fixtures/expected-bundle-upsell1.testonly.json | c6cb5f3710ecc949459541922800b9160b6b0b4b67d4d2b6dcc3d5e2f577769e |
| fixtures/expected-bundle-upsell2-from-upsell1.testonly.json | ae57da8b7a177694e732635b2d1f2651406d9e071a27203dd11def81e9653d6a |
| fixtures/expected-bundle-upsell2-from-downsell1.testonly.json | 81292bb4333c750e0f4552aa837a9a66f09af489a129f06b9befb12bebff8b3c |
| fixtures/request-upsell2-from-upsell1.testonly.json | 41f06953c48ef4249e9e6ee8f4bd6883ae270054a3e90ebfe7f524bbbbe695d6 |
| fixtures/request-upsell2-already-owned.testonly.json | 1fecc64a7ab34b2c19ff56ef078d1450429ab22a686c2fda9a746e079bded5c8 |
| fixtures/journey-main-only.testonly.json | 0d82a404dcde9be7614fce0ee7462f8172a31d24bf35beff67a81db506a86e04 |
| fixtures/journey-upsell2-already-owned.testonly.json | 5a6f7213fb90d820173540df0c90b60c981ba8613b3dfddbfbb1e5ab36ba0e68 |
| fixtures/journey-upsell2-bump-only.testonly.json | 4d161b6dd665ad35fadf2fe8a0b626a8af3cdc9b23ad75a03b8f6b6e755621c4 |
| fixtures/journey-upsell2-client-claim.testonly.json | f4c9c971dd91a889eebbd10db8f36608686896cf4e21105368a9c69c82affcc6 |
| fixtures/journey-upsell2-from-downsell1.testonly.json | ff6611b409504fb324eff1435ba4df0ef0e5130db1b9e3cb5cc5e91e939ae809 |
| fixtures/journey-upsell2-from-upsell1.testonly.json | 55df1f3a1f0f3c9fc92c15c40d67dd0e87fad783c2ac3bf6929d9f3e4fba0f7f |
| fixtures/journey-upsell2-incompatible.testonly.json | e37e0e7df76c6f71a6dfe3363f2f7a6641f0f6aaf62f071c6c799c79fa7822fd |
| tests/test_adapters_upsell1.py | 280efe52bdae98000cb51ae7640356ac40c7b996ca4e4e576a4f9fdbc656f829 |
| tests/test_adapters_upsell2.py | bae37c16636adbcbc8397e2cf6748cb7136c9aa705234a319942966f62d2bfe7 |

(`upsell1_adapter.py`, `routing_state.py`, `produce.py` and
`tests/test_routing_state.py` are unchanged; their hashes in the table
above still stand.)

### Verification (exact commands, this pass)

```
cd ~/workspace/signature-launch/rooms/S80/work/adapters
python3 -m unittest discover -s tests
→ Ran 66 tests in 0.873s — OK

# byte-identical regeneration: produce.py re-run to /tmp outputs for
# all three bundles, diffed against the stored fixtures
→ BYTE-IDENTICAL: all 3 bundles

cd ../80-signature-upsell && python3 -m unittest discover -s tests   # read-only
→ Ran 39 tests — OK

python3 -m py_compile adapter_common.py upsell1_adapter.py \
    upsell2_adapter.py routing_state.py produce.py
→ OK
```

Still pending, unchanged from the original record: S80-06 native
binding (bundles still carry `native_action: null`,
`pending_s80_06`), S80-07 installed part / S80-09 (L3/L4 `not_run`),
S80-08, S80-10. Proof level remains L1.

---

# Appendix B — S80-06 extra-offer binding integration (2026-10-16, appended)

Wires the adapters to the S80-06 extra-offer binding built by the parallel
worker in `work/binding/extra_offer_binding.py` against the fixed contract.
This appendix is appended history; nothing above was rewritten.

## What changed

- **Bundle shape**: every bundle is now `{result, page_plan, native_binding}`.
  `native_binding` is exactly the contract record: kind `extra_offer_binding`,
  interface_ref `S79 extra_offer_interface.md DRAFT (fixture level)`,
  binding_status `interface_conformant_pending_s06`, native_action_id null,
  capability_evidence_ref, open_questions
  [S06-Q1..S06-Q6, S44-Q7, S44-Q8, S49-Q9]. It lives at bundle top level
  because the upsell-result schema forbids additional properties inside
  `result`.
- **CTA action refs**: bundle `cta_map` entries and
  `page_plan.action_binding.action_ref` now carry
  `extra-offer-binding:<offer_id>` (was the placeholder
  `native-one-click:<offer_id>`). `page_plan.action_binding` also records
  `native_action_ref` (the wrapped native form) and its kind/status are
  `extra_offer_binding` / `interface_conformant_pending_s06`; `action_id`
  stays null; guard and trigger lists are unchanged.
- **Two-layer ref rule (honest reconciliation, validator untouched)**: the
  request schema pattern-locks `action_binding.expected_action_ref` to
  `^native-one-click:...`, and the copy validator's guarded-action form
  accepts only `native-one-click:` (its self-test hardcodes that form).
  The copy/request layer therefore keeps declaring
  `native-one-click:<offer_id>`; the bundle/page layer emits the binding
  ref for the SAME offer_id. Correspondence is enforced in three places
  with no weakening anywhere: adapters validate the request's declared
  native ref as before; bundle CTAs/plan carry the binding ref; the
  renderer derives the expected binding ref from the copy's native ref
  and refuses on any disagreement. **Neither the validator nor any
  binding-manifest fixture was edited**: the manifests carry copy-side
  evidence (validator output, native form), not adapter output, so no
  expectation fixture needed to change.
- **Result `native_action`**: `verified_by` is now `s80_06_binding`
  (action_id still null; nothing invented). One contract gap was found
  and closed additively: the result schema's `verified_by` enum was
  `["skill_06", "pending_s80_06"]` and would have rejected the contracted
  value; the enum was extended to include `s80_06_binding` with an honest
  description (schema sha256
  419690ecea7c7d6478ec39ade3c923eb434d285e655fbb91ef782b3539b3f8f8).
  Existing values remain valid; nothing was removed or weakened.
- **Honest status text**: the first bundle blocker now states the binding
  is integrated at interface-conformance level only, the native action ID
  is null pending S06 confirmation (Q1–Q6, S44-Q7/Q8, S49-Q9), and the
  record is NOT installed or live proof. `disclosure_audit.verdict` stays
  `pending_native_binding` (the amount-versus-native match is still
  genuinely pending a native read-back); its note text was updated.
- **capability_evidence_ref**: `native:TEST-CAPABILITY-EVIDENCE` is emitted
  only for test_only requests (scheme-prefixed per the binding module's
  evidence rule); a non-test request records None rather than borrowing
  fixture evidence.

## Files and hashes (sha256)

- adapter_common.py 949099d7ccab45cdb84394280dddb287c8d70eb217e3e749207079801306c25e
- upsell1_adapter.py 3127d3399ff22dfafce5ca4d0446d4ceb192a03490347aa7c79bfc602e36eaec
- upsell2_adapter.py 280f0ea7f75f28bf3a56c3f96a34460ac55c76021f7a08072fb631268acdf5b9
- produce.py 0f0c6425ff2d5d51d40001c07b9a8e5f88f4d27889cf27c26d2c3a38961d9c90 (docstring only)
- tests/test_adapters_upsell1.py f6d367fff8662b135833e4b31d1d2a6e6c932c63c28ef778ff9029e97319b46d
  (two contract-literal assertions updated at the same strength: CTA refs
  are the binding refs; the native-action test now also pins verified_by,
  plan kind/status/action_ref/native_action_ref; no assertion deleted or
  weakened; negative request-layer tests unchanged)
- tests/test_binding_wiring.py (NEW) 5f51d8d5a170b16bda88414639d335c44d8c32ff94a0259e04ce80ba6e6a0a53
- Regenerated expected bundles (field-level diff vs the pre-integration
  fixtures showed ONLY the contracted changes: refs, native_binding
  added, verified_by, plan action_binding, blocker/note text):
  - expected-bundle-upsell1.testonly.json 565ff73a9c5b9d2677ebf13fc10e6245a4d7469b7669c63d8aacbb089ef37868
  - expected-bundle-upsell2-from-upsell1.testonly.json 738a77e513c06038015234d61fabbf5fc8286bc7d81346352f31380b9c9ec81e
  - expected-bundle-upsell2-from-downsell1.testonly.json 65980eca4b69df1a270c9e39876eb802160b0445b39eadf05d6accf4721e1111

## Suites (2026-10-16, this integration)

- Adapter suite: **70 tests OK** (66 pre-existing + 4 new in
  tests/test_binding_wiring.py: exact contract-shape record, binding refs
  on every CTA/plan, uninvented native action, and the cross-check below).
- **Binding reconciliation (DO #5) RAN LIVE, no skip**: the binding tree
  landed during this task (extra_offer_binding.py sha256
  4502b255670312d66b864c60eb7219b3dbbbc971d55c8ccda8f0f557b8b7a19d, the
  post-review repaired version). For each of the 3 bundles the test
  constructs a real `BindingContext` from the bundle plus its producing
  request/journey (including the validated fields launch_revision,
  copy_refs as a tuple, disclosure_terms_ref as a `request:` structured
  ref; native product/price refs are plainly-TEST stand-ins because the
  fixtures honestly record them unmapped) and asserts
  `ExtraOfferBinding(context).binding_record()` equals the bundle's
  native_binding, excluding only the capability_evidence_ref value per
  the contract. PASS for all three bundles. The binding module's own
  suite also passes from this tree: 50 tests OK (read-only run).
- Copy validator suite: 85 tests OK; validator --self-test PASS
  (unchanged by this integration apart from the additive schema enum).

## Honest residual

- native_action_id is null; native install is pending S06 confirmation
  of open questions S06-Q1..Q6 (S44-Q7/Q8, S49-Q9 also open). Nothing here
  is a live native action, an install, or a charge path.
- Acceptance stays at the levels already recorded: adapters L0/L1.
  L3 (installed GHL test location) and L4 (native sandbox payment) are
  **not_run**; this integration does not raise any acceptance level.
- The S80-10 package tree under `work/package/` predates this wiring and
  is now stale relative to the adapters (its copies of adapter_common,
  adapters, schema, and bundles carry the old placeholder ref);
  repackaging is an S80-10 follow-up, not done here.

---

# Appendix C — Hash correction for `tests/test_binding_wiring.py` (2026-10-16, appended; Finding D-N1-1)

This appendix is appended history; nothing above was rewritten. It corrects
one stale hash in Appendix B, as prescribed by Finding D-N1-1 in
`work/review-S80-N1-delta.md`.

- File: `tests/test_binding_wiring.py`
- Hash listed in Appendix B: `5f51d8d5a170b16bda88414639d335c44d8c32ff94a0259e04ce80ba6e6a0a53`
- Current hash on disk: `3479035c7cbd88644238a8ca77632ff9795930a5d836234197be2cc1d611dd38`
- Why it changed: the Appendix B hash was correct when Appendix B was
  written (07:13 EDT, 2026-10-16). The file changed afterwards, at
  07:29 EDT, in the N2 tightening during the S80-10 packaging pass:
  the reconciliation test now asserts the constructed kwarg key set
  equals the `BindingContext` parameter set exactly, instead of
  filtering kwargs by signature (see the in-code comment
  "N2 tightening (S80-10 packaging pass, 2026-10-16)" in that file).
  The packaged copy under
  `work/package/80-signature-upsell/components/adapters/tests/`
  carries the identical current hash.
