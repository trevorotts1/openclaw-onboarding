# Video-link delivery (U10 required)

Joint plan section 5, row **U10 required** — verbatim scope:

> Only client-owned GHL-first verified video link and R2 fallback

Service home per section 5.4: `75-drama-song-ad-factory/mini-app/`. This unit owns
`mini-app/video-link-delivery/**` only — U2 owns `mini-app/service/**`, U3 the
mini-app UI, U4 `mini-app/deploy/**`, U5 `shared-bridge/**`, U12 the pairing/admin
surface. No file here edits another unit's path.

Decision 5 (answered by Trevor, 2026-10-10) fixes the order this module enforces:
the finished video's public CDN link is handed over from the **client's own**
GoHighLevel (white label: Convert and Flow) **first**; Cloudflare R2 (bucket
`drama-studio`) is the **fallback**, used only when the client-owned GHL path is
unavailable. The R2 copy is deleted 7 days after delivery; GHL copies never are.

## What it does, and what it does not

It answers one question: *which link may be handed over, and is it really that
link?* It does not upload the video, does not message anyone, does not schedule
anything, and adds no second control service or scheduler.

It reuses the shape of the repo's proven `ghl_media.py`
(`06-ghl-install-pages/tools/ghl_media.py`): bare `urllib`, a fail-loud `_require`,
an injectable transport so every path is testable with no live call, and a strict
output contract that can only ever describe a link that really resolved.

## "Verified" is not a label

`verify_link()` FETCHES the URL and streams the bytes through sha256. A link is
deliverable only when it returns HTTP 200 **and** the bytes hash to the finished
video's `expected_sha256`. A 200 that serves different media is refused exactly
like a link that does not resolve.

## The refuse rules (in the order the code applies them)

| # | Rule | `reason_code` | Exit |
|---|---|---|---|
| 1 | the record and the delivery must be the same client | `cross-client-delivery` | 4 |
| 2 | no candidate URL may embed a secret or be a signed/expiring link | `token-in-url` | 4 |
| 3 | an operator-owned link (operator location id **or** operator host) is refused outright, never skipped into the fallback | `operator-owned-link` | 4 |
| 4 | the GHL candidate must be the client's own media host **and** the client's own location id | `ghl-candidate-not-client-media`, `ghl-candidate-not-client-owned` | 4 |
| 5 | the R2 candidate must be served by the studio R2 origin, and must verify | `fallback-unverified` | 4 |
| 6 | nothing verified ⇒ refuse rather than hand over anything unverified | `no-verified-deliverable-link` | 4 |

`ownership` in the delivered record is **derived from the source** (`client-ghl`
for GHL, `studio-r2-fallback` for R2), never taken from the caller, so an
operator-hosted upload can never be labelled as the client's.

## CLI (repo envelope contract, `references/cli-contract.md`)

```bash
python3 mini-app/video-link-delivery/video_link_delivery.py deliver \
  --request <path.json> [--out <record.json>]
```

Exactly one JSON object on stdout, no log noise. Exit: `0` ok, `1` error,
`4` rejected. (`waiting` 2 and `parked` 3 are unused here.)

Request fields: `client_id`, `record_client_id`, `client_location_id`,
`expected_sha256` (required); `ghl_candidate`, `r2_candidate`, `stored_link`,
`operator_location_ids`, `operator_hosts`, `token` (optional). The host rules
default to production (`storage.googleapis.com` + `/msgsndr/` for GHL; the R2
origins for the fallback) and a request may point the same rule at a local mock
server for a check.

## Checks

```bash
python3 mini-app/video-link-delivery/checks/run_checks.py   # exit 0 = proven
```

Six checks (A–F), each a real subprocess with a true exit code, and each with a
**planted-bad** copy of the module (one load-bearing line mutated) that must make
the same check FAIL. Every URL is served by a local mock server on `127.0.0.1`;
no live network call, no credential, no client message, no client-box write.
