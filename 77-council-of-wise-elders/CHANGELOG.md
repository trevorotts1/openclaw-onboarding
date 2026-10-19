# Council of Wise Elders (77): Changelog

## v1.0.24: the runtime test collection states the platform it actually runs on

- `runtime/tests/core.test.ts` asserted the XDG data-directory default unconditionally, so it failed on macOS and Windows where `src/cli/paths.ts` documents and implements a per-platform default. The test now asserts the contract for the running platform: `~/Library/Application Support/BlackCEO/WiseElders` on darwin (and that `XDG_DATA_HOME` does not steer it), `%LOCALAPPDATA%\BlackCEO\WiseElders` on win32, XDG elsewhere.
- `runtime/tests/cli.test.ts` ran a bare `doctor --json` and asserted the not-ready contract, which is false on a machine with configured harness roots. The case now injects `createLocalHost({ ...opts, discoverRoutes: false })`, pinning the not-ready contract instead of per-machine state. Real route composition stays covered by the rp0461 cases in `cli-route-composition.test.ts`.
- `runtime/tests/context-integration.test.ts` and `runtime/tests/export-adapter.test.ts` read the real CWE-011 export package, which is external data that is not in this repository and must never be fabricated. When it is genuinely absent they now SKIP naming the exact missing path (`CWE011_EXPORTS_DIR` can point at a real package) instead of erroring or passing on absent data. No assertion was weakened or deleted: the real-data assertions still run whenever the package is present.
- QC: `npx tsc --noEmit -p tsconfig.json` exit 0; `node scripts/doctor.mjs` PASS; `node scripts/verify-cohort-parity.mjs` PASS; manifest and archive regenerated with `scripts/build-bundles.mjs`.

## v1.0.23: the installable tarball carries the chamber assets (W25-U001 packaging)

- `runtime/package.json` limited npm's `files` allowlist to `["dist"]`, so an install from a built tarball carried no `public/chamber` and the front door answered `GET /chamber/` with 404. The allowlist is now `["dist","public/chamber"]`, the only asset tree `front-door.ts` resolves.
- `runtime/tests/package-contents.test.ts` asserts that allowlist, so dropping `public/chamber` again fails the suite instead of shipping an archive that cannot serve the chamber.
- `runtime/public/chamber/RECEIPT.md` no longer claims `files` is `["dist"]` or that shipping through `npm pack` remains a separate release step; the receipt now states the measured allowlist and the pack/install/probe proof.

## v1.0.22: the real backend is composed (W22-U001) and one composition binds the durable service (W25-U001 Lane E)

### One composition binds the durable service (W25-U001 Lane E)

- The measured gap was between "code exists" and "Start creates a session, workers produce output, SSE streams events": a composition root built the store, journal, outbox and workers, but nothing bound the front door's admission sink, event-stream adapter or session reader, and the CLI wrote canonical session rows into a database the service never read.
- `runtime/src/cli/authorization.ts` now opens the installation's ONE canonical database, `<dataDir>/council.db`, instead of a separate `council-authorization.db`. Evidence before the change: a CLI `create` left `council.db` with 1 local `sessions` row and no `council_*` tables, while `council-authorization.db` held 1 `council_sessions` row and 1 `council_events` row; the service reader over `council.db` answered `NULL` with 0 journal rows. After the change `council.db` holds both the local and canonical rows, the service reader answers `FOUND` with 1 journal row, and no authorization database is created. The two schemas share the file because their table names are disjoint.
- `runtime/src/service/events.ts` is the accepted W21 event/session adapter: `journalEventStreamAdapter` replays committed journal rows and follows new ones, `repositorySessionReader` reads the canonical repositories, and `formatCouncilEventFrame` is the existing Command Center SSE wire format.
- `composeCouncilService()` / `startCouncilService()` now bind, in one call: the durable admission sink over `DurableOperationProducer`, the journal event stream adapter, and the repository session reader over the same store/journal/outbox the workers use. Unknown ids answer `404 SESSION_NOT_FOUND` on both the session and events routes; with nothing bound a bare `CouncilFrontDoor` keeps the historical `200 ui: "not_bundled"`, `501 EVENT_STREAM_ADAPTER_NOT_BOUND` and `503 ADMISSION_SINK_UNBOUND` answers byte-for-byte.
- The admission sink maps `{session_id, operation_id, payload}` onto the canonical `AdmissionCommand`; the payload carries the granted run id, frozen route snapshot hash, input hash and reservation. A missing field is a typed refusal: the service never invents a grant, a hash, a reservation or a session.
- Deliberation host bindings: `resolvePrincipal` (standalone owner) and `loadSeatBriefing` (installed advisor packs) are bound; `resolveTransport` is bound when a real route resolved, using the configured harness or OpenAI-compatible endpoint and resolving the credential only at flight time. `catalog` stays null unless the host supplies an adapted Skill 22 export, and `routeBudget` stays null because route discovery publishes `contextWindowTokens` only and this runtime has no verified token-to-byte conversion — both are named rather than guessed.
- `runtime/tests/service-session-journey.test.ts` 3/3 proves: CLI-created session visible to the reader, unknown id 404 on both routes, an SSE frame that matches its committed `council_events` row, a complete admission persisting one `council_jobs` row plus its outbox intent, an incomplete admission refused with nothing written, restart-equivalent recomposition returning the same state and rows, and the unchanged unbound shape.

### The real backend is composed (W22-U001)

- W20 proved the honest-probe mechanism but left `store`, `route`, `routeCallable` and `worker` unbound on purpose, so the service still reported `usable: no` about a running process. The composition modules were merged and waiting; this entry binds them.
- `runtime/src/service/composition.ts` now opens one canonical SQLite handle at `<dataDir>/council.db`, applies the additive `council-0001` schema (all 18 Section 16.2 tables), records the standalone installation profile, and builds `CouncilRepositories` — which constructs the `EventJournal` and the `ProjectionOutbox` over that same handle.
- The supported route path is reused, not reinvented: the selected route id resolves read-only through `discoverConfiguredRoutes` / `resolveRouteForDispatch`; with no id, exactly one composable route is accepted and two or more is `ROUTE_SELECTION_AMBIGUOUS`. The guarded provider dispatch port is bound by the host launcher; offline readiness checks its presence and makes zero provider calls.
- `composeDeliberationService` composes the durable runner, jobs, budget ledger, grants and admission over the same handle, and one `startCouncilWorkers` supervisor runs over that runner. `stop()` stops the supervisor (awaiting in-flight work) and closes the handle exactly once; the timers are unref'd and no child process is spawned.
- Readiness observations now cite real state: `store` = 18/18 canonical tables present with journal and outbox bound; `route` = the selected route configured and its dispatch port bound; `worker` = supervisor running, poll generation observed and the durable budget ledger readable. `ui`, `discovery`, `executable` and `packs` are unchanged from W20. A bare `CouncilFrontDoor` keeps the byte-identical unbound shape.
- The four deliberation host bindings (material catalog, trusted-principal resolver, transport resolver, verified route budget) stay honestly unbound with their exact file and line recorded in the unit receipt; `DeliberationService.readiness()` therefore reports not-ready and no completed deliberation or live advisor turn is claimed. `GET /api/council/sessions/<id>/events` still answers `EVENT_STREAM_ADAPTER_NOT_BOUND`; the event stream is W21's unit.
- Advisors and book-persona mappings are byte-identical to the base commit; `front-door.ts`, `readiness.ts`, `sessions.ts`, `landing.test.ts` and `service.test.ts` are untouched.

## v1.0.21: a real event-stream adapter injection point, and a falsifiable session route

- The merged service answered `GET /api/council/sessions/<id>/events` with an unconditional `501 EVENT_STREAM_ADAPTER_NOT_BOUND`, and `GET /council/<id>` with `200 ui: "not_bundled"` for ANY id including `does-not-exist-123`, which made an earlier "real session URL" proof unfalsifiable.
- `runtime/src/service/front-door.ts`: `FrontDoorOptions` gains optional `eventsAdapter` and `sessionReader` injection points. With an adapter bound, the events route serves `200 text/event-stream` from committed frames only (replay plus optional follow) in the accepted Command Center SSE wire (`id: <sequence>` / `event: <type>` / `data: <json>`). Unbound, the exact `501 EVENT_STREAM_ADAPTER_NOT_BOUND` response is unchanged.
- With a session reader bound, `GET /council/<id>` answers `404 SESSION_NOT_FOUND` for an id the durable store does not know, and `200` with that session's data for one it does. With no reader injected, the historical `200 ui: "not_bundled"` body is preserved byte-for-byte.
- New `runtime/src/service/events.ts` supplies the injection contracts plus `journalEventStreamAdapter` (canonical `EventJournal.list` under an injected envelope) and `repositorySessionReader` (canonical `CouncilRepositories.getSession`). It opens no database, reads no credential and calls no network; a read failure is retried from the same cursor, never replaced by a synthetic frame.
- Cross-unit dependency recorded, not edited: `composition.ts` lives on `unit/W22-U001-composition-root`. That root must pass `eventsAdapter` and `sessionReader` to `CouncilFrontDoor` before these routes are live in the composed service.
- Base-vs-head loopback probe is byte-identical while unbound: `/` 302 `/chamber/`, `/status` 200, `/chamber/` 200, `/council/s1` 200 with `UI_NOT_BUNDLED`, `/api/council/sessions/s1/events` 501 `EVENT_STREAM_ADAPTER_NOT_BOUND`, `/nope` 404.
- QC: typecheck exit 0; new `front-door-events.test.ts` 6/6; `service.test.ts` + `landing.test.ts` 20/20; full runtime suite 430 tests / 423 pass / 7 fail with the failing names identical to a fresh detached worktree at the base commit.

## v1.0.20: the composition root moves into the repository (W20-U001, F5)

- The only working wiring of the front door lived outside the repository in a hand-written host launcher that called `new CouncilFrontDoor({ identity, host, ports })` and bound no readiness probe. `readiness.ts` honestly reports every unbound layer as `unknown` with `READINESS_PROBE_NOT_BOUND` (and `ui` as `blocked` with `UI_NOT_BUNDLED`), and `usable` is true only when every layer is `ready`, so the status page printed `usable: no` with six unbound layers about a service that was actually running. The real composition modules were merged but never wired into the front door.
- Adds `runtime/src/service/composition.ts`, the canonical composition root inside the repository. `composeCouncilService()` builds the identity, creates the durable data directory, binds the probes and the owning authority's `admissionSink` (when supplied), and returns the door without listening. `startCouncilService()` starts it exactly as the host launcher did, optionally installs SIGTERM/SIGINT shutdown, and returns a stop handle. The module imports no `child_process`, reads no `process.env`, makes no network call at module load and creates nothing until called.
- Binds only what this slice can observe truthfully, and each probe fails honestly instead of asserting ready: `ui` resolves the packaged asset `runtime/public/chamber/index.html` from the module's source or compiled layout; `discovery` makes a loopback-only `GET /api/council/service/identity` against the bound origin and requires a structurally valid, owner-matching document; `executable` observes `process.execPath` on disk plus the resolvable `tsx` CLI (`tsx/package.json` → `dist/cli.mjs`); `packs` resolves all nine advisor pack folders and their ten required files under the installed skill root. `store`, `route`, `routeCallable` and `worker` stay deliberately unbound: they need a real store, composed provider route and supervised worker. With this root a loopback probe reports discovery/executable/packs/ui `ready` and store/route/worker `unknown` with `READINESS_PROBE_NOT_BOUND`; `usable` stays `false` because a truthful unknown is never a ready.
- `runtime/src/service/index.ts` re-exports the root. `front-door.ts`, `readiness.ts`, `sessions.ts`, `service.test.ts` and `landing.test.ts` are byte-identical to the base commit; adding the root required no change to the front-door contract because `FrontDoorOptions.readiness` and `admissionSink` already accepted the composition.
- A deployment that has not adopted the root is unchanged: with no probes bound the readiness output keeps exactly the pre-change shape (six `unknown` layers with `READINESS_PROBE_NOT_BOUND`, `ui` `blocked` with `UI_NOT_BUNDLED`, `usable: false`). Identity and health routes keep identical status codes and bodies, proven against a bare front door on the same identity.
- `runtime/src/service/composition.test.ts` 5/5: the bound probe set, the unbound default shape, byte-identical identity/health routes, admission-sink delivery, and start/stop without signal handlers. Typecheck `npx tsc --noEmit -p tsconfig.json` exits 0. The full runtime suite keeps its control counts (430 tests / 423 pass / 7 known pre-existing failures with the same names as a worktree at the base commit). Events still answer 501 `EVENT_STREAM_ADAPTER_NOT_BOUND`: the event stream adapter and a live session journey are not claimed here.
## v1.0.19: the URL opens the Council chamber, not a status report

- The merged service served `GET /` as the developer status page while the packaged chamber sat unreferenced at `runtime/public/chamber/` — no link on that page reached it, so the URL Trevor opens showed identity hashes, six `READINESS_PROBE_NOT_BOUND` layers and three loopback links that are dead on a phone.
- `runtime/src/service/front-door.ts`: when the packaged chamber entry page resolves (`public/chamber/index.html`), `GET /` answers `302` with the relative `Location: /chamber/` — never an absolute loopback URL. The chamber itself is untouched; `/chamber/` still serves `index.html` with no `UI_NOT_BUNDLED` text.
- The previous diagnostics page moves unchanged to `GET /status`: same identity table, same readiness table, same `UI_NOT_BUNDLED` and `EVENT_STREAM_ADAPTER_NOT_BOUND` notices, same routes list. Nothing is lost; the report is simply no longer the front door.
- Without the packaged assets the root keeps the honest status page, so a build that has not shipped the chamber never breaks: `/` answers 200 diagnostics and `/chamber/` still falls through to the unchanged `SERVICE_ROUTE_NOT_FOUND` 404.
- Every other route is unchanged: `/api/council/service/identity` 200, `/council/<id>` 200 with `ui: "not_bundled"`, `/api/council/sessions/<id>/events` 501 `EVENT_STREAM_ADAPTER_NOT_BOUND`, unknown paths 404. The event stream remains unbound; that is the next unit's job and is not claimed here.
- `runtime/src/service/landing.test.ts` asserts the new contract: the 302 and its relative `Location`, `/chamber/` 200 without the diagnostics banner, `/status` 200 carrying the full diagnostics, the no-assets fallback (asset directory temporarily parked and restored inside the test), the byte-identical existing routes, and the unchanged unknown-path 404.

## v1.0.18: the Council chamber itself — WER-021 full packaging

- The merged service served `GET /` as a status report while the chamber did not exist: `GET /chamber/` returned `404 SERVICE_ROUTE_NOT_FOUND`, so an authenticated phone on the public origin landed on a report page instead of the Council. This entry ships the chamber.
- Adds `runtime/public/chamber/` — 25 self-contained files: `index.html` (nine seats, persistent fictional-sample labelling), `advisors.html` (nine seats, 11 `bibliographic_only` labels), `not-packaged.html`, three stylesheets and 18 advisor portrait SVGs. The three stylesheets are byte-identical to the Command Center council styles (16905 / 7384 / 5963 bytes, 3/3 match) and all 18 portraits byte-identical to the Command Center portraits (18/18 match). Zero `<script>`, zero `fetch(`, zero `url(`, zero `https://` in the directory; the only absolute URLs present are 18 SVG `xmlns="http://www.w3.org/2000/svg"` namespace declarations. No operator home path appears anywhere in them.
- `runtime/src/service/front-door.ts` gains a static-asset route under `/chamber/` (and `/chamber`), keeping the catch-all 404 for everything else. Traversal probes all refused with the unchanged catch-all: `/chamber/../package.json`, `/chamber/%2e%2e/package.json`, `/chamber/portraits/%2e%2e%2fpackage.json`, `/chamber/portraits/../../front-door.ts`.
- Every existing route is proven byte-identical in behaviour by a base-vs-head loopback probe against both worktrees: `GET /` 200 text/html, `/nope` 404 `SERVICE_ROUTE_NOT_FOUND`, `/api/council/service/identity` 200, `/council/s1` 200 with the `UI_NOT_BUNDLED` blocker, `/api/council/sessions/s1/events` 501 `EVENT_STREAM_ADAPTER_NOT_BOUND`.
- Pages that cannot ship without the Command Center database and its tenant gate are named with their exact blocking dependency in `runtime/public/chamber/RECEIPT.md` and are served as `not-packaged.html` rather than faked: `/council` (needs `resolveTenantContext` plus `src/lib/council/store.ts`), `/council/<sessionId>` (needs a persisted session and the durable event journal), the Command Center's own `/council/advisors` route (a static roster copy ships instead), `/council/history`, `/council/new`, `/council/settings`.
- QC: typecheck exit 0; `landing.test.ts` + `service.test.ts` 17/17 exit 0 with both files untouched; full runtime suite 430 tests / 423 pass / 7 fail, with the 7 failure names byte-identical to a fresh detached worktree at the base commit (all ENOENT on a pre-existing fixture), so the control, not the change, explains them.

## v1.0.17: a real landing page at GET / (WER-023 authenticated origin)

- The authenticated public origin returned a JSON 404 at `/` - observed live as `{"code":"SERVICE_ROUTE_NOT_FOUND","detail":"No service route for GET /."}` - because the merged WER-021 slice ships no UI and never had a root route.
- `runtime/src/service/front-door.ts` now serves `GET /` as a self-contained HTML status and session page: service identity and readiness from the data the service already holds, the routes that actually work as links, and an explicit `UI_NOT_BUNDLED` notice naming WER-021 full packaging as the path to the real chamber. The catch-all 404 is unchanged for every other unknown path, and all existing routes keep byte-identical behaviour (identity 200, session 200, events 501).
- The page loads **no external asset**: no `<script>`, no `<link>`, no CDN, no font, no network fetch - it renders offline. Independent QC injected a hostile readiness detail carrying an absolute operator home path and an external `evil.example.com` URL; both were redacted in the served HTML (path to `~`, URL to `[external-url-redacted]`), proving operator paths cannot reach the page.
- New suite `landing.test.ts` 4/4; `service.test.ts` still 13/13; typecheck 0.

## v1.0.16: WER-028 final cohort receipt, and a manifest-drift fix

- Records the WER-028 final integration receipt under `evidence/wer028/`: cohort presence proven by tree/blob comparison rather than ancestry (squash and merge-commit merges make ancestry the wrong test), all four version markers asserted equal, required-check state captured per repository with SKIPPED separated from pass, branch-protection state captured for all three repositories including the 999-setup 404, MALCOM's books/personas/portraits proven byte-identical against the pre-session baseline, Skill 76 proven untouched, cross-repository seam schema hashes compared on both sides, and a deferred list naming every item that remains unproven on this hardware.
- **Fixes a manifest drift this skill introduced on main.** The previous rebuild ran while untracked `evidence/wer028/` scratch files sat in the working tree, so `manifest.json` recorded 16 paths that were never committed: `doctor.mjs` and `verify-cohort-parity.mjs` both FAILED on a clean checkout of main (computed 569 files vs recorded 585). Those 16 paths are now genuinely committed, and every build is re-run only after `git status --porcelain` is empty. The rebuild procedure now carries that guard explicitly.

## v1.0.15: runnable supervisor driver and live crash/restart acceptance (WER-026)

- Adds `scripts/supervisor/runner.mjs`, the missing entry point. The merged supervisor was a pure reducer with no main: `supervisor.mjs` declared `NATIVE_ADAPTER_BINDING = {status: UNKNOWN, bound: false}` and `sweep-executor.mjs` took injected functions, so nothing could actually run - which is exactly why the scheduled-sweep and crash/restart receipts had never existed. The driver wires the existing modules with a durable data directory, an interval loop driving `executePlannedSweep` through an injected execute that only records receipts, a durable restart ledger, singleton/lease refusal for a second instance, atomic graceful drain on SIGTERM, and `--once` for deterministic tests. It imports no `child_process`, no network module and no credential, and reads no `process.env`.
- Fixes a **real defect found by independent QC**: the entry-point guard compared `import.meta.url` to `pathToFileURL(process.argv[1]).href`, which is false whenever the script is reached through a symlink - the process then exited 0 having done nothing, with no tick, no data dir and no output. Because macOS makes `/tmp` a symlink to `/private/tmp`, that was not a rare path. Both sides are now resolved with `realpathSync` (falling back to the lexical path when resolution fails), and a regression test invokes the runner through a symlink and asserts a real sweep happens.
- Records the live host acceptance under `evidence/wer026/host/`, independently reproduced by the reviewer from a fresh clone rather than accepted from the builder's artifacts: two completed sweep ticks; `kill -9` mid-tick (exit 137) followed by a restart that reconciled the pending action **exactly once** with `ledger_generation` 1 to 2 and `fencing_generation` 2 to 3; a second concurrent instance refused with `LEASE_HELD` at exit 3; SIGTERM draining to a valid `STOPPED` state file at exit 0; a temp-root snapshot proving zero writes outside the data directory; and `ps` proving no process left running.

Supervisor suite **113/113** with the pre-existing **99/99** preserved.

**Nothing here claims LaunchAgent registration, launchd firing or reboot persistence** - the launchd step is performed separately by the operator and is not proven by this entry.

## v1.0.14: RP-046-4 card-contract conveyance repair (DEFECT-046-C)

- Closes the D-021 canary Round 1 block where five of nine seats returned parseable JSON whose content still failed the card schema after the one permitted repair. The cause was conveyance, not validation: two format rules (`challenges_answered` entries must be opaque IDs; `conditions[].due_at` must be a UTC ISO 8601 timestamp or null) existed only as zod refinement messages, and the JSON Schema generated from the same definitions **drops refinements**, so in the schema the model actually receives those fields are plain strings — the rules reached the model nowhere. The complete required-field list existed only as the schema's `required` array buried in the input payload, and Round 1 issues no challenge IDs at all, so the model had to guess what `challenges_answered` should hold.
- Adds `runtime/src/cli/card-contract.ts`: the exact contract for *this* call, stated in prose, composed into the request and restated in full in the repair instruction. Required field names are read from the same generated JSON Schema the validator enforces, so the prose list can never drift from the enforced contract. Per-call challenge issuance is stated explicitly, and an advisor call with no issued challenges must return `challenges_answered: []` rather than guess.
- Repair instructions now carry **both** the verbatim validator errors and the original constraints, as Section 15.5 requires; previously only the error strings were forwarded, so every failed seat failed again in the same shape.
- Adds `runtime/tests/rp0464-card-conformance.test.ts` and the accepted-card fixtures under `runtime/tests/fixtures/rp0464/` (`accepted-brene-brown.json`, `accepted-dennis-kimbro.json`, `accepted-michelle-obama.json`, `accepted-russell-brunson.json`).
- Only what the model is *told* changed. The validator, the schemas, the single permitted repair, the ledger and the lease behavior are all unchanged: a non-conforming card still fails validation in exactly the same words as before. `runtime/src/cli/engine.ts` is modified only to compose the contract into the request and the repair.

## v1.0.13: Windows platform observers (WER-027 engineering half)

- Closes the deliberate Windows gap the platform adapter carried: `mounts.ts` previously returned `BLOCKED_PLATFORM` with "no mount table observer" on anything that is not Linux, and `identity.ts` marked Windows `unobservable`.
- Adds `runtime/src/platform/windows.ts`: persistent-versus-ephemeral volume classification using observable `statfs` facts and the drive letter, so a data directory under the Windows Temp root is **refused with a concrete reason naming the path and the rule**; a path resolving *through* a junction is judged by its resolved target, so a temp junction onto a real drive is classified by its destination and a real path reaching temp via a junction is still refused; an uncharacterizable or UNC network volume returns `BLOCKED_PLATFORM` rather than a silent pass; paths containing spaces and non-ASCII characters are handled exactly, with case-insensitive segment boundaries that never prefix-match a sibling (`C:\\Data2` is not inside `C:\\Data`).
- Service identity now records the observable `USERNAME` / `USERDOMAIN` / `COMPUTERNAME` values and keeps the honest `unobservable` marker when none resolve - a name is never invented. Unknown container state returns the explicit `BLOCKED_PLATFORM` path rather than assuming "not a container".
- New suite 14/14; the pre-existing platform suite is unchanged at 16/16 and Linux/macOS behavior is byte-for-byte preserved.

**Nothing here was executed on Windows.** No Windows host and no PowerShell exist on the authoring machine, so every behavior is proven by tests against injected facts, not by running on Windows. Real NTFS geometry, real fixed-versus-removable drive type (no native `GetDriveTypeW` without a shell or native addon), real junction/8.3 resolution, real Windows container detection and an end-to-end `win32` run remain **deferred to a real Windows host** and are not claimed.

## v1.0.12: WER-026 local acceptance receipts (install/update/rollback and 3-round journey)

- Records real acceptance evidence under `evidence/wer026/local/`: the actual installer run into an isolated prefix with staged immutable releases, a repeat install proven byte-identical (prefix diff 0 bytes over 1559 lines), a second build moving the activation pointer while the previous release stayed usable, rollback restoring the prior release, harness invocation from an unrelated working directory returning byte-identical results, no service registered, no launchd loaded and no process left behind, and a model probe reported honestly as `BLOCKED_ENVIRONMENT` (`probe` exits 3 `COUNCIL_FEATURE_NOT_READY` — the dispatcher route is unimplemented and no production code imports `model-probe.ts`).
- Records the create-to-verdict journey under `evidence/wer026/journey/`: three rounds completed with real session ids (`sess-w11u002-round1/2/3`), nine seats x three rounds x nine pack versions in real SQLite state, replay and export delta-0 across all 19 authorization tables, duplicate create refused with `COUNCIL_STATE_CONFLICT`, process restart preserving session ids, cross-round isolation (`COUNCIL_SESSION_NOT_FOUND` across data dirs) and byte-identical round-1 exports across repeats.
- Each receipt was independently re-run by the reviewer in its own scratch prefix rather than accepted from the builder's narrative.

## v1.0.11: platform adapter, remote Access identity, cohort-parity detector

- Adds the OpenClaw VPS/container platform adapter (`runtime/src/platform/`): persistent versus ephemeral mount detection that **refuses** a data directory on a replaceable tree with a concrete reason and an explicit unobserved/`virtiofs` state surfacing as `BLOCKED_PLATFORM` rather than a guess, container-vs-host loopback disambiguation that refuses to treat the current container's `127.0.0.1` as the host, UID/service-identity resolution instead of assuming `localhost`, free-port selection that reuses the WER-021 front door and **never kills** an unrelated listener, and a durable handoff (`wise-elders.platform-handoff/v1`) that restores sessions and reservations across a recreate with zero duplicates. Suite 16/16; the 7 pre-existing runtime failures are unchanged against a detached control worktree at base.
- Adds the WER-023 application-side remote identity adapter (`runtime/src/remote/`): RS256 verification of the Cloudflare Access JWT against an injectable JWKS source with `iss`/`aud`/`exp`/`nbf` enforcement, so **an arbitrary forwarded identity header never establishes identity** — it is read only after a JWT verifies. Exact allowed-origin set membership (never suffix matching), a single-owning-endpoint session URL resolver that can never emit two candidates, customer-disabled operation that keeps local/managed working, reauthentication that resumes the same session with **zero** billable Starts, connection loss that is never reinterpreted as cancellation, and cross-user refusal that leaks neither user nor session existence. Suite 13/13 with zero network calls asserted. Real device acceptance remains deferred to WER-026/027.
- Adds the read-only cohort-parity detector (`scripts/verify-cohort-parity.mjs`): recomputes the manifest tree hash exactly as `build-bundles.mjs` does, asserts all three version markers agree with the newest CHANGELOG entry, and catches the G3 condition (skill content moved without `skill-version.txt`). Exits nonzero naming the offending file and expected value; writes nothing and makes zero provider calls. Suite 9/9, script suite 35/35.

## v1.0.10: standalone Council front-door service

- Adds the standalone persistent service (`runtime/src/service/`): layered readiness with zero provider calls when offline, duplicate-start protection that reuses only a **verified matching** service and refuses an unrelated listener without killing it, true verified session URL return with browser-open failure preserving the URL, and graceful drain on stop.

## v1.0.9: waves 5-6 cohort (route discovery, durable budgets, capability probe, supervisor HYB-03/04)

- Discovers Council routes from the actual OpenClaw host layout (`runtime/src/cli/route-discovery.ts`): non-default config and state roots without any `~/.openclaw` assumption, JSON5 host configuration, named secret **references** that resolve only at flight time with the value asserted absent from errors, logs and receipts, explicit failure for unsupported API families and ambiguous model selection with no silent substitution, and freezing through the WER-006 snapshot contract so downstream transport consumes one shape.
- Adds durable budgets (`runtime/src/budgets/`) and wires them into the CLI host (`runtime/src/cli/local-host.ts`, `budget.ts`, `leases.ts`): the tightest applicable ceiling wins over runtime defaults, per-operation reservations commit before dispatch, lease fencing generation flows from the durable store rather than a process-local counter, unknown outcomes stay reserved while known-rejected ones release, and renewal adds capacity without erasing history. Two concurrent admissions against one bound produce exactly one winner across separate store instances.
- Adds the historically-unready bounded capability probe (`runtime/src/cli/model-probe.ts`): purpose-bound grant, route snapshot verified before any spawn, operation/attempt identity recorded before launch, and three distinct outcomes — attempted, answered, schema-qualified — so a refused, failed, malformed or timed-out probe can never set a callable success state. One token never qualifies a complete Council.
- Extends the engineering supervisor with HYB-03 and HYB-04 (`scripts/supervisor/`): deterministic health collection, staffing comparison with expiring underfill exceptions, an incident/action journal with counters that survive restart, a QC-backlog trigger, launchd plist and validated start/status/stop/restart command arrays as artifacts (nothing registered or loaded), an independent due+30s overdue detector that fires even with a live PID, and restart reconciliation over durable pending actions. Supervisor suite: 99/99 (47 original preserved).

## v1.0.8: wave-3 cohort (subprocess transport, approval front door)

- Adds the platform-safe bounded subprocess transport (`runtime/src/cli/`): a structured executable resolver handling native binaries, Windows `.cmd` shims and supported PowerShell invocation without assuming WSL, bash shebangs or symlinks; per-request model/effort and profile config pinned rather than read from a mutable global; prompt content delivered **only** on stdin and never interpolated into a shell string; bounded output, enforced deadlines, abort propagation and whole child-process-tree cleanup on cancellation. A Windows path containing spaces and non-ASCII characters resolves byte-intact in the simulated-resolver tests.
- Records `operationId` and `attemptId` **before** launching, so a timeout is recorded as potentially-dispatched rather than safe-to-retry. A route snapshot failing `verifyRouteSnapshotHash` is refused before any spawn.
- Adds the approval front door (`runtime/src/authorization/`): fingerprinting over the entire normalised approval command — ceilings, expiry, parent/renewal linkage and route options — so an exact retry returns the original committed receipt while a changed option under the same idempotency key conflicts **before** any write. Preview-to-session association is validated, so submitting one session's preview to another's approval URL performs zero grant, state or event writes even under the same owner. Revoked and expired authority both refuse without mutating. Reuses the existing grant service; Council spending authority stays distinct from development merge permission and from action-plan execution authority.

## 1.0.7 - 2026-10-18

Integrate four supplied Oprah and Les book mappings, partial source qualification and governance discovery. Publish the verified 105-persona index. Preserve the landed 1.0.5 queue/supervisor and 1.0.6 route-snapshot/installed-CLI implementations; regenerate the combined distributable.

## v1.0.6: wave-2 cohort (frozen route snapshot, installed-CLI bridge)

- Freezes the normalized route snapshot contract (`runtime/src/providers/`, schema `wise-elders.route-snapshot/v1`): session owner, route and account reference, host/config selection, API family, requested model or combination alias, permitted members and fallbacks, requested / supported / applied reasoning kept distinct, capability version, policy hash and rate/concurrency limits. Configured identity and transport-reported identity are separate fields, and an unreported provider member stays explicitly `UNKNOWN` rather than being assumed. The snapshot carries a stable hash that WER-007, WER-008 and WER-009 consume instead of inventing their own route shapes.
- Pins the member **set** while excluding per-member transport evidence from the pin body, so recording evidence later can never move the pin on a combination route. `withTransportReportedIdentity` now also recomputes authoritatively rather than re-asserting the stale published stamp.
- Resolves the installed Council CLI through the WER-004 release receipt (`runtime/src/bridges/`), independent of the current working directory or a checkout's `dist` folder, and propagates route-discovery diagnostics and the real route catalog through the bridge wrapper instead of swallowing them. A missing or invalid receipt fails with a concrete recovery action, and a failed browser open preserves the usable URL.
- Replaces a frozen `readdirSync` directory literal in the bridges test with a membership check that still fails on a missing module and on a stray file, so a deliberate addition no longer breaks it.

## v1.0.5: wave-1 repair cohort (supervisor, installer, durable producer)

- Adds the engineering supervisor bootstrap (`scripts/supervisor/`): a deterministic ~60s health observer, a 600s full-sweep planner written as a pure function over injected time, durable leader/fencing-generation state, and the STARTING/HEALTHY/DEGRADED/PAUSED/STOPPING/STOPPED machine with the explicit-stop fence. Policy ships as `wise-elders.hybrid-supervisor-policy/v2` with `binding_status: TEMPLATE_NOT_BOUND`. Native-adapter binding is deliberately left `UNKNOWN` rather than invented.
- Rewrites `scripts/install-runtime.mjs` so the exact-executable Node prerequisite probe (`node:sqlite` in-memory write/read/close plus an isolated persistent reopen) runs before any file is written, installs into a staged immutable external prefix, hashes protected SOURCE only — never `node_modules` or `dist` — and activates atomically while preserving the previous receipt.
- Adds the canonical durable operation producer (`runtime/src/queue/`): admission commits transition, job and event/outbox in one owning-store transaction, a QUEUED row without its job is rejected, `attemptOrdinal` survives restart and `leaseGeneration` is rechecked on every mutable commit. No second scheduler was introduced.

## v1.0.4: Russell retained-source intake

- Registers DotCom Secrets and Expert Secrets via Skill22 and binds ten original paraphrases to retained-source hashes and edition-specific locators.
- Records primary-teaching coverage for both Russell anchors without upgrading other seats, semantic evaluation, full-book certification or installed readiness.
- Preserves private-source exclusions and publishes the approved two-persona incremental index as prebuilt-index-v2.4.3 (101 personas / 1,441 rows), with every prior row unchanged.

## Unreleased: final packaging (CWE-039)

No version change: versions are taken at merge time only. This entry
records the final packaging of the complete package whose runtime and
nine advisor packs landed in their own units after the v1.0.0
scaffold.

- Runtime and packs: the deliberation runtime, the standalone CLI,
  and all nine advisor packs ship in this package. Every pack's
  qualification is bibliographic_only (CWE-042); config/advisors.json
  pack_status now reads built_bibliographic_only for all nine seats.
- Distributable archive: scripts/build-bundles.mjs now generates
  council-of-wise-elders.skill at packaging. The archived Brunson
  pack copy has the private_scope items removed and prose references
  to them scrubbed (CWE-012 acceptance condition 3); the source tree
  retains the private-scope record.
- Install path: scripts/install-runtime.mjs performs the real
  isolated pinned install plus build (INSTALL.md Step 4), and
  INSTALL.md Step 9 states the live-acceptance terms for the built
  package, including the INSTALLED_NOT_LIVE_VERIFIED record when no
  live run is authorized.
- Housekeeping: the Wave 6 roster comment in lib-onboarding-state.sh
  and the structural test banner no longer describe the package as a
  scaffold with an unbuilt runtime.

## v1.0.0: Initial canonical scaffold

- Adds the agentskills.io-conformant SKILL.md with the fixed nine-seat
  roster, the exact Section 7 profile label discipline, and the Section
  20.1 front-door phrases with existing-session control resolution.
- Ships the portable package structure: install guide in the literal
  installer-contract order, instructions, examples, core updates,
  prereqs, configuration defaults, references (protocol, scoring,
  source policy, model routing, report template, install matrix,
  troubleshooting), and QC rubric plus bundled QC scripts.
- Registers the skill with the onboarding installer: glob discovery
  counts the folder, the Wave 6 roster in lib-onboarding-state.sh gains
  an explicit entry, the skill-department-map gains the skill 77 entry,
  and the Council deliberation SOP registers in universal-sops.
- Update-flow safety: no council state is stored inside the skill
  folder, so wholesale folder replacement by the update sync cannot
  destroy sessions, briefs, verdicts, or client knowledge.
- Honest scope: the deliberation runtime (runtime/), the standalone
  CLI, the Skill 22 exporter, and the nine advisor knowledge packs are
  scaffolded and marked not-yet-built. They are owned by their own
  build units and are not simulated here. The front door reports the
  council as not ready until they land.
