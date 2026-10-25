#!/usr/bin/env python3
"""S75-T17: reversible migration of the local character-library IDs.

Every record used here is produced by the REAL local writers:
``character_library.save_character`` for the save records and
``intake_session.process`` for the reuse records. Nothing is a hand-written
fixture of a record shape. Run with::

    python3 test_migration_plan_s75_t17.py
"""
import hashlib
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
CARD = os.path.join(CORE, "choice_card", "intake_card")
for _path in (HERE, CORE, CARD):
    if _path not in sys.path:
        sys.path.insert(0, _path)

try:                                     # pytest imports the package
    from character_library import character_library as CL  # noqa: E402
    from character_library import migration_plan as MIG    # noqa: E402
except ImportError:                      # a script run gets the module files
    import character_library as CL       # noqa: E402
    import migration_plan as MIG         # noqa: E402

from choice_card.intake_card import intake_card as IC      # noqa: E402
from choice_card.intake_card import intake_session as IS   # noqa: E402


def tree_snapshot(root):
    """Every file under root, path -> sha256. The byte baseline for a round trip."""
    out = {}
    for current, dirs, files in os.walk(root):
        dirs.sort()
        for name in sorted(files):
            path = os.path.join(current, name)
            with open(path, "rb") as handle:
                out[os.path.relpath(path, root)] = hashlib.sha256(
                    handle.read()).hexdigest()
    return out


class MigrationPlan(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.client = os.path.join(self.tmp, "client-a")
        self.runs = os.path.join(self.tmp, "runs")
        self.images = []
        for name, payload in (("maya.png", b"\x89PNG-maya-bytes"),
                              ("dre.png", b"\x89PNG-dre-bytes")):
            path = os.path.join(self.tmp, name)
            with open(path, "wb") as handle:
                handle.write(payload)
            self.images.append(path)
        CL.save_character(self.client, "Maya Lee", "Warm, 40s, silver braids.",
                          [self.images[0]], "Low, calm alto",
                          background="Ohio", ethnicity="Black")
        CL.save_character(self.client, "Dre", "Sharp suit, calm voice.",
                          [self.images[1]], "Mid baritone")
        # Dre's slug sorts first, so the offer is 2 = Use Dre, 3 = Use Maya Lee.
        self.session_path = self._answer_saved_pick(2)

    # --- the real writers this test reads -------------------------------
    def _answer_saved_pick(self, pick):
        questions = IC._with_saved_character(self.client)
        by_id = {q["id"]: q for q in questions}
        state = IS.process([], questions, run_dir=self.runs,
                           client_dir=self.client)
        for _step in range(30):
            pending = state.get("pending") or {}
            question_id = pending.get("id")
            if question_id is None:
                break
            question = by_id.get(question_id, {})
            if question_id == "saved_character":
                reply = str(pick)
            elif question_id == "spend":
                reply = "$25"
            elif question.get("free_text"):
                reply = "Sweet Details Cookie-Decorating Class"
            else:
                reply = "recommended"
            state = IS.process([reply], questions, run_dir=self.runs,
                               client_dir=self.client)
            if question_id == "saved_character":
                break
        return os.path.join(self.runs, "control", "intake-session.json")

    def _plan(self):
        return MIG.build_plan(self.client, runs_root=self.runs)

    def _mapped(self, plan):
        return {r["content"]["name"]: r for r in plan["records"]
                if r["status"] == "MAPPED"}

    # --- clause: actual local records -----------------------------------
    def test_discovers_actual_save_list_and_reuse_records(self):
        plan = self._plan()
        self.assertEqual(plan["schema"], MIG.PLAN_SCHEMA)
        self.assertEqual(plan["counts"]["records"], 2)
        self.assertEqual(plan["counts"]["mapped"], 2)
        self.assertEqual(sorted(self._mapped(plan)), ["Dre", "Maya Lee"])
        # the list record is the offer the card really rendered, positions included
        labels = [o["label"] for o in plan["list_record"]["offered"]]
        self.assertEqual(labels, ["Create a new character", "Use Dre", "Use Maya Lee"])
        self.assertEqual([o["position"] for o in plan["list_record"]["offered"]], [1, 2, 3])
        # the reuse record is the real session answer
        self.assertEqual(plan["counts"]["reuse_resolved"], 1)
        reference = plan["reuse"][0]
        with open(self.session_path, encoding="utf-8") as handle:
            session = json.load(handle)
        saved = session["answer_records"]["saved_character"]
        self.assertEqual(reference["question_id"], "saved_character")
        self.assertEqual(reference["raw_answer"], "2")
        self.assertEqual(reference["option_number"], saved["option"]["number_shown"])
        self.assertEqual(reference["option_label"], "Use Dre")
        self.assertEqual(reference["old_slug"], "dre")
        self.assertEqual(reference["status"], "RESOLVED")
        self.assertEqual(plan["history"][0]["session_digest"],
                         reference["session_digest"])
        self.assertEqual(plan["history"][0]["events"], len(session["events"]))

    # --- clause: content/identity provenance ----------------------------
    def test_provenance_is_content_and_identity_not_a_bare_id(self):
        plan = self._plan()
        maya = self._mapped(plan)["Maya Lee"]
        self.assertTrue(maya["new_id"].startswith("ch-"))
        self.assertEqual(len(maya["new_id"]), 27)
        self.assertEqual(maya["legacy_ids"], ["slug:maya-lee", "name:Maya Lee"])
        evidence = maya["identity_evidence"]
        self.assertEqual(evidence["record_schema"], MIG.LEGACY_RECORD_SCHEMA)
        self.assertTrue(evidence["folder_matches_slug"])
        self.assertEqual(evidence["slug_derived_from_name"], "maya-lee")
        record_path = os.path.join(self.client, "character-library", "maya-lee",
                                   "character.json")
        self.assertEqual(evidence["character_json_digest"],
                         MIG._file_digest(record_path))
        with open(self.images[0], "rb") as handle:
            expected = "sha256:" + hashlib.sha256(handle.read()).hexdigest()
        self.assertEqual(evidence["reference_images"][0]["digest"], expected)
        self.assertIn("reference image digest", evidence["proved_by"])
        # the ID is derived from content + slug, so a content change is a new ID
        other = MIG.new_identity(maya["content_digest"], "maya-lee")
        self.assertEqual(other, maya["new_id"])
        changed = dict(maya["content"], description="Different person entirely.")
        new_digest = MIG.content_digest(changed, [r["digest"] for r in
                                                 evidence["reference_images"]])
        self.assertNotEqual(MIG.new_identity(new_digest, "maya-lee"), maya["new_id"])
        # and the same record plans to the same ID on a second read
        self.assertEqual(self._mapped(self._plan())["Maya Lee"]["new_id"],
                         maya["new_id"])

    # --- clause: dry run by default -------------------------------------
    def test_dry_run_writes_nothing(self):
        before = tree_snapshot(self.client)
        plan = self._plan()
        self.assertTrue(plan["dry_run"])
        self.assertEqual(plan["plan_digest"], self._plan()["plan_digest"])
        self.assertFalse(os.path.exists(plan["migration_dir"]))
        self.assertEqual(tree_snapshot(self.client), before)

    # --- clause: nothing destructive without confirmation ---------------
    def test_apply_requires_explicit_confirmation(self):
        plan = self._plan()
        before = tree_snapshot(self.client)
        with self.assertRaises(MIG.ConfirmationRequired):
            MIG.apply(plan)
        with self.assertRaises(MIG.ConfirmationRequired):
            MIG.apply(plan, confirm="yes")
        with self.assertRaises(MIG.ConfirmationRequired):
            MIG.reverse(self.client)
        self.assertEqual(tree_snapshot(self.client), before)

    # --- clause: reversible, byte compared ------------------------------
    def test_apply_reverse_round_trip_is_byte_identical(self):
        before = tree_snapshot(self.client)
        plan = self._plan()
        result = MIG.apply(plan, confirm=True)
        self.assertEqual(result["status"], "APPLIED")
        self.assertEqual(len(result["mapped_new"]), 2)
        after_apply = tree_snapshot(self.client)
        self.assertNotEqual(after_apply, before)
        self.assertTrue(all(os.sep + MIG.MIGRATION_DIRNAME + os.sep in rel
                            for rel in set(after_apply) - set(before)))
        self.assertEqual(set(before) - set(after_apply), set())   # nothing removed
        verification = MIG.verify(self.client)
        self.assertTrue(verification["ok"], verification)
        self.assertEqual(verification["records_checked"], 2)
        self.assertEqual(verification["references_resolved"], 1)
        reversed_run = MIG.reverse(self.client, confirm=True)
        self.assertEqual(reversed_run["status"], "REVERSED")
        self.assertEqual(tree_snapshot(self.client), before)

    # --- clause: references and history preserved -----------------------
    def test_references_and_history_survive_migration(self):
        with open(self.session_path, "rb") as handle:
            session_bytes = handle.read()
        plan = self._plan()
        MIG.apply(plan, confirm=True)
        with open(self.session_path, "rb") as handle:
            self.assertEqual(handle.read(), session_bytes)
        with open(os.path.join(plan["migration_dir"], "id-map.json"),
                  encoding="utf-8") as handle:
            id_map = json.load(handle)
        with open(os.path.join(plan["migration_dir"], "references.json"),
                  encoding="utf-8") as handle:
            references = json.load(handle)
        with open(os.path.join(plan["migration_dir"], "history.json"),
                  encoding="utf-8") as handle:
            history = json.load(handle)
        self.assertEqual(len(history["sessions"]), 1)
        self.assertEqual(history["sessions"][0]["session_digest"],
                         MIG._file_digest(self.session_path))
        with open(self.session_path, encoding="utf-8") as handle:
            session = json.load(handle)
        self.assertEqual(history["sessions"][0]["events"], len(session["events"]))
        dre = self._mapped(plan)["Dre"]
        self.assertEqual(MIG.resolve(id_map, "use:Use Dre"), dre["new_id"])
        self.assertEqual(MIG.resolve(id_map, "slug:dre"), dre["new_id"])
        self.assertEqual(MIG.resolve(id_map, "name:Dre"), dre["new_id"])
        entry = references["references"][0]
        self.assertEqual(entry["old_id"], "use:Use Dre")
        self.assertEqual(entry["new_id"], dre["new_id"])
        self.assertEqual(entry["status"], "RESOLVED")
        # the reference resolves to a record that is still on disk, unchanged
        target = os.path.join(self.client, "character-library", "dre", "character.json")
        self.assertTrue(os.path.isfile(target))
        with open(target, encoding="utf-8") as handle:
            self.assertEqual(json.load(handle)["name"], "Dre")
        self.assertEqual(CL.get_character(self.client, "Dre")["description"],
                         "Sharp suit, calm voice.")
        self.assertTrue(MIG.verify(self.client)["ok"])

    # --- clause: old IDs mapped once ------------------------------------
    def test_second_apply_maps_nothing_new_and_renumbers_nothing(self):
        plan = self._plan()
        first = MIG.apply(plan, confirm=True)
        identities = sorted(first["mapped_new"])
        snapshot_after_first = tree_snapshot(self.client)
        fresh = self._plan()
        self.assertEqual(fresh["plan_digest"], plan["plan_digest"])
        second = MIG.apply(fresh, confirm=True)
        self.assertEqual(second["status"], "NOOP")
        self.assertFalse(second["applied"])
        self.assertEqual(second["mapped_new"], [])
        self.assertEqual(second["written"], [])
        self.assertEqual(tree_snapshot(self.client), snapshot_after_first)
        with open(os.path.join(plan["migration_dir"], "id-map.json"),
                  encoding="utf-8") as handle:
            id_map = json.load(handle)
        self.assertEqual(sorted(id_map["records"]), identities)
        self.assertEqual(id_map["counts"]["records"], 2)
        self.assertEqual(len(id_map["legacy_ids"]), 5)   # 2 slugs, 2 names, 1 use

    # --- fail closed on unproved identity -------------------------------
    def test_identity_conflict_blocks_the_whole_migration(self):
        path = os.path.join(self.client, "character-library", "maya-lee",
                            "character.json")
        with open(path, encoding="utf-8") as handle:
            record = json.load(handle)
        record["slug"] = "maya-lee-renamed"
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(record, handle, indent=2, sort_keys=True)
        plan = self._plan()
        blocked = [r for r in plan["records"] if r["status"] == "BLOCKED"]
        self.assertEqual(len(blocked), 1)
        self.assertEqual(blocked[0]["reason_code"], "IDENTITY_CONFLICT")
        self.assertEqual(plan["counts"]["blocked"], 1)
        self.assertNotIn("maya-lee-renamed", json.dumps(plan["legacy_ids"]))
        before = tree_snapshot(self.client)
        with self.assertRaises(MIG.MigrationBlocked):
            MIG.apply(plan, confirm=True)
        self.assertEqual(tree_snapshot(self.client), before)

    def test_missing_reference_image_blocks_and_writes_nothing(self):
        os.unlink(os.path.join(self.client, "character-library", "dre",
                               "references", "1-dre.png"))
        plan = self._plan()
        blocked = {r["old_slug"]: r for r in plan["records"]
                   if r["status"] == "BLOCKED"}
        self.assertEqual(blocked["dre"]["reason_code"], "MISSING_REFERENCE_IMAGE")
        before = tree_snapshot(self.client)
        with self.assertRaises(MIG.MigrationBlocked):
            MIG.apply(plan, confirm=True)
        self.assertEqual(tree_snapshot(self.client), before)

    def test_stale_plan_is_refused(self):
        plan = self._plan()
        extra = os.path.join(self.tmp, "extra.png")
        with open(extra, "wb") as handle:
            handle.write(b"\x89PNG-extra")
        CL.save_character(self.client, "Kofi", "New arrival.", [extra])
        before = tree_snapshot(self.client)
        with self.assertRaises(MIG.StalePlan):
            MIG.apply(plan, confirm=True)
        self.assertEqual(tree_snapshot(self.client), before)
        self.assertFalse(os.path.exists(plan["migration_dir"]))
        self.assertEqual(self._plan()["counts"]["mapped"], 3)


if __name__ == "__main__":
    unittest.main()
