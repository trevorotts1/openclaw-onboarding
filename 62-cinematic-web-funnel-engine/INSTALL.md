# Install / Update Contract — Cinematic and Web Funnel Engine (Skill 62)

## Current state

This skill ships as skill directory `62-cinematic-web-funnel-engine/` inside
`openclaw-onboarding`. It installs the same way every other numbered skill in this
repository installs — as a directory copied/synced by the repository's existing
installer (`install.sh`) and updater (`update-skills.sh`); this skeleton unit does not
add a new install mechanism, a new installer flag, or a new dependency outside what the
repository's Python/Bash baseline already requires.

## Requirements

- `python3` on `PATH` (checked fail-closed by `cinematic-web-funnel-entry.sh`).
- `bash` (the front door itself).
- No third-party Python packages are required by the skeleton (`run_cinematic_web_funnel.py`
  and the entry shell use only the Python/Bash standard library). Later build units that
  add FFmpeg processing, the Next.js template, or provider SDKs will extend this section
  with their own dependency and verification steps.

## What gets installed

```text
62-cinematic-web-funnel-engine/
├── SKILL.md                        (frontmatter: name, description, version)
├── skill-version.txt               (lockstep with SKILL.md frontmatter version)
├── MASTERDOC.md
├── INSTALL.md                      (this file)
├── INSTRUCTIONS.md
├── QC.md
├── CHANGELOG.md
├── CWFE-MANIFEST.json              (P0-P16 phase spine + AF-CWFE-* codes)
├── cinematic-web-funnel-entry.sh   (fail-closed front door, ADR-6)
└── run_cinematic_web_funnel.py     (manifest-driven orchestrator)
```

## Verifying an install

From the skill directory:

```bash
bash cinematic-web-funnel-entry.sh --self-test
```

Expected: `RESULT: PASS` — this proves `python3` is present, `skill-version.txt` matches
the `SKILL.md` frontmatter major version, the manifest loads with phases in contiguous
`P0..P16` order, and direct nonce-less invocation of the orchestrator is rejected.

From the repository root, the shared drift gate also covers this skill automatically
(no per-skill exemption needed):

```bash
bash scripts/qc-assert-skill-frontmatter-version.sh
```

## What this unit does NOT install

No phase gate scripts, no provider adapters, no Next.js template, no GHL/Vercel
integration code, and no department-map/registry/`cc-compat.json` registration. Those
ship in later, separately verified build units. Installing this skeleton onto a client
box makes the skill directory present and self-test-clean; it does not yet make the
engine capable of producing a deployed site — the front door will correctly refuse to
certify any run until the phase gate scripts land.
