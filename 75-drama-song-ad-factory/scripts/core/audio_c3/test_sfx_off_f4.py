#!/usr/bin/env python3
"""F4 guard: a default run's job list contains ZERO Suno sound-effect jobs.

Owner order 2026-10-08, manual Part F item F4 (Medium, ADDENDUM 3). Mocked
by construction: no socket, no provider, no paid call. Run:

Run: python3 core/audio_c3/test_sfx_off_f4.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))          # core/

import audio_c3.sfx_off as SX                      # noqa: E402

FAILS = []

def check(name, cond, detail=""):
    if cond:
        print("PASS  %s" % name)
    else:
        print("FAIL  %s  %s" % (name, detail))
        FAILS.append(name)

# --- 1. default run config: ordered=False -----------------------------------

check("default-config-not-ordered",
      SX.sfx_ordered({}) is False)
check("default-config-no-sfx-errors",
      SX.sfx_error_codes({}) == [])
check("empty-sound_effects-list-not-an-order",
      SX.sfx_ordered({"sound_effects": []}) is False,
      "an empty list is not an explicit manual order")
check("bare-string-not-an-order",
      SX.sfx_ordered({"sound_effects": "thunder"}) is False,
      "shape must be a list of non-empty strings")
check("explicit-order-accepted",
      SX.sfx_ordered({"sound_effects": ["thunder roll"]}) is True,
      "the run's own config may explicitly order sound effects")

# --- 2. default run job list: ZERO sfx jobs ---------------------------------

def run_receipt(jobs):
    return {"schema_version": "x", "jobs": jobs}

DEFAULT_SONG_JOB = {"model": "ai-music-api/generate",
                    "endpoint": "/api/v1/jobs/createTask",
                    "kind": "song"}
DEFAULT_VIDEO_JOB = {"model": "kling/v2-1", "kind": "video"}
DEFAULT_IMAGE_JOB = {"model": "seedream-4", "kind": "image"}

check("default-run-jobs-zero-sfx",
      SX.default_run_job_audit(
          run_receipt([DEFAULT_SONG_JOB, DEFAULT_VIDEO_JOB,
                       DEFAULT_IMAGE_JOB])) == [],
      "a default run's job list must contain no sfx jobs")
check("default-run-empty-jobs",
      SX.default_run_job_audit(run_receipt([])) == [])
check("default-run-no-jobs-key",
      SX.verify_run_jobs({}) == [],
      "a receipt without a job list earns no sfx errors")

# --- 3. an sfx job on a default run FAILS ------------------------------------

SFX_JOB_ROUTE = {"model": "V6", "route": SX.SFX_ROUTE_CURRENT,
                 "kind": "sfx"}
SFX_JOB_CATALOG = {"catalog_model": "suno-sounds", "kind": "sfx"}
SFX_JOB_ENDPOINT = {"model": "V5", "endpoint": "/api/v1/generate/sounds"}

check("sfx-job-on-default-run-fails",
      any(e.startswith("SFX_JOB_NOT_ORDERED") for e in
          SX.default_run_job_audit(run_receipt([SFX_JOB_ROUTE]))),
      "one sounds job on an un-ordered run is F4's refusal")
check("catalog-id-job-fails",
      SX._is_sfx_job(SFX_JOB_CATALOG) is True)
check("legacy-endpoint-job-fails",
      SX._is_sfx_job(SFX_JOB_ENDPOINT) is True)
check("song-job-still-clean",
      SX._is_sfx_job(DEFAULT_SONG_JOB) is False)
check("non-dict-job-ignored",
      SX._is_sfx_job("not a job") is False)

# --- 4. explicit manual order: exactly the ordered count ---------------------

ORDERED_CFG = {"sound_effects": ["thunder roll", "doorbell"]}
check("ordered-run-allows-up-to-ordered-count",
      SX.default_run_job_audit(
          [run_receipt([DEFAULT_SONG_JOB,
                        dict(SFX_JOB_ROUTE, prompt="thunder roll")]),
           run_receipt([SFX_JOB_CATALOG])],
          ORDERED_CFG) == [],
      "two ordered prompts may produce two sfx jobs")
check("ordered-run-surplus-fails",
      any("SFX_JOB_SURPLUS" in e for e in SX.default_run_job_audit(
          [run_receipt([SFX_JOB_ROUTE, SFX_JOB_ENDPOINT]),
           run_receipt([SFX_JOB_CATALOG])],
          ORDERED_CFG)),
      "three sfx jobs against a two-prompt order is a surplus")

# --- 5. config leak gate: sfx words refuse unless ordered --------------------

check("config-sfx-word-default-fails",
      any(e.startswith("SFX_NOT_ORDERED_LEAK") for e in SX.sfx_error_codes(
          {"style": "slow ballad with thunder at the turn"})),
      "an un-ordered config asking for 'thunder' refuses")
check("config-sfx-word-ordered-passes",
      SX.sfx_error_codes(
          {"style": "slow ballad with thunder at the turn",
           "sound_effects": ["thunder"]}) == [])
check("config-clean-style-passes",
      SX.sfx_error_codes({"style": "soul ballad, warm piano"}) == [])
check("config-sfx-key-never-self-leaks",
      SX.sfx_error_codes(
          {"sound_effects": ["thunder", "siren"]}) == [],
      "the order list itself is not re-checked as a leak")

# --- 6. malformed receipts ----------------------------------------------------

check("receipt-not-dict-fails",
      SX.verify_run_jobs(None) == ["RECEIPT_INVALID:not a dict"])
check("jobs-not-list-fails",
      SX.verify_run_jobs({"jobs": "junk"}) == ["JOB_LIST_INVALID:not a list"])
check("receipts-not-list-fails",
      SX.default_run_job_audit(42) == ["RECEIPTS_INVALID:not a list"])
check("audio_jobs-alias-read",
      SX.default_run_job_audit({"audio_jobs": []}) == [],
      "the receipt key the F1 soundtrack verify already reads")

# --- 7. py_compile the module --------------------------------------------------

import py_compile
import tempfile
with tempfile.TemporaryDirectory() as td:
    py_compile.compile(
        os.path.join(HERE, "sfx_off.py"),
        cfile=os.path.join(td, "sfx_off.pyc"), doraise=True)
print("PASS  py_compile sfx_off.py clean")

def test_suite_checks_pass():
    assert not FAILS, FAILS


if __name__ == "__main__":
    print("")
    if FAILS:
        print("FAILED: %d check(s): %s" % (len(FAILS), ", ".join(FAILS)))
        sys.exit(1)
    print("ALL PASS")
    sys.exit(0)