#!/usr/bin/env bash
# qc-trinity-registry.sh — machine-enforce THE TRINITY at register/QC time.
#
# THE TRINITY requires four legs for every registered workflow:
#   1. <slug>.md                              (communications playbook)
#   2. <slug>--build-with-ai-prompt.md       (Build-with-AI prompt)
#      Legacy <slug>--workflow-ai-prompt.md is accepted with a WARN.
#      Registry Layer 1 "No" exempts only this leg.
#   3. A matching row in registry.md.
#   4. <slug>--build-contract.json with a playbook_structure_hash matching
#      the freshly computed structure hash from the canonical playbook_engine.
#
# An empty conversation-workflows folder is NOT a pass. The Trinity cannot
# be proven vacuously. A missing folder and an empty registry both exit 3.
#
# Exit codes: 0 = all requested/discovered workflows complete;
#             1 = one or more workflows incomplete;
#             3 = no folder found OR folder has zero registered/discovered workflows;
#             4 = one or more requested --slug values are not registered/discovered.
#
# Warnings never change exit codes.
#
# Usage:
#   bash scripts/qc-trinity-registry.sh
#   bash scripts/qc-trinity-registry.sh --dir /path/to/conversation-workflows
#   bash scripts/qc-trinity-registry.sh --slug workflow-a
#   bash scripts/qc-trinity-registry.sh --slug workflow-a --slug workflow-b
#   bash scripts/qc-trinity-registry.sh --json
#   bash scripts/qc-trinity-registry.sh --dir /path/to/conversation-workflows --slug workflow-a --json

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

WF_DIR=""
JSON_MODE=0
SLUGS=()

while [ $# -gt 0 ]; do
  case "$1" in
    --dir)
      if [ $# -lt 2 ]; then
        echo "Missing value for --dir" >&2
        exit 2
      fi
      WF_DIR="$2"
      shift 2
      ;;
    --slug)
      if [ $# -lt 2 ]; then
        echo "Missing value for --slug" >&2
        exit 2
      fi
      SLUGS+=("$2")
      shift 2
      ;;
    --json)
      JSON_MODE=1
      shift
      ;;
    -h|--help)
      sed -n '1,45p' "$0"
      exit 0
      ;;
    *)
      echo "Unknown arg: $1" >&2
      exit 2
      ;;
  esac
done

# Auto-locate via the pointer file written by 01-locate-master-files-folder.sh.
if [ -z "$WF_DIR" ]; then
  POINTER="${HOME}/.openclaw/.skill-38-master-files-dir"
  if [ -f "$POINTER" ]; then
    MFD="$(cat "$POINTER")"
    MFD="${MFD%$'\n'}"
    [ -n "$MFD" ] && WF_DIR="$MFD/conversation-workflows"
  fi
fi

if [ -z "$WF_DIR" ] || [ ! -d "$WF_DIR" ]; then
  if [ "$JSON_MODE" = "1" ]; then
    python3 - "$WF_DIR" <<'PYEOF'
import json
import sys
print(json.dumps({
    "verdict": "NO_FOLDER",
    "dir": sys.argv[1] or "<unset>",
    "message": "conversation-workflows folder not found",
}, indent=2))
PYEOF
  else
    echo "qc-trinity-registry: no conversation-workflows folder at '${WF_DIR:-<unset>}'."
    echo "  Pass --dir <path>, or run after 01-locate-master-files-folder.sh has written the pointer."
  fi
  exit 3
fi

export WF_DIR JSON_MODE SKILL_ROOT

python3 - "${SLUGS[@]}" <<'PYEOF'
import json
import os
import re
import sys
from pathlib import Path

WF_DIR = Path(os.environ["WF_DIR"])
JSON_MODE = os.environ.get("JSON_MODE", "0") == "1"
SKILL_ROOT = Path(os.environ["SKILL_ROOT"])
REQUESTED_SLUGS = sys.argv[1:]

PROMPT_SUFFIXES = ("--build-with-ai-prompt.md", "--workflow-ai-prompt.md")
RESERVED_SUFFIXES = (
    "--build-with-ai-prompt.md",
    "--workflow-ai-prompt.md",
    "--verification-checklist.md",
    "--ghl-side.md",
)


def slug_from_playbook(name):
    """Return slug for a playbook, excluding registry and companion files."""
    if name == "registry.md" or not name.endswith(".md"):
        return None
    for suffix in RESERVED_SUFFIXES:
        if name.endswith(suffix):
            return None
    return name[:-3]


def prompt_for_slug(slug):
    """Return (found, legacy); prefer canonical prompt filename."""
    canonical = WF_DIR / f"{slug}--build-with-ai-prompt.md"
    legacy = WF_DIR / f"{slug}--workflow-ai-prompt.md"
    if canonical.is_file():
        return True, False
    if legacy.is_file():
        return True, True
    return False, False


def emit_json(payload):
    print(json.dumps(payload, indent=2))


# Load canonical engine. Failure must never silently pass leg 4.
playbook_engine = None
try:
    sys.path.insert(0, str(SKILL_ROOT / "tools"))
    import playbook_engine as _playbook_engine
    playbook_engine = _playbook_engine
except Exception:
    playbook_engine = None


# Parse registry. Keep existing table and active-workflows bullet parsing.
registry_rows = {}

BULLET_RE = re.compile(r"^[-*]\s+([a-z0-9][a-z0-9-]*)\s*:\s+\S")

reg = WF_DIR / "registry.md"
if reg.is_file():
    in_active = False
    for line in reg.read_text(errors="ignore").splitlines():
        stripped = line.strip()

        if stripped.startswith("#"):
            heading = stripped.lstrip("#").strip().lower()
            in_active = heading.startswith("active workflow")
            continue

        if stripped.startswith("|"):
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            if len(cells) < 4:
                continue
            rid = cells[0]
            rid = rid.strip("`")
            if not rid or rid.lower() in ("id", ":---", "---") or set(rid) <= set("-: "):
                continue
            layer1 = cells[3].lower() if len(cells) > 3 else ""
            layer1_needed = layer1.startswith("yes")
            registry_rows[rid] = {"layer1_needed": layer1_needed, "raw": cells}
            continue

        if in_active:
            if "<" in stripped or "`" in stripped:
                continue
            match = BULLET_RE.match(stripped)
            if match:
                rid = match.group(1)
                registry_rows.setdefault(
                    rid, {"layer1_needed": None, "raw": [rid]}
                )

# Discover playbooks and orphan prompts, then union with registry rows.
playbook_slugs = set()
prompt_only_slugs = set()

for f in sorted(WF_DIR.iterdir()):
    if not f.is_file():
        continue
    slug = slug_from_playbook(f.name)
    if slug:
        playbook_slugs.add(slug)
        continue
    for suffix in PROMPT_SUFFIXES:
        if f.name.endswith(suffix):
            prompt_only_slugs.add(f.name[:-len(suffix)])

discovered_slugs = playbook_slugs | prompt_only_slugs | set(registry_rows.keys())

# Requested slugs must already exist in registry or on disk.
missing_requested = sorted(set(REQUESTED_SLUGS) - discovered_slugs)
if missing_requested:
    if JSON_MODE:
        emit_json({
            "dir": str(WF_DIR),
            "verdict": "SLUG_NOT_REGISTERED",
            "missing_slugs": missing_requested,
            "message": "requested slug is not registered or discovered on disk",
            "complete": [],
            "incomplete": [],
            "warnings": [],
        })
    else:
        for slug in missing_requested:
            print(f"SLUG_NOT_REGISTERED: {slug}")
    sys.exit(4)

all_slugs = (
    set(REQUESTED_SLUGS)
    if REQUESTED_SLUGS
    else discovered_slugs
)

# Empty registry/discovery is never a pass.
if not all_slugs:
    message = (
        "conversation-workflows folder has zero registered playbooks "
        "(the Trinity cannot be proven vacuously)"
    )
    if JSON_MODE:
        emit_json({
            "dir": str(WF_DIR),
            "verdict": "EMPTY_REGISTRY",
            "message": message,
            "complete": [],
            "incomplete": [],
            "warnings": [],
        })
    else:
        print("=== qc-trinity-registry: THE TRINITY four-leg completeness check ===")
        print(f"dir: {WF_DIR}")
        print("")
        print(f"RESULT: FAIL — {message}.")
    sys.exit(3)

incomplete = []
complete = []
warnings = []

for slug in sorted(all_slugs):
    playbook_path = WF_DIR / f"{slug}.md"
    contract_path = WF_DIR / f"{slug}--build-contract.json"

    has_pb = playbook_path.is_file()
    has_pr, legacy_prompt = prompt_for_slug(slug)
    in_reg = slug in registry_rows
    layer1_needed = registry_rows.get(slug, {}).get("layer1_needed")

    problems = []
    slug_warnings = []

    # Leg 1: communications playbook.
    if not has_pb:
        problems.append("communications playbook MISSING (<slug>.md)")

    # Leg 2: Build-with-AI prompt; registry Layer 1 "No" exempts only this leg.
    if not has_pr:
        if layer1_needed is not False:
            problems.append(
                "Build-with-AI prompt MISSING (registry does not mark Layer 1 'No')"
            )
    elif legacy_prompt:
        warning = (
            f"legacy prompt filename {slug}--workflow-ai-prompt.md; "
            f"rename to {slug}--build-with-ai-prompt.md"
        )
        slug_warnings.append(warning)
        warnings.append({"slug": slug, "message": warning})

    # Leg 3: registry row.
    if not in_reg:
        problems.append("not registered in registry.md")

    # Preserve existing orphan/reconciliation diagnostics.
    if has_pr and not has_pb:
        problems.append(
            "Build-with-AI prompt present but communications playbook <slug>.md MISSING"
        )
    if in_reg and not has_pb and not has_pr:
        problems.append("registered in registry.md but no files on disk")

    # Leg 4: build contract and freshly computed canonical structure hash.
    if playbook_engine is None:
        problems.append(
            "build contract cannot be verified (playbook_engine.py unavailable)"
        )
    elif not contract_path.is_file():
        problems.append(f"build contract MISSING ({slug}--build-contract.json)")
    else:
        try:
            contract = json.loads(contract_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            problems.append("build contract is unreadable JSON")
        else:
            if not isinstance(contract, dict):
                problems.append("build contract is unreadable JSON")
            elif "playbook_structure_hash" not in contract:
                problems.append("build contract is missing playbook_structure_hash")
            elif has_pb:
                try:
                    text = playbook_path.read_text(encoding="utf-8")
                    fresh_hash = playbook_engine.structure_hash(
                        playbook_engine.parse_playbook(text)
                    )
                except Exception:
                    problems.append(
                        "build contract is stale: playbook_structure_hash does not match the current playbook"
                    )
                else:
                    if contract["playbook_structure_hash"] != fresh_hash:
                        problems.append(
                            "build contract is stale: playbook_structure_hash does not match the current playbook"
                        )
            else:
                problems.append(
                    "build contract is stale: playbook_structure_hash does not match the current playbook"
                )

    rec = {
        "slug": slug,
        "playbook": has_pb,
        "prompt": has_pr,
        "registered": in_reg,
        "layer1_needed": layer1_needed,
        "build_contract": contract_path.is_file(),
        "warnings": slug_warnings,
        "problems": problems,
    }
    (incomplete if problems else complete).append(rec)

if JSON_MODE:
    emit_json({
        "dir": str(WF_DIR),
        "complete": [r["slug"] for r in complete],
        "incomplete": incomplete,
        "warnings": warnings,
        "verdict": "PASS" if not incomplete else "FAIL",
    })
else:
    print("=== qc-trinity-registry: THE TRINITY four-leg completeness check ===")
    print(f"dir: {WF_DIR}")
    print("")
    for rec in complete:
        note = (
            " (Layer 1 not needed — prompt-free OK)"
            if rec["layer1_needed"] is False
            else ""
        )
        print(f"  [OK]   {rec['slug']}{note}")
    for rec in incomplete:
        print(f"  [INCOMPLETE] {rec['slug']}")
        for problem in rec["problems"]:
            print(f"               - {problem}")
    for warning in warnings:
        print(f"  [WARN] {warning['slug']}: {warning['message']}")
    print("")
    if incomplete:
        print(
            f"RESULT: FAIL — {len(incomplete)} workflow(s) fail four-leg "
            "Trinity validation (playbook + prompt rule + registry + build contract)."
        )
    else:
        print(
            f"RESULT: PASS — all {len(complete)} workflow(s) satisfy four-leg "
            "Trinity validation (playbook + prompt rule + registry + build contract)."
        )

sys.exit(1 if incomplete else 0)
PYEOF
