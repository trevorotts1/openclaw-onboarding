#!/usr/bin/env python3
"""step_gate.py - signed step gates so a Skill 75 run cannot skip a stage or
claim a stage it did not do. Stdlib only.

The contract lives beside this file as stage_contracts.json.

WHY
  Today a stage row can be moved to COMPLETE by anyone who can call the state
  store, QC records are hand-written JSON, and the order gate only asks "does a
  file with this name exist". A one-line shell write can satisfy all three.

WHAT THIS DOES
  open   --stage S   refuses unless the stage before S has a valid seal AND the
                     files that seal names still have the same sha256 on disk.
  seal   --stage S   reads every artifact the contract names for S, validates
                     each one (present, big enough, parses, required keys,
                     no placeholder text, numeric bounds), hashes it, and writes
                     control/gates/S.seal.json signed with HMAC-SHA256. The seal
                     carries the previous seal's signature, so the seals form a
                     chain. Refuses when no `open` record exists, when maker and
                     checker are the same identity, or when any artifact fails.
  verify             re-reads the whole chain and every artifact from disk.
  init               creates the per-run key and the genesis record.
  selftest           builds a throwaway run and proves the gate refuses a
                     skipped stage, an empty file, a placeholder file, a
                     hand-written seal, an edited artifact and self-review.

EXIT CODES
  0 ok   4 refused (contract not met; reason_code names why)   1 tool error

HONEST LIMIT
  The key lives on the same machine. This stops accidental and lazy
  fabrication (the echo-a-file case) and any forgery that does not read the
  key. It is not a security boundary against a process that deliberately reads
  the key and re-signs. The real protection is that every `open` and `verify`
  re-reads and re-validates the actual artifacts instead of trusting a flag.
"""
import argparse
import hashlib
import hmac
import importlib
import json
import os
import secrets
import subprocess
import sys
import tempfile
import time

SCHEMA = "blackceo.step-gate/v1"
EXIT_OK, EXIT_ERROR, EXIT_REFUSED = 0, 1, 4
PLACEHOLDER_TOKENS = ("TODO", "TBD", "PLACEHOLDER", "<fill", "lorem ipsum", "xxx")

#: The one contract file: it sits beside this module and its stage names are
#: batch_mode.batch.STAGES word for word (test_step_gate.py holds that line).
HERE = os.path.dirname(os.path.abspath(__file__))
CONTRACT_PATH = os.path.join(HERE, "stage_contracts.json")


class Refused(Exception):
    def __init__(self, code, detail):
        super().__init__("%s: %s" % (code, detail))
        self.code, self.detail = code, detail


def _sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _canon(doc):
    return json.dumps(doc, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _atomic_write(path, doc):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".gate-", dir=os.path.dirname(path))
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2, sort_keys=True)
        fh.write("\n")
    os.replace(tmp, path)


def _read_json(path, code):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        raise Refused(code + "_MISSING", path)
    except (OSError, ValueError) as exc:
        raise Refused(code + "_UNREADABLE", "%s: %s" % (path, exc))


def key_path(run_dir, key_file=None):
    if key_file:
        return key_file
    run_dir = os.path.abspath(run_dir)
    return os.path.join(os.path.dirname(run_dir), ".gate-keys",
                        os.path.basename(run_dir) + ".key")


def _key(run_dir, key_file=None):
    path = key_path(run_dir, key_file)
    try:
        with open(path, "rb") as fh:
            key = fh.read().strip()
    except OSError as exc:
        raise Refused("GATE_KEY_MISSING", "%s: %s (run `init` first)" % (path, exc))
    if len(key) < 32:
        raise Refused("GATE_KEY_INVALID", path)
    return key


def _sign(key, body):
    return hmac.new(key, _canon(body), hashlib.sha256).hexdigest()


def _gate_file(run_dir, stage, kind):
    return os.path.join(run_dir, "control", "gates", "%s.%s.json" % (stage, kind))


def load_contract(path=None):
    doc = _read_json(path or CONTRACT_PATH, "CONTRACT")
    if not isinstance(doc.get("order"), list) or not isinstance(doc.get("stages"), dict):
        raise Refused("CONTRACT_INVALID", "needs `order` (list) and `stages` (object)")
    for stage in doc["order"]:
        if not (doc["stages"].get(stage) or {}).get("artifacts"):
            raise Refused("CONTRACT_INVALID", "stage %r declares no artifacts" % stage)
    return doc


def _core_module(name):
    """Import one core module; scripts/core goes on the path if it is not there."""
    core = os.path.dirname(HERE)
    if core not in sys.path:
        sys.path.insert(0, core)
    package, _, module = name.partition(".")
    if module:
        return importlib.import_module(package + "." + module)
    return importlib.import_module(package)


def _resolve_validator(ref):
    """``module:function`` -> the callable, or Refused when it does not resolve."""
    module_name, _, func_name = ref.partition(":")
    if not module_name or not func_name:
        raise Refused("ARTIFACT_INVALID", "validator %r is not module:function" % ref)
    fn = None
    try:
        fn = getattr(importlib.import_module(module_name), func_name, None)
    except ImportError:
        fn = None
    if not callable(fn):                 # `step_gate` also names THIS module
        fn = globals().get(func_name)
    if not callable(fn):
        raise Refused("ARTIFACT_INVALID", "validator %r resolves to no function" % ref)
    return fn


def _ffprobe_duration(path):
    """The file's measured duration in seconds via ffprobe, or None."""
    try:
        proc = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    try:
        value = float((proc.stdout or "").strip())
    except ValueError:
        return None
    return value if value > 0 else None


def _chosen_length_s(run_dir):
    """The run's recorded chosen length in seconds, or None (never guessed)."""
    try:
        doc = _read_json(os.path.join(run_dir, "control", "method.json"), "METHOD")
    except Refused:
        return None
    value = doc.get("chosen_length_s") if isinstance(doc, dict) else None
    if isinstance(value, int) and not isinstance(value, bool) and value > 2:
        return value
    return None


#: Per-stage validators. Each takes (run_dir, spec, row) and returns a list of
#: problem strings; an empty list seals. A validator may add evidence to `row`.
#: ``final-qc`` carries none on purpose: its verdict file is written only by the
#: quality-control measurement unit (U-C02), not by anything that reaches this gate.
def validate_lyrics_artifact(run_dir, spec, row):
    """`script-lyrics`: the lyric file parses and lyric_writer reports no error."""
    doc = _read_json(os.path.join(run_dir, spec["path"]), "ARTIFACT")
    lines = doc.get("lines") if isinstance(doc, dict) else doc
    brief = doc.get("brief") if isinstance(doc, dict) else None
    if not isinstance(lines, list):
        return ["%s carries no `lines` list" % spec["path"]]
    writer = _core_module("lyric_writer.lyric_writer")
    result = writer.validate_lyrics(lines, brief if isinstance(brief, dict) else None)
    return ["%s: %s" % (e.get("error"), e.get("detail"))
            for e in result.get("errors") or [] if isinstance(e, dict)]


def validate_song_artifact(run_dir, spec, row):
    """`music`: the picked song opens with ffprobe and honours the overshoot rule."""
    duration = _ffprobe_duration(os.path.join(run_dir, spec["path"]))
    if duration is None:
        return ["ffprobe could not measure %s" % spec["path"]]
    chosen = _chosen_length_s(run_dir)
    if chosen is None:
        return ["no chosen_length_s in control/method.json; the song length cannot be judged"]
    lengths = _core_module("master_length.master_length")
    try:
        verdict = lengths.judge_duration(duration, lengths.master_max_s(chosen), short="free")
    except ValueError as exc:
        return [str(exc)]
    if verdict.get("warning"):          # named, never a stop (order 2026-10-21)
        row["warning"] = verdict["warning"]
    if verdict.get("outcome") != "ok":
        return ["%s: %s" % (verdict.get("reason_code"), verdict.get("detail"))]
    return []


def validate_master_artifact(run_dir, spec, row):
    """`assembly`: the master opens with ffprobe; its measured length is sealed."""
    duration = _ffprobe_duration(os.path.join(run_dir, spec["path"]))
    if duration is None:
        return ["ffprobe could not open %s" % spec["path"]]
    row["measured_s"] = round(duration, 3)
    return []


def validate_artifact(run_dir, spec):
    """Read the REAL artifact and return its evidence row, or raise Refused."""
    rel = spec["path"]
    path = os.path.join(run_dir, rel)
    if not os.path.isfile(path):
        raise Refused("ARTIFACT_MISSING", rel)
    size = os.path.getsize(path)
    floor = int(spec.get("min_bytes", 2))
    if size < floor:
        raise Refused("ARTIFACT_TOO_SMALL", "%s is %d bytes, contract floor is %d"
                      % (rel, size, floor))
    row = {"path": rel, "bytes": size, "sha256": _sha256_file(path), "kind": spec["kind"]}
    if spec["kind"] == "json":
        doc = _read_json(path, "ARTIFACT")
        if doc in ({}, [], None, ""):
            raise Refused("ARTIFACT_EMPTY", "%s parses to an empty value" % rel)
        text = json.dumps(doc).lower()
        for token in PLACEHOLDER_TOKENS:
            if token.lower() in text:
                raise Refused("ARTIFACT_PLACEHOLDER", "%s contains %r" % (rel, token))
        for key in spec.get("required_keys", []):
            if not isinstance(doc, dict) or key not in doc:
                raise Refused("ARTIFACT_KEY_MISSING", "%s lacks key %r" % (rel, key))
        for key, want in (spec.get("equals") or {}).items():
            if not isinstance(doc, dict) or doc.get(key) != want:
                raise Refused("ARTIFACT_VALUE_WRONG", "%s: %s is %r, contract needs %r"
                              % (rel, key, (doc or {}).get(key) if isinstance(doc, dict)
                                 else None, want))
    elif spec["kind"] == "media":
        with open(path, "rb") as fh:
            head = fh.read(16)
        if head.strip(b"\x00") == b"":
            raise Refused("ARTIFACT_NOT_MEDIA", "%s starts with null bytes" % rel)
    ref = spec.get("validator")
    if ref:
        try:
            problems = _resolve_validator(ref)(run_dir, spec, row)
        except Exception as exc:                        # noqa: BLE001 - a raise refuses
            problems = ["%s: %s" % (type(exc).__name__, exc)]
        problems = [str(p) for p in problems or []]
        if problems:
            raise Refused("ARTIFACT_INVALID", "%s failed its validator: %s"
                          % (rel, "; ".join(problems)))
    return row


def _verify_seal(run_dir, stage, key, contract):
    """Re-read the seal AND the artifacts it names. Returns the seal doc."""
    seal = _read_json(_gate_file(run_dir, stage, "seal"), "SEAL")
    body = seal.get("body")
    if not isinstance(body, dict) or body.get("stage") != stage \
            or body.get("schema") != SCHEMA:
        raise Refused("SEAL_MALFORMED", stage)
    if not hmac.compare_digest(str(seal.get("signature", "")), _sign(key, body)):
        raise Refused("SEAL_SIGNATURE_INVALID",
                      "%s seal was not written by this gate (hand-written or edited)" % stage)
    declared = {a["path"] for a in contract["stages"][stage]["artifacts"]}
    sealed = {a["path"]: a for a in body.get("artifacts", [])}
    if set(sealed) != declared:
        raise Refused("SEAL_ARTIFACT_SET_WRONG", "%s sealed %s, contract declares %s"
                      % (stage, sorted(sealed), sorted(declared)))
    for rel, row in sealed.items():
        path = os.path.join(run_dir, rel)
        if not os.path.isfile(path):
            raise Refused("SEALED_ARTIFACT_GONE", rel)
        if _sha256_file(path) != row.get("sha256"):
            raise Refused("SEALED_ARTIFACT_CHANGED",
                          "%s changed after stage %r was sealed" % (rel, stage))
    return seal


def _previous(contract, stage):
    order = contract["order"]
    if stage not in order:
        raise Refused("STAGE_UNKNOWN", stage)
    at = order.index(stage)
    return order[at - 1] if at else None


def cmd_init(run_dir, key_file=None):
    path = key_path(run_dir, key_file)
    if os.path.exists(path):
        raise Refused("GATE_ALREADY_INITIALISED", path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w") as fh:
        fh.write(secrets.token_hex(32))
    _atomic_write(_gate_file(run_dir, "_genesis", "open"),
                  {"schema": SCHEMA, "created_at": int(time.time())})
    return {"initialised": True}


def cmd_open(run_dir, stage, contract, key_file=None):
    key = _key(run_dir, key_file)
    prev = _previous(contract, stage)
    prev_sig = ""
    if prev is not None:
        try:
            prev_sig = _verify_seal(run_dir, prev, key, contract)["signature"]
        except Refused as exc:
            raise Refused("PREVIOUS_STAGE_NOT_PROVEN",
                          "stage %r cannot open: %r -> %s" % (stage, prev, exc))
    body = {"schema": SCHEMA, "stage": stage, "opened_at": int(time.time()),
            "previous_stage": prev, "previous_signature": prev_sig}
    _atomic_write(_gate_file(run_dir, stage, "open"),
                  {"body": body, "signature": _sign(key, body)})
    return {"opened": stage, "previous_stage": prev}


def cmd_seal(run_dir, stage, maker, checker, contract, key_file=None):
    key = _key(run_dir, key_file)
    if not maker or not checker:
        raise Refused("IDENTITY_MISSING", "both --maker and --checker are required")
    if maker.strip().lower() == checker.strip().lower():
        raise Refused("MAKER_SELF_REVIEW", "maker and checker are both %r" % maker)
    opened = _read_json(_gate_file(run_dir, stage, "open"), "OPEN_RECORD")
    if not hmac.compare_digest(str(opened.get("signature", "")),
                               _sign(key, opened.get("body") or {})):
        raise Refused("OPEN_RECORD_INVALID", stage)
    prev = _previous(contract, stage)
    if prev is not None:
        _verify_seal(run_dir, prev, key, contract)          # still true right now?
    rows = [validate_artifact(run_dir, spec)
            for spec in contract["stages"][stage]["artifacts"]]
    body = {"schema": SCHEMA, "stage": stage, "sealed_at": int(time.time()),
            "maker": maker, "checker": checker, "artifacts": rows,
            "previous_stage": prev,
            "previous_signature": opened["body"].get("previous_signature", "")}
    _atomic_write(_gate_file(run_dir, stage, "seal"),
                  {"body": body, "signature": _sign(key, body)})
    return {"sealed": stage, "artifacts": rows}


def cmd_verify(run_dir, contract, through=None, key_file=None):
    key = _key(run_dir, key_file)
    proven, last_sig = [], ""
    for stage in contract["order"]:
        if not os.path.isfile(_gate_file(run_dir, stage, "seal")):
            if through and stage != through and contract["order"].index(stage) \
                    <= contract["order"].index(through):
                raise Refused("CHAIN_INCOMPLETE", "no seal for %r" % stage)
            break
        seal = _verify_seal(run_dir, stage, key, contract)
        if seal["body"].get("previous_signature", "") != last_sig:
            raise Refused("CHAIN_BROKEN", "%r does not follow the stage before it" % stage)
        last_sig = seal["signature"]
        proven.append(stage)
        if stage == through:
            break
    if through and through not in proven:
        raise Refused("CHAIN_INCOMPLETE", "no valid seal through %r" % through)
    return {"proven_stages": proven}


def selftest():
    proofs = []

    def refused(code, fn, *a, **k):
        try:
            fn(*a, **k)
        except Refused as exc:
            return exc.code == code or code in exc.detail
        return False

    contract = {"order": ["one", "two"], "stages": {
        "one": {"artifacts": [{"path": "a/one.json", "kind": "json", "min_bytes": 10,
                               "required_keys": ["lines"]}]},
        "two": {"artifacts": [{"path": "a/two.json", "kind": "json"}]}}}
    with tempfile.TemporaryDirectory() as base:
        run = os.path.join(base, "run-1")
        os.makedirs(os.path.join(run, "a"))
        cmd_init(run)
        proofs.append(("stage two cannot open before stage one is sealed",
                       refused("PREVIOUS_STAGE_NOT_PROVEN", cmd_open, run, "two", contract)))
        cmd_open(run, "one", contract)
        open(os.path.join(run, "a", "one.json"), "w").write("{}")
        proofs.append(("an empty file is refused",
                       refused("ARTIFACT_TOO_SMALL", cmd_seal, run, "one", "m", "c", contract)))
        json.dump({"lines": ["TODO write me"]}, open(os.path.join(run, "a", "one.json"), "w"))
        proofs.append(("a placeholder file is refused",
                       refused("ARTIFACT_PLACEHOLDER", cmd_seal, run, "one", "m", "c", contract)))
        json.dump({"lines": ["a real line of the story"]},
                  open(os.path.join(run, "a", "one.json"), "w"))
        proofs.append(("maker cannot check own work",
                       refused("MAKER_SELF_REVIEW", cmd_seal, run, "one", "Sam", "sam", contract)))
        cmd_seal(run, "one", "builder", "checker", contract)
        proofs.append(("a good stage seals and verifies",
                       cmd_verify(run, contract, through="one")["proven_stages"] == ["one"]))
        seal_path = _gate_file(run, "one", "seal")
        good_seal = open(seal_path).read()
        forged = json.loads(good_seal)
        forged["body"]["checker"] = "someone-else"
        open(seal_path, "w").write(json.dumps(forged))
        proofs.append(("an edited seal is refused",
                       refused("SEAL_SIGNATURE_INVALID", cmd_verify, run, contract, "one")))
        open(seal_path, "w").write(good_seal)
        json.dump({"lines": ["changed after sealing, still valid JSON"]},
                  open(os.path.join(run, "a", "one.json"), "w"))
        proofs.append(("an artifact edited after sealing blocks the next stage",
                       refused("SEALED_ARTIFACT_CHANGED", cmd_open, run, "two", contract)))
    for name, ok in proofs:
        print(("ok   " if ok else "FAIL ") + name)
    return 0 if all(ok for _, ok in proofs) else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("init", "open", "seal", "verify"):
        p = sub.add_parser(name)
        p.add_argument("--run-dir", required=True)
        p.add_argument("--key-file", default=None)
        p.add_argument("--contract", default=None)
        if name in ("open", "seal"):
            p.add_argument("--stage", required=True)
        if name == "seal":
            p.add_argument("--maker", required=True)
            p.add_argument("--checker", required=True)
        if name == "verify":
            p.add_argument("--through", default=None)
    sub.add_parser("selftest")
    a = ap.parse_args(argv)
    if a.cmd == "selftest":
        return selftest()
    try:
        contract = load_contract(a.contract)
        if a.cmd == "init":
            data = cmd_init(a.run_dir, a.key_file)
        elif a.cmd == "open":
            data = cmd_open(a.run_dir, a.stage, contract, a.key_file)
        elif a.cmd == "seal":
            data = cmd_seal(a.run_dir, a.stage, a.maker, a.checker, contract, a.key_file)
        else:
            data = cmd_verify(a.run_dir, contract, a.through, a.key_file)
    except Refused as exc:
        print(json.dumps({"outcome": "rejected", "reason_code": exc.code,
                          "detail": exc.detail}, indent=2))
        return EXIT_REFUSED
    except Exception as exc:
        print(json.dumps({"outcome": "error", "reason_code": "GATE_TOOL_ERROR",
                          "detail": str(exc)}, indent=2))
        return EXIT_ERROR
    print(json.dumps({"outcome": "ok", "data": data}, indent=2, sort_keys=True))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
