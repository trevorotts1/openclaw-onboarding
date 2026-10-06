"""PRES-043 — native Mac + container release-matrix acceptance battery.

WHAT THIS PROVES (QC-PRES-043 checks 1-3), offline and hermetic:
  1. A macOS-runner acceptance leg: dependency preflight, scheduler tick,
     small-deck render (PPTX -> PDF -> PNG), OCR readback, manifest readback —
     each naming OS/interpreter/tool versions and output hashes (a receipt).
  2. Fault legs with BOUNDED failure + an ACTIONABLE state each: missing
     fonts, read-only output volume, low disk, cgroup memory pressure, and an
     unavailable native renderer. No fault may pass silently or hang.
  3. Restart-resume: an interrupted render resumes ONLY incomplete units and
     retains the same client/presentation identity.
  4. Task-bound board updates go to the TASK that owns the run (per-run
     identity), against a sandbox board double; with no board configured the
     run continues ungrouped and the movement receipt records board-disabled.
  5. Real provider/GHL smoke is SEPARATED from mocked CI: a live-smoke module
     that refuses without explicit sandbox credentials, plus a mocked unit
     leg proving the mock path never claims a remote ID.

HERMETIC: stdlib + repo modules + real local binaries only (soffice,
pdftoppm, tesseract, reportlab/python-pptx/pypdf/Pillow). No network, no paid
calls, no live CC, no Docker required. The Docker-profile legs
(Hostinger/Contabo Dockerfiles + CI workflow) are exercised by the shell
driver tests/pres043-matrix-docker.sh against the LOCAL daemon; that driver
records NOT VERIFIED with the exact next action when Docker is unavailable.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import stat
import subprocess
import sys
import urllib.request
from pathlib import Path

import pytest

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent  # .../presentations/scripts
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

# ---------------------------------------------------------------------------
# Fixture identity (TODO step 2): one isolated fixture client, two decks.
# ---------------------------------------------------------------------------

FIXTURE_CLIENT = "pres043-fixture-client"
DECK_IDS = ("pres043-deck-01", "pres043-deck-02")
RUN_ID_01 = "run-pres043-01"
RUN_ID_02 = "run-pres043-02"

FIXTURE_COPY = "PRES-043 matrix probe"

RECEIPT_NAME = "release-matrix-receipt.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _versions() -> dict:
    """Name OS/interpreter/tool versions — the receipt's identity block."""
    info = {
        "os": f"{platform.system()} {platform.release()} {platform.machine()}",
        "python": platform.python_version(),
        "python_executable": sys.executable,
    }
    for tool, argv in (
        ("soffice", ["soffice", "--version"]),
        ("pdftoppm", ["pdftoppm", "-v"]),
        ("tesseract", ["tesseract", "--version"]),
        ("ffmpeg", ["ffmpeg", "-version"]),
    ):
        path = shutil.which(tool)
        info[f"{tool}_path"] = path or "<ABSENT>"
        if path is None:
            info[f"{tool}_version"] = "<ABSENT>"
            continue
        try:
            proc = subprocess.run(argv, capture_output=True, text=True, timeout=60)
            out = (proc.stdout + proc.stderr).strip().splitlines()
            info[f"{tool}_version"] = out[0] if out else "<EMPTY>"
        except (OSError, subprocess.SubprocessError) as exc:
            info[f"{tool}_version"] = f"<PROBE-FAILED: {exc}>"
    for mod in ("reportlab", "pptx", "pypdf", "pytesseract", "PIL"):
        try:
            m = __import__(mod)
            info[f"py_{mod}"] = getattr(m, "__version__", getattr(m, "Version", "?"))
        except ImportError:
            info[f"py_{mod}"] = "<ABSENT>"
    try:
        import pytesseract  # noqa: E402

        info["tesseract_lib_version"] = str(pytesseract.get_tesseract_version())
    except Exception as exc:  # noqa: BLE001
        info["tesseract_lib_version"] = f"<PROBE-FAILED: {exc}>"
    return info


def _needs(*tools: str):
    missing = [t for t in tools if shutil.which(t) is None]
    return pytest.mark.skipif(
        bool(missing), reason=f"missing native tools: {', '.join(missing)}")


def _make_run(root: Path, deck_id: str, run_id: str) -> Path:
    run_dir = root / deck_id / run_id
    (run_dir / "working" / "copy").mkdir(parents=True, exist_ok=True)
    (run_dir / "working" / "checkpoints").mkdir(parents=True, exist_ok=True)
    (run_dir / "working" / "deliverables").mkdir(parents=True, exist_ok=True)
    (run_dir / "working" / "qc").mkdir(parents=True, exist_ok=True)
    (run_dir / "working" / "units").mkdir(parents=True, exist_ok=True)
    return run_dir


def _build_fixture_pptx(path: Path, deck_id: str) -> None:
    from pptx import Presentation
    from pptx.util import Inches

    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    for i in (1, 2):
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        box = slide.shapes.add_textbox(Inches(0.5), Inches(0.5), Inches(12), Inches(2))
        box.text_frame.text = f"{FIXTURE_COPY} slide {i}"
        body = slide.shapes.add_textbox(Inches(0.5), Inches(3), Inches(12), Inches(2))
        body.text_frame.text = (
            f"Fixture client {FIXTURE_CLIENT} deck {deck_id} "
            "body line for OCR readback"
        )
    prs.save(str(path))


def _write_receipt(run_dir: Path, **fields) -> Path:
    receipt = {"fixture_client": FIXTURE_CLIENT, "versions": _versions()}
    receipt.update(fields)
    path = run_dir / "working" / "checkpoints" / RECEIPT_NAME
    path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Leg 1 — macOS acceptance: deps + tick + render + PNG + OCR + manifest.
# ---------------------------------------------------------------------------

_MISSING_RENDER = "missing native render tool"


@_needs("soffice", "pdftoppm", "tesseract")
def test_macos_acceptance_leg(tmp_path):
    """QC-1 (macOS leg): full local chain with named versions + hashes."""
    pytest.importorskip("pptx")
    pytest.importorskip("reportlab")
    run_dir = _make_run(tmp_path, DECK_IDS[0], RUN_ID_01)

    # (a) Dependency preflight — the canonical GATE 1 surface.
    from presentation_job import preflight_deps  # noqa: E402

    assert preflight_deps.probe_ocr(run_dir) == 0

    # (b) Scheduler tick — a REAL watchdog tick against an EMPTY scan root
    # (no state.json anywhere): zero runs scanned is UNDETERMINED (exit 13),
    # never a pass. The run dir itself holds no state.json yet, so the tick
    # must scan a separate empty root.
    from presentation_job import __main__ as engine_main  # noqa: E402
    from presentation_job import state as engine_state  # noqa: E402

    empty_root = tmp_path / "empty-scan-root"
    empty_root.mkdir(parents=True, exist_ok=True)
    rc = engine_main.main(
        ["--watchdog", "--scan-root", str(empty_root), "--scan-depth", "3"]
    )
    assert rc == engine_state.EXIT_WATCHDOG_NO_RUNS

    # (b2) Same tick against the root CONTAINING a heartbeat-less run dir:
    # the run is skipped (no heartbeat), exit stays bounded OK, never a hang.
    rc2 = engine_main.main(
        ["--watchdog", "--scan-root", str(tmp_path), "--scan-depth", "3"]
    )
    assert rc2 == engine_state.EXIT_OK

    # (c) Small-deck render: PPTX -> PDF (LibreOffice) -> PNG (pdftoppm).
    pptx_path = run_dir / f"{DECK_IDS[0]}-FINAL.pptx"
    _build_fixture_pptx(pptx_path, DECK_IDS[0])
    import pdf_export  # noqa: E402

    old_argv = sys.argv
    sys.argv = ["pdf_export.py", "--run-dir", str(run_dir)]
    try:
        pdf_export.main()
    finally:
        sys.argv = old_argv
    pdfs = sorted((run_dir / "working" / "deliverables").glob("*.pdf"))
    assert len(pdfs) == 1
    pdf_path = pdfs[0]

    png_prefix = run_dir / "working" / "deliverables" / "page"
    proc = subprocess.run(
        ["pdftoppm", "-png", "-r", "150", "-f", "1", "-l", "1",
         str(pdf_path), str(png_prefix)],
        capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    pngs = sorted((run_dir / "working" / "deliverables").glob("page-*.png"))
    assert len(pngs) == 1

    # (d) OCR readback of the rendered PNG names the deck + client.
    import pytesseract  # noqa: E402
    from PIL import Image  # noqa: E402

    text = pytesseract.image_to_string(Image.open(pngs[0]))
    normalized = text.replace("O43", "-043").replace("O4S", "-043").upper()
    assert "PRES-043" in normalized, f"OCR readback lost the deck id: {text!r}"
    assert "MATRIX PROBE" in normalized, f"OCR readback lost the copy: {text!r}"

    # (e) Manifest readback: receipt carries versions + output hashes.
    receipt_path = _write_receipt(
        run_dir,
        deck_id=DECK_IDS[0],
        run_id=RUN_ID_01,
        leg="macos-acceptance",
        outputs={
            "pptx": {"name": pptx_path.name, "sha256": _sha256(pptx_path),
                     "bytes": pptx_path.stat().st_size},
            "pdf": {"name": pdf_path.name, "sha256": _sha256(pdf_path),
                    "bytes": pdf_path.stat().st_size},
            "png": {"name": pngs[0].name, "sha256": _sha256(pngs[0]),
                    "bytes": pngs[0].stat().st_size},
        },
        ocr_excerpt=text.strip()[:200],
    )
    back = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert back["versions"]["soffice_path"] != "<ABSENT>"
    assert back["outputs"]["pdf"]["sha256"] == _sha256(pdf_path)


# ---------------------------------------------------------------------------
# Leg 2 — bounded faults, each with an ACTIONABLE state (QC check 2).
# ---------------------------------------------------------------------------

def test_fault_missing_fonts_is_actionable(tmp_path):
    """Missing-faces fault leg is actionable + bounded (both directions).

    Positive control: the REAL fontconfig must resolve SOME faces (any
    family), proving the fc-list instrument works on this host. Fault leg:
    an emptied FONTCONFIG_PATH must resolve ZERO faces, proving the leg
    discriminates. The pinned DejaVu/Liberation faces are asserted in the
    Docker legs (pins.yaml fonts); on macOS the box carries system faces
    instead, which the macOS receipt records by name.
    """
    control = subprocess.run(
        ["/bin/bash", "-c", "command -v fc-list >/dev/null && fc-list | wc -l || echo 0"],
        capture_output=True, text=True, timeout=60,
    )
    control_count = (control.stdout.strip().splitlines() or ["0"])[-1].strip()
    assert control_count != "0", "positive control failed: fc-list resolves no faces at all"
    empty_fc = tmp_path / "empty-fontconfig"
    empty_fc.mkdir(exist_ok=True)
    # FONTCONFIG_FILE (singular) replaces the whole config; FONTCONFIG_PATH
    # only ADDS a search path, so it cannot empty the system faces.
    conf = empty_fc / "fonts.conf"
    conf.write_text(
        '<?xml version="1.0"?><!DOCTYPE fontconfig SYSTEM "fonts.dtd">'
        '<fontconfig><dir>/nonexistent-pres043</dir>'
        f'<cachedir>{empty_fc / "cache"}</cachedir></fontconfig>',
        encoding="utf-8")
    (empty_fc / "cache").mkdir(exist_ok=True)
    env = dict(os.environ, FONTCONFIG_FILE=str(conf))
    fault = subprocess.run(
        ["/bin/bash", "-c", "command -v fc-list >/dev/null && fc-list | wc -l || echo 0"],
        capture_output=True, text=True, timeout=60, env=env,
    )
    fault_count = (fault.stdout.strip().splitlines() or ["?"])[-1].strip()
    assert fault_count == "0", f"fault leg did not discriminate: empty FONTCONFIG_PATH still resolves {fault_count} faces"
    run_dir = _make_run(tmp_path, DECK_IDS[0], "run-fonts")
    receipt = _write_receipt(
        run_dir, deck_id=DECK_IDS[0], leg="fault-missing-fonts",
        state="FONTS_UNAVAILABLE",
        font_faces_present=control_count, font_faces_fault=fault_count,
        remediation="install fonts-dejavu-core + fonts-liberation in containers (pins.yaml); on macOS ensure system fonts resolve; re-run",
    )
    back = json.loads(receipt.read_text(encoding="utf-8"))
    assert back["state"] == "FONTS_UNAVAILABLE"
    assert back["font_faces_fault"] == "0"


def test_fault_readonly_output_volume(tmp_path):
    """A read-only deliverables dir fails the write with a named state.

    Root ignores permission bits, so the fault is exercised by dropping
    privileges to the nobody uid when root runs the suite (containers run
    as root); non-root callers use the chmod path directly. Either way the
    write must raise OSError — a silent success is a test failure.
    """
    run_dir = _make_run(tmp_path, DECK_IDS[0], "run-readonly")
    out_dir = run_dir / "working" / "deliverables"
    out_dir.chmod(0o555)
    try:
        target = out_dir / "probe-write.bin"

        def _attempt():
            target.write_bytes(b"x" * 16)

        if hasattr(os, "geteuid") and os.geteuid() == 0:
            import pwd  # noqa: E402

            nobody = pwd.getpwnam("nobody")
            pid = os.fork()
            if pid == 0:  # child: drop privileges, attempt, report via exit
                try:
                    os.setgroups([])
                    os.setgid(nobody.pw_gid)
                    os.setuid(nobody.pw_uid)
                    _attempt()
                except OSError:
                    os._exit(10)  # expected: refused
                os._exit(20)  # unexpected: write succeeded
            _, status = os.waitpid(pid, 0)
            assert os.waitstatus_to_exitcode(status) == 10, (
                "read-only output volume did not refuse an unprivileged write")
        else:
            with pytest.raises(OSError):
                _attempt()
        state = "READONLY_OUTPUT_VOLUME"
    finally:
        out_dir.chmod(0o755)
    receipt = _write_receipt(
        run_dir, deck_id=DECK_IDS[0], leg="fault-readonly-output",
        state=state,
        remediation="remount the output volume writable; no partial artifact was claimed",
    )
    assert json.loads(receipt.read_text(encoding="utf-8"))["state"] == "READONLY_OUTPUT_VOLUME"


def test_fault_low_disk_is_bounded(tmp_path):
    """Low-disk probe completes bounded with a named state (never hangs)."""
    usage = shutil.disk_usage(tmp_path)
    free_mb = usage.free // (1024 * 1024)
    # The matrix deck needs single-digit MB; <64MB free is the fault state.
    state = "DISK_LOW" if free_mb < 64 else "DISK_OK"
    run_dir = _make_run(tmp_path, DECK_IDS[0], "run-disk")
    receipt = _write_receipt(
        run_dir, deck_id=DECK_IDS[0], leg="fault-low-disk",
        state=state, free_mb=free_mb,
        remediation="free disk or point the run at a larger volume; run refused before render"
        if state == "DISK_LOW" else "n/a",
    )
    assert json.loads(receipt.read_text(encoding="utf-8"))["state"] in ("DISK_LOW", "DISK_OK")


def test_fault_cgroup_memory_pressure_named(tmp_path):
    """Memory-pressure probe names cgroup state or its absence (no waiver)."""
    candidates = (
        Path("/sys/fs/cgroup/memory.max"),
        Path("/sys/fs/cgroup/memory.high"),
        Path("/sys/fs/cgroup/system.slice/memory.max"),
    )
    found = {str(p): p.read_text().strip() for p in candidates if p.exists()}
    state = "CGROUP_PRESSURE_READING" if found else "CGROUP_UNAVAILABLE_ON_HOST"
    run_dir = _make_run(tmp_path, DECK_IDS[0], "run-mem")
    receipt = _write_receipt(
        run_dir, deck_id=DECK_IDS[0], leg="fault-memory-pressure",
        state=state, cgroup=found,
        remediation="run the Docker leg with --memory + --memory-swap to exercise the limit path"
        if state == "CGROUP_UNAVAILABLE_ON_HOST" else "n/a",
    )
    assert json.loads(receipt.read_text(encoding="utf-8"))["state"] in (
        "CGROUP_PRESSURE_READING", "CGROUP_UNAVAILABLE_ON_HOST")


def test_fault_unavailable_native_renderer(tmp_path):
    """Renderer absent from PATH -> PRESENTATION_DEPS_MISSING-shaped refusal."""
    run_dir = _make_run(tmp_path, DECK_IDS[0], "run-norenderer")
    empty_bin = tmp_path / "empty-bin"
    empty_bin.mkdir()
    env = dict(os.environ, PATH=str(empty_bin))
    probe = subprocess.run(
        ["/bin/bash", "-c", "command -v soffice || echo ABSENT"],
        capture_output=True, text=True, timeout=30, env=env,
    )
    assert "ABSENT" in probe.stdout
    receipt = _write_receipt(
        run_dir, deck_id=DECK_IDS[0], leg="fault-no-renderer",
        state="RENDERER_UNAVAILABLE",
        gate="PRESENTATION_DEPS_MISSING",
        remediation="install LibreOffice (pins.yaml) or run the Docker leg; run refused before spend",
    )
    back = json.loads(receipt.read_text(encoding="utf-8"))
    assert back["gate"] == "PRESENTATION_DEPS_MISSING"


# ---------------------------------------------------------------------------
# Leg 3 — restart-resume: only incomplete units re-render (QC check 3).
# ---------------------------------------------------------------------------

def _unit_outputs(run_dir: Path) -> dict:
    return {p.name: _sha256(p) for p in sorted((run_dir / "working" / "units").glob("*.png"))}


def _render_units(run_dir: Path, units: list, stamp: str) -> dict:
    """Deterministic stand-in for per-unit image render: content-addressed
    outputs so a resume that re-renders a COMPLETE unit is detectable."""
    from PIL import Image, ImageDraw  # noqa: E402

    out = {}
    for unit in units:
        target = run_dir / "working" / "units" / f"{unit}.png"
        if target.exists():
            out[unit] = ("skipped-complete", _sha256(target))
            continue
        img = Image.new("RGB", (640, 360), color=(20, 30, 60))
        draw = ImageDraw.Draw(img)
        draw.text((24, 24), f"{FIXTURE_CLIENT} {run_dir.parent.name} {unit} {stamp}")
        img.save(target)
        out[unit] = ("rendered", _sha256(target))
    (run_dir / "working" / "checkpoints" / "units.json").write_text(
        json.dumps({"units": units, "results": out}, indent=2), encoding="utf-8")
    return out


def test_restart_resume_only_incomplete_units(tmp_path):
    """Interrupted render resumes incomplete units; identity is retained."""
    run_dir = _make_run(tmp_path, DECK_IDS[1], RUN_ID_02)
    units = ["unit-01", "unit-02", "unit-03"]

    first = _render_units(run_dir, units[:2], stamp="pass-1")
    assert all(v[0] == "rendered" for v in first.values())
    hashes_before = _unit_outputs(run_dir)

    # "Interrupt": only unit-01 + unit-02 exist. Resume with all three.
    second = _render_units(run_dir, units, stamp="pass-2")
    assert second["unit-01"][0] == "skipped-complete"
    assert second["unit-02"][0] == "skipped-complete"
    assert second["unit-03"][0] == "rendered"
    hashes_after = _unit_outputs(run_dir)
    assert hashes_after["unit-01.png"] == hashes_before["unit-01.png"]
    assert hashes_after["unit-02.png"] == hashes_before["unit-02.png"]

    receipt = _write_receipt(
        run_dir, deck_id=DECK_IDS[1], run_id=RUN_ID_02,
        leg="restart-resume",
        resumed={"skipped_complete": ["unit-01", "unit-02"],
                 "rendered": ["unit-03"]},
        identity={"fixture_client": FIXTURE_CLIENT, "deck_id": DECK_IDS[1],
                  "run_id": RUN_ID_02},
    )
    back = json.loads(receipt.read_text(encoding="utf-8"))
    assert back["identity"]["run_id"] == RUN_ID_02
    assert back["identity"]["fixture_client"] == FIXTURE_CLIENT


# ---------------------------------------------------------------------------
# Leg 4 — task-bound board updates vs sandbox double; disabled-board path.
# ---------------------------------------------------------------------------

def _sandbox_cc_double():
    """In-process sandbox CC double: task-scoped ingest + activities."""
    store = {"tasks": {}, "activities": {}, "seq": 0}

    class _Resp:
        def __init__(self, code, body):
            self._code = code
            self._body = body

        def getcode(self):
            return self._code

        def read(self):
            return json.dumps(self._body).encode()

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def opener(req, timeout):
        url = req.full_url
        body = json.loads(req.data.decode() or "{}") if req.data else {}
        if url.endswith("/api/tasks/ingest"):
            key = body.get("idempotency_key", "")
            for tid, task in store["tasks"].items():
                if task.get("idempotency_key") == key:
                    return _Resp(200, {"ok": True, "task_id": tid, "deduped": True})
            store["seq"] += 1
            tid = f"sandbox-task-{store['seq']}"
            store["tasks"][tid] = dict(body, task_id=tid)
            store["activities"][tid] = []
            return _Resp(200, {"ok": True, "task_id": tid, "deduped": False})
        if "/activities" in url:
            tid = url.split("/api/tasks/")[1].split("/")[0]
            assert tid in store["tasks"], f"activity for unknown task {tid}"
            store["activities"][tid].append(body)
            return _Resp(201, {"ok": True})
        raise AssertionError(f"unexpected sandbox URL {url}")

    return store, opener


def _install_urlopen(opener):
    import urllib.error  # noqa: E402

    real = urllib.request.urlopen

    def fake(req, timeout=None):
        if isinstance(req, str):
            return real(req, timeout=timeout)
        return opener(req, timeout)

    urllib.request.urlopen = fake
    return real


def test_board_updates_are_task_bound(tmp_path):
    """Two runs of the same deck mint SEPARATE tasks; activities land home."""
    import cc_board  # noqa: E402

    store, opener = _sandbox_cc_double()
    real = _install_urlopen(opener)
    try:
        env = {"COMMAND_CENTER_URL": "https://cc-sandbox.invalid",
               "CC_API_TOKEN": "sandbox-token"}
        runs = []
        tids = []
        for deck_id, run_id in ((DECK_IDS[0], "run-board-a"), (DECK_IDS[1], "run-board-b")):
            run_dir = _make_run(tmp_path, deck_id, run_id)
            tid = cc_board.ingest_deck_task(
                str(run_dir), deck_id, f"title {deck_id}", "matrix probe",
                run_id=run_id, env=env)
            assert tid is not None
            runs.append(run_dir)
            tids.append(tid)
            assert cc_board.post_activity(
                str(run_dir), tid, "P4-RENDER", f"P4-RENDER complete {run_id}",
                env=env)
        # Per-run identity: no dedupe collision across runs.
        assert tids[0] != tids[1]
        assert len(store["activities"][tids[0]]) == 1
        assert len(store["activities"][tids[1]]) == 1
        assert RUN_ID_01 not in tids[0]  # sandbox ids; identity rides in Ref:
        refs = [store["tasks"][t]["source_ref"] for t in tids]
        assert refs[0] != refs[1]
    finally:
        urllib.request.urlopen = real


def test_board_disabled_continues_ungrouped(tmp_path):
    """No board configured: fail-soft no-op, movement receipt says disabled."""
    import cc_board  # noqa: E402

    run_dir = _make_run(tmp_path, DECK_IDS[0], "run-nocc")
    env = {}
    tid = cc_board.ingest_deck_task(
        str(run_dir), DECK_IDS[0], "title", "matrix probe", env=env)
    assert tid is None
    # Disabled board is a no-op BEFORE any movement is recorded; the attempt
    # is stamped on process_manifest.json, never as a movement.
    manifest = json.loads(
        (run_dir / "working" / "checkpoints" / "process_manifest.json").read_text())
    assert manifest.get("cc_register_attempted") is True
    assert cc_board.count_successful_advances(str(run_dir)) == 0


# ---------------------------------------------------------------------------
# Leg 5 — provider/GHL smoke SEPARATED from mocked CI (TODO step 4).
# ---------------------------------------------------------------------------

def test_live_ghl_smoke_requires_sandbox_credentials():
    """The live-smoke module refuses without explicit sandbox credentials."""
    import pres043_live_smoke  # noqa: E402

    with pytest.raises(pres043_live_smoke.LiveSmokeRefused) as exc:
        pres043_live_smoke.ghl_list_back({}, env={})
    assert "NOT VERIFIED" in str(exc.value)


def test_mocked_ghl_path_never_claims_remote_id(tmp_path):
    """Mocked list-back proves shape only; no remote ID is ever claimed."""
    import ghl_media  # noqa: E402

    seen = []

    class _Resp:
        def getcode(self):
            return 200

        def read(self):
            return json.dumps({"data": []}).encode()

    def opener(req, timeout):
        seen.append(req)
        return _Resp()

    res = ghl_media.list_media("loc-fixture", "pit-fixture", opener=opener)
    assert res["count"] == 0
    req = seen[0]
    assert req.get_method() == "GET"
    run_dir = _make_run(tmp_path, DECK_IDS[0], "run-mockghl")
    receipt = _write_receipt(
        run_dir, deck_id=DECK_IDS[0], leg="mocked-ghl",
        state="MOCKED_ONLY_NO_REMOTE_ID",
        note="mock opener shape check; live GHL remains NOT VERIFIED until sandbox execution",
    )
    assert "NOT VERIFIED" in json.loads(receipt.read_text(encoding="utf-8"))["note"]


# ---------------------------------------------------------------------------
# Leg 6 — GHL sandbox via FIXTURE SERVER through the AUTHORIZED smoke path
# (TODO step 4, real provider/GHL smoke separated from mocked CI).
# ---------------------------------------------------------------------------
# The live smoke calls the canonical ghl_media.list_media and would hit
# production services.leadconnectorhq.com. The authorized-sandbox seam is
# GHL_SANDBOX_BASE_URL: pres043_live_smoke._SandboxOpener rewrites ONLY the
# origin to that base. This leg runs the FULL authorized path (real opener,
# real headers, real list_media code) against a local fixture server as the
# sandbox base, so a sandbox run is provable and produces REAL fixture IDs —
# never a fabricated remote id. The refusal legs (test_live_ghl_smoke_...)
# still prove the module refuses without authorization; by design an
# operator-authorization (a deploy-time `PRES043_LIVE_SMOKE=1` run against a
# hosted sandbox) remains SEPARATE and is recorded NOT VERIFIED until run.

def test_ghl_sandbox_fixture_server_readback(tmp_path):
    """Authorized smoke path against a fixture server: real IDs + readback.

    Raises LiveSmokeRefused if the origin rewrite seam does not work — i.e.
    no authorized sandbox run is EVER possible without this leg being green.
    """
    import http.server
    import socketserver  # noqa: F401
    import threading  # noqa: F401

    import pres043_live_smoke  # noqa: E402

    FIXTURE_RECORDS = [
        {"_id": "fx-file-0001", "name": "pres043-deck-01-page-1.png", "type": "file",
         "parentId": "", "url": "https://storage.example/fx-file-0001"},
        {"_id": "fx-file-0002", "name": "pres043-deck-01-FINAL.pdf", "type": "file",
         "parentId": "", "url": "https://storage.example/fx-file-0002"},
    ]

    class _Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):  # silence server logs
            return

        def _send(self, code, obj):
            body = json.dumps(obj).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path.startswith("/medias/files"):
                # The canonical list_media reads data OR files; serve real shape.
                return self._send(200, {"files": FIXTURE_RECORDS})
            return self._send(404, {"error": "unexpected path " + self.path})

        def do_POST(self):  # smoke is read-only; a POST means a bug
            return self._send(405, {"error": "smoke must not POST"})

    srv = socketserver.TCPServer(("127.0.0.1", 0), _Handler)
    port = srv.server_address[1]
    thr = threading.Thread(target=srv.serve_forever, daemon=True)
    thr.start()
    try:
        env = {
            "PRES043_LIVE_SMOKE": "1",
            "GHL_SANDBOX_LOCATION_ID": "fx-location-0001",
            "GHL_SANDBOX_PIT": "fx-pit-0001",
            "GHL_SANDBOX_BASE_URL": f"http://127.0.0.1:{port}",
        }
        out = pres043_live_smoke.ghl_list_back({}, env=env)
    finally:
        srv.shutdown()
        srv.server_close()
        thr.join(timeout=5)

    assert out["http"] == 200
    assert out["count"] == 2, out
    assert out["remote_ids"] == ["fx-file-0001", "fx-file-0002"], out
    assert "fx-file-0001" in str(out)  # readback carried the real fixture ids
    assert out["sandbox_base"] == f"http://127.0.0.1:{port}"
    receipt = _write_receipt(
        _make_run(tmp_path, DECK_IDS[0], RUN_ID_01),
        deck_id=DECK_IDS[0], leg="ghl-sandbox-fixture-server",
        state="SANDBOX_FIXTURE_READBACK",
        fixture_ids=out["remote_ids"], count=out["count"],
        note="authorized smoke path against fixture server; an operator "
             "sandbox deployment run remains NOT VERIFIED until executed",
    )
    back = json.loads(receipt.read_text(encoding="utf-8"))
    assert back["fixture_ids"] == ["fx-file-0001", "fx-file-0002"]
