#!/usr/bin/env python3
"""update-summary.py OLD_VER NEW_VER CHANGELOG BUNDLE_DIR LIVE_SKILLS_DIR

Plain-words "what changed" for the UPDATE PENDING flag: CHANGELOG headings between
the box's old version (exclusive) and the new one (inclusive), core-change callouts,
and skills whose skill-version.txt differs from the box's live copy. Never fails:
prints nothing on any error so the flag still gets written."""
import glob, os, re, sys

def ver(s):
    m = re.match(r"v?(\d+)\.(\d+)\.(\d+)", s or "")
    return tuple(int(x) for x in m.groups()) if m else None

def main(old, new, changelog, bundle, live):
    o, n = ver(old), ver(new)
    out = []
    try:
        text = open(changelog, encoding="utf-8").read()
    except OSError:
        text = ""
    secs = re.split(r"\n(?=## )", text)
    heads, body = [], ""
    for s in secs:
        m = re.match(r"##\s+\[?(v\d+\.\d+\.\d+)\]?\s*[-—]*\s*(.*)", s)
        v = ver(m.group(1)) if m else None
        if not v or not n or v > n or (o and v <= o):
            continue
        title = re.sub(r"^(\d{4}-\d{2}-\d{2})\s*[-—]+\s*", "", m.group(2).split("\n")[0]).strip()
        heads.append("%s: %s" % (m.group(1), title[:160]))
        body += s
    if heads:
        out.append("- Releases since %s (newest first, %d):" % (old or "your last update", len(heads)))
        out += ["  - " + h for h in heads[:15]]
        if len(heads) > 15:
            out.append("  - ...and %d older releases (see CHANGELOG.md)" % (len(heads) - 15))
    if re.search(r"JEV|decision engine", body, re.I):
        out.append("- Core: task routing uses the JEV decision engine (intake routing, mc-route.sh) -- "
                   "check with `bash ~/.openclaw/scripts/routing-mode.sh status`")
    changed = []
    for d in sorted(glob.glob(os.path.join(bundle, "[0-9]*"))):
        f = os.path.basename(d)
        if "ARCHIVED" in f:
            continue
        def rd(p):
            try:
                return open(os.path.join(p, "skill-version.txt")).read().strip()
            except OSError:
                return None
        nv, ov = rd(d), rd(os.path.join(live, f))
        if nv and ov and nv != ov:
            changed.append("%s (%s -> %s)" % (f, ov, nv))
    if changed:
        out.append("- Skills updated (version changed): " + ", ".join(changed))
    print("\n".join(out))

if __name__ == "__main__":
    try:
        main(*sys.argv[1:6])
    except Exception:
        pass
