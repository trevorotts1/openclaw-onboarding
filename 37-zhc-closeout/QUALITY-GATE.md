# Skill 37 - The 8.5 Quality Gate (MANDATORY)

This is a systemic, non-optional requirement on EVERY ZHC closeout. No closeout
artifact may be delivered to a client until the running agent has RATED it 1-10
and it scores at least **8.5**. The agent both RATES and QCs every deliverable.

This applies to all four closeout artifact classes:

1. Workforce org chart (Infographic #1 - Workforce Structure)
2. How-Work-Flows diagram (Infographic #2)
3. The Notion closeout doc / page tree (all 9 doctrine sections)
4. Any other closeout doc shipped to the client

If an artifact scores below 8.5, the agent MUST iterate and re-rate until it
reaches 8.5 or higher BEFORE delivery:

- Charts: edit the HTML / CSS and re-render (org chart is deterministic
  HTML + Playwright, so this is fully controllable).
- AI images (flow diagram): re-prompt, or switch model, then re-generate.
- Docs: rewrite the weak sections, fill missing content, re-rate.

Below 8.5 is never shipped. Iterate, do not ship subpar.

---

## Per-Artifact Workflow (apply to EACH artifact)

```
generate artifact
   |
   v
self-rate 1-10 against the rubric below
   |
   v
run the QC checks for that artifact class
   |
   +--> score < 8.5  OR  any QC check fails ?
   |        |
   |        v
   |     iterate / regenerate (edit HTML+CSS for charts,
   |     re-prompt or switch model for AI images,
   |     rewrite for docs) -> re-rate -> re-QC
   |        |
   |        +--> (loop, up to ZHC_QUALITY_MAX_ATTEMPTS, default 3)
   |
   v
score >= 8.5  AND  all QC checks pass
   |
   v
DELIVER to client (Telegram + media library + GHL + Drive)
```

If after the max attempts (default 3) the artifact still cannot reach 8.5,
**HOLD that artifact** (do NOT deliver it), flag for human review via the
operator escalation path, and record the held artifact in state. Never ship
something below the gate just to "finish" the closeout.

`ZHC_QUALITY_MIN` (default `8.5`) sets the bar. `ZHC_QUALITY_MAX_ATTEMPTS`
(default `3`) caps the regenerate loop.

---

## Org Chart rubric (>= 8.5 requires ALL of the following)

- **Visible connector lines showing the reporting hierarchy.** Owner -> CEO
  agent -> branch lines to cluster headers -> lines down to department boxes.
  It must read as a TRUE org chart (a reporting tree), NOT a grid of category
  cards. **This is the #1 failure mode.** The old cluster-card layout, with a
  floating CEO node and no connectors, scores about 6. If you cannot trace a
  line from the Owner all the way down to each department, it is below 8.5.
- Every department is labeled and legible.
- Role counts are visible as legible pills / badges.
- Correct branding: company name, owner name, CEO agent name, brand colors,
  monogram, and the "Built by BlackCEO" footer.
- Fills the canvas with no overflow and no large dead space. Dense clusters of
  7+ departments must still fit (use the verydense sizing path).
- Rendered deterministically via HTML / Playwright, NOT AI image generation
  (AI cannot reliably render org-chart text).

## Flow Diagram rubric (>= 8.5 requires)

- **Industry-specific imagery** tied to what the client actually does, NOT
  generic. A grant firm shows funding / approved-grant motifs; a coaching firm
  shows growth / coaching motifs.
- A clear 5-step progression, numbered, left-to-right.
- Correct iconography. The final "delivered" step is a finished / approved
  deliverable for THAT business, never a generic gift box.
- Brand colors, logo lockup, tagline, and "Built by BlackCEO".
- Clean, legible text and a full-canvas composition.

## Docs rubric (>= 8.5 requires)

- All 9 doctrine sections present (per the ZHC closeout doctrine): What Is a
  ZHC, What Is a ZH Workforce, Workforce Structure (with Infographic #1), How
  Work Runs (with Infographic #2), Departments & Roles (with per-department
  subpages), Communication Hierarchy, Six Sigma DMAIC, Book-to-Persona, and
  First 7 Days.
- Every canonical department AND every client custom department is
  represented in the Departments & Roles section (cross-checked against
  the client's departments.json / build-state canonicalReconciliation --
  no canonical dept silently missing from the closeout doc).
- Real client-specific content throughout. NO placeholders, TODOs, lorem, or
  generic boilerplate.
- The Six Sigma section is DMAIC applied to the client's SPECIFIC departments
  and metrics, not generic quality copy.
- The Book-to-Persona section explains the scoring / decision matrix.
- Professional writing in the client's brand voice.
- Embedded infographics render and all links resolve.

---

## Where the gate runs

- `scripts/run-closeout.sh` enforces a RATE + QC + GATE step after each
  artifact is generated and BEFORE any client delivery. It loops the generator
  up to `ZHC_QUALITY_MAX_ATTEMPTS` times until the artifact clears
  `ZHC_QUALITY_MIN`, then HOLDS (does not deliver) anything that cannot pass.
- `scripts/generate-infographics.sh` carries the same gate inline for the org
  chart and flow diagram so a standalone regeneration is also rated and QC'd.

The agent is the rater. Rate honestly against the rubric above, write the score
and a one-line justification to the closeout log, and only let an artifact reach
the client when it is genuinely 8.5 or better.
