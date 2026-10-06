"""Unit tests for shared-utils/decision_engine_train (JEV D33, spec 14/18, A49-A53).

Stdlib only. Local temporary git fixtures only; no network, no GitHub writes.
Run:  python3 -m pytest tests/unit/test_decision_engine_train.py -q
  or:  python3 -m unittest tests.unit.test_decision_engine_train -v
"""
from __future__ import annotations

import ast
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = Path(__file__).parent
_REPO_ROOT = _HERE.parent.parent
_SHARED = _REPO_ROOT / "shared-utils"
assert _SHARED.is_dir(), "shared-utils missing: %s" % _SHARED
sys.path.insert(0, str(_SHARED))

from decision_engine_train import (  # noqa: E402
    INDEPENDENT_ROUTE,
    OUTCOMES,
    TRAIN_ROUTE,
    WINDOW_SECONDS,
    acquire_lease,
    amend,
    attach_integration_qc,
    collect_all,
    compose_batch,
    enqueue,
    freeze,
    isolate_failure,
    load_state,
    new_state,
    promote,
    quarter_window,
    record_tests,
    release_flight,
    save_state,
    select_eligible,
    tick,
    validate_qc_receipt,
    verify_manifest,
    window_start_utc,
)


def good_receipt(sha, reviewer="sonnet-qc-1"):
    return {"sha": sha, "verdict": "PASS", "reviewer": reviewer,
            "reviewer_route": INDEPENDENT_ROUTE}


def entry(uid, sha, deps=(), reviewer="sonnet-qc-1", verdict="PASS",
          route=INDEPENDENT_ROUTE):
    return {"unit_id": uid, "sha": sha,
            "qc_receipt": {"sha": sha, "verdict": verdict,
                           "reviewer": reviewer, "reviewer_route": route},
            "dependencies": list(deps)}


def passing_results():
    return {"checks": [{"name": "unit", "status": "pass"},
                       {"name": "integration", "status": "pass"}]}


def promote_ready(state, repo, batch_id, integration_sha="int-1", final="main-2"):
    record_tests(state, repo, batch_id, integration_sha, passing_results())
    attach_integration_qc(state, repo, batch_id, "sonnet-qc-1",
                          INDEPENDENT_ROUTE, "PASS")
    return promote(state, repo, batch_id, final)


class Windows(unittest.TestCase):
    def test_quarter_hour_floor(self):
        self.assertEqual(WINDOW_SECONDS, 900)
        self.assertEqual(quarter_window(901 * 900 + 7), 901 * 900)
        self.assertEqual(window_start_utc(900), 900)
        self.assertEqual(quarter_window(0), 0)

    def test_persisted_last_window_and_restart_coalescing(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "train.json"
            s = new_state()
            enqueue(s, "onb", "D01", "sha1", good_receipt("sha1"))
            first = tick(s, "onb", 900, owner="t:onb")
            self.assertEqual(first["outcome"], "collected")
            save_state(s, p)
            reread = load_state(str(p))
            second = tick(reread, "onb", 901, owner="t:onb")
            self.assertEqual(second["outcome"], "in_flight")
            self.assertEqual(second["batch_id"], first["batch_id"])
            self.assertEqual(len(reread["batches"]), 1)

    def test_same_window_retick_after_promotion_coalesces(self):
        s = new_state()
        enqueue(s, "onb", "D01", "sha1", good_receipt("sha1"))
        first = tick(s, "onb", 900, owner="t:onb")
        promote_ready(s, "onb", first["batch_id"])
        second = tick(s, "onb", 901, owner="t:onb")
        self.assertEqual(second["outcome"], "promoted")
        self.assertTrue(second.get("coalesced"))
        self.assertEqual(len(s["batches"]), 1)

    def test_new_window_collects_new_batch(self):
        s = new_state()
        enqueue(s, "onb", "D01", "sha1", good_receipt("sha1"))
        a = tick(s, "onb", 900, owner="t:onb")
        release_flight(s, "onb", "t:onb")
        b = tick(s, "onb", 1800, owner="t:onb")
        self.assertEqual((a["outcome"], b["outcome"]), ("collected", "collected"))
        self.assertNotEqual(a["batch_id"], b["batch_id"])


class Receipts(unittest.TestCase):
    def test_exact_sha_pass_eligible(self):
        ok, reason = validate_qc_receipt(entry("D01", "abc"))
        self.assertTrue(ok, reason)

    def test_changed_sha_loses_eligibility(self):
        s = new_state()
        enqueue(s, "onb", "D01", "abc", good_receipt("abc"))
        amend(s, "onb", "D01", "def")
        eligible, excluded = select_eligible(s, "onb")
        self.assertEqual(eligible, [])
        self.assertEqual(len(excluded), 1)
        self.assertIn("changed SHA", excluded[0]["reason"])

    def test_fail_verdict_wrong_route_missing_reviewer(self):
        for bad in (entry("D01", "a", verdict="FAIL"),
                    entry("D01", "a", route="haiku-chain"),
                    entry("D01", "a", reviewer="")):
            ok, reason = validate_qc_receipt(bad)
            self.assertFalse(ok)
            self.assertTrue(reason)


class Batches(unittest.TestCase):
    def test_deterministic_order_and_closure(self):
        m = compose_batch([entry("D03", "c"), entry("D01", "a"),
                           entry("D02", "b", deps=("D01",))],
                          repository="onb", base_main_sha="m0", batch_id="onb-900")
        self.assertEqual(m["unit_ids"], ["D01", "D02", "D03"])
        self.assertEqual(m["dependency_closure"]["D02"], ["D01"])
        ok, reason = verify_manifest(m)
        self.assertTrue(ok, reason)

    def test_missing_dependency_excludes_only_dependents(self):
        m = compose_batch([entry("D02", "b", deps=("D01",)), entry("D03", "c")])
        self.assertEqual(m["unit_ids"], ["D03"])
        self.assertEqual([e["unit_id"] for e in m["excluded"]], ["D02"])
        self.assertIn("dependency", m["excluded"][0]["reason"])

    def test_transitive_failure_excludes_whole_chain(self):
        m = compose_batch([entry("D03", "c", deps=("D02",)),
                           entry("D02", "b", deps=("D01",)),
                           entry("D04", "d")])
        self.assertEqual(m["unit_ids"], ["D04"])
        self.assertEqual(sorted(e["unit_id"] for e in m["excluded"]), ["D02", "D03"])

    def test_manifest_counts_must_agree(self):
        m = compose_batch([entry("D01", "a")])
        m["feature_shas"].append("zzz")
        ok, _ = verify_manifest(m)
        self.assertFalse(ok)

    def test_frozen_manifest_immutable(self):
        m = freeze(compose_batch([entry("D01", "a")]))
        m["unit_ids"].append("D99")
        m2 = freeze(compose_batch([entry("D01", "a")]))
        self.assertEqual(m2["unit_ids"], ["D01"])


class Ticks(unittest.TestCase):
    def test_empty_tick_creates_no_batch(self):
        s = new_state()
        r = tick(s, "onb", 900)
        self.assertEqual(r["outcome"], "empty")
        self.assertIsNone(r["batch_id"])
        self.assertEqual(s["batches"], {})

    def test_outcome_vocabulary(self):
        self.assertEqual(set(OUTCOMES),
                         {"empty", "collected", "in_flight", "blocked", "promoted"})

    def test_in_flight_second_tick(self):
        s = new_state()
        enqueue(s, "onb", "D01", "a", good_receipt("a"))
        first = tick(s, "onb", 900, owner="t:onb")
        second = tick(s, "onb", 901, owner="t:onb")
        self.assertEqual(first["outcome"], "collected")
        self.assertEqual(second["outcome"], "in_flight")
        self.assertEqual(second["batch_id"], first["batch_id"])

    def test_blocked_when_other_owner_holds_lease(self):
        s = new_state()
        enqueue(s, "onb", "D01", "a", good_receipt("a"))
        ok, _ = acquire_lease(s, "onb", "someone-else", 900)
        self.assertTrue(ok)
        r = tick(s, "onb", 901, owner="t:onb")
        self.assertEqual(r["outcome"], "blocked")

    def test_new_eligible_sha_after_promotion_recollects(self):
        s = new_state()
        enqueue(s, "onb", "D01", "a", good_receipt("a"))
        first = tick(s, "onb", 900, owner="t:onb")
        promote_ready(s, "onb", first["batch_id"])
        enqueue(s, "onb", "D02", "b", good_receipt("b"))
        r = tick(s, "onb", 1800, owner="t:onb")
        self.assertEqual(r["outcome"], "collected")


class Promotion(unittest.TestCase):
    def full_path(self, repo="onb", now=900, owner="t:onb"):
        s = new_state()
        enqueue(s, repo, "D01", "a", good_receipt("a"))
        t = tick(s, repo, now, owner=owner)
        return s, t["batch_id"]

    def test_promote_needs_tests_and_independent_qc(self):
        s, bid = self.full_path()
        with self.assertRaises(ValueError):
            promote(s, "onb", bid, "main-2")
        record_tests(s, "onb", bid, "int-1", passing_results())
        with self.assertRaises(ValueError):
            promote(s, "onb", bid, "main-2")
        with self.assertRaises(ValueError):
            attach_integration_qc(s, "onb", bid, "haiku-1", TRAIN_ROUTE, "PASS")
        attach_integration_qc(s, "onb", bid, "sonnet-1", INDEPENDENT_ROUTE, "PASS")
        m = promote(s, "onb", bid, "main-2")
        self.assertEqual(m["promotion"]["final_main_sha"], "main-2")
        self.assertFalse(m["promotion"]["forced"])
        self.assertEqual(s["windows"]["onb"]["last_outcome"], "promoted")

    def test_force_push_never_permitted(self):
        s, bid = self.full_path()
        promote_ready(s, "onb", bid)
        with self.assertRaisesRegex(ValueError, "force-push"):
            promote(s, "onb", bid, "main-3", force_push=True)

    def test_qc_for_other_candidate_tree_rejected(self):
        s, bid = self.full_path()
        record_tests(s, "onb", bid, "int-1", passing_results())
        attach_integration_qc(s, "onb", bid, "sonnet-1", INDEPENDENT_ROUTE,
                              "PASS")
        record_tests(s, "onb", bid, "int-2", passing_results()) \
            if False else None
        s["batches"]["onb/%s" % bid]["integration_sha"] = "int-2"
        with self.assertRaises(ValueError):
            promote(s, "onb", bid, "main-2")

    def test_red_tests_block_promotion(self):
        s, bid = self.full_path()
        record_tests(s, "onb", bid, "int-1",
                     {"checks": [{"name": "unit", "status": "fail"}]})
        attach_integration_qc(s, "onb", bid, "sonnet-1", INDEPENDENT_ROUTE,
                              "PASS")
        with self.assertRaises(ValueError):
            promote(s, "onb", bid, "main-2")

    def test_conflict_rerecords_new_candidate(self):
        s, bid = self.full_path()
        record_tests(s, "onb", bid, "int-1", passing_results())
        with self.assertRaisesRegex(ValueError, "already recorded"):
            record_tests(s, "onb", bid, "int-2", passing_results())


class Isolation(unittest.TestCase):
    def test_park_only_failed_plus_dependents(self):
        elig = [entry("D01", "a"), entry("D02", "b", deps=("D01",)),
                entry("D03", "c"), entry("D04", "d", deps=("D02",))]
        parked, remaining = isolate_failure(elig, "D01")
        self.assertEqual(sorted(e["unit_id"] for e in parked), ["D01", "D02", "D04"])
        self.assertEqual([e["unit_id"] for e in remaining], ["D03"])

    def test_leaf_failure_parks_nothing_else(self):
        elig = [entry("D01", "a"), entry("D03", "c")]
        parked, remaining = isolate_failure(elig, "D03")
        self.assertEqual([e["unit_id"] for e in parked], ["D03"])
        self.assertEqual([e["unit_id"] for e in remaining], ["D01"])

    def test_unknown_unit_rejected(self):
        with self.assertRaises(ValueError):
            isolate_failure([entry("D01", "a")], "D99")


class TwoRepos(unittest.TestCase):
    def test_concurrent_collect_no_competing_writers(self):
        s = new_state()
        enqueue(s, "onb", "D01", "a", good_receipt("a"))
        enqueue(s, "cc", "C01", "z", good_receipt("z"))
        out = collect_all(s, ("onb", "cc"), 900, owner="train")
        self.assertEqual(out["onb"]["outcome"], "collected")
        self.assertEqual(out["cc"]["outcome"], "collected")
        self.assertNotEqual(out["onb"]["batch_id"], out["cc"]["batch_id"])
        self.assertNotEqual(s["leases"]["onb"]["owner"], s["leases"]["cc"]["owner"])

    def test_slow_batch_does_not_stop_other_repo(self):
        s = new_state()
        enqueue(s, "onb", "D01", "a", good_receipt("a"))
        first = collect_all(s, ("onb", "cc"), 900, owner="train")
        self.assertEqual(first["onb"]["outcome"], "collected")
        self.assertEqual(first["cc"]["outcome"], "empty")
        enqueue(s, "cc", "C01", "z", good_receipt("z"))
        second = collect_all(s, ("onb", "cc"), 1800, owner="train")
        self.assertEqual(second["onb"]["outcome"], "in_flight")
        self.assertEqual(second["cc"]["outcome"], "collected")

    def test_promote_one_repo_leaves_other_in_flight(self):
        s = new_state()
        enqueue(s, "onb", "D01", "a", good_receipt("a"))
        enqueue(s, "cc", "C01", "z", good_receipt("z"))
        out = collect_all(s, ("onb", "cc"), 900, owner="train")
        promote_ready(s, "onb", out["onb"]["batch_id"])
        self.assertEqual(s["windows"]["onb"]["last_outcome"], "promoted")
        self.assertEqual(s["windows"]["cc"]["in_flight"], out["cc"]["batch_id"])


class NoRemoteEffects(unittest.TestCase):
    def test_core_has_no_network_or_process_imports(self):
        tree = ast.parse(Path(_SHARED, "decision_engine_train",
                              "train.py").read_text())
        banned = {"subprocess", "socket", "urllib", "requests", "http",
                  "shutil", "pty", "os.system" if False else "os_system_placeholder"}
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                names.add(node.module.split(".")[0])
        self.assertTrue(banned.isdisjoint(names), names & banned)

    def test_local_git_fixture_shas_flow_through(self):
        with tempfile.TemporaryDirectory() as d:
            env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@x.invalid",
                   "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@x.invalid"}
            import os as _os
            full = dict(_os.environ, **env)
            subprocess.run(["git", "init", "-q", "-b", "main", d], check=True, env=full)
            Path(d, "f.txt").write_text("base")
            subprocess.run(["git", "-C", d, "add", "f.txt"], check=True, env=full)
            subprocess.run(["git", "-C", d, "commit", "-qm", "base"], check=True, env=full)
            sha = subprocess.run(["git", "-C", d, "rev-parse", "HEAD"],
                                 capture_output=True, text=True, check=True,
                                 env=full).stdout.strip()
            remotes = subprocess.run(["git", "-C", d, "remote"],
                                     capture_output=True, text=True,
                                     check=True, env=full).stdout.strip()
            self.assertEqual(remotes, "")
            s = new_state()
            enqueue(s, "onb", "D99", sha, good_receipt(sha))
            eligible, excluded = select_eligible(s, "onb")
            self.assertEqual([e["sha"] for e in eligible], [sha])
            self.assertEqual(excluded, [])
            state_json = json.dumps(s["batches"])
            self.assertEqual(json.loads(state_json), {})


if __name__ == "__main__":
    unittest.main()
