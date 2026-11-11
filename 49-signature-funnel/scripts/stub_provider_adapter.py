#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""stub_provider_adapter.py — TEST-ONLY stand-in for a delegated provider tool.

A10 / T0-09: "the self-test must consume a fixture a provider stub produced, never
one the run authored." This module is that stub. It exists so a self-test can obtain
delegation receipts from a module that is NOT the orchestrator or a prover — the
`recorded_by` stamp delegation_receipt.record() derives from the call stack resolves
to `stub_provider_adapter`, which is not in delegation_receipt.SUBJECT_MODULES, so
the requirer accepts it. If a test tried to shortcut and write the same receipts from
the orchestrator, the stamp would read `run_signature_funnel` and the seam would
refuse it — which is precisely the property under test.

NEVER import this from a production path. It performs no network I/O and mints no
certificate; it only writes receipt lines that stand for calls a real adapter made.
"""

from __future__ import annotations

import atexit
import hashlib
import os
import shutil
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import delegation_receipt


def _stable_id(provider: str, phase: str, remote_id: str) -> str:
    """Deterministic across processes. Python salts str hashing per run, so a
    hash()-derived id would make a COMMITTED golden fixture churn every time it
    is regenerated."""
    digest = hashlib.sha256("|".join((provider, phase, str(remote_id)))
                            .encode("utf-8")).hexdigest()[:12]
    return f"{provider}-resp-{digest}"


def emit(run_dir: Path, phase: str, remote_ids: Sequence[str], *,
         provider: str = "kie", operation: str = "createTask",
         http_status: int = 200) -> List[Dict]:
    """Record one provider receipt per remote id, as a real adapter would."""
    out: List[Dict] = []
    for rid in remote_ids:
        out.append(delegation_receipt.record(
            run_dir, phase=phase, provider=provider, operation=operation,
            provider_response_id=_stable_id(provider, phase, rid),
            http_status=http_status, remote_id=str(rid), covers=[str(rid)]))
    return out


def emit_one(run_dir: Path, phase: str, remote_id: str, *,
             provider: str, operation: str, covers: Sequence[str] = (),
             http_status: int = 200, extra: Optional[Dict] = None) -> Dict:
    return delegation_receipt.record(
        run_dir, phase=phase, provider=provider, operation=operation,
        provider_response_id=_stable_id(provider, phase, remote_id),
        http_status=http_status, remote_id=str(remote_id),
        covers=[str(c) for c in (covers or [remote_id])], extra=extra)


def emit_rail(run_dir: Path, phase: str, rows: Sequence[Tuple[str, Dict]], *,
              provider: str = "fixture-delivery-rail") -> List[Dict]:
    """A delivery rail's signed lines (M1): one per (covers key, extra fields) row. P4-MEDIA rows
    carry {"hosted_url"}; P7-BUILD rows carry {"preview_url", "PASS", "checks", "dom_sha256",
    "screenshot_sha256"} (schema/delivery-rail-receipt.schema.json)."""
    return [emit_one(run_dir, phase, f"{phase.lower()}-{key}", provider=provider, operation="record",
                     covers=[key], extra=extra) for key, extra in rows]


_FIXTURE_KEY: Optional[str] = None


def ensure_fixture_operator_key() -> str:
    """Self-test helper: when the process holds no operator key, create a throwaway 0600 key OUTSIDE any
    run dir and point SF_OPERATOR_KEY_FILE at it (removed at exit), so emit()/emit_rail() lines are signed
    exactly as a real adapter's would be. A key already configured is left alone. Returns the key path."""
    global _FIXTURE_KEY
    have = os.environ.get("SF_OPERATOR_KEY_FILE", "").strip()
    if have:
        return have
    if _FIXTURE_KEY is None or not os.path.isfile(_FIXTURE_KEY):
        kd = tempfile.mkdtemp(prefix="sf_fixture_operator_")
        _FIXTURE_KEY = os.path.join(kd, "operator.key")
        with open(_FIXTURE_KEY, "w", encoding="utf-8") as fh:
            fh.write("fixture-operator-key-0123456789abcdef0123456789abcdef\n")
        os.chmod(_FIXTURE_KEY, 0o600)
        atexit.register(shutil.rmtree, kd, True)
    os.environ["SF_OPERATOR_KEY_FILE"] = _FIXTURE_KEY
    return _FIXTURE_KEY
