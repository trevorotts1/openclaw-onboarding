"""PD-042 -- the client gets what they need to act: the style-pick messages and
the finished message, both built from real run records.

Proves, on the real engine and real records (no network, no model spend):

  * the style-pick request now carries each variant's own one-sentence style
    description (from working/copy/style_preview_spec.json) and that variant's
    three sample file paths, because the reporter transport is a JSON text
    payload that cannot carry an image -- never letters alone, and no phase id;
  * a samples manifest that gives the client nothing to look at sends NO pick
    request and parks instead;
  * the finished message lists one line per VERIFIED delivery destination and
    names no destination whose status is anything else;
  * with no verified destination, no "done" message is sent and
    `report.done_withheld` is recorded;
  * PD-210: a teleprompter publish record with status `warned_no_credentials`
    produces "Your teleprompter file is included. No web link was made for it."
    and no address; only a `published` record contributes a web link.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

from presentation_job import phases as phases_mod  # noqa: E402
from presentation_job import report as report_mod  # noqa: E402
from presentation_job.manifest import Manifest  # noqa: E402
from presentation_job.phases import Engine  # noqa: E402
from presentation_job.state import EXIT_GATE_BLOCKED, StateStore  # noqa: E402


def _canonical_manifest() -> Path:
    deployed = SCRIPTS.parent / "sops" / "PIPELINE-MANIFEST.json"
    if deployed.is_file():
        return deployed
    cur = SCRIPTS
    for _ in range(12):
        cand = cur / "universal-sops" / "presentation-slide-craft" / "PIPELINE-MANIFEST.json"
        if cand.is_file():
            return cand
        if cur.parent == cur:
            break
        cur = cur.parent
    raise FileNotFoundError("PIPELINE-MANIFEST.json not found")


PICK = "P-STYLE-PICK"
CHOICE_REL = "working/copy/style_preview_choice.json"

#: The exact directives the style spec fixture carries. Each message must hold
#: its own variant's directive text verbatim (acceptance: "the message for each
#: variant contains that variant's description text taken from the spec fixture").
DIRECTIVES = {
    "A": "warm editorial, soft gold light, generous white space",
    "B": "high-contrast navy and gold, bold weight ladder",
    "C": "clean minimal, muted neutrals, one accent rule",
}


def _seed_run(tmp_path: Path) -> Path:
    """A run dir holding exactly what P-STYLE-PREVIEW writes: the samples
    manifest (3 variants x 3 representative renders, with real relative render
    paths) and the style spec its directives came from."""
    rd = tmp_path / "run"
    (rd / "working" / "copy").mkdir(parents=True)
    (rd / "working" / "style-preview").mkdir(parents=True)
    (rd / "working" / "copy" / "intake.json").write_text(
        json.dumps({"business_name": "TestCo", "hook": "Grow without guesswork"}))
    samples = []
    for vid in ("A", "B", "C"):
        for ordn in (1, 2, 3):
            samples.append({"variant": vid, "slide": ordn,
                            "render": f"working/style-preview/variant-{vid}-slide-{ordn:02d}.png",
                            "taskId": f"kie-{vid}-{ordn}"})
    (rd / "working" / "style-preview" / "style_samples_manifest.json").write_text(
        json.dumps({"schema": "style_samples_manifest/v1",
                    "variants": ["A", "B", "C"],
                    "representative_slides": [1, 2, 3],
                    "samples": samples,
                    "owner_pick_required": True,
                    "owner_pick_artifact": CHOICE_REL}))
    (rd / "working" / "copy" / "style_preview_spec.json").write_text(json.dumps({
        "variants": [{"id": k, "style_directive": v} for k, v in DIRECTIVES.items()],
        "representative_slides": [1, 2, 3]}))
    return rd


def _engine(rd: Path) -> Engine:
    manifest = Manifest(_canonical_manifest())
    store = StateStore(rd)
    state = {
        "schema_version": 1, "job_id": "t", "run_dir": str(rd),
        "created_at": "2026-01-01T00:00:00+00:00", "manifest_path": str(manifest.path),
        "manifest_version": manifest.version, "manifest_sha256": manifest.sha256,
        "presentation_type": "from_scratch", "requester": {"chat_id": "tc"},
        "phases": [], "gates": [], "waivers": [], "events": [], "sent": {},
        "undeliverable": [], "heartbeat": {}, "terminal": None,
    }
    return Engine(rd, manifest, store, state, dry_run=False)


def _stub_transport(monkeypatch):
    """Every delivered requester message lands here with its kind and text."""
    sent = []

    def _fake_dispatch3(chat_id, kind, message):
        sent.append({"chat_id": chat_id, "kind": kind, "message": message})
        return report_mod.CheckResult.PASS

    monkeypatch.setattr(report_mod, "dispatch3", _fake_dispatch3)
    return sent


class TestStylePickMessages:
    def test_each_variant_message_carries_its_description_and_three_paths(
            self, tmp_path, monkeypatch):
        monkeypatch.setenv("PRESENTATION_STYLE_PICK_TIMEOUT_MINUTES", "0.005")
        monkeypatch.setattr(phases_mod.time, "sleep", lambda *_: None)
        sent = _stub_transport(monkeypatch)
        rd = _seed_run(tmp_path)
        eng = _engine(rd)
        rc = eng.run_phase(eng.manifest.phase_or_none(PICK))
        assert rc == EXIT_GATE_BLOCKED  # no pick landed: it parks, as it must

        picks = [s for s in sent if s["kind"] == "ack"]
        assert len(picks) == 3, [p["message"] for p in picks]
        for i, vid in enumerate(("A", "B", "C")):
            msg = picks[i]["message"]
            assert DIRECTIVES[vid] in msg, (vid, msg)
            for ordn in (1, 2, 3):
                assert f"working/style-preview/variant-{vid}-slide-{ordn:02d}.png" in msg, msg
            assert "Reply A, B or C to pick the look for your whole presentation." in msg
            assert "I will wait for you." in msg
            # No phase id, and no token starting "P-" anywhere in client copy.
            assert PICK not in msg
            assert not [t for t in msg.split() if t.startswith("P-")], msg

    def test_a_manifest_with_nothing_to_show_sends_no_pick_request(
            self, tmp_path, monkeypatch):
        """Control: the same path, a manifest carrying neither a render path nor
        a description -- the engine must NOT ask for a pick nobody can make."""
        monkeypatch.setenv("PRESENTATION_STYLE_PICK_TIMEOUT_MINUTES", "0.005")
        monkeypatch.setattr(phases_mod.time, "sleep", lambda *_: None)
        sent = _stub_transport(monkeypatch)
        rd = _seed_run(tmp_path)
        (rd / "working" / "style-preview" / "style_samples_manifest.json").write_text(
            json.dumps({"schema": "style_samples_manifest/v1",
                        "variants": ["A", "B", "C"]}))
        (rd / "working" / "copy" / "style_preview_spec.json").unlink()
        eng = _engine(rd)
        rc = eng.run_phase(eng.manifest.phase_or_none(PICK))
        assert rc == EXIT_GATE_BLOCKED
        assert not [s for s in sent if s["kind"] == "ack"], sent
        assert any(e["kind"] == "phase.style_pick.samples_missing"
                   for e in eng.state["events"])

    def test_the_timeout_word_is_the_clients_own_sentence(self, tmp_path, monkeypatch):
        monkeypatch.setenv("PRESENTATION_STYLE_PICK_TIMEOUT_MINUTES", "0.005")
        monkeypatch.setattr(phases_mod.time, "sleep", lambda *_: None)
        sent = _stub_transport(monkeypatch)
        rd = _seed_run(tmp_path)
        eng = _engine(rd)
        eng.run_phase(eng.manifest.phase_or_none(PICK))
        blocked = [s for s in sent if s["kind"] == "blocked"]
        assert len(blocked) == 1, blocked
        assert blocked[0]["message"] == (
            "I still need your style pick (A, B or C). Nothing is lost — reply "
            "any time and I will pick right back up."), blocked[0]["message"]


def _seed_delivery(rd: Path, destinations, publish=None) -> None:
    ck = rd / "working" / "checkpoints"
    ck.mkdir(parents=True, exist_ok=True)
    (ck / "delivery_plan.json").write_text(json.dumps({"destinations": destinations}))
    # The bundle dir is pinned INSIDE the run dir so no fixture ever reads or
    # writes the home folder (resolve_bundle_dir's fallback is ~/Downloads).
    bundle = rd / "bundle"
    bundle.mkdir(parents=True, exist_ok=True)
    (ck / "process_manifest.json").write_text(json.dumps({"bundleDir": str(bundle)}))
    if publish is not None:
        (bundle / "teleprompter_publish.json").write_text(json.dumps(publish))


class TestDoneMessage:
    def test_lists_each_verified_destination_and_no_other(self, tmp_path):
        rd = _seed_run(tmp_path)
        _seed_delivery(rd, [
            {"type": "mac_downloads", "status": "verified",
             "verify_anchor": "/decks/demo/demo-FINAL.pptx"},
            {"type": "ghl", "status": "uploaded", "url": "https://example.test/not-yet"},
            {"type": "drive", "status": "verified", "url": "https://drive.test/abc"},
        ])
        msg = phases_mod._compose_done_message(rd)
        assert msg.startswith("Your presentation is ready. Here is where to find it:"), msg
        assert "mac_downloads: /decks/demo/demo-FINAL.pptx" in msg
        assert "drive: https://drive.test/abc" in msg
        assert "not-yet" not in msg, "an unverified destination must never be named"

    def test_no_verified_destination_sends_nothing_and_logs_the_withholding(
            self, tmp_path, monkeypatch):
        sent = _stub_transport(monkeypatch)
        rd = _seed_run(tmp_path)
        _seed_delivery(rd, [
            {"type": "ghl", "status": "uploaded", "url": "https://example.test/x"},
        ])
        assert phases_mod._compose_done_message(rd) == ""
        eng = _engine(rd)
        eng._send_done_message()
        assert not [s for s in sent if s["kind"] == "done"], sent
        withheld = [e for e in eng.state["events"]
                    if e["kind"] == "report.done_withheld"]
        assert len(withheld) == 1, eng.state["events"]

    def test_publish_record_warned_no_credentials_gives_the_sentence_and_no_address(
            self, tmp_path):
        """PD-210. The record's own public_url is set -- it was never verified
        live -- and it must not appear; only the sentence does."""
        rd = _seed_run(tmp_path)
        _seed_delivery(
            rd,
            [{"type": "mac_downloads", "status": "verified",
              "verify_anchor": "/decks/demo/demo-FINAL.pptx"}],
            publish={"status": "warned_no_credentials",
                     "public_url": "https://teleprompter.example/variant-a.html",
                     "verified_http_status": None})
        msg = phases_mod._compose_done_message(rd)
        assert phases_mod.TELEPROMPTER_NO_LINK_SENTENCE in msg, msg
        assert "teleprompter.example" not in msg, msg
        assert "/decks/demo/demo-FINAL.pptx" in msg

    def test_a_published_record_contributes_its_verified_link(self, tmp_path):
        """The control for the row above: the SAME fixture with status
        `published` and a live-verified 200 puts the link in the message."""
        rd = _seed_run(tmp_path)
        _seed_delivery(
            rd,
            [{"type": "mac_downloads", "status": "verified",
              "verify_anchor": "/decks/demo/demo-FINAL.pptx"}],
            publish={"status": "published",
                     "public_url": "https://teleprompter.example/variant-a.html",
                     "verified_http_status": 200})
        msg = phases_mod._compose_done_message(rd)
        assert "teleprompter: https://teleprompter.example/variant-a.html" in msg, msg
        assert phases_mod.TELEPROMPTER_NO_LINK_SENTENCE not in msg
