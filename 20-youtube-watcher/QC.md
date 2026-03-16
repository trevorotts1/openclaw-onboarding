# QC Checklist — YouTube Watcher (Skill 20)

Run this after install to verify the skill is working correctly.
Each section must fully pass before marking the install complete.

---

## 1. File Structure Checks

Run each check. Mark pass/fail.

- [ ] `~/.openclaw/skills/youtube-watcher/` directory exists
  ```bash
  ls ~/.openclaw/skills/youtube-watcher/
  ```

- [ ] `~/.openclaw/skills/youtube-watcher/SKILL.md` exists
  ```bash
  test -f ~/.openclaw/skills/youtube-watcher/SKILL.md && echo PASS || echo FAIL
  ```

- [ ] `~/.openclaw/skills/youtube-watcher/scripts/get_transcript.py` exists
  ```bash
  test -f ~/.openclaw/skills/youtube-watcher/scripts/get_transcript.py && echo PASS || echo FAIL
  ```

- [ ] File count is correct (2 files total: SKILL.md + scripts/get_transcript.py)
  ```bash
  find ~/.openclaw/skills/youtube-watcher -type f | wc -l
  # Expected: 2
  ```

- [ ] `yt-dlp` binary is available in PATH
  ```bash
  which yt-dlp && echo PASS || echo FAIL
  ```

**Section pass criteria:** All 5 checks return PASS or expected values.

---

## 2. Core File Update Checks

Verify that ONLY the allowed core files were updated, and forbidden files were left untouched.

### Allowed files — must contain youtube-watcher content

- [ ] `AGENTS.md` contains a TYP-before-execution rule for youtube-watcher
  ```bash
  grep -i "youtube" ~/.openclaw/AGENTS.md && echo PASS || echo FAIL
  ```

- [ ] `TOOLS.md` contains tool commands or endpoint references for this skill
  ```bash
  grep -i "youtube\|get_transcript\|yt-dlp" ~/.openclaw/TOOLS.md && echo PASS || echo FAIL
  ```

- [ ] `MEMORY.md` contains a path reference pointing to the full skill documentation
  ```bash
  grep -i "youtube" ~/.openclaw/MEMORY.md && echo PASS || echo FAIL
  ```

- [ ] `MEMORY.md` does NOT contain the full SKILL.md content pasted inline (no bulk dump)
  ```bash
  wc -l ~/.openclaw/MEMORY.md
  # Flag for review if line count grew by more than ~10 lines from this install
  ```

### Forbidden files — must NOT have been modified

- [ ] `SOUL.md` last-modified timestamp is unchanged from before install
  ```bash
  ls -la ~/.openclaw/SOUL.md
  # Compare to known pre-install timestamp
  ```

- [ ] `IDENTITY.md` last-modified timestamp is unchanged
  ```bash
  ls -la ~/.openclaw/IDENTITY.md
  ```

- [ ] `HEARTBEAT.md` last-modified timestamp is unchanged
  ```bash
  ls -la ~/.openclaw/HEARTBEAT.md
  ```

**Section pass criteria:** Allowed files have relevant entries; forbidden files show no modification.

---

## 3. Knowledge Verification Questions

Ask the agent each question directly. Verify the answer matches expected.

- [ ] **Q: What are the five trigger phrases for the YouTube Watcher skill?**
  Expected answer (any phrasing that covers all five):
  - "watch youtube"
  - "summarize video"
  - "video transcript"
  - "youtube summary"
  - "analyze video"

- [ ] **Q: What system dependency does YouTube Watcher require?**
  Expected: `yt-dlp` must be installed and available in PATH.

- [ ] **Q: What happens if a video has no subtitles or closed captions?**
  Expected: The script will fail with an error message.

- [ ] **Q: Which core files are non-relevant for this skill and must NOT be edited?**
  Expected: `SOUL.md`, `IDENTITY.md`, `HEARTBEAT.md`

- [ ] **Q: What protocol must be confirmed before this skill can be installed or executed?**
  Expected: Teach Yourself Protocol (TYP)

- [ ] **Q: Where is the full skill documentation stored after TYP install?**
  Expected: In the OpenClaw master files folder (e.g. `~/Downloads/openclaw-master-files/`) as a `.md` file — NOT dumped inline into AGENTS.md/TOOLS.md/MEMORY.md.

- [ ] **Q: What is the exact command template to get a transcript?**
  Expected:
  ```bash
  python3 {baseDir}/scripts/get_transcript.py "https://www.youtube.com/watch?v=VIDEO_ID"
  ```

**Section pass criteria:** Agent answers all 7 questions correctly without hesitation or hallucination.

---

## 4. Live Behavior Test

Test actual skill execution end-to-end.

- [ ] **Step 1 — Trigger the skill by phrase:**
  Say to the agent: `"Summarize this video: https://www.youtube.com/watch?v=dQw4w9WgXcQ"`

  Expected agent behavior:
  1. Recognizes this as a "summarize video" trigger
  2. Calls `get_transcript.py` with the URL
  3. Reads the returned transcript text
  4. Returns a human-readable summary (not raw JSON or raw subtitle data)

- [ ] **Step 2 — Confirm correct script path is used:**
  Agent must resolve `{baseDir}` to `~/.openclaw/skills/youtube-watcher` and call:
  ```bash
  python3 ~/.openclaw/skills/youtube-watcher/scripts/get_transcript.py "..."
  ```
  NOT a path inside the onboarding folder.

- [ ] **Step 3 — No-subtitle error handling:**
  Say: `"Get the transcript for a video with no captions."`
  Expected: Agent reports that the video has no subtitles and does not crash silently or return empty output.

**Section pass criteria:** Steps 1 and 2 succeed; Step 3 returns a clear error message instead of silent failure.

---

## 5. Anti-Pattern Checks

Verify the agent did NOT do any of the following during install.

- [ ] Agent did NOT paste full SKILL.md content into AGENTS.md, TOOLS.md, or MEMORY.md
  ```bash
  wc -l ~/.openclaw/AGENTS.md ~/.openclaw/TOOLS.md ~/.openclaw/MEMORY.md
  # Each file should have grown by no more than ~5-10 lines from this install
  ```

- [ ] Agent did NOT edit SOUL.md, IDENTITY.md, or HEARTBEAT.md
  (Verify via timestamps checked in Section 2)

- [ ] Agent did NOT attempt to trigger a gateway restart autonomously
  (Review session log — no `openclaw gateway restart` command should have been run)

- [ ] Agent did NOT install before completing all TYP reads
  (Ask: "What files did you read before installing?" — must include SKILL.md,
  youtube-watcher-full.md, upstream-original/SKILL.md, CORE_UPDATES.md, INSTALL.md, INSTRUCTIONS.md)

- [ ] Agent did NOT skip the TYP gate and proceed directly to install
  (Confirm TYP was verified in session context before any install step was taken)

- [ ] Agent did NOT use `USER.md` unless there was an explicit need tied to user preferences or routing
  (Check if USER.md was modified — if yes, confirm a clear reason exists)

**Section pass criteria:** Zero anti-patterns detected.

---

## 6. Pass Criteria Summary

| Section | Status |
|---|---|
| 1. File Structure | [ ] PASS / [ ] FAIL |
| 2. Core File Updates | [ ] PASS / [ ] FAIL |
| 3. Knowledge Verification | [ ] PASS / [ ] FAIL |
| 4. Live Behavior Test | [ ] PASS / [ ] FAIL |
| 5. Anti-Pattern Checks | [ ] PASS / [ ] FAIL |

**Overall install result:**
- All 5 sections PASS → Install is complete and verified.
- Any section FAIL → Do not mark install complete. Investigate and re-run failed section only.

---

## Notes

- Version verified against: `youtube-watcher v1.0.0` (upstream), wrapper `v1.5.0`
- QC written: 2026-03-16
- If `yt-dlp` is not installed, the live behavior test will fail. Install via `brew install yt-dlp` or `pip install yt-dlp` before re-running Section 4.
