#!/usr/bin/env python3
"""WWFIX-U1 acceptance tests: the D2 three-version money-safety trap, the D1 rap
floor, the story gates, the pace gate, the fail-closed rap check, the provider
overlap receipt and the words-versus-music label.

Extended by the WW-PREVENT-RECURRENCE wave (Unit U1, package arc-revision-battery):
WW-10 (three DISTINCT initial identities, integer microseconds, 0.999 s FAILS),
WW-03 (the performed-beat manifest and the creative fingerprint, from ONE source),
WW-11 (parity release check, judge-path gate-removal and delivery-boundary tests)
and WW-19 (the import audit of the six referenced module paths).

ONE battery: this file. No second framework, no second suite.

Every threshold these tests pin is a NEW ACCEPTANCE RULE added by WWFIX-U1 or by
the WW wave, not a measured limit of an earlier run.

SCOPE HONESTY. The six modules the WW specification references land with the four
concurrent packages of this same unit. This battery owns three of them
(``music_qc/pace_change.py``, ``song_choices/overlap.py`` and THIS file); the other
three (``music_qc/rap_check.py``, ``story_coverage/story_coverage.py`` and
``story_coverage/__init__.py``) land with the packages that own them. A test whose
dependency has not landed yet is reported as UNDETERMINED -- never as a PASS and
never as a silent FAIL -- so the battery stays green on a partial landing while
still refusing the moment the dependent code is present and wrong. The import
audit (WW-19) reports exactly which of the six exist.

Run: python3 core/music_qc/test_wwfix_u1.py
"""
import argparse
import datetime
import hashlib
import importlib
import importlib.util
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
SKILL_ROOT = os.path.dirname(os.path.dirname(CORE))
for sub in ("", "intake_preflight"):
    sys.path.insert(0, os.path.join(CORE, sub))

FAILURES = []
UNDETERMINED = []


def check(cond, label):
    if cond:
        print("ok   %s" % label)
    else:
        print("FAIL %s" % label)
        FAILURES.append(label)


def undetermined(label, why):
    print("UNDETERMINED %s: %s" % (label, why))
    UNDETERMINED.append("%s (%s)" % (label, why))


def gate(cond, label, why):
    """Guard: a missing (not-yet-published) dependency is UNDETERMINED, never a
    pass; a present-but-wrong dependency is a real FAIL."""
    if cond:
        return True
    undetermined(label, why)
    return False


def _try(name):
    try:
        return importlib.import_module(name)
    except Exception:
        return None


def _load_path(rel):
    """Load a module from a file path so the battery never depends on a package
    __init__ that lands with another work package."""
    p = os.path.join(CORE, rel)
    if not os.path.exists(p):
        return None
    mod = "dsaf_" + rel.replace("/", "_").replace(".", "_")
    try:
        spec = importlib.util.spec_from_file_location(mod, p)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m
    except Exception:
        return None


LF = _try("length_formula")
SCT = _try("song_contract")
R = _try("suno_recipe")
SD = _try("song_dispatch")
SC = _try("song_choices.song_choices")
OV = _load_path("song_choices/overlap.py")
PC = _load_path("music_qc/pace_change.py")
RC = _load_path("music_qc/rap_check.py")
SV = _load_path("story_coverage/story_coverage.py")
SA = _load_path("story_arc/story_arc.py")

SC_D2 = SC is not None and all(hasattr(SC, a) for a in (
    "run_unit", "generate_choices", "cmd_generate", "fan_in", "deliver_choices",
    "plan_units", "_require_three", "ChoiceError"))
LF_RAP = LF is not None and all(hasattr(LF, a) for a in (
    "rap_floor_s", "rap_floor_words", "assert_rap_floor", "RapFloorError")) \
    and SCT is not None and hasattr(SCT, "rap_floor_for")
SCT_SHEET = SCT is not None and hasattr(SCT, "check_sheet") and R is not None
RAP_AUDIO = RC is not None and hasattr(RC, "gate") and hasattr(RC, "classify")


CLIENT = ("I am not small. I never was. One seed of truth made me strong. "
          "She Found Power in the Climb.")
HOOK = ["I am not sma-a-all", "I ne-ever wa-a-as"]
SHEET_RNB = [{"tag": "Intro", "delivery": "spoken", "lines": ["One closed door."]},
             {"tag": "Vocalise", "delivery": "sung", "lines": ["Oo-o-o-o-o-oh,"]},
             {"tag": "Verse", "delivery": "sung",
              "lines": ["And I rise above the pa-a-ain,", "Through the dark I walk alo-o-one,"]},
             {"tag": "Hook 1", "delivery": "sung", "lines": HOOK},
             {"tag": "Verse", "delivery": "sung",
              "lines": ["One seed of truth made me stro-o-ong,", "I hold the light I found,",
                        "I walk free,"]},
             {"tag": "Hook 2", "delivery": "sung", "lines": HOOK},
             {"tag": "Hook 3", "delivery": "sung", "lines": HOOK},
             {"tag": "Verse", "delivery": "rap",
              "lines": ["Backup shoes, backup jacket, but no backup plan,",
                        "So I count what I make and not what they take today,"]}]
HOOK_PLAN = {"true_at_beat": "the_world"}
SPOKEN_RANGE = (15, 20)


def _reqs():
    return SC.build_requests("rnb-flow", SHEET_RNB, CLIENT, "T", 58, hook_plan=HOOK_PLAN)


def _plan():
    return {"delivered_s": 58, "style_id": "rnb-flow",
            "sheet_text": R.render_lyrics(SHEET_RNB, "rnb-flow"), "hook_plan": HOOK_PLAN}


def _spec_file(tmp):
    path = os.path.join(tmp, "req.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"style_id": "rnb-flow", "client_text": CLIENT, "title": "T",
                   "length_s": 58, "hook_plan": HOOK_PLAN,
                   "input": {"lyrics": R.render_lyrics(SHEET_RNB, "rnb-flow"),
                             "style_id": "rnb-flow", "duration": 58, "vocal_gender": "f"}}, f)
    return path


# ---- D2: the three-version money-safety trap ------------------------------

def test_d2_per_unit_selector_dispatches_one_and_the_umbrella_three():
    if not gate(SC_D2, "D2 per-unit/umbrella", "song_choices D2 API not yet published"):
        return
    reqs = _reqs()
    kw = dict(plan=_plan(), measure=lambda t: {}, save=lambda v, t, r: None,
              script_words=CLIENT, hook_text="", spoken_range_pct=SPOKEN_RANGE)
    u_calls, u_gen = _counting_generate()
    unit = SC.run_unit(reqs, unit_id="WW-002", generate=u_gen, **kw)
    a_calls, a_gen = _counting_generate()
    every = SC.generate_choices(reqs, generate=a_gen, **kw)
    check(len(unit) == 1 and len(every) == 3,
          "D2: the per-unit path runs 1 variant, the umbrella runs 3 (%d/%d)"
          % (len(unit), len(every)))
    check(set(u_calls["variants"]) == {reqs[1][0]["id"]},
          "D2: --unit-id WW-002 touches ONLY variant #2 (%r)" % (u_calls["variants"],))
    check(u_calls["n"] * 3 == a_calls["n"] and u_calls["n"] > 0,
          "D2: the umbrella generates exactly 3x the unit, never 9x (%d vs %d)"
          % (u_calls["n"], a_calls["n"]))


def _counting_generate():
    calls = {"n": 0, "variants": []}

    def generate(variant, request):
        calls["n"] += 1
        calls["variants"].append(variant["id"])
        return []
    return calls, generate


def test_d2_cmd_generate_reports_the_dispatch_count_it_actually_made():
    if not gate(SC_D2, "D2 cmd_generate", "song_choices D2 API not yet published"):
        return
    for flag, want in (("WW-001", 2), ("", 6)):
        with tempfile.TemporaryDirectory() as tmp:
            a = argparse.Namespace(run_dir=tmp, request=_spec_file(tmp), ledger="",
                                   run_id="R", variant="", unit_id=flag)
            calls, gen = _counting_generate()
            out = SC.cmd_generate(a, generate=gen, measure=lambda t: {},
                                  save=lambda v, t, r: None, plan=_plan())
            check(out["dispatched"] == calls["n"] == want,
                  "D3: cmd_generate --unit-id %r reports the %d provider jobs it ran"
                  % (flag or "none", want))
            if not flag:
                check(out["media_concurrency"] == 3 and out["builder_agent_units"] == 1,
                      "D2: the umbrella receipt says 3 threads inside ONE agent unit")


def test_d2_fan_in_never_generates_and_the_plan_names_three_units():
    if not gate(SC_D2, "D2 fan_in/plan_units", "song_choices D2 API not yet published"):
        return
    reqs = _reqs()
    import inspect
    for fn, label in ((SC.fan_in, "fan_in"), (SC.deliver_choices, "deliver_choices")):
        params = set(inspect.signature(fn).parameters)
        check("generate" not in params and "kie" not in params,
              "D2: %s takes no generate callable -- it can only CHECK and DELIVER" % label)
    with tempfile.TemporaryDirectory() as tmp:
        try:
            SC.fan_in([{"status": "PASS", "variant": {"id": v}, "take": None,
                        "receipts": []} for v in ("a", "b", "c")], tmp,
                      os.path.join(tmp, "d"), send=lambda *a2: None)
        except SC.ChoiceError:
            check(True, "D2: fan-in with no delivered take refuses instead of generating")
        else:
            check(False, "D2: fan-in accepted three empty results")
    units = SC.plan_units("/run", reqs)
    check([u["unit_id"] for u in units["units"]] == ["WW-001", "WW-002", "WW-003"],
          "D2: the unit plan is WW-001..003")
    check(all(u["owned_requests"] == 1 for u in units["units"])
          and units["reserve"] == 0 and units["provider_slots"] == 3,
          "D2: providerSlots 3, reserve 0, ONE owned request per unit")
    check(units["builder_agent_units"] == 3 and units["media_concurrency"] == 3,
          "D2: 3 provider jobs and 3 agent units are reported as separate facts")
    check(len({u["owned_folder"] for u in units["units"]}) == 3,
          "D2: each unit owns its own folder")


def test_d2_require_three_refuses_before_any_spend():
    if not gate(SC_D2, "D2 _require_three", "song_choices D2 API not yet published"):
        return
    reqs = _reqs()
    for rows, label in ((reqs[:2], "two rows"), (reqs + reqs[:1], "four rows"),
                        ([reqs[0], reqs[0], reqs[1]], "a repeated variant")):
        try:
            SC._require_three(rows, key=lambda r: r[0]["id"])
        except SC.ChoiceError:
            check(True, "D2: _require_three refuses %s" % label)
        else:
            check(False, "D2: _require_three accepted %s" % label)
    try:
        SC.run_unit(reqs, plan=_plan(), generate=lambda v, r: [], measure=lambda t: {},
                    save=lambda v, t, r: None, script_words=CLIENT, hook_text="")
    except SC.ChoiceError:
        check(True, "D2: a worker with no --variant/--unit-id is refused")
    else:
        check(False, "D2: a worker with no --variant/--unit-id was allowed")


def test_d2_cmd_next_exposes_one_mode_at_a_time():
    F = _try("intake_preflight.factory") or _try("factory")
    if not gate(SC_D2 and F is not None and hasattr(F, "_song_choices_next"),
                "D2 cmd_next", "the D2 next-mode wiring is not yet published"):
        return
    with tempfile.TemporaryDirectory() as tmp:
        SC.init(tmp, True)
        umb = F._song_choices_next(tmp, orchestrated=False)
        orch = F._song_choices_next(tmp, orchestrated=True)
    check(umb and umb["mode"] == "umbrella" and umb["command"] == umb["umbrella_command"]
          and not any(u["selected"] for u in umb["units"]),
          "D2: umbrella mode selects the umbrella command and NO unit")
    check(orch and orch["mode"] == "orchestrated" and orch["command"] == ""
          and all(u["selected"] for u in orch["units"])
          and len(orch["units"]) == 3,
          "D2: orchestrated mode selects the three units and NOT the umbrella")
    check("nine" in umb["note"] and umb["overlap_min_s"] == 1.0,
          "D2: the mode note names the nine-generation trap")


# ---- D2 item 3: the provider-overlap receipt -------------------------------

def _receipts(base, seconds, attempt_ids=("a1", "a2", "a3"), initial=True, variants=None):
    t0 = base
    out = []
    for i, aid in enumerate(attempt_ids):
        v = variants[i] if variants and i < len(variants) else "variant-%s" % aid
        out.append(OV.make_receipt(v, {"k": i}, "logical", aid, "task-%s" % aid,
                                   t0, t0 + datetime.timedelta(seconds=seconds),
                                   initial=initial))
    return out


def test_overlap_gate_boundary_and_fail_closed():
    """min(terminal_at) - max(accepted_submit_at) over the THREE INITIAL attempts:
    PASS at exactly 1.000 s, FAIL at 0.999 s and at zero, and UNAVAILABLE -- never
    a pass -- without the evidence."""
    if not gate(OV is not None, "overlap gate", "song_choices/overlap.py not present"):
        return
    base = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)
    at_1 = OV.overlap_gate(_receipts(base, 1.0))
    check(at_1["verdict"] == "PASS" and at_1["overlap_s"] == 1.0,
          "D2: exactly 1.000 s of provider overlap is a PASS (%r)" % (at_1["overlap_s"],))
    below = OV.overlap_gate(_receipts(base, 0.999))
    check(below["verdict"] == "FAIL",
          "D2: 0.999 s is a FAIL (%r, %r us)" % (below["verdict"], below.get("overlap_us")))
    zero = OV.overlap_gate(_receipts(base, 0.0))
    check(zero["verdict"] == "FAIL", "D2: zero overlap is a FAIL")
    short = OV.overlap_gate(_receipts(base, 5.0)[:2])
    check(short["verdict"] == "UNAVAILABLE",
          "D2: fewer than three INITIAL attempts is UNAVAILABLE, never a pass")
    regen = OV.overlap_gate(_receipts(base, 5.0, attempt_ids=("a4", "a5", "a6"), initial=False))
    check(regen["verdict"] == "UNAVAILABLE",
          "D2: regenerated attempts never stand in for the three initial ones")
    naive = [dict(r, submitted_at=r["submitted_at"].replace("Z", ""),
                  accepted_submit_at=r["accepted_submit_at"].replace("Z", ""),
                  terminal_at=r["terminal_at"].replace("Z", ""), receipt_sha256=None)
             for r in _receipts(base, 5.0)]
    check(OV.overlap_gate(naive)["verdict"] == "UNAVAILABLE",
          "D2: an unlabelled/naive clock is not admissible evidence")
    local = [dict(r, timestamp_source="local", receipt_sha256=None)
             for r in _receipts(base, 5.0)]
    check(OV.overlap_gate(local)["verdict"] == "UNAVAILABLE",
          "D2: a receipt labelled with a LOCAL clock is not admissible evidence")
    check(at_1["requires_owner_authority"] is True and at_1["paid_redo"] is False,
          "D2: the gate never authorises a paid redo on its own")


# ---- WW-10: three DISTINCT identities, integer microseconds ---------------

def test_ww10_three_distinct_identities_are_required():
    """WW-10: the gate needs EXACTLY three DISTINCT (variant, attempt, task)
    identities. Two receipts sharing a task id, a repeated variant, or a repeated
    attempt FAIL -- they never PASS."""
    if not gate(OV is not None, "WW-10 distinctness", "song_choices/overlap.py not present"):
        return
    base = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)
    good = OV.overlap_gate(_receipts(base, 5.0))
    check(good["verdict"] == "PASS" and len(good["distinct_identities"]) == 3,
          "WW-10: three distinct task ids PASS (%r)" % (good["distinct_identities"],))
    dup_task = [dict(r) for r in _receipts(base, 5.0)]
    dup_task[1]["task_id"] = dup_task[0]["task_id"]
    g = OV.overlap_gate(dup_task)
    check(g["verdict"] == "FAIL" and g["reason_code"] == "OVERLAP_IDENTITY_DUPLICATE",
          "WW-10: two receipts sharing a task id FAIL (%r)" % (g["verdict"],))
    same_identity = [dict(r) for r in _receipts(base, 5.0)]
    same_identity[2].update(attempt_id=same_identity[0]["attempt_id"],
                            task_id=same_identity[0]["task_id"],
                            variant_id=same_identity[0]["variant_id"])
    check(OV.overlap_gate(same_identity)["verdict"] == "FAIL",
          "WW-10: a repeated (variant, attempt, task) identity FAILS")
    no_var = [dict(r) for r in _receipts(base, 5.0)]
    no_var[1]["variant_id"] = None
    check(OV.overlap_gate(no_var)["verdict"] == "UNAVAILABLE",
          "WW-10: an identity with no variant id is UNAVAILABLE, never a pass")


def test_ww10_microseconds_no_rounding_and_0999_fails():
    """WW-10: the comparison is INTEGER MICROSECONDS with no rounding. 999,999 us
    FAILS; 1,000,000 us PASSes -- 0.999999 s can never become 1.0."""
    if not gate(OV is not None, "WW-10 microseconds", "song_choices/overlap.py not present"):
        return
    base = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)
    just_below = OV.overlap_gate(_receipts(base, 0.999999))
    check(just_below["verdict"] == "FAIL" and just_below["overlap_us"] == 999999,
          "WW-10: 999,999 us FAILS with no rounding (%r us)" % (just_below["overlap_us"],))
    at_floor = OV.overlap_gate(_receipts(base, 1.0))
    check(at_floor["verdict"] == "PASS" and at_floor["overlap_us"] == 1000000,
          "WW-10: exactly 1,000,000 us PASSes")
    check(OV.MIN_OVERLAP_US == 1_000_000 and at_floor["microseconds_compared_without_rounding"],
          "WW-10: the floor is declared in microseconds and the comparison states so")


def test_ww10_malformed_reversed_duplicated_digest_all_fail():
    """WW-10: MISSING lifecycle evidence is UNAVAILABLE; MALFORMED, REVERSED,
    DUPLICATED and DIGEST-MISMATCHED evidence is FAIL."""
    if not gate(OV is not None, "WW-10 malformed", "song_choices/overlap.py not present"):
        return
    base = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)
    reversed_r = [dict(r, receipt_sha256=None) for r in _receipts(base, 5.0)]
    reversed_r[0]["terminal_at"] = "2025-12-31T00:00:00.000Z"     # before its submit
    g = OV.overlap_gate(reversed_r)
    check(g["verdict"] == "FAIL" and g["reason_code"] == "OVERLAP_EVIDENCE_REVERSED",
          "WW-10: a reversed timestamp FAILS (%r)" % (g["reason_code"],))
    malformed = [dict(r, receipt_sha256=None) for r in _receipts(base, 5.0)]
    malformed[0]["terminal_at"] = "not-a-timestamp"
    g = OV.overlap_gate(malformed)
    check(g["verdict"] == "FAIL" and g["reason_code"] == "OVERLAP_EVIDENCE_MALFORMED",
          "WW-10: a malformed timestamp FAILS (%r)" % (g["reason_code"],))
    tampered = [dict(r) for r in _receipts(base, 5.0)]
    tampered[1]["terminal_at"] = "2026-01-01T00:00:05.500Z"       # edited after the digest
    g = OV.overlap_gate(tampered)
    check(g["verdict"] == "FAIL" and g["reason_code"] == "OVERLAP_DIGEST_MISMATCH",
          "WW-10: a digest-mismatched receipt FAILS (%r)" % (g["reason_code"],))
    four = OV.overlap_gate(_receipts(base, 5.0, attempt_ids=("a1", "a2", "a3", "a4")))
    check(four["verdict"] == "FAIL", "WW-10: four initial rows FAIL")
    missing = [dict(r, receipt_sha256=None) for r in _receipts(base, 5.0)]
    missing[2]["terminal_at"] = None
    check(OV.overlap_gate(missing)["verdict"] == "UNAVAILABLE",
          "WW-10: a missing terminal stamp is UNAVAILABLE, never a pass")


def test_ww10_scope_is_honest_concurrency_evidence():
    """WW-10: the fix is scoped as a CONCURRENCY-EVIDENCE fix and carries no
    automatic paid redo."""
    if not gate(OV is not None, "WW-10 scope", "song_choices/overlap.py not present"):
        return
    base = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)
    g = OV.overlap_gate(_receipts(base, 5.0))
    check(g.get("scope") == "CONCURRENCY_EVIDENCE" and g.get("paid_redo") is False
          and g.get("preserve_paid_tracks") is True,
          "WW-10: scope is CONCURRENCY_EVIDENCE, no paid redo, paid tracks preserved")


# ---- WW-03 / WW-15: the performed-beat manifest and the fingerprint --------

def _manifest_source(lines_by_beat, delivery="sung", devices=None):
    return {b: {"lines": lines_by_beat.get(b, []), "delivery": delivery,
                "devices": (devices or {}).get(b, [])} for b in SA.BEATS}


def _aligned(text, start=0.0, step=0.3):
    out = []
    for i, w in enumerate(str(text).split()):
        out.append({"word": w, "startS": start + i * step, "endS": start + i * step + 0.2})
    return out


def test_ww03_manifest_covers_all_twelve_beats_from_one_source():
    """WW-03: ONE source -> the performed-beat manifest for ALL TWELVE canonical
    beats; the fingerprint covers lines, delivery, beat map, hook and pace."""
    if not gate(SA is not None, "WW-03 manifest", "story_arc.py not present"):
        return
    lines = {b: ["line for %s" % b] for b in SA.BEATS}
    man = SA.build_manifest(_manifest_source(lines))
    check(man["beat_count"] == 12 and len(man["beats"]) == 12
          and man["present_count"] == 12 and not man["missing"],
          "WW-03: the manifest covers all twelve canonical beats from ONE source")
    fp = SA.creative_fingerprint(man)
    check(fp["components"] == ["lines", "delivery", "beat_map", "hook", "pace"]
          and isinstance(fp["sha256"], str) and len(fp["sha256"]) == 64,
          "WW-03: the fingerprint covers lines, delivery, beat map, hook and pace")
    src2 = dict(_manifest_source(lines))
    src2[SA.BEATS[3]] = {"lines": ["a different wound line"], "delivery": "sung"}
    check(SA.build_manifest(src2)["fingerprint"] != man["fingerprint"],
          "WW-03: editing ONE line changes the fingerprint")


def test_ww03_metadata_only_twelve_identifiers_do_not_pass():
    """A metadata-only twelve-identifier list (ids but no heard lines) must NOT
    pass -- it is MANIFEST_METADATA_ONLY, never a pass."""
    if not gate(SA is not None, "WW-03 metadata-only", "story_arc.py not present"):
        return
    ids_only = {b: {"line_ids": ["id-%s" % b]} for b in SA.BEATS}
    man = SA.build_manifest(ids_only)
    binding = SA.bind_revision("rev-3", man)
    g = SA.check_performed_manifest(man, binding, _aligned("anything at all"))
    check(g["verdict"] == "FAIL"
          and any(x == "MANIFEST_METADATA_ONLY" for x in g["failed"]),
          "WW-03: a metadata-only twelve-identifier list is refused (%r)" % (g["failed"],))


def test_ww03_the_shipped_take_is_refused_on_missing_devices():
    """The stored take carries only ONE of the seven approved devices, so six
    required devices are missing and the performed gate refuses it."""
    if not gate(SA is not None, "WW-03 devices", "story_arc.py not present"):
        return
    seven = ["The book showed me the way", "The mirror named the pattern",
             "The mentor held the light", "The wound had a name",
             "The climb was mine", "The doubt was loud", "The call came at dawn"]
    lines = {b: ["line for %s" % b] for b in SA.BEATS}
    lines[SA.BEATS[0]] = ["The book showed me the way"]
    man = SA.build_manifest(_manifest_source(lines))
    binding = SA.bind_revision("rev-3", man)
    heard = (_aligned(" ".join(" ".join(lines[b]) for b in SA.BEATS))
             + _aligned("stray filler", start=400.0))
    g = SA.check_performed_manifest(man, binding, heard, required_devices=seven)
    check(g["verdict"] == "FAIL"
          and sum(1 for x in g["failed"] if x.startswith("DEVICE_MISSING")) == 6,
          "WW-03: the shipped take with 1 of 7 devices is refused (%d missing)"
          % sum(1 for x in g["failed"] if x.startswith("DEVICE_MISSING")))


def test_ww03_reorder_and_fingerprint_mismatch_fail():
    """WW-03: a reordered line FAILS, and a take whose stored fingerprint does not
    match the approved sheet is refused -- never retroactively re-bound."""
    if not gate(SA is not None, "WW-03 reorder/fingerprint", "story_arc.py not present"):
        return
    lines = {b: ["line for %s" % b] for b in SA.BEATS}
    man = SA.build_manifest(_manifest_source(lines))
    binding = SA.bind_revision("rev-3", man)
    in_order = _aligned(" ".join(" ".join(lines[b]) for b in SA.BEATS))
    ok = SA.check_performed_manifest(man, binding, in_order)
    check(ok["verdict"] == "PASS" and ok["reason_code"] == "PERFORMED_STORY_COVERED",
          "WW-03: all twelve lines heard in order PASS with a matching fingerprint")
    swapped = list(SA.BEATS)
    swapped[1], swapped[2] = swapped[2], swapped[1]
    reordered = _aligned(" ".join(" ".join(lines[b]) for b in swapped))
    bad = SA.check_performed_manifest(man, binding, reordered)
    check(bad["verdict"] == "FAIL", "WW-03: a line reordered FAILS")
    edited = SA.build_manifest(_manifest_source(dict(lines, **{SA.BEATS[0]: ["a new opener"]})))
    mismatch = SA.check_performed_manifest(man, SA.bind_revision("rev-4", edited), in_order)
    check(mismatch["verdict"] == "FAIL" and "FINGERPRINT_MISMATCH" in mismatch["failed"],
          "WW-03: a take whose fingerprint does not match the approved sheet is refused")
    stale = SA.assert_take_bound({"fingerprint": "deadbeef"}, man)
    check(stale["verdict"] == "FAIL" and stale["reason_code"] == "FINGERPRINT_MISMATCH",
          "WW-15: an existing take is NEVER retroactively bound to an edited sheet")
    check(SA.assert_take_bound({"fingerprint": man["fingerprint"]}, man)["verdict"] == "PASS",
          "WW-15: a take matching the approved revision PASSes")


def test_ww03_counts_are_named_and_distinct_never_relabelled():
    """WW-03: the fifteen-stage source method, the eight coarse timing stages and
    the twelve canonical beats are preserved through explicit NAMED mappings and
    never by relabelling one count as another."""
    if not gate(SA is not None, "WW-03 stage mapping", "story_arc.py not present"):
        return
    rep = SA.stage_mapping_report()
    check(rep["source_method_stage_count"] == 15 and rep["timing_stage_count"] == 8
          and rep["canonical_beat_count"] == 12,
          "WW-03: 15 source-method stages, 8 timing stages, 12 canonical beats")
    check(rep["counts_are_distinct"] and rep["mapped_by_name_not_by_count"],
          "WW-03: the three counts are distinct and mapped BY NAME")
    check(all(b in rep["beat_to_timing"] and rep["beat_to_timing"][b] in rep["timing_stages"]
              for b in rep["canonical_beats"]),
          "WW-03: every canonical beat names a real coarse timing stage")


def test_ww03_pace_component_is_one_source():
    """The fingerprint's pace component is defined once, in music_qc/pace_change."""
    if not gate(PC is not None and hasattr(PC, "pace_fingerprint_component"),
                "WW-03 pace component", "music_qc/pace_change.py not present"):
        return
    a = PC.pace_fingerprint_component({"reason": "the bridge lifts", "boundary_s": 40.0})
    b = PC.pace_fingerprint_component({"boundary_s": 40.0, "reason": "the bridge lifts"})
    check(a and a == b, "WW-03: the pace component is stable under key order")
    check(PC.pace_fingerprint_component(None) == ""
          and PC.canonical_pace({"pace_change": {"boundary_s": 1.0}})["drop"]
          == PC.PACE_CUE_DROP,
          "WW-03: no ordered change -> empty component; the cue names half-time")


# ---- D1: the rap floor -----------------------------------------------------

def test_d1_rap_floor_rule():
    if not gate(LF_RAP, "D1 rap floor", "the rap floor is not yet published to this package"):
        return
    check(LF.rap_floor_s(90) == 9.0 and LF.rap_floor_s(50) == 8.0,
          "D1: floor seconds = max(8.0, 10% of D)")
    check(LF.rap_floor_words("rnb-flow", 90) == LF.rap_floor_words("rnb-flow", 90)
          and LF.rap_floor_words("rnb-flow", 90)
          >= int(__import__("math").ceil(LF.rap_floor_s(90) * 2.5)),
          "D1: floor words = ceil(seconds * the style's rap rate)")
    p = LF.plan(90, style_id="rnb-flow")
    check(p.get("rap_s", 0) >= LF.rap_floor_s(90) and p["words"].get("rap", 0) > 0,
          "D1: plan(90, rnb-flow) emits a rap budget at or above the floor (%r s, %r words)"
          % (p.get("rap_s"), p["words"].get("rap")))
    check(p.get("rap_floor_s") == LF.rap_floor_s(90 - LF.END_EARLY_S) and p.get("rap_gate"),
          "D1: the plan report carries its own rap floor")
    r88 = SCT.rap_floor_for("rnb-flow", 88)
    check(r88["floor_s"] == 8.8 and r88["floor_words"] == 22,
          "D1: at D = 88 the floor is 8.8 s / 22 words (%r)" % (r88,))
    LF.assert_rap_floor(p, "rnb-flow")
    check(True, "D1: assert_rap_floor accepts a floored rapping plan")
    broken = dict(p, rap_s=0.0, words=dict(p["words"], rap=0))
    try:
        LF.assert_rap_floor(broken, "rnb-flow")
    except LF.RapFloorError:
        check(True, "D1: assert_rap_floor refuses a rap style planning ZERO rap")
    else:
        check(False, "D1: assert_rap_floor accepted a rap style planning ZERO rap")


def test_d1_rap_sheet_below_floor_is_refused_before_spend():
    if not gate(SCT_SHEET and LF_RAP, "D1 rap sheet",
                "the rap sheet floor is not yet published to this package"):
        return
    thin = [s for s in SHEET_RNB if s["delivery"] != "rap"]
    out = SCT.check_sheet(R.render_lyrics(thin, "rnb-flow"), "rnb-flow", 58)
    check(out["verdict"] == "FAIL"
          and any(r.startswith("RAP_PLANNED_ZERO_WORDS") for r in out["reasons"]),
          "D1: an R&B Flow sheet with no rap lines is refused (%r)" % (out["reasons"][:1],))
    check(out["totals"]["rap_floor_words"] == 20 and out["totals"]["rap_floor_s"] == 8.0,
          "D1: the refusal names the 58 s floor (20 rap words / 8.0 s)")
    ok = SCT.check_sheet(R.render_lyrics(SHEET_RNB, "rnb-flow"), "rnb-flow", 58)
    check(ok["verdict"] == "PASS" and ok["totals"]["rap_words"] >= 20,
          "D1: the same sheet WITH its rap floor passes (%r)" % (ok["verdict"],))
    soul = SCT.check_sheet(R.render_lyrics(SHEET_RNB, "soul-ballad"), "soul-ballad", 58)
    check(soul["verdict"] == "FAIL",
          "D1: a rap block under a style with no rap delivery is refused")


# ---- D1: the story gates ---------------------------------------------------

def _spread(words, start, step=0.4):
    return [{"word": w, "startS": start + i * step, "endS": start + i * step + 0.3}
            for i, w in enumerate(words)]


PLOT = ["one", "closed", "door", "seed", "truth"]


def test_d1_story_start_gate():
    if not gate(SV is not None, "D1 story start", "story_coverage is not yet published"):
        return
    early = _spread(["one", "closed", "door", "seed"] + ["la"] * 40, 4.0)
    g = SV.story_start_gate(early, PLOT, 58.0)
    check(g["verdict"] == "PASS" and g["first_plot_line_s"] <= 5.0,
          "D1: a plot line at %.2f s passes the 5.0 s ceiling" % g["first_plot_line_s"])
    late = _spread(["la"] * 30 + ["one", "closed", "door", "seed"], 4.0)
    g = SV.story_start_gate(late, PLOT, 58.0)
    check(g["verdict"] == "FAIL" and "FIRST_STORY_WORD_LATE" in g["failed"],
          "D1: a plot line at %.2f s FAILS the 5.0 s ceiling" % g["first_plot_line_s"])
    stray = _spread(["one"] + ["la"] * 40, 4.0)
    g = SV.story_start_gate(stray, PLOT, 58.0)
    check(g["verdict"] == "FAIL" and "NO_PLOT_LINE_SUNG" in g["failed"],
          "D1: one stray plot word is not a plot line (the false pass is closed)")
    long_open = _spread(["one", "closed", "door", "seed"], 12.0)
    g = SV.story_start_gate(long_open, PLOT, 58.0)
    check("OPENING_NON_LEXICAL_TOO_LONG" in g["failed"],
          "D1: an opening wordless span over 15%% of D FAILS")
    check(SV.story_start_gate([], PLOT, 58.0)["verdict"] == "UNAVAILABLE"
          and SV.story_start_gate(early, [], 58.0)["verdict"] == "UNAVAILABLE",
          "D1: missing evidence is UNAVAILABLE, never PASS")


def test_d1_lexical_coverage_gate():
    if not gate(SV is not None, "D1 lexical coverage", "story_coverage is not yet published"):
        return
    words = _spread(["count"] * 20, 0.0, 2.0)
    thin = SV.lexical_coverage_gate(words, 58.0)
    check(thin["verdict"] == "FAIL" and thin["vocalise_counted"] is False,
          "D1: 6.0 s of words over 58 s is below the 0.70 floor")
    fat = _spread(["count"] * 200, 0.0, 0.3)
    ok = SV.lexical_coverage_gate(fat, 58.0)
    check(ok["verdict"] == "PASS" and ok["coverage"] >= 0.70,
          "D1: %.1f s of real words over 58 s clears the 0.70 floor" % ok["lexical_s"])
    check(SV.is_vocalise("Oo-o-o-o-o-oh") and not SV.is_lexical("Oo-o-o-o-o-oh"),
          "D1: a vocalise is not a lexical word")
    voc = _spread(["Oo-o-o-o-o-oh"] * 60, 0.0, 0.7)
    check(SV.lexical_coverage_gate(voc, 58.0)["verdict"] == "FAIL",
          "D1: a sheet of vocalise alone cannot reach the coverage floor")
    check(SV.lexical_coverage_gate([], 58.0)["verdict"] == "UNAVAILABLE",
          "D1: unmeasured coverage is UNAVAILABLE, never PASS")


def test_d1_story_arc_gate():
    if not gate(SV is not None and LF is not None, "D1 story arc",
                "story_coverage is not yet published"):
        return
    beats = [(0.0, 20.0), (20.0, 40.0), (40.0, 43.0)]
    full = _spread(["count"] * 40, 0.0, 1.0)
    ok = SV.story_arc_gate(full, beats, 43.0)
    check(ok["verdict"] == "PASS" and ok["reason_code"] == SV.STORY_ARC_CODE_OK,
          "D1: every judged window carries a line")
    hole = [w for w in full if w["startS"] > 25.0]
    bad = SV.story_arc_gate(hole, beats, 43.0)
    check(bad["verdict"] == "FAIL" and bad["failed_windows"],
          "D1: a wordless 20-40 s window FAILS (the closing 3 s beat is not a hole)")
    check(SV.story_arc_gate([], beats, 43.0)["verdict"] == "UNAVAILABLE"
          and SV.story_arc_gate(full, 0, 43.0)["verdict"] == "UNAVAILABLE",
          "D1: a missing arc or alignment is UNAVAILABLE, never PASS")
    check(len(LF.STORY_ARC_U16) >= 6 and "hook" in LF.STORY_ARC_U16,
          "D1: the story arc is the u16 beat list the plan carries")


# ---- D1: the pace gate -----------------------------------------------------

def test_d1_pace_gate_controls():
    if not gate(PC is not None, "D1 pace gate", "music_qc/pace_change.py not present"):
        return
    shipped = PC.confirm_pace_change({"onset_rate": 2.0, "rms_dbfs": -14.0},
                                     {"onset_rate": 2.0, "rms_dbfs": -14.0},
                                     {"onset_rate": 2.0, "rms_dbfs": -14.0})
    check(shipped["verdict"] == "FAIL" and shipped["reason_code"] == "PACE_CHANGE_ABSENT",
          "D1: a take whose tempo ratio is 1.0 FAILS the ordered gear change")
    pair = PC.confirm_pace_change({"onset_rate": 4.0, "rms_dbfs": -14.0},
                                  {"onset_rate": 2.0, "rms_dbfs": -18.0},
                                  {"onset_rate": 4.1, "rms_dbfs": -14.5})
    check(pair["verdict"] == "PASS" and pair["onset_reduction"] >= PC.PACE_ONSET_REDUCTION
          and pair["energy_drop_db"] >= PC.PACE_ENERGY_DROP_DB,
          "D1: 50%% fewer onsets and -4 dB PASS")
    weak = PC.confirm_pace_change({"onset_rate": 4.0, "rms_dbfs": -14.0},
                                  {"onset_rate": 3.5, "rms_dbfs": -16.0},
                                  {"onset_rate": 4.0, "rms_dbfs": -14.0})
    check(weak["verdict"] == "FAIL"
          and "onset_reduction" in weak["failed"] and "energy_drop" in weak["failed"],
          "D1: a 12.5%% onset change and a -2 dB drop do NOT confirm a gear change")
    unmeasured = PC.confirm_pace_change({}, {}, {})
    check(unmeasured["verdict"] == "UNMEASURED"
          and unmeasured["reason_code"] == "PACE_EVIDENCE_UNMEASURED",
          "D1: missing onset/energy evidence is UNMEASURED, never PASS")
    check(PC.judge_plan_pace({}, {}, {}, {})["applicable"] is False,
          "D1: no ordered change in the plan = nothing to enforce")


def test_d1_pace_selftest_discriminates_and_bpm_never_passes():
    if not gate(PC is not None, "D1 pace selftest", "music_qc/pace_change.py not present"):
        return
    st = PC.selftest()
    check(st.get("pair") == "PASS" and st.get("shipped") == "FAIL"
          and st.get("bare") == "UNMEASURED",
          "D1: the pace controls discriminate (half-time PASS, shipped FAIL, "
          "bare UNMEASURED) %r" % (st,))
    fold = PC.octave_fold_bpm(85.2, 181.5)
    check(fold["same_beat"] is True and fold["grants_pass"] is False,
          "D1: 85.2 and 181.5 bpm read as the SAME beat -- bpm alone never grants PASS")
    off = PC.confirm_pace_change({"onset_rate": 4.0, "rms_dbfs": -14.0},
                                 {"onset_rate": 4.0, "rms_dbfs": -14.0},
                                 {"onset_rate": 4.0, "rms_dbfs": -14.0},
                                 bpm_before=90.909, bpm_after=44.776)
    check(off["verdict"] == "FAIL" and off["octave_fold"]["same_beat"] is True
          and off["bpm_grants_pass"] is False,
          "D1: a folded bpm pair with no onset/energy evidence still FAILS")


# ---- D1: the fail-closed rap audio check -----------------------------------

def test_d1_rap_check_is_fail_closed():
    if not gate(RAP_AUDIO, "D1 rap check", "music_qc/rap_check.py not yet published"):
        return
    segs = [{"delivery": "spoken", "start": 0, "end": 5, "source": "measured"},
            {"delivery": "sung", "start": 5, "end": 20, "source": "measured"}]
    env = {k: "" for k in RC.REQUIRED}
    out = RC.gate(segs, env=env)
    check(out["verdict"] == "UNMEASURED"
          and ("blocks PASS" in out["reason"] or "cannot pass" in out["reason"]),
          "D1: rap on the audio is UNMEASURED and blocks PASS without a control (%r)"
          % (out["verdict"],))
    check(RC.classify(segs, env=env)["verdict"] == "UNMEASURED",
          "D1: classify is fail-closed on the same evidence")
    check(RC.gate([], env=env)["verdict"] == "UNMEASURED"
          and RC.control_ready(env) is False,
          "D1: an empty take and a missing control are both UNMEASURED")
    check(all(k in RC.REQUIRED for k in ("rap", "sung", "spoken_over_beat")),
          "D1: the control set names rap, sung and spoken-over-beat")


# ---- D1: the two conflated figures ----------------------------------------

def test_d1_words_versus_music_are_separate_labels():
    if not gate(SV is not None and hasattr(SV, "coverage_report"), "D1 words/music",
                "story_coverage is not yet published"):
        return
    rep = SV.coverage_report(50.416, 8.0)
    check(rep["vocal_words_s"] == 50.416 and rep["music_only_s"] == 8.0
          and rep["runtime_s"] == 58.416,
          "D1: words, music-only time and runtime are reported separately")
    check(rep["words_and_music_are_separate_labels"] is True
          and "NEVER counted as word time" in rep["label"],
          "D1: the label states the music seconds are not word time")


def test_d1_sheet_parser_counts_the_three_deliveries_separately():
    if not gate(SCT_SHEET, "D1 sheet parser", "the sheet parser is not yet published"):
        return
    sheet = [{"tag": "Intro", "delivery": "spoken", "lines": ["one two three four five six"]},
             {"tag": "Verse", "delivery": "sung", "lines": ["word " * 60]},
             {"tag": "Hook 1", "delivery": "sung", "lines": ["word " * 9]},
             {"tag": "Verse", "delivery": "rap", "lines": ["flow " * 19]},
             {"tag": "Outro", "delivery": "spoken", "lines": ["cta " * 7]}]
    out = SCT.check_sheet(R.render_lyrics(sheet, "rnb-flow"), "rnb-flow", 58)
    t = out["totals"]
    check(t["sung_words"] == 69 and t["spoken_words"] == 13 and t["rap_words"] == 19,
          "D1: the sheet parses as 69 sung + 13 spoken + 19 rap (%r)"
          % ({k: t[k] for k in ("sung_words", "spoken_words", "rap_words")},))
    check(t["total_words"] == 101,
          "D1: the three deliveries total 101 words, not 101 of one delivery")


# ---- defect 2: the two D1 audio gates are WIRED INTO the judge -------------

def _wired_take(plan):
    import song_dispatch as SDm
    take = {"segments": [{"delivery": "sung", "start": 0.0, "end": 30.0,
                          "source": "measured"}],
            "aligned_words": [], "duration_s": 58.0, "detector": "singing_detector 2",
            "music_under_speech_ratio": 1.0, "tail_rms_dbfs": -20.0, "first_sung_s": 5.0}
    return SDm.judge_take(take, plan, "", "", None, "rnb-flow", "")


def test_d1_the_two_audio_gates_are_wired_into_the_take_judge():
    if not gate(SD is not None and hasattr(SD, "judge_take") and PC is not None
                and RC is not None and getattr(SD, "GATES", None)
                and "rap_audio" in SD.GATES, "D1 judge wiring",
                "the take-judge wiring is not yet published to this package"):
        return
    check("rap_audio" in SD.GATES and "pace_change" in SD.GATES,
          "D2: the take judge declares both D1 audio gates")
    calls = {"rap": 0, "pace": 0}
    rap_gate, pace_judge = RC.gate, PC.judge_plan_pace

    def rap_spy(segs):
        calls["rap"] += 1
        return rap_gate(segs)

    def pace_spy(plan, *a, **kw):
        calls["pace"] += 1
        return pace_judge(plan, *a, **kw)

    RC.gate, PC.judge_plan_pace = rap_spy, pace_spy
    try:
        base = {"delivered_s": 58, "style_id": "rnb-flow", "sheet_text": "", "hook_plan": {}}
        plain = _wired_take(base)
        ordered = _wired_take(dict(base, pace_change={
            "reason": "the bridge lifts into the last hook", "boundary_s": 40.0}))
    finally:
        RC.gate, PC.judge_plan_pace = rap_gate, pace_judge
    check(calls == {"rap": 2, "pace": 2},
          "D2: judge_take CALLS rap_check.gate and pace_change.judge_plan_pace (%r)" % (calls,))
    check(plain["gates"]["rap_audio"]["verdict"] == "UNMEASURED"
          and "rap_audio" in plain["flagged"] and plain["verdict"] != "PASS",
          "D2: an unmeasured rap read is flagged and never reaches PASS")
    check(plain["gates"]["pace_change"]["verdict"] == "PASS"
          and plain["gates"]["pace_change"]["detail"].startswith("no ordered pace change"),
          "D2: with no ordered gear change there is nothing to enforce")
    check(ordered["gates"]["pace_change"]["verdict"] == "UNMEASURED"
          and "pace_change" in ordered["flagged"] and ordered["verdict"] != "PASS",
          "D2: an ordered gear change with no evidence never reaches PASS")


# ---- WW-11: judge-path gate-removal and delivery-boundary tests ------------

def _inspect_source(fn):
    try:
        import inspect
        return inspect.getsource(fn)
    except Exception:
        return ""


def _story_gate_wired():
    if SD is None or not hasattr(SD, "judge_take"):
        return False, "song_dispatch.judge_take is not present"
    if "check_returned_story" not in _inspect_source(SD.judge_take):
        return False, "check_returned_story is not yet called from judge_take (WW-08 lands with its own package)"
    return True, ""


def test_ww11_judge_path_gate_removal_breaks_the_suite():
    """WW-08/WW-11: deleting the story-gate invocation from judge_take must break
    the suite. Until the wiring lands this is UNDETERMINED -- never a pass."""
    wired, why = _story_gate_wired()
    if not gate(wired, "WW-11 gate-removal", why):
        return
    import song_contract as _SCTmod
    take = {"segments": [{"delivery": "sung", "start": 0.0, "end": 30.0, "source": "measured"}],
            "aligned_words": [], "duration_s": 58.0, "first_sung_s": 30.0}
    plan = {"delivered_s": 58, "style_id": "rnb-flow", "sheet_text": "", "hook_plan": {}}
    original = getattr(_SCTmod, "check_returned_story", None)
    try:
        _SCTmod.check_returned_story = lambda *a, **k: {"verdict": "PASS", "reasons": []}
        kept = SD.judge_take(take, plan, "", "", None, "rnb-flow", "")
    finally:
        if original is not None:
            _SCTmod.check_returned_story = original
    check("story_coverage" in (kept.get("gates") or {})
          or "story_coverage" in (kept.get("flagged") or [])
          or "story_coverage" in (kept.get("failed") or []),
          "WW-11: the story gate is in the take judge's gate set (removal would drop it)")


def test_ww11_delivery_boundary_refuses_a_non_pass_take():
    """WW-18/WW-11: the delivery path must refuse a take whose required gates did
    not all PASS. Until the delivery-level block lands this is UNDETERMINED."""
    if not gate(SC is not None and hasattr(SC, "deliver_choices"),
                "WW-11 delivery boundary", "song_choices.deliver_choices is not present"):
        return
    src = _inspect_source(SC.deliver_choices) + _inspect_source(getattr(SC, "record_pick", lambda: None))
    if "gates" not in src and "verdict" not in src.replace("FAILED", ""):
        undetermined("WW-11 delivery boundary",
                     "the delivery path does not yet consult the required gate set (WW-18 lands with its own package)")
        return
    bad = {"status": "FLAG", "variant": {"id": "v1"}, "take": {"path": "/tmp/x.mp3"},
           "receipts": [], "gates": {"story": {"verdict": "UNMEASURED"}}}
    with tempfile.TemporaryDirectory() as tmp:
        try:
            SC.deliver_choices([bad], tmp, os.path.join(tmp, "d"), send=lambda *a: None)
        except Exception as e:
            check(True, "WW-11: a take with an unmeasured required gate is refused (%s)"
                  % type(e).__name__)
        else:
            check(False, "WW-11: the delivery path offered a take with an unmeasured gate")


# ---- WW-11: the release-level parity check --------------------------------

def _tree_hash(root):
    lines = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        for name in sorted(filenames):
            if name.endswith(".pyc"):
                continue
            p = os.path.join(dirpath, name)
            rel = os.path.relpath(p, root).replace(os.sep, "/")
            with open(p, "rb") as f:
                lines.append("%s  %s" % (hashlib.sha256(f.read()).hexdigest(), rel))
    return hashlib.sha256("\n".join(sorted(lines)).encode("utf-8")).hexdigest(), sorted(lines)


def parity_check(canonical_core, twin_core, pinned_revision=None, twin_revision=None):
    """The release-level parity check (WW-11): the same shared core scope must be
    byte-identical between the two copies. A missing canonical source -- a missing
    twin, or a twin that has not recorded the revision it mirrored -- is
    UNDETERMINED, never a release PASS."""
    if not canonical_core or not os.path.isdir(canonical_core):
        return {"status": "UNDETERMINED", "detail": "canonical core absent",
                "canonical": canonical_core}
    if not twin_core or not os.path.isdir(twin_core):
        return {"status": "UNDETERMINED", "detail": "twin core absent", "twin": twin_core}
    if pinned_revision is None or twin_revision is None:
        return {"status": "UNDETERMINED",
                "detail": "the twin has not recorded the revision it mirrored"}
    if str(pinned_revision) != str(twin_revision):
        return {"status": "UNDETERMINED",
                "detail": "the twin pinned a different revision (%s != %s)"
                          % (twin_revision, pinned_revision)}
    ch, cl = _tree_hash(canonical_core)
    th, tl = _tree_hash(twin_core)
    cset = {ln.split("  ", 1)[1] for ln in cl}
    tset = {ln.split("  ", 1)[1] for ln in tl}
    if cset != tset:
        return {"status": "FAIL", "detail": "shared core scope differs",
                "only_canonical": sorted(cset - tset), "only_twin": sorted(tset - cset),
                "canonical_hash": ch, "twin_hash": th}
    if ch != th:
        return {"status": "FAIL", "detail": "shared core bytes differ",
                "canonical_hash": ch, "twin_hash": th}
    return {"status": "PASS", "detail": "shared core is byte-identical",
            "canonical_hash": ch, "twin_hash": th}


def test_ww11_release_parity_is_undetermined_when_a_source_is_missing():
    """WW-11: a missing canonical source (or twin), or a twin that has not
    recorded the revision it mirrored, is UNDETERMINED -- NEVER a release PASS.
    The check bites when the pins agree and the bytes differ."""
    twin = os.environ.get("DSAF_TWIN_CORE") or os.path.expanduser(
        "~/.claude/skills/drama-song-ad-factory/scripts/core")
    res = parity_check(CORE, twin, os.environ.get("DSAF_PINNED_REVISION"),
                       os.environ.get("DSAF_TWIN_PINNED_REVISION"))
    if res["status"] != "PASS":
        undetermined("WW-11 parity", "%s -- UNDETERMINED, not a release pass" % res["detail"])
    else:
        check(True, "WW-11: the shared core scope is byte-identical between the two copies")
    # deterministic controls: missing source -> UNDETERMINED; pinned + differing -> FAIL
    missing = parity_check(os.path.join(CORE, "no-such-dir"), twin, "R", "R")
    check(missing["status"] == "UNDETERMINED",
          "WW-11: a missing canonical source is UNDETERMINED, never a release PASS")
    with tempfile.TemporaryDirectory() as tmp:
        a, b, c = (os.path.join(tmp, n) for n in ("a", "b", "c"))
        for d in (a, b, c):
            os.makedirs(d)
        for d in (a, b):
            with open(os.path.join(d, "x.py"), "w", encoding="utf-8") as f:
                f.write("x = 1\n")
        with open(os.path.join(c, "x.py"), "w", encoding="utf-8") as f:
            f.write("x = 2\n")
        check(parity_check(a, b, "R", "R")["status"] == "PASS",
              "WW-11: byte-identical copies at the SAME pinned revision PASS")
        check(parity_check(a, c, "R", "R")["status"] == "FAIL",
              "WW-11: differing bytes at the same pinned revision FAIL")
        check(parity_check(a, b, "R", "R2")["status"] == "UNDETERMINED",
              "WW-11: a twin pinned to a different revision is UNDETERMINED")


# ---- WW-19: the import audit of the six referenced module paths ------------

SIX_MODULE_PATHS = [
    "scripts/core/music_qc/rap_check.py",
    "scripts/core/music_qc/pace_change.py",
    "scripts/core/music_qc/test_wwfix_u1.py",
    "scripts/core/story_coverage/story_coverage.py",
    "scripts/core/story_coverage/__init__.py",
    "scripts/core/song_choices/overlap.py",
]
OWNED_HERE = {
    "scripts/core/music_qc/pace_change.py",
    "scripts/core/music_qc/test_wwfix_u1.py",
    "scripts/core/song_choices/overlap.py",
}
#: Built by the OTHER concurrent packages of THIS SAME unit; absent here means
#: NOT-YET-PUBLISHED (UNDETERMINED), not ABSENT.
NOT_YET_PUBLISHED = {
    "scripts/core/music_qc/rap_check.py",
    "scripts/core/story_coverage/story_coverage.py",
    "scripts/core/story_coverage/__init__.py",
}


def import_audit(core_dir, not_yet_published=None):
    """WW-19: audit the six referenced module paths. PRESENT / NOT-YET-PUBLISHED
    (UNDETERMINED) / ABSENT (a failure). Absent is distinguished from
    not-yet-published, and neither is ever reported as PASS."""
    nyp = NOT_YET_PUBLISHED if not_yet_published is None else not_yet_published
    rows = []
    for rel in SIX_MODULE_PATHS:
        rel_from_core = rel[len("scripts/core/"):]
        if os.path.exists(os.path.join(core_dir, rel_from_core)):
            state = "PRESENT"
        elif rel in nyp:
            state = "NOT_YET_PUBLISHED"
        else:
            state = "ABSENT"
        rows.append({"path": rel, "state": state})
    counts = {s: sum(1 for r in rows if r["state"] == s)
              for s in ("PRESENT", "NOT_YET_PUBLISHED", "ABSENT")}
    return {"rows": rows, "counts": counts,
            "verdict": "FAIL" if counts["ABSENT"] else "DETERMINED"}


def test_ww19_import_audit_reports_absent_vs_not_yet_published():
    audit = import_audit(CORE)
    print("   WW-19 import audit on this tree: %r" % (audit["counts"],))
    check(audit["counts"]["ABSENT"] == 0,
          "WW-19: no referenced module is ABSENT on this tree (%r)" % (audit["counts"],))
    check(audit["counts"]["PRESENT"] >= 3,
          "WW-19: this package's three owned modules are PRESENT (%r)" % (audit["counts"],))
    strict = import_audit(CORE, not_yet_published=set())
    check(strict["verdict"] == "FAIL" and strict["counts"]["ABSENT"] >= 3,
          "WW-19: with no not-yet-published allowance the audit FAILS closed (%r)"
          % (strict["counts"],))


# ---- WW-20: the version is read live, never from a PR body -----------------

def version_check(skill_root, live_version):
    """WW-20: the written version must be strictly ABOVE the version read live
    from main at build time. No live value read -> UNDETERMINED."""
    path = os.path.join(skill_root, "skill-version.txt")
    try:
        with open(path, encoding="utf-8") as f:
            written = f.read().strip()
    except OSError:
        return {"status": "UNDETERMINED", "detail": "skill-version.txt not found"}
    if not live_version:
        return {"status": "UNDETERMINED", "detail": "no live version read at build time",
                "written": written}

    def _parts(v):
        return tuple(int(x) for x in v.lstrip("v").split(".") if x.isdigit())

    return {"status": "PASS" if _parts(written) > _parts(live_version) else "FAIL",
            "written": written, "live": live_version}


def test_ww20_version_is_read_live_and_strictly_above():
    live = os.environ.get("DSAF_LIVE_SKILL_VERSION")
    res = version_check(SKILL_ROOT, live)
    if res["status"] == "UNDETERMINED":
        undetermined("WW-20 live version",
                     "%s -- set DSAF_LIVE_SKILL_VERSION to prove the bump" % res["detail"])
        return
    check(res["status"] == "PASS",
          "WW-20: %s is strictly above the live %s" % (res["written"], res["live"]))


def main():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    if FAILURES:
        print("\n%d FAILED: %s" % (len(FAILURES), "; ".join(FAILURES)))
        return 1
    if UNDETERMINED:
        print("\nPASS (%d UNDETERMINED -- NOT a release pass): %s"
              % (len(UNDETERMINED), "; ".join(UNDETERMINED)))
        return 0
    print("\nALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
