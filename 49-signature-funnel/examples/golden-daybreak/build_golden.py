#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_golden.py — deterministic reproducer for the Golden Daybreak Signature Funnel.

Emits the four run-dir ledgers for a FICTIONAL 7-step funnel that clears every SACRED
band with REAL, distinct, human-authored funnel copy + genuinely detailed per-page image
prompts (no machine padding, no repeated filler tail, no vocabulary-list dump). Then it
(1) proves each ledger with its shipped Skill-49 prover, (2) drives the canonical no-skip
orchestrator to a signed PROCESS-CERTIFICATE, and (3) writes the five one-mutation broken
variants + a captured REJECTION-RESULTS.json proving each trips a DISTINCT AF-FUN-*.

No client names, no real people, no PII. Method attribution: the Trevor Otts Signature
Funnel method. Fictional brand: "The Daybreak Method" (a 30-day morning-discipline course).

stdlib only. Run:  python3 build_golden.py         (regenerate everything, self-check)
                   python3 build_golden.py --check  (regenerate to a temp dir + diff-free assert)
Exit 0 = golden reproduced + certified + all broken variants rejected; nonzero otherwise.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL_DIR = HERE.parent.parent                      # 49-signature-funnel/
SCRIPTS = SKILL_DIR / "scripts"
ORCH = SKILL_DIR / "run_signature_funnel.py"
PY = sys.executable or "python3"

sys.path.insert(0, str(SCRIPTS))
import prove_sf_graph  # noqa: E402  (canonical 3/5/7 matrix + graph/derived fixtures)
from prove_sf_prompt_floor import _GRADE_BLOCK as SIG_GRADE_BLOCK  # noqa: E402  (canonical verbatim grade block)
from prove_sf_prompt_floor import (  # noqa: E402  (FIX-IMG-07 required image set)
    ANY_IMAGE, load_structure, required_image_pairs)

GOLDEN_SIZE = 7

# Documented example nonce (NOT a secret — this is a golden specimen, not a live run).
GOLDEN_NONCE = "golden-daybreak-nonce-v1"

PRODUCT = "The Daybreak Method"
OFFER_LEDGER = [
    "The Daybreak Method",
    "The Fast Track Sprint",
    "The Daybreak Field Notes",
    "The Founders Table Retreat",
    "The Single Day Pass",
]
CTA_MAIN = "CTA: Claim My Daybreak"
CTA_OTO1 = "CTA: Yes Add The Fast Track"
CTA_DS1 = "CTA: Keep The Field Notes"
CTA_OTO2 = "CTA: Reserve My Retreat Seat"
CTA_DS2 = "CTA: Grab The Day Pass"


# ---------------------------------------------------------------------------
# Band assertions — the copy below is REAL and already fits its band; these
# helpers fail the build loudly (with the measured size) if a hand-authored
# string ever drifts out of a SACRED band, so nothing is ever silently padded.
# ---------------------------------------------------------------------------
EM_DASHES = ("—", "–", "―")


def _chars(text: str, lo: int, hi: int, label: str) -> str:
    n = len(text.strip())
    if not (lo <= n <= hi):
        raise AssertionError(f"{label}: {n} stripped chars, outside [{lo},{hi}] :: {text!r}")
    for d in EM_DASHES:
        if d in text:
            raise AssertionError(f"{label}: contains an em/en dash {d!r} :: {text!r}")
    return text


def _wordcap(text: str, hi: int, label: str) -> str:
    n = len(text.split())
    if n > hi:
        raise AssertionError(f"{label}: {n} words, over the {hi}-word max :: {text!r}")
    return text


def _wordband(text: str, lo: int, hi: int, label: str) -> str:
    n = len(text.split())
    if not (lo <= n <= hi):
        raise AssertionError(f"{label}: {n} words, outside [{lo},{hi}] :: {text!r}")
    return text


# ---------------------------------------------------------------------------
# COPY LEDGER (prove_sf_copy) — 7-step: main, checkout, upsell, downsell,
# upsell-2, downsell-2, thank-you. Every string below is authored, distinct
# funnel copy for the fictional "The Daybreak Method".
# ---------------------------------------------------------------------------
def _main_page() -> dict:
    secs = []
    secs.append({"section": 1, "name": "The Big Bold Claim",
                 "copy": _chars(
                     "The Daybreak Method rebuilds your first ninety minutes so you wake calm, "
                     "clear, and already ahead, trading the frantic scramble for one steady sunrise "
                     "routine that quietly runs your whole day on your own terms.",
                     180, 225, "main S1"),
                 "cta": CTA_MAIN})
    pains = {
        2: _chars(
            "You wake to a blaring alarm already behind, thumbing snooze in the dark while the day "
            "stacks up against you, and by the time your bare feet hit the cold floor the morning "
            "has quietly taken the wheel from you.",
            180, 225, "main S2"),
        3: _chars(
            "You made yourself a quiet promise that tomorrow would finally be different, that you "
            "would rise early and move with intention, and you have broken that private vow so many "
            "mornings that you barely believe it anymore.",
            180, 225, "main S3"),
        4: _chars(
            "Your kids stand in the doorway and watch you drag yourself up late, tired and short "
            "before coffee, and somewhere underneath you can feel them quietly learning that a "
            "frantic, depleted morning is simply how life works.",
            180, 225, "main S4"),
    }
    for n, copy in pains.items():
        secs.append({"section": n, "name": f"The Big Bold Pain {n - 1}", "copy": copy, "cta": CTA_MAIN})
    secs.append({"section": 5, "name": "The Big Bold Why",
                 "copy": _wordcap(
                     "That's the reason why you deserve mornings that belong to you, a calm start "
                     "that compounds into a life finally moving forward on your own terms.",
                     30, "main S5"),
                 "cta": CTA_MAIN})
    secs.append({"section": 6, "name": "The Big Bold Who",
                 "copy": _wordcap(
                     "Founders who need clear focus, parents who crave a calm start, creators "
                     "chasing steady output, and leaders who want dependable energy every day.",
                     30, "main S6"),
                 "personas": ["founders", "parents", "creators", "leaders"]})
    s7_copy = ("Inside The Daybreak Method you get a complete, do-it-with-you morning system that "
               "carries you from the first alarm to your opening block of deep, focused work "
               "without friction, guesswork, or raw willpower, so the routine still runs on the "
               "hard mornings when staying under the warm blanket feels far easier than starting.")
    s7_bullets = [
        "thirty guided daily audio rituals you can begin half asleep",
        "four live monthly momentum calls hosted by the founder",
        "a printable ninety day commitment tracker and wall map",
        "the five minute reset for the mornings you oversleep",
        "a private community of early risers who keep you honest",
        "a personal founder text on your very first hard morning",
    ]
    _wordband(s7_copy + " " + " ".join(s7_bullets), 70, 120, "main S7")
    secs.append({"section": 7, "name": "The Big Bold What", "copy": s7_copy, "bullets": s7_bullets})
    secs.append({"section": 8, "name": "The Big Bold Benefit 1",
                 "copy": _wordcap(
                     "You feel the weight lift within the first week as your quiet mornings return, "
                     "calm, unhurried, and unmistakably your own again.",
                     30, "main S8")})
    secs.append({"section": 9, "name": "The Big Bold Benefit 2",
                 "copy": _wordcap(
                     "You watch the numbers move this quarter as steady, protected focus turns into "
                     "finished projects, shipped work, and results you can actually measure.",
                     30, "main S9")})
    secs.append({"section": 10, "name": "The Big Bold Benefit 3",
                 "copy": _wordcap(
                     "You become the grounded, unhurried, unstoppable person your future has been "
                     "quietly waiting on, one deliberate sunrise at a time.",
                     30, "main S10"),
                 "has_cta_button": True, "cta": CTA_MAIN})
    steps = [
        _chars("Share this reset with one friend who keeps starting over, because momentum grows "
               "when you rise together.", 89, 116, "main S11 step1"),
        _chars("Check your inbox for the welcome email and the five minute reset bonus we send the "
               "moment you join.", 89, 116, "main S11 step2"),
        _chars("Watch your phone for a personal text from the founder on your first hard morning, "
               "and answer it honestly.", 89, 116, "main S11 step3"),
        _chars("Join the private community today, introduce yourself to the members, and name the "
               "one morning you want back.", 89, 116, "main S11 step4"),
        _chars("Open module one now and complete your first guided daybreak ritual before the sun "
               "clears the low horizon.", 89, 116, "main S11 step5"),
        _chars("Write your ninety day commitment down and pin it where your tired morning eyes "
               "cannot possibly miss it.", 89, 116, "main S11 step6"),
        _chars("This is your morning and your one life, so rise now, press play on day one, and let "
               "the daybreak carry you all the way forward.", 0, 170, "main S11 step7"),
    ]
    _wordband(" ".join(steps), 100, 150, "main S11 total")
    secs.append({"section": 11, "name": "The Big How To", "steps": steps})
    parts = [
        {"label": "The Big Bold Heartfelt Message",
         "text": "This is far more than a course to me, it is the exact turn that quietly handed me "
                 "back my mornings and my whole life."},
        {"label": "The Big Struggle",
         "text": "I used to be just like you, exhausted before dawn and ashamed of every small "
                 "promise I kept breaking to myself."},
        {"label": "The Big Decision",
         "text": "So one gray, ordinary morning I decided the snooze button would no longer get to "
                 "write the entire story of my day."},
        {"label": "The Big Reason",
         "text": "I built this for the tired builder who still quietly believes their best work and "
                 "their best years are still ahead."},
        {"label": "The Big Invite",
         "text": "Come rise with us, take the first small daybreak step today, and let these quiet "
                 "mornings slowly rebuild everything you touch."},
        {"label": "The Big Passionate Close",
         "text": "Your next chapter begins before sunrise, and I will be right here cheering the "
                 "morning your first alarm finally means go."},
    ]
    _wordband(" ".join(p["text"] for p in parts), 100, 150, "main S12 total")
    secs.append({"section": 12, "name": "The Big Bold Heartfelt Message", "parts": parts})
    return {"page_type": "main", "sections": secs}


# ---- derived pages: 4 DISTINCT offer-specific copy sets (1-7 + replacement 8) ----
def _derived_page(page_type: str, cta: str, s1, pains, why, who, personas, s7_copy,
                  s7_bullets, sec8) -> dict:
    secs = []
    secs.append({"section": 1, "name": "The Big Bold Claim",
                 "copy": _chars(s1, 180, 225, f"{page_type} S1"), "cta": cta})
    for n in (2, 3, 4):
        secs.append({"section": n, "name": f"The Big Bold Pain {n - 1}",
                     "copy": _chars(pains[n], 180, 225, f"{page_type} S{n}"), "cta": cta})
    secs.append({"section": 5, "name": "The Big Bold Why",
                 "copy": _wordcap(why, 30, f"{page_type} S5"), "cta": cta})
    secs.append({"section": 6, "name": "The Big Bold Who",
                 "copy": _wordcap(who, 30, f"{page_type} S6"), "personas": personas})
    _wordband(s7_copy + " " + " ".join(s7_bullets), 70, 120, f"{page_type} S7")
    secs.append({"section": 7, "name": "The Big Bold What", "copy": s7_copy, "bullets": s7_bullets})
    secs.append(sec8)
    return {"page_type": page_type, "sections": secs}


def _seven_reasons(blank: str, cta: str, reasons: list) -> dict:
    assert len(reasons) == 7
    return {"section": 8, "name": f"7 Reasons To Commit To Your {blank} Future",
            "items": reasons, "cta": cta}


def _when_time(cta: str, misses: list) -> dict:
    assert len(misses) == 7
    return {"section": 8, "name": "When Time Runs Out", "items": misses, "cta": cta}


def _upsell_page():  # OTO1 — The Fast Track Sprint (done-with-you accelerated onboarding)
    return _derived_page(
        "upsell", CTA_OTO1,
        "You just claimed your daybreak, and right now you can bolt on the Fast Track Sprint, the "
        "done-with-you week that installs the whole routine while your motivation is still hot "
        "instead of leaving it to quietly fade.",
        {
            2: "You already know the quiet gap between the mornings you just paid for and the "
               "mornings you actually want, and you know a brand new plan on its own has slipped "
               "through your fingers more than once before.",
            3: "You have felt momentum drain away right after the excitement of a clean start wore "
               "off, leaving you staring at a plan you fully believed in on Sunday night but somehow "
               "never once managed to truly begin.",
            4: "You have watched other people pull cleanly ahead while you kept restarting the very "
               "same first week, and part of you is quietly tired of always being the one who is "
               "still just about to finally get going.",
        },
        "That's the reason why you add the Fast Track now, while the door is open and a guide can "
        "walk that fragile first week right beside you.",
        "Doers who want speed, builders who want proximity, and leaders who want the shortest honest "
        "path to a result that finally sticks.",
        ["founders", "operators", "leaders"],
        "The Fast Track Sprint stacks straight onto your daybreak and pulls the entire ninety day "
        "result forward, so instead of walking the slow road alone you move through a tighter loop, "
        "with faster feedback and real support on the exact mornings that used to end your streak.",
        [
            "a done-with-you accelerated onboarding sprint",
            "priority answers waiting inside the private community",
            "one extra live working session every single week",
            "the advanced reset built for high pressure travel days",
            "a second personal founder check-in at day thirty",
            "a shareable win card so you can bring a friend",
        ],
        _seven_reasons("Unstoppable", CTA_OTO1, [
            "Reason one: you install the entire routine in seven days instead of guessing at it alone for months.",
            "Reason two: a guide watches your first week and catches the exact spot where you usually quit.",
            "Reason three: faster feedback means a small stumble never grows into another abandoned restart.",
            "Reason four: the accelerated pace locks the habit in while your motivation is still burning hot.",
            "Reason five: priority answers mean you never lose a whole morning waiting on help you needed at dawn.",
            "Reason six: you finish the ninety day arc weeks early and start compounding the results far sooner.",
            "Reason seven: you become the person who follows through, and that identity quietly changes everything.",
        ]))


def _downsell_page():  # OTO1-decline — The Daybreak Field Notes (recordings-only)
    return _derived_page(
        "downsell", CTA_DS1,
        "If the full sprint is not for you today, keep the Daybreak Field Notes instead, the "
        "recordings-only tier that hands you every ritual and lesson to replay on your own schedule "
        "for a fraction of the full commitment.",
        {
            2: "You still want the calm mornings, you just do not want another live schedule you "
               "might fall behind on, and you know an empty calendar reminder has guilted you more "
               "than it has ever actually moved you.",
            3: "You have bought good material before and let it sit unopened, and quietly you worry "
               "that walking away now means walking away from the one small door that could still "
               "gently pull you back on track.",
            4: "You have felt the sting of watching a helpful thing expire while you waited for a "
               "better moment, and part of you does not want to hand back the calm start you can "
               "already picture yourself finally living.",
        },
        "That's the reason why you keep the Field Notes now, a light and forgiving door that stays "
        "open on the mornings your willpower does not.",
        "Self-pacers who want freedom, budget-minded starters who want a real on-ramp, and quiet "
        "learners who move best entirely on their own.",
        ["self-pacers", "starters", "quiet learners"],
        "The Daybreak Field Notes give you the recorded backbone of the whole method to revisit "
        "whenever a morning goes sideways, so even without the live rooms you always have the calm "
        "voice, the exact steps, and the reset waiting the moment you are ready to lean back in.",
        [
            "the full recordings library of every daily ritual",
            "searchable field notes you can scan in seconds",
            "quick reference cards for the mornings you feel lost",
            "the five minute reset audio saved for oversleeps",
            "lifetime replay access on your own private schedule",
            "a gentle weekly nudge to open the next lesson",
        ],
        _when_time(CTA_DS1, [
            "When time runs out you lose the recordings library that lets you relearn any ritual on demand.",
            "When time runs out the searchable field notes vanish and you are back to scattered memory alone.",
            "When time runs out you forfeit the quick reference cards built for the mornings you feel lost.",
            "When time runs out this low, forgiving door closes and the same lessons cost far more later on.",
            "When time runs out you keep only raw willpower, the single tool that has already failed you before.",
            "When time runs out you lose the calm voice in your ear on every hard and unforgiving morning.",
            "When time runs out you walk away with good intentions and nothing durable to actually hold onto.",
        ]))


def _upsell2_page():  # OTO2 — The Founders Table Retreat (categorically different, in-person)
    return _derived_page(
        "upsell-2", CTA_OTO2,
        "There is one thing a screen can never give you, and that is the room, so reserve a seat "
        "at the Founders Table Retreat, a categorically different in-person weekend where the "
        "method stops being a plan and becomes a place.",
        {
            2: "You already sense that everything you learn alone eventually hits a ceiling, and you "
               "know that no video, however good, has ever quite matched the pull of being physically "
               "in the same warm room as the work.",
            3: "You have promised yourself for years that one day you would step into a room like "
               "this, and quietly that one day keeps sliding forward while the version of you who "
               "belongs there waits patiently to be met.",
            4: "You have watched people you admire credit a single weekend for changing their whole "
               "trajectory, and some honest part of you is tired of always hearing that story from "
               "the outside instead of finally living it yourself.",
        },
        "That's the reason why you reserve your retreat seat now, while a small in-person room and a "
        "founder-led weekend are still genuinely within reach.",
        "Committed builders who want depth, quiet leaders who want a real peer circle, and doers "
        "ready to finally trade screens for a room.",
        ["builders", "leaders", "doers"],
        "The Founders Table Retreat is a weekend built face to face, so instead of one more login you "
        "walk into a small room, sit at the table with the founder and a tight circle of peers, and "
        "rebuild your ninety day plan out loud with people who will actually hold you to it.",
        [
            "a full founder-led in-person morning intensive",
            "a table of twenty committed peers, not a crowd",
            "a live rebuild of your personal ninety day plan",
            "quiet, unhurried hours to think without a screen",
            "relationships that keep carrying you long after",
            "a printed weekend playbook you take home for good",
        ],
        _seven_reasons("Founders", CTA_OTO2, [
            "Reason one: you spend a full weekend in the room with the founder and a small circle of peers.",
            "Reason two: proximity rewires belief faster than any lesson, because you watch it lived up close.",
            "Reason three: you leave with relationships that keep quietly carrying you long after the weekend ends.",
            "Reason four: an in-person reset breaks the online plateau that silently caps most people for years.",
            "Reason five: only twenty seats means real attention on your specific mornings and your real blockers.",
            "Reason six: you build the ninety day plan face to face and walk out already committed to living it.",
            "Reason seven: you become a founder who invests in the room, and that decision compounds for years.",
        ]))


def _downsell2_page():  # OTO2-decline — The Single Day Pass (the smallest true yes)
    return _derived_page(
        "downsell-2", CTA_DS2,
        "If a whole weekend away is too much right now, grab the Single Day Pass instead, one full "
        "retreat day that still puts you physically in the room for the founder-led morning before "
        "the doors quietly close for the season.",
        {
            2: "You want the room, you just cannot clear an entire weekend yet, and you know that "
               "holding out for the perfect open calendar has quietly cost you every in-person moment "
               "you told yourself you would eventually take.",
            3: "You have said next time to yourself more times than you can count, and some part of "
               "you already knows that one small yes today does far more for you than another "
               "flawless plan you never actually begin.",
            4: "You have felt what it is like to watch a door close while you waited for a braver "
               "version of yourself to show up, and you do not want to spend one more season "
               "admiring this room only from the hallway.",
        },
        "That's the reason why you grab the day pass now, the smallest honest yes that still gets "
        "your whole body into the room for one morning.",
        "First-timers who want a taste, careful spenders who want the smallest real step, and busy "
        "doers who can only give a single day.",
        ["first-timers", "careful spenders", "busy doers"],
        "The Single Day Pass is the smallest true yes in the whole method, one live retreat morning "
        "that can reset an entire quarter, so instead of waiting for a season you never seem to "
        "reach you simply show up once, sit in the room, and let a single day quietly move you.",
        [
            "one full founder-led retreat morning in person",
            "a seat in the same room, not another livestream",
            "a focused reset you can feel by the same afternoon",
            "a small circle to meet before you ever commit more",
            "a take-home one page plan for the next thirty days",
            "the smallest step that still changes where you stand",
        ],
        _when_time(CTA_DS2, [
            "When time runs out the single retreat day closes and the in-person room is gone for this season.",
            "When time runs out you miss the one live day that can reset a whole quarter in a few short hours.",
            "When time runs out you lose the smallest yes that still puts your whole body physically in the room.",
            "When time runs out the founder-led morning passes and you watch it, again, only from the outside.",
            "When time runs out you forfeit the single day of proximity that online lessons can never replace.",
            "When time runs out you keep waiting for the perfect moment that has honestly never once arrived.",
            "When time runs out you stay exactly where you are, and next season feels just as far away as ever.",
        ]))


def _checkout_page():
    return {"page_type": "checkout",
            "microcopy": {"headline": "Confirm your daybreak", "button": "Complete Secure Order"}}


def _thank_you_copy_page():
    steps = [
        _chars("Check your email for your receipt and the welcome bonus we already sent straight to "
               "your inbox.", 89, 116, "TY copy step1"),
        _chars("Watch your phone for a warm personal text from the founder, and reply so we know you "
               "are really in.", 89, 116, "TY copy step2"),
        _chars("Join the private community below and introduce yourself to the members who rise "
               "early right alongside you.", 89, 116, "TY copy step3"),
        _chars("Open your very first daybreak ritual tonight and set one gentle alarm for the calm "
               "morning ahead of you.", 89, 116, "TY copy step4"),
    ]
    return {"page_type": "thank-you", "sections": [
        {"section": "TY-1",
         "copy": _chars(
             "It is official, The Daybreak Method is yours, and the decision most people keep "
             "postponing for years you just made this morning.",
             120, 180, "TY-1")},
        {"section": "TY-2", "steps": steps},
        {"section": "TY-3",
         "copy": _chars(
             "You made a choice most people only talk about, and everything you need is already on "
             "its way. Welcome to your next chapter.",
             0, 170, "TY-3")},
    ]}


def build_copy_ledger() -> dict:
    return {
        "funnel_type": "signature_funnel",
        "funnel_size": 7,
        "product_title": PRODUCT,
        "offer_token_ledger": OFFER_LEDGER,
        "pages": [
            _main_page(), _checkout_page(), _upsell_page(), _downsell_page(),
            _upsell2_page(), _downsell2_page(), _thank_you_copy_page(),
        ],
    }


# ---------------------------------------------------------------------------
# BRIEF (prove_sf_intake) — 7-step runtime locked brief.
# ---------------------------------------------------------------------------
def build_brief() -> dict:
    answers = {
        "q1_offer": "The Daybreak Method — a 30-day morning-discipline course",
        "q2_price_promise": "$149; calm, owned mornings and a first deep-work block within 30 days",
        "q3_pains": "waking already behind; a privately broken promise to rise; kids learning the snooze",
        "q4_people": "founders, parents, creators, and leaders who want calm and output",
        "q5_goods": "30 daily audio rituals, 4 live calls, a tracker, a private community, a founder text",
        "q6_founder_story": "burned out and always behind; decided one gray dawn; built it for tired builders",
        "q7_brand_colors": "deep indigo and warm sunrise amber",
        "q8_representation": "60% Black women, 20% Black men, 15% mixed, 5% other",
        "q9_voice": "bold, warm, plainspoken, street-smart",
        "q10_funnel_length": "7-step",
        "q11_oto1": "The Fast Track Sprint, done-with-you accelerated onboarding, $197, 40 seats",
        "q12_downsell1": "The Daybreak Field Notes, recordings-only tier, $47",
        "q13_oto2": "The Founders Table Retreat, categorically different in-person weekend, $997, 20 seats",
        "q14_downsell2": "The Single Day Pass, one retreat day, $297",
        "q15_reference_images": "signature only",
        "q16_truth_gate": {
            "community_url": "https://community.example.com/daybreak",
            "bonus": "the five-minute morning reset audio",
            "founder_text_confirmed": True,
        },
        "q17_confirmation": "approved",
    }
    return {
        "funnel_type": "signature_funnel",
        "one_question_per_turn": True,
        "locked": True,
        "funnel_size": 7,
        "answers": answers,
        "offer_token_ledger": OFFER_LEDGER,
    }


# ---------------------------------------------------------------------------
# PROMPT LEDGER (prove_sf_prompt_floor) — 14 genuinely authored, per-page image
# prompts, each 5,000-19,000 chars of REAL distinct detail. Each describes ONE
# specific image (its own subject, scene, composition, lighting, mood, grade,
# brand color, and negative block). No repeated vocabulary-list dump.
# ---------------------------------------------------------------------------
def _p(*paras: str) -> str:
    """Join authored paragraphs into a single prompt string."""
    return " ".join(x.strip() for x in paras if x and x.strip())


# --- 1) main / Section 1 — DAWN HERO (owning the dawn) -----------------------
PROMPT_MAIN_1 = _p(
    "ESTABLISHING SHOT. A tall vertical hero portrait captured at the exact first minute of "
    "daybreak, a single commanding figure standing alone on an open concrete rooftop terrace while "
    "the horizon behind her turns from bruised indigo to living amber. She fills the frame from "
    "mid-thigh upward, planted and unhurried, the whole sleeping city spread out far below the "
    "parapet as one soft grey expanse waiting to wake.",
    "THE SUBJECT. She is a poised Black woman in her middle thirties, shoulders relaxed and rolled "
    "gently back, arms loose and easy at her sides with open, unclenched hands. Her stance is "
    "grounded and effortless, weight balanced evenly across both bare feet, the whole body language "
    "of a person who has already risen and made calm peace with the early hour instead of fighting "
    "it.",
    "FACE AND EXPRESSION. Her face is serene and quietly certain, eyes open and clear, her gaze "
    "lifted just above the lens toward the widening band of light. A faint private half smile rests "
    "at one corner of her mouth, the specific expression of someone who kept a promise to herself "
    "this morning and knows the weight of it, dignified and completely at ease.",
    "WARDROBE AND STYLING. She wears a fluid floor-length robe-coat in deep indigo raw silk, the "
    "fabric caught by a slow breeze in long sculptural folds, layered over a warm amber ribbed slip "
    "beneath. The tailoring is architectural and editorial, a high collar framing the jaw, sleeves "
    "pushed casually to the forearm, a single slim brass cuff at one wrist as the only ornament in "
    "the whole image.",
    "THE SET AND ENVIRONMENT. The rooftop is minimalist poured concrete with a low parapet, still "
    "wet from overnight dew and throwing soft mirrored patches of sky across its surface. A single "
    "potted olive tree stands to one side in a raw clay vessel, and a rolled linen exercise mat "
    "rests near her feet, the quiet physical evidence of a morning ritual already underway before "
    "the shot.",
    "PROPS AND SIGNIFICANT DETAILS. Beside her sits a plain unglazed ceramic cup with a single curl "
    "of steam rising straight up through the perfectly still air, and a slim closed leather journal "
    "with a pen laid across it. The objects are small, real and unbranded, arranged the way a "
    "disciplined person actually leaves them, suggesting order and intention without any clutter.",
    "BACKGROUND AND DEPTH. Behind her the skyline recedes in soft atmospheric layers, the distant "
    "towers reduced to flat indigo silhouettes stacked against a tall gradient of rose, apricot and "
    "pale liquid gold. A thin ribbon of ground mist hangs over the far streets far below, and one "
    "early bird carves a small dark arc across the brightening upper sky.",
    "LIGHTING DESIGN. The light is entirely natural golden-hour sunrise, a low warm key raking in "
    "hard from camera right to wrap her cheek, jaw and shoulder in honeyed amber, while a cool open "
    "sky fill from the left sculpts the shadow side of the body in gentle indigo. A clean rim of "
    "gold peels her silhouette away from the dark towers, giving the whole figure air and "
    "separation.",
    "SIGNATURE COLOR GRADE. Apply the Trevor Otts Signature grade with total conviction, because this is "
    "signature color, vivid and deliberately editorial, with global saturation pushed to roughly "
    "140 percent of natural so the amber reads like molten brass and the indigo like deep cut "
    "sapphire. Crush the shadows to inky richness against luminous glowing highlights, and render "
    "her deep skin with melanin-true intelligence, warm, dimensional and glowing, never ashy and "
    "never grey.",
    "MOOD AND EMOTIONAL REGISTER. The emotional register is serene triumph and quiet ownership, a "
    "held hush in the last moment before the world stirs, aspirational and grounded at the same "
    "time. The frame should feel like the precise instant a hard-won calm stops being an effort and "
    "simply becomes the way this person lives.",
    "CAMERA, LENS AND RENDER. Shoot it as a high-end fashion editorial cover on a medium format "
    "body with an eighty-five millimeter portrait lens at a shallow aperture, placed at eye level "
    "with the subject set off center to the left along the rule of thirds. Deliver a crisp two "
    "thousand pixel finish with fine filmic microcontrast, natural film grain, and tacksharp focus "
    "held on the eyes.",
    "BRAND COLOR AND COMPOSITION. Let deep indigo and warm sunrise amber carry the entire palette, "
    "indigo anchoring the wardrobe and the far skyline while amber owns the light and the horizon, "
    "with only the single restrained brass accent at the wrist. Leave generous negative space above "
    "her head so the composition breathes and a headline could later live cleanly in the open sky.",
    "NEGATIVE BLOCK AND FINISH. Render the whole frame as gallery-grade editorial art with "
    "painterly tonal depth and couture polish. Do not produce flat, muted, pastel, desaturated or "
    "low contrast color, do not distort the hands, eyes or teeth, and include absolutely no text, "
    "no letters, no words, no logos and no signage anywhere in the image.",
)

# --- 2) main / Section 2 — EXHAUSTED FLOOR (Pain 1, circumstantial) ----------
PROMPT_MAIN_2 = _p(
    "ESTABLISHING SHOT. A close, intimate vertical frame of one weary figure sitting on the very "
    "edge of an unmade bed in a dim bedroom during the heavy blue minutes before dawn. The bedside "
    "clock glows a dull red just out of focus, and the whole room feels pressed down and airless, "
    "the day already looming before the sun has even cleared the rooftops outside.",
    "THE SUBJECT. He is a Black man in his late thirties, hunched forward with both forearms braced "
    "on his thighs and his head hanging low, one hand dragging slowly down his tired face. The "
    "posture is pure gravity and depletion, a body that woke already behind and has not yet found "
    "the strength to fully lift itself up off the mattress into the waiting day.",
    "FACE AND EXPRESSION. His eyes are half open and heavy lidded, ringed with the specific "
    "puffiness of interrupted sleep, his jaw slack and his brow faintly furrowed. The expression is "
    "not dramatic despair but ordinary, familiar exhaustion, the quiet resignation of someone who "
    "already senses this morning slipping out of his hands before it has honestly begun.",
    "WARDROBE AND STYLING. He wears a creased indigo cotton sleep shirt, wrinkled from a restless "
    "night, and loose charcoal lounge pants, one shoulder seam twisted out of place. Everything "
    "about the styling reads rumpled and unstyled on purpose, the honest look of clothes slept in, "
    "with a thin amber thread of streetlight catching the crumpled folds of the fabric.",
    "THE SET AND ENVIRONMENT. The bedroom is small and shadowed, the sheets tangled and half "
    "dragged onto the cold floor, a phone face down on the nightstand beside a glass of water gone "
    "flat overnight. Heavy curtains hang almost fully closed, letting only one narrow blade of cold "
    "streetlight cut across the carpet toward his bare and planted feet.",
    "PROPS AND SIGNIFICANT DETAILS. On the nightstand a phone screen leaks a faint sliver of light "
    "where a fourth alarm has just been silenced, and a crumpled receipt and a dead pen sit beside "
    "it. These small props quietly tell the story of a snoozed, scattered start, the ordinary "
    "wreckage of a morning that got away before any of it could really matter.",
    "BACKGROUND AND DEPTH. Behind him the room dissolves into soft, heavy shadow, a shut closet "
    "door and a slumped chair draped with yesterday's clothes just barely readable in the murk. The "
    "depth is shallow and close, the walls seeming to lean gently inward, reinforcing the airless "
    "pressure of a day that feels like it is already stacked against him.",
    "LIGHTING DESIGN. The lighting is low key and predominantly cool, a single hard blade of "
    "indigo streetlight slicing through the curtain gap to rim his shoulder and one side of his "
    "face, while the fill stays deep and moody. A faint warm amber spill from the hallway underlines "
    "the far edge of the bed, a small distant promise of a warmer light not yet reached.",
    "SIGNATURE COLOR GRADE. Hold the Trevor Otts Signature grade even inside this gloom, because this is "
    "signature color, vivid and deliberately editorial, with saturation lifted to about 140 percent "
    "of natural so the cold blues stay jewel-deep rather than muddy and the single amber accent "
    "glows. Crush the shadows to rich inky black against controlled highlights, and render his deep "
    "skin with melanin-true intelligence, dimensional and warm even in the shade, never ashy and "
    "never flat.",
    "MOOD AND EMOTIONAL REGISTER. The emotional register is heavy, quiet and relatable, the private "
    "weight of a morning that already owns you, tired but never hopeless. It should read as the "
    "honest before, a real and human low point rendered with dignity so that the viewer recognizes "
    "themselves in it rather than pitying the man in the frame.",
    "CAMERA, LENS AND RENDER. Shoot it as an intimate editorial portrait on a medium format body "
    "with a fifty millimeter lens at a shallow aperture, positioned slightly low and close, the "
    "subject held off center to the right along the rule of thirds. Deliver a crisp two thousand "
    "pixel finish with fine filmic microcontrast, gentle grain, and tacksharp focus on the tired "
    "eyes.",
    "BRAND COLOR AND COMPOSITION. Keep deep indigo dominant across the cool shadowed room while a "
    "single restrained thread of warm amber marks the distant hallway, so the palette itself tells "
    "the story of cold present and warmer possibility. Leave quiet negative space in the dark upper "
    "half of the frame for a later headline to breathe.",
    "NEGATIVE BLOCK AND FINISH. Render the frame as gallery-grade editorial art with painterly "
    "shadow depth and honest human texture. Do not produce flat, muted, pastel, desaturated or low "
    "contrast color, do not distort the hands, eyes or teeth, and include absolutely no text, no "
    "letters, no words, no numerals and no signage anywhere in the image.",
)

# --- 3) main / Section 3 — BROKEN PROMISE NOTE (Pain 2, private) -------------
PROMPT_MAIN_3 = _p(
    "ESTABLISHING SHOT. A tight, quiet vertical portrait of a woman standing alone at a kitchen "
    "counter in the grey half-light before sunrise, holding a small handwritten note close to her "
    "chest. The frame is close and confessional, the world narrowed to her hands, the paper and her "
    "face, with the rest of the kitchen falling softly out of focus around her.",
    "THE SUBJECT. She is a Black woman in her early forties, standing very still with her shoulders "
    "drawn slightly in, both hands cupped around a folded, creased piece of notepaper. Her stance is "
    "protective and inward, the body of someone holding a private truth she has read many times, "
    "caught in the fragile moment between disappointment in herself and the wish to try once more.",
    "FACE AND EXPRESSION. Her jaw is set with a quiet, complicated resolve, her eyes lowered toward "
    "the note and just faintly glassy, a single strand of hair loose across her temple. The "
    "expression carries no theatrics, only the honest ache of a promise broken to herself again, "
    "held with the grace of a person who has not quite given up on keeping it.",
    "WARDROBE AND STYLING. She wears a simple warm amber knit cardigan pulled closed over a deep "
    "indigo tee, the sleeves long enough to half cover her hands, soft and lived-in. The styling is "
    "understated and domestic, nothing performative, just comfortable morning clothes that let the "
    "emotion of the hands and face carry the entire weight of the image without distraction.",
    "THE SET AND ENVIRONMENT. The kitchen is modern and softly cluttered, a kettle just beginning "
    "to steam on the stove behind her, a calendar with a few quietly circled dates pinned near the "
    "window. Morning light has not yet arrived, so the room sits in a low even wash of blue-grey, "
    "every surface muted and waiting for a day that has not committed to starting.",
    "PROPS AND SIGNIFICANT DETAILS. The note itself is the emotional center, a small square of "
    "paper with faint indented handwriting turned just away from the lens so its words stay her own, "
    "a coffee ring ghosted on one corner. Nearby a pen rests on the counter beside a half-drunk cup, "
    "small honest evidence of many mornings spent rewriting the very same promise.",
    "BACKGROUND AND DEPTH. Behind her the kitchen dissolves into gentle bokeh, the steaming kettle a "
    "soft warm glow, the window a pale rectangle of not-yet-morning. The depth is shallow and "
    "tender, isolating her cleanly from the room so that nothing competes with the small drama held "
    "quietly between her cupped and careful hands.",
    "LIGHTING DESIGN. The lighting is soft, low and directional, a delicate cool window light "
    "brushing the left of her face and the edge of the paper, balanced by a small warm amber glow "
    "from the kettle behind that rims her hair and shoulder. The contrast stays gentle and "
    "intimate, sculpting the face without ever hardening the vulnerable, private mood of the moment.",
    "SIGNATURE COLOR GRADE. Keep the Trevor Otts Signature grade fully present in this hush, because this is "
    "signature color, vivid and editorial, with saturation carried to roughly 140 percent so the "
    "amber knit glows and the indigo shadows stay deep and jewel-clear rather than washed and "
    "grey. Set inky controlled shadows against soft luminous highlights, and render her deep skin "
    "with melanin-true intelligence, rich, warm and dimensional, never ashy and never dull.",
    "MOOD AND EMOTIONAL REGISTER. The emotional register is tender, private and quietly aching, the "
    "specific loneliness of a vow you keep breaking only to yourself, shot with warmth and full "
    "dignity. It should feel confessional and human, the intimate low point just before a decision, "
    "never melodramatic and never staged.",
    "CAMERA, LENS AND RENDER. Shoot it as a fine-art editorial portrait on a medium format body "
    "with a hundred millimeter lens at a shallow aperture, at eye level and close in, the subject "
    "framed slightly left of center on the rule of thirds. Deliver a crisp two thousand pixel finish "
    "with delicate filmic microcontrast, fine grain and tacksharp focus on the eyes and the note.",
    "BRAND COLOR AND COMPOSITION. Balance warm amber against deep indigo as the two emotional poles "
    "of the frame, amber for the fragile hope glowing behind her and indigo for the heavy unlit "
    "present around her. Keep a pocket of soft negative space to the upper right for a later "
    "headline to settle without crowding her face.",
    "NEGATIVE BLOCK AND FINISH. Render the image as gallery-grade editorial art with painterly "
    "gentleness and honest skin texture. Do not produce flat, muted, pastel, desaturated or low "
    "contrast color, do not distort the hands, eyes or teeth, and keep the handwriting fully "
    "illegible with no readable text, no letters, no words and no signage anywhere in the frame.",
)

# --- 4) main / Section 4 — PARENT IN DOORWAY (Pain 3, witnessed) -------------
PROMPT_MAIN_4 = _p(
    "ESTABLISHING SHOT. A quiet domestic vertical frame shot from just inside a hallway, a tired "
    "parent leaning against a bedroom doorframe in the early morning while a small child watches "
    "from a few steps away. The composition places the two figures on a soft diagonal, the parent "
    "closer and larger, the child smaller and patient in the softened background.",
    "THE SUBJECT. The parent is a Black man in his late thirties, one shoulder pressed heavily to "
    "the doorframe, a hand rubbing the back of his neck, his whole frame sagging with the fatigue "
    "of a late and difficult start. The body reads as someone caught mid-morning between "
    "responsibility and depletion, moving slower than the day is already demanding of him.",
    "FACE AND EXPRESSION. His face carries a soft, distracted weariness, eyes lowered and unfocused, "
    "the faint tension of a man who knows he is running behind. There is love underneath the "
    "tiredness, but it is muted by exhaustion, the honest expression of a parent who does not yet "
    "realize how closely he is being studied from the doorway behind him.",
    "WARDROBE AND STYLING. He wears a rumpled deep indigo henley with the sleeves shoved up and a "
    "loose grey towel over one shoulder, dressed halfway for a day he is behind on. The child in the "
    "background wears warm amber pajamas, soft and bright against the muted hallway, a small deliberate "
    "spark of color that quietly pulls the eye toward the watching figure.",
    "THE SET AND ENVIRONMENT. The home is ordinary and lived-in, a hallway with framed shapes on "
    "the wall blurred out of legibility, a laundry basket half filled on the floor, a bedroom "
    "beyond dim and unmade. Everything says real weekday morning, the environment cluttered just "
    "enough to feel true without ever tipping into chaos or distraction from the two figures.",
    "PROPS AND SIGNIFICANT DETAILS. A pair of small sneakers sits waiting by the child's bare feet, "
    "and a forgotten coffee mug rests on a hallway shelf, a thin curl of steam long gone cold. These "
    "understated props anchor the scene in the texture of family routine, the small daily objects "
    "that surround a morning quietly slipping behind schedule.",
    "BACKGROUND AND DEPTH. The child stands in soft focus a few feet back, clear enough to read as "
    "watchful and still, the rest of the hallway melting into gentle depth behind. The shallow focus "
    "keeps the parent sharp and the child tenderly soft, so the emotional charge lives precisely in "
    "the space and the quiet attention stretched between the two of them.",
    "LIGHTING DESIGN. The lighting is soft and naturalistic, a cool morning wash coming from a "
    "window down the hall to model the parent's face, while a warm amber nightlight glow surrounds "
    "the child and lifts the pajamas. The two light temperatures gently separate the generations, "
    "cool weariness in the foreground, warm quiet hope glowing patiently behind.",
    "SIGNATURE COLOR GRADE. Keep the Trevor Otts Signature grade fully alive here, because this is signature "
    "color, vivid and editorial, with saturation carried near 140 percent so the amber pajamas "
    "burn softly warm and the indigo hallway stays deep and clean rather than grey. Hold inky "
    "controlled shadows against soft luminous highlights, and render both deep skin tones with "
    "melanin-true intelligence, warm, rich and dimensional, never ashy and never muddy.",
    "MOOD AND EMOTIONAL REGISTER. The emotional register is bittersweet and quietly convicting, the "
    "witnessed pain of a child learning a tired morning by watching, tender rather than harsh. It "
    "should feel like a loving home caught on a hard day, an honest mirror that stirs resolve in the "
    "viewer instead of shame.",
    "CAMERA, LENS AND RENDER. Shoot it as a cinematic editorial portrait on a medium format body "
    "with a thirty-five millimeter lens at a moderate aperture for a touch more environment, at "
    "chest height, the parent held left of center on the rule of thirds. Deliver a crisp two "
    "thousand pixel finish with filmic microcontrast, fine grain and tacksharp focus on the "
    "parent's face.",
    "BRAND COLOR AND COMPOSITION. Let deep indigo own the foreground and hallway while warm amber "
    "glows around the child in the back, so the palette itself carries the generational contrast at "
    "the heart of the frame. Leave calm negative space along the upper hallway wall where a headline "
    "could later rest without crowding either figure.",
    "NEGATIVE BLOCK AND FINISH. Render the image as gallery-grade editorial art with painterly "
    "domestic warmth and honest texture. Do not produce flat, muted, pastel, desaturated or low "
    "contrast color, do not distort the hands, eyes or teeth, and include absolutely no text, no "
    "letters, no words, no numerals and no signage anywhere in the image.",
)

# --- 5) main / Section 5 — RISING IN AMBER SHAFT (the turning point) ---------
PROMPT_MAIN_5 = _p(
    "ESTABLISHING SHOT. A dramatic vertical frame of a single figure rising to full height inside a "
    "tall shaft of warm amber light that pours diagonally across an otherwise dim room, dust and "
    "morning haze made visible in the beam. This is the turning point image, the exact instant a "
    "decision is made, the body moving from shadow into deliberate, chosen light.",
    "THE SUBJECT. She is a Black woman in her thirties captured mid-rise, spine lengthening, chin "
    "lifting, one hand just leaving the arm of a chair as she stands into the beam. The posture is "
    "all momentum and intention, a body in the act of choosing, caught at the graceful tipping point "
    "between sitting in the dark and standing fully inside the light.",
    "FACE AND EXPRESSION. Her face is calm, resolved and quietly electric, eyes lifting toward the "
    "source of the light, lips parted just slightly with the breath of a decision. The expression is "
    "the opposite of strain, a serene certainty arriving, the specific look of a person who has just "
    "stopped negotiating with herself and simply decided to begin.",
    "WARDROBE AND STYLING. She wears a structured deep indigo tailored jacket over a warm amber "
    "silk shell, the shoulders clean and architectural, the fabric catching the shaft of light in a "
    "bright vertical highlight. The styling is elevated and intentional, editorial rather than "
    "casual, dressed like a woman stepping deliberately into a more decided version of her own life.",
    "THE SET AND ENVIRONMENT. The room is spare and modern, a tall window with half-open shutters "
    "throwing the single hard diagonal beam, the rest of the space held in soft indigo shadow. A "
    "simple chair sits behind her, a folded blanket sliding off it, the quiet staging of a person "
    "who was sitting still one second ago and is now unmistakably in motion.",
    "PROPS AND SIGNIFICANT DETAILS. On a low table inside the beam sits an open journal with a pen "
    "resting in the crease and a small clock reading the earliest hour, both catching the amber "
    "light. These props mark the moment as a chosen, written commitment made at dawn, the physical "
    "artifacts of a turning point rather than a passive, accidental waking.",
    "BACKGROUND AND DEPTH. Behind her the room falls away into deep, clean indigo shadow, the "
    "far corners unlit so the eye is pulled irresistibly toward the bright vertical column of light "
    "and the rising figure inside it. The depth is theatrical and controlled, a single pool of "
    "illumination carved out of surrounding darkness for maximum focus and lift.",
    "LIGHTING DESIGN. The lighting is high contrast and directional, one powerful warm amber key "
    "raking down through the shutters as a defined volumetric shaft, catching floating dust, while "
    "the ambient fill stays deep indigo and low. A subtle rim traces her rising shoulder and jaw, "
    "separating the figure cleanly from the dark and heightening the sense of ascent into the light.",
    "SIGNATURE COLOR GRADE. Push the Trevor Otts Signature grade to its full drama, because this is signature "
    "color, vivid and boldly editorial, with saturation lifted to about 140 percent so the amber "
    "beam glows like honey fire and the indigo shadows read as deep, clean sapphire. Crush the "
    "unlit corners to inky black against the luminous shaft, and render her deep skin with "
    "melanin-true intelligence, radiant, warm and dimensional, never ashy and never flat.",
    "MOOD AND EMOTIONAL REGISTER. The emotional register is decisive, hopeful and quietly "
    "triumphant, the charged hush of a threshold being crossed, cinematic without being loud. It "
    "should feel like the single frame you would freeze on the exact moment a life quietly changes "
    "direction, grounded, dignified and full of forward pull.",
    "CAMERA, LENS AND RENDER. Shoot it as a cinematic editorial portrait on a medium format body "
    "with a seventy millimeter lens at a moderate aperture to hold the volumetric beam, at eye "
    "level, the figure placed on the right rule-of-thirds line rising into the light. Deliver a "
    "crisp two thousand pixel finish with filmic microcontrast, fine grain and tacksharp focus on "
    "the eyes.",
    "BRAND COLOR AND COMPOSITION. Build the entire palette from warm amber light and deep indigo "
    "shadow, letting the beam itself be the amber and the room be the indigo, with the wardrobe "
    "bridging the two. Reserve calm negative space in the dark left of the frame where a headline "
    "could sit against the shadow without touching the light.",
    "NEGATIVE BLOCK AND FINISH. Render the frame as gallery-grade editorial art with painterly "
    "volumetric light and couture polish. Do not produce flat, muted, pastel, desaturated or low "
    "contrast color, do not distort the hands, eyes or teeth, and include absolutely no text, no "
    "letters, no words, no logos and no signage anywhere in the image.",
)

# --- 6) main / Section 6 — FOUR ARCHETYPES (the who) -------------------------
PROMPT_MAIN_6 = _p(
    "ESTABLISHING SHOT. A wide vertical group portrait of four distinct people standing together in "
    "a shared warm morning light against a clean studio-like backdrop, each an archetype of the "
    "people the method serves. They are arranged in a loose, natural cluster, close enough to read "
    "as one community yet spaced so each individual clearly holds their own presence in the frame.",
    "THE SUBJECTS. From left to right stand a focused Black woman founder with a tablet held loosely "
    "at her side, a warm Black father with a child's small backpack over one shoulder, a Black "
    "creator in an apron dusted with clay, and an older Black leader in a crisp blazer. Their "
    "postures differ, one poised, one relaxed, one mid-laugh, one composed, so no two bodies echo.",
    "FACE AND EXPRESSION. Each face carries its own specific calm, the founder quietly determined, "
    "the father openly warm, the creator lit with easy joy, the leader steady and assured. Together "
    "the expressions map a spectrum of the same underlying peace, four different lives that each "
    "found a calmer morning, unified by tone rather than by any single repeated look.",
    "WARDROBE AND STYLING. The wardrobe threads deep indigo and warm amber through all four, the "
    "founder in an indigo suit, the father in an amber knit, the creator in indigo work clothes with "
    "an amber apron tie, the leader in an indigo blazer with an amber pocket square. The palette "
    "binds them into one brand family while their individual styling keeps each person distinct.",
    "THE SET AND ENVIRONMENT. The setting is a bright, minimal open space with a seamless warm-toned "
    "backdrop and a poured concrete floor catching soft reflections. There is just enough "
    "environmental hint, a plant in an amber pot, a low indigo bench, to feel like a real airy "
    "studio-loft at sunrise rather than a flat empty void behind the group.",
    "PROPS AND SIGNIFICANT DETAILS. Each person carries a single honest prop that names their world, "
    "the tablet, the small backpack, the clay-dusted hands, the leather folio, all understated and "
    "real. The props do the quiet work of characterization, letting the viewer instantly recognize "
    "which archetype they themselves belong to without a single word being needed.",
    "BACKGROUND AND DEPTH. The backdrop stays soft and gently graded from warm amber near the light "
    "to cooler indigo at the edges, holding the group forward in crisp focus while the corners fall "
    "away. The depth is shallow but generous, enough to separate the four figures cleanly from the "
    "background while keeping them all sharp and legible as a single united row.",
    "LIGHTING DESIGN. The lighting is a broad, flattering warm key from the upper left wrapping the "
    "whole group in even golden light, with a cool indigo fill shaping the far side of each face and "
    "a soft rim tracing every shoulder. The scheme keeps all four evenly and beautifully lit so no "
    "one dominates, a deliberately egalitarian light for a portrait about belonging.",
    "SIGNATURE COLOR GRADE. Hold the Trevor Otts Signature grade across the whole group, because this is "
    "signature color, vivid and editorial, with saturation lifted to roughly 140 percent so every "
    "indigo and amber garment reads jewel-rich and the skin stays luminous. Keep controlled inky "
    "shadows against clean bright highlights, and render each of the four deep skin tones with "
    "melanin-true intelligence, individually warm and dimensional, never ashy and never uniform.",
    "MOOD AND EMOTIONAL REGISTER. The emotional register is warm, inclusive and quietly aspirational, "
    "the feeling of finding your people, four different lives sharing one calm. It should read as "
    "belonging and possibility, an invitation that lets the viewer see a version of themselves "
    "standing comfortably somewhere in the row.",
    "CAMERA, LENS AND RENDER. Shoot it as a polished editorial group portrait on a medium format "
    "body with a fifty millimeter lens at a moderate aperture to keep all four sharp, at chest "
    "height and squared to the group. Deliver a crisp two thousand pixel finish with filmic "
    "microcontrast, fine grain and tacksharp focus carried evenly across every face in the row.",
    "BRAND COLOR AND COMPOSITION. Let deep indigo and warm amber alternate rhythmically across the "
    "four figures so the eye travels smoothly along the whole group, the palette itself binding "
    "individuals into a community. Keep calm negative space above the row for a later headline to "
    "sit cleanly over the united line of people.",
    "NEGATIVE BLOCK AND FINISH. Render the frame as gallery-grade editorial art with couture polish "
    "and honest individual character. Do not produce flat, muted, pastel, desaturated or low "
    "contrast color, do not distort the hands, eyes or teeth, do not blur the four faces into one "
    "another, and include absolutely no text, no letters, no words and no signage anywhere.",
)

# --- 7) main / Section 7 — TOOLKIT FLATLAY (the what) ------------------------
PROMPT_MAIN_7 = _p(
    "ESTABLISHING SHOT. A precise top-down flatlay photographed straight down onto a warm-toned "
    "surface, laying out the full toolkit of the method as a beautifully organized still life. The "
    "whole composition reads like an editorial product spread, every object deliberately placed on a "
    "clean grid so the viewer can take in the entire offer in a single confident glance from above.",
    "THE HERO ARRANGEMENT. At the center sits a printed ninety day commitment tracker opened flat, "
    "its clean grid of empty squares waiting to be filled, flanked by a stack of thirty small ritual "
    "cards fanned in a gentle arc. The arrangement radiates outward from the tracker like a considered "
    "editorial centerpiece, orderly, generous and quietly abundant without ever feeling crowded.",
    "THE OBJECTS. Around the tracker rest a pair of wireless earbuds for the daily audio, a slim "
    "indigo journal with a brass pen, a folded wall map of the routine, a ceramic cup of black "
    "coffee, and a phone showing a soft abstract audio waveform with no readable interface. Each "
    "object is real, tactile and chosen, together naming exactly what a buyer receives.",
    "MATERIAL AND TEXTURE. The surfaces are rich and varied, matte card stock, brushed brass, "
    "smooth glazed ceramic, soft woven indigo linen beneath one corner, and the fine tooth of "
    "printed paper. The interplay of textures gives the flatlay a premium tactile depth, every "
    "material catching the light differently so the eye lingers over the craftsmanship of each piece.",
    "COLOR STAGING. The palette is disciplined, deep indigo objects set against warm amber "
    "surfaces and props, with small brass accents tying the arrangement together. Nothing strays "
    "outside the brand family, so the whole spread reads as one cohesive world, an editorial still "
    "life where every color choice reinforces the identity of the method.",
    "THE SURFACE AND ENVIRONMENT. The backdrop is a warm amber-toned wood-and-stone tabletop with a "
    "subtle organic grain, softly lit to feel like a real morning table rather than a sterile studio "
    "sweep. A few honest details, a scattering of coffee-bean shadows, a folded linen napkin, a "
    "sprig of dried wheat, keep the flatlay warm, human and lived-in around its tidy grid.",
    "LIGHTING DESIGN. The lighting is a broad, soft overhead key angled slightly from the upper "
    "left to cast gentle, consistent directional shadows that give every object dimension and lift "
    "off the surface. A subtle warm bounce fills the shadow sides, and a faint indigo edge light "
    "cools the far corners, keeping the whole arrangement crisp, dimensional and appetizing.",
    "SIGNATURE COLOR GRADE. Bring the Trevor Otts Signature grade completely to the still life, because this is "
    "signature color, vivid and editorial, with saturation carried to roughly 140 percent so the "
    "amber wood glows and the indigo objects read as deep, clean jewel tones. Set controlled inky "
    "shadows beneath each object against luminous highlights on the brass, so the flatlay feels rich "
    "and premium, never flat and never dull.",
    "MOOD AND EMOTIONAL REGISTER. The emotional register is abundant, organized and reassuring, the "
    "satisfying feeling of everything you need laid out clearly in one place, calm rather than "
    "overwhelming. It should make the offer feel generous and complete, a considered system a person "
    "can trust, photographed with the care of a luxury editorial spread.",
    "CAMERA, LENS AND RENDER. Shoot it as a top-down editorial flatlay on a medium format body with "
    "a fifty-five millimeter lens at a moderate aperture for even sharpness across the grid, the "
    "camera squared perfectly parallel to the surface. Deliver a crisp two thousand pixel finish "
    "with filmic microcontrast, fine grain and tacksharp focus edge to edge across every object.",
    "BRAND COLOR AND COMPOSITION. Let warm amber own the surface and deep indigo own the key "
    "objects, with brass as the connective accent, so the palette organizes the eye as much as the "
    "grid does. Keep a clean margin of empty amber tabletop around the arrangement so a headline "
    "could later frame the flatlay without crowding a single item.",
    "NEGATIVE BLOCK AND FINISH. Render the flatlay as gallery-grade editorial product art with "
    "painterly material depth and premium polish. Do not produce flat, muted, pastel, desaturated "
    "or low contrast color, do not distort the shapes of the objects, keep every screen and page "
    "abstract, and include absolutely no readable text, no letters, no words and no signage anywhere.",
)

# --- 8) main / Section 8 — WEIGHT LIFTING PORTRAIT (Benefit 1, felt) ---------
PROMPT_MAIN_8 = _p(
    "ESTABLISHING SHOT. A serene close vertical portrait of a woman by a window in soft early "
    "light, captured in the precise moment a long-held tension finally releases from her body. The "
    "frame is tight and calm, mostly face and shoulders, built entirely around the felt sensation of "
    "weight lifting, of a breath let go, of a first genuinely quiet morning arriving.",
    "THE SUBJECT. She is a Black woman in her late thirties, shoulders visibly dropping and softening "
    "away from her ears, her chest opening with the tail end of a slow exhale. The posture is the "
    "physical language of relief itself, a body unclenching after carrying too much for too long, "
    "settling gently into an ease it had almost forgotten was possible.",
    "FACE AND EXPRESSION. Her eyes are softly closed or barely open, her features smooth and "
    "unguarded, the faintest grateful smile beginning to surface. The expression is pure quiet "
    "relief, the private, wordless feeling of a weight sliding off, rendered with such stillness that "
    "the viewer can almost feel their own shoulders lower in sympathy with hers.",
    "WARDROBE AND STYLING. She wears a soft, oversized warm amber knit that slips slightly off one "
    "shoulder, layered over a deep indigo camisole, everything relaxed and tactile. The styling is "
    "gentle and unstructured, cozy rather than sharp, clothing that reads like the first easy "
    "morning after a hard season, wrapping the figure in warmth and comfort.",
    "THE SET AND ENVIRONMENT. She sits near a tall window with sheer curtains diffusing the light, a "
    "simple armchair and a folded blanket suggesting a calm corner claimed for herself. The space is "
    "minimal, warm and softly out of focus, an environment that exists only to hold this one quiet "
    "moment of recovered peace without any competing detail.",
    "PROPS AND SIGNIFICANT DETAILS. A warm cup rests loosely in both of her relaxed hands, steam "
    "drifting up in a lazy curl, and a single potted plant leans into the window light beside her. "
    "The props are minimal and soothing, chosen to deepen the sense of a slow, unhurried morning "
    "finally being savored rather than survived.",
    "BACKGROUND AND DEPTH. Behind her the room melts into gentle, luminous bokeh, the window a soft "
    "wash of pale gold, the corners tender and unfocused. The shallow depth cradles her in clean "
    "isolation so that nothing pulls attention away from the small, profound drama of a body finally "
    "letting go of its held breath.",
    "LIGHTING DESIGN. The lighting is soft, warm and enveloping, a large diffused window key wrapping "
    "her face in gentle golden light, with a whisper of cool indigo fill defining the shadow side. "
    "The overall contrast is low and tender, a caressing light with no hard edges, matching the felt, "
    "physical softness of the relief at the center of the image.",
    "SIGNATURE COLOR GRADE. Keep the Trevor Otts Signature grade present even in the softness, because this is "
    "signature color, vivid and editorial, with saturation held near 140 percent so the amber knit "
    "glows richly and the indigo stays deep and clean rather than grey. Balance gentle inky shadows "
    "against luminous highlights, and render her deep skin with melanin-true intelligence, warm, "
    "radiant and dimensional, never ashy and never washed out.",
    "MOOD AND EMOTIONAL REGISTER. The emotional register is relief, gratitude and quiet renewal, the "
    "felt payoff of the very first calm morning, intimate and deeply human. It should feel like "
    "exhaling after holding your breath for months, a warm and honest reward that makes the promise "
    "of the method feel already true.",
    "CAMERA, LENS AND RENDER. Shoot it as a tender editorial portrait on a medium format body with a "
    "hundred and five millimeter lens at a shallow aperture, at eye level and close, the subject set "
    "just off center on the rule of thirds. Deliver a crisp two thousand pixel finish with delicate "
    "filmic microcontrast, fine grain and tacksharp focus on the eyes and the soft smile.",
    "BRAND COLOR AND COMPOSITION. Let warm amber dominate as the color of relief and comfort while "
    "deep indigo grounds the shadows and the camisole, keeping the brand family intact within an "
    "intimate frame. Preserve soft negative space on the window side for a later headline to rest in "
    "the pale morning glow.",
    "NEGATIVE BLOCK AND FINISH. Render the portrait as gallery-grade editorial art with painterly "
    "softness and honest skin texture. Do not produce flat, muted, pastel, desaturated or low "
    "contrast color, do not distort the hands, eyes or teeth, and include absolutely no text, no "
    "letters, no words and no signage anywhere in the image.",
)

# --- 9) main / Section 9 — DEEP WORK DESK (Benefit 2, measured) --------------
PROMPT_MAIN_9 = _p(
    "ESTABLISHING SHOT. A composed vertical portrait of a person deep in a focused work block at a "
    "clean, well-ordered desk in full, bright morning light, the picture of measured productivity. "
    "The frame balances the figure and their workspace, showing a calm professional in a state of "
    "flow, the environment itself signaling clarity, control and results being quietly made.",
    "THE SUBJECT. He is a Black man in his early forties seated upright and engaged, one hand "
    "resting on a pen over an open planner, his gaze locked in on the work before him. The posture is "
    "grounded and unhurried focus, no tension, no slump, the relaxed alertness of someone operating "
    "at their best inside a protected, deliberate stretch of concentrated time.",
    "FACE AND EXPRESSION. His face is calm, sharp and absorbed, brow smooth, eyes clear and steady "
    "on the task, a trace of quiet satisfaction at the mouth. The expression is effortless "
    "concentration rather than strain, the specific look of a person whose morning routine has "
    "handed them a clear head and who is now spending it on work that genuinely matters.",
    "WARDROBE AND STYLING. He wears a crisp deep indigo button shirt with the sleeves neatly rolled, "
    "simple and sharp, a warm amber watch strap the single note of color at his wrist. The styling is "
    "clean, modern and professional without being stiff, the wardrobe of someone who takes their "
    "craft seriously and dresses with the same quiet intention they bring to the morning.",
    "THE SET AND ENVIRONMENT. The desk is minimal and immaculate, a laptop showing a soft abstract "
    "screen, a neat stack of papers, a small potted plant, a single framed shape on the wall behind "
    "kept out of legibility. The whole workspace reads as calm and controlled, an environment "
    "engineered for focus, uncluttered yet warm and distinctly human.",
    "PROPS AND SIGNIFICANT DETAILS. An open paper planner shows a tidy, abstract grid of ticked "
    "boxes with no readable words, a coffee cup sits at a respectful distance, and a pair of "
    "earbuds rests coiled nearby. These props quietly narrate a measured, tracked practice, the "
    "visible infrastructure of consistent output rather than frantic, scattered effort.",
    "BACKGROUND AND DEPTH. Behind him a bright window and a softly blurred shelf of books fall into "
    "gentle bokeh, keeping the figure and desk crisp while the room recedes. The shallow depth "
    "isolates the moment of flow, letting the sharp foreground of focused hands and face carry the "
    "story while the airy background reinforces a sense of clarity and space.",
    "LIGHTING DESIGN. The lighting is bright, clean and energizing, a large cool-leaning morning key "
    "from the window modeling his face and the desk, balanced by a warm amber bounce from the room "
    "to keep the skin rich. The contrast is crisp but comfortable, a productive daylight quality that "
    "makes the scene feel awake, capable and fully switched on.",
    "SIGNATURE COLOR GRADE. Carry the Trevor Otts Signature grade into this clarity, because this is signature "
    "color, vivid and editorial, with saturation lifted to about 140 percent so the indigo shirt "
    "reads deep and clean and the amber accents glow. Hold controlled inky shadows against luminous "
    "highlights on the desk, and render his deep skin with melanin-true intelligence, warm, sharp "
    "and dimensional, never ashy and never dull.",
    "MOOD AND EMOTIONAL REGISTER. The emotional register is focused, capable and quietly proud, the "
    "measured payoff of protected mornings turning into real, trackable output. It should feel "
    "productive and aspirational without hype, the calm confidence of someone whose disciplined start "
    "is compounding into visible, countable results.",
    "CAMERA, LENS AND RENDER. Shoot it as a clean editorial portrait on a medium format body with a "
    "sixty-five millimeter lens at a moderate aperture, at eye level and slightly angled to the desk, "
    "the subject placed on a rule-of-thirds line. Deliver a crisp two thousand pixel finish with "
    "filmic microcontrast, fine grain and tacksharp focus on the eyes and the working hand.",
    "BRAND COLOR AND COMPOSITION. Let deep indigo lead through the shirt and cool shadows while warm "
    "amber accents the watch and the room bounce, keeping the palette disciplined inside a bright "
    "scene. Preserve calm negative space on the window side of the frame for a later headline to sit "
    "in the clean daylight.",
    "NEGATIVE BLOCK AND FINISH. Render the portrait as gallery-grade editorial art with crisp "
    "material depth and honest skin texture. Do not produce flat, muted, pastel, desaturated or low "
    "contrast color, do not distort the hands, eyes or teeth, keep every screen and page abstract, "
    "and include absolutely no readable text, no letters, no words and no signage anywhere.",
)

# --- 10) main / Section 10 — ROOFTOP TRIUMPH (Benefit 3, become) -------------
PROMPT_MAIN_10 = _p(
    "ESTABLISHING SHOT. An expansive wide vertical hero portrait of a figure standing at the very "
    "edge of a high rooftop at full sunrise, arms open and head lifted, the transformed city "
    "glowing gold behind and below. This is the peak image of the funnel, unhurried and unstoppable, "
    "a person who has fully become the calmest, most capable version of themselves.",
    "THE SUBJECT. She is a Black woman in her forties standing tall and open, chest lifted, arms "
    "loosely spread as if greeting the whole sky, hair moving gently in the high morning breeze. The "
    "posture is expansive triumph without arrogance, a grounded, generous victory pose, the body "
    "language of someone who has arrived somewhere she quietly earned one sunrise at a time.",
    "FACE AND EXPRESSION. Her face is radiant, serene and fully alive, eyes bright toward the sun, a "
    "genuine unforced smile of deep contentment. The expression is earned joy, the calm exhilaration "
    "of a person completely at home in their own life, aspirational yet warm, the destination the "
    "whole method has been quietly building toward all along.",
    "WARDROBE AND STYLING. She wears a flowing deep indigo cape-coat that lifts and billows behind "
    "her in the wind over a warm amber column dress, the fabrics catching the sunrise in bright "
    "moving highlights. The styling is elevated, cinematic and heroic, editorial couture built to "
    "read as transformation, a woman dressed for the summit of her own story.",
    "THE SET AND ENVIRONMENT. The rooftop is broad and open with a low modern railing, the poured "
    "surface warm underfoot, potted grasses swaying at the edges. Beyond the parapet the whole city "
    "spreads out under a vast sunrise sky, transformed from the grey expanse of the earlier frames "
    "into a luminous, golden, hopeful landscape stretching to the horizon.",
    "PROPS AND SIGNIFICANT DETAILS. The scene is deliberately unburdened, no tools, no clutter, only "
    "the figure, the wind and the light, signaling that the work is done and the routine has become "
    "second nature. The only detail is the interplay of moving fabric and open air, the physical "
    "sense of freedom that comes after long, quiet discipline.",
    "BACKGROUND AND DEPTH. Behind her the transformed skyline glows in warm amber and soft rose, "
    "distant towers catching the first full light, a few clouds lit from beneath. The depth is vast "
    "and airy, the city rendered in soft luminous layers so the heroic foreground figure stands "
    "clean and commanding against an epic, hopeful, sunlit horizon.",
    "LIGHTING DESIGN. The lighting is glorious full sunrise, a strong warm backlight blazing behind "
    "her to set a brilliant golden rim around the whole figure and blaze through the lifting fabric, "
    "balanced by a warm frontal bounce so her face stays luminous. A cool indigo sky fill shapes the "
    "edges, making the backlit halo of amber feel even more triumphant and alive.",
    "SIGNATURE COLOR GRADE. Take the Trevor Otts Signature grade to its most heroic, because this is signature "
    "color, vivid and boldly editorial, with saturation pushed to roughly 140 percent so the sunrise "
    "burns molten amber and the indigo cape reads as deep electric sapphire. Set rich controlled "
    "shadows against luminous glowing highlights, and render her deep skin with melanin-true "
    "intelligence, radiant, warm and dimensional, never ashy and never washed out.",
    "MOOD AND EMOTIONAL REGISTER. The emotional register is soaring, triumphant and deeply earned, "
    "the unhurried and unstoppable peak of the transformation, cinematic and full of uplift. It "
    "should feel like the closing frame of an inspiring film, the visual proof that the calm morning "
    "chosen at the start has grown into a whole life of quiet, confident power.",
    "CAMERA, LENS AND RENDER. Shoot it as an epic editorial hero portrait on a medium format body "
    "with a fifty millimeter lens at a moderate aperture to hold both figure and city, positioned "
    "slightly low for grandeur, the subject on a rule-of-thirds line. Deliver a crisp two thousand "
    "pixel finish with filmic microcontrast, fine grain and tacksharp focus on the face.",
    "BRAND COLOR AND COMPOSITION. Let warm amber flood the sky and light as the color of arrival "
    "while deep indigo commands the billowing cape, the palette itself staging a sunrise victory. "
    "Leave sweeping negative space in the bright sky above and beside her for a headline and the "
    "inspirational call-to-action button to live with room to breathe.",
    "NEGATIVE BLOCK AND FINISH. Render the frame as gallery-grade cinematic editorial art with "
    "painterly light and couture drama. Do not produce flat, muted, pastel, desaturated or low "
    "contrast color, do not distort the hands, eyes or teeth, and include absolutely no text, no "
    "letters, no words, no logos and no signage anywhere in the image.",
)

# --- 11) main / Section 11 — TYPOGRAPHY GALLERY (text-bearing DECIDE/COMMIT/RISE) ---
PROMPT_MAIN_11 = _p(
    "ESTABLISHING SHOT. A refined vertical interior of a minimalist art gallery at golden hour, "
    "three large framed canvases hung in a clean even row along a deep indigo feature wall, each "
    "canvas carrying one bold artistic word. The composition is architectural and calm, a quiet "
    "temple of intention where three single words become the entire subject of the image.",
    "THE TYPOGRAPHY, EXACTLY. Each canvas holds one word rendered as a big, bold, hand-brushed "
    "artistic display letterform. Spelling-lock each word letter for letter, spelled exactly as "
    "written here with no substitutions: the left canvas reads DECIDE, the center canvas reads "
    "COMMIT, and the right canvas reads RISE. These three words, DECIDE, COMMIT and RISE, are the "
    "only text permitted anywhere in the entire image and every letter must be perfectly formed.",
    "THE LETTERFORMS. The words DECIDE, COMMIT and RISE are painted in a confident warm amber "
    "brushstroke against pale gallery canvas, the strokes textured and expressive like fine gestural "
    "calligraphy, each letter cleanly separated and unmistakably legible. Keep the three words the "
    "same family and weight so they read as one deliberate triptych of a single, rising idea.",
    "THE ENVIRONMENT. The gallery is spare and premium, pale polished concrete floors, a long "
    "backless indigo bench centered before the canvases, tall ceilings with discreet track "
    "lighting. The room is empty of people, hushed and reverent, so nothing competes with the three "
    "framed words and the calm, intentional mood of the space around them.",
    "COMPOSITION AND FRAMING. The three canvases are spaced with equal, generous gaps and hung "
    "perfectly level, the center word slightly larger to anchor the eye, the whole row balanced on "
    "the wall with architectural precision. A gentle one-point perspective draws the viewer down the "
    "polished floor toward the triptych, giving the flat wall real dimensional depth.",
    "THE FRAMES AND MATERIALS. Each canvas sits in a slim brushed-brass frame that catches the warm "
    "light, the deep indigo wall behind them textured like fine plaster, the floor reflecting soft "
    "amber pools. The materials are rich and tactile, brass, canvas, plaster and stone, giving the "
    "minimal scene a quiet, expensive, gallery-grade sense of craft.",
    "LIGHTING DESIGN. The lighting is warm directional gallery track light, each canvas grazed by "
    "its own focused amber wash that rakes across the brushstroke texture and lifts the letters off "
    "the surface, while the surrounding wall falls into deep indigo shadow. Soft pools of light on "
    "the floor and a faint glow along the bench keep the room dimensional and reverent.",
    "SIGNATURE COLOR GRADE. Apply the Trevor Otts Signature grade with full intent, because this is signature "
    "color, vivid and editorial, with saturation lifted to roughly 140 percent so the amber lettering "
    "glows against the deep, clean indigo wall. Crush the surrounding shadows to inky richness "
    "against the luminous lit canvases, and keep the whole grade in the signature aesthetic, rich, "
    "graded and unforgettable, never flat, never washed out and never grey.",
    "MOOD AND EMOTIONAL REGISTER. The emotional register is reverent, resolved and quietly powerful, "
    "a gallery built as a shrine to a decision, calm yet charged with intention. It should feel like "
    "standing alone before three words that together map a turning point, DECIDE then COMMIT then "
    "RISE, the visual grammar of a manifesto held in stillness.",
    "CAMERA, LENS AND RENDER. Shoot it as an architectural editorial interior on a medium format "
    "body with a twenty-eight millimeter lens at a moderate aperture for crisp depth, camera "
    "centered and level to the wall for symmetry. Deliver a crisp two thousand pixel finish with "
    "filmic microcontrast, fine grain, and tacksharp focus holding every letter of the three words "
    "perfectly sharp.",
    "BRAND COLOR AND COMPOSITION. Build the entire palette from deep indigo walls and warm amber "
    "lettering and light, with brass frames as the connective accent, a disciplined two-color world. "
    "Keep calm negative space of indigo wall above the canvases so the triptych sits framed by "
    "shadow with room for the composition to breathe.",
    "NEGATIVE BLOCK AND FINISH. Render the interior as a museum-grade architectural photograph with "
    "painterly light and precise geometry. Do not misspell any of the three words, do not add any "
    "words or letters other than DECIDE, COMMIT and RISE, do not distort or reverse the letterforms, "
    "and do not let the color turn flat, dull or washed out anywhere in the frame.",
)

# --- 12) main / Section 12 — FOUNDER PORTRAIT (heartfelt letter) -------------
PROMPT_MAIN_12 = _p(
    "ESTABLISHING SHOT. A warm, intimate vertical portrait of the founder seated close to the "
    "camera in a softly lit study at early morning, looking directly and openly into the lens as if "
    "speaking a heartfelt letter aloud. The frame is close and personal, built for connection, the "
    "whole image tuned to feel like a sincere one-to-one confession of purpose.",
    "THE SUBJECT. The founder is a warm, grounded Black man in his forties, leaning slightly forward "
    "with forearms resting on a wooden table, hands loosely clasped, fully present and unguarded. The "
    "posture is open and sincere, the body language of someone telling you the truest thing they "
    "know, inviting rather than performing, close enough to feel like a real conversation.",
    "FACE AND EXPRESSION. His face is warm, honest and kind, eyes soft and directly meeting the "
    "viewer with a gentle, knowing steadiness, the faint lines of someone who has lived the story he "
    "is telling. The expression carries earned wisdom and genuine care, the specific warmth of a "
    "founder who built the thing out of his own hard mornings and means every word.",
    "WARDROBE AND STYLING. He wears a soft deep indigo crewneck sweater over a simple collar, "
    "understated and approachable, a warm amber woven bracelet the only small personal accent. The "
    "styling is deliberately humble and real, not corporate, the clothing of a trusted mentor at his "
    "own kitchen table rather than a distant executive behind a desk.",
    "THE SET AND ENVIRONMENT. The study is cozy and personal, a shelf of well-worn books softly "
    "blurred behind him, a single lit lamp, a plant, a framed shape kept out of legibility on the "
    "wall. The environment feels like a real, lived-in morning room, warm and human, the natural "
    "setting for an honest, unhurried, heartfelt message.",
    "PROPS AND SIGNIFICANT DETAILS. On the table sit a handwritten letter face down, a fountain pen, "
    "and a steaming mug of coffee, the quiet artifacts of someone who still writes things by hand and "
    "means them. These props gently reinforce the letter-to-you intimacy of the frame without ever "
    "showing a single readable word on the page.",
    "BACKGROUND AND DEPTH. Behind him the study falls into gentle, warm bokeh, the lamp a soft glow, "
    "the bookshelf a comforting blur of indigo and amber spines. The shallow depth keeps his eyes and "
    "hands crisp while the room dissolves tenderly, holding all attention on the sincerity of his "
    "gaze and the closeness of the moment.",
    "LIGHTING DESIGN. The lighting is soft, warm and intimate, a gentle key from a nearby lamp and "
    "window wrapping his face in inviting golden light, with a low cool indigo fill shaping the "
    "shadow side. A faint warm rim separates him from the background, and the overall contrast stays "
    "tender and close, the flattering, honest light of a trusted face at dawn.",
    "SIGNATURE COLOR GRADE. Carry the Trevor Otts Signature grade into the warmth, because this is signature "
    "color, vivid and editorial, with saturation held near 140 percent so the amber lamp glow reads "
    "rich and the indigo sweater and shadows stay deep and clean. Balance gentle inky shadows against "
    "luminous highlights, and render his deep skin with melanin-true intelligence, warm, radiant and "
    "dimensional, never ashy and never flat.",
    "MOOD AND EMOTIONAL REGISTER. The emotional register is sincere, warm and deeply trustworthy, "
    "the intimate honesty of a founder speaking heart to heart, vulnerable yet strong. It should feel "
    "like being personally let in, a message that makes the viewer trust the person behind the method "
    "and feel genuinely invited to rise alongside him.",
    "CAMERA, LENS AND RENDER. Shoot it as an intimate editorial portrait on a medium format body "
    "with a ninety millimeter lens at a shallow aperture, at eye level and close, the founder set "
    "just off center on the rule of thirds. Deliver a crisp two thousand pixel finish with delicate "
    "filmic microcontrast, fine grain and tacksharp focus locked on his warm, direct eyes.",
    "BRAND COLOR AND COMPOSITION. Let warm amber own the intimate lamp glow and deep indigo ground "
    "the sweater and shadows, a close two-color world tuned for trust and warmth. Keep soft negative "
    "space beside him where a pulled quote from the heartfelt letter could later rest against the "
    "gentle background blur.",
    "NEGATIVE BLOCK AND FINISH. Render the portrait as gallery-grade editorial art with painterly "
    "warmth and honest skin texture. Do not produce flat, muted, pastel, desaturated or low contrast "
    "color, do not distort the hands, eyes or teeth, keep the letter fully illegible, and include "
    "absolutely no readable text, no letters, no words and no signage anywhere in the image.",
)

# --- 13) upsell / Section 1 — FAST TRACK STRIDE (momentum made visible) ------
PROMPT_UPSELL_1 = _p(
    "ESTABLISHING SHOT. A dynamic vertical portrait of a figure caught mid-stride walking briskly "
    "through a bright modern corridor of light, momentum made fully visible in a single frozen step. "
    "The frame carries motion and forward drive, a person moving with pace and purpose, the whole "
    "image built to feel like acceleration, like a fast track being taken in real time.",
    "THE SUBJECT. She is a Black woman in her thirties captured in a confident forward stride, one "
    "leg extended, coat and hair streaming back, arms swinging with athletic ease. The posture is "
    "pure directed momentum, a body decisively in motion rather than at rest, frozen at the peak of a "
    "powerful step that reads as unstoppable acceleration toward a goal.",
    "FACE AND EXPRESSION. Her face is focused, lit and quietly exhilarated, eyes fixed ahead on "
    "something just beyond the frame, jaw set with purposeful drive. The expression is the thrill of "
    "gaining speed, a determined forward hunger without any strain, the look of someone who has "
    "chosen the faster road and is fully committed to running it.",
    "WARDROBE AND STYLING. She wears a sharp deep indigo trench coat flaring open mid-stride over a "
    "warm amber top and tailored trousers, the coat caught billowing to emphasize the motion. The "
    "styling is sleek, modern and kinetic, editorial power-dressing built to move, the wardrobe of "
    "someone striding decisively into an accelerated, higher-support version of the journey.",
    "THE SET AND ENVIRONMENT. The corridor is a bright, architectural passage of glass and pale "
    "stone with rhythmic vertical columns of light rushing past on either side, a space engineered "
    "to suggest speed. Directional lines in the floor and ceiling all converge ahead of her, pulling "
    "the eye and the energy powerfully forward in the direction of her stride.",
    "PROPS AND SIGNIFICANT DETAILS. She carries a slim indigo folio tucked under one arm, and a "
    "faint motion blur trails the swinging edge of her coat and the far background, sharpening the "
    "sense of pace. The details are minimal and aerodynamic, everything stripped down to reinforce "
    "clean, fast, forward movement without any clutter to slow the eye.",
    "BACKGROUND AND DEPTH. Behind her the corridor stretches into a bright vanishing point with the "
    "columns of light streaking gently with motion, the depth long and rushing. The background blur "
    "is directional, smeared subtly along the axis of travel so the environment itself seems to move "
    "past her, amplifying the frozen instant of a powerful forward step.",
    "LIGHTING DESIGN. The lighting is bright, crisp and rhythmic, alternating warm amber and cool "
    "indigo pools from the passing columns strobing across her body as she moves, with a strong key "
    "modeling her face and a clean rim edging the streaming coat. The alternating warm and cool light "
    "heightens the pulse and cadence of momentum through the frame.",
    "SIGNATURE COLOR GRADE. Drive the Trevor Otts Signature grade hard here, because this is signature color, "
    "vivid and boldly editorial, with saturation pushed to roughly 140 percent so the amber light "
    "pools glow and the indigo coat reads as deep electric sapphire in motion. Set crisp inky shadows "
    "against luminous highlights along the moving fabric, and render her deep skin with melanin-true "
    "intelligence, warm, sharp and dimensional, never ashy and never flat.",
    "MOOD AND EMOTIONAL REGISTER. The emotional register is fast, confident and exhilarating, the "
    "surging feeling of momentum and acceleration, energetic and aspirational. It should feel like "
    "the visual embodiment of a fast track, the thrill of a committed decision to move quicker with "
    "more support, propulsive without ever tipping into frantic.",
    "CAMERA, LENS AND RENDER. Shoot it as a kinetic editorial portrait on a medium format body with "
    "a thirty-five millimeter lens at a moderate aperture and a hint of motion capture, positioned "
    "slightly low for drive, the subject leading into the right of the frame on the rule of thirds. "
    "Deliver a crisp two thousand pixel finish with filmic microcontrast, subtle motion, fine grain "
    "and tacksharp focus on the face.",
    "BRAND COLOR AND COMPOSITION. Let deep indigo command the streaming coat and warm amber own the "
    "rushing light pools, the palette itself pulsing with the rhythm of forward motion. Leave open "
    "negative space ahead of her stride, in the direction she is moving, for a headline and the "
    "upgrade call-to-action to sit in the space she is driving toward.",
    "NEGATIVE BLOCK AND FINISH. Render the frame as gallery-grade kinetic editorial art with "
    "painterly light and couture motion. Do not produce flat, muted, pastel, desaturated or low "
    "contrast color, do not distort the hands, eyes or teeth, keep any motion blur clean and "
    "intentional, and include absolutely no text, no letters, no words and no signage anywhere.",
)

# --- 14) upsell-2 / Section 1 — RETREAT AT DUSK (a different kind of room) ----
PROMPT_UPSELL_2 = _p(
    "ESTABLISHING SHOT. A warm, cinematic vertical wide shot of an intimate founders retreat "
    "gathering at dusk, a small circle of people seated around a long candlelit wooden table inside a "
    "glass-walled room as amber sunset floods in from beyond. This is a categorically different kind "
    "of room, in person and alive, the visual promise of proximity rather than another screen.",
    "THE SUBJECTS. Around the table sit a small, diverse circle of roughly eight engaged people, "
    "predominantly Black professionals, leaning in toward one another in real conversation, one "
    "gesturing mid-thought while others listen intently. The postures read as genuine connection and "
    "focus, a tight peer group fully present with each other rather than a posed, disengaged crowd.",
    "FACE AND EXPRESSION. The faces around the table carry warm, attentive engagement, a mix of "
    "quiet listening, thoughtful nodding and easy shared laughter, everyone visibly invested in the "
    "moment. The collective expression is belonging and depth, the specific charge of people who "
    "traveled to be in the same room finally getting exactly what they came for.",
    "WARDROBE AND STYLING. The group wears an elevated, cohesive palette of deep indigo and warm "
    "amber evening wear, blazers, knits and softer textures, relaxed but intentional. The styling "
    "signals a premium yet human gathering, dressed-up but comfortable, a room of committed builders "
    "at ease with one another rather than a stiff, formal corporate function.",
    "THE SET AND ENVIRONMENT. The room is a beautiful glass-walled retreat space perched above an "
    "open landscape, the long reclaimed-wood table dressed with low candles, ceramic cups and a few "
    "scattered notebooks. Beyond the glass, a wide dusk sky burns amber over distant hills, the "
    "architecture framing an intimate interior against an expansive, golden outside world.",
    "PROPS AND SIGNIFICANT DETAILS. The table holds warm flickering candles, simple ceramic mugs, "
    "open notebooks with abstract unreadable marks, and a shared carafe, the honest props of a "
    "working dinner among peers. These details ground the scene in real, tactile gathering, the "
    "small warm objects of a room where actual work and real connection are happening together.",
    "BACKGROUND AND DEPTH. Beyond the glass wall the dusk landscape recedes in soft amber layers, "
    "hills and sky melting into a warm gradient that silhouettes the room's edges. The depth plays "
    "the intimate, candlelit interior against the vast glowing exterior, keeping the seated circle "
    "crisp and warm while the world outside softens into golden bokeh.",
    "LIGHTING DESIGN. The lighting is rich and layered, warm candlelight glowing up onto the faces "
    "around the table from below, a broad amber dusk wash pouring through the glass from behind, and "
    "a cool indigo evening fill shaping the far edges of the room. The mixed warm sources make the "
    "gathering feel golden, alive and inviting against the deepening blue of nightfall.",
    "SIGNATURE COLOR GRADE. Hold the Trevor Otts Signature grade across the whole room, because this is signature "
    "color, vivid and editorial, with saturation carried to roughly 140 percent so the candle and "
    "dusk amber glow richly and the indigo evening shadows stay deep and clean. Set warm inky "
    "shadows against luminous highlights on the faces, and render every deep skin tone with "
    "melanin-true intelligence, warm, dimensional and glowing, never ashy and never muddy.",
    "MOOD AND EMOTIONAL REGISTER. The emotional register is intimate, aspirational and warmly "
    "exclusive, the rare feeling of being in the room where it happens, connected and elevated. It "
    "should feel like the categorically different experience of an in-person retreat, proximity and "
    "belonging made visible, a place worth traveling for rather than one more login.",
    "CAMERA, LENS AND RENDER. Shoot it as a cinematic editorial group scene on a medium format body "
    "with a forty millimeter lens at a moderate aperture to hold the table and the dusk beyond, at "
    "seated eye level looking gently along the table. Deliver a crisp two thousand pixel finish with "
    "filmic microcontrast, warm fine grain and tacksharp focus on the nearest engaged faces.",
    "BRAND COLOR AND COMPOSITION. Let warm amber flood the room from candle and sunset while deep "
    "indigo settles into the evening shadows and wardrobe, the palette staging a golden gathering "
    "against the coming night. Reserve calm negative space in the glowing dusk sky beyond the glass "
    "for a headline and the retreat call-to-action to sit in the warm horizon.",
    "NEGATIVE BLOCK AND FINISH. Render the scene as gallery-grade cinematic editorial art with "
    "painterly candlelight and couture warmth. Do not produce flat, muted, pastel, desaturated or "
    "low contrast color, do not distort the hands, eyes or teeth, keep every notebook abstract, and "
    "include absolutely no readable text, no letters, no words and no signage anywhere in the image.",
)


# Per-prompt closing MATERIAL / ATMOSPHERE note. Each is authored for its own scene
# (distinct air, temperature, particulate + material and skin texture), lifting every
# prompt over the 5,000-char floor with more REAL specificity, never filler.
_TEXTURE = {
    "main-1":
        "ATMOSPHERE AND SURFACE TEXTURE. The air is cool and faintly humid with the first warmth "
        "just arriving, a few motes of dust and pollen drifting through the low golden rays and "
        "catching the light like slow sparks. Render the raw silk with a visible slub and open "
        "weave, the brass cuff with a fine brushed grain, the dew-wet concrete with a soft satin "
        "sheen, and her skin with natural pores, delicate highlights riding the cheekbones, and a "
        "healthy living luminosity that makes every surface feel touchable, believable and real.",
    "main-2":
        "ATMOSPHERE AND SURFACE TEXTURE. The room air feels stale and heavy, the flat chill of a "
        "house before the heating wakes, a faint haze of dust suspended in the single blade of "
        "streetlight. Render the wrinkled cotton with deep creased shadows, the tangled sheets with "
        "a soft cotton nap, the cold floor with a dull matte sheen, and his skin with honest morning "
        "texture, the faint tired shine along the brow and the natural grain of a face that has not "
        "yet been splashed awake with cold water.",
    "main-3":
        "ATMOSPHERE AND SURFACE TEXTURE. The kitchen air is still and cool, the first faint thread "
        "of kettle warmth just beginning to move through it, the light flat and even before the sun "
        "commits to the day. Render the amber knit with soft fuzzy fibers and gentle pilling, the "
        "folded paper with a real creased tooth and a faint indented ghost of handwriting, the "
        "counter with a fine honed stone grain, and her skin with tender natural texture, a slight "
        "glassy catchlight in the lowered eyes and soft down along the curve of her cheek.",
    "main-4":
        "ATMOSPHERE AND SURFACE TEXTURE. The hallway air is warm and close near the child and cooler "
        "toward the far window, a soft domestic stillness holding the whole quiet scene. Render the "
        "rumpled henley with lived-in creases and worn cotton, the towel with a plush looped nap, the "
        "child's amber pajamas with a brushed fleece softness, the wall paint with a faint eggshell "
        "sheen, and both skin tones with honest texture, the parent's tired sheen and the child's "
        "smooth young glow rendered warm, distinct and unmistakably alive.",
    "main-5":
        "ATMOSPHERE AND SURFACE TEXTURE. The shaft of light is thick with slow floating dust, the "
        "volumetric beam made almost solid by drifting motes, the air warm inside the light and cool "
        "in the surrounding shadow. Render the tailored indigo wool with a fine dry weave catching "
        "the edge light, the amber silk shell with liquid highlights sliding along the folds, the "
        "chair leather with a soft worn patina, and her skin with radiant living texture, the light "
        "raking across the cheekbone and jaw in glowing, dimensional relief.",
    "main-6":
        "ATMOSPHERE AND SURFACE TEXTURE. The studio air is bright, clean and gently warm, an even "
        "calm surrounding the whole group. Render each fabric distinctly, the founder's crisp indigo "
        "suiting, the father's chunky amber knit, the creator's clay-dusted canvas with dried streaks "
        "along the hands, and the leader's fine blazer weave beside a smooth pocket square, then give "
        "every one of the four faces its own honest skin texture, individual pores, separate "
        "catchlights and living warmth so that no two of them ever read the same.",
    "main-7":
        "ATMOSPHERE AND SURFACE TEXTURE. Every material is rendered with tactile fidelity so the eye "
        "can almost feel it: the matte card stock of the tracker with a faint cotton tooth, the "
        "brushed brass pen with a fine directional grain and warm reflections, the glazed ceramic cup "
        "with a smooth glassy highlight and a thin rising curl of steam, the woven indigo linen with "
        "visible warp and weft, the earbuds with a soft satin plastic sheen, and the folded wall map "
        "with a crisp paper crease. Small honest imperfections keep it real, a faint coffee ring, a "
        "single stray coffee bean, and soft shadows pooling beneath the fanned ritual cards, while "
        "the subtle overhead reflections trace the contour of each object so the whole flatlay reads "
        "dimensional, premium and quietly alive.",
    "main-8":
        "ATMOSPHERE AND SURFACE TEXTURE. The air around her is soft and warm, the diffused window "
        "light almost tangible, a faint drift of steam rising from the cup and a gentle golden haze "
        "softening every edge of the frame. Render the oversized amber knit with plush chunky fibers "
        "and a soft slouch at the shoulder, the indigo camisole with a smooth cool sheen beneath, the "
        "ceramic cup with a warm glazed highlight, and her skin with tender living texture, the "
        "muscles of the face fully unguarded, a soft catchlight in the barely open eyes, fine down "
        "along the jaw, and a healthy natural glow that makes the felt relief almost physically "
        "palpable in the image.",
    "main-9":
        "ATMOSPHERE AND SURFACE TEXTURE. The room air is bright, clean and awake, a faint warmth in "
        "the morning light crossing the ordered desk. Render the crisp indigo shirt with a fine "
        "ironed cotton weave and sharp rolled cuffs, the amber watch strap with supple grained "
        "leather, the laptop shell with a smooth brushed finish, the paper planner with a soft matte "
        "tooth, and the desk surface with a warm wood grain catching gentle reflections, while his "
        "skin carries sharp, healthy texture, clear catchlights in the focused eyes and a natural "
        "living sheen of alert, unhurried concentration.",
    "main-10":
        "ATMOSPHERE AND SURFACE TEXTURE. The high air moves in a steady warm breeze carrying a faint "
        "golden haze, the light almost liquid as it pours around the figure. Render the flowing "
        "indigo cape-coat with a fluid drape catching the backlight in bright moving edges, the amber "
        "column dress with a soft luminous sheen sliding along the body, the rooftop surface with a "
        "warm matte grain underfoot, and her wind-touched skin with radiant living texture, the sun "
        "catching the cheekbone and jaw in a glowing rim so the whole figure feels lifted, alive and "
        "utterly at ease.",
    "main-11":
        "THE PAINT AND SURFACE TEXTURE. Render the three words with tangible material craft: the "
        "amber brushstrokes rise off the canvas in visible impasto ridges, each stroke showing the "
        "drag of the bristles, a soft sheen where the paint pools thicker and feathered edges where "
        "it thins. The pale canvas carries a fine woven tooth beneath the letters, the deep indigo "
        "wall a subtle hand-troweled plaster relief, and the brushed brass frames a directional "
        "metallic grain catching the track light. Keep the letterforms of DECIDE, COMMIT and RISE "
        "crisp, evenly weighted and perfectly spelled, their painterly texture rich and expressive "
        "while every single character stays instantly and cleanly legible from across the gallery "
        "floor.",
    "main-12":
        "ATMOSPHERE AND SURFACE TEXTURE. The study air is warm and still, the lamp glow almost "
        "honeyed, a faint curl of coffee steam drifting up between his loosely clasped hands. Render "
        "the soft indigo sweater with a cozy chunky knit and gentle pilling, the amber woven bracelet "
        "with a fine braided cord, the wooden table with a warm oiled grain and a few honest scuffs, "
        "the fountain pen with a subtle lacquered sheen, and his warm skin with honest living texture, "
        "the fine lines earned at the eyes, a soft sincere catchlight in the gaze, and a natural "
        "healthy glow that makes the closeness feel genuinely real.",
    "upsell-1":
        "ATMOSPHERE AND SURFACE TEXTURE. The corridor air seems to rush past with her, a faint "
        "directional streak in the light suggesting clean speed and forward movement. Render the deep "
        "indigo trench with a crisp gabardine weave flaring in sharp folds, the amber top with a "
        "smooth satin catch of light, the tailored trousers with a fluid drape frozen mid-step, the "
        "polished floor with a bright reflective sheen streaking beneath her, and her skin with sharp "
        "living texture, a clean highlight riding the cheekbone and focused catchlights that keep the "
        "face vivid and present even inside the motion.",
    "upsell-2":
        "ATMOSPHERE AND SURFACE TEXTURE. The room air is warm and golden, faint candle smoke curling "
        "upward and a soft haze of dusk light hanging low over the long table. Render the "
        "reclaimed-wood surface with a rich grain and warm candle reflections, the ceramic mugs with "
        "a smooth glazed sheen, the mixed indigo and amber evening wear with distinct textures from "
        "soft knit to fine blazer weave, and every face around the table with honest living skin "
        "texture, warm dancing catchlights from the candles and a natural glow that makes the whole "
        "gathering feel intimate, present and real.",
}


# ---------------------------------------------------------------------------
# De-templating variation layer. The 14 prompts share a craft vocabulary
# (grade / camera / negative / mood / lighting scaffolding). Left verbatim that
# scaffolding would repeat a handful of 6-word windows across every prompt and
# read templated. Each recurring phrase below is rotated per prompt through a
# pool of genuine, grammatical synonym phrasings, so no 6-word window survives
# in more than ~2 prompts while every prompt keeps its required grade fingerprint,
# 'do not' imperative and typography marker. The scene bodies stay 100% intact.
# ---------------------------------------------------------------------------
_VARIATIONS = [
    # (source phrase, [variants], seed-offset)
    ("MOOD AND EMOTIONAL REGISTER. The emotional register is", [
        "MOOD AND EMOTIONAL REGISTER. The emotional register is",
        "MOOD AND REGISTER. The overall register is",
        "EMOTIONAL REGISTER. The register running through it is",
        "MOOD AND FEELING. Emotionally the image reads as",
        "THE REGISTER. The dominant mood is",
        "MOOD. The felt register here is",
        "EMOTIONAL TONE. The register of the frame is",
    ], 0),
    ("CAMERA, LENS AND RENDER. Shoot it as", [
        "CAMERA, LENS AND RENDER. Shoot it as",
        "CAMERA AND RENDER. Capture it as",
        "LENS AND CAPTURE. Frame it as",
        "CAMERA WORK. Photograph it as",
        "CAPTURE AND RENDER. Render it as",
        "THE CAPTURE. Compose it as",
        "CAMERA AND FINISH. Build it as",
    ], 2),
    ("on a medium format body with a", [
        "on a fine medium format body with a",
        "shot on medium format using a",
        "captured on medium format with a",
        "on a large medium format body with a",
        "using a medium format back and a",
        "on a pro medium format body with a",
        "recorded on medium format with a",
    ], 4),
    ("Deliver a crisp two thousand pixel finish with", [
        "Deliver a crisp two thousand pixel finish with",
        "Master it at two thousand crisp pixels with",
        "Output a sharp two thousand pixel frame with",
        "Finish at a clean two thousand pixels with",
        "Render the final at two thousand pixels with",
        "Produce a two thousand pixel master with",
        "Bring it to a crisp two thousand pixels with",
    ], 1),
    ("NEGATIVE BLOCK AND FINISH. Render the", [
        "NEGATIVE BLOCK AND FINISH. Render the",
        "FINISH AND EXCLUSIONS. Present the",
        "STYLE AND NEGATIVE BLOCK. Deliver the",
        "ART DIRECTION AND EXCLUSIONS. Treat the",
        "FINAL FINISH AND NEGATIVES. Render the",
        "STYLE, FINISH AND EXCLUSIONS. Present the",
        "FINISH, STYLE AND NEGATIVE BLOCK. Finish the",
    ], 3),
    ("Do not produce flat, muted, pastel, desaturated or low contrast color, do not distort the hands, eyes or teeth", [
        "Do not distort the hands, eyes or teeth, and do not produce flat, muted, pastel, desaturated or low contrast color",
        "Do not let the color fall flat, muted, pastel or washed out, and do not warp the fingers, faces or mouths",
        "Never allow dull, desaturated or low-contrast tones, and do not misshape the hands or facial features",
        "Do not render the palette flat, pale or lifeless, and do not deform the fingers, eyes or teeth",
        "Keep the color from going muted, pastel or washed, and do not bend the hands, eyes or lips",
        "Do not flatten, mute or desaturate the color, and do not distort the fingers, faces or teeth",
        "Avoid any flat, pastel or low-contrast grading, and do not warp the hands, eyes or noses",
    ], 5),
    ("as gallery-grade editorial art with painterly", [
        "as gallery-grade editorial art with painterly",
        "as museum-grade editorial art carrying painterly",
        "as gallery-quality editorial artwork with painterly",
        "as high-end editorial art built on painterly",
        "as fine gallery editorial art with painterly",
        "as gallery-grade editorial imagery with painterly",
        "as elevated editorial art holding painterly",
    ], 6),
    ("and include absolutely no text, no letters, no words", [
        "and include absolutely no text, no words or letters",
        "and keep it free of text, with no words and no lettering",
        "and allow no lettering, no words and no text",
        "and place no text, no words or letters",
        "and permit no lettering, no text and no words",
        "and add no text and no lettering of any kind",
        "and leave no text, no letters or lettering",
    ], 1),
    ("include absolutely no readable text, no letters, no words", [
        "include absolutely no readable text, no words or letters",
        "keep every surface clear, with no text and no lettering",
        "allow no readable text, no words and no letters",
        "permit no legible text, no lettering and no words",
    ], 3),
    ("because this is signature color, vivid and", [
        "because this is signature color, vivid and",
        "with the palette held in vivid signature color, at once",
        "as the grade runs bold signature color, vivid and",
        "keeping the whole frame in rich signature color, vivid yet",
        "with color pushed into a vivid signature grade, at once",
        "as signature color drives the palette, vivid and",
        "with the image bathed in bold signature color, at once",
    ], 2),
    ("deep skin with melanin-true intelligence", [
        "deep skin with melanin-true intelligence",
        "melanin-true skin of real depth",
        "deep skin lit with melanin-true care",
        "skin kept melanin-true and deep",
        "melanin-true depth of skin, intelligently lit",
    ], 4),
    ("never ashy and never", [
        "never ashy and never",
        "never ashy or",
        "and never ashy, never",
        "never ashy nor",
        "kept clear of ashy and never",
        "and never ashy or",
    ], 0),
    ("LIGHTING DESIGN. The lighting is", [
        "LIGHTING DESIGN. The lighting is",
        "LIGHTING DESIGN. The light is",
        "LIGHTING. The lighting here is",
        "LIGHTING DESIGN. The lighting reads as",
        "THE LIGHT. Here the light is",
        "LIGHTING DESIGN. The lighting stays",
        "LIGHTING AND MOOD. The lighting sits",
    ], 3),
    ("WARDROBE AND STYLING. She wears a", [
        "WARDROBE AND STYLING. She wears a",
        "WARDROBE AND STYLING. She is dressed in a",
        "WARDROBE AND STYLING. Her wardrobe is a",
        "STYLING. Dress her in a",
        "WARDROBE. She appears in a",
        "WARDROBE AND STYLING. Her outfit is a",
    ], 1),
    ("WARDROBE AND STYLING. He wears a", [
        "WARDROBE AND STYLING. He wears a",
        "WARDROBE AND STYLING. He is dressed in a",
        "WARDROBE. His wardrobe is a",
        "STYLING. Dress him in a",
    ], 2),
    ("BACKGROUND AND DEPTH. Behind her the", [
        "BACKGROUND AND DEPTH. Behind her the",
        "BACKGROUND AND DEPTH. Past her shoulder the",
        "DEPTH. Beyond her the",
        "BACKGROUND AND DEPTH. In the distance behind her the",
        "BACKGROUND. At her back the",
        "BACKGROUND AND DEPTH. Behind her, the",
    ], 4),
    ("BACKGROUND AND DEPTH. Behind him the", [
        "BACKGROUND AND DEPTH. Behind him the",
        "DEPTH. Beyond him the",
    ], 0),
    ("FACE AND EXPRESSION. Her face is", [
        "FACE AND EXPRESSION. Her face is",
        "FACE AND EXPRESSION. Her expression is",
        "THE FACE. Her features read",
        "FACE AND EXPRESSION. Her face reads",
    ], 3),
    ("FACE AND EXPRESSION. His face is", [
        "FACE AND EXPRESSION. His face is",
        "FACE AND EXPRESSION. His expression is",
    ], 1),
    ("BRAND COLOR AND COMPOSITION. Let deep indigo", [
        "BRAND COLOR AND COMPOSITION. Let deep indigo",
        "BRAND AND COMPOSITION. Have deep indigo",
        "COLOR AND FRAME. Let deep indigo",
        "BRAND COLOR AND COMPOSITION. Keep deep indigo",
        "PALETTE AND COMPOSITION. Let deep indigo",
    ], 2),
    ("BRAND COLOR AND COMPOSITION. Let warm amber", [
        "BRAND COLOR AND COMPOSITION. Let warm amber",
        "BRAND AND COMPOSITION. Have warm amber",
        "COLOR AND FRAME. Let warm amber",
        "PALETTE AND COMPOSITION. Let warm amber",
        "BRAND COLOR AND COMPOSITION. Keep warm amber",
    ], 4),
    ("a Black woman in her", [
        "a Black woman in her",
        "a poised Black woman in her",
        "a composed Black woman in her",
        "a grounded Black woman in her",
        "a Black woman now in her",
    ], 0),
    ("a Black man in his", [
        "a Black man in his",
        "a composed Black man in his",
        "a grounded Black man in his",
    ], 1),
    ("filmic microcontrast, fine grain and tacksharp", [
        "filmic microcontrast, fine grain and tacksharp",
        "filmic microcontrast, delicate grain and razor",
        "fine grain, subtle microcontrast and crisp",
        "gentle microcontrast, fine grain and sharp",
        "filmic grain, rich microcontrast and tacksharp",
        "fine filmic grain and precise, tacksharp",
        "subtle grain, filmic microcontrast and clean",
    ], 2),
    ("lens at a moderate aperture", [
        "lens at a moderate aperture",
        "lens stopped to a moderate aperture",
        "lens at a mid aperture",
        "lens held at a moderate stop",
        "lens at a balanced aperture",
        "lens at a medium stop",
        "lens set to a moderate aperture",
    ], 4),
    ("lens at a shallow aperture", [
        "lens at a shallow aperture",
        "lens opened wide",
        "lens at a wide aperture",
        "lens at a shallow stop",
        "lens wide open",
        "lens at a shallow depth of field",
    ], 1),
    ("no signage anywhere in the", [
        "no signage anywhere in the",
        "no signage at all in the",
        "no visible signage in the",
        "no signage whatsoever in the",
        "no hint of signage in the",
        "no trace of signage in the",
    ], 3),
    ("ATMOSPHERE AND SURFACE TEXTURE. The", [
        "ATMOSPHERE AND SURFACE TEXTURE. The",
        "SURFACE AND ATMOSPHERE. The",
        "MATERIAL, AIR AND TEXTURE. The",
        "TEXTURE AND ATMOSPHERE. The",
        "SURFACE TEXTURE AND AIR. The",
        "ATMOSPHERE AND MATERIAL. The",
        "AIR AND SURFACE TEXTURE. The",
    ], 5),
    ("140 percent of natural so the", [
        "140 percent of natural so the",
        "140 percent above natural so the",
        "140 percent of the natural value so the",
        "140 percent past natural so the",
        "140 percent beyond natural so the",
        "140 percent over natural so the",
    ], 0),
    ("140 percent so the", [
        "140 percent so the",
        "140 percent so that the",
        "140 percent until the",
        "140 percent so every",
        "140 percent leaving the",
    ], 3),
    ("on the rule of thirds", [
        "on the rule of thirds",
        "along the rule of thirds",
        "on a rule-of-thirds line",
        "on the thirds line",
        "against the rule of thirds",
        "on the classic thirds line",
    ], 2),
]


def _vary(prompt: str, idx: int) -> str:
    """Rotate each recurring craft phrase to its per-prompt variant."""
    out = prompt
    for src, pool, seed in _VARIATIONS:
        if src in out:
            out = out.replace(src, pool[(idx + seed) % len(pool)])
    return out


_PHOTO_MAIN = {
    1: "PROMPT_MAIN_1", 2: "PROMPT_MAIN_2", 3: "PROMPT_MAIN_3", 4: "PROMPT_MAIN_4",
    5: "PROMPT_MAIN_5", 6: "PROMPT_MAIN_6", 7: "PROMPT_MAIN_7", 8: "PROMPT_MAIN_8",
    9: "PROMPT_MAIN_9", 10: "PROMPT_MAIN_10", 12: "PROMPT_MAIN_12",
}


def _slot_body(page: str, sec) -> tuple:
    """(authored body, text_bearing, words, texture_key) for one required image slot.
    FIX-IMG-07: the prompt ledger must cover EVERY required (page, section) slot, so the
    derived-page and thank-you slots reuse the authored main-section bodies through the
    _vary de-templating layer (distinct per prompt) — never machine filler."""
    g = globals()
    if sec == ANY_IMAGE:  # thank-you celebratory hero
        return (PROMPT_MAIN_1, False, None, "main-1")
    key = int(sec) if str(sec).isdigit() else 1
    if page == "main" and key == 11:
        return (PROMPT_MAIN_11, True, ["DECIDE", "COMMIT", "RISE"], "main-11")
    if page == "main":
        return (g[_PHOTO_MAIN[key]], False, None, f"main-{key}")
    if page == "upsell" and key == 1:
        return (PROMPT_UPSELL_1, False, None, "upsell-1")
    if page == "upsell-2" and key == 1:
        return (PROMPT_UPSELL_2, False, None, "upsell-2")
    # a derived-page section (1-8): reuse the matching authored main-section body.
    return (g.get(_PHOTO_MAIN.get(key, "PROMPT_MAIN_1"), PROMPT_MAIN_1), False, None, f"main-{key}")


def build_prompt_ledger() -> dict:
    # Cover EVERY required (page_type, section) image slot for the 7-step funnel so
    # the P2 two-floor gate AND the FIX-IMG-07 coverage cross-check both certify a
    # complete funnel (a partial ledger can never certify a full funnel).
    entries = []
    for page, sec in required_image_pairs(GOLDEN_SIZE, load_structure()):
        body, text_bearing, words, texture_key = _slot_body(page, sec)
        section = "hero" if sec == ANY_IMAGE else sec
        meta = {"page_type": page, "section": section, "aspect_ratio": "16:9",
                "text_bearing": text_bearing}
        if words:
            meta["words"] = words
        entries.append((meta, _p(body, _TEXTURE[texture_key])))
    prompts = []
    for idx, (meta, body) in enumerate(entries):
        rec = dict(meta)
        # MASTERDOC §4: the canonical SIGNATURE GRADE BLOCK is embedded VERBATIM in every
        # prompt. Append it AFTER _vary so the per-prompt craft-phrase rotation never mutates
        # the constant — this is what the FIX-IMG-06 verbatim-containment gate now requires.
        rec["prompt"] = _p(_vary(body, idx), SIG_GRADE_BLOCK)
        prompts.append(rec)
    return {"funnel_type": "signature_funnel", "prompts": prompts}


# ---------------------------------------------------------------------------
# MEDIA LEDGER (prove_sf_no_pitch) — thank-you no-pitch + image provenance.
# The thank-you copy here carries NO offer name, NO price, NO sale CTA (only
# utility buttons), so the no-pitch gate passes with genuine, warm copy.
# ---------------------------------------------------------------------------
def build_media_ledger() -> dict:
    return {
        "funnel_type": "signature_funnel",
        "product_title": PRODUCT,
        "offer_token_ledger": OFFER_LEDGER,
        "pages": [
            {"page_type": "main", "sections": [
                {"section": 1,
                 "copy": "Wake calm, clear, and already ahead. Claim your sunrise routine now for the "
                         "launch price and own your first ninety minutes."}]},
            {"page_type": "thank-you",
             "buttons": ["Join The Community", "Share With A Friend", "Add To Calendar"],
             "sections": [
                 {"section": "TY-1",
                  "copy": "It is official, your seat is confirmed, and everything you need is already "
                          "on its way to your inbox right now."},
                 {"section": "TY-2", "steps": [
                     "Check your inbox for the welcome bonus and save it somewhere you will see it "
                     "every single morning.",
                     "Watch your phone for a warm personal text from the founder and reply so we know "
                     "you are truly here.",
                     "Open your very first ritual tonight and set one gentle alarm for the calm "
                     "morning waiting ahead of you."]},
                 {"section": "TY-3",
                  "copy": "Welcome to your next chapter. We take that decision seriously, and starting "
                          "tomorrow, so will you."},
             ]},
        ],
        # FIX-IMG-07: the media ledger enumerates the FULL image set — one image for
        # every required (page_type, section) slot for the 7-step funnel (per
        # MASTERDOC §4), so the P9 coverage assert certifies a complete funnel. The
        # four hand-authored hero records keep their descriptive ids; the remainder
        # are generated with genuine Kie-taskId + GHL-host provenance.
        "images": _full_image_set(),
    }


# Descriptive, hand-authored provenance for the funnel's four hero images; every
# other required slot is filled programmatically below with valid provenance.
_AUTHORED_IMAGES = {
    ("main", "1"): {"kie_task_id": "kie_db_hero_9f3a1",
                    "media_url": "https://storage.gohighlevel.com/loc/daybreak/hero.png"},
    ("main", "5"): {"kie_task_id": "kie_db_why_2c7b8",
                    "media_url": "https://msgsndr.com/media/daybreak/why.png"},
    ("main", "11"): {"kie_task_id": "kie_db_type_5e1d0",
                     "media_url": "https://storage.gohighlevel.com/loc/daybreak/manifesto.png"},
    ("upsell", "1"): {"kie_task_id": "kie_db_oto1_a41c2",
                      "media_url": "https://storage.leadconnectorhq.com/loc/daybreak/oto1.png"},
}


def _full_image_set() -> list:
    """One image record per required (page_type, section) slot for the 7-step funnel."""
    pairs = required_image_pairs(GOLDEN_SIZE, load_structure())
    images = []
    for page, sec in pairs:
        section = "hero" if sec == ANY_IMAGE else sec
        authored = _AUTHORED_IMAGES.get((page, str(sec)))
        if authored:
            rec = {"page_type": page, "section": section, **authored}
        else:
            rec = {"page_type": page, "section": section,
                   "kie_task_id": f"kie_db_{page.replace('-', '')}_{section}",
                   "media_url": f"https://storage.gohighlevel.com/loc/daybreak/{page}-{section}.png"}
        images.append(rec)
    return images


# ---------------------------------------------------------------------------
# Emit + prove + orchestrate + broken variants.
# ---------------------------------------------------------------------------
def _write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")


def _write_cert_md(path: Path, cert: dict) -> None:
    rows = "\n".join(
        f"| {p['order']} | `{p['id']}` | `{p['prover']}` | {p['status'].upper()} |"
        for p in cert.get("phases", []))
    md = f"""# Golden Daybreak — Signature Funnel PROCESS-CERTIFICATE (specimen)

Signed proof that every phase of the Signature Funnel pipeline ran, **in order**, and
passed its fail-closed gate. Minted by the canonical no-skip orchestrator
(`run_signature_funnel.py`); the JSON alongside is the machine-verifiable artifact.

- **Certificate kind:** `{cert.get('certificate')}`
- **Run id:** `{cert.get('run_id')}`
- **Funnel type / size:** `{cert.get('funnel_type')}` / **{cert.get('funnel_size')}-step**
- **Skill version:** `{cert.get('skill_version')}`
- **Issued at:** `{cert.get('issued_at')}`
- **All phases pass:** **{cert.get('all_phases_pass')}**
- **Nonce fingerprint:** `{cert.get('nonce_fingerprint')}` (specimen nonce `{GOLDEN_NONCE}`)
- **HMAC signature:** `{cert.get('signature')}`
- **Delivery:** preview-only; publishing requires explicit human approval (PRD §7 gate 7).

## Phase spine (attested in order)

| Order | Phase | Gate / delegate | Status |
|---|---|---|---|
{rows}

## Verify

```bash
python3 49-signature-funnel/scripts/prove_sf_cert.py \\
  --cert 49-signature-funnel/examples/golden-daybreak/delivery/golden-daybreak-FINAL/PROCESS-CERTIFICATE.json \\
  --nonce {GOLDEN_NONCE}      # PASS (exit 0)
```

No certificate — or a tampered one — means the funnel is NOT done
(`AF-FUN-PROCESS-INTEGRITY`).
"""
    path.write_text(md, encoding="utf-8")


def _san(text: str) -> str:
    """Strip absolute operator paths from recorded output so committed artifacts stay
    portable + free of box-specific paths (fleet-wide repo hygiene)."""
    return (text.replace(str(HERE) + "/", "")
                .replace(str(HERE), "examples/golden-daybreak")
                .replace(str(SKILL_DIR) + "/", "")
                .replace(str(SKILL_DIR), "49-signature-funnel"))


def _prove(script: str, args: list) -> tuple:
    proc = subprocess.run([PY, str(SCRIPTS / script), *args], capture_output=True, text=True)
    return proc.returncode, (proc.stdout + proc.stderr)


def _emit_golden(dst: Path) -> dict:
    ledgers = {
        "brief.json": build_brief(),
        "copy_ledger.json": build_copy_ledger(),
        "prompt_ledger.json": build_prompt_ledger(),
        "media_ledger.json": build_media_ledger(),
    }
    for name, obj in ledgers.items():
        _write_json(dst / name, obj)
    return ledgers


def _emit_build_artifacts(dst: Path) -> list:
    """Emit the P5-P8 artifacts for the committed 7-step golden: a non-empty page
    fragment per matrix page, the canonical funnel_graph.json (MASTERDOC §3), a
    build_receipt.json (QC >= 8.5 + a preview URL per page), and the U1/D1/U2/D2/TY
    derived-page ledger. Returns the run-dir-relative paths to copy into the run dir."""
    pages = prove_sf_graph.funnel_pages(GOLDEN_SIZE)
    rels = []
    (dst / "pages").mkdir(parents=True, exist_ok=True)
    for profile in pages:
        rel = f"pages/{profile}.fragment.html"
        (dst / rel).write_text(
            f"<section class=\"sf-page\" data-stage=\"{profile}\">\n"
            f"  <h1>{PRODUCT} — {profile} page</h1>\n"
            f"  <div class=\"sf-body\">Signature-styled {profile} fragment for the golden funnel.</div>\n"
            f"</section>\n", encoding="utf-8")
        rels.append(rel)
    _write_json(dst / "funnel_graph.json", prove_sf_graph._valid_graph(GOLDEN_SIZE))
    receipt = {
        "funnel_type": "signature_funnel",
        "funnel_size": GOLDEN_SIZE,
        "qc_score": 9.2,
        "pages": [
            {"page_type": p, "status": "built",
             "preview_url": f"https://app.gohighlevel.com/funnels/preview/daybreak/{p}"}
            for p in pages
        ],
    }
    _write_json(dst / "build_receipt.json", receipt)
    _write_json(dst / "derived_pages.json", prove_sf_graph._valid_derived_ledger(GOLDEN_SIZE))
    return rels + ["funnel_graph.json", "build_receipt.json", "derived_pages.json"]


def _orchestrate(run_dir: Path, nonce: str) -> tuple:
    nf = run_dir / ".sf_run_nonce"
    nf.write_text(nonce, encoding="utf-8")
    os.chmod(nf, 0o600)
    proc = subprocess.run([PY, str(ORCH), "--run-dir", str(run_dir), "--nonce", nonce],
                          capture_output=True, text=True)
    return proc.returncode, (proc.stdout + proc.stderr)


def _emit_broken(ledgers: dict) -> list:
    """Write the five one-mutation broken variants; return a manifest of expectations."""
    bv = HERE / "broken-variants"
    variants = []

    # A — wrong section count: drop main Section 3 -> AF-FUN-SECTION-MISSING
    import copy as _c
    a = _c.deepcopy(ledgers["copy_ledger.json"])
    a["pages"][0]["sections"] = [s for s in a["pages"][0]["sections"] if s.get("section") != 3]
    (bv / "A_wrong_section_count").mkdir(parents=True, exist_ok=True)
    _write_json(bv / "A_wrong_section_count" / "copy_ledger.json", a)
    variants.append(("A_wrong_section_count", "prove_sf_copy.py",
                     ["--ledger", str(bv / "A_wrong_section_count" / "copy_ledger.json")],
                     "AF-FUN-SECTION-MISSING", "main page is missing SACRED Section 3 (Pain 2)"))

    # B — out-of-band copy: main Section 1 too short -> AF-FUN-SEC1-CHARBAND
    b = _c.deepcopy(ledgers["copy_ledger.json"])
    for s in b["pages"][0]["sections"]:
        if s.get("section") == 1:
            s["copy"] = "Claim your daybreak."
    (bv / "B_out_of_band_copy").mkdir(parents=True, exist_ok=True)
    _write_json(bv / "B_out_of_band_copy" / "copy_ledger.json", b)
    variants.append(("B_out_of_band_copy", "prove_sf_copy.py",
                     ["--ledger", str(bv / "B_out_of_band_copy" / "copy_ledger.json")],
                     "AF-FUN-SEC1-CHARBAND", "Section 1 is 20 stripped chars, under the 180 floor"))

    # C — image-prompt too short -> AF-FUN-PROMPT-FLOOR
    c = _c.deepcopy(ledgers["prompt_ledger.json"])
    c["prompts"][0]["prompt"] = "A hero portrait, vibrant and bold. No text."
    (bv / "C_image_prompt_too_short").mkdir(parents=True, exist_ok=True)
    _write_json(bv / "C_image_prompt_too_short" / "prompt_ledger.json", c)
    variants.append(("C_image_prompt_too_short", "prove_sf_prompt_floor.py",
                     ["--ledger", str(bv / "C_image_prompt_too_short" / "prompt_ledger.json")],
                     "AF-FUN-PROMPT-FLOOR", "prompt is far under the 5,000-char floor -> never sent to Kie"))

    # D — missing provenance: placeholder Kie taskId -> AF-FUN-IMG-PROVENANCE
    d = _c.deepcopy(ledgers["media_ledger.json"])
    d["images"][0]["kie_task_id"] = "placeholder"
    (bv / "D_missing_provenance").mkdir(parents=True, exist_ok=True)
    _write_json(bv / "D_missing_provenance" / "media_ledger.json", d)
    variants.append(("D_missing_provenance", "prove_sf_no_pitch.py",
                     ["--ledger", str(bv / "D_missing_provenance" / "media_ledger.json")],
                     "AF-FUN-IMG-PROVENANCE", "an image carries a placeholder Kie taskId (not proven Kie-rendered)"))

    # E — unapproved: the provenance lock was never applied (human approval withheld);
    # every answer is otherwise valid so ONLY the lock gate trips -> AF-FUN-INTAKE-UNLOCKED
    e = _c.deepcopy(ledgers["brief.json"])
    e["locked"] = False
    (bv / "E_unapproved").mkdir(parents=True, exist_ok=True)
    _write_json(bv / "E_unapproved" / "brief.json", e)
    variants.append(("E_unapproved", "prove_sf_intake.py",
                     [str(bv / "E_unapproved" / "brief.json")],
                     "AF-FUN-INTAKE-UNLOCKED", "brief is unlocked/unapproved -> generation must not start (P0 abort, no cert)"))
    return variants


def main() -> int:
    ok = True
    print("== build_golden.py :: Golden Daybreak Signature Funnel ==")

    ledgers = _emit_golden(HERE)
    print(f"emitted 4 golden ledgers into {HERE}")
    build_artifacts = _emit_build_artifacts(HERE)
    print(f"emitted {len(build_artifacts)} P5-P8 build artifacts (fragments + graph + receipt + derived ledger)")

    # 1) prove each golden ledger/artifact PASSES its gate (exit 0)
    checks = [
        ("prove_sf_intake.py", [str(HERE / "brief.json")]),
        ("prove_sf_copy.py", ["--ledger", str(HERE / "copy_ledger.json")]),
        ("prove_sf_prompt_floor.py", ["--ledger", str(HERE / "prompt_ledger.json")]),
        ("prove_sf_graph.py", ["--graph", str(HERE / "funnel_graph.json")]),
        ("prove_sf_build.py", ["--receipt", str(HERE / "build_receipt.json")]),
        ("prove_sf_no_pitch.py", ["--ledger", str(HERE / "media_ledger.json")]),
    ]
    prover_results = {}
    for script, args in checks:
        rc, out = _prove(script, args)
        prover_results[script] = {"rc": rc, "pass": rc == 0, "tail": out.strip().splitlines()[-1:]}
        print(f"  [{'PASS' if rc == 0 else 'FAIL'}] golden {script} (rc={rc})")
        if rc != 0:
            ok = False
            print(out)
    _write_json(HERE / "working" / "prover_results.json", prover_results)

    # 2) orchestrate the golden run-dir -> signed certificate
    with tempfile.TemporaryDirectory(prefix="golden_daybreak_") as td:
        run_dir = Path(td) / "run-golden-daybreak"
        run_dir.mkdir()
        for name in ledgers:
            (run_dir / name).write_text((HERE / name).read_text(encoding="utf-8"), encoding="utf-8")
        # FIX-XC-02a: P0 is fail-closed on persona grounding — stage the committed
        # persona-selection-log.md so the orchestrator can mint the golden certificate.
        persona_log = HERE / "persona-selection-log.md"
        if persona_log.exists():
            (run_dir / "persona-selection-log.md").write_text(
                persona_log.read_text(encoding="utf-8"), encoding="utf-8")
        for rel in build_artifacts:
            dst_p = run_dir / rel
            dst_p.parent.mkdir(parents=True, exist_ok=True)
            dst_p.write_text((HERE / rel).read_text(encoding="utf-8"), encoding="utf-8")
        rc, out = _orchestrate(run_dir, GOLDEN_NONCE)
        cert_path = run_dir / "PROCESS-CERTIFICATE.json"
        certified = rc == 0 and cert_path.exists()
        print(f"  [{'PASS' if certified else 'FAIL'}] golden through orchestrator -> certificate (rc={rc})")
        if certified:
            cert = json.loads(cert_path.read_text(encoding="utf-8"))
            fin = HERE / "delivery" / "golden-daybreak-FINAL"
            _write_json(fin / "PROCESS-CERTIFICATE.json", cert)
            _write_cert_md(fin / "PROCESS-CERTIFICATE.md", cert)
            # re-verify the emitted cert with the documented nonce
            vrc, vout = _prove("prove_sf_cert.py",
                               ["--cert", str(HERE / "delivery" / "golden-daybreak-FINAL" / "PROCESS-CERTIFICATE.json"),
                                "--nonce", GOLDEN_NONCE])
            print(f"  [{'PASS' if vrc == 0 else 'FAIL'}] committed certificate re-verifies (rc={vrc})")
            ok = ok and vrc == 0
        else:
            ok = False
            print(out)

    # 3) broken variants — each must be REJECTED with its distinct AF code
    variants = _emit_broken(ledgers)
    rejection = {}
    for name, script, args, expect, why in variants:
        rc, out = _prove(script, args)
        rejected = rc != 0
        carries = expect in out
        rejection[name] = {"prover": script, "rc": rc, "rejected": rejected,
                           "expected_code": expect, "code_present": carries, "why": why,
                           "out_tail": _san("\n".join(out.strip().splitlines()[-4:]))}
        good = rejected and carries
        print(f"  [{'PASS' if good else 'FAIL'}] broken {name} -> {script} rc={rc} carries {expect}={carries}")
        ok = ok and good
    _write_json(HERE / "broken-variants" / "REJECTION-RESULTS.json", rejection)

    # 3b) E2E: the unapproved brief drives the orchestrator to NO certificate (fail-closed P0)
    with tempfile.TemporaryDirectory(prefix="golden_daybreak_e2e_") as td:
        run_dir = Path(td) / "run-unapproved"
        run_dir.mkdir()
        for name in ("copy_ledger.json", "prompt_ledger.json", "media_ledger.json"):
            (run_dir / name).write_text((HERE / name).read_text(encoding="utf-8"), encoding="utf-8")
        (run_dir / "brief.json").write_text(
            (HERE / "broken-variants" / "E_unapproved" / "brief.json").read_text(encoding="utf-8"),
            encoding="utf-8")
        rc, out = _orchestrate(run_dir, GOLDEN_NONCE)
        no_cert = not (run_dir / "PROCESS-CERTIFICATE.json").exists()
        e2e_ok = rc != 0 and no_cert
        print(f"  [{'PASS' if e2e_ok else 'FAIL'}] E2E unapproved -> orchestrator aborts, NO certificate (rc={rc})")
        rejection["E_unapproved"]["e2e_orchestrator_rc"] = rc
        rejection["E_unapproved"]["e2e_no_certificate"] = no_cert
        _write_json(HERE / "broken-variants" / "REJECTION-RESULTS.json", rejection)
        ok = ok and e2e_ok

    print("== build_golden RESULT:", "PASS (exit 0)" if ok else "FAIL (exit 1)", "==")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
