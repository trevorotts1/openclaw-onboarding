# Anthology Engine: Department, Floor, and Self-Invocation Wiring

Slice: department-wiring (WAVE-PLAN W4.1). Binding on PRD Section 13. The
machine-readable source of truth is `wiring.json` in this folder; this README is
its plain-language companion. The enforcement pointer is
`verify-anthology-engine-wiring.py` in this folder.

Writing rules honored here: zero em dashes, no triple-backtick code fences.

## 1. Two layers, never one department pretending to be the other

Anthology is NOT the Podcast Production Engine's pattern. Podcast (skill 58)
attaches to an EXISTING universal-primary department that already sits on the
fleet's 28-department floor. Anthology (skill 59) is different on purpose: PRD
Section 13 splits it into two layers that are never conflated.

- The FLEET side: the skill registers under the books/publishing floor grouping
  for routing, reusing Skill 54's (anthology-writer) existing role binding. That
  grouping is the marketing department, the same mandatory department Skill 53
  (book-writer) and Skill 54 already bind to through the content-marketing-strategist
  role. This slice does not invent a new fleet department; it reuses the exact
  binding already proven live.

- The CLIENT side: the board identity is the seeded Anthology department, a NEW,
  client-optional department that Skill 32's add-department.sh creates directly
  inside a client's own Command Center at provisioning time (already wired on this
  branch at W2.6 STEP 3.5 and exercised by the board client at W3.1). It is never
  one of the 22 mandatory or 6 universal-primary departments, and it is never
  declared in `department-naming-map.json`.

This two-layer split is the corrective PRD Section 13 names directly: Skill 53's
books department was never seeded, so its cards fall to the CEO catch-all. The
Anthology Engine always seeds its own department, but it does so per client at
provisioning time, never as a static entry in the fleet's floor files. Run the
floor check to confirm nothing on the fleet side moved:

    python3 23-ai-workforce-blueprint/scripts/department-floor.py --json

`expected_floor_count` stays 29 (23 mandatory plus 6 universal-primary-vertical),
computed live, never a hardcoded integer. `department-naming-map.json`'s
`mandatory` and `vertical_packs` blocks are not touched by this slice; a raw-text
scan for the string "anthology" over that file returns zero hits, in either
block, both before and after this slice lands.

## 2. Canonical skill binding

The one machine-readable source binding a skill to its owning department and
specialist roles is `23-ai-workforce-blueprint/skill-department-map.json` (see
`universal-sops/native-skill-invocation.md`). This slice adds the skill 59 entry
there:

- skill 59, slug anthology-engine, client_facing true
- departments: marketing (the fleet-side floor grouping, PRD Section 13)
- owning role: content-marketing-strategist (primary), the EXACT role Skill 54
  already binds to, so the map's orphan check passes with zero new role-library
  entries required by this slice
- intent triggers: the same plain-language phrases SKILL.md already declares
  ("run the anthology engine", "start an anthology", "onboard an anthology
  producer", "assemble the anthology")
- execution_sops: book-writer-craft, the same craft cluster Skill 54 uses

The skill directory `59-anthology-engine/` was authored by the core-skill-authoring
slices (WAVE-PLAN W1.1, W1.5 to W1.24) and already ships on this branch, so
`check-skill-department-map.py`'s map-to-disk coverage assertion goes green as
soon as this map entry lands (no other slice has to co-land first).

PRD Section 13 also names two NEW specialist roles for the pipeline itself:
anthology-producer-orchestrator (owns the run end to end, the ledger, the
exceptions queue, escalations, S9 machinery) and anthology-approvals-steward
(owns gate hygiene, nudge cadence, the readiness report, the trigger and
sign-off flow). Both landed as SKILL-BUNDLED role files at
`59-anthology-engine/roles/` (WAVE-PLAN W4.2), the same kind of skill-internal
persona as the existing anthology-chapter-author, stamped into
`23-ai-workforce-blueprint/persona-matching-protocol.md`'s Section 13 appendix.
Neither is a `templates/role-library/_index.json` department role, so neither
is added to the map's owning-roles list; that is a permanent, structural
distinction, not a temporary gap this slice leaves for a later unit to close.
`wiring.json` records both roles' skill-bundled paths so the wiring stays fully
traceable.

## 3. Self-invocation: one entry point, three event kinds

The seeded Anthology department's how-to doc
(`HOW-TO-USE-THE-ANTHOLOGY-DEPARTMENT.md`, this folder) names
`anthology-engine-entry.sh` as the ONE sanctioned command every self-invocation
runs through, per PRD Section 13: "when an anthology intake, gate event, or
assembly trigger arrives, the department invokes the orchestrator skill through
its entry script." No department event ever calls a stage runner directly.

- Intake: a fresh Convert and Flow submission, or a plain-language producer
  request, invokes `anthology-engine-entry.sh --stage s0 --payload FILE`.
- Gate events: every producer or participant decision (approve, request
  rewrite, mark ready to assemble, sign off) reaches `gate_engine.py`'s shared
  both-door record-approval call through `anthology-engine-entry.sh --stage sN`;
  the board card and the token page are the two doors onto that one call, never
  a second write path.
- Assembly trigger: firing ready-to-assemble or the final sign-off invokes
  `anthology-engine-entry.sh --stage s9 --anthology-id ID`.

`wiring.json`'s `self_invocation` block is the machine-readable form of this
same statement; both point at the same script, which already ships on this
branch at `59-anthology-engine/anthology-engine-entry.sh`.

## 4. Access matrix (PRD Section 13)

Access is default-deny. PRD Section 13: "Marketing and social get READ-ONLY on
published links; every other department, no access. Client humans interact only
through the board, the forms, the token page, and Convert and Flow." The
complete decision lives in `wiring.json` under `access_matrix` and is enforced
by `verify-anthology-engine-wiring.py`:

- Owner (write): the fleet-side marketing department (content-marketing-strategist
  for map and routing purposes, plus the skill-bundled anthology-producer-orchestrator
  and anthology-approvals-steward roles that operate the pipeline stages) runs
  the engine; the only client-side write surface is the seeded Anthology
  department board and the participant token page, and the only client write
  actions are the gate decisions themselves.
- Read-only, downstream (no write): marketing reads published links for
  promotion planning; social-media reads published links for the same purpose.
  Neither can touch the pipeline or its state.
- No access (everything else): sales, billing-finance, legal,
  personal-assistant, customer-support, and every other floor department.
  Customer messaging belongs to Convert and Flow and the participant token page;
  no department messages a participant directly.

The enforcement script fails if a read-only department is granted write access,
or if any explicit no-access example is also a granted department.

## 5. QC independence rule

PRD Section 13: "QC independence rule: the content QC pass never runs on the
persona or model tier that drafted." The drafting persona is
anthology-chapter-author (Skill 54's existing authoring core, a skill-bundled
persona, not a role-library department role). The QC role is
anthology-approvals-steward (the skill-bundled role landed at W4.2). The two
are disjoint by construction; `verify-anthology-engine-wiring.py` asserts the
declared slugs never collapse into one string. Full runtime enforcement
(`judge_harness.py`'s `enforce_independence()`, `qc-tier1-anthology.py`,
`qc-strike-gate.py`) already ships on this branch and is proven end to end at
CHECKLIST.md Part C item 18, not by this slice.

## 6. Board mapping (already wired at W3.1, referenced here only)

Card vocabulary (`STATUS_BY_CURSOR` and `STATUS_BY_ASSEMBLY_STATE`), the ingest
and status endpoints, and the review-to-done contract were wired at W3.1
(`59-anthology-engine/scripts/mc_board.py`). This slice does not re-wire the
board; it registers the department in the fleet floor files and documents the
self-invocation entry. See `card-lifecycle-proof-plan.md` for the observed-move
proof plan, and WAVE-PLAN W4.3 for the mc_board.py-to-stage_cursor mapping unit.

## 7. Proof

- Build-gate proof for this slice: `department-floor.py` returns rc 0 with
  `expected_floor_count` unchanged at 29 and zero composition change;
  `check-skill-department-map.py` returns 0 violations (the skill 59 coverage
  gap it reported before this slice is now closed); `verify-anthology-engine-wiring.py`
  returns rc 0.
- Card-lifecycle proof: see `card-lifecycle-proof-plan.md`. The end-to-end
  observed card move is exercised on the operator box in WAVE-PLAN Wave 5.
