#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""page_swarm.py - build the independent pages of a funnel side by side, safely.

dispatch_launch.py hands this module one lane per page request. Rules, all proven by
test_page_swarm.py with fake pages and a fake limiter (no paid call anywhere):

  * Every lane runs side by side, `workers` at a time, the landing lane (sales page and opt-in page)
    with the rest. The default worker count is the runner profile's max_workers from Skill 71 (Mac 6,
    Hostinger 8, Contabo 4); workers=1 is the sequential fallback and gives byte-identical results.
    No lane waits for another: the look every page follows (design style, brand file, owner,
    provider) is in the shared image inputs file all lanes read from the start. The landing run's
    visual-bible.json is written when the swarm ends, as the record of what it drew; no later page
    prompt reads it, so holding the other pages back for it bought nothing.
  * Every paid image start takes a token from Skill 71's shared KIE limiter (20 starts per 10
    seconds per account, lockfile-persisted); a lane takes one token per image it plans to start,
    again for its single retry. The free stub provider takes none.
  * A per-launch spend ledger enforces image_cap: lanes are reserved in page order and a lane that
    would pass the cap is skipped, never started (status skipped_cap), so no new paid image work
    begins past the cap.
  * One page failing never stops the others. Results come back in the order the lanes were given,
    whatever order they finished in.

Honest ceiling: metering is per lane (a lane reserves its estimated image starts before it begins),
because the image starts themselves happen inside Skill 71's stage executor, which has no limiter of
its own. The same lock file is exported to the lanes as KIE_ACCOUNT_LOCK so anything that honours it
shares the one account window.

Stdlib only. Never reads a secret.
"""
from __future__ import annotations

import json
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import page_set as ps  # noqa: E402

SKILL71_ROOT = HERE.parents[1] / "71-blackceo-signature-page"
BIBLE_NAME = "visual-bible.json"
INPUTS_NAME = "image-inputs.json"
LEDGER_NAME = "spend-ledger.json"


class SwarmError(ValueError):
    pass


class LaneTransient(Exception):
    """A runner raises this to say 'try this lane once more' (a timeout or a transport blip)."""


# ---------------------------------------------------------------------------------------------
# Skill 71's runner profile and KIE limiter, imported rather than copied
# ---------------------------------------------------------------------------------------------
def _swarm_runner(skill71_root: Path = SKILL71_ROOT):
    scripts = str(Path(skill71_root) / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    import swarm_runner  # noqa: E402
    return swarm_runner


def default_workers(env=None, profile_name: Optional[str] = None,
                    skill71_root: Path = SKILL71_ROOT) -> int:
    """max_workers of the resolved runner profile (Mac 6, Hostinger 8, Contabo 4)."""
    sr = _swarm_runner(skill71_root)
    profile, _evidence = sr.resolve_profile(env=env, cli_name=profile_name)
    return max(1, int(profile["max_workers"]))


def kie_limiter(skill71_root: Path = SKILL71_ROOT, env=None, path=None, clock=None):
    """Skill 71's TokenBucket on the shared per-account lock file."""
    sr = _swarm_runner(skill71_root)
    env = os.environ if env is None else env
    profile, _ = sr.resolve_profile(env=env)
    return sr.TokenBucket(sr.limiter_path_for(profile, env, path), clock)


# ---------------------------------------------------------------------------------------------
# The spend ledger
# ---------------------------------------------------------------------------------------------
class SpendLedger:
    """Counts images per lane against image_cap. enforce=False (the free stub) records only."""

    def __init__(self, cap: int, *, enforce: bool = True, path: Optional[Path] = None,
                 provider: str = "stub"):
        self.cap, self.enforce, self.path, self.provider = int(cap), enforce, path, provider
        self.entries: List[Dict[str, Any]] = []
        self._lock = threading.Lock()

    @property
    def reserved(self) -> int:
        return sum(e["reserved"] for e in self.entries if e["status"] != "skipped_cap")

    def reserve(self, lane: str, estimate: int) -> bool:
        """True and the images are held for this lane; False when it would pass the cap."""
        with self._lock:
            if self.enforce and self.reserved + estimate > self.cap:
                self.entries.append({"lane": lane, "reserved": estimate, "status": "skipped_cap"})
                self._save()
                return False
            self.entries.append({"lane": lane, "reserved": estimate, "status": "reserved"})
            self._save()
            return True

    def settle(self, lane: str, status: str) -> None:
        with self._lock:
            for e in self.entries:
                if e["lane"] == lane and e["status"] == "reserved":
                    e["status"] = status
            self._save()

    def to_dict(self) -> Dict[str, Any]:
        return {"schema": "signature-launch-spend-ledger/v1", "provider": self.provider,
                "image_cap": self.cap, "enforced": self.enforce, "reserved_images": self.reserved,
                "entries": list(self.entries)}

    def _save(self) -> None:
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.to_dict(), indent=2) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------------------------
# The lane runner
# ---------------------------------------------------------------------------------------------
def run_swarm(lanes: List[Dict[str, Any]], runner: Callable[[Dict[str, Any]], Any], *,
              workers: int = 1, limiter=None, ledger: Optional[SpendLedger] = None,
              ) -> List[Dict[str, Any]]:
    """Run lanes; returns one outcome per lane IN THE ORDER GIVEN.

    A lane is {"lane": key, "image_estimate": n, ...}. Outcome: {"lane", "status": ok | failed |
    skipped_cap, "attempts", "result" | "error"}. `limiter` (anything with consume()) is charged
    image_estimate tokens per attempt; pass None for a free run."""
    index = {l["lane"]: i for i, l in enumerate(lanes)}
    if len(index) != len(lanes):
        raise SwarmError("two lanes share one key; each page has its own lane")
    outcomes: Dict[str, Dict[str, Any]] = {}

    def attempt(lane: Dict[str, Any]) -> Dict[str, Any]:
        tries, cost = 0, max(0, int(lane.get("image_estimate", 0)))
        while True:
            tries += 1
            if limiter is not None:
                for _ in range(cost):
                    limiter.consume()
            try:
                return {"lane": lane["lane"], "status": "ok", "attempts": tries,
                        "result": runner(lane)}
            except LaneTransient as exc:
                if tries < 2:
                    continue
                return {"lane": lane["lane"], "status": "failed", "attempts": tries,
                        "error": f"still failing after one retry: {exc}"}
            except Exception as exc:  # one page failing never stops the others
                return {"lane": lane["lane"], "status": "failed", "attempts": tries,
                        "error": str(exc)}

    def admit(lane: Dict[str, Any]) -> bool:
        if ledger is not None and not ledger.reserve(lane["lane"], int(lane.get("image_estimate", 0))):
            outcomes[lane["lane"]] = {
                "lane": lane["lane"], "status": "skipped_cap", "attempts": 0,
                "error": f"image cap {ledger.cap} reached; this page was not started "
                         f"(raise the cap or build it separately)"}
            return False
        return True

    def finish(outcome: Dict[str, Any]) -> None:
        outcomes[outcome["lane"]] = outcome
        if ledger is not None:
            ledger.settle(outcome["lane"], outcome["status"])

    admitted = [l for l in lanes if admit(l)]  # reserved in page order, so the cap is deterministic
    if admitted:
        with ThreadPoolExecutor(max_workers=max(1, min(int(workers), len(admitted)))) as pool:
            for outcome in pool.map(attempt, admitted):
                finish(outcome)
    return sorted(outcomes.values(), key=lambda o: index[o["lane"]])


# ---------------------------------------------------------------------------------------------
# Visual bible and the glue dispatch_launch.py calls
# ---------------------------------------------------------------------------------------------
def write_visual_bible(out_dir: Path, launch_id: str, inputs: Optional[Dict[str, Any]],
                       landing: Optional[Dict[str, Any]]) -> Path:
    """visual-bible.json: the record of the look the landing run drew (written when the swarm ends)."""
    inputs = inputs or {}
    result = (landing or {}).get("result") or {}
    doc = {"schema": "signature-launch-visual-bible/v1", "launch_id": launch_id,
           "design_style": inputs.get("design_style"), "brand_file": inputs.get("brand_file"),
           "brand_owner": inputs.get("brand_owner"), "image_provider": inputs.get("image_provider", "stub"),
           "landing_status": (landing or {}).get("status", "not_run"),
           "landing_files": [{"path": a.get("path"), "sha256": a.get("sha256")}
                             for a in (result.get("artifacts") or []) if isinstance(a, dict)]}
    path = Path(out_dir) / BIBLE_NAME
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    return path


def execute(requests: List[Dict[str, Any]], executor: Callable[..., Dict[str, Any]], *,
            page_set: Dict[str, Any], out_dir: Optional[Path], launch_id: str,
            workers: int = 1, image_inputs: Optional[Dict[str, Any]] = None,
            limiter=None) -> Dict[str, Any]:
    """Run every request of a launch (plus the page set's extra pages) as lanes.

    `executor(request)` runs a route lane; `executor(request, lane_key)` runs an extra page that
    rides on its parent's request (today: downsell_2). Returns
    {"outcomes": [...], "swarm": {report}}; the caller decides what a failed lane means."""
    plan = ps.lane_plan(page_set)
    estimates = {l["lane"]: l["image_estimate"] for l in plan["parallel"]}
    by_role = {r["page_role"]: r for r in requests}
    lanes = [{"lane": r["page_role"], "request": r, "extra": False,
              "image_estimate": estimates.get(r["page_role"], 0)} for r in requests]
    for l in plan["parallel"]:
        if l["extra"]:
            if l["request_role"] not in by_role:
                raise SwarmError(f"extra page {l['lane']} rides on {l['request_role']}, which this launch lacks")
            lanes.append({"lane": l["lane"], "request": by_role[l["request_role"]], "extra": True,
                          "image_estimate": l["image_estimate"]})
    paid = bool(image_inputs) and image_inputs.get("image_provider") == "kie"
    # the free stub makes no paid start: no limiter tokens, no cap (the ledger only records)
    out_dir = Path(out_dir) if out_dir else None
    ledger = None
    if image_inputs is not None:
        ledger = SpendLedger(image_inputs["image_cap"], enforce=paid, provider=image_inputs["image_provider"],
                             path=out_dir / LEDGER_NAME if out_dir else None)
    if out_dir and image_inputs is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / INPUTS_NAME).write_text(json.dumps({k: v for k, v in image_inputs.items() if k != "allow_paid"},
                                          indent=2) + "\n", encoding="utf-8")

    def run(lane):
        return executor(lane["request"], lane["lane"]) if lane["extra"] else executor(lane["request"])

    outcomes = run_swarm(lanes, run, workers=workers, limiter=limiter if paid else None, ledger=ledger)
    if out_dir:
        write_visual_bible(out_dir, launch_id, image_inputs,
                           next((o for o in outcomes if o["lane"] == "landing"), None))
    report = {"workers": int(workers),
              "lanes": [o["lane"] for o in outcomes],
              "statuses": {o["lane"]: o["status"] for o in outcomes},
              "attempts": {o["lane"]: o["attempts"] for o in outcomes},
              "spend": ledger.to_dict() if ledger else None,
              "visual_bible": str(out_dir / BIBLE_NAME) if out_dir and (out_dir / BIBLE_NAME).is_file() else None}
    return {"outcomes": outcomes, "swarm": report}


if __name__ == "__main__":
    raise SystemExit("page_swarm.py is a library; dispatch_launch.py --parallel uses it")
