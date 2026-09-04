"""U028 -- atomic checkpointing and per-artifact-type validity predicates."""

import hashlib
import os
import pathlib
import tempfile
from typing import Any, Callable, Dict, Optional

PLACEHOLDER_MIN_BYTES: int = 51200
PNG_MAGIC: bytes = b"\x89PNG"


def atomic_write_bytes(path: pathlib.Path, data: bytes) -> None:
    dest_dir = path.parent
    dest_dir.mkdir(parents=True, exist_ok=True)
    fd = -1
    tmp_path = ""
    try:
        fd, tmp_path = tempfile.mkstemp(dir=str(dest_dir))
        os.write(fd, data)
        os.fsync(fd)
        os.close(fd)
        fd = -1
        os.replace(tmp_path, str(path))
    except Exception:
        if fd >= 0:
            try:
                os.close(fd)
            except OSError:
                pass
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
        raise


def atomic_write_text(path: pathlib.Path, text: str) -> None:
    atomic_write_bytes(path, text.encode("utf-8"))


def _image_predicate(path: pathlib.Path, sha256: Optional[str] = None) -> bool:
    if not path.exists():
        return False
    try:
        st = os.lstat(str(path))
    except OSError:
        return False
    if not __import__("stat").S_ISREG(st.st_mode):
        return False
    if st.st_size < PLACEHOLDER_MIN_BYTES:
        return False
    try:
        with open(str(path), "rb") as f:
            magic = f.read(4)
    except OSError:
        return False
    if magic != PNG_MAGIC:
        return False
    try:
        from PIL import Image
        Image.open(str(path)).verify()
    except Exception:
        return False
    if sha256 is not None:
        try:
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            return False
        if actual != sha256:
            return False
    return True


def _text_predicate(path: pathlib.Path, min_bytes: int = 0) -> bool:
    if not path.exists():
        return False
    try:
        st = os.lstat(str(path))
    except OSError:
        return False
    if not __import__("stat").S_ISREG(st.st_mode):
        return False
    return st.st_size >= min_bytes


PREDICATES: Dict[str, Callable] = {
    "image": _image_predicate,
    "text": _text_predicate,
}

# Disagreement rule: when state.json says done and the predicate says invalid,
# the PREDICATE WINS.  Treat the phase as not-done and re-enter.
# Rationale: re-rendering one slide costs one generation; shipping a corrupt
# slide costs the deck.  This is the OPPOSITE of the normal "state is truth"
# convention -- it is deliberate and must not be reversed.


def _state_store_update_phase(state_store: Any, phase_id: str,
                              artifact_type: str, fields: Dict) -> None:
    """FIX 26: write a predicate result through a real StateStore.

    The engine's StateStore has no update_phase method, so the old bridge was
    a permanent no-op. Take the store's in-memory state (or its load()),
    find/create the phase record by id, record fields[artifact_type] plus the
    remaining fields, and save atomically. Never raises into callers."""
    state = getattr(state_store, "state", None)
    if state is None:
        try:
            state = state_store.load()
        except Exception:
            return
    if not isinstance(state, dict):
        return
    phases = state.setdefault("phases", [])
    record = None
    for ps in phases:
        if isinstance(ps, dict) and ps.get("id") == phase_id:
            record = ps
            break
    if record is None:
        record = {"id": phase_id, "status": "pending", "artifacts": [],
                  "sha256": {}, "attempts": 0, "heal_events": [],
                  "attested_at": None}
        phases.append(record)
    # Predicate-scope results are written under "<type>_predicate_*" keys so
    # they can never collide with the phase record's real keys — most
    # importantly "sha256", which on an engine-managed phase record is the
    # {rel_path: digest} dict the attestation chain reads. Overwriting it with
    # the scalar predicate digest corrupts the recorded digest map.
    record[f"{artifact_type}_predicate_ok"] = fields.get("value", True)
    for k, v in fields.items():
        if k in ("value", "sha256"):
            if k == "sha256":
                record[f"{artifact_type}_predicate_sha256"] = v
            continue
        record[k] = v
    try:
        state_store.save(state)
    except Exception:
        pass


def checkpoint(state_store: Any, phase_id: str, artifact_type: str,
               **fields: Any) -> None:
    """FIX 26: the predicate path writes through a REAL store.

    The old bridge required a store with update_phase (nothing in this
    package provides one) and so silently dropped every result. Now: a
    duck-typed update_phase store is used as before (exactly what
    tests/test_checkpoint.py pins), otherwise the store is handled as a
    StateStore (state/load + save with state['phases']) and the phase record
    is updated directly. A store with neither shape is still a no-op —
    never raise, and a save failure never propagates."""
    if not hasattr(state_store, "update_phase") and not hasattr(state_store, "save"):
        return
    try:
        if hasattr(state_store, "update_phase"):
            state_store.update_phase(phase_id, artifact_type, **fields)
            return
        _state_store_update_phase(state_store, phase_id, artifact_type, dict(fields))
    except Exception:
        pass
