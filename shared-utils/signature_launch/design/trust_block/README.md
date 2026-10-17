# Trust/proof block

**Component:** `trust-proof-block` v1.0.0 · **Owner:** S71 · **Implements:** doc 16 §1 (component inventory, "Trust/proof block — only supplied substantiated proof"), doc 16 §8 (automatic failure: invented proof) and doc 18 §6 (missing proof does not become a fabricated testimonial).

## Purpose

Render the proof a launch actually has — testimonials, credentials,
counts — and render nothing invented when it has none.

## Inputs

`render_trust_block(proof, tokens=None)` where `proof` is launch data:

```json
{
  "testimonials": [{"quote": "...", "attribution": "...", "source_ref": "..."}],
  "credentials":  [{"label": "...", "detail": "...", "source_ref": "..."}],
  "counts":       [{"value": "...", "label": "...", "source_ref": "..."}]
}
```

Every item must carry a `source_ref` naming where the claim is
substantiated. `tokens` is accepted for call-site symmetry; branding
arrives via the `--sl-*` CSS variables and `../../design.css`.

## Outputs

A dict `{html, state, rendered, excluded_unsubstantiated}`:

- `state: "present"` — at least one substantiated item was rendered.
- `state: "absent"` — no substantiated item exists. The HTML is the
  empty section shell with `data-state="absent"` and **no testimonial,
  credential or count markup at all**. The absent state is the honest
  rendering of missing proof; the component never fabricates a
  testimonial, credential or count to fill the space.
- Items without a `source_ref` are excluded from rendering and counted
  in `excluded_unsubstantiated`, so a page build can see that proof was
  dropped for lack of substantiation instead of silently vanishing.

All interpolated text is HTML-escaped (doc 16 §6).

## Tests

`tests/test_trust_block.py` (stdlib unittest): absent/None proof and
proof whose items all lack `source_ref` render the absent state with
zero testimonial markup; supplied substantiated proof renders with its
quote, attribution, counts and credentials; unsubstantiated items are
excluded and tallied; quotes are escaped.
