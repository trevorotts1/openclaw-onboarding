#!/usr/bin/env bash
# install-full-read-guard.sh -- install + enable the full-read-guard OpenClaw plugin on ONE box.
#
# Trevor's order (2026-11-12): agents must read a skill and its dependencies IN FULL, and the
# guard must be picked up on the NEXT FLEET ROLL with no manual step. This script is the roll's
# hook. It is called by update-skills.sh (every roll, above the "content already current" exit),
# by update-skills.sh again for a verify, and by install.sh for fresh installs.
#
# Modes
#   (default) / --install  copy extensions/full-read-guard into <OpenClaw root>/extensions/ and
#                          enable it in <OpenClaw root>/openclaw.json. Idempotent.
#   --repair-config        config only: re-assert enabled + load path + allow-list entry (used
#                          after apply-fleet-standards.sh, which can rewrite plugins.allow).
#   --verify               read-only. Prints one "full-read-guard: PASS|FAIL|SKIP ..." line.
#                          Exit 0 on PASS or SKIP (plugin not shipped), 1 on FAIL.
#
# Options
#   --root DIR     OpenClaw root. Default resolution: --root, $OPENCLAW_ROOT, $OC_CONFIG, $OC_ROOT,
#                  /data/.openclaw (Docker VPS), /home/node/.openclaw (Contabo container),
#                  $HOME/.openclaw (Mac). NEVER assumes $HOME/.openclaw when another root exists.
#   --source DIR   directory holding the plugin folder or the folder itself. Default search:
#                  $OC_CONFIG/.extensions-stage (the roll's stage), $ONBOARDING_DIR/extensions,
#                  <this script>/../extensions.
#
# Rules (each one is a known fleet failure, see the plan):
#   * writes only plugins.entries.full-read-guard.enabled=true (+ additive config.mode), the
#     load path and, only when an allowlist already exists, the allow entry. Never a `hooks` key.
#   * an operator's own config values are never overwritten.
#   * atomic write; `openclaw config validate` afterwards when the CLI exists; on failure the
#     original bytes (kept in memory) are restored. No backup file is created.
#   * a missing plugin folder is a logged no-op, never an error, so a roll that carries this
#     script before the plugin is merged does not fail.
#   * never fails a roll: install mode always exits 0 (problems are printed as ADVISORY).
set -u

PLUGIN_ID="full-read-guard"
MODE="install"
ROOT_ARG=""
SRC_ARG=""
while [ $# -gt 0 ]; do
  case "$1" in
    --install) MODE="install" ;;
    --repair-config) MODE="repair" ;;
    --verify) MODE="verify" ;;
    --root) ROOT_ARG="${2:-}"; shift ;;
    --source) SRC_ARG="${2:-}"; shift ;;
    -h|--help) sed -n 2,34p "$0"; exit 0 ;;
    *) echo "full-read-guard: ADVISORY unknown argument '$1' ignored" ;;
  esac
  shift
done

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"

resolve_root() {
  local c
  for c in "$ROOT_ARG" "${OPENCLAW_ROOT:-}" "${OC_CONFIG:-}" "${OC_ROOT:-}"; do
    if [ -n "$c" ] && [ -d "$c" ]; then printf '%s' "$c"; return 0; fi
  done
  for c in /data/.openclaw /home/node/.openclaw "$HOME/.openclaw"; do
    if [ -d "$c" ]; then printf '%s' "$c"; return 0; fi
  done
  return 1
}

find_source() {
  local base c
  for base in "$SRC_ARG" "${OC_CONFIG:-}/.extensions-stage" "${ROOT:-}/.extensions-stage" \
              "${ONBOARDING_DIR:-}/extensions" "$SELF_DIR/../extensions"; do
    [ -n "$base" ] && [ "$base" != "/.extensions-stage" ] || continue
    if [ -f "$base/openclaw.plugin.json" ] && [ "$(basename "$base")" = "$PLUGIN_ID" ]; then
      printf '%s' "$base"; return 0
    fi
    c="$base/$PLUGIN_ID"
    if [ -d "$c" ] && [ -f "$c/openclaw.plugin.json" ]; then printf '%s' "$c"; return 0; fi
  done
  return 1
}

plugin_version() {  # $1 = plugin dir
  python3 -I - "$1/openclaw.plugin.json" <<'PY' 2>/dev/null || echo "unknown"
import json, sys
try:
    print(json.load(open(sys.argv[1])).get("version", "unknown"))
except Exception:
    print("unknown")
PY
}

if ! ROOT="$(resolve_root)"; then
  if [ "$MODE" = "verify" ]; then
    echo "full-read-guard: SKIP no OpenClaw root found on this box"
  else
    echo "full-read-guard: no-op, no OpenClaw root found (checked --root, OPENCLAW_ROOT, OC_CONFIG, OC_ROOT, /data/.openclaw, /home/node/.openclaw, \$HOME/.openclaw)"
  fi
  exit 0
fi
EXT_DIR="$ROOT/extensions"
DST="$EXT_DIR/$PLUGIN_ID"
CFG="$ROOT/openclaw.json"

# --------------------------------------------------------------------------- config edit
# MODE_PY: install|repair -> edit ; verify -> check only. Prints a single result word on stdout.
config_py() {
  FRG_CFG="$CFG" FRG_EXT="$EXT_DIR" FRG_ID="$PLUGIN_ID" FRG_ACTION="$1" python3 -I - <<'PY'
import json, os, sys
cfg_path = os.environ["FRG_CFG"]; ext = os.environ["FRG_EXT"]
pid = os.environ["FRG_ID"]; action = os.environ["FRG_ACTION"]
if not os.path.isfile(cfg_path):
    print("NOCONFIG"); sys.exit(0)
raw = open(cfg_path, "rb").read()
try:
    cfg = json.loads(raw.decode("utf-8"))
except Exception:
    print("BADJSON"); sys.exit(0)
if not isinstance(cfg, dict):
    print("BADJSON"); sys.exit(0)
plugins = cfg.get("plugins") if isinstance(cfg.get("plugins"), dict) else {}
entry = (plugins.get("entries") or {}).get(pid) if isinstance(plugins.get("entries"), dict) else None
paths = ((plugins.get("load") or {}).get("paths") or []) if isinstance(plugins.get("load"), dict) else []
allow = plugins.get("allow")
def state():
    miss = []
    if not (isinstance(entry, dict) and entry.get("enabled") is True): miss.append("enabled")
    if ext not in paths: miss.append("load-path")
    if isinstance(allow, list) and pid not in allow: miss.append("allow")
    return miss
if action == "check":
    m = state()
    print("OK" if not m else "MISSING:" + ",".join(m)); sys.exit(0)
p = cfg.setdefault("plugins", {})
if not isinstance(p, dict):
    print("BADJSON"); sys.exit(0)
e = p.setdefault("entries", {}).setdefault(pid, {})
e["enabled"] = True                       # only `enabled` is forced; never a `hooks` key
c = e.setdefault("config", {})
if isinstance(c, dict):
    c.setdefault("mode", "enforce")      # additive: an operator's own mode wins
lp = p.setdefault("load", {}).setdefault("paths", [])
if ext not in lp: lp.append(ext)
a = p.get("allow")
if isinstance(a, list) and pid not in a: a.append(pid)   # extend an existing allowlist only
new = (json.dumps(cfg, indent=2) + "\n").encode("utf-8")
if new == raw or json.loads(raw.decode()) == cfg:
    print("UNCHANGED"); sys.exit(0)
tmp = cfg_path + ".tmp.frg"
with open(tmp, "wb") as f:
    f.write(new); f.flush(); os.fsync(f.fileno())
os.replace(tmp, cfg_path)
print("CHANGED")
PY
}

restore_config() {  # $1 = file holding original bytes (in the box's own tmp, removed right after)
  cat "$1" > "$CFG.tmp.frg" && mv "$CFG.tmp.frg" "$CFG"
}

validate_file() {  # $1 = config file; 0 = ok or CLI absent
  command -v openclaw >/dev/null 2>&1 || return 0
  OPENCLAW_CONFIG_PATH="$1" openclaw config validate >/dev/null 2>&1
}

edit_config() {  # prints a short status line
  if [ ! -f "$CFG" ]; then echo "config-absent"; return 0; fi
  local orig res base_ok=1
  orig="$(mktemp "${TMPDIR:-$ROOT}/frg-orig.XXXXXX" 2>/dev/null || mktemp)"
  cat "$CFG" > "$orig"
  # Only blame this edit when the config validated BEFORE it. A box whose config was already
  # invalid for some other reason must not make every install roll itself back.
  validate_file "$orig" || base_ok=0
  res="$(config_py edit)"
  case "$res" in
    CHANGED)
      if validate_file "$CFG"; then echo "enabled"
      elif [ "$base_ok" = 0 ]; then echo "enabled-but-config-was-already-invalid-before-this-edit"
      else restore_config "$orig"; echo "config-restored-after-validate-failure"
      fi ;;
    UNCHANGED) echo "already-enabled" ;;
    BADJSON) echo "config-unreadable-left-untouched" ;;
    NOCONFIG) echo "config-absent" ;;
    *) echo "config-edit-error" ;;
  esac
  rm -f "$orig"
}

# --------------------------------------------------------------------------- verify
if [ "$MODE" = "verify" ]; then
  if [ ! -d "$DST" ]; then
    if SRC="$(find_source)"; then
      echo "full-read-guard: FAIL plugin shipped but not installed at $DST (root $ROOT)"; exit 1
    fi
    echo "full-read-guard: SKIP plugin not shipped in this release (root $ROOT)"; exit 0
  fi
  [ -f "$DST/openclaw.plugin.json" ] || { echo "full-read-guard: FAIL $DST has no openclaw.plugin.json"; exit 1; }
  [ -f "$CFG" ] || { echo "full-read-guard: FAIL no openclaw.json at $CFG"; exit 1; }
  res="$(config_py check)"
  case "$res" in
    OK) echo "full-read-guard: PASS $(plugin_version "$DST") enabled, loaded from $EXT_DIR"; exit 0 ;;
    MISSING:*) echo "full-read-guard: FAIL config missing ${res#MISSING:} (root $ROOT)"; exit 1 ;;
    *) echo "full-read-guard: FAIL cannot read $CFG ($res)"; exit 1 ;;
  esac
fi

# --------------------------------------------------------------------------- repair-config
if [ "$MODE" = "repair" ]; then
  if [ ! -d "$DST" ]; then echo "full-read-guard: repair skipped, plugin not installed at $DST"; exit 0; fi
  echo "full-read-guard: config $(edit_config) (repair, root $ROOT)"
  exit 0
fi

# --------------------------------------------------------------------------- install
if ! SRC="$(find_source)"; then
  echo "full-read-guard: no-op, extensions/full-read-guard not found in this release (searched --source, \$OC_CONFIG/.extensions-stage, \$ONBOARDING_DIR/extensions, repo extensions/)"
  exit 0
fi
NEWV="$(plugin_version "$SRC")"
OLDV="none"; [ -f "$DST/openclaw.plugin.json" ] && OLDV="$(plugin_version "$DST")"
mkdir -p "$DST" 2>/dev/null
# the `/.` form on purpose: without it a second run nests a copy inside the first.
if ! cp -R "$SRC/." "$DST/" 2>/dev/null; then
  echo "full-read-guard: ADVISORY copy into $DST failed, plugin NOT installed (root $ROOT)"
  exit 0
fi
CFGRES="$(edit_config)"
if [ "$OLDV" = "$NEWV" ]; then VMSG="already $NEWV"; else VMSG="installed $NEWV (was $OLDV)"; fi
echo "full-read-guard: $VMSG; config $CFGRES; root $ROOT"
exit 0
