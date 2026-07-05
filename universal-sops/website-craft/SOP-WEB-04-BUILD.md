# SOP-WEB-04: BUILD THE WEBSITE (DELEGATED TO SKILL 6)

**Cluster:** Website-Craft Rules (`universal-sops/website-craft/`)
**Owning role:** Web-Development (build) — Conversion Copywriter's APPROVED copy is the input
**Stage:** P3-BUILD
**Delivery rail:** `06-ghl-install-pages` — the ONE way in

---

## 0. WHY THIS SOP EXISTS

The website is built through the SAME delivery rail as every funnel/page: the Skill 6 dispatcher. This
cluster never writes local HTML as the deliverable and never hand-rolls GHL REST calls — those are the
ungoverned paths.

## 1. THE COPY DEPENDENCY IS ALREADY ENFORCED (FIX-COPY-01)

For a standalone "write it for me" website, the Skill 6 dispatcher (`v2_dispatcher._run_intake` →
`_open_copy_dependency`) has ALREADY opened the P2-COPY mini-epic and is holding the build
`waiting_on_dependency` until an APPROVED `copy.md` / `website_copy_ledger.json` exists. This SOP's
copy contract (SOP-WEB-02) is exactly what clears that hold. Do NOT bypass it by feeding the builder
inline copy.

## 2. FEED APPROVED COPY TO THE BUILDER

Pass the APPROVED `website_copy_ledger.json` as the page copy source. The Skill 6 builder consumes it
per page section — it does not re-author copy. The build's own gates (sub-account hard gate, telemetry
scrub, the sealed `ghl_verify` render check, the rendered-`<img>` gate) apply unchanged.

## 3. VERIFY

The build reaches `verified` only through the sealed Skill 6 verifier. The website copy floors were
already proven at P1-COPY (`prove_web_pages.py`); the build verifier proves the pages actually rendered
with their images. Both must pass before P4-CERTIFY.
