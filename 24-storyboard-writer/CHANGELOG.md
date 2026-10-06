# Changelog - 24 Storyboard Writer (24-storyboard-writer)

## [7.0.1] - 2026-10-05 - Fix: remove Sora default; model choice defers to Skill 67; model database relabeled as a dated snapshot

### Fixed
- SKILL.md defaulted TikTok/Reels to `veo-3-1` and YouTube to `sora-25s`, contradicting the Video department's Sora prohibition (`ai-video-generator-specialist.md`). The Sora default is removed. With no user-named model, the agent now runs Skill 67's selector (`67-kie-video/scripts/select_video_model.py`). Sora is never a default or an option.
- `scripts/model-database.json` (verified 2024-01-15) was labeled "Canonical". It is now a dated, non-authoritative snapshot (SKILL.md, INSTRUCTIONS.md, QC.md, `model_database.py`, and a `_status` field in the JSON). The live catalog and `pricingDesc` come from Skill 74; policy comes from Skill 67. The JSON price numbers stay only as marked fallback constants because `model_database.py` reads them for the cost estimate (authority: `kie_live_adapter.py price --model <id>`). No data was deleted; the Sora entry carries a `policy_note`.
- Examples, QC checks and knowledge questions no longer use or teach Sora (`kling-3` replaces `sora-25s` in the cost check; Q3, Q4, Q7, Q8 rewritten).
- `create_storyboard.py` REFUSES a `sora*` model id (exit 2, `AF-STORYBOARD-PROHIBITED-MODEL`, cites the Video department Sora prohibition, writes nothing); test added. Its `--model` help no longer suggests Sora. SKILL.md step 5 no longer recommends a model from the platform.

### Migration Notes
- CORE_UPDATES.md TOOLS.md text changed ("Veo, Sora, etc." became "Veo, Kling, Seedance, etc.; model choice is owned by Skill 67"). Existing users should re-run core updates. Risk: LOW.

## [7.0.0] - 2026-09-03 - v23 major generation bump: no behavior change, version roll only

No functional changes. Version advanced to the next major generation alongside the v23.0.0 repo release.
