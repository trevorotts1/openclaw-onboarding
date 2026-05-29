#!/usr/bin/env bash
# qc-trinity-registry.sh — machine-enforce THE TRINITY at register/QC time.
#
# THE TRINITY (conversation-workflows-protocol.md): a GHL workflow, its
# communications playbook (Layer 2 markdown), and its workflow-AI / Build-with-AI
# prompt always travel together — one implies the other two. This script turns
# that prose rule into a check: a registry row (or on-disk workflow) that has a
# communications playbook but NO matching Build-with-AI prompt — or the reverse —
# is flagged INCOMPLETE.
#
# It runs against a client's installed conversation-workflows/ folder:
#   <MASTER_FILES_DIR>/conversation-workflows/
#     registry.md
#     <slug>.md                              (Layer 2 communications playbook)
#     <slug>--build-with-ai-prompt.md        (workflow-AI / Build-with-AI prompt)
#     <slug>--verification-checklist.md       (verification checklist)
#     <slug>--ghl-side.md                     (Layer 1 GHL routing mirror)
#
# A workflow is COMPLETE when BOTH exist:
#   <slug>.md                         (the communications playbook)
#   <slug>--build-with-ai-prompt.md   (the Build-with-AI prompt)
# unless the registry row marks Layer 1 as "No (uses existing inbound routing)",
# in which case the prompt is legitimately absent and only <slug>.md is required.
# (Legacy prompt filename <slug>--workflow-ai-prompt.md is also accepted.)
#
# Exit codes: 0 = every workflow complete; 1 = one or more incomplete;
#             3 = no conversation-workflows folder found.
#
# Usage:
#   bash scripts/qc-trinity-registry.sh                       # auto-locate via pointer file
#   bash scripts/qc-trinity-registry.sh --dir /path/to/conversation-workflows
#   bash scripts/qc-trinity-registry.sh --json

set -uo pipefail

WF_DIR=""
JSON_MODE=0

while [ $# -gt 0 ]; do
  case "$1" in
    --dir) WF_DIR="$2"; shift 2 ;;
    --json) JSON_MODE=1; shift ;;
    -h|--help) sed -n '1,40p' "$0"; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

# Auto-locate via the pointer file written by 01-locate-master-files-folder.sh.
if [ -z "$WF_DIR" ]; then
  POINTER="${HOME}/.openclaw/.skill-38-master-files-dir"
  if [ -f "$POINTER" ]; then
    MFD="$(cat "$POINTER")"; MFD="${MFD%$'\n'}"
    [ -n "$MFD" ] && WF_DIR="$MFD/conversation-workflows"
  fi
fi

if [ -z "$WF_DIR" ] || [ ! -d "$WF_DIR" ]; then
  if [ "$JSON_MODE" = "1" ]; then
    printf '{"verdict":"NO_FOLDER","dir":"%s"}\n' "${WF_DIR:-<unset>}"
  else
    echo "qc-trinity-registry: no conversation-workflows folder at '${WF_DIR:-<unset>}'."
    echo "  Pass --dir <path>, or run after 01-locate-master-files-folder.sh has written the pointer."
  fi
  exit 3
fi

export WF_DIR JSON_MODE

python3 - <<'PYEOF'
import json
import os
import re
import sys
from pathlib import Path

WF_DIR = Path(os.environ["WF_DIR"])
JSON_MODE = os.environ.get("JSON_MODE", "0") == "1"

PROMPT_SUFFIXES = ("--build-with-ai-prompt.md", "--workflow-ai-prompt.md")
RESERVED_SUFFIXES = ("--build-with-ai-prompt.md", "--workflow-ai-prompt.md",
                     "--verification-checklist.md", "--ghl-side.md")


def slug_from_playbook(name):
    """A Layer-2 playbook is <slug>.md that is NOT registry.md and NOT one of the
    reserved companion files."""
    if name == "registry.md" or not name.endswith(".md"):
        return None
    for suf in RESERVED_SUFFIXES:
        if name.endswith(suf):
            return None
    return name[:-3]


def has_prompt(slug):
    for suf in PROMPT_SUFFIXES:
        if (WF_DIR / f"{slug}{suf}").is_file():
            return True
    return False


# Parse the registry table to learn each row's Layer-1 disposition.
# Columns (from 09-install-conversation-workflows.sh / SKILL.md §F):
#   | ID | Name | Trigger summary | Layer 1? | OpenClaw playbook | GHL prompt | ... |
registry_rows = {}
reg = WF_DIR / "registry.md"
if reg.is_file():
    for line in reg.read_text(errors="ignore").splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 4:
            continue
        rid = cells[0]
        if not rid or rid.lower() in ("id", ":---", "---") or set(rid) <= set("-: "):
            continue
        layer1 = cells[3].lower() if len(cells) > 3 else ""
        # "No (uses existing inbound)" => prompt legitimately absent.
        layer1_needed = layer1.startswith("yes")
        registry_rows[rid] = {"layer1_needed": layer1_needed, "raw": cells}

# Discover on-disk slugs from playbook files AND from orphan prompt files.
playbook_slugs = set()
prompt_only_slugs = set()
for f in sorted(WF_DIR.iterdir()):
    if not f.is_file():
        continue
    s = slug_from_playbook(f.name)
    if s:
        playbook_slugs.add(s)
        continue
    for suf in PROMPT_SUFFIXES:
        if f.name.endswith(suf):
            prompt_only_slugs.add(f.name[: -len(suf)])

all_slugs = playbook_slugs | prompt_only_slugs | set(registry_rows.keys())

incomplete = []
complete = []
for slug in sorted(all_slugs):
    has_pb = (WF_DIR / f"{slug}.md").is_file()
    has_pr = has_prompt(slug)
    in_reg = slug in registry_rows
    layer1_needed = registry_rows.get(slug, {}).get("layer1_needed", None)

    problems = []
    # Playbook present but no prompt — unless registry says Layer 1 not needed.
    if has_pb and not has_pr:
        if layer1_needed is False:
            pass  # legitimately prompt-free (uses existing inbound routing)
        else:
            problems.append("Build-with-AI prompt MISSING (registry does not mark Layer 1 'No')")
    # Prompt present but no playbook (orphan prompt).
    if has_pr and not has_pb:
        problems.append("Build-with-AI prompt present but communications playbook <slug>.md MISSING")
    # Registered but nothing on disk.
    if in_reg and not has_pb and not has_pr:
        problems.append("registered in registry.md but no files on disk")
    # On disk but not registered.
    if (has_pb or has_pr) and not in_reg:
        problems.append("not registered in registry.md")

    rec = {"slug": slug, "playbook": has_pb, "prompt": has_pr,
           "registered": in_reg, "layer1_needed": layer1_needed,
           "problems": problems}
    (incomplete if problems else complete).append(rec)

if JSON_MODE:
    print(json.dumps({
        "dir": str(WF_DIR),
        "complete": [r["slug"] for r in complete],
        "incomplete": incomplete,
        "verdict": "PASS" if not incomplete else "FAIL",
    }, indent=2))
else:
    print("=== qc-trinity-registry: THE TRINITY completeness check ===")
    print(f"dir: {WF_DIR}")
    print("")
    for r in complete:
        note = " (Layer 1 not needed — prompt-free OK)" if r["layer1_needed"] is False else ""
        print(f"  [OK]   {r['slug']}{note}")
    for r in incomplete:
        print(f"  [INCOMPLETE] {r['slug']}")
        for p in r["problems"]:
            print(f"               - {p}")
    print("")
    if not all_slugs:
        print("RESULT: PASS — no workflows registered yet (nothing to check).")
    elif incomplete:
        print(f"RESULT: FAIL — {len(incomplete)} workflow(s) violate THE TRINITY.")
    else:
        print(f"RESULT: PASS — all {len(complete)} workflow(s) complete (playbook + prompt + registry).")

sys.exit(1 if incomplete else 0)
PYEOF
