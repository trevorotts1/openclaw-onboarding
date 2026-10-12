#!/usr/bin/env python3
"""U10XCODE-U1 — the OPTIONAL U10 extras (Telegram button / card link /
measurement view), native fields first, OFF by default.

Proves, in order:
  1. OFF by default: ``extras_enabled`` is true ONLY for the exact on-values
     ``"true"`` / ``"1"``; unset, empty, ``"false"``, ``"yes"``, ``"TRUE"``
     and junk all stay OFF.
  2. The Telegram button is the NATIVE field added on top of the existing
     message payload: OFF -> the payload is returned unchanged; ON -> one
     ``reply_markup.inline_keyboard`` ``{text, url}`` button; ON with no URL
     -> no button invented.
  3. The card link is one appended line, the card's OWN native ``studio_url``
     first then the environment; OFF or no URL -> the text is unchanged.
  4. The measurement view renders ONLY the counts handed in, and is None when
     extras are off; it opens no store, page or socket.
  5. No input is ever mutated, an OFF-but-demanded extra refuses with the
     named code ``AF-DS-EXTRAS-DISABLED`` and adds nothing, and the module
     never references the required client-owned GHL-first delivery module, so
     it cannot change that path.
  6. The CLI is a real subprocess with a real exit code: 0 ok, 4 refused.

Run: HOME=$(mktemp -d) python3 scripts/core/choice_card/intake_card/test_optional_extras_u10x.py
stdlib only, no network, no send.
"""
from __future__ import annotations

import copy
import json
import os
import subprocess
import sys

HERE = os.path.realpath(os.path.dirname(os.path.abspath(__file__)))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import optional_extras as X                          # noqa: E402

FAILS = []
def check(name, ok, detail=""):
    print("PASS " if ok else "FAIL ", name, "" if ok else detail)
    if not ok:
        FAILS.append(name)

def refused(fn):
    try:
        fn()
    except X.ExtrasRefused as e:
        return e.refusal
    return None

# ------------------------------------------------- 1. OFF by default
check("off-when-unset", X.extras_enabled({}) is False)
check("off-when-empty", X.extras_enabled({X.EXTRAS_ENV: ""}) is False)
for value in ("false", "yes", "TRUE", "True", "on", "0"):
    check("off-when-%s" % value,
          X.extras_enabled({X.EXTRAS_ENV: value}) is False)
for value in ("true", "1"):
    check("on-when-%s" % value,
          X.extras_enabled({X.EXTRAS_ENV: value}) is True)

BASE = {"chat_id": "123", "text": "Your drama song ad"}

# ------------------------------------------- 2. Telegram button (native)
off = X.telegram_button(BASE, "https://studio.example/x", enabled=False)
check("telegram-off-unchanged", off == BASE, off)
check("telegram-off-no-native-field", "reply_markup" not in off)
on = X.telegram_button(BASE, "https://studio.example/x", enabled=True)
check("telegram-on-native-field",
      on.get("reply_markup", {}).get("inline_keyboard")
      == [[{"text": X.BUTTON_LABEL, "url": "https://studio.example/x"}]], on)
check("telegram-on-keeps-base", on.get("chat_id") == "123"
      and on.get("text") == BASE["text"])
base_snapshot = copy.deepcopy(BASE)
X.telegram_button(BASE, "https://studio.example/x", enabled=True)
check("telegram-never-mutates-input", BASE == base_snapshot, BASE)
check("telegram-on-no-url-no-button",
      "reply_markup" not in X.telegram_button(BASE, "", enabled=True))
check("telegram-env-on-reads-switch",
      "reply_markup" in X.telegram_button(
          BASE, "https://studio.example/y", env={X.EXTRAS_ENV: "1"}))

# ------------------------------------------------- 3. Card link
CARD = {"length": "60 seconds", "studio_url": "https://studio.example/card"}
check("card-off-unchanged",
      X.card_link(CARD, "Your card", enabled=False) == "Your card")
check("card-on-appends-native-url",
      X.card_link(CARD, "Your card", enabled=True)
      == "Your card\n%s: https://studio.example/card" % X.CARD_LINK_LABEL)
check("card-native-url-beats-env",
      "https://studio.example/card" in X.card_link(
          CARD, "Your card", enabled=True,
          env={X.STUDIO_URL_ENV: "https://env.example/z"}))
check("card-env-url-when-no-native",
      "https://env.example/z" in X.card_link(
          {}, "Your card", enabled=True,
          env={X.STUDIO_URL_ENV: "https://env.example/z"}))
check("card-on-no-url-unchanged",
      X.card_link({}, "Your card", enabled=True) == "Your card")
card_snapshot = copy.deepcopy(CARD)
X.card_link(CARD, "Your card", enabled=True,
            env={X.STUDIO_URL_ENV: "https://env.example/z"})
check("card-never-mutates-input", CARD == card_snapshot, CARD)

# ------------------------------------------------- 4. Measurement view
COUNTS = {"delivered": 3, "running": 1}
check("measurement-off-none", X.measurement_view(COUNTS, enabled=False) is None)
view = X.measurement_view(COUNTS, enabled=True)
check("measurement-lists-existing-counts",
      "delivered:" in view and "3" in view and "running:" in view
      and "total:" in view and "4" in view, view)
check("measurement-empty-total-zero",
      "total:" in X.measurement_view({}, enabled=True)
      and X.measurement_view({}, enabled=True).split("total:")[1].strip() == "0",
      X.measurement_view({}, enabled=True))
check("measurement-adds-no-store",
      not os.path.exists(os.path.join(HERE, "optional_extras.sqlite")))
counts_snapshot = copy.deepcopy(COUNTS)
X.measurement_view(COUNTS, enabled=True)
check("measurement-never-mutates-input", COUNTS == counts_snapshot, COUNTS)

# ------------------------------- 5. refusal + required path untouched
ref = refused(lambda: X.telegram_button(BASE, "u", enabled=False, require=True))
check("require-off-refuses", ref is not None and ref["code"] == X.DISABLED_CODE,
      ref)
check("require-off-adds-nothing",
      refused(lambda: X.card_link(CARD, "t", enabled=False, require=True))
      is not None)
check("require-off-measurement-refuses",
      refused(lambda: X.measurement_view(COUNTS, enabled=False, require=True))
      is not None)
check("refused-exit-code-is-4", X.REFUSED_EXIT == 4)
with open(os.path.join(HERE, "optional_extras.py"), encoding="utf-8") as fh:
    SRC = fh.read()
check("never-imports-required-delivery",
      "video_link_delivery" not in SRC)

# ------------------------------------------------- 6. CLI as a subprocess
CLI = os.path.join(HERE, "optional_extras.py")
def run(args, env_extra=None, drop_switch=False):
    env = dict(os.environ)
    env.pop(X.EXTRAS_ENV, None)
    env.pop(X.STUDIO_URL_ENV, None)
    if drop_switch:
        env.pop(X.EXTRAS_ENV, None)
    env.update(env_extra or {})
    p = subprocess.run([sys.executable, CLI] + args, capture_output=True,
                       text=True, env=env, stdin=subprocess.DEVNULL)
    return p

p = run(["telegram", "--target", "123", "--message", "hi",
         "--url", "https://studio.example/x"])
check("cli-telegram-off-rc0-silent", p.returncode == 0, p.stderr)
data = json.loads(p.stdout)
check("cli-telegram-off-no-button",
      data["enabled"] is False and "reply_markup" not in data.get("telegram", {}),
      data)
p = run(["telegram", "--target", "123", "--message", "hi",
         "--url", "https://studio.example/x", "--require"])
check("cli-telegram-required-while-off-refused", p.returncode == 4, p.stdout)
check("cli-refusal-named",
      json.loads(p.stdout)["code"] == X.DISABLED_CODE, p.stdout)
p = run(["telegram", "--target", "123", "--message", "hi",
         "--url", "https://studio.example/x"],
        env_extra={X.EXTRAS_ENV: "true"})
check("cli-telegram-on-button",
      p.returncode == 0
      and json.loads(p.stdout)["telegram"]["reply_markup"]["inline_keyboard"],
      p.stdout)
p = run(["measurement", "--counts", json.dumps(COUNTS)],
        env_extra={X.EXTRAS_ENV: "1"})
check("cli-measurement-on-view", p.returncode == 0
      and "total:" in json.loads(p.stdout)["view"], p.stdout)
p = run(["card", "--text", "Your card", "--require"])
check("cli-card-required-while-off-refused", p.returncode == 4, p.stdout)

def test_suite_checks_pass():
    assert not FAILS, FAILS

if __name__ == "__main__":
    print()
    if FAILS:
        print("FAILED %d checks: %s" % (len(FAILS), ", ".join(FAILS)))
        sys.exit(1)
    print("ALL CHECKS PASS")
    sys.exit(0)
