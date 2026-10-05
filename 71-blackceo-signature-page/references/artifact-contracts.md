# Artifact Contracts

These are private production contracts for deterministic scripts and handoffs. They do not replace the detailed SOP.

## Recommended project output tree

```text
project/
  private/
    workflow-state.json
    internal-copy.md
    copy-manifest.json
    page-visual-bible.md
    image-map.json
    qc/
  public/
    public-copy.md
    html/
  wireframes/
    desktop/
    mobile/
  mockups/
    desktop/
    mobile/
  images/
    prompts/
    generated/
  review/
    desktop-wireframes.pdf
    mobile-wireframes.pdf
    desktop-mockups.pdf
    mobile-mockups.pdf
```

## Workflow-state JSON

Use the exact ordered stage IDs defined in `references/stage-contract.json` (enforced by `scripts/stage_gate.py`).

```json
{
  "workflow_id": "client-page-001",
  "page_version": "standard",
  "current_stage": "copy",
  "stages": {
    "intake": {"status": "ready", "attempts": 0},
    "copy": {"status": "working", "attempts": 0},
    "font-action-plan": {"status": "blocked", "attempts": 0},
    "desktop-wireframe": {"status": "blocked", "attempts": 0},
    "mobile-tablet": {"status": "blocked", "attempts": 0},
    "visual-mockup": {"status": "blocked", "attempts": 0},
    "image-inventory-prompts": {"status": "blocked", "attempts": 0},
    "image-generation-qc": {"status": "blocked", "attempts": 0},
    "image-map-upload": {"status": "blocked", "attempts": 0},
    "final-mockups": {"status": "blocked", "attempts": 0},
    "responsive-html": {"status": "blocked", "attempts": 0},
    "ghl-install-test": {"status": "blocked", "attempts": 0},
    "publish-verify": {"status": "blocked", "attempts": 0}
  }
}
```

`attempts` counts focused repair attempts after failure. Valid range is 0-3.

## Image-map JSON

Each image entry is one intended generated master asset. Crops/exports can point to a `master_id` rather than pretending to be separately generated images.

```json
{
  "images": [
    {
      "id": "IMG-001",
      "source_passage": "Hero promise and opening emotional beat",
      "job": "Hero authority and aspiration",
      "scene": "Specific visual scene description",
      "people": "Black woman entrepreneur, fictional",
      "shot_plan": "Three-quarter environmental portrait, subject right third",
      "style_grade": "Selected page Art Direction plus compatible Secret Sauce",
      "text_mode": "no-generated-text",
      "references": [],
      "technical_plan": "Engine-supported wide landscape master",
      "prompt_file": "prompts/IMG-001.md",
      "asset_file": "generated/IMG-001.png",
      "filename": "IMG-001.png",
      "status": "ready"
    }
  ]
}
```

Required fields are validated by `scripts/validate_image_manifest.py`.

## Review-PDF manifest

The manifest is the authority for page order. Do not rely on lexicographic filename sorting.

```json
{
  "category": "desktop-wireframes",
  "output": "desktop-wireframes.pdf",
  "pages": [
    {"path": "../wireframes/desktop/part-01.png", "label": "Part 01"},
    {"path": "../wireframes/desktop/part-02.png", "label": "Part 02"}
  ]
}
```

Allowed categories:

- `desktop-wireframes`
- `mobile-wireframes`
- `desktop-mockups`
- `mobile-mockups`

`combine_review_pdf.py` writes the PDF plus an adjacent JSON receipt containing page order and SHA-256 hashes. `validate_review_pdf.py` checks the expected page count and receipt.
