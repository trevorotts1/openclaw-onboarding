# Cinematic Forge (Skill 28) - QC Checklist

Run this after installation to verify the skill is installed and the agent has learned it correctly.

---

## 1. File Structure Checks

Run each command and verify the expected output.

```bash
# Check skill folder exists
ls ~/.openclaw/skills/cinematic-forge/
```
**Expected:** `SKILL.md`, `INSTALL.md`, `README.md`, `CORE_UPDATES.md` all present

```bash
# Check no extra or corrupt files
find ~/.openclaw/skills/cinematic-forge/ -type f | sort
```
**Expected:** Exactly 4 files. No `.tmp`, `.bak`, or partial downloads.

```bash
# Check SKILL.md is not empty or truncated
wc -l ~/.openclaw/skills/cinematic-forge/SKILL.md
```
**Expected:** 747 lines (or very close). A value under 100 means the file was truncated.

---

## 2. Core File Update Checks

Verify that the Teach Yourself Protocol successfully wrote pointers into the agent's core files.

### AGENTS.md
```bash
grep -n "Cinematic Forge" ~/clawd/AGENTS.md
```
**Expected:** At minimum one match containing `Cinematic Forge (Skill 28)`. The full block should include:
- `Intake is 14 questions, asked one at a time`
- `Track progress in a state file`
- `Always verify KIE.ai balance before spending credits`
- `Always QC output video`

### TOOLS.md
```bash
grep -n "Cinematic Forge" ~/clawd/TOOLS.md
```
**Expected:** Entry present under a `## Video Skills Suite` section with:
- Location pointing to `~/.openclaw/skills/cinematic-forge/`
- Purpose described as end-to-end video production pipeline
- Provider listed as `KIE.ai`

### MEMORY.md
```bash
grep -n "Cinematic Forge" ~/clawd/MEMORY.md
```
**Expected:** At least one pointer line, e.g.:
`Cinematic Forge (Skill 28): ~/.openclaw/skills/cinematic-forge/`

**FAIL condition:** Any of the three files has zero matches. This means the agent did not apply CORE_UPDATES.md and the skill will not be recalled in future sessions.

---

## 3. Dependency Checks

```bash
# FFmpeg must be installed
ffmpeg -version
```
**Expected:** Version output. Anything else = FFmpeg not installed. Run `brew install ffmpeg` (macOS) or `sudo apt install ffmpeg` (Linux).

```bash
# KIE.ai API key must be set
source ~/clawd/secrets/.env && echo "KIE_API_KEY=${KIE_API_KEY:0:8}..."
```
**Expected:** `KIE_API_KEY=xxxxxxxx...` (first 8 chars visible, rest masked). Empty = key not set.

```bash
# Verify KIE.ai key is live (not just present)
source ~/clawd/secrets/.env && curl -s "https://api.kie.ai/api/v1/user/credits" \
  -H "Authorization: Bearer $KIE_API_KEY" | python3 -m json.tool
```
**Expected:** JSON response containing a `credits` or `balance` field. A `401` or `403` error = invalid key.

```bash
# GHL/Convert and Flow PIT (optional but verify if user has GHL)
source ~/clawd/secrets/.env && echo "GHL_PIT=${GHL_PIT:0:6}..."
```
**Expected:** Token prefix visible. If the user has GHL, this must be set. If no GHL, imgBB key should be set instead.

---

## 4. Knowledge Verification Questions

Ask the agent each question directly. Expected answers are listed. A wrong answer means the agent did not fully learn SKILL.md.

**Q1: How many intake questions does Cinematic Forge ask, and what is the rule for how they are delivered?**
Expected answer: 14 questions, asked one at a time. The agent waits for the user's full answer before asking the next question.

**Q2: What happens to the audio that VEO 3.1 Fast generates inside each video segment?**
Expected answer: It is discarded entirely. All audio is replaced with separately generated ElevenLabs (voice/SFX) and Suno (music) tracks mixed via FFmpeg.

**Q3: Can a narrator voiceover and character dialogue appear in the same video segment?**
Expected answer: No. This is a hard rule. If a segment has characters speaking on screen (lips moving), there is no narrator. If a segment has narrator voiceover, characters on screen do not speak.

**Q4: What is the primary video format and when is the secondary format created?**
Expected answer: 9:16 vertical is always the primary format. 16:9 horizontal is only created AFTER the 9:16 version has been approved by the user.

**Q5: What must happen before the agent starts any video generation?**
Expected answer: (a) Create the project folder structure, (b) check KIE.ai credit balance, (c) calculate and present a budget estimate to the user, (d) wait for user confirmation. Generation cannot begin until the user explicitly approves.

**Q6: What is `project-state.json` and why does it exist?**
Expected answer: A session recovery file created at the start of every project. It tracks which segments are complete, their taskIds, file paths, audio clips, and overall production status. It is updated after every completed step so a new session can resume exactly where the previous one left off if the session crashes or times out.

**Q7: What model is used for video generation, and what does it cost per segment?**
Expected answer: VEO 3.1 Fast (`veo3_fast`) via KIE.ai. $0.40 per 8-second segment, including Extend operations.

**Q8: How long is each VEO video segment, and how is a 90-second video produced?**
Expected answer: Each segment is 8 seconds. A 90-second video requires 12 segments: 11 full segments (88 seconds) + 1 segment trimmed to 2 seconds via FFmpeg.

**Q9: What is the correct term for the GHL/Convert and Flow authentication credential?**
Expected answer: Private Integration Token (PIT). It is NOT called an API key.

**Q10: What should the agent do if the `video-frames` or `summarize` skill is missing when the user provides a reference video (Q12)?**
Expected answer: Install the missing tool on the spot (not skip the analysis). Then use the Teach Yourself Protocol to learn the skill, write a summary to TOOLS.md and MEMORY.md, and proceed with the reference video analysis.

**Q11: When is Topaz upscaling offered to the user?**
Expected answer: Only AFTER the user has approved the draft video. It is never offered or run on unapproved content.

**Q12: Which agent model is explicitly banned from running Cinematic Forge, and why?**
Expected answer: Kimi K2.5. It cannot make tool calls (API requests), which is required for every phase of production.

---

## 5. Live Behavior Test

This test verifies the agent behaves correctly in a real interaction. Use a fresh conversation window.

### Test Prompt
> "Create a 15-second test video of a person walking on a beach at sunset."

### Expected Agent Behavior (in order)

1. **Opening statement** - Agent acknowledges the request and says it will ask 14 questions one at a time.

2. **Question 1 only** - Agent asks about the concept/big picture. It does NOT ask multiple questions at once.

3. **Waits** - After you answer Q1, agent asks Q2 (target audience). Continues one question at a time.

4. **Budget confirmation before generation** - Before generating any assets, agent presents a cost estimate and asks for approval.

5. **Does NOT start generation without approval** - If you say "go ahead" at the right moment, agent creates the project folder structure and initializes `project-state.json` before any API call.

6. **Progress updates** - After each segment completes, agent sends a status update ("Segment 1 of 2 complete...").

### Pass Criteria
- [ ] Agent asks exactly 1 question at a time (not a batched list)
- [ ] Agent does not begin generation before presenting a cost estimate
- [ ] Agent does not begin generation without explicit user confirmation
- [ ] Agent creates the project folder and `project-state.json` before making KIE.ai calls
- [ ] Agent provides progress updates after each segment

### Fail Indicators
- Agent asks multiple questions at once → SKILL.md intake rules were not learned
- Agent begins generating without cost confirmation → critical rule 10 was missed
- Agent uses Kimi K2.5 → wrong model, switch to MiniMax M2.5 or Claude Sonnet/Opus

---

## 6. Anti-Pattern Checks

These are behaviors the agent must NEVER exhibit. Verify each one is absent.

| Anti-Pattern | How to Check | Expected Result |
|---|---|---|
| Dumps all 14 questions at once | Ask agent to start a video project | Agent asks exactly 1 question |
| Starts generation without budget approval | Monitor agent behavior after intake completes | Agent presents cost estimate and waits |
| Uses VEO audio in final video | Ask agent to describe assembly steps | Agent says VEO audio is discarded, replaced with ElevenLabs + Suno |
| Narrator and dialogue overlap | Ask agent: "Can a narrator and character speak in the same segment?" | Agent says no, hard rule |
| Creates 16:9 before 9:16 approved | Ask agent about format workflow | Agent says 9:16 first, 16:9 only after approval |
| Skips project-state.json | Ask agent what file tracks session recovery | Agent names `project-state.json` and explains its purpose |
| Provides END image to VEO Segment 1 | Ask agent: "For Segment 1, do you provide a start image, end image, or both?" | Agent says start image only; end images constrain output and produce stiff video |
| Offers Topaz upscale during production | Ask agent when Topaz is offered | Agent says only after the user approves the draft |
| Uses wrong GHL terminology | Ask agent: "What credential do I need for GHL media upload?" | Agent says "Private Integration Token (PIT)" not "API key" |
| Skips TYP prerequisite check | Ask agent: "What do you need before you can run Cinematic Forge?" | Agent names the Teach Yourself Protocol as mandatory |
| Triggers gateway restart autonomously | Review INSTALL.md gateway section | Agent must notify user and wait for `/restart` command, never self-trigger |

---

## 7. Pass Criteria Summary

The skill is considered fully installed and operational when ALL of the following are true:

- [ ] All 4 skill files present in `~/.openclaw/skills/cinematic-forge/`
- [ ] `SKILL.md` is not truncated (approximately 747 lines)
- [ ] `AGENTS.md` contains the Cinematic Forge (Skill 28) rule block
- [ ] `TOOLS.md` contains the Cinematic Forge entry under Video Skills Suite
- [ ] `MEMORY.md` contains the Cinematic Forge pointer
- [ ] FFmpeg installed and responsive
- [ ] KIE.ai API key present and returns a valid response from the credits endpoint
- [ ] Agent answers all 12 knowledge verification questions correctly
- [ ] Live behavior test shows one-question-at-a-time intake and pre-generation budget confirmation
- [ ] All 11 anti-patterns are absent from agent behavior

**Score: 10/10 checks passed = PASS. Any failure = investigate and re-run the relevant installation step.**

---

## 8. Recovery Steps by Failure Type

| Failure | Fix |
|---|---|
| Skill files missing | Re-run the onboarding installer so files copy to `~/.openclaw/skills/cinematic-forge/` |
| Core files not updated | Re-apply `CORE_UPDATES.md` manually — add the exact blocks listed in that file to AGENTS.md, TOOLS.md, MEMORY.md |
| Agent gives wrong answers to knowledge questions | Re-teach: say "Teach yourself this skill" and paste the full contents of `SKILL.md` |
| KIE.ai key missing or invalid | Add `KIE_API_KEY=...` to `~/clawd/secrets/.env` and verify with the credits endpoint |
| FFmpeg not found | `brew install ffmpeg` (macOS) or `sudo apt install ffmpeg` (Linux/WSL) |
| Agent asks all questions at once | Agent did not internalize intake rules — re-teach SKILL.md and emphasize the intake section |
| Wrong model (Kimi K2.5) | Switch conversation to MiniMax M2.5, Claude Opus/Sonnet, or GPT-5.2 |
