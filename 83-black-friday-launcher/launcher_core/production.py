"""The `produce` stage: from approved designs to production pages (issue 4, M8 follow-through).

Everything before this stage ends at a DESIGN: wireframes, mockups and copy. Skill 80's
``build_production_pages.py`` (U1, D1, U2), Skill 81's ``production_handoff`` (D1) and Skill 82's
``build_thank_you_page.py`` were reachable only from their own fixtures. This stage is the one place the
Launcher calls all three, after ``check`` exits 0 and before any install:

  * ``check_package`` must pass on the sealed package (nothing is produced from a package that fails);
  * a copy document that carries ``test_only: true`` never feeds a launch that is not test_only;
  * Skill 80's builder reads the APPROVED route graph and the launch record and writes one finished page
    per enabled extra slot; Skill 81's ``production_handoff`` re-reads the graph for D1 and returns the
    bindings the install needs; Skill 82's builder renders the thank-you page from a verified order view;
  * the pages land in ``<package>/production/<role>.html`` with ``production/manifest.json`` recording
    each page's sha256, builder and (for D1) install handoff; the rule in
    ``check_rules/production.py`` must then pass before the stage closes.

Nothing here installs, publishes or charges anything: ``install_handoff.py`` is the next stage.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

import sys

_ROUTES_DIR = Path(__file__).resolve().parent.parent / "routes"
if str(_ROUTES_DIR) not in sys.path:
    sys.path.insert(0, str(_ROUTES_DIR))

import substrate  # noqa: E402

from . import checks  # noqa: E402

CODE = "AF-LAUNCH-PRODUCE"
PRODUCTION_DIR = "production"
MANIFEST_REL = f"{PRODUCTION_DIR}/manifest.json"
SCHEMA = "83-production/1"
#: The page roles the three production builders cover. Landing, checkout and the order page are not
#: produced here (the landing page is Skill 71's own; checkout is the native form).
PRODUCED_ROLES = ("upsell_1", "downsell_1", "upsell_2", "thank_you")
EXTRA_ROLES = ("upsell_1", "downsell_1", "upsell_2")
BUILDERS = {
    "80": "80-signature-upsell/components/pages/build_production_pages.py",
    "81": "81-signature-downsell/adapters/s06_install_wrapper.py",
    "82": "82-signature-thank-you/scripts/build_thank_you_page.py",
}


class ProductionError(Exception):
    """A refusal the produce stage makes. Stable code, plain detail; nothing is left half-written."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def _read(path: Path, what: str) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ProductionError(f"{CODE}-INPUT", f"{what} ({path}) cannot be read as JSON: {exc}") from exc


def _load(rel: str, name: str, sibling_dir: str):
    """substrate.load, with a missing or broken sibling skill turned into a named refusal."""
    try:
        return substrate.load(rel, name, sibling_dir=sibling_dir)
    except (LookupError, ValueError, OSError, ImportError) as exc:
        raise ProductionError(f"{CODE}-DEPENDENCY", f"{rel} cannot be loaded ({type(exc).__name__}: {exc}); the "
                              "produce stage needs Skills 80, 81 and 82 installed. Nothing was produced.") from exc


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def refuse_test_copy(launch: Mapping[str, Any], docs: Mapping[str, Any]) -> None:
    """A copy document marked test_only never feeds a launch that is not test_only (issue 4)."""
    if launch.get("test_only") is True:
        return
    marked = sorted(name for name, doc in docs.items() if isinstance(doc, Mapping) and doc.get("test_only") is True)
    if marked:
        raise ProductionError(
            f"{CODE}-TEST-COPY",
            f"the copy for {', '.join(marked)} is marked test_only, but this launch is not: practice copy "
            "is never built into a client page. Nothing was produced.")


def produce(root: Path, *, run_dir: Path, copies: Mapping[str, Path],
            downsell_page: Optional[Path] = None, brand: Optional[Path] = None,
            checkout_family: str = "order_upsell_v2_funnel",
            thank_you_view: Optional[Path] = None,
            thank_you_fulfillment: Optional[Path] = None,
            u2_entry_context: Optional[str] = None) -> Dict[str, Any]:
    """Build the production pages into ``<root>/production`` and return the manifest it wrote.

    ``root`` is the assembled package; ``run_dir`` is the dispatch run folder (launch.json and, for D1,
    dispatch/downsell-request-enriched.json). Raises ProductionError, writing nothing, on any refusal."""
    root, run_dir = Path(root), Path(run_dir)
    manifest_path = root / "package-manifest.json"
    fails = checks.check_package(manifest_path, root, announce=False)
    if fails:
        raise ProductionError(
            f"{CODE}-CHECK",
            f"`check` does not pass on this package ({len(fails)} violation(s)); nothing is produced from "
            "a package that fails it. First: " + "; ".join(str(f) for f in fails[:3]))
    package_manifest = _read(manifest_path, "package manifest")
    launch = _read(run_dir / "launch.json", "launch record")
    # The APPROVED route graph is the compiler's own bytes that dispatch wrote beside the launch record
    # (Skill 80's builder re-hashes it against the record); the package carries a re-serialized copy.
    graph_file = run_dir / "dispatch" / "route-graph.json"
    if not graph_file.is_file():
        graph_file = root / str((package_manifest.get("route_graph") or {}).get("path") or "")
    graph = _read(graph_file, "route graph")
    test_only = launch.get("test_only") is True
    roles = {p.get("role") for p in package_manifest.get("pieces") or [] if not p.get("role_instance")}
    docs = {role: _read(Path(path), f"copy for {role}") for role, path in copies.items()}
    d1_doc = _read(Path(downsell_page), "downsell page") if downsell_page else None
    if d1_doc is not None:
        docs["downsell_1"] = d1_doc
    refuse_test_copy(launch, docs)
    brand_doc = _read(Path(brand), "brand tokens") if brand else {}

    if "upsell_2" in roles and not launch.get("u2_entry_context"):
        # Skill 80's builder writes the U2 acknowledgement for ONE entry path. The launch record is a
        # closed schema and carries none, and when downsell_1 is also routed the canonical U2 page has two
        # entry paths: which acknowledgement to build is a choice, so it is asked for, never guessed.
        if u2_entry_context not in ("from_upsell_1", "from_downsell_1"):
            raise ProductionError(
                f"{CODE}-U2-ENTRY",
                "upsell_2 is in this package, so say which entry path its acknowledgement is written for: "
                "--u2-entry-context from_upsell_1 or from_downsell_1. Nothing was produced.")
        launch = dict(launch, u2_entry_context=u2_entry_context)
    build = _load(BUILDERS["80"], "launcher_s80_production_pages", "80-signature-upsell/components/pages")
    try:
        built = build.build(launch, graph, checkout_family,
                            {r: d for r, d in docs.items() if r in ("upsell_1", "upsell_2")},
                            d1_doc if d1_doc is not None else {}, brand_doc)
    except build.PageBuildError as exc:
        raise ProductionError(f"{CODE}-80", f"Skill 80's production builder refused: {exc}") from exc

    pages: Dict[str, Dict[str, Any]] = {}
    html: Dict[str, str] = dict(built["pages"])
    page_rows = {row["slot"]: row for row in built["manifest"]["pages"]}
    for role in EXTRA_ROLES:
        if role in roles and role not in html:
            raise ProductionError(f"{CODE}-80", f"the package carries {role}, but Skill 80's builder built no "
                                  f"page for it (the launch record does not enable that slot)")
    for role, text in html.items():
        pages[role] = {"state": "built", "file": f"{role}.html", "sha256": _sha(text.encode("utf-8")),
                       "page_id": page_rows[role]["page_id"],
                       "builder": {"skill": 80, "module": BUILDERS["80"]},
                       **({"entry_context": launch["u2_entry_context"]} if role == "upsell_2" else {}),
                       "native_product_id": page_rows[role]["native_product_id"],
                       "native_price_id": page_rows[role]["native_price_id"],
                       "routes": page_rows[role]["routes"]}

    if "downsell_1" in html:
        pages["downsell_1"]["handoff"] = _downsell_handoff(run_dir, graph, d1_doc, html["downsell_1"])
        pages["downsell_1"]["handoff_builder"] = {"skill": 81, "module": BUILDERS["81"], "entry": "production_handoff"}

    if "thank_you" in roles:
        if thank_you_view and thank_you_fulfillment:
            ty = _load(BUILDERS["82"], "launcher_s82_thank_you_page", "82-signature-thank-you/scripts")
            try:
                ty_built = ty.build(_read(Path(thank_you_view), "order view"),
                                    _read(Path(thank_you_fulfillment), "fulfillment read"), graph, brand_doc)
            except ty.PageError as exc:
                raise ProductionError(f"{CODE}-82", f"Skill 82's page builder refused: {exc}") from exc
            html["thank_you"] = ty_built["document"]
            pages["thank_you"] = {"state": "built", "file": "thank_you.html",
                                  "sha256": _sha(ty_built["document"].encode("utf-8")),
                                  "page_id": ty_built["manifest"]["thank_you_page_id"],
                                  "builder": {"skill": 82, "module": BUILDERS["82"]}}
        else:
            pages["thank_you"] = {"state": "not_built",
                                  "reason": "Skill 82 renders a verified order view and fulfillment read; "
                                            "none was supplied, so no thank-you page was produced"}

    out = root / PRODUCTION_DIR
    out.mkdir(parents=True, exist_ok=True)
    for role, text in html.items():
        (out / f"{role}.html").write_text(text, encoding="utf-8")
    manifest = {
        "schema": SCHEMA,
        "launch_id": launch.get("launch_id"),
        "revision": launch.get("revision"),
        "test_only": test_only,
        "route_graph_sha256": _sha(graph_file.read_bytes()),
        "checkout_family": checkout_family,
        "pages": pages,
    }
    (root / MANIFEST_REL).write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    from .check_rules import production as rule  # the seam's own rule file, run directly
    bad = rule.production_violations(package_manifest, root, required=True)
    if bad:
        # The seam demands pages once the manifest exists, so a refused production leaves nothing behind
        # (a re-run after the missing input is supplied must not be blocked by this run's own leftovers).
        (root / MANIFEST_REL).unlink()
        for role in html:
            (out / f"{role}.html").unlink()
        raise ProductionError(f"{CODE}-RULE", "the production rule does not pass on what was just built: "
                              + "; ".join(bad[:3]))
    return manifest


def _downsell_handoff(run_dir: Path, graph: Mapping[str, Any], page_doc: Optional[Mapping[str, Any]],
                      d1_html: str) -> Dict[str, Any]:
    """Skill 81's production_handoff for D1: the page identity and every binding the native install
    needs, read from the APPROVED route graph. Native ids must already exist (they exist only after the
    product and price are created in the native catalog): a missing id is Skill 81's named refusal."""
    s06 = _load(BUILDERS["81"], "launcher_s81_install_wrapper", "81-signature-downsell/adapters")
    enriched = _read(run_dir / "dispatch" / "downsell-request-enriched.json", "enriched downsell request")
    page = (page_doc or {}).get("page") if isinstance((page_doc or {}).get("page"), dict) else (page_doc or {})
    try:
        purchase_ref = page["sections"][0]["cta"]["action_ref"]
        decline_ref = page["decline_action"]["action_ref"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ProductionError(f"{CODE}-81", "the D1 page names no purchase action or decline action "
                              f"reference ({type(exc).__name__}); Skill 81's handoff needs both") from exc
    role_of = {n.get("page_id"): n.get("role") for n in graph.get("nodes") or [] if isinstance(n, dict)}
    u2 = next((pid for pid, role in role_of.items() if role == "upsell_2"), None)
    bundle = {"bundle_ref": _sha(d1_html.encode("utf-8")),
              "action_refs": {"purchase_action_ref": purchase_ref, "decline_action_ref": decline_ref}}
    if enriched.get("success_route") == "upsell_2":
        bundle["canonical_u2_page_id"] = u2
    try:
        plan = s06.production_handoff(
            enriched, {"native_product_id": enriched.get("native_product_id"),
                       "native_price_id": enriched.get("native_price_id")}, bundle, graph)
    except s06.InstallPlanError as exc:
        raise ProductionError(f"{CODE}-81", f"Skill 81's production handoff refused: {exc}") from exc
    return plan["handoff"]
