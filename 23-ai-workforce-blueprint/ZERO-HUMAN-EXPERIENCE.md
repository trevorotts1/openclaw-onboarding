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
  passes (exit 0). A not-completed box does nothing and fails nothing.
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
  markers. Exempt for not-completed boxes. Mirrored into `~/clawd/fleet-prover/` for the
  fleet operator aggregate (`--with-subprovers` delegates to `prove-floor.py`).
- **`run-full-install.sh` phase 7z** (Skill 32) — runs `prove-zhe.py --local` after the
  full provisioning; records `zheGateStatus` and prints the verdict loud.
- **`scripts/verify-library-gate.sh`** — runs the prover as the **highest-priority
  verdict** (rc 9), alongside the canonical-authoring / role / SOP / trio / boundary gates;
  records `zheStatus`.

**RED-FIRST CONTRACT (plan §6):** the prover is authored RED before everything so each
ZHE step is built to turn it green. The routing marker passes today; the
persona-reflex / full-context-handoff / reporting / platform-facts assertions stay RED
until W5/W6/W7 stamp them via `apply-fleet-standards.sh`. The two gates above therefore
**record + print loud** today but only **hard-fail** the build under `ZHE_ENFORCE=1`,
so they become blocking acceptance gates by flipping one env var at the "flip green"
milestone — without breaking in-flight builds. A hard fail marks the install failed so
the resume cron re-proves on the next update (fail-loud + auto-repair).

---

## Definition of done (the ZHE)

A box that completed the interview gets the full ZHE (enforced, edge-cases handled);
never rewrites floor roles/SOPs (custom-only exception wired to CC + Kanban + personas);
its CEO routes every task to a department with full context + pointer refs; communicates
assignment/start/done with persona + dept + specialist + SOP + role; nothing sticks on
the Kanban; platform-aware with per-box env locations stamped. **All live-proven,
receipt-backed** (a `prove-zhe` receipt is the single source of "ZHE done").
