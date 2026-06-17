## [v12.21.0] — 2026-06-17 — feat(standards): Ollama provider platform-branch (Mac local daemon vs VPS cloud-direct), enforced

Encodes the CLIENT ONBOARDING STANDARD for the `ollama` model provider, branched by box type, and corrects the pre-existing VPS-only assumption that wrongly treated `127.0.0.1:11434` as a hard violation everywhere.

- **Mac client:** signed-in LOCAL Ollama daemon (`ollama signin`, client's own ollama.com account) + ONE `ollama` provider `baseUrl: http://127.0.0.1:11434`, `api: ollama`, `apiKey: ollama-local`. A signed-in daemon serves BOTH local AND `:cloud` models through that one endpoint (the docs.openclaw.ai/providers/ollama "Cloud + Local" hybrid flow). Loopback baseUrl is REQUIRED on Mac.
- **VPS client:** ONE `ollama` provider cloud-direct — `baseUrl: https://ollama.com` + client's own `OLLAMA_API_KEY`. Loopback baseUrl → `ECONNREFUSED` (HARD VIOLATION; no daemon in container).
- **All boxes:** every `:cloud` model `maxTokens ≤ 64000` (Ollama Cloud caps output at 65536). Verify a live PONG, not just config-valid.
- **New enforcer** `scripts/qc-assert-ollama-provider-platform.sh` (single source of truth; P1 baseUrl/platform, P2 api, P3 apiKey/platform, P4 :cloud maxTokens) wired into `scripts/qc-system-integrity.sh` as hard-fail **CHECK X.9** (runs during install + every update).
- **New SOP** `docs/OLLAMA-PROVIDER-BY-PLATFORM.md`. Updated `AGENTS.md` N30 (now platform-branched), `platform/README.md` (Ollama + STT rows), `FLEET-STANDARDS.md` §5.
- **Operator note:** existing Mac clients onboarded under the old rule (currently cloud-direct on `ollama.com`, no local daemon) will FAIL X.9 with an explicit migration message. They keep working until migrated; do NOT auto-migrate a live client.

## v12.20.1 — Presentations renderer enforces the process to the letter
- build_deck: HARD PROMPT_CHAR_FLOOR=1500 (under 1,500 = fail, not run); renders the Slide Image Creator's RICH prompt verbatim (fail-loud if missing/short); thin self-composed prompt removed; parallel render.
- 9-check PROCESS PREFLIGHT enforces every SOP phase incl. rich-prompt + coverage; QC loops back / forces redo on any deviation.
- Audience modes STANDARD/PERSONAL/GENERAL + target_talk_minutes + speech-length gate (AF-SPEECH-SHORT).
- PIPELINE-MANIFEST v3 + sync_check lockstep green; no existing SOP weakened.

## [v12.20.0] — 2026-06-16 — feat(presentations): universal scrub + anti-compression hard gate + deterministic build pipeline + SOP↔Python lockstep

Merges the presentations-sop-overhaul (universality + anti-compression) branch with the PR #271 deep-research role-library sync. Highlights:

- **Presentations department made UNIVERSAL — zero client names.** Every concrete name, niche, price, hook line, logo wordmark, deck title, and number across the Presentations role library and the master `universal-sops/CLIENT-WEBINAR-DECK-SOP.md` is now an ILLUSTRATIVE EXAMPLE / DISCOVERY VARIABLE the agent substitutes from the live client interview. Nothing client-specific is hardcoded; the examples teach the SHAPE, the discovery variables supply the content. Enforced by a repo-wide client-name scan (0 hits).
- **Anti-compression HARD GATE (AF-COVERAGE-1 + `_chk_coverage`).** The density-floor overhaul RETIRES the old "hook sung at least 7 times" FLOOR (which produced the reference failure case's 40-slide footer-stamping) and REPLACES it with a CEILING: the canonical hook appears VERBATIM on EXACTLY 3 to 4 dedicated pure-typography slides at named beats and NOWHERE else; footer-stamping is banned; more than 4 hook slides, or zero, is an auto-fail. Paired with the AF-DEN density triggers (>= 8-slide gap between price beats, anchor at one-third never the back third, BUILDUP before every DROP, itemized value-stack before Drop 1, promises before anchor, Wall of Wins 4-6 before offer, 4-7-slide re-pitch after FINAL, section floors). Coverage is enforced, compression is auto-failed.
- **Deterministic build pipeline shipped.** `build_deck.py` (the single-command, zero-AI-judgement-at-runtime renderer — the agent writes only `slides.json` per `slides.schema.json`; the script composes each KIE.ai prompt mechanically, submits, polls, verifies, and assembles the .pptx), plus `kie_generate.py` (reference image-to-image/text-to-image submit+poll+download helper) and `test_preflight.py`. The building agent has NO image tool; KIE.ai is the ONLY render call; self-generate / native image tool / inline HTTP / placeholder substitution are all auto-fails. The mandatory English/Latin-only spelling-lock pin is appended verbatim to every prompt.
- **Process manifest (SOP-SLIDE-05-PROCESS-MANIFEST.md).** Documents the one mandated end-to-end flow with no substitutions.
- **SOP ↔ Python lockstep detector.** `universal-sops/presentation-slide-craft/PIPELINE-MANIFEST.json` declares the canonical contract; `sync_check.py` fails the build if the SOPs and the shipped scripts drift apart; `SOP-SLIDE-06-EXTENSION-AND-SYNC.md` documents the extension + sync discipline.
- **Hook CEILING and renderer reconciliation** carried through every consuming role (Director, Hook Strategist, Slide Copywriter, Slide Image Creator, Typography Architect, QC Specialist, Offer Price Strategist, Brand Steward, PPTX Assembly, Brainstorming Buddy, and their SOP mirrors).
- **Deep Research Specialist (PR #271) merged, not lost.** The twelve-category framework (A-L: niche structures, pricing & value benchmarking, supporting statistics, external corroboration, grounded image context, design+hook+pacing, attributable quotes, the fact-validation ledger, objection research, social-proof patterns, persuasion-framework validation, compliance flags) plus AF-RESEARCH-GATE is kept AND the `persuasion_intelligence` seeding from the Content-to-Presentation Architect is preserved.
- **`_index.json` reconciled** to the union: presentations department 25 roles (adds `fish-audio-expression-specialist`), `total_roles` 425, `total_departments` 34, valid JSON, no duplicate slugs.

## [v12.19.1] — 2026-06-16 — fix(presentations): sync Deep Research Specialist ROLE file Section 9 to its SOP mirror

The ROLE file (ROLE-04 presentations) Section 9 was behind its SOP mirror after v12.19.0. Regenerated to match: SOP 9.4 (Deep Validation & Persuasion Research) with Categories G (attributable quotes), H (fact-validation ledger), I (objection research), J (social-proof patterns), K (persuasion-framework validation), L (compliance flags); SOP 9.1 brief template extended with the G-L header counts; SOP 9.3 hook/pacing (F5/F6) + Hook Strategist hand-off. Source role file and mirror now agree.

