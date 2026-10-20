# WER-026 acceptance slice B - create-to-verdict journey (W11-U002)

Real local run of the Council runtime built from the pinned base commit. No host
service, no Command Center database, no network, no client credentials.

- Unit: `W11-U002`
- Repo: `trevorotts1/openclaw-onboarding`
- Base: `main @ 53d772a996835c783927f900cb6a6880948e60a3` (Merge PR #2269)
- Worktree: `lanes/W11-U002-lane/repo` (detached HEAD at the base commit)
- Runtime: Node `v24.21.0`, npm `11.19.0`
- Build: `npm run build` (tsc + esbuild) exit `0`;
  `runtime/dist/blackceo-council.mjs` sha256
  `a85987869541f51398c3a05aabda4234986c13e00ddfa0f1a2f63ad5bf352172`
- Repository source files changed: **none**. `git status --porcelain` =
  `?? 77-council-of-wise-elders/evidence/`

## Entry points actually used

1. **Runtime CLI built from the pinned commit**
   `node <worktree>/77-council-of-wise-elders/runtime/dist/blackceo-council.mjs`
   for `doctor`, `create`, `authorization preview/approve`, `status`,
   `verdict`, `replay`, `export`, `resume`, `pause`.
   The installed `~/.local/bin/blackceo-council` exists on this box but
   execs a different installed runtime prefix, so it was **not** used for
   any acceptance step.
2. **Runtime dispatcher `runCli()` for `start` only**
   `lanes/W11-U002-lane/bin/start-driver.mts` imports the product dispatcher
   and supplies an injected `LocalHost` that (a) registers the runtime's own
   `DeterministicFixtureTransport` for the frozen route and (b) resolves one
   scoped grant. Two real product limits force this for a no-network,
   no-credential slice:
   - the production host composes only routes discovered from the machine's
     live configuration, which would be a network/provider path;
   - headless approval is refused: `authorization approve` returned exit `3`
     `RUN_AUTHORIZATION_REQUIRED` - *"Headless approval is refused: no
     controlling-terminal confirmation is available and no standing grant
     was presented."* (logged raw).

   All downstream work - spec/brief validation, the three protocol rounds,
   seat-pack loading, scoring, verdict, event journal, replay, export - is
   the real product code in the pinned commit. The transport is the
   runtime's labeled deterministic fixture, so no model inference is claimed.

## Counts actually achieved

| Item | Achieved | IDs |
|---|---|---|
| Rounds (create → start → status → verdict → replay → export) | 3 | `sess-w11u002-round1`, `sess-w11u002-round2`, `sess-w11u002-round3` |
| Advisor packs exercised per round | 9 | `simon-sinek`, `td-jakes`, `oprah-winfrey`, `tiffany-aliche`, `russell-brunson`, `michelle-obama`, `brene-brown`, `dennis-kimbro`, `les-brown` |
| Cards per round | 27 (9 seats × protocol rounds 1, 2, 3) | one row per `(round, seat)` |
| Core export invocations (md, json, json-repeat per round) | 9 | 3 per round |
| Total export invocations recorded | 12 | extra round-1 exports were used for the delta and DB-isolation measurements |
| Packs referenced by each exported report | 9 seats / 9 distinct `source_pack_versions` | see `journey.json` `export_report` |

Verdicts (all `validation_status=valid`, `ratification_status=ratified`,
label `WAIT`, recommended option `B`):

| Round | Preview ID | Verdict content sha256 | Events at final replay |
|---|---|---|---|
| 1 | `b52da920-cc8a-4b99-9079-8b8df81344aa` | `ed32838faacca18372b899890cc026758da16085a1fe5b0a464718924e125924` | 74 |
| 2 | `87ddb164-ca4d-44b5-b6a1-b06c8a93ee4b` | `e566837a34b40e778011ec66551bff0cb9b5cc5332473f0e3e68604b6c747d5f` | 71 |
| 3 | `480aaae0-a365-420c-97f8-f5ed9ae0e925` | `5a798ecfb1db08de2ff820b3934de95dc6e5a7cb6572fe240ba0024ee9976da6` | 71 |

## Durability and idempotency (measured)

- **Replay delta 0** for sessions/cards/verdicts/checkpoints
  (`before == after`; events also unchanged).
- **Export delta 0** for sessions/cards/verdicts/checkpoints. Export adds
  exactly **one** `operation_completed` (`kind: report_export`) journal event
  per call, by design - not a task or session.
- **Authorization store delta 0** across an export: every `council_*` table
  in `council-authorization.db` unchanged (`council_sessions`, `council_jobs`,
  `council_task_links`, `council_run_previews` included).
- **Duplicate create** of the same spec+brief: exit `3`
  `COUNCIL_STATE_CONFLICT`, session count remains `1`.
- **Restart**: three separate CLI processes per round returned the identical
  session id, `COMPLETED`, `state_version=10`; no duplicate sessions.
- **Failed / interrupted rounds**:
  - invalid spec/brief hash: exit `2` `COUNCIL_INVALID_INPUT`, 0 sessions;
  - start with an unaccepted grant ref: exit `3`
    `RUN_AUTHORIZATION_REQUIRED`, session stays `DRAFT` (v0), 0 cards,
    0 verdicts; a later process gets `COUNCIL_VERDICT_NOT_READY` (exit 3)
    and a duplicate create is refused (exit 3) - it is not adopted;
  - SIGKILL mid-start (exit `137`): session left `ROUND_1` (v4), 1 card,
    2 checkpoints, 0 verdicts; later `start` exit `3`, `resume` exit `3`,
    `verdict` exit `3`. Nothing resumes it silently.

## Cross-round isolation

- Round 2 data dir: `status` and `pause` of round 1 both exit `3`
  `COUNCIL_SESSION_NOT_FOUND`; round 3 likewise.
- Each round directory holds exactly one session and 27 cards.
- Round 1 exports are **byte-identical** before and after round 3:
  - md `f25aef15c85899cbb86a144e827d36104b28b5683aabc92a4f2d5ba916886f65`
  - json `e8f2bc79d473a8f4ba84918bae85f17984ff96809b71d23bbb332203e5b34a68`
- Repeated `export --format json` is byte-identical within every round.

## Bounds honored

- Only local filesystem and the runtime's own SQLite stores
  (`<lane>/data/roundN/council.db`, `council-authorization.db`).
- The Command Center database and `src/lib/council` were never opened.
- No system service registered, no launchd job loaded.
- No long-lived daemon; every invocation was one short CLI process.
- `HOME` was an empty lane directory for all CLI calls; the driver sets
  `discoverRoutes:false`, so no host route configuration or credential
  reference was read. The transport is in-process and makes no network call.
- No client box, client credential, or provider key touched.
- No process left behind: `ps` matches for the lane = 0.
- No `pm2 jlist` / `pm2 describe` was run.

## Deferred (not claimed)

Two scheduled sweeps, supervisor restart recovery, a browser session URL, a
production worker claiming a real `council_run`, and any live model call.

## Observation (not a blocker for this slice)

With the deterministic fixture transport, `status` reports
`provider_requests consumed: 0` while 27 cards were produced. The fixture is
test-only and never billed; it is not evidence about live-provider budget
accounting. Live budget/wiring remains deferred to the installed/live slices.

## Files

- `journey.json` - machine-readable receipt for all three rounds
- `raw/logs/` - verbatim command outputs, replay/verdict JSON, delta counts,
  failed-round evidence, environment and export hash manifest
- `raw/exports/` - the exported reports referenced by the hash assertions
- `raw/fixtures/` - the exact spec/brief/route-snapshot inputs
- `verify-journey.mjs` - runnable self-check over the recorded evidence:
  `node verify-journey.mjs` (exit 0, 24 PASS lines)

## Reproduce

```sh
# offline build (node_modules copied from an existing identical lockfile checkout)
cd <lane>/repo/77-council-of-wise-elders/runtime && npm run build

# inputs
cd <lane> && ./repo/77-council-of-wise-elders/runtime/node_modules/.bin/tsx bin/make-fixtures.mts

# per round N = 1..3
CLI="node <lane>/repo/77-council-of-wise-elders/runtime/dist/blackceo-council.mjs"
HOME=<lane>/home $CLI create --spec fixtures/session-roundN.json \
  --brief fixtures/brief-roundN.json --data-dir <lane>/data/roundN --json
HOME=<lane>/home $CLI authorization preview sess-w11u002-roundN \
  --route-snapshot fixtures/route-snapshot-roundN.json --data-dir <lane>/data/roundN --json
HOME=<lane>/home ./repo/77-council-of-wise-elders/runtime/node_modules/.bin/tsx \
  bin/start-driver.mts --data-dir <lane>/data/roundN --session sess-w11u002-roundN \
  --grant-ref grant-w11u002-roundN --spec fixtures/session-roundN.json \
  --brief fixtures/brief-roundN.json
HOME=<lane>/home $CLI status|verdict|replay sess-w11u002-roundN --data-dir <lane>/data/roundN --json
HOME=<lane>/home $CLI export sess-w11u002-roundN --format md|json \
  --out <lane>/export/roundN.md --data-dir <lane>/data/roundN --json

cd 77-council-of-wise-elders/evidence/wer026/journey && node verify-journey.mjs
```
