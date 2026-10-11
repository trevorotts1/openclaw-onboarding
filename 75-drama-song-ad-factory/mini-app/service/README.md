# Drama Studio service (U2)

The service foundation of the client mini app for drama song ads. It is the
planned studio home from the joint plan section 5.4 —
`75-drama-song-ad-factory/mini-app/service/` — and it reuses the existing
worker/media pattern from `53-book-writer/mini-app/worker/`. It is not a new
framework, not a new scheduler, not a dashboard, and not a fourth repository.

**What it is.** Section 3.2 of the plan: *"The box is the brain, the relay is
dumb."* This Worker holds **zero** client credentials, **zero** KIE keys,
**zero** GHL tokens and **zero** provider ids. It stores what the client said,
mints short-lived direct-upload links, and answers one line to a check-in.

## Ownership — what this unit writes, and what it does not

| Unit | Owns |
| --- | --- |
| **U2 (this unit)** | `75-drama-song-ad-factory/mini-app/service/**` — keys, inbox entry, uploads, retention, isolation, the option field and the real-wait line, lifecycle and timer precedence, the one operator record per client per day |
| **U20 (this unit)** | `mini-app/service/src/push.js` + its prover — the **OPTIONAL**, version-2 web-push surface. OFF by default (joint plan line 1091); never a version-0 gate |
| U3 | the version-0 pages, the QR screen, the options UI and accessibility. U3 **renders** the lines this service returns; it does not reword them |
| U4 | the deploy files: wrangler config, dry run, zone guard, the bucket's 45-day rule object. **This unit deliberately ships no wrangler.toml** |
| U12 | pairing/admin/key/cutoff **pages**, and setting Option 3 from the admin surface. This unit ships the key code and the endpoints U12 calls |

## Bindings

Declared in `schema.sql`; set by U4's deploy files. This unit reads them from
`env` and never writes a value anywhere.

| Binding | Type | Holds |
| --- | --- | --- |
| `DS_STUDIO` | KV | key records, pairing records, client records, orders, check-ins, upload jobs, the daily operator record |
| `DRAMA_STUDIO` | R2 | the inbox object, uploaded photos/audio, the R2 fallback video |
| `DS_ENROLLMENT_SECRET` | secret | fleet registration only; it never reads an existing client's data |
| `DS_ADMIN_KEY` | secret | the admin endpoints U12 consumes |
| `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY` | secret | presigning only |

The presented key always travels in the **`x-ds-key` header**, never in a query
string, so it cannot land in a URL log.

## Interface contract for U3, U4 and U12

Every response is JSON. Failures are `{ ok: false, code, message }` with a
stable `code` — a refusal always names itself, never a silent blank.

### Entrypoints (the Worker's routes)

| Route | Who calls it | Input | Output |
| --- | --- | --- | --- |
| `GET /api/studio/health` | anyone | — | `{ ok, service, version }` |
| `POST /api/studio/enroll` | U4/U5 on a box's first connection | `{ enrollment_secret, label? }` | `201 { ok, client_id, key }` — the key appears **once** |
| `POST /api/studio/admin/pairing-code` | U12's admin page | `{ admin_key, client_id }` | `201 { ok, code, expires_in }` (`ABCD-2345`) |
| `POST /api/studio/pair` | U13's `studio.py pair` | `{ code, computer_name?, tools? }` | `201 { ok, client_id, key, tools }`; the code burns on use |
| `POST /api/studio/checkin` | U13/U15's `studio_check.py` | header `x-ds-key`, `{ orders? }` | `{ ok, checked_in_at, line }` — `line` is `DRAMA_ORDER r_123 "Spring Sale"` or `null` |
| `POST /api/studio/orders` | U3's page, on Lock it in | header `x-ds-key`, `{ title, order_id? }` | `201 { ok, order, option_line }` |
| `GET /api/studio/orders/<id>` | U3's page | header `x-ds-key` | `{ ok, order, stale_page_line }` |
| `POST /api/studio/orders/<id>/state` | U5's bridge | header `x-ds-key`, `{ event, paid_started? }` | `{ ok, order }` |
| `POST /api/studio/orders/<id>/cancel` | U3's page | header `x-ds-key` | `{ ok, order }` |
| `POST /api/studio/uploads` | U3's page | header `x-ds-key`, `{ channel, filename, size_bytes, content_type, header_bytes }` | `201 { ok, upload_id, object_path, upload: { method, url, content_type, expires_in } }` |
| `POST /api/studio/uploads/<id>/complete` | U3's page | header `x-ds-key` | `{ ok, job }` |
| `GET /api/studio/options` | U3's page | header `x-ds-key` | `{ ok, option, line }` |
| `POST /api/studio/options` | U12's admin page | `{ admin_key, target_client_id, option, approval? }` | `{ ok, option, line }`; Option 3 needs `approval: { option3: true, client_name }` |
| `GET /api/studio/push` | U20's optional page | — | `{ ok, enabled }`; **false** unless an operator set `DS_WEB_PUSH_ENABLED` |
| `POST /api/studio/push/subscribe` | U20's optional page | header `x-ds-key`, `{ subscription: { endpoint, keys: { p256dh, auth } } }` | `201 { ok, subscription_id }`; **503 `AF-DS-PUSH-DISABLED` and stores nothing** when push is off |
| `POST /api/studio/push/unsubscribe` | U20's optional page | header `x-ds-key`, `{ subscription_id }` | `{ ok, subscription_id, status: "revoked" }`; a record that is not the caller's reports `AF-DS-PUSH-MISSING` |
| `POST /api/studio/admin/push/send` | U20, operator only | `{ admin_key, target_client_id, payload }` | `{ ok, attempted, sent, failed, pruned }`; **503 `AF-DS-PUSH-DISABLED`** until push is enabled, configured and a transport is injected |

> **U20 is OPTIONAL and version 2.** Joint plan line 1091: `| U20 | Optional web
> push | U3 | onboarding planned service | U3; never version-0 gate |`. Line 832:
> `none blocks version 0`. With `DS_WEB_PUSH_ENABLED` unset — every version-0
> studio — the status route says `enabled: false`, the subscribe route refuses and
> writes nothing, and the send path refuses before it reads a subscription. The
> VAPID material is env-only and is never stored, echoed or printed; the actual
> wire encryption + VAPID signing is a **transport the runtime injects**
> (`sendPush({..., transport})`), so this unit ships no vendor and opens no socket.

`event` is one of `claim`, `needs_you`, `answer`, `ready`, `deliver`, `done`.
The `order` object is the record in `schema.sql` projected with its timers
applied, plus `state_reason`, `state_from_timer` and `availability`
(`not-delivered` | `available` | `r2-expired`). **Availability is a separate
field, never an order state.**

### The modules U3/U4/U12 import

```js
import { optionLine, staleVerdict, setOption } from '.../service/src/options.js';
import { resolveOrderState, transition }      from '.../service/src/lifecycle.js';
import { randomClientId, scopePath }          from '.../service/src/ids.js';
import { resolveKey, authorizeClient }        from '.../service/src/isolation.js';
import { mintKey, mintPairingCode, attemptPairing } from '.../service/src/keys.js';
import { RETENTION_RULES, retentionVerdict }  from '.../service/src/retention.js';
```

Everything except `presignPut` and the store adapters is pure and takes an
injected adapter, which is why the whole service is testable with no
Cloudflare account:

```js
store.kvGet(key) -> string|null        objects.objectGet(path) -> {value}|null
store.kvPut(key, value, ttlSeconds?)   objects.objectPut(path, value)
store.kvDelete(key)
store.kvList(prefix) -> string[]
```

## The four strings U3 renders (verbatim from section 3.10)

```
1  Your crew starts when you open Claude Code on your computer. Last check-in: 3 hours ago.
2  Your crew is watching. Orders start within about 2 minutes while your computer is on. Last check-in: 1 minute ago.
3  Your crew starts automatically within about 2 minutes while your computer is on and awake. Last check-in: 2 minutes ago.
   (any option, 30 minutes with an order waiting)
   Your computer has not checked in since 2:14 PM. Your order is safe and starts when it is back.
```

The operator inbox line is `Computer has not checked in since 2:14 PM with an
order waiting`, and it is written through the one-record-per-client-per-day rule.

## Security: what is enforced, and how it is proven

Section 3.15, *"One client can never see another's"*:

1. **Possession** — a request reaches a client's records only with a key the
   studio minted. No key record, a revoked key, or a malformed one is refused
   before any read.
2. **Binding** — `client_id` comes **only** from the stored key record. A body
   that claims a different `client_id` is refused (`AF-DS-ISO-CROSS`) and the
   record wins.
3. **Scope** — every object path is checked with `ownsPath` before a read or a
   presign, and order keys are namespaced `order:<client_id>:<order_id>`, so
   another client's key cannot even name the record.
4. **Enrollment** — the fleet secret registers a **new** client. It can never
   adopt or read an existing one.
5. **Keys** — only a sha256 fingerprint is ever stored. The raw key is returned
   to its owner exactly once, at mint time.

### Runnable checks (real commands, real exit codes)

```bash
# Behavior suite — 22 tests
node --test 75-drama-song-ad-factory/mini-app/service/test/service.test.mjs
#   exit 0 = all pass

# Security prover — per-client isolation, retention, once-per-day
node 75-drama-song-ad-factory/mini-app/service/prove/prove_service_boundaries.mjs
#   exit 0 = PASS, 2 = a named case failed, 3 = the prover could not run

# U20 optional-web-push prover (10 cases) and its planted-bad controls
node 75-drama-song-ad-factory/mini-app/service/prove/prove_push_optional.mjs
#   exit 0 = PASS, 2 = a named case failed, 3 = the prover could not run
bash 75-drama-song-ad-factory/mini-app/service/prove/planted-bad.sh
#   exit 0 = every planted defect went red AND the clean run is green
```

The prover runs every store read through a **recording** proxy, so *"client B
never touched client A's records"* is an observed negative — the proxy was
watching A's namespace and saw nothing — not an unchecked absence. Each
negative is paired with a positive control on the same instrument, and the
prover was verified against a planted defect (removing the cross-client refusal
turns `C4` red and exits 2).

The once-per-day proof: two same-day calls produce **one** stored record, the
second line replaces the first, and the next day opens a fresh one.

## Deliberate limits

- No `wrangler.toml` and no deploy script — those are U4's paths.
- No pages, no QR screen, no admin UI — U3's and U12's paths.
- No scheduler, dashboard or management app (section 5.1).
- The daily operator record's day boundary is **UTC**. One line per UTC day is
  what the service can enforce without a timezone it does not yet store; the
  upgrade path is to read `client.timezone` and key on the client's local day.
- No deletion sweep runner — `retention.js` decides, and the caller deletes.
  A never-delete class is partitioned out of the delete list by construction.
- **U20 web push is OPTIONAL (version 2).** It is OFF by default, ships no
  vendor and opens no socket: the wire encryption and VAPID signing are a
  transport the runtime injects, so the deployed Worker refuses to send until a
  transport exists. No version-0 route, page or test reads `push.js`, and the
  version-0 test suite runs unchanged.
