# Skill 39 — Real Estate Playbook: design rules (canonical deep reference)

> **This file is the CANONICAL, FULL text of Skill 39's design rules.**
> It is a Teach-Yourself-Protocol DEEP FILE and is **never** pasted into a box's
> `MEMORY.md`. `scripts/08-update-core-files.sh` writes exactly ONE compact
> pointer block into `MEMORY.md` (marker `<!-- BEGIN skill-39 memory-rules -->`)
> that points here.
>
> **Why:** core bootstrap files are re-billed to the model on every single turn,
> so rule corpora live in deep files and core files carry pointers only (TYP).
> Per-rule enforcement detail lives in `protocols/*.md` and `references/*.md`.

---

## Real-estate design rules

1. **No-Fabrication Rule** — never invent an address, price, sqft, comp, owner, or
   photo. No provider / no match → honest gap + the operator-supplied-key path.
   Mark operator-provided figures `source: operator`.
   See `references/property-providers.md`, `references/provider-status-contract.md`.
2. **Fair-Housing Rule** — never ask about or steer by protected class in
   qualification or routing.
   See `references/fair-housing-guardrails.md`, `scripts/qc-fair-housing.sh`.
3. **Disclosure-Pointer Rule** — disclosure compliance is a POINTER matrix, not
   legal advice; the disclosure decision escalates to the licensed agent/broker.
   See `protocols/disclosure-compliance-protocol.md`,
   `protocols/state-disclosure-compliance-protocol.md`,
   `references/state-disclosure-matrix.md`.
4. **CMA-Anchor Rule** — never reveal a price before the CMA walk-through; anchor
   on verified comps, not the seller's hoped list price.
   See `protocols/seller-qualification-protocol.md`.
5. **Pre-Foreclosure Care Rule** — distressed-owner outreach is empathetic and
   options-focused, never predatory; honor do-not-contact + state cooling-off
   rules. See `protocols/pre-foreclosure-outreach-protocol.md`.
6. **Event-Log Rule** — every RE action appends one line to
   `real-estate-events.jsonl` (field names + counts, never raw PII).
   See `references/master-files-event-contract-F52.md`.
7. **Skill-38-Additive Rule** — the RE Sales-Brain layer is an additive drop-in;
   never overwrite Skill 38's own protocol.
   See `references/sales-brain-real-estate-extension.md`.
