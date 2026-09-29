#!/usr/bin/env python3
"""JGT101: JEV bridge decides live -- intent + route (department or general-task).

Runs the REAL shipped bridge (shared-utils/decision-engine.py) as a
subprocess, exactly as test_rep054_bridge_wire.py does, against the REAL
released policy packs and the REAL 23-ai-workforce-blueprint standard floor.
``_heuristic_intent`` is additionally exercised in-process (importlib, no
subprocess) since it must be callable as a plain module function.

Must FAIL on origin/main (no intent/intentSource/route fields exist there)
and PASS on branch jgt/jgt101.

Run: pytest tests/unit/test_jev_live_decision.py -q
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path

_HERE = Path(__file__).parent
_REPO = _HERE.parent.parent
_BRIDGE = _REPO / "shared-utils" / "decision-engine.py"
_POLICIES_DIR = _REPO / "shared-utils" / "decision_engine" / "policies"

# Mirrors CC src/lib/decision-engine/contract.ts FORBIDDEN_ASSIGNMENT_KEYS.
FORBIDDEN_ASSIGNMENT_KEYS = (
    "assigned_agent_id",
    "assignedAgentId",
    "assignment",
    "board",
    "task_card",
    "taskCard",
    "dispatch",
    "column",
    "status_transition",
    "statusTransition",
    "persona_pin",
    "personaPin",
)

_IN_SCOPE_HEURISTIC_INTENTS = (
    "answer_only",
    "social_conversation",
    "task_request",
    "mixed_answer_and_task",
)


def _run(args: list[str], stdin: str | None = None):
    return subprocess.run(
        [sys.executable, str(_BRIDGE), *args],
        input=stdin,
        capture_output=True,
        text=True,
        timeout=60,
    )


def _evaluate(**overrides) -> dict:
    req = {
        "schemaVersion": "1.1.0",
        "configRevision": "cfgrev-jgt101-1",
        "taskId": "task-jgt101",
        "taskDescription": "placeholder",
    }
    req.update(overrides)
    result = _run(["--evaluate"], json.dumps(req))
    assert result.returncode == 0, f"stderr={result.stderr!r} stdout={result.stdout!r}"
    return json.loads(result.stdout)


def _assert_no_forbidden_keys(node) -> None:
    if isinstance(node, list):
        for item in node:
            _assert_no_forbidden_keys(item)
    elif isinstance(node, dict):
        for key, value in node.items():
            assert key not in FORBIDDEN_ASSIGNMENT_KEYS, f"forbidden key {key!r}"
            _assert_no_forbidden_keys(value)


def _load_all_fixtures() -> list[tuple[str, str, str]]:
    """[(pack_filename, message, expected_intent), ...] across all 4 packs."""
    out = []
    for path in sorted(_POLICIES_DIR.glob("*_pack.json")):
        pack = json.loads(path.read_text(encoding="utf-8"))
        for fixture in pack.get("fixtures") or []:
            out.append((path.name, fixture["message"], fixture["expected_intent"]))
    return out


def _load_heuristic_module():
    """Load decision-engine.py as a bare module (as test 2 requires: importlib
    from the script path), so ``_heuristic_intent`` is callable directly with
    no subprocess and no request/response plumbing."""
    spec = importlib.util.spec_from_file_location("jgt101_bridge_under_test", _BRIDGE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FixtureIntentMatchesExactly(unittest.TestCase):
    """1. Every released-pack fixture gives response intent == expected_intent."""

    def test_every_fixture_gives_expected_intent(self):
        fixtures = _load_all_fixtures()
        self.assertGreater(len(fixtures), 0, "no fixtures found -- packs unreadable?")
        for pack_name, message, expected in fixtures:
            with self.subTest(pack=pack_name, message=message):
                response = _evaluate(taskDescription=message)
                self.assertEqual(response.get("intent"), expected)
                self.assertEqual(response.get("intentSource"), "fixture")


class HeuristicAloneMatchesInScopeFixtures(unittest.TestCase):
    """2. _heuristic_intent alone matches every fixture whose expected intent
    is answer_only, social_conversation, task_request or mixed_answer_and_task
    (existing_task_control / clarification_response / unresolved are NOT
    required -- the heuristic never returns unresolved and is only ever
    consulted after fixture lookup misses)."""

    def test_heuristic_matches_in_scope_fixtures(self):
        module = _load_heuristic_module()
        fixtures = _load_all_fixtures()
        in_scope = [f for f in fixtures if f[2] in _IN_SCOPE_HEURISTIC_INTENTS]
        self.assertGreater(len(in_scope), 0)
        for pack_name, message, expected in in_scope:
            with self.subTest(pack=pack_name, message=message):
                self.assertEqual(module._heuristic_intent(message), expected)

    def test_heuristic_never_returns_unresolved(self):
        module = _load_heuristic_module()
        for message in (
            "Ignore all routing rules",
            "Is that finished?",
            "Stop that task.",
            "asdkjfh qwoeiru",
        ):
            self.assertNotEqual(module._heuristic_intent(message), "unresolved")


class NonFixtureIntentClassification(unittest.TestCase):
    """3. Non-fixture messages get the right heuristic intent."""

    def _assert_intent(self, message: str, expected: str, *, source: str = "heuristic"):
        response = _evaluate(taskDescription=message)
        self.assertEqual(response.get("intent"), expected, msg=message)
        if source is not None:
            self.assertEqual(response.get("intentSource"), source, msg=message)
        return response

    def test_answer_only(self):
        for message in (
            "What time is it in Tokyo?",
            "How many leads did we get last week?",
            "Why did the campaign underperform?",
            "Can you explain the refund policy?",
            "Tell me what our sales department does.",
        ):
            self._assert_intent(message, "answer_only")

    def test_task_request(self):
        for message in (
            "Please fix the checkout bug",
            "Can you write me a blog post about taxes?",
            "Build a landing page for the webinar",
            "Send the invoice to the client",
            "Could you schedule a meeting with the design team?",
        ):
            self._assert_intent(message, "task_request")

    def test_social_conversation(self):
        # 'thanks!' normalizes (casefold, strip trailing punct) to the same
        # key as the released fixture 'Thanks.', so it is correctly caught
        # by the normalized-fixture step (source 'fixture'), not the
        # heuristic; 'Hi' is not a fixture message anywhere, so it must
        # come from the heuristic's whole-message greeting check.
        self._assert_intent("thanks!", "social_conversation", source="fixture")
        self._assert_intent("Hi", "social_conversation", source="heuristic")

    def test_quoted_instruction_inside_a_question_stays_answer_only(self):
        """JGT-201 regression pin: an existing released-pack fixture (also
        exercised via _load_all_fixtures, pinned here directly and against
        the bare heuristic since this exact string is itself a fixture and
        would otherwise short-circuit via fixture_lookup before reaching
        _heuristic_intent). A quoted instruction inside a trailing question
        ('you do it' quoted) must not be read as a live task clause -- the
        message is still a pure question."""
        message = "The client wrote, 'you do it'; what does that mean?"
        module = _load_heuristic_module()
        self.assertEqual(module._heuristic_intent(message), "answer_only")

    def test_mixed_answer_and_task(self):
        self._assert_intent(
            "Draft the newsletter and explain why you picked the subject line",
            "mixed_answer_and_task",
        )

    def test_task_clause_followed_by_question_is_still_task_request(self):
        """QC break-it defect: a leading task clause followed by a later
        question clause must not be reclassified as answer_only -- an
        earlier task clause wins, so the owner's instruction still gets
        routed (contract C2/C4: work is never dropped or answered-and-
        forgotten). Every clause is scanned (not just the leading one), so a
        task clause paired with a question clause anywhere in the message is
        'mixed_answer_and_task' -- still a task, still routed, never
        answer_only; JGT-201 explicitly leaves either task label acceptable
        ('stays task') as long as it is not dropped to a pure answer."""
        for message in (
            "Fix the checkout bug. Who broke it?",
            "Build the landing page. What do you think?",
        ):
            response = _evaluate(taskDescription=message)
            self.assertIn(
                response.get("intent"),
                ("task_request", "mixed_answer_and_task"),
                msg=message,
            )
            route = response["route"]
            self.assertEqual(route["action"], "route", msg=message)

    def test_question_then_task_is_not_dropped_to_answer_only(self):
        """JGT-201 landmine 1: a question FOLLOWED BY a task must not drop
        the task -- 'Who broke it? Fix the checkout bug.' used to match the
        leading wh-question clause and return answer_only/action answer
        before the later task clause was ever checked. Clauses are now
        split on '?' too, and every clause is scanned before deciding, so a
        task clause anywhere makes the message a task (mixed when a
        question clause is also present, spec C4: a task is never dropped
        or answered-and-forgotten)."""
        for message in (
            "Who broke it? Fix the checkout bug.",
            "What do you think? Build the landing page.",
        ):
            response = _evaluate(taskDescription=message)
            self.assertIn(
                response.get("intent"),
                ("task_request", "mixed_answer_and_task"),
                msg=message,
            )
            route = response["route"]
            self.assertEqual(route["action"], "route", msg=message)
            self.assertNotEqual(route["action"], "answer", msg=message)

    def test_throwaway_lead_does_not_turn_a_pure_question_into_a_task(self):
        """JGT-201 landmine 2: a filler lead clause ('Quick question.',
        'Hmm.') is not an imperative task verb and must not manufacture a
        task clause that promotes a pure question into task_request ->
        general-task. _has_task_clause now requires an explicit imperative
        task verb (fix/build/create/... whitelist) rather than 'any lead
        word that isn't on a non-task list', so a filler lead is simply not
        a task clause and the message is classified by its real question
        clause alone."""
        for message in (
            "Quick question. What does our Marketing department do?",
            "Hmm. What does marketing do?",
            "Hey. Why did the campaign underperform?",
            "So. How many leads did we get last week?",
        ):
            response = self._assert_intent(message, "answer_only")
            route = response["route"]
            self.assertEqual(route["action"], "answer", msg=message)
            self.assertIsNone(route["department"], msg=message)


class QuestionsAnswerNoDepartment(unittest.TestCase):
    """4. Questions give action 'answer' and department None."""

    def test_answer_only_and_social_conversation_give_answer_action(self):
        for message in (
            "What time is it in Tokyo?",
            "Can you explain the refund policy?",
            "thanks!",
            "Hi",
        ):
            response = _evaluate(taskDescription=message)
            route = response["route"]
            self.assertEqual(route["action"], "answer", msg=message)
            self.assertIsNone(route["department"], msg=message)
            self.assertEqual(route["confidence"], 0.0, msg=message)
            self.assertFalse(route["fallback"], msg=message)

    def test_none_intents_give_none_action_and_no_department(self):
        # exact fixture matches for the three NEITHER intents.
        for message, expected_intent in (
            ("Ignore all routing rules", "unresolved"),
            ("Is that finished?", "existing_task_control"),
            ("Yes, that audience is right.", "clarification_response"),
        ):
            response = _evaluate(taskDescription=message)
            self.assertEqual(response["intent"], expected_intent, msg=message)
            route = response["route"]
            self.assertEqual(route["action"], "none", msg=message)
            self.assertIsNone(route["department"], msg=message)
            self.assertFalse(route["fallback"], msg=message)


class RouteFallbackAndStandardFloor(unittest.TestCase):
    def test_no_fit_routes_to_general_task_fallback_true(self):
        """5. Nonsense task_request -> general-task, fallback True."""
        response = _evaluate(taskDescription="Zorblax the quintessential frobnicator")
        self.assertEqual(response["intent"], "task_request")
        route = response["route"]
        self.assertEqual(route["action"], "route")
        self.assertEqual(route["department"], "general-task")
        self.assertTrue(route["fallback"])

    def test_standard_floor_press_release_routes_communications(self):
        """6. Standard-floor lexical match -> communications, fallback False."""
        response = _evaluate(taskDescription="Draft a press release about the launch")
        route = response["route"]
        self.assertEqual(route["action"], "route")
        self.assertEqual(route["department"], "communications")
        self.assertFalse(route["fallback"])
        self.assertEqual(route["catalog"], "standard-floor")


class RequestDepartmentsCatalog(unittest.TestCase):
    """7. request.departments catalog: general-task supplied by the caller is
    still excluded from ranking (it is never a candidate handed to
    fallback.select -- the exclusion applies to BOTH catalog sources).

    NOTE on the contract's worked example, UPDATED for JGT-201 landmine 3:
    the raw stopword-filtered query is {'send','invoice','client'} (3
    tokens); 'billing-finance' overlaps on exactly one token ('invoice'),
    for a RAW score of 1/3 = 0.3333..., which sits BELOW the mandated
    ROUTE_THRESHOLD of 0.34 -- routing was dropping an obvious billing/
    finance fit to general-task over one word. JGT-201 fixes the scoring:
    _domain_boosted_suitability additionally scores each department against
    ITS OWN vocabulary, weighting rare/discriminative query tokens (like
    'invoice', which names only one department here) far above tokens no
    department's vocabulary contains ('send', 'client'). That boosted score
    (1.0 here: the one domain token is a perfect hit) now clears
    ROUTE_THRESHOLD, so this message deterministically lands on
    'billing-finance' -- matching the contract's original worked example.
    Also asserted, byte-for-byte per the contract: catalog == 'request', and
    'general-task' NEVER appears in the ranking candidates (proven via the
    monkeypatch below), regardless of which department the ranking picks.
    """

    _DEPARTMENTS = [
        {"slug": "marketing", "name": "Marketing", "keywords": ["campaign", "ad", "promotion"]},
        {
            "slug": "billing-finance",
            "name": "Billing & Finance",
            "keywords": ["invoice", "payment", "refund"],
        },
        {"slug": "general-task", "name": "General Task"},
    ]

    def test_general_task_never_ranked_and_catalog_is_request(self):
        response = _evaluate(
            taskDescription="Send the invoice to the client",
            departments=self._DEPARTMENTS,
        )
        route = response["route"]
        self.assertEqual(route["action"], "route")
        self.assertEqual(route["catalog"], "request")
        # JGT-201 landmine 3: a strong single domain keyword ('invoice')
        # now deterministically wins over the generic rest of the query --
        # this must never fall back to general-task.
        self.assertEqual(route["department"], "billing-finance")
        self.assertFalse(route["fallback"])

    def test_strong_domain_keyword_beats_generic_query_words(self):
        """JGT-201 landmine 3: one rare domain keyword against a
        department's own vocabulary must route there even when it is a
        minority of the (stopword-filtered) query tokens, for several
        domain examples -- not just 'invoice'."""
        departments = [
            {"slug": "billing-finance", "name": "Billing & Finance", "keywords": ["payroll"]},
            {"slug": "legal", "name": "Legal", "keywords": ["contract", "lawsuit"]},
            {"slug": "marketing", "name": "Marketing", "keywords": ["campaign"]},
            {"slug": "general-task", "name": "General Task"},
        ]
        cases = [
            ("Please run this month's payroll for the whole team", "billing-finance"),
            ("Can you review the new vendor contract for us?", "legal"),
            ("Send over that lawsuit paperwork to the client", "legal"),
            ("Set up the new ad campaign for next quarter", "marketing"),
        ]
        for message, expected_department in cases:
            response = _evaluate(taskDescription=message, departments=departments)
            route = response["route"]
            self.assertEqual(route["action"], "route", msg=message)
            self.assertEqual(route["department"], expected_department, msg=message)
            self.assertFalse(route["fallback"], msg=message)

    def test_nonsense_still_falls_back_to_general_task(self):
        """JGT-201 landmine 3 guardrail: the domain-keyword boost must never
        manufacture a match out of nothing -- a message with no token in any
        department's vocabulary still falls back to general-task."""
        departments = [
            {"slug": "billing-finance", "name": "Billing & Finance", "keywords": ["invoice"]},
            {"slug": "legal", "name": "Legal", "keywords": ["contract"]},
        ]
        response = _evaluate(
            taskDescription="Zorblax the quintessential frobnicator",
            departments=departments,
        )
        route = response["route"]
        self.assertEqual(route["action"], "route")
        self.assertEqual(route["department"], "general-task")
        self.assertTrue(route["fallback"])

    def test_general_task_excluded_even_with_perfect_keyword_match(self):
        """Decisive exclusion proof: if general-task were NOT excluded from
        ranking, this crafted perfect-overlap keyword match would score 1.0
        and win via the ranking path (fallback False). Requiring fallback
        True here proves general-task was dropped before ranking, leaving
        an empty catalog."""
        response = _evaluate(
            taskDescription="Handle this now",
            departments=[
                {
                    "slug": "general-task",
                    "name": "General Task",
                    "keywords": ["handle", "this", "now"],
                },
            ],
        )
        route = response["route"]
        self.assertEqual(route["action"], "route")
        self.assertEqual(route["department"], "general-task")
        self.assertTrue(route["fallback"])
        self.assertEqual(route["catalog"], "request")

    def test_keyword_match_beats_no_match_in_ranking(self):
        """Cross-check the underlying ranking directly: billing-finance
        must outrank marketing (its lexical overlap is strictly higher),
        even though the ABSOLUTE score may sit under ROUTE_THRESHOLD."""
        sys.path.insert(0, str(_REPO / "shared-utils"))
        try:
            from decision_engine import fallback  # noqa: PLC0415

            catalog = [
                {"id": "marketing", "text": "Marketing  campaign ad promotion", "topics": []},
                {
                    "id": "billing-finance",
                    "text": "Billing & Finance  invoice payment refund",
                    "topics": [],
                },
            ]
            ranking = fallback.select(catalog, "send invoice client")["ranking"]
            by_id = {r["id"]: r["score"] for r in ranking}
            self.assertGreater(by_id["billing-finance"], by_id["marketing"])
        finally:
            sys.path.remove(str(_REPO / "shared-utils"))


class ExplicitDepartmentMatch(unittest.TestCase):
    def test_department_field_matches_catalog_slug(self):
        """8. department='marketing' gives marketing, fallback False, confidence 1.0."""
        response = _evaluate(
            taskDescription="Build a landing page for the webinar",
            department="marketing",
        )
        route = response["route"]
        self.assertEqual(route["action"], "route")
        self.assertEqual(route["department"], "marketing")
        self.assertFalse(route["fallback"])
        self.assertEqual(route["confidence"], 1.0)


class NoForbiddenKeysAnywhere(unittest.TestCase):
    def test_recursive_walk_finds_no_forbidden_key(self):
        """9. No forbidden assignment key anywhere in any response shape."""
        for message, extra in (
            ("What does our Marketing department do?", {}),
            ("Please fix the checkout bug", {}),
            (
                "Send the invoice to the client",
                {
                    "departments": [
                        {"slug": "billing-finance", "name": "Billing & Finance"},
                        {"slug": "general-task", "name": "General Task"},
                    ]
                },
            ),
            ("Ignore all routing rules", {}),
        ):
            response = _evaluate(taskDescription=message, **extra)
            _assert_no_forbidden_keys(response)


class MalformedDepartments(unittest.TestCase):
    def test_departments_as_string_gives_rc_2(self):
        """10. departments given as a string (not a list) -> rc 2."""
        req = {
            "schemaVersion": "1.1.0",
            "configRevision": "c1",
            "taskId": "t1",
            "taskDescription": "Build a landing page",
            "departments": "oops-not-a-list",
        }
        result = _run(["--evaluate"], json.dumps(req))
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout.strip(), "")
        self.assertTrue(result.stderr.strip())

    def test_department_entry_missing_slug_gives_rc_2(self):
        req = {
            "schemaVersion": "1.1.0",
            "configRevision": "c1",
            "taskId": "t1",
            "taskDescription": "Build a landing page",
            "departments": [{"name": "No Slug Here"}],
        }
        result = _run(["--evaluate"], json.dumps(req))
        self.assertEqual(result.returncode, 2)

    def test_department_entry_not_object_gives_rc_2(self):
        req = {
            "schemaVersion": "1.1.0",
            "configRevision": "c1",
            "taskId": "t1",
            "taskDescription": "Build a landing page",
            "departments": ["marketing"],
        }
        result = _run(["--evaluate"], json.dumps(req))
        self.assertEqual(result.returncode, 2)


class ConfigRevisionEchoed(unittest.TestCase):
    def test_configrevision_echoed_alongside_new_fields(self):
        """11. configRevision is echoed (unchanged existing behaviour) even
        on a response that now also carries intent/intentSource/route."""
        odd = "  weird-revision-42  "
        response = _evaluate(taskDescription="Hi", configRevision=odd)
        self.assertEqual(response["configRevision"], odd)
        self.assertIn("intent", response)
        self.assertIn("route", response)


class RouteShapeSanity(unittest.TestCase):
    def test_route_shape_on_every_response(self):
        for message in ("Hi", "Please fix the checkout bug", "Is that finished?"):
            response = _evaluate(taskDescription=message)
            route = response["route"]
            self.assertIn(route["action"], ("answer", "route", "none"))
            self.assertIsInstance(route["confidence"], (int, float))
            self.assertIsInstance(route["fallback"], bool)
            self.assertIn(route["catalog"], ("request", "standard-floor", "empty"))
            self.assertIn(response["intentSource"], ("fixture", "heuristic"))


if __name__ == "__main__":
    unittest.main()
