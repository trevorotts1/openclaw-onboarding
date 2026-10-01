# BlackCEO Famous Photographers DNA Style Library
## AI-Facing Photographic Style Systems

**Library identity:** A BlackCEO research-to-execution system for converting famous-photographer visual DNA into name-free, production-ready photographic style instructions.

**Version:** 1.1  
**Purpose:** Convert historically recognizable photographic and portrait-making approaches into original, name-free visual instruction systems that an AI agent can execute consistently.

---

## 0. MASTER OPERATING RULE

This document has two layers:

1. **HUMAN-ONLY RESEARCH LAYER** — identifies the source photographer/artist used for study and records the research basis.
2. **AI-FACING EXECUTION LAYER** — contains the new branded style name and the actual visual rules to pass to an image-generation agent.

### NON-NEGOTIABLE DOWNSTREAM RULE

**DO NOT PASS THE HUMAN SOURCE NAME, PHOTOGRAPHER NAME, ARTIST NAME, OR SOURCE-MAPPING FIELD TO AN IMAGE GENERATOR.**

The original name exists only for internal provenance and research traceability. The image agent should receive the **new branded style name plus the descriptive execution rules**.

Do not use:
- “in the style of [source name]”
- “shot by [source name]”
- “inspired by [source name]”
- “like [source name]”
- any source photographer or artist name from the human-only mapping

Instead, translate the selected style into its concrete visual grammar: composition, camera relationship, lens behavior, light, color, texture, set/environment, gesture, wardrobe, emotional register, timing, and finish.

---

## 1. AGENT EXECUTION PROTOCOL

When an agent uses this library:

1. **Identify the requested style ID or branded style name.**
2. Read the entire style block before generating a prompt.
3. Preserve the user’s factual subject requirements first: identity, age, clothing, action, object, setting, orientation, aspect ratio, and any explicit color requirements.
4. Apply the selected style as a **visual system**, not as a one-word adjective.
5. Translate the style into visible decisions:
   - subject treatment
   - composition
   - viewpoint
   - lens/perspective
   - depth of field
   - lighting
   - color or monochrome behavior
   - environment/set design
   - wardrobe/styling
   - texture/materiality
   - motion/timing
   - emotional tone
   - print/digital finish
6. Do not blend multiple library styles unless the user explicitly asks for a hybrid.
7. If a user instruction conflicts with a historical trait, obey the user’s explicit instruction while preserving the remaining style grammar.
8. Never rely on the branded name alone. The branded name is an internal shortcut; the **descriptive rules carry the style**.
9. Avoid generic filler such as “cinematic,” “editorial,” “luxury,” or “dramatic” unless the style block explains exactly how that quality is produced.
10. Before finalizing a prompt, run the **Style Fidelity Check** below.

### STYLE FIDELITY CHECK

A prompt is not finished until the agent can answer all of these:

- What makes the composition distinctive?
- What is the camera’s relationship to the subject?
- What kind of light creates the look?
- What is the tonal/color logic?
- How should skin, fabric, objects, and surfaces render?
- What role does the environment play?
- How should the subject pose or move?
- What emotional temperature should the frame carry?
- What should the final image avoid?
- Could the prompt still create the intended visual language if the branded style name were deleted?

If the answer to the last question is **no**, the prompt is under-specified.


### STYLE LOCK PROTOCOL — MANDATORY FOR ALL GENERATIONS

Every style block contains descriptive traits. Before generating, the agent must convert those traits into **five hard locks**:

1. **Composition lock** — the frame geometry that must survive.
2. **Camera lock** — viewpoint, focal-length behavior, distance, and depth behavior.
3. **Light lock** — source direction, hardness, contrast, and falloff.
4. **Palette / tonal lock** — the dominant color or grayscale behavior.
5. **Behavior lock** — how the subject must pose, move, look, or interact.

The agent must treat these five locks as higher priority than decorative adjectives.

### MODEL-DRIFT REPAIR LOOP

After the first generation, evaluate only visible output:

- If the image could plausibly belong to several unrelated styles in this library, **the style is under-specified**.
- If the image looks like generic commercial photography, strengthen camera, light, composition, and subject-behavior locks.
- If the correct subject appears but the visual language is weak, preserve the subject exactly and rewrite only the style controls.
- If the lighting is wrong, do not compensate with color grading; fix the light source and contrast architecture.
- If the composition is wrong, do not add more adjectives; explicitly move the camera, subject, and major frame anchors.
- If the palette is wrong, specify dominant colors, saturation ceiling, and what must remain neutral.
- If the image is technically polished but emotionally wrong, change gaze, gesture, body tension, interpersonal spacing, and camera proximity.
- Repeat until at least **4 of the 5 style locks are visibly dominant**.

### TECHNICAL SPECIFICATION RULE

Whenever the style permits it, convert vague instructions into approximate photographic behavior:

- **24–35mm equivalent:** environmental, spatial, immersive, slight perspective emphasis.
- **40–58mm equivalent:** natural human perspective, documentary intimacy.
- **70–105mm equivalent:** controlled portrait compression, reduced background expansion.
- **Deep focus:** f/8–f/16 behavior or equivalent scene clarity.
- **Moderate focus:** f/4–f/8 behavior.
- **Shallow focus:** f/1.8–f/3.5 behavior, only when the style explicitly benefits.
- Do not use fake EXIF numbers as decoration. Technical values exist only to force visible optical behavior.


---

## 2. HUMAN-ONLY SOURCE MAP

> **Do not pass this table downstream. It is provenance only.**

| ID | Human research source | New branded style |
|---|---|---|
| VDL-001 | Gordon Parks | **Witnessed Dignity** |
| VDL-002 | Carrie Mae Weems | **Table of Memory** |
| VDL-003 | Helmut Newton | **Power After Dark** |
| VDL-004 | Lorna Simpson | **Fragmented Evidence** |
| VDL-005 | Richard Avedon | **White Field Intensity** |
| VDL-006 | Malick Sidibé | **Electric Social** |
| VDL-007 | Diane Arbus | **Unvarnished Encounter** |
| VDL-008 | James Van Der Zee | **Ceremonial Grandeur** |
| VDL-009 | Cindy Sherman | **Fictional Identity** |
| VDL-010 | Roy DeCarava | **Shadow Poetics** |
| VDL-011 | Irving Penn | **Essential Studio** |
| VDL-012 | Seydou Keïta | **Patterned Prestige** |
| VDL-013 | Nan Goldin | **Intimate Diary** |
| VDL-014 | Dawoud Bey | **Collaborative Presence** |
| VDL-015 | Herb Ritts | **Sun-Sculpted Form** |
| VDL-016 | Zanele Muholi | **Confronting Presence** |
| VDL-017 | Robert Mapplethorpe | **Classical Precision** |
| VDL-018 | Rotimi Fani-Kayode | **Ritual Desire** |
| VDL-019 | Ansel Adams | **Monumental Tonality** |
| VDL-020 | Lola Flash | **Chromatic Inversion** |
| VDL-021 | Sebastião Salgado | **Epic Human Terrain** |
| VDL-022 | Renée Cox | **Iconic Defiance** |
| VDL-023 | Mario Testino | **Intimate Glamour** |
| VDL-024 | Aïda Muluneh | **Primary Symbolism** |
| VDL-025 | Steve McCurry | **Human Color** |
| VDL-026 | Mickalene Thomas | **Ornate Sovereignty** |
| VDL-027 | Weegee | **Midnight Flash** |
| VDL-028 | Deana Lawson | **Constructed Kinship** |
| VDL-029 | Sally Mann | **Haunted Collodion** |
| VDL-030 | Tyler Mitchell | **Pastoral Freedom** |
| VDL-031 | Dorothea Lange | **Human Evidence** |
| VDL-032 | Kwame Brathwaite | **Beautiful Pride** |
| VDL-033 | David LaChapelle | **Pop Revelation** |
| VDL-034 | Jamel Shabazz | **Street Ceremony** |
| VDL-035 | Peter Lindbergh | **Raw Elegance** |
| VDL-036 | Lyle Ashton Harris | **Archive of Self** |
| VDL-037 | Henri Cartier-Bresson | **Geometric Instinct** |
| VDL-038 | Nona Faustine | **Site of Memory** |
| VDL-039 | Andreas Gursky | **System Panorama** |
| VDL-040 | Nadine Ijewere | **Dreamed Identity** |
| VDL-041 | Ellen von Unwerth | **Playful Provocation** |
| VDL-042 | Kehinde Wiley | **Regal Pattern Sovereignty** |
| VDL-043 | Martin Parr | **Hyperreal Satire** |
| VDL-044 | Awol Erizku | **Pop Icon Recode** |
| VDL-045 | Steven Meisel | **Editorial Metamorphosis** |
| VDL-046 | LaToya Ruby Frazier | **Intimate Industry** |
| VDL-047 | Tim Walker | **Crafted Wonder** |
| VDL-048 | Mikael Owunna | **Cosmic Body** |
| VDL-049 | Viviane Sassen | **Shadow Abstraction** |

---

# 3. STYLE LIBRARY

## VDL-001 — WITNESSED DIGNITY

### HUMAN-ONLY RESEARCH LAYER
**Source studied:** Gordon Parks  
**Research basis:** Gordon Parks Foundation — *Portraits, 1947–63*  
https://www.gordonparksfoundation.org/gordon-parks/photography-archive/portraits-1947-63/features

### RESEARCH SYNTHESIS
The defining mechanism is not merely “documentary photography.” The work repeatedly joins social observation with portrait-level attention to character. People are shown inside worlds that communicate class, work, neighborhood, aspiration, pressure, family, or community. The camera can be intimate without becoming voyeuristic. A subject may look directly toward the lens, but the image still feels lived rather than cosmetically staged. Light and framing are deliberate even when the moment appears natural. Black-and-white work depends heavily on meaningful shadow, substantial midtones, luminous skin, and environmental depth; color work retains a documentary base rather than becoming slick advertising color.

### AI-FACING EXECUTION LAYER

**Core intent:** Create an intimate environmental photograph in which a person retains full dignity and psychological presence while the surrounding world quietly explains something about their life.

**Subject treatment**
- Treat the subject as a person with agency, not as an example of a social condition.
- Favor self-possession, restrained expression, thoughtful eye contact, and natural gesture.
- Allow pride, uncertainty, weariness, resolve, tenderness, or ambiguity without exaggerating emotion.
- Avoid glamour posing unless elegance is organically part of the subject’s world.

**Composition**
- Use medium, three-quarter, full-body environmental, or intimate portrait framing.
- Let doors, windows, walls, sidewalks, furniture, signage, work tools, or household objects create context.
- Build clear foreground / subject / background relationships.
- Use asymmetry when it strengthens narrative reality.
- Keep the frame intentional but never over-designed.

**Camera / lens behavior**
- Human eye-level perspective is the default.
- Favor natural perspective over extreme wide-angle distortion or compressed telephoto spectacle.
- Keep enough environmental information in focus to support the story.
- Move close enough to create human connection without creating invasive visual pressure.

**Lighting**
- Favor window light, open shade, directional daylight, practical interior light, or restrained supplemental light.
- Preserve dimensional shadow across the face.
- Do not flatten skin with beauty lighting.
- Let darkness remain dark when it adds emotional or environmental meaning.

**Tonal / color logic**
- Monochrome: deep blacks, rich midtones, luminous but controlled highlights, restrained analog grain, silver-gelatin weight.
- Color: believable skin, restrained saturation, earthy neutrals, aged architecture, muted environmental color, occasional strong localized color.
- Avoid HDR, neon-everywhere grading, or glossy commercial skin.

**Environment / styling**
- Use real-feeling homes, porches, workplaces, streets, neighborhoods, community spaces, backstage areas, or public environments.
- Wardrobe should look owned and lived in: ordinary, occupational, elegant, culturally specific, or period-specific as appropriate.
- Preserve wrinkles, fabric weave, painted walls, pavement, wood, dust, age, and wear.

**Mandatory signature locks**
- **Composition:** subject must remain embedded in a legible lived environment; never reduce to a generic blurred-background portrait.
- **Camera:** natural 40–58mm-equivalent perspective, eye-level by default, camera close enough for relationship but far enough to retain contextual objects.
- **Light:** one believable dominant source, usually window/open shade/daylight, with dimensional shadow preserved.
- **Tone:** monochrome must carry deep blacks + substantial midtones; color must remain restrained and skin-faithful.
- **Behavior:** restrained, self-possessed expression and natural gesture; never influencer performance.

**Technical recipe**
- 40–58mm equivalent for most portraits; 35mm only when the environment must become more present.
- Moderate depth of field: roughly f/4–f/8 behavior.
- Place the brightest meaningful highlight on face/hands or a narratively important object, not randomly in the background.
- Keep at least 2–4 readable environmental clues in frame.
- If the first result looks like generic editorial portraiture, widen context, reduce beauty retouching, deepen shadow, and restore lived environmental detail.


**Emotional register**
Quietly observant. Human. Socially aware. Intimate. Unresolved. Respectful.

**Avoid**
- poverty-as-spectacle
- exaggerated misery
- influencer poses
- featureless studio backgrounds when context matters
- hyper-retouched skin
- decorative clutter with no story function
- melodramatic “cinematic” grading

> **AI production directive:** Create a psychologically present environmental photograph centered on human dignity and lived reality. Place the subject inside a meaningful real-world environment whose architecture, objects, clothing, and surfaces reveal circumstance without explaining everything. Use natural or naturalistic directional light, dimensional shadows, honest skin and material texture, a believable human camera height, and deliberate composition that still feels observed rather than manufactured. Favor restrained expression, meaningful gaze, and gestures that feel caught inside an ongoing life. Preserve contextual detail without clutter. The frame should feel like one consequential moment extracted from a larger story that began before the shutter and continues afterward.

---

## VDL-002 — TABLE OF MEMORY

### HUMAN-ONLY RESEARCH LAYER
**Source studied:** Carrie Mae Weems  
**Research basis:** Carrie Mae Weems Studio — *Kitchen Table Series* and photographic work  
https://www.carriemaeweems.net/kitchentable  
https://www.carriemaeweems.net/photographic-work

### RESEARCH SYNTHESIS
A central mechanism is the conversion of an ordinary domestic stage into a controlled theater of identity, intimacy, power, gender, history, and social expectation. In the best-known table-centered work, repetition is crucial: the same basic location and table become a stable architecture while relationships, gestures, props, clothing, and emotional temperature change. The images are staged, but the staging is emotionally legible rather than glossy. Text and image may operate together, and personal experience is expanded into broader social questions.

### AI-FACING EXECUTION LAYER

**Core intent:** Turn an ordinary domestic location into a symbolic stage where relationships, identity, memory, and power can be read through gesture and arrangement.

**Composition**
- Establish one recurring architectural anchor: a table, lamp, doorway, chair, bed, or other simple domestic structure.
- Build frontal or near-frontal tableaux with strong left-right relational geometry.
- Repetition is valuable: keep the core location stable while changing people, props, or emotional conditions.
- Use negative space and object placement deliberately.
- Let hands, seated posture, leaning distance, and body orientation communicate relationship dynamics.

**Lighting**
- Use one dominant practical or practical-feeling source: hanging lamp, table lamp, window, or tight overhead pool.
- Create a contained island of visibility surrounded by deeper shadow.
- Keep the light theatrical enough to shape meaning but believable enough to remain domestic.

**Color / monochrome**
- Monochrome is especially effective: controlled grayscale, strong blacks, clear skin separation, smooth midtones.
- If color is used, keep the palette restrained and symbolically organized rather than decorative.

**Subject direction**
- Expressions should be emotionally contained.
- Direct gaze may create confrontation; averted gaze may signal distance, reflection, or hierarchy.
- Avoid broad performance. Small gestures should carry large meaning.
- Use pairs, trios, family configurations, or solitary figures to explore relationship structure.

**Props / wardrobe**
- Props should function symbolically: mirror, cards, cigarettes, books, food, phone, glassware, photographs, flowers, clothing changes.
- Never add objects simply to fill the frame.
- Wardrobe can mark changing roles, intimacy, formality, independence, or time.

**Text integration**
- If the project uses text, make it conceptually additive rather than descriptive.
- Text may complicate the image, introduce another voice, or create tension between what is seen and what is said.

**Mandatory signature locks**
- **Composition:** one recurring domestic anchor must structure the frame—table, lamp, chair, doorway, or equivalent.
- **Camera:** frontal or near-frontal, stable, restrained perspective; avoid roaming cinematic coverage.
- **Light:** a contained practical-feeling pool of light with surrounding shadow.
- **Tone:** mostly monochrome or tightly restrained color.
- **Behavior:** small gestures and interpersonal spacing must carry the drama; avoid broad acting.

**Technical recipe**
- 45–65mm-equivalent perspective.
- Moderate-to-deep focus: f/5.6–f/11 behavior so people, table, props, and relational geometry remain readable.
- Camera height near seated eye level for table scenes.
- Keep the practical light source or its believable effect visible.
- If the result becomes generic domestic lifestyle photography, reduce smiles, simplify props, frontalize the geometry, and increase relational tension through spacing and gaze.


**Emotional register**
Intimate, intelligent, self-aware, theatrical, psychologically restrained, socially resonant.

**Avoid**
- generic “family lifestyle” imagery
- smiling stock-photo interaction
- uncontrolled clutter
- decorative props with no conceptual role
- over-cinematic lighting unrelated to the domestic architecture

> **AI production directive:** Build a controlled domestic tableau around a simple recurring architectural anchor such as a table, lamp, doorway, or chair. Treat the location as a stage for intimacy, identity, memory, and power. Use contained directional light, deliberate relational spacing, restrained facial expression, and small gestures that carry psychological meaning. Keep props sparse and symbolic. Favor frontal or near-frontal structure, meaningful negative space, and an atmosphere in which ordinary domestic behavior feels both personal and archetypal. The scene should appear intentionally staged but emotionally credible, as though one room is holding an entire relationship history.

---

## VDL-003 — POWER AFTER DARK

### HUMAN-ONLY RESEARCH LAYER
**Source studied:** Helmut Newton  
**Research basis:** Helmut Newton Foundation — *A Gun for Hire* / fashion commissions  
https://newton-foundation.org/en/ausstellungen/helmut-newton-a-gun-for-hire/

### RESEARCH SYNTHESIS
The recurring visual engine is power rather than simple glamour: assertive fashion subjects occupy streets, hotel rooms, architectural interiors, poolsides, public spaces, and nocturnal environments with a self-aware command of the frame. The imagery often combines polished fashion with tension, voyeuristic suggestion, cinematic ambiguity, hard or dusk-like light, and a cool emotional distance. Subjects frequently appear as protagonists who control their own physical presence rather than passive mannequins.

### AI-FACING EXECUTION LAYER

**Core intent:** Create a fashion photograph in which the subject controls the scene through posture, scale, confidence, and psychological distance.

**Subject direction**
- Use elongated, assertive poses and decisive body lines.
- The subject should look self-possessed, cool, and difficult to dominate visually.
- Expressions can be aloof, knowing, challenging, or unreadable.
- Avoid timid or overly cute posing.

**Composition**
- Favor full-body or three-quarter fashion framing.
- Use strong architectural lines: corridors, hotel rooms, balconies, streets, parking structures, polished interiors, poolsides.
- Let the environment suggest a larger story without resolving it.
- Create tension with mirrors, doorways, off-frame implication, distant secondary figures, or empty architectural space.
- Keep geometry clean and graphic.

**Camera / perspective**
- Modest low angles can amplify stature.
- Use normal-to-short-telephoto perspective for elegant body proportions.
- Keep the image observational enough to feel like a charged event rather than a catalog pose.

**Lighting**
- Favor hard daylight, direct flash, dusk, night practicals, controlled tungsten, or crisp directional sources.
- Allow bold highlights and decisive shadows.
- Do not soften every surface.
- At night, let pools of artificial light create mystery rather than lifting the entire scene.

**Color / monochrome**
- Black and white: crisp, graphic, high-contrast, polished but not muddy.
- Color: restrained luxury palette, cool neutrals, skin against architectural surfaces, occasional saturated accent.
- Avoid trendy teal-orange grading.

**Wardrobe / set**
- Strong tailoring, eveningwear, sharp silhouettes, hosiery, coats, formal shoes, architectural garments.
- Set design should imply luxury, privacy, travel, or metropolitan life without becoming ornate for its own sake.
- Accessories should sharpen character.

**Mandatory signature locks**
- **Composition:** elongated full-body or three-quarter figure against strong metropolitan or luxury architecture.
- **Camera:** neutral-to-modest low angle, 50–90mm-equivalent portrait behavior.
- **Light:** hard daylight, crisp flash, dusk, or selective night practicals—never soft romantic haze.
- **Tone:** polished but cool; graphic blacks/whites or restrained luxury color.
- **Behavior:** subject must project control, stature, and psychological distance.

**Technical recipe**
- 50–85mm equivalent for full-body architecture; 85–105mm for tighter commanding portraits.
- f/4–f/8 behavior; retain architectural structure.
- Hard key 30–60° off camera or direct flash depending scene.
- Keep verticals disciplined and body lines long.
- If the image becomes ordinary glamour, lower the camera slightly, harden the light, simplify the palette, and replace friendly expression with cool self-possession.


**Emotional register**
Controlled, powerful, erotic without softness, cinematic, psychologically cool, slightly dangerous, self-aware.

**Avoid**
- submissive body language
- romantic haze
- soft bohemian styling
- cheerful commercial beauty expressions
- cluttered backgrounds
- excessive digital fantasy

> **AI production directive:** Construct a sophisticated fashion scene built around power, stature, and psychological control. Place the subject inside strong metropolitan or luxury architecture and direct them into elongated, self-possessed poses with cool, unreadable confidence. Use crisp directional light, hard daylight, flash, dusk, or selective night illumination to create graphic separation and tension. Favor clean geometry, full-body presence, polished surfaces, and a suggestion that something happened immediately before or after the frame. Keep glamour sharp rather than soft, sensuality self-directed rather than passive, and the narrative unresolved.

---

## VDL-004 — FRAGMENTED EVIDENCE

### HUMAN-ONLY RESEARCH LAYER
**Source studied:** Lorna Simpson  
**Research basis:** Museum of Modern Art — artist collection and text/image works  
https://www.moma.org/artists/6602

### RESEARCH SYNTHESIS
The key mechanism is withholding. Identity is not presented as a complete portrait to be consumed. Bodies can be cropped, turned away, repeated, partially hidden, or paired with language that destabilizes what the viewer thinks they know. Neutral presentation, controlled studio conditions, fragments, seriality, and text create conceptual pressure around race, gender, classification, memory, and the limits of seeing.

### AI-FACING EXECUTION LAYER

**Core intent:** Make the viewer work with incomplete visual evidence. Treat concealment, cropping, repetition, and language as active compositional devices.

**Subject treatment**
- Do not automatically show a full recognizable face.
- Consider back-of-head views, cropped torso, hands, mouth, hair, clothing, shoulders, or repeated partial views.
- Keep posture controlled and emotionally neutral.
- The subject should not perform for approval.

**Composition**
- Favor frontal studio organization, serial grids, diptychs, repeated poses, or isolated fragments.
- Use generous neutral space.
- Crops should feel intentional and conceptual, never accidental.
- Repetition should create comparison and uncertainty.

**Lighting**
- Controlled, even or softly directional studio light.
- Avoid theatrical rim light or beauty-glamour effects.
- Maintain enough tonal clarity that form and clothing read precisely.

**Background / palette**
- Neutral gray, warm neutral, white, black, or subdued field.
- Restrained color unless a specific hue carries conceptual meaning.
- B&W works well when the purpose is analytic rather than nostalgic.

**Text**
- Optional short phrases can function as a second evidence layer.
- Text should introduce ambiguity, memory, categorization, contradiction, or another point of view.
- Do not caption the obvious content of the image.
- Keep typography plain and conceptually disciplined.

**Wardrobe / objects**
- Minimal, non-distracting clothing.
- Hair, clothing, and body fragments may themselves become identity markers.
- Use objects sparingly and only when they complicate interpretation.

**Mandatory signature locks**
- **Composition:** partial identity, seriality, cropping, turning away, or repetition must be central.
- **Camera:** neutral studio perspective with little optical drama.
- **Light:** even or softly directional studio light.
- **Tone:** restrained neutral field; color only when conceptually necessary.
- **Behavior:** emotionally controlled, withholding, non-performative.

**Technical recipe**
- 50–85mm-equivalent neutral perspective.
- f/5.6–f/11 behavior for exact edges and repeated fragments.
- Plain gray/white/black/warm-neutral background.
- Use one deliberate crop rule: remove face, isolate torso/hands/hair, or repeat the same partial view.
- If the image reads as a normal portrait, hide more identity, simplify the field, and introduce disciplined repetition or text-image tension.


**Emotional register**
Cool, withholding, intelligent, ambiguous, forensic without being clinical, socially charged.

**Avoid**
- conventional smiling portraiture
- over-explained symbolism
- busy set design
- glamour retouching
- narrative closure
- decorative typography

> **AI production directive:** Create a restrained conceptual portrait system built from incomplete evidence. Withhold conventional facial access through cropping, turning away, repetition, or fragmentation. Use controlled studio light, neutral spatial fields, precise body placement, and generous negative space. If text is included, make it complicate the image rather than explain it. Allow hair, clothing, gesture, and isolated body details to carry identity information while refusing a complete visual answer. The final image should feel deliberate, quiet, unresolved, and intellectually charged.

---

## VDL-005 — WHITE FIELD INTENSITY

### HUMAN-ONLY RESEARCH LAYER
**Source studied:** Richard Avedon  
**Research basis:** The Metropolitan Museum of Art — *Richard Avedon: Portraits*  
https://www.metmuseum.org/exhibitions/listings/2002/richard-avedon

### RESEARCH SYNTHESIS
The signature portrait mechanism is radical subtraction. A bright seamless field removes social context so that face, posture, clothing, gesture, asymmetry, and psychological tension become unavoidable. Large-format practice encourages deliberate encounter and extreme detail. Lighting is often broad and clear rather than theatrically sculpted. The image can feel stark, revealing, confrontational, elegant, or vulnerable because there is nowhere else for the viewer to look.

### AI-FACING EXECUTION LAYER

**Core intent:** Remove the environment until the subject’s face, body, clothing, and gesture become the entire psychological event.

**Background**
- Use a seamless pure or near-white field.
- No furniture, scenery, props, decorative shadows, or environmental story unless essential.
- Keep the background visually continuous.

**Composition**
- Use centered or near-centered frontal portraiture, full-length figure studies, or tight crops.
- Allow awkward hand positions, asymmetry, stance, or clothing folds to become expressive.
- Leave enough white space to intensify isolation.
- Preserve edge discipline; an optional subtle dark film-edge impression may reinforce analog directness.

**Camera / lens**
- Simulate large-format clarity and deliberate camera placement.
- Favor normal perspective with minimal distortion.
- High micro-detail in face, hair, fabric, and hands.
- Use depth of field sufficient to keep the essential figure crisp.

**Lighting**
- Broad, bright, diffuse frontal or slightly directional light.
- Keep facial detail open and readable.
- Avoid dramatic rim lighting, colored gels, or moody low-key illumination.
- Shadows should be minimal and controlled rather than cinematic.

**Subject direction**
- Ask for direct gaze or a psychologically meaningful deviation from it.
- Encourage stillness and genuine physical idiosyncrasy.
- Expression may be neutral, tense, amused, tired, skeptical, vulnerable, or commanding.
- Do not force flattering symmetry.

**Finish**
- Monochrome: clean grayscale, detailed skin, strong but not crushed blacks, luminous white field.
- Color: restrained, exact, skin-faithful, no environmental color contamination.
- Retouch lightly; preserve pores, age, wrinkles, and individual physical character.

**Mandatory signature locks**
- **Composition:** seamless white field, subject isolated, no environment.
- **Camera:** frontal, deliberate, large-format-like clarity with natural proportions.
- **Light:** broad bright diffuse light with minimal theatrical shadow.
- **Tone:** luminous white field + highly detailed face/body/fabric.
- **Behavior:** stillness, idiosyncratic posture, psychologically direct presence.

**Technical recipe**
- 70–105mm-equivalent portrait perspective; 50–70mm for full-length.
- f/8–f/16 behavior or equivalent broad sharpness.
- Subject 1.5–3m from the white field to avoid hard cast shadows.
- Use a large frontal/45° soft source with minimal fill imbalance.
- If the result becomes a beauty campaign, reduce smoothing, allow asymmetry, flatten the set further, and intensify directness of gaze/posture.


**Emotional register**
Exposed, direct, elegant, unforgiving, psychologically immediate.

**Avoid**
- props
- elaborate backdrop texture
- shallow-focus fashion haze
- beauty retouching
- gratuitous drama
- fake environmental storytelling

> **AI production directive:** Isolate the subject against a seamless bright white field and make the person alone carry the image. Use broad clear light, normal perspective, large-format-like detail, minimal shadow, and precise rendering of skin, hair, hands, fabric, posture, and expression. Direct the subject toward stillness rather than performance. Preserve asymmetry and physical idiosyncrasy instead of correcting everything toward conventional beauty. The final portrait should feel stripped of distraction, psychologically immediate, and almost confrontational in its clarity.

---

## VDL-006 — ELECTRIC SOCIAL

### HUMAN-ONLY RESEARCH LAYER
**Source studied:** Malick Sidibé  
**Research basis:** Museum of Modern Art — artist collection; Studio Museum biography  
https://www.moma.org/artists/26555  
https://www.studiomuseum.org/artists/malick-sidib%C3%A9

### RESEARCH SYNTHESIS
The visual identity grows from social life: youth, music, dancing, friendship, nightlife, fashion, and the optimism of a changing urban culture. Party photographs feel immediate and kinetic, often using flash that freezes action. Studio portraits are more controlled but retain personality, rhythm, fashion, and playful bodily invention. Black-and-white presentation unifies exuberant gesture, patterned clothing, and social energy.

### AI-FACING EXECUTION LAYER

**Core intent:** Photograph social confidence, youth, music, style, friendship, and movement with directness and infectious energy.

**Scene modes**
1. **Party mode:** crowded social space, dancing, interaction, music, motion, direct flash.
2. **Studio mode:** simple patterned or graphic backdrop, full-body or three-quarter portrait, playful stance, strong fashion identity.

**Composition**
- Party mode can tolerate lively cropping and layered bodies.
- Keep the main subject readable even in a busy room.
- Studio mode should give the body room to perform: crossed legs, lean, hand gesture, dance-like stance, seated swagger.
- Favor human proximity over distant observation.

**Lighting**
- Party mode: straightforward flash that freezes people and separates them from darker interiors.
- Studio mode: clean, simple illumination with enough contrast to define clothing and face.
- Avoid glossy beauty-light complexity.

**Color / tone**
- Prefer energetic black and white with clear whites, solid blacks, and lively midtones.
- Add moderate grain and analog immediacy.
- If translating to color, retain period-natural saturation and avoid modern cinematic grading.

**Wardrobe**
- Make clothing important: suits, patterned shirts, dresses, sunglasses, jewelry, youth fashion, locally specific styling.
- Fashion should look personally chosen, not runway-imposed.

**Gesture / emotion**
- Encourage dancing, laughing, leaning, hand play, pair poses, social swagger, and spontaneous connection.
- Subjects should appear delighted by being seen.
- Avoid solemn museum-like stillness unless specifically required.

**Mandatory signature locks**
- **Composition:** social proximity and visible interaction; party or studio mode must be obvious.
- **Camera:** close human distance, 35–55mm-equivalent perspective.
- **Light:** direct flash for party mode; simple clean studio light for portrait mode.
- **Tone:** energetic black-and-white with clear whites and solid blacks.
- **Behavior:** dance, swagger, friendship, play, or visible enjoyment of being photographed.

**Technical recipe**
- Party: 35–45mm equivalent, f/5.6–f/11 behavior, direct flash, dark ambient room allowed to fall off.
- Studio: 50–65mm equivalent, f/8 behavior, full-body framing against graphic backdrop.
- Freeze gesture more than atmosphere; avoid cinematic motion blur.
- If the result feels solemn, add interpersonal interaction, dance-like stance, and more direct flash energy.


**Emotional register**
Youthful, communal, rhythmic, stylish, optimistic, immediate.

**Avoid**
- detached telephoto observation
- sterile minimalism in party scenes
- over-posed luxury fashion
- soft-focus nostalgia
- removing the social context

> **AI production directive:** Create a lively social photograph driven by music, friendship, fashion, and physical rhythm. Use close human proximity, direct readable framing, and either straightforward flash in a dark social space or simple studio light against a graphic backdrop. Let clothing, stance, hand gestures, dancing, and peer interaction carry personality. Favor energetic black-and-white tonality with analog immediacy. The image should feel participatory rather than observational: the people know the camera is there, enjoy its presence, and turn being photographed into part of the social event.

---

## VDL-007 — UNVARNISHED ENCOUNTER

### HUMAN-ONLY RESEARCH LAYER
**Source studied:** Diane Arbus  
**Research basis:** SFMOMA — *Diane Arbus: In the Beginning*; The Met — *Diane Arbus Revelations*  
https://www.sfmoma.org/exhibition/diane-arbus-beginning/  
https://www.metmuseum.org/exhibitions/diane-arbus-revelations

### RESEARCH SYNTHESIS
The distinctive mechanism is direct encounter rather than stolen observation. Square framing, frontal placement, centrality, eye contact, and a visible relationship between camera and subject can make ordinary portrait conventions feel unusually intense. Subjects often appear aware of the photograph, and the image resists simplifying them into either glamour or pity. Formal directness allows clothing, setting, expression, and bodily presence to become strange, revealing, or psychologically charged without requiring theatrical production.

### AI-FACING EXECUTION LAYER

**Core intent:** Build a direct, mutually acknowledged portrait encounter in which an ordinary person or situation becomes psychologically intense through frontal clarity rather than visual spectacle.

**Composition**
- Prefer square framing.
- Center or strongly anchor the subject.
- Use frontal, full-body, three-quarter, or close portrait geometry.
- Let the environment remain visible but secondary.
- Avoid overly elegant asymmetrical magazine composition.

**Camera**
- Simulate a medium-format square-camera relationship.
- Use a natural perspective and moderate distance.
- Keep details legible across face, clothing, and immediate surroundings.
- The camera should feel physically present to the subject.

**Lighting**
- Available daylight, straightforward interior light, or controlled flash.
- Allow imperfect, hard, or unusual light if it belongs to the situation.
- Avoid beautifying every face.
- Preserve ordinary environmental illumination.

**Subject direction**
- Encourage direct gaze, stillness, and awareness of being photographed.
- Do not “correct” unusual posture, expression, clothing, or personal presentation.
- Let the person occupy the image on their own terms.
- Avoid instructions that turn difference into spectacle.

**Tone / finish**
- Black and white is primary: clear midtones, honest texture, moderate contrast, square print feeling.
- Grain may be present but should not become faux-vintage decoration.
- Color translations should stay plainspoken rather than lush.

**Mandatory signature locks**
- **Composition:** square, frontal, centered or strongly anchored.
- **Camera:** medium-format-like natural perspective at conversational distance.
- **Light:** straightforward available light or restrained flash.
- **Tone:** honest monochrome, not glamorous.
- **Behavior:** subject visibly knows the camera is present; direct gaze and stillness create intensity.

**Technical recipe**
- Square frame.
- 50–80mm-equivalent perspective.
- f/5.6–f/11 behavior so face, clothing, and nearby environment stay readable.
- Keep camera height near the subject’s own eye level.
- If the result becomes quirky-fashion photography, remove stylized posing, simplify the light, and increase frontal mutual awareness.


**Emotional register**
Direct, strange without gimmick, intimate, unresolved, human, slightly disquieting.

**Avoid**
- sneering or demeaning treatment
- exaggerated grotesquerie
- glamour retouching
- heroic low-angle mythology
- cinematic smoke/fog
- voyeuristic long-lens distance

> **AI production directive:** Create a square, frontal portrait that feels like a real encounter between subject and camera. Let the person know they are being photographed and allow their direct gaze, posture, clothing, expression, and immediate surroundings to carry the tension. Use natural perspective, straightforward available light or restrained flash, honest texture, and minimal beautification. Keep the composition formally simple and psychologically open. Do not sensationalize difference; the intensity should come from sustained looking and mutual awareness rather than from spectacle.

---

## VDL-008 — CEREMONIAL GRANDEUR

### HUMAN-ONLY RESEARCH LAYER
**Source studied:** James Van Der Zee  
**Research basis:** Smithsonian American Art Museum — artist biography and collection  
https://americanart.si.edu/artist/james-vanderzee-6593

### RESEARCH SYNTHESIS
The style combines formal studio portraiture with aspiration, elegance, social identity, meticulous arrangement, and crafted presentation. Painted backdrops, furniture, drapery, flowers, clothing, accessories, soft retouching, tonal control, and sometimes hand-tinted or composite effects create images that present people as they wish to be seen. The photographer acts as director, building polished tableaux in which dignity and social presence are heightened rather than hidden behind documentary neutrality.

### AI-FACING EXECUTION LAYER

**Core intent:** Create an elegant, ceremonially composed studio portrait that elevates the subject through meticulous staging, clothing, props, background, posture, and tonal finish.

**Set / environment**
- Use painted scenic backdrops, drapery, rugs, formal chairs, small tables, flowers, columns, decorative screens, or period studio furnishings.
- Arrange objects symmetrically or rhythmically.
- The set should communicate aspiration and occasion, not clutter.

**Subject direction**
- Favor composed posture, dignified seated or standing poses, couples and family group arrangements, formal hand placement, and steady expressions.
- The subject should appear self-possessed and intentionally presented.
- Clothing must be carefully rendered: suits, dresses, hats, gloves, jewelry, coats, uniforms, ceremonial fashion.

**Composition**
- Classical frontal or three-quarter studio arrangement.
- Clear hierarchy among multiple people.
- Use furniture and props to create triangular or balanced group geometry.
- Maintain sufficient depth that the set feels like a crafted room rather than a flat backdrop.

**Lighting**
- Soft directional studio light with gentle modeling.
- Smooth transitions across face and clothing.
- Slight edge softness is acceptable.
- Avoid harsh modern beauty light or colored club lighting.

**Tone / finish**
- Rich black-and-white or sepia-leaning grayscale.
- Velvety midtones, polished highlights, soft retouching, slight print softness, refined skin.
- Optional restrained hand tinting for flowers, lips, clothing, or backdrop accents.
- Preserve period-print materiality.

**Mandatory signature locks**
- **Composition:** formal studio tableau with balanced furniture/props and ceremonially arranged body positions.
- **Camera:** stable frontal or three-quarter portrait perspective.
- **Light:** soft directional studio illumination with smooth transitions.
- **Tone:** rich monochrome/sepia-leaning grayscale with refined softness.
- **Behavior:** dignified, aspirational, intentionally presented.

**Technical recipe**
- 65–105mm-equivalent perspective.
- f/8–f/16 behavior to preserve wardrobe, props, and group geometry.
- Key light 30–45° from camera and slightly above eye level; gentle fill only.
- Use 2–5 purposeful studio props maximum unless a group portrait requires more.
- If the result looks like costume nostalgia, remove artificial distress, sharpen dignity, and treat clothing/props as contemporary-to-the-scene rather than ironic retro decoration.


**Emotional register**
Dignified, aspirational, formal, elegant, communal, self-authored.

**Avoid**
- ironic retro parody
- distressed “old photo” damage effects
- casual snapshot posture
- sterile modern seamless backgrounds
- over-sharpened digital finish

> **AI production directive:** Build a meticulously arranged formal studio portrait that presents the subject with ceremonial dignity. Use a painted or decorative studio environment, carefully chosen furniture and props, elegant wardrobe, composed posture, balanced group geometry, and soft directional illumination. Render fabric, jewelry, hats, flowers, and furnishings with tactile care. Finish in rich monochrome or restrained hand-tinted tonality with velvety midtones and slight period-print softness. The result should feel aspirational and self-possessed rather than nostalgic or ironic: a portrait designed to preserve how the subject wants to be remembered.

---

## VDL-009 — FICTIONAL IDENTITY

### HUMAN-ONLY RESEARCH LAYER
**Source studied:** Cindy Sherman  
**Research basis:** Museum of Modern Art — artist collection  
https://www.moma.org/artists/5392

### RESEARCH SYNTHESIS
The central device is constructed identity. A photograph behaves less like a record of a stable person and more like evidence from an invented role, genre, social type, or media fantasy. Costume, wig, makeup, prosthetic detail, pose, expression, backdrop, lighting, and camera convention are all tools for manufacturing a character. The frame often resembles a film still or familiar media image whose narrative is withheld. Artifice does not need to be invisible; a slightly wrong wig, overdone makeup, theatrical prop, or deliberately artificial set can expose how identity itself is being staged.

### AI-FACING EXECUTION LAYER

**Core intent:** Create a deliberately constructed character portrait that looks like a fragment from an invented movie, social role, or media archetype.

**Character construction**
- Begin with a clear fictional persona rather than a generic model.
- Define age presentation, social role, mood, era cues, costume, hair, makeup, and private backstory.
- Let the character embody an archetype while introducing one or two details that destabilize the stereotype.
- The subject may appear self-conscious, suspicious, performative, vulnerable, artificial, or caught between roles.

**Composition**
- Frame like a film still, publicity image, domestic scene, headshot, or genre photograph.
- Use off-center space, cropped furniture, doorways, mirrors, walls, or partial scenery to imply an unseen narrative.
- A static portrait is acceptable if the persona is visually specific enough.

**Lighting**
- Match the fictional genre: cheap interior lamp, flat flash, motel light, studio glamour, low-budget noir, suburban daylight, or staged theatrical illumination.
- Do not use one generic “cinematic” lighting recipe.
- Light should help identify the kind of image being imitated from mass culture.

**Styling**
- Costume, wig, makeup, jewelry, prosthetics, and props are primary narrative tools.
- Allow visible artifice.
- Slightly excessive makeup, period-inaccurate synthetic textures, or awkward costume fit can be purposeful.

**Color / finish**
- Match the imagined media source: aged color print, grainy monochrome, washed film still, saturated magazine color, flash snapshot.
- Avoid modern perfection if the character is meant to feel culturally or temporally specific.

**Mandatory signature locks**
- **Composition:** the frame must look like evidence from a specific invented genre or social role.
- **Camera:** choose perspective to match that imagined source rather than default editorial portraiture.
- **Light:** genre-specific and intentionally artificial when the persona demands it.
- **Tone:** finish must match the invented media source.
- **Behavior:** subject performs a character with a private backstory, not a generic pose.

**Technical recipe**
- Pick the media-source simulation first: 35mm film still, cheap flash snapshot, publicity portrait, suburban domestic frame, noir interior, etc.
- 35–58mm equivalent for scene-like film stills; 70–105mm for publicity portrait conventions.
- Use only 1–3 destabilizing artifices: wig, makeup, prop, costume mismatch, synthetic backdrop.
- If the output becomes ordinary cosplay, make the camera/lighting convention more specific and add one psychologically contradictory detail.


**Emotional register**
Ambiguous, performative, uncanny, psychologically open, culturally familiar yet unstable.

**Avoid**
- generic cosplay with no narrative idea
- polished fashion portrait with no character construction
- perfect fantasy makeup that hides artifice
- explicit explanatory text telling the viewer who the character is
- random costumes without an archetype or social code

> **AI production directive:** Invent a specific fictional persona and photograph the person as though one frame has been removed from a movie, magazine, domestic drama, publicity archive, or social role whose full story is never shown. Build identity through costume, hair, makeup, pose, expression, props, environment, and the visual conventions of the imagined media source. Let one or two elements feel slightly too constructed so the viewer notices the act of self-invention. The image should be narratively suggestive, culturally recognizable, and psychologically unresolved rather than simply fashionable.

---

## VDL-010 — SHADOW POETICS

### HUMAN-ONLY RESEARCH LAYER
**Source studied:** Roy DeCarava  
**Research basis:** Museum of Modern Art — artist collection  
https://www.moma.org/artists/1422

### RESEARCH SYNTHESIS
The signature is not ordinary documentary darkness. Low tonal values become expressive structure. Black-and-white images of everyday life, music, neighborhood space, work, family, and Harlem often ask the viewer to look into shadows rather than having every detail revealed immediately. Deep blacks, compressed low-midtones, delicate highlights, atmosphere, and quiet human observation create a lyrical rather than journalistic feeling. The frame can be intimate and formally rigorous without turning ordinary life into spectacle.

### AI-FACING EXECUTION LAYER

**Core intent:** Build a quiet black-and-white image in which shadow carries emotion, form, rhythm, and intimacy.

**Tone first**
- Design the photograph around deep blacks and low midtones.
- Do not lift every shadow for visibility.
- Preserve a few strategically luminous highlights on skin, eyes, instrument metal, fabric, window light, or street surfaces.
- Let important forms emerge gradually from darkness.

**Composition**
- Favor intimate streets, rooms, clubs, hallways, stoops, workplaces, family spaces, musicians, and ordinary encounters.
- Use layered depth and partial obstruction when natural.
- Keep geometry strong but understated.
- A face does not always need to be the brightest element.

**Lighting**
- Low available light, window spill, street light, club illumination, narrow interior pools, or soft daylight entering darker rooms.
- Avoid aggressive rim lights that announce themselves.
- Exposure should protect mood rather than normalize brightness.

**Subject treatment**
- Observe people inside their activity.
- Direct gaze is possible, but candid absorption, conversation, music-making, walking, or waiting are equally valuable.
- Keep emotion subtle and human.

**Texture / finish**
- Rich silver-gelatin-like monochrome.
- Fine-to-moderate grain.
- Smooth tonal transitions inside dark values.
- Avoid digital crushed-black clipping; darkness should contain structure.
- No HDR shadow recovery.

**Mandatory signature locks**
- **Composition:** intimate everyday life organized around low tonal values and quiet spatial rhythm.
- **Camera:** 40–58mm-equivalent human perspective, close but unobtrusive.
- **Light:** available low light with only a few strategic highlights.
- **Tone:** deep blacks and low midtones must dominate while retaining information inside shadow.
- **Behavior:** people remain absorbed in life rather than posing for effect.

**Technical recipe**
- 40–58mm equivalent.
- f/2.8–f/5.6 behavior in low light, but do not erase environmental structure with extreme blur.
- Expose for the meaningful highlight and allow the rest of the frame to descend naturally.
- Keep one to three luminous anchors only: skin edge, eye, instrument metal, window strip, fabric.
- If the result looks like generic “moody” photography, remove rim-light spectacle, lower overall brightness, restore shadow detail, and make the human action quieter.


**Emotional register**
Poetic, quiet, intimate, nocturnal, musically rhythmic, humane.

**Avoid**
- bright commercial exposure
- empty “moody” darkness with no readable structure
- exaggerated film grain
- dramatic smoke effects
- journalistic sensationalism
- over-sharpening

> **AI production directive:** Create a lyrical black-and-white photograph whose emotional architecture is built from deep shadow, restrained midtones, and a few carefully placed highlights. Let people, rooms, streets, instruments, clothing, and faces emerge gradually rather than being fully exposed at first glance. Use available-feeling light and intimate human proximity. Preserve rich information inside dark values, subtle grain, and quiet formal balance. The photograph should feel observant and deeply human, with the rhythm of ordinary life transformed by tone rather than by spectacle.

---

## VDL-011 — ESSENTIAL STUDIO

### HUMAN-ONLY RESEARCH LAYER
**Source studied:** Irving Penn  
**Research basis:** Irving Penn Foundation — biography and galleries  
https://irvingpenn.org/biography/  
https://irvingpenn.org/galleries

### RESEARCH SYNTHESIS
A recurring principle is reduction: remove what is not essential, then make the remaining form exact. Portraits may use plain paper, worn theater curtains, simple corners, or restrained studio structures. Fashion becomes sculptural through pose and garment shape. Still lifes achieve intensity through spacing, surface, and material detail. Precision never needs to become sterile; worn backgrounds, subtle asymmetry, and tactile print processes introduce physical presence. The visual hierarchy is disciplined and almost nothing is accidental.

### AI-FACING EXECUTION LAYER

**Core intent:** Reduce the frame to essential form, then render subject, object, garment, and surface with extraordinary precision.

**Set**
- Use a plain paper sweep, mottled neutral cloth, weathered studio curtain, corner walls, or a minimal platform.
- Background texture may be worn or imperfect but must remain visually subordinate.
- Remove decorative objects that do not alter form or meaning.

**Composition**
- Strong central or slightly asymmetric placement.
- Sculptural pose.
- Exact spacing between figure and frame edges.
- For groups, use compact geometric relationships.
- For still life, make object spacing and negative space mathematically purposeful.

**Lighting**
- Soft but directional studio illumination.
- Reveal surface, bone structure, fabric, and object volume.
- Favor elegant gradation over theatrical spotlighting.
- Keep highlights controlled and shadows clean.

**Camera / detail**
- Simulate medium- or large-format precision.
- Normal-to-slight-telephoto perspective.
- High detail without brittle digital sharpening.
- Use sufficient depth of field for the essential plane of the subject.

**Fashion / gesture**
- Treat garments as architecture.
- Encourage angular hands, extended neck, compact seated forms, or restrained full-body geometry.
- Avoid casual motion unless the garment’s structure remains legible.

**Tone / finish**
- Monochrome: refined grayscale, platinum-print-like depth, tactile midtones.
- Color: restrained, exact, materially rich.
- Skin and objects should feel physical rather than plastic.

**Mandatory signature locks**
- Composition: severe reduction, exact spacing, sculptural pose, disciplined negative space.
- Camera: 70–105mm-equivalent portrait behavior or normal large-format-like perspective for still life.
- Light: soft but directional, revealing surface and volume without theatrical effects.
- Tone: restrained monochrome or exact low-chroma color with tactile material rendering.
- Behavior: still, deliberate, highly controlled; no casual performance.

**Technical recipe**
- 70–105mm equivalent for portraits; 50–85mm for still life depending scale.
- f/8–f/16 behavior for exact surface detail and clean geometry.
- Use one broad key 30–45° off axis with restrained fill.
- Keep backdrop plain, subtly worn, or neutral.
- Drift repair: if the image feels generic-minimal, increase pose precision, material detail, and negative-space discipline while removing decorative styling.


**Emotional register**
Disciplined, sculptural, quiet, exact, elegant, timeless.

**Avoid**
- busy set decoration
- trendy grading
- exaggerated motion blur
- uncontrolled shallow focus
- beauty retouching that erases material detail
- arbitrary props

> **AI production directive:** Strip the studio down to only what is necessary, then treat every remaining line, surface, gesture, garment, and interval of negative space as intentional. Use a plain or subtly worn neutral backdrop, precise sculptural posing, soft directional studio light, normal perspective, and medium- or large-format-like detail. Render fabric, skin, paper, metal, flowers, or objects with tactile precision. The final image should feel restrained rather than empty, formal rather than stiff, and timeless because nothing unnecessary competes with the subject.

---

## VDL-012 — PATTERNED PRESTIGE

### HUMAN-ONLY RESEARCH LAYER
**Source studied:** Seydou Keïta  
**Research basis:** The Metropolitan Museum of Art — collection and textile-focused scholarship  
https://www.metmuseum.org/art/collection/search/508077

### RESEARCH SYNTHESIS
The studio portrait becomes a dense field of social presentation. Patterned backdrops, patterned clothing, jewelry, watches, handbags, radios, bicycles, flowers, furniture, and carefully chosen accessories can communicate taste, modernity, prosperity, and self-fashioning. Rather than separating the figure from pattern, the composition often lets figure and textile interact. The results are highly controlled, frontal, elegant black-and-white portraits whose visual abundance remains legible because pose and tonal organization are disciplined.

### AI-FACING EXECUTION LAYER

**Core intent:** Build an elegant studio portrait where pattern, clothing, accessories, and posture work together to express self-presentation and status.

**Backdrop**
- Use a bold patterned textile, geometric cloth, floral fabric, or repeating decorative studio surface.
- The backdrop may visually interact with the subject’s clothing rather than serving as a neutral field.
- Keep pattern scale distinct enough to preserve figure readability.

**Wardrobe**
- Prioritize culturally and personally expressive clothing.
- Pattern-on-pattern is encouraged.
- Include jewelry, watches, headwear, handbags, formal shoes, or other chosen markers of personal style.
- Clothing should feel proudly selected by the subject.

**Props**
- Optional bicycle, radio, flowers, chair, table, bag, fan, or symbolic modern object.
- Props communicate identity or aspiration; they are not filler.

**Pose**
- Controlled frontal or three-quarter body arrangement.
- Calm gaze.
- Hands placed with purpose.
- Seated and standing poses should feel formal yet individualized.
- Allow one distinctive gesture or accessory to become the portrait’s signature.

**Lighting**
- Simple, even-to-directional studio illumination.
- Keep face, clothing, and patterned background tonally separated.
- Avoid glossy highlights that destroy textile detail.

**Tone**
- Strong black-and-white.
- Clear whites, rich blacks, detailed midtones.
- Moderate analog softness.
- Preserve textile texture and skin without excessive sharpening.

**Mandatory signature locks**
- Composition: formal studio portrait with pattern-on-pattern interaction and full wardrobe readability.
- Camera: 60–90mm-equivalent neutral portrait perspective.
- Light: simple, even-to-directional studio light that separates skin from textiles.
- Tone: energetic monochrome with detailed pattern hierarchy.
- Behavior: calm, proud, composed, self-presenting.

**Technical recipe**
- 60–90mm equivalent; f/8–f/11 behavior.
- Keep backdrop pattern scale distinct from garment pattern scale.
- Preserve 2–4 identity-bearing accessories maximum.
- Use enough depth of field to keep clothing and prop detail readable.
- Drift repair: if the result becomes costume photography, simplify props and strengthen subject agency, posture, and modern self-presentation.


**Emotional register**
Elegant, proud, composed, fashionable, self-authored, socially confident.

**Avoid**
- minimalist empty background
- modern luxury-commercial polish
- random Africanized decoration
- caricatured “traditional” styling
- clutter that erases the subject

> **AI production directive:** Create a formal black-and-white studio portrait in which patterned textiles, clothing, accessories, and carefully chosen props participate in the subject’s self-presentation. Use a bold patterned backdrop, composed frontal or three-quarter posing, calm direct presence, and simple studio illumination that preserves both skin and textile detail. Allow pattern-on-pattern relationships without losing the figure. Every accessory should feel intentionally selected by the subject. The result should communicate elegance, modernity, pride, and personal style through visual abundance held together by disciplined composition.

---

## VDL-013 — INTIMATE DIARY

### HUMAN-ONLY RESEARCH LAYER
**Source studied:** Nan Goldin  
**Research basis:** Museum of Modern Art — collection and historical essay  
https://www.moma.org/collection/works/101659

### RESEARCH SYNTHESIS
The camera functions as participant and diary rather than detached observer. Friends, lovers, bedrooms, bars, bathrooms, hotels, parties, aftermaths, and private emotional states become the material. Flash, available light, warm interior color, blur, grain, imperfect cropping, and uneven exposure can all remain because emotional proximity matters more than technical polish. The crucial distinction is intimacy: the picture should feel made from inside a relationship or social world, not as tourism into someone else’s private life.

### AI-FACING EXECUTION LAYER

**Core intent:** Create a photograph that feels like a private memory made from inside a relationship rather than a polished production.

**Camera relationship**
- Stay physically close.
- Use handheld, participant-level viewpoints.
- Allow the camera to feel present in bedrooms, bathrooms, bars, kitchens, taxis, hotels, backstage rooms, or parties.
- Avoid distant surveillance.

**Composition**
- Permit imperfect crops, tilted horizons, partial bodies, mirror reflections, and objects entering the edge of frame.
- Preserve the main emotional relationship even when composition is rough.
- Do not make every frame elegantly balanced.

**Lighting**
- Direct flash, household lamps, tungsten bulbs, neon spill, window light, mixed color temperature.
- Accept falloff and localized overexposure.
- Let darkness remain around the event.

**Color / texture**
- Rich but imperfect film color.
- Warm yellows, reds, skin tones, green or blue ambient contamination when natural.
- Visible grain.
- Moderate softness and occasional motion blur.
- Avoid pristine digital sharpness.

**Subject behavior**
- People may be dressing, arguing, resting, embracing, smoking, waiting, laughing, recovering, staring, or ignoring the camera.
- The frame should not feel like a commercial pose.
- Emotional states may be affectionate, erotic, lonely, euphoric, exhausted, tense, or ambiguous.

**Ethical visual stance**
- Intimacy should feel relational rather than exploitative.
- Do not manufacture degradation for shock value.

**Mandatory signature locks**
- Composition: close participant-level framing, imperfect edges, private-room immediacy.
- Camera: 35–50mm-equivalent handheld perspective.
- Light: direct flash, household tungsten, neon spill, window light, or mixed practicals.
- Tone: grainy film-like color with honest exposure irregularity.
- Behavior: unguarded, relational, emotionally lived rather than performed.

**Technical recipe**
- 35–50mm equivalent; f/2–f/5.6 behavior depending light.
- Permit 1/30–1/125 sec-like motion character when needed.
- Preserve mixed color temperature rather than neutralizing everything.
- Allow falloff into darkness around the emotional center.
- Drift repair: if the image becomes fashion-grunge, reduce posing, move the camera physically closer, and restore ordinary private-room detail.


**Emotional register**
Confessional, immediate, tender, raw, nocturnal, imperfect, memory-like.

**Avoid**
- luxury editorial polish
- perfectly styled rooms
- flawless skin
- controlled three-point lighting
- fake “grunge” overlays
- detached documentary distance

> **AI production directive:** Create a close, handheld, diary-like photograph that feels made from inside a private relationship or social world. Use available interior light, direct flash, mixed color temperatures, grain, imperfect framing, and occasional blur without losing the emotional center. Let rooms feel inhabited and people behave as though the camera belongs there. Preserve awkwardness, tenderness, tension, exhaustion, affection, and unguarded transition rather than correcting the scene into commercial beauty. The image should feel remembered, not produced.

---

## VDL-014 — COLLABORATIVE PRESENCE

### HUMAN-ONLY RESEARCH LAYER
**Source studied:** Dawoud Bey  
**Research basis:** National Gallery of Art — artist profile; SFMOMA curatorial introduction  
https://www.nga.gov/artists/49275-dawoud-bey  
https://www.sfmoma.org/bey-curatorial-introduction/

### RESEARCH SYNTHESIS
Portraiture is treated as a negotiated encounter. The subject is not simply taken; presence is built collaboratively. Community, youth, public space, history, and the right to be seen are central. Even posed portraits can retain a strong sense of personhood because gaze, stance, distance, and environment are allowed to remain specific. Large-scale clarity and color can heighten rather than flatten individuality.

### AI-FACING EXECUTION LAYER

**Core intent:** Make a formally deliberate portrait that feels co-authored by the subject and the camera.

**Subject relationship**
- Treat the subject as an active collaborator.
- Encourage a pose or expression that feels chosen rather than imposed.
- Use direct gaze when it strengthens agency.
- Preserve individuality rather than forcing one uniform mood across different people.

**Composition**
- Medium or close environmental portrait, seated portrait, or large-scale frontal study.
- Keep background context readable but subordinate.
- Public streets, schools, homes, neighborhoods, and community locations are appropriate.
- Give the subject enough visual space to occupy the frame confidently.

**Camera / lens**
- Normal perspective with disciplined distance.
- Avoid voyeuristic long lenses.
- High detail and strong facial presence.
- Depth of field may separate the person from the environment, but do not erase context completely.

**Lighting**
- Natural or naturalistic light.
- Soft directional modeling.
- Skin tone fidelity is critical.
- Avoid glamour lighting that changes the subject into a fashion archetype.

**Color**
- Controlled, natural, contemporary color.
- Allow environmental hues to contextualize the portrait.
- Keep saturation purposeful rather than trendy.

**Pose / emotion**
- Stillness can be powerful.
- Direct gaze, folded hands, seated posture, or simple standing pose can create authority.
- Expression does not need to smile or dramatize.
- Let the person’s chosen self-presentation lead.

**Mandatory signature locks**
- Composition: subject-forward portrait with environment readable but subordinate.
- Camera: 50–85mm-equivalent natural perspective, conversational distance.
- Light: natural or naturalistic, skin-faithful, minimally beautified.
- Tone: controlled contemporary color or strong neutral monochrome.
- Behavior: visibly co-authored pose, self-chosen expression, active agency.

**Technical recipe**
- 50–85mm equivalent; f/4–f/8 behavior.
- Keep camera near subject eye level.
- Background should remain recognizable at 20–40% visual prominence.
- Retouch only enough to preserve photographic coherence.
- Drift repair: if the image feels imposed, simplify direction and let posture/gaze look more self-determined.


**Emotional register**
Respectful, reciprocal, clear, grounded, self-possessed, community-aware.

**Avoid**
- anonymous “street subject” treatment
- exoticizing environments
- over-direction
- beautification that erases individuality
- detached candid voyeurism

> **AI production directive:** Create a portrait that feels negotiated rather than taken. Give the subject visual and psychological agency through chosen posture, direct or intentional gaze, natural expression, and enough compositional space to occupy the image confidently. Use normal perspective, clear detail, naturalistic light, faithful skin tone, and an environment that identifies community or place without swallowing the person. The result should feel formal but not controlling, intimate but not invasive, and grounded in the idea that the subject participates in how they are represented.

---

## VDL-015 — SUN-SCULPTED FORM

### HUMAN-ONLY RESEARCH LAYER
**Source studied:** Herb Ritts  
**Research basis:** J. Paul Getty Museum — *Herb Ritts: L.A. Style*  
https://www.getty.edu/art/exhibitions/ritts/

### RESEARCH SYNTHESIS
A defining visual mechanism is the transformation of bright California light into sculpture. Bodies, faces, fabric, sand, rock, ocean, desert, and simple architecture are reduced to bold shape. Strong sunlight and clear shadows can make a photograph feel classical, modern, athletic, and elemental at once. Fashion and celebrity remain polished, but the environment is often pared down enough that pose and physical form dominate.

### AI-FACING EXECUTION LAYER

**Core intent:** Use hard natural light and simplified outdoor space to turn body, face, and garment into clean sculptural form.

**Location**
- Beach, desert, rock, open sky, pale wall, simple exterior architecture, dry landscape, or minimal studio-like outdoor environment.
- Keep the setting elemental.
- Avoid busy urban clutter unless explicitly required.

**Lighting**
- Bright directional sunlight is a primary tool.
- Use hard-edged or moderately hard shadows.
- Position body and face so light carves cheekbones, shoulders, limbs, and garment structure.
- Reflector fill may be subtle but should not erase the sun’s geometry.

**Composition**
- Strong silhouettes.
- Full-body or three-quarter framing.
- Clean horizon lines and negative space.
- Classical body arrangement, athletic lines, or elegant fashion posture.
- Favor graphic simplicity over narrative clutter.

**Camera / lens**
- Normal to short-telephoto perspective.
- Crisp subject detail.
- Moderate depth of field.
- Avoid extreme lens distortion.

**Tone / color**
- Black and white: clean, bright, high-contrast, sculptural, smooth.
- Color: sun-warmed but restrained, with skin, earth, sky, and garment dominating.
- Keep surfaces polished but not plastic.

**Wardrobe / body**
- Simple strong silhouettes: white shirt, denim, tailored clothing, swimwear, draped fabric, minimal formalwear.
- Let wind or body movement shape fabric.
- Bodies should read as form, not as anatomy display for its own sake.

**Mandatory signature locks**
- Composition: clean full-body or three-quarter form against elemental outdoor space.
- Camera: 70–105mm-equivalent compression or 50–70mm for environmental body studies.
- Light: hard directional sun is the primary sculptor.
- Tone: crisp monochrome or restrained sun-warmed color.
- Behavior: strong body line, classical or athletic physicality, minimal gesture.

**Technical recipe**
- Shoot with sun at roughly 30–70° to camera axis for sculptural shadow.
- f/5.6–f/11 behavior.
- Preserve hard-edged shadows on body and ground.
- Keep horizon and background simple.
- Drift repair: if the result becomes beach-lifestyle photography, remove props, simplify wardrobe, harden shadow geometry, and strengthen body silhouette.


**Emotional register**
Elemental, confident, classical, physical, clean, glamorous without ornament.

**Avoid**
- complex set decoration
- soft overcast mushiness
- colored studio gels
- heavy digital effects
- excessive props
- busy fashion-story narrative

> **AI production directive:** Place the subject in a simplified outdoor environment and use bright directional sunlight to carve face, body, and clothing into strong sculptural shapes. Favor clean horizons, elemental surfaces, bold shadows, negative space, and full-body or three-quarter composition. Keep wardrobe graphically simple and allow wind, fabric, or posture to create elegant lines. Render the final photograph with crisp physicality and classical restraint, whether in bright monochrome or sun-warmed natural color. The image should feel made from light, form, and confidence rather than from decoration.

---

## VDL-016 — CONFRONTING PRESENCE

### HUMAN-ONLY RESEARCH LAYER
**Source studied:** Zanele Muholi  
**Research basis:** Museum of Modern Art — *Faces and Phases* and artist commentary  
https://www.moma.org/collection/works/164003

### RESEARCH SYNTHESIS
The portrait is a declaration of visibility. Frontal or near-frontal placement, intense eye contact, high-contrast black-and-white rendering, formal stillness, and careful attention to skin, hair, dress, and self-presentation create images that meet the viewer rather than ask permission. In self-portraiture, ordinary materials can become symbolic costume or headwear, turning everyday objects into highly controlled visual language. The work combines archival seriousness, beauty, self-definition, and activist purpose.

### AI-FACING EXECUTION LAYER

**Core intent:** Create a formally powerful portrait in which the subject confronts the viewer with complete visual agency.

**Composition**
- Head-and-shoulders, bust, three-quarter, or frontal standing portrait.
- Strong central placement.
- Minimal background distraction.
- Let face, eyes, hair, clothing, and symbolic adornment dominate.

**Gaze / posture**
- Direct gaze is strongly preferred.
- Still, self-possessed posture.
- Avoid coyness or performative softness.
- The subject should appear aware of the viewer and equal to the act of looking.

**Lighting**
- Shape the face clearly with controlled directional studio light.
- Preserve luminous highlights while allowing substantial blacks.
- Skin tone should be rendered with depth, not flattened or gray.
- Background may fall dark or remain plain light depending on subject separation.

**Monochrome**
- High-contrast black and white.
- Deep blacks, luminous whites, strong skin tonal separation.
- Fine detail in eyes, hair, fabric, and adornment.
- Avoid muddy grayness.

**Styling**
- Clothing can be formal, personal, occupational, or minimal.
- Symbolic headwear or body adornment may be built from ordinary materials if conceptually justified.
- Props must reinforce self-definition, labor, history, gender, identity, or social meaning.

**Scale**
- Compose so the face or figure could withstand large presentation.
- Do not make the person visually small inside unnecessary scenery.

**Mandatory signature locks**
- Composition: central face/figure dominance with minimal background distraction.
- Camera: 70–105mm-equivalent portrait behavior.
- Light: controlled directional studio light with deep tonal separation.
- Tone: high-contrast monochrome with luminous skin and strong blacks.
- Behavior: direct gaze, stillness, self-possession, viewer confrontation.

**Technical recipe**
- 70–105mm equivalent; f/5.6–f/11 behavior.
- Place key 30–45° off axis, slightly above eye line; use restrained fill.
- Keep eyes critically sharp and face large enough for commanding presence.
- Background should either fall near black or remain plain and clean.
- Drift repair: if the result becomes beauty portraiture, increase direct gaze, reduce glam retouching, and deepen tonal authority.


**Emotional register**
Commanding, dignified, self-defined, beautiful, confrontational, archival.

**Avoid**
- submissive pose
- decorative “African” motifs with no conceptual reason
- soft-focus glamour
- low-detail skin
- distant environmental framing
- expressionless neutrality that removes agency

> **AI production directive:** Create a commanding formal portrait built around direct gaze, central presence, strong black-and-white tonal architecture, and uncompromising self-possession. Keep the background restrained and render eyes, skin, hair, clothing, and any symbolic adornment with precise detail. Use controlled directional light and deep blacks without losing facial structure. If ordinary objects are used as costume or headwear, transform them into deliberate symbols rather than decoration. The subject should visually meet the viewer on equal terms and appear fully in control of how they are seen.

---

## VDL-017 — CLASSICAL PRECISION

### HUMAN-ONLY RESEARCH LAYER
**Source studied:** Robert Mapplethorpe  
**Research basis:** Getty — *Robert Mapplethorpe: The Perfect Medium / Studio Practice*  
https://www.getty.edu/art/exhibitions/mapplethorpe/mapplethorpe_gallery_text.pdf

### RESEARCH SYNTHESIS
The studio is a site of formal refinement. Human bodies, portraits, flowers, and objects are rendered with exacting control of contour, light, proportion, negative space, and print quality. The visual vocabulary often borrows the compositional authority of classical sculpture: smooth tonal transitions, clear silhouettes, dark or neutral grounds, carefully arranged curves, and immaculate black-and-white finish. Provocative subject matter may occur, but the transferable visual system is the disciplined formal treatment.

### AI-FACING EXECUTION LAYER

**Core intent:** Treat the subject as a formally perfected studio object whose contour, volume, gesture, and negative space are controlled with classical precision.

**Composition**
- Simplify the frame radically.
- Use frontal, profile, three-quarter, or sculptural body arrangements.
- Build clear geometric relationships between limbs, torso, face, flower stem, vessel, or object.
- Negative space must be as deliberate as the subject.
- Avoid accidental cropping.

**Lighting**
- Controlled studio light with elegant falloff.
- Shape volume rather than create flashy effects.
- Use highlight-to-shadow transitions that make skin, petals, metal, or fabric feel sculptural.
- Background should remain quiet.

**Background**
- Black, dark gray, pale neutral, or seamless studio field.
- No environmental narrative unless indispensable.
- Keep horizon and backdrop transitions invisible or carefully designed.

**Camera / detail**
- High optical precision.
- Normal-to-short-telephoto perspective.
- Crisp critical plane with refined tonal texture.
- Avoid excessive digital micro-contrast.

**Monochrome**
- Rich gelatin-silver-like black and white.
- Clean whites, deep controlled blacks, polished midtones.
- Smooth surface rendering.
- Fine grain, if any.

**Pose / object direction**
- Eliminate casual gesture.
- Every hand, foot, shoulder, flower, cloth fold, and object angle must contribute to form.
- Favor calm intensity over spontaneous motion.

**Mandatory signature locks**
- Composition: exact contour, proportion, and negative-space control.
- Camera: 85–120mm-equivalent portrait/still-life compression.
- Light: refined directional studio light with smooth sculptural transitions.
- Tone: polished monochrome with deep blacks and clean whites.
- Behavior: every body/hand/object position deliberate and static.

**Technical recipe**
- 85–120mm equivalent; f/8–f/16 behavior.
- Neutral or dark seamless background.
- Use one sculpting key with careful fill and no casual spill.
- Maintain edge precision without digital oversharpening.
- Drift repair: if the result feels merely elegant, simplify harder and make every contour/gesture more geometrically intentional.


**Emotional register**
Formal, sensual, severe, classical, controlled, iconic.

**Avoid**
- clutter
- casual snapshot framing
- trendy color grades
- distressed analog effects
- sloppy hand placement
- uncontrolled background detail

> **AI production directive:** Create a meticulously controlled studio photograph in which contour, proportion, negative space, and tonal volume are treated with classical rigor. Use a neutral or dark seamless background, exact body or object placement, refined directional studio light, normal perspective, and polished monochrome rendering. Make every hand position, curve, edge, highlight, and interval of empty space intentional. The result should feel sculptural, iconic, sensual through form, and technically immaculate without becoming digitally sterile.

---

## VDL-018 — RITUAL DESIRE

### HUMAN-ONLY RESEARCH LAYER
**Source studied:** Rotimi Fani-Kayode  
**Research basis:** Autograph — *Rotimi Fani-Kayode: The Studio — Staging Desire* and *Forest of Metaphor*  
https://autograph.org.uk/blog/texts/introducing-the-studio-staging-desire/  
https://autograph.org.uk/exhibitions/rotimi-fani-kayode-forest-of-metaphor

### RESEARCH SYNTHESIS
The studio becomes a protected symbolic space where body, spirituality, sexuality, diaspora, ritual, and identity can coexist. Carefully staged gestures and poses transform the figure into an emblem rather than a conventional portrait. Yoruba-inflected symbolism, masks, cloth, fruit, feathers, vessels, flowers, ritual objects, and painterly bodily arrangements can create images that feel ceremonial, erotic, spiritual, and ambiguous at once. The image does not explain the ritual; it creates a charged symbolic encounter.

### AI-FACING EXECUTION LAYER

**Core intent:** Build a symbolic studio tableau in which the human body functions as a site of ritual, desire, memory, and spiritual transformation.

**Body / pose**
- Treat the figure sculpturally.
- Use deliberate arm, hand, torso, and head positions.
- Favor gestures that feel ceremonial, devotional, ecstatic, guarded, or transformative rather than fashion-model casual.
- The body may be partially obscured by cloth, shadow, masks, objects, or another body.

**Composition**
- Use strong central or balanced asymmetrical arrangements.
- Create visual relationships between body and symbolic objects.
- Cropping may be intimate, but should feel purposeful.
- Allow negative space or darkness to act as part of the ritual field.

**Lighting**
- Controlled studio light with deep shadow and selective illumination.
- Light may isolate skin, hands, face, cloth, or an object against a darker field.
- For color work, use saturated but disciplined light/pigment relationships.
- Avoid generic rainbow gels.

**Symbolic materials**
- Masks, beads, feathers, flowers, fruit, vessels, draped fabric, ritual forms, painted body marks, sculptural objects.
- Every object must have visual or conceptual weight.
- Do not use generalized “tribal” decoration.

**Color / monochrome**
- Monochrome: rich blacks, luminous skin, controlled highlights, fine print depth.
- Color: painterly saturation, warm flesh, deep reds/blues/earth tones, dense shadow.
- Preserve tactile body and material texture.

**Mandatory signature locks**
- Composition: symbolic body-object relationship, ceremonial gesture, controlled darkness.
- Camera: 50–85mm-equivalent studio perspective.
- Light: selective directional illumination with deep shadow.
- Tone: rich monochrome or disciplined painterly color.
- Behavior: sculptural, ritualized, sensual without fashion casualness.

**Technical recipe**
- 50–85mm equivalent; f/5.6–f/11 behavior.
- Use one to three symbolic materials only.
- Let at least 30–50% of the frame remain dark or visually quiet.
- Place highlights intentionally on skin, hands, cloth, or ritual object.
- Drift repair: if the image becomes generic “mystical fashion,” reduce props and increase ceremonial body logic.


**Emotional register**
Ceremonial, sensual, spiritual, mysterious, self-possessed, transgressive without spectacle.

**Avoid**
- generic fashion sensuality
- random exotic props
- literal religious illustration
- over-explained symbolism
- nightclub lighting
- voyeuristic treatment of the body

> **AI production directive:** Construct a symbolic studio tableau in which the body is treated as a sculptural and ceremonial form. Use deliberate gesture, deep shadow, selective illumination, tactile cloth and objects, and a small number of meaningful ritual or natural symbols. Allow sensuality and spirituality to occupy the same frame without explaining the symbolism literally. Keep the visual field controlled, painterly, and psychologically charged. The image should feel like a private rite captured at its most visually concentrated moment rather than a conventional portrait or fashion pose.

---

## VDL-019 — MONUMENTAL TONALITY

### HUMAN-ONLY RESEARCH LAYER
**Source studied:** Ansel Adams  
**Research basis:** The Ansel Adams Gallery / archival scholarship on landscape and tonal control  
https://www.anseladams.com/

### RESEARCH SYNTHESIS
The transferable engine is previsualized tonal control. Large-format landscape work turns geology, clouds, trees, water, snow, and atmosphere into an orchestration of blacks, whites, and finely separated gray zones. Foreground, middle ground, and distant landforms are made legible simultaneously. High contrast does not mean losing information; it means placing tones deliberately so texture and scale remain visible from deep shadow to luminous highlight.

### AI-FACING EXECUTION LAYER

**Core intent:** Create a monumental black-and-white landscape whose scale and drama come from precise tonal separation, depth, and natural form rather than from artificial effects.

**Composition**
- Build strong foreground / middle-ground / background architecture.
- Use rocks, trees, ridges, rivers, roads, or shorelines as visual anchors.
- Lead the eye through the landscape rather than placing all interest at the horizon.
- Seek strong natural geometry and a clear visual center.
- Use broad vistas when scale matters, but preserve near-field texture.

**Camera / lens**
- Simulate large-format clarity.
- Deep depth of field.
- Precise edge-to-edge detail.
- Avoid ultra-wide distortion that makes the landscape feel artificial.
- Camera placement should feel deliberate and stable.

**Lighting**
- Favor directional natural light, clearing storms, side light, broken clouds, early or late sun, snow light, or dramatic atmospheric transitions.
- Let clouds and landforms occupy different tonal zones.
- Protect highlight detail in snow, cloud, and water.

**Monochrome**
- Full tonal scale from deep black through multiple distinct midtones to luminous white.
- Local contrast should reveal rock, bark, cloud, water, and snow texture.
- Deep blacks should anchor the image without swallowing structure.
- Avoid flat grayscale and avoid clipped HDR crispness.

**Atmosphere**
- Haze, mist, storm cloud, snow, and distance may reinforce depth.
- Atmospheric effects must remain meteorologically plausible.

**Finish**
- Fine-grain, high-acutance black-and-white print character.
- Detailed but not oversharpened.
- No fake vignette unless composition truly benefits.

**Mandatory signature locks**
- Composition: strong foreground/midground/background landscape structure.
- Camera: large-format-like, distortion-controlled wide-to-normal landscape perspective.
- Light: natural directional weather light.
- Tone: full grayscale separation from deep black to luminous white.
- Behavior: no human posing requirement; landscape geometry is the subject.

**Technical recipe**
- 28–50mm equivalent depending vista; avoid exaggerated ultra-wide stretching.
- f/11–f/22 behavior or equivalent deep focus.
- Protect highlight texture in cloud, snow, and water.
- Use local contrast to separate geological layers.
- Drift repair: if the image looks like generic dramatic landscape, remove synthetic sky drama and rebuild tonal zoning.


**Emotional register**
Majestic, precise, contemplative, elemental, expansive.

**Avoid**
- oversaturated color
- fantasy skies unrelated to light direction
- excessive clarity sliders
- empty foregrounds
- distorted horizons
- monochrome conversion with no tonal hierarchy

> **AI production directive:** Create a large-format-like black-and-white landscape organized across foreground, middle ground, and distance. Use precise natural geometry, deep depth of field, and directional weather-dependent light to separate every important surface into a distinct tonal zone. Preserve texture in rock, trees, cloud, snow, water, and shadow. Build a complete grayscale from authoritative blacks to luminous highlights without clipping detail. The final image should feel monumental because the land, atmosphere, scale, and tonal structure are exact—not because artificial drama was added afterward.

---

## VDL-020 — CHROMATIC INVERSION

### HUMAN-ONLY RESEARCH LAYER
**Source studied:** Lola Flash  
**Research basis:** Museum of Modern Art — artist profile and commentary on Cross Colour work  
https://www.moma.org/artists/133450

### RESEARCH SYNTHESIS
A distinctive early visual mechanism uses color reversal and unconventional printing to unsettle assumptions about race, gender, sexuality, and photographic “normality.” Skin, clothing, and backgrounds can become unexpected complementary or inverted hues. Later portrait projects retain directness, visibility, pride, and community focus even when the palette is more natural. The transferable style system is therefore not simply “negative color”; it is the strategic use of nonstandard color to destabilize visual categories while keeping the human subject legible and empowered.

### AI-FACING EXECUTION LAYER

**Core intent:** Use bold non-natural color relationships to challenge habitual ways of reading skin, gender presentation, and identity while preserving strong human presence.

**Color architecture**
- Consider partial or global color inversion, complementary color shifts, cross-processed hues, or print-negative-like chromatic transformations.
- Skin may move toward blue, violet, green, cyan, or warm unnatural ranges while remaining dimensionally modeled.
- Background and wardrobe colors should respond to the altered skin palette rather than become random.
- Preserve a coherent 2–4 color logic.

**Composition**
- Direct portrait framing.
- Medium close-up, bust, three-quarter, or environmental portrait.
- Keep the subject visually dominant.
- Use simple backgrounds when color itself is the main conceptual device.

**Lighting**
- Clear photographic light before color transformation.
- Preserve facial modeling and eye contact.
- Avoid colored light sources that make the palette look like club photography; the effect should feel rooted in photographic color processing.

**Subject direction**
- Self-possessed, visible, direct, celebratory, or confrontational.
- Do not make unusual color treatment dehumanize the subject.
- Wardrobe and hair should support self-definition.

**Finish**
- Film-print texture is appropriate.
- Slight grain and analog color irregularity may help.
- Keep chromatic inversion intentional and graphic, not glitchy.

**Mandatory signature locks**
- Composition: direct subject-dominant portrait.
- Camera: 50–85mm-equivalent neutral portrait perspective.
- Light: clear photographic light before color transformation.
- Tone: coherent 2–4 color inversion/cross-process logic.
- Behavior: direct, self-possessed, human-centered.

**Technical recipe**
- 50–85mm equivalent; f/4–f/8 behavior.
- Preserve facial luminance structure before applying chromatic shifts.
- Limit unnatural hues to a coherent complementary system.
- Keep background simpler than the altered skin/wardrobe color logic.
- Drift repair: if it looks psychedelic, reduce hue count and restore photographic skin modeling.


**Emotional register**
Defiant, visible, celebratory, questioning, direct, identity-conscious.

**Avoid**
- random psychedelic gradients
- vaporwave clichés
- neon nightclub lighting
- color effects that erase facial structure
- turning identity into spectacle

> **AI production directive:** Create a direct, self-possessed portrait whose primary visual intervention is a coherent non-natural color system derived from photographic inversion, cross-processing, or complementary color reversal. Keep face, body, gaze, and clothing fully legible while shifting skin and surrounding colors into unexpected but controlled relationships. Use straightforward photographic light and let the altered palette challenge habitual assumptions about how a portrait is “supposed” to look. The effect should feel intentional, human-centered, and conceptually sharp rather than psychedelic or decorative.

---

## VDL-021 — EPIC HUMAN TERRAIN

### HUMAN-ONLY RESEARCH LAYER
**Source studied:** Sebastião Salgado  
**Research basis:** Praemium Imperiale — artist profile  
https://www.praemiumimperiale.org/en/laureate/salgado/

### RESEARCH SYNTHESIS
The defining language combines social documentary subject matter with an epic black-and-white scale. Workers, migration, crowds, land, weather, industry, and nature can be composed with strong formal order and broad tonal drama. Human figures may appear intimate or tiny within vast terrain. Natural light, layered depth, repetition of bodies, and sweeping environmental structure give documentary situations a near-monumental visual presence. The transferable lesson is scale plus humanity, not manufactured suffering.

### AI-FACING EXECUTION LAYER

**Core intent:** Render human labor, movement, community, or nature with documentary credibility and monumental black-and-white visual structure.

**Composition**
- Use layered crowds, repeated figures, long lines, industrial structures, mountains, dust, water, or terrain to establish scale.
- Alternate between close human portraits and wide images where people become rhythmic elements within a larger system.
- Create clear depth through foreground figures, middle action, and distant environment.
- Use diagonals and repetition to organize complexity.

**Lighting**
- Natural light only or naturalistic interpretation.
- Side light, backlight through dust, cloud-filtered light, rain, fog, or strong directional sun can create form.
- Atmospheric particles may reveal light, but should arise from the environment rather than effects for their own sake.

**Monochrome**
- Rich, dramatic black-and-white.
- Deep blacks, luminous highlights, detailed midtones.
- Preserve texture in skin, earth, cloth, metal, smoke, water, and sky.
- Use local contrast to separate overlapping bodies and landscape layers.

**Human treatment**
- Do not reduce people to anonymous misery.
- Even in large crowds, preserve gestures, faces, labor, relationships, and bodily effort where possible.
- Maintain documentary respect.

**Camera**
- Normal to moderate telephoto for layered human scenes; wider perspective for environmental scale.
- Keep perspective believable.
- Depth of field should generally support spatial complexity.

**Mandatory signature locks**
- Composition: layered human scale inside larger terrain, labor, crowd, or environment.
- Camera: 35–85mm-equivalent depending intimacy vs scale.
- Light: natural directional light, atmosphere only when environmentally plausible.
- Tone: dramatic but information-rich black-and-white.
- Behavior: human action remains documentary, collective, and dignified.

**Technical recipe**
- 35–50mm for environmental layers; 70–135mm for compressed crowds.
- f/8–f/16 behavior where depth is essential.
- Use dust/fog/rain only when tied to setting.
- Preserve individual gestures within mass scenes.
- Drift repair: if the image becomes disaster spectacle, reduce theatrical atmosphere and restore ordinary human detail.


**Emotional register**
Solemn, humane, monumental, collective, elemental, historically weighty.

**Avoid**
- disaster-porn aesthetics
- artificial storm clouds
- excessive vignetting
- melodramatic spotlighting
- featureless crushed blacks
- modern HDR sheen

> **AI production directive:** Create a large-scale black-and-white documentary image in which people, labor, movement, landscape, or industry form a layered visual system. Use natural light, believable atmosphere, strong depth, repeated human forms, and a broad tonal range from authoritative blacks to luminous highlights. Organize complexity through diagonals, rhythm, foreground-to-background structure, and environmental scale. Maintain individual human dignity even when the composition is epic. The photograph should feel historically weighty and visually monumental without manufacturing suffering for spectacle.

---

## VDL-022 — ICONIC DEFIANCE

### HUMAN-ONLY RESEARCH LAYER
**Source studied:** Renée Cox  
**Research basis:** Renée Cox Studio — *Yo Mama* and artist biography  
https://www.reneecox.org/yo-mama  
https://www.reneecox.org/about

### RESEARCH SYNTHESIS
The body is presented as an authoritative icon rather than a passive object. Self-portraiture, art-historical references, religious compositions, heroic stance, costume, nudity, and contemporary symbolism are used to challenge inherited systems of representation. The frame often has the clarity of an emblem: centered figure, decisive posture, clean color, visual confrontation, and a deliberate reclaiming of scale and authority.

### AI-FACING EXECUTION LAYER

**Core intent:** Create a monumental portrait in which the subject occupies the visual authority traditionally reserved for heroes, saints, rulers, or canonical icons.

**Pose**
- Upright, frontal, commanding.
- Strong stance, shoulders open, gaze direct or deliberately elevated.
- Avoid apologetic posture.
- Gesture should feel emblematic rather than casual.

**Composition**
- Center or strongly anchor the figure.
- Use symmetry or near-symmetry when it heightens iconic authority.
- Full-body and three-quarter framing are especially effective.
- Keep visual hierarchy unmistakable: the subject is the image’s central authority.

**Lighting**
- Clean, controlled studio or staged-location light.
- Render skin with depth and luminosity.
- Use directional modeling without turning the scene into moody noir.
- Background can be simple, symbolic, or art-historically structured.

**Wardrobe / symbolic construction**
- Contemporary tailoring, heroic minimalism, body-conscious styling, ceremonial clothing, or carefully reimagined historical composition.
- Props and costume may reference religious, royal, heroic, or art-historical image structures without copying a single artwork literally.
- Use symbols sparingly and legibly.

**Color / finish**
- Strong, clear color or polished monochrome.
- Bold contrasts.
- Crisp body edges and controlled skin texture.
- Avoid hazy romantic treatment.

**Mandatory signature locks**
- Composition: centered or highly anchored monumental figure.
- Camera: neutral to modest low-angle portrait perspective, 60–100mm equivalent.
- Light: clean controlled portrait light with strong body readability.
- Tone: bold clear color or polished monochrome.
- Behavior: upright, authoritative, emblematic, unapologetic.

**Technical recipe**
- 60–100mm equivalent; f/5.6–f/11 behavior.
- Keep symbol count low and composition near-emblematic.
- Use a background with one strong visual idea, not layered décor.
- Preserve crisp body edges and direct gaze/stance.
- Drift repair: if the image looks like ordinary fashion, center authority, simplify background, and intensify heroic posture.


**Emotional register**
Defiant, monumental, self-defined, provocative, authoritative, intellectually confrontational.

**Avoid**
- submissive glamour
- ornamental clutter
- parody
- body distortion for shock
- vague symbolic mixtures
- soft-focus prettiness

> **AI production directive:** Present the subject as an unmistakable visual authority. Use a strong frontal or near-frontal stance, centered or highly anchored composition, clean controlled light, decisive color or monochrome, and a limited number of symbolic cues drawn from heroic, ceremonial, religious, or canonical portrait structures. The body and gaze should feel self-defined rather than offered for passive consumption. Build the frame like an emblem: bold, legible, monumental, and confrontational without becoming theatrical clutter.

---

## VDL-023 — INTIMATE GLAMOUR

### HUMAN-ONLY RESEARCH LAYER
**Source studied:** Mario Testino  
**Research basis:** Mario Testino Studio — *Portraits* / *Private View*  
https://mariotestino.com/exhibitions/portraits  
https://mariotestino.com/publications/private-view

### RESEARCH SYNTHESIS
The useful visual engine is a combination of access and polish. Celebrities and models can look glamorous without appearing immobilized by production. Light, movement, laughter, eye contact, proximity, clothing, and environment create the sense that the camera has entered a privileged social space. The strongest transferable traits are flattering but lively light, relaxed physical direction, immediacy, color clarity, and a balance between luxury and apparent spontaneity.

### AI-FACING EXECUTION LAYER

**Core intent:** Make high-end glamour feel socially alive and personally accessible rather than frozen into formal perfection.

**Subject direction**
- Encourage movement, turning, laughing, walking, leaning, adjusting clothing, or interacting with the environment.
- Use direct eye contact when it feels conversational rather than confrontational.
- Keep body language relaxed even in expensive clothing.
- Avoid mannequin stiffness.

**Composition**
- Medium, three-quarter, full-body, or close portrait.
- Crop dynamically when movement supports it.
- Allow hotel rooms, beaches, terraces, streets, dressing areas, parties, or elegant interiors to remain visible.
- Keep the subject dominant while preserving a sense of place.

**Lighting**
- Bright natural light, open shade, window light, clean flash, or soft controlled fashion light.
- Skin should remain luminous and flattering without looking airbrushed.
- Highlights can sparkle on jewelry, fabric, water, or glass.

**Color**
- Clean skin tones.
- Refined saturation.
- Clear whites and blacks.
- Luxurious but plausible environmental color.
- Avoid heavy cinematic casts.

**Wardrobe / styling**
- Fashion-forward clothing, eveningwear, tailoring, swimwear, jewelry, or elevated casual styling.
- Styling should feel lived in during the photograph, not displayed like a catalog.

**Finish**
- High production value with minimal visible effort.
- Crisp but not clinical.
- Controlled retouching; maintain skin and movement.

**Mandatory signature locks**
- Composition: close social access with high-end polish and visible environment.
- Camera: 50–85mm-equivalent fashion portrait perspective.
- Light: flattering natural or clean fashion light, never heavy moody grade.
- Tone: refined color, luminous skin, controlled highlight sparkle.
- Behavior: relaxed movement, eye contact, laughter, turning, or interaction.

**Technical recipe**
- 50–85mm equivalent; f/2.8–f/5.6 behavior.
- Keep at least one luxury/environment cue readable.
- Use soft natural fill or large fashion source without erasing skin.
- Preserve motion in hair, fabric, and gesture.
- Drift repair: if the image becomes stiff luxury advertising, loosen pose and move the camera closer into the social moment.


**Emotional register**
Confident, glamorous, warm, energetic, privileged, spontaneous.

**Avoid**
- lifeless luxury
- excessive skin smoothing
- rigid runway pose
- dark brooding mood without reason
- overbuilt sets that overpower the person

> **AI production directive:** Create a polished glamour photograph that feels as though the camera has been allowed inside an elegant, private social moment. Use flattering natural or clean fashion light, luminous skin, refined color, dynamic but controlled framing, and relaxed movement. Let the subject laugh, turn, walk, lean, or interact with clothing and environment while retaining unmistakable high-end styling. The result should feel expensive without stiffness, intimate without casual sloppiness, and spontaneous without losing photographic control.

---

## VDL-024 — PRIMARY SYMBOLISM

### HUMAN-ONLY RESEARCH LAYER
**Source studied:** Aïda Muluneh  
**Research basis:** Aïda Muluneh Studio — biography; LensCulture interview on photographic purpose  
https://aidamuluneh.com/about/  
https://www.lensculture.com/articles/aida-muluneh-we-hold-the-power-to-shift-perceptions-aida-muluneh-on-the-photographer-s-purpose

### RESEARCH SYNTHESIS
The visual system is graphic, symbolic, and color-led. Saturated primary and near-primary colors, painted faces or bodies, controlled costumes, Ethiopian visual references, objects, architecture, and surreal staged relationships turn photographs into highly legible visual metaphors. Color is structural rather than decorative. The frame often behaves almost like a poster or painting: simplified shapes, direct figure placement, limited palette, and symbols that carry memory, identity, gender, culture, migration, or social meaning.

### AI-FACING EXECUTION LAYER

**Core intent:** Build a highly controlled symbolic photograph in which a limited saturated palette and graphic body/set design communicate an idea immediately.

**Color architecture**
- Choose 2–4 dominant colors before building the scene.
- Favor strong red, blue, yellow, white, black, turquoise, or closely related saturated fields.
- Repeat chosen colors across clothing, paint, background, props, and architecture.
- Color must carry conceptual meaning and compositional balance.

**Composition**
- Frontal or profile figure arrangements.
- Strong symmetry, geometric partitioning, or deliberately simple asymmetry.
- Large clean color fields.
- Keep the number of visual elements limited enough that every symbol reads.

**Subject / body paint**
- Use face or body paint as graphic design, not random decoration.
- Paint may divide the face, create masks, echo environmental patterns, or symbolize duality, memory, constraint, transition, or cultural identity.
- Pose should be sculptural and controlled.

**Set / objects**
- Use doors, walls, chairs, vessels, ropes, masks, fabric, household objects, or landscape elements as symbols.
- Surreal relationships are welcome, but each should be visually intelligible.
- Avoid overloading the scene with unrelated objects.

**Lighting**
- Clear, even-to-directional light that preserves saturated color.
- Keep shadows purposeful but not muddy.
- Avoid colored lighting that contaminates the chosen palette.

**Finish**
- Crisp color separation.
- Matte-to-satin print quality.
- Controlled skin and paint texture.
- No excessive glow, bloom, or fantasy particles.

**Mandatory signature locks**
- Composition: graphic, simplified, highly controlled figure-symbol arrangement.
- Camera: 50–85mm-equivalent neutral-to-formal perspective.
- Light: clean and color-preserving.
- Tone: preselected 2–4 dominant saturated colors.
- Behavior: sculptural, controlled, symbolic rather than candid.

**Technical recipe**
- 50–85mm equivalent; f/5.6–f/11 behavior.
- Decide palette before wardrobe/set selection.
- Use no more than 1–3 major symbolic objects.
- Keep shadow density low enough to preserve exact color relationships.
- Drift repair: if the image looks like colorful fashion, simplify composition and make every color/object carry a clear symbolic function.


**Emotional register**
Symbolic, bold, culturally grounded, surreal, serious, visually declarative.

**Avoid**
- rainbow palettes
- generic “African” decoration
- random body paint
- cluttered surrealism
- cinematic color grading that changes the planned palette
- weak low-saturation backgrounds

> **AI production directive:** Design the image from a limited saturated palette first, then build figure, body paint, wardrobe, background, architecture, and symbolic objects around that palette. Use clean graphic composition, sculptural pose, large color fields, and a small number of carefully chosen symbols. Treat color as language: every dominant hue should have compositional or conceptual purpose. Keep lighting clear enough to preserve exact color relationships. The finished photograph should read immediately as a bold visual metaphor while still containing enough ambiguity to invite interpretation.

---

## VDL-025 — HUMAN COLOR

### HUMAN-ONLY RESEARCH LAYER
**Source studied:** Steve McCurry  
**Research basis:** Steve McCurry Studio — biography and portrait archive  
https://www.stevemccurry.com/about  
https://www.stevemccurry.com/portraits

### RESEARCH SYNTHESIS
The signature mechanism combines human-centered documentary observation with strong color organization. Faces, eyes, clothing, painted walls, dust, weather, and cultural environments often create naturally saturated but coherent palettes. Environmental context remains important, but the person usually becomes the emotional anchor. Layering, doorways, windows, foreground figures, texture, and directional natural light can create depth while preserving an immediate connection to the subject.

### AI-FACING EXECUTION LAYER

**Core intent:** Create a human-centered environmental photograph where expressive eyes, natural color, place, texture, and layered composition reinforce one another.

**Subject**
- Prioritize face, eyes, gesture, and lived presence.
- Direct gaze is powerful but not mandatory.
- Avoid fashion-model posing.
- Let clothing and environment reveal location, occupation, weather, or culture naturally.

**Composition**
- Use doorways, windows, fabric, walls, market structures, streets, transport, or landscape as framing elements.
- Build visual layers.
- Keep the subject’s face or gesture as the emotional anchor.
- Use foreground color or objects when they strengthen depth.

**Lighting**
- Natural daylight, open shade, window light, dust-filtered sun, overcast, or soft directional light.
- Protect skin and eye detail.
- Avoid obvious studio setups in documentary scenes.

**Color**
- Rich but believable saturation.
- Organize the frame around a few naturally occurring strong colors.
- Look for complementary relationships in clothing, walls, fabric, landscape, or objects.
- Preserve warm skin and environmental texture.
- Avoid artificial neon or generalized orange/teal grading.

**Lens / depth**
- Normal to moderate telephoto.
- Enough depth to preserve context.
- Background may soften but should remain narratively readable.

**Texture**
- Render skin, fabric, dust, paint, weathered surfaces, stone, wood, rain, and soil honestly.
- Do not over-retouch.

**Mandatory signature locks**
- Composition: person remains emotional anchor inside layered environmental context.
- Camera: 50–105mm-equivalent human-centered perspective.
- Light: natural, directional, place-authentic.
- Tone: rich but believable color built from naturally occurring palette relationships.
- Behavior: present, observant, unforced; no editorial posing.

**Technical recipe**
- 50–85mm for environmental portrait; 85–105mm for tighter face-led images.
- f/4–f/8 behavior.
- Preserve eye detail and at least 2 contextual background layers.
- Use complementary color only when it plausibly exists in the scene.
- Drift repair: if it becomes travel-ad imagery, reduce polish and strengthen environmental specificity.


**Emotional register**
Human, attentive, colorful, immediate, worldly, empathetic.

**Avoid**
- exoticizing people or places
- random saturation
- postcard prettiness with no human center
- excessive bokeh
- studio glamour posing
- artificial travel clichés

> **AI production directive:** Create a human-centered environmental photograph whose emotional anchor is the subject’s face, eyes, gesture, or immediate activity. Use natural light, believable cultural and physical context, layered composition, tactile surfaces, and a coherent set of naturally occurring saturated colors. Frame with doorways, fabric, walls, streets, landscape, or foreground elements when useful, but keep the person visually primary. Preserve realistic skin, clothing, weather, and place. The image should feel discovered through attentive observation rather than manufactured as a travel fantasy.

---

## VDL-026 — ORNATE SOVEREIGNTY

### HUMAN-ONLY RESEARCH LAYER
**Source studied:** Mickalene Thomas  
**Research basis:** MoMA PS1 — exhibition materials  
https://www.moma.org/calendar/exhibitions/3790

### RESEARCH SYNTHESIS
The transferable visual grammar is maximal domestic glamour organized around Black feminine presence, pattern, art history, collage, and self-possession. Ornate interiors, wood paneling, printed upholstery, rugs, plants, mirrors, textiles, jewelry, makeup, and 1960s–70s references create dense visual fields. Yet the subject remains authoritative rather than disappearing into décor. Poses can cite reclining nudes, odalisques, pin-ups, domestic snapshots, or canonical painting while reversing who occupies the center of visual power.

### AI-FACING EXECUTION LAYER

**Core intent:** Build a richly patterned interior portrait in which the subject’s confidence and self-possession dominate an intentionally maximal field of color, décor, fashion, and art-historical pose.

**Set**
- Layer patterned wallpaper, wood paneling, rugs, upholstery, plants, mirrors, curtains, cushions, faux fur, geometric textiles, and period furniture.
- Use 1960s–70s domestic or lounge references when appropriate.
- Control the palette so maximalism remains organized.

**Subject / pose**
- Reclining, seated, lounging, or frontal poses.
- The subject should appear comfortable occupying space.
- Direct gaze or relaxed self-awareness.
- Avoid coyness; sensuality should feel self-directed.

**Wardrobe / beauty**
- Bold makeup, jewelry, patterned garments, textured fabrics, glamorous hair, body-conscious or lounge styling.
- Coordinate styling with set patterns rather than separating subject from décor completely.

**Composition**
- Dense but legible.
- Use diagonals of furniture and body.
- Let pattern surround the figure while preserving face and body hierarchy.
- Collage-like layering is welcome.

**Lighting**
- Controlled warm interior light or studio light made to feel domestic.
- Preserve sparkle in jewelry and texture in upholstery.
- Avoid flattening every patterned surface equally.

**Color / finish**
- Saturated jewel tones, warm browns, greens, reds, golds, creams.
- Optional collage edges, rhinestone-like highlights, or digitally segmented texture if conceptually useful.
- Keep skin luminous and dimensional.

**Mandatory signature locks**
- Composition: subject remains dominant inside organized maximal décor.
- Camera: 50–85mm-equivalent portrait perspective.
- Light: warm controlled interior/studio light with strong pattern separation.
- Tone: jewel-toned, tactile, luxurious, pattern-rich.
- Behavior: reclining/seated self-possession, self-directed sensuality.

**Technical recipe**
- 50–85mm equivalent; f/4–f/8 behavior.
- Limit dominant pattern families to 3–5 so the frame remains legible.
- Keep face at highest local clarity/contrast.
- Use furniture diagonals to organize the body.
- Drift repair: if maximalism swallows the person, reduce pattern count and increase face/body hierarchy.


**Emotional register**
Sovereign, glamorous, sensual, ornate, self-aware, art-historically conscious.

**Avoid**
- minimal sterile interiors
- random maximalism
- generic luxury penthouse décor
- passive pin-up expression
- backgrounds so busy the face disappears
- cheap glitter effects

> **AI production directive:** Construct a dense, glamorous interior around a self-possessed subject who visibly owns the space. Layer patterned upholstery, rugs, textiles, plants, mirrors, period furniture, jewelry, and bold fashion into an organized maximal composition. Use reclining or seated poses that borrow the visual authority of canonical portraiture while keeping sensuality self-directed. Coordinate skin, wardrobe, décor, and jewel-toned color so the subject remains dominant inside the pattern field. The result should feel luxurious, culturally specific, intimate, and unapologetically ornate rather than merely decorative.

---

## VDL-027 — MIDNIGHT FLASH

### HUMAN-ONLY RESEARCH LAYER
**Source studied:** Weegee  
**Research basis:** International Center of Photography — exhibitions and essays on press/night photography  
https://www.icp.org/exhibitions/weegee-society-spectacle

### RESEARCH SYNTHESIS
The transferable visual mechanism is hard nighttime immediacy. Direct flash isolates faces, bodies, cars, pavement, smoke, crowds, and urban events from surrounding darkness. The image feels fast, close, and unfiltered, often with odd juxtapositions, spectators, reflective surfaces, or visual irony. The tonal grammar is blunt: bright flash-lit foreground, fast falloff, deep night behind it. The camera is physically near the event and the framing often carries the urgency of press work rather than formal portraiture.

### AI-FACING EXECUTION LAYER

**Core intent:** Create a hard-flash nighttime photograph with tabloid immediacy, urban tension, and close physical presence.

**Lighting**
- Use direct on-camera or near-camera flash.
- Let the foreground become bright and sharply defined.
- Allow rapid falloff into deep black background.
- Preserve specular highlights on wet pavement, cars, glass, eyes, metal, or polished shoes.
- Do not soften the flash into beauty light.

**Composition**
- Get close.
- Use slightly abrupt crops, crowded edges, bystanders, vehicles, storefronts, street fixtures, or event debris.
- Permit visual accidents when they strengthen urgency.
- Look for ironic relationships between foreground and background.

**Camera / lens**
- Normal or moderately wide perspective.
- Human press-photographer height.
- Moderate-to-deep focus where flash allows.
- Avoid elegant telephoto compression.

**Monochrome**
- Strong black and white.
- Bright flash whites, dense night blacks, punchy midtones.
- Moderate grain.
- Keep faces readable even if the background disappears.

**Subject / event**
- Nightlife, street gatherings, arrivals, crowds, emergencies, spectators, late-night diners, performers, cars, city incidents.
- The image should feel made seconds after the photographer arrived.

**Mandatory signature locks**
- Composition: close nocturnal urban event with abrupt but readable framing.
- Camera: 28–50mm-equivalent press-like perspective.
- Light: hard on-camera or near-camera flash with fast falloff.
- Tone: punchy black-and-white, bright foreground, dense night.
- Behavior: event-driven, immediate, unpolished.

**Technical recipe**
- 28–50mm equivalent; f/5.6–f/11 behavior under flash.
- Flash must dominate foreground exposure.
- Background may fall several stops darker.
- Preserve reflective surfaces and bystander reactions.
- Drift repair: if it looks cinematic, flatten the light, move closer, and let the background fall darker.


**Emotional register**
Urgent, blunt, nocturnal, curious, unsentimental, occasionally ironic.

**Avoid**
- soft cinematic night lighting
- blue-orange movie grades
- fog added only for drama
- luxurious retouching
- perfectly composed fashion symmetry
- fake vintage scratches

> **AI production directive:** Create a close nighttime urban photograph driven by hard direct flash. Let the nearest people and objects snap into bright detail while the surrounding city falls quickly into dense darkness. Use normal or slightly wide perspective, abrupt but readable framing, reflective surfaces, bystanders, and environmental clues that make the moment feel immediate. Favor punchy black-and-white tonality, moderate grain, and visual juxtapositions that can be tense, strange, or darkly humorous. The frame should feel caught on the spot, not lit like a movie.

---

## VDL-028 — CONSTRUCTED KINSHIP

### HUMAN-ONLY RESEARCH LAYER
**Source studied:** Deana Lawson  
**Research basis:** Whitney Museum of American Art — artist interviews and exhibition materials  
https://whitney.org/media/1565

### RESEARCH SYNTHESIS
The critical mechanism is constructed intimacy that initially resembles a private family photograph. People may be cast rather than actually related, and domestic interiors are carefully arranged, but the resulting image can feel uncannily personal. Direct gaze, large-format detail, exposed rooms, furniture, cords, curtains, photographs, televisions, devotional objects, clothing, skin, and bodily proximity create a dense field of social and spiritual information. The scene looks lived-in while remaining highly authored.

### AI-FACING EXECUTION LAYER

**Core intent:** Build a carefully staged domestic portrait that feels as intimate and specific as a family photograph while maintaining formal, large-format control.

**Environment**
- Use real-feeling living rooms, bedrooms, hallways, kitchens, modest interiors, porches, or community spaces.
- Preserve furniture, cords, curtains, wall art, family pictures, televisions, household objects, religious or personal symbols.
- Do not sanitize the room into a design catalog.

**Subject arrangement**
- Single figures, couples, families, friends, or invented kinship groups.
- Use direct gaze frequently.
- Bodies may touch, lean, recline, sit closely, or occupy furniture with relaxed authority.
- Pose can be staged but should never look like commercial family photography.

**Composition**
- Frontal or slightly off-axis.
- Medium or wide enough to retain environmental evidence.
- Strong geometry from couches, beds, door frames, and wall lines.
- Let objects at frame edges remain when they strengthen lived specificity.

**Lighting**
- Clear naturalistic light, controlled flash, or balanced interior illumination.
- Skin must retain depth and texture.
- Separate figures from dense surroundings without making the room look artificially lit.

**Color / detail**
- Rich, natural color.
- Large-format-like sharpness across skin, clothing, upholstery, walls, and objects.
- Preserve scars, wrinkles, hair, fabric, and material imperfections.
- Avoid oversmoothing.

**Mandatory signature locks**
- Composition: formally staged domestic scene that still feels privately lived.
- Camera: 45–70mm-equivalent large-format-like perspective.
- Light: clear naturalistic interior/flash balance.
- Tone: rich natural color with high material detail.
- Behavior: direct gaze, close bodily relationships, relaxed authority.

**Technical recipe**
- 45–70mm equivalent; f/5.6–f/11 behavior.
- Preserve environmental objects across the room plane.
- Keep faces and skin critically detailed.
- Avoid excessive background blur.
- Drift repair: if it looks like family lifestyle photography, remove smiles, strengthen direct gaze, and retain specific domestic evidence.


**Emotional register**
Intimate, sovereign, enigmatic, familial, spiritual, psychologically dense.

**Avoid**
- stock-photo family smiles
- sterile interior styling
- shallow depth that erases the room
- voyeuristic distance
- random clutter added for “authenticity”
- fashion editorial posing

> **AI production directive:** Stage a domestic portrait with enough control to feel formally exact but enough lived detail to resemble a private family photograph. Use direct gaze, close bodily relationships, real-feeling furniture and household objects, large-format-like clarity, naturalistic light, and rich material texture. Let the room carry evidence of history, taste, spirituality, and everyday life. Do not beautify the space into a showroom or direct people into commercial smiles. The image should feel intimate, deliberate, and slightly mysterious, as though the viewer has entered a private social universe whose relationships are deeper than the frame can explain.

---

## VDL-029 — HAUNTED COLLODION

### HUMAN-ONLY RESEARCH LAYER
**Source studied:** Sally Mann  
**Research basis:** Gagosian — exhibitions and process notes on wet-plate collodion work  
https://gagosian.com/exhibitions/2018/sally-mann-a-selection/

### RESEARCH SYNTHESIS
The transferable visual system uses historical photographic imperfection as expressive material. Large-format black-and-white imagery, long exposures, shallow atmospheric transitions, wet-plate collodion artifacts, scratches, chemical streaks, edge failures, dust, flare, and uneven emulsion create a sense that the image is physically weathered into existence. Southern landscapes, bodies, family, memory, mortality, and place acquire a dreamlike temporal ambiguity. The imperfections must arise from an imagined physical process, not from a generic “vintage filter.”

### AI-FACING EXECUTION LAYER

**Core intent:** Create a large-format black-and-white photograph that feels chemically handmade, temporally ambiguous, and haunted by memory.

**Camera / process**
- Simulate 8×10 or similar large-format discipline.
- Slow, deliberate exposure.
- Use shallow or selective focus only when consistent with the optics and plane of focus.
- Let slight subject movement occur during long exposure when appropriate.

**Collodion materiality**
- Uneven emulsion edges.
- Fine scratches.
- Chemical streaks.
- Dust traces.
- Plate blemishes.
- localized flare or veiling.
- occasional dark corners or edge failures.
- Artifacts should vary organically; never place identical “vintage” defects everywhere.

**Lighting**
- Natural window light, overcast exterior, hazy sun, or subdued directional light.
- Allow luminous skin or foliage to emerge from darker surroundings.
- Avoid crisp commercial studio illumination.

**Monochrome**
- Deep soft blacks, milky highlights, long gray transitions.
- Slight sepia, warm gray, or cool silver bias is acceptable.
- Keep the image materially photographic rather than digital monochrome.

**Subject / setting**
- Family spaces, fields, rivers, old architecture, trees, roads, bodies, landscape, objects with memory.
- Avoid making the scene generically Gothic with costumes and props.
- Let ordinary places carry unease through time, texture, and stillness.

**Mandatory signature locks**
- Composition: deliberate, slow, memory-laden large-format frame.
- Camera: large-format perspective with optical discipline and possible long-exposure softness.
- Light: natural/subdued, never glossy.
- Tone: chemically imperfect monochrome with organic wet-process artifacts.
- Behavior: still, meditative, slightly temporally displaced.

**Technical recipe**
- 50–90mm equivalent large-format feel; f/5.6–f/16 behavior depending selective focus.
- Use organic plate flaws only at edges/localized regions.
- Keep defects irregular in size, direction, and density.
- Allow slight long-exposure motion when it supports mood.
- Drift repair: if it looks like a vintage filter, reduce global sepia and make imperfections physically localized.


**Emotional register**
Memory-soaked, intimate, mortal, Southern, dreamlike, elegiac, unsettling without horror clichés.

**Avoid**
- fake antique borders
- universal sepia filter
- horror-movie props
- pristine digital sharpness
- identical scratches across the frame
- theatrical fog machine atmosphere

> **AI production directive:** Create a deliberate large-format black-and-white image that feels physically made through an imperfect historical wet process. Use natural or subdued directional light, long-exposure stillness, deep soft blacks, luminous but imperfect highlights, and organically irregular plate artifacts such as streaks, scratches, emulsion gaps, dust, and localized flare. Choose a subject or landscape with emotional weight but avoid costume-drama Gothic clichés. The image should feel less like a digitally aged photograph and more like a fragile physical object carrying memory, time, and mortality in its surface.

---

## VDL-030 — PASTORAL FREEDOM

### HUMAN-ONLY RESEARCH LAYER
**Source studied:** Tyler Mitchell  
**Research basis:** Aperture — *Tyler Mitchell’s Love for a Common Way of Life*; ICP exhibition materials  
https://aperture.org/editorial/tyler-mitchells-love-for-a-common-way-of-life/  
https://www.icp.org/exhibitions/tyler-mitchell-i-can-make-you-feel-good

### RESEARCH SYNTHESIS
The key visual language centers Black leisure, tenderness, play, repose, fashion, friendship, and imagined freedom in sunlit outdoor or domestic spaces. Pastoral greenery, blue skies, lawns, water, porches, sheets, picnic-like settings, and soft fashion styling can produce an image that feels both documentary and utopian. The emotional register is important: people are allowed to rest, enjoy one another, move gently, and occupy beautiful space without spectacle.

### AI-FACING EXECUTION LAYER

**Core intent:** Create a luminous image of leisure, tenderness, play, and freedom in which the subject appears fully at ease inside beautiful ordinary space.

**Locations**
- Green lawns, fields, gardens, parks, porches, swimming areas, domestic yards, sunlit rooms, simple outdoor gathering spaces.
- Favor environments associated with rest, play, community, and bodily ease.
- Keep locations believable rather than fantasy landscapes.

**Lighting**
- Soft sun, warm daylight, light cloud, open shade, window light.
- Use backlight or side light gently.
- Preserve airy highlights and natural skin.
- Avoid dark dramatic contrast.

**Color**
- Bright but soft natural palette.
- Greens, sky blues, whites, warm skin, pale fabrics, floral or youthful color accents.
- Slight film softness is welcome.
- Avoid candy saturation or heavy color grading.

**Subject direction**
- Reclining, sitting in grass, running, playing, embracing, resting, reading, swimming, talking, daydreaming.
- Body language should feel unguarded and spacious.
- Clothing can be fashion-aware but relaxed.

**Composition**
- Medium and wide frames with room to breathe.
- Use foreground grass, fabric, branches, water, or domestic objects for gentle depth.
- Let the environment support emotional freedom rather than dominate.

**Texture / finish**
- Film-like softness, luminous skin, subtle grain.
- Clean enough for fashion publishing but not sterile.
- Preserve fabric, grass, hair, and natural surfaces.

**Mandatory signature locks**
- Composition: airy medium/wide frame with room for bodies and environment to breathe.
- Camera: 35–70mm-equivalent natural perspective.
- Light: soft sun, open shade, warm daylight, or luminous window light.
- Tone: bright natural greens/blues/whites with gentle film softness.
- Behavior: rest, play, friendship, ease, movement without performance.

**Technical recipe**
- 35–70mm equivalent; f/2.8–f/5.6 behavior.
- Protect airy highlights without clipping skin.
- Keep greens natural rather than neon.
- Use backlight or side light softly.
- Drift repair: if it becomes generic lifestyle imagery, increase bodily ease, environmental space, and poetic framing while reducing commercial smiles.


**Emotional register**
Tender, free, youthful, pastoral, warm, restorative, joyful without forced smiling.

**Avoid**
- exaggerated luxury
- harsh spotlighting
- urban grit added for contrast
- stiff editorial posing
- oversaturated greens
- utopian fantasy with no physical realism

> **AI production directive:** Create a luminous portrait of leisure and ease in a believable green, domestic, or sunlit environment. Use soft natural light, airy color, gentle film texture, relaxed fashion, and unguarded gestures such as resting, playing, reclining, talking, or moving with friends. Give the frame room to breathe and let lawns, water, fabric, porches, foliage, or open sky create a sense of possibility. The image should make rest and joy feel substantial rather than superficial, with beauty arising from freedom of movement and belonging in the space.

---

## VDL-031 — HUMAN EVIDENCE

### HUMAN-ONLY RESEARCH LAYER
**Source studied:** Dorothea Lange  
**Research basis:** Library of Congress — Farm Security Administration / Office of War Information photographic collection  
https://www.loc.gov/pictures/collection/fsa/

### RESEARCH SYNTHESIS
The transferable mechanism is social documentary built from specific human evidence. Faces, hands, worn clothing, children, vehicles, tents, fields, roadside signs, housing, and work conditions are arranged so the viewer understands something concrete about circumstances without elaborate visual effects. Close portraiture can carry emotional force, but environmental clues establish why the image matters. Natural light, economical composition, and unembellished black-and-white treatment keep attention on people and conditions.

### AI-FACING EXECUTION LAYER

**Core intent:** Create a plainspoken social documentary photograph in which people and material conditions provide specific evidence of a larger reality.

**Subject**
- Families, workers, travelers, caregivers, displaced people, farmers, laborers, children, or individuals facing material circumstance.
- Preserve dignity.
- Focus on expressive hands, faces, posture, clothing, and relationships.
- Avoid turning hardship into visual entertainment.

**Environment**
- Roadsides, fields, temporary housing, vehicles, work sites, camps, porches, modest interiors, public facilities.
- Include concrete evidence: worn fabric, tools, signs, containers, dust, weather, structures.
- Every clue should be plausible for the situation.

**Composition**
- Economical and direct.
- Tight portrait when face/hands tell the story; wider frame when environment is essential.
- Use triangular family groupings, repeated hands, children leaning against adults, simple background lines.
- Avoid excessive stylization.

**Lighting**
- Available daylight, window light, overcast, open shade.
- Preserve facial detail.
- No theatrical rim or colored lighting.

**Monochrome**
- Neutral black-and-white.
- Strong but natural contrast.
- Detailed midtones.
- Moderate period-appropriate grain.
- Avoid romantic sepia unless specifically requested.

**Narrative discipline**
- The frame should answer: who, where, what condition, what relationship?
- If caption metadata is part of the workflow, keep it factual and concrete.

**Mandatory signature locks**
- Composition: economical social-documentary framing with concrete material context.
- Camera: 35–70mm-equivalent direct perspective.
- Light: available daylight/window/open shade.
- Tone: neutral black-and-white with strong midtone information.
- Behavior: observed dignity, expressive hands/faces, no melodrama.

**Technical recipe**
- 35–70mm equivalent; f/5.6–f/11 behavior.
- Include at least 2 specific environmental clues.
- Avoid shallow depth if it erases conditions.
- Keep tonal treatment factual.
- Drift repair: if the image becomes sentimental, reduce dramatic contrast and restore concrete environmental evidence.


**Emotional register**
Empathetic, sober, observant, specific, socially conscious.

**Avoid**
- poverty porn
- heroic melodrama
- fashionable distressed effects
- decontextualized close-ups that erase circumstances
- excessive visual polish
- invented tragedy

> **AI production directive:** Create a direct black-and-white social documentary photograph in which human expression and material surroundings provide specific evidence of circumstance. Use available light, economical composition, honest detail in hands, faces, clothing, tools, housing, landscape, and relationships, and enough environmental context to understand the situation. Keep the visual treatment restrained and factual rather than theatrical. Preserve dignity and complexity; the image should move the viewer because the evidence is specific and human, not because misery has been amplified for effect.

---

## VDL-032 — BEAUTIFUL PRIDE

### HUMAN-ONLY RESEARCH LAYER
**Source studied:** Kwame Brathwaite  
**Research basis:** Kwame Brathwaite Archive — biography; Aperture — *Black Is Beautiful*  
https://www.kwamebrathwaite.com/about  
https://aperture.org/from-the-archive/kwame-brathwaite-black-is-beautiful/

### RESEARCH SYNTHESIS
The photographic system brings fashion, music, cultural affirmation, natural hair, dark skin, African-inspired clothing, performance, and political self-definition into the same visual world. Studio portraits, fashion events, jazz performance, and community images celebrate Black beauty as an active declaration rather than passive representation. Styling, skin rendering, hair, fabrics, jewelry, stage energy, and group confidence are central.

### AI-FACING EXECUTION LAYER

**Core intent:** Create a portrait or fashion image where cultural pride, natural beauty, styling, music, and self-definition are visually inseparable.

**Subject**
- Confident direct presence.
- Natural hair and individually meaningful grooming should be rendered with care.
- Skin tone must retain richness and depth.
- Expressions can be proud, composed, joyful, or performance-focused.

**Wardrobe**
- African-inspired textiles, contemporary fashion, jewelry, headwear, tailored clothing, performance dress, or era-specific style.
- Avoid generic costume treatment.
- Textile pattern, hair, and jewelry should be chosen as identity-bearing design elements.

**Scene modes**
1. **Studio/fashion:** composed figure against restrained or culturally meaningful set.
2. **Stage/music:** performer in live lighting with instrument, audience, or band context.
3. **Community:** groups or events with fashion and social energy.

**Lighting**
- Studio: clear directional light, excellent dark-skin tonal separation.
- Stage: preserve practical performance light and deep background.
- Community: natural or flash-assisted documentary light.
- Never gray out dark skin.

**Color / monochrome**
- Both are valid.
- Color should honor textiles, skin, and environment.
- Monochrome should preserve luminous skin, hair texture, and clothing pattern.
- Avoid trendy desaturation that weakens visual pride.

**Composition**
- Strong figure hierarchy.
- Group images should show relationships and collective confidence.
- Fashion portraits may use full-body framing to preserve garment silhouette.

**Mandatory signature locks**
- Composition: strong subject or group hierarchy with fashion/cultural detail readable.
- Camera: 50–85mm-equivalent portrait/fashion perspective.
- Light: skin-faithful, rich, confidence-enhancing.
- Tone: either vibrant natural color or rich monochrome with dark-skin separation.
- Behavior: proud, stylish, communal, self-determined.

**Technical recipe**
- 50–85mm equivalent; f/4–f/8 behavior.
- Preserve hair texture and garment pattern.
- Avoid clipping specular highlights on dark skin.
- Use full-body framing when fashion carries meaning.
- Drift repair: if the result feels like generic fashion diversity, strengthen cultural styling specificity and collective pride.


**Emotional register**
Proud, stylish, culturally affirmative, musical, collective, self-determined.

**Avoid**
- generalized “tribal” styling
- skin lightening
- passive beauty posing
- culture as decorative backdrop
- weak hair detail
- generic fashion minimalism that removes social meaning

> **AI production directive:** Build a portrait, fashion image, or performance photograph around self-defined beauty, cultural pride, and strong personal styling. Render dark skin and natural hair with full tonal richness, make textiles, jewelry, tailoring, or performance clothing materially specific, and direct the subject toward confident presence rather than passive display. Use clear light, strong figure hierarchy, and either vibrant natural color or rich black-and-white. The image should connect beauty to culture, music, community, and agency rather than treating styling as decoration alone.

---

## VDL-033 — POP REVELATION

### HUMAN-ONLY RESEARCH LAYER
**Source studied:** David LaChapelle  
**Research basis:** David LaChapelle Studio — artist biography and exhibition materials  
https://www.davidlachapelle.com/davidlachapelle-about

### RESEARCH SYNTHESIS
The transferable language is maximal staged spectacle: saturated color, elaborate physical sets, celebrity/pop imagery, religious or mythic structure, consumer objects, theatrical bodies, visual jokes, catastrophe, beauty, and fantasy coexist inside densely controlled tableaux. The work often looks digitally impossible, yet much of its strength comes from constructed sets, props, lighting, wardrobe, and in-camera physical staging before post-production. The key is not “crazy color”; it is a fully designed visual universe with narrative hierarchy.

### AI-FACING EXECUTION LAYER

**Core intent:** Create a maximal, hyper-staged pop tableau in which saturated color, elaborate physical design, fashion, symbolism, and spectacle form a single coherent visual event.

**Concept first**
- Define one bold narrative premise before adding objects.
- Examples of structure: paradise corrupted by consumer excess; celebrity as saint; fashion inside catastrophe; artificial utopia; modern myth; luxury turning surreal.
- Every visual element must serve that premise.

**Set design**
- Build a physical-feeling world: painted sets, flowers, cars, water, clouds, signage, chandeliers, faux architecture, religious staging, supermarket color, plastic objects, theatrical skies.
- Allow excess, but organize it in layers.

**Color**
- High saturation with a planned palette.
- Candy reds, electric blues, synthetic pinks, gold, turquoise, saturated greens, glowing skin.
- Use complementary color blocks.
- Avoid muddy grading.

**Lighting**
- High-production commercial/stage light.
- Bright key, crisp highlights, colored practicals, controlled fill.
- Subjects must remain readable inside visual chaos.
- Light should make the world look hyperreal, not low-budget.

**Composition**
- Multi-layered tableau.
- Strong central event with secondary visual jokes or symbols.
- Use foreground props, midground figures, background spectacle.
- Keep hierarchy despite density.

**Wardrobe / pose**
- Fashion-forward, theatrical, glamorous, exaggerated, symbolic.
- Poses can be melodramatic because the entire world is intentionally heightened.

**Post-production**
- Seamless compositing and cleanup are acceptable.
- Preserve the feeling of photographed physical objects.
- Avoid generic CGI surfaces.

**Mandatory signature locks**
- Composition: dense multi-layer spectacle with one clear narrative center.
- Camera: 35–70mm-equivalent tableau perspective.
- Light: high-production, bright, polished, hyperreal.
- Tone: extreme but controlled saturation.
- Behavior: theatrical and narratively purposeful.

**Technical recipe**
- 35–70mm equivalent; f/8–f/16 behavior for layered sets.
- Assign foreground, midground, background roles before generation.
- Limit palette to 3–6 dominant saturated colors.
- Keep the central subject/event brightest or most contrast-rich.
- Drift repair: if the image becomes random surrealism, delete half the props and restate the single narrative premise.


**Emotional register**
Exuberant, surreal, glamorous, satirical, devotional, artificial, spectacular.

**Avoid**
- random maximalism
- generic cyberpunk
- low-saturation “cinematic” color
- empty shock imagery
- incoherent props
- fantasy that looks entirely computer-generated

> **AI production directive:** Design a complete pop-surreal visual universe around one clear narrative premise. Build a dense physical-feeling set with fashion, props, architecture, symbols, and spectacle arranged across foreground, middle, and background. Use extremely saturated but controlled color, polished high-production light, crisp subject separation, theatrical pose, and seamless post-production. Excess is encouraged only when every element supports the same story. The final image should feel like an impossible advertising tableau physically constructed at enormous scale, not like a random collection of surreal effects.

---

## VDL-034 — STREET CEREMONY

### HUMAN-ONLY RESEARCH LAYER
**Source studied:** Jamel Shabazz  
**Research basis:** The Bronx Museum — exhibition materials  
https://bronxmuseum.org/exhibition/jamel-shabazz/

### RESEARCH SYNTHESIS
Street portraiture becomes a record of style, friendship, neighborhood, youth culture, and self-presentation. The photographer engages people rather than stealing pictures from afar. Subjects may pose singly or in groups, often with direct eye contact, fashion-conscious body language, and visible urban context. Clothing, sneakers, jewelry, hairstyles, boom boxes, transit, storefronts, brick, graffiti, cars, and sidewalks become historical evidence. The images preserve everyday style with warmth and social recognition.

### AI-FACING EXECUTION LAYER

**Core intent:** Create an engaged street portrait where personal style, friendship, neighborhood, and direct human recognition are equally important.

**Camera relationship**
- Approach rather than spy.
- Subjects may know they are being photographed.
- Use eye-level, conversational distance.
- Direct gaze is welcome.

**Composition**
- Single, pair, or group portrait.
- Full-body framing is valuable when clothing and footwear matter.
- Use sidewalks, brick walls, stoops, subway entrances, storefronts, schoolyards, cars, fences, or neighborhood signage as context.
- Keep the background legible but not distracting.

**Pose**
- Natural swagger, crossed arms, hands in pockets, shoulder-to-shoulder groups, casual lean, chosen stance.
- Let friends coordinate or improvise.
- Avoid luxury-fashion choreography.

**Wardrobe**
- Treat fashion as social history: jackets, tracksuits, denim, hats, sneakers, jewelry, belts, glasses, era-specific silhouettes.
- Render logos and details only when plausible and necessary.
- Style should feel personally assembled.

**Lighting**
- Natural daylight, open shade, or restrained direct flash.
- Skin tone and clothing color must remain accurate.
- Avoid elaborate studio effects.

**Color / monochrome**
- Natural saturated street color or straightforward black-and-white.
- Moderate film grain and period print character when appropriate.
- Keep colors grounded in actual clothing and urban environment.

**Mandatory signature locks**
- Composition: eye-level posed street portrait with fashion + neighborhood context readable.
- Camera: 35–60mm-equivalent conversational street perspective.
- Light: daylight/open shade or restrained direct flash.
- Tone: grounded film-like color or plainspoken monochrome.
- Behavior: chosen stance, swagger, friendship, direct recognition.

**Technical recipe**
- 35–60mm equivalent; f/5.6–f/11 behavior.
- Full-body when footwear and silhouette matter.
- Keep at least one clear neighborhood anchor.
- Avoid shallow bokeh.
- Drift repair: if it looks editorial, simplify pose and restore ordinary street specificity.


**Emotional register**
Warm, cool, proud, social, youthful, neighborhood-centered, historically observant.

**Avoid**
- paparazzi distance
- generic “urban grit”
- exaggerated gang stereotypes
- luxury editorial polish
- shallow focus that erases place
- artificial graffiti clutter

> **AI production directive:** Create an eye-level street portrait based on mutual recognition between camera and subject. Give the person or group enough space for clothing, footwear, stance, friendship, and neighborhood context to register clearly. Use ordinary daylight or restrained flash, natural street color or plainspoken monochrome, and a real-feeling urban backdrop such as a stoop, sidewalk, storefront, schoolyard, transit entrance, brick wall, or parked car. Let style and body language feel chosen by the subjects. The frame should preserve everyday self-presentation as cultural history without turning the neighborhood into a stereotype.

---

## VDL-035 — RAW ELEGANCE

### HUMAN-ONLY RESEARCH LAYER
**Source studied:** Peter Lindbergh  
**Research basis:** Gagosian — artist profile and exhibition materials  
https://gagosian.com/artists/peter-lindbergh/

### RESEARCH SYNTHESIS
The transferable mechanism rejects over-calculated glamour in favor of apparent truthfulness. High-fashion subjects are photographed with minimal retouching, natural expression, windswept hair, simple clothing, industrial streets, beaches, open landscapes, or sparse sets. Black-and-white work is especially central: strong but natural contrast, visible skin, unforced movement, and a cinematic sense of fleeting life. The image can remain unmistakably fashion-oriented while refusing cosmetic perfection.

### AI-FACING EXECUTION LAYER

**Core intent:** Create fashion imagery that feels emotionally and physically real: elegant because the person is present, not because every surface is perfected.

**Subject direction**
- Encourage walking, turning, laughing, staring, resting, hands in pockets, wind in hair, coat movement, or simple stillness.
- Keep expression natural and unscripted.
- Avoid exaggerated model poses.

**Wardrobe**
- Strong simple pieces: white shirt, black tailoring, trench, coat, knit, slip dress, workwear-influenced fashion.
- Let clothing move with the body.
- Styling can be high fashion but should not overpower personality.

**Locations**
- Industrial streets, plain studios, beaches, waterfronts, sparse city exteriors, backstage-like spaces.
- Environments should add texture without looking lavish.

**Lighting**
- Natural daylight, overcast, directional window light, or simple studio light.
- Preserve skin texture and under-eye detail.
- Avoid beauty glow and elaborate multi-light sheen.

**Monochrome**
- High-contrast black-and-white with open skin detail.
- Strong blacks without destroying texture.
- Fine grain, slightly cinematic print quality.
- Color can be used, but keep it restrained and natural.

**Camera**
- Medium or full-body fashion framing.
- Normal-to-short-telephoto perspective.
- Moderate depth of field.
- Let motion remain slightly imperfect.

**Retouching**
- Minimal.
- Keep pores, lines, hair flyaways, fabric creases, and believable anatomy.
- Do not reshape the body toward artificial perfection.

**Mandatory signature locks**
- Composition: fashion-aware but unforced, with person more important than set.
- Camera: 50–105mm-equivalent portrait/fashion behavior.
- Light: natural or uncomplicated directional light.
- Tone: strong truthful monochrome or restrained natural color.
- Behavior: walking, turning, staring, resting, wind, real expression.

**Technical recipe**
- 50–105mm equivalent; f/2.8–f/5.6 behavior.
- Preserve skin texture and hair flyaways.
- Use simple wardrobe silhouettes.
- Let slight motion imperfection remain.
- Drift repair: if it becomes luxury polish, reduce retouching and add physical/environmental looseness.


**Emotional register**
Unforced, intelligent, modern, windswept, strong, humane, elegant.

**Avoid**
- plastic skin
- ornate luxury sets
- rigid glamour poses
- hyper-saturated color
- perfect hair placement
- excessive digital compositing

> **AI production directive:** Create an elegant fashion photograph whose power comes from an unforced person rather than cosmetic perfection. Use simple clothing, natural movement, visible skin texture, wind or environmental motion, restrained locations, and daylight or uncomplicated directional light. Favor strong black-and-white with truthful detail and minimal retouching. Let hair move, fabric crease, posture relax, and expression remain psychologically present. The image should still understand fashion, but it should feel discovered in life rather than engineered in a beauty laboratory.

---

## VDL-036 — ARCHIVE OF SELF

### HUMAN-ONLY RESEARCH LAYER
**Source studied:** Lyle Ashton Harris  
**Research basis:** Whitney Museum of American Art — *Ektachrome Archives*; artist project materials  
https://whitney.org/collection/works/57226

### RESEARCH SYNTHESIS
The photographic language moves between self-portrait, performance, family/community archive, snapshot, slide, fashion, and conceptual staging. Identity is intentionally unstable: gender presentation, race, sexuality, class, celebrity, friendship, family, masks, costume, and performance can overlap. Saturated slide-film color and intimate archival images can sit beside more deliberate staged self-images. The transferable mechanism is using the personal archive as both evidence and performance.

### AI-FACING EXECUTION LAYER

**Core intent:** Create an image that feels simultaneously personal, archival, performative, and self-questioning.

**Mode selection**
Choose one of two connected modes:
1. **Archive mode:** intimate slide/snapshot image from a social, family, studio, travel, or backstage life.
2. **Performance mode:** deliberate self-staging using costume, mask, makeup, pose, or symbolic persona.

**Composition**
- Archive mode may use casual crops, flash, crowded social framing, mirrors, or domestic space.
- Performance mode should be more deliberate: frontal portrait, mirror structure, staged body, symbolic object, or constructed persona.
- Preserve the feeling that both modes belong to the same life-world.

**Color / material**
- Favor saturated reversal-film or slide-film character: rich reds, blues, skin, and deep blacks.
- Slight grain and projected-slide luster are appropriate.
- Do not imitate generic Instagram filters.

**Identity construction**
- Clothing, makeup, wigs, masks, gesture, friends, family, and cultural references can act as identity layers.
- Avoid reducing identity to one obvious symbol.
- Contradiction is valuable: masculine/feminine, private/public, serious/playful, glamorous/ordinary.

**Lighting**
- Direct flash, available interior light, daylight, or simple staged studio light depending on mode.
- Keep the technical approach consistent with the imagined source: snapshot, slide, or performed portrait.

**Mandatory signature locks**
- Composition: either intimate archive snapshot or deliberate identity performance—never a vague midpoint.
- Camera: 35–55mm snapshot behavior or 70–100mm staged portrait behavior.
- Light: direct flash/available light for archive; simple controlled light for performance.
- Tone: saturated slide/reversal-film character.
- Behavior: identity layered through clothing, gesture, relation, mask, or persona.

**Technical recipe**
- Archive mode: 35–55mm equivalent, f/2.8–f/8.
- Performance mode: 70–100mm equivalent, f/5.6–f/11.
- Preserve rich reds/blues and deep blacks.
- Drift repair: if the image feels generically retro, make the identity-performance logic more specific.


**Emotional register**
Personal, unstable, intimate, performative, archival, self-aware.

**Avoid**
- generic drag/fashion imagery without personal context
- polished branding photography
- over-explained identity symbolism
- uniform treatment that erases the distinction between archive and performance
- modern digital perfection

> **AI production directive:** Build the image as part of a living personal archive in which identity is both remembered and performed. Decide whether the frame is an intimate slide-like snapshot or a deliberately staged persona, then use saturated film color, direct or available light, clothing, gesture, mirrors, masks, friends, family, or private surroundings to create layered self-presentation. Allow contradictions in gender, glamour, class, seriousness, and intimacy to remain visible. The photograph should feel like evidence from a life that is actively constructing its own visual history.

---

## VDL-037 — GEOMETRIC INSTINCT

### HUMAN-ONLY RESEARCH LAYER
**Source studied:** Henri Cartier-Bresson  
**Research basis:** Fondation Henri Cartier-Bresson — biography and *The Decisive Moment* materials  
https://www.henricartierbresson.org/en/hcb/

### RESEARCH SYNTHESIS
The core is not simply “candid street photography.” It is the instantaneous alignment of human action with rigorous geometry. Stairs, walls, windows, shadows, railings, roads, puddles, signs, and architectural planes create a formal stage; a gesture, stride, glance, bicycle, jump, or passing figure completes the design for a fraction of a second. The camera remains light, unobtrusive, and responsive. Natural light and black-and-white clarity support the structure rather than calling attention to technique.

### AI-FACING EXECUTION LAYER

**Core intent:** Capture the instant when spontaneous human action completes an already meaningful geometric composition.

**Composition**
- Search for strong lines, curves, diagonals, frames-within-frames, repeating windows, staircases, fences, shadows, reflections, and architectural planes.
- Establish the visual geometry first.
- Place or catch the human figure at a point where action resolves the design.
- Use foreground and background relationships deliberately.

**Timing**
- The action should feel fraction-of-a-second specific.
- Favor mid-stride, leap, glance, hand gesture, bicycle movement, crossing, or fleeting alignment.
- Avoid generic “person walking down street” timing.

**Camera / lens**
- Small-camera feeling.
- Normal to moderately wide perspective.
- Eye-level or naturally found viewpoint.
- Deep enough focus to preserve geometric context.
- Avoid telephoto voyeurism.

**Lighting**
- Available natural light.
- Use shadows, reflections, rain, windows, or bright sun when they strengthen geometry.
- No visible studio or flash aesthetic unless the scene naturally demands it.

**Monochrome**
- Clear black-and-white.
- Moderate contrast.
- Fine grain.
- Keep detail in architecture and people.
- Avoid dramatic post-processing that overwhelms timing.

**Human behavior**
- People should appear engaged in real activity, not fashion-directed.
- The image can be humorous, tender, ironic, mysterious, or simply formally satisfying.

**Mandatory signature locks**
- Composition: architecture/geometry established first; human action completes it.
- Camera: 28–50mm-equivalent small-camera perspective.
- Light: available natural light only.
- Tone: restrained monochrome with clear spatial lines.
- Behavior: real action caught at exact timing point.

**Technical recipe**
- 28–50mm equivalent; f/8–f/16 behavior when possible.
- Keep geometry and human figure both readable.
- Use shadows/reflections only when they reinforce structure.
- Drift repair: if the image looks staged, simplify action and strengthen environmental geometry.


**Emotional register**
Alert, elegant, spontaneous, observant, restrained, exact.

**Avoid**
- staged-looking action
- excessive motion blur
- extreme wide-angle distortion
- shallow-focus street portraiture
- overprocessed skies
- geometry with no meaningful human moment

> **AI production directive:** Build a natural street or public-space composition around strong geometry—lines, stairs, windows, shadows, reflections, railings, walls, or curves—then capture the exact fraction of a second when a human gesture or movement completes that geometry. Use a small-camera, eye-level feeling, natural light, normal-to-moderately-wide perspective, and enough depth of field to keep spatial relationships clear. The photograph should look effortless, but its timing and formal alignment must be exact. Do not stage spectacle; let ordinary life briefly become perfect structure.

---

## VDL-038 — SITE OF MEMORY

### HUMAN-ONLY RESEARCH LAYER
**Source studied:** Nona Faustine  
**Research basis:** Brooklyn Museum — *White Shoes*  
https://www.brooklynmuseum.org/opencollection/exhibitions/3431/

### RESEARCH SYNTHESIS
The body is placed directly into historically charged public sites so that contemporary presence confronts architecture, monuments, streets, waterfronts, and landscapes carrying hidden or suppressed histories. The staging can be simple and severe: a body, a location, a small symbolic object or garment, and an unambiguous relationship between person and site. Vulnerability and command coexist. The transferable engine is site-specific historical confrontation, not generic urban portraiture.

### AI-FACING EXECUTION LAYER

**Core intent:** Use a human figure to activate the hidden historical meaning of a real or realistically constructed place.

**Location first**
- Select a site with specific historical, social, labor, racial, civic, or memorial significance.
- Architecture, street grid, waterfront, government building, monument, ruin, market site, or landscape should remain recognizable.
- Do not choose a location only because it looks dramatic.

**Subject placement**
- Position the figure so body and site visibly relate.
- Frontal standing, seated, back-to-camera, or still profile can work.
- Keep gesture spare.
- The body may appear vulnerable, exposed, ceremonial, or resolute.

**Symbolic element**
- One repeated garment, shoe, cloth, object, or color can function as a visual key.
- The symbol should be simple enough to recur across multiple locations.
- Avoid prop overload.

**Composition**
- Medium-wide or wide enough to retain architecture.
- Use verticals, pavement lines, doors, columns, fences, or horizon to structure the body/site relationship.
- Do not dissolve the location into bokeh.

**Lighting**
- Natural daylight, overcast, dawn/dusk, or location-authentic light.
- Let weather and season reinforce history without becoming theatrical.

**Color / monochrome**
- Restrained documentary color or sober monochrome.
- Keep skin and architecture materially real.
- Avoid fashionable grading.

**Mandatory signature locks**
- Composition: body and historically meaningful location must both remain legible.
- Camera: 35–70mm-equivalent site-specific perspective.
- Light: authentic natural location light.
- Tone: sober color or monochrome.
- Behavior: spare, vulnerable, resolute, historically confrontational.

**Technical recipe**
- 35–70mm equivalent; f/8–f/16 behavior to preserve site detail.
- Keep landmark/site features readable.
- Use one symbolic object or garment at most.
- Avoid background blur.
- Drift repair: if it becomes travel portraiture, increase historical site dominance and reduce glamour cues.


**Emotional register**
Confrontational, vulnerable, historical, site-specific, solemn, embodied.

**Avoid**
- random landmark portraiture
- generic travel photography
- too many symbols
- glamour pose
- shallow depth that erases historical context
- artificial ruin effects

> **AI production directive:** Begin with a location carrying specific historical or civic meaning and compose the human body as an intentional counter-presence inside that site. Keep the architecture, street, waterfront, monument, or landscape recognizable; use natural light, restrained color or monochrome, and a sparse pose. Add at most one recurring symbolic garment or object. The image should create tension between present body and past site without explaining the entire history visually. The location is not background—it is the second subject.

---

## VDL-039 — SYSTEM PANORAMA

### HUMAN-ONLY RESEARCH LAYER
**Source studied:** Andreas Gursky  
**Research basis:** Museum of Modern Art — retrospective and collection notes  
https://www.moma.org/calendar/exhibitions/170  
https://www.moma.org/collection/works/88067

### RESEARCH SYNTHESIS
The signature system uses enormous scale, elevated or distant viewpoint, saturated color, dense detail, repetition, architecture, crowds, commerce, infrastructure, and digital construction to make global systems visually legible. Images often hover between photograph and abstract painting. Individuals can become units inside patterns created by shelves, windows, desks, factories, apartments, roads, stadiums, markets, landscapes, or financial spaces. Digital intervention may remove, duplicate, align, or combine elements to create a seamless reality that is more ordered than ordinary seeing.

### AI-FACING EXECUTION LAYER

**Core intent:** Turn a large human or architectural system into a vast, highly detailed visual pattern that remains believable at both macro and micro scale.

**Viewpoint**
- Elevated, distant, balcony-height, aerial-adjacent, or architecturally detached.
- Avoid intimate eye-level portrait perspective.
- The viewer should feel able to scan an entire system at once.

**Subjects / systems**
- Crowds, markets, factories, warehouses, apartment façades, offices, stadiums, retail shelves, roads, ports, production lines, landscapes altered by infrastructure.
- Repetition is essential.
- People may be small but should remain individually legible upon close inspection.

**Composition**
- Strong horizontals, grids, bands, fields, or repeating modules.
- Reduce traditional foreground/middle/background when a flat pattern is stronger.
- Or use deep panoramic layering when scale benefits.
- Keep the entire frame active.

**Color**
- Saturated but highly organized.
- Repeated colors should reinforce pattern.
- Architectural neutrals may contrast with clusters of clothing, products, signs, or vegetation.
- Avoid cinematic grading.

**Detail / focus**
- Very high resolution.
- Broad depth of field.
- Micro-detail across the frame.
- No arbitrary soft zones.

**Digital construction**
- Seamless stitching, removal of distracting elements, repeated motifs, perspective balancing, and controlled compositing are acceptable.
- Manipulation must produce a plausible hyperreality, not obvious fantasy.

**Mandatory signature locks**
- Composition: elevated/systemic viewpoint with dense repetition across the frame.
- Camera: distant 50–150mm-equivalent or stitched panoramic behavior.
- Light: even enough to reveal mass structure and micro-detail.
- Tone: saturated but organized, broad depth.
- Behavior: people/objects function as repeated units inside a system.

**Technical recipe**
- 50–150mm equivalent depending distance; f/8–f/16 behavior.
- Keep focus broad and micro-detail consistent.
- Use grids/bands/repetition as primary structure.
- Seamless compositing allowed only when visually plausible.
- Drift repair: if it becomes a drone photo, flatten the emotional viewpoint and intensify repeating system logic.


**Emotional register**
Analytical, overwhelming, detached, global, abstract, systematic, hyperreal.

**Avoid**
- shallow-focus miniaturization
- intimate emotional portraiture
- obvious copy-paste repetition
- fake aerial-drone drama
- empty vistas with no system
- low-detail backgrounds

> **AI production directive:** Create a vast, highly resolved photograph of a human, commercial, architectural, or infrastructural system from an elevated and emotionally detached viewpoint. Organize the frame through grids, bands, repetition, crowds, shelves, windows, desks, roads, or other recurring units. Maintain broad depth of field and enough micro-detail that close inspection reveals individuals and objects even while the overall image reads as abstraction. Use saturated but organized color and seamless digital construction when necessary to intensify order. The frame should feel simultaneously photographic, painterly, overwhelming, and systemic.

---

## VDL-040 — DREAMED IDENTITY

### HUMAN-ONLY RESEARCH LAYER
**Source studied:** Nadine Ijewere  
**Research basis:** Nadine Ijewere Studio — biography and monograph materials  
https://www.nadineijewere.co.uk/9553533-about  
https://www.nadineijewere.co.uk/book

### RESEARCH SYNTHESIS
The transferable language is fashion portraiture built from vivid color, dreamlike staging, nontraditional beauty, culturally specific hair and styling, strong gaze, and imaginative background design. Color can be lush without becoming chaotic. The subject’s features are not normalized toward one beauty standard; hair texture, skin tone, face shape, clothing, and cultural styling are treated as primary visual strengths. Sets may be soft, painterly, floral, graphic, or surreal while remaining fashion-legible.

### AI-FACING EXECUTION LAYER

**Core intent:** Create a vibrant fashion portrait that treats distinctive identity, hair, skin, styling, and color as the source of beauty rather than something to normalize.

**Casting / subject treatment**
- Preserve distinctive facial structure, skin tone, hair texture, body shape, and cultural styling.
- Do not homogenize toward conventional beauty-template proportions.
- Direct gaze may be fierce, calm, playful, or dreamy.

**Hair / beauty**
- Hair is a major compositional element: braids, curls, sculptural natural hair, elaborate styling, beads, wraps, or culturally specific treatments.
- Makeup should complement skin and color palette rather than mask features.
- Retouch without erasing texture.

**Color**
- Use a planned vivid palette.
- Coordinate background, garment, makeup, hair accessories, and props.
- Saturation may be high, but skin must remain believable and dimensional.
- Pastel dreaminess and intense jewel tones can both work depending on concept.

**Set**
- Painted or gradient backgrounds, florals, fabric, soft sculptural forms, simple surreal props, graphic color blocks.
- Keep the set imaginative but not more important than the person.

**Lighting**
- Soft-to-crisp fashion light with excellent skin rendering.
- Gentle shadow or color separation.
- Avoid hard light that destroys subtle skin tone unless deliberately graphic.

**Composition**
- Close portrait, bust, three-quarter, or full-body fashion frame.
- Strong silhouette and gaze.
- Allow asymmetry and negative space when it enhances dreamlike quality.

**Mandatory signature locks**
- Composition: fashion portrait centered on distinctive identity, hair, skin, and color design.
- Camera: 70–105mm-equivalent portrait behavior.
- Light: soft-to-crisp fashion light optimized for skin nuance.
- Tone: coherent vivid palette, saturated but controlled.
- Behavior: poised, imaginative, culturally specific.

**Technical recipe**
- 70–105mm equivalent; f/4–f/8 behavior.
- Coordinate hair, garment, background, and makeup within one palette.
- Keep face/eyes at highest local sharpness.
- Drift repair: if it becomes generic colorful beauty, make hair/identity styling more specific and simplify set gimmicks.


**Emotional register**
Vivid, inclusive, youthful, imaginative, poised, culturally specific, aspirational.

**Avoid**
- whitening or flattening dark skin
- generic “diversity” casting with no visual specificity
- rainbow color without palette discipline
- plastic beauty retouching
- conventional hair normalization
- set design that swallows the face

> **AI production directive:** Create a vivid fashion portrait in which distinctive facial features, skin tone, hair texture, culturally specific styling, and personal presence are treated as the central beauty language. Build a coherent color palette across background, clothing, makeup, hair, and props; use dreamlike or graphic set design with disciplined saturation; and light the subject so skin retains depth and nuance. Preserve texture and individuality. The image should feel imaginative and fashion-forward while refusing to normalize the person toward a single conventional beauty template.

---

## VDL-041 — PLAYFUL PROVOCATION

### HUMAN-ONLY RESEARCH LAYER
**Source studied:** Ellen von Unwerth  
**Research basis:** Fotografiska — *Devotion! 30 Years of Photographing Women*; Fahey/Klein Gallery — *Bombshell*  
https://newyork.fotografiska.com/en/exhibitions/devotion-30-years-of-photographing-women  
https://www.faheykleingallery.com/exhibitions/ellen-von-unwerth3

### RESEARCH SYNTHESIS
The style is sensual fashion photography powered by play, movement, humor, cinematic scenarios, female agency, and spontaneous performance. Subjects flirt, laugh, run, dance, tease, hide, reveal, or inhabit invented personas. The images often feel like frames from a mischievous story rather than static fashion plates. Strong exposure, flash, motion, elaborate hair and makeup, pin-up references, black-and-white or exuberant color, and a slightly chaotic social energy create a world in which the subject is an active instigator.

### AI-FACING EXECUTION LAYER

**Core intent:** Create a sensual fashion story driven by movement, humor, self-directed performance, and mischievous energy rather than passive display.

**Subject direction**
- Give the subject a persona and an action.
- Encourage laughing, dancing, running, teasing, turning, jumping, crawling, hiding, peeking, eating, dressing, undressing, or interacting with friends/props.
- Expressions should feel alive and knowing.
- The subject controls the game.

**Narrative**
- Construct a small cinematic scenario: backstage escapade, hotel mischief, dressing-room drama, party aftermath, playful pin-up, roadside adventure, decadent picnic, theatrical bedroom.
- Leave the story unresolved.
- Use props that invite action.

**Lighting**
- Direct flash, strong exposure, crisp daylight, theatrical interior light, or high-energy fashion lighting.
- B&W can be punchy and grainy; color can be vivid and glossy.
- Light should support movement rather than freeze the image into solemn perfection.

**Composition**
- Dynamic crops.
- Tilted or off-center frames are acceptable.
- Let fabric, limbs, hair, props, and secondary people create motion.
- Keep fashion readable even when energy is high.

**Styling**
- Lingerie, tailoring, pin-up silhouettes, heels, playful costumes, bold makeup, elaborate hair, accessories, theatrical fashion.
- Sensuality should feel chosen and active.

**Mandatory signature locks**
- Composition: dynamic fashion story frame with action and character.
- Camera: 35–70mm-equivalent close fashion-story perspective.
- Light: direct flash, crisp daylight, or theatrical interior light.
- Tone: punchy monochrome or vivid glossy color.
- Behavior: subject instigates the action—teasing, laughing, running, dancing, hiding, interacting.

**Technical recipe**
- 35–70mm equivalent; f/2.8–f/8 behavior.
- Use dynamic crops and visible motion without losing clothing.
- Props must invite action.
- Drift repair: if it becomes passive boudoir, give the subject a stronger action and more control of the scene.


**Emotional register**
Mischievous, sexy, humorous, energetic, theatrical, self-directed, alive.

**Avoid**
- passive objectification
- frozen solemn fashion poses
- sterile luxury
- beauty retouching that removes energy
- generic boudoir softness
- sensuality with no character or story

> **AI production directive:** Give the subject a mischievous persona and something active to do inside a small cinematic fashion scenario. Use movement, laughter, direct flash or strong fashion light, dynamic cropping, expressive hair and clothing, playful props, and a sense that the subject is teasing the camera rather than submitting to it. Keep sensuality self-directed, humorous, and energetic. The frame should feel like the liveliest instant from a larger escapade—stylish enough for fashion, spontaneous enough to feel alive, and never merely posed for admiration.

---

## VDL-042 — REGAL PATTERN SOVEREIGNTY

### HUMAN-ONLY RESEARCH LAYER
**Source studied:** Kehinde Wiley  
**Note:** This source is primarily a painter; the visual system is translated here into photographic staging principles.  
**Research basis:** Kehinde Wiley Studio — biography and practice  
https://kehindewiley.com/about/

### RESEARCH SYNTHESIS
The defining visual architecture places contemporary people of color into the compositional authority historically associated with aristocratic, heroic, or canonical portraiture. Monumental pose, direct presence, contemporary clothing, saturated color, and ornate floral/damask patterning create a deliberate collision between present-day subject and inherited visual power. Pattern may refuse to stay behind the figure; leaves, vines, and ornament can visually overlap or surround the body, challenging normal foreground/background hierarchy.

### AI-FACING EXECUTION LAYER

**Core intent:** Create a monumental contemporary portrait where the subject occupies regal visual authority and ornate pattern actively surrounds the figure.

**Subject / pose**
- Strong, upright, heroic, seated-regal, equestrian-inspired, or ceremonially composed posture.
- Direct gaze or elevated self-possession.
- Contemporary clothing should remain visible and specific.
- The subject must feel like the owner of the portrait, not a costume model.

**Background**
- Dense floral, botanical, damask, textile, or ornamental pattern.
- Use saturated repeating motifs.
- Permit selected leaves, flowers, or vines to cross in front of the body, creating ambiguous figure/ground depth.
- Pattern must remain deliberate, not wallpaper filler.

**Composition**
- Monumental vertical portrait.
- Low or neutral camera height depending desired stature.
- Classical balance and strong silhouette.
- Full or three-quarter body often works best.

**Lighting**
- Polished portrait light with clear skin modeling.
- Enough separation to keep face and clothing legible against pattern.
- Avoid moody low-key treatment that weakens ornamental color.

**Color**
- Saturated jewel tones, greens, reds, blues, golds, florals.
- Coordinate clothing with the background while preserving contrast.
- Keep skin natural and rich.

**Finish**
- Extremely clean edges except where pattern intentionally crosses figure.
- Painterly richness may be suggested through surface and pattern, but the subject should remain photographically convincing.

**Mandatory signature locks**
- Composition: monumental contemporary figure against dense ornamental pattern.
- Camera: 60–100mm-equivalent portrait perspective, neutral or slight low angle.
- Light: polished skin-focused portrait light.
- Tone: saturated jewel colors with intentional pattern/figure overlap.
- Behavior: regal, self-possessed, contemporary.

**Technical recipe**
- 60–100mm equivalent; f/5.6–f/11 behavior.
- Keep facial plane clearly separated from pattern.
- Allow 5–15% of ornamental motifs to overlap figure edges.
- Drift repair: if it becomes wallpaper portraiture, strengthen figure authority and foreground/background competition.


**Emotional register**
Regal, contemporary, monumental, ornate, confident, revisionary.

**Avoid**
- generic throne-room clichés
- random baroque props
- historical costume unless requested
- weak floral wallpaper
- subject disappearing into pattern
- passive pose

> **AI production directive:** Present a contemporary subject with the visual authority of a monumental state or aristocratic portrait while keeping their present-day clothing and identity intact. Place them against an intensely patterned floral, botanical, textile, or damask field and allow selected ornamental elements to cross in front of the figure so background and foreground compete. Use polished portrait light, saturated jewel color, strong silhouette, and a self-possessed pose. The result should feel regal and revisionary without requiring historical costume: contemporary presence occupying inherited visual power.

---

## VDL-043 — HYPERREAL SATIRE

### HUMAN-ONLY RESEARCH LAYER
**Source studied:** Martin Parr  
**Research basis:** Martin Parr Studio — introduction and technical FAQ; Magnum Photos profile  
https://martinparr.com/introduction/  
https://martinparr.com/faq/

### RESEARCH SYNTHESIS
The style turns ordinary leisure, tourism, consumption, food, bodies, beaches, shopping, and social behavior into bright, funny, uncomfortable social evidence. Garish color, unusual viewpoints, close observation, macro detail, ring flash or direct flash, crowded frames, and deliberately unflattering juxtapositions can make reality look almost fictional. The humor is observational rather than dependent on staged jokes. Saturation is achieved through film/flash logic rather than through generic psychedelic post-processing.

### AI-FACING EXECUTION LAYER

**Core intent:** Make ordinary consumer and leisure behavior look visually excessive enough to become social satire without inventing a fantasy world.

**Subject matter**
- Beaches, resorts, buffets, fairs, tourism, shopping, food, souvenirs, queues, parties, public leisure, signage, consumer goods.
- Look for contradictions between aspiration and physical reality.
- Keep scenes recognizably ordinary.

**Composition**
- Use close, strange, or slightly intrusive viewpoints.
- Crop bodies, food, hands, objects, and signs in ways that heighten visual absurdity.
- Let crowded frames remain crowded.
- Seek accidental juxtapositions and social gestures.

**Lighting**
- Direct flash or ring-flash-like fill in daylight.
- Hard, clear illumination.
- Flatten some depth when it makes color and surfaces more graphic.
- Avoid soft lifestyle lighting.

**Color**
- Very high saturation.
- Strong reds, blues, yellows, skin tones, plastic colors, food colors, beach accessories.
- Preserve the look of saturated color film plus flash.
- Do not use neon sci-fi grading.

**Lens / detail**
- Normal, moderately wide, or macro-close perspective.
- High detail in food, skin, objects, signage, and material excess.
- Do not beautify texture.

**Mandatory signature locks**
- Composition: ordinary leisure/consumer scene observed from close, awkward, or revealing viewpoint.
- Camera: 28–60mm or macro-close perspective.
- Light: hard daylight fill, direct flash, or ring-flash-like clarity.
- Tone: highly saturated, materially blunt color.
- Behavior: unstaged social gesture; humor emerges from reality.

**Technical recipe**
- 28–60mm equivalent; macro where detail itself is the subject.
- f/8–f/16 behavior in bright/flash scenes.
- Keep food, skin, signage, plastic, and objects highly detailed.
- Drift repair: if it becomes colorful street photography, push closer to a revealing social/material contradiction.


**Emotional register**
Funny, critical, observant, excessive, awkward, democratic, socially specific.

**Avoid**
- mean-spirited caricature
- staged comedy
- cinematic glamour
- tasteful muted color
- shallow bokeh
- fantasy consumer environments

> **AI production directive:** Observe an ordinary scene of leisure, tourism, shopping, food, or consumption from a close and slightly unusual viewpoint. Use hard flash or ring-flash-like daylight fill, saturated film-like color, unapologetic material detail, crowded framing, and real social gestures. Look for visual contradictions, awkward juxtapositions, excess, aspiration, and humor already present in the scene rather than staging a joke. The image should be bright, funny, uncomfortable, and socially revealing while remaining unmistakably grounded in everyday reality.

---

## VDL-044 — POP ICON RECODE

### HUMAN-ONLY RESEARCH LAYER
**Source studied:** Awol Erizku  
**Research basis:** The Metropolitan Museum of Art — *Malcolm x Freestyle (Pharaoh's Dance)*; Aperture — *How Awol Erizku Is Building a Visual Multiverse*  
https://www.metmuseum.org/art/collection/search/890566  
https://aperture.org/editorial/how-awol-erizku-is-building-a-visual-multiverse/

### RESEARCH SYNTHESIS
The visual engine is cultural recoding: Black subjects, symbols, art-historical structures, hip-hop language, ancient references, objects, flowers, sculpture, still life, and contemporary style are combined to create a new iconography rather than simply inserting a subject into an old picture. Portraits can feel regal, minimal, pop, conceptual, or surreal. Still lifes function like coded constellations in which each object has layered cultural meaning. The transferable rule is to build a coherent Black-centered symbolic lexicon with the visual confidence of both fine art and contemporary editorial photography.

### AI-FACING EXECUTION LAYER

**Core intent:** Create a culturally coded contemporary image that elevates the subject or still life into an icon through deliberate references, symbols, color, and visual recontextualization.

**Concept**
- Start with one clear cultural or symbolic thesis.
- Choose a small network of references: contemporary music, diaspora, ancient history, everyday Black visual culture, fine-art composition, fashion, spirituality, or language.
- Recode rather than merely quote: the final image must feel new.

**Portrait mode**
- Present the subject with calm, confident, regal presence.
- Use a clean or boldly colored background.
- Clothing, grooming, flowers, sculpture, jewelry, or one symbolic object may carry the conceptual layer.
- Pose should feel iconic rather than casual.

**Still-life mode**
- Arrange books, sculptural objects, flowers, souvenirs, tools, records, masks, found objects, or contemporary cultural symbols into a deliberate constellation.
- Each object should contribute a different layer of meaning.
- Use spacing and color as carefully as object selection.

**Color**
- Strong, contemporary, highly controlled.
- Solid backgrounds, rich blacks, orange, red, blue, gold, green, or other saturated fields can work.
- Limit the palette enough to keep symbolic elements legible.

**Lighting**
- Clean studio light or crisp naturalistic light.
- Use shadow deliberately to give objects and faces sculptural weight.
- Avoid generic beauty glow.

**Composition**
- Graphic and intentional.
- Centered icon, formal still life, or balanced asymmetry.
- Negative space is useful when it increases symbolic clarity.

**Mandatory signature locks**
- Composition: iconic portrait or coded still life built around one cultural thesis.
- Camera: 50–100mm-equivalent clean studio perspective.
- Light: crisp sculptural studio or naturalistic light.
- Tone: strong controlled contemporary color.
- Behavior: calm, regal, symbolic, culturally self-defined.

**Technical recipe**
- 50–100mm equivalent; f/5.6–f/11 behavior.
- Limit symbol network to 3–6 meaningful elements.
- Use negative space to keep coding legible.
- Drift repair: if it becomes generic Afrofuturism/pop art, reduce symbols and reconnect every element to the core thesis.


**Emotional register**
Regal, coded, contemporary, cerebral, culturally self-defined, pop-aware.

**Avoid**
- random cultural symbols
- direct one-to-one copying of famous paintings
- generic Afrofuturist neon
- cluttered references no viewer can parse
- fashion styling with no conceptual thesis

> **AI production directive:** Build the image around one clear cultural thesis and a tightly selected set of symbols. Present the subject or still life with iconic compositional authority, clean or saturated color fields, crisp controlled light, and objects whose meanings connect contemporary culture, history, style, spirituality, or diaspora. Recode familiar visual structures instead of merely reproducing them. Keep the palette and object count disciplined so the symbolism remains legible. The result should feel like a new visual lexicon: contemporary, culturally self-defined, and immediately iconic.

---

## VDL-045 — EDITORIAL METAMORPHOSIS

### HUMAN-ONLY RESEARCH LAYER
**Source studied:** Steven Meisel  
**Research basis:** Vogue — retrospective reporting and interviews on his image-making, collaboration, movement, character, and fashion history  
https://www.vogue.com/slideshow/1993-steven-meisel-photos-british-vogue-november-2022  
https://www.vogue.com/article/steven-meisel-zara-collaboration-collection

### RESEARCH SYNTHESIS
The most transferable quality is not one fixed lighting setup. It is editorial transformation. Fashion stories can become cinematic narratives, character studies, historical quotations, raw subculture, polished studio portraiture, paparazzi simulation, glamour, beauty, or social satire. Models are directed into characters through movement, expression, styling, hair, makeup, casting, and a strong conceptual frame. Deep knowledge of fashion and image history supports the transformations. The consistent thread is total editorial commitment: every visual choice belongs to the story.

### AI-FACING EXECUTION LAYER

**Core intent:** Transform the subject into the protagonist of a fully coherent fashion narrative rather than applying one repeated visual recipe.

**Step 1 — Declare the editorial world**
Before prompting, define:
- era or temporal reference
- social world or subculture
- character archetype
- emotional tone
- location/set
- camera language
- styling logic
- beauty/hair logic
- color/monochrome logic

Do not proceed until these agree.

**Character direction**
- Give the model a role, not just a pose.
- Encourage movement, self-expression, attitude, intimacy, elegance, aggression, awkwardness, or stillness according to the chosen world.
- Hair and makeup may radically transform the same face from story to story.

**Composition**
- Adapt to concept: clean studio portrait, cinematic group scene, documentary-like street frame, close beauty crop, theatrical narrative, or formal fashion tableau.
- Maintain publication-level hierarchy and precision regardless of mode.

**Lighting**
- No single default.
- Select light that belongs to the narrative: hard flash, large soft source, beauty light, daylight, noir, bright studio, paparazzi-like exposure.
- Lighting must never contradict the story.

**Fashion**
- Clothing should be read in relation to character and era.
- Use styling, pose, casting, and expression to make fashion tell the story rather than merely display garments.

**Finish**
- High production precision.
- Retouching should support the chosen visual language.
- Historical references should feel researched, not costume-shop approximate.

**Mandatory signature locks**
- Composition: must obey a declared editorial world; no default generic fashion layout.
- Camera: chosen specifically for the concept.
- Light: chosen specifically for the concept.
- Tone: chosen specifically for era/story.
- Behavior: subject performs a character, not a pose.

**Technical recipe**
- Before generating, explicitly set: era, social world, character, location, camera language, light, styling, hair/makeup, finish.
- Use focal length and depth to support that world rather than a house default.
- Keep all departments visually consistent.
- Drift repair: if any element feels from a different story, change that element instead of averaging the concept.


**Emotional register**
Transformative, fashion-literate, character-driven, narrative, controlled, versatile.

**Avoid**
- one generic “luxury editorial” look
- fashionable styling with no story
- random historical references
- beautiful lighting that contradicts the character
- static catalog posing
- concept drift between set, hair, makeup, wardrobe, and camera

> **AI production directive:** Begin by defining a complete editorial world—era, character, social context, emotional tone, location, styling, hair, makeup, camera language, and light—then make every visual decision obey that world. Direct the subject as a character rather than a clothes hanger. Choose composition and lighting specifically for the narrative, whether polished studio, documentary street, cinematic tableau, close beauty, flash-driven immediacy, or formal portraiture. Maintain high fashion precision while allowing dramatic transformation between stories. The signature is not one surface treatment; it is total coherence of concept, character, fashion, and photographic execution.

---

## VDL-046 — INTIMATE INDUSTRY

### HUMAN-ONLY RESEARCH LAYER
**Source studied:** LaToya Ruby Frazier  
**Research basis:** LaToya Ruby Frazier Studio — biography and publications on collaborative social documentary  
https://latoyarubyfrazier.com/about/  
https://latoyarubyfrazier.com/publications/

### RESEARCH SYNTHESIS
The photographic system joins family, community, labor, health, environmental conditions, deindustrialization, and social history through long-term collaborative storytelling. The photographer is not outside the subject matter; domestic life and public systems are allowed to occupy the same archive. Black-and-white portraiture can be intimate and physically close, while factories, hospitals, water systems, streets, homes, unions, and landscapes provide structural context. Serial work and collaboration matter: a single heroic image is less important than a body of evidence built with people over time.

### AI-FACING EXECUTION LAYER

**Core intent:** Connect intimate human life to the larger systems—industry, labor, health, environment, infrastructure, policy, or community history—that shape it.

**Story structure**
- Whenever possible, think in a sequence rather than one isolated image.
- Include portrait, domestic detail, environmental context, institutional or industrial evidence, and community interaction.
- A single frame should still hint at both personal and structural realities.

**Subject relationship**
- Use collaborative, respectful portraiture.
- Let people appear in their homes, workplaces, neighborhoods, clinics, union halls, community spaces, or sites of environmental significance.
- Avoid anonymous victim imagery.

**Composition**
- Direct medium portraits, family arrangements, mirrors, domestic spaces, industrial landscapes, public infrastructure.
- Keep environmental details sharp enough to function as evidence.
- Use repeated locations or family members across a series.

**Lighting**
- Available or naturalistic light.
- Direct flash may be used when it feels embedded in documentary practice.
- Preserve skin, surfaces, and industrial texture honestly.

**Monochrome / color**
- Strong documentary black-and-white is primary.
- Rich grays, substantial blacks, direct facial rendering.
- Color may be used when environmental evidence depends on it, but keep it factual.

**Material detail**
- Factories, pipes, water, smoke, machinery, roads, medical spaces, homes, family photographs, work clothes, tools, signs, documents.
- Do not add industrial props for aesthetics.

**Mandatory signature locks**
- Composition: person/community + structural system visible in the same frame or sequence.
- Camera: 35–70mm-equivalent documentary perspective.
- Light: available or naturalistic.
- Tone: strong black-and-white or factual color.
- Behavior: collaborative, grounded, socially specific.

**Technical recipe**
- 35–70mm equivalent; f/5.6–f/11 behavior.
- Include at least one concrete system clue: machinery, pipe, clinic, road, document, workplace, utility, landscape alteration.
- Avoid ruin-only imagery.
- Drift repair: if it becomes industrial aesthetics, re-center the person/system relationship.


**Emotional register**
Intimate, structural, collaborative, persistent, socially specific, historically aware.

**Avoid**
- industrial ruin porn
- anonymous hardship
- dramatic disaster lighting
- decontextualized portraits
- heroic simplification of complicated communities
- one-off spectacle replacing sustained evidence

> **AI production directive:** Create a socially grounded documentary image that connects a specific person, family, or community to the larger material system shaping daily life. Use respectful collaborative portraiture, available-feeling light, direct composition, honest skin and surface texture, and environmental evidence such as home, workplace, infrastructure, health setting, landscape, machinery, or public space. Favor strong black-and-white when appropriate. The frame should make intimate life and structural conditions visible at the same time, avoiding both anonymous victimhood and picturesque industrial decay.

---

## VDL-047 — CRAFTED WONDER

### HUMAN-ONLY RESEARCH LAYER
**Source studied:** Tim Walker  
**Research basis:** Victoria and Albert Museum — *Tim Walker: Wonderful Things* and set-design materials  
https://www.vam.ac.uk/exhibitions/tim-walker  
https://www.vam.ac.uk/articles/working-with-tim-walker-set-design

### RESEARCH SYNTHESIS
The visual language is fantastical, but its strength comes from tactile invention rather than generic digital fantasy. Oversized props, handmade sets, painted scenery, elaborate costumes, surreal scale, fairytale logic, historic garments, flowers, creatures, strange rooms, and collaborative production design create complete worlds. Mood boards, storyboards, hair, makeup, wardrobe, set, prop, and location are developed together. The photograph should retain evidence that impossible things were physically built.

### AI-FACING EXECUTION LAYER

**Core intent:** Create a fantastical fashion world that feels handcrafted, tactile, storybook-like, and physically staged rather than generated from generic fantasy effects.

**World building**
- Begin with a simple imaginative premise: giant room, miniature person, enchanted garden, impossible household object, dream banquet, paper palace, strange woodland, theatrical museum, living still life.
- Define physical rules for the world.
- Build set, prop, wardrobe, and character around the same premise.

**Scale**
- Use intentional scale distortion: enormous doll, giant glove, tiny doorway, oversized flower, colossal furniture, room too tall, prop too large.
- Maintain believable contact shadows and physical interaction so scale feels photographed.

**Set / props**
- Favor handmade textures: painted canvas, paper, cardboard, wood, fabric, plaster, flowers, vintage objects, sculptural props.
- Imperfections may remain visible.
- Avoid smooth generic CGI.

**Wardrobe / beauty**
- Elaborate fashion, historical references, eccentric silhouettes, theatrical hair, unusual hats, crafted makeup.
- Clothing should participate in the world’s shapes and palette.

**Lighting**
- Soft theatrical light, window-like daylight, studio illumination shaped to feel magical, or location-authentic light.
- Preserve tactile surfaces.
- Avoid synthetic volumetric effects unless physically motivated.

**Color**
- Can be pastel, jewel-toned, muted fairytale, or richly theatrical.
- Choose a controlled story palette.
- Color should support materiality.

**Composition**
- Layer foreground props, character, and deep set.
- Use wide frames when scale matters.
- Leave enough space to appreciate production design.

**Mandatory signature locks**
- Composition: tactile physically staged fantasy world with coherent scale logic.
- Camera: 35–70mm-equivalent set-aware perspective.
- Light: theatrical but material-revealing.
- Tone: story-specific controlled palette.
- Behavior: subject physically interacts with constructed props/set.

**Technical recipe**
- 35–70mm equivalent; f/5.6–f/11 behavior for set depth.
- Require believable contact shadows.
- Use handmade material cues—paper, wood, cloth, painted canvas, plaster.
- Drift repair: if it looks CGI, reduce impossible detail and increase visible handcrafted materiality.


**Emotional register**
Whimsical, uncanny, romantic, theatrical, tactile, imaginative, childlike without being childish.

**Avoid**
- generic fantasy castles
- AI-looking infinite detail
- random floating particles
- plastic CGI textures
- unmotivated surreal objects
- fashion model pasted into a fantasy background

> **AI production directive:** Invent a tactile fantasy world around one clear story premise and make it feel physically constructed. Use handmade-looking sets, oversized or undersized props, painted surfaces, fabric, flowers, wood, paper, sculptural objects, elaborate fashion, and theatrical hair or makeup. Preserve contact shadows, material imperfections, and believable interaction between subject and set so the impossible feels photographed rather than rendered. Control the palette and scale logic. The image should produce wonder through craftsmanship, physical invention, and storybook staging—not through generic digital fantasy effects.

---

## VDL-048 — COSMIC BODY

### HUMAN-ONLY RESEARCH LAYER
**Source studied:** Mikael Owunna  
**Research basis:** Mikael Owunna Studio — *Infinite Essence*  
https://www.mikaelowunna.com/projects-photography-infinite-essence

### RESEARCH SYNTHESIS
The central technique turns Black bodies into luminous cosmic forms. Subjects are photographed in total darkness after being painted with fluorescent material and illuminated with a custom ultraviolet flash. Most environmental information disappears, leaving a deep black field and bodies traced by glowing dots, lines, constellations, and nebula-like marks. The body becomes simultaneously physical, celestial, spiritual, sculptural, and diasporic. The key is ultraviolet fluorescence against true darkness, not ordinary neon body paint.

### AI-FACING EXECUTION LAYER

**Core intent:** Transform the human body into a luminous cosmic figure emerging from complete darkness through fluorescent ultraviolet-responsive markings.

**Background**
- Pure or near-pure black void.
- No visible room, horizon, floor, or environmental context unless intentionally minimal.
- Darkness must feel deep enough that the luminous body appears to emerge from space.

**Body treatment**
- Apply fluorescent paint as thousands of points, star clusters, constellations, fine lines, celestial bands, or controlled cosmic patterns.
- Let paint follow anatomy without simply outlining every edge.
- Preserve substantial regions of unlit skin so the body oscillates between visible and invisible.

**Lighting**
- Simulate ultraviolet flash or ultraviolet-responsive illumination.
- Fluorescent paint should emit visible brightness while most ordinary surfaces remain dark.
- Avoid neon rim light around the entire silhouette.
- No conventional three-point studio lighting.

**Pose**
- Sculptural, expansive, curled, reaching, balanced, floating-like, or ceremonial.
- Hands and limbs should form clear constellated geometry.
- Avoid generic dance-club poses.

**Color**
- Deep black background with controlled fluorescent blue, violet, cyan, magenta, white, or limited additional hues.
- Keep color luminous but not rainbow.
- The highest brightness belongs to fluorescent markings.

**Texture**
- Paint points should vary naturally in size and density.
- Preserve skin/body dimensionality through selective fluorescence rather than visible ambient light.

**Mandatory signature locks**
- Composition: body emerges from true black void through fluorescent markings.
- Camera: 50–85mm-equivalent studio perspective.
- Light: UV-responsive fluorescence is the primary visible illumination.
- Tone: deep black + limited cosmic luminous hues.
- Behavior: sculptural, ceremonial, expansive.

**Technical recipe**
- 50–85mm equivalent; f/4–f/8 behavior.
- Keep conventional ambient exposure near-black.
- Limit fluorescent hues to 1–4 colors.
- Do not outline every contour.
- Drift repair: if it resembles neon body paint, darken ambient skin visibility and break markings into irregular constellations.


**Emotional register**
Cosmic, spiritual, ancestral, expansive, intimate, sculptural, transcendent.

**Avoid**
- Tron-like glowing outlines
- cyberpunk neon city backgrounds
- visible studio environment
- rainbow body paint
- generic starfield pasted behind the body
- full-body illumination that removes the darkness

> **AI production directive:** Place the subject in a true black visual void and reveal the body almost entirely through ultraviolet-responsive fluorescent markings. Paint the skin with constellations, star clusters, fine celestial lines, and irregular luminous points while leaving large areas of the body in darkness. Use no ordinary beauty lighting; the fluorescence itself should provide the dominant visible structure. Direct the body into a sculptural, ceremonial pose and keep the palette limited to a few cosmic luminous hues against deep black. The body should feel simultaneously human, celestial, and spiritually expansive—not like a neon costume.

---

## VDL-049 — SHADOW ABSTRACTION

### HUMAN-ONLY RESEARCH LAYER
**Source studied:** Viviane Sassen  
**Research basis:** Foam Fotografiemuseum Amsterdam — artist profile and collection materials  
https://www.foam.org/artists/viviane-sassen

### RESEARCH SYNTHESIS
The transferable visual grammar turns bodies, fashion, architecture, color, and hard shadow into ambiguous abstract shapes. Faces may be obscured by shadow, cropped, turned away, covered by objects, or subordinated to bodily geometry. Saturated color and unusual viewpoints can flatten depth until the human figure behaves like sculpture or collage. Strong sunlight, colored surfaces, negative space, and strange body arrangements create images that are fashion-aware but resist ordinary portrait legibility.

### AI-FACING EXECUTION LAYER

**Core intent:** Use hard shadow, saturated color, cropping, and body geometry to transform a fashion or human figure into an ambiguous abstract composition.

**Shadow**
- Treat shadow as an object, not merely absence of light.
- Use hard-edged sunlight or directional light that creates graphic black shapes across face, body, wall, or ground.
- Allow shadow to conceal identity.
- Align shadow with limbs, architecture, or color fields.

**Body / pose**
- Fold, crop, rotate, overlap, or partially hide limbs.
- Use unusual but physically plausible positions.
- Turn faces away, cover them, place them in shadow, or let the body become more important than recognizable identity.
- Avoid conventional fashion-model gestures.

**Color**
- Saturated but controlled.
- Strong single-color walls, fabric, clothing, skin, sky, and geometric props.
- Use 2–4 major color fields.
- Allow one color to dominate.

**Composition**
- Flatten perspective when useful.
- Use extreme crops, negative space, unexpected camera height, diagonal body sections, or partial architecture.
- Let figure and background merge into shapes.
- The image may read abstractly before it reads as a portrait.

**Lighting**
- Hard sun or hard directional studio light.
- Crisp shadow boundaries.
- Avoid soft beauty fill that destroys graphic contrast.

**Texture / finish**
- Clean, matte-to-saturated photographic color.
- Precise edges.
- Minimal digital effects; abstraction should come from camera, light, pose, and color.

**Mandatory signature locks**
- Composition: body, shadow, and saturated field must first read as abstract geometry.
- Camera: 35–85mm-equivalent depending crop and spatial flattening.
- Light: hard directional sun or hard studio source.
- Tone: 2–4 strong color fields plus deep graphic shadow.
- Behavior: folded, cropped, rotated, concealed, physically plausible.

**Technical recipe**
- 35–85mm equivalent; f/5.6–f/11 behavior.
- Keep shadow edges crisp.
- Allow face concealment when it strengthens geometry.
- Use minimal props.
- Drift repair: if it becomes ordinary colorful fashion, increase shadow/body overlap and reduce conventional portrait legibility.


**Emotional register**
Surreal, graphic, sensual, playful, ambiguous, sculptural, visually disorienting.

**Avoid**
- standard headshot visibility
- soft glamorous lighting
- generic colorful fashion background
- digital liquify/distortion
- busy prop collections
- symmetry by default

> **AI production directive:** Build the photograph from hard shadow, saturated color fields, body geometry, and selective concealment. Use crisp directional light to cast graphic black shapes across the subject and environment; crop or fold the body into unusual but plausible arrangements; obscure or turn away the face when useful; and flatten figure and background until the image first reads as abstract composition and only then as fashion or portraiture. Keep the palette disciplined and the finish clean. The strangeness should come from real light, camera placement, pose, and color rather than digital distortion.

---

# 4. NAME-FREE AGENT PROMPT ASSEMBLY TEMPLATE

Use the following template when an agent converts a user request into an image prompt.

## INPUTS

- **STYLE_ID:** one VDL style ID or branded style name
- **SUBJECT:** who/what must appear
- **ACTION:** what the subject is doing
- **SETTING:** where it happens
- **WARDROBE / OBJECTS:** required clothing, props, products, or details
- **FORMAT:** aspect ratio / orientation
- **USER LOCKS:** any facts that must not change

## ASSEMBLY ORDER

### A. CONTENT LOCK
State the subject, action, setting, required objects, required colors, identity details, and format exactly enough that they cannot be lost.

### B. VISUAL GRAMMAR
Translate the selected style block into:
1. composition
2. camera position and perspective
3. lens/depth behavior
4. lighting
5. color or monochrome
6. environment/set treatment
7. pose/motion
8. wardrobe/styling behavior
9. texture/materiality
10. finish/post-processing
11. emotional register

### C. NEGATIVE CONTROL
Add the most important items from the style’s **Avoid** section. Do not dump every generic negative prompt into every image.

### D. FINAL SOURCE-NAME CHECK
Before sending the prompt downstream:
- Search the assembled prompt for the HUMAN-ONLY source name.
- Remove it if present.
- Search for phrases such as “in the style of,” “shot by,” “inspired by,” or “like [artist].”
- Remove them.
- Confirm that the descriptive instructions still independently specify the intended look.

---

# 5. STYLE-FIDELITY PRIORITY

When prompt length is constrained, preserve information in this order:

1. **Core intent**
2. **Lighting architecture**
3. **Composition and camera relationship**
4. **Subject direction / body language**
5. **Color or tonal system**
6. **Environment / set architecture**
7. **Texture and finish**
8. **Wardrobe / props**
9. **Avoid rules**

Do not reduce a style to its branded name plus three adjectives. The descriptive grammar is the style.

---

# 6. HYBRID STYLE RULE

Only create a hybrid when the user explicitly requests one.

For a two-style hybrid:
- Choose one **PRIMARY** style that controls composition, camera, and lighting.
- Choose one **SECONDARY** style that may contribute color, texture, set language, or emotional register.
- Do not average both systems into a generic midpoint.
- State which traits come from each branded style.
- Never import the HUMAN-ONLY source names.

Example structure:

**PRIMARY:** `WITNESSED DIGNITY`  
Controls: environmental storytelling, camera relationship, naturalistic light, human presence.

**SECONDARY:** `PRIMARY SYMBOLISM`  
Contributes: limited saturated palette, graphic body paint, symbolic object discipline.

The resulting prompt should still be able to explain every major visible decision.

---

# 7. DOCUMENT MAINTENANCE RULE

When adding future styles:

1. Research the source from authoritative first-party, museum, archive, foundation, gallery, or serious critical sources.
2. Identify repeatable visual mechanisms rather than reputation-level adjectives.
3. Separate historical facts from visual inference.
4. Create a new branded style name that does not contain the source artist’s name.
5. Write the AI-facing block without relying on the source name.
6. Include:
   - core intent
   - subject treatment
   - composition
   - camera/lens behavior
   - lighting
   - tonal/color system
   - environment/set design
   - wardrobe/styling
   - texture
   - emotional register
   - avoid rules
   - one complete name-free production directive
7. Run the Style Fidelity Check.
8. Run the Source-Name Check.
9. Confirm that the style remains meaningfully distinct from existing entries.

---


# 8. QUALITY ASSURANCE STANDARD

The library is considered production-ready only when every style meets or exceeds these minimum internal scores:

- **Instruction clarity:** 8.0/10 minimum
- **Style separation:** 8.0/10 minimum
- **Technical repeatability:** 8.0/10 minimum
- **Model-drift resistance:** 8.0/10 minimum
- **Lighting specificity:** 8.0/10 minimum
- **Composition specificity:** 8.0/10 minimum
- **Camera/lens specificity:** 8.0/10 minimum
- **Color/tonal specificity:** 8.0/10 minimum
- **Subject-behavior specificity:** 8.0/10 minimum
- **Name-free downstream usability:** 8.0/10 minimum

Any future revision that causes one of these dimensions to fall below 8.0 must be strengthened before release.

---

# END OF MASTER LIBRARY

**Current style count:** 49  
**Human source count represented:** 49  
**Downstream requirement:** source names remain internal; descriptive visual systems are passed to image agents.
