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

## Street View image (server-side byte fetch — NEVER a keyed URL)

**The agent does not construct a Street View URL.** It calls the shipped
function, which keeps the key in-process and returns a LOCAL FILE PATH.

> This section previously documented the request shape as
> `https://maps.googleapis.com/maps/api/streetview?...&key=<KEY>` for the agent
> to issue itself. `scripts/lib-property.sh:143-148` records that this exact
> construction was deliberately removed from the implementation, because a keyed
> URL attached to a client conversation or written into the event log ships the
> raw credential with it. A hardened implementation that nothing routes to is not
> a fix, so the reference is now the contract the code implements.

**Entry point:** `streetview <lat,lon> [output-path]` in
`scripts/lib-property.sh`.

**Contract:**

1. **No key → honest gap.** With `GOOGLE_MAPS_API_KEY` unset the function returns
   `{"available":false,"source":"none","reason":"GOOGLE_MAPS_API_KEY not set"}`.
   It never fabricates or AI-generates a building.
2. **Metadata probe first.** The free Street View *metadata* endpoint is probed
   before any image quota is spent. Any status other than `OK` is an honest gap —
   never a blank or substituted tile.
3. **Bytes fetched server-side.** The image is fetched inside the process to a
   local file. The key is used only in that in-process request.
4. **Local path emitted, never a URL.** On success the function returns
   `{"available":true,"source":"google_streetview","image_path":"…","bytes":N,"content_type":"…"}`.
   There is **no `url` field and no key** in the output, by design.

**What the agent does with it:** attach the file at `image_path`. Do not
reconstruct a URL from the coordinates, do not paste a `maps.googleapis.com`
link into a conversation or an event record, and do not put the key anywhere a
message, a log line or a task comment can carry it.

```bash
# correct usage — the caller attaches the returned image_path
. "$SKILL_DIR/scripts/lib-property.sh"
streetview "37.4220,-122.0841" "$MFD/street-view/<opaque-ref>.jpg"
```
