"""PD-107 — the operator-contract path declares itself.

Rows (01-BUILD-SPEC.md, unit PD-107):

  A1  a recorder in place of the driver call sees the flag on every answer.
  A2  with PD-004b's proof set to `enforce`, an operator-contract run completes.
  A3  the same run with one byte of the receipt file changed exits 6.

PD-004b lives on its own lane, so this branch's `scripts/` driver may not carry
`--operator-contract` yet. A2 and A3 use the driver exactly as PD-004b wrote it,
exported from its commit; once it is in main the on-disk driver is used as-is.
"""
import importlib.util
import json
import os
import pathlib
import subprocess
import sys

import pytest

HERE = pathlib.Path(__file__).resolve().parent
APP = HERE.parent
PRESENTATIONS = HERE.parent.parent.parent
DRIVER = PRESENTATIONS / "scripts" / "deck-intake-driver.py"
SCHEMA_DIR = PRESENTATIONS / "intake"
BRIDGE = APP / "bridge" / "intake_bridge.py"
# The accepted PD-004b head that added the third provenance class.
PD004B_COMMIT = "27c667070"
REL = "23-ai-workforce-blueprint/templates/role-library/presentations"

spec = importlib.util.spec_from_file_location("pd107_bridge", BRIDGE)
bridge = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(bridge)

RECEIPT_HMAC = "pd107-test-receipt-hmac"

def contract():
    # Values are explicit non-commercial facts from the authenticated
    # informational-demo contract, never invented commercial claims.
    return {
        "version": 1, "source": "operator-delegated",
        "task_id": "d4e05a2f-f83b-4e87-aabe-d5e31c43867b",
        "execution_id": "b4cc51f0-0abf-420a-bed2-9cfbb8650e83",
        "title": "How the Presentation Department Works",
        "presentation_type": "from_scratch", "run_mode": "ultra",
        "workhorse_model": "deepseek-flash@deepseek-direct",
        "slide_count": 8, "pitch_included": False,
        "want_teleprompter": "yes", "want_speech_script": "yes",
        "want_audio_deliverable": "yes", "want_audio_demo": True,
        "want_ghl_upload": "yes", "want_sales_checkout": "yes", "want_vsl_page": "yes",
        "deliverable_set": "PPTX, PDF, presenter guide, workbook, fillable workbook, infographic",
        "delivery_destinations": ["PPTX", "PDF", "presenter guide", "workbook",
                                  "fillable workbook", "infographic"],
        "answers": {
            "audience": "General informational audience learning how to use the Presentation Department",
            "transformation_promise": "No commercial transformation promise — informational department demonstration",
            "cta_action": "Request or use the Presentation Department",
            "tone": "teacher",
        },
    }

def _repo_root() -> pathlib.Path:
    proc = subprocess.run(["git", "-C", str(HERE), "rev-parse", "--show-toplevel"],
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    return pathlib.Path(proc.stdout.strip())

def driver_supports_contract(driver: pathlib.Path) -> bool:
    return driver.is_file() and "--operator-contract" in driver.read_text(encoding="utf-8")

def pd004b_driver(tmp_path: pathlib.Path) -> pathlib.Path:
    """PD-004b's driver and its own question bank, as its author wrote them.

    The unit is accepted at PD004B_COMMIT but lives on another lane, so this
    branch's `scripts/` may not carry `--operator-contract` yet. The exported
    tree pairs the driver with the bank it was written against -- never one
    lane's driver with the other lane's bank.
    """
    if driver_supports_contract(DRIVER):
        return DRIVER
    root = tmp_path / "pd004b"
    root.mkdir()
    archive = subprocess.run(["git", "-C", str(_repo_root()), "archive",
                              PD004B_COMMIT, f"{REL}/intake", f"{REL}/scripts"],
                             capture_output=True)
    if archive.returncode:
        pytest.skip(f"PD-004b tree unavailable ({PD004B_COMMIT}) and the "
                    "checked-out driver does not carry --operator-contract yet")
    untar = subprocess.run(["tar", "-x", "-C", str(root)],
                           input=archive.stdout, capture_output=True)
    assert untar.returncode == 0, untar.stderr
    return root / REL / "scripts" / "deck-intake-driver.py"

def _run_env(monkeypatch, **extra):
    monkeypatch.setenv("PRESENTATION_REQUESTER_CHAT_ID", "operator-test-route")
    monkeypatch.setenv("PRESENTATION_REQUESTER_CHANNEL", "operator-delegated")
    for key, value in extra.items():
        monkeypatch.setenv(key, value)


def test_pd107_a1_a_recorder_sees_the_flag_on_every_answer(tmp_path, monkeypatch):
    _run_env(monkeypatch)
    root = tmp_path / "recorder"
    (root / "scripts").mkdir(parents=True)
    (root / "intake").symlink_to(SCHEMA_DIR)
    log = tmp_path / "calls.jsonl"
    (root / "scripts" / "deck-intake-driver.py").write_text(
        "import json, sys\n"
        f"open({str(log)!r}, 'a', encoding='utf-8').write(json.dumps(sys.argv[1:]) + '\\n')\n"
        "sys.exit(0)\n",
        encoding="utf-8")
    rd = tmp_path / "recorder-run"
    # The recorder writes no intake, so the run stops after the driver calls.
    # The row is about what the recorder saw, not about what came after it.
    with pytest.raises(Exception):
        bridge.drive_operator_contract(contract(), rd,
                                       driver_path=root / "scripts" / "deck-intake-driver.py",
                                       launch=False, receipt_hmac=RECEIPT_HMAC)
    calls = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    answers = [call for call in calls if "--answer" in call]
    assert answers, f"the recorder saw no answer call: {calls}"
    missing = [call for call in answers if "--operator-contract" not in call]
    assert not missing, f"answers recorded without --operator-contract: {missing}"
    # The receipt the driver hashes exists before the first answer is written.
    answered_at = log.stat().st_mtime
    receipt = rd / "working" / "interview" / "operator_contract.json"
    assert receipt.is_file() and receipt.stat().st_mtime <= answered_at


def _contract_entries(rd):
    ledger = json.loads((pathlib.Path(rd) / "working" / "interview" /
                         "intake_ledger.json").read_text())
    return [entry for entry in ledger["entries"].values() if isinstance(entry, dict)
            and entry.get("source") == "operator-contract"]


def test_pd107_a2_an_operator_contract_run_completes_under_enforce(tmp_path, monkeypatch):
    _run_env(monkeypatch, PRESENTATION_INTAKE_PROVENANCE="enforce")
    driver = pd004b_driver(tmp_path)
    rd = tmp_path / "enforce-run"
    report = bridge.drive_operator_contract(contract(), rd, driver_path=driver,
                                            launch=False, receipt_hmac=RECEIPT_HMAC)
    assert report["driver_complete"] is True
    receipt = rd / "working" / "interview" / "operator_contract.json"
    receipt_sha = bridge.hashlib.sha256(receipt.read_bytes()).hexdigest()
    entries = _contract_entries(rd)
    assert entries, "no answer declared the operator-contract class"
    for entry in entries:
        assert entry.get("contract_sha256") == receipt_sha
    # PD-004b's driver mirrors the contract's run mode onto its own ledger key;
    # the bridge must declare that mirror or `enforce` refuses at --complete.
    run_mode = json.loads((rd / "working" / "interview" / "intake_ledger.json")
                          .read_text())["entries"]["run_mode"]
    assert run_mode["source"] == "operator-contract", run_mode
    assert run_mode["contract_sha256"] == receipt_sha, run_mode


def test_pd107_a3_one_changed_receipt_byte_exits_six(tmp_path, monkeypatch):
    _run_env(monkeypatch, PRESENTATION_INTAKE_PROVENANCE="enforce")
    driver = pd004b_driver(tmp_path)
    rd = tmp_path / "tampered-run"
    real_run = bridge.subprocess.run

    def tampering(argv, *args, **kwargs):
        # The byte changes between the answers and the completion door, so the
        # run is the same run and only the receipt differs.
        if isinstance(argv, list) and "--complete" in argv:
            receipt = rd / "working" / "interview" / "operator_contract.json"
            raw = receipt.read_bytes()
            receipt.write_bytes(raw[:-1] + (b" " if raw[-1:] != b" " else b"\n"))
        return real_run(argv, *args, **kwargs)

    monkeypatch.setattr(bridge.subprocess, "run", tampering)
    with pytest.raises(RuntimeError) as refused:
        bridge.drive_operator_contract(contract(), rd, driver_path=driver,
                                       launch=False, receipt_hmac=RECEIPT_HMAC)
    assert "driver completion refused" in str(refused.value)
    proc = real_run([sys.executable, str(driver), "--run-dir", str(rd), "--complete"],
                    capture_output=True, text=True, check=False)
    assert proc.returncode == 6, f"rc={proc.returncode} stderr={proc.stderr[-400:]}"
    payload = json.loads(proc.stdout)
    assert "the operator contract receipt no longer matches this answer" in " ".join(
        payload["findings"])
    assert len(payload["unproven_questions"]) > 1, payload
