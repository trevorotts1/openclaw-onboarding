#!/usr/bin/env bash
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GATE="$SCRIPT_DIR/qc-prompt-completeness.sh"
REAL="$(cd "$SCRIPT_DIR/.." && pwd)"
fail() { echo "[TEST FAIL] qc-prompt-completeness: $1"; exit 1; }

# ── template mode (default) ───────────────────────────────────────────────────
bash "$GATE" --skill-dir "$REAL" >/dev/null 2>&1 || fail "gate failed on intact template tree"
c="$(mktemp -d)"; cp -a "$REAL/." "$c/"
# Break it: strip the 'Webhook configuration' section from the template
grep -vi "Webhook configuration" "$c/templates/build-with-ai-prompt-template.md" > "$c/t.tmp" && mv "$c/t.tmp" "$c/templates/build-with-ai-prompt-template.md"
if bash "$GATE" --skill-dir "$c" >/dev/null 2>&1; then rm -rf "$c"; fail "template gate did NOT bite when a required section was removed"; fi
rm -rf "$c"

# ── --prompt mode (real generated output) ─────────────────────────────────────
tmp="$(mktemp -d)"
# A GOOD generated prompt: all 8 sections, substantive body, no bracket placeholders.
good="$tmp/good-prompt.md"
cat > "$good" <<'EOF'
Workflow Name: New Lead Welcome Sequence

Trigger Specification: Contact Created, filter tag Any of ZHC-new-lead, with a
re-fire guard so an existing contact does not re-enter the sequence twice.

Dependency List: Tag ZHC-new-lead created before build, Tag ZHC-welcome-sent
created before build, Custom Value welcome_email_subject set to a real subject
line, Custom Field ZHC_lead_source dataType text.

Action Sequence:
1. Add Tag ZHC-new-lead to the contact record.
2. Send Email using the Welcome template to the contact email address with the
   configured from name and the welcome subject custom value.
3. Wait one day before the follow-up branch evaluates.
4. If Else on whether the contact replied, branching to SMS on the NO branch.

Conditions: If Else Step 4 asks did the contact reply, YES branch exits the
workflow, NO branch sends the SMS follow-up on the contact phone number.

Webhook Configuration: None for this workflow.

Settings: Allow re-entry No, stop on response Yes, all hours time window, sender
details drawn from the location name and location email.

Post-Build Verification Checklist: run the twelve point checklist confirming the
workflow name, trigger, tags, custom fields, custom values, action order, if else
operators, wait durations, webhook, headers, settings, and a live test contact.
EOF
bash "$GATE" --prompt "$good" >/dev/null 2>&1 || { rm -rf "$tmp"; fail "--prompt mode failed on a complete real prompt"; }

# BAD prompt A: has all section titles but is a thin stub (below the word floor).
thin="$tmp/thin-prompt.md"
cat > "$thin" <<'EOF'
Workflow name. Trigger specification. Dependency list. Action sequence.
Conditions. Webhook configuration. Settings. Post-build verification checklist.
EOF
if bash "$GATE" --prompt "$thin" >/dev/null 2>&1; then rm -rf "$tmp"; fail "--prompt mode did NOT bite on a thin stub"; fi

# BAD prompt B: substantive length + all sections BUT leaves an unfilled [placeholder].
placeholder="$tmp/placeholder-prompt.md"
cp "$good" "$placeholder"
printf '\n[Clear, descriptive name for the workflow. Under 60 characters.]\n' >> "$placeholder"
if bash "$GATE" --prompt "$placeholder" >/dev/null 2>&1; then rm -rf "$tmp"; fail "--prompt mode did NOT bite on an unfilled [ ] placeholder"; fi

# BAD prompt C: missing a required section (drop Webhook configuration line).
missing="$tmp/missing-section.md"
grep -vi "Webhook Configuration" "$good" > "$missing"
if bash "$GATE" --prompt "$missing" >/dev/null 2>&1; then rm -rf "$tmp"; fail "--prompt mode did NOT bite on a missing section"; fi

# Missing file path -> exit 1 (not a false pass).
if bash "$GATE" --prompt "$tmp/does-not-exist.md" >/dev/null 2>&1; then rm -rf "$tmp"; fail "--prompt mode passed on a nonexistent file"; fi

rm -rf "$tmp"
echo "[TEST PASS] qc-prompt-completeness bites (template mode + --prompt real-output mode)"
exit 0
