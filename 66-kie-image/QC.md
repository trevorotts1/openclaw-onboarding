# QC Checklist: KIE Image (Skill 66)

## 1. Purpose
Enables the agent to generate images through the KIE.ai Market API across 14
image families (GPT Image 2, Qwen Image 3.0/Pro, Seedream 5.0 Pro/Lite/4.5,
Nano Banana 2/2 Lite/Pro/legacy, Wan 2.7 Image, FLUX.2, Z-Image, Ideogram V3,
Imagen 4), with machine-readable registry, model-aware prompt validation
(spec 5 rules A-E), payload validation before dispatch, async createTask +
recordInfo/callback waiting, and MANDATORY real visual QC (spec 7.6).

## 2. Installation Checks
- [ ] Skill folder exists and contains `SKILL.md`, `INSTALL.md`,
      `INSTRUCTIONS.md`, `EXAMPLES.md`, `CORE_UPDATES.md`, `CHANGELOG.md`,
      `QC.md`, `PREREQS.json`, `models.json`, `references/`, `scripts/`,
      `wire.sh`, `skill-version.txt`.
- [ ] `models.json` parses as valid JSON; no duplicate canonical_model_id;
      every entry has `source_url` and `last_verified_at` and a `cap_status`.
- [ ] The skill zip does NOT contain `wire.sh` (installers are not shipped in
      the bundle).
- [ ] `skill-version.txt` reads `v1.0.0`.

## 3. Dependency Checks
- [ ] TYP (Skill 01) and BYUP (Skill 02) are installed first (PREREQS.json).
- [ ] `KIE_API_KEY` is present (SET) — QC checks presence only, never value.
- [ ] `curl` available for verification calls.
- [ ] The installer understands ALL image tasks on KIE Market are
      ASYNCHRONOUS (createTask 200 = created, not completed) — unlike Agnes
      Image 63, which is synchronous.

## 4. Key Detection
- [ ] Search the standard secret locations in order: `~/.openclaw/secrets/.env`,
      `~/.openclaw/openclaw.json` `env.vars`, `~/clawd/secrets/.env`, and the
      live environment. Primary variable: `KIE_API_KEY`.
- [ ] QC fails only if the agent reports the key missing WITHOUT checking all
      locations first. A genuinely absent key is a WARN (operator must
      provision), never a fabricated key.

## 5. Functional Checks
- [ ] `KIE_API_KEY` loads into the environment (presence only).
- [ ] Connectivity proven WITHOUT burning credits: recordInfo with an invalid
      taskId answers non-401 (404/400 = key authenticates, endpoint alive).
- [ ] Confirm the agent can explain: createTask 200 ≠ done; state enum
      waiting/queuing/generating/success/fail; 429 = rate limited (back off);
      callbacks are HMAC-SHA256 signed; result URLs expire ~24h, media 14 days;
      GPT Image 2 ratio exclusions at 2K/4K (5:4, 4:5, 3:1, 1:3, 9:21), "auto"
      → 1K only, 1:1 never 4K.
- [ ] Run validator test suites — every one must print PASS and exit 0:
      `python3 scripts/normalize_alias.py --self-test` (PASS)
      `python3 scripts/select_image_model.py --self-test` (PASS)
      `python3 scripts/validate_prompt.py --self-test` (PASS)
      `python3 scripts/validate_payload.py --self-test` (PASS)
- [ ] wire.sh run twice against a scratch workspace: second run reports no
      change for all three targets; exactly one BEGIN/END block per target;
      exactly one sentinel.

## 6. Real Visual Asset QC (spec 7.6)
- [ ] Visual asset inspection: download the full-resolution asset and inspect
      it — never QC from a filename or a 200 OK.
- [ ] Dimensions vs requested: GPT Image 2 auto→1K only, 1:1 never 4K, excluded
      ratios never silently returned at 2K/4K; Seedream tier maps to the
      expected resolution; refs respect Wan's min 240 px INPUT rule.
- [ ] Reference & edit fidelity: subject identity/faces/product geometry/
      colors; edit preservation; logo I2I actually used; style-reference-only
      directive present whenever style refs attached.

## 7. QC Score
- Score this skill from **0 to 10** after running the checks above.
  - **10/10**: All installation, dependency, key-detection, functional, and
    visual checks pass with no ambiguity.
  - **8-9/10**: Core behavior works, one or two non-critical items need cleanup.
  - **6-7/10**: Basic install exists, missing a meaningful validation or
    behavior.
  - **0-5/10**: Missing prerequisites, broken verification, wrong secrets
    handling, or failed functional tests.
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

After install, score yourself honestly against this rubric. **Pass gate: 8.5/10
minimum.** Below 8.5 = loop back and fix until passing (max 5 loops, then
escalate to owner).

| Section | Points | What it tests |
|---|---|---|
| Prerequisites acknowledged | 1.0 | TYP (01) + BYUP (02) installed; PREREQS.json satisfied. |
| All skill .md files read before any execution | 1.0 | SKILL.md, INSTALL.md, INSTRUCTIONS.md, CORE_UPDATES.md, QC.md, references/* read BEFORE any command. |
| INSTALL.md steps executed in order | 1.5 | No skipping/reordering/improvising. |
| Credential confirmed at canonical path, value never printed | 1.5 | KIE_API_KEY SET; never echoed/catted/logged; checked all three env stores. |
| Functional checks pass | 1.5 | Credit-free connectivity probe + all four validator self-tests PASS + wire.sh idempotent. |
| CORE_UPDATES.md applied surgically | 1.0 | wire.sh only; own markers only; no SOUL/IDENTITY/USER/HEARTBEAT touched. |
| Skill-specific QC items above all checked | 1.5 | Every checkbox in sections 2-6 ticked. |
| Security | 0.5 | No secret leaked into chat/logs/commits/.md files. |
| Owner-facing confirmation message sent | 0.5 | Plain-English "Skill 66 active" summary. |

### Self-audit before declaring done
1. All .md files read before execution: ✓ / ✗
2. INSTALL.md step order followed verbatim: ✓ / ✗
3. QC rubric score: __/10 (≥ 8.5 to pass)
4. All four validator self-tests exit 0: ✓ / ✗
5. wire.sh second run no-change: ✓ / ✗
6. No shortcuts taken: ✓ / ✗
7. Owner confirmation message sent: ✓ / ✗

If any answer is ✗, this skill is NOT done. Loop back.
