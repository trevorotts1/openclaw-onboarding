#!/usr/bin/env python3
"""S80-08 local verification for the rendered upsell pages (L2).

Independently loads the adapter bundles, the copy fixtures, the upsell
profile and the generated HTML (via manifest.json), then asserts, per page:

  * exactly 8 sections, in the profile's section order (number and key);
  * exactly one CTA per section (CTA count == section count == 8);
  * every CTA carries the same data-action-ref, equal to the bundle's
    page_plan action ref, and its text equals the bundle cta_map text;
  * the bundle disclosure text appears verbatim as the element immediately
    following every CTA (adjacent to the primary CTA in particular);
  * a visible decline control exists that routes without charging
    (data-charges="false", target equal to the bundle decline target);
  * the acknowledgement blocks selected for the page's entry context are
    present, and the other path's acknowledgement is absent;
  * for the from_downsell_1 U2 page: the U1 offer name ("Deep Work Library")
    appears nowhere (spec 10 section 5 truth rule), while it does appear on
    the from_upsell_1 page where it is true;
  * processing / payment-pending / expired-context / one-click-unavailable
    states render every CTA disabled;
  * the suppressed state contains no charge action at all (no bundle action
    ref anywhere in the file, no data-action-ref attribute) and does carry
    the safe thank-you route.

Exit code 0 = all assertions pass; 1 = at least one failure (all failures are
printed). Run after render_pages.py.
"""

import json
import sys
from html.parser import HTMLParser
from pathlib import Path

PAGES_DIR = Path(__file__).resolve().parent
WORK_DIR = PAGES_DIR.parent
PROFILE = WORK_DIR / "80-signature-upsell" / "profiles" / "upsell-profile.json"

DISABLED_STATES = {"processing", "payment-pending", "expired-context", "one-click-unavailable"}
U1_OFFER_NAME = "Deep Work Library"

FAILURES = []


def check(condition, message):
    if not condition:
        FAILURES.append(message)


def load_json(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


class PageParse(HTMLParser):
    """Collects the structures the assertions need from one HTML file."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.sections = []          # list of dicts: number, key
        self.cta_blocks = []        # list of list-of-(tag, attrs, text) children
        self.buttons = []           # every <button>: attrs, text
        self.decline = None         # attrs of the decline element
        self.safe_route = None      # attrs of the suppressed continue link
        self.text = []              # all character data, in order
        self._stack = []
        self._cta_block = None
        self._capture = None        # (kind, attrs, buffer)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self._stack.append(tag)
        if tag == "section":
            self.sections.append(
                {"number": attrs.get("data-section-number"), "key": attrs.get("data-section-key")}
            )
        if tag == "div" and attrs.get("class") == "cta-block":
            self._cta_block = []
        if tag == "button":
            self._capture = ("button", attrs, [])
        if tag == "p" and self._cta_block is not None and "disclosure" in attrs.get("class", ""):
            self._capture = ("disclosure", attrs, [])
        if "data-decline-route" in attrs:
            self.decline = attrs
        if "data-safe-route-role" in attrs:
            self.safe_route = attrs

    def handle_data(self, data):
        self.text.append(data)
        if self._capture is not None:
            self._capture[2].append(data)

    def handle_endtag(self, tag):
        if self._capture is not None and (
            (self._capture[0] == "button" and tag == "button")
            or (self._capture[0] == "disclosure" and tag == "p")
        ):
            kind, attrs, buf = self._capture
            text = "".join(buf).strip()
            if kind == "button":
                self.buttons.append({"attrs": attrs, "text": text})
            if self._cta_block is not None:
                self._cta_block.append((kind, attrs, text))
            self._capture = None
        if tag == "div" and self._cta_block is not None:
            self.cta_blocks.append(self._cta_block)
            self._cta_block = None
        if self._stack and self._stack[-1] == tag:
            self._stack.pop()

    def full_text(self):
        return "".join(self.text)


def parse_file(path):
    parser = PageParse()
    parser.feed(path.read_text(encoding="utf-8"))
    parser.close()
    return parser


def expected_ack_texts(plan, entry_context):
    included, excluded = [], []
    for block in plan.get("acknowledgement_blocks", []):
        if block["condition"] == "verified_original_purchase" or block["condition"] == entry_context:
            included.append(block["text"])
        else:
            excluded.append(block["text"])
    return included, excluded


def check_offer_page(label, bundle, profile_sections, page_dir, state):
    plan = bundle["page_plan"]
    result = bundle["result"]
    entry_context = result["eligibility_check"].get("entry_context")
    path = page_dir / (state + ".html")
    check(path.exists(), "%s: missing state file %s" % (label, path))
    if not path.exists():
        return
    parsed = parse_file(path)
    action_ref = plan["action_binding"]["action_ref"]
    disclosure_text = plan["disclosure"]["text"]
    cta_map = {c["section_number"]: c for c in result["cta_map"]}

    # Sections: count and order vs profile.
    expected_numbers = [str(s["number"]) for s in profile_sections]
    expected_keys = [s["key"] for s in profile_sections]
    got_numbers = [s["number"] for s in parsed.sections]
    got_keys = [s["key"] for s in parsed.sections]
    check(
        got_numbers == expected_numbers,
        "%s/%s: section numbers %s != profile %s" % (label, state, got_numbers, expected_numbers),
    )
    check(
        got_keys == expected_keys,
        "%s/%s: section keys %s != profile %s" % (label, state, got_keys, expected_keys),
    )

    # CTAs: one per section, same action ref, bundle text.
    ctas = [b for b in parsed.buttons if "cta" in b["attrs"].get("class", "")]
    check(
        len(ctas) == len(parsed.sections) == 8,
        "%s/%s: CTA count %d, section count %d (want 8/8)"
        % (label, state, len(ctas), len(parsed.sections)),
    )
    refs = {b["attrs"].get("data-action-ref") for b in ctas}
    check(
        refs == {action_ref},
        "%s/%s: CTA action refs %s != bundle %s" % (label, state, refs, action_ref),
    )
    for idx, button in enumerate(ctas, start=1):
        check(
            button["text"] == cta_map[idx]["cta_text"],
            "%s/%s: CTA %d text %r != bundle cta_map %r"
            % (label, state, idx, button["text"], cta_map[idx]["cta_text"]),
        )

    # Disclosure adjacency: every cta-block is exactly [button, disclosure p]
    # and the disclosure text is the bundle's, verbatim. Block 0 holds the
    # primary CTA, so adjacency to the primary CTA is covered explicitly.
    check(
        len(parsed.cta_blocks) == 8,
        "%s/%s: found %d cta-blocks, want 8" % (label, state, len(parsed.cta_blocks)),
    )
    for idx, block in enumerate(parsed.cta_blocks, start=1):
        kinds = [item[0] for item in block]
        check(
            kinds == ["button", "disclosure"],
            "%s/%s: cta-block %d children %s, want [button, disclosure] (adjacent)"
            % (label, state, idx, kinds),
        )
        if len(block) == 2:
            check(
                block[1][2] == disclosure_text,
                "%s/%s: cta-block %d disclosure %r != bundle disclosure verbatim"
                % (label, state, idx, block[1][2]),
            )

    # Decline control: present, visible, no charge, bundle target.
    decline = plan["states"]["decline"]
    check(parsed.decline is not None, "%s/%s: no decline control found" % (label, state))
    if parsed.decline is not None:
        check(
            parsed.decline.get("data-decline-route") == decline["target_page_id"],
            "%s/%s: decline target %s != bundle %s"
            % (label, state, parsed.decline.get("data-decline-route"), decline["target_page_id"]),
        )
        check(
            parsed.decline.get("data-charges") == "false",
            "%s/%s: decline control does not declare data-charges=false" % (label, state),
        )
        check(
            "hidden" not in parsed.decline,
            "%s/%s: decline control is hidden" % (label, state),
        )

    # Acknowledgements for this entry context present; the other path's absent.
    included, excluded = expected_ack_texts(plan, entry_context)
    full = parsed.full_text()
    for text in included:
        check(text in full, "%s/%s: acknowledgement block missing: %r" % (label, state, text[:60]))
    for text in excluded:
        check(
            text not in full,
            "%s/%s: other-path acknowledgement leaked in: %r" % (label, state, text[:60]),
        )

    # State-specific control availability.
    if state in DISABLED_STATES:
        enabled = [b for b in ctas if "disabled" not in b["attrs"]]
        check(
            not enabled,
            "%s/%s: %d CTAs are NOT disabled in a state that must block repeats"
            % (label, state, len(enabled)),
        )
    if state == "default":
        disabled = [b for b in ctas if "disabled" in b["attrs"]]
        check(not disabled, "%s/default: CTAs must be enabled in the default state" % label)


def check_suppressed(label, bundle, page_dir):
    plan = bundle["page_plan"]
    action_ref = plan["action_binding"]["action_ref"]
    path = page_dir / "suppressed.html"
    check(path.exists(), "%s: missing suppressed.html" % label)
    if not path.exists():
        return
    raw = path.read_text(encoding="utf-8")
    parsed = parse_file(path)
    check(
        action_ref not in raw,
        "%s/suppressed: bundle action ref %r present in suppressed page" % (label, action_ref),
    )
    check(
        "data-action-ref" not in raw,
        "%s/suppressed: a data-action-ref attribute is present (charge action leaked)"
        % label,
    )
    check(
        not parsed.buttons,
        "%s/suppressed: %d buttons present, want none" % (label, len(parsed.buttons)),
    )
    check(
        parsed.safe_route is not None and parsed.safe_route.get("data-safe-route-role") == "thank_you",
        "%s/suppressed: safe thank-you continuation route missing" % label,
    )
    check(
        parsed.decline is None,
        "%s/suppressed: unexpected decline control on the suppressed page" % label,
    )


def main():
    profile = load_json(PROFILE)
    profile_sections = sorted(profile["sections"], key=lambda s: s["number"])
    manifest = load_json(PAGES_DIR / "manifest.json")
    for page in manifest["pages"]:
        bundle = load_json(WORK_DIR / page["bundle_file"])
        page_dir = PAGES_DIR / page["directory"]
        label = page["directory"]
        for state in page["states"]:
            if state == "suppressed":
                check_suppressed(label, bundle, page_dir)
            else:
                check_offer_page(label, bundle, profile_sections, page_dir, state)
        # D1-path truth rule (spec 10 section 5): the U1 offer name must not
        # appear anywhere on the D1-entry U2 render; it must appear on the
        # U1-entry render, where the acknowledgement truthfully names it.
        default_raw = (page_dir / "default.html").read_text(encoding="utf-8")
        if page["entry_context"] == "from_downsell_1":
            check(
                U1_OFFER_NAME not in default_raw,
                "%s: U1 offer name %r appears on the D1-path U2 page" % (label, U1_OFFER_NAME),
            )
        if page["entry_context"] == "from_upsell_1":
            check(
                U1_OFFER_NAME in default_raw,
                "%s: U1 offer name %r missing from the U1-path U2 page ack" % (label, U1_OFFER_NAME),
            )
    total_pages = len(manifest["pages"])
    if FAILURES:
        print("FAIL (%d failures):" % len(FAILURES))
        for failure in FAILURES:
            print("  - " + failure)
        return 1
    print(
        "PASS: all S80-08 page assertions hold for %d page instances x %d states."
        % (total_pages, len(manifest["pages"][0]["states"]))
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
