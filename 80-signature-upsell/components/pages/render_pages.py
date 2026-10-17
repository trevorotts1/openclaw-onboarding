#!/usr/bin/env python3
"""S80-08 local renderer (L2 local rendered proof).

Deterministically renders static HTML for the two TEST ONLY upsell page
instances from the S80 adapter bundles and their copy fixtures. The HTML is
generated from the bundle JSON (page_plan, cta_map, disclosure,
acknowledgement blocks, decline/success routes) and the copy fixture the
bundle itself names in result.artifacts[0]. Nothing is hand-written per page:
if the copy fixture and the bundle disagree on a CTA text or action ref, the
renderer fails loudly instead of papering over the divergence.

The CTAs bind the bundles' S80-06 extra-offer binding ref
("extra-offer-binding:<offer_id>", action_id null, binding status
interface_conformant_pending_s06): the binding is interface-conformant at
fixture level, native install is pending S06 confirmation, and no live
native action exists. These pages cannot charge anything; they are local
proof only. No timestamps: identical inputs give identical bytes on every
run.

Usage: python3 render_pages.py
Writes, under this script's directory:
  <page-dir>/<state>.html  for each bundle and each render state
  index.html               listing of every generated page/state
  manifest.json            machine-readable list consumed by check_pages.py
"""

import hashlib
import html
import json
import sys
from pathlib import Path

PAGES_DIR = Path(__file__).resolve().parent
WORK_DIR = PAGES_DIR.parent
ADAPTER_FIXTURES = WORK_DIR / "adapters" / "fixtures"

BUNDLE_FILES = [
    "expected-bundle-upsell1.testonly.json",
    "expected-bundle-upsell2-from-upsell1.testonly.json",
    "expected-bundle-upsell2-from-downsell1.testonly.json",
]

# Render states per page. "suppressed" is the already-owned/incompatible
# disposition (safe thank-you route, no charge action) and gets its own
# minimal renderer; every other state renders the full offer page with a
# state banner and state-appropriate control availability.
STATES = [
    "default",
    "processing",
    "payment-failed",
    "payment-pending",
    "authentication-required",
    "expired-context",
    "one-click-unavailable",
    "suppressed",
]

# States in which the paid action must be inert, per the bundle page_plan
# state behaviours (processing: single-flight guard; expired-context and
# one-click-unavailable: block_paid_action_safe_continuation).
CTA_DISABLED_STATES = {"processing", "payment-pending", "expired-context", "one-click-unavailable"}

STATE_BANNERS = {
    "processing": (
        "Processing your choice - please wait. The accept button is disabled "
        "while your payment is confirmed, so it cannot be triggered twice."
    ),
    "payment-failed": (
        "Your payment did not go through and no charge was made. Nothing was "
        "added to your order. This is not a decline: you can try the same "
        "button again, or use the no-thanks link to continue without the extra."
    ),
    "payment-pending": (
        "Your payment is still being confirmed. This is not yet an acceptance "
        "and not yet a decline, and nothing is final until the confirmation arrives."
    ),
    "authentication-required": (
        "Your payment provider needs you to confirm this payment before it can "
        "complete (for example in your banking app). No charge has been "
        "completed yet. When you have confirmed, reload the offer to continue."
    ),
    "expired-context": (
        "Your saved payment context has expired, so the one-click action is "
        "blocked for safety. You have not been charged and no payment token "
        "has been created. You can continue without the extra below."
    ),
    "one-click-unavailable": (
        "One-click purchase is not available for this offer right now, so the "
        "paid action is blocked rather than replaced with a different "
        "checkout. You have not been charged. You can continue without the "
        "extra below."
    ),
}

CSS = """
:root{
  --ink:#212631; --paper:#fffdf8; --tint:#eef3fd; --accent:#2456c8;
  --accent-dark:#1a4199; --amber:#ffb340; --line:#d9dee9; --muted:#4d5566;
}
*{box-sizing:border-box}
body{margin:0;background:#f4f2ec;color:var(--ink);
  font-family:Georgia,'Times New Roman',serif;line-height:1.55}
main{max-width:46rem;margin:0 auto;padding:0 1rem 3rem}
.test-banner{background:var(--amber);color:#231a00;text-align:center;
  font-family:Verdana,sans-serif;font-size:.8rem;font-weight:bold;
  letter-spacing:.04em;padding:.5rem 1rem}
.state-banner{background:#fff3d6;border:1px solid #d9a72e;border-radius:.5rem;
  padding:.8rem 1rem;margin:1rem 0;font-size:1rem}
.ack{background:#eaf6ec;border:1px solid #9cc7a2;border-radius:.5rem;
  padding:.8rem 1rem;margin:1rem 0}
section{background:var(--paper);border:1px solid var(--line);
  border-radius:.75rem;padding:1.4rem 1.4rem 1.2rem;margin:1.1rem 0}
section.alt{background:var(--tint)}
section.hero{border-top:.45rem solid var(--accent)}
section.hero h2{font-size:1.9rem;line-height:1.2;margin:.2rem 0 .6rem}
h2{font-size:1.35rem;margin:.2rem 0 .5rem;line-height:1.3}
.entry-tag{font-family:Verdana,sans-serif;font-size:.75rem;color:var(--muted);
  text-transform:uppercase;letter-spacing:.08em;margin:0}
.cta-block{margin-top:1rem}
button.cta{display:block;width:100%;background:var(--accent);color:#fff;
  border:0;border-radius:.6rem;padding:.95rem 1rem;font-size:1.05rem;
  font-family:Verdana,sans-serif;font-weight:bold;cursor:pointer}
button.cta:hover{background:var(--accent-dark)}
button.cta[disabled]{background:#9aa3b2;cursor:not-allowed}
p.disclosure{font-size:.95rem;color:var(--muted);margin:.45rem 0 0;
  font-family:Verdana,sans-serif}
ul{padding-left:1.2rem}
ol.reasons{padding-left:1.4rem}
ol.reasons li{margin:.55rem 0}
.spinner{display:inline-block;width:1rem;height:1rem;border:.2rem solid #c8cfdd;
  border-top-color:var(--accent);border-radius:50%;vertical-align:-.15rem;
  margin-right:.5rem;animation:spin 1s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
footer{border-top:1px solid var(--line);margin-top:1.5rem;padding-top:1rem;
  text-align:center}
a.decline{font-family:Verdana,sans-serif;font-size:1rem;color:var(--accent-dark)}
a.decline.disabled{color:var(--muted);pointer-events:none}
a.secondary{font-family:Verdana,sans-serif}
.thanks{text-align:center;padding:2.5rem 1rem}
.thanks a.continue{display:inline-block;background:var(--accent);color:#fff;
  text-decoration:none;border-radius:.6rem;padding:.9rem 1.4rem;
  font-family:Verdana,sans-serif;font-weight:bold}
@media (max-width:640px){
  section{padding:1.1rem 1rem 1rem}
  section.hero h2{font-size:1.55rem}
  button.cta{font-size:1rem;padding:1rem}
  p.disclosure{font-size:.95rem}
}
@media (prefers-reduced-motion: reduce){
  .spinner{animation:none}
  *{transition:none}
}
"""


def esc(text):
    return html.escape(str(text), quote=True)


def load_json(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def page_dir_name(plan, entry_context):
    if plan["instance"] == "upsell_1":
        return "upsell1"
    return "upsell2-" + entry_context.replace("_", "-")


NATIVE_REF_PREFIX = "native-one-click:"
BINDING_REF_PREFIX = "extra-offer-binding:"


def binding_ref_for_copy_ref(copy_ref):
    """The S80-06 binding ref that wraps a copy-layer native ref.

    The copy fixture declares the guarded native action in the
    copy/request-layer form "native-one-click:<offer_id>" (the only form
    the request schema and the copy validator accept); the bundle's CTAs
    bind the extra-offer binding ref for the SAME offer_id. Anything
    that is not the native form has no binding correspondence and is
    refused.
    """
    if not copy_ref.startswith(NATIVE_REF_PREFIX):
        raise SystemExit(
            "copy accept_action_ref %r is not in the native guarded form" % copy_ref
        )
    return BINDING_REF_PREFIX + copy_ref[len(NATIVE_REF_PREFIX):]


def check_copy_agrees_with_bundle(bundle, copy_doc):
    """Fail loudly if the copy fixture diverges from the bundle contract."""
    result = bundle["result"]
    plan = bundle["page_plan"]
    if copy_doc["instance"] != plan["instance"]:
        raise SystemExit("copy instance mismatch for " + plan["page_id"])
    native_ref = copy_doc["accept_action_ref"]
    binding_ref = binding_ref_for_copy_ref(native_ref)
    if plan["action_binding"]["action_ref"] != binding_ref:
        raise SystemExit("bundle action_binding ref mismatch for " + plan["page_id"])
    if plan["action_binding"].get("native_action_ref") != native_ref:
        raise SystemExit("bundle native_action_ref mismatch for " + plan["page_id"])
    cta_by_section = {c["section_number"]: c for c in result["cta_map"]}
    if len(copy_doc["sections"]) != len(cta_by_section):
        raise SystemExit("section count mismatch for " + plan["page_id"])
    for section in copy_doc["sections"]:
        mapped = cta_by_section[section["number"]]
        if section["cta"]["text"] != mapped["cta_text"]:
            raise SystemExit(
                "CTA text mismatch, section %s, %s" % (section["number"], plan["page_id"])
            )
        if section["cta"]["action_ref"] != native_ref:
            raise SystemExit(
                "copy CTA action_ref mismatch, section %s, %s" % (section["number"], plan["page_id"])
            )
        if mapped["action_ref"] != binding_ref:
            raise SystemExit(
                "bundle CTA action_ref mismatch, section %s, %s" % (section["number"], plan["page_id"])
            )


def ack_blocks_for(plan, entry_context):
    blocks = []
    for block in plan.get("acknowledgement_blocks", []):
        if block["condition"] == "verified_original_purchase" or block["condition"] == entry_context:
            blocks.append(block)
    return blocks


def render_cta_block(section, plan, state, primary=False):
    disclosure = plan["disclosure"]["text"]
    action_ref = plan["action_binding"]["action_ref"]
    disabled = state in CTA_DISABLED_STATES
    attrs = ' class="cta%s" data-action-ref="%s" data-native-action-status="%s"' % (
        " primary" if primary else "",
        esc(action_ref),
        esc(plan["action_binding"]["status"]),
    )
    if primary:
        attrs += ' id="primary-cta"'
    if disabled:
        attrs += ' disabled aria-disabled="true"'
    return (
        '<div class="cta-block"><button%s>%s</button>'
        '<p class="disclosure">%s</p></div>'
        % (attrs, esc(section["cta"]["text"]), esc(disclosure))
    )


def render_offer_page(bundle, copy_doc, state):
    result = bundle["result"]
    plan = bundle["page_plan"]
    entry_context = result["eligibility_check"].get("entry_context")
    page_id = plan["page_id"]
    title = "%s - %s (%s)" % (copy_doc["offer_name"], page_id, state)

    out = []
    out.append("<!DOCTYPE html>")
    out.append('<html lang="en">')
    out.append("<head>")
    out.append('<meta charset="utf-8">')
    out.append('<meta name="viewport" content="width=device-width, initial-scale=1">')
    out.append("<title>%s</title>" % esc(title))
    out.append("<style>%s</style>" % CSS)
    out.append("</head>")
    out.append("<body>")
    out.append(
        '<div class="test-banner">TEST ONLY - local rendered proof (L2). '
        "The accept buttons bind through the S80-06 extra-offer binding, "
        "interface-conformant with the S79/S06 draft interface; native "
        "install is pending S06 confirmation, no live native action exists "
        "yet, and this page cannot charge anything.</div>"
    )
    out.append("<main>")
    if state in STATE_BANNERS:
        spinner = '<span class="spinner" aria-hidden="true"></span>' if state == "processing" else ""
        out.append(
            '<div class="state-banner" data-state="%s" role="status">%s%s</div>'
            % (state, spinner, esc(STATE_BANNERS[state]))
        )
    for block in ack_blocks_for(plan, entry_context):
        out.append(
            '<div class="ack" data-ack-condition="%s">%s</div>'
            % (esc(block["condition"]), esc(block["text"]))
        )
    for section in copy_doc["sections"]:
        number = section["number"]
        classes = []
        if number == 1:
            classes.append("hero")
        if number % 2 == 0:
            classes.append("alt")
        out.append(
            '<section data-section-number="%d" data-section-key="%s" class="%s">'
            % (number, esc(section["key"]), " ".join(classes))
        )
        out.append('<p class="entry-tag">Optional extra - step %d of 8</p>' % number)
        out.append("<h2>%s</h2>" % esc(section["heading"]))
        out.append("<p>%s</p>" % esc(section["body"]))
        if section.get("bullets"):
            out.append("<ul>")
            for bullet in section["bullets"]:
                out.append("<li>%s</li>" % esc(bullet))
            out.append("</ul>")
        if section.get("reasons"):
            out.append('<ol class="reasons">')
            for reason in section["reasons"]:
                out.append("<li>%s</li>" % esc(reason))
            out.append("</ol>")
        out.append(render_cta_block(section, plan, state, primary=(number == 1)))
        out.append("</section>")
    decline = plan["states"]["decline"]
    decline_disabled = ' class="decline disabled" aria-disabled="true"' if state == "processing" else ' class="decline"'
    out.append("<footer>")
    out.append(
        '<a%s href="#route-%s" data-decline-route="%s" data-charges="false">'
        "No thanks - continue without this extra</a>"
        % (decline_disabled, esc(decline["target_page_id"]), esc(decline["target_page_id"]))
    )
    out.append(
        '<p class="disclosure">Choosing no thanks never charges you. '
        "Your original purchase stays complete either way.</p>"
    )
    out.append("</footer>")
    out.append("</main>")
    out.append("</body>")
    out.append("</html>")
    return "\n".join(out) + "\n"


def render_suppressed_page(bundle, copy_doc):
    plan = bundle["page_plan"]
    page_id = plan["page_id"]
    # Route to the final thank-you role. The U2 bundles name the thank-you
    # page id in their decline/success routes; the U1 bundle names no
    # thank-you page id, so for U1 the target stays the bare role marker
    # instead of an invented page id (recorded in BUILD-NOTES-PAGES.md).
    thanks_id = None
    for route in (plan["states"]["decline"], plan["success_route"]):
        if route.get("target_role") == "thank_you":
            thanks_id = route["target_page_id"]
            break
    if thanks_id:
        href = "#route-" + thanks_id
        route_attrs = ' data-safe-route="%s" data-safe-route-role="thank_you"' % esc(thanks_id)
    else:
        href = "#safe-final-thank-you"
        route_attrs = ' data-safe-route-role="thank_you"'
    title = "%s - %s (suppressed: already owned)" % (copy_doc["offer_name"], page_id)
    out = []
    out.append("<!DOCTYPE html>")
    out.append('<html lang="en">')
    out.append("<head>")
    out.append('<meta charset="utf-8">')
    out.append('<meta name="viewport" content="width=device-width, initial-scale=1">')
    out.append("<title>%s</title>" % esc(title))
    out.append("<style>%s</style>" % CSS)
    out.append("</head>")
    out.append("<body>")
    out.append('<div class="test-banner">TEST ONLY - local rendered proof (L2).</div>')
    out.append("<main>")
    out.append('<div class="thanks" data-state="suppressed">')
    out.append("<h2>You already have this covered</h2>")
    out.append(
        "<p>Our records show this extra is already part of what you own, or "
        "is not compatible with your purchase, so there is nothing to add "
        "here. You have not been charged, and you will never be charged "
        "twice for the same extra.</p>"
    )
    out.append(
        '<a class="continue" href="%s"%s>Continue to your confirmation</a>' % (href, route_attrs)
    )
    out.append("</div>")
    out.append("</main>")
    out.append("</body>")
    out.append("</html>")
    return "\n".join(out) + "\n"


def render_index(manifest_pages):
    out = []
    out.append("<!DOCTYPE html>")
    out.append('<html lang="en">')
    out.append("<head>")
    out.append('<meta charset="utf-8">')
    out.append('<meta name="viewport" content="width=device-width, initial-scale=1">')
    out.append("<title>S80-08 local renders - index</title>")
    out.append("<style>%s</style>" % CSS)
    out.append("</head>")
    out.append("<body>")
    out.append('<div class="test-banner">TEST ONLY - local rendered proof (L2).</div>')
    out.append("<main>")
    out.append("<h2>S80-08 local page renders</h2>")
    out.append(
        "<p>Static renders generated by render_pages.py from the S80 adapter "
        "bundles and copy fixtures. The S80-06 extra-offer binding is "
        "interface-conformant at fixture level; native install is pending "
        "S06 confirmation and nothing here can charge anything.</p>"
    )
    for page in manifest_pages:
        out.append("<h3>%s (%s)</h3>" % (esc(page["page_id"]), esc(page["directory"])))
        out.append("<ul>")
        for state in page["states"]:
            out.append(
                '<li><a href="%s/%s.html">%s</a></li>' % (esc(page["directory"]), state, state)
            )
        out.append("</ul>")
    out.append("</main>")
    out.append("</body>")
    out.append("</html>")
    return "\n".join(out) + "\n"


def main():
    manifest_pages = []
    written = []
    for bundle_name in BUNDLE_FILES:
        bundle = load_json(ADAPTER_FIXTURES / bundle_name)
        result = bundle["result"]
        plan = bundle["page_plan"]
        copy_rel = result["artifacts"][0]["path"]
        copy_doc = load_json(WORK_DIR / copy_rel)
        check_copy_agrees_with_bundle(bundle, copy_doc)
        entry_context = result["eligibility_check"].get("entry_context")
        directory = page_dir_name(plan, entry_context)
        page_out = PAGES_DIR / directory
        page_out.mkdir(parents=True, exist_ok=True)
        for state in STATES:
            if state == "suppressed":
                content = render_suppressed_page(bundle, copy_doc)
            else:
                content = render_offer_page(bundle, copy_doc, state)
            target = page_out / (state + ".html")
            target.write_text(content, encoding="utf-8")
            written.append(target)
        manifest_pages.append(
            {
                "page_id": plan["page_id"],
                "instance": plan["instance"],
                "entry_context": entry_context,
                "directory": directory,
                "bundle_file": "adapters/fixtures/" + bundle_name,
                "copy_file": copy_rel,
                "action_ref": plan["action_binding"]["action_ref"],
                "states": STATES,
            }
        )
    index_path = PAGES_DIR / "index.html"
    index_path.write_text(render_index(manifest_pages), encoding="utf-8")
    written.append(index_path)
    manifest = {"pages": manifest_pages}
    manifest_path = PAGES_DIR / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    written.append(manifest_path)
    for path in written:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        print("%s  %s" % (digest, path.relative_to(PAGES_DIR)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
