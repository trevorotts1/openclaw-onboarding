"""Tests for PD-205c -- the image check gets a contract and is sent the slide image.

Acceptance rows (01-BUILD-SPEC.md, PD-205c):
  A1  the request built for a `P-IMAGE-QC` unit holds one image part whose
      bytes equal the fixture image
  A2  a text-only route: zero calls and the plain reason
  A3  the merged report from stub answers carries `observed_text` on every
      slide row, `request_id`, and `graded_by_model`; with the human grounding
      sub-verdict present, PHASE_VERIFIERS["P-IMAGE-QC"] passes
  A4  control: a stub answer without `observed_text` makes its unit invalid
  A5  no test opens a network connection (the stub is the only transport
      object created)

A REAL image check sends the client's slide images to a model provider. No
builder or checker does that (the unit's live-action flag): every transport in
this file is a Python stub, and an autouse fixture turns `urlopen` into a hard
failure so a real call can never happen silently.
"""
from __future__ import annotations

import base64
import json
import random
import struct
import sys
import zlib
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

from presentation_job import dispatcher  # noqa: E402
import phase_verifiers  # noqa: E402

REASON = "this route cannot carry an image"


# --------------------------------------------------------------------------
# fixtures / stubs (no network, no model)
# --------------------------------------------------------------------------
def _noise_png(size: int = 192) -> bytes:
    """A real, decodable PNG of single-colour-noise pixels: >51,200 bytes (the
    kie-bake floor build_deck enforces) and non-flat, so the pixel leg of the
    image gate genuinely measures it instead of rejecting a 1x1 stub."""
    rnd = random.Random(205)
    raw = b"".join(b"\x00" + bytes(rnd.randrange(256) for _ in range(size * 3))
                   for _ in range(size))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data +
                struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9))
            + chunk(b"IEND", b""))


class FakeRouter:
    """model_router stand-in: resolves ONE fixed route, no profile read."""
    _PROVIDER_KEY_NAMES = {"openrouter": ("OPENROUTER_API_KEY",)}

    def __init__(self, provider: str, model: str) -> None:
        self.provider, self.model = provider, model

    def active_mode(self) -> str:
        return "standard"

    def resolve_route(self, phase_id, mode=None):
        return {"router": "fake", "profile_state": "has_providers",
                "route": {"provider": self.provider, "model": self.model},
                "reason": "fake route"}

    def _norm_provider(self, provider):
        return str(provider or "").strip().lower().replace("_", "-")


def _recorder(sink: list):
    def _stub(system_prompt, user_prompt, **kwargs):
        sink.append(kwargs)
        return '{"pass": true, "observed_text": "stub"}', {"request_id": "req_1"}
    return _stub


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """A5: no test in this file may open a connection. urlopen is poisoned for
    every test, so a leaked real call fails loudly instead of billing."""
    def _boom(*args, **kwargs):  # noqa: ANN001
        raise AssertionError("PD-205c test attempted a network connection")
    monkeypatch.setattr(dispatcher.urllib.request, "urlopen", _boom)
    yield


def _run_dir(tmp_path: Path, slides=(1, 2)) -> Path:
    run_dir = tmp_path / "run"
    (run_dir / "renders").mkdir(parents=True, exist_ok=True)
    png = _noise_png()
    for n in slides:
        (run_dir / "renders" / f"slide-{n:02d}.png").write_bytes(png)
    return run_dir


# --------------------------------------------------------------------------
# A1 -- the request carries the slide image, byte for byte
# --------------------------------------------------------------------------
def test_a1_request_holds_one_image_part_of_the_fixture_bytes(tmp_path, monkeypatch):
    run_dir = _run_dir(tmp_path, slides=(1,))
    png = (run_dir / "renders" / "slide-01.png").read_bytes()
    payload = {"phase_id": "P-IMAGE-QC", "ordinal": 1, "slide_id": "slide-01"}

    # the unit's own read: exactly this slide's render bytes
    image = dispatcher.unit_slide_image(run_dir, payload)
    assert image == (png, "image/png")

    # the request the transport actually sends
    body = dispatcher.openai_compat_body(
        "system", "grade slide 1", model="qwen2.5-vl-72b", max_tokens=64,
        image=image)
    parts = body["messages"][1]["content"]
    assert [p["type"] for p in parts] == ["text", "image_url"]
    url = parts[1]["image_url"]["url"]
    assert url.startswith("data:image/png;base64,")
    assert base64.b64decode(url[len("data:image/png;base64,"):]) == png

    # ... and the same bytes cross the dispatch seam into the transport
    calls: list = []
    monkeypatch.setattr(dispatcher, "_model_router",
                        FakeRouter("openrouter", "qwen2.5-vl-72b"))
    monkeypatch.setattr(dispatcher, "_openai_compat_complete", _recorder(calls))
    dispatcher.dispatch_complete("system", "grade slide 1", phase_id="P-IMAGE-QC",
                                 run_dir=run_dir, image=image)
    assert len(calls) == 1
    assert calls[0]["image"] == (png, "image/png")


# --------------------------------------------------------------------------
# A2 -- a text-only route: zero calls, the plain reason, no fallback
# --------------------------------------------------------------------------
def test_a2_text_only_route_zero_calls_and_plain_reason(tmp_path, monkeypatch):
    run_dir = _run_dir(tmp_path, slides=(1,))
    image = ((run_dir / "renders" / "slide-01.png").read_bytes(), "image/png")
    deep_calls: list = []
    compat_calls: list = []
    paid: list = []

    monkeypatch.setattr(dispatcher, "_model_router",
                        FakeRouter("deepseek-direct", "deepseek-v4.1-flash"))
    monkeypatch.setattr(dispatcher, "deepseek_complete",
                        lambda *a, **k: deep_calls.append((a, k)) or ("", {}))
    monkeypatch.setattr(dispatcher, "_openai_compat_complete",
                        _recorder(compat_calls))
    monkeypatch.setattr(dispatcher, "_reserve_paid_attempt",
                        lambda *a, **k: paid.append((a, k)))

    with pytest.raises(dispatcher.ImageRouteIneligible) as excinfo:
        dispatcher.dispatch_complete("system", "grade slide 1",
                                     phase_id="P-IMAGE-QC", run_dir=run_dir,
                                     image=image)

    assert excinfo.value.reason == REASON
    assert dispatcher.IMAGE_ROUTE_INELIGIBLE_REASON == REASON
    assert str(excinfo.value).endswith(REASON)
    # zero transport calls, zero paid attempts: never a text-only fallback
    assert deep_calls == []
    assert compat_calls == []
    assert paid == []


# --------------------------------------------------------------------------
# A1 (contract half) -- the phase is actually TOLD the new shape
# --------------------------------------------------------------------------
def test_image_phase_is_told_its_own_contract_not_the_generic_one(tmp_path):
    run_dir = _run_dir(tmp_path, slides=(1,))
    dept_root = tmp_path / "dept"
    dept_root.mkdir()
    (dept_root / "image-qc-specialist.md").write_text("SOP", encoding="utf-8")
    payload = {"phase_id": "P-IMAGE-QC", "ordinal": 1, "slide_id": "slide-01",
               "scope": "slide", "unit_count": 1,
               "unit_kind": "json", "output_schema": "json: {observed_text, pass}"}
    order = dispatcher._unit_scope_work_order({"phase_id": "P-IMAGE-QC"}, payload)

    _system, user = dispatcher.compose_prompt(
        phase_id="P-IMAGE-QC", owning_role="image-qc-specialist",
        dept_root=dept_root, run_dir=run_dir, order=order, attempt=1,
        prior_reasons=None)

    assert "Report what you see. A failing slide is a correct output." in user
    assert '"observed_text"' in user
    # the generic contract's "write an artifact file" instruction is gone
    assert "write the exact artifact file(s) named in the work order" not in user
    # and the unit is told the picture is attached
    assert "THE RENDERED SLIDE IMAGE IS ATTACHED" in user


# --------------------------------------------------------------------------
# A3 -- the merged report is a vision record the step check can pass
# --------------------------------------------------------------------------
def _stub_answers(n: int = 2):
    ordered = []
    for ordinal in range(1, n + 1):
        payload = {
            "key": f"slide-{ordinal:02d}", "phase_id": "P-IMAGE-QC",
            "unit_count": n, "ordinal": ordinal,
            "slide_id": f"slide-{ordinal:02d}", "scope": "slide",
            "needs_observed_text": True,
            "reviewer_role": "image-grounding-steward",
            "route_provider": "openrouter",
            "route_model": "qwen2.5-vl-72b",
            "route_request_id": "req_img_1",
        }
        answer = json.dumps({
            "slide": ordinal, "slide_id": f"slide-{ordinal:02d}",
            "pass": True,
            "observed_text": f"slide {ordinal}: the words baked into the render",
            "findings": [],
        })
        ordered.append((payload, answer))
    return ordered


def test_a3_merged_report_carries_the_vision_provenance_and_the_step_passes(tmp_path):
    run_dir = _run_dir(tmp_path, slides=(1, 2))
    merged = dispatcher._reduce_qc_union(_stub_answers(2))
    assert merged, "the union refused a complete, well-formed stub deck"
    report = json.loads(merged)

    # every slide row carries the observation it graded ...
    assert [r["observed_text"] for r in report["slides"]] == [
        "slide 1: the words baked into the render",
        "slide 2: the words baked into the render",
    ]
    # ... and the report names the route that graded it, from the record
    assert report["graded_by_model"] == "qwen2.5-vl-72b"
    assert report["graded_by_provider"] == "openrouter"
    assert report["request_id"] == "req_img_1"

    # the human grounding sub-verdict (PD-206a's file) is run data, not code
    report["image_grounding"] = {"pass": True,
                                 "reviewed_by": "image-grounding-steward"}
    (run_dir / "working" / "qc").mkdir(parents=True, exist_ok=True)
    (run_dir / "working" / "qc" / "image_qc_report.json").write_text(
        json.dumps(report), encoding="utf-8")

    ok, reasons = phase_verifiers.PHASE_VERIFIERS["P-IMAGE-QC"](run_dir)
    assert ok is True, reasons


# --------------------------------------------------------------------------
# A4 -- control: an answer without observed_text is not a valid unit
# --------------------------------------------------------------------------
def test_a4_answer_without_observed_text_is_an_invalid_unit():
    payload = {"phase_id": "P-IMAGE-QC", "ordinal": 1,
               "slide_id": "slide-01", "needs_observed_text": True}

    ok, reasons = dispatcher._validate_qc_slide(
        payload, json.dumps({"slide": 1, "slide_id": "slide-01", "pass": True}))
    assert ok is False
    assert any("observed_text" in r for r in reasons), reasons

    # control: the same answer WITH the observation is a valid unit
    ok2, reasons2 = dispatcher._validate_qc_slide(
        payload, json.dumps({"slide": 1, "slide_id": "slide-01", "pass": True,
                             "observed_text": "the baked headline"}))
    assert ok2 is True, reasons2


# --------------------------------------------------------------------------
# A5 -- the stub is the only transport object created
# --------------------------------------------------------------------------
def test_a5_no_network_connection_is_opened(tmp_path, monkeypatch):
    run_dir = _run_dir(tmp_path, slides=(1,))
    image = ((run_dir / "renders" / "slide-01.png").read_bytes(), "image/png")
    calls: list = []
    monkeypatch.setattr(dispatcher, "_model_router",
                        FakeRouter("ollama-cloud", "qwen2.5-vl:32b"))
    monkeypatch.setattr(dispatcher, "_openai_compat_complete", _recorder(calls))
    monkeypatch.setattr(dispatcher, "deepseek_complete",
                        lambda *a, **k: pytest.fail("native transport used"))

    dispatcher.dispatch_complete("system", "grade", phase_id="P-IMAGE-QC",
                                 run_dir=run_dir, image=image)
    assert len(calls) == 1  # exactly one stub transport object, nothing else
    # the poisoned urlopen is still the one in place: a real call would fail
    with pytest.raises(AssertionError):
        dispatcher.urllib.request.urlopen("https://example.invalid")
