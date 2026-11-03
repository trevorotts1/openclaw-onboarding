#!/usr/bin/env python3
"""
library-gate-repair-clears-gate.test.py — the front-door library gate must be CLEARABLE.

The defect (repo-fix libgate): the health gate reported 153 of 3480 role playbooks and
SOP files as empty, thin or placeholder, and a clean update could not clear them,
because the repair side never reached the files the gate judges:

  1. a role folder holding IDENTITY.md with no how-to.md was "missing how-to.md" to
     the gate and invisible to the repair (the repair skipped absent paths);
  2. the repair read stub signatures from the title line only, the gate from the
     first 600 bytes, so a body marker (and every non-hyphen dash form) was fatal
     to the gate and invisible to the repair;
  3. a routing notice for a department the library does not cover had no
     deterministic rung that could ever replace it;
  4. a dept-level legacy stub had no owner (the library ships
     how-to-use-this-department.md, never how-to.md);
  5. on a <workspace>/departments layout with no build state the repair could not
     resolve the tree at all (rc 2) while the gate resolved and failed it;
  6. update-skills.sh returned early when the PRE-install verdict was clean, so a
     tree broken BY the install was never re-judged.

Round 2 (the round-1 verify refutation). The branch left THREE gate-fatal classes the
repair could not reach, so the gate still failed after a clean update:

  7. an EMPTY or thin role how-to.md with no installer signature classified as None
     ("real content"), so the 0-byte and 55-byte files the gate names were never
     touched; a thin file may hold real owner words, so the repair APPENDS the shipped
     library body and keeps every original byte as the prefix;
  8. SOP files under <role>/sops/ were never walked at all (the gate walks every .md
     under a sops/ container, whole-file, no size floor);
  9. flat role files under <dept>/roles/ were never walked either (the gate judges
     them, no size floor);
 10. a TRUE dept-level stub/routing notice (departments/<dept>/how-to.md) for a
     department the library does not cover had no deterministic writer and stayed
     gate-fatal as REVIEW.

Run:
    python3 tests/unit/library-gate-repair-clears-gate.test.py
No network, no model, no box. Writes only under a temporary directory.
Exit: 0 green; 1 regressed.
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
SCRIPTS = REPO / "23-ai-workforce-blueprint" / "scripts"
GATE = REPO / "scripts" / "health" / "library-gate-check.sh"
FRONTDOOR = REPO / "shared-utils" / "oct4_frontdoor.py"
MIN_BYTES = 3072
ROUTED_MARKER = "[ROUTED — WORK HANDLED BY GENERAL-TASK]"
SIG = re.compile(
    r"PENDING\W{0,4}FILL FROM LIBRARY"
    r"|how-to\.md \(stub\)"
    r"|to be personalized based on research"
    r"|\[\s*step\s+\d+\s*[-–—]\s*to be personalized"
    r"|\[ROUTED\W{1,6}WORK HANDLED BY GENERAL-TASK\]",
    re.IGNORECASE)

FAIL = 0
DEFECTS = []


def ok(msg):
    print("  PASS: " + msg)


def bad(msg):
    global FAIL
    FAIL = 1
    DEFECTS.append(msg)
    print("  FAIL: " + msg)


def build_env(home, ws, state_file=None):
    env = {
        "HOME": str(home),
        "PATH": "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
        "LANG": "C.UTF-8",
        "OPENCLAW_ROOT": str(ws),
        "OPENCLAW_MAINTENANCE_SILENT": "1",
    }
    if state_file is not None:
        env["WORKFORCE_BUILD_STATE_FILE"] = str(state_file)
    return env


def routed_text():
    """The exact bytes create_role_workspaces.routing_how_to() emits for devops."""
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(
        "crw_for_test", SCRIPTS / "create_role_workspaces.py")
    crw = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(crw)
    return crw.routing_how_to("Zeta Beacon Operator", "Devops", "devops",
                              "Acme", "consulting", "sop-needed-0001", "")


def build_tree(ws, layout):
    """The five staged entries (+ a clean general-task dept the gate needs to pass)."""
    dd = (ws / "company" / "departments") if layout == "B" else (ws / "departments")
    acme = dd / "acme"

    director = acme / "01-director-acme"
    director.mkdir(parents=True)
    (director / "IDENTITY.md").write_text("# Director of Acme\n", encoding="utf-8")
    (director / "how-to.md").write_text(
        "# Director of Acme — how-to.md\n\n"
        "**Department:** Acme\n\n## Weekly routine\n\n"
        + "".join("- Step %d: review the department queue and report.\n" % i
                  for i in range(1, 120)),
        encoding="utf-8")

    ident = acme / "02-identity-only"
    ident.mkdir()
    (ident / "IDENTITY.md").write_text("# Identity Only\n", encoding="utf-8")

    emdash = acme / "03-emdash-stub"
    emdash.mkdir()
    (emdash / "how-to.md").write_text(
        "# Emdash Stub — how-to.md\n\n> [PENDING — FILL FROM LIBRARY]\n\n"
        "## What This Role Does\n\n(Pending.)\n", encoding="utf-8")

    deptstub = acme / "04-dept-stub"
    deptstub.mkdir()
    (deptstub / "how-to.md").write_text(
        "# Acme — how-to.md (stub) [PENDING - FILL FROM LIBRARY]\n", encoding="utf-8")

    unmatched = acme / "05-unmatched"
    unmatched.mkdir()
    (unmatched / "how-to.md").write_text(routed_text(), encoding="utf-8")

    gt = dd / "general-task" / "01-head-of-general-task"
    gt.mkdir(parents=True)
    (gt / "IDENTITY.md").write_text("# Head of General Task\n", encoding="utf-8")
    (gt / "how-to.md").write_text(
        "# Head of General Task — how-to.md\n\n## Routing procedure\n\n"
        + "".join("- Step %d: intake, classify and route the task.\n" % i
                  for i in range(1, 120)),
        encoding="utf-8")
    return dd


def run_gate(dd, ws, env):
    return subprocess.run(["bash", str(GATE), "--departments-dir", str(dd),
                           "--workspace", str(ws)],
                          capture_output=True, text=True, env=env, timeout=300)


def snapshot(tree):
    return {str(p.relative_to(tree)): p.read_bytes()
            for p in sorted(tree.rglob("*")) if p.is_file()}


def gate_verdict_line(stdout):
    for ln in stdout.splitlines():
        if "placeholder-files:" in ln:
            return ln
    return ""


def is_placeholder_file(text):
    """A pure installer stub: a signature in the head and no real body."""
    return bool(text) and bool(SIG.search(text[:600])) and len(text.encode()) < MIN_BYTES


# ---------------------------------------------------------------------------
# Layout A / B: one front-door run must clear the gate
# ---------------------------------------------------------------------------
def check_layout(layout, root):
    print("\n[layout %s] one oct4_frontdoor run, then the gate must PASS" % layout)
    home = root / "home"
    ws = home / ".openclaw" / "workspace"
    ws.mkdir(parents=True)
    # the updater delivers the skills tree at <root>/skills
    os.symlink(str(REPO), str(ws / "skills"))
    state_file = None
    if layout == "B":
        (ws / "company").mkdir()
        state_file = ws / ".workforce-build-state.json"
        state_file.write_text(json.dumps({"companyRoot": str(ws / "company")}),
                              encoding="utf-8")
    dd = build_tree(ws, layout)
    env = build_env(home, ws, state_file)

    # --- CONTROL: the untouched tree must FAIL, or the acceptance proves nothing ---
    control = run_gate(dd, ws, env)
    want = ["02-identity-only", "03-emdash-stub", "04-dept-stub", "05-unmatched"]
    line = gate_verdict_line(control.stdout)
    if control.returncode == 1 and "placeholder-files: FAIL" in line:
        ok("control: gate fails the untouched tree (%s)" % line.strip())
    else:
        bad("control: gate did not fail the untouched tree (rc=%s, %s)"
            % (control.returncode, line.strip() or control.stderr[-300:]))
    missing = [n for n in want if n not in control.stdout]
    if not missing:
        ok("control: gate names all four staged entries")
    else:
        bad("control: gate did not name %s" % ", ".join(missing))

    director_before = (dd / "acme" / "01-director-acme" / "how-to.md").read_bytes()
    before = snapshot(dd)

    # --- the ONE invocation the acceptance names: no arguments ---
    r = subprocess.run([sys.executable, str(FRONTDOOR)], cwd=str(ws), env=env,
                       capture_output=True, text=True, timeout=1800)
    out = (r.stdout or "") + "\n" + (r.stderr or "")
    print("\n".join("    | " + ln for ln in out.strip().splitlines()))

    bad_steps = [ln for ln in out.splitlines()
                 if re.search(r"repair\s+\S+\s+(needs-attention|failed)\b", ln)]
    if not bad_steps:
        ok("run_repair_runner has no step whose meaning is needs-attention or failed")
    else:
        bad("repair step(s) reported needs-attention/failed: %s" % bad_steps)
    if "gate                   pass" in out:
        ok("the front-door health gate passed inside the same run")
    else:
        bad("the front-door health gate did not pass inside the run")

    # --- gate re-run on the repaired tree ---
    after = run_gate(dd, ws, env)
    line2 = gate_verdict_line(after.stdout)
    if after.returncode == 0 and "placeholder-files: PASS - 0 of" in line2:
        ok("gate PASS after the run (%s)" % line2.strip())
    else:
        bad("gate did not pass after the run (rc=%s, %s)"
            % (after.returncode, line2.strip() or after.stderr[-300:]))
        for ln in after.stdout.splitlines():
            if "    - " in ln:
                print("      " + ln.strip())

    for rel in ("acme/02-identity-only", "acme/03-emdash-stub",
                "acme/04-dept-stub", "acme/05-unmatched"):
        p = dd / rel / "how-to.md"
        if not p.is_file():
            bad("%s/how-to.md was not written" % rel)
            continue
        txt = p.read_text(encoding="utf-8", errors="replace")
        if len(txt.encode()) >= MIN_BYTES and not SIG.search(txt[:600]):
            ok("%s/how-to.md is a real playbook (%d bytes, no signature)"
               % (rel, len(txt.encode())))
        else:
            bad("%s/how-to.md is still thin/placeholder (%d bytes)" % (rel, len(txt.encode())))
    if ROUTED_MARKER not in (dd / "acme" / "05-unmatched" / "how-to.md").read_text(
            encoding="utf-8", errors="replace"):
        ok("the routing notice was replaced, not left behind")

    # --- nothing client-authored touched; deletions only of pure stubs ---
    director_after = (dd / "acme" / "01-director-acme" / "how-to.md").read_bytes()
    if director_after.startswith(director_before):
        ok("real playbook preserved (append-only; nothing overwritten)")
    else:
        bad("the repair rewrote a real playbook instead of preserving it")
    now = snapshot(dd)
    removed = [k for k in before if k not in now]
    wrongly = [k for k in removed
               if not is_placeholder_file(before[k].decode("utf-8", "replace"))]
    if not removed:
        ok("no file deleted")
    elif not wrongly:
        ok("only pure stubs were deleted (%s)" % ", ".join(removed))
    else:
        bad("non-stub file(s) deleted: %s" % wrongly)


# ---------------------------------------------------------------------------
# deterministic_fill must stay reachable (the hyphenated import regression)
# ---------------------------------------------------------------------------
def check_deterministic_fill(root):
    print("\n[deterministic_fill] author-missing-sops can import fill-pending-howtos")
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    # No installed marker dir under this temporary HOME: name the platform instead of
    # letting detect_platform raise SystemExit out of library resolution.
    os.environ.setdefault("OPENCLAW_PLATFORM", "mac")
    spec = importlib.util.spec_from_file_location(
        "author_missing_sops", SCRIPTS / "author-missing-sops.py")
    ams = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ams)

    dd = root / "df" / "departments"
    good = dd / "sales" / "appointment-setter"
    good.mkdir(parents=True)
    (good / "how-to.md").write_text(
        "# Appointment Setter — how-to.md  %s\n\n> routing notice\n" % ROUTED_MARKER,
        encoding="utf-8")
    rec = {"department": "sales", "role": "Appointment Setter",
           "role_folder": str(good), "how_to_path": str(good / "how-to.md")}
    okk, why = ams.deterministic_fill(rec, dd)
    if okk and "deterministic fill via" in why:
        ok("deterministic_fill fills a matched role (%s)" % why)
    else:
        bad("deterministic_fill failed on a matched role: %s" % why)
    txt = (good / "how-to.md").read_text(encoding="utf-8", errors="replace")
    if len(txt.encode()) >= MIN_BYTES and not SIG.search(txt[:600]):
        ok("the deterministic fill produced a real playbook (%d bytes)" % len(txt.encode()))
    else:
        bad("the deterministic fill produced a thin/placeholder file")

    miss = dd / "devops" / "zeta-beacon-operator"
    miss.mkdir(parents=True)
    (miss / "how-to.md").write_text(
        "# Zeta Beacon Operator — how-to.md  %s\n\n> routing notice\n" % ROUTED_MARKER,
        encoding="utf-8")
    rec2 = {"department": "devops", "role": "Zeta Beacon Operator",
            "role_folder": str(miss), "how_to_path": str(miss / "how-to.md")}
    okk2, why2 = ams.deterministic_fill(rec2, dd)
    if not okk2 and "no comparable template" in why2:
        ok("an uncovered department still needs authoring (%s)" % why2)
    elif "fill-pending-howtos unavailable" in why2:
        bad("deterministic_fill still cannot import fill-pending-howtos: %s" % why2)
    else:
        bad("deterministic_fill behaviour on an uncovered role changed: %s" % why2)


# ---------------------------------------------------------------------------
# Round 1's refutation tree: the exact five file classes the gate named
# ---------------------------------------------------------------------------
# A thin file that is NOT a stub may hold real owner words, so the repair must APPEND.
# Both fixtures below are the refutation's exact shapes and sizes.
THIN_REAL = b"# Thin Role - how-to.md\n\nOwner keeps the vendor calendar here.\n"[:55]
PLAYBOOK_REAL = ("# Playbook Role - how-to.md\n\n## Weekly routine\n\n"
                 + "".join("- Step %d: run the playbook check.\n" % i
                           for i in range(1, 200))).encode()[:2757]
DEPT_STUB = "# {t} — how-to.md (stub) [PENDING - FILL FROM LIBRARY]\n"


def real_playbook(title):
    return ("# %s — how-to.md\n\n## Weekly routine\n\n" % title
            + "".join("- Step %d: review the queue and report.\n" % i
                      for i in range(1, 120)))


def add_general_task(dd):
    gt = dd / "general-task" / "01-head-of-general-task"
    gt.mkdir(parents=True)
    (gt / "IDENTITY.md").write_text("# Head of General Task\n", encoding="utf-8")
    (gt / "how-to.md").write_text(
        "# Head of General Task — how-to.md\n\n## Routing procedure\n\n"
        + "".join("- Step %d: intake, classify and route the task.\n" % i
                  for i in range(1, 120)), encoding="utf-8")


def run_frontdoor(ws, env):
    """The ONE invocation the acceptance names: oct4_frontdoor.py with NO arguments."""
    r = subprocess.run([sys.executable, str(FRONTDOOR)], cwd=str(ws), env=env,
                       capture_output=True, text=True, timeout=1800)
    out = (r.stdout or "") + "\n" + (r.stderr or "")
    print("\n".join("    | " + ln for ln in out.strip().splitlines()))
    return r, out


def check_refutation_tree(root):
    print("\n[refutation tree] 0-byte/thin roles, SOPs and flat roles: ONE no-arg run")
    home = root / "home"
    ws = home / ".openclaw" / "workspace"
    ws.mkdir(parents=True)
    os.symlink(str(REPO), str(ws / "skills"))
    env = build_env(home, ws)
    dd = ws / "departments"
    acme = dd / "acme"

    if len(THIN_REAL) != 55 or len(PLAYBOOK_REAL) != 2757:
        bad("fixture drift: thin=%d playbook=%d, want 55 and 2757"
            % (len(THIN_REAL), len(PLAYBOOK_REAL)))
    # a clean director playbook (the control's clean file, and the director item)
    d = acme / "01-director-acme"
    d.mkdir(parents=True)
    (d / "IDENTITY.md").write_text("# Director of Acme\n", encoding="utf-8")
    (d / "how-to.md").write_text(real_playbook("Director of Acme"), encoding="utf-8")
    # (1) a 0-byte role how-to.md
    d = acme / "02-empty-role"
    d.mkdir()
    (d / "IDENTITY.md").write_text("# Empty Role\n", encoding="utf-8")
    (d / "how-to.md").write_bytes(b"")
    # (2) a 55-byte REAL role how-to.md: owner words that must survive byte-for-byte
    d = acme / "03-thin-role"
    d.mkdir()
    (d / "IDENTITY.md").write_text("# Thin Role\n", encoding="utf-8")
    (d / "how-to.md").write_bytes(THIN_REAL)
    # (3) a real playbook of 2757 bytes: under the 3072 floor, so gate-fatal
    d = acme / "04-playbook-role"
    d.mkdir()
    (d / "IDENTITY.md").write_text("# Playbook Role\n", encoding="utf-8")
    (d / "how-to.md").write_bytes(PLAYBOOK_REAL)
    # (4) a 0-byte SOP under <role>/sops/
    d = acme / "05-sop-role"
    d.mkdir()
    (d / "IDENTITY.md").write_text("# Sop Role\n", encoding="utf-8")
    (d / "how-to.md").write_text(real_playbook("Sop Role"), encoding="utf-8")
    (d / "sops").mkdir()
    (d / "sops" / "SOP-DIU-101.md").write_bytes(b"")
    # (5) a 0-byte flat role file under <dept>/roles/
    f = acme / "roles"
    f.mkdir()
    (f / "legacy-role.md").write_bytes(b"")
    add_general_task(dd)

    five = ("acme/02-empty-role/how-to.md", "acme/03-thin-role/how-to.md",
            "acme/04-playbook-role/how-to.md", "acme/05-sop-role/sops/SOP-DIU-101.md",
            "acme/roles/legacy-role.md")

    # --- CONTROL: the round-1 verdict must reproduce before the repair ---
    control = run_gate(dd, ws, env)
    line = gate_verdict_line(control.stdout)
    if control.returncode == 1 and "placeholder-files: FAIL" in line:
        ok("control: gate fails the untouched five-file tree (%s)" % line.strip())
    else:
        bad("control: gate did not fail the five-file tree (rc=%s, %s)"
            % (control.returncode, line.strip() or control.stderr[-300:]))
    missing = [n for n in five if n not in control.stdout]
    if not missing:
        ok("control: the gate names all five classes")
    else:
        bad("control: the gate did not name %s" % ", ".join(missing))

    before = {rel: (dd / rel).read_bytes() for rel in five}

    r, out = run_frontdoor(ws, env)

    bad_steps = [ln for ln in out.splitlines()
                 if re.search(r"repair\s+\S+\s+(needs-attention|failed)\b", ln)]
    if not bad_steps:
        ok("run_repair_runner has no step whose meaning is needs-attention or failed")
    else:
        bad("repair step(s) reported needs-attention/failed: %s" % bad_steps)
    if "gate                   pass" in out:
        ok("the front-door health gate passed inside the same run")
    else:
        bad("the front-door health gate did not pass inside the run")
    if r.returncode == 0:
        ok("front door exit 0")
    else:
        bad("front door exited %d" % r.returncode)

    after = run_gate(dd, ws, env)
    line2 = gate_verdict_line(after.stdout)
    if after.returncode == 0 and "placeholder-files: PASS - 0 of" in line2:
        ok("gate PASS after the run (%s)" % line2.strip())
    else:
        bad("gate did not pass after the run (rc=%s, %s)"
            % (after.returncode, line2.strip() or after.stderr[-300:]))
        for ln in after.stdout.splitlines():
            if "    - " in ln:
                print("      " + ln.strip())

    # --- a thin file's own bytes are NEVER replaced or truncated ---
    for rel in five:
        p = dd / rel
        if not p.is_file():
            bad("%s is no longer a file (a thin client file was deleted)" % rel)
            continue
        data = p.read_bytes()
        if data.startswith(before[rel]):
            ok("%s keeps every original byte as its prefix (%d -> %d bytes)"
               % (rel, len(before[rel]), len(data)))
        else:
            bad("%s does not start with its original bytes (rewritten)" % rel)
    for rel in ("acme/03-thin-role/how-to.md", "acme/04-playbook-role/how-to.md"):
        txt = (dd / rel).read_text(encoding="utf-8", errors="replace")
        if len(txt.encode()) >= MIN_BYTES and not SIG.search(txt[:600]):
            ok("%s now clears the 3072-byte floor (%d bytes)"
               % (rel, len(txt.encode())))
        else:
            bad("%s is still thin/placeholder (%d bytes)" % (rel, len(txt.encode())))
    for rel in ("acme/05-sop-role/sops/SOP-DIU-101.md", "acme/roles/legacy-role.md"):
        txt = (dd / rel).read_text(encoding="utf-8", errors="replace")
        if txt.strip() and not SIG.search(txt[:600]):
            ok("%s filled from shipped library content (%d bytes)"
               % (rel, len(txt.encode())))
        else:
            bad("%s is still empty/placeholder" % rel)
    flat = (dd / "acme" / "roles" / "legacy-role.md").read_text(
        encoding="utf-8", errors="replace")
    if "generator=repair-placeholder-sops.py" in flat:
        ok("the flat role file carries shipped-library provenance")


def check_dept_level_stub(root):
    print("\n[dept-level stub] departments/<dept>/how-to.md itself, NOT a role folder")
    home = root / "home"
    ws = home / ".openclaw" / "workspace"
    ws.mkdir(parents=True)
    os.symlink(str(REPO), str(ws / "skills"))
    env = build_env(home, ws)
    dd = ws / "departments"
    # a department the role library DOES cover: filled from its shipped dept guide
    covered = dd / "sales"
    covered.mkdir(parents=True)
    (covered / "how-to.md").write_text(DEPT_STUB.format(t="Sales"), encoding="utf-8")
    # a department the library does NOT cover: the true round-1 hole
    uncovered = dd / "zzq-vertical"
    uncovered.mkdir()
    (uncovered / "how-to.md").write_text(DEPT_STUB.format(t="Zzq Vertical"),
                                         encoding="utf-8")
    add_general_task(dd)

    control = run_gate(dd, ws, env)
    line = gate_verdict_line(control.stdout)
    if (control.returncode == 1 and "sales/how-to.md" in control.stdout
            and "zzq-vertical/how-to.md" in control.stdout):
        ok("control: gate fails BOTH dept-level stubs at the department root (%s)"
           % line.strip())
    else:
        bad("control: gate did not fail both dept-level stubs (rc=%s, %s)"
            % (control.returncode, line.strip() or control.stderr[-300:]))

    r, out = run_frontdoor(ws, env)
    if r.returncode == 0 and "gate                   pass" in out:
        ok("one no-arg front-door run clears both dept-level stubs")
    else:
        bad("the front-door run did not clear the dept-level stubs")

    after = run_gate(dd, ws, env)
    line2 = gate_verdict_line(after.stdout)
    if after.returncode == 0 and "placeholder-files: PASS - 0 of" in line2:
        ok("gate PASS after the run (%s)" % line2.strip())
    else:
        bad("gate did not pass after the run (rc=%s, %s)"
            % (after.returncode, line2.strip() or after.stderr[-300:]))

    p = covered / "how-to.md"
    txt = p.read_text(encoding="utf-8", errors="replace") if p.is_file() else ""
    if (txt.strip() and not SIG.search(txt[:600])
            and "how to use the sales department" in txt.lower()):
        ok("sales/how-to.md is the shipped department guide (%d bytes)"
           % len(txt.encode()))
    else:
        bad("sales/how-to.md was not filled from the shipped department guide")
    q = uncovered / "how-to.md"
    if not q.exists():
        ok("zzq-vertical/how-to.md: pure installer stub removed, gate no longer sees it")
    else:
        txt = q.read_text(encoding="utf-8", errors="replace")
        if txt.strip() and not SIG.search(txt[:600]):
            ok("zzq-vertical/how-to.md filled from shipped content (%d bytes)"
               % len(txt.encode()))
        else:
            bad("zzq-vertical/how-to.md is still a gate-fatal placeholder")


def main():
    if shutil.which("python3") is None or shutil.which("bash") is None:
        print("cannot run: python3/bash missing", file=sys.stderr)
        return 1
    if shutil.which("openclaw") is not None:
        print("note: an openclaw binary is on PATH; the sandbox env still excludes it",
              file=sys.stderr)
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        for label, fn, arg in (("layout A", check_layout, ("A", root / "layoutA")),
                               ("layout B", check_layout, ("B", root / "layoutB")),
                               ("deterministic_fill", check_deterministic_fill,
                                (root / "unit",)),
                               ("refutation tree", check_refutation_tree,
                                (root / "refute",)),
                               ("dept-level stub", check_dept_level_stub,
                                (root / "deptstub",))):
            try:
                fn(*arg)
            except SystemExit as e:
                bad("%s aborted with SystemExit(%s) instead of a verdict" % (label, e.code))
    if FAIL:
        print("\nlibrary-gate-repair-clears-gate: FAIL")
        return 1
    print("\nlibrary-gate-repair-clears-gate: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
