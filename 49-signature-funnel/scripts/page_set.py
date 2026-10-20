#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""page_set.py - which pages a funnel has, what each must deliver, and the shared image inputs.

Three jobs, all driven by structure/page_types.json (the one list of page types):

  1. build_page_set(launch, ...)   one ordered entry per page for ANY funnel shape (single offer,
                                   multiple options, folded levels, free entry), with the pages the
                                   intake picked. Every entry says role + page_kind + role_instance,
                                   the skill and wrapper that builds it, the client-facing label,
                                   and its deliverables (desktop + mobile wireframes and mockups,
                                   review PDFs, overview boards).
  2. legacy_page_set(funnel_size)  the same entries for the legacy 3, 5 and 7 step funnel.
  3. check_deliverables(...)       prove a page's run folder really holds every deliverable; a stub
                                   run is reported as "images only, render pending", never complete.

Plus the shared image inputs file (contract C3, image_inputs.json): load_image_inputs() validates it
and fill_args() lets every wrapper take its brand file, owner, cap, design style and provider from
that one file instead of five flags. design_artifacts() lists every output file of a run folder so a
page result carries all of them.

Plain-English choices (D1, to confirm with the client, never silently final):
  * the client picks the landing page set at intake: landing (opt-in), sales, or both. When they did
    not, the recommended set is used and "landing_pages" is returned in `to_confirm`.
  * a second downsell is a design page the client opts into (extra_pages=["downsell_2"]).

Deterministic, stdlib only, no network, no model. Never reads a secret.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import compile_launch_route as clr  # noqa: E402

PAGE_TYPES_FILE = HERE.parent / "structure" / "page_types.json"
FUNNEL_STRUCTURE_FILE = HERE.parent / "structure" / "funnel_structure.json"
LANDING_PAGE_KEYS = ("landing", "sales")
STYLES = ("A", "B", "C")
PROVIDERS = ("stub", "kie")


class PageSetError(ValueError):
    pass


_CACHE: Dict[str, Any] = {}


def page_types() -> Dict[str, Any]:
    """structure/page_types.json (read once); a missing or malformed file is a named refusal."""
    if "doc" not in _CACHE:
        try:
            doc = json.loads(PAGE_TYPES_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise PageSetError(f"cannot read {PAGE_TYPES_FILE}: {exc}") from exc
        if doc.get("contract") != "signature-funnel-page-types/v1" or not doc.get("pages"):
            raise PageSetError(f"{PAGE_TYPES_FILE.name} is not signature-funnel-page-types/v1")
        _CACHE["doc"] = doc
    return _CACHE["doc"]


def slug_of(page_key: str) -> str:
    """The file-name slug 71's deliverable_labels gives the page ('sales_page' -> 'sales-page')."""
    role = page_types()["pages"][page_key]["label_role"]
    return re.sub(r"[^a-z0-9]+", "-", role.lower()).strip("-")


def deliverables_for(page_key: str) -> List[Dict[str, Any]]:
    """The page's deliverables with {slug} resolved (a copy; callers may not mutate the file)."""
    slug = slug_of(page_key)
    return [dict(d, glob=d["glob"].format(slug=slug)) for d in page_types()["deliverables"]]


def image_estimate(page_key: str, long_form: bool = False) -> int:
    """Images one page makes: 4 per section (desktop + mobile wireframe, desktop + mobile mockup)."""
    p = page_types()["pages"][page_key]
    n = p.get("long_form_sections", p["sections"]) if long_form else p["sections"]
    return 4 * int(n)


def _entry(page_key: str, shape: str, source: str) -> Dict[str, Any]:
    p = page_types()["pages"][page_key]
    return {
        "page_key": page_key, "order": p["order"], "role": p["role"],
        "page_kind": p["page_kind"], "role_instance": p["role_instance"],
        "request_role": p["request_role"], "skill": p["skill"], "wrapper": p["wrapper"],
        "label": p["label"], "design_only": p["design_only"], "shape": shape, "source": source,
        "image_estimate": image_estimate(page_key),
        "deliverables": [d["id"] for d in page_types()["deliverables"]],
    }


def recommended_landing_pages(launch: Dict[str, Any]) -> List[str]:
    """What we recommend when the client did not choose (shown to them as 'to confirm')."""
    mode = launch.get("journey_mode")
    ex = launch.get("extras") or {}
    full = all(ex.get(k) is True for k in ("upsell_1", "downsell_1", "upsell_2"))
    if mode == "free_entry":
        return ["landing"]
    if mode in ("multiple_options", "folded_levels") or full:
        return ["landing", "sales"]
    return ["sales"]


def build_page_set(launch: Dict[str, Any], *, landing_pages: Optional[Iterable[str]] = None,
                   extra_pages: Iterable[str] = ()) -> Dict[str, Any]:
    """The ordered pages of one launch: {"pages": [...], "to_confirm": [...], "shape": mode}.

    Every route node is a page; the landing role expands to the client's chosen landing pages; the
    opted-in extras (today: downsell_2) are added after the route pages they follow."""
    roles = clr.expected_roles(launch)  # raises RouteError on a mode/extras the route law refuses
    mode = launch["journey_mode"]
    to_confirm: List[str] = []
    if landing_pages is None:
        chosen = recommended_landing_pages(launch)
        to_confirm.append("landing_pages")
    else:
        chosen = list(landing_pages)
        bad = [k for k in chosen if k not in LANDING_PAGE_KEYS]
        if bad or not chosen or len(set(chosen)) != len(chosen):
            raise PageSetError(f"landing_pages must be a non-empty subset of {LANDING_PAGE_KEYS}, got {chosen!r}")
    keys: List[str] = []
    for role in roles:
        if role == "landing":
            keys += [k for k in LANDING_PAGE_KEYS if k in chosen]
        else:
            keys.append(role)
    extras = list(extra_pages)
    for extra in extras:
        if extra != "downsell_2":
            raise PageSetError(f"extra page {extra!r} is not one the funnel can add (only downsell_2)")
        if "downsell_1" not in roles:
            raise PageSetError("downsell_2 follows downsell_1, and this launch has no downsell_1 page")
        keys.append(extra)
    pages = sorted((_entry(k, mode, "intake" if k in extras or k in LANDING_PAGE_KEYS else "route")
                    for k in keys), key=lambda e: e["order"])
    return {"shape": mode, "pages": pages, "to_confirm": to_confirm}


def page_key_for_slug(slug: str) -> str:
    """The page_key of a legacy funnel_matrix slug ('main' -> 'sales', 'upsell-2' -> 'upsell_2')."""
    for key, p in page_types()["pages"].items():
        if p["matrix_slug"] == slug:
            return key
    raise PageSetError(f"funnel matrix slug {slug!r} is not a page type in {PAGE_TYPES_FILE.name}")


def legacy_page_set(funnel_size: int) -> Dict[str, Any]:
    """The legacy 3, 5 or 7 step funnel as the same page entries (matrix slug -> page_key)."""
    structure = json.loads(FUNNEL_STRUCTURE_FILE.read_text(encoding="utf-8"))
    slugs = structure["funnel_matrix"].get(str(funnel_size))
    if not isinstance(slugs, list):
        raise PageSetError(f"funnel_size {funnel_size!r} is not 3, 5 or 7")
    pages = [_entry(page_key_for_slug(s), f"legacy_{funnel_size}", "legacy") for s in slugs]
    return {"shape": f"legacy_{funnel_size}", "pages": sorted(pages, key=lambda e: e["order"]),
            "to_confirm": []}


def plain_summary(page_set: Dict[str, Any]) -> str:
    """The page list in plain English for the client, with anything we chose for them marked
    'to confirm' and how to change it. Short lines, no jargon."""
    pages = page_set["pages"]
    lines = [f"Your funnel has {len(pages)} pages. Every page gets desktop and mobile wireframes "
             "and desktop and mobile mockups:"]
    for i, p in enumerate(pages, 1):
        note = " (design only; the real order form is installed separately)" if p["page_key"] == "checkout" \
            else " (design only)" if p["design_only"] else ""
        lines.append(f"  {i}. {p['label']}{note}")
    if "landing_pages" in page_set["to_confirm"]:
        chosen = [p["label"] for p in pages if p["page_key"] in LANDING_PAGE_KEYS]
        lines += ["", "To confirm with you:",
                  f"  - Landing pages: we suggested {' and '.join(chosen)}. "
                  "Tell us if you want only the sales page or only the landing page."]
    return "\n".join(lines)


def lane_plan(page_set: Dict[str, Any]) -> Dict[str, Any]:
    """The request lanes, in page order. A lane is one dispatch request (or one extra page); every
    lane is independent and runs side by side (the landing lane too: the look the pages share is the
    image inputs file, so no page waits for another)."""
    lanes: List[Dict[str, Any]] = []
    for page in page_set["pages"]:
        extra = page["role_instance"] is not None
        lane_key = page["role_instance"] if extra else page["request_role"]
        lane = next((x for x in lanes if x["lane"] == lane_key), None)
        if lane:
            lane["pages"].append(page["page_key"])
            lane["image_estimate"] += page["image_estimate"]
        else:
            lanes.append({"lane": lane_key, "request_role": page["request_role"], "extra": extra,
                          "pages": [page["page_key"]], "image_estimate": page["image_estimate"]})
    return {"parallel": lanes}


# ---------------------------------------------------------------------------------------------
# Deliverable completeness
# ---------------------------------------------------------------------------------------------
def check_deliverables(page_key: str, run_dir: Path, *, rendered: bool) -> Dict[str, Any]:
    """Which deliverables of this page exist in run_dir.

    `rendered` says the paid provider composed PDFs and boards; on a stub run those are reported in
    `render_pending` and the page is NOT complete (images_complete only)."""
    run_dir = Path(run_dir)
    present, missing, render_pending, files = [], [], [], []
    for d in deliverables_for(page_key):
        found = sorted(p for p in run_dir.glob(d["glob"]) if p.is_file())
        if found:
            present.append(d["id"])
            files += found
        elif d["needs"] == "render" and not rendered:
            render_pending.append(d["id"])
        else:
            missing.append(d["id"])
    return {"page_key": page_key, "present": present, "missing": missing,
            "render_pending": render_pending, "files": [str(f) for f in files],
            "images_complete": not any(d["id"] in missing for d in deliverables_for(page_key)
                                       if d["needs"] == "images"),
            "complete": not missing and not render_pending}


def design_artifacts(page_key: str, run_dir: Path, relative: bool = False) -> List[Dict[str, str]]:
    """Every deliverable file of the page as page-result artifacts ({path, sha256}), sorted by path.
    Includes the stage records so the result also shows which provider drew the images.
    relative=True names each path from run_dir (the form Skill 71's own page results use)."""
    run_dir = Path(run_dir)
    paths = set(check_deliverables(page_key, run_dir, rendered=True)["files"])
    paths |= {str(p) for p in run_dir.glob("*/stage-executor-record.json")}
    paths |= {str(p) for p in run_dir.glob("visual-bible.json")}
    shown = (lambda p: str(Path(p).relative_to(run_dir))) if relative else (lambda p: p)
    return sorted(({"path": shown(p), "sha256": hashlib.sha256(Path(p).read_bytes()).hexdigest()}
                   for p in paths), key=lambda a: a["path"])


# ---------------------------------------------------------------------------------------------
# C3: the shared image inputs file
# ---------------------------------------------------------------------------------------------
IMAGE_INPUT_KEYS = ("design_style", "brand_file", "brand_owner", "image_cap", "image_provider",
                    "paid_render_approval_ref", "design_prose_ref", "visual_bible_ref", "test_only")


def load_image_inputs(path) -> Dict[str, Any]:
    """Read and check image_inputs.json (C3). Returns the validated dict plus `allow_paid`.

    Refusals are plain: the provider must be stub or kie (an agnes launch is refused by name until
    Skill 71's stage executor has an Agnes path), and the paid provider needs the client's recorded
    approval reference. Nothing is defaulted that spends money."""
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise PageSetError(f"image inputs {path}: cannot read: {exc}") from exc
    if not isinstance(doc, dict):
        raise PageSetError("image inputs: the document is not a JSON object")
    unknown = sorted(set(doc) - set(IMAGE_INPUT_KEYS))
    if unknown:
        raise PageSetError(f"image inputs: unknown key(s) {unknown}; allowed {list(IMAGE_INPUT_KEYS)}")
    style = doc.get("design_style")
    if style is not None and style not in STYLES:
        raise PageSetError(f"image inputs: design_style must be A, B or C (or null to ask), got {style!r}")
    cap = doc.get("image_cap")
    if isinstance(cap, bool) or not isinstance(cap, int) or cap < 0:
        raise PageSetError(f"image inputs: image_cap must be an integer >= 0, got {cap!r}")
    for key in ("brand_file", "brand_owner"):
        if not isinstance(doc.get(key), str) or not doc[key].strip():
            raise PageSetError(f"image inputs: {key} is missing; it is the client's own value and is never invented")
    provider = doc.get("image_provider", "stub")
    if provider == "agnes":
        raise PageSetError("image inputs: image_provider 'agnes' is refused: Skill 71's stage executor "
                           "draws with stub or kie only, so an Agnes launch cannot be built yet")
    if provider not in PROVIDERS:
        raise PageSetError(f"image inputs: image_provider must be one of {PROVIDERS}, got {provider!r}")
    ref = doc.get("paid_render_approval_ref")
    if provider == "kie" and not (isinstance(ref, str) and ref.strip()) and not doc.get("test_only"):
        raise PageSetError("image inputs: the paid provider needs paid_render_approval_ref (the client's "
                           "recorded approval of the spend); without it only the free stub provider runs")
    if "test_only" in doc and not isinstance(doc["test_only"], bool):
        raise PageSetError("image inputs: test_only must be true or false")
    out = dict(doc, image_provider=provider)
    out["allow_paid"] = provider == "kie" and bool(ref)
    return out


def fill_args(args, inputs: Dict[str, Any], names: Dict[str, str]) -> None:
    """Fill a wrapper's unset options from the shared inputs. `names` maps an inputs key to the
    argparse attribute ('brand_file' -> 'brand_file'). A flag the caller typed always wins."""
    for key, attr in names.items():
        if getattr(args, attr, None) in (None, "", False) and inputs.get(key) not in (None, ""):
            setattr(args, attr, inputs[key])


def stage_visual_bible(inputs: Optional[Dict[str, Any]], run_dir: Path) -> bool:
    """Copy the landing run's visual bible into a page's run folder so the page's files show the look
    it follows. False when there is none (the landing page itself, or a sequential hand run)."""
    ref = (inputs or {}).get("visual_bible_ref")
    if not ref or not Path(ref).is_file():
        return False
    Path(run_dir).mkdir(parents=True, exist_ok=True)
    (Path(run_dir) / "visual-bible.json").write_bytes(Path(ref).read_bytes())
    return True


def selection_inputs(inputs: Dict[str, Any], route_graph: str) -> Dict[str, Any]:
    """The inputs file Skill 78's run_image_stages.py reads, made from the shared inputs."""
    return {"route_graph": str(route_graph), "brand_file": inputs["brand_file"],
            "brand_owner": inputs["brand_owner"], "image_cap": inputs["image_cap"],
            "design_style": inputs.get("design_style"), "provider": inputs["image_provider"]}


def main(argv: List[str]) -> int:
    """python3 page_set.py <launch.json> [--landing-pages a,b] [--extra downsell_2]: print the plan."""
    import argparse
    ap = argparse.ArgumentParser(description="Print the page set and lane plan of a launch record.")
    ap.add_argument("launch")
    ap.add_argument("--landing-pages")
    ap.add_argument("--extra", action="append", default=[])
    ap.add_argument("--plain", action="store_true", help="print the plain-English page list instead of JSON")
    a = ap.parse_args(argv)
    launch = json.loads(Path(a.launch).read_text(encoding="utf-8"))
    ps = build_page_set(launch, landing_pages=a.landing_pages.split(",") if a.landing_pages else None,
                        extra_pages=a.extra)
    print(plain_summary(ps) if a.plain else json.dumps({**ps, "lane_plan": lane_plan(ps)}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
