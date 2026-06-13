# Changelog — convert-and-flow-operator (Skill 44)

## [1.0.15] - 2026-06-13 — feat: PLAN→BUILD→QC protocol (plan mode + WF-21 checklist + independent MiniMax QC gate + hallucination escalation)

### Added (PLAN MODE — INSTRUCTIONS.md Step 0.5)
- **Step 0.5 — PLAN MODE** binding gate inserted between Step 0 (model check) and the
  Natural-language intents table in INSTRUCTIONS.md. Fires on any new workflow CREATE/BUILD;
  not triggered by reads, REVIEW/export, or single-step patch-email/patch-trigger on an
  existing workflow.
- Six mandatory steps before any `caf workflows build` call:
  - **Step A — THINK:** reason through A1 (desired result in client's own framing), A2
    (client expectations, honored verbatim when hyper-specific), A3 (best trigger/node/action
    approach for THIS client's goal).
  - **Step B — DEPENDENCY PRE-CHECK:** GET-verify every tag/custom-field/custom-value before
    the build; missing items listed as "must create first"; ZHC-/ZHC_ standing approval noted.
  - **Step C — OUTLINE:** ordered trigger→nodes→exit blueprint with config for each step.
  - **Step D — CHECKLIST:** instantiate references/workflow-build-checklist-template.md for
    this build with all 21 WF items filled.
  - **Step E — IMPROVEMENTS:** optional labeled suggestions alongside (never instead of) the
    client's exact spec.
  - **Step F — PRESENT + GATING QUESTIONS:** present plan to client and ask two mandatory
    gating questions: Q1 publish/draft, Q2 re-entry once/allow-multiple.
- Binding rule: "Rushing to a default build is NOT the best outcome and is a violation."
- `"Build a follow-up workflow"` intent row re-pointed to "PLAN MODE (Step 0.5) first, then
  TRINITY."
- Per-operation decision rule: new sub-rule 2.0 "New workflow build → run PLAN MODE (Step 0.5)
  and get gating answers BEFORE choosing the token/tier path."

### Added (WF-1..WF-21 Checklist Template)
- **references/workflow-build-checklist-template.md** — new canonical 21-item reusable
  checklist serving BOTH the agent self-check (PLAN MODE Step D) AND the client hand-over
  (after QC passes). Covers: name, tags, trigger type+filters, trigger active flag (WF-4
  Sheila gate), publish state, re-entry/allow-multiple, action sequence, If/Else conditions,
  wait durations, custom fields, custom values, SMS From-number (WF-12 Sheila trap), email
  sender, webhooks, delivery chain linkage, advanced settings, edge cases, dependencies,
  TRINITY completeness, hallucination detection (WF-20), and snapshot verification (WF-21).
  Cross-referenced as superset of skill 41's 12-point checklist.

### Added (Step 9 — QC GATE, INSTRUCTIONS.md)
- **Step 9 — QC GATE** binding gate: after build completion, before declaring done.
  Sequence:
  1. Verbatim client announce via `openclaw message send --channel telegram` (mandatory).
  2. Spawn independent MiniMax QC sub-agent via `sessions_send` in a fresh session; prefer
     `minimax/minimax-2.7` via OpenRouter or `minimax-m3:cloud`; verify model configured +
     reachable before spawn; fall back to next independent high-reasoning model and log.
  3. QC sub-agent inspects via `caf workflows export <id>` + `qc-built-workflow.sh <id>`;
     returns explicit PASS/FAIL + observed vs expected for each WF-1..WF-21 item.
  4. All-PASS → Step 6. Any FAIL → fix + re-run QC.
  5. ONLY after all-PASS: declare done + hand client the filled checklist.
  6. Log QC run to build-events ledger (model used, per-item verdicts, pass/fail, escalation).
- **Hallucination escalation sub-section:** when QC class=HALLUCINATION (build-agent-claimed
  TRUE, QC-observed FALSE): hard stop; v12.3.5 Step 0 recommendation FLIPPED TO REQUIREMENT
  (redo must use high-reasoning model + thinking=HIGH); full re-QC from scratch; honest client
  disclosure; ledger log.

### Added (qc-built-workflow.sh — per-build QC script)
- **qc-built-workflow.sh** — new per-build QC script (DISTINCT from install-level
  qc-convert-and-flow.sh). Takes `<workflow-id> [--publish-intent DRAFT|LIVE]
  [--re-entry ONCE|ALLOW-MULTIPLE] [--json]`. Machine-asserts WF-3 (trigger present),
  WF-4 (trigger active vs publish-intent — Sheila gate), WF-5 (publish status), WF-6
  (re-entry setting), WF-7 (action nodes present), WF-12 (SMS From-number non-empty),
  WF-15 (delivery chain linkage), WF-18+WF-21 (snapshot exists). Emits per-item PASS/FAIL
  JSON. Appends to build-events ledger. Exit 0=all-pass, 1=fail, 2=prereq-error.

### Added (qc-convert-and-flow.sh Section S static assertions)
- 35 new static assertions in Section S covering: Step 0.5 PLAN MODE present + all binding
  rules, Step 9 QC GATE + announce template + MiniMax dispatch + checklist handover, checklist
  template exists with all 21 WF items + Sheila/SMS gates + hallucination detector + skill 41
  cross-ref, qc-built-workflow.sh present + executable + per-item assertions, CORE_UPDATES
  AGENTS.md block has all 3 new rules (plan-mode, QC-gate, hallucination→reasoning-HIGH).

### Changed (SKILL.md)
- READ-BEFORE-ACT block extended with Step 0.5 PLAN MODE + Step 9 QC GATE summaries.
- Teach Yourself read-order updated (references/workflow-build-checklist-template.md item 4,
  qc-built-workflow.sh item 5; existing items renumbered).
- Files in this folder list updated (items 9, 16 added).

### Changed (CORE_UPDATES.md AGENTS.md block)
- Three new binding rules prepended to the Convert and Flow Operator AGENTS.md section so
  every client agent inherits them on session start:
  1. PLAN MODE before build (think→outline→checklist→recommendations→gating questions).
  2. Independent MiniMax QC + checklist hand-over before declaring done.
  3. Hallucination → reasoning-model-thinking-HIGH (hard requirement, not recommendation).

### Scope
- Engine builder code under tools/engine/ is UNTOUCHED (docs/protocol + QC-script release).
- Engine CLI version unchanged (2.1.1).
- total_roles UNCHANGED (335).

---

## [1.0.13] - 2026-06-13 — docs: model-recommendation pre-flight warning for workflow builds

### Added (Step 0 model check — recommendation gate, not a hard block)
- **INSTRUCTIONS.md Step 0** — new "Model Check Pre-flight" section at the top of
  INSTRUCTIONS.md, triggered before any workflow BUILD or MODIFY action. Checks the
  active session model/thinking level; if lighter/non-high-reasoning or thinking not HIGH,
  surfaces a clear recommendation to the owner before proceeding. Proceeds on owner
  acknowledgement ("proceed anyway") — never blocks. Read-only ops exempt.
- **SKILL.md READ-BEFORE-ACT block** — a short "READ-BEFORE-ACT" callout added above
  the Teach Yourself Protocol, pointing to INSTRUCTIONS.md Step 0 for the model check.
- **CORE_UPDATES.md AGENTS.md block** — a concise pre-flight note prepended to the
  Convert and Flow Operator AGENTS.md section so every client agent sees the check rule
  every session.

### Motivation
A lighter model previously hallucinated a workflow's failure cause, a fake link, and a
wrong number — turning a 2-minute fix into a 12-hour debugging loop. This warning
surfaces the risk before the build starts and routes the operator to a better model when
needed, without blocking work when the owner chooses to proceed.

---

## [1.0.11] - 2026-06-11 — fix: wire GHL creds into gateway-inherited env + fail-loud live verify (Evelyn VPS reproduction)

### Fixed (install env-wiring gap — root cause of caf dying on a "successful" install)
- **Creds landed only where the gateway process never reads them.** The installer
  left `GOHIGHLEVEL_*` in `~/.openclaw/secrets/.env` — a file the OpenClaw
  gateway/agent **process never loads.** When the agent invoked `caf`, the
  gateway's process env had no `GOHIGHLEVEL_LOCATION_ID`, so the engine died at
  `Error: GHL_LOCATION_ID environment variable is not set.` while the install had
  already reported success. **Reproduced live on Evelyn's VPS, 2026-06-11.**
- **Empty docker `env_file` placeholders masked everything (VPS).** The Hostinger
  compose `env_file` (`/docker/<project>/.env`) carried empty placeholder lines
  (`GOHIGHLEVEL_API_KEY=` with no value, no FIREBASE line). docker-compose injects
  an empty `env_file` value as an **empty string** into the container process env,
  and an empty string still wins against the secrets file for any consumer that
  reads `os.environ` — so it masked the real value even after it was added
  elsewhere. Empty placeholders are now **replaced in place**, never appended-after.

### Added (`tools/engine/wire-ghl-env.sh` — single-source env wiring)
- Wires all **5** canonical vars (`GOHIGHLEVEL_API_KEY`, `GOHIGHLEVEL_LOCATION_ID`,
  `GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN`, `GOHIGHLEVEL_ALLOWED_LOCATION_IDS`,
  `GOHIGHLEVEL_DRAFT_ONLY`) into `openclaw.json` `env.vars` — the block the gateway
  inherits at process start. Tries `openclaw config set` first; **falls back to a
  direct JSON deep-merge** into `openclaw.json` when `config set` rejects the
  nested key (the supported pattern on OpenClaw 2026.5.20+, same as
  `31-upgraded-memory-system/scripts/activate-memory-stack.sh`).
- **VPS:** ALSO populates the host `/docker/<project>/.env`, REPLACING empty
  `GOHIGHLEVEL_*=` placeholder lines in place (with a logged note on why empty
  placeholders mask). Auto-finds the OpenClaw project under `/docker`; skipped
  cleanly when `/docker` is not visible (inside the container).
- **Mac:** wires `env.vars` but does NOT restart the gateway (rescue-Mac rule);
  documents that a `launchctl kickstart` may be needed for full inheritance.
- Exit 2 (required var absent everywhere) lets the caller mark the skill
  installed-with-missing-prereqs and list exactly which vars — never a fabricated
  success.

### Added (`tools/engine/verify-ghl-live.sh` — fail-loud post-install verify gate)
- Runs a **real read** against GHL using **ONLY the inherited process env** (no
  manual secrets sourcing — reproduces exactly what the gateway/agent process
  sees): `caf workflows list`, falling back to `caf contacts list --limit 1`
  (PIT-only, since workflow reads can legitimately fail without the Firebase
  token). **FAILS LOUDLY (exit 1)** if creds are present but caf can't reach GHL
  (the Evelyn failure mode). Exit 2 = installed-with-missing-prereqs (lists the
  vars). Exit 0 = live-verified. The install path NEVER reports skill-44 success
  on exit 1.

### Wired into both install paths
- **`INSTALL.md` Action 5** rewritten to call `wire-ghl-env.sh` (single source, no
  inline `config set` drift); **new Action 6b** runs the fail-loud verify gate;
  Action 2 chmods the two new scripts; "Done When" updated.
- **Root `install.sh` Step 14e** (`install_skill_44_convert_and_flow_operator_env`)
  runs both scripts as part of the orchestrated install, with the same
  fail-loud / missing-prereqs semantics.

### Added (CI + QC)
- `.github/workflows/skill44-install-path.yml` — new job `install-path-env-wiring`
  asserting both scripts exist, the deep-merge fallback + docker placeholder-replace
  logic is present, INSTALL.md Action 5 calls `wire-ghl-env.sh`, and Action 6b runs
  `verify-ghl-live.sh`.
- `qc-convert-and-flow.sh` — Section S assertions for the two scripts, the
  env-wiring call, and the verify gate.

### Scope note
- Installer / env-wiring only. Engine builder code is untouched (a separate branch
  `caf-engine-folder-hardening` owns engine fixes).

## [1.0.10] - 2026-06-11 — docs: world-first "just by talking" hype in owner-facing copy

Docs-only release. No engine, wrapper, or CLI behaviour changed (CLI stays `2.1.1`). Per the
repo G3 guard (any change inside a skill folder requires a `skill-version.txt` bump), the
skill version moves `1.0.9` -> `1.0.10` to carry the copy update with the skill payload.

### Changed
- **`references/fleet-announcement-template.md`** — MESSAGE 1 of the canonical 3-message
  template: same structure (🎉 congrats → what it unlocks → one final 5-min token setup →
  next two messages → reach Trevor), but the "what it unlocks" middle now leads with the
  fact the owner builds workflows **just by talking** to [AGENT_NAME] (plain chat message →
  draft to review; no clicking, no tech setup, no tutorials) and states plainly that this is
  the **only system in the world** that can do this right now, installed on the owner's own
  setup. Placeholders `[OWNER_NAME]` / `[AGENT_NAME]` unchanged.
- **`references/owner-token-grabber-guide.md`** — the "What this unlocks for you" intro now
  weaves in the same two beats (build automations **just by talking** + **only system in the
  world** that does this right now). The 8 setup steps and the FOR THE AGENT wiring section
  are untouched.

### Not changed
- Engine (`2.1.1`), wrapper, CLI surface, write-safety posture, the token-setup steps, and
  all tests are untouched. This release ships owner-facing copy only.

## [1.0.9] - 2026-06-11 — docs: standardized fleet announcement template + send runbook

Docs-only release. No engine or wrapper behaviour changed; the CLI version stays `2.1.1`.
Per the repo G3 guard (any change inside a skill folder requires a `skill-version.txt`
bump), the skill version moves `1.0.8` -> `1.0.9` to carry the new doc with the skill payload.

### Added
- **`references/fleet-announcement-template.md`** — the ONE canonical owner-facing Skill 44
  announcement, sent fleet-wide once a box has been given Skill 44. Two parts:
  - **The canonical 3-message template** (placeholders `[OWNER_NAME]` / `[AGENT_NAME]`,
    verbatim from what was sent to Cassandra and Aurelia): Message 1 = 🎉 congratulations +
    plain-English "what it unlocks" (the agent BUILDS Convert & Flow automation workflows as
    drafts to review — appointment follow-ups, lead-nurture, tag-and-text) + the "one final
    5-minute one-time token setup" framing + the "reach out to Trevor" offer; Message 2 =
    🔑 FINAL SETUP Part 1 of 2 (token explainer + Chrome Token Grabber, steps 1️⃣–5️⃣: download
    from the public Drive link, unzip, `chrome://extensions`, Developer mode ON, Load unpacked,
    pin the 🧩); Message 3 = 🔑 FINAL SETUP Part 2 of 2 (steps 6️⃣–8️⃣: log out/in, grab + copy,
    paste the canonical "Here is the Convert and Flow GHL Firebase token: …" message, then
    "Use Skill 44 and create me a test workflow").
  - **The operator-facing fleet-send runbook**: the GATE (only announce when the box's ledger
    shows skill44 remediation complete — caf engine ≥ 2.1.1 with a live `caf` read, or
    explicitly token-pending where the announcement IS the token ask; never announce a
    capability that is not live on the box), SEND MECHANICS (always the client's OWN OpenClaw
    gateway via `openclaw message send --channel telegram` — never the direct Telegram API;
    one client at a time; substitute the roster names; verify exit code + message id before
    the next; 3 messages in order), RECEIPTS (per-client JSON line appended to the operator
    ledger), and the already-announced list (cassandra msg ids 12524-12526 / aurelia, both
    2026-06-11) to prevent duplicate sends.

### Changed
- `SKILL.md` — the Token Grabber section now points to the new fleet-announcement template
  (a "Fleet announcement" subsection beside the owner-facing setup guide), and the "Files in
  this folder" list includes `references/fleet-announcement-template.md` (item 14).

### Not changed
- Engine (`2.1.1`), wrapper, CLI surface, write-safety posture, and all 119 tests are
  untouched. This release ships documentation only.

## [1.0.8] - 2026-06-11 — docs: owner-facing Token Grabber setup guide + agent wiring notes

Docs-only release. No engine or wrapper behaviour changed; the CLI version stays `2.1.1`.
Per the repo G3 guard (any change inside a skill folder requires a `skill-version.txt`
bump), the skill version moves `1.0.7` -> `1.0.8` to carry the new doc with the skill payload.

### Added
- **`references/owner-token-grabber-guide.md`** — a NEW owner-facing explainer a client
  agent can send or walk a non-technical business owner through. Plain-English description
  of what Skill 44 unlocks (the agent builds Convert & Flow / GHL automation workflows as
  DRAFTS the owner reviews: appointment follow-ups, lead nurture, tag-and-text), the
  prominent public download link for the Convert & Flow Token Grabber Chrome extension, and
  the polished 8-step one-time setup (download/unpack → `chrome://extensions` → Developer
  mode → Load unpacked → pin the 🧩 → log out/in → grab + copy → paste to agent).
- A clearly-separated **FOR THE AGENT** section inside the same doc: wire the pasted token
  as `GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN` into the gateway-inherited env (`openclaw config
  set env.vars.*`; on Hostinger VPS also replace the empty `/docker/<project>/.env`
  placeholder + `--force-recreate`), verify with a real `caf` read on the inherited env,
  then build the test workflow DRAFT-only with a `ZHC-` prefixed name, retrying once on a
  transient "token refresh failed" before reporting any problem.

### Changed
- `SKILL.md` — the "Chrome Extension: Token Grabber" section now points to the new
  owner-facing guide, and the "Files in this folder" list includes
  `references/owner-token-grabber-guide.md` (item 13).

### Not changed
- Engine (`2.1.1`), wrapper, CLI surface, write-safety posture, and all 119 tests are
  untouched. This release ships documentation only.

## [1.0.7] - 2026-06-11 — fix: ZHC- folder standing approval + top-level `folder` plan-key hardening (both reproduced live on a client box)

Two surgical engine fixes, both confirmed live on a managed client box (Evelyn, VPS)
by an Opus diagnostic 2026-06-11. These are NEW bugs — disjoint from the 1.0.3
400 `corrupted order` fix (already shipped).

### Fixed (CRITICAL — engine `workflow_builder.py`)
- **Bug 2a — folder-creation POST bypassed ZHC- standing approval.**
  `CampaignBuilder._build_locked` created the campaign folder with
  `self.client.request("POST", f"/workflow/{loc}", {"name": folder_name, ...})`
  WITHOUT passing `workflow_name`. The safety gate (`safety_gate._is_approved`)
  only inspects `workflow_name` for the ZHC-/ZHC_ standing-approval prefix, so it
  saw an empty string and **demanded `CAF_APPROVAL_TOKEN` even when the FOLDER
  name was ZHC-prefixed** — the build refused at the folder step despite a
  ZHC- folder name that should be standing-approved exactly like a ZHC- workflow
  name. Fix: pass `workflow_name=folder_name` on the folder POST. Non-ZHC folder
  names still require a token (gate behaviour unchanged).

### Fixed (CRITICAL — engine CLI `gohighlevel_cli.py` `workflows build`)
- **Bug 2b — a top-level `"folder": "<name>"` plan key crashed the builder with
  `TypeError: string indices must be integers`.** The `workflows build` handler
  read `campaign.get("folder")` for the folder name but passed the WHOLE plan
  dict (including the bare-string `folder` value) into `CampaignBuilder.build()`,
  which iterates every value as a workflow dict (`wf_def["name"]`) — indexing a
  string with `"name"` raised the TypeError. Fix: `pop` `folder` out of the plan
  dict before iterating; use the popped value as the folder name when `--folder`
  was not supplied; `--folder` wins when both are present. After the pop, every
  remaining entry must be a workflow object — the handler now **fails loud** with
  a clear message listing the offending non-dict entries (and exits non-zero)
  instead of surfacing a raw TypeError.

### Changed
- Engine CLI version bumped `2.1.0` -> `2.1.1` (behaviour: folder POST carries
  the folder name for ZHC- standing approval; build pops/validates the `folder`
  plan key).

### Added
- Regression tests `TestZHCFolderStandingApprovalAndFolderKeyPlan` in
  `tools/engine/tests/test_e2e_unit11.py`:
  - **TEST A** — a ZHC- folder name + ZHC- workflow name, NO `CAF_APPROVAL_TOKEN`:
    build exits 0 and the folder-creation POST carries `workflow_name=<ZHC folder>`
    (FAILS on pre-fix main, where the missing name triggers a SAFETY GATE refusal /
    non-zero exit).
  - **TEST B** — a plan with a top-level `"folder": "<name>"` string key builds
    successfully (no TypeError), the folder key is consumed as the folder name,
    and is NOT iterated as a workflow.
  - **TEST C** — `--folder` wins over the plan `folder` key when both are present.
  - **TEST D** — a non-dict, non-`folder` top-level entry fails loud (non-zero
    exit, clear message) rather than raising a raw TypeError.
- `TestZHCFolderApprovalGate` in `tools/engine/tests/test_safety_gate.py`:
  unit-level proof that `check_write` with `workflow_name="ZHC-Folder"` and NO
  token passes (the gate-side contract Bug 2a relies on).

### Not changed (safety gate preserved exactly)
- Fail-closed location whitelist, the approval gate semantics for non-ZHC names,
  dry-run refusals, draft-only default, the 1.0.3 build fail-loud / `link_steps`
  ordering, and the 1.0.4 token retry-once are all untouched.

## [1.0.6] - 2026-06-11 — fix: install auto-applies CORE_UPDATES + de-dup wrapper (single source) + CI install-path test

### Fixed (install integrity — root cause of boxes not knowing skill 44 is installed)
- **CORE_UPDATES were never auto-applied by INSTALL.md.** The "Done When" checklist listed
  the sentinel as a requirement, but no Action step actually wrote it. Agents on boxes where
  skill 44 was installed pre-this-fix had no `<!-- skill:44-convert-and-flow-operator:core-update-applied -->`
  in AGENTS.md / TOOLS.md / MEMORY.md, so the agent had no knowledge of Tier 0 and
  fell through to MCP on every GHL op. Added **Action 7** to INSTALL.md: idempotent script
  (guard checks for sentinel first) that appends the exact CORE_UPDATES.md blocks to
  AGENTS.md, TOOLS.md, and MEMORY.md automatically at install time.

### Fixed (wrapper single source — eliminates heredoc drift)
- **INSTALL.md Action 3 re-declared the wrapper as an inline heredoc**, creating a second
  copy of the wrapper logic that could silently diverge from `tools/engine/caf` (exactly how
  the `gohighlevel.main` bug in PR #167 happened: the engine wrapper was correct but the
  heredoc was stale). Action 3 now `cp`s the committed `tools/engine/caf`,
  `tools/engine/convertandflow`, and `tools/engine/ghl` wrappers to `$CAF_DIR/` instead of
  re-writing them inline. Single source — one place to edit wrapper logic, zero drift.

### Added (CI install-path test)
- **`.github/workflows/skill44-install-path.yml`** — new CI job `skill44-install-path` with
  two checks that run on every PR touching `44-convert-and-flow-operator/**`:
  1. `install-path-wrapper-exec` — asserts `tools/engine/caf` exec line is
     `python -m cli_anything.gohighlevel` (not `.main`), and that the `convertandflow`/`ghl`
     wrappers match. Fails on pre-#167 exec line. Guards against entrypoint drift.
  2. `install-path-core-updates-action` — asserts INSTALL.md contains the CORE_UPDATES
     auto-apply action (sentinel grep + `skill:44-convert-and-flow-operator:core-update-applied`
     present in Action 7 block). Fails without this fix.
  The workflow is additive — does not replace `skill44-e2e.yml`.

### QC (qc-convert-and-flow.sh)
- Two new static assertions in Section S:
  - `INSTALL.md contains CORE_UPDATES auto-apply action (Action 7)`
  - `INSTALL.md Action 3 uses cp (single-source wrapper, no inline heredoc)`

## [1.0.5] - 2026-06-11 — fix: INSTALL.md Action-3 heredoc used stale `cli_anything.gohighlevel.main` entrypoint (no `main.py` in engine 2.1.0)

### Fixed (install path)
- **INSTALL.md Action-3 heredoc** exec line corrected from
  `exec "$VENV/bin/python" -m cli_anything.gohighlevel.main "$@"` to
  `exec "$VENV/bin/python" -m cli_anything.gohighlevel "$@"`.
  Engine 2.1.0 (shipped in PR #163) removed `main.py` — the package entry point
  is now `__main__.py` which routes to `gohighlevel_cli:main`. The stale
  `.main` suffix caused `ModuleNotFoundError` on every `caf` invocation on any
  box installed with the 2.1.0 engine via INSTALL.md. The three committed wrapper
  scripts (tools/engine/caf, convertandflow, ghl) were already correct and are
  unchanged.

### Root cause
  Engine CLI was bumped 2.0.0 → 2.1.0 in PR #163; `main.py` was removed but the
  INSTALL.md heredoc was not updated to match. Boxes receiving the 2.1.0 engine
  via the heredoc install path broke silently; boxes that copied the committed
  wrapper scripts (e.g. hand-patched) were unaffected.

## [1.0.4] - 2026-06-11 — fix: retry-once on the transient Firebase token-refresh error for workflow writes

### Fixed (engine `internal/transport.py`)
- **Transient Firebase token-refresh failure now auto-retries ONCE before
  surfacing.** The securetoken refresh exchange can return `None` as a ONE-TIME
  transient (observed live on a managed box) and succeed on the very next call;
  the old code raised `TOKEN_REFRESH_FAILED` on the first `None`, falsely nudging
  the owner to re-grab a token that was still valid. `InternalTransport.get_token()`
  now retries the exchange **exactly once** on a `None` result, and only raises
  `TOKEN_REFRESH_FAILED` if the second attempt also fails. This is one retry, not
  a loop, and is disjoint from the existing request()-level 401/403 retry.

### Preserved (NOT weakened)
- The PR #163 build-path **fail-loud** behaviour is untouched: a downstream HTTP
  error dict (e.g. the 400 `corrupted order` save rejection) is returned UNCHANGED
  by `transport.request()` and never triggers a token-refresh exchange. Only a
  `None` from the securetoken exchange (transient) is retried; only a `None` from
  `_do_request` (401/403 auth signal) drives the separate one-shot `force_refresh`.

### Added
- `tools/engine/tests/test_token_retry.py` (`TestTokenRefreshRetryOnce`):
  - transient failure -> ONE retry -> success (exactly 2 exchange attempts);
  - persistent failure -> `TOKEN_REFRESH_FAILED` surfaced after one retry (exactly
    2 attempts — proves no loop);
  - happy path -> single attempt (never retried);
  - HTTP `_error` dict (400 corrupted-order) -> surfaced unchanged, no refresh
    triggered (guards the PR #163 fail-loud).
  The two retry tests FAIL on pre-1.0.4 transport and PASS after the fix.

## [1.0.3] - 2026-06-11 — fix: `workflows build` now ADDS action ordering and FAILS LOUD on rejected save; opportunities list snake_case params; payments list alias

### Fixed (CRITICAL — engine `workflow_builder.py`)
- **Bug 1a — `workflows build` omitted action ORDERING on the save PUT** (GHL rejected with
  400 `corrupted order`). `CampaignBuilder._create_workflow` now runs `link_steps()` on the
  plan templates ONCE up front and uses that linked copy (carrying `order`/`next`/`parentKey`)
  for the Step-2 first-step link, the Step-3 step-save PUT body, AND the Step-4 sync PUT.
  Previously `link_steps` was defined but never called on the build path, so the very first
  save PUT had zero execution chain and GHL rejected it.
- **Bug 1b — `workflows build` SWALLOWED a non-2xx save and printed `Steps: 0, Errors: 0`
  (false success, exit 0).** A rejected step-save PUT (transport returns
  `{"_error": True, "http_code": 400, ...}`) is now captured as a real error string
  (including HTTP code + message), returned from `_create_workflow`, and appended to
  `stats['errors']` UNCONDITIONALLY (not gated on the workflow-shell id). The CLI
  (`workflows build` / `workflows create` / `workflows create-n8n`) now prints the error
  summary to stderr and exits non-zero whenever `stats['errors']` is non-empty.

### Fixed (engine CLI `gohighlevel_cli.py`)
- **Bug 3 — `opportunities list` 422 from camelCase params.** `GET /opportunities/search`
  now sends snake_case `location_id`/`pipeline_id` (the one search endpoint that diverges
  from the camelCase convention). The create/update BODIES (camelCase) are unchanged.
- **Bug 4 — `payments` had no `list` verb.** Added a thin `payments list` alias that
  forwards to `payments transactions`, so the uniform `<group> list` pattern works.
  Explicit `transactions`/`orders`/`invoices` verbs are unchanged.

### Changed
- Engine CLI version bumped `2.0.0` -> `2.1.0` (behavior change: build applies ordering and
  fails loud on a rejected save).

### Added
- Regression tests `TestBuildFailsLoudAndEmitsOrdering` in
  `tools/engine/tests/test_e2e_unit11.py`:
  - TEST A asserts a rejected step-save exits non-zero with the 400/`corrupted order`
    cause surfaced (guards the exact pre-fix Steps:0/Errors:0/exit-0 false-success shape).
  - TEST B asserts the FIRST (step-save) PUT body carries `order` `[0,1,2]` plus
    `next`/`parentKey` links — proving `link_steps` ran BEFORE the save PUT.
  Both tests FAIL on pre-fix main and PASS after the fix.
- `qc-convert-and-flow.sh` static asserts for the build-path `link_steps`, CLI fail-loud,
  snake_case opportunities params, payments list alias, the regression test, and the
  `convertandflow`/`ghl` wrapper auto-seed parity.

### Hardening (consistency, not a blocker)
- `tools/engine/convertandflow` and `tools/engine/ghl` wrappers now apply the same
  `CAF_ALLOWED_LOCATION_IDS` auto-seed-from-`GHL_LOCATION_ID` logic that `caf` got in 1.0.2,
  so a blank whitelist never silently blocks all writes on any of the three runtime wrappers.
- `INSTALL.md` Action 3 installed wrapper now exports `CAF_ALLOWED_LOCATION_IDS` /
  `CAF_DRAFT_ONLY` / `CAF_DRY_RUN` (the exact names `safety_gate.py` reads) instead of the
  `GHL_`-prefixed names the gate ignores — matching the shipped engine wrappers.

### Not changed (safety gate preserved exactly)
- Fail-closed location whitelist, approval gate, and dry-run refusals (all `sys.exit(1)` on
  `SafetyRefused`). Draft-only default. `STRIP_KEYS`. Transport 401 retry-once / 429 no-retry.

## [1.0.2] - 2026-06-11 — fix: CAF_ALLOWED_LOCATION_IDS auto-seeds from GOHIGHLEVEL_LOCATION_ID at install

### Fixed
- `tools/engine/caf` (engine wrapper): `CAF_ALLOWED_LOCATION_IDS` no longer defaults to
  blank, which silently blocked every write on a fresh single-location install. When neither
  `GOHIGHLEVEL_ALLOWED_LOCATION_IDS` nor `CAF_ALLOWED_LOCATION_IDS` is set, the wrapper now
  seeds the whitelist from `GHL_LOCATION_ID` (i.e. the client's own location) and emits:
  `[caf] Allowed write locations set to <id>; add more in CAF_ALLOWED_LOCATION_IDS`
- `INSTALL.md` Action 3 (installed wrapper written to disk): same auto-seed logic applied
  so the problem cannot re-emerge after a fresh install.
- `INSTALL.md` Action 5 (credential wiring step): now explicitly wires
  `GOHIGHLEVEL_ALLOWED_LOCATION_IDS` via `openclaw config set` to `$GOHIGHLEVEL_LOCATION_ID`
  as the initial value, matching the auto-seed logic.

### Added
- `INSTALL.md` "Note: Write-location whitelist auto-seed" section explaining the behaviour,
  the log line, and how to add additional sub-account IDs for multi-location setups.

### Not changed
- Draft-only default (`GOHIGHLEVEL_DRAFT_ONLY=true`) untouched.
- Approval gate untouched.
- Engine internals untouched.

## [1.0.1] - 2026-06-11 — Chrome extension: switch to load-unpacked (no Chrome Web Store)

### Changed
- Chrome extension delivery method: NOT publishing to the Chrome Web Store.
  Clients load the extension unpacked via chrome://extensions → Developer mode ON →
  "Load unpacked" → select tools/chrome-extension/.
- INSTALL.md: added Action 5b with full load-unpacked steps (get folder, install,
  grab token, store as GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN, reload after edits).
- SKILL.md: added "Chrome Extension: Token Grabber" section documenting the no-web-store
  decision, what the extension does (zero network calls, IndexedDB reader), and the
  tools/chrome-extension/ file manifest.
- tools/chrome-extension/: added as top-level client-facing copy of the extension
  (manifest.json, popup.html, popup.js, icon48.png — identical to the zip the operator
  ships). Skill is now self-contained.

## [1.0.0] - 2026-06-10 — Initial release

### Added
- Full Tier 0 GHL operator: caf/convertandflow/ghl CLI wrapper over the de-branded
  Convert and Flow engine (Jay's zip, stripped of Nextcloud/Blotato, de-branded builders,
  Chrome extension rebranded, UNIVERSAL templates).
- Token-aware routing: PIT for standard ops; Firebase refresh token for workflow writes;
  graceful fall-through to Tier 4 when Firebase token absent.
- Write-safety posture: dry-run, draft-only default (GOHIGHLEVEL_DRAFT_ONLY=true),
  location whitelist, approval gate, ZHC- standing approval.
- Workflow-write data rollback: pre-write snapshot before every mutation; `workflows restore`.
- TRINITY gate: any conversational workflow build auto-invokes skill 38; qc-convert-and-flow.sh
  calls qc-trinity-registry.sh as a hard gate.
- Dependency-first contract from skill 41: refuses to build if dependencies don't exist.
- Engine vendored at tools/engine/ (from skill44-build/engine).
- Platform overlays: platform/mac/ (venv at ~/.openclaw/tools/..., auto-re-grab recipe) +
  platform/vps/ (venv at /data/.openclaw/tools/..., owner-nudge on expired token).
- Client-facing plain-language auto-re-grab disclosure in INSTALL.md (binding transparency).
- qc-convert-and-flow.sh with assertions for all acceptance criteria.
