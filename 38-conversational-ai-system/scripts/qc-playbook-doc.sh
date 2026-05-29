#!/usr/bin/env bash
# qc-playbook-doc.sh — machine-enforce the MANDATORY per-playbook human-facing
# doc deliverable (Notion -> Google Docs -> plain-text fallback).
#
# Root cause this gate kills: when a communications/conversation playbook is
# created (the base install creates the FIRST one — appointment booking), the
# agent is ALSO supposed to create a human-facing copy of that playbook in the
# CLIENT's own account, in this fallback order: (1) the client's Notion, (2) if
# no Notion -> Google Docs, (3) if neither -> a plain-text doc the client can
# access. On a live client this step was SKIPPED — the agent scaffolded the
# playbook files locally and reported the install "clean" but never created the
# client's Notion doc, leaving the customer with no human-facing reference of
# what was set up. The cause: the doc deliverable was PROSE in the standard
# (references/communications-playbook-standard.md §4 + the protocol §I.3 step 4),
# not an ENFORCED gate. "AUTOMATIC NEXT STEP" prose is NOT enforcement — it needs
# a recorded state field + a verify/resume gate + a QC check, exactly like the
# send-directive (qc-send-directive.sh) and conversation-memory
# (qc-conversation-memory.sh) gates. This linter is that QC check.
#
# It is the playbook-doc analogue of qc-trinity-registry.sh — same scan target
# (the client's conversation-workflows/registry.md) — and is LAYER 3 of the
# 4-change playbook-doc enforcement:
#   1 = INSTRUCTIONS.md / v6.0-source-playbook.md F.7 / protocol §I.3 binding
#       install step (state-gated: install not complete until the doc URL/path is
#       recorded in the registry's "Doc (Notion/Docs/text)" column + run manifest)
#   2 = scripts/09-install-conversation-workflows.sh installer action (tries
#       Notion -> Google Docs -> plain-text, records the resulting URL/path, emits
#       a clear operator line stating WHERE the doc was created)
#   3 = THIS gate (wired into 11-run-qc-checklist.sh + qc-static.yml CI)
#   4 = references/communications-playbook-standard.md §2/§4 +
#       references/GHL-INBOUND-AND-PLAYBOOKS.md §10 + protocol §F mark the doc a
#       MUST-APPEAR mandatory deliverable, machine-enforced by THIS script.
#
# WHAT IT SCANS — the client's conversation-workflows/registry.md. Every
# registered conversation playbook (a row under "## Active workflows", in EITHER
# the canonical TABLE form or the legacy BULLET form) MUST carry a recorded
# human-facing doc:
#   * TABLE form: the trailing "Doc (Notion/Docs/text)" column carries a real
#     reference — a Notion URL, a Google Docs URL, an http(s) URL, or a
#     .md/.txt file path the client can access.
#   * BULLET form: the line carries a "[doc: <url-or-path>]" / "doc: <url-or-path>"
#     tail with the same kinds of reference.
# A row whose doc cell is empty, missing, "n/a", "tbd", "todo", "pending", or
# only an unfilled <placeholder> is a FAILURE — that is exactly the skipped-doc
# regression this gate exists to catch.
#
# Exit codes: 0 = every registered playbook has a recorded human-facing doc;
#             1 = one or more registered playbooks have NO recorded doc;
#             2 = no playbooks registered yet (nothing to check) — treated as a
#                 distinct code so callers never confuse "blind/empty" with PASS;
#             3 = no conversation-workflows folder found (scan target moved).
#
# Usage:
#   bash scripts/qc-playbook-doc.sh                       # auto-locate via pointer file
#   bash scripts/qc-playbook-doc.sh --dir /path/to/conversation-workflows
#   bash scripts/qc-playbook-doc.sh --json

set -uo pipefail

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
    echo "qc-playbook-doc: no conversation-workflows folder at '${WF_DIR:-<unset>}'."
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

# A recorded human-facing doc reference is one of:
#   * a Notion URL (notion.so / notion.site)
#   * a Google Docs / Drive URL (docs.google.com / drive.google.com)
#   * any other http(s):// URL
#   * a plain-text/markdown file path the client can access (ends .md/.txt) that
#     is NOT just the Layer-2 playbook file or a reserved companion file the
#     trinity gate already tracks (<slug>.md, <slug>--build-with-ai-prompt.md,
#     <slug>--verification-checklist.md, <slug>--ghl-side.md). A doc PATH must
#     look like a human-facing copy: either it sits at an absolute/relative path
#     (has a "/" separator) or its filename signals a doc (contains "doc").
URL_RE = re.compile(r'https?://\S+', re.IGNORECASE)
TXT_PATH_RE = re.compile(r'[^\s|]+\.(?:md|txt)\b', re.IGNORECASE)

RESERVED_DOC_SUFFIXES = ("--build-with-ai-prompt.md", "--workflow-ai-prompt.md",
                         "--verification-checklist.md", "--ghl-side.md")

# Cells / tails that explicitly mean "no doc recorded yet" — fail.
EMPTY_TOKENS = {"", "n/a", "na", "none", "tbd", "todo", "to do", "pending",
                "-", "—", "...", "…"}


def _is_playbook_or_companion_file(path, slug):
    """True if `path` is just the Layer-2 playbook (<slug>.md) or one of the
    reserved companion files — those are NOT a human-facing doc."""
    base = path.rsplit("/", 1)[-1]
    if slug is not None and base == f"{slug}.md":
        return True
    for suf in RESERVED_DOC_SUFFIXES:
        if base.endswith(suf):
            return True
    return False


def doc_ref_in(text, slug=None):
    """Return a recorded human-facing doc reference string from `text`, or None.

    Accepts a Notion/Docs/any http(s) URL, or a real .md/.txt doc PATH (one that
    has a path separator or a "doc"-signalling filename, and is not the playbook
    itself / a reserved companion file). Rejects empty / placeholder /
    unfilled-<angle> values."""
    if text is None:
        return None
    t = text.strip()
    low = t.strip().strip("`").strip().lower()
    if low in EMPTY_TOKENS:
        return None
    # An unfilled angle-bracket placeholder like <notion-url> is NOT a real doc.
    stripped_angles = re.sub(r'<[^>]*>', '', t).strip()

    m = URL_RE.search(t)
    if m and m.group(0).strip("<>").strip():
        return m.group(0).rstrip(".,;)")

    m = TXT_PATH_RE.search(t)
    if m and stripped_angles:
        candidate = m.group(0)
        # Reject the playbook/companion files the trinity gate already tracks.
        if _is_playbook_or_companion_file(candidate, slug):
            return None
        base = candidate.rsplit("/", 1)[-1].lower()
        # A doc PATH must look like a human-facing copy: a real path (has "/")
        # or a "doc"-signalling filename. A bare "<slug>.md"-shaped sibling with
        # no separator and no "doc" hint is NOT accepted as the doc.
        if ("/" in candidate) or ("doc" in base):
            return candidate
    return None


# ---------------------------------------------------------------------------
# Parse registry.md "## Active workflows" rows in BOTH shapes.
#   (A) TABLE form: | ID | Name | Trigger | Layer 1? | OpenClaw playbook |
#                   GHL prompt | Verification checklist | Doc (Notion/Docs/text) |
#       The doc reference lives in ANY cell (we scan all cells) so the gate is
#       robust to column-order tweaks, but the canonical home is the trailing
#       "Doc (Notion/Docs/text)" column.
#   (B) BULLET form: "- <slug>: <desc>  [doc: <url-or-path>]"  (or "doc: ...").
# ---------------------------------------------------------------------------
BULLET_RE = re.compile(r"^[-*]\s+([a-z0-9][a-z0-9-]*)\s*:\s+\S")

registry_rows = {}  # slug -> {"doc": <ref or None>, "shape": "table"|"bullet"}

reg = WF_DIR / "registry.md"
if not reg.is_file():
    # No registry at all = no playbooks recorded = nothing to check (but never
    # silently pass blind: distinct exit code 2).
    if JSON_MODE:
        print(json.dumps({"dir": str(WF_DIR), "verdict": "NO_PLAYBOOKS",
                          "reason": "no registry.md"}, indent=2))
    else:
        print("=== qc-playbook-doc: per-playbook human-facing doc gate ===")
        print(f"dir: {WF_DIR}")
        print("")
        print("RESULT: NO PLAYBOOKS — registry.md absent; nothing to check (exit 2, not a blind PASS).")
    sys.exit(2)

in_active = False
for line in reg.read_text(errors="ignore").splitlines():
    stripped = line.strip()

    if stripped.startswith("#"):
        heading = stripped.lstrip("#").strip().lower()
        in_active = heading.startswith("active workflow")
        continue

    # (A) Table rows.
    if stripped.startswith("|"):
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if len(cells) < 4:
            continue
        rid = cells[0].strip("`").strip()
        if (not rid or rid.lower() in ("id", ":---", "---")
                or set(rid) <= set("-: ")):
            continue
        # Find a recorded doc reference in ANY cell of the row (the canonical
        # home is the trailing "Doc (Notion/Docs/text)" column).
        doc = None
        for c in cells:
            r = doc_ref_in(c, slug=rid)
            if r:
                doc = r
                break
        registry_rows[rid] = {"doc": doc, "shape": "table"}
        continue

    # (B) Bullet rows under "## Active workflows".
    if in_active:
        if "<" in stripped or "`" in stripped:
            continue
        m = BULLET_RE.match(stripped)
        if m:
            rid = m.group(1)
            doc = doc_ref_in(stripped, slug=rid)
            registry_rows.setdefault(rid, {"doc": doc, "shape": "bullet"})

# ---------------------------------------------------------------------------
# Discover on-disk playbook slugs too, so a playbook present on disk but with no
# registry row (and therefore no recorded doc) is still caught.
# ---------------------------------------------------------------------------
RESERVED_SUFFIXES = ("--build-with-ai-prompt.md", "--workflow-ai-prompt.md",
                     "--verification-checklist.md", "--ghl-side.md")


def slug_from_playbook(name):
    if name == "registry.md" or not name.endswith(".md"):
        return None
    for suf in RESERVED_SUFFIXES:
        if name.endswith(suf):
            return None
    return name[:-3]


disk_slugs = set()
for f in sorted(WF_DIR.iterdir()):
    if f.is_file():
        s = slug_from_playbook(f.name)
        if s:
            disk_slugs.add(s)

all_slugs = set(registry_rows.keys()) | disk_slugs

if not all_slugs:
    if JSON_MODE:
        print(json.dumps({"dir": str(WF_DIR), "verdict": "NO_PLAYBOOKS"}, indent=2))
    else:
        print("=== qc-playbook-doc: per-playbook human-facing doc gate ===")
        print(f"dir: {WF_DIR}")
        print("")
        print("RESULT: NO PLAYBOOKS — none registered or on disk; nothing to check (exit 2, not a blind PASS).")
    sys.exit(2)

results = []
for slug in sorted(all_slugs):
    row = registry_rows.get(slug)
    doc = row["doc"] if row else None
    problems = []
    if slug not in registry_rows:
        problems.append("playbook on disk but NOT registered in registry.md (so no doc can be recorded)")
    if not doc:
        problems.append("no recorded human-facing doc (Notion URL / Google Docs URL / .md|.txt path) — "
                        "the Notion->Google Docs->text deliverable was skipped or not recorded")
    results.append({"slug": slug, "doc": doc, "problems": problems})

failures = [r for r in results if r["problems"]]

if JSON_MODE:
    print(json.dumps({
        "dir": str(WF_DIR),
        "playbooks": results,
        "verdict": "PASS" if not failures else "FAIL",
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
    print("")
    if failures:
        print(f"RESULT: FAIL — {len(failures)} registered playbook(s) have NO recorded human-facing doc. "
              "Create it in the client's account (Notion -> Google Docs -> text) and record the URL/path "
              "in the registry's 'Doc (Notion/Docs/text)' column.")
    else:
        print(f"RESULT: PASS — all {len(results)} playbook(s) have a recorded human-facing doc.")

sys.exit(1 if failures else 0)
PYEOF
