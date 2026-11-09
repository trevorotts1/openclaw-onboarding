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
# UNINITIALISED means no playbooks could be verified; it is never a PASS.
# Discovery faults fail closed with verdict FAIL.
#
# STATUS FILE: --status-file PATH writes compact JSON with exactly these keys:
# gate, legacy_needs_migration, new_style_failures, verdict, legacy_files,
# workflows_dir. new_style_failures > 0 means FAIL; otherwise legacy_needs_migration
# > 0 means NEEDS-MIGRATION; otherwise PASS. Exit codes remain unchanged;
# NEEDS-MIGRATION exits 0 for fleet updates. Callers MUST treat missing or
# unparseable status files as failure, never PASS; completion depends on status.
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
DIR_SUPPLIED=0
JSON_MODE=0
STATUS_FILE=""

while [ $# -gt 0 ]; do
  case "$1" in
    --dir) WF_DIR="$2"; DIR_SUPPLIED=1; shift 2 ;;
    --json) JSON_MODE=1; shift ;;
    --status-file) STATUS_FILE="$2"; shift 2 ;;
    -h|--help) sed -n '1,70p' "$0"; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

POINTER="${HOME}/.openclaw/.skill-38-master-files-dir"
WF_ORIGIN="none"
WF_FAULT=""
if [ "$DIR_SUPPLIED" -eq 1 ]; then
  WF_ORIGIN="arg"
  if [ ! -d "$WF_DIR" ]; then
    WF_FAULT="explicit --dir path does not exist: $WF_DIR"
  fi
elif [ -f "$POINTER" ]; then
  WF_ORIGIN="pointer"
  if ! MFD="$(cat "$POINTER")"; then
    WF_FAULT="pointer file $POINTER is unreadable"
  else
    MFD="${MFD%$'\n'}"
    MFD="${MFD%$'\r'}"
    if [ -z "$MFD" ]; then
      WF_FAULT="pointer file $POINTER is empty; cannot locate the master files dir"
    elif [ ! -d "$MFD/conversation-workflows" ]; then
      WF_FAULT="pointer file $POINTER points at $MFD/conversation-workflows, which does not exist"
    else
      WF_DIR="$MFD/conversation-workflows"
    fi
  fi
fi
if [ -n "$WF_DIR" ] && [ -d "$WF_DIR" ] && { [ ! -r "$WF_DIR" ] || [ ! -x "$WF_DIR" ]; }; then
  WF_FAULT="workflows dir $WF_DIR is present but unreadable (permission denied)"
fi

write_early_status() {
  local verdict="$1"
  local failures="$2"
  local dir="$3"
  if [ -n "$STATUS_FILE" ] && command -v python3 >/dev/null 2>&1; then
    STATUS_FILE="$STATUS_FILE" STATUS_VERDICT="$verdict" STATUS_FAILURES="$failures" STATUS_DIR="$dir" python3 - <<'PYSTATUS'
import json, os
status = {
    "gate":"qc-playbook-doc",
    "legacy_needs_migration":0,
    "new_style_failures":int(os.environ["STATUS_FAILURES"]),
    "verdict":os.environ["STATUS_VERDICT"],
    "legacy_files":[],
    "workflows_dir":os.environ["STATUS_DIR"],
}
try:
    with open(os.environ["STATUS_FILE"], "w", encoding="utf-8") as f:
        f.write(json.dumps(status, separators=(",",":")) + "\n")
except OSError:
    pass
PYSTATUS
  fi
}

if [ -n "$WF_FAULT" ]; then
  printf 'qc-playbook-doc: FAIL - %s\n' "$WF_FAULT"
  write_early_status "FAIL" 1 "$( [ -n "$WF_DIR" ] && python3 -c 'import os,sys; print(os.path.abspath(sys.argv[1]))' "$WF_DIR" 2>/dev/null || true )"
  exit 1
fi

if [ "$WF_ORIGIN" = "none" ]; then
  if [ "$JSON_MODE" = "1" ]; then
    printf '{"gate":"qc-playbook-doc","legacy_needs_migration":0,"new_style_failures":0,"verdict":"UNINITIALISED","legacy_files":[],"workflows_dir":""}\n'
  else
    echo "qc-playbook-doc: UNINITIALISED - no conversation-workflows folder and no pointer file at $POINTER; 0 playbooks examined; this is NOT a PASS."
  fi
  write_early_status "UNINITIALISED" 0 ""
  exit 3
fi

if [ ! -r "$WF_DIR" ] || [ ! -x "$WF_DIR" ]; then
  printf 'qc-playbook-doc: FAIL - workflows dir %s is present but unreadable (permission denied)\n' "$WF_DIR"
  write_early_status "FAIL" 1 "$(python3 -c 'import os,sys; print(os.path.abspath(sys.argv[1]))' "$WF_DIR" 2>/dev/null || true)"
  exit 1
fi

REGISTRY="$WF_DIR/registry.md"
if [ -e "$REGISTRY" ] && [ ! -r "$REGISTRY" ]; then
  printf 'qc-playbook-doc: FAIL - registry.md is unreadable: %s (permission denied)\n' "$REGISTRY"
  write_early_status "FAIL" 1 "$(python3 -c 'import os,sys; print(os.path.abspath(sys.argv[1]))' "$WF_DIR" 2>/dev/null || true)"
  exit 1
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

export WF_DIR WF_ORIGIN WF_FAULT JSON_MODE ENGINE STATUS_FILE

"$PYTHON_BIN" - <<'PYEOF'
import json
import os
import re
import sys
from pathlib import Path

WF_DIR = Path(os.environ["WF_DIR"])
JSON_MODE = os.environ.get("JSON_MODE", "0") == "1"
ENGINE = Path(os.environ["ENGINE"])
STATUS_FILE = os.environ.get("STATUS_FILE", "")

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
    try:
        return path.is_file() and classify_playbook(
            path.read_text(encoding="utf-8", errors="ignore")
        ) == "LEGACY"
    except OSError as exc:
        failures.append("%s: unreadable (%s)" % (path, exc.strerror or str(exc)))
        return False


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
failures = []

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
    try:
        disk_candidates = sorted(WF_DIR.iterdir())
    except OSError as exc:
        failures.append("%s: unreadable (%s)" % (WF_DIR, exc.strerror or str(exc)))
        disk_candidates = []
    for f in disk_candidates:
        try:
            if not f.is_file() or not f.name.endswith(".md"):
                continue
            if slug_from_playbook(f.name) is None:
                continue
            if is_legacy_file(f):
                legacy.append(f.name)
            else:
                has_non_legacy = True
        except OSError as exc:
            failures.append("%s: unreadable (%s)" % (f, exc.strerror or str(exc)))
    all_legacy = bool(legacy) and not has_non_legacy and not failures
    # An empty directory has nothing to check: that is UNINITIALISED with zero
    # failures, the same state the other three gates report. It is not a FAIL —
    # inventing a failure count of 1 for "no playbooks exist yet" made a fresh
    # box look broken and made the status file disagree with the exit code.
    if failures:
        verdict = "FAIL"
        new_failures = len(failures)
    elif not legacy and not has_non_legacy:
        verdict = "UNINITIALISED"
        new_failures = 0
    elif all_legacy:
        verdict = "NEEDS-MIGRATION"
        new_failures = 0
    else:
        verdict = "FAIL"
        new_failures = 1
    if STATUS_FILE:
        status = {"gate":"qc-playbook-doc","legacy_needs_migration":len(legacy) if all_legacy else 0,"new_style_failures":new_failures,"verdict":verdict,"legacy_files":sorted(legacy) if all_legacy else [],"workflows_dir":str(WF_DIR.resolve())}
        try:
            with open(STATUS_FILE + ".doc", "w", encoding="utf-8") as f:
                f.write(json.dumps(status, separators=(",",":")) + "\n")
        except OSError:
            pass
    if JSON_MODE:
        print(json.dumps({
            "dir": str(WF_DIR),
            # Report the verdict actually computed, not a label of its own: a
            # consumer reading this JSON and a consumer reading the status file
            # must not be told two different things about the same run.
            "verdict": verdict,
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
        elif failures:
            for msg in failures:
                print("  [FAIL] %s" % msg)
            print("RESULT: FAIL - unreadable playbook content.")
        elif verdict == "UNINITIALISED":
            print("RESULT: UNINITIALISED — registry.md absent and no playbooks on disk; 0 playbooks examined; this is NOT a PASS.")
        else:
            print("RESULT: FAIL - playbooks exist but registry.md is absent, so their human-facing docs cannot be recorded or checked.")
    # The exit code follows the verdict, so a FAIL can never leave as 2 and an
    # UNINITIALISED can never leave as 1.
    sys.exit(1 if verdict == "FAIL" else (0 if verdict in ("PASS", "NEEDS-MIGRATION") else 2))

try:
    registry_text = reg.read_text(encoding="utf-8", errors="ignore")
except OSError as exc:
    failures.append("registry.md is unreadable: %s (%s)" % (reg, exc.strerror or str(exc)))
    if STATUS_FILE:
        status = {"gate":"qc-playbook-doc","legacy_needs_migration":0,"new_style_failures":1,"verdict":"FAIL","legacy_files":[],"workflows_dir":str(WF_DIR.resolve())}
        try:
            with open(STATUS_FILE + ".doc", "w", encoding="utf-8") as f:
                f.write(json.dumps(status, separators=(",",":")) + "\n")
        except OSError:
            pass
    for msg in failures:
        print("  [FAIL] %s" % msg)
    print("RESULT: FAIL - registry.md is unreadable.")
    sys.exit(1)

in_active = False
for line in registry_text.splitlines():
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

try:
    disk_candidates = sorted(WF_DIR.iterdir())
except OSError as exc:
    failures.append("%s: unreadable (%s)" % (WF_DIR, exc.strerror or str(exc)))
    disk_candidates = []

disk_files = {}
for f in disk_candidates:
    try:
        if f.is_file():
            slug = slug_from_playbook(f.name)
            if slug:
                disk_files[slug] = f
    except OSError as exc:
        failures.append("%s: unreadable (%s)" % (f, exc.strerror or str(exc)))

disk_slugs = set(disk_files)
all_slugs = set(registry_rows.keys()) | disk_slugs

if not all_slugs:
    # Nothing on disk and nothing registered is UNINITIALISED, not FAIL, and it
    # carries zero failures — the same state the other three gates report. This
    # used to write verdict FAIL with a fabricated failure count of 1 while
    # exiting 2, so the status file, the exit code and the printed text each
    # told the caller something different about the same run.
    if STATUS_FILE:
        try:
            with open(STATUS_FILE + ".doc", "w", encoding="utf-8") as f:
                f.write(json.dumps({"gate":"qc-playbook-doc","legacy_needs_migration":0,"new_style_failures":0,"verdict":"UNINITIALISED","legacy_files":[],"workflows_dir":str(WF_DIR.resolve())}, separators=(",",":")) + "\n")
        except OSError:
            pass
    if JSON_MODE:
        print(json.dumps({
            "dir": str(WF_DIR),
            "verdict": "UNINITIALISED",
            "reason": "no playbooks registered and none on disk",
            "legacy": [],
            "needs_migration": 0,
        }, indent=2))
    else:
        print("=== qc-playbook-doc: per-playbook human-facing doc gate ===")
        print(f"dir: {WF_DIR}")
        print("")
        print("legacy playbooks NEEDS-MIGRATION: 0")
        print("RESULT: UNINITIALISED — none registered or on disk; 0 playbooks examined; this is NOT a PASS.")
    sys.exit(1 if failures else 2)

non_legacy_on_disk = False
for path in disk_files.values():
    if not is_legacy_file(path):
        non_legacy_on_disk = True
if not registry_rows and non_legacy_on_disk:
    failures.append("registry.md at %s is malformed: parsed 0 entries; cannot verify recorded docs" % reg)

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

doc_failures = [r for r in results if r["problems"]]
if failures:
    verdict = "FAIL"
elif not results and not legacy:
    verdict = "UNINITIALISED"
elif doc_failures:
    verdict = "FAIL"
elif legacy:
    verdict = "NEEDS-MIGRATION"
else:
    verdict = "PASS"

if STATUS_FILE:
    status = {"gate":"qc-playbook-doc","legacy_needs_migration":len(legacy) if verdict != "UNINITIALISED" else 0,"new_style_failures":len(failures) + len(doc_failures),"verdict":verdict,"legacy_files":sorted(legacy) if verdict != "UNINITIALISED" else [],"workflows_dir":str(WF_DIR.resolve())}
    try:
        with open(STATUS_FILE + ".doc", "w", encoding="utf-8") as f:
            f.write(json.dumps(status, separators=(",",":")) + "\n")
    except OSError:
        pass

if JSON_MODE:
    print(json.dumps({
        "dir": str(WF_DIR),
        "playbooks": results,
        "verdict": verdict,
        "legacy": legacy,
        "needs_migration": len(legacy),
        "failures": failures,
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
        for msg in failures:
            print("  [FAIL] %s" % msg)
        print("RESULT: FAIL - registry or playbook read failed.")
    elif doc_failures:
        print(f"RESULT: FAIL — {len(doc_failures)} registered playbook(s) have NO recorded human-facing doc. "
              "Create it in the client's account (Notion -> Google Docs -> text) and record the URL/path "
              "in the registry's 'Doc (Notion/Docs/text)' column.")
    elif verdict == "UNINITIALISED":
        print("RESULT: UNINITIALISED - 0 playbooks examined; nothing was verified on this box; this is NOT a PASS.")
    elif legacy:
        print("RESULT: NEEDS-MIGRATION - %d legacy playbook(s) need migration; nothing else failed. They are not PASS." % len(legacy))
    else:
        print(f"RESULT: PASS — all {len(results)} playbook(s) have a recorded human-facing doc.")

DOC_RC = 1 if verdict == "FAIL" else (2 if verdict == "UNINITIALISED" else 0)
sys.exit(DOC_RC)
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
  export WF_DIR ENGINE JSON_MODE PYTHON_BIN PYTHON_VERSION STATUS_FILE
  "$PYTHON_BIN" - <<'PYEOF2'
import json
import os
import re
import sys
from pathlib import Path

ENGINE = Path(os.environ["ENGINE"])
WF_DIR = os.environ.get("WF_DIR", "")
JSON_MODE = os.environ.get("JSON_MODE", "0") == "1"
STATUS_FILE = os.environ.get("STATUS_FILE", "")
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
        try:
            candidates = sorted(wf.iterdir())
        except OSError as exc:
            defects.append("%s: unreadable (%s)" % (wf, exc.strerror or str(exc)))
            candidates = []
        for f in candidates:
            try:
                if not f.is_file() or not f.name.endswith(".md"):
                    continue
                if f.name == "registry.md" or any(f.name.endswith(s) for s in RESERVED):
                    continue
                text = f.read_text(encoding="utf-8", errors="ignore")
            except OSError as exc:
                defects.append("%s: unreadable (%s)" % (f, exc.strerror or str(exc)))
                continue

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

resolved_wf = str(Path(WF_DIR).resolve()) if WF_DIR else ""
migration_command = "bash scripts/33-migrate-legacy-playbooks.sh %s --write" % (resolved_wf or "<ABSOLUTE_WORKFLOWS_DIR>")
if defects:
    verdict = "FAIL"
elif checked == 0 and not legacy:
    verdict = "UNINITIALISED"
elif legacy:
    verdict = "NEEDS-MIGRATION"
else:
    verdict = "PASS"
if STATUS_FILE:
    status = {"gate":"qc-playbook-doc","legacy_needs_migration":len(legacy) if verdict != "UNINITIALISED" else 0,"new_style_failures":len(defects),"verdict":verdict,"legacy_files":sorted(legacy) if verdict != "UNINITIALISED" else [],"workflows_dir":resolved_wf}
    try:
        with open(STATUS_FILE + ".meta", "w", encoding="utf-8") as f:
            f.write(json.dumps(status, separators=(",",":")) + "\n")
    except OSError:
        pass

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
    elif verdict == "UNINITIALISED":
        print("RESULT: UNINITIALISED - 0 playbooks examined; not a PASS.")
    elif legacy:
        print("RESULT: NEEDS-MIGRATION - %d legacy playbook(s) need migration; nothing else failed. They are not PASS." % len(legacy))
    else:
        print("RESULT: PASS - every present metadata line parses against the grammar.")

META_RC = 1 if verdict == "FAIL" else (2 if verdict == "UNINITIALISED" else 0)
sys.exit(META_RC)
PYEOF2
  META_RC=$?
fi

if [ -n "$STATUS_FILE" ]; then
  STATUS_FILE="$STATUS_FILE" WF_DIR="$WF_DIR" DOC_RC="$DOC_RC" META_RC="$META_RC" python3 - <<'PYMERGE'
import json, os
from pathlib import Path
base = os.environ["STATUS_FILE"]
valid = {"PASS", "NEEDS-MIGRATION", "FAIL", "UNINITIALISED"}
stages = []
for suffix in (".doc", ".meta"):
    try:
        with open(base + suffix, encoding="utf-8") as f:
            item = json.load(f)
        if not isinstance(item, dict) or item.get("verdict") not in valid:
            raise ValueError("invalid verdict")
        if type(item.get("legacy_needs_migration")) is not int or type(item.get("new_style_failures")) is not int:
            raise ValueError("invalid counts")
        if not isinstance(item.get("legacy_files"), list):
            raise ValueError("invalid legacy_files")
        stages.append(item)
    except Exception:
        stages.append({"legacy_needs_migration":0,"new_style_failures":1,"verdict":"FAIL","legacy_files":[]})
legacy = max((s["legacy_needs_migration"] for s in stages), default=0)
fails = sum(s["new_style_failures"] for s in stages)
if fails:
    verdict = "FAIL"
elif any(s["verdict"] == "UNINITIALISED" for s in stages):
    verdict = "UNINITIALISED"
elif legacy:
    verdict = "NEEDS-MIGRATION"
else:
    verdict = "PASS"
files = sorted({Path(n).name for s in stages for n in s["legacy_files"] if isinstance(n, str)})
status = {"gate":"qc-playbook-doc","legacy_needs_migration":legacy if verdict != "UNINITIALISED" else 0,"new_style_failures":fails,"verdict":verdict,"legacy_files":files if verdict != "UNINITIALISED" else [],"workflows_dir":str(Path(os.environ["WF_DIR"]).resolve()) if os.environ.get("WF_DIR") else ""}
try:
    with open(base, "w", encoding="utf-8") as f:
        f.write(json.dumps(status, separators=(",",":")) + "\n")
except OSError:
    pass
for suffix in (".doc", ".meta"):
    try:
        os.unlink(base + suffix)
    except OSError:
        pass
PYMERGE
fi

if [ "$DOC_RC" -eq 0 ] && [ "$META_RC" -eq 0 ]; then
  exit 0
fi
if [ "$DOC_RC" -eq 2 ]; then
  exit 2
fi
exit 1
