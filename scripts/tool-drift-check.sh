#!/usr/bin/env bash
# ==============================================================================
# tool-drift-check.sh — installed-tool vs skill-source RECONCILIATION GUARD
# ==============================================================================
# Root cause it defends against:
#   Several skills install a STANDALONE CLI by COPYING the skill-source engine
#   into ~/.openclaw/tools/<tool>/ and `pip install -e .` against the COPY.
#   The routine update path (update-skills.sh) syncs the skill SOURCE files but
#   NEVER re-copies the engine or re-runs the editable install — so the installed
#   binary silently drifts behind the source. Source-on-disk != working binary.
#
#   Confirmed live example (caf): skill source has `payments create-product` /
#   `payments create-price` (gohighlevel_cli.py:1430 / :1465) but the installed
#   `caf payments --help` only lists create-invoice/invoices/orders/transactions.
#
# What this guard does (READ-ONLY by default):
#   (a) reads an install-time version STAMP from the install dir (.installed-from)
#   (b) compares it to the CURRENT skill-source version (skill-version.txt)
#   (c) runs a CREDS-FREE CAPABILITY PROBE: it invokes the tool's OWN venv python
#       as `python -m <package> <subcmd> --help` (NOT the credentialed CLI wrapper,
#       which hard-exits rc=1 without GHL creds and would yield a FALSE drift on any
#       box lacking GHL credentials) and asserts each expected sub-command resolves
#       rc=0 — because a matching source on disk does NOT prove the editable-installed
#       binary actually exposes them. This mirrors the creds-free editable-install
#       resolution in skill 44's wire.sh is_current().
#   (d) emits one JSON object per tool + an aggregate, and a top-level overall_pass
#
#   If a tool is stale or its probe fails it PRINTS the exact rebuild command but
#   DOES NOT run it. Rebuild is opt-in behind the separate `--rebuild` flag.
#
# Exit code: 0 iff every registered tool has drift=false AND probe_pass=true.
#            1 otherwise (so it can gate update-skills.sh / prove-floor.py).
#
# Usage:
#   bash tool-drift-check.sh                 # read-only check, JSON to stdout
#   bash tool-drift-check.sh --json-only     # suppress human lines, JSON only
#   bash tool-drift-check.sh --write-stamp   # (opt-in) (re)write .installed-from
#                                            #   stamps from current source — use
#                                            #   right AFTER a real rebuild only
#   bash tool-drift-check.sh --rebuild       # (opt-in) run the printed rebuild
#                                            #   command for failing tools, then
#                                            #   re-probe. NEVER the default.
#
# Extending to other copy-installed tools: add a `register_tool` line in the
# REGISTRY section at the bottom. No other edits needed.
# ==============================================================================
set -u

JSON_ONLY=0
DO_REBUILD=0
DO_WRITE_STAMP=0
for arg in "$@"; do
  case "$arg" in
    --json-only)   JSON_ONLY=1 ;;
    --rebuild)     DO_REBUILD=1 ;;
    --write-stamp) DO_WRITE_STAMP=1 ;;
    -h|--help)
      grep -E '^#( |$)' "$0" | sed 's/^# \{0,1\}//' | head -55
      exit 0 ;;
    *) echo "unknown arg: $arg" >&2; exit 64 ;;
  esac
done

log()  { [ "$JSON_ONLY" -eq 1 ] || echo "$@" >&2; }
expand() { # expand a leading ~ to $HOME
  # NB: the strip pattern MUST be quoted (`${1#"~/"}`). Unquoted `${1#~/}` is
  # subject to tilde expansion on the pattern itself (bash 3.2 AND 5.x), so the
  # pattern becomes "$HOME/" and never matches the literal leading "~/" in the
  # value — yielding a bogus "$HOME/~/.openclaw/..." that resolves to nothing and
  # makes EVERY registered ~/-path tool false-report drift. Quoting fixes it.
  case "$1" in "~"/*) printf '%s' "$HOME/${1#"~/"}";; *) printf '%s' "$1";; esac
}

# Results accumulate as TAB-delimited records consumed by the JSON emitter.
# fields: name  source_version  installed_version  drift  probe_pass  overall_pass  reason  rebuild_cmd
RESULTS_FILE="$(mktemp -t tool-drift-check.XXXXXX)"
trap 'rm -f "$RESULTS_FILE"' EXIT
AGG_FAIL=0

# ------------------------------------------------------------------------------
# check_tool — one registered tool.
# Args (positional):
#   1 name            short id, e.g. caf
#   2 install_dir     dir holding the installed binary + the .installed-from stamp
#   3 bin_rel         probe executable, relative to install_dir. Use the tool's OWN
#                     venv python (e.g. .venv/bin/python) so the probe is CREDS-FREE.
#                     Do NOT point this at the credentialed CLI wrapper (e.g. caf):
#                     the wrapper hard-exits rc=1 when GHL creds are absent, which
#                     would mark a freshly-built tool as failing on any creds-less box.
#   4 skill_src_dir   skill source dir, e.g. ~/.openclaw/skills/44-convert-and-flow-operator
#   5 version_file    version file relative to skill_src_dir, e.g. skill-version.txt
#   6 probe_argv_list ';'-separated argv strings; each run as: "$BIN" <argv>; ALL must
#                     exit 0. With the venv python as BIN, each argv is a module
#                     invocation, e.g. `-m cli_anything.gohighlevel payments --help`.
#   7 rebuild_cmd     full shell command to rebuild the installed tool from source
# ------------------------------------------------------------------------------
check_tool() {
  local name="$1" install_dir bin_rel skill_src_dir version_file probe_list rebuild_cmd
  install_dir="$(expand "$2")"; bin_rel="$3"
  skill_src_dir="$(expand "$4")"; version_file="$5"
  probe_list="$6"; rebuild_cmd="$7"

  local BIN="$install_dir/$bin_rel"
  local STAMP="$install_dir/.installed-from"
  local SRC_VER_FILE="$skill_src_dir/$version_file"

  # ---- source version (the truth we want the binary to match) ----
  local source_version="absent"
  [ -f "$SRC_VER_FILE" ] && source_version="$(tr -d '[:space:]' < "$SRC_VER_FILE")"
  # also capture onboarding/wire marker for richer drift signal
  local source_wire="" m
  for m in "$skill_src_dir"/.wired-v*; do [ -e "$m" ] && source_wire="$(basename "$m" | sed 's/^\.wired-//')"; done

  # ---- installed version (from the stamp written at install time) ----
  local installed_version="unknown" installed_wire=""
  if [ -f "$STAMP" ]; then
    installed_version="$(grep -E '^SKILL_VERSION=' "$STAMP" | head -1 | cut -d= -f2- | tr -d '[:space:]')"
    installed_wire="$(grep -E '^ONBOARDING_VERSION=' "$STAMP" | head -1 | cut -d= -f2- | tr -d '[:space:]')"
    [ -z "$installed_version" ] && installed_version="unknown"
  fi

  # ---- (opt-in) (re)write the stamp from current source, then continue ----
  if [ "$DO_WRITE_STAMP" -eq 1 ] && [ -d "$install_dir" ]; then
    {
      echo "TOOL=$name"
      echo "SKILL_VERSION=$source_version"
      echo "ONBOARDING_VERSION=$source_wire"
      echo "INSTALLED_AT=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
      echo "SOURCE_PATH=$skill_src_dir"
    } > "$STAMP"
    installed_version="$source_version"; installed_wire="$source_wire"
    log "[stamp] wrote $STAMP (SKILL_VERSION=$source_version)"
  fi

  # ---- drift decision ----
  # drift=true when we cannot PROVE the binary matches current source:
  #   - stamp missing (legacy install predating the stamp) -> unprovable -> drift
  #   - stamp skill_version != source skill_version
  #   - stamp onboarding/wire marker != source wire marker (when both known)
  local drift="false" reason="in-sync"
  if [ ! -f "$STAMP" ]; then
    drift="true"; reason="no .installed-from stamp (legacy install; cannot prove freshness)"
  elif [ "$installed_version" != "$source_version" ]; then
    drift="true"; reason="version mismatch: installed=$installed_version source=$source_version"
  elif [ -n "$source_wire" ] && [ -n "$installed_wire" ] && [ "$installed_wire" != "$source_wire" ]; then
    drift="true"; reason="onboarding-marker mismatch: installed=$installed_wire source=$source_wire"
  fi

  # ---- capability probe: run the tool's venv python, assert sub-commands ------
  # Load-bearing check: source-on-disk != working binary. Probe via the tool's OWN
  # venv python (`python -m <pkg> <subcmd> --help`) — creds-free, the same way skill
  # 44's wire.sh is_current() resolves the editable install. The credentialed CLI
  # wrapper is deliberately NOT probed: it hard-exits rc=1 without GHL creds and
  # would FALSE-FAIL on any creds-less box. A stale editable-install copy still
  # FAILS `<subcmd> --help` even when the source on disk has it.
  local probe_pass="true" probe_detail="" sub rc
  if [ ! -x "$BIN" ]; then
    probe_pass="false"; probe_detail="binary not found/executable at $BIN"
  else
    local OLD_IFS="$IFS"; IFS=';'
    for sub in $probe_list; do
      IFS="$OLD_IFS"
      sub="$(echo "$sub" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
      [ -z "$sub" ] && continue
      # shellcheck disable=SC2086
      "$BIN" $sub >/dev/null 2>&1; rc=$?
      if [ "$rc" -ne 0 ]; then
        probe_pass="false"
        probe_detail="${probe_detail}{$sub -> rc=$rc} "
      fi
      IFS=';'
    done
    IFS="$OLD_IFS"
    [ "$probe_pass" = "true" ] && probe_detail="all probes exit 0"
  fi
  [ -n "$probe_detail" ] && reason="$reason | probe: $probe_detail"

  # ---- per-tool verdict ----
  local overall="true"
  { [ "$drift" = "true" ] || [ "$probe_pass" != "true" ]; } && overall="false"
  [ "$overall" = "false" ] && AGG_FAIL=1

  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
    "$name" "$source_version" "$installed_version" "$drift" "$probe_pass" \
    "$overall" "$reason" "$rebuild_cmd" >> "$RESULTS_FILE"

  if [ "$overall" = "false" ]; then
    log "DRIFT/PROBE FAIL: $name  (drift=$drift probe_pass=$probe_pass)"
    log "  reason: $reason"
    log "  REBUILD (opt-in — NOT run): $rebuild_cmd"
    if [ "$DO_REBUILD" -eq 1 ]; then
      log "  --rebuild given: running rebuild for $name ..."
      bash -c "$rebuild_cmd" >&2 || log "  rebuild reported non-zero (see output above)"
      log "  re-run this guard (read-only) to confirm the tool now passes."
    fi
  else
    log "OK: $name  (source=$source_version installed=$installed_version, probes pass)"
  fi
}

# ------------------------------------------------------------------------------
# register_tool — thin alias so the registry reads as data, not logic.
# ------------------------------------------------------------------------------
register_tool() { check_tool "$@"; }

# ==============================================================================
# REGISTRY — add a line per copy-installed CLI tool. (Extensible.)
# ==============================================================================
# caf (skill 44 — Convert and Flow Operator). The confirmed drift case.
# Probe binary = the tool's OWN venv python (.venv/bin/python), CREDS-FREE. The
# `caf` wrapper itself hard-exits rc=1 without GHL creds (tools/engine/caf tail:
# `if [ -z "$GHL_API_KEY" ]; then ... exit 1; fi` before `exec python3`), so
# probing the wrapper would FALSE-FAIL on any box lacking GHL credentials even
# when the binary is freshly built and current. Running the module directly via
# the venv python mirrors the creds-free editable-install resolution in skill 44's
# wire.sh is_current() — `<subcmd> --help` exits 0 before any credentialed call.
register_tool \
  "caf" \
  "~/.openclaw/tools/convert-and-flow-cli" \
  ".venv/bin/python" \
  "~/.openclaw/skills/44-convert-and-flow-operator" \
  "skill-version.txt" \
  "-m cli_anything.gohighlevel payments create-product --help ; -m cli_anything.gohighlevel payments create-price --help ; -m cli_anything.gohighlevel payments --help" \
  "bash ~/.openclaw/skills/44-convert-and-flow-operator/tools/engine/install.sh"

# video-creator (skill 25 — Video Creator). Same drift CLASS as caf, different
# shape: skill 25 installs by COPYING the whole skill into an UN-numbered
# ~/.openclaw/skills/video-creator/ (the runtime location named by TOOLS.md /
# CORE_UPDATES.md / qc-video-creator.sh) plus a local `venv`. The wiring loop
# only walks numbered dirs ([0-9]*/, update-skills.sh:1617) and re-syncs the
# NUMBERED source, so the un-numbered copy + its venv silently drift. Skill 25's
# root wire.sh now reconciles them and writes this .installed-from stamp.
#
# Probe binary = the copy's OWN venv python (venv/bin/python), CREDS-FREE: skill
# 25's scripts need no API keys to import their runtime (keys are only read at
# generation time, and `--provider mock`/`local` need none). Each probe is a
# stdlib-style `-c __import__('<mod>')` of a PINNED dependency — written as a
# single space-free token so the registry's word-split argv passes it intact (a
# `-c "import x.y"` form would be split on its internal space). `moviepy.editor`
# is load-bearing: it FAILS on MoviePy v2 (which removed that module), so it
# also catches the exact v1-vs-v2 pin drift INSTALL.md Step 2 warns about. A
# stale/empty/wrong venv FAILS these even when the source on disk looks current.
register_tool \
  "video-creator" \
  "~/.openclaw/skills/video-creator" \
  "venv/bin/python" \
  "~/.openclaw/skills/25-video-creator" \
  "skill-version.txt" \
  "-c __import__('moviepy.editor') ; -c __import__('cv2') ; -c __import__('numpy') ; -c __import__('PIL') ; -c __import__('requests')" \
  "bash ~/.openclaw/skills/25-video-creator/wire.sh"

# ==============================================================================
# JSON EMIT + aggregate verdict (python3 = hard dep on Mac per repo convention)
# ==============================================================================
python3 - "$RESULTS_FILE" <<'PYEOF'
import sys, json
path = sys.argv[1]
tools = []
overall = True
with open(path, encoding="utf-8") as f:
    for line in f:
        line = line.rstrip("\n")
        if not line:
            continue
        name, src, inst, drift, probe, ov, reason, rebuild = line.split("\t")
        tb = {"tool": name,
              "source_version": src,
              "installed_version": inst,
              "drift": (drift == "true"),
              "probe_pass": (probe == "true"),
              "overall_pass": (ov == "true"),
              "reason": reason,
              "rebuild_command": rebuild}
        if not tb["overall_pass"]:
            overall = False
        tools.append(tb)
print(json.dumps({"check": "tool-drift",
                  "overall_pass": overall,
                  "tool_count": len(tools),
                  "tools": tools}, indent=2))
PYEOF

exit "$AGG_FAIL"
