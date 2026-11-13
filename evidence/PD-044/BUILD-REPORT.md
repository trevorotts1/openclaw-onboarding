# PD-044 — A capacity probe that runs on a Mac and reads the real dependency list

- **Unit:** PD-044 (lane FL14, repository trevorotts1/openclaw-onboarding)
- **Branch:** `pd/fl14-role-procedures-a`
- **Base head at start:** `b7084c3b1` — PD-041: deliver to the client's own DELIVERY_DESTINATIONS answer
- **Builder:** deepseek-chain
- **Live actions:** none. Files only; no box opened, nothing executed on a client machine.

## Prior work on this branch (named, undisturbed)

| Commit | Unit | State |
|---|---|---|
| `38d1dd364` | PD-040: point role procedures at the paths the engine writes | ACCEPTED |
| `c51fbf2b7` | PD-904: Director procedure reads the intake the driver writes, not deck_brief.json | ACCEPTED |
| `4c15ef2af` | PD-903: role files carry the mirror-only sections; mirrors regenerate equal | ACCEPTED |
| `b7084c3b1` | PD-041: deliver to the client's own DELIVERY_DESTINATIONS answer | ACCEPTED |

PD-044 touches only the Capacity and Reliability Engineer pair. The Delivery Concierge, Speech QC and Director role files and their mirrors were not read for edit and not changed. PD-041's section 9 / mirror equality on the Delivery Concierge pair is untouched.

## Files changed (lane-owned only)

- `23-ai-workforce-blueprint/templates/role-library/presentations/capacity-reliability-engineer.md`
- `23-ai-workforce-blueprint/templates/role-library/presentations/sops/capacity-reliability-engineer-sops.md`

## Verification the unit asked for: what `--capacity` actually carries

Read `scripts/presentation_job/__main__.py` `cmd_capacity` (lines 891-900) and `scripts/presentation_job/capacity.py` `probe()` / `format_report()` (report emitter at line 3056). `cmd_capacity` calls `capacity.probe()` and prints `capacity.format_report(result)`; nothing else.

The report carries:

- probe mode, status, detection source, provider, plan
- dispatchable availability, reserve, effective available, working-concurrent count and its measurement method
- fleet shape (recorded/detected/candidates) and gauge state
- one row per provider: plan, ceiling (or UNBOUNDED / UNMEASURED), whether the plan was answered, source, probed flag
- provider key inventory: presence only, never a value, plus unlocked model count
- 9Router lineup: wired model count and provider aliases
- detection trail

It does **not** carry memory, processor count, load average or disk. Proof — hardware metrics inside the module:

```
$ grep -n "cpu_count\|virtual_memory\|disk_usage\|sysctl\|loadavg\|hw.ncpu\|hw.memsize" presentation_job/capacity.py
NONE
```

(The only `psutil` use in the module is `process_iter` for the working-concurrent count, line 2200-2216.)

So all four hardware values got an explicit macOS/Linux command pair in SOP 9.1 step 1, and step 2 now computes from those pairs:

| Value | macOS | Linux |
|---|---|---|
| free RAM | `sysctl -n hw.memsize` + `memory_pressure -Q` | `awk '/MemTotal\|MemAvailable/ {print $2}' /proc/meminfo` |
| processor count | `sysctl -n hw.ncpu` | `nproc` |
| 15-minute load | `sysctl -n vm.loadavg` | `cat /proc/loadavg` |
| free disk | `df -k /` | `df -k /` |

## Edits

1. **SOP 9.1 step 1** — the four commands replaced with `python3 <SCRIPTS_DIR>/presentation_job.py --capacity`, the list of what its report carries, and the macOS/Linux pairs for the four hardware values it does not carry.
2. **SOP 9.1 step 2** — `free_ram_gb` / `cpu_cores` / `cpu_load_15min` / `free_disk_gb` now name the exact source command per platform (no `free -h` "free" column).
3. **SOP 9.1 step 11** — the three named tools replaced with: run the door's dependency gate in plan mode and read its result; every entry marked `required` in `presentation-deps.json` must be present. The gate is GATE 1 of `bash <SCRIPTS_DIR>/presentation-canonical-entry.sh --plan` (verified in `presentation-canonical-entry.sh`: `deps_check` runs before the `--plan` exit, prints `OK: all runtime deps present` at line 902, or exits 6 with `PRESENTATION_DEPS_MISSING: <list>` at line 899). The director-facing flag sentence is kept.
4. **SOP 9.2 step 1 and failure mode** — both `… | grep …` probes replaced with: Mac `launchctl print gui/$(id -u)/com.blackceo.presentation-watchdog` exits 0; Server `openclaw cron list --json` contains an entry whose name is exactly `presentation-watchdog`.
5. **SOP 9.2 Outputs** — the three per-deck watchdog output lines removed, replaced with `capacity_plan.json` records `watchdog: installer-managed`.
6. **Outside section 9, same file, same fix** — section 8 "Tools You Use" (4 lines), section 15 mistake 1, and edge case 17.1 named the retired commands (`free -h`, bare `nproc`, `uptime`, `df -h`, `vm_stat`). All now name the platform pairs, so no file in this pair recommends a probe the unit replaced.

### Pre-existing mirror drift found and fixed

At the start head the Capacity pair was **not** equal: role section 9 line 243 said "the catalog-resolved QC scoring model"; the mirror line 130 said "the client's chosen vision/QC model … independent from the producer; no self-grading". Both lines arrived together in `41c7e3278`. The role file is authoritative per the mirror header, and "catalog-resolved QC scoring model" is the department-wide term (7 other role files use it; the mirror's variant is the outlier). The mirror was regenerated from the role file's section 9, so the pair is now strictly equal. No role-file content was changed to force equality.

## Acceptance

### Mirror check (strict, line by line)

Command (script kept at `/Volumes/mac mini m4/swarm-contract/pd-fix/scratchpads/PD-044/mirror_check.py`):

```
python3 -I .../scratchpads/PD-044/mirror_check.py \
  capacity-reliability-engineer.md sops/capacity-reliability-engineer-sops.md
```

Output:

```
role   section 9: 149 lines  (capacity-reliability-engineer.md)
mirror section 9: 149 lines  (capacity-reliability-engineer-sops.md)
STRICT EQUAL
```

### Banned strings (read the file, report)

```
role   free -h: 0   grep: 0   launchctl list: 0
mirror free -h: 0   grep: 0
```

`nproc` appears only as the Linux half of the pair: inside the macOS/Linux block in step 1 (macOS `sysctl -n hw.ncpu` on the line above), and in step 2 as "`sysctl -n hw.ncpu` (macOS) or `nproc` (Linux)".

### Dependency canon

```
$ python3 -c "import json; d=json.load(open('scripts/presentation-deps.json')); print([x['name'] for x in d['deps'] if x.get('required')])"
['soffice', 'pdftoppm', 'python:reportlab+pptx', 'python:pypdf', 'tesseract', 'python:pytesseract']
```

Six required entries; the procedure now points at the gate that enforces exactly this list instead of naming three tools by hand.

## Test note

`python3 -I test_retired_roles.py` in the presentations role directory reports `FAILED (failures=1)`: `test_1_pattern_registered_with_correct_shape` expects 5 patterns, the registry holds 9. Pre-existing and unrelated — the test counts `retired-doctrine-patterns.json`, which this unit did not modify (working tree contains only the two markdown files above); all other 5 tests in that file pass.

## Scope

No engine code, no tests, no manifest, no other lane's files. No merge, no push to main, no rebase.
