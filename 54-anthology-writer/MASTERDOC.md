# Anthology Writer — MASTERDOC (SACRED IP + rule→code map)

This is the anonymized canonical method for the Anthology Writer (Skill 54) and
the single human-readable index tying every SACRED rule to the fail-closed prover
that enforces it. **Enforcement, not description:** if a rule is here, a prover
measures it; a model's self-report is never trusted.

## The unit of work

One **contributor**, one **chapter**. An anthology is many contributors; this
skill authors and certifies each chapter independently, so contributors run in
parallel and one blocked chapter never strands the others.

## The pipeline (P0 → P7, no phase skips)

| Phase | Produces | Gate (AF-AW-*) |
|---|---|---|
| P0 INTAKE | `working/intake.json` | INTAKE-MISSING, INTAKE-CREDENTIAL |
| P0A AVATAR | `working/avatar.md` (via Skill 52 handoff + aw-12 extraction) | AVATAR-MISSING, AVATAR-HANDOFF-DRIFT, AVATAR-COPIED |
| P1 FIDELITY | pinned prompts + tone-core lockstep | PROMPT-DRIFT, TONE-DRIFT |
| P2 TONE-AUTHOR | `working/tone-doc.md` | — |
| P3 TONE-QC | tone QC report | TONE-4, TONE-FLOOR |
| P4 TITLE-LOCK | `working/title.json` | TITLE-MISSING |
| P5 CHAPTER-AUTHOR | `working/outline.md` + `working/chapter.md` | — |
| P6 CHAPTER-QC | chapter QC report | CHAP-LEN, VERIFY-BLOCK, PLACEHOLDER, TITLE-LOCK, STORIES, ANTHROPIC, REWRITE-BUDGET |
| P7 DELIVER | `delivery/PROCESS-CERTIFICATE.json` | STAGE-SKIPPED, PROCESS-INTEGRITY |

## The SACRED floors (never floored, reordered, or reinterpreted)

1. **Chapter length:** 2,000–3,500 stripped words — measured, not self-reported.
   Whitespace/filler padding is inert. Exactly ONE chapter per contributor.
2. **Blended tone:** "The {First} {Last} Tone", synthesized from EXACTLY four
   tone-style influence analyses, ≥ 3,000 stripped words (shared tone-core R7).
3. **Title lock:** the contributor's chosen title + subtitle become byte-exact
   invariants carried into the outline AND the chapter; a rewrite can never
   change them.
4. **Story placement:** every non-`N/A` personal-story anchor is provably placed
   in the outline AND the chapter (assigned to a beat before prose is written).
5. **Completion block:** the chapter ends with a `COMPLETION VERIFICATION` block
   (its numbers are ignored; its presence is required).
6. **No placeholders:** no `{{..}}` / `[[..]]` / `<ALLCAPS>` survives into a
   finalized artifact.
7. **Rewrite budget:** at most two rewrites per contributor; a third escalates to
   the owner.
8. **Client sovereignty / NON-Anthropic:** every resolved model id is the
   client's own strongest NON-Anthropic model. No `claude-*` / `anthropic/*` id,
   no operator key, no key taken through intake.

## The tone core (referenced, never re-authored)

The four tone-style analyzers + the blended-tone author live ONCE in
`shared-utils/tone-writing-core/prompts/04..08`. Skill 54 bakes a **lockstep
copy** into `prompts/` and proves it byte-identical at build/CI time
(`verify_tone_core_sync.py`, AF-AW-TONE-DRIFT). A change to the shared core flags
both Skill 54 (Anthology) and Skill 53 (Book) for review. The two are separate
skills sharing one core — never merged (Trevor's standing decision).

## The NON-Anthropic build-fix (source → runtime)

The source anthology workflow pinned every extracted call to an Anthropic model
id and routed through "the client's OpenRouter primary". Those ids are
**capability tiers, not prescriptions**. Skill 54 bakes prompt BODIES only (no
concrete model id anywhere) and resolves the tiers per box:

| Tier | Stages | Resolves to |
|---|---|---|
| HEAVY-WRITER | aw-09 chapter, aw-10 rewrite | client's strongest long-form NON-Anthropic model |
| MID-WRITER | aw-01..08 tone/title/blurb/outline | client's mid NON-Anthropic model |
| RESEARCHER | optional grounding | client's own web-search tool (else `degraded:search`) |
| IMAGE | optional cover | client's own image provider (else `degraded:image`) |

There is NO formatter tier — the five source HTML-formatter LLM calls are
**retired**; formatting is deterministic Python. `aw_build_check.py`
(G-NOANTHROPIC) hard-fails any `/anthropic|claude/i` id in the run ledger, and
`verify.sh` statically scans the shipped skill for any concrete `claude-*` /
`anthropic/*` id.

## Timeout, retry, and degraded behavior

- **Subprocess timeout (AF-AW-PROVER-TIMEOUT):** every `subprocess.call` and
  `subprocess.run` through `_run_prover` and `_run_prover_json` is capped at 300
  seconds. A prover that hangs past this ceiling is killed by the OS and the phase
  fails closed. The stderr diagnostic names the script that hung. The orchestrator
  (`run_anthology.py`) itself is dispatched by `anthology-entry.sh` via `exec` with
  no timeout shell built-in — the 300s per-prover ceiling plus the entry-script
  `trap ... EXIT INT TERM HUP` handler form the entire watchdog surface.
- **Retry on nonzero exit:** a prover that EXITS nonzero (but does not hang past
  the 300s ceiling) is re-launched automatically — up to 3 total attempts with a
  1s then 2s backoff between attempts (`delay = 2 ** attempt` in both
  `_run_prover` and `_run_prover_json`). If all 3 attempts fail, the phase fails
  closed and the final return code is reported to stderr.
- **No automatic retry on timeout:** a timed-out prover is NOT re-launched. The operator must
  inspect the hung prover for deadlocks, infinite loops, or stalled upstream model
  calls, fix the root cause, and re-run through `anthology-entry.sh`. The process
  manifest records the failed phase for audit.
- **Degraded upstream model handling:** the LLM authoring stages (P2, P5) are run
  upstream on the client's NON-Anthropic providers, not by this orchestrator. If an
  upstream model call is unreachable, times out, or returns a non-200 response, the
  authoring sub-agent produces no artifact. The corresponding QC phase sees the
  missing artifact and fails closed (never degraded-open). There is no automatic
  provider fallback — the operator must re-configure the model map via `preflight.sh`
  or re-run the authoring stage on a reachable box.
- **Execution chain (anthology-entry.sh -> run_anthology.py):** `anthology-entry.sh`
  dispatches `run_anthology.py` via `exec` (no subshell) and the entry script's
  `trap ... EXIT INT TERM HUP` cleans up the nonce on any signal. The 300s
  per-prover timeout in `run_anthology.py` is the sole ceiling for provers; the
  entry script does not add a second global timeout because each prover already
  carries its own.
- **Non-watchdog note:** `anthology-entry.sh` itself has no built-in `timeout`
  wrapper. The operator shell can optionally wrap the whole invocation with
  `timeout` (e.g., `timeout 900 bash anthology-entry.sh --run-dir ...`) if a
  run-level ceiling is desired, but this is external to the skill and NOT an engine
  guarantee.
