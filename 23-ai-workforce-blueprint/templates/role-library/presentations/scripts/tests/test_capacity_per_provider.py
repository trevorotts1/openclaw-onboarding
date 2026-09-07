#!/usr/bin/env python3
"""test_capacity_per_provider.py -- F1/F2: a plan answer about ONE provider
must never cap another provider's routes.

THE DEFECT (measured on v25.0.17 / eaedc0633, reproduced in an isolated
scratch config dir with the live code):

    capacity.probe()                                  -> no file: deepseek-direct,
                                                         available 2500
    resource_profile.record_plan_answer(              -> writes BOTH the profile
        'ollama-cloud', '$100/month')                    AND capacity_override.json
    capacity.probe()                                  -> ollama-cloud, available 8
                                                         (source capacity_override.json,
                                                          detection steps b/c never run)
    dispatcher.resolve_max_workers(dept, None, 50)    -> 8   (was 2500)

One client's answer about ONE account became the whole box's ceiling, because
`capacity_override.json` was step (a) of a detection chain that answered ONE
question ("what is this box's capacity?") when the dispatch path asks a
different one per route ("what is THIS provider's capacity?").

THE FIX THIS FILE LOCKS:
  F1  detect()/probe() take `provider=`/`model=` and answer about ONE
      provider; the override file is honoured ONLY for the provider it names;
      schema 2 holds several providers side by side; a legacy v1 flat record
      is still read, scoped to its own provider, and never rewritten.
  F2  resource_profile.record_plan_answer() stops projecting the answer into
      capacity_override.json. The profile is THE store; its lock is THE
      ask-once gate; the CAP_TABLE concurrency_ceiling write stays, because
      the governor's operator reserve reads it.

EVERY test here redirects both config envs at tmp_path and disables the live
provider probes -- nothing in this file may read or write the operator's real
resource profile.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from presentation_job import capacity  # noqa: E402
from presentation_job import governor  # noqa: E402
from presentation_job import resource_profile  # noqa: E402


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------
def _isolate(monkeypatch, tmp_path):
    """No 9Router db, no OpenClaw config, no harness settings, no live probes
    -- and BOTH stores redirected into tmp_path, so no test here can read or
    write the operator's real ~/.openclaw/state/presentation/ profile."""
    monkeypatch.setattr(capacity, "NINEROUTER_DB", tmp_path / "absent.sqlite")
    monkeypatch.setattr(capacity, "OPENCLAW_CONFIG", tmp_path / "absent.json")
    monkeypatch.setattr(capacity, "HARNESS_SETTINGS_CANDIDATES",
                        (tmp_path / "absent-settings.json",))
    monkeypatch.setattr(capacity, "measure_working_concurrent",
                        lambda: (0, "stub", True))
    monkeypatch.setenv("PRESENTATION_PROVIDER_PROBES", "0")
    cfg = tmp_path / "cfg"
    cfg.mkdir(exist_ok=True)
    monkeypatch.setenv(capacity.CONFIG_DIR_ENV, str(cfg))
    monkeypatch.setenv(resource_profile.DIR_ENV, str(cfg))
    monkeypatch.delenv(resource_profile.FLAG_ENV, raising=False)
    cache = getattr(capacity, "_DECLARED_CACHE", None)
    if isinstance(cache, dict):
        cache.clear()
    return cfg


def _openclaw_routing_to(monkeypatch, tmp_path, namespace, model, base_url):
    """Make detection step (c) report a REAL provider -- the multi-provider
    box the defect needs: the client routes to one provider and has answered
    the plan question about a DIFFERENT one."""
    path = tmp_path / "openclaw.json"
    path.write_text(json.dumps({
        "agents": {"defaults": {"model": {"primary": f"{namespace}/{model}"}}},
        "models": {"providers": {namespace: {"baseUrl": base_url}}},
    }), encoding="utf-8")
    monkeypatch.setattr(capacity, "OPENCLAW_CONFIG", path)
    return path


def _deepseek_box(monkeypatch, tmp_path):
    return _openclaw_routing_to(monkeypatch, tmp_path, "deepseek",
                                "deepseek-v4-flash", "https://api.deepseek.com/v1")


# ---------------------------------------------------------------------------
# TEST 1 -- the defect itself
# ---------------------------------------------------------------------------
def test_plan_answer_for_one_provider_never_caps_another(monkeypatch, tmp_path):
    """THE regression. A DeepSeek-routed box whose client answered the Ollama
    plan question must still dispatch DeepSeek routes at DeepSeek's ceiling.

    MUTATION CAUGHT ON PRISTINE eaedc0633: record_plan_answer() wrote
    capacity_override.json, detection step (a) read it first, and probe()
    answered `ollama-cloud / 8` for a box whose primary route is DeepSeek
    Flash / 2500."""
    cfg = _isolate(monkeypatch, tmp_path)
    _deepseek_box(monkeypatch, tmp_path)

    before = capacity.probe(cfg)
    assert before["provider"] == "deepseek-direct", before
    assert before["available"] == 2500, before

    resource_profile.record_plan_answer("ollama-cloud", "$100/month", cfg)

    after = capacity.probe(cfg)
    assert after["provider"] == "deepseek-direct", after
    assert after["available"] == 2500, after

    # ...and each provider still answers for ITSELF.
    assert capacity.probe(cfg, provider="ollama-cloud")["available"] == 8
    assert capacity.probe(
        cfg, provider="deepseek-direct", model="deepseek-v4-flash"
    )["available"] == 2500


def test_the_probe_says_which_provider_it_was_asked_about(monkeypatch, tmp_path):
    """`provider_requested` exists so the routing stamp can ASSERT the answer
    is about the provider it asked about instead of inferring it -- the
    inference is what let a probe about ollama-cloud size a DeepSeek route."""
    cfg = _isolate(monkeypatch, tmp_path)
    _deepseek_box(monkeypatch, tmp_path)
    asked = capacity.probe(cfg, provider="ollama-cloud")
    assert asked["provider_requested"] == "ollama-cloud", asked
    assert asked["provider"] == "ollama-cloud", asked
    # The no-arg call keeps today's meaning: the PRIMARY route's account.
    unasked = capacity.probe(cfg)
    assert unasked["provider_requested"] is None, unasked
    assert unasked["provider"] == "deepseek-direct", unasked


# ---------------------------------------------------------------------------
# TEST 2 -- the profile is the store
# ---------------------------------------------------------------------------
def test_record_plan_answer_writes_the_profile_not_the_override(
        monkeypatch, tmp_path):
    """F2. MUTATION CAUGHT ON PRISTINE eaedc0633: record_plan_answer() called
    capacity.persist_plan_answer(), so capacity_override.json existed after
    the interview -- and its mere existence pre-empted detection for every
    provider on the box."""
    cfg = _isolate(monkeypatch, tmp_path)
    resource_profile.record_plan_answer("ollama-cloud", "$100/month", cfg)

    assert not capacity.override_path(cfg).is_file(), (
        "the interview answer must not be projected into capacity_override.json")

    entry = resource_profile.get_provider(
        resource_profile.load_profile(cfg), "ollama-cloud")
    assert entry["plan_tier"] == "$100/month", entry
    assert entry["plan_known"] is True, entry
    assert entry["locked"] is True, entry
    # The governor's operator reserve reads THIS number -- keep it.
    assert entry["concurrency_ceiling"] == 8, entry


def test_the_profile_disabled_rollback_still_has_a_durable_home(
        monkeypatch, tmp_path):
    """The one case the profile cannot hold the answer: the documented
    rollback PRESENTATION_RESOURCE_PROFILE=0. Then -- and only then -- a v2
    declaration is written, for exactly the provider that was answered."""
    cfg = _isolate(monkeypatch, tmp_path)
    monkeypatch.setenv(resource_profile.FLAG_ENV, "0")
    resource_profile.record_plan_answer("ollama-cloud", "$100/month", cfg)

    path = capacity.override_path(cfg)
    assert path.is_file(), "the rollback path must not lose the answer"
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert doc["schema"] == capacity.OVERRIDE_SCHEMA, doc
    assert list(doc["providers"]) == ["ollama-cloud"], doc
    assert doc["providers"]["ollama-cloud"]["plan"] == "$100/month", doc


# ---------------------------------------------------------------------------
# TEST 5 -- a legacy v1 record is scoped to its own provider
# ---------------------------------------------------------------------------
def test_legacy_v1_override_is_scoped_to_its_provider(monkeypatch, tmp_path):
    """Fleet remediation without touching a single fleet file: a box that
    already carries the old flat record keeps working, and that record stops
    being a statement about every OTHER provider on the box.

    MUTATION CAUGHT ON PRISTINE eaedc0633: this exact file made probe()
    answer ollama-cloud/8 for a DeepSeek-routed box."""
    cfg = _isolate(monkeypatch, tmp_path)
    _deepseek_box(monkeypatch, tmp_path)
    legacy = {"provider": "ollama-cloud", "plan": "$100/month",
              "max_concurrent": 8, "source": "interview"}
    capacity.override_path(cfg).write_text(json.dumps(legacy), encoding="utf-8")

    primary = capacity.probe(cfg)
    assert primary["provider"] == "deepseek-direct", primary
    assert primary["available"] == 2500, primary

    scoped = capacity.probe(cfg, provider="ollama-cloud")
    assert scoped["available"] == 8, scoped
    assert scoped["detection_source"] == capacity.SOURCE_OVERRIDE, scoped


def test_a_legacy_v1_record_is_never_rewritten_on_read(monkeypatch, tmp_path):
    """Reading is not migrating. A client box's file comes back byte-identical
    after any number of probes -- nothing on a fleet box is rewritten behind
    the operator's back to make this fix work."""
    cfg = _isolate(monkeypatch, tmp_path)
    _deepseek_box(monkeypatch, tmp_path)
    path = capacity.override_path(cfg)
    raw = json.dumps({"provider": "ollama-cloud", "plan": "$100/month"})
    path.write_text(raw, encoding="utf-8")

    capacity.probe(cfg)
    capacity.probe(cfg, provider="ollama-cloud")
    capacity.probe(cfg, provider="deepseek-direct", model="deepseek-v4-flash")

    assert path.read_text(encoding="utf-8") == raw


# ---------------------------------------------------------------------------
# TEST 6 -- schema 2 holds several providers, and only lowers
# ---------------------------------------------------------------------------
def test_v2_override_holds_several_providers_and_only_lowers(
        monkeypatch, tmp_path):
    """The self-throttle survives as a PER-PROVIDER declaration: ollama-cloud
    throttled to 5 (below its $100 row of 8, so honoured) while deepseek-direct
    declares 9999 (above its Flash row of 2500, so clamped down). Neither
    statement touches the other provider.

    MUTATION CAUGHT ON PRISTINE eaedc0633: read_override() understood only the
    flat v1 shape, so this file resolved provider=None with no max_concurrent
    at the top level and collapsed the whole box to DEFAULT_CONSERVATIVE = 3 --
    a client who declared two accounts got neither."""
    cfg = _isolate(monkeypatch, tmp_path)
    capacity.override_path(cfg).write_text(json.dumps({
        "schema": 2,
        "providers": {
            "ollama-cloud": {"plan": "$100/month", "max_concurrent": 5},
            "deepseek-direct": {"plan": "v4-flash", "max_concurrent": 9999},
        },
    }), encoding="utf-8")

    # Behavioural, signature-independent: on pristine main read_override()
    # understood only the flat shape, so this whole file resolved to
    # DEFAULT_CONSERVATIVE = 3. With no primary route detected, the FIRST
    # provider the operator declared is the one the no-arg call answers about.
    assert capacity.probe(cfg)["available"] == 5
    assert capacity.probe(cfg)["available"] != capacity.DEFAULT_CONSERVATIVE

    assert capacity.probe(cfg, provider="ollama-cloud")["available"] == 5
    assert capacity.probe(cfg, provider="deepseek-direct")["available"] == 2500


def test_declare_capacity_merges_and_never_clobbers_another_provider(
        monkeypatch, tmp_path):
    """A second declaration is a statement about a second account, not a
    replacement for the first. Clobbering is the file-level shape of the same
    defect: one provider's number standing in for the whole box."""
    cfg = _isolate(monkeypatch, tmp_path)
    capacity.declare_capacity("ollama-cloud", plan="$100/month", config_dir=cfg)
    capacity.declare_capacity("deepseek-direct", max_concurrent=9, config_dir=cfg)

    doc = json.loads(capacity.override_path(cfg).read_text(encoding="utf-8"))
    assert doc["schema"] == capacity.OVERRIDE_SCHEMA, doc
    assert set(doc["providers"]) == {"ollama-cloud", "deepseek-direct"}, doc
    assert capacity.probe(cfg, provider="ollama-cloud")["available"] == 8
    assert capacity.probe(
        cfg, provider="deepseek-direct", model="deepseek-v4-flash"
    )["available"] == 9


def test_declare_capacity_refuses_an_unidentified_provider(monkeypatch, tmp_path):
    """A declaration has to say WHICH account it is about. Writing one that
    does not is how dispatcher.ensure_capacity_override PARKed every run by
    hard-coding a provider it had not established."""
    cfg = _isolate(monkeypatch, tmp_path)
    with pytest.raises(ValueError):
        capacity.declare_capacity("some-random-unknown-llm",
                                  max_concurrent=40, config_dir=cfg)
    assert not capacity.override_path(cfg).is_file()
    with pytest.raises(ValueError):
        capacity.declare_capacity("ollama-cloud", config_dir=cfg)
    assert not capacity.override_path(cfg).is_file()


def test_persist_plan_answer_alias_still_works(monkeypatch, tmp_path):
    """The old name stays callable with its old positional signature -- a
    rename is not a licence to break every caller that already exists."""
    cfg = _isolate(monkeypatch, tmp_path)
    written = capacity.persist_plan_answer("ollama-cloud", "$100", cfg)
    assert written.is_file()
    assert capacity.probe(cfg)["available"] == 8


# ---------------------------------------------------------------------------
# TEST 8 -- the operator reserve does not depend on the override file
# ---------------------------------------------------------------------------
def _profile_only_ollama_100(cfg):
    """A profile carrying the $100 answer and NOTHING else -- written straight
    into the store rather than through record_plan_answer(), so this proof
    holds identically on pristine main (where record_plan_answer also wrote an
    override file) and on this branch (where it does not). The point is what
    the GOVERNOR reads, not who wrote it."""
    profile = resource_profile.load_profile(cfg)
    resource_profile.upsert_provider(
        profile, "ollama-cloud", plan_tier="$100/month", plan_known=True,
        concurrency_ceiling=capacity.CAP_TABLE[("ollama-cloud", "$100/month")],
        ceiling_source="cap-table", locked=True)
    resource_profile.save_profile(profile, cfg)
    return profile


def test_governor_reserve_does_not_depend_on_the_override_file(
        monkeypatch, tmp_path):
    """OPERATOR RULING, restated verbatim 2026-09-07: "ollama 20 dollar plan
    is 3 agents max ollama 100 a month plan is 8" and "i said 8 so that 2 are
    left over for other work".

    THIS TEST PASSES ON PRISTINE eaedc0633 ON PURPOSE. It is not a defect
    proof, it is the regression guard on the ruling: with NO capacity_override
    .json anywhere, the profile alone must still hand the governor
    rps 8 / max_inflight 8 -- so deleting the interview's projection into that
    file (F2) cannot cost the client their reserve. A guard that only passed
    after the change would prove nothing about what the change preserved.

    Its anti-vacuity companion below proves this assertion CAN fail."""
    cfg = _isolate(monkeypatch, tmp_path)
    _profile_only_ollama_100(cfg)
    assert not capacity.override_path(cfg).is_file(), (
        "this proof is about the PROFILE; an override file would make it vacuous")

    conf = governor.provider_config("ollama-cloud")
    assert conf["max_inflight"] == 8, conf
    assert conf["rps"] == 8.0, conf
    assert capacity.CAP_TABLE[("ollama-cloud", "$100/month")] == 8
    assert capacity.CAP_TABLE[("ollama-cloud", "$20/month")] == 3


def test_the_reserve_proof_is_not_vacuous(monkeypatch, tmp_path):
    """THE ANTI-VACUITY CHECK for the test above. Delete the profile entry the
    reserve is supposed to come from and the same assertion MUST fail --
    otherwise that test would be passing on the providers.yaml defaults and
    proving nothing about the operator's 8."""
    cfg = _isolate(monkeypatch, tmp_path)
    _profile_only_ollama_100(cfg)
    assert governor.provider_config("ollama-cloud")["max_inflight"] == 8

    profile = resource_profile.load_profile(cfg)
    del profile["providers"]["ollama-cloud"]
    resource_profile.save_profile(profile, cfg)

    conf = governor.provider_config("ollama-cloud")
    assert conf["max_inflight"] != 8, (
        "with the profile entry gone the reserve must NOT still read 8 -- if it "
        "does, the reserve proof above is measuring something else")


def test_record_plan_answer_still_feeds_the_reserve(monkeypatch, tmp_path):
    """...and the interview path still lands on the same number. F2 removed a
    WRITE (the capacity_override.json projection); it must not have removed
    the CAP_TABLE concurrency_ceiling write the governor reads."""
    cfg = _isolate(monkeypatch, tmp_path)
    resource_profile.record_plan_answer("ollama-cloud", "$100/month", cfg)
    conf = governor.provider_config("ollama-cloud")
    assert conf["max_inflight"] == 8, conf
    assert conf["rps"] == 8.0, conf


# ---------------------------------------------------------------------------
# TEST 9 -- ask-once is the profile lock, and only the profile lock
# ---------------------------------------------------------------------------
def test_ask_once_is_the_profile_lock_only(monkeypatch, tmp_path):
    """The two gates encoded ONE fact -- "the client answered once" -- in two
    files, and the second was single-provider, so its existence was misread as
    "measured for every provider". That misreading IS the defect. One store,
    one lock, per provider."""
    cfg = _isolate(monkeypatch, tmp_path)
    detection = {"provider": "ollama-cloud", "detected": True}
    assert resource_profile.pending_questions(
        detection=detection, config_dir=cfg), "the question is owed before it is answered"

    resource_profile.record_plan_answer("ollama-cloud", "$100/month", cfg)

    assert resource_profile.pending_questions(config_dir=cfg) == []
    assert resource_profile.pending_questions(
        detection=detection, config_dir=cfg) == []
    assert resource_profile.is_plan_locked("ollama-cloud", config_dir=cfg)

    # A probe refresh must not unsettle the lock...
    resource_profile.apply_probe_refresh({"provider": "ollama-cloud"},
                                         config_dir=cfg)
    assert resource_profile.pending_questions(
        detection=detection, config_dir=cfg) == []

    # ...and there is no file whose absence could re-arm the question.
    assert not capacity.override_path(cfg).is_file()
    assert capacity.probe(cfg, provider="ollama-cloud")["interview_question"] is None


def test_an_unanswered_provider_still_parks(monkeypatch, tmp_path):
    """The control for the test above: removing the file-existence gate must
    not remove the GATE. A cap-table provider nobody has answered for still
    PARKs behind its one-time question -- capacity is never guessed upward."""
    cfg = _isolate(monkeypatch, tmp_path)
    parked = capacity.probe(cfg, provider="ollama-cloud")
    assert parked["status"] == capacity.STATUS_PARKED, parked
    assert parked["available"] is None, parked
    assert parked["autofail_code"] == "AF-CAPACITY-UNMEASURED", parked
    assert "Which plan is your ollama-cloud account on?" in parked["interview_question"]


# ---------------------------------------------------------------------------
# TEST 12 -- the report names every provider
# ---------------------------------------------------------------------------
def test_capacity_report_lists_every_provider(monkeypatch, tmp_path):
    """MUTATION CAUGHT ON PRISTINE eaedc0633: the report printed ONE
    "Provider:" line and ONE "Dispatchable:" number, so an operator looking at
    a box pinned to 8 by an ollama answer had nothing on screen telling them
    their DeepSeek routes were the ones being capped."""
    cfg = _isolate(monkeypatch, tmp_path)
    _deepseek_box(monkeypatch, tmp_path)
    resource_profile.record_plan_answer("ollama-cloud", "$100/month", cfg)
    profile = resource_profile.load_profile(cfg)
    resource_profile.upsert_provider(profile, "deepseek-direct",
                                     plan_tier="v4-flash", plan_known=True,
                                     concurrency_ceiling=2500,
                                     ceiling_source="cap-table")
    resource_profile.save_profile(profile, cfg)

    report = capacity.format_report(capacity.probe(cfg))
    rows = [line.strip() for line in report.splitlines()
            if line.startswith("  ") and ": plan " in line]
    named = {row.split(":", 1)[0] for row in rows}
    assert {"ollama-cloud", "deepseek-direct"} <= named, report
    assert any(r.startswith("ollama-cloud:") and "ceiling 8" in r for r in rows), rows
    assert any(r.startswith("deepseek-direct:") and "ceiling 2500" in r
               for r in rows), rows
