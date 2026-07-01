# QC Checklist — Skill 29: GHL Convert and Flow API

Run this checklist after installation to confirm the skill is correctly installed and the agent can use it safely.

---

## 1. File Structure + Version Check

```bash
SKILL_DIR="$HOME/.openclaw/skills/29-ghl-convert-and-flow"
[ -d "$SKILL_DIR" ] || SKILL_DIR="$HOME/.openclaw/skills/ghl-convert-and-flow"

echo "Using skill dir: $SKILL_DIR"

for f in SKILL.md INSTALL.md INSTRUCTIONS.md EXAMPLES.md CORE_UPDATES.md \
         ghl-convert-and-flow-full.md skill-version.txt; do
  [ -f "$SKILL_DIR/$f" ] && echo "PASS: $f" || echo "FAIL: $f missing"
done

for r in auth.md calendars.md campaigns.md contacts.md conversations.md locations.md \
         modules.md opportunities.md payments.md phone-numbers.md users.md webhooks.md; do
  [ -f "$SKILL_DIR/references/$r" ] && echo "PASS: references/$r" || echo "FAIL: references/$r missing"
done
```

**Pass criteria:** All required files are present and `skill-version.txt` is readable.

---

## 2. Environment + Tool Checks

This skill is documentation-first. It mainly needs shell tooling plus real GHL credentials.

```bash
curl --version >/dev/null 2>&1 && echo "PASS: curl found" || echo "FAIL: curl missing"
python3 --version >/dev/null 2>&1 && echo "PASS: python3 found" || echo "FAIL: python3 missing"
which jq >/dev/null 2>&1 && echo "PASS: jq found" || echo "INFO: jq not installed (recommended)"
```

Required environment values (canonical names — the same ones the runnable examples use):
- `GOHIGHLEVEL_API_KEY` (the LOCATION-scoped Private Integration Token / PIT)
- `GOHIGHLEVEL_LOCATION_ID`

```bash
# Platform-aware env load. Hostinger Docker VPS already has these as container env
# vars (no .env file exists, so the [ -f ] guard simply skips). Mac stores them in
# ~/.openclaw/secrets/.env (canonical). Canonical names = GOHIGHLEVEL_API_KEY /
# GOHIGHLEVEL_LOCATION_ID — the SAME names the runnable examples use, so QC tests what
# the agent actually runs. Legacy aliases are mapped onto the canonical names.
[ -f ~/.openclaw/secrets/.env ] && { set -a; . ~/.openclaw/secrets/.env; set +a; }
: "${GOHIGHLEVEL_API_KEY:=${GHL_API_KEY:-${GHL_PRIVATE_INTEGRATION_TOKEN:-${PRIVATE_INTEGRATION_TOKEN:-${GHL_PRIVATE_TOKEN:-}}}}}"
: "${GOHIGHLEVEL_LOCATION_ID:=${GHL_LOCATION_ID:-}}"
[ -n "${GOHIGHLEVEL_API_KEY:-}" ]     && echo "PASS: GOHIGHLEVEL_API_KEY set"     || echo "FAIL: GOHIGHLEVEL_API_KEY missing"
[ -n "${GOHIGHLEVEL_LOCATION_ID:-}" ] && echo "PASS: GOHIGHLEVEL_LOCATION_ID set" || echo "FAIL: GOHIGHLEVEL_LOCATION_ID missing"

echo "Token length: ${#GOHIGHLEVEL_API_KEY}"
echo "Location ID: $GOHIGHLEVEL_LOCATION_ID"
```

**Pass criteria:** both env vars are present and non-placeholder.

---

## 3. Core Knowledge Verification

**Q1.** What is the base URL for GHL API v2?
> **Expected:** `https://services.leadconnectorhq.com`

**Q2.** What two headers are required on nearly every API call?
> **Expected:** `Authorization: Bearer <token>` and `Version: 2021-04-15`

**Q3.** What auth method should this skill use?
> **Expected:** Private Integration Token (PIT), not legacy API keys.

**Q4.** If a user asks to send an SMS or inspect conversation history, which reference file should be opened?
> **Expected:** `references/conversations.md`

**Q5.** If a user asks to book an appointment or inspect free slots, which reference file should be opened?
> **Expected:** `references/calendars.md`

**Q6.** If a call returns HTTP 403, what is the most likely problem?
> **Expected:** Missing required scope on the Private Integration Token.

**Q7.** What is the rule for the giant master reference file?
> **Expected:** Do not load it by default. Open only the relevant domain file. Use the full file only if a domain file is missing coverage.

**Q8.** What is Trevor-only from this skill?
> **Expected:** Billing/payment actions and phone-number removal/release are not autonomous agent actions.

**Q9.** What must the agent never hardcode into curl examples?
> **Expected:** Real tokens or real location IDs. Use env vars.

**Q10.** What should the agent do on a normal query like "look up a contact by email"?
> **Expected:** Read only `references/contacts.md`, then build the call with env vars.

**Pass criteria:** 10/10 answers correct.

---

## 4. Live Smoke Test

### 4.1 Location-read test

```bash
# Same canonical loader as section 2 (legacy aliases mapped; container env auto-detected).
[ -f ~/.openclaw/secrets/.env ] && { set -a; . ~/.openclaw/secrets/.env; set +a; }
: "${GOHIGHLEVEL_API_KEY:=${GHL_API_KEY:-${GHL_PRIVATE_INTEGRATION_TOKEN:-${PRIVATE_INTEGRATION_TOKEN:-${GHL_PRIVATE_TOKEN:-}}}}}"
: "${GOHIGHLEVEL_LOCATION_ID:=${GHL_LOCATION_ID:-}}"
if [ -z "${GOHIGHLEVEL_API_KEY:-}" ] || [ -z "${GOHIGHLEVEL_LOCATION_ID:-}" ]; then
  echo "BLOCKED: set GOHIGHLEVEL_API_KEY + GOHIGHLEVEL_LOCATION_ID in ~/.openclaw/secrets/.env first." >&2
else
  HTTP_CODE=$(curl -s -o /tmp/ghl_qc_location.json -w "%{http_code}" \
    -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" \
    -H "Version: 2021-04-15" \
    "https://services.leadconnectorhq.com/locations/$GOHIGHLEVEL_LOCATION_ID")
  echo "HTTP: $HTTP_CODE"
  python3 -m json.tool /tmp/ghl_qc_location.json | head -20
fi
```

**Expected:** HTTP `200` and JSON showing the location record.

### 4.2 Contacts-read behavior check

Prompt the agent:
> "Look up a contact in Convert and Flow by email address."

Verify the agent:
- identifies the domain as contacts
- reads `references/contacts.md` only
- uses `contacts.readonly`
- includes `Version: 2021-04-15`
- uses `$GOHIGHLEVEL_API_KEY` and `$GOHIGHLEVEL_LOCATION_ID`
- does not open all reference files up front

**Pass criteria:** All six checks pass.

---

## 5. Special Rule Checks

```bash
grep -n "phone number" "$SKILL_DIR/references/phone-numbers.md" | head
```

Verify the agent knows:
- destructive phone number actions are Trevor-only
- billing and payment actions require explicit approval
- the skill is read-on-demand, not bulk-loaded into context

---

## 6. Anti-Pattern Checks

Fail the skill if any of these occur:

- agent opens the full master reference for a routine domain query
- agent reads all reference files up front
- agent hardcodes a real token in output
- agent omits the `Version: 2021-04-15` header
- agent treats GHL PIT like a generic API key in client-facing language
- agent performs phone-number release/removal autonomously
- agent performs billing/payment actions autonomously
- agent invents parameters not documented in the selected reference file

**Pass criteria:** Zero anti-patterns triggered.

---

## 🔴 INSTALL-TIME QC RUBRIC (v9.3.0+ standard — added automatically)

After install, score yourself honestly against this rubric. **Pass gate: 8.5/10 minimum.** Below 8.5 = loop back and fix until passing (max 5 loops, then escalate to owner).

### Score breakdown (10 points)

| Section | Points | What it tests |
|---|---|---|
| Prerequisites + INSTALL-CONTRACT.md acknowledged | 1.0 | INSTALL-CONTRACT.md was read this session AND acknowledged in your work log for this specific skill. All prerequisite skills installed. |
| All skill .md files read before any execution | 1.0 | SKILL.md, INSTALL.md, CORE_UPDATES.md, QC.md (this file), any referenced `references/*.md`. Reading happened BEFORE any command was run. |
| INSTALL.md steps executed in order | 1.5 | No skipping, no reordering, no improvising. If a step was skipped, owner consent is documented. |
| Credentials at canonical paths with canonical names | 1.5 | `~/.openclaw/secrets/.env` (Mac) / `~/.openclaw/secrets/.env` (VPS), chmod 600. Canonical env-var names used (not deprecated ones). For GHL: `GOHIGHLEVEL_API_KEY` (a PIT, not an API key) + `GOHIGHLEVEL_LOCATION_ID`. |
| Functional checks pass | 1.5 | The skill's specific smoke tests (API reachability, software present, etc.) all return expected results. No 4xx/5xx unhandled. |
| CORE_UPDATES.md applied surgically | 1.0 | Only labeled sections added to labeled core files. No SOUL.md / IDENTITY.md / USER.md / HEARTBEAT.md touched unless this skill's CORE_UPDATES.md explicitly labels them. |
| Skill-specific QC items above all checked | 1.5 | Every checkbox in the skill-specific sections of THIS QC.md is ticked. |
| Security | 0.5 | No PIT or other secret leaked into chat / logs / commits / .md files. Secrets file chmod 600. |
| Owner-facing confirmation message sent | 0.5 | The final summary was sent in plain English with structure: "Skill NN active. Anything pending your attention: [list]." |

### Loop-until-passing rule

If score < 8.5:
1. Identify the lowest-scoring section
2. Apply the smallest fix possible
3. Re-run only the failed checks
4. Re-score
5. After 5 loops, STOP and escalate to owner via Telegram with: which sections failed, what you tried, what's blocking

### Bundled `qc-skill-NN.sh`

If a `qc-skill-NN.sh` script exists in this skill folder, run it. Exit 0 is required in addition to the rubric score. The script catches mechanical items the rubric assumes (file modes, env-var format, network reachability).

### Self-audit before declaring done

Recite in your work log:
1. INSTALL-CONTRACT.md acknowledged for this skill: ✓ / ✗
2. All .md files read before execution: ✓ / ✗
3. INSTALL.md step order followed verbatim: ✓ / ✗
4. QC rubric score: __/10 (≥ 8.5 to pass)
5. Bundled qc-*.sh exited 0: ✓ / ✗ / N/A
6. No shortcuts taken (no `--force`, etc.): ✓ / ✗
7. Owner confirmation message sent: ✓ / ✗

If any answer is ✗, this skill is NOT done. Loop back.
