#!/usr/bin/env python3
"""The one place that names a Skill 71 deliverable (page type + device + kind).

Every wireframe and mockup the client receives must say exactly what it is:
PAGE TYPE (Signature Landing Page, Order Page, Upsell 1, ...) + DEVICE
(DESKTOP or MOBILE) + KIND (WIREFRAME or MOCKUP) + Section N of M + section
name. combine_review_pdf.py (the PDF's one title band, PDF and image file names, client
delivery folders) and build_overview_board.py (board titles, headers, tile
captions, file names) both take their words from here, so a page type added
later is named once and every output follows.

The labels are driven only by `page_role` (a landing-role run whose page_kind is sales is named "sales_page") and the stage; no role is special-cased
beyond a display-name table, and an unknown role still gets a readable name.
Pure stdlib: no Pillow, no I/O except the run's own role files.
"""
import json
import re
from pathlib import Path

PAGE_TYPE = {
    "landing": "Signature Landing Page",
    "sales_page": "Signature Sales Page",
    "product_selection": "Order Page",
    "checkout": "Order Form / Checkout",
    "thank_you": "Thank-You Page",
}
# upsell_1, downsell_2, ... -> "Upsell 1", "Downsell 2" (any number)
_NUMBERED = re.compile(r"^(upsell|downsell)_(\d+)$")

# stage -> (kind, variant). Both wireframe stages are WIREFRAMEs (the device
# comes from the image set); the two mockup stages are told apart in file names.
STAGE_KIND = {
    "desktop-wireframe": ("WIREFRAME", ""),
    "mobile-tablet": ("WIREFRAME", ""),
    "visual-mockup": ("MOCKUP", "visual"),
    "final-mockups": ("MOCKUP", "final"),
}


def declared_page_role(run_dir):
    """The run's page role, read by scripts/page_role.py: the one reader the Design Board, the
    section-count check and the wireframe prompt use, so a label never names another page."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        import page_kinds
        import page_role
    finally:
        sys.path.pop(0)
    role = page_role.declared_role(run_dir)
    if role == "landing":  # a sales page is role landing: name it by its kind, like the Design Board
        try:
            if page_kinds.declared(run_dir, {}) == "sales":
                return "sales_page"
        except page_kinds.KindError:
            pass  # an unknown kind is refused by the gate; a label never crashes on it
    return role


def page_type(role):
    """Human page type for a page_role."""
    if role in PAGE_TYPE:
        return PAGE_TYPE[role]
    m = _NUMBERED.match(role or "")
    if m:
        return f"{m.group(1).title()} {m.group(2)}"
    return str(role or "page").replace("_", " ").replace("-", " ").title()


def role_slug(role):
    """File-name slug: upsell_1 -> upsell-1."""
    return re.sub(r"[^a-z0-9]+", "-", str(role or "page").lower()).strip("-") or "page"


def kind_variant(stage):
    return STAGE_KIND[stage]


def text_slug(text, limit=40):
    return re.sub(r"[^a-z0-9]+", "-", str(text or "").lower()).strip("-")[:limit].strip("-") or "section"


def _tag(variant, sep):
    return f"{sep}{variant}" if variant else ""


def headline(role, device, stage):
    """'UPSELL 1 · DESKTOP WIREFRAME' (device is desktop|mobile|desktop+mobile)."""
    kind, _ = kind_variant(stage)
    dev = device.upper().replace("+", " + ")
    return f"{page_type(role).upper()} · {dev} {kind}"


def section_text(n, m):
    return f"SECTION {n} OF {m}"


def folder(device, stage):
    """Client delivery folder: desktop-wireframes, mobile-wireframes, desktop-mockups, mobile-mockups."""
    kind, _ = kind_variant(stage)
    return f"{device.lower()}-{kind.lower()}s"


def pdf_name(role, device, stage):
    """upsell-1_DESKTOP_WIREFRAMES.pdf; mockups carry their stage: landing_MOBILE_MOCKUPS-FINAL.pdf."""
    kind, variant = kind_variant(stage)
    return f"{role_slug(role)}_{device.upper()}_{kind}S{_tag(variant.upper(), '-')}.pdf"


def image_name(role, device, stage, n, m, section_name):
    """upsell-1_desktop_wireframe_s03-of-08_offer.png"""
    kind, variant = kind_variant(stage)
    return (f"{role_slug(role)}_{device.lower()}_{kind.lower()}{_tag(variant, '-')}"
            f"_s{n:02d}-of-{m:02d}_{text_slug(section_name)}.png")


def board_name(role, device, stage):
    """Board file stem. device: desktop | mobile | combined.
    upsell-1_DESKTOP_WIREFRAME-BOARD, landing_DESKTOP-and-MOBILE_MOCKUP-FINAL-BOARD."""
    kind, variant = kind_variant(stage)
    dev = "DESKTOP-and-MOBILE" if device == "combined" else device.upper()
    return f"{role_slug(role)}_{dev}_{kind}{_tag(variant.upper(), '-')}-BOARD"


def board_title(role, device, stage):
    """Title band text of a board; device: desktop | mobile | combined."""
    return headline(role, "desktop+mobile" if device == "combined" else device, stage)


def title_band(role, device, stage, m):
    """The ONE label of a review PDF, printed once as a title band at the very
    top of page 1: 'DOWNSELL 1 \u00b7 DESKTOP WIREFRAME \u00b7 8 SECTIONS'.
    No other page, and no gap between two sections, carries a label."""
    return f"{headline(role, device, stage)} \u00b7 {m} SECTION{'' if m == 1 else 'S'}"


def page_label(role, device, stage, n, m):
    """Per-page label kept in the receipt only (never drawn on a page)."""
    return f"{headline(role, device, stage)} \u00b7 {section_text(n, m)}"


def band_height(width):
    """Height in px of the single title band on page 1 for a page `width` px wide.
    Pages 2 and on have no band at all: their height is exactly the section image's."""
    return max(40, round(width * 0.03))


if __name__ == "__main__":  # smoke: python3 deliverable_labels.py
    assert pdf_name("upsell_1", "desktop", "desktop-wireframe") == "upsell-1_DESKTOP_WIREFRAMES.pdf"
    assert image_name("upsell_1", "desktop", "desktop-wireframe", 3, 8, "Offer") == \
        "upsell-1_desktop_wireframe_s03-of-08_offer.png"
    assert title_band("downsell_1", "desktop", "desktop-wireframe", 8) == "DOWNSELL 1 \u00b7 DESKTOP WIREFRAME \u00b7 8 SECTIONS"
    assert page_type("upsell_2") == "Upsell 2" and page_type("downsell_1") == "Downsell 1"
    assert page_type("some_new_page") == "Some New Page"
    print("ok")
