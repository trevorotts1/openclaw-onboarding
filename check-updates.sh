#!/usr/bin/env bash
# ============================================================
#  OpenClaw Onboarding — Check for Updates (READ-ONLY)
#  Compares local install against GitHub. NEVER installs anything.
#  Outputs structured JSON the cron agent reasons over.
#
#  Run via: curl -fsSL https://raw.githubusercontent.com/trevorotts1/openclaw-onboarding/main/check-updates.sh | bash
#  Or directly: bash ~/.openclaw/skills/check-updates.sh
# ============================================================

set -u
SCRIPT_VERSION="1.0.0"

#=== BEGIN APPROVED-RELEASE-TARGET-V1 ===
# ----------------------------------------------------------
#  APPROVED IMMUTABLE RELEASE TARGET -- selectable, OFF by default.
#
#  Every fetch in this file used to take whatever `main` happened to be at
#  run time. This block lets a box honour ONE explicitly approved release
#  identity instead: a release tag (`v27.1.66`) or a full 40-hex commit.
#
#  Trevor has not decided whether an approved pinned release should reach
#  clients automatically, so this is SELECTABLE and inert until turned on:
#
#    OPENCLAW_RELEASE_PIN_MODE=off      (default) exactly the old behaviour
#    OPENCLAW_RELEASE_PIN_MODE=prefer   use the target when one is configured,
#                                       else continue on the moving branch
#                                       after printing the reason code
#    OPENCLAW_RELEASE_PIN_MODE=require  refuse the update (exit 78) with a
#                                       named reason code when no usable
#                                       approved target is configured
#
#  Target source, first one that answers:
#    1. $OPENCLAW_APPROVED_RELEASE
#    2. <openclaw root>/approved-release -- line 1 = tag or full 40-hex
#       commit, optional line 2 = off|prefer|require. This file is what a
#       cron-run update can see; cron does not inherit an operator's env.
#
#  Reason codes (stable, greppable): RELEASE_TARGET_UNSET,
#  RELEASE_TARGET_INVALID, RELEASE_TARGET_MISSING.
# ----------------------------------------------------------
_OC_REL_MODE="${OPENCLAW_RELEASE_PIN_MODE:-}"
_OC_REL_TARGET="${OPENCLAW_APPROVED_RELEASE:-}"
# ONE pin surface: read the SAME fleet-refresh/release-pin.json that
# update-skills.sh, fleet-refresh.sh, weekly-full-update.sh and
# oc-atomic-upgrade.sh read. This detector used to read only a divergent
# legacy text file nothing else wrote, so a canonical pin was invisible here.
if [ -z "$_OC_REL_MODE" ] || [ -z "$_OC_REL_TARGET" ]; then
  _oc_rel_pin_file="${OPENCLAW_RELEASE_PIN_FILE:-}"
  if [ -z "$_oc_rel_pin_file" ]; then
    _oc_rel_root="${OPENCLAW_ROOT:-}"
    [ -n "$_oc_rel_root" ] || { [ -d /data/.openclaw ] && _oc_rel_root=/data/.openclaw; }
    [ -n "$_oc_rel_root" ] || _oc_rel_root="$HOME/.openclaw"
    _oc_rel_pin_file="$_oc_rel_root/fleet-refresh/release-pin.json"
  fi
  if [ -r "$_oc_rel_pin_file" ] && command -v python3 >/dev/null 2>&1; then
    if [ -z "$_OC_REL_TARGET" ]; then
      _OC_REL_TARGET="$(python3 -I -c 'import json,sys
try: v=json.load(open(sys.argv[1])).get("approved_ref")
except Exception: v=None
print(v if isinstance(v,str) else "")' "$_oc_rel_pin_file" 2>/dev/null | tr -d '[:space:]' || true)"
    fi
    if [ -z "$_OC_REL_MODE" ]; then
      _OC_REL_MODE="$(python3 -I -c 'import json,sys
try: v=json.load(open(sys.argv[1])).get("mode")
except Exception: v=None
print(v if isinstance(v,str) else "")' "$_oc_rel_pin_file" 2>/dev/null | tr -d '[:space:]' || true)"
    fi
  fi
fi
# Legacy plaintext fallback (approved-release), kept for boxes that predate
# release-pin.json. The canonical json above wins when both are present.
if [ -z "$_OC_REL_MODE" ] || [ -z "$_OC_REL_TARGET" ]; then
  for _oc_rel_f in /data/.openclaw/approved-release "$HOME/.openclaw/approved-release"; do
    [ -f "$_oc_rel_f" ] || continue
    { IFS= read -r _oc_rel_l1 || true; IFS= read -r _oc_rel_l2 || true; } < "$_oc_rel_f"
    if [ -z "$_OC_REL_TARGET" ]; then _OC_REL_TARGET="$(printf '%s' "${_oc_rel_l1:-}" | tr -d '[:space:]')"; fi
    if [ -z "$_OC_REL_MODE" ];   then _OC_REL_MODE="$(printf '%s' "${_oc_rel_l2:-}" | tr -d '[:space:]')"; fi
    break
  done
fi
_OC_REL_MODE="${_OC_REL_MODE:-off}"
# Vocabulary bridge: the canonical modes are enforce|advisory|off. This
# resolver speaks require|prefer|off under the SAME env var, so a box pinned
# with canonical "enforce"/"advisory" used to abort here with exit 78.
case "$_OC_REL_MODE" in
  enforce)  _OC_REL_MODE="require" ;;
  advisory) _OC_REL_MODE="prefer" ;;
esac
_OC_REL_REF="main"     # the moving default branch: unchanged behaviour
case "$_OC_REL_MODE" in
  off|prefer|require) : ;;
  *) echo "ERROR (release-pin): OPENCLAW_RELEASE_PIN_MODE='$_OC_REL_MODE' is not one of off|prefer|require." >&2
     echo "RELEASE_TARGET_INVALID" >&2; exit 78 ;;
esac
if [ "$_OC_REL_MODE" != "off" ]; then
  if [ -z "$_OC_REL_TARGET" ]; then
    echo "RELEASE_TARGET_UNSET: no approved release target configured (OPENCLAW_RELEASE_PIN_MODE=$_OC_REL_MODE)" >&2
    [ "$_OC_REL_MODE" = "require" ] && exit 78
  else
    case "$_OC_REL_TARGET" in
      *[!0-9A-Za-z._-]*)
        echo "RELEASE_TARGET_INVALID: '$_OC_REL_TARGET' carries characters a ref cannot" >&2
        [ "$_OC_REL_MODE" = "require" ] && exit 78 ;;
      [0-9a-f][0-9a-f]*)
        # A commit target must be the FULL 40-hex id: a short sha is ambiguous.
        if [ "${#_OC_REL_TARGET}" -eq 40 ]; then
          _OC_REL_REF="$_OC_REL_TARGET"
        else
          echo "RELEASE_TARGET_INVALID: '$_OC_REL_TARGET' is not a full 40-hex commit" >&2
          [ "$_OC_REL_MODE" = "require" ] && exit 78
        fi ;;
      v[0-9]*)
        _OC_REL_REF="$_OC_REL_TARGET" ;;
      *)
        echo "RELEASE_TARGET_INVALID: '$_OC_REL_TARGET' is neither a v<digit> release tag nor a full 40-hex commit" >&2
        [ "$_OC_REL_MODE" = "require" ] && exit 78 ;;
    esac
  fi
fi
# RELEASE_TARGET_MISSING is raised where the target is resolved against the
# remote (a failed git fetch, or an HTTP 404 below).
#=== END APPROVED-RELEASE-TARGET-V1 ===

# ----------------------------------------------------------
# Detect platform (Mac vs VPS) — determines all paths
# ----------------------------------------------------------
if [ -d "/data/.openclaw" ]; then
  PLATFORM="vps"
  REPO_NAME="openclaw-onboarding"
  SKILLS_DIR="/data/.openclaw/skills"
  MASTER_DIR="/data/Downloads/openclaw-master-files"
  WORKSPACE="/data/clawd"
else
  PLATFORM="mac"
  REPO_NAME="openclaw-onboarding"
  SKILLS_DIR="$HOME/.openclaw/skills"
  MASTER_DIR="$HOME/Downloads/openclaw-master-files"
  WORKSPACE="$HOME/clawd"
fi

# ----------------------------------------------------------
# Fetch helpers
# ----------------------------------------------------------
GH_RAW="https://raw.githubusercontent.com/trevorotts1/${REPO_NAME}/${_OC_REL_REF}"

fetch_remote() {
  # $1 = path relative to repo root. Returns content or empty on 404.
  curl -fsSL --max-time 15 "${GH_RAW}/$1" 2>/dev/null || echo ""
}

# ----------------------------------------------------------
# Read local state
# ----------------------------------------------------------
LOCAL_VERSION=""
if [ -f "$SKILLS_DIR/.onboarding-version" ]; then
  LOCAL_VERSION=$(tr -d '[:space:]' < "$SKILLS_DIR/.onboarding-version")
fi

# Build local skill version map
LOCAL_SKILLS_TMP=$(mktemp)
if [ -d "$SKILLS_DIR" ]; then
  for d in "$SKILLS_DIR"/[0-9]*; do
    [ -d "$d" ] || continue
    name=$(basename "$d")
    case "$name" in *ARCHIVED*) continue ;; esac
    ver=""
    [ -f "$d/skill-version.txt" ] && ver=$(tr -d '[:space:]' < "$d/skill-version.txt")
    echo "$name|$ver" >> "$LOCAL_SKILLS_TMP"
  done
fi

# ----------------------------------------------------------
# Fetch remote state
# ----------------------------------------------------------
LATEST_VERSION=$(fetch_remote version | tr -d '[:space:]')
LATEST_CHANGELOG=$(fetch_remote CHANGELOG.md)
# The selector is honoured for EVERY fetch in this file (the raw base and the
# tree API both use _OC_REL_REF), so a pinned cohort is never swapped for
# whatever main holds at refresh time. A target that cannot be resolved is a
# named absence: `require` refuses the run, `prefer` states it and continues.
if [ -z "$LATEST_VERSION" ] && [ "$_OC_REL_MODE" != "off" ]; then
  echo "RELEASE_TARGET_MISSING: approved target '$_OC_REL_REF' could not be fetched (version came back empty)" >&2
  [ "$_OC_REL_MODE" = "require" ] && exit 78
fi

# Pull just the most recent changelog entry (top section until next heading).
# Matches BOTH heading formats used historically:
#   ## v10.6.2 — ...        (older entries)
#   ## [v10.7.0] — ...      (current bracketed style, since v10.6.2 release)
LATEST_ENTRY=""
if [ -n "$LATEST_CHANGELOG" ]; then
  LATEST_ENTRY=$(echo "$LATEST_CHANGELOG" | awk '
    /^## (\[v|v)/ {
      if (count == 0) { count=1; print; next }
      else { exit }
    }
    count == 1 { print }
  ')
fi

# Pull risk hint if changelog uses "### Risk: low|medium|high" tag
RISK_HINT=""
if [ -n "$LATEST_ENTRY" ]; then
  RISK_HINT=$(echo "$LATEST_ENTRY" | grep -iE "^### Risk:" | head -1 | sed -E 's/^### Risk:[[:space:]]*//I' | tr -d '[:space:]' | tr '[:upper:]' '[:lower:]')
fi

# ----------------------------------------------------------
# Fetch the remote skill manifest (list of skill folders + their versions)
# We hit the GitHub git/trees API for a one-shot listing
# ----------------------------------------------------------
REMOTE_SKILLS_TMP=$(mktemp)
TREE_JSON=$(curl -fsSL --max-time 15 "https://api.github.com/repos/trevorotts1/${REPO_NAME}/git/trees/${_OC_REL_REF}" 2>/dev/null)
if [ -n "$TREE_JSON" ]; then
  echo "$TREE_JSON" | python3 -c "
import json,sys,re
try:
    d=json.load(sys.stdin)
    for t in d.get('tree',[]):
        n=t.get('path','')
        if t.get('type')=='tree' and re.match(r'^[0-9]+-', n) and 'ARCHIVED' not in n:
            print(n)
except: pass
" 2>/dev/null > "${REMOTE_SKILLS_TMP}.names"

  # For each remote skill, fetch its skill-version.txt
  while IFS= read -r skill_name; do
    [ -z "$skill_name" ] && continue
    remote_ver=$(curl -fsSL --max-time 10 "${GH_RAW}/${skill_name}/skill-version.txt" 2>/dev/null | tr -d '[:space:]')
    echo "${skill_name}|${remote_ver}" >> "$REMOTE_SKILLS_TMP"
  done < "${REMOTE_SKILLS_TMP}.names"
  rm -f "${REMOTE_SKILLS_TMP}.names"
fi

# ----------------------------------------------------------
# Compose skill_changes array
# ----------------------------------------------------------
SKILL_CHANGES_JSON=""
HAS_SKILL_UPDATES="false"

if [ -s "$REMOTE_SKILLS_TMP" ]; then
  while IFS='|' read -r remote_name remote_ver; do
    [ -z "$remote_name" ] && continue
    local_ver=$(grep "^${remote_name}|" "$LOCAL_SKILLS_TMP" 2>/dev/null | cut -d'|' -f2 | head -1)
    is_new="false"
    has_upd="false"
    if [ -z "$local_ver" ]; then
      is_new="true"
      has_upd="true"
      HAS_SKILL_UPDATES="true"
    elif [ "$local_ver" != "$remote_ver" ]; then
      has_upd="true"
      HAS_SKILL_UPDATES="true"
    fi
    if [ -n "$SKILL_CHANGES_JSON" ]; then SKILL_CHANGES_JSON="$SKILL_CHANGES_JSON,"; fi
    SKILL_CHANGES_JSON="${SKILL_CHANGES_JSON}{\"name\":\"${remote_name}\",\"local\":\"${local_ver}\",\"latest\":\"${remote_ver}\",\"is_new\":${is_new},\"has_update\":${has_upd}}"
  done < "$REMOTE_SKILLS_TMP"
fi

# ----------------------------------------------------------
# Compose final JSON
# ----------------------------------------------------------
HAS_REPO_UPDATE="false"
if [ -n "$LATEST_VERSION" ] && [ "$LOCAL_VERSION" != "$LATEST_VERSION" ]; then
  HAS_REPO_UPDATE="true"
fi

# A4: Content-verification — read .onboarding-content-manifest.json and check
# whether the on-box installed content matches the recorded manifest for the
# stamped version. If it does not, force has_skill_updates=true even when
# the version strings match (the half-applied-box symptom: stamp matches, content drifted).
#
# F24: an EMPTY or INCOMPLETE recorded skill map is never "verified". The old
# check was self-consistent with whatever entries happened to be recorded, so a
# manifest carrying `"skills": {}` reported content_verified=true and the box was
# called updated with nothing proven. The check now needs the EXPECTED closure
# (every installed numbered skill recorded) plus a per-skill digest; a digest
# mismatch, a recorded-but-absent tree, an installed-but-unrecorded tree, a
# missing recorded version or an unreadable manifest is a named finding and
# content_verified stays false.
CONTENT_VERIFIED="false"
CONTENT_VERIFY_REASON=""
CONTENT_DRIFT_SKILLS_JSON=""
_MANIFEST_FILE="$SKILLS_DIR/.onboarding-content-manifest.json"
if [ -f "$_MANIFEST_FILE" ] && command -v python3 >/dev/null 2>&1; then
  _CONTENT_CHECK=$(python3 - "$_MANIFEST_FILE" "$SKILLS_DIR" <<'PYEOF'
import json, hashlib, os, sys
from pathlib import Path

manifest_path = sys.argv[1]
skills_dir = sys.argv[2]

try:
    manifest = json.load(open(manifest_path))
except Exception as e:
    print(f"incomplete:manifest_unreadable:{type(e).__name__}")
    sys.exit(0)

if not isinstance(manifest, dict):
    print("incomplete:manifest_not_an_object")
    sys.exit(0)

recorded_version = manifest.get("version", "")
recorded_skills = manifest.get("skills", {})

# An empty/absent map is a stated absence, never a pass: nothing is proven about
# the installed content, so this box cannot be called verified or updated.
if not isinstance(recorded_skills, dict) or not recorded_skills:
    print("incomplete:empty_skill_record")
    sys.exit(0)
if not isinstance(recorded_version, str) or not recorded_version.strip():
    print("incomplete:no_recorded_version")
    sys.exit(0)

unrecorded_digests = sorted(
    name for name, digest in recorded_skills.items()
    if not isinstance(digest, str) or not digest.strip())
if unrecorded_digests:
    print("incomplete:no_recorded_digest:" + ",".join(unrecorded_digests))
    sys.exit(0)

# The expected closure: every installed numbered skill (ARCHIVED excluded) must
# be recorded, or the record describes a different box than the one on disk.
installed = set()
try:
    for entry in Path(skills_dir).iterdir():
        if entry.is_dir() and entry.name[:1].isdigit() and "ARCHIVED" not in entry.name:
            installed.add(entry.name)
except OSError as e:
    print(f"incomplete:skills_dir_unreadable:{type(e).__name__}")
    sys.exit(0)
if not installed:
    print("incomplete:no_installed_skills")
    sys.exit(0)
unrecorded_installed = sorted(installed - set(recorded_skills))
if unrecorded_installed:
    print("incomplete:skills_not_recorded:" + ",".join(unrecorded_installed))
    sys.exit(0)

# Check SHA tool
import subprocess
sha_cmd = None
for cmd in [["shasum", "-a", "256"], ["sha256sum"]]:
    try:
        r = subprocess.run(cmd + ["/dev/null"], capture_output=True, timeout=5)
        if r.returncode == 0:
            sha_cmd = cmd
            break
    except Exception:
        pass

if sha_cmd is None:
    print("no_sha_tool")
    sys.exit(0)

drift = []
for skill_name, recorded_digest in recorded_skills.items():
    skill_dir = Path(skills_dir) / skill_name
    if not skill_dir.is_dir():
        drift.append(f"{skill_name}:missing")
        continue

    exclude_names = {".wired-", "skill-version.txt", ".onboarding-version",
                     ".onboarding-content-manifest.json"}
    exclude_suffixes = (".bak",)

    file_hash_input = []
    for fpath in sorted(skill_dir.rglob("*")):
        if not fpath.is_file():
            continue
        # exclude volatile files
        skip = False
        for ex in exclude_names:
            if fpath.name.startswith(ex) or fpath.name == ex:
                skip = True; break
        if fpath.suffix in exclude_suffixes:
            skip = True
        if ".git" in fpath.parts:
            skip = True
        if skip:
            continue

        rel = str(fpath.relative_to(skill_dir))
        r = subprocess.run(sha_cmd + [str(fpath)], capture_output=True, text=True, timeout=10)
        file_digest = r.stdout.split()[0] if r.returncode == 0 else "error"
        file_hash_input.append(f"{rel}:{file_digest}")

    combined = "\n".join(sorted(file_hash_input)) + "\n"
    skill_digest = hashlib.sha256(combined.encode()).hexdigest()

    if skill_digest != recorded_digest:
        drift.append(f"{skill_name}:digest_mismatch")

if drift:
    print("drift:" + ",".join(drift))
else:
    print("ok")
PYEOF
  2>/dev/null || echo "check_error")

  if [ "$_CONTENT_CHECK" = "ok" ]; then
    CONTENT_VERIFIED="true"
    CONTENT_VERIFY_REASON="closure_recorded_and_matched"
  elif [[ "$_CONTENT_CHECK" == incomplete:* ]]; then
    # The record cannot prove the installed content: an empty/incomplete skill
    # map, an absent digest, an unrecorded installed tree. That is NOT a verified
    # installation and NOT an updated one, so it drives the update flag.
    CONTENT_VERIFIED="false"
    CONTENT_VERIFY_REASON="${_CONTENT_CHECK#incomplete:}"
    _UNRECORDED_LIST="${CONTENT_VERIFY_REASON##*:}"
    case "$CONTENT_VERIFY_REASON" in
      skills_not_recorded:*) CONTENT_DRIFT_SKILLS_JSON=$(printf '%s' "$_UNRECORDED_LIST" | awk -F, '{printf "["; for(i=1;i<=NF;i++){printf "%s\"%s:not_recorded\"", (i>1?",":""), $i} print "]"}') ;;
      *) CONTENT_DRIFT_SKILLS_JSON="[]" ;;
    esac
    [ -z "$CONTENT_DRIFT_SKILLS_JSON" ] && CONTENT_DRIFT_SKILLS_JSON="[]"
    HAS_SKILL_UPDATES="true"
    HAS_REPO_UPDATE="true"
  elif [[ "$_CONTENT_CHECK" == drift:* ]]; then
    # Content drifted — force has_skill_updates even if version string matches
    CONTENT_VERIFIED="false"
    CONTENT_VERIFY_REASON="digest_mismatch_or_missing_tree"
    _DRIFT_LIST="${_CONTENT_CHECK#drift:}"
    # Build JSON array of drifted skills
    CONTENT_DRIFT_SKILLS_JSON=$(python3 -c "
import json, sys
items = sys.argv[1].split(',')
print(json.dumps(items))
" "$_DRIFT_LIST" 2>/dev/null || echo '[]')
    HAS_SKILL_UPDATES="true"
    HAS_REPO_UPDATE="true"  # treat content drift as needing an update
  else
    CONTENT_VERIFIED="false"  # check failed/unavailable — conservative
    CONTENT_VERIFY_REASON="check_unavailable_or_failed:${_CONTENT_CHECK}"
  fi
else
  # No manifest yet (first install) or python3 unavailable — a stated absence,
  # never a verified installation.
  CONTENT_VERIFIED="false"
  CONTENT_VERIFY_REASON="no_content_manifest"
fi
[ -z "$CONTENT_DRIFT_SKILLS_JSON" ] && CONTENT_DRIFT_SKILLS_JSON="[]"
[ -z "$CONTENT_VERIFY_REASON" ] && CONTENT_VERIFY_REASON="not_checked"

# ----------------------------------------------------------
# F24: the install report. Every installed skill is classified explicitly —
# PRESERVED (on disk, not in this release: kept, never replaced, and never
# called updated), CONFLICTING (installed at another version), MISSING (in the
# release, not installed), BLOCKED (installed but unreadable/unprovable) or
# UPDATED (same version AND content verified). "Fully updated" is only true when
# every one of those lists is empty and the content record proved the closure.
# An unresolved remote fetch is stated, never read as "nothing to do".
# ----------------------------------------------------------
INSTALL_REPORT_JSON='{"available":false}'
FULLY_UPDATED="false"
_REMOTE_FETCH_STATUS="resolved"
[ -s "${REMOTE_SKILLS_TMP:-/dev/null}" ] || _REMOTE_FETCH_STATUS="unresolved"
if command -v python3 >/dev/null 2>&1; then
  INSTALL_REPORT_JSON=$(python3 - "$LOCAL_SKILLS_TMP" "$REMOTE_SKILLS_TMP" \
      "$CONTENT_VERIFIED" "$_REMOTE_FETCH_STATUS" <<'PYEOF'
import json, sys
from pathlib import Path

local_path, remote_path, content_verified, fetch_status = sys.argv[1:5]

def load(path):
    out = {}
    try:
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if "|" in line:
                name, _, version = line.partition("|")
                if name:
                    out[name] = version
    except OSError:
        pass
    return out

local, remote = load(local_path), load(remote_path)
report = {"available": True, "fetch_status": fetch_status,
          "preserved": [], "conflicting": [], "missing": [], "blocked": [],
          "updated": []}
if fetch_status != "resolved":
    # With no release list there is nothing to compare against: the installed set
    # is stated, and none of it is classified as updated, preserved or missing.
    report["unresolved_local"] = sorted(local)
for name, version in sorted(remote.items()):
    if name not in local:
        report["missing"].append(name)
        continue
    if not local[name]:
        report["blocked"].append(f"{name}:installed_version_unreadable")
    elif version and local[name] != version:
        report["conflicting"].append(name)
    elif not version:
        report["blocked"].append(f"{name}:remote_version_unreadable")
    else:
        report["updated"].append(name)
# A skill on disk that this release does not carry is PRESERVED: a client-only
# or locally added tree. It is reported, never deleted, and never called updated.
if fetch_status == "resolved":
    for name in sorted(set(local) - set(remote)):
        report["preserved"].append(name)
if content_verified != "true":
    # The version strings alone never prove an installation: without the recorded
    # closure the "updated" list is a version comparison, so nothing may claim it.
    report["updated_version_only"] = list(report["updated"])
    report["updated"] = []
report["fully_updated"] = bool(
    content_verified == "true" and fetch_status == "resolved"
    and not (report["preserved"] or report["conflicting"] or report["missing"]
             or report["blocked"]))
print(json.dumps(report))
PYEOF
  2>/dev/null || echo '{"available":false}')
fi
[ -z "$INSTALL_REPORT_JSON" ] && INSTALL_REPORT_JSON='{"available":false}'
FULLY_UPDATED=$(printf '%s' "$INSTALL_REPORT_JSON" | python3 -c \
  "import json,sys;print('true' if json.load(sys.stdin).get('fully_updated') else 'false')" \
  2>/dev/null || echo "false")
# A pending repo or skill update is never "fully updated", whatever the record says.
if [ "$HAS_REPO_UPDATE" = "true" ] || [ "$HAS_SKILL_UPDATES" = "true" ]; then
  FULLY_UPDATED="false"
fi

# ----------------------------------------------------------
# v12.27.0: PER-ARTIFACT staleness probe (role / dept / SOP). READ-ONLY.
# After a new library version lands in $SKILLS_DIR, this asks
# detect-stale-artifacts.py whether THIS client's built workforce is out of date
# vs the installed role-library content manifest — per ROLE, per DEPT, per SOP.
# The hash is canonical-source based, so this has zero per-client false positives.
# rc 10 + the --json item list become the refresh work queue that update-skills.sh
# re-instantiates. We surface a compact summary in the output JSON; the full item
# list is available by running the detector directly.
# ----------------------------------------------------------
ARTIFACT_STALENESS_JSON='{"available":false}'
_DETECT="$SKILLS_DIR/23-ai-workforce-blueprint/scripts/detect-stale-artifacts.py"
_AMANIFEST="$SKILLS_DIR/23-ai-workforce-blueprint/templates/role-library/_index.json"
if [ "$PLATFORM" = "vps" ]; then
  _OC_WORKSPACE="/data/.openclaw/workspace"
else
  _OC_WORKSPACE="$HOME/.openclaw/workspace"
fi
if [ -f "$_DETECT" ] && [ -f "$_AMANIFEST" ] && \
   { [ -d "$_OC_WORKSPACE/departments" ] || [ -f "$_OC_WORKSPACE/.workforce-build-state.json" ]; } && \
   command -v python3 >/dev/null 2>&1; then
  _DETECT_JSON=$(python3 "$_DETECT" --workspace "$_OC_WORKSPACE" --manifest "$_AMANIFEST" --json 2>/dev/null || echo "")
  if [ -n "$_DETECT_JSON" ]; then
    ARTIFACT_STALENESS_JSON=$(printf '%s' "$_DETECT_JSON" | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
except Exception:
    print('{\"available\":false}'); sys.exit(0)
s = d.get('summary', {})
stale_items = [i['key'] for i in d.get('items', []) if i.get('status') in ('STALE','MISSING','UNTRACKED','ORPHAN')]
out = {
    'available': True,
    'manifest_version': d.get('manifest_version'),
    'build_record_source': d.get('build_record_source'),
    'summary': s,
    'actionable': s.get('stale',0)+s.get('missing',0)+s.get('orphan',0)+s.get('untracked',0),
    'sample': stale_items[:25],
}
print(json.dumps(out))
" 2>/dev/null || echo '{"available":false}')
    # An out-of-date workforce is an update signal (drives the refresh flow).
    _ACTIONABLE=$(printf '%s' "$ARTIFACT_STALENESS_JSON" | python3 -c "import json,sys;print(json.load(sys.stdin).get('actionable',0))" 2>/dev/null || echo 0)
    if [ "${_ACTIONABLE:-0}" -gt 0 ] 2>/dev/null; then
      HAS_SKILL_UPDATES="true"
    fi
  fi
fi
[ -z "$ARTIFACT_STALENESS_JSON" ] && ARTIFACT_STALENESS_JSON='{"available":false}'

# Escape changelog excerpt for JSON
LATEST_ENTRY_JSON=$(printf '%s' "$LATEST_ENTRY" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read()))" 2>/dev/null)
[ -z "$LATEST_ENTRY_JSON" ] && LATEST_ENTRY_JSON='""'

cat <<JSON
{
  "script_version": "${SCRIPT_VERSION}",
  "repo": "${REPO_NAME}",
  "platform": "${PLATFORM}",
  "checked_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "local_version": "${LOCAL_VERSION}",
  "latest_version": "${LATEST_VERSION}",
  "has_repo_update": ${HAS_REPO_UPDATE},
  "has_skill_updates": ${HAS_SKILL_UPDATES},
  "risk_hint": "${RISK_HINT}",
  "changelog_excerpt": ${LATEST_ENTRY_JSON},
  "release_target": "${_OC_REL_REF}",
  "release_pin_mode": "${_OC_REL_MODE}",
  "skill_changes": [${SKILL_CHANGES_JSON}],
  "content_verified": ${CONTENT_VERIFIED},
  "content_verify_reason": "${CONTENT_VERIFY_REASON}",
  "content_drift_skills": ${CONTENT_DRIFT_SKILLS_JSON},
  "install_report": ${INSTALL_REPORT_JSON},
  "fully_updated": ${FULLY_UPDATED},
  "artifact_staleness": ${ARTIFACT_STALENESS_JSON}
}
JSON

# Cleanup
rm -f "$LOCAL_SKILLS_TMP" "$REMOTE_SKILLS_TMP"

# Mark when this check ran (for catchup detection in update-skills.sh)
mkdir -p "$(dirname "$SKILLS_DIR/.last-update-check")"
date -u +%Y-%m-%dT%H:%M:%SZ > "$SKILLS_DIR/.last-update-check" 2>/dev/null || true

# ----------------------------------------------------------
# N22 (triple-fire trigger, detection-side) — write the AGENTS.md flag
# whenever an update is detected. This fires on DETECTION, NOT only on
# force-update apply. The flag remains until the user replies (via the
# Sunday cron Telegram flow) or until next Sunday's check clears it.
# v10.12.0 P20.1: prior versions only wrote this flag from force-update.sh.
# ----------------------------------------------------------
# A4: also fires when content_verified=false (content drifted even with matching stamp)
if [ "$HAS_REPO_UPDATE" = "true" ] || [ "$HAS_SKILL_UPDATES" = "true" ]; then
  if [ "$PLATFORM" = "vps" ]; then
    AGENTS_MD="/data/.openclaw/AGENTS.md"
  else
    AGENTS_MD="$HOME/.openclaw/AGENTS.md"
  fi
  mkdir -p "$(dirname "$AGENTS_MD")" 2>/dev/null || true
  flag_marker="<!-- OPENCLAW_UPDATE_DETECTED:${LATEST_VERSION}:$(date -u +%Y-%m-%dT%H:%M:%SZ) -->"
  if [ -f "$AGENTS_MD" ] && grep -qF "OPENCLAW_UPDATE_DETECTED:${LATEST_VERSION}" "$AGENTS_MD" 2>/dev/null; then
    : # already flagged for this version
  else
    {
      echo ""
      echo "$flag_marker"
      echo "## OpenClaw update detected: ${LATEST_VERSION} (from ${LOCAL_VERSION})"
      echo "Repo: ${REPO_NAME}"
      echo "Risk hint: ${RISK_HINT:-unknown}"
      echo "Detected at $(date -u +%Y-%m-%dT%H:%M:%SZ) by check-updates.sh"
      echo "Status: PENDING_USER_REPLY — awaiting Telegram reply per Sunday cron RULE 6."
      echo "<!-- OPENCLAW_UPDATE_DETECTED_END -->"
    } >> "$AGENTS_MD" 2>/dev/null || true
  fi
fi
