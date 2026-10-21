# Council Troubleshooting Reference

## Diagnostic states

- **FEATURE_NOT_READY.** The capability resolved, but a required part
  is not built or not paired: the runtime, an advisor pack, or the
  managed Command Center contract. Report which part, in the words of
  install-matrix.md. Never work around this state by simulating
  output.
- **CONTEXT_TOO_SMALL.** The prepared brief plus the required pack
  context exceeds the selected route's usable context. Report the
  sizes involved and stop; do not silently truncate the brief or drop
  seats to make it fit.
- **RUN_AUTHORIZATION_REQUIRED.** The low-level command line was used
  directly without an internal run reference. This is not a question for
  the client and nothing needs their approval: the client's request to
  convene is the approval. Convene through the normal service path
  (SKILL.md step 4b) instead, and never ask the client to approve
  anything to get past this error.

- **COUNCIL_WIRE / COUNCIL_BOX codes.** wire.sh prints one
  `COUNCIL_WIRE:` line during the roll; `scripts/verify-council-box.sh`
  prints one `COUNCIL_BOX:` line on demand. Every code, its cause and its
  fix is tabulated in install-matrix.md. Short list:
  COUNCIL_WIRE READY, NOOP, ADOPTED_EXISTING, DEFERRED_NO_GUI, NOT_READY
  with NODE_TOO_OLD, NO_NPM, NO_PM2, RUNNING_AS_ROOT, PORT_IN_USE,
  SERVICE_UNHEALTHY, RUNTIME_BUILD_FAILED or UNSUPPORTED_PLATFORM;
  COUNCIL_BOX READY, DEGRADED or NOT_READY with RUNTIME_MISSING,
  RELEASE_UNVERIFIED, SERVICE_NOT_REGISTERED, SERVICE_DOWN,
  NO_USABLE_ROUTE, ACCESS_GATE_OPEN, CLI_SHIM_MISSING,
  PUBLIC_ORIGIN_UNSET, ACCESS_GATE_MISSING or TUNNEL_NOT_IN_CONTAINER.
  Report the code in plain words and never work around it by simulating
  a session.

## Common situations

**The client cannot open the chamber.** Run
`bash scripts/verify-council-box.sh` first. PUBLIC_ORIGIN_UNSET means the
box has no verified Council address yet. The address is published
automatically (an operator-side job runs every 30 minutes) and the box looks
for it each time a council is convened, so there is nothing to run: the
first council after it exists prints the `chamber_url`. If it is still
unset more than an hour after the client's Command Center existed, report
the `COUNCIL_BOX:` line to the operator. The client signs in at the
`chamber_url` the CLI prints with their Command Center emails; an email that is not on the Command Center allow-list is refused by
Cloudflare Access by design. Never build the address by hand and never send
a 127.0.0.1 link, which only opens on the box itself.

**The service is not running.** wire.sh owns it: the LaunchAgent
`ai.blackceo.council-service` on a Mac, the pm2 app `council-of-wise-elders`
on a VPS. Re-roll rather than starting it by hand. Do not run npm or tsx in
the skill folder; the service runs from the immutable release in
`$OPENCLAW_ROOT/council-runtime` and its data lives in
`$OPENCLAW_ROOT/council-data`.

**The council disappeared after an update.** It did not: update sync
replaces the skill folder, and council state never lived there. Check
the authoritative store for the installation's mode (Command Center
database, or the per-user council database outside the skills tree).
If sessions are missing there, that is a data-store issue in the
owning app, not a skill-folder issue.

**A seat shows no sources.** Its anchor works are absent from the
source library, or not yet obtained and verified. The honest states
are recorded in advisors/<seat-id>/sources.json and coverage.json.
Do not fill the gap with plausible-sounding material.

**The verdict has no GO-style label.** Coverage was below 80 percent
or a critical-domain abstention is unresolved. The report states which;
see scoring.md. This is the system working as designed.

**Skill 76 or embeddings broke after install.** This skill never
touches 76-local-embedder, memory providers, or embedding settings.
Check what else changed on the box before attributing the break to
this install, and never "repair" it by rewriting Skill 76.

**A cancel seems ignored.** A late provider response cannot resurrect
a cancelled session. If controls show cleanup pending, report that
exact state rather than success, and let the operation lease expire
(60-second TTL) before retrying the control.

## Repairs that are never allowed

- Deleting council state to fix an install.
- Resetting the box, the skills tree, or the Command Center database.
- Hand-editing files inside the installed skill folder (the tree is
  verified against its manifest; drift fails QC until the folder is
  reinstalled cleanly).
- Switching the authority mode silently because one store is
  unreachable.
