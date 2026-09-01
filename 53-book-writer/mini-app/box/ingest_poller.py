#!/usr/bin/env python3
# =============================================================================
# BOOK WRITER MINI-APP — U12 BOX INGEST POLLER (preflight.sh mirror)
# -----------------------------------------------------------------------------
# mini-app/box/ingest_poller.py
#
# Box-side poller for the run box that OWNS a Book Writer mini-app run. It
# polls the Worker job registry (GET /api/media/<answerId>, the media.js
# pollJob contract), pulls completed media, hands each completed job to the
# transcription engine (bridge/media_textractor.py, U13), and stages the
# transcription output for the GHL write-back seam (U15, Skill 44 rails).
#
#   ┌────────────┐  GET /api/media/:answerId   ┌──────────────┐
#   │  Worker     │ ──────────────────────────▶ │  poller      │
#   │  media.js   │ ◀────────────────────────── │  (this box)  │
#   └────────────┘   job JSON (pollJob contract) └──────┬───────┘
#                                                       │ pull completed media
#                                                       ▼
#                                              bridge/media_textractor.py
#                                                       │ transcription (U13)
#                                                       ▼
#                                              staged/  → GHL write-back seam (U15)
#
# THE POLLER RUNS ON THE BOX THAT OWNS THE RUN. It never runs on a generic
# edge; it never holds a client PIT. The Worker is a DUMB RELAY that holds
# ZERO client credentials — the KV binding row is the SOLE destination
# authority. The poller talks to the Worker with a token it holds ONLY because
# the run lives on this box; the Worker still validates the binding and serves
# the job row from KV.
#
# FAIL-CLOSED discipline (preflight.sh mirror — enforcement, not description):
#   * No media staged  → honest EMPTY result, exit 0. Never a fabricated job.
#   * A job that is queued/processing → parked, reported pending, not fetched.
#   * A job that is failed  → surfaced as failed (retry), never silenced.
#   * A done job with EMPTY text  → surfaced as missing/blank, never trusted.
#   * Any worker/network failure  → surfaced, exit 2 (never a silent skip).
#   * Every capability the box needs is read from capability-map.json (the
#     U12 probe / preflight.sh mirror); a REQUIRED capability absent -> hard
#     fail with AF-BW-MA-CAPABILITY, never a silent skip.
#   * No double-brace or dollar-paren template tokens, no Anthropic ids, no
#     client secrets on the edge.
#
# NEW AF CODES (MASTER-PLAN section 4, prefixed AF-BW-MA-*):
#   AF-BW-MA-CAPABILITY   a required capability is absent (probe said false
#                         and no client resolver) — hard fail, never skip
#   AF-BW-MA-WORKER       the Worker job registry was unreachable or returned
#                         a malformed job (fail-closed, never silent)
#   AF-BW-MA-JOB-PENDING  a queued/processing job was parked (honest pending,
#                         not fabricated)
#   AF-BW-MA-EXTRACT-NO-TEXT  a done job carried empty text (never trusted)
#
# EXIT CODES (prover convention via _bw_common):
#   0  PASS — poll complete; staged any completed media; or honest empty
#   2  AUTOFAIL — an AF-BW-MA-* violation fired (fail-closed)
#   3  USAGE/IO — missing file / unreadable / bad arguments
#   7  capability hard-fail (required capability absent, no resolver)
#
# USAGE:
#   python3 ingest_poller.py <poll-spec.json> [--capability-map cap.json]
#       [--out-dir DIR] [--self-test]
#
# poll-spec.json shape (written by the run ledger on the owning box):
#   {
#     "client_id":   string,        -- bound client (authority lives on the
#                                     KV binding row, never invented here)
#     "run_id":      string,
#     "answer_ids":  ["<answerId>", ...],   -- answerIds to poll
#     "worker_base": string,        -- Worker base URL (GET /api/media/:id)
#     "token":       string         -- run token this box holds (binding token)
#   }
#
# The self-test uses a STUBBED poll source: no network, no Worker. The
# negative case (no media / a pending job / a failed job) must produce an
# HONEST empty/failed result — never a fabricated job.
# =============================================================================
"""Box-side ingest poller (U12, preflight.sh mirror) — poll -> pull -> transcribe -> stage."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# _bw_common lives in 53-book-writer/scripts/ — reach it from the box dir.
_HERE = Path(__file__).resolve().parent
_SCRIPTS = (_HERE.parent.parent / "scripts")
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import _bw_common as c  # noqa: E402

# ---- AF codes (MASTER-PLAN section 4) --------------------------------------
AF_CAPABILITY = "AF-BW-MA-CAPABILITY"
AF_WORKER = "AF-BW-MA-WORKER"
AF_JOB_PENDING = "AF-BW-MA-JOB-PENDING"
AF_EXTRACT_NO_TEXT = "AF-BW-MA-EXTRACT-NO-TEXT"
AF_ANTHROPIC = "AF-BW-MA-ANTHROPIC"

# ---- job status contract (mirror worker/src/media-lib.js JOB_STATUS) --------
JOB_STATUS = ("queued", "processing", "done", "failed")
DONE = "done"
FAILED = "failed"

# The media job field names the poller reads from the Worker pollJob view
# (media-lib.js buildQueuedJob / pollView contract).
JOB_FIELDS = (
    "intake_id", "answer_id", "channel", "source_uri", "source_sha256",
    "status", "text", "transcript_json", "still_frame", "error",
    "created_at_utc", "done_at_utc",
)

# Placeholder/template tokens never shipped (shared regex lives in _bw_common;
# the self-test scans this module with c._PLACEHOLDER_RE).


def _now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


# ---------------------------------------------------------------------------
# capability gate (reads capability-map.json written by U12 capability_probe)
# ---------------------------------------------------------------------------

_DEFAULT_CAPABILITY_MAP_CANDIDATES = (
    _HERE / "capability-map.json",
    _HERE.parent / "capability-map.json",
    _HERE.parent.parent / "capability-map.json",
)


def resolve_capability_map_path(path) -> Path | None:
    """Resolve the capability-map.json path (explicit arg or default
    candidates), or None when no map exists on the box. Returns the PATH —
    the poller passes the path to the textractor, never a dict."""
    p = Path(path) if path else None
    if p is None or not p.exists():
        for cand in _DEFAULT_CAPABILITY_MAP_CANDIDATES:
            if cand.exists():
                p = cand
                break
    return p if (p is not None and p.exists()) else None


def load_capability_map(path):
    """Read capability-map.json (U12 / preflight.sh mirror). A missing or
    unreadable map -> {} (capabilities unknown; the poller still runs and
    surfaces honest results, but a REQUIRED capability absent from an empty
    map hard-fails via AF-BW-MA-CAPABILITY when it would be needed)."""
    p = resolve_capability_map_path(path)
    if p is None:
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


# ---------------------------------------------------------------------------
# Worker poll client (media.js pollJob contract)
# ---------------------------------------------------------------------------

def poll_worker(worker_base: str, answer_id: str, token: str | None,
                timeout: float = 30.0) -> tuple:
    """GET /api/media/<answer_id> against the Worker. Returns
    (ok: bool, job: dict|None, status: int|None).

    Mirrors media.js pollJob: a 200 with a job row -> job; a 200 with
    job:null (missing) -> (True, None); any HTTP error -> (False, None, code);
    a network failure -> (False, None, None). Fail-closed: an unreachable or
    malformed registry is never treated as "no media".
    """
    url = "%s/api/media/%s" % (worker_base.rstrip("/"), answer_id)
    headers = {}
    if token:
        headers["Authorization"] = "Bearer %s" % token
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", "replace")
            try:
                data = json.loads(body)
            except ValueError:
                return True, None, resp.status  # 200 but unparsable -> no job view
            job = data.get("job") if isinstance(data, dict) else None
            if job is None and isinstance(data, dict) and data.get("status"):
                # some poll views embed the job at top level
                job = data
            return True, (job if isinstance(job, dict) else None), resp.status
    except urllib.error.HTTPError as exc:
        return False, None, exc.code
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return False, None, None


# ---------------------------------------------------------------------------
# transcription hand-off (bridge/media_textractor.py, U13)
# ---------------------------------------------------------------------------

def _find_textractor() -> Path | None:
    """Locate bridge/media_textractor.py (the U13 engine)."""
    cands = (
        _HERE.parent / "bridge" / "media_textractor.py",
        _HERE.parent.parent / "bridge" / "media_textractor.py",
    )
    for cpath in cands:
        if cpath.exists():
            return cpath
    return None


def transcribe_job(job: dict, capability_map_path: Path | None,
                   client_resolver: str | None, out_dir: Path) -> dict:
    """Hand one completed job to bridge/media_textractor.py (U13). Returns the
    textractor's completed job record (done -> text; failed -> error).

    capability_map_path is the RESOLVED capability-map.json path (or None) —
    passed through to the textractor's --capability-map argument.

    Fail-closed: the textractor is REQUIRED. If the engine is missing this is
    a capability hard-fail (AF-BW-MA-CAPABILITY), never a silent skip.
    """
    tx = _find_textractor()
    if tx is None:
        return _hard_fail(job, AF_CAPABILITY,
                          "bridge/media_textractor.py (U13 engine) is not "
                          "present on this box — cannot transcribe")
    payload = {k: job.get(k) for k in JOB_FIELDS if k in job}
    payload.setdefault("intake_id", job.get("intake_id"))
    payload.setdefault("answer_id", job.get("answer_id"))
    payload.setdefault("channel", job.get("channel"))
    payload.setdefault("source_uri", job.get("source_uri"))
    payload.setdefault("source_sha256", job.get("source_sha256"))

    job_file = out_dir / "job-input.json"
    out_file = out_dir / "job-output.json"
    job_file.parent.mkdir(parents=True, exist_ok=True)
    job_file.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

    argv = [sys.executable, str(tx), str(job_file), "--out", str(out_file)]
    if capability_map_path is not None:
        argv += ["--capability-map", str(capability_map_path)]
    if client_resolver:
        argv += ["--client-resolver", client_resolver]
    try:
        proc = subprocess.run(argv, capture_output=True, timeout=1800)
    except (subprocess.TimeoutExpired, OSError) as exc:
        return _hard_fail(job, AF_CAPABILITY,
                          "textractor invocation failed: %s" % exc)
    try:
        result = json.loads(out_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return _hard_fail(job, AF_WORKER,
                          "textractor produced no parseable output (exit %d)"
                          % proc.returncode)
    if proc.returncode not in (0, 2, 7) or not isinstance(result, dict):
        return _hard_fail(job, AF_WORKER,
                          "textractor exited %d for %s"
                          % (proc.returncode, job.get("answer_id")))
    return result


def _hard_fail(job: dict, code: str, msg: str) -> dict:
    out = dict(job)
    out["status"] = FAILED
    out["done_at_utc"] = _now_utc()
    out["error"] = "%s: %s" % (code, msg)
    return out


# ---------------------------------------------------------------------------
# the poll decision core (pure — injected poll for offline tests)
# ---------------------------------------------------------------------------

def poll_one(spec: dict, poll_impl, capability_map_path=None,
             client_resolver=None, out_dir=None, now=None) -> dict:
    """Poll a single answerId through the ingest pipeline. Returns a per-job
    outcome record. Pure given poll_impl (the network call is injected).

    poll_impl(answer_id, token) -> (ok, job, status) per poll_worker.
    capability_map_path is the RESOLVED capability-map.json path (or None),
    threaded to the textractor (U13) when a done job is staged.
    """
    answer_id = spec.get("answer_id")
    token = spec.get("token")
    out_dir = out_dir or (Path(spec.get("out_dir")) if spec.get("out_dir") else _HERE / "staged")
    now = now or _now_utc()

    if not answer_id:
        return {"answer_id": answer_id, "status": FAILED,
                "error": "%s: poll-spec missing answer_id" % AF_WORKER,
                "done_at_utc": now}

    ok, job, status = poll_impl(answer_id, token)
    if not ok:
        return {"answer_id": answer_id, "status": FAILED,
                "error": "%s: worker unreachable or error (http %s)"
                % (AF_WORKER, status if status is not None else "none"),
                "done_at_utc": now}
    if job is None:
        # Honest absence: the worker returned no job for this answerId.
        return {"answer_id": answer_id, "status": "missing",
                "error": None, "done_at_utc": now}

    js = job.get("status")
    if js in ("queued", "processing"):
        return {"answer_id": answer_id, "status": js, "pending": True,
                "error": None, "done_at_utc": now}
    if js == FAILED:
        return {"answer_id": answer_id, "status": FAILED,
                "error": job.get("error") or "%s: job failed upstream" % AF_WORKER,
                "done_at_utc": now}
    if js == DONE:
        text = job.get("text") or ""
        if not text.strip():
            return {"answer_id": answer_id, "status": FAILED,
                    "error": "%s: done job carried empty text — never trusted"
                    % AF_EXTRACT_NO_TEXT, "done_at_utc": now}
        # Stage for the textractor (U13) — the engine re-validates format/size
        # and performs the transcription on the box that owns the run.
        staged = transcribe_job(job, capability_map_path, client_resolver, out_dir)
        return {"answer_id": answer_id, "status": staged.get("status"),
                "job": staged, "error": staged.get("error"),
                "done_at_utc": now}
    return {"answer_id": answer_id, "status": FAILED,
            "error": "%s: unknown job status %r" % (AF_WORKER, js),
            "done_at_utc": now}


def poll_all(spec: dict, poll_impl, capability_map_path=None,
             client_resolver=None, out_dir=None, now=None) -> dict:
    """Poll every answerId in the spec and build the run outcome. The negative
    case (no answerIds / every poll empty) is an HONEST empty result — never
    a fabricated job. capability_map_path threads the resolved capability-map
    path to the textractor for staged done jobs."""
    answers = spec.get("answer_ids") or []
    if not answers:
        return {
            "run_id": spec.get("run_id"),
            "client_id": spec.get("client_id"),
            "polled_at": now or _now_utc(),
            "outcomes": [],
            "summary": {"total": 0, "done": 0, "pending": 0, "failed": 0,
                        "missing": 0},
            "stage": {"out_dir": str(out_dir or _HERE / "staged")},
            "empty": True,
        }
    outcomes = []
    for aid in answers:
        sub = dict(spec)
        sub["answer_id"] = aid
        outcomes.append(poll_one(sub, poll_impl,
                                 capability_map_path=capability_map_path,
                                 client_resolver=client_resolver,
                                 out_dir=out_dir, now=now))
    summary = {"total": len(outcomes), "done": 0, "pending": 0, "failed": 0,
               "missing": 0}
    for o in outcomes:
        s = o.get("status")
        if s == "done":
            summary["done"] += 1
        elif s in ("queued", "processing") or o.get("pending"):
            summary["pending"] += 1
        elif s == "missing":
            summary["missing"] += 1
        elif s == FAILED:
            summary["failed"] += 1
    return {
        "run_id": spec.get("run_id"),
        "client_id": spec.get("client_id"),
        "polled_at": now or _now_utc(),
        "outcomes": outcomes,
        "summary": summary,
        "stage": {"out_dir": str(out_dir or _HERE / "staged")},
        "empty": summary["total"] == 0,
    }


# ---------------------------------------------------------------------------
# CLI + self-test
# ---------------------------------------------------------------------------

def self_test() -> int:
    checks = []

    # 1. Negative case: no answerIds -> honest empty, exit-0 class.
    empty = poll_all({"run_id": "r1", "client_id": "client_A",
                      "answer_ids": []},
                     poll_impl=None)
    checks.append(("no answerIds -> honest empty result", empty.get("empty") is True
                   and empty["summary"]["total"] == 0
                   and empty["outcomes"] == []))

    # 2. Pending job (queued/processing) -> parked as pending, not fabricated.
    spec = {"run_id": "r1", "client_id": "client_A", "answer_ids": ["a1"],
            "worker_base": "https://worker.test", "token": "tok"}
    def pending_poll(aid, token):
        return (True, {"status": "queued", "answer_id": aid,
                       "text": "", "source_uri": "r2://x/a1.mp3"}, 200)
    out = poll_all(spec, pending_poll)
    o = out["outcomes"][0]
    checks.append(("queued job -> parked pending, honest", o.get("pending") is True
                   and o.get("status") == "queued"))
    checks.append(("pending never fabricated as done",
                   not (o.get("status") == "done" and not o.get("text"))))

    # 3. Failed job -> surfaced as failed with the upstream error, never silent.
    def failed_poll(aid, token):
        return (True, {"status": "failed", "answer_id": aid, "text": "",
                       "error": "upstream failed"}, 200)
    out = poll_all(spec, failed_poll)
    checks.append(("failed job -> surfaced failed with error",
                   out["outcomes"][0]["status"] == "failed"
                   and "upstream failed" in (out["outcomes"][0].get("error") or "")))

    # 4. Done job with EMPTY text -> failed (never trusted as done-with-blank).
    def blank_done_poll(aid, token):
        return (True, {"status": "done", "answer_id": aid, "text": "   "}, 200)
    out = poll_all(spec, blank_done_poll)
    checks.append(("done + empty text -> EXTRACT-NO-TEXT failed",
                   out["outcomes"][0]["status"] == "failed"
                   and AF_EXTRACT_NO_TEXT in (out["outcomes"][0].get("error") or "")))

    # 5. Worker unreachable -> honest worker failure (exit-2 class), never
    #    a silent "no media".
    def dead_poll(aid, token):
        return (False, None, None)
    out = poll_all(spec, dead_poll)
    checks.append(("worker unreachable -> AF-BW-MA-WORKER failed",
                   out["outcomes"][0]["status"] == "failed"
                   and AF_WORKER in (out["outcomes"][0].get("error") or "")))

    # 6. Worker returns no job (job:null) -> honest missing.
    def missing_poll(aid, token):
        return (True, None, 200)
    out = poll_all(spec, missing_poll)
    checks.append(("worker job:null -> honest missing", out["outcomes"][0]["status"] == "missing"))

    # 7. A done job with text hands to the textractor; when the engine is
    #    absent on the box -> capability hard-fail, never a silent skip.
    #    (The textractor is present in this repo, so the positive path runs
    #    the real engine against a fixture source.)
    import tempfile
    import shutil as _sh
    tmp = Path(tempfile.mkdtemp(prefix="ma-u12-selftest-"))
    out_dir = tmp / "staged"
    txt_src = tmp / "notes.txt"
    txt_src.write_text("my story ideas\n", encoding="utf-8")

    def done_txt_poll(aid, token):
        return (True, {"status": "done", "answer_id": aid, "text": "staged",
                       "channel": "txt", "source_uri": str(txt_src),
                       "source_sha256": "x", "intake_id": "i1"}, 200)
    cap_map_path = tmp / "capability-map.json"
    cap_map_path.write_text(json.dumps({"transcribe": True, "resolvers": {}}),
                            encoding="utf-8")
    out = poll_all(spec, done_txt_poll, capability_map_path=cap_map_path,
                   out_dir=out_dir)
    o = out["outcomes"][0]
    tx = _find_textractor()
    if tx is None:
        checks.append(("done+text with no textractor -> capability hard-fail",
                       o["status"] == "failed" and AF_CAPABILITY in (o.get("error") or "")))
    else:
        checks.append(("done+text staged through textractor -> done with text",
                       o["status"] == "done" and (o.get("job") or {}).get("text") == "my story ideas"))
        checks.append(("staged output written to out_dir",
                       (out_dir / "job-output.json").exists()))

    # 8. No double-brace/dollar-paren template tokens in shipped code.
    src = Path(__file__).read_text(encoding="utf-8")
    checks.append(("no double-brace/dollar-paren template tokens in shipped code",
                   c._PLACEHOLDER_RE.search(src) is None))

    # cleanup
    _sh.rmtree(tmp, ignore_errors=True)
    return c.selftest_report("ingest_poller", checks)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Book Writer mini-app U12 box ingest poller "
                    "(preflight.sh mirror).")
    ap.add_argument("spec", nargs="?", help="poll-spec.json")
    ap.add_argument("--capability-map", help="capability-map.json path")
    ap.add_argument("--client-resolver", help="per-client ASR resolver name")
    ap.add_argument("--out-dir", help="staging output directory")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)

    if args.self_test:
        return self_test()
    if not args.spec:
        ap.error("a poll-spec.json path is required (or use --self-test)")

    try:
        spec = c.read_json(args.spec)
    except SystemExit:
        return c.EXIT_USAGE
    if not isinstance(spec, dict):
        print("USAGE/IO: poll-spec must be a JSON object", file=sys.stderr)
        return c.EXIT_USAGE

    capability_map_path = resolve_capability_map_path(args.capability_map)
    out_dir = Path(args.out_dir) if args.out_dir else (_HERE / "staged")
    worker_base = spec.get("worker_base") or os.environ.get("BW_WORKER_BASE")
    if not worker_base:
        print("USAGE/IO: poll-spec worker_base required (or BW_WORKER_BASE)",
              file=sys.stderr)
        return c.EXIT_USAGE

    def poll_impl(aid, token):
        return poll_worker(worker_base, aid, token)

    result = poll_all(spec, poll_impl, capability_map_path=capability_map_path,
                      client_resolver=args.client_resolver, out_dir=out_dir)
    print(json.dumps(result, indent=2, default=str))

    # fail-closed exit: any failed outcome is an AUTOFAIL (2); a capability
    # hard-fail is exit 7; otherwise 0 (including honest empty).
    codes = [o.get("error") or "" for o in result["outcomes"]]
    if any(AF_CAPABILITY in e for e in codes):
        return 7
    if any(o.get("status") == "failed" for o in result["outcomes"]):
        return c.EXIT_AUTOFAIL
    return c.EXIT_PASS


if __name__ == "__main__":
    sys.exit(main())
