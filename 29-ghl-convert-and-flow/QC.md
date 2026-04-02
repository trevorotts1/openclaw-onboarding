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

Required environment values:
- `GHL_API_KEY` (Trevor naming for the Private Integration Token / PIT)
- `GHL_LOCATION_ID`

```bash
source ~/clawd/secrets/.env 2>/dev/null || true
for var in GHL_API_KEY GHL_LOCATION_ID; do
  [ -n "$(printenv "$var" 2>/dev/null)" ] \
    && echo "PASS: $var set" \
    || echo "FAIL: $var missing"
done

echo "Token length: ${#GHL_API_KEY}"
echo "Location ID: $GHL_LOCATION_ID"
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
source ~/clawd/secrets/.env 2>/dev/null || true

HTTP_CODE=$(curl -s -o /tmp/ghl_qc_location.json -w "%{http_code}" \
  -H "Authorization: Bearer $GHL_API_KEY" \
  -H "Version: 2021-04-15" \
  "https://services.leadconnectorhq.com/locations/$GHL_LOCATION_ID")

echo "HTTP: $HTTP_CODE"
python3 -m json.tool /tmp/ghl_qc_location.json | head -20
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
- uses `$GHL_API_KEY` and `$GHL_LOCATION_ID`
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
