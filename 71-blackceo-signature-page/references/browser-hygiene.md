# Browser Hygiene: Session Registry, Teardown, and the Gate (Item 33)

No session left behind. Browser work in this skill runs under
Amendment 5's Browser Engine Contract (operations: launch, seed, act,
capture, teardown, reap; sessions isolated and named; engine names
DRAFT-PENDING-LANDING per Amendment 5B and Skill 6 draft PR #1990).
This reference is the accounting layer that makes the contract's
cleanup a gated, evidenced property of the run instead of a hope:
`scripts/browser_sessions.py` is the registry and reaper,
`scripts/stage-gate-browser-hygiene.patch` wires the verdict into
`scripts/stage_gate.py`, and `scripts/swarm_runner.py` performs the
runner-side registration and teardown.

## The rule

A browser-using stage cannot close while any browser session opened
for it is unaccounted, and cannot close with a headed launch on record
unless an owner override is recorded in the stage's hygiene receipt.
REPORT.md carries one line per run:

```
Browser hygiene: N sessions opened, N closed, N orphans reaped.
```

## Which stages are browser-using

The contract marks a stage with `"uses_browser": true`: the flag is
on `ghl-install-test`, `publish-verify`, and `automation-wiring`
(stage 14), with `<stage>/browser-hygiene.json` as a required
artifact of each. `automation-wiring`'s browser use is the Tier 4
backstop case; the gate code is flag-driven and needs no change. Independently of the flag, any stage the registry holds
sessions for is accountable: the gate treats registry presence as
browser use, which is the publish-verify conditional case (a browser
produced its evidence) expressed without a second flag value.

## The registry: `private/browser-sessions.jsonl`

Append-only, one JSON object per line, written by the launching
wrapper at open time (the swarm runner, or a Skill 6 adapter), never
from a working agent's memory. An `opened` event:

```json
{"event": "opened", "session_name": "...", "run_id": "...",
 "stage": "ghl-install-test", "engine": "...", "binding": "...",
 "unit": "session", "client_slug": "...", "headed": false,
 "opened_at": "...", "owner_pid": null, "live_marker": null,
 "teardown_cmd": null, "via": "swarm-runner"}
```

A `closed` event: `{event, session_name, closed_by, closed_at, via,
detail}` with `closed_by` exactly `"normal"` (the owner tore the
session down through the contract's teardown operation) or `"reaped"`
(the reaper sweep closed the books).

Field notes:

- `session_name` carries client slug, run reference, and stage (the
  Browser Engine Contract's naming rule); the runner builds it as
  `<client-slug>-<run-ref>-<stage>[-<item>]`.
- `unit` is the controlled unit the engine actually isolates
  (Amendment 5B): a CLI engine isolates a named session; the OpenClaw
  Chrome extension (DRAFT-PENDING-LANDING) isolates controlled tabs or
  windows in the operator's Chrome. Adapters record the unit their
  engine truly isolates. Until Skill 6's change lands and the
  extension-accurate restatement is written (Amendment 5B point 3,
  owed, not waived), the OpenClaw binding records `"session"` and no
  stronger claim is made.
- `headed` records whether the launch was headed. Under the extension
  binding, "headed" means the work touched the operator's active
  screen or active window; under CLI bindings it means a non-headless
  launch. Either way it is a contract violation unless overridden
  (below).
- `owner_pid`, `live_marker`, and `teardown_cmd` are the reaper's
  evidence handles: what a later sweep can probe and act on after the
  launcher is gone. Wrappers record whichever their engine offers.

## Teardown on every exit path

| Exit path | Who tears down |
|---|---|
| Worker finishes (any outcome) | The runner closes the node's session in a finally around the spawn |
| Validator failure, stage failure | The node's worker has exited, so the row above applies; anything the worker itself leaked is the gate reaper's |
| Runner run end | The runner closes every session it still holds |
| Runner SIGTERM / SIGINT | The runner's signal handler closes every session it still holds, then exits |
| Runner death (SIGKILL, host crash) | Nobody can run code; the registry keeps the opens, and the gate's reaper pass accounts for them at the next `check` or `close` of a browser-using stage, before anything else is evaluated |

## The reaper pass (the gate)

For a browser-using stage, `check` and `close` first run the pass in
`scripts/browser_sessions.py`:

1. Fold the registry. Every session of this stage still open is an
   orphan.
2. Probe each orphan: a recorded `live_marker` exists (alive) or not
   (gone); else a recorded `owner_pid` answers `os.kill(pid, 0)`
   (alive), is gone, or cannot be probed (unknown).
3. Provably gone: record `closed` with `closed_by: "reaped"` (the
   sweep verified it and closed the books). Provably alive: try the
   recorded `teardown_cmd` (exit 0 with no contradicting probe), else
   SIGTERM to the recorded owner pid; success records `"reaped"`.
4. Anything still open after the sweep is **unaccounted**: the close
   is refused, naming each session. The accounting never upgrades
   hope into a close.
5. The pass writes the stage receipt (below) before the gate
   evaluates anything else, so a passing close hashes the receipt as
   one of the stage's artifacts.

## The receipt: `<stage>/browser-hygiene.json`

Written by the gate's pass (and refreshable via
`python3 scripts/browser_sessions.py receipt <run_dir> --stage S`):

```json
{"stage": "ghl-install-test", "sessions_opened": 3, "sessions_closed": 2,
 "orphans_found": 1, "orphans_reaped": 1, "unaccounted": 0,
 "headed_launches": 0, "owner_override_headed": null,
 "sessions": [{"name": "...", "engine": "...", "binding": "...",
               "unit": "session", "closed_by": "normal"}],
 "updated_at": "..."}
```

`sessions_opened` counts distinct opened sessions; `sessions_closed`
counts `closed_by: "normal"`; `orphans_found` is `orphans_reaped`
plus the still-open count, so the receipt and the fold agree whenever
they are read; `unaccounted` is the still-open count after the sweep;
`sessions[].closed_by` is null for an unaccounted session (it is named
there and in the gate's refusal line).

**Headed override.** `headed_launches` above zero blocks the close
unless an owner override is on record: an `owner_override_headed`
object with a `reason` (and who recorded it) placed in the receipt by
the executor ahead of the gate, or `intake.json`'s
`browser_headed_override` for the stage. The gate preserves a recorded
override into the receipt it writes; it never invents one. This is
the interactive exception: a run that deliberately works headed (an
operator watching a click-through, for example) declares it, and the
declaration is what REPORT consumers see.

## REPORT.json mapping (S6 frozen schema, Item 25)

`REPORT.json`'s hygiene object is frozen (status, opened, closed,
orphans_found, reaped, unaccounted, headed_launches). Naming note,
recorded rather than silently bridged: the per-stage receipt follows
Item 33's text (`sessions_opened`, `sessions_closed`,
`orphans_reaped`), while the frozen roll-up shortens three names.
The gate's `report_hygiene_object()` performs the mapping in code:
`sessions_opened` to `opened`, `sessions_closed` to `closed`,
`orphans_reaped` to `reaped`; `orphans_found`, `unaccounted`, and
`headed_launches` keep their names. The roll-up sums the per-stage
receipts; `status` is `"recorded"` only when at least one stage
receipt exists, otherwise `"not_recorded"` with null counts (a run
with no browser accounting does not claim recorded zeros). When a
REPORT.json already exists, `cmd_report` fills its hygiene object
from this roll-up; the Item 25 writer emits the same object from the
same function.

## Honest limits

- Registration is wrapper-side by design (Item 33 HOW 1). A browser
  launched by hand, outside the runner and the adapters, is invisible
  to the fold; the executor-side complement is Skill 6's own
  process/window enumeration by session-name prefix, which its reaper
  scheduling already carries. The gate accounts for everything the
  registry proves, and says so.
- The probe reads the handles the wrapper recorded. A session whose
  wrapper recorded no pid, marker, or teardown command and which is
  still open at the sweep is unaccounted by definition: unverifiable
  is unaccounted, never assumed closed.

## Proposed `references/artifact-contracts.md` entry (coordinator action)

> **Browser hygiene receipt (Item 33).** Per browser-using stage
> (`ghl-install-test`, `publish-verify`, and `automation-wiring` when
> the backstop runs), `<stage>/browser-hygiene.json`, written by the
> stage gate's reaper pass from `private/browser-sessions.jsonl`:
> `{stage, sessions_opened, sessions_closed, orphans_found,
> orphans_reaped, unaccounted, headed_launches,
> owner_override_headed, sessions: [{name, engine, binding, unit,
> closed_by}], updated_at}`. The stage cannot close with
> `unaccounted` above zero, or with `headed_launches` above zero
> without the owner override recorded in the receipt.

## Patch application (coordinator action)

Apply `scripts/stage-gate-browser-hygiene.patch` AFTER
`scripts/stage-gate-item-commands.patch` (Item 20), against S1's
`scripts/stage_gate.py` and `references/stage-contract.json`;
`scripts/browser_sessions.py` ships as a new file beside them. The
gate loads the module by path at pass time and fails a browser-using
stage's close closed, with the reason named, if the module is absent.
