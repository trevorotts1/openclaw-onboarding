# Skill 71 run events and REPORT.json: the tracking contract

Status: **FROZEN v1.0** (fix plan Items 24, 25, 26; built by stream S6).
This document and its two machine-readable schemas are the contract the
Command Center importer, `/api/skill-runs`, and the board panel are built
against:

- `references/run-events.schema.json`: one event per JSONL line.
- `references/report-json.schema.json`: `REPORT.json`, the structured twin
  of `REPORT.md`.
- `references/run-events.example.jsonl` and
  `references/report-json.example.json`: one worked run carried through
  both formats (the same run, the same values).

Changes to either schema after this freeze are version changes: bump
`schema_version`, keep consumers tolerant of the previous version, and
never edit a field's meaning in place.

## 1. Why events, and who may emit them

A run's existence used to be knowable only from its own folder. Events fix
that, and their trust property is the point of the design: **events are
emitted by the gate (`stage_gate.py`) and the runner (`swarm_runner.py`)
at the moment of a state transition, never by agents.** An agent cannot
emit, edit, or backfill an event; the files below are append-only.

## 2. Where the lines live

| Place | Path | Written by |
|---|---|---|
| Run-local feed | `<run_dir>/private/run-events.jsonl` | the gate/runner, always |
| Host index | the file named by env `SKILL71_RUNS_INDEX` | the gate/runner, only when the variable is set |
| Ship spool | the directory named by env `SKILL71_RUNS_SPOOL` | the gate/runner on push failure (fleet-hostinger) |
| Command Center | `POST /api/skill-runs/ingest` | gate/runner push, or `scripts/ship_run_events.py` draining the spool |

Every event carries `event_id` (UUID, the dedupe key everywhere),
`event_type`, `schema_version`, `emitted_at` (UTC ISO-8601 from the
emitting host), and `run_id`. Lines written outside the run folder (host
index, spool, shipped payloads) additionally carry `run_dir`, the run
folder's absolute path on the emitting host. Consumers store `run_dir`;
they never resolve another machine's path locally.

If `SKILL71_RUNS_INDEX` is unset, nothing external is written and nothing
fails: the run-local feed is the whole story for that host.

### Per fleet shape (Amendment 1, Item 24 rider)

- **fleet-mac:** the index lives at
  `<openclaw-data>/skill71-runs/runs.jsonl` on the client's own Mac and is
  read locally. Command Center visibility is **opt-in only**: nothing is
  pushed unless the deployment sets `SKILL71_RUNS_SHIP_URL` (and the token
  file below). A fleet-mac run that never appears on the board is expected
  behavior, not data loss.
- **fleet-hostinger:** the index lives in the container's persistent
  OpenClaw data volume. Delivery is push-primary, spool-fallback: with
  `SKILL71_RUNS_SHIP_URL` set, each event is POSTed to the Command Center
  ingest endpoint with the per-client bearer token read from the file
  named by `SKILL71_RUNS_SHIP_TOKEN_FILE` (a path; the token value never
  enters the repo or the run folder). On any network failure the event is
  appended to the spool instead, and `scripts/ship_run_events.py` drains
  the spool in order (run by the runner at the start and end of every
  run, and by a per-box timer every 15 minutes).
- **fleet-contabo:** the index is per-container, aggregated on the host
  by mount contract: host `/srv/skill71-runs/<client-slug>/` is
  bind-mounted into that client's container only, at `/skill71-runs`, and
  `SKILL71_RUNS_INDEX=/skill71-runs/runs.jsonl`. The Command Center reads
  `/srv/skill71-runs/*/runs.jsonl` directly on the host. Isolation is
  mount-level: a container cannot see a sibling's directory because it was
  never mounted. If the Command Center ever moves off that host, the same
  boxes run the shipper in push mode against the same ingest endpoint; no
  other change.

Delivery is **at-least-once** everywhere. Every consumer dedupes by
`event_id`, so re-shipping after a crash is safe by construction.

## 3. The event set

| Event | Emitted when | Carries (beyond the envelope) |
|---|---|---|
| `run_initialized` | `cmd_init` creates the run | `host_shape` (required), `page_name`, `brand_id`, `client` (copied from `intake.json` when present), `test_run` |
| `stage_closed` | a stage close is recorded | `stage`, `receipt_status` (`pass` / `not_authorized`), `closed_at`, `duration_s`, `scores_summary` (Item 2 aggregates, or null), `cost` (`{provider, credits_used}` when the receipt carries cost, else null), `artifact_hashes`, `review_files` |
| `stage_blocked` | a stage close is refused | `stage`, `failures` (the gate's named failure lines, verbatim), `blocked_at` |
| `item_closed` | an item-level close succeeds (Item 20/21) | `stage`, `item_id`, `closed_at`, `artifact_hash` when the item has one |
| `item_blocked` | an item-level close is refused | `stage`, `item_id`, `failures`, `blocked_at` |
| `report_generated` | `cmd_report` writes REPORT.md/REPORT.json | `overall`, `review_mode`, `report_json_path`, `report_md_path` |
| `pin_drift` | an authority pin check finds drift (Item 11 rider) | `authority_id`, `pinned_sha`, `observed_sha` (null when the pinned file is missing) |

Item events exist only once Item 20's item-level gates do; stage events
work without them. Before Item 20, a run's feed is stage events only, and
consumers must not treat the absence of item events as an error.

Example `pin_drift` line:

```json
{"event_id":"9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d","event_type":"pin_drift","schema_version":"1.0","emitted_at":"2026-10-13T14:00:05Z","run_id":"da3f43ec-5c7b-52c5-a28e-60eb97aac84d","run_dir":"/skill71-runs/runs/example-run","authority_id":"shared-utils/kie_prompt_enforcer.py","pinned_sha":"d4472c65","observed_sha":null}
```

## 4. Payload rules (what may never appear)

Events and REPORT.json carry **identifiers, verdicts, timestamps,
hashes, counts, score aggregates, gate-generated failure strings, and
paths on the emitting host. Nothing else.** Specifically, never:

- credential values, token values, or secrets-file contents (the ship
  token travels in an HTTP header from a file read at send time, never in
  a payload);
- page copy, prompt text, review criterion notes, or any other client
  content (review *scores* travel as aggregates; the notes themselves are
  evidence that stays in the run folder);
- client PII of any kind (`client` and `client_slug` are the operator's
  own identifiers from intake and provisioning, nothing more).

A consumer that receives a line failing the schema rejects the line. It
does not repair it, guess at it, or store it "for reference."

## 5. REPORT.json, field by field against REPORT.md

`cmd_report` writes `REPORT.json` beside `REPORT.md` with the same
values, structured (`references/report-json.schema.json`):

| REPORT.json | REPORT.md source |
|---|---|
| `generated_at` | the "Generated by scripts/stage_gate.py report at" line |
| `stages[].status` | the Stages table Status column, verbatim vocabulary: `PASS`, `NOT AUTHORIZED`, `FAIL`, `BLOCKED`, `NOT RUN` |
| `stages[].closed_at` | the Stages table "Closed at" column |
| `stages[].duration_s` | the Stages table Duration column, in seconds |
| `stages[].receipt_status`, `scores_summary`, `cost`, `artifact_hashes`, `review_files` | the state.json close record behind the row (receipt status; Item 2 score aggregate; cost block; close-recorded hashes; v2 review file paths) |
| `warnings` | the WARN list, one string per line, without the `- WARN:` prefix |
| `totals.cost_by_provider` | the Cost section's per-provider lines; an empty object is the data form of the section's explicit no-cost-data line |
| `totals.slowest_stages` | the Slowest stages section (top three) |
| `compare_sheets` | the Compare sheets list |
| `overall` | `complete` for REPORT.md's RUN COMPLETE, `incomplete` for RUN INCOMPLETE, `test-run` when `intake.test_run` is true (Item 25's vocabulary) |
| `review_mode` | the "Review mode:" line printed under the overall line, as data: `mode` (`INDEPENDENT` / `SELF-REVIEWED` / `UNKNOWN`), the reviewer/author session counts, the overlap stages, and `line`, the exact printed string |
| `artifacts` | every stage's close-recorded artifact hashes merged into one path-to-hash map |
| `owner_blocked` | owner-blocked waits in force for this run, named plainly (Item 6 discipline: downgrades print). Reserved: an empty list until the gate has an owner-block source |
| `waivers` | waivers in force for this run (for example an intake-recorded layout-references waiver). Reserved the same way: empty list, never omitted |
| `hygiene` | **placeholder for Item 33** (S7): browser-session hygiene counts from the hygiene receipt. Until Item 33 lands: `status: "not_recorded"` and null counts |
| `run_id`, `page_name`, `brand_id`, `client`, `host_shape` | run identity from `private/state.json` and `intake.json`; `run_id` is null only in a report from a gate build predating Item 24 |

One rule keeps the twins honest: REPORT.md gains one line under its
title, `Structured twin: REPORT.json (schema skill71/report-json/1.0)`,
and REPORT.json carries the review-mode `line` verbatim. If the two ever
disagree, the Markdown is what a human read and the JSON is what the
board showed; the disagreement itself is a bug to report, not a tie to
break silently.

## 6. Gate-side emission spec (for the coordinator's integration window)

`stage_gate.py` is another stream's file in this build window, so this
section is the complete spec of the gate change; the code lands with the
integration window, not in this stream's tree.

1. **`cmd_init`**: after loading/creating state, mint `run_id` (UUID4)
   when `state.json` has none and store it, with `page_name`, `brand_id`,
   `client` copied from `intake.json` when present. Append
   `run_initialized` (with `host_shape`, resolved per Amendment 1's
   profile detection: `FLEET_SHAPE` env, container default fleet-contabo,
   Darwin fleet-mac, other Linux fleet-hostinger). Re-running `init` on
   an existing run emits nothing.
2. **A single helper**, `emit_event(run_dir, event)`: fills the envelope
   (`event_id` UUID4, `schema_version` `"1.0"`, `emitted_at` UTC now,
   `run_id` from state), appends one JSON line to
   `<run_dir>/private/run-events.jsonl`, and, when `SKILL71_RUNS_INDEX`
   is set, appends the same line with `run_dir` added to that file. When
   shipping is configured (fleet-hostinger push), it also attempts the
   POST and falls back to the spool on failure (section 2). Emission
   failure never fails the gate command: events are evidence about the
   gate, and a broken index path must not block a client's page; the
   failure prints as a WARN line on stderr.
3. **`record_close`**: after `save_state`, emit `stage_closed` from the
   values just recorded (receipt status, closed_at, duration from the
   receipt's started/finished, `review_scores_summary`, cost computed as
   before minus after when both are present, artifact hashes, review file
   list).
4. **`cmd_close` failure paths**: when close is refused (any
   `fail_exit` after the stage's receipt was examined), emit
   `stage_blocked` with the failure lines. A close refused because the
   stage name is invalid emits nothing (there is no run transition).
5. **`cmd_report`**: write REPORT.json (schema above) in the same pass
   that writes REPORT.md, then emit `report_generated` carrying both
   paths, `overall` (the REPORT.json vocabulary), and `review_mode` (the
   `compute_review_mode` result's mode token).
6. **Item events**: Item 20's item-level check/close in the gate emits
   `item_closed` / `item_blocked` the same way; `swarm_runner.py`
   forwards the events its own item closes produce through the same
   helper. Until Item 20 lands, no item events exist (section 3).
7. **Pin drift**: the Item 11 pin check, wherever it runs, emits
   `pin_drift` against the active run when one exists (provisioning-time
   checks with no run context record the drift in the health-check output
   only, and the first run initialized afterward carries it in its feed
   via a `pin_drift` line emitted at `cmd_init` when a recorded drift is
   still outstanding).

`references/artifact-contracts.md` gains the environment contract in the
same integration window: the variables (`SKILL71_RUNS_INDEX`,
`SKILL71_RUNS_SHIP_URL`, `SKILL71_RUNS_SHIP_TOKEN_FILE`,
`SKILL71_RUNS_SPOOL`), the run-events file, and a pointer to this
document. The exact section text is this document's sections 1, 2, and 4,
condensed by the integrating builder; the contract itself does not change.

## 7. Consumer contract (Command Center)

One ingestion core, two transports (Amendment 1, Item 26 rider):

- **File transport** (fleet-contabo): read `/srv/skill71-runs/*/runs.jsonl`
  on the host. `scripts/import-skill71-runs.ts` in the Command Center repo
  is this transport's driver.
- **HTTP transport** (fleet-hostinger push; fleet-mac opt-in push):
  `POST /api/skill-runs/ingest` with a per-client bearer token. The token
  record binds `client_slug` and `host_shape`; an event whose claimed
  slug or shape contradicts its token is rejected.

Both feed the same core: validate against the frozen schema, dedupe by
`event_id`, upsert the run record (latest event state per run). Ingestion
is idempotent and read-only with respect to run folders: re-importing
changes nothing the events do not say, and no consumer ever writes into a
run folder. The board's read API (`GET /api/skill-runs`) serves the
database only; it never reaches into run folders at request time.

The panel shows `host_shape` on every run. The set of runs on the board
is the set of runs that were delivered, and delivery is shape-dependent
by design (fleet-mac local by default): an absent fleet-mac run is an
absent delivery, not missing data.
