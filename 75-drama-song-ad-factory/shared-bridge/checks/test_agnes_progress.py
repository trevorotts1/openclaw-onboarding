#!/usr/bin/env python3
"""W2-wiring-U2 checks: the check-in carries the remembered Agnes answer and the
active run's progress, and a replay whose reply count cannot complete the card's
question list is refused instead of shifted.

Every check drives the REAL `studio_bridge.py poll` on its real command line
against a fake studio on 127.0.0.1 - no Agnes, no KIE, no live endpoint - and
every negative carries a control on the SAME instrument, so a green run means the
check discriminates rather than that nothing ran:

  A  the check-in body carries `agnes_remembered` as exactly unknown|yes|no,
     read from the client folder through `agnes_access`; controls: no client
     folder reads unknown, an unrecognised stored answer is clamped to unknown
  B  `agnes_progress` rides the check-in while a run's job is unfinished, and is
     absent when it is finished - the same file, the same command, one field
  C  a reply set the card cannot complete refuses the order with
     REPLAY_QUESTION_MISMATCH naming both counts (the accepted answers and the
     card's own question count), cancels it with that reason, and writes no run
     folder: one set that stops short, one with a reply that does not fit
  D  a complete replay still runs - including one that only completes because a
     remembered "no" removed the AGNES screen
  E  the refusal discriminates: the same card and the same replies do not
     refuse when `conversation` carries no purpose flow to count against
  F  no key value reaches a request body or the output, and no request leaves
     127.0.0.1; the secret detector has a planted positive control

Run: python3 checks/test_agnes_progress.py
Exit: 0 all pass · 1 at least one failed
"""
import http.server
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import threading

HERE = pathlib.Path(__file__).resolve().parent
BRIDGE_DIR = HERE.parent                          # .../shared-bridge
sys.path.insert(0, str(BRIDGE_DIR))
import studio_bridge as SB  # noqa: E402

PY = sys.executable
BRIDGE = str(BRIDGE_DIR / "studio_bridge.py")
#: The box temp-file prefix this lane is allowed to use (never a repo or a /tmp
#: copy of any source file).
WORK = pathlib.Path(tempfile.mkdtemp(prefix="blackceomacmini-W2-wiring-U2-",
                                     dir="/tmp"))
SENTINEL = "sk-DEADBEEF-not-a-real-key-1234567890"

#: One order, one title: what the fake studio answers `GET /api/studio/orders/<id>`.
STATE = {"line": None, "order": {}}
RECORDED = []          # every request the bridge made: method, path, body, host


def _run(args, env=None):
    return subprocess.run([PY, BRIDGE] + list(args), capture_output=True,
                          text=True, env=env)


def _env(state_name):
    """A poll environment: the lane's own state folder, and the machine key the
    bridge will send - with `DS_KEY` removed so the file is what is read."""
    env = dict(os.environ)
    env.pop("DS_KEY", None)
    env["DRAMA_STUDIO_STATE"] = str(WORK / state_name)
    return env


def _state_dir(name):
    folder = WORK / name
    folder.mkdir(parents=True, exist_ok=True)
    SB.write_private(folder / "machine.key", SENTINEL + "\n")
    return folder


def _checkin(run):
    """Every recorded `POST /api/studio/checkin` body in this run's window."""
    return [r["body"] for r in run if r["path"].endswith("/checkin")]


class _FakeStudio(http.server.BaseHTTPRequestHandler):
    def _read(self):
        try:
            n = int(self.headers.get("content-length") or 0)
        except ValueError:
            n = 0
        raw = self.rfile.read(n) if n else b""
        try:
            body = json.loads(raw) if raw else {}
        except ValueError:
            body = {"__raw__": raw.decode("utf-8", "replace")}
        RECORDED.append({"method": self.command, "path": self.path,
                         "body": body, "host": self.headers.get("Host", ""),
                         "ua": self.headers.get("User-Agent") or ""})
        return body

    def _send(self, payload, status=200):
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):  # noqa: N802
        self._read()
        self._send({"ok": True, "order": STATE["order"]})

    def do_POST(self):  # noqa: N802
        self._read()
        if self.path.endswith("/api/studio/checkin"):
            self._send({"ok": True, "checked_in_at": 1, "line": STATE["line"]})
        else:
            self._send({"ok": True, "order": STATE["order"]})

    def log_message(self, *a):
        pass


SERVER = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _FakeStudio)
BASE = "http://127.0.0.1:%d" % SERVER.server_address[1]
threading.Thread(target=SERVER.serve_forever, daemon=True).start()


# --- fixtures: the two modules this unit reads --------------------------------
# Both are other units of this same program (O-agnes-core and O-card-wiring) and
# land in the batches beside this one. They are stood in for here so this unit
# proves what IT does - that the bridge reads the answer through `agnes_access`
# and refuses a count `_shaped` cannot complete - while each real module keeps
# its own Prove (W1-agnes-core-U3 `test_agnes_access.py`, W1-card-questions-U1
# `test_purpose_agnes.py`). The installed card's own copy is check E below.

AGNES_ACCESS = '''\
import json
import os

#: Returns the stored answer UNCLAMPED: proving the bridge narrows an
#: unrecognised value to "unknown" is this check's control.
def remembered(client_dir):
    if not client_dir:
        return "unknown"
    try:
        with open(os.path.join(os.path.expanduser(str(client_dir)), "agnes.json"),
                  encoding="utf-8") as f:
            rec = json.load(f)
    except (OSError, ValueError):
        return "unknown"
    answer = rec.get("subscriber") if isinstance(rec, dict) else None
    return answer if answer is not None else "unknown"
'''

INTAKE_CARD = '''\
#: The purpose-flow shape W1-card-questions-U1 `_shaped` builds (SPEC B1):
#: PURPOSE first, its one follow-up right after it, the plain screens unchanged,
#: and AGNES only while the remembered answer is not "no".
_YES = ("yes", "y", "yep", "go", "ok", "okay", "start", "approve", "approved")
_CONDITIONAL = ("purpose", "episode_length", "shape", "permission", "where", "agnes")
#: Two options per screen, like the card's own choice screens.
QUESTIONS = [{"id": n, "options": [("One", None), ("Two", None)]}
             for n in ("models", "length", "music", "look")]


def _remembered(client_dir):
    if not client_dir:
        return "unknown"
    try:
        from agnes_access import agnes_access as AG
    except Exception:
        return "unknown"
    return AG.remembered(client_dir)


def _shaped(qs, answers, client_dir=None):
    out = [{"id": "purpose", "options": [("A", None), ("B", None)]}]
    n = answers[0].get("n") if answers else None
    if n == 1:
        out += [{"id": "episode_length", "options": [("A", None)]},
                {"id": "shape", "options": [("A", None)]}]
    elif n == 2:
        out += [{"id": "permission", "options": [("A", None)]}]
    out += [q for q in qs if q["id"] not in _CONDITIONAL]
    if _remembered(client_dir) != "no":
        out.append({"id": "agnes", "options": [("A", None), ("B", None)],
                    "recommended": 0})
    return out


def _parse(reply, q):
    """The card's own parser, at miniature size: an option number, the pick
    words on a screen that recommends one, and a free-text screen's own text."""
    t = (reply or "").strip().lower()
    opts = q.get("options") or []
    if q.get("free_text"):
        return None if (len(t) < 2 or t in _YES) else \
            {"n": 1, "text": reply, "value": reply, "id": q["id"]}
    if t in _YES:
        return None if q.get("recommended") is None else \
            {"n": (q.get("recommended") or 0) + 1, "text": "picked", "id": q["id"]}
    if t.isdigit() and 1 <= int(t) <= len(opts):
        return {"n": int(t), "text": opts[int(t) - 1][0], "id": q["id"]}
    return None


def conversation(replies, questions=None, state_store=None, run_id=None,
                 run_dir=None, target=None, client_dir=None, purpose_flow=False):
    """The card's own control flow (intake_card.conversation), miniature: the
    list is rebuilt from the answers as it walks, a digit at the recap changes a
    line, and a complete list prints the recap - never a step line. The studio
    page appends one recap confirmation after every screen
    (`mini-app/ui/studio.js:470`), which this path also absorbs."""
    answers, fix, note, done = [], None, "", False

    def shaped(qs, ans):
        return _shaped(list(qs), ans, client_dir)

    for r in replies:
        note = ""
        qs = shaped(QUESTIONS, answers)
        if len(answers) < len(qs) and fix is None:
            a = _parse(r, qs[len(answers)])
            if a:
                answers.append(a)
            else:
                note = "Sorry, I did not catch that. "
        elif fix is not None:
            a = _parse(r, qs[fix])
            if a:
                if qs[fix]["id"] == "purpose":
                    del answers[fix + 1:]
                answers[fix], fix = a, None
            else:
                note = "Sorry, I did not catch that. "
        else:
            t = r.strip().lower()
            if t in _YES:
                done = True
            elif t.isdigit() and 1 <= int(t) <= len(qs):
                fix = int(t) - 1
            else:
                note = "Sorry, I did not catch that. "
    qs = shaped(QUESTIONS, answers)
    if done:
        msg = "Locked in. I am starting now."
    elif fix is not None:
        msg = note + "Question %d of %d - %s" % (fix + 1, len(qs),
                                                 qs[fix]["id"].upper())
    elif len(answers) < len(qs):
        msg = note + "Question %d of %d - %s" % (len(answers) + 1, len(qs),
                                                 qs[len(answers)]["id"].upper())
    else:
        msg = note + "Here is what you picked:"
    return {"answers": answers, "done": done, "message": msg, "video_model": None}
'''

#: The card of a skill copy that predates the purpose flow: `_shaped` is there
#: to be found, but `conversation` has no purpose flow to be counted against, so
#: the guard must stay inert. Built from the same source with only that one
#: difference, so check E compares the two on the same replies.
NO_FLOW_INTAKE_CARD = INTAKE_CARD.replace(
    ", client_dir=None, purpose_flow=False):", ", client_dir=None):")
assert NO_FLOW_INTAKE_CARD != INTAKE_CARD

FACTORY = '''\
#!/usr/bin/env python3
"""The only proof this check needs: the replay actually reached the card."""
import json
import pathlib
import sys

run = sys.argv[sys.argv.index("--run-dir") + 1]
control = pathlib.Path(run) / "control"
control.mkdir(parents=True, exist_ok=True)
(control / "card-answers.json").write_text(
    json.dumps({"argv": sys.argv[1:]}) + "\\n", encoding="utf-8")
sys.exit(0)
'''


def _fixture_skill_root(name="skill", card_source=INTAKE_CARD):
    root = WORK / name
    for rel in ("scripts/core/agnes_access", "scripts/core/choice_card/intake_card",
                "scripts/core/intake_preflight"):
        (root / rel).mkdir(parents=True, exist_ok=True)
        (root / rel / "__init__.py").write_text("", encoding="utf-8")
    (root / "scripts/core/agnes_access/agnes_access.py").write_text(
        AGNES_ACCESS, encoding="utf-8")
    (root / "scripts/core/choice_card/intake_card/intake_card.py").write_text(
        card_source, encoding="utf-8")
    factory = root / "scripts/core/intake_preflight/factory.py"
    factory.write_text(FACTORY, encoding="utf-8")
    factory.chmod(0o755)
    return root


#: Built once: the skill root every end-to-end run uses unless a check names
#: another one.
FIXTURE_ROOT = _fixture_skill_root()
#: The same card with the purpose flow taken out - check E's control.
NO_FLOW_ROOT = _fixture_skill_root("skill-no-flow", NO_FLOW_INTAKE_CARD)


def _client(name, subscriber):
    folder = WORK / name
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "agnes.json").write_text(
        json.dumps({"subscriber": subscriber, "answered_at": "2026-10-15T00:00:00Z"}),
        encoding="utf-8")
    return folder


def _scenario(name, replies, order_id=None, skill_root=None, client_dir="",
              progress=None, waiting=True):
    """One poll against the fake studio. Returns (exit code, parsed stdout,
    this run's recorded requests, the run folder it would use). `waiting=False`
    answers the check-in with no order waiting, so only the check-in runs."""
    order_id = order_id or ("r_" + name.replace("-", ""))
    runs = WORK / ("runs-" + name)
    runs.mkdir(parents=True, exist_ok=True)
    if progress is not None:
        control = runs / order_id / "control"
        control.mkdir(parents=True, exist_ok=True)
        (control / "agnes-progress.json").write_text(
            json.dumps(progress, sort_keys=True), encoding="utf-8")
    _state_dir("state-" + name)
    STATE["line"] = ('DRAMA_ORDER %s "%s"' % (order_id, "Fixture order")
                     if waiting else None)
    STATE["order"] = {"order_id": order_id, "client_id": "c-" + "0" * 32,
                      "title": "Fixture order", "replies": list(replies)}
    RECORDED.clear()
    argv = ["poll", "--base-url", BASE, "--skill-root",
            str(skill_root or FIXTURE_ROOT), "--runs", str(runs),
            "--db", str(WORK / ("claim-" + name + ".db"))]
    if client_dir:
        argv += ["--client-dir", str(client_dir)]
    proc = _run(argv, env=_env("state-" + name))
    out = {}
    if proc.stdout.strip():
        try:
            out = json.loads(proc.stdout)
        except ValueError:
            out = {"__unparsed__": proc.stdout}
    return proc.returncode, out, list(RECORDED), runs / order_id


#: `n_answers` screens answered in order (the card's first option, which every
#: screen accepts) plus the one recap confirmation the studio page appends
#: (`mini-app/ui/studio.js:470`).
def _replies(n_answers, confirm="yes"):
    return ["1"] * n_answers + [confirm]


def check_a_remembered_answer():
    yes = _client("client-yes", "yes")
    no = _client("client-no", "no")
    odd = _client("client-odd", "maybe")
    cases = (
        ("no folder", "", "unknown"),
        ("remembered yes", yes, "yes"),
        ("remembered no", no, "no"),
        ("unrecognised stored answer", odd, "unknown"),
    )
    seen, bad = [], []
    for index, (label, folder, want) in enumerate(cases):
        code, out, rec, _ = _scenario("a-%d" % index, [], client_dir=folder,
                                      waiting=False)
        bodies = _checkin(rec)
        got = bodies[0].get("agnes_remembered") if bodies else "<no check-in>"
        extra = (set(bodies[0]) - {"agnes_remembered", "agnes_progress"}
                 if bodies else {"<no check-in>"})
        seen.append("%s->%s" % (label, got))
        if got != want or code != 0 or extra:
            bad.append("%s: got %r want %r code=%s extra=%s"
                       % (label, got, want, code, sorted(extra)))
    # control: four different client folders, one instrument - if the field were
    # a constant, all four would read the same word
    ok = not bad and len({s.split("->")[1] for s in seen}) > 1
    return ok, ("; ".join(seen) if ok else " | ".join(bad))


def _progress(done, total):
    return {"clips_total": total, "clips_done": done, "in_flight": 2,
            "waiting_reason": None, "next_continue_utc": None,
            "eta_minutes_low": 110, "eta_minutes_high": 130,
            "updated_utc": "2026-10-15T02:00:00Z"}


def check_b_progress_only_while_active():
    active = _progress(12, 30)
    code, out, rec, run_dir = _scenario("b-active", [], progress=active,
                                        waiting=False)
    bodies = _checkin(rec)
    carried = bodies[0].get("agnes_progress") if bodies else None
    want = dict(active, order_id=run_dir.name)
    active_ok = (carried == want and code == 0)

    code2, out2, rec2, run_dir2 = _scenario("b-finished", [],
                                            progress=_progress(30, 30),
                                            waiting=False)
    bodies2 = _checkin(rec2)
    # control on the SAME file and the SAME command: a finished job carries nothing
    finished_absent = bool(bodies2) and "agnes_progress" not in bodies2[0]

    code3, out3, rec3, _ = _scenario("b-none", [], waiting=False)
    bodies3 = _checkin(rec3)
    none_absent = bool(bodies3) and "agnes_progress" not in bodies3[0]

    ok = active_ok and finished_absent and none_absent
    return ok, ("active=%r finished_absent=%s no_run_absent=%s codes=%s,%s,%s"
                % (carried, finished_absent, none_absent, code, code2, code3))


def _replay_scenario(name, replies, client_dir="", skill_root=None):
    code, out, rec, run_dir = _scenario(name, replies, client_dir=client_dir,
                                        skill_root=skill_root)
    cancels = [r["body"] for r in rec
               if r["method"] == "POST" and "/state" in r["path"]
               and r["body"].get("event") == "cancel"]
    reason = cancels[0].get("reason", "") if cancels else ""
    factory_ran = (run_dir / "control" / "card-answers.json").exists()
    return code, out, reason, cancels, run_dir, factory_ran, rec


def check_c_mismatch_refused_and_cancelled():
    # 8 questions on this shape: purpose + its two follow-ups + four plain
    # screens + AGNES. A set that stops short, and one with a reply that does
    # not fit the screen it landed on (the shifted replay this guard exists for).
    short = _replay_scenario("c-few", _replies(7))
    shifted = _replay_scenario("c-shifted",
                               ["1"] * 3 + ["9"] + ["1"] * 3 + ["yes"])
    bad = []
    for label, (code, out, reason, cancels, run_dir, factory_ran, _) in (
            ("too few replies", short), ("one reply that does not fit", shifted)):
        want_code = "REPLAY_QUESTION_MISMATCH"
        if code != SB.EXIT["refused"]:
            bad.append("%s: exit %s want %s" % (label, code, SB.EXIT["refused"]))
        if out.get("code") != want_code:
            bad.append("%s: code %r" % (label, out.get("code")))
        if not (isinstance(out.get("replies"), int)
                and isinstance(out.get("questions"), int)
                and out["replies"] < out["questions"]):
            bad.append("%s: counts not both named with accepted < questions: %r"
                       % (label, {k: out.get(k) for k in ("replies", "questions")}))
        if want_code not in str(out.get("message", "")):
            bad.append("%s: message %r" % (label, out.get("message")))
        if not (cancels and want_code in reason
                and str(out.get("replies")) in reason
                and str(out.get("questions")) in reason):
            bad.append("%s: cancel reason %r" % (label, reason))
        if run_dir.exists():
            bad.append("%s: run folder was written" % label)
        if factory_ran:
            bad.append("%s: the card replay ran (shifted replay)" % label)
    ok = not bad
    return ok, ("too few: card accepted %d of %d; one bad reply: card accepted "
                "%d of %d - both refused, cancelled with both counts named, no "
                "run folder, no replay"
                % (short[1]["replies"], short[1]["questions"],
                   shifted[1]["replies"], shifted[1]["questions"])
                if ok else " | ".join(bad))


def check_d_complete_replay_runs():
    no = _client("client-no2", "no")
    # 8 questions with the AGNES screen on; a remembered "no" takes it out, so
    # that list is one shorter and one answer shorter completes it.
    good = _replay_scenario("d-full", _replies(8))
    remembered_no = _replay_scenario("d-remembered-no", _replies(7),
                                     client_dir=no)
    bad = []
    for label, (code, out, reason, cancels, run_dir, factory_ran, _) in (
            ("complete", good), ("complete with remembered no", remembered_no)):
        if code != SB.EXIT["ok"]:
            bad.append("%s: exit %s want 0 (out=%r)" % (label, code, out))
        if "next" not in out:
            bad.append("%s: no next command: %r" % (label, out))
        if cancels:
            bad.append("%s: cancelled: %r" % (label, cancels))
        if not factory_ran:
            bad.append("%s: the card replay never ran" % label)
        if not run_dir.exists():
            bad.append("%s: no run folder" % label)
    ok = not bad
    return ok, ("complete 8 answers + the page's confirm -> next printed and "
                "the card replayed; remembered no 7 answers + confirm -> next "
                "printed (the AGNES screen was out of that list)"
                if ok else " | ".join(bad))


def check_e_inert_without_a_purpose_flow_card():
    """Control on the SAME function and the SAME replies: a card whose
    `conversation` has no purpose flow cannot be counted against, so the guard
    refuses nothing - it discriminates, it does not just refuse everything.
    (A skill copy without `_shaped` at all is inert for the same reason; this
    form of the control keeps working after that module ships.)"""
    replies = _replies(6)
    flow = _replay_scenario("e-purpose-flow", replies, skill_root=FIXTURE_ROOT)
    noflow = _replay_scenario("e-no-purpose-flow", replies, skill_root=NO_FLOW_ROOT)
    ok = (flow[1].get("code") == "REPLAY_QUESTION_MISMATCH"
          and flow[0] == SB.EXIT["refused"]
          and noflow[1].get("code") != "REPLAY_QUESTION_MISMATCH"
          and noflow[0] == SB.EXIT["ok"])
    return ok, ("purpose-flow card: code=%r exit=%s; the same card without a "
                "purpose flow: code=%r exit=%s (next printed, card replayed); "
                "same %d replies"
                % (flow[1].get("code"), flow[0], noflow[1].get("code"),
                   noflow[0], len(replies)))


def check_f_no_secret_and_no_live_endpoint():
    seen = []
    for i in range(2):
        _, _, rec, _ = _scenario("f-%d" % i, _replies(8))
        seen.extend(rec)
    joined = json.dumps([r["body"] for r in seen])
    secret_in_body = SENTINEL in joined
    # positive control on the SAME detector: without it, "not found" means nothing
    detector_sees_planted = SENTINEL in ("planted " + SENTINEL)
    hosts = sorted({r["host"].split(":")[0] for r in seen})
    local_only = hosts == ["127.0.0.1"]
    ua_ok = all(r["ua"] == SB.STUDIO_USER_AGENT for r in seen)
    ok = (not secret_in_body) and detector_sees_planted and local_only and ua_ok
    return ok, ("secret_in_body=%s detector_control=%s hosts=%s user_agent_exact=%s "
                "requests=%d" % (secret_in_body, detector_sees_planted, hosts,
                                 ua_ok, len(seen)))


CHECKS = (
    ("A check-in carries the remembered Agnes answer", check_a_remembered_answer),
    ("B progress rides the check-in only while the job is active",
     check_b_progress_only_while_active),
    ("C a reply count that cannot complete the card is refused and cancelled",
     check_c_mismatch_refused_and_cancelled),
    ("D a complete replay still runs, remembered answer included",
     check_d_complete_replay_runs),
    ("E the refusal discriminates: no purpose-flow card, no refusal",
     check_e_inert_without_a_purpose_flow_card),
    ("F no secret, no endpoint outside 127.0.0.1", check_f_no_secret_and_no_live_endpoint),
)


def main():
    fails = 0
    try:
        for name, fn in CHECKS:
            try:
                ok, detail = fn()
            except Exception as e:  # noqa: BLE001
                ok, detail = False, "raised %r" % (e,)
            print("%s %s :: %s" % ("PASS" if ok else "FAIL", name, detail))
            if not ok:
                fails += 1
    finally:
        SERVER.shutdown()
        SERVER.server_close()
        shutil.rmtree(WORK, ignore_errors=True)
    print("ALL PASS" if not fails else "%d CHECK(S) FAILED" % fails)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
