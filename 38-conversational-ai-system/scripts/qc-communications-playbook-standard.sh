#!/usr/bin/env bash
# qc-communications-playbook-standard.sh — machine-enforce the COMMUNICATION PLAYBOOK
# STANDARD (references/communications-playbook-standard.md).
#
# WHY: the communication-playbook output drifted run-to-run. This gate asserts the
# standard doc carries the hard leading "EVERY COMMUNICATION PLAYBOOK MUST INCLUDE ALL
# OF THE FOLLOWING" mandatory checklist (Section 0) AND every required item (a)-(q),
# so a regression that deletes or guts the checklist fails the build.
#
# WHAT IT CHECKS:
#   Doc mode:
#     1. references/communications-playbook-standard.md exists.
#     2. It has the leading mandatory-checklist headline (Section 0).
#     3. It names all 8 channels in that section.
#     4. Each mandatory item (a)-(i) is present with its load-bearing concept.
#     5. Items (k)-(q) remain present in the standard.
#     6. The doc points at the enforcing gate (this script).
#     7. SKILL.md / INSTRUCTIONS.md carry a pointer to the standard.
#   Playbook mode:
#     Validates eligible markdown playbooks and Layer-2 craft requirements.
#
# Exit codes: 0 = clean; 1 = validation failures; 2 = bad usage or directory.
#
# Usage:
#   bash scripts/qc-communications-playbook-standard.sh
#   bash scripts/qc-communications-playbook-standard.sh --skill-dir DIR
#   bash scripts/qc-communications-playbook-standard.sh --doc PATH
#   bash scripts/qc-communications-playbook-standard.sh --playbooks DIR
#
# --doc supports negative-test fixtures. --playbooks validates every eligible
# *.md file directly inside DIR, excluding registry and generated companion files.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
DOC=""
PLAYBOOKS=""

while [ $# -gt 0 ]; do
  case "$1" in
    --skill-dir)
      if [ $# -lt 2 ]; then
        echo "Missing value for --skill-dir" >&2
        exit 2
      fi
      SKILL_DIR="$2"
      shift 2
      ;;
    --doc)
      if [ $# -lt 2 ]; then
        echo "Missing value for --doc" >&2
        exit 2
      fi
      DOC="$2"
      shift 2
      ;;
    --playbooks)
      if [ $# -lt 2 ]; then
        echo "Missing value for --playbooks" >&2
        exit 2
      fi
      PLAYBOOKS="$2"
      shift 2
      ;;
    -h|--help)
      sed -n '1,42p' "$0"
      exit 0
      ;;
    *)
      echo "Unknown arg: $1" >&2
      exit 2
      ;;
  esac
done

if [ -n "$PLAYBOOKS" ]; then
  if [ -n "$DOC" ]; then
    echo "Cannot combine --playbooks with --doc" >&2
    exit 2
  fi

  if [ ! -d "$PLAYBOOKS" ]; then
    echo "[FAIL] no eligible playbooks found in $PLAYBOOKS"
    exit 2
  fi

  echo "=== qc-communications-playbook-standard: playbook gate ==="
  echo "playbooks : $PLAYBOOKS"
  echo ""

  FILES_SCANNED=0
  FILES_PASSED=0
  FILES_FAILED=0
  CHECKS_RUN=0
  CHECKS_FAILED=0
  declare -a FILE_RESULTS=()

  playbook_pass() {
    echo "  [PASS] $1 :: $2"
    CHECKS_RUN=$((CHECKS_RUN + 1))
  }

  playbook_fail() {
    echo "  [FAIL] $1 :: $2"
    CHECKS_RUN=$((CHECKS_RUN + 1))
    CHECKS_FAILED=$((CHECKS_FAILED + 1))
    FILE_FAIL=1
  }

  playbook_skip() {
    echo "  [SKIP] $1 :: $2 (not a Layer-2 playbook)"
  }

  # ponytail: scan direct-child markdown only; recurse when nested playbooks become supported.
  for f in "$PLAYBOOKS"/*.md; do
    [ -f "$f" ] || continue

    base="${f##*/}"

    case "$base" in
      registry.md|*--build-with-ai-prompt.md|*--workflow-ai-prompt.md|*--verification-checklist.md|*--ghl-side.md|*--build-contract.json)
        continue
        ;;
    esac

    FILES_SCANNED=$((FILES_SCANNED + 1))
    FILE_FAIL=0

    # Read each eligible file into one variable for content checks.
    doc="$(cat "$f")"
    header="$(sed -n '1,40p' "$f")"

    echo "File: $base"

    # (a) Persona or channel header.
    if printf '%s\n' "$header" | grep -qiE '^(persona|channel):'; then
      playbook_pass "$base" "(a) persona/channel header"
    else
      playbook_fail "$base" "(a) persona/channel header"
    fi

    # (b) Opening section or opening reference.
    if printf '%s\n' "$doc" | grep -qiE '^## Opening|opening'; then
      playbook_pass "$base" "(b) opening section"
    else
      playbook_fail "$base" "(b) opening section"
    fi

    # (c) Goal.
    if printf '%s\n' "$doc" | grep -qiE '\*\*Goal:\*\*|^## Goal'; then
      playbook_pass "$base" "(c) goal"
    else
      playbook_fail "$base" "(c) goal"
    fi

    # (d) Mandatory Conversations API send contract.
    if printf '%s\n' "$doc" | grep -qiF 'Conversations API' &&
       printf '%s\n' "$doc" | grep -qiE 'drafting|composing' &&
       printf '%s\n' "$doc" | grep -qF 'messageId'; then
      playbook_pass "$base" "(d) Conversations API send contract"
    else
      playbook_fail "$base" "(d) Conversations API send contract"
    fi

    # (e) Conversation-memory read/append contract.
    if printf '%s\n' "$doc" | grep -qiF 'conversational-logs' &&
       printf '%s\n' "$doc" | grep -qiF 'read' &&
       printf '%s\n' "$doc" | grep -qiF 'append'; then
      playbook_pass "$base" "(e) conversation-memory read/append"
    else
      playbook_fail "$base" "(e) conversation-memory read/append"
    fi

    # (f) Honesty and a non-empty escalation section.
    if printf '%s\n' "$doc" | grep -qiE 'honesty|NEVER fabricat'; then
      HONESTY_OK=1
    else
      HONESTY_OK=0
    fi

    ESCALATION_BODY_OK=0
    if printf '%s\n' "$doc" | awk '
      BEGIN { IGNORECASE=1; found=0; in_section=0 }
      /^## On escalation[[:space:]]*$/ {
        found=1
        in_section=1
        next
      }
      in_section && /^## / { exit }
      in_section && NF {
        found=1
        body=1
        exit
      }
      END {
        if (found && body) exit 0
        exit 1
      }
    '; then
      ESCALATION_BODY_OK=1
    fi

    if [ "$HONESTY_OK" -eq 1 ] && [ "$ESCALATION_BODY_OK" -eq 1 ]; then
      playbook_pass "$base" "(f) honesty and escalation body"
    else
      playbook_fail "$base" "(f) honesty and escalation body"
    fi

    # (g) Quiet hours and compliance opt-out keywords.
    if printf '%s\n' "$doc" | grep -qiF 'quiet hours' &&
       printf '%s\n' "$doc" | grep -qiE 'STOP|UNSUBSCRIBE'; then
      playbook_pass "$base" "(g) quiet hours and opt-out compliance"
    else
      playbook_fail "$base" "(g) quiet hours and opt-out compliance"
    fi

    # (h) ZHC tag prefix.
    if printf '%s\n' "$doc" | grep -qF 'ZHC-'; then
      playbook_pass "$base" "(h) ZHC- tag prefix"
    else
      playbook_fail "$base" "(h) ZHC- tag prefix"
    fi

    # (i) Per-channel formatting guidance.
    if printf '%s\n' "$doc" | grep -qiE '160|2-4 short paragraphs|1-3 conversational sentences|professional concise|short real-time turns'; then
      playbook_pass "$base" "(i) per-channel formatting guidance"
    else
      playbook_fail "$base" "(i) per-channel formatting guidance"
    fi

    # Layer-2 means at least one canonical phase heading.
    if printf '%s\n' "$doc" | grep -qE '^### Phase'; then
      LAYER2=1
    else
      LAYER2=0
    fi

    # (l1) At least five objection table rows, excluding header and separator.
    if [ "$LAYER2" -eq 1 ]; then
      OBJECTION_ROWS="$(printf '%s\n' "$doc" | awk '
        /^\|/ {
          if ($0 ~ /^\|[[:space:]]*:?-[-| :]*-?[[:space:]]*\|?[[:space:]]*$/) next
          if (!header_seen) {
            header_seen=1
            next
          }
          rows++
        }
        END { print rows+0 }
      ')"
      if [ "$OBJECTION_ROWS" -ge 5 ]; then
        playbook_pass "$base" "(l1) at least five objection rows"
      else
        playbook_fail "$base" "(l1) at least five objection rows"
      fi
    else
      playbook_skip "$base" "(l1) at least five objection rows"
    fi

    # (l2) Every Phase block must contain an example: line.
    if [ "$LAYER2" -eq 1 ]; then
      if printf '%s\n' "$doc" | awk '
        /^### Phase/ {
          if (in_phase && !has_example) bad=1
          in_phase=1
          has_example=0
          next
        }
        in_phase && /^[[:space:]]*example[[:space:]]*:/ {
          has_example=1
        }
        END {
          if (in_phase && !has_example) bad=1
          exit bad
        }
      '; then
        playbook_pass "$base" "(l2) example line in every Phase block"
      else
        playbook_fail "$base" "(l2) example line in every Phase block"
      fi
    else
      playbook_skip "$base" "(l2) example line in every Phase block"
    fi

    # (p1) Conversational KPI section with at least one numeric target.
    if [ "$LAYER2" -eq 1 ]; then
      if printf '%s\n' "$doc" | awk '
        BEGIN { IGNORECASE=1 }
        /^## Conversational KPIs[[:space:]]*$/ {
          in_kpi=1
          found=1
          next
        }
        in_kpi && /^## / { in_kpi=0 }
        in_kpi && /[0-9]/ { numeric=1 }
        END { exit !(found && numeric) }
      '; then
        playbook_pass "$base" "(p1) conversational KPI targets"
      else
        playbook_fail "$base" "(p1) conversational KPI targets"
      fi
    else
      playbook_skip "$base" "(p1) conversational KPI targets"
    fi

    # (p2) Golden transcript section.
    if [ "$LAYER2" -eq 1 ]; then
      if printf '%s\n' "$doc" | grep -qiE '^## Golden transcript[[:space:]]*$'; then
        playbook_pass "$base" "(p2) golden transcript section"
      else
        playbook_fail "$base" "(p2) golden transcript section"
      fi
    else
      playbook_skip "$base" "(p2) golden transcript section"
    fi

    if [ "$FILE_FAIL" -eq 0 ]; then
      FILES_PASSED=$((FILES_PASSED + 1))
      FILE_RESULTS[${#FILE_RESULTS[@]}]="PASS|$base"
    else
      FILES_FAILED=$((FILES_FAILED + 1))
      FILE_RESULTS[${#FILE_RESULTS[@]}]="FAIL|$base"
    fi

    echo ""
  done

  if [ "$FILES_SCANNED" -eq 0 ]; then
    echo "[FAIL] no eligible playbooks found in $PLAYBOOKS"
    exit 2
  fi

  echo "files scanned: $FILES_SCANNED"
  echo "files passed: $FILES_PASSED"
  echo "files failed: $FILES_FAILED"
  echo "checks run: $CHECKS_RUN"
  echo "checks failed: $CHECKS_FAILED"
  echo ""
  for result in "${FILE_RESULTS[@]}"; do
    status="${result%%|*}"
    name="${result#*|}"
    printf '%-6s %s\n' "$status" "$name"
  done

  if [ "$FILES_FAILED" -eq 0 ] && [ "$FILES_SCANNED" -gt 0 ]; then
    echo "RESULT: PASS — all eligible playbooks passed."
    exit 0
  else
    echo "RESULT: FAIL — one or more playbooks failed validation."
    exit 1
  fi
fi

[ -n "$DOC" ] || DOC="$SKILL_DIR/references/communications-playbook-standard.md"

FAIL=0
pass() { echo "  [PASS] $1"; }
fail() { echo "  [FAIL] $1"; FAIL=1; }

echo "=== qc-communications-playbook-standard: COMMUNICATION PLAYBOOK STANDARD gate ==="
echo "doc : $DOC"
echo ""

if [ ! -f "$DOC" ]; then
  echo "  [FAIL] standard doc MISSING: $DOC"
  echo ""
  echo "RESULT: FAIL"
  exit 1
fi

# 1. The hard leading mandatory-checklist headline (Section 0).
if grep -qiE 'EVERY COMMUNICATION PLAYBOOK MUST INCLUDE ALL OF THE FOLLOWING' "$DOC"; then
  pass "Section 0 mandatory-checklist headline present"
else
  fail "missing the leading 'EVERY COMMUNICATION PLAYBOOK MUST INCLUDE ALL OF THE FOLLOWING' headline"
fi

# 2. NON-NEGOTIABLE framing.
grep -qiE 'NON-NEGOTIABLE' "$DOC" && pass "checklist framed NON-NEGOTIABLE" || fail "checklist must be framed NON-NEGOTIABLE"

# 3. All 8 channels named.
CHANNELS=("SMS" "Email" "FB Messenger" "FB comments" "IG DM" "LinkedIn" "Live Chat" "All-in-One")
for c in "${CHANNELS[@]}"; do
  if grep -qF "$c" "$DOC"; then pass "channel named: $c"; else fail "channel NOT named: $c"; fi
done

# 4. Each mandatory item (a)-(i) — match on the load-bearing concept, not just the letter.
declare -a ITEM_KEYS=(
  "channel + persona|persona / voice identity|persona/voice"
  "opening behavior|how to greet|greet"
  "conversation GOAL|GOAL / desired outcome|desired outcome"
  "MANDATORY SEND|GHL Conversations API|drafting/composing is NOT sending|Drafting"
  "Conversation-memory|read-before|append-after|conversational-logs"
  "Escalation|HONESTY FLOOR|honesty floor|NEEDS_HUMAN"
  "Quiet-hours|quiet hours|compliance|STOP"
  "ZHC- tag-prefix|ZHC- prefix for|programmatic tags? carr|programmatic.{0,12}ZHC-"
  "Per-channel formatting|formatting constraints|160 chars|24-hour"
)
declare -a ITEM_NAMES=(
  "(a) channel + persona/voice identity"
  "(b) opening behavior + how to greet"
  "(c) conversation goal / desired outcome"
  "(d) mandatory SEND rule (Conversations API, mirror, drafting != sending)"
  "(e) conversation-memory read-before/append-after"
  "(f) escalation/handoff + honesty floor"
  "(g) quiet-hours + compliance-keyword respect"
  "(h) ZHC- tag-prefix for programmatic tags"
  "(i) per-channel formatting constraints"
)
i=0
for keyset in "${ITEM_KEYS[@]}"; do
  if grep -qiE "$keyset" "$DOC"; then
    pass "mandatory item present: ${ITEM_NAMES[$i]}"
  else
    fail "mandatory item MISSING: ${ITEM_NAMES[$i]}"
  fi
  i=$((i+1))
done

# 4b. Items (k)-(q) must remain in the standard doc.
if grep -qiE '\(k\).*declares' "$DOC" &&
   grep -qi 'tools-used' "$DOC" &&
   grep -qi 'exits-used' "$DOC" &&
   grep -qi 'fields-used' "$DOC" &&
   grep -qi 'tags-used' "$DOC" &&
   grep -qi 'calendars' "$DOC" &&
   grep -qi 'pipeline' "$DOC" &&
   grep -qi 'stage-map' "$DOC"; then
  pass "(k) machine-readable declares block"
else
  fail "(k) machine-readable declares block"
fi

if grep -qiE '\(l\).*objection library' "$DOC"; then
  pass "(l) objection library"
else
  fail "(l) objection library"
fi

if grep -qiE '\(m\).*turn discipline' "$DOC"; then
  pass "(m) turn discipline"
else
  fail "(m) turn discipline"
fi

if grep -qiE '\(n\).*ambiguity and multi-intent' "$DOC"; then
  pass "(n) ambiguity and multi-intent"
else
  fail "(n) ambiguity and multi-intent"
fi

if grep -qiE '\(o\).*stall recovery' "$DOC"; then
  pass "(o) stall recovery"
else
  fail "(o) stall recovery"
fi

if grep -qiE '\(p\).*golden transcript' "$DOC"; then
  pass "(p) golden transcript"
else
  fail "(p) golden transcript"
fi

if grep -qiE '\(q\).*conversational kpi' "$DOC"; then
  pass "(q) conversational KPI"
else
  fail "(q) conversational KPI"
fi

# 5. Self-consistency: the doc names its enforcing gate.
grep -qF 'qc-communications-playbook-standard.sh' "$DOC" \
  && pass "doc references its enforcing gate (qc-communications-playbook-standard.sh)" \
  || fail "doc must reference its enforcing gate (qc-communications-playbook-standard.sh)"

# 6. SKILL.md / INSTRUCTIONS.md pointer (skip when running against a fixture --doc).
if [ -z "${DOC##*communications-playbook-standard.md}" ]; then
  PTR=0
  for f in "$SKILL_DIR/SKILL.md" "$SKILL_DIR/INSTRUCTIONS.md"; do
    [ -f "$f" ] && grep -qF 'communications-playbook-standard.md' "$f" && PTR=1
  done
  [ "$PTR" -eq 1 ] && pass "SKILL.md/INSTRUCTIONS.md point to the standard" \
                    || fail "SKILL.md or INSTRUCTIONS.md must point to references/communications-playbook-standard.md"
fi

echo ""
if [ "$FAIL" -eq 0 ]; then
  echo "RESULT: PASS — the communication playbook standard carries the mandatory checklist + every required item (a)-(i)."
  exit 0
else
  echo "RESULT: FAIL — a communication-playbook-standard mandatory item is missing (see above)."
  exit 1
fi
