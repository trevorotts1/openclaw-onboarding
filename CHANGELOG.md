## v13.2.2 — 2026-06-21 — fix(routing): CEO-gate is ROUTER-SCOPED — a personal-assistant-default box is never frozen

v13.1.3 DEFECT-2 broadened the CEO production-lock target from `id=="main"` to "whatever agent is `default:true`". That is wrong on a box whose DEFAULT agent is a hands-on personal assistant (not a router): the broadening clamped the CEO production-lock (`skills:[]` + `tools.deny` of write/edit/exec/browser/image/process + GHL-MCP deny) AND the global PreToolUse intent-gate onto the PA, FREEZING it. v13.2.2 makes the gate ROUTER-SCOPED everywhere: the default agent is gated ONLY when it is also a router; a personal-assistant / owner default agent is never gated. The legitimate router cases (`default:true` agents whose id is `dept-master-orchestrator` or `dept-executive-office`) still gate exactly as before. All generic; no client names.

- **Canonical router identity (single source of truth).** New `CEO_ROUTER_IDS` + `ceo_agent_is_router()` in `hooks/lib-ceo-tool-gate.sh`. An agent is a ROUTER iff ANY of: `is_master === true`, `role === "router"`, or `id ∈ {main, ceo, dept-ceo, master-orchestrator, dept-master-orchestrator, dept-executive-office}`. Every gate-target site embeds an identical `ROUTER_IDS` + `_is_router()` mirror (drift-asserted by the test). The build-time origin (`build-workforce.py`) already gated by router `dept_id` only — this aligns the post-build / verify sites to that same intent.
- **`hooks/ceo-intent-gate.sh` — AGENT-SCOPE self-guard.** Before any production-tool / consent logic, the hook resolves the running agent's identity (from the hook event JSON, then gateway env markers `OPENCLAW_AGENT_ID`/`OPENCLAW_AGENT_ROLE`/`OPENCLAW_AGENT_IS_MASTER`, with a `OPENCLAW_CEO_GATE_SCOPE=router|non-router` override) and `exit 0` (ALLOW) for any agent that is NOT the router. The gate can never fire on a personal-assistant / owner agent. Fails OPEN on the agent-scope guard (a router's actual `tools.deny` is the real brake; the hook is the backstop), while the consent reader still fails CLOSED.
- **`scripts/apply-routing-fix.sh` (Layer 2 skills:[] + Layer 5 tool-gate).** Both layers now gate the default agent ONLY if it is a router; a non-router default agent is SKIPPED with an auditable `PA-freeze guard` log line on both L2 and L5. The legitimate `default:true` router (e.g. `dept-executive-office`) is still gated.
- **`scripts/apply-fleet-standards.sh` (CEO tool-gate re-assert).** The fleet-roll re-assert now SKIPS a non-router default agent (logs the PA-freeze skip) instead of re-asserting the CEO deny onto a PA.
- **`scripts/verify-routing.sh` (G4 / G7 / G8a).** A PA-default-topology box is now a PASSING configuration, not a FATAL. G4 reports `PA_DEFAULT_OK` (the pptx router-deny is N/A on a PA). G7 PASSES on a PA default (and if a SEPARATE router agent also exists, it gate-checks that router instead so a real router is never missed). G8a does NOT force-wire the unscoped PreToolUse hook on a PA-default box (an absent hook there is the correct state → PASS).
- **`scripts/install-ceo-intent-gate.sh`.** No global all-sessions deny: the wired matcher is runtime agent-scoped by the hook's own self-guard. On a PA-default box (no router agent present) the installer SKIPS the matcher wire entirely (belt-and-suspenders); the hook+lib are still staged (harmless — they self-guard and no-op on a non-router).
- **Persistent department-agent spawn (item #5).** SOP-00 gains **R11**: production work is dispatched to the PERSISTENT per-department agent (`agent:<dept>` via the task board), which survives a new owner message — NEVER run as an ephemeral turn-scoped inline child (`controller=agent:main:main`, spawn mode `run`) that dies when the next owner message starts a new turn. The persistent per-department agents already exist (`build-workforce.py`). REPO-SIDE = persistent agents + R11 board-routing doctrine (done). PLATFORM-SIDE = making a *directly-spawned* specialist detached/work-scoped (decoupled from the controlling turn) is a gateway spawn-mode property the strict `AgentEntrySchema.subagents` cannot express — specified for the gateway team in `platform/SPEC-persistent-department-spawn.md`, NOT faked in a script.
- **Tests:** `scripts/test-ceo-tool-gate.sh` extended from 18 → 41 checks. New: I (PA-default box NEVER gated by apply-routing-fix / apply-fleet-standards / verify-routing G4+G7+G8a), J (router-default box — `dept-master-orchestrator`, `dept-executive-office`, `role:router`, `is_master:true` — STILL gated), K (the hook ALLOWs a non-router agent and DENIES the router, routing curl still allowed, scope override honored), L (router-id set canonical + present in all 5 gate sites + `ceo_agent_is_router` behavior). The original H1/H2 (the legitimate `dept-executive-office` default-true gating from v13.1.3) still pass — no regression. `bash -n` clean on all 7 touched shell files; `py_compile` clean. Skill 23 `skill-version.txt` → 13.2.2; SOP-00 → 1.3.0.

## v13.2.1 — 2026-06-21 — fix: CONDITIONAL embedding default (no keyless gemini pin) + smart 3-alias Google-key detection

v13.2.0 (group a) unconditionally pinned `gemini-embedding-2` as the memorySearch embedding default whenever `configure_active_memory` ran. That broke 6 boxes that have NO usable Google/Gemini key — it pinned a model they cannot serve, so the embed index fails on every search. v13.2.1 makes the gemini default CONDITIONAL on a usable key, and the key detection is SMART. All generic; no client names.

- **Smart Google/Gemini key detection (`has_usable_gemini_key`).** A single Google AI Studio credential is the SAME key under THREE env NAMES — `GOOGLE_API_KEY` = `GOOGLE_AI_STUDIO_API_KEY` = `GEMINI_API_KEY` (plus `GOOGLE_GEMINI_API_KEY` / `GOOGLE_GENERATIVE_AI_API_KEY` / `GOOGLE_AI_API_KEY`) — and can live in several stores. A new `install.sh` helper checks ALL of them before ever concluding "no key": the bulletproof `search_env_var` path (live shell env, every `.env`/secrets/`.envrc`/shell-rc file under `$HOME` incl. `~/.openclaw/secrets/.env` + `~/clawd/secrets/.env`, openclaw.json `env.vars`, the `models.providers.google.apiKey` block, plugin configs, secrets.json, deep scan), PLUS `~/.openclaw/workspace/.env`, the VPS host `/docker/<project>/.env` compose env-file, AND the live container env via `docker exec <ctr> printenv`. Every candidate passes `looks_like_real_key` (so a placeholder cannot register as "found").
- **Conditional default in `configure_active_memory` (install.sh).** If a usable Gemini key is found → pin `gemini-embedding-2` @3072 (the v13.2.0 standard). If genuinely NONE is found anywhere → do NOT force gemini: keep the box's EXISTING working memorySearch provider/model when it is already a serveable non-gemini embedding (e.g. `openai/text-embedding-3-small`), else fall back to whatever embedding-capable key the box DOES have (OpenAI → `text-embedding-3-small`; OpenRouter → `openai/text-embedding-3-large`). A box left stranded on a keyless v13.2.0 gemini pin is UN-PINNED to a model it can serve; with no embedding-capable key at all the provider/model are left UNSET rather than pinned to an unservable model. `text-embedding-3-small` is no longer treated as "dying" on a no-gemini box (it is a perfectly serveable OpenAI model — only the gemini-key path upgrades off it).
- **Same conditional logic in Skill 31 `activate-memory-stack.sh`.** The canonical memorySearch block's provider/model/dimensions are now decided from the keys the box can actually serve (same 3-alias × every-store + live-container detection), and the provider-self-loop guard repairs `none`/dying-gemini values to a serveable provider — never unconditionally to gemini. The embed-once corpus-on-main scoping, empty-defaults `extraPaths` bloat guard, and capped embedding cache are all preserved.
- **Test:** `tests/unit/conditional-embedding-default.test.sh` proves both layers — (1) box with only `GEMINI_API_KEY` is detected; (2) box with only `GOOGLE_AI_STUDIO_API_KEY` is STILL detected (alias coverage); (3) box with only `GOOGLE_API_KEY` is detected; (4) box with only an OpenAI key is NOT detected (no false gemini); and end-to-end that the config pins gemini-2 with a key, keeps/falls back to openai without one, un-pins a stranded keyless gemini, and leaves provider UNSET when no embedding key exists. 11/11 checks pass. `bash -n` clean on all touched files; existing `memory-corpus-no-defaults-extrapaths.test.sh` still passes. Skill 31 `skill-version.txt` → v7.2.3.

## v13.2.0 — 2026-06-21 — feat: embedding-prevention bundle + Command-Center duplicate guards + unified short-interview exemption + 12 personal-assistant SOPs

Four independent reliability groups, all generic (no client names). Closes the disk-bloat/embedding-drift class of incidents, hardens Command-Center registration against duplicates, reconciles the interview-completion gate so legitimate short interviews stop false-failing, and expands the personal-assistant SOP coverage.

- **(a) Embedding-prevention bundle (fleet-wide).** Four new health scripts are wired fleet-wide so the memory-DB bloat / re-embedding class of incidents is caught and prevented automatically: `index-model-drift-check` (flags an index built under a different embedding model than the one currently pinned), `orphan-temp-sweep` (reclaims orphaned temp/scratch artifacts left behind by interrupted embed runs), `disk-usage-alert` (thresholded alert before a box fills its disk), and `pre-july14-embedding-migration-check` (proactive guard ahead of the 2026-07-14 hard-shutdown of the legacy embedding model). The default embedding model is now pinned to `gemini-embedding-2` (@3072) so every box converges on one GA model; index scoping is constrained so a shared corpus is no longer re-embedded per department; a provider-self-loop guard prevents the embedding provider from cycling to `none` and corrupting the index; and Time-Machine memory exclusion keeps the memory store out of macOS backups (no backup-driven bloat or lock contention).
- **(b) Command-Center duplicate-registration guards.** Eliminates duplicate Command-Center registrations from re-runs and mid-run crashes: `create-tunnel.sh` now carries a re-POST guard so re-invocation does not create a second tunnel/registration; `run-full-install.sh` phase 6b is gated so it does not re-register an already-registered box; and the social-media-planner registration is made idempotent with crash-window recovery so a crash between submit and confirm cannot leave a half-registered or doubled entry.
- **(c) Unified short-interview exemption.** `23-ai-workforce-blueprint/scripts/qc-interview-completion.py` now recognizes a single unified exemption for legitimately-short interviews — both the legacy pre-standard interview shape and the tailored/founder-self-build path — so a genuinely complete short interview no longer false-fails the completion gate, with no weakening of the full-interview requirement. Backed by `build-state-schema.json` (schema for the exemption/build-state fields) and `test-interview-experience.sh` (regression tests covering the exempt and non-exempt paths).
- **(d) 12 personal-assistant SOPs.** Twelve new SOPs added across the personal-assistant specialists: `task-priority-manager`, `personal-coach`, and `travel-logistics-specialist`, expanding their DMAIC SOP coverage. Additive to Skill 23 (does not modify it).

## v13.1.4 — 2026-06-21 — fix(zhc): py3.9-compat build-state refresh + verify-wiring arg-shift (#293)

Fixes two defects surfaced finishing a real client closeout (build-state schema drift). All generic; no client names.

- **py3.9 compatibility:** `refresh-build-state-from-index.py` used Python 3.10+ `Path | None` union annotations, which raise `TypeError` on the py3.9 interpreters several client boxes resolve to — so the canonical build-state `.id` repair couldn't run (closeout's `verify-wiring` then rc=9 FATAL on legacy slug-keyed dept records). Replaced with `typing.Optional[Path]`.
- **verify-wiring infinite loop:** `verify-wiring.sh` `--allow-missing-config` arg case never shifted, causing an infinite loop when that flag was passed; added the missing `shift`.

## v13.1.3 — 2026-06-20 — fix(fleet-roll): three v13.1.1-roll defects (2026.6.8 schema reject, hardcoded-main gate, stale-checkout updater)

Fixes three defects exposed by the v13.1.1 roll across 27 boxes. All generic; no client names.

- **DEFECT 1 (dominant — blocked 24 boxes): OpenClaw 2026.6.8 rejects `agents.defaults.tools.*`.** At config-validate, 2026.6.8 fails any `agents.defaults.tools.*` key with `agents.defaults: Invalid input`. `apply-fleet-standards.sh` wrote the GOAL-4 no-refusal baseline as `agents.defaults.tools.allow=["*"]`, so the validate-fail rollback restored the backup and the box stayed un-ungated; `verify-routing.sh` G7b then FATAL'd.
  - `scripts/apply-fleet-standards.sh` is now **schema-version-aware** (detects the running gateway via `openclaw --version`; `FLEET_OC_VERSION_OVERRIDE` pins it for tests). On **>= 2026.6.8** it expresses the no-refusal baseline ONLY with keys that validate clean — root `tools.exec.security=full` + `tools.exec.ask=off` + `agents.defaults.subagents.allowAgents=["*"]` + `requireAgentId=false` — and STRIPS any pre-existing `agents.defaults.tools` (self-heals a poison-key box). On **< 2026.6.8 or unknown** it still writes `agents.defaults.tools.allow=["*"]` (legacy-permissive default; validate gate is the backstop). Idempotent; leaves config valid.
  - `scripts/verify-routing.sh` **G7b** now PASSES on the FUNCTIONAL UNGATE (root `tools.exec` full+off + `agents.defaults.subagents` ungate) as the satisfied Goal-4 baseline on 2026.6.8 — the absence of `agents.defaults.tools.allow` is expected there, not a failure. Form A (`agents.defaults.tools.allow`) still passes on older schemas.
- **DEFECT 2: CEO tool-gate (Goal 5) was hardcoded to the `main` agent.** Some boxes' default agent is `dept-executive-office` (`default:true`), which was left ungated. `scripts/apply-routing-fix.sh` (Layer 2 skills:[] + Layer 5 tool-gate), `scripts/verify-routing.sh` (G7), and the `apply-fleet-standards.sh` CEO re-assert now target the box's ACTUAL default agent (`default:true`, else `main`) — `default:true` wins even when a `main` agent is also present. Also fixes a latent `printf '---\n\n'` (`printf: --: invalid option`) abort in apply-routing-fix.sh Layer 1 that aborted the run on stale boxes before the gate applied.
- **DEFECT 3: `update-skills.sh` had no self-sync, wired from a stale checkout, and crashed with `PLATFORM: unbound variable`.** A new `self_sync_guard` runs before any wiring: curl|bash skips (fresh by definition); a clean+current local git checkout proceeds; a dirty/behind checkout **fails loud with exact remediation** (default, non-destructive) or, with `OPENCLAW_UPDATE_AUTO_SYNC=1`, hard-syncs to `origin/main` and re-execs the intended version. A `PLATFORM` guard (`PLATFORM="${PLATFORM:-$OPENCLAW_PLATFORM}"`) is initialized before any use so a bare `$PLATFORM` reference can never abort under `set -u`.
- **Tests:** `scripts/test-ceo-tool-gate.sh` extended with G1/G2 (Defect 1 — 2026.6.8 strip + G7b functional-ungate pass) and H1/H2 (Defect 2 — gate + verify target `dept-executive-office` over a present `main`). All 18 checks pass. `bash -n` clean on all four touched scripts.

## v13.1.2 — 2026-06-20 — fix(zhc): closeout gate regressions — named-set sops/ + old library markers (#291)

Two 2026-06-20 skill-refresh regressions blocked ZHC closeout for clients whose role/SOP content is fully present (prove-floor passes). All generic; no client names.

- **named-set sops/ walked as a role:** `verify-wiring.sh` + `create_role_workspaces.py` walked a dept's named-set `sops/` SOP-library folder as a role, writing a PENDING stub how-to.md and failing rc=2. Both walkers now skip a `sops/` dir holding real SOP docs; genuinely-empty roles still fail.
- **old library-marker regex:** `qc-completeness.sh` LIBRARY_MARKER only matched the new markers, so ~33 real role files carrying the older "Instantiated from role-library vX" / `workforce-provenance source=role-library` markers counted as lib%=0. Broadened the marker regex; the AND-3KB substance floor is unchanged.

## v13.1.1 — 2026-06-20 — feat(skill-23): Department Class-Kit enforcement gate + CI self-test (#290)

Add `qc-class-kit-gate.sh` enforcing Gates A–D (kit completeness; deck ≥20 slides; Notion embedding when a page id is given; structure/auto-fail checks that REJECT text-only pages and placeholder/deferral language), ship `DEPT-KIT-TEMPLATE.md` as the canonical version-controlled standard, and add `.github/workflows/class-kit-gate.yml` self-testing the gate against baked-in GOOD/BAD fixtures. Generic department docs only; no client names.

## v13.1.0 — 2026-06-20 — feat: presentation engines + Ship-Every-Time + fleet ungate + CEO router tool-gate + closeout robustness (#289)

- **Goal 3 (Make the Promise True):** PIPELINE-MANIFEST v14, ordered pitch loop, un-inverted branded-methodology, cost-of-inaction/guarantee/scarcity auto-fails, intelligence + pitch + story engines.
- **Goal 4 (Ship Every Time):** asset-intake + scratch-parser, pitchless-first-class, deterministic `run_signature_deck.py` (owner-auth skip + Kie preflight), overlay path eliminated, no-refusal baseline.
- **Goal 5 (CEO Must Delegate):** CEO tool-gate on real tool names + `route_task` + block-redirect hook + QC provenance gate + owner-consent profile-swap + verify-routing G7–G11.
- **Closeout robustness:** ghost-false-done guard + pending-slots + qc-rate-artifacts (8.5-release). Gate hardening: qc-completeness GATE-SCOPE + verify-library trio scoping.

## v13.0.3 — 2026-06-20 — fix(zhc): closeout robustness

Closeout-pipeline robustness hardening (ghost-false-done guard, pending-slots, QC rate-artifacts) on the path to the v13.1.0 release train.

## v13.0.2 — 2026-06-20 — fix(cron): --json presence check for trigger registration

Cron trigger registration uses a `--json` presence check so an existing trigger is detected reliably (idempotent registration), preventing duplicate or skipped pipeline-trigger crons.

## v13.0.1 — 2026-06-20 — fix(fleet): cron registration fix

Fleet cron-registration fix so pipeline trigger crons register correctly across boxes.

## v13.0.0 — 2026-06-20 — Zero-Human-Experience closeout reliability + presentation gate-measurement fixes

Guarantees every client who completes the AI Workforce interview reliably receives their Zero-Human-Experience closeout, and fixes the build-completeness gate so genuinely-complete workforces stop reading as incomplete.

- **Closeout trigger reliability**: new `scripts/ensure-pipeline-crons.sh` (idempotent registrar of all pipeline trigger crons) is now called by BOTH `install.sh` and `update-skills.sh` (closes the gap where the hot-patch path shipped files but no triggers); new install-time `37-zhc-closeout/scripts/install-closeout-resume-cron.sh` makes the closeout trigger redundant; `install.sh` Step-13 operator-chat hard-abort relaxed to log+continue (was stranding boxes); new `37-zhc-closeout/scripts/qc-closeout-wiring.sh` per-box gate fails loud if closeout would silently never fire.
- **Six gate-measurement bug fixes** (complete workforces were false-failing the closeout completeness gate): LIBRARY_MARKER regex drift (now recognizes the `workforce-provenance: source=role-library` marker; >=3072B floor unchanged); lib% denominator no longer counts non-role dirs (sops/scripts); trio gate counts subdir-stored roles (not just `.md` files); jq slug-null state-write crash guarded; SOP-substance TOKEN_LEAK regex no longer nukes credit for `{{X}}` single-letter example variables (>=3-char real field tokens only); graphics `_index.json` phantom (13 byte-identical `ROLE--` twins) deduped.
- **Gate scope (client-facing)**: never-client-facing meta-roles (`devils-advocate`, `sop-writer`) exempted from the per-role SOP-substance floor; trio gate scoped to departments whose canonical roster includes a trio; personal-assistant reconciled to its canonical templated roster. No-weakening preserved.
- **11 client-facing role templates authored** (7 thin workflow roles + 4 presentations QC sub-specialists) so every client gets them via deterministic template-copy.

## v12.43.0 — 2026-06-19 — fix(install): IS_VPS unbound variable aborted fresh installs with zero skills installed

**Bug:** `install.sh` line 5821 referenced `$IS_VPS` inside an `if` condition. The variable `IS_VPS` is never assigned anywhere in `install.sh` — platform detection sets and exports `OPENCLAW_PLATFORM` (values: `vps` or `mac`) at line 42. Because `set -u` is active at that point in the script, any expansion of the unbound `$IS_VPS` aborted the installer immediately with `IS_VPS: unbound variable`. This caused fresh Mac installs to exit with zero skills installed and no `.onboarding-version` stamp written. Reproduced on a fresh Mac install.

**Fix:** Changed `[ "$IS_VPS" = "true" ]` to `[ "$OPENCLAW_PLATFORM" = "vps" ]`. `OPENCLAW_PLATFORM` is the canonical platform variable exported at line 42; its value is `vps` on VPS boxes and `mac` on Mac boxes. No other IS_VPS references exist in install.sh (confirmed by grep). The secondary guard `[ -d "/docker" ]` is unchanged and continues to catch Hostinger Docker environments on VPS.

**Proof:** `bash -n install.sh` exits 0. Under `bash -u`, the fixed construct `export OPENCLAW_PLATFORM=mac; if [ "$OPENCLAW_PLATFORM" = "vps" ] || [ -d /docker ]; then echo vps; else echo mac; fi` prints `mac` with no error; the old construct `if [ "$IS_VPS" = "true" ]; then :; fi` aborts with `IS_VPS: unbound variable`.

**Impact:** Every fresh install on a Mac box hit this abort at the WhatsApp-ban layer (line 5821), after skill-copying had already run but before `.onboarding-version` was stamped. The installer exited with a non-zero code, leaving the box with skills on disk but no onboarding-version marker and no final kickoff fired.

## v12.42.0 — 2026-06-19 — fix(skill-content-hash): exclude __pycache__/*.pyc/*.pyo + .DS_Store from A3 content hash — some built boxes that ran skill Python at install could not stamp

**Bug (introduced before v12.39.0):** `scripts/skill-content-hash.sh` hashes every non-excluded file under each numbered skill directory. Its `_should_exclude()` function did not exclude `__pycache__/` directories or `*.pyc`/`*.pyo` files. At install time, skill-23's Python scripts execute and Python writes `*/scripts/__pycache__/*.cpython-3XX.pyc` and `*/lib/__pycache__/*.pyc` into the destination skill directory. Those bytecode files (a) are absent from the source tree, (b) embed a per-run source hash/mtime that changes every install, and (c) vary by Python version. Because the source manifest never contains these files but the destination directory does, the A3 gate computed `src_digest != dest_digest` non-deterministically — blocking the `.onboarding-version` stamp write on some built boxes even when all shipped content was fully correct.

**Fix (3 additions to `_should_exclude()`):**
1. Path-based exclusion: `*/__pycache__/*) return 0 ;;` — any file under a `__pycache__` directory at any depth is excluded from the hash.
2. Basename exclusion: `*.pyc|*.pyo) return 0 ;;` — compiled/optimised Python bytecode files, which may appear outside `__pycache__` on older toolchains.
3. Basename exclusion: `.DS_Store) return 0 ;;` — macOS Finder metadata, which is OS-generated and not shipped content.

No existing excludes were removed or weakened. The hashing algorithm is unchanged. All `.py` source files remain in scope, so a missing or truncated source script still changes the digest and fails the gate.

**Proof (replayed against a temp copy of skill-23):**
- Copy A = clean. Copy B = clean + `scripts/__pycache__/x.cpython-314.pyc` and `lib/__pycache__/y.cpython-314.pyc` injected with random bytes.
- Round 1: `digest(A) = f65f06c607a43c042d8154e3659545e538637c661c1f1e2475d62d2600856dcb`, `digest(B) = f65f06c607a43c042d8154e3659545e538637c661c1f1e2475d62d2600856dcb` — equal (PASS).
- Round 2 (different random bytes): `digest(A) = f65f06c607a43c042d8154e3659545e538637c661c1f1e2475d62d2600856dcb`, `digest(B) = f65f06c607a43c042d8154e3659545e538637c661c1f1e2475d62d2600856dcb` — equal (PASS, run-to-run determinism confirmed).
- Gate still works: after deleting a real source `.md` from copy B, `digest(B) = d24668424e112d6d77bb0d764070d8de27d7771bd39fc903230d4c46737e2a3c` differs from `digest(A)` (PASS).

**Impact:** Some built boxes that executed skill-23 Python scripts at install time accumulated `__pycache__/*.pyc` files in the destination skill directory, causing the A3 content gate to withhold the stamp non-deterministically on subsequent updater runs. After this fix the hash is stable across installs and Python versions.

## v12.41.0 — 2026-06-19 — fix(update-skills): set -e hardening of stale-detection and A3 content-gate block — three grep pipelines and detect-stale exit-10 now safe under set -euo pipefail

**Bug (introduced v12.27.0):** `update-skills.sh` runs under `set -euo pipefail` from line 35. The stale-detection block assigned the output of `detect-stale-artifacts.py` directly: `DETECT_OUT="$(python3 ... )"`. That script intentionally exits 10 when actionable artifacts exist. Under `set -e`, a bare command-substitution assignment inherits the subprocess exit code, so exit 10 aborted the script at that line — before `DETECT_RC=$?` was captured, before the rc-10 handler ran, and before the `.onboarding-version` stamp write at line 1541. Skills installed cleanly (46 of them) and the A3 gate passed, but the stamp was never written.

Two additional unguarded grep pipelines in the same block (`dest_digest=$(... | grep ...)` in the A3 loop, `_TREE_SHA=$(... | grep ...)` in the manifest-write section) would abort the script on a no-match because `grep` exits 1 when no lines match and `pipefail` propagates that through the pipeline.

**Fixes (3 lines):**
1. Replaced the two-line `DETECT_OUT=... ; DETECT_RC=$?` construct with the if-idiom (`if DETECT_OUT="$(...)"; then DETECT_RC=0; else DETECT_RC=$?; fi`). The if-condition is exempt from `set -e`, so exit 10 is caught and `$DETECT_RC` is correctly set to 10. Downstream rc-10 handler and stamp write are now reachable.
2. Added `|| true` to `dest_digest=$(... | grep "^${skill_name}|" ...)` in the A3 loop. When a skill is absent from the destination manifest, grep exits 1; the guard lets the assignment produce an empty string, which the existing `[ -z "$dest_digest" ]` check then correctly classifies as a mismatch.
3. Added `|| true` to `_TREE_SHA=$(... | grep "^__TREE_SHA__|" ...)` in the manifest companion-write section. If the manifest contains no `__TREE_SHA__` row, grep exits 1; the guard lets `_TREE_SHA` be empty, and the existing `${_TREE_SHA:-unknown}` expansion handles the fallback.

**Proof (replayed in bash -euo pipefail):**
- Old construct: `DETECT_OUT="$(stub_exit10)"; echo NEXT` — NEXT never printed; shell exits 10.
- New construct: `if DETECT_OUT="$(stub_exit10)"; then DETECT_RC=0; else DETECT_RC=$?; fi; echo "SURVIVED rc=$DETECT_RC"` — prints `SURVIVED rc=10`.
- Unguarded grep no-match: `x=$(echo "a|1" | grep "^z|" | cut -d'|' -f2 | head -1)` — exits 1, script aborts.
- Guarded: `x=$(... || true)` — exits 0, `x` is empty string.

**Impact:** Boxes with detect-stale-artifacts.py returning rc 10 (actionable stale artifacts present) will now correctly write the `.onboarding-version` stamp after a successful install.

## v12.40.0 — 2026-06-19 — fix(update-skills): PLATFORM unbound-variable crash — built boxes were stuck at their prior version

**Bug (introduced v12.27.0):** `update-skills.sh` referenced `$PLATFORM` at the stale-artifact detection block (line 1431 of the pre-fix file) but that variable was never assigned anywhere in the script. Under `set -euo pipefail` (active from line 35), any reference to an unset variable aborts with "PLATFORM: unbound variable" and exits 1. The `.onboarding-version` stamp write sits ~110 lines later (after the A3 content gate), so the stamp was never written even when all skills installed cleanly and the A3 gate passed. Result: fully-built boxes were permanently stuck reporting their old version; re-runs of `update-skills.sh` always crashed before the stamp was written.

**Root cause:** The script exports `OPENCLAW_PLATFORM` unconditionally at line 17 (always `vps` or `mac`) and `OC_PLATFORM` conditionally in the no-bootstrap fallback branch. The stale-artifact block mistakenly used the bare name `PLATFORM` which exists in neither branch.

**Fix:** Changed line 1431 from `if [ "$PLATFORM" = "vps" ]; then` to `if [ "$OPENCLAW_PLATFORM" = "vps" ]; then`. Confirmed with a full grep that this was the only bare `$PLATFORM` / `${PLATFORM}` reference in the script.

**Proof:**
- `bash -n update-skills.sh` exits 0.
- Under `bash -u` with `OPENCLAW_PLATFORM=vps` and `PLATFORM` unset: fixed code exits 0 and sets `OC_WORKSPACE=/data/.openclaw/workspace`.
- Under `bash -u` with `PLATFORM` unset: old code exits 127 with "PLATFORM: unbound variable".

**Impact:** Built boxes whose `.onboarding-version` stamp was never updated will stamp correctly on the next `update-skills.sh` run.

## v12.39.0 — 2026-06-19 — A3 content-gate hash-race fix: exclude volatile generated files from both sides of the SRC/DEST comparison

Fleet-wide bug fix for the A3 integrity gate in `update-skills.sh`. The gate computes a SRC digest of each skill's content (from the freshly downloaded source tree) before the install copy loop, then computes a DEST digest of the installed skill afterward. A spurious mismatch could occur because `hash-content-manifest.py` rewrites `templates/role-library/_index.json` (updating `content_hashed_at` / `generated_at` timestamps) after the copy but before the DEST hash is computed — so the DEST view includes modified timestamps not present in the SRC view. This caused the gate to fail and refuse to write the `.onboarding-version` stamp even when all real content was correctly installed.

**Root cause**: `scripts/skill-content-hash.sh`'s `_should_exclude()` function excluded `.wired-*`, `skill-version.txt`, `.onboarding-version`, `.onboarding-content-manifest.json` but NOT the install-time-regenerated generated artifacts (`_index.json`, `_qc-summary.md`, `how-to-use-this-department.md`).

**Fix**: Added those three generated-artifact filenames to `_should_exclude()` with clear comments explaining why each is safe to exclude. The fix is applied consistently to BOTH sides of the A3 comparison (both SRC and DEST calls to `skill-content-hash.sh` use the same script, so adding to `_should_exclude` fixes both sides simultaneously). The gate still detects a real content mismatch — all non-generated role, SOP, and persona `.md` files remain in scope.

**Simulation proof** (run locally):
- Test 1 (correct install passes): SRC digest == DEST digest `0755bd36e2630564a22d52d7b019f6ba972bf5087c420916e0dc7081c11fac76` after mutating `_index.json` + `_qc-summary.md` + `how-to-use-this-department.md` in DEST. PASS.
- Test 2 (real mismatch detected): deleting `account-management/client-relationship-manager.md` from DEST changes digest to `26ea7c16805bd96cfa42dae8653f3630ac8be9e89ce3256a71cf5fe03f61f101`. PASS.

**Impact**: Boxes whose `.onboarding-version` stamp was never written despite a correct install (observed intermittently — some boxes hit the race repeatedly before passing, and at least one never recovered) will stamp correctly on the next `update-skills.sh` run.

## v12.38.0 — 2026-06-19 — Teleprompter upgrade: speed-control fix, SPOKEN/TRADITIONAL dual mode, fuzzy already-spoken highlight, feature-gap fixes

Teleprompter rebuilt and self-verified (build_teleprompter.py + teleprompter SOP/role updates):

- **Speed-control fix (O1)**: sub-pixel accumulator + delta-time clamp eliminates scroll jitter; curved 18–240 px/s range with clock reset on every mode transition. Speed changes now take effect immediately without a reset.
- **SPOKEN/TRADITIONAL dual mode (O2)**: Web Speech API voice-following mode (tracks spoken word and auto-scrolls to match) alongside fixed-speed TRADITIONAL mode; runtime toggle with fallback to fixed-speed when the browser lacks Web Speech support.
- **Fuzzy already-spoken highlight (O3)**: two-tier highlight (current word + surrounding context window); fuzzy string alignment means the highlight recovers gracefully from recognition errors and partial words rather than losing position.
- **Feature-gap fixes (O4)**: clicker-key navigation (PageUp/PageDown/arrow keys advance cue points), eye-line guide overlay (fixed horizontal bar at reading position), vertical mirror mode, and status chip showing current mode + recognition confidence.

Merged from main: v12.36.0 (AF-DARK-SLIDE gate) + v12.37.0 (5 deck-quality gates + Guard A green). All five presentation gates present; Guard A exits 0; all verification gates pass.

## v12.37.0 — 2026-06-19 — Guard A green: emit_af_coverage probes for 5 new gates (including AF-DARK-SLIDE from main) + _slide_dominant_colors Pillow 11.x palette-length fix

Two concrete bugs found by independent audit, both fixed:

- **Bug 1 (Guard A red — BUG 1)**: `emit_af_coverage()` in `test_preflight.py` had standalone `test_check_*()` functions for the 4 new gates (AF-VISUAL-VARIETY, AF-PACKAGE-CLEAN, AF-IMAGE-QC-RAN, AF-BRAND-CONSISTENCY) but NO probes in `emit_af_coverage()` — the ONLY producer of `working/af-coverage.json` that `gate_integrity_check.py` (Guard A) reads. Guard A was exiting 1 with "4 UNTESTED violations". Fixed: added 4 deliberate-failure probes in `emit_af_coverage()` that drive each gate to a FAIL result and record the AF code via the `record()` helper. AF-DARK-SLIDE (merged from main) also wired into emit_af_coverage. The triggered set grows to 23 codes; Guard A now exits 0.
- **Bug 2 (AF-BRAND-CONSISTENCY no-op)**: `_slide_dominant_colors()` used `for i in range(64)` after `quantize(colors=64)`, but Pillow 11.x returns a SHORT palette for low-colour images (e.g. a solid fill yields `len(palette)==3`). Indexing `palette[i*3]` for `i>=1` raised `IndexError`; the bare `except Exception` swallowed it and returned `[]`, so `check_brand_consistency()` treated every slide as "skip" and could NEVER fail. Fixed: bounded the loop to `len(palette)//3`; separated the `ImportError` (PIL absent -> silent defer) from real errors (logged to stderr, return `[]` -- callers skip slides where dominant==[]).

Merge: v12.36.0 from main (AF-DARK-SLIDE gate) merged into deck-quality-gates branch. All five gates now present; manifest_version bumped to 12.

Verification (all from the scripts dir):
- `python3 test_preflight.py` -> exit 0, 23 codes triggered in af-coverage.
- `python3 gate_integrity_check.py` -> exit 0 (Guard A green, 23/23 codes).
- `python3 sync_check.py` -> exit 0.
- `check_brand_consistency` with a solid-magenta slide vs navy/gold palette returns AF-BRAND-CONSISTENCY (was: always return "").

## v12.36.0 — 2026-06-19 — Deck quality enforcement gates + No-dark-slides rule (AF-VISUAL-VARIETY, AF-PACKAGE-CLEAN, AF-IMAGE-QC-RAN, AF-BRAND-CONSISTENCY, AF-DARK-SLIDE)

Five enforcement gates total (4 from deck-quality-gates branch + AF-DARK-SLIDE from main). Each gate has a concrete Python checker in `build_deck.py`, a manifest entry in `PIPELINE-MANIFEST.json`, a row in the Section-5 `MASTER-QC-AUTOFAIL-RULESET.md` table, a negative test in `test_preflight.py`, and is wired into both `PREFLIGHT_REQUIRED` (where conditional) and `run_postflight_gate`. `sync_check.py` exits 0 (in-sync). Skill-23 bumped to 2.1.0.

- **AF-VISUAL-VARIETY** (`check_visual_variety`): rejects an all-dark monotone deck -- fires when >= 90% of rendered slides share one dominant background hue bucket OR >= 90% are below the dark-luma threshold (0.30) with < 10% light/break slides. Blocks an all-navy 35-slide deck (mean luma < 0.18, gold-on-navy contrast ~2.1:1 WCAG fail). Defers pre-render.
- **AF-PACKAGE-CLEAN** (`check_package_cleanliness`): the delivered bundle must contain ONLY canonical deliverable files. Fails on any `.py`, `.sh`, `~$*` Office lock/temp file, `tasks/` directory, `task_*.json`, or numbered intermediate `.md` draft. Example rejected artifacts: build_pptx.py, poll_images.py, download_images.sh, tasks/, ~$WIB-Business-Function-Fidelity.pptx. Fires at postflight.
- **AF-IMAGE-QC-RAN** (`check_image_qc_present`): the image-QC report must exist, be NEWER than the rendered PNGs (staleness check), and carry a per-slide PASS/FAIL row for every rendered slide. A stale or rubber-stamped report (no slides[] array) fails loud. Defers pre-render; defers on absent report (AF-IMAGE-QC owns absence).
- **AF-BRAND-CONSISTENCY** (`check_brand_consistency`): every rendered slide's dominant palette must fall within the client's declared brand token set (intake.json brand.palette). Slides whose ALL sampled dominant colors exceed BRAND_CONSISTENCY_TOLERANCE (80 RGB units) from every brand token are flagged. Closes the off-brand stock-imagery failure (fantasy castle / sunrise against navy/gold). Defers when no palette declared or no renders.
- **AF-DARK-SLIDE** (`_chk_no_dark_slides`, merged from main): presentation slides MUST use LIGHT backgrounds by default; DARK/black-background slides are NOT allowed unless the client explicitly requests a dark theme (client_dark_theme flag in intake.json). Written into SOP-SLIDE-00 (both ruleset copies) + slide-image-creator / typography / slide-copywriter / director SOPs.

## v12.35.0 — 2026-06-19 — System-wide add-handling: AUTO-REGISTER helper + library-lockstep backstop (every department)

Generalizes the presentation-only `sync_check` lockstep to the WHOLE role/SOP/persona/department library. The role library's single machine source of truth is `templates/role-library/_index.json` — everything downstream (`create_role_workspaces.library_lookup`, the materializer, the content-hash manifest, the repo-consistency gate, Command-Center wiring) reads the index, never the raw files. So a "half-add" — a role/SOP/persona/dept FILE added without its `_index.json` registration, or a stale entry whose file was renamed/removed — was invisible to the build and slipped through CI. This closes that, system-wide.

- **AUTO-REGISTER helper (NEW)**: `23-ai-workforce-blueprint/scripts/register-library-additions.py` — an idempotent disk→index reconciler for ANY department. Discovers every canonical role file (flat `<dept>/<slug>.md` OR folder `<dept>/<slug>/how-to.md`), ADDS a `roles[]` entry + dept membership for any role missing from the index (preserving existing rich metadata — never clobbers), recomputes `total_roles`/`total_departments`/per-dept `count`, then chains `tag_role_classes.py` (capability_class) + `hash-content-manifest.py` (content_sha restamp) so the whole manifest is current. `--check` (CI), `--apply`, `--prune-duplicate-residue`.
- **AUTO-PROPAGATE wiring**: `add-role.sh` now scaffolds a library `how-to.md` stub and runs the reconciler so a single add yields a COMPLETE `roles[]` entry (not membership-without-a-file); `32-command-center-setup/scripts/sync-extensions.sh --converge` runs the reconciler (Step 2b-pre) BEFORE invariant-validation/propagation so new library roles are registered before they materialize into client workspaces (rosters are already regenerated every materialize run by `create_role_workspaces.regenerate_department_roster`).
- **BACKSTOP (NEW)**: `register-library-additions.py --check` is wired into `qc-static.yml` and a dedicated `library-lockstep.yml` workflow; it FAILS LOUD (exit 7) on any half-add in any dept — unregistered file, dead entry, duplicate-residue (flat `.md` beside a canonical folder-form role), triple-hyphen orphan, or count drift. `test-library-register.sh` (NEW) proves the gate bites on all of those classes and heals via `--apply`.
- **Cleaned pre-existing half-adds**: removed 14 duplicate-residue flat role files (e.g. `engineering/qa-engineer.md` beside the canonical `engineering/qa-engineer/how-to.md`) and 1 triple-hyphen orphan draft (`legal-compliance/qc-specialist---legal.md`); content manifest re-stamped. On the merged tree (rebased onto the v12.34.0 Presentation Quality Overhaul) `total_roles` is 428 — the v12.34.0 overhaul's 5 new presentation roles plus the cleaned library.

## v12.34.0 — 2026-06-18 — Presentation Quality Overhaul: re-sequenced flow + 5 QC roles + duration/pitch/creativity gates

- Flow re-sequenced so each QC follows its artifact (copy-QC after copy, prompt-QC after prompt-authoring, image-QC after render, typography-QC after design, speech-QC after speech).
- Five independent QC functions with rubric SOPs + independent-reviewer requirement; new prompt-author role; image-prompt floor reconciled to 5000.
- Duration-driven intake + AF-SLIDE-COUNT-FLOOR (a 30-min/10-slide deck auto-fails); AF-PITCH-MISSING (offer ladder + re-pitch required); AF-CREATIVITY (reject template-sameness/cliche). manifest_version 10; each gate has a negative test (Guard A).

## v12.33.0 — 2026-06-18 — Presentation pipeline hardening: process gate, QC-independence, prevention guards, deps

Presentation department — the deck build now hard-fails (non-zero exit) on any skipped mandatory stage, and the gate system is protected against future "described-but-unenforced" gaps:

- **Process gate / self-healing**: `AF-I14` (rendered slides must be real KIE-baked images, not placeholders → postflight exit 5), the research-cited Category G/H/I gate (preflight exit 3), and the postflight bundle-completeness gate (`AF-BUNDLE-COMPLETE`) all hard-fail on a skipped stage. The per-slide render loop retries with backoff (self-healing) and stops + escalates the exact reason on a genuine blocker (e.g. no KIE key) rather than silent-skipping.
- **QC independence (`AF-QC-INDEPENDENCE`, NEW)**: a copy-QC report self-graded by the builder (`graded_by`/`author`/`reviewer` == the builder, or `self_graded:true`, or no independent-reviewer provenance) is now rejected (preflight exit 3). Registered in `PIPELINE-MANIFEST.json` + both `MASTER-QC-AUTOFAIL-RULESET.md` copies (sync_check lockstep → manifest_version 9, 47 autofails) + a negative test in `test_preflight.py`.
- **Hook-doctrine reconciliation (M4/L2)**: the retired hook≥7 floor is fully removed from live instructions across the dept (`build_deck.py` + `presenter-coach.md` reconciled to the 3–4 band); remaining "7" mentions are retirement/history context only.
- **Prevention guards (NEW)**: `gate_integrity_check.py` (Guard A) fails CI if any build_deck-enforced autofail lacks an enforcing symbol or a negative test that triggers it (via `test_preflight.py`'s af-coverage cross-check); `doctrine_residual_check.py` + `retired-doctrine-patterns.json` (Guard B) fail CI on any live reappearance of a retired doctrine value; the promotion rule ("a described rule is not enforced") is documented in `QC-PROTOCOL.md` + the dept how-to. Both wired into `presentations-lockstep.yml`.
- **Runtime deps**: `install.sh` installs the presentation toolchain (LibreOffice/soffice, poppler/pdftoppm, reportlab, python-pptx) on Mac + VPS-durable via openclaw cron; the qc-completeness gate hard-fails on a missing dep; new CI guard (`presentation-deps-gate.yml`).

## v12.32.0 — 2026-06-18 — Operator co-mingling fix

Fleet Operator Co-Mingling Audit remediation — client boxes no longer ship the operator's personal chat as a proactive send-target or routed worker:

- Client boxes now ship **reply-to-sender + owner-only** routing: the materialized routing docs (TEAM_CONFIG.md and the skill-15 client-box stamping blocks) carry only the owner placeholder, never an operator Telegram ID. Client agents reply to whoever messaged them and route work to the owner alone.
- The **operator dispatcher roster is gated to the operator box only** (`IS_OPERATOR_BOX=1`). On any client box the dispatcher table is absent; the skill-15 QC Hard Gate 6 fails the build if an operator ID appears in client-box routing, and skips on the operator box where the roster is legitimate.
- **Operator escalation is opt-in** via `OPERATOR_ESCALATION_CHAT_ID` (default OFF). There is no hardcoded `5252140759` fallback anywhere — the central resolver `shared-utils/operator-chat-id.sh` defaults to empty, so escalation only fires when the operator explicitly configures the key.
- New **`no-operator-comingle-template` CI guard** (`tests/unit/no-operator-comingle-template.test.sh` + `.github/workflows/cron-owner-chat-guard.yml`) is the upstream backstop: it fails the build if any script reintroduces an operator ID as a send-target fallback default, or if a client routing template lists an operator ID as a routed worker.
- **Operator inbound access preserved**: operator IDs remain in `channels.telegram.allowFrom` (legitimate inbound DMs via the isolated `remote-rescue` agent). Only the outbound/proactive co-mingling was removed; inbound operator access is unchanged.

## v12.31.1 — 2026-06-18 — content-manifest restamp + QC-static repo-consistency fix

- Content-manifest restamp + QC-static repo-consistency fix for the v12.31.0 presentation edits. The v12.31.0 commit restamped `23-ai-workforce-blueprint/templates/role-library/_index.json` (a Skill-23 file) without moving the skill version, tripping the version-consistency guards (G3 "skill content change requires skill-version.txt bump" + the "9 markers must agree / skill-version.txt == /version" rule). This patch bumps the whole version in lockstep so all 9 markers + `cc-compat.json onboardingVersion` read `v12.31.1`, and re-runs `hash-content-manifest.py` so the per-artifact content_sha manifest stays consistent. No functional change beyond v12.31.0.



## v12.31.0 — 2026-06-18 — Presentation Friday-critical fixes + roster-regen materialization fix

Presentation pipeline (Friday-critical):
- Deleted the legacy `23-ai-workforce-blueprint/templates/presentation-render/build_deck.py`; the canonical renderer is `templates/role-library/presentations/scripts/build_deck.py`. Cleaned the now-dead `presentation-render/build_deck.py` references in `docs/LEGACY-RETIREMENT.md` and the three AF3 retirement-allowlist locations in `.github/workflows/qc-static.yml`.
- PIPELINE-MANIFEST.json bumped to manifest_version 7 with the new autofails wired in (AF additions) and the role roster reconciled — `sync_check.py` now reports IN SYNC (11 phases, 45 autofails, 29 roles).
- ROLE-23 registration: the missing presentations role is now registered in the manifest/roster so the lockstep check passes.
- Infographic-owner ownership corrected and ROLE-21 duplicate registration de-duplicated in the roster.
- Research routing: the AF-RESEARCH-GATE (`_chk_research_brief`) now requires Deep-Research categories G/H/I/K/L to be present AND carry real (non-placeholder) bodies before `research_complete:true` is honoured; `test_preflight.py`'s CASE2 fixture was updated to populate those five sections (the gate itself was NOT weakened). All preflight + postflight self-tests pass (exit 0).
- Teleprompter publish uses `CLOUDFLARE_ZHW_ACCOUNT_ID` (the Zero Human Workforce fleet account, distinct from the per-client `CLOUDFLARE_ACCOUNT_ID`) for the central R2 `zhw-teleprompter` bucket PutObject.
- Added `.github/workflows/presentations-lockstep.yml` so CI runs `sync_check.py` (renderer ↔ manifest ↔ roster ↔ SOP lockstep) on every change.

Workforce build:
- Roster-regen materialization fix in the department roster regeneration path (`regenerate-dept-roster.py` + build-workforce / create_role_workspaces) so the regenerated department roster is actually materialized on the box.

## Historical release backfill — CHANGELOG headers for previously-untracked annotated tags

## v12.19.0 — 2026-06-16 — historical release (backfilled changelog entry)
## v12.18.1 — 2026-06-16 — historical release (backfilled changelog entry)
## v12.17.4 — 2026-06-16 — historical release (backfilled changelog entry)
## v12.17.1 — 2026-06-15 — historical release (backfilled changelog entry)
## v12.16.2 — 2026-06-15 — historical release (backfilled changelog entry)
## v12.16.1 — 2026-06-15 — historical release (backfilled changelog entry)
## v12.16.0 — 2026-06-15 — historical release (backfilled changelog entry)
## v12.15.2 — 2026-06-15 — historical release (backfilled changelog entry)
## v12.15.1 — 2026-06-15 — historical release (backfilled changelog entry)
## v12.14.5 — 2026-06-15 — historical release (backfilled changelog entry)
## v12.14.4 — 2026-06-15 — historical release (backfilled changelog entry)
## v12.14.3 — 2026-06-15 — historical release (backfilled changelog entry)
## v12.14.2 — 2026-06-15 — historical release (backfilled changelog entry)
## v12.14.1 — 2026-06-15 — historical release (backfilled changelog entry)
## v12.14.0 — 2026-06-15 — historical release (backfilled changelog entry)
## v12.13.0 — 2026-06-15 — historical release (backfilled changelog entry)
## v12.12.1 — 2026-06-15 — historical release (backfilled changelog entry)
## v12.12.0 — 2026-06-15 — historical release (backfilled changelog entry)
## v12.10.0 — 2026-06-15 — historical release (backfilled changelog entry)
## v12.9.9 — 2026-06-15 — historical release (backfilled changelog entry)
## v12.9.8 — 2026-06-14 — historical release (backfilled changelog entry)
## v12.9.7 — 2026-06-14 — historical release (backfilled changelog entry)
## v12.9.6 — 2026-06-14 — historical release (backfilled changelog entry)
## v12.9.5 — 2026-06-14 — historical release (backfilled changelog entry)
## v12.9.4 — 2026-06-14 — historical release (backfilled changelog entry)
## v12.9.3 — 2026-06-14 — historical release (backfilled changelog entry)
## v12.9.2 — 2026-06-14 — historical release (backfilled changelog entry)
## v12.9.0 — 2026-06-14 — historical release (backfilled changelog entry)
## v12.8.3 — 2026-06-14 — historical release (backfilled changelog entry)
## v12.8.1 — 2026-06-14 — historical release (backfilled changelog entry)
## v12.7.2 — 2026-06-14 — historical release (backfilled changelog entry)
## v12.7.1 — 2026-06-14 — historical release (backfilled changelog entry)
## v12.6.2 — 2026-06-14 — historical release (backfilled changelog entry)
## v12.6.1 — 2026-06-14 — historical release (backfilled changelog entry)
## v12.6.0 — 2026-06-14 — historical release (backfilled changelog entry)
## v12.5.0 — 2026-06-14 — historical release (backfilled changelog entry)
## v12.4.7 — 2026-06-14 — historical release (backfilled changelog entry)
## v12.4.4 — 2026-06-14 — historical release (backfilled changelog entry)
## v12.4.3 — 2026-06-14 — historical release (backfilled changelog entry)
## v12.4.2 — 2026-06-14 — historical release (backfilled changelog entry)
## v12.4.1 — 2026-06-14 — historical release (backfilled changelog entry)
## v12.3.11 — 2026-06-13 — historical release (backfilled changelog entry)
## v12.3.10 — 2026-06-13 — historical release (backfilled changelog entry)
## v12.3.9 — 2026-06-13 — historical release (backfilled changelog entry)
## v12.3.8 — 2026-06-13 — historical release (backfilled changelog entry)
## v12.3.7 — 2026-06-13 — historical release (backfilled changelog entry)
## v12.3.6 — 2026-06-13 — historical release (backfilled changelog entry)
## v12.3.5 — 2026-06-13 — historical release (backfilled changelog entry)
## v12.3.4 — 2026-06-13 — historical release (backfilled changelog entry)
## v12.3.3 — 2026-06-13 — historical release (backfilled changelog entry)
## v12.3.2 — 2026-06-13 — historical release (backfilled changelog entry)
## v12.3.1 — 2026-06-13 — historical release (backfilled changelog entry)
## v12.3.0 — 2026-06-13 — historical release (backfilled changelog entry)
## v12.2.0 — 2026-06-12 — historical release (backfilled changelog entry)
## v12.1.1 — 2026-06-12 — historical release (backfilled changelog entry)
## v12.1.0 — 2026-06-12 — historical release (backfilled changelog entry)
## v12.0.0 — 2026-06-12 — historical release (backfilled changelog entry)
## v11.20.0 — 2026-06-11 — historical release (backfilled changelog entry)
## v11.19.0 — 2026-06-11 — historical release (backfilled changelog entry)
## v11.18.5 — 2026-06-11 — historical release (backfilled changelog entry)
## v11.18.3 — 2026-06-11 — historical release (backfilled changelog entry)
## v11.18.0 — 2026-06-11 — historical release (backfilled changelog entry)
## v11.17.2 — 2026-06-11 — historical release (backfilled changelog entry)
## v11.17.1 — 2026-06-11 — historical release (backfilled changelog entry)
## v11.17.0 — 2026-06-11 — historical release (backfilled changelog entry)
## v11.16.0 — 2026-06-11 — historical release (backfilled changelog entry)
## v11.15.0 — 2026-06-11 — historical release (backfilled changelog entry)
## v11.14.0 — 2026-06-10 — historical release (backfilled changelog entry)
## v11.13.0 — 2026-06-10 — historical release (backfilled changelog entry)
## v11.12.2 — 2026-06-10 — historical release (backfilled changelog entry)
## v11.12.1 — 2026-06-10 — historical release (backfilled changelog entry)
## v11.12.0 — 2026-06-10 — historical release (backfilled changelog entry)
## v11.11.0 — 2026-06-10 — historical release (backfilled changelog entry)
## v11.10.0 — 2026-06-10 — historical release (backfilled changelog entry)
## v11.9.0 — 2026-06-10 — historical release (backfilled changelog entry)
## v11.8.8 — 2026-06-10 — historical release (backfilled changelog entry)
## v11.8.6 — 2026-06-10 — historical release (backfilled changelog entry)
## v11.8.5 — 2026-06-10 — historical release (backfilled changelog entry)
## v11.8.4 — 2026-06-10 — historical release (backfilled changelog entry)
## v11.8.3 — 2026-06-10 — historical release (backfilled changelog entry)
## v11.8.2 — 2026-06-10 — historical release (backfilled changelog entry)
## v11.8.1 — 2026-06-10 — historical release (backfilled changelog entry)
## v11.8.0 — 2026-06-10 — historical release (backfilled changelog entry)
## v11.7.0 — 2026-06-10 — historical release (backfilled changelog entry)
## v11.6.0 — 2026-06-10 — historical release (backfilled changelog entry)
## v11.5.0 — 2026-06-10 — historical release (backfilled changelog entry)
## v11.4.0 — 2026-06-10 — historical release (backfilled changelog entry)
## v11.3.2 — 2026-06-09 — historical release (backfilled changelog entry)
## v11.3.0 — 2026-06-09 — historical release (backfilled changelog entry)
## v11.2.0 — 2026-06-09 — historical release (backfilled changelog entry)
## v11.0.0 — 2026-06-09 — historical release (backfilled changelog entry)

## v12.30.0
- CI green on bare runners: detect_platform honors an OPENCLAW_PLATFORM env override (mac|vps) so static gates run without a live OpenClaw install (real Mac/VPS detection unchanged; v12.29.0 legacy /data/clawd path preserved); qc-static.yml sets OPENCLAW_PLATFORM=mac.
- how-to-use-this-department gate fix: relocate the stray fish-audio/ reference docs into presentations/fish-audio/ (kills a false department; preserves the presenters-speech-writer references) + regenerate the stale presentations how-to guide.

## v12.29.0
- Skill 44 agency provisioning: create-sub-account (Firebase internal / Chrome-extension token) + add-user (agency PIT public API, type=account guarded, agency-user hard-refused); version:2021-07-28 transport fix; teach-yourself + AGENTS.md + TOOLS.md rewritten to the new way; OAuth marketplace path marked dead.
- Fleet-completion unblock: detect_platform now also resolves the legacy /data/clawd/zero-human-company workforce path on VPS boxes (kills false department-floor-FAIL alerts on legacy-tree clients).

## [v12.28.0] — 2026-06-17 — feat(presentations): the nine Intelligence Engines — named taxonomy + new enforcement (Lighting skin-tone, Typography 8th-row/salesy-font, Story character-continuity, Product placement, required slide-type beats)

Promotes the Presentation Department's image/pitch capabilities to a single, named, verifiable **Intelligence Engines** taxonomy and wires the previously-undocumented doctrines into the QC auto-fail gate as **enforcement, not prose**. The pipeline already spoke three of these engines by name (the FACIAL EXPRESSION ENGINE, the AUDIENCE ENGINE, and the WORLD ENGINE in `slide-image-creator-sops.md` element 11) and two under their mechanic names (Hook Doctrine, Re-Pitch); this release completes and unifies the set of NINE — **1 Facial · 2 Lighting · 3 Typography · 4 Story · 5 World · 6 Pricing · 7 Hook · 8 Recap · 9 Product** — each with a definition, a "how you know it landed" check, and named failure modes auto-failed at QC.

- **New framework SOP** `…/presentations/sops/SOP-ENGINE-00-INTELLIGENCE-ENGINES-FRAMEWORK.md` — the single artifact that defines all 9 engines (definition / verify / failure modes), the binding spine (`AF-WORD-IMAGE-MISMATCH`: the image must reflect what the words say), the "image editing is a Lego set" mental model, and the required slide-type doctrine map. It POINTS AT existing enforcement rather than duplicating it; new gates are added only where a real gap was found.
- **Lighting Intelligence (Engine 2) — net-new doctrine.** `slide-image-creator-sops.md` SOP 9.3 gains a skin-tone lighting sub-section: deep skin lit rich/dimensional with a rim/hair light (avoid the "murderer" silhouette), lighter skin with retained texture/shadow (avoid the "Casper" wash); lighting is a per-skin-tone property, not one deck-wide recipe. Distinct from (and stacked on) the existing skin-tone COLOR-fidelity negative. New auto-fail `AF-LIGHT-SKINTONE`.
- **Typography Intelligence (Engine 3) — net-new doctrine.** `SOP-DESIGN-01` §2.6 adds the **8th-row readability test** (headline survives ~25% shrink, relative to slide height), the **salesy/cheap-font ban** (carnival/"$9.97 big-price-tag"/novelty faces banned on a trust deck), and the **"typography = funnel"** framing. New auto-fails `AF-TYPE-8THROW`, `AF-TYPE-SALESY-FONT`.
- **Story Intelligence (Engine 4) — AMENDED a blocking line.** `slide-image-creator-sops.md` Part D previously read "Consistency is a color and light property, not a composition property" — which silently blocked carrying the SAME character across life stages. Amended to carve out a `STORY_CHARACTER:<id>` exception (held person identity via image-to-image from a locked reference, aged per the beat) while keeping the anti-template variety rule as the default. New auto-fail `AF-STORY-CHARACTER-DRIFT`.
- **Product Intelligence (Engine 9) — net-new.** `slide-image-creator-sops.md` adds element 16, subtle in-world product placement composited image-to-image from a `PRODUCT_ASSET_URL` on `PRODUCT_PLACEMENT:yes` slides, mirroring the logo I2I mechanic (never reinvented). Pairs with the new **Subtle Brand Cue** doctrine in `brand-steward-sops.md` (a hidden in-world reminder of the brand's core value). New auto-fails `AF-PRODUCT-INVENTED`, `AF-PRODUCT-MISSING`.
- **World / Pricing / Hook / Recap — naming + rationale.** `SOP-IMG-01` states WHY GPT-Image-2 is pinned (real-world grounding for the World engine); `SOP-PITCH-02` re-homes "promise precedes price" as Pricing Intelligence's first law; `SOP-SLIDE-03`/`hook-strategist-sops.md` alias the sacred-refrain doctrine as Hook Intelligence; `SOP-PITCH-03` aliases Re-Pitch as Recap Intelligence. These add NO new gate — their existing enforcement (`AF-C7`/`AF-DEN`, `AF-HOOK`/`AF-C2`/`AF-P12`, c23/c24/`AF-DEN-7`) stands.
- **Required slide-type beats (enforcement).** `SOP-SLIDE-04` §2.1 adds Formula (`AF-NO-FORMULA`), standalone Measurable-Results (`AF-NO-MEASURABLE-RESULTS`), Fork-in-the-Road decision tree with a check-mark on the chosen path (`AF-NO-FORK`), and Before&After ≥1 (`AF-NO-BEFORE-AFTER`). `SOP-PITCH-04` formalizes External Proof — expert-quote boxes + a "the science agrees" studies slide, distinct from the Wall of Wins (`AF-NO-EXPERT-PROOF`).
- **Hybrid delivery + self-coaching .pptx.** `presenter-coach-sops.md` SOP 9.5 + `delivery-concierge-sops.md` add the HYBRID PRESENTATION model (live → record → live; ≥3 logged live runs before a recording is cut). `pptx-assembly-specialist-sops.md` mandates per-slide speaker notes in the native .pptx notes pane (`AF-EMPTY-NOTES-PANE`, enforced at closeout).
- **Gate wiring (enforcement, not prose).** `SOP-SLIDE-00` Section 8 registers all new auto-fail codes (`AF-WORD-IMAGE-MISMATCH`, `AF-LIGHT-SKINTONE`, `AF-TYPE-8THROW`, `AF-TYPE-SALESY-FONT`, `AF-STORY-CHARACTER-DRIFT`, `AF-PRODUCT-INVENTED`, `AF-PRODUCT-MISSING`, `AF-NO-FORMULA`, `AF-NO-MEASURABLE-RESULTS`, `AF-NO-FORK`, `AF-NO-BEFORE-AFTER`, `AF-NO-EXPERT-PROOF`, `AF-EMPTY-NOTES-PANE`) with detection method and failure message each.
- **Manifest:** re-ran `hash-content-manifest.py` — SOP-ENGINE-00 added to `sops[]` (97 dept-level SOPs) and the 14 edited SOPs re-stamped (`content_versions bumped: 14`). `--check` passes.
- **Version:** rolled all 9 markers + `cc-compat.json` to **v12.28.0** via `bump-version.sh`.

## [v12.27.0] — 2026-06-17 — feat(versioning): per-artifact content hashes + change detection (Skill 23 — "this client's role X is out of date")

Adds a **per-artifact content hash + version** for every role, dept-level SOP, and department in the role library, plus a **detector** that tells, per artifact, whether a given client's built workforce is **CURRENT / STALE / MISSING / ORPHAN / UNTRACKED** vs the current library content. This is the mechanism that drives the refresh flow ("this client's role X is out of date → re-instantiate it") and that, on any **future** library edit, auto-flags exactly the affected clients for exactly the changed artifact — precise, per-artifact, **false-positive-free**.

- **Why naive byte-hashing was wrong (and the fix).** Every library `.md` is a pure TEMPLATE full of `{{TOKENS}}` (`{{COMPANY_NAME}}`/`{{ISO_DATE}}`/`{{GENERATION_DATE}}`/…). At instantiation those become per-client values **and** volatile values (`datetime.now()`), so a hash of the *rendered client file* differs for **every client and every day** even when the library is unchanged → massive false positives. The fix: `content_sha` is computed over the **canonical template** with **`{{TOKENS}}` left intact** (the tokens ARE the canonical content), after stripping the provenance marker and normalizing the volatile `**Last updated:**` / `**Version:**` header values. Two identical templates produce an identical `content_sha` regardless of which client they later serve. Proven in tests: the naive byte-hash differs across (Acme, Jan-15) vs (Globex, Jun-17) while the canonical `content_sha` is identical; a real content edit changes it; a date/marker-only change does not.
- **New generator** `23-ai-workforce-blueprint/scripts/hash-content-manifest.py` — idempotent in-place stamper (modeled on `tag_role_classes.py`) over `templates/role-library/_index.json`. Stamps `content_sha`/`render_sha`/`content_version`/`content_hashed_at` onto all **423** `roles[]` entries, adds a new top-level **`sops[]`** array for the **96** `<dept>/sops/*.md` dept-level SOP files, computes a per-dept `content_sha` (sha over the sorted member-slug+member-sha list, so a dept goes stale on membership change OR any member change) into `departments{}`, and writes a self-describing **`content_manifest{}`** header (algo/normalize/neutral_config_sha/schema). `render_sha` is a build-time determinism cross-check (forward-render through `fill_tokens()` with a neutral config + frozen clock; asserts no un-mapped **canonical** token survives). `--dry-run` / `--summary` / `--check`.
- **Per-client build record (additive — does not break existing builds).** The build now stamps a `workforce-provenance` HTML-comment marker into each instantiated `how-to.md` carrying the **source** `content_sha`/`content_version` copied from the manifest (replacing the old `v?` marker that had no sha), in BOTH `create_role_workspaces.try_library_fill()` and `build-workforce._instantiate_role_from_library()`. `build-workforce.py` also rolls these up into `.workforce-build-state.json` → **`artifactProvenance.{roles,depts,sops}`** (the fast detection path; the per-file marker is the ground-truth fallback).
- **New detector** `23-ai-workforce-blueprint/scripts/detect-stale-artifacts.py` — given `--workspace` + `--manifest`, classifies every artifact **CURRENT / STALE / MISSING / ORPHAN / UNTRACKED** (fast path = build-state `artifactProvenance`; fallback = scan `how-to.md` provenance markers; a content file with no marker = UNTRACKED). Human table + `--json {summary, items}`. **Exit 0** = all current, **10** = actionable drift (the refresh work queue), **2** = load error. Read-only on the client side.
- **Enforcement (a stale manifest can't ship).** New **CONTENT-HASH** dimension in `qc-assert-repo-consistency.py` `evaluate_artifact_coverage()` (exit **6** on drift): re-runs the hash pipeline (`check_manifest`) over the live library files and asserts every `roles[]`/`sops[]` entry HAS `content_sha`+`content_version`, each stored sha EQUALS the freshly recomputed one (manifest not stale vs files), and `render_sha` recomputes with no surviving un-mapped canonical token. Same gate already invoked by `qc-static.yml` / `.githooks/pre-commit` / `scripts/qc-system-integrity.sh`. Plus a fast static CI step in `.github/workflows/qc-static.yml` running `hash-content-manifest.py --check` (pure repo files; no live install).
- **Wired into the refresh flow.** `update-skills.sh` runs `detect-stale-artifacts.py` after `migrate-existing-workforce.sh` and writes the actionable items to `.artifact-refresh-queue.json`; `check-updates.sh` surfaces an `artifact_staleness` summary in its output JSON (an out-of-date workforce becomes an update signal). `add-role.sh` re-stamps the manifest after upserting a role.
- **New adversarial tests** `23-ai-workforce-blueprint/scripts/test-artifact-versioning.sh` (11 fixtures, all pass): clean `--check` passes; canonical hash is client/day-invariant while naive differs; real-vs-volatile edit; stale-manifest `--check` fails; idempotency; detector fast-path CURRENT/STALE/MISSING/ORPHAN + exit 10; marker-fallback UNTRACKED; all-current → exit 0; CONTENT-HASH gate dimension passes clean and exits 6 on an un-restamped edit.
- **Docs:** `23-ai-workforce-blueprint/ADDING-DEPARTMENTS-ROLES-SOPS.md` gains a "Per-artifact content hashes + change detection" section + a CONTENT-HASH row in the gate table; after editing any role/SOP/dept you MUST run `hash-content-manifest.py` (enforced by the gate).
- **Version:** rolled all 9 markers + `cc-compat.json` to **v12.27.0** via `bump-version.sh`.

## [v12.26.0] — 2026-06-17 — chore(skills): archive Skill 11 (SuperDesign) + Skill 21 (Tavily Search) — 41 active, 5 archived

Both skills archived and removed from install waves. Skills-count gate confirmed green after archive.

- **Skill 11 (SuperDesign) archived.** SuperDesign was a third-party SaaS design tool installed on every client box. Replaced by Skill 45 (Design Intelligence Library / DIU) which ships 13 specialist roles covering style analysis, deck generation, brand systems, and image generation through the client's own Kie.ai endpoint — no external SuperDesign account required. Folder renamed `11-superdesign-ARCHIVED`; `ARCHIVED.md` added per convention.
- **Skill 21 (Tavily Search) archived.** Tavily was a paid real-time web-search API. Tavily is no longer used in the OpenClaw fleet. Replaced by Agent Browser (Skill 03) for live web research and Context7 (Skill 09) for documentation lookups. Folder renamed `21-tavily-search-ARCHIVED`; `ARCHIVED.md` added per convention.
- **Install waves updated:** Wave 2 drops from 11 to 10 skills (11-superdesign removed); Wave 3 drops from 15 to 14 skills (21-tavily-search removed). Total: 41 active + 5 archived (11, 13, 21, 33, 34) across 46 numbered folders.
- **All skills-count markers updated:** `install.sh` active count, README inventory rows (both ARCHIVED rows updated), README/install.sh prose counts.
- **Convention:** identical to Skills 13, 33, 34 — folder renamed with `-ARCHIVED` suffix, `ARCHIVED.md` added explaining replacement + backward-compat rationale, skill excluded from install loop via existing `*ARCHIVED*` guard.

## [v12.25.0] — 2026-06-17 — feat(consistency): artifact-coverage gate — "complete check for everything" (org-chart × routing × command-center × dreaming × bootstrap × skills-count × version)

Extends the v12.23.0 repo-consistency gate from FLOOR × ROSTER × LIBRARY × SOP × PERSONA to cover **everything** — the remaining classes of drift where a floor department, role, skill, bootstrap file, or version marker can silently fall out of a **downstream artifact** even though the 5-dimension gate is green. Same script (`23-ai-workforce-blueprint/scripts/qc-assert-repo-consistency.py`); the bare invocation now runs BOTH gates (`--only consistency` / `--only artifact` to isolate). The new gate exits **6** on any artifact drift.

- **Seven new dimensions** (`evaluate_artifact_coverage`):
  - **ORG-CHART** — runs the REAL `generate_org_chart` against a synthesized full-floor `selected_departments`; every floor dept + its roster roles must render.
  - **ROUTING** — runs the REAL `write_universal_routing_map`; every floor dept must have a `departments/<dept>/` row in `00-ROUTING.md` (no unrouted dept silently falling back to `general-task`).
  - **COMMAND-CENTER** — runs the REAL `generate_departments_json`; every floor dept must be present as a slug (Kanban column / Telegram topic), CEO column first.
  - **DREAMING** — every floor dept gets a workspace + `memory/` substrate via the `selected_departments` loop (no hardcoded subset); `install.sh configure_dreaming` writes the workspace-wide `memory-core` dreaming config; no per-dept dreaming exclusion list may omit a floor dept.
  - **GENERATOR-WIRING** — the org-chart / routing / command-center generators must be CALLED by the build (not just defined).
  - **BOOTSTRAP** — the 6 shipped core templates (`IDENTITY`/`SOUL`/`AGENTS`/`USER`/`TOOLS`/`HEARTBEAT`.md) exist at repo root; `MEMORY.md` is NOT committed (seeded fresh+empty per agent); `Start Here.md` enumerates all 7.
  - **SKILLS-COUNT** — `install.sh` active-skill prose == README count == the actual skill-dir tree, and every active skill has a README inventory row.
  - **VERSION** — every version marker (the 9-marker `bump-version.sh` set + `cc-compat.json` `onboardingVersion`) agrees with `/version`.
  It mirrors the build (synthesizes the full floor from `load_canonical_floor()` + the vertical-pack one-liners and runs the real generators), so a generator that drops a dept, hardcodes a subset, or is unwired fails legitimately.
- **Genuine drift found on the repo and FIXED (the gate now PASSES legitimately — 8/8 artifact dimensions OK, 29/29 floor depts covered):**
  - **VERSION:** `/version` was `v12.24.0` but the 9 bump-version markers were all stuck at `v12.20.0`/`12.20.1` and `cc-compat.json` at `v12.17.4`. Ran `bump-version.sh v12.25.0` (rolls all 9) + set `cc-compat.json` `onboardingVersion` to `v12.25.0`.
  - **SKILLS-COUNT:** README said "44 folders / 41 active" (line 39) and "45 folders / 42 active" (line 134); `install.sh` prose said "40 active" (×2); the README inventory table was missing rows for `44-convert-and-flow-operator` and `46-kie-callback-relay`. Actual tree is **46 folders, 43 active, 3 archived** (13/33/34). Corrected all four prose counts and added the two missing inventory rows.
- **Wired in:** new CI step in `.github/workflows/qc-static.yml` (runs `--only artifact` + the new fixtures); `scripts/qc-system-integrity.sh` **CHECK X.12** extended to hard-fail on rc=6 (artifact drift) with per-dimension detail; build preflight `lib-onboarding-state.sh` `oc_repo_consistency_ok()` already fails closed on any nonzero rc (5 or 6) since it runs the bare gate. Documented in `23-ai-workforce-blueprint/ADDING-DEPARTMENTS-ROLES-SOPS.md` ("The artifact-coverage gate").
- **New adversarial tests:** `23-ai-workforce-blueprint/scripts/test-artifact-coverage.sh` — plants exactly one drift per dimension in an isolated sandbox and proves the gate exits 6 (clean PASSes; org-chart / routing / command-center / dreaming / generator-wiring / bootstrap-delete / committed-MEMORY / skills-count / version drift all FAIL — 10/10 fixtures pass).

## [v12.24.0] — 2026-06-17 — fix(ghl-mcp): supervised + reboot-surviving + PORT-pinned autostart (fleet incident: 12/19 boxes down/unsupervised)

Makes it IMPOSSIBLE for a fresh install to ship a GHL Community MCP (Tier 2, skill 36) that dies on teardown or binds a random port. Confirmed fleet-wide today: 12 of 19 boxes had the GHL MCP down/unsupervised. TWO root causes, both now fixed AND enforced at the QC gate:

- **Root cause 1 — RANDOM PORT.** The community MCP's `main.js` reads `process.env.PORT` **before** `process.env.MCP_SERVER_PORT` (`src/main.ts:55`, `src/http-server.ts:30`). The launchd plist and systemd unit only set `MCP_SERVER_PORT`, so a stray inherited `PORT` bound a random port (49032/63703) instead of 8765. **Fix:** every launch surface now pins **BOTH** `PORT=8765` **and** `MCP_SERVER_PORT=8765` — launchd plist `EnvironmentVariables`, pm2 `ecosystem.config.js` env, systemd `Environment=`, the server `.env`, and the fallback supervisor loop.
- **Root cause 2 — UNSUPERVISED BARE NOHUP.** `scripts/ghl-mcp-autostart.sh` (VPS branch) and `platform/vps/36-ghl-mcp-setup-scripts/start-ghl-mcp-server.sh` started the server with a bare `nohup node …` that does NOT survive session/exec teardown and is never restarted on crash. **Fix:** the VPS path now runs under **pm2** (the fleet-standard supervisor) via a generated `ecosystem.config.js`, calls `pm2 save`, and wires reboot survival (`pm2 startup` + an idempotent `@reboot pm2 resurrect` cron, matching the Command Center pattern). systemd is the non-container fallback (now with `PORT` pinned via `Environment=`); a detached `setsid` **supervised relaunch loop** (poor-man's pm2, PORT pinned) is the last resort. The bare-nohup path is removed.
- **Mac unchanged in mechanism, hardened in port:** launchd `KeepAlive` + `RunAtLoad` plist `com.clawd.ghl-mcp` now also pins `PORT` (not just `MCP_SERVER_PORT`).
- **New enforcer** `scripts/qc-assert-ghl-mcp-supervised.sh` (single source of truth) — a STATIC check of the SHIPPED autostart scripts: asserts the Mac launchd KeepAlive plist, the VPS pm2 + `pm2 save` + reboot-resurrect wiring, NO bare `nohup node`, and BOTH ports pinned. Wired into `scripts/qc-system-integrity.sh` as hard-fail **CHECK X.13** (runs during install + every update — before the server is even started, so a regression can never ship). Positive + negative tested (catches reintroduced bare nohup / unpinned PORT).
- **Docs:** `36-ghl-mcp-setup/INSTALL.md` §5.5/§5.6 rewritten (launchd `PORT` pin; VPS pm2 ecosystem + reboot-resurrect replacing the systemd-only/nohup path) and `platform/README.md` service-mgmt + GHL-MCP-start rows updated.

## [v12.23.0] — 2026-06-17 — feat(consistency): one gate cross-checks floor × roster × library × SOP × persona (AF-REPO-CONSISTENCY, N38)

Makes it IMPOSSIBLE for a department / role / SOP / persona to ship inconsistent. The Skill 23 workforce blueprint carried SIX independent sources of truth that NOTHING cross-checked — department FLOOR (`department-naming-map.json` mandatory + universal-primary verticals), ROSTERS (`suggested-roles/*.md`), ROLE LIBRARY (`templates/role-library/_index.json`), SOP source (role-library copy path / Skill-42 PA library), and PERSONA generation (`build-workforce.py` `dept_to_domains` ×2 + `create_role_workspaces.py` `DEPT_DOMAIN_HINTS`). Six departments once shipped unbuildable; eleven floor depts silently fell back to the generic `['leadership']` persona pool.

- **New gate** `23-ai-workforce-blueprint/scripts/qc-assert-repo-consistency.py` (exit 5 on ANY drift). For every floor dept it HARD-ASSERTS: (a) its roster PARSES, (b) every roster role resolves a library/SOP template, (c) the dept DRY-RUN-INSTANTIATES cleanly, (d) every role has a real SOP source, (e) the dept has a NON-fallback persona-domain mapping in ALL THREE persona maps, (f) no orphan rosters / unreachable floor depts. Prints a per-department `DEPT | ROSTER | LIBRARY | INSTANTIATE | SOP | PERSONA-DOMAIN | STATUS` table + PASS/FAIL with raw counts. Uses the SAME functions the build uses (`parse_roster` / `library_lookup` / `normalize_dept` / `evaluate_floor` / `is_canonical_dept`), so it can never disagree with the build.
- **Drift fixed (current repo now PASSES legitimately — 29/29 floor depts OK, 0 unresolved roles):**
  - **Persona-domain (headline):** added the canonical FLOOR dept ids (`billing-finance`, `customer-support`, `web-development`, `app-development`, `communications`, `openclaw-maintenance`, `social-media`, `paid-advertisement`, `crm`, `quality-control`, `account-management`) to `dept_to_domains` in BOTH `create_governing_personas_md` and `generate_persona_matrix`, and added `crm` / `quality-control` / `account-management` to `DEPT_DOMAIN_HINTS` — 11 floor depts no longer fall back to `['leadership']`.
  - **Roster→library name drift:** added explicit `**Slug:**` lines to 28 roster roles (sales, billing, customer-support, web-development, app-development, graphics, video, audio, research, legal-compliance, personal-assistant) so a roster name shorter than its library title (e.g. "SDR" → `sdr-sales-development-rep`) resolves deterministically.
  - **Corrupt library slug:** renamed two sales role-library files whose slugs carried the em-dash as the escaped bytes `\342\200\224` (`qc-specialist-…-sales`, `deep-research-specialist-…-sales`) to clean ASCII slugs + patched `_index.json`.
  - **Phantom roster headers:** demoted 3 `### ` policy/mandate headers in `openclaw-maintenance-suggested-roles.md` (Furnace-Watch Mandate / Rescue Rangers Escalation / Platform-Specific Guardrails) to `####` so the roster parser no longer counts them as roles.
  - **Table-format rosters:** taught `parse_roster` (create_role_workspaces.py) AND `parse_suggested_roles` (build-workforce.py) to ALSO parse the `| # | Slug | Title | Type | Purpose |` table format so `general-task` + `project-architecture-office` materialize their roles (they parsed 0 before).
- **Wired in:** CI step in `.github/workflows/qc-static.yml` (runs the gate + `test-repo-consistency.sh` on every PR/commit); `scripts/qc-system-integrity.sh` **CHECK X.12** (hard-fail); build-start preflight `lib-onboarding-state.sh` `oc_repo_consistency_ok()` (a client build refuses to run against a drifted repo). Documented as `AGENTS.md` **N38**, `FLEET-STANDARDS.md` **§7**, and a contributor checklist `23-ai-workforce-blueprint/ADDING-DEPARTMENTS-ROLES-SOPS.md`.
- **New tests:** `23-ai-workforce-blueprint/scripts/test-repo-consistency.sh` — proves the gate PASSES clean and FAILS when a roster / role / persona-mapping / library slug is broken in a sandbox (5/5 fixtures pass).

## [v12.21.0] — 2026-06-17 — feat(standards): Ollama provider platform-branch (Mac local daemon vs VPS cloud-direct), enforced

Encodes the CLIENT ONBOARDING STANDARD for the `ollama` model provider, branched by box type, and corrects the pre-existing VPS-only assumption that wrongly treated `127.0.0.1:11434` as a hard violation everywhere.

- **Mac client:** signed-in LOCAL Ollama daemon (`ollama signin`, client's own ollama.com account) + ONE `ollama` provider `baseUrl: http://127.0.0.1:11434`, `api: ollama`, `apiKey: ollama-local`. A signed-in daemon serves BOTH local AND `:cloud` models through that one endpoint (the docs.openclaw.ai/providers/ollama "Cloud + Local" hybrid flow). Loopback baseUrl is REQUIRED on Mac.
- **VPS client:** ONE `ollama` provider cloud-direct — `baseUrl: https://ollama.com` + client's own `OLLAMA_API_KEY`. Loopback baseUrl → `ECONNREFUSED` (HARD VIOLATION; no daemon in container).
- **All boxes:** every `:cloud` model `maxTokens ≤ 64000` (Ollama Cloud caps output at 65536). Verify a live PONG, not just config-valid.
- **New enforcer** `scripts/qc-assert-ollama-provider-platform.sh` (single source of truth; P1 baseUrl/platform, P2 api, P3 apiKey/platform, P4 :cloud maxTokens) wired into `scripts/qc-system-integrity.sh` as hard-fail **CHECK X.9** (runs during install + every update).
- **New SOP** `docs/OLLAMA-PROVIDER-BY-PLATFORM.md`. Updated `AGENTS.md` N30 (now platform-branched), `platform/README.md` (Ollama + STT rows), `FLEET-STANDARDS.md` §5.
- **Operator note:** existing Mac clients onboarded under the old rule (currently cloud-direct on `ollama.com`, no local daemon) will FAIL X.9 with an explicit migration message. They keep working until migrated; do NOT auto-migrate a live client.

## v12.20.1 — Presentations renderer enforces the process to the letter
- build_deck: HARD PROMPT_CHAR_FLOOR=1500 (under 1,500 = fail, not run); renders the Slide Image Creator's RICH prompt verbatim (fail-loud if missing/short); thin self-composed prompt removed; parallel render.
- 9-check PROCESS PREFLIGHT enforces every SOP phase incl. rich-prompt + coverage; QC loops back / forces redo on any deviation.
- Audience modes STANDARD/PERSONAL/GENERAL + target_talk_minutes + speech-length gate (AF-SPEECH-SHORT).
- PIPELINE-MANIFEST v3 + sync_check lockstep green; no existing SOP weakened.

## [v12.20.0] — 2026-06-16 — feat(presentations): universal scrub + anti-compression hard gate + deterministic build pipeline + SOP↔Python lockstep

Merges the presentations-sop-overhaul (universality + anti-compression) branch with the PR #271 deep-research role-library sync. Highlights:

- **Presentations department made UNIVERSAL — zero client names.** Every concrete name, niche, price, hook line, logo wordmark, deck title, and number across the Presentations role library and the master `universal-sops/CLIENT-WEBINAR-DECK-SOP.md` is now an ILLUSTRATIVE EXAMPLE / DISCOVERY VARIABLE the agent substitutes from the live client interview. Nothing client-specific is hardcoded; the examples teach the SHAPE, the discovery variables supply the content. Enforced by a repo-wide client-name scan (0 hits).
- **Anti-compression HARD GATE (AF-COVERAGE-1 + `_chk_coverage`).** The density-floor overhaul RETIRES the old "hook sung at least 7 times" FLOOR (which produced the reference failure case's 40-slide footer-stamping) and REPLACES it with a CEILING: the canonical hook appears VERBATIM on EXACTLY 3 to 4 dedicated pure-typography slides at named beats and NOWHERE else; footer-stamping is banned; more than 4 hook slides, or zero, is an auto-fail. Paired with the AF-DEN density triggers (>= 8-slide gap between price beats, anchor at one-third never the back third, BUILDUP before every DROP, itemized value-stack before Drop 1, promises before anchor, Wall of Wins 4-6 before offer, 4-7-slide re-pitch after FINAL, section floors). Coverage is enforced, compression is auto-failed.
- **Deterministic build pipeline shipped.** `build_deck.py` (the single-command, zero-AI-judgement-at-runtime renderer — the agent writes only `slides.json` per `slides.schema.json`; the script composes each KIE.ai prompt mechanically, submits, polls, verifies, and assembles the .pptx), plus `kie_generate.py` (reference image-to-image/text-to-image submit+poll+download helper) and `test_preflight.py`. The building agent has NO image tool; KIE.ai is the ONLY render call; self-generate / native image tool / inline HTTP / placeholder substitution are all auto-fails. The mandatory English/Latin-only spelling-lock pin is appended verbatim to every prompt.
- **Process manifest (SOP-SLIDE-05-PROCESS-MANIFEST.md).** Documents the one mandated end-to-end flow with no substitutions.
- **SOP ↔ Python lockstep detector.** `universal-sops/presentation-slide-craft/PIPELINE-MANIFEST.json` declares the canonical contract; `sync_check.py` fails the build if the SOPs and the shipped scripts drift apart; `SOP-SLIDE-06-EXTENSION-AND-SYNC.md` documents the extension + sync discipline.
- **Hook CEILING and renderer reconciliation** carried through every consuming role (Director, Hook Strategist, Slide Copywriter, Slide Image Creator, Typography Architect, QC Specialist, Offer Price Strategist, Brand Steward, PPTX Assembly, Brainstorming Buddy, and their SOP mirrors).
- **Deep Research Specialist (PR #271) merged, not lost.** The twelve-category framework (A-L: niche structures, pricing & value benchmarking, supporting statistics, external corroboration, grounded image context, design+hook+pacing, attributable quotes, the fact-validation ledger, objection research, social-proof patterns, persuasion-framework validation, compliance flags) plus AF-RESEARCH-GATE is kept AND the `persuasion_intelligence` seeding from the Content-to-Presentation Architect is preserved.
- **`_index.json` reconciled** to the union: presentations department 25 roles (adds `fish-audio-expression-specialist`), `total_roles` 425, `total_departments` 34, valid JSON, no duplicate slugs.

## [v12.19.1] — 2026-06-16 — fix(presentations): sync Deep Research Specialist ROLE file Section 9 to its SOP mirror

The ROLE file (ROLE-04 presentations) Section 9 was behind its SOP mirror after v12.19.0. Regenerated to match: SOP 9.4 (Deep Validation & Persuasion Research) with Categories G (attributable quotes), H (fact-validation ledger), I (objection research), J (social-proof patterns), K (persuasion-framework validation), L (compliance flags); SOP 9.1 brief template extended with the G-L header counts; SOP 9.3 hook/pacing (F5/F6) + Hook Strategist hand-off. Source role file and mirror now agree.

