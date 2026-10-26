#!/usr/bin/env python3
"""S75-T13 (S75-A13): the emergency owner is PER-INSTALL, never a hard-coded name.

Boss rule 2026-10-26 (D-9/D-10): an install config value wins; an operator-box
install with none defaults to "Trevor"; a CLIENT install with none fails closed
(refused, recorded, never Trevor, never invented). A malformed value or an
unreadable config is refused on every box.

Stdlib only, no network, no provider call, no client message.
Run: python3 -I <this file>
"""
import io
import json
import os
import sys
import tempfile
from contextlib import redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import emergency_owner as EO  # noqa: E402
from intake_preflight import factory  # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), str(detail)))
    return bool(ok)


def home(marker=False, config=None):
    """A throwaway install root; config is the identity JSON body (or a string)."""
    root = tempfile.mkdtemp(prefix="emergency-owner-")
    if marker:
        with open(os.path.join(root, EO.OPERATOR_MARKER), "w") as f:
            f.write("operator box\n")
    if config is not None:
        with open(os.path.join(root, EO.IDENTITY_FILE), "w") as f:
            f.write(config if isinstance(config, str) else json.dumps(config))
    return root


def checks():
    # the env var is an operator signal too; tests own it outright.
    saved_env = os.environ.pop(EO.OPERATOR_ENV, None)
    try:
        # 1. operator box, no configured value -> Trevor, and only "Trevor".
        r = EO.resolve(home(marker=True))
        check("operator box with no value resolves to Trevor",
              r["outcome"] == "ok" and r["owner"] == EO.OPERATOR_DEFAULT == "Trevor"
              and r["source"] == "operator_box_default"
              and r["reason_code"] == EO.CODE_OPERATOR_DEFAULT
              and r["blocked"] is False, repr(r))

        # 2. client install, no configured value -> FAIL CLOSED.
        r = EO.resolve(home())
        check("client install with no on-call operator refuses",
              r["outcome"] == "refused" and r["owner"] is None
              and r["blocked"] is True
              and r["reason_code"] == EO.CODE_UNCONFIGURED, repr(r))
        check("a client refusal never carries the operator default",
              r.get("owner") is None
              and EO.OPERATOR_DEFAULT not in json.dumps(r.get("owner")), repr(r))

        # 3. client install with its own on-call operator -> that name, never Trevor.
        r = EO.resolve(home(config={"ownerName": "Client Owner",
                                    "onCallOperator": "On Call Pat"}))
        check("client install binds its own recorded on-call operator",
              r["outcome"] == "ok" and r["owner"] == "On Call Pat"
              and r["source"] == "install_config"
              and r["reason_code"] == EO.CODE_FROM_CONFIG, repr(r))

        # 4. a configured value wins on the operator box too (default is only a default).
        r = EO.resolve(home(marker=True, config={"onCallOperator": "Designated Dana"}))
        check("a recorded value beats the operator-box default",
              r["outcome"] == "ok" and r["owner"] == "Designated Dana", repr(r))

        # 5. blank / non-string / oversize values are refused, never defaulted.
        for bad in ("", "   ", 7, None, "x" * (EO.MAX_NAME + 1), "line\nbreak"):
            r = EO.resolve(home(marker=True, config={"onCallOperator": bad}))
            check("malformed onCallOperator %r is refused on the operator box" % (bad,),
                  r["outcome"] == "refused" and r["owner"] is None
                  and r["blocked"] is True
                  and r["reason_code"] == EO.CODE_INVALID, repr(r))

        # 6. an unreadable config is refused on every box (never guessed).
        for marker in (False, True):
            r = EO.resolve(home(marker=marker, config="{not json"))
            check("unreadable install config is refused (operator_box=%s)" % marker,
                  r["outcome"] == "refused" and r["blocked"] is True
                  and r["reason_code"] == EO.CODE_CONFIG_INVALID, repr(r))
        r = EO.resolve(home(marker=True, config="[1, 2]"))
        check("a non-object install config is refused",
              r["outcome"] == "refused"
              and r["reason_code"] == EO.CODE_CONFIG_INVALID, repr(r))

        # 7. a missing install root on a client install is still a refusal.
        missing = os.path.join(tempfile.mkdtemp(prefix="emergency-owner-"), "absent")
        r = EO.resolve(missing)
        check("a client install with no config file at all refuses",
              r["outcome"] == "refused"
              and r["reason_code"] == EO.CODE_UNCONFIGURED, repr(r))

        # 8. the refusal record names the fact and carries no invented owner.
        rec = EO.refusal_record(r, at="2026-10-26T00:00:00+00:00")
        check("the refusal record is durable and ownerless",
              rec["outcome"] == "refused" and rec["blocked"] is True
              and rec["owner"] is None
              and rec["recorded_at"] == "2026-10-26T00:00:00+00:00"
              and rec["reason_code"] == EO.CODE_UNCONFIGURED, repr(rec))

        # 9. factory CLI: refusal is exit 4, an envelope, and a recorded refusal.
        run = os.path.join(tempfile.mkdtemp(prefix="emergency-run-"), "run")
        out = io.StringIO()
        with redirect_stdout(out):
            code = factory.main(["owner", "--install-home", home(), "--run-dir", run])
        env = json.loads(out.getvalue())
        rec_path = os.path.join(run, "control", "emergency-owner-refusal.json")
        check("factory owner exits 4 and answers rejected on a client install",
              code == 4 and env["outcome"] == "rejected"
              and env["reason_code"] == EO.CODE_UNCONFIGURED
              and env["data"]["owner"] is None, out.getvalue())
        check("the refusal is recorded on disk and named in the envelope",
              os.path.isfile(rec_path)
              and os.path.realpath(env["data"].get("refusal_record") or "")
              == os.path.realpath(rec_path)
              and json.load(open(rec_path))["owner"] is None, rec_path)
        check("the refusal next_action sends the operator to the config key",
              EO.CONFIG_KEY in env["next_action"], env["next_action"])

        # 10. factory CLI: the operator box answers ok with Trevor, exit 0.
        out = io.StringIO()
        with redirect_stdout(out):
            code = factory.main(["owner", "--install-home", home(marker=True)])
        env = json.loads(out.getvalue())
        check("factory owner exits 0 with Trevor on an operator box",
              code == 0 and env["outcome"] == "ok"
              and env["data"]["owner"] == "Trevor"
              and env["data"]["source"] == "operator_box_default", out.getvalue())

        # 11. factory CLI: a directly named config path is honored (no second root).
        cfg = os.path.join(home(), EO.IDENTITY_FILE)
        with open(cfg, "w") as f:
            json.dump({"onCallOperator": "Exact Config Eve"}, f)
        out = io.StringIO()
        with redirect_stdout(out):
            code = factory.main(["owner", "--install-home", home(), "--config", cfg])
        env = json.loads(out.getvalue())
        check("an exact --config path resolves its own recorded owner",
              code == 0 and env["data"]["owner"] == "Exact Config Eve", out.getvalue())
    finally:
        if saved_env is not None:
            os.environ[EO.OPERATOR_ENV] = saved_env
        else:
            os.environ.pop(EO.OPERATOR_ENV, None)
    return RESULTS


def main():
    results = checks()
    failed = [(n, d) for n, ok, d in results if not ok]
    for name, ok, detail in results:
        print("%s %s%s" % ("PASS" if ok else "FAIL", name,
                           "" if ok else " :: " + detail[:300]))
    print("\n%d checks, %d failed" % (len(results), len(failed)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
