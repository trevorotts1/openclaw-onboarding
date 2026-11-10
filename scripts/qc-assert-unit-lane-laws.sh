#!/usr/bin/env bash
# qc-assert-unit-lane-laws.sh — v1.0.0
#
# SCOPE: unit laws L4-L16 only (SCOPE-LEDGER.md INST-001 items 27-39). L1-L3 are
# judged by the diff/PR checks owned by other lanes and are deliberately NOT
# judged here.
#
# WHY THIS EXISTS
#   The binding unit laws shipped only as prose inside every unit's build prompt
#   ("non-negotiables", COLLISION LAW, ONE PR, PIN LAW, ANCESTRY LAW,
#   CLONE/TMPDIR, MODEL POLICY). So a lane could write any of them in its report
#   and no artifact could contradict it — the only "verifier" was the lane itself.
#   This gate turns L4-L16 into checks over data a lane already produces: the
#   base..head commit range, the PR number(s), the lane transcript, the QC verdict.
#
#   It judges. It never lands, pushes, mints, or touches a network or credential.
#   A PASS means "no evidence of a violation in the inputs given"; it is not an
#   opinion on the code.
#
# LAW -> CHECK
#   L4  no --no-verify        command-position match in the transcript
#   L5  pin not hand-written  every commit touching the pin in base..head is
#                             bot-authored, bot-committed, and touches only the pin
#   L6  pin minted once       at most one pin-touching commit in base..head
#   L7  no SSH                command-position ssh/scp in the transcript
#   L8  no fleet contact      fleet-access.sh, rescue-*, contabo-host, lyric-mac
#   L9  no secret printed     secret shapes in the transcript / QC text; the gate
#                             reports the LINE NUMBER, never the value
#   L10 collision law         `gh pr list --state open` and, per changed file,
#                             `git log --oneline -5 ... -- <file>`, with the open-PR
#                             check ordered FIRST (line number compared)
#   L11 ONE PR                exactly one PR, or two with an explicit recut pointer
#   L12 no merge-of-main      no merge commit in base..head other than the PR merge
#   L13 ancestry              `git merge-base --is-ancestor <head> <main-ref>` = 0
#   L14 clone/TMPDIR          every workspace path in the transcript is under
#                             --clone or --tmpdir
#   L15 QC not the builder    --qc-model differs from --builder-model
#   L16 QC verdict            CONFIRMED or FAILED present; FAILED + landed = FAIL
#
# USAGE
#   scripts/qc-assert-unit-lane-laws.sh --unit INST-001 \
#     --base <sha> --head <sha> --transcript <file> \
#     --builder-model <id> --qc-model <id> \
#     --clone <dir> --tmpdir <dir> \
#     --pr <number> [--pr <number> --recut-pointer "<text>"] \
#     [--qc-verdict <file>] [--main-ref origin/main] [--pin-path <path>]
#     [--repo <dir>] [--allow-unmerged]
#
# EXIT
#   0 every law PASS (SKIP is printed separately and never counted as a PASS)
#   1 at least one law FAILED
#   2 usage or instrument error — fail closed, never "clean"
#
# ponytail: transcript checks are line-based heuristics, which is the depth the
# law's own verification method has ("lane transcript"). A lane that edits its
# transcript can defeat them; the ceiling is an append-only, gateway-written
# transcript. Upgrade path: read the gateway's own log instead of a lane-supplied
# file. The ancestry, merge, and pin checks are git facts and do not share this
# ceiling.

set -uo pipefail

PIN_PATH_DEFAULT="49-signature-funnel/scripts/SF-PROVER-PIN.sha256"
BOT_EMAIL_DEFAULT="41898282+github-actions[bot]@users.noreply.github.com"

UNIT=""
BASE=""
HEAD=""
TRANSCRIPT=""
BUILDER_MODEL=""
QC_MODEL=""
CLONE=""
TMPDIR_LANE=""
MAIN_REF="origin/main"
PIN_PATH="$PIN_PATH_DEFAULT"
REPO="."
QC_VERDICT=""
QC_VERDICT_TEXT=""
RECUT_POINTER=""
ALLOW_UNMERGED=0
PRS=""

usage() { sed -n '2,50p' "$0" | sed 's/^# \{0,1\}//'; }

die_usage() { echo "qc-assert-unit-lane-laws: $*" >&2; exit 2; }

while [ $# -gt 0 ]; do
  case "$1" in
    --unit) UNIT="${2:-}"; shift 2 ;;
    --base) BASE="${2:-}"; shift 2 ;;
    --head) HEAD="${2:-}"; shift 2 ;;
    --transcript) TRANSCRIPT="${2:-}"; shift 2 ;;
    --builder-model) BUILDER_MODEL="${2:-}"; shift 2 ;;
    --qc-model) QC_MODEL="${2:-}"; shift 2 ;;
    --clone) CLONE="${2:-}"; shift 2 ;;
    --tmpdir) TMPDIR_LANE="${2:-}"; shift 2 ;;
    --main-ref) MAIN_REF="${2:-}"; shift 2 ;;
    --pin-path) PIN_PATH="${2:-}"; shift 2 ;;
    --repo) REPO="${2:-}"; shift 2 ;;
    --qc-verdict) QC_VERDICT="${2:-}"; shift 2 ;;
    --qc-verdict-text) QC_VERDICT_TEXT="${2:-}"; shift 2 ;;
    --recut-pointer) RECUT_POINTER="${2:-}"; shift 2 ;;
    --pr) PRS="$PRS ${2:-}"; shift 2 ;;
    --allow-unmerged) ALLOW_UNMERGED=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) die_usage "unexpected argument: $1" ;;
  esac
done

[ -n "$UNIT" ] || die_usage "--unit is required"
[ -n "$BASE" ] || die_usage "--base is required"
[ -n "$HEAD" ] || die_usage "--head is required"
[ -n "$TRANSCRIPT" ] || die_usage "--transcript is required"
[ -n "$BUILDER_MODEL" ] || die_usage "--builder-model is required"
[ -n "$QC_MODEL" ] || die_usage "--qc-model is required"
[ -n "$CLONE" ] || die_usage "--clone is required"
[ -n "$TMPDIR_LANE" ] || die_usage "--tmpdir is required"
[ -n "$(printf '%s' "$PRS" | tr -d ' ')" ] || die_usage "--pr is required"

if ! git -C "$REPO" rev-parse --verify --quiet "${BASE}^{commit}" >/dev/null; then
  die_usage "--base '$BASE' does not resolve to a commit in $REPO"
fi
if ! git -C "$REPO" rev-parse --verify --quiet "${HEAD}^{commit}" >/dev/null; then
  die_usage "--head '$HEAD' does not resolve to a commit in $REPO"
fi
if ! git -C "$REPO" rev-parse --verify --quiet "${MAIN_REF}^{commit}" >/dev/null; then
  die_usage "--main-ref '$MAIN_REF' does not resolve to a commit in $REPO"
fi
[ -f "$TRANSCRIPT" ] || die_usage "--transcript '$TRANSCRIPT' is not a file"

PASSES=0
FAILS=0
SKIPS=0

verdict() { # law status reason
  local law="$1" status="$2"; shift 2
  local reason="$*"
  if [ -z "$reason" ]; then reason="-"; fi
  printf '%s %-4s %s\n' "$law" "$status" "$reason"
  case "$status" in
    PASS) PASSES=$((PASSES + 1)) ;;
    FAIL) FAILS=$((FAILS + 1)) ;;
    SKIP) SKIPS=$((SKIPS + 1)) ;;
  esac
}

# ── L4: no --no-verify ───────────────────────────────────────────────────────
# Command position only: the line must BEGIN with git/npm/yarn/pnpm (optionally
# behind a "$ " prompt). A prose line that quotes the rule does not trip it.
if grep -nE '^[[:space:]]*(\$[[:space:]]+)?(git|npm|yarn|pnpm)[[:space:]].*--no-verify' "$TRANSCRIPT" >/dev/null 2>&1; then
  verdict L4 FAIL "transcript invokes --no-verify at line(s) $(grep -nE '^[[:space:]]*(\$[[:space:]]+)?(git|npm|yarn|pnpm)[[:space:]].*--no-verify' "$TRANSCRIPT" | cut -d: -f1 | paste -sd, -)"
else
  verdict L4 PASS "no command-position --no-verify in transcript"
fi

# ── L5 / L6: the pin ─────────────────────────────────────────────────────────
PIN_COMMITS="$(git -C "$REPO" log --format='%H %ae %ce' "${BASE}..${HEAD}" -- "$PIN_PATH" 2>/dev/null || true)"
PIN_COUNT=0
if [ -n "$PIN_COMMITS" ]; then PIN_COUNT="$(printf '%s\n' "$PIN_COMMITS" | wc -l | tr -d ' ')"; fi

L5_REASON="no commit in the range touches $PIN_PATH"
L5_STATUS=PASS
if [ "$PIN_COUNT" -gt 0 ]; then
  while read -r sha ae ce; do
    [ -n "$sha" ] || continue
    if [ "$ae" != "$BOT_EMAIL_DEFAULT" ] || [ "$ce" != "$BOT_EMAIL_DEFAULT" ]; then
      L5_STATUS=FAIL
      L5_REASON="pin written by non-bot commit ${sha:0:12} (author $ae, committer $ce)"
      break
    fi
    others="$(git -C "$REPO" diff-tree --no-commit-id --name-only -r "$sha" | awk -v p="$PIN_PATH" '$0 != p')"
    if [ -n "$others" ]; then
      L5_STATUS=FAIL
      L5_REASON="pin-mint commit ${sha:0:12} also touches $(printf '%s' "$others" | paste -sd, -)"
      break
    fi
  done <<EOF
$PIN_COMMITS
EOF
  if [ "$L5_STATUS" = PASS ]; then
    L5_REASON="$PIN_COUNT bot-authored pin-only commit(s)"
  fi
fi
verdict L5 "$L5_STATUS" "$L5_REASON"

if [ "$PIN_COUNT" -le 1 ]; then
  verdict L6 PASS "pin-touching commits in range: $PIN_COUNT (at most one)"
else
  verdict L6 FAIL "pin-touching commits in range: $PIN_COUNT (the authority workflow mints once)"
fi

# ── L7: no SSH ───────────────────────────────────────────────────────────────
SSH_HITS="$(grep -nE '^[[:space:]]*(\$[[:space:]]+)?(ssh|scp|rsync)[[:space:]]' "$TRANSCRIPT" 2>/dev/null | cut -d: -f1 | paste -sd, -)"
if [ -n "$SSH_HITS" ]; then
  verdict L7 FAIL "transcript runs ssh/scp/rsync at line(s) $SSH_HITS"
else
  verdict L7 PASS "no ssh/scp/rsync command in transcript"
fi

# ── L8: no fleet contact ─────────────────────────────────────────────────────
FLEET_PAT='fleet-access\.sh|rescue-[a-z0-9-]+|contabo-host|lyric-mac'
FLEET_HITS="$(grep -nE "$FLEET_PAT" "$TRANSCRIPT" 2>/dev/null | cut -d: -f1 | paste -sd, -)"
if [ -n "$FLEET_HITS" ]; then
  verdict L8 FAIL "transcript reaches a fleet target at line(s) $FLEET_HITS"
else
  verdict L8 PASS "no fleet-access/rescue-*/contabo-host/lyric-mac in transcript"
fi

# ── L9: no secret printed ────────────────────────────────────────────────────
# Line numbers only. The value is NEVER echoed — a guard that prints the secret
# it caught has leaked it into the same log it is protecting.
SECRET_TEXT="$(mktemp)"
cat "$TRANSCRIPT" > "$SECRET_TEXT"
if [ -n "$QC_VERDICT" ] && [ -f "$QC_VERDICT" ]; then cat "$QC_VERDICT" >> "$SECRET_TEXT"; fi
if [ -n "$QC_VERDICT_TEXT" ]; then printf '%s\n' "$QC_VERDICT_TEXT" >> "$SECRET_TEXT"; fi

SECRET_LABELS=""
SECRET_LINES=""
scan_secret() { # label pattern
  local label="$1" pat="$2" hits
  hits="$(grep -nE "$pat" "$SECRET_TEXT" 2>/dev/null | cut -d: -f1 | paste -sd, -)"
  if [ -n "$hits" ]; then
    SECRET_LABELS="$SECRET_LABELS $label"
    SECRET_LINES="$SECRET_LINES $label@$hits"
  fi
}
scan_secret aws-access-key-id 'AKIA[0-9A-Z]{16}'
scan_secret github-token 'gh[pous]_[A-Za-z0-9]{20,}'
scan_secret api-key 'sk-[A-Za-z0-9_-]{20,}'
scan_secret slack-token 'xox[abprs]-[A-Za-z0-9-]{10,}'
scan_secret private-key '-----BEGIN [A-Z ]*PRIVATE KEY-----'
if [ -n "$SECRET_LABELS" ]; then
  verdict L9 FAIL "secret shape(s) printed:$SECRET_LINES"
else
  verdict L9 PASS "no secret shape in transcript or QC text"
fi
rm -f "$SECRET_TEXT"

# ── L10: collision law ───────────────────────────────────────────────────────
PR_LIST_LINE="$(grep -nE 'gh[[:space:]]+pr[[:space:]]+list[[:space:]]+--state[[:space:]]+open' "$TRANSCRIPT" 2>/dev/null | head -1 | cut -d: -f1)"
CHANGED="$(git -C "$REPO" diff --name-only "${BASE}" "${HEAD}" 2>/dev/null || true)"
MISSING=""
OUT_OF_ORDER=""
if [ -z "$PR_LIST_LINE" ]; then
  verdict L10 FAIL "no 'gh pr list --state open' in the transcript"
else
  while IFS= read -r f; do
    [ -n "$f" ] || continue
    base="$(basename "$f")"
    log_line="$(grep -nF -- "$base" "$TRANSCRIPT" 2>/dev/null | grep -E 'git log --oneline -5' | head -1 | cut -d: -f1)"
    if [ -z "$log_line" ]; then
      MISSING="$MISSING $f"
    elif [ "$PR_LIST_LINE" -gt "$log_line" ]; then
      OUT_OF_ORDER="$OUT_OF_ORDER $f"
    fi
  done <<EOF
$CHANGED
EOF
  if [ -n "$MISSING" ] || [ -n "$OUT_OF_ORDER" ]; then
    reason=""
    [ -n "$MISSING" ] && reason="no 'git log --oneline -5 ... -- <file>' for:$MISSING"
    [ -n "$OUT_OF_ORDER" ] && reason="$reason; open-PR check runs AFTER the per-file log check for:$OUT_OF_ORDER"
    verdict L10 FAIL "$reason"
  else
    verdict L10 PASS "open-PR check at line $PR_LIST_LINE precedes the per-file log check for $(printf '%s\n' "$CHANGED" | grep -c . ) file(s)"
  fi
fi

# ── L11: ONE PR ──────────────────────────────────────────────────────────────
PR_COUNT="$(printf '%s\n' $PRS | grep -c . )"
if [ "$PR_COUNT" -eq 1 ]; then
  verdict L11 PASS "one PR: $(printf '%s\n' $PRS)"
elif [ "$PR_COUNT" -eq 2 ] && [ -n "$RECUT_POINTER" ]; then
  verdict L11 PASS "one original PR plus one recut, pointer: $RECUT_POINTER"
elif [ "$PR_COUNT" -eq 2 ]; then
  verdict L11 FAIL "two PRs with no --recut-pointer naming the replacement"
else
  verdict L11 FAIL "PR count for $UNIT is $PR_COUNT (ONE PR per unit)"
fi

# ── L12: never merge main into a branch ──────────────────────────────────────
# A GitHub PR merge has the subject "Merge pull request #N ...". Anything else is
# a "Merge remote-tracking branch 'origin/main' into <branch>" or a local merge.
BAD_MERGES="$(git -C "$REPO" log --merges --format='%h %s' "${BASE}..${HEAD}" 2>/dev/null \
  | awk '{ $1=""; sub(/^ /,""); if ($0 !~ /^Merge pull request /) print }')"
if [ -n "$BAD_MERGES" ]; then
  verdict L12 FAIL "merge-of-main into the branch: $(printf '%s' "$BAD_MERGES" | paste -sd';' -)"
else
  verdict L12 PASS "no merge commit in base..head other than the PR merge"
fi

# ── L13: ancestry ────────────────────────────────────────────────────────────
if git -C "$REPO" merge-base --is-ancestor "$HEAD" "$MAIN_REF" 2>/dev/null; then
  verdict L13 PASS "git merge-base --is-ancestor ${HEAD:0:12} $MAIN_REF = 0"
elif [ "$ALLOW_UNMERGED" -eq 1 ]; then
  verdict L13 SKIP "not landed yet and --allow-unmerged was given"
else
  verdict L13 FAIL "git merge-base --is-ancestor ${HEAD:0:12} $MAIN_REF != 0"
fi

# ── L14: clone / TMPDIR ──────────────────────────────────────────────────────
# Paths are normalised for repeated slashes first: a temp dir spelled with a
# trailing slash yields ".../T//lane/clone", whose second half would otherwise
# be extracted as a bare "/lane/clone" and read as an escape.
norm_path() { printf '%s' "$1" | sed 's://*:/:g; s:/*$::'; }
CLONE_NORM="$(norm_path "$CLONE")"
TMP_NORM="$(norm_path "$TMPDIR_LANE")"
BAD_PATHS=""
while IFS= read -r p; do
  [ -n "$p" ] || continue
  p="$(norm_path "$p")"
  case "$p" in
    "$CLONE_NORM"|"$CLONE_NORM"/*|"$TMP_NORM"|"$TMP_NORM"/*) continue ;;
    /dev/*|/usr/*|/bin/*|/sbin/*|/etc/*|/opt/homebrew/*|/Library/*|/System/*|/tmp/*) continue ;;
  esac
  BAD_PATHS="$BAD_PATHS $p"
done <<EOF
$(grep -E '^[[:space:]]*(\$[[:space:]]+)?(cd|pushd)[[:space:]]|git[[:space:]]+clone|TMPDIR=' "$TRANSCRIPT" 2>/dev/null \
  | sed 's://*:/:g' \
  | grep -oE '/[A-Za-z0-9._+-]+(/[A-Za-z0-9._+-]+)*' | sort -u)
EOF
if [ -n "$BAD_PATHS" ]; then
  verdict L14 FAIL "workspace path outside --clone/--tmpdir:$BAD_PATHS"
else
  verdict L14 PASS "every workspace path in the transcript is under --clone or --tmpdir"
fi

# ── L15: QC lane is not the builder ──────────────────────────────────────────
BUILDER_LC="$(printf '%s' "$BUILDER_MODEL" | tr '[:upper:]' '[:lower:]')"
QC_LC="$(printf '%s' "$QC_MODEL" | tr '[:upper:]' '[:lower:]')"
if [ "$BUILDER_LC" = "$QC_LC" ]; then
  verdict L15 FAIL "builder and QC models are the same ($QC_MODEL)"
else
  verdict L15 PASS "QC model $QC_MODEL differs from builder model $BUILDER_MODEL"
fi

# ── L16: QC verdict ──────────────────────────────────────────────────────────
VERDICT_TEXT=""
if [ -n "$QC_VERDICT_TEXT" ]; then
  VERDICT_TEXT="$QC_VERDICT_TEXT"
elif [ -n "$QC_VERDICT" ] && [ -f "$QC_VERDICT" ]; then
  VERDICT_TEXT="$(cat "$QC_VERDICT")"
else
  VERDICT_TEXT="$(grep -iE '\b(CONFIRMED|FAILED)\b' "$TRANSCRIPT" 2>/dev/null)"
fi
# A here-string, never a pipe into `grep -q`: grep -q exits at the first match
# and SIGPIPEs its producer, which under `pipefail` turns a successful match into
# a false failure (scripts/qc-assert-code-has-no-sigpipe.sh, T5).
VERDICT_WORD="$(grep -oiE -m1 '\b(CONFIRMED|FAILED)\b' <<< "$VERDICT_TEXT" 2>/dev/null | tr '[:lower:]' '[:upper:]' || true)"
if [ -z "$VERDICT_WORD" ]; then
  verdict L16 FAIL "no CONFIRMED or FAILED verdict in the QC text"
elif [ "$VERDICT_WORD" = "FAILED" ] && [ "$ALLOW_UNMERGED" -ne 1 ]; then
  verdict L16 FAIL "QC said FAILED but the commit is landed on $MAIN_REF"
else
  verdict L16 PASS "QC verdict present ($VERDICT_WORD)"
fi

# ── summary ──────────────────────────────────────────────────────────────────
TOTAL=$((PASSES + FAILS + SKIPS))
echo "---"
echo "RESULT: $PASSES PASS / $FAILS FAIL / $SKIPS SKIP ($TOTAL of 13 laws, L4-L16, unit $UNIT)"
if [ "$FAILS" -gt 0 ]; then exit 1; fi
exit 0
