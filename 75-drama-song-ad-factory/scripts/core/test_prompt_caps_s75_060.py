#!/usr/bin/env python3
"""S75-060: every card video model has a measured prompt cap; one catalog locator.

Proves (zero network, zero spend, no repository writes):
  1. every ``kie_model`` / ``kie_tier`` sold on the card's video price menu
     comes back with a measured prompt cap, or a NAMED refusal
     (PROMPT_LIMIT_NO_CAP) -- never a silent null;
  2. the two rows the catalog leaves uncapped carry the vendor page they were
     read from, the read date and their status: Seedance 2.0 Mini at 20,000
     VERIFIED, Veo 3.1 Fast at the conservative 5,000 UNVERIFIED;
  3. a sold model with no catalog cap and no override is refused, not sent;
  4. ``suno_extend.catalog()`` loads the 68 work copy with NO path argument, in
     the repository layout and in an installed layout built in a temp folder
     (75-... beside 68-kie-audio).
  5. that resolution follows module position, not import resolution: a tree
     whose locator and walk disagree returns the copy beside the module, and
     the 999-setup installer layout (walk finds nothing) still resolves via
     the locator.

Run: python3 -B scripts/core/test_prompt_caps_s75_060.py
Exit 0 = all pass, 1 = failures.
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import prompt_limits as PL          # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        (" (%s)" % (detail,)) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def _suno_extend():
    """The extend module, loaded by path (its catalog import does the rest)."""
    path = os.path.join(HERE, "audio_c3", "extend", "suno_extend.py")
    spec = importlib.util.spec_from_file_location("suno_extend_s75_060", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def sold_rows():
    """Every (kie_model, kie_tier) the card's video price menu sells."""
    doc = json.loads(PL.RATES_PATH.read_text(encoding="utf-8"))
    rows = []
    for row in doc.get("models") or []:
        for key in ("kie_model", "kie_tier"):
            value = row.get(key)
            if isinstance(value, str) and value.strip():
                rows.append((key, value.strip()))
    return rows


# ---- 1. every sold model is measured or refused by name -------------------
def test_every_sold_model_has_a_cap_or_a_named_refusal():
    video = PL.find_catalogs()[1]
    check("the 67 catalog resolves in this tree", video is not None and os.path.isfile(str(video)),
          video)
    rows = sold_rows()
    check("the price menu is readable", bool(rows), PL.RATES_PATH)
    for key, model in rows:
        try:
            row = PL.video_caps(model, models_path=video)
        except PL.PromptLimitError as exc:
            check("%s %r never passes unmeasured (named refusal)" % (key, model),
                  exc.code in ("PROMPT_LIMIT_NO_CAP", "PROMPT_LIMIT_NO_CATALOG"),
                  "%s: %s" % (exc.code, exc))
            continue
        check("%s %r has a measured prompt cap" % (key, model),
              isinstance(row.get("prompt"), int) and row["prompt"] > 0, row)
        check("%s %r reports its cap status" % (key, model),
              isinstance(row.get("status"), str) and row["status"], row)


# ---- 2. the two sourced rows ---------------------------------------------
def test_the_two_new_rows_carry_their_source():
    row = PL.OVERRIDES["bytedance/seedance-2-mini"]
    check("Seedance 2.0 Mini is held at the vendor page's 20,000",
          row["cap"] == 20000, row)
    check("Seedance 2.0 Mini is VERIFIED and names the page it was read from",
          row["status"] == "VERIFIED"
          and row["source_url"] == "https://docs.kie.ai/market/bytedance/seedance-2-mini"
          and "2026-11-12" in row["source"], row)
    veo = PL.OVERRIDES["veo3_fast"]
    check("Veo 3.1 Fast is held at the conservative sibling cap 5,000",
          veo["cap"] == 5000, veo)
    check("Veo 3.1 Fast stays UNVERIFIED and says the page states no cap",
          veo["status"] == "UNVERIFIED"
          and veo["source_url"] == "https://docs.kie.ai/veo3-api/generate-veo-3-video"
          and "no prompt maxLength" in veo["source"], veo)
    check("neither new row claims a negative_prompt cap the catalog does not declare",
          row["negative_prompt"] is None and veo["negative_prompt"] is None,
          (row.get("negative_prompt"), veo.get("negative_prompt")))
    caps = PL.video_caps("veo-3-1")          # the market id the card's row uses
    check("the market id veo-3-1 answers from the veo3_fast row",
          caps["prompt"] == 5000 and caps["negative_prompt"] is None, caps)
    check("Seedance 2.5 keeps its catalog cap of 30,000",
          PL.video_caps("bytedance/seedance-2-5")["prompt"] == 30000)


# ---- 3. the refusal is real, not decorative ------------------------------
def test_a_sold_model_with_no_cap_refuses():
    video = PL.find_catalogs()[1]
    real = PL.sold_video_models
    PL.sold_video_models = lambda: {"veo3"}    # a catalog row with a null cap
    try:
        try:
            PL.video_caps("veo3", models_path=video)
        except PL.PromptLimitError as exc:
            check("a sold model with no cap and no override is refused",
                  exc.code == "PROMPT_LIMIT_NO_CAP" and "OVERRIDES" in str(exc),
                  "%s: %s" % (exc.code, exc))
        else:
            check("a sold model with no cap and no override is refused", False,
                  "no refusal")
    finally:
        PL.sold_video_models = real
    caps = PL.video_caps("veo3", models_path=video)
    check("an unsold null-cap model still answers with cap None (unchanged)",
          caps["prompt"] is None, caps)


# ---- 4. one locator, both layouts ----------------------------------------
def test_catalog_loads_with_no_path_argument():
    SE = _suno_extend()
    ids = SE.catalog()
    check("suno_extend.catalog() loads in the repository layout with no argument",
          SE.EXTEND_CATALOG_ID in ids, sorted(ids)[:6])
    check("the same call names the 68 catalog it read",
          str(SE._catalog_file()).endswith(os.path.join("68-kie-audio", "models.json")),
          SE._catalog_file())

    audio = PL.find_catalogs()[0]
    check("the 68 catalog resolves for the installed layout", audio is not None
          and os.path.isfile(str(audio)), audio)
    if audio is None:
        return
    core_src = os.path.dirname(os.path.abspath(PL.__file__))
    extend_src = os.path.join(HERE, "audio_c3", "extend", "suno_extend.py")
    tmp = tempfile.mkdtemp(prefix="s75-060-installed-")
    try:
        skills = os.path.join(tmp, "skills")
        installed_core = os.path.join(skills, "75-drama-song-ad-factory",
                                      "scripts", "core")
        os.makedirs(os.path.join(skills, "68-kie-audio"))
        os.makedirs(os.path.join(installed_core, "audio_c3", "extend"))
        shutil.copy(str(audio), os.path.join(skills, "68-kie-audio", "models.json"))
        shutil.copy(os.path.join(core_src, "prompt_limits.py"),
                    os.path.join(installed_core, "prompt_limits.py"))
        shutil.copy(extend_src, os.path.join(installed_core, "audio_c3", "extend",
                                             "suno_extend.py"))
        script = (
            "import importlib.util, json\n"
            "spec = importlib.util.spec_from_file_location(\n"
            "    'suno_extend_s75_060_installed', %r)\n"
            "mod = importlib.util.module_from_spec(spec)\n"
            "spec.loader.exec_module(mod)\n"
            "print(json.dumps(sorted(mod.catalog())))\n"
            % os.path.join(installed_core, "audio_c3", "extend",
                           "suno_extend.py")
        )
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        run = subprocess.run([sys.executable, "-B", "-c", script], cwd=tmp,
                             capture_output=True, text=True, timeout=120, env=env)
        check("the installed layout runs the loader cleanly",
              run.returncode == 0, (run.returncode, run.stderr[-800:]))
        try:
            ids = json.loads(run.stdout.strip().split("\n")[-1])
        except (ValueError, IndexError):
            ids = []
        check("suno_extend.catalog() loads in the installed layout with no argument",
              "suno-extend" in ids and "suno-generate" in ids, ids)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _write_catalog(directory, marker):
    """A minimal 68 catalog whose extend route names ``marker``."""
    os.makedirs(os.path.join(directory, "68-kie-audio"), exist_ok=True)
    doc = {"entries": [{
        "canonical_model_id": "suno-extend",
        "route_models": {"current": "suno-extend/" + marker,
                         "current_endpoint": "https://" + marker + ".invalid/x"},
        "model_enum": ["V6"],
    }]}
    with open(os.path.join(directory, "68-kie-audio", "models.json"), "w",
              encoding="utf-8") as f:
        json.dump(doc, f)


def _run_loader(script, cwd):
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    run = subprocess.run([sys.executable, "-B", "-c", script], cwd=cwd,
                         capture_output=True, text=True, timeout=120, env=env)
    try:
        out = json.loads(run.stdout.strip().split("\n")[-1])
    except (ValueError, IndexError):
        out = {}
    return run, out


# ---- 5. ordering is module position, not import resolution ---------------
def test_catalog_order_is_module_position_not_import():
    """Locator and walk disagree -> the copy beside THIS module wins.

    Tree A holds the module copy and its own 68-kie-audio; tree B holds a
    ``prompt_limits`` (and a different 68-kie-audio) that is the one an
    ``import`` resolves. Resolution must follow module position: before the
    fix, ``find_catalogs()`` won and the shadow catalog came back silently.
    """
    extend_src = os.path.join(HERE, "audio_c3", "extend", "suno_extend.py")
    shadow_src = os.path.join(HERE, "prompt_limits.py")
    tmp = tempfile.mkdtemp(prefix="s75-060-divergence-")
    try:
        a = os.path.join(tmp, "A")
        b = os.path.join(tmp, "B")
        a_extend = os.path.join(a, "75-drama-song-ad-factory", "scripts",
                                "core", "audio_c3", "extend")
        os.makedirs(a_extend)
        os.makedirs(b)
        shutil.copy(extend_src, os.path.join(a_extend, "suno_extend.py"))
        shutil.copy(shadow_src, os.path.join(b, "prompt_limits.py"))
        _write_catalog(a, "tree-a-walk")
        _write_catalog(b, "shadow-b-locator")
        script = (
            "import importlib.util, json, sys\n"
            "R = %r\n"
            "s = importlib.util.spec_from_file_location('prompt_limits',\n"
            "        R + '/B/prompt_limits.py')\n"
            "pl = importlib.util.module_from_spec(s)\n"
            "s.loader.exec_module(pl)\n"
            "sys.modules['prompt_limits'] = pl\n"
            "m = R + '/A/75-drama-song-ad-factory/scripts/core/audio_c3/"
            "extend/suno_extend.py'\n"
            "s2 = importlib.util.spec_from_file_location('se_divergence', m)\n"
            "SE = importlib.util.module_from_spec(s2)\n"
            "s2.loader.exec_module(SE)\n"
            "print(json.dumps({'chosen': str(SE._catalog_path()),\n"
            "                  'locator': str(pl.find_catalogs()[0]),\n"
            "                  'route': SE.route_model()}))\n"
            % tmp
        )
        run, out = _run_loader(script, tmp)
        check("the divergent tree loads cleanly", run.returncode == 0,
              (run.returncode, run.stderr[-800:]))
        chosen = out.get("chosen", "")
        locator = out.get("locator", "")
        check("the locator really disagrees in this tree",
              os.path.join(b, "68-kie-audio", "models.json") == os.path.abspath(locator),
              locator)
        check("the catalog beside the module wins over the shadow locator",
              os.path.abspath(chosen) == os.path.join(
                  a, "68-kie-audio", "models.json"), chosen)
        check("the winning catalog is the one actually read",
              out.get("route") == "suno-extend/tree-a-walk", out.get("route"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_installed_layout_still_resolves_via_the_locator():
    """The 999-setup installer layout: the walk finds nothing, the locator does."""
    extend_src = os.path.join(HERE, "audio_c3", "extend", "suno_extend.py")
    core_src = os.path.dirname(os.path.abspath(PL.__file__))
    tmp = tempfile.mkdtemp(prefix="s75-060-installer-")
    try:
        core = os.path.join(tmp, "skills", "75-drama-song-ad-factory",
                            "scripts", "core")
        os.makedirs(os.path.join(core, "audio_c3", "extend"))
        os.makedirs(os.path.join(tmp, "installer-registration", "helpers",
                                 "68-kie-audio"))
        shutil.copy(extend_src, os.path.join(core, "audio_c3", "extend",
                                             "suno_extend.py"))
        shutil.copy(os.path.join(core_src, "prompt_limits.py"),
                    os.path.join(core, "prompt_limits.py"))
        target = os.path.join(tmp, "installer-registration", "helpers",
                              "68-kie-audio", "models.json")
        with open(target, "w", encoding="utf-8") as f:
            json.dump({"entries": [{
                "canonical_model_id": "suno-extend",
                "route_models": {"current": "suno-extend/installer-locator",
                                 "current_endpoint": "https://installer.invalid/x"},
                "model_enum": ["V6"]}]}, f)
        script = (
            "import importlib.util, json\n"
            "m = %r\n"
            "s = importlib.util.spec_from_file_location('se_installer', m)\n"
            "SE = importlib.util.module_from_spec(s)\n"
            "s.loader.exec_module(SE)\n"
            "print(json.dumps({'chosen': str(SE._catalog_path()),\n"
            "                  'route': SE.route_model()}))\n"
            % os.path.join(core, "audio_c3", "extend", "suno_extend.py")
        )
        run, out = _run_loader(script, tmp)
        check("the installer layout runs the loader cleanly",
              run.returncode == 0, (run.returncode, run.stderr[-800:]))
        check("the walk finds nothing there, so the locator names the catalog",
              os.path.abspath(out.get("chosen", "")) == target, out.get("chosen"))
        check("the installer catalog is the one actually read",
              out.get("route") == "suno-extend/installer-locator",
              out.get("route"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    test_every_sold_model_has_a_cap_or_a_named_refusal()
    test_the_two_new_rows_carry_their_source()
    test_a_sold_model_with_no_cap_refuses()
    test_catalog_loads_with_no_path_argument()
    test_catalog_order_is_module_position_not_import()
    test_installed_layout_still_resolves_via_the_locator()
    print()
    if FAILS:
        print("FAILED: %d" % len(FAILS))
        for name in FAILS:
            print("  - %s" % name)
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
