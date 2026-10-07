# tests/ci-provenance — W4-05-U1 CI + provenance + secret closure

Unit **W4-05-U1** (SWARM-PLAN W4-05). Stdlib python3 + `gh` + `git`.
No network writes, no repo mutations, no secrets printed. Nothing outside
this folder written except receipts here; scratch lives in
`/tmp/blackceomacmini-W4-05-U1-*` (removed by the run).

## Run

```sh
bash run_ci_provenance.sh    # all three, combined table + exit code
python3 ci_matrix.py         # checker 1 alone (needs gh auth)
python3 provenance_closure.py
python3 secret_scan.py
```

Exit `0` = all PASS, `1` = any FAIL, `2` = tooling failure (instrument
broken — never reported as a clean pass).

## Acceptance → where proved

| Clause | Proof |
|---|---|
| **CI matrix green** | `ci_matrix.py` → `receipts/ci-matrix.json`: 7/7 rows GREEN — 4 build-proposed-merge PR heads (999 #40 `8203088`, #41 `bb7c40d`, CC #487 `2b8939f`, onboarding #1563 `2a95ab10`) at the SHA the gates judged, plus current origin/main tips of all three repos. 0 red, 0 pending after bounded poll (26 × 20s window; onboarding `QC static invariants` measured at 6–8 min, so a short poll reads healthy-but-running as pending). Branch-protection contexts recorded per repo. |
| **Provenance closure receipts** | `provenance_closure.py` → `receipts/provenance-closure.json`: 16/16 records valid — artifact provenance contract (`core/contracts/artifact-schema.json` provenance fields), delivery writer (`core/delivery_variants/manifests.py`), run campaign provenance + receipts + reconciliation set (W3-04), merge provenance (all 4 rows fetched-ancestry-proven), donor/repo/provider/runtime planning records, third-party notices in both distributions, 3 recorded QC verdicts. Each record carries sha256. |
| **Secret-scan clean** | `secret_scan.py` → `receipts/secret-scan.json`: 1294 files walked (1265 text-scanned) + 2265 git blobs across the tree's git object stores; 395 secret-named env values byte-searched; **0 real, 0 unclassified, 0 env-value hits**. 53 placeholder-doc hits (`OPENROUTER_API_KEY=replace_with_real_key` in 999 docs) and 2 git-fixture hits classified with proof, see below. |

## Controls (a zero is not evidence without them)

| Control | Expect | Where |
|---|---|---|
| A roundtrip | `verify_binding` ok=True on freshly written provenance | provenance_closure |
| B manifest tamper | `verify_binding` refuses | provenance_closure (negative) |
| C artifact tamper | `verify_binding` refuses | provenance_closure (negative) |
| A pattern plant | fabricated `ghp_…` in `/tmp` detected | secret_scan |
| B env-value plant | one real env value (memory only) detected | secret_scan |
| C git-object plant | key committed into throwaway repo detected by object walk | secret_scan (proves the git scan is not a broken walk) |
| negative end-to-end | plant `ghp_` in build tree → full scan exits **1**, remove → exit 0 | verified live this run |

## Findings worth knowing

1. **2 git-object hits are test fixtures, not live credentials** — both
   cleared only via evidence, never by assumption:
   - `holding/slice5-test/verify-image-lane.sh` blob `00b9912…` — line
     annotated `dead key, known bad`; not in HEAD/origin, not in env stores,
     not in working tree.
   - `.claude/skills/kaizen/tests/run-kaizen-tests.sh` blob `17b1ca0…` —
     the kaizen fixture that *plants* `sk-proj-` via `printf` to prove its
     own scanner detects keys (HEAD line 290); constructed at runtime, not
     a stored credential; absent from env stores and working tree.
   - Clearing requires **all three**: path in `GIT_FIXTURE_PATHS`, value
     absent from operator env credential stores, value absent from current
     working tree. Anything else in git objects = `unclassified` → FAIL.
2. Repo `trevorotts1/999-setup` is **public** — the fixture strings are
   reachable via the two commits above; both are test-discrimination
   artifacts, recorded as such in the receipt.
3. `scan_text` decides `placeholder`/`fixture` while the line is in hand,
   so historical blobs tier against their own content, not the current file.

## What this suite does NOT do

- No repo writes, no merges/publishes (blocked by unit contract).
- No branch-protection *enforcement* claim: only `required_status_checks`
  contexts as configured are recorded (onboarding/CC contexts null,
  999 no protection) — green check-runs are proven, protection config
  is reported as found.
- Secret scan covers this build tree's working files + its git object
  stores; it does not scan the three upstream repos' full remote history.

## Receipts

`receipts/ci-matrix.json`, `receipts/provenance-closure.json`,
`receipts/secret-scan.json` — schemas `blackceo.ci-provenance/{ci-matrix/v1,
provenance-closure/v1, secret-scan/v2}`, all stamped `unit_id: W4-05-U1`.
Matched secret text and env values are never written into receipts; only
counts, sha256 prefixes, keys and paths.