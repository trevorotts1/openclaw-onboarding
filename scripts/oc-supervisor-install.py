#!/usr/bin/env python3
"""oc-supervisor-install.py -- which OpenClaw install does the SUPERVISOR launch?

CAN015. `openclaw` on PATH is whatever the shell finds first (nvm, brew, a
~/.npm-global shim). The gateway is launched by launchd / systemd with an
explicit `node <...>/node_modules/openclaw/dist/index.js`, and that tree can be
a different copy at a different version. An upgrade that measures or installs
through PATH can report "already at target" while the gateway keeps running the
old build (operator Mac, roll 20261019: gateway 2026.10.4, PATH copy 2026.10.5).
So the launched path is the only thing worth measuring.

Usage:  oc-supervisor-install.py <field>      (HOME is honoured; stdlib only)
        field: show | source | unit | node | entry | pkg_root | pkg_json |
               prefix | version
exit:   0 resolved and the field is on stdout
        1 no launchd plist / systemd unit for OpenClaw on this box (caller may
          fall back to PATH -- there is no supervisor install to disagree with)
        2 a supervisor definition exists but does not resolve to an installed
          openclaw package (caller must NOT guess from PATH)
       64 usage

Resolution (launchd ProgramArguments / systemd ExecStart, same rule):
  node     the argument whose basename is node/nodejs
  entry    the argument that sits under .../node_modules/openclaw (exactly as
           the supervisor wrote it -- what the live process command line holds)
  pkg_root that .../node_modules/openclaw directory (a shim such as
           ~/.npm-global/bin/openclaw is followed with realpath)
  prefix   the npm prefix that owns it: <prefix>/lib/node_modules/openclaw
"""
import glob
import json
import os
import plistlib
import re
import shlex
import shutil
import sys

LABEL = "ai.openclaw.gateway"
PKG_RE = re.compile(r"^(.*/node_modules/openclaw)(?:/|$)")
FIELDS = ("source", "unit", "node", "entry", "pkg_root", "pkg_json", "prefix", "version")


def supervisor_argv(home):
    """(source, definition path, argv) of the first OpenClaw supervisor found, else None."""
    plist = os.path.join(home, "Library", "LaunchAgents", LABEL + ".plist")
    if os.path.isfile(plist):
        try:
            with open(plist, "rb") as f:
                argv = plistlib.load(f).get("ProgramArguments") or []
        except Exception:
            argv = []
        return "launchd", plist, [str(a) for a in argv]
    # ponytail: unit-name glob openclaw*.service; add `systemctl show -p ExecStart` if units get odd names
    for pat in (os.path.join(home, ".config/systemd/user/openclaw*.service"),
                "/etc/systemd/system/openclaw*.service",
                "/lib/systemd/system/openclaw*.service",
                "/usr/lib/systemd/system/openclaw*.service"):
        for unit in sorted(glob.glob(pat)):
            try:
                text = open(unit, errors="replace").read()
            except OSError:
                continue
            m = re.search(r"^\s*ExecStart\s*=\s*(.+)$", text, re.M)
            if m:
                cmd = m.group(1).strip().lstrip("-@+!:").replace("%h", home)
                try:
                    return "systemd", unit, shlex.split(cmd)
                except ValueError:
                    return "systemd", unit, []
    return None


def resolve(home):
    sup = supervisor_argv(home)
    if sup is None:
        return None, 1
    source, unit, argv = sup
    out = {"source": source, "unit": unit, "node": "", "entry": "", "pkg_root": ""}
    for a in argv:
        base = os.path.basename(a)
        if not out["node"] and base in ("node", "nodejs"):
            out["node"] = a if os.path.isabs(a) else (shutil.which(a) or "")
        if out["pkg_root"]:
            continue
        for cand in (a, os.path.realpath(a)):
            m = PKG_RE.match(cand)
            if m and os.path.isfile(os.path.join(m.group(1), "package.json")):
                out["entry"], out["pkg_root"] = a, m.group(1)
                break
    if not out["pkg_root"]:
        return out, 2
    nm = os.path.dirname(out["pkg_root"])            # .../node_modules
    up = os.path.dirname(nm)
    out["prefix"] = os.path.dirname(up) if os.path.basename(up) == "lib" else up
    out["pkg_json"] = os.path.join(out["pkg_root"], "package.json")
    try:
        out["version"] = str(json.load(open(out["pkg_json"])).get("version") or "")
    except Exception:
        out["version"] = ""
    return out, 0


def main(argv):
    if len(argv) != 2 or (argv[1] != "show" and argv[1] not in FIELDS):
        sys.stderr.write(__doc__.split("\n\n")[1] + "\n")
        return 64
    info, rc = resolve(os.path.expanduser("~"))
    if rc != 0:
        return rc
    if argv[1] == "show":
        for k in FIELDS:
            print("%s=%s" % (k, info[k]))
    else:
        print(info[argv[1]])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
