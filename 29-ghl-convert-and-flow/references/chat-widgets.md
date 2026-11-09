# Chat Widgets — creation, installation and conversation proof

> **Authority.** The executable registry (`44-convert-and-flow-operator/tools/engine/cli_anything/gohighlevel/public/operations.py`) is the only implementation authority. This reference is a derived, source-indexed view. Reading it cannot enable an operation; enablement is per `(operation_id, tenant)` in the capability gate.
>
> **Evidence state (2026-11-08).** Pages were not refetched in this lane. `ghl-contract-sources.json` labels each source `inherited`/`reopened-at-spec-time`, never "verified live". A source-reported capability is not a measured entitlement of this or any client account. Machine-readable rows: `ghl-hybrid-capability-index.json`.

## Write allowlist is narrower than read results

The create contract accepts `liveChat` and `emailChat`. Other widget types visible in reads are not valid create payloads. A request for Voice AI, WhatsApp, all-in-one or another unlisted type is a gap: discover a newer exact contract or use the approved UI path; never coerce it into a different type and call it fulfilled.

Three different "versions" meet here:
- HTTP `Version: v3`
- body configuration `version` (numeric)
- local schema version

Never set the configuration `version` to the string `v3`. The create response uses `_id`; do not run a universal `id` extractor.

## Build sequence

1. Inventory existing widgets and page installations; identify reuse/update.
2. Validate the requested type against the write schema, not the read schema.
3. Create/update; read back the real `_id`, appearance, location and behavior settings.
4. Obtain the vendor's actual embed instruction. Never fabricate a script URL, attribute or widget token.
5. Install once at the correct site/page scope; detect global and page-level embeds to prevent duplicates.
6. Verify desktop/mobile display, launcher placement, keyboard/touch use, and interference with navigation/checkout/consent.
7. Submit an approved test conversation; verify the correct inbox/thread and intended responder.
8. Verify handoff and non-business-hours behavior when applicable.
9. Activate only within approved scope; record rollback.

A visible bubble is not proof messages reach the right location. An inbox message is not proof the intended AI replied. Test separately.

## Synthetic request

```json
{"locationId":"SYNTHETIC_LOCATION","type":"liveChat","name":"ZHC Site Chat","version":1}
```

Failure: `type:"whatsapp"` → refuse (outside the documented allowlist). Failure: `version:"v3"` → refuse (type error). Readback: `GET /chat-widget/data/{locationId}/{_id}` then an approved thread test.

## Registry state

No `chat_widgets.*` registry row exists at this base; `documented_unregistered` carries `chat_widgets.create` as a documented-unimplemented gap (WF31). Skill 6 owns installation rendering/verification; Skill 38 owns response behavior.
