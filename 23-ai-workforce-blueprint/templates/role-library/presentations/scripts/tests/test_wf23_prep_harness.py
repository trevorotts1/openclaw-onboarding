"""WF23 prep harness self-tests TEMPLATE (W6 WF23 prep, NOT acceptance).

WHAT THIS IS. Hermetic integrity checks over the WF23 prep fixtures
(tests/fixtures/wf23/): synthetic companies + presentations load and cohere,
the three adapter-readiness probes discriminate (positive control passes,
negative control fails on the same instrument), the pause/resume harness
round-trips without repeats, the render/visual-QC hooks emit PASS on good
input and PENDING (never a pass) on bad input, the matrix stubs never claim
PASS, and the fixture tree carries no secret patterns.

WHAT THIS IS NOT. This is prep scaffolding on ONB base 2244b00fe. It does
NOT run the engine, the renderer, any provider, any real gateway, any host
matrix leg, or any live Command Center / GoHighLevel resource. It cannot
and does not count as QC-PRES-055 acceptance, which per HOW-TO-EXECUTE.md
requires the completed W5 candidate (frozen package + installed consumer +
scoped authorized resources) rerun from fresh input.

Hermetic: tempfile/JSON/localhost-only HTTP/subprocess of the fixture
scripts. No outbound network, no engine, no paid calls.

Run:  python3 tests/test_wf23_prep_harness.py
      python3 -m pytest tests/test_wf23_prep_harness.py -q
"""
from __future__ import annotations

import json
import os
import re
import stat
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_FIXDIR = _HERE / "fixtures" / "wf23"
_SCRIPTS = _HERE.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
if str(_FIXDIR / "harness") not in sys.path:
    sys.path.insert(0, str(_FIXDIR / "harness"))

from presentation_job.vocab import normalize_presentation_type  # noqa: E402

COMPANIES = _FIXDIR / "companies.json"
PRESENTATIONS = _FIXDIR / "presentations.json"
BRIEFS = _FIXDIR / "intake_briefs.json"
MATRIX = _FIXDIR / "matrix.json"
NEGCTRL = _FIXDIR / "negative_control.json"
SCOPED = _FIXDIR / "scoped_resources.json"
DECK10 = _FIXDIR / "decks" / "syn_deck_10.json"
PROBE_GW = _FIXDIR / "probes" / "probe_openclaw_gateway.py"
PROBE_SKILL = _FIXDIR / "probes" / "probe_skill_invocation.py"
PROBE_STANDALONE = _FIXDIR / "probes" / "probe_standalone.py"
RENDER_HOOK = _FIXDIR / "hooks" / "render_hook.py"
VISUAL_HOOK = _FIXDIR / "hooks" / "visual_qc_hook.py"
MATRIX_SCRIPTS = {
    "mac-native": _FIXDIR / "matrix" / "mac-native.sh",
    "hostinger-docker": _FIXDIR / "matrix" / "hostinger-docker.sh",
    "contabo-docker": _FIXDIR / "matrix" / "contabo-docker.sh",
}

import pause_resume as pr  # noqa: E402


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _run(argv: list, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(argv, capture_output=True, text=True, timeout=60, **kw)


# ---------------------------------------------------------------------------
# 1. Fixtures load and cohere
# ---------------------------------------------------------------------------

def test_companies_two_distinct_synthetic():
    doc = _load(COMPANIES)
    assert doc.get("synthetic") is True
    cos = doc["companies"]
    assert len(cos) == 2
    ids = [c["company_id"] for c in cos]
    assert len(set(ids)) == 2
    assert all(i.startswith("SYN-") for i in ids)
    assert len({c["workspace"] for c in cos}) == 2
    for c in cos:
        assert c["contact"].endswith("@example.invalid")


def test_presentations_variants_two_in_one_company():
    doc = _load(PRESENTATIONS)
    assert doc.get("synthetic") is True
    pres = doc["presentations"]
    company_ids = {c["company_id"] for c in _load(COMPANIES)["companies"]}
    for p in pres:
        assert p["company_id"] in company_ids
        normalize_presentation_type(p["presentation_type"])  # canonical only
    in_acme = [p for p in pres if p["company_id"] == "SYN-CO-ACME-01"]
    assert len(in_acme) == 2  # HOST-ACCEPTANCE step-2 shape
    kinds = {(p["deliverables"]["sales_checkout"], p["deliverables"]["vsl_page"])
             for p in pres}
    assert (False, False) in kinds  # deck-only
    assert (True, True) in kinds  # deck + sales + VSL


def test_intake_briefs_cover_every_presentation():
    pres_ids = {p["presentation_id"] for p in _load(PRESENTATIONS)["presentations"]}
    briefs = _load(BRIEFS)["briefs"]
    assert {b["presentation_id"] for b in briefs} == pres_ids
    for b in briefs:
        normalize_presentation_type(b["answers"]["presentation_type"])
        assert b["answers"]["goal"] and b["answers"]["cta_action"]


def test_matrix_enumerates_hosts_installs_ops_not_run():
    doc = _load(MATRIX)
    assert set(doc["hosts"]) == {"claude-code", "claude-nine", "openclaw"}
    assert {i["id"] for i in doc["installs"]} == {
        "mac-native", "hostinger-docker", "contabo-docker"}
    assert set(doc["ops"]) == {"fresh", "upgrade", "restart"}
    assert "NOT-RUN" in doc["note"]


def test_scoped_resources_are_placeholders_only():
    doc = _load(SCOPED)
    assert doc.get("synthetic") is True
    blob = json.dumps(doc)
    assert "PLACEHOLDER" in blob
    assert "example.invalid" in doc["command_center"]["base_url"]


# ---------------------------------------------------------------------------
# 2. Gateway probe discriminates (same instrument, both directions)
# ---------------------------------------------------------------------------

class _Handler(BaseHTTPRequestHandler):
    token_required: str | None = None

    def do_GET(self):
        if self.path != "/wf23-prep-probe":
            self.send_response(404)
            self.end_headers()
            return
        if _Handler.token_required is not None:
            got = self.headers.get("Authorization", "")
            if got != f"Bearer {_Handler.token_required}":
                self.send_response(401)
                self.end_headers()
                return
        body = b'{"ok": true}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


def _serve(token_required=None):
    _Handler.token_required = token_required
    srv = HTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def _closed_port() -> int:
    import socket
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_gateway_probe_positive_passes():
    srv = _serve()
    try:
        url = f"http://127.0.0.1:{srv.server_port}"
        r = _run([sys.executable, str(PROBE_GW), "--url", url])
        assert r.returncode == 0, r.stderr
        assert json.loads(r.stdout)["status"] == "READY"
    finally:
        srv.shutdown()


def test_gateway_probe_dead_port_fails_live_process_control():
    # Negative control: THIS process is alive, but nothing listens on the
    # probe port. A PID-aliveness check would false-pass; the listening
    # check must report NOT-READY. Mirrors fixtures/wf23/negative_control.json.
    neg = _load(NEGCTRL)
    assert neg["expect"]["status"] == "NOT-READY"
    url = neg["gateway_url_template"].format(closed_port=_closed_port())
    r = _run([sys.executable, str(PROBE_GW), "--url", url,
              "--path", neg["gateway_path"]])
    assert r.returncode == 2, r.stdout
    assert json.loads(r.stdout)["status"] == "NOT-READY"


def test_gateway_probe_wrong_token_fails_auth():
    srv = _serve(token_required="syn-token-1")
    try:
        url = f"http://127.0.0.1:{srv.server_port}"
        r = _run([sys.executable, str(PROBE_GW), "--url", url,
                  "--token", "wrong-token"])
        assert r.returncode == 2, r.stdout
        assert "auth" in json.loads(r.stdout)["reason"]
        ok = _run([sys.executable, str(PROBE_GW), "--url", url,
                   "--token", "syn-token-1"])
        assert ok.returncode == 0, ok.stderr
    finally:
        srv.shutdown()


# ---------------------------------------------------------------------------
# 3. Skill-invocation and standalone probes discriminate
# ---------------------------------------------------------------------------

def _skill_tree(tmp_path: Path, *, with_md=True, md_empty=False,
                with_entry=True, entry_exec=True) -> tuple[Path, Path]:
    skills = tmp_path / "skills"
    entry = tmp_path / "presentation-canonical-entry.sh"
    if with_md:
        md = skills / "claude-code" / "SKILL.md"
        md.parent.mkdir(parents=True)
        md.write_text("", encoding="utf-8") if md_empty else md.write_text(
            "# Synthetic skill surface\n", encoding="utf-8")
    if with_entry:
        entry.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
        if entry_exec:
            entry.chmod(entry.stat().st_mode | stat.S_IXUSR)
    return skills, entry


def test_skill_probe_positive_passes(tmp_path):
    skills, entry = _skill_tree(tmp_path)
    r = _run([sys.executable, str(PROBE_SKILL), "--skill", "claude-code",
              "--skills-dir", str(skills), "--entry", str(entry)])
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["status"] == "READY"


def test_skill_probe_missing_surface_fails(tmp_path):
    skills, entry = _skill_tree(tmp_path, with_md=False)
    r = _run([sys.executable, str(PROBE_SKILL), "--skill", "claude-code",
              "--skills-dir", str(skills), "--entry", str(entry)])
    assert r.returncode == 2
    assert json.loads(r.stdout)["status"] == "NOT-READY"
    skills2, entry2 = _skill_tree(tmp_path / "b", entry_exec=False)
    r2 = _run([sys.executable, str(PROBE_SKILL), "--skill", "claude-nine",
               "--skills-dir", str(skills2), "--entry", str(entry2)])
    assert r2.returncode == 2
    assert json.loads(r2.stdout)["status"] == "NOT-READY"


def test_standalone_probe_needs_no_gateway(tmp_path):
    pkg = tmp_path / "pkg"
    (pkg / "presentation_job").mkdir(parents=True)
    (pkg / "presentation_job" / "__init__.py").write_text("# prep\n")
    env = dict(os.environ)
    env["OPENCLAW_GATEWAY_URL"] = "http://127.0.0.1:9"
    r = _run([sys.executable, str(PROBE_STANDALONE),
              "--package-dir", str(pkg)], env=env)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["status"] == "READY"
    r2 = _run([sys.executable, str(PROBE_STANDALONE),
               "--package-dir", str(tmp_path / "empty")], env=env)
    assert r2.returncode == 2
    assert json.loads(r2.stdout)["status"] == "NOT-READY"


# ---------------------------------------------------------------------------
# 4. Pause/resume harness: round-trip, identity, no repeats
# ---------------------------------------------------------------------------

def test_pause_resume_roundtrip_no_repeats(tmp_path):
    ckpt = tmp_path / "run" / "checkpoint.json"
    answers = {"presentation_type": "from_scratch", "goal": "synthetic"}
    units = ["P1-INTAKE", "P2-COPY"]
    pr.save_checkpoint(ckpt, presentation_id="SYN-PRES-ACME-DECK-01",
                       company_id="SYN-CO-ACME-01", answers=answers,
                       completed_units=units, revision=2)
    back = pr.load_checkpoint(ckpt, presentation_id="SYN-PRES-ACME-DECK-01",
                              company_id="SYN-CO-ACME-01", min_revision=2)
    assert back["answers"] == answers
    assert back["completed_units"] == units  # resume continues, never redoes
    assert back["revision"] == 2


def test_pause_resume_rejects_mismatch_rollback_missing(tmp_path):
    import pytest
    ckpt = tmp_path / "c.json"
    pr.save_checkpoint(ckpt, presentation_id="SYN-PRES-ACME-DECK-01",
                       company_id="SYN-CO-ACME-01", answers={}, completed_units=[])
    with pytest.raises(pr.CheckpointError, match="company_id mismatch"):
        pr.load_checkpoint(ckpt, company_id="SYN-CO-BLUE-02")
    with pytest.raises(pr.CheckpointError, match="presentation_id mismatch"):
        pr.load_checkpoint(ckpt, presentation_id="SYN-PRES-BLUE-VSL-01")
    with pytest.raises(pr.CheckpointError, match="revision rollback"):
        pr.load_checkpoint(ckpt, min_revision=99)
    with pytest.raises(pr.CheckpointError, match="missing"):
        pr.load_checkpoint(tmp_path / "nope.json")


# ---------------------------------------------------------------------------
# 5. Render / visual-QC hooks: PASS on good, PENDING (never pass) on bad
# ---------------------------------------------------------------------------

def test_render_hook_pass_and_pending(tmp_path):
    out = tmp_path / "render-receipt.json"
    r = _run([sys.executable, str(RENDER_HOOK),
              "--deck", str(DECK10), "--out", str(out)])
    assert r.returncode == 0, r.stderr
    assert json.loads(out.read_text())["status"] == "PASS"
    bad = tmp_path / "bad.json"
    deck = json.loads(DECK10.read_text())
    deck.append({"slide": 10, "scene": "dup ordinal", "copy": "dup"})
    bad.write_text(json.dumps(deck))
    out2 = tmp_path / "render-bad.json"
    r2 = _run([sys.executable, str(RENDER_HOOK),
               "--deck", str(bad), "--out", str(out2)])
    assert r2.returncode == 2
    assert json.loads(out2.read_text())["status"] == "PENDING"


def test_visual_qc_hook_pass_and_pending(tmp_path):
    good = tmp_path / "art"
    good.mkdir()
    (good / "s01.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 64)
    out = tmp_path / "vq.json"
    r = _run([sys.executable, str(VISUAL_HOOK),
              "--artifacts-dir", str(good), "--out", str(out)])
    assert r.returncode == 0, r.stderr
    assert json.loads(out.read_text())["status"] == "PASS"
    empty = tmp_path / "empty"
    empty.mkdir()
    out2 = tmp_path / "vq2.json"
    r2 = _run([sys.executable, str(VISUAL_HOOK),
               "--artifacts-dir", str(empty), "--out", str(out2)])
    assert r2.returncode == 2
    assert json.loads(out2.read_text())["status"] == "PENDING"
    (good / "s02.png").write_bytes(b"not a png")
    out3 = tmp_path / "vq3.json"
    r3 = _run([sys.executable, str(VISUAL_HOOK),
               "--artifacts-dir", str(good), "--out", str(out3)])
    assert r3.returncode == 2
    assert json.loads(out3.read_text())["status"] == "PENDING"


# ---------------------------------------------------------------------------
# 6. Matrix stubs never claim PASS; fixture tree carries no secrets
# ---------------------------------------------------------------------------

def test_matrix_stubs_report_not_run_never_pass():
    for leg_id, script in MATRIX_SCRIPTS.items():
        assert script.is_file(), f"missing matrix stub {leg_id}"
        assert os.access(script, os.X_OK), f"stub not executable {leg_id}"
        for op in ("fresh", "upgrade", "restart"):
            r = _run(["bash", str(script), op])
            assert r.returncode == 3, f"{leg_id}/{op}: {r.stdout}"
            assert "NOT-RUN" in r.stdout, f"{leg_id}/{op}: {r.stdout}"
            assert "PASS" not in r.stdout.split("NOT-RUN")[0]
            assert "\nPASS" not in r.stdout and "status=PASS" not in r.stdout


SECRET_PATTERNS = (
    r"sk-(live|test)-[A-Za-z0-9]{8,}",
    r"ghp_[A-Za-z0-9]{8,}",
    r"github_pat_[A-Za-z0-9_]{8,}",
    r"AIza[0-9A-Za-z_-]{10,}",
    r"AKIA[0-9A-Z]{16}",
    r"xox[bap]-[A-Za-z0-9-]{6,}",
    r"-----BEGIN [A-Z ]*PRIVATE KEY",
)


def test_fixture_tree_carries_no_secret_patterns():
    offenders = []
    for path in sorted(_FIXDIR.rglob("*")):
        if not path.is_file() or path.suffix == ".md":
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for pat in SECRET_PATTERNS:
            if re.search(pat, text):
                offenders.append(f"{path.name}: {pat}")
    assert not offenders, f"secret-like patterns in prep fixtures: {offenders}"


if __name__ == "__main__":
    names = [n for n in sorted(globals()) if n.startswith("test_")]
    import tempfile
    failures = []
    for name in names:
        fn = globals()[name]
        try:
            if "tmp_path" in fn.__code__.co_varnames:
                with tempfile.TemporaryDirectory() as td:
                    fn(Path(td))
            else:
                fn()
            print(f"ok - {name}")
        except Exception as exc:  # noqa: BLE001
            failures.append(name)
            print(f"FAIL - {name}: {exc}")
    print(f"{len(names) - len(failures)}/{len(names)} self-tests passed")
    sys.exit(1 if failures else 0)
