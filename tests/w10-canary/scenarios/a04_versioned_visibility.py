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


def main(argv=None):
    args = H.add_args(description=__doc__).parse_args(argv)
    core = H.resolve_core(args)
    SA = H.load_pkg(core, "script_approval.script_approval")
    AE = H.load_pkg(core, "script_approval.approval_events")
    c = H.Checks(ROW, TITLE)
    print("A04 %s — tree %s" % (TITLE, core))

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

        return c.finish(args.out)


if __name__ == "__main__":
    sys.exit(main())
