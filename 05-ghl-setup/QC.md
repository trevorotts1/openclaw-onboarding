# QC Checklist — Skill 05: GHL / Convert and Flow Setup
Version: v1.5.0 | Last updated: 2026-03-16

Run this checklist after installing Skill 05. Every item must pass before declaring the skill installed correctly. Work top to bottom. Do not skip sections.

---

## SECTION 1 — File Structure Checks

Verify all required skill files are present in the correct location.

```bash
ls ~/Downloads/openclaw-master-files/OpenClaw\ Onboarding/05-ghl-setup/
```

- [ ] `SKILL.md` exists
- [ ] `INSTALL.md` exists
- [ ] `INSTRUCTIONS.md` exists
- [ ] `EXAMPLES.md` exists
- [ ] `CORE_UPDATES.md` exists
- [ ] `CHANGELOG.md` exists
- [ ] `ghl-setup-full.md` exists
- [ ] `QC.md` exists (this file)

**Pass criteria:** All 8 files present. Missing any file = FAIL.

---

## SECTION 2 — Credential Storage Checks

### 2a. Primary credential store — ~/clawd/secrets/.env

```bash
grep -E "GHL_API_KEY|GHL_LOCATION_ID" ~/clawd/secrets/.env
```

- [ ] `GHL_API_KEY` is present and non-empty
- [ ] `GHL_LOCATION_ID` is present and non-empty
- [ ] Neither value is a placeholder string (e.g. `your-api-key-here`, `xxx`, `REPLACE_ME`)

### 2b. Secondary credential store — ~/.openclaw/openclaw.json (if section exists)

```bash
cat ~/.openclaw/openclaw.json | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('env',{}).get('vars',{}))" 2>/dev/null
```

- [ ] If `env.vars` section exists: `GHL_API_KEY` and `GHL_LOCATION_ID` are present
- [ ] Values in openclaw.json (if present) match values in secrets/.env

**Pass criteria:** secrets/.env has both real credentials. openclaw.json sync is optional but must be consistent if present. Placeholders = FAIL.

---

## SECTION 3 — Core File Update Checks

### 3a. AGENTS.md

```bash
grep -i "GHL\|Convert and Flow\|Version.*2021-07-28" ~/clawd/AGENTS.md
```

- [ ] A GHL/Convert and Flow section exists
- [ ] The `Version: 2021-07-28` header requirement is mentioned
- [ ] A file path reference to `ghl-setup-full.md` is present
- [ ] Full documentation was NOT pasted in (only a summary + path reference)

### 3b. TOOLS.md

```bash
grep -i "GHL\|leadconnectorhq\|Version.*2021-07-28" ~/clawd/TOOLS.md
```

- [ ] A GHL/Convert and Flow API section exists
- [ ] Base URL `https://services.leadconnectorhq.com` is referenced
- [ ] `Version: 2021-07-28` header rule is mentioned
- [ ] Key endpoints (`/contacts/search`, `/conversations/messages`, `/opportunities/`) are listed
- [ ] A file path reference to `ghl-setup-full.md` is present
- [ ] Full documentation was NOT pasted in (only a summary + path reference)

### 3c. MEMORY.md

```bash
grep -i "GHL\|Convert and Flow\|secrets/.env" ~/clawd/MEMORY.md
```

- [ ] A GHL setup entry exists with an install date
- [ ] Credential storage location (`~/clawd/secrets/.env`) is noted
- [ ] `Version: 2021-07-28` mandatory header is noted
- [ ] A file path reference to `ghl-setup-full.md` is present

### 3d. Files that must NOT be updated

- [ ] `IDENTITY.md` — confirm no GHL content was added
- [ ] `HEARTBEAT.md` — confirm no GHL content was added
- [ ] `USER.md` — confirm no GHL content was added
- [ ] `SOUL.md` — confirm no GHL content was added

**Pass criteria:** All three core files updated with lean summaries + path refs. No full doc dumps. No edits to the four protected files.

---

## SECTION 4 — Knowledge Verification Questions

Ask the agent each question. Evaluate its answer against the expected response.

**Q1:** What is the base URL for all GHL API calls?
- Expected: `https://services.leadconnectorhq.com`
- [ ] PASS / [ ] FAIL

**Q2:** What two headers are required on every GHL API request?
- Expected: `Authorization: Bearer {GHL_API_KEY}` AND `Version: 2021-07-28`
- [ ] PASS / [ ] FAIL

**Q3:** What is the correct name for the GHL authentication token?
- Expected: Private Integration Token (PIT) — NOT "API key"
- [ ] PASS / [ ] FAIL

**Q4:** What is "Convert and Flow"?
- Expected: The white-label client-facing name for GoHighLevel. Same API, same endpoints, same backend.
- [ ] PASS / [ ] FAIL

**Q5:** Where does the agent check for GHL credentials?
- Expected: TWO locations — `~/clawd/secrets/.env` (primary) AND `~/.openclaw/openclaw.json` under `env.vars` (secondary)
- [ ] PASS / [ ] FAIL

**Q6:** What happens if you omit the Version header on a GHL request?
- Expected: 400 Bad Request error
- [ ] PASS / [ ] FAIL

**Q7:** What is the GHL rate limit for most endpoints?
- Expected: 100 requests per minute
- [ ] PASS / [ ] FAIL

**Q8:** Should the agent use the native GHL node in n8n?
- Expected: No — always use HTTP Request nodes instead
- [ ] PASS / [ ] FAIL

**Q9:** What are the three priority scopes to test first after GHL setup?
- Expected: Contacts, Media Library, Conversations (SMS + Email)
- [ ] PASS / [ ] FAIL

**Q10:** Which credential store is the authoritative source of truth — secrets/.env or openclaw.json?
- Expected: `~/clawd/secrets/.env` is primary. `openclaw.json` is secondary/optional mirror only.
- [ ] PASS / [ ] FAIL

**Pass criteria:** 9 of 10 correct. Any wrong answer about the Version header, base URL, or credential location = automatic FAIL regardless of score.

---

## SECTION 5 — Live Behavior Tests

Run all four tests sequentially. Each must pass before moving to the next.

### Test 1 — Credentials loaded into environment

```bash
echo "API Key: $(echo $GHL_API_KEY | head -c 10)..." && echo "Location ID: $GHL_LOCATION_ID"
```

- [ ] First 10 characters of API key are displayed (not blank, not placeholder)
- [ ] Full Location ID is displayed (not blank, not placeholder)

### Test 2 — API connection and authentication

```bash
curl -s -X GET "https://services.leadconnectorhq.com/locations/$GHL_LOCATION_ID" \
  -H "Authorization: Bearer $GHL_API_KEY" \
  -H "Version: 2021-07-28"
```

- [ ] Response is valid JSON
- [ ] Response contains location name and business details
- [ ] No `401 Unauthorized` error
- [ ] No `400 Bad Request` error

### Test 3 — Contact search endpoint

```bash
curl -s -X GET "https://services.leadconnectorhq.com/contacts/?locationId=$GHL_LOCATION_ID&limit=1" \
  -H "Authorization: Bearer $GHL_API_KEY" \
  -H "Version: 2021-07-28"
```

- [ ] Response is valid JSON
- [ ] Response contains a `contacts` array (may be empty — that is acceptable)
- [ ] No error response

### Test 4 — Media library access

```bash
curl -s -X GET "https://services.leadconnectorhq.com/medias/?locationId=$GHL_LOCATION_ID&limit=1" \
  -H "Authorization: Bearer $GHL_API_KEY" \
  -H "Version: 2021-07-28"
```

- [ ] Response is valid JSON
- [ ] Response contains a media files structure (may be empty — that is acceptable)
- [ ] No `403 Forbidden` error (would indicate media scope not enabled)

**Pass criteria:** All 4 tests return valid JSON with no error codes. Any test failure = FAIL for this section.

---

## SECTION 6 — Anti-Pattern Checks

Verify the agent is NOT doing any of the following. These are the most common failure modes.

- [ ] Agent does NOT refer to the GHL credential as an "API key" — must say "Private Integration Token" or "PIT"
- [ ] Agent does NOT omit the `Version: 2021-07-28` header from any API call
- [ ] Agent does NOT write full GHL documentation into AGENTS.md, TOOLS.md, or MEMORY.md (TYP violation)
- [ ] Agent does NOT claim setup is complete before all 4 live tests pass
- [ ] Agent does NOT attempt to restart the OpenClaw gateway autonomously
- [ ] Agent does NOT use placeholder values (`your-api-key-here`, `xxx`, `REPLACE_ME`) in credential files
- [ ] Agent does NOT store credentials only in openclaw.json while skipping secrets/.env
- [ ] Agent does NOT recommend using the native GHL node in n8n
- [ ] Agent does NOT prompt the user for credentials before first checking both env file locations
- [ ] Agent does NOT update IDENTITY.md, HEARTBEAT.md, USER.md, or SOUL.md

**Pass criteria:** Zero anti-patterns present. Any single anti-pattern = FAIL.

---

## SECTION 7 — Overall Pass Criteria

| Section | Requirement |
|---|---|
| 1 — File Structure | All 8 files present |
| 2 — Credentials | Both credentials real and non-empty in secrets/.env |
| 3 — Core File Updates | All 3 files updated (lean); 4 protected files untouched |
| 4 — Knowledge | 9/10 correct; Version header + base URL + credential location must be correct |
| 5 — Live Tests | All 4 tests return valid JSON, no errors |
| 6 — Anti-Patterns | Zero violations |

**OVERALL PASS:** All 6 sections pass.
**OVERALL FAIL:** Any single section fails.

---

## Failure Response Protocol

If any section fails:

1. Note which section failed and the specific item
2. Do NOT mark the skill as installed
3. Return to the relevant step in `INSTALL.md` and re-execute
4. Re-run this QC checklist from the top after fixing
5. Only report success to the user once all sections pass
