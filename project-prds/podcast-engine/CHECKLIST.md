# PODCAST PRODUCTION ENGINE, MASTER CHECKLIST
### Part A: per-episode runtime checklist (from the companion document, binding at runtime)
### Part B: episode QC protocol gate (Tier 1 plus rubric, binding at runtime)
### Part C: build acceptance criteria (binding on the /goal build, every item failable)

Rules: zero em dashes anywhere; no triple backtick fences in any produced JSON, HTML, or script output; every box checked honestly or not at all. Misreporting any check is an absolute failure.

---

## PART A: PER-EPISODE CHECKLIST (reproduced in every delivery report)

INTAKE AND SETUP
- [ ] First-run smoke test passed (custom field map fields exist; client's own private integration token and Location ID, Podbean, Fish Audio, Kie.ai credentials present). Once per client.
- [ ] All required input fields present (mode, style, show name and host for Interview mode, guest name, preferred pronoun, SMIQ transparency answer, Q1 through final answer). Missing fields raised to the OPERATOR, never guessed.
- [ ] Preferred pronoun captured and governing every reference to the speaker or guest.
- [ ] Production Mode identified: Personal Podcast Style or Interview Style Podcast. Output-type preset resolved.
- [ ] Presentation Style identified: Counter Intuitive, Vulnerable, Provocative, or Passionate.
- [ ] Matching Style Engine and Mode rules loaded.
- [ ] Job key computed; intake ledger claimed; duplicate deliveries acknowledged without a second run.

RESEARCH ASSISTANT STAGE
- [ ] Web research tool identified (Perplexity if available, otherwise the best available tool). Tool named in the delivery report.
- [ ] Every respondent answer improved and expanded without losing detail or changing intent.
- [ ] Three power statements extracted from the respondent's ideas, in their voice.
- [ ] Missing pieces generated: three key takeaways, supporting findings, closing question or call to action.
- [ ] Up to three case studies researched, each real and verified, demographic-matched where applicable.
- [ ] No fabricated study, statistic, person, company, or outcome anywhere in the package.
- [ ] Research call count within the 12-call cap; package frozen into the episode record.

BLUEPRINT AND SIZING
- [ ] Episode title created: compelling, edgy, never preceded by the word Title; immutable from here on.
- [ ] Thesis in one sentence, traceable to Q1 (and Q2 for Provocative).
- [ ] Style signature line written verbatim (reversal, definition drop, refrain, or crescendo command).
- [ ] Every arc beat assigned content and a word budget summing to the chosen total.
- [ ] Transparency beat placed per the Style Engine; case studies and power statements placed.
- [ ] Opening line and final line written first.
- [ ] Runtime chosen inside 7 to 15 minutes, defaulting to the 10-minute sweet spot; word target set at 140 words per minute.

DRAFT AND IMPROVEMENT
- [ ] Full draft in Final Draft format: prose only, everything speakable.
- [ ] Fish Audio tags embedded in correct syntax (S2.1 Pro square brackets by default, S1 parentheses only if the account is specified S1) at all mandatory locations.
- [ ] Improvement Pass completed: more compelling, more disruptive, more emotionally captivating, tone enforced.
- [ ] Improvement Pass did NOT change the title or thesis, remove the transparency beat, add fabricated material, or inflate length.
- [ ] Read-aloud pass completed; nothing a mouth would stumble on remains.

QUALITY CONTROL
- [ ] All 16 Tier 1 hard-fail checks passed (Part B).
- [ ] All 10 rubric dimensions scored 8 or higher, no averaging.
- [ ] Spoken word count verified honestly, tags excluded, inside the target range.
- [ ] Attempt count recorded; three-strike cap honored if reached (stop, founder notified with failing checks and best draft).

IMAGE
- [ ] Cover art generated via Kie.ai GPT-image-2 at 1K square from the visual description plus episode theme, within polling bounds.
- [ ] Squared and compressed in-house with ffmpeg: JPEG, RGB, within 1400 to 3000, under 512 kilobytes, spec-valid filename. Never below 1400 square.

AUDIO
- [ ] Speech Script converted via Fish Audio model s2.1-pro with the client's own voice reference_id; free tier never used.
- [ ] Split at natural boundaries and ffmpeg-joined if needed; condition_on_previous_chunks true; no seams; loudness mastered to the department doctrine; ffprobe-verified.
- [ ] MP3 named client name first, then episode title; valid characters only.

DOCUMENTS
- [ ] Document tooling detected (Google, Notion, or plain text) before creation.
- [ ] Episode Package created rich and fully rendered, no font below 12 point.
- [ ] Speech Script created as clean text only.
- [ ] Google sharing set to anyone-with-the-link-can-edit where Google is the destination.

BOOK TEASER (Interview mode only; skipped entirely for Personal mode)
- [ ] Teaser written (at most three pages) from answers, improved answers, and verified research, in the person's voice, ending on a cliffhanger, on Kimi 2.6 or GLM 5.2.
- [ ] Rendered as a book-typeset PDF, no font below 14 point, uploaded to Convert and Flow media storage, URL captured.
- [ ] Link written to the book_teaser field, or the founder reminder surfaced if the field is absent (never silently created, never fails the episode).

MEDIA, PUBLISHING, LINK-BACK, ENROLLMENT
- [ ] MP3 and cover uploaded to the client's Convert and Flow media library folders; URLs captured and HEAD-verified publicly reachable.
- [ ] Episode published to the client's OWN Podbean channel; permalink captured; scheduled when a future release date exists.
- [ ] Title, description, Episode Package link, Speech Script link written first in one batch; contact.podcast_survey_episode_url written ALONE and LAST; every write read back byte-for-byte.
- [ ] Interview mode: enrollment into both workflows verified per the discovered trigger mechanism, after publish and field writes only, double-enrollment guarded. Personal mode: running spreadsheet updated, no workflows, no messages.
- [ ] Engine STOPPED at the boundary: zero SMS, zero email, zero customer messages from the agent.

DELIVERY
- [ ] Deliverable contains the pure script, document links, media URLs, and the Podbean episode link.
- [ ] Delivery report prepared separately (title, honest word count, runtime, style, mode, writing model and any substitution, research tool, destinations and links, save confirmations, enrollment confirmation, image prompt, this checklist completed, rubric scores) to the operator channel only.
- [ ] Ledger and database state complete; costs recorded; dashboard reflects the finished episode.

---

## PART B: EPISODE QC GATE (all 16 must pass, then rubric, then closing gate)

TIER 1 HARD-FAIL CHECKS (deterministic where possible, via qc-tier1-mechanical.py)
1. EM DASH: zero em dash characters anywhere in the deliverable.
2. NO TRIPLE BACKTICKS or code-fence markers of any kind.
3. NO MARKDOWN in the script: no asterisks, headers, bullets, numbered lists, bold or italic markers.
4. NO LABELS: no Title:, Intro:, HOST:, speaker prefixes, Music or SFX placeholders, or plain-text stage directions.
5. TITLE PLACEMENT: the word Title never precedes the title; a spoken title is woven into natural speech.
6. SPEAKABLE CHARACTERS ONLY: numbers, symbols, abbreviations, units written as spoken.
7. TAG SYNTAX INTEGRITY: correct syntax for the target model, no orphaned or malformed brackets.
8. TAG COUNT EXCLUSION: word and character counts recomputed with tags stripped, inside target.
9. WORD COUNT HONESTY: the true spoken count is reported; misreporting is an absolute failure.
10. FORBIDDEN NAMES: none of the four reference speakers, their books, or talks appear anywhere.
11. FORBIDDEN WORD BY STYLE: the word paradox never appears in a Counter Intuitive episode.
12. NO FABRICATION: every case study, statistic, institution, and claim real and verified; no invented biography.
13. MODE PERSPECTIVE: Personal is first person throughout; Interview keeps host first person and guest third person by name with the epic guest introduction present; no slippage.
14. PRONOUN CORRECTNESS: every pronoun and honorific matches contact.my_preferred_pronoun; nothing guessed or defaulted.
15. PURE DELIVERABLE: the script contains the episode and nothing else.
16. NO INTAKE CONTAMINATION: contact details, consent language, and the image description never appear in the script.

TIER 2 RUBRIC (each dimension 8 or higher, no averaging): 1 Authorial Voice Fidelity, 2 Arc Execution, 3 Persuasion Mechanics, 4 Opening Power, 5 Closing Power, 6 Captivation Throughout, 7 Fidelity to the Respondent, 8 Research Integration Quality, 9 Delivery Craft, 10 Audio Direction Quality.

CLOSING GATE: deliverable only when all 16 Tier 1 checks pass AND all 10 dimensions score 8 or higher AND Part A is honestly complete. Genuine input limitations are noted plainly, never faked into a pass. FAILURE LOOP CAP: hard stop at three failed attempts; notify the founder with the failing checks and the best draft; never relax the standards.

---

## PART C: BUILD ACCEPTANCE CRITERIA (every item independently failable; the build is not done until all pass)

1. [ ] Skill directory exists in the onboarding repo with the complete runbook, prompts, config, and scripts; installs cleanly via the standard updater path.
2. [ ] Webhook layer: route template, deterministic mapper with fixture unit tests (Convert and Flow, Make.com, n8n samples), job-key module with collision and divergence tests, ledger with exclusive-create claim, T1 to T9 verification script EXECUTED and observed passing on the operator box, including T9 through the real public URL.
3. [ ] Idempotency proven: identical redelivery produces one episode record and a duplicate acknowledgment; a one-answer change produces a new job.
4. [ ] Convert and Flow layer: credential resolver with CONVERTFLOW aliases landed in the SHARED resolver; ghl_credential_gate.py passing full mode on the operator box; field map verified including the double underscore key; write ordering (URL last and alone) and read-back verification implemented and tested; media upload with HEAD verification; Skill 44 discovery-then-verify-then-enroll with the Personal-mode hard refusal.
5. [ ] MCP-free pipeline proven: a static check confirms no MCP tier is invoked anywhere in the per-episode path.
6. [ ] All four Style Engines and both Modes implemented per the companion document, with the four output-type presets selectable; golden fixture episode passes the full episode QC gate.
7. [ ] Fish render module: s2.1-pro via header verified LIVE, reference_id parameterized, free tier structurally refused, split-and-join with ffprobe verification, loudness mastering applied.
8. [ ] All furnace guardrails shipped and passing: cost ledger with ceilings, state writer with transition matrix, smoke test at or under 1 cent with pinned balance endpoints, alert dedup, qc-attempt-gate with frozen research and targeted retries, guard-cron-inventory (exactly one cron, no heartbeat), runtime routing config with deny patterns.
9. [ ] guard-no-anthropic-runtime.py passes over every shipped runtime file including the dashboard; zero Anthropic model ids, providers, packages, keys, or hosts.
10. [ ] Dashboard: all fourteen acceptance criteria in design/dashboard-design.md Section 15 verified, including read-only enforcement, serializer field matrix, token revocation round trip, the three-blade kill switch, brand-variable flow-through, and responsive checks at 375, 768, and 1280 pixels.
11. [ ] Cloudflare provision and revocation scripts implemented against LIVE-verified endpoints; provision gate (302 to Access, signed hook test, smoke-test cron fired once) and revocation verification (edge dark, hook dead, box clean, gateway healthy) both proven on the operator box.
12. [ ] Department wiring: the EXISTING podcast department carries the skill; no duplicate department; department-floor.py passes; persona matching binds to the Skill 23 podcast and audio roles; a test job appears on the kanban and moves through the state vocabulary.
13. [ ] SOP set: the six new standard operating procedures added and the seven updates applied (Section 13 of the PRD), each with its enforcement pointer.
14. [ ] Both QC gates demonstrably distinct: the build gate scored at or above 8.5 on the 10-category fleet rubric for every merged unit; the episode gate exercised on the golden fixture with a forced Tier 1 failure and a forced rubric failure both correctly blocking delivery, and the 3-strike cap correctly stopping and alerting.
15. [ ] Repo mechanics: update.sh skill count corrected; _index.json content_sha restamped for every touched file; version bumped to v18.0.0; ANNOTATED tag created BEFORE the serial merge; merge completed by the single merge-writer; fresh-clone verification passed.
16. [ ] PRD folder present in onboarding master files at project-prds/podcast-engine/ containing PRD, session log, change log, to-do list, checklist, and QC protocol and matrix, in sync with this folder.
17. [ ] Silence and secrecy audit: zero client-facing messages in any code path; every credential check reports SET or NOT SET only; grep of all shipped files and logs finds no secret values; repo grep finds no client names.
18. [ ] Canary complete: one full end-to-end episode (test contact, _test-gated where destructive) proven on the operator box from the MERGED repo; fleet rollout explicitly HELD at repo-only with the hold recorded in the session log.
