# QC Checklist: Agnes Image 2.1 Flash

## 1. Purpose
Enables the agent to call the Agnes Image 2.1 Flash endpoint to generate images
from text (text-to-image) and to transform existing images (image-to-image),
using the EXISTING fleet credential AGNES_AI_API_KEY, with correct size tiers,
aspect ratios, the `response_format`-in-`extra_body` gotcha, and the URL/Base64
output shape. The image endpoint is synchronous — one request returns the image.

## 2. Installation Checks
- [ ] Skill folder exists and contains `SKILL.md`, `INSTRUCTIONS.md`,
      `EXAMPLES.md`, `INSTALL.md`, `CORE_UPDATES.md`, the full reference
      `agnes-image-full.md`, `PREREQS.json`, `qc-agnes-image.sh`, and the
      `agnes-image.skill` package.
- [ ] The full reference documents the correct model name
      (`agnes-image-2.1-flash`) and endpoint
      (`https://apihub.agnes-ai.com/v1/images/generations`).
- [ ] The full reference states the two gotchas: `response_format` in
      `extra_body`, and no `tags` for image-to-image.
- [ ] The output-dimension table is present (for example the `16:9` `2K` size
      `2624x1472`).
- [ ] No real credential value appears anywhere in the skill files.

## 3. Dependency Checks
- [ ] TYP (Skill 01) and BYUP (Skill 02) are installed first.
- [ ] `AGNES_AI_API_KEY` is present (SET) — the same key the existing `agnes` /
      `agnes-2.0-flash` model uses. QC checks presence only, never the value.
- [ ] `curl` is available for the verification call.
- [ ] The installer understands the image endpoint is SYNCHRONOUS (no polling)
      and that the Agnes VIDEO endpoint is a separate, asynchronous service.

## 4. Key Detection
- [ ] Search the standard secret locations in order: `~/.openclaw/secrets/.env`,
      `~/.openclaw/openclaw.json` `env.vars`, `~/clawd/secrets/.env`, and the
      live environment. Primary variable: `AGNES_AI_API_KEY`.
- [ ] QC fails only if the agent reports the key missing WITHOUT checking all
      locations first. A genuinely absent key is a WARN (operator must
      provision), never a fabricated key.

## 5. Functional Checks
- [ ] Confirm `AGNES_AI_API_KEY` loads into the environment (presence only).
- [ ] Make one synchronous text-to-image call (model `agnes-image-2.1-flash`,
      `size` `1K`, `ratio` `1:1`, `extra_body.response_format` `url`) and confirm
      the SAME response carries `data[0].url`.
- [ ] Confirm the agent can explain: 401 = bad/missing key; 429 = per-tier rate
      limit (back off, do not hardcode a cap); response_format belongs in
      extra_body; image-to-image needs no tags.

## 6. QC Score
- Score this skill from **0 to 10** after running the checks above.
  - **10/10**: All installation, dependency, key-detection, and functional checks
    pass with no ambiguity.
  - **8-9/10**: Core behavior works, one or two non-critical items need cleanup.
  - **6-7/10**: Basic install exists, missing a meaningful validation or behavior.
  - **0-5/10**: Missing prerequisites, broken verification, wrong secrets
    handling, or failed functional tests.
- Record final result here:
  - **QC Score:** ____ / 10
  - **Status:** Pass / Needs Fix / Blocked
  - **Notes:** ____________________________________________

## 7. QC Loop Rule
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
| Prerequisites + INSTALL-CONTRACT.md acknowledged | 1.0 | Read + acknowledged this session; prerequisite skills installed. |
| All skill .md files read before any execution | 1.0 | SKILL.md, INSTALL.md, CORE_UPDATES.md, QC.md, agnes-image-full.md read BEFORE any command. |
| INSTALL.md steps executed in order | 1.5 | No skipping/reordering/improvising. |
| Credential confirmed at canonical path, value never printed | 1.5 | AGNES_AI_API_KEY SET; never echoed/catted/logged. |
| Functional checks pass | 1.5 | Synchronous test call returns data[0].url; no unhandled 4xx/5xx. |
| CORE_UPDATES.md applied surgically | 1.0 | Only labeled sections into labeled core files. No SOUL/IDENTITY/USER/HEARTBEAT touched. |
| Skill-specific QC items above all checked | 1.5 | Every checkbox in sections 2-5 ticked. |
| Security | 0.5 | No secret leaked into chat/logs/commits/.md files. |
| Owner-facing confirmation message sent | 0.5 | Plain-English "Skill 63 active" summary. |

### Bundled `qc-agnes-image.sh`
Run it. Exit 0 is required in addition to the rubric score. It catches the
mechanical items (files present, reference doc correctness, credential presence).

### Self-audit before declaring done
1. INSTALL-CONTRACT.md acknowledged: ✓ / ✗
2. All .md files read before execution: ✓ / ✗
3. INSTALL.md step order followed verbatim: ✓ / ✗
4. QC rubric score: __/10 (≥ 8.5 to pass)
5. Bundled qc-agnes-image.sh exited 0: ✓ / ✗
6. No shortcuts taken: ✓ / ✗
7. Owner confirmation message sent: ✓ / ✗

If any answer is ✗, this skill is NOT done. Loop back.
