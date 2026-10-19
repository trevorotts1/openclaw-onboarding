# GHL-111 — GU-022 403 scope/location analysis

Date: 2026-10-19
Unit: GHL-111 (W11-parity)
Scope: READ ONLY. No write, no mutation, no credential substitution, no token value printed.
Credential used: `GOHIGHLEVEL_API_KEY` only (40 characters, `pit-` prefix — Private Integration
Token shape). No other credential was read into a request.

## 1. Answer first

The 403 is an authorization-layer rejection of the **credential-to-location binding**, plus a
**documented scope** requirement that the same call also needs. The token is not bound to the
location it is configured with, and the exact bound location is **not derivable from any
configuration on this box**. The required correction is an owner action in the HighLevel UI:
put a Private Integration Token that was created **inside the target sub-account** and that
carries `contacts.readonly` and `locations.readonly` into `GOHIGHLEVEL_API_KEY`, with
`GOHIGHLEVEL_LOCATION_ID` naming that same sub-account.

## 2. What the configuration actually binds (non-secret identifiers only)

`GOHIGHLEVEL_API_KEY` is resolved by `public/auth.py` as auth class `location_pit`. The frozen
alias chain at `44-convert-and-flow-operator/tools/engine/cli_anything/gohighlevel/public/auth.py:35-55`
puts `GOHIGHLEVEL_API_KEY` first; no other PIT alias is set in the environment, so this is the
credential the adapter and GU-022 both use.

Tenant aliases (`auth.py:76-86`) resolve `GOHIGHLEVEL_LOCATION_ID` first. The pair in
`~/.openclaw/secrets/.env` is:

| Identifier | Value (non-secret) |
|---|---|
| Credential variable | `GOHIGHLEVEL_API_KEY` (value never printed) |
| Configured location | `XCgFTEA1oDvsPnTqqgoB` |
| Company / agency id | `DAD7unnJpNUFc36952Xp` |

Every other location id present anywhere on this box (three drifting env stores plus the two
per-client stores) was enumerated and tested with the **same** credential:

| Location id | Source (name only) |
|---|---|
| `XCgFTEA1oDvsPnTqqgoB` | `~/.openclaw/secrets/.env:GOHIGHLEVEL_LOCATION_ID`, `GOHIGHLEVEL_ALLOWED_LOCATION_IDS`, `CAF_ALLOWED_LOCATION_IDS`, `~/.openclaw/secrets/secrets.env` |
| `CjxATjhv9Gt21qSqURIt` | `PODCAST_ENGINE_GHL_LOCATION_ID` |
| `w4A5LiurmAjBbvJOXmyz` | `OLD_PODCAST_GHL_LOCATION_ID` |
| `mQeLerCLRJzGKzAQoY2Y` | `STAR_BOBATOON_GHL_LOCATION_ID` |
| `rvAsxGJTII3XpEKIFQ5T` | `DRTOLA_GHL_LOCATION_ID` |
| `B47go0z6UyNoPESI9G4L` | `~/.openclaw/secrets/donna-izzard.env:GOHIGHLEVEL_LOCATION_ID` |
| `tWMezdePuWYFZrrUMw16` | `~/.openclaw/secrets/janet-pinkney.env:GOHIGHLEVEL_LOCATION_ID` |

No value of `GOHIGHLEVEL_API_KEY` is shared with any other named PIT on the box (compared by
equality in the shell, never printed), so no alias inference is possible: the token is not a
renamed copy of another configured client token.

## 3. Documented scope for each failing operation

Source: the official HighLevel OpenAPI documents and scope table, fetched 2026-10-19 from
`github.com/GoHighLevel/highlevel-api-docs` (the pages under
`marketplace.gohighlevel.com/docs` are a JavaScript shell and returned no text).

| Operation | Method / path | Version | Security scheme | Required scope | Deprecated | Documented responses |
|---|---|---|---|---|---|---|
| `locations.get` | `GET /locations/{locationId}` | `2021-07-28` | `Location-Access`, `Agency-Access` | `locations.readonly` | no | 200, 400, 401, 422 |
| `contacts.list` | `GET /contacts/` | `2021-07-28` | `bearer` | `contacts.readonly` | **yes** | 200, 400, 401, 422 |
| `contacts.search` (supported replacement) | `POST /contacts/search` | `v3` | `bearer` | `contacts.readonly` | no | 200, 400, 401, 422 |

`docs/oauth/Scopes.md` lists `contacts.readonly` (access type: Sub-Account) and
`locations.readonly` (access type: Sub-Account, Agency). The scheme description on both API
documents reads "Access Token generated with user type as Sub-Account (OR) Private Integration
Token of Sub-Account" — a PIT is a **sub-account** credential, which is why the location in the
path/query must be the PIT's own sub-account.

Both operations were called with `Version: 2021-07-28`. **403 is not in the documented
response set for either operation**, so this rejection comes from the authorization layer
above the documented contract.

## 4. Live read-only evidence (same credential, same transport)

`GOHIGHLEVEL_API_KEY`, base `https://services.leadconnectorhq.com`, no other credential used.

| Probe | Location id | Status | Message |
|---|---|---|---|
| `GET /locations/{id}` | `XCgFTEA1oDvsPnTqqgoB` | 403 | `Forbidden resource` |
| `GET /contacts/?locationId=…&limit=1` | `XCgFTEA1oDvsPnTqqgoB` | 403 | `The token does not have access to this location.` |
| `GET /users/?locationId=…` | `XCgFTEA1oDvsPnTqqgoB` | 401 | `This location is not accessible from this token!` |
| `GET /users/?locationId=…` | `CjxATjhv9Gt21qSqURIt` | 401 | `This location is not accessible from this token!` |
| `GET /users/?locationId=…` | `w4A5LiurmAjBbvJOXmyz` | 401 | `This location is not accessible from this token!` |
| `GET /users/?locationId=…` | `mQeLerCLRJzGKzAQoY2Y` | 401 | `This location is not accessible from this token!` |
| `GET /users/?locationId=…` | `rvAsxGJTII3XpEKIFQ5T` | 401 | `This location is not accessible from this token!` |
| `GET /users/?locationId=…` | `B47go0z6UyNoPESI9G4L` | 401 | `This location is not accessible from this token!` |
| `GET /users/?locationId=…` | `tWMezdePuWYFZrrUMw16` | 401 | `This location is not accessible from this token!` |

`GET /users/` requires `users.readonly` and the same location binding. It is used here only as a
location-access discriminator; no user record was printed (only the status and the error text).

### Instrument control (proves the check discriminates)

| Control | Status | Message |
|---|---|---|
| Deliberately invalid token on the same URL | 401 | `Invalid JWT` |
| No `Authorization` header | 401 | `No Authorization header found for authentication!` |

The instrument returns 401 for an invalid/missing credential and 403/401-with-location-text for
this valid token. The result is token-specific, not a broken check.

### What this proves and what it does not

Proven: the token is structurally valid (it does not produce `Invalid JWT`), and the service
refuses it for every location id that exists in configuration on this box, including the one it
is paired with.

Not proven: which location the token **is** bound to. HighLevel exposes no token-introspection
endpoint, and the binding is server-side. Two explanations remain open and both are owner-side:
(a) the PIT was created in a different sub-account, or (b) the PIT was created with no/partial
scopes. The response text alone cannot separate them; the correction is the same either way.

## 5. The actual client path cannot prove anything yet — two independent blockers

1. **Registry.** `GET /locations/{locationId}` is **not an operation in the frozen registry**
   (`public/operations.py`, 139 rows, zero `locations.*` rows). `GET /contacts/` **is** the row
   `contacts.list`, whose route class is `retired` with blocker `B-DEPRECATED`. So neither
   GU-022 probe is a valid client-path operation: one has no row, the other is retired. The
   supported read is `POST /contacts/search` (`v3`, `contacts.readonly`, blocker
   `B-FILTER-SCHEMA`).
2. **Capability gate.** The adapter is default-deny
   (`public/capability.py:92-99`; `public/adapter.py:454`). Exercising the real adapter
   (`PublicGhlAdapter.call`) with the production credential returned, before transport:

   | Operation | Adapter status | HTTP | Rule |
   |---|---|---|---|
   | `contacts.list` | denied | none | `capability_disabled` |
   | `contacts.search` | denied | none | `capability_disabled` |
   | `custom_fields.list` | denied | none | `capability_disabled` |

   No `state/ghl-public-capabilities.json` exists in the worktree, the run root, or
   `~/.openclaw`, and no loader for it exists in the adapter. Enablement is therefore not a
   credential problem: it is the W04 capability-record build item.

Consequently: **no representative operation can be proven through the client path with the
current credential**, and the reason is not only the 403. Both a corrected credential and a
recorded capability for `(operation_id, tenant)` are required before any client-path read can
reach the network.

## 6. Exact owner action (Trevor — account/credential authority)

1. In HighLevel, open the **sub-account** `XCgFTEA1oDvsPnTqqgoB` → Settings → Private
   Integrations. Read which sub-account the existing `pit-…` currently in
   `GOHIGHLEVEL_API_KEY` belongs to. (The UI is authoritative; no API can reveal this.)
2. Then do exactly one of:
   - **If that PIT belongs to `XCgFTEA1oDvsPnTqqgoB`:** edit it and enable the scopes
     `contacts.readonly` and `locations.readonly` (add `users.readonly` only if user reads are
     wanted). Save.
   - **If it belongs to another sub-account:** create a new Private Integration Token inside
     `XCgFTEA1oDvsPnTqqgoB` with `contacts.readonly` and `locations.readonly`, and replace
     `GOHIGHLEVEL_API_KEY` in `~/.openclaw/secrets/.env` (and the gateway env store, which
     currently holds the same value). Alternatively, if the intended tenant is the PIT's
     sub-account, change `GOHIGHLEVEL_LOCATION_ID` to that sub-account's id instead.
3. Do **not** substitute, rotate, or borrow another client's PIT to force a pass; that is
   forbidden by the freeze and by client sovereignty.
4. Unblock acceptance (read-only, no mutation): `GET /locations/{id}` → 200 and
   `GET /contacts/?locationId=…` → 200, or after W04 `POST /contacts/search` → 200. Record the
   status lines only; never the bodies.

After step 2, the W04 capability-record item still has to land before the adapter will call
through; the credential fix alone does not make the client path live.

## 7. Sources checked, and what was not

Checked: `~/.openclaw/secrets/.env`, `~/.openclaw/.env`, `~/.openclaw/secrets/secrets.env`,
`~/.openclaw/service-env/ai.openclaw.gateway.env`, `~/.openclaw/secrets/donna-izzard.env`,
`~/.openclaw/secrets/janet-pinkney.env`; `public/auth.py`, `public/aliases.py`,
`public/operations.py`, `public/capability.py`, `public/adapter.py`; the official HighLevel
OpenAPI documents `apps/locations.json`, `apps/contacts.json`, `apps/users.json` and
`docs/oauth/Scopes.md`.

Not checked / not determinable from this box: the HighLevel agency UI (authoritative token
binding and scope list), any location id not present in the stores above, and the OAuth rail
(not attempted; it is a different credential class and would be substitution).

No token, no secret, and no customer data appear in this document.

## 8. Verification run for this artifact

```
python3 evidence/W11/check-gu022-scope-analysis.py
OK: registry, scopes, default-deny gate and no-secret checks passed
```

The check is offline, asserts the registry facts above, asserts the adapter denies the three
probed operations before transport, and asserts that no credential value from the operator's env
stores appears in either evidence file.

```
cd 44-convert-and-flow-operator/tools/engine
python3 -m pytest tests/test_public_aliases.py tests/test_public_capability_gate.py \
  tests/test_public_adapter_contract.py -q
77 passed, 679 subtests passed in 0.14s
```

Machine-readable fact record: `evidence/W11/ghl-111-scope-facts.json`.
