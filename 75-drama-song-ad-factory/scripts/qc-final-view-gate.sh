#!/usr/bin/env bash
# qc-final-view-gate.sh — X08 fail-closed final-view enforcement gate (CI wiring).
#
# Runs the pinned gate 75-drama-song-ad-factory/scripts/core/character_bible/final_view_gate.py
# (FINAL-VIEW-BEHAVIOUR-R1, owed views pinned inside the gate) against a self-built
# fixture battery in a throwaway TMPDIR:
#   1. clean package (2 characters x 4 owed views, exact consumption) -> PASS rc 0
#   2. planted crossed reference (same bytes filed under two identities) -> FAIL rc 1 CROSSED_REFERENCE
#   3. planted missing view (one owed view dropped) -> FAIL rc 1 MISSING_VIEW
#   4. planted placeholder-as-final -> FAIL rc 1 PLACEHOLDER_NOT_FINAL
#   5. discriminating control: crossed rule removed -> same crossed fixture PASSes,
#      proving the fire comes from the rule, not fixture noise
#   6. garbage input (malformed manifest) -> FAIL rc 1 MALFORMED_INPUT (never a pass)
#
# Stdlib-only python3, no network, writes only under TMPDIR.
# Exit 0 when every expectation holds; exit 1 otherwise.
set -u

here="$(cd "$(dirname "$0")" 2>/dev/null && pwd)"
gate="${DRAMA75_FINAL_VIEW_GATE:-$here/core/character_bible/final_view_gate.py}"
if [ ! -f "$gate" ]; then
  echo "qc-final-view-gate: gate not found at $gate (set DRAMA75_FINAL_VIEW_GATE)" >&2
  exit 1
fi

tmp="$(mktemp -d "${TMPDIR:-/tmp}/qcfvg.XXXXXX")"
trap 'rm -rf "$tmp"' EXIT

PYTHONDONTWRITEBYTECODE=1 python3 -I - "$gate" "$tmp" <<'PY'
import hashlib
import json
import os
import struct
import subprocess
import sys
import zlib

gate, tmp = sys.argv[1], sys.argv[2]
VIEWS = ["close-up", "side-profile", "three-quarter", "full-standing"]
ENV = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")

def sha(data):
    return hashlib.sha256(data).hexdigest()

def png(path, rgb):
    def chunk(tag, body):
        payload = tag + body
        return (struct.pack(">I", len(body)) + payload
                + struct.pack(">I", zlib.crc32(payload) & 0xffffffff))
    raw = b"\x00" + bytes(rgb)
    blob = (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw))
            + chunk(b"IEND", b""))
    with open(path, "wb") as fh:
        fh.write(blob)

def run_gate(manifest_path, base):
    p = subprocess.run([sys.executable, "-I", gate, "--manifest", manifest_path,
                        "--base", base], capture_output=True, text=True, env=ENV)
    try:
        body = json.loads(p.stdout.strip() or "{}")
    except ValueError:
        body = {}
    return p.returncode, body

def build(base, name, mutate=None):
    colours = [(200, 20, 20), (20, 200, 20), (20, 20, 200), (220, 220, 20),
               (220, 20, 220), (20, 220, 220), (120, 60, 30), (30, 60, 120)]
    characters, refs = [], []
    for ci, char in enumerate(("alice", "bob")):
        views = {}
        for vi, view in enumerate(VIEWS):
            rel = "fixtures/%s-%s.png" % (char, view)
            png(os.path.join(base, rel), colours[ci * 4 + vi])
            digest = sha(open(os.path.join(base, rel), "rb").read())
            views[view] = {"path": rel, "sha256": digest, "kind": "actual", "approved": True}
            refs.append({"character_id": char, "view": view, "sha256": digest})
        characters.append({"id": char, "name": char.title(), "views": views})
    doc = {"schema": "blackceo.final-view-manifest/v1",
           "characters": characters,
           "consumption": [{"request_id": "req-keyframes-1", "references": refs}]}
    if mutate:
        mutate(doc, base)
    path = os.path.join(base, name + ".json")
    json.dump(doc, open(path, "w", encoding="utf-8"), indent=1, sort_keys=True)
    return path

def crossed(doc, base):
    rel = doc["characters"][0]["views"]["close-up"]["path"]
    digest = sha(open(os.path.join(base, rel), "rb").read())
    doc["characters"][1]["views"]["close-up"] = dict(doc["characters"][1]["views"]["close-up"])
    doc["characters"][1]["views"]["close-up"]["path"] = rel
    doc["characters"][1]["views"]["close-up"]["sha256"] = digest
    for ref in doc["consumption"][0]["references"]:
        if ref["character_id"] == "bob" and ref["view"] == "close-up":
            ref["sha256"] = digest

def drop_view(doc, base):
    doc["characters"][1]["views"].pop("full-standing")

def placeholder(doc, base):
    doc["characters"][0]["views"]["close-up"] = {"path": doc["characters"][0]["views"]["close-up"]["path"],
                                                 "sha256": "",
                                                 "kind": "placeholder",
                                                 "placeholder": True,
                                                 "approved": False}

os.makedirs(os.path.join(tmp, "fixtures"))
fails = []
def expect(name, path, want_rc, want_code=None):
    rc, body = run_gate(path, tmp)
    codes = body.get("fail_codes") or []
    ok = (rc == want_rc and body.get("verdict") == ("PASS" if want_rc == 0 else "FAIL")
          and (want_code is None or any(str(c).split(":")[0] == want_code for c in codes)))
    print(("  ok " if ok else "  FAIL ") + "%s rc=%d want=%d codes=%s" % (name, rc, want_rc, codes))
    if not ok:
        fails.append(name)

expect("clean PASS", build(tmp, "clean"), 0)
expect("planted crossed FAIL", build(tmp, "crossed", crossed), 1, "CROSSED_REFERENCE")
crossed_path = os.path.join(tmp, "crossed.json")
expect("planted missing view FAIL", build(tmp, "missing", drop_view), 1, "MISSING_VIEW")
expect("planted placeholder FAIL", build(tmp, "placeholder", placeholder), 1, "PLACEHOLDER_NOT_FINAL")

src = open(gate, encoding="utf-8").read()
start = src.index("    # R6 crossed associations")
end = src.index("    # R7 exact consumption")
no_r6 = os.path.join(tmp, "gate_no_r6.py")
open(no_r6, "w", encoding="utf-8").write(src[:start] + "    # R6 removed for instrument control\n\n" + src[end:])
p = subprocess.run([sys.executable, "-I", no_r6, "--manifest", crossed_path, "--base", tmp],
                   capture_output=True, text=True, env=ENV)
try:
    body = json.loads(p.stdout.strip() or "{}")
except ValueError:
    body = {}
ok = (p.returncode == 0 and body.get("verdict") == "PASS")
print(("  ok " if ok else "  FAIL ") + "control r6-removed-crossed-passes rc=%d verdict=%s" % (p.returncode, body.get("verdict")))
if not ok:
    fails.append("control_r6_removed")

bad = os.path.join(tmp, "garbage.json")
open(bad, "w").write("{not json")
rc, body = run_gate(bad, tmp)
ok = (rc == 1 and any(str(c).startswith("MALFORMED_INPUT") for c in (body.get("fail_codes") or [])))
print(("  ok " if ok else "  FAIL ") + "control garbage-fails-closed rc=%d codes=%s" % (rc, body.get("fail_codes")))
if not ok:
    fails.append("control_garbage")

if fails:
    print("qc-final-view-gate: FAIL — %s" % ", ".join(fails))
    sys.exit(1)
print("qc-final-view-gate: clean — clean PASS, 3 planted FAILs with named codes, r6-removed control + garbage control hold")
PY
rc=$?
if [ "$rc" -ne 0 ]; then
  echo "qc-final-view-gate: FAIL (rc=$rc)" >&2
  exit 1
fi
exit 0
