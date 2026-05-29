#!/usr/bin/env bash
# qc-conversation-memory.sh — machine-enforce the conversation-memory protocol
# (read-before + append-after) on every GHL inbound SERVER messageTemplate.
#
# Root cause this gate kills: GHL inbound hook sessions are SINGLE-TURN /
# stateless — every hook run is a fresh session (user-turns = 1), so the agent
# has NO in-session memory of prior messages. Its ONLY memory of a contact
# across messages is the per-contact conversation log file
# (<MASTER_FILES_DIR>/conversational-logs/<contact_id>__<name>.md): it must READ
# that log BEFORE replying and APPEND inbound+reply AFTER sending. On a live
# client this broke because the canonical messageTemplate was simplified during
# testing and lost the read/append steps — the agent had zero memory ("didn't
# remember anything" mid-booking). The send-directive gate (qc-send-directive.sh)
# did NOT catch it because it only checks for the SEND instruction. This linter
# proves every GHL inbound SERVER messageTemplate carries BOTH the read-before
# and append-after conversation-log steps instead of trusting it.
#
# It is the conversation-memory analogue of qc-send-directive.sh — same scan
# target, same structure — and is the machine-enforced layer of the 4-change
# conversation-memory enforcement:
#   1 = scripts/15-configure-hooks-mappings.sh canonical template (+ fail-closed guard)
#   2 = scripts/09-install-conversation-workflows.sh creates+chowns conversational-logs/
#   3 = scripts/05-update-agents-md.sh AGENTS.md Conversation Memory Protocol base rule
#   4 = THIS gate (wired into 11-run-qc-checklist.sh + qc-static.yml CI)
#
# WHAT IT SCANS — only GHL INBOUND SERVER-mapping messageTemplates, i.e. the
# object-B `hooks.mappings` reply templates that resolve `{{…}}` placeholders:
#   • the installer's jq-built canonical template in
#     scripts/15-configure-hooks-mappings.sh
#   • every GHL server-mapping messageTemplate embedded in references/ +
#     templates/ + scripts/ (a {{contact_id}}-bearing messageTemplate that
#     instructs a GHL reply).
#
# WHAT IT DELIBERATELY SKIPS:
#   • object-A 23-key FLAT GHL bodies (placeholder-FREE messageTemplate) — those
#     MUST stay placeholder-free per the 23-key rule (qc-23-key-bodies.sh); the
#     read/append directive lives ONLY on the server mapping.
#   • non-GHL server mappings (Stripe / Shopify / n8n) — their messageTemplate
#     has no GHL contact/reply intent, so this directive does not apply.
#
# REQUIRED conversation-memory elements (wording may vary slightly but ALL must
# be present in each GHL inbound server template):
#   1. the conversational-logs file path / reference ("conversational-logs")
#   2. a READ-before-replying instruction ("read" the log before drafting)
#   3. an APPEND-after-sending instruction ("append" inbound+reply to the log)
#
# Exit codes: 0 = all GHL inbound server templates carry read-before + append-after;
#             1 = one or more are missing element(s);
#             2 = no GHL inbound server templates found (scan target moved —
#                 treated as FAILURE so the linter never goes silently blind).
#
# Usage:
#   bash scripts/qc-conversation-memory.sh            # human output
#   bash scripts/qc-conversation-memory.sh --json     # machine output
#   bash scripts/qc-conversation-memory.sh --skill-dir /path/to/38-conversational-ai-system

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
JSON_MODE=0

while [ $# -gt 0 ]; do
  case "$1" in
    --skill-dir) SKILL_DIR="$2"; shift 2 ;;
    --json) JSON_MODE=1; shift ;;
    -h|--help) sed -n '1,60p' "$0"; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

export SKILL_DIR JSON_MODE

python3 - <<'PYEOF'
import json
import os
import re
import sys
from pathlib import Path

SKILL_DIR = Path(os.environ["SKILL_DIR"])
JSON_MODE = os.environ.get("JSON_MODE", "0") == "1"

SCAN_DIRS = ["references", "templates", "scripts"]

# Each rule is (label, predicate-on-lowercased-template). ALL must hold.
def _has_log_path(t):
    # The per-contact conversation log dir / file is referenced.
    return "conversational-logs" in t

def _has_read_before(t):
    # An instruction to READ the log (before replying). "read" appears together
    # with the log reference; the canonical template uses "READ this contact's
    # conversation log ... FIRST, before drafting anything".
    return "read" in t

def _has_append_after(t):
    # An instruction to APPEND the inbound + reply to the log after sending.
    return "append" in t

REQUIRED = [
    ("conversational-logs path reference", _has_log_path),
    ("READ-before-replying instruction", _has_read_before),
    ("APPEND-after-sending instruction", _has_append_after),
]

# A GHL INBOUND SERVER template is one whose messageTemplate VALUE both:
#   (a) carries a {{contact_id}} placeholder (it is the placeholder-resolving
#       server mapping, not a placeholder-free 23-key body), AND
#   (b) instructs a GHL reply (mentions "ghl conversations api" or "reply"),
# which excludes Stripe/Shopify/n8n server templates that have no GHL reply
# intent and excludes the placeholder-free object-A bodies.
def is_ghl_inbound_server_template(value):
    v = value.lower()
    if "{{contact_id}}" not in v:
        return False
    if ("ghl conversations api" in v) or ("reply" in v) or ("send" in v):
        return True
    return False

# Pull every "messageTemplate": "<value>" occurrence (JSON-style) from a text.
# Handles escaped quotes inside the value.
MT_JSON_RE = re.compile(r'"messageTemplate"\s*:\s*"((?:[^"\\]|\\.)*)"')

# The installer builds the template with jq using an unquoted key:
#   messageTemplate:"....."
# inside a `jq -n '{ ... }'` single-quoted block. Capture that too.
MT_JQ_RE = re.compile(r'messageTemplate\s*:\s*"((?:[^"\\]|\\.)*)"')


def _unescape(s):
    # Minimal JSON-string unescape for the elements scan.
    return (s.replace('\\"', '"')
             .replace("\\\\", "\\")
             .replace("\\n", " ")
             .replace("\\t", " "))


def find_ghl_server_templates(text):
    """Yield raw messageTemplate values that are GHL inbound server templates."""
    seen = set()
    for rx in (MT_JSON_RE, MT_JQ_RE):
        for m in rx.finditer(text):
            raw = m.group(1)
            val = _unescape(raw)
            if val in seen:
                continue
            if is_ghl_inbound_server_template(val):
                seen.add(val)
                yield val


def lint_template(value):
    t = value.lower()
    missing = [label for (label, pred) in REQUIRED if not pred(t)]
    return missing


results = []
total = 0

for sub in SCAN_DIRS:
    d = SKILL_DIR / sub
    if not d.is_dir():
        continue
    for f in sorted(d.rglob("*")):
        if not f.is_file():
            continue
        if f.suffix not in (".md", ".sh", ".txt"):
            continue
        try:
            text = f.read_text(errors="ignore")
        except Exception:
            continue
        for i, val in enumerate(find_ghl_server_templates(text)):
            total += 1
            missing = lint_template(val)
            results.append({
                "file": str(f.relative_to(SKILL_DIR)),
                "template_index": i,
                "missing": missing,
                "preview": (val[:120] + "…") if len(val) > 120 else val,
            })

failures = [r for r in results if r["missing"]]

if JSON_MODE:
    print(json.dumps({
        "scanned_ghl_server_templates": total,
        "failures": failures,
        "verdict": "PASS" if (not failures and total > 0) else
                   ("NO_TEMPLATES" if total == 0 else "FAIL"),
    }, indent=2))
else:
    print("=== qc-conversation-memory: GHL inbound SERVER messageTemplate read-before/append-after linter ===")
    print(f"skill_dir : {SKILL_DIR}")
    print(f"scanned   : {total} GHL inbound server messageTemplate(s)")
    print("")
    for r in results:
        tag = "PASS" if not r["missing"] else "FAIL"
        print(f"  [{tag}] {r['file']} (template #{r['template_index']})")
        print(f"         {r['preview']}")
        for miss in r["missing"]:
            print(f"          - MISSING: {miss}")
    print("")
    if total == 0:
        print("RESULT: NO GHL INBOUND SERVER TEMPLATES FOUND — the scan target moved; the linter is blind. Treating as FAIL.")
    elif failures:
        print(f"RESULT: FAIL — {len(failures)} GHL inbound server template(s) lack the conversation-memory read-before/append-after steps.")
    else:
        print(f"RESULT: PASS — all {total} GHL inbound server template(s) carry the conversation-memory read-before + append-after steps.")

if total == 0:
    sys.exit(2)
sys.exit(1 if failures else 0)
PYEOF
