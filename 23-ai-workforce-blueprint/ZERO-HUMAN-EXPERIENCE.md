# ZERO HUMAN EXPERIENCE (ZHE) — DOCTRINE

**Constant:** `ZHE_SEQUENCE_V1`
**Owner:** Trevor (BlackCEO). **Canonical spec:** `ZERO-HUMAN-COMPANY-SYSTEM-SPEC.md` §1.
**Status:** wired into the repo so that when Trevor says **"zero human experience"** the
system knows the term, the steps, the edge cases, and what is being asked.

---

## What "Zero Human Experience" means

**"Zero Human Experience" = the exact sequence that MUST happen when a person completes
the AI Workforce interview.** From interview-complete to a routable Zero Human Company,
no human has to wire anything by hand — the box provisions itself from the canonical
floor library and proves it landed, with receipts.

---

## The ZHE sequence (`ZHE_SEQUENCE_V1`) — steps on interview completion

1. Interview answers → company profile (industry, offers, brand, voice, departments needed).
2. **Workforce build** (`build-workforce.py`): selects the FLOOR departments for this
   company + any **custom** departments the interview surfaced.
3. **Roles + SOPs are PROVISIONED FROM THE CANONICAL FLOOR LIBRARY — NOT rewritten by the
   box.** (Hard invariant — see spec §2.) Custom-only generation is the sole exception,
   and custom artifacts must auto-wire to Command Center + Kanban + personas.
4. **Dept agents REGISTERED** in `agents.list` (`materialize-dept-agents.sh`) —
   built-as-files AND registered-as-agents (agent id `dept-<slug>`).
5. **Personas** indexed (section-tagged canonical index) + persona-matching wired.
6. **Command Center** provisioned (board, departments surfaced) + **Kanban** ready.
7. **AGENTS.md** stamped with: routing doctrine, persona reflex, full-context-handoff
   rule, reporting rules, **and platform facts** (spec §7).
8. Owner can now talk to the AI CEO and have tasks routed + executed + reported.
   **Floor PASS proves it.**

---

## Edge cases (binding)

- **Interview incomplete → no ZHE; the box is EXEMPT.** The prover skips the checks and
  passes (exit 0). A not-completed box does nothing and fails nothing. This exemption
  holds for boxes that have NOT been standard-prebuilt.
- **Interview incomplete BUT standard-prebuilt → the box proves STANDARD_READY and is
  EXEMPT from the registration/routing checks** (standard-first redesign, 2026-08-04;
  master plan §3.3 + §5.2). When build-state carries `standardPrebuild.status == "done"`
  while `interviewComplete` is not true, the operator's prebuild has already provisioned
  the full canonical floor from the role library. Such a box is neither EXEMPT (that
  would blind the fleet signal — a broken prebuild would prove nothing) nor held to the
  full ZHE (it deliberately defers the rest). `prove-zhe.py` runs the STANDARD_READY
  subset instead:
  - **(SR-A)** the floor departments are present **ON DISK** — measured by
    `department_floor.evaluate_floor()`, never the build-state JSON;
  - **(SR-B)** the chosen-departments artifact (`<company>/departments.json`) is present
    and non-empty;
  - **(SR-C)** the Command Center board join holds (`prove-board-join.py`:
    chosen == provisioned == displayed).
  SKIPPED until `interviewComplete` (by design): agent registration (lazy `agents.list`
  rows land at interview-completion for confirmed-kept departments only), persona
  indexing, AGENTS.md doctrine stamping, and the provisioning-receipt equality. The
  receipt carries `standard_ready: true` + `verdict: "standard-ready"`; the prover exits
  0 on subset pass and 1 on a broken prebuild. A standard-prebuilt box that ALSO has
  `interviewComplete == true` runs the FULL `ZHE_SEQUENCE_V1` (the apply-diff build has
  run; the whole sequence applies). The fleet aggregate counts STANDARD_READY as its OWN
  column — never folded into PASS or EXEMPT.
- **Custom departments present →** assert via the custom-dept wiring path (spec §2), not
  as a violation. A custom dept is "done" only when routable + on the board + persona-matchable.
- **Offline / partial install →** the gate records the verdict and **auto-resumes on the
  next update** (resume cron re-proves).
- **Platform variants (Mac mini / VPS-Hostinger / VPS-Contabo / Docker) →** the prover and
  scripts resolve the expected paths per detected platform (spec §7); never hardcode.

---

## Enforcement (where the doctrine becomes a gate)

This doctrine is not prose-only — it is enforced by a fail-loud, receipt-backed,
pure-code gate (no LLM is ever in the counting or the verdict):

- **`scripts/prove-zhe.py`** — the per-box + CI acceptance prover. Asserts, with a receipt:
  floor depts present **and** registered as agents; personas canonical + section-tagged
  (54 personas, ~4413-row `embeddings` index with `mode`/`section_number`); Command Center
  DB reachable + `workspaces` rows present + a board lane per floor department; AGENTS.md
  carrying the routing + persona-reflex + full-context-handoff + reporting + **platform-facts**
  markers. Exempt for not-completed boxes; **STANDARD_READY** for standard-prebuilt boxes
  whose interview has not completed (see edge cases). Mirrored into `~/clawd/fleet-prover/`
  for the fleet operator aggregate (`--with-subprovers` delegates to `prove-floor.py`).
- **`run-full-install.sh` phase 7z** (Skill 32) — runs `prove-zhe.py --local` after the
  full provisioning; records `zheGateStatus` and prints the verdict loud.
- **`scripts/verify-library-gate.sh`** — runs the prover as the **highest-priority
  verdict** (rc 9), alongside the canonical-authoring / role / SOP / trio / boundary gates;
  records `zheStatus`. A STANDARD_READY receipt is **pass-equivalent** (`zheStatus =
  "standard-ready"`); rc 9 stays reserved for genuine failures — a complete box that
  misses the ZHE, or a prebuilt box whose STANDARD_READY subset is broken.
- **`scripts/verify-zhc-standard.sh`** — the closeout preflight's standard check. A
  standard-prebuilt, interview-incomplete box is reported **STANDARD_READY** with its own
  exit code (10) instead of going red (rc 2) on every newly-prebuilt box; a broken
  prebuild still fails loud (rc 3 floor / rc 8 chosen artifact).

**BLOCKING BY DEFAULT (plan §6; Issue #6, v17.0.11):** the prover was authored RED
before everything so each ZHE step was built to turn it green. The routing,
persona-reflex, full-context-handoff, reporting and platform-facts markers are now
stamped via `apply-fleet-standards.sh`, so the RED-first precondition has landed. The
two gates above therefore **hard-fail the build BY DEFAULT** (`ZHE_ENFORCE` unset
behaves as `=1`); an explicit `ZHE_ENFORCE=0` escape hatch is retained to unblock a box
while a genuine prover regression is triaged. The default is safe for fresh/in-flight
builds because a box that did NOT complete the interview is **EXEMPT** (prover exits 0),
and a standard-prebuilt box proves **STANDARD_READY** (pass-equivalent) instead of
failing. A hard fail marks the install failed so the resume cron re-proves on the next
update (fail-loud + auto-repair).

---

## Definition of done (the ZHE)

A box that completed the interview gets the full ZHE (enforced, edge-cases handled);
never rewrites floor roles/SOPs (custom-only exception wired to CC + Kanban + personas);
its CEO routes every task to a department with full context + pointer refs; communicates
assignment/start/done with persona + dept + specialist + SOP + role; nothing sticks on
the Kanban; platform-aware with per-box env locations stamped. **All live-proven,
receipt-backed** (a `prove-zhe` receipt is the single source of "ZHE done").

A box that is standard-prebuilt but interview-incomplete gets **STANDARD_READY**
(floor on disk + chosen artifact + board join proven; registration/routing deferred to
`interviewComplete`) — receipt-backed, with its own column in the fleet aggregate, and
never confused with either the full ZHE or the EXEMPT state.
