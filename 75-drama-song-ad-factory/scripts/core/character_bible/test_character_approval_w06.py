#!/usr/bin/env python3
"""W06-U1: the CHARACTER BIBLE approval boundary.

Run: python3 test_character_approval_w06.py  (or under unittest/pytest)

Generic fixture characters only -- no client names anywhere. The suite proves
the acceptance, end to end on the real run directory:

  * each character card shows name, role, background, appearance, the
    voice/performance notes AND the actual reference pictures, presented in
    the ORIGINATING conversation as the typed artifact envelope;
  * the approval event is VERSIONED and bound to the bible revision and every
    image hash, and it wires AUTOMATIC continuation (durable queue entry in
    the same transaction boundary, restart scan, replay without duplicate
  * work);
  * the invalidation matrix is verified: unchanged character images retain
    approval across unrelated lyric edits, and a revision blocks ONLY the
    downstream work its own dependency class feeds;
  * character work proceeds alongside the script and never waits behind a
    broken music stage;
  * locked character references cannot feed dependent production before the
    approval event.
"""
import json
import os
import shutil
import struct
import sys
import tempfile
import unittest
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
for _p in (CORE, os.path.join(CORE, "character_bible")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from character_bible import character_approval as CA  # noqa: E402
from character_bible import character_bible as CB      # noqa: E402
from choice_card.intake_card import delivery_outbox as DO  # noqa: E402
import state_store  # noqa: E402


def _png(path, w=24, h=32, rgb=(180, 60, 60)):
    raw = b"".join(b"\x00" + bytes(rgb) * w for _ in range(h))

    def chunk(kind, data):
        return (struct.pack(">I", len(data)) + kind + data
                + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF))

    with open(path, "wb") as fh:
        fh.write(b"\x89PNG\r\n\x1a\n"
                 + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                 + chunk(b"IDAT", zlib.compress(raw))
                 + chunk(b"IEND", b""))
    return path


#: Generic fixture cast. Never a client.
def _entries(img_dir, rgb=(180, 60, 60)):
    def four(stem, color):
        return {view: _png(os.path.join(img_dir, "%s-%s.png" % (stem, view)),
                           rgb=color)
                for view in ("close-up", "side-profile", "three-quarter",
                             "full-standing")}
    return [
        {"name": "Sample Character", "role": "protagonist",
         "background": "Grew up in a small coastal town and ran the family shop.",
         "appearance": "Medium-brown skin, short coily hair, a broad easy smile.",
         "voice_notes": "Low, unhurried, warm. Sings the verses plainly.",
         "images": four("sample", rgb)},
        {"name": "Rival Character", "role": "villain",
         "background": "Came up through the city trade and never forgives a slight.",
         "appearance": "Tall, sharp suit, silver at the temples, quick eyes.",
         "voice_notes": "Bright, clipped, sardonic. Pushes every hook.",
         "images": four("rival", (60, 60, 180))},
    ]


class ApprovalBoundary(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.mkdtemp(prefix="s75w06u1-")
        self.run = os.path.join(self.t, "run-1")
        self.imgs = os.path.join(self.t, "imgs")
        os.makedirs(self.run)
        os.makedirs(self.imgs)
        self.entries = _entries(self.imgs)
        self.sent = []                      # the conversation sink
        DO.save_origin(self.run, DO.origin_record(
            tenant_id="tenant-7", account_id="bot-7", channel="app",
            conversation_id="conv-7", thread_id="thread-7"))
        CA.save_bible(self.run, CA.bible_from_entries(self.entries))

    def tearDown(self):
        shutil.rmtree(self.t, ignore_errors=True)

    # -- helpers ----------------------------------------------------------
    def _send(self, message, images):
        self.sent.append((message, list(images)))

    def _present(self):
        return CA.present(self.run, send=self._send, run_id="run-1")

    def _approve(self, reply="approve", by="client-7"):
        return CA.approve(self.run, reply, approved_by=by, run_id="run-1")

    def _rewrite_image(self, entry_i=0, view="close-up", rgb=(10, 200, 10)):
        path = self.entries[entry_i]["images"][view]
        _png(path, rgb=rgb)

    # -- presentation -----------------------------------------------------
    def test_card_shows_all_fields_and_actual_images(self):
        p = self._present()
        card = p["messages"][0]
        for label in ("Name: Sample Character", "Role: protagonist",
                      "Background: Grew up in a small coastal town",
                      "Appearance: Medium-brown skin",
                      "Voice / performance notes: Low, unhurried, warm"):
            self.assertIn(label, card)
        # the ACTUAL generated or selected reference images, each hashed
        self.assertEqual(len(p["attachments"]), 8)      # 2 characters x 4 views
        for caption, path in p["attachments"]:
            self.assertTrue(os.path.isfile(path), path)
            self.assertGreater(os.path.getsize(path), 0)
        env = p["envelope"]
        self.assertEqual(len(env["presentation"]["attachments"]), 8)
        for att in env["presentation"]["attachments"]:
            self.assertTrue(att["sha256"])
            self.assertTrue(att["path"])

    def test_presentation_is_in_the_originating_conversation(self):
        p = self._present()
        env = p["envelope"]
        self.assertEqual(env["artifact_kind"], "character_bible")
        self.assertEqual(env["origin"]["channel"], "app")
        self.assertEqual(env["origin"]["conversation_id"], "conv-7")
        self.assertEqual(env["origin"]["thread_id"], "thread-7")
        self.assertEqual(env["tenant_id"], "tenant-7")
        self.assertEqual(env["approval"],
                         {"state": "pending", "allowed_actions": ["approve", "revise"]})
        # the typed envelope is queued in the durable outbox: prepared is not
        # sent, and every piece carries its own identity and payload hash
        pieces = DO.Outbox(self.run).pieces()
        self.assertTrue(pieces)
        kinds = {p_["kind"] for p_ in pieces}
        self.assertEqual(kinds, {"text", "attachment"})
        self.assertTrue(all(p_["state"] == DO.QUEUED for p_ in pieces))
        self.assertTrue(all(p_["payload_sha256"] for p_ in pieces))

    def test_images_travel_with_their_own_card(self):
        self._present()
        card1 = next(m for m, _ in self.sent if "Sample Character" in m)
        card2 = next(m for m, _ in self.sent if "Rival Character" in m)
        imgs1 = [i for m, i in self.sent if m is card1][0]
        imgs2 = [i for m, i in self.sent if m is card2][0]
        self.assertEqual(len(imgs1), 4)
        self.assertEqual(len(imgs2), 4)
        self.assertTrue(all("Sample Character" in c for c, _ in imgs1))
        self.assertTrue(all("Rival Character" in c for c, _ in imgs2))

    def test_presentation_refuses_a_missing_picture(self):
        os.remove(self.entries[0]["images"]["side-profile"])
        with self.assertRaises(CA.ApprovalError) as caught:
            self._present()
        self.assertIn("IMAGE_MISSING", str(caught.exception))
        self.assertIn("side-profile", str(caught.exception))

    # -- the versioned approval event ------------------------------------
    def test_approval_event_binds_revision_and_image_hashes(self):
        self._present()
        res = self._approve()
        ev = res["event"]
        self.assertEqual(ev["status"], "approved")
        self.assertEqual(ev["artifact_kind"], "character_bible")
        self.assertEqual(ev["bible_revision"], 1)
        self.assertEqual(ev["presentation_version"], 1)
        self.assertEqual(ev["tenant_id"], "tenant-7")
        self.assertEqual(ev["run_id"], "run-1")
        self.assertEqual(ev["origin"]["conversation_id"], "conv-7")
        self.assertEqual(ev["approved_by"], "client-7")
        self.assertGreater(ev["at"], 0)
        hashes = ev["image_hashes"]["sample-character"]
        self.assertEqual(set(hashes), {"close-up", "side-profile",
                                       "three-quarter", "full-standing"})
        for view, sha in hashes.items():
            self.assertEqual(sha, CA.sha256_file(self.entries[0]["images"][view]))
        # and the gate opens for every class
        for lock in CA.LOCKS:
            self.assertIsNone(CA.check(self.run, need=lock))

    def test_approval_wires_automatic_continuation(self):
        self._present()
        res = self._approve()
        entry = res["continuation"]
        self.assertEqual(entry["state"], "queued")
        self.assertEqual(entry["event"], "character-approved")
        self.assertIn("intake_preflight/factory.py next --run-dir", entry["next_action"])
        self.assertTrue(res["continuation_enqueued"])
        # the run CONTINUES: no "shall I continue?" round trip, just go
        stage = CA.run_stage(self.run, send=self._send)
        self.assertEqual(stage["outcome"], "go")
        self.assertIn("factory.py next --run-dir", stage["next_action"])

    def test_replayed_approval_enqueues_no_duplicate_work(self):
        self._present()
        first = self._approve()
        second = self._approve()
        self.assertTrue(second["replayed"])
        self.assertEqual(second["continuation"]["id"],
                         first["continuation"]["id"])
        entries = CA._continuation_doc(self.run)["entries"]
        self.assertEqual(len(entries), 1)

    def test_unseen_artifact_cannot_be_approved(self):
        res = self._approve()                # nothing presented yet
        self.assertEqual(res["status"], "error")
        self.assertEqual(res["reason_code"], "UNSEEN_ARTIFACT")

    def test_ambiguous_reply_among_several_pending_asks_once(self):
        self._present()
        os.makedirs(os.path.join(self.run, "creative"), exist_ok=True)
        with open(os.path.join(self.run, "creative", "script-approval.json"),
                  "w", encoding="utf-8") as f:
            json.dump({"required": True, "status": "pending"}, f)
        res = self._approve("yes")           # generic: script + character pending
        self.assertEqual(res["status"], CA.CLARIFY)
        self.assertIn("character bible", res["question"])
        res = self._approve("approve the character bible")   # scoped: no question
        self.assertEqual(res["status"], "approved")

    def test_revision_request_round_trips_in_one_stage_call(self):
        self._present()
        seen = {}

        def apply_edit(edit, doc):
            seen["edit"] = edit
            new = json.loads(json.dumps(doc))
            new["characters"][0]["appearance"] = "Taller than last time, same smile."
            return new

        stage = CA.run_stage(self.run, send=self._send, reply="make her taller",
                             apply_edit=apply_edit)
        self.assertEqual(stage["outcome"], "waiting")
        self.assertEqual(stage["reason"], "revised-and-presented")
        self.assertEqual(seen["edit"], "make her taller")
        doc = CA.load_bible(self.run)
        self.assertEqual(doc["revision"], 2)            # a revision is versioned
        self.assertIn("Taller than last time", stage["messages"][0])

    def test_bible_revision_bumps_only_on_content_change(self):
        before = CA.load_bible(self.run)
        again = CA.save_bible(self.run, CA.load_bible(self.run))
        self.assertEqual(again["revision"], before["revision"])
        again["characters"][0]["voice_notes"] = "Still low, now with a rasp."
        bumped = CA.save_bible(self.run, again)
        self.assertEqual(bumped["revision"], before["revision"] + 1)

    # -- the invalidation matrix -----------------------------------------
    def test_lyric_edit_retains_image_approval(self):
        self._present()
        self._approve()
        os.makedirs(os.path.join(self.run, "creative"), exist_ok=True)
        with open(os.path.join(self.run, "creative", "lyrics.json"),
                  "w", encoding="utf-8") as f:
            json.dump({"lines": ["A brand new lyric line nobody approved"]}, f)
        # the bible did not change at all: every class keeps its approval
        self.assertIsNone(CA.check(self.run, need=CA.LOCK_IMAGE))
        self.assertIsNone(CA.check(self.run, need=CA.LOCK_VOICE))
        self.assertIsNone(CA.check(self.run, need=CA.LOCK_IDENTITY))
        self.assertEqual(CA.changes_since_approval(self.run), set())
        self.assertEqual(CA.blocked_downstream({"lyric_edit"}), [])

    def test_image_change_blocks_only_image_downstream(self):
        self._present()
        self._approve()
        self._rewrite_image(0, "close-up")
        self.assertEqual(CA.changes_since_approval(self.run), {"image_bytes"})
        self.assertEqual(CA.blocked_downstream({"image_bytes"}),
                         ["assembly", "continuity-bible", "delivery",
                          "final-qc", "image-keyframes", "qc-retakes",
                          "video-generation"])
        self.assertEqual(CA.retained_locks({"image_bytes"}),
                         [CA.LOCK_VOICE, CA.LOCK_IDENTITY])
        ref = CA.check(self.run, need=CA.LOCK_IMAGE)
        self.assertEqual(ref["reason_code"], CA.REASON_IMAGES_CHANGED)
        self.assertIsNone(CA.check(self.run, need=CA.LOCK_VOICE))
        self.assertIsNone(CA.check(self.run, need=CA.LOCK_IDENTITY))
        with self.assertRaises(CA.ApprovalError) as caught:
            CA.locked_references(self.run)
        self.assertEqual(caught.exception.reason_code, CA.REASON_IMAGES_CHANGED)

    def test_voice_change_blocks_only_voice_downstream(self):
        self._present()
        self._approve()
        doc = CA.load_bible(self.run)
        doc["characters"][0]["voice_notes"] = "Now bright and quick."
        CA.save_bible(self.run, doc)
        self.assertEqual(CA.changes_since_approval(self.run), {"voice_notes"})
        # the bible card itself re-opens; downstream only lip-sync consumes
        # the voice/performance notes
        self.assertEqual(CA.blocked_downstream({"voice_notes"}),
                         ["continuity-bible", "lip-sync"])
        self.assertEqual(CA.retained_locks({"voice_notes"}),
                         [CA.LOCK_IMAGE, CA.LOCK_IDENTITY])
        ref = CA.check(self.run, need=CA.LOCK_VOICE)
        self.assertEqual(ref["reason_code"], CA.REASON_VOICE_CHANGED)
        self.assertIsNone(CA.check(self.run, need=CA.LOCK_IMAGE))
        # the unchanged pictures are still the locked, approved ones
        refs = CA.locked_references(self.run)
        self.assertEqual(len(refs), 2)

    def test_identity_change_blocks_identity_downstream(self):
        self._present()
        self._approve()
        doc = CA.load_bible(self.run)
        doc["characters"][0]["role"] = "foil"
        CA.save_bible(self.run, doc)
        self.assertEqual(CA.changes_since_approval(self.run), {"identity"})
        self.assertEqual(CA.blocked_downstream({"identity"}),
                         ["continuity-bible", "script-lyrics", "storyboard"])
        self.assertEqual(CA.retained_locks({"identity"}),
                         [CA.LOCK_IMAGE, CA.LOCK_VOICE])
        ref = CA.check(self.run, need=CA.LOCK_IDENTITY)
        self.assertEqual(ref["reason_code"], CA.REASON_IDENTITY_CHANGED)
        self.assertIsNone(CA.check(self.run, need=CA.LOCK_IMAGE))

    def test_added_or_removed_character_blocks_everything(self):
        self._present()
        self._approve()
        doc = CA.load_bible(self.run)
        doc["characters"] = doc["characters"][:1]
        CA.save_bible(self.run, doc)
        self.assertEqual(CA.changes_since_approval(self.run),
                         {"character_removed"})
        for change in ("character_removed", "character_added"):
            self.assertEqual(CA.blocked_downstream({change}),
                             sorted(CA.DOWNSTREAM_LOCKS))
            self.assertEqual(CA.retained_locks({change}), [])

    def test_invalidation_matrix_verified(self):
        # the declared matrix, exactly: what each change dirties, what it
        # blocks, what keeps its approval
        self.assertEqual(CA.INVALIDATION_MATRIX["lyric_edit"],
                         {"dirties": [], "blocks": [], "retains_approval":
                          ["image", "voice", "identity"]})
        self.assertEqual(CA.INVALIDATION_MATRIX["image_bytes"]["dirties"],
                         ["image"])
        self.assertNotIn("lip-sync", CA.INVALIDATION_MATRIX["image_bytes"]["blocks"])
        self.assertIn("image-keyframes", CA.INVALIDATION_MATRIX["image_bytes"]["blocks"])
        self.assertEqual(CA.INVALIDATION_MATRIX["voice_notes"]["blocks"],
                         ["continuity-bible", "lip-sync"])
        self.assertEqual(CA.INVALIDATION_MATRIX["appearance"]["dirties"], ["image"])
        self.assertEqual(CA.INVALIDATION_MATRIX["identity"]["blocks"],
                         ["continuity-bible", "script-lyrics", "storyboard"])
        self.assertEqual(CA.INVALIDATION_MATRIX["character_added"]["retains_approval"],
                         [])

    # -- readiness: never behind the music stage -------------------------
    def test_broken_music_stage_does_not_block_character_work(self):
        db = os.path.join(self.run, "control", "state.sqlite3")
        store = state_store.Store(db)
        store.init_run("run-1", ["music", "continuity-bible"])
        for to in ("READY", "RUNNING"):
            store.transition("run-1", "music", to, "music")
        store.transition("run-1", "music", "FAILED_BLOCKED", "music",
                         reason="provider outage")
        self.assertEqual(store.get("run-1", "music")["state"], "FAILED_BLOCKED")
        store.close()
        # character work proceeds alongside the script anyway
        r = CA.ready(self.run)
        self.assertTrue(r["ready"], r["missing"])
        self.assertEqual(r["waits_on"], [])
        self.assertEqual(r["independent_of"], ["music"])
        stage = CA.run_stage(self.run, send=self._send)
        self.assertEqual(stage["outcome"], "waiting")
        res = self._approve()
        self.assertEqual(res["status"], "approved")
        self.assertEqual(CA.run_stage(self.run, send=self._send)["outcome"], "go")

    def test_ready_names_missing_inputs(self):
        doc = CA.load_bible(self.run)
        doc["characters"][0]["background"] = ""
        CA.save_bible(self.run, doc)
        os.remove(self.entries[1]["images"]["three-quarter"])
        r = CA.ready(self.run)
        self.assertFalse(r["ready"])
        self.assertTrue(any("background is not filled in" in m for m in r["missing"]))
        self.assertTrue(any("three-quarter reference picture" in m
                            for m in r["missing"]))
        stage = CA.run_stage(self.run, send=self._send)
        self.assertEqual(stage["outcome"], "blocked")

    def test_stage_contract_declares_the_independence(self):
        c = CA.STAGE_CONTRACT
        self.assertEqual(c["stage"], "continuity-bible")
        self.assertIn("script-lyrics", c["parallel_with"])
        self.assertEqual(c["never_blocks_on"], ("music",))
        self.assertNotIn("music", c["prerequisites"])

    # -- locked references and the restart scan --------------------------
    def test_locked_references_refuses_before_approval(self):
        with self.assertRaises(CA.ApprovalError) as caught:
            CA.locked_references(self.run)
        self.assertEqual(caught.exception.reason_code, CA.REASON_REQUIRED)
        self._present()
        with self.assertRaises(CA.ApprovalError):
            CA.locked_references(self.run)     # presented is not approved
        self._approve()
        refs = CA.locked_references(self.run)
        self.assertEqual([r["name"] for r in refs],
                         ["Sample Character", "Rival Character"])
        self.assertEqual(refs[0]["role"], "protagonist")
        for view, meta in refs[0]["images"].items():
            self.assertTrue(os.path.isfile(meta["path"]))
            self.assertEqual(meta["sha256"], CA.sha256_file(meta["path"]))

    def test_restart_scan_repairs_and_resumes_continuation(self):
        self._present()
        self._approve()
        os.remove(os.path.join(self.run, CA.CONTINUATION_NAME))  # crash window
        r = CA.resume_continuations(self.run)
        self.assertTrue(r["repaired"])
        self.assertEqual(len(r["entries"]), 1)
        self.assertIn("factory.py next --run-dir", r["entries"][0]["next_action"])
        again = CA.resume_continuations(self.run)               # replay-safe
        self.assertFalse(again["repaired"])
        self.assertEqual(len(again["entries"]), 1)

    def test_delivery_of_locked_images_refuses_on_stale_approval(self):
        from delivery_package import contract as DC
        self._present()
        self._approve()
        with open(os.path.join(self.run, "character", "brief.json"),
                  "w", encoding="utf-8") as f:
            json.dump({
                "character_name": "Sample Character",
                "character_description": "A warm, practical person.",
                "character_background": "Grew up in a small coastal town.",
                "character_ethnicity": "Medium-brown skin, short coily hair.",
            }, f)
        self._rewrite_image(0, "close-up")         # approved bytes changed
        # assert by reason_code and class name: under some pytest import modes
        # the delivery module resolves its own instance of the boundary
        # module, so a class-identity assertRaises would be testing the import
        # layout, not the refusal
        try:
            CB.produce_delivery(self.run, DC.ITEMS_BY_KEY["character_bible"])
        except Exception as e:  # noqa: BLE001 - the refusal is what is proven
            self.assertEqual(type(e).__name__, "ApprovalError")
            self.assertEqual(getattr(e, "reason_code", None),
                             CA.REASON_IMAGES_CHANGED)
        else:
            self.fail("stale image approval did not refuse the locked delivery")


if __name__ == "__main__":
    unittest.main(verbosity=1)
