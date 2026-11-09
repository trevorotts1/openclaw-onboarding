#!/usr/bin/env bash
# ============================================================
# check-ghl-hybrid-parity.sh — packaging parity gate (WFIN-021)
# ============================================================
#
# WHAT IT PROVES
#   P1  the packaging manifest names the version this tree actually is
#       (VERSION == manifest.package.version).
#   P2  for every skill the package covers, the manifest's recorded version
#       equals the skill's own declared version (skill-version.txt, else the
#       SKILL.md frontmatter).  A skill that changes without a manifest bump
#       fails here — the version and the manifest move together or not at all.
#   P3  the shipped verifier is the reviewed verifier: its sha256 equals the
#       one pinned in the manifest.
#   P4  INSTALLED == SOURCE, per covered skill, using the repo's own
#       skill-content-hash.sh digest (not a re-implementation of it).
#   P5  the CANDIDATE this package integrates against is live: the candidate is
#       younger than its own max_age_seconds AND every sha it records still
#       equals the branch tip live origin returns now.  A candidate that went
#       stale, even by one commit on one unit, fails here: building from it would
#       ship that unit behind.  The candidate is therefore self-invalidating —
#       it expires on its own clock and is re-checked against origin every run.
#
# A skill touched without its version bumped cannot pass: P2 reads the version
# the skill declares, so content changes that leave a stale version behind are
# caught by P4 on the installed side and by CI's own release gates on the
# source side.  Nothing here is an allowlist and nothing is skipped.
#
# Usage:
#   check-ghl-hybrid-parity.sh [--source DIR] [--installed DIR] [--manifest FILE]
#                               [--candidate FILE]
#
# Defaults: --source <repo root>, --installed $GHL_HYBRID_INSTALLED or
#           ~/.openclaw/skills, --manifest packaging/ghl-hybrid-manifest.json,
#           --candidate $GHL_HYBRID_CANDIDATE else integration/candidate.json
#           under the repo else ../../integration/candidate.json (run-root
#           layout: <run-root>/clones/<clone>/).
#
# P5 needs to read origin.  If `git ls-remote` cannot run, that is an
# environment failure (exit 2), never a pass: an unread candidate is not a
# live candidate.
#
# Exit: 0 parity holds, 1 parity failure, 2 usage/environment failure.
# ============================================================

set -uo pipefail   # NOT -e: every failure is named and reported, then summed.

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE="$REPO_ROOT"
INSTALLED="${GHL_HYBRID_INSTALLED:-$HOME/.openclaw/skills}"
MANIFEST="$REPO_ROOT/packaging/ghl-hybrid-manifest.json"
CANDIDATE="${GHL_HYBRID_CANDIDATE:-}"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --source)    [ "$#" -ge 2 ] || { echo "FAIL usage: --source needs a value" >&2; exit 2; }; SOURCE="$2"; shift 2 ;;
    --installed) [ "$#" -ge 2 ] || { echo "FAIL usage: --installed needs a value" >&2; exit 2; }; INSTALLED="$2"; shift 2 ;;
    --manifest)  [ "$#" -ge 2 ] || { echo "FAIL usage: --manifest needs a value" >&2; exit 2; }; MANIFEST="$2"; shift 2 ;;
    --candidate) [ "$#" -ge 2 ] || { echo "FAIL usage: --candidate needs a value" >&2; exit 2; }; CANDIDATE="$2"; shift 2 ;;
    -h|--help)   sed -n '2,52p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "FAIL usage: unknown argument '$1'" >&2; exit 2 ;;
  esac
done

FAILURES=0
fail() { echo "FAIL $*"; FAILURES=$((FAILURES + 1)); }
pass() { echo "PASS $*"; }

if [ ! -f "$MANIFEST" ]; then
  echo "FAIL environment: packaging manifest missing: $MANIFEST" >&2; exit 2
fi
if [ ! -f "$REPO_ROOT/scripts/skill-content-hash.sh" ]; then
  echo "FAIL environment: scripts/skill-content-hash.sh missing (the digest source)" >&2; exit 2
fi
if [ ! -d "$SOURCE" ]; then
  echo "FAIL environment: source root missing: $SOURCE" >&2; exit 2
fi
command -v python3 >/dev/null 2>&1 || {
  echo "FAIL environment: python3 absent; the manifest cannot be read" >&2; exit 2; }

# ── manifest projection: one tab-separated line per fact ───────────────────
MODE_TSV="$(python3 -I - "$MANIFEST" <<'PY'
import json, sys
try:
    m = json.load(open(sys.argv[1], encoding="utf-8"))
except Exception as exc:
    print("ERR\tmanifest\t%s: %s" % (type(exc).__name__, exc)); raise SystemExit(0)
print("PKG\t%s" % m.get("package", {}).get("version", ""))
print("VER\t%s\t%s" % (m.get("verifier", {}).get("path", ""),
                       m.get("verifier", {}).get("sha256", "")))
covered = m.get("covered_skills") or []
if not covered:
    print("ERR\tcovered_skills\tmanifest covers no skills")
for item in covered:
    print("SKILL\t%s\t%s" % (item.get("name", ""), item.get("version", "")))
PY
)" || { echo "FAIL environment: manifest projection failed" >&2; exit 2; }

PKG_VERSION=""; VER_PATH=""; VER_SHA=""; SKILL_NAMES=(); SKILL_VERS=()
while IFS=$'\t' read -r kind a b; do
  case "$kind" in
    PKG)   PKG_VERSION="$a" ;;
    VER)   VER_PATH="$a"; VER_SHA="$b" ;;
    SKILL) SKILL_NAMES+=("$a"); SKILL_VERS+=("$b") ;;
    ERR)   fail "manifest: $a ($b)" ;;
  esac
done <<< "$MODE_TSV"

# ── P1: repo version == manifest version ──────────────────────────────────
REPO_VERSION="$(tr -d '[:space:]' < "$REPO_ROOT/VERSION" 2>/dev/null || true)"
if [ -z "$REPO_VERSION" ]; then
  fail "P1 version-file missing: $REPO_ROOT/VERSION"
elif [ "$REPO_VERSION" = "$PKG_VERSION" ]; then
  pass "P1 package version pinned: $PKG_VERSION"
else
  fail "P1 version-drift: VERSION is $REPO_VERSION, manifest.package.version is ${PKG_VERSION:-<absent>}"
fi

# ── P3: the shipped verifier is the pinned verifier ───────────────────────
_sha256() {
  if command -v shasum >/dev/null 2>&1; then shasum -a 256 "$1" | awk '{print $1}'
  else sha256sum "$1" | awk '{print $1}'; fi
}
if [ -z "$VER_PATH" ] || [ -z "$VER_SHA" ]; then
  fail "P3 manifest records no verifier path/sha256"
elif [ ! -f "$REPO_ROOT/$VER_PATH" ]; then
  fail "P3 verifier missing: $VER_PATH"
else
  ACTUAL="$(_sha256 "$REPO_ROOT/$VER_PATH")"
  if [ "$ACTUAL" = "$VER_SHA" ]; then
    pass "P3 verifier pinned: $VER_PATH"
  else
    fail "P3 verifier-sha-drift: $VER_PATH is $ACTUAL, manifest pins $VER_SHA (re-pin after review)"
  fi
fi

# ── P2: manifest version == the skill's own declared version ──────────────
_declared_version() {
  local dir="$1"
  if [ -f "$dir/skill-version.txt" ]; then
    tr -d '[:space:]' < "$dir/skill-version.txt"; return 0
  fi
  if [ -f "$dir/SKILL.md" ]; then
    awk 'BEGIN{fm=0}
         /^---[[:space:]]*$/{fm++; next}
         fm==1 && /^[[:space:]]*version:/{sub(/^[[:space:]]*version:[[:space:]]*/,""); gsub(/["'\'']/,""); print; exit}' \
      "$dir/SKILL.md"
    return 0
  fi
  echo ""; return 0
}

if [ "${#SKILL_NAMES[@]}" -eq 0 ]; then
  fail "P2 manifest covers no skills"
fi
for i in "${!SKILL_NAMES[@]}"; do
  name="${SKILL_NAMES[$i]}"; want="${SKILL_VERS[$i]}"
  if [ ! -d "$SOURCE/$name" ]; then
    fail "P2 skill-missing-in-source: $name"
    continue
  fi
  got="$(_declared_version "$SOURCE/$name")"
  if [ -z "$got" ]; then
    fail "P2 skill-version-undeclared: $name has neither skill-version.txt nor a SKILL.md version"
  elif [ "$got" = "$want" ]; then
    pass "P2 $name version pinned: $got"
  else
    fail "P2 skill-version-drift: $name declares $got, manifest records ${want:-<absent>} (bump the skill and the manifest together)"
  fi
done

# ── P4: installed == source, per covered skill ────────────────────────────
if [ ! -d "$INSTALLED" ]; then
  fail "P4 installed-root-missing: $INSTALLED (nothing is installed to compare against)"
else
  TMP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/wfin021-parity.XXXXXX")" || {
    echo "FAIL environment: mktemp failed" >&2; exit 2; }
  # shellcheck disable=SC2064
  trap 'rm -rf "$TMP_ROOT"' EXIT

  mkdir -p "$TMP_ROOT/source" "$TMP_ROOT/installed"
  for name in "${SKILL_NAMES[@]:-}"; do
    [ -n "$name" ] || continue
    [ -d "$SOURCE/$name" ] && cp -R "$SOURCE/$name" "$TMP_ROOT/source/" 2>/dev/null
  done
  for name in "${SKILL_NAMES[@]:-}"; do
    [ -n "$name" ] || continue
    if [ -d "$INSTALLED/$name" ]; then
      cp -R "$INSTALLED/$name" "$TMP_ROOT/installed/" 2>/dev/null
    else
      fail "P4 installed-skill-missing: $name is not installed under $INSTALLED"
    fi
  done

  bash "$REPO_ROOT/scripts/skill-content-hash.sh" "$TMP_ROOT/source" > "$TMP_ROOT/source.hash" 2>"$TMP_ROOT/source.err"
  SRC_RC=$?
  bash "$REPO_ROOT/scripts/skill-content-hash.sh" "$TMP_ROOT/installed" > "$TMP_ROOT/installed.hash" 2>"$TMP_ROOT/installed.err"
  INST_RC=$?

  if [ "$SRC_RC" -ne 0 ]; then
    fail "P4 source-digest-failed rc=$SRC_RC: $(head -1 "$TMP_ROOT/source.err")"
  elif [ "$INST_RC" -ne 0 ]; then
    fail "P4 installed-digest-failed rc=$INST_RC: $(head -1 "$TMP_ROOT/installed.err")"
  else
    _digest_of() { awk -F'|' -v k="$2" '$1==k{print $2}' "$1"; }
    for name in "${SKILL_NAMES[@]}"; do
      [ -d "$INSTALLED/$name" ] || continue
      src="$(_digest_of "$TMP_ROOT/source.hash" "$name")"
      ins="$(_digest_of "$TMP_ROOT/installed.hash" "$name")"
      if [ -z "$src" ]; then
        fail "P4 source-digest-absent: $name produced no line"
      elif [ -z "$ins" ]; then
        fail "P4 installed-digest-absent: $name produced no line"
      elif [ "$src" = "$ins" ]; then
        pass "P4 installed==source: $name"
      else
        fail "P4 installed-parity: $name source ${src:0:16}… != installed ${ins:0:16}…"
      fi
    done
    # the tree rollup catches a skill that is installed but not covered
    SRC_TREE="$(awk -F'|' '$1=="__TREE_SHA__"{print $2}' "$TMP_ROOT/source.hash")"
    INST_TREE="$(awk -F'|' '$1=="__TREE_SHA__"{print $2}' "$TMP_ROOT/installed.hash")"
    if [ "$SRC_TREE" != "$INST_TREE" ]; then
      fail "P4 tree-rollup-drift: source ${SRC_TREE:0:16}… != installed ${INST_TREE:0:16}…"
    fi
  fi
fi

# ── P5: the integration candidate is live, not a snapshot of the past ──────
# A candidate goes stale silently: a unit pushes one second after the query and
# every consumer keeps building the old tip.  So the candidate carries its own
# expiry, and every sha it records is re-read from origin here.  Absence is
# recorded by the candidate itself (unit, exact ref checked, query, alternates),
# never inferred here.
P5_DIR="$(mktemp -d "${TMPDIR:-/tmp}/wfin021-candidate.XXXXXX")" || {
  echo "FAIL environment: mktemp failed" >&2; exit 2; }
# shellcheck disable=SC2064
trap 'rm -rf "$P5_DIR"' EXIT
# An explicit --candidate (or $GHL_HYBRID_CANDIDATE) IS the candidate: it is
# never replaced by a default when it is missing, or a caller asking for one
# file would silently be judged against another.
CAND_SOURCES=()
if [ -n "$CANDIDATE" ]; then
  CAND_SOURCES+=("$CANDIDATE")
else
  CAND_SOURCES+=("$REPO_ROOT/integration/candidate.json" "$REPO_ROOT/../../integration/candidate.json")
fi
CAND_FILE=""
for cand in "${CAND_SOURCES[@]}"; do
  if [ -f "$cand" ]; then CAND_FILE="$cand"; break; fi
done

if [ -z "$CAND_FILE" ]; then
  fail "P5 candidate-absent: no candidate at ${CAND_SOURCES[*]} (regenerate with scripts/gen-ghl-hybrid-candidate.sh --out <run-root>/integration/candidate.json)"
else
  git -C "$REPO_ROOT" ls-remote --heads origin > "$P5_DIR/live-refs" 2> "$P5_DIR/live-refs.err"
  P5_QUERY_RC=$?
  if [ "$P5_QUERY_RC" -ne 0 ] || [ ! -s "$P5_DIR/live-refs" ]; then
    echo "FAIL environment: P5 cannot read live origin (git ls-remote --heads origin rc=$P5_QUERY_RC): $(head -1 "$P5_DIR/live-refs.err")" >&2
    exit 2
  fi
  P5_TSV="$(python3 -I - "$CAND_FILE" "$P5_DIR/live-refs" "$(date -u +%s)" <<'PY'
import datetime, json, sys

cand_path, refs_path, now_raw = sys.argv[1], sys.argv[2], sys.argv[3]
EXPECTED_SCHEMA = "ghl-hybrid/integration-candidate/v2"
EXPECTED_UNITS = ["WF%02d" % i for i in range(36)]


def emit(kind, msg):
    print("%s\t%s" % (kind, msg))


try:
    now = int(now_raw)
except ValueError:
    emit("FAIL", "P5 clock: could not read the current time")
    raise SystemExit(0)

try:
    with open(cand_path, encoding="utf-8") as fh:
        candidate = json.load(fh)
except Exception as exc:
    emit("FAIL", "P5 candidate-unreadable: %s: %s" % (type(exc).__name__, exc))
    raise SystemExit(0)

if candidate.get("schema") != EXPECTED_SCHEMA:
    emit("FAIL", "P5 schema: expected %s, got %r (a candidate without max_age_seconds cannot expire)"
         % (EXPECTED_SCHEMA, candidate.get("schema")))
    raise SystemExit(0)

max_age = candidate.get("max_age_seconds")
if isinstance(max_age, bool) or not isinstance(max_age, int) or max_age <= 0:
    emit("FAIL", "P5 max_age_seconds: %r is not a positive integer, so the candidate cannot expire" % (max_age,))
    raise SystemExit(0)

stamp = candidate.get("generated_at")
age = None
if not isinstance(stamp, str) or not stamp.endswith("Z"):
    emit("FAIL", "P5 generated_at: %r is not an ISO-8601 UTC timestamp ending in Z" % (stamp,))
else:
    try:
        born = datetime.datetime.fromisoformat(stamp[:-1] + "+00:00")
        age = int(now - born.timestamp())
    except Exception as exc:
        emit("FAIL", "P5 generated_at: %r does not parse (%s)" % (stamp, exc))
if age is not None:
    if age < -300:
        emit("FAIL", "P5 generated_at: %s is %ds in the future (clock or file is wrong)" % (stamp, -age))
    elif age > max_age:
        emit("FAIL", "P5 candidate-stale: generated_at %s is %ds old, max_age_seconds is %d (regenerate before integrating)"
             % (stamp, age, max_age))
    else:
        emit("PASS", "P5 candidate fresh: generated_at %s, age %ds <= max_age_seconds %d" % (stamp, age, max_age))

refs = {}
try:
    with open(refs_path, encoding="utf-8") as fh:
        for line in fh:
            parts = line.split()
            if len(parts) == 2:
                refs[parts[1]] = parts[0]
except Exception as exc:
    emit("FAIL", "P5 live-refs-unreadable: %s: %s" % (type(exc).__name__, exc))
    raise SystemExit(0)

source = candidate.get("source") or {}
main_sha = source.get("main_sha")
main_ref = source.get("main_ref") or "refs/heads/main"
live_main = refs.get(main_ref)
if not isinstance(main_sha, str) or not main_sha:
    emit("FAIL", "P5 main: candidate records no %s sha" % main_ref)
elif live_main is None:
    emit("FAIL", "P5 main: origin returned no %s" % main_ref)
elif live_main == main_sha:
    emit("PASS", "P5 main tip live: %s %s" % (main_ref, main_sha[:12]))
else:
    emit("FAIL", "P5 candidate-main-drift: recorded %s, origin %s (%s)"
         % (main_sha[:12], live_main[:12], main_ref))

units = candidate.get("units") or []
names = [u.get("unit") for u in units if isinstance(u, dict)]
if names != EXPECTED_UNITS:
    emit("FAIL", "P5 units-coverage: candidate lists %d unit(s) %s, expected WF00..WF35 in order with none omitted"
         % (len(names), names[:6]))
else:
    emit("PASS", "P5 units-coverage: all 36 units WF00..WF35 recorded")

drift = 0
for entry in units:
    if not isinstance(entry, dict):
        emit("FAIL", "P5 unit-entry: %r is not an object" % (entry,))
        drift += 1
        continue
    unit = entry.get("unit")
    state = entry.get("state")
    branch = entry.get("branch")
    sha = entry.get("sha")
    ref_checked = entry.get("ref_checked")
    if state == "present":
        if not isinstance(branch, str) or not branch or not isinstance(sha, str) or not sha:
            emit("FAIL", "P5 %s present: records no branch and sha" % unit)
            drift += 1
            continue
        ref = "refs/heads/" + branch
        live = refs.get(ref)
        if live is None:
            emit("FAIL", "P5 %s candidate-ref-vanished: %s is no longer on origin" % (unit, ref))
            drift += 1
        elif live != sha:
            emit("FAIL", "P5 %s candidate-sha-drift: recorded %s, origin %s (%s)"
                 % (unit, sha[:12], live[:12], ref))
            drift += 1
        else:
            emit("PASS", "P5 %s tip live: %s %s" % (unit, ref, sha[:12]))
    elif state == "absent":
        ref = ref_checked
        if not isinstance(ref, str) or not ref:
            ref = "refs/heads/" + branch if isinstance(branch, str) and branch else None
        if not isinstance(entry.get("searched"), str) or not entry.get("searched"):
            emit("FAIL", "P5 %s absent: records no query it was searched under" % unit)
            drift += 1
        elif ref is not None and ref in refs:
            emit("FAIL", "P5 %s candidate-absent-but-live: %s now exists at %s"
                 % (unit, ref, refs[ref][:12]))
            drift += 1
        else:
            emit("PASS", "P5 %s still absent: %s not on origin" % (unit, ref or "<no ref recorded>"))
    else:
        emit("FAIL", "P5 %s state: %r is neither present nor absent" % (unit, state))
        drift += 1

present = sum(1 for u in units if isinstance(u, dict) and u.get("state") == "present")
absent = sum(1 for u in units if isinstance(u, dict) and u.get("state") == "absent")
counts = candidate.get("candidate") or {}
if counts.get("units_present") != present or counts.get("units_absent") != absent:
    emit("FAIL", "P5 unit-counts: candidate says %r present / %r absent, its units array holds %d present / %d absent"
         % (counts.get("units_present"), counts.get("units_absent"), present, absent))
    drift += 1

if drift == 0 and names == EXPECTED_UNITS:
    emit("PASS", "P5 candidate is live: %d unit(s) re-read from origin, none drifted" % len(units))
PY
)" || { echo "FAIL environment: P5 candidate projection failed" >&2; exit 2; }

  while IFS=$'\t' read -r p5_kind p5_msg; do
    case "$p5_kind" in
      PASS) pass "$p5_msg" ;;
      FAIL) fail "$p5_msg" ;;
      "")   ;;
      *)    fail "P5 projection emitted an unknown record '$p5_kind'" ;;
    esac
  done <<< "$P5_TSV"
fi

echo
if [ "$FAILURES" -ne 0 ]; then
  echo "FAIL harness: $FAILURES packaging parity failure(s)"
  exit 1
fi
echo "OK: packaging parity holds (source == installed for every covered skill)"
exit 0
