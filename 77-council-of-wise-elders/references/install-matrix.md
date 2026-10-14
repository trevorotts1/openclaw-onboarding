# Council Install Matrix Reference

Which installation shapes support which council modes, and the precise
not-ready states when they do not.

## Prerequisite classes

- **Install:** supported host runtime, writable per-user prefix,
  verified bundle, correct schema, core, and source-pack versions.
- **Run:** valid client scope, approved source packs, a selected
  functioning route, a data store, budget and permission, sufficient
  context and capacity.
- **Visual managed mode:** compatible Command Center, authenticated
  pairing and scope, council migration applied through the Command
  Center, job and event integration, UI assets.
- **Knowledge authoring only:** Skill 22 extractors and authorized
  source content. A client install never needs these merely to consult
  prebuilt packs.

## Matrix

| Shape | Portable skill | Standalone mode | Managed visual mode |
|---|---|---|---|
| Mac (fleet-mac) | Installs and registers | Available when the runtime lands; state in the per-user council database outside the skills tree | Requires a compatible Command Center on the box; see not-ready state below |
| Hostinger VPS (fleet-hostinger) | Installs and registers | Same as Mac | Same requirement |
| Contabo container (fleet-contabo) | Installs and registers | Same as Mac | Same requirement |
| Standalone, no Command Center | Installs and registers | The supported shape for this box | Not applicable; never promised |

## Precise not-ready states (use these words)

- **Runtime not built:** "The council runtime is not yet built. The
  skill is installed and registered; deliberation is not available."
  Diagnostic state: FEATURE_NOT_READY.
- **Managed mode:** the Command Center pinned for this onboarding
  release (see cc-compat.json, currently v7.6.112) carries no council
  contract, migration, or UI. Managed mode is therefore not ready on
  any box running the pinned release. The portable skill still
  installs and registers; never tell a client the visual experience
  is ready.
- **Source packs not built:** seats whose packs are not built abstain
  on source-grounded claims. A council with unbuilt packs does not
  convene a partial fake roster.

## State locations by mode

- Managed: the Command Center database is authoritative.
- Standalone: the per-user council SQLite database lives outside the
  skills tree (per-user data directory for the installation).
- Never: inside 77-council-of-wise-elders/, because update sync
  replaces skill folders wholesale.

## Preservation guarantees

An install or update of this skill never mutates 76-local-embedder,
memory providers, embedding settings, global model defaults, or any
unrelated skill. The updater's box-state allow-list needs no entry for
this skill, because there is no skill-folder state to preserve.
