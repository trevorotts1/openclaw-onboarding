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
backup, verified copy, isolated dependency install, registry and core
update, nonsecret configuration, migrations through the owning app,
offline QC, permitted live acceptance, release receipt.

## Prerequisites

See PREREQS.json for the machine-readable mirror of this section.

Required to install: a supported host runtime (Node.js 18 or newer for the
skill's own scripts), a writable per-user installation prefix, the verified
skill bundle, and correct schema, core, and source-pack versions once the
runtime and packs land.

Required to run (later units, stated here so nobody mistakes an installed
scaffold for a working council): a valid client scope, approved source
packs, a selected functioning route, a data store, budget and permission,
and sufficient context and capacity.

Required for visual managed mode: a compatible Command Center, an
authenticated pairing and scope, the council migration applied through the
Command Center, job and event integration, and UI assets. No compatible
Command Center release exists yet; see references/install-matrix.md for
the precise not-ready state. An older Command Center may receive this
portable skill but must not be told the visual experience is ready.

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

## Step 4: Isolated dependency install

The complete runtime declares exact pinned dependencies in
runtime/package.json: zod for the contracts, and TypeScript, tsx,
esbuild, and @types/node for the build. Install them in isolation
inside runtime/ only and build the runtime:

    node scripts/install-runtime.mjs

The script derives the pinned package set from runtime/package.json
(every version must be an exact pin), runs the pinned install
(`npm install --no-save` with those exact versions, so neither
package.json nor the lockfile is rewritten), then runs the runtime
build (`npm run build`: tsc plus the esbuild CLI bundle) and verifies
that runtime/dist/ exists. Never install globally, never into another
skill's tree, and never copy a native binary built for a different OS
or architecture. A native module ABI mismatch fails the installation
precisely, with no data reset. The source repository tree itself is
never built in place; the build happens in the installed copy.

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
the runtime on first use, outside the skills tree. The managed
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

## Step 9: Permitted live acceptance

Only with explicit authorization, a real client-selected route, and a
recorded budget:

- The runtime and all nine advisor packs are built and ship in this
  package. Live acceptance convenes one bounded council on a
  synthetic, unmistakably labeled fixture decision through the
  installed runtime, under the run-authorization lifecycle (preview,
  approve, start), and verifies the full report order in
  references/report-template.md, the saved session readback, and the
  provider usage against the recorded budget.
- Without that authorization, record the installation as
  INSTALLED_NOT_LIVE_VERIFIED: installed and offline-verified, live
  unverified. Never simulate a session or invent a verdict to fill
  the gap.
- The not-ready report is still the correct result wherever a named
  prerequisite is actually missing (no client-selected route, no
  compatible Command Center release for managed mode, no run grant);
  it names the missing prerequisite precisely rather than claiming
  the council itself is unbuilt.

## Step 10: Release receipt

Record, in the install work log or the box's onboarding state:

- Discovery of slot 77 and the installed path.
- Source, core, and pack hashes (the tree aggregate and archive hash
  recorded in manifest.json; all nine packs ship in this package).
- The compatible Command Center version, or the precise not-ready state
  from references/install-matrix.md.
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

## Restarts

A worker never restarts the gateway or the Command Center on its own.
If a restart is ever required, the master orchestrator checks active
work, coordinates the restart, and verifies health afterward.
