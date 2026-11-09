# Upsell Page Layout - Wireframes and Mockups (Skill 80)

Status: build candidate. Structure only. The sheet language and the colors are Skill 71's: every wireframe and mockup is drawn in the client's own brand colors, never in grey line work. The client's brand colors, the Design Board and design style A, B or C still govern; this file only names the bands. The machine form of this page is `71-blackceo-signature-page/references/page-structures.json`, block `layouts`, entries `upsell_1` and `upsell_2`; the wireframe lines are in `71-blackceo-signature-page/references/wireframe-build-spec.json` under `page_type_blocks.upsell` (one LAYOUT TAG line per section). This file is the plain description of the same bands.

## The page in one view

Eight bands, one per numbered section, never merged. Every band ends in the same call-to-action stack: the button, the exact terms line, the plain decline link. The first screen tells the visitor their original order is confirmed and safe. U1 and U2 share this band geometry (one page type); they differ in the image plan, which comes from `80-signature-upsell/components/adapters/upsell_image_plan.py`, so each page's images carry their own subject, composition and art direction.

## The eight bands

| # | Band | Layout tag | Geometry | Image slot and ratio |
|---|---|---|---|---|
| 1 | Opening offer | `hero-confirm` | A thin order-confirmed strip across the top, the offer headline beside one wide hero image plate, then the CTA stack. | IMG-001 16:9 |
| 2 | First problem | `split-right` | Headline and body in a left column with a short row of icon bullets, one image plate on the right, then the CTA stack. | IMG-002 4:3 |
| 3 | Second problem | `wide-over` | One wide image plate with the headline laid over it, the body in a centred column under it, then the CTA stack. | IMG-003 3:2 |
| 4 | Third problem | `dark-card` | A full-width dark ground: headline and body on a narrow dark card that overlaps the edge of the image plate on the right, then the CTA stack. | IMG-004 4:3 |
| 5 | Why now | `split-left` | Image plate on the left, headline and one supporting paragraph on the right on a light ground, then the CTA stack. | IMG-005 3:2 |
| 6 | Who it is for | `who-list` | A persona list of check rows beside the image plate, then the CTA stack. | IMG-006 1:1 |
| 7 | What is added | `what-panel` | Extra inclusions as check rows on the left, a price-and-terms panel with the exact terms line and the CTA on the right. | IMG-007 4:3 |
| 8 | Seven reasons | `reasons-seven` | Seven numbered reason chips 1 to 7 each beside its reason text, then the final CTA stack. | IMG-008 3:2 |

## Rules the layout keeps

1. Eight bands in this order, one request section per band; never band-compressed.
2. The three problem bands (2, 3, 4) never share one geometry; no two adjacent bands share a layout tag.
3. A wireframe slice of section N carries exactly the layout tag declared for N.
4. Nothing in this file is copy and nothing is an offer claim. The words come from the approved page copy; the layout names bands, not sentences.
