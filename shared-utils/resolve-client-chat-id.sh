#!/usr/bin/env bash
# resolve-client-chat-id.sh — resolve a CLIENT's numeric Telegram chat_id from the
# fleet's OWN registry (fleet-roster.json), so a Telegram send is NEVER attempted
# against a phone number (which the Bot API cannot deliver to).
#
# WHY A RUNTIME SCRIPT (and not memory-wiring): the fleet registry holds REAL
# client chat ids — un-committable PII. It lives ONLY on the operator box at
# $HOME/clawd/fleet-prover/fleet-roster.json (gitignored; NEVER in this repo). This
# resolver READS it at runtime and EMBEDS NOTHING. Wiring the registry into
# searchable memory would drag those real ids into the repo/index; a script keeps
# the values on the box and ships only the lookup logic + a synthetic-fixture test.
#
# Companion to shared-utils/resolve-owner-chat.sh (owner-chat resolver) and
# shared-utils/operator-chat-id.sh (operator-escalation resolver): same house
# style — a single sourceable helper + an inline python3 heredoc that prints ONLY
# the resolved numeric id on stdout, nothing else.
#
# ROSTER LOCATION (first existing wins):
#   1. $OPENCLAW_FLEET_ROSTER                     (env override)
#   2. $HOME/clawd/fleet-prover/fleet-roster.json (operator box default)
#   3. /data/clawd/fleet-prover/fleet-roster.json (containerized default)
# If none exists: empty stdout, non-zero exit (3), stderr "fleet roster not found".
#
# MATCHING: the client-name argument is matched (case-insensitive) against each
# boxes[].client field, and secondarily against the box-slug key. An EXACT
# case-insensitive match wins; otherwise a UNIQUE substring match is used. A match
# only counts as resolvable if its chatId is a VALID numeric Telegram chat id
# (^-?[0-9]{6,20}$) and is NOT one of the sentinel strings unconfirmed / tbd / ""
# (empty).
#
# OUTPUT CONTRACT (mirrors resolve-owner-chat.sh — stdout carries ONLY the id):
#   - EXACTLY ONE confident, valid match  -> print the numeric chat_id to STDOUT, exit 0.
#   - Otherwise                            -> print NOTHING to stdout; exit non-zero.
#     Human diagnostics go to STDERR only. Exit codes:
#       1  not found, or matched but chatId is unconfirmed / tbd / missing
#       2  ambiguous — the name matched more than one distinct client
#       3  roster file not found / unreadable
#       4  usage — no client-name argument
#
# Usage (direct):
#   id="$(shared-utils/resolve-client-chat-id.sh "Wibble Widgets")" \
#     && echo "deliver to chat_id $id"   # e.g. 1234567890
#
# Usage (sourced):
#   source "$(dirname "$0")/resolve-client-chat-id.sh"
#   id="$(resolve_client_chat_id "Wibble Widgets")" || echo "unresolved (rc=$?)"
#
# DOCTRINE: NEVER pass a phone number (e.g. an E.164 like +15551234567, or a CRM
# contact's phone) as a Telegram send target. Resolve the chat_id here FIRST; if
# this returns empty / non-zero, mark the task BLOCKED and escalate to the operator
# — do NOT fall back to a phone number. See
# universal-sops/telegram-target-resolution.md and
# 23-ai-workforce-blueprint/master-orchestrator-dept/SOP-01-Blocked-vs-Return.md.

set -u

# Echo the first existing roster path, or empty string (+ non-zero) if none.
_rcci_roster_path() {
  if [[ -n "${OPENCLAW_FLEET_ROSTER:-}" && -f "${OPENCLAW_FLEET_ROSTER}" ]]; then
    printf '%s' "${OPENCLAW_FLEET_ROSTER}"; return 0
  fi
  local candidate
  for candidate in \
    "${HOME:-/root}/clawd/fleet-prover/fleet-roster.json" \
    "/data/clawd/fleet-prover/fleet-roster.json"; do
    [[ -f "$candidate" ]] && { printf '%s' "$candidate"; return 0; }
  done
  printf '%s' ""
  return 1
}

resolve_client_chat_id() {
  local query="${1:-}"
  if [[ -z "${query// }" ]]; then
    echo "resolve-client-chat-id: usage: resolve_client_chat_id \"<client name>\"" >&2
    return 4
  fi

  local roster
  roster="$(_rcci_roster_path)" || true
  if [[ -z "$roster" ]]; then
    echo "resolve-client-chat-id: fleet roster not found (looked in \$OPENCLAW_FLEET_ROSTER, then \$HOME/clawd/fleet-prover/fleet-roster.json, then /data/clawd/fleet-prover/fleet-roster.json)" >&2
    return 3
  fi

  # Python performs the match. It prints ONLY the resolved numeric id to stdout on
  # a single confident valid match (exit 0); otherwise nothing on stdout, a
  # diagnostic on stderr, and a distinct non-zero exit the shell propagates.
  ROSTER="$roster" QUERY="$query" python3 - <<'PYEOF'
import json, os, re, sys

roster = os.environ["ROSTER"]
query = os.environ["QUERY"].strip()

VALID_ID = re.compile(r"^-?[0-9]{6,20}$")
SENTINELS = {"", "unconfirmed", "tbd"}


def valid_id(v):
    """Return the id string if it is a valid numeric Telegram chat id, else ""."""
    if v is None:
        return ""
    s = str(v).strip()
    if s.lower() in SENTINELS:
        return ""
    return s if VALID_ID.match(s) else ""


try:
    with open(roster) as fh:
        data = json.load(fh)
except Exception as e:  # unreadable / malformed roster -> treat as missing (3)
    sys.stderr.write("resolve-client-chat-id: roster unreadable: %s\n" % e)
    raise SystemExit(3)

boxes = data.get("boxes", {})
if not isinstance(boxes, dict):
    boxes = {}

q = query.lower()
exact = []   # (slug, valid_or_empty_id) — exact case-insensitive client/slug match
substr = []  # (slug, valid_or_empty_id) — substring fallback

for slug, entry in boxes.items():
    if not isinstance(entry, dict):
        continue
    cid = valid_id(entry.get("chatId"))
    keys = [str(entry.get("client", "") or "").lower().strip(),
            str(slug).lower().strip()]
    keys = [k for k in keys if k]
    if q in keys:
        exact.append((slug, cid))
    elif any(q in k for k in keys):
        substr.append((slug, cid))

# Exact matches win outright; substring is only consulted when there is no exact
# match at all (so an exact hit disambiguates a name that is also a substring of
# other entries).
pool = exact if exact else substr
matched_slugs = {slug for slug, _cid in pool}

if not pool:
    sys.stderr.write("resolve-client-chat-id: no roster entry matches %r\n" % query)
    raise SystemExit(1)

if len(matched_slugs) > 1:
    sys.stderr.write(
        "resolve-client-chat-id: ambiguous — %d distinct clients match %r; "
        "refine the name\n" % (len(matched_slugs), query))
    raise SystemExit(2)

# Exactly one distinct client matched (pool holds a single slug's entry).
_slug, cid = pool[0]
if not cid:
    sys.stderr.write(
        "resolve-client-chat-id: matched %r but its chatId is unconfirmed / "
        "missing — resolve or escalate; do NOT send to a phone number\n" % query)
    raise SystemExit(1)

# Confident, valid, single match: print ONLY the numeric id.
print(cid)
raise SystemExit(0)
PYEOF
}

# When executed directly (not sourced), resolve the CLI argument and propagate the
# function's exit code. Prints only the resolved id (or nothing) to stdout.
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  resolve_client_chat_id "${1:-}"
  exit $?
fi
