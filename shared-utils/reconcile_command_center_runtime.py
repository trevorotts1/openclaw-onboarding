#!/usr/bin/env python3
"""Fail-closed update-time reconciliation for Command Center runtime config.

The Command Center intentionally ships empty/template runtime configuration.
This helper repairs only those unpopulated states from this box's durable Skill
23 artifacts:

* departments: the selected ZHC ``<company>/departments.json`` artifact;
* identity: ``.workforce-build-state.json`` and the matching ZHC
  ``company-config.json``.

It never selects a different company's most-recent file, never invents a
company name, and never overwrites a non-empty departments list, a non-template
company name, or a non-empty logo URL. Writes are atomic and re-running is a
byte-for-byte no-op once the runtime config is healthy.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import quote

from detect_platform import get_openclaw_paths


TEMPLATE_COMPANY_NAME = "Your Company"
_HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
_SAFE_SLUG = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class ReconcileError(RuntimeError):
    """An unsafe or incomplete reconciliation state."""


def _load_json(path: Path, *, missing: Any = None, empty: Any = None) -> Any:
    if not path.exists():
        return missing
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ReconcileError(f"cannot read required runtime artifact: {exc}") from exc
    if not raw.strip():
        return empty
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ReconcileError(f"invalid JSON in required runtime artifact: {path.name}: {exc}") from exc


def _valid_departments(payload: Any) -> bool:
    if not isinstance(payload, list) or not payload:
        return False
    seen: Set[str] = set()
    for entry in payload:
        if not isinstance(entry, dict):
            return False
        slug = entry.get("slug") or entry.get("id")
        name = entry.get("name")
        if not isinstance(slug, str) or not slug.strip() or not isinstance(name, str) or not name.strip():
            return False
        normalized = (slug[5:] if slug.startswith("dept-") else slug).strip().lower()
        if normalized in seen:
            return False
        seen.add(normalized)
    return True


def _company_roots(master_files: Optional[Path]) -> List[Path]:
    if master_files is not None:
        roots: List[Path] = [master_files / "zero-human-company"]
    else:
        # detect_platform.py is the repository's sole authority for canonical
        # and read-only legacy company resolution. In particular, do not add a
        # second local-candidate loop here: that can select another client on a
        # box whose historical layout differs from the updater's assumptions.
        try:
            paths = get_openclaw_paths()
        except SystemExit as exc:
            raise ReconcileError(
                "cannot resolve the canonical company root for this platform"
            ) from exc
        roots = [Path(paths["company_root"])]
        active_company = paths.get("company_dir")
        if active_company is not None:
            roots.append(Path(active_company).parent)
    deduped: List[Path] = []
    seen: Set[str] = set()
    for root in roots:
        key = os.path.realpath(root)
        if key not in seen:
            seen.add(key)
            deduped.append(root)
    return deduped


def _resolve_company_dir(
    workspace: Path, master_files: Optional[Path], state: Dict[str, Any]
) -> Optional[Path]:
    slug = str(state.get("companySlug") or state.get("clientSlug") or "").strip()
    if slug and not _SAFE_SLUG.fullmatch(slug):
        raise ReconcileError("build-state company slug is unsafe; refusing path resolution")

    roots = _company_roots(master_files)
    if slug:
        matches = [root / slug for root in roots if (root / slug / "departments.json").is_file()]
        if len(matches) > 1:
            real_matches = {os.path.realpath(match) for match in matches}
            if len(real_matches) > 1:
                raise ReconcileError(
                    "multiple department artifacts match the build-state slug; refusing ambiguous identity"
                )
        return matches[0] if matches else None

    candidates: List[Path] = []
    for root in roots:
        if not root.is_dir():
            continue
        for child in root.iterdir():
            if child.is_dir() and not child.name.startswith(".") and (child / "departments.json").is_file():
                candidates.append(child)
    unique = {os.path.realpath(candidate): candidate for candidate in candidates}
    if len(unique) == 1:
        return next(iter(unique.values()))
    if len(unique) > 1:
        raise ReconcileError(
            "build-state has no company slug and multiple company artifacts exist; refusing cross-client selection"
        )
    return None


def _real_name(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    name = value.strip()
    if not name or name == TEMPLATE_COMPANY_NAME:
        return ""
    return name


def _first_string(mapping: Dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _nested_string(mapping: Dict[str, Any], containers: Tuple[str, ...], *keys: str) -> str:
    direct = _first_string(mapping, *keys)
    if direct:
        return direct
    for container in containers:
        nested = mapping.get(container)
        if isinstance(nested, dict):
            value = _first_string(nested, *keys)
            if value:
                return value
    return ""


def _resolve_identity(
    state: Dict[str, Any], zhc_config: Dict[str, Any]
) -> Dict[str, str]:
    state_name = _real_name(state.get("companyName") or state.get("company_name"))
    zhc_name = _real_name(
        zhc_config.get("companyName") or zhc_config.get("company_name") or zhc_config.get("name")
    )
    if state_name and zhc_name and state_name != zhc_name:
        raise ReconcileError(
            "provisioning identity conflicts with the matching ZHC company identity; refusing overwrite"
        )
    name = state_name or zhc_name

    slug = _first_string(state, "companySlug", "clientSlug") or _first_string(
        zhc_config, "companySlug", "clientSlug", "slug"
    )
    industry = _first_string(state, "industry") or _first_string(zhc_config, "industry")
    logo_url = _nested_string(
        state,
        ("brand", "branding", "identity"),
        "logoUrl",
        "logoURL",
        "companyLogoUrl",
        "companyLogoURL",
    ) or _nested_string(
        zhc_config,
        ("brand", "brandColors", "branding", "identity"),
        "logoUrl",
        "logoURL",
        "companyLogoUrl",
        "companyLogoURL",
    )
    primary = _nested_string(
        state, ("brand", "brandColors", "branding"), "brandColor", "primary", "primaryColor"
    ) or _nested_string(
        zhc_config, ("brand", "brandColors", "branding"), "brandColor", "primary", "primaryColor"
    )
    if not _HEX_COLOR.fullmatch(primary):
        primary = "#1e293b"
    return {
        "name": name,
        "slug": slug,
        "industry": industry,
        "logo_url": logo_url,
        "primary": primary,
    }


def _identity_logo_data_url(name: str, primary: str) -> str:
    # This is a deterministic text mark of the verified provisioning identity,
    # not a guessed logo or company name. An explicit recorded logo URL wins.
    safe_name = html.escape(name, quote=True)
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 960 120">'
        f'<rect width="960" height="120" rx="16" fill="{primary}"/>'
        f'<text x="480" y="76" text-anchor="middle" font-family="Arial,sans-serif" '
        f'font-size="44" font-weight="700" fill="#ffffff">{safe_name}</text>'
        "</svg>"
    )
    return "data:image/svg+xml," + quote(svg, safe="")


def _atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = path.stat().st_mode & 0o777 if path.exists() else 0o644
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def _restore(path: Path, prior: Optional[bytes]) -> None:
    if prior is None:
        path.unlink(missing_ok=True)
        return
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.rollback.", dir=str(path.parent))
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(prior)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def reconcile(
    workspace: Path, master_files: Optional[Path], command_center: Path
) -> Dict[str, str]:
    company_path = command_center / "config/company-config.json"
    departments_path = command_center / "config/departments.json"
    logo_path = command_center / "public/logo-config.json"

    departments = _load_json(departments_path, missing=[], empty=[])
    if departments and not _valid_departments(departments):
        raise ReconcileError(
            "existing departments.json is non-empty but invalid; refusing to clobber operator/client data"
        )
    needs_departments = not departments

    company = _load_json(company_path, missing=None, empty=None)
    if company is None:
        example = _load_json(
            command_center / "config/company-config.example.json", missing={}, empty={}
        )
        company = example
    if not isinstance(company, dict):
        raise ReconcileError("company-config.json is not a JSON object; refusing overwrite")
    company_name = company.get("companyName")
    if not isinstance(company_name, str) or not company_name:
        raise ReconcileError(
            "company-config.json companyName is blank/missing, not the exact shipped placeholder; refusing overwrite"
        )
    needs_name = company_name == TEMPLATE_COMPANY_NAME

    logo = _load_json(logo_path, missing={}, empty={})
    if not isinstance(logo, dict):
        raise ReconcileError("logo-config.json is not a JSON object; refusing overwrite")
    logo_value = logo.get("logoUrl")
    needs_logo = not isinstance(logo_value, str) or not logo_value.strip()

    # A healthy box is a strict no-op. Do not require historical provisioning
    # artifacts merely to re-approve runtime files that are already populated.
    if not needs_departments and not needs_name and not needs_logo:
        return {
            "departments": "preserved",
            "company_name": "preserved",
            "logo": "preserved",
            "writes": "0",
        }

    state_payload = _load_json(
        workspace / ".workforce-build-state.json", missing={}, empty={}
    )
    if not isinstance(state_payload, dict):
        raise ReconcileError(".workforce-build-state.json is not a JSON object")
    company_dir = _resolve_company_dir(workspace, master_files, state_payload)

    source_departments: Optional[List[Dict[str, Any]]] = None
    zhc_config: Dict[str, Any] = {}
    if company_dir is not None:
        source_payload = _load_json(company_dir / "departments.json", missing=None, empty=None)
        if source_payload is not None:
            if not _valid_departments(source_payload):
                raise ReconcileError("canonical ZHC departments artifact is empty or invalid")
            source_departments = source_payload
        zhc_payload = _load_json(company_dir / "company-config.json", missing={}, empty={})
        if not isinstance(zhc_payload, dict):
            raise ReconcileError("matching ZHC company-config.json is not a JSON object")
        zhc_config = zhc_payload

    if needs_departments and source_departments is None:
        raise ReconcileError(
            "DEPARTMENTS UNRESOLVED: dashboard departments are empty and no exact client ZHC artifact exists"
        )

    identity = _resolve_identity(state_payload, zhc_config)
    if (needs_name or needs_logo) and not identity["name"]:
        raise ReconcileError(
            "IDENTITY UNRESOLVED: placeholder/empty branding remains and no legitimate provisioning identity exists"
        )

    next_company = dict(company)
    next_logo = dict(logo)
    if needs_name:
        next_company["companyName"] = identity["name"]
        if not str(next_company.get("industry") or "").strip() and identity["industry"]:
            next_company["industry"] = identity["industry"]
        if not str(next_company.get("companySlug") or "").strip() and identity["slug"]:
            next_company["companySlug"] = identity["slug"]
        if not str(next_company.get("brandPrimaryColor") or "").strip():
            next_company["brandPrimaryColor"] = identity["primary"]

    if needs_logo:
        resolved_logo = identity["logo_url"] or _identity_logo_data_url(
            identity["name"], identity["primary"]
        )
        next_logo["logoUrl"] = resolved_logo
        if not str(next_company.get("logoUrl") or "").strip():
            next_company["logoUrl"] = resolved_logo

    writes: List[Tuple[Path, Any]] = []
    if needs_departments:
        writes.append((departments_path, source_departments))
    if next_company != company or not company_path.exists():
        writes.append((company_path, next_company))
    if next_logo != logo or not logo_path.exists():
        writes.append((logo_path, next_logo))

    snapshots = {path: path.read_bytes() if path.exists() else None for path, _ in writes}
    try:
        for path, payload in writes:
            _atomic_write_json(path, payload)
    except Exception:
        for path, prior in snapshots.items():
            _restore(path, prior)
        raise

    # Independent post-write proof. An exit 0 is never accepted without all
    # three runtime artifacts being concretely populated.
    final_departments = _load_json(departments_path, missing=[], empty=[])
    final_company = _load_json(company_path, missing={}, empty={})
    final_logo = _load_json(logo_path, missing={}, empty={})
    if not _valid_departments(final_departments):
        raise ReconcileError("post-write assertion failed: departments.json remains empty/invalid")
    if not isinstance(final_company, dict) or final_company.get("companyName") == TEMPLATE_COMPANY_NAME:
        raise ReconcileError("post-write assertion failed: exact company placeholder remains")
    if not isinstance(final_logo, dict) or not str(final_logo.get("logoUrl") or "").strip():
        raise ReconcileError("post-write assertion failed: logo-config.json remains empty")

    return {
        "departments": "populated" if needs_departments else "preserved",
        "company_name": "applied" if needs_name else "preserved",
        "logo": "applied" if needs_logo else "preserved",
        "writes": str(len(writes)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--master-files", type=Path)
    parser.add_argument("--command-center-dir", type=Path, required=True)
    args = parser.parse_args()

    try:
        result = reconcile(
            args.workspace.expanduser(),
            args.master_files.expanduser() if args.master_files else None,
            args.command_center_dir.expanduser(),
        )
    except (OSError, ReconcileError) as exc:
        print(f"[cc-runtime] FATAL: {exc}", file=sys.stderr)
        return 1

    print(
        "[cc-runtime] PASS: "
        f"departments={result['departments']} "
        f"company_name={result['company_name']} logo={result['logo']} writes={result['writes']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
