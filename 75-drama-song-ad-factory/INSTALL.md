# INSTALL - Skill 75: Drama Song Ad Factory (OpenClaw distribution)

Install/update instructions for a clean onboarding box. Follow the steps
in order, verbatim - the QC rubric scores that (≥ 8.5/10 to pass).

## Step 0: Contracts and prerequisites (before anything else)

1. Read `INSTALL-CONTRACT.md` at the repo root and acknowledge it in your
   work log (violation handling lives there).
2. Complete Skill 01 (`01-teach-yourself-protocol`) and Skill 02
   (`02-back-yourself-up-protocol`) - repo law and build-directive
   section 25 step 1. Both ship with this repo's installer.
3. Read this skill's `SKILL.md`, `INSTRUCTIONS.md`, `EXAMPLES.md` and
   `QC.md` BEFORE running anything.

## Step 1: First-time onboarding install

The canonical one-liner (from the `install.sh` header):

```bash
curl -fSL --progress-bar https://raw.githubusercontent.com/trevorotts1/openclaw-onboarding/main/install.sh | bash
```

It detects Mac (`~/.openclaw/`) vs VPS (`/data/.openclaw/`) via
`OPENCLAW_PLATFORM` (auto-detect: presence of `/data/.openclaw`), then
installs the numbered skill folders additively into the box's skills dir.

Already on a checkout? From the repo root:

```bash
bash install.sh
```

The skill lands at:

```text
$SKILLS_DIR/75-drama-song-ad-factory/      # Mac: ~/.openclaw/skills/...
                                            # VPS: /data/.openclaw/skills/...
```

`SKILLS_DIR` resolves as `${OC_SKILLS_DIR:-${OPENCLAW_ROOT:-${OC_CONFIG:-$HOME/.openclaw}}/skills}`
(`shared-utils/lib-shared.sh` `discover_skills_dir`).

## Step 2: Update an existing box

From an onboarding checkout at the repo root:

```bash
bash update-skills.sh
```

Same platform auto-detection as `install.sh`. Updates are additive
per-item copy; verify afterwards:

```bash
cat "$SKILLS_DIR/75-drama-song-ad-factory/skill-version.txt"
```

## Step 2b: Lip-sync picture gate (face model + mediapipe)

Without these the gate refuses every lip-sync job (nothing else in the skill needs them):

```bash
python3 -m pip install 'mediapipe>=0.10.14' opencv-python-headless numpy
python3 "$SKILLS_DIR/75-drama-song-ad-factory/scripts/core/lip_sync/lip_gate/install_face_model.py"
```

The second command downloads `face_landmarker.task` from Google's official URL, verifies its
pinned sha256, and places it in `assets/face_landmarker.task` (or `$LIPSYNC_FACE_MODEL`).
Re-run it after every skill update (an update replaces the skill folder).

## Step 3: Credentials (canonical paths, canonical names)

Needed for paid KIE paths (required):

```bash
# confirm presence ONLY - never print values
grep -c KIE_API_KEY ~/.openclaw/secrets/.env 2>/dev/null || echo "add it"
chmod 600 ~/.openclaw/secrets/.env     # Mac
# VPS: /data/.openclaw/secrets/.env
```

If absent, ask the operator to add `KIE_API_KEY` to
`~/.openclaw/secrets/.env` (Mac) or `/data/.openclaw/secrets/.env`
(VPS), chmod 600, then:

```bash
openclaw config set env.vars.KIE_API_KEY "$KIE_API_KEY"
```

Do NOT mint a new key. `FISH_AUDIO_API_KEY` / `FISH_AUDIO_VOICE_ID` are
only needed for spoken voiceover stages (Skill 30); sung-only campaigns
skip them.

Command Center board sync (`scripts/core/cc_sync.py`) also needs these
three environment variables (names only - values live in the env stores,
never printed):

- `CC_WORKSPACE` - the workspace binding the outbox enforces (required;
  without it the sync refuses to start).
- `MC_API_TOKEN` - the Bearer token Command Center's middleware checks.
- `WEBHOOK_SECRET` - the HMAC secret for the `x-webhook-signature` header.

A **403** from the board means Command Center credentials are missing;
the ad still finishes locally. The board sync reports an auth error and
stops sending - the campaign folder, receipt and delivery are unchanged.

## Step 4: Helper skills are NOT installed by reference

Build-directive section 2.4: references to onboarding Skills
66/67/68/74 (and 07/24/25/27/30/46) do not install them. The unified
installer copies every numbered folder it ships; if a helper folder is
missing on the box, the prerequisite checker names it - fix before paid
work (Step 5). Do not hand-copy helper code; re-run the installer/updater.

## Step 5: Verify the install

```bash
# 5a. prerequisites (exit 0 = satisfied; exit 2 = missing prereqs, listed
#     with their satisfy strings; never blocks install - Rule 16)
bash "$SKILLS_DIR/shared-utils/check-skill-prereqs.sh" "$SKILLS_DIR/75-drama-song-ad-factory"
echo "rc=$?"

# 5b. control layer smoke - intake must exit 0 on a complete brief
cd "$SKILLS_DIR/75-drama-song-ad-factory"
python3 scripts/core/intake_preflight/factory.py intake --brief-file /path/to/complete-brief.json
echo "rc=$?"     # expect 0 (ok)

# 5c. preflight on a writable scratch root with an authorization record
python3 scripts/core/intake_preflight/factory.py preflight \
  --root "$PWD/scratch-storage" --storage-dir "$PWD/scratch-storage" \
  --auth-file /path/to/auth-ok.json --summary-digest testdigest
echo "rc=$?"     # expect 0 (preflight-pass)
```

Exact fixture shapes and captured outputs for 5b/5c: `EXAMPLES.md`
(Examples 1 and 6). Then run `QC.md` and score ≥ 8.5/10.

## Step 6: Run storage

Campaign runs live under an operator-approved persistent root (section 21
canonical project structure; on the operator box that root is
`~/Downloads/Drama Song Ads`). The preflight `--root` must point inside
it; references outside the root are rejected. Never create a second
writable run-state authority for a campaign.

## Step 7: Version and contract bookkeeping

- `skill-version.txt` is the skill's version of record; keep
  `SKILL.md` frontmatter `version:` in agreement (Section 1 of QC.md
  checks it).
- Schema/contract versions live in
  `scripts/core/contracts/*-schema.json` and
  `scripts/core/acceptance-profile.json` (see DEPENDENCY-MANIFEST
  section 6). Any contract bump re-qualifies both distributions through
  the parity tests before release (directive 2.3/2.4).
- Release manifests (core + adapter versions, schema versions, Command
  Center API compatibility, source commits, dependency hashes, notices)
  are produced at release time per DEPENDENCY-MANIFEST.

## Rollback

`install.sh`/`update-skills.sh` write backups before changing a box
(Mac: `~/Downloads/openclaw-backups/`; VPS: `/data/.openclaw/backups/`
- canonical paths from the installer header). To roll back: restore the
skill folder from the box's backup copy, then re-run Step 5 to confirm
the restored version. For a partial skill rollback in git, restore the
folder from the previous release commit and re-run Step 5. Never roll
back by deleting a client's run state or ledger.

## After install

Per the self-audit in `INSTALL-CONTRACT.md`: recite the checklist, run
`QC.md`, and send the owner-facing confirmation: "Skill 75 active.
Anything pending your attention: [list]."
