# Council Install Matrix Reference

Which installation shapes support which council modes, and the precise
not-ready states when they do not.

## Prerequisite classes

- **Install:** supported host runtime, writable per-user prefix,
  verified bundle, correct schema, core, and source-pack versions.
- **Run:** valid client scope, approved source packs, a selected
  functioning route, a data store, sufficient context and capacity, and
  the Council service running (built and started by the skill's wire.sh).
- **Client access:** the client's own address
  `https://<slug>-council.zerohumanworkforce.com` published behind
  Cloudflare Access by the operator step
  `scripts/provision-council-access.sh --all --apply`.
- **Managed visual mode (optional):** compatible Command Center,
  authenticated pairing and scope, council migration applied through the
  Command Center, job and event integration, UI assets. The standalone
  Roast Room chamber does not need any of this.
- **Knowledge authoring only:** Skill 22 extractors and authorized
  source content. A client install never needs these merely to consult
  prebuilt packs.

Installed means usable: a box is done when
`bash scripts/verify-council-box.sh` ends with `COUNCIL_BOX: READY`.

## Matrix: one row per platform

All platforms share the same layout: releases and receipts in
`$OPENCLAW_ROOT/council-runtime` (`active.json`, `service.json`,
`bin/council-service`, `bin/blackceo-council`), durable data in
`$OPENCLAW_ROOT/council-data`, loopback port 8787. `$OPENCLAW_ROOT` is the
environment value, else `/data/.openclaw`, else `~/.openclaw`. The service
runs from the immutable release as
`<node> <release>/node_modules/tsx/dist/cli.mjs <release>/scripts/service-launch.mjs`.

| Platform | Service manager | Public access | Status |
|---|---|---|---|
| Mac (fleet-mac) | LaunchAgent `ai.blackceo.council-service`, started by wire.sh, restarts on update and reboot | The box's one tunnel publishes `https://<slug>-council.zerohumanworkforce.com` behind Access (operator step) | Supported. A Mac with no logged-in GUI session reports `COUNCIL_WIRE: DEFERRED_NO_GUI` and finishes on a later roll |
| Hostinger VPS (fleet-hostinger) | pm2 app `council-of-wise-elders` inside the container; the tunnel connector runs inside the container as a pm2 app named cloudflared | Same address, same Access gate | Supported once the connector runs in the container; otherwise DEGRADED TUNNEL_NOT_IN_CONTAINER |
| Contabo container (fleet-contabo) | pm2 app `council-of-wise-elders` inside the container | The connector today runs on the host, and a host-side connector cannot reach the container's loopback | Service supported; public access pending a connector inside the container. Verifier reports DEGRADED TUNNEL_NOT_IN_CONTAINER |
| Standalone, no Command Center | Same as the platform above | Same | The supported shape for any box without a council-capable Command Center; managed visual mode is never promised |

## COUNCIL_WIRE codes (printed by wire.sh during the roll)

Result lines:

| Line | Meaning | Fix |
|---|---|---|
| `COUNCIL_WIRE: READY` | Built, started and healthy | None. Run the verifier |
| `COUNCIL_WIRE: NOOP` | Release and service already current; nothing changed | None |
| `COUNCIL_WIRE: ADOPTED_EXISTING` | A healthy Council service already on the port was adopted instead of replaced | None. Run the verifier |
| `COUNCIL_WIRE: DEFERRED_NO_GUI` | Mac with no logged-in GUI session, so the LaunchAgent cannot load yet | Have the client log in to the Mac, then re-roll |
| `COUNCIL_WIRE: NOT_READY <code>` | Not built or not running; the code says why | See below |

Not-ready codes:

| Code | Cause | Fix |
|---|---|---|
| `NODE_TOO_OLD` | Node.js is older than 22.13 (or not 24+), so built-in SQLite is missing | Provide the box's managed Node 22.13+ or 24+, then re-roll |
| `NO_NPM` | npm is not on PATH, so the pinned install cannot run | Install a Node distribution that includes npm, then re-roll |
| `NO_PM2` | VPS box without pm2 | Install pm2 in the container the way the box's other services are managed, then re-roll |
| `RUNNING_AS_ROOT` | wire.sh was run as root where the service must belong to the client's own user | Run the roll as the client's user |
| `PORT_IN_USE` | Something other than the Council service holds port 8787 | Find the holder with `lsof -nP -iTCP:8787 -sTCP:LISTEN`, decide with the operator, then re-roll. Never kill an unknown process blindly |
| `SERVICE_UNHEALTHY` | The service started but `/status` did not answer in time | Read the service log (pm2 logs or the LaunchAgent log), fix the cause, re-roll |
| `RUNTIME_BUILD_FAILED` | `install-runtime.mjs` failed (network for `npm ci`, disk space, build error) | Read its last `FAIL` line, fix the cause, re-roll. The previous release stays active |
| `UNSUPPORTED_PLATFORM` | Neither a supported Mac nor a Linux container | Report to the operator; the Council service is not wired here |

## COUNCIL_BOX codes (printed by scripts/verify-council-box.sh)

Last line: `COUNCIL_BOX: READY|DEGRADED|NOT_READY <codes>`. Exit 0 for READY
or DEGRADED, 1 for NOT_READY, 2 when the verifier itself could not run
(unresolvable node or curl, unreadable receipt). The verifier is
read-only and checks, in this order:

| Code | State | What was checked | Fix |
|---|---|---|---|
| `RUNTIME_MISSING` | NOT_READY | `council-runtime/active.json` exists | wire.sh has not built a release: re-roll and read the COUNCIL_WIRE line |
| `RELEASE_UNVERIFIED` | NOT_READY | `<node> install-runtime.mjs --verify-release <releasePath> --prefix <council-runtime>` passes | The release is damaged or tampered with: re-roll to rebuild; never hand-edit a release |
| `SERVICE_NOT_REGISTERED` | NOT_READY | `service.json` exists and the manager shows the job running (`launchctl print gui/<uid>/ai.blackceo.council-service`, or `pm2 jlist` for `council-of-wise-elders`) | Re-roll; on Mac make sure the client is logged in; on VPS make sure pm2 runs |
| `SERVICE_DOWN` | NOT_READY | `GET http://127.0.0.1:<port>/status` answers | Restart through the manager (kickstart the LaunchAgent, or pm2 restart), then read the service log |
| `NO_USABLE_ROUTE` | NOT_READY | `GET /api/council/routes` lists at least one usable route (ids and usable flags are printed) | The client's own model route is not usable (for example claude-nine or claude-configured is not set up). The client or operator fixes the route; never change client credentials, models or sovereignty to get past it |
| `ACCESS_GATE_OPEN` | NOT_READY | `GET <public_origin>/status` without following redirects answered 2xx, or redirected to its own host | Security failure: the address works with no sign-in. Do not send any chamber link. The operator removes the council hostname route or repairs its Access app, then re-runs `provision-council-access.sh --apply` |
| `CLI_SHIM_MISSING` | DEGRADED | `blackceo-council` on PATH, else `council-runtime/bin/blackceo-council` | Re-roll; meanwhile call the absolute path |
| `PUBLIC_ORIGIN_UNSET` | DEGRADED | `public_origin` in `service.json` is not null | Operator runs `provision-council-access.sh --all --apply`. Until then tell the client the chamber link is not ready; never send a 127.0.0.1 link |
| `ACCESS_GATE_MISSING` | DEGRADED | `GET <public_origin>/status` is a 3xx to `*.cloudflareaccess.com` | The address did not answer or redirects elsewhere: operator checks the tunnel route and Access app, re-runs `provision-council-access.sh --apply` |
| `TUNNEL_NOT_IN_CONTAINER` | DEGRADED | VPS only: `pm2 jlist` lists a cloudflared app | A host-side connector cannot reach the container's loopback. Run the connector inside the container as a pm2 app named cloudflared (Contabo: pending) |

## Precise not-ready states (use these words)

- **Runtime payload missing at the installed location:** "The council
  runtime is not present at the installed location. The skill is
  installed and registered; deliberation is not available."
  Diagnostic state: FEATURE_NOT_READY. (The runtime ships in this
  package; this state names an install whose payload is absent or
  failed its doctor, never the package itself.)
- **Managed mode (optional; the standalone chamber does not need it):**
  the Command Center pinned for this onboarding
  release (see cc-compat.json, currently v7.6.112) carries no council
  contract, migration, or UI. A council-capable Command Center exists
  in this release's own cohort and is negotiated through the
  compatibility manifest, but managed mode is not ready on any box
  until that Command Center release is actually installed there. The
  portable skill still installs and registers; never tell a client
  the visual experience is ready before then.
- **Source coverage:** all nine packs ship in this package at
  bibliographic_only coverage. A seat abstains on any source-grounded
  claim its recorded coverage does not support. A council never
  convenes a partial fake roster.

## State locations by mode

- Managed: the Command Center database is authoritative.
- Standalone: the per-user council SQLite database lives outside the
  skills tree, in `$OPENCLAW_ROOT/council-data`.
- Never: inside 77-council-of-wise-elders/, because update sync
  replaces skill folders wholesale.

## Preservation guarantees

An install or update of this skill never mutates 76-local-embedder,
memory providers, embedding settings, global model defaults, or any
unrelated skill. The updater's box-state allow-list needs no entry for
this skill, because there is no skill-folder state to preserve.
