# County → Platform → Tier Map

Maps each shipped Tier-1 county to its records-platform vendor and the Tier-2
adapter that serves it. `custom` means a bespoke county portal handled by its own
Tier-1 selectors (not a shared vendor adapter). FIPS are standard US Census
county FIPS (state2 + county3).

| County | State | FIPS | Platform | Tier-2 adapter |
|---|---|---|---|---|
| Cook County | IL | 17031 | custom | — (Tier-1 selectors) |
| Los Angeles County | CA | 06037 | custom | — |
| Maricopa County | AZ | 04013 | custom | — |
| Harris County | TX | 48201 | custom | — |
| San Diego County | CA | 06073 | custom | — |
| Orange County | CA | 06059 | custom | — |
| Miami-Dade County | FL | 12086 | custom | — |
| Kings County (Brooklyn) | NY | 36047 | custom | — |
| Dallas County | TX | 48113 | tyler | tyler-technologies.md |
| King County (Seattle) | WA | 53033 | custom | — |
| Clark County (Las Vegas) | NV | 32003 | custom | — |
| Santa Clara County | CA | 06085 | custom | — |
| Tarrant County (Fort Worth) | TX | 48439 | tyler | tyler-technologies.md |
| Riverside County | CA | 06065 | custom | — |
| Wayne County (Detroit) | MI | 26163 | custom | — |
| Broward County | FL | 12011 | govos | govos-landmark.md |
| Bexar County (San Antonio) | TX | 48029 | tyler | tyler-technologies.md |
| Sacramento County | CA | 06067 | custom | — |

## How the map is used

- The router resolves a query's county FIPS, then finds the Tier-1 config whose
  `county_fips` matches.
- If that config's `platform` names a Tier-2 vendor (`tyler`, `govos`), the
  router uses the vendor adapter (`references/tier2-adapters/<vendor>.md`)
  parameterized by the config's `portal_url`/`search_path`/`selectors`.
- `custom` configs are served by their own Tier-1 selectors directly.

## Adding a county

1. Add `references/tier1-counties/<slug>.json` with the county FIPS + platform.
2. If it's on a known vendor, set `platform` to that vendor; otherwise `custom`.
3. Add the row here.
4. Run `03-load-tier1-counties.sh` to re-index, then `05-validate-target.sh
   <slug>` before any live run.

## Platform values are illustrative routing labels

The `platform` value (`tyler`, `govos`, `custom`) is a routing hint for which
extraction adapter to use. The operator confirms the actual platform + fills the
`portal_url`/`tos_url`/`selectors` and validates before live use. A mismatch
surfaces as a Tier-4 honest gap — never fabricated data.
