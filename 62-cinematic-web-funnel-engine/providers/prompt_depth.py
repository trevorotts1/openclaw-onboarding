# -*- coding: utf-8 -*-
"""prompt_depth.py -- descriptive direction for Skill 62 media prompts.

Owner rule 12: a descriptive prompt must use 95 to 100 percent of the model's prompt
maximum and may never fall below 80 percent. Skill 74 ``prompt-budget`` owns the numbers
(live schema first); ``KieProvider.prompt_budget`` hands them to this module and
``fit_prompt`` assembles the prompt from real production direction, not filler: each
section below is a self-contained brief about one craft decision (composition, optics,
light, color, material, atmosphere, continuity, motion), filled in from the project's
style contract and the scene. Sections are added in order while they still fit under the
maximum and stop once the target is reached. Nothing here hard-codes a character band.

Verbatim fields (spoken text, lyrics) are exempt and never come through here.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Fit: add sections while they fit, stop at the target (95 percent of the maximum).
# ---------------------------------------------------------------------------


def fit_prompt(base: str, sections: List[str], budget: Optional[Dict[str, Any]], reserve: int = 0) -> str:
    """Return ``base`` extended with whole sections so its length lands in the target band.

    ``budget`` is Skill 74 prompt-budget data (``max``, ``target_min``) or None (no limit known:
    the base prompt is returned unchanged). ``reserve`` is text the provider appends after this
    prompt (for example the negative-prompt clause). If every section is used and the prompt is
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
    # A section that did not fit whole may still fit sentence by sentence: this closes the last gap to
    # the target when the maximum is small (a whole section is about a thousand characters).
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
# Context
# ---------------------------------------------------------------------------


def _ctx(style: Dict[str, Any], scene: Optional[Dict[str, Any]] = None, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    scene = scene or {}
    camera = scene.get("camera") or {}
    c = {
        "world": style.get("visual_world") or "the approved visual world",
        "realism": style.get("realism_level") or "photoreal",
        "palette": ", ".join(style.get("palette") or []) or "the approved palette",
        "material": style.get("material_language") or "natural materials with tactile surfaces",
        "lighting": style.get("lighting_logic") or "one consistent key light direction",
        "lens": style.get("lens_family") or "a 35 to 85 millimetre cinematic lens family",
        "composition": style.get("composition_system") or "a disciplined rule of thirds layout",
        "prohibited": ", ".join(style.get("prohibited_styles") or []) or "styles outside the approved world",
        "motif": scene.get("visual_motif") or "the hero subject of the project",
        "purpose": scene.get("narrative_purpose") or "the section this scene supports",
        "cam_start": camera.get("start_state") or "the opening framing",
        "cam_end": camera.get("end_state") or "the closing framing",
        "cam_move": camera.get("motion_direction") or "a slow forward move",
        "cam_speed": camera.get("motion_speed") or "slow",
    }
    c.update(extra or {})
    return c


# ---------------------------------------------------------------------------
# Shared craft sections (stills and motion).
# ---------------------------------------------------------------------------
_SHARED = [
    # 1
    """Subject and world fidelity. Everything in this frame belongs to {world}. The hero subject is {motif}, and it must read at a glance as the single most important object in the image: it carries the highest local contrast, the sharpest edges and the most saturated accent in the frame, while everything around it supports rather than competes. Treat the scene as a real place that exists beyond the borders of the picture: show evidence of use, such as scuffs on a floor, a half-open drawer, a light switch, a cable, footprints in dust, because lived-in detail is what separates a photograph from an illustration. Keep the {realism} realism level consistent in every element, including background props, distant architecture and reflections, so that no object looks pasted in from a different style. The scene supports this narrative purpose: {purpose}. Let that purpose decide which details are emphasised and which fall away into soft background, and never add decorative objects that do not serve it.""",
    # 2
    """Composition and framing. Build the frame on {composition}. Place the hero subject on a strong intersection, give it breathing room on the side it faces or moves toward, and let secondary elements form a clear second and third read in descending visual weight. Use leading lines, such as floor seams, shelf edges, window mullions, road markings or the horizon, to carry the eye toward the hero rather than away from it. Keep the horizon level unless the narrative calls for tension, and when it does, tilt it deliberately by a few degrees and keep every vertical line consistent with that tilt. Avoid tangents, where an edge of one object just touches the edge of another, and avoid placing bright small objects on the extreme border of the frame, where they pull the eye out of the picture. Reserve calm, low-detail regions that can sit behind headline text and buttons on the finished web page, and keep the visual centre of gravity away from those regions.""",
    # 3
    """Lens and optics. Render with {lens}. Choose focal length by the job the shot has to do: a wider lens exaggerates depth and suits establishing views with strong foreground, a normal lens keeps proportions honest for product and portrait work, and a short telephone lens compresses distance and stacks background layers behind the hero. Use a shallow but believable depth of field: the hero plane is critically sharp, the plane a few steps behind it is gently soft, and the far background dissolves into smooth, round, even bokeh with no cat-eye distortion in the center and only mild optical vignetting at the corners. Add only the optical character a real lens would add: a trace of chromatic fringing on very high contrast edges, soft highlight bloom around practical lights, and natural micro-contrast roll-off. Do not add lens flares, anamorphic streaks or fisheye distortion unless this scene explicitly calls for them.""",
    # 4
    """Lighting design. Follow this lighting logic everywhere in the frame: {lighting}. Establish one dominant source and let every shadow in the scene agree with it in direction, length and softness. Describe the quality of that source precisely: its direction relative to the lens, its color temperature, how soft or hard its penumbra is, and how far it falls off across the room or landscape. Add a gentle fill that lifts shadows without flattening the form, and a restrained edge or rim light that separates the hero from the background without glowing. Practical lights in the scene, such as lamps, screens, windows and signage, must be the plausible origin of the light they appear to emit, and must cast matching pools of light on nearby surfaces. Let highlights keep detail instead of clipping to flat white, and let shadows keep a trace of texture instead of crushing to flat black, so that the grade has latitude to work in later.""",
    # 5
    """Color and tonal grade. The palette for this project is {palette}. Use it as a structure, not a coat of paint: assign a dominant color family to large calm areas, a supporting family to mid-sized elements, and reserve the strongest accent for the hero subject and the single most important call to action zone. Keep skin tones, wood, foliage and sky within believable ranges even inside a stylised grade, because audiences reject images where natural things shift to the wrong hue. Control contrast with intent: a clean, slightly lifted black point, a smooth midtone curve, and highlights that roll off gently instead of clipping. Keep color temperature coherent across the whole frame, with warm and cool contrast coming from the light sources rather than from arbitrary tint layers, and make sure the mood of the grade matches the emotional beat the scene serves, without pushing saturation to the point where gradients band or skin turns orange.""",
    # 6
    """Materials and surface detail. The material language of this project is {material}. Render each surface as a physically plausible material: describe how it reflects, how rough or glossy it is, how light enters and leaves it, and what small imperfections it carries. Wood needs visible grain direction, pores and softened edges; metal needs believable anisotropic highlights, fingerprints or brushing; glass needs correct refraction, faint dust and edge tint; fabric needs weave, folds that follow gravity and tension, and a soft fuzzy edge in backlight; concrete and plaster need pores, hairline cracks and tonal clouding; skin needs pores, fine vellus hair and subsurface warmth without wax or plastic smoothing. Keep material scale consistent: texture detail must be proportional to the distance from the lens, so close surfaces show fine grain and far surfaces simplify naturally. Avoid repeating textures in obvious tiles, and avoid the over-smoothed, airbrushed finish that marks synthetic images.""",
    # 7
    """Atmosphere and depth. Build depth with at least four readable planes: a foreground element that frames the shot and may sit softly out of focus, the hero plane, a supporting midground, and a background that fades with atmospheric perspective. Let distant planes lose contrast and saturation and drift slightly toward the ambient light color, exactly as haze, dust and humidity do in real air. Where the world allows it, add subtle volumetric light, such as sun shafts through a window, dust motes drifting through a beam, steam over a cup, or a thin morning mist in a street, always lit by the same dominant source as everything else. Keep particle effects restrained and physically motivated, and never let them cover the hero or reduce legibility of the key subject. Depth cues should agree with each other: occlusion, scale, overlap, blur and haze must all tell the same story about which object is nearer, so that the image reads as one coherent three dimensional space.""",
    # 8
    """Continuity and consistency. This image is one frame of a larger sequence that must feel shot on one set by one crew. Keep the identity of every recurring object, person and location stable: the same proportions, the same materials, the same wear, the same scale relative to the room. Keep the light logic, the lens family and the grade identical to the approved project anchor, so that when this frame is placed beside any other frame of the project, nobody can tell where one was generated and the next began. Match the approved anchor in architecture, furniture style, props, wardrobe, signage language and overall design vocabulary. If the anchor shows a specific object, such as a lamp, a vehicle or a product, reproduce it with the same shape, color and finish rather than reinterpreting it. Where this frame introduces something new, design it from the same vocabulary of shapes, materials and color so that it looks like it always belonged there.""",
    # 9
    """People, anatomy and brand safety. When people appear, render natural, believable anatomy: correct hand structure with five fingers, plausible joint angles, consistent limb length, symmetrical but not mirror-perfect faces, natural eye direction and believable teeth. Keep expressions authentic and understated, and let posture, gesture and gaze serve the narrative purpose rather than posing for the camera. Wardrobe must be consistent with the world, free of readable logos unless supplied by the project, and fit the body the way real clothes do, with believable seams, folds and shadow under straps and collars. Do not render any recognisable real person, celebrity or public figure, and do not render any copyrighted character, trademark or watermark. Do not render legible text, UI copy, captions or signage lettering unless this prompt supplies the exact words; if a surface would naturally carry text, keep it out of focus, turned away, or abstracted into non-letter marks.""",
    # 10
    """Texture, resolution and finish. The finished image should hold up at full resolution on a large retina display and when cropped to a tight detail. Keep fine detail crisp where the lens is focused and keep transitions into softness smooth, with no halos, no oversharpening rings, and no plastic denoise smear. Preserve a natural, very fine film-like grain that is consistent across the frame, so that gradients in skies, walls and out of focus areas do not band, and so that compression later does not reveal blocking. Avoid noise patterns that vary from region to region, mismatched sharpness between neighbouring objects, and uncanny micro-detail such as repeating hair strands or identical leaves. Edges between hero and background should be clean and natural with correct fine detail in hair, fur, foliage and glass, and no cut-out outline. Aim for the look of a carefully lit, professionally retouched photograph of a real set: honest, rich and calm rather than hyper-processed.""",
    # 11
    """Layout safety for the finished web page. This image will sit inside a scroll-driven web page with headlines, body copy and buttons layered above it, and with the page cropped differently on desktop and phone. Keep the hero subject inside the central safe region so that neither a wide desktop crop nor a tall phone crop cuts it, and keep important secondary details away from the outer ten percent of the frame. Provide at least one large, calm, low-contrast area with an even tone where light or dark text can be placed and read without a scrim, and make sure that area does not contain faces, hands or the focal object. Avoid very busy high-frequency patterns, such as dense foliage or tiled floors, behind the area intended for text. Keep brightness variation across the frame moderate so that a single overlay treatment works across the page, and avoid bright small hot spots that would fight with button colors.""",
    # 12
    """What this image must not contain. Do not include text, letters, numbers, logos, watermarks, signatures, frames, borders, drop shadows around the whole picture, or interface elements. Do not include distorted anatomy, extra limbs, merged fingers, duplicated faces, or floating objects with no support or shadow. Do not include inconsistent shadows, impossible reflections, mismatched perspective between objects, or objects that intersect each other without physical reason. Do not include collage seams, cloned patches, symmetrical duplicate textures, over-saturated neon color, heavy vignette, oil painting smears, cartoon outlines, plastic skin, or an overall artificial glow. Stay away from these prohibited styles for this project: {prohibited}. When in doubt between a bold decorative choice and a quiet believable one, choose the quiet believable one, because the project depends on a calm, premium, trustworthy look.""",
    # 13
    """Time of day and weather. Fix one believable moment for the whole project and hold it: the angle and color of the sun or sky, the length of shadows, the state of the clouds and the dampness of surfaces must all agree with that moment. If the scene is indoors, let the window light, the practical lamps and the color cast on walls tell the same story about the hour. Avoid ambiguous lighting that could be noon and dusk at once, and avoid sudden weather shifts between neighbouring scenes. Subtle weather evidence, such as a faint sheen on pavement after rain, condensation on a cold glass or the slight lean of grass in a breeze, adds truth without drawing attention. Keep the emotional temperature of the weather in step with the narrative beat: calm and clear for trust, a little drama in the sky for a turning point, soft overcast for reflection.""",
    # 14
    """Environment and set dressing. Design the environment as a real, specific place with a clear architecture or landscape logic rather than a generic backdrop. Choose a small number of repeating design motifs, such as a window shape, a railing profile, a tile pattern or a plant species, and use them consistently so the place feels authored. Dress the set with believable props placed with intent: objects cluster in groups of odd numbers, overlap slightly, sit at different heights, and show use. Keep clutter below the level where it distracts from the hero, and keep clear space around the hero so its silhouette reads. Make sure that every prop has a reason to be there for the people who live or work in this world, and that no prop contradicts the budget, era or culture implied by the rest of the scene.""",
    # 15
    """Scale and proportion. Keep human-scale cues in the frame wherever a sense of size matters, such as a door handle, a chair, a step, a cup or a hand, and keep them consistent in size relative to one another and to the architecture. Do not let the hero subject drift in apparent size between frames of the same scene, and do not exaggerate it unnaturally unless the narrative explicitly calls for a monumental feel. Maintain correct perspective for the chosen lens: parallel lines converge toward vanishing points that agree across objects, and objects of the same real size shrink by the same ratio with distance. Check that floors recede correctly, that walls meet at plausible angles, and that no object looks like a miniature or a giant relative to its neighbours.""",
    # 16
    """Emotional tone. The image should make the viewer feel the beat this scene serves, and it should do so through craft rather than through effects. Warmer light, softer shadows and open composition invite trust and ease; cooler light, harder edges and tighter framing create focus and tension; a low camera and strong verticals suggest ambition; a high camera and generous empty space suggest calm and perspective. Choose the combination that fits the narrative purpose, and apply it consistently across light, color, framing and pose, so every element pulls in the same direction. Keep the tone premium and human: authentic, quiet confidence, never hype, never harshness, never the glossy emptiness of stock imagery. Leave a small sign of life, such as a lit window, a used cup or a coat over a chair, that tells the viewer a person has just been here.""",
    # 17
    """Reflections, glass and contact. Every reflective surface must show a plausible reflection of what is actually in the scene, at the correct angle and with the correct blur for the roughness of the surface. Glass should show both a reflection of the room and a view of whatever lies behind it, with a faint edge tint and a little dust. Wet or polished floors should mirror nearby objects and lights with distance-dependent fading. Wherever objects touch a surface, show correct contact: a tight dark contact shadow, a soft ambient occlusion in the crease, and a small bounce of the surface color onto the underside of the object. Objects must never appear to float, hover or sink, and shadows must always connect to the thing that casts them.""",
    # 18
    """Background architecture and landscape. Keep the background simple enough to support the hero but detailed enough to feel real. Architecture should have correct structure: visible beams, lintels, sills, trim and joints, with plausible wear where hands, feet and weather touch it. Landscapes should have layered structure, with believable geology, plant communities and drainage, and a horizon that sits at a deliberate height. Distant buildings and hills should simplify into clean shapes with reduced contrast, not into noise. Avoid generic repeated windows, cloned trees and symmetric fantasy structures. Let the background carry the project's design vocabulary quietly, so that it explains the world of the hero without competing with it.""",
    # 19
    """Props, wear and imperfection. Perfectly clean, perfectly symmetrical scenes look synthetic. Add tasteful imperfection with intent: slightly uneven stacking, a lightly rumpled fabric, fingerprints on a glass, a few crumbs, chipped paint at a corner, soft dust on a high shelf, a plant leaf with one browned tip. Keep the amount low and the placement natural, concentrating wear where real use would create it, such as handles, edges, steps and seating. Imperfections must be consistent with the established age and care of the place, and must never read as damage, dirt or neglect that undermines the premium positioning of the project.""",
]

# ---------------------------------------------------------------------------
# Still-image sections.
# ---------------------------------------------------------------------------
_STILL = [
    """Focal hierarchy for a still. A still is read in a few seconds, so decide the order in which the eye should travel and build the image to enforce it: first the hero, {motif}, then the element that explains where it is, then the quiet detail that rewards a second look. Control that order with contrast, size, saturation and sharpness, not with arrows or outlines. Place the second read on the opposite side of the hero from the leading lines so the eye has a path to travel, and make the third read small, soft and low in contrast so it never competes. Check that the image still works in a small thumbnail: the hero silhouette should remain clear when the picture is shrunk, with a clean separation between its outline and the background tone behind it.""",
    """Cropping discipline. This frame will be cropped to a wide landscape format and also to a tall portrait format by the page layout. Compose with a generous margin on every side so that no key element sits within the outer edge band, and keep the hero and its immediate context inside a central region that survives both crops. Let background architecture, horizon lines and ground planes continue past the edges of the frame, since the picture should feel like a window onto a larger space rather than a closed vignette. Avoid placing the hero exactly at the dead center, which makes the layout feel static, and avoid placing it so close to an edge that a crop would cut it.""",
    """Boundary frame discipline. When this image is used as the opening or closing frame of a moving shot, it has to be a clean, stable starting or ending point: the camera position, lens and light must be exactly what the shot needs at that instant, with the hero in a calm, unambiguous pose and no motion blur smearing the main subject. Leave consistent room in the direction of the move so the camera can travel there, and keep the geometry simple enough that a video model can continue it without inventing new structure. Depth planes should be clearly separated, so parallax during the move reveals real layers instead of a flat cardboard cut-out.""",
    """Reference fidelity. If reference images are supplied, treat them as binding: reproduce the identity, proportions, palette, material finish and design vocabulary of the references, and change only what this prompt explicitly asks to change. Do not average the references into a generic compromise and do not restyle them. Where the reference and the prompt disagree on a detail that matters for continuity, the reference wins; where the prompt introduces something the reference does not show, design it so it looks as though it was photographed on the same set on the same day, with the same lens, light and grade.""",
    """Detail budget for a still. Spend resolution where the eye will look: the hero, the faces or key surfaces next to it, and the focal edge where sharp meets soft. Describe those regions richly, with real material information, and let the rest simplify gracefully. A single hero with convincing fine detail is worth more than a frame full of uniform, undifferentiated texture. Keep detail density consistent with the optical distance, so nothing far away is sharper than something near, and keep the transition from detailed to simplified areas smooth and natural.""",
    """Pose and gesture in a still. If a person or animal is the hero, freeze a believable instant with no motion blur on the main subject: weight clearly on one leg, a hand in the middle of a natural gesture, eyes directed at something specific, and a face relaxed in a genuine, small expression. Avoid stiff, symmetrical, camera-aimed poses. Let clothing and hair show the preceding motion, with a slight asymmetry, and keep the silhouette of the pose readable against the background.""",
]

# ---------------------------------------------------------------------------
# Motion sections.
# ---------------------------------------------------------------------------
_MOTION = [
    """Camera path and easing. The camera moves {cam_move} at {cam_speed} speed, travelling from {cam_start} to {cam_end}. Describe the move as one continuous physical gesture: a single path through space with a smooth start, a steady middle and a smooth settle, with no jitter, no sudden speed changes, no hunting zooms and no reversals of direction. The move should feel like a real camera on a dolly, slider, crane or gimbal, with the slight inertia that real equipment has, and not like a digital zoom. Keep the horizon stable and keep vertical lines vertical unless the move itself changes pitch. The speed should be slow enough that every detail in the frame can be read as it passes, and consistent from the first frame to the last, because the clip will be scrubbed by the visitor scrolling the page and any speed change will feel like a glitch.""",
    """Parallax and three dimensional depth. As the camera moves, nearer objects must slide across the frame faster than distant ones, with correct occlusion: foreground elements pass in front of the hero and reveal new background behind it, edges disoccluding without smearing or stretching. Treat the scene as a real volume with a floor, walls, furniture and sky at believable distances, and let perspective lines converge or diverge exactly as the camera position implies. Do not slide a flat image sideways, do not warp the picture like a liquid, and do not let the background swim relative to the foreground. Where the move reveals area that was not visible in the opening frame, invent it from the same design vocabulary, materials and light so that the new area looks like it was always there.""",
    """Temporal consistency. Every object keeps its shape, size, color and texture from the first frame to the last. Avoid flicker in light, shimmer in fine textures, crawling patterns in fabric or foliage, breathing walls, morphing faces, melting edges, and objects that appear, vanish or change count between frames. Shadows must move correctly with the camera and the light, reflections must update plausibly, and highlight positions must change smoothly as the angle changes. If people or animals are present, keep the identity and wardrobe stable and let any motion be small, natural and purposeful, such as a slow breath, a blink, a turn of the head or a hand settling, rather than large, theatrical gestures that a video model cannot hold together.""",
    """Subject motion and life in the scene. The hero, {motif}, stays the anchor of the shot. If it moves, it moves with weight and intent: acceleration and deceleration follow physics, fabric and hair respond to the motion with slight delay, and contact with the ground or other surfaces is plausible. Add only quiet ambient motion elsewhere, such as drifting dust in a light beam, a gentle sway of leaves, steam rising from a cup, slow cloud movement, or a soft shimmer on water, each of which should move at a speed consistent with the rest of the world and none of which should draw attention away from the hero or from the camera move. Avoid sudden events, fast cuts inside the shot, explosions, flashes and strobing, which break the continuity needed for scroll scrubbing.""",
    """Start and end frame fidelity. The first frame of the clip must match the supplied opening image as exactly as possible in composition, subject placement, lighting and color, and the last frame must settle into the supplied closing image in the same way. Do not invent a different set, a different time of day or a different style between them. Spend the full duration moving from one to the other along a single believable path, arriving at the final composition at the end of the clip and not earlier, so that the last frames are not static padding. If the two frames are the same scene at two camera positions, the clip is the straight, continuous camera path between those positions through the same space.""",
    """Scroll-scrub suitability. The clip will be played forward and backward by the visitor's scroll position, so every frame should stand on its own as a good image and every pair of adjacent frames should differ only by a small, smooth step. Avoid effects that only make sense in forward playback, such as motion blur direction cues, falling objects, pouring liquids, or smoke trails, and avoid any beat that needs time to build, such as a slow fade in from black. No hard cuts, no whip pans, no title cards, no on-screen text, no fades at the beginning or the end, and no letterbox bars. Keep audio considerations out of the picture: no visible speakers, no lip-synced speech, and no musical performance, since the clip plays silent behind page copy.""",
    """Lens behaviour during the move. Keep the focal length constant through the clip: the change of framing comes from the camera travelling, never from a zoom. Maintain focus on the hero plane throughout, with the depth of field behaving exactly as the lens and the changing distance imply: as the camera approaches, the focus plane stays on the hero and the background softens a little more; as it retreats, more of the scene comes into focus. Avoid focus hunting, breathing of the framing, and sudden shifts of the focus plane. Keep exposure steady, with any change in brightness coming only from the physical change of what the lens is looking at, and keep white balance fixed so the grade does not drift during playback.""",
    """Light changes during the move. The sources of light stay where they are in the world, and the way they fall on surfaces changes only because the camera has moved. Specular highlights slide across glossy surfaces as the angle changes, shadows rotate with the viewpoint, and reflections update. Do not animate the lights themselves, flicker practical lamps, or pulse the exposure. Backlit edges may gain or lose a little rim light as the angle opens and closes, and a soft shaft of light may cross the frame, but both must be gradual and consistent with a single sun, window or lamp, matching the lighting logic given above.""",
    """Pacing across the duration. Divide the clip into a gentle opening in which the viewer settles on the starting composition, a steady middle in which the move and the reveal unfold at a constant rate, and a calm close in which the final composition arrives and holds for the last few frames. Do not front-load the action or crowd the end. Keep the amount of new visual information per second low and steady, so that the clip stays readable at any scroll speed, and so that the motion feels premium and unhurried. Whatever the length of the clip, it contains exactly one move and one idea.""",
]

_CONNECTOR = [
    """Connector transition. This clip joins {from_motif} to {to_motif} without a cut. Begin on the exact last frame of the preceding scene and end on the exact first frame of the next scene, and carry the same camera direction, speed, lens and light through the hand-off so the viewer feels one continuous move through a single connected world. The next scene should enter as a softly blurred, partially visible frame edge growing in sharpness and size as the move proceeds, and the previous scene should fall away behind the camera with natural parallax. Keep the three dimensional depth of the move obvious throughout, so the transition reads as travelling through space rather than as a dissolve between two pictures, and keep the light logic and material language of both scenes legible across the hand-off.""",
]


def _fill(sections: List[str], ctx: Dict[str, str]) -> List[str]:
    return [s.format(**ctx) for s in sections]


def image_sections(style: Dict[str, Any], scene: Optional[Dict[str, Any]] = None) -> List[str]:
    """Direction sections for a still (concept board, anchor, scene and boundary stills)."""
    ctx = _ctx(style, scene)
    return _fill(_SHARED[:4] + _STILL[:1] + _SHARED[4:8] + _STILL[1:3] + _SHARED[8:12] + _STILL[3:] + _SHARED[12:], ctx)


def video_sections(
    style: Dict[str, Any],
    scene: Optional[Dict[str, Any]] = None,
    to_scene: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """Direction sections for a clip (draft, final scene clip, connector). Pass ``to_scene`` for a connector."""
    extra = {}
    if to_scene is not None:
        extra = {"from_motif": (scene or {}).get("visual_motif", "the previous scene"), "to_motif": to_scene.get("visual_motif", "the next scene")}
    ctx = _ctx(style, scene, extra)
    ordered = (_CONNECTOR if to_scene is not None else []) + _MOTION[:2] + _SHARED[:4] + _MOTION[2:4] + _SHARED[4:8] + _MOTION[4:] + _SHARED[8:]
    return _fill(ordered, ctx)
