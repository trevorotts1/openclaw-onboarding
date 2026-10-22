# Council of Wise Elders (Skill 77): Installation Guide

> Teach Yourself Protocol first: before any action in this skill, the
> installing agent must have completed Skill 01 (Teach Yourself Protocol)
> and Skill 02 (Back Yourself Up Protocol), and must read every .md file in
> this folder before touching the system (INSTALL-CONTRACT.md Rules 1, 2
> and 14). Acknowledge the contract for this skill in the work log:
> "INSTALL-CONTRACT.md acknowledged for skill 77-council-of-wise-elders.
> Proceeding with INSTALL.md step order."

Follow these steps in this exact order. Do not skip, reorder, or combine
steps. The order is the onboarding installer contract order: preflight,
backup, verified copy, runtime build and service (wire.sh), registry and core
update, nonsecret configuration, migrations through the owning app,
offline QC, permitted live acceptance, release receipt.

## Prerequisites

See PREREQS.json for the machine-readable mirror of this section.

Required to install: a supported host runtime (Node.js 18 or newer for the
skill's own scripts), a writable per-user installation prefix, the verified
skill bundle, and correct schema, core, and source-pack versions once the
runtime and packs land.

Required to run: a valid client scope, approved source packs, a selected
functioning route, a data store, and sufficient context and capacity. The
runtime itself needs Node.js 22.13 or newer (or 24+) with built-in SQLite;
wire.sh checks this and reports NODE_TOO_OLD when it is not met.

Installed means usable. A box counts as installed only when the Council
service is running from a verified release AND the client has a signed-in
way to open the Roast Room chamber. Copying the skill folder is only the
first step; Step 4 (wire.sh) builds and starts the service, the client's
Council address is published automatically (see Client access below), and
`scripts/verify-council-box.sh` is the proof.

Optional, for the Command Center managed visual mode only: a compatible
Command Center, an authenticated pairing and scope, the council migration
applied through the Command Center, job and event integration, and UI
assets. The standalone Roast Room chamber does NOT need any of this: it is
served by the Council service itself and opened at the client's own
council address (see Client access). No Command Center release carrying
the managed council contract exists yet; see references/install-matrix.md
for the precise not-ready state. An older Command Center may receive this
portable skill but must not be told the managed visual mode is ready.

Required only for new knowledge authoring: the relevant Skill 22
extractors and authorized source content. A client install does NOT need
Calibre or transcription packages merely to consult prebuilt advisor
packs.

## Step 1: Preflight

1. Confirm slot 77 is free or already this feature: the skills directory
   contains no other 77-* folder. If an unrelated feature occupies slot
   77, STOP and report the collision. Never overwrite it and never
   silently choose slot 78.
2. Confirm 76-local-embedder is present and record that it must remain
   byte-untouched by this install. This skill never rewrites memory
   providers, embedding settings, or Skill 76 for any reason. An
   unavailable optional embedding service is never a reason to touch it.
3. Confirm Node.js 18 or newer: `node --version`.
4. Confirm the installation prefix is writable: $HOME/.openclaw/skills on
   Mac, /data/.openclaw/skills on VPS.
5. Record the slot 77 discovery expectation: the installer's glob
   discovery (install.sh discover_skills) counts this folder
   automatically; there is no second discovery list to edit.
6. Choose and record the authority mode for this installation, managed
   (Command Center database is authoritative) or standalone (per-user
   local council database). Record it OUTSIDE the skill folder (managed:
   in the Command Center; standalone: in the per-user council data
   profile). Never store it inside the skill folder, and never switch it
   silently later.

## Step 2: Backup

Back up before writing, using the mechanism already running the install:

- Fresh install.sh run: the installer's own backup behavior applies.
- Update roll (update-skills.sh): the updater snapshots or backs up the
  installed skills tree before the sync; do not bypass it.
- Manual install: copy the existing installed skills directory to a
  dated backup OUTSIDE every skills and config root, so an old SKILL.md
  copy can never register as a phantom skill.

Council state is never inside the skill folder (see SKILL.md), so a
correct backup of the skills tree never contains council sessions, and a
restore never resurrects stale council state.

## Step 3: Verified copy

1. Copy 77-council-of-wise-elders/ into the skills directory as a whole
   folder (never copy the folder's contents flat into the skills root).
2. Verify the copy against the source: run
   `node scripts/doctor.mjs --root <installed-folder>` from the installed
   folder (Step 8 runs the full QC; this is the copy check). The doctor
   verifies the file inventory, the frontmatter name
   council-of-wise-elders, agreement between the version file,
   skill-version.txt, and the SKILL.md frontmatter version, and that no
   state files are present inside the folder.
3. When a generated manifest.json is present in the package, run
   `node scripts/verify-bundles.mjs --root <installed-folder>` and
   require the aggregate tree hash to match the manifest. A mismatch
   stops the install; do not hand-patch the installed tree.
4. If you extracted a `.skill` archive instead of copying the full source folder,
   add `--distribution` to both commands. This explicitly verifies extracted
   content without requiring the archive to contain itself. For the Step 8
   shell QC command, also pass `--distribution`. The default source mode
   requires the distributable archive and its SHA-256. Never select the mode
   from the manifest status, and never use distribution mode to certify a
   source release. These checks prove file consistency, not publisher identity.

## Step 4: Runtime build and service (wire.sh does this; nobody hand-runs npm)

The fleet roll runs `77-council-of-wise-elders/wire.sh` (update-skills.sh
runs a skill's wire.sh first). Do not run npm, tsx or install-runtime.mjs by
hand to "finish" an install: no roll can satisfy a manual step, and a
hand-built tree drifts from the verified release. wire.sh is idempotent and
does the whole job:

1. Resolves OPENCLAW_ROOT: `$OPENCLAW_ROOT`, else `/data/.openclaw`, else
   `~/.openclaw`.
2. Builds the runtime into an immutable release under
   `$OPENCLAW_ROOT/council-runtime` (it runs `scripts/install-runtime.mjs`:
   Node and SQLite preflight, pinned `npm ci`, build, receipts, then an
   atomic switch of `active.json`). The skill folder is never built in
   place. Durable council data lives in `$OPENCLAW_ROOT/council-data`,
   outside every replaceable tree.
3. Registers and starts the service on loopback port 8787 and keeps it
   running across updates and reboots: Mac uses the LaunchAgent
   `ai.blackceo.council-service`; VPS uses the pm2 app
   `council-of-wise-elders` inside the container. The service runs from the
   immutable release as
   `<node> <release>/node_modules/tsx/dist/cli.mjs <release>/scripts/service-launch.mjs`.
4. Writes `council-runtime/service.json` (port, origin, public_origin or
   null, manager launchd, pm2 or external, name, release id), plus the
   launcher `council-runtime/bin/council-service` and the command line tool
   `council-runtime/bin/blackceo-council`.
5. Prints one result line, `COUNCIL_WIRE: READY`, `NOOP`, `ADOPTED_EXISTING`,
   `DEFERRED_NO_GUI` or `NOT_READY <code>`. The codes (NODE_TOO_OLD, NO_NPM,
   NO_PM2, RUNNING_AS_ROOT, PORT_IN_USE, SERVICE_UNHEALTHY,
   RUNTIME_BUILD_FAILED, UNSUPPORTED_PLATFORM) and their fixes are in
   references/install-matrix.md. A NOT_READY line is a precise state to
   report, never a reason to simulate a council.

wire.sh never touches client credentials, model defaults or route
selection. The client's route choice (including claude-nine and
claude-configured, not only DeepSeek) is read at convene time.

## Step 5: Registry and core update

All registry entries for this skill ship in the repository; the install
verifies them, it does not create local copies:

1. Discovery: confirm the installer glob counts the folder (Step 1,
   item 5). Verify with the discovery count, not with a new list.
2. Wave roster: confirm lib-onboarding-state.sh OC_WAVE6_SKILLS contains
   77-council-of-wise-elders exactly once. The wave goal check treats the
   skill like every other gated extension skill.
3. Capability map: confirm 23-ai-workforce-blueprint/
   skill-department-map.json carries the skill 77 entry. The council is a
   company-level capability invoked through the AI CEO front door, not a
   department-owned skill, so the entry is registered as platform-owned
   with no department intent triggers; department bindings arrive with
   the runtime units.
4. Core update: apply CORE_UPDATES.md through the existing idempotent
   core-update merger (update-skills.sh wire_core_updates). It adds one
   labeled AGENTS.md section and stamps the sentinel
   <!-- skill:77-council-of-wise-elders:core-update-applied -->. Never
   overwrite the whole AGENTS.md, SOUL.md, or TOOLS.md, and never paste
   the block by hand.
5. Advisory SOP: the Council deliberation SOP ships at universal-sops/
   SOP-COUNCIL-01-COUNCIL-OF-WISE-ELDERS-DELIBERATION.md and is verified
   against universal-sops/_content-manifest.json. The chair governance
   persona is process governance, not a tenth advisor; its company
   binding is created by the company-aware workforce mechanism only when
   a real company context exists. Do not fabricate a completed interview
   or fictitious business facts to force the binding.

## Step 6: Nonsecret configuration

1. config/defaults.json and config/advisors.json are reference copies of
   the shipped defaults and the fixed nine-seat roster. The runtime reads
   its effective configuration from the authoritative store for the
   chosen mode, never from mutable state inside this folder.
2. No secret is configured by this skill. Provider credentials resolve
   through the box's existing credential stores at run time; never write
   a credential into this folder, into config files here, or into a
   council brief.
3. Confirm the recorded authority mode (Step 1, item 6) matches the
   installation's intent.

## Step 7: Migrations through the owning app

This skill owns no database and runs no migration. In managed mode the
council tables are created by the Command Center's own migration path
when the compatible Command Center release is installed; the onboarding
installer must never migrate a managed Command Center database behind
its back. In standalone mode the local council database is created by
the runtime on first use in `$OPENCLAW_ROOT/council-data`, outside the
skills tree. The managed
council migration number remains unallocated in this release (the
compatibility negotiation surfaces it as the MIGRATION_ID_UNALLOCATED
advisory); the correct receipt entry states exactly which migrations
ran, or that none did, and never claims a number that does not exist.

## Step 8: Offline QC

From the INSTALLED folder (not only the source tree):

1. Run `bash scripts/qc-council-of-wise-elders.sh`. It must exit 0.
2. Score QC.md honestly against its rubric. 8.5 of 10 or better is a
   pass; below that, loop on the specific failed items (maximum 5 loops,
   then escalate). The installer who runs this QC is never the agent
   that performed the install (no self-QC).

Then prove the box can actually be used. Run, read-only, on the box:

    bash scripts/verify-council-box.sh

Its last line is `COUNCIL_BOX: READY`, `DEGRADED <codes>` or
`NOT_READY <codes>` (exit 0, 0, 1; exit 2 means the verifier itself could
not run). It checks, in order: the release receipt, the release hash, the
service registration (LaunchAgent or pm2), the local `/status`, a usable
model route, the `blackceo-council` command, the public address and its
Cloudflare Access sign-in gate, and (VPS) a tunnel connector inside the
container. Every code and its fix is in references/install-matrix.md.
READY is the only state that means the client can use the Council today.

## Step 9: Permitted live acceptance

Only with a real client-selected route:

- The runtime and all nine advisor packs are built and ship in this
  package. Live acceptance convenes one bounded council on a
  synthetic, unmistakably labeled fixture decision through the
  installed runtime (convening is the approval; there is no separate
  approval step), and verifies the full report order in
  references/report-template.md and the saved session readback.
- Without a live route, record the installation as
  INSTALLED_NOT_LIVE_VERIFIED: installed and offline-verified, live
  unverified. Never simulate a session or invent a verdict to fill
  the gap.
- The not-ready report is still the correct result wherever a named
  prerequisite is actually missing (no client-selected route, or a
  COUNCIL_WIRE / COUNCIL_BOX code from Step 4 or Step 8);
  it names the missing prerequisite precisely rather than claiming
  the council itself is unbuilt.
- The agent convenes with `blackceo-council` (or
  `$OPENCLAW_ROOT/council-runtime/bin/blackceo-council` when it is not on
  PATH) and sends the client the `chamber_url` when the command prints one.
  When it prints none, the agent never invents or guesses a link and never
  sends a 127.0.0.1 link (that address only works on the box itself); it
  tells the client the Council runs, the result will be shared, and their
  private Council link is still being set up.

## Step 10: Release receipt

Record, in the install work log or the box's onboarding state:

- Discovery of slot 77 and the installed path.
- Source, core, and pack hashes (the tree aggregate and archive hash
  recorded in manifest.json; all nine packs ship in this package).
- The COUNCIL_WIRE line from the roll and the COUNCIL_BOX line from
  `scripts/verify-council-box.sh`.
- Whether the managed Command Center mode is available (optional), or the
  precise not-ready state from references/install-matrix.md.
- The registered capability identity (council-of-wise-elders), the SOP
  ID (SOP-COUNCIL-01), and the governance persona binding state
  (deferred until a real company context exists).
- The current scope and authority mode.
- That the client's route selection and model defaults were preserved,
  and that Skill 76 and unrelated skills were not mutated.
- The QC results from the actual installed location.

## Update flow

Existing clients receive this skill through the usual update process
without repeating the company interview. The updater backs up, then
replaces the skill folder wholesale; that is safe for the council
precisely because no council state lives inside the folder. Saved names,
goals, permissions, routes, history, and unrelated skills are preserved
by keeping them where they already live: outside this folder. A
standard-company placeholder is not evidence of actual revenue, cash,
mission, or customer demand, and council intake must keep unconfirmed
scaffold data separate from client-confirmed facts.

## Client access (automatic)

The client opens the Roast Room chamber at
`https://<slug>-council.zerohumanworkforce.com`, where `<slug>` is the
first label of their Command Center address, and signs in with the same
email addresses that sign in to their Command Center. The address rides the
box's existing Cloudflare tunnel (or the box's own dedicated `council-<slug>`
tunnel when the Command Center tunnel is local-managed or the Command Center
runs inside a container) behind a Cloudflare Access application
that copies the Command Center's allow-list and then follows its email list:
when an email is added to or removed from the Command Center login page, the
next run adds it to or removes it from the Council login page (`SYNCED`,
counts only), editing only the Council app's own allow policy, keeping its
other rules, and reading it back. The Command Center app is never edited by
that step. It refuses (`FAILED`, zero writes) when the Council app is not
`Council - <slug>` on `<slug>-council.<zone>`, when an email to remove sits
on a reusable or non-allow policy, or when either app's allow rules hold
something other than emails and service tokens (everyone, an email domain, a
group), or when the two apps' exclude/require rules differ (a revocation by
exclude on the Command Center page is never silently missed).

Nobody does anything to get it, for existing clients and for every client
added later:

- Every client has a Command Center from install (it ships first, locked to
  the interview until closeout), so every client gets an address whether or
  not the AI Workforce Interview is finished. Nothing in this path reads the
  interview or `.workforce-build-state.json`.
- An operator-side job, `scripts/council-access-autoprovision.sh`, runs every
  30 minutes on the operator Mac. It finds every Command Center from the
  Cloudflare zone and publishes any missing Council address, so a new
  client has one within about 30 minutes of their Command Center existing.
  It is idempotent, writes nothing on any client box, and is never run on
  a client box or by a client.
- The box resolves its address each time `blackceo-council convene` runs and
  uses it only when it answers with a Cloudflare Access sign-in. The first
  council after the address exists prints `chamber_url =
  <public_origin>/chamber/#session=<id>`: no roll, no `wire.sh` re-run, no
  manual step.

### Command Center login pages (operator side)

Step 1 of that job, `scripts/ensure-cc-access.sh`, keeps every client's
Command Center login page (its Cloudflare Access application) letting in
the operator emails and every verified client email, so the client can sign
in with Google or a one-time PIN:

- A Command Center with no login page gets one (`CREATED`), only once a
  verified client email is known; otherwise `NEEDS_EMAIL`, retried every run.
- An existing login page gets each missing operator or client email added
  to its allow policy (`RECONCILED`). Additive only: every existing rule
  (emails, service tokens, anything else) is kept in place and in order,
  nothing is removed, and the policy is read back to prove it. Nothing to
  add is `ALREADY_PRESENT` with zero writes. A page that admits everyone,
  has no allow policy, or uses a reusable (shared) allow policy is `DRIFT`:
  reported, never edited.
- Client emails are found by the automation, not asked for: the emails
  file, the non-operator emails already on the client's own login page and
  on its `rescue-<slug>` page, and a read-only GoHighLevel (Convert and
  Flow) lookup in the Black CEO LLC location (`scripts/ghl-client-emails.py`):
  contacts carrying one of those emails, or whose company name is the host
  name read as a business name, plus the same person's duplicate contacts
  (same full name and same phone). Never a one-word host name (often a
  first name) and never a company that is only the contact's own name.
  Two different people matched, or a nameless contact among several, is
  `ambiguous` and adds nothing.

The emails file is `~/.claude/state/council-elders/cc-access-emails.json`
(override `COUNCIL_CC_EMAILS_FILE`), every key optional:

```json
{"operator": ["<operator email>"],
 "clients": {"<host-slug>": ["<client email>"]},
 "ghl": {"location_id": "<Black CEO LLC location id>"}}
```

The GoHighLevel token is `GOHIGHLEVEL_API_KEY`, parsed (never sourced) from
`~/.openclaw/secrets/.env`, then `~/.openclaw/.env`. The location id comes
from `COUNCIL_GHL_LOCATION_ID`, else `ghl.location_id` above; the location
variables in the env files name a different location, so it is never taken
from them. With no token or no location id the lookup is skipped and the run
prints one line, `ghl: skipped (no credentials/location)`. Emails are never
printed, logged or put in receipts: counts only.

Until then `verify-council-box.sh` reports DEGRADED PUBLIC_ORIGIN_UNSET and
the agent sends no chamber link: it tells the client plainly that the
Council runs, the result will be shared here, and their private Council
link is still being set up. It never invents a link, sends a local one, or
mentions scripts, fleet or Cloudflare to the client. If the verifier ever
reports ACCESS_GATE_OPEN, the address answers without a sign-in: treat it as
a security failure and do not send the link.

A box whose Command Center tunnel is local-managed first tries to ride the
client's own rescue tunnel on the same machine, exactly like a remote-managed
Command Center tunnel (the result line says `rides rescue tunnel <name>`; no
new tunnel, no token file, no connector delivery). It rides only when all of
these hold: the Command Center tunnel reports the host at
`http://localhost:4000` or `http://127.0.0.1:4000` (Contabo containers on
19003-19005 never match); exactly one tunnel is named `rescue-<slug>` (or
`rescue-<slug>-...`, the slug as a whole word); that tunnel is healthy,
remote-managed and has an `ssh://` rule for `rescue-<slug>.<zone>` itself
(so `rescue-<slug>-x`, another client's tunnel, is never ridden); the active connectors of both
tunnels report `origin_ip` sets that are non-empty and overlap (the same
machine); no `<slug>-council` record already points at another tunnel; and
`COUNCIL_TUNNEL_OVERRIDES` has no entry for the slug (trevor keeps
`council-desktop`). Otherwise it falls back to the dedicated tunnel below.

A Command Center record whose tunnel, or the tunnel's configuration, no
longer exists (HTTP 404, `Configuration for tunnel not found`, a deleted
tunnel) is an orphan: both `ensure-cc-access.sh` and
`provision-council-access.sh` report `SKIPPED_ORPHAN` (zero writes, exit 0,
named in the receipts). A transient read error (5xx, timeout, auth) stays
`FAILED`, and so does a tunnel that is healthy but whose configuration
cannot be read: a live tunnel is never an orphan.

Failing that, a box whose Command Center tunnel is local-managed (it cannot
take an API ingress rule) gets a dedicated remote-managed tunnel
`council-<slug>` from the operator side instead. No `<slug>-council` DNS record exists until that
tunnel has an active connector: the first `--apply` creates the tunnel, its
route, the Access app and the saved token and ends `CONNECTOR_PENDING` with
zero DNS writes; the first run that sees the connector creates the record
(`PROVISIONED`); a record whose connector is later gone is `CONNECTOR_DOWN`,
zero writes, nothing deleted. File contract: the connector token sits at
`$OPENCLAW_ROOT/secrets/tunnel-council.token`, mode 600, holding only the
token - the in-container path for container hosts (`OPENCLAW_ROOT` resolves
to `/data/.openclaw` or `~/.openclaw` as wire.sh does), the host path
`~/.openclaw/secrets/tunnel-council.token` for host-run connectors; the
`CONNECTOR_PENDING` line names both delivery paths. How it reaches the box
is an operator delivery step, never wire.sh,
which fetches nothing. When the file exists, wire.sh keeps
`cloudflared tunnel run --token-file <file>` running (Mac LaunchAgent
`ai.blackceo.council-tunnel`, VPS pm2 app `cloudflared-council`), restarts
it only when the file changes, never touches the Command Center connector,
never prints the token, and prints one `COUNCIL_CONNECTOR:` line
(`READY`, `NOOP`, `DEFERRED_NO_GUI`, or `NOT_READY` with `TOKEN_UNREADABLE`,
`NO_CLOUDFLARED` or `CONNECTOR_START_FAILED`). With no file it does nothing.
The verifier then reports the connector (DEGRADED COUNCIL_CONNECTOR_DOWN
when it is not running).

When the `<slug>-council` record already points at a healthy tunnel that
already routes the exact path-less rule
`<slug>-council.<zone> -> http://127.0.0.1:8787`
(equivalent loopback forms count; a path-scoped rule does not count), the host is ADOPTED by that tunnel:
`ALREADY_PROVISIONED` with the detail `Council address already wired via
tunnel <name>`, zero writes, and no dedicated tunnel is ever planned for it.
The `Council - <slug>` Access app and the edge 302 check still apply to the
adopted route. Only a record pointing at a tunnel with no such rule (a
genuinely foreign or broken claim), or at a dead or deleted tunnel, stays
`CONFLICT` and fails the run.

A remote-managed Command Center tunnel whose rule points at a private bridge
address (an IPv4 in 172.16.0.0/12, 10.0.0.0/8 or 192.168.0.0/16, or the
literal `host.docker.internal`, on the Command Center port) takes that same
dedicated tunnel path: the Council
never rides the Command Center tunnel (a connector on the host cannot reach
the container's loopback), `provision-council-access.sh` creates
`council-<slug>` remote-managed with the route
`<slug>-council -> http://127.0.0.1:8787`, saves the token operator side.
The private-bridge shape alone never proves a container: the in-container
wording (the connector must run INSIDE the client's container) fires only
with positive container evidence the operator side can gather -
`COUNCIL_CONTAINER_HOSTS` names the host (comma list of slugs, the explicit
operator override), or the tunnel's other ingress rules use a
container-bridge pattern. With no evidence the same dedicated path runs
unchanged and the message says the connector runs ON THE HOST; the
`CONNECTOR_PENDING` line always names both delivery paths (in-container
`$OPENCLAW_ROOT/secrets/tunnel-council.token`, host
`~/.openclaw/secrets/tunnel-council.token`, plus the operator-side saved
token). The DNS record still appears only after the connector is active, and the
Council login page still mirrors the Command Center's. Every other
non-loopback origin keeps the `ORIGIN_NOT_LOOPBACK` refusal; a bridge
origin on a non-Command-Center port is allowed only on the local-managed
path, never the remote-managed one.

## Front-door service launcher

`runtime/scripts/service-launch.mjs` is the launcher. wire.sh starts it from
the immutable release, never from the skill folder, as
`<node> <release>/node_modules/tsx/dist/cli.mjs <release>/scripts/service-launch.mjs`
(tsx is installed inside the release; plain `node` cannot load the
extensionless imports in the tsc `dist/` output). The launcher calls the
composition root `startCouncilService(...)`, never a bare
`CouncilFrontDoor`: a bare door leaves the event, admission and session
adapters unbound (events answer 501). It binds loopback only, defaults to
port 8787, takes the data directory from `COUNCIL_SERVICE_DATA_DIR`
(wire.sh sets it to `$OPENCLAW_ROOT/council-data`), logs one JSON object per
stdout line, and stops on SIGTERM or SIGINT.

## Restarts

A worker never restarts the gateway or the Command Center on its own.
If a restart is ever required, the master orchestrator checks active
work, coordinates the restart, and verifies health afterward.
