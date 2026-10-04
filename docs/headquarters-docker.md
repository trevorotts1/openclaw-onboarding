# Headquarters — Docker target guide (Hostinger VPS)

Audience: the operator standing up or repairing a Docker Target box. This guide
describes the **existing** colocated packaging. It introduces no new container,
no new image, no new service and no new dependency — Command Center already runs
as a pm2 process *inside* the OpenClaw container, and this document only covers
what Headquarters adds to that arrangement.

Authority: `SPEC.md` rev 4 sections S5, S6, S7, S10; `swarm-plan.json` rev 4
tasks B17, B19, B32; frozen contracts `evidence/contracts/targets.md` and
`evidence/contracts/capture-bindings.md`. Where this guide and the SPEC differ,
the SPEC wins and this file is the bug.

Related: `docs/portable-onboarding-platforms.md` (platform differences),
`docs/FLEET-ROLL-RUNBOOK.md` (the roll this installer is part of),
`docs/MC-ROUTE.md` (routing).

---

## 1. What "the Docker target" is

One container, one persistent mount, one pm2 daemon:

| Piece | Value |
|---|---|
| Container | the box's own `hvps-openclaw` service — **never a Headquarters container** |
| Persistent mount | `/data` (Hostinger's volume; survives `--force-recreate`) |
| Command Center checkout | `/data/projects/command-center` |
| pm2 app | `blackceo-command-center`, launched by `scripts/cc-start.sh --port 4000` |
| Port | `CC_PORT` (default 4000). `PORT` is never read — Hostinger injects a random `PORT`, and `cc-start.sh` explicitly strips it |
| DB | `/data/projects/command-center/mission-control.db` (`DATABASE_PATH` in the pm2 env block) |
| Gateway | the image's `node server.mjs`; the startup script never touches, restarts or signals it |

Two guard rules inherited from the existing packaging, both load-bearing:

* **pm2 runs as node, never root.** A root pm2 daemon at `/data/.pm2` ran the
  Command Center as root; its python skill calls left root-owned `__pycache__`
  in the skills tree and the next update rolled the whole box back
  (2026-09-29). `container-startup.sh` hands `PM2_HOME` to node and re-execs
  itself as node when started as root.
* **`stop_exit_codes: [78]` is one contract across two files.** `cc-start.sh`
  exits 78 for exactly one condition (a deterministically stale build) and pm2
  must stop rather than restart-loop on it. Change 78 only together with
  `scripts/cc-start.sh`'s own `exit 78`.

## 2. Persistent paths Headquarters depends on

These are the `vps-docker` values of Command Center's `src/lib/platform.ts`,
expressed from the mount root so they are provably inside `/data`:

| Purpose | Path |
|---|---|
| OpenClaw config | `/data/.openclaw/openclaw.json` |
| Tenant workspace (vault, scratch) | `/data/.openclaw/workspace/` |
| Telemetry correlation store | `/data/.openclaw/workspace/hq-telemetry/correlation/` |
| Telemetry outbox | `/data/.openclaw/workspace/hq-telemetry/outbox/` |
| Bridge device identity | `/data/.openclaw/mission-control/identity/` |
| Path-loaded extensions | `/data/.openclaw/extensions/` |

`container-startup.sh` creates any that are missing (`mkdir -p`; it never
deletes, moves or truncates) before pm2 resurrects. Nothing above is a new
location: the workspace and identity roots are the ones Command Center already
resolved on this platform, and the two `hq-telemetry` directories are the
subpaths the outbox adapter (task B17) and the telemetry extension (task B19)
were frozen against.

Persistence is what makes container replacement safe. `--force-recreate` gives
the container an empty pm2 and an empty layer above `/data`; rows, the outbox,
the correlation store and the bridge keypair all live under the mount, so the
same logical company comes back.

## 3. Startup resurrection

`platform/vps/hostinger/container-startup.sh` is the container's `command:`.
It is installed on the **host** by
`platform/vps/hostinger/install-startup-hook.sh /docker/<project>`:

1. copies the script to `<project>/data/.openclaw/scripts/`;
2. writes `command: ["bash", "/data/.openclaw/scripts/container-startup.sh"]`
   onto the `hvps-openclaw` service, backing the compose up first;
3. refuses a compose that already carries some *other* `command:` (merge by
   hand), and refuses when the edited compose does not validate.

Nothing is restarted; the hook takes effect at the next container (re)create.
Order of operations inside the startup script:

1. persistent roots ensured (section 2) and the recorded Headquarters flag
   echoed to `/data/.openclaw/logs/container-startup.log`;
2. after `PM2_RESURRECT_DELAY` (default 45 s, so the gateway is warm),
   `pm2 resurrect`;
3. if `blackceo-command-center` is still absent from pm2 **and**
   `ecosystem.config.cjs` exists, `pm2 start ecosystem.config.cjs && pm2 save`;
4. `exec node server.mjs` — the image's own gateway wrapper.

Contabo has its own parity file at `platform/vps/contabo/container-startup.sh`
with different path mechanics (HOME is ephemeral there); the two are kept
side by side and are not interchangeable.

## 4. Install and upgrade

First install of the in-container toolchain is
`/data/projects/command-center/scripts/install/vps-docker-bootstrap.sh` run
inside the container: apt packages, Node 20, npm globals, `uv`, cloudflared,
persistent directories, the canonical pm2 ecosystem, an **additive** env-file
reconcile, the Headquarters capability check, pm2 startup, and Command Center
repair. Every step is idempotent; re-running is safe.

The Headquarters additions to that script are additive and non-destructive:

* the env reconcile appends only keys that are present as **active** lines in
  the repository template and absent from the live file — an operator's value is
  never modified, reordered or deleted, and a `.env.bak` precedes every write;
* the capability check is **read-only** (SQLite opened `mode=ro`).

Updates run through the existing onboarding roll: `install.sh` (fresh box) or
`update-skills.sh` (fleet roll), both of which now register the telemetry
extension explicitly — see section 5.

## 5. The telemetry extension, and why registration is explicit

Headquarters exchange capture is a passive OpenClaw plugin,
`extensions/agent-exchange-telemetry` (built by task B19). It observes
`before_tool_call` / `after_tool_call` for `sessions_send` and `sessions_spawn`
plus the run-scoped `lifecycle` terminal stream. It replaces no tool, edits no
parameters, invokes no agent, changes no model and synthesizes no dialogue.

**It is path-loaded, not bundled.** Nothing discovers it by scanning sibling
directories: an unregistered copy on disk is a copy that never loads, and
capture silently reports zero exchanges. `install.sh` and `update-skills.sh`
therefore carry an explicit deploy-and-register block (mirroring the existing
CEO Routing Doctrine block, whose three hard-won rules apply unchanged):

| Rule | Why |
|---|---|
| `cp -R "$SRC/." "$DST/"` — the `/.` form | the plain form nests a second copy on the second run; every roll would add another |
| `plugins.entries.<id>` gets `enabled` **only** | `hooks` there is `additionalProperties:false`; writing `allowPromptInjection` made `openclaw config validate` FAIL, which is fatal at gateway startup — the gateway never starts and cron freezes forever, silently |
| append `plugins.load.paths` only if absent; **extend** `plugins.allow` only when it already exists | `apply-fleet-standards.sh` rewrites `allow` to the bundled ids earlier in the roll; creating an allowlist where none existed disables every other plugin |

One deliberate difference from the doctrine block: this entry is merged
**additively** (`setdefault` + `enabled: true`), because the extension has a
`configSchema` and its `config` object carries the trusted identity. A whole
object assignment would silently blank the box's capture identity. The block
fills `config.companyId` / `config.installationId` from values this box already
recorded (`openclaw.json` `env.vars`, then the installer environment) and writes
nothing when they are absent — an unproven identity stays absent so the plugin
records honest uncorrelated capture health instead of a guessed company. The
plugin may not read those values from hook context or tool params; that is a
frozen finding of the capture contract, not a limitation of the installer.

Credentials and provider settings are never touched or printed: the block writes
only `plugins.entries`, `plugins.load.paths` and `plugins.allow`, refers to keys
by NAME, and backs `openclaw.json` up to a timestamped `.bak.xet-…` file before
an atomic `os.replace`.

## 6. The availability flag

`HEADQUARTERS_ENABLED` is an operational fallback, **not** customer activation
approval. It is written only after capability checks, by two independent paths
that must agree:

| Path | When it runs | File it writes |
|---|---|---|
| `vps-docker-bootstrap.sh` step 8d | first install in-container | `/data/.openclaw/.env` |
| `run-full-install.sh` phase 6k | every install/update roll | `<CC>/.env.local` |

Both write `1` only when the additive HQ tables of SPEC S6 are present in the
database the app actually serves **and** the company binding is resolvable;
otherwise they write `0` and name what is missing. Both are additive — an
existing `HEADQUARTERS_ENABLED` is preserved, so an operator's deliberate `0` is
never rotated back on by a routine update. A missing database or an unreadable
schema leaves the flag **unset** rather than guessed, and the startup script
reports `unset` as `unset`.

Schema failure blocks Headquarters writes and returns failed health. It does
**not** produce a deceptive empty office: the floor renders the setup state.

## 7. What this target does not authorize

* No new container, image, service, compose file, framework or dependency.
* No customer-facing rollout. Operator probe box first; client mutation needs an
  explicit fleet/client go.
* No database restore. Rollback switches to the previous tested code while
  retaining additive rows and every message written since the upgrade; restoring
  a stale backup over new writes is a separately authorized recovery operation.
* No provider, model, key or policy change, and no credential value in any log,
  report or transcript.

## 8. Verifying a box

The contract fixtures for this target ship with the two repositories and run
without Docker:

```sh
# onboarding repo
bash tests/unit/hq/B32/headquarters-docker.test.sh

# command center repo
bash tests/unit/hq/B32/headquarters-docker-capability.test.sh
```

They execute the real startup script (fake `node`/`pm2`, temp `OPENCLAW_DATA`)
and the real capability functions (temp database), and assert: persistent roots
created and preserved across a re-run; resurrect sequenced; the extension
registered once, idempotently, with the operator's config block intact;
allowlist extended but never created; the flag written only on a proven
capability and preserved once set.

What they do **not** prove is a real container replacement with real customer
state. That is the integration proof (task T07), which must run against a
disposable local Docker fixture and record row counts/hashes across a recreate —
never inferred from these fixtures. If the Docker daemon is unavailable, the
honest report is BLOCKED with the evidence still needed, not a pass.
