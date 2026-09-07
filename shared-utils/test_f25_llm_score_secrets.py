"""F25 regression: shared-utils/llm_score.py must resolve credentials from
the box's SECRETS STORES, not from os.environ and openclaw.json alone.

WHY THIS EXISTS (measured on the operator Mac, 2026-09-06 -- presence and
LENGTH only, no value was read or printed by the measurement):

    presentation_job.env_store --report
        watched  OPENROUTER_API_KEY: PRESENT (len 73, source env-store)
    llm_score._env("OPENROUTER_API_KEY")
        resolved=False len=0

Same box, same instant, two readers, opposite answers. A script started by
launchd or by the openclaw cron gets essentially NO environment, so a
persona-scoring pass spawned under a scheduler resolved no key at all and
logged "all models failed: OPENROUTER_API_KE..." while the key sat, present
and non-blank, in ~/.openclaw/secrets/.env. This is the residual half of the
env-loading class that left PRESENTATION_NOTIFY_CMD unreachable and refused
5,948 consecutive dispatches with AF-NOTIFY-UNCONFIGURED. It is an
ENV-LOADING defect, never a credential defect.

WHAT IS PINNED HERE:

  1. STATIC    -- the module actually has a store resolver, and its own CLI
                  can report resolution without printing a value.
  2. FAILING-BEFORE / PASSING-AFTER ON ONE INSTRUMENT -- the SAME hermetic
                  store and the SAME environment, resolved twice: once
                  through the pre-fix shape (restated verbatim from
                  origin/main below, which is os.environ + the openclaw.json
                  top level and nothing else) and once through the shipped
                  _env(). The first must NOT resolve; the second must.
  3. CONTROL    -- with the store REMOVED, the shipped _env() must resolve
                  nothing either. Without this leg a green result could be a
                  harness leaking this box's real credential rather than the
                  scratch store answering.
  4. PRECEDENCE -- a NON-BLANK process value wins over the store; a BLANK
                  process value does NOT shadow it (blank is the absence
                  this fix is about, not an override); the first store that
                  answers wins and a blank assignment never blocks a later
                  store.
  5. ALIASES    -- the FIX 67 canon (shared-utils/secret_names.json) decides
                  which names are the same credential, so a key stored as
                  OPENROUTER_KEY resolves; and a name outside the canon
                  never picks up an unrelated alias.
  6. REDACTION  -- a sentinel planted in the scratch store must appear
                  NOWHERE in env_report() or in the CLI's output. Presence
                  and LENGTH are the only facts about a value that may be
                  reported.
  7. LOCKSTEP   -- llm_score's candidate stores cover every candidate the
                  shared sibling resolver (secret_helper) knows about, so
                  the two cannot silently drift apart.
  8. DEGRADATION-- an unreadable store, a junk store and an unimportable
                  canon all degrade; this module's contract is "never raise".

Every leg is hermetic: HOME is redirected into tmp_path and OPENCLAW_SECRETS
names a scratch file, so no leg can read -- or print -- this box's real
secrets. Nothing here touches the network.

    python3 -m pytest shared-utils/test_f25_llm_score_secrets.py -q
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent          # .../shared-utils
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import llm_score  # noqa: E402

MODULE_PATH = _HERE / "llm_score.py"

#: A value no real store would ever carry, long enough to survive any
#: placeholder heuristic. If this string appears in a report or on stdout,
#: a secret value leaked.
SENTINEL = "sk-or-v1-F25-SENTINEL-MUST-NEVER-BE-PRINTED-0123456789abcdef"
OTHER = "sk-or-v1-F25-SECOND-STORE-VALUE-0123456789abcdefghij"
OVERRIDE = "sk-or-v1-F25-PROCESS-OVERRIDE-0123456789abcdefghij"


# ---------------------------------------------------------------------------
# Hermetic harness
# ---------------------------------------------------------------------------
_SCRUB = (
    "OPENROUTER_API_KEY", "OPENROUTER_KEY", "OR_API_KEY", "OPEN_ROUTER_API_KEY",
    "OLLAMA_CLOUD_API_KEY", "OLLAMA_API_KEY", "OLLAMA_KEY", "OLLAMA_TOKEN",
    "OLLAMA_CLOUD_URL", "OPENCLAW_SECRETS", "OC_ROOT", "OC_CONFIG",
)

#: Cleared inside the out-of-process probes so they measure the DEFAULT
#: (unpinned) candidate order. A pin on the developer's box would otherwise
#: make the lockstep comparison test a different arrangement than the one it
#: claims to test.
_PIN_NAMES = ("OPENCLAW_ROOT", "OC_ROOT", "OC_CONFIG", "OPENCLAW_SECRETS")


@pytest.fixture()
def box(tmp_path, monkeypatch):
    """A scratch box: HOME redirected into tmp_path, the client root PINNED
    to the scratch installation, every name these tests touch removed from
    the process environment, and no store yet.

    THE PIN IS WHAT MAKES THIS HERMETIC ON EVERY HOST. HOME redirection alone
    is not enough: /data/.openclaw is an absolute candidate that a redirected
    HOME cannot hide, so on a container these legs would silently measure the
    REAL store instead of the scratch one -- a green that means nothing and a
    red that means nothing. OPENCLAW_ROOT is the same pin
    presentation_job.oc_paths.root() honours, and llm_score searches a pinned
    root and nothing else, so no leg here can reach another installation's
    credentials on any box.
    """
    home = tmp_path / "home"
    (home / ".openclaw" / "secrets").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("OPENCLAW_ROOT", str(home / ".openclaw"))
    for name in _SCRUB:
        monkeypatch.delenv(name, raising=False)
    return home


def test_the_box_fixture_cannot_reach_another_installation(box):
    """ANTI-VACUITY for the fixture itself: with the pin set, NOTHING outside
    the scratch installation may appear in the candidate list -- not
    /data/.openclaw, not the real ~/.env. If this ever regresses, every
    'nothing resolves' control leg above becomes unfalsifiable."""
    candidates = llm_score._secret_store_files()
    assert candidates, "control: there must be candidates to inspect"
    outside = [p for p in candidates if not p.startswith(str(box) + os.sep)]
    assert not outside, (
        f"the pinned scratch box can still reach {outside}; these tests would "
        "measure a real installation's store on any host that has one"
    )


def write_store(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    path.chmod(0o600)
    return path


def prefix_store(home: Path, body: str) -> Path:
    """The store an OpenClaw box actually ships: <root>/secrets/.env."""
    return write_store(home / ".openclaw" / "secrets" / ".env", body)


def prefix_openclaw_json(home: Path, env_block: dict) -> Path:
    path = home / ".openclaw" / "openclaw.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"env": env_block}), encoding="utf-8")
    return path


def prefix_env_resolution(key: str, default: str = "") -> str:
    """THE PRE-FIX SHAPE, restated verbatim from origin/main's llm_score.py.

    This is the control instrument for leg 2. It is deliberately a copy and
    not an import: the point is to run the OLD resolution against the SAME
    scratch store the new one sees, on the same call, in the same process.

        def _env(key, default=""):
            v = os.environ.get(key)
            if v:
                return v
            return _openclaw_env().get(key, default) or default

    with _openclaw_env() reading only the TOP LEVEL of the openclaw.json
    "env" object.
    """
    value = os.environ.get(key)
    if value:
        return value
    block = {}
    for candidate in (os.path.expanduser("~/.openclaw/openclaw.json"),
                      "/data/.openclaw/openclaw.json"):
        if os.path.exists(candidate):
            try:
                with open(candidate) as handle:
                    block = json.load(handle).get("env", {}) or {}
            except Exception:
                block = {}
            break
    return block.get(key, default) or default


# ---------------------------------------------------------------------------
# 1. STATIC
# ---------------------------------------------------------------------------

def test_module_has_a_secrets_store_resolver():
    """A reader with no store resolver is the defect, by definition."""
    for symbol in ("_store_lookup", "_secret_store_files", "_parse_store",
                   "_alias_family", "env_report"):
        assert hasattr(llm_score, symbol), (
            f"llm_score.{symbol} is missing -- without it this module reads "
            "os.environ and openclaw.json only, and a scheduler-spawned "
            "scoring pass resolves no credential at all (F25)."
        )


def test_unpinned_order_is_container_root_then_home_root(box, monkeypatch):
    """With no pin, the order is the one every sibling reader uses: the
    container root first (a VPS box's real root), then this user's HOME
    root, then ~/.env."""
    monkeypatch.delenv("OPENCLAW_ROOT", raising=False)
    candidates = llm_score._secret_store_files()
    assert candidates[0] == "/data/.openclaw/secrets/.env", candidates
    home_first = os.path.join(str(box), ".openclaw", "secrets", ".env")
    assert home_first in candidates, candidates
    assert candidates.index("/data/.openclaw/secrets/.env") < candidates.index(home_first)
    assert candidates[-1] == os.path.join(str(box), ".env"), candidates


@pytest.mark.parametrize("bad", ["", "   ", "relative/path", "/"],
                         ids=["empty", "blank", "relative", "root-slash"])
def test_an_unusable_root_pin_is_no_pin_at_all(box, monkeypatch, bad):
    """A pin that cannot name an installation must not silently redirect the
    search; it falls back to the normal roots."""
    monkeypatch.setenv("OPENCLAW_ROOT", bad)
    assert llm_score._root_pin(os.environ) == ""
    assert "/data/.openclaw/secrets/.env" in llm_score._secret_store_files()


def test_candidate_stores_include_the_shipped_store_filenames(box):
    files = llm_score._secret_store_files()
    joined = "\n".join(files)
    for expected in ("secrets/.env", "secrets/secrets.env"):
        assert expected in joined, (
            f"no candidate store ends in {expected!r}; the box's shipped "
            f"credential store would never be read. Got: {files}"
        )


# ---------------------------------------------------------------------------
# 2. FAILING-BEFORE / PASSING-AFTER, one instrument
# ---------------------------------------------------------------------------

def test_pre_fix_shape_does_not_resolve_from_the_store(box):
    """CONTROL for the leg below: the SAME store, the SAME environment, and
    the pre-F25 resolution. It must NOT resolve -- that is the bug."""
    prefix_store(box, f"OPENROUTER_API_KEY={SENTINEL}\n")
    assert prefix_env_resolution("OPENROUTER_API_KEY") == "", (
        "the pre-fix resolution answered from a secrets store -- then this "
        "test is not measuring what it claims to measure."
    )


def test_env_resolves_the_key_from_the_secrets_store(box):
    """THE FIX. Same store, same environment, shipped resolver."""
    prefix_store(box, f"OPENROUTER_API_KEY={SENTINEL}\n")
    assert llm_score._env("OPENROUTER_API_KEY") == SENTINEL


def test_with_no_store_nothing_resolves(box):
    """CONTROL for the leg above. With the store REMOVED and the process
    environment scrubbed, the shipped resolver must return the default --
    if it still answers, the harness is leaking this box's real credential
    and every green result above is worthless."""
    assert llm_score._env("OPENROUTER_API_KEY") == ""
    assert llm_score._env("OPENROUTER_API_KEY", "fallback") == "fallback"


def test_store_answers_for_every_provider_name_the_chain_uses(box):
    prefix_store(
        box,
        f"OLLAMA_CLOUD_API_KEY={SENTINEL}\n"
        "OLLAMA_CLOUD_URL=https://ollama.example/api\n",
    )
    assert llm_score._env("OLLAMA_CLOUD_API_KEY") == SENTINEL
    assert llm_score._env("OLLAMA_CLOUD_URL",
                          "https://ollama.com/api") == "https://ollama.example/api"


# ---------------------------------------------------------------------------
# 3. PRECEDENCE
# ---------------------------------------------------------------------------

def test_non_blank_process_value_wins_over_the_store(box, monkeypatch):
    """An operator override for one invocation must still hold."""
    prefix_store(box, f"OPENROUTER_API_KEY={SENTINEL}\n")
    monkeypatch.setenv("OPENROUTER_API_KEY", OVERRIDE)
    assert llm_score._env("OPENROUTER_API_KEY") == OVERRIDE


def test_blank_process_value_does_not_shadow_the_store(box, monkeypatch):
    """THE PRECEDENCE THAT MATTERS. launchd and the openclaw cron hand a job
    an empty environment; an exported-but-empty name is the ABSENCE this fix
    is about, never an override. If a blank wins, the fix is inert exactly
    where it was needed."""
    prefix_store(box, f"OPENROUTER_API_KEY={SENTINEL}\n")
    monkeypatch.setenv("OPENROUTER_API_KEY", "")
    assert llm_score._env("OPENROUTER_API_KEY") == SENTINEL
    monkeypatch.setenv("OPENROUTER_API_KEY", "   ")
    assert llm_score._env("OPENROUTER_API_KEY") == SENTINEL


def test_first_store_that_answers_wins(box, monkeypatch):
    """Store order is the outer loop: an explicit OPENCLAW_SECRETS pin is
    tried before the default locations, and later stores only fill gaps."""
    pinned = write_store(box / "pinned.env", f"OPENROUTER_API_KEY={SENTINEL}\n")
    prefix_store(box, f"OPENROUTER_API_KEY={OTHER}\n")
    monkeypatch.setenv("OPENCLAW_SECRETS", str(pinned))
    assert llm_score._env("OPENROUTER_API_KEY") == SENTINEL


def test_blank_assignment_in_the_first_store_does_not_block_a_later_store(
        box, monkeypatch):
    """The original defect wearing a different hat: an empty
    `OPENROUTER_API_KEY=` line in the first store must not swallow the real
    value the next store carries."""
    pinned = write_store(box / "pinned.env", "OPENROUTER_API_KEY=\n")
    prefix_store(box, f"OPENROUTER_API_KEY={SENTINEL}\n")
    monkeypatch.setenv("OPENCLAW_SECRETS", str(pinned))
    assert llm_score._env("OPENROUTER_API_KEY") == SENTINEL


def test_store_beats_openclaw_json_and_openclaw_json_still_answers(box):
    """The stores are the credential authority; the openclaw.json env block
    stays as the legacy last resort so nothing that resolved before stops
    resolving."""
    prefix_openclaw_json(box, {"vars": {"OPENROUTER_API_KEY": OTHER}})
    prefix_store(box, f"OPENROUTER_API_KEY={SENTINEL}\n")
    assert llm_score._env("OPENROUTER_API_KEY") == SENTINEL

    (box / ".openclaw" / "secrets" / ".env").unlink()
    assert llm_score._env("OPENROUTER_API_KEY") == OTHER


def test_openclaw_json_nested_vars_shape_resolves(box):
    """REALITY, measured 2026-09-06: every box writes the env block as
    {"env": {"vars": {...}}}. Reading only the top level of "env" -- what
    this module did before F25 -- resolved nothing there, which is why the
    module's own documented openclaw.json fallback had never once fired."""
    prefix_openclaw_json(box, {"vars": {"OPENROUTER_API_KEY": SENTINEL}})
    assert prefix_env_resolution("OPENROUTER_API_KEY") == "", (
        "control: the pre-fix shape must NOT see the nested vars block"
    )
    assert llm_score._env("OPENROUTER_API_KEY") == SENTINEL


def test_openclaw_json_flat_shape_still_resolves(box):
    """Nothing that resolved before may stop resolving."""
    prefix_openclaw_json(box, {"OPENROUTER_API_KEY": SENTINEL})
    assert llm_score._env("OPENROUTER_API_KEY") == SENTINEL


# ---------------------------------------------------------------------------
# 4. ALIASES -- the FIX 67 canon decides, this module does not restate it
# ---------------------------------------------------------------------------

def test_key_stored_under_a_canon_alias_resolves(box):
    prefix_store(box, f"OPENROUTER_KEY={SENTINEL}\n")
    assert llm_score._env("OPENROUTER_API_KEY") == SENTINEL


def test_alias_in_the_process_env_beats_the_store(box, monkeypatch):
    """An alias exported in the process environment is still an explicit
    process value, so it wins -- same rule as the exact name."""
    prefix_store(box, f"OPENROUTER_API_KEY={SENTINEL}\n")
    monkeypatch.setenv("OPENROUTER_KEY", OVERRIDE)
    assert llm_score._env("OPENROUTER_API_KEY") == OVERRIDE


def test_a_name_outside_the_canon_is_its_own_family(box):
    """A non-secret setting must never pick up an unrelated alias."""
    assert llm_score._alias_family("OLLAMA_CLOUD_URL") == ["OLLAMA_CLOUD_URL"]


def test_alias_family_comes_from_the_shared_canon():
    """If this module ever restates its own alias table, a key written under
    a name the canon knows stops resolving here while resolving everywhere
    else. Pin it to the canon instead."""
    import secret_helper

    canon = secret_helper.alias_list("OPENROUTER_API_KEY")
    assert len(canon) > 1, (
        "control: secret_names.json must define an OPENROUTER family, "
        "otherwise this test proves nothing"
    )
    family = llm_score._alias_family("OPENROUTER_API_KEY")
    for alias in canon:
        assert alias in family, (
            f"{alias} is in the shared canon but not in llm_score's family "
            f"{family} -- the tables have drifted apart"
        )


# ---------------------------------------------------------------------------
# 5. REDACTION -- presence and LENGTH only, never a value
# ---------------------------------------------------------------------------

def test_env_report_never_carries_a_value(box):
    prefix_store(box, f"OPENROUTER_API_KEY={SENTINEL}\n")
    report = llm_score.env_report()
    assert SENTINEL not in report, "env_report leaked the credential VALUE"
    for fragment in (SENTINEL[:12], SENTINEL[-12:]):
        assert fragment not in report, "env_report leaked a PREFIX of the value"
    assert f"PRESENT (len {len(SENTINEL)}" in report, (
        "env_report must state presence and LENGTH -- that is the whole "
        f"reporting surface. Got:\n{report}"
    )
    assert "source secrets-store" in report


def test_env_report_names_an_unresolved_credential_without_guessing(box):
    report = llm_score.env_report(["OPENROUTER_API_KEY"])
    assert "NOT RESOLVED" in report
    assert "PRESENT" not in report


def test_cli_env_report_prints_no_value(box, tmp_path):
    """The operator-facing surface, run as a real process."""
    prefix_store(box, f"OPENROUTER_API_KEY={SENTINEL}\n")
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(box),
    }
    proc = subprocess.run(
        [sys.executable, str(MODULE_PATH), "--env-report"],
        env=env, capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    combined = proc.stdout + proc.stderr
    assert SENTINEL not in combined, "the CLI printed the credential VALUE"
    assert f"PRESENT (len {len(SENTINEL)}" in combined, combined


# ---------------------------------------------------------------------------
# 6. LOCKSTEP with the shared sibling resolver
# ---------------------------------------------------------------------------

#: Computes BOTH candidate lists in ONE fresh interpreter under ONE HOME.
#: secret_helper.ENV_FILE_CANDIDATES is a module-level constant whose ~ was
#: expanded once, at import; comparing it against a list built later from a
#: monkeypatched HOME would compare two different boxes and prove nothing.
#: Running it out of process also removes any dependence on the order the
#: tests in this file happen to run in.
_LOCKSTEP_PROBE = """
import json, os, sys
sys.path.insert(0, {shared_utils!r})
for _name in {pins!r}:
    os.environ.pop(_name, None)
import secret_helper, llm_score
shared = list(secret_helper.env_file_candidates())
mine = list(llm_score._secret_store_files())
print(json.dumps({{"shared": shared, "mine": mine}}))
"""


def _lockstep_lists(env=None):
    proc = subprocess.run(
        [sys.executable, "-c", _LOCKSTEP_PROBE.format(
            shared_utils=str(_HERE), pins=_PIN_NAMES)],
        env=env, capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout.strip().splitlines()[-1])
    return payload["shared"], payload["mine"]


def test_candidate_stores_cover_every_shared_candidate():
    """secret_helper is the sibling every other shared-utils reader uses. If
    it learns a new store location and this module does not, a credential
    that resolves everywhere else stops resolving here."""
    shared, mine = _lockstep_lists()
    assert shared, "control: secret_helper must publish candidates"
    assert mine, "control: llm_score must publish candidates"
    missing = [p for p in shared if p not in set(mine)]
    assert not missing, (
        "secret_helper knows store candidates llm_score does not read: "
        f"{missing}. Add them to _STORE_RELATIVE_PATHS / "
        "_secret_store_files()."
    )


#: Imports secret_helper FIRST (freezing its ~ to the real HOME), THEN
#: redirects HOME, THEN asks llm_score for its candidates. That order is the
#: whole point: it is the only arrangement in which "built live" and "reused
#: the shared constant" give different answers.
_VACUITY_PROBE = """
import json, os, sys
sys.path.insert(0, {shared_utils!r})
for _name in {pins!r}:
    os.environ.pop(_name, None)
import secret_helper
frozen = list(secret_helper.env_file_candidates())
os.environ["HOME"] = {other!r}
import llm_score
mine = list(llm_score._secret_store_files())
print(json.dumps({{"frozen": frozen, "mine": mine}}))
"""


def test_the_lockstep_comparison_is_not_vacuous(tmp_path):
    """ANTI-VACUITY for the leg above, and a hermeticity guarantee in its own
    right.

    llm_score must build its candidate list from the LIVE environment. If it
    instead unioned in secret_helper's import-time constant, two bad things
    would follow at once: the comparison above would pass by construction and
    could never fail, AND a HOME-redirected child would read a DIFFERENT
    installation's credential store -- the borrowing presentation_job.oc_paths
    refuses outright. One probe rules out both.
    """
    other = tmp_path / "other-box"
    (other / ".openclaw" / "secrets").mkdir(parents=True)
    proc = subprocess.run(
        [sys.executable, "-c", _VACUITY_PROBE.format(
            shared_utils=str(_HERE), other=str(other), pins=_PIN_NAMES)],
        capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout.strip().splitlines()[-1])
    frozen, mine = payload["frozen"], payload["mine"]

    assert any(str(other) in path for path in mine), (
        f"llm_score ignored the live HOME; its candidates are {mine}"
    )
    real_home = os.path.expanduser("~")
    assert any(path.startswith(real_home + os.sep) for path in frozen), (
        "control: secret_helper's constant must have frozen to the real HOME "
        f"before the redirect, otherwise this probe proves nothing: {frozen}"
    )
    borrowed = [p for p in mine if p.startswith(real_home + os.sep)]
    assert not borrowed, (
        "llm_score reused secret_helper's import-time candidate list. After a "
        "HOME redirect it would read a DIFFERENT installation's store, and "
        "test_candidate_stores_cover_every_shared_candidate would pass by "
        f"construction. Borrowed paths: {borrowed}"
    )


# ---------------------------------------------------------------------------
# 7. DEGRADATION -- this module's contract is "never raise"
# ---------------------------------------------------------------------------

def test_unreadable_and_junk_stores_never_raise(box, monkeypatch):
    junk = write_store(
        box / "junk.env",
        "not an assignment\n"
        "# comment\n"
        "\n"
        "9INVALID_NAME=x\n"
        f'export OPENROUTER_API_KEY="{SENTINEL}"\n',
    )
    monkeypatch.setenv("OPENCLAW_SECRETS", str(junk))
    assert llm_score._env("OPENROUTER_API_KEY") == SENTINEL

    monkeypatch.setenv("OPENCLAW_SECRETS", str(box / "does-not-exist.env"))
    assert llm_score._env("OPENROUTER_API_KEY") == ""

    directory = box / "a-directory.env"
    directory.mkdir()
    monkeypatch.setenv("OPENCLAW_SECRETS", str(directory))
    assert llm_score._env("OPENROUTER_API_KEY") == ""


def test_resolution_survives_an_unimportable_canon(box, monkeypatch):
    """A broken secret_names.json must degrade to the exact name, never take
    credential resolution down."""
    prefix_store(box, f"OPENROUTER_API_KEY={SENTINEL}\n")
    monkeypatch.setattr(llm_score, "_SECRET_HELPER", None, raising=False)
    monkeypatch.setattr(llm_score, "_SECRET_HELPER_TRIED", True, raising=False)
    assert llm_score._alias_family("OPENROUTER_API_KEY") == ["OPENROUTER_API_KEY"]
    assert llm_score._env("OPENROUTER_API_KEY") == SENTINEL


def test_public_api_still_imports_and_the_chain_still_degrades(box):
    """qc-static.yml imports these three symbols; keep them callable, and
    keep the documented degraded mode intact with no provider configured."""
    from llm_score import (  # noqa: F401
        NEUTRAL_FALLBACK_SCORE, _cache_key, score_layer,
        summarize_persona_blueprint,
    )

    result = score_layer(
        persona_id="f25-no-provider-configured",
        layer="mission",
        persona_blueprint_summary="scratch",
        context="scratch",
        use_cache=False,
    )
    assert result["fallback"] is True
    assert result["score"] == NEUTRAL_FALLBACK_SCORE
    assert SENTINEL not in json.dumps(result)
