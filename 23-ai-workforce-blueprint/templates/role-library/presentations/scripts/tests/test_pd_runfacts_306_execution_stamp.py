"""test_pd_runfacts_306_execution_stamp.py -- PD-306 acceptance (A1).

PD-306: execution-stamp rows are KEYED, and the legacy rule is explicit.

Every claim in the unit is proven here, with the old behaviour shown failing:

  A1-key   the per-row keyed hash changes when the row changes and not
           otherwise, and a row edited after it was written no longer verifies.
  A1-key2  the key mints ONCE and is idempotent (state.ensure_run_key).
  A1-key3  the key never reaches stdout/stderr, and never reaches a stamp row.
  A1-leg1  a stamp file with NO hashed row is treated as today and logs
           ``stamp.legacy``.
  A1-leg2  once ANY row is hashed, a hashless row is ignored, not accepted.
  A1-old   the pre-PD-306 read (every row trusted) ACCEPTS the tampered row the
           keyed read rejects -- the negative half of the proof.

No network, no credentials. Stdlib + pytest/tmp_path only.
"""
import json
import pathlib
import sys

import pytest

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent
for _p in (SCRIPTS, SCRIPTS / "presentation_job"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from presentation_job import execution_stamp as es  # noqa: E402
from presentation_job import state as st  # noqa: E402

PHASE = "P1Q-COPY-QC"
ARTIFACT_REL = "working/qc/copy_qc_report.json"


def _rd(tmp_path: pathlib.Path, *, with_key: bool = True) -> pathlib.Path:
    rd = tmp_path / "run"
    (rd / "working" / "qc").mkdir(parents=True)
    (rd / ARTIFACT_REL).write_text(json.dumps({"gate": "Phase 1Q", "pass": True}),
                                   encoding="utf-8")
    if with_key:
        _write_state(rd, st.mint_run_key())
    return rd


def _write_state(rd: pathlib.Path, key: str) -> None:
    (rd / es.STATE_FILENAME).write_text(
        json.dumps({"job_id": "job-test", "schema_version": 1,
                    st.RUN_KEY_FIELD: key}), encoding="utf-8")


def _key(rd: pathlib.Path) -> str:
    return es.resolve_run_key(rd)


def _write_rows(rd: pathlib.Path, rows) -> pathlib.Path:
    d = rd / "working" / "execution-stamps"
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{PHASE}.stamp.json"
    p.write_text(json.dumps({"schema_version": 1, "phase_id": PHASE,
                             "rows": rows}, indent=2), encoding="utf-8")
    return p


def _rows(rd: pathlib.Path):
    return json.loads((rd / "working" / "execution-stamps" /
                       f"{PHASE}.stamp.json").read_text(encoding="utf-8"))["rows"]


def _pair(rd: pathlib.Path, *, author_exec="exec-author0001",
          reviewer_exec="exec-review0002", rubric="manifest-test"):
    """A legitimately keyed author+reviewer pair for the current artifact."""
    art = rd / ARTIFACT_REL
    es.author_stamp(rd, PHASE, art, model="deepseek-v4.1-flash",
                    provider="deepseek-direct")
    es.qc_stamp(rd, PHASE, art, reviewer_execution_id=reviewer_exec,
                model="kimi-v4-a", provider="moonshot", rubric_version=rubric)
    rows = _rows(rd)
    rows[0]["execution_id"] = author_exec
    # Re-key after the deliberate id change so the pair is internally honest.
    key = _key(rd)
    for r in rows:
        r[es.ROW_HASH_FIELD] = es.keyed_row_hash(r, key)
    _write_rows(rd, rows)
    return rows


# ---------------------------------------------------------------- A1-key

def test_keyed_hash_changes_when_the_row_changes_and_not_otherwise(tmp_path):
    rd = _rd(tmp_path)
    key = _key(rd)
    row = {"kind": "author", "execution_id": "exec-aaaa", "artifact": ARTIFACT_REL,
           "model": "deepseek-v4.1-flash", "stamped_at": "2026-01-01T00:00:00+00:00"}

    h1 = es.keyed_row_hash(row, key)
    h2 = es.keyed_row_hash(dict(row), key)
    assert h1 == h2, "identical rows must hash identically"

    changed = dict(row, model="kimi-v4-a")
    assert es.keyed_row_hash(changed, key) != h1, "a changed field must change the hash"

    # A different run key must not reproduce the first run's hash.
    assert es.keyed_row_hash(row, st.mint_run_key()) != h1

    # The hash itself is not part of what it covers (no self-reference).
    with_hash = dict(row, **{es.ROW_HASH_FIELD: h1})
    assert es.keyed_row_hash(with_hash, key) == h1


def test_edited_row_no_longer_verifies(tmp_path):
    rd = _rd(tmp_path)
    rows = _pair(rd)
    assert all(es._row_is_valid(r, _key(rd)) for r in rows)

    rows[1]["model"] = "claude-opus"          # tamper: claim a different reviewer
    assert not es._row_is_valid(rows[1], _key(rd))
    _write_rows(rd, rows)
    reason = es.qc_independence_reason(rd, PHASE, None, rd / ARTIFACT_REL)
    assert reason.startswith("AF-EXEC-STAMP: no trusted REVIEWER stamp"), reason


# --------------------------------------------------------------- A1-key2

def test_run_key_mints_once_and_is_idempotent(tmp_path):
    state = {"job_id": "job-test", "schema_version": 1}
    first = st.ensure_run_key(state)
    second = st.ensure_run_key(state)
    assert first == second, "ensure_run_key must never re-mint"
    assert st.run_key_of(state) == first
    assert len(first) == st.RUN_KEY_BYTES * 2 and int(first, 16) >= 0
    # A fresh run is a different key.
    assert st.mint_run_key() != st.mint_run_key()


def test_ensure_run_key_persists_through_the_store(tmp_path):
    rd = tmp_path / "run"
    rd.mkdir()
    store = st.StateStore(rd)
    state = {"job_id": "job-test", "schema_version": 1}
    key = st.ensure_run_key(state, store)
    reloaded = store.load()
    assert st.run_key_of(reloaded) == key, "the key must survive a reload (resume)"


# --------------------------------------------------------------- A1-key3

def test_the_key_is_never_logged_or_printed(tmp_path, capfd):
    rd = _rd(tmp_path)
    key = _key(rd)
    _pair(rd)                                   # writes two keyed rows
    es.qc_independence_reason(rd, PHASE, None, rd / ARTIFACT_REL)
    es.consumed_coverage_reasons(rd, PHASE, rd / ARTIFACT_REL)
    es.stale_units(rd, PHASE, [rd / ARTIFACT_REL])
    st.ensure_run_key({"job_id": "job-test", "schema_version": 1})

    captured = capfd.readouterr()
    assert key not in captured.out
    assert key not in captured.err

    # And the key never lands in a stamp row either -- only its HMAC does.
    blob = (rd / "working" / "execution-stamps" / f"{PHASE}.stamp.json").read_text()
    assert key not in blob
    assert es.ROW_HASH_FIELD in blob


# ---------------------------------------------------------------- A1-leg1

def test_hashless_file_is_treated_as_today_and_logs_stamp_legacy(tmp_path, capfd):
    rd = _rd(tmp_path, with_key=False)
    art = rd / ARTIFACT_REL
    sha = es.sha256_file(art)
    # Exactly the pre-PD-306 shape: no row_hash anywhere.
    _write_rows(rd, [
        {"kind": "author", "execution_id": "exec-old-author", "phase_id": PHASE,
         "artifact": ARTIFACT_REL, "artifact_sha256": sha,
         "model": "deepseek-v4.1-flash", "provider": "deepseek-direct",
         "model_class": es.model_class_of("deepseek-v4.1-flash"),
         "stamped_at": es.utcnow()},
        {"kind": "reviewer", "execution_id": "exec-old-review", "phase_id": PHASE,
         "reviewed_artifact": ARTIFACT_REL, "reviewed_artifact_sha256": sha,
         "model": "kimi-v4-a", "provider": "moonshot",
         "model_class": es.model_class_of("kimi-v4-a"),
         "rubric_version": "manifest-test", "stamped_at": es.utcnow()},
    ])
    reason = es.qc_independence_reason(rd, PHASE, None, art)
    assert reason == "", f"a legacy hashless pair must still pass, got {reason!r}"
    err = capfd.readouterr().err
    assert es.STAMP_LEGACY_MARK in err
    assert "stamp.legacy" in err


# ---------------------------------------------------------------- A1-leg2

def test_hashless_row_is_ignored_once_any_row_is_hashed(tmp_path):
    rd = _rd(tmp_path)
    art = rd / ARTIFACT_REL
    sha = es.sha256_file(art)
    key = _key(rd)
    author = {"kind": "author", "execution_id": "exec-honest-author",
              "phase_id": PHASE, "artifact": ARTIFACT_REL,
              "artifact_sha256": sha, "model": "deepseek-v4.1-flash",
              "provider": "deepseek-direct",
              "model_class": es.model_class_of("deepseek-v4.1-flash"),
              "stamped_at": es.utcnow()}
    author[es.ROW_HASH_FIELD] = es.keyed_row_hash(author, key)
    sneaked = {"kind": "reviewer", "execution_id": "exec-not-ours",
               "phase_id": PHASE, "reviewed_artifact": ARTIFACT_REL,
               "reviewed_artifact_sha256": sha, "model": "kimi-v4-a",
               "provider": "moonshot",
               "model_class": es.model_class_of("kimi-v4-a"),
               "rubric_version": "manifest-test", "stamped_at": es.utcnow()}
    _write_rows(rd, [author, sneaked])          # one hashed -> strict file

    rows = es.trusted_rows(_rows(rd), key, run_dir=rd, phase_id=PHASE)
    assert len(rows) == 1 and rows[0]["kind"] == "author"
    reason = es.qc_independence_reason(rd, PHASE, None, art)
    assert reason.startswith("AF-EXEC-STAMP: no trusted REVIEWER stamp"), reason


def test_a_run_with_no_key_trusts_no_hashed_row(tmp_path):
    rd = _rd(tmp_path)
    rows = _pair(rd)
    (rd / es.STATE_FILENAME).unlink()           # no key anywhere
    assert es.trusted_rows(rows, None, run_dir=rd, phase_id=PHASE) == []
    assert es.qc_independence_reason(rd, PHASE, None, rd / ARTIFACT_REL) != ""


# ----------------------------------------------------------------- A1-old

def test_the_keyed_read_rejects_what_the_old_read_accepted(tmp_path):
    """The negative half: show the PRE-PD-306 behaviour passing a forged row."""
    rd = _rd(tmp_path)
    art = rd / ARTIFACT_REL
    rows = _pair(rd)

    # Forge: a reviewer row claiming a fully independent model, appended by
    # someone with write access to the run dir, then the honest rows removed.
    forged = {k: v for k, v in rows[1].items() if k != es.ROW_HASH_FIELD}
    forged["model"] = "claude-opus"
    forged["provider"] = "anthropic"
    forged["model_class"] = es.model_class_of("claude-opus")
    _write_rows(rd, [rows[0], forged])

    # OLD read: every row as-is (this is `_load_stamps(...)["rows"]` pre-PD-306).
    from presentation_job.execution_stamp import _load_stamps  # noqa: E402
    old_rows = _load_stamps(rd, PHASE)["rows"]
    old_reviewer = [r for r in old_rows
                    if r.get("kind") == "reviewer"
                    and r.get("reviewed_artifact") == ARTIFACT_REL]
    assert len(old_reviewer) == 1, "the old read saw the forged row"
    assert old_reviewer[0]["model"] == "claude-opus", "the old read trusted it"

    # NEW read: the forged row carries no valid hash, so it is dropped and the
    # gate refuses with a named reason.
    new_rows = es.trusted_rows(old_rows, _key(rd), run_dir=rd, phase_id=PHASE)
    assert [r for r in new_rows if r.get("kind") == "reviewer"] == []
    reason = es.qc_independence_reason(rd, PHASE, None, art)
    assert reason.startswith("AF-EXEC-STAMP: no trusted REVIEWER stamp"), reason


# ------------------------------------------------------- stamp surfaces agree

def test_consumed_coverage_and_stale_units_use_trusted_rows(tmp_path):
    rd = _rd(tmp_path)
    art = rd / ARTIFACT_REL
    rows = _pair(rd)
    assert es.consumed_coverage_reasons(rd, PHASE, art) == []
    assert es.stale_units(rd, PHASE, [art]) == []

    rows[1]["rubric_version"] = "tampered-after-the-fact"
    _write_rows(rd, rows)
    reasons = es.consumed_coverage_reasons(rd, PHASE, art)
    assert reasons and reasons[0].startswith("AF-EXEC-STAMP: no reviewer stamp")
    assert es.stale_units(rd, PHASE, [art]) == [ARTIFACT_REL]


# ------------------------------------------- the human verdict never touches it

def test_verdict_in_its_own_file_leaves_the_report_stamp_passing(tmp_path):
    """PD-306's other half (decision D-34): a person's verdict is recorded in
    working/qc/human-review/, so it never edits the graded report -- and the
    report's keyed execution stamps still pass afterwards."""
    rd = _rd(tmp_path)
    art = rd / ARTIFACT_REL
    _pair(rd)
    before = es.sha256_file(art)
    assert es.qc_independence_reason(rd, PHASE, None, art) == ""

    hr = rd / "working" / "qc" / "human-review"
    hr.mkdir(parents=True)
    (hr / "representation_casting.json").write_text(json.dumps({
        "pass": True, "reviewed_by": "operator:trevor",
        "reviewed_at": "2026-01-01T00:00:00+00:00", "note": "people match",
    }), encoding="utf-8")

    assert es.sha256_file(art) == before, "the report's bytes must be unchanged"
    assert es.qc_independence_reason(rd, PHASE, None, art) == "", \
        "a verdict written beside the report must not break its stamp"

