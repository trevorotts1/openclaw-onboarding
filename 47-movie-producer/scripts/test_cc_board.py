#!/usr/bin/env python3
"""
test_cc_board.py — offline, network-free proof of the Skill 47 cc_board contract
(FIX-S36-40). Zero third-party deps. Exit 0 = all behaviors hold, exit 1 = a
contract violation.

Proves:
  * FAIL-SOFT: with MISSION_CONTROL_URL unset the board is a clean no-op —
    board_config() is None and every public caller returns a falsy value WITHOUT
    raising or touching the network.
  * LEGAL PATH: _legal_path walks in_progress -> review -> done and NEVER skips the
    QC `review` column (the exact bug FIX-S36-40 closes); backlog -> done also
    traverses in_progress + review.
  * RECEIPT STAMPING: stamp_receipt merges campaign_id + final_mp4_path into an
    EXISTING render receipt, never mints one when absent, and never clobbers an
    already-set final_mp4_path.
"""

import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import cc_board  # noqa: E402


def _run(fails, cond, msg):
    if not cond:
        fails.append(msg)


def main() -> int:
    fails: list = []

    # ---- FAIL-SOFT: board disabled when MISSION_CONTROL_URL unset --------------
    _run(fails, cc_board.board_config({}) is None,
         "board_config({}) should be None when MISSION_CONTROL_URL is unset.")
    _run(fails, cc_board.create_campaign("job-1", "My Video", env={}) is None,
         "create_campaign should return None (no-op) when the board is disabled.")
    _run(fails, cc_board.set_stage_status("job-1", "v-define", "done", env={}) is False,
         "set_stage_status should return False (no-op) when the board is disabled.")

    # ---- LEGAL PATH: review column is never skipped ---------------------------
    path = cc_board._legal_path("in_progress", "done")
    _run(fails, path == ["review", "done"],
         f"in_progress->done must walk through review; got {path!r}.")
    full = cc_board._legal_path("backlog", "done")
    _run(fails, full == ["in_progress", "review", "done"],
         f"backlog->done must walk in_progress->review->done; got {full!r}.")
    _run(fails, cc_board._legal_path("done", "done") == [],
         "done->done should be an empty path (already there).")
    _run(fails, cc_board._legal_path("backlog", "blocked") == ["blocked"],
         "any->blocked should be one hop.")

    # ---- RECEIPT STAMPING -----------------------------------------------------
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp)
        # (a) absent receipt -> stamp is a no-op (never mints a premature receipt).
        _run(fails,
             cc_board.stamp_receipt(run_dir, campaign_id="c1",
                                    final_mp4_path="working/final.mp4") is False,
             "stamp_receipt should return False when render-receipt.json is absent.")
        _run(fails, not cc_board._render_receipt_path(run_dir).exists(),
             "stamp_receipt must NOT create render-receipt.json when it is absent.")
        # (b) existing receipt -> merge campaign_id + final_mp4_path.
        rrp = cc_board._render_receipt_path(run_dir)
        rrp.parent.mkdir(parents=True, exist_ok=True)
        rrp.write_text(json.dumps({"ffprobe_pass": True, "note": "keep me"}))
        ok = cc_board.stamp_receipt(run_dir, campaign_id="c1",
                                    final_mp4_path="working/final.mp4")
        merged = json.loads(rrp.read_text())
        _run(fails, ok and merged.get("campaign_id") == "c1"
             and merged.get("final_mp4_path") == "working/final.mp4"
             and merged.get("note") == "keep me" and merged.get("ffprobe_pass") is True,
             f"stamp_receipt should merge fields without clobbering; got {merged!r}.")
        # (c) do not clobber an already-set final_mp4_path.
        rrp.write_text(json.dumps({"final_mp4_path": "working/real.mp4"}))
        cc_board.stamp_receipt(run_dir, final_mp4_path="working/other.mp4")
        keep = json.loads(rrp.read_text())
        _run(fails, keep.get("final_mp4_path") == "working/real.mp4",
             f"stamp_receipt must not clobber an existing final_mp4_path; got {keep!r}.")

    if fails:
        print("=== test_cc_board: FAILURES ===", file=sys.stderr)
        for f in fails:
            print(f"  FAIL: {f}", file=sys.stderr)
        return 1
    print("=== test_cc_board: ALL BEHAVIORS HOLD "
          "(fail-soft no-op, legal review->done path, receipt stamping) ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
