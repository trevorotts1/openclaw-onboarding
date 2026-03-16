# QC Checklist — Skill 07: KIE Setup
**Run after installation to verify the skill installed correctly.**
**All items must pass before reporting installation complete.**

---

## SECTION 1: FILE STRUCTURE CHECKS

Verify these files exist before checking anything else.

```
[ ] 1.1  ~/clawd/secrets/.env exists
[ ] 1.2  ~/clawd/secrets/.env contains the line: KIE_API_KEY=<non-empty value>
[ ] 1.3  The KIE_API_KEY value is not a placeholder (not "paste-your-actual-api-key-here",
         not "YOUR_API_KEY", not empty)
[ ] 1.4  A KIE.ai reference .md file exists somewhere under ~/Downloads/ in an
         "OpenClaw" master files folder (any of the valid folder name variants)
         Example: ~/Downloads/openclaw-master-files/OpenClaw Onboarding/07-kie-setup/kie-setup-full.md
         OR a copy saved separately like ~/Downloads/OpenClaw Master Files/kie-ai-reference.md
[ ] 1.5  The reference file is NOT empty (it should be a very large file, 100K+ characters)
```

**How to verify 1.1–1.3:**
```bash
grep "KIE_API_KEY" ~/clawd/secrets/.env
```
Pass: line appears with a real key value. Fail: missing, empty, or placeholder text.

**How to verify 1.4–1.5:**
```bash
find ~/Downloads -iname "*.md" | xargs grep -l "nano-banana-pro" 2>/dev/null | head -5
```
Pass: at least one file returned. Fail: no results.

---

## SECTION 2: CORE FILE UPDATE CHECKS

Verify that AGENTS.md, TOOLS.md, and MEMORY.md were updated correctly and lean (no full documentation dumped in).

### 2.1 AGENTS.md

```
[ ] 2.1a  AGENTS.md contains a KIE.ai section
[ ] 2.1b  The section references "KIE_API_KEY" or "secrets/.env"
[ ] 2.1c  The section references the full reference file path (not the full content)
[ ] 2.1d  The section mentions "nano-banana-pro" as the primary image model
[ ] 2.1e  The section does NOT contain thousands of lines of raw API docs
          (the entry should be under ~10 lines, not a full API reference)
```

**Spot check command:**
```bash
grep -A 8 "KIE" ~/clawd/AGENTS.md | head -20
```
Pass: short summary with a file path reference. Fail: raw API docs pasted in.

### 2.2 TOOLS.md

```
[ ] 2.2a  TOOLS.md contains a KIE.ai API section
[ ] 2.2b  Section includes the base URL: https://api.kie.ai/api/v1/
[ ] 2.2c  Section includes the image endpoint: /api/v1/jobs/createTask
[ ] 2.2d  Section includes the VEO video endpoint: /api/v1/veo/generate
[ ] 2.2e  Section includes the credit check endpoint: /api/v1/chat/credit
[ ] 2.2f  Section references the full reference file path (not the content)
[ ] 2.2g  Section does NOT contain the full 176K-character API reference
```

**Spot check command:**
```bash
grep -A 8 "KIE" ~/clawd/TOOLS.md | head -20
```
Pass: concise entry, file path reference present. Fail: multi-hundred line dump.

### 2.3 MEMORY.md

```
[ ] 2.3a  MEMORY.md contains a KIE.ai entry
[ ] 2.3b  Entry shows the install date (not left as [DATE])
[ ] 2.3c  Entry references the location of the full reference file
[ ] 2.3d  Entry is brief (3–5 lines), not a full document dump
```

**Spot check command:**
```bash
grep -A 5 "KIE" ~/clawd/MEMORY.md | head -12
```

### 2.4 Files That Must NOT Have Been Changed

```
[ ] 2.4a  IDENTITY.md was NOT modified (run: git diff ~/clawd/IDENTITY.md — should be clean)
[ ] 2.4b  HEARTBEAT.md was NOT modified
[ ] 2.4c  USER.md was NOT modified
[ ] 2.4d  SOUL.md was NOT modified
```

---

## SECTION 3: KNOWLEDGE VERIFICATION QUESTIONS

Ask the agent each question. Check the answer against the expected response.

**Q1: What is the correct endpoint to generate an image using nano-banana-pro?**
Expected: `POST https://api.kie.ai/api/v1/jobs/createTask`
Fail if: agent says `/v1/images/generations` or any OpenAI-style endpoint.

```
[ ] 3.1  Correct endpoint stated
```

---

**Q2: What is the correct endpoint to check the status of a VEO video task?**
Expected: `GET https://api.kie.ai/api/v1/veo/task?taskId=XXX`
Fail if: agent says `/api/v1/jobs/recordInfo` for a VEO task.

```
[ ] 3.2  Correct VEO status endpoint stated (different from regular job status)
```

---

**Q3: When you submit a job and get a 200 response, is the media ready to download?**
Expected: NO. A 200 means the task was CREATED, not finished. You must poll.
Fail if: agent says yes or implies the result is immediately available.

```
[ ] 3.3  Correctly identifies async workflow — 200 = task created, not completed
```

---

**Q4: How long are generated file URLs valid for?**
Expected: Approximately 24 hours (some 14 days). Must be downloaded immediately.
Fail if: agent says "indefinitely" or does not mention expiry.

```
[ ] 3.4  Correctly states ~24-hour URL expiry
```

---

**Q5: What does a 401 error from KIE.ai mean? What about a 402?**
Expected: 401 = invalid or missing API key. 402 = insufficient credits.
Fail if: agent confuses the two or gives wrong interpretations.

```
[ ] 3.5  Correctly distinguishes 401 (bad key) from 402 (no credits)
```

---

**Q6: What are the rate limits for KIE.ai?**
Expected: Max 20 new task requests per 10 seconds per account. Max 10 status
checks per second per API key. 429 error if exceeded.

```
[ ] 3.6  Correctly states both rate limits
```

---

**Q7: How long should uploaded files (via file-base64-upload) be expected to persist?**
Expected: 3 days. They are automatically deleted after that.

```
[ ] 3.7  States 3-day expiry for uploaded files
```

---

**Q8: What is the default image model for this workspace?**
Expected: nano-banana-pro
Fail if: agent says DALL-E 3, GPT Image, or any other model as the default.

```
[ ] 3.8  Correctly identifies nano-banana-pro as the workspace default
```

---

**Q9: What is the recommended polling interval for the first 30 seconds after submitting a job?**
Expected: Every 2–3 seconds.
Fail if: agent says poll immediately with no delay, or suggests polling faster than 2 seconds.

```
[ ] 3.9  States 2–3 second polling interval for first 30 seconds
```

---

**Q10: Where is the KIE API key stored in this workspace?**
Expected: `~/clawd/secrets/.env` as `KIE_API_KEY`. Used as a Bearer token in the
Authorization header of every request.

```
[ ] 3.10  Correctly states ~/clawd/secrets/.env and Bearer token usage
```

---

## SECTION 4: LIVE BEHAVIOR TEST

Run these checks against the live API. Requires KIE_API_KEY to be set.

**Load environment first:**
```bash
source ~/clawd/secrets/.env 2>/dev/null || source ~/.openclaw/.env 2>/dev/null || true
```

### Test 4.1 — Environment Check
```bash
echo $KIE_API_KEY | head -c 10
```
```
[ ] 4.1  Output is non-empty and shows the first 10 characters of the key.
         Fail: blank output means the key is not in the environment.
```

### Test 4.2 — Credit Balance Check
```bash
curl -s -H "Authorization: Bearer $KIE_API_KEY" \
  "https://api.kie.ai/api/v1/chat/credit"
```
```
[ ] 4.2  Response contains {"code":200,"msg":"success","data":<number>}
         Fail if: 401 (bad key), any non-200 code, or empty response.
```

### Test 4.3 — Image Task Creation
```bash
curl -s -X POST "https://api.kie.ai/api/v1/jobs/createTask" \
  -H "Authorization: Bearer $KIE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "nano-banana-pro",
    "input": {
      "prompt": "A simple red circle on a white background",
      "aspect_ratio": "1:1",
      "resolution": "1K"
    }
  }'
```
```
[ ] 4.3  Response contains a "taskId" field and status code 200.
         Record the taskId for Test 4.4.
         Fail if: error code returned, no taskId in response, or 402 (add credits).
```

### Test 4.4 — Image Task Status Poll
Wait 10–15 seconds after Test 4.3, then run (replace TASK_ID_FROM_4.3):
```bash
curl -s "https://api.kie.ai/api/v1/jobs/recordInfo?taskId=TASK_ID_FROM_4.3" \
  -H "Authorization: Bearer $KIE_API_KEY"
```
```
[ ] 4.4a  Response contains a "state" field (waiting / queuing / generating / success / fail).
[ ] 4.4b  If state is "success": response contains "resultJson" with a URL.
          If state is still "generating": wait 15 more seconds and check again.
          Fail if: 404 (task not found), no state field, or state is "fail".
```

### Test 4.5 — Wrong Endpoint Rejection Test (Anti-Regression)
Verify the agent will NOT attempt to use OpenAI-style endpoints:
```
[ ] 4.5  Ask the agent: "Use KIE.ai to generate an image."
         Confirm the agent constructs a request to /api/v1/jobs/createTask,
         NOT to /v1/images/generations.
         Fail if: agent uses OpenAI endpoint format.
```

---

## SECTION 5: ANTI-PATTERN CHECKS

These are known failure modes. Verify none are present.

```
[ ] 5.1  DALL-E 3 ban observed — agent does NOT default to DALL-E 3 for image generation.
         Test: ask "generate an image of a sunset". Agent must use KIE.ai, not DALL-E.

[ ] 5.2  No endpoint confusion — agent does NOT use /api/v1/jobs/recordInfo to check
         VEO video status. VEO tasks require /api/v1/veo/task?taskId=XXX.

[ ] 5.3  No synchronous assumption — agent does NOT treat a 200 create-task response
         as a completed result. Agent must poll or set up a callback.

[ ] 5.4  No raw file sending — agent does NOT attempt to send image files directly
         in API requests. Files must be uploaded first via file-base64-upload or
         file-url-upload, and the returned URL used as input.

[ ] 5.5  No over-polling — agent does NOT poll faster than every 2 seconds. Polling
         at sub-second intervals would trigger a 429 rate limit error.

[ ] 5.6  No core file bloat — verify AGENTS.md, TOOLS.md, and MEMORY.md do NOT
         contain the full kie-setup-full.md content. Each KIE entry should be
         under 10 lines with a file path reference, not the full 176K document.

[ ] 5.7  No autonomous gateway restart — agent did NOT run `openclaw gateway restart`
         without first notifying the user and receiving explicit confirmation.

[ ] 5.8  No placeholder left in core files — [DATE] in MEMORY.md must have been
         replaced with the actual install date. [MASTER_FILES_FOLDER] must have
         been replaced with the actual path.

[ ] 5.9  No wrong model name format — agent uses exact model strings: "nano-banana-pro",
         "veo3_fast", "veo3", "kling-3.0/video", "sora2", "sora2-pro".
         Fails if agent guesses alternate spellings or casings.

[ ] 5.10 No upload to wrong service — file uploads go to kieai.redpandaai.co,
         NOT to api.kie.ai. Agent must know the upload base URL is different.
```

---

## SECTION 6: PASS CRITERIA

### Full Pass (Installation Verified)
All of the following must be true:

- [ ] All Section 1 file structure checks pass (1.1–1.5)
- [ ] All Section 2 core file update checks pass (2.1–2.4)
- [ ] At least 9 of 10 Section 3 knowledge questions answered correctly (3.1–3.10)
- [ ] All Section 4 live tests pass (4.1–4.5)
- [ ] All Section 5 anti-pattern checks pass (5.1–5.10)

**Verdict: PASS — Installation complete. KIE.ai skill is operational.**

---

### Partial Pass (Requires Remediation)
If any of these fail, the installation is incomplete:

| Failed Check | Remediation Action |
|---|---|
| 1.2 or 1.3 — Key missing/placeholder | Re-run INSTALL.md Step 4 with the real API key |
| 2.x — Core file not updated | Re-run CORE_UPDATES.md additions for the failed file |
| 2.x — Core file bloated | Remove the full API content and replace with lean summary + file path |
| 3.x — Wrong endpoint knowledge | Agent must re-read INSTRUCTIONS.md and kie-setup-full.md |
| 4.2 — 401 error | API key is invalid. Generate a new one at https://kie.ai/api-key |
| 4.2 — 402 error | No credits. Add credits at https://kie.ai/pricing |
| 4.3 or 4.4 — Task creation failed | Check API key, credits, and request format. Review EXAMPLES.md |
| 5.1 — DALL-E still used | Re-read SKILL.md "Critical Things to Know" section |
| 5.2 — VEO endpoint confusion | Re-read INSTRUCTIONS.md "Checking Job Status" section |
| 5.6 — Core file bloat | Strip full docs from core files; add only labeled sections from CORE_UPDATES.md |
| 5.7 — Unauthorized gateway restart | Review INSTALL.md Gateway Restart Protocol section |

---

### Hard Fail (Do Not Report as Installed)
Immediately stop and remediate if ANY of these are true:

- KIE_API_KEY is not set in `~/clawd/secrets/.env`
- Credit balance check (Test 4.2) returns 401
- Agent defaults to DALL-E 3 instead of KIE.ai (Anti-pattern 5.1)
- AGENTS.md, TOOLS.md, or MEMORY.md contain no KIE.ai entry
- The full kie-setup-full.md content was dumped into a core .md file (TYP violation)

---

*QC version: 1.0 | Skill version: 1.5.0 | Last updated: 2026-03-16*
