# Drama Song Ad Factory mini-app — Studio UI (Unit U3, version 0)

The client-facing studio for the drama song ad. Wave 1a, version 0.

Service home: `75-drama-song-ad-factory/mini-app/`. This unit owns **`mini-app/ui/`
only**.

## What is here (version 0)

| File | What it is |
|---|---|
| `index.html` | The page shell: skip link, progress bar, section nav, focusable `<main>`, polite live region. |
| `studio.css` | Warm palette tokens (light + dark), focus ring, reduced-motion guard, 16px gutter, no horizontal scroll. |
| `studio.js` | The five pages, the eight options, the QR surface, the "Looks good" state, and the delivery download. |
| `qr.js` | A dependency-free QR generator (byte mode, EC level M, versions 1..10). Inline SVG, no CDN. |
| `download.js` | The one place that decides whether a delivery link is an **actual download**. |
| `api-client.js` | The whole U2 service boundary — the entrypoints the page consumes. Implements no service behaviour. |
| `push.js` | **U20, OPTIONAL (version 2).** The web-push surface. **Not imported by `studio.js` or `index.html`**, so version 0 is unchanged. |
| `package.json` | `{"type":"module"}` marker so the checks import the shipped modules unchanged. |
| `checks/` | The runnable proofs (see below). |

### The five pages

1. **Start** — what the client is buying and how the four steps go.
2. **Your eight answers** — the option surface (offer, audience, star, length, music,
   look, quality, budget), native radio groups with real labels.
3. **The recap** — the numbered card, the **"Looks good — start my video"**
   confirmation state, and a QR surface beside the chosen look sample.
4. **Your approvals** — script, song (pick 1 of 3), storyboard. Each ends in its own
   "Looks good" state that stays on the page after it is taken.
5. **Your premiere** — the delivery download, the clips, and a QR surface for the
   share link.

## The U2 dependency, stated plainly

The UI consumes the SERVICE and implements none of it. Keys, inbox, uploads,
retention, per-client isolation, lifecycle/timer precedence and the
one-operator-record-per-client-per-day rule all belong to **U2**.

**This unit was built against the stated interface, not a live one.** The U2
branch was not open as a pull request at build time (no `unit/U2-U1` branch or PR
existed on `origin`), so the interface could not be read from it. The contract
this UI codes against is the shape stated in the U2 unit text — service side owns
keys / inbox / uploads / retention / isolation / lifecycle — rendered concretely
in `api-client.js` as nine named entrypoints:

```
getSession, saveAnswer, getOptions, listInbox, postInbox,
requestUpload, advance, getDelivery, verifyDeliveryLink
```

When U2 lands, `globalThis.studioService` is the single injection point. Until
then the page boots, draws every screen and says, in words, that nothing can be
saved yet — it never pretends.

## The trap this unit closes: a redirect is not an actual download

`download.js` accepts a delivery link only when, on the exact URL the client
taps, it gets **HTTP 200** (a 3xx is refused outright — redirects are never
followed), **`Content-Disposition: attachment`**, a positive **`Content-Length`**,
that many bytes actually arriving, and a media/binary **`Content-Type`**. A share
link that bounces to a landing page — or even to the real file — is not a
download, and the button stays disabled with the reason written above it.

## Accessibility covered

Covered and asserted by `checks/a11y-check.mjs` (32 rules, light and dark):

- WCAG contrast computed from the real stylesheet tokens; every text pair clears
  **4.5:1** in both themes;
- a real `<label>` for every input, and an `id` on every input the page builds;
- **focus order is source order** — no positive `tabindex` anywhere;
- changing page **moves focus to the new page heading**;
- a visible `:focus-visible` ring, never removed;
- every state is announced in a polite live region, and **no state is carried by
  motion or colour alone** — each has words beside it;
- motion is guarded by `prefers-reduced-motion`;
- the QR is `role="img"` with an accessible name, and the same link is written out
  in plain text underneath it as the real alternative;
- skip link, `lang`, viewport, focusable `<main>`, labelled nav and progressbar,
  and a `<noscript>` fallback.

Not covered (no false claims): a real browser and a screen reader. The check is
static plus computed, and `checks/README.md` says so in the same words.

## Run the checks

```bash
cd 75-drama-song-ad-factory/mini-app/ui
bash checks/run-all.sh          # all four; exit 0 = pass, 2 = a check failed
```

Individual checks:

- `node checks/ui-contract.mjs` — the version-0 surface exists and imports cleanly.
- `node checks/a11y-check.mjs` — the accessibility floor above.
- `node checks/qr-roundtrip.mjs` — the QR really scans (decoded by an independent decoder).
- `node checks/download-bytes-check.mjs` — real bytes, with the redirect-only negative control.

## U20 — the OPTIONAL web-push surface (version 2, never a version-0 gate)

Joint plan line 1091: `| U20 | Optional web push | U3 | onboarding planned
service | U3; never version-0 gate |`. Line 832: `none blocks version 0`.

`push.js` is the browser side of that optional feature:

- **OFF by default.** `pushSurfaceState()` returns `{ show: false }` unless it is
  handed `enabled: true` (from the service's `GET /api/studio/push`) **and**
  `supported: true`. `enablePush()` refuses and asks the browser nothing unless
  `enabled` is exactly `true`.
- **Inert for version 0.** `studio.js` and `index.html` do **not** import it. A
  version-0 studio behaves exactly as it did before U20 existed.
- **No key material here.** The page handles only its own subscription object and
  the service's **public** VAPID key; no private key, endpoint secret or service
  key is ever read, held or written by this file.

Its behaviours are proved by the service-side prover
`mini-app/service/prove/prove_push_optional.mjs` (cases `U20_UI_OFF_BY_DEFAULT`
and `U20_UI_NEVER_ASKS_UNSOLICITED`), with a planted-bad control in
`mini-app/service/prove/planted-bad.sh`.

## Not this unit

`mini-app/service/` (U2), the deploy files (U4), and pairing / admin / key /
cutoff (U12) are other units' paths. This unit writes none of them, and keeps no
service state of its own.
