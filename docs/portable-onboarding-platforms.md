# Onboarding on Mac and Linux VPS

The operating system and runtime topology determine installation behavior. A
Hostinger or Contabo label does not establish whether OpenClaw runs directly on
Linux or inside Docker.

`platform/common.sh` provides the shared resolver. `oc_detect_platform` maps
Darwin to `mac` and Linux to `vps`. `oc_runtime_topology` checks container markers.
`oc_set_platform_paths` preserves `OPENCLAW_ROOT` and the matching
`OPENCLAW_WORKSPACE_PATH` / `OPENCLAW_WORKSPACE_ROOT` pins, then reads an existing
configured workspace before choosing a default. Conflicting workspace pins or
two unselected installed roots must be resolved explicitly; another client's
directory is never substituted.

| Runtime | Default client root | Bootstrap behavior |
| --- | --- | --- |
| macOS | `~/.openclaw` | Mac prerequisites and power policy |
| Native Linux VPS | `~/.openclaw` | Linux prerequisites; no Docker requirement |
| Existing Linux `/data` installation | `/data/.openclaw` | Preserve the existing root |
| Container with `/data` mounted | `/data/.openclaw` | Work inside the container; never nest a Docker re-exec |
| Docker host | Resolve the client's running container first | Re-execute in that container, preserving explicit identity and path pins |

A native root/config/runtime takes precedence over an unrelated Docker daemon.
`OPENCLAW_CONTAINER_NAME` explicitly selects a container and must exactly match a
running name. Multiple OpenClaw containers, or a stopped container, do not fall
back to creating a replacement host installation. The container's configured
user is honored; Docker's empty user value means root, not a guessed `node`
account. Root/workspace pins supplied during re-exec must name paths **inside
that container**. The bootstrap forwards them as data, alongside the two client
identity answers.

The persona writer supports the stock Bash 3.2 shipped by macOS and modern Linux
Bash. Prebuild resolves and verifies an absolute interpreter before materializing
the company, so a background service's limited PATH cannot select the wrong
shell. `OPENCLAW_BASH` is an optional absolute pin; an invalid pin is rejected.
No Homebrew Bash installation is required just to write governing persona files.
Other tools such as Command Center atomic deployment retain their own stated
prerequisites.

Native Linux systemd startup is registered by Skill 32's
`scripts/ensure-pm2-boot.py` after dashboard/tunnel convergence. The helper saves
PM2 under the current runtime user, keeps HOME/PM2_HOME and the absolute executable
paths, and verifies its systemd unit is enabled without restarting live services.
It uses root or passwordless sudo; unsupported init, missing privilege or an
incompatible or unverifiable existing unit leaves installation pending. A compatible
existing official PM2 unit is verified, preserved and enabled. Existing Mac
launchd and Docker host/entrypoint policies are preserved. An enabled unit proves
startup registration; an actual host reboot test remains a separate acceptance
check.

Hermetic verification:

```bash
python3 tests/unit/test_portable_bootstrap.py
python3 tests/unit/test_governing_persona_portability.py
python3 tests/unit/test_pm2_boot.py
```

These tests use isolated client roots, fake Docker inventory and no live services
or package installs. The persona tests execute the real writer under `/bin/bash`
with a restricted service PATH and verify both contents and repeat-run retention.

Presentation intake scheduling uses the same selected client context. Mac plist
jobs and VPS cron commands carry the root/workspace pins and the installed
Presentations runs directory; a checkout used as the script source does not
become the runs directory. Scheduler configuration is validated before replacing
a working job. Invalid selections stop installation with a specific failure.

Presentation worker credential candidates remain inside the selected client root
and workspace. An invalid path resolver or incomplete helper deployment does not
fall back to another installation’s HOME, `/data`, or legacy stores. Existing
nonstandard credential locations must be migrated into the selected client
installation or configured as a valid in-boundary override.
