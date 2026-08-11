#!/usr/bin/env python3
"""test_prefill.py -- unit tests for prefill_verifier.py, the U08/U09
value-side gate (Skill 59, anthology engine). The module guards the ONE
surface every book's journey starts at: the live universal author-intake form
whose hidden anthology_id AND stage fields must be pre-filled by the minted
intake link's TWO query params
    <forms_base>/widget/form/<form_id>?anthology_id=<minted>&stage=<stage>
(anthology_book.build_intake_link; the universal hidden-field contract
contact_id / anthology_id / stage from
config/anthology-snapshot-contract.json forms.universal_hidden_fields).

THE LAW UNDER TEST (mirrored from the module header):

  * FAIL-CLOSED -- a form page that cannot be fetched or decoded is HELD
    (exit 3), never proven compliant; a page that differs between the bare
    URL and the two-param probe URL is a REFUSAL (exit 5) -- the widget owns
    the pre-fill, never the origin, and a page that bakes the probe into the
    served bytes would make the real widget double-apply; a page that does
    not reference the widget build is a REFUSAL; a build artifact that does
    not match its committed baseline digest (or has NO committed signature)
    is a MISMATCH; a bundle without the pinned hydration code is a MISMATCH;
    an out-of-vocabulary stage token is a STOP (exit 2) -- a check that
    cannot see its law never fabricates a pass.
  * --execute REQUIRED for the live verify (u08_u09 package doctrine): the
    live read is a PUBLIC GET, never a write, but a background or accidental
    invocation must never even probe the live surface. WITHOUT --execute the
    CLI REFUSES (exit 2, AF-AE-PREFILL-EXECUTE) BEFORE any network read.
  * NEVER a token printed -- this module holds NO credential surface at all;
    the probe values are deliberately synthetic fixtures (ANTH_TEST /
    s1_avatar), never the real fleet pin, and the report carries digests and
    masked markers only.
  * Browser UA (CF 1010) -- every fetch rides reg.CAF_BROWSER_UA
    (Mozilla/5.0 ... Chrome/120.0.0.0), the house pattern that clears the
    Cloudflare edge fronting stcdn.leadconnectorhq.com; urllib's default
    Python-urllib UA is 1010'd at the edge.
  * The single-implementation doctrine -- the expected anthology_id key is
    mirrored from anthology_book.INTAKE_QUERY_KEY and the stage key + the
    stage-token vocabulary from the committed contract / anthology_state
    STAGE_CURSORS; a drift between the minted link and this gate is pinned
    to fail here, before it ships.

HERMETIC BY DESIGN -- OFFLINE: no network, no browser, no secrets. The pure
checks are exercised with synthetic fixtures; the --execute gate is proven
through the CLI with a stubbed network layer (monkeypatched fetch) so the
refusal is provable without touching the live surface; the module's own
offline self-test battery runs as a process (the house self-test convention
-- a tamper NEVER masquerades as exit 1). The baseline/contract files are
read ONLY where the check under test reads them (they are committed, hashed
source of truth), and the LIVE (subprocess+CDP) path is deliberately never
exercised here -- that is the module's own self-test + live domain.

Run: python3 -m pytest 59-anthology-engine/scripts/u08_u09_modules/test_prefill.py -q
 or: python3 59-anthology-engine/scripts/u08_u09_modules/test_prefill.py
"""
import gzip
import json
import os
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent.parent
SCRIPTS = SKILL_DIR / "scripts"
U08 = SCRIPTS / "u08_u09_modules"

for _p in (SCRIPTS, U08):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import anthology_registry as reg  # noqa: E402
import prefill_verifier as pv  # noqa: E402


# ---------------------------------------------------------------------------
# The mirror pins: the U08 two-hidden-field law, fixed to the one source of
# truth for each constant (the same mirrors the module's own offline
# self-test pins -- a drift trips THIS battery first).
# ---------------------------------------------------------------------------
def test_intake_query_key_mirror_is_the_g3_contract():
    """The anthology_id key must mirror anthology_book.INTAKE_QUERY_KEY
    byte-exact (the single-implementation doctrine: the SAME constant
    build_intake_link mints links with)."""
    import anthology_book  # noqa: F401  (sibling bootstrap already ran)
    assert pv._resolve_intake_key() == "anthology_id"
    assert anthology_book.INTAKE_QUERY_KEY == "anthology_id"
    assert pv._resolve_intake_key() == anthology_book.INTAKE_QUERY_KEY, (
        "prefill_verifier's anthology_id key drifted from the minted-link "
        "constant")


def test_stage_query_key_mirror_is_the_contract():
    """The stage key must resolve from the committed universal hidden-field
    contract (config/anthology-snapshot-contract.json
    forms.universal_hidden_fields) -- and it must be 'stage'."""
    assert pv._resolve_stage_query_key() == "stage"


def test_stage_token_vocabulary_mirrors_anthology_state():
    """The stage-token vocabulary must resolve from
    anthology_state.STAGE_CURSORS and carry the probe token s1_avatar."""
    import anthology_state  # noqa: F401  (sibling bootstrap already ran)
    vocab = pv._resolve_stage_vocabulary()
    assert isinstance(vocab, tuple) and vocab, (
        "the stage-token vocabulary must resolve to a non-empty tuple")
    assert "s1_avatar" in vocab
    # the vocabulary is the engine's stage-cursor law — mirror it exactly
    import anthology_state  # noqa: F401
    assert tuple(vocab) == tuple(anthology_state.STAGE_CURSORS)


def test_fixture_constants_pinned():
    """The committed fixtures must stay pinned (a caller-supplied probe value
    could otherwise influence a run)."""
    assert pv.DEFAULT_PROBE_VALUE == "ANTH_TEST"
    assert pv.DEFAULT_STAGE_TOKEN == "s1_avatar"
    assert pv.WIDGET_FORM_PATH == "/widget/form"


def test_browser_ua_is_the_cf1010_law():
    """Every fetch must ride the house browser User-Agent (CF 1010 law):
    Mozilla-prefixed and Chrome-complete, NEVER urllib's Python-urllib."""
    ua = reg.CAF_BROWSER_UA
    assert pv.fetch_http.__doc__ and "CAF_BROWSER_UA" in pv.fetch_http.__doc__
    assert ua.startswith("Mozilla/5.0"), (
        "CAF_BROWSER_UA must be a browser User-Agent (CF 1010)")
    assert "Chrome/" in ua, "CAF_BROWSER_UA must carry a Chrome segment"
    assert "Python-urllib" not in ua, (
        "urllib's default UA is 1010'd at the Cloudflare edge")


def test_fetch_http_rides_the_browser_ua(monkeypatch):
    """fetch_http must attach reg.CAF_BROWSER_UA (and gzip Accept-Encoding)
    to the request it opens -- proven by intercepting the request, never by
    a live fetch."""
    captured = {}

    def _hdr(req, name):
        # urllib Request stores header keys capitalized ("User-agent") —
        # read case-insensitively
        for k, v in req.headers.items():
            if k.lower() == name.lower():
                return v
        return None

    class _Resp:
        status = 200
        headers = {}

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self, limit=None):
            return b"<html>page</html>"

    def _fake_urlopen(req, timeout=None):
        captured["ua"] = _hdr(req, "User-Agent")
        captured["ae"] = _hdr(req, "Accept-Encoding")
        captured["url"] = req.full_url
        return _Resp()

    monkeypatch.setattr(reg.urllib.request, "urlopen", _fake_urlopen)
    body = pv.fetch_http("https://link.msgsndr.com/widget/form/U65pwoeMTy1niMqllKWG")
    assert body == b"<html>page</html>"
    assert captured["ua"] == reg.CAF_BROWSER_UA, (
        "the request must carry the house browser UA (CF 1010), got %r"
        % captured["ua"])
    assert captured["ae"] == "gzip"


def test_fetch_http_holds_http_error_as_unreachable(monkeypatch):
    """An HTTP error (edge/WAF/origin refusal) must surface as
    reg.CafUnreachable -- the HELD family (exit 3), never a pass and never
    a bare HTTPError leak."""
    def _fake_urlopen(req, timeout=None):
        raise reg.urllib.error.HTTPError(
            req.full_url, 403, "Forbidden", {}, None)

    monkeypatch.setattr(reg.urllib.request, "urlopen", _fake_urlopen)
    try:
        pv.fetch_http("https://stcdn.leadconnectorhq.com/_preview/x.js")
    except reg.CafUnreachable as exc:
        assert "403" in str(exc)
    else:  # pragma: no cover -- a fail-open fetch is a defect
        raise AssertionError("an HTTP 403 must HELD, not pass")


def test_fetch_http_holds_transport_failure_as_unreachable(monkeypatch):
    """A transport failure must surface as reg.CafUnreachable (HELD), never
    a bare URLError/OSError leak."""
    def _fake_urlopen(req, timeout=None):
        raise reg.urllib.error.URLError("connection refused")

    monkeypatch.setattr(reg.urllib.request, "urlopen", _fake_urlopen)
    try:
        pv.fetch_http("https://link.msgsndr.com/widget/form/x")
    except reg.CafUnreachable:
        pass
    else:  # pragma: no cover
        raise AssertionError("a transport failure must HELD, not pass")


def test_fetch_http_refuses_runaway_response(monkeypatch):
    """A body longer than MAX_READ_BYTES must be HELD (never slurped)."""
    class _Resp:
        status = 200
        headers = {}

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self, limit=None):
            return b"x" * (pv.MAX_READ_BYTES + 1)

    def _fake_urlopen(req, timeout=None):
        return _Resp()

    monkeypatch.setattr(reg.urllib.request, "urlopen", _fake_urlopen)
    try:
        pv.fetch_http("https://stcdn.leadconnectorhq.com/_preview/big.js")
    except reg.CafUnreachable as exc:
        assert "runaway" in str(exc).lower()
    else:  # pragma: no cover
        raise AssertionError("a runaway response must HELD, not pass")


# ---------------------------------------------------------------------------
# The pure fail-closed checks (deterministic, value-free, offline).
# ---------------------------------------------------------------------------
def test_check_page_identity_byte_identical_passes():
    """The served-surface identity law: the form page must be byte-identical
    with and without the probe params."""
    page = b"<html><body>same page</body></html>"
    report = pv.check_page_identity(page, page)
    assert report["ok"] is True
    assert report["bare_sha256"] == report["probed_sha256"]
    assert report["bytes"] == len(page)


def test_check_page_identity_any_byte_drift_fails():
    """ANY byte difference between the bare and the probed page is a
    mismatch (a tampered/caching page -- the widget would double-apply)."""
    report = pv.check_page_identity(b"<html>A</html>", b"<html>B</html>")
    assert report["ok"] is False
    assert "drift" in (report["detail"] or "")


def test_check_page_identity_probe_baked_into_served_bytes_fails():
    """A page that bakes the probe value into its served bytes must FAIL --
    the pre-fill is the widget's job, never the origin's."""
    baked = (b"<html><input value=\"" + pv.DEFAULT_PROBE_VALUE.encode()
             + b"\"></html>")
    report = pv.check_page_identity(b"<html><input></html>", baked)
    assert report["ok"] is False


def test_check_page_is_widget_references_build():
    """A page referencing the _preview module bundle IS the hosted-form
    surface this gate exists for."""
    page = ('<html><head><script type="module" src="https://'
            'stcdn.leadconnectorhq.com/_preview/mxFsF5jP.js" '
            'crossorigin></script></head><body></body></html>')
    report = pv.check_page_is_widget(page)
    assert report["ok"] is True
    assert any("mxFsF5jP.js" in u for u in report["refs"])


def test_check_page_is_widget_accepts_build_meta_only():
    """The build-meta JSON URL (derived from the page's __NUXT__ config) is
    alone a sufficient widget reference -- the page must not be refused just
    because it preloads no module script."""
    page = ('<html><head><script>window.__NUXT__={app:{baseURL:"",'
            'buildId:"61af4923-e329-4e77-94ba-94a97885eec7",'
            'buildAssetsDir:"/_nuxt/",cdnURL:"https://stcdn.leadconnectorhq.com/_preview"}}'
            '</script></head><body></body></html>')
    report = pv.check_page_is_widget(page)
    assert report["ok"] is True, (
        "a page carrying only the build-meta reference must be a widget "
        "surface, got %r" % report["refs"])
    assert any("builds/meta/" in u for u in report["refs"]), (
        "the build-meta URL must be among the refs")


def test_check_page_is_widget_refuses_plain_page():
    """A page with NO widget build reference is NOT the hosted-form surface
    -- REFUSED, never a pass."""
    report = pv.check_page_is_widget("<html><body>hello</body></html>")
    assert report["ok"] is False
    assert report["refs"] == []


def test_check_probe_url_canonical_two_params():
    """The canonical TWO-param probe URL -- the U08 law: anthology_id AND
    stage, both URL-quoted, from the same constants build_intake_link mints
    with."""
    url = pv.check_probe_url_canonical(
        "https://link.msgsndr.com", "U65pwoeMTy1niMqllKWG",
        "anthology_id", "ANTH_TEST", "stage", "s1_avatar")
    assert url == ("https://link.msgsndr.com/widget/form/"
                   "U65pwoeMTy1niMqllKWG?anthology_id=ANTH_TEST"
                   "&stage=s1_avatar"), url


def test_check_probe_url_canonical_quotes_values():
    """Probe values must be URL-quoted (a form id or probe carrying
    characters like '?' or '&' must not corrupt the URL)."""
    url = pv.check_probe_url_canonical(
        "https://link.msgsndr.com/", "a?b&c",
        "anthology_id", "ANTH_TEST", "stage", "s1_avatar")
    assert "?anthology_id=ANTH_TEST&stage=s1_avatar" in url
    assert "a%3Fb%26c" in url, "the form id must be URL-quoted"


def test_check_probe_url_canonical_refuses_empty_component():
    """An empty key/probe/stage component is a STOP refusal -- the law is
    unverifiable, never a guessed URL."""
    for kw in ({"probe": ""}, {"stage_token": ""},
               {"key": ""}, {"stage_key": ""}):
        args = {"base": "https://link.msgsndr.com",
                "form_id": "U65pwoeMTy1niMqllKWG",
                "key": "anthology_id", "probe": "ANTH_TEST",
                "stage_key": "stage", "stage_token": "s1_avatar"}
        args.update(kw)
        try:
            pv.check_probe_url_canonical(**args)
            raise AssertionError("an empty query component must refuse "
                                 "(got %r)" % kw)
        except pv._PrefillPageError:
            pass


def test_check_build_signature_matches_committed_baseline():
    """Every fetched artifact must match its committed baseline digest
    byte-exact, and the baseline must carry a signature for every fetched
    artifact."""
    baseline = pv.load_baseline()
    fetched = {}
    for url, record in baseline.get("signatures", {}).items():
        fetched[url] = {"url": url, "sha256": record["sha256"],
                        "bytes": record["bytes"]}
    report = pv.check_build_signature(fetched, baseline)
    assert report["ok"] is True, (
        "the committed baseline must self-match, got %r" % report["detail"])
    assert set(report["checked"]) == set(fetched)


def test_check_build_signature_digest_drift_fails():
    """A tampered artifact digest is a MISMATCH, never a blind pass."""
    baseline = pv.load_baseline()
    golden = baseline.get("signatures", {})
    tampered = {url: {"url": url, "sha256": "0" * 64, "bytes": 1}
                for url in golden}
    report = pv.check_build_signature(tampered, baseline)
    assert report["ok"] is False
    assert "drift" in (report["detail"] or "")


def test_check_build_signature_unsigned_artifact_fails():
    """A fetched artifact with NO committed signature is unverifiable ->
    mismatch."""
    report = pv.check_build_signature(
        {"https://stcdn.leadconnectorhq.com/_preview/nonexistent.js":
         {"url": "https://stcdn.leadconnectorhq.com/_preview/nonexistent.js",
          "sha256": "1" * 64, "bytes": 1}},
        {"schema_version": 1, "signatures": {}})
    assert report["ok"] is False
    assert "no committed signature" in (report["detail"] or "")


def test_check_build_signature_missing_section_fails():
    """A baseline with NO signatures section is a mismatch (law
    unverifiable), never a pass."""
    report = pv.check_build_signature(
        {"a": {"sha256": "1" * 64}}, {"schema_version": 1})
    assert report["ok"] is False


def test_check_hydration_code_markers_pass():
    """The pinned hydration-code text (hiddenFieldQueryKey -> urlParams ->
    field value) must be present in the fetched widget code."""
    blob = "function Ct(e,r){hiddenFieldQueryKey in c&&(I.value[O.tag]=e)}"
    report = pv.check_hydration_code(blob)
    assert report["ok"] is True


def test_check_hydration_code_absent_markers_fail():
    """A bundle whose hydration code is absent or drifted is a MISMATCH,
    never a silent pass."""
    assert pv.check_hydration_code("function n(e){return e}")["ok"] is False
    assert pv.check_hydration_code("")["ok"] is False


def test_check_stage_token_vocabulary():
    """The probe stage token MUST be a member of the committed stage-cursor
    vocabulary; an out-of-vocabulary token is refused."""
    vocab = pv._resolve_stage_vocabulary()
    report = pv.check_stage_token_vocabulary("s1_avatar", vocab)
    assert report["ok"] is True
    report = pv.check_stage_token_vocabulary("not_a_stage", vocab)
    assert report["ok"] is False
    assert "NOT in the committed stage-cursor vocabulary" in (
        report["detail"] or "")


# ---------------------------------------------------------------------------
# The masking law: no identifier surface ever prints a full value.
# ---------------------------------------------------------------------------
def test_mask_form_id_keeps_last_four_only():
    """A form id surface is masked to the last 4 characters, never full."""
    assert pv._mask_form_id("U65pwoeMTy1niMqllKWG") == "...lKWG"
    assert pv._mask_form_id("x") == "...(short)"
    assert pv._mask_form_id("") == "...(short)"


def test_mask_value_keeps_prefix_and_length_only():
    """A rendered value surface carries a 4-char prefix + length, never the
    full value (a deliberate probe fixture, but the house masks anyway)."""
    assert pv._mask_value("ANTH_TEST") == "ANTH...(len 9)"
    assert pv._mask_value("") == "(empty)"


# ---------------------------------------------------------------------------
# The decode/digest helpers (deterministic, offline).
# ---------------------------------------------------------------------------
def test_decompress_handles_plain_and_gzip():
    assert pv._decompress(b"<html>page</html>") == "<html>page</html>"
    compressed = gzip.compress(b"<html>page</html>")
    assert pv._decompress(compressed) == "<html>page</html>"


def test_decompress_refuses_undecodable_bytes():
    """A 2xx body that cannot be decoded faithfully must raise (-> HELD) --
    a tampered page is the attack this gate exists for."""
    try:
        pv._decompress(b"\xff\xfe\xfa")
    except (OSError, ValueError):
        pass
    else:  # pragma: no cover
        raise AssertionError("undecodable bytes must raise, never fabricate")


def test_digest_bytes_is_sha256_hex():
    assert pv._digest_bytes(b"") == (
        "e3b0c44298fc1c149afbf4c8996fb924"
        "27ae41e4649b934ca495991b7852b855")


# ---------------------------------------------------------------------------
# The build-signature record + chunk-ref parser.
# ---------------------------------------------------------------------------
def test_build_signature_record():
    data = b"function x(){}"
    sig = pv._build_signature("https://stcdn.leadconnectorhq.com/_preview/x.js",
                              data)
    assert sig["url"] == "https://stcdn.leadconnectorhq.com/_preview/x.js"
    assert sig["sha256"] == pv._digest_bytes(data)
    assert sig["bytes"] == len(data)


def test_parse_bundle_refs_dedupes_and_orders():
    """The dynamic-chunk refs must be deduplicated, ordered by first mention,
    and absolute (the hydration code ships in a dynamic chunk)."""
    refs = pv._parse_bundle_refs(
        'import("./chunk1.js");import("https://stcdn.leadconnectorhq.com/'
        '_preview/DO9dUel-.js");import("https://stcdn.leadconnectorhq.com/'
        '_preview/DO9dUel-.js")')
    assert refs == ["https://stcdn.leadconnectorhq.com/_preview/DO9dUel-.js"]
    assert pv._parse_bundle_refs("no imports here") == []


# ---------------------------------------------------------------------------
# The optional rendered observation -- fail-closed and value-free.
# ---------------------------------------------------------------------------
def test_verify_render_optional_skips_without_runtime(monkeypatch):
    """Absent headless runtime -> SKIPPED as undetermined, never fabricated
    (and never a FAIL)."""
    monkeypatch.setattr(pv, "find_headless_chromium", lambda: "")
    status, row = pv.verify_render_optional(
        "https://link.msgsndr.com/widget/form/x?anthology_id=a&stage=s",
        "ANTH_TEST", "s1_avatar", allow_render=True, out=None)
    assert status == "SKIP"
    assert row["status"] == "SKIP"
    assert "NOT AVAILABLE" in row["detail"]


def test_verify_render_optional_skips_on_no_render(monkeypatch):
    """--no-render -> the rendered pre-fill is not observed (served-surface
    checks only)."""
    monkeypatch.setattr(pv, "find_headless_chromium",
                        lambda: "/usr/bin/fake-chromium")
    status, row = pv.verify_render_optional(
        "https://link.msgsndr.com/widget/form/x", "ANTH_TEST", "s1_avatar",
        allow_render=False, out=None)
    assert status == "SKIP"
    assert "--no-render" in row["detail"]


def test_verify_render_optional_holds_failed_render(monkeypatch):
    """A render that cannot complete is HELD (exit 3) -- the rendered law is
    UNDETERMINED, never proven compliant and never a pass."""
    monkeypatch.setattr(pv, "find_headless_chromium",
                        lambda: "/usr/bin/fake-chromium")

    def _boom(url):
        raise reg.CafUnreachable("the headless render exposed no page target")

    monkeypatch.setattr(pv, "_render_probe_url", _boom)
    status, row = pv.verify_render_optional(
        "https://link.msgsndr.com/widget/form/x", "ANTH_TEST", "s1_avatar",
        allow_render=True, out=None)
    assert status == "HELD"
    assert row["status"] == "HELD"


def test_verify_render_optional_fails_wrong_value(monkeypatch):
    """A rendered NON-exact value for EITHER hidden field is a MISMATCH
    (exit 5), never a pass."""
    monkeypatch.setattr(pv, "find_headless_chromium",
                        lambda: "/usr/bin/fake-chromium")
    monkeypatch.setattr(
        pv, "_render_probe_url",
        lambda url: {"anthology_id": "SOMETHING_ELSE", "stage": "s1_avatar"})
    status, row = pv.verify_render_optional(
        "https://link.msgsndr.com/widget/form/x", "ANTH_TEST", "s1_avatar",
        allow_render=True, out=None)
    assert status == "FAIL"
    assert "AF-AE-PREFILL-RENDER" in row["detail"]
    # the report surface carries the MASKED marker only -- never the full
    # rendered value
    assert "SOMETHING_ELSE" not in row["detail"]
    assert "SOME...(len" in row["detail"]


def test_verify_render_optional_fails_wrong_stage(monkeypatch):
    """A stage field rendered with a non-exact token is a MISMATCH (U08 law:
    BOTH hidden fields must carry EXACTLY their probe values)."""
    monkeypatch.setattr(pv, "find_headless_chromium",
                        lambda: "/usr/bin/fake-chromium")
    monkeypatch.setattr(
        pv, "_render_probe_url",
        lambda url: {"anthology_id": "ANTH_TEST", "stage": "s9_deliver"})
    status, row = pv.verify_render_optional(
        "https://link.msgsndr.com/widget/form/x", "ANTH_TEST", "s1_avatar",
        allow_render=True, out=None)
    assert status == "FAIL"
    assert "stage" in row["detail"]


def test_verify_render_optional_passes_exact_values(monkeypatch):
    """Both hidden fields carrying EXACTLY their probe values is a PASS."""
    monkeypatch.setattr(pv, "find_headless_chromium",
                        lambda: "/usr/bin/fake-chromium")
    monkeypatch.setattr(
        pv, "_render_probe_url",
        lambda url: {"anthology_id": "ANTH_TEST", "stage": "s1_avatar"})
    status, row = pv.verify_render_optional(
        "https://link.msgsndr.com/widget/form/x", "ANTH_TEST", "s1_avatar",
        allow_render=True, out=None)
    assert status == "PASS"
    assert row["status"] == "PASS"


# ---------------------------------------------------------------------------
# The fail-closed baseline loader (STOP family: exit 2).
# ---------------------------------------------------------------------------
def test_load_baseline_committed_file_is_object(tmp_path):
    """The committed baseline must load and carry schema_version -- the
    hashed source of truth for the hydration law."""
    baseline = pv.load_baseline()
    assert isinstance(baseline, dict)
    assert baseline.get("schema_version") == 1
    assert isinstance(baseline.get("signatures"), dict)


def test_load_baseline_missing_file_is_stop(tmp_path):
    try:
        pv.load_baseline(tmp_path / "nope.json")
        raise AssertionError("a missing baseline must refuse")
    except pv._BaselineError as exc:
        assert "UNREADABLE" in str(exc)


def test_load_baseline_malformed_file_is_stop(tmp_path):
    (tmp_path / "bad.json").write_text("{not json", encoding="utf-8")
    try:
        pv.load_baseline(tmp_path / "bad.json")
        raise AssertionError("a malformed baseline must refuse")
    except pv._BaselineError as exc:
        assert "MALFORMED" in str(exc)


def test_load_baseline_non_object_is_stop(tmp_path):
    (tmp_path / "arr.json").write_text("[1,2]", encoding="utf-8")
    try:
        pv.load_baseline(tmp_path / "arr.json")
        raise AssertionError("a non-object baseline must refuse")
    except pv._BaselineError:
        pass


# ---------------------------------------------------------------------------
# The --execute gate: the live verify REFUSES (exit 2) without --execute,
# and the refusal happens BEFORE any network read (provable offline with a
# stubbed fetch that would raise if touched).
# ---------------------------------------------------------------------------
def _run_cli(args, monkeypatch):
    """Drive the CLI with a fetch that raises if ANY network read is
    attempted. Returns (exit_code, touched_urls)."""
    calls = []

    def _forbidden_fetch(url, timeout=20.0):
        calls.append(url)
        raise AssertionError(
            "live verify must refuse BEFORE any network read (touched %s)"
            % url)

    monkeypatch.setattr(pv, "fetch_http", _forbidden_fetch)
    old_argv = sys.argv
    sys.argv = ["prefill_verifier.py"] + args
    try:
        code = pv.main()
    finally:
        sys.argv = old_argv
    return code, calls


def test_live_verify_refuses_without_execute(monkeypatch):
    """AF-AE-PREFILL-EXECUTE: `live` without --execute is a STOP (exit 2),
    and it must refuse BEFORE any fetch -- a background or accidental
    invocation never even probes the live surface."""
    code, calls = _run_cli(["live"], monkeypatch)
    assert code == reg.EX_STOP
    assert calls == [], (
        "without --execute the live verify must not touch the network")


def test_plan_runs_offline_and_reports_the_law(monkeypatch):
    """`plan` is OFFLINE (no --execute, no network, no credentials) and
    reports exactly what the live verify WOULD check."""
    code, calls = _run_cli(["plan"], monkeypatch)
    assert code == reg.EX_OK
    assert calls == []


def test_main_holds_fetch_failure_as_exit_3(monkeypatch):
    """A fetch failure during the live verify is HELD (exit 3) -- the law
    is UNDETERMINED, never a compliance verdict."""
    def _held(url, timeout=20.0):
        raise reg.CafUnreachable("HTTP 403 on %s (held)" % url)

    monkeypatch.setattr(pv, "fetch_http", _held)
    old_argv = sys.argv
    sys.argv = ["prefill_verifier.py", "live", "--execute"]
    try:
        code = pv.main()
    finally:
        sys.argv = old_argv
    assert code == reg.EX_HELD


# ---------------------------------------------------------------------------
# The module's own offline self-test battery (the house self-test
# convention: run as a process so a tamper never masquerades as exit 1).
# ---------------------------------------------------------------------------
def test_module_self_test_battery_passes():
    """The module's own offline golden/attack battery must pass: golden
    states pass, every attack fixture FAILS, and the U08 two-hidden-field
    law stays pinned to the committed constants."""
    proc = subprocess.run(
        [sys.executable, str(U08 / "prefill_verifier.py"), "self-test"],
        capture_output=True, text=True, timeout=120)
    assert proc.returncode == reg.EX_OK, (
        "prefill_verifier self-test FAILED (exit %d):\n%s\n%s"
        % (proc.returncode, proc.stdout[-2000:], proc.stderr[-2000:]))


def test_self_test_is_offline():
    """The self-test must not touch the network -- an EMPTY environment and
    a stubbed urlopen that raises must still pass (it is pure)."""
    env = {k: v for k, v in os.environ.items()
           if k in ("PATH", "SYSTEMROOT", "HOME", "PYTHONPATH")}
    proc = subprocess.run(
        [sys.executable, str(U08 / "prefill_verifier.py"), "self-test"],
        capture_output=True, text=True, timeout=120, env=env)
    assert proc.returncode == reg.EX_OK, (
        "self-test must pass with an empty environment (exit %d):\n%s\n%s"
        % (proc.returncode, proc.stdout[-2000:], proc.stderr[-2000:]))


# ---------------------------------------------------------------------------
# Never-print: no credential-shaped string on any surface.
# ---------------------------------------------------------------------------
def test_never_print_credential_shaped_strings(monkeypatch):
    """No report/plan surface may ever carry a credential-shaped string
    (pit- tokens, Bearer), and the baseline must carry none either."""
    baseline = pv.load_baseline()
    blob = json.dumps(baseline, sort_keys=True)
    for token in ("pit-", "Bearer "):
        assert token not in blob, (
            "the committed baseline must carry no %r token" % token)

    code, _ = _run_cli(["plan"], monkeypatch)
    assert code == reg.EX_OK
