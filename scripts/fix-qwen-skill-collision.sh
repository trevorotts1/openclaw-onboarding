#!/usr/bin/env bash
# fix-qwen-skill-collision.sh — repair the qwen-mm-plugins skill-id collision.
#
# BUG: three OpenClaw plugins from the upstream Qwen-MM-Plugins marketplace
# (qwen-mm-plugins-core, qwen-mm-plugins-video-edit, qwen-mm-plugins-video-memory)
# each ship their skill in a directory literally named skill/. OpenClaw derives a
# skill id from the DIRECTORY BASENAME, not the name: field in SKILL.md, so all
# three register as a skill named "skill", collide, and OpenClaw keeps only the
# first one it loads — silently dropping the other two. Observed error:
#
#   [skills] plugin skill name collision: "skill" resolves to both
#   /.../extensions/qwen-mm-plugins-core/skill and
#   /.../extensions/qwen-mm-plugins-video-edit/skill;
#   only the first will be published
#
# FIX: rename each plugin skill directory to <plugin-id>-skill/ and repoint the
# skills field in every manifest that references it. Confirmed clean afterwards
# (0 collisions, all three plugins ready).
#
# We do not control the upstream repo (github.com/QwenLM/Qwen-MM-Plugins), so
# this cannot be fixed at the source. Worse: `openclaw update repair` RE-CLONES
# these plugins from upstream, which wipes the rename. Re-run this script after
# any install, update, or repair that touches the qwen-mm-plugins extensions.
#
# Idempotent — safe to run repeatedly. Already-fixed plugins are a no-op.
#
# USAGE:
#   bash scripts/fix-qwen-skill-collision.sh [extensions-dir]
#
# [extensions-dir] defaults to /data/.openclaw/extensions inside a Docker VPS
# install, or $HOME/.openclaw/extensions on a Mac install.
#
# EXIT CODES:
#   0   every installed plugin verified fixed (or none were installed)
#   1   at least one plugin failed to fix or failed verification
set -uo pipefail

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
    sed -n '2,32p' "${BASH_SOURCE[0]}"
    exit 0
fi

if [ -d "/data/.openclaw" ]; then
    DEFAULT_EXT_DIR="/data/.openclaw/extensions"
else
    DEFAULT_EXT_DIR="$HOME/.openclaw/extensions"
fi
EXT_DIR="${1:-$DEFAULT_EXT_DIR}"

TS="$(date +%Y%m%d-%H%M%S)"
PLUGINS="qwen-mm-plugins-core qwen-mm-plugins-video-edit qwen-mm-plugins-video-memory"
MANIFEST_RELPATHS=".codex-plugin/plugin.json .claude-plugin/plugin.json .qoder-plugin/plugin.json"

if ! command -v python3 >/dev/null 2>&1; then
    echo "ERROR: python3 is required to safely edit the plugin manifests." >&2
    exit 1
fi

echo "[fix-qwen-skill-collision] extensions dir: $EXT_DIR"
echo ""

OVERALL_FAIL=0
ANY_INSTALLED=0
RESULT_LINES=""

for PLUGIN in $PLUGINS; do
    PLUGIN_DIR="$EXT_DIR/$PLUGIN"

    if [ ! -d "$PLUGIN_DIR" ]; then
        echo "== $PLUGIN =="
        echo "  not installed on this box — skipping"
        echo ""
        RESULT_LINES="${RESULT_LINES}${PLUGIN}: NOT INSTALLED (skipped)
"
        continue
    fi

    ANY_INSTALLED=1
    echo "== $PLUGIN =="
    PLUGIN_FAIL=0
    OLD_DIR="$PLUGIN_DIR/skill"
    NEW_DIR="$PLUGIN_DIR/${PLUGIN}-skill"
    NEW_REL="./${PLUGIN}-skill"
    OLD_REL="./skill"

    # ---- Step 1: rename the skill directory --------------------------------
    if [ -d "$NEW_DIR" ] && [ ! -e "$OLD_DIR" ]; then
        echo "  dir: already renamed -> $(basename "$NEW_DIR")"
    elif [ -d "$OLD_DIR" ]; then
        if mv "$OLD_DIR" "$NEW_DIR"; then
            echo "  dir: renamed skill/ -> $(basename "$NEW_DIR")/"
        else
            echo "  ERROR: failed to rename $OLD_DIR -> $NEW_DIR"
            PLUGIN_FAIL=1
        fi
    elif [ -e "$OLD_DIR" ]; then
        echo "  ERROR: $OLD_DIR exists but is not a directory — skipping plugin"
        PLUGIN_FAIL=1
    else
        echo "  ERROR: neither skill/ nor $(basename "$NEW_DIR")/ found under $PLUGIN_DIR — unexpected layout, skipping"
        PLUGIN_FAIL=1
    fi

    # ---- Step 2: repoint every manifest that references it -----------------
    if [ "$PLUGIN_FAIL" -eq 0 ]; then
        for RELPATH in $MANIFEST_RELPATHS; do
            MANIFEST="$PLUGIN_DIR/$RELPATH"
            if [ ! -f "$MANIFEST" ]; then
                echo "  manifest: $RELPATH not present, skipping"
                continue
            fi

            BACKUP="${MANIFEST}.bak-skill-collision-${TS}"
            if ! cp "$MANIFEST" "$BACKUP"; then
                echo "  ERROR: could not back up $RELPATH before editing"
                PLUGIN_FAIL=1
                continue
            fi

            OUT="$(python3 - "$MANIFEST" "$OLD_REL" "$NEW_REL" <<'PYEOF'
import json
import sys

path, old_rel, new_rel = sys.argv[1], sys.argv[2], sys.argv[3]

with open(path) as f:
    data = json.load(f)

skills = data.get("skills")

if isinstance(skills, str):
    if skills == new_rel:
        print("NOOP")
        sys.exit(0)
    if skills != old_rel:
        print("UNEXPECTED_STRING:" + skills)
        sys.exit(3)
    data["skills"] = new_rel
elif isinstance(skills, list):
    if new_rel in skills and old_rel not in skills:
        print("NOOP")
        sys.exit(0)
    if old_rel not in skills:
        print("UNEXPECTED_LIST:" + json.dumps(skills))
        sys.exit(3)
    data["skills"] = [new_rel if entry == old_rel else entry for entry in skills]
else:
    print("UNEXPECTED_TYPE:" + json.dumps(skills))
    sys.exit(3)

with open(path, "w") as f:
    json.dump(data, f, indent=2)
    f.write("\n")

print("CHANGED")
PYEOF
)"
            PY_STATUS=$?

            case "$OUT" in
                NOOP)
                    echo "  manifest: $RELPATH already points to $NEW_REL"
                    rm -f "$BACKUP"
                    ;;
                CHANGED)
                    echo "  manifest: $RELPATH updated -> $NEW_REL (backup: $(basename "$BACKUP"))"
                    ;;
                UNEXPECTED_STRING:*|UNEXPECTED_LIST:*|UNEXPECTED_TYPE:*)
                    echo "  ERROR: $RELPATH has an unrecognized skills value (${OUT}) — left untouched, backup at $(basename "$BACKUP")"
                    PLUGIN_FAIL=1
                    ;;
                *)
                    echo "  ERROR: could not parse or edit $RELPATH (exit $PY_STATUS) — backup at $(basename "$BACKUP")"
                    PLUGIN_FAIL=1
                    ;;
            esac
        done
    fi

    # ---- Step 3: re-grant capability consent (best-effort, non-fatal) ------
    if [ "$PLUGIN_FAIL" -eq 0 ]; then
        if command -v openclaw >/dev/null 2>&1; then
            if openclaw plugins enable "$PLUGIN" --accept-capabilities >/dev/null 2>&1; then
                echo "  consent: re-granted (openclaw plugins enable --accept-capabilities)"
            else
                echo "  NOTE: consent re-grant failed — run manually: openclaw plugins enable $PLUGIN --accept-capabilities"
            fi
        else
            echo "  NOTE: openclaw CLI not on PATH here — re-grant consent manually: openclaw plugins enable $PLUGIN --accept-capabilities"
        fi
    fi

    # ---- Step 4: verify -----------------------------------------------------
    VERIFY_OK=1
    if [ ! -d "$NEW_DIR" ] || [ -e "$OLD_DIR" ]; then
        VERIFY_OK=0
    fi
    for RELPATH in $MANIFEST_RELPATHS; do
        MANIFEST="$PLUGIN_DIR/$RELPATH"
        [ -f "$MANIFEST" ] || continue
        if ! python3 -c "
import json, sys
with open('$MANIFEST') as f:
    data = json.load(f)
skills = data.get('skills')
new_rel = '$NEW_REL'
ok = (skills == new_rel) or (isinstance(skills, list) and new_rel in skills and '$OLD_REL' not in skills)
sys.exit(0 if ok else 1)
"; then
            VERIFY_OK=0
        fi
    done

    if [ "$PLUGIN_FAIL" -ne 0 ] || [ "$VERIFY_OK" -ne 1 ]; then
        echo "  RESULT: FAIL"
        RESULT_LINES="${RESULT_LINES}${PLUGIN}: FAIL
"
        OVERALL_FAIL=1
    else
        echo "  RESULT: PASS"
        RESULT_LINES="${RESULT_LINES}${PLUGIN}: PASS
"
    fi
    echo ""
done

echo "==================================================================="
echo "SUMMARY"
printf '%s' "$RESULT_LINES"
echo "==================================================================="

if [ "$ANY_INSTALLED" -eq 1 ] && [ "$OVERALL_FAIL" -eq 0 ]; then
    echo ""
    echo "Restart the gateway to pick up the change: openclaw gateway restart"
fi

if [ "$OVERALL_FAIL" -ne 0 ]; then
    echo ""
    echo "OVERALL: FAIL"
    exit 1
fi

echo ""
echo "OVERALL: PASS"
exit 0
