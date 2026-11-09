#!/usr/bin/env python3
"""S75-X08 focused tests: final-view gate on the shipped gate bytes.

Runs gate/final_view_gate.py against throwaway fixtures proving the same
battery the CI wrapper (scripts/qc-final-view-gate.sh) asserts:
  clean PASS rc 0;
  three planted violations FAIL rc 1 with named primary codes
  (CROSSED_REFERENCE, MISSING_VIEW, PLACEHOLDER_NOT_FINAL);
  the r6-removed discriminating control PASSes the crossed fixture;
  garbage input FAILs MALFORMED_INPUT (fail closed, never a pass).

Run: python3 75-drama-song-ad-factory/scripts/core/character_bible/test_final_view_gate_s75_x08.py
"""
import hashlib
import json
import os
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
GATE = os.path.join(HERE, "final_view_gate.py")
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


def build(base, mutate=None):
    colours = [(200, 20, 20), (20, 200, 20), (20, 20, 200), (220, 220, 20),
               (220, 20, 220), (20, 220, 220), (120, 60, 30), (30, 60, 120)]
    os.makedirs(os.path.join(base, "fixtures"), exist_ok=True)
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
    return doc


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
    entry = doc["characters"][0]["views"]["close-up"]
    doc["characters"][0]["views"]["close-up"] = {"path": entry["path"], "sha256": "",
                                                 "kind": "placeholder",
                                                 "placeholder": True, "approved": False}


def dump(base, name, doc):
    path = os.path.join(base, name + ".json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=1, sort_keys=True)
    return path


class FinalViewGateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="fvg-x08-")
        cls.clean_path = dump(cls.tmp, "clean", build(cls.tmp))
        cls.crossed_path = dump(cls.tmp, "crossed", build(cls.tmp, crossed))
        cls.missing_path = dump(cls.tmp, "missing", build(cls.tmp, drop_view))
        cls.placeholder_path = dump(cls.tmp, "placeholder", build(cls.tmp, placeholder))
        bad = os.path.join(cls.tmp, "garbage.json")
        with open(bad, "w") as fh:
            fh.write("{not json")
        cls.bad_path = bad

    def run_gate(self, path):
        proc = subprocess.run([sys.executable, "-I", GATE, "--manifest", path,
                               "--base", self.tmp],
                              capture_output=True, text=True, env=ENV)
        try:
            body = json.loads(proc.stdout.strip() or "{}")
        except ValueError:
            body = {}
        return proc.returncode, body

    def test_clean_passes(self):
        rc, body = self.run_gate(self.clean_path)
        self.assertEqual(rc, 0, body)
        self.assertEqual(body.get("verdict"), "PASS")
        self.assertEqual(body.get("fail_codes"), [])

    def test_planted_crossed_fails_named(self):
        rc, body = self.run_gate(self.crossed_path)
        codes = body.get("fail_codes") or []
        self.assertEqual(rc, 1, body)
        self.assertTrue(any(str(c).startswith("CROSSED_REFERENCE") for c in codes), codes)

    def test_planted_missing_view_fails_named(self):
        rc, body = self.run_gate(self.missing_path)
        codes = body.get("fail_codes") or []
        self.assertEqual(rc, 1, body)
        self.assertTrue(any(str(c).startswith("MISSING_VIEW") for c in codes), codes)

    def test_planted_placeholder_fails_named(self):
        rc, body = self.run_gate(self.placeholder_path)
        codes = body.get("fail_codes") or []
        self.assertEqual(rc, 1, body)
        self.assertTrue(any(str(c).startswith("PLACEHOLDER_NOT_FINAL") for c in codes), codes)

    def test_r6_removed_control_passes_crossed(self):
        with open(GATE, encoding="utf-8") as fh:
            src = fh.read()
        start = src.index("    # R6 crossed associations")
        end = src.index("    # R7 exact consumption")
        no_r6 = os.path.join(self.tmp, "gate_no_r6.py")
        with open(no_r6, "w", encoding="utf-8") as fh:
            fh.write(src[:start] + "    # R6 removed for instrument control\n\n" + src[end:])
        proc = subprocess.run([sys.executable, "-I", no_r6, "--manifest", self.crossed_path,
                               "--base", self.tmp],
                              capture_output=True, text=True, env=ENV)
        body = json.loads(proc.stdout.strip() or "{}")
        self.assertEqual(proc.returncode, 0, body)
        self.assertEqual(body.get("verdict"), "PASS")

    def test_garbage_fails_closed(self):
        rc, body = self.run_gate(self.bad_path)
        codes = body.get("fail_codes") or []
        self.assertEqual(rc, 1, body)
        self.assertTrue(any(str(c).startswith("MALFORMED_INPUT") for c in codes), codes)


if __name__ == "__main__":
    unittest.main(verbosity=2)
