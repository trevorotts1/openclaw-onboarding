# KIE Common Rules (single source of truth)

Status: canonical. Verified 2026-10-05. Every SOP and skill that touches KIE.ai points here
instead of restating these rules. If another file disagrees with this one, this file wins
(except where rule 1 gives a higher authority). Fix the other file.

Sources: https://docs.kie.ai (market, rate-limit, task-detail, file-upload, common API pages),
live endpoint probes on 2026-10-05, and AGENTS.md section N43.

## 1. Authority order (highest first)

1. Owner rulings (AGENTS.md N43 and similar).
2. Department pins (for example the Presentations `model_catalog.json`).
3. Skill policy owners: Skill 66 (image), Skill 67 (video), Skill 68 (audio).
4. Skill 74 live adapter: mechanics only. It never chooses models.
5. Static tables in the repo: dated snapshots only.

## 2. Endpoints (live-verified 2026-10-05)

- Base: `https://api.kie.ai`
- Create job: `POST /api/v1/jobs/createTask`
- Job status: `GET /api/v1/jobs/recordInfo?taskId=<id>`
- Balance: `GET /api/v1/chat/credit`
- Catalog: `GET /api/v1/models`; schema: `GET /api/v1/models/<id>/schema`
- Fresh download link: `POST /api/v1/common/download-url`
- Upload host: `https://kieai.redpandaai.co` with `/api/file-base64-upload` (10 MB max),
  `/api/file-stream-upload`, `/api/file-url-upload`
- Legacy family routes still live: `/api/v1/veo/generate`, `/api/v1/veo/record-info`
- DEAD (404), never use: `/api/v1/account/balance`, `/api/v1/user/credits`,
  `/api/v1/jobs/create`, `/api/v1/veo/task`, `/api/v1/video/generate`

Auth: `Authorization: Bearer <key>` only. A header named `apikey` returns 401.
Always read the body field `code`. HTTP 200 can still carry 401, 402, 404, 422, 429, 433 or 455.

## 3. Rate limits (KIE official)

- createTask: 20 per 10 seconds per account.
- recordInfo: 10 per second per taskId.
- models, schema, price and success-rate calls share 1 per second per account.

Any other figure anywhere in the repo is wrong.

## 4. Polling

Production batches use Skill 46 callbacks. One-off polling starts at about 3 seconds, backs off,
and has a deadline sized to the media (image about 300 seconds; video and music longer).
A department whose code implements a specific ladder (for example Presentations `build_deck.py`)
is authoritative for that department, and its SOPs must describe that code.

## 5. Limits authority (prompt length, enums, required fields)

One authority: the live schema, checked with
`python3 74-kie-live-adapter/scripts/kie_live_adapter.py validate` (falls back to the generated
snapshot `74-kie-live-adapter/references/kie-model-registry.json`). It covers prompt
maxLength/minLength, enums and required fields per model. Requests outside the limits are
blocked before dispatch. For the GPT Image 2.5 family the prompt cap is 20,000 characters
(N43 and the KIE model page); a 25,000 figure is wrong for 2.5. (N43 records 25,000 as the
owner-confirmed cap for retained legacy `gpt-image-2-*` entries only; never apply either number
across generations.) The older house band of 9,000 to 19,000 is superseded by rule 12.

## 6. Credit preflight

Required balance = price (rule 7) x 1.30. A skill may enforce a stricter documented absolute
minimum. Read balance only through `/api/v1/chat/credit`.

## 7. Price authority

One authority: `python3 74-kie-live-adapter/scripts/kie_live_adapter.py price --model <id>`
(live catalog `pricingDesc`, falling back to the generated snapshot
`74-kie-live-adapter/references/kie-model-registry.json`). No skill may keep its own price
table. Any price table elsewhere in the repo is a dated snapshot and not authoritative.
(The adapter and registry land in a follow-up Skill 74 change; reference them by these names.)

## 8. Retention

Download and persist results immediately. KIE documents 14 days for generated media, but its
task-detail page says result URLs typically expire after 24 hours, so never rely on 14 days.
Uploads are deleted after 24 hours (one docs section says 3 days; honor `expiresAt` when
returned). Links from download-url last 20 minutes. Task records last 2 months.

## 9. Keys

On a client box the KIE key is the client's own. Operator keys are never used for client work.
Resolve keys only through shared-utils `key_resolver.py` / `secret_names.json`. Print SET or
NOT-SET only, never the value. Stop after 2 attempts on 401 or 403.

## 10. Model ids

Never write a model id from memory. Use the policy owner's registry or the department pin.
New live models start as DISCOVERED and are never auto-defaults.

## 11. Image pin (restated from N43, unchanged)

The fleet image family is `gpt-image-2-5-sunburst-*`. Legacy `gpt-image-2-*` is used only for
the 3:1, 1:3 and 9:21 ratios. `flare` is not introduced without a new owner ruling.

## 12. Prompt length budget (owner order 2026-10-05)

Prompt writers must know each model's character limit and write prompts close to the maximum
(at least within 5 percent of it, never below 80 percent) to get better images, video and audio.

- Applies to DESCRIPTIVE prompt fields of KIE image, video and music models: image prompt,
  video prompt, music style or description. It does NOT apply to verbatim content fields that
  are spoken or sung exactly (text-to-speech script text, user-supplied lyrics); those follow
  their own content length.
- Limit source: `python3 74-kie-live-adapter/scripts/kie_live_adapter.py prompt-budget --model <id>`
  (live schema maxLength; fallback `74-kie-live-adapter/references/kie-model-registry.json`).
  Never from memory.
- Target: 95 to 100 percent of maxLength. Hard floor: 80 percent (below it, reject and rewrite).
  Hard ceiling: 100 percent (above it, reject). 80 to 95 percent: warn and expand.
- Example: GPT Image 2.5 (sunburst), maxLength 20,000: floor 16,000, target 19,000 to 20,000.
  Legacy `gpt-image-2-*` per N43, cap 25,000: floor 20,000, target 23,750 to 25,000.
- This rule supersedes the older house band of 9,000 to 19,000 (its floor and ceiling). Any skill
  or SOP still stating that band is out of date and will be updated to point here.
- If a model's schema declares no maxLength for its prompt field, writers use the policy owner's
  documented limit (Skill 66, 67 or 68). If none exists, the validator reports UNKNOWN and does
  not enforce a floor.
