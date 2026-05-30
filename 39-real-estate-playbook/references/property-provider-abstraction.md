# Property Provider Abstraction — the contract

Skill 39 talks to property data through ONE contract so any provider can be
swapped in without touching the conversation layer. The implementation is
`scripts/lib-property.sh`. **Every function honors the no-fabrication floor: a
provider miss returns an honest gap, never an invented value.**

## The four operations

| Operation | Function | Honest-gap shape on miss |
|---|---|---|
| Geocode + normalize | `geocode "<raw address>"` | `{"matched": false, "source": "none", "reason": ...}` |
| Property lookup | `lookup "<normalized addr>"` | `{"available": false, "source": "none", "reason": ...}` |
| Comparable sales | `comps "<normalized addr>"` | `{"available": false, "source": "none", "reason": ...}` |
| Street View image | `streetview "<lat>,<lon>"` | `{"available": false, "source": "none", "reason": ...}` |

## Provider tiers

- **Geocoding** is ALWAYS available via the keyless **US Census Geocoder** (US
  addresses). Optional precise/non-US providers: Google (`GOOGLE_MAPS_API_KEY`),
  Mapbox (`MAPBOX_TOKEN`).
- **Lookup + comps** are PROVIDER-GATED. Skill 39 ships ONE example adapter
  (RentCast, `RENTCAST_API_KEY`) plus the contract. Without a keyed provider,
  both return `available: false`.
- **Street View** is GATED on `GOOGLE_MAPS_API_KEY`.

## How to add or swap a provider

1. Add an adapter branch inside the relevant function in `lib-property.sh`,
   gated on the provider's env key (e.g. `if [ -n "${YOUR_PROVIDER_KEY:-}" ]`).
2. Make the HTTP call with `curl -fsS --max-time N`.
3. On a hit, return the SAME contract shape: `{"available": true, "source":
   "<provider-slug>", ...}` (or `matched: true` for geocode).
4. On a miss, FALL THROUGH to the existing honest-gap return — never invent a
   record.
5. Add the env key to `02-configure-providers.sh`'s probe list and to
   `00-verify-prerequisites.sh`'s provider-key report.
6. Document the provider's ToS expectation — the operator is responsible for
   provider ToS + licensing (MLS/RESO feeds in particular require a license).

## Why field NAMES (not values) go to the event log

The live reply gets the full record on stdout. The `real-estate-events.jsonl`
log records only field NAMES + counts + an opaque `lead_ref` so the operator's
ground-truth log stays free of raw property PII. See INSTRUCTIONS.md.

## MLS / RESO note

MLS-adjacent data (RESO Web API) requires a licensed feed and carries strict
ToS. Skill 39 ships NO MLS credentials. The operator wires their licensed RESO
token via env; the adapter follows the same contract.
