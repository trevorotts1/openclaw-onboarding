#!/usr/bin/env bash
# install-front-door.sh (CTR-103) - install the council front door into a
# DURABLE, release-versioned directory.
#
# why: wire.sh used to bake the shim it installs at
# $OPENCLAW_ROOT/council-runtime/bin/council-ask as an absolute path into the
# skill checkout it was run FROM. When that checkout is a lane worktree or a
# temporary clone (the normal case for an install before the merge commit
# exists), post-merge hygiene deletes it and the installed front door becomes
# `node MODULE_NOT_FOUND`. The front door this unit exists to install must
# outlive the checkout that installed it.
#
# The copy lives beside the releases, NOT inside one: a release directory is
# hash-covered by its artifact receipt and install-runtime's verifyRelease
# rejects an "unexpected generated file", so adding skill files there would
# make every wire run rebuild the runtime. $P/frontdoor/<release-id>/ is
# immutable, versioned and never deleted.
#
# Usage: install-front-door.sh <prefix> <release-id> <skill-dir> <node-exe>
#   <prefix>      e.g. $OPENCLAW_ROOT/council-runtime
#   <release-id>  the active release id (e.g. rel-067ba04e5f48)
#   <skill-dir>   the skill tree to copy from (may be a doomed checkout)
#   <node-exe>    node used for the load check
# Prints the installed entry path on success. Exit 1 on any failure.
# Never touches an existing release, data dir, or credential.
set -u

if [ "$#" -ne 4 ]; then
  echo "usage: install-front-door.sh <prefix> <release-id> <skill-dir> <node-exe>" >&2
  exit 1
fi

PREFIX="$1"; REL_ID="$2"; SRC="$3"; NODE="$4"

case "$REL_ID" in
  ''|*/*|.|..) echo "FRONTDOOR_INSTALL_FAILED invalid release id '$REL_ID'" >&2; exit 1 ;;
esac
[ -d "$SRC/scripts" ] || { echo "FRONTDOOR_INSTALL_FAILED source scripts missing: $SRC/scripts" >&2; exit 1; }

DEST="$PREFIX/frontdoor/$REL_ID/scripts"
mkdir -p "$DEST" || { echo "FRONTDOOR_INSTALL_FAILED cannot create $DEST" >&2; exit 1; }

for f in council-entry.mjs chamber-visual.sh; do
  [ -f "$SRC/scripts/$f" ] || { echo "FRONTDOOR_INSTALL_FAILED source $SRC/scripts/$f missing" >&2; exit 1; }
  cp -f "$SRC/scripts/$f" "$DEST/$f" || { echo "FRONTDOOR_INSTALL_FAILED cannot copy $f into $DEST" >&2; exit 1; }
done
chmod 755 "$DEST/chamber-visual.sh" 2>/dev/null || true
chmod 644 "$DEST/council-entry.mjs" 2>/dev/null || true

[ -s "$DEST/council-entry.mjs" ] || { echo "FRONTDOOR_INSTALL_FAILED copied entry is empty" >&2; exit 1; }
[ -s "$DEST/chamber-visual.sh" ] || { echo "FRONTDOOR_INSTALL_FAILED copied helper is empty" >&2; exit 1; }
"$NODE" --check "$DEST/council-entry.mjs" >/dev/null 2>&1 \
  || { echo "FRONTDOOR_INSTALL_FAILED copied entry does not load (node --check)" >&2; exit 1; }

printf '%s\n' "$DEST/council-entry.mjs"
