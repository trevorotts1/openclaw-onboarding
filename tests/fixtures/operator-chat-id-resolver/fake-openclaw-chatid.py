#!/usr/bin/env python3
"""fake-openclaw-chatid.py — a fake `openclaw` CLI for the operator-chat-id
resolver tests (tests/unit/operator-chat-id-resolver.test.sh).

Reproduces the ONE thing those tests need to control: what `openclaw config
get <key>` does, so a test can simulate a dead gateway ("1006 abnormal
closure") without a live gateway anywhere near the test, alongside the
ordinary "key not found" response a healthy gateway gives for an absent key.
Also records `openclaw message send ...` calls (never actually sends anything
— this is a fake binary, no network call is possible) so a test can assert
what a caller WOULD have sent, without ever touching a real Telegram chat.

Mode via $FAKE_OC_MODE (required):
  gateway_fail   -> every `config get` fails with a gateway/connection-level
                    signature (1006 abnormal closure), regardless of key.
                    Simulates the proven-live incident this fix addresses.
  clean_notfound -> every `config get` fails with an ordinary "not found"
                    (the NORMAL, non-broken response for an absent key on a
                    healthy gateway) — must NOT be treated as a failure
                    signature by the resolver under test.
  ok             -> `config get <key>` reads $FAKE_OC_CONFIG_JSON (shaped like
                    a real openclaw.json: {"env":{"vars":{...}}}) and returns
                    the value for env.vars.<key-suffix> if present, else the
                    same ordinary "not found" as clean_notfound.

`message send` calls are appended (one line, raw argv) to
$FAKE_OC_CALLS_FILE when set.
"""
import json
import os
import sys


def config_get(args):
    mode = os.environ.get("FAKE_OC_MODE", "")
    if mode == "gateway_fail":
        sys.stderr.write(
            "Error: connect ECONNREFUSED 127.0.0.1:18789 (1006 abnormal closure)\n"
        )
        return 1
    if not args:
        sys.stderr.write("Error: config get requires a key\n")
        return 1
    key = args[0]
    if mode == "ok":
        cfg_path = os.environ.get("FAKE_OC_CONFIG_JSON", "")
        if cfg_path and os.path.isfile(cfg_path):
            try:
                with open(cfg_path) as fh:
                    cfg = json.load(fh)
            except Exception:
                cfg = {}
            # key is dotted, e.g. env.vars.OPERATOR_ESCALATION_CHAT_ID
            parts = key.split(".")
            cur = cfg
            for p in parts:
                if isinstance(cur, dict) and p in cur:
                    cur = cur[p]
                else:
                    cur = None
                    break
            if cur is not None and cur != "":
                print(str(cur))
                return 0
    # clean_notfound (or ok-but-absent): the documented normal "not configured"
    # response — a clean, non-gateway-failure non-zero exit.
    sys.stderr.write("Error: key not found\n")
    return 1


def message_send(args):
    calls_file = os.environ.get("FAKE_OC_CALLS_FILE", "")
    if calls_file:
        with open(calls_file, "a") as fh:
            fh.write("message send " + " ".join(args) + "\n")
    return 0


def cron_list(args):
    print(json.dumps({"jobs": []}))
    return 0


def main(argv):
    if len(argv) >= 2 and argv[0] == "config" and argv[1] == "get":
        return config_get(argv[2:])
    if len(argv) >= 2 and argv[0] == "message" and argv[1] == "send":
        return message_send(argv[2:])
    if len(argv) >= 2 and argv[0] == "cron" and argv[1] == "list":
        return cron_list(argv[2:])
    sys.stderr.write("fake-openclaw-chatid: unsupported invocation: %r\n" % (argv,))
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
