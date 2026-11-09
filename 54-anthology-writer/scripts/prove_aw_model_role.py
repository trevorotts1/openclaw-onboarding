#!/usr/bin/env python3
# =============================================================================
# SKILL 54 — ANTHOLOGY WRITER :: MODEL-ROLE PROVER  (fail-closed, stdlib-only)
# -----------------------------------------------------------------------------
# FIX-13: Model-role correctness — the engine never reads model-map.json for
# dispatch; P2/P4/P5 dispatch no model. This prover closes the gap:
#
#   (a) reads model-map.json (the RESOLVED client model map)
#   (b) reads RUN-LEDGER.json (the run ledger from FIX-02)
#   (c) validates the model each stage used is in the resolved model-map
#
# AF-AW-MODEL-ROLE — a model id in RUN-LEDGER.json is not in the
#   resolved model-map (model-role contract violation).
#
# EXIT: 0 PASS · 2 AUTOFAIL · 3 USAGE/IO.
# USAGE: prove_aw_model_role.py <RUN-LEDGER.json> <model-map.json> [--json] | prove_aw_model_role.py --self-test
# =============================================================================
"""Fail-closed model-role prover for Skill 54 Anthology Writer."""

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _aw_common as c  # noqa: E402

AF_MODEL_ROLE = "AF-AW-MODEL-ROLE"

_FIX = Path(__file__).resolve().parent.parent / "test-fixtures"


def _model_ids(ledger: dict) -> list:
    """Extract (stage_id, model) pairs from the run ledger."""
    ids = []
    for stage in ledger.get("stages", []) if isinstance(ledger, dict) else []:
        if isinstance(stage, dict):
            for key in ("model", "model_id", "resolved_model"):
                v = stage.get(key)
                if v:
                    ids.append((stage.get("stage_id", "?"), str(v)))
    return ids


def _model_map_models(model_map: dict) -> set:
    """Collect every resolved model id from every tier in the model map."""
    models = set()
    tiers = model_map.get("tiers", {}) if isinstance(model_map, dict) else {}
    for _tier_name, tier_obj in tiers.items():
        if isinstance(tier_obj, dict):
            m = tier_obj.get("model", "")
            if m and isinstance(m, str) and m.strip():
                models.add(m.strip())
    return models


def evaluate(ledger: dict, model_map: dict) -> c.Result:
    """Validate model-role correctness: every stage model is in the resolved model map."""
    r = c.Result("prove_aw_model_role")
    ids = _model_ids(ledger)
    allowed = _model_map_models(model_map)

    if not ids:
        r.fail(AF_MODEL_ROLE, "RUN-LEDGER.json records no resolved model id "
               "(empty/absent stages) — model-role provenance is REQUIRED; "
               "the model-role gate cannot pass vacuously on an unproven run")
        return r

    if not allowed:
        r.fail(AF_MODEL_ROLE, "model-map.json contains no resolved model ids "
               "— the model map is unpopulated (client install unresolved?)")
        return r

    for stage_id, model in ids:
        if model.strip() not in allowed:
            r.fail(AF_MODEL_ROLE, "stage %s resolved to model %r which is NOT in the "
                   "resolved model-map.json — model-role contract requires every stage's "
                   "model to be one of the client's resolved tiers" % (stage_id, model))

    if r.passed:
        r.note("%d resolved model id(s), all in the resolved model map"
               % len(ids))
    return r


def prove(ledger_path, model_map_path, as_json=False) -> int:
    ledger = c.read_json(ledger_path)
    model_map = c.read_json(model_map_path)
    return evaluate(ledger, model_map).emit(as_json)


def self_test() -> int:
    checks = []

    # Golden: all models in the golden RUN-LEDGER are in the golden model-map.
    g_ledger = c.read_json(_FIX / "golden" / "RUN-LEDGER.json")
    g_map = c.read_json(_FIX / "golden" / "model-map.json")
    checks.append(("golden ledger + model-map PASS (all models in map)",
                   evaluate(g_ledger, g_map).passed))

    # Attack: a model not in the model map fails with AF-AW-MODEL-ROLE.
    nm_ledger = c.read_json(_FIX / "attack" / "ledger_model_not_in_map.json")
    nm_result = evaluate(nm_ledger, g_map)
    checks.append(("model-not-in-map ledger AUTOFAILs AF-AW-MODEL-ROLE",
                   any(code == AF_MODEL_ROLE for code, _ in nm_result.violations)))

    # Empty ledger fails with AF-AW-MODEL-ROLE (vacuously passing is not allowed).
    empty = c.read_json(_FIX / "attack" / "ledger_no_provenance.json")
    empty_result = evaluate(empty, g_map)
    checks.append(("empty-provenance ledger AUTOFAILs AF-AW-MODEL-ROLE",
                   any(code == AF_MODEL_ROLE for code, _ in empty_result.violations)))

    # Empty model map fails.
    empty_map_result = evaluate(g_ledger, {})
    checks.append(("empty model map AUTOFAILs AF-AW-MODEL-ROLE",
                   any(code == AF_MODEL_ROLE for code, _ in empty_map_result.violations)))

    return c.selftest_report("prove_aw_model_role", checks)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Anthology Writer model-role prover (Skill 54, FIX-13).")
    ap.add_argument("ledger_path", nargs="?",
                    help="RUN-LEDGER.json to prove")
    ap.add_argument("model_map_path", nargs="?",
                    help="model-map.json (resolved client model map)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-test", dest="self_test", action="store_true")
    args = ap.parse_args(argv)
    if args.self_test:
        return self_test()
    if not args.ledger_path or not args.model_map_path:
        ap.error("RUN-LEDGER.json and model-map.json paths are required (or use --self-test)")
    return prove(args.ledger_path, args.model_map_path, as_json=args.json)


if __name__ == "__main__":
    sys.exit(main())
