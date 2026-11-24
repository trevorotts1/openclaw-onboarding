#!/usr/bin/env python3
"""out_of_pipeline.py - the fail-closed out-of-pipeline detector (F14 items 4-6).

WHY THIS EXISTS
---------------
F14 item 4: an artifact written outside the governed pipeline must be *refused*,
not warned about. F14 item 5: the detector must not block the pipeline's own
intermediate files, so legitimate in-progress outputs are registered BEFORE the
producer writes them and are reported as `registered_unfinished`, never as
ungoverned. F14 item 6: an unadmitted output is marked unverified and excluded
from delivery, progress credit, installation and publication -- it is preserved
for inspection and never auto-deleted.

THE THREE RULES THIS FILE KEEPS
-------------------------------
1. Scope is explicit. Only a REGISTERED run root is scanned, and only declared
   native resources are compared. Nothing is inferred from a directory name.
2. Comparison is exact. A path is normalised to one relative POSIX spelling and
   compared by equality against the registry and the receipts. Substring
   membership is never used to prove an artifact belongs to a receipt: a receipt
   naming `page.html` does not admit `old-page.html` (item 4, verbatim).
3. Content and resource bindings are hashes. An `emitted` output whose bytes no
   longer match its registered sha256 is a content mismatch, which is ungoverned
   output, not a pass.

THREAT MODEL M (1.3.47; every check in this file is held to it)
---------------------------------------------------------------
The admission gate exists to stop mistaken or unreviewed out-of-pipeline files becoming
pipeline output. Assume an actor that can WRITE ANY FILE inside the run folder (governor.json,
any stage-executor-record.json, sidecar JSON, edited images, the ledger itself) but does NOT
hold the operator key. Under M an unsigned file, field or claim is never trusted. Only (a)
records HMAC-signed with the key named by SF_PIN_AUTHORITY_KEY_FILE (mode 0600, outside the
run) and (b) the contents of pass-stage receipts written by the gate are trusted. An actor
who holds the key is the owner and is out of scope.

Stdlib only. No network. No execution. Never deletes anything.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = "signature-launch-out-of-pipeline/v1"

# Run-internal machinery is not pipeline output: the registry, the stage gate's
# state and receipts, briefs and browser sessions all live under private/.
INTERNAL_DIRS = ("private",)

# The quarantine ledger (1.3.44): an operator-signed acknowledgement that a file is
# OUT of the pipeline. It is never a registration and never a promotion.
LEDGER_FILE = "private/quarantine-ledger.json"
LEDGER_SCHEMA = "signature-launch-quarantine-ledger/v1"
LEDGER_KIND = "quarantine_entry"
GOVERNOR_FILE = "private/governor.json"
ADMISSION_KIND = "admission_record"
ACK_FILE = "private/input-acknowledgements.json"
ACK_SCHEMA = "signature-launch-input-acknowledgements/v1"
ACK_KIND = "input_acknowledgement"
ACK_FIELDS = ("path", "old_sha256", "new_sha256", "reason", "approver", "acknowledged_at")
EXECUTOR_RECORD = "stage-executor-record.json"   # read ONLY to print evidence in a release note
SEAL_FILE = "private/quarantine-seal.json"
SEAL_SCHEMA = "signature-launch-quarantine-seal/v1"
SEAL_KIND = "quarantine_seal"
RELEASE_FILE = "private/quarantine-releases.json"
RELEASE_SCHEMA = "signature-launch-quarantine-releases/v1"
RELEASE_KIND = "quarantine_release"
RELEASE_FIELDS = ("path", "sha256", "stage", "reason", "approver", "signed_at", "note")
REOWN_FILE = "private/reown-records.json"
REOWN_SCHEMA = "signature-launch-reown-records/v1"
REOWN_KIND = "reown"
REOWN_FIELDS = ("path", "sha256", "owner_stage", "reason", "approver", "signed_at", "note")
ENTRY_FIELDS = ("path", "sha256", "size", "reason", "quarantined_at", "approver")

# RUN-STATE FILES (1.3.45). Exact root-level names the pipeline rewrites on every
# dispatch BY DESIGN, so a byte change on one is a record, not out-of-pipeline output:
#   production-request.json  the stage request is rebuilt from the manuscript on every
#                            stage (SOP Stage 4, "Per-run layout input"; generation-execution.md)
#   image-spend-ledger.json  the append-only per-run spend record, written before and after
#                            every paid render (stage_executor.py, LEDGER)
#   page-result.json         the page result record rebuilt from stage state (HANDOFF.md,
#                            doc 02 section 6)
# The list is CLOSED: a name outside it, the same name in a subfolder, a file that is not
# registered, or a file whose content does not have the shape below is not run state.
# A change is recorded (old/new sha) in `run_state_changed` and never fails the scan.
RUN_STATE_SHAPES = {
    "production-request.json": ("model", "sections"),
    "image-spend-ledger.json": ("calls",),
    "page-result.json": ("request_id", "status", "artifacts"),
}
RUN_STATE_FILES = tuple(RUN_STATE_SHAPES)
RUN_STATE_MAX_BYTES = 64 * 1024 * 1024

IN_PROGRESS = "in_progress"
EMITTED = "emitted"
STATES = (IN_PROGRESS, EMITTED)


class OutOfPipeline(ValueError):
    """A fail-closed refusal: something in the run did not come through the pipeline."""


# --------------------------------------------------------------------------
# path normalisation - one spelling, compared by equality only
# --------------------------------------------------------------------------

def normalise(root, path):
    """One canonical relative POSIX path inside `root`, or OutOfPipeline.

    Absolute paths and `..` escapes are refused. Two different spellings of the
    same file (`./a/b.png`, `a//b.png`) collapse to `a/b.png` so the comparison
    cannot be dodged by re-spelling a path.
    """
    base = Path(root).resolve()
    text = str(path or "").strip().replace("\\", "/")
    if not text:
        raise OutOfPipeline("artifact path is empty")
    candidate = Path(text)
    if candidate.is_absolute() or text.startswith("~"):
        raise OutOfPipeline("artifact path must be relative to the run root: %r" % text)
    target = (base / candidate).resolve()
    if target != base and base not in target.parents:
        raise OutOfPipeline("artifact path escapes the run root: %r" % text)
    rel = target.relative_to(base).as_posix()
    if rel in ("", "."):
        raise OutOfPipeline("artifact path is the run root itself: %r" % text)
    return rel


def registry_path(root):
    return Path(root).resolve() / "private" / "governed-outputs.json"


def register_root(root):
    """Declaration of one governed run root (item 4: explicit scope)."""
    base = Path(root).resolve()
    if not base.is_dir():
        raise OutOfPipeline("run root does not exist: %s" % base)
    return {"root": str(base)}


def _sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def _digest(value, field):
    text = str(value or "").strip()
    if text.startswith("sha256:"):
        text = text[7:]
    if len(text) != 64 or any(ch not in "0123456789abcdef" for ch in text):
        raise OutOfPipeline("%s must be a 64-hex sha256 digest, got %r" % (field, value))
    return text


# --------------------------------------------------------------------------
# the registry
# --------------------------------------------------------------------------

def load(root):
    path = registry_path(root)
    if not path.is_file():
        return {"schema": SCHEMA, "root": str(Path(root).resolve()), "outputs": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise OutOfPipeline("governed-outputs.json is unreadable: %s" % exc)
    if not isinstance(data, dict) or not isinstance(data.get("outputs"), dict):
        raise OutOfPipeline("governed-outputs.json is not a registry document")
    return data


def save(root, registry):
    path = registry_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(registry, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


# --------------------------------------------------------------------------
# the quarantine ledger (1.3.44)
# --------------------------------------------------------------------------
# A quarantined file is ACKNOWLEDGED as out-of-pipeline and stays out. The ledger
# can only make the scan stop refusing a file; it can never make a file governed:
# register() and close() refuse a quarantined path, a registered path cannot be
# quarantined, and delivery excludes quarantined files. Each entry carries an
# HMAC-SHA256 signature made with the operator key (SF_PIN_AUTHORITY_KEY_FILE),
# the same key and the same canonical-JSON signing the pin-rotation record uses.
# The key is read by path and never printed.

def ledger_path(root):
    return Path(root).resolve() / LEDGER_FILE


def _key_bytes(root, key_file=None):
    path = Path(key_file or os.environ.get("SF_PIN_AUTHORITY_KEY_FILE") or "")
    if not str(path) or str(path) == "." or not path.is_file():
        raise OutOfPipeline("operator key file not found (set SF_PIN_AUTHORITY_KEY_FILE)")
    real = path.resolve()
    base = Path(root).resolve()
    if real == base or base in real.parents:
        raise OutOfPipeline("operator key must live outside the run root")
    if real.stat().st_mode & 0o077:
        raise OutOfPipeline("operator key file must be mode 0600")
    key = real.read_bytes().strip()
    if len(key) < 16:
        raise OutOfPipeline("operator key is too short")
    return key


def _entry_signature(entry, key):
    body = {k: entry.get(k) for k in ENTRY_FIELDS}
    body["kind"] = LEDGER_KIND  # domain separation from the pin_rotation record
    return hmac.new(key, json.dumps(body, sort_keys=True, separators=(",", ":")).encode(),
                    hashlib.sha256).hexdigest()


def _read_ledger(root):
    """None when there is no ledger file; else {'entries': [...], 'error': str|None}."""
    path = ledger_path(root)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {"entries": [], "error": "quarantine ledger is unreadable: %s" % exc}
    entries = data.get("entries") if isinstance(data, dict) else None
    if not isinstance(entries, list):
        return {"entries": [], "error": "quarantine ledger is not a ledger document"}
    return {"entries": [e for e in entries if isinstance(e, dict)], "error": None}


def is_quarantined_path(root, path):
    """True when ANY ledger entry OR the signed seal names this path (valid or not): it can
    never be registered or closed without a signed release. A tampered, deleted or rolled-back
    entry must not reopen the door, because the seal still lists the path."""
    try:
        rel = normalise(root, path)
    except OutOfPipeline:
        return False
    return rel in _ledger_status(root)["paths"]


def quarantine(root, path, *, reason, approver, key_file=None, now=None):
    """Acknowledge one UNREGISTERED file as out-of-pipeline, signed with the operator key."""
    base = Path(root).resolve()
    rel = normalise(base, path)
    if rel.split("/", 1)[0] in INTERNAL_DIRS:
        raise OutOfPipeline("%s is run-internal machinery, not a file to quarantine" % rel)
    for field, value in (("reason", reason), ("approver", approver)):
        if not str(value or "").strip():
            raise OutOfPipeline("quarantine needs a %s" % field)
    target = base / rel
    if not target.is_file():
        raise OutOfPipeline("%s does not exist, so it cannot be quarantined" % rel)
    if rel in load(base)["outputs"]:
        raise OutOfPipeline("%s is a registered pipeline output; a governed file cannot be "
                            "quarantined (that would hide a mismatch)" % rel)
    key = _key_bytes(base, key_file)
    status = _ledger_status(base, key)
    if status["exists"] and not status["ok"]:
        raise OutOfPipeline("the quarantine ledger cannot be extended: %s" % status["why"])
    entry = {
        "path": rel, "sha256": _sha256_file(target), "size": target.stat().st_size,
        "reason": str(reason).strip(),
        "quarantined_at": (now or datetime.now(timezone.utc)).isoformat(),
        "approver": str(approver).strip(),
    }
    entry["signature"] = _entry_signature(entry, key)
    entries = [e for e in status["entries"] if e.get("path") != rel] + [entry]
    _write_ledger(base, entries, key, now=now)
    return entry


def _write_ledger(base, entries, key, *, now=None):
    path_out = ledger_path(base)
    path_out.parent.mkdir(parents=True, exist_ok=True)
    path_out.write_text(json.dumps({"schema": LEDGER_SCHEMA, "entries": entries},
                                   indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_seal(base, entries, key, now=now)


# --------------------------------------------------------------------------
# the signed seal over the ledger (1.3.47)
# --------------------------------------------------------------------------
# The ledger file is only a list; under M an actor can delete an entry, or put an older
# copy of the file back. The seal is a SEPARATE key-signed record of exactly which
# (path, entry signature) pairs the ledger holds, with a serial that only grows. A ledger
# that disagrees with its seal is broken: nothing is honoured, no path is registered or
# closed, and the deleted path is still named by the seal. An anchor outside the run folder
# (next to the key, or SF_SEAL_ANCHOR_DIR) remembers the newest serial, so putting back an
# older ledger AND an older seal is caught too.

def seal_path(root):
    return Path(root).resolve() / SEAL_FILE


def _seal_signature(doc, key):
    body = {"kind": SEAL_KIND, "serial": doc.get("serial"), "sealed_at": doc.get("sealed_at"),
            "entries": doc.get("entries")}
    return hmac.new(key, _canonical_json(body), hashlib.sha256).hexdigest()


def _anchor_file(root, key_file=None):
    folder = os.environ.get("SF_SEAL_ANCHOR_DIR")
    if not folder:
        keyfile = Path(key_file or os.environ.get("SF_PIN_AUTHORITY_KEY_FILE") or "")
        if not str(keyfile) or str(keyfile) == ".":
            return None
        folder = str(keyfile.resolve().parent / "sf-seal-anchors")
    ident = hashlib.sha256(str(Path(root).resolve()).encode()).hexdigest()[:32]
    return Path(folder) / (ident + ".json")


def _read_anchor(root):
    path = _anchor_file(root)
    if path is None or not path.is_file():
        return None
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"serial": float("inf"), "seal_signature": None}   # unreadable anchor: fail closed
    return doc if isinstance(doc, dict) else {"serial": float("inf"), "seal_signature": None}


def _write_seal(base, entries, key, *, now=None):
    old = _read_seal(base)
    serial = int(old.get("serial") or 0) + 1 if isinstance(old, dict) else 1
    anchor = _read_anchor(base)
    if anchor and isinstance(anchor.get("serial"), int):
        serial = max(serial, anchor["serial"] + 1)
    doc = {"schema": SEAL_SCHEMA, "serial": serial,
           "sealed_at": (now or datetime.now(timezone.utc)).isoformat(),
           "entries": sorted(([e.get("path"), e.get("signature")] for e in entries),
                             key=lambda row: (str(row[0]), str(row[1])))}
    doc["signature"] = _seal_signature(doc, key)
    out = seal_path(base)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    anchor_path = _anchor_file(base)
    if anchor_path is not None:
        try:
            anchor_path.parent.mkdir(parents=True, exist_ok=True)
            anchor_path.write_text(json.dumps({"serial": serial, "seal_signature": doc["signature"]}),
                                   encoding="utf-8")
        except OSError:
            pass   # an anchor that cannot be written is simply absent; the seal still stands
    return doc


def _read_seal(root):
    path = seal_path(root)
    if not path.is_file():
        return None
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"unreadable": True}
    return doc if isinstance(doc, dict) else {"unreadable": True}


def _ledger_status(root, key=None):
    """The one verdict on the quarantine ledger.

    {'exists', 'ok', 'why', 'entries' (dicts as read), 'paths' (ledger AND seal paths)}.
    `ok` is True only when a key is available, the seal verifies under it, the ledger holds
    exactly the (path, signature) pairs the seal lists, and the serial is not older than the
    anchor. No ledger and no seal at all is ok (nothing was ever quarantined)."""
    ledger = _read_ledger(root)
    seal = _read_seal(root)
    entries = ledger["entries"] if ledger else []
    paths = {e.get("path") for e in entries if isinstance(e.get("path"), str)}
    result = {"exists": ledger is not None or seal is not None, "ok": False, "why": None,
              "entries": entries, "paths": paths}
    if isinstance(seal, dict) and isinstance(seal.get("entries"), list):
        for row in seal["entries"]:
            if isinstance(row, (list, tuple)) and row and isinstance(row[0], str):
                paths.add(row[0])
    if ledger is None and seal is None:
        result.update(ok=True)
        return result
    if key is None:
        try:
            key = _key_bytes(root)
        except OutOfPipeline:
            result["why"] = "operator key unavailable, so the quarantine ledger cannot be verified"
            return result
    if ledger is not None and ledger["error"]:
        result["why"] = ledger["error"]
        return result
    if seal is None:
        result["why"] = ("the quarantine ledger has no signed seal (run quarantine_ledger.py seal "
                         "once, as the operator)")
        return result
    sig = seal.get("signature") if isinstance(seal, dict) else None
    if seal.get("unreadable") or not isinstance(seal.get("entries"), list) \
            or not isinstance(sig, str) or not isinstance(seal.get("serial"), int) \
            or not hmac.compare_digest(sig, _seal_signature(seal, key)):
        result["why"] = "the quarantine seal does not verify under the operator key"
        return result
    listed = sorted((str(r[0]), str(r[1])) for r in seal["entries"]
                    if isinstance(r, (list, tuple)) and len(r) == 2)
    held = sorted((str(e.get("path")), str(e.get("signature"))) for e in entries)
    if listed != held or len(listed) != len(seal["entries"]):
        result["why"] = ("the quarantine ledger does not match its signed seal (an entry was "
                         "deleted, added or replaced)")
        return result
    anchor = _read_anchor(root)
    if anchor is not None:
        serial = anchor.get("serial")
        if not isinstance(serial, (int, float)) or seal["serial"] < serial or (
                seal["serial"] == serial and anchor.get("seal_signature") != sig):
            result["why"] = ("the quarantine seal is older than the operator's anchor (the "
                             "ledger and seal were rolled back)")
            return result
    result["ok"] = True
    return result


def seal_ledger(root, *, key_file=None, now=None):
    """The operator adopts the ledger as it stands: every entry must verify, then one signed
    seal is written. Needed once for a ledger made before 1.3.47."""
    base = Path(root).resolve()
    key = _key_bytes(base, key_file)
    ledger = _read_ledger(base)
    if ledger is None:
        raise OutOfPipeline("there is no quarantine ledger to seal")
    if ledger["error"]:
        raise OutOfPipeline(ledger["error"])
    seen = set()
    for entry in ledger["entries"]:
        sig = entry.get("signature")
        if not isinstance(sig, str) or not hmac.compare_digest(sig, _entry_signature(entry, key)):
            raise OutOfPipeline("ledger entry %r does not verify; it cannot be sealed"
                                % entry.get("path"))
        if entry.get("path") in seen:
            raise OutOfPipeline("ledger names %r twice" % entry.get("path"))
        seen.add(entry.get("path"))
    doc = _write_seal(base, ledger["entries"], key, now=now)
    return {"serial": doc["serial"], "entries": len(ledger["entries"])}


def _quarantine_verdict(entry, key, target):
    """(acknowledged, why_not). Signature, then the file's current bytes."""
    if key is None:
        return False, "operator key unavailable, so the quarantine entry cannot be verified"
    sig = entry.get("signature")
    if not isinstance(sig, str) or not hmac.compare_digest(sig, _entry_signature(entry, key)):
        return False, "quarantine entry signature does not verify"
    if entry.get("sha256") != _sha256_file(target) or entry.get("size") != target.stat().st_size:
        return False, "the file changed after it was quarantined"
    return True, None



def _ledger_entry(root, rel):
    ledger = _read_ledger(root)
    if ledger is None:
        return None
    return next((e for e in ledger["entries"] if e.get("path") == rel), None)


# --------------------------------------------------------------------------
# signed admission records (1.3.46)
# --------------------------------------------------------------------------
# Every decision the governor writes is signed with the operator key (HMAC-SHA256,
# domain-separated, tagged 'admission_record'). A row that is unsigned, signed with
# another key, or edited after signing is ignored by every consumer.

def _canonical_json(value):
    plain = json.loads(json.dumps(value, default=str))   # one spelling, as read back from disk
    return json.dumps(plain, sort_keys=True, separators=(",", ":")).encode()


def admission_signature(decision, key):
    body = {k: v for k, v in decision.items() if k != "signature"}
    return hmac.new(key, _canonical_json({"domain": ADMISSION_KIND, "record": body}),
                    hashlib.sha256).hexdigest()


def sign_admission(root, decision, *, key_file=None, now=None):
    """Stamp `signed_at` and `signature` onto one governor decision. Returns True when
    signed; False (row stays unsigned, and is never trusted) when no operator key is usable."""
    try:
        key = _key_bytes(root, key_file)
    except OutOfPipeline:
        return False
    decision.pop("signature", None)
    decision["signed_at"] = (now or datetime.now(timezone.utc)).isoformat()
    decision["signature"] = admission_signature(decision, key)
    return True


def verify_admission(decision, key):
    if key is None or not isinstance(decision, dict):
        return False
    sig = decision.get("signature")
    return isinstance(sig, str) and isinstance(decision.get("signed_at"), str) \
        and hmac.compare_digest(sig, admission_signature(decision, key))


def _parse_time(text):
    try:
        value = datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


# --------------------------------------------------------------------------
# signed release-quarantine and reown records (1.3.47)
# --------------------------------------------------------------------------
# 1.3.46 let a quarantined path be closed over bytes an unsigned stage-executor-record.json
# listed. Under M anyone can write that file, so it proved nothing (SWB-231 B08, B09, B10).
# The ONLY way a quarantined path is registered or closed now is a record the operator signs:
#   * release-quarantine: path + sha256 + stage + reason + approver + time (+ a note). It is
#     valid while the file's current sha256 equals the record's, the record's stage is the
#     stage asking, and the bytes differ from the quarantined bytes. The owner signs it AFTER
#     the stage regenerated the file. The note prints the executor-record row the signer saw
#     as EVIDENCE; nothing is trusted from that file.
#   * reown: path + sha256 + new owner stage + reason + approver + time (+ a note). It re-owns a
#     registered file to a stage, valid while the file's sha256 equals the record's. It replaces
#     the content-claimed owner rules (sidecar JSON, board siblings, byte-equal receipt hashes).

def _record_signature(kind, fields, entry, key):
    body = {k: entry.get(k) for k in fields}
    body["kind"] = kind     # each record type has its own tag: no record verifies as another
    return hmac.new(key, json.dumps(body, sort_keys=True, separators=(",", ":")).encode(),
                    hashlib.sha256).hexdigest()


def _read_records(root, rel_file):
    try:
        data = json.loads((Path(root).resolve() / rel_file).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    entries = data.get("entries") if isinstance(data, dict) else None
    return [e for e in entries if isinstance(e, dict)] if isinstance(entries, list) else []


def _write_records(root, rel_file, schema, entries):
    out = Path(root).resolve() / rel_file
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"schema": schema, "entries": entries}, indent=2, sort_keys=True) + "\n",
                   encoding="utf-8")


def _record_ok(kind, fields, entry, key):
    sig = entry.get("signature")
    return isinstance(sig, str) and hmac.compare_digest(sig, _record_signature(kind, fields, entry, key))


def _executor_evidence(base, rel, digest):
    """Text for a signing note only: which executor record rows name `rel`. Never trusted."""
    seen = []
    for record in sorted(base.glob("*/" + EXECUTOR_RECORD)):
        if record.parent.name in INTERNAL_DIRS:
            continue
        try:
            data = json.loads(record.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        for entry in (data.get("images") or []) + (data.get("items") or []):
            if isinstance(entry, dict) and entry.get("file") == rel:
                seen.append("%s lists %s sha256=%s (%s the bytes now on disk)" % (
                    record.relative_to(base).as_posix(), rel, entry.get("sha256"),
                    "equals" if entry.get("sha256") == digest else "does NOT equal"))
    return ("executor-record evidence (unsigned, shown only): " + "; ".join(seen)) if seen else \
        "executor-record evidence (unsigned, shown only): no row names this path"


def release_quarantine(root, path, *, stage, reason, approver, in_scope=None,
                       key_file=None, now=None):
    """Sign: stage `stage` may register and close the quarantined `path` over the bytes on
    disk now. Refused unless the path is a verified quarantine entry, the bytes differ from the
    quarantined bytes, and `in_scope(path, stage)` says the stage writes that path."""
    base = Path(root).resolve()
    rel = normalise(base, path)
    for field, value in (("stage", stage), ("reason", reason), ("approver", approver)):
        if not str(value or "").strip():
            raise OutOfPipeline("a quarantine release needs a %s" % field)
    if in_scope is None or not in_scope(rel, str(stage)):
        raise OutOfPipeline("%s is not a path stage %r writes; it cannot be released to it" % (rel, stage))
    key = _key_bytes(base, key_file)
    status = _ledger_status(base, key)
    if not status["ok"]:
        raise OutOfPipeline("the quarantine ledger is not sound: %s" % status["why"])
    led = next((e for e in status["entries"] if e.get("path") == rel), None)
    if led is None:
        raise OutOfPipeline("%s is not quarantined" % rel)
    sig = led.get("signature")
    if not isinstance(sig, str) or not hmac.compare_digest(sig, _entry_signature(led, key)):
        raise OutOfPipeline("the quarantine entry for %s does not verify" % rel)
    target = base / rel
    if not target.is_file():
        raise OutOfPipeline("%s does not exist" % rel)
    digest = _sha256_file(target)
    if digest == led.get("sha256"):
        raise OutOfPipeline("%s still holds its quarantined bytes; the stage has not regenerated it" % rel)
    entry = {"path": rel, "sha256": digest, "stage": str(stage).strip(),
             "reason": str(reason).strip(), "approver": str(approver).strip(),
             "signed_at": (now or datetime.now(timezone.utc)).isoformat(),
             "note": _executor_evidence(base, rel, digest)}
    entry["signature"] = _record_signature(RELEASE_KIND, RELEASE_FIELDS, entry, key)
    entries = [e for e in _read_records(base, RELEASE_FILE)
              if not (e.get("path") == rel and e.get("stage") == entry["stage"])] + [entry]
    _write_records(base, RELEASE_FILE, RELEASE_SCHEMA, entries)
    return entry


def find_release(root, rel, stage, in_scope=None):
    """The valid signed release record for exactly (rel, stage, the bytes on disk now), or None."""
    if in_scope is None or not in_scope(rel, str(stage)):
        return None
    try:
        key = _key_bytes(root)
    except OutOfPipeline:
        return None
    status = _ledger_status(root, key)
    if not status["ok"]:
        return None
    led = next((e for e in status["entries"] if e.get("path") == rel), None)
    target = Path(root).resolve() / rel
    if led is None or not target.is_file():
        return None
    sig = led.get("signature")
    if not isinstance(sig, str) or not hmac.compare_digest(sig, _entry_signature(led, key)):
        return None
    digest = _sha256_file(target)
    if digest == led.get("sha256"):
        return None
    for entry in _read_records(root, RELEASE_FILE):
        if entry.get("path") == rel and entry.get("stage") == str(stage) \
                and entry.get("sha256") == digest and _record_ok(RELEASE_KIND, RELEASE_FIELDS, entry, key):
            return entry
    return None


def _receipt_listing(base, rel):
    found = []
    folder = base / "private" / "receipts"
    try:
        names = sorted(folder.glob("*.json"))
    except OSError:
        names = []
    for name in names:
        try:
            doc = json.loads(name.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(doc, dict) and doc.get("status") == "pass" \
                and rel in (doc.get("artifact_hashes") or {}):
            found.append(name.stem)
    return found


def reown(root, path, *, owner_stage, reason, approver, key_file=None, now=None):
    """Sign: the registered file `path`, as it is now, belongs to `owner_stage`. The evidence
    sentence in `reason` is the operator's; the note adds what the registry and receipts say."""
    base = Path(root).resolve()
    rel = normalise(base, path)
    for field, value in (("owner stage", owner_stage), ("reason", reason), ("approver", approver)):
        if not str(value or "").strip():
            raise OutOfPipeline("a reown record needs a %s" % field)
    registered = load(base)["outputs"].get(rel)
    if registered is None or registered.get("state") != EMITTED:
        raise OutOfPipeline("%s is not a registered, emitted output, so it cannot be re-owned" % rel)
    target = base / rel
    if not target.is_file():
        raise OutOfPipeline("%s does not exist" % rel)
    key = _key_bytes(base, key_file)
    listed = _receipt_listing(base, rel)
    entry = {"path": rel, "sha256": _sha256_file(target), "owner_stage": str(owner_stage).strip(),
             "reason": str(reason).strip(), "approver": str(approver).strip(),
             "signed_at": (now or datetime.now(timezone.utc)).isoformat(),
             "note": "registry owner %r; pass receipts listing this exact path: %s (shown only)" % (
                 registered.get("stage"), ", ".join(listed) or "none")}
    entry["signature"] = _record_signature(REOWN_KIND, REOWN_FIELDS, entry, key)
    entries = [e for e in _read_records(base, REOWN_FILE) if e.get("path") != rel] + [entry]
    _write_records(base, REOWN_FILE, REOWN_SCHEMA, entries)
    return entry


def reowned_to(root, rel, actual_sha256):
    """The owner stage a valid signed reown record gives `rel` while its bytes are `actual_sha256`."""
    try:
        key = _key_bytes(root)
    except OutOfPipeline:
        return None
    for entry in _read_records(root, REOWN_FILE):
        if entry.get("path") == rel and actual_sha256 and entry.get("sha256") == actual_sha256 \
                and _record_ok(REOWN_KIND, REOWN_FIELDS, entry, key):
            return entry.get("owner_stage")
    return None


# --------------------------------------------------------------------------
# signed input acknowledgements (1.3.46)
# --------------------------------------------------------------------------

def ack_path(root):
    return Path(root).resolve() / ACK_FILE


def _ack_signature(entry, key):
    body = {k: entry.get(k) for k in ACK_FIELDS}
    body["kind"] = ACK_KIND
    return hmac.new(key, json.dumps(body, sort_keys=True, separators=(",", ":")).encode(),
                    hashlib.sha256).hexdigest()


def _read_acks(root):
    try:
        data = json.loads(ack_path(root).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    entries = data.get("entries") if isinstance(data, dict) else None
    return [e for e in entries if isinstance(e, dict)] if isinstance(entries, list) else []


def acknowledge_input(root, path, *, old_sha256, new_sha256, reason, approver,
                      key_file=None, now=None):
    """Sign an acknowledgement that the declared input `path` changed from old to new.
    It is valid only while the file's sha256 equals `new_sha256` and the registry still
    holds `old_sha256`. It never alters the registry or the file."""
    base = Path(root).resolve()
    rel = normalise(base, path)
    old, new = _digest(old_sha256, "old sha256"), _digest(new_sha256, "new sha256")
    for field, value in (("reason", reason), ("approver", approver)):
        if not str(value or "").strip():
            raise OutOfPipeline("an input acknowledgement needs a %s" % field)
    target = base / rel
    if not target.is_file():
        raise OutOfPipeline("%s does not exist" % rel)
    if _sha256_file(target) != new:
        raise OutOfPipeline("%s does not hold the acknowledged new sha256 now" % rel)
    if (load(base)["outputs"].get(rel) or {}).get("sha256") != old:
        raise OutOfPipeline("%s is not registered with the acknowledged old sha256" % rel)
    key = _key_bytes(base, key_file)
    entry = {"path": rel, "old_sha256": old, "new_sha256": new,
             "reason": str(reason).strip(), "approver": str(approver).strip(),
             "acknowledged_at": (now or datetime.now(timezone.utc)).isoformat()}
    entry["signature"] = _ack_signature(entry, key)
    entries = [e for e in _read_acks(base)
               if not (e.get("path") == rel and e.get("new_sha256") == new)] + [entry]
    out = ack_path(base)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"schema": ACK_SCHEMA, "entries": entries},
                              indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return entry


def input_acknowledged(root, row):
    """True when a valid signed acknowledgement covers this `input_changed` row (path, the
    registered old hash, and the actual new hash that is on disk now)."""
    try:
        key = _key_bytes(root)
    except OutOfPipeline:
        return False
    for entry in _read_acks(root):
        sig = entry.get("signature")
        if entry.get("path") == row.get("path") and entry.get("old_sha256") == row.get("registered") \
                and entry.get("new_sha256") == row.get("actual") \
                and isinstance(sig, str) and hmac.compare_digest(sig, _ack_signature(entry, key)):
            return True
    return False


def _refuse_unsound_ledger(root):
    status = _ledger_status(root)
    if status["exists"] and not status["ok"]:
        raise OutOfPipeline("the quarantine ledger is not sound, so nothing is registered or closed: %s"
                            % status["why"])


def register(root, path, *, stage, item=None, expected_sha256=None, producer=None, in_scope=None):
    """Register one output BEFORE the producer writes it (item 5)."""
    rel = normalise(root, path)
    _refuse_unsound_ledger(root)
    if is_quarantined_path(root, rel) and find_release(root, rel, stage, in_scope) is None:
        raise OutOfPipeline("%s is quarantined (out of the pipeline) and can never be registered "
                            "(no signed release-quarantine record for stage %r and the bytes on "
                            "disk now)" % (rel, stage))
    if not str(stage or "").strip():
        raise OutOfPipeline("register() needs the canonical stage the output belongs to")
    registry = load(root)
    entry = {"path": rel, "stage": str(stage), "state": IN_PROGRESS}
    for key, value in (("item", item), ("producer", producer)):
        if value not in (None, ""):
            entry[key] = str(value)
    if expected_sha256 not in (None, ""):
        entry["expected_sha256"] = _digest(expected_sha256, "expected_sha256")
    existing = registry["outputs"].get(rel)
    if existing is not None:
        # Re-registering the same binding is idempotent; rebinding an existing
        # output to a different stage/item is a refusal, not a silent overwrite.
        for key in ("stage", "item"):
            if existing.get(key) != entry.get(key):
                raise OutOfPipeline(
                    "output %s is already registered to %s=%r; it cannot be rebound to %r"
                    % (rel, key, existing.get(key), entry.get(key)))
        if entry.get("expected_sha256") and existing.get("expected_sha256") \
                and entry["expected_sha256"] != existing["expected_sha256"]:
            raise OutOfPipeline("output %s is re-registered with a different expected hash" % rel)
        existing.update({k: v for k, v in entry.items() if k not in ("path", "state")})
        registry["outputs"][rel] = existing
    else:
        registry["outputs"][rel] = entry
    save(root, registry)
    return registry["outputs"][rel]


def close(root, path, *, stage, sha256=None, in_scope=None):
    """Mark one registered output emitted, binding the bytes that were written."""
    rel = normalise(root, path)
    _refuse_unsound_ledger(root)
    quarantined = is_quarantined_path(root, rel)
    release = find_release(root, rel, stage, in_scope) if quarantined else None
    if quarantined and release is None:
        raise OutOfPipeline("%s is quarantined (out of the pipeline) and can never be closed "
                            "(no signed release-quarantine record for stage %r and the bytes on "
                            "disk now)" % (rel, stage))
    registry = load(root)
    entry = registry["outputs"].get(rel)
    if entry is None:
        raise OutOfPipeline("output %s was never registered before it was written" % rel)
    if entry.get("stage") != str(stage):
        raise OutOfPipeline("output %s belongs to stage %r, not %r"
                            % (rel, entry.get("stage"), stage))
    target = Path(root).resolve() / rel
    if sha256 in (None, ""):
        if not target.is_file():
            raise OutOfPipeline("output %s does not exist, so it cannot be closed" % rel)
        digest = _sha256_file(target)
    else:
        digest = _digest(sha256, "sha256")
    if quarantined:
        # Closed only over the exact bytes the operator signed a release for. No executor
        # record, sidecar or receipt is consulted: under M each is a file anyone can write.
        if not target.is_file() or _sha256_file(target) != digest:
            raise OutOfPipeline("quarantined path %s can only be closed over the bytes now on "
                                "disk" % rel)
        if release.get("sha256") != digest:
            raise OutOfPipeline("quarantined path %s: the signed release is for other bytes" % rel)
    expected = entry.get("expected_sha256")
    if expected and expected != digest:
        raise OutOfPipeline("output %s emitted %s but was registered as %s"
                            % (rel, digest, expected))
    entry["state"] = EMITTED
    entry["sha256"] = digest
    registry["outputs"][rel] = entry
    save(root, registry)
    return entry


# --------------------------------------------------------------------------
# the scan
# --------------------------------------------------------------------------

def _json_shape_ok(path, required_keys):
    """True when `path` is a JSON object (not a list, image or text) holding every key."""
    try:
        if path.stat().st_size > RUN_STATE_MAX_BYTES:
            return False
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if not isinstance(doc, dict) or not all(k in doc for k in required_keys):
        return False
    if "calls" in required_keys and not isinstance(doc.get("calls"), list):
        return False
    return True


def run_state_name(rel):
    """The run-state name `rel` is, or None. Root level, exact equality, nothing else."""
    return rel if rel in RUN_STATE_FILES and "/" not in rel else None


def is_run_state(rel, entry, path):
    """A registered, emitted, root-level file on the closed list with the right shape."""
    name = run_state_name(rel)
    return bool(name and entry and entry.get("state") == EMITTED
                and _json_shape_ok(path, RUN_STATE_SHAPES[name]))


def declared_brand_input(base, outputs):
    """The one brand file the run's own intake names (`brand_file`), or None.

    Exact, root-level, registered under the intake stage, and a JSON brand profile
    (it carries `brand_id`). Anything else the intake names is not a brand input."""
    try:
        intake = json.loads((base / "intake.json").read_text(encoding="utf-8"))
        name = intake.get("brand_file")
    except (OSError, ValueError, AttributeError):
        return None
    if not isinstance(name, str) or not name or "/" in name or name in INTERNAL_DIRS \
            or name.startswith("."):
        return None
    entry = outputs.get(name)
    target = base / name
    if entry is None or entry.get("stage") != "intake" or entry.get("state") != EMITTED \
            or not target.is_file() or not _json_shape_ok(target, ("brand_id",)):
        return None
    return name


def _pinned_brand_hashes(base):
    found = {}
    for doc in ("launch.json", "page-request.json"):
        try:
            value = json.loads((base / doc).read_text(encoding="utf-8")).get("brand_hash")
        except (OSError, ValueError, AttributeError):
            value = None
        if isinstance(value, str) and value:
            found[doc] = value
    return found


def _walk(root):
    base = Path(root).resolve()
    for path in sorted(base.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(base).as_posix()
        if rel.split("/", 1)[0] in INTERNAL_DIRS:
            continue
        yield rel, path


def _receipt_paths(receipts):
    """Every artifact a receipt claims, as exact normalised paths and resources."""
    paths, resources = [], []
    for entry in receipts or []:
        if isinstance(entry, dict):
            path, resource = entry.get("path"), entry.get("resource_id")
            digest = entry.get("sha256")
        else:
            path, resource, digest = entry, None, None
        if path:
            paths.append((str(path), digest))
        elif resource:
            resources.append((str(resource), digest))
    return paths, resources


def scan(root, *, receipts=None, declared_native=None, inputs=()):
    """Compare the run's real files against the registry and the receipts.

    `inputs` are the exact paths of the run's canonical INPUT documents (intake,
    page-request, launch record, brand, manuscript). They are read, not produced,
    so they are reported under `inputs` and are never mistaken for ungoverned
    output -- or for pipeline credit.

    Returns a result whose `ok` is False for anything that did not come through
    the pipeline. Failures are named by exact path/resource -- never by
    substring.
    """
    base = Path(root).resolve()
    if not base.is_dir():
        raise OutOfPipeline("run root does not exist: %s" % base)
    registered_inputs = set()
    for raw in inputs or ():
        registered_inputs.add(normalise(base, raw))
    registry = load(base)
    outputs = registry["outputs"]
    result = {
        "schema": SCHEMA,
        "root": str(base),
        "declared_roots": [register_root(base)],
        "governed": [],
        "inputs": [],
        "registered_unfinished": [],
        "ungoverned": [],
        "content_mismatch": [],
        "run_state_changed": [],
        "input_changed": [],
        "receipt_unregistered": [],
        "native_unregistered": [],
    }
    status = _ledger_status(base)
    ledger_by_path = {}
    key = None
    if status["exists"]:
        result["quarantined"] = []
        for led in status["entries"]:
            ledger_by_path.setdefault(led.get("path"), led)
        if not status["ok"]:
            result["quarantine_ledger_error"] = status["why"]
        else:
            try:
                key = _key_bytes(base)
            except OutOfPipeline:
                key = None
    brand_input = declared_brand_input(base, outputs)
    for rel, path in _walk(base):
        entry = outputs.get(rel)
        if rel in registered_inputs and not (
                rel == brand_input and entry is not None and entry.get("state") == EMITTED
                and entry.get("sha256") != _sha256_file(path)):
            # 1.3.47: the declared brand file is checked even when its name is also a stage input
            # (brand.json); every other declared input is read, not produced.
            result["inputs"].append(rel)
            continue
        if entry is None:
            led = ledger_by_path.get(rel)
            if led is not None:
                ok_q, why = (False, "the quarantine ledger is not sound: %s" % status["why"]) \
                    if not status["ok"] else _quarantine_verdict(led, key, path)
                if ok_q:
                    result["quarantined"].append({
                        "path": rel, "sha256": led["sha256"], "size": led["size"],
                        "reason": led.get("reason"), "approver": led.get("approver")})
                    continue
                result["ungoverned"].append({"path": rel, "reason": "not registered with the "
                                             "pipeline; " + why})
                continue
            result["ungoverned"].append({"path": rel, "reason": "not registered with the pipeline"})
            continue
        if entry.get("state") == IN_PROGRESS:
            result["registered_unfinished"].append({"path": rel, "stage": entry.get("stage")})
            continue
        digest = _sha256_file(path)
        if entry.get("sha256") != digest and is_run_state(rel, entry, path):
            result["run_state_changed"].append({
                "path": rel, "registered": entry.get("sha256"), "actual": digest,
                "reason": "run state rewritten by the pipeline on every dispatch (closed list)"})
            continue
        if entry.get("sha256") != digest and rel == brand_input:
            row = {"path": rel, "registered": entry.get("sha256"), "actual": digest,
                   "reason": "brand input named by intake.json brand_file was edited after it "
                             "was attested"}
            pins = {k: v for k, v in _pinned_brand_hashes(base).items() if v != digest}
            if pins:
                row["stale_brand_pins"] = pins
            result["input_changed"].append(row)
            continue
        if entry.get("sha256") != digest:
            result["content_mismatch"].append({
                "path": rel, "registered": entry.get("sha256"), "actual": digest})
            continue
        result["governed"].append({"path": rel, "stage": entry.get("stage"),
                                   "sha256": digest})

    claimed_paths, claimed_resources = _receipt_paths(receipts)
    for raw, digest in claimed_paths:
        try:
            rel = normalise(base, raw)
        except OutOfPipeline as exc:
            result["receipt_unregistered"].append({"path": str(raw), "reason": str(exc)})
            continue
        entry = outputs.get(rel)
        if entry is None:
            result["receipt_unregistered"].append(
                {"path": rel, "reason": "the receipt names a path the pipeline never registered"})
            continue
        if digest not in (None, "") and entry.get("sha256") \
                and _digest(digest, "receipt sha256") != entry["sha256"]:
            result["receipt_unregistered"].append(
                {"path": rel, "reason": "the receipt's hash is not this pipeline output's hash"})

    declared = {}
    for entry in declared_native or []:
        if isinstance(entry, dict) and entry.get("resource_id"):
            declared[str(entry["resource_id"])] = (
                _digest(entry["sha256"], "native sha256") if entry.get("sha256") else None)
    for resource, digest in claimed_resources:
        if resource not in declared:
            result["native_unregistered"].append(
                {"resource_id": resource,
                 "reason": "the receipt names a native resource outside the declared set"})
            continue
        if digest not in (None, "") and declared[resource] \
                and _digest(digest, "receipt sha256") != declared[resource]:
            result["native_unregistered"].append(
                {"resource_id": resource,
                 "reason": "the receipt's hash is not the declared resource hash"})

    result["ok"] = not (result["ungoverned"] or result["content_mismatch"]
                        or result["receipt_unregistered"] or result["native_unregistered"])
    return result


def require_governed(root, *, receipts=None, declared_native=None, inputs=()):
    """Fail closed: raise naming every piece of out-of-pipeline output."""
    result = scan(root, receipts=receipts, declared_native=declared_native,
                  inputs=inputs)
    if result["ok"]:
        return result
    lines = []
    for bucket in ("ungoverned", "content_mismatch",
                   "receipt_unregistered", "native_unregistered"):
        for entry in result[bucket]:
            lines.append("%s: %s (%s)" % (bucket, entry.get("path") or entry.get("resource_id"),
                                          entry.get("reason")))
    raise OutOfPipeline(
        "out-of-pipeline output refused for %s: %s" % (result["root"], "; ".join(lines)))
    return result


# --------------------------------------------------------------------------
# item 6 - unadmitted output earns nothing and is preserved
# --------------------------------------------------------------------------

def excluded_paths(result):
    """Every path that may not earn delivery, credit, install or publish."""
    names = []
    for bucket in ("ungoverned", "content_mismatch", "run_state_changed", "input_changed"):
        names.extend(entry["path"] for entry in result.get(bucket, ()))
    # A quarantined file is acknowledged as out-of-pipeline: it never earns
    # delivery, credit, installation or publication.
    names.extend(entry["path"] for entry in result.get("quarantined", ()))
    return sorted(set(names))


def delivery(artifacts, result):
    """Split a result's artifacts into admitted and unadmitted (item 6).

    An unadmitted artifact is not deleted: it is reported, marked unverified, and
    excluded from delivery, progress credit, installation and publication.
    """
    blocked = set(excluded_paths(result))
    quarantined = {entry["path"] for entry in result.get("quarantined", ())}
    unfinished = {entry["path"] for entry in result["registered_unfinished"]}
    admitted, excluded = [], []
    for entry in artifacts or []:
        path = entry.get("path") if isinstance(entry, dict) else None
        if path is None:
            admitted.append(entry)  # a native resource is compared by the scan, not here
            continue
        if path in blocked:
            row = {**entry, "verified": False,
                   "excluded_from": ["delivery", "progress_credit",
                                     "installation", "publication"]}
            if path in quarantined:
                row["reason"] = "quarantined: acknowledged as out of the pipeline"
            excluded.append(row)
        elif path in unfinished:
            excluded.append({**entry, "verified": False,
                             "excluded_from": ["delivery", "progress_credit",
                                               "installation", "publication"],
                             "reason": "registered but unfinished"})
        else:
            admitted.append(entry)
    return {"admitted": admitted, "excluded": excluded, "preserved": True}


# --------------------------------------------------------------------------
# self-check
# --------------------------------------------------------------------------

def self_test():
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "a").mkdir()
        (root / "a" / "page.html").write_text("<p>one</p>", encoding="utf-8")
        (root / "a" / "old-page.html").write_text("<p>old</p>", encoding="utf-8")
        (root / "a" / "draft.png").write_bytes(b"png")

        register(root, "a/page.html", stage="responsive-html")
        close(root, "a/page.html", stage="responsive-html")
        register(root, "a/draft.png", stage="final-mockups")

        # Exact path identity: `old-page.html` is NOT admitted by `page.html`.
        result = scan(root, receipts=[{"path": "a/page.html"}])
        self_paths = excluded_paths(result)
        assert "a/old-page.html" in self_paths, result
        assert "a/page.html" not in self_paths, result
        # Registered-but-unfinished is distinguished from ungoverned (item 5).
        assert [e["path"] for e in result["registered_unfinished"]] == ["a/draft.png"], result
        assert result["ok"] is False

        split = delivery([{"path": "a/page.html"}, {"path": "a/old-page.html"},
                          {"path": "a/draft.png"}], result)
        assert [e["path"] for e in split["admitted"]] == ["a/page.html"]
        assert sorted(e["path"] for e in split["excluded"]) == \
            ["a/draft.png", "a/old-page.html"]
        assert all(e["verified"] is False for e in split["excluded"])

        # A receipt naming an unregistered path is refused by name.
        bad = scan(root, receipts=[{"path": "a/old-page.html"}])
        assert bad["receipt_unregistered"], bad

        # Content mismatch is ungoverned, not a pass.
        (root / "a" / "page.html").write_text("<p>changed</p>", encoding="utf-8")
        changed = scan(root)
        assert [e["path"] for e in changed["content_mismatch"]] == ["a/page.html"], changed


if __name__ == "__main__":
    self_test()
    print("out_of_pipeline self-test: PASS")
