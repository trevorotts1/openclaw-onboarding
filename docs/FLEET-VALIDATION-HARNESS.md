# Fleet roll: the per-box ledger + post-fan-out validation harness

**FLEET-FIX 4b / AUD-58.** This is the HARD GATE in front of **the ONE batched fleet roll**.
Nothing is "rolled" until this harness is green on every box in the wave.

The failure mode it closes is specific and has happened before:

> **a fan-out that reports GREEN on a broken box.**

An aggregate exit code is the one number a partially-failed fan-out is worst at. So the roll
now leaves **evidence per box**, and the evidence is **fail-closed**: nothing becomes green by
default, by silence, or by timeout.

---

## The two pieces

| Piece | Path | What it is |
|---|---|---|
| Per-box ledger | `shared-utils/fleet_ledger.py` | one persistent JSON row per box at **`/tmp/<sweep>/<box>.json`**, plus a `_sweep.json` rollup. Bash-callable CLI, so the roll's own fan-out loop writes rows with no Python glue. |
| Validation harness | `shared-utils/fleet_validation_harness.py` (CLI: `scripts/fleet-validate.sh`) | runs the five REQUIRED checks against each box and writes the verdict into that box's ledger row. |

---

## The five REQUIRED per-box checks

| # | Check id | PASS means | FAIL means |
|---|---|---|---|
| 1 | `mc_api_token_store` | the box's own `check-credential.sh MC_API_TOKEN --json` reports the token present in >= 1 store, live env checked | the token is in **no** store — write-back will 401 forever |
| 2 | `writeback_probe` | the Command Center write-back endpoint answers **2xx or 401** | `000`/`403`/`404`/`5xx`/timeout — the box cannot write its work back |
| 3 | `browser_probe` | the agent-browser preflight exits 0 **and** prints its PASS marker | preflight failed (or exited 0 in silence -> `UNKNOWN`, never green) |
| 4 | `openclaw_ceiling` | `openclaw --version` >= the declared minimum **and** the `runRetries` ceiling row is present and within the declared ceiling | version below minimum (the box did not take the roll / was DOWNGRADED), or the **runRetries row is ABSENT** — an absent row is a FAIL, never a default |
| 5 | `repo_stamp` | the box's onboarding checkout reports the expected **version + sha** | mismatch — **`update-skills.sh` piped from a stale checkout silently rolls a box BACKWARDS**, and the stamp is the only thing that catches it |

**Exit-code trap, encoded on purpose:** `check-credential.sh` exits **3** (`NEEDS_BLOCK`) for
`MC_API_TOKEN`, and that is a **perfectly healthy** verdict — `MC_API_TOKEN` is not a model-provider
key, so no `models.providers` block will ever reference it. The harness judges the **verdict**, not
the exit code. A harness that judged the exit code would fail every healthy box in the fleet.

**Secret discipline.** The token's **value** is never read, never requested, never logged. Check 1 asks
for a verdict (SET / where), not a value. Check 2 sends **no bearer by default** — both because an
unauthenticated POST cannot mutate a live Command Center (a probe that creates a junk task on 20
client boxes is a bug, not a check) and because **401 is the healthy answer anyway**. Every reason and
observed string is scrubbed on the way into the ledger.

---

## Fail-closed contract (why this is a gate, not a report)

* **Undeclared expectation -> the sweep is REFUSED (exit 4), before a single box is touched.**
  You cannot validate a repo stamp nobody named. *A gate you cannot fail is not a gate.*
* **A required check that never ran is a FAIL**, not a skip.
* **`UNKNOWN` is never green.** An ssh timeout means we could not ask the question, so we must not
  answer it — exit 3, roll blocked.
* **A box with no ledger row at all is a FAIL** in the rollup ("missing" never means "fine").
* **A corrupt/truncated ledger row is a FAIL**, not a shrug.
* **Zero boxes is a FAILED sweep**, not a green one.
* **> 20 boxes is REFUSED** (doctrine: <= 20 boxes per wave — split the wave).
* Per-box isolation: one box exploding never aborts the wave, never contaminates another row.

Exit codes: `0` all PASS · `2` any FAIL · `3` any UNKNOWN · `4` sweep refused · `1` fatal.

---

## Running it

### 1. Declare the expectations (once per roll)

```json
{
  "repo_version":         "v19.44.0",
  "repo_sha":             "002f8333...",
  "openclaw_min_version": "2026.5.22",
  "run_retries_max":      3,
  "writeback_url":        "http://127.0.0.1:4000/api/tasks/ingest",
  "repo_dir":             "$HOME/openclaw-onboarding"
}
```

Every field except `repo_dir` is **mandatory**. The expectations are hashed into each ledger row, so
a PASS recorded against the *previous* roll target can never satisfy the next one — `--resume` will
correctly re-probe the box.

### 2. Wave loop (<= 20 boxes), writing the ledger as you go

```bash
SWEEP="roll-v19-44-0"
for BOX in $(cat wave1.txt); do
  # ... update-skills.sh | bash -s   FROM A FRESH CHECKOUT (a stale one DOWNGRADES the box) ...
  python3 shared-utils/fleet_ledger.py record --sweep-id "$SWEEP" --box "$BOX" \
      --check install --status PASS --reason "update-skills applied v19.44.0"
done
```

### 3. Validate the wave — this is the gate

```bash
bash scripts/fleet-validate.sh \
    --sweep-id "$SWEEP" --boxes-file wave1.json \
    --expectations expectations.json --backend ssh --max-parallel 8
```

Green -> the wave is done. Not green -> **the roll is BLOCKED**: fix the named boxes and re-run with
`--resume` (already-green boxes are skipped; the broken ones are re-probed and their history keeps
both attempts).

**Operator-box canary first** (`--backend local --box <this box>`), then client waves. And never run
`qc-completeness.sh` standalone during a roll — it leaks a client Telegram alert. This harness does
not call it and never will.

---

## Proving it without a fleet

`--backend sim --sim-fixture <file>` serves canned probe output, so the whole thing — a 20-box
fan-out, a deliberately-broken box, the loud failure — is reproducible with no ssh, no network and
no live box:

```bash
python3 tests/unit/fleet-ledger-harness.test.py        # 52 tests: every fail-open path
bash    tests/unit/fleet-validation-harness.test.sh    # ACCEPTANCE: 20 boxes, 1 broken, exit 2
```

CI: `.github/workflows/fleet-validation-harness-guard.yml`.
