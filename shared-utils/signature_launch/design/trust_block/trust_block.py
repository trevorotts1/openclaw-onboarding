"""Trust/proof block: render only supplied, substantiated proof.

Owner: S71. Implements doc 16 section 1 ("Trust/proof block ... Only
supplied substantiated proof") and the doc 16 section 8 automatic
failure "invented proof/scarcity", with doc 18 section 6: missing proof
does not become a fabricated testimonial.

Rules:

- Proof is data supplied by the launch: testimonials (quote +
  attribution), credentials (label + optional detail) and counts
  (value + label). Every item MUST carry a ``source_ref`` naming where
  the proof is substantiated. An item without a source_ref is excluded
  and counted in the result's ``excluded_unsubstantiated`` tally.
- When no substantiated item remains (including proof=None), the block
  renders its absent state: the section shell with
  ``data-state="absent"`` and NO testimonial, credential or count
  markup at all. Absence is honest; nothing is fabricated to fill it.
- All interpolated text is HTML-escaped (doc 16 section 6).

Deterministic, standard library only; rendering is a pure function.
"""

import html

COMPONENT_NAME = "trust-proof-block"
COMPONENT_VERSION = "1.0.0"
COMPONENT_OWNER = "S71"


def _esc(value):
    return html.escape(str(value), quote=True)


def _substantiated(items):
    kept, excluded = [], 0
    for item in items or []:
        if item.get("source_ref"):
            kept.append(item)
        else:
            excluded += 1
    return kept, excluded


def render_trust_block(proof, tokens=None):
    """Render the trust/proof block for a proof dict (or None).

    Returns a dict: {"html": str, "state": "present"|"absent",
    "rendered": {"testimonials": n, "credentials": n, "counts": n},
    "excluded_unsubstantiated": n}.

    proof shape:
      {"testimonials": [{"quote", "attribution", "source_ref"}],
       "credentials":  [{"label", "detail"?, "source_ref"}],
       "counts":       [{"value", "label", "source_ref"}]}

    ``tokens`` is accepted for call-site symmetry with the other design
    components; branding reaches the block through the --sl-* CSS
    variables and design.css, so the markup carries no brand values.
    """
    proof = proof or {}
    testimonials, ex_t = _substantiated(proof.get("testimonials"))
    credentials, ex_c = _substantiated(proof.get("credentials"))
    counts, ex_n = _substantiated(proof.get("counts"))
    excluded = ex_t + ex_c + ex_n
    rendered = {
        "testimonials": len(testimonials),
        "credentials": len(credentials),
        "counts": len(counts),
    }

    if not (testimonials or credentials or counts):
        return {
            "html": '<section class="sl-trust" data-state="absent"></section>\n',
            "state": "absent",
            "rendered": rendered,
            "excluded_unsubstantiated": excluded,
        }

    parts = ['<section class="sl-trust" data-state="present">']
    for item in testimonials:
        parts.append('  <figure class="sl-trust-testimonial">')
        parts.append(
            '    <blockquote>%s</blockquote>' % _esc(item.get("quote", ""))
        )
        parts.append(
            '    <figcaption>%s</figcaption>' % _esc(item.get("attribution", ""))
        )
        parts.append("  </figure>")
    for item in counts:
        parts.append('  <div class="sl-trust-count">')
        parts.append(
            '    <span class="sl-trust-count-value">%s</span>' % _esc(item.get("value", ""))
        )
        parts.append(
            '    <span class="sl-trust-count-label">%s</span>' % _esc(item.get("label", ""))
        )
        parts.append("  </div>")
    for item in credentials:
        detail = item.get("detail")
        detail_html = ""
        if detail:
            detail_html = ' <span class="sl-trust-credential-detail">%s</span>' % _esc(detail)
        parts.append(
            '  <div class="sl-trust-credential">%s%s</div>'
            % (_esc(item.get("label", "")), detail_html)
        )
    parts.append("</section>")
    return {
        "html": "\n".join(parts) + "\n",
        "state": "present",
        "rendered": rendered,
        "excluded_unsubstantiated": excluded,
    }
