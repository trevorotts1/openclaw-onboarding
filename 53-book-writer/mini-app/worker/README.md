# Book Writer Mini-App — Worker answers POST (U03)

Wave A, unit U03 of the Book Writer Mini-App Gauntlet. This is the edge Worker's
answer-receiving endpoint. Per the master plan (section 3), the edge Worker is a
**dumb relay** holding **zero client GHL credentials**; the KV binding row is the
**sole authority** for where an answer lands.

## What it does

`POST /api/answers?tk=<token>`

1. **Re-validates the token binding** (KV `binding:<token>`) — unknown /
   expired / completed bindings → 401 / 410 with zero writes.
2. **Normalizes the answer** at the ONE boundary (`normalizeAnswerValue` /
   `normalizeAnswerObject`) — trailing-space keys like `firstname ` and
   `Idealavatar ` (intake-schema.json's defect set) are fixed here and never
   reach a prompt.
3. **Enforces the per-step consumed counter** (KV `consumed:<run>:<phase>:<qid>`) —
   a replayed submit of an already-consumed step is **rejected (409)**, never
   duplicated. Idempotent by construction.
4. **Stages the answer** to per-client KV (`answer:<client_id>:<run>:<phase>:<qid>`).
5. **Returns a receipt + done page** (201).

## Isolation guarantees (master plan section 3)

- The request body is scanned for injected `location_id` / `contact_id` /
  `client_id` — they are **IGNORED** and never copied into the staged answer.
- The KV binding row is the **sole** destination authority.
- The staged answer's `destination` block records ONLY the bound client /
  location / phase / run / intake — nothing from the wire.
- No PITs, no GHL API keys anywhere at the edge.

## Files

- `src/answers.js` — Worker entry + pure decision core (`decideSubmit`,
  `checkBinding`, normalization, key derivation).
- `src/answers.test.mjs` — offline unit gate (`node --test`), 18 tests:
  normal submit, replay-rejected, injected-destination-ignored, tamper/expiry/
  completed 4xx, done-page warmth (no banned strings).
- `wrangler.toml` — KV binding `BW_BINDINGS`; all ids are `<PLACEHOLDER>`.

## Run the self-test

```sh
cd 53-book-writer/mini-app/worker
node --test src/answers.test.mjs
```

Expected: 18 pass, 0 fail.

## Integration

The box ingest poller (U12) polls `answer:<client_id>:...` keys and performs the
GHL write on the run box via Skill 44 rails. The GHL write is **never** done here.
