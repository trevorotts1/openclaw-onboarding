#!/usr/bin/env bash
# ============================================================================
# report-missing-999.sh   (operator-box tool, READ-ONLY)
#
# Lists the fleet boxes that do NOT have 999-setup installed, for the fleet
# roll report. The roll only ever REFRESHES 999-setup where it already exists
# (shared-utils/fleet_refresh_runner.py: step_update_999 -> "999 not installed"
# skip). This report names those boxes so the skip is visible, not silent.
#
# It installs nothing, writes nothing on any box, and changes no setting.
#
# HOW IT REACHES BOXES
#   The ONLY roster and the ONLY route source is the operator fleet-access tool
#   (~/.claude/tools/fleet-access.sh --all --json). Never ~/.ssh/config, never
#   a hand-kept list. The tool resolves every box and proves reachability;
#   this script reads its verdicts and, for a reachable Mac box that the tool
#   gave a ssh alias for, runs ONE read-only `test -f` probe through that alias.
#   Headless only: BatchMode, no browser login, no cloudflared login.
#
# WHAT "INSTALLED" MEANS
#   Same test as the roll's own step_update_999 (_find_999_checkout): a checkout
#   that carries all three marker files
#       .claude/skills/nine-router-setup/scripts/setup-macos.sh
#       AGENT_INSTALL.md
#       CONTROL/bundled-skills.txt
#   found first by following an installed nine-router-setup skill link back to
#   its repo, then by the known checkout locations. tests/unit/
#   report-missing-999.test.sh fails if these lists drift from the runner's.
#
# HOW IT STAYS HONEST (negative-result contract)
#   MISSING is printed ONLY when the probe ran on a reachable box, returned its
#   own marker line, and found no checkout. A box that is unreachable, refused
#   the connection, printed no marker, or has no per-box shell route in the
#   fleet-access output is UNKNOWN with the reason -- never MISSING. Before any
#   box is probed, the probe is run against a planted fixture checkout (must say
#   INSTALLED) and an empty fixture (must say MISSING); if either answer is wrong
#   the run stops with exit 2 and reports no verdict.
#
# USAGE
#   report-missing-999.sh            full report on stdout
#   report-missing-999.sh --selftest probe discrimination check only
#   report-missing-999.sh --help
#
# EXIT  0 = report produced (boxes may be missing -- that is the finding, not a
#           failure).   2 = tooling failure (fleet-access failed or unparsable,
#           instrument control failed). No verdict is admissible on exit 2.
#
# TEST HOOKS (fixture tests only; defaults are the real tools)
#   FLEET_ACCESS_BIN    resolver  (default ~/.claude/tools/fleet-access.sh)
#   REPORT_999_SSH_BIN  ssh       (default /usr/bin/ssh)
#
# Bash 3.2-safe: no associative arrays, no mapfile, no case modifiers.
# ponytail: boxes are probed one at a time (about 25 Mac boxes, a few seconds
# each); add a worker pool only if the fleet grows past what one roll tolerates.
# ponytail: VPS and Contabo boxes are reported UNKNOWN because fleet-access
# exposes no per-box shell route for them (addresses are redacted, the Contabo
# alias is shared); add them when the tool exposes one.
# ============================================================================
set -uo pipefail

FLEET_ACCESS_BIN="${FLEET_ACCESS_BIN:-$HOME/.claude/tools/fleet-access.sh}"
SSH_BIN="${REPORT_999_SSH_BIN:-/usr/bin/ssh}"
PY=/usr/bin/python3
export PYTHONDONTWRITEBYTECODE=1   # read-only means no interpreter cache written under $HOME either

usage() { sed -n '2,/^# =\{20,\}$/p' "$0" | sed 's/^# \{0,1\}//'; }

die_tooling() {
  printf 'TOOLING FAILURE: %s\nNo verdict is admissible. Nothing was changed on any box.\n' "$1" >&2
  exit 2
}

case "${1:-}" in
  -h|--help) usage; exit 0 ;;
  --selftest|"") ;;
  *) printf 'unknown argument: %s (try --help)\n' "$1" >&2; exit 64 ;;
esac

[ -x "$PY" ] || die_tooling "$PY not executable"

WORK="$(mktemp -d "${TMPDIR:-/tmp}/report-missing-999.XXXXXX")" || die_tooling "mktemp failed"
trap 'rm -rf "$WORK"' EXIT

# ---------------------------------------------------------------------------
# The probe. POSIX sh, runs on the box (or locally for the operator box), reads
# only: `test -f`, `cd -P`, `dirname`. Prints exactly one marker line.
# Locations mirror shared-utils/fleet_refresh_runner.py (_999_SKILL_LINKS,
# _999_CANDIDATES, _999_INSTALLER and the two marker files).
# ---------------------------------------------------------------------------
PROBE="$WORK/probe.sh"
cat > "$PROBE" <<'PROBE_EOF'
need() {
  [ -f "$1/.claude/skills/nine-router-setup/scripts/setup-macos.sh" ] &&
  [ -f "$1/AGENT_INSTALL.md" ] &&
  [ -f "$1/CONTROL/bundled-skills.txt" ]
}
HP=$(cd -P "$HOME" 2>/dev/null && pwd -P)
show() { case "$1" in "$HOME"/*) echo "${1#"$HOME"/}" ;; "$HP"/*) echo "${1#"$HP"/}" ;; *) echo "$1" ;; esac; }
for l in .claude/skills/nine-router-setup .claude-nine/skills/nine-router-setup; do
  [ -L "$HOME/$l" ] || continue
  d=$(cd -P "$HOME/$l" 2>/dev/null && pwd -P) || continue
  r=$(dirname "$(dirname "$(dirname "$d")")")
  if need "$r"; then echo "__R999__ INSTALLED $(show "$r")"; exit 0; fi
done
for c in Documents/999-setup Documents/999-setup-main \
         Downloads/999-setup Downloads/999-setup-main \
         999-setup 999-setup-main Desktop/999-setup \
         clawd/999-setup projects/999-setup Projects/999-setup; do
  if need "$HOME/$c"; then echo "__R999__ INSTALLED $c"; exit 0; fi
done
echo "__R999__ MISSING"
PROBE_EOF

# Reads a probe output file; prints "INSTALLED <where>" | "MISSING" | "NOMARKER".
classify() {
  local line
  line="$(grep '^__R999__ ' "$1" 2>/dev/null | tail -n 1)"
  case "$line" in
    "__R999__ INSTALLED "*) printf 'INSTALLED %s\n' "${line#__R999__ INSTALLED }" ;;
    "__R999__ MISSING")     printf 'MISSING\n' ;;
    *)                      printf 'NOMARKER\n' ;;
  esac
}

# Runs the probe against a local HOME (operator box, and the instrument control).
probe_local_home() {
  HOME="$1" /bin/sh -s < "$PROBE" > "$WORK/local.out" 2>&1
  classify "$WORK/local.out"
}

# ---- CONTROL: the probe must separate present from absent -------------------
instrument_control() {
  local fx="$WORK/control" got
  mkdir -p "$fx/yes/Documents/999-setup/.claude/skills/nine-router-setup/scripts" \
           "$fx/yes/Documents/999-setup/CONTROL" "$fx/no" \
           "$fx/partial/Documents/999-setup/CONTROL"
  : > "$fx/yes/Documents/999-setup/.claude/skills/nine-router-setup/scripts/setup-macos.sh"
  : > "$fx/yes/Documents/999-setup/AGENT_INSTALL.md"
  : > "$fx/yes/Documents/999-setup/CONTROL/bundled-skills.txt"
  : > "$fx/partial/Documents/999-setup/CONTROL/bundled-skills.txt"
  got="$(probe_local_home "$fx/yes")"
  [ "$got" = "INSTALLED Documents/999-setup" ] || die_tooling "probe control (planted checkout) answered '$got', expected INSTALLED"
  got="$(probe_local_home "$fx/no")"
  [ "$got" = "MISSING" ] || die_tooling "probe control (empty home) answered '$got', expected MISSING"
  got="$(probe_local_home "$fx/partial")"
  [ "$got" = "MISSING" ] || die_tooling "probe control (partial checkout) answered '$got', expected MISSING"
}
instrument_control
if [ "${1:-}" = "--selftest" ]; then
  echo "SELFTEST PASSED: the probe separates installed, empty and partial checkouts."
  exit 0
fi

# ---- the roster and routes: fleet-access only --------------------------------
[ -x "$FLEET_ACCESS_BIN" ] || die_tooling "fleet-access tool not executable: $FLEET_ACCESS_BIN"
"$FLEET_ACCESS_BIN" --all --json > "$WORK/fa.out" 2> "$WORK/fa.err"
fa_rc=$?
[ "$fa_rc" -eq 0 ] || die_tooling "fleet-access exited $fa_rc: $(tail -n 3 "$WORK/fa.err" | tr '\n' ' ')"

# Output = source preamble, then one JSON document. Emit one TSV row per box:
#   BOX<TAB>slug<TAB>platform<TAB>REACHABLE|<verdict text><TAB>alias-or-'-'
# plus NOTE rows for the tool's own class-control warnings.
if ! "$PY" - "$WORK/fa.out" > "$WORK/boxes.tsv" 2> "$WORK/parse.err" <<'PY_EOF'
import json, re, sys
t = open(sys.argv[1]).read()
m = re.search(r'^\{\s*$', t, re.M)
if not m:
    sys.exit("no JSON document in fleet-access output")
d = json.JSONDecoder().raw_decode(t[m.start():])[0]
boxes = d.get("boxes")
if not isinstance(boxes, list) or not boxes:
    sys.exit("fleet-access returned no boxes")
clean = lambda s: re.sub(r'[\t\r\n]+', ' ', str(s)).strip()
for b in boxes:
    slug, plat, verdict = clean(b["slug"]), clean(b.get("platform", "unknown")), clean(b.get("verdict", ""))
    alias = "-"
    if plat == "mac":
        for p in b.get("paths", []):
            r = str(p.get("route", ""))
            if r.startswith("alias:") and p.get("verdict") == "REACHABLE":
                alias = clean(r[len("alias:"):]) or "-"
                break
    print("BOX\t%s\t%s\t%s\t%s" % (slug, plat, "REACHABLE" if verdict == "REACHABLE" else verdict[:90], alias))
failed = d.get("class_control_failed") or []
suspect = d.get("class_control_suspect") or {}
if failed:
    print("NOTE\tfleet-access class control FAILED for: %s" % clean(",".join(map(str, failed))))
if suspect:
    print("NOTE\tfleet-access class control SUSPECT for: %s" % clean(",".join(map(str, suspect))))
PY_EOF
then
  die_tooling "could not read fleet-access output: $(tail -n 2 "$WORK/parse.err" | tr '\n' ' ')"
fi

# ---- probe each box -----------------------------------------------------------
RESULTS="$WORK/results.tsv"      # status<TAB>slug<TAB>detail
NOTES="$WORK/notes.txt"
: > "$RESULTS"; : > "$NOTES"
total=0
TILDE='~'    # display only: a literal ~ in the report, never expanded

while IFS="$(printf '\t')" read -r kind slug platform reach alias; do
  if [ "$kind" = "NOTE" ]; then printf '%s\n' "$slug" >> "$NOTES"; continue; fi
  [ "$kind" = "BOX" ] || continue
  total=$((total + 1))

  if [ "$reach" != "REACHABLE" ]; then
    printf 'UNKNOWN\t%s\tnot reachable per fleet-access: %s\n' "$slug" "$reach" >> "$RESULTS"; continue
  fi

  if [ "$platform" = "local" ]; then
    got="$(probe_local_home "$HOME")"
  elif [ "$platform" = "mac" ] && [ "$alias" != "-" ]; then
    # The alias came from tool output: accept only a plain host alias, never an option.
    case "$alias" in
      [A-Za-z0-9]*) ;;
      *) printf 'UNKNOWN\t%s\talias from fleet-access rejected (not a plain host alias)\n' "$slug" >> "$RESULTS"; continue ;;
    esac
    case "$alias" in
      *[!A-Za-z0-9._-]*) printf 'UNKNOWN\t%s\talias from fleet-access rejected (not a plain host alias)\n' "$slug" >> "$RESULTS"; continue ;;
    esac
    "$SSH_BIN" -o BatchMode=yes -o ConnectTimeout=8 -o ServerAliveInterval=5 -o ServerAliveCountMax=2 \
      -o LogLevel=ERROR "$alias" 'sh -s' < "$PROBE" > "$WORK/box.out" 2> "$WORK/box.err"
    ssh_rc=$?
    got="$(classify "$WORK/box.out")"
    if [ "$got" = "NOMARKER" ]; then
      printf 'UNKNOWN\t%s\tprobe gave no answer (ssh exit %s) -- absence of an answer is not evidence\n' "$slug" "$ssh_rc" >> "$RESULTS"; continue
    fi
  else
    printf 'UNKNOWN\t%s\tno per-box shell route in fleet-access output (%s box)\n' "$slug" "$platform" >> "$RESULTS"; continue
  fi

  case "$got" in
    "INSTALLED "*)
      where="${got#INSTALLED }"
      case "$where" in /*) ;; *) where="${TILDE}/$where" ;; esac
      printf 'INSTALLED\t%s\t%s\n' "$slug" "$where" >> "$RESULTS" ;;
    MISSING)       printf 'MISSING\t%s\t-\n' "$slug" >> "$RESULTS" ;;
    *)             printf 'UNKNOWN\t%s\tlocal probe gave no answer\n' "$slug" >> "$RESULTS" ;;
  esac
done < "$WORK/boxes.tsv"

[ "$total" -gt 0 ] || die_tooling "fleet-access listed zero boxes"

# ---- report -------------------------------------------------------------------
count() { grep -c "^$1	" "$RESULTS" || true; }
n_missing="$(count MISSING)"; n_inst="$(count INSTALLED)"; n_unk="$(count UNKNOWN)"

echo "999-SETUP MISSING REPORT   $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "Source: fleet-access --all (${total} boxes). Read-only: nothing installed, nothing written on any box."
echo

echo "MISSING 999-setup (${n_missing}) -- reachable, probe answered, no checkout found:"
if [ "$n_missing" -gt 0 ]; then grep '^MISSING	' "$RESULTS" | cut -f2 | sort | sed 's/^/  /'; else echo "  (none)"; fi
echo

echo "INSTALLED (${n_inst}):"
if [ "$n_inst" -gt 0 ]; then grep '^INSTALLED	' "$RESULTS" | sort -t"$(printf '\t')" -k2 | awk -F'\t' '{printf "  %-40s %s\n", $2, $3}'; else echo "  (none)"; fi
echo

echo "UNKNOWN (${n_unk}) -- not a finding either way, reason shown:"
if [ "$n_unk" -gt 0 ]; then grep '^UNKNOWN	' "$RESULTS" | sort -t"$(printf '\t')" -k2 | awk -F'\t' '{printf "  %-40s %s\n", $2, $3}'; else echo "  (none)"; fi
echo

if [ -s "$NOTES" ]; then
  echo "Notes from fleet-access:"; sed 's/^/  /' "$NOTES"; echo
fi

echo "Searched on each probed box: skill links ~/.claude/skills/nine-router-setup and"
echo "  ~/.claude-nine/skills/nine-router-setup, then Documents, Downloads, Desktop, home,"
echo "  clawd and projects checkout locations (same list the roll's refresh step uses)."
echo "NOT searched: any other path. MISSING means 'none of those', not 'nowhere on disk'."
echo
echo "RESULT total=${total} missing=${n_missing} installed=${n_inst} unknown=${n_unk}"
exit 0
