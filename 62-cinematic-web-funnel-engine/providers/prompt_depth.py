# -*- coding: utf-8 -*-
"""prompt_depth.py -- scene-specific production direction for Skill 62 media prompts.

Owner rule 12: a descriptive prompt uses 95 to 100 percent of the model's prompt maximum and never
less than 80 percent. Owner intent: the length exists to make the output BETTER, so it must be carried
by what is true of THIS scene, not by house rules repeated in every prompt.

How it works:
  * The planner (scripts/plan_visual_journey.py) writes ``production_direction`` on every scene:
    subject, setting, time of day, light, materials, motion, camera blocking, mood and continuity.
  * This module expands each of those, topic by topic (subject, setting, composition, lens, light,
    color, materials, atmosphere, motion or pose, continuity, layout, mood, scale, wear, finish),
    into sentences that apply one craft rule to this scene's own fields. Most sentences embed a
    scene-level field, so two different scenes share only a minority of sentences (the house rules).
  * ``fit_prompt`` adds whole topics while they fit under the model maximum and stops at the 95
    percent target (Skill 74 prompt-budget supplies the numbers; ``KieProvider.prompt_budget``).

``{medium}`` is "image" for stills and "clip" for video, so a video model is never told it is
making an image. Examples are world-neutral; the project's world comes from the style contract.
Verbatim fields (spoken text, lyrics) are exempt and never come through here.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Fit: add topics while they fit, stop at the target (95 percent of the maximum).
# ---------------------------------------------------------------------------


def fit_prompt(base: str, sections: List[str], budget: Optional[Dict[str, Any]], reserve: int = 0) -> str:
    """Return ``base`` extended with whole topics so its length lands in the target band.

    ``budget`` is Skill 74 prompt-budget data (``max``, ``target_min``) or None (no limit known:
    the base prompt is returned unchanged). ``reserve`` is text the provider appends after this
    prompt (for example the negative-prompt clause). If every topic is used and the prompt is
    still short, the short prompt is returned and the provider refuses it with the exact
    characters to add (fail closed)."""
    if not budget or not budget.get("max") or budget.get("verbatim"):
        return base
    ceiling = int(budget["max"]) - reserve
    target = int(budget.get("target_min") or ceiling) - reserve
    out = base.strip()
    leftover: List[str] = []
    for section in sections:
        if len(out) >= target:
            break
        add = "\n\n" + section.strip()
        if len(out) + len(add) <= ceiling:
            out += add
        else:
            leftover.append(section)
    # A topic that did not fit whole may still fit sentence by sentence: this closes the last gap to
    # the target when the maximum is small (a whole topic is about a thousand characters).
    for section in leftover:
        for sentence in section.replace("\n", " ").split(". "):
            if len(out) >= target:
                return out
            piece = sentence.strip()
            piece = piece if piece.endswith(".") else piece + "."
            if piece and len(out) + 1 + len(piece) <= ceiling:
                out += " " + piece
    return out


# ---------------------------------------------------------------------------
# Context: style fields (project level) and direction fields (scene level)
# ---------------------------------------------------------------------------


def _ctx(style: Dict[str, Any], scene: Optional[Dict[str, Any]], medium: str, prefix: str = "") -> Dict[str, str]:
    scene = scene or {}
    camera = scene.get("camera") or {}
    pd = scene.get("production_direction") or {}
    crop = scene.get("crop_rules") or {}
    motif = scene.get("visual_motif") or "the hero subject of the project"
    c = {
        "world": style.get("visual_world") or "the approved visual world",
        "realism": style.get("realism_level") or "photoreal",
        "palette": ", ".join(style.get("palette") or []) or "the approved palette",
        "style_material": style.get("material_language") or "natural materials with tactile surfaces",
        "lighting": style.get("lighting_logic") or "one consistent key light direction",
        "lens": style.get("lens_family") or "a 35 to 85 millimetre cinematic lens family",
        "composition": style.get("composition_system") or "a disciplined rule of thirds layout",
        "prohibited": ", ".join(style.get("prohibited_styles") or []) or "styles outside the approved world",
        "section": scene.get("page_section") or "this",
        "purpose": scene.get("narrative_purpose") or "advance the story of the page",
        "conversion": scene.get("conversion_purpose") or "carry conversion momentum",
        "subject": pd.get("subject") or motif,
        "setting": pd.get("setting") or "the environment established by the approved anchor",
        "time": pd.get("time_of_day") or "the moment of the day established by the approved anchor",
        "light": pd.get("light") or "the project's lighting logic",
        "materials": pd.get("materials") or "the project's material language",
        "motion": pd.get("motion") or "a slow, motivated movement and otherwise stillness",
        "blocking": pd.get("camera_blocking") or "a steady camera move without wobble",
        "mood": pd.get("mood") or "calm, credible confidence",
        "continuity": pd.get("continuity") or "the approved anchor's palette, light direction and proportions",
        "cam_start": camera.get("start_state") or "the opening framing",
        "cam_end": camera.get("end_state") or "the closing framing",
        "cam_move": camera.get("motion_direction") or "a slow forward move",
        "cam_speed": camera.get("motion_speed") or "slow",
        "duration": str(scene.get("duration_seconds") or 8).rstrip("0").rstrip("."),
        "crop_d": crop.get("desktop") or "16:9 full-bleed",
        "crop_m": crop.get("mobile") or "9:16 crop-safe",
        "medium": medium,
        "stock": "photography" if medium == "image" else "footage",
    }
    return {prefix + k: v for k, v in c.items()} if prefix else c


def _fill(topics: List[str], ctx: Dict[str, str]) -> List[str]:
    return [t.format(**ctx) for t in topics]


# ---------------------------------------------------------------------------
# Topics for both media. Each topic is a few sentences; the sentences that name {subject},
# {setting}, {light}, {materials}, {mood}, {time}, {motion}, {blocking}, {continuity}, {purpose}
# and the crop and camera fields are scene-bound and differ from scene to scene.
# ---------------------------------------------------------------------------
_COMMON = {
    "subject": (
        "Subject and hero. The hero must be the single most important thing in the {medium}: it carries the highest local contrast, the sharpest edges and the strongest accent. "
        "In this scene the hero is {subject}. "
        "It sits within {setting}, and it exists to {purpose}. "
        "Keep the hero readable at a glance by separating it from {setting} with value contrast and clean edges rather than outlines or glows. "
        "This scene belongs to the {section} section of the page, so the hero should make the visitor feel {mood}. "
        "Everything else in the {medium} is there only to explain that place or to lead the eye back to {subject}."
    ),
    "setting": (
        "Setting and world. Treat the setting as a real place that continues beyond the edges of the {medium}, with evidence of the people or forces that shaped it. "
        "Here the setting is {setting}, rendered in {world}. "
        "Show how that place has been shaped by use, wear or time, using {materials} as the evidence. "
        "Let the color of the light and the air, and the length of the shadows, say that it is {time}, so that the place reads as one specific moment. "
        "Any small sign of life there must agree with the mood of {mood}. "
        "Keep the realism level at {realism} in every element of {setting}, including distant structures and background props."
    ),
    "composition": (
        "Composition. Build the frame on {composition}, keep the main horizontal lines level unless the story needs tension, and avoid tangents and bright small objects on the border. "
        "Place {subject} on a strong intersection with open space on the side it faces, and let the framing follow this blocking: {blocking}. "
        "Let the leading lines of {setting} carry the eye toward {subject} rather than away from it. "
        "Keep one calm, low-detail area free for headline copy, on the opposite side from the strongest part of {motion}. "
        "The {cam_start} framing at the start and the {cam_end} framing at the end must both keep {subject} inside the central safe region."
    ),
    "lens": (
        "Lens and optics. Render with {lens}, a shallow but believable depth of field, smooth round background blur and no flare, anamorphic streaks or fisheye unless asked for. "
        "Choose the focal length that serves {subject} inside {setting}: wider where the place is part of the story, longer where the hero must stand apart from it. "
        "Keep the focus plane on {subject} and let the background of {setting} soften by exactly as much as the change from the {cam_start} framing to the {cam_end} framing implies. "
        "The optical character should suit a mood of {mood}: gentle micro-contrast, soft highlight bloom around bright sources and a trace of edge fringing on the hardest edges."
    ),
    "light": (
        "Lighting. Follow the project lighting logic, {lighting}, with one dominant source whose shadows agree in direction, length and softness everywhere in the {medium}. "
        "The light in this scene is {light}. "
        "At {time}, that light must fall across {materials} with the correct color temperature and softness. "
        "Cast {subject} with shadows that agree with that light and let them settle into {setting} naturally. "
        "Add only the fill and edge light that keep the mood of {mood} without glowing, and let highlights keep detail while shadows keep a trace of texture."
    ),
    "color": (
        "Color and grade. Use the project palette, {palette}, as a structure: a dominant family for calm areas, a supporting family for mid-sized elements and the strongest accent for the hero. "
        "Let {subject} take that accent and let {setting} carry the calm dominant family. "
        "The color of the air and the light at {time} should tint the shadows inside {setting} consistently. "
        "Grade for the mood of {mood}: keep skin, natural materials and any visible light sources within believable ranges, a clean black point and highlights that roll off instead of clipping. "
        "Keep {materials} true to their own hue under {light} so the grade supports them instead of repainting them."
    ),
    "materials": (
        "Materials and surfaces. Render every surface as a physically plausible material that reflects, absorbs and ages the way the real one does. "
        "The surfaces in this scene are {materials}. "
        "Show how they respond to {light}: where they shine, where they stay matte, and where they pick up dust, scuffs or patina. "
        "Keep the texture scale of {materials} proportional to the distance of the {cam_start} framing, with fine grain near the lens and natural simplification far away. "
        "The project's own material language, {style_material}, continues to govern the finish of {subject}. "
        "Avoid repeating textures in obvious tiles and avoid the airbrushed finish that marks a synthetic {medium}."
    ),
    "atmosphere": (
        "Atmosphere and depth. Build at least four readable planes: a foreground element, the hero plane, a supporting midground and a background that fades with atmospheric perspective. "
        "In {setting}, make the hero plane of {subject} the sharpest and most contrasty, and let the distance fall away softly at {time}. "
        "Haze, dust or moisture in the air must follow {light} and must never veil the hero. "
        "Any particles, haze or moisture in {setting} must be motivated by {time} and by {motion}, and kept restrained."
    ),
    "continuity": (
        "Continuity. This {medium} belongs to a sequence that must feel shot on one set by one crew. "
        "Carry forward: {continuity}. "
        "Keep {subject} identical in proportion, material and finish wherever it recurs, and keep the light logic and lens family of the approved anchor in {world}. "
        "What changes in this scene is {setting} and the moment, {time}; what must not change is the design vocabulary, the palette and the scale of things relative to people. "
        "Where this scene introduces something new, design it from the same shapes, materials and colors as {subject} so it looks as if it always belonged there."
    ),
    "layout": (
        "Layout for the web page. This {medium} will sit under headlines, body copy and buttons in the {section} section, and the page is cropped as {crop_d} on desktop and {crop_m} on mobile. "
        "Keep {subject} inside the safe region that survives both crops, and keep secondary detail away from the outer tenth of the frame. "
        "Provide a large, calm, evenly toned area away from {subject} where light or dark text can be read without a scrim. "
        "The conversion role of this scene is to {conversion}, so nothing in {setting} should draw the eye away from where the call to action will sit. "
        "Avoid dense, high-frequency patterns behind the text area and avoid small hot spots that would fight with button colors."
    ),
    "mood": (
        "Emotional tone. The {medium} should make the visitor feel {mood}, and it should do so through craft, not effects. "
        "Warmer light and open composition invite trust, cooler light and tighter framing create focus, a low camera suggests ambition and a high camera suggests perspective; apply the combination that fits {subject} in {setting}. "
        "Let {light} and the pace of {motion} pull in the same direction as that feeling. "
        "Keep the tone premium and human: quiet confidence, never hype, never harshness, never the empty gloss of stock {stock}. "
        "The purpose to {purpose} is served by feeling, not by decoration."
    ),
    "scale": (
        "Scale and proportion. Keep human-scale cues in the {medium} wherever size matters, and keep them consistent relative to {subject} and to the structure and surroundings of {setting}. "
        "Do not let {subject} drift in apparent size between frames of this scene, and do not exaggerate it unless the story calls for a monumental feel. "
        "Maintain correct perspective for the lens: parallel lines converge toward vanishing points that agree across objects, and equal objects shrink by equal ratios with distance. "
        "Ground planes and the main horizontal lines in {setting} must recede correctly under {light}."
    ),
    "wear": (
        "Wear and imperfection. Perfectly clean, perfectly symmetrical scenes look synthetic, so add tasteful, motivated imperfection to {materials}: tool marks, tracks, fingerprints, ageing, dust or patina where real use or time would leave them. "
        "Concentrate that wear where {subject} is touched, stepped on or exposed in {setting}. "
        "It must be consistent with the age and care implied by {setting} at {time}, and it must never read as damage that undermines the mood of {mood}."
    ),
    "people": (
        "People, anatomy and brand safety. When people appear in {setting}, render natural anatomy: correct hands, plausible joints, consistent limb length, natural eye direction and honest, understated expressions. "
        "Wardrobe must belong to {world} and fit the way real clothes do. "
        "Do not render any recognisable real person, copyrighted character, trademark or watermark. "
        "Do not render legible text, numbers or logos unless this prompt supplies the exact words; a surface in {setting} that would naturally carry lettering stays out of focus, turned away or abstracted."
    ),
    "finish": (
        "Finish and resolution. The {medium} should hold up at full resolution on a large display and when cropped to a tight detail. "
        "Keep detail crisp on {subject} and on the surface of {materials} nearest the lens, and keep transitions into softness smooth, with no halos, no oversharpening rings and no plastic denoise smear. "
        "Preserve a fine, even, film-like grain so gradients in {setting} do not band; keep edges between {subject} and the background clean, with correct fine detail in hair, fine fibres and glass. "
        "Aim for the look of a carefully lit, professionally graded {medium} of a real place at {time}."
    ),
    "time_conditions": (
        "Time and conditions. Fix one believable moment for the whole {medium} and hold it: it is {time}. "
        "The angle and color of {light}, the length of the shadows and the dampness or dryness of {materials} must all agree with that moment. "
        "Small conditions in {setting}, such as a sheen on a surface, condensation, drifting dust or a soft haze, add truth without drawing attention to themselves. "
        "Keep the emotional temperature of those conditions in step with {mood}, and avoid lighting that could be two different hours at once."
    ),
    "background": (
        "Background and surroundings. Keep the surroundings of {subject} simple enough to support it and detailed enough to feel real. "
        "{setting} should show correct structure, with visible joints, supports, edges and plausible wear where hands, feet and the elements touch it. "
        "Distant forms in {setting} simplify into clean shapes with reduced contrast under {light}, not into noise, and nothing repeats like a cloned tile. "
        "The background carries the design vocabulary of {world} quietly, so that it explains {subject} without competing with it."
    ),
    "exclusions": (
        "What must not appear. No text, letters, numbers, logos, watermarks, signatures, borders or interface elements; no distorted anatomy, extra limbs or floating objects; no inconsistent shadows, impossible reflections or mismatched perspective; no collage seams, cloned patches, neon oversaturation, heavy vignette, cartoon outlines or plastic skin. "
        "Stay away from these prohibited styles: {prohibited}. "
        "Nothing may contradict {setting} or the mood of {mood}. "
        "When in doubt between a bold decorative choice and a quiet believable one, choose the believable one that keeps {subject} dominant."
    ),
}

# ---------------------------------------------------------------------------
# Topics for stills only.
# ---------------------------------------------------------------------------
_STILL = {
    "pose": (
        "The frozen instant. This is one decisive moment, not a summary: {motion}. "
        "Freeze it with no motion blur on {subject}, weight and gesture clearly resolved, and a silhouette that reads against {setting}. "
        "Let {materials} show the motion that came just before, with a slight asymmetry that keeps the {medium} alive."
    ),
    "hierarchy": (
        "Focal hierarchy. A still is read in a few seconds, so decide the order of reading: first {subject}, then the element that explains {setting}, then one quiet detail that rewards a second look. "
        "Control that order with contrast, size, saturation and sharpness. "
        "Check that {subject} stays clear when the picture is shrunk to a thumbnail, with a clean separation from {setting}."
    ),
    "crop": (
        "Cropping discipline. This frame is cropped as {crop_d} on desktop and {crop_m} on mobile, so compose with a generous margin on every side. "
        "Let {setting} continue past the edges of the frame so it feels like a view onto a larger place, and keep {subject} off the dead center and away from every edge band."
    ),
    "boundary": (
        "Boundary discipline. When this still opens or closes a moving shot, it must be a clean, stable instant: the camera at the {cam_start} framing or the {cam_end} framing, the lens and light exactly right for the move that follows ({cam_move}, {cam_speed}). "
        "Leave open space in the direction of travel for {subject}, keep the geometry simple enough to continue, and separate the depth planes of {setting} clearly so parallax later reveals real layers."
    ),
    "detail": (
        "Detail budget for a still. Spend resolution where the eye will look: {subject}, the part of {materials} next to it and the focal edge where sharp meets soft. "
        "Describe those regions with real material information and let the rest of {setting} simplify gracefully. "
        "One hero with convincing fine detail is worth more than a frame of uniform texture, and detail density must follow optical distance so nothing far away is sharper than something near."
    ),
    "depth_ready": (
        "Depth planes and parallax readiness. This still will be animated later, so build clean depth: a foreground element, {subject}, a midground and a far plane, each separated by tone, focus or atmosphere. "
        "Keep the boundary between {subject} and {setting} crisp enough that a later move can reveal what lies behind it, and keep the nearest surface of {materials} detailed enough to survive a push toward it. "
        "Avoid flattened lighting that merges the planes, and keep {light} directional so each plane carries its own shading."
    ),
    "micro_detail": (
        "Texture and micro-detail under the grade. Under the {mood} grade, the smallest details still have to read: the grain and edge wear of {materials}, the way {light} breaks across them, and the fine transitions where {subject} meets what is behind it. "
        "Let micro-contrast fall off smoothly from the focus plane, keep highlights textured and shadows quietly detailed, and never flatten fine structure into smooth blur. "
        "The detail must look captured at {time}, not painted."
    ),
    "silhouette": (
        "Edge and silhouette treatment. The outline of {subject} is its signature, so keep it clean, believable and distinct from {setting}: a thin natural edge light under {light}, no cut-out halo, no glow and no tangent with a neighbouring shape. "
        "Check that the shape still reads when the {medium} is seen small, and let the edge soften only where the lens and the distance say it should."
    ),
    "camera_height": (
        "Camera height and perspective. Choose one camera height and hold it: low enough to give {subject} presence, high enough to show how it sits in {setting}, and level enough that verticals stay vertical. "
        "The {cam_start} framing tells the visitor where they are and the {cam_end} framing tells them what to look at, so the height should serve both. "
        "Let perspective lines converge honestly under {lens}, and match the height to a mood of {mood}."
    ),
    "tonal_range": (
        "Tonal range and exposure latitude. Expose so the finished picture can be graded later: a true black point that still holds texture in the darkest part of {setting}, a highlight shoulder that lets {light} roll off without clipping, and a midtone placement that keeps {subject} at the brightness a viewer reads as correct. "
        "Keep the histogram continuous rather than stacked at either end, and make the contrast between {subject} and what is behind it come from tone first and color second, so it survives a desaturated or high-contrast treatment on the page. "
        "A {mood} feeling lives in the midtones, so do not spend them on empty gradients."
    ),
    "separation": (
        "Figure and ground separation. {subject} must separate from {setting} by at least two of the three tools: a difference in value, a difference in color temperature and a difference in edge sharpness. "
        "Use the one that suits {light} first, and add a second so the separation holds under compression and on a small screen. "
        "Never rely on an outline or an artificial glow, and never let a background shape of similar tone touch the edge of {subject}."
    ),
    "story_detail": (
        "Supporting story detail. Add two or three small details that quietly prove the narrative purpose, {purpose}: things a careful viewer notices on a second look and that belong to {setting} and to {materials}. "
        "Place them off the main reading path so they reward attention without competing with {subject}, keep them consistent with {time}, and make sure none of them introduces text, a logo or a face that was not asked for."
    ),
    "artefacts": (
        "Avoiding synthetic artefacts. Check the places where generated pictures usually fail: hands and fingers, teeth and eyes, repeated or cloned texture in {materials}, text-like marks that are not letters, symmetrical duplicates, melted or fused edges where {subject} meets {setting}, and objects that change scale across the frame. "
        "Resolve each of these deliberately: vary the repeated pattern, break the symmetry, give every edge a physical reason and keep every object at one consistent scale."
    ),
    "negative_space": (
        "Negative space. Plan the empty areas on purpose: the open space around {subject} gives it presence, and the quiet area kept for copy must stay calm at both crops, {crop_d} on desktop and {crop_m} on mobile. "
        "Shape the empty space so that it leads toward {subject} instead of leaving a hole, give it a tone that follows {light}, and keep it free of small bright accents. "
        "A mood of {mood} needs space to breathe, so protect the space even when {setting} offers detail to fill it."
    ),
    "light_ratio": (
        "Lighting ratio. Set the ratio between the key and the fill so that {subject} keeps its form: strong enough that {materials} show their relief under {light}, soft enough that the shadow side still carries detail at {time}. "
        "Keep the ratio the same across the whole {medium} so that nothing looks lit by a different source, and let the deepest shadow hold the faintest trace of the surfaces around {subject}."
    ),
    "accent": (
        "Accent discipline. From the project palette, {palette}, choose one accent family and place it on {subject} and on at most one other small element. "
        "Keep {materials} in the calmer neighbouring families so the accent stays rare, and keep the accent's saturation within what {light} would really produce at {time}. "
        "An accent that appears three times stops being an accent."
    ),
    "reference": (
        "Reference fidelity. If reference images are supplied they are binding: reproduce the identity, proportions, palette, finish and design vocabulary of {subject} and {setting} exactly and change only what this prompt asks to change. "
        "Where a reference and this prompt disagree on a detail that matters for continuity, the reference wins; anything new is designed so that it looks photographed on the same set on the same day."
    ),
}

# ---------------------------------------------------------------------------
# Topics for clips only.
# ---------------------------------------------------------------------------
_MOTION = {
    "path": (
        "Camera path and easing. The camera moves {cam_move} at {cam_speed} speed from the {cam_start} framing to the {cam_end} framing over {duration} seconds. "
        "The specific blocking is: {blocking}. "
        "Describe it as one continuous physical gesture with a smooth start, a steady middle and a smooth settle, with no jitter, hunting zoom or reversal, and with the slight inertia of real dolly, slider, crane or gimbal equipment. "
        "Keep the main horizontals stable and verticals vertical, and keep the speed constant, because the clip will be scrubbed by scroll position."
    ),
    "parallax": (
        "Parallax and depth during the move. As the camera travels, nearer parts of {setting} must slide across the frame faster than distant ones, with correct occlusion and clean disocclusion behind {subject}. "
        "Treat {setting} as a real volume under {light}, and let perspective lines converge or diverge exactly as the camera position implies. "
        "Do not slide a flat plate sideways, do not warp it, and do not let the background swim. "
        "Where the move reveals area that was not visible at the start, invent it from the same design vocabulary and {materials}."
    ),
    "temporal": (
        "Temporal consistency. Every object keeps its shape, size, color and texture from the first frame to the last. "
        "{subject} and {materials} must not flicker, shimmer, crawl, breathe or morph, and no object may appear, vanish or change count. "
        "Shadows and highlights must move correctly with the camera under {light}, and reflections must update plausibly. "
        "If people or animals are present, keep identity and wardrobe stable and keep any movement small and purposeful."
    ),
    "subject_motion": (
        "Motion inside the scene. {subject} stays the anchor of the shot, and the movement in this clip is: {motion}. "
        "Any movement has weight and intent, with acceleration that follows physics and fabric, hair or loose fibres responding with a slight delay. "
        "Add only quiet ambient motion elsewhere in {setting}, at a speed consistent with {time}, and nothing that draws attention from {subject} or from the camera move. "
        "No sudden events, fast cuts inside the shot, flashes or strobing."
    ),
    "endpoints": (
        "Start and end frame fidelity. The first frame must match the supplied opening frame in composition, subject placement, light and color, and the last frame must settle into the supplied closing frame the same way. "
        "Do not invent a different set or time of day between them: it stays {time} in {setting} throughout. "
        "Spend the whole {duration} seconds moving from the {cam_start} framing to the {cam_end} framing on one believable path, arriving at the end and not earlier, so the last frames are not static padding."
    ),
    "scrub": (
        "Scroll scrubbing. The clip is played forward and backward by the visitor's scroll position, so every frame must stand alone as a good frame of {subject} and every pair of neighbouring frames must differ by a small, smooth step. "
        "Avoid effects that only make sense forward, such as falling objects, pouring liquid or smoke trails, and avoid any beat that needs time to build. "
        "No hard cuts, whip pans, title cards, on-screen text, fades at the ends or letterbox bars; no speech, singing or visible speakers, since the clip plays silent behind page copy."
    ),
    "lens_move": (
        "Lens behaviour during the move. Keep the focal length constant: the change of framing comes from travelling, never from zooming. "
        "Hold focus on {subject} and let the depth of field of {setting} behave as the changing distance implies, with no focus hunting or breathing of the framing. "
        "Keep exposure and white balance fixed, so any change in brightness comes only from what the lens is looking at under {light}."
    ),
    "light_move": (
        "Light during the move. The sources stay where they are in the world and only the way they fall on {materials} changes as the camera moves. "
        "Specular highlights slide across surfaces, shadows rotate with the viewpoint and reflections update, all consistent with {light} at {time}. "
        "Do not animate the lights, flicker lamps or pulse the exposure; any rim light on {subject} may gain or lose a little as the angle opens, gradually."
    ),
    "shutter": (
        "Shutter and motion rendering. Render movement with the natural motion blur of a real shutter: enough on {motion} to feel natural, never so much that {subject} smears, and none on the parts of the frame that are meant to be still. "
        "Keep the blur direction consistent with the {cam_move} move at {cam_speed} speed, and keep {materials} sharp enough that their detail survives playback in either direction."
    ),
    "plane_handoff": (
        "Hand-off between depth planes. During the move, each depth plane takes its turn as the point of interest: first what the {cam_start} framing introduces, then {subject}, then what the {cam_end} framing resolves to. "
        "Let focus and contrast pass between the planes smoothly, keep {light} constant across them, and never let a plane pop in front of {subject} without a physical reason."
    ),
    "motion_artefacts": (
        "Avoiding motion artefacts. Check the places where generated clips usually fail: melting or rubber-banding edges on {subject}, ghosting trails behind {motion}, textures on {materials} that crawl or swap while the camera moves, and background structure that rebuilds itself between frames. "
        "Resolve each deliberately: let the geometry of {setting} stay rigid, let only the intended movement change from frame to frame, and keep every edge physically attached to the thing that owns it."
    ),
    "encode_ready": (
        "Ready for web encoding. The clip will be compressed for the page, so keep large gradients in {setting} smooth and free of banding, keep noise and grain even from frame to frame so the encoder does not shimmer, and avoid fine repeating patterns on {materials} that alias when scaled. "
        "Keep the brightness of {subject} steady under {light}, because a fluctuating level reads as flicker once compressed."
    ),
    "easing": (
        "Easing and frame rhythm. Over the {duration} seconds, the {cam_move} move at {cam_speed} speed should ease in over roughly the first tenth of the clip and ease out over the last tenth, with a constant speed between. "
        "Keep that rhythm identical on every playback so the clip scrubs predictably, and keep {motion} locked to the same rhythm so that nothing in the frame accelerates on its own."
    ),
    "foreground": (
        "Foreground elements for parallax. Give the move something near the lens to pass: a soft out-of-focus edge, a surface of {materials} or a partial form that belongs to {setting}, entering and leaving the frame smoothly. "
        "Keep it dark or low in contrast so it never competes with {subject}, and let it sell the three dimensional depth of the {cam_move} move under {light}."
    ),
    "end_hold": (
        "Ending hold. The last frames settle on the {cam_end} framing and hold steady so that copy and buttons can sit over {subject} without the picture moving under them. "
        "Hold the light, the focus and the position of {subject} exactly, and let only the faintest ambient motion continue, in keeping with a mood of {mood}."
    ),
    "pacing": (
        "Pacing. Divide the {duration} seconds into a gentle opening in which the viewer settles on the {cam_start} framing, a steady middle in which {motion} unfolds, and a calm close in which the {cam_end} framing arrives and holds for the last few frames. "
        "Keep the amount of new visual information per second low and steady so the clip stays readable at any scroll speed and feels unhurried. "
        "The clip contains exactly one move and one idea: the purpose to {purpose}."
    ),
}

_CONNECTOR = {
    "bridge": (
        "Connector transition. This clip joins {subject} in {setting} (the scene that ends) to {to_subject} in {to_setting} (the scene that begins) without a cut. "
        "Begin on the exact last frame of the preceding scene, at {time}, and end on the exact first frame of the next scene, at {to_time}. "
        "Carry the same camera direction, speed, lens and light through the hand-off so the viewer feels one continuous move through one connected world."
    ),
    "handoff": (
        "Hand-off of light and materials. The preceding scene is lit by {light}; the next scene is lit by {to_light}. "
        "Let one pass into the other gradually in direction, warmth and softness, never as a dissolve between two pictures. "
        "{materials} must fall away behind the camera with natural parallax while {to_materials} come into focus ahead."
    ),
    "entering": (
        "The entering scene. {to_setting} should enter as a softly blurred, partly visible frame edge that grows in size and sharpness as the move proceeds, so that {to_subject} is clearly the next destination. "
        "Keep the three dimensional depth of the move obvious throughout, so the transition reads as travelling through space, and keep what must carry across legible: {continuity}. "
        "The next scene's mood, {to_mood}, should be felt before it is seen."
    ),
}

# Ordering: interleave scene-heavy topics so the early part of a prompt is already scene-specific.
_STILL_ORDER = [
    ("c", "subject"), ("c", "setting"), ("s", "pose"), ("c", "composition"), ("c", "light"), ("s", "hierarchy"),
    ("c", "materials"), ("c", "lens"), ("c", "color"), ("s", "boundary"), ("c", "atmosphere"), ("c", "mood"),
    ("c", "continuity"), ("s", "crop"), ("c", "time_conditions"), ("c", "layout"), ("s", "detail"), ("c", "scale"),
    ("c", "background"), ("c", "wear"), ("c", "finish"), ("s", "depth_ready"), ("s", "micro_detail"), ("s", "tonal_range"), ("s", "silhouette"), ("s", "separation"), ("s", "camera_height"),
    ("s", "story_detail"), ("s", "negative_space"), ("s", "light_ratio"), ("s", "accent"), ("s", "artefacts"),
    ("s", "reference"), ("c", "people"), ("c", "exclusions"),
]
_VIDEO_ORDER = [
    ("c", "subject"), ("c", "setting"), ("m", "path"), ("c", "composition"), ("c", "light"), ("m", "subject_motion"),
    ("m", "parallax"), ("c", "materials"), ("m", "endpoints"), ("c", "lens"), ("m", "temporal"), ("c", "color"),
    ("c", "atmosphere"), ("m", "lens_move"), ("c", "mood"), ("m", "light_move"), ("c", "continuity"), ("m", "shutter"), ("m", "plane_handoff"), ("m", "motion_artefacts"), ("m", "encode_ready"), ("m", "easing"), ("m", "foreground"), ("m", "end_hold"), ("m", "pacing"),
    ("c", "time_conditions"), ("c", "layout"), ("m", "scrub"), ("c", "scale"), ("c", "background"), ("c", "wear"), ("c", "finish"),
    ("c", "people"), ("c", "exclusions"),
]
_TABLES = {"c": _COMMON, "s": _STILL, "m": _MOTION}


def image_sections(style: Dict[str, Any], scene: Optional[Dict[str, Any]] = None) -> List[str]:
    """Scene-specific direction topics for a still (concept board, anchor, scene and boundary stills)."""
    ctx = _ctx(style, scene, "image")
    return _fill([_TABLES[t][k] for t, k in _STILL_ORDER], ctx)


def video_sections(
    style: Dict[str, Any],
    scene: Optional[Dict[str, Any]] = None,
    to_scene: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """Scene-specific direction topics for a clip (draft, final scene clip, connector). Pass ``to_scene`` for a connector."""
    ctx = _ctx(style, scene, "clip")
    topics = [_TABLES[t][k] for t, k in _VIDEO_ORDER]
    if to_scene is not None:
        ctx.update(_ctx(style, to_scene, "clip", prefix="to_"))
        topics = [_CONNECTOR["bridge"], _CONNECTOR["handoff"]] + topics[:6] + [_CONNECTOR["entering"]] + topics[6:]
    return _fill(topics, ctx)
