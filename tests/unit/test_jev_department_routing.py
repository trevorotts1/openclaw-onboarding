#!/usr/bin/env python3
"""JEV-506: the bridge's department picker, measured on a labeled set.

The JEV bridge (shared-utils/decision-engine.py) is the OFFLINE fallback
department picker: when the CEO AI has already decided a message is a task,
the bridge only picks WHICH department gets the card (General Task when
nothing fits). The independent review found ~1 in 5 confident picks wrong,
e.g. "Show me a draft of the welcome email" -> Podcast/Audio. This file is
the fixed yardstick for that picker.

Each row: (owner task message, acceptable departments, forbidden departments).
Departments are the standard floor (23-ai-workforce-blueprint/
department-naming-map.json `mandatory`). An empty acceptable set means no
floor department fits (HR-style work) and only General Task is right.

Gates (on the full set, standard-floor catalog, no request.departments):
  * accuracy  -- pick is an acceptable department OR general-task: >= 90%
  * coverage  -- rows WITH an acceptable department that actually land in one
                 (so "route everything to General Task" cannot pass): >= 75%
  * no row lands in one of its forbidden departments (the review misroutes)

Intent classification is NOT exercised here; it is frozen (review 2026-09,
decision (e)). Only `route.department` is measured.

Must FAIL on origin/main v25.2.19 and PASS on branch jev506/department-routing.

Run: pytest tests/unit/test_jev_department_routing.py -q
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent.parent
_BRIDGE = _REPO / "shared-utils" / "decision-engine.py"

ACCURACY_GATE = 0.90
COVERAGE_GATE = 0.75

MK, SA, BF, CS = "marketing", "sales", "billing-finance", "customer-support"
WD, FU, AD, GR = "web-development", "funnels", "app-development", "graphics"
VI, AU, RE, CO = "video", "audio", "research", "communications"
CRM, OM, LE, SM = "crm", "openclaw-maintenance", "legal", "social-media"
PA, PAS, PAO = "paid-advertisement", "personal-assistant", "project-architecture-office"
BU, HE, QC = "bugs", "healer", "quality-control"

# (message, acceptable departments, forbidden departments)
LABELED_SET: list[tuple[str, tuple, tuple]] = [
    # --- review misroutes (section 3.3), verbatim ---
    ("Show me a draft of the welcome email", (MK, CO, CRM), (AU,)),
    ("Walk the new VA through onboarding", (), (BF,)),
    ("Summarize this week's sales calls", (SA,), (FU,)),
    ("Let the team know about the new policy", (CO,), (LE,)),
    # --- marketing ---
    ("Write a lead magnet for our coaching program", (MK,), ()),
    ("Plan next month's email campaign for the spring sale", (MK, CRM), ()),
    ("Come up with a content calendar for the blog", (MK, SM), ()),
    ("Rewrite the headline on our sales page so it converts better", (MK, WD, FU), ()),
    ("Draft a newsletter announcing our new course", (MK, CO, CRM), ()),
    ("Create a referral program for past clients", (MK, SA), ()),
    ("Put together a brand positioning statement", (MK, CO), ()),
    ("Plan the launch strategy for the webinar", (MK,), ()),
    ("Find some influencers we could partner with", (MK, SM), ()),
    ("Write three subject lines for Friday's promo email", (MK, CRM), ()),
    ("Map out the customer journey from first click to purchase", (MK, SA), ()),
    # --- sales ---
    ("Follow up with the leads from yesterday's webinar", (SA, CRM), ()),
    ("Put together a proposal for the Johnson account", (SA,), ()),
    ("Book discovery calls with the five new prospects", (SA, PAS), ()),
    ("Write a closing script for high-ticket calls", (SA,), ()),
    ("Update the pipeline with this week's deals", (SA, CRM), ()),
    ("Send a quote to the dentist office that asked about pricing", (SA,), ()),
    ("Build a follow-up sequence for leads who went cold", (SA, CRM), ()),
    ("Prep me for tomorrow's call with the prospect from Atlanta", (SA, PAS), ()),
    ("Draft an outreach message for cold prospects on LinkedIn", (SA, SM), ()),
    # --- billing & finance ---
    ("Pay the electric bill", (BF, PAS), ()),
    ("Send the invoice to the client", (BF,), ()),
    ("Refund the customer who was charged twice", (BF, CS), ()),
    ("Reconcile last month's expenses", (BF,), ()),
    ("Run payroll for the team this Friday", (BF,), ()),
    ("Chase the unpaid invoices from March", (BF,), ()),
    ("Set up a payment plan for the Smith family", (BF,), ()),
    ("Give me a profit and loss report for the quarter", (BF, RE), ()),
    ("Cancel the software subscription we don't use anymore", (BF, PAS), ()),
    ("Track our monthly revenue in a spreadsheet", (BF,), ()),
    ("Prepare the receipts for my accountant for taxes", (BF,), ()),
    # --- customer support ---
    ("Reply to the customer who can't log into the course", (CS,), ()),
    ("Help the client who is upset about the late delivery", (CS,), ()),
    ("Write a help article on how to reset a password", (CS,), ()),
    ("Answer the support tickets that came in overnight", (CS,), ()),
    ("Check in with members who haven't logged in for a month", (CS,), ()),
    ("Tell the customer their order is on the way", (CS, CO), ()),
    ("Handle the complaint from the woman in Ohio", (CS,), ()),
    ("Set up a live chat reply for common questions", (CS,), ()),
    ("Onboard the new client who signed up today", (CS, SA), ()),
    ("Build an FAQ for our membership", (CS, WD), ()),
    # --- web development ---
    ("Change the price on the coaching page to $997", (WD, FU), ()),
    ("Fix the broken link in the website footer", (WD, BU), ()),
    ("Build a landing page for the new book", (WD, FU), ()),
    ("Improve our SEO for local search", (WD, MK), ()),
    ("Update the homepage banner with the new offer", (WD, GR), ()),
    ("Make the website load faster on phones", (WD,), ()),
    ("Add a contact form to the about page", (WD,), ()),
    ("Set up a WordPress blog for the business", (WD,), ()),
    ("Add the new testimonials to the site", (WD, MK), ()),
    # --- funnels ---
    ("Build a GHL funnel for the free masterclass", (FU, WD), ()),
    ("Check that the checkout step of the funnel works", (FU, WD, QC), ()),
    ("Clone the webinar funnel for the new product", (FU, WD), ()),
    ("Change the webinar date to the 15th on the registration funnel", (FU, WD, MK), ()),
    # --- app development ---
    ("Build a mobile app for our members", (AD,), ()),
    ("Add push notifications to the iPhone app", (AD,), ()),
    ("Fix the crash in the Android app", (AD, BU), ()),
    ("Set up an API so the app can pull client data", (AD,), ()),
    ("Get the app listed in the App Store", (AD,), ()),
    ("Design the login screen for the app", (AD, GR), ()),
    # --- graphics ---
    ("Design a logo for the new podcast", (GR,), ()),
    ("Make a flyer for Saturday's event", (GR,), ()),
    ("Create slides for my keynote", (GR,), ()),
    ("Design a thumbnail for the new YouTube video", (GR, VI), ()),
    ("Make an infographic about our results", (GR,), ()),
    ("Create ad images for the Facebook campaign", (GR, PA), ()),
    ("Design a book cover for my new book", (GR,), ()),
    ("Make some Instagram graphics for next week", (GR, SM), ()),
    # --- video ---
    ("Edit the interview video and add captions", (VI,), ()),
    ("Make a short reel from yesterday's livestream", (VI, SM), ()),
    ("Script and produce a sales video for the offer", (VI, MK), ()),
    ("Optimize the titles on our YouTube videos", (VI, SM), ()),
    ("Create an AI video for the product launch", (VI,), ()),
    ("Set up the livestream for Thursday's class", (VI,), ()),
    # --- audio ---
    ("Edit this week's podcast episode", (AU,), ()),
    ("Record a voiceover for the promo", (AU,), ()),
    ("Transcribe the recording of the board meeting", (AU, PAS), ()),
    ("Clean up the sound on the podcast intro", (AU,), ()),
    ("Produce the audiobook version of my book", (AU,), ()),
    ("Book a guest for next week's podcast", (AU, PAS), ()),
    # --- research ---
    ("Research our top three competitors", (RE,), ()),
    ("Find out what the market for online coaching looks like", (RE,), ()),
    ("Survey our customers about the new program", (RE, CS), ()),
    ("Analyze the data from last quarter's campaign", (RE, MK), ()),
    ("Look into industry trends for home care agencies", (RE,), ()),
    ("Build a customer persona for our ideal buyer", (RE, MK), ()),
    # --- communications ---
    ("Write a press release about our new location", (CO,), ()),
    ("Draft talking points for my radio interview", (CO,), ()),
    ("Announce the price change to our members", (CO, CS, MK), ()),
    ("Write an update for our investors", (CO,), ()),
    ("Pitch our story to local news outlets", (CO,), ()),
    ("Prepare a statement about the data breach", (CO, LE), ()),
    ("Write a speech for the awards dinner", (CO, AU), ()),
    # --- CRM ---
    ("Tag everyone who bought the course in the CRM", (CRM,), ()),
    ("Set up an automation that texts new leads", (CRM,), ()),
    ("Clean up duplicate contacts in the CRM", (CRM,), ()),
    ("Build a workflow that emails people after they book", (CRM,), ()),
    ("Move the leads from the old pipeline stage to the new one", (CRM, SA), ()),
    ("Fix our email deliverability so we stop landing in spam", (CRM,), ()),
    # --- OpenClaw maintenance ---
    ("Back up the AI system tonight", (OM,), ()),
    ("Check why the agents are running slow", (OM,), ()),
    ("Update OpenClaw to the latest version", (OM,), ()),
    ("Rotate the API keys for the assistant", (OM,), ()),
    ("Reduce how many tokens the agents are burning", (OM,), ()),
    ("Connect the new MCP server to the system", (OM,), ()),
    # --- legal ---
    ("Review the new vendor contract", (LE,), ()),
    ("Draft a non-disclosure agreement for the contractor", (LE,), ()),
    ("Make sure our website privacy policy is compliant", (LE,), ()),
    ("Check if we need a license to sell in California", (LE,), ()),
    ("Register a trademark for our brand name", (LE,), ()),
    # --- social media ---
    ("Post the event photos on Instagram", (SM,), ()),
    ("Reply to the comments on yesterday's Facebook post", (SM,), ()),
    ("Schedule LinkedIn posts for the week", (SM,), ()),
    ("Grow our TikTok following", (SM,), ()),
    ("Moderate the Discord community", (SM,), ()),
    # --- paid advertisement ---
    ("Launch a Facebook ad for the webinar", (PA,), ()),
    ("Lower our cost per lead on Google Ads", (PA,), ()),
    ("Set up retargeting ads for people who visited the site", (PA,), ()),
    ("Test two versions of the YouTube ad", (PA, VI), ()),
    ("Increase the ad budget for the spring promo", (PA,), ()),
    # --- personal assistant ---
    ("Book my flight to Dallas for next Tuesday", (PAS,), ()),
    ("Clear my calendar on Friday afternoon", (PAS,), ()),
    ("Clean up my inbox", (PAS,), ()),
    ("Remind me to call my mother on Sunday", (PAS,), ()),
    ("Make a dinner reservation for Saturday night", (PAS,), ()),
    ("Give me a morning briefing every day at 7", (PAS,), ()),
    ("Reschedule my dentist appointment", (PAS,), ()),
    # --- project architecture / bugs / healer / quality control ---
    ("Write a project plan for the new client portal", (PAO, AD, WD), ()),
    ("Create a PRD for the membership app", (PAO, AD), ()),
    ("Log a bug: the checkout button does nothing", (BU, WD, FU), ()),
    ("Track the error that keeps showing on the dashboard", (BU, OM), ()),
    ("Find the root cause of why the reminders keep failing", (HE, BU, OM), ()),
    ("Audit the SOPs in the sales department", (QC, SA), ()),
    ("Quality check the new onboarding procedure", (QC,), ()),
    # --- nothing on the floor fits: General Task only ---
    ("Hire a new virtual assistant", (), (BF,)),
    ("Order new office chairs", (PAS,), ()),
    ("Find a cleaning service for the office", (PAS,), ()),
    ("Write a job description for a part-time bookkeeper", (), ()),
    ("Plan the staff holiday party", (PAS,), ()),
    # --- second batch, written AFTER the first tuning pass and scored
    # before any change it informed: 82.5% accuracy / 57.9% coverage on this
    # batch alone (origin/main: 50.0% / 42.1%). One generic-scoring pass
    # (one-liner prose and role titles down-weighted, prose filler words
    # made generic) then took it to 90.0% / 71.1%; no row-specific tuning.
    ("Draft the copy for our spring sale email blast", (MK, CRM), ()),
    ("Brainstorm a name for the new mentorship offer", (MK,), ()),
    ("Call back the lady who asked about our group program", (SA, CS), ()),
    ("Close the deal with the gym owner before Friday", (SA,), ()),
    ("Send a payment reminder to clients who are late", (BF, CRM), ()),
    ("Figure out how much we spent on software this year", (BF,), ()),
    ("Issue a credit to the customer for the missed session", (BF, CS), ()),
    ("Respond to the angry review on Google", (CS, SM), ()),
    ("Help the member who can't find the course videos", (CS,), ()),
    ("Put a countdown timer on the sales page", (WD, FU), ()),
    ("Our site is down, get it back up", (WD, OM), ()),
    ("Hook up the order form to the new product", (FU, WD), ()),
    ("Add dark mode to the app", (AD,), ()),
    ("Make a banner image for the Facebook group", (GR, SM), ()),
    ("Design new business cards", (GR,), ()),
    ("Cut a 30 second teaser from the webinar recording", (VI, AU), ()),
    ("Add subtitles to the training video", (VI,), ()),
    ("Mix the intro music for the podcast", (AU,), ()),
    ("Pull together what our competitors charge", (RE, SA), ()),
    ("Dig into why our open rates dropped", (RE, CRM, MK), ()),
    ("Tell our members about the holiday schedule", (CO, CS), ()),
    ("Write a LinkedIn announcement about our new hire", (CO, SM), ()),
    ("Send a text blast to everyone tagged VIP", (CRM,), ()),
    ("Stop the welcome sequence from sending twice", (CRM,), ()),
    ("Restart the assistant, it stopped replying", (OM,), ()),
    ("Switch the agents to a cheaper model", (OM,), ()),
    ("Look over the lease before I sign it", (LE,), ()),
    ("Make sure our emails follow the spam laws", (LE, CRM), ()),
    ("Share our client win on Facebook and Instagram", (SM,), ()),
    ("Answer the DMs on Instagram", (SM, CS), ()),
    ("Pause the Google ads over the holidays", (PA,), ()),
    ("Find me a hotel in Chicago for the conference", (PAS,), ()),
    ("Move my 3pm meeting to Thursday", (PAS,), ()),
    ("Set up a new hire checklist for employees", (), ()),
    ("Put together interview questions for the office manager role", (), ()),
    ("Figure out why the nightly backup keeps failing", (HE, OM, BU), ()),
    ("Review every department's procedures for gaps", (QC,), ()),
    ("Scope out the requirements for the booking portal", (PAO, WD, AD), ()),
    ("File a bug for the broken signup button", (BU, WD, FU), ()),
    ("Create a slide deck for the investor meeting", (GR, CO), ()),
]


def _load_bridge():
    spec = importlib.util.spec_from_file_location("jev506_bridge_under_test", _BRIDGE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _pick_all(bridge) -> list[tuple[str, tuple, tuple, str]]:
    catalog = bridge._standard_floor_catalog()
    return [
        (msg, ok, bad, bridge._resolve_route_department(msg, None, catalog)[0])
        for msg, ok, bad in LABELED_SET
    ]


def _wire_route(message: str) -> dict:
    req = {
        "schemaVersion": "1.1.0",
        "configRevision": "cfgrev-jev506",
        "taskId": "task-jev506",
        "taskDescription": message,
    }
    result = subprocess.run(
        [sys.executable, str(_BRIDGE), "--evaluate"],
        input=json.dumps(req),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, f"stderr={result.stderr!r}"
    return json.loads(result.stdout)["route"]


class LabeledSetShape(unittest.TestCase):
    def test_set_is_big_enough_and_uses_real_floor_slugs(self):
        self.assertGreaterEqual(len(LABELED_SET), 120)
        floor = json.loads(
            (_REPO / "23-ai-workforce-blueprint" / "department-naming-map.json").read_text(
                encoding="utf-8"
            )
        )["mandatory"]
        for msg, ok, bad in LABELED_SET:
            for slug in ok + bad:
                self.assertIn(slug, floor, msg=msg)
        self.assertEqual(len({m for m, _, _ in LABELED_SET}), len(LABELED_SET))


class DepartmentPickerGates(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.results = _pick_all(_load_bridge())

    def test_accuracy_acceptable_or_general_task_at_least_90pct(self):
        misses = [
            (m, got) for m, ok, _, got in self.results if got not in ok and got != "general-task"
        ]
        accuracy = 1 - len(misses) / len(self.results)
        self.assertGreaterEqual(
            accuracy, ACCURACY_GATE, msg=f"accuracy {accuracy:.3f}; wrong picks: {misses}"
        )

    def test_coverage_not_everything_dumped_on_general_task(self):
        labeled = [(m, ok, got) for m, ok, _, got in self.results if ok]
        hits = sum(1 for _, ok, got in labeled if got in ok)
        coverage = hits / len(labeled)
        self.assertGreaterEqual(coverage, COVERAGE_GATE, msg=f"coverage {coverage:.3f}")

    def test_no_forbidden_department(self):
        bad = [(m, got) for m, _, forbidden, got in self.results if got in forbidden]
        self.assertEqual(bad, [])


class ReviewMisroutesOnTheWire(unittest.TestCase):
    """The four review misroutes, through the real --evaluate wire."""

    def test_review_examples(self):
        for message, ok, forbidden in LABELED_SET[:4]:
            route = _wire_route(message)
            self.assertEqual(route["action"], "route", msg=message)
            self.assertEqual(route["catalog"], "standard-floor", msg=message)
            self.assertNotIn(route["department"], forbidden, msg=message)
            self.assertIn(route["department"], ok + ("general-task",), msg=message)


class RequestCatalogStillWins(unittest.TestCase):
    """A caller catalog whose slugs match the floor gets the same domain
    knowledge; a caller-only department is still ranked on its own text."""

    def test_request_catalog_routes(self):
        bridge = _load_bridge()
        catalog = [
            {"slug": "marketing", "text": "Marketing"},
            {"slug": "sales", "text": "Sales"},
            {"slug": "podcast", "text": "Podcast show production and episodes"},
            {"slug": "legal", "text": "Legal"},
        ]
        cases = [
            ("Summarize this week's sales calls", "sales"),
            ("Edit this week's podcast episode", "podcast"),
            ("Review the new vendor contract", "legal"),
        ]
        for message, expected in cases:
            self.assertEqual(
                bridge._resolve_route_department(message, None, catalog)[0], expected, msg=message
            )
        pick = bridge._resolve_route_department("Show me a draft of the welcome email", None, catalog)
        self.assertNotEqual(pick[0], "podcast")

    def test_people_work_goes_to_a_real_hr_department_when_the_caller_has_one(self):
        bridge = _load_bridge()
        floor = bridge._standard_floor_catalog()
        self.assertEqual(
            bridge._resolve_route_department("Hire a new virtual assistant", None, floor)[0],
            "general-task",
        )
        message = "Screen the applicants for the receptionist job"
        self.assertEqual(bridge._resolve_route_department(message, None, floor)[0], "general-task")
        catalog = floor + [
            {"slug": "human-resources", "text": "Human Resources hiring recruiting applicants jobs"}
        ]
        self.assertEqual(
            bridge._resolve_route_department(message, None, catalog)[0], "human-resources"
        )


if __name__ == "__main__":
    unittest.main()
