#!/usr/bin/env python3
"""a05_character_bible_approval.py — acceptance row A05 (weight 7).

Condition (tests/w10-canary/receipt-mapping.json, row A05, verbatim):
    "character bible + versioned approve/revise proofs (S75-W10-U1)"

Proves, against the tree under test:
  * the character bible is a saved, fingerprinted document with a revision;
  * its cards are presented in the originating conversation at that revision;
  * dependent work is REFUSED before approval (never a silent pass);
  * a client reply becomes a versioned approval event bound to the bible
    revision and the image hashes, and the gate then opens;
  * a replayed approval is acknowledged as a replay and enqueues no duplicate
    continuation;
  * a non-approval reply is recorded as a revision request (needs-edit), not
    as an approval;
  * revising the bible content bumps the revision and INVALIDATES the prior
    approval — the gate closes again and the downstream stages that consume
    the changed class are named.

No provider, no channel, no paid call; images are 1x1 PNGs written to /tmp.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _harness as H  # noqa: E402

ROW = "a05"
TITLE = "character bible + versioned approve/revise"


def main(argv=None):
    args = H.add_args(description=__doc__).parse_args(argv)
    core = H.resolve_core(args)
    CA = H.load_pkg(core, "character_bible.character_approval")
    c = H.Checks(ROW, TITLE)
    print("A05 %s — tree %s" % (TITLE, core))

    with H.Scratch() as run_dir:
        png = H.tiny_png(run_dir / "fixtures" / "maya-front.png")
        doc = CA.bible_from_entries([{
            "name": "Maya", "role": "shop owner",
            "background": "raised behind the counter of the family shop",
            "appearance": "red apron, hair tied back",
            "voice_notes": "warm alto, unhurried",
            "images": {"front": png},
        }])
        saved = CA.save_bible(str(run_dir), doc)
        c.check("a05:bible-saved-revision-1",
                saved.get("revision") == 1 and bool(saved.get("fingerprint")),
                "revision=%s fingerprint=%s"
                % (saved.get("revision"), str(saved.get("fingerprint"))[:8]))

        # dependent work before approval must be refused by name
        pre = CA.check(str(run_dir))
        c.check("a05:gate-refuses-before-approval",
                isinstance(pre, dict)
                and pre.get("reason_code") == CA.REASON_REQUIRED,
                "reason=%s" % (pre or {}).get("reason_code"))

        pres = CA.present(str(run_dir), send=lambda msg, imgs: None, run_id="runA05")
        c.check("a05:cards-presented-at-revision",
                pres.get("outcome") == "waiting"
                and any("revision 1" in m for m in pres.get("messages") or []),
                "outcome=%s cards=%d" % (pres.get("outcome"),
                                         len(pres.get("messages") or [])))

        ok = CA.approve(str(run_dir), "approve the character bible",
                        approved_by="client", run_id="runA05")
        ev = ok.get("event") or {}
        c.check("a05:approval-is-versioned-event",
                ok.get("status") == CA.APPROVED
                and ev.get("bible_revision") == 1
                and bool(ev.get("image_hashes"))
                and ev.get("approved_by") == "client",
                "status=%s bible_revision=%s"
                % (ok.get("status"), ev.get("bible_revision")))
        c.check("a05:gate-opens-after-approval",
                CA.check(str(run_dir)) is None,
                "refusal=%s" % (CA.check(str(run_dir)),))

        replay = CA.approve(str(run_dir), "approve the character bible",
                            approved_by="client", run_id="runA05")
        c.check("a05:replayed-approval-enqueues-nothing",
                replay.get("status") == CA.APPROVED
                and replay.get("replayed") is True
                and replay.get("continuation_enqueued") is False,
                "replayed=%s enqueued=%s"
                % (replay.get("replayed"), replay.get("continuation_enqueued")))

        revise = CA.approve(str(run_dir), "please make her older",
                            approved_by="client", run_id="runA05")
        c.check("a05:revise-reply-recorded-as-needs-edit",
                revise.get("status") == CA.NEEDS_EDIT,
                "status=%s" % revise.get("status"))

        # revise the bible content: revision must bump and the approval stale
        cur = CA.load_bible(str(run_dir))
        cur["characters"][0]["appearance"] = "grey apron, hair tied back"
        CA.save_bible(str(run_dir), cur)
        after = CA.load_bible(str(run_dir))
        c.check("a05:content-change-bumps-revision",
                after.get("revision") == 2,
                "revision=%s" % after.get("revision"))

        post = CA.check(str(run_dir))
        c.check("a05:gate-closes-on-revised-bible",
                isinstance(post, dict)
                and post.get("reason_code") == CA.REASON_IMAGES_CHANGED,
                "reason=%s" % (post or {}).get("reason_code"))

        changes = CA.changes_since_approval(str(run_dir))
        blocks = CA.blocked_downstream(changes)
        c.check("a05:revision-invalidates-downstream-by-class",
                "appearance" in changes and bool(blocks)
                and "image-keyframes" in blocks,
                "changes=%s blocked=%s" % (sorted(changes), blocks))

        return c.finish(args.out)


if __name__ == "__main__":
    sys.exit(main())
