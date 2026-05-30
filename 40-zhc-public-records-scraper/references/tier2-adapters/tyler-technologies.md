# Tier-2 Adapter — Tyler Technologies platforms

Tyler Technologies powers a large share of US county records, recorder, and court
portals (product families historically including Eagle Recorder, Odyssey court
portals, and iasWorld/property appraisal in some jurisdictions). ONE adapter
serves any county on a Tyler platform — parameterized by that county's portal
URL from its Tier-1 config (or a Tier-3 config naming `platform: tyler`).

> This adapter is a FRAMEWORK description, not a credentialed integration. Live
> use requires the county's portal URL + the operator acknowledging that
> county's robots.txt + ToS. A Tyler-powered county whose robots disallow our
> path is a Tier-4 honest gap.

## How the router uses this adapter

1. The resolved county's Tier-1 config has `platform: "tyler"` (or a Tier-3
   config names it). The router selects this adapter.
2. The adapter takes the county's `portal_url` + `search_path` + `search_form_fields`
   + `selectors` from the config (Tyler portals share a search → results-table
   shape, but the exact field names + selectors vary per county skin).
3. Compliance gate runs FIRST: robots.txt + acknowledged ToS.
4. The adapter submits the search, parses the results table using the config's
   selectors, and stamps each record `source` + `retrieved_at`.
5. If the portal shape has drifted (selectors don't match), the adapter returns a
   Tier-4 honest gap — it NEVER invents a record.

## Config contract for a Tyler county

```jsonc
{
  "slug": "<county-st>",
  "county_fips": "<5-digit>",
  "state": "<2-digit>",
  "platform": "tyler",
  "portal_url": "https://<county>.<tyler-portal-host>",
  "search_path": "/<search-endpoint>",
  "tos_url": "https://<county-portal>/terms",
  "record_types": ["ownership", "deeds", "tax", "pre_foreclosure"],
  "search_form_fields": { "<field>": "<how-to-fill>" },
  "selectors": { "result_row": "<css>", "owner": "<css>", "recorded_date": "<css>" }
}
```

## Why a vendor adapter (vs one config per county)

Counties on the same vendor share the search→results shape, so the extraction
logic is written once. Per-county differences live in the config (URL + field
names + selectors), not in code. Adding a Tyler county = adding a config that
names `platform: tyler`.

## Honesty floor

The adapter never fabricates. Drifted selectors, a disallowing robots.txt, or an
unacknowledged ToS each produce a Tier-4 honest gap, logged and reported.
