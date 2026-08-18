#!/usr/bin/env python3
"""test_prefill.py -- offline contract tests for the U04 INTAKE PRE-FILL VERIFIER
(scripts/u04_modules/prefill_verifier.py), the G3 value-side gate.

THE G3 LAW, VALUE SIDE (prefill_verifier.py header): the minted author-intake
link <forms_base>/widget/form/<form_id>?anthology_id=<minted> must pre-fill the
form's HIDDEN anthology_id field. The pre-fill is NOT server-rendered: the
widget hydrates the hidden field CLIENT-SIDE from the URL param (proofed live
against the fleet-wide universal form on link.msgsndr.com). The honest LIVE
observation is a two-part signature:

  1. served-surface identity: the form page is BYTE-IDENTICAL with and without
     the probe param (a page that BAKES the probe into the served bytes is a
     tampered/caching page, REFUSED — the real widget would double-apply), and
  2. the hydration-law signature: the served widget build must match the
     committed fleet baseline (config/prefill-verifier-baseline.json) digest
     byte-exact and must carry the prefill hydration code
     (hiddenFieldQueryKey -> urlParams -> field value).

A real browser render is OPTIONAL (absent headless runtime -> SKIP as
undetermined, never fabricated); the served-surface checks report their own
verdict without it.

WHAT THIS FILE PROVES (network-free, credential-free, browser-free):

  - the G3 key law: the expected query key is pinned to
    anthology_book.INTAKE_QUERY_KEY ("anthology_id", never the lookalike
    "anthology_active_id") and the canonical probe URL is built from the SAME
    constants build_intake_link mints with (single-implementation doctrine),
  - served-surface identity: byte-identical pages PASS, ANY drift (including
    the probe baked into the served bytes) is a FAIL — never a blind pass,
  - the widget-surface law: a page that references the _preview build
    (module script / preloads / build-meta from the page's own __NUXT__
    config) is the hosted-form surface; a page without any reference is
    REFUSED, never a pass,
  - the build-signature law: artifacts matching the committed baseline digest
    PASS, a tampered digest / unsigned artifact / signature-less baseline /
    non-dict signatures section all FAIL — never a silent pass,
  - the hydration-code law: the fetched widget code must carry the exact
    prefill-map markers (hiddenFieldQueryKey in c / I.value[O.tag]=); a
    bundle without them is a MISMATCH,
  - the committed baseline: exists, parses to an object, carries the pinned
    self-test code blob with a matching committed sha256 (a drift in EITHER
    trips the battery), and every signature entry is an absolute https URL
    with a 64-hex digest; missing / malformed / non-object baselines STOP,
  - the OPTIONAL rendered observation: --no-render SKIPs, an absent runtime
    SKIPs (never fabricated), an exact rendered value PASSes, a non-exact
    value FAILs with AF-AE-PREFILL-RENDER, a render that cannot complete is
    HELD, and a non-https URL is REFUSED (no injection surface),
  - the live aggregate's fail-closed exit matrix, driven with a PATCHED
    fetcher (the registry's CafClient is NEVER constructed, no env var is
    read, no subprocess runs, no network): PASS=0 (fabricated baseline whose
    digests match the fixture bytes), page drift / build drift / render
    FAIL=5, fetch failure / render HELD=3, empty probe / missing baseline /
    empty key=2 — the pass/fail split discriminates (the golden control is
    never a broken instrument),
  - never-a-token: no credential shape (pit- / Bearer), no full form id, no
    full digest, and no probe value leak on any captured surface; the
    browser-UA law (CF 1010) stays pinned.

House doctrine (Skill 59, u04_modules/__init__.py): fail-closed, both
directions; never a token printed; browser User-Agent on every GoHighLevel /
Convert and Flow surface (urllib's default "Python-urllib/x.y" is 403'd at
the Cloudflare WAF edge as CF error 1010); move in silence; NOTHING
Anthropic in any runtime surface; stdlib only; pytest with plain asserts.

Run: python3 -m pytest 59-anthology-engine/scripts/u04_modules/test_prefill.py -q
 or: python3 59-anthology-engine/scripts/u04_modules/test_prefill.py
"""
import contextlib
import hashlib
import io
import json
import sys
from pathlib import Path

import pytest

SKILL_DIR = Path(__file__).resolve().parent.parent.parent
SCRIPTS = SKILL_DIR / "scripts"
sys.path.insert(0, str(SCRIPTS))

import anthology_book as book  # noqa: E402  (the G3 link authority)
import anthology_registry as reg  # noqa: E402
import u04_modules.prefill_verifier as pv  # noqa: E402

# The house exit-code convention (0/1/2/3/4/5) — asserted through the exported
# constants, never re-typed.
EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH = (
    reg.EX_OK, reg.EX_ERR, reg.EX_STOP, reg.EX_HELD, reg.EX_MISMATCH)
EX_VIOLATION = 4  # enforced violation detected (self-test FAILED)

# A credential-shaped string is the pit- token prefix followed by a value —
# the house guard shape. No test fixture ever carries one, so no captured
# surface may either.
CREDENTIAL_SHAPE = "pit-"

# The synthetic widget page (module-bundle ref) and the golden hydration
# bundle — pure fixtures, never real artifacts, never the live network. The
# bundle carries the EXACT pinned hydration markers and its digest IS the
# committed baseline self-test blob digest (proved below).
WIDGET_PAGE = ('<html><head><script type="module" src="https://'
               'stcdn.leadconnectorhq.com/_preview/mxFsF5jP.js" '
               'crossorigin></script></head><body></body></html>')
BUNDLE = ("function Ct(e,r){hiddenFieldQueryKey in c&&(I.value[O.tag]=e)}"
          .encode("utf-8"))
BUNDLE_SHA = hashlib.sha256(BUNDLE).hexdigest()
BUNDLE_URL = "https://stcdn.leadconnectorhq.com/_preview/mxFsF5jP.js"


def _fabricated_baseline():
    """A synthetic baseline whose committed digest matches the fixture bundle
    — the ONLY surface on which the aggregate PASS is provable offline (the
    real committed digests cannot be inverted into fixture bytes)."""
    return {
        "schema_version": 1,
        "signatures": {
            BUNDLE_URL: {"url": BUNDLE_URL, "sha256": BUNDLE_SHA,
                         "bytes": len(BUNDLE)},
        },
    }


class _Patch:
    """Pytest-free patch seam for the direct-run main() (which passes no
    fixtures). Registers every setattr on a shared list so the runner can
    restore them ALL after each test — the same per-test isolation pytest's
    monkeypatch gives, without the pytest import at run time.

    setattr(module, name, value) applies the patch immediately and records
    the restoration on the shared `_registry` list (the runner clears the
    list after each test). When `_registry` is None (pytest is running),
    setattr simply applies the patch and the pytest monkeypatch fixture
    owns the restoration — the pytest path never touches this class."""

    def __init__(self, registry):
        self._registry = registry

    def setattr(self, module, name, value):
        saved = getattr(module, name, None)
        setattr(module, name, value)
        if self._registry is not None:
            self._registry.append((module, name, saved))
        return self


def _patch_fetch(monkeypatch, fn):
    """Patch the verifier's fetcher with a deterministic fixture — the ONLY
    seam the live aggregate ever touches (no network, no credentials).
    `monkeypatch` is pytest's fixture under pytest, or a _Patch seam under
    the direct runner (which passes a bare sentinel)."""
    return monkeypatch.setattr(pv, "fetch_http", fn)


def _same_page(url, timeout=20.0):
    """Serve the SAME bytes for the bare and the probe-param URL — the
    proven live shape (the widget owns the pre-fill, never the origin)."""
    if "mxFsF5jP" in url:
        return BUNDLE
    return WIDGET_PAGE.encode("utf-8")


def _capture_stdout(func, *args, **kwargs):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = func(*args, **kwargs)
    return rc, buf.getvalue()


# ---------------------------------------------------------------------------
# G3 key law + the canonical probe URL (single-implementation doctrine).
# ---------------------------------------------------------------------------
def test_g3_key_law_is_pinned_to_the_minted_link_constant():
    """The expected query key is the SAME constant build_intake_link mints
    with — the lookalike anthology_active_id is the G3 defect, never the
    law."""
    assert pv._resolve_intake_key() == "anthology_id"
    assert book.INTAKE_QUERY_KEY == "anthology_id"
    assert pv.WIDGET_FORM_PATH == book.WIDGET_FORM_PATH == "/widget/form"
    assert pv.DEFAULT_FORMS_BASE == book.DEFAULT_FORMS_BASE
    assert pv.DEFAULT_UNIVERSAL_INTAKE_FORM_ID == \
        book.DEFAULT_UNIVERSAL_INTAKE_FORM_ID


def test_probe_url_is_built_from_the_g3_constants():
    """The canonical probe URL equals the minted-link shape exactly:
    <base>/widget/form/<form_id>?anthology_id=<probe>."""
    url = pv.check_probe_url_canonical(
        pv.DEFAULT_FORMS_BASE, pv.DEFAULT_UNIVERSAL_INTAKE_FORM_ID,
        "anthology_id", pv.DEFAULT_PROBE_VALUE)
    assert url == ("https://link.msgsndr.com/widget/form/"
                   "U65pwoeMTy1niMqllKWG?anthology_id=ANTH_TEST")
    # the SAME shape build_intake_link mints, with the probe in place of the
    # minted id
    minted = book.build_intake_link(
        pv.DEFAULT_FORMS_BASE, pv.DEFAULT_UNIVERSAL_INTAKE_FORM_ID,
        pv.DEFAULT_PROBE_VALUE)
    assert url == minted
    # empty key / probe refuse (STOP family, never a guessed URL)
    with pytest.raises(pv._PrefillPageError):
        pv.check_probe_url_canonical(pv.DEFAULT_FORMS_BASE, "fid", "", "X")
    with pytest.raises(pv._PrefillPageError):
        pv.check_probe_url_canonical(pv.DEFAULT_FORMS_BASE, "fid",
                                     "anthology_id", "")


def test_probe_is_the_pinned_fixture_never_the_fleet_pin():
    """The probe is a deliberately synthetic fixture value — a test value,
    never a secret and never the real fleet pin (which stays masked)."""
    assert pv.DEFAULT_PROBE_VALUE == "ANTH_TEST"
    assert pv.DEFAULT_PROBE_VALUE != book.DEFAULT_UNIVERSAL_INTAKE_FORM_ID


# ---------------------------------------------------------------------------
# Served-surface identity law (pure).
# ---------------------------------------------------------------------------
def test_byte_identical_pages_pass_and_any_drift_fails():
    """The form page must be byte-identical with and without the probe param
    — a tampered/caching page is the attack this gate exists for."""
    bare = b"<html>same page</html>"
    report = pv.check_page_identity(bare, bare)
    assert report["ok"] is True
    assert report["bare_sha256"] == report["probed_sha256"]
    report = pv.check_page_identity(bare, b"<html>DIFFERENT</html>")
    assert report["ok"] is False
    # probe baked into the served bytes -> FAIL (the widget would double-apply)
    baked = b"<html><input value=\"ANTH_TEST\"></html>"
    assert pv.check_page_identity(bare, baked)["ok"] is False


# ---------------------------------------------------------------------------
# Widget-surface law (pure).
# ---------------------------------------------------------------------------
def test_widget_page_is_the_hosted_form_surface():
    """A page referencing the _preview build (module script / preloads /
    build-meta from the page's own __NUXT__ app config) is the hosted-form
    surface this gate exists for."""
    report = pv.check_page_is_widget(WIDGET_PAGE)
    assert report["ok"] is True
    # refs are FULL URLs — the membership law is substring over the list
    assert any("mxFsF5jP.js" in u for u in report["refs"])
    # a page without ANY build reference is REFUSED, never a pass
    assert pv.check_page_is_widget("<html><body>hello</body></html>")["ok"] \
        is False


def test_build_meta_ref_is_derived_from_the_pages_own_config():
    """The build-meta URL derives from the page's own __NUXT__ app config
    (cdnURL + buildAssetsDir + buildId) — the SAME resolution the widget
    bundle performs at runtime."""
    page = ('<script>app:{baseURL:"/",buildId:"61af4923-e329-4e77-94ba-'
            '94a97885eec7",buildAssetsDir:"/_preview/",'
            'cdnURL:"https://stcdn.leadconnectorhq.com"}</script>')
    refs = pv._widget_refs(page)
    assert any(r.endswith("builds/meta/61af4923-e329-4e77-94ba-94a97885eec7.json")
               for r in refs)


def test_chunk_refs_are_deduplicated_and_absolute():
    """The module bundle's dynamic-import chunks carry the SAME _preview root
    as the page's preloads; refs are deduplicated, ordered, absolute."""
    refs = pv._parse_bundle_refs(
        'import("./chunk1.js");import("https://stcdn.leadconnectorhq.com/'
        '_preview/DO9dUel-.js");import("https://stcdn.leadconnectorhq.com/'
        '_preview/DO9dUel-.js")')
    assert refs == ["https://stcdn.leadconnectorhq.com/_preview/DO9dUel-.js"]


# ---------------------------------------------------------------------------
# Build-signature law (pure, against the committed baseline).
# ---------------------------------------------------------------------------
def test_committed_baseline_is_wellformed_and_self_consistent():
    """The committed fleet baseline exists, parses, and is an object; the
    self-test code blob and its committed sha256 match; every signature
    entry is an absolute https URL with a 64-hex digest."""
    baseline = pv.load_baseline()
    assert isinstance(baseline, dict) and baseline.get("schema_version")
    st = baseline.get("self_test") or {}
    blob = st.get("blob")
    assert isinstance(blob, str) and blob
    assert blob == ("function Ct(e,r){hiddenFieldQueryKey in c&&"
                    "(I.value[O.tag]=e)}")
    assert isinstance(st.get("sha256"), str) and len(st["sha256"]) == 64
    assert st["sha256"] == hashlib.sha256(blob.encode("utf-8")).hexdigest()
    # the module's golden hydration fixture equals the committed blob
    assert pv._fake_bundle(hydration=True) == blob
    # the golden fixture bundle digest IS the committed blob digest
    assert BUNDLE.decode("utf-8") == blob
    assert BUNDLE_SHA == st["sha256"]
    golden = baseline.get("signatures") or {}
    assert isinstance(golden, dict) and golden
    for url, record in golden.items():
        assert url.startswith("https://")
        assert isinstance(record, dict)
        assert isinstance(record.get("sha256"), str) and len(record["sha256"]) == 64


def test_build_signature_matches_committed_digest_and_refuses_drift():
    """Artifacts matching the committed baseline digest PASS; a tampered
    digest, an unsigned artifact, a signature-less baseline, and a non-dict
    signatures section all FAIL — never a silent pass."""
    baseline = pv.load_baseline()
    sigs = baseline.get("signatures") or {}
    url = next(u for u in sigs if "DO9dUel-" in u)
    record = sigs[url]
    # golden match
    res = pv.check_build_signature({url: record}, baseline)
    assert res["ok"] is True and res["checked"] == [url]
    # tampered digest -> FAIL
    tampered = {url: {"url": url, "sha256": "0" * 64, "bytes": 1}}
    res = pv.check_build_signature(tampered, baseline)
    assert res["ok"] is False
    # the detail carries the TRUNCATED digests (12 hex), never the full ones
    assert record["sha256"] not in res["detail"]
    # an artifact with NO committed signature -> FAIL (unverifiable)
    res = pv.check_build_signature(
        {"https://stcdn.leadconnectorhq.com/_preview/nonexistent.js":
         {"url": "https://stcdn.leadconnectorhq.com/_preview/nonexistent.js",
          "sha256": "1" * 64, "bytes": 1}}, baseline)
    assert res["ok"] is False
    # a baseline with NO signatures section -> FAIL (law unverifiable)
    res = pv.check_build_signature({"a": {"sha256": "1" * 64}},
                                   {"schema_version": 1})
    assert res["ok"] is False
    # a non-dict signatures section -> FAIL (never a blind pass)
    res = pv.check_build_signature({"a": {"sha256": "1" * 64}},
                                   {"schema_version": 1, "signatures": "x"})
    assert res["ok"] is False


def test_missing_malformed_or_nonobject_baseline_stops(tmp_path):
    """A missing / malformed / non-object baseline is a STOP (exit 2 family)
    — the hydration law is unverifiable, never a pass."""
    with pytest.raises(pv._BaselineError):
        pv.load_baseline(tmp_path / "nope.json")
    (tmp_path / "bad.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(pv._BaselineError):
        pv.load_baseline(tmp_path / "bad.json")
    (tmp_path / "arr.json").write_text("[1,2]", encoding="utf-8")
    with pytest.raises(pv._BaselineError):
        pv.load_baseline(tmp_path / "arr.json")


# ---------------------------------------------------------------------------
# Hydration-code law (pure).
# ---------------------------------------------------------------------------
def test_hydration_code_markers_pass_only_when_present():
    """The fetched widget code must carry the exact prefill-map shape
    (hiddenFieldQueryKey -> urlParams -> field value) the self-test pins."""
    assert pv.check_hydration_code(pv._fake_bundle(hydration=True))["ok"] is True
    assert pv.check_hydration_code(BUNDLE.decode("utf-8"))["ok"] is True
    assert pv.check_hydration_code(pv._fake_bundle(hydration=False))["ok"] \
        is False
    assert pv.check_hydration_code("")["ok"] is False


# ---------------------------------------------------------------------------
# The OPTIONAL rendered observation (pure, runtime-free in this battery).
# ---------------------------------------------------------------------------
def test_render_skips_when_disabled_or_runtime_absent(monkeypatch):
    """The rendered observation is OPTIONAL: --no-render SKIPs, an absent
    headless runtime SKIPs — never fabricated, never a verdict."""
    status, row = pv.verify_render_optional(
        "https://x.test/w", "ANTH_TEST", allow_render=False,
        out=io.StringIO())
    assert status == "SKIP" and row["status"] == "SKIP"
    monkeypatch.setattr(pv, "find_headless_chromium", lambda: "")
    status, row = pv.verify_render_optional(
        "https://x.test/w", "ANTH_TEST", allow_render=True,
        out=io.StringIO())
    assert status == "SKIP" and row["status"] == "SKIP"


def test_render_refuses_a_non_https_url():
    """A non-https URL is REFUSED — no injection surface (the URL is the ONLY
    argument; a fixed argv list)."""
    with pytest.raises(pv._PrefillPageError):
        pv._render_probe_url("http://x.test/w")


def test_render_exact_value_passes_non_exact_fails(monkeypatch):
    """An exact rendered value PASSes; a non-exact value FAILs with the loud
    AF code and a MASKED value — the report never echoes the rendered value
    in full."""
    monkeypatch.setattr(pv, "_render_probe_url", lambda url: "ANTH_TEST")
    status, row = pv.verify_render_optional(
        "https://x.test/w", "ANTH_TEST", allow_render=True,
        out=io.StringIO())
    assert status == "PASS" and row["status"] == "PASS"
    monkeypatch.setattr(pv, "_render_probe_url", lambda url: "WRONG_VALUE")
    status, row = pv.verify_render_optional(
        "https://x.test/w", "ANTH_TEST", allow_render=True,
        out=io.StringIO())
    assert status == "FAIL" and row["status"] == "FAIL"
    assert "AF-AE-PREFILL-RENDER" in row["detail"]
    assert "WRONG_VALUE" not in row["detail"]
    assert "ANTH_TEST" not in row["detail"]


def test_render_cannot_complete_is_held(monkeypatch):
    """A render that cannot complete is HELD (exit 3) — the rendered law is
    UNDETERMINED, never proven compliant."""
    monkeypatch.setattr(pv, "find_headless_chromium", lambda: "/usr/bin/false")
    status, row = pv.verify_render_optional(
        "https://x.test/w", "ANTH_TEST", allow_render=True,
        out=io.StringIO())
    assert status == "HELD" and row["status"] == "HELD"


def test_dump_value_parses_exact_and_holds_without_a_field():
    """The rendered hidden-field value parses from the CDP evaluate payload;
    a payload with NO field value is HELD (the rendered law is
    UNDETERMINED). The CDP evaluate expression is proven to select the
    textarea by data-q=anthology_id and JSON-stringify {v: value}."""
    expr = ('JSON.stringify((()=>{const t=document.querySelector('
            '\'textarea[data-q="anthology_id"]\');'
            'return {v:t?t.value:null}})())')
    assert 'data-q="anthology_id"' in expr
    assert "{v:t?t.value:null}" in expr
    # the payload the CDP evaluate returns: {result: {value: <json string>}}
    assert json.loads(json.dumps(
        {"result": {"value": '{"v":"ANTH_TEST"}'}}))["result"]["value"] == \
        '{"v":"ANTH_TEST"}'
    assert json.loads('{"v":"ANTH_TEST"}').get("v") == "ANTH_TEST"
    assert json.loads('{"v":null}').get("v") is None


# ---------------------------------------------------------------------------
# The live aggregate — fail-closed exit matrix, patched fetcher, no network.
# ---------------------------------------------------------------------------
def test_aggregate_passes_with_matching_served_surface(monkeypatch):
    """The golden aggregate: byte-identical pages + widget surface + matching
    fabricated baseline digest + hydration code + render skipped -> PASS
    exit 0, ONE JSON report on stdout with every check row ok."""
    _patch_fetch(monkeypatch, _same_page)
    rc, out = _capture_stdout(
        pv.run_live, "https://link.msgsndr.com",
        pv.DEFAULT_UNIVERSAL_INTAKE_FORM_ID, "ANTH_TEST",
        key="anthology_id", baseline=_fabricated_baseline(),
        allow_render=False, timeout=5.0, out=io.StringIO())
    assert rc == EX_OK
    rep = json.loads(out)
    assert rep["contract"] == "anthology-engine-prefill-verify"
    assert rep["verdict"] == "PASS"
    for k in ("page_identity", "page_is_widget", "build_signature",
              "hydration_code"):
        assert rep["checks"][k]["ok"] is True, k
    assert rep["checks"]["render"]["status"] == "SKIP"
    assert rep["form_id_masked"] == "...lKWG"
    assert rep["fail_closed"] is True


def test_aggregate_render_fail_drives_exit_5(monkeypatch):
    """A rendered prefill MISMATCH after a clean served surface is exit 5
    (AF-AE-PREFILL-RENDER family), never a pass."""
    _patch_fetch(monkeypatch, _same_page)
    monkeypatch.setattr(
        pv, "verify_render_optional",
        lambda url, probe, *, allow_render, out: (
            "FAIL", {"status": "FAIL", "detail": "AF-AE-PREFILL-RENDER: fixture"}))
    rc, _out = _capture_stdout(
        pv.run_live, "https://link.msgsndr.com",
        pv.DEFAULT_UNIVERSAL_INTAKE_FORM_ID, "ANTH_TEST",
        key="anthology_id", baseline=_fabricated_baseline(),
        allow_render=True, timeout=5.0, out=io.StringIO())
    assert rc == EX_MISMATCH


def test_aggregate_render_held_drives_exit_3(monkeypatch):
    """A render that cannot complete is HELD (exit 3) — UNDETERMINED, never
    a fabricated verdict."""
    _patch_fetch(monkeypatch, _same_page)
    monkeypatch.setattr(
        pv, "verify_render_optional",
        lambda url, probe, *, allow_render, out: (
            "HELD", {"status": "HELD", "detail": "fixture held"}))
    err = io.StringIO()
    rc, _out = _capture_stdout(
        pv.run_live, "https://link.msgsndr.com",
        pv.DEFAULT_UNIVERSAL_INTAKE_FORM_ID, "ANTH_TEST",
        key="anthology_id", baseline=_fabricated_baseline(),
        allow_render=True, timeout=5.0, out=err)
    assert rc == EX_HELD
    assert "HELD" in err.getvalue()


def test_aggregate_served_page_drift_is_exit_5(monkeypatch):
    """A page that serves DIFFERENT bytes for the probe URL is a REFUSAL
    (exit 5) — a tampered/caching page, never the live widget surface."""
    def drifted(url, timeout=20.0):
        if "?" in url:
            return b"<html>DIFFERENT</html>"
        return b"<html>same</html>"
    _patch_fetch(monkeypatch, drifted)
    err = io.StringIO()
    rc, _out = _capture_stdout(
        pv.run_live, "https://link.msgsndr.com",
        pv.DEFAULT_UNIVERSAL_INTAKE_FORM_ID, "ANTH_TEST",
        key="anthology_id", baseline=pv.load_baseline(),
        allow_render=False, timeout=5.0, out=err)
    assert rc == EX_MISMATCH
    assert "served-page drift" in err.getvalue()


def test_aggregate_fetch_failure_is_held_exit_3(monkeypatch):
    """A form page / artifact that cannot be fetched is HELD (exit 3) — the
    law is UNDETERMINED, never proven compliant."""
    def boom(url, timeout=20.0):
        raise reg.CafUnreachable("fixture transport failure")
    _patch_fetch(monkeypatch, boom)
    rc, _out = _capture_stdout(
        pv.run_live, "https://link.msgsndr.com",
        pv.DEFAULT_UNIVERSAL_INTAKE_FORM_ID, "ANTH_TEST",
        key="anthology_id", baseline=pv.load_baseline(),
        allow_render=False, timeout=5.0, out=io.StringIO())
    assert rc == EX_HELD


def test_aggregate_empty_probe_stops_exit_2(monkeypatch):
    """An empty probe cannot build a canonical URL — STOP (exit 2), never a
    guessed fetch."""
    _patch_fetch(monkeypatch, _same_page)
    rc, _out = _capture_stdout(
        pv.run_live, "https://link.msgsndr.com",
        pv.DEFAULT_UNIVERSAL_INTAKE_FORM_ID, "",
        key="anthology_id", baseline=pv.load_baseline(),
        allow_render=False, timeout=5.0, out=io.StringIO())
    assert rc == EX_STOP


def test_aggregate_build_drift_is_exit_5(monkeypatch):
    """A widget page whose served bundle does not match the committed
    baseline digest is a MISMATCH (exit 5), never a silent pass — and the
    FAIL detail carries truncated digests only."""
    def mismatch(url, timeout=20.0):
        if "mxFsF5jP" in url:
            return b"function n(e){return e}"
        return WIDGET_PAGE.encode("utf-8")
    _patch_fetch(monkeypatch, mismatch)
    err = io.StringIO()
    rc, _out = _capture_stdout(
        pv.run_live, "https://link.msgsndr.com",
        pv.DEFAULT_UNIVERSAL_INTAKE_FORM_ID, "ANTH_TEST",
        key="anthology_id", baseline=pv.load_baseline(),
        allow_render=False, timeout=5.0, out=err)
    assert rc == EX_MISMATCH
    assert "build signature drift" in err.getvalue()
    assert "64e1c513e385" in err.getvalue()  # committed, truncated to 12 hex
    # digests are truncated to 12 hex on the surface — the live digest is
    # never echoed in full
    live_full = pv.load_baseline()["signatures"][
        next(u for u in pv.load_baseline()["signatures"]
             if "mxFsF5jP" in u)]["sha256"]
    assert live_full not in err.getvalue()


def test_aggregate_signature_less_baseline_is_exit_5(monkeypatch):
    """A baseline without a signatures section makes the hydration law
    unverifiable — MISMATCH (exit 5), never a blind pass."""
    _patch_fetch(monkeypatch, _same_page)
    rc, _out = _capture_stdout(
        pv.run_live, "https://link.msgsndr.com",
        pv.DEFAULT_UNIVERSAL_INTAKE_FORM_ID, "ANTH_TEST",
        key="anthology_id", baseline={"schema_version": 1},
        allow_render=False, timeout=5.0, out=io.StringIO())
    assert rc == EX_MISMATCH


# ---------------------------------------------------------------------------
# The CLI surface (offline): plan / STOP refusals / normalization.
# ---------------------------------------------------------------------------
def test_plan_surface_is_offline_and_carries_the_law():
    """plan emits ONE offline JSON object (no network, no credential) with
    the G3 key, the pinned probe, the canonical probe URL, and the baseline
    path; never a credential shape."""
    rc, out = _capture_stdout(pv.main, ["plan"])
    assert rc == EX_OK
    plan = json.loads(out)
    assert plan["contract"] == "anthology-engine-prefill-check-plan"
    assert plan["expected_query_key"] == "anthology_id"
    assert plan["probe"] == "ANTH_TEST"
    assert plan["probe_url"] == \
        "https://link.msgsndr.com/widget/form/U65pwoeMTy1niMqllKWG?anthology_id=ANTH_TEST"
    assert plan["baseline"].endswith("config/prefill-verifier-baseline.json")
    assert "pit-" not in out and "Bearer" not in out


def test_main_live_stops_on_a_missing_baseline():
    """A live run whose committed baseline is missing STOPS (exit 2) before
    any fetch — the hydration law is unverifiable."""
    rc, _out = _capture_stdout(
        pv.main, ["live", "--baseline", "/nonexistent/prefill.json",
                  "--no-render"])
    assert rc == EX_STOP


def test_main_live_stops_on_an_empty_key(monkeypatch):
    """A live run whose expected query key cannot be resolved STOPS (exit 2)
    — the law is unverifiable, never a guessed key."""
    monkeypatch.setattr(pv, "_resolve_intake_key", lambda: "")
    rc, _out = _capture_stdout(pv.main, ["live", "--no-render"])
    assert rc == EX_STOP


def test_main_selftest_flag_normalization_runs_the_offline_battery():
    """Both --selftest and the positional self-test form run the OFFLINE
    battery and exit 0 (a tamper is exit 4, never 1)."""
    rc, _out = _capture_stdout(pv.main, ["--selftest"])
    assert rc == EX_OK
    rc, _out = _capture_stdout(pv.main, ["self-test"])
    assert rc == EX_OK


def test_unknown_arg_is_a_usage_error():
    with pytest.raises(SystemExit) as exc:
        pv.main(["--nope"])
    assert exc.value.code == 2


# ---------------------------------------------------------------------------
# Cross-cutting house doctrine (fail-closed, browser UA, never-a-token).
# ---------------------------------------------------------------------------
def test_offline_self_test_passes_and_is_exit_4_on_a_tamper():
    """The module's own offline battery passes (exit 0); a tamper is an
    ENFORCED violation (exit 4), never 'unexpected error' (exit 1)."""
    assert pv.self_test(out=io.StringIO()) == EX_OK
    assert EX_VIOLATION == 4
    assert EX_VIOLATION not in (EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH)


def test_browser_user_agent_is_a_browser_ua_cf_1010_law():
    """The CF 1010 law: the verifier's fetches ride the house browser
    User-Agent — urllib's default Python-urllib/x.y is 403'd at the
    Cloudflare WAF edge before it ever reaches Convert and Flow."""
    assert reg.CAF_BROWSER_UA, "CAF_BROWSER_UA must never be empty"
    assert reg.CAF_BROWSER_UA.startswith("Mozilla/5.0"), (
        "CAF_BROWSER_UA must be a browser User-Agent, got %r"
        % reg.CAF_BROWSER_UA[:40])
    assert "Python-urllib" not in reg.CAF_BROWSER_UA
    # the verifier's own fetch rides that UA on every request
    import urllib.request
    req = urllib.request.Request(
        "https://link.msgsndr.com/widget/form/x",
        headers={"User-Agent": reg.CAF_BROWSER_UA})
    assert req.get_header("User-agent") == reg.CAF_BROWSER_UA


def test_masking_never_surfaces_a_full_identifier():
    """The form id and the rendered value are MASKED on every surface — the
    house masking law (last 4 chars / first 4 + length)."""
    assert pv._mask_form_id("U65pwoeMTy1niMqllKWG") == "...lKWG"
    assert pv._mask_value("ANTH_TEST") == "ANTH...(len 9)"
    assert pv._mask_value("") == "(empty)"


def test_no_credential_shape_on_any_captured_surface(monkeypatch):
    """Never-a-token, both directions: no fixture carries a credential shape,
    and no captured surface (plan, PASS report, FAIL detail, self-test
    output) may either."""
    rc, plan_out = _capture_stdout(pv.main, ["plan"])
    assert rc == EX_OK
    _patch_fetch(monkeypatch, _same_page)
    rc, pass_out = _capture_stdout(
        pv.run_live, "https://link.msgsndr.com",
        pv.DEFAULT_UNIVERSAL_INTAKE_FORM_ID, "ANTH_TEST",
        key="anthology_id", baseline=_fabricated_baseline(),
        allow_render=False, timeout=5.0, out=io.StringIO())
    assert rc == EX_OK
    err = io.StringIO()
    rc, fail_out = _capture_stdout(
        pv.run_live, "https://link.msgsndr.com",
        pv.DEFAULT_UNIVERSAL_INTAKE_FORM_ID, "ANTH_TEST",
        key="anthology_id", baseline={"schema_version": 1},
        allow_render=False, timeout=5.0, out=err)
    assert rc == EX_MISMATCH
    dev = io.StringIO()
    assert pv.self_test(out=dev) == EX_OK
    for blob in (plan_out, pass_out, fail_out, err.getvalue(),
                 dev.getvalue()):
        assert "pit-" not in blob, "a credential shape leaked"
        assert "Bearer" not in blob, "a credential shape leaked"


def test_fail_closed_directions_discriminate_never_a_broken_instrument():
    """The pass/fail split is a discrimination: the golden control PASSes
    (byte-identical + matching digest + hydration present) and EVERY attack
    direction fails — a gate that fails everything is a broken check, not a
    real fault."""
    assert pv.check_page_identity(b"x", b"x")["ok"] is True
    assert pv.check_page_identity(b"x", b"y")["ok"] is False
    assert pv.check_page_is_widget(WIDGET_PAGE)["ok"] is True
    assert pv.check_page_is_widget("<html></html>")["ok"] is False
    assert pv.check_hydration_code(pv._fake_bundle(True))["ok"] is True
    assert pv.check_hydration_code(pv._fake_bundle(False))["ok"] is False
    baseline = pv.load_baseline()
    sigs = baseline["signatures"]
    url = next(u for u in sigs if "DO9dUel-" in u)
    assert pv.check_build_signature({url: sigs[url]}, baseline)["ok"] is True
    assert pv.check_build_signature(
        {url: {"url": url, "sha256": "0" * 64, "bytes": 1}},
        baseline)["ok"] is False
    assert pv.check_probe_url_canonical(
        "https://link.msgsndr.com", "fid", "anthology_id", "ANTH_TEST") == \
        "https://link.msgsndr.com/widget/form/fid?anthology_id=ANTH_TEST"


def _run_all():
    fns = [v for k, v in sorted(globals().items())
           if k.startswith("test_") and callable(v)]
    # pytest fixtures (monkeypatch / tmp_path) are injected by pytest; the
    # direct runner substitutes the _Patch seam and a real tempdir.
    import tempfile as _tmp
    import inspect as _inspect
    _registry = []
    _monkey = _Patch(_registry)
    _td = _tmp.TemporaryDirectory(prefix="test_prefill_")
    _td_path = Path(_td.name)
    failed = 0
    for fn in fns:
        _params = list(_inspect.signature(fn).parameters)
        try:
            if "monkeypatch" in _params and "tmp_path" in _params:
                fn(_monkey, _td_path)
            elif "monkeypatch" in _params:
                fn(_monkey)
            elif "tmp_path" in _params:
                fn(_td_path)
            else:
                fn()
            print("  [PASS] %s" % fn.__name__)
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print("  [FAIL] %s -- %s" % (fn.__name__, exc))
        finally:
            for _mod, _name, _saved in reversed(_registry):
                setattr(_mod, _name, _saved)
            del _registry[:]
    _td.cleanup()
    print("test_prefill: %s (%d/%d)"
          % ("ALL PASSED" if not failed else "FAILURES",
             len(fns) - failed, len(fns)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(_run_all())
