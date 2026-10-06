# Changelog - 27 Video Editor (27-video-editor)

## [7.0.1] - 2026-10-05 - Fix: B-roll model choice and KIE rules defer to Skill 67 and the canonical rules file; removed hard-coded prices

### Fixed
- `references/kie-ai-models.md` was titled "Complete guide". It is now a dated, non-authoritative snapshot that defers to Skill 67 (policy), Skill 74 (live catalog, `pricingDesc`) and `07-kie-setup/references/kie-common-rules.md`. The Sora section is marked prohibited (Video department). Its "Model Selection Guide" and "Quick Reference: Cost Examples" tables (Veo ~$0.40/~$2.00, Sora picks) were removed, as were its restated credit conversion and rate-limit lines. All Cost and Resolution columns and numeric limits are gone: one price authority, `kie_live_adapter.py price --model <id>` (Skill 74).
- `BROLL-WORKFLOW.md` Step 9 and "B-ROLL GENERATION WITH KIE.AI": hard-coded model picks and prices (Veo 3.1 Fast ~$0.40, Quality ~$2.00, Sora 2 $0.015/sec) replaced by Skill 67's selector, live pricing from Skill 74, a Rule Zero cost announcement, and the credit preflight in the rules file.
- `BROLL-WORKFLOW.md` KIE error handling: removed the stale `~/clawd/secrets/.env` pointer and the invented status-code advice (429 wait 60 seconds, 500/503 wait 2 minutes); now points to the canonical rules and Skill 67's retry ladder. QC.md anti-pattern 7 updated to match.
- Contradiction fixed: the model reference said the skill never calls KIE and users generate B-roll themselves, while BROLL-WORKFLOW.md said the agent does all the work. Now stated once: the skill ships no KIE client and the agent generates through Skill 67.
- Contradiction fixed: BROLL-WORKFLOW.md said the person is on screen about 25 percent of the time, while its own worked examples show 38 to 47 percent; the 60-second example heading said 60 but totals 64 seconds. QC.md Q6 and Q9 updated.
- `scripts/broll-workflow.sh` prompt text no longer prints Veo prices; it points to Skill 67, Skill 74 and the rules file.

## [7.0.0] - 2026-09-03 - v23 major generation bump: no behavior change, version roll only

No functional changes. Version advanced to the next major generation alongside the v23.0.0 repo release.
