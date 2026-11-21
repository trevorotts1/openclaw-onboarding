#!/usr/bin/env python3
"""test_funnel_stop_explainer.py - every Skill 49 stop the client can see explains itself in plain words.

Offline, stdlib only, no spend. Run: python3 test_funnel_stop_explainer.py

STOP INVENTORY (where Skill 49 stops, refuses, holds or waits, and who sees it):
  * signature-funnel-entry.sh die "<TAG>": DEPS, VERSION, MODE, USAGE, MODEL-TIER, SELF-TEST
    ("ABORT [TAG]: ..."), and front_door.py FrontDoorError gates VERSION, DEPT-MAP, HASH-PIN,
    BYPASS-SCAN, PIN-ROTATION (same "ABORT [TAG]" form).
  * run_signature_funnel.py: every P0..P9 phase gate and P10-EMAIL abort (process_manifest.json
    aborted_at + detail; every AF-FUN-* code in FUNNEL-MANIFEST.json and in the provers), the
    AF-FUN-FRONT-DOOR refusals, the VISUAL-ARGS / VISUAL-STEP visual step, and a prover that cannot
    read its file ("USAGE/IO ERROR").
  * the seven provers' AF-FUN-* violations (intake, copy, prompt floor, graph, build, no-pitch, cert).
  * launch mode: launch_intake.py awaiting_missing_fact (incl. "payment plans are not supported in
    this release") and IntakeError/ApprovalError, dispatch_launch.py FAIL (approval, page set, image
    cap, route), legacy_downsell_images.py REFUSED (paid run without OK, placeholder approval, card
    fields, final-mockups not closed), collect_launch_receipts.py a "blocked" checkpoint, and
    page_set.py AF-FUN-IMAGE-CAP-MONEY, launch_plan.py AF-FUN-LAUNCH-EMAIL-REGISTRY.
The guard below collects the AF-FUN codes from the code itself, so a new stop with no entry fails.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
sys.path.insert(0, str(HERE))
import funnel_stop_explainer as es  # noqa: E402

TABLE = es.load_table()
ENTRIES = TABLE["entries"]
SKIP = ("vendor", "fixtures", "working", "examples", "tests", "__pycache__")
CODE = re.compile(r"AF-FUN-[A-Z0-9]+(?:-[A-Z0-9]+)*")
# Client words never carry a code-like or ENV_NAME token, an exception name, a path, a file name or a {slot}.
LEAKS = re.compile(r"\b[A-Z][A-Z0-9]*(?:[-_][A-Z0-9]+)+\b|\b\w*(?:Error|Exception)\b|ABORT \[|Traceback|File \"|"
                   r"\.py\b|\.json\b|/[\w.-]+/|[{}]")
# Each entry-shell / front_door abort tag and the one entry that must explain it.
SHELL_TAGS = {"DEPS": "FD-DEPS", "VERSION": "FD-VERSION", "MODE": "FD-MODE", "USAGE": "FD-USAGE",
              "MODEL-TIER": "AF-FUN-MODEL-TIER", "SELF-TEST": "FD-SELF-TEST", "DEPT-MAP": "FD-DEPT-MAP",
              "HASH-PIN": "AF-FUN-HASH-PIN", "BYPASS-SCAN": "AF-FUN-CANONICAL-BYPASS",
              "PIN-ROTATION": "FD-PIN-ROTATION"}
# Launch-mode and setup stops that carry no AF code: the refusal text that must resolve.
PHRASE_STOPS = {
    "FAIL: plan is not ready: missing main offer price": "LAUNCH-MISSING-FACT",
    "billing 'installment' (payment plans are not supported in this release)": "LAUNCH-PAYMENT-PLAN",
    "FAIL: approval not verified against platform record: no approval_id": "LAUNCH-APPROVAL",
    "the worker operating the run cannot approve its own work (self-approval is refused)": "LAUNCH-APPROVAL",
    "this plan is already approved; call request_revision() first": "LAUNCH-ALREADY-APPROVED",
    "image cap 40 is smaller than this launch needs": "LAUNCH-IMAGE-CAP",
    "--image-provider kie spends money; it needs --allow-paid, approved by the owner": "LAUNCH-PAID-NEEDS-OK",
    "checkout: the manuscript names card, expiry or security-code fields": "LAUNCH-CARD-FIELDS",
    "final-mockups has no closed record with images for page(s) ['main']; nothing recorded": "LAUNCH-DESIGN-RECORD",
    "USAGE/IO ERROR: cannot load copy ledger 'copy_ledger.json': [Errno 2]": "RUN-FILE-UNREADABLE",
    # the dispatch command line's two named launch-mode stops (their own entries, not a borrow)
    "FAIL: the launch request file is not valid JSON": "LAUNCH-REQUEST-BROKEN",
    "adapters require --out (or --run-dir) as the work dir for request/result files": "LAUNCH-NO-WORK-FOLDER",
}


def code_inventory():
    found = set(json.loads((SKILL / "FUNNEL-MANIFEST.json").read_text(encoding="utf-8"))["autofail_codes"])
    for root, dirs, files in os.walk(SKILL):
        dirs[:] = [d for d in dirs if d not in SKIP]
        for f in files:
            if f.endswith((".py", ".sh")) and not f.startswith("test_") and f != "funnel_stop_explainer.py":
                found |= set(CODE.findall(Path(root, f).read_text(encoding="utf-8", errors="replace")))
    return found


def missing_entries(entries, inventory):
    """Codes with no entry OF THEIR OWN. The parent fallback in resolve() is a runtime safety net only; a
    shipped stop must carry its own words, so a parent never stands in for a missing child here."""
    return sorted(c for c in inventory if c not in entries)


def client_part(stderr):
    """What the entry shell prints for the client: everything after its FOR THE CLIENT: line."""
    return stderr.split("FOR THE CLIENT:\n", 1)[1] if "FOR THE CLIENT:\n" in stderr else ""


class TableShape(unittest.TestCase):
    def test_every_entry_has_four_parts_and_two_to_four_choices(self):
        for code, e in ENTRIES.items():
            for part in ("what_happened", "why", "fix"):
                self.assertTrue(str(e.get(part, "")).strip(), f"{code}: empty {part}")
            self.assertTrue(2 <= len(e["choices"]) <= 4, f"{code}: {len(e['choices'])} choices")
            self.assertTrue(any(c.startswith("I ") for c in e["choices"]),
                            f"{code}: no choice where the agent does the work")

    def test_entry_words_carry_no_codes_or_paths(self):
        for code, e in ENTRIES.items():
            text = " ".join([e["what_happened"], e["why"], e["fix"], *e["choices"]])
            text = re.sub(r"\{[a-z_]+\}", "", text)
            self.assertIsNone(LEAKS.search(text), f"{code}: client words leak {LEAKS.search(text)}")


class InventoryGuard(unittest.TestCase):
    def test_every_stop_code_in_the_code_has_its_own_entry(self):
        self.assertEqual(missing_entries(ENTRIES, code_inventory()), [],
                         "add these stops to references/stop-explanations.json")

    def test_guard_catches_a_child_code_hidden_by_its_parent(self):
        inventory = code_inventory()
        self.assertIn("AF-FUN-DELEG-RECEIPT-UNSIGNED", inventory)
        without = {k: v for k, v in ENTRIES.items() if k != "AF-FUN-DELEG-RECEIPT-UNSIGNED"}
        self.assertIsNotNone(es.resolve("AF-FUN-DELEG-RECEIPT-UNSIGNED", "", without))  # the parent still answers
        self.assertEqual(missing_entries(without, inventory), ["AF-FUN-DELEG-RECEIPT-UNSIGNED"])

    def test_every_shell_abort_tag_resolves_to_its_entry(self):
        for tag, want in SHELL_TAGS.items():
            self.assertEqual(es.resolve(None, f"ABORT [{tag}]: detail", ENTRIES), want, tag)

    def test_entry_shell_tags_are_all_listed(self):
        sh = (SKILL / "signature-funnel-entry.sh").read_text(encoding="utf-8")
        fd = (HERE / "front_door.py").read_text(encoding="utf-8")
        tags = set(re.findall(r'die "([A-Z-]+)"', sh)) | set(re.findall(r'FrontDoorError\("([A-Z-]+)"', fd))
        self.assertEqual(sorted(tags - set(SHELL_TAGS)), [], "a new shell stop tag needs an entry")

    def test_launch_and_setup_phrases_resolve(self):
        for text, want in PHRASE_STOPS.items():
            self.assertEqual(es.resolve(None, text, ENTRIES), want, text)


class OrchestratorUsageStopsCarryNoPath(unittest.TestCase):
    """Round-2 review, finding 4: the run-dir usage error printed the absolute run directory
    before the client message, so the raw operator path stayed visible in the command output."""

    def run_orch(self, *args):
        with tempfile.TemporaryDirectory() as home:
            env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": home}
            return subprocess.run([sys.executable, str(SKILL / "run_signature_funnel.py"), *args],
                                  text=True, capture_output=True, env=env, timeout=120)

    def test_a_missing_job_folder_names_no_path(self):
        with tempfile.TemporaryDirectory() as td:
            missing = Path(td) / "not-a-folder"
            p = self.run_orch("--run-dir", str(missing))
        out = p.stdout + p.stderr
        self.assertNotEqual(p.returncode, 0, out)
        self.assertNotIn(str(missing), out, out)      # the whole path, never printed
        self.assertNotIn(str(Path(td)), out, out)     # nor its parent
        self.assertIn("Start it again with the job folder", out, out)
        self.assertIn("FOR THE CLIENT:", out, out)

    def test_the_job_folder_stop_is_still_explained(self):
        with tempfile.TemporaryDirectory() as td:
            p = self.run_orch("--run-dir", str(Path(td) / "gone"))
        msg = client_part(p.stdout + p.stderr)
        self.assertIn("started without everything it needs", msg, msg)
        self.assertIsNone(LEAKS.search(msg), msg)

class EntryShellExplains(unittest.TestCase):
    """A refusal from the canonical entry shell carries the four plain parts, never only its ABORT code."""

    def entry(self, *args):
        with tempfile.TemporaryDirectory() as home:
            env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": home,
                   "PYTHON": sys.executable, "OPENCLAW_PLATFORM": "mac"}
            return subprocess.run(["bash", str(SKILL / "signature-funnel-entry.sh"), *args],
                                  text=True, capture_output=True, env=env, timeout=120)

    def assertExplained(self, p, needle):
        self.assertNotEqual(p.returncode, 0)
        msg = client_part(p.stderr)
        self.assertIn(needle, msg, p.stderr)
        for head in ("What happened:", "Why this rule exists:", "What will fix it:", "Your choices:", "1. ", "2. "):
            self.assertIn(head, msg)
        self.assertIsNone(LEAKS.search(msg), msg)
        self.assertTrue(msg.rstrip().endswith("Reply with the number you want."), msg)

    def test_invalid_mode_is_explained(self):
        self.assertExplained(self.entry("--mode", "bogus"), "started without everything it needs")

    def test_missing_run_dir_value_is_explained(self):
        self.assertExplained(self.entry("--run-dir"), "started without everything it needs")

    def test_front_door_refusal_is_explained(self):
        with tempfile.TemporaryDirectory() as rd:
            Path(rd, "d.sh").write_text("curl https://api.kie.ai/api/v1/jobs/" + "createTask\n", encoding="utf-8")
            p = self.entry("--scan-only", "--run-dir", rd)
        self.assertIn("ABORT [BYPASS-SCAN]", p.stderr)  # the code stays for the log
        self.assertExplained(p, "approved tools")


class Rendering(unittest.TestCase):
    def assertClean(self, out):
        self.assertIsNone(LEAKS.search(out["message"]), out["message"])
        for head in ("What happened:", "Why this rule exists:", "What will fix it:", "Your choices:", "1. ", "2. "):
            self.assertIn(head, out["message"])

    def test_every_entry_renders_clean_with_defaults(self):
        for code in ENTRIES:
            self.assertClean(es.explain_stop(code))

    def test_real_prover_line_fills_real_numbers(self):
        line = ("prove_sf_copy.py rc=2 :: VIOLATION [AF-FUN-SEC12-WORDS] page 'main' Section 12 "
                "(The Big Bold Heartfelt Message): 160 words, over the sacred maximum of 150")
        out = es.explain_stop(envelope=line)
        self.assertIn("160 words", out["what_happened"])
        self.assertIn("between 100 and 150 words", out["what_happened"])
        self.assertIn("Signature Sales Page", out["what_happened"])
        self.assertClean(out)

    def test_band_line_fills_count_min_and_max(self):
        line = ("VIOLATION [AF-FUN-PAIN-CHARBAND] page 'upsell' Section 2 (The Big Bold Pain 1): "
                "visible copy is 240 chars, over the profile maximum 225 (copy profile band [180, 225] chars)")
        out = es.explain_stop(envelope=line)
        self.assertIn("240 characters", out["what_happened"])
        self.assertIn("between 180 and 225", out["what_happened"])
        self.assertIn("Upsell 1", out["what_happened"])

    def test_given_facts_win_and_are_cleaned(self):
        out = es.explain_stop("AF-FUN-BUILD-QC", {"score": "7.1"})
        self.assertIn("7.1", out["what_happened"])
        self.assertIn("8.5 out of 10", out["what_happened"])
        out = es.explain_stop("AF-FUN-INTAKE-MISSING", {"missing": "/tmp/x/brief.json AF-FUN-X"})
        self.assertClean(out)

    def test_child_code_falls_back_to_parent(self):
        self.assertEqual(es.explain_stop(envelope="AF-FUN-IMG-HOST-UNSIGNED: forged")["code"], "AF-FUN-IMG-HOST")

    def test_no_spend_claim_only_where_true(self):
        self.assertIn("did not spend any money", es.explain_stop("AF-FUN-SEC1-CHARBAND")["message"])
        self.assertNotIn("did not spend any money", es.explain_stop("AF-FUN-VISUAL-STEP")["message"])
        self.assertNotIn("did not spend any money", es.explain_stop(envelope="something odd")["message"])

    def test_unknown_stop_still_gets_four_parts(self):
        out = es.explain_stop("AF-NOPE", envelope={"detail": "it broke in /tmp/a/b.py AF-FUN-ZZZ-QQ",
                                                    "next_action": "run the step again"})
        self.assertIsNone(out["code"])
        self.assertEqual(out["what_happened"], "it broke in a file")
        self.assertEqual(out["fix"], "run the step again")
        self.assertTrue(out["why"] and len(out["choices"]) >= 2)
        self.assertClean(out)
        empty = es.explain_stop()
        self.assertEqual(empty["what_happened"], TABLE["fallback"]["what_happened"])
        self.assertClean(empty)

    def test_unknown_codes_exception_names_and_env_names_never_reach_the_client(self):
        for detail in ("RUN-UNKNOWN: PermissionError: /tmp/private.txt", "KeyError: q3_offer_name",
                       "SF_RUN_NONCE refused rc=2", "OSError [Errno 13] on copy_ledger.json",
                       "HTTP 403 from https:/a file with API access forbidden"):
            out = es.explain_stop(envelope={"detail": detail})
            self.assertIsNone(out["code"], detail)
            self.assertEqual(out["what_happened"], TABLE["fallback"]["what_happened"], detail)
            for word in ("RUN-UNKNOWN", "PermissionError", "KeyError", "q3_offer_name", "SF_RUN_NONCE", "Errno",
                         "rc=", "private", "403", "HTTP"):
                self.assertNotIn(word, out["message"], detail)
            self.assertClean(out)
        out = es.explain_stop(envelope={"detail": "the brief could not be read because the disk is full"})
        self.assertEqual(out["what_happened"], "the brief could not be read because the disk is full")

    def test_missing_qc_score_never_reports_a_score(self):
        out = es.explain_stop("AF-FUN-BUILD-QC")
        self.assertIn("no score recorded", out["what_happened"], out)
        self.assertNotRegex(out["what_happened"], r"scored [\d.]+", out)
        scored = es.explain_stop("AF-FUN-BUILD-QC", {"score": "7.1"})
        self.assertIn("7.1", scored["what_happened"], scored)

    def test_funnel_size_fallback_names_no_number(self):
        out = es.explain_stop("AF-FUN-BUILD-PAGESET")
        self.assertNotIn("approved-step", out["message"], out)
        self.assertClean(out)

    def test_technical_prose_is_not_echoed_as_the_client_message(self):
        """Reproduction from the round-2 review: cleaned machine talk is not fifth-grade wording."""
        out = es.explain_stop(envelope="encrypted archive exceeds 17 bytes and requires signature")
        self.assertEqual(out["what_happened"], TABLE["fallback"]["what_happened"], out)
        self.assertEqual(out["fix"], TABLE["fallback"]["fix"], out)
        self.assertClean(out)
        for detail in ("the payload could not be decoded (checksum mismatch)",
                       "serialized schema offset 0x1f out of range",
                       "compression failed on the buffer"):
            self.assertEqual(es.explain_stop(envelope=detail)["what_happened"],
                             TABLE["fallback"]["what_happened"], detail)
        # the control: a plain sentence about the client's own work is still their own words
        plain = "the brief could not be read because the disk is full"
        self.assertEqual(es.explain_stop(envelope=plain)["what_happened"], plain)

    def test_traceback_never_reaches_the_client(self):
        tb = 'Traceback (most recent call last):\n  File "/x/y.py", line 3, in <module>\nValueError: bad'
        self.assertClean(es.explain_stop(envelope=tb))


if __name__ == "__main__":
    unittest.main(verbosity=1)
