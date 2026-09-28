#!/usr/bin/env python3
"""stamp-rescue-escalation.py -- stamp the Rescue Rangers escalation section
into a box's workspace AGENTS.md (the only AGENTS.md a client agent loads).

Called by scripts/apply-fleet-standards.sh section 5j on every roll and by
install.sh on a fresh box. Externalized from the old inline 5j heredoc so both
callers run the SAME code and so it no longer sits inside a bash $(...) where
macOS bash 3.2 mis-parses quotes.

WHAT CHANGED (V4). The old step only UPGRADED an existing
"## Escalate to Rescue Rangers" section and logged a wiring gap when it was
absent, so no client box ever gained the section and an agent asked to
escalate improvised (it emailed). Now, on a client box, an absent section is
INSERTED near the top of the file, after the first top-level block.

CONTRACT
  * Marker pair <!-- RESCUE_ESCALATION_BOXNAME_V4 --> / <!-- END ... -->.
    Re-run = byte-identical no-op. V1-V3 and unmarked sections are upgraded
    IN PLACE (the stale opening marker and the V3 "What Rescue Rangers IS"
    tail are consumed), never duplicated.
  * Insert position is never inside another managed marker pair or a fenced
    code block, and is kept far below the 150,000-char bootstrap target.
  * The operator box (IS_OPERATOR_BOX / OPERATOR_BOX = 1|true, or an
    N8N_API_KEY in the environment -- the operator-only signal section 5k
    already uses) never gets a section inserted.
  * Every real write is preceded by a timestamped backup next to the file
    (AGENTS.md.bak-rescue-esc-<ts>) and done atomically under an flock.
  * Fail-open: prints ONE verdict token and exits 0.
    replace:<old>:<new> | upgrade:<old>:<new> | insert:<pos>:<new> | noop |
    skipped-operator | unrendered | error

usage: stamp-rescue-escalation.py --agents AGENTS.md --tpl TEMPLATE [--config openclaw.json]
"""
import argparse
import fcntl
import json
import os
import re
import shutil
import sys
import time

START = "<!-- RESCUE_ESCALATION_BOXNAME_V4 -->"
END = "<!-- END RESCUE_ESCALATION_BOXNAME_V4 -->"
UNSEEDED = ("NOT SEEDED YET: FLEET_STANDING_BOX_SLUG is missing, so rr-escalate.sh "
            "will refuse to send until it is set; report that to the operator")
MAX_INSERT_POS = 100000
MARKER_LINE = re.compile(r"^<!--\s*(?:BEGIN\s+)?(\S+)\s*-->\s*$")
END_LINE = re.compile(r"^<!--\s*END\s+(\S+)\s*-->\s*$")
FENCE = re.compile(r"^\s*(```|~~~)")


def env_vars(config):
    try:
        with open(config, encoding="utf-8") as fh:
            return ((json.load(fh).get("env") or {}).get("vars") or {})
    except Exception:
        return {}


def setting(name, cfg_vars):
    return str(os.environ.get(name) or cfg_vars.get(name) or "").strip()


def is_operator_box(cfg_vars):
    for name in ("IS_OPERATOR_BOX", "OPERATOR_BOX"):
        if setting(name, cfg_vars).lower() in ("1", "true", "yes"):
            return True
    return bool(os.environ.get("N8N_API_KEY", "").strip())


def insert_position(txt):
    """First safe block boundary AFTER the first top-level block."""
    lines = txt.splitlines(True)
    offs, pos = [], 0
    for line in lines:
        offs.append(pos)
        pos += len(line)
    offs.append(pos)
    # managed marker spans: START line .. matching END line
    spans, opened = [], {}
    for i, line in enumerate(lines):
        e = END_LINE.match(line)
        if e:
            if e.group(1) in opened:
                spans.append((offs[opened.pop(e.group(1))], offs[i + 1]))
            continue
        m = MARKER_LINE.match(line)
        if m:
            opened[m.group(1)] = i
    candidates, in_fence = set(), False
    for i, line in enumerate(lines):
        if FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if line.startswith("## "):
            j = i
            while j > 0 and MARKER_LINE.match(lines[j - 1]) and not END_LINE.match(lines[j - 1]):
                j -= 1
            candidates.add(offs[j])
        elif END_LINE.match(line):
            candidates.add(offs[i + 1])
    ok = sorted(c for c in candidates
                if 0 < c < len(txt) and not any(s < c < e for s, e in spans))
    if ok and ok[0] <= MAX_INSERT_POS:
        return ok[0]
    return 0 if len(txt) > MAX_INSERT_POS or ok else len(txt)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--agents", required=True)
    ap.add_argument("--tpl", required=True)
    ap.add_argument("--config", default="")
    args = ap.parse_args()
    path = args.agents
    cfg_vars = env_vars(args.config) if args.config else {}

    try:
        tpl = open(args.tpl, encoding="utf-8").read()
    except Exception:
        print("error")
        return
    rendered = tpl.replace("{{BOX_NAME}}", setting("FLEET_STANDING_BOX_SLUG", cfg_vars) or UNSEEDED)
    if re.search(r"\{\{[A-Z_]+\}\}", rendered):
        print("unrendered")
        return
    rendered = rendered.rstrip("\n") + "\n"

    lock_path = os.path.join(os.path.dirname(os.path.abspath(path)), ".AGENTS.md.rescue-esc.lock")
    try:
        lock = open(lock_path, "a")
        fcntl.flock(lock, fcntl.LOCK_EX)
        txt = open(path, encoding="utf-8").read()
    except Exception:
        print("error")
        return

    si, ei = txt.find(START), txt.find(END)
    if si != -1 and ei > si:
        cur_start, cur_end, mode = si, ei + len(END), "replace"
        if txt[cur_end:cur_end + 1] == "\n":
            cur_end += 1
    else:
        m = re.search(r"(?:^<!-- RESCUE_ESCALATION_BOXNAME_V\d+ -->\n)?"
                      r"^## Escalate to Rescue Rangers.*?(?=^## |\Z)",
                      txt, re.MULTILINE | re.DOTALL)
        if m:
            cur_start, cur_end, mode = m.start(), m.end(), "upgrade"
            # The V3 template rendered a second section after its END marker.
            tail = re.match(r"^## What Rescue Rangers IS \+ your own wiring.*?(?=^## |\Z)",
                            txt[cur_end:], re.MULTILINE | re.DOTALL)
            if tail:
                cur_end += tail.end()
        elif is_operator_box(cfg_vars):
            print("skipped-operator")
            return
        else:
            cur_start = cur_end = insert_position(txt)
            mode = "insert"

    current = txt[cur_start:cur_end]
    if mode == "insert":
        block = rendered + "\n"
        if cur_start > 0 and not txt[:cur_start].endswith("\n\n"):
            block = ("\n" if txt[:cur_start].endswith("\n") else "\n\n") + block
    else:
        block = rendered + ("\n" if txt[cur_end:] and mode == "upgrade" else "")
        if current == block:
            print("noop")
            return
    out = txt[:cur_start] + block + txt[cur_end:]

    ts = os.environ.get("TIMESTAMP") or time.strftime("%Y%m%d%H%M%S")
    tmp = path + ".tmp-rescue-esc"
    try:
        shutil.copy2(path, "%s.bak-rescue-esc-%s" % (path, ts))
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(out)
        shutil.copymode(path, tmp)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except Exception:
            pass
        print("error")
        return
    print("%s:%d:%d" % (mode, cur_start if mode == "insert" else len(current), len(block)))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("error")
    sys.exit(0)
