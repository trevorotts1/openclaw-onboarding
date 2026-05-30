# ZHC Pixel Protocol (Feature 49) — INSTRUCTIONS Step 9.43

**Status:** MVP / scaffold. The pixel JS, the generator, the OpenClaw hook wiring, the
Pixel Concierge agent + AGENTS.md protocol, the behavioral trigger rules, the privacy
controls, the JSONL data contract, the scope precheck, and the scope-gated Cloudflare
deploy are all SHIPPED in this skill. The one thing that is deliberately **GATED, not
auto-run** is the **live per-client Cloudflare deploy** — it requires the operator's CF
token to carry Pages/Workers scopes; `scripts/25-verify-pixel-prerequisites.sh` HALTS
with a clear message if they are missing. See "MVP vs production follow-ups" at the end.

UNIVERSAL — zero personal/client data. Every concrete value below is a placeholder:
`<PUBLIC_HOSTNAME>`, `<CLIENT_DOMAIN>`, `<SITE_ID>`, `<AGENT_ID>`, `<LOCATION_ID>`.

---

## 1. What the ZHC Pixel is

Every client gets THEIR OWN private visitor-signal pixel. It is **not** a shared
analytics service. The pixel is a small JavaScript snippet the client pastes on their
site; it watches anonymous visitor behavior and POSTs batched signals to **their own**
OpenClaw gateway over **their existing Cloudflare tunnel**:

```
visitor browser
   │  (batched JSON every ~5s, anonymous-but-persistent visitor id)
   ▼
pixel.<CLIENT_DOMAIN>            ← a hostname added to the client's EXISTING tunnel
   │  (Cloudflare edge; optional Worker for batching / rate-limit)
   ▼
their OpenClaw gateway  /hooks/pixel-visitor-signal
   │
   ▼
Pixel Concierge agent (<AGENT_ID>)   ← evaluates behavioral trigger rules
```

No visitor data ever touches a shared/operator-owned collector endpoint. The data lives
in the client's own OpenClaw master-files dir as JSONL (see §7) and, on identification,
in the client's own GHL.

The pixel template lives at `templates/zhc-pixel/zhc-pixel.template.js` with the
placeholders `__ZHC_PIXEL_ENDPOINT__` / `__ZHC_PIXEL_SITE_ID__` / `__ZHC_PIXEL_AGENT_ID__`.
The generator `scripts/26-render-pixel-js.sh` renders a per-client file.

---

## 2. Identification — what IS and is NOT possible (legally compliant; never fabricate)

This is the section the agent must internalize. **The agent NEVER invents a visitor
identity.** Identification is server-side, retroactive, and first-party only.

### Possible (and how)

- **First-party form linkage.** The moment a visitor EVER submits a form on the client's
  own site (or GHL captures their contact), the pixel's anonymous `visitor_id` is tied to
  that GHL contact **forever**. From then on, every prior and future browsing signal for
  that `visitor_id` attaches to the known contact.
- **Cross-device linkage (same email = same person).** If the same email is captured on a
  second device, the two `visitor_id`s collapse to one GHL contact server-side. This is
  email-equality only — never inferred from behavior.
- **Anonymous → known, retroactively.** While anonymous, signals are stored against the
  `visitor_id`. On the FIRST identification event, the previously-anonymous history
  attaches to the now-known contact (the Pixel Concierge backfills the contact's
  `ZHC_*` fields and timeline).

### NOT possible (say so plainly; refuse to fabricate)

- **Cold-anonymous name lookup.** You CANNOT turn a never-identified visitor into a name.
  There is no reverse lookup from a browser fingerprint to a person.
- **Gmail / Facebook / social direct lookup.** You CANNOT query Google, Meta, or any
  third party to resolve an anonymous visitor. The pixel has no such access and it would
  not be legal.
- **IP → identity.** Coarse geo from IP is a HINT for F45 geo-qualification only; it is
  never a person.

If asked "who is this anonymous visitor?", the honest answer is: *"They haven't
identified themselves yet — I can see what they're interested in, and the moment they
fill out anything, I'll connect the dots."* **Never guess a name.**

---

## 3. The OpenClaw hook — `pixel-visitor-signal`

`scripts/27-configure-pixel-hook.sh` registers a `hooks.mappings` entry (idempotent,
same jq-safe pattern as `15-configure-hooks-mappings.sh`):

- `id` / `match.path`: `pixel-visitor-signal`
- `action`: `agent`, `agentId`: the Pixel Concierge agent `<AGENT_ID>`
- `sessionKey`: `hook:pixel:<site_id>:<visitor_id>` (allowed prefix `hook:pixel:`)
- `deliver: false` (the agent acts via GHL / widget, never echoes the signal back)
- `messageTemplate`: instructs the agent to evaluate the trigger rules in §4, drop
  bot-like traffic with ZERO model spend, and only engage when a rule fires.
- A model is set on the mapping (cheap real-time tier — most signals are dropped before
  any reasoning).

The hook does NOT reply to the browser with content; it returns `200 {ok:true}` and the
agent does its work out-of-band (GHL tag/field write, widget directive, email schedule).

---

## 4. Behavioral trigger rules (operator-configurable)

Defaults shipped in `openclaw.json` under `skill38.zhc_pixel.triggers.*`. The agent
applies them on every `pixel-visitor-signal` envelope, in this order:

1. **Bot-like → SILENTLY DROP (no tokens).** Sub-2-second pageview cadence, impossible
   scroll velocity, missing/headless UA, or a known-bot UA → drop before any LLM call.
   Tag (only if a contact exists) `ZHC-pixel-bot-suspected`. This MUST be first so junk
   traffic never costs a reasoning call.
2. **Known customer on an account/login page → NO engagement.** If the `visitor_id` maps
   to an existing customer and the page is account/billing/login, do nothing.
3. **Pricing page > N minutes (default 3) → offer chat widget.** Surface the chat widget
   with a soft, context-aware opener.
4. **Clicked a contact/booking element → preempt with the widget.** `intent_hint:
   "contact"` → open the widget before they finish navigating.
5. **4th return to the SAME page → soft outreach.** `total_visits` high on one path →
   a low-pressure outreach (widget if anonymous; if known, a short follow-up).
6. **Cart abandonment → 1-hour email.** `intent_hint: "checkout"` then exit without a
   purchase signal → schedule a single follow-up email at +1h (only if known/identified;
   anonymous carts get a widget nudge instead).
7. **Comparison-shopping (3+ service/product pages in a session) → consultation offer.**
   Offer a consultation/quote via the widget or a known-contact message.

Every threshold is operator-configurable; OFF a rule by setting its toggle false. The
agent **always** prefers the least-intrusive action and respects quiet hours (Step 0.5),
compliance keywords (Step 0.7), and the honesty floor.

### Tags written (programmatic → ZHC- prefix, per Step 9.42)

- `ZHC-pixel-visitor` — a contact who has been seen by the pixel.
- `ZHC-pixel-returning-visitor` — `total_visits >= 2`.
- `ZHC-pixel-high-intent` — fired a high-intent rule (pricing dwell / contact click /
  comparison shopping).
- `ZHC-pixel-bot-suspected` — bot-like (only applied if a contact already exists; never
  creates a contact for a bot).

### Custom fields written (programmatic → ZHC_ prefix, per Step 9.40, create-if-missing)

- `ZHC_first_visit_date` (date)
- `ZHC_total_visits` (number)
- `ZHC_pages_viewed` (text — comma-joined recent paths, capped)
- `ZHC_high_intent_signal` (text — the rule name that fired, e.g. `pricing_dwell`)

Field discovery/validation/create reuse the F46 CRM-field-write mechanism
(`GET/POST /locations/<LOCATION_ID>/customFields`).

---

## 5. The Pixel Concierge agent

A NEW dedicated agent (`<AGENT_ID>`, e.g. `pixel-concierge`) registered by
`scripts/27-configure-pixel-hook.sh`. Why a separate agent and not `main`:

- **Scoped allow-list.** The Pixel Concierge is allowed to act ONLY on chats it is
  triggering — its hook session keys (`hook:pixel:*`) and the widget/GHL actions the
  trigger rules permit. It is NOT a general operator agent.
- **Cost isolation.** It runs the cheap real-time model; most signals are dropped before
  reasoning, so it stays inexpensive.
- **Behavioral protocol.** Its rules live in the AGENTS.md `STEP_1_45_PIXEL_CONCIERGE`
  marker block (inserted by `scripts/05-update-agents-md.sh`), pointing back to this
  protocol. The block is concise; the detail lives here (never inline the full ruleset
  into AGENTS.md).

The agent's allow-list (`hooks.allowedAgentIds` includes the Pixel Concierge id;
`hooks.allowedSessionKeyPrefixes` includes `hook:pixel:`) is set in the same config merge.

---

## 6. Cloudflare deploy (scope-gated)

The deploy is CODE that ships; running it live is GATED on the operator's CF token
carrying the right scopes. Two scripts:

### `scripts/25-verify-pixel-prerequisites.sh` — the precheck (run FIRST)

Inspects the CF token via the API (`GET /user/tokens/verify` + a permissions probe) and
HALTS with a clear operator message if any of these are missing:

- **Pages:Edit** (host the rendered pixel JS on a CF Pages project)
- **Workers Scripts:Edit** (optional edge batching/rate-limit Worker)
- **Workers Routes:Edit** (bind the Worker to `pixel.<CLIENT_DOMAIN>/*`)

These are the SAME scopes Feature 52 needs. On a missing scope the precheck points the
operator to the token-instructions Google Doc:
`https://docs.google.com/document/d/1A_U-H-MMLh2mQ_zhzLxK_tKmFyPNb7i0FNvxjJ4SVpo/edit`
(the "Cloudflare Pages/Workers permissions" section). It also confirms the prerequisites
the deploy needs: an existing tunnel (from Step 1) and an identified domain.

### `scripts/28-deploy-pixel-cloudflare.sh` — the deploy (scope-gated, idempotent)

Refuses to run unless the precheck passed (`ZHC_PIXEL_SCOPES_OK=1` in the run-state, or
`--force` with operator confirmation). When authorized, it:

(a) adds `pixel.<CLIENT_DOMAIN>` as an ingress hostname on the client's EXISTING tunnel
    (reusing the tunnel id from `13-create-cloudflare-tunnel.sh`) + a proxied CNAME;
(b) creates/reuses a CF **Pages** project to host the rendered pixel JS;
(c) deploys the rendered JS via the API;
(d) OPTIONALLY deploys a CF **Worker** for edge batching/rate-limit and binds a **Workers
    Route** `pixel.<CLIENT_DOMAIN>/ingest*` → Worker → tunnel origin. The Worker attaches
    the hooks bearer token server-side (so the token never lives in the browser bundle).

If scopes are missing the deploy does NOT silently fail — it exits non-zero with the same
Google-Doc pointer. **The code ships; the deploy is gated** (owner directive).

---

## 7. Data contract — visitor-event JSONL (Feature 52)

The Pixel Concierge appends every received envelope's events to:

```
<MASTER_FILES_DIR>/pixel-events/YYYY-MM-DD.jsonl
```

One JSON object per line. Every line carries `timestamp` (ISO-8601 UTC), `event_type`,
and the event `data`, plus the envelope identity. Schema:

| Field | Type | Notes |
|---|---|---|
| `timestamp` | string (ISO-8601 UTC) | when the event occurred in the browser |
| `event_type` | string | `pageview` \| `scroll` \| `click` \| `page_hidden` \| `delete_request` |
| `site_id` | string | `<SITE_ID>` (per-client) |
| `agent_id` | string | `<AGENT_ID>` (Pixel Concierge) |
| `visitor_id` | string | anonymous-but-persistent first-party id (NOT a person) |
| `fingerprint` | string\|null | short non-reversible soft fingerprint; null under DNT |
| `path` | string | page path |
| `referrer` | string\|null | document.referrer |
| `seconds_on_page` | number | session dwell at emit time |
| `total_visits` | number | first-party return-visit counter |
| `first_visit_date` | string (ISO-8601) | first-party first-seen |
| `data` | object | event-specific (`depth_pct`, `intent_hint`, `text`, `href`, …) |

Worked example line (anonymous pricing dwell):

```json
{"timestamp":"2026-05-30T15:04:22Z","event_type":"scroll","site_id":"<SITE_ID>","agent_id":"<AGENT_ID>","visitor_id":"a1b2c3d4e5f6","fingerprint":"k9x2","path":"/pricing","referrer":null,"seconds_on_page":185,"total_visits":2,"first_visit_date":"2026-05-28T10:11:00Z","data":{"depth_pct":80}}
```

`delete_request` (CCPA opt-out) lines instruct the agent to purge that `visitor_id`'s
stored signals on the next nightly pass.

---

## 8. Privacy compliance (non-negotiable)

All enforced in `zhc-pixel.template.js` and documented for the operator:

- **GDPR consent.** Nothing is sent until consent is granted. The pixel defers behind the
  host page's CMP, or its own built-in banner (`grantConsent()` / `denyConsent()`). No
  consent → no cookie, no fingerprint, no POST.
- **CCPA opt-out.** `window.ZHCPixel.optOut()` permanently disables, clears the cookie +
  local state, and POSTs a `delete_request` event.
- **Do-Not-Track.** If `navigator.doNotTrack=='1'` (or msDoNotTrack/window.doNotTrack),
  the pixel does NO fingerprinting, sets NO cookie, and sends NOTHING. Hard stop at boot.
- **Data deletable on request.** The `delete_request` event + the nightly purge give the
  client a documented deletion path. Operators should expose an opt-out link.
- **Privacy-policy note.** The client MUST add a one-line note to their privacy policy
  ("We use a first-party analytics cookie to improve your experience; opt out here.").
  The generated install instructions remind them.

### Token handling

The hooks bearer token is NEVER baked into the browser bundle. Either the edge Worker
attaches `Authorization: Bearer <token>` server-side, or (Worker-less mode) the tunnel
ingress is configured to require it at the gateway and the Pages-hosted JS posts to a
path the Worker fronts. The browser bundle posts the signal envelope only.

---

## 9. Auto-install flow

`scripts/25-verify-pixel-prerequisites.sh` decides the path:

- If `CLOUDFLARE_API_TOKEN` present + an existing tunnel detected (from Step 1) + a domain
  identified + the Pages/Workers scopes present → the operator can run
  `27-configure-pixel-hook.sh` then `26-render-pixel-js.sh` then `28-deploy-pixel-cloudflare.sh`
  to auto-provision end-to-end.
- If ANY prerequisite is missing → the precheck PAUSES and tells the operator EXACTLY
  what is needed (no silent failure), with the Google-Doc pointer for the CF scopes.

After deploy, the operator gets a one-line `<script>` snippet to paste on their site:

```html
<script src="https://pixel.<CLIENT_DOMAIN>/zhc-pixel.js" async></script>
```

(`26-render-pixel-js.sh` prints the exact snippet with the client's hostname filled in.)

---

## 10. Interaction with other Skill 38 features

- **F44 (Step 1.42 interrupts):** a `pixel-priority` interrupt trigger lets a live chat
  detour to handle a high-intent pixel signal, then return. (Already referenced in the
  F44 protocol's trigger list.)
- **F45 (Step 2.0 geo-qualification):** pixel/IP is the FIRST location HINT — still a
  hint, always confirmed by asking.
- **F46 (Step 2.5 CRM field write):** the `ZHC_*` pixel fields use the F46 create-if-
  missing mechanism.
- **F50 (Step 1.35 aggression):** unaffected — pixel signals are not chat messages.

---

## MVP vs production follow-ups (honest scaffold status)

SHIPPED (working code in this skill):

- Pixel JS template + generator (renders per-client, placeholder substitution).
- OpenClaw `pixel-visitor-signal` hook registration + Pixel Concierge agent + scoped
  allow-list (`27-configure-pixel-hook.sh`).
- AGENTS.md `STEP_1_45_PIXEL_CONCIERGE` behavioral protocol (via 05-update-agents-md.sh).
- Behavioral trigger rules + `openclaw.json` toggles.
- Privacy controls (GDPR/CCPA/DNT/deletion) in the browser bundle.
- JSONL data contract (F52) + documented schema.
- Scope precheck (`25-verify-pixel-prerequisites.sh`) + scope-gated CF deploy
  (`28-deploy-pixel-cloudflare.sh`).
- QC gate `qc-zhc-pixel.sh` (CI + pre-handoff).

STUBBED / GATED / production follow-ups (honest):

- **Live per-client Cloudflare deploy is GATED, not auto-run.** It requires the operator's
  CF token to carry Pages/Workers scopes; the precheck HALTS otherwise. This is by design
  (owner directive) — the deploy code ships but is not executed without scopes.
- **Edge Worker batching/rate-limit is OPTIONAL and minimal.** `28-deploy-pixel-cloudflare.sh`
  ships a small inline Worker; production tuning (rate-limit thresholds, abuse rules,
  KV-backed dedup) is a follow-up.
- **Server-side identity resolution / cross-device email-collapse is documented and the
  agent behavior is specified, but the nightly backfill job is a LIGHT scaffold** — it
  reads the JSONL and writes GHL fields/tags on trigger; a full dedup/identity-graph store
  is a future enhancement (F52 territory).
- **`delete_request` purge is a documented nightly behavior**, not a hardened compliance
  pipeline; clients with strict DSAR SLAs should layer a dedicated deletion workflow.
- **The pixel's soft fingerprint is intentionally weak** (privacy-bounded). It is a cookie
  survival hint, not a precise device tracker — by design.
