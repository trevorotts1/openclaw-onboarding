# Property-Data Provider Abstraction (Skill 39)

Skill 39 NEVER fabricates property data. Every property fact comes from a named
provider the operator has configured. This reference documents the capability →
provider abstraction and how to supply each key. Keys are OPTIONAL and
operator-supplied; the skill ships ZERO keys and ZERO scraped data.

`scripts/02-configure-providers.sh` scans the operator's standard env locations,
records which capabilities are AVAILABLE vs an HONEST GAP, and writes
`<MASTER_FILES_DIR>/.skill-39-provider-status.json`. The runtime
(`scripts/property-lookup.sh`) reads that status and either tells the agent to
issue the provider request, or returns the honest-gap line.

## Capabilities and accepted env keys

| Capability | What it answers | Accepted env var(s) | Notes |
|---|---|---|---|
| `property_lookup` | listing facts (beds/baths, sqft, status, est. value) | `RENTSPREE_API_KEY`, `RAPIDAPI_ZILLOW_KEY`, `PROPERTY_API_KEY` | Zillow has no fully-open public API; most operators use a RapidAPI bridge or RentSpree. **Honor each provider's ToS.** |
| `mls` | authoritative listing + showing instructions | `RESO_WEB_API_TOKEN`, `MLS_API_TOKEN`, `IDX_API_KEY` | MLS/IDX access is **licensed per-operator** (RESO Web API / IDX vendor). The skill documents the contract; the operator supplies the licensed token. |
| `geocode` | address → lat/long + normalization | `GOOGLE_GEOCODING_API_KEY`, `MAPBOX_TOKEN`, `GEOCODE_API_KEY` | Used to disambiguate addresses and anchor Street View. |
| `street_view` | exterior property image | `GOOGLE_STREET_VIEW_API_KEY`, `GOOGLE_MAPS_API_KEY` | Google Street View Static API. Image generation only — no synthetic/AI-faked exteriors. |
| `comps` | comparable sales for a CMA | `COMPS_API_KEY`, `ATTOM_API_KEY`, `PROPERTY_API_KEY` | Feeds the seller CMA. If absent → honest gap; offer a manual CMA. |

## How to add a provider key
Put the key in any of the operator's standard env locations (same set Skill 38
uses):
- `~/.openclaw/.env` / `~/.openclaw/secrets.env` / `~/.openclaw/openclaw.env`
- `<MASTER_FILES_DIR>/.env` / `<MASTER_FILES_DIR>/secrets.env`
- `~/.zshrc` / `~/.bashrc` / `~/.bash_profile`
- the running shell environment

Then re-run `scripts/02-configure-providers.sh` to refresh the status JSON.

## MVP honesty (what is REAL vs STUB)
- **REAL now:** provider abstraction, key discovery, capability status, address
  normalization (heuristic), and the F52 event emission. The lookup script prints
  the exact provider request shape per capability and the honest-gap line.
- **STUB / operator-supplied:** the actual network call to each provider is
  performed by the agent through its configured tool/MCP using the documented
  request shape — the skill does not bundle provider client code or keys. The
  Street View image is fetched by the agent via the documented Static API URL.
- This is intentional: a UNIVERSAL skill cannot ship licensed MLS access or paid
  property-data keys. It ships the contract + the honest-gap discipline.

## Street View image generation (request shape)
When `street_view` is AVAILABLE, the agent issues a Google Street View Static API
GET against the geocoded lat/long (or address) with the operator's key. Document:
`https://maps.googleapis.com/maps/api/streetview?size=600x400&location=<lat,lng>&key=<GOOGLE_STREET_VIEW_API_KEY>`.
The image is the REAL exterior; the agent never fakes or AI-generates a building.
