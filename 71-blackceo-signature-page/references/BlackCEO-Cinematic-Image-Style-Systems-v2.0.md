# CINEMATIC IMAGE STYLE SYSTEMS
## 50 Research-Derived Visual Grammars for AI Image Creation

**Document type:** AI-facing master style manual  
**Version:** 2.0 — Compiler + Fidelity QC Upgrade  
**Purpose:** Convert recognizable cinematic image languages into original, name-independent visual systems that an AI agent can execute from explicit visual rules rather than relying on a filmmaker's name.

---

# 0. HOW TO USE THIS DOCUMENT

This manual contains 50 visual systems derived from research into the recurring image-making decisions associated with the filmmakers in the source list. The goal is **not** to reduce a filmmaker to a color grade, one famous movie, or a handful of adjectives. Each system isolates recurring, transferable image variables such as:

- composition and subject placement
- camera height and point of view
- lens behavior and spatial compression
- depth of field
- lighting motivation and contrast behavior
- color architecture
- texture and image finish
- production design and environmental geometry
- portrait/character direction
- motion language and implied motion in stills
- relationship between foreground, subject, and background
- use of realism, abstraction, symbolism, or spectacle
- recurring visual tensions
- failure modes that make an image generic instead of faithful to the intended grammar

## Deployment rule

The filmmaker's name appears only in each **Research Lineage** field so a human can audit where the analysis came from. When generating an image, the AI should use the **Branded Style Name**, **Style ID**, and the **AI Deployment Block**. Do not depend on the source filmmaker's name as a prompt token.

## Evidence discipline

Each profile distinguishes between:

1. **Persistent visual invariants** — traits that recur across multiple works or are explicitly discussed by the filmmaker/cinematographer.
2. **Film-specific variants** — choices that belong to a particular project and should not be mistaken for a universal signature.
3. **AI synthesis rules** — operational instructions derived from the research. These are not quotations; they are an executable translation of the observed visual grammar.

When a filmmaker deliberately changes styles from project to project, this document models the **decision logic underneath the variation** rather than pretending there is one permanent LUT, lens, or palette.

## Recommended prompt structure

```text
STYLE SYSTEM: [BRANDED STYLE NAME / STYLE ID]
SUBJECT: [who or what]
ACTION: [what is happening]
ENVIRONMENT: [where]
STORY BEAT: [what the image should make us feel or understand]

Apply the full visual grammar for the selected style system. Preserve the subject and action exactly. Let the style system determine composition, camera behavior, lighting logic, color architecture, texture, environmental treatment, and emotional framing.
```

---

# 0A. UNIVERSAL STYLE COMPILER PROTOCOL

The **Style Compiler** converts an ordinary user request into a generation-ready instruction set while preserving the user's subject. It is not a synonym generator. It is a transformation pipeline that maps the selected visual system onto specific image variables.

## Compiler input
The compiler receives:
- **Subject lock:** identity, species/object, age if supplied, clothing, required colors, props, and non-negotiable attributes.
- **Action lock:** what the subject is doing.
- **Environment lock:** required location or setting, if supplied.
- **Story beat:** the emotion, idea, or dramatic moment the image should communicate.
- **Selected style system:** one CIS profile from this document.

## Compiler order of operations
The agent must compile in this order:

1. **LOCK USER CONTENT.** Copy all non-negotiable subject/action/environment requirements into a protected list. Style may not erase or replace them.
2. **SELECT THE STYLE'S FIVE CORE ANCHORS.** Use the five anchors listed in that profile's Style Compiler. These are the highest-priority visual traits.
3. **PLACE THE CAMERA.** Specify physical camera position, distance, angle, framing, lens/spatial behavior, and what remains readable in the background.
4. **BUILD LIGHT FROM SOURCES.** State the dominant light source, direction, hardness/softness, contrast behavior, and what the light does to faces/materials.
5. **BUILD COLOR THROUGH OBJECTS AND MATERIALS.** Assign color to wardrobe, walls, weather, practical lights, landscape, props, skin, vehicles, signage, or other real elements before using global grading language.
6. **BUILD ENVIRONMENTAL LOGIC.** Specify architecture, production design, weather, material texture, and spatial relationships that make the selected visual grammar visible.
7. **DIRECT THE SUBJECT.** Specify posture, gaze, expression, energy, relationship to the environment, and implied movement.
8. **ADD THE STYLE-SPECIFIC CONTRAST.** Introduce at least one tension appropriate to the system: intimacy/scale, ordinary/impossible, beauty/isolation, community/authority, stillness/motion, order/distortion, etc.
9. **RUN THE AVOID FILTER.** Remove choices listed in that profile's Avoid section unless the user explicitly requires them.
10. **ASSEMBLE ONE COHERENT GENERATION PROMPT.** Do not dump disconnected adjectives. Express the scene in causal visual language: what is present, where the camera is, how light behaves, how space is organized, what materials/colors are visible, and what emotional tension the image carries.

## Compiled prompt schema

```text
SUBJECT LOCK: [exact user-required subject, clothing, colors, props]
ACTION LOCK: [exact user-required action]
ENVIRONMENT LOCK: [required setting, if any]

STYLE SYSTEM: [BRANDED NAME / CIS-ID]
CORE ANCHORS: [five profile-specific anchors]
CAMERA: [position + distance + angle + framing + lens/spatial behavior]
COMPOSITION: [subject placement + foreground/midground/background + geometry]
LIGHT: [source + direction + quality + contrast behavior]
COLOR/MATERIALS: [object-level palette + tactile materials]
ENVIRONMENT: [architecture/location/weather/production-design logic]
CHARACTER DIRECTION: [posture + gaze + expression + movement]
STYLE CONTRAST: [one meaningful tension]
ANTI-DRIFT: [profile-specific avoid rules]

FINAL GENERATION INSTRUCTION:
[one integrated, image-specific prompt using the fields above]
```

## Subject-preservation rule
If style and subject conflict, preserve the user's required subject first and adapt the style around it. Example: if the user asks for a blue duck with red boots, the compiler may change camera, light, environment, texture, contrast, and physical behavior, but it may not remove the blue feathers or red boots.

## Minimum successful application
A generated image must visibly express **at least four of the five core anchors**, and all five should be represented in the prompt unless the user's requirements directly conflict with one of them.

## Abstract-anchor translation rule
A conceptual anchor does **not** count merely because the prompt repeats the concept. Translate it into visible image behavior. For example, `institutional pressure` must become something observable such as a small subject constrained by rigid architecture, authority figures controlling foreground space, compressed blocking, or restrictive sightlines. `Dignity` must become observable through posture, eye line, respectful camera distance, skin rendering, and non-exploitative framing. The Fidelity Gate scores what is visible in the image, not whether the prompt used the right vocabulary.

---

# 0B. STYLE FIDELITY GATE AND CORRECTION LOOP

Every generated image must be checked after generation. The agent must not assume that a good prompt automatically produced a faithful image.

## Eight-dimension fidelity score
Score each dimension from **0 to 10**:

1. **Content preservation** — did the image preserve the user's locked subject/action/required details?
2. **Camera + composition** — does framing and camera placement visibly follow the selected system?
3. **Lens + spatial behavior** — is depth, perspective, compression/expansion, and background readability appropriate?
4. **Lighting logic** — does light follow the selected system's source, direction, contrast, and skin/material behavior?
5. **Color + material architecture** — are color and texture produced through the correct objects/materials rather than a generic filter?
6. **Environment + production design** — does the space behave like the selected system instead of generic cinematic scenery?
7. **Character/action direction** — do posture, gaze, movement, and emotional temperature fit the grammar?
8. **Signature fidelity** — are at least four of the five core anchors clearly visible, with no dominant Avoid-rule violation?

## Passing standard
A result **passes only if**:
- the average score is **8.0 or higher**;
- **Content preservation** is at least **9.0**;
- **Signature fidelity** is at least **8.0**;
- no other dimension is below **7.5**;
- at least four of five core anchors are visibly present;
- no dominant Avoid-rule violation has taken over the image.

## Correction loop
If the image fails:

1. Identify only the failed dimensions.
2. Name the visible failure precisely. Example: `background erased by shallow focus`, not `not cinematic enough`.
3. Write a **repair delta** containing only corrective instructions for those failed dimensions.
4. Preserve all locked user content and all dimensions that already scored 8+.
5. Regenerate with the original compiled prompt + repair delta.
6. Re-score.
7. Run a maximum of **two automatic repair cycles**. After two failed cycles, report the persistent failure instead of drifting into endless prompt mutation.

### Repair-delta template

```text
REPAIR DELTA
FAILED DIMENSION(S): [names]
VISIBLE FAILURE: [specific visual problem]
PRESERVE: [successful elements that must not change]
CORRECT: [specific camera/light/color/material/environment/action changes]
DO NOT ADD: [new drift risks]
```


---

# 0C. WORKED STYLE-COMPILER EXAMPLE

This example demonstrates how to compile a simple user request without changing its required content.

## Raw user request
`Create a blue duck wearing red boots, dancing in the rain.`

## Selected system
`PHYSICAL PARADOX CINEMA / CIS-02`

## Step 1 — Subject/action lock
- blue duck
- red boots
- dancing
- rain

These four requirements are protected. The style may not replace the duck, recolor it, remove the boots, or change the action.

## Step 2 — Core anchors
- extraordinary event treated as physical reality
- environmentally motivated light
- functional structural geometry
- believable human-scale camera position
- readable environmental context

## Step 3 — Camera compilation
Place the camera near street level, several meters from the duck, with a natural wide-to-normal spatial feel. Keep the duck large enough to read clearly but retain the surrounding street, building geometry, wet roadway, and distant structures. Do not erase the environment with portrait-mode blur.

## Step 4 — Light compilation
Use overcast rain as the broad source, supplemented only by plausible streetlights, storefront spill, vehicle lamps, or window light. Reflections on wet asphalt must correspond to those sources.

## Step 5 — Color/material compilation
The duck's blue feathers and red rubber boots are the primary saturated colors. Surround them with concrete, wet asphalt, glass, steel, muted sky, vehicle surfaces, and small practical lights. Do not apply a global teal/orange filter.

## Step 6 — Environmental paradox
Introduce one impossible but physically photographed event: several lanes of roadway in the far background curve upward into a vertical plane while cars, rainwater, concrete barriers, and headlights continue to behave with convincing weight and material detail. The duck remains physically grounded in the foreground.

## Step 7 — Action/physicality
The dancing duck displaces puddle water with each step. Wet feathers clump naturally. Boots contact the pavement with believable weight. Rain interacts with feathers, rubber, roadway, and reflections.

## Step 8 — Anti-drift
Reject neon cyberpunk, unexplained rim light, fantasy glow, glossy CGI surfaces, extreme bokeh, weightless motion, and arbitrary lens flare.

## Compiled generation instruction
> A blue duck wearing bright red rubber boots dances energetically in steady rain on a real wet city street, photographed from a believable street-level position with a natural wide-to-normal perspective. Keep the duck prominent but preserve the surrounding concrete, glass, roadway, puddles, traffic infrastructure, and distant architecture in readable depth. Use soft overcast daylight plus only plausible street, window, and vehicle light, with reflections tied to those sources. Render wet feathers, rubber boots, asphalt, concrete, glass, rainwater, splashes, and vehicle surfaces with tactile physical detail and believable mass. In the far background, a section of roadway rises into an impossible vertical curve while cars and water continue to obey convincing physical behavior. The impossible event should look genuinely photographed rather than fantastically lit. Preserve restrained location-derived color, realistic atmospheric depth, and environmental geometry. Avoid cyberpunk neon, glossy CGI, fantasy glow, excessive bokeh, arbitrary flares, and weightless action.

## Fidelity check before accepting
The result passes only if the duck is still blue, the boots are still red, the duck is visibly dancing in rain, at least four CIS-02 anchors are clearly present, and the eight-dimension Fidelity Gate averages at least 8.0.

# 0D. RESEARCH TRACEABILITY STANDARD

Research anchors in each profile are now treated as an auditable evidence record rather than decorative bibliography.

## Evidence tags
- **[TECH-1]** — first-person director/cinematographer craft interview, production breakdown, or technical trade source.
- **[INST-2]** — institutional film source such as BFI, Criterion, DGA, Cannes, cinematheque, archive, or restoration material.
- **[FRAME-3]** — comparative observation across representative frames from multiple works.
- **[CRIT-4]** — reputable critical/scholarly analysis used where first-person technical documentation is limited.

## Evidence-use rule
The agent may convert supported observations into operational image instructions, but must not invent exact focal lengths, stocks, camera packages, lighting diagrams, or production methods unless the anchor actually supports them. When evidence is thinner, the system should become **more conservative technically, not more generic visually**: emphasize observable composition, light behavior, spatial logic, palette construction, materials, point of view, and recurring visual tensions.

## Traceability confidence
Each profile includes a traceability confidence label derived from the evidence present in this manual:
- **HIGH** — multiple technical/first-person or institutional anchors support the operational rules.
- **MEDIUM-HIGH** — at least one strong institutional/technical anchor plus cross-film comparison.
- **MEDIUM** — primarily institutional/critical/frame-comparison evidence; operational instructions remain grounded in observable screen grammar.
- **CONSERVATIVE** — technical documentation is thin; the profile intentionally avoids unsupported technical claims.


# 01. SOVEREIGN HUMAN LIGHT
**Style ID:** CIS-01  
**Research Lineage:** Ava DuVernay  
**Representative works studied:** *Middle of Nowhere*, *Selma*, *13th*, *When They See Us*, *Origin*

## Research synthesis
The recurring image logic is less about a fixed color palette than about **dignified human presence inside socially meaningful environments**. DuVernay and cinematographer Bradford Young discussed building *Middle of Nowhere* around nuanced rendering of Black skin, meaningful shadow, natural environments, and a refusal to impose a pre-designed 'cool' look on the characters. The image is allowed to become warm, cool, still, or fluid according to the emotional truth of the scene. Across later work, faces remain central, institutions and public spaces carry social weight, and camera movement tends to feel purposeful rather than ornamental.

## Persistent visual invariants
- Render dark skin with dimensional highlight rolloff and meaningful shadow detail; never flatten the face into a single exposure value.
- Put human dignity ahead of visual gimmickry.
- Allow the environment to communicate social position, institutional pressure, family structure, or community context.
- Use controlled camera movement that can shift between still observation and fluid emotional attachment.
- Favor naturalistic or plausibly motivated light even when the result is visually rich.
- Let color emerge from place, wardrobe, and emotional state rather than forcing one signature grade.
- Use close portraiture at moments of moral choice, grief, resolve, or recognition.
- Keep the image socially grounded: streets, homes, public buildings, courtrooms, classrooms, transit spaces, and gathering places should feel inhabited rather than designed as generic sets.

## AI image-construction rules
### Composition and camera
Frame people as full psychological subjects. Use medium close-ups and close-ups when emotion is the story, but preserve contextual details when social environment matters. Avoid reducing the subject to a decorative silhouette. In group scenes, organize bodies to reveal relationships and power rather than merely fill the frame.

### Lighting
Use soft but directional naturalism. Protect skin tone separation in shadows. Windows, practical lamps, overcast daylight, late sun, or institutional fixtures should appear to be the reason the scene is lit. Allow shadow to carry emotional weight without erasing facial information.

### Color
Build palettes from the actual world: warm wood, neutral walls, skin, street color, clothing, church interiors, civic architecture, or landscape. Permit selective warmth or coolness to follow emotional state. Avoid a one-size-fits-all teal/orange grade.

### Texture and environment
Favor tactile realism: lived-in homes, real street surfaces, paper, fabric, glass, wood, concrete, natural hair texture, skin texture, and atmospheric depth. The world should feel inhabited before the camera arrived.

### Character direction
Expressions should feel observed rather than posed. Favor held emotion, internal calculation, resilience, grief, moral attention, and moments when a character is deciding what to do.

### Avoid
- cosmetic beauty lighting that disconnects the person from the scene
- gratuitous shallow focus on every portrait
- generic prestige-drama desaturation
- movement with no emotional purpose
- flattening Black skin or crushing it into shadow
- social environments treated as anonymous backdrops

## AI Deployment Block
**SOVEREIGN HUMAN LIGHT / CIS-01:** Build the image around dignified human presence and emotionally truthful observation. Render skin, especially dark skin, with dimensional highlights, nuanced shadow, and natural texture. Use plausible environmental light, purposeful stillness or fluid movement, socially meaningful locations, and composition that reveals relationships and institutional context. Let color come from the world and emotional state rather than a fixed grade. Keep faces psychologically specific, environments lived-in, and camera choices motivated by what the subject is experiencing. Avoid decorative cinematography, generic prestige desaturation, empty movement, and beauty lighting that separates the person from reality.

## Style Compiler
**Compiler role:** Convert any user subject into this visual system without changing the user's required content.

### Five non-negotiable visual anchors
1. Render dark skin with dimensional highlight rolloff and meaningful shadow detail; never flatten the face into a single exposure value.
2. Put human dignity ahead of visual gimmickry.
3. Allow the environment to communicate social position, institutional pressure, family structure, or community context.
4. Use controlled camera movement that can shift between still observation and fluid emotional attachment.
5. Favor naturalistic or plausibly motivated light even when the result is visually rich.

**Minimum visibility rule:** At least four of these five anchors must be visibly present in the generated image. All five should be encoded in the prompt unless a locked user requirement conflicts.

### Style-specific compilation sequence
1. **Lock the subject.** Preserve every user-required identity/species/object, clothing item, color, prop, action, and setting constraint.
2. **Establish the visual premise.** Use the logic of **SOVEREIGN HUMAN LIGHT / CIS-01** rather than adding generic cinematic adjectives. The deployment block above is the governing summary.
3. **Compile camera + composition.** Translate the profile's camera/composition rules into one explicit camera location, distance, framing, spatial behavior, and foreground/background relationship.
4. **Compile light.** Name the physical or psychological source, direction, hardness/softness, contrast behavior, and what it does to faces/materials.
5. **Compile color + materials.** Put the style palette into actual objects, surfaces, weather, wardrobe, architecture, practical light, landscape, skin, or props before using global grading language.
6. **Compile environment.** Make the space carry the style through architecture, geography, social context, production design, weather, and tactile material behavior.
7. **Compile character/action direction.** Specify posture, gaze, expression, movement, and emotional temperature so the subject participates in the visual grammar rather than merely standing inside it.
8. **Enforce the five anchors.** Check the prompt line-by-line and add any missing core anchor in concrete visual form.
9. **Run the anti-drift filter.** Reject or rewrite these failure modes: cosmetic beauty lighting that disconnects the person from the scene; gratuitous shallow focus on every portrait; generic prestige-drama desaturation; movement with no emotional purpose; flattening Black skin or crushing it into shadow; social environments treated as anonymous backdrops.
10. **Assemble one causal prompt.** The final instruction must read like a photographable scene, not a bag of adjectives.

### Compiled output checklist
- **STYLE:** SOVEREIGN HUMAN LIGHT / CIS-01
- **SUBJECT LOCK:** exact user content preserved
- **CAMERA:** physical placement + framing + spatial behavior
- **LIGHT:** source + direction + contrast behavior
- **COLOR/MATERIALS:** object-level palette + tactile surfaces
- **ENVIRONMENT:** style-specific spatial/production-design logic
- **CHARACTER/ACTION:** posture + gaze + expression + movement
- **CORE ANCHORS:** all five represented in the prompt
- **ANTI-DRIFT:** Avoid-rule conflicts removed
- **FINAL PROMPT:** one integrated generation instruction


## Style Fidelity Gate
**Pass threshold:** average fidelity score >= **8.0/10**, Signature Fidelity >= **8.0**, Content Preservation >= **9.0**, and no other dimension below **7.5**.

### Profile-specific signature test
- Anchor 1: Render dark skin with dimensional highlight rolloff and meaningful shadow detail; never flatten the face into a single exposure value.
- Anchor 2: Put human dignity ahead of visual gimmickry.
- Anchor 3: Allow the environment to communicate social position, institutional pressure, family structure, or community context.
- Anchor 4: Use controlled camera movement that can shift between still observation and fluid emotional attachment.
- Anchor 5: Favor naturalistic or plausibly motivated light even when the result is visually rich.

The image fails signature fidelity if fewer than four anchors are clearly visible.

### Score after generation
Score **Content Preservation, Camera/Composition, Lens/Space, Lighting, Color/Materials, Environment/Texture, Character/Action, and Signature Fidelity** from 0-10 using the global Fidelity Gate.

### Correction rule
If any passing condition fails, write a repair delta only for the failed dimensions, preserve successful dimensions, and regenerate. Run no more than two automatic repair cycles. Do not respond to failure by making the image generically "more cinematic."


### Research traceability record
**Traceability confidence:** MEDIUM-HIGH

**Evidence-use instruction:** Use these anchors to support the visual rules above. Do not infer unsupported technical specifications.

- [TECH-1] *Filmmaker Magazine* — Ava DuVernay / Bradford Young discussion of *Middle of Nowhere*: Black skin, nuanced shadows, lived environments, and image choices led by the moment rather than a preset look.
- [FRAME-3] Representative-frame comparison across *Middle of Nowhere*, *Selma*, *When They See Us*, and *Origin*.

---

# 02. PHYSICAL PARADOX CINEMA
**Style ID:** CIS-02  
**Research Lineage:** Christopher Nolan  
**Representative works studied:** *The Dark Knight*, *Inception*, *Interstellar*, *Dunkirk*, *Oppenheimer*

## Research synthesis
The most useful recurring principle is **photographic realism applied to extraordinary events**. In research around *Inception*, Nolan and Wally Pfister repeatedly emphasized that dreams should look photographically real and that strangeness should come from the environment or event rather than from obviously 'dreamy' photography. Location-specific palettes, practical/in-camera effects, naturalistic sources, moving point of view, and substantial environmental context recur. With Hoyte van Hoytema, large-format photography is also used for unusual human proximity, not only spectacle: close faces remain embedded in surrounding space. *Dunkirk* adds reactive, documentary-like physical immediacy; *Oppenheimer* intensifies psychological proximity while keeping source logic and tactile film character.

## Core visual law
**Make the event impossible. Make the photograph believable.**

## Persistent visual invariants
- Extraordinary events are treated as physical reality.
- Lighting looks motivated by the environment rather than by decorative movie lighting.
- Architecture and infrastructure create strong functional geometry.
- Human-scale camera positions make impossible events feel observable and real.
- Environmental information remains important even in close portraiture.
- Different locations may have distinct natural palettes; there is no single universal color grade.
- Physical mass, inertia, debris, weather, and contact matter.
- Camera movement follows action or thought rather than advertising-style choreography.
- Film texture and slight imperfection are preferable to sterile digital polish.

## AI image-construction rules
### Composition
Use roads, corridors, bridges, stairwells, windows, runways, city blocks, laboratories, machinery, and institutional spaces to create strong horizontals, verticals, rectangles, and vanishing lines. Geometry should feel structural, not decorative. Combine intimate human scale with a larger environmental system.

### Lens and depth
Favor naturalistic wide-to-normal perspective. Keep enough background information to understand the space. Avoid default portrait-mode bokeh. In close images, let architecture or environmental force remain present around the face.

### Lighting
Every major source should be physically plausible: sky, windows, practical lamps, headlights, fluorescent fixtures, fire, projection, industrial lights. Avoid gratuitous rim lights or fantasy glow.

### Color
Derive palette from location and story. One environment may be cold and metallic, another warm and wood-toned, another neutral or sun-bleached. Maintain internal color identity without imposing a universal LUT.

### Physicality
Vehicles, bodies, buildings, water, smoke, and debris must have believable mass. If physics are violated, everything else should obey physics. Let extraordinary motion create environmental consequences.

### Character direction
Favor concentration, calculation, restrained fear, moral pressure, intellectual tension, and internal conflict. Avoid action-poster posing.

### Avoid
- generic neon sci-fi
- excessive teal/orange grading
- arbitrary flares and haze
- extreme background blur everywhere
- glossy CGI surfaces
- weightless action
- fantasy lighting with no source
- spectacle without a human or physical point of reference

## AI Deployment Block
**PHYSICAL PARADOX CINEMA / CIS-02:** Treat impossible subject matter as documentary reality. Use physically motivated light, credible materials, functional architecture, human-scale camera positions, strong structural geometry, restrained location-specific color, readable environmental context, tactile film texture, and believable mass and inertia. Keep surrealism in the event rather than in decorative photography. Combine intimate human proximity with large systems or spaces. Preserve real atmospheric behavior and physical consequences. Avoid glossy CGI, generic neon, gratuitous bokeh, unexplained rim light, fantasy haze, and weightless spectacle. **Make the event impossible; make the photograph believable.**

## Style Compiler
**Compiler role:** Convert any user subject into this visual system without changing the user's required content.

### Five non-negotiable visual anchors
1. Extraordinary events are treated as physical reality.
2. Lighting looks motivated by the environment rather than by decorative movie lighting.
3. Architecture and infrastructure create strong functional geometry.
4. Human-scale camera positions make impossible events feel observable and real.
5. Environmental information remains important even in close portraiture.

**Minimum visibility rule:** At least four of these five anchors must be visibly present in the generated image. All five should be encoded in the prompt unless a locked user requirement conflicts.

### Style-specific compilation sequence
1. **Lock the subject.** Preserve every user-required identity/species/object, clothing item, color, prop, action, and setting constraint.
2. **Establish the visual premise.** Use the logic of **PHYSICAL PARADOX CINEMA / CIS-02** rather than adding generic cinematic adjectives. The deployment block above is the governing summary.
3. **Compile camera + composition.** Translate the profile's camera/composition rules into one explicit camera location, distance, framing, spatial behavior, and foreground/background relationship.
4. **Compile light.** Name the physical or psychological source, direction, hardness/softness, contrast behavior, and what it does to faces/materials.
5. **Compile color + materials.** Put the style palette into actual objects, surfaces, weather, wardrobe, architecture, practical light, landscape, skin, or props before using global grading language.
6. **Compile environment.** Make the space carry the style through architecture, geography, social context, production design, weather, and tactile material behavior.
7. **Compile character/action direction.** Specify posture, gaze, expression, movement, and emotional temperature so the subject participates in the visual grammar rather than merely standing inside it.
8. **Enforce the five anchors.** Check the prompt line-by-line and add any missing core anchor in concrete visual form.
9. **Run the anti-drift filter.** Reject or rewrite these failure modes: generic neon sci-fi; excessive teal/orange grading; arbitrary flares and haze; extreme background blur everywhere; glossy CGI surfaces; weightless action.
10. **Assemble one causal prompt.** The final instruction must read like a photographable scene, not a bag of adjectives.

### Compiled output checklist
- **STYLE:** PHYSICAL PARADOX CINEMA / CIS-02
- **SUBJECT LOCK:** exact user content preserved
- **CAMERA:** physical placement + framing + spatial behavior
- **LIGHT:** source + direction + contrast behavior
- **COLOR/MATERIALS:** object-level palette + tactile surfaces
- **ENVIRONMENT:** style-specific spatial/production-design logic
- **CHARACTER/ACTION:** posture + gaze + expression + movement
- **CORE ANCHORS:** all five represented in the prompt
- **ANTI-DRIFT:** Avoid-rule conflicts removed
- **FINAL PROMPT:** one integrated generation instruction


## Style Fidelity Gate
**Pass threshold:** average fidelity score >= **8.0/10**, Signature Fidelity >= **8.0**, Content Preservation >= **9.0**, and no other dimension below **7.5**.

### Profile-specific signature test
- Anchor 1: Extraordinary events are treated as physical reality.
- Anchor 2: Lighting looks motivated by the environment rather than by decorative movie lighting.
- Anchor 3: Architecture and infrastructure create strong functional geometry.
- Anchor 4: Human-scale camera positions make impossible events feel observable and real.
- Anchor 5: Environmental information remains important even in close portraiture.

The image fails signature fidelity if fewer than four anchors are clearly visible.

### Score after generation
Score **Content Preservation, Camera/Composition, Lens/Space, Lighting, Color/Materials, Environment/Texture, Character/Action, and Signature Fidelity** from 0-10 using the global Fidelity Gate.

### Correction rule
If any passing condition fails, write a repair delta only for the failed dimensions, preserve successful dimensions, and regenerate. Run no more than two automatic repair cycles. Do not respond to failure by making the image generically "more cinematic."


### Research traceability record
**Traceability confidence:** HIGH

**Evidence-use instruction:** Use these anchors to support the visual rules above. Do not infer unsupported technical specifications.

- [TECH-1] *American Cinematographer* — *Inception*: photographic realism, motivated light, natural location hues, practical effects, handheld/documentary feeling, and dreams photographed as reality.
- [TECH-1] Kodak / cinematography interviews on *Oppenheimer*: large-format close proximity, 50mm/80mm preference, surrounding space retained, source-honest lighting.
- [TECH-1] *American Cinematographer* discussions of *Dunkirk*: reactive camera behavior, physical IMAX operation, reality as priority.

---

# 03. URBAN VOLTAGE FRAMING
**Style ID:** CIS-03  
**Research Lineage:** Spike Lee  
**Representative works studied:** *Do the Right Thing*, *Malcolm X*, *Clockers*, *25th Hour*, *BlacKkKlansman*

## Research synthesis
The recurring grammar combines **frontal confrontation, urban social geography, graphic color, expressive perspective, and sudden departures from ordinary camera physics when psychology or history demands it**. *Do the Right Thing* makes heat and racial tension visible through saturated production design, strong faces, wide-lens proximity, and graphic neighborhood staging. The signature double-dolly is not simply a trick: Lee has described it as a motivated way to separate a character psychologically from ordinary ground movement. Across films, direct address, bold low angles, wide-angle distortion, signs, walls, murals, storefronts, crowds, and music-performance energy make public space part of the argument.

## Persistent visual invariants
- Faces can confront the viewer directly.
- Urban environment is active social information, not background texture.
- Color can operate as emotional temperature or political pressure.
- Wide lenses frequently place characters close to the viewer while preserving neighborhood context.
- Perspective may become aggressive through low angles, canted frames, or exaggerated proximity.
- Graphic text, signs, flags, storefronts, and cultural objects are allowed to carry meaning inside the frame.
- Normal realism can abruptly give way to stylized motion when a character reaches a heightened psychological state.
- Ensemble blocking and crowd geography reveal social factions and tensions.

## AI image-construction rules
### Composition
Use strong frontal portraits, low-angle hero or confrontation frames, corner/storefront geometry, streets receding behind the subject, and group arrangements that visibly encode alliances or conflict. Allow centered framing when direct confrontation is desired.

### Lens behavior
Use wide-to-normal focal lengths at close physical distance. Let perspective exaggeration increase emotional charge. Keep the environment legible.

### Color and heat
Build bold color relationships from wardrobe, painted walls, signs, food stands, vehicles, brick, asphalt, and sunlight. In heat-driven scenes, push warm surfaces, red/orange accents, hard sun, and compressed air. Do not simply add saturation globally; assign color to objects and factions.

### Movement translated to still image
Suggest forward glide, floating psychological separation, or sudden social pressure through body posture, background motion, converging perspective, and directional blur only when motivated.

### Portrait direction
Eyes matter. Direct-to-camera looks may feel accusatory, declarative, humorous, or testimonial. Faces should carry social position and point of view.

### Avoid
- tasteful neutralization of the neighborhood
- random Dutch angles with no tension
- generic music-video neon
- color without social or emotional function
- shallow-focus portraits that erase the street
- using the floating/double-dolly feeling as decoration

## AI Deployment Block
**URBAN VOLTAGE FRAMING / CIS-03:** Build the image from confrontational faces, close wide-lens perspective, visible neighborhood geography, graphic signs and cultural objects, strong warm/cool or complementary color relationships, and social blocking that makes power and tension readable. Let ordinary street realism become more formally aggressive when psychology spikes: low angles, direct address, centered confrontation, canted perspective, or a floating sense of separation may appear when motivated. Keep color attached to architecture, wardrobe, heat, and community. Avoid tasteful generic urban photography, meaningless Dutch angles, and shallow-focus isolation from the neighborhood.

## Style Compiler
**Compiler role:** Convert any user subject into this visual system without changing the user's required content.

### Five non-negotiable visual anchors
1. Faces can confront the viewer directly.
2. Urban environment is active social information, not background texture.
3. Color can operate as emotional temperature or political pressure.
4. Wide lenses frequently place characters close to the viewer while preserving neighborhood context.
5. Perspective may become aggressive through low angles, canted frames, or exaggerated proximity.

**Minimum visibility rule:** At least four of these five anchors must be visibly present in the generated image. All five should be encoded in the prompt unless a locked user requirement conflicts.

### Style-specific compilation sequence
1. **Lock the subject.** Preserve every user-required identity/species/object, clothing item, color, prop, action, and setting constraint.
2. **Establish the visual premise.** Use the logic of **URBAN VOLTAGE FRAMING / CIS-03** rather than adding generic cinematic adjectives. The deployment block above is the governing summary.
3. **Compile camera + composition.** Translate the profile's camera/composition rules into one explicit camera location, distance, framing, spatial behavior, and foreground/background relationship.
4. **Compile light.** Name the physical or psychological source, direction, hardness/softness, contrast behavior, and what it does to faces/materials.
5. **Compile color + materials.** Put the style palette into actual objects, surfaces, weather, wardrobe, architecture, practical light, landscape, skin, or props before using global grading language.
6. **Compile environment.** Make the space carry the style through architecture, geography, social context, production design, weather, and tactile material behavior.
7. **Compile character/action direction.** Specify posture, gaze, expression, movement, and emotional temperature so the subject participates in the visual grammar rather than merely standing inside it.
8. **Enforce the five anchors.** Check the prompt line-by-line and add any missing core anchor in concrete visual form.
9. **Run the anti-drift filter.** Reject or rewrite these failure modes: tasteful neutralization of the neighborhood; random Dutch angles with no tension; generic music-video neon; color without social or emotional function; shallow-focus portraits that erase the street; using the floating/double-dolly feeling as decoration.
10. **Assemble one causal prompt.** The final instruction must read like a photographable scene, not a bag of adjectives.

### Compiled output checklist
- **STYLE:** URBAN VOLTAGE FRAMING / CIS-03
- **SUBJECT LOCK:** exact user content preserved
- **CAMERA:** physical placement + framing + spatial behavior
- **LIGHT:** source + direction + contrast behavior
- **COLOR/MATERIALS:** object-level palette + tactile surfaces
- **ENVIRONMENT:** style-specific spatial/production-design logic
- **CHARACTER/ACTION:** posture + gaze + expression + movement
- **CORE ANCHORS:** all five represented in the prompt
- **ANTI-DRIFT:** Avoid-rule conflicts removed
- **FINAL PROMPT:** one integrated generation instruction


## Style Fidelity Gate
**Pass threshold:** average fidelity score >= **8.0/10**, Signature Fidelity >= **8.0**, Content Preservation >= **9.0**, and no other dimension below **7.5**.

### Profile-specific signature test
- Anchor 1: Faces can confront the viewer directly.
- Anchor 2: Urban environment is active social information, not background texture.
- Anchor 3: Color can operate as emotional temperature or political pressure.
- Anchor 4: Wide lenses frequently place characters close to the viewer while preserving neighborhood context.
- Anchor 5: Perspective may become aggressive through low angles, canted frames, or exaggerated proximity.

The image fails signature fidelity if fewer than four anchors are clearly visible.

### Score after generation
Score **Content Preservation, Camera/Composition, Lens/Space, Lighting, Color/Materials, Environment/Texture, Character/Action, and Signature Fidelity** from 0-10 using the global Fidelity Gate.

### Correction rule
If any passing condition fails, write a repair delta only for the failed dimensions, preserve successful dimensions, and regenerate. Run no more than two automatic repair cycles. Do not respond to failure by making the image generically "more cinematic."


### Research traceability record
**Traceability confidence:** HIGH

**Evidence-use instruction:** Use these anchors to support the visual rules above. Do not infer unsupported technical specifications.

- [TECH-1] Directors Guild of America — Spike Lee on the double-dolly as a motivated psychological device.
- [INST-2] Criterion / BFI analysis of *Do the Right Thing*: saturated heat, faces, neighborhood staging, symmetry, movement, and graphic production design.

---

# 04. PRECISION STORYBOOK GEOMETRY
**Style ID:** CIS-04  
**Research Lineage:** Wes Anderson  
**Representative works studied:** *The Royal Tenenbaums*, *The Grand Budapest Hotel*, *Moonrise Kingdom*, *The French Dispatch*, *Asteroid City*

## Research synthesis
This visual system is built from **axial geometry, frontal theatricality, deliberate palette engineering, miniature-like world design, and choreographed camera movement**. The frame often behaves like an illustrated stage or architectural elevation: characters are centered or arranged laterally; the camera pans, tracks, or rotates in clean geometric directions; rooms are organized as visual compartments. Anderson and collaborators extensively test colors, props, fabrics, walls, and period references before shooting. Aspect ratio and medium can change to mark different narrative worlds.

## Persistent visual invariants
- Frontal or profile staging dominates; diagonal naturalism is reduced.
- Strong bilateral symmetry or deliberately balanced asymmetry.
- Centered subjects, repeated rectangles, shelves, doorways, windows, elevators, desks, and facades.
- Camera movement tends to be rectilinear: horizontal track, vertical move, 90-degree turn, snap zoom.
- Production design and costume are color-planned as a unified system.
- Environments feel hand-built, curated, and slightly miniaturized even when full scale.
- Deep staging allows multiple characters and objects to coexist legibly.
- Typography, labels, maps, documents, packages, and props can be graphic elements.

## AI image-construction rules
### Composition
Start by finding the visual axis. Place the camera square to walls, facades, tables, hallways, vehicles, or stages. Build a centered or carefully balanced tableau. Arrange secondary characters and props in clean rows or compartments. Favor full-body and medium-wide compositions that reveal the designed world.

### Lens and spatial feel
Use relatively wide lenses without chaotic distortion. Keep multiple planes readable. The room should feel like a stage box or diorama rather than a naturalistically messy location.

### Color
Choose a limited, intentional family of 3-6 principal colors. Repeat them across walls, wardrobe, furniture, vehicles, stationery, and small props. Pastel, dusty period hues, jewel tones, or desert primaries can all work if internally consistent. Do not default to one famous pink palette.

### Lighting
Keep lighting legible and clean, often soft or even enough to preserve production-design detail. Directional sun may be graphic, but muddy uncontrolled contrast should not obscure the geometry.

### Character direction
Deadpan or understated expression. Characters often appear composed within a system larger than themselves. Stillness is acceptable and often desirable.

### Avoid
- handheld chaos
- random shallow focus
- clutter without organization
- generic pastel grading detached from production design
- diagonal compositions that destroy the axial structure
- faux-quaint props without coherent world-building

## AI Deployment Block
**PRECISION STORYBOOK GEOMETRY / CIS-04:** Treat the frame as a meticulously built illustrated stage. Square the camera to architecture, establish a strong central axis, use symmetry or highly controlled balance, organize people and objects into legible compartments, and keep multiple planes readable. Engineer a limited palette across wardrobe, walls, props, vehicles, and typography. Favor rectilinear camera logic, deadpan portraiture, graphic documents/signage, and miniature-like environmental order. Avoid handheld naturalism, arbitrary pastel filters, chaotic diagonals, meaningless clutter, and shallow focus that hides the designed world.

## Style Compiler
**Compiler role:** Convert any user subject into this visual system without changing the user's required content.

### Five non-negotiable visual anchors
1. Frontal or profile staging dominates; diagonal naturalism is reduced.
2. Strong bilateral symmetry or deliberately balanced asymmetry.
3. Centered subjects, repeated rectangles, shelves, doorways, windows, elevators, desks, and facades.
4. Camera movement tends to be rectilinear: horizontal track, vertical move, 90-degree turn, snap zoom.
5. Production design and costume are color-planned as a unified system.

**Minimum visibility rule:** At least four of these five anchors must be visibly present in the generated image. All five should be encoded in the prompt unless a locked user requirement conflicts.

### Style-specific compilation sequence
1. **Lock the subject.** Preserve every user-required identity/species/object, clothing item, color, prop, action, and setting constraint.
2. **Establish the visual premise.** Use the logic of **PRECISION STORYBOOK GEOMETRY / CIS-04** rather than adding generic cinematic adjectives. The deployment block above is the governing summary.
3. **Compile camera + composition.** Translate the profile's camera/composition rules into one explicit camera location, distance, framing, spatial behavior, and foreground/background relationship.
4. **Compile light.** Name the physical or psychological source, direction, hardness/softness, contrast behavior, and what it does to faces/materials.
5. **Compile color + materials.** Put the style palette into actual objects, surfaces, weather, wardrobe, architecture, practical light, landscape, skin, or props before using global grading language.
6. **Compile environment.** Make the space carry the style through architecture, geography, social context, production design, weather, and tactile material behavior.
7. **Compile character/action direction.** Specify posture, gaze, expression, movement, and emotional temperature so the subject participates in the visual grammar rather than merely standing inside it.
8. **Enforce the five anchors.** Check the prompt line-by-line and add any missing core anchor in concrete visual form.
9. **Run the anti-drift filter.** Reject or rewrite these failure modes: handheld chaos; random shallow focus; clutter without organization; generic pastel grading detached from production design; diagonal compositions that destroy the axial structure; faux-quaint props without coherent world-building.
10. **Assemble one causal prompt.** The final instruction must read like a photographable scene, not a bag of adjectives.

### Compiled output checklist
- **STYLE:** PRECISION STORYBOOK GEOMETRY / CIS-04
- **SUBJECT LOCK:** exact user content preserved
- **CAMERA:** physical placement + framing + spatial behavior
- **LIGHT:** source + direction + contrast behavior
- **COLOR/MATERIALS:** object-level palette + tactile surfaces
- **ENVIRONMENT:** style-specific spatial/production-design logic
- **CHARACTER/ACTION:** posture + gaze + expression + movement
- **CORE ANCHORS:** all five represented in the prompt
- **ANTI-DRIFT:** Avoid-rule conflicts removed
- **FINAL PROMPT:** one integrated generation instruction


## Style Fidelity Gate
**Pass threshold:** average fidelity score >= **8.0/10**, Signature Fidelity >= **8.0**, Content Preservation >= **9.0**, and no other dimension below **7.5**.

### Profile-specific signature test
- Anchor 1: Frontal or profile staging dominates; diagonal naturalism is reduced.
- Anchor 2: Strong bilateral symmetry or deliberately balanced asymmetry.
- Anchor 3: Centered subjects, repeated rectangles, shelves, doorways, windows, elevators, desks, and facades.
- Anchor 4: Camera movement tends to be rectilinear: horizontal track, vertical move, 90-degree turn, snap zoom.
- Anchor 5: Production design and costume are color-planned as a unified system.

The image fails signature fidelity if fewer than four anchors are clearly visible.

### Score after generation
Score **Content Preservation, Camera/Composition, Lens/Space, Lighting, Color/Materials, Environment/Texture, Character/Action, and Signature Fidelity** from 0-10 using the global Fidelity Gate.

### Correction rule
If any passing condition fails, write a repair delta only for the failed dimensions, preserve successful dimensions, and regenerate. Run no more than two automatic repair cycles. Do not respond to failure by making the image generically "more cinematic."


### Research traceability record
**Traceability confidence:** HIGH

**Evidence-use instruction:** Use these anchors to support the visual rules above. Do not infer unsupported technical specifications.

- [TECH-1] *American Cinematographer* — *Moonrise Kingdom*: formal centered compositions, wide lenses, snap zooms, and theatrical staging.
- [TECH-1] Motion Picture Association / cinematography interviews: extensive palette, prop, and composition planning.
- [TECH-1] Kodak interviews on *The French Dispatch* and *Asteroid City*: aspect-ratio changes and full-width ensemble composition.

---

# 05. SOCIAL DREAD REALISM
**Style ID:** CIS-05  
**Research Lineage:** Jordan Peele  
**Representative works studied:** *Get Out*, *Us*, *Nope*

## Research synthesis
The system begins with **credible ordinary reality and slowly reveals that the geometry, color, or negative space is wrong**. *Get Out* was intentionally grounded rather than photographed as overt horror; warmer estate imagery can create false comfort, while cooler/cyan-green nocturnal passages carry threat. *Nope* expands the grammar into enormous readable landscapes and a spectacle that remains anchored in observation. Across the films, ordinary domestic or commercial spaces, carefully placed negative space, central sightlines, doubles, thresholds, and hidden observers turn social unease into visual structure.

## Persistent visual invariants
- Begin from realistic, recognizable spaces and plausible light.
- Hide threat in negative space, background depth, windows, doorways, darkness, sky, or apparently harmless symmetry.
- Use social arrangement itself as suspense: who sits where, who watches whom, who is isolated.
- Pleasant color and warm light may conceal danger rather than signal safety.
- Strong visual symbols are embedded in ordinary objects and architecture.
- Wide environmental shots preserve enough information for the viewer to scan for threat.
- Darkness is spatial, not just underexposure: a void can become a psychological place.
- Spectacle remains connected to a human observer and a readable physical environment.

## AI image-construction rules
### Composition
Create a normal-looking scene with one structurally disturbing relationship. Put extra empty space where the viewer expects nothing. Use centered corridors, windows, doorways, lawns, parking lots, theaters, living rooms, roads, or open sky as visual traps. Keep backgrounds legible enough that the viewer searches them.

### Lighting
Ground the scene in natural or practical sources. Warm daylight or domestic tungsten may be falsely comforting. Night can use cyan, green, aqua, or moonlit separation, but retain environmental readability instead of crushing everything to black.

### Color
Assign palette to social function: comfort, false hospitality, institutional control, spectacle, or danger. Avoid generic horror red/black unless the scene earns it.

### Symbolic object rule
Include 1-2 ordinary objects that carry narrative pressure: cup, camera, scissors, tether, door, television, balloon, animal, or repeated shape. The symbol should belong naturally in the world.

### Character direction
Favor watchfulness, polite discomfort, suppressed panic, uncanny calm, fixed smiles, or a person realizing the social rules are not what they appeared to be.

### Avoid
- immediate monster-movie lighting
- random gore as the main source of fear
- over-fogging
- empty darkness with no spatial design
- surreal filters that announce the twist too early
- spectacle with no observing human point of view

## AI Deployment Block
**SOCIAL DREAD REALISM / CIS-05:** Start with believable ordinary reality, then make one spatial, social, or symbolic relationship feel subtly wrong. Use plausible light, readable backgrounds, purposeful negative space, thresholds, windows, centered sightlines, doubles, and ordinary objects that acquire pressure. Warmth may conceal danger; night should retain spatial information. Keep spectacle tied to a human observer. Build fear from who is watching, where people are placed, what is missing, and what occupies the background rather than from generic horror color, fog, or gore.

## Style Compiler
**Compiler role:** Convert any user subject into this visual system without changing the user's required content.

### Five non-negotiable visual anchors
1. Begin from realistic, recognizable spaces and plausible light.
2. Hide threat in negative space, background depth, windows, doorways, darkness, sky, or apparently harmless symmetry.
3. Use social arrangement itself as suspense: who sits where, who watches whom, who is isolated.
4. Pleasant color and warm light may conceal danger rather than signal safety.
5. Strong visual symbols are embedded in ordinary objects and architecture.

**Minimum visibility rule:** At least four of these five anchors must be visibly present in the generated image. All five should be encoded in the prompt unless a locked user requirement conflicts.

### Style-specific compilation sequence
1. **Lock the subject.** Preserve every user-required identity/species/object, clothing item, color, prop, action, and setting constraint.
2. **Establish the visual premise.** Use the logic of **SOCIAL DREAD REALISM / CIS-05** rather than adding generic cinematic adjectives. The deployment block above is the governing summary.
3. **Compile camera + composition.** Translate the profile's camera/composition rules into one explicit camera location, distance, framing, spatial behavior, and foreground/background relationship.
4. **Compile light.** Name the physical or psychological source, direction, hardness/softness, contrast behavior, and what it does to faces/materials.
5. **Compile color + materials.** Put the style palette into actual objects, surfaces, weather, wardrobe, architecture, practical light, landscape, skin, or props before using global grading language.
6. **Compile environment.** Make the space carry the style through architecture, geography, social context, production design, weather, and tactile material behavior.
7. **Compile character/action direction.** Specify posture, gaze, expression, movement, and emotional temperature so the subject participates in the visual grammar rather than merely standing inside it.
8. **Enforce the five anchors.** Check the prompt line-by-line and add any missing core anchor in concrete visual form.
9. **Run the anti-drift filter.** Reject or rewrite these failure modes: immediate monster-movie lighting; random gore as the main source of fear; over-fogging; empty darkness with no spatial design; surreal filters that announce the twist too early; spectacle with no observing human point of view.
10. **Assemble one causal prompt.** The final instruction must read like a photographable scene, not a bag of adjectives.

### Compiled output checklist
- **STYLE:** SOCIAL DREAD REALISM / CIS-05
- **SUBJECT LOCK:** exact user content preserved
- **CAMERA:** physical placement + framing + spatial behavior
- **LIGHT:** source + direction + contrast behavior
- **COLOR/MATERIALS:** object-level palette + tactile surfaces
- **ENVIRONMENT:** style-specific spatial/production-design logic
- **CHARACTER/ACTION:** posture + gaze + expression + movement
- **CORE ANCHORS:** all five represented in the prompt
- **ANTI-DRIFT:** Avoid-rule conflicts removed
- **FINAL PROMPT:** one integrated generation instruction


## Style Fidelity Gate
**Pass threshold:** average fidelity score >= **8.0/10**, Signature Fidelity >= **8.0**, Content Preservation >= **9.0**, and no other dimension below **7.5**.

### Profile-specific signature test
- Anchor 1: Begin from realistic, recognizable spaces and plausible light.
- Anchor 2: Hide threat in negative space, background depth, windows, doorways, darkness, sky, or apparently harmless symmetry.
- Anchor 3: Use social arrangement itself as suspense: who sits where, who watches whom, who is isolated.
- Anchor 4: Pleasant color and warm light may conceal danger rather than signal safety.
- Anchor 5: Strong visual symbols are embedded in ordinary objects and architecture.

The image fails signature fidelity if fewer than four anchors are clearly visible.

### Score after generation
Score **Content Preservation, Camera/Composition, Lens/Space, Lighting, Color/Materials, Environment/Texture, Character/Action, and Signature Fidelity** from 0-10 using the global Fidelity Gate.

### Correction rule
If any passing condition fails, write a repair delta only for the failed dimensions, preserve successful dimensions, and regenerate. Run no more than two automatic repair cycles. Do not respond to failure by making the image generically "more cinematic."


### Research traceability record
**Traceability confidence:** HIGH

**Evidence-use instruction:** Use these anchors to support the visual rules above. Do not infer unsupported technical specifications.

- [TECH-1] *American Cinematographer* — *Get Out*: grounded photography, warm/cool location strategy, cyan-green night work.
- [TECH-1] *Filmmaker Magazine* — *Get Out*: construction of the Sunken Place and visualizing black void/observation.
- [TECH-1] Kodak / cinematography coverage of *Nope*: 65mm/IMAX, readable night landscape, day-for-night methodology, and large-scale observation.

---

# 06. PULP DEEP-FRAME CINEMA
**Style ID:** CIS-06  
**Research Lineage:** Quentin Tarantino  
**Representative works studied:** *Pulp Fiction*, *Jackie Brown*, *Kill Bill*, *Inglourious Basterds*, *The Hateful Eight*, *Once Upon a Time in Hollywood*

## Research synthesis
The image language mixes **classic widescreen staging, cinephile genre grammar, deep foreground/background relationships, period texture, sudden graphic emphasis, and unapologetically theatrical visual punctuation**. Tarantino and his cinematographers often favor wider anamorphic focal lengths that keep characters related to the room rather than separating them with long-lens blur. Long conversational sequences are staged for spatial tension; then a snap zoom, trunk-low angle, overhead, extreme close insert, or sudden violent graphic event breaks the equilibrium. Film stock, period color, and diegetic media formats are part of the pleasure.

## Persistent visual invariants
- Wide-lens ensemble staging with readable room geography.
- Characters and background remain relational; avoid flattening everyone against bokeh.
- Long dialogue scenes create visual tension through blocking and eyelines.
- Bold punctuation devices: rapid zoom, low trunk-like angle, overhead, profile two-shot, extreme detail insert.
- Genre references can alter palette, framing, or format within one project.
- Film texture and period-specific color are valued.
- Lighting may be broad and classical, with strong overhead or practical motivation.
- Violence, when it arrives, is often graphically abrupt rather than continuously chaotic.

## AI image-construction rules
### Composition
Favor two-shots, three-shots, table scenes, booth scenes, car interiors, hallways, rooms with doorways, and low-angle group staging. Preserve foreground/background relationships. Let props on tables, weapons, food, signage, cigarettes, records, or period objects participate in the composition.

### Lens
Use wide-to-normal anamorphic feeling. Keep the environment present. Allow close focus without making the background disappear entirely.

### Color and finish
Choose a period/genre palette: warm Technicolor richness, faded 1970s earth tones, saturated pulp primaries, cold war-movie gray, or dusty western warmth. Tie palette to the scene's genre logic rather than applying all at once. Preserve film grain and halation subtly.

### Visual punctuation
For a still image, imply the moment just before or just after a dramatic punctuation: a sudden glance, weapon entering frame, hand reaching, door opening, object on table, or low-angle reveal.

### Avoid
- generic contemporary action grading
- telephoto separation that destroys ensemble geometry
- constant visual hysteria
- meaningless retro props
- gratuitous gore without scene tension
- copying one iconic composition as a template for every image

## AI Deployment Block
**PULP DEEP-FRAME CINEMA / CIS-06:** Stage people in a readable widescreen environment using wide-to-normal perspective, strong foreground/background relationships, and tension-rich blocking. Let dialogue, eyelines, props, tables, cars, doorways, and group geometry carry the image. Use film-like period color chosen for the scene's genre, then punctuate otherwise controlled staging with one bold device: a low reveal, rapid-zoom feeling, overhead, extreme insert, or sudden graphic intrusion. Avoid generic action grading, telephoto bokeh isolation, empty retro decoration, and nonstop chaos.

## Style Compiler
**Compiler role:** Convert any user subject into this visual system without changing the user's required content.

### Five non-negotiable visual anchors
1. Wide-lens ensemble staging with readable room geography.
2. Characters and background remain relational; avoid flattening everyone against bokeh.
3. Long dialogue scenes create visual tension through blocking and eyelines.
4. Bold punctuation devices: rapid zoom, low trunk-like angle, overhead, profile two-shot, extreme detail insert.
5. Genre references can alter palette, framing, or format within one project.

**Minimum visibility rule:** At least four of these five anchors must be visibly present in the generated image. All five should be encoded in the prompt unless a locked user requirement conflicts.

### Style-specific compilation sequence
1. **Lock the subject.** Preserve every user-required identity/species/object, clothing item, color, prop, action, and setting constraint.
2. **Establish the visual premise.** Use the logic of **PULP DEEP-FRAME CINEMA / CIS-06** rather than adding generic cinematic adjectives. The deployment block above is the governing summary.
3. **Compile camera + composition.** Translate the profile's camera/composition rules into one explicit camera location, distance, framing, spatial behavior, and foreground/background relationship.
4. **Compile light.** Name the physical or psychological source, direction, hardness/softness, contrast behavior, and what it does to faces/materials.
5. **Compile color + materials.** Put the style palette into actual objects, surfaces, weather, wardrobe, architecture, practical light, landscape, skin, or props before using global grading language.
6. **Compile environment.** Make the space carry the style through architecture, geography, social context, production design, weather, and tactile material behavior.
7. **Compile character/action direction.** Specify posture, gaze, expression, movement, and emotional temperature so the subject participates in the visual grammar rather than merely standing inside it.
8. **Enforce the five anchors.** Check the prompt line-by-line and add any missing core anchor in concrete visual form.
9. **Run the anti-drift filter.** Reject or rewrite these failure modes: generic contemporary action grading; telephoto separation that destroys ensemble geometry; constant visual hysteria; meaningless retro props; gratuitous gore without scene tension; copying one iconic composition as a template for every image.
10. **Assemble one causal prompt.** The final instruction must read like a photographable scene, not a bag of adjectives.

### Compiled output checklist
- **STYLE:** PULP DEEP-FRAME CINEMA / CIS-06
- **SUBJECT LOCK:** exact user content preserved
- **CAMERA:** physical placement + framing + spatial behavior
- **LIGHT:** source + direction + contrast behavior
- **COLOR/MATERIALS:** object-level palette + tactile surfaces
- **ENVIRONMENT:** style-specific spatial/production-design logic
- **CHARACTER/ACTION:** posture + gaze + expression + movement
- **CORE ANCHORS:** all five represented in the prompt
- **ANTI-DRIFT:** Avoid-rule conflicts removed
- **FINAL PROMPT:** one integrated generation instruction


## Style Fidelity Gate
**Pass threshold:** average fidelity score >= **8.0/10**, Signature Fidelity >= **8.0**, Content Preservation >= **9.0**, and no other dimension below **7.5**.

### Profile-specific signature test
- Anchor 1: Wide-lens ensemble staging with readable room geography.
- Anchor 2: Characters and background remain relational; avoid flattening everyone against bokeh.
- Anchor 3: Long dialogue scenes create visual tension through blocking and eyelines.
- Anchor 4: Bold punctuation devices: rapid zoom, low trunk-like angle, overhead, profile two-shot, extreme detail insert.
- Anchor 5: Genre references can alter palette, framing, or format within one project.

The image fails signature fidelity if fewer than four anchors are clearly visible.

### Score after generation
Score **Content Preservation, Camera/Composition, Lens/Space, Lighting, Color/Materials, Environment/Texture, Character/Action, and Signature Fidelity** from 0-10 using the global Fidelity Gate.

### Correction rule
If any passing condition fails, write a repair delta only for the failed dimensions, preserve successful dimensions, and regenerate. Run no more than two automatic repair cycles. Do not respond to failure by making the image generically "more cinematic."


### Research traceability record
**Traceability confidence:** HIGH

**Evidence-use instruction:** Use these anchors to support the visual rules above. Do not infer unsupported technical specifications.

- [TECH-1] *American Cinematographer* interviews on Tarantino productions: preference for wider anamorphic focal lengths, full spatial relationships, and photochemical acquisition.
- [TECH-1] Kodak / cinematography coverage of *Once Upon a Time in Hollywood*: period film texture, zoom language, format shifts, and rich dye-transfer-inspired color.

---

# 07. RADIANT INTERIORISM
**Style ID:** CIS-07  
**Research Lineage:** Barry Jenkins  
**Representative works studied:** *Medicine for Melancholy*, *Moonlight*, *If Beale Street Could Talk*, *The Underground Railroad*

## Research synthesis
The durable signature is not one palette. It is **camera-as-emotional-participant**: close human proximity, luminous skin, direct or nearly direct eye contact, subjective movement, tactile environments, and color chosen according to the emotional world of the specific story. Research on *Moonlight* emphasizes imagery rising from character rather than being imposed on character. *Beale Street* becomes more precise, patient, and warm than *Moonlight*, yet retains direct-to-lens intimacy and a camera that seems to enter the conversation instead of observing from a safe distance.

## Persistent visual invariants
- The camera is emotionally attached to the character.
- Dark skin is rendered as luminous, dimensional, and chromatically alive.
- Direct-to-lens or near-lens portraiture can create intense viewer intimacy.
- Movement often circles, follows, or gently floats with characters.
- Color is expressive but story-specific rather than fixed.
- Small sensory details — hands, faces, water, fabric, street light, food, breath — carry emotional memory.
- Intimacy can coexist with vivid environmental color.
- The image seeks tenderness without becoming visually bland.

## AI image-construction rules
### Portraiture
Place the lens physically close enough that the viewer feels present in the conversation. Use eye-level portraiture and allow direct gaze when emotional connection is the point. Protect nuanced skin highlights and color variation.

### Movement translated to stills
Use subtle rotational energy, foreground drift, or a background that suggests the camera has arrived inside a moving emotional moment. Avoid frozen fashion posing.

### Color
Choose an emotionally coherent palette for the story: tropical blues/greens, warm amber/cream, saturated street color, deep night, or period warmth. Color should support memory and feeling, not merely identify the system.

### Lighting
Favor soft directional sources, natural daylight, warm practicals, neon or street sources when geographically appropriate. Let highlights caress skin rather than bleach it.

### Depth
Moderate shallow focus is acceptable, but retain enough place to sense the character's world. Let bokeh become atmosphere, not erasure.

### Avoid
- beauty-ad glamour
- monochrome desaturation as a shortcut for seriousness
- flattening skin tones
- emotionally distant long-lens voyeurism
- assigning one famous palette to every scene

## AI Deployment Block
**RADIANT INTERIORISM / CIS-07:** Place the camera emotionally inside the character's experience. Work close to faces, preserve luminous dimensional skin, allow direct or near-direct eye contact, and use gentle attached movement or implied movement rather than detached observation. Build an expressive palette specific to the story and place; let color, practical light, water, fabric, street glow, and small sensory details carry memory. Keep portraits tender, psychologically present, and tactile. Avoid generic desaturation, cosmetic glamour, distant telephoto voyeurism, and one fixed color recipe.

## Style Compiler
**Compiler role:** Convert any user subject into this visual system without changing the user's required content.

### Five non-negotiable visual anchors
1. The camera is emotionally attached to the character.
2. Dark skin is rendered as luminous, dimensional, and chromatically alive.
3. Direct-to-lens or near-lens portraiture can create intense viewer intimacy.
4. Movement often circles, follows, or gently floats with characters.
5. Color is expressive but story-specific rather than fixed.

**Minimum visibility rule:** At least four of these five anchors must be visibly present in the generated image. All five should be encoded in the prompt unless a locked user requirement conflicts.

### Style-specific compilation sequence
1. **Lock the subject.** Preserve every user-required identity/species/object, clothing item, color, prop, action, and setting constraint.
2. **Establish the visual premise.** Use the logic of **RADIANT INTERIORISM / CIS-07** rather than adding generic cinematic adjectives. The deployment block above is the governing summary.
3. **Compile camera + composition.** Translate the profile's camera/composition rules into one explicit camera location, distance, framing, spatial behavior, and foreground/background relationship.
4. **Compile light.** Name the physical or psychological source, direction, hardness/softness, contrast behavior, and what it does to faces/materials.
5. **Compile color + materials.** Put the style palette into actual objects, surfaces, weather, wardrobe, architecture, practical light, landscape, skin, or props before using global grading language.
6. **Compile environment.** Make the space carry the style through architecture, geography, social context, production design, weather, and tactile material behavior.
7. **Compile character/action direction.** Specify posture, gaze, expression, movement, and emotional temperature so the subject participates in the visual grammar rather than merely standing inside it.
8. **Enforce the five anchors.** Check the prompt line-by-line and add any missing core anchor in concrete visual form.
9. **Run the anti-drift filter.** Reject or rewrite these failure modes: beauty-ad glamour; monochrome desaturation as a shortcut for seriousness; flattening skin tones; emotionally distant long-lens voyeurism; assigning one famous palette to every scene.
10. **Assemble one causal prompt.** The final instruction must read like a photographable scene, not a bag of adjectives.

### Compiled output checklist
- **STYLE:** RADIANT INTERIORISM / CIS-07
- **SUBJECT LOCK:** exact user content preserved
- **CAMERA:** physical placement + framing + spatial behavior
- **LIGHT:** source + direction + contrast behavior
- **COLOR/MATERIALS:** object-level palette + tactile surfaces
- **ENVIRONMENT:** style-specific spatial/production-design logic
- **CHARACTER/ACTION:** posture + gaze + expression + movement
- **CORE ANCHORS:** all five represented in the prompt
- **ANTI-DRIFT:** Avoid-rule conflicts removed
- **FINAL PROMPT:** one integrated generation instruction


## Style Fidelity Gate
**Pass threshold:** average fidelity score >= **8.0/10**, Signature Fidelity >= **8.0**, Content Preservation >= **9.0**, and no other dimension below **7.5**.

### Profile-specific signature test
- Anchor 1: The camera is emotionally attached to the character.
- Anchor 2: Dark skin is rendered as luminous, dimensional, and chromatically alive.
- Anchor 3: Direct-to-lens or near-lens portraiture can create intense viewer intimacy.
- Anchor 4: Movement often circles, follows, or gently floats with characters.
- Anchor 5: Color is expressive but story-specific rather than fixed.

The image fails signature fidelity if fewer than four anchors are clearly visible.

### Score after generation
Score **Content Preservation, Camera/Composition, Lens/Space, Lighting, Color/Materials, Environment/Texture, Character/Action, and Signature Fidelity** from 0-10 using the global Fidelity Gate.

### Correction rule
If any passing condition fails, write a repair delta only for the failed dimensions, preserve successful dimensions, and regenerate. Run no more than two automatic repair cycles. Do not respond to failure by making the image generically "more cinematic."


### Research traceability record
**Traceability confidence:** HIGH

**Evidence-use instruction:** Use these anchors to support the visual rules above. Do not infer unsupported technical specifications.

- [INST-2] BFI / cinematography analysis of *Moonlight*: character-led imagery, portraiture, skin rendering, and attached camera movement.
- [TECH-1] *Filmmaker Magazine* and Bradford Young/James Laxton discussions of *If Beale Street Could Talk*: precise patient camera, warmth, direct-to-lens intimacy, and emotional perspective.

---

# 08. CHROMATIC GOTHIC HUMANISM
**Style ID:** CIS-08  
**Research Lineage:** Guillermo del Toro  
**Representative works studied:** *The Devil's Backbone*, *Pan's Labyrinth*, *Crimson Peak*, *The Shape of Water*, *Nightmare Alley*

## Research synthesis
The recurring image grammar combines **baroque tactile production design, emotionally coded color, gothic darkness, fluid revealing camera movement, and deep sympathy for the creature/outcast**. Color is highly intentional: steel blues and aquatic greens may define one world; amber, red, or gold another. Environments are dense with curved architecture, worn metal, wood, wallpaper, pipes, water, books, clocks, insects, religious or mythic motifs, and practical sources. The fantastical is materially built and photographed as part of the same world as the human characters.

## Persistent visual invariants
- Color separates emotional or moral worlds.
- Gothic darkness is paired with luminous pockets of practical light.
- Sets are dense, tactile, and story-bearing rather than generic fantasy decoration.
- Curves, circles, arches, windows, portholes, machinery, stairs, roots, and organic shapes recur.
- Camera movement often glides to reveal information or connect characters to architecture.
- Creatures and outsiders are photographed with empathy and physical detail.
- Moisture, smoke, dust, rain, blood, rust, wax, fog, or water provide tangible atmosphere.
- Warm/cool opposition is often embedded in production design before grading.

## AI image-construction rules
### Environment
Build a complete material world. Use aged brass, tile, stone, wet concrete, dark wood, wallpaper, laboratory glass, iron, velvet, books, mechanical parts, roots, or water depending on setting. Nothing should look like a generic fantasy asset pack.

### Color
Choose two emotionally meaningful color families and let them occupy real objects and light sources. Example: blue-green institutional world versus amber-red intimate refuge. Keep the opposition deliberate.

### Lighting
Use pools of motivated light within darkness: lamps, windows, fire, water reflections, laboratory fixtures, moonlight. Allow rich blacks but preserve tactile edges and silhouettes.

### Composition and movement
Use arches, doorways, circular motifs, layers, foreground objects, and gliding reveal logic. Even in a still, suggest that the viewer has just discovered something through a threshold.

### Creature direction
Treat nonhuman subjects as living beings with weight, skin/material texture, posture, vulnerability, and emotional presence — not as disposable monsters.

### Avoid
- generic Halloween gothic
- purple/green fantasy lighting with no story logic
- clean plastic CGI surfaces
- empty fog
- clutter that does not reveal character or mythology
- creatures lit only to look frightening

## AI Deployment Block
**CHROMATIC GOTHIC HUMANISM / CIS-08:** Build a tactile gothic world whose materials, architecture, practical light, and color carry emotional meaning. Use dense but purposeful production design, arches and circular motifs, moisture/smoke/water texture, rich darkness with luminous motivated sources, and a controlled warm/cool color opposition embedded in the set itself. Let the camera feel as though it is revealing a secret through layers or thresholds. Photograph creatures and outsiders with physical weight and empathy. Avoid generic Halloween color, plastic CGI, meaningless fog, and decorative clutter.

## Style Compiler
**Compiler role:** Convert any user subject into this visual system without changing the user's required content.

### Five non-negotiable visual anchors
1. Color separates emotional or moral worlds.
2. Gothic darkness is paired with luminous pockets of practical light.
3. Sets are dense, tactile, and story-bearing rather than generic fantasy decoration.
4. Curves, circles, arches, windows, portholes, machinery, stairs, roots, and organic shapes recur.
5. Camera movement often glides to reveal information or connect characters to architecture.

**Minimum visibility rule:** At least four of these five anchors must be visibly present in the generated image. All five should be encoded in the prompt unless a locked user requirement conflicts.

### Style-specific compilation sequence
1. **Lock the subject.** Preserve every user-required identity/species/object, clothing item, color, prop, action, and setting constraint.
2. **Establish the visual premise.** Use the logic of **CHROMATIC GOTHIC HUMANISM / CIS-08** rather than adding generic cinematic adjectives. The deployment block above is the governing summary.
3. **Compile camera + composition.** Translate the profile's camera/composition rules into one explicit camera location, distance, framing, spatial behavior, and foreground/background relationship.
4. **Compile light.** Name the physical or psychological source, direction, hardness/softness, contrast behavior, and what it does to faces/materials.
5. **Compile color + materials.** Put the style palette into actual objects, surfaces, weather, wardrobe, architecture, practical light, landscape, skin, or props before using global grading language.
6. **Compile environment.** Make the space carry the style through architecture, geography, social context, production design, weather, and tactile material behavior.
7. **Compile character/action direction.** Specify posture, gaze, expression, movement, and emotional temperature so the subject participates in the visual grammar rather than merely standing inside it.
8. **Enforce the five anchors.** Check the prompt line-by-line and add any missing core anchor in concrete visual form.
9. **Run the anti-drift filter.** Reject or rewrite these failure modes: generic Halloween gothic; purple/green fantasy lighting with no story logic; clean plastic CGI surfaces; empty fog; clutter that does not reveal character or mythology; creatures lit only to look frightening.
10. **Assemble one causal prompt.** The final instruction must read like a photographable scene, not a bag of adjectives.

### Compiled output checklist
- **STYLE:** CHROMATIC GOTHIC HUMANISM / CIS-08
- **SUBJECT LOCK:** exact user content preserved
- **CAMERA:** physical placement + framing + spatial behavior
- **LIGHT:** source + direction + contrast behavior
- **COLOR/MATERIALS:** object-level palette + tactile surfaces
- **ENVIRONMENT:** style-specific spatial/production-design logic
- **CHARACTER/ACTION:** posture + gaze + expression + movement
- **CORE ANCHORS:** all five represented in the prompt
- **ANTI-DRIFT:** Avoid-rule conflicts removed
- **FINAL PROMPT:** one integrated generation instruction


## Style Fidelity Gate
**Pass threshold:** average fidelity score >= **8.0/10**, Signature Fidelity >= **8.0**, Content Preservation >= **9.0**, and no other dimension below **7.5**.

### Profile-specific signature test
- Anchor 1: Color separates emotional or moral worlds.
- Anchor 2: Gothic darkness is paired with luminous pockets of practical light.
- Anchor 3: Sets are dense, tactile, and story-bearing rather than generic fantasy decoration.
- Anchor 4: Curves, circles, arches, windows, portholes, machinery, stairs, roots, and organic shapes recur.
- Anchor 5: Camera movement often glides to reveal information or connect characters to architecture.

The image fails signature fidelity if fewer than four anchors are clearly visible.

### Score after generation
Score **Content Preservation, Camera/Composition, Lens/Space, Lighting, Color/Materials, Environment/Texture, Character/Action, and Signature Fidelity** from 0-10 using the global Fidelity Gate.

### Correction rule
If any passing condition fails, write a repair delta only for the failed dimensions, preserve successful dimensions, and regenerate. Run no more than two automatic repair cycles. Do not respond to failure by making the image generically "more cinematic."


### Research traceability record
**Traceability confidence:** MEDIUM-HIGH

**Evidence-use instruction:** Use these anchors to support the visual rules above. Do not infer unsupported technical specifications.

- [TECH-1] *Filmmaker Magazine* / cinematography discussion of *The Shape of Water*: steel blue/green world, warm and red emotional accents, precise color design.
- [CRIT-4] Comparative frame analysis across *Pan's Labyrinth*, *Crimson Peak*, *The Shape of Water*, and *Nightmare Alley*.

---

# 09. INTIMATE EPIC REALISM
**Style ID:** CIS-09  
**Research Lineage:** Ryan Coogler  
**Representative works studied:** *Fruitvale Station*, *Creed*, *Black Panther*, *Black Panther: Wakanda Forever*, *Sinners*

## Research synthesis
The core is **epic scope kept emotionally tethered to human bodies, family, community, and cultural specificity**. Research around *Black Panther* emphasizes the desire to keep backgrounds readable enough to appreciate sets, costumes, and world-building while still achieving intimate eyelines and subjective character perspective. Coogler's roots in smaller-scale realist work remain visible in the way cameras stay physically close to people even inside spectacle. Action is allowed to become large, but the viewer should know whose emotional experience organizes the frame.

## Persistent visual invariants
- Character intimacy survives inside large-scale world-building.
- Background design remains readable rather than dissolving into blur.
- Tight eyelines make conversations feel physically immediate.
- Culturally specific costume, architecture, hair, ritual, color, and landscape are treated as essential visual information.
- Camera movement follows bodies and relationships rather than showing off technology.
- Action geography remains connected to the protagonist's emotional goal.
- Documentary/handheld energy can coexist with polished epic imagery.
- Faces, family structures, and community carry as much weight as spectacle.

## AI image-construction rules
### Composition
Place the subject close enough to feel human, but keep enough environment visible to understand culture and scale. Use medium wides, close two-shots, low/eye-level hero frames, and group compositions with readable costume/environment detail.

### Lens and depth
Favor normal-to-wide proximity and moderate depth. Do not erase the designed world behind the actor.

### Lighting/color
Let skin, costume, metals, textiles, landscape, and architecture contribute to a rich but coherent palette. Use sunlight, fire, practical interiors, arena light, street light, or landscape color as plausible sources.

### Action
Show body mechanics and spatial purpose. Even a huge action image should reveal who is protecting, pursuing, resisting, grieving, or deciding.

### Cultural design rule
Never substitute generic 'African,' 'urban,' 'boxing,' or 'superhero' shorthand for specific material detail. Build a coherent cultural visual system from costume, pattern, architecture, hairstyle, tools, landscape, and ritual appropriate to the fictional world.

### Avoid
- anonymous blockbuster spectacle
- background-erasing bokeh
- generic tribal/futurist collage
- emotionless hero posing
- action without relationship stakes

## AI Deployment Block
**INTIMATE EPIC REALISM / CIS-09:** Keep the camera emotionally and physically close to people even when the world is enormous. Preserve readable background design, costume, architecture, cultural detail, and group relationships. Use tight eyelines, moderate depth, human-scale lens proximity, grounded movement, and action organized around an emotional objective. Let culturally specific materials and color build the world instead of generic genre shorthand. Avoid anonymous blockbuster scale, erased backgrounds, empty hero poses, and spectacle without family, community, or character stakes.

## Style Compiler
**Compiler role:** Convert any user subject into this visual system without changing the user's required content.

### Five non-negotiable visual anchors
1. Character intimacy survives inside large-scale world-building.
2. Background design remains readable rather than dissolving into blur.
3. Tight eyelines make conversations feel physically immediate.
4. Culturally specific costume, architecture, hair, ritual, color, and landscape are treated as essential visual information.
5. Camera movement follows bodies and relationships rather than showing off technology.

**Minimum visibility rule:** At least four of these five anchors must be visibly present in the generated image. All five should be encoded in the prompt unless a locked user requirement conflicts.

### Style-specific compilation sequence
1. **Lock the subject.** Preserve every user-required identity/species/object, clothing item, color, prop, action, and setting constraint.
2. **Establish the visual premise.** Use the logic of **INTIMATE EPIC REALISM / CIS-09** rather than adding generic cinematic adjectives. The deployment block above is the governing summary.
3. **Compile camera + composition.** Translate the profile's camera/composition rules into one explicit camera location, distance, framing, spatial behavior, and foreground/background relationship.
4. **Compile light.** Name the physical or psychological source, direction, hardness/softness, contrast behavior, and what it does to faces/materials.
5. **Compile color + materials.** Put the style palette into actual objects, surfaces, weather, wardrobe, architecture, practical light, landscape, skin, or props before using global grading language.
6. **Compile environment.** Make the space carry the style through architecture, geography, social context, production design, weather, and tactile material behavior.
7. **Compile character/action direction.** Specify posture, gaze, expression, movement, and emotional temperature so the subject participates in the visual grammar rather than merely standing inside it.
8. **Enforce the five anchors.** Check the prompt line-by-line and add any missing core anchor in concrete visual form.
9. **Run the anti-drift filter.** Reject or rewrite these failure modes: anonymous blockbuster spectacle; background-erasing bokeh; generic tribal/futurist collage; emotionless hero posing; action without relationship stakes.
10. **Assemble one causal prompt.** The final instruction must read like a photographable scene, not a bag of adjectives.

### Compiled output checklist
- **STYLE:** INTIMATE EPIC REALISM / CIS-09
- **SUBJECT LOCK:** exact user content preserved
- **CAMERA:** physical placement + framing + spatial behavior
- **LIGHT:** source + direction + contrast behavior
- **COLOR/MATERIALS:** object-level palette + tactile surfaces
- **ENVIRONMENT:** style-specific spatial/production-design logic
- **CHARACTER/ACTION:** posture + gaze + expression + movement
- **CORE ANCHORS:** all five represented in the prompt
- **ANTI-DRIFT:** Avoid-rule conflicts removed
- **FINAL PROMPT:** one integrated generation instruction


## Style Fidelity Gate
**Pass threshold:** average fidelity score >= **8.0/10**, Signature Fidelity >= **8.0**, Content Preservation >= **9.0**, and no other dimension below **7.5**.

### Profile-specific signature test
- Anchor 1: Character intimacy survives inside large-scale world-building.
- Anchor 2: Background design remains readable rather than dissolving into blur.
- Anchor 3: Tight eyelines make conversations feel physically immediate.
- Anchor 4: Culturally specific costume, architecture, hair, ritual, color, and landscape are treated as essential visual information.
- Anchor 5: Camera movement follows bodies and relationships rather than showing off technology.

The image fails signature fidelity if fewer than four anchors are clearly visible.

### Score after generation
Score **Content Preservation, Camera/Composition, Lens/Space, Lighting, Color/Materials, Environment/Texture, Character/Action, and Signature Fidelity** from 0-10 using the global Fidelity Gate.

### Correction rule
If any passing condition fails, write a repair delta only for the failed dimensions, preserve successful dimensions, and regenerate. Run no more than two automatic repair cycles. Do not respond to failure by making the image generically "more cinematic."


### Research traceability record
**Traceability confidence:** MEDIUM-HIGH

**Evidence-use instruction:** Use these anchors to support the visual rules above. Do not infer unsupported technical specifications.

- [TECH-1] *American Cinematographer* — *Black Panther*: readable sets/costumes, intimacy plus scope, tight eyelines, character-centered camera, and documentary-rooted immediacy.
- [CRIT-4] Comparative visual study of *Fruitvale Station*, *Creed*, and the *Black Panther* films.

---

# 10. LUMINOUS ISOLATION
**Style ID:** CIS-10  
**Research Lineage:** Sofia Coppola  
**Representative works studied:** *The Virgin Suicides*, *Lost in Translation*, *Marie Antoinette*, *The Beguiled*, *Priscilla*

## Research synthesis
The recurring grammar is **quiet subjective observation, feminine interiority, atmospheric available light, restrained camera behavior, and beauty used to make loneliness more palpable rather than to eliminate it**. *Lost in Translation* mixes hotel-window distance, Tokyo street immediacy, intimate close-ups, rain, reflections, and off-the-cuff observation. *The Beguiled* deliberately shifts from a pale, almost fairy-tale surface toward darker Gothic confinement, using a narrower frame and candlelit shadow. Across projects, the camera often refuses to move unless movement adds emotional value.

## Persistent visual invariants
- Beauty and isolation occupy the same frame.
- Windows, mirrors, curtains, beds, hotel rooms, cars, hallways, bedrooms, dressing rooms, and thresholds create emotional containment.
- Available or naturalistic light is favored over visibly 'cinematic' lighting.
- Camera movement is restrained; stillness is meaningful.
- Soft film texture, haze, reflections, flare, or low-contrast atmosphere may suggest memory and subjectivity.
- Negative space can make a person appear emotionally distant even in luxurious surroundings.
- Color is often delicate, pastel, desaturated, creamy, or period-specific, but can darken as confinement grows.
- Small gestures and private moments matter more than theatrical expression.

## AI image-construction rules
### Composition
Place the subject near a window, edge of bed, back seat, mirror, doorway, balcony, or large empty interior. Use negative space to show emotional disconnection. Allow off-center placement and partially obstructed views.

### Lighting
Use window light, soft overcast, practical lamps, candlelight, city glow, or morning/evening ambient light. Let exposure feel gentle and slightly imperfect. Do not add dramatic rim light just to make the image cinematic.

### Color/texture
Choose a restrained story palette: dusty pastel, cream, faded floral, warm hotel amber, cool urban blue, pale green, or period color. Preserve soft film grain and atmospheric highlights.

### Character direction
Favor boredom, contemplation, private curiosity, melancholy, quiet rebellion, or emotional drift. Avoid exaggerated crying or fashion-model intensity.

### Environment
Luxury should still feel emotionally empty when the story requires it. Ordinary rooms can feel intimate through light and texture rather than decorative excess.

### Avoid
- music-video glamour
- excessive camera drama
- saturated blockbuster color
- beauty lighting that removes vulnerability
- over-styled fashion posing
- mist/flares with no environmental source

## AI Deployment Block
**LUMINOUS ISOLATION / CIS-10:** Create quiet, intimate images in which beauty and loneliness coexist. Use restrained or static camera logic, natural/available light, windows, mirrors, beds, cars, hallways, curtains, and negative space to contain the subject emotionally. Favor soft film texture, gentle reflections, subdued story-specific color, and private gestures rather than theatrical expression. Let luxury remain lonely and ordinary rooms become poetic through light. Avoid glossy music-video glamour, aggressive camera angles, blockbuster saturation, and cosmetic lighting that erases vulnerability.

## Style Compiler
**Compiler role:** Convert any user subject into this visual system without changing the user's required content.

### Five non-negotiable visual anchors
1. Beauty and isolation occupy the same frame.
2. Windows, mirrors, curtains, beds, hotel rooms, cars, hallways, bedrooms, dressing rooms, and thresholds create emotional containment.
3. Available or naturalistic light is favored over visibly 'cinematic' lighting.
4. Camera movement is restrained; stillness is meaningful.
5. Soft film texture, haze, reflections, flare, or low-contrast atmosphere may suggest memory and subjectivity.

**Minimum visibility rule:** At least four of these five anchors must be visibly present in the generated image. All five should be encoded in the prompt unless a locked user requirement conflicts.

### Style-specific compilation sequence
1. **Lock the subject.** Preserve every user-required identity/species/object, clothing item, color, prop, action, and setting constraint.
2. **Establish the visual premise.** Use the logic of **LUMINOUS ISOLATION / CIS-10** rather than adding generic cinematic adjectives. The deployment block above is the governing summary.
3. **Compile camera + composition.** Translate the profile's camera/composition rules into one explicit camera location, distance, framing, spatial behavior, and foreground/background relationship.
4. **Compile light.** Name the physical or psychological source, direction, hardness/softness, contrast behavior, and what it does to faces/materials.
5. **Compile color + materials.** Put the style palette into actual objects, surfaces, weather, wardrobe, architecture, practical light, landscape, skin, or props before using global grading language.
6. **Compile environment.** Make the space carry the style through architecture, geography, social context, production design, weather, and tactile material behavior.
7. **Compile character/action direction.** Specify posture, gaze, expression, movement, and emotional temperature so the subject participates in the visual grammar rather than merely standing inside it.
8. **Enforce the five anchors.** Check the prompt line-by-line and add any missing core anchor in concrete visual form.
9. **Run the anti-drift filter.** Reject or rewrite these failure modes: music-video glamour; excessive camera drama; saturated blockbuster color; beauty lighting that removes vulnerability; over-styled fashion posing; mist/flares with no environmental source.
10. **Assemble one causal prompt.** The final instruction must read like a photographable scene, not a bag of adjectives.

### Compiled output checklist
- **STYLE:** LUMINOUS ISOLATION / CIS-10
- **SUBJECT LOCK:** exact user content preserved
- **CAMERA:** physical placement + framing + spatial behavior
- **LIGHT:** source + direction + contrast behavior
- **COLOR/MATERIALS:** object-level palette + tactile surfaces
- **ENVIRONMENT:** style-specific spatial/production-design logic
- **CHARACTER/ACTION:** posture + gaze + expression + movement
- **CORE ANCHORS:** all five represented in the prompt
- **ANTI-DRIFT:** Avoid-rule conflicts removed
- **FINAL PROMPT:** one integrated generation instruction


## Style Fidelity Gate
**Pass threshold:** average fidelity score >= **8.0/10**, Signature Fidelity >= **8.0**, Content Preservation >= **9.0**, and no other dimension below **7.5**.

### Profile-specific signature test
- Anchor 1: Beauty and isolation occupy the same frame.
- Anchor 2: Windows, mirrors, curtains, beds, hotel rooms, cars, hallways, bedrooms, dressing rooms, and thresholds create emotional containment.
- Anchor 3: Available or naturalistic light is favored over visibly 'cinematic' lighting.
- Anchor 4: Camera movement is restrained; stillness is meaningful.
- Anchor 5: Soft film texture, haze, reflections, flare, or low-contrast atmosphere may suggest memory and subjectivity.

The image fails signature fidelity if fewer than four anchors are clearly visible.

### Score after generation
Score **Content Preservation, Camera/Composition, Lens/Space, Lighting, Color/Materials, Environment/Texture, Character/Action, and Signature Fidelity** from 0-10 using the global Fidelity Gate.

### Correction rule
If any passing condition fails, write a repair delta only for the failed dimensions, preserve successful dimensions, and regenerate. Run no more than two automatic repair cycles. Do not respond to failure by making the image generically "more cinematic."


### Research traceability record
**Traceability confidence:** HIGH

**Evidence-use instruction:** Use these anchors to support the visual rules above. Do not infer unsupported technical specifications.

- [TECH-1] *Filmmaker Magazine* — *Lost in Translation*: off-the-cuff Tokyo observation, hotel windows, rain, close human moments.
- [TECH-1] Kodak / cinematography coverage of *The Beguiled*: pastel-to-Gothic palette evolution, candlelight, dark shadow, 1.66 confinement, and restrained camera movement.

---

# 11. TACTILE SEVERITY
**Style ID:** CIS-11  
**Research Lineage:** Steve McQueen  
**Representative works studied:** *Hunger*, *Shame*, *12 Years a Slave*, *Widows*, *Small Axe*

## Research synthesis
The recurring grammar is **formal rigor fused with bodily materiality**. McQueen's background in visual art appears not as decorative prettiness but as an ability to hold a severe composition long enough for physical reality to become unavoidable. Research around *Hunger* describes a form that changes according to the subject: controlled observational tableaux, extraordinarily extended static duration, and later lyrical or subjective passages. Across the work, bodies occupy oppressive systems — prisons, bedrooms, plantations, streets, institutions — and the camera often refuses easy emotional release. A beautifully composed image may contain pain, dirt, silence, or moral discomfort.

## Persistent visual invariants
- Strong, painterly compositions without sentimental beautification.
- Long-held observation and willingness to let duration become part of the image.
- Architecture can imprison, divide, expose, or dwarf the body.
- Physical textures — skin, sweat, blood, food, walls, rain, dirt, fabric — remain tangible.
- Negative space and stillness often increase moral pressure.
- Sudden lyrical or subjective imagery is used sparingly, therefore carries weight.
- Faces are often allowed to remain unreadable or emotionally contained.
- The camera can stay distant from suffering instead of forcing melodramatic close-ups.

## AI image-construction rules
### Composition
Use clean, severe geometry. Doorframes, walls, cells, corridors, windows, furniture, streets, and institutional architecture should organize the body. Let a human figure occupy only part of the frame when the system surrounding the person is the real pressure.

### Camera behavior
Favor stillness, restrained movement, and patient observation. In a still image, choose a moment that feels held rather than snatched. Avoid overly expressive camera angles unless the scene has crossed into a clearly subjective state.

### Lighting
Use source-based naturalism, often with substantial shadow. Light should reveal physical texture and spatial boundaries. Avoid soft glamour.

### Color
Keep palettes controlled and materially grounded: concrete, skin, dark fabric, institutional green, tobacco, earth, black, gray, off-white, or deep natural color. A strong accent should feel narratively earned.

### Physical detail
Let the viewer feel temperature and surfaces. Preserve sweat, pores, moisture, worn paint, scuffed flooring, textile fibers, smoke, or bodily fatigue.

### Avoid
- sentimental glow
- heroic posing
- melodramatic color grading
- excessive handheld agitation
- aestheticizing suffering into fashion
- cutting the environment away from the body

## AI Deployment Block
**TACTILE SEVERITY / CIS-11:** Use rigorous, patient composition and tangible physical detail. Let architecture, negative space, and stillness exert pressure on the human body. Favor source-based light, controlled color, tactile skin/material texture, restrained expression, and frames that can hold discomfort without decorating it. Allow lyrical subjectivity only as a rare contrast to severe observation. Avoid glamour, sentimental glow, fashionable suffering, constant camera agitation, and compositions that remove the person from the system surrounding them.

## Style Compiler
**Compiler role:** Convert any user subject into this visual system without changing the user's required content.

### Five non-negotiable visual anchors
1. Strong, painterly compositions without sentimental beautification.
2. Long-held observation and willingness to let duration become part of the image.
3. Architecture can imprison, divide, expose, or dwarf the body.
4. Physical textures — skin, sweat, blood, food, walls, rain, dirt, fabric — remain tangible.
5. Negative space and stillness often increase moral pressure.

**Minimum visibility rule:** At least four of these five anchors must be visibly present in the generated image. All five should be encoded in the prompt unless a locked user requirement conflicts.

### Style-specific compilation sequence
1. **Lock the subject.** Preserve every user-required identity/species/object, clothing item, color, prop, action, and setting constraint.
2. **Establish the visual premise.** Use the logic of **TACTILE SEVERITY / CIS-11** rather than adding generic cinematic adjectives. The deployment block above is the governing summary.
3. **Compile camera + composition.** Translate the profile's camera/composition rules into one explicit camera location, distance, framing, spatial behavior, and foreground/background relationship.
4. **Compile light.** Name the physical or psychological source, direction, hardness/softness, contrast behavior, and what it does to faces/materials.
5. **Compile color + materials.** Put the style palette into actual objects, surfaces, weather, wardrobe, architecture, practical light, landscape, skin, or props before using global grading language.
6. **Compile environment.** Make the space carry the style through architecture, geography, social context, production design, weather, and tactile material behavior.
7. **Compile character/action direction.** Specify posture, gaze, expression, movement, and emotional temperature so the subject participates in the visual grammar rather than merely standing inside it.
8. **Enforce the five anchors.** Check the prompt line-by-line and add any missing core anchor in concrete visual form.
9. **Run the anti-drift filter.** Reject or rewrite these failure modes: sentimental glow; heroic posing; melodramatic color grading; excessive handheld agitation; aestheticizing suffering into fashion; cutting the environment away from the body.
10. **Assemble one causal prompt.** The final instruction must read like a photographable scene, not a bag of adjectives.

### Compiled output checklist
- **STYLE:** TACTILE SEVERITY / CIS-11
- **SUBJECT LOCK:** exact user content preserved
- **CAMERA:** physical placement + framing + spatial behavior
- **LIGHT:** source + direction + contrast behavior
- **COLOR/MATERIALS:** object-level palette + tactile surfaces
- **ENVIRONMENT:** style-specific spatial/production-design logic
- **CHARACTER/ACTION:** posture + gaze + expression + movement
- **CORE ANCHORS:** all five represented in the prompt
- **ANTI-DRIFT:** Avoid-rule conflicts removed
- **FINAL PROMPT:** one integrated generation instruction


## Style Fidelity Gate
**Pass threshold:** average fidelity score >= **8.0/10**, Signature Fidelity >= **8.0**, Content Preservation >= **9.0**, and no other dimension below **7.5**.

### Profile-specific signature test
- Anchor 1: Strong, painterly compositions without sentimental beautification.
- Anchor 2: Long-held observation and willingness to let duration become part of the image.
- Anchor 3: Architecture can imprison, divide, expose, or dwarf the body.
- Anchor 4: Physical textures — skin, sweat, blood, food, walls, rain, dirt, fabric — remain tangible.
- Anchor 5: Negative space and stillness often increase moral pressure.

The image fails signature fidelity if fewer than four anchors are clearly visible.

### Score after generation
Score **Content Preservation, Camera/Composition, Lens/Space, Lighting, Color/Materials, Environment/Texture, Character/Action, and Signature Fidelity** from 0-10 using the global Fidelity Gate.

### Correction rule
If any passing condition fails, write a repair delta only for the failed dimensions, preserve successful dimensions, and regenerate. Run no more than two automatic repair cycles. Do not respond to failure by making the image generically "more cinematic."


### Research traceability record
**Traceability confidence:** HIGH

**Evidence-use instruction:** Use these anchors to support the visual rules above. Do not infer unsupported technical specifications.

- [TECH-1] *Filmmaker Magazine* — *Hunger*: form changing by section, physical ritual, texture, static duration, and later lyrical subjectivity.
- [INST-2] BFI analysis of McQueen's painterly composition and long-take rigor.

---

# 12. LIVING MEMORY NATURALISM
**Style ID:** CIS-12  
**Research Lineage:** Greta Gerwig  
**Representative works studied:** *Lady Bird*, *Little Women*, *Barbie*

## Research synthesis
The recurring image logic is **emotionally heightened naturalism organized around memory, relationships, and lived-in group behavior**. Research on *Lady Bird* describes a visual target resembling a color photocopy of remembered Sacramento: warm but imperfect, slightly granular, rooted in natural light and Wayne Thiebaud-like color. *Little Women* separates emotional time periods through movement, warmth, and photographic behavior rather than simplistic labels: childhood can feel mobile and alive, while later passages become more classical or still. The camera often treats families, friends, and rooms as relational systems rather than isolating one star.

## Persistent visual invariants
- Memory is warm and specific rather than hazy and generic.
- Natural light can be made radiant without losing everyday credibility.
- Grain and slight optical imperfection help the image feel lived rather than digitally pristine.
- Group blocking matters: families and friends overlap, interrupt, touch, and share frames.
- Youth may produce looser, more kinetic camera behavior; adulthood or separation may become more composed.
- Tableaux and frames-within-frames are used without making the scene emotionally cold.
- Production design carries character history through books, clothes, wallpaper, dishes, furniture, school spaces, and bedrooms.
- Color can be bold when the world justifies it, but emotional legibility remains central.

## AI image-construction rules
### Composition
Favor relational framing: mother/daughter two-shots, crowded tables, siblings on floors and beds, friends in cars, people crossing in front of one another. Use doorways and room layers to keep multiple relationships visible.

### Camera and lens
Use human-height, normal-to-wide perspective. Slight imperfection is preferable to sterile perfection. Movement can feel buoyant and close during youth or joy, then become more measured when distance or maturity enters.

### Lighting
Build from windows, sun, overcast daylight, lamps, fireplaces, practical interiors, and late-afternoon warmth. Keep one dominant source logic rather than lighting every face independently.

### Color/texture
Use warm but nuanced memory color: butterscotch sunlight, faded blue, cream, rose, forest green, paper, wood, aged fabric. Preserve visible grain and natural flare when appropriate.

### Avoid
- generic sepia nostalgia
- excessive diffusion
- sterile studio perfection
- single-person glamour compositions when the scene is relational
- random vintage props with no character meaning

## AI Deployment Block
**LIVING MEMORY NATURALISM / CIS-12:** Build emotionally warm, specific memory from ordinary life rather than generic nostalgia. Use natural-source light, tactile grain, slightly imperfect optics, human-height perspective, and relational group blocking in lived-in rooms, cars, schools, streets, and family spaces. Let youth feel more mobile and buoyant; let maturity or separation become more composed. Use period or contemporary objects as evidence of character history. Avoid sepia shortcuts, excessive haze, sterile polish, and compositions that isolate people from the relationships defining the scene.

## Style Compiler
**Compiler role:** Convert any user subject into this visual system without changing the user's required content.

### Five non-negotiable visual anchors
1. Memory is warm and specific rather than hazy and generic.
2. Natural light can be made radiant without losing everyday credibility.
3. Grain and slight optical imperfection help the image feel lived rather than digitally pristine.
4. Group blocking matters: families and friends overlap, interrupt, touch, and share frames.
5. Youth may produce looser, more kinetic camera behavior; adulthood or separation may become more composed.

**Minimum visibility rule:** At least four of these five anchors must be visibly present in the generated image. All five should be encoded in the prompt unless a locked user requirement conflicts.

### Style-specific compilation sequence
1. **Lock the subject.** Preserve every user-required identity/species/object, clothing item, color, prop, action, and setting constraint.
2. **Establish the visual premise.** Use the logic of **LIVING MEMORY NATURALISM / CIS-12** rather than adding generic cinematic adjectives. The deployment block above is the governing summary.
3. **Compile camera + composition.** Translate the profile's camera/composition rules into one explicit camera location, distance, framing, spatial behavior, and foreground/background relationship.
4. **Compile light.** Name the physical or psychological source, direction, hardness/softness, contrast behavior, and what it does to faces/materials.
5. **Compile color + materials.** Put the style palette into actual objects, surfaces, weather, wardrobe, architecture, practical light, landscape, skin, or props before using global grading language.
6. **Compile environment.** Make the space carry the style through architecture, geography, social context, production design, weather, and tactile material behavior.
7. **Compile character/action direction.** Specify posture, gaze, expression, movement, and emotional temperature so the subject participates in the visual grammar rather than merely standing inside it.
8. **Enforce the five anchors.** Check the prompt line-by-line and add any missing core anchor in concrete visual form.
9. **Run the anti-drift filter.** Reject or rewrite these failure modes: generic sepia nostalgia; excessive diffusion; sterile studio perfection; single-person glamour compositions when the scene is relational; random vintage props with no character meaning.
10. **Assemble one causal prompt.** The final instruction must read like a photographable scene, not a bag of adjectives.

### Compiled output checklist
- **STYLE:** LIVING MEMORY NATURALISM / CIS-12
- **SUBJECT LOCK:** exact user content preserved
- **CAMERA:** physical placement + framing + spatial behavior
- **LIGHT:** source + direction + contrast behavior
- **COLOR/MATERIALS:** object-level palette + tactile surfaces
- **ENVIRONMENT:** style-specific spatial/production-design logic
- **CHARACTER/ACTION:** posture + gaze + expression + movement
- **CORE ANCHORS:** all five represented in the prompt
- **ANTI-DRIFT:** Avoid-rule conflicts removed
- **FINAL PROMPT:** one integrated generation instruction


## Style Fidelity Gate
**Pass threshold:** average fidelity score >= **8.0/10**, Signature Fidelity >= **8.0**, Content Preservation >= **9.0**, and no other dimension below **7.5**.

### Profile-specific signature test
- Anchor 1: Memory is warm and specific rather than hazy and generic.
- Anchor 2: Natural light can be made radiant without losing everyday credibility.
- Anchor 3: Grain and slight optical imperfection help the image feel lived rather than digitally pristine.
- Anchor 4: Group blocking matters: families and friends overlap, interrupt, touch, and share frames.
- Anchor 5: Youth may produce looser, more kinetic camera behavior; adulthood or separation may become more composed.

The image fails signature fidelity if fewer than four anchors are clearly visible.

### Score after generation
Score **Content Preservation, Camera/Composition, Lens/Space, Lighting, Color/Materials, Environment/Texture, Character/Action, and Signature Fidelity** from 0-10 using the global Fidelity Gate.

### Correction rule
If any passing condition fails, write a repair delta only for the failed dimensions, preserve successful dimensions, and regenerate. Run no more than two automatic repair cycles. Do not respond to failure by making the image generically "more cinematic."


### Research traceability record
**Traceability confidence:** HIGH

**Evidence-use instruction:** Use these anchors to support the visual rules above. Do not infer unsupported technical specifications.

- [TECH-1] *Filmmaker Magazine* — *Lady Bird*: color-photocopy memory concept, Sacramento/Thiebaud influence, older-lens imperfection, grain, one-source lighting, tableaux.
- [TECH-1] Kodak / cinematography coverage of *Little Women*: shallow depth, smoky period patina, natural flare, and differentiated camera movement across timelines.

---

# 13. EMBODIED LIGHT REALISM
**Style ID:** CIS-13  
**Research Lineage:** Dee Rees  
**Representative works studied:** *Pariah*, *Mudbound*, *Bessie*, *The Last Thing He Wanted*

## Research synthesis
The system is built around **lighting and camera perspective as extensions of character state**. Research on *Pariah* emphasizes that lighting darkness was intentional and character-based: the protagonist moves in and out of light as identity, pressure, and liberation shift. The film's dark skin rendering required specific attention to diffuse, dimensional light rather than simply increasing exposure. *Mudbound* expands the language into tactile historical realism — natural light, weathered earth/wood palettes, older anamorphic softness, period photographic references, and an image that should feel lived rather than polished.

## Persistent visual invariants
- Light tracks identity and emotional state.
- Darkness is expressive but should retain dimensional skin information.
- Camera style follows character rather than a preset 'cool' visual package.
- Natural locations and historical materials are treated tactically and texturally.
- Skin tone, clothing, earth, wood, weather, and practical sources create palette.
- Fluid exploratory camera work can coexist with formal portraiture.
- Imperfect optics and analog-feeling texture help history feel inhabited.
- Liberation or clarity may be expressed through increased brightness, openness, or spatial release.

## AI image-construction rules
### Portrait and exposure
Expose faces for dimensional modeling, not flat brightness. Let shadow remain visible as shadow. Preserve highlights on cheekbones, forehead, nose, eyes, and lips without bleaching skin.

### Lighting
Use sources belonging to the world: club neon, street light, bedroom lamps, windows, sun, cloud, fire, porch light, farm daylight. Let a character move conceptually from shadow to light when the story calls for it.

### Color
For contemporary interiors, allow strong environment color to strike skin naturally. For historical/rural settings, favor earth, wood, faded cotton, warm highlights, blue-black shadow, and weather-softened saturation.

### Lens/texture
Permit edge softness, grain, veiling flare, imperfect focus falloff, and older-glass character where the story benefits. Avoid glossy digital crispness for historical material.

### Avoid
- crushing dark skin into unreadable black
- over-lighting every face equally
- generic 'period brown'
- stylization detached from character state
- spotless historical environments

## AI Deployment Block
**EMBODIED LIGHT REALISM / CIS-13:** Make light follow character identity and emotional state. Preserve dimensional dark skin in both highlight and shadow, use practical or natural sources, and let movement between darkness, color, and openness carry psychological meaning. In historical or rural settings, emphasize tactile earth, wood, cloth, weather, older-optic softness, and analog-feeling imperfection. Let the camera explore with the character rather than imposing a preselected visual trick. Avoid flattened skin, equalized studio lighting, generic brown period grading, and polished historical surfaces.

## Style Compiler
**Compiler role:** Convert any user subject into this visual system without changing the user's required content.

### Five non-negotiable visual anchors
1. Light tracks identity and emotional state.
2. Darkness is expressive but should retain dimensional skin information.
3. Camera style follows character rather than a preset 'cool' visual package.
4. Natural locations and historical materials are treated tactically and texturally.
5. Skin tone, clothing, earth, wood, weather, and practical sources create palette.

**Minimum visibility rule:** At least four of these five anchors must be visibly present in the generated image. All five should be encoded in the prompt unless a locked user requirement conflicts.

### Style-specific compilation sequence
1. **Lock the subject.** Preserve every user-required identity/species/object, clothing item, color, prop, action, and setting constraint.
2. **Establish the visual premise.** Use the logic of **EMBODIED LIGHT REALISM / CIS-13** rather than adding generic cinematic adjectives. The deployment block above is the governing summary.
3. **Compile camera + composition.** Translate the profile's camera/composition rules into one explicit camera location, distance, framing, spatial behavior, and foreground/background relationship.
4. **Compile light.** Name the physical or psychological source, direction, hardness/softness, contrast behavior, and what it does to faces/materials.
5. **Compile color + materials.** Put the style palette into actual objects, surfaces, weather, wardrobe, architecture, practical light, landscape, skin, or props before using global grading language.
6. **Compile environment.** Make the space carry the style through architecture, geography, social context, production design, weather, and tactile material behavior.
7. **Compile character/action direction.** Specify posture, gaze, expression, movement, and emotional temperature so the subject participates in the visual grammar rather than merely standing inside it.
8. **Enforce the five anchors.** Check the prompt line-by-line and add any missing core anchor in concrete visual form.
9. **Run the anti-drift filter.** Reject or rewrite these failure modes: crushing dark skin into unreadable black; over-lighting every face equally; generic 'period brown'; stylization detached from character state; spotless historical environments.
10. **Assemble one causal prompt.** The final instruction must read like a photographable scene, not a bag of adjectives.

### Compiled output checklist
- **STYLE:** EMBODIED LIGHT REALISM / CIS-13
- **SUBJECT LOCK:** exact user content preserved
- **CAMERA:** physical placement + framing + spatial behavior
- **LIGHT:** source + direction + contrast behavior
- **COLOR/MATERIALS:** object-level palette + tactile surfaces
- **ENVIRONMENT:** style-specific spatial/production-design logic
- **CHARACTER/ACTION:** posture + gaze + expression + movement
- **CORE ANCHORS:** all five represented in the prompt
- **ANTI-DRIFT:** Avoid-rule conflicts removed
- **FINAL PROMPT:** one integrated generation instruction


## Style Fidelity Gate
**Pass threshold:** average fidelity score >= **8.0/10**, Signature Fidelity >= **8.0**, Content Preservation >= **9.0**, and no other dimension below **7.5**.

### Profile-specific signature test
- Anchor 1: Light tracks identity and emotional state.
- Anchor 2: Darkness is expressive but should retain dimensional skin information.
- Anchor 3: Camera style follows character rather than a preset 'cool' visual package.
- Anchor 4: Natural locations and historical materials are treated tactically and texturally.
- Anchor 5: Skin tone, clothing, earth, wood, weather, and practical sources create palette.

The image fails signature fidelity if fewer than four anchors are clearly visible.

### Score after generation
Score **Content Preservation, Camera/Composition, Lens/Space, Lighting, Color/Materials, Environment/Texture, Character/Action, and Signature Fidelity** from 0-10 using the global Fidelity Gate.

### Correction rule
If any passing condition fails, write a repair delta only for the failed dimensions, preserve successful dimensions, and regenerate. Run no more than two automatic repair cycles. Do not respond to failure by making the image generically "more cinematic."


### Research traceability record
**Traceability confidence:** HIGH

**Evidence-use instruction:** Use these anchors to support the visual rules above. Do not infer unsupported technical specifications.

- [INST-2] BFI analysis of *Pariah*: character-led camera, intentional underexposure, light/dark identity transitions, and custom strategies for dark skin.
- [TECH-1] *Filmmaker Magazine* coverage of *Mudbound*: naturalistic analog feeling, period photo references, older anamorphic softness, earth/wood palette, and exploratory camera.

---

# 14. DOMESTIC UNCANNY NOIR
**Style ID:** CIS-14  
**Research Lineage:** David Lynch  
**Representative works studied:** *Blue Velvet*, *Twin Peaks: Fire Walk with Me*, *Lost Highway*, *Mulholland Drive*, *Inland Empire*

## Research synthesis
The recurring visual system places **ordinary domestic or civic surfaces beside pockets of inexplicable darkness, dream glamour, voyeuristic framing, and sudden changes in image texture**. *Blue Velvet* famously creates a bright, saturated small-town surface and then descends into rich, almost liquid black. *Lost Highway* embraces rooms near the threshold of visibility. *Mulholland Drive* can move between old-Hollywood softness, neo-noir night, and emotional light changes that do not need literal justification. *Inland Empire* proves that immaculate film beauty is not required; harsh low-resolution digital proximity can itself become uncanny.

## Persistent visual invariants
- Cheerful normality and profound menace may exist in adjacent spaces.
- Darkness is a place, not simply low exposure.
- Curtains, doorways, hallways, closets, stages, bedrooms, lamps, clubs, and empty roads become thresholds.
- Saturated primary color, especially red, can function as an emotional alarm.
- Pools of practical light may float inside large areas of black.
- Slow approach, static observation, voyeuristic obstruction, or extreme facial proximity can all generate dread.
- Dream glamour and ugly digital immediacy can coexist within the larger grammar.
- Emotional logic may override physical lighting continuity.

## AI image-construction rules
### Composition
Use thresholds and partial concealment. Frame through curtains, doorways, closet slats, mirrors, windshields, stage openings, or dark foreground shapes. Keep empty areas of darkness that feel spatially inhabited.

### Lighting
Build isolated pools from table lamps, sconces, headlights, stage light, neon, or weak daylight. Let surrounding rooms fall nearly black. In brighter 'normal' scenes, push clean lawn green, blue sky, painted surfaces, and cheerful domestic color just enough to feel too complete.

### Color
Use strong reds, browns, yellows, deep blue-black, or sickly domestic color selectively. Do not turn every image into a neon nightmare.

### Texture
Choose either polished dream-film softness or confrontational low-resolution digital texture according to psychological state. Abruptly changing image quality can itself be meaningful.

### Character direction
Still smiles, distant gazes, frozen social politeness, fear that has not yet become action, or faces too close to the lens can be more disturbing than overt monster behavior.

### Avoid
- generic surreal collage
- random melting objects
- purple/green horror lighting
- constant dutch angles
- explaining the uncanny visually too soon
- making every scene equally dark

## AI Deployment Block
**DOMESTIC UNCANNY NOIR / CIS-14:** Begin with a recognizable domestic, civic, roadside, or entertainment space, then create a threshold where normality gives way to darkness or emotional unreality. Use curtains, doorways, mirrors, lamps, stages, empty roads, voyeuristic obstruction, saturated red accents, pools of practical light, and large near-black spaces. Permit dream-soft glamour or harsh digital proximity when psychology changes. Keep the uncanny spatial and emotional rather than filling the frame with generic surreal effects. Avoid random distortion, all-purpose neon horror, and constant darkness.

## Style Compiler
**Compiler role:** Convert any user subject into this visual system without changing the user's required content.

### Five non-negotiable visual anchors
1. Cheerful normality and profound menace may exist in adjacent spaces.
2. Darkness is a place, not simply low exposure.
3. Curtains, doorways, hallways, closets, stages, bedrooms, lamps, clubs, and empty roads become thresholds.
4. Saturated primary color, especially red, can function as an emotional alarm.
5. Pools of practical light may float inside large areas of black.

**Minimum visibility rule:** At least four of these five anchors must be visibly present in the generated image. All five should be encoded in the prompt unless a locked user requirement conflicts.

### Style-specific compilation sequence
1. **Lock the subject.** Preserve every user-required identity/species/object, clothing item, color, prop, action, and setting constraint.
2. **Establish the visual premise.** Use the logic of **DOMESTIC UNCANNY NOIR / CIS-14** rather than adding generic cinematic adjectives. The deployment block above is the governing summary.
3. **Compile camera + composition.** Translate the profile's camera/composition rules into one explicit camera location, distance, framing, spatial behavior, and foreground/background relationship.
4. **Compile light.** Name the physical or psychological source, direction, hardness/softness, contrast behavior, and what it does to faces/materials.
5. **Compile color + materials.** Put the style palette into actual objects, surfaces, weather, wardrobe, architecture, practical light, landscape, skin, or props before using global grading language.
6. **Compile environment.** Make the space carry the style through architecture, geography, social context, production design, weather, and tactile material behavior.
7. **Compile character/action direction.** Specify posture, gaze, expression, movement, and emotional temperature so the subject participates in the visual grammar rather than merely standing inside it.
8. **Enforce the five anchors.** Check the prompt line-by-line and add any missing core anchor in concrete visual form.
9. **Run the anti-drift filter.** Reject or rewrite these failure modes: generic surreal collage; random melting objects; purple/green horror lighting; constant dutch angles; explaining the uncanny visually too soon; making every scene equally dark.
10. **Assemble one causal prompt.** The final instruction must read like a photographable scene, not a bag of adjectives.

### Compiled output checklist
- **STYLE:** DOMESTIC UNCANNY NOIR / CIS-14
- **SUBJECT LOCK:** exact user content preserved
- **CAMERA:** physical placement + framing + spatial behavior
- **LIGHT:** source + direction + contrast behavior
- **COLOR/MATERIALS:** object-level palette + tactile surfaces
- **ENVIRONMENT:** style-specific spatial/production-design logic
- **CHARACTER/ACTION:** posture + gaze + expression + movement
- **CORE ANCHORS:** all five represented in the prompt
- **ANTI-DRIFT:** Avoid-rule conflicts removed
- **FINAL PROMPT:** one integrated generation instruction


## Style Fidelity Gate
**Pass threshold:** average fidelity score >= **8.0/10**, Signature Fidelity >= **8.0**, Content Preservation >= **9.0**, and no other dimension below **7.5**.

### Profile-specific signature test
- Anchor 1: Cheerful normality and profound menace may exist in adjacent spaces.
- Anchor 2: Darkness is a place, not simply low exposure.
- Anchor 3: Curtains, doorways, hallways, closets, stages, bedrooms, lamps, clubs, and empty roads become thresholds.
- Anchor 4: Saturated primary color, especially red, can function as an emotional alarm.
- Anchor 5: Pools of practical light may float inside large areas of black.

The image fails signature fidelity if fewer than four anchors are clearly visible.

### Score after generation
Score **Content Preservation, Camera/Composition, Lens/Space, Lighting, Color/Materials, Environment/Texture, Character/Action, and Signature Fidelity** from 0-10 using the global Fidelity Gate.

### Correction rule
If any passing condition fails, write a repair delta only for the failed dimensions, preserve successful dimensions, and regenerate. Run no more than two automatic repair cycles. Do not respond to failure by making the image generically "more cinematic."


### Research traceability record
**Traceability confidence:** HIGH

**Evidence-use instruction:** Use these anchors to support the visual rules above. Do not infer unsupported technical specifications.

- [TECH-1] *American Cinematographer* — *Blue Velvet*: saturated small-town surface, liquid black, voyeuristic POV, and changing room mood.
- [TECH-1] *American Cinematographer* — *Mulholland Drive* / *Lost Highway*: neo-noir darkness, old-Hollywood softness, emotional light shifts, and near-dark interiors.
- [INST-2] BFI analysis of *Inland Empire*: confrontational low-resolution digital image texture.

---

# 15. STREET PULSE CINEMA
**Style ID:** CIS-15  
**Research Lineage:** F. Gary Gray  
**Representative works studied:** *Friday*, *Set It Off*, *The Italian Job*, *Straight Outta Compton*, *The Fate of the Furious*

## Research synthesis
The recurring grammar is **kinetic urban immediacy with strong location identity**. Research around *Straight Outta Compton* emphasizes a desire for the image to feel real and authentic rather than overly 'Hollywood,' using moving camera, handheld/documentary behavior, period-accurate sodium-vapor environments, warm/cool practical mixtures, optical dirt, and city-specific atmosphere. Gray's action work adds clearer mechanical geography, but the street remains felt as a social and physical environment rather than a generic backdrop.

## Persistent visual invariants
- Street and neighborhood identity remain visible around characters.
- Camera movement carries performance energy and urban momentum.
- Handheld or documentary-style responsiveness is acceptable when it increases authenticity.
- Practical color temperatures — sodium orange, fluorescent green, cool night, warm interiors — can coexist.
- Optical or textural imperfection prevents the image from feeling sterile.
- Cars, sidewalks, clubs, porches, studios, stages, parking lots, and houses are treated as social spaces.
- Action remains readable even when the camera is energetic.
- Period details should appear lived, not museum-curated.

## AI image-construction rules
### Camera
Use street-level, shoulder-height perspective, moving proximity, occasional low angles, and moderate wide lenses. Let the viewer feel physically near the group or vehicle.

### Lighting/color
Preserve real urban source conflict: sodium street light against cooler ambient night, fluorescent interiors against warm skin, sun-baked afternoon against dark car interiors. Do not neutralize all color temperatures.

### Texture
Allow grain, older-lens softness, flare, slight halation, atmospheric haze, scuffed vehicles, worn asphalt, sweat, smoke, and imperfect surfaces.

### Group direction
Characters should interact with one another and the space — leaning on cars, sitting on stoops, crossing streets, working in studios, performing, arguing, laughing. Avoid lineup posing.

### Avoid
- generic glossy music-video polish
- anonymous futuristic city light
- over-stabilized action
- fake period cleanliness
- background blur that removes neighborhood identity

## AI Deployment Block
**STREET PULSE CINEMA / CIS-15:** Keep the camera physically near the street, group, vehicle, club, home, or performance space. Use moving or handheld immediacy, moderate wide perspective, authentic location detail, mixed practical color temperatures, textured optics, and readable action geography. Preserve sodium light, fluorescent spill, warm interiors, cool night, grain, flare, worn surfaces, and period imperfection when appropriate. People should inhabit the neighborhood rather than pose against it. Avoid glossy music-video sterility, anonymous city backgrounds, fake period cleanliness, and excessive stabilization.

## Style Compiler
**Compiler role:** Convert any user subject into this visual system without changing the user's required content.

### Five non-negotiable visual anchors
1. Street and neighborhood identity remain visible around characters.
2. Camera movement carries performance energy and urban momentum.
3. Handheld or documentary-style responsiveness is acceptable when it increases authenticity.
4. Practical color temperatures — sodium orange, fluorescent green, cool night, warm interiors — can coexist.
5. Optical or textural imperfection prevents the image from feeling sterile.

**Minimum visibility rule:** At least four of these five anchors must be visibly present in the generated image. All five should be encoded in the prompt unless a locked user requirement conflicts.

### Style-specific compilation sequence
1. **Lock the subject.** Preserve every user-required identity/species/object, clothing item, color, prop, action, and setting constraint.
2. **Establish the visual premise.** Use the logic of **STREET PULSE CINEMA / CIS-15** rather than adding generic cinematic adjectives. The deployment block above is the governing summary.
3. **Compile camera + composition.** Translate the profile's camera/composition rules into one explicit camera location, distance, framing, spatial behavior, and foreground/background relationship.
4. **Compile light.** Name the physical or psychological source, direction, hardness/softness, contrast behavior, and what it does to faces/materials.
5. **Compile color + materials.** Put the style palette into actual objects, surfaces, weather, wardrobe, architecture, practical light, landscape, skin, or props before using global grading language.
6. **Compile environment.** Make the space carry the style through architecture, geography, social context, production design, weather, and tactile material behavior.
7. **Compile character/action direction.** Specify posture, gaze, expression, movement, and emotional temperature so the subject participates in the visual grammar rather than merely standing inside it.
8. **Enforce the five anchors.** Check the prompt line-by-line and add any missing core anchor in concrete visual form.
9. **Run the anti-drift filter.** Reject or rewrite these failure modes: generic glossy music-video polish; anonymous futuristic city light; over-stabilized action; fake period cleanliness; background blur that removes neighborhood identity.
10. **Assemble one causal prompt.** The final instruction must read like a photographable scene, not a bag of adjectives.

### Compiled output checklist
- **STYLE:** STREET PULSE CINEMA / CIS-15
- **SUBJECT LOCK:** exact user content preserved
- **CAMERA:** physical placement + framing + spatial behavior
- **LIGHT:** source + direction + contrast behavior
- **COLOR/MATERIALS:** object-level palette + tactile surfaces
- **ENVIRONMENT:** style-specific spatial/production-design logic
- **CHARACTER/ACTION:** posture + gaze + expression + movement
- **CORE ANCHORS:** all five represented in the prompt
- **ANTI-DRIFT:** Avoid-rule conflicts removed
- **FINAL PROMPT:** one integrated generation instruction


## Style Fidelity Gate
**Pass threshold:** average fidelity score >= **8.0/10**, Signature Fidelity >= **8.0**, Content Preservation >= **9.0**, and no other dimension below **7.5**.

### Profile-specific signature test
- Anchor 1: Street and neighborhood identity remain visible around characters.
- Anchor 2: Camera movement carries performance energy and urban momentum.
- Anchor 3: Handheld or documentary-style responsiveness is acceptable when it increases authenticity.
- Anchor 4: Practical color temperatures — sodium orange, fluorescent green, cool night, warm interiors — can coexist.
- Anchor 5: Optical or textural imperfection prevents the image from feeling sterile.

The image fails signature fidelity if fewer than four anchors are clearly visible.

### Score after generation
Score **Content Preservation, Camera/Composition, Lens/Space, Lighting, Color/Materials, Environment/Texture, Character/Action, and Signature Fidelity** from 0-10 using the global Fidelity Gate.

### Correction rule
If any passing condition fails, write a repair delta only for the failed dimensions, preserve successful dimensions, and regenerate. Run no more than two automatic repair cycles. Do not respond to failure by making the image generically "more cinematic."


### Research traceability record
**Traceability confidence:** HIGH

**Evidence-use instruction:** Use these anchors to support the visual rules above. Do not infer unsupported technical specifications.

- [TECH-1] Post-production / cinematography interviews on *Straight Outta Compton*: authentic Los Angeles, moving/handheld camera, documentary feel.
- [TECH-1] Matthew Libatique interviews: sodium-vapor period lighting, warm/cool contrast, and a deliberately 'dirtier' image.

---

# 16. SOMATIC SPIRAL
**Style ID:** CIS-16  
**Research Lineage:** Darren Aronofsky  
**Representative works studied:** *Pi*, *Requiem for a Dream*, *The Wrestler*, *Black Swan*, *mother!*, *The Whale*

## Research synthesis
The invariant is **extreme subjectivity through the body**. Aronofsky repeatedly makes the camera feel attached to obsession, addiction, performance, pain, or psychological collapse. *Requiem for a Dream* formalizes this with repeated micro-montage rituals, body-mounted/Snorricam perspective, extreme inserts, increasingly abrasive texture, and wide-angle proximity. Later work such as *The Wrestler*, *Black Swan*, and *mother!* often replaces rigid montage systems with longer handheld following behavior, but the purpose remains the same: the viewer is trapped inside the protagonist's physical and mental loop.

## Persistent visual invariants
- Camera perspective is organized around subjective bodily experience.
- Repetition of actions/objects can become a visual ritual.
- Extreme close detail — eye, hand, pill, needle, skin, food, mirror, wound, fabric — can compress the world into obsession.
- Wide lenses used close to the body increase distortion and pressure.
- Attached/body-mounted perspective can make the background move unnaturally around a stable face.
- Image texture can deteriorate or intensify as psychology deteriorates.
- Mirrors, doubles, reflections, circular motion, and repeated pathways externalize mental loops.
- Later vérité-style following remains character-bound rather than objective.

## AI image-construction rules
### Camera
Stay attached to the protagonist. Use shoulder-follow, over-close wide angle, body-rig feeling, mirror reflection, or frontal moving portrait. Background geometry can feel unstable while the subject remains fixed.

### Detail system
Identify 2-4 repeated sensory details tied to the obsession. For still images, include at least one close symbolic detail in the composition or imply a repetitive ritual through objects and body posture.

### Lighting/color
Let the visual environment intensify with psychology. Early scenes may be cleaner or more natural; later scenes may become harsher, higher contrast, greener, redder, grainier, more fluorescent, or more depleted depending on story.

### Texture
Use grain, sweat, pores, scratches, digital noise, blown practicals, dirty mirrors, or abrasive shadow when collapse is advancing.

### Avoid
- random psychedelic effects disconnected from the body
- detached scenic wides during intense subjective moments
- elegant beauty blur
- using every extreme technique at once without psychological escalation

## AI Deployment Block
**SOMATIC SPIRAL / CIS-16:** Trap the image inside the protagonist's bodily and psychological loop. Use close wide-angle proximity, attached-camera feeling, mirrors/reflections, repeated ritual objects, extreme sensory details, and texture that can intensify as obsession or collapse deepens. Let the background become unstable around a psychologically fixed subject. Escalate contrast, grain, color contamination, and optical discomfort only as the story escalates. Avoid decorative psychedelia, distant objectivity, and piling on distortions without a character-based reason.

## Style Compiler
**Compiler role:** Convert any user subject into this visual system without changing the user's required content.

### Five non-negotiable visual anchors
1. Camera perspective is organized around subjective bodily experience.
2. Repetition of actions/objects can become a visual ritual.
3. Extreme close detail — eye, hand, pill, needle, skin, food, mirror, wound, fabric — can compress the world into obsession.
4. Wide lenses used close to the body increase distortion and pressure.
5. Attached/body-mounted perspective can make the background move unnaturally around a stable face.

**Minimum visibility rule:** At least four of these five anchors must be visibly present in the generated image. All five should be encoded in the prompt unless a locked user requirement conflicts.

### Style-specific compilation sequence
1. **Lock the subject.** Preserve every user-required identity/species/object, clothing item, color, prop, action, and setting constraint.
2. **Establish the visual premise.** Use the logic of **SOMATIC SPIRAL / CIS-16** rather than adding generic cinematic adjectives. The deployment block above is the governing summary.
3. **Compile camera + composition.** Translate the profile's camera/composition rules into one explicit camera location, distance, framing, spatial behavior, and foreground/background relationship.
4. **Compile light.** Name the physical or psychological source, direction, hardness/softness, contrast behavior, and what it does to faces/materials.
5. **Compile color + materials.** Put the style palette into actual objects, surfaces, weather, wardrobe, architecture, practical light, landscape, skin, or props before using global grading language.
6. **Compile environment.** Make the space carry the style through architecture, geography, social context, production design, weather, and tactile material behavior.
7. **Compile character/action direction.** Specify posture, gaze, expression, movement, and emotional temperature so the subject participates in the visual grammar rather than merely standing inside it.
8. **Enforce the five anchors.** Check the prompt line-by-line and add any missing core anchor in concrete visual form.
9. **Run the anti-drift filter.** Reject or rewrite these failure modes: random psychedelic effects disconnected from the body; detached scenic wides during intense subjective moments; elegant beauty blur; using every extreme technique at once without psychological escalation.
10. **Assemble one causal prompt.** The final instruction must read like a photographable scene, not a bag of adjectives.

### Compiled output checklist
- **STYLE:** SOMATIC SPIRAL / CIS-16
- **SUBJECT LOCK:** exact user content preserved
- **CAMERA:** physical placement + framing + spatial behavior
- **LIGHT:** source + direction + contrast behavior
- **COLOR/MATERIALS:** object-level palette + tactile surfaces
- **ENVIRONMENT:** style-specific spatial/production-design logic
- **CHARACTER/ACTION:** posture + gaze + expression + movement
- **CORE ANCHORS:** all five represented in the prompt
- **ANTI-DRIFT:** Avoid-rule conflicts removed
- **FINAL PROMPT:** one integrated generation instruction


## Style Fidelity Gate
**Pass threshold:** average fidelity score >= **8.0/10**, Signature Fidelity >= **8.0**, Content Preservation >= **9.0**, and no other dimension below **7.5**.

### Profile-specific signature test
- Anchor 1: Camera perspective is organized around subjective bodily experience.
- Anchor 2: Repetition of actions/objects can become a visual ritual.
- Anchor 3: Extreme close detail — eye, hand, pill, needle, skin, food, mirror, wound, fabric — can compress the world into obsession.
- Anchor 4: Wide lenses used close to the body increase distortion and pressure.
- Anchor 5: Attached/body-mounted perspective can make the background move unnaturally around a stable face.

The image fails signature fidelity if fewer than four anchors are clearly visible.

### Score after generation
Score **Content Preservation, Camera/Composition, Lens/Space, Lighting, Color/Materials, Environment/Texture, Character/Action, and Signature Fidelity** from 0-10 using the global Fidelity Gate.

### Correction rule
If any passing condition fails, write a repair delta only for the failed dimensions, preserve successful dimensions, and regenerate. Run no more than two automatic repair cycles. Do not respond to failure by making the image generically "more cinematic."


### Research traceability record
**Traceability confidence:** HIGH

**Evidence-use instruction:** Use these anchors to support the visual rules above. Do not infer unsupported technical specifications.

- [TECH-1] *American Cinematographer* — *Requiem for a Dream*: repeated montage grammar, Snorricam/body rigs, wide proximity, and texture escalation.
- [TECH-1] *Filmmaker Magazine* — *Black Swan* / later Aronofsky: transition toward longer, character-bound vérité/following camera while retaining subjective focus.

---

# 17. COMPOSED HERITAGE RADIANCE
**Style ID:** CIS-17  
**Research Lineage:** Amma Asante  
**Representative works studied:** *Belle*, *A United Kingdom*, *Where Hands Touch*

## Research synthesis
The recurring language is **classical period composition made emotionally legible through color, skin, costume, architecture, and social placement**. Research on *Belle* documents rigorous mood and color planning: households and social spaces receive distinct palette identities, such as cooler icy tones versus warmer gold/yellow wealth. Asante's period worlds are polished but not inert; the frame is designed to show who belongs, who is being displayed, who is being excluded, and how identity operates inside rigid social systems.

## Persistent visual invariants
- Period beauty is organized around social power and identity.
- Color palettes can distinguish families, institutions, countries, or emotional climates.
- Classical rooms, portraits, staircases, gardens, dining tables, and formal dress become power geometry.
- Dark skin should remain luminous inside historically styled interiors and exteriors.
- Composition is elegant and controlled but character perspective remains central.
- Costume color and texture are active narrative tools.
- Romantic warmth and institutional coolness can coexist as opposing visual zones.

## AI image-construction rules
### Composition
Use balanced classical framing, doorways, staircases, long tables, portrait walls, garden axes, drawing rooms, formal exteriors, and carefully spaced bodies. Let placement reveal rank and exclusion.

### Lighting
Use window daylight, candles, fireplaces, overcast exterior light, and soft directional period interiors. Preserve facial dimensionality across varied skin tones.

### Color
Create explicit palette families for competing social worlds. Example: cold powder blue/silver for emotionally restrictive aristocratic space versus warm gold/ochre/cream for intimacy or security. Tie colors to rooms, costumes, upholstery, and daylight rather than grading alone.

### Texture
Silk, linen, wool, polished wood, painted plaster, porcelain, grass, paper, and jewelry should feel tactile and period-specific.

### Avoid
- generic brown period grading
- costume-drama postcard prettiness with no power structure
- overexposed dark skin
- random modern saturation
- compositions that ignore social hierarchy

## AI Deployment Block
**COMPOSED HERITAGE RADIANCE / CIS-17:** Build elegant period imagery in which social hierarchy is visible through body placement, architecture, costume, and controlled palette families. Use classical balanced compositions, window/candle/fireplace light, tactile period materials, and dimensional skin rendering. Assign different color climates to families, institutions, or emotional zones rather than applying one sepia grade. Let beauty reveal exclusion, belonging, romance, and power. Avoid museum-like stiffness, generic brown grading, and period decoration without social meaning.

## Style Compiler
**Compiler role:** Convert any user subject into this visual system without changing the user's required content.

### Five non-negotiable visual anchors
1. Period beauty is organized around social power and identity.
2. Color palettes can distinguish families, institutions, countries, or emotional climates.
3. Classical rooms, portraits, staircases, gardens, dining tables, and formal dress become power geometry.
4. Dark skin should remain luminous inside historically styled interiors and exteriors.
5. Composition is elegant and controlled but character perspective remains central.

**Minimum visibility rule:** At least four of these five anchors must be visibly present in the generated image. All five should be encoded in the prompt unless a locked user requirement conflicts.

### Style-specific compilation sequence
1. **Lock the subject.** Preserve every user-required identity/species/object, clothing item, color, prop, action, and setting constraint.
2. **Establish the visual premise.** Use the logic of **COMPOSED HERITAGE RADIANCE / CIS-17** rather than adding generic cinematic adjectives. The deployment block above is the governing summary.
3. **Compile camera + composition.** Translate the profile's camera/composition rules into one explicit camera location, distance, framing, spatial behavior, and foreground/background relationship.
4. **Compile light.** Name the physical or psychological source, direction, hardness/softness, contrast behavior, and what it does to faces/materials.
5. **Compile color + materials.** Put the style palette into actual objects, surfaces, weather, wardrobe, architecture, practical light, landscape, skin, or props before using global grading language.
6. **Compile environment.** Make the space carry the style through architecture, geography, social context, production design, weather, and tactile material behavior.
7. **Compile character/action direction.** Specify posture, gaze, expression, movement, and emotional temperature so the subject participates in the visual grammar rather than merely standing inside it.
8. **Enforce the five anchors.** Check the prompt line-by-line and add any missing core anchor in concrete visual form.
9. **Run the anti-drift filter.** Reject or rewrite these failure modes: generic brown period grading; costume-drama postcard prettiness with no power structure; overexposed dark skin; random modern saturation; compositions that ignore social hierarchy.
10. **Assemble one causal prompt.** The final instruction must read like a photographable scene, not a bag of adjectives.

### Compiled output checklist
- **STYLE:** COMPOSED HERITAGE RADIANCE / CIS-17
- **SUBJECT LOCK:** exact user content preserved
- **CAMERA:** physical placement + framing + spatial behavior
- **LIGHT:** source + direction + contrast behavior
- **COLOR/MATERIALS:** object-level palette + tactile surfaces
- **ENVIRONMENT:** style-specific spatial/production-design logic
- **CHARACTER/ACTION:** posture + gaze + expression + movement
- **CORE ANCHORS:** all five represented in the prompt
- **ANTI-DRIFT:** Avoid-rule conflicts removed
- **FINAL PROMPT:** one integrated generation instruction


## Style Fidelity Gate
**Pass threshold:** average fidelity score >= **8.0/10**, Signature Fidelity >= **8.0**, Content Preservation >= **9.0**, and no other dimension below **7.5**.

### Profile-specific signature test
- Anchor 1: Period beauty is organized around social power and identity.
- Anchor 2: Color palettes can distinguish families, institutions, countries, or emotional climates.
- Anchor 3: Classical rooms, portraits, staircases, gardens, dining tables, and formal dress become power geometry.
- Anchor 4: Dark skin should remain luminous inside historically styled interiors and exteriors.
- Anchor 5: Composition is elegant and controlled but character perspective remains central.

The image fails signature fidelity if fewer than four anchors are clearly visible.

### Score after generation
Score **Content Preservation, Camera/Composition, Lens/Space, Lighting, Color/Materials, Environment/Texture, Character/Action, and Signature Fidelity** from 0-10 using the global Fidelity Gate.

### Correction rule
If any passing condition fails, write a repair delta only for the failed dimensions, preserve successful dimensions, and regenerate. Run no more than two automatic repair cycles. Do not respond to failure by making the image generically "more cinematic."


### Research traceability record
**Traceability confidence:** MEDIUM

**Evidence-use instruction:** Use these anchors to support the visual rules above. Do not infer unsupported technical specifications.

- [CRIT-4] Interviews on *Belle*: strict mood/color boards and family-specific palette systems, including cool versus warm social worlds.
- [CRIT-4] Comparative frame study of *Belle* and *A United Kingdom*.

---

# 18. NEON MEMORY DRIFT
**Style ID:** CIS-18  
**Research Lineage:** Wong Kar-wai  
**Representative works studied:** *Days of Being Wild*, *Chungking Express*, *Fallen Angels*, *Happy Together*, *In the Mood for Love*, *2046*

## Research synthesis
The deeper invariant is **emotion made spatial and temporal**. The exact palette changes radically from film to film, but recurring devices include close wide-angle urban intimacy, reflections and foreground obstruction, bodies separated by architecture, repeated fragments, saturated practical color, and manipulation of motion/time. Step-printing and undercranking can turn crowds into smeared velocity around an emotionally isolated person. *In the Mood for Love* becomes more controlled and claustrophobic, using doorways, mirrors, narrow corridors, repeated passages, and sensual texture instead of the looser rush of *Chungking Express*. What persists is memory, longing, and subjective time.

## Persistent visual invariants
- Time may feel stretched, skipped, repeated, or smeared.
- Characters are often physically close but architecturally separated.
- Foreground objects, doorframes, mirrors, glass, curtains, and narrow passageways create partial views.
- Practical neon, tungsten, fluorescent, street color, or deep red/green can carry emotion.
- Wide lenses used close can distort intimate urban interiors.
- Motion blur or step-printed smear can isolate one emotional subject from moving crowds.
- Repeated gestures, meals, hallways, clocks, rain, cigarettes, music, and clothing become memory anchors.
- Static romantic tableaux and handheld improvisation are both valid depending on emotional phase.

## AI image-construction rules
### Composition
Frame through obstacles. Let a wall, doorway, mirror edge, window, shelf, passerby, or curtain occupy significant foreground. Put characters in narrow restaurants, stairwells, hotel corridors, apartments, alleys, trains, or night streets.

### Lens and proximity
Use wide-to-normal lenses close to faces in tight spaces. Allow edge distortion when it intensifies intimacy. Avoid clean commercial portrait distance.

### Color
Build color from practical sources: green fluorescent, red wall, amber lamp, cyan sign, sodium street light, patterned dress. Let one or two colors dominate a scene emotionally. Do not force neon into daylight or quiet historical interiors when inappropriate.

### Time/motion in a still
Use selective motion smear around a relatively stable subject, repeated reflections, rain streaks, passing bodies, clocks, or layered foreground to suggest time sliding rather than freezing.

### Avoid
- generic cyberpunk neon
- clean symmetrical nightlife photography
- bokeh-only 'romance'
- color with no practical source
- treating every image as frantic; still claustrophobic elegance is equally important

## AI Deployment Block
**NEON MEMORY DRIFT / CIS-18:** Make emotion alter the viewer's sense of space and time. Work close to characters in narrow urban or domestic spaces, frame through doors, mirrors, glass, curtains, walls, and passing bodies, and use practical color as emotional memory. Allow selective motion smear, repeated gestures, reflections, rain, clocks, or crowd movement to make time feel stretched or fragmented. Use either restless handheld intimacy or still claustrophobic tableaux according to the emotional phase. Avoid generic cyberpunk, clean nightlife glamour, and neon without a physical source.

## Style Compiler
**Compiler role:** Convert any user subject into this visual system without changing the user's required content.

### Five non-negotiable visual anchors
1. Time may feel stretched, skipped, repeated, or smeared.
2. Characters are often physically close but architecturally separated.
3. Foreground objects, doorframes, mirrors, glass, curtains, and narrow passageways create partial views.
4. Practical neon, tungsten, fluorescent, street color, or deep red/green can carry emotion.
5. Wide lenses used close can distort intimate urban interiors.

**Minimum visibility rule:** At least four of these five anchors must be visibly present in the generated image. All five should be encoded in the prompt unless a locked user requirement conflicts.

### Style-specific compilation sequence
1. **Lock the subject.** Preserve every user-required identity/species/object, clothing item, color, prop, action, and setting constraint.
2. **Establish the visual premise.** Use the logic of **NEON MEMORY DRIFT / CIS-18** rather than adding generic cinematic adjectives. The deployment block above is the governing summary.
3. **Compile camera + composition.** Translate the profile's camera/composition rules into one explicit camera location, distance, framing, spatial behavior, and foreground/background relationship.
4. **Compile light.** Name the physical or psychological source, direction, hardness/softness, contrast behavior, and what it does to faces/materials.
5. **Compile color + materials.** Put the style palette into actual objects, surfaces, weather, wardrobe, architecture, practical light, landscape, skin, or props before using global grading language.
6. **Compile environment.** Make the space carry the style through architecture, geography, social context, production design, weather, and tactile material behavior.
7. **Compile character/action direction.** Specify posture, gaze, expression, movement, and emotional temperature so the subject participates in the visual grammar rather than merely standing inside it.
8. **Enforce the five anchors.** Check the prompt line-by-line and add any missing core anchor in concrete visual form.
9. **Run the anti-drift filter.** Reject or rewrite these failure modes: generic cyberpunk neon; clean symmetrical nightlife photography; bokeh-only 'romance'; color with no practical source; treating every image as frantic; still claustrophobic elegance is equally important.
10. **Assemble one causal prompt.** The final instruction must read like a photographable scene, not a bag of adjectives.

### Compiled output checklist
- **STYLE:** NEON MEMORY DRIFT / CIS-18
- **SUBJECT LOCK:** exact user content preserved
- **CAMERA:** physical placement + framing + spatial behavior
- **LIGHT:** source + direction + contrast behavior
- **COLOR/MATERIALS:** object-level palette + tactile surfaces
- **ENVIRONMENT:** style-specific spatial/production-design logic
- **CHARACTER/ACTION:** posture + gaze + expression + movement
- **CORE ANCHORS:** all five represented in the prompt
- **ANTI-DRIFT:** Avoid-rule conflicts removed
- **FINAL PROMPT:** one integrated generation instruction


## Style Fidelity Gate
**Pass threshold:** average fidelity score >= **8.0/10**, Signature Fidelity >= **8.0**, Content Preservation >= **9.0**, and no other dimension below **7.5**.

### Profile-specific signature test
- Anchor 1: Time may feel stretched, skipped, repeated, or smeared.
- Anchor 2: Characters are often physically close but architecturally separated.
- Anchor 3: Foreground objects, doorframes, mirrors, glass, curtains, and narrow passageways create partial views.
- Anchor 4: Practical neon, tungsten, fluorescent, street color, or deep red/green can carry emotion.
- Anchor 5: Wide lenses used close can distort intimate urban interiors.

The image fails signature fidelity if fewer than four anchors are clearly visible.

### Score after generation
Score **Content Preservation, Camera/Composition, Lens/Space, Lighting, Color/Materials, Environment/Texture, Character/Action, and Signature Fidelity** from 0-10 using the global Fidelity Gate.

### Correction rule
If any passing condition fails, write a repair delta only for the failed dimensions, preserve successful dimensions, and regenerate. Run no more than two automatic repair cycles. Do not respond to failure by making the image generically "more cinematic."


### Research traceability record
**Traceability confidence:** MEDIUM-HIGH

**Evidence-use instruction:** Use these anchors to support the visual rules above. Do not infer unsupported technical specifications.

- [INST-2] BFI analysis of *Chungking Express* and broader Wong Kar-wai technique: step-printing, undercranking, neon city intimacy, repeated fragments, and subjective time.
- [INST-2] Criterion / BFI analysis of *In the Mood for Love*: concealed viewpoints, claustrophobic architecture, repetition, sensual texture, and controlled romantic tableaux.

---

# 19. PRESSURE-POINT REALISM
**Style ID:** CIS-19  
**Research Lineage:** Antoine Fuqua  
**Representative works studied:** *Training Day*, *Tears of the Sun*, *Shooter*, *The Equalizer*, *Southpaw*

## Research synthesis
The recurring grammar is **gritty physical realism that moves from objective geography into subjective pressure**. Research on *Southpaw* describes fight coverage that changes as the protagonist changes: earlier sequences can be more observational, while later fights move closer into bodily subjectivity. Across Fuqua's urban and action work, hard natural light, practical night sources, smoke, sweat, vehicles, weapon mechanics, street texture, and morally charged close-ups keep spectacle grounded in immediate consequence.

## Persistent visual invariants
- Action should feel physically consequential and spatially understandable.
- Camera distance can change to reflect a protagonist's mental state.
- Hard daylight, mixed urban night, fluorescent interiors, and practical sources contribute grit.
- Faces are often photographed under moral or physical pressure rather than glamour.
- Sweat, grime, smoke, rain, glass, metal, asphalt, gym texture, or weapon surfaces carry material weight.
- Street environments and vehicles are integrated into action geography.
- Subjective closeness increases when danger becomes personal.

## AI image-construction rules
### Composition
Use street corners, cars, doorways, gyms, alleys, rooftops, industrial interiors, training spaces, and rooms with clear exit/entry paths. Keep threat direction readable.

### Camera
Begin more observational when establishing geography; move physically closer, lower, or more reactive as pressure rises. For a single still, choose the camera distance that matches the psychological intensity of the moment.

### Lighting
Use hard sun, window shafts, sodium/LED street sources, fluorescent institutional light, vehicle headlights, fire, or practical lamps. Allow mixed temperatures and controlled shadow.

### Texture
Preserve sweat, bruises, fabric strain, smoke, chipped paint, metal, cracked pavement, and dust. Avoid clean action-figure surfaces.

### Avoid
- weightless gun-fu
- random shaky framing that hides geography
- glossy blue action grading
- pristine wardrobe after physical conflict
- heroic posing disconnected from stress

## AI Deployment Block
**PRESSURE-POINT REALISM / CIS-19:** Ground action in readable geography, real materials, practical light, bodily fatigue, and visible consequences. Let camera distance reflect psychological pressure: establish space objectively, then move closer and more reactive as danger becomes personal. Use hard daylight, mixed urban night, sweat, smoke, metal, glass, asphalt, gym or street texture, and morally tense faces. Avoid weightless spectacle, chaotic framing that hides space, polished action-figure surfaces, and heroic posing without stress.

## Style Compiler
**Compiler role:** Convert any user subject into this visual system without changing the user's required content.

### Five non-negotiable visual anchors
1. Action should feel physically consequential and spatially understandable.
2. Camera distance can change to reflect a protagonist's mental state.
3. Hard daylight, mixed urban night, fluorescent interiors, and practical sources contribute grit.
4. Faces are often photographed under moral or physical pressure rather than glamour.
5. Sweat, grime, smoke, rain, glass, metal, asphalt, gym texture, or weapon surfaces carry material weight.

**Minimum visibility rule:** At least four of these five anchors must be visibly present in the generated image. All five should be encoded in the prompt unless a locked user requirement conflicts.

### Style-specific compilation sequence
1. **Lock the subject.** Preserve every user-required identity/species/object, clothing item, color, prop, action, and setting constraint.
2. **Establish the visual premise.** Use the logic of **PRESSURE-POINT REALISM / CIS-19** rather than adding generic cinematic adjectives. The deployment block above is the governing summary.
3. **Compile camera + composition.** Translate the profile's camera/composition rules into one explicit camera location, distance, framing, spatial behavior, and foreground/background relationship.
4. **Compile light.** Name the physical or psychological source, direction, hardness/softness, contrast behavior, and what it does to faces/materials.
5. **Compile color + materials.** Put the style palette into actual objects, surfaces, weather, wardrobe, architecture, practical light, landscape, skin, or props before using global grading language.
6. **Compile environment.** Make the space carry the style through architecture, geography, social context, production design, weather, and tactile material behavior.
7. **Compile character/action direction.** Specify posture, gaze, expression, movement, and emotional temperature so the subject participates in the visual grammar rather than merely standing inside it.
8. **Enforce the five anchors.** Check the prompt line-by-line and add any missing core anchor in concrete visual form.
9. **Run the anti-drift filter.** Reject or rewrite these failure modes: weightless gun-fu; random shaky framing that hides geography; glossy blue action grading; pristine wardrobe after physical conflict; heroic posing disconnected from stress.
10. **Assemble one causal prompt.** The final instruction must read like a photographable scene, not a bag of adjectives.

### Compiled output checklist
- **STYLE:** PRESSURE-POINT REALISM / CIS-19
- **SUBJECT LOCK:** exact user content preserved
- **CAMERA:** physical placement + framing + spatial behavior
- **LIGHT:** source + direction + contrast behavior
- **COLOR/MATERIALS:** object-level palette + tactile surfaces
- **ENVIRONMENT:** style-specific spatial/production-design logic
- **CHARACTER/ACTION:** posture + gaze + expression + movement
- **CORE ANCHORS:** all five represented in the prompt
- **ANTI-DRIFT:** Avoid-rule conflicts removed
- **FINAL PROMPT:** one integrated generation instruction


## Style Fidelity Gate
**Pass threshold:** average fidelity score >= **8.0/10**, Signature Fidelity >= **8.0**, Content Preservation >= **9.0**, and no other dimension below **7.5**.

### Profile-specific signature test
- Anchor 1: Action should feel physically consequential and spatially understandable.
- Anchor 2: Camera distance can change to reflect a protagonist's mental state.
- Anchor 3: Hard daylight, mixed urban night, fluorescent interiors, and practical sources contribute grit.
- Anchor 4: Faces are often photographed under moral or physical pressure rather than glamour.
- Anchor 5: Sweat, grime, smoke, rain, glass, metal, asphalt, gym texture, or weapon surfaces carry material weight.

The image fails signature fidelity if fewer than four anchors are clearly visible.

### Score after generation
Score **Content Preservation, Camera/Composition, Lens/Space, Lighting, Color/Materials, Environment/Texture, Character/Action, and Signature Fidelity** from 0-10 using the global Fidelity Gate.

### Correction rule
If any passing condition fails, write a repair delta only for the failed dimensions, preserve successful dimensions, and regenerate. Run no more than two automatic repair cycles. Do not respond to failure by making the image generically "more cinematic."


### Research traceability record
**Traceability confidence:** MEDIUM-HIGH

**Evidence-use instruction:** Use these anchors to support the visual rules above. Do not infer unsupported technical specifications.

- [TECH-1] *American Cinematographer* / production interviews on *Southpaw*: fight coverage progressing from objective to subjective and camera strategy following character development.
- [CRIT-4] Comparative frame analysis across *Training Day*, *Southpaw*, and *The Equalizer*.

---

# 20. ELASTIC ABSURDIST OPTICS
**Style ID:** CIS-20  
**Research Lineage:** Yorgos Lanthimos  
**Representative works studied:** *Dogtooth*, *The Lobster*, *The Killing of a Sacred Deer*, *The Favourite*, *Poor Things*, *Kinds of Kindness*

## Research synthesis
The recurring system is **deadpan human behavior photographed through deliberately destabilizing spatial optics and formal staging**. Research on *The Favourite* and *Poor Things* documents extreme wide lenses, natural or practical light, unusual high/low camera positions, fluid camera movement, and an active rejection of conventional coverage. *Poor Things* expands the optical vocabulary further with fisheye-scale wides, portrait lenses with swirling falloff, porthole-like circular images, and camera behavior that evolves with the protagonist. The image can be lavish while the human behavior stays strangely flat or ceremonial.

## Persistent visual invariants
- Very wide lenses used close to subjects distort rooms and social relationships.
- Large spaces can make people look lonely, absurd, or institutionally trapped.
- Camera positions may be too high, too low, too far, or geometrically unexpected.
- Natural/available light often coexists with lavish production design.
- Long, fluid moves replace conventional shot/reverse-shot coverage.
- Deadpan or ritualized body language contrasts with optical extremity.
- Fisheye, porthole, swirl, or edge distortion may be used intentionally, not as random novelty.
- Symmetry can feel clinical, absurd, or oppressive rather than comforting.

## AI image-construction rules
### Lens
Use extreme wide perspective when the environment should dominate. Place the lens close enough that faces, hands, furniture, corridors, or ceilings stretch perceptually. For portraits, a swirling or antique-optic falloff may isolate the face while keeping the result strange rather than glamorous.

### Composition
Exploit huge ceilings, long corridors, formal gardens, palaces, sterile offices, hospitals, dining rooms, or oversized furniture. Position people slightly too centrally or too far apart. Let empty space become absurd.

### Lighting
Use windows, candles, daylight, overcast sky, practical fixtures, or deliberately theatrical sources that still belong to the world. Avoid generic cinematic rim light.

### Character direction
Keep expressions controlled, blank, polite, ritualized, or emotionally delayed. Let body placement become the joke or threat.

### Avoid
- fisheye on every image
- random distortion without social purpose
- quirky color as a substitute for composition
- conventional flattering portrait lenses
- busy coverage-style framing

## AI Deployment Block
**ELASTIC ABSURDIST OPTICS / CIS-20:** Photograph formal human behavior through spatially destabilizing optics. Use extreme wide lenses close to subjects, oversized rooms, high/low or geometrically unexpected camera positions, long visual axes, controlled symmetry, and large pockets of empty space. Let natural or practical light coexist with elaborate design. Keep faces and bodies deadpan or ritualized while the room bends around them. Use fisheye, porthole, or swirl effects selectively when they express social or psychological distortion. Avoid random quirk, flattering conventional portraiture, and distortion without purpose.

## Style Compiler
**Compiler role:** Convert any user subject into this visual system without changing the user's required content.

### Five non-negotiable visual anchors
1. Very wide lenses used close to subjects distort rooms and social relationships.
2. Large spaces can make people look lonely, absurd, or institutionally trapped.
3. Camera positions may be too high, too low, too far, or geometrically unexpected.
4. Natural/available light often coexists with lavish production design.
5. Long, fluid moves replace conventional shot/reverse-shot coverage.

**Minimum visibility rule:** At least four of these five anchors must be visibly present in the generated image. All five should be encoded in the prompt unless a locked user requirement conflicts.

### Style-specific compilation sequence
1. **Lock the subject.** Preserve every user-required identity/species/object, clothing item, color, prop, action, and setting constraint.
2. **Establish the visual premise.** Use the logic of **ELASTIC ABSURDIST OPTICS / CIS-20** rather than adding generic cinematic adjectives. The deployment block above is the governing summary.
3. **Compile camera + composition.** Translate the profile's camera/composition rules into one explicit camera location, distance, framing, spatial behavior, and foreground/background relationship.
4. **Compile light.** Name the physical or psychological source, direction, hardness/softness, contrast behavior, and what it does to faces/materials.
5. **Compile color + materials.** Put the style palette into actual objects, surfaces, weather, wardrobe, architecture, practical light, landscape, skin, or props before using global grading language.
6. **Compile environment.** Make the space carry the style through architecture, geography, social context, production design, weather, and tactile material behavior.
7. **Compile character/action direction.** Specify posture, gaze, expression, movement, and emotional temperature so the subject participates in the visual grammar rather than merely standing inside it.
8. **Enforce the five anchors.** Check the prompt line-by-line and add any missing core anchor in concrete visual form.
9. **Run the anti-drift filter.** Reject or rewrite these failure modes: fisheye on every image; random distortion without social purpose; quirky color as a substitute for composition; conventional flattering portrait lenses; busy coverage-style framing.
10. **Assemble one causal prompt.** The final instruction must read like a photographable scene, not a bag of adjectives.

### Compiled output checklist
- **STYLE:** ELASTIC ABSURDIST OPTICS / CIS-20
- **SUBJECT LOCK:** exact user content preserved
- **CAMERA:** physical placement + framing + spatial behavior
- **LIGHT:** source + direction + contrast behavior
- **COLOR/MATERIALS:** object-level palette + tactile surfaces
- **ENVIRONMENT:** style-specific spatial/production-design logic
- **CHARACTER/ACTION:** posture + gaze + expression + movement
- **CORE ANCHORS:** all five represented in the prompt
- **ANTI-DRIFT:** Avoid-rule conflicts removed
- **FINAL PROMPT:** one integrated generation instruction


## Style Fidelity Gate
**Pass threshold:** average fidelity score >= **8.0/10**, Signature Fidelity >= **8.0**, Content Preservation >= **9.0**, and no other dimension below **7.5**.

### Profile-specific signature test
- Anchor 1: Very wide lenses used close to subjects distort rooms and social relationships.
- Anchor 2: Large spaces can make people look lonely, absurd, or institutionally trapped.
- Anchor 3: Camera positions may be too high, too low, too far, or geometrically unexpected.
- Anchor 4: Natural/available light often coexists with lavish production design.
- Anchor 5: Long, fluid moves replace conventional shot/reverse-shot coverage.

The image fails signature fidelity if fewer than four anchors are clearly visible.

### Score after generation
Score **Content Preservation, Camera/Composition, Lens/Space, Lighting, Color/Materials, Environment/Texture, Character/Action, and Signature Fidelity** from 0-10 using the global Fidelity Gate.

### Correction rule
If any passing condition fails, write a repair delta only for the failed dimensions, preserve successful dimensions, and regenerate. Run no more than two automatic repair cycles. Do not respond to failure by making the image generically "more cinematic."


### Research traceability record
**Traceability confidence:** HIGH

**Evidence-use instruction:** Use these anchors to support the visual rules above. Do not infer unsupported technical specifications.

- [TECH-1] *American Cinematographer* — *Poor Things*: 8mm/10mm extreme wides, specialized portrait optics, circular/porthole imagery, and evolving subjective camera.
- [TECH-1] Kodak / cinematography coverage of *The Favourite*: wide lenses, natural light, fluid movement, and characters isolated inside huge spaces.

---

# 21. NEIGHBORHOOD WITNESS REALISM
**Style ID:** CIS-21  
**Research Lineage:** John Singleton  
**Representative works studied:** *Boyz n the Hood*, *Poetic Justice*, *Higher Learning*, *Baby Boy*

## Research synthesis
The durable image logic is **neighborhood geography used as moral and social information**. In *Boyz n the Hood*, streets, porches, stop signs, planes, fences, lawns, police presence, cars, bedrooms, and storefronts do more than locate the story: they show the systems pressing on young people. BFI analysis notes Singleton's layered foreground/background symbolism and shifts between measured observation and handheld emotional rupture. The camera generally respects ordinary space, which makes sudden violence or grief more destabilizing.

## Persistent visual invariants
- The neighborhood is a social system, not a generic urban backdrop.
- Foreground objects, signs, fences, aircraft, cars, and street layouts can carry thematic meaning.
- Family interiors and porches are intimate counterspaces to public danger.
- Camera behavior is usually observational until emotion or violence destabilizes it.
- Natural daylight, practical night sources, and location texture preserve realism.
- Group blocking reveals friendship, masculinity, family structure, conflict, and surveillance.
- Overhead or distanced views may turn aftermath into social witness rather than spectacle.
- Youth is photographed within systems already larger than the individual.

## AI image-construction rules
### Composition
Use streets with depth, porches, yards, sidewalks, fences, corner stores, school grounds, bedrooms, kitchens, cars, or neighborhood intersections. Include one environmental detail that quietly reveals pressure or history: a sign, police cruiser, distant plane, fence, memorial, boarded building, or family object.

### Camera
Favor eye-level or slightly low street perspective and medium-wide relational framing. Hold ordinary geography clearly. Move closer or become rougher only when emotion breaks normal social control.

### Lighting/color
Use credible sun, shade, porch light, streetlamp, car light, kitchen light, or school fluorescent sources. Color should belong to South Los Angeles or the chosen equivalent environment: dry sun, lawns, asphalt, painted homes, clothing, storefronts, and car paint.

### Character direction
People should inhabit the block: sitting, talking, fixing something, crossing the street, watching, arguing, grieving, playing. Avoid lineup-style posing.

### Avoid
- generic 'gritty hood' filters
- making poverty a decorative texture
- anonymous city skylines
- constant handheld chaos
- background blur that erases neighborhood geography

## AI Deployment Block
**NEIGHBORHOOD WITNESS REALISM / CIS-21:** Treat the neighborhood as a readable social system. Use eye-level street geography, porches, yards, cars, fences, homes, schools, and signs as meaningful context around people. Let foreground/background details quietly reveal pressure, surveillance, family, or history. Keep the camera observational and relational until grief or violence justifies greater instability. Use natural or practical light and inhabited group behavior. Avoid generic urban grit, decorative poverty, anonymous skylines, and blur that removes the community from the frame.

## Style Compiler
**Compiler role:** Convert any user subject into this visual system without changing the user's required content.

### Five non-negotiable visual anchors
1. The neighborhood is a social system, not a generic urban backdrop.
2. Foreground objects, signs, fences, aircraft, cars, and street layouts can carry thematic meaning.
3. Family interiors and porches are intimate counterspaces to public danger.
4. Camera behavior is usually observational until emotion or violence destabilizes it.
5. Natural daylight, practical night sources, and location texture preserve realism.

**Minimum visibility rule:** At least four of these five anchors must be visibly present in the generated image. All five should be encoded in the prompt unless a locked user requirement conflicts.

### Style-specific compilation sequence
1. **Lock the subject.** Preserve every user-required identity/species/object, clothing item, color, prop, action, and setting constraint.
2. **Establish the visual premise.** Use the logic of **NEIGHBORHOOD WITNESS REALISM / CIS-21** rather than adding generic cinematic adjectives. The deployment block above is the governing summary.
3. **Compile camera + composition.** Translate the profile's camera/composition rules into one explicit camera location, distance, framing, spatial behavior, and foreground/background relationship.
4. **Compile light.** Name the physical or psychological source, direction, hardness/softness, contrast behavior, and what it does to faces/materials.
5. **Compile color + materials.** Put the style palette into actual objects, surfaces, weather, wardrobe, architecture, practical light, landscape, skin, or props before using global grading language.
6. **Compile environment.** Make the space carry the style through architecture, geography, social context, production design, weather, and tactile material behavior.
7. **Compile character/action direction.** Specify posture, gaze, expression, movement, and emotional temperature so the subject participates in the visual grammar rather than merely standing inside it.
8. **Enforce the five anchors.** Check the prompt line-by-line and add any missing core anchor in concrete visual form.
9. **Run the anti-drift filter.** Reject or rewrite these failure modes: generic 'gritty hood' filters; making poverty a decorative texture; anonymous city skylines; constant handheld chaos; background blur that erases neighborhood geography.
10. **Assemble one causal prompt.** The final instruction must read like a photographable scene, not a bag of adjectives.

### Compiled output checklist
- **STYLE:** NEIGHBORHOOD WITNESS REALISM / CIS-21
- **SUBJECT LOCK:** exact user content preserved
- **CAMERA:** physical placement + framing + spatial behavior
- **LIGHT:** source + direction + contrast behavior
- **COLOR/MATERIALS:** object-level palette + tactile surfaces
- **ENVIRONMENT:** style-specific spatial/production-design logic
- **CHARACTER/ACTION:** posture + gaze + expression + movement
- **CORE ANCHORS:** all five represented in the prompt
- **ANTI-DRIFT:** Avoid-rule conflicts removed
- **FINAL PROMPT:** one integrated generation instruction


## Style Fidelity Gate
**Pass threshold:** average fidelity score >= **8.0/10**, Signature Fidelity >= **8.0**, Content Preservation >= **9.0**, and no other dimension below **7.5**.

### Profile-specific signature test
- Anchor 1: The neighborhood is a social system, not a generic urban backdrop.
- Anchor 2: Foreground objects, signs, fences, aircraft, cars, and street layouts can carry thematic meaning.
- Anchor 3: Family interiors and porches are intimate counterspaces to public danger.
- Anchor 4: Camera behavior is usually observational until emotion or violence destabilizes it.
- Anchor 5: Natural daylight, practical night sources, and location texture preserve realism.

The image fails signature fidelity if fewer than four anchors are clearly visible.

### Score after generation
Score **Content Preservation, Camera/Composition, Lens/Space, Lighting, Color/Materials, Environment/Texture, Character/Action, and Signature Fidelity** from 0-10 using the global Fidelity Gate.

### Correction rule
If any passing condition fails, write a repair delta only for the failed dimensions, preserve successful dimensions, and regenerate. Run no more than two automatic repair cycles. Do not respond to failure by making the image generically "more cinematic."


### Research traceability record
**Traceability confidence:** MEDIUM

**Evidence-use instruction:** Use these anchors to support the visual rules above. Do not infer unsupported technical specifications.

- [INST-2] BFI analysis of *Boyz n the Hood*: layered social symbolism, street geography, measured camera movement, overhead witness, and handheld grief.
- [CRIT-4] Comparative frame analysis of *Boyz n the Hood*, *Poetic Justice*, and *Baby Boy*.

---

# 22. SOCIAL GEOMETRY ENGINE
**Style ID:** CIS-22  
**Research Lineage:** Bong Joon-ho  
**Representative works studied:** *Memories of Murder*, *The Host*, *Snowpiercer*, *Okja*, *Parasite*

## Research synthesis
The recurring grammar is **social hierarchy converted into architecture, blocking, depth, and movement**. Research on *Parasite* makes this explicit: sets were designed around character paths and camera angles, windows become social screens, vertical movement maps class, and different homes produce different relationships to privacy, light, and depth. Bong's images can shift from comedy to thriller to horror without abandoning spatial clarity. The frame is often a machine whose geometry will later reveal or reverse its meaning.

## Persistent visual invariants
- Architecture encodes class, access, privacy, labor, and power.
- Vertical movement — stairs, hills, basements, elevated rooms — frequently carries social meaning.
- Windows, doors, tunnels, platforms, and corridors act as frames within frames.
- Blocking is precise enough that relationships can be understood without dialogue.
- Background action is often important; deep or moderate focus preserves it.
- Camera movement can be smooth and controlled even during tonal shifts.
- Visual setups may later return with reversed meaning.
- Humor and threat often coexist in the same clean composition.

## AI image-construction rules
### Spatial design
Before styling color, decide the social map. Who is above whom? Who can see outside? Who must descend? Who controls the doorway? Who occupies the clean open plane and who is compressed under objects or ceilings?

### Composition
Use stairs, split levels, windows, glass, basement thresholds, hallways, train cars, tunnels, dining tables, and rooms with multiple planes. Keep blocking readable. Let the environment diagram hierarchy.

### Lens/depth
Favor enough depth to understand where everyone is. Avoid isolating every subject with shallow focus. Use wider compositions when the architecture itself is the argument.

### Lighting/color
Let wealth, labor, nature, or confinement alter the light: large clean daylight openings versus small low windows; controlled architectural illumination versus dirty fluorescent basement light. Keep differences grounded in design.

### Avoid
- treating class as wardrobe alone
- random staircase imagery with no hierarchy
- muddy blocking
- one-note dark thriller grading
- excessive bokeh that destroys the social diagram

## AI Deployment Block
**SOCIAL GEOMETRY ENGINE / CIS-22:** Convert hierarchy into spatial design. Use levels, stairs, windows, basements, corridors, doors, platforms, and multiple depth planes to show who has access, privacy, light, space, and power. Block characters precisely so the social relationship is visible before dialogue. Keep enough depth for background information and allow comedy, threat, and reversal to inhabit the same controlled frame. Avoid shallow-focus isolation, random architecture, and generic thriller darkness. The environment must function as a social diagram.

## Style Compiler
**Compiler role:** Convert any user subject into this visual system without changing the user's required content.

### Five non-negotiable visual anchors
1. Architecture encodes class, access, privacy, labor, and power.
2. Vertical movement — stairs, hills, basements, elevated rooms — frequently carries social meaning.
3. Windows, doors, tunnels, platforms, and corridors act as frames within frames.
4. Blocking is precise enough that relationships can be understood without dialogue.
5. Background action is often important; deep or moderate focus preserves it.

**Minimum visibility rule:** At least four of these five anchors must be visibly present in the generated image. All five should be encoded in the prompt unless a locked user requirement conflicts.

### Style-specific compilation sequence
1. **Lock the subject.** Preserve every user-required identity/species/object, clothing item, color, prop, action, and setting constraint.
2. **Establish the visual premise.** Use the logic of **SOCIAL GEOMETRY ENGINE / CIS-22** rather than adding generic cinematic adjectives. The deployment block above is the governing summary.
3. **Compile camera + composition.** Translate the profile's camera/composition rules into one explicit camera location, distance, framing, spatial behavior, and foreground/background relationship.
4. **Compile light.** Name the physical or psychological source, direction, hardness/softness, contrast behavior, and what it does to faces/materials.
5. **Compile color + materials.** Put the style palette into actual objects, surfaces, weather, wardrobe, architecture, practical light, landscape, skin, or props before using global grading language.
6. **Compile environment.** Make the space carry the style through architecture, geography, social context, production design, weather, and tactile material behavior.
7. **Compile character/action direction.** Specify posture, gaze, expression, movement, and emotional temperature so the subject participates in the visual grammar rather than merely standing inside it.
8. **Enforce the five anchors.** Check the prompt line-by-line and add any missing core anchor in concrete visual form.
9. **Run the anti-drift filter.** Reject or rewrite these failure modes: treating class as wardrobe alone; random staircase imagery with no hierarchy; muddy blocking; one-note dark thriller grading; excessive bokeh that destroys the social diagram.
10. **Assemble one causal prompt.** The final instruction must read like a photographable scene, not a bag of adjectives.

### Compiled output checklist
- **STYLE:** SOCIAL GEOMETRY ENGINE / CIS-22
- **SUBJECT LOCK:** exact user content preserved
- **CAMERA:** physical placement + framing + spatial behavior
- **LIGHT:** source + direction + contrast behavior
- **COLOR/MATERIALS:** object-level palette + tactile surfaces
- **ENVIRONMENT:** style-specific spatial/production-design logic
- **CHARACTER/ACTION:** posture + gaze + expression + movement
- **CORE ANCHORS:** all five represented in the prompt
- **ANTI-DRIFT:** Avoid-rule conflicts removed
- **FINAL PROMPT:** one integrated generation instruction


## Style Fidelity Gate
**Pass threshold:** average fidelity score >= **8.0/10**, Signature Fidelity >= **8.0**, Content Preservation >= **9.0**, and no other dimension below **7.5**.

### Profile-specific signature test
- Anchor 1: Architecture encodes class, access, privacy, labor, and power.
- Anchor 2: Vertical movement — stairs, hills, basements, elevated rooms — frequently carries social meaning.
- Anchor 3: Windows, doors, tunnels, platforms, and corridors act as frames within frames.
- Anchor 4: Blocking is precise enough that relationships can be understood without dialogue.
- Anchor 5: Background action is often important; deep or moderate focus preserves it.

The image fails signature fidelity if fewer than four anchors are clearly visible.

### Score after generation
Score **Content Preservation, Camera/Composition, Lens/Space, Lighting, Color/Materials, Environment/Texture, Character/Action, and Signature Fidelity** from 0-10 using the global Fidelity Gate.

### Correction rule
If any passing condition fails, write a repair delta only for the failed dimensions, preserve successful dimensions, and regenerate. Run no more than two automatic repair cycles. Do not respond to failure by making the image generically "more cinematic."


### Research traceability record
**Traceability confidence:** MEDIUM

**Evidence-use instruction:** Use these anchors to support the visual rules above. Do not infer unsupported technical specifications.

- [CRIT-4] Bong Joon-ho interviews on *Parasite*: set architecture built around character movement and camera needs; windows and vertical space as class structure.
- [CRIT-4] ARRI / cinematography discussions of *Parasite*: lighting and environmental control used to distinguish class worlds.

---

# 23. GULF GOTHIC REVERIE
**Style ID:** CIS-23  
**Research Lineage:** Kasi Lemmons  
**Representative works studied:** *Eve's Bayou*, *Talk to Me*, *Black Nativity*, *Harriet*

## Research synthesis
The defining image language in the most visually influential work combines **Southern family realism, humid Gothic atmosphere, child/subjective memory, mirrors and visions, and lush natural texture**. *Eve's Bayou* uses the Louisiana environment not merely as scenery but as memory space: trees, water, porches, old interiors, candles, summer humidity, family portraits, mirrors, and psychic images coexist without a hard border between realism and the supernatural. Later work varies, but Lemmons continues to foreground Black interior life, family, music, history, and expressive portraiture.

## Persistent visual invariants
- Family space can feel loving, secretive, haunted, and sensuous at once.
- Southern landscape and weather carry memory.
- Mirrors, water, windows, reflections, photographs, and visions can bridge reality and memory.
- Warm amber/brown interior light contrasts with humid green/blue exterior space.
- Children or emotionally vulnerable observers may organize the point of view.
- Ensemble family tableaux are as important as individual close-ups.
- Texture — wood, lace, skin, sweat, candles, trees, water — gives the image sensory weight.
- Supernatural elements enter gently rather than as effects-heavy spectacle.

## AI image-construction rules
### Environment
Use porches, kitchens, bedrooms, family dining rooms, old wood, lace curtains, bayou water, moss, trees, fields, churches, or period domestic architecture. Let air feel warm and dense.

### Lighting
Favor window light, candles, lamps, dusk, moonlight, sun filtered through trees, and humid exterior atmosphere. Interiors may glow amber while exteriors remain green/blue and mysterious.

### Composition
Use mirrors, reflections, layered doorways, family groupings, and partially concealed observations. Let a child-height or intimate observer's perspective make adult spaces feel charged.

### Supernatural rule
Do not announce visions with fantasy glow. Keep them photographically continuous with the surrounding world; use reflection, stillness, double exposure feeling, altered focus, or subtle temporal ambiguity.

### Avoid
- generic plantation-Gothic clichés
- horror fog with no humidity/weather logic
- magical sparkles
- costume-drama stiffness
- reducing Black family life to trauma imagery

## AI Deployment Block
**GULF GOTHIC REVERIE / CIS-23:** Build a humid, tactile family world where realism, memory, and the supernatural overlap quietly. Use Southern domestic architecture, porches, old wood, trees, water, mirrors, reflections, amber practical interiors, green-blue exterior atmosphere, and layered family tableaux. Let visions enter through stillness, reflection, altered focus, or temporal ambiguity rather than fantasy effects. Keep Black family interior life rich and specific. Avoid generic Gothic clichés, magical glow, museum stiffness, and trauma-only imagery.

## Style Compiler
**Compiler role:** Convert any user subject into this visual system without changing the user's required content.

### Five non-negotiable visual anchors
1. Family space can feel loving, secretive, haunted, and sensuous at once.
2. Southern landscape and weather carry memory.
3. Mirrors, water, windows, reflections, photographs, and visions can bridge reality and memory.
4. Warm amber/brown interior light contrasts with humid green/blue exterior space.
5. Children or emotionally vulnerable observers may organize the point of view.

**Minimum visibility rule:** At least four of these five anchors must be visibly present in the generated image. All five should be encoded in the prompt unless a locked user requirement conflicts.

### Style-specific compilation sequence
1. **Lock the subject.** Preserve every user-required identity/species/object, clothing item, color, prop, action, and setting constraint.
2. **Establish the visual premise.** Use the logic of **GULF GOTHIC REVERIE / CIS-23** rather than adding generic cinematic adjectives. The deployment block above is the governing summary.
3. **Compile camera + composition.** Translate the profile's camera/composition rules into one explicit camera location, distance, framing, spatial behavior, and foreground/background relationship.
4. **Compile light.** Name the physical or psychological source, direction, hardness/softness, contrast behavior, and what it does to faces/materials.
5. **Compile color + materials.** Put the style palette into actual objects, surfaces, weather, wardrobe, architecture, practical light, landscape, skin, or props before using global grading language.
6. **Compile environment.** Make the space carry the style through architecture, geography, social context, production design, weather, and tactile material behavior.
7. **Compile character/action direction.** Specify posture, gaze, expression, movement, and emotional temperature so the subject participates in the visual grammar rather than merely standing inside it.
8. **Enforce the five anchors.** Check the prompt line-by-line and add any missing core anchor in concrete visual form.
9. **Run the anti-drift filter.** Reject or rewrite these failure modes: generic plantation-Gothic clichés; horror fog with no humidity/weather logic; magical sparkles; costume-drama stiffness; reducing Black family life to trauma imagery.
10. **Assemble one causal prompt.** The final instruction must read like a photographable scene, not a bag of adjectives.

### Compiled output checklist
- **STYLE:** GULF GOTHIC REVERIE / CIS-23
- **SUBJECT LOCK:** exact user content preserved
- **CAMERA:** physical placement + framing + spatial behavior
- **LIGHT:** source + direction + contrast behavior
- **COLOR/MATERIALS:** object-level palette + tactile surfaces
- **ENVIRONMENT:** style-specific spatial/production-design logic
- **CHARACTER/ACTION:** posture + gaze + expression + movement
- **CORE ANCHORS:** all five represented in the prompt
- **ANTI-DRIFT:** Avoid-rule conflicts removed
- **FINAL PROMPT:** one integrated generation instruction


## Style Fidelity Gate
**Pass threshold:** average fidelity score >= **8.0/10**, Signature Fidelity >= **8.0**, Content Preservation >= **9.0**, and no other dimension below **7.5**.

### Profile-specific signature test
- Anchor 1: Family space can feel loving, secretive, haunted, and sensuous at once.
- Anchor 2: Southern landscape and weather carry memory.
- Anchor 3: Mirrors, water, windows, reflections, photographs, and visions can bridge reality and memory.
- Anchor 4: Warm amber/brown interior light contrasts with humid green/blue exterior space.
- Anchor 5: Children or emotionally vulnerable observers may organize the point of view.

The image fails signature fidelity if fewer than four anchors are clearly visible.

### Score after generation
Score **Content Preservation, Camera/Composition, Lens/Space, Lighting, Color/Materials, Environment/Texture, Character/Action, and Signature Fidelity** from 0-10 using the global Fidelity Gate.

### Correction rule
If any passing condition fails, write a repair delta only for the failed dimensions, preserve successful dimensions, and regenerate. Run no more than two automatic repair cycles. Do not respond to failure by making the image generically "more cinematic."


### Research traceability record
**Traceability confidence:** MEDIUM-HIGH

**Evidence-use instruction:** Use these anchors to support the visual rules above. Do not infer unsupported technical specifications.

- [TECH-1] *American Cinematographer* / Criterion materials on *Eve's Bayou* and cinematographer Amy Vincent.
- [CRIT-4] Director-approved restoration and critical analysis emphasizing the film's Southern Gothic, memory, family, and photographic texture.

---

# 24. MONOLITHIC ATMOSPHERE
**Style ID:** CIS-24  
**Research Lineage:** Denis Villeneuve  
**Representative works studied:** *Prisoners*, *Sicario*, *Arrival*, *Blade Runner 2049*, *Dune*, *Dune: Part Two*

## Research synthesis
The recurring grammar is **human fragility inside monumental, atmospheric systems**. Research on *Arrival* describes a 'dirty sci-fi' approach: science fiction made normal, delicate, procedural, and emotionally haunted through restrained movement, muted color, and single-source feeling. *Blade Runner 2049* expands into monumental architecture, haze, stark shape, and distinct sequence palettes while still treating environment as psychological force. Villeneuve's large-scale films repeatedly use negative space, silhouettes, slow or deliberate camera movement, and weather/atmosphere to make size felt rather than merely shown.

## Persistent visual invariants
- Monumental architecture or landscape often dwarfs the human figure.
- Negative space is a primary compositional tool.
- Camera movement is generally deliberate, not frenetic.
- Atmosphere — fog, dust, rain, snow, smoke, heat, darkness — shapes depth.
- Lighting often feels like one dominant source or environmental condition.
- Palettes can be strongly sequence-specific: gray-green, orange dust, icy blue, sodium amber, monochrome desert.
- Silhouettes and graphic forms remain readable at large scale.
- Science fiction technology feels materially integrated rather than decorative.

## AI image-construction rules
### Composition
Use enormous walls, voids, deserts, industrial interiors, geometric vehicles, mountains, brutalist rooms, or vast skies. Make the person smaller than conventional hero framing when scale is the story. Use clean horizon lines and large uninterrupted shapes.

### Lighting
Choose one dominant environmental source: overcast sky, low sun, fog-diffused daylight, orange dust light, cold artificial ceiling, hard desert sun, or deep night practicals. Avoid lighting every object independently.

### Color
Limit the palette aggressively by sequence. Build mostly within one family and allow skin, costume, or one object to provide subtle contrast. Distinct worlds may use radically different palettes.

### Camera/lens
Favor restrained wide or normal perspective, slow push/pull feeling, and clear spatial hierarchy. Telephoto compression can be used for oppressive landscapes but should remain calm.

### Avoid
- busy sci-fi panels everywhere
- neon cyberpunk clutter
- constant lens flare
- fast action-camera chaos
- tiny atmospheric particles added without environmental cause
- generic teal/orange

## AI Deployment Block
**MONOLITHIC ATMOSPHERE / CIS-24:** Make the human figure feel fragile inside enormous architecture, landscape, weather, or machinery. Use negative space, clean monumental shapes, deliberate camera logic, one dominant environmental light condition, strong atmospheric depth, and an aggressively limited palette specific to the scene. Let fog, dust, rain, snow, heat, or darkness shape scale. Keep technology tactile and integrated. Avoid busy sci-fi decoration, generic neon, constant flares, frantic movement, and universal teal/orange grading.

## Style Compiler
**Compiler role:** Convert any user subject into this visual system without changing the user's required content.

### Five non-negotiable visual anchors
1. Monumental architecture or landscape often dwarfs the human figure.
2. Negative space is a primary compositional tool.
3. Camera movement is generally deliberate, not frenetic.
4. Atmosphere — fog, dust, rain, snow, smoke, heat, darkness — shapes depth.
5. Lighting often feels like one dominant source or environmental condition.

**Minimum visibility rule:** At least four of these five anchors must be visibly present in the generated image. All five should be encoded in the prompt unless a locked user requirement conflicts.

### Style-specific compilation sequence
1. **Lock the subject.** Preserve every user-required identity/species/object, clothing item, color, prop, action, and setting constraint.
2. **Establish the visual premise.** Use the logic of **MONOLITHIC ATMOSPHERE / CIS-24** rather than adding generic cinematic adjectives. The deployment block above is the governing summary.
3. **Compile camera + composition.** Translate the profile's camera/composition rules into one explicit camera location, distance, framing, spatial behavior, and foreground/background relationship.
4. **Compile light.** Name the physical or psychological source, direction, hardness/softness, contrast behavior, and what it does to faces/materials.
5. **Compile color + materials.** Put the style palette into actual objects, surfaces, weather, wardrobe, architecture, practical light, landscape, skin, or props before using global grading language.
6. **Compile environment.** Make the space carry the style through architecture, geography, social context, production design, weather, and tactile material behavior.
7. **Compile character/action direction.** Specify posture, gaze, expression, movement, and emotional temperature so the subject participates in the visual grammar rather than merely standing inside it.
8. **Enforce the five anchors.** Check the prompt line-by-line and add any missing core anchor in concrete visual form.
9. **Run the anti-drift filter.** Reject or rewrite these failure modes: busy sci-fi panels everywhere; neon cyberpunk clutter; constant lens flare; fast action-camera chaos; tiny atmospheric particles added without environmental cause; generic teal/orange.
10. **Assemble one causal prompt.** The final instruction must read like a photographable scene, not a bag of adjectives.

### Compiled output checklist
- **STYLE:** MONOLITHIC ATMOSPHERE / CIS-24
- **SUBJECT LOCK:** exact user content preserved
- **CAMERA:** physical placement + framing + spatial behavior
- **LIGHT:** source + direction + contrast behavior
- **COLOR/MATERIALS:** object-level palette + tactile surfaces
- **ENVIRONMENT:** style-specific spatial/production-design logic
- **CHARACTER/ACTION:** posture + gaze + expression + movement
- **CORE ANCHORS:** all five represented in the prompt
- **ANTI-DRIFT:** Avoid-rule conflicts removed
- **FINAL PROMPT:** one integrated generation instruction


## Style Fidelity Gate
**Pass threshold:** average fidelity score >= **8.0/10**, Signature Fidelity >= **8.0**, Content Preservation >= **9.0**, and no other dimension below **7.5**.

### Profile-specific signature test
- Anchor 1: Monumental architecture or landscape often dwarfs the human figure.
- Anchor 2: Negative space is a primary compositional tool.
- Anchor 3: Camera movement is generally deliberate, not frenetic.
- Anchor 4: Atmosphere — fog, dust, rain, snow, smoke, heat, darkness — shapes depth.
- Anchor 5: Lighting often feels like one dominant source or environmental condition.

The image fails signature fidelity if fewer than four anchors are clearly visible.

### Score after generation
Score **Content Preservation, Camera/Composition, Lens/Space, Lighting, Color/Materials, Environment/Texture, Character/Action, and Signature Fidelity** from 0-10 using the global Fidelity Gate.

### Correction rule
If any passing condition fails, write a repair delta only for the failed dimensions, preserve successful dimensions, and regenerate. Run no more than two automatic repair cycles. Do not respond to failure by making the image generically "more cinematic."


### Research traceability record
**Traceability confidence:** HIGH

**Evidence-use instruction:** Use these anchors to support the visual rules above. Do not infer unsupported technical specifications.

- [TECH-1] *American Cinematographer* — *Arrival*: dirty sci-fi, normal/everyday reality, dark restrained LUT, delicate camera movement, and single-source lighting logic.
- [TECH-1] *American Cinematographer* — *Blade Runner 2049*: brutalist/architectural references, environment as character, moving light, and sequence-specific color worlds.

---

# 25. GRIOT SOCIAL CLARITY
**Style ID:** CIS-25  
**Research Lineage:** Ousmane Sembene  
**Representative works studied:** *Black Girl*, *Mandabi*, *Xala*, *Camp de Thiaroye*, *Moolaade*

## Research synthesis
The recurring image logic is **socially lucid, symbolically charged, and grounded in everyday African life rather than exotic spectacle**. *Black Girl* combines realistic domestic spaces with objects that accumulate political meaning — most famously the mask — while later color films use costume, public space, household arrangement, signage, ritual, and community groups to make social contradictions visible. Sembene's visual clarity serves satire and critique: composition should make relations of class, colonial inheritance, gender, bureaucracy, and tradition easy to read.

## Persistent visual invariants
- Everyday environments are shown directly rather than exoticized.
- Symbolic objects emerge from normal life rather than floating as abstract metaphors.
- Frontal, clear, often relatively deep compositions support social legibility.
- Groups and public space matter as much as individual psychological portraiture.
- Costume and color can identify social role, tradition, bureaucracy, or contradiction.
- Satire may appear through juxtaposition inside a straightforward frame.
- Architecture, offices, compounds, streets, markets, gates, and homes reveal institutional relationships.
- The viewer is trusted to read the social arrangement without excessive visual manipulation.

## AI image-construction rules
### Composition
Favor direct, readable arrangements of people and environment. Show who sits, stands, waits, serves, commands, enters, or is excluded. Use gates, offices, courtyards, markets, houses, streets, and meeting spaces as social stages.

### Symbol rule
Choose one ordinary culturally grounded object — mask, bowl, letter, stamp, garment, vehicle, sign, chair, radio — and let its meaning arise from who handles it and where it appears.

### Lighting/color
Use natural sun, shade, practical interiors, and culturally specific textile/architecture color. Avoid cinematic exoticism or safari warmth as an automatic grade.

### Character direction
People should look engaged in work, family, bureaucracy, argument, ritual, waiting, trade, or community life. Avoid ethnographic posing for the viewer.

### Avoid
- exoticizing Africa
- generic sepia
- mystical haze attached to tradition
- shallow-focus tourism imagery
- symbols disconnected from daily life

## AI Deployment Block
**GRIOT SOCIAL CLARITY / CIS-25:** Make social relationships immediately readable through direct composition, group blocking, everyday architecture, public space, work, household life, costume, and culturally grounded objects. Use natural sun and practical interiors rather than exoticizing color grades. Let one ordinary object gather symbolic meaning through repetition and social use. Favor clear depth and social observation over glamorous isolation. Avoid generic sepia, safari warmth, mystical treatment of tradition, tourist framing, and symbols detached from ordinary life.

## Style Compiler
**Compiler role:** Convert any user subject into this visual system without changing the user's required content.

### Five non-negotiable visual anchors
1. Everyday environments are shown directly rather than exoticized.
2. Symbolic objects emerge from normal life rather than floating as abstract metaphors.
3. Frontal, clear, often relatively deep compositions support social legibility.
4. Groups and public space matter as much as individual psychological portraiture.
5. Costume and color can identify social role, tradition, bureaucracy, or contradiction.

**Minimum visibility rule:** At least four of these five anchors must be visibly present in the generated image. All five should be encoded in the prompt unless a locked user requirement conflicts.

### Style-specific compilation sequence
1. **Lock the subject.** Preserve every user-required identity/species/object, clothing item, color, prop, action, and setting constraint.
2. **Establish the visual premise.** Use the logic of **GRIOT SOCIAL CLARITY / CIS-25** rather than adding generic cinematic adjectives. The deployment block above is the governing summary.
3. **Compile camera + composition.** Translate the profile's camera/composition rules into one explicit camera location, distance, framing, spatial behavior, and foreground/background relationship.
4. **Compile light.** Name the physical or psychological source, direction, hardness/softness, contrast behavior, and what it does to faces/materials.
5. **Compile color + materials.** Put the style palette into actual objects, surfaces, weather, wardrobe, architecture, practical light, landscape, skin, or props before using global grading language.
6. **Compile environment.** Make the space carry the style through architecture, geography, social context, production design, weather, and tactile material behavior.
7. **Compile character/action direction.** Specify posture, gaze, expression, movement, and emotional temperature so the subject participates in the visual grammar rather than merely standing inside it.
8. **Enforce the five anchors.** Check the prompt line-by-line and add any missing core anchor in concrete visual form.
9. **Run the anti-drift filter.** Reject or rewrite these failure modes: exoticizing Africa; generic sepia; mystical haze attached to tradition; shallow-focus tourism imagery; symbols disconnected from daily life.
10. **Assemble one causal prompt.** The final instruction must read like a photographable scene, not a bag of adjectives.

### Compiled output checklist
- **STYLE:** GRIOT SOCIAL CLARITY / CIS-25
- **SUBJECT LOCK:** exact user content preserved
- **CAMERA:** physical placement + framing + spatial behavior
- **LIGHT:** source + direction + contrast behavior
- **COLOR/MATERIALS:** object-level palette + tactile surfaces
- **ENVIRONMENT:** style-specific spatial/production-design logic
- **CHARACTER/ACTION:** posture + gaze + expression + movement
- **CORE ANCHORS:** all five represented in the prompt
- **ANTI-DRIFT:** Avoid-rule conflicts removed
- **FINAL PROMPT:** one integrated generation instruction


## Style Fidelity Gate
**Pass threshold:** average fidelity score >= **8.0/10**, Signature Fidelity >= **8.0**, Content Preservation >= **9.0**, and no other dimension below **7.5**.

### Profile-specific signature test
- Anchor 1: Everyday environments are shown directly rather than exoticized.
- Anchor 2: Symbolic objects emerge from normal life rather than floating as abstract metaphors.
- Anchor 3: Frontal, clear, often relatively deep compositions support social legibility.
- Anchor 4: Groups and public space matter as much as individual psychological portraiture.
- Anchor 5: Costume and color can identify social role, tradition, bureaucracy, or contradiction.

The image fails signature fidelity if fewer than four anchors are clearly visible.

### Score after generation
Score **Content Preservation, Camera/Composition, Lens/Space, Lighting, Color/Materials, Environment/Texture, Character/Action, and Signature Fidelity** from 0-10 using the global Fidelity Gate.

### Correction rule
If any passing condition fails, write a repair delta only for the failed dimensions, preserve successful dimensions, and regenerate. Run no more than two automatic repair cycles. Do not respond to failure by making the image generically "more cinematic."


### Research traceability record
**Traceability confidence:** MEDIUM

**Evidence-use instruction:** Use these anchors to support the visual rules above. Do not infer unsupported technical specifications.

- [INST-2] Criterion analysis of *Black Girl*: realism combined with metaphysical/metafictional meaning, especially the charged mask as anti-assimilation symbol.
- [CRIT-4] Comparative study of social staging and color in *Mandabi*, *Xala*, and *Moolaade*.

---

# 26. POP CHIAROSCURO MELODRAMA
**Style ID:** CIS-26  
**Research Lineage:** Pedro Almodovar  
**Representative works studied:** *Women on the Verge of a Nervous Breakdown*, *All About My Mother*, *Talk to Her*, *Volver*, *The Skin I Live In*, *Pain and Glory*

## Research synthesis
The recurring grammar is **saturated production color, emotionally explicit objects and interiors, deep visual information, and painterly light applied to melodrama without visual chaos**. Almodovar has described predetermining color ranges and using deep focus so backgrounds remain emotionally active. His interiors are filled with art, furniture, textiles, flowers, kitchen objects, wallpaper, phones, books, and clothing that participate in characterization. Red is famous but not mandatory; the deeper principle is deliberate color separation and expressive domestic design.

## Persistent visual invariants
- Color is embedded in wardrobe, walls, furniture, art, food, flowers, and objects before grading.
- Reds, blues, yellows, greens, black, and cream may be intensely separated.
- Backgrounds often remain readable and emotionally significant.
- Domestic interiors are graphic, sensual, and character-specific.
- Light can be painterly and contrasty while skin remains flattering but real.
- Melodrama is expressed through composition and color rather than constant camera hysteria.
- Objects can function as emotional or narrative punctuation.
- Frontal, profile, and clean geometric compositions coexist with intimate close-ups.

## AI image-construction rules
### Color architecture
Choose 3-5 principal colors with strong separation. Assign them to actual surfaces: wall, sofa, dress, phone, flower, curtain, kitchen tile, artwork. Do not simply saturate the entire image.

### Depth
Keep enough background focus that the room contributes to the emotion. A lonely person can be intensified by a fully visible, colorful room rather than blurred away from it.

### Lighting
Use windows, lamps, practicals, daylight, and painterly directional sources. Allow chiaroscuro when the scene is darker, but preserve color integrity.

### Composition
Treat domestic spaces as designed emotional diagrams. Use doorways, mirrors, tables, beds, kitchens, corridors, and art as structured graphic elements.

### Avoid
- 'red everywhere' as a shortcut
- random maximalist clutter
- shallow bokeh that erases the room
- generic soap-opera lighting
- color with no object-level logic

## AI Deployment Block
**POP CHIAROSCURO MELODRAMA / CIS-26:** Build emotion through object-level color design. Select a small group of saturated, clearly separated colors and place them deliberately across wardrobe, walls, furniture, flowers, art, food, and props. Keep interiors readable with substantial depth, use painterly but motivated light, and arrange domestic geometry cleanly around the character. Let the room participate in melodrama. Avoid global saturation, red-only imitation, meaningless maximalism, erased backgrounds, and flat television lighting.

## Style Compiler
**Compiler role:** Convert any user subject into this visual system without changing the user's required content.

### Five non-negotiable visual anchors
1. Color is embedded in wardrobe, walls, furniture, art, food, flowers, and objects before grading.
2. Reds, blues, yellows, greens, black, and cream may be intensely separated.
3. Backgrounds often remain readable and emotionally significant.
4. Domestic interiors are graphic, sensual, and character-specific.
5. Light can be painterly and contrasty while skin remains flattering but real.

**Minimum visibility rule:** At least four of these five anchors must be visibly present in the generated image. All five should be encoded in the prompt unless a locked user requirement conflicts.

### Style-specific compilation sequence
1. **Lock the subject.** Preserve every user-required identity/species/object, clothing item, color, prop, action, and setting constraint.
2. **Establish the visual premise.** Use the logic of **POP CHIAROSCURO MELODRAMA / CIS-26** rather than adding generic cinematic adjectives. The deployment block above is the governing summary.
3. **Compile camera + composition.** Translate the profile's camera/composition rules into one explicit camera location, distance, framing, spatial behavior, and foreground/background relationship.
4. **Compile light.** Name the physical or psychological source, direction, hardness/softness, contrast behavior, and what it does to faces/materials.
5. **Compile color + materials.** Put the style palette into actual objects, surfaces, weather, wardrobe, architecture, practical light, landscape, skin, or props before using global grading language.
6. **Compile environment.** Make the space carry the style through architecture, geography, social context, production design, weather, and tactile material behavior.
7. **Compile character/action direction.** Specify posture, gaze, expression, movement, and emotional temperature so the subject participates in the visual grammar rather than merely standing inside it.
8. **Enforce the five anchors.** Check the prompt line-by-line and add any missing core anchor in concrete visual form.
9. **Run the anti-drift filter.** Reject or rewrite these failure modes: 'red everywhere' as a shortcut; random maximalist clutter; shallow bokeh that erases the room; generic soap-opera lighting; color with no object-level logic.
10. **Assemble one causal prompt.** The final instruction must read like a photographable scene, not a bag of adjectives.

### Compiled output checklist
- **STYLE:** POP CHIAROSCURO MELODRAMA / CIS-26
- **SUBJECT LOCK:** exact user content preserved
- **CAMERA:** physical placement + framing + spatial behavior
- **LIGHT:** source + direction + contrast behavior
- **COLOR/MATERIALS:** object-level palette + tactile surfaces
- **ENVIRONMENT:** style-specific spatial/production-design logic
- **CHARACTER/ACTION:** posture + gaze + expression + movement
- **CORE ANCHORS:** all five represented in the prompt
- **ANTI-DRIFT:** Avoid-rule conflicts removed
- **FINAL PROMPT:** one integrated generation instruction


## Style Fidelity Gate
**Pass threshold:** average fidelity score >= **8.0/10**, Signature Fidelity >= **8.0**, Content Preservation >= **9.0**, and no other dimension below **7.5**.

### Profile-specific signature test
- Anchor 1: Color is embedded in wardrobe, walls, furniture, art, food, flowers, and objects before grading.
- Anchor 2: Reds, blues, yellows, greens, black, and cream may be intensely separated.
- Anchor 3: Backgrounds often remain readable and emotionally significant.
- Anchor 4: Domestic interiors are graphic, sensual, and character-specific.
- Anchor 5: Light can be painterly and contrasty while skin remains flattering but real.

The image fails signature fidelity if fewer than four anchors are clearly visible.

### Score after generation
Score **Content Preservation, Camera/Composition, Lens/Space, Lighting, Color/Materials, Environment/Texture, Character/Action, and Signature Fidelity** from 0-10 using the global Fidelity Gate.

### Correction rule
If any passing condition fails, write a repair delta only for the failed dimensions, preserve successful dimensions, and regenerate. Run no more than two automatic repair cycles. Do not respond to failure by making the image generically "more cinematic."


### Research traceability record
**Traceability confidence:** HIGH

**Evidence-use instruction:** Use these anchors to support the visual rules above. Do not infer unsupported technical specifications.

- [TECH-1] Director notes / cinematography interviews for *Pain and Glory*: predetermined color ranges, chiaroscuro, maximum depth, and backgrounds used to intensify solitude.
- [TECH-1] Jose Luis Alcaine interviews: deep focus, softer skin rendering, painterly lighting, and sharp environmental detail.

---

# 27. LIBERATION COLLAGE
**Style ID:** CIS-27  
**Research Lineage:** Melvin Van Peebles  
**Representative works studied:** *The Story of a Three-Day Pass*, *Watermelon Man*, *Sweet Sweetback's Baadasssss Song*

## Research synthesis
The recurring grammar is **guerrilla image-making turned into psychological and political collage**. Critical research on *Sweet Sweetback* emphasizes jagged jump cuts, superimpositions, psychedelic color effects, monochromatic neon passages, accelerated montage, rough street texture, and sound-image collisions. The point is not visual cleanliness; the form itself refuses smooth institutional polish. Ordinary location footage can abruptly fracture into subjective color, repeated images, print-like overlays, or rhythmic visual assault.

## Persistent visual invariants
- Rough location realism and psychedelic abstraction coexist.
- Jump cuts, superimpositions, repeated frames, and abrupt montage can express urgency.
- Strong monochromatic colorization or neon-like fields may represent psychological distance.
- Street texture remains visible beneath experimentation.
- Zooms, freeze-like moments, optical printing, and layered exposure are valid tools.
- Image imperfection can communicate independence and resistance.
- Motion, music, bodies, and montage often operate as one rhythmic system.
- Formal rupture is more important than visual polish.

## AI image-construction rules
### Base image
Start with a believable street, apartment, road, club, police encounter, running body, crowd, or city fragment. Preserve grain, hard light, imperfect framing, and location texture.

### Collage layer
Add only 1-3 deliberate disruptions: duplicated silhouette, superimposed face, monochrome red/yellow/blue wash, repeated body positions, frame-within-frame, motion echo, posterized print texture, or jump-cut-like temporal layering.

### Color
Use strong colorization as a structural event, not a permanent filter. Let ordinary color return around it.

### Rhythm in a still
Imply repetition and propulsion through echoing figures, diagonals, repeated streetlights, running limbs, or layered exposure.

### Avoid
- polished vaporwave
- clean modern glitch effects
- arbitrary rainbow psychedelia
- smoothing grain or imperfect edges
- making experimentation feel like a software preset

## AI Deployment Block
**LIBERATION COLLAGE / CIS-27:** Begin with rough, believable location photography, then fracture it with a small number of aggressive analog-feeling interventions: jump-cut-like repetition, superimposed figures, monochromatic colorization, motion echo, posterized texture, zoom energy, or layered exposure. Keep street grain and imperfect framing visible beneath the collage. Let motion, body, music-like rhythm, and visual rupture feel inseparable. Avoid polished digital glitch aesthetics, rainbow psychedelia, and effects that look like modern software presets.

## Style Compiler
**Compiler role:** Convert any user subject into this visual system without changing the user's required content.

### Five non-negotiable visual anchors
1. Rough location realism and psychedelic abstraction coexist.
2. Jump cuts, superimpositions, repeated frames, and abrupt montage can express urgency.
3. Strong monochromatic colorization or neon-like fields may represent psychological distance.
4. Street texture remains visible beneath experimentation.
5. Zooms, freeze-like moments, optical printing, and layered exposure are valid tools.

**Minimum visibility rule:** At least four of these five anchors must be visibly present in the generated image. All five should be encoded in the prompt unless a locked user requirement conflicts.

### Style-specific compilation sequence
1. **Lock the subject.** Preserve every user-required identity/species/object, clothing item, color, prop, action, and setting constraint.
2. **Establish the visual premise.** Use the logic of **LIBERATION COLLAGE / CIS-27** rather than adding generic cinematic adjectives. The deployment block above is the governing summary.
3. **Compile camera + composition.** Translate the profile's camera/composition rules into one explicit camera location, distance, framing, spatial behavior, and foreground/background relationship.
4. **Compile light.** Name the physical or psychological source, direction, hardness/softness, contrast behavior, and what it does to faces/materials.
5. **Compile color + materials.** Put the style palette into actual objects, surfaces, weather, wardrobe, architecture, practical light, landscape, skin, or props before using global grading language.
6. **Compile environment.** Make the space carry the style through architecture, geography, social context, production design, weather, and tactile material behavior.
7. **Compile character/action direction.** Specify posture, gaze, expression, movement, and emotional temperature so the subject participates in the visual grammar rather than merely standing inside it.
8. **Enforce the five anchors.** Check the prompt line-by-line and add any missing core anchor in concrete visual form.
9. **Run the anti-drift filter.** Reject or rewrite these failure modes: polished vaporwave; clean modern glitch effects; arbitrary rainbow psychedelia; smoothing grain or imperfect edges; making experimentation feel like a software preset.
10. **Assemble one causal prompt.** The final instruction must read like a photographable scene, not a bag of adjectives.

### Compiled output checklist
- **STYLE:** LIBERATION COLLAGE / CIS-27
- **SUBJECT LOCK:** exact user content preserved
- **CAMERA:** physical placement + framing + spatial behavior
- **LIGHT:** source + direction + contrast behavior
- **COLOR/MATERIALS:** object-level palette + tactile surfaces
- **ENVIRONMENT:** style-specific spatial/production-design logic
- **CHARACTER/ACTION:** posture + gaze + expression + movement
- **CORE ANCHORS:** all five represented in the prompt
- **ANTI-DRIFT:** Avoid-rule conflicts removed
- **FINAL PROMPT:** one integrated generation instruction


## Style Fidelity Gate
**Pass threshold:** average fidelity score >= **8.0/10**, Signature Fidelity >= **8.0**, Content Preservation >= **9.0**, and no other dimension below **7.5**.

### Profile-specific signature test
- Anchor 1: Rough location realism and psychedelic abstraction coexist.
- Anchor 2: Jump cuts, superimpositions, repeated frames, and abrupt montage can express urgency.
- Anchor 3: Strong monochromatic colorization or neon-like fields may represent psychological distance.
- Anchor 4: Street texture remains visible beneath experimentation.
- Anchor 5: Zooms, freeze-like moments, optical printing, and layered exposure are valid tools.

The image fails signature fidelity if fewer than four anchors are clearly visible.

### Score after generation
Score **Content Preservation, Camera/Composition, Lens/Space, Lighting, Color/Materials, Environment/Texture, Character/Action, and Signature Fidelity** from 0-10 using the global Fidelity Gate.

### Correction rule
If any passing condition fails, write a repair delta only for the failed dimensions, preserve successful dimensions, and regenerate. Run no more than two automatic repair cycles. Do not respond to failure by making the image generically "more cinematic."


### Research traceability record
**Traceability confidence:** MEDIUM

**Evidence-use instruction:** Use these anchors to support the visual rules above. Do not infer unsupported technical specifications.

- [INST-2] Criterion analysis of *Sweet Sweetback's Baadasssss Song*: jagged jump cuts, superimpositions, psychedelic sound/image construction.
- [CRIT-4] Critical studies of its monochromatic neon passages and montage as psychological/political expression.

---

# 28. WANDERING CINECRITURE
**Style ID:** CIS-28  
**Research Lineage:** Agnes Varda  
**Representative works studied:** *Cleo from 5 to 7*, *Le Bonheur*, *Vagabond*, *The Gleaners and I*, *Faces Places*

## Research synthesis
The deeper system is **observational curiosity organized through writing with images**: documentary reality and overt formal play are allowed to coexist. *Cleo from 5 to 7* moves through real Paris with handheld and tracking immediacy while using mirrors, reflections, structural time, and playful editing. Across Varda's work, streets, faces, hands, beaches, objects, murals, photographs, discarded things, and color can all become essay material. The camera is curious rather than dominating; stylization does not cancel realism.

## Persistent visual invariants
- Walking, wandering, and tracking create discovery.
- Documentary observation can sit beside constructed tableaux, intertitles, color devices, or staged images.
- Mirrors, shop windows, photographs, posters, and reflective surfaces complicate identity.
- Small objects and overlooked people receive visual attention.
- The filmmaker's own curiosity or presence can be acknowledged rather than hidden.
- Color/black-and-white shifts may have structural or conceptual meaning.
- Places are encountered at human scale.
- Playfulness and mortality can coexist in one visual essay.

## AI image-construction rules
### Camera
Use eye-level walking perspective, gentle tracking feeling, handheld observation, or still-life attention. Do not over-polish the street.

### Composition
Notice the overlooked: hand, potato, old wall, sign, hair, mirror, poster, abandoned object, passerby, market display, beach debris. Build visual rhymes between person and object.

### Formal play
One deliberate intervention may be visible: a framed photograph within the scene, a color-to-monochrome division, handwritten sign, mirrored duplicate, playful scale contrast, or staged tableau inside documentary reality.

### Color
Use real location color boldly when present. Do not impose fashionable grading over ordinary streets and faces.

### Avoid
- clinical documentary neutrality
- glossy travel photography
- random whimsy with no observation behind it
- hiding all traces of subjectivity
- turning ordinary people into decorative background figures

## AI Deployment Block
**WANDERING CINECRITURE / CIS-28:** Treat image-making as curious visual writing. Work at human scale through real streets, rooms, beaches, markets, faces, hands, signs, mirrors, photographs, and overlooked objects. Combine documentary observation with one clear formal intervention or visual rhyme. Let walking, tracking, reflection, color shifts, and still-life attention create thought. Preserve ordinary location color and imperfection. Avoid glossy travel aesthetics, sterile documentary neutrality, and whimsy that is not rooted in something genuinely observed.

## Style Compiler
**Compiler role:** Convert any user subject into this visual system without changing the user's required content.

### Five non-negotiable visual anchors
1. Walking, wandering, and tracking create discovery.
2. Documentary observation can sit beside constructed tableaux, intertitles, color devices, or staged images.
3. Mirrors, shop windows, photographs, posters, and reflective surfaces complicate identity.
4. Small objects and overlooked people receive visual attention.
5. The filmmaker's own curiosity or presence can be acknowledged rather than hidden.

**Minimum visibility rule:** At least four of these five anchors must be visibly present in the generated image. All five should be encoded in the prompt unless a locked user requirement conflicts.

### Style-specific compilation sequence
1. **Lock the subject.** Preserve every user-required identity/species/object, clothing item, color, prop, action, and setting constraint.
2. **Establish the visual premise.** Use the logic of **WANDERING CINECRITURE / CIS-28** rather than adding generic cinematic adjectives. The deployment block above is the governing summary.
3. **Compile camera + composition.** Translate the profile's camera/composition rules into one explicit camera location, distance, framing, spatial behavior, and foreground/background relationship.
4. **Compile light.** Name the physical or psychological source, direction, hardness/softness, contrast behavior, and what it does to faces/materials.
5. **Compile color + materials.** Put the style palette into actual objects, surfaces, weather, wardrobe, architecture, practical light, landscape, skin, or props before using global grading language.
6. **Compile environment.** Make the space carry the style through architecture, geography, social context, production design, weather, and tactile material behavior.
7. **Compile character/action direction.** Specify posture, gaze, expression, movement, and emotional temperature so the subject participates in the visual grammar rather than merely standing inside it.
8. **Enforce the five anchors.** Check the prompt line-by-line and add any missing core anchor in concrete visual form.
9. **Run the anti-drift filter.** Reject or rewrite these failure modes: clinical documentary neutrality; glossy travel photography; random whimsy with no observation behind it; hiding all traces of subjectivity; turning ordinary people into decorative background figures.
10. **Assemble one causal prompt.** The final instruction must read like a photographable scene, not a bag of adjectives.

### Compiled output checklist
- **STYLE:** WANDERING CINECRITURE / CIS-28
- **SUBJECT LOCK:** exact user content preserved
- **CAMERA:** physical placement + framing + spatial behavior
- **LIGHT:** source + direction + contrast behavior
- **COLOR/MATERIALS:** object-level palette + tactile surfaces
- **ENVIRONMENT:** style-specific spatial/production-design logic
- **CHARACTER/ACTION:** posture + gaze + expression + movement
- **CORE ANCHORS:** all five represented in the prompt
- **ANTI-DRIFT:** Avoid-rule conflicts removed
- **FINAL PROMPT:** one integrated generation instruction


## Style Fidelity Gate
**Pass threshold:** average fidelity score >= **8.0/10**, Signature Fidelity >= **8.0**, Content Preservation >= **9.0**, and no other dimension below **7.5**.

### Profile-specific signature test
- Anchor 1: Walking, wandering, and tracking create discovery.
- Anchor 2: Documentary observation can sit beside constructed tableaux, intertitles, color devices, or staged images.
- Anchor 3: Mirrors, shop windows, photographs, posters, and reflective surfaces complicate identity.
- Anchor 4: Small objects and overlooked people receive visual attention.
- Anchor 5: The filmmaker's own curiosity or presence can be acknowledged rather than hidden.

The image fails signature fidelity if fewer than four anchors are clearly visible.

### Score after generation
Score **Content Preservation, Camera/Composition, Lens/Space, Lighting, Color/Materials, Environment/Texture, Character/Action, and Signature Fidelity** from 0-10 using the global Fidelity Gate.

### Correction rule
If any passing condition fails, write a repair delta only for the failed dimensions, preserve successful dimensions, and regenerate. Run no more than two automatic repair cycles. Do not respond to failure by making the image generically "more cinematic."


### Research traceability record
**Traceability confidence:** MEDIUM-HIGH

**Evidence-use instruction:** Use these anchors to support the visual rules above. Do not infer unsupported technical specifications.

- [INST-2] BFI analysis of Varda: tracking/walking, women in space, realism plus visible stylization, and color consciousness.
- [INST-2] Criterion analysis of *Cleo from 5 to 7*: verite immediacy, mirrors/reflections, handheld street observation, structural time, and formal play.

---

# 29. ARCHIVE-TRUTH REMIX
**Style ID:** CIS-29  
**Research Lineage:** Cheryl Dunye  
**Representative works studied:** *The Watermelon Woman*, *The Owls*, *Mommy Is Coming*

## Research synthesis
The defining grammar is **media hybridity used to question who gets documented and who disappears from archives**. *The Watermelon Woman* intentionally combines 16mm narrative photography, grainy consumer video, direct-to-camera address, mock-documentary interviews, and staged black-and-white archival photographs. The changes in image quality are not flaws to be normalized; they distinguish kinds of evidence, performance, memory, intimacy, and historical invention.

## Persistent visual invariants
- Multiple media textures can coexist inside one project.
- Direct address and talking-head framing create intimacy and self-awareness.
- Staged archival material may be intentionally credible but slightly uncanny.
- Domestic, retail, street, library, bar, and community spaces retain low-budget immediacy.
- Fiction and documentary evidence can deliberately contaminate one another.
- Queer intimacy is photographed casually rather than monumentalized.
- Media limitations are preserved as part of the meaning.
- The image can reveal the process of searching, recording, cataloguing, or inventing history.

## AI image-construction rules
### Media selection
Choose an explicit image medium for each layer: clean-ish 16mm narrative, consumer VHS/Hi8 video, black-and-white archival still, photocopy, library record, interview frame. If combining layers, make the difference visible.

### Composition
Favor direct camera address, casual handheld interiors, simple interview setups, shelves/records/photos, apartments, stores, community spaces, and intimate two-shots.

### Archive rule
If creating a fictive historical image, make it materially plausible: period clothing, monochrome silver-gelatin feel, age marks, simple studio or location posing. Do not over-dramatize it.

### Texture
Keep tape noise, grain, soft focus, exposure shifts, scan marks, or photographic wear appropriate to the chosen medium.

### Avoid
- cleaning every medium into one modern look
- fake VHS overlays that do not affect image behavior
- glossy prestige documentary lighting
- overproduced archival fakery
- treating queer life as an exotic subject

## AI Deployment Block
**ARCHIVE-TRUTH REMIX / CIS-29:** Build the image from visibly different media languages — 16mm narrative, consumer video, direct-address interview, staged black-and-white archive, photocopy, record, or home-media texture — and let their differences remain meaningful. Use casual community/domestic framing, research objects, photographs, shelves, and direct gaze. Make archival imagery materially plausible rather than spectacular. Preserve grain, tape softness, exposure shifts, and imperfect evidence. Avoid homogenizing everything into modern polish or adding fake retro overlays without changing the underlying image logic.

## Style Compiler
**Compiler role:** Convert any user subject into this visual system without changing the user's required content.

### Five non-negotiable visual anchors
1. Multiple media textures can coexist inside one project.
2. Direct address and talking-head framing create intimacy and self-awareness.
3. Staged archival material may be intentionally credible but slightly uncanny.
4. Domestic, retail, street, library, bar, and community spaces retain low-budget immediacy.
5. Fiction and documentary evidence can deliberately contaminate one another.

**Minimum visibility rule:** At least four of these five anchors must be visibly present in the generated image. All five should be encoded in the prompt unless a locked user requirement conflicts.

### Style-specific compilation sequence
1. **Lock the subject.** Preserve every user-required identity/species/object, clothing item, color, prop, action, and setting constraint.
2. **Establish the visual premise.** Use the logic of **ARCHIVE-TRUTH REMIX / CIS-29** rather than adding generic cinematic adjectives. The deployment block above is the governing summary.
3. **Compile camera + composition.** Translate the profile's camera/composition rules into one explicit camera location, distance, framing, spatial behavior, and foreground/background relationship.
4. **Compile light.** Name the physical or psychological source, direction, hardness/softness, contrast behavior, and what it does to faces/materials.
5. **Compile color + materials.** Put the style palette into actual objects, surfaces, weather, wardrobe, architecture, practical light, landscape, skin, or props before using global grading language.
6. **Compile environment.** Make the space carry the style through architecture, geography, social context, production design, weather, and tactile material behavior.
7. **Compile character/action direction.** Specify posture, gaze, expression, movement, and emotional temperature so the subject participates in the visual grammar rather than merely standing inside it.
8. **Enforce the five anchors.** Check the prompt line-by-line and add any missing core anchor in concrete visual form.
9. **Run the anti-drift filter.** Reject or rewrite these failure modes: cleaning every medium into one modern look; fake VHS overlays that do not affect image behavior; glossy prestige documentary lighting; overproduced archival fakery; treating queer life as an exotic subject.
10. **Assemble one causal prompt.** The final instruction must read like a photographable scene, not a bag of adjectives.

### Compiled output checklist
- **STYLE:** ARCHIVE-TRUTH REMIX / CIS-29
- **SUBJECT LOCK:** exact user content preserved
- **CAMERA:** physical placement + framing + spatial behavior
- **LIGHT:** source + direction + contrast behavior
- **COLOR/MATERIALS:** object-level palette + tactile surfaces
- **ENVIRONMENT:** style-specific spatial/production-design logic
- **CHARACTER/ACTION:** posture + gaze + expression + movement
- **CORE ANCHORS:** all five represented in the prompt
- **ANTI-DRIFT:** Avoid-rule conflicts removed
- **FINAL PROMPT:** one integrated generation instruction


## Style Fidelity Gate
**Pass threshold:** average fidelity score >= **8.0/10**, Signature Fidelity >= **8.0**, Content Preservation >= **9.0**, and no other dimension below **7.5**.

### Profile-specific signature test
- Anchor 1: Multiple media textures can coexist inside one project.
- Anchor 2: Direct address and talking-head framing create intimacy and self-awareness.
- Anchor 3: Staged archival material may be intentionally credible but slightly uncanny.
- Anchor 4: Domestic, retail, street, library, bar, and community spaces retain low-budget immediacy.
- Anchor 5: Fiction and documentary evidence can deliberately contaminate one another.

The image fails signature fidelity if fewer than four anchors are clearly visible.

### Score after generation
Score **Content Preservation, Camera/Composition, Lens/Space, Lighting, Color/Materials, Environment/Texture, Character/Action, and Signature Fidelity** from 0-10 using the global Fidelity Gate.

### Correction rule
If any passing condition fails, write a repair delta only for the failed dimensions, preserve successful dimensions, and regenerate. Run no more than two automatic repair cycles. Do not respond to failure by making the image generically "more cinematic."


### Research traceability record
**Traceability confidence:** MEDIUM-HIGH

**Evidence-use instruction:** Use these anchors to support the visual rules above. Do not infer unsupported technical specifications.

- [INST-2] BFI analysis of *The Watermelon Woman*: 16mm, grainy 1990s video, staged black-and-white archive, talking heads, and fiction/nonfiction layering.
- [INST-2] Criterion essays on Dunye's use of invented archive to address inaccessible queer Black history.

---

# 30. RAW SUBLIME FRICTION
**Style ID:** CIS-30  
**Research Lineage:** Lars von Trier  
**Representative works studied:** *Breaking the Waves*, *Dancer in the Dark*, *Dogville*, *Antichrist*, *Melancholia*

## Research synthesis
The recurring grammar thrives on **friction between raw, unstable human observation and highly controlled iconic imagery**. *Breaking the Waves* uses handheld widescreen and documentary roughness against melodrama. *Dancer in the Dark* pushes consumer/digital immediacy and fragmented coverage. *Melancholia* can move among faces with documentary-like reactivity, then stop for exquisitely staged painterly images. The system is therefore not simply 'shaky camera': it is the collision between unvarnished proximity and moments of overwhelming formal beauty or abstraction.

## Persistent visual invariants
- Handheld reactivity, zooms, reframing, and imperfect timing can make performance feel unprotected.
- Natural/practical light may be accepted even when unflattering.
- Cutting or framing can feel rough instead of smoothing emotion into classical coverage.
- Iconic tableaux appear as a contrasting mode, not the constant baseline.
- Grand landscapes, bodies, animals, weather, or celestial imagery may become symbolic.
- Digital/film texture may be manipulated rather than hidden.
- Performance remains central even when the image is formally abrasive.
- Beauty can be deliberately contaminated by dread.

## AI image-construction rules
### Mode A: raw proximity
Use handheld-feeling eye level, imperfect centering, practical light, rough exposure, faces caught mid-action, visible motion, and unprotected emotional presence.

### Mode B: sublime tableau
Use extremely controlled painterly composition, slowed implied motion, strong landscape/sky/body relationship, symbolic objects, and formal stillness.

### Friction rule
Do not mix both modes into mush. Choose one as the dominant image mode, then allow one element from the other to intrude.

### Color/texture
Accept subdued natural color, manipulated digital harshness, or painterly high contrast according to mode. Preserve imperfection where the raw mode is chosen.

### Avoid
- generic shaky-cam everywhere
- pretty apocalypse wallpaper
- glossy melancholy
- classical coverage that neutralizes performance
- symbolic imagery with no emotional contradiction

## AI Deployment Block
**RAW SUBLIME FRICTION / CIS-30:** Choose between two opposing visual modes: raw, reactive human proximity or highly controlled sublime tableau. In raw mode, accept handheld-feeling reframing, practical light, imperfect exposure, motion, and emotionally unprotected faces. In tableau mode, use painterly stillness, landscape, body, weather, or symbolic form with severe control. Let one element from the opposite mode contaminate the image. Avoid constant generic shaky-cam, decorative apocalypse beauty, and polished melancholy.

## Style Compiler
**Compiler role:** Convert any user subject into this visual system without changing the user's required content.

### Five non-negotiable visual anchors
1. Handheld reactivity, zooms, reframing, and imperfect timing can make performance feel unprotected.
2. Natural/practical light may be accepted even when unflattering.
3. Cutting or framing can feel rough instead of smoothing emotion into classical coverage.
4. Iconic tableaux appear as a contrasting mode, not the constant baseline.
5. Grand landscapes, bodies, animals, weather, or celestial imagery may become symbolic.

**Minimum visibility rule:** At least four of these five anchors must be visibly present in the generated image. All five should be encoded in the prompt unless a locked user requirement conflicts.

### Style-specific compilation sequence
1. **Lock the subject.** Preserve every user-required identity/species/object, clothing item, color, prop, action, and setting constraint.
2. **Establish the visual premise.** Use the logic of **RAW SUBLIME FRICTION / CIS-30** rather than adding generic cinematic adjectives. The deployment block above is the governing summary.
3. **Compile camera + composition.** Translate the profile's camera/composition rules into one explicit camera location, distance, framing, spatial behavior, and foreground/background relationship.
4. **Compile light.** Name the physical or psychological source, direction, hardness/softness, contrast behavior, and what it does to faces/materials.
5. **Compile color + materials.** Put the style palette into actual objects, surfaces, weather, wardrobe, architecture, practical light, landscape, skin, or props before using global grading language.
6. **Compile environment.** Make the space carry the style through architecture, geography, social context, production design, weather, and tactile material behavior.
7. **Compile character/action direction.** Specify posture, gaze, expression, movement, and emotional temperature so the subject participates in the visual grammar rather than merely standing inside it.
8. **Enforce the five anchors.** Check the prompt line-by-line and add any missing core anchor in concrete visual form.
9. **Run the anti-drift filter.** Reject or rewrite these failure modes: generic shaky-cam everywhere; pretty apocalypse wallpaper; glossy melancholy; classical coverage that neutralizes performance; symbolic imagery with no emotional contradiction.
10. **Assemble one causal prompt.** The final instruction must read like a photographable scene, not a bag of adjectives.

### Compiled output checklist
- **STYLE:** RAW SUBLIME FRICTION / CIS-30
- **SUBJECT LOCK:** exact user content preserved
- **CAMERA:** physical placement + framing + spatial behavior
- **LIGHT:** source + direction + contrast behavior
- **COLOR/MATERIALS:** object-level palette + tactile surfaces
- **ENVIRONMENT:** style-specific spatial/production-design logic
- **CHARACTER/ACTION:** posture + gaze + expression + movement
- **CORE ANCHORS:** all five represented in the prompt
- **ANTI-DRIFT:** Avoid-rule conflicts removed
- **FINAL PROMPT:** one integrated generation instruction


## Style Fidelity Gate
**Pass threshold:** average fidelity score >= **8.0/10**, Signature Fidelity >= **8.0**, Content Preservation >= **9.0**, and no other dimension below **7.5**.

### Profile-specific signature test
- Anchor 1: Handheld reactivity, zooms, reframing, and imperfect timing can make performance feel unprotected.
- Anchor 2: Natural/practical light may be accepted even when unflattering.
- Anchor 3: Cutting or framing can feel rough instead of smoothing emotion into classical coverage.
- Anchor 4: Iconic tableaux appear as a contrasting mode, not the constant baseline.
- Anchor 5: Grand landscapes, bodies, animals, weather, or celestial imagery may become symbolic.

The image fails signature fidelity if fewer than four anchors are clearly visible.

### Score after generation
Score **Content Preservation, Camera/Composition, Lens/Space, Lighting, Color/Materials, Environment/Texture, Character/Action, and Signature Fidelity** from 0-10 using the global Fidelity Gate.

### Correction rule
If any passing condition fails, write a repair delta only for the failed dimensions, preserve successful dimensions, and regenerate. Run no more than two automatic repair cycles. Do not respond to failure by making the image generically "more cinematic."


### Research traceability record
**Traceability confidence:** HIGH

**Evidence-use instruction:** Use these anchors to support the visual rules above. Do not infer unsupported technical specifications.

- [INST-2] Criterion analysis of *Breaking the Waves*: handheld CinemaScope, documentary rawness, manipulated color, and melodrama in tension with rough form.
- [TECH-1] *Filmmaker Magazine* / cinematography discussion of *Melancholia*: reactive documentary-style face coverage contrasted with meticulously designed iconic images.

---

# 31. SOVEREIGN ANGLE CINEMA
**Style ID:** CIS-31  
**Research Lineage:** Haile Gerima  
**Representative works studied:** *Harvest: 3,000 Years*, *Bush Mama*, *Sankofa*, *Teza*

## Research synthesis
The recurring grammar is **decolonized point of view expressed through camera position, fractured time, symbolic landscape, and refusal of inherited visual authority**. Gerima has discussed high and low camera angles not as decorative choices but as ways of empowering or disempowering subjects. His films frequently move through memory, history, present experience, and ancestral consciousness without smoothing those layers into conventional continuity. Harsh black-and-white, earth-rich color, frontal portraiture, symbolic objects, and charged landscapes help turn perspective itself into an argument.

## Persistent visual invariants
- Camera height and angle carry political and psychological power.
- History, memory, present time, and ancestral consciousness may coexist nonlinearly.
- Faces are often confronted directly and given moral weight.
- Landscape is historical ground rather than scenery.
- High contrast, grain, earth color, and strong silhouettes are legitimate expressive tools.
- Montage can rupture continuity to connect present oppression with historical memory.
- Symbolic objects and repeated images emerge from lived history.
- Conventional visual hierarchy may be deliberately inverted.

## AI image-construction rules
### Point-of-view rule
Before framing, decide who owns the image. Use low angle when a marginalized subject must acquire visual sovereignty; high angle when a system is suppressing or surveilling; eye level when witness and equality are required. Do not choose angle for 'coolness.'

### Time/memory
Use one visual bridge between temporal layers: repeated body position, ancestral object, landscape match, double exposure feeling, archival texture, shadow, doorway, or costume echo. The image should suggest historical presence without generic ghost effects.

### Lighting/color
For monochrome, permit hard contrast, deep blacks, bright sun, grain, and stark face modeling. For color, favor earth, dust, dark skin, vegetation, cloth, fire, sky, and materially grounded accents.

### Composition
Use frontal faces, community groupings, roads, fields, industrial/domestic spaces, historical architecture, and symbolic foreground objects. Let geography carry historical weight.

### Avoid
- colonial-postcard framing
- mystical 'Africa' haze
- random Dutch angles
- generic sepia history
- visual hierarchy that automatically centers institutional power

## AI Deployment Block
**SOVEREIGN ANGLE CINEMA / CIS-31:** Make camera position a statement about who owns the image. Choose high, low, or eye-level perspective according to power, surveillance, resistance, or witness. Combine frontal human presence with historically charged landscape, tactile grain, strong contrast or earth-based color, and one visual bridge between present time and memory or ancestry. Let montage-like echoes or repeated objects disrupt conventional chronology when needed. Avoid exoticized landscape, mystical haze, decorative angles, and inherited visual hierarchy that automatically privileges institutions over people.

## Style Compiler
**Compiler role:** Convert any user subject into this visual system without changing the user's required content.

### Five non-negotiable visual anchors
1. Camera height and angle carry political and psychological power.
2. History, memory, present time, and ancestral consciousness may coexist nonlinearly.
3. Faces are often confronted directly and given moral weight.
4. Landscape is historical ground rather than scenery.
5. High contrast, grain, earth color, and strong silhouettes are legitimate expressive tools.

**Minimum visibility rule:** At least four of these five anchors must be visibly present in the generated image. All five should be encoded in the prompt unless a locked user requirement conflicts.

### Style-specific compilation sequence
1. **Lock the subject.** Preserve every user-required identity/species/object, clothing item, color, prop, action, and setting constraint.
2. **Establish the visual premise.** Use the logic of **SOVEREIGN ANGLE CINEMA / CIS-31** rather than adding generic cinematic adjectives. The deployment block above is the governing summary.
3. **Compile camera + composition.** Translate the profile's camera/composition rules into one explicit camera location, distance, framing, spatial behavior, and foreground/background relationship.
4. **Compile light.** Name the physical or psychological source, direction, hardness/softness, contrast behavior, and what it does to faces/materials.
5. **Compile color + materials.** Put the style palette into actual objects, surfaces, weather, wardrobe, architecture, practical light, landscape, skin, or props before using global grading language.
6. **Compile environment.** Make the space carry the style through architecture, geography, social context, production design, weather, and tactile material behavior.
7. **Compile character/action direction.** Specify posture, gaze, expression, movement, and emotional temperature so the subject participates in the visual grammar rather than merely standing inside it.
8. **Enforce the five anchors.** Check the prompt line-by-line and add any missing core anchor in concrete visual form.
9. **Run the anti-drift filter.** Reject or rewrite these failure modes: colonial-postcard framing; mystical 'Africa' haze; random Dutch angles; generic sepia history; visual hierarchy that automatically centers institutional power.
10. **Assemble one causal prompt.** The final instruction must read like a photographable scene, not a bag of adjectives.

### Compiled output checklist
- **STYLE:** SOVEREIGN ANGLE CINEMA / CIS-31
- **SUBJECT LOCK:** exact user content preserved
- **CAMERA:** physical placement + framing + spatial behavior
- **LIGHT:** source + direction + contrast behavior
- **COLOR/MATERIALS:** object-level palette + tactile surfaces
- **ENVIRONMENT:** style-specific spatial/production-design logic
- **CHARACTER/ACTION:** posture + gaze + expression + movement
- **CORE ANCHORS:** all five represented in the prompt
- **ANTI-DRIFT:** Avoid-rule conflicts removed
- **FINAL PROMPT:** one integrated generation instruction


## Style Fidelity Gate
**Pass threshold:** average fidelity score >= **8.0/10**, Signature Fidelity >= **8.0**, Content Preservation >= **9.0**, and no other dimension below **7.5**.

### Profile-specific signature test
- Anchor 1: Camera height and angle carry political and psychological power.
- Anchor 2: History, memory, present time, and ancestral consciousness may coexist nonlinearly.
- Anchor 3: Faces are often confronted directly and given moral weight.
- Anchor 4: Landscape is historical ground rather than scenery.
- Anchor 5: High contrast, grain, earth color, and strong silhouettes are legitimate expressive tools.

The image fails signature fidelity if fewer than four anchors are clearly visible.

### Score after generation
Score **Content Preservation, Camera/Composition, Lens/Space, Lighting, Color/Materials, Environment/Texture, Character/Action, and Signature Fidelity** from 0-10 using the global Fidelity Gate.

### Correction rule
If any passing condition fails, write a repair delta only for the failed dimensions, preserve successful dimensions, and regenerate. Run no more than two automatic repair cycles. Do not respond to failure by making the image generically "more cinematic."


### Research traceability record
**Traceability confidence:** MEDIUM

**Evidence-use instruction:** Use these anchors to support the visual rules above. Do not infer unsupported technical specifications.

- [CRIT-4] Gerima interviews and MUBI materials: camera height/angle as an explicit system of empowerment and disempowerment.
- [CRIT-4] Comparative visual study of *Bush Mama*, *Sankofa*, and *Teza*: nonlinear memory, historical landscape, frontal presence, and decolonial image structure.

---

# 32. FORENSIC NOIR PRECISION
**Style ID:** CIS-32  
**Research Lineage:** David Fincher  
**Representative works studied:** *Se7en*, *Fight Club*, *Zodiac*, *The Social Network*, *Gone Girl*, *The Killer*

## Research synthesis
The recurring grammar is **meticulous controlled realism with noir pressure**. *Se7en* established a sharp, graphic 'color noir' world in which production design, costume, location, and lighting were unified before the image reached post. *Fight Club* uses more normal realism as a baseline and pushes toward heightened, contaminated imagery as Tyler's world takes over. Later digital work refines the system: exact camera placement, repeatable movement, carefully controlled low-light exposure, practical sources, subtle underexposure, cold/green/yellow/brown color families, and insert details that make process feel forensic.

## Persistent visual invariants
- Camera placement feels exact, deliberate, and repeatable.
- Movement is smooth, motivated, and mechanically precise when movement is required.
- Low-key light often comes from plausible practical/environmental sources.
- Color is limited, controlled, and integrated with set/costume design.
- Micro-details of objects, screens, tools, paperwork, wounds, mechanisms, or routines are narratively important.
- Rooms remain spatially coherent even when dark.
- Frames are often slightly underexposed rather than brightly cinematic.
- Handheld disorder is used selectively, not as a baseline.

## AI image-construction rules
### Composition
Use exact horizontals and verticals, controlled headroom, deliberate negative space, centered or carefully offset subjects, clean room geometry, windows, desks, hallways, institutional spaces, basements, offices, cars, and anonymous modern architecture.

### Camera/lens
Favor stable normal-to-moderately-wide perspective. If movement is implied, it should feel like an exact dolly, stabilized track, or impossible-but-perfect camera pass rather than handheld drift.

### Lighting
Use practical lamps, computer screens, windows, fluorescent fixtures, street light, overcast sky, ceiling sources, or motivated pools. Keep blacks clean, shadows controlled, and highlights disciplined.

### Color
Limit the family: cyan-gray, sickly green, nicotine yellow, brown, steel, black, muted flesh. Let warmer or brighter color become meaningful because it is rare.

### Detail rule
Include one precise procedural detail: typed page, fingerprint, file folder, screen, tool, coffee stain, instrument, cable, weapon component, notebook, or hand performing a specific task.

### Avoid
- generic blue thriller grading
- random handheld shake
- crushed muddy blacks
- glossy neon
- uncontrolled clutter
- fake 'darkness' that destroys spatial legibility

## AI Deployment Block
**FORENSIC NOIR PRECISION / CIS-32:** Construct the frame with exact camera placement, controlled geometry, disciplined low-key practical light, limited color, clean dark values, and procedural detail. Keep rooms legible even when underexposed. Movement should feel mechanically smooth and motivated rather than casually handheld. Integrate set, costume, props, screens, paperwork, and tools into one visual system. Use muted green, cyan, nicotine, brown, steel, or black only when supported by the environment. Avoid generic thriller blue, muddy blacks, random shake, glossy neon, and uncontrolled clutter.

## Style Compiler
**Compiler role:** Convert any user subject into this visual system without changing the user's required content.

### Five non-negotiable visual anchors
1. Camera placement feels exact, deliberate, and repeatable.
2. Movement is smooth, motivated, and mechanically precise when movement is required.
3. Low-key light often comes from plausible practical/environmental sources.
4. Color is limited, controlled, and integrated with set/costume design.
5. Micro-details of objects, screens, tools, paperwork, wounds, mechanisms, or routines are narratively important.

**Minimum visibility rule:** At least four of these five anchors must be visibly present in the generated image. All five should be encoded in the prompt unless a locked user requirement conflicts.

### Style-specific compilation sequence
1. **Lock the subject.** Preserve every user-required identity/species/object, clothing item, color, prop, action, and setting constraint.
2. **Establish the visual premise.** Use the logic of **FORENSIC NOIR PRECISION / CIS-32** rather than adding generic cinematic adjectives. The deployment block above is the governing summary.
3. **Compile camera + composition.** Translate the profile's camera/composition rules into one explicit camera location, distance, framing, spatial behavior, and foreground/background relationship.
4. **Compile light.** Name the physical or psychological source, direction, hardness/softness, contrast behavior, and what it does to faces/materials.
5. **Compile color + materials.** Put the style palette into actual objects, surfaces, weather, wardrobe, architecture, practical light, landscape, skin, or props before using global grading language.
6. **Compile environment.** Make the space carry the style through architecture, geography, social context, production design, weather, and tactile material behavior.
7. **Compile character/action direction.** Specify posture, gaze, expression, movement, and emotional temperature so the subject participates in the visual grammar rather than merely standing inside it.
8. **Enforce the five anchors.** Check the prompt line-by-line and add any missing core anchor in concrete visual form.
9. **Run the anti-drift filter.** Reject or rewrite these failure modes: generic blue thriller grading; random handheld shake; crushed muddy blacks; glossy neon; uncontrolled clutter; fake 'darkness' that destroys spatial legibility.
10. **Assemble one causal prompt.** The final instruction must read like a photographable scene, not a bag of adjectives.

### Compiled output checklist
- **STYLE:** FORENSIC NOIR PRECISION / CIS-32
- **SUBJECT LOCK:** exact user content preserved
- **CAMERA:** physical placement + framing + spatial behavior
- **LIGHT:** source + direction + contrast behavior
- **COLOR/MATERIALS:** object-level palette + tactile surfaces
- **ENVIRONMENT:** style-specific spatial/production-design logic
- **CHARACTER/ACTION:** posture + gaze + expression + movement
- **CORE ANCHORS:** all five represented in the prompt
- **ANTI-DRIFT:** Avoid-rule conflicts removed
- **FINAL PROMPT:** one integrated generation instruction


## Style Fidelity Gate
**Pass threshold:** average fidelity score >= **8.0/10**, Signature Fidelity >= **8.0**, Content Preservation >= **9.0**, and no other dimension below **7.5**.

### Profile-specific signature test
- Anchor 1: Camera placement feels exact, deliberate, and repeatable.
- Anchor 2: Movement is smooth, motivated, and mechanically precise when movement is required.
- Anchor 3: Low-key light often comes from plausible practical/environmental sources.
- Anchor 4: Color is limited, controlled, and integrated with set/costume design.
- Anchor 5: Micro-details of objects, screens, tools, paperwork, wounds, mechanisms, or routines are narratively important.

The image fails signature fidelity if fewer than four anchors are clearly visible.

### Score after generation
Score **Content Preservation, Camera/Composition, Lens/Space, Lighting, Color/Materials, Environment/Texture, Character/Action, and Signature Fidelity** from 0-10 using the global Fidelity Gate.

### Correction rule
If any passing condition fails, write a repair delta only for the failed dimensions, preserve successful dimensions, and regenerate. Run no more than two automatic repair cycles. Do not respond to failure by making the image generically "more cinematic."


### Research traceability record
**Traceability confidence:** HIGH

**Evidence-use instruction:** Use these anchors to support the visual rules above. Do not infer unsupported technical specifications.

- [TECH-1] *American Cinematographer* — *Se7en*: sharp graphic 'color noir,' gritty stylization, and unified camera/production/costume design.
- [TECH-1] *American Cinematographer* — *Fight Club*: realistic baseline versus heightened Tyler-world imagery, practical/location lighting, and controlled visual deterioration.

---

# 33. EVERYDAY POETIC WITNESS
**Style ID:** CIS-33  
**Research Lineage:** Charles Burnett  
**Representative works studied:** *Killer of Sheep*, *My Brother's Wedding*, *To Sleep with Anger*

## Research synthesis
The recurring grammar is **quiet observational realism that discovers poetry inside ordinary Black working-class life without announcing the poetry as style**. Research on *Killer of Sheep* emphasizes minimal lighting, modest production resources, scratchy film texture, a camera that often settles into place and observes, and a documentary-like relationship to real community environments. Children, adults, labor, play, fatigue, marriage, music, animals, windows, kitchens, alleys, and small household gestures share the same visual importance.

## Persistent visual invariants
- Observation precedes aesthetic display.
- Available/minimal light and modest film texture are accepted rather than overcorrected.
- Static or gently composed frames let behavior develop naturally.
- Children and adults inhabit the same social world without sentimental separation.
- Everyday objects and labor can become lyrical through attention.
- Community events and domestic rituals feel discovered rather than staged for spectacle.
- Black family interiors are rendered with tenderness and contradiction.
- Episodic/vignette structure favors moments over conventional visual climax.

## AI image-construction rules
### Composition
Set the camera where a patient witness might stand: kitchen doorway, yard edge, sidewalk, window, alley, living room corner, workplace, stairwell. Allow bodies to enter and leave naturally. Keep ordinary clutter and household evidence.

### Lighting
Use window light, bare bulbs, porch light, exterior sun/shade, practical kitchen or living-room sources. Do not 'fix' every shadow into studio perfection.

### Texture
Use restrained 16mm-like grain, modest contrast, occasional exposure imperfection, weathered surfaces, laundry, tools, dishes, toys, furniture, fences, and lived-in walls.

### Human direction
Favor work, waiting, play, teasing, fatigue, quiet affection, boredom, argument, or reflection. Avoid performance poses.

### Avoid
- poverty porn
- polished nostalgic sepia
- dramatic prestige lighting
- aestheticizing every ordinary object
- artificial background extras

## AI Deployment Block
**EVERYDAY POETIC WITNESS / CIS-33:** Observe ordinary Black working-class life patiently and without spectacle. Use a static or gently composed human-height camera, available/practical light, modest film grain, lived-in homes and streets, real household clutter, labor, children, play, fatigue, and small gestures. Let poetry emerge from attention rather than from decorative lighting or posing. Preserve imperfect surfaces and exposure when believable. Avoid poverty spectacle, nostalgic sepia, prestige-drama polish, and turning ordinary people into background decoration.

## Style Compiler
**Compiler role:** Convert any user subject into this visual system without changing the user's required content.

### Five non-negotiable visual anchors
1. Observation precedes aesthetic display.
2. Available/minimal light and modest film texture are accepted rather than overcorrected.
3. Static or gently composed frames let behavior develop naturally.
4. Children and adults inhabit the same social world without sentimental separation.
5. Everyday objects and labor can become lyrical through attention.

**Minimum visibility rule:** At least four of these five anchors must be visibly present in the generated image. All five should be encoded in the prompt unless a locked user requirement conflicts.

### Style-specific compilation sequence
1. **Lock the subject.** Preserve every user-required identity/species/object, clothing item, color, prop, action, and setting constraint.
2. **Establish the visual premise.** Use the logic of **EVERYDAY POETIC WITNESS / CIS-33** rather than adding generic cinematic adjectives. The deployment block above is the governing summary.
3. **Compile camera + composition.** Translate the profile's camera/composition rules into one explicit camera location, distance, framing, spatial behavior, and foreground/background relationship.
4. **Compile light.** Name the physical or psychological source, direction, hardness/softness, contrast behavior, and what it does to faces/materials.
5. **Compile color + materials.** Put the style palette into actual objects, surfaces, weather, wardrobe, architecture, practical light, landscape, skin, or props before using global grading language.
6. **Compile environment.** Make the space carry the style through architecture, geography, social context, production design, weather, and tactile material behavior.
7. **Compile character/action direction.** Specify posture, gaze, expression, movement, and emotional temperature so the subject participates in the visual grammar rather than merely standing inside it.
8. **Enforce the five anchors.** Check the prompt line-by-line and add any missing core anchor in concrete visual form.
9. **Run the anti-drift filter.** Reject or rewrite these failure modes: poverty porn; polished nostalgic sepia; dramatic prestige lighting; aestheticizing every ordinary object; artificial background extras.
10. **Assemble one causal prompt.** The final instruction must read like a photographable scene, not a bag of adjectives.

### Compiled output checklist
- **STYLE:** EVERYDAY POETIC WITNESS / CIS-33
- **SUBJECT LOCK:** exact user content preserved
- **CAMERA:** physical placement + framing + spatial behavior
- **LIGHT:** source + direction + contrast behavior
- **COLOR/MATERIALS:** object-level palette + tactile surfaces
- **ENVIRONMENT:** style-specific spatial/production-design logic
- **CHARACTER/ACTION:** posture + gaze + expression + movement
- **CORE ANCHORS:** all five represented in the prompt
- **ANTI-DRIFT:** Avoid-rule conflicts removed
- **FINAL PROMPT:** one integrated generation instruction


## Style Fidelity Gate
**Pass threshold:** average fidelity score >= **8.0/10**, Signature Fidelity >= **8.0**, Content Preservation >= **9.0**, and no other dimension below **7.5**.

### Profile-specific signature test
- Anchor 1: Observation precedes aesthetic display.
- Anchor 2: Available/minimal light and modest film texture are accepted rather than overcorrected.
- Anchor 3: Static or gently composed frames let behavior develop naturally.
- Anchor 4: Children and adults inhabit the same social world without sentimental separation.
- Anchor 5: Everyday objects and labor can become lyrical through attention.

The image fails signature fidelity if fewer than four anchors are clearly visible.

### Score after generation
Score **Content Preservation, Camera/Composition, Lens/Space, Lighting, Color/Materials, Environment/Texture, Character/Action, and Signature Fidelity** from 0-10 using the global Fidelity Gate.

### Correction rule
If any passing condition fails, write a repair delta only for the failed dimensions, preserve successful dimensions, and regenerate. Run no more than two automatic repair cycles. Do not respond to failure by making the image generically "more cinematic."


### Research traceability record
**Traceability confidence:** HIGH

**Evidence-use instruction:** Use these anchors to support the visual rules above. Do not infer unsupported technical specifications.

- [TECH-1] BFI / *Filmmaker Magazine* discussions of *Killer of Sheep*: documentary-like observation, minimal lighting, scratchy texture, and camera-as-witness.
- [INST-2] Criterion analysis of Burnett's naturalistic yet poetic Black family interiors.

---

# 34. OPERATIONAL IMMERSION
**Style ID:** CIS-34  
**Research Lineage:** Kathryn Bigelow  
**Representative works studied:** *Point Break*, *The Hurt Locker*, *Zero Dark Thirty*, *Detroit*, *A House of Dynamite*

## Research synthesis
The recurring grammar is **physically immersive, procedurally truthful action observed from multiple documentary-like positions**. Research around *The Hurt Locker*, *Zero Dark Thirty*, and *Detroit* emphasizes raw immediacy, multi-camera coverage, 16mm or documentary-derived texture, scene lighting that lets actors move freely, and camera operators reacting inside 360-degree environments. The objective is not shaky spectacle; it is the sensation that an event is unfolding beyond the camera's control while geography, procedure, and bodily risk remain intelligible.

## Persistent visual invariants
- Camera behaves like an embedded witness rather than an omniscient action machine.
- Multiple observational positions may coexist: long lens, shoulder camera, vehicle mount, wide situational view.
- Action spaces remain operationally understandable.
- Natural light, dust, heat, darkness, practical sources, and atmospheric conditions are accepted as part of the event.
- Actors must be able to move through space without waiting for perfect marks.
- Zooms/reframes can feel like real-time response.
- Threat can emerge from ordinary background information.
- Physical procedure — bomb suit, weapon, vehicle, door, radio, crowd control, surveillance — is visually specific.

## AI image-construction rules
### Geography
Show enough street, room, vehicle, field, corridor, crowd, or compound to understand the operational problem. Position obstacles and possible threats clearly.

### Camera
Use shoulder-height, long-lens observation, reactive zoom feeling, handheld proximity, or a wider situational frame. Keep horizon and major geography believable even when the image feels urgent.

### Lighting
Let the environment lead: hard sun, dusty haze, overcast, weak practical night, vehicle headlights, fluorescent interiors, fire, flashlight. Avoid beauty lighting.

### Detail
Include real procedural objects and body mechanics. Hands should grip tools plausibly; equipment should have weight; protective gear should affect posture.

### Avoid
- fake chaotic shake
- impossible action geography
- glamorous hero lighting
- spotless gear
- cinematic smoke with no source
- poses that ignore procedure

## AI Deployment Block
**OPERATIONAL IMMERSION / CIS-34:** Put the viewer inside a real unfolding operation. Preserve readable geography, procedural detail, natural/practical light, dust/heat/weather, physically believable equipment, and a camera that reacts rather than performs. Use embedded shoulder perspective, long-lens observation, reactive reframing, or a situational wide according to the moment. Let actors move freely through 360-degree space. Avoid fake shake, beauty lighting, impossible geography, spotless equipment, and heroic posing that contradicts real procedure.

## Style Compiler
**Compiler role:** Convert any user subject into this visual system without changing the user's required content.

### Five non-negotiable visual anchors
1. Camera behaves like an embedded witness rather than an omniscient action machine.
2. Multiple observational positions may coexist: long lens, shoulder camera, vehicle mount, wide situational view.
3. Action spaces remain operationally understandable.
4. Natural light, dust, heat, darkness, practical sources, and atmospheric conditions are accepted as part of the event.
5. Actors must be able to move through space without waiting for perfect marks.

**Minimum visibility rule:** At least four of these five anchors must be visibly present in the generated image. All five should be encoded in the prompt unless a locked user requirement conflicts.

### Style-specific compilation sequence
1. **Lock the subject.** Preserve every user-required identity/species/object, clothing item, color, prop, action, and setting constraint.
2. **Establish the visual premise.** Use the logic of **OPERATIONAL IMMERSION / CIS-34** rather than adding generic cinematic adjectives. The deployment block above is the governing summary.
3. **Compile camera + composition.** Translate the profile's camera/composition rules into one explicit camera location, distance, framing, spatial behavior, and foreground/background relationship.
4. **Compile light.** Name the physical or psychological source, direction, hardness/softness, contrast behavior, and what it does to faces/materials.
5. **Compile color + materials.** Put the style palette into actual objects, surfaces, weather, wardrobe, architecture, practical light, landscape, skin, or props before using global grading language.
6. **Compile environment.** Make the space carry the style through architecture, geography, social context, production design, weather, and tactile material behavior.
7. **Compile character/action direction.** Specify posture, gaze, expression, movement, and emotional temperature so the subject participates in the visual grammar rather than merely standing inside it.
8. **Enforce the five anchors.** Check the prompt line-by-line and add any missing core anchor in concrete visual form.
9. **Run the anti-drift filter.** Reject or rewrite these failure modes: fake chaotic shake; impossible action geography; glamorous hero lighting; spotless gear; cinematic smoke with no source; poses that ignore procedure.
10. **Assemble one causal prompt.** The final instruction must read like a photographable scene, not a bag of adjectives.

### Compiled output checklist
- **STYLE:** OPERATIONAL IMMERSION / CIS-34
- **SUBJECT LOCK:** exact user content preserved
- **CAMERA:** physical placement + framing + spatial behavior
- **LIGHT:** source + direction + contrast behavior
- **COLOR/MATERIALS:** object-level palette + tactile surfaces
- **ENVIRONMENT:** style-specific spatial/production-design logic
- **CHARACTER/ACTION:** posture + gaze + expression + movement
- **CORE ANCHORS:** all five represented in the prompt
- **ANTI-DRIFT:** Avoid-rule conflicts removed
- **FINAL PROMPT:** one integrated generation instruction


## Style Fidelity Gate
**Pass threshold:** average fidelity score >= **8.0/10**, Signature Fidelity >= **8.0**, Content Preservation >= **9.0**, and no other dimension below **7.5**.

### Profile-specific signature test
- Anchor 1: Camera behaves like an embedded witness rather than an omniscient action machine.
- Anchor 2: Multiple observational positions may coexist: long lens, shoulder camera, vehicle mount, wide situational view.
- Anchor 3: Action spaces remain operationally understandable.
- Anchor 4: Natural light, dust, heat, darkness, practical sources, and atmospheric conditions are accepted as part of the event.
- Anchor 5: Actors must be able to move through space without waiting for perfect marks.

The image fails signature fidelity if fewer than four anchors are clearly visible.

### Score after generation
Score **Content Preservation, Camera/Composition, Lens/Space, Lighting, Color/Materials, Environment/Texture, Character/Action, and Signature Fidelity** from 0-10 using the global Fidelity Gate.

### Correction rule
If any passing condition fails, write a repair delta only for the failed dimensions, preserve successful dimensions, and regenerate. Run no more than two automatic repair cycles. Do not respond to failure by making the image generically "more cinematic."


### Research traceability record
**Traceability confidence:** HIGH

**Evidence-use instruction:** Use these anchors to support the visual rules above. Do not infer unsupported technical specifications.

- [TECH-1] *Filmmaker Magazine* / cinematography discussions of *The Hurt Locker* and *Detroit*: raw immediacy, multi-camera/16mm approach, 360-degree action, and documentary perspective.
- [TECH-1] Barry Ackroyd interviews: scene-lit environments, actor freedom, multiple observational positions.

---

# 35. INVITATIONAL DISTANCE
**Style ID:** CIS-35  
**Research Lineage:** Abderrahmane Sissako  
**Representative works studied:** *Waiting for Happiness*, *Bamako*, *Timbuktu*

## Research synthesis
The recurring grammar is **spacious humanist observation that invites the viewer into a place without visually possessing it**. Sissako has spoken about avoiding an imposed close-up logic and using framing as an invitation. Violence may be shown at considerable distance inside a beautiful landscape rather than converted into sensational coverage. The image can be poetic, quiet, absurd, political, and visually beautiful, yet Sissako repeatedly redirects attention from scenic beauty back to human presence.

## Persistent visual invariants
- Wide or medium-wide distance respects people and place.
- Landscape is allowed to breathe without becoming postcard spectacle.
- Violence may remain distant, making the viewer witness rather than consume it.
- Natural late-afternoon, desert, courtyard, sea, or town light often carries the image.
- Minimal camera intervention encourages observation.
- Human figures are integrated into architecture/landscape rather than extracted from it.
- Humor and absurdity may occupy the same quiet frame as political threat.
- Close-ups are used selectively, so they retain force.

## AI image-construction rules
### Composition
Create spacious frames with clean visual paths: desert, beach, courtyard, street, field, simple room, low wall, goalpost, tent, or village edge. Place people as meaningful figures within the environment rather than filling the image with faces.

### Camera
Use patient eye-level or slightly distant observation. Avoid aggressive lens intrusion. Let important action happen within the frame rather than forcing the camera toward it.

### Lighting/color
Favor natural sun, dusk, shade, pale earth, sky, sand, water, white cloth, modest saturated accents, and real environmental contrast.

### Humanism rule
If the location is visually beautiful, include a human action or detail that prevents the image from becoming tourism: conversation, work, waiting, grief, play, bureaucracy, prayer, music, sport.

### Avoid
- exotic postcard framing
- telephoto voyeurism
- melodramatic violence coverage
- oversaturated desert orange
- constant close-ups

## AI Deployment Block
**INVITATIONAL DISTANCE / CIS-35:** Use spacious, patient frames that invite the viewer into a place without visually possessing it. Integrate human figures into landscape and architecture, allow natural light and environmental silence to breathe, and keep important action readable at a respectful distance when appropriate. Let humor, politics, beauty, and threat coexist without sensational coverage. If the landscape is striking, anchor it with specific human activity. Avoid tourism imagery, oversaturated desert grading, voyeuristic telephoto, and unnecessary close-up pressure.

## Style Compiler
**Compiler role:** Convert any user subject into this visual system without changing the user's required content.

### Five non-negotiable visual anchors
1. Wide or medium-wide distance respects people and place.
2. Landscape is allowed to breathe without becoming postcard spectacle.
3. Violence may remain distant, making the viewer witness rather than consume it.
4. Natural late-afternoon, desert, courtyard, sea, or town light often carries the image.
5. Minimal camera intervention encourages observation.

**Minimum visibility rule:** At least four of these five anchors must be visibly present in the generated image. All five should be encoded in the prompt unless a locked user requirement conflicts.

### Style-specific compilation sequence
1. **Lock the subject.** Preserve every user-required identity/species/object, clothing item, color, prop, action, and setting constraint.
2. **Establish the visual premise.** Use the logic of **INVITATIONAL DISTANCE / CIS-35** rather than adding generic cinematic adjectives. The deployment block above is the governing summary.
3. **Compile camera + composition.** Translate the profile's camera/composition rules into one explicit camera location, distance, framing, spatial behavior, and foreground/background relationship.
4. **Compile light.** Name the physical or psychological source, direction, hardness/softness, contrast behavior, and what it does to faces/materials.
5. **Compile color + materials.** Put the style palette into actual objects, surfaces, weather, wardrobe, architecture, practical light, landscape, skin, or props before using global grading language.
6. **Compile environment.** Make the space carry the style through architecture, geography, social context, production design, weather, and tactile material behavior.
7. **Compile character/action direction.** Specify posture, gaze, expression, movement, and emotional temperature so the subject participates in the visual grammar rather than merely standing inside it.
8. **Enforce the five anchors.** Check the prompt line-by-line and add any missing core anchor in concrete visual form.
9. **Run the anti-drift filter.** Reject or rewrite these failure modes: exotic postcard framing; telephoto voyeurism; melodramatic violence coverage; oversaturated desert orange; constant close-ups.
10. **Assemble one causal prompt.** The final instruction must read like a photographable scene, not a bag of adjectives.

### Compiled output checklist
- **STYLE:** INVITATIONAL DISTANCE / CIS-35
- **SUBJECT LOCK:** exact user content preserved
- **CAMERA:** physical placement + framing + spatial behavior
- **LIGHT:** source + direction + contrast behavior
- **COLOR/MATERIALS:** object-level palette + tactile surfaces
- **ENVIRONMENT:** style-specific spatial/production-design logic
- **CHARACTER/ACTION:** posture + gaze + expression + movement
- **CORE ANCHORS:** all five represented in the prompt
- **ANTI-DRIFT:** Avoid-rule conflicts removed
- **FINAL PROMPT:** one integrated generation instruction


## Style Fidelity Gate
**Pass threshold:** average fidelity score >= **8.0/10**, Signature Fidelity >= **8.0**, Content Preservation >= **9.0**, and no other dimension below **7.5**.

### Profile-specific signature test
- Anchor 1: Wide or medium-wide distance respects people and place.
- Anchor 2: Landscape is allowed to breathe without becoming postcard spectacle.
- Anchor 3: Violence may remain distant, making the viewer witness rather than consume it.
- Anchor 4: Natural late-afternoon, desert, courtyard, sea, or town light often carries the image.
- Anchor 5: Minimal camera intervention encourages observation.

The image fails signature fidelity if fewer than four anchors are clearly visible.

### Score after generation
Score **Content Preservation, Camera/Composition, Lens/Space, Lighting, Color/Materials, Environment/Texture, Character/Action, and Signature Fidelity** from 0-10 using the global Fidelity Gate.

### Correction rule
If any passing condition fails, write a repair delta only for the failed dimensions, preserve successful dimensions, and regenerate. Run no more than two automatic repair cycles. Do not respond to failure by making the image generically "more cinematic."


### Research traceability record
**Traceability confidence:** MEDIUM-HIGH

**Evidence-use instruction:** Use these anchors to support the visual rules above. Do not infer unsupported technical specifications.

- [TECH-1] Sissako interviews: framing as an invitation, limited dependence on close-ups, and resistance to imposing the camera on people.
- [CRIT-4] Critical discussion of *Timbuktu*: distant framing of violence and human figures held within beautiful natural space.

---

# 36. SUBURBAN DREAM BREACH
**Style ID:** CIS-36  
**Research Lineage:** Wes Craven  
**Representative works studied:** *The Last House on the Left*, *A Nightmare on Elm Street*, *The People Under the Stairs*, *Scream*

## Research synthesis
The recurring visual idea is **ordinary domestic or suburban reality whose spatial rules can suddenly become unreliable**. Research on *A Nightmare on Elm Street* emphasizes the contrast between relatively flat/drab waking naturalism and a more expressive industrial dream underworld of steam, darkness, sodium warmth, blue light, and boiler geometry — while also noting that some dream passages are intentionally photographed like waking reality so the transition cannot be trusted. *Scream* updates the grammar to clean suburban slasher space, self-aware genre framing, phones, windows, kitchens, staircases, and stalking point of view.

## Persistent visual invariants
- Normal houses and suburbs must first feel credible.
- Dream/reality boundaries may be visually obvious in some moments and invisible in others.
- Boiler rooms, basements, hallways, stairs, bedrooms, windows, bathrooms, and school corridors become threat geometry.
- Red/green or warm/cool accents can operate as recognizable tension anchors.
- Practical fog/steam belongs to industrial or dream environments, not everywhere.
- Subjective stalking POV can turn ordinary architecture into a trap.
- Impossible spatial transitions are more disturbing when camera behavior remains simple.
- Daylight normality provides critical contrast to night/dream threat.

## AI image-construction rules
### Base reality
Start with clean, ordinary suburban or institutional photography: believable home lighting, lawns, kitchens, bedrooms, schools, streets, phones, televisions, cars.

### Breach
Introduce one impossible spatial clue: corridor too long, doorway opening into wrong place, shadow behaving incorrectly, bathtub/bed threshold, stair geometry, figure in background, steam emerging where it should not.

### Lighting
Keep waking scenes relatively natural. Reserve high contrast, steam, sodium orange, deep blue, industrial backlight, or red/green punctuation for heightened zones.

### POV
Use doorway, window, closet, stair landing, phone-distance, or stalking perspective to make architecture feel watched.

### Avoid
- gothic mansion defaults
- fog in every shot
- neon slasher color without location logic
- overt monsters before spatial tension exists
- surreal distortion that announces 'dream' immediately every time

## AI Deployment Block
**SUBURBAN DREAM BREACH / CIS-36:** Establish credible ordinary suburban or domestic reality, then violate exactly one spatial rule. Use homes, bedrooms, kitchens, schools, stairs, windows, phones, hallways, basements, or industrial spaces as threat geometry. Keep waking light natural; reserve steam, high contrast, red/green tension accents, sodium warmth, or deep blue for heightened zones. Some dream images should remain photographically ordinary so reality cannot be trusted. Avoid constant fog, generic gothic settings, and surreal effects that reveal the breach too early.

## Style Compiler
**Compiler role:** Convert any user subject into this visual system without changing the user's required content.

### Five non-negotiable visual anchors
1. Normal houses and suburbs must first feel credible.
2. Dream/reality boundaries may be visually obvious in some moments and invisible in others.
3. Boiler rooms, basements, hallways, stairs, bedrooms, windows, bathrooms, and school corridors become threat geometry.
4. Red/green or warm/cool accents can operate as recognizable tension anchors.
5. Practical fog/steam belongs to industrial or dream environments, not everywhere.

**Minimum visibility rule:** At least four of these five anchors must be visibly present in the generated image. All five should be encoded in the prompt unless a locked user requirement conflicts.

### Style-specific compilation sequence
1. **Lock the subject.** Preserve every user-required identity/species/object, clothing item, color, prop, action, and setting constraint.
2. **Establish the visual premise.** Use the logic of **SUBURBAN DREAM BREACH / CIS-36** rather than adding generic cinematic adjectives. The deployment block above is the governing summary.
3. **Compile camera + composition.** Translate the profile's camera/composition rules into one explicit camera location, distance, framing, spatial behavior, and foreground/background relationship.
4. **Compile light.** Name the physical or psychological source, direction, hardness/softness, contrast behavior, and what it does to faces/materials.
5. **Compile color + materials.** Put the style palette into actual objects, surfaces, weather, wardrobe, architecture, practical light, landscape, skin, or props before using global grading language.
6. **Compile environment.** Make the space carry the style through architecture, geography, social context, production design, weather, and tactile material behavior.
7. **Compile character/action direction.** Specify posture, gaze, expression, movement, and emotional temperature so the subject participates in the visual grammar rather than merely standing inside it.
8. **Enforce the five anchors.** Check the prompt line-by-line and add any missing core anchor in concrete visual form.
9. **Run the anti-drift filter.** Reject or rewrite these failure modes: gothic mansion defaults; fog in every shot; neon slasher color without location logic; overt monsters before spatial tension exists; surreal distortion that announces 'dream' immediately every time.
10. **Assemble one causal prompt.** The final instruction must read like a photographable scene, not a bag of adjectives.

### Compiled output checklist
- **STYLE:** SUBURBAN DREAM BREACH / CIS-36
- **SUBJECT LOCK:** exact user content preserved
- **CAMERA:** physical placement + framing + spatial behavior
- **LIGHT:** source + direction + contrast behavior
- **COLOR/MATERIALS:** object-level palette + tactile surfaces
- **ENVIRONMENT:** style-specific spatial/production-design logic
- **CHARACTER/ACTION:** posture + gaze + expression + movement
- **CORE ANCHORS:** all five represented in the prompt
- **ANTI-DRIFT:** Avoid-rule conflicts removed
- **FINAL PROMPT:** one integrated generation instruction


## Style Fidelity Gate
**Pass threshold:** average fidelity score >= **8.0/10**, Signature Fidelity >= **8.0**, Content Preservation >= **9.0**, and no other dimension below **7.5**.

### Profile-specific signature test
- Anchor 1: Normal houses and suburbs must first feel credible.
- Anchor 2: Dream/reality boundaries may be visually obvious in some moments and invisible in others.
- Anchor 3: Boiler rooms, basements, hallways, stairs, bedrooms, windows, bathrooms, and school corridors become threat geometry.
- Anchor 4: Red/green or warm/cool accents can operate as recognizable tension anchors.
- Anchor 5: Practical fog/steam belongs to industrial or dream environments, not everywhere.

The image fails signature fidelity if fewer than four anchors are clearly visible.

### Score after generation
Score **Content Preservation, Camera/Composition, Lens/Space, Lighting, Color/Materials, Environment/Texture, Character/Action, and Signature Fidelity** from 0-10 using the global Fidelity Gate.

### Correction rule
If any passing condition fails, write a repair delta only for the failed dimensions, preserve successful dimensions, and regenerate. Run no more than two automatic repair cycles. Do not respond to failure by making the image generically "more cinematic."


### Research traceability record
**Traceability confidence:** MEDIUM

**Evidence-use instruction:** Use these anchors to support the visual rules above. Do not infer unsupported technical specifications.

- [CRIT-4] Critical/cinematography analysis of *A Nightmare on Elm Street*: waking-world naturalism versus industrial dream contrast, steam, sodium/blue light, and intentionally ambiguous dream transitions.
- [CRIT-4] Comparative frame analysis of *Scream*: clean suburban realism, subjective threat, windows/phones/stairs, and genre-aware composition.

---

# 37. TIDAL HAUNT REALISM
**Style ID:** CIS-37  
**Research Lineage:** Mati Diop  
**Representative works studied:** *Atlantics*, *Dahomey*

## Research synthesis
The recurring grammar is **social realism allowed to drift almost imperceptibly into haunting, with coastal light, bodies, labor, migration, history, and the horizon acting as emotional forces**. *Atlantics* uses sweltering Dakar day, sea horizon, unfinished architecture, reflective skin, wind, and nocturnal color to make absence physically present. The supernatural does not arrive as fantasy spectacle; it grows from the same bodies, streets, clubs, ocean, and economic reality already established.

## Persistent visual invariants
- Ocean, horizon, wind, and humidity carry emotional meaning.
- Social/economic reality remains legible beneath the supernatural.
- Daylight can feel hot, pale, unfinished, and materially specific.
- Night may become cool, neon, moonlit, or dreamlike without losing physical texture.
- Faces and skin remain luminous inside dark environments.
- Still or slow compositions allow absence to accumulate.
- Supernatural presence is often carried by gaze, body, reflection, sound-implied space, or repetition rather than effects.
- Architecture under construction can symbolize futures interrupted or deferred.

## AI image-construction rules
### Environment
Use coastlines, sea horizon, unfinished towers, concrete, dust, clubs, bedrooms, streets, rooftops, construction sites, fabric moving in wind, reflective water, or salt air.

### Day/night contrast
Day: hot natural sun, pale concrete, blue sea, dust, sweat, bright sky. Night: cool blue/cyan, selective neon or practical color, dark skin with controlled highlights, moon/reflection, black negative space.

### Supernatural rule
Keep the apparition inside ordinary photographic reality. Change gaze, stillness, group behavior, reflection, eye light, repeated position, or temporal feeling before adding any overt effect.

### Avoid
- fantasy glow
- generic African mysticism
- cyberpunk nightclub color
- postcard ocean imagery
- supernatural figures detached from social context

## AI Deployment Block
**TIDAL HAUNT REALISM / CIS-37:** Root the image in coastal social reality — sea horizon, heat, concrete, construction, streets, wind, labor, bodies, and economic absence — then let haunting emerge without changing the photographic rules. Use hot pale daylight and cool luminous night, preserve reflective skin and real material texture, and allow stillness, gaze, reflection, repetition, or group behavior to introduce the supernatural. Keep the ocean emotionally active but not postcard-pretty. Avoid fantasy glow, generic mysticism, cyberpunk color, and supernatural imagery disconnected from social reality.

## Style Compiler
**Compiler role:** Convert any user subject into this visual system without changing the user's required content.

### Five non-negotiable visual anchors
1. Ocean, horizon, wind, and humidity carry emotional meaning.
2. Social/economic reality remains legible beneath the supernatural.
3. Daylight can feel hot, pale, unfinished, and materially specific.
4. Night may become cool, neon, moonlit, or dreamlike without losing physical texture.
5. Faces and skin remain luminous inside dark environments.

**Minimum visibility rule:** At least four of these five anchors must be visibly present in the generated image. All five should be encoded in the prompt unless a locked user requirement conflicts.

### Style-specific compilation sequence
1. **Lock the subject.** Preserve every user-required identity/species/object, clothing item, color, prop, action, and setting constraint.
2. **Establish the visual premise.** Use the logic of **TIDAL HAUNT REALISM / CIS-37** rather than adding generic cinematic adjectives. The deployment block above is the governing summary.
3. **Compile camera + composition.** Translate the profile's camera/composition rules into one explicit camera location, distance, framing, spatial behavior, and foreground/background relationship.
4. **Compile light.** Name the physical or psychological source, direction, hardness/softness, contrast behavior, and what it does to faces/materials.
5. **Compile color + materials.** Put the style palette into actual objects, surfaces, weather, wardrobe, architecture, practical light, landscape, skin, or props before using global grading language.
6. **Compile environment.** Make the space carry the style through architecture, geography, social context, production design, weather, and tactile material behavior.
7. **Compile character/action direction.** Specify posture, gaze, expression, movement, and emotional temperature so the subject participates in the visual grammar rather than merely standing inside it.
8. **Enforce the five anchors.** Check the prompt line-by-line and add any missing core anchor in concrete visual form.
9. **Run the anti-drift filter.** Reject or rewrite these failure modes: fantasy glow; generic African mysticism; cyberpunk nightclub color; postcard ocean imagery; supernatural figures detached from social context.
10. **Assemble one causal prompt.** The final instruction must read like a photographable scene, not a bag of adjectives.

### Compiled output checklist
- **STYLE:** TIDAL HAUNT REALISM / CIS-37
- **SUBJECT LOCK:** exact user content preserved
- **CAMERA:** physical placement + framing + spatial behavior
- **LIGHT:** source + direction + contrast behavior
- **COLOR/MATERIALS:** object-level palette + tactile surfaces
- **ENVIRONMENT:** style-specific spatial/production-design logic
- **CHARACTER/ACTION:** posture + gaze + expression + movement
- **CORE ANCHORS:** all five represented in the prompt
- **ANTI-DRIFT:** Avoid-rule conflicts removed
- **FINAL PROMPT:** one integrated generation instruction


## Style Fidelity Gate
**Pass threshold:** average fidelity score >= **8.0/10**, Signature Fidelity >= **8.0**, Content Preservation >= **9.0**, and no other dimension below **7.5**.

### Profile-specific signature test
- Anchor 1: Ocean, horizon, wind, and humidity carry emotional meaning.
- Anchor 2: Social/economic reality remains legible beneath the supernatural.
- Anchor 3: Daylight can feel hot, pale, unfinished, and materially specific.
- Anchor 4: Night may become cool, neon, moonlit, or dreamlike without losing physical texture.
- Anchor 5: Faces and skin remain luminous inside dark environments.

The image fails signature fidelity if fewer than four anchors are clearly visible.

### Score after generation
Score **Content Preservation, Camera/Composition, Lens/Space, Lighting, Color/Materials, Environment/Texture, Character/Action, and Signature Fidelity** from 0-10 using the global Fidelity Gate.

### Correction rule
If any passing condition fails, write a repair delta only for the failed dimensions, preserve successful dimensions, and regenerate. Run no more than two automatic repair cycles. Do not respond to failure by making the image generically "more cinematic."


### Research traceability record
**Traceability confidence:** MEDIUM

**Evidence-use instruction:** Use these anchors to support the visual rules above. Do not infer unsupported technical specifications.

- [INST-2] BFI analysis of *Atlantics*: luminous cinematography, sweltering Dakar day, neon/supernatural night, and the lives of those left behind.
- [CRIT-4] Comparative visual study of Diop's coastal, diasporic, and historical image strategies.

---

# 38. ORNATE GAZE MECHANICS
**Style ID:** CIS-38  
**Research Lineage:** Park Chan-wook  
**Representative works studied:** *Oldboy*, *Lady Vengeance*, *The Handmaiden*, *Decision to Leave*

## Research synthesis
The recurring grammar is **precise architecture, sensual material detail, mobile camera logic, and perspective games built around who is looking at whom**. Park has described *The Handmaiden* in terms of a 'game of glances,' with camera movement and close-up strategy designed around gaze and shifting point of view. *Decision to Leave* continues the pattern through reflections, screens, surveillance, impossible-seeming transitions, and images that collapse physical distance or time. Ornate visual beauty is not passive; it is an apparatus for desire, deception, memory, and control.

## Persistent visual invariants
- Gaze is a structural element: watcher, watched, reflected, recorded, imagined.
- Architecture provides nested frames: doors, screens, windows, mirrors, railings, stairs, corridors.
- Camera movement is elegant and motivated, often revealing new spatial information.
- Macro details of objects, hands, fabric, food, wounds, tools, or writing carry sensual/narrative weight.
- Symmetry and meticulous design can be disturbed by off-axis desire or threat.
- Graphic transitions can connect locations, times, memories, or viewpoints.
- Color is rich but disciplined and tied to materials and production design.
- Violence and sensuality may share the same visual precision.

## AI image-construction rules
### Composition
Create a layered viewing apparatus. Include at least two of: mirror, glass, doorway, screen, banister, window, curtain, photograph, phone, telescope, camera, shadow, framed opening. Make it clear who can see whom.

### Movement translated to stills
Use perspective that implies an elegant reveal: foreground object partially hides a face; a reflection reveals a second figure; a corridor creates a visual path; a hand/object detail leads toward the main subject.

### Color/material
Use lacquered wood, patterned fabric, wallpaper, polished metal, wet stone, snow, foliage, ink, smoke, rain, or saturated but controlled room color. Preserve texture.

### Detail
One macro-scale narrative object should matter: cigarette, glove, shoe, rope, notebook, photograph, knife, jewelry, food, pill, phone.

### Avoid
- empty 'luxury thriller' gloss
- symmetry with no gaze relationship
- gratuitous gore
- random mirror effects
- color that does not belong to the set/materials

## AI Deployment Block
**ORNATE GAZE MECHANICS / CIS-38:** Build the frame around seeing and being seen. Use nested doors, screens, windows, mirrors, glass, railings, photographs, devices, and reflections to create a layered viewing apparatus. Let elegant spatial logic or implied camera movement reveal information. Combine disciplined symmetry with off-axis desire or threat, rich tactile materials, controlled color, and one narratively charged macro detail. Avoid empty luxury gloss, decorative mirrors, gore without perspective logic, and symmetry that does not express a relationship of gaze.

## Style Compiler
**Compiler role:** Convert any user subject into this visual system without changing the user's required content.

### Five non-negotiable visual anchors
1. Gaze is a structural element: watcher, watched, reflected, recorded, imagined.
2. Architecture provides nested frames: doors, screens, windows, mirrors, railings, stairs, corridors.
3. Camera movement is elegant and motivated, often revealing new spatial information.
4. Macro details of objects, hands, fabric, food, wounds, tools, or writing carry sensual/narrative weight.
5. Symmetry and meticulous design can be disturbed by off-axis desire or threat.

**Minimum visibility rule:** At least four of these five anchors must be visibly present in the generated image. All five should be encoded in the prompt unless a locked user requirement conflicts.

### Style-specific compilation sequence
1. **Lock the subject.** Preserve every user-required identity/species/object, clothing item, color, prop, action, and setting constraint.
2. **Establish the visual premise.** Use the logic of **ORNATE GAZE MECHANICS / CIS-38** rather than adding generic cinematic adjectives. The deployment block above is the governing summary.
3. **Compile camera + composition.** Translate the profile's camera/composition rules into one explicit camera location, distance, framing, spatial behavior, and foreground/background relationship.
4. **Compile light.** Name the physical or psychological source, direction, hardness/softness, contrast behavior, and what it does to faces/materials.
5. **Compile color + materials.** Put the style palette into actual objects, surfaces, weather, wardrobe, architecture, practical light, landscape, skin, or props before using global grading language.
6. **Compile environment.** Make the space carry the style through architecture, geography, social context, production design, weather, and tactile material behavior.
7. **Compile character/action direction.** Specify posture, gaze, expression, movement, and emotional temperature so the subject participates in the visual grammar rather than merely standing inside it.
8. **Enforce the five anchors.** Check the prompt line-by-line and add any missing core anchor in concrete visual form.
9. **Run the anti-drift filter.** Reject or rewrite these failure modes: empty 'luxury thriller' gloss; symmetry with no gaze relationship; gratuitous gore; random mirror effects; color that does not belong to the set/materials.
10. **Assemble one causal prompt.** The final instruction must read like a photographable scene, not a bag of adjectives.

### Compiled output checklist
- **STYLE:** ORNATE GAZE MECHANICS / CIS-38
- **SUBJECT LOCK:** exact user content preserved
- **CAMERA:** physical placement + framing + spatial behavior
- **LIGHT:** source + direction + contrast behavior
- **COLOR/MATERIALS:** object-level palette + tactile surfaces
- **ENVIRONMENT:** style-specific spatial/production-design logic
- **CHARACTER/ACTION:** posture + gaze + expression + movement
- **CORE ANCHORS:** all five represented in the prompt
- **ANTI-DRIFT:** Avoid-rule conflicts removed
- **FINAL PROMPT:** one integrated generation instruction


## Style Fidelity Gate
**Pass threshold:** average fidelity score >= **8.0/10**, Signature Fidelity >= **8.0**, Content Preservation >= **9.0**, and no other dimension below **7.5**.

### Profile-specific signature test
- Anchor 1: Gaze is a structural element: watcher, watched, reflected, recorded, imagined.
- Anchor 2: Architecture provides nested frames: doors, screens, windows, mirrors, railings, stairs, corridors.
- Anchor 3: Camera movement is elegant and motivated, often revealing new spatial information.
- Anchor 4: Macro details of objects, hands, fabric, food, wounds, tools, or writing carry sensual/narrative weight.
- Anchor 5: Symmetry and meticulous design can be disturbed by off-axis desire or threat.

The image fails signature fidelity if fewer than four anchors are clearly visible.

### Score after generation
Score **Content Preservation, Camera/Composition, Lens/Space, Lighting, Color/Materials, Environment/Texture, Character/Action, and Signature Fidelity** from 0-10 using the global Fidelity Gate.

### Correction rule
If any passing condition fails, write a repair delta only for the failed dimensions, preserve successful dimensions, and regenerate. Run no more than two automatic repair cycles. Do not respond to failure by making the image generically "more cinematic."


### Research traceability record
**Traceability confidence:** MEDIUM-HIGH

**Evidence-use instruction:** Use these anchors to support the visual rules above. Do not infer unsupported technical specifications.

- [CRIT-4] Park Chan-wook Q&A on *The Handmaiden*: hybrid architecture, 'game of glances,' camera movement, close-ups, and shifting perspective.
- [TECH-1] *American Cinematographer* / cinematography discussion of *Decision to Leave*: unconventional perspective, dream/reality transitions, time, and moonlight.

---

# 39. ANCESTRAL TIDE LYRISM
**Style ID:** CIS-39  
**Research Lineage:** Julie Dash  
**Representative works studied:** *Daughters of the Dust*, *Illusions*, *Praise House*

## Research synthesis
The recurring grammar is **Black feminine interiority, ancestry, place, and nonlinear time expressed through luminous tableaux, movement, textile, landscape, and rhythmic image duration**. *Daughters of the Dust* situates white garments, indigo, earth, sea, grass, dark skin, food, hair, hands, ritual objects, and family groups inside coastal light that can feel both historical and present. Research and interviews around Dash's work stress Afrocentric aesthetics, environmental attunement, movement influenced by music/dub/jazz, and speed changes that create meditative or ancestral time.

## Persistent visual invariants
- Ancestry is present in bodies, landscape, ritual, memory, and material culture rather than as ghost decoration.
- Coastal landscape and natural light create a temporal continuum.
- Black skin, white cloth, indigo, earth, green, sea, and food create rich material contrast.
- Group tableaux emphasize women, family, and generational relation.
- Slow motion or altered motion can shift ordinary action into ancestral/meditative time.
- Hair, hands, fabric, jewelry, baskets, food, water, and soil receive tactile attention.
- Narrative chronology may feel circular or layered rather than linear.
- The image is lyrical without ceasing to be culturally specific.

## AI image-construction rules
### Composition
Use wide family tableaux, women in relation to landscape, low-country/coastal horizon, porches, fields, shorelines, trees, tables, ritual or domestic gatherings. Combine wide context with tactile inserts of hands, hair, fabric, food, jewelry, or objects.

### Lighting
Use luminous natural daylight, shade under trees/porches, late sun, bright sky, reflected water, and gentle interior practicals. Protect deep skin tone and white fabric simultaneously.

### Color
Favor material color: indigo cloth, off-white cotton, skin, green vegetation, brown earth, sea blue, food, weathered wood. Avoid generic vintage sepia.

### Time in a still
Suggest slowed or layered time through wind-caught fabric, suspended gesture, repeated generations, reflections, or a figure separated from normal motion.

### Avoid
- generic spiritual glow
- costume-museum stiffness
- exoticizing Gullah/Geechee culture
- monochrome nostalgia
- treating ancestry as supernatural VFX

## AI Deployment Block
**ANCESTRAL TIDE LYRISM / CIS-39:** Create luminous, culturally specific images in which ancestry lives through family, landscape, material culture, and layered time. Use coastal or low-country natural light, rich dark skin, white and indigo cloth, earth, sea, vegetation, tactile hands/hair/food/fabric, and communal tableaux. Allow slowed implied motion or suspended gesture to create meditative ancestral time. Keep the image grounded in bodies and place rather than fantasy effects. Avoid sepia nostalgia, generic spiritual glow, museum stiffness, and exoticization.

## Style Compiler
**Compiler role:** Convert any user subject into this visual system without changing the user's required content.

### Five non-negotiable visual anchors
1. Ancestry is present in bodies, landscape, ritual, memory, and material culture rather than as ghost decoration.
2. Coastal landscape and natural light create a temporal continuum.
3. Black skin, white cloth, indigo, earth, green, sea, and food create rich material contrast.
4. Group tableaux emphasize women, family, and generational relation.
5. Slow motion or altered motion can shift ordinary action into ancestral/meditative time.

**Minimum visibility rule:** At least four of these five anchors must be visibly present in the generated image. All five should be encoded in the prompt unless a locked user requirement conflicts.

### Style-specific compilation sequence
1. **Lock the subject.** Preserve every user-required identity/species/object, clothing item, color, prop, action, and setting constraint.
2. **Establish the visual premise.** Use the logic of **ANCESTRAL TIDE LYRISM / CIS-39** rather than adding generic cinematic adjectives. The deployment block above is the governing summary.
3. **Compile camera + composition.** Translate the profile's camera/composition rules into one explicit camera location, distance, framing, spatial behavior, and foreground/background relationship.
4. **Compile light.** Name the physical or psychological source, direction, hardness/softness, contrast behavior, and what it does to faces/materials.
5. **Compile color + materials.** Put the style palette into actual objects, surfaces, weather, wardrobe, architecture, practical light, landscape, skin, or props before using global grading language.
6. **Compile environment.** Make the space carry the style through architecture, geography, social context, production design, weather, and tactile material behavior.
7. **Compile character/action direction.** Specify posture, gaze, expression, movement, and emotional temperature so the subject participates in the visual grammar rather than merely standing inside it.
8. **Enforce the five anchors.** Check the prompt line-by-line and add any missing core anchor in concrete visual form.
9. **Run the anti-drift filter.** Reject or rewrite these failure modes: generic spiritual glow; costume-museum stiffness; exoticizing Gullah/Geechee culture; monochrome nostalgia; treating ancestry as supernatural VFX.
10. **Assemble one causal prompt.** The final instruction must read like a photographable scene, not a bag of adjectives.

### Compiled output checklist
- **STYLE:** ANCESTRAL TIDE LYRISM / CIS-39
- **SUBJECT LOCK:** exact user content preserved
- **CAMERA:** physical placement + framing + spatial behavior
- **LIGHT:** source + direction + contrast behavior
- **COLOR/MATERIALS:** object-level palette + tactile surfaces
- **ENVIRONMENT:** style-specific spatial/production-design logic
- **CHARACTER/ACTION:** posture + gaze + expression + movement
- **CORE ANCHORS:** all five represented in the prompt
- **ANTI-DRIFT:** Avoid-rule conflicts removed
- **FINAL PROMPT:** one integrated generation instruction


## Style Fidelity Gate
**Pass threshold:** average fidelity score >= **8.0/10**, Signature Fidelity >= **8.0**, Content Preservation >= **9.0**, and no other dimension below **7.5**.

### Profile-specific signature test
- Anchor 1: Ancestry is present in bodies, landscape, ritual, memory, and material culture rather than as ghost decoration.
- Anchor 2: Coastal landscape and natural light create a temporal continuum.
- Anchor 3: Black skin, white cloth, indigo, earth, green, sea, and food create rich material contrast.
- Anchor 4: Group tableaux emphasize women, family, and generational relation.
- Anchor 5: Slow motion or altered motion can shift ordinary action into ancestral/meditative time.

The image fails signature fidelity if fewer than four anchors are clearly visible.

### Score after generation
Score **Content Preservation, Camera/Composition, Lens/Space, Lighting, Color/Materials, Environment/Texture, Character/Action, and Signature Fidelity** from 0-10 using the global Fidelity Gate.

### Correction rule
If any passing condition fails, write a repair delta only for the failed dimensions, preserve successful dimensions, and regenerate. Run no more than two automatic repair cycles. Do not respond to failure by making the image generically "more cinematic."


### Research traceability record
**Traceability confidence:** MEDIUM

**Evidence-use instruction:** Use these anchors to support the visual rules above. Do not infer unsupported technical specifications.

- [INST-2] BFI scholarship on Dash: Afrocentric aesthetics, Black womanhood, shared narrative, ancestry, vibrant color and movement.
- [CRIT-4] Arthur Jafa / critical discussions of speed, temporal 'declensions,' environmental tuning, and meditative image rhythm in *Daughters of the Dust*.

---

# 40. STORYBOOK EXPRESSIONIST GOTHIC
**Style ID:** CIS-40  
**Research Lineage:** Tim Burton  
**Representative works studied:** *Edward Scissorhands*, *Batman Returns*, *Sleepy Hollow*, *Sweeney Todd*, *Big Fish*

## Research synthesis
The recurring grammar is **theatrical expressionist world-building in which architecture, silhouette, season, and production design externalize outsider emotion**. Research on *Sleepy Hollow* describes a deliberately synthetic pictorial reality influenced by classic studio filmmaking: controlled fog, wind, color, contrast, season, and stylized built environments. *Batman Returns* similarly demonstrates how heavily production design determines the image before lighting. The world is not trying to look casually real; it behaves like a dark illustrated storybook whose shapes reveal psychological identity.

## Persistent visual invariants
- Architecture can bend, lean, spike, curl, loom, or huddle like a character.
- Silhouette is highly important: pale face/dark costume, bare tree/fog, black roof/snow, tall narrow figure/rounded environment.
- Palettes are limited and seasonal, often black/white/gray/brown with selective candy, red, blue, or green accents.
- Backlit fog, snow, rain, smoke, moonlight, or diffuse sky create graphic depth.
- Sets feel handmade/theatrical rather than invisible naturalism.
- Outsiders are centered sympathetically within environments that exaggerate difference.
- Curves, spirals, stripes, sharp peaks, crooked verticals, and exaggerated scale recur.
- Miniature/storybook logic can coexist with tactile physical materials.

## AI image-construction rules
### Shape language
Choose 2-3 dominant shape motifs: crooked verticals, needle peaks, spirals, scallops, oversized circles, narrow windows, striped forms. Repeat across architecture, furniture, trees, costume, and props.

### Composition
Use strong silhouette and frontal storybook readability. Place the outsider against a world whose architecture visually comments on them. Let the environment look intentionally designed.

### Lighting
Use diffuse overcast, moonlike backlight, practical pools, snow bounce, fireplace, or theatrical shafts through fog. Keep faces readable against dark costume/environment.

### Color
Restrict heavily. Use desaturated or near-monochrome world color with one small family of heightened accents when useful.

### Avoid
- generic Halloween decoration
- purple/green everything
- random crooked shapes with no repeated motif
- glossy CGI gothic
- photoreal naturalism that neutralizes the theatrical world

## AI Deployment Block
**STORYBOOK EXPRESSIONIST GOTHIC / CIS-40:** Build an intentionally theatrical dark storybook world from repeated shape language, distorted architecture, strong silhouette, handmade materials, controlled fog/weather, and a narrow seasonal palette. Let buildings, trees, furniture, costume, and props echo 2-3 shapes such as spikes, curls, stripes, narrow verticals, or oversized circles. Center the outsider sympathetically within an environment that exaggerates difference. Avoid generic Halloween color, arbitrary crookedness, glossy CGI, and naturalism that flattens the expressionist design.

## Style Compiler
**Compiler role:** Convert any user subject into this visual system without changing the user's required content.

### Five non-negotiable visual anchors
1. Architecture can bend, lean, spike, curl, loom, or huddle like a character.
2. Silhouette is highly important: pale face/dark costume, bare tree/fog, black roof/snow, tall narrow figure/rounded environment.
3. Palettes are limited and seasonal, often black/white/gray/brown with selective candy, red, blue, or green accents.
4. Backlit fog, snow, rain, smoke, moonlight, or diffuse sky create graphic depth.
5. Sets feel handmade/theatrical rather than invisible naturalism.

**Minimum visibility rule:** At least four of these five anchors must be visibly present in the generated image. All five should be encoded in the prompt unless a locked user requirement conflicts.

### Style-specific compilation sequence
1. **Lock the subject.** Preserve every user-required identity/species/object, clothing item, color, prop, action, and setting constraint.
2. **Establish the visual premise.** Use the logic of **STORYBOOK EXPRESSIONIST GOTHIC / CIS-40** rather than adding generic cinematic adjectives. The deployment block above is the governing summary.
3. **Compile camera + composition.** Translate the profile's camera/composition rules into one explicit camera location, distance, framing, spatial behavior, and foreground/background relationship.
4. **Compile light.** Name the physical or psychological source, direction, hardness/softness, contrast behavior, and what it does to faces/materials.
5. **Compile color + materials.** Put the style palette into actual objects, surfaces, weather, wardrobe, architecture, practical light, landscape, skin, or props before using global grading language.
6. **Compile environment.** Make the space carry the style through architecture, geography, social context, production design, weather, and tactile material behavior.
7. **Compile character/action direction.** Specify posture, gaze, expression, movement, and emotional temperature so the subject participates in the visual grammar rather than merely standing inside it.
8. **Enforce the five anchors.** Check the prompt line-by-line and add any missing core anchor in concrete visual form.
9. **Run the anti-drift filter.** Reject or rewrite these failure modes: generic Halloween decoration; purple/green everything; random crooked shapes with no repeated motif; glossy CGI gothic; photoreal naturalism that neutralizes the theatrical world.
10. **Assemble one causal prompt.** The final instruction must read like a photographable scene, not a bag of adjectives.

### Compiled output checklist
- **STYLE:** STORYBOOK EXPRESSIONIST GOTHIC / CIS-40
- **SUBJECT LOCK:** exact user content preserved
- **CAMERA:** physical placement + framing + spatial behavior
- **LIGHT:** source + direction + contrast behavior
- **COLOR/MATERIALS:** object-level palette + tactile surfaces
- **ENVIRONMENT:** style-specific spatial/production-design logic
- **CHARACTER/ACTION:** posture + gaze + expression + movement
- **CORE ANCHORS:** all five represented in the prompt
- **ANTI-DRIFT:** Avoid-rule conflicts removed
- **FINAL PROMPT:** one integrated generation instruction


## Style Fidelity Gate
**Pass threshold:** average fidelity score >= **8.0/10**, Signature Fidelity >= **8.0**, Content Preservation >= **9.0**, and no other dimension below **7.5**.

### Profile-specific signature test
- Anchor 1: Architecture can bend, lean, spike, curl, loom, or huddle like a character.
- Anchor 2: Silhouette is highly important: pale face/dark costume, bare tree/fog, black roof/snow, tall narrow figure/rounded environment.
- Anchor 3: Palettes are limited and seasonal, often black/white/gray/brown with selective candy, red, blue, or green accents.
- Anchor 4: Backlit fog, snow, rain, smoke, moonlight, or diffuse sky create graphic depth.
- Anchor 5: Sets feel handmade/theatrical rather than invisible naturalism.

The image fails signature fidelity if fewer than four anchors are clearly visible.

### Score after generation
Score **Content Preservation, Camera/Composition, Lens/Space, Lighting, Color/Materials, Environment/Texture, Character/Action, and Signature Fidelity** from 0-10 using the global Fidelity Gate.

### Correction rule
If any passing condition fails, write a repair delta only for the failed dimensions, preserve successful dimensions, and regenerate. Run no more than two automatic repair cycles. Do not respond to failure by making the image generically "more cinematic."


### Research traceability record
**Traceability confidence:** HIGH

**Evidence-use instruction:** Use these anchors to support the visual rules above. Do not infer unsupported technical specifications.

- [TECH-1] *American Cinematographer* — *Sleepy Hollow*: synthetic pictorial classic-studio reality, controlled fog/wind/season/color, and stylized sets.
- [TECH-1] *American Cinematographer* — *Batman Returns*: production-design-driven visual world and expressionist environmental control.

---

# 41. SAHEL SURREAL MONTAGE
**Style ID:** CIS-41  
**Research Lineage:** Djibril Diop Mambety  
**Representative works studied:** *Touki Bouki*, *Hyenas*, *The Little Girl Who Sold the Sun*

## Research synthesis
The recurring grammar is **street-level African reality fractured by associative montage, surreal symbolism, abrupt tonal shifts, and restless sound-image rhythm**. Critical writing on *Touki Bouki* emphasizes its ability to be naturalistic and hallucinatory in the same breath: Dakar streets, animals, roads, motorcycles, bodies, and daily commerce are cut against symbolic or fantasy imagery through jagged editing and vivid sound. The visual power comes from collision rather than from a smooth prestige look.

## Persistent visual invariants
- Real streets, markets, coast, roads, animals, vehicles, and bodies remain materially present.
- Symbolic imagery may interrupt realism without explanation.
- Montage can be jagged, associative, manic, or suddenly meditative.
- Strong color and sun can coexist with rough documentary texture.
- Repetition of vehicles, horns, animals, money, clothing, or urban signs can become rhythmic motifs.
- Wide environmental frames make Dakar and other places active characters.
- Tone may swing from comic to cruel to lyrical without smoothing the transitions.
- Sound-implied rhythm should be visible in the composition even in a still.

## AI image-construction rules
### Base reality
Photograph a real social environment first: street, market, road, slaughterhouse edge, beach, bus, motorcycle, crowd, courtyard, shop, or dusty open space. Preserve hard sun, ordinary clothing, surface wear, and uncontrolled life at the edges.

### Surreal collision
Introduce one symbolic intrusion that belongs to the character's desire or social reality: animal horns, luxury object, repeated vehicle, impossible juxtaposition, doubled figure, isolated color field, or dreamlike object placement. Keep it concrete rather than vaporous.

### Composition
Use bold diagonals, road perspective, bodies against open sky, motorcycle/vehicle shapes, environmental layers, or sudden frontal symbolism. Allow asymmetry and rough edges.

### Color/texture
Retain sun-struck color, grain, dust, skin, painted metal, fabric, sea, asphalt, and urban signage. Avoid smoothing everything into contemporary digital cleanliness.

### Avoid
- generic 'African surrealism'
- dream fog
- polished fashion-editorial appropriation
- effects with no social or symbolic connection
- seamless montage logic that removes the productive collision

## AI Deployment Block
**SAHEL SURREAL MONTAGE / CIS-41:** Begin with materially real street, road, market, coast, vehicle, animal, body, and sun, then fracture that reality with one concrete symbolic collision. Use jagged associative visual logic, bold environmental framing, vivid but real color, rough texture, repeated motifs, and abrupt shifts between comic, lyrical, and threatening energy. Let the surreal element emerge from desire, money, migration, status, history, or everyday life rather than from fantasy fog. Avoid polished fashion surrealism, generic mysticism, and effects with no social connection.

## Style Compiler
**Compiler role:** Convert any user subject into this visual system without changing the user's required content.

### Five non-negotiable visual anchors
1. Real streets, markets, coast, roads, animals, vehicles, and bodies remain materially present.
2. Symbolic imagery may interrupt realism without explanation.
3. Montage can be jagged, associative, manic, or suddenly meditative.
4. Strong color and sun can coexist with rough documentary texture.
5. Repetition of vehicles, horns, animals, money, clothing, or urban signs can become rhythmic motifs.

**Minimum visibility rule:** At least four of these five anchors must be visibly present in the generated image. All five should be encoded in the prompt unless a locked user requirement conflicts.

### Style-specific compilation sequence
1. **Lock the subject.** Preserve every user-required identity/species/object, clothing item, color, prop, action, and setting constraint.
2. **Establish the visual premise.** Use the logic of **SAHEL SURREAL MONTAGE / CIS-41** rather than adding generic cinematic adjectives. The deployment block above is the governing summary.
3. **Compile camera + composition.** Translate the profile's camera/composition rules into one explicit camera location, distance, framing, spatial behavior, and foreground/background relationship.
4. **Compile light.** Name the physical or psychological source, direction, hardness/softness, contrast behavior, and what it does to faces/materials.
5. **Compile color + materials.** Put the style palette into actual objects, surfaces, weather, wardrobe, architecture, practical light, landscape, skin, or props before using global grading language.
6. **Compile environment.** Make the space carry the style through architecture, geography, social context, production design, weather, and tactile material behavior.
7. **Compile character/action direction.** Specify posture, gaze, expression, movement, and emotional temperature so the subject participates in the visual grammar rather than merely standing inside it.
8. **Enforce the five anchors.** Check the prompt line-by-line and add any missing core anchor in concrete visual form.
9. **Run the anti-drift filter.** Reject or rewrite these failure modes: generic 'African surrealism'; dream fog; polished fashion-editorial appropriation; effects with no social or symbolic connection; seamless montage logic that removes the productive collision.
10. **Assemble one causal prompt.** The final instruction must read like a photographable scene, not a bag of adjectives.

### Compiled output checklist
- **STYLE:** SAHEL SURREAL MONTAGE / CIS-41
- **SUBJECT LOCK:** exact user content preserved
- **CAMERA:** physical placement + framing + spatial behavior
- **LIGHT:** source + direction + contrast behavior
- **COLOR/MATERIALS:** object-level palette + tactile surfaces
- **ENVIRONMENT:** style-specific spatial/production-design logic
- **CHARACTER/ACTION:** posture + gaze + expression + movement
- **CORE ANCHORS:** all five represented in the prompt
- **ANTI-DRIFT:** Avoid-rule conflicts removed
- **FINAL PROMPT:** one integrated generation instruction


## Style Fidelity Gate
**Pass threshold:** average fidelity score >= **8.0/10**, Signature Fidelity >= **8.0**, Content Preservation >= **9.0**, and no other dimension below **7.5**.

### Profile-specific signature test
- Anchor 1: Real streets, markets, coast, roads, animals, vehicles, and bodies remain materially present.
- Anchor 2: Symbolic imagery may interrupt realism without explanation.
- Anchor 3: Montage can be jagged, associative, manic, or suddenly meditative.
- Anchor 4: Strong color and sun can coexist with rough documentary texture.
- Anchor 5: Repetition of vehicles, horns, animals, money, clothing, or urban signs can become rhythmic motifs.

The image fails signature fidelity if fewer than four anchors are clearly visible.

### Score after generation
Score **Content Preservation, Camera/Composition, Lens/Space, Lighting, Color/Materials, Environment/Texture, Character/Action, and Signature Fidelity** from 0-10 using the global Fidelity Gate.

### Correction rule
If any passing condition fails, write a repair delta only for the failed dimensions, preserve successful dimensions, and regenerate. Run no more than two automatic repair cycles. Do not respond to failure by making the image generically "more cinematic."


### Research traceability record
**Traceability confidence:** MEDIUM

**Evidence-use instruction:** Use these anchors to support the visual rules above. Do not infer unsupported technical specifications.

- [INST-2] Criterion criticism on *Touki Bouki*: surreal-naturalistic fusion, fractured portraiture, vivid imagery, unconventional editing, jagged soundscape, and alternation between manic and meditative rhythm.
- [CRIT-4] Comparative visual study of *Touki Bouki* and *Hyenas*.

---

# 42. ELASTIC REAL-TIME IMMERSION
**Style ID:** CIS-42  
**Research Lineage:** Alfonso Cuaron  
**Representative works studied:** *Y Tu Mama Tambien*, *Children of Men*, *Gravity*, *Roma*

## Research synthesis
The recurring grammar is **long-duration spatial immersion in which the camera can move from wide geography to intimate human detail without surrendering the continuity of the event**. Research around *Children of Men* describes handheld/documentary realism, minimal traditional lighting, and scenes designed to unfold rather than be assembled from conventional coverage. Long takes are elastic: the camera can be a witness, participant, passenger, or observer as action develops in foreground and background simultaneously. *Roma* refines the same ethic into slower lateral observation and deep environmental choreography.

## Persistent visual invariants
- Events unfold in continuous space rather than being reduced to coverage fragments.
- Foreground, middle ground, and background may all contain meaningful action.
- Camera distance can change inside one conceptual shot.
- Natural/available or environment-driven light supports realism.
- Long-lens voyeurism is less important than embodied spatial presence.
- Handheld movement remains legible rather than chaotic.
- Background events can surprise the viewer because the world exists beyond the protagonist.
- Weather, crowds, vehicles, architecture, and extras are choreographed as living systems.

## AI image-construction rules
### Composition
Build a frame with at least three spatial planes. Place the subject in relation to an active environment: street protest, beach, family room, car, hospital, refugee camp, city block, courtyard, forest, or apartment. Include meaningful secondary action that would continue even if the protagonist left.

### Camera
Use eye-level or shoulder-height immersion, lateral tracking feeling, vehicle/passenger perspective, or a wide composition capable of becoming intimate through proximity. Keep the viewer physically inside the scene.

### Lighting
Use the environment: overcast sky, windows, practical lamps, car light, fire, street sources, sun through haze. Avoid obviously separate key/fill/rim construction.

### Depth
Keep substantial environmental detail readable. Deep or moderate focus is preferred when spatial choreography matters.

### Avoid
- conventional hero close-up disconnected from the event
- chaotic shake
- montage-like visual clutter in one still
- shallow-focus erasure of background action
- artificial beauty light

## AI Deployment Block
**ELASTIC REAL-TIME IMMERSION / CIS-42:** Construct the image as a slice of continuous lived space. Use three readable depth planes, environment-driven light, eye/shoulder-level camera presence, and meaningful foreground/background action that feels capable of continuing beyond the frame. Let the viewer occupy the street, room, car, crowd, beach, or crisis rather than observe from a detached telephoto position. Preserve spatial choreography and environmental detail. Avoid chaotic shake, isolated hero portraiture, excessive bokeh, and visibly artificial beauty lighting.

## Style Compiler
**Compiler role:** Convert any user subject into this visual system without changing the user's required content.

### Five non-negotiable visual anchors
1. Events unfold in continuous space rather than being reduced to coverage fragments.
2. Foreground, middle ground, and background may all contain meaningful action.
3. Camera distance can change inside one conceptual shot.
4. Natural/available or environment-driven light supports realism.
5. Long-lens voyeurism is less important than embodied spatial presence.

**Minimum visibility rule:** At least four of these five anchors must be visibly present in the generated image. All five should be encoded in the prompt unless a locked user requirement conflicts.

### Style-specific compilation sequence
1. **Lock the subject.** Preserve every user-required identity/species/object, clothing item, color, prop, action, and setting constraint.
2. **Establish the visual premise.** Use the logic of **ELASTIC REAL-TIME IMMERSION / CIS-42** rather than adding generic cinematic adjectives. The deployment block above is the governing summary.
3. **Compile camera + composition.** Translate the profile's camera/composition rules into one explicit camera location, distance, framing, spatial behavior, and foreground/background relationship.
4. **Compile light.** Name the physical or psychological source, direction, hardness/softness, contrast behavior, and what it does to faces/materials.
5. **Compile color + materials.** Put the style palette into actual objects, surfaces, weather, wardrobe, architecture, practical light, landscape, skin, or props before using global grading language.
6. **Compile environment.** Make the space carry the style through architecture, geography, social context, production design, weather, and tactile material behavior.
7. **Compile character/action direction.** Specify posture, gaze, expression, movement, and emotional temperature so the subject participates in the visual grammar rather than merely standing inside it.
8. **Enforce the five anchors.** Check the prompt line-by-line and add any missing core anchor in concrete visual form.
9. **Run the anti-drift filter.** Reject or rewrite these failure modes: conventional hero close-up disconnected from the event; chaotic shake; montage-like visual clutter in one still; shallow-focus erasure of background action; artificial beauty light.
10. **Assemble one causal prompt.** The final instruction must read like a photographable scene, not a bag of adjectives.

### Compiled output checklist
- **STYLE:** ELASTIC REAL-TIME IMMERSION / CIS-42
- **SUBJECT LOCK:** exact user content preserved
- **CAMERA:** physical placement + framing + spatial behavior
- **LIGHT:** source + direction + contrast behavior
- **COLOR/MATERIALS:** object-level palette + tactile surfaces
- **ENVIRONMENT:** style-specific spatial/production-design logic
- **CHARACTER/ACTION:** posture + gaze + expression + movement
- **CORE ANCHORS:** all five represented in the prompt
- **ANTI-DRIFT:** Avoid-rule conflicts removed
- **FINAL PROMPT:** one integrated generation instruction


## Style Fidelity Gate
**Pass threshold:** average fidelity score >= **8.0/10**, Signature Fidelity >= **8.0**, Content Preservation >= **9.0**, and no other dimension below **7.5**.

### Profile-specific signature test
- Anchor 1: Events unfold in continuous space rather than being reduced to coverage fragments.
- Anchor 2: Foreground, middle ground, and background may all contain meaningful action.
- Anchor 3: Camera distance can change inside one conceptual shot.
- Anchor 4: Natural/available or environment-driven light supports realism.
- Anchor 5: Long-lens voyeurism is less important than embodied spatial presence.

The image fails signature fidelity if fewer than four anchors are clearly visible.

### Score after generation
Score **Content Preservation, Camera/Composition, Lens/Space, Lighting, Color/Materials, Environment/Texture, Character/Action, and Signature Fidelity** from 0-10 using the global Fidelity Gate.

### Correction rule
If any passing condition fails, write a repair delta only for the failed dimensions, preserve successful dimensions, and regenerate. Run no more than two automatic repair cycles. Do not respond to failure by making the image generically "more cinematic."


### Research traceability record
**Traceability confidence:** MEDIUM-HIGH

**Evidence-use instruction:** Use these anchors to support the visual rules above. Do not infer unsupported technical specifications.

- [TECH-1] *American Cinematographer* — *Children of Men*: handheld/documentary realism, limited traditional lighting, unconventional coverage, and self-contained unfolding shots.
- [CRIT-4] Cinematography analysis of Cuaron's long takes as elastic movement from wide spatial information to intimate proximity.

---

# 43. DIGNIFIED HUMAN FOCUS
**Style ID:** CIS-43  
**Research Lineage:** Chinonye Chukwu  
**Representative works studied:** *Clemency*, *Till*

## Research synthesis
Across two very different films, the durable principle is **human dignity organized through deliberate portraiture, restraint, and visual environments that clarify whether a person is being constrained or allowed to live fully**. *Clemency* uses institutional stillness, controlled framing, muted spaces, and emotional containment. Research around *Till* describes a consciously bright, bold palette intended to represent the vitality and richness of Black communities rather than allowing historical violence to define the entire visual world. Together they suggest a system in which color and camera restraint are ethical choices about how the subject is seen.

## Persistent visual invariants
- The human subject is never merely an illustration of an issue.
- Institutional spaces can be still, repetitive, compressed, and emotionally draining.
- Community and private life can be richer in color, texture, and movement.
- Close-ups are purposeful and emotionally patient.
- Historical Black life should contain beauty, fashion, home, commerce, family, and ordinary pleasure, not only suffering.
- Visual restraint can intensify moral tension.
- Color contrast between social worlds can reveal what systems remove from people.

## AI image-construction rules
### Composition
For institutional pressure, use controlled lines, doors, glass, desks, hallways, partitions, uniform spacing, centered or slightly boxed-in figures. For community/private life, open the frame, include relationships, patterned clothing, shop/home detail, street life, and brighter spatial depth.

### Lighting/color
Institutional zone: restrained neutral/cool practical light, low saturation, controlled contrast. Human/community zone: richer wardrobe and environmental color, warmer skin, daylight, household practicals, vibrant but historically or geographically credible color.

### Portraiture
Hold the face long enough to communicate thought. Avoid melodramatic expressions. Let eyes, jaw, posture, hands, and stillness carry moral weight.

### Avoid
- trauma-only visual identity
- gray desaturation for every historical scene
- sentimental glow around victims
- issue-poster symbolism
- reducing community scenes to background color without individual people

## AI Deployment Block
**DIGNIFIED HUMAN FOCUS / CIS-43:** Center human dignity before issue or spectacle. Use patient, controlled portraiture and let institutional spaces become visually repetitive, restrained, boxed, and draining. When the image moves into family, community, commerce, memory, or ordinary life, permit fuller color, texture, relationships, and spatial openness. Render historical Black life with vitality as well as gravity. Avoid trauma-only imagery, universal gray grading, sentimental victim lighting, and symbolic issue-poster composition.

## Style Compiler
**Compiler role:** Convert any user subject into this visual system without changing the user's required content.

### Five non-negotiable visual anchors
1. The human subject is never merely an illustration of an issue.
2. Institutional spaces can be still, repetitive, compressed, and emotionally draining.
3. Community and private life can be richer in color, texture, and movement.
4. Close-ups are purposeful and emotionally patient.
5. Historical Black life should contain beauty, fashion, home, commerce, family, and ordinary pleasure, not only suffering.

**Minimum visibility rule:** At least four of these five anchors must be visibly present in the generated image. All five should be encoded in the prompt unless a locked user requirement conflicts.

### Style-specific compilation sequence
1. **Lock the subject.** Preserve every user-required identity/species/object, clothing item, color, prop, action, and setting constraint.
2. **Establish the visual premise.** Use the logic of **DIGNIFIED HUMAN FOCUS / CIS-43** rather than adding generic cinematic adjectives. The deployment block above is the governing summary.
3. **Compile camera + composition.** Translate the profile's camera/composition rules into one explicit camera location, distance, framing, spatial behavior, and foreground/background relationship.
4. **Compile light.** Name the physical or psychological source, direction, hardness/softness, contrast behavior, and what it does to faces/materials.
5. **Compile color + materials.** Put the style palette into actual objects, surfaces, weather, wardrobe, architecture, practical light, landscape, skin, or props before using global grading language.
6. **Compile environment.** Make the space carry the style through architecture, geography, social context, production design, weather, and tactile material behavior.
7. **Compile character/action direction.** Specify posture, gaze, expression, movement, and emotional temperature so the subject participates in the visual grammar rather than merely standing inside it.
8. **Enforce the five anchors.** Check the prompt line-by-line and add any missing core anchor in concrete visual form.
9. **Run the anti-drift filter.** Reject or rewrite these failure modes: trauma-only visual identity; gray desaturation for every historical scene; sentimental glow around victims; issue-poster symbolism; reducing community scenes to background color without individual people.
10. **Assemble one causal prompt.** The final instruction must read like a photographable scene, not a bag of adjectives.

### Compiled output checklist
- **STYLE:** DIGNIFIED HUMAN FOCUS / CIS-43
- **SUBJECT LOCK:** exact user content preserved
- **CAMERA:** physical placement + framing + spatial behavior
- **LIGHT:** source + direction + contrast behavior
- **COLOR/MATERIALS:** object-level palette + tactile surfaces
- **ENVIRONMENT:** style-specific spatial/production-design logic
- **CHARACTER/ACTION:** posture + gaze + expression + movement
- **CORE ANCHORS:** all five represented in the prompt
- **ANTI-DRIFT:** Avoid-rule conflicts removed
- **FINAL PROMPT:** one integrated generation instruction


## Style Fidelity Gate
**Pass threshold:** average fidelity score >= **8.0/10**, Signature Fidelity >= **8.0**, Content Preservation >= **9.0**, and no other dimension below **7.5**.

### Profile-specific signature test
- Anchor 1: The human subject is never merely an illustration of an issue.
- Anchor 2: Institutional spaces can be still, repetitive, compressed, and emotionally draining.
- Anchor 3: Community and private life can be richer in color, texture, and movement.
- Anchor 4: Close-ups are purposeful and emotionally patient.
- Anchor 5: Historical Black life should contain beauty, fashion, home, commerce, family, and ordinary pleasure, not only suffering.

The image fails signature fidelity if fewer than four anchors are clearly visible.

### Score after generation
Score **Content Preservation, Camera/Composition, Lens/Space, Lighting, Color/Materials, Environment/Texture, Character/Action, and Signature Fidelity** from 0-10 using the global Fidelity Gate.

### Correction rule
If any passing condition fails, write a repair delta only for the failed dimensions, preserve successful dimensions, and regenerate. Run no more than two automatic repair cycles. Do not respond to failure by making the image generically "more cinematic."


### Research traceability record
**Traceability confidence:** MEDIUM-HIGH

**Evidence-use instruction:** Use these anchors to support the visual rules above. Do not infer unsupported technical specifications.

- [TECH-1] *Filmmaker Magazine* / production coverage of *Till*: bright, bold color used to restore the vitality and richness of Black community life and avoid museum-like history.
- [CRIT-4] Comparative visual study of the restrained institutional language of *Clemency* and the fuller living world of *Till*.

---

# 44. ATMOSPHERIC WORLDFORGE
**Style ID:** CIS-44  
**Research Lineage:** Ridley Scott  
**Representative works studied:** *Alien*, *Blade Runner*, *Gladiator*, *Black Hawk Down*, *Kingdom of Heaven*, *The Martian*

## Research synthesis
The recurring grammar is **dense production design forged together with directional atmospheric light so the world feels physically present before plot begins**. *Alien* uses low-key practical fluorescent/tungsten logic, industrial corridors, condensation, grime, and handheld panic inside a heavily designed environment. *Blade Runner* develops noir shafts, backlight, rain, smoke, neon, and layered foreground architecture. *Gladiator* and later historical/action work transfer the same world-building instinct to dust, low angles, fire, crowds, multi-camera physicality, and location-specific palette. The signature is not 'dark sci-fi'; it is the integration of design, atmosphere, and directional light.

## Persistent visual invariants
- Production design carries enormous visual responsibility.
- Atmosphere makes light visible: smoke, rain, dust, steam, mist, sand, snow, condensation.
- Strong backlight or directional shafts carve depth through complex environments.
- Foreground layers create visual density.
- Low camera positions often give structures, machines, crowds, or warriors physical weight.
- Widescreen staging preserves environment and scale.
- Different worlds may have sharply different color/texture identities.
- Action can become handheld/multi-camera without abandoning the tactile world.

## AI image-construction rules
### World first
Define materials before color grading: wet metal, concrete, carved stone, sand, leather, scratched plastic, fabric, glass, pipes, wood, machinery, armor, vegetation. Build at least three material families into the environment.

### Atmosphere
Use only atmosphere justified by location: rain in street/industrial city, dust in desert/battlefield, steam around machinery, smoke near fire, condensation in sealed interior. Let atmosphere reveal light direction.

### Lighting
Favor directional backlight, side light, practical pools, shafts through dust/smoke, hard sun, fire, or fluorescent/tungsten industrial sources. Preserve silhouette.

### Composition
Layer foreground objects, subject, and large environment. Use widescreen depth, low angles, doorways, machinery, columns, crowds, or structures that make the world feel built.

### Avoid
- atmosphere with no source
- generic blue sci-fi
- empty clean sets
- digital plastic surfaces
- light that does not interact with weather/material
- production design reduced to background wallpaper

## AI Deployment Block
**ATMOSPHERIC WORLDFORGE / CIS-44:** Build the physical world before styling the image. Combine tactile materials, dense production design, strong foreground layers, widescreen depth, and directional light made visible by justified atmosphere such as rain, dust, steam, smoke, mist, or condensation. Use low angles and silhouettes when mass matters. Give each environment its own material and color identity. Avoid empty clean sets, generic blue sci-fi, plastic surfaces, unmotivated fog, and lighting that does not interact with the world.

## Style Compiler
**Compiler role:** Convert any user subject into this visual system without changing the user's required content.

### Five non-negotiable visual anchors
1. Production design carries enormous visual responsibility.
2. Atmosphere makes light visible: smoke, rain, dust, steam, mist, sand, snow, condensation.
3. Strong backlight or directional shafts carve depth through complex environments.
4. Foreground layers create visual density.
5. Low camera positions often give structures, machines, crowds, or warriors physical weight.

**Minimum visibility rule:** At least four of these five anchors must be visibly present in the generated image. All five should be encoded in the prompt unless a locked user requirement conflicts.

### Style-specific compilation sequence
1. **Lock the subject.** Preserve every user-required identity/species/object, clothing item, color, prop, action, and setting constraint.
2. **Establish the visual premise.** Use the logic of **ATMOSPHERIC WORLDFORGE / CIS-44** rather than adding generic cinematic adjectives. The deployment block above is the governing summary.
3. **Compile camera + composition.** Translate the profile's camera/composition rules into one explicit camera location, distance, framing, spatial behavior, and foreground/background relationship.
4. **Compile light.** Name the physical or psychological source, direction, hardness/softness, contrast behavior, and what it does to faces/materials.
5. **Compile color + materials.** Put the style palette into actual objects, surfaces, weather, wardrobe, architecture, practical light, landscape, skin, or props before using global grading language.
6. **Compile environment.** Make the space carry the style through architecture, geography, social context, production design, weather, and tactile material behavior.
7. **Compile character/action direction.** Specify posture, gaze, expression, movement, and emotional temperature so the subject participates in the visual grammar rather than merely standing inside it.
8. **Enforce the five anchors.** Check the prompt line-by-line and add any missing core anchor in concrete visual form.
9. **Run the anti-drift filter.** Reject or rewrite these failure modes: atmosphere with no source; generic blue sci-fi; empty clean sets; digital plastic surfaces; light that does not interact with weather/material; production design reduced to background wallpaper.
10. **Assemble one causal prompt.** The final instruction must read like a photographable scene, not a bag of adjectives.

### Compiled output checklist
- **STYLE:** ATMOSPHERIC WORLDFORGE / CIS-44
- **SUBJECT LOCK:** exact user content preserved
- **CAMERA:** physical placement + framing + spatial behavior
- **LIGHT:** source + direction + contrast behavior
- **COLOR/MATERIALS:** object-level palette + tactile surfaces
- **ENVIRONMENT:** style-specific spatial/production-design logic
- **CHARACTER/ACTION:** posture + gaze + expression + movement
- **CORE ANCHORS:** all five represented in the prompt
- **ANTI-DRIFT:** Avoid-rule conflicts removed
- **FINAL PROMPT:** one integrated generation instruction


## Style Fidelity Gate
**Pass threshold:** average fidelity score >= **8.0/10**, Signature Fidelity >= **8.0**, Content Preservation >= **9.0**, and no other dimension below **7.5**.

### Profile-specific signature test
- Anchor 1: Production design carries enormous visual responsibility.
- Anchor 2: Atmosphere makes light visible: smoke, rain, dust, steam, mist, sand, snow, condensation.
- Anchor 3: Strong backlight or directional shafts carve depth through complex environments.
- Anchor 4: Foreground layers create visual density.
- Anchor 5: Low camera positions often give structures, machines, crowds, or warriors physical weight.

The image fails signature fidelity if fewer than four anchors are clearly visible.

### Score after generation
Score **Content Preservation, Camera/Composition, Lens/Space, Lighting, Color/Materials, Environment/Texture, Character/Action, and Signature Fidelity** from 0-10 using the global Fidelity Gate.

### Correction rule
If any passing condition fails, write a repair delta only for the failed dimensions, preserve successful dimensions, and regenerate. Run no more than two automatic repair cycles. Do not respond to failure by making the image generically "more cinematic."


### Research traceability record
**Traceability confidence:** HIGH

**Evidence-use instruction:** Use these anchors to support the visual rules above. Do not infer unsupported technical specifications.

- [TECH-1] *American Cinematographer* — *Alien*: directional low-key spaceship lighting, fluorescent/tungsten practical logic, anamorphic staging, handheld panic, and designed environment.
- [TECH-1] *American Cinematographer* — *Blade Runner*: noir shafts, backlight, contrast, neon/rain atmosphere, and unusual angles.
- [TECH-1] *American Cinematographer* — *Gladiator*: strong frames, low camera positions, multi-camera battle texture, dust/smoke, and location-specific color.

---

# 45. CHADIAN LUMINOUS MINIMALISM
**Style ID:** CIS-45  
**Research Lineage:** Mahamat-Saleh Haroun  
**Representative works studied:** *Abouna*, *Daratt*, *A Screaming Man*, *Grigris*, *Lingui, the Sacred Bonds*

## Research synthesis
The recurring visual language is **spare, painterly humanism in which color, light, shadow, silence, and ordinary objects carry emotional weight**. Haroun has spoken about color drawn from Chad — yellow, orange, ochre — and about visual metaphor such as movement from tunnel/darkness into light. Critical discussion notes fixed or patient compositions, thick night, Caravaggio-like contrast, vivid local color, and a preference for telling the story visually rather than through excessive dialogue. The frame is often simple enough that one body or object becomes intensely meaningful.

## Persistent visual invariants
- Composition is spare and readable rather than crowded.
- Warm local color — ochre, yellow, orange, earth — can be vivid without becoming a tourist filter.
- Night may be deep and dense, with faces emerging through controlled pools of light.
- Fixed or patient wide framing supports dignity.
- Everyday objects can become visual metaphors through repetition and context.
- Dialogue may be minimal; posture, distance, and light carry narrative.
- Movement into or out of light can signify emotional possibility.
- Style follows content rather than forcing every scene into the same formal device.

## AI image-construction rules
### Composition
Use simple rooms, courtyards, streets, workshops, water, walls, gates, vehicles, or open landscape. Limit competing objects. Place the subject so distance between people becomes emotionally readable.

### Lighting
Day: hard or warm natural sun, shaded walls, reflected earth color. Night: dark sky/room with one strong practical or directional source modeling faces and hands. Permit Caravaggio-like contrast without theatrical excess.

### Color
Use ochre, yellow, orange, earth, dark blue/black, skin, cloth, painted walls, and small saturated accents tied to the location. Avoid a global orange grade.

### Object rule
Choose one ordinary object — fan, motorcycle, uniform, chair, water container, phone, fabric, tool — and let its repeated presence carry emotion or social meaning.

### Avoid
- visual clutter
- generic 'African warmth'
- over-filled frames
- excessive dialogue-poster posing
- fake painterly filters

## AI Deployment Block
**CHADIAN LUMINOUS MINIMALISM / CIS-45:** Use spare, patient composition, vivid but location-grounded earth color, deep night, and directional natural/practical light to give bodies and ordinary objects emotional weight. Keep the frame uncluttered enough that posture, distance, a doorway, wall, chair, vehicle, tool, or patch of light can tell the story. Let movement between darkness and light become a metaphor when appropriate. Avoid generic orange grading, crowded design, decorative painterly filters, and exoticized warmth.

## Style Compiler
**Compiler role:** Convert any user subject into this visual system without changing the user's required content.

### Five non-negotiable visual anchors
1. Composition is spare and readable rather than crowded.
2. Warm local color — ochre, yellow, orange, earth — can be vivid without becoming a tourist filter.
3. Night may be deep and dense, with faces emerging through controlled pools of light.
4. Fixed or patient wide framing supports dignity.
5. Everyday objects can become visual metaphors through repetition and context.

**Minimum visibility rule:** At least four of these five anchors must be visibly present in the generated image. All five should be encoded in the prompt unless a locked user requirement conflicts.

### Style-specific compilation sequence
1. **Lock the subject.** Preserve every user-required identity/species/object, clothing item, color, prop, action, and setting constraint.
2. **Establish the visual premise.** Use the logic of **CHADIAN LUMINOUS MINIMALISM / CIS-45** rather than adding generic cinematic adjectives. The deployment block above is the governing summary.
3. **Compile camera + composition.** Translate the profile's camera/composition rules into one explicit camera location, distance, framing, spatial behavior, and foreground/background relationship.
4. **Compile light.** Name the physical or psychological source, direction, hardness/softness, contrast behavior, and what it does to faces/materials.
5. **Compile color + materials.** Put the style palette into actual objects, surfaces, weather, wardrobe, architecture, practical light, landscape, skin, or props before using global grading language.
6. **Compile environment.** Make the space carry the style through architecture, geography, social context, production design, weather, and tactile material behavior.
7. **Compile character/action direction.** Specify posture, gaze, expression, movement, and emotional temperature so the subject participates in the visual grammar rather than merely standing inside it.
8. **Enforce the five anchors.** Check the prompt line-by-line and add any missing core anchor in concrete visual form.
9. **Run the anti-drift filter.** Reject or rewrite these failure modes: visual clutter; generic 'African warmth'; over-filled frames; excessive dialogue-poster posing; fake painterly filters.
10. **Assemble one causal prompt.** The final instruction must read like a photographable scene, not a bag of adjectives.

### Compiled output checklist
- **STYLE:** CHADIAN LUMINOUS MINIMALISM / CIS-45
- **SUBJECT LOCK:** exact user content preserved
- **CAMERA:** physical placement + framing + spatial behavior
- **LIGHT:** source + direction + contrast behavior
- **COLOR/MATERIALS:** object-level palette + tactile surfaces
- **ENVIRONMENT:** style-specific spatial/production-design logic
- **CHARACTER/ACTION:** posture + gaze + expression + movement
- **CORE ANCHORS:** all five represented in the prompt
- **ANTI-DRIFT:** Avoid-rule conflicts removed
- **FINAL PROMPT:** one integrated generation instruction


## Style Fidelity Gate
**Pass threshold:** average fidelity score >= **8.0/10**, Signature Fidelity >= **8.0**, Content Preservation >= **9.0**, and no other dimension below **7.5**.

### Profile-specific signature test
- Anchor 1: Composition is spare and readable rather than crowded.
- Anchor 2: Warm local color — ochre, yellow, orange, earth — can be vivid without becoming a tourist filter.
- Anchor 3: Night may be deep and dense, with faces emerging through controlled pools of light.
- Anchor 4: Fixed or patient wide framing supports dignity.
- Anchor 5: Everyday objects can become visual metaphors through repetition and context.

The image fails signature fidelity if fewer than four anchors are clearly visible.

### Score after generation
Score **Content Preservation, Camera/Composition, Lens/Space, Lighting, Color/Materials, Environment/Texture, Character/Action, and Signature Fidelity** from 0-10 using the global Fidelity Gate.

### Correction rule
If any passing condition fails, write a repair delta only for the failed dimensions, preserve successful dimensions, and regenerate. Run no more than two automatic repair cycles. Do not respond to failure by making the image generically "more cinematic."


### Research traceability record
**Traceability confidence:** MEDIUM-HIGH

**Evidence-use instruction:** Use these anchors to support the visual rules above. Do not infer unsupported technical specifications.

- [TECH-1] Haroun interviews: color rooted in Chad, visual metaphor from darkness/tunnel toward light, and style following content.
- [CRIT-4] Critical analysis of *Daratt*, *A Screaming Man*, and *Lingui*: spare painterly frames, thick nights, color/light/shadow as emotion, and visual storytelling with minimal dialogue.

---

# 46. SENSUAL LANDSCAPE INTERIORISM
**Style ID:** CIS-46  
**Research Lineage:** Jane Campion  
**Representative works studied:** *An Angel at My Table*, *The Piano*, *The Portrait of a Lady*, *Bright Star*, *The Power of the Dog*

## Research synthesis
The recurring grammar is **psychological interiority expressed through landscape, weather, touch, partial point of view, and tactile detail**. Critical analysis of *The Piano* describes landscape as simultaneously gritty and uncanny, with bush that can feel mossy, dark, intimate, and almost underwater. Campion's work repeatedly juxtaposes large landscapes with hands, clothing, hair, skin, flowers, mud, fabric, wood, piano keys, letters, or domestic objects. Recent work continues to value natural-light imperfection rather than smoothing reality into ideal beauty.

## Persistent visual invariants
- Landscape operates as psychological pressure, desire, threat, freedom, or secrecy.
- Tactile details of bodies and materials carry interior emotion.
- Female or otherwise intimate subjectivity can be expressed through partial/fragmented point of view.
- Nature is not merely scenic; weather, mud, grass, water, mountains, and wind act on bodies.
- Natural light is allowed to be imperfect or odd.
- Wide landscape and bodily close detail create a productive scale contrast.
- Cool, desaturated, mossy, earthy, or natural palettes may be punctuated by warm interior color.
- Storyboarding/compositional precision can coexist with organic nature.

## AI image-construction rules
### Composition
Pair one environmental force with one tactile human detail. Example: vast mountain + hand gripping leather; wet forest + mud on skirt; beach + hair blowing across face; bright field + crushed flower; dark room + fingers on fabric.

### Camera
Use wide landscape, medium profile, partial POV, shoulder view, hand/body detail, or intimate close-up. Do not rely exclusively on conventional frontal portraiture.

### Lighting
Use real sun, cloud, fog, window, fire, dawn/dusk, or weather-softened light. Accept uneven illumination when it makes nature feel present.

### Color/texture
Favor moss, slate, earth, cream, skin, wool, leather, grass, water, wood, faded floral, smoke, dust. Keep materials sensual but not glossy.

### Avoid
- postcard landscapes
- romantic soft-focus everywhere
- fashion poses in nature
- perfect golden-hour light as default
- tactile close-ups with no emotional connection

## AI Deployment Block
**SENSUAL LANDSCAPE INTERIORISM / CIS-46:** Express inner life through physical contact with landscape and material. Pair large natural forces — mountain, bush, beach, field, weather, mud, water, wind — with intimate details of hands, hair, skin, fabric, flowers, wood, leather, or objects. Use natural light with real imperfection and alternate between environmental scale and bodily proximity. Let nature pressure or reveal the character instead of decorating them. Avoid postcard scenery, universal golden hour, fashion posing, and soft focus with no psychological purpose.

## Style Compiler
**Compiler role:** Convert any user subject into this visual system without changing the user's required content.

### Five non-negotiable visual anchors
1. Landscape operates as psychological pressure, desire, threat, freedom, or secrecy.
2. Tactile details of bodies and materials carry interior emotion.
3. Female or otherwise intimate subjectivity can be expressed through partial/fragmented point of view.
4. Nature is not merely scenic; weather, mud, grass, water, mountains, and wind act on bodies.
5. Natural light is allowed to be imperfect or odd.

**Minimum visibility rule:** At least four of these five anchors must be visibly present in the generated image. All five should be encoded in the prompt unless a locked user requirement conflicts.

### Style-specific compilation sequence
1. **Lock the subject.** Preserve every user-required identity/species/object, clothing item, color, prop, action, and setting constraint.
2. **Establish the visual premise.** Use the logic of **SENSUAL LANDSCAPE INTERIORISM / CIS-46** rather than adding generic cinematic adjectives. The deployment block above is the governing summary.
3. **Compile camera + composition.** Translate the profile's camera/composition rules into one explicit camera location, distance, framing, spatial behavior, and foreground/background relationship.
4. **Compile light.** Name the physical or psychological source, direction, hardness/softness, contrast behavior, and what it does to faces/materials.
5. **Compile color + materials.** Put the style palette into actual objects, surfaces, weather, wardrobe, architecture, practical light, landscape, skin, or props before using global grading language.
6. **Compile environment.** Make the space carry the style through architecture, geography, social context, production design, weather, and tactile material behavior.
7. **Compile character/action direction.** Specify posture, gaze, expression, movement, and emotional temperature so the subject participates in the visual grammar rather than merely standing inside it.
8. **Enforce the five anchors.** Check the prompt line-by-line and add any missing core anchor in concrete visual form.
9. **Run the anti-drift filter.** Reject or rewrite these failure modes: postcard landscapes; romantic soft-focus everywhere; fashion poses in nature; perfect golden-hour light as default; tactile close-ups with no emotional connection.
10. **Assemble one causal prompt.** The final instruction must read like a photographable scene, not a bag of adjectives.

### Compiled output checklist
- **STYLE:** SENSUAL LANDSCAPE INTERIORISM / CIS-46
- **SUBJECT LOCK:** exact user content preserved
- **CAMERA:** physical placement + framing + spatial behavior
- **LIGHT:** source + direction + contrast behavior
- **COLOR/MATERIALS:** object-level palette + tactile surfaces
- **ENVIRONMENT:** style-specific spatial/production-design logic
- **CHARACTER/ACTION:** posture + gaze + expression + movement
- **CORE ANCHORS:** all five represented in the prompt
- **ANTI-DRIFT:** Avoid-rule conflicts removed
- **FINAL PROMPT:** one integrated generation instruction


## Style Fidelity Gate
**Pass threshold:** average fidelity score >= **8.0/10**, Signature Fidelity >= **8.0**, Content Preservation >= **9.0**, and no other dimension below **7.5**.

### Profile-specific signature test
- Anchor 1: Landscape operates as psychological pressure, desire, threat, freedom, or secrecy.
- Anchor 2: Tactile details of bodies and materials carry interior emotion.
- Anchor 3: Female or otherwise intimate subjectivity can be expressed through partial/fragmented point of view.
- Anchor 4: Nature is not merely scenic; weather, mud, grass, water, mountains, and wind act on bodies.
- Anchor 5: Natural light is allowed to be imperfect or odd.

The image fails signature fidelity if fewer than four anchors are clearly visible.

### Score after generation
Score **Content Preservation, Camera/Composition, Lens/Space, Lighting, Color/Materials, Environment/Texture, Character/Action, and Signature Fidelity** from 0-10 using the global Fidelity Gate.

### Correction rule
If any passing condition fails, write a repair delta only for the failed dimensions, preserve successful dimensions, and regenerate. Run no more than two automatic repair cycles. Do not respond to failure by making the image generically "more cinematic."


### Research traceability record
**Traceability confidence:** HIGH

**Evidence-use instruction:** Use these anchors to support the visual rules above. Do not infer unsupported technical specifications.

- [INST-2] Critical/BFI analysis of *The Piano*: Ada's point of view, tactile detail, landscape as both gritty reality and uncanny interior space.
- [TECH-1] Cinematography interviews for *The Power of the Dog*: valuing real natural-sun imperfection and image specificity over idealized polish.

---

# 47. HISTORIC COUNTER-MONTAGE
**Style ID:** CIS-47  
**Research Lineage:** Raoul Peck  
**Representative works studied:** *Lumumba*, *I Am Not Your Negro*, *The Young Karl Marx*, *Exterminate All the Brutes*

## Research synthesis
The recurring grammar is **history reconstructed through collision of evidence rather than presented as a seamless authoritative image**. *I Am Not Your Negro* and *Exterminate All the Brutes* layer archival footage, photographs, television, newsreel, contemporary imagery, voice, text, and reenactment to expose who controls historical narrative. Even in dramatic features, framing tends toward political clarity rather than ornamental period nostalgia. The important visual signature is the deliberate relationship among different temporal records.

## Persistent visual invariants
- Archival image and contemporary image are placed in argument with each other.
- Photographs, television frames, documents, newspapers, speeches, maps, or public monuments can become visual evidence.
- Historical material retains its native texture instead of being cosmetically modernized.
- Reenactment should clarify history, not pretend to replace evidence.
- Public space, crowd, institution, portrait, and archive are connected structurally.
- Text/voice-implied material may guide what an image means without requiring decorative graphics.
- Montage can reveal continuity between past structures and present space.
- Political imagery remains human-centered rather than abstractly didactic.

## AI image-construction rules
### Evidence layers
Choose 2-3 temporal materials: archival black-and-white still, 16mm/newsreel frame, television image, typed document, contemporary color photograph, reenacted scene. Make their different material qualities visible.

### Composition
Use split temporal echoes, photograph-in-scene, projection, television, newspaper, public monument, crowd image, courtroom/parliament/street, portrait beside document, or a contemporary location haunted by archival evidence.

### Texture
Respect medium: silver-grain still, faded print, broadcast scanlines/softness, 16mm grain, modern digital clarity. Do not homogenize.

### Human rule
Anchor history to faces, bodies, labor, testimony, or public gathering. Avoid infographic-only abstraction.

### Avoid
- fake generic archive scratches
- glossy reenactment pretending to be original footage
- flattening all eras into one color grade
- decorative newspaper collage
- historical spectacle without evidentiary relationship

## AI Deployment Block
**HISTORIC COUNTER-MONTAGE / CIS-47:** Build the image as an argument among different records of time. Combine 2-3 materially distinct evidence layers such as archival photograph, newsreel/16mm, television, document, contemporary color, public monument, or restrained reenactment. Preserve each medium's texture and let past and present visually answer one another. Anchor history to faces, bodies, testimony, labor, or public space. Avoid generic archive scratches, decorative newspaper collage, seamless fake history, and one-grade homogenization of different eras.

## Style Compiler
**Compiler role:** Convert any user subject into this visual system without changing the user's required content.

### Five non-negotiable visual anchors
1. Archival image and contemporary image are placed in argument with each other.
2. Photographs, television frames, documents, newspapers, speeches, maps, or public monuments can become visual evidence.
3. Historical material retains its native texture instead of being cosmetically modernized.
4. Reenactment should clarify history, not pretend to replace evidence.
5. Public space, crowd, institution, portrait, and archive are connected structurally.

**Minimum visibility rule:** At least four of these five anchors must be visibly present in the generated image. All five should be encoded in the prompt unless a locked user requirement conflicts.

### Style-specific compilation sequence
1. **Lock the subject.** Preserve every user-required identity/species/object, clothing item, color, prop, action, and setting constraint.
2. **Establish the visual premise.** Use the logic of **HISTORIC COUNTER-MONTAGE / CIS-47** rather than adding generic cinematic adjectives. The deployment block above is the governing summary.
3. **Compile camera + composition.** Translate the profile's camera/composition rules into one explicit camera location, distance, framing, spatial behavior, and foreground/background relationship.
4. **Compile light.** Name the physical or psychological source, direction, hardness/softness, contrast behavior, and what it does to faces/materials.
5. **Compile color + materials.** Put the style palette into actual objects, surfaces, weather, wardrobe, architecture, practical light, landscape, skin, or props before using global grading language.
6. **Compile environment.** Make the space carry the style through architecture, geography, social context, production design, weather, and tactile material behavior.
7. **Compile character/action direction.** Specify posture, gaze, expression, movement, and emotional temperature so the subject participates in the visual grammar rather than merely standing inside it.
8. **Enforce the five anchors.** Check the prompt line-by-line and add any missing core anchor in concrete visual form.
9. **Run the anti-drift filter.** Reject or rewrite these failure modes: fake generic archive scratches; glossy reenactment pretending to be original footage; flattening all eras into one color grade; decorative newspaper collage; historical spectacle without evidentiary relationship.
10. **Assemble one causal prompt.** The final instruction must read like a photographable scene, not a bag of adjectives.

### Compiled output checklist
- **STYLE:** HISTORIC COUNTER-MONTAGE / CIS-47
- **SUBJECT LOCK:** exact user content preserved
- **CAMERA:** physical placement + framing + spatial behavior
- **LIGHT:** source + direction + contrast behavior
- **COLOR/MATERIALS:** object-level palette + tactile surfaces
- **ENVIRONMENT:** style-specific spatial/production-design logic
- **CHARACTER/ACTION:** posture + gaze + expression + movement
- **CORE ANCHORS:** all five represented in the prompt
- **ANTI-DRIFT:** Avoid-rule conflicts removed
- **FINAL PROMPT:** one integrated generation instruction


## Style Fidelity Gate
**Pass threshold:** average fidelity score >= **8.0/10**, Signature Fidelity >= **8.0**, Content Preservation >= **9.0**, and no other dimension below **7.5**.

### Profile-specific signature test
- Anchor 1: Archival image and contemporary image are placed in argument with each other.
- Anchor 2: Photographs, television frames, documents, newspapers, speeches, maps, or public monuments can become visual evidence.
- Anchor 3: Historical material retains its native texture instead of being cosmetically modernized.
- Anchor 4: Reenactment should clarify history, not pretend to replace evidence.
- Anchor 5: Public space, crowd, institution, portrait, and archive are connected structurally.

The image fails signature fidelity if fewer than four anchors are clearly visible.

### Score after generation
Score **Content Preservation, Camera/Composition, Lens/Space, Lighting, Color/Materials, Environment/Texture, Character/Action, and Signature Fidelity** from 0-10 using the global Fidelity Gate.

### Correction rule
If any passing condition fails, write a repair delta only for the failed dimensions, preserve successful dimensions, and regenerate. Run no more than two automatic repair cycles. Do not respond to failure by making the image generically "more cinematic."


### Research traceability record
**Traceability confidence:** MEDIUM

**Evidence-use instruction:** Use these anchors to support the visual rules above. Do not infer unsupported technical specifications.

- [INST-2] BFI analysis of *I Am Not Your Negro*: layered Baldwin television appearances, archival film, photography, and contemporary footage without conventional talking-head structure.
- [CRIT-4] Comparative study of *Lumumba* and *Exterminate All the Brutes*: political reconstruction through evidence, reenactment, and historical montage.

---

# 48. FRAGMENTED SENSORY MEMORY
**Style ID:** CIS-48  
**Research Lineage:** Lynne Ramsay  
**Representative works studied:** *Ratcatcher*, *Morvern Callar*, *We Need to Talk About Kevin*, *You Were Never Really Here*

## Research synthesis
The recurring grammar is **emotion reconstructed from fragments rather than explained through conventional scene coverage**. Critical writing on *Ratcatcher* emphasizes concentrated details of bodies and objects, offscreen possibility, slow motion, and poetic compositions that let one small image carry an entire dramatic beat. Ramsay often withholds the central action and photographs what remains around it: curtain, hand, stain, food, shoe, blood, water, hair, doorway, sound-implied violence. Color can become intensely symbolic — especially a single saturated color against an otherwise depleted world.

## Persistent visual invariants
- Detail can replace exposition.
- Violence or major action may remain partly or entirely offscreen.
- Objects, body fragments, and textures carry memory and guilt.
- Ellipsis creates emotional participation: the viewer must connect fragments.
- Slow motion or suspended gesture can make ordinary action uncanny or lyrical.
- One strong color family can haunt an otherwise muted palette.
- Frames have photographic precision even when narrative information is incomplete.
- Sound-implied space should be suggested visually through what the camera chooses not to show.

## AI image-construction rules
### Fragment rule
Do not illustrate the whole event. Choose the emotionally charged remainder: hand on sink, red paint on wall, shoe in hallway, curtain moving, wet hair, crushed food, reflection, blood diluted in water, empty chair, bruised knuckles, torn fabric.

### Composition
Use cropped bodies, partial faces, edges of rooms, reflections, extreme details, or a still object surrounded by negative space. Let offscreen space feel active.

### Color
Choose one persistent color signal only when story-relevant — red, yellow, blue, green — and let it recur in object/material form rather than global grading.

### Lighting/texture
Favor naturalistic but precise light, tangible grain, wet surfaces, skin, cloth, glass, food, metal, water, and domestic texture.

### Avoid
- explaining the entire narrative in one frame
- generic moody desaturation
- random symbolic red
- gore shown merely for impact
- dreamy blur used as a substitute for memory

## AI Deployment Block
**FRAGMENTED SENSORY MEMORY / CIS-48:** Do not illustrate the entire event. Photograph the emotionally charged fragment left behind: hand, stain, curtain, shoe, food, reflection, water, bruised skin, torn fabric, empty space, or object. Use cropped bodies, partial rooms, offscreen pressure, precise tactile light, and one story-specific color signal when useful. Let the viewer reconstruct violence, guilt, desire, or memory from sensory evidence. Avoid exposition-heavy compositions, arbitrary red symbolism, generic desaturation, gratuitous gore, and dreamy blur with no material anchor.

## Style Compiler
**Compiler role:** Convert any user subject into this visual system without changing the user's required content.

### Five non-negotiable visual anchors
1. Detail can replace exposition.
2. Violence or major action may remain partly or entirely offscreen.
3. Objects, body fragments, and textures carry memory and guilt.
4. Ellipsis creates emotional participation: the viewer must connect fragments.
5. Slow motion or suspended gesture can make ordinary action uncanny or lyrical.

**Minimum visibility rule:** At least four of these five anchors must be visibly present in the generated image. All five should be encoded in the prompt unless a locked user requirement conflicts.

### Style-specific compilation sequence
1. **Lock the subject.** Preserve every user-required identity/species/object, clothing item, color, prop, action, and setting constraint.
2. **Establish the visual premise.** Use the logic of **FRAGMENTED SENSORY MEMORY / CIS-48** rather than adding generic cinematic adjectives. The deployment block above is the governing summary.
3. **Compile camera + composition.** Translate the profile's camera/composition rules into one explicit camera location, distance, framing, spatial behavior, and foreground/background relationship.
4. **Compile light.** Name the physical or psychological source, direction, hardness/softness, contrast behavior, and what it does to faces/materials.
5. **Compile color + materials.** Put the style palette into actual objects, surfaces, weather, wardrobe, architecture, practical light, landscape, skin, or props before using global grading language.
6. **Compile environment.** Make the space carry the style through architecture, geography, social context, production design, weather, and tactile material behavior.
7. **Compile character/action direction.** Specify posture, gaze, expression, movement, and emotional temperature so the subject participates in the visual grammar rather than merely standing inside it.
8. **Enforce the five anchors.** Check the prompt line-by-line and add any missing core anchor in concrete visual form.
9. **Run the anti-drift filter.** Reject or rewrite these failure modes: explaining the entire narrative in one frame; generic moody desaturation; random symbolic red; gore shown merely for impact; dreamy blur used as a substitute for memory.
10. **Assemble one causal prompt.** The final instruction must read like a photographable scene, not a bag of adjectives.

### Compiled output checklist
- **STYLE:** FRAGMENTED SENSORY MEMORY / CIS-48
- **SUBJECT LOCK:** exact user content preserved
- **CAMERA:** physical placement + framing + spatial behavior
- **LIGHT:** source + direction + contrast behavior
- **COLOR/MATERIALS:** object-level palette + tactile surfaces
- **ENVIRONMENT:** style-specific spatial/production-design logic
- **CHARACTER/ACTION:** posture + gaze + expression + movement
- **CORE ANCHORS:** all five represented in the prompt
- **ANTI-DRIFT:** Avoid-rule conflicts removed
- **FINAL PROMPT:** one integrated generation instruction


## Style Fidelity Gate
**Pass threshold:** average fidelity score >= **8.0/10**, Signature Fidelity >= **8.0**, Content Preservation >= **9.0**, and no other dimension below **7.5**.

### Profile-specific signature test
- Anchor 1: Detail can replace exposition.
- Anchor 2: Violence or major action may remain partly or entirely offscreen.
- Anchor 3: Objects, body fragments, and textures carry memory and guilt.
- Anchor 4: Ellipsis creates emotional participation: the viewer must connect fragments.
- Anchor 5: Slow motion or suspended gesture can make ordinary action uncanny or lyrical.

The image fails signature fidelity if fewer than four anchors are clearly visible.

### Score after generation
Score **Content Preservation, Camera/Composition, Lens/Space, Lighting, Color/Materials, Environment/Texture, Character/Action, and Signature Fidelity** from 0-10 using the global Fidelity Gate.

### Correction rule
If any passing condition fails, write a repair delta only for the failed dimensions, preserve successful dimensions, and regenerate. Run no more than two automatic repair cycles. Do not respond to failure by making the image generically "more cinematic."


### Research traceability record
**Traceability confidence:** MEDIUM

**Evidence-use instruction:** Use these anchors to support the visual rules above. Do not infer unsupported technical specifications.

- [INST-2] Criterion analysis of *Ratcatcher*: concentrated detail, objects/bodies, offscreen possibility, suggestive composition, and slow-motion lyricism.
- [FRAME-3] Critical comparison across *Morvern Callar*, *We Need to Talk About Kevin*, and *You Were Never Really Here*: recurring visual fragments, color echoes, memory, guilt, and withheld violence.

---

# 49. EQUATORIAL CIVIC WITNESS
**Style ID:** CIS-49  
**Research Lineage:** Bassek ba Kobhio  
**Representative works studied:** *Sango Malo*, *Le Grand Blanc de Lambarene*, *The Silence of the Forest* (co-directed with Didier Ouenangare)

## Research synthesis
The available English-language technical cinematography documentation is thinner here, so this profile is intentionally conservative and anchored in film records, interviews, critical description, and representative scenes rather than invented camera specifications. The recurring visual direction is **social and civic realism rooted in Central African place, community interaction, natural environment, and anti-colonial point of view**. Writing on *Sango Malo* remembers fixed observation of torrential rain in the school courtyard, the sovereignty of nature, simplicity of framing, and authentic social dynamics of village education and political change. *Le Grand Blanc de Lambarene* uses location and juxtaposed episodes to reverse the usual colonial gaze and examine European behavior from an African perspective.

## Persistent visual invariants
- Community and social systems are more important than individual glamour.
- Natural environment — forest, rain, earth, courtyard, road, village — has autonomous presence.
- Simple, patient frames can let weather and collective behavior become the event.
- Schools, clinics, village meetings, homes, roads, and institutions become civic stages.
- The point of view resists colonial hero framing and centers African social interpretation.
- Juxtaposed scenes may reveal contradictions rather than forcing a single heroic narrative.
- Local sound-implied environment should be visible through rain, trees, open air, crowd spacing, or work.
- Real location texture is preferable to generalized 'African' production design.

## AI image-construction rules
### Composition
Use patient wide or medium-wide community framing: schoolyard, classroom, village meeting, clinic, forest edge, road, courtyard, house, agricultural work, public gathering. Let several people occupy the frame in functional relation.

### Environment
Give rain, forest canopy, mud, open sky, wood, concrete, cloth, tools, desks, clinic equipment, road dust, or local architecture real material presence. Weather should be allowed to dominate a frame when appropriate.

### Lighting/color
Use available daylight, overcast rain, shaded forest, practical interiors, sun, or simple lamps. Keep color tied to vegetation, soil, buildings, clothing, and actual local materials. Avoid an automatic warm/orange 'Africa' grade.

### Perspective rule
When colonial or institutional power appears, do not automatically make the outsider the heroic visual center. Arrange the frame so community reaction, local interpretation, or the surrounding social system remains visible.

### Avoid
- safari/postcard aesthetics
- invented technical claims unsupported by the films
- generic tribal decoration
- colonial savior framing
- artificial rain/forest mysticism

## AI Deployment Block
**EQUATORIAL CIVIC WITNESS / CIS-49:** Use patient, socially readable framing rooted in real Central African community space and natural environment. Let schools, clinics, meetings, courtyards, roads, forest, rain, work, and collective behavior carry the image. Preserve available light, real weather, local material color, and community reaction. When institutions or outsiders enter, keep the surrounding African social point of view visible rather than automatically centering external authority. Avoid safari warmth, generic tribal design, colonial-savior composition, and mystical treatment of forest or rain.

## Style Compiler
**Compiler role:** Convert any user subject into this visual system without changing the user's required content.

### Five non-negotiable visual anchors
1. Community and social systems are more important than individual glamour.
2. Natural environment — forest, rain, earth, courtyard, road, village — has autonomous presence.
3. Simple, patient frames can let weather and collective behavior become the event.
4. Schools, clinics, village meetings, homes, roads, and institutions become civic stages.
5. The point of view resists colonial hero framing and centers African social interpretation.

**Minimum visibility rule:** At least four of these five anchors must be visibly present in the generated image. All five should be encoded in the prompt unless a locked user requirement conflicts.

### Style-specific compilation sequence
1. **Lock the subject.** Preserve every user-required identity/species/object, clothing item, color, prop, action, and setting constraint.
2. **Establish the visual premise.** Use the logic of **EQUATORIAL CIVIC WITNESS / CIS-49** rather than adding generic cinematic adjectives. The deployment block above is the governing summary.
3. **Compile camera + composition.** Translate the profile's camera/composition rules into one explicit camera location, distance, framing, spatial behavior, and foreground/background relationship.
4. **Compile light.** Name the physical or psychological source, direction, hardness/softness, contrast behavior, and what it does to faces/materials.
5. **Compile color + materials.** Put the style palette into actual objects, surfaces, weather, wardrobe, architecture, practical light, landscape, skin, or props before using global grading language.
6. **Compile environment.** Make the space carry the style through architecture, geography, social context, production design, weather, and tactile material behavior.
7. **Compile character/action direction.** Specify posture, gaze, expression, movement, and emotional temperature so the subject participates in the visual grammar rather than merely standing inside it.
8. **Enforce the five anchors.** Check the prompt line-by-line and add any missing core anchor in concrete visual form.
9. **Run the anti-drift filter.** Reject or rewrite these failure modes: safari/postcard aesthetics; invented technical claims unsupported by the films; generic tribal decoration; colonial savior framing; artificial rain/forest mysticism.
10. **Assemble one causal prompt.** The final instruction must read like a photographable scene, not a bag of adjectives.

### Compiled output checklist
- **STYLE:** EQUATORIAL CIVIC WITNESS / CIS-49
- **SUBJECT LOCK:** exact user content preserved
- **CAMERA:** physical placement + framing + spatial behavior
- **LIGHT:** source + direction + contrast behavior
- **COLOR/MATERIALS:** object-level palette + tactile surfaces
- **ENVIRONMENT:** style-specific spatial/production-design logic
- **CHARACTER/ACTION:** posture + gaze + expression + movement
- **CORE ANCHORS:** all five represented in the prompt
- **ANTI-DRIFT:** Avoid-rule conflicts removed
- **FINAL PROMPT:** one integrated generation instruction


## Style Fidelity Gate
**Pass threshold:** average fidelity score >= **8.0/10**, Signature Fidelity >= **8.0**, Content Preservation >= **9.0**, and no other dimension below **7.5**.

### Profile-specific signature test
- Anchor 1: Community and social systems are more important than individual glamour.
- Anchor 2: Natural environment — forest, rain, earth, courtyard, road, village — has autonomous presence.
- Anchor 3: Simple, patient frames can let weather and collective behavior become the event.
- Anchor 4: Schools, clinics, village meetings, homes, roads, and institutions become civic stages.
- Anchor 5: The point of view resists colonial hero framing and centers African social interpretation.

The image fails signature fidelity if fewer than four anchors are clearly visible.

### Score after generation
Score **Content Preservation, Camera/Composition, Lens/Space, Lighting, Color/Materials, Environment/Texture, Character/Action, and Signature Fidelity** from 0-10 using the global Fidelity Gate.

### Correction rule
If any passing condition fails, write a repair delta only for the failed dimensions, preserve successful dimensions, and regenerate. Run no more than two automatic repair cycles. Do not respond to failure by making the image generically "more cinematic."


### Research traceability record
**Traceability confidence:** CONSERVATIVE

**Evidence-use instruction:** Use these anchors to support the visual rules above. Do not infer unsupported technical specifications.

- [INST-2] Cannes / Africultures records for *Sango Malo* and its production/cinematography credits.
- [INST-2] California Newsreel: *Sango Malo* as an intimate portrait of social dynamics, education, democratic change, and village community.
- [CRIT-4] Afrofolio remembrance of the schoolyard rain sequence: fixed camera, torrential rain, silence, simplicity, and natural sovereignty.
- [CRIT-4] *Le Monde* / African cinema archives on *Le Grand Blanc de Lambarene*: episodic treatment of colonial history from an African critical viewpoint.

---

# 50. PSYCHOLOGICAL FACE CHAMBER
**Style ID:** CIS-50  
**Research Lineage:** Ingmar Bergman  
**Representative works studied:** *The Seventh Seal*, *Persona*, *Cries and Whispers*, *Scenes from a Marriage*, *Fanny and Alexander*

## Research synthesis
The recurring grammar is **the human face treated as psychological landscape, placed inside stripped, symbolically charged light and space**. Sven Nykvist's natural-light collaboration refined a style in which window light, soft overcast, and minimal apparatus could expose faces with extraordinary intimacy. *Persona* pushes high-contrast black-and-white, rigid composition, direct looks, and even the mechanism of film itself. *Cries and Whispers* demonstrates that the system is not limited to monochrome: saturated crimson rooms, white clothing, skin, and black create a severe symbolic chamber. The essential variable is psychological concentration, not one palette.

## Persistent visual invariants
- Faces are primary landscapes.
- Extreme or very close two-face compositions can collapse personal boundaries.
- Window/natural light reveals skin, eyes, age, fatigue, and emotional contradiction.
- Sparse interiors and negative space prevent distraction from psychology.
- High-contrast black-and-white or controlled symbolic color are both valid.
- Direct gaze into or near the camera can feel confessional or confrontational.
- Theatrical blocking and stillness are often more powerful than busy camera movement.
- Simple symbolic shapes — doorway, bed, table, cross, chessboard, curtain, wall — can carry existential weight.

## AI image-construction rules
### Portraiture
Move close enough that tiny facial changes matter. Use full face, profile, overlapping faces, face beside face, or one face emerging from shadow. Preserve skin texture, eye moisture, wrinkles, and asymmetry.

### Lighting
Use soft window light, overcast daylight, single practical lamp, candle, or severe directional source. For black-and-white, protect luminous midtones and deep but readable blacks. For color, choose a severe symbolic field such as crimson/white/black rather than many competing hues.

### Composition
Simplify the room. Use bed, wall, curtain, doorway, chair, table, window, or bare landscape. Let negative space and stillness concentrate the face.

### Character direction
Favor silence, shame, intimacy, fear, spiritual doubt, resentment, tenderness, aging, confession, or emotional ambiguity. Avoid theatrical facial exaggeration; the camera should notice the smallest shift.

### Avoid
- generic vintage-film filters
- ornate set decoration that competes with faces
- beauty retouching
- random expressionist shadows
- melodramatic crying as a shortcut for depth

## AI Deployment Block
**PSYCHOLOGICAL FACE CHAMBER / CIS-50:** Treat the human face as the primary landscape. Use close or extreme-close portraiture, overlapping or opposing faces, simple rooms, negative space, stillness, and natural/window or single-source light that reveals skin, eyes, age, and contradiction. Work either in precise high-contrast monochrome or a severely limited symbolic color field. Keep sets sparse and gestures small. Allow direct or near-direct gaze when confrontation or confession is needed. Avoid beauty retouching, decorative period filters, busy sets, and exaggerated performance.

## Style Compiler
**Compiler role:** Convert any user subject into this visual system without changing the user's required content.

### Five non-negotiable visual anchors
1. Faces are primary landscapes.
2. Extreme or very close two-face compositions can collapse personal boundaries.
3. Window/natural light reveals skin, eyes, age, fatigue, and emotional contradiction.
4. Sparse interiors and negative space prevent distraction from psychology.
5. High-contrast black-and-white or controlled symbolic color are both valid.

**Minimum visibility rule:** At least four of these five anchors must be visibly present in the generated image. All five should be encoded in the prompt unless a locked user requirement conflicts.

### Style-specific compilation sequence
1. **Lock the subject.** Preserve every user-required identity/species/object, clothing item, color, prop, action, and setting constraint.
2. **Establish the visual premise.** Use the logic of **PSYCHOLOGICAL FACE CHAMBER / CIS-50** rather than adding generic cinematic adjectives. The deployment block above is the governing summary.
3. **Compile camera + composition.** Translate the profile's camera/composition rules into one explicit camera location, distance, framing, spatial behavior, and foreground/background relationship.
4. **Compile light.** Name the physical or psychological source, direction, hardness/softness, contrast behavior, and what it does to faces/materials.
5. **Compile color + materials.** Put the style palette into actual objects, surfaces, weather, wardrobe, architecture, practical light, landscape, skin, or props before using global grading language.
6. **Compile environment.** Make the space carry the style through architecture, geography, social context, production design, weather, and tactile material behavior.
7. **Compile character/action direction.** Specify posture, gaze, expression, movement, and emotional temperature so the subject participates in the visual grammar rather than merely standing inside it.
8. **Enforce the five anchors.** Check the prompt line-by-line and add any missing core anchor in concrete visual form.
9. **Run the anti-drift filter.** Reject or rewrite these failure modes: generic vintage-film filters; ornate set decoration that competes with faces; beauty retouching; random expressionist shadows; melodramatic crying as a shortcut for depth.
10. **Assemble one causal prompt.** The final instruction must read like a photographable scene, not a bag of adjectives.

### Compiled output checklist
- **STYLE:** PSYCHOLOGICAL FACE CHAMBER / CIS-50
- **SUBJECT LOCK:** exact user content preserved
- **CAMERA:** physical placement + framing + spatial behavior
- **LIGHT:** source + direction + contrast behavior
- **COLOR/MATERIALS:** object-level palette + tactile surfaces
- **ENVIRONMENT:** style-specific spatial/production-design logic
- **CHARACTER/ACTION:** posture + gaze + expression + movement
- **CORE ANCHORS:** all five represented in the prompt
- **ANTI-DRIFT:** Avoid-rule conflicts removed
- **FINAL PROMPT:** one integrated generation instruction


## Style Fidelity Gate
**Pass threshold:** average fidelity score >= **8.0/10**, Signature Fidelity >= **8.0**, Content Preservation >= **9.0**, and no other dimension below **7.5**.

### Profile-specific signature test
- Anchor 1: Faces are primary landscapes.
- Anchor 2: Extreme or very close two-face compositions can collapse personal boundaries.
- Anchor 3: Window/natural light reveals skin, eyes, age, fatigue, and emotional contradiction.
- Anchor 4: Sparse interiors and negative space prevent distraction from psychology.
- Anchor 5: High-contrast black-and-white or controlled symbolic color are both valid.

The image fails signature fidelity if fewer than four anchors are clearly visible.

### Score after generation
Score **Content Preservation, Camera/Composition, Lens/Space, Lighting, Color/Materials, Environment/Texture, Character/Action, and Signature Fidelity** from 0-10 using the global Fidelity Gate.

### Correction rule
If any passing condition fails, write a repair delta only for the failed dimensions, preserve successful dimensions, and regenerate. Run no more than two automatic repair cycles. Do not respond to failure by making the image generically "more cinematic."


### Research traceability record
**Traceability confidence:** HIGH

**Evidence-use instruction:** Use these anchors to support the visual rules above. Do not infer unsupported technical specifications.

- [INST-2] BFI / Criterion analysis of *Persona*: high-contrast black-and-white, rigid construction, direct facial confrontation, and visible film mechanism.
- [TECH-1] Criterion / *American Cinematographer* materials on Sven Nykvist: natural light, minimalism, and the face as psychological 'X-ray.'
- [INST-2] BFI analysis of *Cries and Whispers*: crimson/white/black color chamber and concentrated human psychology.

---
# MASTER DEPLOYMENT INDEX

| Style ID | Branded Style Name | Primary Visual Function |
|---|---|---|
| CIS-01 | Sovereign Human Light | Dignified human/social realism with nuanced skin and motivated light |
| CIS-02 | Physical Paradox Cinema | Impossible event photographed as believable physical reality |
| CIS-03 | Urban Voltage Framing | Confrontational urban color, perspective, and social geometry |
| CIS-04 | Precision Storybook Geometry | Axial symmetry, curated palette, theatrical/diorama order |
| CIS-05 | Social Dread Realism | Ordinary reality containing spatial/social threat |
| CIS-06 | Pulp Deep-Frame Cinema | Widescreen ensemble staging and bold genre punctuation |
| CIS-07 | Radiant Interiorism | Intimate luminous portraiture and emotional camera attachment |
| CIS-08 | Chromatic Gothic Humanism | Tactile gothic worlds and emotionally coded color |
| CIS-09 | Intimate Epic Realism | Human proximity retained inside cultural/epic scale |
| CIS-10 | Luminous Isolation | Quiet beauty, negative space, private melancholy |
| CIS-11 | Tactile Severity | Patient formal rigor and bodily/material pressure |
| CIS-12 | Living Memory Naturalism | Warm relational memory with natural light and grain |
| CIS-13 | Embodied Light Realism | Character state expressed through light, darkness, and texture |
| CIS-14 | Domestic Uncanny Noir | Ordinary domestic surface opening into spatial darkness |
| CIS-15 | Street Pulse Cinema | Kinetic urban authenticity and mixed practical color |
| CIS-16 | Somatic Spiral | Body-bound subjective obsession and escalating texture |
| CIS-17 | Composed Heritage Radiance | Classical period power encoded by color and placement |
| CIS-18 | Neon Memory Drift | Emotional time, urban intimacy, reflection, and motion smear |
| CIS-19 | Pressure-Point Realism | Grounded action moving from objective to subjective pressure |
| CIS-20 | Elastic Absurdist Optics | Extreme optics, deadpan bodies, and distorted social space |
| CIS-21 | Neighborhood Witness Realism | Community geography as moral/social information |
| CIS-22 | Social Geometry Engine | Architecture and blocking as hierarchy diagram |
| CIS-23 | Gulf Gothic Reverie | Southern family realism drifting into memory/supernatural |
| CIS-24 | Monolithic Atmosphere | Human fragility inside monumental environment and weather |
| CIS-25 | Griot Social Clarity | Clear everyday social staging and culturally grounded symbols |
| CIS-26 | Pop Chiaroscuro Melodrama | Object-level saturated color with readable deep interiors |
| CIS-27 | Liberation Collage | Guerrilla realism fractured by analog psychedelic montage |
| CIS-28 | Wandering Cinecriture | Observational visual essay with playful formal intervention |
| CIS-29 | Archive-Truth Remix | Mixed media, direct address, and invented/real archive |
| CIS-30 | Raw Sublime Friction | Reactive human roughness versus painterly iconic tableau |
| CIS-31 | Sovereign Angle Cinema | Camera angle as decolonial power and historical memory |
| CIS-32 | Forensic Noir Precision | Exact dark realism, procedural detail, controlled movement |
| CIS-33 | Everyday Poetic Witness | Patient community observation and unforced lyric detail |
| CIS-34 | Operational Immersion | Embedded procedural realism and reactive event coverage |
| CIS-35 | Invitational Distance | Spacious humanist witness without visual possession |
| CIS-36 | Suburban Dream Breach | Credible ordinary space whose rules become unreliable |
| CIS-37 | Tidal Haunt Realism | Coastal social reality drifting seamlessly into haunting |
| CIS-38 | Ornate Gaze Mechanics | Architecture, reflection, sensual detail, and gaze systems |
| CIS-39 | Ancestral Tide Lyrism | Luminous Black feminine ancestry, landscape, and layered time |
| CIS-40 | Storybook Expressionist Gothic | Theatrical shape language and outsider-centered gothic worlds |
| CIS-41 | Sahel Surreal Montage | Material street reality fractured by symbolic montage |
| CIS-42 | Elastic Real-Time Immersion | Continuous spatial event with deep environmental choreography |
| CIS-43 | Dignified Human Focus | Restrained institutions versus vibrant human/community life |
| CIS-44 | Atmospheric Worldforge | Dense production design fused with directional atmosphere |
| CIS-45 | Chadian Luminous Minimalism | Spare painterly frames, local color, deep night, symbolic objects |
| CIS-46 | Sensual Landscape Interiorism | Inner life expressed through landscape and tactile detail |
| CIS-47 | Historic Counter-Montage | History argued through materially distinct records of time |
| CIS-48 | Fragmented Sensory Memory | Emotion reconstructed from charged visual fragments |
| CIS-49 | Equatorial Civic Witness | Community/social realism rooted in place, weather, and local POV |
| CIS-50 | Psychological Face Chamber | Face-centered psychological minimalism and symbolic light |

---

# GLOBAL AGENT INSTRUCTIONS

**Mandatory runtime order:** Select style -> run Style Compiler -> generate -> run Style Fidelity Gate -> repair only failed dimensions if needed.

## A. Never reduce a style to its palette
Color is only one variable. The selected system must affect at least **six** of the following nine dimensions:
1. camera position
2. composition
3. lens/spatial behavior
4. depth of field
5. lighting logic
6. color architecture
7. material/texture treatment
8. environment/production design
9. character direction / implied movement

If only color changes, the style has not been applied.

## B. Preserve the user's subject before applying style
The requested subject, identity, clothing, action, required object, and setting constraints take priority. The style system should change **how the scene is photographed and designed**, not silently replace the requested content.

## C. Distinguish persistent grammar from famous-film imitation
Do not recreate a copyrighted frame, recognizable character, signature costume, or exact set unless separately requested and allowed. Use the underlying grammar to build a new image around the user's own subject.

## D. Do not stack unrelated style systems by default
One style system should be dominant. If two are deliberately combined, identify:
- **Primary system:** controls camera/composition/lighting.
- **Secondary system:** may contribute only 1-3 specified traits.

Do not average two systems into generic 'cinematic' imagery.

## E. Contrast architecture
Every strong image should contain at least one meaningful tension appropriate to the selected system. Examples:
- person / institution
- intimacy / scale
- ordinary photograph / impossible event
- beauty / isolation
- social order / visual distortion
- daylight normality / hidden threat
- bodily closeness / environmental pressure
- stillness / implied motion
- historical evidence / contemporary space
- community / external authority

Contrast must arise from story and composition, not merely from increasing the contrast slider.

## F. Material-first rule
Whenever possible, produce color and atmosphere through **things in the scene** — wardrobe, walls, weather, practical lights, landscape, furniture, vehicles, food, signage, skin, fabric, metal, water — before relying on a global post-processing look.

## G. Physical-source lighting rule
Unless the selected system explicitly calls for theatrical or psychologically impossible light, every dominant light should have a plausible source in the world.

## H. Image-specificity checklist
Before generation, the agent should be able to answer:
- Where is the camera physically located?
- How far is it from the subject?
- What is the lens doing to space?
- What remains readable in the background?
- What is the dominant source of light?
- Which colors belong to actual objects or surfaces?
- What is the strongest environmental material?
- What emotional relationship organizes the subjects?
- What is the one visual tension that makes this image belong to the selected system?

If these answers are vague, expand the prompt before generation.

---

# RESEARCH METHODOLOGY AND CONFIDENCE NOTES

## Version 2 traceability upgrade
Every profile now carries an evidence-class tag and a traceability-confidence label. These labels rate the **evidence trail in this manual**, not the artistic importance of the filmmaker. The purpose is to stop an agent from treating a critical observation as though it were a documented technical specification. [TECH-1] and [INST-2] claims may support more precise operational rules; [FRAME-3] and [CRIT-4] claims should be translated into visible image behavior without inventing unsupported equipment details.


This document was built from a combination of:

1. cinematographer/director interviews and first-person production commentary;
2. *American Cinematographer*, Kodak, BFI, Criterion, Filmmaker Magazine, DGA, and other film-institution/production sources;
3. representative-frame comparison across multiple films rather than a single famous title;
4. critical sources used to identify recurring visual structures when direct technical interviews were unavailable;
5. conservative synthesis for filmmakers with thinner English-language technical documentation.

The document intentionally avoids inventing exact focal lengths, film stocks, lighting diagrams, or camera packages where the research did not support them. A style profile can still be operationally useful by accurately specifying spatial behavior, lighting logic, palette construction, material treatment, point of view, and composition without pretending to know unsupported technical details.

## Particularly strong first-person/technical research bases
The technical evidence is especially strong for the systems derived from Christopher Nolan, Wes Anderson, Jordan Peele, Quentin Tarantino, Barry Jenkins, Guillermo del Toro, Ryan Coogler, Sofia Coppola, Dee Rees, Darren Aronofsky, Wong Kar-wai, Yorgos Lanthimos, Denis Villeneuve, David Fincher, Kathryn Bigelow, Alfonso Cuaron, Ridley Scott, and Ingmar Bergman/Sven Nykvist, because substantial cinematographer/director interviews and institutional analysis are available.

## Conservative-evidence profiles
For Bassek ba Kobhio and several filmmakers whose technical production coverage is less extensively archived in English, the operational systems rely more heavily on representative films, interviews about artistic priorities, festival/archive records, and reputable critical description. Those profiles are intentionally less specific about camera packages or exact lens choices and more specific about observable composition, environment, social point of view, and material behavior.

---

# SOURCE FAMILY / RESEARCH ANCHOR INDEX

The following source families were used repeatedly because they provide higher-value information than generic style summaries:

- **American Cinematographer / ASC** — cinematographer interviews, production breakdowns, lens/lighting/camera strategy.
- **Kodak Motion Picture** — photochemical workflow, film-stock and cinematography interviews.
- **BFI** — filmmaker retrospectives, close visual analysis, historical context.
- **Criterion Collection** — filmmaker-approved editions, visual essays, restoration notes, scholarly/critical analysis.
- **Filmmaker Magazine** — director/cinematographer interviews and production discussions.
- **Directors Guild of America (DGA)** — director craft discussion, including signature camera devices and staging.
- **Cannes / Cinematheque / Africultures / Images Francophones / California Newsreel** — film records, interviews, and African-cinema archival context used particularly for under-documented filmmakers.
- **Director and cinematographer first-person interviews** — prioritized whenever available.

### Named technical/critical anchors represented in the research
- *American Cinematographer*: *Inception*, *Moonrise Kingdom*, *Get Out*, *Black Panther*, *Se7en*, *Fight Club*, *Arrival*, *Blade Runner 2049*, *Children of Men*, *Alien*, *Blade Runner*, *Gladiator*, *Requiem for a Dream*, *Decision to Leave* and related production coverage.
- Kodak Motion Picture: *Oppenheimer*, *Nope*, *The Beguiled*, *Little Women*, *The Favourite*, *The French Dispatch*, *Asteroid City*, *Once Upon a Time in Hollywood* and related cinematography interviews.
- BFI / Criterion: visual analysis of *Moonlight*, *Do the Right Thing*, *Chungking Express*, *In the Mood for Love*, *Pariah*, *Blue Velvet*, *Boyz n the Hood*, *Black Girl*, *Cleo from 5 to 7*, *The Watermelon Woman*, *Killer of Sheep*, *Daughters of the Dust*, *Touki Bouki*, *Persona*, *Cries and Whispers*, *Ratcatcher*, *I Am Not Your Negro* and related filmmaker studies.
- Filmmaker Magazine: *Middle of Nowhere*, *Hunger*, *Lady Bird*, *Mudbound*, *Black Swan*, *Lost in Translation*, *Melancholia*, *Till* and related interviews.

---


# VERSION 2 PRODUCTION-READINESS CHECK

The following weaknesses identified in the Version 1 self-audit have been corrected:

- **Arbitrary-subject adaptation:** upgraded with a mandatory Style Compiler in every one of the 50 profiles.
- **Automated style-fidelity QC:** upgraded with an eight-dimension post-generation scoring gate and bounded repair loop.
- **Research traceability:** upgraded with evidence-class tags, profile-level confidence labels, and an explicit rule separating supported technical claims from visual synthesis.
- **Prompt drift:** reduced by five non-negotiable visual anchors per style, a four-of-five visibility requirement, subject locks, and profile-specific anti-drift filters.
- **Endless correction risk:** bounded to two automatic repair cycles while preserving dimensions that already pass.

## Production target
The runtime goal is **>=8.0/10 fidelity**, with subject preservation >=9.0 and signature fidelity >=8.0. Passing is based on the generated image, not merely on whether the prompt contains style vocabulary.


# END OF MASTER DOCUMENT

**Operational reminder:** The name-independent system label and AI Deployment Block are the generation-facing components. The Research Lineage and Research Anchors exist for human audit, revision, and future expansion of the style library.
