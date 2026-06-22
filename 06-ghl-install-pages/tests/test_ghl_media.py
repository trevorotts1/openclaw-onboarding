"""MOCK-only unit tests — ghl_media (T2 REAL IMAGE PIPELINE).

These tests are MOCK-ONLY. There are NO live KIE.ai calls, NO live GoHighLevel
media uploads, NO network of any kind, and NO real keys. The image-generation API
is mocked via the injectable ``runner`` (a fake that writes PNG-magic-byte
fixtures and returns an exit code); the GHL media upload is mocked via the
injectable ``opener`` (a fake that returns a canned ``{fileId, url}`` response).
The assertions cover:

  * ``build_prompts_json`` — the English/Latin pin appended VERBATIM (idempotent),
    t2i default, i2i requires input_urls, generator-shaped file vs enriched return,
    duplicate-id / blank-field rejection.
  * ``generate_images`` — shells the REUSED kie_generate.py (mocked runner), and
    fails LOUD on a missing or non-PNG output (never pretends success).
  * ``upload_media`` — the PROVEN ``services.*/medias/upload-file`` request SHAPE
    (origin, ``Authorization: Bearer <PIT>``, ``Version: 2021-07-28``, multipart
    fields + the real file bytes), the public-GCS-url return, and fail-loud on
    non-2xx / missing-fields / non-PNG (never fabricates a CDN URL).
  * ``image_tag`` — refuses file:// / data: placeholders; only the public CDN URL.
  * ``build_image_manifest`` — strict contract (https cdn_url + cdn_http_status 200).
  * the full MOCK wire-in: copy -> prompts -> generate -> upload -> <img> ->
    ``ghl_rest_canvas.edit_element_customcode`` -> draft autosave body, with the
    pristine baseline preserved (revert still possible) and the placeholder gone.

No real client/operator names, ids, emails, or location-ids appear — all values
are generic / parameterised fakes.
"""
from __future__ import annotations

import json
import os
import sys

# Make the tools importable regardless of working directory — same convention as
# the rest of this suite (test_ghl_rest_canvas.py etc.).
_TOOLS_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "tools"))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

import pytest

import ghl_media as m
import ghl_rest_canvas as rc


# ── Generic fakes (NO real client/operator data) ─────────────────────────────

FAKE_PIT = "PIT-fixture-not-a-real-token"
FAKE_LOC = "LOCATION0000000fake"
FAKE_PAGE_ID = "PAGEID0000000000fake"
FAKE_FUNNEL_ID = "FUNNELID000000000fake"
FAKE_GCS_URL = "https://storage.googleapis.com/msgsndr/LOCATION0000000fake/hero-soap-trio.png"

# A minimal real-PNG byte payload (correct magic bytes + a little body).
PNG_BYTES = m.PNG_MAGIC + b"\x00\x00\x00\rIHDR" + b"fakefakefake"


class _FakeResp:
    """Minimal urlopen-like response for the mocked upload opener."""

    def __init__(self, code: int, body: bytes):
        self._code = code
        self._body = body

    def getcode(self) -> int:
        return self._code

    def read(self) -> bytes:
        return self._body


def _ok_opener(record: dict | None = None):
    """Return a fake opener that records the Request and returns a 200 with a
    canned public-GCS ``{fileId, url}``."""
    def _opener(req, timeout):
        if record is not None:
            record["url"] = req.full_url
            record["method"] = req.get_method()
            record["auth"] = req.get_header("Authorization")
            record["version"] = req.get_header("Version")
            record["content_type"] = req.get_header("Content-type")
            record["body"] = req.data
        return _FakeResp(200, json.dumps({"fileId": "FILEID123", "url": FAKE_GCS_URL}).encode())
    return _opener


def _png_runner(ids: list[str], exit_code: int = 0, write_png: bool = True):
    """Return a fake KIE runner: writes ``<id>.png`` (real PNG bytes when
    ``write_png``, else a non-PNG) into argv's out_dir, returns ``exit_code``."""
    def _runner(argv: list[str]) -> int:
        out_dir = argv[-1]
        payload = PNG_BYTES if write_png else b"<svg>not a png</svg>"
        for sid in ids:
            with open(os.path.join(out_dir, f"{sid}.png"), "wb") as f:
                f.write(payload)
        return exit_code
    return _runner


def _customcode_blob(raw: str = '<img src="file:///placeholder.svg">') -> dict:
    """A page-data blob with a custom-code element at [0][2] (a placeholder img)."""
    return {
        "sections": [
            {
                "elements": [
                    {"id": "h1", "type": "headline"},
                    {"id": "sub", "type": "text"},
                    {"id": "img", "type": "custom-code",
                     "extra": {"customCode": {"value": {"rawCustomCode": raw}}}},
                ]
            }
        ],
        "settings": {},
        "trackingCode": {"head": ""},
    }


# ── build_prompts_json ────────────────────────────────────────────────────────

class TestBuildPromptsJson:
    def test_appends_english_latin_pin_verbatim(self):
        enriched = m.build_prompts_json([{"id": "hero", "prompt": "A trio of soap bars"}])
        assert m.ENGLISH_LATIN_PIN in enriched[0]["prompt"]
        # The pin is appended after the copy-derived brief.
        assert enriched[0]["prompt"].startswith("A trio of soap bars")

    def test_pin_is_idempotent(self):
        first = m.build_prompts_json([{"id": "a", "prompt": "scene"}])[0]["prompt"]
        second = m.build_prompts_json([{"id": "a", "prompt": first}])[0]["prompt"]
        assert second.count(m.ENGLISH_LATIN_PIN) == 1

    def test_default_mode_is_t2i(self):
        enriched = m.build_prompts_json([{"id": "a", "prompt": "p"}])
        assert enriched[0]["mode"] == "t2i"

    def test_i2i_requires_input_urls(self):
        with pytest.raises(ValueError):
            m.build_prompts_json([{"id": "a", "prompt": "p", "mode": "i2i"}])
        ok = m.build_prompts_json([
            {"id": "a", "prompt": "p", "mode": "i2i", "input_urls": ["https://x/logo.png"]}
        ])
        assert ok[0]["input_urls"] == ["https://x/logo.png"]

    def test_unknown_mode_rejected(self):
        with pytest.raises(ValueError):
            m.build_prompts_json([{"id": "a", "prompt": "p", "mode": "video"}])

    def test_blank_id_or_prompt_rejected(self):
        with pytest.raises(ValueError):
            m.build_prompts_json([{"id": "", "prompt": "p"}])
        with pytest.raises(ValueError):
            m.build_prompts_json([{"id": "a", "prompt": "   "}])

    def test_duplicate_id_rejected(self):
        with pytest.raises(ValueError):
            m.build_prompts_json([{"id": "a", "prompt": "p1"}, {"id": "a", "prompt": "p2"}])

    def test_empty_specs_rejected(self):
        with pytest.raises(ValueError):
            m.build_prompts_json([])

    def test_carries_buildtime_fields_on_return_only(self, tmp_path):
        """Enriched return keeps used_on_page_id/alt/locator; the on-disk file is
        exactly the generator shape (those build-time fields stripped)."""
        out = tmp_path / "prompts.json"
        enriched = m.build_prompts_json(
            [{"id": "hero", "prompt": "p", "used_on_page_id": "P1",
              "alt": "soap", "locator": {"section_idx": 0, "element_idx": 2}}],
            out_path=str(out),
        )
        assert enriched[0]["used_on_page_id"] == "P1"
        assert enriched[0]["locator"] == {"section_idx": 0, "element_idx": 2}
        file_arr = json.loads(out.read_text())
        assert set(file_arr[0].keys()) == {"slide", "prompt", "mode"}
        assert file_arr[0]["slide"] == "hero"

    def test_file_entry_is_kie_generate_shape(self, tmp_path):
        """The written file uses the 'slide' key kie_generate.py consumes."""
        out = tmp_path / "p.json"
        m.build_prompts_json([{"id": "x", "prompt": "p"}], out_path=str(out))
        arr = json.loads(out.read_text())
        assert arr[0]["slide"] == "x" and "mode" in arr[0]


# ── generate_images (mock the gen API via runner) ─────────────────────────────

class TestGenerateImages:
    def _prompts_file(self, tmp_path, ids):
        out = tmp_path / "prompts.json"
        m.build_prompts_json([{"id": i, "prompt": f"p-{i}"} for i in ids], out_path=str(out))
        return str(out)

    def test_all_land_ok(self, tmp_path):
        ids = ["hero-soap-trio", "founder-portrait"]
        prompts = self._prompts_file(tmp_path, ids)
        out_dir = str(tmp_path / "images")
        res = m.generate_images(prompts, out_dir, runner=_png_runner(ids))
        assert res["ok"] is True
        assert res["exit_code"] == 0
        assert res["missing"] == []
        assert {i["id"] for i in res["images"]} == set(ids)
        assert all(i["png_verified"] for i in res["images"])
        assert all(i["bytes"] > 0 for i in res["images"])

    def test_missing_output_fails_loud(self, tmp_path):
        """Generator exits 0 but a slide png never landed -> ok False (no pretend)."""
        ids = ["hero-soap-trio", "founder-portrait"]
        prompts = self._prompts_file(tmp_path, ids)
        out_dir = str(tmp_path / "images")
        # runner only writes the first id.
        res = m.generate_images(prompts, out_dir, expected_ids=ids,
                                runner=_png_runner(["hero-soap-trio"]))
        assert res["ok"] is False
        assert res["missing"] == ["founder-portrait"]

    def test_non_png_output_fails_loud(self, tmp_path):
        """A non-PNG byte blob is NOT accepted (never an SVG stub downstream)."""
        ids = ["hero"]
        prompts = self._prompts_file(tmp_path, ids)
        out_dir = str(tmp_path / "images")
        res = m.generate_images(prompts, out_dir, runner=_png_runner(ids, write_png=False))
        assert res["ok"] is False
        assert res["missing"] == ["hero"]
        assert res["images"] == []

    def test_nonzero_exit_is_not_ok(self, tmp_path):
        ids = ["hero"]
        prompts = self._prompts_file(tmp_path, ids)
        out_dir = str(tmp_path / "images")
        res = m.generate_images(prompts, out_dir, runner=_png_runner(ids, exit_code=1))
        assert res["ok"] is False  # even though the png is present, exit!=0
        assert res["exit_code"] == 1

    def test_runner_receives_reused_kie_generate(self, tmp_path):
        """The argv shelled is python3 + the REUSED kie_generate.py + prompts + out."""
        ids = ["hero"]
        prompts = self._prompts_file(tmp_path, ids)
        out_dir = str(tmp_path / "images")
        seen = {}

        def _capture(argv):
            seen["argv"] = argv
            with open(os.path.join(argv[-1], "hero.png"), "wb") as f:
                f.write(PNG_BYTES)
            return 0

        m.generate_images(prompts, out_dir, runner=_capture)
        assert seen["argv"][1].endswith("kie_generate.py")
        assert seen["argv"][2] == prompts
        assert seen["argv"][3] == out_dir

    def test_missing_prompts_file_raises(self, tmp_path):
        with pytest.raises(ValueError):
            m.generate_images(str(tmp_path / "nope.json"), str(tmp_path / "o"),
                              runner=_png_runner([]))


# ── upload_media (mock the HTTP via opener) ───────────────────────────────────

class TestUploadMedia:
    def _png(self, tmp_path, name="hero-soap-trio.png"):
        p = tmp_path / name
        p.write_bytes(PNG_BYTES)
        return str(p)

    def test_request_shape_matches_proven_pattern(self, tmp_path):
        png = self._png(tmp_path)
        rec: dict = {}
        res = m.upload_media(png, FAKE_LOC, "Brand - Hero", FAKE_PIT, opener=_ok_opener(rec))
        # Returned public GCS url + fileId.
        assert res["fileId"] == "FILEID123"
        assert res["url"] == FAKE_GCS_URL
        assert res["url"].startswith("https://storage.googleapis.com/msgsndr/")
        assert res["http"] == 200
        # Proven services.* origin + path.
        assert rec["url"] == "https://services.leadconnectorhq.com/medias/upload-file"
        assert rec["method"] == "POST"
        # Bearer LOCATION PIT (NOT a different scheme) + the proven Version header.
        assert rec["auth"] == f"Bearer {FAKE_PIT}"
        assert rec["version"] == "2021-07-28"
        assert rec["content_type"].startswith("multipart/form-data; boundary=")

    def test_multipart_carries_fields_and_real_bytes(self, tmp_path):
        png = self._png(tmp_path)
        rec: dict = {}
        m.upload_media(png, FAKE_LOC, "Brand - Hero", FAKE_PIT, opener=_ok_opener(rec))
        body = rec["body"]
        assert b'name="locationId"' in body and FAKE_LOC.encode() in body
        assert b'name="name"' in body and b"Brand - Hero" in body
        assert b'name="hosted"' in body and b"false" in body
        assert b'name="file"; filename="hero-soap-trio.png"' in body
        # The ACTUAL raster bytes are in the multipart payload (a real upload).
        assert PNG_BYTES in body

    def test_hosted_true_and_parent_id(self, tmp_path):
        png = self._png(tmp_path)
        rec: dict = {}
        m.upload_media(png, FAKE_LOC, "N", FAKE_PIT, hosted=True,
                       parent_id="FOLDER123", opener=_ok_opener(rec))
        body = rec["body"]
        assert b'name="hosted"' in body and b"true" in body
        # The documented folder field is parentId (NOT folderId).
        assert b'name="parentId"' in body and b"FOLDER123" in body
        assert b"folderId" not in body

    def test_non_2xx_fails_loud(self, tmp_path):
        png = self._png(tmp_path)
        opener = lambda req, t: _FakeResp(401, b'{"message":"unauthorized"}')
        with pytest.raises(RuntimeError, match="HTTP 401"):
            m.upload_media(png, FAKE_LOC, "N", "BADPIT", opener=opener)

    def test_2xx_missing_fileid_url_fails_loud(self, tmp_path):
        png = self._png(tmp_path)
        opener = lambda req, t: _FakeResp(200, b"{}")
        with pytest.raises(RuntimeError, match="missing fileId/url"):
            m.upload_media(png, FAKE_LOC, "N", FAKE_PIT, opener=opener)

    def test_2xx_non_json_fails_loud(self, tmp_path):
        png = self._png(tmp_path)
        opener = lambda req, t: _FakeResp(200, b"not json")
        with pytest.raises(RuntimeError, match="not JSON"):
            m.upload_media(png, FAKE_LOC, "N", FAKE_PIT, opener=opener)

    def test_non_png_refused_before_upload(self, tmp_path):
        bad = tmp_path / "x.svg"
        bad.write_bytes(b"<svg/>")
        called = {"n": 0}

        def opener(req, t):
            called["n"] += 1
            return _FakeResp(200, b"{}")

        with pytest.raises(ValueError, match="not a valid PNG"):
            m.upload_media(str(bad), FAKE_LOC, "N", FAKE_PIT, opener=opener)
        assert called["n"] == 0  # never even attempted the upload

    def test_blank_args_rejected(self, tmp_path):
        png = self._png(tmp_path)
        for args in [("", FAKE_LOC, "N", FAKE_PIT), (png, "", "N", FAKE_PIT),
                     (png, FAKE_LOC, "", FAKE_PIT), (png, FAKE_LOC, "N", "")]:
            with pytest.raises(ValueError):
                m.upload_media(*args, opener=_ok_opener())


# ── image_tag ─────────────────────────────────────────────────────────────────

class TestImageTag:
    def test_https_url_accepted(self):
        tag = m.image_tag(FAKE_GCS_URL, "soap trio")
        assert tag.startswith(f'<img src="{FAKE_GCS_URL}"')
        assert 'alt="soap trio"' in tag

    def test_alt_quotes_escaped(self):
        tag = m.image_tag(FAKE_GCS_URL, 'a "quoted" alt')
        assert "&quot;" in tag
        assert '"quoted"' not in tag.split("alt=")[1][:40]

    @pytest.mark.parametrize("bad", ["file:///tmp/x.png", "data:image/svg+xml;base64,abc", ""])
    def test_placeholder_or_blank_refused(self, bad):
        with pytest.raises(ValueError):
            m.image_tag(bad)


# ── build_image_manifest (strict https + 200 contract) ────────────────────────

class TestBuildImageManifest:
    def _rec(self, **over):
        rec = {"id": "hero", "prompt": "p", "file": "/x/hero.png",
               "cdn_url": FAKE_GCS_URL, "cdn_http_status": 200, "used_on_page_id": "P1"}
        rec.update(over)
        return rec

    def test_valid_record(self, tmp_path):
        out = tmp_path / "manifest.json"
        man = m.build_image_manifest([self._rec(file_id="F1")], out_path=str(out))
        assert man[0]["cdn_url"] == FAKE_GCS_URL
        assert man[0]["cdn_http_status"] == 200
        assert man[0]["file_id"] == "F1"
        # written file round-trips.
        assert json.loads(out.read_text())[0]["id"] == "hero"

    def test_non_https_cdn_url_rejected(self):
        with pytest.raises(ValueError):
            m.build_image_manifest([self._rec(cdn_url="file:///x/hero.png")])
        with pytest.raises(ValueError):
            m.build_image_manifest([self._rec(cdn_url="http://insecure/x.png")])

    def test_non_200_status_rejected(self):
        with pytest.raises(ValueError):
            m.build_image_manifest([self._rec(cdn_http_status=404)])
        with pytest.raises(ValueError):
            m.build_image_manifest([self._rec(cdn_http_status=None)])

    def test_empty_records_rejected(self):
        with pytest.raises(ValueError):
            m.build_image_manifest([])


# ── Full MOCK wire-in: copy -> prompts -> gen -> upload -> <img> -> autosave ──

class TestMockImagePipelineWireIn:
    """The build-time call sequence end-to-end with the gen API + upload mocked.
    No network. Proves the CDN <img> replaces the placeholder in the page blob via
    ghl_rest_canvas.edit_element_customcode and lands in a DRAFT autosave body,
    while the pristine baseline is preserved (revert still possible)."""

    def test_pipeline(self, tmp_path):
        blob = _customcode_blob('<img src="file:///placeholder.svg">')
        baseline_md5 = rc.blob_md5(blob)

        # 1) copy -> prompts (pin appended, t2i)
        specs = [{"id": "hero-soap-trio", "prompt": "Trio of artisanal soap bars",
                  "used_on_page_id": FAKE_PAGE_ID, "alt": "soap trio",
                  "locator": {"section_idx": 0, "element_idx": 2}}]
        prompts = str(tmp_path / "prompts.json")
        enriched = m.build_prompts_json(specs, out_path=prompts)
        assert m.ENGLISH_LATIN_PIN in enriched[0]["prompt"]

        # 2) generate (MOCK runner writes a real-PNG fixture)
        out_dir = str(tmp_path / "images")
        gen = m.generate_images(prompts, out_dir, runner=_png_runner(["hero-soap-trio"]))
        assert gen["ok"] is True
        png_path = gen["images"][0]["file"]

        # 3) upload (MOCK opener -> public GCS url)
        rec: dict = {}
        up = m.upload_media(png_path, FAKE_LOC, "Brand - Hero", FAKE_PIT, opener=_ok_opener(rec))
        cdn_url = up["url"]
        assert cdn_url.startswith("https://storage.googleapis.com/msgsndr/")

        # 4) <img> referencing the CDN url, spliced via the proven canvas-REST transform
        locator = enriched[0]["locator"]
        new_html = m.image_tag(cdn_url, enriched[0]["alt"])
        edited = rc.edit_element_customcode(blob, locator, new_html)

        # The placeholder is GONE and the public CDN url is now in the element.
        landed = edited["sections"][0]["elements"][2]["extra"]["customCode"]["value"]["rawCustomCode"]
        assert cdn_url in landed
        assert "file://" not in landed
        # The pristine baseline is untouched (copy semantics -> revert possible).
        assert rc.blob_md5(blob) == baseline_md5
        assert not rc.is_byte_identical(blob, edited)

        # 5) the in-browser DRAFT autosave body carries the edited blob (numeric n+1)
        save = rc.page_autosave(FAKE_PAGE_ID, edited, funnel_id=FAKE_FUNNEL_ID, page_version=1)
        assert save["body"]["pageType"] == "draft"
        assert save["body"]["pageVersion"] == 2
        assert cdn_url in json.dumps(save["body"]["pageData"])

        # 6) manifest contract (https + 200), mapping the image to its page
        manifest = m.build_image_manifest([{
            "id": "hero-soap-trio", "prompt": enriched[0]["prompt"], "file": png_path,
            "cdn_url": cdn_url, "cdn_http_status": 200,
            "used_on_page_id": enriched[0]["used_on_page_id"], "file_id": up["fileId"],
        }])
        assert manifest[0]["cdn_url"] == cdn_url
        assert manifest[0]["cdn_http_status"] == 200
        assert manifest[0]["used_on_page_id"] == FAKE_PAGE_ID

        # The mocked upload carried the proven Bearer-PIT + Version + real bytes.
        assert rec["auth"] == f"Bearer {FAKE_PIT}"
        assert rec["version"] == "2021-07-28"
        assert PNG_BYTES in rec["body"]
