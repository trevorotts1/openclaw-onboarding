# Full-Funnel Pipeline (SOP-07 enforcement)

Executable enforcement + on-fixture evidence for the P0→P5 full-funnel value
stream specified in
`../master-orchestrator-dept/SOP-07-Full-Funnel-Build-Orchestration.md`.

Before this directory, SOP-07 + the persona-grounded SOPs were correctly WIRED
but unenforced: `funnel_rollback` existed only as prose, no end-to-end run had
produced the evidence files the acceptance checklist names, and no per-rubric
scorecards existed. This directory closes those gaps with code that runs
**offline** — no live CRM, no live Gemini, no network.

## Contents

| File | What it is |
|------|------------|
| `funnel_rollback.py` | Executable implementation of SOP-07 §7. Byte-identical page revert (`ghl_rest_canvas.is_byte_identical`/`blob_md5`), idempotent delete of created-but-UNVERIFIED ecosystem objects (qc-passed objects are kept), test-contact delete, and `funnel_rollback.json` with replay-safe `parent_task_id`+`idempotency_key`. All clients injected → unit-testable without a CRM. |
| `funnel_fixture_harness.py` | Deterministic P0→P5 run. Each stage reads its upstream artifact (exercising the `depends_on` edges) and writes the artifact SOP-07 names. Drives the REAL `persona-selector-v2.py` for the web-development funnel surface. Emits the evidence tree + `final-preview-verify.json` (RAW) + `verify-summary.json` (derived, with a VerifyContradiction guard). Parent epic reaches done ONLY at 7/7. `--inject-failure p4-build` drives the FAILED→rollback path. |
| `funnel_rubrics.py` | The 11 acceptance rubrics — `R-COPY`, `R-STRUCTURE`, `R-PAGES`, `R-FORMS`, `R-PRODUCT`, `R-TAGS`, `R-EMAILS`, `R-AUTOMATIONS`, `R-PERSONA-GROUNDING`, `R-KANBAN-CORRECTNESS`, `R-CC-SYNC` — each scored ≥ 8.5 **by reading the RAW evidence**. NOT self-certifying: a missing artifact, an unAPPROVED copy, a non-7/7 rollup, a contradicted summary, or a converge-invariant failure scores that rubric below 8.5. `--gate` exits non-zero on any sub-threshold rubric. |
| `tests/test_full_funnel_pipeline.py` | T-1..T-9 happy-path integration + T-N1..T-N6 negatives + `funnel_rollback` idempotency (24 tests). |
| `evidence/fixture-run/` | A committed reference run: offer-spec.json, funnel-spec.json, hormozi persona-selection-log, copy.md APPROVED, ecosystem receipts, `logs/final-preview-verify.json` (7/7), `scorecard/verify-summary.json`, and the 11 per-rubric scorecards + `RUBRIC-SCORECARD.md`. Portable (repo-relative paths, no secrets). |

## Run it

```bash
# Happy path → 7/7 evidence tree
python3 funnel_fixture_harness.py --run-dir /tmp/run

# Score the 11 rubrics from that evidence (CI gate mode = nonzero exit on any < 8.5)
python3 funnel_rubrics.py --run-dir /tmp/run --cc-invariant-ok 1 --gate

# Failure path → funnel_rollback + parent NOT published
python3 funnel_fixture_harness.py --run-dir /tmp/fail --inject-failure p4-build

# Full test suite
python3 -m pytest tests/ -q
```

CI: `.github/workflows/full-funnel-pipeline.yml` runs the persona selector test,
the pipeline pytest, the seed-workspaces normalizer test, and the rubric
scorecard gate on every push/PR to `main`.

## Scope note (what this does NOT do)

This harness proves the **pipeline contract** end-to-end against an offline
fixture. It does NOT make a LIVE GoHighLevel build (that is gated behind the
operator fixture + funded location, per `v2-autonomous-build-sop.md`). The
`R-CC-SYNC` rubric reads the converge invariant signal (`total_roles == sum`,
`departments == N`) which is produced by `sync-extensions.sh --converge`; it does
not by itself prove the operator's full role/SOP library is complete (that is the
separate concern measured by `verify-library-gate.sh` / `verify-wiring.sh`
against the live workspace).
