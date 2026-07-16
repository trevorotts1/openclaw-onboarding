# Certificate aggregation and signing (build unit U20)

Owner script: `scripts/prove_certificate.py`
Schema: `structure/process-certificate.schema.json`
Phase: P16-CERTIFY (`CWFE-MANIFEST.json`, `af_code: AF-CWFE-P16-CERTIFY`)
Cross-cutting: `AF-CWFE-SECRET-LEAK` (`py_symbol: prove_certificate.assert_no_secret_values`)

## What this unit builds

`prove_certificate.py` is two things in one file, matching the manifest's own
declaration for P16-CERTIFY (`"produces_artifact": "PROCESS-CERTIFICATE.json
(signed, final artifact index)"`, `"gate": "scripts/prove_certificate.py"`):

1. **A deterministic prover aggregator.** Given a `run_dir`, it re-runs every
   one of the 16 upstream phase gates (P0-ENVIRONMENT .. P15-PRODUCTION) —
   `prove_p0_environment.py`, `prove_intake.py`, `prove_content.py` (x2,
   P2/P3), `prove_budget.py` (x2, P4/P5), `prove_media.py` (x4,
   P6/P7/P8/P9), `verify_seams.py`, `prove_site.py`, `prove_conversion.py`
   (P12 — not yet built as of this unit, see "current real state" below),
   `run_browser_qc.py`, and `prove_deployment.py` (x2, P14/P15) — against
   the SAME `run_dir`, through the identical uniform gate contract
   `run_cinematic_web_funnel.py`'s own orchestrator uses:
   `<gate> --run-dir <run_dir>`, exit code 0 means PASS. It never trusts a
   prior `phase-status.json` or any agent's claim that a phase already
   passed — every invocation re-derives every verdict from scratch.
2. **The signed PROCESS-CERTIFICATE emitter.** Only when all 16 upstream
   gates come back PASS, the run-scoped front-door nonce file
   (`<run_dir>/.cwfe_run_nonce`, ADR-6) is present and non-empty, and a
   full artifact scan finds no secret VALUE anywhere under `run_dir`, does
   it build a 17-entry (P0..P16) certificate object, validate it against
   `structure/process-certificate.schema.json` (created by this unit — it
   did not exist before U20), sign it with HMAC-SHA256 keyed by the
   run-scoped nonce, validate the signed object against the schema again,
   and atomically write `PROCESS-CERTIFICATE.json`.

`certificate-status.json` is written into `run_dir` on **every** invocation
— pass or fail — so a rejected certification attempt still leaves a fully
evidence-bearing audit trail (the same pattern every other `prove_*.py` in
this skill already follows, e.g. `prove_p0_environment.py`'s
`environment-receipt.json`).

## Fail-closed rules enforced (no certificate on a red gate)

| Condition | AF code | Result |
|---|---|---|
| Any upstream gate script missing on disk | phase's own `AF-CWFE-P<N>-*` (surfaced as `GATE-SCRIPT-MISSING`) | withheld |
| Any upstream gate script exits non-zero | phase's own `AF-CWFE-P<N>-*` (surfaced as `FAIL`) | withheld |
| A secret VALUE found anywhere under `run_dir` | `AF-CWFE-SECRET-LEAK` | withheld |
| No/empty `.cwfe_run_nonce` file | `AF-CWFE-CERT-NO-NONCE` | withheld |
| Manifest phase spine malformed (not 17 phases, or not orders 0..15 + one 16) | `AF-CWFE-CERT-PHASE-GAP` | withheld |
| Constructed/signed certificate somehow fails its own schema (should never happen) | `AF-CWFE-CERT-SCHEMA` | withheld |

Every one of these returns `(False, detail)` from `evaluate()` **before**
any certificate write is attempted — the write call is the very last
statement in the success path, not a step that can be reached and then
rolled back.

## Standalone re-verification: `verify(cert, nonce)`

`CWFE-MANIFEST.json` names `prove_certificate.verify` as the P16-CERTIFY
`py_symbol`. `verify()` is the standalone counterpart to `evaluate()`: given
an **already-emitted** certificate object (e.g. read back off disk later,
by a merge-ticket check, a restart/resume audit, or an independent QC pass)
and the nonce that should have signed it, it independently re-checks:

1. schema shape (`structure/process-certificate.schema.json`);
2. the `certificate` discriminator field;
3. phase-order contiguity 0..16 (catches a duplicated/skipped order even
   when the schema's own `minItems`/`maxItems: 17` cannot, e.g. a
   duplicated order value with the count still correct);
4. every phase's `status == "PASS"` and `all_phases_pass == true`;
5. the `nonce_fingerprint` matches `sha256(nonce)[:16]`;
6. the HMAC-SHA256 `signature` verifies (`hmac.compare_digest`, constant-time).

Any failure appends `AF-CWFE-PROCESS-INTEGRITY` ("process certificate
invalid — engine run is NOT certified"), mirroring
`49-signature-funnel/scripts/prove_sf_cert.py`'s own `verify()` shape and
its `AF-FUN-PROCESS-INTEGRITY` terminal code.

Standalone CLI usage:

```bash
python3 scripts/prove_certificate.py --verify PROCESS-CERTIFICATE.json --nonce <the-run-nonce>
# or, to read the nonce from the run directory automatically:
python3 scripts/prove_certificate.py --verify PROCESS-CERTIFICATE.json --run-dir <run_dir>
```

## Why the schema only checks shape, not "all PASS"

`structure/process-certificate.schema.json`'s `status` enum permits
`PASS`, `FAIL`, and `GATE-SCRIPT-MISSING` — not just `PASS` — on purpose.
The same schema is used to validate BOTH a genuinely-emitted, all-green
certificate AND (conceptually) any other certificate-shaped object passed
through the shape-checker before its semantic verdict is read. Whether
every phase is actually `PASS` is a **semantic** rule, enforced in code by
`evaluate()`/`verify()`, exactly matching this skill's established
doctrine — see `prove_deployment.py`'s own docstring: "schema validity was
already enforced ... this is a DIFFERENT, semantic pass over the same
data."

## The "final artifact index"

Spec Section 16 requires P16 to produce "a signed process certificate and
final artifact index." `_build_artifact_index()` derives the expected
filename for every P0-P15 phase directly from that phase's own
`produces_artifact` string in `CWFE-MANIFEST.json` (e.g.
`"cost-ledger.json (signed/recorded paid-call authorization)"` →
`cost-ledger.json`), deduplicates (`cost-ledger.json` and
`deployment-receipt.json` each legitimately appear twice, once per phase
that touches them), searches `run_dir` recursively for each, and records
`{path, sha256, bytes}` for every one that is actually present. No
filename is invented — every entry traces back to the manifest.

## AF-CWFE-SECRET-LEAK

`assert_no_secret_values(run_dir)` walks every text-like file under
`run_dir` (skipping `node_modules/`, `.git/`, `.next/`, `__pycache__/`,
`.venv/`, `dist/`, `build/`, and binary media by extension), and reuses
`build_site.SECRET_PATTERNS` — the **same detector** `prove_deployment.py`
already reuses for its own receipt scan (see that module's docstring point
2) — rather than forking a third pattern list. A finding is reported as
`"<relative-path>: matched secret pattern <regex>"` — the matched TEXT
itself is never included, so a failed scan can never itself become a leak
(spec Section 20: "never log secret values").

## Known integration seam (out of this unit's file area)

`run_cinematic_web_funnel.py` (skill root, **outside** `scripts/` +
`references/` — this build unit, U20, is restricted to those two
directories) still ends its phase loop with its own inline
`_emit_certificate()`, which signs a nonce-keyed `sha256` "seed" hash over
the in-memory phase results — its own comment already says this is
"upgraded to a proper HMAC scheme when the certificate prover lands
(P16-CERTIFY gate)." Because that inline call runs immediately **after**
this script returns PASS for the P16 phase (the orchestrator's phase loop
invokes P16's gate — this script — like every other phase, then only
calls `_emit_certificate()` once the *entire* loop, P16 included, finishes
green), on a live fully-orchestrated run it will **overwrite** the real,
schema-validated, HMAC-signed certificate this module just wrote with its
own simpler placeholder object.

This is a real, observable seam, not a hidden one:

- Standalone invocation (`python3 scripts/prove_certificate.py --run-dir
  <dir>`, run directly rather than through the orchestrator's subprocess
  loop) is **unaffected** — it always produces and leaves in place the
  real signed certificate, and this is the way `--self-test` and every
  test in this unit exercises it.
- A live end-to-end orchestrated run (`cinematic-web-funnel-entry.sh
  --run-dir <dir>`) will currently end with the orchestrator's own
  placeholder overwriting this module's certificate, because
  `run_cinematic_web_funnel.py` has not (yet, and not by this unit) been
  changed to call `prove_certificate.evaluate()`/its signing path directly
  instead of its own inline `_emit_certificate()`.
- Fixing this requires editing `run_cinematic_web_funnel.py` itself, which
  sits outside `scripts/` + `references/` — out of scope for U20
  (`U20=scripts/`, `U21=tests/` per this build's file-area assignment).
  Flagged here explicitly for whichever unit/integrator owns the
  orchestrator file next, rather than silently worked around or hidden.

## Current real repository state (as of this unit, HEAD `bfeb0ac4` + U20)

Running `prove_certificate.py --run-dir <bare-run-dir-with-only-a-nonce-file>`
against the REAL, unmodified `CWFE-MANIFEST.json` and this skill's own
`scripts/` directory correctly withholds the certificate today, because:

- 15 of the 16 upstream gates genuinely `FAIL` against a bare run_dir (no
  locked intake, no approved content, no budget approval, no generated
  media, no built site, no deployment — none of the real upstream
  artifacts a genuine project run would have produced yet); and
- P12-CRM's declared gate, `scripts/prove_conversion.py`, does not exist
  on disk as of this unit (U16 built the CRM/GHL conversion components
  themselves but not a dedicated `prove_conversion.py` gate script), so it
  reports `GATE-SCRIPT-MISSING`.

This is exactly the fail-closed behavior the directive requires — a
missing OR failing gate withholds the certificate, with no exception —
and `self_test()`'s Part F exercises this against the real repository (not
a synthetic fixture) so the assertion stays honest as later units land.
