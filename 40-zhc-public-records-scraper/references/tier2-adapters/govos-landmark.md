# Tier-2 Adapter — GovOS / Landmark Web (Official Records)

GovOS (Landmark Web "Official Records Search" being a common deployment) powers
official-records search portals for many county recorders/clerks. ONE adapter
serves any county on a GovOS/Landmark portal — parameterized by that county's
portal URL from its config (`platform: "govos"`).

> FRAMEWORK description, not a credentialed integration. Live use requires the
> county's portal URL + operator acknowledgement of that county's robots.txt +
> ToS. A disallowing robots = Tier-4 honest gap.

## How the router uses this adapter

1. The resolved county's config has `platform: "govos"`. The router selects this
   adapter.
2. The adapter uses the config's `portal_url` + `search_path` + `search_form_fields`
   + `selectors`. GovOS/Landmark portals share a document-search → results-grid
   shape; field names + selectors vary per county skin.
3. Compliance gate FIRST: robots.txt + acknowledged ToS.
4. Submit the search, parse the results grid via the config selectors, stamp each
   record `source` + `retrieved_at`.
5. Selector drift / disallow / unacknowledged ToS → Tier-4 honest gap. Never an
   invented record.

## Config contract for a GovOS county

```jsonc
{
  "slug": "<county-st>",
  "county_fips": "<5-digit>",
  "state": "<2-digit>",
  "platform": "govos",
  "portal_url": "https://<county>.<govos-or-landmark-host>",
  "search_path": "/<search-endpoint>",
  "tos_url": "https://<county-portal>/terms",
  "record_types": ["deeds", "ownership", "pre_foreclosure"],
  "search_form_fields": { "<field>": "<how-to-fill>" },
  "selectors": { "result_row": "<css>", "grantor": "<css>", "grantee": "<css>", "recorded_date": "<css>" }
}
```

## Adding another vendor

Copy this pattern: write `references/tier2-adapters/<vendor>.md`, give it a
`platform: "<vendor>"` value, and add the vendor to `county-platform-map.md`.
Counties then reference the vendor in their config and reuse the adapter.

## Honesty floor

Never fabricate. Any failure mode is a Tier-4 honest gap, logged + reported.
