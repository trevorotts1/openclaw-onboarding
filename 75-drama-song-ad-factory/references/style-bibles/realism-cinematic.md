# Realism look (owner decision D19)

Source: the hybrid One Check Chanel elevator close-up that Trevor approved on 2026-10-07 ("looks really real... that's the look we want when it switches into realism mode"). Copied verbatim from the prompts that produced it:
- image: drama-song-factory-build/qualification/hybrid-one-check-chanel/requests/img-R_elev_cu-request.json
- video: drama-song-factory-build/qualification/hybrid-one-check-chanel/requests/vid-R_elev_cu-request.json

Use: injected into every REALISM / real-mode visual prompt (hybrid real segments and any realistic style), together with the character block and the scene. The setting-specific examples inside it (office, elevator, bedroom, car) are adapted to each campaign's own locations; the rules stay the same.

This file is THE source of the `realism` and `golden-realism` render modes. `references/prompt-templates/modes/realism.json` carries the keyframe and motion paragraphs below, condensed, and carries none of the restated copies. A test asserts the mode block still carries the five phrases this recipe requires (`RECIPE_REQUIRED_PHRASES` in `style_bibles/hybrid/hybrid_bible.py`). The look text that enters a prompt exists ONCE, in the mode file; this recipe is where it came from.

## Style tag
[STYLE] Photoreal cinematic live-action look: natural skin texture, shallow depth of field, soft natural light, 35mm film grade, realistic fabrics and reflections, no cartoon, no illustration. [/STYLE]

## Keyframe image block
Photography: photoreal live-action cinematic still, shot on a full-frame camera with a 35 millimetre or 50 millimetre lens at a wide aperture, shallow depth of field, natural film grain, subtle halation, gentle contrast, true-to-life colour, realistic skin with pores and tiny natural highlights, realistic fabric weave and realistic reflections in the glasses.
Lighting: motivated natural light that fits the setting: cool daylight through office glass, cold steel reflections in the elevator, warm lamp light at home. Soft shadows, believable practical lights, no harsh studio flash, no HDR halos, no neon unless the scene asks for it.
Setting realism: modern American office lobby with glass and marble, a steel elevator with a buttons panel and a floor directory, a tidy modern bedroom, a realistic car interior; objects are clean, believable and slightly out of focus behind the character so they remain the focus.
Emotion: grounded and truthful acting, small believable micro-expressions, wet glistening eyes when the scene is painful (see the emotion note below for the D20 limit), relaxed shoulders when the scene is calm; never theatrical, never stiff. Posture and gaze are natural.
Colour grade: cool blue and steel tones for stress and layoffs, warm amber tones for home and comfort, with skin tones always natural and consistent. Skin is never grey, orange or plastic.
Photographic finish: crisp focus on the eyes, creamy background blur, accurate perspective, no lens distortion, no oversharpening, no painting or illustration look, no 3D render look.

## Video motion block
Motion realism: natural human motion with believable weight, subtle breathing, natural blinks every few seconds, soft head movement, fabric that moves naturally, and no warping of the face, hands or glasses at any moment.
Camera: per shot - the clip's own Camera section names the move (a locked-off frame is one valid choice), and this look asks only for a steady horizon, the shallow depth of field maintained, no shaking, no flashes, no sudden exposure changes, and no cut, fade or transition inside the clip.
Lighting continuity: the light stays constant and natural for the whole clip, with only the motivated changes described in the motion section.
Silence: the clip is silent; there is no dialogue, no music and no sound effect; mouths move only if the motion section says the character speaks or sings.
Lip-sync readiness: the face is front-facing and centred for the whole clip, the mouth is clearly visible at all times, the lips open and close in a natural continuous speaking rhythm with visible jaw movement, the mouth never freezes, and no hand, hair strand or object ever covers the mouth.
Performance: the emotion reads clearly from the eyes and brows throughout; head movement stays within a few degrees; gaze stays on the lens; the expression changes naturally with the words and never turns into a grimace.

## Worked example (Chanel, the run that set this look)

The identity is per campaign. It comes from the character record
(`character_continuity`, the Continuity Bible), never from this file: what
follows is the shape of one identity paragraph, written for Chanel, the woman
whose approved close-up taught us this look. Each block is written once.

Identity lock: the woman in the reference images is Chanel. Reproduce her exactly: the same face shape, the same warm brown skin tone, the same nose and full lips, the same shoulder-length straight black bob with a clean side part that ends at the shoulders, the same black rectangular glasses sitting straight on the bridge of the nose, and the same small gold hoop earrings. Do not change her hairstyle, do not add bangs, do not lengthen or shorten the bob, do not swap the glasses for a different shape, do not remove the earrings, do not lighten or darken her skin, and do not alter her age. She is the same person in every picture of this campaign.
Character stability: Chanel keeps exactly the same face, shoulder-length black bob, black rectangular glasses and small gold hoop earrings for the whole clip; her outfit never changes; she never turns into another person; no new people enter unless the motion section names them.
Reference handling: use the supplied reference images only for who Chanel is and for the overall look of her world, not as a layout to copy. Compose a brand new picture that shows the situation described in the scene section, with the pose, camera angle, expression, background and props the scene asks for. Keep the identity of Chanel from the references and build everything else fresh. If a reference shows a different art style from the requested style, keep her identity and translate her fully into the requested style.
Wardrobe rules: at home she wears a plain casual grey crew-neck t-shirt; at work she wears a tailored black blazer over a white top; in golden finale scenes she wears the black blazer over a white top. The wardrobe never changes within a scene, there is no extra jewellery beyond the small gold hoop earrings, no necklaces, no scarves, no hats, and no logos or brand names on any clothing.

## Emotion note (Trevor, 2026-10-07)
The block above says "wet glistening eyes when the scene is painful". Per D20 that applies only to the one or two deepest moments; other pain beats use the expression the storyboard assigns (shock, humiliation, numbness, anger, exhaustion, fear). Replace that phrase in each prompt with the beat's assigned expression.

## Lip-sync note (learned 2026-10-07)
The video block above asked the mouth to keep moving ("lips open and close in a natural continuous speaking rhythm"). That makes the face look alive but fights the lip-sync step: the mouth already moves on its own, so lip-sync barely changes it. For shots that will be lip-synced, generate the source clip with the mouth closed and still, and let the audio-driven lip-sync create all mouth motion. Shots that will not be lip-synced keep the block as written.
