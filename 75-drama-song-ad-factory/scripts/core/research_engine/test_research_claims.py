#!/usr/bin/env python3
"""Focused tests for S75-T04: research authoring + claim provenance.

Runs under pytest AND script-style (`python3 test_research_claims.py`), matching
test_research_gather.py, because the repo's required gate runs both. No
network: every stage call either takes the client's own sources or a premise.
"""
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

try:
    import pytest
except ImportError:                      # script-style run: no pytest installed
    pytest = None

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import claims as C          # noqa: E402
import research as R        # noqa: E402

FIXTURE = os.path.join(HERE, "fixtures", "research_claims.json")


def _fx():
    with open(FIXTURE, encoding="utf-8") as f:
        return json.load(f)


def _bundle(claims, sources=None, **extra):
    return {"schema_version": C.BUNDLE_SCHEMA_VERSION,
            "sources": sources or [], "claims": claims, **extra}


def _facts(fx):
    """The owner facts the run recorded — the fixture declares them at the top
    level, exactly as `author_bundle` writes them out of the brief. A claim's
    own `about.fact_text` is never the record: it is checked against this."""
    return {k: fx[k] for k in ("offer", "audience", "action") if k in fx}


def _plain(prov, text, **kw):
    claim = {"id": kw.pop("id", "x1"), "text": text, "provenance": prov,
             "sections": kw.pop("sections", ["market", "audience", "competitors"])}
    claim.update(kw)
    return claim


# ------------------------------------------------------------- accepted paths

def test_substantive_sourced_bundle_passes(tmp_path):
    fx = _fx()["accept"]
    env, code = R.run_stage(fx, str(tmp_path))
    assert code == R.EXIT["ok"] and env["outcome"] == "ok", env
    assert env["data"]["provenance"] == {"owner-fact": 1, "public-fact": 3,
                                         "fiction": 1}, env["data"]
    bundle = json.loads((tmp_path / "research" / "bundle.json").read_text())
    assert C.validate_bundle(bundle) == []
    provs = {c["provenance"] for c in bundle["claims"]}
    assert provs == {"owner-fact", "public-fact", "fiction"}


def test_explicitly_fictional_premise_passes_without_any_source(tmp_path):
    brief = {"offer": "A radio drama about a family diner",
             "audience": "listeners who like small-town stories",
             "action": "listen to episode one",
             "sub_avatar": {"avatar": "commuter", "emotional_wound": "long drive",
                            "desired_transformation": "a story worth the drive"},
             "premise": "The diner's owner invents a regular who never existed."}
    env, code = R.run_stage(brief, str(tmp_path))
    assert code == R.EXIT["ok"], env
    premise = (tmp_path / "research" / "premise.md").read_text()
    assert "fiction" in premise.lower() and "not a verified" in premise
    bundle = json.loads((tmp_path / "research" / "bundle.json").read_text())
    fiction = [c for c in bundle["claims"] if c["provenance"] == "fiction"]
    assert fiction and all("source" not in c for c in fiction), bundle["claims"]


def test_rendered_sections_carry_claims_and_provenance_not_just_headers(tmp_path):
    fx = _fx()["accept"]
    env, code = R.run_stage(fx, str(tmp_path))
    assert code == R.EXIT["ok"], env
    for section, expect in (("market", "Registered nursing"),
                            ("audience", "Rotating shift work"),
                            ("competitors", "competing sleep programs")):
        body = (tmp_path / "research" / ("%s.md" % section)).read_text()
        assert expect in body, (section, body)
        assert "[public-fact]" in body or "[owner-fact]" in body, body
        assert "TBD" not in body


def test_owner_claim_keeps_raw_answer_identity_and_stays_unverified(tmp_path):
    fx = _fx()["accept"]
    env, code = R.run_stage(fx, str(tmp_path))
    assert code == R.EXIT["ok"], env
    bundle = json.loads((tmp_path / "research" / "bundle.json").read_text())
    owner = [c for c in bundle["claims"] if c["provenance"] == "owner-fact"][0]
    assert owner["owner_ref"] == "answer:q11"
    assert owner["verification"] == "owner-asserted-unverified"


def test_gathered_claims_are_tagged_public_facts(tmp_path):
    """A briefly untagged client claim that a page cited becomes public-fact."""
    brief = {"offer": "Example back pain guide for adults",
             "audience": "adults over 50 who want to sleep through the night",
             "action": "book a free call",
             "sub_avatar": {"avatar": "retiree", "emotional_wound": "nights awake",
                            "desired_transformation": "sleeping through"},
             "sources": [{"id": "src-1", "url": "https://example.invalid/note",
                          "retrieved": "2026-10-20"}],
             "claims": [{"id": "c1",
                         "text": "Adults over fifty often wake during the night.",
                         "source": "src-1"}]}
    env, code = R.run_stage(brief, str(tmp_path))
    assert code == R.EXIT["ok"], env
    bundle = json.loads((tmp_path / "research" / "bundle.json").read_text())
    claim = bundle["claims"][0]
    assert claim["provenance"] == "public-fact"
    assert claim["source"] == "src-1"


# -------------------------------------------------------------- refused paths

def test_untagged_claims_are_refused():
    fx = _fx()["reject_untagged"]
    tagged, errors = C.tag_claims(fx["claims"], {}, {"src-1"})
    assert errors == []
    assert [c.get("provenance") for c in tagged] == ["public-fact", "public-fact"]
    # The same claims handed in as an artifact with the tags stripped are
    # refused on content: an origin is never invented for them.
    stripped = [{"id": c["id"], "text": c["text"], "sections": ["market"]}
                for c in fx["claims"]]
    errors = C.validate_bundle(_bundle(stripped, fx["sources"]))
    assert any("no provenance tag" in e for e in errors), errors


def test_sections_without_claims_are_refused():
    claim = _plain("owner-fact", "The owner says clients call back within a week.",
                   owner_ref="answer:q3", sections=["market"])
    errors = C.validate_bundle(_bundle([claim]))
    assert any(e.startswith("audience:") for e in errors), errors
    assert any(e.startswith("competitors:") for e in errors), errors


def test_empty_research_fails_however_large_the_artifact_is():
    big = {"claims": [], "padding": "x" * 200000,
           "market_md": "# Market\n\n" + ("Offer: x\n" * 4000)}
    errors = C.validate_bundle(big)
    assert any("empty research" in e for e in errors), errors


def test_a_keyword_run_is_the_judged_checks_job_not_a_parser():
    """U-X01: the hand-built language parser is gone. A run of keywords is not
    refused here for being a run of keywords; a marker it carries with no
    citation for that marker is still refused, and the rest is the run's
    checker model's verdict, filed as one `research_relevance` record."""
    fx = _fx()["reject_keyword_stuffing"]
    errors = C.validate_bundle(_bundle(fx["claims"], fx["sources"]))
    assert not any("keyword stuffing" in e for e in errors), errors
    assert any("uncited claim" in e for e in errors), errors
    # a run with no escalated marker passes the structural check ...
    plain = _plain("public-fact",
                   "buy backlinks, crypto signals, weight loss tea, katy perry "
                   "diet, seo package",
                   id="s2", source="src-1",
                   sections=["market", "audience", "competitors"])
    assert C.validate_bundle(_bundle([plain], fx["sources"])) == []
    # ... and the stage cannot advance until a checker has judged it.
    assert C.relevance_verdict([], maker="maker-1") == "MISSING"


def test_unsupported_business_claim_is_refused():
    fx = _fx()["reject_unsupported_business"]
    errors = C.validate_bundle(_bundle(fx["claims"], fx["sources"]))
    assert any("unsupported business claim" in e for e in errors), errors


def test_quantified_business_claim_is_refused_in_any_phrasing():
    fx = _fx()["reject_business_phrasings"]
    errors = C.validate_bundle(_bundle(fx["claims"], fx["sources"]))
    by_id = [e for e in errors if "unsupported business claim" in e]
    assert len(by_id) >= 3, errors
    # variants the verdict did not name: digits with a magnitude, a spelled-out
    # count, and a growth number — none of them share a fixed phrase.
    src = [{"id": "src-1", "url": "https://example.invalid/r", "retrieved": "2026-10-20"}]
    for text in ("Our Dallas clinic has helped 250 clients since 2019.",
                 "More than four thousand families have trusted our coaches.",
                 "Since 2020 the program has enrolled 4,000 students."):
        claim = _plain("public-fact", text, source="src-1")
        errors = C.validate_bundle(_bundle([claim], src))
        assert any("unsupported business claim" in e for e in errors), (text, errors)


def test_superlative_business_claim_is_refused_in_any_phrasing():
    src = [{"id": "src-1", "url": "https://example.invalid/r", "retrieved": "2026-10-20"}]
    for text in ("This program is the most trusted sleep coaching service in Dallas.",
                 "The premier coaching service and the fastest growing program in Texas.",
                 "We run the leading sleep clinic in the city.",
                 "Dallas families call our coaching the best they have used."):
        claim = _plain("public-fact", text, source="src-1")
        errors = C.validate_bundle(_bundle([claim], src))
        assert any("unsupported business claim" in e for e in errors), (text, errors)


def test_sentence_shaped_keyword_stuffing_is_left_to_the_judged_check():
    """U-X01: no parser reads the sentence shape any more. 'Best sleep coach'
    is refused because a superlative with no citation for that claim is not
    evidence — a structural rule, not a vocabulary."""
    fx = _fx()["reject_sentence_keyword_stuffing"]
    errors = C.validate_bundle(_bundle(fx["claims"], fx["sources"]))
    assert not any("keyword stuffing" in e for e in errors), errors
    assert any("uncited claim" in e for e in errors), errors


def test_market_facts_still_pass_the_same_instrument():
    """Quantified and comparative market research is not a business claim."""
    fx = _fx()["accept_market_facts"]
    errors = C.validate_bundle(_bundle(fx["claims"], fx["sources"], **_facts(fx)))
    assert errors == [], errors


def test_relevance_is_a_checker_record_and_the_maker_cannot_sign_it():
    """U-X01: relevance and fairness are the run's CHECKER model's verdict,
    filed through the QC record path under the check id research_relevance. A
    maker's own signature is not evidence (17.6)."""
    reviewer = {"identity": "checker-model", "session": "run-1",
                "authority": "research-qc"}
    rec = C.relevance_record(run_id="research-1", stage="research",
                             maker="maker-model", reviewer=reviewer,
                             verdict="PASS",
                             summary="every claim is about this client and fairly stated")
    assert rec["check"] == C.RESEARCH_RELEVANCE_CHECK == "research_relevance"
    assert rec["schema_version"] == "1.0.0" and rec["reviewer"] == reviewer
    assert C.relevance_verdict([rec], maker="maker-model") == "PASS"
    assert C.relevance_verdict([rec], maker=None) == "PASS"
    assert C.relevance_verdict([], maker="maker-model") == "MISSING"
    failed = dict(rec, verdict="FAIL")
    assert C.relevance_verdict([failed], maker="maker-model") == "FAIL"
    try:
        C.relevance_record(run_id="research-1", stage="research",
                           maker="maker-model",
                           reviewer=dict(reviewer, identity="maker-model"),
                           verdict="PASS", summary="trust me")
    except ValueError:
        pass
    else:
        raise AssertionError("a maker signing its own relevance check must be refused")
    own = dict(rec, reviewer=dict(reviewer, identity="maker-model"))
    assert C.relevance_verdict([own], maker="maker-model") == "MISSING"


def test_two_industries_pass_the_same_structural_check(tmp_path):
    """Acceptance: a sleep-coaching brief and a non-coaching brief both pass the
    structural check. Nothing in it is keyed to a trade's vocabulary."""
    with open(os.path.join(HERE, "fixtures", "research_industries.json"),
              encoding="utf-8") as f:
        bakery = json.load(f)["bakery"]
    for label, brief in (("coaching", _fx()["accept"]), ("bakery", bakery)):
        out = str(tmp_path / label)
        env, code = R.run_stage(dict(brief), out)
        assert code == R.EXIT["ok"], (label, env)
        bundle = json.loads((tmp_path / label / "research" / "bundle.json").read_text())
        assert C.validate_bundle(bundle) == [], (label, C.validate_bundle(bundle))


def test_repeated_text_is_refused_and_deduped_at_authoring():
    dupe = "Nurses on rotating shifts sleep less than day staff."
    claims = [_plain("owner-fact", dupe, id="a", owner_ref="answer:q1"),
              _plain("owner-fact", dupe, id="b", owner_ref="answer:q2")]
    errors = C.validate_bundle(_bundle(claims))
    assert any("duplicate of" in e for e in errors), errors


def test_public_fact_without_a_resolvable_source_is_refused():
    errors = C.validate_bundle(_bundle(
        [_plain("public-fact", "Night shift nurses sleep in two short blocks.",
                source="src-9")]))
    assert any("no resolvable source" in e for e in errors), errors


def test_owner_fact_without_an_answer_identity_is_refused():
    errors = C.validate_bundle(_bundle(
        [_plain("owner-fact", "Clients say the program works.", owner_ref="")]))
    assert any("raw answer identity" in e for e in errors), errors


# -------------------------------------------------------------------- the CLI

def test_validate_bundle_cli_exit_codes(tmp_path, capsys):
    fx = _fx()
    good = _bundle(
        [_plain("public-fact", "Registered nursing is a large occupation.",
                source="src-1", sections=["market", "audience", "competitors"])],
        [{"id": "src-1", "url": "https://example.invalid/a", "retrieved": "2026-10-20"}])
    path = tmp_path / "bundle.json"
    path.write_text(json.dumps(good), encoding="utf-8")
    assert R.main(["--validate-bundle", str(path)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["outcome"] == "ok" and payload["command"] == "research-validate"

    bad = dict(good, claims=[{"id": "z", "text": "Untagged line.", "sections": ["market"]}])
    path.write_text(json.dumps(bad), encoding="utf-8")
    assert R.main(["--validate-bundle", str(path)]) == R.EXIT["rejected"] == 4
    payload = json.loads(capsys.readouterr().out)
    assert payload["reason_code"] == "research-bundle-invalid"

    path.write_text(json.dumps(fx["reject_empty"]), encoding="utf-8")
    assert R.main(["--validate-bundle", str(path)]) == 4


def test_stage_refuses_an_artifact_it_cannot_tag(tmp_path):
    """An untaggable claim stops the stage before anything is written."""
    brief = {"offer": "Sleep coaching", "audience": "shift workers",
             "action": "book a call",
             "sub_avatar": {"avatar": "nurse", "emotional_wound": "awake",
                            "desired_transformation": "rested"},
             "sources": [{"id": "src-1", "url": "https://example.invalid/a",
                          "retrieved": "2026-10-20"}],
             "claims": [{"id": "c1", "text": "Shift work affects sleep.",
                         "source": "src-1", "provenance": "hearsay"}]}
    env, code = R.run_stage(brief, str(tmp_path))
    assert code == R.EXIT["rejected"], env
    assert env["reason_code"] == "research-bundle-invalid"
    assert not (tmp_path / "research").exists(), "no artifact on refusal"


class _Captured:
    def __init__(self):
        import io
        self._buf = io.StringIO()
        self._old = sys.stdout
        sys.stdout = self._buf

    def readouterr(self):
        out = self._buf.getvalue()
        self._buf.seek(0)
        self._buf.truncate(0)
        return type("Captured", (), {"out": out, "err": ""})()

    def close(self):
        sys.stdout = self._old


def _run_all():
    import inspect
    passed, failures = 0, []
    for name, fn in sorted(globals().items()):
        if not (name.startswith("test_") and callable(fn)):
            continue
        kwargs, teardown = {}, []
        unknown = [p for p in inspect.signature(fn).parameters
                   if p != "tmp_path" and p != "capsys"]
        if unknown:
            failures.append(name)
            print("FAIL: %s: no script-style runner for %s" % (name, unknown))
            continue
        for param in inspect.signature(fn).parameters:
            if param == "tmp_path":
                kwargs[param] = Path(tempfile.mkdtemp(prefix="research-claims-"))
            else:
                kwargs[param] = _Captured()
                teardown.append(kwargs[param])
        error = None
        try:
            fn(**kwargs)
        except Exception as exc:          # noqa: BLE001 - report and keep going
            error = exc
        finally:
            for item in teardown:
                item.close()
            if "tmp_path" in kwargs:
                shutil.rmtree(kwargs["tmp_path"], ignore_errors=True)
        if error is None:
            passed += 1
            print("ok: %s" % name)
        else:
            failures.append(name)
            print("FAIL: %s: %s" % (name, error))
    print("%d passed, %d failed" % (passed, len(failures)))
    return 1 if failures else 0


if __name__ == "__main__":
    if pytest is not None:
        sys.exit(pytest.main([__file__, "-q"]))
    sys.exit(_run_all())
