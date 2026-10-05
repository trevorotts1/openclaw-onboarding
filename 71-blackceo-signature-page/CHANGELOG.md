# CHANGELOG

## 1.1.0 - 2026-10-05

Enforcement fixes after the failed 2026-10-01 page test (order:
BLACKCEO-SKILL-71-ENFORCEMENT-FIX-ORDER.md). Every item ID from that order is
listed in the entry.

- **A1.4-6** Brand is now a machine-readable file every stage loads: `assets/brand/blackceo-brand.json`, `assets/brand/brand.schema.json`, `assets/brand/client-brand.template.json`, `references/BlackCEO-Page-Brand-Law.md`; SKILL.md "Read only what the current stage needs" opens with the brand bullet; SOP Stage 3 and Stage 6 read fonts/palette from the brand file exactly; `authority-map.md` names the brand file and Page Brand Law the top authority for page colors, fonts, logo, and founder imagery.
- **A2.1-2** No direction at intake means `SECRET_SAUCE_ONLY` — never agent-delegated style choice; SKILL.md states it and the v5 image guide's selection step 4 requires explicit owner delegation (`creative_direction: "delegated"`); `scripts/validate_visual_direction.py` enforces it with color/font/placeholder checks.
- **A3** Signature Grade Block restored as a constant: `assets/brand/signature-grade-block.txt` (byte-for-byte from the archived IMPROVED-FRAMEWORK-v2 section 2.4); required verbatim in every `SECRET_SAUCE_ONLY` prompt via `validate_prompt.py --sauce-only`; image guide section 8 states it.
- **A4** `assets/page-references/README.md` lists the three REQUIRED page-layout reference files; `authority-map.md` marks `BlackCEO-Master-Visual-Reference-Guide.png` an image-style menu only, never a page-layout/page-color reference.
- **B1** A mockup is a real rendered image: SOP Stage 6 and Stage 11 outputs are `mockup.html` plus `part-*.png` renders by `scripts/render_page.py`; Stage 12 adds "the final mockups are the visual target"; `validate_page.py --mode mockup` brand-checks the mock before any image work.
- **B2** `scripts/stage_gate.py` is mandatory: check/close/report; `references/stage-contract.json` owns stage IDs, artifacts, validators, review and score requirements; SKILL.md states the gate cannot be bypassed and `validate_state.py` remains for back-compat.
- **B3** Stage order owned by the gate; SKILL.md: "If a run order lists fewer stages than `references/stage-contract.json`, follow the contract and record the order's omission in the report."
- **C1-C6** (scripts, other lane) `render_page.py`, `compare_sheet.py`, `html-qc-rubric.md`, `validate_page.py`, extended `validate_public_copy.py`, extended `validate_prompt.py`, extended `validate_image_manifest.py`, `validate_image_grade.py`.
- **D1** `references/swarm-plan.md` — one agent per item, per-image fan-out, reviewers start when their item lands; stage contract fan-out deps.
- **D2** Stage-contract `reads` field is the only reading list per stage; SOP:154 narrowed to the image guide's crop/face/hair requirements section.
- **D3** SKILL.md + swarm-plan: agents write receipts; the orchestrator learns results only from `stage_gate.py check/close` output, never chat replies; no recovery lanes.
- **E1** `stage_gate.py report` writes `REPORT.md`; SKILL.md: report to the owner by pasting REPORT.md's overall line, stage table, and cost line — no self-written stage-status summary.
- **E2** "Nothing marked 'pending confirmation' may ship; pending means BLOCKED." in SKILL.md; invented tokens fail `validate_visual_direction.py`.
- **F1** Installed-only 1.0.2 fixes and files ported into this repo copy (CHANGELOG, EVALUATION-CHECKLIST, START-HERE, VERSION, adapters/, agents/openai.yaml, references/runtime-adapters.md, scripts/install_local.py, tests/); SKILL.md merged to one text (installed 1.0.2 fix wording wins, repo OpenClaw seam sections kept); verify.sh now runs `python3 tests/run_tests.py`.
- **F2** Five dead links to the removed `BlackCEO-Signature-Image-Prompt-Creation-Guide-v1.md` re-pointed to `BlackCEO-Signature-Image-Intelligence-and-Prompt-Creation-Guide-v5.md` (SOP x3, Standard v6, Long-Form v6).
- **F3.1** `authority-map.md`: qc-contract thresholds win over style libraries (average >=8.5, each >=8, 3 repair attempts).
- **F3.2** Photographers library section 6 heading: "Not used by Skill 71 — one style per page."
- **F3.3** Image guide: "this v4 master" -> "this v5 master".
- **F3.5** `artifact-contracts.md` stage names now point to `references/stage-contract.json`; stage IDs live in SKILL.md.
- **F3.6** SOP scope note: OpenClaw direct-response/VSL sales-page stacks route to Skill 56; SOP sales-page notes apply only to an explicitly assigned single BlackCEO Signature page.
- **F3.7** SOP:302 links `references/html-qc-rubric.md` for the "every required criterion >=8" rule.
- Version bumped to 1.1.0 everywhere (SKILL.md frontmatter, skill-version.txt, VERSION).


## 1.0.2 - 2026-10-01

Compatibility, safety and documentation fixes found by the Opus review of the landing-page
skill window plus the full page test. No methodology, writing, visual, QC, threshold or
production-order change.

1. `SKILL.md` intake: paid providers (Kie, Agnes, GHL, Vercel) use ONLY the client's own keys from that client's own `secrets.env` — never an operator's or another client's key; if a key is absent, the stage is marked BLOCKED. The same intake list now asks for a per-job image cap (count) — a cap, never an approval gate.
2. Large references note in `SKILL.md`: the style libraries are large — run the copy and image stages in separate sessions or subagents, and grep a style library by Style-ID (`VDL-nnn` photographic, `CIS-nn` cinematic, `ART-nn` visual artist) instead of reading it whole.
3. Adapter READMEs (`adapters/claude-code/README.md`, `adapters/claude-nine/README.md`, `adapters/codex/README.md`): Windows command line using `py scripts/...`, and the Pillow prerequisite noted where the PDF review test is documented.
4. `references/`: five dead links to the removed "Image Prompt Creation Guide v1" (`SOP-v1.md` x3, `Standard-v6.md`, `Long-Form-v6.md`) re-pointed to the v5 image guide; the image guide now states that when the onboarding repository is absent, the rules in that guide apply and nothing is fetched; `SOP-v1.md` GHL test-form step now requires a named test contact the owner approved for testing and never fires a live client automation.
5. Script fixes: `scripts/install_local.py` continues past a Codex-root conflict and creates absent roots instead of returning early on the first one; `scripts/validate_state.py` no longer crashes on a non-object stage; `scripts/validate_image_manifest.py` no longer crashes on an unhashable id and no longer false-fails authoring dialects against map-dialect schema; `scripts/validate_prompt.py` no longer false-fails on the ordinary English word "placeholder" (the bracketed marker and the bare `PLACEHOLDER` token still fail).
6. 999-setup installers: `setup-macos.sh` and `setup-windows.ps1` install Pillow the safe way (`python3 -m pip install --user Pillow` on macOS CLT python, `py -m pip install Pillow` on Windows) and link the bundled skills into `~/.codex/skills` and `~/.agents/skills` when `~/.codex` exists. `--break-system-packages` is never used.

The page-test artifact also carries the wireframe Section 3 overlap fix (the image frame no longer covers the text and CTA in `desktop-part-B.png`).

## 1.0.1 - 2026-10-01

Two compatibility fixes. No methodology, writing, visual, QC, threshold or production-order change.

1. `python` -> `python3` in `adapters/claude-code/README.md`, `adapters/claude-nine/README.md`, `adapters/codex/README.md`, and `references/runtime-adapters.md`. On macOS only `python3` exists; the documented `python` commands fail with exit 127.
2. `scripts/install_local.py` now knows both Codex skills roots. `DEFAULT_ROOTS["codex"]` was `~/.agents/skills` only; it is now `~/.agents/skills` and `~/.codex/skills`, and the installer links into every root listed.

## 1.0.0 - initial

First packaged release of the BlackCEO Signature Page skill.
