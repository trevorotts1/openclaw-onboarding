# Provider-status contract — `provider-status/v1` (T2-32)

**Schema version:** `provider-status/v1`
**Artifact:** `<MASTER_FILES_DIR>/.skill-39-provider-status.json`
**Producer:** `scripts/02-configure-providers.sh`
**Consumer:** `scripts/property-lookup.sh`

## Why this file exists

The producer and the consumer disagreed on three independent axes at once, so the
consumer saw no status file at all — and its capability checks would not have
lined up if it had. The skill fell back to treating every provider as
unavailable.

| Axis | Producer wrote | Consumer read |
|---|---|---|
| **Path** | `$HOME/.openclaw/.skill-39-provider-status.json` (a fixed home path) | `$MFD/.skill-39-provider-status.json` (the resolved master-files directory) |
| **Capability names** | `geocode`, `lookup`, `comps`, `streetview` | `geocode`, `property_lookup`, `street_view`, `comps` |
| **State shape** | `{"geocode": {"google_maps_api_key": "set", …}}` — key NAMES mapped to set/unset | a `"state":"AVAILABLE"` field per capability |

All three are now pinned here, and both scripts validate against this document.

## 1. Path — resolved, never hardcoded

Both sides resolve the directory through **`re_events_master_dir()` in
`scripts/lib-re-events.sh`** — the same persisted single-source-of-truth resolver
the event log uses. Neither side may hardcode `$HOME/...` or `/data/...`, because
a caller with a different `HOME` would split-brain the artifact.

When the resolver is unavailable and `MASTER_FILES_DIR` is unset, both sides
**fail loudly (exit 2)**. Neither invents a path, and neither treats an
unresolved directory as "no providers configured" — an unresolvable location is
reported, not silently converted into an honest gap.

## 2. Capability vocabulary — one set of names

The canonical names are the four the `--want` flag accepts, because that is the
public interface an operator types:

```
geocode  ·  property_lookup  ·  street_view  ·  comps
```

`lookup` and `streetview` are **not** valid capability names. A status file
containing either is rejected as a schema violation rather than silently read as
"unavailable".

## 3. State shape

```json
{
  "schema": "provider-status/v1",
  "generated_at": "<ISO-8601 UTC>",
  "capabilities": {
    "geocode":         { "state": "AVAILABLE",  "providers": ["census"] },
    "property_lookup": { "state": "HONEST_GAP", "providers": [] },
    "street_view":     { "state": "HONEST_GAP", "providers": [] },
    "comps":           { "state": "HONEST_GAP", "providers": [] }
  }
}
```

- `state` is exactly `AVAILABLE` or `HONEST_GAP`. No third value.
- `providers` lists the provider **names** that made the capability available.
  It is empty when the state is `HONEST_GAP`.
- **No credential value appears anywhere in this file, ever** — provider names
  only. The producer's existing discipline (key NAMES + set/unset, never values)
  is preserved; this contract narrows it further to provider names.
- `geocode` is always `AVAILABLE`: the US Census geocoder is keyless.

## 4. Validation

`scripts/validate-provider-status.sh <file>` validates an artifact against this
contract and is invoked by the producer after writing and by the consumer before
reading.

- **exit 0** — conforms.
- **exit 1** — violates the contract (every violation is listed).
- **exit 2** — could not run (file absent or unreadable). This is reported, never
  counted as a pass and never converted into "no providers available".

A consumer that finds no status file reports that fact and tells the operator to
run `02-configure-providers.sh`. It does not silently degrade every capability to
an honest gap, because "the operator configured nothing" and "the two halves of
this skill disagree about where the file lives" are different problems and must
not produce the same message.
