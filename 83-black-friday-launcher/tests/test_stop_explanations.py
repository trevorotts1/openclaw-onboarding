"""Every stop the client hears about explains itself, in four plain parts, and is never a dead end.

Owner order (2026-11-20): when a rule or a problem stops the work, the client is told what happened (with
the real numbers), why the rule exists, what will fix it, and two to four numbered choices, one of them work
the agent does. No reason code, file path or stack trace ever reaches the client.

The INVENTORY guard: every stop code written in this skill's code (launcher_core/, routes/ and the shared
answers reader the launcher calls), every picture-stage hold, and every picture review code must have a row in
references/stop-explanations.json. A new stop without its explanation fails here.

Offline, stdlib only, nothing spent: python3 -m unittest tests/test_stop_explanations.py
"""

from __future__ import annotations

import io
import re
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = SKILL_ROOT.parent
sys.path.insert(0, str(SKILL_ROOT))

from launcher_core import (capability_check, cli, image_stages, linked_delivery,  # noqa: E402
                           stop_explain)

TABLE = stop_explain.table()
CODE = re.compile(r"\bAF-[A-Z0-9]+(?:-[A-Z0-9]+)*\b")
PATHLIKE = re.compile(r"/|\\|\.py\b|\.json\b|\.md\b")
TRACE = re.compile(r"Traceback|File \"|line \d+, in ")
PLACEHOLDER = re.compile(r"\{[a-z_]+\}")

# What the client must never read in a stop message (the inside words of this skill, from SKILL.md's list).
INSIDE_WORDS = ("intake", "manifest", "dispatch", "schema", "receipt", "contract", "gate", "python",
                "dependency", "jsonschema", "hash", "adapter", "entitlement", "preflight")

def code_inventory():
    """Every stop code the launcher can raise or report, read from its own source."""
    literal = re.compile(r"""f?["'](AF-[A-Z0-9]+(?:-[A-Z0-9]+)*)(?=["':\s])""")
    const = re.compile(r"""^(\w*CODE\w*)\s*=\s*["'](AF-[A-Z0-9-]+)["']""", re.M)
    joined = re.compile(r"""f["']\{(\w*CODE\w*)\}-([A-Z0-9]+(?:-[A-Z0-9]+)*)""")
    files = sorted(list((SKILL_ROOT / "launcher_core").rglob("*.py")) + list((SKILL_ROOT / "routes").glob("*.py")))
    shared = REPO_ROOT / "shared-utils" / "client_intake" / "launcher_intake.py"
    if shared.is_file():  # the answers reader the dispatch step calls (absent in a vendored copy)
        files.append(shared)
    found = set()
    for path in files:
        text = path.read_text(encoding="utf-8")
        found |= set(literal.findall(text))
        consts = dict(const.findall(text))
        found |= {f"{consts[name]}-{tail}" for name, tail in joined.findall(text) if name in consts}
    return found

def hold_inventory():
    """Every picture-stage status a page can be left in that is not complete."""
    text = (SKILL_ROOT / "launcher_core" / "image_stages.py").read_text(encoding="utf-8")
    statuses = set(re.findall(r'Stop\("([a-z_]+)"', text)) | set(re.findall(r'status="([a-z_]+)"', text)) \
        | set(re.findall(r'"status": "([a-z_]+)"', text))
    return {f"image_stage:{s}" for s in statuses if s not in ("complete", "ready")}

def picture_review_codes():
    """AF-G1..AF-G8, from Skill 71's own stage contract (absent in a vendored copy)."""
    path = REPO_ROOT / "71-blackceo-signature-page" / "references" / "stage-contract.json"
    if not path.is_file():
        return set()
    import json
    return {row["code"] for row in json.loads(path.read_text(encoding="utf-8"))["graphics_autofails"]}

def clean(testcase, text, where):
    testcase.assertFalse(CODE.search(text), f"{where}: a reason code reaches the client: {text!r}")
    testcase.assertFalse(PATHLIKE.search(text), f"{where}: a file path reaches the client: {text!r}")
    testcase.assertFalse(TRACE.search(text), f"{where}: a stack trace reaches the client: {text!r}")
    testcase.assertFalse(PLACEHOLDER.search(text), f"{where}: an unfilled placeholder: {text!r}")
    lowered = text.lower()
    for word in INSIDE_WORDS:
        testcase.assertNotRegex(lowered, rf"\b{word}", f"{where}: inside word {word!r}: {text!r}")

class EveryStopHasItsExplanation(unittest.TestCase):
    def test_every_stop_in_the_code_has_a_table_row(self):
        inventory = code_inventory() | hold_inventory() | picture_review_codes()
        self.assertGreater(len(inventory), 200, "the inventory scan found too few stops; the scan is broken")
        missing = sorted(c for c in inventory if c not in TABLE["codes"])
        self.assertEqual(missing, [], "a client-facing stop shipped without its explanation: add a row to "
                                      "references/stop-explanations.json")

    def test_the_inventory_scan_sees_what_it_is_for(self):  # control: the guard is not always green
        self.assertIn("AF-LAUNCH-IMAGE-PLAN-CAP", code_inventory())
        self.assertIn("AF-LAUNCH-PRODUCE-80", code_inventory())  # joined from CODE = "AF-LAUNCH-PRODUCE"
        self.assertIn("image_stage:awaiting_layout_proof_approval", hold_inventory())

    def test_every_row_names_a_real_family(self):
        bad = {code: row.get("family") for code, row in TABLE["codes"].items()
               if row.get("family") not in TABLE["families"]}
        self.assertEqual(bad, {})

    def test_every_family_and_override_has_four_parts_and_two_to_four_choices(self):
        def check(parts, where):
            for key in ("what_happened", "why", "fix"):
                self.assertTrue(isinstance(parts.get(key), str) and parts[key].strip(), f"{where}: {key}")
            choices = parts.get("choices")
            self.assertTrue(isinstance(choices, list) and 2 <= len(choices) <= 4, f"{where}: choices")
            self.assertTrue(any(c.startswith("I ") for c in choices), f"{where}: no choice the agent does")
        for name, family in TABLE["families"].items():
            check(family, f"family {name}")
            for v in family.get("variants") or []:
                check({**family, **v}, f"family {name} variant {v['match']}")
        for code, row in TABLE["codes"].items():
            merged = {**TABLE["families"][row["family"]], **row}
            check(merged, code)
            for v in row.get("variants") or []:
                check({**merged, **v}, f"{code} variant {v['match']}")

    def test_every_code_renders_a_clean_message(self):
        for code in TABLE["codes"]:
            out = stop_explain.explain_stop(code)
            for key in ("what_happened", "why", "fix", "message"):
                self.assertTrue(out[key].strip(), f"{code}: {key}")
                clean(self, out[key], f"{code} {key}")
            for choice in out["choices"]:
                clean(self, choice, f"{code} choice")
            self.assertIn("1. ", out["message"])
            self.assertIn("2. ", out["message"])

class TheRealNumbersAreFilledIn(unittest.TestCase):
    def test_the_picture_budget_stop_names_the_real_numbers(self):
        out = stop_explain.explain_stop("AF-LAUNCH-IMAGE-PLAN-CAP", envelope={
            "detail": "image_plan.image_cap: 135 pictures cost more than your budget: 9500 minor USD pays for "
                      "at most 95. Nothing has been spent."})
        self.assertEqual(out["what_happened"],
                         "Your pages need 135 pictures, but your picture budget of $95 covers only 95.")
        self.assertIn("Nothing was charged.", out["message"])
        clean(self, out["message"], "budget")

    def test_the_text_cap_stop_names_the_real_numbers(self):
        out = stop_explain.explain_stop("AF-LAUNCH-PLAN-TEXT-CAP", envelope={
            "detail": "text_sets: 7 promotional sets exceeds the cap of 5 (a, b, c, d, e, f, g)"})
        self.assertEqual(out["what_happened"],
                         "Your plan has 7 sets of sales texts, but a launch can have at most 5.")

    def test_caller_facts_fill_placeholders(self):
        out = stop_explain.explain_stop("AF-LAUNCH-PLAN-TEXT-CAP", facts={"count": 6, "cap": 5})
        self.assertEqual(out["what_happened"],
                         "Your plan has 6 sets of sales texts, but a launch can have at most 5.")

    def test_a_missing_fact_never_leaves_a_placeholder(self):
        out = stop_explain.explain_stop("AF-LAUNCH-PLAN-TEXT-CAP")
        self.assertNotIn("{", out["what_happened"])
        self.assertIn("more sets of sales texts", out["what_happened"])

    def test_nothing_charged_is_said_only_when_the_stop_says_so(self):
        quiet = stop_explain.explain_stop("AF-LAUNCH-PKG-HASH", envelope={"detail": "artifact moved"})
        self.assertNotIn("charged", quiet["message"])

class UnknownStopsStillGetFourParts(unittest.TestCase):
    def test_an_unknown_code_falls_back_to_four_plain_parts(self):
        out = stop_explain.explain_stop("AF-NEVER-SEEN", envelope={
            "detail": "the widget at /opt/skills/x/thing.json broke (AF-NEVER-SEEN-2)",
            "next_action": "run tools/fix.py then retry"})
        for key in ("what_happened", "why", "fix"):
            self.assertTrue(out[key].strip(), key)
        self.assertGreaterEqual(len(out["choices"]), 2)
        clean(self, out["message"], "fallback")
        self.assertIn("widget", out["what_happened"])

    def test_nothing_at_all_still_says_something(self):
        out = stop_explain.explain_stop(None)
        self.assertTrue(out["what_happened"] and out["why"] and out["fix"] and len(out["choices"]) >= 2)

    def test_a_trace_never_reaches_the_client(self):
        out = stop_explain.explain_stop("AF-NEVER-SEEN", envelope={
            "detail": 'Traceback (most recent call last):\n  File "x.py", line 3, in <module>\nKeyError: 1'})
        clean(self, out["message"], "trace")

    def test_an_exception_with_a_secret_value_is_scrubbed_to_generic_parts(self):
        """Round-1 finding 2: 'internal customer token is abc123; KeyError: secret_setting'
        must not reach the client — no token, no identifier, no error class."""
        from launcher_core import launch_bridge  # noqa: E402  (local: summary uses explanations)
        out = stop_explain.explain_stop("AF-NEVER-SEEN", envelope={
            "detail": "internal customer token is abc123; KeyError: secret_setting"})
        message = out["message"]
        lowered = message.lower()
        for leaked in ("abc123", "secret_setting", "keyerror", "internal",
                       "customer token", "token is"):
            self.assertNotIn(leaked, lowered, f"secret/exception text reaches the client: {leaked!r}")
        clean(self, message, "secret-scrub")
        self.assertEqual(out["what_happened"], stop_explain._FALLBACK["what_happened"])

    def test_round2_unknown_transport_codes_never_reach_the_client(self):
        """Round-2 finding 3: raw 'HTTP 429 billing problem' must not reach the client.
        Transport words and their 4xx/5xx status go; the plain words stay."""
        out = stop_explain.explain_stop("AF-NEVER-SEEN", envelope={
            "detail": "HTTP 429 billing problem"})
        lowered = out["message"].lower()
        self.assertNotIn("http", lowered)
        self.assertNotIn("429", out["message"])
        self.assertIn("billing problem", lowered)
        clean(self, out["message"], "transport-scrub")

    def test_round2_an_operator_note_never_becomes_the_client_fix(self):
        """Round-2 finding 4: a next_step written for the operator (a tool path) must not
        reach the client as the fix. The fix falls back to the plain generic one."""
        out = stop_explain.explain_stop("AF-NEVER-SEEN", envelope={
            "detail": "something stopped the run",
            "next_action": "run tools/fix.py then retry"})
        clean(self, out["message"], "operator-note")
        self.assertNotIn("tools/fix.py", out["message"])
        self.assertEqual(out["fix"], stop_explain._FALLBACK["fix"])

    def test_round2_unknown_fallback_names_no_rule_and_no_cost_claim(self):
        """Round-2 finding 4: the unknown fallback asserts no protective rule and no cost
        record it has no evidence for. The why names only the stop itself."""
        out = stop_explain.explain_stop("AF-NEVER-SEEN")
        lowered = (out["why"] + " " + out["fix"]).lower()
        for claimed in ("protect", "customer", "money", "charged", "spent", "cost"):
            self.assertNotIn(claimed, lowered,
                             f"fallback claims what it has no evidence for: {claimed!r}")

    def test_round2_every_distinct_check_failure_gets_its_explanation(self):
        """Round-2 finding 2: no slice on explain_violations in cmd_check. Five distinct check
        failures print five client messages, not three."""
        import inspect  # noqa: E402
        from launcher_core import cli as cli_module  # noqa: E402
        body = inspect.getsource(cli_module).split("def cmd_check")[1].split("\ndef ")[0]
        self.assertNotIn("[:3]", body)
        five = ["AF-LAUNCH-IMAGE-PLAN-CAP: detail one", "AF-LAUNCH-PLAN-TEXT-CAP: detail two",
                "AF-LAUNCH-PKG-HASH: detail three", "AF-LAUNCH-ASSEMBLE-ARGS: detail four",
                "AF-LAUNCH-LINKED-URL: detail five"]
        self.assertEqual(len(stop_explain.explain_violations(five)), 5)

    def test_round2_install_blockers_get_a_client_message(self):
        """Round-2 finding 1: 'dependencies --install' with leftover blockers prints a
        CLIENT MESSAGE. A blocked install is a stop, never a bare nonzero exit."""
        import inspect  # noqa: E402
        from launcher_core import cli as cli_module  # noqa: E402
        body = inspect.getsource(cli_module).split("def cmd_dependencies")[1].split("\ndef ")[0]
        tail = body.split("SELECTED BUT MISSING")[1]
        self.assertIn("_tell_client", tail)

    def test_every_cli_stop_forwards_the_client_four_parts(self):
        """Round-1 finding 1: the flagged stops (brand, revise-image, shared intake,
        dependencies, sop-ack) print a CLIENT MESSAGE, never a bare FAIL."""
        import inspect  # noqa: E402
        from launcher_core import cli as cli_module  # noqa: E402
        source = inspect.getsource(cli_module)
        for fn in ("cmd_brand", "cmd_revise_image", "cmd_dependencies", "cmd_sop_ack",
                   "cmd_dispatch", "cmd_questions"):
            body = source.split(f"def {fn}")[1].split("\ndef ")[0]
            self.assertIn("_tell_stop", body, f"{fn} ends without a four-part client message")

    def test_summary_states_the_explanation_not_the_raw_blocker(self):
        """Round-1 finding 3: summary_lines prints the explanation's what_happened and fix,
        with why and the numbered choices — never the raw operator sentence alone."""
        from launcher_core import launch_bridge  # noqa: E402
        rep = {"pages": ["landing"], "page_labels": ["landing"],
               "lane_plan": {"phase_1_alone": [], "independent_pages": 1},
               "parallel": "parallel", "paid_calls_allowed": False, "to_confirm": [],
               "linked_delivery": {
                   "client_blockers": ["EXTERNAL xyz url 'http://x' is not an https address"],
                   "next_steps": ["Record the https address."],
                   "client_explanations": [stop_explain.explain_stop(
                       "AF-LAUNCH-LINKED-URL",
                       envelope={"detail": "whatever the operator logged",
                                 "client_message": "The destination 'members' needs a real https address.",
                                 "next_step": "Record the https address buyers are actually sent to."})]}}
        lines = launch_bridge.summary_lines(rep)
        joined = "\n".join(lines)
        explanation = rep["linked_delivery"]["client_explanations"][0]
        self.assertIn(explanation["what_happened"], joined)
        self.assertIn(explanation["fix"], joined)
        self.assertIn("What I can do right now:", joined)
        self.assertNotIn("EXTERNAL xyz", joined)

class TheStopPointsCarryTheExplanation(unittest.TestCase):
    def test_a_raised_refusal_becomes_a_clean_client_message(self):
        refusal = cli.CliError("AF-LAUNCH-ASSEMBLE-ARGS", "give --run-dir (the dispatch run folder) or --pieces")
        err = io.StringIO()
        with redirect_stderr(err):
            cli._tell_client([stop_explain.explain_exception(refusal)])
        message = err.getvalue().split("CLIENT MESSAGE (say this to the client, in your own warm voice):\n", 1)[1]
        clean(self, message, "cli")

    def test_main_prints_the_client_message_on_a_refusal(self):
        err = io.StringIO()
        with redirect_stderr(err), redirect_stdout(io.StringIO()):
            rc = cli.main(["plan"])  # neither --intake nor --plan: AF-LAUNCH-PLAN-ARGS
        self.assertEqual(rc, 2)
        self.assertIn("FAIL AF-LAUNCH-PLAN-ARGS", err.getvalue())  # the operator line keeps its code
        message = err.getvalue().split("CLIENT MESSAGE (say this to the client, in your own warm voice):\n", 1)[1]
        clean(self, message, "main")

    def test_a_linked_blocker_carries_its_explanation(self):
        row = linked_delivery._blocker("AF-LAUNCH-LINKED-URL", "The destination 'members' needs a real https "
                                       "address.", "Record the https address.", "members: http only", "members")
        self.assertEqual(set(row["client_explanation"]), {"what_happened", "why", "fix", "choices", "message"})
        self.assertEqual(row["client_message"], "The destination 'members' needs a real https address.")
        clean(self, row["client_explanation"]["message"], "linked")

    def test_a_blocked_capability_carries_its_explanation(self):
        live = {"test_only": False, "offers": [{"offer_id": "main", "role": "main", "canonical": {"prices": [{}]}}],
                "journey_mode": "single_simple", "launch_id": "x"}
        record = capability_check.run(live)
        self.assertIn("billing_type", record["blocked"])
        self.assertEqual(len(record["client_explanations"]), len(record["blocked"]))
        for each in record["client_explanations"]:
            clean(self, each["message"], "capability")

    def test_a_waiting_picture_page_carries_its_explanation(self):
        out = stop_explain.explain_stop("image_stage:awaiting_layout_proof_approval",
                                        envelope={"detail": "the layout proofs are the first approval checkpoint"})
        self.assertIn("waiting for your OK", out["what_happened"])
        clean(self, out["message"], "picture hold")
        source = (SKILL_ROOT / "launcher_core" / "image_stages.py").read_text(encoding="utf-8")
        self.assertIn('p["client_explanation"] = stop_explain.explain_stop(f"image_stage:', source)

class TheSkillTellsTheAgent(unittest.TestCase):
    def test_skill_md_carries_the_four_part_contract_and_the_maintainer_rule(self):
        text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        head = text.partition("## Operator reference (NEVER read")[0]
        section = head.partition("## When something stops the work")[2]
        self.assertTrue(section, "SKILL.md has no 'When something stops the work' section before the operator part")
        for needed in ("What happened", "Why this rule is here", "What will fix it", "choices",
                       "references/stop-explanations.json", "tests/test_stop_explanations.py"):
            self.assertIn(needed, section)


if __name__ == "__main__":
    unittest.main(verbosity=2)
