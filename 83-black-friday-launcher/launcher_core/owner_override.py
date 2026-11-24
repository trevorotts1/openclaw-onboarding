"""SWB-094: the owner override for a client delivery that carries no page designs.

``package._verify_design_waiver`` refuses a design waiver for a client delivery (test_only false), and
that refusal stays for every caller. This module is the one narrow exception the OWNER of the
installation can use: a record signed with the operator key (the secret file named by
SF_OPERATOR_KEY_FILE, the same key Skill 49 signs its delegation receipts with). The record names the
plan hash it covers, the scope it overrides (only ``page_designs``) and the owner's own words. Whoever
does not hold the key cannot mint one, and a record that was edited after it was signed does not verify.

The key is never printed, never copied into a record and never returned: ``mint`` returns the record
(with its HMAC signature) and ``verify`` returns a list of plain reasons.

A package assembled on an override says so in its manifest (``owner_override``, marker ``OWNER OVERRIDE``)
and in its delivery label, so no reader can take it for a package that carries every design.
"""

from __future__ import annotations

import hashlib
import hmac
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

from .constants import SkillResolutionError, skill_path

CODE = "AF-LAUNCH-ASSEMBLE-OWNER-OVERRIDE"
KIND = "owner_override"
SCOPE_PAGE_DESIGNS = "page_designs"
SCOPES = (SCOPE_PAGE_DESIGNS,)
MARKER = "OWNER OVERRIDE"
SCHEMA = "skill83.owner-override/v1"
KEY_MODULE_REF = "scripts/prove_sf_cert.py"
FUNNEL_SKILL_SLUG = "signature-funnel"
_SIGNED_FIELDS = ("schema", "kind", "scope", "plan_hash", "owner_words", "granted_by", "note", "written_at")


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _operator_key(run_dir: Optional[Path] = None) -> Tuple[Optional[str], str]:
    """(key, reason) from Skill 49's own loader: >=32 chars, mode 0600, never inside the run dir."""
    try:
        path = skill_path(FUNNEL_SKILL_SLUG, KEY_MODULE_REF)
    except SkillResolutionError:
        return None, "Skill 49 (signature-funnel) is not installed, so the operator key cannot be read"
    if not path.is_file():
        return None, "Skill 49 prove_sf_cert.py is not installed, so the operator key cannot be read"
    spec = importlib.util.spec_from_file_location("s49_prove_sf_cert_for_override", path)
    if spec is None or spec.loader is None:
        return None, "Skill 49 prove_sf_cert.py could not be loaded"
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
        return module.load_operator_key(run_dir)
    except Exception as exc:  # noqa: BLE001  (a broken loader is a refusal, not a traceback)
        return None, f"the operator key loader failed ({type(exc).__name__})"


def _payload(record: Mapping[str, Any]) -> bytes:
    return json.dumps({k: record.get(k) for k in _SIGNED_FIELDS}, sort_keys=True,
                      separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _sign(record: Mapping[str, Any], key: str) -> str:
    return hmac.new(key.encode("utf-8"), _payload(record), hashlib.sha256).hexdigest()


def mint(plan_hash: str, scope: str, owner_words: List[str], note: str = "",
         run_dir: Optional[Path] = None) -> Dict[str, Any]:
    """The signed record, or ValueError naming why none can be made. Needs the operator key."""
    if scope not in SCOPES:
        raise ValueError(f"scope {scope!r} is not one an owner override covers {SCOPES}")
    if not (isinstance(plan_hash, str) and len(plan_hash) == 64):
        raise ValueError("plan_hash must be the 64-hex approved plan hash")
    words = [w for w in (owner_words or []) if _nonempty(w)]
    if not words:
        raise ValueError("an owner override records the owner's own words; none were given")
    key, why = _operator_key(run_dir)
    if key is None:
        raise ValueError(f"no operator key, so no owner override can be signed: {why}")
    record = {
        "schema": SCHEMA, "kind": KIND, "scope": scope, "plan_hash": plan_hash,
        "owner_words": words,
        "granted_by": "the holder of the operator key (the owner of this installation)",
        "note": note or "",
        "written_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    record["signature"] = _sign(record, key)
    return record


def verify(record: Any, plan_hash: str, scope: str = SCOPE_PAGE_DESIGNS,
           run_dir: Optional[Path] = None) -> List[str]:
    """Every reason ``record`` is not a valid owner override for this plan and scope. [] = valid."""
    if not isinstance(record, Mapping):
        return ["the owner override is not a JSON object"]
    fails: List[str] = []
    if record.get("schema") != SCHEMA or record.get("kind") != KIND:
        fails.append("the record is not a skill83.owner-override/v1 owner_override")
    if record.get("scope") != scope or scope not in SCOPES:
        fails.append(f"the record's scope is {record.get('scope')!r}, not {scope!r}")
    if record.get("plan_hash") != plan_hash or not _nonempty(plan_hash):
        fails.append("the record covers another plan hash than this package's")
    words = record.get("owner_words")
    if not (isinstance(words, list) and any(_nonempty(w) for w in words)):
        fails.append("the record carries none of the owner's own words")
    sig = record.get("signature")
    if not (_nonempty(sig) and len(sig) == 64):
        fails.append("the record is unsigned")
        return fails
    key, why = _operator_key(run_dir)
    if key is None:
        fails.append(f"the signature cannot be checked without the operator key: {why}")
        return fails
    if not hmac.compare_digest(_sign(record, key), sig):
        fails.append("the signature does not match the record (edited after signing, or signed with another key)")
    return fails


def accept(record: Any, plan_hash: str, run_dir: Optional[Path] = None) -> Dict[str, Any]:
    """The manifest entry for a verified override; raises ValueError listing every reason otherwise."""
    fails = verify(record, plan_hash, SCOPE_PAGE_DESIGNS, run_dir)
    if fails:
        raise ValueError("; ".join(fails))
    return {"marker": MARKER, "verified": True, **{k: record[k] for k in (*_SIGNED_FIELDS, "signature")}}
