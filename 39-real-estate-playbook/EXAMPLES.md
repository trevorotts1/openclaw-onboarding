# Skill 39 — Worked Examples

All examples use UNIVERSAL placeholders. No real address, client, agent, or key appears. Replace
`<...>` placeholders with the live values at runtime. Every example shows the honest-gap path where
a provider key may be absent.

## Example 1 — Buyer lead, address in play, no property-data provider keyed

```
Lead: "Hi, I saw 123 Example St and want to know what it's worth."

Agent (Skill 38 detects buyer intent → Skill 39 buyer qualification + property lookup):
  1. geocode → lib-property.sh geocode "123 Example St, <City> <ST>"
     → Census match: normalized address + lat/lon + county FIPS. (event: geocode, matched:true)
  2. lookup → lib-property.sh lookup "<normalized>"
     → {"available": false, "reason": "no property-data provider configured"} (event: property_lookup, available:false)
  3. HONEST GAP reply: "I can't pull a verified valuation for that address yet — no property-data
     provider is connected. I can pull it the moment you connect a provider key, or if you have a
     figure in mind I'll note it as your estimate (not a verified value)."
  4. Continue buyer qualification: timeline / financing / neighborhood / must-haves.
     → tag ZHC-buyer-lead (event: qualify, role:buyer)
```

The agent NEVER invents a value. It states the gap and offers the operator-supplied-key path.

## Example 2 — Buyer lead WITH a provider key + Street View

```
With RENTCAST_API_KEY (example provider) and GOOGLE_MAPS_API_KEY set:

  geocode    → matched (event: geocode)
  lookup     → {"available": true, "provider": "rentcast", ...}  (event: property_lookup, available:true)
  comps      → {"available": true, "comp_count": 5, ...}         (event: comps, comp_count:5)
  streetview → image URL attached                                 (event: streetview, available:true)

Agent presents VERIFIED facts, citing the provider. CMA pricing-reveal timing (SPICED-RE) applies:
walk the comps first, then reveal the number anchored on comps — never on the seller's hoped price.
```

## Example 3 — Seller qualification + lead routing

```
Lead: "I'm thinking about selling but not in a rush."

Agent → seller qualification (motivation / timeline / price expectation / occupancy):
  motivation = downsizing; timeline = ~6 months; occupancy = owner-occupied
  → tag ZHC-seller-lead (event: qualify, role:seller)

Lead routing → lib reads templates/agent-specialty-roster.template.json:
  best-fit specialty = "listing/seller"; tie broken by round-robin
  → (event: lead_route, agent_specialty:"listing", reason:"seller intent", tie_broken_by:"round_robin")

Fair-housing: never ask about or steer by protected class; route on specialty + fairness only.
```

## Example 4 — Showing scheduler + disclosure pointer

```
Lead books a showing for <date/time> at <address> (state = <ST>).

Agent (showing-scheduler-protocol):
  - confirm date/time/address + access (lockbox type from showing-scheduler-config)
  - set 24h + 2h reminders                              (event: showing, reminders_set:true)
  - surface the state disclosure pointer from references/state-disclosure-matrix.md
    (event: disclosure_surfaced, state:"<ST>")
  - ESCALATE the actual disclosure decision to the licensed agent — Skill 39 gives the pointer,
    not legal advice.
```

## Example 5 — Pre-foreclosure outreach (pairs with Skill 40)

```
Skill 40 surfaces a Notice-of-Default record for a property in county <FIPS>.
Skill 39 consumes it (NEVER scrapes records itself):

  pre-foreclosure-outreach-protocol → care-first, options-focused outreach
  - honors do-not-contact + state cooling-off rules
  - tag ZHC-pre-foreclosure-prospect
  - (event: pre_foreclosure_touch, record_type:"NOD", outreach_stage:"initial", from_skill_40:true)

If Skill 40 is NOT installed or returns nothing → honest gap; no fabricated distress record.
```

## Example 6 — Installing the additive Sales-Brain RE extension

```bash
$ ./05-install-sales-brain-extension.sh
[skill 39] Skill 38 found at <skills-dir>/38-conversational-ai-system
[skill 39] Installing RE Sales-Brain extension as a NEW file (additive):
           38-conversational-ai-system/protocols/sales-best-practices-real-estate-extension.md
[skill 39] Skill 38's own sales-best-practices-protocol.md left UNTOUCHED (verified by hash).
[skill 39] AGENTS.md pointer added behind <!-- BEGIN skill-39 sales-brain-re-extension -->.
[skill 39] event: sales_brain_extension_installed (marker_added:true)
[skill 39] Done. Re-run is idempotent (diffs the file + checks the marker).
```

## Example 7 — Reading the event log (operator ground truth)

```bash
$ tail -3 "$MASTER_FILES_DIR/real-estate-events.jsonl"
{"ts":"2026-05-30T15:00:01Z","skill":"39-real-estate-playbook","event":"geocode","lead_ref":"lead_a1b2","source":"census","matched":true,"county_fips":"<FIPS>","state":"<ST>"}
{"ts":"2026-05-30T15:00:02Z","skill":"39-real-estate-playbook","event":"property_lookup","lead_ref":"lead_a1b2","source":"none","available":false}
{"ts":"2026-05-30T15:00:05Z","skill":"39-real-estate-playbook","event":"qualify","lead_ref":"lead_a1b2","source":"operator","role":"buyer","tag":"ZHC-buyer-lead"}
```

The log records field NAMES + counts, never raw addresses/owner names/prices, and references the lead
by an opaque handle — so the operator's ground-truth log stays PII-free.
