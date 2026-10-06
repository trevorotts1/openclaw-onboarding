#!/usr/bin/env bash
# vendor_skill_probe.sh - PROBE BOX ONLY. Detects drift in KIE's official agent skills.
# Installs them with `npx skills add https://kie.ai` into a disposable HOME and project,
# hashes the unique files the same way vendor-approval.json was built, prints MATCH or DRIFT,
# then deletes the temp dir. Never touches the real HOME. Never run on client boxes.
# Needs: npx (Node), python3, network. Exit 0 = MATCH, 1 = DRIFT, 2 = probe could not run.
set -uo pipefail
export GIT_TERMINAL_PROMPT=0
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APPROVAL="${KIE_VENDOR_APPROVAL:-$HERE/../vendor-approval.json}"
command -v npx >/dev/null 2>&1 || { echo "UNDETERMINED: npx not found"; exit 2; }
command -v python3 >/dev/null 2>&1 || { echo "UNDETERMINED: python3 not found"; exit 2; }
[ -f "$APPROVAL" ] || { echo "UNDETERMINED: $APPROVAL missing"; exit 2; }

TMP="$(mktemp -d "${TMPDIR:-/tmp}/kie-vendor-probe.XXXXXX")" || exit 2
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/home" "$TMP/project"
# A real HOME would be read by npm/skills for config; the temp HOME isolates all of it.
( cd "$TMP/project" && HOME="$TMP/home" XDG_CONFIG_HOME="$TMP/home/.config" \
  timeout 240 npx -y skills add https://kie.ai -y --copy ) >"$TMP/install.log" 2>&1
rc=$?
if [ "$rc" -ne 0 ]; then echo "UNDETERMINED: install failed rc=$rc (log discarded with temp dir)"; tail -5 "$TMP/install.log"; exit 2; fi

TMPROOT="$TMP/project" APPROVAL="$APPROVAL" python3 - <<'PY'
import hashlib, json, os, sys
root, approval = os.environ["TMPROOT"], json.load(open(os.environ["APPROVAL"]))
want = approval["files"]
seen = {}  # "<skill>/<relative path>" -> set of hashes found
# The CLI copies the skills into ~55 agent dirs; the universal copy under .agents/skills is canonical.
# (One agent dir rewrites SKILL.md for its own format, so scanning every dir would report false drift.)
for d, _, fs in os.walk(os.path.join(root, ".agents", "skills")):
    for f in fs:
        p = os.path.join(d, f)
        parts = p.split(os.sep)
        for skill in ("kie-models", "kie-chat-agents"):
            if skill in parts:
                rel = "/".join(parts[parts.index(skill):])
                if rel in want:
                    seen.setdefault(rel, set()).add(hashlib.sha256(open(p, "rb").read()).hexdigest())
unique = sorted({h for hs in seen.values() for h in hs})
tree = hashlib.sha256(("\n".join(unique) + "\n").encode()).hexdigest()
bad = [k for k in want if seen.get(k) != {want[k]}]
extra = sorted(set(seen) - set(want))
if tree == approval["treeHash_sha256"] and not bad:
    print("MATCH tree=" + tree)
    sys.exit(0)
print("DRIFT tree=%s approved=%s" % (tree, approval["treeHash_sha256"]))
print("files differing or missing:", bad or "none", "| unexpected:", extra or "none")
sys.exit(1)
PY
