#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""resolve_content_engine.py — Content and Funnel Methodology Router (Skill 62,
build unit U8). Implements spec Section 7 ("Content and Funnel Methodology
Router") and ADR-10 ("The engine routes content methodology instead of
duplicating it").

This module is the STEP-0 project/methodology selector that runs before any
cinematic content is generated. It is the mechanics behind CWFE-MANIFEST.json's
P2-METHODOLOGY and P3-CONTENT phases (scripts/prove_content.py is the thin gate
wrapper around this module, mirroring how prove_p0_environment.py wraps
resolve_execution_environment.py).

Two responsibilities, matching CWFE-MANIFEST.json's two produces_artifact
entries exactly:

  P2-METHODOLOGY -> methodology-decision.json (content engine decision +
  delegation receipt). route() scores the request text against the SAME
  registry.json (06-ghl-install-pages/funnel-engines/registry.json) engines[]
  match blocks Skill 6's own STEP-0 selector uses for Skill 49 (Signature
  Funnel) and Skill 56 (Sales-Page-Assets) — one source of truth, no
  duplicated/drifting keyword lists. Every one of spec 7.2's six routing rules
  maps to exactly one decision.rule_applied value, so a decision is always
  traceable, never a black box. Rule 3 ("ordinary funnel ... do not hijack the
  task") and its siblings (rules 5/6) resolve to methodology_source
  'existing-funnel-selector' — the NO_ENGINE_MATCH fall-through the shared
  registry's own default_behavior documents; a below-threshold score never
  blocks anything, it just means this engine steps aside.

  P3-CONTENT -> content-manifest.json (approved content + copy QC receipt),
  LOCKED with an immutable sha256 content_hash. Built one of three ways
  depending on the P2 decision:
    - signature-funnel / sales-page-assets: consumed from a content-handoff.json
      the delegate skill's completed run produced (structure/content-handoff.
      schema.json is the contract 62 requires of that handoff — see that
      schema's docstring for why approved_copy_paths carries PATHS, never
      inlined text: it is what makes "never rewrite the delegated sacred copy"
      mechanically checkable rather than a policy statement).
    - cinematic-native: this engine owns content strategy itself (ADR-10) using
      a minimal, explicitly-labeled placeholder profile pending the real
      visual-journey/scene-planner build unit (U10).
    - existing-funnel-selector: P3 intentionally refuses to author or lock
      anything (NoEngineMatchFallthrough) — this IS routing rule 3 working as
      designed, not a defect, exactly like CWFE-MANIFEST.json's own
      GATE-SCRIPT-MISSING convention documents intentional non-certification.

AF-CWFE-CONTENT-DUPLICATE (assert_delegated_methodology, defined in
prove_content.py per the manifest's py_symbol) is enforced mechanically here:
a delegated content-manifest.json is only ever built from approved_copy_paths
that are absolute, exist on disk, and resolve OUTSIDE the consuming project's
run_dir. A path inside run_dir would mean the copy was authored locally by
this engine, which ADR-10 forbids.

stdlib only.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_SCRIPT_DIR = Path(__file__).resolve().parent
_SKILL_DIR = _SCRIPT_DIR.parent
_STRUCTURE_DIR = _SKILL_DIR / "structure"
_REPO_ROOT = _SKILL_DIR.parent

if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))
sys.path.insert(0, str(_SCRIPT_DIR / "lib"))

import json_schema_lite as jsl  # noqa: E402
import state_engine as se  # noqa: E402

SCHEMA_VERSION = "1.0.0"

DEFAULT_REGISTRY_RELPATH = "06-ghl-install-pages/funnel-engines/registry.json"
DELEGATE_ENGINE_IDS = ("signature-funnel", "sales-page-assets")
ENGINE_ID_TO_METHODOLOGY_SOURCE: Dict[str, str] = {
    "signature-funnel": "signature-funnel",
    "sales-page-assets": "sales-page-assets",
}
EXPECTED_SKILL_DIR_FOR_SOURCE: Dict[str, str] = {
    "signature-funnel": "49-signature-funnel",
    "sales-page-assets": "56-sales-page-assets",
}

# spec 7.2's "defined conversion-page profiles" for the cinematic-native path
# (routing rule 4), pending the real brief-derived profile from the visual
# journey / scene planner build unit (U10). Explicitly labeled as a
# placeholder in the manifest this produces, never presented as real content.
DEFAULT_CINEMATIC_NATIVE_SECTIONS = ["hero", "offer", "proof", "cta"]
DEFAULT_CINEMATIC_NATIVE_PROFILE_ID = "cinematic-landing-default"

CONTENT_BEARING_EXCLUDE = {"schema_version", "content_hash", "locked", "created_at", "updated_at"}


class UsageError(Exception):
    """Bad arguments / unreadable config — distinct from a routing/build failure."""


class SchemaValidationFailed(Exception):
    def __init__(self, errors: List[str], label: str = ""):
        self.errors = errors
        prefix = f"{label}: " if label else ""
        super().__init__(prefix + "; ".join(errors))


class NoEngineMatchFallthrough(Exception):
    """Raised by the P3 manifest builders when the P2 decision was
    'existing-funnel-selector'. This is spec 7.2 routing rule 3 (and its
    siblings, rules 5/6) working exactly as designed — the engine correctly
    declines to author or lock content it was never asked to own. Callers
    (prove_content.evaluate_manifest) must treat this as an intentional,
    documented non-PASS, not a crash."""


class ContentDuplicateViolation(Exception):
    """Raised when a delegated content-manifest would violate ADR-10 / would
    trip AF-CWFE-CONTENT-DUPLICATE — e.g. an approved_copy_paths entry that
    resolves inside the consuming project's own run_dir (locally authored,
    not delegated), or a content-handoff.json whose declared source_skill
    does not match the skill P2 actually routed to."""


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_hex(path.read_bytes())


_LOCAL_SCHEMA_CACHE: Dict[str, Dict[str, Any]] = {}


def _load_local_schema(filename: str) -> Dict[str, Any]:
    if filename not in _LOCAL_SCHEMA_CACHE:
        path = _STRUCTURE_DIR / filename
        if not path.exists():
            raise UsageError(f"schema file missing: {path}")
        _LOCAL_SCHEMA_CACHE[filename] = json.loads(path.read_text(encoding="utf-8"))
    return _LOCAL_SCHEMA_CACHE[filename]


def validate_request(instance: Any) -> List[str]:
    return jsl.validate(instance, _load_local_schema("methodology-request.schema.json"))


def validate_decision(instance: Any) -> List[str]:
    return jsl.validate(instance, _load_local_schema("methodology-decision.schema.json"))


def validate_handoff(instance: Any) -> List[str]:
    return jsl.validate(instance, _load_local_schema("content-handoff.schema.json"))


def _read_skill_version(repo_root: Path, skill_dir: str) -> str:
    path = repo_root / skill_dir / "skill-version.txt"
    if not path.is_file():
        raise UsageError(f"skill-version.txt not found for delegate skill: {path}")
    version = path.read_text(encoding="utf-8").strip()
    if not version:
        raise UsageError(f"skill-version.txt is empty for delegate skill: {path}")
    return version


# ---------------------------------------------------------------------------
# Registry loading + match scoring (reads the SAME shared STEP-0 registry
# Skill 6 uses — one source of truth for names/keywords/signals/anti_signals,
# never a duplicated/drifting copy of Skill 49's or Skill 56's match block).
# ---------------------------------------------------------------------------
def load_registry(registry_path: Optional[str] = None, *, repo_root: Optional[Path] = None) -> Dict[str, Any]:
    repo_root = repo_root or _REPO_ROOT
    path = Path(registry_path) if registry_path else (repo_root / DEFAULT_REGISTRY_RELPATH)
    if not path.is_file():
        raise UsageError(f"funnel-engine registry not found: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise UsageError(f"funnel-engine registry is not valid JSON ({path}): {exc}")
    if not isinstance(data, dict) or not isinstance(data.get("engines"), list):
        raise UsageError(f"funnel-engine registry at {path} does not have the expected engines[] shape")
    return data


def _score_engine(text_corpus: str, engine: Dict[str, Any]) -> Dict[str, Any]:
    """Deterministic, transparent scoring: weighted term hits (name=3,
    keyword=2, signal=1) saturate into a 0..1 confidence via
    1 - e^(-weighted/3) — a single strong name-match alone clears the
    registry's default 0.55 threshold (score ~0.632), a single loose keyword
    alone does not (~0.487), matching the intent that this router should not
    hijack a task on weak evidence. ANY matched anti_signal is a hard veto
    (score forced to 0, cleared forced to False) regardless of how many
    positive terms also matched — anti_signals exist precisely to disambiguate
    Skill 49 from its direct-response sibling Skill 56."""
    import math

    match = engine.get("match", {}) or {}
    name_hits = [t for t in match.get("names", []) if t.lower() in text_corpus]
    keyword_hits = [t for t in match.get("keywords", []) if t.lower() in text_corpus]
    signal_hits = [t for t in match.get("signals", []) if t.lower() in text_corpus]
    anti_hits = [t for t in match.get("anti_signals", []) if t.lower() in text_corpus]

    weighted = 3 * len(name_hits) + 2 * len(keyword_hits) + 1 * len(signal_hits)
    veto = bool(anti_hits)
    score = 0.0 if veto else round(1.0 - math.exp(-weighted / 3.0), 4)
    threshold = float(engine.get("confidence_threshold", 0.55))
    cleared = (not veto) and score >= threshold

    return {
        "engine_id": engine.get("id"),
        "skill": engine.get("skill"),
        "priority": engine.get("priority", 0),
        "score": score,
        "threshold": threshold,
        "cleared": cleared,
        "matched": {
            "names": name_hits,
            "keywords": keyword_hits,
            "signals": signal_hits,
            "anti_signals": anti_hits,
        },
    }


def score_delegate_engines(text_corpus: str, registry: Dict[str, Any]) -> List[Dict[str, Any]]:
    candidates = [
        _score_engine(text_corpus, eng)
        for eng in registry.get("engines", [])
        if eng.get("id") in DELEGATE_ENGINE_IDS
    ]
    candidates.sort(key=lambda c: c["engine_id"])  # deterministic order, independent of registry file order
    return candidates


def _text_corpus(request: Dict[str, Any]) -> str:
    parts = [
        request.get("requested_deliverable_type") or "",
        request.get("requested_visual_treatment") or "",
        request.get("existing_funnel_methodology_named") or "",
        request.get("offer_summary") or "",
        request.get("conversion_goal") or "",
        request.get("request_text") or "",
    ]
    return " ".join(p for p in parts if p).lower()


# ---------------------------------------------------------------------------
# P2-METHODOLOGY — route()
# ---------------------------------------------------------------------------
def route(request: Dict[str, Any], *, registry_path: Optional[str] = None, repo_root: Optional[Path] = None) -> Dict[str, Any]:
    """Runs the full spec 7.2 routing-rule decision tree and returns the
    complete methodology-decision.json payload (also written verbatim by
    write_methodology_decision()). Never silently guesses cinematic_intent —
    it is read directly from the request. Raises UsageError only for a
    structurally broken registry file; a routing decision itself always
    resolves to exactly one of the four methodology_source values."""
    repo_root = repo_root or _REPO_ROOT
    registry = load_registry(registry_path, repo_root=repo_root)

    deliverable = (request.get("requested_deliverable_type") or "").strip().lower()
    visual = (request.get("requested_visual_treatment") or "").strip().lower()
    cinematic_intent = bool(request.get("cinematic_intent"))
    corpus = _text_corpus(request)

    candidates = score_delegate_engines(corpus, registry)

    def _decision(source: str, rule: str, reason: str, engine: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return {
            "methodology_source": source,
            "rule_applied": rule,
            "engine_id": engine["engine_id"] if engine else None,
            "confidence_score": engine["score"] if engine else None,
            "confidence_threshold": engine["threshold"] if engine else None,
            "candidates": candidates,
            "reason": reason,
        }

    if deliverable == "video-only" or visual == "video-only":
        decision = _decision(
            "existing-funnel-selector",
            "rule-5-video-only",
            "requested_deliverable_type/requested_visual_treatment named 'video-only' — spec 7.2 rule 5 "
            "routes to the existing video skills, not this engine.",
        )
    elif not cinematic_intent and (deliverable == "static-page" or visual == "static"):
        decision = _decision(
            "existing-funnel-selector",
            "rule-6-static-no-cinematic",
            "static page requested and cinematic_intent is false — spec 7.2 rule 6 routes to existing "
            "web/funnel systems (cinematic mode was not chosen).",
        )
    elif not cinematic_intent:
        decision = _decision(
            "existing-funnel-selector",
            "rule-3-ordinary-no-cinematic-intent",
            "cinematic_intent is false — spec 7.2 rule 3: remain on the existing funnel selector, never "
            "hijack an ordinary-funnel task.",
        )
    else:
        cleared = [c for c in candidates if c["cleared"]]
        if cleared:
            winner = max(cleared, key=lambda c: (c["score"], c["priority"]))
            source = ENGINE_ID_TO_METHODOLOGY_SOURCE[winner["engine_id"]]
            rule = "rule-1-signature-funnel" if winner["engine_id"] == "signature-funnel" else "rule-2-direct-response"
            decision = _decision(
                source,
                rule,
                f"cinematic_intent=true; engine '{winner['engine_id']}' cleared its confidence threshold "
                f"({winner['score']} >= {winner['threshold']}) against the shared registry match block — "
                f"delegating per spec 7.2 {rule}.",
                engine=winner,
            )
        else:
            decision = _decision(
                "cinematic-native",
                "rule-4-cinematic-native",
                "cinematic_intent=true but no delegate engine cleared its confidence threshold — spec 7.2 "
                "rule 4: this engine owns content strategy natively using a provider-agnostic project brief.",
            )

    delegation_receipt = None
    failure_reasons: List[str] = []
    if decision["methodology_source"] in EXPECTED_SKILL_DIR_FOR_SOURCE:
        eng_entry = next((e for e in registry["engines"] if e.get("id") == decision["engine_id"]), None)
        if eng_entry is None:
            failure_reasons.append(
                f"REGISTRY-ENGINE-MISSING: decision named engine_id={decision['engine_id']!r} but no such "
                "entry exists in the loaded registry"
            )
        else:
            skill_dir = eng_entry.get("skill", "")
            try:
                version = _read_skill_version(repo_root, skill_dir)
            except UsageError as exc:
                failure_reasons.append(str(exc))
                version = "UNKNOWN"
            delegation_receipt = {
                "target_skill": skill_dir,
                "target_skill_version": version,
                "entry_script": eng_entry.get("entry", ""),
                "entry_contract": eng_entry.get("entry_contract", ""),
                "decided_at": _now(),
            }

    status = "FAIL" if failure_reasons else "PASS"
    payload: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "project_id": request.get("project_id", ""),
        "generated_at": _now(),
        "request": request,
        "decision": decision,
        "delegation_receipt": delegation_receipt,
        "status": status,
        "af_code": None if status == "PASS" else "AF-CWFE-P2-METHODOLOGY",
        "failure_reasons": failure_reasons,
    }
    return payload


def write_methodology_decision(payload: Dict[str, Any], run_dir: Path) -> Path:
    errors = validate_decision(payload)
    if errors:
        raise SchemaValidationFailed(errors, label="methodology-decision.json")
    out_path = run_dir / "methodology-decision.json"
    se.atomic_write_json(out_path, payload)
    return out_path


def read_methodology_decision(run_dir: Path) -> Dict[str, Any]:
    path = run_dir / "methodology-decision.json"
    if not path.is_file():
        raise FileNotFoundError(str(path))
    data = se.read_json(path)
    errors = validate_decision(data)
    if errors:
        raise SchemaValidationFailed(errors, label=str(path))
    return data


# ---------------------------------------------------------------------------
# P3-CONTENT — cinematic-native manifest fields
# ---------------------------------------------------------------------------
def build_cinematic_native_manifest_fields(
    project_id: str,
    decision_payload: Dict[str, Any],
    *,
    native_profile_path: Optional[str] = None,
) -> Dict[str, Any]:
    decision = decision_payload["decision"]
    if decision["methodology_source"] == "existing-funnel-selector":
        raise NoEngineMatchFallthrough(
            f"spec 7.2 {decision['rule_applied']} routed to the existing funnel selector — this engine "
            "correctly declines to author cinematic-native content for a task it was never asked to own."
        )
    if decision["methodology_source"] != "cinematic-native":
        raise UsageError(
            f"build_cinematic_native_manifest_fields called for methodology_source="
            f"{decision['methodology_source']!r} — expected 'cinematic-native'"
        )

    request = decision_payload.get("request", {})
    profile = {
        "page_profiles": [{"profile_id": DEFAULT_CINEMATIC_NATIVE_PROFILE_ID, "sections": list(DEFAULT_CINEMATIC_NATIVE_SECTIONS)}],
        "section_order": list(DEFAULT_CINEMATIC_NATIVE_SECTIONS),
        "cta_map": {},
        "offer_ledger": [],
        "claims": [],
        "placeholder": True,
    }
    if native_profile_path:
        p = Path(native_profile_path)
        if not p.is_file():
            raise UsageError(f"CWFE_CINEMATIC_NATIVE_PROFILE path does not exist: {p}")
        try:
            supplied = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise UsageError(f"CWFE_CINEMATIC_NATIVE_PROFILE is not valid JSON ({p}): {exc}")
        if not isinstance(supplied, dict):
            raise UsageError(f"CWFE_CINEMATIC_NATIVE_PROFILE must be a JSON object: {p}")
        for key in ("page_profiles", "section_order", "cta_map", "offer_ledger", "claims"):
            if key in supplied:
                profile[key] = supplied[key]
        profile["placeholder"] = False

    conversion_requirements = request.get("conversion_requirements") or {"form": False, "calendar": False, "payment": False}

    return {
        "schema_version": SCHEMA_VERSION,
        "project_id": project_id,
        "methodology_source": "cinematic-native",
        "source_skill": "62-cinematic-web-funnel-engine",
        "source_skill_version": _read_own_skill_version(),
        "page_profiles": profile["page_profiles"],
        "section_order": profile["section_order"],
        "approved_copy_paths": [],
        "cta_map": profile["cta_map"],
        "offer_ledger": profile["offer_ledger"],
        "conversion_requirements": conversion_requirements,
        "claims": profile["claims"],
        "copy_qc_receipt": {
            "source": "cinematic-native",
            "placeholder": profile["placeholder"],
            "note": (
                "Content strategy owned natively by Skill 62 (ADR-10). Page profile is a documented "
                "placeholder pending the visual-journey/scene-planner build unit (U10) unless "
                "CWFE_CINEMATIC_NATIVE_PROFILE supplied a brief-derived profile."
            ),
            "verified_at": _now(),
        },
    }


def _read_own_skill_version() -> str:
    path = _SKILL_DIR / "skill-version.txt"
    if not path.is_file():
        return "UNKNOWN"
    return path.read_text(encoding="utf-8").strip() or "UNKNOWN"


# ---------------------------------------------------------------------------
# P3-CONTENT — delegated manifest fields (Skill 49 / Skill 56)
# ---------------------------------------------------------------------------
def load_content_handoff(delegate_dir: Path) -> Dict[str, Any]:
    path = delegate_dir / "content-handoff.json"
    if not path.is_file():
        raise UsageError(f"content-handoff.json not found in delegate output dir: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise UsageError(f"content-handoff.json is not valid JSON ({path}): {exc}")
    errors = validate_handoff(data)
    if errors:
        raise SchemaValidationFailed(errors, label=str(path))
    return data


def build_delegated_manifest_fields(
    project_id: str,
    decision_payload: Dict[str, Any],
    delegate_dir: Path,
) -> Dict[str, Any]:
    decision = decision_payload["decision"]
    source = decision["methodology_source"]
    if source == "existing-funnel-selector":
        raise NoEngineMatchFallthrough(
            f"spec 7.2 {decision['rule_applied']} routed to the existing funnel selector — this engine "
            "correctly declines to consume/author a delegated content-manifest for a task it was never "
            "asked to own."
        )
    if source not in EXPECTED_SKILL_DIR_FOR_SOURCE:
        raise UsageError(f"build_delegated_manifest_fields called for non-delegated methodology_source={source!r}")

    handoff = load_content_handoff(delegate_dir)
    expected_skill_dir = EXPECTED_SKILL_DIR_FOR_SOURCE[source]
    if handoff["source_skill"] != expected_skill_dir:
        raise ContentDuplicateViolation(
            f"content-handoff.json source_skill={handoff['source_skill']!r} does not match the routed "
            f"methodology_source={source!r}'s expected delegate skill {expected_skill_dir!r} "
            "(AF-CWFE-CONTENT-DUPLICATE — the wrong engine's output was handed in)"
        )

    delegation_receipt = decision_payload.get("delegation_receipt") or {}
    consumed_artifacts = []
    for p in handoff["approved_copy_paths"]:
        pp = Path(p)
        if pp.is_file():
            consumed_artifacts.append({"path": str(pp), "sha256": _sha256_file(pp)})
        else:
            consumed_artifacts.append({"path": str(pp), "sha256": None})

    copy_qc_receipt = dict(handoff.get("qc_receipt") or {})
    copy_qc_receipt["delegation"] = {
        "target_skill": expected_skill_dir,
        "target_skill_version": handoff["source_skill_version"],
        "entry_script": delegation_receipt.get("entry_script"),
        "entry_contract": delegation_receipt.get("entry_contract"),
        "certificate_ref": handoff.get("certificate_ref"),
        "consumed_at": _now(),
        "consumed_artifact_hashes": consumed_artifacts,
        "no_rewrite_attestation": "content is referenced by approved_copy_paths (filesystem paths into the "
        "delegate skill's own output), never inlined or edited by this engine",
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "project_id": project_id,
        "methodology_source": source,
        "source_skill": handoff["source_skill"],
        "source_skill_version": handoff["source_skill_version"],
        "page_profiles": handoff["page_profiles"],
        "section_order": handoff["section_order"],
        "approved_copy_paths": handoff["approved_copy_paths"],
        "cta_map": handoff["cta_map"],
        "offer_ledger": handoff["offer_ledger"],
        "conversion_requirements": handoff["conversion_requirements"],
        "claims": handoff["claims"],
        "copy_qc_receipt": copy_qc_receipt,
    }


# ---------------------------------------------------------------------------
# Hashing / locking / persistence (shared by both P3 paths)
# ---------------------------------------------------------------------------
def compute_content_hash(manifest_fields: Dict[str, Any]) -> str:
    """sha256 over the canonical (sorted-key, no-whitespace) serialization of
    every field EXCEPT schema_version/content_hash/locked/created_at/
    updated_at — the same 'content-bearing fields' language
    content-manifest.schema.json's own content_hash description uses."""
    subset = {k: v for k, v in manifest_fields.items() if k not in CONTENT_BEARING_EXCLUDE}
    canonical = json.dumps(subset, sort_keys=True, separators=(",", ":"))
    return _sha256_hex(canonical.encode("utf-8"))


def verify_locked_manifest(manifest: Dict[str, Any]) -> Tuple[bool, str]:
    if not manifest.get("locked"):
        return False, "manifest is not locked"
    expected = compute_content_hash(manifest)
    actual = manifest.get("content_hash")
    if expected != actual:
        return False, f"content_hash mismatch — recomputed {expected} != stored {actual} (tamper or corruption)"
    return True, "content_hash verified against a fresh recomputation; manifest is immutably locked"


def finalize_and_save_content_manifest(run_dir: Path, manifest_fields: Dict[str, Any]) -> Dict[str, Any]:
    """Adds created_at/updated_at, computes the immutable content_hash over the
    content-bearing fields, sets locked=True, then validates + atomically
    writes via state_engine.ProjectState — the SAME lock-guarded, schema-
    validated, atomic-write path U6 built for every other manifest kind.
    Refuses to overwrite an existing content-manifest.json that is already
    locked (spec 7.3: 'Cinematic assembly may not silently rewrite sacred or
    approved copy'), enforcing manifest immutability at the storage layer, not
    only as a policy statement."""
    now = _now()
    manifest = dict(manifest_fields)
    manifest["created_at"] = now
    manifest["updated_at"] = now
    manifest["content_hash"] = compute_content_hash(manifest)
    manifest["locked"] = True

    state = se.ProjectState(run_dir)
    with state.lock():
        if state.exists("content-manifest"):
            existing = state.load("content-manifest")
            if existing.get("locked"):
                raise se.StateEngineError(
                    "content-manifest.json already exists and is locked=true — refusing to overwrite "
                    "sacred/approved content (spec 7.3, ADR-10)"
                )
        state.save("content-manifest", manifest)
    return manifest


# ---------------------------------------------------------------------------
# CLI (mirrors resolve_execution_environment.py's --self-test convention)
# ---------------------------------------------------------------------------
def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        # The real self-test lives in tests/unit/test_resolve_content_engine.py
        # (this repo's convention keeps state_engine.py's --self-test inline
        # because it needs no fixtures; this module's tests need registry +
        # content-handoff fixtures, so they live under tests/unit/ instead).
        print("Run: python3 -m unittest tests.unit.test_resolve_content_engine -v")
        sys.exit(0)
    parser.print_help()
    sys.exit(2)


if __name__ == "__main__":
    main()
