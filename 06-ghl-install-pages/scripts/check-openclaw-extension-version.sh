#!/usr/bin/env bash
# check-openclaw-extension-version.sh — Skill 06 standing preflight:
# reports the OpenClaw extension lane's (Lane 1) verdict. The extension is
# Skill 6's PRIMARY browser engine (operator decision, 2026-10-13), but
# the verdict gates Lane 1 ONLY: a missing or stale extension disables
# Lane 1 and the run proceeds on the next lane the capability probe
# verifies; a run stops only when zero lanes verify (fail closed).
#
# What "current" means here, in resolution order:
#   1. $SKILL6_OPENCLAW_EXTENSION_EXPECTED_VERSION, when the operator pins it.
#   2. The version of the extension source the local OpenClaw install bundles
#      ($OPENCLAW_HOME/browser/chrome-extension/manifest.json, default
#      ~/.openclaw/browser/chrome-extension/manifest.json) — the OpenClaw
#      release on the box and its extension ship in lockstep.
#   3. Unknown: presence alone passes WITH a warning; the Chrome Web Store
#      listing is the authority in that case (see the URL below).
#
# Installed versions are read from each Chrome profile's Secure Preferences
# (Default + Profile * under the OS Chrome user-data dir, plus every
# OpenClaw-managed browser user-data dir). $GHL_SKILL6_CHROME_PROFILE_ROOTS
# (os.pathsep-separated) overrides the scan roots — same knobs the capability
# probe uses, so the two never disagree.
#
# Exit codes (human mode): 0 = installed and current (or installed with
# currency unknown, with a warning); 2 = missing or behind (Lane 1
# unavailable); 1 = the check itself could not run.
# Exit codes (--json mode): 0 = a verdict was computed (current, behind,
# missing, and unknown-currency are all verdicts); 2 = the check itself
# could not run. The check cannot run when: python3 is absent; the
# embedded probe fails or its output cannot be parsed; or no enumerated
# Chrome profile root exists on disk AND no expected-version source
# exists (no operator pin and no readable bundled manifest). A profile
# root that does not exist is otherwise NOT an error: it contributes no
# installed version, and "not installed" is a computable verdict.
#
# Usage: bash scripts/check-openclaw-extension-version.sh [--json]
#   --json prints exactly one JSON object and nothing else on stdout:
#   {installed, version, expectedVersion, expectedSource, current, lane,
#    laneAvailable}. current is true, false, or "unknown";
#    expectedSource is "operator-pin", "bundled-manifest", or "unknown";
#    lane is always "openclaw-extension"; laneAvailable = installed AND
#    current != false (mirrors the capability probe, which accepts
#    presence with a warning when currency is unknown).

set -u

EXTENSION_ID="kcdjddhmeafeomebliikmbpblkmkfoig"
STORE_URL="https://chromewebstore.google.com/detail/openclaw/${EXTENSION_ID}"

MODE="human"
if [ $# -gt 0 ]; then
  if [ "$1" = "--json" ]; then
    MODE="json"
  else
    echo "Usage: bash scripts/check-openclaw-extension-version.sh [--json]" >&2
    exit 1
  fi
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "ERROR: python3 not found; cannot run the OpenClaw extension preflight." >&2
  if [ "$MODE" = "json" ]; then
    exit 2
  fi
  exit 1
fi

if [ "$MODE" = "json" ]; then
  EXT_JSON=1
else
  EXT_JSON=0
fi

RESULT="$(SKILL6_EXT_JSON="$EXT_JSON" python3 - << 'PYEOF'
import glob, json, os, platform, sys

EXT_ID = "kcdjddhmeafeomebliikmbpblkmkfoig"
JSON_MODE = os.environ.get("SKILL6_EXT_JSON") == "1"

def semver(v):
    parts = []
    for piece in str(v or "").split("."):
        try:
            parts.append(int(piece))
        except ValueError:
            parts.append(0)
    return parts

def roots(env):
    out = []
    raw = env.get("GHL_SKILL6_CHROME_PROFILE_ROOTS", "")
    if raw:
        out.extend([p for p in raw.split(os.pathsep) if p])
    home = env.get("HOME") or os.path.expanduser("~")
    if platform.system().lower() == "darwin":
        out.append(os.path.join(home, "Library", "Application Support",
                                "Google", "Chrome"))
    else:
        out.append(os.path.join(home, ".config", "google-chrome"))
        out.append(os.path.join(home, ".config", "chromium"))
    oc_home = env.get("OPENCLAW_HOME") or os.path.join(home, ".openclaw")
    bdir = os.path.join(oc_home, "browser")
    try:
        for name in sorted(os.listdir(bdir)):
            ud = os.path.join(bdir, name, "user-data")
            if os.path.isdir(ud):
                out.append(ud)
    except OSError:
        pass
    seen = []
    for r in out:
        if r not in seen:
            seen.append(r)
    return seen

def version_in(user_data):
    best, best_key = None, None
    cands = [user_data] + sorted(
        d for d in glob.glob(os.path.join(user_data, "*")) if os.path.isdir(d))
    for prof in cands:
        try:
            with open(os.path.join(prof, "Secure Preferences")) as f:
                data = json.load(f)
        except Exception:
            continue
        settings = (data.get("extensions", {}) or {}).get("settings", {}) or {}
        info = settings.get(EXT_ID)
        if not info:
            continue
        ver = str((info.get("manifest") or {}).get("version")
                  or info.get("version") or "")
        if ver and (best_key is None or semver(ver) > best_key):
            best, best_key = ver, semver(ver)
    return best

def cannot_run(reason):
    sys.stderr.write("cannot run: %s\n" % reason)
    sys.exit(3)

env = dict(os.environ)
all_roots = roots(env)
roots_exist = 0
for r in all_roots:
    if os.path.isdir(r):
        roots_exist += 1

installed = None
for root in all_roots:
    ver = version_in(root)
    if ver and (installed is None or semver(ver) > semver(installed)):
        installed = ver

expected = env.get("SKILL6_OPENCLAW_EXTENSION_EXPECTED_VERSION") or None
if expected:
    expected_source = "operator-pin"
else:
    expected_source = "unknown"
    home = env.get("HOME") or os.path.expanduser("~")
    oc_home = env.get("OPENCLAW_HOME") or os.path.join(home, ".openclaw")
    try:
        with open(os.path.join(oc_home, "browser", "chrome-extension",
                               "manifest.json")) as f:
            expected = str(json.load(f).get("version") or "") or None
        if expected:
            expected_source = "bundled-manifest"
    except Exception:
        expected = None

if roots_exist == 0 and expected is None:
    cannot_run("no Chrome profile root exists on disk and no "
               "expected-version source exists")

if JSON_MODE:
    if installed is None:
        current = False
    elif expected is None:
        current = "unknown"
    else:
        current = semver(installed) >= semver(expected)
    print(json.dumps({
        "installed": installed is not None,
        "version": installed,
        "expectedVersion": expected,
        "expectedSource": expected_source,
        "current": current,
        "lane": "openclaw-extension",
        "laneAvailable": installed is not None and current is not False,
    }))
else:
    print("INSTALLED=%s" % (installed or "none"))
    print("EXPECTED=%s" % (expected or "unknown"))
    print("EXPECTED_SOURCE=%s" % expected_source)
    print("ROOTS_EXIST=%d" % roots_exist)
PYEOF
)"
PROBE_RC=$?

if [ "$MODE" = "json" ]; then
  if [ "$PROBE_RC" -ne 0 ]; then
    echo "ERROR: the OpenClaw extension preflight could not run on this box (the embedded probe failed). No Lane 1 verdict was computed; this is not a Lane 1 failure." >&2
    exit 2
  fi
  case "$RESULT" in
    "{"*)
      printf '%s\n' "$RESULT"
      exit 0
      ;;
    *)
      echo "ERROR: the OpenClaw extension preflight could not run on this box (the embedded probe output could not be parsed). No Lane 1 verdict was computed; this is not a Lane 1 failure." >&2
      exit 2
      ;;
  esac
fi

if [ "$PROBE_RC" -ne 0 ]; then
  echo "ERROR: the OpenClaw extension preflight could not run on this box (the embedded probe failed). No Lane 1 verdict was computed; this is not a Lane 1 failure." >&2
  exit 1
fi

INSTALLED="$(printf '%s\n' "$RESULT" | sed -n 's/^INSTALLED=//p')"
EXPECTED="$(printf '%s\n' "$RESULT" | sed -n 's/^EXPECTED=//p')"

if [ -z "$INSTALLED" ] || [ -z "$EXPECTED" ]; then
  echo "ERROR: the OpenClaw extension preflight could not run on this box (the embedded probe output could not be parsed). No Lane 1 verdict was computed; this is not a Lane 1 failure." >&2
  exit 1
fi

if [ "$INSTALLED" = "none" ]; then
  echo "LANE 1 UNAVAILABLE: the OpenClaw Chrome extension is NOT installed in any Chrome profile on this box."
  echo "Only the extension lane (Lane 1) is disabled. Skill 6 continues on the next lane the capability probe verifies; the run stops only if no lane verifies."
  echo "Fix (restores Lane 1): install it from the Chrome Web Store into the Chrome profile OpenClaw is paired with:"
  echo "  $STORE_URL"
  echo "Then re-run this check: bash scripts/check-openclaw-extension-version.sh"
  exit 2
fi

if [ "$EXPECTED" = "unknown" ]; then
  echo "OK (with warning): OpenClaw Chrome extension v$INSTALLED is installed."
  echo "This box cannot prove the newest version (no operator pin and no bundled"
  echo "extension manifest in the local OpenClaw install). Confirm currency against"
  echo "the Chrome Web Store listing when you can: $STORE_URL"
  exit 0
fi

# Numeric compare via python3 (string compare would rank 2.10.0 below 2.3.0).
CURRENT="$(python3 -c '
import sys
def sv(v):
    out = []
    for p in str(v).split("."):
        try: out.append(int(p))
        except ValueError: out.append(0)
    return out
print("1" if sv(sys.argv[1]) >= sv(sys.argv[2]) else "0")
' "$INSTALLED" "$EXPECTED")"

if [ "$CURRENT" = "1" ]; then
  echo "OK: OpenClaw Chrome extension v$INSTALLED is installed and current (expected v$EXPECTED)."
  exit 0
fi

echo "LANE 1 UNAVAILABLE: the OpenClaw Chrome extension is behind: installed v$INSTALLED, current is v$EXPECTED."
echo "Only the extension lane (Lane 1) is disabled. Skill 6 continues on the next lane the capability probe verifies; the run stops only if no lane verifies."
echo "Fix (restores Lane 1): let Chrome update it (chrome://extensions, or remove and reinstall from the Web Store):"
echo "  $STORE_URL"
echo "Then re-run this check: bash scripts/check-openclaw-extension-version.sh"
exit 2
