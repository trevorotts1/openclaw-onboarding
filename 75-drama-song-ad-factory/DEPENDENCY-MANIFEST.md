# Dependency manifest — drama-song-ad-factory

Scaffold (W1-07). Exact pins and hashes are completed at release time (W5-02)
after W1-06 reconciles Skill 68 and after clean-install verification in both
distributions per directive 2.4. Rule: clean installs receive the actual
provider/helper dependencies they invoke; references to onboarding Skills
66/67/68/74 do not install them. Preflight fails with an actionable error
if a required helper is absent.

Source of helper identities: directive section 5.1.
Source of bundled registry gap: `CONTROL/bundled-skills.txt` in 999-setup
(audited snapshot: 8 skills, no `motion-video-plus`, no `drama-song-ad-factory`).
Source of CLI shape: directive 24.1 (`scripts/factory.py`, `release_check.py`).
Source of faster-whisper fallback: directive 12.4 (provider-native lyric
timing first, faster-whisper/Whisper-based alignment second).

Source of the ONE transcription step (F17, owner order 2026-10-08, Critical):
`scripts/core/audio_c3/lyric_timing.py` — every consumer needing words/word
timing (lyric check, captions, lip-sync line windows, talk/sing split) calls
`provide_word_timings()` there; tier order is 1) Suno's own timestamped
lyrics via KIE `ai-music-api/timeStamped-lyrics` through `core/kie_dispatch`
(alignedWords startS/endS; default, no local model), 2) fallback
faster-whisper LOCAL — ONE model loaded at a time, tracks one after another
in that single process, smallest model that passes (small/medium int8); NEVER
openai-whisper, 3) third fallback cloud speech-to-text with word timestamps,
the CLIENT's own key only (never operator keys). The Part D load guard
(`memory_guard`, lane_size/capacity-monitor numbers) runs before any local
model load and refuses with LOCAL_MODEL_LOAD_REFUSED. Builders may never
write their own whisper/asr scripts: `scripts/qc-no-local-asr.sh` (the F14
lock, extended) fails a hand-written whisper/asr/transcription script in a
run folder or core non-test file.

Canonical-core default architecture: onboarding-owned canonical core with
thin OpenClaw and 999 runtime adapters (directive 2.4). Exact source path
and release mechanism recorded in `ARCHITECTURE-DECISIONS.md` before coding.

## 1. Canonical source

| Item | Value (scaffold) |
|---|---|
| Canonical core home | onboarding repo, path TBD in `ARCHITECTURE-DECISIONS.md` |
| OpenClaw adapter | `NN-drama-song-ad-factory/` (next free slot after fresh numbering audit; 75 at 2026-10-06 snapshot) |
| 999 adapter | `.claude/skills/drama-song-ad-factory/` with `adapters/claude-nine/` + `adapters/claude-code/` |
| CLI entrypoint | `scripts/factory.py` (one entrypoint, subcommands backed by shared modules; no parallel OpenClaw/999 implementations) |
| Release verifier | `release_check.py` (manifest comparison, clean helper install proof, supported versions, migration/rollback, test receipts) |

## 2. Helper dependencies (onboarding skills, resolved by source — not by reference)

Pinned at source commit `cc2e595f1de87c1411dfb44e9542f0017f3b5acc`
(2026-10-07). Version = the helper's `skill-version.txt`; hash = its git
tree object at that commit (`git rev-parse <commit>:<folder>`). Re-pin
at every release (W5-02) and record the new commit here. This table is
the human view; `PREREQS.json` in this folder is the executable mirror
that fails preflight with an actionable error when a required helper is
absent (INSTALL-CONTRACT Rule 16, build-directive section 2.4).

| Helper | Version | Tree hash | Role | Install mechanism (TBD at release) |
|---|---|---|---|---|
| Skill 66 (`66-kie-image`) | v2.2.1 | `6f8cde39aba0edfdf6091b8104f857eebaf358da` | KIE image model selection, prompt constraints, domain QC | versioned package or generated bundle — NOT a bare reference |
| Skill 67 (`67-kie-video`) | v2.1.2 | `343b1dd1d1326c31de571317f4c2ed891bab4194` | KIE video routing (no hardcoded Seedance/Kling/Veo/Wan) | versioned package or generated bundle — NOT a bare reference |
| Skill 68 (`68-kie-audio`) | v2.3.0 | `cf5b5759d6a7f4b3be42af086ce8ea330777cfd4` | Suno audio after W1-06 contract repair (createTask envelope) | versioned package or generated bundle — NOT a bare reference |
| Skill 74 (`74-kie-live-adapter`) | v1.1.2 | `a8cb84590e6b1d487002ae7d4b6ac812eb46a6b6` | Paid transport: discovery, schemas, upload, submit, poll, credits (shadow-first) | versioned package or generated bundle — NOT a bare reference |
| Skill 07 (`07-kie-setup`) | v7.1.1 | `0c7396a55b2d1f888a6a2f93f79e8a33c66722c9` | KIE account setup / credential context | existing install path (`install.sh` / `update-skills.sh`) |
| Skill 46 (`46-kie-callback-relay`) | v2.1.0 | `d547170894c605e26912901a7c922ac7d149606c` | Async KIE callback relay | existing install path |
| Skill 30 (`30-fish-audio-api-reference`) | v7.0.0 | `c4b12d28ff1513e252280436aa63aa35657217a5` | Fish Audio spoken voice (preferred; no new ElevenLabs dependency) — optional path | existing install path |
| Skill 24 (`24-storyboard-writer`) | v7.0.1 | `bf3bf41f4c191ca3790421eccbfa4de6b21a88ca` | Canonical storyboard/shot-planning reuse (directive 25 step 3) | existing install path |
| Skill 25 (`25-video-creator`) | v7.1.2 | `642651ff9b6aed77ba668e9d63b181c943646789` | FFmpeg-based video work | existing install path |
| Skill 27 (`27-video-editor`) | v7.0.1 | `60bc98dbc7e659b7c62c332551d6bc2c9686b9c5` | FFmpeg-based ordinary editing | existing install path |
| Skill 01 (`01-teach-yourself-protocol`) | v7.0.1 | `d2ba78baf2615246d70910626bdab39a5c41116b` | Teach Yourself prerequisite (directive 25 step 1) | existing install path |
| Skill 02 (`02-back-yourself-up-protocol`) | v7.1.0 | `433c9bdee530a0459cc945c2860fd6876d5588d3` | Backup prerequisite (repo law) | existing install path |

## 3. Package / binary dependencies

| Package | Role | Pin status (scaffold) |
|---|---|---|
| `faster-whisper` | Local lyric-alignment fallback when provider-native timestamps are insufficient (directive 12.4; F17 owner order 2026-10-08: installed ONLY when the tier-2 fallback is enabled — `PREREQS.json` `faster-whisper-optional` carries the same condition). Tier 2 loads ONE model at a time in `scripts/core/audio_c3/lyric_timing.py` (ONE process per run, tracks transcribed one after another, small/medium int8); the Part D load guard refuses a load past the machine's limit. NEVER openai-whisper (qc-no-local-asr.sh). Approved lyrics stay source of truth; ASR gives timing/mismatch evidence only | NOT INSTALLED on this box (verified 2026-10-06: `import faster_whisper` → `ModuleNotFoundError`; no `pip` on PATH; Python 3.14.7). Pin + hash + Python/tool versions at release after verification on both clean installs |
| `ffmpeg` | Frame stitch, scene join, voiceover mux, -14 LUFS finish | PRESENT on this box (verified 2026-10-06: `/opt/homebrew/bin/ffmpeg`, version 8.1.1). Pin minimum version + verify on both clean installs at release |
| Python stdlib | State, hashing, paths, CLI parsing, cost arithmetic (directive 24.4) | preferred; no pin needed |

## 4. 999 bundled-skills registry

`CONTROL/bundled-skills.txt` (audited snapshot, 8 entries):
`nine-router-setup`, `spec-protocol`, `kaizen`, `eli5`, `bro`,
`blackceo-signature-page`, `hook-skill`, `kiss`.

Gaps (verified 2026-10-06):

- `motion-video-plus` source EXISTS at
  `.claude/skills/motion-video-plus/` (with `adapters/claude-nine`,
  `adapters/claude-code`, `adapters/codex`, `VERSION` = `1.0.2`) but is
  ABSENT from `bundled-skills.txt` — source presence is not proof of
  automatic installation (directive 2.4).
- `drama-song-ad-factory` is absent (expected — not yet built).

W3-03 inspects and updates the installer/bundled-skill registries, including
`CONTROL/bundled-skills.txt` if it remains the canonical mechanism.

## 5. Standard library first

Control layer prefers stdlib (`sqlite3`, `hashlib`, `pathlib`, `argparse`,
`json`). Any non-stdlib schema/media/alignment dependency is pinned here
with its hash and verified on both clean installs. Skill 74's stdlib design
proves nothing about new helpers.

## 6. Schema / contract versions consumed

| Contract | Version (scaffold) |
|---|---|
| `core/contracts/campaign-schema.json` (`schema_version`) | `1.0.0` |
| `core/contracts/artifact-schema.json` (`schema_version`) | `1.0.0` |
| `core/contracts/qc-schema.json` (`schema_version`) | `1.0.0` |
| `core/acceptance-profile.json` (`profile_version`) | `1.0.0` |

Bump rule: any contract change re-qualifies consumers via parity/lockstep
tests (directive 2.3) and records migration + rollback in the release
manifest (schema: `release-manifest.schema.json`).
