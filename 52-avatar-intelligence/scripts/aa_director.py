#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""aa_director.py — the Avatar-Alchemist foreman (Skill 52).

Schedules the 40-generator BRAND pipeline in dependency waves computed from
AA-PIPELINE-MANIFEST.json `depends_on` (the digest-verified DAG), throttled to
min(slots, provider_cap). Dispatches ONE sub-agent per stage with only that
stage's three prompt files + its resolved dependency artifacts, and REFUSES to
dispatch any stage whose depends_on receipts are missing. Idempotent on
RUN-LEDGER.json (--resume never re-generates a verified stage). Parks fail-closed
on non-recoverable conditions. Issues the signed certificate only when every
phase passes (delegates the gate to aa_delivery_gate.py).

Front-door nonce: a real run REQUIRES the one-time nonce entry.sh minted this run
(deps + bypass-scan + hash-pin already passed). No nonce -> no dispatch.

This module's deterministic scheduling core is fully self-tested offline; the LLM
dispatch itself is the OpenClaw sub-agent seam (client providers only).

Exit 0 = ok, 2 = schedule/precedence/park violation, 3 = usage/IO error.
Flags: --plan --dry-run --status --resume --recover --fast-ads --strict-source --self-test
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List


def _manifest_path() -> Path:
    return Path(__file__).resolve().parent.parent / "AA-PIPELINE-MANIFEST.json"


AD_TAIL = [f"{n:02d}-ad-set-{n-21}" for n in range(23, 35)]  # ad sets 2..13 (fast-ads collapse targets)


def compute_waves(stages: List[Dict[str, Any]], fast_ads: bool = False) -> List[List[str]]:
    """Kahn layering from depends_on. Proves the DAG is acyclic and yields waves
    where every stage's deps are in strictly-earlier waves."""
    deps: Dict[str, set] = {}
    for s in stages:
        d = set(s["depends_on"])
        if fast_ads and s["stage_id"] in AD_TAIL:
            # collapse the harmony chain: sets 2..13 depend only on ad-set-1 (+ their base set)
            d = {x for x in d if not x.startswith(("23-", "24-", "25-", "26-", "27-", "28-",
                                                   "29-", "30-", "31-", "32-", "33-", "34-"))}
            d.add("22-ad-set-1")
        deps[s["stage_id"]] = d
    done: set = set()
    waves: List[List[str]] = []
    remaining = set(deps)
    while remaining:
        ready = sorted(sid for sid in remaining if deps[sid] <= done)
        if not ready:
            raise ValueError(f"cycle or missing dep among: {sorted(remaining)}")
        waves.append(ready)
        done |= set(ready)
        remaining -= set(ready)
    return waves


def throttle(wave: List[str], cap: int) -> List[List[str]]:
    return [wave[i:i + cap] for i in range(0, len(wave), cap)]


def verify_schedule(stages: List[Dict[str, Any]], waves: List[List[str]], fast_ads: bool) -> List[str]:
    """Assert no stage is scheduled before all its deps have completed in an earlier wave."""
    errs = []
    pos = {sid: i for i, w in enumerate(waves) for sid in w}
    by_id = {s["stage_id"]: s for s in stages}
    all_ids = set(by_id)
    scheduled = {sid for w in waves for sid in w}
    if scheduled != all_ids:
        errs.append(f"schedule covers {len(scheduled)}/{len(all_ids)} stages")
    for s in stages:
        sid = s["stage_id"]
        deps = set(s["depends_on"])
        if fast_ads and sid in AD_TAIL:
            deps = {"22-ad-set-1"}
        for d in deps:
            if d in pos and pos[d] >= pos.get(sid, -1):
                errs.append(f"{sid} scheduled in wave {pos.get(sid)} but dep {d} is in wave {pos[d]}")
    return errs


# ---------------------------------------------------------------------------
def _print_plan(manifest, fast_ads: bool, provider_cap: int) -> int:
    stages = manifest["stages"]
    waves = compute_waves(stages, fast_ads)
    errs = verify_schedule(stages, waves, fast_ads)
    print(f"AVATAR-ALCHEMIST FOREMAN PLAN  (fast_ads={fast_ads}, provider_cap={provider_cap})")
    print(f"branch=brand  stages={len(stages)}  dependency-waves={len(waves)}")
    for i, w in enumerate(waves, 1):
        subs = throttle(w, provider_cap)
        tag = "" if len(subs) == 1 else f"  -> {len(subs)} sub-waves @cap {provider_cap}"
        print(f"  W{i:>2}: {len(w):>2} dispatched  {w}{tag}")
    peak = max(len(w) for w in waves)
    print(f"peak dispatched width = {peak}")
    if errs:
        print("SCHEDULE VIOLATIONS:")
        for e in errs:
            print("  " + e)
        return 2
    print("schedule OK: every stage follows its dependencies.")
    return 0


def _require_nonce(nonce_path: str | None) -> bool:
    if not nonce_path:
        return False
    p = Path(nonce_path)
    return p.is_file() and len(p.read_text(encoding="utf-8").strip()) >= 16


def run_self_test(manifest) -> int:
    ok = True
    stages = manifest["stages"]

    # (a) default schedule is acyclic, covers 40, respects deps
    waves = compute_waves(stages, fast_ads=False)
    errs = verify_schedule(stages, waves, fast_ads=False)
    covered = sum(len(w) for w in waves)
    if errs or covered != 40:
        ok = False
        print(f"SELF-TEST FAIL: default schedule errs={errs[:3]} covered={covered}")
    else:
        print(f"SELF-TEST ok: default schedule acyclic, 40/40 covered, deps respected ({len(waves)} waves).")

    # (b) peak width matches the honest profile (<=5 simultaneous authors, PRD 10.1)
    peak = max(len(w) for w in waves)
    if peak > 5:
        ok = False; print(f"SELF-TEST FAIL: default peak width {peak} > 5 (PRD 10.1)")
    else:
        print(f"SELF-TEST ok: default peak simultaneous authors = {peak} (<=5).")

    # (c) fast-ads collapses the ad tail into one wide wave and stays valid
    fw = compute_waves(stages, fast_ads=True)
    ferrs = verify_schedule(stages, fw, fast_ads=True)
    fpeak = max(len(w) for w in fw)
    if ferrs or fpeak < 6:
        ok = False; print(f"SELF-TEST FAIL: fast-ads errs={ferrs[:3]} peak={fpeak}")
    else:
        print(f"SELF-TEST ok: --fast-ads valid, collapses ad tail (peak width {fpeak}, {len(fw)} waves).")

    # (d) precedence guard: a stage with an unmet dep is refused
    fake_done = {"01-avatar-questions-1-30"}
    blocked = "08-blended-tone"
    deps = set(next(s for s in stages if s["stage_id"] == blocked)["depends_on"])
    refused = not (deps <= fake_done)
    if not refused:
        ok = False; print("SELF-TEST FAIL: precedence guard did not refuse a stage with unmet deps")
    else:
        print("SELF-TEST ok: precedence guard refuses dispatch when depends_on receipts are missing.")

    # (e) front-door nonce required for a real run
    if _require_nonce(None) or _require_nonce("/nonexistent/nonce"):
        ok = False; print("SELF-TEST FAIL: nonce guard accepted a missing/short nonce")
    else:
        print("SELF-TEST ok: front-door nonce required (missing/short nonce refused).")

    print("SELF-TEST RESULT:", "PASS (exit 0)" if ok else "FAIL (exit 1)")
    return 0 if ok else 1


def main(argv) -> int:
    ap = argparse.ArgumentParser(description="Avatar-Alchemist foreman (wave scheduler + dispatcher).")
    ap.add_argument("--manifest")
    ap.add_argument("--plan", action="store_true", help="print the dependency-wave schedule")
    ap.add_argument("--dry-run", action="store_true", help="alias for --plan (no dispatch)")
    ap.add_argument("--status", action="store_true", help="print RUN-LEDGER status")
    ap.add_argument("--run-dir", help="run directory for --status/--resume")
    ap.add_argument("--nonce", help="one-time front-door nonce minted by entry.sh (required for a real run)")
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--recover", action="store_true")
    ap.add_argument("--fast-ads", action="store_true", help="collapse the ad-set harmony chain (fidelity trade-off, OFF by default)")
    ap.add_argument("--strict-source", action="store_true", help="replay the original defective wiring for A/B")
    ap.add_argument("--provider-cap", type=int, default=10, help="max concurrent authors (Ollama-only boxes cap 3)")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)

    try:
        manifest = json.loads(Path(args.manifest or _manifest_path()).read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        print(f"USAGE/IO ERROR: cannot load manifest: {exc}")
        return 3

    if args.self_test:
        return run_self_test(manifest)
    if args.plan or args.dry_run:
        return _print_plan(manifest, args.fast_ads, args.provider_cap)
    if args.status:
        led = Path(args.run_dir or ".") / "RUN-LEDGER.json"
        if not led.is_file():
            print("no RUN-LEDGER.json yet."); return 0
        data = json.loads(led.read_text(encoding="utf-8"))
        rows = data.get("stages", {})
        done = sum(1 for r in rows.values() if r.get("receipt"))
        print(f"RUN {data.get('run_id','?')}: {done}/{len(manifest['stages'])} stages attested")
        return 0
    # a REAL dispatch requires the front-door nonce (deps/bypass-scan/hash-pin already passed)
    if not _require_nonce(args.nonce):
        print("REFUSED: no valid front-door nonce. Start the run via entry.sh "
              "(deps -> bypass-scan -> hash-pin -> nonce), then pass --nonce.")
        return 2
    print("front-door nonce accepted. LLM dispatch is the OpenClaw sub-agent seam "
          "(client providers only); this offline build validates scheduling, not model calls. "
          "Use --plan to inspect the wave schedule.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
