#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_sf_gate_coverage.py — the Signature Funnel NEGATIVE-TEST BATTERY (FIX-XC-05a).

This is the coverage emitter half of the gate-integrity harness (the presentation
department's `test_preflight.py` role, ported to Skill 49). It drives EVERY
python-enforced autofail in FUNNEL-MANIFEST.json to a deliberately-failing fixture
and records which AF codes actually FIRED. The result is written to
`working/af-coverage.json` and consumed by `gate_integrity_check.py` to prove the
"declared == enforced == TESTED" contract: a gate a prover cannot be made to raise
on a broken input is a latent no-op, and this battery is what makes that provable.

It REUSES each prover's own already-verified fixtures where they expose
`_violation_cases()` / `_valid_*()`, and adds targeted probes for the remaining
declared codes (the section-band / CTA / order codes the provers enforce but did
not individually fixture) plus the orchestrator-enforced phase gates
(HTML-FRAGMENT / BUILD-FAB / DERIVE-LEDGER / FRONT-DOOR).

Shell-enforced front-door codes (py_symbol `signature-funnel-entry.sh:*`) are OUT
OF SCOPE here — they are bash guards, tested by the entry shell's own self-checks.

Exit 0 = every in-scope declared code was triggered by a fixture (coverage COMPLETE,
af-coverage.json written). Exit 1 = a declared code could not be triggered (a probe
gap OR a genuinely-unenforceable gate — either way, fail-closed and reported).
Exit 2 = could not run (import / manifest error).

stdlib only.
"""
from __future__ import annotations

import json
import re
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Set, Tuple

HERE = Path(__file__).resolve().parent           # 49-signature-funnel/scripts
SKILL_DIR = HERE.parent                            # 49-signature-funnel
MANIFEST = SKILL_DIR / "FUNNEL-MANIFEST.json"
COVERAGE_OUT = HERE / "working" / "af-coverage.json"

for p in (str(HERE), str(SKILL_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

import prove_sf_intake as intake          # noqa: E402
import prove_sf_copy as copy_             # noqa: E402
import prove_sf_prompt_floor as pf        # noqa: E402
import prove_sf_graph as graph            # noqa: E402
import prove_sf_build as build            # noqa: E402
import prove_sf_no_pitch as nopitch       # noqa: E402
import prove_sf_cert as cert              # noqa: E402
import run_signature_funnel as runner     # noqa: E402

AF_RE = re.compile(r"AF-FUN-[A-Z0-9]+(?:-[A-Z0-9]+)*")


def _codes(pairs) -> Set[str]:
    """Collect AF codes from a list of (code, msg) tuples."""
    out: Set[str] = set()
    for c, _ in pairs:
        if isinstance(c, str) and c.startswith("AF-FUN-"):
            out.add(c)
    return out


def _codes_from_msg(msg: str) -> Set[str]:
    return set(AF_RE.findall(str(msg)))


# ---------------------------------------------------------------------------
# Probe batteries — each returns a set of AF codes actually raised.
# ---------------------------------------------------------------------------
def probe_intake() -> Set[str]:
    got: Set[str] = set()
    PL = intake._VALID_PERSONA_LOG

    def ev(fx, pl=PL):
        return _codes(intake.evaluate(fx, persona_log=pl))

    f = intake._valid_runtime(3); f["funnel_type"] = "sales_page"; got |= ev(f)
    f = intake._valid_runtime(3); del f["answers"]["q5_goods"]; got |= ev(f)
    f = intake._valid_runtime(3); f["funnel_size"] = 4; f["answers"]["q10_funnel_length"] = "4-step"; got |= ev(f)
    f = intake._valid_runtime(3); f["offer_token_ledger"] = []; got |= ev(f)
    f = intake._valid_runtime(3); f["answers"]["q8_representation"] = "   "; got |= ev(f)
    f = intake._valid_runtime(3); f["answers"]["q16_truth_gate"]["founder_text_confirmed"] = False; got |= ev(f)
    f = intake._valid_runtime(3); f["locked"] = False; got |= ev(f)
    got |= ev(intake._valid_runtime(3), pl=None)                     # persona-log
    return got


def probe_copy() -> Set[str]:
    got: Set[str] = set()
    structure = copy_._load_structure(None)

    def ev(ledger):
        v, _ = copy_.verify(structure, ledger)
        return _codes(v)

    # (a) the prover's own violation battery
    for _name, _expected, builder in copy_._violation_cases():
        got |= ev(builder())

    # (b) supplemental probes for the declared codes the battery did not fixture
    def sec(d, page, num):
        return copy_._sec(d, page, num)

    m = copy_._mut
    # PROFILE-UNKNOWN
    got |= ev(m(lambda d: d["pages"][0].__setitem__("page_type", "mystery")))
    # SECTION-EXTRA
    got |= ev(m(lambda d: copy_._main_secs(d).append({"section": 13, "name": "x", "copy": "y"})))
    # SECTION-ORDER (reverse -> not ascending)
    got |= ev(m(lambda d: d["pages"][0].__setitem__("sections", list(reversed(copy_._main_secs(d))))))
    # SEC1-CTA
    got |= ev(m(lambda d: sec(d, 0, 1).pop("cta", None)))
    # PAIN-CHARBAND
    got |= ev(m(lambda d: sec(d, 0, 2).__setitem__("copy", "You go now.")))
    # PAIN-CTA
    got |= ev(m(lambda d: sec(d, 0, 2).pop("cta", None)))
    # SEC5-WORDS
    got |= ev(m(lambda d: sec(d, 0, 5).__setitem__("copy", "That's the reason why " + "word " * 40)))
    # SEC5-CTA
    got |= ev(m(lambda d: sec(d, 0, 5).pop("cta", None)))
    # SEC6-WORDS
    got |= ev(m(lambda d: sec(d, 0, 6).__setitem__("copy", "word " * 40)))
    # SEC7-WORDS (too few words, bullet count preserved)
    got |= ev(m(lambda d: (sec(d, 0, 7).__setitem__("copy", "clarity"),
                           sec(d, 0, 7).__setitem__("bullets", ["short"] * 6))))
    # BENEFIT-WORDS
    got |= ev(m(lambda d: sec(d, 0, 8).__setitem__("copy", "word " * 40)))
    # BENEFIT-NO-CTA
    got |= ev(m(lambda d: sec(d, 0, 8).__setitem__("cta", "CTA: buy now")))
    # SEC11-WORDS (7 one-word steps)
    got |= ev(m(lambda d: sec(d, 0, 11).__setitem__("steps", ["one"] * 7)))
    # SEC11-NO-CTA-BUTTON
    got |= ev(m(lambda d: sec(d, 0, 11).__setitem__("has_cta_button", True)))
    # SEC11-STEPS (4 in-band steps)
    got |= ev(m(lambda d: sec(d, 0, 11).__setitem__(
        "steps", [copy_._fill("Take a clear morning action and keep repeating the same steady thing", 100)] * 4)))
    # SEC11-STEP7 (final step over 170)
    got |= ev(m(lambda d: sec(d, 0, 11)["steps"].__setitem__(-1, "x" * 180)))
    # SEC12-WORDS (6 one-word parts)
    got |= ev(m(lambda d: sec(d, 0, 12).__setitem__(
        "parts", [{"label": f"p{i}", "text": "a"} for i in range(6)])))
    # TY1-TITLE (valid band, no product title)
    got |= ev(m(lambda d: sec(d, 2, "TY-1").__setitem__(
        "copy", copy_._fill("A warm hello and welcome to the calm mornings that are now on their way to you", 150))))
    # TY2-STEPBAND (one short step)
    got |= ev(m(lambda d: sec(d, 2, "TY-2")["steps"].__setitem__(0, "short")))
    return got


def probe_prompt_floor() -> Set[str]:
    got: Set[str] = set()
    for _name, _expected, builder in pf._violation_cases():
        v, _ = pf.verify(builder())
        got |= _codes(v)
    # coverage cross-check (PROMPT-COVERAGE / IMG-COVERAGE)
    structure = pf.load_structure()
    skimpy_p = {"prompts": [{"page_type": "main", "section": 1, "prompt": "x"}]}
    v, _ = pf.verify_structure(3, skimpy_p, structure)
    got |= _codes(v)
    skimpy_i = {"images": [{"page_type": "main", "section": 1, "kie_task_id": "k",
                            "media_url": "https://msgsndr.com/a.png"}]}
    v, _ = pf.verify_structure(3, skimpy_i, structure)
    got |= _codes(v)
    return got


def probe_graph() -> Set[str]:
    got: Set[str] = set()
    for _name, _expected, builder in graph._violation_cases():
        v, _ = graph.verify(builder())
        got |= _codes(v)
    # GRAPH-TYPE (funnel_type mismatch) + GRAPH-REACH (unreachable node)
    g = graph._valid_graph(5); g["funnel_type"] = "sales_page"
    v, _ = graph.verify(g); got |= _codes(v)
    g = graph._valid_graph(5)
    g["edges"] = [e for e in g["edges"] if e.get("to") != "upsell"]
    v, _ = graph.verify(g); got |= _codes(v)
    return got


def probe_build() -> Set[str]:
    """A10 / T0-11: each build case is now (receipt, locked_funnel_size) — the
    completeness gate needs the size the brief locked, not whatever the receipt
    says about itself. Passing the tuple straight to verify() would make every
    fixture read as MALFORMED and silently drop the QC / PREVIEW / TYPE codes
    this probe exists to trigger."""
    got: Set[str] = set()
    for _name, _expected, builder in build._violation_cases():
        receipt, size = builder()
        v, _ = build.verify(receipt, funnel_size=size)
        got |= _codes(v)
    return got


def _codes_both(pairs) -> Set[str]:
    """Collect AF codes from BOTH the code slot AND the message (the fail-closed
    no-pitch findings carry the AF code inside the message text)."""
    out: Set[str] = set()
    for c, msg in pairs:
        if isinstance(c, str) and c.startswith("AF-FUN-"):
            out.add(c)
        out |= _codes_from_msg(msg)
    return out


def probe_no_pitch() -> Set[str]:
    got: Set[str] = set()
    for _name, _expected, builder in nopitch._violation_cases():
        _code, fails = nopitch.evaluate_ledger(builder())
        got |= _codes_both(fails)
    import copy as _c
    led = _c.deepcopy(nopitch._valid_ledger()); led["offer_token_ledger"] = []; led.pop("product_title", None)
    _c1, f = nopitch.evaluate_ledger(led); got |= _codes_both(f)
    led = _c.deepcopy(nopitch._valid_ledger())
    led["pages"] = [p for p in led["pages"] if p["page_type"] != "thank-you"]
    _c2, f = nopitch.evaluate_ledger(led); got |= _codes_both(f)
    led = _c.deepcopy(nopitch._valid_ledger()); led["images"] = []
    _c3, f = nopitch.evaluate_ledger(led); got |= _codes_both(f)
    return got


def probe_cert() -> Set[str]:
    got: Set[str] = set()
    nonce = "coverage-nonce-abc123"
    got |= _codes(cert.verify("not-a-dict", nonce))                        # CERT-MISSING
    c = cert._valid_cert(nonce); c["phases"] = c["phases"][:3] + c["phases"][4:]
    c["signature"] = cert.sign(cert.canonical_payload(c), nonce)
    got |= _codes(cert.verify(c, nonce))                                    # CERT-PHASE-GAP (+PROCESS-INTEGRITY)
    c = cert._valid_cert(nonce); c["phases"][2]["status"] = "fail"
    c["signature"] = cert.sign(cert.canonical_payload(c), nonce)
    got |= _codes(cert.verify(c, nonce))                                    # CERT-PHASE-FAIL
    got |= _codes(cert.verify(cert._valid_cert(nonce), "the-wrong-nonce"))  # CERT-SIGNATURE
    got |= _codes(cert.evaluate_model_receipt(None))                        # MODEL-TIER
    got |= _codes(cert.evaluate_model_receipt(
        {"role": "content", "model": "claude-opus-4", "provider": "anthropic", "tier": "content"}))  # NOANTHROPIC
    return got


def probe_runner() -> Set[str]:
    got: Set[str] = set()
    with tempfile.TemporaryDirectory() as td:
        rd = Path(td)
        # a brief with a resolvable size so the gate reaches its artifact check
        (rd / "brief.json").write_text(json.dumps({"funnel_type": "signature_funnel", "funnel_size": 3}))
        for fn in (runner._gate_html_fragments, runner._gate_derived_pages, runner._gate_build):
            ok, msg = fn(rd)
            if not ok:
                got |= _codes_from_msg(msg)
        ok, msg = runner._check_front_door(rd, None, None)
        if not ok:
            got |= _codes_from_msg(msg)
    return got


def probe_delegation() -> Set[str]:
    """A10 / T0-09 — the delegated image + media seams. Drive each to failure:
      * an EMPTY/no-provenance ledger the run authored              -> AF-FUN-DELEG-IMAGES
      * an off-host media URL                                       -> AF-FUN-DELEG-MEDIA
      * a receipt the ORCHESTRATOR stamped for itself     -> AF-FUN-DELEG-RECEIPT-SELF-AUTHORED
    The self-authored case is the headline: it proves the seam refuses evidence the
    certificate's own subject wrote, so the fixture is minted through the provider
    stub, then a self-authored receipt is forced on top."""
    import stub_provider_adapter  # noqa: F401  (imported for parity with the run path)
    import delegation_receipt
    got: Set[str] = set()
    with tempfile.TemporaryDirectory() as td:
        rd = Path(td)
        # no provenance -> AF-FUN-DELEG-IMAGES
        (rd / "media_ledger.json").write_text(json.dumps(
            {"images": [{"page_type": "main", "section": "1", "kie_task_id": "",
                         "media_url": "https://storage.gohighlevel.com/x.png"}]}))
        ok, msg = runner._gate_p3_images(rd)
        if not ok:
            got |= _codes_from_msg(msg)
        # off-host -> AF-FUN-DELEG-MEDIA (task id present so P3 would pass)
        (rd / "media_ledger.json").write_text(json.dumps(
            {"images": [{"page_type": "main", "section": "1", "kie_task_id": "kie-1",
                         "media_url": "https://cdn.somewhere-else.test/x.png"}]}))
        ok, msg = runner._gate_p4_media(rd)
        if not ok:
            got |= _codes_from_msg(msg)
    with tempfile.TemporaryDirectory() as td:
        rd = Path(td)
        (rd / "media_ledger.json").write_text(json.dumps(
            {"images": [{"page_type": "main", "section": "1", "kie_task_id": "kie-1",
                         "media_url": "https://storage.gohighlevel.com/x.png"}]}))
        # A receipt stamped recorded_by an orchestrator (a SUBJECT_MODULE) — exactly what a
        # self-authoring run would emit — must be refused. Written as a raw line so the fixture
        # carries the forged stamp regardless of who runs this probe.
        (rd / delegation_receipt.RECEIPTS_REL).write_text(json.dumps({
            "phase": "P3-IMAGES", "provider": "kie", "operation": "createTask",
            "provider_response_id": "kie-resp-x", "http_status": 200, "remote_id": "kie-1",
            "covers": ["kie-1"], "recorded_by": "run_signature_funnel", "at": "2026-07-21T00:00:00Z",
        }) + "\n", encoding="utf-8")
        ok, msg = runner._gate_p3_images(rd)
        if not ok:
            got |= _codes_from_msg(msg)
    return got


PROBES = [
    ("intake", probe_intake),
    ("copy", probe_copy),
    ("prompt_floor", probe_prompt_floor),
    ("graph", probe_graph),
    ("build", probe_build),
    ("no_pitch", probe_no_pitch),
    ("cert", probe_cert),
    ("runner", probe_runner),
    ("delegation", probe_delegation),
]


# ---------------------------------------------------------------------------
# In-scope declared codes = python-enforced autofails (py_symbol module.symbol,
# NOT a `*.sh:` shell guard).
# ---------------------------------------------------------------------------
def in_scope_codes() -> Tuple[Set[str], Set[str]]:
    manifest = json.loads(MANIFEST.read_text())
    codes = manifest.get("autofail_codes", {})
    py, shell = set(), set()
    for code, meta in codes.items():
        sym = str((meta or {}).get("py_symbol", ""))
        if ".sh:" in sym or sym.endswith(".sh"):
            shell.add(code)
        else:
            py.add(code)
    return py, shell


def main() -> int:
    py_scope, shell_scope = in_scope_codes()
    triggered: Set[str] = set()
    per_probe: Dict[str, List[str]] = {}
    for name, fn in PROBES:
        codes = fn()
        per_probe[name] = sorted(codes)
        triggered |= codes

    missing = sorted(py_scope - triggered)
    extra = sorted(triggered - py_scope)   # informational (side-effect codes)

    COVERAGE_OUT.parent.mkdir(parents=True, exist_ok=True)
    COVERAGE_OUT.write_text(json.dumps({
        "generated_by": "test_sf_gate_coverage.py",
        "skill": "49-signature-funnel",
        "in_scope_python_codes": sorted(py_scope),
        "shell_enforced_codes_out_of_scope": sorted(shell_scope),
        "triggered": sorted(triggered),
        "missing": missing,
        "per_probe": per_probe,
    }, indent=2) + "\n", encoding="utf-8")

    print(f"== test_sf_gate_coverage: negative-test battery ==")
    print(f"in-scope python-enforced codes: {len(py_scope)}")
    print(f"triggered by a failing fixture: {len(triggered & py_scope)}")
    print(f"shell-enforced (out of scope):  {len(shell_scope)} -> {sorted(shell_scope)}")
    if extra:
        print(f"note: {len(extra)} extra code(s) also triggered (side effects): {extra}")
    print(f"wrote {COVERAGE_OUT.relative_to(SKILL_DIR)}")
    if missing:
        print(f"FAIL: {len(missing)} declared code(s) NEVER triggered by any fixture (fail-closed):")
        for c in missing:
            print(f"  UNTESTED {c}")
        return 1
    print("PASS: every in-scope declared autofail was triggered by a deliberately-failing fixture.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
