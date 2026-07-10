# Deploy — Presentation Intake mini-app

> **DOMAIN CHOICE IS FLAGGED, NOT GUESSED.**
> The production host is the **operator's Cloudflare zone**. This repo ships
> `<PLACEHOLDER>` tokens in `worker/wrangler.toml` on purpose. Fill them in at
> deploy time. Do not commit a real account id, zone, or database id.
> Suggested public host: `intake.<FLEET_DOMAIN>` (operator picks the zone;
> the fleet already fronts client surfaces on Cloudflare).

## Prerequisites

- `wrangler` CLI logged in to the operator's Cloudflare account
  (`npx wrangler login`).
- A Cloudflare zone the operator controls (for `intake.<FLEET_DOMAIN>`).

## 1. Create + migrate D1

```
cd worker
npx wrangler d1 create presentation_intake
# → copy the returned database_id into wrangler.toml [[d1_databases]].database_id
npx wrangler d1 execute presentation_intake --remote --file=schema.sql
```

## 2. Fill in wrangler.toml placeholders

- `account_id` = the operator's Cloudflare account id
- `routes[].pattern` / `zone_name` = `intake.<FLEET_DOMAIN>/api/*` and the zone
- `[[d1_databases]].database_id` = from step 1

## 3. Set the one secret (box↔worker auth)

```
npx wrangler secret put INTAKE_ADMIN_TOKEN
# paste a fresh random 32+ char string; store the SAME value on each box as
# env INTAKE_ADMIN_TOKEN (the bridge reads it there). It never appears in argv,
# the repo, or any log. Capability tokens gate everything client-facing, so no
# other secret is needed.
```

## 4. Deploy the Worker (API)

```
npx wrangler deploy
curl https://intake.<FLEET_DOMAIN>/healthz     # → {"status":"ok",...}
```

## 5. Deploy the UI (Pages)

The Worker owns `/api/*`; the Pages project serves everything else
(`/s/<token>`, `/`). Same origin so the UI calls `/api/...` with no CORS.

```
npx wrangler pages deploy ../pages --project-name presentation-intake
```

Point the Pages project (or a route) at `intake.<FLEET_DOMAIN>` for all non-`/api`
paths, with an SPA fallback so `/s/<token>` serves `index.html`.

> **Single-Worker alternative.** If the operator prefers one deployable, enable
> Workers Static Assets: add an `[assets] directory = "../pages"` binding to
> `wrangler.toml` and the Worker will serve the UI for non-`/api` paths itself.
> The API code needs no change — it already only claims `/api/*` and `/healthz`.

## 6. Box side

```
# generate the payload from the canonical JSONs
python3 payload/build_questions_payload.py --set standard --run-id RUN123 --out /tmp/payload.json

# mint a session (INTAKE_ADMIN_TOKEN must be in the box env)
python3 bridge/intake_bridge.py mint \
  --worker-url https://intake.<FLEET_DOMAIN> \
  --run-id RUN123 --box-id boxA --questions /tmp/payload.json
# → prints {"capability_url": "https://intake.<FLEET_DOMAIN>/s/<token>", ...}

# after the client fills it in, pull answers into the run's intake ledger
python3 bridge/intake_bridge.py sync \
  --worker-url https://intake.<FLEET_DOMAIN> \
  --token <token> --run-dir /path/to/run --question-set standard
```

For a signature run pass `--set signature` (mint) and `--question-set signature`
(sync); on completion the bridge assembles the record and runs
`--signature --record`, which invokes `prove_sp_intake.py`.

## Cost

Cloudflare free tier is sufficient at fleet volume (a Worker, a small D1, a Pages
project). A Worker outage degrades to the chat driver automatically.
