# Skill 47 — Dependency Manifest (§A)

> **Status: NO VENDORING REQUIRED** — every dependency is fetched at install time.

## Research basis

All claims below were read from `/tmp/openmontage-read-102` (remote `github.com/calesthio/OpenMontage`, HEAD `a5b5b12`, verified via `git remote -v`).

## Finding: zero git submodules

```
ls .gitmodules  →  "No such file or directory"
```

OpenMontage has **no `.gitmodules`** file. There are **zero git submodules**. HyperFrames and Remotion are both consumed as npm packages, not nested GitHub clones.

## Dependency table

| Dependency | Type | In fleet template repo? | How it reaches the client box |
|---|---|---|---|
| OpenMontage itself | GitHub repo (AGPLv3) | NO | Skill 47 `git clone github.com/calesthio/OpenMontage` at install |
| pyyaml / pydantic / jsonschema / python-dotenv / Pillow / requests / google-auth | PyPI | NO | `make setup` → `pip install -r requirements.txt` |
| remotion + @remotion/* + react / react-dom | npm | NO | `make setup` → `cd remotion-composer && npm install` |
| hyperframes | npm (CLI via npx) | NO | `make setup` → `npx --yes hyperframes --version` (cache-warm) |
| piper-tts | PyPI | NO | `make setup` → `pip install piper-tts` (soft-fail: skip if unavailable) |
| FFmpeg + ffprobe | system binary | NO | Skill 47 fail-loud preflight: `command -v ffmpeg` (client installs via brew/apt) |
| Node >= 18 + npx | system binary | NO | Skill 47 fail-loud preflight: `node -v` + version check (client installs) |
| torch / torchaudio / torchvision (GPU) | PyPI | NO | OPTIONAL `make install-gpu` only if client has NVIDIA GPU — out of scope v1 |
| Wav2Lip / SadTalker | GitHub repos (local clone) | NO | OUT OF SCOPE v1 — runtime client clone if ever enabled; never vendored |

## Source evidence (file + line in OpenMontage)

- **Python deps** — `requirements.txt`: `pyyaml>=6.0`, `pydantic>=2.0`, `jsonschema>=4.20`, `python-dotenv>=1.0`, `Pillow>=10.0`, `requests>=2.31`, `google-auth>=2.0`. `setup.py` `install_requires` mirrors this list.
- **Remotion** — `remotion-composer/package.json` `dependencies`: `remotion ^4.0.441` + `@remotion/cli`, `captions`, `google-fonts`, `media`, `player`, `transitions` at `^4.0.441` + `react/react-dom ^18.2.0`. Pulled by `Makefile` `setup:` → `cd remotion-composer && npm install`.
- **HyperFrames** — `Makefile` `setup:` warms via `npx --yes hyperframes --version`. Runtime check in `tools/video/hyperframes_compose.py`. HyperFrames is the npm package `hyperframes`, resolved on demand by `npx`. NOT a git submodule, NOT vendored source.
- **Piper** — `Makefile` `setup:` → `pip install piper-tts` (soft-fail: "TTS will use cloud providers instead"). Consumed by `tools/audio/piper_tts.py`.
- **System binaries** — FFmpeg, Node >=18, npx. Checked by Skill 47's `preflight.sh`. Also probed by `make hyperframes-doctor` in the OpenMontage tree.

## Conclusion

**Nothing needs to be vendored into the main `openclaw-onboarding` repo.** Every dependency is fetched at install time by:
1. Skill 47's `preflight.sh` (system binaries — exits 1 with a precise fix if missing)
2. `git clone` (OpenMontage itself — AGPLv3 stays on client deployment)
3. `make setup` (PyPI packages + Remotion npm + HyperFrames npx + piper-tts)

This is the AGPLv3-safe path AND keeps the fleet template clean.

## Vendoring contingency (NOT triggered)

The vendoring escape hatch in the build spec is:
> "Vendor ONLY a dep Skill 47 cannot fetch — into `47-…/vendor/` with its license, never AGPLv3 OpenMontage source."

This contingency does NOT trigger because every dep is fetchable. If a future upstream change makes a dep unfetchable on the client box (e.g. a removed npm package), ONLY THEN does a vendored copy land in `47-movie-producer/vendor/` with its license. AGPLv3 OpenMontage source is NEVER vendored.

## Proof command (run on a clean box)

```bash
bash ~/.openclaw/skills/47-movie-producer/verify-deps.sh
```

Expected output ends with:
```
=== PASS: All deps fetched by make setup. No vendoring required. ===
```
