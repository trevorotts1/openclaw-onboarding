# PRES-055 leg B Docker-matrix REDO R2 (W6 WF23, Opus)

Scope: NEW files ONLY under `accept-b/docker-redo/` in worktree
`run/worktrees/wf23-onb-accept`, branch `pres055-wf23-b-redo` from
`984b3522d46309d1e063b823ed36089479f3c57c`. READ-ONLY everywhere else.
NEVER push/tag/release/merge/stash. No live client/merchant data, no real
paid calls, no client-box writes.

Why this exists: commit `984b3522d` (leg B) recorded 6/6 Docker legs
NOT-VERIFIED because the colima daemon was down
(`unix:///Users/blackceomacmini/.colima/default/docker.sock` unreachable).
The daemon was restored 2026-09-10 (server 29.2.1 Ubuntu 24.04.4 LTS
aarch64, client 29.7.2). This redo runs the matrix legs for real against
the EXACT released carriers and never waives a leg that cannot run.

## What runs

| Module | Leg | Nature |
|---|---|---|
| `docker_redo.py` | Hostinger-Docker + Contabo-Docker x fresh/upgrade/restart (6 legs) | REAL daemon contact, REAL containers from the pinned base image digest, fresh venv + pip install of the exact wheel inside the container, `presentation init/doctor/start/status/verify/export`, bounded resume entry, engine dry-run park, render + QC inside the container, export read back on the host. Receipts: `docker info`/`docker version`, image digest, `docker inspect`, container logs, per-step rc + log tails, job ID, event/phase counts. |
| `docker_redo.py` | Controls | Matrix stub contract (must self-report NOT-RUN exit 3, never PASS) + adapter probes (standalone positive + missing-marker negative) re-run from the leg B module, unchanged code path + exec control on the instrument. |
| `run_redo.py` | Orchestrator | Writes evidence to packet `run/evidence/PRES-055/b-docker-redo/` and the candidate to `run/candidates/PRES-055-b-redo/candidate.json` after the commit SHA is known. |

## Labels used in receipts

- `DEPLOYED-RUN-PASS`: every required step rc is green and no artifact
  defect was recorded.
- `DEPLOYED-RUN-PASS-WITH-RECORDED-DEFECTS`: the install path ran for real
  and every REQUIRED step is green, but a CONTROL step came back red and
  the red is recorded under `defects` with its exact log. Never a silent
  pass, never a waiver.

The bounded `presentation resume` step accepts rc 0, 124 and 137: the
container's own `/usr/bin/timeout -k 10 100` returns 124 when the engine
died on SIGTERM at the 100s bound and 137 when it survived SIGTERM and had
to be SIGKILLed at 110s. The engine's FIX-105 handler logs the shutdown
(`[engine shutdown] signal 15 received`) but the resume loop keeps
servicing, so 137 is the normal outcome here; both are recorded verbatim
and neither is collapsed into the other.

- `DEPLOYED-RUN-FAIL`: a required step came back red; the leg did not run
  as specified.
- `NOT-VERIFIED`: the leg could not run; the exact daemon/container error
  is recorded verbatim. Never converted to a pass.
- `SOURCE-RUN-*` / `FIXTURE-PASS-*`: not used for the container legs.

## Two runtime controls (both must discriminate)

A control that comes back uniform means the CHECK is broken, not the target,
so both controls compare arms on the same instrument and record
`discriminates`.

1. `runtime_control_python_version` - the `Thread._stop` shadowing probe on
   `python:3.11-slim`, `python:3.12-slim`, host python 3.14.7 and host
   python 3.12.12. Raises on <=3.12, passes on 3.14.
2. `runtime_control_pid1_reaping` - an orphan is manufactured (a `sleep`
   whose parent shell exits, so it is reparented to pid 1), killed, and the
   resulting `/proc` row is handed to the engine's OWN `lease` module
   (`pid_is_alive`, `_pid_provably_dead`, `_holder_is_live`). Two arms
   differing ONLY in `--init`. Verified result on this box:
   - no-init: pid1 = `sleep infinity`, orphan stays `state=Z ppid=1`,
     `engine_waits_full_ttl: true` (the F19 takeover can never fire).
   - `--init`: pid1 = `/sbin/docker-init`, orphan is reaped, `all_zombies []`,
     `engine_pid_provably_dead: true`.
   Every leg therefore runs `docker run --init`.

## Recorded artifact defects (never waived)

- `ENGINE-DRYRUN-PY311-THREAD-STOP` - on the container runtime (python
  3.11.16) `engine --run --dry-run` returns **rc 1** instead of the parked
  **rc 3**: `engine/lease.py` `HeartbeatThread` sets
  `self._stop = threading.Event()`, which shadows `Thread._stop`, and
  `threading.Thread._wait_for_tstate_lock` calls `self._stop()` on python
  <= 3.12, so `engine/__main__.py:1049 lease_hb.join(timeout=5)` raises
  `TypeError: 'Event' object is not callable` after the park message has
  already printed. The same verb parks cleanly at rc 3 on host python 3.14.7.
  The step is recorded as a CONTROL that came back red, its exact traceback
  is in `containers/<profile>__<op>/logs/engine_run_dry_run.txt`, and the
  discriminator is the `runtime_control_python_version` control above.

## Receipt self-consistency gate (added after a real contradiction was found)

A receipt whose `failures` list disagrees with its own per-step rows is a
broken INSTRUMENT: it can print `DEPLOYED-RUN-PASS` next to a red. That
happened here. `step()` recorded a red at run time, `rejudge()` later fixed
the row for a non-rc criterion (the bounded resume accepts rc 0/124/137) and
left the stale entry behind, so a leg could read green while `failures` still
held `cli_resume_bounded: rc=137 ...`.

Fix, and the proof it is fixed:

- `rejudge()` now rebuilds the step's entry in `fails` / `controls_red` from
  the post-rejudge row verdict and its `required` flag.
- Every leg carries `receipt_self_consistent` with both directions checked on
  step-named entries: every red row is listed, and no listed entry names a
  green row (prose checks like QC/carriers/mounts are not step rows and are
  not compared). If the check fails, the leg is marked `NOT-VERIFIED` with
  reason `receipt self-inconsistency ... broken instrument` — never a pass.

## Honest limitations recorded (never waived)

- Both install profiles execute on the SAME local Docker engine (colima on
  the operator box). The profile-specific remote hosts (Hostinger VPS
  container, Contabo VPS) were NOT contacted: no scoped authorization to
  write there and no credentials in this packet. The profile name selects
  the recorded profile row; it is not evidence about the vendor host.
- No PRIOR released wheel exists in this packet, so the `upgrade` op is
  exercised as a real force-reinstall of the exact artifact over a live
  install + preserved workspace/run. Version-to-version upgrade remains
  NOT-VERIFIED and is recorded as such.
- Connected CC/GHL acceptance stays NOT-VERIFIED (PRES-025/CC connected
  legs already recorded in `run/evidence/PRES-055/b-docker/` and are not
  redone here).
- Render is LOCAL-SYNTHETIC from the synthetic fixture inside the
  container; canonical KIE render is NOT-RUN (zero paid calls).

No receipt here self-approves anything. QC-PRES-055 stays OPEN pending
INDEPENDENT QC.
