#!/usr/bin/env python3
"""BATCH-5 member B: the dispatch CLI must reach the F14 lock and the receipt.

Two defects this pins, both on the CLI surface only:

  * `--state-store` did not exist, so every video dispatch typed on the
    command line could never pass F14 (VIDEO_MODEL_LOCK_MISSING no matter what
    was locked) -- the flag now threads into dispatch().
  * `--prompt-file` kept the file's trailing newline, while a prompt receipt
    hashes the prompt text; one 0x0A made every templated H3 job refuse
    PROMPT_NOT_TEMPLATED. Reading a file drops exactly one trailing newline.

stdlib only, no network, no provider: dispatch() is replaced in-process.

Run from the skill root:  python3 scripts/core/kie_dispatch/test_kie_cli_state_store_b5.py
"""
import json
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
CORE = HERE.parent
if str(CORE) not in sys.path:
    sys.path.insert(0, str(CORE))

import kie_dispatch.model_lock as ML  # noqa: E402

KD = __import__("importlib").import_module("kie_dispatch.kie_dispatch")

PASS, FAILS = [], []


def check(name, got, want):
    if got == want:
        PASS.append(name)
        print("ok %s" % name)
    else:
        FAILS.append(name)
        print("FAIL %s: got %r want %r" % (name, got, want))


def _args(tmp, **kw):
    a = ["dispatch", "--model", "minimax-h3/image-to-video",
         "--request", str(tmp / "req.json"),
         "--save-dir", str(tmp), "--ledger", str(tmp / "spend.sqlite3"),
         "--run-id", "r1", "--logical-key", "video", "--attempt-id", "a1",
         "--cost", "0"]
    for k, v in kw.items():
        a += ["--" + k.replace("_", "-"), str(v)]
    return a


def main():
    import io
    import contextlib

    real = KD.dispatch
    seen = {}

    def fake(**kw):
        seen.update(kw)
        return {"outcome": "ok", "reason_code": "STUB", "evidence": {}}

    KD.dispatch = fake
    try:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            (tmp / "req.json").write_text('{"prompt": "x"}', encoding="utf-8")

            (tmp / "p1.txt").write_text("hello H3 prompt\n", encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                KD.main(_args(tmp, prompt_file=tmp / "p1.txt",
                               state_store=tmp / "state.sqlite3"))
            check("1: prompt file loses exactly one trailing newline",
                  seen.get("prompt"), "hello H3 prompt")
            check("2: --state-store reaches dispatch()",
                  seen.get("state_store"), str(tmp / "state.sqlite3"))

            (tmp / "p2.txt").write_text("two newlines\n\n", encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                KD.main(_args(tmp, prompt_file=tmp / "p2.txt"))
            check("3: only ONE trailing newline is dropped",
                  seen.get("prompt"), "two newlines\n")

            (tmp / "p3.txt").write_text("no newline", encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                KD.main(_args(tmp, prompt_file=tmp / "p3.txt"))
            check("4: a file with no newline is unchanged",
                  seen.get("prompt"), "no newline")

            # the real dispatch(): the locked store is now reachable from the CLI
            db = str(tmp / "lock.sqlite3")
            ML.lock_run_model(db, "r1", "minimax-h3/*")
            seen.clear()
            KD.dispatch = real
            with contextlib.redirect_stdout(io.StringIO()) as out:
                KD.main(_args(tmp, state_store=db))
            env = json.loads(out.getvalue())
            check("5: a locked run is not refused at F14 from the CLI",
                  env.get("reason_code") == "VIDEO_MODEL_LOCK_MISSING", False)
            with contextlib.redirect_stdout(io.StringIO()) as out:
                KD.main(_args(tmp))
            env = json.loads(out.getvalue())
            check("6: no store means the F14 refusal, never a silent pass",
                  env.get("reason_code"), "VIDEO_MODEL_LOCK_MISSING")
    finally:
        KD.dispatch = real

    print("\n%s" % ("ALL PASS" if not FAILS else
                    "%d FAILED: %s" % (len(FAILS), ", ".join(FAILS))))
    return 0 if not FAILS else 1


if __name__ == "__main__":
    sys.exit(main())
