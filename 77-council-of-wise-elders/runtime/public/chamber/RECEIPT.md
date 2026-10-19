# W18-U001 / WER-021 full packaging — investigation receipt

Base: `origin/main` at `f032bde1c3888065ad54411da1f8a8db8a7fe624`
(Skill 77 v1.0.17, which added the `GET /` status landing page).

This receipt is written BEFORE implementation so the discovery survives even
if implementation stops early. Source repositories inspected read-only:
`trevorotts1/openclaw-onboarding` (worktree) and `blackceo-command-center`
(read-only reference, never modified).

## (a) Command Center council page inventory and dependencies

| Route | Source | Imports that need a server or the CC database |
|---|---|---|
| `/council` | `src/app/council/page.tsx` → `CouncilPageShell`, `CouncilHome` | `CouncilHome` imports `@/lib/council/journey-client` and calls `listSessions()` + `getCapabilities()` → `GET /api/council/sessions`, `GET /api/council/capabilities` |
| `/council/[sessionId]` | `src/app/council/[sessionId]/page.tsx` (`'use client'`) | `next/navigation` `useSearchParams`, `CouncilApiClient` → `GET /api/council/sessions/<id>`, `GET /api/council/sessions/<id>/verdict`; `FetchCouncilSessionTransport` → `GET /api/council/sessions/<id>/events?snapshot=1&after=…` and an `EventSource` stream; `@/lib/council/contracts` types |
| `/council/advisors` | `src/app/council/advisors/page.tsx` (`'use client'`) | `CouncilApiClient.getAdvisors()` → `GET /api/council/advisors` (nine-seat roster + per-seat qualification from the council API) |
| `/council/history` | `src/app/council/history/page.tsx` (`'use client'`) | `getCapabilities()` + `listSessions()` + `getSession()` + `getVerdict()` → four council API reads; rerun comparison needs two live sessions |
| `/council/new` | `src/app/council/new/page.tsx` → `DecisionComposer` (`'use client'`) | `@/lib/council/journey-client` `getModels()` + `createSession()` → `GET/POST /api/council/*`; also `@/lib/council/providers` route catalogue types |
| `/council/settings` | `src/app/council/settings/page.tsx` (`'use client'`) | `CouncilApiClient.getSettings()` → `GET /api/council/settings` (the endpoint answers typed `FEATURE_NOT_READY`) |

Server-side pieces behind those reads: the council API routes resolve the
tenant/principal through `src/lib/auth/tenant-context.ts`, then read the
Command Center database through `src/lib/council/store.ts` /
`src/lib/council/persistence/**`. Any static export that needs session lists,
session detail, verdicts, advisors-as-served, or settings therefore needs BOTH
the CC database and a verified tenant identity. Neither is available to a
standalone static page.

### Exact gate for a request from `council.zerohumanworkforce.com`

`src/middleware.ts` applies two layers:

1. **Layer 1 (Cloudflare Access, opt-in via `REQUIRE_CF_ACCESS`)** — verifies
   `Cf-Access-Jwt-Assertion` when enabled. Not the observed refusal in the
   current CC response.
2. **Layer 2 page gate** — for `GET`/`HEAD` page navigations,
   `isInterviewGateExempt(pathname)` (middleware.ts:244) is checked. Its
   exempt list is exactly `/interview`, `/onboarding`, `/preview`,
   `/settings`, `/social-theme`, `/participant`, `/api/`, `/_next/`, and any
   path whose last segment contains a dot. **`/council` is not on that list.**
   The middleware then calls `resolveTenantContext(request)`
   (`src/lib/auth/tenant-context.ts:276`), which:
   - resolves the host through `tenantRegistration(host)`; an unregistered
     host throws `TenantAccessError('Hostname has no configured tenant')`
     unless the host is loopback or the box's own `CC_PUBLIC_URL` host;
   - requires one of: matching `Bearer MC_API_TOKEN`, a valid
     `mc_tenant_session` grant, a cryptographically verified Cloudflare
     Access JWT (`cf-access-jwt-assertion`, RS256/JWKS, exact registered
     subject or allowed signed email), or the non-production local trust flag.
   - throws `TenantAccessError('A verified tenant identity is required')`
     when none is present.

   The throw is caught at `middleware.ts:832` and returned as
   `tenantRefusalResponse(...)` with `error: 'tenant_access_required'`, HTTP
   **403**. That is exactly the observed CC behaviour: a request arriving
   from the `council.zerohumanworkforce.com` origin with no CC session/CF
   Access identity is refused at the edge middleware before any council page
   renders. The API reads the pages make (`/api/*`) pass through the same
   tenant resolution and additionally rewrite client-kind hosts onto
   `/api/tenant-board/*`.

Conclusion: the CC council UI is not a self-contained artifact. Every journey
page is a thin client over authenticated, database-backed council APIs.

## (b) Honest static-export feasibility

Feasible from fixtures alone (client-side, no server):

| Surface | Source of truth | Why it can be static |
|---|---|---|
| Nine-seat chamber room | `src/components/council/council-room-fixtures.ts` `SAMPLE_ROOM_VIEW` (explicitly synthetic, `mode: 'sample'`), `council-room-types.ts` roster + locked slot geometry, `council-theme.ts` `COUNCIL_SEAT_SLOTS` | Pure render of typed fixture data; the code's own fixture contract requires the persistent "Fictional sample" badge |
| Advisor roster | `council-room-types.ts` `COUNCIL_SEAT_ROSTER` + `77-council-of-wise-elders/assets/portrait-manifest.json`; pack qualification is `bibliographic_only` in the skill's advisor packs | Roster identity and qualification are static data in this repo; no API required |
| Round stepper / reading view | `RoundStepper.tsx`, `CouncilReadingView.tsx`, same fixture room | Pure render of the same typed fixture |

Not feasible without the CC database / authenticated council API:

| Route | Exact blocking dependency |
|---|---|
| `/council` (home session list) | `GET /api/council/sessions` + `GET /api/council/capabilities`; needs verified tenant (`resolveTenantContext`) + CC database (`src/lib/council/store.ts`) |
| `/council/[sessionId]` | `GET /api/council/sessions/<id>` + `/verdict` + `/events` live SSE; needs a real persisted session and the durable event stream |
| `/council/advisors` as served by CC | `GET /api/council/advisors`; needs verified tenant. (A static roster copy IS feasible from the skill's own advisor packs and is shipped.) |
| `/council/history` | `GET /api/council/capabilities` + `/sessions` + two `/sessions/<id>` + two `/verdict`; needs real sessions |
| `/council/new` | `getModels()` (`GET /api/council/models`) and `createSession()` (`POST /api/council/sessions`); needs provider route discovery and a durable write |
| `/council/settings` | `GET /api/council/settings`; endpoint is typed `FEATURE_NOT_READY` in CC and still requires the authenticated API |

**Verdict:** a full faithful packaging of the CC council journey is NOT
achievable as a self-contained static export. The honest subset is a
fixture-driven chamber (room + reading view) plus a static advisor roster.
The remaining pages are deliberately NOT shipped as blanks or fakes; the
blocking dependency for each is named above and repeated in the served page.

## (c) Implementation scope chosen

- New static assets only under `77-council-of-wise-elders/runtime/public/chamber/`.
- One additive route branch in `src/service/front-door.ts` under `/chamber/`.
  `GET /`, the catch-all 404, identity, session and events routes are
  untouched.
- Assets are self-contained: no CDN, no external font download, no script,
  no runtime network fetch, and no operator home path.

## Implementation outcome (appended after the investigation above)

Shipped under `77-council-of-wise-elders/runtime/public/chamber/`:

| File | What it is |
|---|---|
| `index.html` | Fixture-driven nine-seat chamber room (locked ellipse geometry, `SAMPLE_ROOM_VIEW`, persistent "Fictional sample" badge) plus the full-text reading view |
| `advisors.html` | Static nine-seat roster built from the skill's portrait manifest and advisor packs; every seat labelled `bibliographic_only` |
| `not-packaged.html` | Explicit route-by-route list of what this slice does not package and the exact blocking dependency |
| `RECEIPT.md` | This receipt |
| `council-theme.css`, `council-room.css`, `council-journey.css` | Verbatim copies of the Command Center council stylesheets (no external reference; checked with `grep -E '@import|url\(|https?://'` → no matches) |
| `portraits/*.svg` | Verbatim copies of the 18 Command Center medallion SVGs (9 large + 9 small) |

One additive route branch was added to `src/service/front-door.ts`:
`GET /chamber` and `GET /chamber/` serve `index.html`; a fixed allowlist
serves the HTML/CSS/`RECEIPT.md` files; `portraits/<name>.svg` is served by a
strict filename regex. Any miss falls through to the unchanged
`SERVICE_ROUTE_NOT_FOUND` catch-all. `GET /`, identity, session, events and
admission behaviour were not edited.

### Pages NOT shipped (named again, with the blocking dependency)

`/council`, `/council/<sessionId>`, `/council/advisors` as served by CC,
`/council/history`, `/council/new`, `/council/settings`. The exact blocking
imports/endpoints are in the table in section (b) above and in
`not-packaged.html`. They are not shipped as blanks or fakes.

### Test evidence

Commands run from `77-council-of-wise-elders/runtime/`:

| Command | Result |
|---|---|
| `npx tsc --noEmit -p tsconfig.json` | exit 0 |
| `node --import tsx --test src/service/landing.test.ts src/service/service.test.ts` | exit 0, 17 tests, 17 pass, 0 fail (run after the commit, so the landing scope proof sees a clean worktree) |
| `node --import tsx --test tests/*.test.ts tests/scenarios/*.test.ts` | exit 1, 430 tests, 423 pass, 7 fail — byte-for-byte the same 7 pre-existing failures as the base run at `f032bde1c` (export-adapter CWE-011 path/adaptation cases, CLI doctor honesty, XDG paths, Brunson private-scope record) |

Live loopback proof (no external network): started `CouncilFrontDoor` on an
ephemeral port and fetched `/chamber/`, `/chamber`, `/chamber/advisors.html`,
`/chamber/not-packaged.html`, the three stylesheets, one portrait SVG and
`RECEIPT.md` — all 200 with the expected content type; `/chamber/nope.json`,
`/chamber/../package.json` and a traversal portrait path all returned the
existing 404 shape; `/`, identity, session and events kept their prior
status/body. Playwright rendered the page at 1280×900 and 390×844: phone view
turns the room into the designed two-column grid, `scrollWidth ===
innerWidth` (no horizontal scroll), and the network log contains only
same-origin `/chamber/*` requests — no CDN, font or foreign origin.

Packaging: the runtime `package.json` `files` field is
`["dist", "public/chamber"]`, so an npm tarball carries the chamber. It was
`["dist"]` when this receipt was first written, which left `npm pack --dry-run`
returning 2 entries with no chamber files; that defect was fixed in
`unit/W25-U001-packaging` (runtime/package.json plus a `package-contents` guard
test), verified by packing, installing into a throwaway prefix and probing the
path `CHAMBER_ASSET_ROOTS` actually resolves. The asset resolver still covers
the source tree, the tsc `dist/service` output and the single-file `dist`
bundle.

