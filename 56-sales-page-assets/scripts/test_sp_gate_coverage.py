#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_sp_gate_coverage.py — the Sales Page Assets NEGATIVE-TEST BATTERY (FIX-XC-05a).

The coverage emitter half of the gate-integrity harness (the presentation
department's `test_preflight.py` role, ported to Skill 56). It drives EVERY
python-enforced autofail in SALESPAGE-MANIFEST.json to a deliberately-failing
fixture and records which AF codes actually FIRED, into `working/af-coverage.json`,
which `gate_integrity_check.py` consumes to prove "declared == enforced == TESTED".

Reuses each prover's own already-verified fixtures (`_valid_*()` / `_violation_cases()`)
and adds targeted probes for the remaining declared codes plus the orchestrator-
enforced phase gates (FRAGMENT-MISSING / DOCS-MISSING / DELIVER-MISSING /
DELIVER-SUBJECT / BUILD-RECEIPT / FRONT-DOOR).

Shell-enforced front-door codes (py_symbol `sales-page-assets-entry.sh:*`) are OUT
OF SCOPE — bash guards proven by the entry shell's own self-checks.

Exit 0 = coverage COMPLETE; 1 = a declared code could not be triggered; 2 = cannot run.
stdlib only.
"""
from __future__ import annotations

import json
import re
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Set, Tuple

HERE = Path(__file__).resolve().parent            # 56-sales-page-assets/scripts
SKILL_DIR = HERE.parent                            # 56-sales-page-assets
MANIFEST = SKILL_DIR / "SALESPAGE-MANIFEST.json"
COVERAGE_OUT = HERE / "working" / "af-coverage.json"

for p in (str(HERE), str(SKILL_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

import prove_sp_intake as intake            # noqa: E402
import prove_sp_image_plan as imgplan       # noqa: E402
import prove_sp_prompt_floor as pf          # noqa: E402
import prove_sp_main_structure as mains     # noqa: E402
import prove_sp_upsell_structure as upsell  # noqa: E402
import prove_sp_highticket_band as hight    # noqa: E402
import prove_sp_bump_band as bump           # noqa: E402
import prove_sp_media as media              # noqa: E402
import prove_sp_bundle as bundle            # noqa: E402
import prove_sp_cert as cert                # noqa: E402
import run_sales_page_assets as runner      # noqa: E402

AF_RE = re.compile(r"AF-SP56-[A-Z0-9]+(?:-[A-Z0-9]+)*")


def _codes(pairs) -> Set[str]:
    """AF codes from BOTH the code slot AND the message (fail-closed findings carry
    the AF code inside the message text)."""
    out: Set[str] = set()
    for c, msg in pairs:
        if isinstance(c, str) and c.startswith("AF-SP56-"):
            out.add(c)
        out |= set(AF_RE.findall(str(msg)))
    return out


def _codes_from_msg(msg: str) -> Set[str]:
    return set(AF_RE.findall(str(msg)))


# ---------------------------------------------------------------------------
# Probe batteries.
# ---------------------------------------------------------------------------
def probe_intake() -> Set[str]:
    got: Set[str] = set()
    PL = intake._VALID_PERSONA_LOG

    def ev(fx, pl=PL):
        return _codes(intake.evaluate(fx, persona_log=pl))

    f = intake._valid_runtime(); f["funnel_type"] = "signature_funnel"; got |= ev(f)
    f = intake._valid_runtime(); del f["answers"]["bump_desc"]; got |= ev(f)
    f = intake._valid_runtime(); f["answers"]["image_prompt_count"] = 0; got |= ev(f)
    f = intake._valid_runtime(); f["answers"]["image_prompt_count"] = 21; got |= ev(f)
    f = intake._valid_runtime(); f["offer_token_ledger"] = []; got |= ev(f)
    f = intake._valid_runtime(); f["client_slug"] = "Jane Doe"; got |= ev(f)
    f = intake._valid_runtime(); f["locked"] = False; got |= ev(f)
    got |= ev(intake._valid_runtime(), pl=None)
    return got


def probe_image_plan() -> Set[str]:
    got: Set[str] = set()
    got |= _codes(imgplan.evaluate(imgplan._valid_plan(4)))          # SLICE
    f = imgplan._valid_plan(12); f["image_prompt_count"] = 11
    got |= _codes(imgplan.evaluate(f))                               # COUNT
    f = imgplan._valid_plan(12); f["prompts"][5]["index"] = 99
    got |= _codes(imgplan.evaluate(f))                               # INDEX
    f = imgplan._valid_plan(12); f["prompts"][10]["prompt_text"] = "   "
    got |= _codes(imgplan.evaluate(f))                               # EMPTY-PROMPT
    got |= _codes(imgplan.evaluate({"image_prompt_count": 0, "prompts": []}))  # EMPTY
    return got


def probe_prompt_floor() -> Set[str]:
    got: Set[str] = set()
    for _name, _expected, builder in pf._violation_cases():
        v, _ = pf.verify(builder())
        got |= _codes(v)
    return got


def probe_main() -> Set[str]:
    got: Set[str] = set()

    def ev(fx):
        return _codes(mains.evaluate(fx))

    f = mains._valid_ledger(); f["assets"] = [f["assets"][0]]; got |= ev(f)          # VARIANT
    f = mains._valid_ledger(); f["assets"][0]["sections"] = f["assets"][0]["sections"][:7]; got |= ev(f)  # COUNT+MISSING
    f = mains._valid_ledger()
    f["assets"][1]["sections"] = [{"order": i + 1, "name": nm, "copy": mains._FIXTURE_COPY} for i, nm in enumerate(
        ["Attention-Grabbing Header", "Hero Section", "Benefits Section", "Problem & Solution",
         "Product Details", "Credibility Section", "Final Call to Action", "Footer"])]
    got |= ev(f)                                                                     # ORDER
    f = mains._valid_ledger(); f["assets"][0]["sections"][5] = {"order": 6, "name": "Bonus Stack"}
    got |= ev(f)                                                                     # UNKNOWN (+MISSING)
    f = mains._valid_ledger(); f["assets"][0]["sections"][1]["copy"] = "Too thin to convert."
    got |= ev(f)                                                                     # BAND
    f = mains._valid_ledger(); f["assets"][1]["has_countdown_timer"] = False; got |= ev(f)  # COUNTDOWN
    got |= ev({"assets": []})                                                        # EMPTY
    return got


def probe_upsell() -> Set[str]:
    got: Set[str] = set()

    def ev(fx):
        return _codes(upsell.evaluate(fx))

    f = upsell._valid_ledger(); f["assets"] = [f["assets"][1]]; got |= ev(f)          # VARIANT
    f = upsell._valid_ledger(); f["assets"][0]["sections"] = f["assets"][0]["sections"][:8]; got |= ev(f)  # COUNT+MISSING
    f = upsell._valid_ledger()
    swap = list(upsell._CANON_ORDER); swap[4], swap[5] = swap[5], swap[4]
    f["assets"][1]["sections"] = [{"order": i + 1, "name": nm, "copy": upsell._FIXTURE_COPY} for i, nm in enumerate(swap)]
    got |= ev(f)                                                                      # ORDER
    f = upsell._valid_ledger(); f["assets"][0]["sections"][6] = {"order": 7, "name": "Bonus Vault"}
    got |= ev(f)                                                                      # UNKNOWN (+MISSING)
    f = upsell._valid_ledger(); f["assets"][1]["sections"][0]["copy"] = "Nice upgrade, buy it."
    got |= ev(f)                                                                      # BAND
    got |= ev({"assets": []})                                                         # EMPTY
    return got


def probe_highticket() -> Set[str]:
    got: Set[str] = set()
    lo, hi = hight._band()
    got |= _codes(hight.evaluate({"assets": [hight._asset_with_words(lo - 1)]}))       # FLOOR
    got |= _codes(hight.evaluate({"assets": [hight._asset_with_words(hi + 1)]}))       # CEILING
    got |= _codes(hight.evaluate({"assets": []}))                                      # EMPTY
    return got


def probe_bump() -> Set[str]:
    got: Set[str] = set()
    lo, hi, _rx = bump._band_and_checkbox()
    got |= _codes(bump.evaluate({"assets": [bump._bump(lo - 1)]}))                     # FLOOR
    got |= _codes(bump.evaluate({"assets": [bump._bump(hi + 1)]}))                     # CEILING
    got |= _codes(bump.evaluate({"assets": [bump._bump(60, checkbox=False)]}))         # NO-CHECKBOX
    got |= _codes(bump.evaluate({"assets": []}))                                       # EMPTY
    return got


def probe_media() -> Set[str]:
    got: Set[str] = set()
    plan = media._valid_plan()
    for _name, _expected, builder in media._violation_cases():
        _code, fails = media.evaluate_media(builder(), plan)
        got |= _codes(fails)
    _c, f = media.evaluate_media({"images": []}, plan); got |= _codes(f)               # MEDIA-EMPTY
    _c, f = media.evaluate_media(media._valid_media(), {"prompts": []}); got |= _codes(f)  # MEDIA-PLAN-EMPTY
    return got


def probe_bundle() -> Set[str]:
    got: Set[str] = set()

    def ev(fx):
        return _codes(bundle.evaluate(fx))

    _norm = bundle._norm
    f = bundle._valid_manifest(); f["steps"][0]["asset_key"] = "jane-doe__glow-method__main__claude__v01a"; got |= ev(f)  # LABEL
    f = bundle._valid_manifest(); f["funnel_name"] = "jane-doe glow-method v01"; got |= ev(f)   # ZHC
    f = bundle._valid_manifest(); f["seo"]["keywords"] = ["only-one"]; got |= ev(f)             # SEO
    f = bundle._valid_manifest(); f["steps"][0].pop("fragment_path"); got |= ev(f)              # FRAGMENT
    f = bundle._valid_manifest(); f["steps"][0].pop("method_decision"); got |= ev(f)            # METHOD
    f = bundle._valid_manifest(); f["steps"][0].pop("copy_tokens", None); got |= ev(f)          # COPYTOKENS
    f = bundle._valid_manifest(); f["steps"] = [s for s in f["steps"] if _norm(s.get("stage")) != "thank-you"]; got |= ev(f)  # THANKYOU
    f = bundle._valid_manifest()
    for s in f["steps"]:
        if _norm(s.get("stage")) == "bump":
            s["route"] = "DIRECT"
    got |= ev(f)                                                                                # BUMP-ROUTE
    f = bundle._valid_manifest(); f.pop("location_id"); got |= ev(f)                            # LOCATION
    got |= ev({"funnel_name": "ZHC x y v01", "steps": []})                                      # EMPTY
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
        for fn in (runner._fragments_gate, runner._docs_gate, runner._deliver_gate,
                   runner._build_receipt_gate):
            ok, msg = fn(rd)
            if not ok:
                got |= _codes_from_msg(msg)
        # DELIVER-SUBJECT needs a delivery.json with a leftover 'test' subject
        (rd / "delivery.json").write_text(json.dumps({"subject": "test send", "folder_link": "https://x"}))
        ok, msg = runner._deliver_gate(rd)
        if not ok:
            got |= _codes_from_msg(msg)
        ok, msg = runner._check_front_door(rd, None, None)
        if not ok:
            got |= _codes_from_msg(msg)
    return got


PROBES = [
    ("intake", probe_intake),
    ("image_plan", probe_image_plan),
    ("prompt_floor", probe_prompt_floor),
    ("main", probe_main),
    ("upsell", probe_upsell),
    ("highticket", probe_highticket),
    ("bump", probe_bump),
    ("media", probe_media),
    ("bundle", probe_bundle),
    ("cert", probe_cert),
    ("runner", probe_runner),
]


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
    extra = sorted(triggered - py_scope)

    COVERAGE_OUT.parent.mkdir(parents=True, exist_ok=True)
    COVERAGE_OUT.write_text(json.dumps({
        "generated_by": "test_sp_gate_coverage.py",
        "skill": "56-sales-page-assets",
        "in_scope_python_codes": sorted(py_scope),
        "shell_enforced_codes_out_of_scope": sorted(shell_scope),
        "triggered": sorted(triggered),
        "missing": missing,
        "per_probe": per_probe,
    }, indent=2) + "\n", encoding="utf-8")

    print("== test_sp_gate_coverage: negative-test battery ==")
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
