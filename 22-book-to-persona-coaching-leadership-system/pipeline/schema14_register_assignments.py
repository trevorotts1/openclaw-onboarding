#!/usr/bin/env python3
"""
A-U3 schema-1.4 backfill assignment map.

WHY a hand-reviewed map, not a keyword classifier: the spec (A-U3) requires
these fields be "synthesized from the blueprint + book source, never invented
from the name." Every value below was assigned by reading THIS persona's own
already-catalogued voice_style.tone[]/devices[]/cadence/avoid[] (the v6.17.0
one-time backfill's synthesis output — itself grounded in each book's
extraction/analysis notes) and domain[] — not from the persona's name/author
alone. The map is reviewable line-by-line against that same source data (see
backfill-schema14-registers.py --explain), auditable, and idempotent.

Vocab (closed, curated, and — per A-U3 — vocab-checked by
persona_blend.validate_catalog_tags once shipped in the catalog's
emotionalRegisterTags / audienceResonanceTags / conversionStyleTags):

emotional_register (14): tough-love, warm-encouragement, data-calm,
  righteous-fire, playful-irreverence, reflective-stillness, fierce-clarity,
  steady-reassurance, urgent-drive, compassionate-directness,
  analytical-detachment, bold-confrontation, grounded-humility,
  visionary-inspiration

audience_resonance (12): seen-and-understood, challenged-to-rise,
  validated-not-alone, given-permission, sparked-to-action,
  calmed-and-grounded, equipped-and-capable, confronted-with-truth,
  inspired-to-dream-bigger, relieved-of-overwhelm, respected-as-smart,
  awakened-to-blind-spots

conversion_style (5, operator-pinned canonical set per A-U3 spec):
  story-close, stack-close, logic-close, invitation-close, challenge-close
"""

# slug -> (emotional_register, audience_resonance, conversion_style)
ASSIGNMENTS = {
    "allan-dib-the-1-page-marketing-plan": ("fierce-clarity", "equipped-and-capable", "logic-close"),
    "attwood-passion-test": ("visionary-inspiration", "inspired-to-dream-bigger", "invitation-close"),
    "bly-copywriters-handbook": ("data-calm", "equipped-and-capable", "stack-close"),
    "brown-atlas-of-heart": ("compassionate-directness", "seen-and-understood", "story-close"),
    "charvet-words-change-minds": ("fierce-clarity", "respected-as-smart", "logic-close"),
    "cialdini-influence": ("analytical-detachment", "respected-as-smart", "logic-close"),
    "clear-atomic-habits": ("data-calm", "equipped-and-capable", "invitation-close"),
    "collins-good-to-great": ("fierce-clarity", "confronted-with-truth", "logic-close"),
    "collins-good-to-great-summary": ("fierce-clarity", "confronted-with-truth", "logic-close"),
    "duhigg-power-of-habit": ("analytical-detachment", "equipped-and-capable", "logic-close"),
    "forte-building-second-brain": ("steady-reassurance", "relieved-of-overwhelm", "invitation-close"),
    "forte-para-method": ("steady-reassurance", "relieved-of-overwhelm", "invitation-close"),
    "godin-this-is-marketing": ("fierce-clarity", "awakened-to-blind-spots", "invitation-close"),
    "goggins-cant-hurt-me": ("bold-confrontation", "challenged-to-rise", "challenge-close"),
    "grenny-crucial-conversations": ("steady-reassurance", "equipped-and-capable", "invitation-close"),
    "grover-relentless": ("bold-confrontation", "challenged-to-rise", "challenge-close"),
    "hormozi-100m-leads": ("urgent-drive", "sparked-to-action", "stack-close"),
    "hormozi-100m-offers": ("urgent-drive", "sparked-to-action", "stack-close"),
    "jakes-instinct": ("visionary-inspiration", "inspired-to-dream-bigger", "story-close"),
    "jeremy-miner-the-nepq-black-book-of-questions": ("analytical-detachment", "respected-as-smart", "logic-close"),
    "jones-exactly-what-to-say": ("steady-reassurance", "equipped-and-capable", "invitation-close"),
    "kane-hook-point": ("urgent-drive", "sparked-to-action", "logic-close"),
    "lakhiani-extraordinary-mind": ("compassionate-directness", "challenged-to-rise", "challenge-close"),
    "michalowicz-profit-first": ("tough-love", "relieved-of-overwhelm", "stack-close"),
    "moran-12-week-year": ("urgent-drive", "challenged-to-rise", "challenge-close"),
    "obama-becoming": ("reflective-stillness", "seen-and-understood", "story-close"),
    "obama-light-we-carry": ("steady-reassurance", "calmed-and-grounded", "story-close"),
    "pink-drive": ("data-calm", "respected-as-smart", "logic-close"),
    "pink-to-sell-is-human": ("data-calm", "equipped-and-capable", "invitation-close"),
    "pink-when": ("data-calm", "equipped-and-capable", "logic-close"),
    "priestley-oversubscribed": ("fierce-clarity", "awakened-to-blind-spots", "logic-close"),
    "rackham-spin-selling": ("analytical-detachment", "respected-as-smart", "logic-close"),
    "robbins-five-second-rule": ("urgent-drive", "sparked-to-action", "challenge-close"),
    "robbins-let-them-theory": ("tough-love", "relieved-of-overwhelm", "invitation-close"),
    "russell-brunson-lead-funnels": ("urgent-drive", "sparked-to-action", "stack-close"),
    "russell-brunson-the-funnel-hackers-cookbook": ("data-calm", "equipped-and-capable", "stack-close"),
    "russell-brunson-traffic-secrets": ("urgent-drive", "inspired-to-dream-bigger", "story-close"),
    "samit-disrupt-yourself": ("bold-confrontation", "challenged-to-rise", "challenge-close"),
    "sharma-5am-club": ("visionary-inspiration", "inspired-to-dream-bigger", "story-close"),
    "sinek-find-your-why": ("warm-encouragement", "seen-and-understood", "invitation-close"),
    "sinek-start-with-why": ("righteous-fire", "inspired-to-dream-bigger", "story-close"),
    "tawwab-set-boundaries-find-peace": ("compassionate-directness", "validated-not-alone", "invitation-close"),
    "voss-never-split-difference": ("analytical-detachment", "equipped-and-capable", "logic-close"),
    "vsevolod-pudovkin-film-technique": ("analytical-detachment", "respected-as-smart", "logic-close"),
    "wiebe-copy-hackers": ("urgent-drive", "awakened-to-blind-spots", "logic-close"),
    "acuff-miner-new-model-of-selling": ("analytical-detachment", "respected-as-smart", "logic-close"),
    "brunson-marketing-secrets-blackbook": ("playful-irreverence", "inspired-to-dream-bigger", "story-close"),
    "brunson-network-marketing-secrets": ("warm-encouragement", "seen-and-understood", "story-close"),
    "edwards-copywriting-secrets": ("tough-love", "equipped-and-capable", "stack-close"),
    "leland-brand-mapping-strategy": ("playful-irreverence", "awakened-to-blind-spots", "story-close"),
    "miller-building-storybrand": ("fierce-clarity", "equipped-and-capable", "story-close"),
    "miller-coach-builder": ("warm-encouragement", "equipped-and-capable", "invitation-close"),
    "rohde-the-sketchnote-workbook": ("warm-encouragement", "given-permission", "invitation-close"),
    "pedro-adao-challenge-secrets-masterclass": ("righteous-fire", "inspired-to-dream-bigger", "challenge-close"),
    "cancel-conversational-marketing": ("fierce-clarity", "awakened-to-blind-spots", "invitation-close"),
    "wickman-rocket-fuel": ("fierce-clarity", "equipped-and-capable", "stack-close"),
    "ries-lean-startup": ("data-calm", "equipped-and-capable", "logic-close"),
    "kaufman-personal-mba": ("data-calm", "relieved-of-overwhelm", "logic-close"),
    "budelmann-brand-identity-essentials": ("steady-reassurance", "equipped-and-capable", "logic-close"),
    "opara-color-works": ("data-calm", "respected-as-smart", "logic-close"),
    "walker-launch": ("warm-encouragement", "given-permission", "story-close"),
    "miller-marketing-made-simple": ("fierce-clarity", "equipped-and-capable", "invitation-close"),
    "suby-sell-like-crazy": ("urgent-drive", "sparked-to-action", "stack-close"),
    "erikson-surrounded-by-idiots": ("warm-encouragement", "seen-and-understood", "invitation-close"),
    "gitomer-sales-bible": ("playful-irreverence", "sparked-to-action", "invitation-close"),
    "aliche-get-good-with-money": ("warm-encouragement", "validated-not-alone", "invitation-close"),
    "berger-contagious": ("data-calm", "respected-as-smart", "logic-close"),
    "carnegie-how-to-win-friends-digital-age": ("warm-encouragement", "seen-and-understood", "invitation-close"),
    "charvet-words-that-change-minds": ("compassionate-directness", "seen-and-understood", "invitation-close"),
    "covey-7-habits": ("tough-love", "challenged-to-rise", "invitation-close"),
    "duckworth-grit": ("tough-love", "challenged-to-rise", "logic-close"),
    "gallo-talk-like-ted": ("visionary-inspiration", "equipped-and-capable", "story-close"),
    "kahneman-thinking-fast-and-slow": ("analytical-detachment", "awakened-to-blind-spots", "logic-close"),
    "kimbro-the-wealth-choice": ("righteous-fire", "challenged-to-rise", "challenge-close"),
    "kimbro-what-makes-great-great": ("righteous-fire", "challenged-to-rise", "challenge-close"),
    "king-read-people-like-a-book": ("analytical-detachment", "equipped-and-capable", "logic-close"),
    "kleon-show-your-work": ("playful-irreverence", "given-permission", "invitation-close"),
    "michalowicz-clockwork": ("tough-love", "relieved-of-overwhelm", "stack-close"),
    "thiel-zero-to-one": ("bold-confrontation", "awakened-to-blind-spots", "logic-close"),
    "tolle-the-power-of-now": ("reflective-stillness", "calmed-and-grounded", "invitation-close"),
    "wickman-traction": ("tough-love", "equipped-and-capable", "stack-close"),
    "blackceo-house-voice": ("steady-reassurance", "seen-and-understood", "invitation-close"),
    "hunt-thomas-pragmatic-programmer": ("grounded-humility", "equipped-and-capable", "logic-close"),
    "brian-mark-10-million-instagram-funnel": ("urgent-drive", "sparked-to-action", "challenge-close"),
    "butow-instagram-facebook-all-in-one": ("steady-reassurance", "given-permission", "invitation-close"),
    "butow-ultimate-guide-social-media-marketing": ("warm-encouragement", "equipped-and-capable", "invitation-close"),
    "cialdini-pre-suasion": ("analytical-detachment", "respected-as-smart", "logic-close"),
    "collins-turning-the-flywheel": ("fierce-clarity", "confronted-with-truth", "logic-close"),
    "deziel-content-fuel-framework": ("warm-encouragement", "relieved-of-overwhelm", "invitation-close"),
    "duhigg-smarter-faster-better": ("steady-reassurance", "equipped-and-capable", "logic-close"),
    "duhigg-supercommunicators": ("compassionate-directness", "seen-and-understood", "invitation-close"),
    "ferri-growth-marketing": ("playful-irreverence", "sparked-to-action", "logic-close"),
    "flynn-superfans": ("warm-encouragement", "given-permission", "invitation-close"),
    "kane-one-million-followers": ("data-calm", "equipped-and-capable", "logic-close"),
    "king-the-art-of-witty-banter": ("playful-irreverence", "given-permission", "invitation-close"),
    "landing-page-conversion-essentials": ("fierce-clarity", "equipped-and-capable", "logic-close"),
    "thomas-instagram-performance-marketing": ("playful-irreverence", "awakened-to-blind-spots", "logic-close"),
    "thorne-youtube-unlocked": ("righteous-fire", "sparked-to-action", "challenge-close"),
    "video-funnels": ("warm-encouragement", "equipped-and-capable", "invitation-close"),
}

EMOTIONAL_REGISTER_TAGS = sorted({v[0] for v in ASSIGNMENTS.values()})
AUDIENCE_RESONANCE_TAGS = sorted({v[1] for v in ASSIGNMENTS.values()})
CONVERSION_STYLE_TAGS = sorted({v[2] for v in ASSIGNMENTS.values()})
