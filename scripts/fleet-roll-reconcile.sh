#!/usr/bin/env bash
# fleet-roll-reconcile.sh — v1.0.0
#
# PURPOSE
#   A fleet sweep only succeeds for the boxes it actually reached. This
#   script is the append-only bookkeeping layer that makes "reached" and
#   "not reached" durable, queryable, and impossible to quietly forget.
#
# EVIDENCE THIS CLOSES
#   A fleet sweep applied a provider-timeout fix across ~33 boxes. Two boxes
#   were recorded "Unreachable (pre-existing)" and silently excluded from the
#   sweep's own success reporting. Three days later one of those two boxes
#   was found still broken with exactly that fault class — nothing had ever
#   surfaced it, because nothing outside that one sweep run's transient
#   console output ever recorded it as owed. Separately, that same class of
#   sweep suffered a partition bug that left 24 boxes completely unswept
#   while the sweep still reported overall success. Both failures share one
#   root cause: a sweep's reach is not persisted, is not reconciled against
#   what it was SUPPOSED to attempt, and nothing forces the next sweep to
#   deal with what the last one missed.
#
# BEHAVIOR
#   --record            Append one sweep's result to the ledger: sweep id,
#                        ISO timestamp, the change applied, and the boxes
#                        ATTEMPTED / REACHED / NOT-REACHED (each not-reached
#                        box carries a reason). REFUSES to write (exit 1) if
#                        --attempted is given and does not exactly equal
#                        reached UNION not-reached, or if any box is listed
#                        as both reached and not-reached — that mismatch IS
#                        the partition bug from the incident, caught before
#                        it can repeat.
#   --drain              Print the outstanding not-reached boxes across every
#                        prior sweep in the ledger (a box last recorded
#                        REACHED in a later sweep is no longer outstanding).
#                        Designed to be the FIRST action of the next sweep.
#                        Exits non-zero when the outstanding list is
#                        non-empty, so a roll cannot quietly proceed while
#                        boxes are still owed a fix.
#   --verify-drift <expected-state-file>
#                        Compare EVERY box named in the expected-state file
#                        against its most recently recorded ledger state,
#                        REGARDLESS of whether that box participated in the
#                        sweep being checked. A box with no ledger record at
#                        all, or whose last record is not-reached, is
#                        reported UNDETERMINED — never treated as compliant
#                        just because it was left out of the sweep that
#                        mattered.
#   --self-test          Exercises all three modes against a throwaway temp
#                        ledger (never the real ledger, never committed).
#
# DATA MODEL — a box that was not reached can never be recorded as clean
#   Every not-reached ledger entry is built by the embedded Python below with
#   a HARDCODED status of "UNDETERMINED". There is no CLI flag, field, or
#   code path that lets a caller set a not-reached box's status to anything
#   else (in particular, never "PASS" or "REACHED") — the per-box dict is a
#   Python literal, not populated from caller input for that field. See the
#   `record` heredoc below.
#
# LEDGER
#   Append-only JSON Lines — one compact JSON object per line, never
#   rewritten, never truncated. Default path is platform-detected
#   ($OC_ROOT/fleet-roll-reconcile-ledger.jsonl); override with
#   --ledger <path> or FLEET_ROLL_RECONCILE_LEDGER. The ledger is written at
#   RUNTIME ONLY — nothing under this repo ever ships a ledger file, and this
#   script never writes anywhere inside the repo it lives in.
#
# EXIT CODES
#   Global (any mode):
#     0   success — see per-mode meaning below
#     3   MISUSE — bad invocation (unknown mode/flag, missing required value)
#     4   ENVIRONMENT — python3 not on PATH, malformed input file, unreadable
#         expected-state file
#   --record:
#     0   sweep appended to the ledger
#     1   REFUSED — --attempted did not equal reached UNION not-reached
#         (the partition bug), or a box was listed as both reached and
#         not-reached. Nothing was written to the ledger.
#   --drain:
#     0   zero outstanding not-reached boxes
#     2   one or more boxes are still outstanding (printed to stdout)
#   --verify-drift:
#     0   every named box verified REACHED with the matching change
#     1   one or more boxes are DRIFT or UNDETERMINED
#   --self-test:
#     0   every embedded fixture assertion passed
#     1   an embedded fixture assertion failed
#
# USAGE
#   bash scripts/fleet-roll-reconcile.sh --record --sweep-id <id> \
#        --change "<description>" \
#        [--reached BOX]... [--not-reached "BOX=reason"]... \
#        [--attempted BOX]... [--ledger <path>]
#
#   bash scripts/fleet-roll-reconcile.sh --drain [--ledger <path>] [--json]
#
#   bash scripts/fleet-roll-reconcile.sh --verify-drift expected.json \
#        [--ledger <path>] [--json]
#     expected.json shape:
#       {"expected_change": "provider-timeout-fix-v2",
#        "boxes": ["box-01", "box-02", "box-03"]}
#
#   bash scripts/fleet-roll-reconcile.sh --self-test
#
# NO CLIENT NAMES: this script and every ledger entry it writes are
# box-identifier only ("box-01", an ssh alias, etc.) — never a client's name.

set -uo pipefail

TAG="[fleet-roll-reconcile]"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT_PATH="$SCRIPT_DIR/$(basename "${BASH_SOURCE[0]}")"

usage() {
  sed -n '2,90p' "${BASH_SOURCE[0]}"
}

_die_misuse() { echo "$TAG MISUSE: $1" >&2; exit 3; }
_die_env()    { echo "$TAG ENVIRONMENT: $1" >&2; exit 4; }

# ─── platform-detected default ledger path (VPS /data first, Mac fallback) ───
if [ -d /data/.openclaw ]; then
  OC_ROOT=/data/.openclaw
elif [ -d "$HOME/.openclaw" ]; then
  OC_ROOT="$HOME/.openclaw"
else
  OC_ROOT="$HOME/.openclaw"
fi
DEFAULT_LEDGER="${FLEET_ROLL_RECONCILE_LEDGER:-$OC_ROOT/fleet-roll-reconcile-ledger.jsonl}"

# ═══════════════════════════════════════════════════════════════════════════
# record_sweep — append one sweep result to the ledger via embedded Python.
# The per-box "status" for not-reached boxes is a Python literal string
# ("UNDETERMINED") — it is never read from argv, so this mode structurally
# cannot record a not-reached box as clean.
# ═══════════════════════════════════════════════════════════════════════════
record_sweep() {
  local ledger="$1" sweep_id="$2" change="$3"
  shift 3
  # remaining "$@" = PY_ARGS sections (sentinel-delimited), built by caller
  python3 - "$ledger" "$sweep_id" "$change" "$@" <<'PYEOF'
import sys, json, os, datetime

def main():
    args = sys.argv[1:]
    ledger_path, sweep_id, change = args[0], args[1], args[2]
    rest = args[3:]

    sections = {"@@ATTEMPTED@@": [], "@@REACHED@@": [], "@@NOTREACHED@@": []}
    current = None
    for tok in rest:
        if tok in sections:
            current = tok
            continue
        if current is None:
            print("record: malformed argv — value before any section marker: %r" % tok, file=sys.stderr)
            sys.exit(4)
        sections[current].append(tok)

    attempted_in = sections["@@ATTEMPTED@@"]
    reached = sections["@@REACHED@@"]
    not_reached_raw = sections["@@NOTREACHED@@"]

    not_reached = []
    for item in not_reached_raw:
        if "=" not in item:
            print("record: malformed --not-reached entry (need BOX=reason): %r" % item, file=sys.stderr)
            sys.exit(4)
        box, reason = item.split("=", 1)
        # HARDCODED literal status — never taken from caller input. This is
        # the enforcement point for "a box that was not reached can never be
        # recorded as clean."
        not_reached.append({"box": box, "reason": reason, "status": "UNDETERMINED"})

    reached_set = set(reached)
    not_reached_set = set(item["box"] for item in not_reached)

    overlap = reached_set & not_reached_set
    if overlap:
        print("record: REFUSED — box(es) listed as BOTH reached and not-reached: %s" % ", ".join(sorted(overlap)), file=sys.stderr)
        sys.exit(1)

    derived_attempted = reached_set | not_reached_set

    if attempted_in:
        attempted_set = set(attempted_in)
        missing_from_lists = attempted_set - derived_attempted
        extra_in_lists = derived_attempted - attempted_set
        if missing_from_lists or extra_in_lists:
            print("record: REFUSED — partition mismatch between --attempted and reached+not-reached.", file=sys.stderr)
            if missing_from_lists:
                print("  attempted but recorded in NEITHER reached nor not-reached: %s" % ", ".join(sorted(missing_from_lists)), file=sys.stderr)
            if extra_in_lists:
                print("  recorded reached/not-reached but NOT listed in --attempted: %s" % ", ".join(sorted(extra_in_lists)), file=sys.stderr)
            print("  this is exactly the partition bug from the incident (boxes silently excluded while the sweep still reported success). Nothing was written.", file=sys.stderr)
            sys.exit(1)
        attempted = sorted(attempted_set)
    else:
        attempted = sorted(derived_attempted)

    entry = {
        "sweep_id": sweep_id,
        "ts": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "change": change,
        "attempted": attempted,
        "reached": sorted(reached_set),
        "not_reached": sorted(not_reached, key=lambda d: d["box"]),
    }

    d = os.path.dirname(ledger_path)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(ledger_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, sort_keys=True) + "\n")

    print("record: OK — sweep '%s' appended to %s (attempted=%d reached=%d not_reached=%d)" % (
        sweep_id, ledger_path, len(attempted), len(reached_set), len(not_reached_set)))
    sys.exit(0)

main()
PYEOF
}

# ═══════════════════════════════════════════════════════════════════════════
# drain_ledger — print every box whose MOST RECENT ledger appearance is
# not-reached. A box last recorded REACHED in a later sweep is resolved and
# no longer printed. Exits 2 when the outstanding list is non-empty.
# ═══════════════════════════════════════════════════════════════════════════
drain_ledger() {
  local ledger="$1" json_out="$2"
  python3 - "$ledger" "$json_out" <<'PYEOF'
import sys, json, os

def main():
    ledger_path = sys.argv[1]
    json_out = sys.argv[2] == "1"

    if not os.path.isfile(ledger_path):
        if json_out:
            print(json.dumps([]))
        else:
            print("drain: no ledger at %s yet — nothing outstanding" % ledger_path)
        sys.exit(0)

    status_by_box = {}
    corrupt = 0
    with open(ledger_path, "r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except Exception as e:
                print("drain: WARN — corrupt ledger line %d, skipping: %s" % (lineno, e), file=sys.stderr)
                corrupt += 1
                continue
            sweep_id = entry.get("sweep_id", "?")
            ts = entry.get("ts", "?")
            for box in entry.get("reached", []):
                status_by_box[box] = {"status": "REACHED", "sweep_id": sweep_id, "ts": ts, "reason": None}
            for item in entry.get("not_reached", []):
                box = item.get("box")
                if box is None:
                    continue
                status_by_box[box] = {"status": "UNDETERMINED", "sweep_id": sweep_id, "ts": ts, "reason": item.get("reason", "")}

    outstanding = sorted(
        [(box, info) for box, info in status_by_box.items() if info["status"] == "UNDETERMINED"],
        key=lambda x: x[0],
    )

    if json_out:
        print(json.dumps([dict(box=b, **i) for b, i in outstanding]))
    else:
        if not outstanding:
            suffix = " (%d corrupt line(s) skipped)" % corrupt if corrupt else ""
            print("drain: zero outstanding not-reached boxes" + suffix)
        else:
            print("drain: %d outstanding not-reached box(es) — owed a fix before a new sweep proceeds:" % len(outstanding))
            for box, info in outstanding:
                print("  %s  UNDETERMINED  last not-reached in sweep '%s' at %s  reason: %s" % (
                    box, info["sweep_id"], info["ts"], info["reason"]))
            if corrupt:
                print("drain: WARN — %d corrupt ledger line(s) skipped" % corrupt, file=sys.stderr)

    sys.exit(2 if outstanding else 0)

main()
PYEOF
}

# ═══════════════════════════════════════════════════════════════════════════
# verify_drift — compare every box in the expected-state file against its
# most recent ledger state, regardless of sweep participation. A box absent
# from the ledger, or last recorded not-reached, is UNDETERMINED — never OK.
# ═══════════════════════════════════════════════════════════════════════════
verify_drift() {
  local ledger="$1" expected_file="$2" json_out="$3"
  python3 - "$ledger" "$expected_file" "$json_out" <<'PYEOF'
import sys, json, os

def main():
    ledger_path = sys.argv[1]
    expected_path = sys.argv[2]
    json_out = sys.argv[3] == "1"

    try:
        with open(expected_path, "r", encoding="utf-8") as f:
            expected = json.load(f)
    except Exception as e:
        print("verify-drift: ENVIRONMENT — could not read/parse expected-state file %s: %s" % (expected_path, e), file=sys.stderr)
        sys.exit(4)

    expected_change = expected.get("expected_change")
    boxes = expected.get("boxes")
    if not expected_change or not isinstance(boxes, list) or not boxes:
        print("verify-drift: ENVIRONMENT — expected-state file must have a non-empty 'expected_change' (string) and a non-empty 'boxes' (array)", file=sys.stderr)
        sys.exit(4)

    status_by_box = {}
    if os.path.isfile(ledger_path):
        with open(ledger_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except Exception:
                    continue
                sweep_id = entry.get("sweep_id", "?")
                change = entry.get("change", "?")
                for box in entry.get("reached", []):
                    status_by_box[box] = {"status": "REACHED", "change": change, "sweep_id": sweep_id, "reason": None}
                for item in entry.get("not_reached", []):
                    box = item.get("box")
                    if box is None:
                        continue
                    status_by_box[box] = {"status": "UNDETERMINED", "change": None, "sweep_id": sweep_id, "reason": item.get("reason", "")}

    results = []
    any_bad = False
    for box in boxes:
        rec = status_by_box.get(box)
        if rec is None:
            results.append({"box": box, "verdict": "UNDETERMINED", "detail": "no ledger record for this box"})
            any_bad = True
        elif rec["status"] == "UNDETERMINED":
            results.append({"box": box, "verdict": "UNDETERMINED", "detail": "last recorded state is not-reached (sweep '%s', reason: %s)" % (rec["sweep_id"], rec["reason"])})
            any_bad = True
        elif rec["change"] == expected_change:
            results.append({"box": box, "verdict": "OK", "detail": "reached with matching change '%s' (sweep '%s')" % (expected_change, rec["sweep_id"])})
        else:
            results.append({"box": box, "verdict": "DRIFT", "detail": "last reached with change '%s', expected '%s' (sweep '%s')" % (rec["change"], expected_change, rec["sweep_id"])})
            any_bad = True

    if json_out:
        print(json.dumps(results))
    else:
        for r in results:
            print("  %-24s %-13s %s" % (r["box"], r["verdict"], r["detail"]))
        bad = [r for r in results if r["verdict"] != "OK"]
        if bad:
            print("verify-drift: %d of %d box(es) NOT verified (DRIFT or UNDETERMINED)" % (len(bad), len(results)))
        else:
            print("verify-drift: all %d box(es) verified REACHED with the matching change" % len(results))

    sys.exit(1 if any_bad else 0)

main()
PYEOF
}

# ═══════════════════════════════════════════════════════════════════════════
# self_test — exercises all three modes against a throwaway temp ledger.
# Never touches the real ledger, never writes into the repo.
# ═══════════════════════════════════════════════════════════════════════════
self_test() {
  local tmpdir rc out fails=0
  tmpdir="$(mktemp -d)" || { echo "SELF-TEST FAIL — could not create temp dir" >&2; return 1; }
  trap 'rm -rf "$tmpdir"' RETURN
  local ledger="$tmpdir/ledger.jsonl"

  # 1. record a sweep with 1 reached + 1 not-reached — expect exit 0.
  out="$(bash "$SCRIPT_PATH" --record --sweep-id sweep-1 --change "fix-v1" \
    --reached box-a --not-reached "box-b=ssh timeout" --ledger "$ledger" 2>&1)"
  rc=$?
  if [ "$rc" -ne 0 ]; then
    echo "SELF-TEST FAIL — initial --record expected exit 0, got $rc. Output: $out" >&2
    fails=$((fails + 1))
  else
    echo "SELF-TEST: --record (1 reached, 1 not-reached) exited 0 — correct"
  fi

  if ! grep -q 'UNDETERMINED' "$ledger" 2>/dev/null; then
    echo "SELF-TEST FAIL — ledger entry for box-b does not carry status UNDETERMINED" >&2
    fails=$((fails + 1))
  else
    echo "SELF-TEST: not-reached box recorded with status UNDETERMINED in the ledger — correct"
  fi

  # 2. drain — expect exactly box-b outstanding, exit 2.
  out="$(bash "$SCRIPT_PATH" --drain --ledger "$ledger" 2>&1)"
  rc=$?
  if [ "$rc" -ne 2 ]; then
    echo "SELF-TEST FAIL — --drain with 1 outstanding box expected exit 2, got $rc. Output: $out" >&2
    fails=$((fails + 1))
  elif ! printf '%s' "$out" | grep -q "box-b"; then
    echo "SELF-TEST FAIL — --drain output did not list box-b. Output: $out" >&2
    fails=$((fails + 1))
  else
    echo "SELF-TEST: --drain lists box-b and exits 2 (non-zero) — correct"
  fi

  # 3. a not-reached box can never be recorded as PASS — the ledger must
  #    contain no such status anywhere.
  if grep -q 'PASS' "$ledger" 2>/dev/null; then
    echo "SELF-TEST FAIL — ledger somehow contains a PASS status; the data model must make this impossible" >&2
    fails=$((fails + 1))
  else
    echo "SELF-TEST: ledger contains no PASS status anywhere — a not-reached box cannot be recorded clean — correct"
  fi

  # 4. resolve box-b in a second sweep (reached this time) — drain goes clean.
  out="$(bash "$SCRIPT_PATH" --record --sweep-id sweep-2 --change "fix-v1" \
    --reached box-a --reached box-b --ledger "$ledger" 2>&1)"
  rc=$?
  if [ "$rc" -ne 0 ]; then
    echo "SELF-TEST FAIL — resolving sweep expected exit 0, got $rc. Output: $out" >&2
    fails=$((fails + 1))
  fi

  out="$(bash "$SCRIPT_PATH" --drain --ledger "$ledger" 2>&1)"
  rc=$?
  if [ "$rc" -ne 0 ]; then
    echo "SELF-TEST FAIL — --drain after resolution expected exit 0 (zero outstanding), got $rc. Output: $out" >&2
    fails=$((fails + 1))
  else
    echo "SELF-TEST: --drain exits 0 once every box has since been reached — correct"
  fi

  # 5. partition mismatch is REFUSED (exit 1), nothing appended.
  local lines_before lines_after
  lines_before="$(wc -l < "$ledger" | tr -d ' ')"
  out="$(bash "$SCRIPT_PATH" --record --sweep-id sweep-3 --change "fix-v2" \
    --reached box-a --attempted box-a --attempted box-c --ledger "$ledger" 2>&1)"
  rc=$?
  lines_after="$(wc -l < "$ledger" | tr -d ' ')"
  if [ "$rc" -ne 1 ]; then
    echo "SELF-TEST FAIL — partition-mismatch --record expected exit 1 (REFUSED), got $rc. Output: $out" >&2
    fails=$((fails + 1))
  elif [ "$lines_before" != "$lines_after" ]; then
    echo "SELF-TEST FAIL — a REFUSED record still appended a ledger line ($lines_before -> $lines_after)" >&2
    fails=$((fails + 1))
  else
    echo "SELF-TEST: --record with an attempted/reached partition mismatch is REFUSED (exit 1), ledger untouched — correct"
  fi

  # 6. verify-drift: matching, drift, and undetermined cases.
  printf '{"expected_change":"fix-v1","boxes":["box-a","box-b"]}\n' > "$tmpdir/expected-ok.json"
  out="$(bash "$SCRIPT_PATH" --verify-drift "$tmpdir/expected-ok.json" --ledger "$ledger" 2>&1)"
  rc=$?
  if [ "$rc" -ne 0 ]; then
    echo "SELF-TEST FAIL — verify-drift on matching boxes expected exit 0, got $rc. Output: $out" >&2
    fails=$((fails + 1))
  else
    echo "SELF-TEST: --verify-drift exits 0 when every box matches the expected change — correct"
  fi

  printf '{"expected_change":"fix-v99","boxes":["box-a"]}\n' > "$tmpdir/expected-drift.json"
  out="$(bash "$SCRIPT_PATH" --verify-drift "$tmpdir/expected-drift.json" --ledger "$ledger" 2>&1)"
  rc=$?
  if [ "$rc" -ne 1 ]; then
    echo "SELF-TEST FAIL — verify-drift on a mismatched change expected exit 1 (DRIFT), got $rc. Output: $out" >&2
    fails=$((fails + 1))
  else
    echo "SELF-TEST: --verify-drift exits 1 (DRIFT) when the recorded change does not match — correct"
  fi

  printf '{"expected_change":"fix-v1","boxes":["box-never-swept"]}\n' > "$tmpdir/expected-unknown.json"
  out="$(bash "$SCRIPT_PATH" --verify-drift "$tmpdir/expected-unknown.json" --ledger "$ledger" 2>&1)"
  rc=$?
  if [ "$rc" -ne 1 ] || ! printf '%s' "$out" | grep -q "UNDETERMINED"; then
    echo "SELF-TEST FAIL — verify-drift on a box with no ledger record expected exit 1 with UNDETERMINED, got rc=$rc. Output: $out" >&2
    fails=$((fails + 1))
  else
    echo "SELF-TEST: --verify-drift reports UNDETERMINED (never PASS/OK) for a box absent from the ledger — correct"
  fi

  if [ "$fails" -eq 0 ]; then
    echo "SELF-TEST PASS — all fleet-roll-reconcile.sh fixture assertions passed"
    return 0
  else
    echo "SELF-TEST FAIL — $fails assertion(s) failed" >&2
    return 1
  fi
}

main() {
  local mode="" ledger="$DEFAULT_LEDGER" json_out=0
  local sweep_id="" change="" expected_file=""
  local attempted=() reached=() not_reached=()

  while [ $# -gt 0 ]; do
    case "$1" in
      --record) mode="record"; shift ;;
      --drain) mode="drain"; shift ;;
      --verify-drift)
        mode="verify-drift"
        expected_file="${2:-}"
        [ -z "$expected_file" ] && _die_misuse "--verify-drift requires <expected-state-file>"
        shift 2
        ;;
      --self-test) mode="self-test"; shift ;;
      --sweep-id) sweep_id="${2:-}"; shift 2 ;;
      --change) change="${2:-}"; shift 2 ;;
      --reached)
        [ -z "${2:-}" ] && _die_misuse "--reached requires a box name"
        reached+=("$2"); shift 2 ;;
      --not-reached)
        [ -z "${2:-}" ] && _die_misuse "--not-reached requires BOX=reason"
        case "$2" in *=*) ;; *) _die_misuse "--not-reached value must be BOX=reason (got: $2)" ;; esac
        not_reached+=("$2"); shift 2 ;;
      --attempted)
        [ -z "${2:-}" ] && _die_misuse "--attempted requires a box name"
        attempted+=("$2"); shift 2 ;;
      --ledger)
        ledger="${2:-}"
        [ -z "$ledger" ] && _die_misuse "--ledger requires a path"
        shift 2 ;;
      --json) json_out=1; shift ;;
      --help|-h) usage; exit 0 ;;
      *) _die_misuse "unknown argument: $1" ;;
    esac
  done

  [ -z "$mode" ] && _die_misuse "one of --record, --drain, --verify-drift, --self-test is required"

  if [ "$mode" = "self-test" ]; then
    self_test
    exit $?
  fi

  command -v python3 >/dev/null 2>&1 || _die_env "python3 not found on PATH"

  case "$mode" in
    record)
      [ -z "$sweep_id" ] && _die_misuse "--record requires --sweep-id"
      [ -z "$change" ] && _die_misuse "--record requires --change"
      if [ "${#reached[@]}" -eq 0 ] && [ "${#not_reached[@]}" -eq 0 ]; then
        _die_misuse "--record requires at least one --reached or --not-reached box"
      fi

      local py_args=()
      py_args+=("@@ATTEMPTED@@")
      if [ "${#attempted[@]}" -gt 0 ]; then
        for b in "${attempted[@]}"; do py_args+=("$b"); done
      fi
      py_args+=("@@REACHED@@")
      if [ "${#reached[@]}" -gt 0 ]; then
        for b in "${reached[@]}"; do py_args+=("$b"); done
      fi
      py_args+=("@@NOTREACHED@@")
      if [ "${#not_reached[@]}" -gt 0 ]; then
        for b in "${not_reached[@]}"; do py_args+=("$b"); done
      fi

      record_sweep "$ledger" "$sweep_id" "$change" "${py_args[@]}"
      exit $?
      ;;
    drain)
      drain_ledger "$ledger" "$json_out"
      exit $?
      ;;
    verify-drift)
      verify_drift "$ledger" "$expected_file" "$json_out"
      exit $?
      ;;
  esac
}

main "$@"
