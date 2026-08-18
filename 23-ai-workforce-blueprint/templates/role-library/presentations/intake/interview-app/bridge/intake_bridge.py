#!/usr/bin/env python3
"""Box-side bridge: pick a finished intake up from the app, write the run-dir
record, and trigger the presentation department (kanban card).

This is the SUBMIT-TRIGGER. When a client finishes the Presentation Interview
app, the app (or the Worker /api/intake sink) has the assembled intake record.
This bridge:

  ingest  -> pull the finished intake from the Worker (/api/intake or the
             session answer stream), write working/copy/intake.json +
             working/interview/intake_ledger.json via intake_writer.py, then
             call cc_board.ingest_deck_task() to open the Command Center kanban
             card (department_slug=presentations) — the presentation department
             start. No shortcuts: the deck can only build through
             presentation-canonical-entry.sh's governed gates.

It mirrors the canonical intake-miniapp bridge (intake_bridge.py) for the
hosted-session path, and adds the /api/dept-start hand-off for the static-app
path. Stdlib only (urllib) — nothing to install on a box.

No secrets are printed. The box→worker admin token is read from env
INTAKE_ADMIN_TOKEN (never from argv, never logged).
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import urllib.error
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

try:
    import intake_writer
except ImportError:
    # Allow running from a checkout where intake_writer.py sits next to us.
    import importlib.util  # noqa: F401
    intake_writer = None


def _load_cc_board() -> object | None:
    """Locate cc_board.py (the Command Center ingest helper) if available."""
    for root in (
        pathlib.Path(os.environ.get("PRESENTATIONS_SCRIPTS", "")) if os.environ.get("PRESENTATIONS_SCRIPTS") else HERE.parent,
        HERE.parent.parent / "scripts",
        pathlib.Path.home() / ".openclaw" / "workspace" / "departments" / "Presentations" / "scripts",
    ):
        cand = root / "cc_board.py"
        if cand.is_file():
            import importlib.util as _u
            spec = _u.spec_from_file_location("cc_board", cand)
            if spec and spec.loader:
                mod = _u.module_from_spec(spec)
                spec.loader.exec_module(mod)
                return mod
    return None


_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")


def _http(method: str, url: str, *, token: str | None = None, body: dict | None = None,
          timeout: int = 20) -> tuple[int, dict]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("content-type", "application/json")
    # Browser-like UA so Cloudflare's bot check does not 1010-block the bridge.
    req.add_header("user-agent", _UA)
    if token:
        req.add_header("authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, {"error": raw[:200]}


def _fetch_intake(args) -> dict:
    """Fetch the finished intake record from the Worker (by session id)."""
    admin = os.environ.get("INTAKE_ADMIN_TOKEN", "")
    if not admin:
        print("error: INTAKE_ADMIN_TOKEN not set in env", file=sys.stderr)
        sys.exit(2)
    url = args.worker_url.rstrip("/") + "/api/intake?id=" + args.session_id
    status, resp = _http("GET", url, token=admin)
    if status != 200:
        print(f"error: intake fetch failed (HTTP {status}): {resp.get('error')}", file=sys.stderr)
        sys.exit(3)
    return resp


def cmd_ingest(args) -> int:
    intake_payload = _fetch_intake(args)
    intake = intake_payload.get("intake") or intake_payload
    intake.setdefault("intake_session_id", args.session_id)

    # fix/deck-type-routing-bypass follow-up: this bridge already has
    # PRESENTER_CHAT_ID in hand (it is read a few lines below, but only to
    # pass to cc.ingest_deck_task() for CC-board registration -- a different
    # purpose than the engine's own hard gate on requester.chat_id; see
    # presentation_job/resolve_intake.py and __main__.py cmd_new). It was
    # never stamped into the record intake_writer.write_intake_file() below
    # persists as working/copy/intake.json -- the ONE file the engine's
    # resolve_intake.py reads -- so an app-submitted deck's engine job could
    # never report to the client who submitted it. Stamp it into `intake`
    # itself, here, BEFORE the write, so it lands in the run-dir record.
    # Never overwrites a value the app itself already supplied.
    if not str(intake.get("requester_chat_id") or "").strip():
        _presenter_chat_id = os.environ.get("PRESENTER_CHAT_ID", "").strip()
        if _presenter_chat_id:
            intake["requester_chat_id"] = _presenter_chat_id
            intake["requester_channel"] = \
                os.environ.get("PRESENTER_CHANNEL", "").strip() or "telegram"

    # 1) Write the run-dir record (dept-format intake.json + completed ledger
    #    + the GATE 0b conversation transcript).
    if intake_writer is not None:
        run_dir = pathlib.Path(args.run_dir).expanduser().resolve()
        run_dir.mkdir(parents=True, exist_ok=True)
        intake_writer.write_intake_file(run_dir, intake)
        intake_writer.write_ledger(run_dir, intake)
        if hasattr(intake_writer, "write_transcript"):
            intake_writer.write_transcript(run_dir, intake)
        if args.verbose:
            print(f"wrote run-dir record under {run_dir}/working/")
    else:
        print("error: intake_writer.py not importable — cannot stamp the run dir", file=sys.stderr)
        return 2

    # 2) Trigger the presentation department start (kanban card, no shortcuts).
    cc = _load_cc_board()
    if cc is not None and hasattr(cc, "ingest_deck_task"):
        brief = intake.get("deck_brief") or {}
        title = brief.get("OFFER_NAME") or intake.get("intake_session_id") or args.session_id
        desc = f"Intake captured by the Presentation Interview app ({args.session_id}).\n" + json.dumps(intake.get("deck_brief") or intake.get("answers") or {}, indent=2)
        task_id = cc.ingest_deck_task(
            run_dir,
            deck_slug=args.session_id,
            title=f"Deck — {title}",
            description=desc,
            priority="medium",
            requester_chat_id=os.environ.get("PRESENTER_CHAT_ID", ""),
        )
        if task_id:
            print(json.dumps({"status": "dept_started", "session_id": args.session_id, "task_id": task_id}))
            return 0
        print(json.dumps({"status": "dept_start_deferred", "session_id": args.session_id,
                          "note": "cc_board.ingest_deck_task returned None (board URL unset or transport failure); run staged for pickup"}))
        return 0

    # 3) Fall back to the Worker /api/dept-start endpoint.
    admin = os.environ.get("INTAKE_ADMIN_TOKEN", "")
    status, resp = _http("POST", args.worker_url.rstrip("/") + "/api/dept-start", token=admin,
                         body={"intake_session_id": args.session_id, "intake": intake})
    if status in (200, 201, 202):
        print(json.dumps(resp))
        return 0
    print(f"error: dept-start failed (HTTP {status}): {resp.get('error')}", file=sys.stderr)
    return 4


def _list_intakes(args) -> list:
    """GET /api/intake/list — enumerate finished intakes stored in the worker."""
    admin = os.environ.get("INTAKE_ADMIN_TOKEN", "")
    if not admin:
        print("error: INTAKE_ADMIN_TOKEN not set in env", file=sys.stderr)
        sys.exit(2)
    url = args.worker_url.rstrip("/") + "/api/intake/list"
    status, resp = _http("GET", url, token=admin)
    if status != 200:
        print(f"error: intake list failed (HTTP {status}): {resp.get('error')}", file=sys.stderr)
        sys.exit(3)
    return resp.get("intakes") or []


def _processed_ledger(args) -> set:
    """Read the poll ledger (session ids already ingested) if present."""
    led = pathlib.Path(args.poll_ledger).expanduser()
    try:
        return set(led.read_text().split())
    except FileNotFoundError:
        return set()


def _mark_processed(args, session_id: str) -> None:
    """Append a session id to the poll ledger (idempotent — a session is ingested once)."""
    led = pathlib.Path(args.poll_ledger).expanduser()
    led.parent.mkdir(parents=True, exist_ok=True)
    done = _processed_ledger(args)
    done.add(session_id)
    led.write_text("\n".join(sorted(done)) + "\n")


def cmd_poll(args) -> int:
    """Discover finished intakes via the list endpoint and ingest each one once."""
    intakes = _list_intakes(args)
    if args.verbose:
        print(f"poll: {len(intakes)} stored intake(s) discovered")
    processed = _processed_ledger(args)
    ingested = 0
    skipped = 0
    for it in intakes:
        sid = it.get("session_id")
        if not sid:
            continue
        if sid in processed:
            skipped += 1
            if args.verbose:
                print(f"poll: {sid} already processed — skip")
            continue
        # Ingest this session (mirrors `ingest` with a per-session run dir).
        run_dir = pathlib.Path(args.run_dir).expanduser().resolve()
        if args.per_session_dirs:
            run_dir = run_dir / sid
        # Reuse the ingest machinery via a synthetic args namespace.
        sub = argparse.Namespace(
            worker_url=args.worker_url, session_id=sid, run_dir=str(run_dir),
            verbose=args.verbose, func=cmd_ingest,
        )
        rc = cmd_ingest(sub)
        if rc == 0:
            _mark_processed(args, sid)
            ingested += 1
            print(json.dumps({"status": "ingested", "session_id": sid}))
        else:
            # Failed — do NOT mark processed; the next poll retries it.
            print(json.dumps({"status": "ingest_failed", "session_id": sid, "rc": rc}))
    print(json.dumps({"status": "poll_done", "discovered": len(intakes),
                      "ingested": ingested, "already_processed": skipped}))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("ingest", help="pull a finished intake + write run dir + start the presentation dept")
    i.add_argument("--worker-url", required=True)
    i.add_argument("--session-id", required=True, help="the intake_session_id from the app")
    i.add_argument("--run-dir", required=True, help="deck run directory to stamp")
    i.add_argument("--verbose", action="store_true")
    i.set_defaults(func=cmd_ingest)
    p = sub.add_parser("poll", help="list finished intakes and ingest each once")
    p.add_argument("--worker-url", required=True)
    p.add_argument("--run-dir", required=True, help="deck run directory to stamp each intake under")
    p.add_argument("--poll-ledger", required=True, help="path to the poll ledger (processed session ids)")
    p.add_argument("--per-session-dirs", action="store_true",
                   help="stamp each intake under <run-dir>/<session-id>/ instead of a single run dir")
    p.add_argument("--verbose", action="store_true")
    p.set_defaults(func=cmd_poll)
    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
