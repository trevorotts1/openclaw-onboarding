# QC Checklist: KIE Audio (TTS + Suno Music + STT status)

## 1. Purpose
Enables the agent to generate TTS (Gemini 3.1 Flash / 2.5 Pro + ElevenLabs
dialogue-v3 / multilingual-v2 / turbo-2-5 via the generic Market `createTask`
route) and Suno music/sound generation (the DEDICATED `/api/v1/generate`
family — never `createTask`), using the EXISTING fleet credential KIE_API_KEY,
with correct payload shapes, caps, validation, async completion handling, and
REAL audio QC. STT is registered as `ADVERTISED_NOT_YET_VERIFIED`,
`dispatch_enabled: false` — this skill cannot do speech-to-text and must never
pretend otherwise.

## 2. Installation Checks
- [ ] Skill folder exists and contains `SKILL.md`, `INSTALL.md`,
      `INSTRUCTIONS.md`, `EXAMPLES.md`, `CORE_UPDATES.md`, `CHANGELOG.md`,
      `QC.md`, `PREREQS.json`, `models.json`, `skill-version.txt`,
      `references/` (tts.md, music.md, stt.md, qc.md),
      `scripts/` (validate_audio_request.py, normalize_alias.py), `wire.sh`,
      and the `68-kie-audio.skill` package.
- [ ] `models.json` validates as JSON; stt entry has `dispatch_enabled: false`,
      `status: "ADVERTISED_NOT_YET_VERIFIED"`, `active: false`, and quotes the
      negative trail; no duplicate canonical ids; every entry carries
      `source_url`.
- [ ] The references document the correct model ids (`google/gemini-3-1-flash-tts`, etc.)
      and endpoints (`https://api.kie.ai/api/v1/jobs/createTask` for TTS;
      `/api/v1/generate` family for Suno).
- [ ] `skill-version.txt` reads `v1.0.0`.
- [ ] No real credential value appears anywhere in the skill files.

## 3. Dependency Checks
- [ ] TYP (Skill 01) and BYUP (Skill 02) are installed first.
- [ ] `KIE_API_KEY` is present (SET) — referenced, never printed.
- [ ] `curl` and `python3` (stdlib only) are available.
- [ ] The installer understands the three sub-domains and their API families:
      TTS = generic Market `createTask`; Suno = DEDICATED routes (never
      `createTask`); STT = not dispatchable.

## 4. Key Detection
- [ ] Search the standard secret locations in order: `~/.openclaw/secrets/.env`,
      `~/.openclaw/openclaw.json` `env.vars`, `~/clawd/secrets/.env`, and the
      live environment. Primary variable: `KIE_API_KEY`.
- [ ] QC fails only if the agent reports the key missing WITHOUT checking all
      locations first. A genuinely absent key is a WARN (operator must
      provision), never a fabricated key.

## 5. Functional Checks
- [ ] Confirm `KIE_API_KEY` loads into the environment (presence only; value
      never echoed).
- [ ] Endpoint reachability + key validity:
      `curl -sS -m 30 https://api.kie.ai/api/v1/account/balance -H "Authorization: Bearer $KIE_API_KEY"`
      — JSON body expected; 401 = key wrong, 402 = zero credits. This is the
      zero-cost install check; do NOT run a real generation as the install test.
- [ ] Validator self-tests pass deterministically (exit 0, same output twice):
      - `python3 scripts/validate_audio_request.py --self-test` (13 checks)
      - `python3 scripts/normalize_alias.py --self-test`
- [ ] Confirm the agent can explain: 200 = task accepted, NOT complete;
      Suno callback stages `text` → `first` → `complete` (only complete is
      finished output); media expires after ~14 days; Suno must NEVER go
      through `createTask`; STT dispatch is rejected with exit 2.

## 6. Real Audio QC (SPEC 9.5 verbatim lists) — after generation, MANDATORY
API success is NOT QC. Actually inspect the result.

### 6.1 TTS QC
- [ ] Valid playable file
- [ ] Language (matches the requested/declared language)
- [ ] Voice identity (the requested voice, not a different one)
- [ ] Pronunciation (names, acronyms, foreign words rendered correctly)
- [ ] Pace (matches requested pace: Natural / Rapid Fire / The Drift / Staccato)
- [ ] Style/emotion (matches requested style: Vocal Smile / Newscaster / Whisper /
      Empathetic / Promo/Hype / Deadpan)
- [ ] Clipping/distortion (no audible clipping at peaks, no artifacts)
- [ ] Speaker ordering/dialogue correctness (multi-speaker tasks: each turn is
      spoken by the right speaker, in order)

### 6.2 Music QC
- [ ] Valid playable file
- [ ] Requested duration/model behavior (duration only effective for V5_5
      custom; check the returned duration)
- [ ] Musical genre/style (matches prompt/style intent)
- [ ] Vocals/instrumental intent (instrumental request returned instrumental;
      vocal request returned vocals)
- [ ] Lyrics fidelity when supplied (lyrics match the supplied text)
- [ ] No truncation/clipping (track not cut off early; no clipping)
- [ ] Callback completion stage (reached `complete` — `text`/`first` stages are
      not finished output)

### 6.3 STT QC
- [ ] n/a — STT is `ADVERTISED_NOT_YET_VERIFIED`, `dispatch_enabled: false`.
      Nothing can be generated, so nothing can be QC'd. Do NOT fabricate a
      check for a route that must not be dispatched.

## 7. File-level checks (before declaring QC pass)
- [ ] File downloads and opens in a player (not 0-byte, not an HTML error page
      saved as .mp3).
- [ ] Duration sanity via file header (ffprobe/mediainfo or equivalent):
      roughly matches the request; 0s or absurd value = failure.
- [ ] Sample rate sanity (expected 44.1/48kHz; corrupted header = failure).
- [ ] No truncation: file length matches announced duration.

## 8. QC Score
- Score this skill from **0 to 10** after running the checks above.
  - **10/10**: All installation, dependency, key-detection, functional, and
    audio checks pass with no ambiguity.
  - **8-9/10**: Core behavior works, one or two non-critical items need cleanup.
  - **6-7/10**: Basic install exists, missing a meaningful validation or behavior.
  - **0-5/10**: Missing prerequisites, broken verification, wrong secrets
    handling, or failed functional tests.
- Record final result here:
  - **QC Score:** ____ / 10
  - **Status:** Pass / Needs Fix / Blocked
  - **Notes:** ____________________________________________

## 9. QC Loop Rule
- Run at most **5 total QC/fix rounds** for this skill.
- After each failed round: record which items failed, apply the smallest fix,
  re-run only the failed checks. After the 5th failed round, stop and escalate.

---

## 🔴 INSTALL-TIME QC RUBRIC (v9.3.0+ standard)

After install, score yourself honestly against this rubric. **Pass gate: 8.5/10
minimum.** Below 8.5 = loop back and fix until passing (max 5 loops, then
escalate to owner).

| Section | Points | What it tests |
|---|---|---|
| Prerequisites acknowledged | 1.0 | TYP (Skill 01) + BYUP (Skill 02) installed this session. |
| All skill .md files read before any execution | 1.0 | SKILL.md, INSTALL.md, CORE_UPDATES.md, QC.md, references read BEFORE any command. |
| INSTALL.md steps executed in order | 1.5 | No skipping/reordering/improvising. |
| Credential confirmed, value never printed | 1.5 | KIE_API_KEY SET; never echoed/catted/logged. |
| Functional checks pass | 1.5 | Balance endpoint returns JSON; both validators pass self-test twice. |
| CORE_UPDATES.md applied surgically (via wire.sh) | 1.0 | Only labeled sections into labeled core files via `bash wire.sh`. No SOUL/IDENTITY/USER/HEARTBEAT touched. |
| Skill-specific QC items above all checked | 1.5 | Every checkbox in sections 2-7 ticked. |
| Security | 0.5 | No secret leaked into chat/logs/commits/.md files. |
| Owner-facing confirmation message sent | 0.5 | Plain-English "Skill 68 active" summary. |

### Self-audit before declaring done
1. All .md files read before execution: ✓ / ✗
2. INSTALL.md step order followed verbatim: ✓ / ✗
3. QC rubric score: __/10 (≥ 8.5 to pass)
4. Validators exited 0 twice each (determinism): ✓ / ✗
5. No shortcuts taken: ✓ / ✗
6. Owner confirmation message sent: ✓ / ✗

If any answer is ✗, this skill is NOT done. Loop back.
