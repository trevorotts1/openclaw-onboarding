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

| Helper | Role | Install mechanism (TBD at release) |
|---|---|---|
| Skill 66 (`66-kie-image`) | KIE image model selection, prompt constraints, domain QC | versioned package or generated bundle — NOT a bare reference |
| Skill 67 (`67-kie-video`) | KIE video routing (no hardcoded Seedance/Kling/Veo/Wan) | versioned package or generated bundle — NOT a bare reference |
| Skill 68 (`68-kie-audio`) | Suno audio after W1-06 contract repair (createTask envelope) | versioned package or generated bundle — NOT a bare reference |
| Skill 74 (`74-kie-live-adapter`) | Paid transport: discovery, schemas, upload, submit, poll, credits (shadow-first) | versioned package or generated bundle — NOT a bare reference |
| Skill 07 | Account setup | existing install path |
| Skill 46 | Callback relay | existing install path |
| Skill 30 | Fish Audio spoken voice (preferred; no new ElevenLabs dependency) | existing install path |
| Skill 25 / 27 | FFmpeg and ordinary local editing | existing install path |

## 3. Package / binary dependencies

| Package | Role | Pin status (scaffold) |
|---|---|---|
| `faster-whisper` | Local lyric-alignment fallback when provider-native timestamps are insufficient (directive 12.4). Approved lyrics stay source of truth; ASR gives timing/mismatch evidence only | NOT INSTALLED on this box (verified 2026-10-06: `import faster_whisper` → `ModuleNotFoundError`; no `pip` on PATH; Python 3.14.7). Pin + hash + Python/tool versions at release after verification on both clean installs |
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
