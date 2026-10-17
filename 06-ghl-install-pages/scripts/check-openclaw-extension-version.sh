#!/usr/bin/env bash
# check-openclaw-extension-version.sh — Skill 06 standing preflight:
# the OpenClaw Chrome extension must be installed AND current before any
# install run, because the extension is Skill 6's PRIMARY browser engine
# (operator decision, 2026-10-13).
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
# Exit codes: 0 = installed and current; 2 = missing or behind (STOP);
# 1 = the check itself could not run (no python3).
#
# Usage: bash scripts/check-openclaw-extension-version.sh

set -u

EXTENSION_ID="kcdjddhmeafeomebliikmbpblkmkfoig"
STORE_URL="https://chromewebstore.google.com/detail/openclaw/${EXTENSION_ID}"

if ! command -v python3 >/dev/null 2>&1; then
  echo "ERROR: python3 not found; cannot run the OpenClaw extension preflight." >&2
  exit 1
fi

RESULT="$(python3 - << 'PYEOF'
import glob, json, os, platform

EXT_ID = "kcdjddhmeafeomebliikmbpblkmkfoig"

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

env = dict(os.environ)
installed = None
for root in roots(env):
    ver = version_in(root)
    if ver and (installed is None or semver(ver) > semver(installed)):
        installed = ver

expected = env.get("SKILL6_OPENCLAW_EXTENSION_EXPECTED_VERSION") or None
if not expected:
    home = env.get("HOME") or os.path.expanduser("~")
    oc_home = env.get("OPENCLAW_HOME") or os.path.join(home, ".openclaw")
    try:
        with open(os.path.join(oc_home, "browser", "chrome-extension",
                               "manifest.json")) as f:
            expected = str(json.load(f).get("version") or "") or None
    except Exception:
        expected = None

print("INSTALLED=%s" % (installed or "none"))
print("EXPECTED=%s" % (expected or "unknown"))
PYEOF
)"

INSTALLED="$(printf '%s\n' "$RESULT" | sed -n 's/^INSTALLED=//p')"
EXPECTED="$(printf '%s\n' "$RESULT" | sed -n 's/^EXPECTED=//p')"

if [ "$INSTALLED" = "none" ] || [ -z "$INSTALLED" ]; then
  echo "STOP: the OpenClaw Chrome extension is NOT installed in any Chrome profile on this box."
  echo "Skill 6's PRIMARY browser engine is that extension, so no install run can start."
  echo "Fix: install it from the Chrome Web Store into the Chrome profile OpenClaw is paired with:"
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

echo "STOP: the OpenClaw Chrome extension is behind: installed v$INSTALLED, current is v$EXPECTED."
echo "Skill 6's PRIMARY browser engine must be current before an install run."
echo "Fix: let Chrome update it (chrome://extensions, or remove and reinstall from the Web Store):"
echo "  $STORE_URL"
echo "Then re-run this check: bash scripts/check-openclaw-extension-version.sh"
exit 2
