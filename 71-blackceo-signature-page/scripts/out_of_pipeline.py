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

Stdlib only. No network. No execution. Never deletes anything.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

SCHEMA = "signature-launch-out-of-pipeline/v1"

# Run-internal machinery is not pipeline output: the registry, the stage gate's
# state and receipts, briefs and browser sessions all live under private/.
INTERNAL_DIRS = ("private",)

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


def register(root, path, *, stage, item=None, expected_sha256=None, producer=None):
    """Register one output BEFORE the producer writes it (item 5)."""
    rel = normalise(root, path)
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


def close(root, path, *, stage, sha256=None):
    """Mark one registered output emitted, binding the bytes that were written."""
    rel = normalise(root, path)
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
        "receipt_unregistered": [],
        "native_unregistered": [],
    }
    for rel, path in _walk(base):
        if rel in registered_inputs:
            result["inputs"].append(rel)
            continue
        entry = outputs.get(rel)
        if entry is None:
            result["ungoverned"].append({"path": rel, "reason": "not registered with the pipeline"})
            continue
        if entry.get("state") == IN_PROGRESS:
            result["registered_unfinished"].append({"path": rel, "stage": entry.get("stage")})
            continue
        digest = _sha256_file(path)
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
    for bucket in ("ungoverned", "content_mismatch"):
        names.extend(entry["path"] for entry in result[bucket])
    return sorted(set(names))


def delivery(artifacts, result):
    """Split a result's artifacts into admitted and unadmitted (item 6).

    An unadmitted artifact is not deleted: it is reported, marked unverified, and
    excluded from delivery, progress credit, installation and publication.
    """
    blocked = set(excluded_paths(result))
    unfinished = {entry["path"] for entry in result["registered_unfinished"]}
    admitted, excluded = [], []
    for entry in artifacts or []:
        path = entry.get("path") if isinstance(entry, dict) else None
        if path is None:
            admitted.append(entry)  # a native resource is compared by the scan, not here
            continue
        if path in blocked:
            excluded.append({**entry, "verified": False,
                             "excluded_from": ["delivery", "progress_credit",
                                               "installation", "publication"]})
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
