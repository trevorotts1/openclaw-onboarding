"""Packaged persona catalog — provenance + closure (PRES-053).

Loads the vendored Skill22 runtime catalog (persona-categories.json +
personas/_section-map.json + persona blueprints) from an explicit
resource root. Every resource is hashed; the catalog MUST NOT reference
a blueprint that is absent from the package — that is a doctor failure
before any paid work, never a silent skip.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

CATALOG_FILENAME = "persona-categories.json"
SECTION_MAP_FILENAME = "_section-map.json"
BLUEPRINT_FILENAME = "persona-blueprint.md"

REQUIRED_CATALOG_KEYS = ("personas",)


def sha256_file(path: Path) -> Optional[str]:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


class PackagedCatalog:
    """Vendored catalog + blueprints rooted at an explicit directory."""

    def __init__(self, resource_root: Path | str) -> None:
        self.root = Path(resource_root)
        self.catalog_path = self.root / CATALOG_FILENAME
        self.persona_root = self.root / "personas"
        self.section_map_path = self.persona_root / SECTION_MAP_FILENAME
        self._catalog: Optional[dict] = None
        self._section_map: Optional[dict] = None
        self._hashes: Optional[Dict[str, str]] = None

    # -- loading ---------------------------------------------------------
    def load(self) -> dict:
        if self._catalog is None:
            try:
                data = json.loads(self.catalog_path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                raise CatalogError(f"catalog unreadable at {self.catalog_path}: {exc}")
            if not isinstance(data, dict) or "personas" not in data:
                raise CatalogError(
                    f"catalog at {self.catalog_path} lacks 'personas' mapping")
            self._catalog = data
        return self._catalog

    def section_map(self) -> dict:
        if self._section_map is None:
            try:
                data = json.loads(self.section_map_path.read_text(encoding="utf-8"))
                self._section_map = data if isinstance(data, dict) else {}
            except (OSError, ValueError):
                self._section_map = {}
        return self._section_map

    def persona_ids(self) -> List[str]:
        catalog = self.load()
        personas = catalog.get("personas") or {}
        if isinstance(personas, dict):
            return sorted(personas.keys())
        if isinstance(personas, list):
            return sorted(d.get("id") or d.get("name") for d in personas
                          if isinstance(d, dict))
        return []

    def persona_meta(self, persona_id: str) -> dict:
        catalog = self.load()
        personas = catalog.get("personas") or {}
        if isinstance(personas, dict):
            meta = personas.get(persona_id)
            return dict(meta) if isinstance(meta, dict) else {}
        return {}

    # -- mandatory reference bytes ---------------------------------------
    def blueprint_path(self, persona_id: str) -> Optional[Path]:
        cand = self.persona_root / persona_id / BLUEPRINT_FILENAME
        return cand if cand.is_file() else None

    def blueprint_text(self, persona_id: str) -> str:
        """Load mandatory blueprint bytes. Empty string when absent — the
        caller (doctor/verify) treats absence as failure, never as success."""
        path = self.blueprint_path(persona_id)
        if path is None:
            return ""
        try:
            return path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""

    def governance_section_number(self, persona_id: str) -> Optional[int]:
        entry = self.section_map().get("personas", {}).get(persona_id)
        if not isinstance(entry, dict):
            return None
        num = entry.get("governance_section")
        return int(num) if isinstance(num, int) else None

    # -- provenance -------------------------------------------------------
    def resource_hashes(self) -> Dict[str, str]:
        """{relative_path: sha256} for catalog + section map + blueprints."""
        if self._hashes is None:
            out: Dict[str, str] = {}
            for path in [self.catalog_path, self.section_map_path]:
                digest = sha256_file(path)
                if digest:
                    out[str(path.relative_to(self.root))] = digest
            for pid in self.persona_ids():
                bp = self.blueprint_path(pid)
                if bp is not None:
                    digest = sha256_file(bp)
                    if digest:
                        out[str(bp.relative_to(self.root))] = digest
            self._hashes = dict(sorted(out.items()))
        return self._hashes

    def content_version(self) -> str:
        """Hash over the whole packaged resource set (cache half 2 input)."""
        raw = json.dumps(self.resource_hashes(), sort_keys=True,
                         separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    # -- closure ----------------------------------------------------------
    def missing_blueprints(self) -> List[str]:
        """Catalog ids with no packaged blueprint — must be empty."""
        return [pid for pid in self.persona_ids()
                if self.blueprint_path(pid) is None]

    def validate_closure(self) -> Tuple[bool, List[str]]:
        """(ok, problems). Fail-closed: any problem blocks paid work."""
        problems: List[str] = []
        try:
            self.load()
        except CatalogError as exc:
            return False, [str(exc)]
        missing = self.missing_blueprints()
        if missing:
            problems.append(
                f"catalog references {len(missing)} missing blueprint(s): "
                + ", ".join(sorted(missing)[:10])
                + (" ..." if len(missing) > 10 else ""))
        if not self.persona_ids():
            problems.append("catalog declares zero personas")
        return (not problems), problems


class CatalogError(RuntimeError):
    pass
