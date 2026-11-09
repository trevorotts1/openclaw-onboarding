#!/usr/bin/env bash
# ============================================================
# gen-ghl-hybrid-candidate.sh — regenerate the integration candidate
# ============================================================
#
# WHAT IT DOES
#   Re-reads EVERY unit branch tip from live origin (`git ls-remote --heads
#   origin`) and writes integration/candidate.json, the named candidate the
#   packaging gate (scripts/check-ghl-hybrid-parity.sh, P5) verifies against.
#   Nothing is copied from an earlier candidate: the only input is origin, read
#   at run time.  A unit with no branch is recorded ABSENT with the exact ref
#   that was checked, the query that was run and any alternate refs found — no
#   unit is ever silently omitted.
#
# WHY IT EXISTS
#   The candidate went stale once by 12 seconds: it was written at 03:08:29Z and
#   WF30 pushed its next commit at 03:08:41Z, so every consumer built WF30 one
#   commit behind.  The candidate now carries its own expiry (generated_at +
#   max_age_seconds) and P5 re-reads origin, so a stale or superseded candidate
#   fails the gate instead of shipping.  Regenerate with this script before
#   integrating — never hand-edit a sha.
#
# Usage:
#   gen-ghl-hybrid-candidate.sh [--out FILE] [--max-age SECONDS] [--prefix P]
#                                [--repo OWNER/NAME] [--remote NAME]
#
# Defaults: --out <repo root>/integration/candidate.json, --max-age 86400,
#           --prefix ghl-hybrid/r3-20261108, --remote origin, --repo derived
#           from the remote URL.
#
# Exit: 0 written, 2 usage or environment failure (including unreadable origin).
# ============================================================

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="$REPO_ROOT/integration/candidate.json"
MAX_AGE=86400
PREFIX="ghl-hybrid/r3-20261108"
REMOTE="origin"
SLUG=""

while [ "$#" -gt 0 ]; do
  case "$1" in
    --out)     [ "$#" -ge 2 ] || { echo "FAIL usage: --out needs a value" >&2; exit 2; }; OUT="$2"; shift 2 ;;
    --max-age) [ "$#" -ge 2 ] || { echo "FAIL usage: --max-age needs a value" >&2; exit 2; }; MAX_AGE="$2"; shift 2 ;;
    --prefix)  [ "$#" -ge 2 ] || { echo "FAIL usage: --prefix needs a value" >&2; exit 2; }; PREFIX="$2"; shift 2 ;;
    --repo)    [ "$#" -ge 2 ] || { echo "FAIL usage: --repo needs a value" >&2; exit 2; }; SLUG="$2"; shift 2 ;;
    --remote)  [ "$#" -ge 2 ] || { echo "FAIL usage: --remote needs a value" >&2; exit 2; }; REMOTE="$2"; shift 2 ;;
    -h|--help) sed -n '2,38p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "FAIL usage: unknown argument '$1'" >&2; exit 2 ;;
  esac
done

case "$MAX_AGE" in
  ''|*[!0-9]*) echo "FAIL usage: --max-age must be a positive integer, got '$MAX_AGE'" >&2; exit 2 ;;
esac
[ "$MAX_AGE" -gt 0 ] || { echo "FAIL usage: --max-age must be positive" >&2; exit 2; }

if [ -z "$SLUG" ]; then
  SLUG="$(git -C "$REPO_ROOT" config --get "remote.$REMOTE.url" 2>/dev/null \
    | sed -e 's#^.*[:/]\([^/]*/[^/]*\)\.git$#\1#' -e 's#^.*[:/]\([^/]*/[^/]*\)$#\1#')"
fi

WORK="$(mktemp -d "${TMPDIR:-/tmp}/ghl-hybrid-candidate.XXXXXX")" || {
  echo "FAIL environment: mktemp failed" >&2; exit 2; }
# shellcheck disable=SC2064
trap 'rm -rf "$WORK"' EXIT

git -C "$REPO_ROOT" ls-remote --heads "$REMOTE" > "$WORK/live-refs" 2> "$WORK/live-refs.err"
REF_RC=$?
if [ "$REF_RC" -ne 0 ] || [ ! -s "$WORK/live-refs" ]; then
  echo "FAIL environment: cannot read live refs from '$REMOTE' (git ls-remote rc=$REF_RC): $(head -1 "$WORK/live-refs.err")" >&2
  exit 2
fi

OUT_DIR="$(dirname "$OUT")"
mkdir -p "$OUT_DIR" || { echo "FAIL environment: cannot create $OUT_DIR" >&2; exit 2; }

python3 -I - "$WORK/live-refs" "$OUT.tmp" "$MAX_AGE" "$PREFIX" "$REMOTE" "$SLUG" <<'PY'
import datetime, json, sys

refs_path, out_path, max_age_raw, prefix, remote, slug = sys.argv[1:7]
max_age = int(max_age_raw)

refs = {}
with open(refs_path, encoding="utf-8") as fh:
    for line in fh:
        parts = line.split()
        if len(parts) == 2:
            refs[parts[1]] = parts[0]

main_ref = "refs/heads/main"
main_sha = refs.get(main_ref)
if not main_sha:
    print("FAIL environment: origin returned no " + main_ref, file=sys.stderr)
    raise SystemExit(2)

units = []
for i in range(36):
    unit = "WF%02d" % i
    branch = "%s/%s" % (prefix, unit.lower())
    ref = "refs/heads/" + branch
    sha = refs.get(ref)
    if sha:
        units.append({"unit": unit, "branch": branch, "sha": sha, "state": "present"})
    else:
        needle = unit.lower()
        alternates = sorted(r for r in refs if needle in r)
        units.append({
            "unit": unit,
            "branch": None,
            "sha": None,
            "state": "absent",
            "ref_checked": ref,
            "searched": "git ls-remote --heads %s" % remote,
            "alternate_refs_found": alternates,
            "reason": "origin returned no %s; any alternate refs that exist are listed, none is this unit's tip" % ref,
        })

present = [u["unit"] for u in units if u["state"] == "present"]
absent = [u["unit"] for u in units if u["state"] == "absent"]
stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

doc = {
    "record": "integration-candidate",
    "schema": "ghl-hybrid/integration-candidate/v2",
    "unit": "WFIN-021",
    "generated_at": stamp,
    "max_age_seconds": max_age,
    "source": {
        "repo": slug or None,
        "remote": remote,
        "query": "git ls-remote --heads %s" % remote,
        "main_sha": main_sha,
        "main_ref": main_ref,
    },
    "candidate": {
        "mode": "per-unit-branch",
        "branch_prefix": prefix + "/",
        "units_total": len(units),
        "units_present": len(present),
        "units_absent": len(absent),
        "absent_units": absent,
    },
    "units": units,
}

with open(out_path, "w", encoding="utf-8") as fh:
    json.dump(doc, fh, indent=2)
    fh.write("\n")
print("generated_at=%s max_age_seconds=%d present=%d absent=%d main=%s"
      % (stamp, max_age, len(present), len(absent), main_sha[:12]), file=sys.stderr)
PY
GEN_RC=$?
if [ "$GEN_RC" -ne 0 ]; then
  rm -f "$OUT.tmp"
  echo "FAIL environment: candidate generation failed rc=$GEN_RC" >&2
  exit 2
fi
mv "$OUT.tmp" "$OUT" || { rm -f "$OUT.tmp"; echo "FAIL environment: cannot install $OUT" >&2; exit 2; }
echo "OK: candidate written to $OUT"
