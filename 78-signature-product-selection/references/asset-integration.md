# Skill 78 visual and asset integration (S78-07)

## Position

A selection page's job is comprehension (doc 16 section 5). Decoration never
hides price, exclusions, or the continue action, and no animation may shift
the selection controls.

Every package card carries one image plate (slot `PKG-n`, in card order): the
client's supplied package or product image, or one generated image when no
image was supplied. The wireframes and mockups are made through Skill 71's
shared image service (`scripts/run_image_stages.py`), and the page's Design
Board is built from these plates, so its image grid is never empty. A plate is
a labelled placeholder in the wireframe and a real image in the mockup; it
never hides price, exclusions or the Choose button.

## Where the images come from

Examples: an approved product visualization supplied by the client, or one
generated image per offer.

Rules, all inherited and none forked here:

- Generate only through the shared provider adapter resolved from the
  approved launch preference (KIE or Agnes; S63 and Skills 66/74 own policy
  and transport). This skill contains no provider client and hardcodes no
  model.
- One asset, one complete prompt, one provenance record per doc 02
  section 10: requested and actual provider and model, mode, provider
  receipt identifiers actually returned (a KIE task ID only when the KIE
  path returned one; never fabricate one for a synchronous Agnes result),
  result hash and dimensions, budget decision, output path, prompt hash,
  and independent visual QC.
- Real identity assets (founder portraits, logos) come from the brand file
  only. Missing assets stay missing; no lookalikes are invented.
- Generated media destined for a live site is uploaded to the client's GHL
  media library in a folder named for that site, per the owner's standing
  media workflow, and the CDN URL is what the page embeds. S06 performs the
  upload through its rail; S78 records the returned URL in the asset list.
- A changed image filename does not reopen approved copy or strategy; a
  changed offer fact reopens copy, layout, and price checks (doc 16
  section 4).

## Asset list shape (page result attachment)

This shape is for media assets attached to a page result, and is distinct
from the plan's asset_list, which carries the launch catalog's asset
descriptors (name and owner, the packet launch contract shape;
build_selection_plan.py rejects a descriptor missing its owner).

Each media entry: asset_id, role (for example offer_visual), source_kind
(client_supplied | generated | brand_library), provenance_ref, url_or_path,
alt_text, and qc_receipt_ref. An entry without provenance does not ship.
