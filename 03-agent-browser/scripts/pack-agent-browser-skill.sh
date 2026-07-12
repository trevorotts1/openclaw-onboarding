#!/usr/bin/env bash
# pack-agent-browser-skill.sh — P3-06 step (c)1: regenerate agent-browser.skill
# from the loose on-disk source files. This is the ONLY sanctioned way to
# produce/update the archive from now on — never hand-zip it again.
#
# ROOT CAUSE THIS CLOSES: the bundled agent-browser.skill was hand-packaged
# with no regeneration step and no drift check, so it shipped a STALE copy of
# INSTALL.md (missing the N24 TYP citation, the mandatory --headed false
# requirement, the guaranteed-close trap, the Lifecycle hygiene section, and
# the GATEWAY RESTART PROTOCOL block) and CORE_UPDATES.md, right next to
# current loose files.
#
# USAGE
#   pack-agent-browser-skill.sh              regenerate agent-browser.skill in place
#   pack-agent-browser-skill.sh --check       verify the shipped archive matches
#                                             the on-disk docs; exits 1 and names
#                                             the differing file(s) if not.
#                                             Never writes anything.
#   pack-agent-browser-skill.sh --out PATH   write the regenerated archive to
#                                             PATH instead of in place (testing).
#
# DETERMINISM: the archive is built with `zip -X` (no extra file attributes)
# from a sorted, fixed file list, with every entry's mtime normalized to a
# fixed timestamp (`touch -t 202601010000` applied to the build directory
# AND every file inside it — the `agent-browser/` directory is itself a zip
# entry; omitting it from normalization previously left that one entry's
# mtime at a live build-time value, so two regenerations differed at that
# byte even though every file underneath was identical). With that fix, two
# regenerations of identical source content, run with the same `zip` binary
# on the same OS/toolchain, produce a byte-identical archive — proven by
# scripts/tests/pack-agent-browser-skill.test.sh's "two independent
# regenerations of identical source content are byte-identical" assertion
# (runs the packer twice, `cmp`s the output). This is a same-toolchain
# guarantee, not a claim that the archive is byte-identical across different
# `zip` implementations or operating systems (permission bits, OS-type byte,
# and extra-field encoding are not independently pinned here) — only that
# re-running this script against unchanged source on the SAME box never
# produces drift.
#
# WIRED INTO CI: .github/workflows/qc-static.yml runs this in --check mode on
# every push/PR (mirrors scripts/bump-version.sh --check) — a content change
# to INSTALL.md/SKILL.md/CHANGELOG.md/CORE_UPDATES.md without a repack now
# fails the build instead of shipping silently stale.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ARCHIVE_NAME="agent-browser.skill"
DEFAULT_ARCHIVE="$SKILL_DIR/$ARCHIVE_NAME"

# shellcheck source=./lib-archive-diff.sh
source "$SCRIPT_DIR/lib-archive-diff.sh"

MODE="build"
OUT_PATH="$DEFAULT_ARCHIVE"

while [ $# -gt 0 ]; do
  case "$1" in
    --check) MODE="check" ;;
    --out)
      shift
      OUT_PATH="${1:-}"
      [ -z "$OUT_PATH" ] && { echo "ERROR: --out requires a path" >&2; exit 2; }
      ;;
    -h|--help)
      sed -n '2,27p' "$0"
      exit 0
      ;;
    *)
      echo "ERROR: unknown argument: $1" >&2
      exit 2
      ;;
  esac
  shift
done

for doc in "${AGENT_BROWSER_ARCHIVE_DOCS[@]}"; do
  if [ ! -f "$SKILL_DIR/$doc" ]; then
    echo "ERROR: cannot pack — source file missing: $SKILL_DIR/$doc" >&2
    exit 2
  fi
done

if ! command -v zip >/dev/null 2>&1; then
  echo "ERROR: 'zip' is not available on PATH" >&2
  exit 2
fi

_build_archive() {
  local dest="$1"
  local build_dir
  build_dir="$(mktemp -d)" || { echo "ERROR: mktemp -d failed" >&2; return 2; }

  mkdir -p "$build_dir/agent-browser"
  local doc
  for doc in "${AGENT_BROWSER_ARCHIVE_DOCS[@]}"; do
    cp "$SKILL_DIR/$doc" "$build_dir/agent-browser/$doc"
  done

  # Normalize mtimes so the archive is byte-identical across regenerations of
  # identical content (deterministic --check, no timestamp false-positives).
  # Deliberately NOT `-type f`: the `agent-browser/` directory itself is a
  # zip entry too, and its mtime must be normalized as well, or two
  # regenerations diverge at the directory entry's mtime field even when
  # every file underneath is byte-identical.
  find "$build_dir" -exec touch -t 202601010000 {} +

  rm -f "$dest"
  ( cd "$build_dir" && zip -X -q -r "$dest" agent-browser )
  local rc=$?
  rm -rf "$build_dir"
  return $rc
}

if [ "$MODE" = "check" ]; then
  if [ ! -f "$DEFAULT_ARCHIVE" ]; then
    echo "FAIL — $ARCHIVE_NAME does not exist at $DEFAULT_ARCHIVE" >&2
    exit 1
  fi
  DRIFT="$(agent_browser_archive_diff "$DEFAULT_ARCHIVE" "$SKILL_DIR")"
  DRIFT_RC=$?
  if [ "$DRIFT_RC" -ne 0 ]; then
    echo "FAIL — could not evaluate archive drift: $DRIFT" >&2
    exit 1
  fi
  if [ -n "$DRIFT" ]; then
    echo "FAIL — $ARCHIVE_NAME is STALE vs on-disk source. Differing file(s):" >&2
    echo "$DRIFT" | sed 's/^/    /' >&2
    echo "FIX: run scripts/pack-agent-browser-skill.sh (no args) to regenerate, then commit the archive." >&2
    exit 1
  fi
  echo "PASS — $ARCHIVE_NAME matches on-disk INSTALL.md/SKILL.md/CHANGELOG.md/CORE_UPDATES.md byte-for-byte"
  exit 0
fi

if ! _build_archive "$OUT_PATH"; then
  echo "ERROR: archive build failed" >&2
  exit 2
fi
echo "OK — regenerated $OUT_PATH from $SKILL_DIR (${AGENT_BROWSER_ARCHIVE_DOCS[*]})"
exit 0
