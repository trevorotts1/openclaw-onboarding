"""PD-TEST-098 (verifier half) -- the SUBSTANCE VERIFIER must enforce the shared
prompt band, because THREE authorities consult it
(tests/test_pd098_design_verifier_band.py).

THE DEFECT THIS CLOSES. Fixing `artifacts.validate_artifact` alone was NOT
enough, and the independent review refuted that claim by driving the whole
chain. The `artifacts.py` arm does fire -- `phase.banked_invalid` is emitted and
the phase is checkpointed PENDING -- but TWO other authorities then re-blessed
the same over-ceiling artifact, so the net effect was 0 model calls and an
unchanged artifact:

  Authority 1 -- `Engine._phase_artifact_satisfied` (phases.py:2670) is
    `_artifacts_present` AND `phase_verifiers.verify`. `wo_satisfied`
    (phases.py:2813) uses it to complete a phase WITHOUT dispatching, so the
    engine re-attested the phase `done`, artifact byte-unchanged.
  Authority 2 -- the dispatcher's idempotent pre-check
    (dispatcher.py:5140-5157) consults the same verifier and returned
    `skipped_satisfied`.
  Authority 3 -- `_phase_already_done` (dispatcher.py:3226, called at :5090) is
    a STATUS-STRING-ONLY guard: no verifier, no artifact. It is why the engine's
    PENDING reset is load-bearing.

The old arm was `_make_pu_verifier` -> `_pu_check_text`, which accepted these
files on ">= 40 chars" alone, so `verify('P-U-DESIGN-SALES', run)` returned
`(True, [])` on the live 58,482-char prompt.

THE FIX. `_pu_check_design_prompt` enforces the shared band, read from
`prompt_gate`. One seam closes Authorities 1 and 2; the `artifacts.py` reset
closes Authority 3. BOTH are required -- neither alone heals the run.

MEASURED END TO END (real dispatcher, real manifest, model STUBBED, no paid
call), phase status `pending` vs `done`:

    status=pending -> dispatch_one returns `ok`, 3 model calls,
                      artifact 58,482 -> 17,858 chars, prompt_gate -> []
    status=done    -> dispatch_one returns `skipped_satisfied`, 0 calls

WHAT THESE TESTS PIN
  1. `phase_verifiers.verify` returns `(False, [reason naming AF-P2 and the
     measured length])` for all three live over-ceiling prompts
     (Authorities 1 + 2).
  2. `Engine._phase_artifact_satisfied` is therefore False.
  3. Driven through the REAL `Engine.run_phase`, the phase is NOT re-attested
     `done` and no `phase.work_order_satisfied` event fires.
  4. At `pending`, `dispatch_one` does NOT return `skipped_satisfied`; with a
     compliant stubbed model it RE-AUTHORS an artifact that clears the real
     gate (Authority 3 + the producer half together).
  5. BLAST RADIUS: non-design `P-U-*` text artifacts are unaffected.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # cross-test fixture import

import phase_verifiers as PV  # noqa: E402
import prompt_gate as PG  # noqa: E402
from presentation_job import dispatcher as D  # noqa: E402
from presentation_job.manifest import Manifest  # noqa: E402
from presentation_job.state import StateStore  # noqa: E402


def _find_shipped_manifest():
    """Walk UP from this file -- never a fixed `parents[N]` index, which raised
    `IndexError: 4` at COLLECTION time in a shallower tree."""
    for base in SCRIPTS.parents:
        cand = base / "universal-sops" / "presentation-slide-craft" / "PIPELINE-MANIFEST.json"
        if cand.is_file():
            return cand
    return None


_SHIPPED = _find_shipped_manifest()

# (phase, artifact, live stripped length) -- measured read-only on the live run.
DESIGN = (
    ("P-U-DESIGN-SALES", "prompts/sales.design.txt", 58482),
    ("P-U-DESIGN-CHECKOUT", "prompts/checkout.design.txt", 49525),
    ("P-U-DESIGN-VSL", "prompts/vsl.design.txt", 51333),
)


def _manifest_file(tmp_path: Path, *, with_fanout: bool = True) -> Path:
    """A manifest carrying the REAL contract fields for the three design
    phases. The shipped v69 manifest is used when this tree has it, so the
    test drives the real contract; the inline copy is a fallback."""
    if _SHIPPED is not None:
        return _SHIPPED
    phases = []
    for i, (pid, rel, _n) in enumerate(DESIGN):
        entry = {"id": pid, "order": 4.2 + i, "owning_role": "slide-image-creator",
                 "produces_artifact": [rel], "client_report": {},
                 "executor": {"kind": "agent"}}
        if with_fanout:
            entry["fanout"] = {"by": "slide", "desired_count": 3, "batch_width": 3}
        phases.append(entry)
    mf = tmp_path / "mf.json"
    mf.write_text(json.dumps({"manifest_version": 69, "phases": phases,
                              "deliverables_required": []}))
    return mf


# ---------------------------------------------------------------------------
# PD-TEST-113 -- A FIXTURE THAT CLEARS THE WHOLE GATE.
#
# `_run_with_live_artifacts` used to author every "in-band" control artifact as
# `"d" * size`. That is byte-length padding and nothing else, so once the
# verifier stopped enforcing only AF-P1/AF-P2 and started delegating to
# `prompt_gate.prompt_problems` (the whole gate the render phase applies), those
# controls failed for the RIGHT reason: 1 distinct word against a 220 floor, no
# brand HEX, no type size, no composition token, no structural block. The
# negative control has to be a prompt that genuinely clears the gate, or it
# pins nothing about the band. (The neutrality assert runs on first use, not at
# module import.)
#
# The filler is GATE-NEUTRAL by construction. Without that, a mutation test is
# vacuous: the first version of this vocabulary contained `monogram` and
# `lockup`, so deleting the negative block's logo clause still left AF-P13's
# logo class satisfied by the FILLER, and a test that meant to prove "the
# verifier applies AF-P13" passed for the wrong reason. Neutrality is asserted
# on first use, never assumed.
# ---------------------------------------------------------------------------
_ART_DIRECTION_WORDS = (
    "editorial premium cinematic restrained confident warm architectural studio "
    "portrait landscape texture grain gradient ambient shadow "
    "highlight contrast saturation harmony balance rhythm cadence spacing "
    "kerning leading baseline gutter column diagonal "
    "symmetry asymmetry perspective parallax bokeh vignette "
    "overlay underlay layer stack plate frame border divider accent "
    "primary secondary tertiary neutral tint shade hue chroma luminance "
    "serif sans display condensed extended humanist geometric grotesque "
    "uppercase lowercase smallcaps italic oblique tracking measure widow "
    "orphan caption eyebrow kicker standfirst pullquote byline "
    "masthead wordmark emblem crest seal stamp "
    "paper cardstock matte satin gloss foil emboss deboss letterpress "
    "photograph illustration diagram chart table timeline sequence ladder "
    "matrix map blueprint schematic wireframe mockup composite "
    "cutout silhouette outline contour edge bevel chamfer radius fillet "
    "shadowbox pedestal plinth platform riser tier apron backdrop "
    "cyclorama sweep flat lay overhead dutch angle threequarter profile "
    "candid posed environmental location interiors exteriors workspace "
    "desk laptop notebook coffee plant window daylight tungsten "
    "softbox bounce flag diffusion reflector gel practical "
    "wardrobe fabric wool cotton linen denim leather knit weave drape "
    "gesture posture expression gaze attention focus calm assured "
    "approachable credible authoritative generous specific concrete "
    "measurable deliberate intentional crafted considered resolved "
    "readable scannable hierarchical structured "
    "navigable anchored aligned justified ragged centered offset "
    "chromatic monochrome duotone tritone sepia cool warm "
    "glossy brushed polished textured woven pressed folded "
    "inch pixel hyphen bullet asterisk "
    "amber ivory charcoal slate sand clay rust copper brass bronze "
    "linen canvas burlap cork oak walnut maple ash birch cedar teak "
    "plum olive sage moss fern pine spruce "
    "coral blush peach apricot honey butter cream "
    "indigo cobalt azure cerulean teal turquoise aqua mint "
    "crimson scarlet vermilion ruby garnet burgundy maroon "
    "violet lavender lilac orchid mauve magenta fuchsia "
    "quartz granite marble onyx jade pearl opal topaz "
    "whisper murmur echo hush stillness pause breath "
    "arc sweep curve spiral helix loop coil twist "
    "thread strand fiber cord rope cable wire "
    "beacon lantern candle glow ember spark flame "
    "threshold doorway archway corridor atrium alcove "
    "terrace balcony mezzanine gallery hall foyer "
    "niche recess nook cranny corner"
).split()


def _gate_token_set():
    """Every literal `prompt_gate` matches on for the NON-length rules, read
    from the gate itself so this stays true when a rule gains a token."""
    toks = set()
    for group in PG.NEGATIVE_BLOCK_CLASS_TOKENS.values():
        toks.update(t.lower() for t in group)
    toks.update(t.lower() for t in PG.SPELLING_LOCK_TOKENS)
    toks.update(t.lower() for t in PG.PROMPT_COMPOSITION_TOKENS)
    return toks


def _neutral_filler() -> str:
    toks = _gate_token_set()
    keep = [w for w in _ART_DIRECTION_WORDS
            if not any(w in t or t in w for t in toks)]
    assert len(set(keep)) >= PG.PROMPT_MIN_DISTINCT_WORDS, (
        f"gate-neutral filler is too small ({len(set(keep))} distinct) to clear "
        f"the density floor ({PG.PROMPT_MIN_DISTINCT_WORDS})")
    return " ".join(keep)


_NEGATIVE_BLOCK = (
    "DO-NOT BLOCK\n"
    "Do not misspell or garble any word; render every quoted string "
    "letter-for-letter.\n"
    "Do not redraw, recolor or restyle the logo, monogram or tagline lockup.\n"
    "Do not leave a bracketed token, square bracket placeholder or owner to "
    "confirm marker.\n"
    "Do not add narration, a presenter line, spoken-script or stage direction.\n"
    "Do not distort anatomy: no fused hand, malformed finger, distorted "
    "facial feature.\n"
    "Do not let a busy, cluttered or high-detail background compete with the "
    "text zone.\n"
    "Do not alter demographic or skin tone fidelity; never lighten, "
    "desaturate or mono-cast.\n"
    "Do not add a watermark, emoji, clipart, default font or UI artifact.\n"
)

_HEAD = (
    "[ARCHETYPE: editorial split-screen, premium direct-response]\n"
    "Canvas 1920x1080, 16:9 frame, 300 dpi safe margin.\n"
    "Brand palette #0B1F3A deep navy, #F2B705 signal gold, #F7F7F5 paper.\n"
    "Typography headline 96pt condensed uppercase, deck 28pt humanist, "
    "caption 18pt.\n"
    "Composition rule of thirds; subject on the left third, copy zone on "
    "the right third; a scrim behind any text.\n"
    "Render every quoted text string exactly as written, letter-for-letter.\n"
)


def _gate_clean_prompt(target_len: int) -> str:
    """A prompt of EXACTLY `target_len` chars that clears every NON-LENGTH rule
    in `prompt_gate.prompt_problems` -- asserted below, never assumed."""
    body = (_neutral_filler() + " ") * (1 + target_len // 300)
    text = (_HEAD + body)[:max(0, target_len - len(_NEGATIVE_BLOCK))] + _NEGATIVE_BLOCK
    text = text[:target_len]
    leftovers = [x for x in PG.prompt_problems(text)
                 if not x.startswith(("AF-P1:", "AF-P2:"))]
    assert not leftovers, f"fixture prompt is not quality-clean: {leftovers}"
    return text


def _run_with_live_artifacts(tmp_path: Path, *, status: str = "done",
                             sizes=None, manifest_path: Path | None = None,
                             gate_clean: bool = False):
    """A run dir holding the three live over-ceiling design prompts, with real
    banked sha256 recorded, plus whatever run context the verifier reads."""
    rd = tmp_path / "run"
    (rd / "prompts").mkdir(parents=True, exist_ok=True)
    (rd / "working" / "copy").mkdir(parents=True, exist_ok=True)
    (rd / "working" / "work-orders").mkdir(parents=True, exist_ok=True)
    (rd / "working" / "copy" / "arc_allocation.json").write_text(json.dumps(
        {"slots": [{"ordinal": n, "arc": "A"} for n in range(1, 9)]}))
    (rd / "working" / "copy" / "slides.json").write_text(json.dumps(
        {"slides": [{"ordinal": n} for n in range(1, 9)]}))
    # The three design phases each `defers_unless` an intake flag; without the
    # flags the verifier correctly reports the phase DEFERRED (satisfied), which
    # would make the band assertions below vacuous.
    (rd / "working" / "copy" / "intake.json").write_text(json.dumps(
        {"client": "t", "want_sales_checkout": "yes", "want_vsl_page": "yes"}))
    mf = manifest_path or _manifest_file(tmp_path)
    phases = []
    for pid, rel, n in DESIGN:
        size = (sizes or {}).get(pid, n)
        p = rd / rel
        p.write_text((_gate_clean_prompt(size) if gate_clean else "d" * size) + "\n",
                     encoding="utf-8")
        sha = hashlib.sha256(p.read_bytes()).hexdigest()
        phases.append({"id": pid, "status": status, "artifacts": [rel],
                       "sha256": {rel: sha}, "attempts": 1, "heal_events": [],
                       "attested_at": "x"})
    store = StateStore(rd)
    store.save({"job_id": "pj", "schema_version": 1, "run_dir": str(rd),
                "manifest_path": str(mf), "phases": phases, "events": [],
                "sent": {}, "requester": {"chat_id": "t"}, "heartbeat": {}})
    return rd, mf


# ---------------------------------------------------------------------------
# 1 -- Authorities 1 and 2: the verifier itself.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("pid,rel,n", DESIGN)
def test_verify_rejects_the_live_over_ceiling_design_prompt(tmp_path, pid, rel, n):
    """THE ACCEPTANCE TARGET, half 1. Pre-fix this returned `(True, [])` -- the
    re-blessing that made the artifacts.py predicate a no-op in practice."""
    rd, _mf = _run_with_live_artifacts(tmp_path)
    ok, reasons = PV.verify(pid, rd)
    assert ok is False, (
        "the substance verifier must NOT accept an over-ceiling design prompt")
    joined = " ".join(reasons)
    assert "AF-P2" in joined, joined
    assert str(n) in joined, joined


def test_verify_accepts_an_in_band_design_prompt(tmp_path):
    """NEGATIVE CONTROL: without this, the test above would pass even if the
    verifier failed every design prompt, and no resume could ever reuse work."""
    rd, _mf = _run_with_live_artifacts(
        tmp_path, sizes={pid: PG.PROMPT_CHAR_CEILING for pid, _r, _n in DESIGN},
        gate_clean=True)
    for pid, _rel, _n in DESIGN:
        ok, reasons = PV.verify(pid, rd)
        assert ok is True, f"{pid}: an in-band design prompt must verify: {reasons}"


def test_verify_band_is_read_from_prompt_gate(tmp_path, monkeypatch):
    rd, _mf = _run_with_live_artifacts(
        tmp_path, sizes={pid: 30000 for pid, _r, _n in DESIGN}, gate_clean=True)
    ok, reasons = PV.verify(DESIGN[0][0], rd)
    assert ok is False, "30,000 chars is over the 18,000 ceiling"
    assert "AF-P2" in " ".join(reasons), reasons
    monkeypatch.setattr(PG, "PROMPT_CHAR_CEILING", 60000)
    monkeypatch.setattr(PG, "PROMPT_CHAR_FLOOR", 20000)
    ok, reasons = PV.verify(DESIGN[0][0], rd)
    assert ok is True, (
        "the verifier must follow prompt_gate's constants, not a second copy: "
        f"{reasons}")


def test_verify_under_floor_design_prompt_is_refused(tmp_path):
    rd, _mf = _run_with_live_artifacts(
        tmp_path, sizes={pid: 500 for pid, _r, _n in DESIGN})
    ok, reasons = PV.verify(DESIGN[0][0], rd)
    assert ok is False and "AF-P1" in " ".join(reasons), reasons


# ---------------------------------------------------------------------------
# 2/3 -- Authority 1 and the engine half, end to end.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("pid,rel,n", DESIGN)
def test_phase_artifact_satisfied_is_false(tmp_path, pid, rel, n):
    from presentation_job.phases import Engine
    rd, mf = _run_with_live_artifacts(tmp_path)
    eng = Engine(rd, Manifest(mf), StateStore(rd), StateStore(rd).load(), dry_run=True)
    assert eng._phase_artifact_satisfied(eng.manifest.phase(pid)) is False, (
        "Authority 1: a satisfied check that passes here re-attests the phase "
        "done without dispatching")


@pytest.mark.parametrize("pid,rel,n", DESIGN)
def test_engine_run_phase_does_not_reattest_done(tmp_path, pid, rel, n):
    """THE ACCEPTANCE TARGET, half 2 -- the half the review found unproven.
    Pre-fix: `phase.work_order_satisfied` fired and the phase went back to
    `done` with an unchanged artifact."""
    from presentation_job.phases import Engine
    rd, mf = _run_with_live_artifacts(tmp_path, status="done")
    before = (rd / rel).read_bytes()
    eng = Engine(rd, Manifest(mf), StateStore(rd), StateStore(rd).load(), dry_run=True)
    try:
        eng.run_phase(eng.manifest.phase(pid))
    except Exception:  # noqa: BLE001 -- the observable is the state, not the rc
        pass
    ps = eng._phase_state(pid)
    kinds = [e.get("kind") for e in eng.state.get("events", [])]
    satisfied = [e for e in eng.state.get("events", [])
                 if e.get("kind") == "phase.work_order_satisfied"
                 and pid in str(e.get("message", ""))]
    assert "phase.banked_invalid" in kinds, (
        "the artifacts.py half must announce the banked artifact invalid")
    assert ps.get("status") != "done", (
        "the phase was re-attested done on an over-ceiling artifact")
    assert not satisfied, "a satisfied work order must not complete this phase"
    assert (rd / rel).read_bytes() == before, "the artifact was not re-authored"


# ---------------------------------------------------------------------------
# 4 -- Authority 3 + the full self-heal, model STUBBED (no paid call).
# ---------------------------------------------------------------------------
def _stub_dispatch(monkeypatch, parts_for):
    calls: list = []

    def fake(system_prompt, user_prompt, *, phase_id, run_dir, **kw):
        calls.append(user_prompt)
        parts = parts_for()
        return (parts[min(len(calls), len(parts)) - 1],
                {"request_id": "req-stub"}, {"provider": "stub", "model": "stub"})

    monkeypatch.setattr(D, "dispatch_complete", fake)
    return calls


@pytest.mark.parametrize("pid,rel,n", DESIGN)
def test_pending_phase_is_not_skipped_and_is_reauthoried(tmp_path, monkeypatch, pid, rel, n):
    """THE STRONGEST EVIDENCE AVAILABLE WITHOUT A PAID CALL (review's ask).

    Authority 3 short-circuits on the STATUS STRING alone, so only a real
    dispatch proves the re-blessing is gone. At `pending` (the state the
    artifacts.py arm produces) `dispatch_one` must NOT return
    `skipped_satisfied`, must actually call the model, and the artifact it
    writes must clear the REAL shared gate."""
    from test_pd098_design_prompt_band import _compliant_parts
    rd, mf = _run_with_live_artifacts(tmp_path, status="pending")
    calls = _stub_dispatch(monkeypatch, lambda: _compliant_parts(3))
    man = Manifest(mf)
    res = D.dispatch_one(
        rd, pid, {"phase": pid, "owning_role": "slide-image-creator",
                  "produces_artifact": [rel]},
        dept_root=SCRIPTS.parent, phase_obj=man.phase(pid), worker_id="test")
    assert res.status != "skipped_satisfied", (
        "the dispatcher's idempotent pre-check re-blessed the artifact")
    assert len(calls) == 3, f"expected a real 3-unit re-author, got {len(calls)}"
    text = (rd / rel).read_text(encoding="utf-8").strip()
    assert PG.PROMPT_CHAR_FLOOR <= len(text) <= PG.PROMPT_CHAR_CEILING, (
        f"re-authored artifact is {len(text)} chars, outside the band")
    assert PG.prompt_problems(text, "One Request. One Package.") == []


@pytest.mark.parametrize("pid,rel,n", DESIGN)
def test_done_phase_is_still_skipped_by_the_status_guard(tmp_path, monkeypatch, pid, rel, n):
    """Authority 3, stated as a test so the dependency is explicit: while
    state.json says `done` the dispatcher skips on the status string and never
    reaches the verifier. This is exactly why the engine's PENDING reset is
    load-bearing and why the predicate alone changes nothing."""
    rd, mf = _run_with_live_artifacts(tmp_path, status="done")
    calls = _stub_dispatch(monkeypatch, lambda: ["x"])
    man = Manifest(mf)
    res = D.dispatch_one(
        rd, pid, {"phase": pid, "owning_role": "slide-image-creator",
                  "produces_artifact": [rel]},
        dept_root=SCRIPTS.parent, phase_obj=man.phase(pid), worker_id="test")
    assert res.status == "skipped_satisfied"
    assert calls == []


# ---------------------------------------------------------------------------
# 5 -- BLAST RADIUS on the verifier: non-design P-U-* text artifacts.
# ---------------------------------------------------------------------------
def test_non_design_pu_text_artifacts_are_unaffected(tmp_path):
    """Every other `_pu_check_text` consumer must keep the old ">= 40 chars"
    contract -- the new arm matches only `prompts/*.design.txt`."""
    rd = tmp_path / "run"
    body = "# fragment\n" + "real authored copy for the upsell page. " * 12
    for rel in ("working/upsell/copy/sales.fragment.md",
                "working/upsell/copy/copy_ledger.json",
                "working/upsell/copy/checkout.fragment.md",
                "working/upsell/vsl-research.md"):
        p = rd / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"ledger": body}) if rel.endswith(".json") else body,
                     encoding="utf-8")
    for pid in ("P-U-SALES-COPY", "P-U-CHECKOUT-COPY", "P-U-VSL-RESEARCH"):
        ok, reasons = PV.verify(pid, rd)
        assert ok is True, f"{pid}: non-design text artifact must still pass: {reasons}"
    # ...and the near-miss paths never enter the design arm
    for near in ("working/prompts/sales.design.txt", "prompts/sales.design.md",
                 "prompts/sales.txt"):
        assert not PV._DESIGN_PROMPT_REL_RE.match(near), near


def test_shipped_manifest_lookup_never_raises():
    """(D) nit: the old `SCRIPTS.parents[4]` raised IndexError at COLLECTION
    time outside the canonical tree depth."""
    import test_pd098_banked_design_revalidation as other
    # total: returns a Path or None, never raises, at ANY tree depth
    assert other._find_shipped_manifest() is not None
    assert _find_shipped_manifest() == other._find_shipped_manifest()

# ---------------------------------------------------------------------------
# PD-TEST-113 -- the verifier must apply the CONSUMER's whole gate, not just
# its length clause. The live prompts cleared the band and were then refused by
# their own render phase on AF-P13 / AF-R3 / AF-P14.
# ---------------------------------------------------------------------------
def _rewrite_artifact(rd: Path, pid: str, rel: str, text: str) -> None:
    """Write `text` as the phase's artifact and re-record its banked sha, so the
    verifier reads the mutated file and not a stale hash."""
    p = rd / rel
    p.write_text(text + "\n", encoding="utf-8")
    st = json.loads((rd / "state.json").read_text())
    for ph in st["phases"]:
        if ph["id"] == pid:
            ph["sha256"][rel] = hashlib.sha256(p.read_bytes()).hexdigest()
    StateStore(rd).save(st)


def _drop_negative_block(text: str) -> str:
    """The live VSL refusal, reproduced: the negative block collapses to the
    one-line 'no text' stub SOP 9.8 says does NOT satisfy AF-P13."""
    i = text.index("DO-NOT BLOCK")
    return text[:i] + "DO-NOT BLOCK\nDo not add text.\n"


MUTATIONS = (
    ("AF-P13", _drop_negative_block),
    ("AF-R3", lambda t: t.replace("skin tone fidelity",
                                  "a standard representation mix")),
    ("AF-P14", lambda t: t.replace("letter-for-letter", "faithfully")
                          .replace("exactly as written", "as intended")),
)


def test_verifier_agrees_with_the_consumer_gate(tmp_path):
    """THE PD-TEST-113 ACCEPTANCE TARGET, stated as the invariant that was
    broken: for an artifact INSIDE the band, `phase_verifiers.verify` must
    return the SAME verdict as `prompt_gate.prompt_problems` -- the function the
    render phase actually calls. Pre-fix the verifier enforced only AF-P1/AF-P2,
    so all three mutated artifacts below returned `(True, [])`, were attested
    `done`, and were then refused by P-U-DESIGN-RENDER-* after a full paid
    re-author each."""
    for code, mutate in MUTATIONS:
        rd, _mf = _run_with_live_artifacts(
            tmp_path, sizes={pid: PG.PROMPT_CHAR_CEILING for pid, _r, _n in DESIGN},
            gate_clean=True)
        rel = "prompts/sales.design.txt"
        # Built 200 chars under the ceiling so a mutation that GROWS the text
        # (the AF-R3 replacement is +10) cannot tip it out of band and turn this
        # into an AF-P2 test by accident.
        text = mutate(_gate_clean_prompt(PG.PROMPT_CHAR_CEILING - 200))
        assert len(text.strip()) <= PG.PROMPT_CHAR_CEILING, (
            f"must stay IN band: {len(text.strip())}")
        _rewrite_artifact(rd, "P-U-DESIGN-SALES", rel, text)

        problems = PG.prompt_problems(text)
        assert any(code in pr for pr in problems), (
            f"control for {code} is not actually deficient: {problems}")

        ok, reasons = PV.verify("P-U-DESIGN-SALES", rd)
        joined = " ".join(reasons)
        assert ok is (not problems), (
            f"{code}: verifier verdict {ok} disagrees with the consumer gate "
            f"({len(problems)} problem(s)): {reasons}")
        for problem in problems:
            assert problem in joined, (
                f"{code}: the verifier withheld the consumer's own reason "
                f"{problem[:70]!r} from prior_reasons, so no re-author can ever "
                f"converge on it")

# ---------------------------------------------------------------------------
# D1 / D2 -- the two defects the INDEPENDENT REVIEW of PR #1148 found. Both are
# the same shape as PD-TEST-113: a seam that disagrees with the consumer.
# ---------------------------------------------------------------------------
def test_verifier_strips_like_the_consumer_does(tmp_path):
    """D1: the verifier passed raw `text`; `build_infographic.resolve_design_prompt`
    passes `text.strip()`. `prompt_gate`'s structural check matches the literal
    `'Do not '` INCLUDING its trailing space, so a truncated file whose only such
    literal is a trailing-space EOF satisfies `prompt_problems(raw)` and is REFUSED
    by the consumer -- the exact one-directional divergence the review proved."""
    rd, _mf = _run_with_live_artifacts(
        tmp_path, sizes={pid: PG.PROMPT_CHAR_CEILING - 200 for pid, _r, _n in DESIGN},
        gate_clean=True)
    rel = "prompts/sales.design.txt"
    base = _gate_clean_prompt(PG.PROMPT_CHAR_CEILING - 200)
    # Rewrite every `Do not ` so that the ONLY surviving one is the final
    # trailing-space literal -- then let the fixture's "\n" make it a trailing-space EOF.
    text = base.replace("Do not ", "Never ").rstrip() + "\nDo not "
    assert PG.prompt_problems(text) == [], (
        "control is wrong: the RAW form must clear the gate")
    assert PG.prompt_problems(text.strip()) != [], (
        "control is wrong: the STRIPPED form must be refused")

    _rewrite_artifact(rd, "P-U-DESIGN-SALES", rel, text)
    ok, reasons = PV.verify("P-U-DESIGN-SALES", rd)
    joined = " ".join(reasons)
    assert ok is False, (
        "the verifier accepted an artifact its own render phase REFUSES: it must "
        "strip exactly as build_infographic.resolve_design_prompt does")
    assert "Do not" in joined, joined


def test_banked_predicate_applies_the_whole_gate(tmp_path):
    """D2: `artifacts.validate_design_prompt` enforced only the length band, and
    THAT is the arm deciding whether an already-`done` phase is re-opened
    (`_revalidate_banked` -> `validate_artifact`). An in-band prompt failing
    AF-P13 was still reusable banked work, so the phase was never re-opened and
    the strict verifier was never consulted -- the live state of P-U-DESIGN-SALES
    and P-U-DESIGN-VSL."""
    from presentation_job import artifacts as A
    rd, _mf = _run_with_live_artifacts(
        tmp_path, sizes={pid: PG.PROMPT_CHAR_CEILING for pid, _r, _n in DESIGN},
        gate_clean=True)
    rel = "prompts/sales.design.txt"
    text = _drop_negative_block(_gate_clean_prompt(PG.PROMPT_CHAR_CEILING))
    assert len(text.strip()) <= PG.PROMPT_CHAR_CEILING, "must stay IN band"
    _rewrite_artifact(rd, "P-U-DESIGN-SALES", rel, text)

    assert PG.prompt_problems(text.strip()), "control must fail the gate"
    ok, why = A.validate_artifact(rd, rel, None)
    assert ok is False, (
        "the banked predicate accepted an in-band prompt the render gate REFUSES, "
        "so a `done` phase holding it is never re-opened: " + str(why))
    assert "AF-P13" in str(why), why

