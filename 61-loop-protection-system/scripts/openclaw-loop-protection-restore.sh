#!/usr/bin/env bash
# openclaw-loop-protection-restore.sh
#
# Post-update restore-and-verify for the OpenClaw runaway-tool-loop protection stack.
#
# WHY THIS EXISTS
#   `openclaw update` reinstalls node_modules and silently reverts the dist patch that makes a
#   runaway tool loop actually abort. It can also regenerate the service-env file. This script
#   detects every piece of the protection stack, and with --apply puts back the ones it is safe
#   to put back.
#
# USAGE
#   openclaw-loop-protection-restore.sh              # read-only check (default)
#   openclaw-loop-protection-restore.sh --apply      # check, then repair what is repairable
#   openclaw-loop-protection-restore.sh --help
#
# EXIT CODES
#   0  all checks passed, nothing to do
#   3  drift found and NOT repaired (check-only run, or an item that needs a human)
#   4  hard failure (upstream code changed, a must-be-true safety setting is false, etc.)
#   2  usage error / missing prerequisite
#
# SECURITY
#   Two files inspected here are full of plaintext secrets: the gateway service-env file and
#   openclaw.json. This script compares by KEY NAME and by boolean/numeric value only. It never
#   echoes, cats, prints, or logs a value out of either file. There is no flag that turns
#   redaction off. `ps eww` and `launchctl print` are never used (they dump every secret inline).
#
# SAFETY
#   Read-only by default. Mutations only under --apply. Idempotent. Every write is atomic
#   (temp file + rename, never in-place truncation) and preceded by a timestamped, cmp-verified
#   backup. NEVER restarts the gateway - if a restart is needed it says so and exits.
#
# PORTABILITY
#   All paths derive from $HOME / the resolved openclaw binary. No hostnames, client names,
#   chat IDs, tokens, or absolute machine-specific paths. Safe to ship fleet-wide unmodified.

set -uo pipefail

VERSION="1.0.0"

# ---------------------------------------------------------------------------- flags
MODE="check"
for arg in "$@"; do
  case "${arg}" in
    --apply) MODE="apply" ;;
    --check) MODE="check" ;;
    --version) printf '%s\n' "${VERSION}"; exit 0 ;;
    -h|--help)
      /usr/bin/sed -n '2,40p' "$0" | /usr/bin/sed 's/^# \{0,1\}//'
      exit 0 ;;
    *) printf 'Unknown argument: %s (try --help)\n' "${arg}" >&2; exit 2 ;;
  esac
done

if [ "${EUID:-$(id -u)}" = "0" ]; then
  printf 'REFUSING TO RUN AS ROOT: writing OpenClaw config as root corrupts ownership.\n' >&2
  exit 2
fi

# ---------------------------------------------------------------------------- paths
TS="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_ROOT="${HOME}/.openclaw-patch-backups/restore-${TS}"
ENV_FILE="${HOME}/.openclaw/service-env/ai.openclaw.gateway.env"
STUB_SCRIPT="${HOME}/.openclaw/scripts/ensure-daily-memory-stub.sh"
HOOKS_DIR="${HOME}/.openclaw/hooks"
EXT_DIR="${HOME}/.openclaw/extensions"
CLAUDE_SETTINGS="${HOME}/.claude/settings.json"
QUARANTINE_DIR="${HOME}/.openclaw/.ceo-gate-quarantine-${TS}"

resolve_bin() {
  local candidate
  candidate="$(command -v openclaw 2>/dev/null)" || candidate=""
  if [ -z "${candidate}" ] && [ -x "${HOME}/.npm-global/bin/openclaw" ]; then
    candidate="${HOME}/.npm-global/bin/openclaw"
  fi
  printf '%s' "${candidate}"
}
OC_BIN="$(resolve_bin)"

resolve_node() {
  local candidate
  candidate="$(command -v node 2>/dev/null)" || candidate=""
  printf '%s' "${candidate}"
}
NODE_BIN="$(resolve_node)"

resolve_dist_dir() {
  # Test override first, then the openclaw binary's own package, then npm root -g.
  if [ -n "${OPENCLAW_DIST_DIR:-}" ]; then printf '%s' "${OPENCLAW_DIST_DIR}"; return; fi
  local target pkg root
  if [ -n "${OC_BIN}" ]; then
    target="$(cd "$(dirname "${OC_BIN}")" 2>/dev/null && pwd -P)/$(basename "${OC_BIN}")"
    while [ -L "${target}" ]; do
      local link; link="$(readlink "${target}")"
      case "${link}" in
        /*) target="${link}" ;;
        *)  target="$(cd "$(dirname "${target}")" && cd "$(dirname "${link}")" && pwd -P)/$(basename "${link}")" ;;
      esac
    done
    pkg="$(dirname "${target}")"
    if [ -d "${pkg}/dist" ]; then printf '%s' "${pkg}/dist"; return; fi
  fi
  root="$(npm root -g 2>/dev/null)" || root=""
  if [ -n "${root}" ] && [ -d "${root}/openclaw/dist" ]; then printf '%s' "${root}/openclaw/dist"; return; fi
  printf ''
}
DIST_DIR="$(resolve_dist_dir)"

# ---------------------------------------------------------------------------- output
PASS_N=0; DRIFT_N=0; FAIL_N=0; FIXED_N=0
RESTART_NEEDED=0
declare -a MANUAL_ACTIONS=()

ok()     { PASS_N=$((PASS_N+1));  printf '  [ OK ]   %s\n' "$1"; }
drift()  { DRIFT_N=$((DRIFT_N+1)); printf '  [DRIFT]  %s\n' "$1"; }
fail()   { FAIL_N=$((FAIL_N+1));  printf '  [ FAIL]  %s\n' "$1"; }
fixed()  { FIXED_N=$((FIXED_N+1)); printf '  [FIXED]  %s\n' "$1"; }
info()   { printf '           %s\n' "$1"; }
section(){ printf '\n%s\n' "$1"; }
manual() { MANUAL_ACTIONS+=("$1"); }

# Timestamped, cmp-verified backup. Returns non-zero if the backup cannot be trusted.
backup_file() {
  local src="$1" name dest
  [ -f "${src}" ] || return 0
  name="$(basename "${src}")"
  mkdir -p "${BACKUP_ROOT}" || return 1
  dest="${BACKUP_ROOT}/${name}.${TS}.bak"
  cp -p "${src}" "${dest}" || return 1
  cmp -s "${src}" "${dest}" || return 1
  printf '%s' "${dest}"
}

# ---------------------------------------------------------------------------- prereqs
if [ -z "${OC_BIN}" ]; then
  printf 'PREREQUISITE MISSING: openclaw binary not found on PATH nor at $HOME/.npm-global/bin/openclaw\n' >&2
  exit 2
fi
if [ -z "${NODE_BIN}" ]; then
  printf 'PREREQUISITE MISSING: node not found on PATH (OpenClaw requires it)\n' >&2
  exit 2
fi
if [ -z "${DIST_DIR}" ] || [ ! -d "${DIST_DIR}" ]; then
  printf 'PREREQUISITE MISSING: could not locate the OpenClaw dist directory\n' >&2
  exit 2
fi

OC_VERSION="$("${OC_BIN}" --version 2>/dev/null | /usr/bin/head -1)" || OC_VERSION="unknown"

printf '================================================================\n'
printf ' OpenClaw loop-protection restore & verify   (script v%s)\n' "${VERSION}"
printf ' mode: %s        openclaw: %s\n' "${MODE}" "${OC_VERSION:-unknown}"
printf '================================================================\n'

# ---------------------------------------------------------------------------- helper: config get
# Prints the raw value of a config path. ONLY ever called on non-secret numeric/boolean/
# structural paths listed in this script. Never called on provider keys or channel tokens.
cfg_get() { "${OC_BIN}" config get "$1" 2>/dev/null; }

# Returns 0 if the path exists at all.
cfg_has() { "${OC_BIN}" config get "$1" >/dev/null 2>&1; }

cfg_set_json() {
  local path="$1" value="$2"
  "${OC_BIN}" config set "${path}" "${value}" --strict-json >/dev/null 2>&1
}

# ============================================================================
# 1. DIST PATCH  (runaway tool-loop abort)
# ============================================================================
section "1. Runaway tool-loop abort patch (OpenClaw dist)"

PATCHER="$(/usr/bin/mktemp -t ocloop-patcher.XXXXXX)" || { printf 'mktemp failed\n' >&2; exit 2; }
PATCHER_MJS="${PATCHER}.mjs"
mv "${PATCHER}" "${PATCHER_MJS}"
cleanup() { rm -f "${PATCHER_MJS}"; }
trap cleanup EXIT

# The patch table is the single source of truth. Anchors are exact byte strings from
# OpenClaw's built dist. If an anchor is neither found nor already-applied, upstream changed
# and we FAIL LOUDLY rather than guess - a wrong patch is worse than no patch.
cat > "${PATCHER_MJS}" <<'NODEEOF'
import { readFileSync, writeFileSync, renameSync, statSync, chmodSync } from "node:fs";
import { join } from "node:path";

const distDir = process.argv[2];
const mode = process.argv[3] || "check";        // check | apply
const groupFilter = process.argv[4] || "all";   // all | a | b   (revert helper for mutation tests)
const revert = process.argv[5] === "revert";

const L = (...lines) => lines.join("\n");

const HUNKS = [
  {
    id: "a1", group: "a", file: "tool-loop-detection-QRwz_WH8.js",
    marker: "deniedReason: details.deniedReason",
    what: "loop-veto outcomes are hashed and recorded instead of discarded",
    find: L('\tif (isLoopVetoResult(details)) return { resultHash: void 0 };'),
    repl: L(
      '\tif (isLoopVetoResult(details)) return {',
      '\t\tresultHash: digestStable({',
      '\t\t\tstatus: details.status,',
      '\t\t\tdeniedReason: details.deniedReason',
      '\t\t}),',
      '\t\tloopVeto: true',
      '\t};'),
  },
  {
    id: "a2", group: "a", file: "tool-loop-detection-QRwz_WH8.js",
    marker: "vetoStreak += 1;",
    what: "blocked attempts extend the no-progress streak instead of resetting it",
    find: L(
      'function getNoProgressStreak(history, toolName, argsHash) {',
      '\tlet streak = 0;',
      '\tlet latestResultHash;',
      '\tfor (let i = history.length - 1; i >= 0; i -= 1) {',
      '\t\tconst record = history[i];',
      '\t\tif (!record || record.toolName !== toolName || record.argsHash !== argsHash) continue;',
      '\t\tif (typeof record.resultHash !== "string" || !record.resultHash) continue;'),
    repl: L(
      'function getNoProgressStreak(history, toolName, argsHash) {',
      '\tlet streak = 0;',
      '\tlet vetoStreak = 0;',
      '\tlet latestResultHash;',
      '\tfor (let i = history.length - 1; i >= 0; i -= 1) {',
      '\t\tconst record = history[i];',
      '\t\tif (!record || record.toolName !== toolName || record.argsHash !== argsHash) continue;',
      '\t\tif (record.loopVeto === true) {',
      '\t\t\tvetoStreak += 1;',
      '\t\t\tcontinue;',
      '\t\t}',
      '\t\tif (typeof record.resultHash !== "string" || !record.resultHash) continue;'),
  },
  {
    id: "a3", group: "a", file: "tool-loop-detection-QRwz_WH8.js",
    marker: "count: streak + vetoStreak,",
    what: "no-progress streak count includes blocked attempts",
    find: L(
      '\treturn {',
      '\t\tcount: streak,',
      '\t\tlatestResultHash',
      '\t};',
      '}',
      'function getPingPongStreak(history, currentSignature) {'),
    repl: L(
      '\treturn {',
      '\t\tcount: streak + vetoStreak,',
      '\t\tlatestResultHash',
      '\t};',
      '}',
      'function getPingPongStreak(history, currentSignature) {'),
  },
  {
    id: "a4", group: "a", file: "tool-loop-detection-QRwz_WH8.js",
    marker: "if (outcome.loopVeto === true) call.loopVeto = true;",
    what: "loop-veto marker carried onto an updated history record",
    find: L(
      '\t\tcall.resultHash = resultHash;',
      '\t\tcall.unknownToolName = outcome.unknownToolName;',
      '\t\tmatched = true;'),
    repl: L(
      '\t\tcall.resultHash = resultHash;',
      '\t\tcall.unknownToolName = outcome.unknownToolName;',
      '\t\tif (outcome.loopVeto === true) call.loopVeto = true;',
      '\t\tmatched = true;'),
  },
  {
    id: "a5", group: "a", file: "tool-loop-detection-QRwz_WH8.js",
    marker: "...outcome.loopVeto === true ? { loopVeto: true } : {},",
    what: "loop-veto marker carried onto a newly pushed history record",
    find: L(
      '\t\t\tresultHash,',
      '\t\t\tunknownToolName: outcome.unknownToolName,',
      '\t\t\ttimestamp: Date.now()'),
    repl: L(
      '\t\t\tresultHash,',
      '\t\t\tunknownToolName: outcome.unknownToolName,',
      '\t\t\t...outcome.loopVeto === true ? { loopVeto: true } : {},',
      '\t\t\ttimestamp: Date.now()'),
  },
  {
    id: "b1", group: "b", file: "embedded-agent-DGUuxGR2.js",
    marker: "function createToolLoopRunawayGuard(config, options) {",
    what: "always-armed runaway guard + ToolLoopRunawayAbortError defined",
    find: L(
      '};',
      '//#endregion',
      '//#region src/agents/embedded-agent-runner/run/failover-policy.ts'),
    repl: L(
      '};',
      'const runawayLog = createSubsystemLogger("agents/tool-loop-runaway");',
      'const DEFAULT_RUNAWAY_THRESHOLD = 6;',
      'const RUNAWAY_MIN_THRESHOLD = 4;',
      'const RUNAWAY_WINDOW_MULTIPLIER = 3;',
      '/**',
      '* Always-armed runaway tool-loop guard.',
      '*',
      '* Unlike the post-compaction guard this never disarms. It watches every recorded tool',
      '* outcome for the whole run and trips when one (toolName, argsHash, resultHash) triple',
      '* repeats globalCircuitBreakerThreshold times inside a bounded window of recent outcomes.',
      '* The bounded window is what keeps legitimate, widely-spaced repeat calls from tripping it.',
      '*/',
      'function createToolLoopRunawayGuard(config, options) {',
      '\tconst enabled = options?.enabled !== false;',
      '\tconst threshold = Math.max(asPositiveInt(config?.globalCircuitBreakerThreshold, DEFAULT_RUNAWAY_THRESHOLD), RUNAWAY_MIN_THRESHOLD);',
      '\tconst windowSize = threshold * RUNAWAY_WINDOW_MULTIPLIER;',
      '\tconst recentKeys = [];',
      '\tlet tripped = false;',
      '\tconst observe = (call) => {',
      '\t\tif (!enabled || tripped) return { shouldAbort: false };',
      '\t\tconst toolName = call?.toolName;',
      '\t\tconst argsHash = call?.argsHash;',
      '\t\tconst resultHash = call?.resultHash;',
      '\t\tif (typeof toolName !== "string" || typeof argsHash !== "string" || typeof resultHash !== "string" || !resultHash) return { shouldAbort: false };',
      '\t\tconst key = `${toolName}\\u0000${argsHash}\\u0000${resultHash}`;',
      '\t\trecentKeys.push(key);',
      '\t\tif (recentKeys.length > windowSize) recentKeys.splice(0, recentKeys.length - windowSize);',
      '\t\tlet count = 0;',
      '\t\tfor (const entry of recentKeys) if (entry === key) count += 1;',
      '\t\tif (count < threshold) return { shouldAbort: false };',
      '\t\ttripped = true;',
      '\t\trunawayLog.error(`tool loop runaway abort: tool=${toolName} identical args+result repeated ${count} times within last ${recentKeys.length} tool outcomes (threshold=${threshold})`);',
      '\t\treturn {',
      '\t\t\tshouldAbort: true,',
      '\t\t\tdetector: "tool_loop_runaway",',
      '\t\t\tcount,',
      '\t\t\ttoolName,',
      '\t\t\tmessage: `CRITICAL: tool ${toolName} produced ${count} identical argument+result outcomes within the last ${recentKeys.length} tool calls of this run (threshold ${threshold}). Aborting the run to stop a runaway tool loop.`',
      '\t\t};',
      '\t};',
      '\treturn { observe };',
      '}',
      '/** Error raised when the always-armed runaway tool-loop guard aborts a run. */',
      'var ToolLoopRunawayAbortError = class ToolLoopRunawayAbortError extends Error {',
      '\tconstructor(message, details) {',
      '\t\tsuper(message);',
      '\t\tthis.name = "ToolLoopRunawayAbortError";',
      '\t\tthis.detector = details.detector;',
      '\t\tthis.count = details.count;',
      '\t\tthis.toolName = details.toolName;',
      '\t}',
      '\tstatic fromVerdict(verdict) {',
      '\t\treturn new ToolLoopRunawayAbortError(verdict.message, {',
      '\t\t\tdetector: verdict.detector,',
      '\t\t\tcount: verdict.count,',
      '\t\t\ttoolName: verdict.toolName',
      '\t\t});',
      '\t}',
      '};',
      '//#endregion',
      '//#region src/agents/embedded-agent-runner/run/failover-policy.ts'),
  },
  {
    id: "b2", group: "b", file: "embedded-agent-DGUuxGR2.js",
    marker: "const toolLoopRunawayGuard = createToolLoopRunawayGuard(",
    what: "runaway guard instantiated for every run",
    find: L('\t\t\tconst postCompactionGuard = createPostCompactionLoopGuard(resolvedLoopDetectionConfig?.postCompactionGuard, { enabled: resolvedLoopDetectionConfig?.enabled !== false });'),
    repl: L(
      '\t\t\tconst postCompactionGuard = createPostCompactionLoopGuard(resolvedLoopDetectionConfig?.postCompactionGuard, { enabled: resolvedLoopDetectionConfig?.enabled !== false });',
      '\t\t\tconst toolLoopRunawayGuard = createToolLoopRunawayGuard(resolvedLoopDetectionConfig, { enabled: resolvedLoopDetectionConfig?.enabled !== false });'),
  },
  {
    id: "b3", group: "b", file: "embedded-agent-DGUuxGR2.js",
    marker: "const runawayVerdict = toolLoopRunawayGuard.observe(observation);",
    what: "runaway verdict aborts the run via the lane abort controller",
    find: L(
      '\t\t\t\tconst verdict = postCompactionGuard.observe(observation);',
      '\t\t\t\tif (verdict.shouldAbort) {',
      '\t\t\t\t\tpostCompactionAbortError ??= PostCompactionLoopPersistedError.fromVerdict(verdict);',
      '\t\t\t\t\tlaneTaskAbortController.abort(postCompactionAbortError);',
      '\t\t\t\t\tpostCompactionAbortController?.abort(postCompactionAbortError);',
      '\t\t\t\t}'),
    repl: L(
      '\t\t\t\tconst verdict = postCompactionGuard.observe(observation);',
      '\t\t\t\tif (verdict.shouldAbort) {',
      '\t\t\t\t\tpostCompactionAbortError ??= PostCompactionLoopPersistedError.fromVerdict(verdict);',
      '\t\t\t\t\tlaneTaskAbortController.abort(postCompactionAbortError);',
      '\t\t\t\t\tpostCompactionAbortController?.abort(postCompactionAbortError);',
      '\t\t\t\t}',
      '\t\t\t\tconst runawayVerdict = toolLoopRunawayGuard.observe(observation);',
      '\t\t\t\tif (runawayVerdict.shouldAbort) {',
      '\t\t\t\t\tpostCompactionAbortError ??= ToolLoopRunawayAbortError.fromVerdict(runawayVerdict);',
      '\t\t\t\t\tlaneTaskAbortController.abort(postCompactionAbortError);',
      '\t\t\t\t\tpostCompactionAbortController?.abort(postCompactionAbortError);',
      '\t\t\t\t}'),
  },
];

const countOf = (haystack, needle) => {
  let n = 0, i = 0;
  for (;;) { const at = haystack.indexOf(needle, i); if (at < 0) break; n += 1; i = at + 1; }
  return n;
};

const cache = new Map();
const readFile = (f) => {
  if (!cache.has(f)) cache.set(f, readFileSync(join(distDir, f), "utf8"));
  return cache.get(f);
};

const selected = HUNKS.filter((h) => groupFilter === "all" || h.group === groupFilter);
const results = [];
let hardFail = false;

// Detection is marker-based, not find-based: several replacements legitimately still contain
// their own anchor, so "anchor still present" does NOT mean "not applied". The marker is a
// string that exists ONLY in patched output.
for (const h of selected) {
  let text;
  try { text = readFile(h.file); }
  catch (err) { results.push({ id: h.id, state: "FILEMISSING", what: h.what, file: h.file }); hardFail = true; continue; }
  const nMarker = countOf(text, h.marker);
  const nFind = countOf(text, h.find);
  const nRepl = countOf(text, h.repl);
  const from = revert ? h.repl : h.find;
  const to   = revert ? h.find : h.repl;
  let state;
  if (nMarker > 1) { state = "AMBIGUOUS"; hardFail = true; }
  else if (revert) {
    if (nMarker === 0) state = "DONE";
    else if (nRepl === 1) state = "TODO";
    else { state = "AMBIGUOUS"; hardFail = true; }
  } else if (nMarker === 1) {
    state = "DONE";
  } else if (nFind === 1) {
    state = "TODO";
  } else if (nFind === 0) {
    state = "UPSTREAM_CHANGED"; hardFail = true;
  } else {
    state = "AMBIGUOUS"; hardFail = true;
  }
  results.push({ id: h.id, state, what: h.what, file: h.file, from, to });
}

const todo = results.filter((r) => r.state === "TODO");
const done = results.filter((r) => r.state === "DONE");

const emit = (o) => process.stdout.write(JSON.stringify(o) + "\n");

if (hardFail) {
  emit({ verdict: "HARDFAIL", results: results.map(({ id, state, what, file }) => ({ id, state, what, file })) });
  process.exit(4);
}

if (mode === "check") {
  emit({
    verdict: todo.length === 0 ? "APPLIED" : (done.length === 0 ? "ABSENT" : "PARTIAL"),
    applied: done.map((r) => r.id), pending: todo.map((r) => r.id),
    results: results.map(({ id, state, what, file }) => ({ id, state, what, file })),
  });
  process.exit(todo.length === 0 ? 0 : 3);
}

// apply: group edits per file, write atomically, preserve mode
const byFile = new Map();
for (const r of todo) {
  if (!byFile.has(r.file)) byFile.set(r.file, readFile(r.file));
  let text = byFile.get(r.file);
  if (countOf(text, r.from) !== 1) {
    emit({ verdict: "HARDFAIL", reason: "anchor no longer unique mid-apply", id: r.id });
    process.exit(4);
  }
  byFile.set(r.file, text.replace(r.from, r.to));
}

const written = [];
for (const [file, text] of byFile.entries()) {
  const full = join(distDir, file);
  const mode0 = statSync(full).mode & 0o777;
  const tmp = `${full}.ocloop-tmp-${process.pid}`;
  writeFileSync(tmp, text, { encoding: "utf8", mode: mode0 });
  chmodSync(tmp, mode0);
  renameSync(tmp, full);
  written.push(file);
}

emit({ verdict: "APPLIED", changed: todo.map((r) => r.id), files: written });
process.exit(0);
NODEEOF

PATCH_JSON="$("${NODE_BIN}" "${PATCHER_MJS}" "${DIST_DIR}" check all 2>&1)"
PATCH_RC=$?

patch_field() { printf '%s' "${PATCH_JSON}" | "${NODE_BIN}" -e '
let s="";process.stdin.on("data",d=>s+=d).on("end",()=>{try{const o=JSON.parse(s.trim().split("\n").pop());process.stdout.write(String(o[process.argv[1]]??""));}catch(e){process.stdout.write("");}});' "$1"; }

PATCH_VERDICT="$(patch_field verdict)"

case "${PATCH_VERDICT}" in
  APPLIED)
    ok "runaway-abort patch present and complete (hunks: $(patch_field applied))"
    ;;
  ABSENT|PARTIAL)
    if [ "${PATCH_VERDICT}" = "PARTIAL" ]; then
      drift "runaway-abort patch is PARTIALLY applied (applied: $(patch_field applied) / pending: $(patch_field pending))"
    else
      drift "runaway-abort patch is ABSENT - a runaway tool loop will NOT be aborted"
    fi
    if [ "${MODE}" = "apply" ]; then
      bk1="$(backup_file "${DIST_DIR}/tool-loop-detection-QRwz_WH8.js")" || { fail "backup failed for tool-loop-detection - refusing to patch"; }
      bk2="$(backup_file "${DIST_DIR}/embedded-agent-DGUuxGR2.js")"      || { fail "backup failed for embedded-agent - refusing to patch"; }
      if [ -n "${bk1}" ] && [ -n "${bk2}" ]; then
        info "backups: ${BACKUP_ROOT}"
        APPLY_JSON="$("${NODE_BIN}" "${PATCHER_MJS}" "${DIST_DIR}" apply all 2>&1)"
        if [ $? -eq 0 ]; then
          for f in tool-loop-detection-QRwz_WH8.js embedded-agent-DGUuxGR2.js; do
            if ! "${NODE_BIN}" --check "${DIST_DIR}/${f}" >/dev/null 2>&1; then
              fail "PATCHED FILE FAILS SYNTAX CHECK: ${f} - restore from ${BACKUP_ROOT} immediately"
            fi
          done
          fixed "runaway-abort patch applied"
          RESTART_NEEDED=1
        else
          fail "patch apply failed - dist left untouched or restore from ${BACKUP_ROOT}"
        fi
      fi
    fi
    ;;
  HARDFAIL)
    fail "runaway-abort patch anchors NOT FOUND in this OpenClaw build - upstream code changed."
    info "Refusing to guess. Re-derive the patch against this build before trusting loop protection."
    info "Per-hunk state: $(printf '%s' "${PATCH_JSON}" | /usr/bin/tr -d '\n' | /usr/bin/sed 's/.*"results"://')"
    ;;
  *)
    fail "patch checker produced no usable verdict (rc=${PATCH_RC}) - treat loop protection as UNDETERMINED"
    ;;
esac

# ============================================================================
# 2. Telegram spooled-handler timeout in the gateway service-env
# ============================================================================
section "2. Telegram spooled-handler turn timeout (service-env)"

ENV_KEY="OPENCLAW_TELEGRAM_SPOOLED_HANDLER_TIMEOUT_MS"
ENV_WANT="1800000"

if [ ! -f "${ENV_FILE}" ]; then
  drift "service-env file not present: \$HOME/.openclaw/service-env/ai.openclaw.gateway.env"
  info "Nothing to repair - the gateway has not generated it yet."
else
  # Extracts ONLY this key's digits. No other byte of this secret-bearing file is ever read out.
  ENV_VAL="$(/usr/bin/grep -o "${ENV_KEY}=['\"]\{0,1\}[0-9]*" "${ENV_FILE}" 2>/dev/null | /usr/bin/grep -o '[0-9]*$' | /usr/bin/tail -1)"
  ENV_GREP_RC=$?
  if [ "${ENV_GREP_RC}" -ge 2 ]; then
    fail "could not read service-env file (grep error rc=${ENV_GREP_RC}) - value UNDETERMINED"
  elif [ "${ENV_VAL}" = "${ENV_WANT}" ]; then
    ok "${ENV_KEY}=${ENV_WANT} (non-secret numeric)"
  else
    if [ -z "${ENV_VAL}" ]; then
      drift "${ENV_KEY} is MISSING - Telegram turns over 5 minutes will be killed and their text nulled"
    else
      drift "${ENV_KEY} is set to a different value than ${ENV_WANT}"
    fi
    if [ "${MODE}" = "apply" ]; then
      bk="$(backup_file "${ENV_FILE}")"
      if [ -z "${bk}" ]; then
        fail "backup of service-env failed - refusing to edit a secret-bearing file"
      else
        # Atomic, value-blind rewrite: only the one line is touched, nothing is printed.
        if "${NODE_BIN}" -e '
const fs=require("fs"),p=process.argv[1],k=process.argv[2],v=process.argv[3];
const st=fs.statSync(p);const src=fs.readFileSync(p,"utf8");
const re=new RegExp("^"+k+"=.*$","m");
const line=k+"='"'"'"+v+"'"'"'";
const out=re.test(src)?src.replace(re,line):(src.endsWith("\n")?src+line+"\n":src+"\n"+line+"\n");
const tmp=p+".ocloop-tmp-"+process.pid;
fs.writeFileSync(tmp,out,{encoding:"utf8",mode:st.mode&0o777});
fs.chmodSync(tmp,st.mode&0o777);fs.renameSync(tmp,p);
' "${ENV_FILE}" "${ENV_KEY}" "${ENV_WANT}" >/dev/null 2>&1; then
          fixed "${ENV_KEY} set to ${ENV_WANT} (backup: ${bk})"
          RESTART_NEEDED=1
        else
          fail "failed to write service-env - original preserved, backup at ${bk}"
        fi
      fi
    fi
  fi
fi

# ============================================================================
# 3-5. Memory-flush journaling
# ============================================================================
section "3-5. Pre-compaction memory flush (journaling)"

MF="agents.defaults.compaction.memoryFlush"

MF_ENABLED="$(cfg_get "${MF}.enabled")"
if [ "${MF_ENABLED}" = "true" ]; then
  ok "${MF}.enabled = true"
elif [ -z "${MF_ENABLED}" ]; then
  drift "${MF}.enabled is unset (OpenClaw default applies)"
  if [ "${MODE}" = "apply" ]; then
    if cfg_set_json "${MF}.enabled" true; then fixed "${MF}.enabled = true"; else fail "could not set ${MF}.enabled"; fi
  fi
else
  fail "${MF}.enabled = ${MF_ENABLED} - JOURNALING IS OFF. This must never be false."
  if [ "${MODE}" = "apply" ]; then
    if cfg_set_json "${MF}.enabled" true; then fixed "${MF}.enabled restored to true"; else fail "could not restore ${MF}.enabled"; fi
  fi
fi

MF_BYTES="$(cfg_get "${MF}.forceFlushTranscriptBytes")"
if [ "${MF_BYTES}" = "0" ]; then
  ok "${MF}.forceFlushTranscriptBytes = 0"
else
  drift "${MF}.forceFlushTranscriptBytes = ${MF_BYTES:-<unset>} (want 0)"
  if [ "${MODE}" = "apply" ]; then
    if cfg_set_json "${MF}.forceFlushTranscriptBytes" 0; then fixed "${MF}.forceFlushTranscriptBytes = 0"; else fail "could not set ${MF}.forceFlushTranscriptBytes"; fi
  fi
fi

# Prompt content check. The prompt is matched against fixed substrings and is NEVER printed.
# The three hint strings must be byte-exact: OpenClaw appends its own copy on any mismatch,
# which re-introduces the read/no-read contradiction that caused the original stuck session.
MF_PROMPT="$(cfg_get "${MF}.prompt")"
if [ -z "${MF_PROMPT}" ]; then
  drift "${MF}.prompt is unset - cannot verify anti-read directive or safety hints"
else
  H_ANTIREAD='HOW TO APPEND: do NOT read the target file first.'
  H1='Store durable memories only in memory/YYYY-MM-DD.md (create memory/ if needed).'
  H2='If memory/YYYY-MM-DD.md already exists, APPEND new content only and do not overwrite existing entries.'
  H3='Treat workspace bootstrap/reference files such as MEMORY.md, DREAMS.md, SOUL.md, TOOLS.md, and AGENTS.md as read-only during this flush; never overwrite, replace, or edit them.'
  MISSING=""
  case "${MF_PROMPT}" in *"${H_ANTIREAD}"*) : ;; *) MISSING="${MISSING} anti-read-directive" ;; esac
  case "${MF_PROMPT}" in *"${H1}"*) : ;; *) MISSING="${MISSING} hint1-target" ;; esac
  case "${MF_PROMPT}" in *"${H2}"*) : ;; *) MISSING="${MISSING} hint2-append-only" ;; esac
  case "${MF_PROMPT}" in *"${H3}"*) : ;; *) MISSING="${MISSING} hint3-read-only" ;; esac
  if [ -z "${MISSING}" ]; then
    ok "${MF}.prompt contains the anti-read directive and all 3 byte-exact safety hints"
  else
    fail "${MF}.prompt DRIFTED - missing:${MISSING}"
    info "OpenClaw re-appends any hint it cannot find verbatim, which restores the read/no-read"
    info "contradiction. Fix the prompt by hand - this script will not rewrite prompt text."
    manual "Repair ${MF}.prompt so it contains the anti-read directive and all 3 verbatim hints."
  fi
fi
unset MF_PROMPT

# ============================================================================
# 6. Loop-detection thresholds + no per-agent override
# ============================================================================
section "6. Loop-detection thresholds"

check_num() {
  local path="$1" want="$2" got
  got="$(cfg_get "${path}")"
  if [ "${got}" = "${want}" ]; then
    ok "${path} = ${want}"
  else
    drift "${path} = ${got:-<unset>} (want ${want})"
    if [ "${MODE}" = "apply" ]; then
      if cfg_set_json "${path}" "${want}"; then fixed "${path} = ${want}"; else fail "could not set ${path}"; fi
    fi
  fi
}

check_num tools.loopDetection.enabled true
check_num tools.loopDetection.warningThreshold 2
check_num tools.loopDetection.criticalThreshold 3
check_num tools.loopDetection.globalCircuitBreakerThreshold 6
check_num tools.loopDetection.unknownToolThreshold 3
check_num tools.loopDetection.postCompactionGuard.windowSize 2

# A per-agent override silently beats the global block: agent config is merged OVER global.
OVERRIDE_FOUND=0
if cfg_has agents.main.tools.loopDetection; then
  fail "agents.main.tools.loopDetection EXISTS - it silently overrides the global thresholds"
  OVERRIDE_FOUND=1
fi
if "${OC_BIN}" config get agents.list 2>/dev/null | "${NODE_BIN}" -e '
let s="";process.stdin.on("data",d=>s+=d).on("end",()=>{
  let a;try{a=JSON.parse(s);}catch(e){process.exit(0);}
  if(!Array.isArray(a))process.exit(0);
  const hit=a.some((e)=>e&&e.id==="main"&&e.tools&&e.tools.loopDetection);
  process.exit(hit?1:0);});' ; then
  ok "no per-agent loopDetection override on the main agent"
else
  if [ "$?" = "1" ]; then
    fail "agents.list[id=main].tools.loopDetection EXISTS - it silently overrides the global thresholds"
    OVERRIDE_FOUND=1
  fi
fi
if [ "${OVERRIDE_FOUND}" = "1" ]; then
  info "Remove it so the global thresholds govern:"
  manual "openclaw config unset agents.main.tools.loopDetection   (and/or the agents.list entry)"
fi

# ============================================================================
# 7. Daily memory stub guard
# ============================================================================
section "7. Daily memory-file stub guard"

STUB_MARKER="ensure-daily-memory-stub.sh"
if [ -f "${STUB_SCRIPT}" ]; then
  if [ -x "${STUB_SCRIPT}" ]; then
    ok "stub script present and executable"
  else
    drift "stub script present but NOT executable"
    if [ "${MODE}" = "apply" ]; then
      if chmod +x "${STUB_SCRIPT}"; then fixed "stub script made executable"; else fail "chmod failed on stub script"; fi
    fi
  fi
else
  fail "stub script MISSING: \$HOME/.openclaw/scripts/${STUB_MARKER}"
  info "Without it an empty memory/<date>.md can restart the read loop this stack exists to stop."
  manual "Restore \$HOME/.openclaw/scripts/${STUB_MARKER} from the onboarding repo."
fi

CRON_LIST="$(crontab -l 2>/dev/null)"; CRON_RC=$?
if [ "${CRON_RC}" -gt 1 ]; then
  fail "crontab could not be read (rc=${CRON_RC}) - cron registration UNDETERMINED"
elif printf '%s\n' "${CRON_LIST}" | /usr/bin/grep -q "${STUB_MARKER}"; then
  if printf '%s\n' "${CRON_LIST}" | /usr/bin/grep "${STUB_MARKER}" | /usr/bin/grep -q '^\*/5 '; then
    ok "cron registered at */5 * * * *"
  else
    drift "cron registered but not on the */5 schedule"
    manual "Adjust the ${STUB_MARKER} crontab entry to '*/5 * * * *'."
  fi
else
  drift "cron entry for ${STUB_MARKER} is NOT registered"
  if [ "${MODE}" = "apply" ] && [ -x "${STUB_SCRIPT}" ]; then
    NEWCRON="$(printf '%s\n%s\n' "${CRON_LIST}" "*/5 * * * * /bin/bash ${STUB_SCRIPT} >/dev/null 2>&1  # OpenClaw daily memory-file stub guard")"
    if printf '%s\n' "${NEWCRON}" | /usr/bin/grep -v '^$' | crontab - ; then
      fixed "cron entry registered at */5 * * * *"
    else
      fail "failed to register cron entry - crontab left unchanged"
    fi
  fi
fi

# ============================================================================
# 8. ceo-routing-doctrine plugin
# ============================================================================
section "8. ceo-routing-doctrine plugin"

PLUG="ceo-routing-doctrine"
PLUG_DIST="${EXT_DIR}/${PLUG}/dist/index.js"

if [ -f "${PLUG_DIST}" ]; then
  ok "plugin build present at \$HOME/.openclaw/extensions/${PLUG}/dist/index.js"
else
  fail "plugin build MISSING at \$HOME/.openclaw/extensions/${PLUG}/dist/index.js"
  info "Config alone cannot load it. This script will not fabricate a plugin build."
  manual "Restore/rebuild the ${PLUG} plugin, then re-run this script."
fi

if "${OC_BIN}" config get plugins.load.paths 2>/dev/null | /usr/bin/grep -q "/.openclaw/extensions"; then
  ok "plugins.load.paths includes the extensions directory"
else
  drift "plugins.load.paths does NOT include \$HOME/.openclaw/extensions"
  if [ "${MODE}" = "apply" ]; then
    if cfg_set_json plugins.load.paths "[\"${EXT_DIR}\"]"; then fixed "plugins.load.paths set"; else fail "could not set plugins.load.paths"; fi
  fi
fi

# origin:"config" plugins are stripped by a roll - allow-list membership is the fragile part.
if "${OC_BIN}" config get plugins.allow 2>/dev/null | /usr/bin/grep -q "\"${PLUG}\""; then
  ok "${PLUG} is present in plugins.allow"
else
  drift "${PLUG} is NOT in plugins.allow - it will not load"
  if [ "${MODE}" = "apply" ]; then
    # mktemp, never a predictable /tmp/<name>.$$ — a PID-named path in a
    # world-writable directory is a symlink-clobber target, and this value is fed
    # straight back into `openclaw config set`.
    ALLOW_TMP="$(/usr/bin/mktemp -t ocloop-allow.XXXXXX)" || ALLOW_TMP=""
    if [ -z "${ALLOW_TMP}" ]; then
      fail "mktemp failed - cannot safely stage the plugins.allow update"
    elif "${OC_BIN}" config get plugins.allow 2>/dev/null | "${NODE_BIN}" -e '
let s="";process.stdin.on("data",d=>s+=d).on("end",()=>{
  let a;try{a=JSON.parse(s);}catch(e){a=[];}
  if(!Array.isArray(a))a=[];
  if(!a.includes(process.argv[1]))a.push(process.argv[1]);
  a.sort();process.stdout.write(JSON.stringify(a));});' "${PLUG}" > "${ALLOW_TMP}" 2>/dev/null \
      && cfg_set_json plugins.allow "$(/bin/cat "${ALLOW_TMP}")"; then
      fixed "${PLUG} added to plugins.allow"
    else
      fail "could not add ${PLUG} to plugins.allow"
    fi
    rm -f "${ALLOW_TMP}"
  fi
fi

PLUG_ENABLED="$(cfg_get "plugins.entries.${PLUG}.enabled")"
if [ "${PLUG_ENABLED}" = "true" ]; then
  ok "plugins.entries.${PLUG}.enabled = true"
else
  drift "plugins.entries.${PLUG}.enabled = ${PLUG_ENABLED:-<unset>} (want true)"
  if [ "${MODE}" = "apply" ]; then
    if cfg_set_json "plugins.entries.${PLUG}.enabled" true; then fixed "plugin enabled"; else fail "could not enable plugin"; fi
  fi
fi

PLUG_INJECT="$(cfg_get "plugins.entries.${PLUG}.hooks.allowPromptInjection")"
if [ "${PLUG_INJECT}" = "true" ]; then
  ok "plugins.entries.${PLUG}.hooks.allowPromptInjection = true"
else
  drift "plugins.entries.${PLUG}.hooks.allowPromptInjection = ${PLUG_INJECT:-<unset>} (want true)"
  if [ "${MODE}" = "apply" ]; then
    if cfg_set_json "plugins.entries.${PLUG}.hooks.allowPromptInjection" true; then fixed "allowPromptInjection = true"; else fail "could not set allowPromptInjection"; fi
  fi
fi

# ============================================================================
# 9. CEO intent gate must stay dead
# ============================================================================
section "9. CEO intent gate absent (ordered dead)"

GATE_HITS=0
for f in ceo-intent-gate.sh lib-ceo-consent.sh; do
  if [ -e "${HOOKS_DIR}/${f}" ]; then
    fail "resurrected gate file present: \$HOME/.openclaw/hooks/${f}"
    GATE_HITS=$((GATE_HITS+1))
    if [ "${MODE}" = "apply" ]; then
      mkdir -p "${QUARANTINE_DIR}"
      if mv "${HOOKS_DIR}/${f}" "${QUARANTINE_DIR}/${f}"; then
        fixed "moved ${f} to quarantine (not deleted): ${QUARANTINE_DIR}"
      else
        fail "could not quarantine ${f}"
      fi
    fi
  fi
done
[ "${GATE_HITS}" = "0" ] && ok "no ceo-intent-gate.sh / lib-ceo-consent.sh in \$HOME/.openclaw/hooks"

if [ -f "${CLAUDE_SETTINGS}" ]; then
  if /usr/bin/grep -q "ceo-intent-gate" "${CLAUDE_SETTINGS}" 2>/dev/null; then
    fail "ceo-intent-gate referenced in \$HOME/.claude/settings.json (PreToolUse) - it is ordered dead"
    manual "Remove the ceo-intent-gate PreToolUse hook from \$HOME/.claude/settings.json by hand."
  else
    SETTINGS_LINES="$(/usr/bin/grep -c "" "${CLAUDE_SETTINGS}" 2>/dev/null)"
    if [ "${SETTINGS_LINES:-0}" -gt 0 ]; then
      ok "no ceo-intent-gate hook in \$HOME/.claude/settings.json (${SETTINGS_LINES} lines scanned)"
    else
      fail "\$HOME/.claude/settings.json unreadable or empty - gate absence UNDETERMINED"
    fi
  fi
else
  ok "no \$HOME/.claude/settings.json present (nothing can register the gate there)"
fi

# The gate's signature effect was denying the write tool to the routing agent. An explicit
# tools.allow list that omits "write" denies it just as effectively as a deny entry, so both
# shapes are checked. Never auto-changed: an agent's tool grants are the operator's call.
# mktemp, never a predictable /tmp/<name>.$$ (symlink-clobber target).
WRITE_TMP="$(/usr/bin/mktemp -t ocloop-write.XXXXXX)" || WRITE_TMP="/dev/null"
"${OC_BIN}" config get agents.list 2>/dev/null | "${NODE_BIN}" -e '
let s="";process.stdin.on("data",d=>s+=d).on("end",()=>{
  let a;try{a=JSON.parse(s);}catch(e){process.stdout.write("UNREADABLE");return;}
  if(!Array.isArray(a)){process.stdout.write("UNREADABLE");return;}
  const m=a.find((e)=>e&&e.id==="main");
  if(!m){process.stdout.write("NOMAIN");return;}
  const t=m.tools||{};
  const deny=Array.isArray(t.deny)?t.deny:[];
  const allow=Array.isArray(t.allow)?t.allow:null;
  if(deny.some((d)=>d==="write"||d==="*")){process.stdout.write("DENIED");return;}
  if(allow&&allow.length&&!allow.includes("write")&&!allow.includes("*")){process.stdout.write("NOTALLOWED");return;}
  process.stdout.write("OK");});' > "${WRITE_TMP}" 2>/dev/null
WRITE_STATE="$(/bin/cat "${WRITE_TMP}" 2>/dev/null)"; rm -f "${WRITE_TMP}"
case "${WRITE_STATE}" in
  OK)         ok "main agent can use the write tool (no deny, not excluded by an allow-list)" ;;
  DENIED)     fail "main agent has an explicit deny on the write tool - this is the CEO-gate failure shape"
              manual "Remove the write deny from the main agent's tools.deny." ;;
  NOTALLOWED) drift "main agent has a tools.allow list that OMITS \"write\" - it cannot write its memory file."
              info "This reproduces the CEO-gate failure shape without any gate file: the flush prompt"
              info "orders a write the agent has no tool for, so the turn loops. Operator decision -"
              info "this script will not change an agent's tool grants."
              manual "Add \"write\" to the main agent's tools.allow, or drop the allow-list." ;;
  NOMAIN)     drift "no agent with id \"main\" found - write-tool check skipped" ;;
  *)          fail "could not read agents.list - write-tool state UNDETERMINED" ;;
esac

# ============================================================================
# summary
# ============================================================================
printf '\n================================================================\n'
printf ' RESULT:  %s passed   %s drifted   %s failed   %s fixed\n' "${PASS_N}" "${DRIFT_N}" "${FAIL_N}" "${FIXED_N}"
printf '================================================================\n'

if [ "${#MANUAL_ACTIONS[@]}" -gt 0 ]; then
  printf '\nNEEDS A HUMAN:\n'
  for m in "${MANUAL_ACTIONS[@]}"; do printf '  - %s\n' "${m}"; done
fi

if [ "${RESTART_NEEDED}" = "1" ]; then
  printf '\n*** GATEWAY RESTART REQUIRED ***\n'
  printf 'A dist patch and/or a service-env value changed. A running gateway keeps the OLD code\n'
  printf 'and the OLD environment until it is restarted. This script NEVER restarts the gateway.\n'
  printf 'Restart it yourself when the box is idle.\n'
fi

if [ "${FAIL_N}" -gt 0 ]; then
  printf '\nVERDICT: HARD FAIL - loop protection is not trustworthy right now.\n'
  exit 4
fi
if [ "${DRIFT_N}" -gt 0 ]; then
  if [ "${MODE}" = "apply" ] && [ "${DRIFT_N}" -le "${FIXED_N}" ]; then
    printf '\nVERDICT: all drift repaired.\n'
    exit 0
  fi
  printf '\nVERDICT: DRIFT FOUND'
  [ "${MODE}" = "check" ] && printf ' - re-run with --apply to repair what is repairable.\n' || printf ' - some items still need attention.\n'
  exit 3
fi
printf '\nVERDICT: ALL CLEAR - loop protection is fully in place.\n'
exit 0
