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
- **RUN_AUTHORIZATION_REQUIRED.** No valid purpose-bound run grant
  covers this run. Show the preview (scope, budget, validity window)
  and wait for the client's decision. Never self-approve, and never
  widen an existing grant to cover a new purpose.

## Common situations

**The council disappeared after an update.** It did not: update sync
replaces the skill folder, and council state never lived there. Check
the authoritative store for the installation's mode (Command Center
database, or the per-user council database outside the skills tree).
If sessions are missing there, that is a data-store issue in the
owning app, not a skill-folder issue.

**A seat shows no sources.** Its pack is not built or its anchors are
not yet obtained and verified. The honest states are recorded in
advisors/<seat-id>/sources.json and coverage.json. Do not fill the gap
with plausible-sounding material.

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
