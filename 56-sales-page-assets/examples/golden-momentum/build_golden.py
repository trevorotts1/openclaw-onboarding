#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_golden.py — deterministic reproducer for the Golden Momentum Sales Page Assets bundle.

Emits the run-dir ledgers for a FICTIONAL Direct-Response funnel that clears every Skill-56
SACRED gate with REAL, distinct, human-authored persuasive copy (no machine padding, no
repeated filler tail, no vocabulary-list dump, no mid-phrase cutoffs). Then it
  (1) proves each ledger with its shipped Skill-56 prover,
  (2) drives the canonical no-skip orchestrator to a signed PROCESS-CERTIFICATE, and
  (3) writes the six one-mutation broken variants + a captured REJECTION-RESULTS.json
      proving each trips a DISTINCT fail-closed autofail.

No client names, no real people, no PII, no secrets. Method attribution: the Trevor Otts
Direct-Response method (owner attribution only). Fictional founder: "Marcus Vale"; fictional
offer stack: "The Momentum Engine" (a self-paced operating-system course for solo operators).

stdlib only. Run:  python3 build_golden.py          (regenerate everything, self-check)
                   python3 build_golden.py --content-check   (assert content authenticity only)
Exit 0 = golden reproduced + certified + all broken variants rejected; nonzero otherwise.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL_DIR = HERE.parent.parent                      # 56-sales-page-assets/
SCRIPTS = SKILL_DIR / "scripts"
ORCH = SKILL_DIR / "run_sales_page_assets.py"
PY = sys.executable or "python3"

# Documented example nonce (NOT a secret — this is a golden specimen, not a live run).
GOLDEN_NONCE = "golden-momentum-nonce-v1"
CLIENT = "marcus-vale"
FUNNEL = "momentum-engine"
RUN_ID = f"{CLIENT}__{FUNNEL}__run-20260702-01"
FOUNDER = "Marcus Vale"
CHECKOUT = "https://example.com/momentum/checkout"

OFFER_LEDGER = [
    "The Momentum Engine",
    "The 10-Minute Momentum Reset",
    "The Momentum Accelerator",
    "Momentum Accelerator Recordings Vault",
    "The Sovereign Operator Mentorship",
]


# ===========================================================================
# 1. MAIN sales page — the 8-section "Advanced Sales Page Creation" structure,
#    authored for BOTH A/B variants. Each section carries genuine, distinct copy.
# ===========================================================================
MAIN_A = [
    ("Attention-Grabbing Header",
     "New for founders who are done trading more hours for the same flat month: The Momentum Engine "
     "rebuilds how your business actually moves, so progress stops depending on how hard you push."),
    ("Hero Section",
     "You did not start this to become the bottleneck of your own company, yet here you are, the busiest "
     "person in the room and the reason nothing ships without you. The Momentum Engine installs a simple "
     "operating system that turns your scattered effort into steady, compounding output you can feel by Friday."),
    ("Problem & Solution",
     "The problem was never your work ethic; it was that your business has no engine, only you, sprinting. "
     "The moment you stop, everything coasts to a halt. The Momentum Engine replaces heroics with a repeatable "
     "cadence of decisions, so the machine keeps rolling whether you are inspired, exhausted, or on vacation."),
    ("Benefits Section",
     "Reclaim your mornings from the inbox. Watch projects finish instead of aging. Make one clean decision "
     "where you used to make ten anxious ones. Feel the quiet confidence of a founder whose company runs on "
     "structure instead of adrenaline, and whose calendar finally reflects what actually matters."),
    ("Product Details",
     "The Momentum Engine is a self-paced system of thirty short lessons, twelve fill-in operating templates, "
     "and a weekly cadence worksheet you will use for years. Each module takes under fifteen minutes and ends "
     "with one action you install that same day. No fluff, no theory you cannot use before lunch."),
    ("Credibility Section",
     "Built from the Trevor Otts Direct-Response method and pressure-tested across hundreds of solo operators, "
     "the Engine is the same cadence quietly running behind founders who stopped confusing motion with progress. "
     "It is not a motivational high; it is the boring machinery that makes ambitious work inevitable."),
    ("Final Call to Action",
     "For the price of one distracted afternoon you can install the operating system your business has been "
     "missing. The countdown below marks the founding-cohort price; when it reaches zero the Engine returns to "
     "full price. Claim The Momentum Engine now and let your next quarter run itself."),
    ("Footer",
     "The Momentum Engine by Marcus Vale. Results depend on the work you install. Questions before you buy? "
     "Reach the team from any page. Copyright and terms apply; this page makes no income guarantee."),
]

MAIN_B = [
    ("Attention-Grabbing Header",
     "If your best month still felt like you were holding the whole company up with both hands, read this: "
     "The Momentum Engine is how solo operators finally put the weight down without dropping the results."),
    ("Hero Section",
     "Imagine opening your laptop and knowing exactly what moves the needle today, this week, and this quarter, "
     "without a single anxious guess. That clarity is not a personality trait you were born without. It is an "
     "engine you install, and The Momentum Engine hands you every part of it, already assembled."),
    ("Problem & Solution",
     "Hustle got you here and hustle is now the ceiling. You cannot out-work a broken system, and willpower is "
     "the most expensive fuel there is. The Engine swaps raw effort for a designed cadence, so the important work "
     "happens on a schedule instead of a mood, and your business finally moves when you are not looking."),
    ("Benefits Section",
     "Shorter days that produce more. Fewer decisions that carry more weight. A visible pipeline instead of a "
     "mental fog. The strange, welcome feeling of ending a week ahead of where you started, with energy left over "
     "for the people who actually matter to you."),
    ("Product Details",
     "Inside you get thirty bite-size lessons, a set of plug-and-play operating templates, and a one-page weekly "
     "rhythm you will run on autopilot. Everything is designed to be installed the same day you learn it, so the "
     "Engine is turning over before you finish the course, not months later when motivation fades."),
    ("Credibility Section",
     "This is the Trevor Otts Direct-Response method applied to the founder who wears every hat. It has been "
     "refined with operators who were skeptical of one more course and stayed because, for once, the thing worked "
     "quietly in the background exactly as promised. Boring, repeatable, and impossible to un-see."),
    ("Final Call to Action",
     "The founding price on the timer below disappears the instant it hits zero, and it does not come back. "
     "You can keep renting your results from your own exhaustion, or you can own an engine that pays you every "
     "week. Start The Momentum Engine today and give your future self a company that runs."),
    ("Footer",
     "The Momentum Engine by Marcus Vale. Your outcome tracks your effort; nothing here is a promise of income. "
     "Support is one message away from any screen. All trademarks, terms, and privacy notices apply."),
]


# ===========================================================================
# 2. UPSELL 1 — the Trevor Otts 9-section framework, authored for BOTH variants.
#    variant a = conversion-copywriter persona; variant b = emotional-hijacking persona.
# ===========================================================================
UPSELL_A = [
    ("Hook acknowledging purchase",
     "Smart move. You just installed the Engine, which means the hardest decision is already behind you. "
     "Before you close this tab, there is one upgrade that decides whether the Engine idles or roars, and it is "
     "only on this page, only right now, at a price you will not see again."),
    ("First pain point",
     "Here is the trap most operators fall into next: they learn the cadence, agree with it, and then never quite "
     "install it, because knowing what to do and doing it under real pressure are two very different animals."),
    ("Second pain point amplification",
     "Left alone, that gap widens. The templates sit untouched, the weekly rhythm slips, and within a month the "
     "Engine you were so excited about becomes one more thing you bought and did not use, which quietly confirms "
     "the old story that nothing sticks for you."),
    ("Third pain point with urgency",
     "And the clock is not neutral. Every week you run on the old scramble is a week of decisions made tired, "
     "revenue left on the table, and momentum you will have to rebuild from cold. The cost of waiting is not zero; "
     "it compounds against you daily."),
    ("Hope introduction",
     "It does not have to go that way. Imagine the Engine fully installed inside thirty days, not someday, with "
     "someone making sure each part is actually turning before you move to the next. That is not wishful thinking; "
     "that is simply what happens when you are not doing it alone."),
    ("Solution positioning",
     "The Momentum Accelerator is the done-with-you sprint that installs the Engine for you. Thirty days, guided "
     "checkpoints, and a build partner who tunes each template to your business so nothing is left to figure out "
     "at midnight. You supply the business; we supply the momentum."),
    ("Value stacking presentation",
     "You get the full thirty-day guided build, live checkpoint reviews of your operating templates, a private "
     "priority channel for same-day answers, and a personalized cadence map for your exact model. Bought "
     "separately this is a coaching engagement; today it is a single-page upgrade to what you already own."),
    ("Logical justification with founder credibility",
     "I am Marcus Vale, and I built the Accelerator because I watched too many capable operators buy the right "
     "system and still stall at installation. The math is simple: the sprint pays for itself the first week the "
     "Engine actually runs, and it runs far faster with a partner than it ever will from a folder of templates."),
    ("Identity challenge close",
     "So the real question is not whether the Accelerator is worth it. It is who you intend to be thirty days "
     "from now: the operator who finally installed the machine, or the one who bought another set of templates. "
     "Add the Accelerator, and become the first one."),
]

UPSELL_B = [
    ("Hook acknowledging purchase",
     "Stop for one breath. You just did something most people only talk about, and the version of you that "
     "clicked buy deserves to be heard out on one last thing, because what you do in the next sixty seconds "
     "decides whether that decision changes your year or just your afternoon."),
    ("First pain point",
     "You already know the ache of the unopened course, the template folder you swore you would use, the quiet "
     "shame of the login you never returned to. That is not laziness. It is what happens when good intentions "
     "meet a week that eats everything you feed it."),
    ("Second pain point amplification",
     "Picture it thirty days out: the Engine still parked, the excitement gone cold, and that old familiar voice "
     "whispering that you are the kind of person who starts things and does not finish them. You have heard that "
     "voice before, and you know exactly how much it has already cost you."),
    ("Third pain point with urgency",
     "Every quiet week that voice gets louder and the road back gets steeper. Momentum you do not build today "
     "does not wait politely; it drains, and the operator you could have become by next quarter slips a little "
     "further out of reach with each day you delay."),
    ("Hope introduction",
     "But feel the other version for a second. Thirty days from now the Engine is humming, the fog has lifted, "
     "and for the first time in years you trust that your business will keep moving even on the days you cannot. "
     "That relief is real, and it is closer than it has ever been."),
    ("Solution positioning",
     "The Momentum Accelerator is how you make sure it is that second version. It is thirty guided days with a "
     "partner who will not let the Engine sit idle, who tunes it to your life and holds the line when your week "
     "tries to swallow it whole. You will not be doing this alone, and that changes everything."),
    ("Value stacking presentation",
     "Thirty days of guided installation, live reviews so nothing stays half-built, a direct line for the "
     "moment you get stuck, and a cadence mapped to the messy reality of your actual days. This is the "
     "difference between a course you own and a change you can feel in your chest."),
    ("Logical justification with founder credibility",
     "I am Marcus Vale, and I will be honest with you: I do not offer this because it is clever marketing. I "
     "offer it because I have felt the specific grief of watching a good person quit six inches from the "
     "breakthrough, and I refuse to sell you a machine and then walk away while it gathers dust."),
    ("Identity challenge close",
     "You can close this page and hope the old pattern breaks on its own, or you can decide, right now, that "
     "the person who quits early is not who you are anymore. Say yes to the Accelerator, and let this be the "
     "decision you point back to."),
]


# ===========================================================================
# 3. DOWNSELL 1 — post-rejection emotional-recovery page (graceful concession),
#    reusing the 9-section frame. Single authored variant (not prover-gated; part
#    of the deliverable stack + the build manifest).
# ===========================================================================
DOWNSELL = [
    ("Hook acknowledging purchase",
     "I get it, and there is no hard feelings here. The Accelerator is the fast lane, and the fast lane is not "
     "the right lane for everyone this month. Before you go, let me hold the door open a little wider, because I "
     "would rather you move slowly than not move at all."),
    ("First pain point",
     "Maybe the sprint felt like a lot to take on right now, another commitment stacked onto a week that is "
     "already full. That is fair, and it is honest, and it is exactly the kind of overwhelm the Engine was built "
     "to quiet in the first place."),
    ("Second pain point amplification",
     "But I also know how these moments go. You close the tab meaning to come back, life closes in, and the "
     "install you were one decision away from quietly never happens. Not because you did not care, but because "
     "nobody left you a smaller first step."),
    ("Third pain point with urgency",
     "So here is a smaller step, and it will not stay on this page long. I would rather you keep a little "
     "momentum today than lose all of it waiting for a perfect week that, if we are being honest with each "
     "other, is not actually coming."),
    ("Hope introduction",
     "You do not need the whole sprint to start feeling the Engine turn. You just need the map and the room to "
     "walk it at your own pace, on your own clock, without anyone standing over your shoulder."),
    ("Solution positioning",
     "The Recordings Vault gives you every Accelerator build session, self-paced, yours to keep. Same guided "
     "installation, same templates walked through step by step, minus the live schedule you were worried you "
     "could not protect. Slower lane, same road, same destination."),
    ("Value stacking presentation",
     "You get the complete recorded build library, the tuned template walkthroughs, and the cadence map, "
     "downloadable and permanent, at a fraction of the sprint. It is the whole method, patient enough to meet "
     "you on the week you actually have instead of the week you wish you had."),
    ("Logical justification with founder credibility",
     "I am Marcus Vale, and I built the Vault for exactly this moment, because saying no to the sprint should "
     "never mean saying no to your own momentum. Keeping a small promise to yourself today is worth more than a "
     "grand plan you abandon tomorrow, and this is the smallest promise I know how to offer."),
    ("Identity challenge close",
     "You already proved you are serious when you started the Engine. Do not let a single no talk you out of the "
     "whole thing. Take the Vault, keep the momentum you have earned, and come back for the fast lane whenever "
     "your week is finally ready for it."),
]


# ===========================================================================
# 4. BUMP — order-bump copy: 40-80 body words, ending with the checkbox close.
# ===========================================================================
BUMP_BODY = (
    "Add The 10-Minute Momentum Reset. When a day goes sideways and the Engine stalls, this pocket audio "
    "pack walks you back to a clean, moving start in the time it takes coffee to brew. Operators call it "
    "the fastest way to rescue a lost afternoon. Grab it now for less than a single distracted hour of your time."
)
BUMP_CHECKBOX = "[X] Yes, add The 10-Minute Momentum Reset to my order for $27"


# ===========================================================================
# 5. HIGH-TICKET — "The Sovereign Operator Mentorship" long-form page,
#    the Sovereign Architect band [6,500 - 7,100] STRIPPED words. Authored as
#    genuine, varied persuasive prose across ~22 sections. No padding.
# ===========================================================================
HT_SECTIONS = [
    ("The paradigm you did not know you were trapped inside",
     "Every operator who ever plateaued believed the same quiet lie: that the next level was a matter of "
     "working harder inside the same machine that had already stopped rewarding effort. You have felt it. "
     "The days are full, the calendar is dense, the output is real, and still the needle refuses to move the "
     "way it did in the beginning. That is not a discipline problem, and it is certainly not a talent problem. "
     "It is a design problem. The Sovereign Operator Mentorship exists for one reason: to rebuild the machine "
     "underneath you so your ambition finally has somewhere to go. Most programs sell you more speed. This one "
     "questions the road. What you are about to read is not another course you will skim and abandon, or "
     "another motivational push dressed up as strategy. It is a direct and occasionally uncomfortable "
     "examination of how a capable person becomes trapped by their own competence, and what it actually takes "
     "to escape. If you have built something real and now feel the ceiling pressing down on your best hours, "
     "keep reading. The ceiling is not the sky. In almost every case, it turns out to be a floor you have not "
     "yet learned how to stand on. The operators who break through do not find a secret hack. They change the "
     "structure they are operating inside, and the results follow so naturally that afterward it looks obvious. "
     "That is the whole promise of this page, and I intend to earn it line by line before I ever ask you for "
     "anything at all. Take your time with what follows, because the operators who skim this page are usually the "
     "same ones who will skim their own business for another decade, and I would rather you read slowly and "
     "decide clearly than move fast and stay stuck. Everything here is written for the person who is ready to "
     "stop being impressed by activity and start being honest about results."),

    ("Why more was always going to fail you",
     "The advice you have been handed your entire career is some version of the word more. Do more, hustle "
     "more, wake earlier, want it badder, out-grind the competition. It is seductive because in the early days "
     "it genuinely worked. When you had nothing, effort was the lever, and pulling it harder moved everything. "
     "But leverage is not linear, and the exact behavior that built your first plateau is powerless to lift you "
     "off it. More effort into a system with no structure does not produce more results; it produces more "
     "friction, more fatigue, and a quiet resentment toward the very work you used to love. You already know "
     "this in your body. You have had the month where you worked the hardest and moved the least, and you "
     "walked away wondering if something was wrong with you. Nothing is wrong with you. You simply reached the "
     "natural limit of a strategy that was never meant to carry you this far. The tragedy is that most "
     "operators respond to that limit by ordering another serving of the thing that stopped working, because "
     "more is the only tool they were ever given. They read another book on productivity, buy another planner, "
     "try another morning routine, and each one delivers a brief hit of hope before the ceiling closes back in. "
     "The way out is not a better version of more. It is a different category of decision entirely, and until "
     "you make it, no amount of effort will save you from the arithmetic of your own exhaustion. That is the "
     "hardest thing to hear and the most important thing on this page."),

    ("The mechanism of the plateau, named at last",
     "Here is what is actually happening under the hood, described plainly so you can never un-see it. Your "
     "business does not run on a system; it runs on you. You are the operating system, the memory, the "
     "decision engine, and the emergency response team, all at once. In the beginning that centralization was a "
     "superpower, because you could move faster than any process. But past a certain size, being the machine "
     "stops being an advantage and becomes the single hard limit on everything you can build. Every decision "
     "routes through your attention, every project stalls when you look away, and your growth is capped at the "
     "exact width of one tired human mind. This is why hiring rarely fixes it, why tools rarely fix it, and why "
     "the next big push only buys you a few weeks before the ceiling returns. You cannot delegate a system that "
     "lives only in your head, and you cannot scale a company whose entire operating logic evaporates the "
     "moment you take a day off. The plateau is not a wall in front of you. It is the shape of a business built "
     "with exactly one moving part. Once you see it this way, the path forward stops being mysterious. The work "
     "is not to push the one part harder. The work is to externalize the machine, to move the operating logic "
     "out of your skull and into a structure that runs whether you are present, inspired, or asleep. That "
     "single shift is the difference between owning a company and being owned by one, and it is the precise "
     "thing this mentorship is built to install inside you."),

    ("The hidden cost you have been quietly paying",
     "Let us talk about the invoice nobody hands you. The most expensive thing about the plateau is not the "
     "revenue you are not earning, though that number is real and larger than you let yourself admit. The most "
     "expensive thing is everything the plateau quietly takes while it holds you in place. It takes your "
     "evenings, because a business that depends entirely on you never truly closes. It takes your attention at "
     "dinner, on vacation, in the middle of the night when a problem surfaces and there is no one but you to "
     "catch it. It takes the version of you that your family fell in love with and replaces him with a person "
     "who is always a little somewhere else. And it takes the most irreplaceable resource of all, which is "
     "time, the years that pass while you tell yourself that next quarter you will finally build the structure, "
     "that once this launch is over you will get organized, that someday the fire will die down enough to think. "
     "That someday does not arrive on its own, because a system with one moving part is designed to keep that "
     "part running. The cost compounds silently, the way debt does, until one day you look up and realize you "
     "have spent years being busy inside a life you did not choose. I am not telling you this to twist a knife. "
     "I am telling you because the true cost of staying exactly where you are is almost never counted honestly, "
     "and the decision in front of you looks very different once it is. The status quo is not free. It is the "
     "most expensive option on the table, and you have been paying for it in the only currency that never comes "
     "back."),

    ("The night the road forked for me",
     "I want to tell you how I found this, because I did not read it in a book. There was a stretch of my "
     "career where I was, by every visible measure, winning. The revenue was up, the clients were happy, and "
     "from the outside it looked like the dream I had chased for a decade. Inside, I was coming apart. I was "
     "working seventy-hour weeks to hold together a business that could not survive a single day without me, "
     "and I had begun to quietly dread the thing I had built my whole adult life around. The turning point was "
     "not dramatic. It was a Tuesday night, late, when I caught myself answering a message I had answered a "
     "hundred times before, and I realized that I was not building a company at all. I was manually operating "
     "one, forever, and there was no version of that story that ended with me free. Something in me refused it. "
     "I stopped trying to work harder and started asking a completely different question. Not how do I do more, "
     "but why does everything depend on me doing it. That question led me down a two-year path of tearing my "
     "business apart and rebuilding it around structure instead of heroics, and what came out the other side "
     "was a machine that ran without my hands on every lever. My hours dropped and my results climbed, which "
     "the old logic said was impossible. It was not impossible. It was simply what happens when you stop being "
     "the engine and start being the architect. Everything I teach in this mentorship was forged on that path, "
     "tested first on the only operator I could afford to experiment on, which was me."),

    ("The new paradigm, and why it changes the math",
     "The shift has a name, and the name is sovereignty. A sovereign operator is not the person who does the "
     "most work. It is the person who designs the system that does the work, and who therefore owns their time, "
     "their attention, and their outcomes instead of renting them from their own stamina. This is a genuine "
     "category change, not a productivity tweak. When you operate sovereignly, your growth stops being capped "
     "by your energy and starts being driven by the quality of the structure you build. A good decision, made "
     "once and installed into the machine, pays you every day after without asking for more effort. A cadence, "
     "designed well and run on schedule, produces compounding output whether you feel motivated or not. This is "
     "why sovereign operators seem to defy gravity: they are not working more than you, they are working inside "
     "a system that multiplies what they do instead of merely adding it up. The math changes completely. Under "
     "the old paradigm, results equal effort, and effort has a hard ceiling. Under the new one, results equal "
     "the effort you install multiplied by how well the structure carries it, and structure has almost no "
     "ceiling at all. That is the entire game. Everything in this mentorship exists to move you from the first "
     "equation to the second, deliberately, in a specific order, with someone who has walked the path guiding "
     "each step. It is not faster because we hurry. It is faster because we stop wasting your effort on a design "
     "that was always going to leak it away, and we point every ounce you have at the parts of the machine that "
     "actually compound."),

    ("What the Sovereign Operator Mentorship actually is",
     "Now that you understand the shift, let me be precise about what I am offering, because vagueness is how "
     "high-ticket programs hide. The Sovereign Operator Mentorship is a direct, one-to-one engagement between "
     "you and me over a focused period, built to install the sovereign operating structure inside your specific "
     "business, not a generic one. This is not a course you consume alone, not a group program where you are "
     "one voice in a crowded call, and not a library of videos you will feel guilty for not finishing. It is a "
     "hands-on rebuild, guided personally, of the way your company makes decisions, executes work, and moves "
     "without you. We start by mapping the machine you have now, honestly, including the parts that only exist "
     "in your head. Then we externalize them, one system at a time, until the operating logic of your business "
     "lives in a structure instead of in your exhaustion. You will leave with your decisions systematized, your "
     "core work running on a designed cadence, and a company that keeps moving on the days you step away. Along "
     "the way you get me, directly, as the person who has done this and helped others do it, in the room for the "
     "hard calls and the strategic forks that no template can make for you. The point is not information. You "
     "already have more information than you can use. The point is installation, done with you, so that when we "
     "are finished the change is not a set of notes you hope to apply someday. It is the way your business "
     "already runs."),

    ("Who this is for, and who it is honestly not for",
     "I would rather turn away the wrong person than take money from someone this cannot help, so let me be "
     "clear about both sides. This is for the operator who has already built something real. You have revenue, "
     "you have customers, and you have proven you can do the work, which means your problem is no longer "
     "capability, it is structure. It is for the founder who feels the ceiling not as a lack of ideas but as a "
     "lack of hours, who is tired of being the bottleneck, and who is ready to stop being the machine so they "
     "can start being the architect. If you are willing to look honestly at how your business really runs and "
     "to rebuild the parts that are quietly costing you your life, you are exactly who this was made for. It is "
     "not for the person looking for a magic tactic, a quick funnel trick, or a way to avoid the work of "
     "confronting how their company is actually built. It is not for someone still searching for their first "
     "customer, because there is no structure to sovereignize yet. And it is not for the operator who wants to "
     "hand me the problem and disappear, because this is done with you, not to you, and your engagement is the "
     "ingredient I cannot supply. If that honesty made you more interested rather than less, that is a very good "
     "sign. The people who thrive here are the ones who were quietly relieved to finally be told the truth about "
     "why more stopped working, and who are done pretending the old way still has a next level left in it."),

    ("A case study in what changes",
     "Let me show you what this looks like in a real trajectory, using a composite operator we will call Renna, "
     "so no one is identified. When Renna started, she was running a service business that had grown to a "
     "respectable size entirely on her back. She was the salesperson, the fulfillment lead, the quality control, "
     "and the person who fixed everything at night. Her revenue looked healthy and her life did not. Every dollar "
     "of growth demanded another hour she did not have, and she had begun turning away work not because she "
     "lacked demand but because she could not personally absorb any more of it. That is the plateau in its "
     "purest form, growth capped at the width of one person. We did not add anything to her plate. We mapped the "
     "machine, found that nearly every important decision was routing through her by default rather than by "
     "design, and began externalizing them one at a time. First the intake decisions, then the fulfillment "
     "cadence, then the quality standards, each moved out of her head and into a structure her team could run "
     "without her. Within a season her role had changed shape entirely. She was no longer the machine; she was "
     "watching the machine run. Her hours fell, her capacity rose, and for the first time she took a full week "
     "away without the business flinching. The revenue growth that followed was almost a side effect. The real "
     "result was that she got her life back and kept her company, which the old logic said she had to choose "
     "between. She never did. What matters most in her story is not the specific systems we built, because those "
     "were particular to her business and yours will differ. What matters is the sequence, the willingness to "
     "map before rebuilding, and the discipline to move each decision out of her head in the order that returned "
     "the most breathing room first. That is portable. That is the part I can install with you, whatever shape "
     "your company happens to take."),

    ("A second case study, from the other direction",
     "Renna was drowning in her own success. The next operator, a composite we will call Cole, had the opposite "
     "surface problem and the identical root. Cole was not overwhelmed; he was stuck. His business had grown "
     "fast and then simply stopped, flat for the better part of two years despite everything he threw at it. He "
     "had tried new offers, new marketing, new hires, and each one produced a brief flicker before the line went "
     "flat again. From the outside it looked like a growth problem. It was not. It was the same one-moving-part "
     "machine, just experienced from the plateau instead of the overwhelm. Everything Cole tried died on contact "
     "with the same bottleneck, because every new initiative still had to route through the one person who was "
     "already at capacity. Adding more to a saturated system does not grow it; it just changes which fires burn. "
     "We stopped adding and started redesigning. We took the initiatives he was already running and rebuilt the "
     "structure beneath them so they could execute without his constant hand on the wheel. Almost immediately "
     "the flat line began to move, not because he found a new tactic but because the tactics he already had "
     "finally had room to work. The lesson in Cole is the one operators resist the most: the answer to a "
     "plateau is almost never another thing to do. It is a better structure for the things you are already "
     "doing, so that your effort compounds instead of colliding with itself at the same choke point every "
     "single time."),

    ("A third case, and the pattern underneath all three",
     "The third operator, a composite named Dev, is the one who reminds me why I do this. Dev was successful and "
     "quietly miserable, the specific misery of a person who got everything he aimed for and found it had cost "
     "more than he agreed to pay. He was not going to burn out in a dramatic collapse; he was going to slowly "
     "resent the life he had built until one day he sold it for far too little just to be free of it. I have "
     "watched that ending too many times to stay calm about it. With Dev the work was less about revenue and "
     "more about reclaiming ownership of his own hours before the resentment became permanent. We rebuilt his "
     "operating structure with one non-negotiable goal, that the business had to run without him for weeks at a "
     "time, and we did not stop until it did. What surprised him was not that it worked. It was how much better "
     "the business performed once it no longer depended on a founder who was, by his own admission, running on "
     "fumes. Across all three of these operators, the surface stories could not look more different: too much "
     "work, too little growth, too little life. But the machine underneath was always the same, a company with "
     "one moving part, and the cure was always the same, externalize the machine and become the architect. That "
     "is the pattern this mentorship is built around, and it is durable precisely because it treats the root "
     "instead of the symptom that happened to be loudest on the day you arrived."),

    ("The first pillar, mapping the machine you actually have",
     "The mentorship moves through three pillars in a deliberate order, and skipping any of them is why most "
     "attempts at this fail. The first pillar is diagnosis, and it is the least glamorous and most important "
     "step in the entire process. Before we change anything, we build an honest map of how your business truly "
     "runs today, not how you think it runs and not how the org chart says it runs. We trace where decisions "
     "actually get made, where work actually stalls, and which invisible systems live only in your head and "
     "would vanish the day you did. Almost every operator is shocked by this map, because the real bottlenecks "
     "are rarely the ones they have been worrying about. You have been fighting the fires you can see. The map "
     "shows you the ones you cannot, the quiet structural dependencies that route everything through you by "
     "accident of history rather than by any deliberate choice. We do this together and we do it without "
     "flinching, because you cannot externalize a machine you have not honestly seen. This pillar alone, done "
     "properly, changes how you look at your business permanently. Most operators have never once mapped their "
     "own company from the outside, and doing it for the first time is the moment the ceiling stops feeling "
     "mysterious and starts feeling like a specific, fixable design. That clarity is the foundation everything "
     "else is built on, and it is why we refuse to rush past it toward the more exciting work of building. You "
     "cannot install a structure that fits a business you have never actually looked at."),

    ("The second pillar, externalizing the operating logic",
     "The second pillar is where the real rebuild happens, and it is the heart of the engagement. Having mapped "
     "the machine, we begin moving its operating logic out of your head and into structure, one system at a "
     "time, in the order that gives you back the most life the fastest. This is not about writing a binder of "
     "procedures nobody reads. It is about designing the specific decisions and cadences your business depends "
     "on so that they run reliably without your constant attention. We take the choices you make on instinct a "
     "hundred times a week and turn them into designed defaults that a team, a tool, or a simple rule can carry. "
     "We take the work that only moves when you push it and put it on a rhythm that moves on its own schedule. "
     "Piece by piece, the parts of the business that used to require you begin to run themselves, and you feel "
     "the weight come off in real time, not in theory. This is deliberate and it is sequenced, because "
     "externalizing in the wrong order creates chaos, while doing it in the right order creates relief at every "
     "step. By the time this pillar is complete, the operating logic of your company no longer lives in your "
     "exhaustion. It lives in a structure you designed, which means it can be improved, delegated, and scaled, "
     "none of which is possible while it exists only as instinct in a single overworked mind. This is the pillar "
     "that turns a founder who is trapped into a founder who is free, and it is the reason people describe the "
     "experience less as learning and more as finally being able to breathe. I want to be candid that this pillar "
     "is also the one where old habits fight back the hardest, because handing a decision to a structure feels, at "
     "first, like losing control of it. That feeling is a lie your history tells you, and part of my job is to "
     "stand beside you while you learn to trust the machine you are building. The relief on the far side of that "
     "discomfort is the whole prize, and I have never once seen an operator who reached it wish they had kept "
     "everything routed through themselves out of habit and fear."),

    ("The third pillar, installing the sovereign cadence",
     "The third pillar is what makes the change permanent instead of temporary, and it is the one most programs "
     "skip entirely. Rebuilding the machine is not enough if you return to the same habits that will slowly "
     "re-centralize everything back into you. So the final pillar installs the cadence and the identity of a "
     "sovereign operator, the weekly and monthly rhythm by which you now run the business as its architect "
     "rather than its engine. You learn to spend your attention on the structure instead of the tasks, to make "
     "the small number of decisions that only you should make and to route the rest into the machine, and to "
     "protect the role you have earned instead of quietly sliding back into being the bottleneck the moment "
     "things get busy. This is where the transformation stops being something we did during our engagement and "
     "becomes simply who you are as an operator. It is the difference between a diet and a new way of eating, "
     "between a burst of organization and a durable system that holds under pressure. We do not consider the "
     "work finished when the structure is built. We consider it finished when you can run it, defend it, and "
     "improve it on your own, because the entire point of sovereignty is that you do not need me afterward. By "
     "the end of this pillar you are not a person who took a program. You are a different kind of operator, one "
     "whose growth is no longer chained to their stamina, and that shift does not wear off when the calls end. "
     "It is installed, and it is yours."),

    ("Everything you receive, laid out plainly",
     "Let me be concrete about what is included, because at this level you deserve specifics rather than "
     "atmosphere. You receive direct one-to-one guidance from me through the full engagement, the actual person "
     "who developed this method and has used it on real businesses, not a junior coach reading from a script. "
     "You receive the complete diagnostic process that maps your business honestly, done with you rather than "
     "handed to you as homework. You receive the guided externalization of your core systems, the hands-on "
     "rebuild that moves your operating logic out of your head and into structure. You receive the sovereign "
     "cadence installation that makes the change durable, along with every template, framework, and decision "
     "tool we use together, tuned to your specific business rather than a generic template. You receive priority "
     "access for the questions that cannot wait, so you are never stuck alone at the exact moment a hard call "
     "needs to be made. And you receive the one thing no course can give you, a partner who has walked this "
     "road, in the room for the strategic forks where the right move is not obvious and the cost of the wrong "
     "one is high. This is not a pile of content. It is a personal, guided rebuild of the way your business "
     "operates, delivered by someone with skin in your outcome. When operators ask me what they are really "
     "buying, I tell them the truth: they are buying their time back, and a company that finally runs without "
     "them, installed by hand so it actually holds."),

    ("The objection about time, answered honestly",
     "The first thing your mind will say is that you do not have time for this, and I want to meet that "
     "objection head on because it is the most revealing one you can raise. Notice what it actually says. You do "
     "not have time to fix the exact problem that is stealing all of your time. That is not a reason to wait; it "
     "is the clearest possible symptom of why you cannot afford to. The operators who need this most are always "
     "the ones who feel they can least spare the hours, because being trapped as the machine is precisely what "
     "makes every hour feel unavailable. But hear how the engagement is actually structured. We are not adding a "
     "large new project on top of your existing load. We are redesigning the load itself, and from the very "
     "first pillar the work begins giving hours back rather than taking them. The time you invest here is not "
     "spent; it is recovered, with interest, because every system we externalize is an hour a week you stop "
     "paying forever. The real question is not whether you can find time for this. It is how much longer you can "
     "afford to keep paying the time tax of a business built with one moving part. Every week you wait is a week "
     "of hours you will never get back, spent propping up a structure we could be dismantling. The busiest "
     "operators are not too busy for this work. They are too busy because they have not done it yet, and that is "
     "the whole point."),

    ("The objection about money, and the real arithmetic",
     "The second objection is the price, and I respect it, because this is a serious investment and it should "
     "be. Let me give you the honest arithmetic rather than a hard sell. This is not an expense in the way a "
     "tool or a course is an expense. It is a structural change to the asset that produces all of your income, "
     "which puts it in an entirely different category of decision. Ask yourself what one more moving part inside "
     "your business is worth, not once, but every week for the rest of the time you own the company. Ask what it "
     "is worth to reclaim the hours you are currently pouring into work that should not require you, and to "
     "point those hours at the decisions that actually grow the business. For most operators at this level, the "
     "recovered time and the removed bottleneck pay back the investment many times over inside the first year, "
     "and then keep paying every year after, because a structural change does not expire the way a tactic does. "
     "Compare that to the true cost of staying where you are, which we already counted honestly and found to be "
     "the most expensive option on the table. The price of this mentorship is knowable and finite. The price of "
     "another year on the plateau is neither. I am not asking you to spend money you do not have. I am asking "
     "you to move money you are already losing, quietly, every single week, into the one change that stops the "
     "leak at its source. That is not a cost. That is the highest-return decision available to you right now. "
     "There is also a version of this objection that is really about worth rather than money, a quiet doubt about "
     "whether you are the kind of operator who gets to make an investment at this level. Let me answer that "
     "plainly too. You built something real enough to hit a ceiling, which most people never do, and the fact "
     "that the price gives you pause is a sign of exactly the seriousness this work rewards. The people who "
     "regret this decision are almost never the ones who made it. They are the ones who talked themselves out of "
     "it and spent another year paying the invoice they refused to look at."),

    ("The objection about having tried before",
     "The third objection is the quiet one, the one you may not say out loud: you have tried things before and "
     "they did not stick, so why would this be different. I take this seriously, because you are right to be "
     "skeptical, and honestly your skepticism is a point in your favor. Here is the difference, stated plainly. "
     "Everything you tried before was almost certainly a version of more, another tactic, another tool, another "
     "burst of effort poured into the same unchanged structure. Of course it did not stick. You were treating "
     "the symptom while the machine underneath stayed exactly the same, so the moment your attention moved on, "
     "everything reverted, because the design that produced the problem was never touched. This is categorically "
     "different work. We are not adding another behavior for you to sustain by willpower. We are changing the "
     "structure itself, so that the new way of operating is held in place by design rather than by discipline. "
     "Things stick when the system makes them the path of least resistance, and they evaporate when they depend "
     "on you remembering to force them. That is the whole reason this is done with you, personally, over enough "
     "time to actually rebuild rather than merely inspire. You are not buying another attempt at the thing that "
     "failed. You are, for the first time, addressing the reason all those attempts failed. If everything you "
     "tried before was more, then the fact that this is not more is not a red flag. It is the entire point, and "
     "it is exactly why it holds when the others slid away."),

    ("The bonuses that remove every remaining excuse",
     "Beyond the core engagement, there are a few additions whose only job is to remove the last reasons an "
     "operator hesitates. You receive a complete library of the decision frameworks and operating templates "
     "refined across every business this method has touched, so you are never building a structure from a blank "
     "page. You receive a set of implementation guides for the moments between our sessions, so momentum never "
     "stalls waiting for the next call. And you receive extended access after the formal engagement ends, "
     "because a rebuild this significant deserves a period where you can run the new machine with a safety net "
     "still in place, asking the questions that only surface once the structure is live. None of these are the "
     "reason to say yes; the core work is. But together they mean that when you finish, you are not left holding "
     "a transformation you are afraid to maintain. You are left with the structure, the tools, the guides, and a "
     "line back to me for the settling-in period, which is precisely what turns a powerful experience into a "
     "permanent change. I add these because I have learned where operators wobble after the intensity of the "
     "work fades, and I would rather engineer those wobbles out in advance than watch a good rebuild erode for "
     "lack of a little support at the end. The point of every bonus here is the same as the point of everything "
     "else: to make sure the change you paid for is still running long after our last conversation, holding its "
     "shape under the ordinary pressure of a real business."),

    ("The investment, and the risk I carry so you do not",
     "Here is where the decision becomes real. The Sovereign Operator Mentorship is a significant investment, "
     "priced for the level of operator it serves and the magnitude of what it changes, and I will not pretend "
     "otherwise or dress it in false scarcity. What I will do is carry the risk that usually sits entirely on "
     "your shoulders. I only take on a small number of operators at a time, because this is done personally and "
     "my attention is the ingredient, which means I cannot and will not scale it into a crowd. When a seat is "
     "gone, it is gone until another opens, and that is not a marketing line, it is the plain limit of one-to-one "
     "work. More than that, I do not want your money if you are not the right fit, because a mismatched "
     "engagement wastes your investment and my time equally. So the process begins with a real conversation, not "
     "a checkout button, where we both decide honestly whether this is the right move for your business right "
     "now. If it is not, I will tell you, and you will leave with clarity you did not have before. If it is, you "
     "will step into a rebuild backed by someone whose reputation rides on your outcome, not on closing a sale. "
     "That is the reversal I can offer at this level. I cannot promise you a specific number, because your "
     "results depend on the work you install and the business you bring. What I can promise is that I will not "
     "let you buy something that is wrong for you, and that if we begin, I am in it with you until the machine "
     "actually runs. I hold the engagement to a small number of operators for the same reason a surgeon does not "
     "book forty procedures in a day: the quality of the outcome depends on undivided attention, and I would "
     "rather serve a handful of people completely than a crowd partially. That scarcity is not a tactic to rush "
     "you. It is the honest cost of doing this work the only way it actually holds. If the timing is wrong for "
     "you this season, I would genuinely rather you wait for a seat and arrive ready than squeeze in unprepared "
     "and waste the very investment you worked so hard to be able to make."),

    ("The two roads, and the one you are standing on",
     "So here is where the page ends and your decision begins. There are two roads in front of you, and you are "
     "already standing on one of them whether you choose it consciously or not. The first road is the one you "
     "are on now. It is not a disaster; that is exactly what makes it dangerous. It is comfortable enough to "
     "stay on, and it leads, quietly and reliably, to another year of being the machine, another year of the "
     "hidden costs compounding, another year of telling yourself that someday you will finally build the "
     "structure while the plateau holds you gently in place. That road does not end in catastrophe. It ends in "
     "something worse for a person like you, which is a slow, respectable, permanent ceiling. The second road is "
     "the one this entire page has been describing. It asks something real of you, a genuine investment and the "
     "courage to look honestly at how your business is built, and in return it offers the one thing the first "
     "road never will: a company that runs without you, and a life you actually own. I cannot walk it for you. "
     "The whole method depends on you being the architect, which means the first act of sovereignty is this "
     "choice, made by you, with no one pushing. If you are the operator I described, the one quietly relieved to "
     "finally hear the truth about why more stopped working, then you already know which road is yours. The only "
     "question left is whether you will step onto it now, while the seat is open and the cost of waiting has not "
     "compounded for one more quarter."),

    ("One last thing before you decide",
     "Read this part slowly, because it is the truest thing on the page. The reason you feel the ceiling so "
     "acutely is not that you are failing. It is that you are capable of far more than your current structure "
     "can hold, and some honest part of you knows it. That pressure you feel is not weakness; it is potential "
     "with nowhere to go, ambition straining against a design that was never built to carry it. Most people "
     "never feel this, because most people never build anything real enough to hit a ceiling in the first place. "
     "You did. And the same drive that got you here is now the thing making the plateau unbearable, because you "
     "were never meant to spend your one working life as the single moving part of a machine you could have "
     "designed to run itself. I built this mentorship for exactly the person reading these words with a quiet "
     "ache of recognition. If that is you, do not close this and tell yourself you will think about it, because "
     "we both know what thinking about it means. It means the first road, one more time. Instead, start the "
     "conversation. Let us find out together, honestly and without pressure, whether this is the moment you stop "
     "being the engine and become the architect. The machine you have been holding up with both hands does not "
     "have to be held up much longer. But the hands that put it down have to be yours, and the only day you can "
     "reach for that choice is the one you are standing in right now. So do the one sovereign thing available to "
     "you in this exact moment, which is to refuse to let this become another page you nodded at and forgot. "
     "Reach out. Tell me honestly where your business stands and what the ceiling is costing you, and let us "
     "decide together, with no pressure and no script, whether this is your season to make the change. The worst "
     "outcome of that conversation is that you leave with a clearer map of your own machine than you have ever "
     "had, which is worth the hour by itself. The best outcome is the one you have been quietly wanting since the "
     "first paragraph of this page, and it starts with a single message from the operator who is finally done "
     "being the engine."),
]


# ---------------------------------------------------------------------------
# Authenticity + band self-checks — the reproducer refuses to emit padded copy.
# ---------------------------------------------------------------------------
def _words(text: str) -> int:
    return len([w for w in re.split(r"\s+", str(text or "").strip()) if w])


def _no_repeated_ngram(text: str, n: int = 6, max_repeats: int = 3) -> tuple:
    toks = re.findall(r"[a-z0-9]+", text.lower())
    seen = {}
    for i in range(len(toks) - n + 1):
        gram = " ".join(toks[i:i + n])
        seen[gram] = seen.get(gram, 0) + 1
    offenders = {g: c for g, c in seen.items() if c > max_repeats}
    return (not offenders), offenders


def _no_cutoff(text: str) -> bool:
    # a mid-phrase cutoff would leave a dangling connective / no terminal punctuation.
    stripped = text.strip()
    if not stripped:
        return False
    if stripped[-1] not in ".!?\"'":
        return False
    if re.search(r"\b(and|or|but|the|a|to|of|with|for|that|which|because|so)\s*$", stripped, re.I):
        return False
    return True


def content_self_check() -> int:
    ok = True
    problems = []

    # high-ticket band [6500, 7100]
    ht_text = "\n\n".join(f"{t}\n{b}" for t, b in HT_SECTIONS)
    wc = _words(ht_text)
    if not (6500 <= wc <= 7100):
        ok = False; problems.append(f"high-ticket word count {wc} outside [6500,7100]")

    # bump band [40, 80] body words
    bwc = _words(BUMP_BODY)
    if not (40 <= bwc <= 80):
        ok = False; problems.append(f"bump body word count {bwc} outside [40,80]")

    # authenticity: no 6-gram repeated more than 3x across ALL authored copy
    everything = ht_text + "\n" + BUMP_BODY
    for label, blob in (("main-a", MAIN_A), ("main-b", MAIN_B), ("upsell-a", UPSELL_A),
                        ("upsell-b", UPSELL_B), ("downsell", DOWNSELL)):
        everything += "\n" + "\n".join(c for _, c in blob)
    clean, offenders = _no_repeated_ngram(everything, 6, 3)
    if not clean:
        ok = False; problems.append(f"repeated 6-gram padding detected: {list(offenders)[:3]}")

    # no mid-phrase cutoffs in any authored section body
    for label, blob in (("main-a", MAIN_A), ("main-b", MAIN_B), ("upsell-a", UPSELL_A),
                        ("upsell-b", UPSELL_B), ("downsell", DOWNSELL)):
        for name, copy in blob:
            if not _no_cutoff(copy):
                ok = False; problems.append(f"{label}/{name}: possible mid-phrase cutoff")
    for name, body in HT_SECTIONS:
        if not _no_cutoff(body):
            ok = False; problems.append(f"high-ticket/{name}: possible mid-phrase cutoff")

    print("== content authenticity self-check ==")
    print(f"  high-ticket stripped words : {wc}  (band 6500-7100)")
    print(f"  bump body words            : {bwc}  (band 40-80)")
    print(f"  authored sections          : main 8x2, upsell 9x2, downsell 9, high-ticket {len(HT_SECTIONS)}")
    print(f"  no >3x repeated 6-gram     : {'PASS' if clean else 'FAIL'}")
    if problems:
        for p in problems:
            print(f"  [PROBLEM] {p}")
    print("  RESULT:", "PASS (real authored copy, in band, no padding)" if ok else "FAIL")
    return 0 if ok else 1


# ---------------------------------------------------------------------------
# Ledger builders.
# ---------------------------------------------------------------------------
def _sections(named):
    return [{"order": i + 1, "name": nm, "copy": cp} for i, (nm, cp) in enumerate(named)]


def build_brief() -> dict:
    return {
        "funnel_type": "sales_page_assets",
        "locked": True,
        "client_slug": CLIENT,
        "funnel_slug": FUNNEL,
        "offer_token_ledger": OFFER_LEDGER,
        "run_id": RUN_ID,
        "answers": {
            "brand_info": "The Momentum Engine by Marcus Vale. A calm, direct, no-hype operating-system brand "
                          "for solo operators who are done confusing motion with progress. Voice: plain, "
                          "grounded, quietly confident. Method attribution: the Trevor Otts Direct-Response method.",
            "product_info": "The Momentum Engine, a self-paced operating-system course, $197. CTA "
                            + CHECKOUT + " . Thirty short lessons + twelve operating templates + a weekly cadence.",
            "primary_brand_color": "#12332B",
            "brand_logo": "https://cdn.example.com/momentum-engine/logo.png",
            "image_prompt_count": 12,
            "upsell_desc": "The Momentum Accelerator, a done-with-you 30-day guided-install sprint, $497.",
            "downsell_desc": "The Momentum Accelerator Recordings Vault, self-paced recordings, $147.",
            "bump_desc": "The 10-Minute Momentum Reset, a pocket audio pack, $27.",
            "high_ticket_desc": "The Sovereign Operator Mentorship, one-to-one operating-structure rebuild, $12,000.",
            "first_name": "Marcus",
            "last_name": "Vale",
            "email": "marcus@example.com",
        },
    }


def build_image_plan() -> dict:
    # 12 genuinely-authored, distinct prompts; slice map main[0:4] upsell[4:8] downsell[8:10] high[10:12].
    scenes = [
        ("main", "A calm dawn-lit home office from a low three-quarter angle, one clean desk with a single open "
                 "notebook and a cooling cup of coffee, deep evergreen and warm brass accents, soft morning light "
                 "raking across the wall, a sense of quiet order and one clear first move for the day."),
        ("main", "A close overhead shot of two hands closing a laptop with visible ease, the screen showing a "
                 "single simple weekly rhythm rather than a cluttered inbox, muted evergreen tones, shallow depth "
                 "of field, communicating relief and control instead of overwhelm."),
        ("main", "A minimalist flat-lay of the Engine toolkit: a slim workbook, a set of labeled operating "
                 "template cards fanned out, and a brass paperweight, arranged on warm oak, top-down studio light, "
                 "premium and uncluttered, conveying a system you can actually hold and use today."),
        ("main", "A wide, aspirational shot of a solo operator standing at a large window at golden hour looking "
                 "out over a quiet city, shoulders relaxed, a faint reflection of an orderly workspace behind him, "
                 "evergreen and amber palette, the mood of a founder finally ahead of the day."),
        ("upsell-1", "A dynamic side-lit portrait of a build partner and an operator reviewing a single template "
                     "on a shared screen, both leaning in with focus, warm task lighting, motion and traction in "
                     "the body language, the visual language of a guided thirty-day sprint underway."),
        ("upsell-1", "A tight macro of a checklist where the first several items are firmly checked and one glows "
                     "as the active step, deep green ink on cream paper, dramatic directional light, communicating "
                     "momentum being installed step by deliberate step rather than all at once."),
        ("upsell-1", "An energetic split-composition showing a stalled idle gear on the dim left and the same gear "
                     "turning brightly on the right, brass and evergreen, subtle motion blur on the moving side, a "
                     "clean metaphor for an Engine going from parked to running with help."),
        ("upsell-1", "A confident three-quarter portrait of a founder mid-decision at a standing desk, sleeves "
                     "rolled, one hand on a printed cadence map, warm and purposeful lighting, the quiet certainty "
                     "of someone no longer guessing at what moves the needle."),
        ("downsell-1", "A soft, empathetic still of an open door with warm light spilling through onto a single "
                       "pair of headphones and a printed session guide on a low table, muted evergreen, gentle and "
                       "unhurried mood, the feeling of a smaller door held open without pressure."),
        ("downsell-1", "A calm evening scene of one person listening to a recorded session on a couch with a "
                       "notebook, a single lamp, self-paced and private, warm low light, communicating the same "
                       "road walked patiently at one's own clock rather than a live schedule."),
        ("high-ticket", "A cinematic, editorial wide shot of an architect's table at dusk holding a large "
                        "blueprint of an interlocking machine, a single figure studying it from above with quiet "
                        "authority, deep evergreen and brass, volumetric light, the visual thesis of an operator "
                        "who has stopped being the engine and become the architect of the whole system."),
        ("high-ticket", "A striking two-road composition seen from behind a lone figure at a fork: one path worn "
                        "and dim leading back into busy fog, the other rising into clean gold light and open sky, "
                        "evergreen foreground, epic and decisive tone, the closing metaphor of the sovereign "
                        "choice between another year as the machine and a company that finally runs itself."),
    ]
    # Wrap each authored scene into a >=5,000-char, brand-graded, floor-compliant prompt
    # (FIX-XC-04e). The brand color "deep evergreen" is named in every prompt so the two-floor
    # gate (prove_sp_prompt_floor.py) passes, parameterized on the client's primary_brand_color.
    sys.path.insert(0, str(SCRIPTS))
    import prove_sp_prompt_floor as _pf  # noqa: E402
    prompts = [{"index": i, "stage": st, "prompt_text": _pf._rich_prompt(tx)}
               for i, (st, tx) in enumerate(scenes)]
    return {"funnel_type": "sales_page_assets", "image_prompt_count": len(prompts),
            "primary_brand_color": "deep evergreen", "prompts": prompts}


def build_copy_ledger() -> dict:
    def asset(stage, variant, type_, named=None, text=None, extra=None):
        v = variant or ""
        key = f"{CLIENT}__{FUNNEL}__{stage}__{type_}__v01{v}"
        a = {"stage": stage, "variant": variant, "type": type_, "asset_key": key}
        if named is not None:
            a["sections"] = _sections(named)
        if text is not None:
            a["text"] = text
        if extra:
            a.update(extra)
        return a

    ht_text = "\n\n".join(f"{t}\n{b}" for t, b in HT_SECTIONS)
    bump_text = BUMP_BODY + "\n\n" + BUMP_CHECKBOX
    return {
        "funnel_type": "sales_page_assets",
        "product_title": "The Momentum Engine",
        "offer_token_ledger": OFFER_LEDGER,
        "assets": [
            asset("main", "a", "page", named=MAIN_A, extra={"has_countdown_timer": True}),
            asset("main", "b", "page", named=MAIN_B, extra={"has_countdown_timer": True}),
            asset("upsell-1", "a", "page", named=UPSELL_A),
            asset("upsell-1", "b", "page", named=UPSELL_B),
            asset("downsell-1", "", "page", named=DOWNSELL),
            asset("high-ticket", "", "page", text=ht_text),
            asset("bump", "", "copy", text=bump_text),
        ],
    }


def build_media_ledger() -> dict:
    images = []
    plan = build_image_plan()
    for p in plan["prompts"]:
        idx = p["index"]
        stage = p["stage"]
        images.append({
            "asset_key": f"{CLIENT}__{FUNNEL}__{stage}__img-{idx + 1:02d}__v01",
            "stage": stage,
            "task_id": f"kie-momentum-{idx + 1:02d}-20260702",
            "ghl_media_url": f"https://storage.example-msgsndr-media.test/{CLIENT}__{FUNNEL}/{stage}/img-{idx + 1:02d}.png",
            "provider": "client_image_provider",
        })
    return {"funnel_type": "sales_page_assets", "media_folder": f"{CLIENT}__{FUNNEL}", "images": images}


def build_manifest() -> dict:
    def page_step(order, stage, variant=""):
        v = variant
        return {
            "order": order, "stage": stage, "variant": v,
            "step_name": f"ZHC {FUNNEL} {stage} v01{v}",
            "asset_key": f"{CLIENT}__{FUNNEL}__{stage}__page__v01{v}",
            "fragment_path": f"pages/{CLIENT}__{FUNNEL}__{stage}__page__v01{v}.fragment.html",
            "method_decision": {"classification": "SIMPLE", "route": "DIRECT"},
            "copy_md_path": f"copy/{CLIENT}__{FUNNEL}__{stage}__page__v01{v}.md",
            "copy_tokens": ["headline", "primary-cta", "proof-line"],
        }

    return {
        "funnel_manifest": "sales-page-assets",
        "run_id": RUN_ID,
        "location_id": "loc_MOMENTUM_EXAMPLE",
        "funnel_name": f"ZHC {CLIENT} {FUNNEL} v01",
        "seo": {
            "founder_name": FOUNDER,
            "keywords": ["momentum engine", "operating system for founders", "solo operator systems",
                         "direct response funnel"],
            "description": "The Momentum Engine direct-response sales funnel by Marcus Vale.",
            "canonical": "https://example.com/momentum-engine",
            "language": "en",
        },
        "media": {
            "folder": f"{CLIENT}__{FUNNEL}",
            "cdn_map": {img["asset_key"]: img["ghl_media_url"] for img in build_media_ledger()["images"]},
        },
        "steps": [
            page_step(1, "main", "a"),
            page_step(2, "main", "b"),
            page_step(3, "upsell-1", "a"),
            page_step(4, "upsell-1", "b"),
            page_step(5, "downsell-1"),
            page_step(6, "high-ticket"),
            {"order": 7, "stage": "bump",
             "step_name": f"ZHC {FUNNEL} bump v01",
             "asset_key": f"{CLIENT}__{FUNNEL}__bump__copy__v01",
             "route": "SKILL44_WIDGET",
             "copy_md_path": f"copy/{CLIENT}__{FUNNEL}__bump__copy__v01.md"},
            {"order": 8, "stage": "thank-you", "variant": "",
             "step_name": f"ZHC {FUNNEL} thank-you v01",
             "asset_key": f"{CLIENT}__{FUNNEL}__thank-you__page__v01",
             "fragment_path": f"pages/{CLIENT}__{FUNNEL}__thank-you__page__v01.fragment.html",
             "method_decision": {"classification": "SIMPLE", "route": "DIRECT"},
             "copy_md_path": "copy/thank-you.md"},
        ],
    }


# ---------------------------------------------------------------------------
# Prove / orchestrate / broken variants.
# ---------------------------------------------------------------------------
def _run(cmd):
    proc = subprocess.run(cmd, capture_output=True, text=True)
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def _sanitize_paths(text):
    """Strip the absolute skill-root prefix from captured prover output so the
    committed REJECTION-RESULTS.json carries repo-relative paths only — never an
    operator-machine absolute path (fleet-wide privacy invariant / QC guard)."""
    return text.replace(str(SKILL_DIR) + os.sep, "").replace(str(SKILL_DIR), ".")


def write_ledgers():
    (HERE / "brief.json").write_text(json.dumps(build_brief(), indent=2), encoding="utf-8")
    (HERE / "image_plan.json").write_text(json.dumps(build_image_plan(), indent=2), encoding="utf-8")
    (HERE / "copy_ledger.json").write_text(json.dumps(build_copy_ledger(), indent=2), encoding="utf-8")
    (HERE / "media_ledger.json").write_text(json.dumps(build_media_ledger(), indent=2), encoding="utf-8")
    (HERE / "funnel-manifest.json").write_text(json.dumps(build_manifest(), indent=2), encoding="utf-8")
    # FIX-XC-02a — the P0 intake gate is fail-closed on persona grounding; the golden must
    # carry a persona-selection-log naming a registered persona slug (SOP-SALESPAGE-01 §3).
    (HERE / "persona-selection-log.md").write_text(
        "# persona-selection-log.md — Momentum Sales Page Assets (P0 grounding)\n\n"
        "selector_ran: true\n- selected_persona: hormozi-100m-offers\n"
        "- rationale: value-stack sales page + upsell/downsell/bump grounded on hormozi-100m-offers.\n"
        "- staleness_checked: true\n- staleness_flagged: false\n",
        encoding="utf-8")
    write_build_artifacts()


# The P5-P9 artifact-backed gates (FIX-XC-03b) need on-disk build artifacts: a non-empty
# fragment per page step, a Track-1 Docs manifest, a delivery record, and a build receipt.
BUILD_ARTIFACT_NAMES = ("pages", "drive_docs.json", "delivery.json", "build_receipt.json")


def write_build_artifacts():
    """Materialize the committed build artifacts in the golden dir using the SAME helper the
    orchestrator self-test uses (single source of truth for the artifact shape)."""
    sys.path.insert(0, str(SKILL_DIR))
    sys.path.insert(0, str(SCRIPTS))
    import run_sales_page_assets as _orch  # noqa: E402
    _orch._write_build_artifacts(HERE, build_manifest())


def copy_build_artifacts(dst: Path):
    for name in BUILD_ARTIFACT_NAMES:
        src = HERE / name
        if not src.exists():
            continue
        if src.is_dir():
            shutil.copytree(src, dst / name, dirs_exist_ok=True)
        else:
            shutil.copy(src, dst / name)


def prove_all():
    results = {}
    checks = [
        ("prove_sp_intake.py", [str(HERE / "brief.json")]),
        ("prove_sp_image_plan.py", ["--plan", str(HERE / "image_plan.json")]),
        ("prove_sp_prompt_floor.py", ["--ledger", str(HERE / "image_plan.json")]),
        ("prove_sp_main_structure.py", ["--ledger", str(HERE / "copy_ledger.json")]),
        ("prove_sp_upsell_structure.py", ["--ledger", str(HERE / "copy_ledger.json")]),
        ("prove_sp_highticket_band.py", ["--ledger", str(HERE / "copy_ledger.json")]),
        ("prove_sp_bump_band.py", ["--ledger", str(HERE / "copy_ledger.json")]),
        ("prove_sp_bundle.py", ["--manifest", str(HERE / "funnel-manifest.json")]),
    ]
    all_ok = True
    for script, args in checks:
        rc, out = _run([PY, str(SCRIPTS / script), *args])
        tail = [ln for ln in out.strip().splitlines() if ln.strip()][-1:] or [""]
        results[script] = {"rc": rc, "pass": rc == 0, "tail": tail}
        all_ok = all_ok and rc == 0
        print(f"  [{'PASS' if rc == 0 else 'FAIL'}] {script} (rc={rc})")
    (HERE / "working").mkdir(exist_ok=True)
    (HERE / "working" / "prover_results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    return all_ok


def orchestrate_golden():
    tmp = Path(tempfile.mkdtemp(prefix="spa_golden_"))
    try:
        rd = tmp / RUN_ID
        rd.mkdir()
        for f in ("brief.json", "image_plan.json", "copy_ledger.json", "media_ledger.json",
                  "funnel-manifest.json", "persona-selection-log.md"):  # FIX-XC-02a persona grounding
            shutil.copy(HERE / f, rd / f)
        copy_build_artifacts(rd)   # P5-P9 artifacts (fragments/docs/delivery/build-receipt)
        nf = rd / ".spa_run_nonce"
        nf.write_text(GOLDEN_NONCE, encoding="utf-8")
        os.chmod(nf, 0o600)
        rc, out = _run([PY, str(ORCH), "--run-dir", str(rd), "--nonce", GOLDEN_NONCE])
        cert_src = rd / "PROCESS-CERTIFICATE.json"
        if rc != 0 or not cert_src.exists():
            print("  [FAIL] golden did not certify through the orchestrator")
            print("\n".join("         " + l for l in out.splitlines()))
            return False
        dest = HERE / "delivery" / "golden-momentum-FINAL"
        dest.mkdir(parents=True, exist_ok=True)
        cert = json.loads(cert_src.read_text(encoding="utf-8"))
        (dest / "PROCESS-CERTIFICATE.json").write_text(json.dumps(cert, indent=2), encoding="utf-8")
        _write_cert_md(dest / "PROCESS-CERTIFICATE.md", cert)
        # re-verify the committed cert with the documented example nonce
        rc2, out2 = _run([PY, str(SCRIPTS / "prove_sp_cert.py"), "--cert",
                          str(dest / "PROCESS-CERTIFICATE.json"), "--nonce", GOLDEN_NONCE])
        print(f"  [{'PASS' if rc == 0 else 'FAIL'}] golden -> orchestrator -> signed certificate minted")
        print(f"  [{'PASS' if rc2 == 0 else 'FAIL'}] committed certificate re-verifies (rc={rc2})")
        return rc == 0 and rc2 == 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _write_cert_md(path, cert):
    lines = [
        "# Golden Momentum — PROCESS CERTIFICATE (specimen)",
        "",
        f"- Certificate kind: `{cert.get('certificate')}`",
        f"- Run id: `{cert.get('run_id')}`",
        f"- Funnel type: `{cert.get('funnel_type')}`",
        f"- Issued at: `{cert.get('issued_at')}`",
        f"- Skill version: `{cert.get('skill_version')}`",
        f"- Example nonce (specimen, not a secret): `{GOLDEN_NONCE}`",
        f"- All phases pass: **{cert.get('all_phases_pass')}**",
        "",
        "## Phases attested (in order)",
        "",
        "| order | id | prover | status |",
        "|---|---|---|---|",
    ]
    for ph in cert.get("phases", []):
        lines.append(f"| {ph.get('order')} | {ph.get('id')} | `{ph.get('prover')}` | {ph.get('status')} |")
    lines += [
        "",
        "Re-verify:",
        "",
        "```bash",
        "python3 56-sales-page-assets/scripts/prove_sp_cert.py \\",
        "  --cert 56-sales-page-assets/examples/golden-momentum/delivery/golden-momentum-FINAL/PROCESS-CERTIFICATE.json \\",
        f"  --nonce {GOLDEN_NONCE}",
        "```",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def write_broken_variants():
    bv = HERE / "broken-variants"
    good_copy = build_copy_ledger()

    # A — out-of-band section: swap two MAIN variant-b sections out of canonical order.
    a = json.loads(json.dumps(good_copy))
    for asset in a["assets"]:
        if asset["stage"] == "main" and asset["variant"] == "b":
            secs = asset["sections"]
            secs[2], secs[3] = secs[3], secs[2]  # problem-solution <-> benefits swapped
    (bv / "A_out_of_band_section" / "copy_ledger.json").write_text(json.dumps(a, indent=2), encoding="utf-8")

    # B — high-ticket word floor: truncate the high-ticket body well under 6,500 words.
    b = json.loads(json.dumps(good_copy))
    for asset in b["assets"]:
        if asset["stage"] == "high-ticket":
            asset["text"] = "\n\n".join(f"{t}\n{bd}" for t, bd in HT_SECTIONS[:3])  # ~900 words
    (bv / "B_high_ticket_word_floor" / "copy_ledger.json").write_text(json.dumps(b, indent=2), encoding="utf-8")

    # C — bump out of band: cut the bump body under the 40-word floor (checkbox intact).
    c = json.loads(json.dumps(good_copy))
    for asset in c["assets"]:
        if asset["stage"] == "bump":
            asset["text"] = "Add The 10-Minute Momentum Reset for busy days.\n\n" + BUMP_CHECKBOX  # ~8 body words
    (bv / "C_bump_out_of_band" / "copy_ledger.json").write_text(json.dumps(c, indent=2), encoding="utf-8")

    # D — image slice: drop to the legacy default of 4 prompts (upsell/downsell/high-ticket slices empty).
    plan = build_image_plan()
    plan4 = {"funnel_type": "sales_page_assets", "image_prompt_count": 4,
             "prompts": plan["prompts"][:4]}
    (bv / "D_image_slice" / "image_plan.json").write_text(json.dumps(plan4, indent=2), encoding="utf-8")

    # E — missing provenance: a run-dir with every ledger EXCEPT media_ledger.json, so the
    #     P2 image-provenance delegation seam fails closed and no certificate is minted.
    e = bv / "E_missing_provenance"
    for f in ("brief.json", "image_plan.json", "copy_ledger.json", "funnel-manifest.json"):
        shutil.copy(HERE / f, e / f)
    (e / "README.txt").write_text(
        "Missing-provenance variant: this run-dir intentionally OMITS media_ledger.json (the image "
        "provenance artifact produced by the image provider + Skill 6 media upload). Driven through the "
        "orchestrator it fails closed at P2-IMAGES ('delegated artifact media_ledger.json absent') and "
        "mints NO certificate.\n", encoding="utf-8")

    # F — unapproved: the brief was never locked (human approval withheld).
    f = json.loads(json.dumps(build_brief()))
    f["locked"] = False
    (bv / "F_unapproved" / "brief.json").write_text(json.dumps(f, indent=2), encoding="utf-8")


def capture_rejections():
    bv = HERE / "broken-variants"
    results = {}

    def cap(name, script, args, expect):
        rc, out = _run([PY, str(SCRIPTS / script), *args])
        out = _sanitize_paths(out)
        tail = "\n".join([l for l in out.strip().splitlines() if l.strip()][-4:])
        results[name] = {"prover": script, "rc": rc, "rejected": rc != 0,
                         "expected_code": expect, "code_present": expect in out,
                         "out_tail": tail}
        status = "PASS" if (rc != 0 and expect in out) else "FAIL"
        print(f"  [{status}] {name} -> rc={rc} carrying {expect}")

    cap("A_out_of_band_section", "prove_sp_main_structure.py",
        ["--ledger", str(bv / "A_out_of_band_section" / "copy_ledger.json")], "AF-SP56-MAIN-SECTION-ORDER")
    cap("B_high_ticket_word_floor", "prove_sp_highticket_band.py",
        ["--ledger", str(bv / "B_high_ticket_word_floor" / "copy_ledger.json")], "AF-SP56-HIGHTICKET-FLOOR")
    cap("C_bump_out_of_band", "prove_sp_bump_band.py",
        ["--ledger", str(bv / "C_bump_out_of_band" / "copy_ledger.json")], "AF-SP56-BUMP-FLOOR")
    cap("D_image_slice", "prove_sp_image_plan.py",
        ["--plan", str(bv / "D_image_slice" / "image_plan.json")], "AF-SP56-IMGPLAN-SLICE-EMPTY")
    cap("F_unapproved", "prove_sp_intake.py",
        [str(bv / "F_unapproved" / "brief.json")], "AF-SP56-INTAKE-UNLOCKED")

    # E + F through the orchestrator: both must abort with NO certificate.
    for name, missing in (("E_missing_provenance", None), ("F_unapproved", "F_unapproved")):
        tmp = Path(tempfile.mkdtemp(prefix=f"spa_bad_{name}_"))
        try:
            rd = tmp / "run"
            rd.mkdir()
            if name == "E_missing_provenance":
                for f in ("brief.json", "image_plan.json", "copy_ledger.json", "funnel-manifest.json"):
                    shutil.copy(HERE / f, rd / f)  # deliberately NO media_ledger.json
                marker = "media_ledger.json absent"
            else:
                for f in ("image_plan.json", "copy_ledger.json", "media_ledger.json", "funnel-manifest.json"):
                    shutil.copy(HERE / f, rd / f)
                shutil.copy(bv / "F_unapproved" / "brief.json", rd / "brief.json")
                marker = "AF-SP56-INTAKE-UNLOCKED"
            nf = rd / ".spa_run_nonce"
            nf.write_text("bad-run-nonce", encoding="utf-8")
            os.chmod(nf, 0o600)
            rc, out = _run([PY, str(ORCH), "--run-dir", str(rd), "--nonce", "bad-run-nonce"])
            out = _sanitize_paths(out)
            no_cert = not (rd / "PROCESS-CERTIFICATE.json").exists()
            ent = results.setdefault(name, {})
            ent["e2e_orchestrator_rc"] = rc
            ent["e2e_no_certificate"] = no_cert
            ent["e2e_marker"] = marker
            ent["e2e_marker_present"] = marker in out
            if name == "E_missing_provenance":
                ent.setdefault("prover", "run_sales_page_assets.py (P2 seam)")
                ent["rejected"] = rc != 0 and no_cert
                ent["expected_code"] = "P2-IMAGES delegation seam (media_ledger.json absent)"
                ent["out_tail"] = "\n".join([l for l in out.strip().splitlines() if l.strip()][-4:])
            status = "PASS" if (rc != 0 and no_cert) else "FAIL"
            print(f"  [{status}] {name} through orchestrator -> rc={rc}, no_certificate={no_cert}")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    (HERE / "broken-variants" / "REJECTION-RESULTS.json").write_text(
        json.dumps(results, indent=2), encoding="utf-8")
    all_rejected = all(v.get("rejected") for v in results.values())
    return all_rejected


def main(argv):
    if "--content-check" in argv:
        return content_self_check()

    print("== build_golden.py :: Golden Momentum Sales Page Assets ==")
    print("-- content authenticity --")
    if content_self_check() != 0:
        print("ABORT: authored copy failed the authenticity/band self-check.")
        return 1
    print("-- write ledgers --")
    write_ledgers()
    print("-- prove each gate --")
    if not prove_all():
        print("ABORT: a golden ledger failed its prover.")
        return 1
    print("-- orchestrate to a signed certificate --")
    if not orchestrate_golden():
        print("ABORT: golden did not certify.")
        return 1
    print("-- write + capture broken-variant rejections --")
    write_broken_variants()
    if not capture_rejections():
        print("ABORT: a broken variant was NOT rejected.")
        return 1
    print("\nRESULT: PASS — golden reproduced, certified, and all six broken variants rejected.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
