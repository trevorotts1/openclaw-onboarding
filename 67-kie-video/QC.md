# QC Checklist: KIE Video (Skill 67)

## 1. Purpose
Enables the agent to generate videos through the KIE.ai API across 37 video models
(Wan 3.0/2.7, Kling 3.0 Omni/3.0/2.6/2.5 Turbo, ByteDance Seedance 2.5/2.0 Mini,
PixVerse V6, MiniMax H3, HappyHorse 1.1/1.0, Gemini Omni Video, Runway Dedicated,
Veo 3.1 Dedicated), with machine-readable registry, model-aware prompt validation
(Rules A–E), payload validation before dispatch, async createTask/dedicated dispatch,
recordInfo/callback waiting, and MANDATORY multi-frame visual QC (Frame 0, Midpoint, Final Frame).

## 2. Installation Checks
- [ ] Skill folder exists and contains `SKILL.md`, `INSTALL.md`,
      `INSTRUCTIONS.md`, `EXAMPLES.md`, `CORE_UPDATES.md`, `CHANGELOG.md`,
      `QC.md`, `PREREQS.json`, `models.json`, `references/`, `scripts/`,
      `wire.sh`, `skill-version.txt`.
- [ ] `models.json` parses as valid JSON; exactly 37 models; no duplicate canonical_model_id;
      every entry has `source_url`, `last_verified_at`, and `cap_status`.
- [ ] The skill package zip does NOT contain `wire.sh` (installers are not shipped in the bundle).
- [ ] `skill-version.txt` reads `v1.1.0`.

## 3. Dependency Checks
- [ ] TYP (Skill 01), BYUP (Skill 02), and KIE Setup (Skill 07) are satisfied (PREREQS.json).
- [ ] `KIE_API_KEY` is present (SET) — QC checks presence only, never value.
- [ ] `curl` available for verification calls.
- [ ] The installer understands ALL video tasks on KIE are ASYNCHRONOUS
      (createTask 200 = created, not completed).

## 4. Key Detection
- [ ] Search the standard secret locations in order: `~/.openclaw/secrets/.env`,
      `~/.openclaw/openclaw.json` `env.vars`, `~/clawd/secrets/.env`, and the
      live environment. Primary variable: `KIE_API_KEY`.
- [ ] QC fails only if the agent reports the key missing WITHOUT checking all
      locations first. A genuinely absent key is a WARN (operator must provision).

## 5. Functional Checks
- [ ] `KIE_API_KEY` loads into the environment (presence only).
- [ ] Connectivity proven WITHOUT burning credits: recordInfo with an invalid
      taskId answers non-401 (404/400 = key authenticates, endpoint alive).
- [ ] Confirm the agent can explain: createTask 200 ≠ done; state enum
      waiting/queuing/generating/success/fail; dedicated endpoints for Runway/Veo;
      Runway 1080p 5s limitation; 429 = rate limited (back off);
      callbacks are HMAC-SHA256 signed; result URLs expire ~24h, media 14 days.
- [ ] Run validator test suites — every one must print PASS and exit 0:
      `python3 scripts/normalize_alias.py --self-test` (PASS)
      `python3 scripts/select_video_model.py --self-test` (PASS)
      `python3 scripts/validate_prompt.py --self-test` (PASS)
      `python3 scripts/validate_payload.py --self-test` (PASS)
- [ ] wire.sh run twice against a scratch workspace: second run reports no
      change for all three targets; exactly one BEGIN/END block per target;
      exactly one sentinel.

## 6. Real Visual Asset QC
- [ ] Multi-frame inspection: download the full-resolution video asset and inspect
      Frame 0 (Start), Frame T/2 (Midpoint), and Frame N (End) — never QC from a filename or a 200 OK.
- [ ] Duration and dimensions vs requested: verify container (`mp4`/`mov`), video codec (`h264`/`h265`),
      audio stream presence when requested, and pixel dimensions.
- [ ] Subject identity & anatomical integrity: check facial geometry, skin tones, limbs, and non-morphing geometry.
- [ ] Smooth motion dynamics: ensure zero jarring jumps, strobing flicker, or severe jitter.

## 7. QC Score
- Score this skill from **0 to 10** after running the checks above.
  - **10/10**: All installation, dependency, key-detection, functional, and
    visual checks pass with no ambiguity.
  - **8-9/10**: Core behavior works, one or two non-critical items need cleanup.
  - **6-7/10**: Basic install exists, missing a meaningful validation or behavior.
  - **0-5/10**: Missing prerequisites, broken verification, wrong secrets handling, or failed functional tests.
- Record final result here:
  - **QC Score:** ____ / 10
  - **Status:** Pass / Needs Fix / Blocked
  - **Notes:** ____________________________________________

## 8. QC Loop Rule
- Run at most **5 total QC/fix rounds** for this skill.
- After each failed round: record which items failed, apply the smallest fix,
  re-run only the failed checks. After the 5th failed round, stop and escalate.

---

## 🔴 INSTALL-TIME QC RUBRIC

After install, score yourself honestly against this rubric. **Pass gate: 8.5/10 minimum.**

| Section | Points | What it tests |
|---|---|---|
| Prerequisites acknowledged | 1.0 | TYP (01) + BYUP (02) + KIE Setup (07) satisfied. |
| All skill .md files read before any execution | 1.0 | SKILL.md, INSTALL.md, INSTRUCTIONS.md, CORE_UPDATES.md, QC.md, references/* read BEFORE any command. |
| INSTALL.md steps executed in order | 1.5 | No skipping/reordering/improvising. |
| Credential confirmed at canonical path, value never printed | 1.5 | KIE_API_KEY SET; never echoed/catted/logged; checked all three env stores. |
| Functional checks pass | 1.5 | Credit-free connectivity probe + all four validator self-tests PASS + wire.sh idempotent. |
| CORE_UPDATES.md applied surgically | 1.0 | wire.sh only; own markers only; no SOUL/IDENTITY/USER/HEARTBEAT touched. |
| Skill-specific QC items above all checked | 1.5 | Every checkbox in sections 2-6 ticked. |
| Security | 0.5 | No secret leaked into chat/logs/commits/.md files. |
| Owner-facing confirmation message sent | 0.5 | Plain-English "Skill 67 active" summary. |

### Self-audit before declaring done
1. All .md files read before execution: ✓ / ✗
2. INSTALL.md step order followed verbatim: ✓ / ✗
3. QC rubric score: __/10 (≥ 8.5 to pass)
4. All four validator self-tests exit 0: ✓ / ✗
5. wire.sh second run no-change: ✓ / ✗
6. No shortcuts taken: ✓ / ✗
7. Owner confirmation message sent: ✓ / ✗

If any answer is ✗, this skill is NOT done. Loop back.
