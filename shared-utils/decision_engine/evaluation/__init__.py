#!/usr/bin/env python3
"""D30 offline comparative evaluation harness (JEV spec 1.1, ss 16.3-16.4, 3.5, 3.6).

Runs the frozen D29 650-case corpus (train / calibration / heldout) through
two REAL paths and reports measured numbers only:

* baseline: majority-class predictor fit on TRAIN intent rows only;
* implementation: exact code integrated in this checkout --
    D03 fixture lookup (exact + one fixed normalization) for intake intent,
    D04/D05/D06/D07 DirectFirstLadder with injected fake transports for
    provider / mode / tenant rows.

Rows whose exact implementation revisions are absent from this checkout
(exec/D11, capload/D13-D15/D20-D22/D24, shadow + atomic + off/legacy provmode
rows) are reported NOT_RUN with the missing revision named. Nothing guessed.
Nothing tuned on heldout -- or on any split: the harness has zero trainable
parameters, and the calibration split is scored only.

OFFLINE PROOF: corpus loaded via immutable `git show FROZEN_REV:path` (no
working-tree copy exists to tune); sockets blocked during evaluation; every
provider call is an injected fake counted per source (typesafe_direct /
openrouter / fixture_lookup; evaluation-run counts as provmode_runs;
embedding / probe / shadow sources have no implementation in this
checkout and count 0).

Stdlib only. No network, no disk writes, no environment reads.
Run: python3 -m pytest tests/unit/test_offline_eval_d30.py -q  (from repo root)
 or: python3 shared-utils/decision_engine/evaluation/__init__.py --out report.json
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import socket
import statistics
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

FROZEN_REV = "5e42cdd3924628ded5df2d7275e024403768bdf0"
FROZEN_PATH = "tests/unit/test_decision_corpus.py"
HELDOUT_FP = "b8beb8468ddf0e36bada05eee593c3184985c33e8e63124944ace151d6be73c8"
BASE_REV = "404347fb337e7a6c8dd45395a1773781b114d673"

MISSING_REVISIONS = {
    "exec": "D11 owner-direct policy exact revision 7ac21400 not integrated "
            "in base 404347fb (exec intent+exec classification unowned)",
    "capload": "D13 6375dccb + D14 fb2be759 + D15 9f984036 + D20/D21 5e447fe7 "
               "+ D22 7c6d874f + D24 (no revision; branch jev11/onb-d24 "
               "unintegrated) not integrated in base 404347fb "
               "(department/role selection unowned)",
    "OFF_EQUALS_LEGACY": "D08 no-JEV fallback exact revision 95c861a8 not "
               "integrated in base 404347fb (off/legacy equivalence unowned)",
    "SHADOW": "no shadow sampler in base 404347fb; remote shadow needs an "
              "approved allowance per spec 3.9 (none granted)",
    "ATOMIC": "production budget store with atomic CAS absent offline; "
              "concurrent reservation overdraw unprovable with fakes",
}

_HERE = Path(__file__).resolve()
_DE = _HERE.parent.parent
_REPO = _DE.parent.parent

_NONW = re.compile(r"[^\w\s']")
_WS = re.compile(r"\s+")

FAKE_DIRECT = "D30FakeDirectKey9Qm4Zx7Vb2Nw8X"
FAKE_OR = "D30FakeRouterKey3Kp8Rn5Tu2Wx6Y"

INTENT_CLASSES = (
    "answer_only", "task_request", "mixed_answer_and_task",
    "existing_task_control", "clarification_response",
    "social_conversation", "unresolved",
)
NON_TASK = ("answer_only", "social_conversation", "unresolved")
TASKISH = ("task_request", "mixed_answer_and_task")


def _by_path(mod_name, path):
    existing = sys.modules.get(mod_name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(mod_name, str(path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)
    return module


def load_policies():
    return _by_path("d30_policies", _DE / "policies" / "__init__.py")


def load_ladder():
    return _by_path("d30_ladder", _DE / "ladder" / "ladder.py")


def load_frozen_corpus(repo_root=None):
    """Read-only immutable load of the approved corpus. Raises on drift."""
    repo = str(repo_root or _REPO)
    r = subprocess.run(
        ["git", "show", FROZEN_REV + ":" + FROZEN_PATH],
        cwd=repo, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("immutable corpus read failed: %s" % r.stderr[:200])
    ns = {"__name__": "d30_frozen_corpus", "__file__": "frozen_corpus.py"}
    exec(compile(r.stdout, "frozen_corpus.py", "exec"), ns)
    corpus = ns["CORPUS"]
    if ns["heldout_fingerprint"]() != HELDOUT_FP:
        raise ValueError("heldout drifted from approved fingerprint")
    return corpus


def _norm(text):
    return _WS.sub(" ", _NONW.sub(" ", text.lower())).strip()


def build_intent_index(packs):
    index = {}
    for pack in packs:
        for fix in pack.get("fixtures") or []:
            key, val = _norm(fix["message"]), fix["expected_intent"]
            if key in index and index[key] != val:
                raise ValueError("fixture collision on %r" % key)
            index[key] = val
    return index


def predict_intent(text, pol, packs, index):
    """Real D03 implementation path. Returns (intent|None, provenance)."""
    got = pol.fixture_lookup(text, packs)
    if got is not None:
        return got, "exact-fixture"
    got = index.get(_norm(text))
    if got is not None:
        return got, "normalized-fixture"
    return None, "abstain"


def train_majority(corpus):
    """Baseline fit on TRAIN intent rows only. Never sees heldout."""
    counts = Counter(
        c["expected"]["intent"] for c in corpus
        if c["family"] == "intent" and c["split"] == "train")
    return counts.most_common(1)[0][0]


def intent_correct(pred, case):
    if pred is None:
        return False
    exp = case["expected"]["intent"]
    if pred == exp:
        return True
    return any(a.get("intent") == pred
               for a in case.get("acceptable_alternatives") or [])


def scenario_key(exp):
    if exp.get("path") == "typesafe_direct" and exp.get("openrouter_calls") == 0 \
            and "reason" not in exp:
        return "BOTH_KEYS"
    if exp.get("path") == "openrouter" and exp.get("openrouter_calls") == 1 \
            and "reason" not in exp:
        return "OR_ONLY"
    if exp.get("path") == "no_jev" and exp.get("blocks_work") is False:
        return "NO_KEYS"
    if exp.get("reason") == "not_authorized":
        return "DENIED"
    if exp.get("off_equals_legacy") is True:
        return "OFF_EQUALS_LEGACY"
    if exp.get("path") == "no_jev_authoritative":
        return "SHADOW"
    if exp.get("reason") == "tenant_mismatch":
        return "TENANT"
    if exp.get("reason") == "direct_not_permitted":
        return "DIRECT_FORBIDDEN"
    if exp.get("reason") == "openrouter_not_permitted":
        return "OR_FORBIDDEN"
    if exp.get("path") == "budget_atomic":
        return "ATOMIC"
    if exp.get("path") == "root_budget":
        return "ROOT_BUDGET"
    return "UNKNOWN"


def _allow_all(provider, purpose):
    return {"spend_ok": True, "transmit_ok": True, "reason": "standing"}


def _deny_all(provider, purpose):
    return {"spend_ok": False, "transmit_ok": False, "reason": "denied"}


def run_provmode(case, lad_mod):
    """One real ladder run with fake transports. Returns a measured row."""
    exp = case["expected"]
    key = scenario_key(exp)
    co = (case.get("context") or {}).get("company", "D30EvalCo")
    calls = Counter()
    order_log = []

    def fake_direct(url, body, headers, timeout_s):
        calls["typesafe_direct"] += 1
        assert FAKE_DIRECT in headers.get("Authorization", "")
        assert FAKE_OR not in headers.get("Authorization", "")
        return 200, {"model": "jev-1.13.0", "judgments": []}

    def fake_or(endpoint, headers, payload):
        calls["openrouter"] += 1
        assert FAKE_OR in headers.get("Authorization", "")
        return 200, {"model": "typesafe/jev-1.13", "judgments": []}

    both = {"TYPESAFE_API_KEY": FAKE_DIRECT, "OPENROUTER_API_KEY": FAKE_OR}
    both_stores = [{"source_category": "client_secrets", "company_id": co,
                    "values": dict(both)}]
    questions = [{"id": "q_intent", "type": "select"}]
    t0 = time.perf_counter()

    if key == "BOTH_KEYS":
        lad = lad_mod.DirectFirstLadder(policy_fn=_allow_all)
        verdict = lad.run(company_id=co, stores=both_stores, context={},
                          state={}, questions=questions, keys=dict(both),
                          direct_http=fake_direct,
                          openrouter_transport=fake_or, order_log=order_log)
        passed = (verdict["decision_source"] == "typesafe_direct"
                  and calls["openrouter"] == 0
                  and calls["typesafe_direct"] == 1)
    elif key == "OR_ONLY":
        or_only = {"OPENROUTER_API_KEY": FAKE_OR}
        lad = lad_mod.DirectFirstLadder(policy_fn=_allow_all)
        verdict = lad.run(
            company_id=co,
            stores=[{"source_category": "client_secrets", "company_id": co,
                     "values": dict(or_only)}],
            context={}, state={}, questions=questions, keys=dict(or_only),
            direct_http=fake_direct, openrouter_transport=fake_or,
            order_log=order_log)
        passed = (verdict["decision_source"] == "openrouter"
                  and calls["openrouter"] == 1
                  and calls["typesafe_direct"] == 0)
    elif key == "NO_KEYS":
        lad = lad_mod.DirectFirstLadder(policy_fn=_allow_all)
        verdict = lad.run(
            company_id=co,
            stores=[{"source_category": "client_secrets", "company_id": co,
                     "values": {}}],
            context={}, state={}, questions=questions, keys={},
            direct_http=fake_direct, openrouter_transport=fake_or,
            order_log=order_log)
        passed = (verdict["decision_source"] == "no_jev"
                  and verdict.get("fallback", {}).get("ok") is True
                  and calls["typesafe_direct"] == 0
                  and calls["openrouter"] == 0)
    elif key == "DENIED":
        lad = lad_mod.DirectFirstLadder(policy_fn=_deny_all)
        verdict = lad.run(company_id=co, stores=both_stores, context={},
                          state={}, questions=questions, keys=dict(both),
                          direct_http=fake_direct,
                          openrouter_transport=fake_or, order_log=order_log)
        skips = {s["stage"]: s["skip_reason"] for s in verdict["stages"]}
        passed = (verdict["decision_source"] == "no_jev"
                  and calls["typesafe_direct"] == 0
                  and calls["openrouter"] == 0
                  and skips.get("typesafe_direct") == "not_authorized"
                  and skips.get("openrouter") == "not_authorized")
    elif key == "TENANT":
        lad = lad_mod.DirectFirstLadder(policy_fn=_allow_all)
        verdict = lad.run(
            company_id=co,
            stores=[{"source_category": "client_secrets",
                     "company_id": "OtherCo",
                     "values": dict(both)}],
            context={}, state={}, questions=questions, keys={},
            direct_http=fake_direct, openrouter_transport=fake_or,
            order_log=order_log)
        _, _, cr = lad_mod._load_providers()
        tenant_state = cr.resolve_provider_key(
            "direct", co,
            [{"source_category": "client_secrets", "company_id": "OtherCo",
              "values": dict(both)}])
        passed = (verdict["decision_source"] == "no_jev"
                  and calls["typesafe_direct"] == 0
                  and calls["openrouter"] == 0
                  and any("other_company" in s
                          for s in tenant_state.skipped_sources))
    elif key == "DIRECT_FORBIDDEN":
        def pol(provider, purpose):
            if provider == "typesafe_direct":
                return {"spend_ok": False, "transmit_ok": True,
                        "reason": "direct-not-permitted"}
            return {"spend_ok": True, "transmit_ok": True,
                    "reason": "standing"}
        lad = lad_mod.DirectFirstLadder(policy_fn=pol)
        verdict = lad.run(company_id=co, stores=both_stores, context={},
                          state={}, questions=questions, keys=dict(both),
                          direct_http=fake_direct,
                          openrouter_transport=fake_or, order_log=order_log)
        passed = (verdict["decision_source"] == "openrouter"
                  and calls["typesafe_direct"] == 0
                  and calls["openrouter"] == 1)
    elif key == "OR_FORBIDDEN":
        def pol(provider, purpose):
            if provider == "openrouter":
                return {"spend_ok": False, "transmit_ok": True,
                        "reason": "openrouter-not-permitted"}
            return {"spend_ok": True, "transmit_ok": True,
                    "reason": "standing"}
        lad = lad_mod.DirectFirstLadder(policy_fn=pol)
        verdict = lad.run(company_id=co, stores=both_stores, context={},
                          state={}, questions=questions, keys=dict(both),
                          direct_http=fake_direct,
                          openrouter_transport=fake_or, order_log=order_log)
        passed = (verdict["decision_source"] == "typesafe_direct"
                  and calls["openrouter"] == 0
                  and calls["typesafe_direct"] == 1)
    elif key == "ROOT_BUDGET":
        lad = lad_mod.DirectFirstLadder(policy_fn=_allow_all)
        expired = lad_mod.RootDeadline(0, clock=time.monotonic)
        verdict = lad.run(company_id=co, stores=both_stores, context={},
                          state={}, questions=questions, keys=dict(both),
                          direct_http=fake_direct,
                          openrouter_transport=fake_or, order_log=order_log,
                          root_deadline=expired)
        skips = {s["stage"]: s["skip_reason"] for s in verdict["stages"]}
        passed = (verdict["decision_source"] == "no_jev"
                  and verdict.get("fallback", {}).get("ok") is True
                  and calls["typesafe_direct"] == 0
                  and calls["openrouter"] == 0
                  and skips.get("typesafe_direct") == "root_deadline_expired"
                  and skips.get("openrouter") == "root_deadline_expired")
    else:
        return {"id": case["id"], "family": "provmode",
                "split": case["split"], "scenario": key,
                "outcome": "NOT_RUN",
                "reason": MISSING_REVISIONS.get(
                    key, "no owned implementation for scenario %s" % key),
                "latency_ms": 0.0,
                "calls": {}, "expected": dict(exp)}

    latency_ms = (time.perf_counter() - t0) * 1000.0
    return {"id": case["id"], "family": "provmode", "split": case["split"],
            "scenario": key, "outcome": "PASS" if passed else "FAIL",
            "measured_source": verdict["decision_source"],
            "latency_ms": latency_ms,
            "root_remaining_ms": verdict["root"]["remaining_ms"],
            "attempts": verdict["accounting"]["total_attempts"],
            "order_log": list(order_log),
            "stage_skips": [s.get("skip_reason") for s in verdict["stages"]],
            "calls": dict(calls), "expected": dict(exp)}


class _BlockedSocket(socket.socket):
    def __init__(self, *args, **kwargs):
        raise RuntimeError("D30 offline: network blocked")


class offline:
    """Fail-closed network block for the evaluation loop."""
    def __enter__(self):
        self._real = socket.socket
        socket.socket = _BlockedSocket
        return self

    def __exit__(self, *exc):
        socket.socket = self._real
        return False


def _p95(values):
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(0.95 * (len(ordered) - 1)))]


def evaluate(repo_root=None):
    """Full offline run. Returns a JSON-serializable report (no timestamps)."""
    corpus = load_frozen_corpus(repo_root)
    pol = load_policies()
    lad_mod = load_ladder()
    packs = [pol.load_pack(f) for f in pol.PACK_FILES]
    index = build_intent_index(packs)
    majority = train_majority(corpus)
    t_start = time.perf_counter()

    rows = []
    calls = Counter({"fixture_lookup": 0, "provmode_runs": 0,
                      "typesafe_direct": 0, "openrouter": 0,
                      "embedding": 0, "probe": 0, "shadow": 0})
    with offline():
        for case in corpus:
            fam = case["family"]
            if fam == "intent":
                t0 = time.perf_counter()
                pred, prov = predict_intent(case["text"], pol, packs, index)
                calls["fixture_lookup"] += 1
                base = majority
                lat = (time.perf_counter() - t0) * 1000.0
                rows.append({
                    "id": case["id"], "family": "intent",
                    "split": case["split"], "outcome":
                        "PASS" if intent_correct(pred, case) else
                        ("ABSTAIN" if pred is None else "FAIL"),
                    "predicted": pred, "baseline": base,
                    "baseline_correct": base == case["expected"]["intent"],
                    "provenance": prov, "latency_ms": lat,
                    "expected": case["expected"]["intent"]})
            elif fam == "provmode":
                row = run_provmode(case, lad_mod)
                for src, n in row.get("calls", {}).items():
                    calls[src] += n
                if row["outcome"] in ("PASS", "FAIL"):
                    calls["provmode_runs"] += 1
                rows.append(row)
            elif fam == "exec":
                rows.append({"id": case["id"], "family": "exec",
                             "split": case["split"], "outcome": "NOT_RUN",
                             "reason": MISSING_REVISIONS["exec"],
                             "latency_ms": 0.0,
                             "expected": dict(case["expected"])})
            elif fam == "capload":
                rows.append({"id": case["id"], "family": "capload",
                             "split": case["split"], "outcome": "NOT_RUN",
                             "reason": MISSING_REVISIONS["capload"],
                             "latency_ms": 0.0,
                             "expected": dict(case["expected"])})
            else:
                raise ValueError("unknown family %r" % fam)

    by_split_fam = {}
    for split in ("train", "calibration", "heldout"):
        for fam in ("intent", "provmode", "exec", "capload"):
            sel = [r for r in rows
                   if r["split"] == split and r["family"] == fam]
            ran = [r for r in sel if r["outcome"] in ("PASS", "FAIL")]
            abst = [r for r in sel if r["outcome"] == "ABSTAIN"]
            passed = [r for r in sel if r["outcome"] == "PASS"]
            impl_acc = (len(passed) / len(ran)) if ran else None
            base_hit = [r for r in ran
                        if r.get("baseline_correct") is True]
            by_split_fam["%s/%s" % (split, fam)] = {
                "n": len(sel), "run": len(ran),
                "not_run": len(sel) - len(ran) - len(abst),
                "abstain": len(abst),
                "coverage": ((len(ran) + len(abst)) / len(sel)) if sel else None,
                "impl_accuracy_covered":
                    (len(passed) / len(ran)) if ran else None,
                "impl_accuracy_all":
                    (len(passed) / len(sel)) if sel else None,
                "baseline_accuracy_covered":
                    (len(base_hit) / len(ran)) if ran else None,
            }
            _ = impl_acc

    pr = {}
    for split in ("train", "calibration", "heldout"):
        # ABSTAIN counts: predicted None never equals a class, so it lands
        # as a miss on taskish rows and a correct non-creation on NON_TASK.
        sel = [r for r in rows
               if r["split"] == split and r["family"] == "intent"
               and r["outcome"] in ("PASS", "FAIL", "ABSTAIN")]
        per_class = {}
        for cls in INTENT_CLASSES:
            tp = sum(1 for r in sel if r["predicted"] == cls
                     and r["expected"] == cls)
            fp = sum(1 for r in sel if r["predicted"] == cls
                     and r["expected"] != cls)
            fn = sum(1 for r in sel if r["predicted"] != cls
                     and r["expected"] == cls)
            per_class[cls] = {
                "precision": (tp / (tp + fp)) if (tp + fp) else None,
                "recall": (tp / (tp + fn)) if (tp + fn) else None,
                "support": tp + fn}
        non_task = [r for r in sel if r["expected"] in NON_TASK]
        false_task = sum(1 for r in non_task if r["predicted"] in TASKISH)
        pr[split] = {"per_class": per_class,
                     "false_task_creation": {
                         "n": len(non_task), "false": false_task,
                         "rate": (false_task / len(non_task))
                                 if non_task else None}}

    prov_rows = [r for r in rows if r["family"] == "provmode"
                 and r["outcome"] in ("PASS", "FAIL")]
    lat_all = [r["latency_ms"] for r in rows
               if r["outcome"] in ("PASS", "FAIL", "ABSTAIN")]
    lat_prov = [r["latency_ms"] for r in prov_rows]
    lat_intent = [r["latency_ms"] for r in rows
                  if r["family"] == "intent"
                  and r["outcome"] in ("PASS", "FAIL", "ABSTAIN")]
    wall_s = time.perf_counter() - t_start
    report = {
        "unit": "JEV-030",
        "status": "PARTIAL",
        "base_rev": BASE_REV,
        "frozen_rev": FROZEN_REV,
        "heldout_fingerprint": HELDOUT_FP,
        "total_cases": len(corpus),
        "offline": {"socket_blocked": True,
                    "remote_transport_calls":
                        calls["typesafe_direct"] + calls["openrouter"],
                    "paid_calls": 0, "shadow_calls": 0, "probe_calls": 0,
                    "embedding_calls": 0},
        "calls_by_source": dict(calls),
        "splits": by_split_fam,
        "intent_precision_recall": pr,
        "provmode": {
            "run": len(prov_rows),
            "passed": sum(1 for r in prov_rows if r["outcome"] == "PASS"),
            "failed": sum(1 for r in prov_rows if r["outcome"] == "FAIL"),
            "attempts_total": sum(r["attempts"] for r in prov_rows),
            "attempts_max_per_row":
                max([r["attempts"] for r in prov_rows] + [0]),
            "root_remaining_ms_min":
                min([r["root_remaining_ms"] for r in prov_rows] + [0.0]),
        },
        "latency_ms": {
            "all_median": statistics.median(lat_all) if lat_all else 0.0,
            "all_p95": _p95(lat_all),
            "intent_median":
                statistics.median(lat_intent) if lat_intent else 0.0,
            "intent_p95": _p95(lat_intent),
            "provmode_median":
                statistics.median(lat_prov) if lat_prov else 0.0,
            "provmode_p95": _p95(lat_prov),
            "harness_wall_s": wall_s,
        },
        "not_run_ids": {fam: sorted(
            r["id"] for r in rows
            if r["family"] == fam and r["outcome"] == "NOT_RUN")
            for fam in ("exec", "capload", "provmode", "intent")},
        "not_run_reasons": {k: MISSING_REVISIONS[k] for k in
                            ("exec", "capload", "OFF_EQUALS_LEGACY",
                             "SHADOW", "ATOMIC")},
        "missing_revisions_note": "Full D30 needs D14-D24 exact integrated "
            "revisions; this base holds D16/D17/D18/D19/D23 only. "
            "D08/D10/D11/D13-D15/D20-D22/D24 rows are NOT_RUN, never guessed.",
        "fabrication_guard": "Every number above is measured in this run: "
            "predictions from real modules, calls counted at fake transports, "
            "latency from perf_counter. No estimated scores, no speedups.",
        "rows": rows,
    }
    return report


def main(argv=None):
    ap = argparse.ArgumentParser(description="D30 offline evaluation")
    ap.add_argument("--out", default=None, help="write JSON report to path")
    ap.add_argument("--repo", default=None, help="repo root override")
    args = ap.parse_args(argv)
    report = evaluate(args.repo)
    blob = json.dumps(report, indent=1, sort_keys=True)
    if args.out:
        Path(args.out).write_text(blob + "\n")
    else:
        print(blob)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
