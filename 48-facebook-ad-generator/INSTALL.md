# Skill 48 — Installation (client box)

## Prerequisites
- `python3 >= 3.8` (the enforcement spine is stdlib-only).
- The Paid Advertisement department present with a live agent and a copy-capable seat.
- A Telegram topic for the two human pauses (pick-10, approve).
- The client's OWN keys (never the operator's):
  - `KIE_API_KEY` — image generation (the reused gpt-image adapter).
  - GoHighLevel LOCATION Private Integration Token with `medias.write` — image hosting
    (`GOHIGHLEVEL_API_KEY`/`GHL_API_KEY`) + the location id (`GHL_LOCATION_ID`).

## Steps
1. `bash 48-facebook-ad-generator/install.sh` — proves payload integrity, runs the
   enforcement self-test (sync + negative suite + Guard A), and runs install QC. It
   FAILS loudly on any defect.
2. `bash 48-facebook-ad-generator/preflight.sh` — confirms keys, agent, and ceiling.
3. `bash 48-facebook-ad-generator/verify-deps.sh` — proves the outside tools are present.

## Re-indexing — NONE (proven no-op)
Skill 48 ships ZERO new persona blueprints; it REUSES the 42 built authors. Installing
or updating a skill never runs the Gemini indexer (skill files are read by direct path).
There is nothing to re-index.

## Graceful degradation
If the box's Command Center predates the `POST /api/ad-campaigns` endpoint, the run files
ungrouped cards on the marketing board and logs it. If no Meta interest resolver/key
exists, targeting interests degrade to `flagged_unverified` so the package still ships.
