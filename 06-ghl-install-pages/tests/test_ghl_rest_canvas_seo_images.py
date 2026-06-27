"""MOCK-only unit tests — ghl_rest_canvas §2 SEO + §3 images-as-media-links.

These tests cover the transcript BUILD-RECIPE additions this run owns:

  * §2 SEO / AI-search Content panel — build_seo_meta / validate_seo_meta /
    set_page_seo / assert_seo_populated / page_seo_autosave: the populated,
    VALIDATED seoMeta (title<=60, description<=160, researched keywords, author
    BOUND to the founder name, https canonical that is not a Firebase/GCS storage
    host, explicit language, GHL-media ogImage) spliced onto the pageData blob.
  * §3 images-as-media-links — is_ghl_media_url / find_non_ghl_images /
    assert_images_are_ghl_media and the html_fragment(require_ghl_media=True)
    gate: external hot-links / placeholders / src-less <img> are rejected; GHL
    media-storage URLs pass.

No network, no browser, no real client/operator data — all values are generic
fakes. Pure-transform / shape assertions only.
"""
from __future__ import annotations

import os
import sys

_TOOLS_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "tools"))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

import pytest

import ghl_rest_canvas as rc


FAKE_PAGE_ID = "PAGEID0000000000fake"
FAKE_FUNNEL_ID = "FUNNELID000000000fake"
FOUNDER = "Jordan Rivera"
GCS_IMG = "https://storage.googleapis.com/msgsndr/loc123/media/hero.png"
LC_IMG = "https://images.leadconnectorhq.com/media/hero.png"
CANON = "https://funnel.example.com/optin"
CANON_HOSTS = ("funnel.example.com",)


def _seo(**over):
    base = dict(
        title="Handmade Soap Trio — Cold-Process Botanical Bars",
        description="Small-batch cold-process soap made with botanical oils, "
                    "shipped nationwide. Order the trio today.",
        keywords=["cold process soap", "botanical soap bars", "handmade soap trio"],
        founder_name=FOUNDER,
        canonical_url=CANON,
        canonical_hosts=CANON_HOSTS,
    )
    base.update(over)
    return rc.build_seo_meta(**base)


# ── §3 images-as-media-links ──────────────────────────────────────────────────

class TestIsGhlMediaUrl:
    def test_gcs_msgsndr_object_is_media(self):
        assert rc.is_ghl_media_url(GCS_IMG) is True

    def test_leadconnector_cdn_is_media(self):
        assert rc.is_ghl_media_url(LC_IMG) is True

    def test_protocol_relative_leadconnector_is_media(self):
        assert rc.is_ghl_media_url("//images.leadconnectorhq.com/x.png") is True

    def test_arbitrary_gcs_bucket_without_msgsndr_is_not_media(self):
        # Public GCS but NOT the GHL /msgsndr/ namespace — reject.
        assert rc.is_ghl_media_url("https://storage.googleapis.com/other/x.png") is False

    @pytest.mark.parametrize("bad", [
        "https://cdn.unsplash.com/photo.jpg",   # external hot-link
        "http://example.com/img.png",           # external + non-https
        "data:image/png;base64,AAAA",           # placeholder
        "file:///tmp/x.png",                     # local placeholder
        "/relative/path.png",                    # relative — no host
        "img.png",                               # bare relative
        "",                                       # empty
        "   ",                                    # blank
    ])
    def test_non_ghl_sources_rejected(self, bad):
        assert rc.is_ghl_media_url(bad) is False

    def test_extra_hosts_extends_allowlist(self):
        custom = "https://media.myagency.com/x.png"
        assert rc.is_ghl_media_url(custom) is False
        assert rc.is_ghl_media_url(custom, extra_hosts=("media.myagency.com",)) is True


class TestFindNonGhlImages:
    def test_all_ghl_images_clean(self):
        html = f"<div><img src='{GCS_IMG}'><img src=\"{LC_IMG}\" alt='hi'></div>"
        assert rc.find_non_ghl_images(html) == []

    def test_external_image_flagged(self):
        html = f"<img src='{GCS_IMG}'><img src='https://evil.cdn.com/x.png'>"
        problems = rc.find_non_ghl_images(html)
        assert len(problems) == 1
        assert "evil.cdn.com" in problems[0]

    def test_src_less_image_flagged(self):
        problems = rc.find_non_ghl_images("<img alt='no src here'>")
        assert len(problems) == 1
        assert "no src" in problems[0].lower()

    def test_empty_src_flagged(self):
        problems = rc.find_non_ghl_images("<img src=''>")
        assert len(problems) == 1
        assert "empty src" in problems[0].lower()

    def test_no_images_is_clean(self):
        assert rc.find_non_ghl_images("<p>no images here</p>") == []


class TestAssertImagesAreGhlMedia:
    def test_passes_for_ghl_media(self):
        rc.assert_images_are_ghl_media(f"<img src='{GCS_IMG}'>")  # no raise

    def test_raises_listing_offenders(self):
        html = f"<img src='{GCS_IMG}'><img src='https://x.com/a.png'>"
        with pytest.raises(ValueError) as exc:
            rc.assert_images_are_ghl_media(html)
        assert "x.com/a.png" in str(exc.value)


class TestHtmlFragmentImageGate:
    def test_require_ghl_media_passes_for_ghl_img(self):
        out = rc.html_fragment(f"<section><img src='{GCS_IMG}'></section>",
                               require_ghl_media=True)
        assert GCS_IMG in out

    def test_require_ghl_media_rejects_external(self):
        with pytest.raises(ValueError):
            rc.html_fragment("<img src='https://external.com/x.png'>",
                             require_ghl_media=True)

    def test_default_does_not_gate_images(self):
        # Backward-compatible default: external img passes when not requiring media.
        out = rc.html_fragment("<img src='https://external.com/x.png'>")
        assert "external.com" in out

    def test_media_hosts_kwarg_threaded_through(self):
        custom = "https://media.myagency.com/x.png"
        out = rc.html_fragment(f"<img src='{custom}'>", require_ghl_media=True,
                               media_hosts=("media.myagency.com",))
        assert custom in out


# ── §2 SEO / AI-search Content panel ──────────────────────────────────────────

class TestBuildSeoMeta:
    def test_happy_path_shape(self):
        meta = _seo()
        assert meta["author"] == FOUNDER            # author BOUND to founder
        assert meta["language"] == "en"             # explicit, not GHL default
        assert meta["canonicalUrl"] == CANON
        assert meta["keywords"] == [
            "cold process soap", "botanical soap bars", "handmade soap trio"
        ]
        assert meta["ogImage"] == ""                # optional, absent here

    def test_author_is_founder_even_when_brand_tempting(self):
        meta = _seo(founder_name="Casey Okafor")
        assert meta["author"] == "Casey Okafor"

    def test_title_over_60_rejected(self):
        with pytest.raises(ValueError, match="title"):
            _seo(title="x" * 61)

    def test_title_at_limit_ok(self):
        assert _seo(title="x" * 60)["title"] == "x" * 60

    def test_description_over_160_rejected(self):
        with pytest.raises(ValueError, match="description"):
            _seo(description="y" * 161)

    def test_missing_founder_rejected(self):
        with pytest.raises(ValueError, match="founder_name"):
            _seo(founder_name="   ")

    def test_too_few_keywords_rejected(self):
        with pytest.raises(ValueError, match="DISTINCT"):
            _seo(keywords=["only one", "two terms"])

    def test_duplicate_keywords_do_not_count(self):
        with pytest.raises(ValueError, match="DISTINCT"):
            _seo(keywords=["soap", "Soap", "SOAP"])  # 1 distinct

    def test_placeholder_keyword_rejected(self):
        with pytest.raises(ValueError, match="placeholder"):
            _seo(keywords=["real term one", "real term two", "TBD"])

    def test_canonical_must_be_https(self):
        with pytest.raises(ValueError, match="https"):
            _seo(canonical_url="http://funnel.example.com/optin")

    def test_canonical_rejects_firebase_storage_host(self):
        with pytest.raises(ValueError, match="storage/Firebase"):
            _seo(canonical_url="https://firebasestorage.googleapis.com/x",
                 canonical_hosts=None)

    def test_canonical_rejects_gcs_storage_host(self):
        with pytest.raises(ValueError, match="storage/Firebase"):
            _seo(canonical_url="https://storage.googleapis.com/msgsndr/p",
                 canonical_hosts=None)

    def test_canonical_host_not_in_allowlist_rejected(self):
        with pytest.raises(ValueError, match="allowlist"):
            _seo(canonical_url="https://other-domain.com/optin")

    def test_canonical_subdomain_of_allowlist_ok(self):
        meta = _seo(canonical_url="https://www.funnel.example.com/optin")
        assert "funnel.example.com" in meta["canonicalUrl"]

    def test_ogimage_must_be_ghl_media(self):
        with pytest.raises(ValueError, match="ogImage"):
            _seo(og_image="https://external.com/og.png")

    def test_ogimage_ghl_media_accepted(self):
        assert _seo(og_image=GCS_IMG)["ogImage"] == GCS_IMG

    def test_ogimage_unverified_rejected(self):
        with pytest.raises(ValueError, match="re-verify"):
            _seo(og_image=GCS_IMG, og_image_verified=False)

    def test_ogimage_verified_accepted(self):
        assert _seo(og_image=GCS_IMG, og_image_verified=True)["ogImage"] == GCS_IMG

    def test_links_must_be_absolute(self):
        with pytest.raises(ValueError, match="links"):
            _seo(links=["/relative/path"])

    def test_links_and_tags_passthrough(self):
        meta = _seo(links=["https://maps.example.com/x"], tags=["soap", "botanical"])
        assert meta["links"] == ["https://maps.example.com/x"]
        assert meta["tags"] == ["soap", "botanical"]

    def test_language_can_be_overridden_explicitly(self):
        assert _seo(language="es")["language"] == "es"


class TestValidateSeoMeta:
    def test_valid_meta_passes(self):
        rc.validate_seo_meta(_seo(), founder_name=FOUNDER, canonical_hosts=CANON_HOSTS)

    def test_author_mismatch_rejected(self):
        meta = _seo()
        with pytest.raises(ValueError, match="founder"):
            rc.validate_seo_meta(meta, founder_name="Someone Else")

    def test_blank_author_rejected(self):
        meta = _seo()
        meta["author"] = ""
        with pytest.raises(ValueError, match="author"):
            rc.validate_seo_meta(meta)

    def test_non_dict_rejected(self):
        with pytest.raises(ValueError):
            rc.validate_seo_meta("not a dict")


class TestSetPageSeoAndGate:
    def _blob(self):
        return {"sections": [{"elements": []}], "settings": {}}

    def test_set_page_seo_is_pure_copy(self):
        blob = self._blob()
        meta = _seo()
        out = rc.set_page_seo(blob, meta, founder_name=FOUNDER,
                              canonical_hosts=CANON_HOSTS)
        assert out["seoMeta"]["author"] == FOUNDER
        assert "seoMeta" not in blob          # input untouched
        out["seoMeta"]["title"] = "mutated"
        assert meta["title"] != "mutated"     # deep-copied, source untouched

    def test_set_page_seo_validates_before_write(self):
        bad = _seo()
        bad["keywords"] = []                  # corrupt after build
        with pytest.raises(ValueError):
            rc.set_page_seo(self._blob(), bad)

    def test_assert_seo_populated_passes(self):
        out = rc.set_page_seo(self._blob(), _seo(), founder_name=FOUNDER,
                              canonical_hosts=CANON_HOSTS)
        rc.assert_seo_populated(out, founder_name=FOUNDER, canonical_hosts=CANON_HOSTS)

    def test_assert_seo_populated_raises_when_absent(self):
        with pytest.raises(ValueError, match="seoMeta"):
            rc.assert_seo_populated(self._blob())


class TestPageSeoAutosave:
    def test_emits_autosave_step_with_seo_expect(self):
        blob = {"sections": [{"elements": []}], "settings": {}}
        meta = _seo()
        step = rc.page_seo_autosave(
            FAKE_PAGE_ID, blob, meta, funnel_id=FAKE_FUNNEL_ID, page_version=3,
            founder_name=FOUNDER, canonical_hosts=CANON_HOSTS,
        )
        assert step["method"] == "POST"
        assert step["expect"]["seo_populated"] is True
        assert step["expect"]["seo_author_is_founder"] is True
        # The seoMeta rides inside the autosaved pageData blob.
        assert step["body"]["pageData"]["seoMeta"]["author"] == FOUNDER
        assert step["body"]["pageVersion"] == 4         # numeric n+1
        assert step["body"]["pageType"] == "draft"      # default draft

    def test_invalid_seo_blocks_step(self):
        blob = {"sections": [{"elements": []}], "settings": {}}
        meta = _seo()
        meta["canonicalUrl"] = "http://insecure.example.com"
        with pytest.raises(ValueError):
            rc.page_seo_autosave(
                FAKE_PAGE_ID, blob, meta, funnel_id=FAKE_FUNNEL_ID,
                page_version=1, founder_name=FOUNDER, canonical_hosts=CANON_HOSTS,
            )
