# Version Architecture

## How Versioning Works

There are TWO sides to version tracking:

### Publisher Side (GitHub)
- `version` file at repo root: the canonical published version
- `install.sh` ONBOARDING_VERSION variable: MUST match the root version file
- These are set by the repo maintainer when pushing updates
- Rule: NEVER update one without the other

### Client Side (Installed Machine)
- `~/.openclaw/skills/.onboarding-version`: the installed version
- Written by install.sh after a successful install or update
- This is what the update script checks against GitHub

### Update Check Flow
1. Update script downloads GitHub version file
2. Compares GitHub version vs ~/.openclaw/skills/.onboarding-version
3. If different: update available
4. If same: already up to date

### Per-Skill Versions
- Each skill has skill-version.txt in its folder
- ~/.openclaw/skills/.skill-manifest.json lists all skill versions
- The updater compares skill versions individually
- A skill can be updated independently of other skills

### Rollback
- Before any update, the full skills folder is backed up
- Rollback restores the backup and resets .onboarding-version
- .skill-manifest.json is regenerated after rollback

### Version Format
- Repo level: vMAJOR.MINOR.PATCH (e.g., v8.1.0)
- Skill level: vMAJOR.MINOR.PATCH (e.g., v7.0.0)
- MAJOR: breaking changes, architecture rewrites
- MINOR: new features, non-breaking additions
- PATCH: bug fixes, doc updates
