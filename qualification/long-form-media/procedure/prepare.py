#!/usr/bin/env python3
"""W4-01-U1 long-form payload builder. Stdlib only. Reads nothing governed.

Writes production inputs under qualification/long-form-media/ (owned output).
No network, no spend, no dispatch.

Target: 63s drama-song ad (directive band 60-90s), 3 shots x 21s,
9:16 vertical, one keyframe image reused as first frame on every shot so
character continuity is a property of the generation inputs, not a hope.
"""
import json
import os
import sys

BROOT = os.environ.get("DTS_BUILD_ROOT", os.getcwd())
OUT = os.path.join(BROOT, "qualification", "long-form-media")
EV = os.path.join(OUT, "evidence")
REQ = os.path.join(OUT, "requests")
TIM = os.path.join(OUT, "timing")
SHP = os.path.join(OUT, "shots")

RUN = "w4-long"
TARGET_S = 63
SHOT_S = 21
N_SHOTS = 3
PROFILE = "long-9x16-60s"
CEILING = 5000  # run-row ceiling, USD-cents (program ceiling $50 total)

# ---------------------------------------------------------------- campaign
# campaign.brief is what lyric_writer validates against: it must be the text
# that is actually sung, not the intake brief.
BRIEF_INNER = {
    "product_name": "BlackCEO Drama Song Ad Factory",
    "offer_text": "BlackCEO Drama Song Ad Factory demo",
    "cta_text": "Visit blackceo dot com and book the demo",
    "claims": [],
}

LYRICS = [
    {"line_id": "hook01", "critical": True,
     "pronunciation_map": {"BlackCEO": "Black C E O", "Drama": "Drama",
                           "Song": "Song"},
     "text": "I sing my BlackCEO Drama Song"},
    {"line_id": "hook02", "critical": True,
     "pronunciation_map": {"Factory": "Factory"},
     "text": "I built this Factory demo for owners"},
    {"line_id": "hook03", "critical": False,
     "text": "I feel the rhythm lift my day"},
    {"line_id": "verse01", "critical": False,
     "text": "I keep the beat rolling in my heart"},
    {"line_id": "verse02", "critical": False,
     "text": "I turn my shop story into music"},
    {"line_id": "verse03", "critical": False,
     "text": "I watch my customers nod along"},
    {"line_id": "verse04", "critical": True,
     "pronunciation_map": {"Drama": "Drama", "Song": "Song"},
     "text": "I let the Drama Song carry my pitch"},
    {"line_id": "cta01", "critical": True,
     "pronunciation_map": {"BlackCEO": "Black C E O"},
     "text": "Visit BlackCEO dot com and book the demo"},
    {"line_id": "cta02", "critical": False,
     "text": "Hear what your brand sounds like sung"},
    {"line_id": "cta03", "critical": False,
     "text": "Start today and let the tune travel"},
    {"line_id": "cta04", "critical": True,
     "pronunciation_map": {"BlackCEO": "Black C E O", "Drama": "Drama",
                           "Song": "Song", "Factory": "Factory"},
     "text": "BlackCEO Drama Song Ad Factory starts here"},
    {"line_id": "cta05", "critical": True,
     "text": "Book the demo before the week ends"},
]

# Generation spelling (pronunciation maps applied; spelling only).
def mapped(line):
    text = line["text"]
    for k, v in (line.get("pronunciation_map") or {}).items():
        text = text.replace(k, v)
    return text


MAPPED_LYRICS = "\n".join(mapped(l) for l in LYRICS)

STYLE = (
    "Upbeat contemporary R&B with gospel-tinged backing vocals, warm Rhodes "
    "chords, a finger-snapped backbeat and a rounded sub-bass. Mid-tempo "
    "groove around 96 BPM in a bright major key, handclaps on the two and "
    "four, string pads under the chorus. The lead vocal is a clear "
    "confident alto singing in the first person, close-miked and lightly "
    "doubled in the chorus so every word stays intelligible on a phone "
    "speaker. The arrangement builds from a sparse verse into a full "
    "sing-along chorus, leaves air around the vocal on the call-to-action "
    "line, and finishes on a clean sustained chord with no long "
    "instrumental tail. Low end stays tight, hi-hats sit soft and slightly "
    "behind the grid, and a two-bar intro sets the tempo before the first "
    "lyric lands. Sixty-three seconds total: a three-line hook, a "
    "four-line verse, then a five-line call-to-action close that lands the "
    "last line on the final beat."
)

TITLE = "BlackCEO Drama Song Ad Factory 60s"

# --------------------------------------------------------- intake fixtures
# Written by phase "prepare-intake" of long_run.py, not here: the summary
# digest has to exist before settings.authorization.scope can bind to it.

# --------------------------------------------------------------- keyframe
KEYFRAME_PROMPT = (
    "Vertical 9:16 key visual for a promotional music video made by the "
    "BlackCEO Drama Song Ad Factory. The frame centres on a confident Black "
    "woman small-business owner standing just inside the open doorway of her "
    "neighbourhood shop at golden hour, phone held loosely in one hand, "
    "mid-laugh, as if she has just sung a line and is waiting for the take "
    "to be called again. Warm late-afternoon sun rakes in from camera left "
    "and throws long soft shadows across a scuffed concrete floor, catching "
    "dust in the air. Behind her, hand-painted signage in brush script sits "
    "above a wooden counter, and a small ring light on a low stand plus a "
    "phone clamped to a compact tripod sit just off frame at the edge of the "
    "shot, so the viewer understands the advertisement is being made in the "
    "room rather than staged in a studio. She wears a soft cream knit "
    "overshirt over a plain tee, simple gold hoops and a thin chain, hair "
    "worn natural and catching the rim light, makeup minimal and skin "
    "luminous with visible pores and fine texture. Her weight sits on one "
    "hip, shoulders relaxed, chin slightly lifted, eyes bright and engaged "
    "with the lens, one hand open and expressive while the other holds the "
    "phone at chest height. The shop interior reads in three layers: the "
    "doorway and subject in the foreground, the counter and shelving with "
    "stacked product boxes in the mid-ground, and a softly blurred back wall "
    "with a taped-up running order and a small potted plant in the "
    "background. A laptop on the counter shows a plain booking page, softly "
    "out of focus, so the product appears without legible text. The key "
    "light is the low sun through the door, a cool bounce fills the shadow "
    "side, and the ring light adds a small catchlight so the eyes stay "
    "alive. The colour palette is warm amber, deep teal and soft cream, "
    "with a gentle filmic contrast that keeps skin tones rich and luminous "
    "and the highlights rolled off rather than clipped. Shot on a "
    "35mm-equivalent lens at a shallow but readable depth of field, the "
    "subject crisp and the shop interior softly falling away behind her, "
    "horizon level, camera at chest height. Composition leaves clear "
    "negative space in the lower third for a caption and in the upper third "
    "for a title, both unobstructed at phone width, with the subject placed "
    "slightly off-centre on the upper third line. The vertical frame is "
    "composed for a phone screen: nothing important sits within a "
    "thumb-width of either edge, the eyeline falls in the upper half so a "
    "platform interface never covers her face. Photorealistic rendering, "
    "natural skin texture, realistic lighting falloff, subtle film grain, "
    "high dynamic range, no text, no lettering, no logos, no watermarks, no "
    "brand marks, no extra limbs, no distorted hands, no warped background "
    "geometry, no duplicated faces, no floating objects. The subject keeps "
    "a single continuous silhouette with no doubled shoulders, the doorway "
    "edges stay parallel rather than bowing, and the shelving behind her "
    "keeps straight lines with no melted geometry."
)

# ------------------------------------------------------------------ shots
WARDROBE = ["ward-knit-cream-tee", "ward-gold-hoops-thin-chain"]
CHAR_ID = "char-owner-shop"

CAMERA = {
    1: "locked-off medium shot, camera static at chest height",
    2: "slow push-in from medium to medium close-up",
    3: "slow pull-back from medium close-up to wide",
}
OBJECTIVE = {
    1: "Land the sung hook on her face in the doorway so the product name "
       "arrives with a person, not a logo",
    2: "Show the booking laptop on the counter while she keeps singing so "
       "the offer has a place in the room",
    3: "Open the frame to the whole shop as she delivers the call to "
       "action so the viewer sees where the demo leads",
}
STORY_STAGE = {
    1: "hook",
    2: "offer",
    3: "call to action",
}
LOCATION = {
    1: "shop-doorway",
    2: "shop-counter",
    3: "shop-floor-wide",
}
PRODUCT_VIS = {1: "background", 2: "featured", 3: "hero"}
LYRIC_IDS = {
    1: ["hook01", "hook02", "hook03"],
    2: ["verse01", "verse02", "verse03", "verse04"],
    3: ["cta01", "cta02", "cta03", "cta04", "cta05"],
}
WINDOW = {1: (0.0, 21.0), 2: (21.0, 42.0), 3: (42.0, 63.0)}

# 1080P wan/3-0-video: 32 credits/s max tier -> 21s = 672 credits = 336 cents.
SHOT_COST_CENTS = 336

CONTRACTS = {
    1: {
        "lyric_text": "I sing my BlackCEO Drama Song / I built this Factory "
                      "demo for owners / I feel the rhythm lift my day",
        "viewer_understanding": "A real shop owner is singing the product "
                                "name in her own doorway",
        "character_action": "She sings straight to the lens and holds the "
                            "phone at chest height",
        "visible_emotion": "joyful",
        "change_from_prior": "Opening frame, no prior shot",
        "treatment": "literal-repeat",
        "necessity": "The hook line names the product, so the first shot "
                     "must carry it",
    },
    2: {
        "lyric_text": "I keep the beat rolling in my heart / I turn my shop "
                      "story into music / I watch my customers nod along / "
                      "I let the Drama Song carry my pitch",
        "viewer_understanding": "The offer sits on the counter of the same "
                                "shop she just sang in",
        "character_action": "She steps to the counter and gestures toward "
                            "the laptop while she keeps singing",
        "visible_emotion": "confident",
        "change_from_prior": "She moves from the doorway to the counter and "
                             "the laptop enters frame",
        "treatment": "contextual-contrast",
        "necessity": "The offer line needs a visible place for the demo to "
                     "happen",
    },
    3: {
        "lyric_text": "Visit BlackCEO dot com and book the demo / Hear what "
                      "your brand sounds like sung / Start today and let "
                      "the tune travel / BlackCEO Drama Song Ad Factory "
                      "starts here / Book the demo before the week ends",
        "viewer_understanding": "Booking the demo is the next step and the "
                                "whole shop is behind the ask",
        "character_action": "She opens her arms to the room and finishes "
                            "the last line on a held smile",
        "visible_emotion": "inviting",
        "change_from_prior": "The frame widens from her to the whole shop",
        "treatment": "metaphor-amplify",
        "necessity": "The call to action closes the ad and must hold the "
                     "final beat",
    },
}

QC_REQS = [
    "character identity matches the keyframe in every frame",
    "wardrobe identical across all three shots",
    "no burned-in text, captions or logos",
    "clip duration within one frame of the planned window",
    "lower third stays clear for a caption",
]

CHARACTER = {
    "schema_version": "1.0.0",
    "character_id": CHAR_ID,
    "age_band": "30-40",
    "skin_tone_complexion": "deep brown, warm undertone, luminous",
    "facial_structure": "oval face, high cheekbones, rounded chin",
    "eyes": "dark brown, bright, engaged with the lens",
    "nose": "broad bridge, softly rounded tip",
    "mouth": "full lips, wide laugh lines",
    "hair": "natural coils worn loose, catching the rim light",
    "body_build": "average build, relaxed posture, weight on one hip",
    "distinguishing_features": "small gold hoop earrings and a thin chain",
    "wardrobe_rules": "soft cream knit overshirt over a plain tee; never "
                      "changes between shots",
    "expression_range": ["joyful", "confident", "inviting"],
    "prohibited_drift": ["no wardrobe change between shots",
                         "no hair colour change",
                         "no jewellery change"],
    "accessories": ["thin gold chain", "plain phone case"],
    "approved_reference_asset_ids": ["asset-keyframe-01"],
}


def build_music_request():
    return {
        "endpoint": "/api/v1/jobs/createTask",
        "model": "ai-music-api/generate",
        "input": {
            "custom_mode": True,
            "instrumental": False,
            "model": "V6",
            "style": STYLE,
            "title": TITLE,
            "lyrics": MAPPED_LYRICS,
            "prompt": MAPPED_LYRICS,
            "duration": TARGET_S,
        },
    }


def build_image_request():
    return {
        "model": "google/imagen4-fast",
        "input": {
            "prompt": KEYFRAME_PROMPT,
            "aspect_ratio": "9:16",
            "n": 1,
        },
        "timeout": 300,
    }


VIDEO_BODY = {
    1: "She sings the opening hook straight to the lens in the open "
       "doorway, phone still held loosely in one hand, and holds a warm "
       "smile on the last word. The camera stays locked off at chest "
       "height with no push and no pull, so the frame never moves. Warm "
       "late-afternoon light rakes in from camera left, dust drifting "
       "through the beam. Background movement is limited to drifting dust "
       "and a slight curtain sway. Performance beats: frames one to "
       "twenty hold a relaxed open pose while she draws breath, the "
       "middle carries the sung lines with natural jaw and brow movement, "
       "and the final frames hold still for a clean cut.",
    2: "She steps to the wooden counter where a laptop sits open on a "
       "plain booking page, keeps singing, and gestures once toward the "
       "laptop with an open hand. The camera pushes in slowly and evenly "
       "from a medium shot to a medium close-up on a 35mm-equivalent "
       "lens. Warm afternoon light from camera left, a cool bounce fills "
       "the shadow side, a ring light adds a catchlight. Background "
       "movement is limited to drifting dust and a slight sway of a "
       "paper sign. Focus stays locked on her eyes through the push-in "
       "with no hunting, exposure stays constant with no flicker, and the "
       "final frames settle for a clean cut.",
    3: "She finishes the call to action with both arms opening toward "
       "the room and holds a wide inviting smile on the last line. The "
       "camera pulls back evenly from a medium close-up to a wide shot "
       "that reveals the whole shop floor, doorway and counter in one "
       "readable composition. Warm late-afternoon key with a cool teal "
       "fill, gentle filmic contrast. Background movement is limited to "
       "drifting dust and a slow curtain sway. Focus stays locked on her "
       "eyes as the frame widens, exposure holds constant, and the clip "
       "ends on a held composition with the lower third clear.",
}


def video_prompt(n):
    common = (
        "Vertical 9:16 clip for a promotional music video made by the "
        "BlackCEO Drama Song Ad Factory, continuing from a single "
        "photographic first frame so the character, wardrobe and shop stay "
        "identical to the frame before it. A confident Black woman "
        "small-business owner in a soft cream knit overshirt over a plain "
        "tee, simple gold hoops and a thin chain, hair worn natural and "
        "catching the rim light, skin luminous with visible texture. The "
        "shop interior reads in three layers: doorway and subject in the "
        "foreground, wooden counter with stacked plain unbranded boxes in "
        "the mid-ground, softly blurred back wall with a taped-up running "
        "order and a small potted plant behind. Wardrobe detail stays "
        "consistent throughout: cream knit weave visible, gold hoops "
        "catching a warm highlight, thin chain at the collarbone, plain "
        "phone case in her left hand with a dark screen. Hair keeps its "
        "natural shape, skin shows real pores and a soft highlight along "
        "the cheekbone rather than a plastic finish. Hair, hands and "
        "jewellery stay anatomically correct in every frame with no "
        "merging fingers and no changing ear shapes. Colour palette of "
        "warm amber, deep teal and soft cream, gentle filmic contrast, "
        "subtle grain, photorealistic. The clip plays as one continuous "
        "take with no visible cuts, no sudden jumps in framing, and no "
        "shift in colour temperature between the first and last frame. "
        "Motion reads as a natural shutter rather than stepping, with no "
        "rolling-shutter wobble on the doorway edges. The frame is "
        "composed for a phone screen with nothing important within a "
        "thumb-width of either edge, the lower third stays clear for a "
        "caption and the upper third stays clear for a title. "
    )
    motion = (
        "Motion is steady with no whip pans and no sudden camera moves. "
    )
    tail = (
        "Photorealistic, natural skin texture, realistic lighting falloff, "
        "subtle film grain, high dynamic range, no text, no lettering, no "
        "logos, no watermarks, no brand marks, no extra limbs, no "
        "distorted hands, no duplicated faces, no floating objects, no "
        "warped background geometry. Natural micro-movement, believable "
        "hand and finger detail, consistent facial identity from first "
        "frame to last."
    )
    return common + motion + VIDEO_BODY[n] + " " + tail


def build_video_request(n):
    return {
        "model": "wan/3-0-video",
        "input": {
            "prompt": video_prompt(n),
            "duration": SHOT_S,
            "resolution": "1080P",
            "aspect_ratio": "9:16",
            "audio": False,
        },
        "timeout": 900,
    }


def build_router_request(n):
    return {
        "capabilities": ["image-to-video", "duration", "resolution"],
        "duration_seconds": SHOT_S,
        "resolution": "1080P",
        "aspect_ratio": "9:16",
        "audio": "disabled",
        "pin": "wan/3-0-video",
        "prompt_chars": len(video_prompt(n)),
        "reference_images": 1,
    }


TIMING_MAP = {
    "song_id": "w4-long-master",
    "duration_seconds": TARGET_S,
    "sections": [
        {"section_id": "hook", "start": 0.0, "end": 21.0, "lyrics": [
            {"line_id": "hook01", "start": 0.0, "end": 7.0,
             "text": LYRICS[0]["text"]},
            {"line_id": "hook02", "start": 7.0, "end": 14.0,
             "text": LYRICS[1]["text"]},
            {"line_id": "hook03", "start": 14.0, "end": 21.0,
             "text": LYRICS[2]["text"]},
        ]},
        {"section_id": "verse", "start": 21.0, "end": 42.0, "lyrics": [
            {"line_id": "verse01", "start": 21.0, "end": 26.0,
             "text": LYRICS[3]["text"]},
            {"line_id": "verse02", "start": 26.0, "end": 31.0,
             "text": LYRICS[4]["text"]},
            {"line_id": "verse03", "start": 31.0, "end": 36.0,
             "text": LYRICS[5]["text"]},
            {"line_id": "verse04", "start": 36.0, "end": 42.0,
             "text": LYRICS[6]["text"]},
        ]},
        {"section_id": "cta", "start": 42.0, "end": 63.0, "lyrics": [
            {"line_id": "cta01", "start": 42.0, "end": 49.0,
             "text": LYRICS[7]["text"]},
            {"line_id": "cta02", "start": 49.0, "end": 54.0,
             "text": LYRICS[8]["text"]},
            {"line_id": "cta03", "start": 54.0, "end": 58.0,
             "text": LYRICS[9]["text"]},
            {"line_id": "cta04", "start": 58.0, "end": 61.0,
             "text": LYRICS[10]["text"]},
            {"line_id": "cta05", "start": 61.0, "end": 63.0,
             "text": LYRICS[11]["text"]},
        ]},
    ],
}


def shot(n):
    s, e = WINDOW[n]
    return {
        "shot_id": "shot-0%d" % n,
        "song_start": s,
        "song_end": e,
        "lyric_line_ids": list(LYRIC_IDS[n]),
        "story_stage": STORY_STAGE[n],
        "visual_objective": OBJECTIVE[n],
        "character_ids": [CHAR_ID],
        "wardrobe_ids": list(WARDROBE),
        "location_id": LOCATION[n],
        "product_visibility": PRODUCT_VIS[n],
        "camera_direction": CAMERA[n],
        "reference_assets": ["asset-keyframe-01"],
        "image_model_capability_request": {
            "capabilities": ["text-to-image", "aspect-ratio-9x16"]},
        "video_model_capability_request": {
            "capabilities": ["image-to-video", "duration", "resolution"]},
        "continuity_constraints": [
            "same keyframe image is the first frame of this clip",
            "wardrobe identical to the preceding shot",
            "one continuous take, no internal cut",
        ],
        "negative_constraints": [
            "no burned-in text",
            "no logos or watermarks",
            "no extra limbs or distorted hands",
            "no wardrobe change",
        ],
        "cost_estimate": SHOT_COST_CENTS,
        "qc_requirements": list(QC_REQS),
        "status": "planned",
    }


def w(obj, rel):
    path = os.path.join(OUT, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, sort_keys=True, ensure_ascii=False)
    return path


def main():
    campaign = {
        "schema_version": "1.0.0",
        "campaign_id": RUN,
        "run_id": RUN,
        "aspects": ["9:16"],
        "target_duration_s": TARGET_S,
        "brief": dict(BRIEF_INNER),
        "lyrics": LYRICS,
        "lyrics_provenance": {
            "source": "builder-authored from the W4-01 brief; same product, "
                      "offer and CTA text proven by the W3-04 short run",
            "human_lyric_signoff": "none recorded; lyric_writer validate "
                                   "gates sung-copy rules only",
        },
    }
    shots = [shot(n) for n in range(1, N_SHOTS + 1)]
    contracts = {"shot-0%d" % n: CONTRACTS[n] for n in range(1, N_SHOTS + 1)}
    outs = {
        "campaign.json": w(campaign, "campaign.json"),
        "timing/timing-map.json": w(TIMING_MAP, "timing/timing-map.json"),
        "shots/shots.json": w(shots, "shots/shots.json"),
        "shots/contracts.json": w(contracts, "shots/contracts.json"),
        "shots/characters.json": w([CHARACTER], "shots/characters.json"),
        "requests/music-request.json": w(build_music_request(),
                                         "requests/music-request.json"),
        "requests/image-request.json": w(build_image_request(),
                                         "requests/image-request.json"),
    }
    for n in range(1, N_SHOTS + 1):
        outs["requests/video-shot-0%d-request.json" % n] = w(
            build_video_request(n), "requests/video-shot-0%d-request.json" % n)
        outs["requests/router-shot-0%d-request.json" % n] = w(
            build_router_request(n),
            "requests/router-shot-0%d-request.json" % n)

    report = {
        "run_id": RUN,
        "target_duration_s": TARGET_S,
        "shots": N_SHOTS,
        "shot_seconds": SHOT_S,
        "mapped_lyric_chars": len(MAPPED_LYRICS),
        "style_chars": len(STYLE),
        "keyframe_prompt_chars": len(KEYFRAME_PROMPT),
        "video_prompt_chars": {str(n): len(video_prompt(n))
                               for n in range(1, N_SHOTS + 1)},
        "profile": PROFILE,
        "ceiling_cents": CEILING,
        "files": {k: os.path.getsize(v) for k, v in outs.items()},
    }
    print(json.dumps(report, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
