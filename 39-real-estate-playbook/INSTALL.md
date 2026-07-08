# Skill 39 — Real Estate Playbook & Property Intelligence: Install Guide

## What this installs

The real-estate VERTICAL on top of Skill 38 (Conversational AI System):

- **Property intelligence** — a provider abstraction (`lib-property.sh`) for geocoding (keyless US Census + optional Google/Mapbox), property lookup, comps, and Street View imagery. All provider keys are OPERATOR-SUPPLIED via env; absence is an honest gap, never fabricated data.
- **Buyer + seller qualification** question sets (timeline/financing/neighborhood/must-haves; motivation/timeline/price/occupancy).
- **Showing scheduler** (lockbox / MLS-rules config + protocol).
- **State disclosure compliance** — a 50-state + DC pointer matrix (where to look; NOT legal advice).
- **Lead routing by agent specialty** + fair-housing guardrails.
- **Open-house automation** + **pre-foreclosure outreach** playbooks (the latter pairs with Skill 40).
- **Sales-Brain RE extension** — an ADDITIVE drop-in into the installed Skill 38 (RE objection patterns, CMA pricing-reveal timing, SPICED-RE) that never edits Skill 38's own protocol.
- A `real-estate-events.jsonl` append-only event log per the F52 master-files contract.

## Prerequisites (ALL required unless marked optional)

This skill REFUSES to proceed until the mandatory prerequisites pass (`00-verify-prerequisites.sh`).

1. **Skill 38 — Conversational AI System** — installed. Skill 39 is the RE vertical on top of it.
2. **`MASTER_FILES_DIR`** — resolvable (Skill 38 Step O.2 persists it). The event log lives there.
3. **`jq`** on PATH — scripts parse provider JSON + append events.
4. **`curl`** on PATH — geocode / provider / Street View HTTP calls.

### Provider keys (OPTIONAL — honest gap without them)

| Env var | Enables | Without it |
|---|---|---|
| `GOOGLE_MAPS_API_KEY` | Geocoding (precise) + Street View imagery | Census geocoder still works (keyless); no Street View |
| `MAPBOX_TOKEN` | Alternative geocoding | Census geocoder still works |
| `RENTCAST_API_KEY` (example) | Property lookup + comps (one example provider) | Lookup/comps return honest `available:false` |
| RESO/MLS Web API token | MLS-adjacent property + comps | Lookup/comps return honest `available:false` |

Skill 39 ships the provider ABSTRACTION + example adapter stubs. The operator wires their own licensed provider — Skill 39 ships zero keys and no MLS credentials.

## What this does NOT do

- Does NOT install or modify Skill 38's own protocol files. The RE Sales-Brain layer is an ADDITIVE new file + one AGENTS.md pointer line.
- Does NOT fabricate property data — ever. No provider → honest gap + operator-supplied-key path.
- Does NOT scrape public records. Pre-foreclosure data comes from Skill 40.
- Does NOT give legal/lending/fiduciary/appraisal advice; disclosure compliance is a pointer matrix.
- Does NOT ship any provider API key or MLS credential.

## Install order (run in this order; each is idempotent)

```bash
cd ~/.openclaw/skills/39-real-estate-playbook/scripts

./00-verify-prerequisites.sh           # Skill 38 present, MASTER_FILES_DIR, jq, curl; provider-key report
./01-locate-master-files-folder.sh     # reuse Skill 38's MASTER_FILES_DIR selection (or resolve it)
./02-configure-providers.sh            # record which providers are keyed; honest-gap summary
./03-init-real-estate-events-log.sh    # create real-estate-events.jsonl + .schema.json sidecar
./04-install-qualification-scripts.sh  # buyer + seller qualification templates into master files
./05-install-sales-brain-extension.sh  # ADDITIVE RE Sales-Brain drop-in into installed Skill 38
./06-scaffold-showing-scheduler.sh     # showing-scheduler state + lockbox/MLS-rules config
./07-register-crons.sh                 # open-house follow-up + post-close anniversary scan
./08-update-core-files.sh              # AGENTS.md / MEMORY.md / TOOLS.md pointers (idempotent markers)
```

After scripts run, follow INSTRUCTIONS.md for the runtime flows (property lookup, qualification, showings, routing, pre-foreclosure outreach) and the `real-estate-events.jsonl` schema.

## OS support

`darwin` (Mac mini operators) and `linux` (VPS operators). All scripts detect OS at runtime via `uname -s`:

- **Darwin:** `$HOME/.openclaw/skills`
- **Linux:** `/data/.openclaw/skills`

## QC gates shipped with this skill

```bash
bash scripts/qc-no-personal-data.sh   # UNIVERSAL: zero client/personal identifiers
bash scripts/qc-no-fabrication.sh     # no script returns invented data on a provider miss
bash scripts/qc-fair-housing.sh       # CODED fair-housing gate (fail-closed; no protected-class field)
```

Both must PASS before the skill is considered installed cleanly (per `../QC-PROTOCOL.md` Rule 5).

## Where to read next

- `INSTRUCTIONS.md` — runtime flows + the `real-estate-events.jsonl` schema
- `references/property-provider-abstraction.md` — the provider contract (add/swap a provider)
- `references/sales-brain-real-estate-extension.md` — the additive RE Sales-Brain extension source
- `references/state-disclosure-matrix.md` — 50-state + DC disclosure pointers
