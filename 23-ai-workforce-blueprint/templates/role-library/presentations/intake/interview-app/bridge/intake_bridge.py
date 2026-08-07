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


def _http(method: str, url: str, *, token: str | None = None, body: dict | None = None,
          timeout: int = 20) -> tuple[int, dict]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("content-type", "application/json")
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

    # 1) Write the run-dir record (dept-format intake.json + completed ledger).
    if intake_writer is not None:
        run_dir = pathlib.Path(args.run_dir).expanduser().resolve()
        run_dir.mkdir(parents=True, exist_ok=True)
        intake_writer.write_intake_file(run_dir, intake)
        intake_writer.write_ledger(run_dir, intake)
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


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("ingest", help="pull a finished intake + write run dir + start the presentation dept")
    i.add_argument("--worker-url", required=True)
    i.add_argument("--session-id", required=True, help="the intake_session_id from the app")
    i.add_argument("--run-dir", required=True, help="deck run directory to stamp")
    i.add_argument("--verbose", action="store_true")
    i.set_defaults(func=cmd_ingest)
    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
