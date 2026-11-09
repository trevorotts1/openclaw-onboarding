#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""prove_sf_build.py — fail-closed P7-BUILD gate for the Signature Funnel.

FIX-XC-03a: P7-BUILD was an unconditional no-op (`_delegation_seam(..., None, ...)`) —
a certificate could mint with no build receipt and no proof the GHL funnel/page build
ever cleared QC. This prover requires a real `build_receipt.json` produced by the Skill 6
build rail and enforces the two documented invariants (FUNNEL-MANIFEST P7):
  * funnel-build QC score >= 8.5 (the OpenClaw QC threshold), MEASURED from the receipt
    and NEVER assumed — a missing/non-numeric/below-floor score FAILS.   -> AF-FUN-BUILD-QC
  * a non-empty http(s) preview URL for every built page (preview-only
    delivery still needs a real preview to hand to human approval).      -> AF-FUN-BUILD-PREVIEW
  * that preview URL is not a placeholder/example/loopback host — a
    caller-authored stand-in is not a preview.                  -> AF-FUN-BUILD-PREVIEW-PLACEHOLDER

A10 / T0-11 — COMPLETENESS. The gate above verified every page the receipt SUPPLIED
and never checked that all required pages were supplied, so a 7-step funnel whose
receipt carried 3 pages returned zero violations and reached a Complete verdict. The
required page-type set is now DERIVED from the locked funnel size (the 3/5/7 matrix in
structure/funnel_structure.json — the same source of truth P6 and P8 use) and any
missing page type FAILS.                                                 -> AF-FUN-BUILD-PAGESET
The size is resolved from --funnel-size (the orchestrator passes the LOCKED brief size)
or from the receipt's own funnel_size; an unresolvable size is fail-closed, and a
receipt whose declared size contradicts the brief FAILS. -> AF-FUN-BUILD-SIZE / -SIZE-MISMATCH

STR-18 / S06-08 / IMG-16 — THE RECEIPT IS NOT THE EVIDENCE. The receipt and the copy
ledger are authored by the run's own agent, so a score or a URL written in them proves
nothing. P7 now also reads what the TOOLS wrote under the run dir (--run-dir, default:
the receipt's folder):
  * pages/<profile>.fragment.html is PARSED for the profile's section markers
    (data-section="N", "TY-N") and count, never accepted as "any non-empty text".
                                                              -> AF-FUN-HTML-SECTIONS
  * the QC score is RECOMPUTED from the Skill 6 verify run under build/evidence
    (ghl_gate.require_pass re-run on that evidence root, then 10 x passing / total
    raw page records). No tool-run record, a failing gate, a recomputed score below the
    floor, or a receipt score above the recomputed one FAILS.   -> AF-FUN-BUILD-QC-RECORD
  * every receipt preview URL must be a URL a PASSING raw verify record checked.
                                                              -> AF-FUN-BUILD-PREVIEW-UNBOUND
  * every page of the funnel carries a wireframe + mockup set from
    legacy_downsell_images.py (page-images/page-images-receipt.json and one
    stage-executor-record.json per page and stage on disk): a funnel with no visual
    direction cannot be certified.                              -> AF-FUN-BUILD-VISUAL
Called with no run dir, none of this can be proven, so each of those codes fails closed.

Fail-closed: an absent/unreadable/empty receipt is a FAIL, never a pass.  -> AF-FUN-BUILD-MALFORMED
funnel_type mismatch (when declared) also FAILS.                          -> AF-FUN-BUILD-TYPE

stdlib only. Exit 0 = pass, exit 2 = violation, exit 3 = usage / fail-closed.
"""

from __future__ import annotations

import argparse
import atexit
import hashlib
import json
import os
import shutil
import sys
import tempfile
import uuid
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

EXIT_OK = 0
EXIT_VIOLATION = 2
EXIT_FAILCLOSED = 3

FUNNEL_TYPE = "signature_funnel"
QC_FLOOR = 8.5  # OpenClaw QC Protocol threshold (>= 8.5 auto-approves)

SKILL_DIR = Path(__file__).resolve().parents[1]
GHL_TOOLS = SKILL_DIR.parent / "06-ghl-install-pages" / "tools"  # Skill 6: ghl_gate / ghl_verify
EVIDENCE_REL = Path("build") / "evidence"        # Skill 6 verify evidence root inside the run dir
PAGE_IMAGES_REL = Path("page-images")            # legacy_downsell_images.py --out-dir
PAGE_IMAGES_RECEIPT = "page-images-receipt.json"
# Same tuple as legacy_downsell_images.STAGES (a test holds them equal).
VISUAL_STAGES = ("desktop-wireframe", "mobile-tablet", "visual-mockup")
MIN_SECTION_CHARS = 10   # a section marker around no real text is not a built section
QC_TOLERANCE = 0.05

# Hosts that are never a real preview. Matched as an exact host or a dotted suffix,
# so a genuine vendor host that merely CONTAINS one of these words (for example
# app.example-ghl.com) is not false-failed.
PLACEHOLDER_HOSTS = (
    "example.com", "example.org", "example.net", "example.edu", "invalid",
    "localhost", "127.0.0.1", "0.0.0.0", "test.com", "changeme.com", "todo.com",
)


def _host_of(url: str) -> str:
    try:
        return (urlparse(url.strip()).hostname or "").lower()
    except (ValueError, TypeError):
        return ""


def _placeholder_host(url: Any) -> bool:
    """True when the URL's host IS a placeholder host or a subdomain of one."""
    if not isinstance(url, str):
        return False
    host = _host_of(url)
    if not host:
        return False
    return any(host == ph or host.endswith("." + ph) for ph in PLACEHOLDER_HOSTS)


def _preview_ok(url: Any) -> bool:
    return isinstance(url, str) and url.strip().lower().startswith(("http://", "https://"))


def required_page_types(size: int) -> List[str]:
    """The page-type set a build receipt MUST carry for a locked funnel size, read
    from the SAME 3/5/7 matrix P6-COMPOSE and P8-DERIVE use. Raises on an unknown
    size or an unreadable matrix so the caller fails closed rather than guessing."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import prove_sf_graph  # noqa: E402  (sibling prover; single source of truth)
    return list(prove_sf_graph.funnel_pages(int(size)))


def _resolve_size(receipt: Dict[str, Any],
                  funnel_size: Optional[int]) -> Tuple[Optional[int], List[Tuple[str, str]]]:
    """(size, fails). Explicit --funnel-size (the LOCKED brief size) wins; the
    receipt's own declaration is cross-checked against it, never trusted over it."""
    fails: List[Tuple[str, str]] = []
    declared = receipt.get("funnel_size")
    declared = declared if isinstance(declared, int) and not isinstance(declared, bool) else None
    if funnel_size is not None and declared is not None and int(funnel_size) != declared:
        fails.append(("AF-FUN-BUILD-SIZE-MISMATCH",
                      f"build receipt declares funnel_size {declared} but the locked brief "
                      f"size is {int(funnel_size)} — the receipt does not describe this funnel"))
        return None, fails
    size = int(funnel_size) if funnel_size is not None else declared
    if size is None:
        fails.append(("AF-FUN-BUILD-SIZE",
                      "funnel size is unresolved (no --funnel-size and no receipt funnel_size) "
                      "— the required page set cannot be computed, so completeness cannot be "
                      "proven (fail-closed)"))
    return size, fails


def _structure() -> Dict[str, Any]:
    return json.loads((SKILL_DIR / "structure" / "funnel_structure.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# STR-18 — P5 fragments are PARSED for the profile's section markers.
# ---------------------------------------------------------------------------
_VOID = frozenset({"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
                   "param", "source", "track", "wbr"})


class _Fragment(HTMLParser):
    """Collects page markers (data-page / data-stage), the ordered data-section ids and the
    visible text under each section (nearest enclosing section; script/style ignored)."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.pages: List[str] = []
        self.sections: List[str] = []
        self.text: Dict[str, str] = {}
        self.all_text = ""
        self._stack: List[Tuple[str, Optional[str]]] = []

    def handle_starttag(self, tag, attrs):
        a = {k: (v or "") for k, v in attrs}
        for key in ("data-page", "data-stage"):
            if a.get(key, "").strip():
                self.pages.append(a[key].strip().lower())
        sid = a["data-section"].strip().upper() if "data-section" in a else None
        if sid is not None:
            self.sections.append(sid)
        if tag not in _VOID:
            self._stack.append((tag, sid))

    def handle_endtag(self, tag):
        for i in range(len(self._stack) - 1, -1, -1):
            if self._stack[i][0] == tag:
                del self._stack[i:]
                return

    def handle_data(self, data):
        if any(t in ("script", "style") for t, _ in self._stack):
            return
        self.all_text += data
        for _, sid in reversed(self._stack):
            if sid is not None:
                self.text[sid] = self.text.get(sid, "") + data
                return


def required_section_ids(structure: Dict[str, Any], slug: str) -> List[str]:
    """The data-section ids a page fragment must carry, in order, from the profile."""
    profile = (structure.get("profiles") or {}).get(slug) or {}
    if profile.get("microcopy_only"):
        return []
    if profile.get("thank_you"):
        return [k for k in (structure.get("thank_you") or {}) if str(k).upper().startswith("TY-")]
    return [str(n) for n in (profile.get("sections") or [])]


def html_fragment_violations(run_dir: Path, size: int) -> List[Tuple[str, str]]:
    """P5-HTML, strict: every matrix page's pages/<profile>.fragment.html must be a real
    fragment — root page marker, exactly the profile's section markers in order, each
    carrying text. A fragment containing only 'x' fails."""
    out: List[Tuple[str, str]] = []
    structure = _structure()
    for slug in required_page_types(size):
        path = Path(run_dir) / "pages" / f"{slug}.fragment.html"
        try:
            body = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""
        except OSError:
            body = ""
        if not body.strip():
            out.append(("AF-FUN-HTML-FRAGMENT", f"pages/{slug}.fragment.html is missing or empty"))
            continue
        frag = _Fragment()
        try:
            frag.feed(body)
            frag.close()
        except Exception as exc:  # noqa: BLE001 — unparseable markup is a fail, never a pass
            out.append(("AF-FUN-HTML-SECTIONS", f"pages/{slug}.fragment.html cannot be parsed ({exc})"))
            continue
        if slug not in frag.pages:
            out.append(("AF-FUN-HTML-SECTIONS",
                        f"pages/{slug}.fragment.html has no data-page=\"{slug}\" (or data-stage) root marker"))
        want = required_section_ids(structure, slug)
        if want and frag.sections != want:
            out.append(("AF-FUN-HTML-SECTIONS",
                        f"pages/{slug}.fragment.html carries data-section markers {frag.sections} "
                        f"but the '{slug}' profile requires {want} ({len(want)} sections, in order)"))
        elif want:
            thin = [sid for sid in want if len(frag.text.get(sid, "").strip()) < MIN_SECTION_CHARS]
            if thin:
                out.append(("AF-FUN-HTML-SECTIONS",
                            f"pages/{slug}.fragment.html: section(s) {thin} carry under "
                            f"{MIN_SECTION_CHARS} characters of text (a marker around nothing)"))
        elif len(frag.all_text.strip()) < MIN_SECTION_CHARS:
            out.append(("AF-FUN-HTML-SECTIONS",
                        f"pages/{slug}.fragment.html (microcopy-only page) carries no real text"))
    return out


# ---------------------------------------------------------------------------
# S06-08 / STR-18 — QC and preview URLs come from a TOOL RUN, not the receipt.
# ---------------------------------------------------------------------------
def _sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def tool_run_violations(receipt: Dict[str, Any], evidence_root: Path) -> List[Tuple[str, str]]:
    """Re-run Skill 6's ghl_gate.require_pass on the evidence root, recompute the QC score
    from the raw verify records and bind the receipt's preview URLs to passing records."""
    qc_code, bind_code = "AF-FUN-BUILD-QC-RECORD", "AF-FUN-BUILD-PREVIEW-UNBOUND"
    root = Path(evidence_root)
    if not root.is_dir():
        return [(qc_code, f"no tool-run QC record: evidence root {root} is absent, so the receipt's "
                          "qc_score is a claim nothing measured (fail-closed)")]
    try:
        if str(GHL_TOOLS) not in sys.path:
            sys.path.append(str(GHL_TOOLS))
        import ghl_gate  # noqa: E402  (Skill 6 verdict reader — the one gate)
        import ghl_verify  # noqa: E402
        rc = ghl_gate.require_pass(str(root))
        raw = json.loads((root / ghl_verify.RAW_REL).read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 — an unusable gate is a fail, never a pass
        return [(qc_code, f"ghl_gate.require_pass cannot be re-run on {root} ({exc}) (fail-closed)")]
    if rc != 0:
        return [(qc_code, f"ghl_gate.require_pass rc={rc} on {root}: the Skill 6 verify run is missing, "
                          "tampered, mock or failing")]
    records = [r for r in raw if isinstance(r, dict)] if isinstance(raw, list) else []
    if not records:
        return [(qc_code, "the verify run carries no page records to score")]
    passing = [r for r in records if r.get("PASS") is True]
    qc = round(10.0 * len(passing) / len(records), 2)
    out: List[Tuple[str, str]] = []
    if qc < QC_FLOOR:
        out.append((qc_code, f"QC recomputed from the verify run is {qc} "
                             f"({len(passing)}/{len(records)} pages), below the {QC_FLOOR} floor"))
    claimed = receipt.get("qc_score")
    if isinstance(claimed, (int, float)) and not isinstance(claimed, bool) and float(claimed) > qc + QC_TOLERANCE:
        out.append((qc_code, f"receipt qc_score {float(claimed)} exceeds the QC {qc} recomputed from "
                             "the verify run — the receipt may not claim more than the tool measured"))
    checked = {str(r.get("preview_url") or "").strip() for r in passing}
    for pg in receipt.get("pages") or []:
        url = pg.get("preview_url") if isinstance(pg, dict) else None
        if isinstance(url, str) and url.strip() and url.strip() not in checked:
            out.append((bind_code, f"page '{pg.get('page_type')}': preview_url {url!r} is not a URL "
                                   "any passing verify record checked"))
    return out


# ---------------------------------------------------------------------------
# IMG-16 — a funnel needs visual direction (wireframes + mockups) for every page.
# ---------------------------------------------------------------------------
def visual_direction_violations(run_dir: Path, size: int) -> List[Tuple[str, str]]:
    """Every page of the funnel needs the desktop wireframe, mobile wireframe and visual
    mockup records legacy_downsell_images.py writes under <run>/page-images. The design-only
    checkout may instead be named in the receipt's not_built (the tool says what it needs)."""
    code = "AF-FUN-BUILD-VISUAL"
    base = Path(run_dir) / PAGE_IMAGES_REL
    out: List[Tuple[str, str]] = []
    receipt: Dict[str, Any] = {}
    try:
        loaded = json.loads((base / PAGE_IMAGES_RECEIPT).read_text(encoding="utf-8"))
        receipt = loaded if isinstance(loaded, dict) else {}
    except (OSError, ValueError):
        pass
    if not receipt:
        out.append((code, f"{PAGE_IMAGES_REL}/{PAGE_IMAGES_RECEIPT} is absent or unreadable: no wireframe "
                          "or mockup set was produced (run scripts/legacy_downsell_images.py)"))
    claimed_pages = receipt.get("pages") if isinstance(receipt.get("pages"), dict) else {}
    not_built = receipt.get("not_built") if isinstance(receipt.get("not_built"), dict) else {}
    for slug in required_page_types(size):
        if slug == "checkout" and slug not in claimed_pages and slug in not_built:
            continue  # design-only: the receipt names it as not built and says what it needs
        for stage in VISUAL_STAGES:
            rec = base / slug / stage / "stage-executor-record.json"
            try:
                data = json.loads(rec.read_text(encoding="utf-8"))
                images = data.get("images") if isinstance(data, dict) else None
            except (OSError, ValueError):
                images = None
            if not isinstance(images, list) or not images:
                out.append((code, f"page '{slug}': no {stage} record with images at "
                                  f"{PAGE_IMAGES_REL}/{slug}/{stage}/ (no wireframe/mockup set)"))
                continue
            claimed = (((claimed_pages.get(slug) or {}).get("stages") or {}).get(stage) or {}).get("sha256")
            if receipt and claimed != _sha256_file(rec):
                out.append((code, f"page '{slug}': {stage} record does not match the sha256 in "
                                  f"{PAGE_IMAGES_RECEIPT}"))
    return out


def verify(receipt: Dict[str, Any], funnel_size: Optional[int] = None,
           run_dir: Optional[Path] = None,
           evidence_root: Optional[Path] = None) -> Tuple[List[Tuple[str, str]], List[str]]:
    fails: List[Tuple[str, str]] = []
    notes: List[str] = []

    def fail(code: str, msg: str) -> None:
        fails.append((code, msg))

    if not isinstance(receipt, dict):
        return [("AF-FUN-BUILD-MALFORMED", "build receipt is not a JSON object")], notes

    ftype = receipt.get("funnel_type")
    if ftype is not None and ftype != FUNNEL_TYPE:
        fail("AF-FUN-BUILD-TYPE", f"funnel_type is {ftype!r}, expected {FUNNEL_TYPE!r}")

    # QC score — measured, never assumed. bool is rejected (isinstance(True,int) guard).
    score = receipt.get("qc_score")
    if isinstance(score, bool) or not isinstance(score, (int, float)):
        fail("AF-FUN-BUILD-QC", f"qc_score is {score!r} — must be a number (fail-closed)")
    elif float(score) < QC_FLOOR:
        fail("AF-FUN-BUILD-QC", f"qc_score {float(score)} is below the {QC_FLOOR} funnel-build floor")

    pages = receipt.get("pages")
    if not isinstance(pages, list) or not pages:
        return [("AF-FUN-BUILD-MALFORMED",
                 "build receipt carries no non-empty 'pages' array (cannot prove a build)")] + fails, notes

    supplied: List[str] = []
    for i, pg in enumerate(pages):
        if not isinstance(pg, dict):
            fail("AF-FUN-BUILD-MALFORMED", f"page entry #{i} is not an object")
            continue
        who = str(pg.get("page_type") or pg.get("id") or f"#{i}")
        pt = str(pg.get("page_type") or "").strip().lower()
        if pt:
            supplied.append(pt)
        url = pg.get("preview_url")
        if not _preview_ok(url):
            fail("AF-FUN-BUILD-PREVIEW",
                 f"page '{who}': preview_url {url!r} is not a non-empty http(s) URL")
        elif _placeholder_host(url):
            fail("AF-FUN-BUILD-PREVIEW-PLACEHOLDER",
                 f"page '{who}': preview_url {url!r} resolves to placeholder host "
                 f"{_host_of(url)!r} — a caller-authored stand-in is not a built preview")

    # A10 / T0-11 — COMPLETENESS against the locked size.
    size, size_fails = _resolve_size(receipt, funnel_size)
    fails.extend(size_fails)
    if size is not None:
        try:
            required = required_page_types(size)
        except (ValueError, OSError, ImportError) as exc:
            fail("AF-FUN-BUILD-SIZE",
                 f"cannot resolve the {size}-step page matrix ({exc}) — completeness cannot "
                 "be proven (fail-closed)")
        else:
            missing = [p for p in required if p.strip().lower() not in supplied]
            if missing:
                fail("AF-FUN-BUILD-PAGESET",
                     f"build receipt supplies {sorted(set(supplied))} but the {size}-step "
                     f"funnel requires {required} — missing {missing}. Every required page "
                     "must be built and previewed before the funnel can be Complete.")
            extra = sorted(set(supplied) - {p.strip().lower() for p in required})
            if extra:
                notes.append(f"receipt carries {len(extra)} page type(s) outside the "
                             f"{size}-step matrix: {extra} (not a violation)")
            notes.append(f"page-set completeness checked against the {size}-step matrix "
                         f"({len(required)} required page type(s))")

    # STR-18 / S06-08 / IMG-16 — the evidence the tools wrote, not the receipt's word.
    if run_dir is None:
        for code in ("AF-FUN-HTML-SECTIONS", "AF-FUN-BUILD-QC-RECORD",
                     "AF-FUN-BUILD-PREVIEW-UNBOUND", "AF-FUN-BUILD-VISUAL"):
            fail(code, "no run directory supplied: the built pages, the tool-run QC record and the "
                       "visual-direction set cannot be read, so they cannot be proven (fail-closed)")
    elif size is not None and not any(c == "AF-FUN-BUILD-SIZE" for c, _ in fails):
        rd = Path(run_dir)
        fails.extend(html_fragment_violations(rd, size))
        fails.extend(tool_run_violations(receipt, Path(evidence_root) if evidence_root else rd / EVIDENCE_REL))
        fails.extend(visual_direction_violations(rd, size))
        notes.append(f"run-dir evidence checked under {rd} (fragments, tool-run QC, visual direction)")

    notes.append(f"checked build receipt: qc_score={receipt.get('qc_score')!r} (floor {QC_FLOOR}), "
                 f"{len(pages)} page(s) with preview URLs")
    return fails, notes


# ---------------------------------------------------------------------------
# IO
# ---------------------------------------------------------------------------
def _load_json(path: str) -> Any:
    if path == "-":
        return json.loads(sys.stdin.read())
    return json.loads(Path(path).read_text(encoding="utf-8", errors="replace"))


def _report(violations, notes) -> None:
    for note in notes:
        print(f"NOTE: {note}")
    if not violations:
        print(f"PASS: funnel build receipt clears QC >= {QC_FLOOR} with a preview URL per page.")
        return
    print(f"FAIL: {len(violations)} build-receipt violation(s) — P7-BUILD does not clear.")
    for code, msg in violations:
        print(f"  VIOLATION [{code}] {msg}")


# ---------------------------------------------------------------------------
# Self-test fixtures.
# ---------------------------------------------------------------------------
def _valid_receipt(size: int = 5) -> Dict[str, Any]:
    """A COMPLETE receipt for `size`: every page type the locked matrix requires,
    built and previewed on a real (non-placeholder) vendor host.

    A10 / T0-11 — this fixture used to hardcode a 3-page list (main/upsell/
    thank-you) while declaring funnel_size 5, and the gate passed it. It now
    derives its page list from the SAME matrix the gate checks against, so the
    fixture cannot silently disagree with the contract it is meant to exercise."""
    stages = required_page_types(size)
    return {
        "funnel_type": FUNNEL_TYPE,
        "funnel_size": size,
        "qc_score": 9.1,
        "pages": [
            {"page_type": s, "status": "built",
             "preview_url": f"https://app.gohighlevel.com/funnels/preview/{s}"}
            for s in stages
        ],
    }


def _valid_fragment(slug: str) -> str:
    """A passing pages/<slug>.fragment.html: root page marker plus the profile's section
    markers in order, each around real text."""
    ids = required_section_ids(_structure(), slug)
    body = "".join(f'  <div class="sf-sec" data-section="{sid}"><p>{slug} section {sid} copy that '
                   f'carries real words.</p></div>\n' for sid in ids)
    if not ids:
        body = f"  <p>{slug} order page microcopy with real words.</p>\n"
    return f'<section class="sf-page" data-page="{slug}">\n{body}</section>\n'


def write_valid_run_evidence(run_dir: Path, size: int,
                             receipt: Optional[Dict[str, Any]] = None) -> None:
    """Write, under run_dir, everything the strict P7 reads that the TOOLS produce — the
    fixture the orchestrator's own self-test and the golden sample call so their runs
    keep certifying: valid page fragments, a Skill 6 verify evidence tree that clears
    ghl_gate.require_pass (build/evidence), and a legacy_downsell_images.py output set
    (page-images). Test fixtures only; never a substitute for a real tool run."""
    rd = Path(run_dir)
    receipt = receipt or _valid_receipt(size)
    (rd / "build_receipt.json").write_text(json.dumps(receipt), encoding="utf-8")
    (rd / "pages").mkdir(parents=True, exist_ok=True)
    for slug in required_page_types(size):
        (rd / "pages" / f"{slug}.fragment.html").write_text(_valid_fragment(slug), encoding="utf-8")
    # Skill 6 verify evidence, sealed the way ghl_verify.verify_all leaves it: raw records, a render
    # manifest naming a dom/png/console file per page (re-hashed by the gate), the summary ghl_verify
    # derives, and the 0600 run-nonce file OUTSIDE the evidence tree (ghl_gate.require_pass reads all).
    sys.path.append(str(GHL_TOOLS))
    import ghl_verify  # noqa: E402
    nonce = str(uuid.uuid4())
    ev = rd / EVIDENCE_REL
    (ev / "scorecard").mkdir(parents=True, exist_ok=True)
    (ev / "logs").mkdir(parents=True, exist_ok=True)
    (ev / "render").mkdir(parents=True, exist_ok=True)
    raw: List[Dict[str, Any]] = []
    manifest: Dict[str, Any] = {}
    for pg in receipt["pages"]:
        step, marker = pg["page_type"], f"sf-fixture-marker-{pg['page_type']}"
        entry: Dict[str, Any] = {}
        for key, ext, data in (("dom", "dom.html", f"<html><body><p>{marker}</p></body></html>".encode()),
                               ("png", "png", b"\x89PNG\r\n\x1a\n" + b"x" * 64),
                               ("console", "console.json", b"[]")):
            path = ev / "render" / f"{step}.{ext}"
            path.write_bytes(data)
            entry[f"{key}_path"] = str(path)
            entry[f"{key}_sha256"] = _sha256_file(path)
        manifest[step] = entry
        raw.append({"step": step, "page_id": f"p-{step}", "preview_url": pg["preview_url"],
                    "marker": marker, "http": 200, "http_code": 200, "marker_in_rendered_dom": True,
                    "marker_in_preview": True, "render_errors": [], "PASS": True})
    raw_bytes = json.dumps(raw).encode("utf-8")
    (ev / ghl_verify.RAW_REL).write_bytes(raw_bytes)
    (ev / ghl_verify.RENDER_MANIFEST_REL).write_text(json.dumps(manifest), encoding="utf-8")
    summary = ghl_verify.derive_summary(raw, run_id=rd.name, run_nonce=nonce)
    summary["raw_sha256"] = hashlib.sha256(raw_bytes).hexdigest()
    (ev / ghl_verify.SUMMARY_REL).write_text(json.dumps(summary), encoding="utf-8")
    if not os.environ.get(ghl_verify.NONCE_DIR_ENV):   # never write the fixture nonce into a real HOME
        nd = tempfile.mkdtemp(prefix="sf_ghl_nonces_")
        os.environ[ghl_verify.NONCE_DIR_ENV] = nd
        atexit.register(shutil.rmtree, nd, True)
    ghl_verify.write_run_nonce(str(rd), nonce, str(ev / ghl_verify.RAW_REL),
                               str(ev / ghl_verify.RENDER_MANIFEST_REL))
    # legacy_downsell_images.py output shape: one record per page and stage, plus the receipt.
    out = rd / PAGE_IMAGES_REL
    pages: Dict[str, Any] = {}
    for slug in required_page_types(size):
        if slug == "checkout":
            continue
        stages = {}
        for stage in VISUAL_STAGES:
            rec = out / slug / stage / "stage-executor-record.json"
            rec.parent.mkdir(parents=True, exist_ok=True)
            rec.write_text(json.dumps({"images": [{"id": f"{slug}-{stage}-1"}]}), encoding="utf-8")
            stages[stage] = {"record": str(rec), "sha256": _sha256_file(rec), "images": 1}
        pages[slug] = {"stages": stages}
    (out / PAGE_IMAGES_RECEIPT).write_text(json.dumps(
        {"funnel_size": size, "pages": pages,
         "not_built": {"checkout": "design-only page"} if size == 7 else {}}), encoding="utf-8")


def _evidence_cases():
    """(name, expected AF code, mutate(run_dir)) — each breaks ONE thing in a run dir that
    write_valid_run_evidence made, and must produce its code."""
    def frag(slug, text):
        return lambda rd: (rd / "pages" / f"{slug}.fragment.html").write_text(text, encoding="utf-8")

    def drop_section(rd):
        p = rd / "pages" / "main.fragment.html"
        p.write_text(p.read_text(encoding="utf-8").replace('data-section="7"', 'data-x="7"'), encoding="utf-8")

    def empty_section(rd):
        p = rd / "pages" / "upsell.fragment.html"
        p.write_text(p.read_text(encoding="utf-8").replace("upsell section 3 copy that carries real words.", ""),
                     encoding="utf-8")

    def drop_evidence(rd):
        shutil.rmtree(rd / EVIDENCE_REL)

    def failing_summary(rd):
        sp = rd / EVIDENCE_REL / "scorecard" / "verify-summary.json"
        d = json.loads(sp.read_text(encoding="utf-8"))
        d["overall_pass"] = False
        sp.write_text(json.dumps(d), encoding="utf-8")

    def tamper_raw(rd):
        rp = rd / EVIDENCE_REL / "logs" / "final-preview-verify.json"
        rp.write_text(rp.read_text(encoding="utf-8").replace('"PASS": true', '"PASS": false', 1), encoding="utf-8")

    def unbound_url(rd):
        p = rd / "build_receipt.json"
        d = json.loads(p.read_text(encoding="utf-8"))
        d["pages"][0]["preview_url"] = "https://app.gohighlevel.com/funnels/preview/never-verified"
        p.write_text(json.dumps(d), encoding="utf-8")

    def drop_visuals(rd):
        shutil.rmtree(rd / PAGE_IMAGES_REL)

    def drop_one_stage(rd):
        (rd / PAGE_IMAGES_REL / "upsell" / "visual-mockup" / "stage-executor-record.json").unlink()

    return [
        ("fragment_x", "AF-FUN-HTML-SECTIONS", frag("main", "x")),
        ("fragment_no_root_marker", "AF-FUN-HTML-SECTIONS", frag("main", "<section><p>" + "word " * 30 + "</p></section>")),
        ("fragment_missing_marker", "AF-FUN-HTML-SECTIONS", drop_section),
        ("fragment_empty_section", "AF-FUN-HTML-SECTIONS", empty_section),
        ("fragment_missing_file", "AF-FUN-HTML-FRAGMENT",
         lambda rd: (rd / "pages" / "thank-you.fragment.html").unlink()),
        ("no_tool_run_record", "AF-FUN-BUILD-QC-RECORD", drop_evidence),
        ("tool_run_failing", "AF-FUN-BUILD-QC-RECORD", failing_summary),
        ("tool_run_raw_tampered", "AF-FUN-BUILD-QC-RECORD", tamper_raw),
        ("preview_url_not_verified", "AF-FUN-BUILD-PREVIEW-UNBOUND", unbound_url),
        ("no_visual_direction", "AF-FUN-BUILD-VISUAL", drop_visuals),
        ("one_page_missing_mockup", "AF-FUN-BUILD-VISUAL", drop_one_stage),
    ]


def _violation_cases():
    def low_qc(r):
        r["qc_score"] = 7.9

    def missing_qc(r):
        r.pop("qc_score", None)

    def bool_qc(r):
        r["qc_score"] = True

    def empty_preview(r):
        r["pages"][1]["preview_url"] = ""

    def bad_preview(r):
        r["pages"][0]["preview_url"] = "ftp://nope"

    def placeholder_preview(r):
        r["pages"][0]["preview_url"] = "https://preview.example.com/main"

    def no_pages(r):
        r["pages"] = []

    def wrong_type(r):
        r["funnel_type"] = "sales_page"

    def drop_a_page(r):
        # T0-11 in one line: hand back fewer pages than the locked size requires.
        r["pages"] = r["pages"][:-1]

    def undersized_receipt(r):
        # the exact shape the finding describes: a 7-step funnel, 3 pages supplied.
        r["funnel_size"] = 7
        r["pages"] = [p for p in r["pages"]
                      if p["page_type"] in ("main", "upsell", "thank-you")]

    def size_lies(r):
        r["funnel_size"] = 3  # contradicts the locked brief size passed in below

    def _mk(fn, size=5):
        r = _valid_receipt(size)
        fn(r)
        return r

    return [
        ("low_qc", "AF-FUN-BUILD-QC", lambda: (_mk(low_qc), None)),
        ("missing_qc", "AF-FUN-BUILD-QC", lambda: (_mk(missing_qc), None)),
        ("bool_qc", "AF-FUN-BUILD-QC", lambda: (_mk(bool_qc), None)),
        ("empty_preview", "AF-FUN-BUILD-PREVIEW", lambda: (_mk(empty_preview), None)),
        ("bad_preview_scheme", "AF-FUN-BUILD-PREVIEW", lambda: (_mk(bad_preview), None)),
        ("placeholder_preview_host", "AF-FUN-BUILD-PREVIEW-PLACEHOLDER",
         lambda: (_mk(placeholder_preview), None)),
        ("no_pages", "AF-FUN-BUILD-MALFORMED", lambda: (_mk(no_pages), None)),
        ("wrong_type", "AF-FUN-BUILD-TYPE", lambda: (_mk(wrong_type), None)),
        # --- A10 / T0-11 completeness ---
        ("missing_one_required_page", "AF-FUN-BUILD-PAGESET", lambda: (_mk(drop_a_page), None)),
        ("seven_step_funnel_three_pages", "AF-FUN-BUILD-PAGESET",
         lambda: (_mk(undersized_receipt, 7), None)),
        # An undeclared receipt cannot dodge completeness by simply not naming a
        # size: the LOCKED brief size the orchestrator passes decides the set.
        ("three_pages_against_locked_size_7", "AF-FUN-BUILD-PAGESET",
         lambda: (_mk(lambda r: r.pop("funnel_size", None), 3), 7)),
        ("receipt_size_contradicts_brief", "AF-FUN-BUILD-SIZE-MISMATCH",
         lambda: (_mk(size_lies), 5)),
        ("unresolvable_size", "AF-FUN-BUILD-SIZE",
         lambda: ({"funnel_type": FUNNEL_TYPE, "qc_score": 9.1,
                   "pages": [{"page_type": "main", "status": "built",
                              "preview_url": "https://app.gohighlevel.com/p/main"}]}, None)),
    ]


def run_self_test() -> int:
    ok = True
    for size in (3, 5, 7):
        with tempfile.TemporaryDirectory(prefix="sf_build_selftest_") as td:
            write_valid_run_evidence(Path(td), size)
            v, _ = verify(_valid_receipt(size), funnel_size=size, run_dir=Path(td))
        if v:
            ok = False
            print(f"SELF-TEST FAIL: complete {size}-step receipt produced "
                  f"{len(v)} violation(s): {v}")
        else:
            print(f"SELF-TEST ok: COMPLETE {size}-step receipt PASSES (0 violations, "
                  f"{len(required_page_types(size))} required page types present, "
                  "fragments + tool-run QC + visual direction on disk).")
    ev_caught = 0
    for name, expected, mutate in _evidence_cases():
        with tempfile.TemporaryDirectory(prefix="sf_build_selftest_") as td:
            write_valid_run_evidence(Path(td), 5)
            mutate(Path(td))
            vio, _ = verify(json.loads((Path(td) / "build_receipt.json").read_text(encoding="utf-8")),
                            funnel_size=5, run_dir=Path(td))
        codes = {c for c, _ in vio}
        if expected in codes:
            ev_caught += 1
            print(f"SELF-TEST ok: run-dir case '{name}' -> carries {expected}.")
        else:
            ok = False
            print(f"SELF-TEST FAIL: run-dir case '{name}' -> {sorted(codes)} (expected {expected}).")
    vio, _ = verify(_valid_receipt(5), funnel_size=5)  # no run dir: nothing provable
    if {"AF-FUN-HTML-SECTIONS", "AF-FUN-BUILD-QC-RECORD", "AF-FUN-BUILD-PREVIEW-UNBOUND",
            "AF-FUN-BUILD-VISUAL"} <= {c for c, _ in vio}:
        ev_caught += 1
        print("SELF-TEST ok: a receipt with no run dir fails closed on every evidence code.")
    else:
        ok = False
        print("SELF-TEST FAIL: a receipt with no run dir was not failed closed.")
    cases = _violation_cases()
    caught = 0
    for name, expected, build in cases:
        receipt, size = build()
        vio, _ = verify(receipt, funnel_size=size)
        codes = {c for c, _ in vio}
        if not vio:
            ok = False
            print(f"SELF-TEST FAIL: '{name}' produced NO violations (expected {expected}).")
        elif expected not in codes:
            ok = False
            print(f"SELF-TEST FAIL: '{name}' -> {sorted(codes)} (expected {expected}).")
        else:
            caught += 1
            print(f"SELF-TEST ok: '{name}' -> nonzero, carries {expected}.")
    print(f"SELF-TEST FIXTURES: 3 complete-pass (3/5/7), {caught}/{len(cases)} violation-catch, "
          f"{ev_caught}/{len(_evidence_cases()) + 1} run-dir evidence-catch")
    print("SELF-TEST RESULT:", "PASS (exit 0)" if ok else "FAIL (exit 1)")
    return 0 if ok else 1


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(
        description=f"Fail-closed P7-BUILD gate: validate build_receipt.json (QC >= {QC_FLOOR} + "
                    "preview URL per page). Exit 0 pass, 2 violation, 3 usage.")
    ap.add_argument("--receipt", help="path to build_receipt.json ('-' reads stdin)")
    ap.add_argument("receipt_pos", nargs="?", help="optional positional receipt path (equivalent to --receipt)")
    ap.add_argument("--funnel-size", type=int, default=None,
                    help="the LOCKED brief funnel size (3/5/7). Required page-type "
                         "completeness is computed from it; without it the receipt's own "
                         "funnel_size is used and an unresolvable size is fail-closed.")
    ap.add_argument("--run-dir", default=None,
                    help="the run directory holding pages/, build/evidence and page-images/ "
                         "(default: the folder of --receipt; stdin receipts have none and fail closed)")
    ap.add_argument("--evidence-root", default=None,
                    help="Skill 6 verify evidence root (default <run-dir>/build/evidence)")
    ap.add_argument("--self-test", action="store_true",
                    help="construct a VALID receipt (must PASS) + each VIOLATION fixture (must FAIL)")
    args = ap.parse_args(argv)

    if args.self_test:
        return run_self_test()

    receipt_path = args.receipt or args.receipt_pos
    if not receipt_path:
        print("USAGE ERROR: pass --receipt <build_receipt.json> (or a positional path, or --self-test).")
        return EXIT_FAILCLOSED
    try:
        receipt = _load_json(receipt_path)
    except Exception as exc:  # noqa: BLE001
        print(f"USAGE/IO ERROR: cannot load build receipt {receipt_path!r}: {exc}")
        return EXIT_FAILCLOSED

    run_dir = args.run_dir or (None if receipt_path == "-" else str(Path(receipt_path).resolve().parent))
    violations, notes = verify(receipt, funnel_size=args.funnel_size,
                               run_dir=Path(run_dir) if run_dir else None,
                               evidence_root=Path(args.evidence_root) if args.evidence_root else None)
    _report(violations, notes)
    return EXIT_OK if not violations else EXIT_VIOLATION


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
