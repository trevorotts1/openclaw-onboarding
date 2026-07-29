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


def checkpoint(state_store: Any, phase_id: str, artifact_type: str,
               **fields: Any) -> None:
    if not hasattr(state_store, "update_phase"):
        return
    try:
        state_store.update_phase(phase_id, artifact_type, **fields)
    except Exception:
        pass
