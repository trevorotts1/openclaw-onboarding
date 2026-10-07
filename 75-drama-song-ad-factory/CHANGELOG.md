# Changelog - drama-song-ad-factory (Skill 75)

All notable changes to this skill are documented here. The version of
record is `skill-version.txt` (kept in agreement with the `SKILL.md`
frontmatter `version:` field).

---

## [v2.4.3] - 2026-10-07 - audio-fix wave D36-D38: no-echo rule, spoken-share band, reverb-tail QC, pitch ban, Sketch-to-Life voice guard

### Added
- `scripts/core/audio_c3/no_echo/` - every Suno request (song and voice-pack) stamps dry close-microphone vocals plus the seven negative tags and refuses spacious / cinematic / choir in spoken parts (D22a).
- `scripts/core/smp/no_echo/` - the same no-echo rule on the Skill 35 weekly drama-song request.
- `scripts/core/qc_reverb_tail/` - QC measures the reverb tail after each spoken line; a ringing line fails QC (D22a).
- `scripts/core/qc_voice_match/pitch_ban/` - pitch ban guard for voice-match QC.
- `scripts/core/spoken_share/` - spoken share retarget: target 45 percent, band 40-55, rap counts as spoken, first sung line within about 10 seconds (D15).
- `scripts/core/spoken_share_card_docs/` - card and docs lines carrying that spoken-share rule.
- `scripts/core/smp/spoken_share/` - the same spoken-share rule on the Skill 35 planner wave (D15).
- `scripts/core/choice_card/stl_voice_guard/` - Sketch to Life is always All Suno; Velvet Voiceover is refused for that look (D25).

## [v2.4.2] - 2026-10-07 - fix: style bible compiler routes its prompt cap through the one KIE enforcer

### Fixed
- `scripts/core/product_style_bible/bible.py` imports `shared-utils/kie_prompt_enforcer.py` and calls `KPE.check(...)` (kind verbatim, ceiling only) on every compiled prompt, as the KIE prompt enforcer guard (rule 12) requires of a declared gate module. The cap values (20000 sunburst, 25000 legacy) and compile behavior are unchanged.

## [v2.4.1] - 2026-10-07 - docs: PACKAGING-DECISION wording

### Fixed
- `PACKAGING-DECISION.md` no longer cites the retired legacy updater path literally (single-update-skills-entrypoint guard, section C). No behavior change.

## [v2.3.0] - 2026-10-07 - docs: directive 2.1 document set landed

### Added
- `INSTRUCTIONS.md` - operating instructions: the mandatory TYP gate, the
  eleven build-directive section 25 runtime steps, the shared
  intake/preflight controls and section 24.3 intake rules, exit-code
  envelope contract, section 17 QC non-negotiables, and the skill's
  never-do list.
- `EXAMPLES.md` - twelve verified examples using only the implemented
  entrypoint (`scripts/core/intake_preflight/factory.py`) and the repo's
  shipped `check-skill-prereqs.sh` / `qc-prereqs-json.sh`; every shown
  outcome was executed and captured (intake ok/waiting/rejected, resume
  ok/parked, preflight pass/tool-unavailable/credential-missing/
  approval-missing/approval-expired/reference-outside, checker rc 0/2/3,
  lint PASS on 24 PREREQS.json files).
- `QC.md` - install-time rubric (10 points, gate 8.5), file/version and
  credential checks, control-layer smoke, 9-question knowledge check,
  and the campaign QC gate checklist mapped to build-directive sections
  17.1-17.9 with anti-patterns.
- `INSTALL.md` - first install (`install.sh` one-liner / checkout),
  update (`update-skills.sh`), canonical credential paths, helper-skill
  install law (section 2.4), verification steps, run-storage root,
  version bookkeeping and rollback via installer backups.
- `CORE_UPDATES.md` - surgical allowlist (AGENTS.md / TOOLS.md /
  MEMORY.md) with exact text blocks; core persona files never touched.
- `PREREQS.json` - executable prerequisite mirror per INSTALL-CONTRACT
  Rule 16: skills 01/02/07/24/25/27/30/46/66/67/68/74 (folder form),
  KIE_API_KEY (required), FISH_AUDIO_API_KEY (optional), python3 and
  ffmpeg binaries, faster-whisper advisory note; every required `satisfy`
  names the action, canonical secrets path and config command.

### Changed
- `DEPENDENCY-MANIFEST.md` - helper dependency table now carries version
  + git tree hash per helper pinned at source commit
  `cc2e595f1de87c1411dfb44e9542f0017f3b5acc` (2026-10-07), cross-linked
  to `PREREQS.json` as the executable mirror. Scaffold notes for
  release-time pins (W5-02) are preserved.

---

## [v2.3.0] - 2026-10-06 - feat: OpenClaw distribution (W3-02)

- Initial Skill 75 folder: `SKILL.md` (route boundaries, control
  entrypoint contract, section 24.3 intake rules, paid-generation
  boundaries, department wiring), `scripts/core/` shared canonical core
  (state_store, artifact_graph, spend_ledger, job_recovery, contracts,
  acceptance-profile, intake_preflight, qc_gate, timing_guard),
  `DEPENDENCY-MANIFEST.md`, `THIRD_PARTY_NOTICES.md`,
  `skill-version.txt` = v2.3.0. Exit-table correction and CI guard
  repairs followed the same day (commits `2dd07e409`..`37a6926c8`).

---

Format follows `46-kie-callback-relay/CHANGELOG.md`: newest first,
`## [version] - date - type: summary`, sections `### Added` /
`### Changed` / `### Fixed` / `### Tests`.
