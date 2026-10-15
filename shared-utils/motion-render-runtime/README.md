# Shared Motion Render Runtime

One reproducible rendering runtime shared by **Skill 47 (Movie Producer)**
and **Skill 72 (Motion Video Plus)**. Both skills need the same two
headless-Chromium render engines at the same pinned versions; this directory
is the single provisioning implementation they both call, so the versions
can never drift between skills and a failed engine install can never be
reported as success.

## What is pinned here

From `package.json` / `package-lock.json` (the committed contract; installs
use `npm ci` against the lockfile and never fetch `latest`):

| Package | Pin | Role |
|---|---|---|
| `remotion`, `@remotion/cli`, `@remotion/renderer`, `@remotion/bundler` | 4.0.535 | Remotion engine (all `@remotion/*` packages move in lockstep) |
| `hyperframes` | 0.8.155 | HyperFrames engine (HeyGen CLI) |
| `gsap` | 3.15.0 | Animation library used by HyperFrames compositions |
| `react`, `react-dom` | 19.3.0 | Remotion composition runtime |
| `typescript` (dev) | 5.9.3 | Type tooling for the runtime's composition sources |

Host requirements: Node >= 22, npm, and (for final encodes) ffmpeg. On
Linux, Chromium needs system libraries; `provision.sh` installs them via
apt (same package set Remotion documents for Docker/Linux). There are no
Python dependencies for this runtime itself; Skill 47's optional Piper TTS
stays in the Skill 47 wrapper (opt-in, pip-pinned there).

## Who calls it

- **Skill 72** invokes `provision.sh` directly at install time (see
  `72-motion-video-plus/INSTALL.md`). Skill 72 has **no OpenMontage-clone
  requirement**; nothing in this directory knows OpenMontage exists.
- **Skill 47** calls it from `47-movie-producer/provision-render-deps.sh`,
  which first provisions these generic engines through this directory and
  then does its own OpenMontage-clone-specific work (clone presence,
  the clone's `remotion-composer` pin, optional Piper). A generic-engine
  failure now fails the Skill 47 wrapper too; the old WARN-only success
  behavior is gone.

## Exit-code contract

`provision.sh` exits **0 only when the install (or verified reuse) is
complete AND the readiness probe passed for every mandatory engine**. It
exits 1 with a `FAIL` line naming the failed step or engine when:

- node/npm is missing or Node < 22, or the OS is unsupported;
- `npm ci` (or the override `npm install`) fails;
- the Remotion browser ensure fails;
- the probe fails for Remotion or HyperFrames.

There is no WARN-only success path for mandatory engines. The apt step may
warn (for example on a non-apt distro): the probe's real browser launch is
the hard gate, so a genuinely missing system library surfaces as a probe
failure, never as a silent pass.

## The readiness probe (`probe.mjs`)

Readiness is proven by launching and rendering, not by checking that
`node_modules` exists:

- **Remotion:** bundles a minimal composition on the fly and renders one
  real frame to PNG via `@remotion/bundler` + `@remotion/renderer`, then
  verifies the PNG signature, the exact dimensions, and a non-trivial
  file size. It also records the resolved Chrome-Headless-Shell revision.
- **HyperFrames:** runs the pinned CLI `--version` and its health command
  (`doctor`, discovered from `--help`) and requires exit code 0.

The probe writes **`runtime-lock.json`**: measured package versions, Node
version, platform, browser revision, ffmpeg version when present, a
timestamp, and a per-engine pass/fail record. It is the evidence artifact
for "this box can render", and later stages may compare against it.

## Layout: committed code vs generated state

Committed (source of truth):

```
package.json  package-lock.json  provision.sh  probe.mjs  rollback.sh  README.md  .gitignore
```

Generated local state (gitignored, never committed; anti-tamper: these are
caches/local config class artifacts, not skill source):

```
.runtime/
  versions/<lock-hash>/     one verified runtime per lockfile hash
    node_modules/  probe.mjs  package.json  runtime-lock.json  ...
  current -> versions/<lock-hash>
  runtime-lock.json         copy of the active runtime's probe record
node_modules/  .cache/      any tool-local spill at the package root
```

## Atomic switch and idempotency

- Installs land in `.runtime/staging-*` first. Only after the probe passes
  is the staging directory promoted to `.runtime/versions/<id>/` and the
  `.runtime/current` symlink flipped (temp link + rename, so the flip is
  atomic). A failed or interrupted run discards staging and leaves the
  previously verified runtime active and untouched.
- A repeat run whose plan (lockfile hash) matches the active runtime
  skips the reinstall, re-runs the probe against the active runtime to
  prove it still launches and renders today, refreshes
  `.runtime/runtime-lock.json`, and exits 0.

## Rollback (`rollback.sh`)

`rollback.sh [version-id]` flips `.runtime/current` back to a previously
verified version without re-provisioning. With no argument it targets the
newest (by modification time) verified version other than the one
currently active. A version counts as verified only when its
`runtime-lock.json` records `result: "pass"` with both mandatory engines
(Remotion and HyperFrames) passing; an unverified target is refused. It
also refuses, exit 1 with the pointer untouched, when the target directory
is missing, when an `.runtime/active-renders.json` record names a live
process (a running render keeps its pinned runtime undisturbed), or when
node is unavailable. The flip is the same atomic temporary-symlink-plus-
rename the provisioner uses, `.runtime/runtime-lock.json` is refreshed
from the target's record, nothing is deleted, and running it while
already on the target exits 0. `MOTION_RUNTIME_HOME` overrides the
runtime home (default: the script's own directory) so a staged copy can
be verified before use.

## Environment toggles

| Variable | Effect |
|---|---|
| `MOTION_RUNTIME_SKIP_APT=1` | Skip the Linux apt system-library step (assumed pre-provisioned). `SKILL47_SKIP_APT=1` is honored as a legacy alias. |
| `REMOTION_VERSION=x.y.z` | Development override: pin every `@remotion/*` package to another version. Bypasses the committed lockfile for that run and lands in its own `versions/override-*` directory. |
| `HYPERFRAMES_VERSION=x.y.z` | Development override for HyperFrames, same semantics. |

Overrides exist for development and incident response. Normal installs use
the committed lockfile only; renders never resolve versions at render time.
