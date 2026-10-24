#!/usr/bin/env python3
"""S75-T41 harness: replay the two verifiers' receipts against BOTH rules.

Side by side, in-process, one run:

    production      what shipped on the unit branch
                    S75-T06  ``cast_writer._anonymous()``       (branch s75/S75-T06)
                    S75-T07  ``cast_validation._episode_role_ok`` / ``_content_issue``
                    (branch s75/S75-T07)
    proposed        ``real_content.person_name_ok`` / ``story_role_ok`` /
                    ``content_issue``                (this branch)

The existing modules are NEVER edited and never imported from a mutated tree.
They are read out of their own git blobs into a throwaway directory and
imported from there, so this harness works on a clean worktree where neither
file exists on disk.

Replay data comes from the verifiers' own receipts, frozen into
``real_content_replay_s75_t41.json`` by ``_freeze_replay()``'s source data:

    evidence/S75-T06.verdict.reattest.6.json  (round 6, head 1ea7e50dd)
    evidence/S75-T07.verdict.reattest.7.json  (round 4, head 835a2a380)

Usage::

    python3 replay_real_content_s75_t41.py [--repo DIR] [--json OUT]

Exit status is 0 when the proposed rule meets both directions -- every replayed
T06 descriptor refused, every replayed T07 real role accepted -- and 1
otherwise.  It prints the full table either way.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPLAY = os.path.join(_HERE, "real_content_replay_s75_t41.json")

T06_BRANCH = "origin/s75/S75-T06"
T07_BRANCH = "origin/s75/S75-T07"
T06_PATH = "75-drama-song-ad-factory/scripts/core/character_bible/cast_writer.py"
T07_PATH = "75-drama-song-ad-factory/scripts/core/character_bible/cast_validation.py"
CONTRACTS_PATH = "75-drama-song-ad-factory/scripts/core/story_first_contracts.py"

_REAL = "“"


# ---------------------------------------------------------------------------
# read-only import of the production modules
# ---------------------------------------------------------------------------

def _git(repo, *args):
    return subprocess.run(["git", "-C", repo] + list(args),
                          check=True, capture_output=True, text=True).stdout


def _extract(repo, rev, path, outdir, name):
    """Write ``rev:path`` into ``outdir/name.py`` -- read-only use of the blob."""
    src = _git(repo, "show", "%s:%s" % (rev, path))
    dest = os.path.join(outdir, name + ".py")
    with open(dest, "w", encoding="utf-8") as handle:
        handle.write(src)
    return dest


def _load(modname, path):
    spec = importlib.util.spec_from_file_location(modname, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[modname] = module
    spec.loader.exec_module(module)
    return module


def load_production(repo):
    """Import both production modules from their own branches, read-only."""
    tmp = tempfile.mkdtemp(prefix="s75t41-prod-")
    local_core = _HERE
    if local_core not in sys.path:
        sys.path.insert(0, local_core)
    if not os.path.exists(os.path.join(local_core, "story_first_contracts.py")):
        _extract(repo, "origin/main", CONTRACTS_PATH, tmp, "story_first_contracts")
    if tmp not in sys.path:
        sys.path.insert(0, tmp)
    writer = _load("_s75t06_cast_writer",
                   _extract(repo, T06_BRANCH, T06_PATH, tmp, "_s75t06_cast_writer"))
    validation = _load("_s75t07_cast_validation",
                       _extract(repo, T07_BRANCH, T07_PATH, tmp,
                                "_s75t07_cast_validation"))
    return writer, validation, tmp


def load_proposed():
    if _HERE not in sys.path:
        sys.path.insert(0, _HERE)
    import real_content
    return real_content


# ---------------------------------------------------------------------------
# the two rules, behind one signature
# ---------------------------------------------------------------------------

class Production:
    """Production verdicts, expressed as the ACCEPT side of each question."""

    def __init__(self, writer, validation):
        self.writer = writer
        self.validation = validation

    def person(self, value):
        # ``_anonymous`` True means "refused"; the display_name path accepts
        # exactly when it is False.  This is the predicate S75-T06 round 6
        # named as its root cause.
        return not self.writer._anonymous(value)

    def role(self, value):
        return self.validation._episode_role_ok(value)

    def content_issue(self, value, kind):
        return self.validation._content_issue(value, kind)

    def real_content(self, value, kind):
        if kind == "role":
            return self.role(value)
        return self.content_issue(value, kind) is None

    def id_list(self, value):
        return all(self.validation._id_ok(v) for v in value)


class Proposed:
    def __init__(self, module):
        self.m = module

    def person(self, value):
        return self.m.person_name_ok(value)

    def role(self, value):
        return self.m.story_role_ok(value)

    def content_issue(self, value, kind):
        return self.m.content_issue(value, kind)

    def real_content(self, value, kind):
        return self.m.real_content_ok(value, kind)

    def id_list(self, value):
        return all(self.m.id_ok(v) for v in value)


# ---------------------------------------------------------------------------
# T07 replay probes, one per T07 filler row that a content predicate can see
# ---------------------------------------------------------------------------
#: The 64 ``accepted_filler`` rows are all replayed.  Five of them are SCHEMA
#: holes, not content holes -- an entry with no ``text``/``action`` key, a
#: ``line_id`` that is never content-judged, and a placement slot for a scene
#: the group does not list.  A content predicate cannot address those, so they
#: are reported separately as NOT ADDRESSED rather than quietly dropped.
_T07_TEXT = [
    "aei", "aeiou", "eieie", "ueue", "ababab", "abab", "abcabc", "aeaeae",
    "obobob", "tatata", "mamama", "hahaha", "lalala", "yayaya", "tralala",
    "abb", "zoz", "uuuue", "qwertz", "asdfgj", "banana phone banana",
    "aei eau iou", "ababab titit", "zzz abc def ghi", "iрsum",
]

_T07_PROBES = (
    [("text", "cast.immediate_story_function", v) for v in _T07_TEXT]
    + [("text", "scene.sung_lyrics.text", "lalala"),
       ("text", "scene.named_actions.action", "hahaha"),
       ("text", "scene.featured_reactions.reaction", "ababab"),
       ("text", "crowd.location_placement[dead]", "zzz")]
    + [("text_list", "cast.choice_or_consequence", [bad, _REAL])
       for bad in ("x y z", "foo bar baz", "blah blah blah", "a b c",
                   "aaa bbb ccc", "ab​c", "aei")]
    + [("text_list", "cast.choice_or_consequence",
        ["x y z", "a b c", "blah blah blah", _REAL]),
       ("text_list", "crowd.roles", ["x y z", _REAL]),
       ("prose", "crowd.age_range", {"a": "zzz", "b": _REAL}),
       ("prose", "crowd.age_range", {"a": 1, "b": _REAL}),
       ("prose", "crowd.age_range", {"a": {"b": "zzz"}, "c": {"d": _REAL}}),
       ("prose", "crowd.age_range", {"a": ["x y z", _REAL]}),
       ("prose", "crowd.age_range", {"a": "", "b": _REAL}),
       ("prose", "crowd.age_range", {"a": "blah blah blah", "b": _REAL}),
       ("prose", "cast.identity_revision", {"a": "zzz", "b": _REAL}),
       ("prose", "cast.identity_revision", {"a": 1, "b": _REAL}),
       ("prose", "cast.identity_revision", -7)]
    + [("id", "cast.identity_digest", v) for v in
       ("lorem-1", "tbd-1", "none-1", "test-1", "placeholder-1", "zzz1",
        "abc123", "aaa.aaa", "aaa-aaa-aaa", "aaaaab", "x1x")]
    + [("id_list", "cast.scene_ids", ["zzz1"])]
)

#: Dressings the T06 verifier applied around every head.  The production bug
#: was DRESSING-dependent, so the replay applies them too rather than testing
#: only the canonical spelling.
_DETERMINERS = ("", "a ", "the ", "some ")
_CASES = (str.lower, str.title, str.upper, str.swapcase)
_TAILS = ("", ".", "…", "!", "。", "．")
_PADS = ("", " ")


def _dressings(value):
    """Every dressing this harness replays for one canonical descriptor."""
    for case in _CASES:
        cased = case(value)
        for det in _DETERMINERS:
            for tail in _TAILS:
                for pad in _PADS:
                    yield (pad + det + cased + tail + pad)


_T07_REAL_ROLES = ("comic relief", "love interest")
_T07_ACCEPT_ROLES = ("lead", "supporting partner", "antagonist", "narrator")
_T07_ACCEPT_TEXTS = (
    "Must choose to expose the hidden warning.",
    "Disclosure shifts her from isolation to shared responsibility.",
    "If I lock that door, their checks bounce tomorrow.",
    "opens the ledger where Mara can read it",
    "four adult repair customers waiting in an ordinary queue",
)


# ---------------------------------------------------------------------------
# replay
# ---------------------------------------------------------------------------

def replay(repo):
    data = json.load(open(_REPLAY, encoding="utf-8"))
    proposed = Proposed(load_proposed())
    writer, validation, tmp = load_production(repo)
    production = Production(writer, validation)
    try:
        return _run(data, production, proposed)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


#: Inputs that appear in NEITHER receipt, so a rule tuned to the two test sets
#: shows up as a failure here rather than passing by construction.
_GENERALITY_ACCEPT_NAMES = (
    "Priya Raman", "Kwame Mensah", "Ingrid Solberg", "Tomás Herrera",
    "Zorblax Quinn", "Nkechi Adeyemi", "Officer Marta Reyes", "Sgt. Bo Lindqvist",
)
_GENERALITY_REFUSE_NAMES = (
    "Tall Stranger", "Hooded Figure", "Third Man", "Shop Staff",
    "The Woman", "Mysterious stranger", "Unseen Voice", "Crowd Member",
    "passenger", "SILENT ONLOOKER",
)
_GENERALITY_REFUSE_ROLES = ("aei", "ababab", "banana phone banana", "lalala", "qwertz")
_GENERALITY_ACCEPT_ROLES = ("reluctant mentor", "comic sidekick", "romantic interest")


def _generality(production, proposed):
    """Unseen-input probes in both directions."""
    rows = {"names_accept": [], "names_refuse": [], "roles_accept": [],
            "roles_refuse": []}
    for value in _GENERALITY_ACCEPT_NAMES:
        rows["names_accept"].append({"value": value,
                                     "production": production.person(value),
                                     "proposed": proposed.person(value)})
    for value in _GENERALITY_REFUSE_NAMES:
        rows["names_refuse"].append({"value": value,
                                     "production": production.person(value),
                                     "proposed": proposed.person(value)})
    for value in _GENERALITY_ACCEPT_ROLES:
        rows["roles_accept"].append({"value": value,
                                     "production": production.role(value),
                                     "proposed": proposed.role(value)})
    for value in _GENERALITY_REFUSE_ROLES:
        rows["roles_refuse"].append({"value": value,
                                     "production": production.role(value),
                                     "proposed": proposed.role(value)})
    return rows


def _run(data, production, proposed):
    t06 = data["t06"]
    t07 = data["t07"]
    report = {"provenance": data["provenance"]}

    # --- T06 direction (over-acceptance): every descriptor must be REFUSED ---
    rows = []
    acc_prod = acc_new = 0
    for value in t06["descriptors"]:
        prod = production.person(value)
        new = proposed.person(value)
        acc_prod += bool(prod)
        acc_new += bool(new)
        rows.append({"value": value, "production": prod, "proposed": new})
    report["t06_descriptors"] = {
        "replayed": len(rows),
        "accepted_production": acc_prod,
        "accepted_proposed": acc_new,
        "rows": rows,
    }

    # --- T06 direction, DRESSED: the same heads in every dressing ----------
    dressed_total = dressed_prod = dressed_new = 0
    dressed_fail = []
    for value in t06["descriptors"]:
        for candidate in _dressings(value):
            dressed_total += 1
            if production.person(candidate):
                dressed_prod += 1
            if proposed.person(candidate):
                dressed_new += 1
                if len(dressed_fail) < 40:
                    dressed_fail.append(candidate)
    report["t06_dressed"] = {
        "replayed": dressed_total,
        "accepted_production": dressed_prod,
        "accepted_proposed": dressed_new,
        "still_accepted_sample": dressed_fail,
    }

    # --- T06 direction (over-refusal): the false-positive controls ---------
    controls = []
    for value in t06["false_positive_controls"]:
        controls.append({"value": value,
                         "production": production.person(value),
                         "proposed": proposed.person(value)})
    report["t06_controls"] = {
        "replayed": len(controls),
        "accepted_production": sum(1 for c in controls if c["production"]),
        "accepted_proposed": sum(1 for c in controls if c["proposed"]),
        "rows": controls,
    }

    # --- T06 unicode class specifically -----------------------------------
    unicode_rows = [r for r in rows if any(ord(ch) > 127 for ch in r["value"])]
    report["t06_unicode"] = {
        "replayed": len(unicode_rows),
        "accepted_production": sum(1 for r in unicode_rows if r["production"]),
        "accepted_proposed": sum(1 for r in unicode_rows if r["proposed"]),
    }

    # --- T07 direction (over-acceptance): every filler row refused ---------
    filler = []
    for kind, surface, value in _T07_PROBES:
        if kind == "id_list":
            prod = production.id_list(value)
            new = proposed.id_list(value)
        else:
            prod = production.real_content(value, kind)
            new = proposed.real_content(value, kind)
        filler.append({"surface": surface, "kind": kind, "value": value,
                       "production": prod, "proposed": new})
    report["t07_filler"] = {
        "rows_replayable": len(filler),
        "evidence_rows": len(t07["accepted_filler_rows"]),
        "accepted_production": sum(1 for f in filler if f["production"]),
        "accepted_proposed": sum(1 for f in filler if f["proposed"]),
        "rows": filler,
    }

    # --- T07 direction (over-refusal): the real roles it wrongly refused ---
    roles = []
    for value in _T07_REAL_ROLES:
        roles.append({"value": value,
                      "production": production.role(value),
                      "proposed": proposed.role(value)})
    report["t07_refused_roles"] = {
        "rows": roles,
        "accepted_production": sum(1 for r in roles if r["production"]),
        "accepted_proposed": sum(1 for r in roles if r["proposed"]),
    }

    # --- T07 positive controls the verifier already accepted --------------
    role_controls = [{"value": v, "production": production.role(v),
                      "proposed": proposed.role(v)} for v in _T07_ACCEPT_ROLES]
    text_controls = [{"value": v, "production": production.real_content(v, "text"),
                      "proposed": proposed.real_content(v, "text")}
                     for v in _T07_ACCEPT_TEXTS]
    report["t07_controls"] = {
        "roles": role_controls,
        "texts": text_controls,
        "proposed_all_accepted": all(r["proposed"] for r in role_controls + text_controls),
    }
    report["generalisation"] = _generality(production, proposed)
    return report


def _print(report):
    print("=" * 78)
    print("S75-T41 shared-rule replay -- production vs proposed")
    print("=" * 78)
    for unit, meta in report["provenance"].items():
        print("%s: %s round %s head %s" % (unit.upper(), meta["file"],
                                           meta["round"], meta["head"][:12]))
    print()
    t = report["t06_descriptors"]
    print("T06 DESCRIPTORS (must be REFUSED -- over-acceptance direction)")
    print("  replayed %d   production accepted %d   proposed accepted %d"
          % (t["replayed"], t["accepted_production"], t["accepted_proposed"]))
    for row in t["rows"]:
        if row["proposed"]:
            print("    STILL ACCEPTED: %r" % (row["value"],))
    d = report["t06_dressed"]
    print("T06 DESCRIPTORS, DRESSED GRID (case x determiner x tail x pad)")
    print("  replayed %d   production accepted %d   proposed accepted %d"
          % (d["replayed"], d["accepted_production"], d["accepted_proposed"]))
    for value in d["still_accepted_sample"]:
        print("    STILL ACCEPTED: %r" % (value,))
    print()
    c = report["t06_controls"]
    print("T06 FALSE-POSITIVE CONTROLS (must be ACCEPTED -- over-refusal direction)")
    print("  replayed %d   production accepted %d   proposed accepted %d"
          % (c["replayed"], c["accepted_production"], c["accepted_proposed"]))
    for row in c["rows"]:
        if not row["proposed"]:
            print("    NOW REFUSED: %r" % (row["value"],))
    print()
    u = report["t06_unicode"]
    print("T06 UNICODE CLASS  replayed %d  production accepted %d  proposed accepted %d"
          % (u["replayed"], u["accepted_production"], u["accepted_proposed"]))
    print()
    f = report["t07_filler"]
    print("T07 FILLER (must be REFUSED -- over-acceptance direction)")
    print("  replayable rows %d of %d evidence rows; production accepted %d; proposed accepted %d"
          % (f["rows_replayable"], f["evidence_rows"],
             f["accepted_production"], f["accepted_proposed"]))
    for row in f["rows"]:
        if row["proposed"]:
            print("    STILL ACCEPTED: %s=%r (%s)"
                  % (row["surface"], row["value"], row["kind"]))
    print()
    r = report["t07_refused_roles"]
    print("T07 REAL ROLES IT WRONGLY REFUSED (must be ACCEPTED)")
    for row in r["rows"]:
        print("  %-16r production %-5s proposed %s"
              % (row["value"], row["production"], row["proposed"]))
    print()
    print("T07 POSITIVE CONTROLS")
    for row in report["t07_controls"]["roles"]:
        print("  role %-24r production %-5s proposed %s"
              % (row["value"], row["production"], row["proposed"]))
    for row in report["t07_controls"]["texts"]:
        print("  text %-60.60r production %-5s proposed %s"
              % (row["value"], row["production"], row["proposed"]))
    print()
    print("GENERALISATION (inputs in NEITHER receipt)")
    g = report["generalisation"]
    for bucket, want in (("names_accept", True), ("names_refuse", False),
                         ("roles_accept", True), ("roles_refuse", False)):
        bad = [row for row in g[bucket] if row["proposed"] != want]
        print("  %-14s %2d probes  proposed wrong %d%s"
              % (bucket, len(g[bucket]), len(bad),
                 "  " + repr([r["value"] for r in bad]) if bad else ""))
    print()
    gen_ok = all(row["proposed"] == want
                 for bucket, want in (("names_accept", True), ("names_refuse", False),
                                      ("roles_accept", True), ("roles_refuse", False))
                 for row in g[bucket])
    ok = (t["accepted_proposed"] == 0
          and d["accepted_proposed"] == 0
          and f["accepted_proposed"] == 0
          and all(row["proposed"] for row in r["rows"])
          and report["t07_controls"]["proposed_all_accepted"]
          and gen_ok)
    print("VERDICT: %s" % ("both directions hold" if ok else "DIRECTION NOT HELD"))
    return ok


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo", default=None,
                    help="git repo holding the unit branches (default: toplevel)")
    ap.add_argument("--json", default=None, help="write the full report here")
    args = ap.parse_args(argv)
    repo = args.repo or _git(_HERE, "rev-parse", "--show-toplevel").strip()
    report = replay(repo)
    ok = _print(report)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=1, ensure_ascii=False)
        print("report written to %s" % args.json)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
