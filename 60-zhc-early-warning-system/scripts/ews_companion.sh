#!/usr/bin/env bash
# =============================================================================
# SKILL 60 - ZHC EARLY WARNING SYSTEM :: ews_companion.sh
# The companion command surface: audit | install | troubleshoot (spec Section 5).
# -----------------------------------------------------------------------------
# It COMMANDS the target box's own tooling; it does not do the box's work from
# afar (fleet command doctrine). Read-only where it says read-only. Never prints a
# secret value. Operator-verbose, client-silent.
#
#   audit [--json]     read-only: baseline-vs-live diff table, config owner/mode,
#                      cron inventory, heartbeat posture, compaction arithmetic,
#                      last-tick recency, snapshot count, ledger health. --json emits
#                      the tiny digest the operator-box aggregator consumes. Exit 0
#                      clean / 4 findings present.
#   install [...]      delegates to install.sh (idempotent; also the upgrade path).
#   troubleshoot       the spec-5.4 decision tree: read-only probes + PRINTED
#                      sanctioned fixes (executed only on the operator's word).
#
# EXIT: 0 clean, 1 error, 2 usage, 4 findings present.
# =============================================================================
set -uo pipefail
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
SKILL_DIR="$(cd "$SELF_DIR/.." && pwd)"
SCRIPTS="$SELF_DIR"
TAG="[ews-companion]"
EX_OK=0; EX_ERR=1; EX_USAGE=2; EX_FINDINGS=4

audit() {
    local as_json=0
    [ "${1:-}" = "--json" ] && as_json=1
    SCRIPTS="$SCRIPTS" AS_JSON="$as_json" python3 - <<'PY'
import json, os, sys, time
sys.path.insert(0, os.environ["SCRIPTS"])
import ews_common as C
import ews_baseline as B
from ews_ledger import Ledger, default_state_dir
as_json = os.environ.get("AS_JSON") == "1"

report = {"ok": True, "findings": 0}
findings = []
try:
    cfg = C.read_config()
except Exception as e:
    cfg = None
    findings.append(("config", "unreadable: %s" % type(e).__name__))

# baseline diff
bp = B.baseline_path()
diffs = []
if bp.is_file() and cfg is not None:
    baseline = json.loads(bp.read_text(encoding="utf-8"))
    diffs = B.compute_diff(baseline, cfg)
    for d in diffs:
        if d["changed"]:
            findings.append((d["path"], "changed:%s%s" % (d["direction"],
                             " DANGEROUS" if d["dangerous"] else "")))
    report["config_owner"] = baseline.get("config_owner")
    report["config_mode"] = baseline.get("config_mode")
    report["baseline_pinned_at"] = baseline.get("pinned_at")
else:
    findings.append(("baseline", "not pinned"))

# compaction arithmetic
if cfg is not None:
    broken, ceil, why = C.subtractive_broken(cfg)
    report["compaction"] = {"broken": broken, "effective_ceiling": ceil, "reason": why}
    if broken:
        findings.append(("compaction", "SUBTRACTIVE MISCONFIG: %s" % why))
    report["cron_inventory"] = [c["name"] for c in C.cron_inventory(cfg)]
    hb = C.dotpath_get(cfg, "agents.defaults.heartbeat")
    report["heartbeat"] = hb if isinstance(hb, dict) else None

# ledger health + last tick + open events by severity
led = Ledger()
try:
    open_ev = led.open_events()
    by_sev, by_class = {}, {}
    last_ts = None
    for e in open_ev:
        by_sev[e["severity"]] = by_sev.get(e["severity"], 0) + 1
        by_class[e["class"] or "?"] = by_class.get(e["class"] or "?", 0) + 1
        if not last_ts or e["tick_ts"] > last_ts:
            last_ts = e["tick_ts"]
    snaps = led.list_snapshots()
    report.update({"box": led.get_meta("box"), "role": led.get_meta("role"),
                   "open_events": len(open_ev), "by_severity": by_sev,
                   "counts": by_class, "snapshots": len(snaps),
                   "last_tick_ts": last_ts, "ledger": str(led.db_path)})
finally:
    led.close()

report["findings"] = len(findings)
report["finding_list"] = [{"key": k, "note": v} for k, v in findings]

if as_json:
    # the tiny digest the aggregator consumes (NO config contents, NO secrets)
    digest = {"box": report.get("box"), "last_tick_ts": report.get("last_tick_ts"),
              "red_flags": len(findings), "by_severity": report.get("by_severity", {}),
              "counts": report.get("counts", {})}
    print(json.dumps(digest, sort_keys=True))
else:
    print("== EWS AUDIT ==")
    print("box=%s role=%s" % (report.get("box"), report.get("role")))
    print("config owner=%s mode=%s (pinned %s)" % (report.get("config_owner"),
          report.get("config_mode"), report.get("baseline_pinned_at")))
    print("compaction: %s" % report.get("compaction"))
    print("cron: %s" % report.get("cron_inventory"))
    print("snapshots: %s   last_tick: %s" % (report.get("snapshots"), report.get("last_tick_ts")))
    print("open events by severity: %s" % report.get("by_severity"))
    if findings:
        print("FINDINGS (%d):" % len(findings))
        for k, v in findings:
            print("  [%s] %s" % (k, v))
    else:
        print("CLEAN: no findings")

sys.exit(4 if findings else 0)
PY
}

troubleshoot() {
    cat <<EOF
$TAG troubleshoot decision tree (spec 5.4). Read-only probes below; the FIXES are
PRINTED and executed ONLY on the operator's word.

1. SENTINEL DARK? Is the tick cron present, and does a manual tick run?
   probe: bash $SKILL_DIR/ews-entry.sh tick --no-send
   fix:   re-register the cron (bash $SKILL_DIR/install.sh) OR recover/rotate the
          ledger; then a gateway send test to the operator account.
2. GATEWAY DOWN? (S7 root cause) - PLATFORM-SANCTIONED restart ONLY:
   Mac: MASTER-only kickstart-then-stop with the launchctl fallback + orphan-port cleanup.
   VPS: docker compose up  (NEVER 'restart' - it skips env_file).
3. CONFIG OWNED BY ROOT? (S6 P1) - chown to the box user, validate, restart per (2).
4. BASELINE DISPUTED? ("that change was intended"):
   bash $SKILL_DIR/ews-entry.sh approve-baseline --key <path>
5. FALSE-POSITIVE SIGNATURE? signatures are DATA - fix via the repo + rollout, NEVER
   hand-edit on a box (a hand-edit trips S9 by design).
6. EVERYTHING ON FIRE? bash $SKILL_DIR/ews-entry.sh revert --to <last-green-utc-ts>
   then escalate on Rescue Rangers with the audit output attached.
EOF
    # read-only probe: is a manual tick healthy?
    echo "$TAG probe: manual tick (no send)..."
    bash "$SKILL_DIR/ews-entry.sh" tick --no-send >/dev/null 2>&1 \
        && echo "$TAG probe OK: sentinel tick runs" \
        || echo "$TAG probe: tick returned findings or errored (see audit)"
    return $EX_OK
}

self_test() {
    echo "$TAG self-test: audit against a sandbox produces a digest + finding count"
    local td; td="$(mktemp -d)"
    export EWS_STATE_DIR="$td/ews" EWS_OPENCLAW_ROOT="$td/oc" EWS_CONFIG_PATH="$td/openclaw.json"
    mkdir -p "$td/oc"
    cat > "$EWS_CONFIG_PATH" <<'JSON'
{ "agents": { "defaults": { "maxConcurrent": 16, "subagents": { "maxConcurrent": 16 },
  "compaction": { "memoryFlush": { "softThresholdTokens": 900000 } } } },
  "_contextWindow": 128000,
  "channels": { "telegram": { "accounts": { "default": { "allowFrom": ["1"] } } } },
  "cron": [] }
JSON
    python3 "$SCRIPTS/ews_ledger.py" init >/dev/null 2>&1
    python3 - <<PY
import sys; sys.path.insert(0, "$SCRIPTS")
from ews_ledger import Ledger
l=Ledger(); l.set_meta("box","selftest-box-example"); l.close()
PY
    # audit should flag the subtractive misconfig (finding) => exit 4
    local out rc
    out="$(audit 2>&1)"; rc=$?
    if [ $rc -eq $EX_FINDINGS ] && printf '%s' "$out" | grep -q "SUBTRACTIVE MISCONFIG"; then
        echo "  audit case: PASS (subtractive misconfig flagged, exit 4)"
    else
        echo "$TAG self-test FAIL: audit did not flag the misconfig (rc=$rc)" >&2
        rm -rf "$td"; return 1
    fi
    # --json emits a digest with a box name and no secret
    local dj
    dj="$(audit --json 2>/dev/null)"
    if printf '%s' "$dj" | python3 -c "import json,sys; d=json.load(sys.stdin); assert d['box']=='selftest-box-example'"; then
        echo "  digest case: PASS (--json digest has the box name, aggregator-ready)"
    else
        echo "$TAG self-test FAIL: --json digest malformed" >&2; rm -rf "$td"; return 1
    fi
    rm -rf "$td"
    unset EWS_STATE_DIR EWS_OPENCLAW_ROOT EWS_CONFIG_PATH
    echo "$TAG self-test: PASS"
    return 0
}

main() {
    case "${1:-}" in
        audit)        shift; audit "$@" ;;
        install)      shift; bash "$SKILL_DIR/install.sh" "$@" ;;
        troubleshoot) shift; troubleshoot "$@" ;;
        --self-test)  self_test ;;
        -h|--help|"") echo "$TAG usage: ews_companion.sh {audit [--json]|install [...]|troubleshoot} | --self-test" ;;
        *) echo "$TAG unknown verb: $1" >&2; exit $EX_USAGE ;;
    esac
}
main "$@"
