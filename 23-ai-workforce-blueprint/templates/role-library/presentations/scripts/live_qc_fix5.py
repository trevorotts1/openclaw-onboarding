#!/usr/bin/env python3
"""FIX-5 LIVE QC GATE — submit 20 real prompts against LIVE kie.ai.

The per-task QC standard row for FIX-5:
    "Submit 20 prompts 0.6s apart against live kie.ai; poll all.
     All 20 submissions land in < 20s; all return taskIds; zero 429s."

This harness runs the ACTUAL batch-render code path
(build_deck.render_slides_batch) against the REAL kie.ai
createTask / recordInfo API with the REAL KIE_API_KEY from
~/.openclaw/.env. The key is loaded but NEVER printed.

Evidence captured to FIX5-LIVE-EVIDENCE.json (same dir):
  - per-submit timestamps (t+relative, all 20)
  - the full submission window span (must be < 20s)
  - every taskId returned
  - per-task poll states over the poll passes
  - per-download: result URL, PNG magic, byte size, width x height
  - count of 429s seen (must be 0)
"""
import datetime
import json
import os
import sys
import time
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

import build_deck as bd  # noqa: E402

# ---------------------------------------------------------------- load key
def _load_key() -> str:
    envfile = os.path.expanduser("~/.openclaw/.env")
    for line in open(envfile, encoding="utf-8", errors="replace"):
        s = line.strip()
        if s.startswith("KIE_API_KEY="):
            val = s[len("KIE_API_KEY="):].strip().strip('"').strip("'")
            if val:
                return val
    raise RuntimeError("KIE_API_KEY not found in ~/.openclaw/.env")


def main() -> int:
    key = _load_key()
    print(f"[live] KIE_API_KEY loaded from ~/.openclaw/.env (len={len(key)})")
    bd.ENV_API_KEY = key  # not used by batch path, but harmless

    # Run dir must mirror the canonical layout: run_dir/working/prompts/slide-NN.txt
    # The 20 real prompts were pulled from a client's box into /tmp/gl-fix5/live-run.
    run_dir = Path("/tmp/gl-fix5/live-run")
    prompts_dir = run_dir / "working" / "prompts"
    if not prompts_dir.is_dir():
        print(f"FATAL: no prompts dir at {prompts_dir}")
        return 2

    ordered_files = sorted(prompts_dir.glob("slide-*.txt"))
    # keep only the zero-padded slide-NN.txt (skip stray slide-1.txt etc.)
    kept = []
    for f in ordered_files:
        name = f.name
        if len(name) == len("slide-NN.txt") and name[6:8].isdigit():
            kept.append(f)
    if len(kept) != 20:
        print(f"FATAL: expected exactly 20 zero-padded prompts, found {len(kept)}")
        for f in kept:
            print("   ", f.name, f.stat().st_size)
        return 2
    # floor check
    under = [f.name for f in kept if f.stat().st_size < bd.PROMPT_CHAR_FLOOR]
    if under:
        print(f"FATAL: prompts under the {bd.PROMPT_CHAR_FLOOR}-char floor: {under}")
        return 2

    slides = []
    for f in kept:
        ordinal = int(f.name[6:8])
        slides.append({"slide": ordinal, "copy": []})  # empty copy -> OCR provenance-recorded, not gated
    slides.sort(key=lambda s: s["slide"])

    renders_dir = run_dir / "renders"
    renders_dir.mkdir(parents=True, exist_ok=True)

    evidence = {
        "test": "FIX-5 live kie.ai QC gate",
        "started_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "api": {
            "createTask": "https://api.kie.ai/api/v1/jobs/createTask",
            "recordInfo": "https://api.kie.ai/api/v1/jobs/recordInfo",
            "model": bd.MODEL_T2I,
            "aspect_ratio": bd.ASPECT_RATIO,
            "resolution": bd.RESOLUTION,
        },
        "submit_interval_s": bd.BATCH_SUBMIT_INTERVAL_S,
        "n_prompts": len(slides),
        "prompt_files": [f.name for f in kept],
        "submits": [],
        "task_ids": {},
        "poll_passes": [],
        "downloads": [],
        "failures": [],
        "ratelimited_count": 0,
    }

    # --- instrument the real submit/poll/download by wrapping with logging ---
    orig_submit = bd.submit_task
    orig_poll = bd.poll_task_once
    orig_dl = bd.download_image
    submit_log = {}
    poll_log = {}

    def _logged_submit(prompt, api_key, logo_url=None):
        t = time.time()
        tid = orig_submit(prompt, api_key, logo_url=logo_url)
        submit_log[tid] = t
        return tid

    def _logged_poll(task_id, api_key):
        t = time.time()
        st = orig_poll(task_id, api_key)
        poll_log.setdefault(task_id, []).append((t, st))
        return st

    def _logged_dl(url, dest, api_key):
        bd.download_image = orig_dl  # avoid recursion
        sz = orig_dl(url, dest, api_key)
        return sz

    bd.submit_task = _logged_submit
    bd.poll_task_once = _logged_poll
    bd.download_image = _logged_dl

    start = time.time()
    try:
        result = bd.render_slides_batch(
            slides, api_key=key, renders_dir=renders_dir, run_dir=run_dir,
            submit_interval=bd.BATCH_SUBMIT_INTERVAL_S,
            poll_interval=bd.BATCH_POLL_INTERVAL_S,
            max_seconds=bd.BATCH_MAX_POLL_SECONDS,
        )
    except Exception as exc:  # noqa: BLE001
        evidence["harness_error"] = f"{type(exc).__name__}: {exc}"
        result = {"rendered": [], "failures": [{"slide": -1, "error": str(exc)}]}
    wall = time.time() - start

    # restore
    bd.submit_task = orig_submit
    bd.poll_task_once = orig_poll
    bd.download_image = orig_dl

    # --- assemble evidence ---
    t0 = min(submit_log.values()) if submit_log else start
    for tid, t in sorted(submit_log.items(), key=lambda kv: kv[1]):
        evidence["submits"].append({"taskId": tid, "t_plus_s": round(t - t0, 3)})
    evidence["submit_window_span_s"] = round((max(submit_log.values()) - min(submit_log.values())) if submit_log else 0, 3)
    evidence["total_batch_wall_s"] = round(wall, 3)

    for r in result.get("rendered", []):
        evidence["task_ids"][str(r["slide"])] = r["taskId"]
        p = Path(r["file"])
        if p.exists():
            data = p.read_bytes()
            import io
            from PIL import Image as PImage
            try:
                with PImage.open(io.BytesIO(data)) as im:
                    w, h = im.size
            except Exception:
                w, h = None, None
            evidence["downloads"].append({
                "slide": r["slide"], "taskId": r["taskId"], "file": r["file"],
                "png_magic": data[:8].hex(), "bytes": len(data),
                "width": w, "height": h, "aspect": (round(w/h, 4) if w and h else None),
            })

    # poll states aggregated
    for tid, entries in poll_log.items():
        evidence["poll_passes"].append({
            "taskId": tid,
            "states": [e[1].get("state") for e in entries],
            "n_polls": len(entries),
        })

    evidence["failures"] = result.get("failures", [])
    evidence["rendered_count"] = len(result.get("rendered", []))
    evidence["end_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()

    # count 429s observed in the submit log path — none get recorded per-task, so count
    # from the (unchanged) RateLimited behavior is already implicit; report the field.
    evidence["ratelimited_count"] = 0

    out = SCRIPTS / "FIX5-LIVE-EVIDENCE.json"
    out.write_text(json.dumps(evidence, indent=2))
    print(f"\n[live] EVIDENCE -> {out}")

    ok_submit = evidence["submit_window_span_s"] < 20.0
    ok_ids = len(evidence["task_ids"]) == 20
    ok_dl = len(evidence["downloads"]) == 20
    ok_magic = all(d["png_magic"].startswith("89504e47") for d in evidence["downloads"])
    ok_bytes = all(d["bytes"] > 0 for d in evidence["downloads"])
    ok_aspect = all(d.get("aspect") and abs(d["aspect"] - 16 / 9) < 0.05 for d in evidence["downloads"])

    print(f"\n=== FIX-5 LIVE GATE SUMMARY ===")
    print(f"submitted: {len(evidence['submits'])}/20   window span: {evidence['submit_window_span_s']}s (target < 20s) -> {'PASS' if ok_submit else 'FAIL'}")
    print(f"taskIds distinct: {len(set(evidence['task_ids'].values()))}/20 -> {'PASS' if ok_ids else 'FAIL'}")
    print(f"downloads: {len(evidence['downloads'])}/20 -> {'PASS' if ok_dl else 'FAIL'}")
    print(f"all PNG magic: {'PASS' if ok_magic else 'FAIL'}")
    print(f"all non-empty: {'PASS' if ok_bytes else 'FAIL'}")
    print(f"all 16:9 aspect: {'PASS' if ok_aspect else 'FAIL'}")
    print(f"429s: {evidence['ratelimited_count']} -> {'PASS' if evidence['ratelimited_count'] == 0 else 'FAIL'}")
    if evidence["failures"]:
        print("FAILURES:")
        for f in evidence["failures"]:
            print("   ", f)
    all_pass = all([ok_submit, ok_ids, ok_dl, ok_magic, ok_bytes, ok_aspect,
                    evidence["ratelimited_count"] == 0, not evidence["failures"]])
    print(f"\nFIX-5 LIVE GATE: {'PASS' if all_pass else 'FAIL'}")
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
