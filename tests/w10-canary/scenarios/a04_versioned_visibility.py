#!/usr/bin/env python3
"""a04_versioned_visibility.py — acceptance row A04 (weight 8).

Condition (tests/w10-canary/receipt-mapping.json, row A04, verbatim):
    "script/lyrics/hook versioned-visibility proofs (S75-W10-U1 scenario matrix)"

Proves, against the tree under test:
  * script and lyrics are registered as versioned artifacts, each carrying a
    revision number and the hash of the exact content presented;
  * the approval presentation DISPLAYS those revision labels (a revision the
    client cannot see is not a versioned-visible artifact);
  * the earned song hook is displayed as a named element of the presentation;
  * a changed lyrics revision moves the displayed revision forward and the
    stale revision is no longer displayed;
  * an unchanged script keeps its revision across a lyric edit while the
    hook/lyrics revision advances — changed and unchanged content are told
    apart, not blanket-bumped;
  * a changed hook is what the presentation shows (no stale hook text).

Every assertion is a real code path of the tree under test. Nothing is sent,
paid, or written outside a /tmp fixture.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _harness as H  # noqa: E402

ROW = "a04"
TITLE = "script/lyrics/hook versioned-visibility"

HOOK1 = "do it for the ones who stayed"
HOOK2 = "we did it for the ones who stayed"

STORY = [("Act 1", ["A woman opens a shop on her own street."]),
         ("Act 2", ["The first winter nearly closes it."])]


def sheet(hook_line):
    return [
        {"tag": "Verse 1", "delivery": "sung",
         "lines": ["I built this from nothing", "with my own two hands"]},
        {"tag": "Hook", "delivery": "sung", "lines": [hook_line]},
        {"tag": "Verse 2", "delivery": "sung",
         "lines": ["The sign went up in the rain", "and I still stood there"]},
        {"tag": "Hook", "delivery": "sung", "lines": [hook_line]},
    ]


def lyrics_of(sh):
    return "\n".join("\n".join(s["lines"]) for s in sh)


def joined(messages):
    return "\n".join(messages or [])


def scenario(core, muts=frozenset()):
    # selftest runs every mutation in this one process; drop the product
    # modules first so no patch from an earlier mutation leaks into the next.
    for name in [n for n in list(sys.modules)
                 if n.split(".")[0] in ("script_approval", "script_pdf")]:
        del sys.modules[name]
    SA = H.load_pkg(core, "script_approval.script_approval")
    AE = H.load_pkg(core, "script_approval.approval_events")
    SP = H.load_pkg(core, "script_pdf.script_pdf")

    # Deliberate PRODUCT defects: each one damages a rule the row measures, so
    # the assertion has to read the product to notice. None of them edits a
    # fixture the assertion compares against.
    if "presentation_drops_revisions" in muts:
        real_render = SA.render_presentation
        SA.render_presentation = (
            lambda *a, **kw: real_render(*a, **dict(kw, labels=None)))
    if "presentation_unnames_earned_hook" in muts:
        real_render = SA.render_presentation
        SA.render_presentation = (
            lambda *a, **kw: real_render(*a, **kw).replace(
                "EARNED SONG HOOK", "SONG HOOK"))
    if "blanket_revision_bump" in muts:
        real_register = AE.register_artifact

        def blanket(rec, kind, sha256, revision=None):
            cur = (rec.get("artifacts") or {}).get(kind) or {}
            if revision is None and cur.get("sha256") == sha256:
                bump = int(cur.get("revision") or 0) + 1
                rec["artifacts"][kind] = dict(cur, revision=bump)
                return {"changed": True, "kind": kind, "revision": bump,
                        "invalidated": []}
            return real_register(rec, kind, sha256, revision)

        AE.register_artifact = blanket
    if "gate_always_open" in muts:
        SA.check_script_approval = lambda record, lyrics: None
    if "stale_revision_accepted" in muts:
        real_load = SP.load_approved_source

        def accepts_stale(*a, **kw):
            return dict(real_load(*a, **kw), ok=True, reason_code="OK")

        SP.load_approved_source = accepts_stale
    if "presentation_drops_labels_and_hook" in muts:
        real_render = SA.render_presentation

        def muted(*a, **kw):
            out, skipping = [], False
            for line in real_render(*a, **kw).splitlines():
                if line.strip() == "EARNED SONG HOOK":
                    skipping = True
                    continue
                if skipping and line.strip() == "ERM DROP":
                    skipping = False
                if (skipping or "revision" in line.lower()
                        or HOOK1 in line or HOOK2 in line):
                    continue
                out.append(line)
            return "\n".join(out)

        SA.render_presentation = muted
    if "stale_revision_label" in muts:
        real_render = SA.render_presentation
        SA.render_presentation = (
            lambda *a, **kw: real_render(*a, **kw)
            + "\nLyrics revision 1 (deadbeef)")
    if "stale_hook_shown" in muts:
        real_render = SA.render_presentation
        SA.render_presentation = (
            lambda *a, **kw: real_render(*a, **kw) + "\n" + HOOK1)
    if "revisions_start_at_seven" in muts:
        real_register = AE.register_artifact
        AE.register_artifact = (
            lambda rec, kind, sha256, revision=None:
            real_register(rec, kind, sha256, revision=7))
    if "revisions_never_advance" in muts:
        real_register = AE.register_artifact
        AE.register_artifact = (
            lambda rec, kind, sha256, revision=None:
            real_register(rec, kind, sha256, revision=1))
    if "ask_records_wrong_revisions" in muts:
        real_ask = AE.open_ask

        def wrong_ask(rec, kinds, message_id=None, ask_id=None):
            ask = real_ask(rec, kinds, message_id=message_id, ask_id=ask_id)
            ask["revisions"] = {k: 99 for k in ask.get("kinds") or []}
            return ask

        AE.open_ask = wrong_ask
    if "approval_never_opens" in muts:
        SA.check_script_approval = (
            lambda record, lyrics: {"reason_code": SA.REASON,
                                    "detail": "defect: the gate never opens"})
    if "approval_never_recloses" in muts:
        SA.check_script_approval = lambda record, lyrics: None
    if "approval_hash_ignored" in muts:
        AE.active_approval = (
            lambda rec, kind, sha256=None: {"state": "active", "kind": kind})
    if "stale_source_accepted" in muts:
        SP.load_approved_source = (
            lambda run_dir, approval=None, doc=None:
            {"ok": True, "detail": "defect: stale source accepted"})
    if "record_unreadable" in muts:
        AE.load_record = lambda run_dir: ("corrupt", AE._new_record())

    c = H.Checks(ROW, TITLE)
    print("A04 %s — tree %s%s"
          % (TITLE, core, (" [defect: %s]" % ",".join(sorted(muts)))
             if muts else ""))

    hook1 = "do it for the ones who stayed"
    hook2 = "we did it for the ones who stayed"
    sh1 = sheet(hook1)
    lyr1 = lyrics_of(sh1)
    ctx = {"run_id": "runA04", "tenant_id": "tenantA04",
           "conversation_id": "convA04", "channel": "canary"}

    with H.Scratch() as run_dir:
        msg1 = SA.request_approval(str(run_dir), "The Corner Shop", STORY,
                                   sh1, lyr1, context=ctx)
        state, rec = AE.load_record(str(run_dir))
        art = rec.get("artifacts") or {}
        c.check("a04:record-readable", state == "ok", "state=%s" % state)
        c.check("a04:script-registered-rev1",
                (art.get("script") or {}).get("revision") == 1
                and bool((art.get("script") or {}).get("sha256")),
                "script=%s" % ((art.get("script") or {}).get("revision"),))
        c.check("a04:lyrics-registered-rev1",
                (art.get("lyrics") or {}).get("revision") == 1
                and (art.get("lyrics") or {}).get("sha256") == SA.lyrics_sha(lyr1),
                "lyrics=%s" % ((art.get("lyrics") or {}).get("revision"),))

        text1 = joined(msg1)
        c.check("a04:presentation-displays-both-revisions",
                "Script revision 1" in text1 and "Lyrics revision 1" in text1,
                "labels shown: %s" % [l for l in text1.splitlines()
                                      if "revision" in l.lower()])
        c.check("a04:hook-displayed-as-named-element",
                "EARNED SONG HOOK" in text1 and hook1 in text1,
                "hook line present=%s" % (hook1 in text1))

        ask = (rec.get("asks") or [{}])[-1]
        c.check("a04:ask-binds-displayed-revisions",
                ask.get("revisions") == {"script": 1, "lyrics": 1},
                "ask.revisions=%s" % (ask.get("revisions"),))

        # --- a lyric-only edit: lyrics advance, script must NOT move ---------
        sh2 = [dict(s) for s in sh1]
        sh2[2] = {"tag": "Verse 2", "delivery": "sung",
                  "lines": ["The sign went up in the pouring rain",
                            "and I still stood there"]}
        lyr2 = lyrics_of(sh2)
        msg2 = SA.request_approval(str(run_dir), "The Corner Shop", STORY,
                                   sh2, lyr2, context=ctx)
        _, rec2 = AE.load_record(str(run_dir))
        art2 = rec2.get("artifacts") or {}
        c.check("a04:lyrics-revision-advances",
                (art2.get("lyrics") or {}).get("revision") == 2
                and (art2.get("lyrics") or {}).get("sha256") != art["lyrics"]["sha256"],
                "lyrics rev=%s" % ((art2.get("lyrics") or {}).get("revision"),))
        c.check("a04:unchanged-script-keeps-revision",
                (art2.get("script") or {}).get("revision") == 1
                and (art2.get("script") or {}).get("sha256") == art["script"]["sha256"],
                "script rev=%s" % ((art2.get("script") or {}).get("revision"),))

        text2 = joined(msg2)
        c.check("a04:new-revision-displayed",
                "Lyrics revision 2" in text2,
                "labels shown: %s" % [l for l in text2.splitlines()
                                      if "revision" in l.lower()])
        c.check("a04:stale-revision-not-displayed",
                "Lyrics revision 1" not in text2,
                "stale label present=%s" % ("Lyrics revision 1" in text2))

        # --- a hook change: the presented hook is the new one ---------------
        sh3 = sheet(hook2)
        lyr3 = lyrics_of(sh3)
        msg3 = SA.request_approval(str(run_dir), "The Corner Shop", STORY,
                                   sh3, lyr3, context=ctx)
        _, rec3 = AE.load_record(str(run_dir))
        art3 = rec3.get("artifacts") or {}
        text3 = joined(msg3)
        c.check("a04:hook-change-advances-lyrics-revision",
                (art3.get("lyrics") or {}).get("revision") == 3,
                "lyrics rev=%s" % ((art3.get("lyrics") or {}).get("revision"),))
        c.check("a04:changed-hook-displayed",
                hook2 in text3,
                "new hook present=%s" % (hook2 in text3))
        c.check("a04:stale-hook-not-displayed",
                hook1 not in text3,
                "old hook present=%s" % (hook1 in text3))

        # --- SC-05: a lyrics edit AFTER approval re-closes the boundary -----
        # Everything above only REQUESTED approval. Approve this exact revision
        # here so both directions can be asserted: the gate is open for the
        # approved lyrics and shut for an edited revision, and the refusal names
        # both hashes. A blanket refusal would fail the first check.
        AE.record_decision(rec3, ["script", "lyrics"],
                           dict(ctx, approved_by="client",
                                reply_to_message_id="m-approve-sc05"))
        AE.project(rec3, SA.lyrics_sha(lyr3))
        AE.save_record(str(run_dir), rec3)
        _, rec4 = AE.load_record(str(run_dir))

        still_open = SA.check_script_approval(rec4, lyr3)
        c.check("a04:approval-open-for-approved-lyrics",
                still_open is None,
                "refusal=%s at the approved revision" % (still_open,))

        sh4 = [dict(s) for s in sh3]
        sh4[2] = {"tag": "Verse 2", "delivery": "sung",
                  "lines": ["The sign went up in the freezing rain",
                            "and I still stood there"]}
        lyr4 = lyrics_of(sh4)
        closed = SA.check_script_approval(rec4, lyr4)
        c.check("a04:lyrics-edit-recloses-approval",
                isinstance(closed, dict)
                and closed.get("reason_code") == SA.REASON,
                "reason=%s after the edit"
                % ((closed or {}).get("reason_code"),))

        live = AE.active_approval(rec4, "lyrics", SA.lyrics_sha(lyr4))
        recorded = AE.active_approval(rec4, "lyrics", SA.lyrics_sha(lyr3))
        c.check("a04:lyrics-approval-hash-mismatch-recorded",
                live is None and recorded is not None
                and SA.lyrics_sha(lyr3) != SA.lyrics_sha(lyr4),
                "active_for_edit=%s recorded=%s edit=%s"
                % (live is not None, str(SA.lyrics_sha(lyr3))[:12],
                   str(SA.lyrics_sha(lyr4))[:12]))

        stale = SP.load_approved_source(
            str(run_dir), approval=rec4,
            doc={"title": "The Corner Shop",
                 "story": [list(a) for a in STORY],
                 "sheet": sh4, "lyrics": lyr4})
        detail = str(stale.get("detail") or "")
        c.check("a04:lyrics-hash-mismatch-refused-by-name",
                stale.get("ok") is False
                and stale.get("reason_code") == SP.REASON_STALE
                and SA.lyrics_sha(lyr3)[:12] in detail
                and SA.lyrics_sha(lyr4)[:12] in detail,
                "code=%s detail=%s" % (stale.get("reason_code"), detail[:160]))

        return c

# --------------------------------------------------------------------------
# selftest — deliberate product defects must turn the named assertions RED
# --------------------------------------------------------------------------
MUTATIONS = {
    "presentation_drops_revisions": [
        "a04:presentation-displays-both-revisions",
        "a04:new-revision-displayed",
    ],
    "presentation_unnames_earned_hook": [
        "a04:hook-displayed-as-named-element",
    ],
    "blanket_revision_bump": [
        "a04:unchanged-script-keeps-revision",
    ],
    "gate_always_open": [
        "a04:lyrics-edit-recloses-approval",
    ],
    "stale_revision_accepted": [
        "a04:lyrics-hash-mismatch-refused-by-name",
    ],
    "presentation_drops_labels_and_hook": [
        "a04:presentation-displays-both-revisions",
        "a04:hook-displayed-as-named-element",
        "a04:new-revision-displayed",
        "a04:changed-hook-displayed",
    ],
    "stale_revision_label": [
        "a04:stale-revision-not-displayed",
    ],
    "stale_hook_shown": [
        "a04:stale-hook-not-displayed",
    ],
    "revisions_start_at_seven": [
        "a04:script-registered-rev1",
        "a04:lyrics-registered-rev1",
        "a04:unchanged-script-keeps-revision",
    ],
    "revisions_never_advance": [
        "a04:lyrics-revision-advances",
        "a04:hook-change-advances-lyrics-revision",
    ],
    "ask_records_wrong_revisions": [
        "a04:ask-binds-displayed-revisions",
    ],
    "approval_never_opens": [
        "a04:approval-open-for-approved-lyrics",
    ],
    "approval_never_recloses": [
        "a04:lyrics-edit-recloses-approval",
    ],
    "approval_hash_ignored": [
        "a04:lyrics-approval-hash-mismatch-recorded",
    ],
    "stale_source_accepted": [
        "a04:lyrics-hash-mismatch-refused-by-name",
    ],
    "record_unreadable": [
        "a04:record-readable",
    ],
}

def selftest(core):
    ok = True
    for name in sorted(MUTATIONS):
        c = scenario(core, frozenset([name]))
        failed = [r["name"] for r in c.failed()]
        expected = MUTATIONS[name]
        hit = [e for e in expected if e in failed]
        good = len(hit) == len(expected) and bool(failed)
        ok = ok and good
        print("selftest:%s — %s; red=%s"
              % (name, "RED as required" if good else "DID NOT FAIL AS EXPECTED",
                 failed or "none"))
        print("selftest:%s — expected hit=%d/%d"
              % (name, len(hit), len(expected)))
    print("selftest — %s" % ("harness fails on all %d defects" % len(MUTATIONS)
                             if ok else "HARNESS CANNOT PROVE A FAILURE"))
    return 0 if ok else 1


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    selftest_mode = bool(argv) and argv[0] == "selftest"
    args = H.add_args(
        description="a04 selftest" if selftest_mode else __doc__
    ).parse_args(argv[1:] if selftest_mode else argv)
    core = H.resolve_core(args)
    if selftest_mode:
        return selftest(core)
    return scenario(core).finish(args.out)


if __name__ == "__main__":
    sys.exit(main())
