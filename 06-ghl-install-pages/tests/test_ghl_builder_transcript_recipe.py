"""MOCK-only unit tests — the transcript BUILD-RECIPE items added to
``ghl_builder.py`` (Skill 06, source: references/ghl-build-spec-from-transcript.md).

This run owns the authoritative end-state every build must reach (NOT the harden
run's selector-priors / render_check / probes). These tests cover:

  * ZHC provenance prefix — EMITTED uppercase 'ZHC ' (transcript ~03:28), match
    stays case-INSENSITIVE (no double-prefix), multi-step 'ZHC part <N>' naming
    (transcript step 20);
  * the two-saves invariant (save CODE then save PAGE, transcript steps 17->18);
  * the SEO/AI-search Content panel end-state (transcript §2) — seoMeta build +
    every HALT gate (length caps, researched-keywords floor, founder-as-author,
    canonical format, explicit language);
  * the founder-name P0 pre-flight gate (author := founder, never brand/blank);
  * wiring SEO into emit_rest_save_plan (ordered seo_apply step; pristine
    baseline preserved; autosave carries the seoMeta);
  * the gates.json Show-settings ALT-route prior (distinct top-level entry that
    does NOT touch the 2-captured/26-runtime gate counts);
  * the CLI surface (zhc --order, seo-check, two-saves).

MOCK-ONLY: no live GoHighLevel, no network, no agent-browser against real GHL.
No real client/operator names, ids, emails, or location-ids appear.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

_TOOLS_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "tools"))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

import pytest

import ghl_builder as b

FIXTURE_LOC = "FIXTURE0LOCATION0000"  # generic 20-char fixture id (NOT real)


# ── ZHC prefix casing + multi-step numbering ──────────────────────────────────

class TestZhcPrefix:
    def test_emits_uppercase_prefix(self):
        # The transcript states 'ZHC' (uppercase); the old code emitted lowercase.
        assert b.ensure_zhc_prefix("test") == "ZHC test"
        assert b.ensure_zhc_prefix("Home Page") == "ZHC Home Page"

    def test_empty_name_is_zhc_untitled(self):
        assert b.ensure_zhc_prefix("") == "ZHC untitled"
        assert b.ensure_zhc_prefix("   ") == "ZHC untitled"

    @pytest.mark.parametrize("already", ["ZHC test", "zhc test", "Zhc Home", "  zhc x"])
    def test_match_is_case_insensitive_no_double_prefix(self, already):
        # An already-prefixed name (any casing) is returned untouched (stripped).
        out = b.ensure_zhc_prefix(already)
        assert out == already.strip()
        assert not out.lower().startswith("zhc zhc")

    def test_order_auto_names_multi_step_part_n(self):
        # transcript step 20: unnamed multi-step steps -> 'ZHC part <order>'.
        assert b.ensure_zhc_prefix("", 2) == "ZHC part 2"
        assert b.ensure_zhc_prefix(None, 5) == "ZHC part 5"

    def test_order_ignored_when_name_present(self):
        assert b.ensure_zhc_prefix("Checkout", 3) == "ZHC Checkout"

    def test_zhc_step_name_wrapper(self):
        assert b.zhc_step_name(None, 4) == "ZHC part 4"
        assert b.zhc_step_name("About", 1) == "ZHC About"
        assert b.zhc_step_name("zhc Pricing", 2) == "zhc Pricing"


class TestBuildManifestStepNaming:
    def _pages(self, *names):
        # iframe mode skips the payload-file check (pure, no disk IO).
        return [{"name": n, "mode": "iframe", "iframe_src": "https://e.com"}
                for n in names]

    def test_unnamed_steps_get_zhc_part_numbering(self):
        pages = [{"mode": "iframe", "iframe_src": "https://e.com"},
                 {"mode": "iframe", "iframe_src": "https://e.com"}]
        m = b.build_manifest("My Funnel", "funnel", pages)
        assert m["funnel_name"] == "ZHC My Funnel"
        assert [p["name"] for p in m["pages"]] == ["ZHC part 1", "ZHC part 2"]

    def test_named_steps_are_zhc_prefixed(self):
        m = b.build_manifest("F", "website", self._pages("Home", "zhc About"))
        assert [p["name"] for p in m["pages"]] == ["ZHC Home", "zhc About"]


# ── Founder-name P0 gate ──────────────────────────────────────────────────────

class TestFounderGate:
    def test_valid_founder_passes(self):
        assert b.validate_founder_name("Jane Doe") == "Jane Doe"

    def test_missing_founder_halts(self):
        with pytest.raises(b.SeoValidationError):
            b.validate_founder_name("")

    @pytest.mark.parametrize("ph", ["Founder", "founder name", "brand", "TODO"])
    def test_placeholder_founder_halts(self, ph):
        with pytest.raises(b.SeoValidationError):
            b.validate_founder_name(ph)

    def test_founder_equal_to_brand_halts(self):
        with pytest.raises(b.SeoValidationError):
            b.validate_founder_name("Acme", brand="acme")


# ── SEO seoMeta build + gates ─────────────────────────────────────────────────

def _seo(**over):
    base = dict(
        title="Acme Soap — Handmade Bars",
        description="Small-batch handmade soap, shipped fresh to your door.",
        keywords=["handmade soap", "natural soap bars", "small batch soap"],
        founder_name="Jane Doe",
        canonical_url="https://www.acmesoap.com/home",
        og_image="https://storage.googleapis.com/msgsndr/abc.png",
    )
    base.update(over)
    return base


class TestBuildSeoMeta:
    def test_happy_path_sets_author_to_founder_and_language_en(self):
        seo = b.build_seo_meta(**_seo())
        assert seo["author"] == "Jane Doe"          # author := founder
        assert seo["language"] == "en"              # explicit, not GHL default
        assert seo["keywords"] == ["handmade soap", "natural soap bars",
                                   "small batch soap"]
        assert seo["canonicalUrl"].startswith("https://")

    def test_title_over_60_halts(self):
        with pytest.raises(b.SeoValidationError):
            b.build_seo_meta(**_seo(title="x" * 61))

    def test_description_over_160_halts(self):
        with pytest.raises(b.SeoValidationError):
            b.build_seo_meta(**_seo(description="x" * 161))

    def test_too_few_distinct_keywords_halts(self):
        with pytest.raises(b.SeoValidationError):
            b.build_seo_meta(**_seo(keywords=["one keyword", "two keyword"]))

    def test_placeholder_keywords_dropped_then_floor_halts(self):
        with pytest.raises(b.SeoValidationError):
            b.build_seo_meta(**_seo(keywords=["real one", "lorem", "TODO", "real one"]))

    def test_keywords_dedup_case_insensitive(self):
        seo = b.build_seo_meta(**_seo(
            keywords=["Soap", "soap", "natural soap", "handmade soap"]))
        assert seo["keywords"] == ["Soap", "natural soap", "handmade soap"]

    def test_keywords_accepts_comma_string(self):
        seo = b.build_seo_meta(**_seo(keywords="a soap, b soap, c soap"))
        assert seo["keywords"] == ["a soap", "b soap", "c soap"]

    def test_canonical_must_be_https(self):
        with pytest.raises(b.SeoValidationError):
            b.build_seo_meta(**_seo(canonical_url="http://acmesoap.com/home"))

    def test_canonical_rejects_storage_host(self):
        with pytest.raises(b.SeoValidationError):
            b.build_seo_meta(**_seo(
                canonical_url="https://storage.googleapis.com/x/p.html"))

    def test_canonical_host_match_when_expected_host_given(self):
        # www-insensitive match passes; a mismatch halts.
        b.build_seo_meta(**_seo(expected_host="acmesoap.com"))
        with pytest.raises(b.SeoValidationError):
            b.build_seo_meta(**_seo(expected_host="other.com"))

    def test_ogimage_must_be_absolute_https(self):
        with pytest.raises(b.SeoValidationError):
            b.build_seo_meta(**_seo(og_image="/relative/x.png"))

    def test_missing_founder_halts_in_build(self):
        with pytest.raises(b.SeoValidationError):
            b.build_seo_meta(**_seo(founder_name=""))


class TestAssertSeoPopulated:
    def test_full_seo_meta_passes(self):
        seo = b.build_seo_meta(**_seo())
        res = b.assert_seo_populated(seo)
        assert res["ok"] is True
        assert res["reasons"] == []

    def test_absent_seo_fails(self):
        assert b.assert_seo_populated(None)["ok"] is False
        assert b.assert_seo_populated({})["ok"] is False

    def test_non_en_language_flagged(self):
        seo = b.build_seo_meta(**_seo(language="fr"))
        res = b.assert_seo_populated(seo)
        assert res["ok"] is False
        assert any("language" in r for r in res["reasons"])


# ── Two-saves invariant ───────────────────────────────────────────────────────

class TestTwoSaves:
    def test_emit_two_save_plan_is_ordered_code_then_page(self):
        plan = b.emit_two_save_plan()
        assert [s["step"] for s in plan["steps"]] == ["save_code", "save_page"]
        assert plan["steps"][0]["gate"] == b.CODE_SAVE_GATE == 17
        assert plan["steps"][1]["gate"] == b.PAGE_SAVE_GATE == 19
        assert plan["steps"][0]["ledger_target"] == "code-saved"
        assert plan["steps"][1]["ledger_target"] == "page-saved"

    def test_assert_two_saves_on_rest_plan_ok(self):
        plan = _rest_plan()
        res = b.assert_two_saves(plan)
        assert res["ok"] is True
        assert res["code_save_step"] == "edit"
        assert res["page_save_step"] == "page_autosave"

    def test_assert_two_saves_detects_order_violation(self):
        # Swap the ledger targets so page-save would precede code-save in order.
        bad = {
            "steps": [{"step": "page_autosave"}, {"step": "edit"}],
            "ledger_targets": {"page_autosave": "page-saved", "edit": "code-saved"},
        }
        res = b.assert_two_saves(bad)
        assert res["ok"] is False
        assert any("ORDER" in r for r in res["reasons"])

    def test_assert_two_saves_detects_missing_code_save(self):
        res = b.assert_two_saves({
            "steps": [{"step": "page_autosave"}],
            "ledger_targets": {"page_autosave": "page-saved"},
        })
        assert res["ok"] is False
        assert any("CODE save" in r for r in res["reasons"])


# ── SEO wired into emit_rest_save_plan ────────────────────────────────────────

def _customcode_blob(raw="<img src='old.png'>"):
    return {
        "sections": [{"elements": [{
            "id": "el-0", "type": "custom-code",
            "extra": {"customCode": {"value": {"rawCustomCode": raw}}}}]}],
        "settings": {},
        "trackingCode": {"head": ""},
    }


def _rest_plan(**over):
    kw = dict(
        page_id="P", funnel_id="F", location_id=FIXTURE_LOC,
        current_location_id=FIXTURE_LOC,
        locator={"section_idx": 0, "element_idx": 0},
        new_value="MARKER", page_version=1, page_data=_customcode_blob(),
        preview_url="https://www.example.com/preview/P", marker="MARKER",
    )
    kw.update(over)
    return b.emit_rest_save_plan(**kw)


class TestRestSaveSeoWiring:
    def test_no_seo_keeps_default_six_step_shape(self):
        plan = _rest_plan()
        assert [s["step"] for s in plan["steps"]] == [
            "stage_token", "page_read", "edit", "page_autosave",
            "verify_preview", "revert_baseline"]
        assert "seo" not in plan
        assert plan["two_saves"]["ok"] is True

    def test_seo_inserts_ordered_seo_apply_after_autosave(self):
        plan = _rest_plan(seo=_seo())
        assert [s["step"] for s in plan["steps"]] == [
            "stage_token", "page_read", "edit", "page_autosave",
            "seo_apply", "verify_preview", "revert_baseline"]
        seo_step = next(s for s in plan["steps"] if s["step"] == "seo_apply")
        assert seo_step["expect"]["og_image_http_200"] == _seo()["og_image"]
        assert seo_step["expect"]["author_is_founder"] is True
        assert plan["seo"]["author"] == "Jane Doe"

    def test_seo_persisted_in_autosave_body_not_baseline(self):
        blob = _customcode_blob()
        before = json.dumps(blob, sort_keys=True)
        plan = _rest_plan(page_data=blob, seo=_seo())
        # The pristine baseline is untouched (revert stays byte-identical).
        assert json.dumps(blob, sort_keys=True) == before
        assert "seoMeta" not in blob
        save = next(s for s in plan["steps"] if s["step"] == "page_autosave")
        assert "seoMeta" in save["body"]["pageData"]
        assert save["body"]["pageData"]["seoMeta"]["author"] == "Jane Doe"

    def test_invalid_seo_halts_the_plan(self):
        with pytest.raises(b.SeoValidationError):
            _rest_plan(seo=_seo(founder_name=""))


# ── gates.json Show-settings ALT-route prior ──────────────────────────────────

class TestShowSettingsAltRoutePrior:
    def test_alt_route_entry_present_and_points_at_gate_14(self):
        g = b.load_gates()
        alt = g["full_width_alt_route_show_settings"]
        assert alt["alt_to_gate"] == 14
        assert alt["status"] == "runtime"
        assert "Show settings" in alt["label"]
        assert "Allow Rows to take entire width" in alt["find"]

    def test_alt_route_does_not_change_gate_counts(self):
        # The harden run owns the gate-array selector priors; the QC asserts
        # exactly 2 captured / 26 runtime / 28 total — the alt route is a
        # top-level prior, NOT a member of the gates array.
        cap = b.captured_gates()
        run = b.runtime_gates()
        assert len(cap) == 2
        assert len(run) == 26
        assert len(b.load_gates()["gates"]) == 28


# ── CLI surface ───────────────────────────────────────────────────────────────

def _run(args):
    return subprocess.run(
        [sys.executable, os.path.join(_TOOLS_DIR, "ghl_builder.py"), *args],
        capture_output=True, text=True)


class TestCli:
    def test_zhc_order_flag(self):
        res = _run(["zhc", "", "--order", "3"])
        assert res.returncode == 0
        assert res.stdout.strip() == "ZHC part 3"

    def test_zhc_uppercase_emit(self):
        res = _run(["zhc", "test"])
        assert res.stdout.strip() == "ZHC test"

    def test_seo_check_pass(self, tmp_path):
        spec = tmp_path / "seo.json"
        spec.write_text(json.dumps(_seo()))
        res = _run(["seo-check", str(spec)])
        assert res.returncode == 0, res.stderr
        out = json.loads(res.stdout)
        assert out["ok"] is True
        assert out["seo_meta"]["author"] == "Jane Doe"

    def test_seo_check_fail_exit_one(self, tmp_path):
        spec = tmp_path / "seo_bad.json"
        spec.write_text(json.dumps(_seo(founder_name="")))
        res = _run(["seo-check", str(spec)])
        assert res.returncode == 1
        out = json.loads(res.stdout)
        assert out["ok"] is False

    def test_two_saves_cli(self):
        res = _run(["two-saves"])
        assert res.returncode == 0, res.stderr
        plan = json.loads(res.stdout)
        assert [s["step"] for s in plan["steps"]] == ["save_code", "save_page"]
