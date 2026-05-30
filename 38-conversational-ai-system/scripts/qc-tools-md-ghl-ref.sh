#!/usr/bin/env bash
# qc-tools-md-ghl-ref.sh — machine-enforce the GHL API quick-reference block that
# Skill 38 injects into the CLIENT TOOLS.md (scripts/24-update-tools-md.sh).
#
# Root cause this gate kills: the whole point of the block is to give the agent
# the EXACT request shapes in its core context so it replies fast. If a regression
# drops an operation, a scope, or quietly bloats the block (defeating "concise"),
# or — worst — leaks a personal/client identifier into a UNIVERSAL skill artifact,
# the feature silently breaks. This linter proves the canonical source the
# installer injects (references/ghl-api-quick-reference.md) is complete, concise,
# and free of personal/client data.
#
# WHAT IT SCANS: references/ghl-api-quick-reference.md — the single source of
# truth that 24-update-tools-md.sh appends verbatim into the client TOOLS.md.
# (Checking the source file makes this a static, CI-runnable gate; the client
# TOOLS.md is identical because the installer copies this block byte-for-byte.)
#
# FAILS on any of:
#   1. MISSING OPERATION — each messaging channel type (SMS / Email / FB / IG /
#      Live_Chat), calendars list/get/create, free-slots, appointment
#      book/reschedule/cancel, and send invoice.
#   2. MISSING SCOPE — each required PIT scope in the summary line.
#   3. SIZE BUDGET — block exceeds the concise budget (avoid core-file bloat).
#   4. PERSONAL/CLIENT DATA — any client/personal identifier (real name, email,
#      phone, a concrete locationId/contactId, a real *.trycloudflare/hstgr host).
#
# Exit codes: 0 = pass; 1 = one or more violations.
#
# Usage:
#   bash scripts/qc-tools-md-ghl-ref.sh            # human output
#   bash scripts/qc-tools-md-ghl-ref.sh --json     # machine output
#   bash scripts/qc-tools-md-ghl-ref.sh --skill-dir /path/to/38-conversational-ai-system

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
JSON_MODE=0

while [ $# -gt 0 ]; do
  case "$1" in
    --skill-dir) SKILL_DIR="$2"; shift 2 ;;
    --json) JSON_MODE=1; shift ;;
    -h|--help) sed -n '1,40p' "$0"; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; exit 1 ;;
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

REF = SKILL_DIR / "references" / "ghl-api-quick-reference.md"

failures = []

if not REF.is_file():
    failures.append(f"reference file missing: {REF.relative_to(SKILL_DIR)}")
    if JSON_MODE:
        print(json.dumps({"verdict": "FAIL", "failures": failures}, indent=2))
    else:
        print("=== qc-tools-md-ghl-ref ===")
        for f in failures:
            print(f"  [FAIL] {f}")
        print("RESULT: FAIL")
    sys.exit(1)

text = REF.read_text(errors="ignore")
low = text.lower()

# ---------------------------------------------------------------------------
# 1) REQUIRED OPERATIONS — each must appear as a recognizable shape.
#    Keyed by a human label → a predicate over the (lowercased) block text.
# ---------------------------------------------------------------------------
def has_all(*subs):
    return lambda t: all(s in t for s in subs)

# Anchor messaging-channel detection to the channel TABLE ROWS, not "anywhere in
# the block" — otherwise the short codes that appear in the prose (e.g. the
# INVALID-types note "use the short codes (`FB`, `IG`)") would mask a dropped row.
# A channel row looks like:  | <Channel> | `<TYPE>` | contactId, locationId, ... |
TABLE_ROWS = [ln for ln in low.splitlines() if ln.lstrip().startswith("|")]
def in_channel_row(type_code):
    needle = f"`{type_code}`"
    for ln in TABLE_ROWS:
        if needle in ln and "contactid" in ln and "locationid" in ln:
            return True
    return False

REQUIRED_OPS = {
    # Messaging — one endpoint, one type per channel (row-anchored).
    "messaging endpoint POST /conversations/messages": lambda t: "/conversations/messages" in t,
    "messaging type SMS":        lambda t: in_channel_row("sms"),
    "messaging type Email":      lambda t: in_channel_row("email"),
    "messaging type FB":         lambda t: in_channel_row("fb"),
    "messaging type IG":         lambda t: in_channel_row("ig"),
    "messaging type Live_Chat":  lambda t: in_channel_row("live_chat"),
    # Calendars.
    "calendars list (GET /calendars/?locationId)":        has_all("get /calendars/?locationid"),
    "calendars get (GET /calendars/<calendarId>)":        has_all("get /calendars/<calendarid>"),
    "calendars create (POST /calendars/)":                has_all("post /calendars/`"),
    "free slots (GET .../free-slots)":                    has_all("/free-slots"),
    # Appointments.
    "appointment book (POST /calendars/events/appointments)":      has_all("post /calendars/events/appointments"),
    "appointment reschedule (PUT .../appointments/<eventId>)":     has_all("put /calendars/events/appointments/<eventid>"),
    "appointment cancel (DELETE /calendars/events/<eventId>)":     has_all("delete /calendars/events/<eventid>"),
    # Invoices.
    "send invoice (POST /invoices/<invoiceId>/send)":     has_all("post /invoices/<invoiceid>/send"),
}

for label, pred in REQUIRED_OPS.items():
    if not pred(low):
        failures.append(f"MISSING OPERATION: {label}")

# ---------------------------------------------------------------------------
# 1b) SEND ENUM uses the SHORT CODES (FB / IG) — never the long-forms as a send
#     `type`, and the SEND BODY does NOT carry conversationId (it threads by
#     contactId; conversationId is the READ key only). Verified facts: the GHL
#     SendMessageBodyDto enum is SMS/RCS/Email/WhatsApp/IG/FB/Custom/Live_Chat/
#     TIKTOK — there is no `Facebook`/`Instagram` send type — and the send body
#     accepts contactId, NOT conversationId.
# ---------------------------------------------------------------------------
# (a) FB / IG short codes must appear as send types in the channel table rows.
if not in_channel_row("fb"):
    failures.append("SEND ENUM: Facebook send type must be the short code `FB` in a channel row (not the long-form `Facebook`)")
if not in_channel_row("ig"):
    failures.append("SEND ENUM: Instagram send type must be the short code `IG` in a channel row (not the long-form `Instagram`)")
# (b) A long-form used AS a send `type` value (backtick-wrapped) is the bug.
for badtype in ("`facebook`", "`instagram`", "`webchat`"):
    # Allow it ONLY when explicitly called out as INVALID/long-form. Flag a bare
    # appearance as a send-type code anywhere it is presented as valid.
    for ln in low.splitlines():
        if badtype in ln and ("invalid" not in ln) and ("long-form" not in ln) and ("reject" not in ln) and ("not a send" not in ln):
            failures.append(f"SEND ENUM: long-form send type {badtype} presented as valid (use the short code) — line: {ln.strip()[:80]}")
            break
# (c) conversationId must NEVER be shown as a SEND body field. The send body is
#     {type, contactId, locationId, message}. conversationId is read-only.
#     Catch it inside any conversations/messages POST body / send-body shape.
SEND_BODY_RE = re.compile(r'/conversations/messages[^\n]*\n(?:[^\n]*\n){0,12}', re.IGNORECASE)
send_ctx = "".join(SEND_BODY_RE.findall(text))
# Also scan the curl POST body lines directly for a conversationId send field.
for m in re.finditer(r'"conversationid"\s*:', low):
    failures.append("SEND BODY: conversationId appears as a send-body field — the send threads BY contactId; conversationId is the READ key only")
    break
# READ endpoints must be present (find-thread by contact + read history) so the
# READ path for conversationId is documented (scope conversations.readonly).
if "/conversations/search" not in low:
    failures.append("MISSING OPERATION: conversations READ — GET /conversations/search (find the thread by contact)")
if "/conversations/<conversationid>/messages" not in low and "/conversations/{conversationid}/messages" not in low:
    failures.append("MISSING OPERATION: conversations READ — GET /conversations/<conversationId>/messages (read history)")
if "conversations.readonly" not in low:
    failures.append("MISSING SCOPE: conversations.readonly (required for the conversation READ ops)")

# ---------------------------------------------------------------------------
# 2) REQUIRED SCOPES — the summary line + per-op scopes.
# ---------------------------------------------------------------------------
REQUIRED_SCOPES = [
    "conversations/message.write",
    "calendars.readonly",
    "calendars.write",
    "calendars/events.readonly",
    "calendars/events.write",
    "invoices.write",
]
for sc in REQUIRED_SCOPES:
    if sc.lower() not in low:
        failures.append(f"MISSING SCOPE: {sc}")

# ---------------------------------------------------------------------------
# 3) SIZE BUDGET — concise, no core-file bloat. The block is a cheat sheet.
#    Budget chosen with headroom over the shipped block; tripping it means the
#    block grew toward "the whole API" (the exact thing we said NOT to do).
# ---------------------------------------------------------------------------
LINE_BUDGET = 120
# 6500 (was 6000 at v1.4.20): v1.4.21 added the MESSAGING (READ) ops
# (GET /conversations/search + GET /conversations/<id>/messages, scope
# conversations.readonly), the channel-mirror map, and the SendMessageBodyDto
# enum note. ~500 chars of headroom keeps the block a concise cheat sheet (the
# 120-line guard is the real anti-bloat gate) without tripping on the legitimate
# new READ content.
CHAR_BUDGET = 6500
nlines = text.count("\n") + 1
nchars = len(text)
if nlines > LINE_BUDGET:
    failures.append(f"SIZE BUDGET: {nlines} lines > {LINE_BUDGET} (block bloated — keep it a concise cheat sheet)")
if nchars > CHAR_BUDGET:
    failures.append(f"SIZE BUDGET: {nchars} chars > {CHAR_BUDGET} (block bloated — keep it a concise cheat sheet)")

# ---------------------------------------------------------------------------
# 4) NO PERSONAL / CLIENT DATA — this is a UNIVERSAL skill artifact.
#    Allowed placeholders: <contactId>, <calendarId>, <eventId>, <invoiceId>,
#    <LOCATION_ID>, <ISO8601 start>, <reply text>, $GHL_PRIVATE_INTEGRATION_TOKEN,
#    $PUBLIC_HOSTNAME (only as a comment, emitted by the installer at runtime).
# ---------------------------------------------------------------------------
# Real email address (but NOT placeholder field NAMES like emailFrom/emailTo).
for m in re.finditer(r'[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}', text):
    failures.append(f"PERSONAL DATA: looks like a real email address: {m.group(0)}")
# Phone-number-shaped runs (10+ consecutive digits, or +<country> formats).
for m in re.finditer(r'(?<!\d)(?:\+?\d[\d\-\.\s]{8,}\d)(?!\d)', text):
    digits = re.sub(r'\D', '', m.group(0))
    if len(digits) >= 10:
        failures.append(f"PERSONAL DATA: looks like a real phone number: {m.group(0).strip()}")
# Concrete GHL ids would be long alnum tokens assigned to contactId/locationId
# WITHOUT the <...> placeholder wrapper. Catch e.g. contactId":"abc123XYZ".
for field in ("contactId", "locationId", "calendarId", "eventId", "invoiceId"):
    for m in re.finditer(rf'{field}"?\s*[:=]\s*"?([A-Za-z0-9]{{12,}})"?', text):
        val = m.group(1)
        failures.append(f"PERSONAL DATA: concrete {field} value (use a <{field}> placeholder): {val}")
# Real tunnel/host strings (a concrete client hook host baked in would be data).
for m in re.finditer(r'[A-Za-z0-9\-]+\.(?:trycloudflare\.com|hstgr\.cloud|zerohumanworkforce\.com)', text):
    failures.append(f"PERSONAL DATA: concrete client host baked in: {m.group(0)}")

# ---------------------------------------------------------------------------
# Verdict.
# ---------------------------------------------------------------------------
if JSON_MODE:
    print(json.dumps({
        "file": str(REF.relative_to(SKILL_DIR)),
        "lines": nlines,
        "chars": nchars,
        "failures": failures,
        "verdict": "PASS" if not failures else "FAIL",
    }, indent=2))
else:
    print("=== qc-tools-md-ghl-ref: GHL TOOLS.md quick-reference linter ===")
    print(f"file  : {REF.relative_to(SKILL_DIR)}")
    print(f"size  : {nlines} lines / {nchars} chars (budget {LINE_BUDGET} / {CHAR_BUDGET})")
    print("")
    if not failures:
        print("RESULT: PASS — block carries every operation + scope, is concise, and contains no personal/client data.")
    else:
        for f in failures:
            print(f"  [FAIL] {f}")
        print("")
        print(f"RESULT: FAIL — {len(failures)} violation(s).")

sys.exit(1 if failures else 0)
PYEOF
