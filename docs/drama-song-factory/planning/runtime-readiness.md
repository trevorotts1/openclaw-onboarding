# Runtime readiness — W0-04 / DTS-104

Owned scope: this file only. No merge, no publish, no self-approve. Repo root is not a git repo (`Is a git repository: false` at invocation), so no commit exists for this unit — artifact = this file. Test evidence: `<build-root>/lanes/DTS-104-lane/check.py` (run output in `evidence.md` in same lane).

## 1. Workflow guard pattern and caps

Name pattern enforced in the validator, invoked by `guard.py validate()`:

- `~/.claude/hooks/workflow-guard/validate.mjs:8` — `const NAME_RE=/^[a-z0-9]{2,12}-W[0-9]{1,2}-(build\+qc|build|qc|repair|merge|test)-[A-Z]{2,5}[0-9]{3,}(\.\.[A-Z]{2,5}[0-9]{3,})?-([0-9]{1,2})L$/;`
- `validate.mjs:9` — `const NAME_EXAMPLE='pres-W2-build+qc-SKR012..SKR019-8L';`
- `validate.mjs:33` — bad `meta.name` error tells caller to `Regenerate with make-workflow.py --program <slug> --wave <n> --phase build+qc.`
- `validate.mjs:105` — `const TOTAL_CEILING=200;` (total-call runaway backstop; `validate.mjs:106` errors above it)
- `validate.mjs:107-108` — `const envCap=Number.parseInt(process.env.WORKFLOW_GUARD_CAP??'',10);` + `const cap=Number.isInteger(envCap)&&envCap>=1&&envCap<=10?envCap:Math.min(10,Math.max(1,os.cpus().length-2));` — effective lane cap, hard ceiling 10, else host CPUs minus 2.
- `validate.mjs:109` — name lane count must equal computed bound (`name claims N lanes, script has M`).
- `validate.mjs:110` — `Computed upper bound ${bound} concurrent agents exceeds effective cap ${cap} (hard ceiling 10).`
- `validate.mjs:116` — multi-lane scripts must carry the SCRATCH ISOLATION rule in agent prompts.
- `validate.mjs:117-123` — provider-slots mechanism: `readyUnits` must be nonnegative int; `providerSlots` positive int; `bound>slots` errors (`Workflow exceeds declared available provider slots`); `bound<min(ready,slots,cap)` without `dependencyReason` errors (`Unused ready capacity`).

Running-at-once accounting in `guard.py`:

- `guard.py:67-68` — `LIMITS_FILE=STATE/'limits.json'`; `LIMITS_DEFAULTS={'concurrent_agents_per_workflow':1000000,'concurrent_workflows_per_program':1000000,'concurrent_agents_total':1000000,'session_lease_seconds':3600}`.
- `guard.py:62-66` — ceilings are safety guards, never approval gates; live in `state/limits.json`.
- `guard.py:226-259` — `admit_launch()` checks peak vs per-workflow cap (`guard.py:243-245`), workflows-per-program (`246-248`), total agents (`249-250`) in one `BEGIN IMMEDIATE` transaction.
- `guard.py:492` — launch records `result['conservativePeak']`; `guard.py:496` — post-validation message `validated {peak} maximum active lanes; cap {cap}`.
- `guard.py:708` — `This workflow worker must not spawn descendants... within ten slots.`
- `guard.py:766` — SessionStart text still narrates `(defaults 10 per workflow, 50 workflows per program, 500 agents total)`; live `state/limits.json` overrides all three to `1000000` with `session_lease_seconds: 3600` (read 2026-10-06). Validator hard ceiling 10 still bounds each script.

`make-workflow.py` usage:

- `make-workflow.py:14` — `PROGRAM_RE = re.compile(r'^[a-z0-9]{2,12}$')`; `:15` — `UNIT_ID_RE = re.compile(r'^[A-Z]{2,5}-[0-9]{3,}$')`; `:16` — `NAME_RE` (same pattern as validator); `:17` — `PHASE_CHOICES = ('build+qc', 'build', 'qc', 'repair', 'merge', 'test')`.
- `make-workflow.py:36-46` — `host_cap()`: `WORKFLOW_GUARD_CAP` int 1..10 wins, else `max(1, cpu_count-2)`.
- Required flags — `make-workflow.py:133` `--units`, `:135` `--provider-slots` (required), `:136` `--reserve`, `:137` `--program`, `:140` `--wave`, `:139` `--phase`, `:140` `--run-root` (absolute), `:141` `--dependency-reason`, `:142-143` `--builder`/`--reviewer` (must differ).
- `make-workflow.py:158` — `cap = min(10, host_cap(), a.provider_slots - a.reserve)`; slice width = cap (`:171`).
- `make-workflow.py:88-91` — `slice_name()`: `<program>-W<wave>-<phase>-<firstID>[..<lastID>]-<lanes>L`.
- `make-workflow.py:179` — embeds `INPUT.guard = {readyUnits, providerSlots: cap, dependencyReason, runRoot}`.
- `make-workflow.py:204-206` — per slice prints `VALIDATED_NOT_LAUNCHED` + `LAUNCH: call the Workflow tool with exactly {"scriptPath": "<target>"} (nothing else). Then open /workflows, confirm the name ... shows N lanes, and record the Task ID and Run ID in the ledger.`

## 2. W0-04 launch receipt — PROVEN IDs

Source: guard journal DB `~/.claude/hooks/workflow-guard/state/guard.sqlite3`, table `launches`, row `id=call_155luf0a` (queried 2026-10-06):

- Workflow name: `dts-W0-build+qc-DTS101..DTS102-2L`
- Run ID: `wf_4b8b2d4f-edb`
- Task ID: `wisxp6m2t`
- State: `COMPLETED`
- Transcript: `<session-dir>.jsonl` (3.0M, exists)
- Receipt: `{"response_keys": ["status", "taskId", "taskType", "workflowName", "runId", "summary", "transcriptDir", "scriptPath"], "event": "PostToolUse", "task_id": "wisxp6m2t", "run_id": "wf_4b8b2d4f-edb", "visibility": "UNVERIFIED"}`
- Journal dir: `<session-dir>/subagents/workflows/wf_4b8b2d4f-edb/` — `journal.jsonl` 8 lines: line 1 `{"type":"launched"}`, lines 2-3 `started build:DTS-101` / `build:DTS-102`, line 4 `result` DTS-101 `status PASS`, line 5+ `started qc:DTS-101`. Agent journals for both build lanes present in same dir.

Visibility verdict: **PROVEN IDs** — background launch returned Task ID + Run ID, receipt row exists, journal + transcript exist with worker events. Guard's own `visibility` marker reads `UNVERIFIED` (means native `/workflows` rendered-tree check not recorded in DB, not that launch failed). No bare `/workflows` tree screenshot in evidence — that half stays UNVERIFIED.

## 3. opus-chain members — DEFINED by setup script, live router not probed

Concrete member models come from the 999-setup wiring script (checked 2026-10-06):

- `<build-root>/999-setup/.claude/skills/nine-router-setup/scripts/common/configure-nine-router.mjs:450-452` — `dsPrefix="ds"`, `olPrefix="ollama"`, `agPrefix="agnes"`.
- `:383-384` — `dsMaxPrefix = "ds-max"` (custom DeepSeek node for max-thinking Opus lane).
- `:460` — `const dsMaxFlash = \`${dsMaxPrefix}/deepseek-v4-flash(max)\`; // DS Max = Flash + max`
- `:465` — `const agFlash = \`${agPrefix}/agnes-2.5-flash\`;`
- `:477` — `RESOLVED_ROUTES.opus = "opus-chain"; // Opus → opus-chain (primary: DS Max = DeepSeek v4 FLASH, thinking MAX; fallback: Agnes 2.5 Flash)`
- `:518` — `await upsertCombo("opus-chain", [dsMaxFlash, agFlash]);` → members: **`ds-max/deepseek-v4-flash(max)` primary, `agnes/agnes-2.5-flash` fallback**.
- `:553` — `"opus-chain": { fallbackStrategy: "fallback" }`.
- `:595,619` — post-config live probes hit `RESOLVED_ROUTES.opus` for HTTP + thinking-level verification.
- Provider thinking wiring `:434-439` — DS Max node forced `mode: "max"`.

spec-protocol references name the route only (no member lists):

- `999-setup/.claude/skills/spec-protocol/tools/hooks/dispatch-gate.py:1825` — `"builderRoute": "opus-chain", "qcRoute": "sonnet-chain"` (profile template).
- `999-setup/.claude/skills/spec-protocol/tools/repo-anchor.sh:774` — same pair in anchor template.
- `999-setup/.claude/skills/spec-protocol/tools/project-profile-selftest.sh:8,68` — fixture profile + assertion on the pair.
- `999-setup/.claude/skills/spec-protocol/tools/seat-check.sh:435` — alias map `ANTHROPIC_DEFAULT_OPUS_MODEL=opus-chain ...`; `:449` opus-lane selftest; `:487` settings fallback fixture.

`~/.openclaw` check (2026-10-06): grepped `config`, `credentials`, `agents` trees for `opus-chain` — **zero hits**. `find` for a 9Router config file surfaced only logs/scripts (`logs/9router-log-retention.log`, `scripts/9router-log-retention.sh`, `999-setup/launchers/macos/get-9router-key.sh`). Live router combo membership (management API / persistence DB) was **not queried** — direct DB edits are forbidden by `999-setup/CLAUDE.md` rule 8/16, and no live probe ran from this lane. So: members DEFINED-BY-SETUP-SCRIPT as above; live-router state UNDETERMINED, no file omitted.

## 4. Measured capacity

`sysctl` 2026-10-06, operator Mac Mini: `hw.ncpu: 12`, `hw.memsize: 25769803776` (24 GiB), `hw.physicalcpu: 12`, `hw.logicalcpu: 12`; `os.cpu_count() = 12`.

Build lane assumption: host ceiling = `cpu_count - 2 = 10`, hard ceiling 10 → **measured max concurrent lanes = 10** (`make-workflow.py:36-46`, `validate.mjs:107-108`). Effective slice width = `min(10, host_cap, provider_slots - reserve)` (`make-workflow.py:158`). W0 slice ran 2 lanes under `providerSlots: 8, readyUnits: 4` (launch INPUT recorded in `state/scripts/3e6147e833570435e94cf7cec4f86d9466ec2fa69f746f919d1fb528f23008a5.js:4`).

## 5. QC seat — bound fallback pending W1-08 pinning

No `policy.qcRoute` exists for this program yet: `find <build-root> -maxdepth 2 -name .spec-protocol.json` returns nothing (2026-10-06). Bound rule is the packet fallback:

- `<build-root>/packet/CLAUDE_NINE_DRAMA_...:253` (directive) — `**QC route:** use the bound project's explicit \`policy.qcRoute\` when present. If absent, follow the current approved technical-QC seat rule (\`sonnet\` alias under Claude-Nine; Sonnet under plain Claude Code), resolving the actual provider/model before the first verdict. ... \`sonnet-chain\` is not automatically independent of \`opus-chain\`. See \`QC-REPAIR.md\` ...`
- `<build-root>/packet/QC-REPAIR.md:10` (swarm packet) — `| QC/recheck | The bound project's explicit **\`policy.qcRoute\`** when present. Otherwise use the current approved technical-QC seat rule: **\`sonnet\` alias for Claude-Nine; Sonnet for plain Claude Code**. Resolve and record its actual model before the first verdict. |`
- `QC-REPAIR.md:12` — no-QC-pin + default-collides path: select approved callable independent seat, bind before use.
- `QC-REPAIR.md:16` — W0-04 resolves concrete assignments before first verdict.

**Bound route: `sonnet` QC seat (fallback rule)**, pending W1-08 pinning. Actual provider/model resolution + independence proof against opus-chain members (§3) due before first verdict.

---
*ponytail:* live-router combo read skipped (management-API probe); add when a verdict needs it — query combos via 9Router API, never the DB file.
