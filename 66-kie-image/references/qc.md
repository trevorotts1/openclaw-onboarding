# KIE Image — Real Image Quality Control (QC)

Authority: Spec 7.6 (KIE Image QC), Spec 15 (Controlled Retry/Fallback Ladder).

A successful createTask and even a `state == "success"` record only proves the
provider delivered bytes. Production release requires ACTUAL visual inspection
of the image asset — using the system's visual capability, never a filename or a
200 OK.

---

## 1. Confirmation checklist (before any QC)

- [ ] Task reached `state == "success"` via recordInfo or callback (never assume
      from createTask 200 — "A 200 OK response only means the task was
      successfully created").
- [ ] `resultJson.resultUrls` present and non-empty; URLs expire ~24h —
      download/persist immediately when the workflow needs long-term access
      (provider deletes media after 14 days).
- [ ] `failCode`/`failMsg` empty; `creditsConsumed` recorded for audit.
- [ ] Persist final media into durable storage when required.

## 2. Visual QC — actual image inspection

Inspect the downloaded full-resolution asset:

1. **Dimensions vs requested.**
   - GPT Image 2: 1:1 cannot convert to 4K; `auto` ratio yields 1K only; at
     2K/4K the ratios **5:4, 4:5, 3:1, 1:3, 9:21** are excluded — if the
     returned image is one of those ratios at 2K/4K, the route silently bent
     the request. Verify against the requested resolution enum (1K/2K/4K.
   - Seedream: Basic/High/Ultra maps to resolution tiers (Pro Basic=1K,
     High=2K; Lite Basic=2K/High=3K/Ultra=4K; 4.5 Basic=2K/High=4K). Confirm
     the returned size matches the tier that was requested.
   - Wan: min 240 px applies to INPUT refs; outputs follow requested enum.
2. **Reference fidelity.** For every attached reference: subject identity,
   faces, clothing, product geometry, colors. For logo/brand work: exact
   geometry preserved from the reference.
3. **Edit preservation.** What was asked to stay identical (composition,
   camera angle, background, non-edited areas) is identical; what was asked to
   change changed.
4. **Colors, lighting, typography.** Palette/grade/lit match directives; any
   requested text/lettering spelled correctly and legible.
5. **Anatomy/artifacts.** Subject count matches prompt; faces, hands, limbs
   correct; no synthetic watermarks, seam lines, boundary distortion, or
   duplication artifacts.
6. **Subject identity/count.** Multi-image requests (Wan `n` 1–4; gallery up to
   12 where "the actual value is determined by the model") — verify count
   matches what was returned and the brief.
7. **Ratio/geometry compliance** per family enum (e.g. Z-Image `1:1, 4:3, 3:4,
   16:9, 9:16` — no 21:9; NB2 supports 1:4/4:1/1:8/8:1, NB Pro does NOT).

## 3. Mandatory directive/route compliance checks

- **Logo I2I rule.** When a prompt involves a client's logo, wordmark, brand
  mark, monogram, or any existing brand image, generation MUST be image-to-image
  with the logo passed as a reference (`input_urls`/`image_urls`/`image_input`
  per family). A text-to-image model cannot render a specific client's logo
  accurately and will invent a lookalike. QC verifies I2I was actually used.
- **Style-reference-only directive.** Whenever any reference image is attached
  for STYLE guidance, the prompt MUST carry: "Use the attached images only as
  style reference for color grading, lighting, and composition -- do not copy
  their subjects, faces, or text." Verify presence in the dispatched prompt.
- **No invented support.** Z-Image is T2I-only; Ideogram v3-edit uses a mask,
  v3-remix uses strength — never treat these as generic multi-reference
  composition; Imagen 4 has no reference route.

## 4. Controlled retry ladder (spec 15) — five steps, never silent

1. **Same model, corrected prompt/parameters.** Fix what QC found (lighting
   phrasing, composition, negative constraints, ratio/resolution typo) and
   re-dispatch.
2. **Same model, alternate valid mode/reference encoding.** E.g. switch ref
   encoding (URL vs data URI), crop/normalize a ref to legal format, change
   aspect ratio to a supported enum value, or route i2i on the same family.
3. **Another compatible model in the SAME provider** — only if model selection
   was automatic or the user permits it. e.g. GPT Image 2 -> Nano Banana Pro;
   Seedream 5.0 Pro -> Seedream 5.0 Lite. Record the switch.
4. **Another provider** — only when generic provider routing is allowed or the
   user approves.
5. **Stop after the configured retry cap and report why.** Never silently burn
   credits across multiple models. After 3 failed attempts (or the task's
   configured cap), stop, log exact failure symptoms (failCode/failMsg,
   inspected defects), and escalate to the operator.

Every retry step: change nothing else, record the step number, and re-run the
full visual QC after each generation.
