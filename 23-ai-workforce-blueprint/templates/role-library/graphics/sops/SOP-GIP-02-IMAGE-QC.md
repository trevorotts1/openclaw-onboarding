# SOP-GIP-02 — Generated-Image QC (BINDING)

**ID:** SOP-GIP-02
**Classification:** ZHC SOP — Graphics Image Protocol (GIP)
**Owner Role:** QC Specialist (Graphics) — independent reviewer
**Version:** 1.0 | **Date:** 2026-07-10
**Status:** CANONICAL
**Library-version pin:** MODEL-SPECS v1.4, TEST-PROTOCOL v1.0 (§-refs verified 2026-07-10)

---

## Why this exists

The Graphics department had no mechanical per-deliverable image QC: the style-card fidelity gate
(`TEST-PROTOCOL.md`, average ≥ 4.0/5) is explicitly **"Style-card fidelity ONLY — NOT the QC for a
deliverable"** (`TEST-PROTOCOL.md:5`), the Gate-2 review carried no numeric threshold / no mandated
vision pass / no auto-fail battery / no provenance log, and social graphics sampled only 10% (diagnosis
G2). This SOP adopts the Presentations image-QC mechanics wholesale, adapted to graphics AF-G* codes.

**SCOPE:** every AI-generated image leaving this department for ANY external surface (client deliverable,
social post, ad, email, funnel, print). **100% coverage for external assets** — the 10% sampling rule
survives ONLY for internal drafts.

---

## Procedure

1. **MANDATORY VISION READ.** Open every candidate PNG/JPG with a real multimodal vision pass (primary:
   `qwen3-vl:235b-cloud` or the client's own vision-capable provider; **NEVER the model that produced or
   prompted the image** — QC independence). A report graded from filenames, prompt text, or a self-typed
   number is REFUSED (**AF-G-VISION**). Every asset carries a non-null `vision_api_response` record in
   `<job>/qc/vision_qc_log.json`.

2. **AUTO-FAIL BATTERY FIRST** (any hit = FAIL regardless of average):
   - **AF-G1** garbled/misspelled baked text (pixel-vs-copy parity against the brief's verbatim strings)
   - **AF-G2** logo mutated / recolored / invented mark (compare against the LOGO reference)
   - **AF-G3** legibility/contrast failure on any key text element
   - **AF-G4** anatomical artifact (fingers, limbs, face geometry)
   - **AF-G5** placeholder/bracket token rendered as visible text
   - **AF-G6** brand-palette drift beyond the style card's stated tolerances
   - **AF-G7** demographic default / mono-cast / skin-tone fidelity failure
   - **AF-G8** provenance gap: no Kie.ai taskId + receipt in `_vault/receipts/` tying pixels to the
     sanctioned pipeline (the graphics analogue of AF-CANONICAL-RENDER-BYPASS)

3. **SCORE 1–10** on: brief fidelity, composition, style-card/brand fidelity, technical quality
   (resolution/format/aspect), surface-fitness (platform safe areas). **PASS = average ≥ 8.5, zero
   auto-fails.** Write `<job>/qc/image_qc_report.json` — the SAME shape Presentations uses, so downstream
   gates and `graphics_ghl_push.py` share code. Each asset record carries at minimum:
   `{local_path, asset_id, average, pass, triggered_autofails}`; `pass:true` + empty `triggered_autofails`
   is the ONLY combination `graphics_ghl_push.py` will host.

4. **FAIL** loops back to the producing role with the specific AF-G codes; **3 consecutive fails** on the
   same defect = escalate to the Chief Design Officer (mirrors the DIU 3-strike law, `diu_validator.py
   fidelity`).

---

## Interaction with the fidelity gate and social graphics

- `TEST-PROTOCOL.md` fidelity (≥ 4.0/5) remains the **style-card** promotion gate; SOP-GIP-02 is the
  **deliverable** gate. Both may apply to one asset — fidelity says the card renders on style; SOP-GIP-02
  says this specific external asset is shippable.
- External social posts authored by the Graphics department run 100% SOP-GIP-02 (the 10% sample survives
  only for internal drafts). **Skill 57 media-core output is governed by Skill 57's own fail-closed
  provers (Gemini 4-grid judge + SeedDream repair); graphics-department-authored social assets are
  governed by this SOP.** (Respects the ratified 2026-07-03 decision to hold Skill-57 rollout changes.)

**Gate:** the QC report `<job>/qc/image_qc_report.json` (with per-asset `pass`/`triggered_autofails`) is
the machine input to the finished-asset GHL delivery gate (`graphics_ghl_push.py --gate`, SOP-GIP-03) and
to the board's IMAGE-QC activity (`gr_board.py`, SOP 9.12).
