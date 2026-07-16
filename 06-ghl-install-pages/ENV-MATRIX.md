# Skill 6 — VPS-vs-Mac ENVIRONMENT MATRIX (build unit `envmatrix`, spec §4)

This is the pinned, testable contract for running Skill 6 identically on a
**real Mac / Mac mini** and on a **VPS (Linux, Docker)**. It documents what
already exists (mostly in `tools/browser_manager.sh` / `tools/browser_manager.py`)
and names the ONE canonical detection/portability primitive per dimension so no
new tool ever re-implements its own, drifting, VPS-vs-Mac check.

Source of truth for every row below: `SKILL-6-BROWSER-CONTROL-BULLETPROOF-SPEC-v1.md`
§4, cross-checked live against `tools/browser_manager.sh` / `.py` and
`tools/parallel_saves.sh` in this repo.

| Dimension | Mac (operator/client Mac mini) | VPS (Linux, Docker) | Canonical primitive |
|---|---|---|---|
| Durable root detection | `~/.openclaw` | `/data/.openclaw` checked **first** | shell: `_bm_durable_root()` (`tools/browser_manager.sh`); python: `browser_manager.durable_root()` — both check VPS then Mac then return `""` |
| Browser launch | agent-browser headless via the gateway; headed is possible on real hardware but **forbidden** (D6, exit 75) | Same — headless only; no display exists at all, so a headed regression fails hard instead of popping a window | `bm_require_current_guard()` / `headless_guard()` — identical on both, no branch |
| Display / Xvfb | Not used | Not used — agent-browser 0.27.0's headless Chromium needs no X server | n/a — headless-only design means neither side ever needs a display |
| Locking | No `flock` on macOS → atomic-`mkdir` lock + dead-PID stale reclaim | `flock` present → real fd-9 flock | `_bm_lock_acquire()` — probes `command -v flock` at call time, falls back to `mkdir "$LOCKDIR/ab.lock.d"` with PID-liveness stale reclaim. **Verified in this unit**: `test_lock_is_flock_or_mkdir` (existing) + this unit's env-matrix test suite re-assert both code paths are present and exercised by the mkdir-lock hermetic test. |
| bash version / builtins | **bash 3.2** (`/bin/bash` on stock macOS — verified live: `GNU bash, version 3.2.57(1)-release`). No `mapfile`/`readarray` (bash 4.0+), no associative arrays (`declare -A`, bash 4.0+), no `${var,,}`/`${var^^}` case expansion (bash 4.0+), `wait -n` is bash 4.3+. | bash 4/5 typically present, but scripts must not *rely* on that — a box could still resolve to an older `/bin/sh`-symlinked shell. | Every `.sh` file under `06-ghl-install-pages/tools/` and `scripts/` must be bash-3.2-safe. **Found + fixed in this unit**: `tools/parallel_saves.sh` used `mapfile -t page_specs < <(...)` — this crashes with `mapfile: command not found` under real `/bin/bash` 3.2 (reproduced live before the fix). Replaced with a `while IFS= read -r line; do array+=("$line"); done <<< "$captured_string"` loop (portable to bash 3.1+), functionally re-verified end-to-end against both `/bin/bash` (3.2.57) and Homebrew `bash` (5.3.12) with a stubbed `agent-browser` — identical output, identical exit code. |
| BSD vs GNU grep | BSD grep (macOS system grep) — no `-P` (Perl regex), no `-o` guarantee of multi-match-per-line ordering some GNU-only flags assume | GNU grep (`grep -P`, `-o`, etc. all available) | Every `grep` invocation in `tools/*.sh` / `scripts/*.sh` under Skill 6 is `grep -E` / `grep -F` / `grep -q` / `grep -o` with a POSIX-portable pattern — **audited in this unit**: `browser_manager.sh`, `parallel_saves.sh`, `inject-ghl-auth.sh`, `qc-built-form.sh`, `qc-built-funnel.sh`, `scripts/guard-ghl-method-decision.sh`, `scripts/guard-ghl-verify-unfakeable.sh` — zero `grep -P` occurrences (would be BSD-incompatible). Where a match needs richer parsing than portable POSIX grep, the scripts already delegate to `python3 -c "..."` (JSON-aware, no grep at all) rather than reach for a GNU-only flag — keep doing this for any new tool. |
| Supervision | `launchd` (MCP server plist; hourly reaper via cron) | `pm2` (`pm2 restart ghl-community-mcp`) or `systemd` (`systemctl restart ghl-mcp`); cron in-container | **Informational only** — Skill 6 build/verify logic never branches on this (D14-style invariant: identical behavior both sides). `browser_manager.supervisor()` (new, this unit) returns `"launchd"` on `darwin`, `"pm2-or-systemd"` elsewhere, for diagnostics/logging only — never for control flow. |
| Env stores | `~/.openclaw/secrets/.env` → `~/clawd/secrets/.env` → `~/.openclaw/workspace/.env` | Hostinger: `/docker/<project>/.env` feeds the container; in-container `~/.openclaw/secrets/.env`; `docker compose restart` **skips** `env_file` (must `up --force-recreate`) | Skill 6 reads `GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN` / `CAF_FIREBASE_REFRESH_TOKEN` / `GHL_FIREBASE_REFRESH_TOKEN` etc. from **already-resolved process env** (`os.environ`) — it does not itself walk the alias × store resolution chain; that happens upstream (fleet convention, `credential-check-live-process-env-first`). No Skill-6 code hardcodes a store path other than the docstring examples in `seed-ghl-auth.py`, which are documentation, not a resolution order the code executes. |
| Docker env-file / workdir | n/a | `docker compose restart` **skips** `env_file` re-read — a changed `.env` needs `docker compose up -d --force-recreate`; a pushed workdir needs `chown -R node` after the push (container runs as `node`, not root) | **B-U15 item 3 — now an automated preflight, not prose only**: `browser_manager.py::stale_env_preflight()` (shell mirror: `browser_manager.sh::bm_stale_env_preflight()`, called from `bm_ensure()` — every build routes through it) compares the host `/docker/<project>/.env` mtime against the running container's `docker inspect .State.StartedAt`. Advisory WARN only (never blocks a build, matches this row's own "operational doctrine" framing): fires when the env is genuinely stale, stays silent on a Mac and on any box where docker/the container/the env path cannot be determined (never guesses). Hermetic tests: `tests/test_b_u15_env_matrix_live_proof.py::TestStaleEnvPreflight*`. |
| Session persistence | `~/.agent-browser/` profile + `state save` files persist across runs | Same paths inside the container; persist only if the workdir is on a **mounted volume** | `AB_REAPER_PLAYWRIGHT_DIR` scopes the reaper's cleanup; a VPS build MUST confirm `~/.agent-browser` is on a persistent (not ephemeral-overlay) mount before relying on `state save/load` across container restarts. **B-U15 item 1 — mechanism shipped, LIVE round trip owed**: `tools/ghl_vps_mount_proof.py` (classify the mount table, plant a run-id marker, verify it survived, write `routing/vps-mount-receipt.json` recording the mount type) + `scripts/vps-mount-proof.sh --live` (the real `state save` → `docker compose up -d --force-recreate` → `state load` orchestration, refuses cleanly — never fabricates a PASS — when no real Docker/VPS is reachable). The row's **[ASSUMED, spec-carried]** status is now "offline mechanism VERIFIED (hermetic classify/marker/receipt tests); the real per-box confirmation on an actual VPS is OPERATOR-RUN, not yet executed" — not silently closed. |
| TMPDIR | `/var/folders/*`, wiped on boot | tmpfs `/tmp`, wiped on boot | This is exactly why `PARK_DIR`/receipts/durable state live under `durable_root()`, never under `$TMPDIR`/`$LOCKDIR` — both sides wipe TMPDIR on reboot, and a PARK marker that silently vanished on reboot would un-park a qc-failed build with no operator action. |

## Adaptation contract (binding for every future Skill-6 change)

1. **Detect environment ONLY via `durable_root()`** (`browser_manager.py`) or
   `_bm_durable_root()` (`browser_manager.sh`) — never a new hand-rolled
   `/data` or `~/.openclaw` check. Both check VPS first, Mac second, empty
   third, and are proven to agree by `tests/test_env_matrix.py`.
2. **No `flock`/`timeout`/GNU-only assumptions** — reuse the gateway's
   existing portable primitives (`_bm_lock_acquire`'s flock-or-mkdir branch,
   the `command -v timeout` guard in `AB()`). Do not add a new lock or a new
   timeout wrapper elsewhere in the skill.
3. **All `.sh` files stay bash-3.2-safe.** Banned builtins/constructs in any
   `06-ghl-install-pages/tools/*.sh` or `06-ghl-install-pages/scripts/*.sh`
   file: `mapfile`, `readarray`, `declare -A` / `local -A`, `${var,,}`,
   `${var^^}`, `wait -n`. Use `while IFS= read -r line; do arr+=("$line"); done`
   for array-from-command-output, `tr '[:upper:]' '[:lower:]'` for
   case-folding, and a polling loop (as `parallel_saves.sh` already does) in
   place of `wait -n`. `tests/test_env_matrix.py::TestBash32Safety` enforces
   this by static scan, and by literally invoking every skill-6 `.sh` file's
   `bash -n`/`--selftest` (where one exists) under `/bin/bash` in addition to
   the box's default `bash`.
4. **Run evidence lives under the run-evidence root; PARK/breaker state lives
   under `durable_root()`** — never under `$TMPDIR`. (F6 receipts already
   follow this via the caller-supplied `evidence_root`; `PARK_DIR` already
   follows this via `_bm_durable_root`.)
5. **The first-hour ground truth (spec §9.4) is run on BOTH one Mac and one
   VPS** before any fix in this family is declared fleet-ready. **B-U15 item 2
   — schema + comparator shipped, live runs owed**:
   `tools/ghl_env_matrix_ground_truth.py` defines the receipt shape a fixture
   build (dispatch → build → verify → FAB-QC) emits per box
   (`GROUND_TRUTH_REQUIRED_FIELDS`) and `compare_ground_truth()` /
   `assert_ground_truth_parity()` prove real parity between a Mac receipt and
   a VPS receipt (matching `durable_root()`/`is_vps()`/`supervisor()`
   resolution per box, both builds actually PASS-ing FAB-QC ≥ 8.5, non-zero
   object receipts on each — never a vacuous "looks fine"). This is the
   offline-provable COMPARATOR; actually running the fixture build on a real
   Mac and a real VPS to produce the two receipts it compares is OPERATOR-RUN
   and OWED (not this branch-only unit's to fabricate).

## What this unit changed (envmatrix, offline-only — no live browser, no GHL write)

- **Fixed a real bash-3.2 incompatibility**: `tools/parallel_saves.sh`'s
  `ps_run_batch` used `mapfile -t` to build its page-spec array. Verified live
  on this box that stock `/bin/bash` (3.2.57) does not have `mapfile` at all
  (`mapfile: command not found`) — a VPS box or a Mac with Homebrew bash ahead
  in `PATH` would never have hit this, but a stock-Mac `PATH` resolves
  `#!/usr/bin/env bash` to `/bin/bash` and would have crashed every batched
  parallel-save run. Replaced with a portable `while read -r` loop; re-verified
  end-to-end (stub `agent-browser`, real JSON spec file, both `/bin/bash` and
  Homebrew `bash`) — identical output, identical exit code, both shells.
- **Added `browser_manager.py::durable_root()` / `is_vps()` / `supervisor()`** —
  the Python-side mirror of `_bm_durable_root()` that did not exist before this
  unit. Additive only; no existing behavior changed. This is the primitive any
  future Python-only Skill-6 tool (the §5 community/course builders, a future
  receipt writer) must use instead of hand-rolling its own VPS-vs-Mac check.
- **This document** — the single place the matrix + the adaptation contract
  live inside the skill (previously only in the external spec file), so a
  future contributor does not have to re-derive it.

## B-U15 — ENV-MATRIX live proof: the ASSUMED VPS mount row + first-hour ground truth + stale-env preflight

Builds on the `envmatrix` unit above (which SHIPPED the matrix + Python
mirror + bash-3.2 fix). This unit is the live-proof layer for the matrix's
one remaining `[ASSUMED, spec-carried]` row plus two contract items that were
prose-only before now:

- **Item 1 (VPS mount row) — mechanism shipped, live round trip owed.**
  `tools/ghl_vps_mount_proof.py`: `classify_mount()` (parse the mount table,
  distinguish an ephemeral `overlay`/`aufs`/`tmpfs` container layer from a
  real bind/volume mount — injectable reader, hermetic), `write_marker()` /
  `verify_marker()` (the actual proof-by-survival: stamp a run-id-tagged
  marker into the path, read it back after whatever happened in between),
  `build_receipt()` / `write_receipt()` (the single
  `routing/vps-mount-receipt.json` artifact recording the mount type — never
  upgraded to a PASS on a `post=None` partial). `scripts/vps-mount-proof.sh`
  is the live orchestration wrapper (`--live --path ... --run-id ...
  --compose-file ...`: marker → `docker compose up -d --force-recreate` →
  marker verify → receipt) — mirrors `run-selector-canary.sh`'s
  offline-default / `--live`-is-operator-run shape exactly, and REFUSES
  (exit 3) rather than fabricate a pass when no real `docker` binary or
  compose file is reachable. **Owed**: the actual live run on a real VPS
  (spec §9.4 step 10).
- **Item 2 (first-hour ground truth) — schema + comparator shipped, live
  runs owed.** `tools/ghl_env_matrix_ground_truth.py`: the ground-truth
  receipt schema plus `compare_ground_truth()` /
  `assert_ground_truth_parity()` (see adaptation contract item 5 above for
  the full field list and checks). **Owed**: running the actual fixture
  build end-to-end on one real Mac and one real VPS to produce the two
  receipts this compares.
- **Item 3 (stale-env preflight) — fully shipped, no live leg.**
  `browser_manager.py::stale_env_preflight()` / `browser_manager.sh
  ::bm_stale_env_preflight()` (wired into `bm_ensure()` — see the "Docker
  env-file / workdir" row above). Every input is injectable, so "fires on a
  seeded stale `.env`, silent otherwise" (this unit's BINARY acceptance (d))
  is fully hermetic — no live leg outstanding for this item.

All three mechanisms are covered by
`tests/test_b_u15_env_matrix_live_proof.py` (hermetic, no network, no Docker,
no live browser) plus the pre-existing `tests/test_env_matrix.py` (still
green, unmodified acceptance).
