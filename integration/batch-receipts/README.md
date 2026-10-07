# integration/batch-receipts — W5-01-U1 batch controller integration receipts

Proof that eligible, dependency-closed candidates land **only through the
30-minute batch window gate**, with fetched remote ancestry proof, and that no
individual builder merges. All of it ran against a **scratch candidate set** in
the unit lane (`swarm-plans/lanes/W5-01-U1-lane/scratch/`): its own git repo +
local bare `origin`. No real repo, no remote push, no crontab, no timer install.

## Method

1. **Scratch set** — repo with candidates `unit/W501U1-A` (independent),
   `unit/W501U1-B` (stacked on A → batch set {A,B} dependency-closed),
   `unit/W501U1-C` (QC FAIL), `unit/W501U1-D` (arrives after the window).
   QC records written through the existing `ledger.sh` into the scratch
   project's `CONTROL/LEDGER.md`; registry at `CONTROL/repos.json`.
2. **Gate** — `batch-window.sh` (this directory). Cadence + lock mirror
   `watch-tick.sh`'s `merge_batch`: `merge-batch.stamp` age must be ≥
   `MERGE_BATCH_MINUTES` (30, read **at the invocation**, not an interactive
   export), `merge-batch.lock.d` forbids overlap. Two reconciliations required
   by `packet/claude-nine-swarm/GITHUB-MERGE-RULES.md`: missing stamp is seeded
   at **T0** (no immediate first merge; first window = T0+30min), and the
   30-minute value rides the invocation.
3. **Merge** — only the existing
   `999-setup/.claude/skills/spec-protocol/tools/merge-train.sh <home> --batch`
   runs: QC selection (`ready_ids`), one combined-candidate gate
   (`test -f cand-a.txt && test -f cand-b.txt`), one `--no-ff` pass, **one
   push, then fetched ancestry proof** (`MERGED: … trunk=origin/main`),
   post-proof cleanup. Train invoked with committer `batch-train`, so every
   landing is attributable.
4. **Negative control** — D is QC-PASS and dependency-closed, presented right
   after the window closed → gate prints `WINDOW-REFUSED reason=window-cadence-not-due
   stamp_age=21s < 1800s`, rc=2, train never invoked, D never reaches
   `origin/main`. Second negative: C stays out via the train's own QC filter.

## Receipts (this directory)

| File | What |
|---|---|
| `candidate-manifest.json` | candidates, tips, QC, deps, closure proof, batch id `BATCH-W501U1-1` |
| `window-receipts.jsonl` | gate events: 1 batch (window 30 = `[T0+1800k, T0+1800(k+1))`, stamp_age=54220s) + 1 refusal (stamp_age=21s) |
| `batch-1.log` | raw train output: LANDED/MERGED/CLEANED, gate `tests=pass`, `trunk=origin/main` |
| `negative-1.log` | raw `WINDOW-REFUSED` refusal |
| `proof-ancestry.txt` | independent `merge-base --is-ancestor` re-proof vs freshly fetched `origin/main`: A,B ∈; C,D ∉ |
| `builder-merge-scan.json` | trunk history: 2 merges, both by `batch-train` inside the batch run; 0 builder merges; builder commits frozen before window open |
| `negative-controls.json` | NC-QC-FAIL + NC-OUTSIDE-WINDOW results |
| `scratch-ledger.md` | copy of the scratch `CONTROL/LEDGER.md` (QC records + train lines) |
| `merge-train-selftest.log` | existing train's own `--selftest` (5/5 ok) |
| `verify.sh` + `verify.log` | the one runnable check: 28/28 PASS |

## Re-run

```bash
bash /Users/blackceomacmini/drama-song-factory-build/integration/batch-receipts/verify.sh
```

`verify.sh` re-fetches the scratch `origin` and re-proves ancestry, window
math (T0 from `run/state.json` `build_started_unix` = 1791300227, windows of
1800s), refusal timing, and the zero-builder-merge scan. It needs the lane
scratch repo alive; `verify.log` is the captured run.

## Scope

Scratch-lifecycle proof of the existing controller wiring (acceptance of
W5-01-U1). Production timer wiring for the real build stays with the owners in
`build-control/project-bindings/bindings.json` (`merge_owner` = merge-train.sh,
`tick_owner` = watch-tick.sh, `merge_seconds` 1800 / heartbeat 300). This unit
modified none of them.
