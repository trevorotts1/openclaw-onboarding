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


def _load_by_file(mod_name: str, file_name: str) -> object | None:
    """Locate a sanctioned scripts/ sibling module (cc_board.py,
    operator_requester.py, ...) by file path across the candidate roots this
    bridge can run from -- a checkout, a deployed box, or PRESENTATIONS_SCRIPTS
    override. Same technique for every such module so all of them resolve the
    SAME box/checkout, never a mix."""
    for root in (
        pathlib.Path(os.environ.get("PRESENTATIONS_SCRIPTS", "")) if os.environ.get("PRESENTATIONS_SCRIPTS") else HERE.parent,
        HERE.parent.parent / "scripts",
        pathlib.Path.home() / ".openclaw" / "workspace" / "departments" / "Presentations" / "scripts",
    ):
        cand = root / file_name
        if cand.is_file():
            import importlib.util as _u
            spec = _u.spec_from_file_location(mod_name, cand)
            if spec and spec.loader:
                mod = _u.module_from_spec(spec)
                spec.loader.exec_module(mod)
                return mod
    return None


def _load_cc_board() -> object | None:
    """Locate cc_board.py (the Command Center ingest helper) if available."""
    return _load_by_file("cc_board", "cc_board.py")


def _load_operator_requester() -> object | None:
    """Locate operator_requester.py (FIX F19's sanctioned OPERATOR chat-id
    fallback) if available. Returns None -- never raises -- when the module
    is not reachable from any candidate root; callers treat that exactly
    like 'nothing configured' (see resolve_operator_chat_id()'s own
    never-fabricate contract)."""
    return _load_by_file("operator_requester", "operator_requester.py")


# FIX F19: mirrors cc_board.py's _REQUESTER_ENV_KEYS / deck-intake-driver.py's
# _REQUESTER_ENV_KEYS byte-for-byte. Before this fix, this bridge was the ONLY
# intake path reading a DIFFERENT env var name (PRESENTER_CHAT_ID) for the
# identical purpose -- an app-submitted session and a CLI/dispatcher-driven
# session silently disagreed on where the requester lives, the exact
# divergent-intake-path disease behind FAULT-02/05/11. The canonical keys are
# now checked FIRST so both paths agree; PRESENTER_CHAT_ID is kept as a
# back-compat alias (see cmd_ingest() below) so an existing deployment's env
# export keeps working.
_REQUESTER_ENV_KEYS = (
    "PRESENTATION_REQUESTER_CHAT_ID",
    "ROUTE_PRES_REQUESTER_CHAT_ID",
    "MC_ROUTE_REQUESTER_CHAT_ID",
)


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


def stamp_requester(intake: dict, env: dict | None = None,
                    load_operator_requester=_load_operator_requester) -> dict:
    """Stamp requester_chat_id/requester_channel onto `intake` IN PLACE from a
    legitimate source, and return it (for easy call-site chaining). Never
    overwrites a value the app itself already supplied. Extracted to its own
    function (FIX F19) so this resolution order is unit-testable without
    driving the network-calling parts of cmd_ingest().

    Order (see operator_requester.py's docstring for the full rationale):
      1. the canonical chat-surface env vars every other intake path already
         reads (_REQUESTER_ENV_KEYS above -- the real client's identity, when
         a dispatcher exported it) -- this is the RIGHT source for a real
         client order and always wins when present;
      2. PRESENTER_CHAT_ID, kept ONLY as a back-compat alias for an existing
         deployment's env export (this bridge used to read ONLY this name --
         see the fix/deck-type-routing-bypass follow-up this replaces);
      3. the sanctioned OPERATOR fallback (operator_requester.py) for a
         genuinely operator-run app session that has neither -- never a
         client identity, never invented.
    `load_operator_requester` is injectable for tests (default: the real
    file-path loader above).
    """
    src_env = env if env is not None else os.environ
    if str(intake.get("requester_chat_id") or "").strip():
        return intake
    chat_id = ""
    channel = ""
    for key in _REQUESTER_ENV_KEYS:
        val = str(src_env.get(key) or "").strip()
        if val:
            chat_id = val
            break
    if not chat_id:
        chat_id = str(src_env.get("PRESENTER_CHAT_ID") or "").strip()
    if chat_id:
        channel = (
            str(src_env.get("PRESENTATION_REQUESTER_CHANNEL") or "").strip()
            or str(src_env.get("PRESENTER_CHANNEL") or "").strip()
            or "telegram"
        )
    else:
        op_mod = load_operator_requester()
        if op_mod is not None and hasattr(op_mod, "resolve_operator_chat_id"):
            chat_id, channel = op_mod.resolve_operator_chat_id()
    if chat_id:
        intake["requester_chat_id"] = chat_id
        intake["requester_channel"] = channel or "telegram"
    return intake


def _load_presentation_job():
    """Locate the presentation_job package root (the scripts/ directory that
    CONTAINS it) the same way every other sanctioned sibling is resolved here:
    by file path across the candidate roots, never a mix of boxes/checkouts.
    Candidate layouts covered:
      PRESENTATIONS_SCRIPTS override (deployed boxes);
      <presentations>/scripts (this checkout: interview-app sits under
      presentations/intake/, so presentations/ is HERE x3 parents up);
      <intake>/scripts and the OC workspace path (other deployed shapes).
    Returns the imported package or None -- never raises (a box without the
    department scripts installed keeps its pre-FIX-61 behavior)."""
    for root in (
        pathlib.Path(os.environ["PRESENTATIONS_SCRIPTS"]) if os.environ.get("PRESENTATIONS_SCRIPTS") else None,
        HERE.parent.parent.parent / "scripts",
        HERE.parent.parent / "scripts",
        pathlib.Path.home() / ".openclaw" / "workspace" / "departments" / "Presentations" / "scripts",
    ):
        if root is None:
            continue
        if (root / "presentation_job" / "launcher.py").is_file():
            if str(root) not in sys.path:
                sys.path.insert(0, str(root))
            try:
                import presentation_job  # noqa: F401
                return presentation_job
            except ImportError:
                continue
    return None


def _dispatch_engine_under_lease(run_dir: pathlib.Path, intake: dict,
                                 session_id: str, verbose: bool = False) -> dict:
    """FIX 61: a staged submission becomes a RUNNING ENGINE within one poll
    interval, with no human action -- this bridge is not just the card-writer
    any more. After the run-dir record is stamped (working/copy/intake.json,
    the file launcher.dispatch_new's --new path reads via --intake), acquire
    the run lease (FIX 18) with THIS BRIDGE named as holder and call
    launcher.dispatch_new() while it is held, releasing it in a finally.

    The lease document (working/.lease.json) names the bridge as holder, so
    the FIX 61 proof can read it and so the intake poll / supervisor / engine
    can never double-launch the same run concurrently: acquire() returns None
    when a live holder keeps the run, and that is reported, never swallowed
    into a fake success.

    Deck type comes from the GROUNDED intake record (intake_writer already
    corrected it against the client's own presentation_type answer);
    vocab.normalize_presentation_type() -- the same single-sourced resolver
    the door, poll, engine, and launcher share -- accepts both the deck_type
    name ("signature_presentation" -> "signature") and the canonical value,
    and dispatch_new refuses loudly (DISPATCH_UNKNOWN_DECK_TYPE) on anything
    else, so an unresolvable type is a loud failure, never a silent webinar.

    Never raises: the return dict carries the outcome for the caller's own
    status line. A launcher refusal (capacity unmeasured, notify unconfigured,
    OCR missing, ...) leaves the staged submission staged -- the poll retries
    it on the next interval, exactly the pre-FIX-61 staged semantics, minus
    the human action that used to sit between the two."""
    out: dict = {"dispatched": False, "detail": "presentation_job not reachable"}
    pj = _load_presentation_job()
    if pj is None:
        return out
    # presentation_job/__init__.py is a docstring only -- launcher and lease are
    # SUBMODULES, never package attributes. Resolve them as attributes first
    # (an injected stand-in in tests, or a future __init__ that re-exports
    # them), then fall back to importing the submodules by name -- attribute
    # access on the bare package alone would hand back the "presentation_job
    # incomplete" report on every real box.
    launcher = getattr(pj, "launcher", None)
    lease_mod = getattr(pj, "lease", None)
    if launcher is None or lease_mod is None:
        try:
            import importlib as _importlib
            if launcher is None:
                launcher = _importlib.import_module("presentation_job.launcher")
            if lease_mod is None:
                lease_mod = _importlib.import_module("presentation_job.lease")
        except ImportError as exc:
            out["detail"] = f"presentation_job incomplete: {exc}"
            return out

    deck_type = str(intake.get("deck_type") or "").strip()
    client = str(intake.get("requester_chat_id") or intake.get("intake_session_id")
                 or session_id or "").strip() or "operator"
    holder = {"who": "intake-bridge", "session_id": session_id}
    lease = None
    try:
        lease = lease_mod.acquire(run_dir, holder=holder,
                                  ttl_s=lease_mod.DEFAULT_TTL_S, wait_s=30.0)
        if lease is None:
            doc = lease_mod.read(run_dir) or {}
            out["detail"] = (
                "lease held by pid {pid} on host {host}; dispatch skipped, "
                "session left staged for the next poll".format(
                    pid=doc.get("pid"), host=doc.get("host")))
            return out
        pid = launcher.dispatch_new(str(run_dir), client=client,
                                    deck_type=deck_type, background=True)
        out["pid"] = pid
        out["deck_type"] = deck_type
        if isinstance(pid, int) and pid > 0:
            out["dispatched"] = True
            out["detail"] = f"engine dispatched (pid {pid})"
        elif pid == launcher.DISPATCH_UNKNOWN_DECK_TYPE:
            out["detail"] = (f"dispatch refused (AF-DECK-TYPE-UNKNOWN): deck_type "
                             f"{deck_type!r} does not resolve through vocab -- "
                             "session left staged for the next poll")
        else:
            codes = {
                launcher.DISPATCH_CAPACITY_REFUSED: "AF-CAPACITY-UNMEASURED",
                launcher.DISPATCH_NOTIFY_REFUSED: "AF-NOTIFY-UNCONFIGURED",
                launcher.DISPATCH_OCR_REFUSED: "AF-OCR-ENGINE-MISSING",
                launcher.DISPATCH_CREDIT_REFUSED: "AF-CREDIT-PREFLIGHT",
                launcher.DISPATCH_MODE_INVALID: "AF-MODE-INVALID",
                -2: "already running",
                -3: "already DONE",
                -1: "spawn failure",
            }
            code = codes.get(pid, "refused")
            out["detail"] = (f"dispatch refused ({code}, rc={pid}) -- nothing "
                             "spawned; session left staged for the next poll")
        return out
    except Exception as exc:  # noqa: BLE001 -- a dispatch failure must never break ingest
        out["detail"] = f"dispatch error: {type(exc).__name__}: {exc}"
        return out
    finally:
        if lease is not None:
            try:
                lease_mod.release(lease)
            except Exception:  # noqa: BLE001
                pass


def cmd_ingest(args) -> int:
    intake_payload = _fetch_intake(args)
    intake = intake_payload.get("intake") or intake_payload
    intake.setdefault("intake_session_id", args.session_id)

    # fix/deck-type-routing-bypass follow-up, extended by FIX F19: this
    # bridge needs a requester_chat_id stamped into `intake` itself, here,
    # BEFORE intake_writer.write_intake_file() below persists it as
    # working/copy/intake.json -- the ONE file the engine's
    # resolve_intake.py reads -- or an app-submitted deck's engine job could
    # never report to the client who submitted it. See stamp_requester()'s
    # own docstring for the full resolution order.
    stamp_requester(intake)

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

    # 1b) FIX 61: a staged submission becomes a running engine within one
    #     poll interval with no human action. The intake.json is on disk
    #     (step 1) -- exactly what launcher.dispatch_new's --new path reads
    #     -- so dispatch the engine NOW, under the run lease (working/.lease.json
    #     names THIS BRIDGE as holder), before the kanban card. Best-effort
    #     and never fatal: a refusal (lease held, capacity unmeasured, ...) is
    #     reported and the session stays staged for the next poll to retry.
    dispatch_out = _dispatch_engine_under_lease(
        run_dir, intake, args.session_id, verbose=bool(getattr(args, "verbose", False)))
    if args.verbose or not dispatch_out.get("dispatched"):
        print(json.dumps({"status": "dispatch",
                          "session_id": args.session_id,
                          **dispatch_out}),
              file=(sys.stderr if not dispatch_out.get("dispatched") else sys.stdout))

    # 2) Trigger the presentation department start (kanban card, no shortcuts).
    cc = _load_cc_board()
    if cc is not None and hasattr(cc, "ingest_deck_task"):
        brief = intake.get("deck_brief") or {}
        title = brief.get("OFFER_NAME") or intake.get("intake_session_id") or args.session_id
        desc = f"Intake captured by the Presentation Interview app ({args.session_id}).\n" + json.dumps(intake.get("deck_brief") or intake.get("answers") or {}, indent=2)
        # FIX F19: use the value already resolved onto `intake` above (canonical
        # env vars -> PRESENTER_CHAT_ID back-compat -> operator fallback) instead
        # of re-reading raw PRESENTER_CHAT_ID -- so CC-board registration and the
        # engine's own working/copy/intake.json never disagree on the requester.
        task_id = cc.ingest_deck_task(
            run_dir,
            deck_slug=args.session_id,
            title=f"Deck — {title}",
            description=desc,
            priority="medium",
            requester_chat_id=intake.get("requester_chat_id", ""),
        )
        if task_id:
            print(json.dumps({"status": "dept_started", "session_id": args.session_id, "task_id": task_id}))
            return 0
        # FIX F12: a None here means NO kanban card exists — returning 0 lets
        # cmd_poll mark the session processed and the card is silently never
        # created, never retried. Return nonzero so poll leaves the session
        # unprocessed and retries on the next pass.
        print(json.dumps({"status": "dept_start_failed", "session_id": args.session_id,
                          "note": "cc_board.ingest_deck_task returned None (board URL unset or transport failure); session left for retry"}),
              file=sys.stderr)
        return 5

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
        # FIX F13: one poison session (malformed payload, transport crash) used
        # to raise out of the loop and kill the whole poll batch — every other
        # waiting session behind it was never attempted. Contain the failure to
        # the single session; unprocessed sessions retry on the next poll.
        try:
            rc = cmd_ingest(sub)
        except Exception as exc:  # noqa: BLE001 — poll must survive any single bad session
            print(json.dumps({"status": "ingest_crashed", "session_id": sid,
                              "error": f"{type(exc).__name__}: {exc}"}), file=sys.stderr)
            continue
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
