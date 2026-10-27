#!/usr/bin/env bash
# qc-playbook-doc.sh — machine-enforce the MANDATORY per-playbook human-facing
# doc deliverable (Notion -> Google Docs -> plain-text fallback).
#
# LEGACY CLASSIFICATION (content only; never mtime): A file is NEW when any
# line matches PHASE_RE. A file is BROKEN when it has NO phase line BUT has a
# bare 'declares' line (strip fences, ln.strip().lower()=='declares') OR a line
# matching MODEL_RE. Otherwise it is LEGACY.
#
# Legacy files need migration, never PASS, but do not hard-fail install QC.
#
# WHAT IT SCANS — the client's conversation-workflows/registry.md. Every
# registered conversation playbook MUST carry a recorded human-facing doc:
#   * TABLE form: the trailing "Doc (Notion/Docs/text)" column carries a real
#     reference — a Notion URL, a Google Docs URL, an http(s) URL, or a
#     .md/.txt file path the client can access.
#   * BULLET form: the line carries a "[doc: <url-or-path>]" / "doc: <url-or-path>"
#     tail with the same kinds of reference.
#
# U-4 METADATA GRAMMAR: checks per-phase objective metadata against the documented
# grammar using tools/playbook_engine.py.
#
# Exit codes: 0 = pass or migration needed; 1 = a doc-column or metadata/grammar
#                 check failed, or a required validator prerequisite is missing;
#             2 = no registry/playbooks registered yet;
#             3 = no conversation-workflows folder found.
#
# Usage:
#   bash scripts/qc-playbook-doc.sh
#   bash scripts/qc-playbook-doc.sh --dir /path/to/conversation-workflows
#   bash scripts/qc-playbook-doc.sh --json

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ENGINE="$SKILL_ROOT/tools/playbook_engine.py"
PYTHON_BIN="$(command -v python3 2>/dev/null || true)"

WF_DIR=""
JSON_MODE=0

while [ $# -gt 0 ]; do
  case "$1" in
    --dir) WF_DIR="$2"; shift 2 ;;
    --json) JSON_MODE=1; shift ;;
    -h|--help) sed -n '1,70p' "$0"; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

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
    echo "qc-playbook-doc: no conversation-workflows folder at '${WF_DIR:-<unset>}'."
    echo "  Pass --dir <path>, or run after 01-locate-master-files-folder.sh has written the pointer."
  fi
  exit 3
fi

PYTHON_ERROR=""
if [ -z "$PYTHON_BIN" ]; then
  PYTHON_ERROR="command -v python3"
elif [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_ERROR="python3 executable check: $PYTHON_BIN"
elif ! "$PYTHON_BIN" -c "import sys" >/dev/null 2>&1; then
  PYTHON_ERROR="$PYTHON_BIN -c \"import sys\""
fi

if [ -n "$PYTHON_ERROR" ]; then
  if [ "$JSON_MODE" = "1" ]; then
    printf '{"gate":"qc-playbook-doc:prerequisites","verdict":"FAIL","reason":"required command failed: %s"}\n' "$PYTHON_ERROR" >&2
  else
    printf 'RESULT: FAIL — required command failed: %s\n' "$PYTHON_ERROR"
  fi
  exit 1
fi

export WF_DIR JSON_MODE ENGINE

"$PYTHON_BIN" - <<'PYEOF'
import json
import os
import re
import sys
from pathlib import Path

WF_DIR = Path(os.environ["WF_DIR"])
JSON_MODE = os.environ.get("JSON_MODE", "0") == "1"
ENGINE = Path(os.environ["ENGINE"])

sys.path.insert(0, str(ENGINE.parent))
import playbook_engine as engine

PHASE_RE = re.compile(r'^\s{0,3}#{2,4}\s*Phase\s*\d', re.IGNORECASE)
MODEL_RE = re.compile(r'^\s*\*{0,2}model-tier\*{0,2}\s*:', re.IGNORECASE)

URL_RE = re.compile(r'https?://\S+', re.IGNORECASE)
TXT_PATH_RE = re.compile(r'[^\s|]+\.(?:md|txt)\b', re.IGNORECASE)

RESERVED_DOC_SUFFIXES = ("--build-with-ai-prompt.md", "--workflow-ai-prompt.md",
                         "--verification-checklist.md", "--ghl-side.md")
RESERVED_SUFFIXES = RESERVED_DOC_SUFFIXES

EMPTY_TOKENS = {"", "n/a", "na", "none", "tbd", "todo", "to do", "pending",
                "-", "—", "...", "…"}


def classify_playbook(text):
    lines = engine._strip_fence(text.splitlines())
    has_phase = any(PHASE_RE.search(line) for line in lines)
    has_declares = any(line.strip().lower() == "declares" for line in lines)
    has_model = any(MODEL_RE.search(line) for line in lines)
    if has_phase:
        return "NEW"
    if has_declares or has_model:
        return "BROKEN"
    return "LEGACY"


def is_legacy_file(path):
    return path.is_file() and classify_playbook(
        path.read_text(encoding="utf-8", errors="ignore")
    ) == "LEGACY"


def _is_playbook_or_companion_file(path, slug):
    base = path.rsplit("/", 1)[-1]
    if slug is not None and base == f"{slug}.md":
        return True
    return any(base.endswith(suf) for suf in RESERVED_DOC_SUFFIXES)


def doc_ref_in(text, slug=None):
    if text is None:
        return None
    t = text.strip()
    low = t.strip().strip("`").strip().lower()
    if low in EMPTY_TOKENS:
        return None
    stripped_angles = re.sub(r'<[^>]*>', '', t)

    m = URL_RE.search(t)
    if m and m.group(0).strip("<>").strip():
        return m.group(0).rstrip(".,;)")

    m = TXT_PATH_RE.search(t)
    if m and stripped_angles:
        candidate = m.group(0)
        if _is_playbook_or_companion_file(candidate, slug):
            return None
        base = candidate.rsplit("/", 1)[-1].lower()
        if "/" in candidate or "doc" in base:
            return candidate
    return None


BULLET_RE = re.compile(r"^[-*]\s+([a-z0-9][a-z0-9-]*)\s*:\s+\S")
registry_rows = {}

RESERVED = ("--build-with-ai-prompt.md", "--workflow-ai-prompt.md",
            "--verification-checklist.md", "--ghl-side.md")


def slug_from_playbook(name):
    if name == "registry.md" or not name.endswith(".md"):
        return None
    if any(name.endswith(suf) for suf in RESERVED):
        return None
    return name[:-3]


def migration_command():
    return "bash scripts/33-migrate-legacy-playbooks.sh %s --write" % WF_DIR.resolve()


def print_legacy(legacy):
    for name in legacy:
        print("[NEEDS-MIGRATION] %s — legacy playbook (no '### Phase N', no declares, no model-tier:); NOT a pass. Fix: %s" % (name, migration_command()))
    print("legacy playbooks NEEDS-MIGRATION: %d" % len(legacy))


reg = WF_DIR / "registry.md"

if not reg.is_file():
    legacy = []
    has_non_legacy = False
    for f in sorted(WF_DIR.iterdir()):
        if not f.is_file() or not f.name.endswith(".md"):
            continue
        if slug_from_playbook(f.name) is None:
            continue
        if is_legacy_file(f):
            legacy.append(f.name)
        else:
            has_non_legacy = True

    all_legacy = bool(legacy) and not has_non_legacy
    if JSON_MODE:
        print(json.dumps({
            "dir": str(WF_DIR),
            "verdict": "NEEDS-MIGRATION" if all_legacy else "NO_PLAYBOOKS",
            "reason": "no registry.md",
            "legacy": legacy,
            "needs_migration": len(legacy),
        }, indent=2))
    else:
        print("=== qc-playbook-doc: per-playbook human-facing doc gate ===")
        print(f"dir: {WF_DIR}")
        print("")
        print_legacy(legacy)
        if all_legacy:
            print("RESULT: NEEDS-MIGRATION - %d legacy playbook(s) need migration; nothing else failed. They are not PASS." % len(legacy))
        else:
            print("RESULT: NO PLAYBOOKS — registry.md absent; nothing to check (exit 2, not a blind PASS).")
    sys.exit(0 if all_legacy else 2)

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
        rid = cells[0].strip("`").strip()
        if not rid or rid.lower() in ("id", ":---", "---") or set(rid) <= set("-: "):
            continue
        doc = None
        for c in cells:
            r = doc_ref_in(c, slug=rid)
            if r:
                doc = r
                break
        registry_rows[rid] = {"doc": doc, "shape": "table"}
        continue

    if in_active:
        if "<" in stripped or "`" in stripped:
            continue
        m = BULLET_RE.match(stripped)
        if m:
            rid = m.group(1)
            doc = doc_ref_in(stripped, slug=rid)
            registry_rows.setdefault(rid, {"doc": doc, "shape": "bullet"})


disk_files = {}
for f in sorted(WF_DIR.iterdir()):
    if f.is_file():
        slug = slug_from_playbook(f.name)
        if slug:
            disk_files[slug] = f

disk_slugs = set(disk_files)
all_slugs = set(registry_rows.keys()) | disk_slugs

if not all_slugs:
    if JSON_MODE:
        print(json.dumps({
            "dir": str(WF_DIR),
            "verdict": "NO_PLAYBOOKS",
            "legacy": [],
            "needs_migration": 0,
        }, indent=2))
    else:
        print("=== qc-playbook-doc: per-playbook human-facing doc gate ===")
        print(f"dir: {WF_DIR}")
        print("")
        print("legacy playbooks NEEDS-MIGRATION: 0")
        print("RESULT: NO PLAYBOOKS — none registered or on disk; nothing to check (exit 2, not a blind PASS).")
    sys.exit(2)

results = []
legacy = []
for slug in sorted(all_slugs):
    row = registry_rows.get(slug)
    doc = row["doc"] if row else None
    disk_file = disk_files.get(slug)

    if disk_file is not None and is_legacy_file(disk_file):
        legacy.append(disk_file.name)
        continue

    problems = []
    if slug not in registry_rows:
        problems.append("playbook on disk but NOT registered in registry.md (so no doc can be recorded)")
    if not doc:
        problems.append("no recorded human-facing doc (Notion URL / Google Docs URL / .md|.txt path) — "
                        "the Notion->Google Docs->text deliverable was skipped or not recorded")
    results.append({"slug": slug, "doc": doc, "problems": problems})

failures = [r for r in results if r["problems"]]
verdict = "FAIL" if failures else ("NEEDS-MIGRATION" if legacy else "PASS")

if JSON_MODE:
    print(json.dumps({
        "dir": str(WF_DIR),
        "playbooks": results,
        "verdict": verdict,
        "legacy": legacy,
        "needs_migration": len(legacy),
    }, indent=2))
else:
    print("=== qc-playbook-doc: per-playbook human-facing doc gate ===")
    print(f"dir: {WF_DIR}")
    print("")
    for r in results:
        if r["problems"]:
            print(f"  [FAIL] {r['slug']}")
            for p in r["problems"]:
                print(f"          - {p}")
        else:
            print(f"  [OK]   {r['slug']}  (doc: {r['doc']})")
    print_legacy(legacy)
    print("")
    if failures:
        print(f"RESULT: FAIL — {len(failures)} registered playbook(s) have NO recorded human-facing doc. "
              "Create it in the client's account (Notion -> Google Docs -> text) and record the URL/path "
              "in the registry's 'Doc (Notion/Docs/text)' column.")
    elif legacy:
        print("RESULT: NEEDS-MIGRATION - %d legacy playbook(s) need migration; nothing else failed. They are not PASS." % len(legacy))
    else:
        print(f"RESULT: PASS — all {len(results)} playbook(s) have a recorded human-facing doc.")

sys.exit(1 if failures else 0)
PYEOF
DOC_RC=$?

META_RC=0
PYTHON_VERSION="$("$PYTHON_BIN" --version 2>&1)"
if [ $? -ne 0 ] || [ -z "$PYTHON_VERSION" ]; then
  PYTHON_ERROR="$PYTHON_BIN --version"
  META_RC=1
elif [ ! -f "$ENGINE" ] || [ ! -r "$ENGINE" ]; then
  META_RC=1
  if [ "$JSON_MODE" = "1" ]; then
    printf '{"gate":"qc-playbook-doc:metadata","verdict":"FAIL","reason":"canonical validator SKIPPED — engine missing or unreadable: %s","playbooks_checked":0,"defects":[]}\n' "$ENGINE" >&2
  else
    printf '\n=== qc-playbook-doc: U-4 objective-metadata grammar (via playbook_engine.py) ===\n'
    printf 'canonical validator SKIPPED — engine missing or unreadable: %s\n' "$ENGINE"
    printf 'playbooks checked: 0\n'
    printf 'RESULT: FAIL - required canonical validator unavailable.\n'
  fi
elif ! "$PYTHON_BIN" -c "import sys" >/dev/null 2>&1; then
  PYTHON_ERROR="$PYTHON_BIN -c \"import sys\""
  META_RC=1
fi

if [ "$META_RC" -ne 0 ] && [ -n "${PYTHON_ERROR:-}" ]; then
  if [ "$JSON_MODE" = "1" ]; then
    printf '{"gate":"qc-playbook-doc:metadata","verdict":"FAIL","reason":"required command failed: %s","engine":"%s","python3":"%s","playbooks_checked":0,"defects":[]}\n' "$PYTHON_ERROR" "$ENGINE" "$PYTHON_BIN" >&2
  else
    printf '\n=== qc-playbook-doc: U-4 objective-metadata grammar (via playbook_engine.py) ===\n'
    printf 'required command failed: %s\n' "$PYTHON_ERROR"
    printf 'playbooks checked: 0\n'
    printf 'RESULT: FAIL - required metadata prerequisite unavailable.\n'
  fi
fi

if [ "$META_RC" -eq 0 ]; then
  export WF_DIR ENGINE JSON_MODE PYTHON_BIN PYTHON_VERSION
  "$PYTHON_BIN" - <<'PYEOF2'
import json
import os
import re
import sys
from pathlib import Path

ENGINE = Path(os.environ["ENGINE"])
WF_DIR = os.environ.get("WF_DIR", "")
JSON_MODE = os.environ.get("JSON_MODE", "0") == "1"
PYTHON_BIN = os.environ["PYTHON_BIN"]
PYTHON_VERSION = os.environ["PYTHON_VERSION"]

PHASE_RE = re.compile(r'^\s{0,3}#{2,4}\s*Phase\s*\d', re.IGNORECASE)
MODEL_RE = re.compile(r'^\s*\*{0,2}model-tier\*{0,2}\s*:', re.IGNORECASE)

defects = []
legacy = []
checked = 0
wf = Path(WF_DIR) if WF_DIR else None

try:
    sys.path.insert(0, str(ENGINE.parent))
    import playbook_engine as engine

    RESERVED = ("--build-with-ai-prompt.md", "--workflow-ai-prompt.md",
                "--verification-checklist.md", "--ghl-side.md")

    def classify_playbook(text):
        lines = engine._strip_fence(text.splitlines())
        has_phase = any(PHASE_RE.search(line) for line in lines)
        has_declares = any(line.strip().lower() == "declares" for line in lines)
        has_model = any(MODEL_RE.search(line) for line in lines)
        if has_phase:
            return "NEW"
        if has_declares or has_model:
            return "BROKEN"
        return "LEGACY"

    if wf and wf.is_dir():
        for f in sorted(wf.iterdir()):
            if not f.is_file() or not f.name.endswith(".md"):
                continue
            if f.name == "registry.md" or any(f.name.endswith(s) for s in RESERVED):
                continue

            text = f.read_text(encoding="utf-8", errors="ignore")
            if classify_playbook(text) == "LEGACY":
                legacy.append(f.name)
                continue

            checked += 1
            parsed = engine.parse_playbook(text)

            vdef = engine.validate_playbook(parsed)
            for d in vdef:
                if d.startswith("no phases found") and not parsed["phases"]:
                    continue
                defects.append("%s: %s" % (f.name, d))
            if not parsed["phases"]:
                defects.append("%s has no \"### Phase N\" block (not a Layer-2 playbook)" % f.name)

            mt = parsed["header"]["model_tier"]
            if mt is not None and mt not in engine.MODEL_TIERS:
                defects.append("%s header model-tier '%s' is not one of %s"
                               % (f.name, mt, ", ".join(sorted(engine.MODEL_TIERS))))
            for ph in parsed["phases"]:
                label = "%s Phase %s (%s)" % (f.name, ph["number"], ph["name"] or "unnamed")
                ma = ph.get("max_attempts")
                if ma is not None and (not ma.isdigit() or int(ma) < 1):
                    defects.append("%s max-attempts '%s' must be a positive integer" % (label, ma))
                if ph.get("gate_if_not_met") and not ph.get("gate_closing"):
                    defects.append("%s gate-if-not-met requires a 'closing:' message per the grammar" % label)
                sif = ph.get("skip_if_field_filled")
                if sif is not None and sif.strip() == "":
                    defects.append("%s skip-if-field-filled must name a field" % label)
except Exception as exc:
    defects.append("canonical validator execution failed: %s: %s" % (type(exc).__name__, exc))

resolved_wf = str(Path(WF_DIR).resolve()) if WF_DIR else "<ABSOLUTE_WORKFLOWS_DIR>"
migration_command = "bash scripts/33-migrate-legacy-playbooks.sh %s --write" % resolved_wf
verdict = "FAIL" if defects else ("NEEDS-MIGRATION" if legacy else "PASS")

if JSON_MODE:
    print(json.dumps({
        "gate": "qc-playbook-doc:metadata",
        "verdict": verdict,
        "playbooks_checked": checked,
        "defects": defects,
        "engine": str(ENGINE),
        "python3": PYTHON_BIN,
        "python3_version": PYTHON_VERSION,
        "legacy": legacy,
        "needs_migration": len(legacy),
    }, indent=2), file=sys.stderr)
else:
    print("")
    print("=== qc-playbook-doc: U-4 objective-metadata grammar (via playbook_engine.py) ===")
    print("prerequisites verified:")
    print("  engine: %s (readable)" % ENGINE)
    print("  python3: %s" % PYTHON_BIN)
    print("  python3 --version: %s" % PYTHON_VERSION)
    print("playbooks checked: %d" % checked)
    for name in legacy:
        print("[NEEDS-MIGRATION] %s — legacy playbook (no '### Phase N', no declares, no model-tier:); NOT a pass. Fix: %s" % (name, migration_command))
    print("legacy playbooks NEEDS-MIGRATION: %d" % len(legacy))
    if defects:
        for d in defects:
            print("  [FAIL] %s" % d)
        print("RESULT: FAIL - %d metadata-grammar defect(s)." % len(defects))
    elif legacy:
        print("RESULT: NEEDS-MIGRATION - %d legacy playbook(s) need migration; nothing else failed. They are not PASS." % len(legacy))
    else:
        print("RESULT: PASS - every present metadata line parses against the grammar.")

sys.exit(1 if defects else 0)
PYEOF2
  META_RC=$?
fi

if [ "$DOC_RC" -eq 0 ] && [ "$META_RC" -eq 0 ]; then
  exit 0
fi
if [ "$DOC_RC" -eq 2 ]; then
  exit 2
fi
exit 1
