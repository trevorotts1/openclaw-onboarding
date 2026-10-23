#!/usr/bin/env python3
"""sc37_semantic_sibling_advancement.py — acceptance row SC-37.

Condition (SCENARIO-MATRIX.json, row SC-37, verbatim):
    "Semantic sibling advancement"

Required result (verbatim):
    "NEGATIVE: semantic sibling advancement is refused when the accepted pair is
     not identical (same_pair=false), never advanced on freshness alone"

This row lives in the graphify convergence seam (S75-W09): unified promotion
must refuse when the semantic views do not name ONE common accepted
onboarding/999 pair. The named counterexample is
``same_pair=false / unified_coverage_fresh=true`` — every component's own
release head is fresh, so freshness alone would advance the promotion, and
that must be refused.

The runner drives the REAL modules of the graphify checkout given by
``--graphify-root`` (``src/graphifyctl/unified.py`` + ``engine.py``) against
synthetic release metadata in a scratch data root. No network, no provider, no
live graph write, no index refresh.

A supplied ``--graphify-root`` is AUTHORITATIVE: if that checkout does not hold
``src/graphifyctl/unified.py`` the runner exits 2 naming the path. Defaults are
searched only when the argument is omitted.

Modes:
  (no flag)   run the scenario and print one assertion line per check
  selftest    re-run under deliberate defects and REQUIRE the named assertions
              to turn RED (proves the harness can fail)

Exit 0 = every assertion held; 1 = at least one failed; 2 = tooling.
"""
from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _harness as H  # noqa: E402

ROW = "sc37"
TITLE = "semantic sibling advancement refused when the pair is not identical"
GRAPHIFY_REL = Path("src") / "graphifyctl" / "unified.py"

ONB = "1" * 40
NINE = "2" * 40
ONB_ALT = "3" * 40
NINE_ALT = "4" * 40
CC = "5" * 40

#: only searched when --graphify-root is OMITTED
DEFAULT_ROOTS = (
    H.REPO_ROOT.parent / "blackceo-graphify-infrastructure",
    H.REPO_ROOT / ".." / "blackceo-graphify-infrastructure",
)

# --------------------------------------------------------------------------
# root resolution — an explicit path is authoritative, never a fallback
# --------------------------------------------------------------------------
def resolve_graphify_root(explicit):
    if explicit:
        root = Path(explicit).expanduser().resolve()
        if not (root / GRAPHIFY_REL).is_file():
            print("TOOLING: graphify root %s does not hold %s"
                  % (root, GRAPHIFY_REL))
            raise SystemExit(2)
        return root
    seen = []
    for cand in DEFAULT_ROOTS:
        cand = Path(cand)
        seen.append(str(cand))
        if (cand / GRAPHIFY_REL).is_file():
            return cand.resolve()
    print("TOOLING: no graphify checkout in the default locations (%s); pass "
          "--graphify-root" % ", ".join(seen))
    raise SystemExit(2)

def load_graphify(root):
    src = str(Path(root) / "src")
    sys.path.insert(0, src)
    try:
        engine = importlib.import_module("graphifyctl.engine")
        unified = importlib.import_module("graphifyctl.unified")
    except ImportError as exc:
        print("TOOLING: cannot import graphifyctl from %s: %s" % (src, exc))
        raise SystemExit(2)
    finally:
        try:
            sys.path.remove(src)
        except ValueError:
            pass
    return unified, engine

# --------------------------------------------------------------------------
# synthetic fixtures — component releases with recorded semantic pairs
# --------------------------------------------------------------------------
def release(data, name, head, pair, release_name="r1"):
    dest = Path(data) / name / "releases" / release_name
    dest.mkdir(parents=True, exist_ok=True)
    meta = {"repository": name, "release": release_name,
            "source": {"head": head}}
    if pair is not None:
        meta["semantic"] = {"onboarding_ref": pair[0], "ref_999": pair[1]}
    (dest / "metadata.json").write_text(json.dumps(meta, sort_keys=True),
                                        encoding="utf-8")
    link = Path(data) / name / "current"
    if link.is_symlink() or link.exists():
        link.unlink()
    os.symlink("releases/" + release_name, link)

def unified_meta(data, heads):
    udata = Path(data) / "unified"
    udata.mkdir(parents=True, exist_ok=True)
    components = {name: {"release": rel, "head": head}
                  for name, (rel, head) in heads.items()}
    (udata / "metadata.json").write_text(
        json.dumps({"components": components, "stats": {}}, sort_keys=True),
        encoding="utf-8")

def unified_graph(data):
    udata = Path(data) / "unified"
    udata.mkdir(parents=True, exist_ok=True)
    (udata / "linked-graph.json").write_text(json.dumps({
        "nodes": [{"id": "n1"}, {"id": "n2"}],
        "links": [{"source": "n1", "target": "n2"}],
    }), encoding="utf-8")

def config(tmp):
    tmp = Path(tmp)
    return {
        "data_root": str(tmp / "data"),
        "semantic": {"enabled_repos": ["onboarding", "999"]},
        "aggregate": {"enabled": True},
        "n8n": {"enabled": True},
        "ghl": {"enabled": True},
        "repos": {
            "onboarding": {"enabled": True, "initialized": True,
                           "path": str(tmp / "repo-onboarding")},
            "999": {"enabled": True, "initialized": True,
                    "path": str(tmp / "repo-999")},
            "command-center": {"enabled": True, "initialized": True,
                               "path": str(tmp / "repo-cc")},
        },
    }

def accepted_vector(status="ACCEPTED"):
    return {"status": status, "vector": {
        "onboarding": {"accepted_sha": ONB},
        "999": {"accepted_sha": NINE},
        "command-center": {"accepted_sha": CC},
        "graphify_engine_revision": {"accepted_sha": "6" * 40},
    }}

def divergent(cfg):
    """Two semantic views, two different pairs; every own head is fresh."""
    data = Path(cfg["data_root"])
    release(data, "onboarding", ONB, (ONB, NINE))
    release(data, "999", NINE, (ONB_ALT, NINE_ALT))
    release(data, "command-center", CC, None)
    unified_meta(data, {"onboarding": ("r1", ONB), "999": ("r1", NINE),
                        "command-center": ("r1", CC)})

def converged(cfg, pair=(ONB, NINE)):
    data = Path(cfg["data_root"])
    release(data, "onboarding", ONB, pair)
    release(data, "999", NINE, pair)
    release(data, "command-center", CC, None)
    unified_meta(data, {"onboarding": ("r1", ONB), "999": ("r1", NINE),
                        "command-center": ("r1", CC)})

def freshness_axes_clean(cover):
    return (not cover["missing"] and not cover["stale_components"]
            and not cover["identity_mismatches"])

def refusal(fn, *args, **kwargs):
    """(raised: bool, text: str) — never swallows a non-UnifiedError."""
    try:
        fn(*args, **kwargs)
    except Exception as exc:                       # noqa: BLE001
        return type(exc).__name__, str(exc)
    return None, ""

# --------------------------------------------------------------------------
# the scenario
# --------------------------------------------------------------------------
def scenario(root, muts=frozenset()):
    unified, engine = load_graphify(root)
    if "fresh_ignores_pair" in muts:
        real_coverage = unified.coverage

        def freshness_only(cfg):
            out = dict(real_coverage(cfg))
            out["fresh"] = True          # defect: freshness alone advances
            return out
        unified.coverage = freshness_only
    if "pair_always_true" in muts:
        real_pair = unified.semantic_pair_check

        def pair_always_ok(cfg):
            out = dict(real_pair(cfg))
            out["same_pair"] = True      # defect: divergence never refused
            out["reasons"] = []
            return out
        # coverage()/rebuild() read semantic_pair_check at call time, so this
        # patch is the whole pre-repair defect. build() is stubbed so the
        # defective path reaches publication deterministically.
        unified.semantic_pair_check = pair_always_ok
        unified.build = lambda cfg: {
            "graph": {"nodes": [{"id": "n1"}, {"id": "n2"}],
                      "links": [{"source": "n1", "target": "n2"}]},
            "summary": {"stats": {}, "components": {}},
        }

    c = H.Checks(ROW, TITLE)
    print("SC37 %s — graphify %s%s"
          % (TITLE, root, (" [defect: %s]" % ",".join(sorted(muts)))
             if muts else ""))

    with H.Scratch() as tmp:
        tmp = Path(tmp)

        # ---- named counterexample: same_pair=false, own heads fresh ------
        cfg = config(tmp / "case1")
        divergent(cfg)
        cover = unified.coverage(cfg)
        clean = freshness_axes_clean(cover)
        c.check("sc37:same-pair-is-false-on-divergent-views",
                cover["same_pair"] is False,
                "same_pair=%s distinct_pairs=%s reasons=%s"
                % (cover["same_pair"],
                   cover["semantic_pair"]["distinct_pairs"],
                   cover["semantic_pair"]["reasons"]))
        c.check("sc37:freshness-axes-are-clean-in-the-counterexample",
                clean,
                "missing=%s stale=%s identity=%s"
                % (cover["missing"], sorted(cover["stale_components"]),
                   sorted(cover["identity_mismatches"])))
        c.check("sc37:not-fresh-on-freshness-alone",
                clean and cover["fresh"] is False,
                "fresh=%s same_pair=%s freshness_axes_clean=%s"
                % (cover["fresh"], cover["same_pair"], clean))

        kind, text = refusal(unified.rebuild, cfg)
        c.check("sc37:rebuild-refuses-divergent-pair",
                kind == "UnifiedError" and "semantic" in text.lower(),
                "raised=%s message=%r" % (kind, text[:160]))
        udata = Path(cfg["data_root"]) / "unified"
        current = udata / "current"
        releases = (sorted(p.name for p in (udata / "releases").iterdir())
                    if (udata / "releases").is_dir() else [])
        published = os.path.lexists(str(current)) or bool(releases)
        c.check("sc37:refused-promotion-publishes-nothing",
                not published,
                "current_symlink=%s releases=%s"
                % (os.path.lexists(str(current)), releases or "none"))

        # ---- verify() refuses a previously published unified graph ------
        unified_graph(cfg["data_root"])
        kind, text = refusal(unified.verify, cfg)
        c.check("sc37:verify-refuses-a-published-graph",
                kind == "UnifiedError" and "semantic convergence" in text,
                "raised=%s message=%r" % (kind, text[:160]))

        # ---- a sibling's published SHA never substitutes for the pair ---
        cfg = config(tmp / "case2")
        cfg["semantic"]["accepted_vector"] = accepted_vector()
        data = Path(cfg["data_root"])
        release(data, "onboarding", ONB, (ONB, NINE))
        release(data, "999", NINE, (ONB_ALT, NINE_ALT))
        release(data, "command-center", CC, None)
        pair = unified.semantic_pair_check(cfg)
        named_999 = any("999" in reason for reason in pair["reasons"])
        c.check("sc37:sibling-sha-does-not-substitute-for-the-pair",
                pair["same_pair"] is False and named_999,
                "same_pair=%s distinct_pairs=%s reasons=%s"
                % (pair["same_pair"], pair["distinct_pairs"], pair["reasons"]))
        kind, text = refusal(unified.rebuild, cfg)
        c.check("sc37:off-pair-rebuild-refused-against-accepted-vector",
                kind == "UnifiedError" and "accepted source vector" in text,
                "raised=%s message=%r" % (kind, text[:160]))

        # ---- control: an identical accepted pair converges --------------
        cfg = config(tmp / "case3")
        cfg["semantic"]["accepted_vector"] = accepted_vector()
        converged(cfg)
        cover = unified.coverage(cfg)
        c.check("sc37:control-identical-pair-converges",
                cover["same_pair"] is True and cover["fresh"] is True,
                "same_pair=%s fresh=%s views=%s accepted_vector=%s"
                % (cover["same_pair"], cover["fresh"],
                   sorted(cover["semantic_pair"]["views"]),
                   cover["semantic_pair"]["accepted_vector"]))

        # ---- semantic scope: structural component is never a view ------
        pair = unified.semantic_pair_check(cfg)
        views = sorted(pair["views"])
        c.check("sc37:structural-component-is-not-a-semantic-view",
                views == ["999", "onboarding"] and pair["unverified"] == [],
                "views=%s unverified=%s" % (views, pair["unverified"]))
    return c

# --------------------------------------------------------------------------
# selftest — prove the harness turns RED under deliberate defects
# --------------------------------------------------------------------------
MUTATIONS = {
    "fresh_ignores_pair": [
        "sc37:not-fresh-on-freshness-alone",
    ],
    "pair_always_true": [
        "sc37:same-pair-is-false-on-divergent-views",
        "sc37:not-fresh-on-freshness-alone",
        "sc37:rebuild-refuses-divergent-pair",
        "sc37:refused-promotion-publishes-nothing",
    ],
}

def selftest(root):
    ok = True
    for name in sorted(MUTATIONS):
        c = scenario(root, frozenset([name]))
        failed = [r["name"] for r in c.failed()]
        expected = MUTATIONS[name]
        hit = [e for e in expected if e in failed]
        good = len(hit) == len(expected) and len(failed) >= 1
        ok = ok and good
        print("selftest:%s — %s; red=%s"
              % (name, "RED as required" if good else "DID NOT FAIL AS EXPECTED",
                 failed or "none"))
        print("selftest:%s — expected hit=%d/%d"
              % (name, len(hit), len(expected)))
    print("selftest — %s"
          % ("harness fails on every injected defect" if ok
             else "HARNESS CANNOT PROVE A FAILURE"))
    return 0 if ok else 1

def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "selftest":
        ap = argparse.ArgumentParser(description="sc37 selftest")
        ap.add_argument("--graphify-root", default=None)
        args = ap.parse_args(argv[1:])
        return selftest(resolve_graphify_root(args.graphify_root))

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--graphify-root", default=None,
                    help="explicit graphify checkout (authoritative); omitted "
                         "searches the default locations")
    ap.add_argument("--out", default=None, help="optional receipt directory")
    args = ap.parse_args(argv)
    root = resolve_graphify_root(args.graphify_root)
    result = scenario(root)
    if args.out:
        path = Path(args.out) / "receipts"
        return result.finish(path)
    return result.finish()

if __name__ == "__main__":
    sys.exit(main())
