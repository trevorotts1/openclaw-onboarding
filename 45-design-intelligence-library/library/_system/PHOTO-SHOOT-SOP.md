# PERSONAL PHOTO SHOOT MODE — SOP
**Version:** 1.0 | **Last Updated:** 2026-06-12
**Audience:** AI agents. This mode generates new imagery of a REAL, SPECIFIC person — the client — with their identity locked and everything else variable: locations, wardrobe, poses, backgrounds, stylization, and retouching. Treat identity fidelity as the #1 success metric; a beautiful image of the wrong-looking person is a total failure.

---

## 1. CONSENT & IDENTITY RULES (non-negotiable)

- Generate a real person's likeness ONLY for the client themself or with the client's documented permission, routed through the producer.
- Never place the client's likeness in deceptive contexts (fake endorsements they didn't approve, fabricated events presented as real news, compromising scenarios).
- All photo-shoot outputs route through the producer for approval before reaching the client — standard gatekeeper model.
- Retouching serves the client's stated wishes. Execute requested edits matter-of-factly. If a requested change is so extreme the person would no longer be recognizable, flag it to the producer — not as judgment, but because identity drift breaks the deliverable's purpose.

## 2. SOURCING THE CLIENT'S IMAGE (resolution hierarchy)

Locate reference images in this order; use the FIRST source that yields usable refs:
1. **Images attached to the current request.**
2. **The client's identity profile** in this library: `personal-photo-shoot/{client-slug}/IDENTITY.md` (schema in §3).
3. **The client's media library folder**, if the workspace has one.
4. **Paths referenced in workspace config files**: check `AGENTS.md`, `TOOLS.md`, `MEMORY.md`, `USER.md`, `IDENTITY.md` for declared client image locations or media library paths.

**Verification step (mandatory):** before generating, confirm you have the right person — match against the identity profile description, or ask the operator if any ambiguity exists (two clients named similarly, multiple people in refs, outdated images). Never guess identity.

**Reference quality bar:** ideal set = 3–10 images: one clear frontal face, one 3/4 angle, one full body, in good light. Note deficiencies in the shoot record ("only one low-res frontal ref available — expect reduced identity fidelity").

## 3. CLIENT IDENTITY PROFILE (one per client)

File: `personal-photo-shoot/{client-slug}/IDENTITY.md`
```markdown
# IDENTITY — {Client Name}
- Slug / Created / Updated / Consent status & date
## Reference Images
| # | Path or URL | Type (frontal/3-4/full-body) | Quality note |
## Identity Description (what must NEVER change)
{facial structure, skin tone described richly and precisely, eye color, distinguishing
features — glasses, locs, beard, beauty marks — typical hair, age range, build}
## Standing Retouch Preferences (pre-approved)
{e.g., "always remove temporary blemishes; whiten teeth one shade; never alter nose or body shape"}
## Wardrobe & Brand Notes
{brand colors for outfits, styles the client favors/avoids, modesty preferences}
## Do-Not List
{client-specific never-do items}
## Shoot History
| Date | Shoot type | Winning outputs | Notes |
```

## 4. THE IDENTITY LOCK BLOCK (mandatory in every photo-shoot prompt)

Include this block, adapted per client, in EVERY generation involving the client's likeness:
```
Preserve this exact person's identity with complete fidelity: the same facial structure,
the same facial proportions, the same {skin tone — describe richly, e.g., "deep warm brown
skin with golden undertones"}, the same eyes, nose, mouth, and {distinguishing features}.
Render their skin tone EXACTLY as in the reference — do not lighten, grey, or desaturate it.
Do not alter their age, weight, or features except as explicitly instructed below.
Use the attached image(s) as identity reference for this person only — do not copy the
background, clothing, pose, or composition of the reference unless instructed.
```
The skin-tone preservation line is a HARD RULE — skin lightening is the most common and most damaging identity-drift failure, and is never acceptable.

## 5. SHOOT MODES

| Mode | What changes | What's locked | Primary endpoint |
|---|---|---|---|
| **A. Location** | Setting/background/environment | Identity, (optionally) outfit | Nano Banana 2 or GPT-Image 2 I2I |
| **B. Wardrobe** | Clothing ("blue suit", "red dress", brand-color outfit) | Identity, pose if on existing photo | Seedream 4.5 Edit (on a photo) / NB2 (new scene) |
| **C. Action & Pose** | Body position, activity (speaking on stage, walking city street, arms crossed power pose) | Identity, wardrobe optional | Nano Banana 2 or GPT-Image 2 I2I |
| **D. Editorial / Lifestyle** | Full scene built to a style card (e.g., "client in style SI-003") | Identity | GPT-Image 2 I2I (refs + LONG style spec) |
| **E. Slide Integration** | Client placed into a PPT family's visual world | Identity + the deck's foundation style | Per PPT card routing; include foundation block + identity lock |
| **F. Stylized / Cartoon** | Render style (3D animated character, comic illustration, watercolor portrait, flat vector avatar) | Recognizable identity through the stylization | GPT-Image 2 I2I or NB2 |
| **G. Retouch** | Targeted corrections on a REAL photo | Everything except the named fix | **Seedream 4.5 Edit — the true editor** |

Mode prompts COMBINE: Identity Lock Block + mode instructions + (if style-driven) the style card prompt with {SUBJECT} = "this exact person from the reference images."

**Mode F note:** describe target styles generically ("glossy 3D animated character style with large expressive eyes," "bold ink comic illustration") — never instruct the model to copy a named studio's or artist's protected style.

## 6. RETOUCH MODE (Mode G) — detailed protocol

**Endpoint:** Seedream 4.5 Edit is the primary tool — it is the only roster endpoint that performs true surgical editing (change X, genuinely keep everything else). GPT-Image 2 I2I is the fallback when the edit needs a long spec; expect more regeneration drift. All other endpoints regenerate rather than edit.

**The retouch catalog** (all legitimate, client-requested):
- Skin: blemish/acne removal, even skin tone, reduce shine, soften under-eye — "natural skin texture retained" always
- Teeth: whitening (specify shades: "one shade whiter"), minor straightening/gap correction
- Body: slimming/contouring — specify area and degree ("slightly slimmer waistline, approximately 10%, natural proportions")
- Hair: flyaway cleanup, fill thinning areas, color refresh
- Eyes: redness removal, glasses-glare removal, brighten slightly
- Cleanup: remove background objects, stains on clothing, lint, wrinkles in fabric

**Rules of the craft:**
1. **One change per pass.** Chain passes for multiple edits — each pass's prompt: "Keep everything unchanged except: {single edit}." Chaining preserves control and isolates failures.
2. **Specify degree on a 1–5 subtlety scale** and translate to language: 1 = "barely perceptible," 3 = "noticeable but natural," 5 = "dramatic." Default 2 unless client specifies.
3. **Preserve-first phrasing** (Seedream responds best): lead with what to keep, then the change.
4. **Natural-result guardrails** in every retouch prompt: "retain natural skin texture and pores, no plastic smoothing, result must look like an unedited photograph."
5. Output at `quality: high` (4K) for final passes; `basic` for intermediate chain steps.

**Retouch prompt skeleton (Seedream 4.5 Edit, ≤3,000 chars):**
```
Keep this person's identity, facial structure, skin tone, pose, expression, lighting,
clothing, and background completely unchanged. Make exactly one change: {EDIT — e.g.,
"remove the blemishes on the forehead and left cheek"}. Degree: {subtle/noticeable-but-
natural}. Retain natural skin texture and pores; no plastic smoothing. The result must
look like the same unedited photograph with only this correction applied.
```

## 7. RESOLUTION & RATIO

- Headshots/portraits: 3:4 or 4:5. Full scenes: per destination (slide = 16:9, IG = per SM rules).
- Resolution: drafts 1K; deliverables 2K; print/large-format/retouch-finals 4K. Client choice governs — ask via producer if unspecified, default 2K.

## 8. STANDARD WORKFLOW

1. **Brief**: client, shoot mode(s), scene/wardrobe/pose list, destination format, resolution choice, style card if any.
2. **Identity check**: load/create IDENTITY.md, verify refs (§2).
3. **Contact sheet**: generate 3–4 draft variants per concept at 1K (Wan 2.7 n=4 for no-ref concept frames, or NB2 1K with refs).
4. **Producer selects** winners.
5. **Final render** of winners at chosen resolution on the mode's primary endpoint.
6. **Retouch chain** (Mode G passes) as requested.
7. **Log** the shoot in IDENTITY.md Shoot History; save winning prompts as a Shoot Card if reusable (§9).

## 9. SHOOT CARDS (PS-)

Reusable, client-agnostic shoot concepts stored as standard style cards in `personal-photo-shoot/` with prefix PS- (e.g., `PS-001_executive-rooftop-golden-hour.md`). They follow STYLE-CARD-TEMPLATE.md with {SUBJECT} = the identity-locked client. Register in INDEX.md like any style.

## 10. FAILURE MODES (photo-shoot-specific)

| Failure | Fix |
|---|---|
| Identity drift (looks like a different person) | More refs (add 3/4 + full body); strengthen Identity Lock; reduce competing style instructions; switch to NB2 multi-ref |
| **Skin tone lightened** | HARD FAIL. Re-run with skin description doubled (positive twin + negative); never deliver |
| Plastic/over-smoothed skin | Add texture guardrails (§6 rule 4); lower subtlety degree |
| Age shift (younger/older) | Add "exact same age as reference" to Identity Lock |
| Body proportions altered unrequested | Add "same build and body proportions as reference" |
| Reference clothing/background copied into new scene | Strengthen the "identity reference only" clause; on NB2 reduce ref count |
| Stylized mode loses likeness | Reduce stylization degree; "the face must remain clearly recognizable as this person" |
