# Deployment evidence — PBB-070 / T-47 cross-repository compatibility

**Status: NOTHING IS DEPLOYED.** No push, pull request, merge, installer run, service restart, database migration, or client-box contact produced this document or the manifest beside it. Everything below was read from local git objects and repository files on the operator Mac mini on 2026-10-24. The machine-readable companion is [`compatibility-manifest.json`](./compatibility-manifest.json).

## Commits the interfaces were verified against

| Repository | Ref read | Commit | Version | How the commit was produced |
|---|---|---|---|---|
| `trevorotts1/openclaw-onboarding` | `origin/main` | `bccc4050f8ed98b2d9b55cfc087c27c924d62b03` | `v27.1.65` | `git -C ".../build-t47" rev-parse origin/main` |
| `trevorotts1/999-setup` | `origin/main` | `1d1545fc84129d2995231347886c0a8822395935` | `1.38.1` | `git -C ".../999-setup" rev-parse origin/main` |
| `trevorotts1/blackceo-command-center` | tag `v7.6.112` (the deployment pin in `cc-compat.json`) | `ef6b9364e8ddd695f357cca2f3ed41ab75262a13` | `v7.6.112` | `git -C ".../blackceo-command-center" rev-parse 'v7.6.112^{commit}'` |

999-setup's local working copy was at `3b4e0b97` (behind `origin/main`), and the Command Center's at `a92d11d9`. Every check read the named commit's objects with `git show`, `git grep`, `git cat-file`, and `git archive`; no working tree was treated as evidence. The onboarding checkout is exactly `origin/main`.

## Proven (static interface checks that passed)

1. **Pin resolution.** `shared-utils/cc_compat.py` resolves `pinnedTag` `v7.6.112`, asserts it against `minVersion` `v7.4.0`, exit 0.
2. **Pin identity.** Tag `v7.6.112` peels to `ef6b9364`, that commit's `version` file reads `v7.6.112`, and `release-cohort.json` `cc_sha` is the identical string.
3. **HTTP routes at the pin.** `src/app/api/system/converge/route.ts` and `src/app/api/ad-campaigns/route.ts` both exist at `ef6b9364`.
4. **Decision bridge schema.** Onboarding `BRIDGE_SCHEMA_VERSION = "1.1.0"`, Command Center `DECISION_SCHEMA_VERSION = '1.1.0'` at the pin, and `release-cohort.json` `contract = "1.1.0"` — all three equal.
5. **999-setup → onboarding helper pins.** `installer-registration/check-helper-pins.py --onboarding <onboarding worktree> --ref origin/main` at 999-setup `1d1545f`: exit 0, "every pin equals openclaw-onboarding@origin/main and every vendored helper folder matches its pin." Covers the nine registered helpers only.
6. **999-setup → Command Center filesystem contract.** Both sides name the same 9Router registry path (`~/.9router/db/data.sqlite`: 999-setup `configure-nine-router.mjs`, Command Center `presentation_job/capacity.py` `NINEROUTER_DB`) and the same claude-nine config root (`~/.claude-nine/settings.json`: 999-setup `launchers/macos/claude-nine`, Command Center `HARNESS_SETTINGS_CANDIDATES`).

## NOT proven

1. **Nothing has been run.** No installer, no `claude-nine`, no 9Router, no Command Center build, no HTTP request to any live service. All proof is static file-and-git inspection.
2. **Skill 71 ingestion is incompatible at the deployment pin.** `/api/skill-runs/ingest` and `/api/skill-runs` are referenced by onboarding `71-blackceo-signature-page/references/run-events-schema.md` and by the same files inside the 999-setup vendored copy, but neither route exists at `ef6b9364` (`v7.6.112`). Both routes exist only on unpinned Command Center `origin/main` `6fb636071f1cbc480721c8d658ce36ad627f57dd` (`v7.6.125`). Marked UNVERIFIED in the manifest.
3. **Vendored skill trees are not equal to canonical main.** Spot checks: `77-council-of-wise-elders` `v1.0.54` vs `v1.0.51`; `75-drama-song-ad-factory` `v2.9.106` vs `v2.9.99`; `71-blackceo-signature-page` `1.3.6` vs `1.3.4`. Recorded vendoring sources are historical — `council-vendoring.json` names onboarding `77eb96e` (250 commits behind `origin/main`), `DIST-02-PACKAGING-MANIFEST.json` names onboarding `39e7443` (1416 commits behind). Only the nine helper registrations are pinned and guarded.
4. **The repository's recorded tested pair is stale.** `release-cohort.json` `onb_sha` is `f8491492`, a real ancestor of `origin/main` but **2567 commits behind** `bccc4050f`. The static checks above hold at `bccc4050f`, but that is not the pair the decision-engine trainer recorded as tested.
5. **No box state was observed.** No fleet or client machine was contacted, so deployed versions on any box are unknown here.

## What a human must do that an agent cannot

1. **Decide the Command Center commit to deploy.** Keep the `v7.6.112` pin and accept that Skill 71 ingestion has no receiver, or move the pin to `v7.6.125`+ with `scripts/pin-cc-tag.py` (which writes both `cc-compat.json` and `release-cohort.json`). Moving a release pin is a release decision, not an agent action.
2. **Decide whether 999-setup is re-vendored and released** before or after the onboarding/Command Center deployment. The current distribution lags canonical main.
3. **Supply credentials and provider keys** on the target machine. None were read, tested, or written here.
4. **Run the installers and runtime verification on a canary machine with the owner present**, including installing 999-setup on a non-operator machine, confirming `claude-nine` plus 9Router start, and running the Skill 71 shipper only if a receiver exists.
5. **Perform the deployment itself** — checkout, build, Command Center migrations, service restart — with an explicit GO, and record the result. This document does not authorize it.

## Reproduce the checks

```bash
cd "/Volumes/mac mini m4/Downloads/git trees and automations/worktrees/pb-skill38-20261024/build-t47"

git rev-parse origin/main
git -C "../999-setup" rev-parse origin/main
git -C "../blackceo-command-center" rev-parse 'v7.6.112^{commit}'

python3 -B -c "import sys; sys.path.insert(0,'shared-utils'); from cc_compat import load_cc_compat, resolve_cc_tag, assert_min_version; d=load_cc_compat(); t=resolve_cc_tag(d); assert_min_version(t, d); print(t, d['commandCenter']['minVersion'])"

git -C "../blackceo-command-center" cat-file -e 'v7.6.112^{commit}:src/app/api/system/converge/route.ts'
git -C "../blackceo-command-center" cat-file -e 'v7.6.112^{commit}:src/app/api/ad-campaigns/route.ts'
git -C "../blackceo-command-center" cat-file -e 'v7.6.112^{commit}:src/app/api/skill-runs/ingest/route.ts'   # expected: ABSENT at the pin
git -C "../blackceo-command-center" cat-file -e '6fb636071f1cbc480721c8d658ce36ad627f57dd:src/app/api/skill-runs/ingest/route.ts'  # EXISTS on main

git -C "../999-setup" archive 1d1545fc84129d2995231347886c0a8822395935 | tar -x -C "/Volumes/mac mini m4/Downloads/git trees and automations/scratch/pb-skill38-20261024/lanes/PBB-070-lane"
cd "/Volumes/mac mini m4/Downloads/git trees and automations/scratch/pb-skill38-20261024/lanes/PBB-070-lane"
python3 -B installer-registration/check-helper-pins.py --onboarding "/Volumes/mac mini m4/Downloads/git trees and automations/worktrees/pb-skill38-20261024/build-t47" --ref origin/main
```
