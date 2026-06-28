#!/usr/bin/env python3
"""
prove-zhe.py — the ZERO HUMAN EXPERIENCE (ZHE) acceptance prover (W1.3).

Deterministic, receipt-backed, single per-box wrapping gate that asserts the WHOLE
Zero Human Experience fired for an interview-completed box. PURE CODE — no LLM is ever
involved in the counting or the verdict. Models the FS-abstraction + receipt + box-access
pattern on ~/clawd/fleet-prover/prove-floor.py (which this file does NOT edit).

It proves, with receipts, the four ZHE wrappings the spec/plan name (spec §1 steps 4–7):
  (a) FLOOR DEPARTMENTS present AND registered as agents — built-as-files AND
      registered-as-agents in openclaw.json agents.list[] (not just folders on disk).
  (b) PERSONAS CANONICAL — 54 canonical personas + canonical persona-categories.json
      + a section-tagged coaching-personas index (gemini-index.sqlite, ~4413 rows,
      section_number/mode tags applied, NOT default-only).
  (c) COMMAND CENTER board reachable — mission-control.db present, `workspaces` table
      live (>=1 row), AND a board lane per floor department.
  (d) AGENTS.md DOCTRINE — carries routing doctrine + persona reflex + full-context
      handoff + reporting rules + platform facts markers.

EXEMPTION (spec §1 + §3 edge case): a box that has NOT completed the interview has NO ZHE
obligation. It is EXEMPT — the prover records exempt=true, skips the four checks, and passes
(exit 0). Only interview-completed boxes are held to the full ZHE.

  ====================================================================================
  INTEGRATION POINTS (where this file gets wired in at integration time)
  ------------------------------------------------------------------------------------
  • LIVES AT:   23-ai-workforce-blueprint/scripts/prove-zhe.py        (plan W1.3)
  • INVOKED BY: run-full-install.sh phase 6 (extend the wiring assert; plan W1.2/W1.3)
                23-ai-workforce-blueprint/scripts/verify-library-gate.sh
                  (highest-priority verdict, alongside the canonical-authoring check)
  • MODELED ON: ~/clawd/fleet-prover/prove-floor.py  (FS abstraction, secrets loader,
                box-registry resolution, receipt write — mirrored, NOT imported, so this
                gate is standalone)
  • READS / ASSERTS AGAINST (real call sites it is built to verify):
      - interview state .workforce-build-state.json  (schema: 23-ai-workforce-blueprint/
        build-state-schema.json; key `interviewComplete`) → EXEMPTION
      - openclaw.json agents.list[] entries `id: dept-<slug>` written by
        32-command-center-setup/scripts/materialize-dept-agents.sh:221-262   → check (a)
      - personas dir + index: shared-utils/embedding_engine.py:133-134
        (WORKSPACE_ROOT/data/coaching-personas/{personas,gemini-index.sqlite});
        section tags written by 23-ai-workforce-blueprint/scripts/section-tag-migration.py
        (embeddings.mode / embeddings.section_number); canonical categories
        persona-categories.json (PRD 2.7 canonical: workspace/data/coaching-personas/)  → (b)
      - mission-control.db candidates: materialize-dept-agents.sh:436-438 (+ projects/*)
        `workspaces` table rows = board lanes                                  → check (c)
      - AGENTS.md at WORKSPACE/AGENTS.md (apply-fleet-standards.sh:530) with markers:
          routing:   CEO_ORCHESTRATOR_RULE_V* / CEO_ROUTING_NO_LOOPHOLES_V1
                     (apply-fleet-standards.sh:469,584)
          persona-reflex / full-context-handoff / owner-reporting / platform-facts:
          stamped by W5.5 + W6 + W7.2 (apply-fleet-standards.sh ~:588).  This prover is
          authored RED-FIRST: the routing markers pass today; the persona/handoff/
          reporting/platform-facts assertions stay RED until W5/W6/W7 land them, which
          is the intended "build to turn it green" contract (plan §6).
  ====================================================================================

Usage:
  prove-zhe.py <box-id>                connect per box-registry.json and prove the live box
  prove-zhe.py --local <oc-root>       prove a local OpenClaw root (dir containing
                                       openclaw.json + workspace/) — for tests/fixtures
  prove-zhe.py <box-id> --registry P   use an alternate box-registry.json
  prove-zhe.py <box-id> --with-subprovers   additionally run sibling per-workstream provers
                                            (prove-floor.py, prove-custom-dept-wiring.py)
                                            if present; absent ones are recorded "skipped",
                                            never failing the gate.

Receipt: receipts/<box>-<UTCiso>.json   — {box, overall_pass, exempt, checks:{...}, ts, ...}
Exit code: 0 iff overall_pass (or exempt) is true, else 1; 2 on bad invocation.
"""
import json, os, sys, datetime, subprocess, shlex, re, base64

HERE = os.path.dirname(os.path.abspath(__file__))
REGISTRY_PATH = os.path.join(HERE, "box-registry.json")
RECEIPTS_DIR = os.path.join(HERE, "receipts")

PROVER_VERSION = "1.0"

# --- ZHE canonical expectations (spec §1 + persona system facts) --------------
# VALIDATED 2026-06-28 against the live operator box
# (~/.clawdbot/workspace/data/coaching-personas/gemini-index.sqlite):
#   table 'embeddings' present; rows=4413; cols include mode + section_number;
#   persona dirs=54; section_number NOT NULL=3172; mode in (leadership,coaching)=944.
# Magic numbers match the canonical box exactly — left as canonical, not re-read.
EXPECTED_PERSONA_COUNT = 54          # canonical coaching/leadership persona library
EXPECTED_INDEX_ROWS = 4413           # section-tagged coaching-personas index size
INDEX_ROW_FLOOR_RATIO = 0.90         # tolerate minor re-embed variance, never zero
INDEX_ROW_FLOOR = int(EXPECTED_INDEX_ROWS * INDEX_ROW_FLOOR_RATIO)

# Department folders the prover ignores when discovering floor depts (mirror
# 32-command-center-setup/scripts/materialize-dept-agents.sh:163 SKIP_SLUGS).
SKIP_SLUGS = {
    ".git", ".cache", ".workforce-build-state.json",
    "templates", "shared", "_archive", "node_modules",
}

# Sibling per-workstream provers folded in under --with-subprovers (plan: W1.3
# "by delegating to the per-workstream provers"). Absent => skipped, never a FAIL.
SUBPROVERS = ["prove-custom-dept-wiring.py", "prove-floor.py"]


# ---------------------------------------------------------------------------
# Secrets loader — reads KEY=VALUE lines from secrets env files so SSH
# ProxyCommand var interpolations (${CF_ACCESS_*}) resolve. Mirrors prove-floor.
# ---------------------------------------------------------------------------
_SECRETS_CACHE = None

# Build secrets file candidates via get_openclaw_paths() so the legacy ~/clawd
# path is resolved by the canonical path-authority (PRD 1.9 / AF3 compliance)
# rather than a hardcoded local candidate loop.
try:
    import sys as _sys
    _here = os.path.dirname(os.path.abspath(__file__))
    _shared = os.path.join(_here, "..", "..", "shared-utils")
    if _shared not in _sys.path:
        _sys.path.insert(0, _shared)
    from detect_platform import get_openclaw_paths as _get_oc_paths  # type: ignore
    _oc_paths = _get_oc_paths()
    _SECRETS_FILES = [str(_oc_paths["secrets"] / ".env")]
except Exception:
    # Fallback to the canonical new-install path only (legacy ~/clawd excluded
    # per AF3; detect_platform handles it when importable).
    _SECRETS_FILES = [os.path.expanduser("~/.openclaw/secrets/.env")]


def _load_secrets():
    global _SECRETS_CACHE
    if _SECRETS_CACHE is not None:
        return _SECRETS_CACHE
    result = {}
    for path in _SECRETS_FILES:
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, _, val = line.partition("=")
                    key = key.strip()
                    val = val.strip().strip("'\"")
                    if key:
                        result[key] = val
        except OSError:
            pass
    _SECRETS_CACHE = result
    return result


def _subprocess_env():
    env = dict(os.environ)
    env.update(_load_secrets())
    return env


def die(msg):
    print(f"FATAL: {msg}", file=sys.stderr)
    sys.exit(2)


def utc_now_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _remote_quote(path):
    """Quote a remote path; expand a leading ~ to $HOME on the remote shell
    (shlex.quote would single-quote and suppress tilde expansion)."""
    if path == "~":
        return '"$HOME"'
    if path.startswith("~/"):
        return '"$HOME/' + path[2:].replace('"', '\\"') + '"'
    return shlex.quote(path)


# ---------------------------------------------------------------------------
# Filesystem accessor abstraction (mirrors prove-floor.py LocalFS/RemoteFS).
# Local mode uses python os; remote mode runs read-only shell probes over SSH
# (+ docker exec for VPS). Adds run()/box_python() so the counting logic can run
# a sqlite query inside the box without ever mutating it.
# ---------------------------------------------------------------------------

class LocalFS:
    """`root` is a local OpenClaw root (a dir containing openclaw.json + workspace/)."""

    def __init__(self, root):
        self.root = os.path.abspath(os.path.expanduser(root))

    def resolve_oc_root(self):
        return self.root if os.path.isfile(os.path.join(self.root, "openclaw.json")) else None

    def isdir(self, path):
        return os.path.isdir(os.path.expanduser(path))

    def isfile(self, path):
        return os.path.isfile(os.path.expanduser(path))

    def listdir(self, path):
        try:
            return sorted(os.listdir(os.path.expanduser(path)))
        except OSError:
            return []

    def read_text(self, path):
        try:
            with open(os.path.expanduser(path), encoding="utf-8") as f:
                return f.read()
        except OSError:
            return None

    def run(self, cmd):
        # `cmd` is ALWAYS an internally-built, shlex-quoted string from box_python()
        # (never raw user input). Use the explicit `/bin/sh -c` argv list form rather
        # than shell=True so no implicit shell-string parsing of caller data occurs.
        try:
            p = subprocess.run(["/bin/sh", "-c", cmd], capture_output=True, text=True,
                               timeout=90, env=_subprocess_env())
            return p.returncode, p.stdout, p.stderr
        except (subprocess.TimeoutExpired, OSError) as e:
            return 255, "", str(e)


class RemoteFS:
    """Runs read-only probes on a remote box. VPS: ssh root@ip -> docker exec -u node <ctr>.
    Mac: ssh <alias> -> zsh -lc. Mirrors prove-floor.py RemoteFS; never mutates the box."""

    def __init__(self, box_id, entry):
        self.box_id = box_id
        self.entry = entry
        self.kind = entry["kind"]

    def _wrap(self, remote_cmd):
        if self.kind == "vps":
            inner = f"docker exec -u node {shlex.quote(self.entry['container'])} sh -c {shlex.quote(remote_cmd)}"
            return ["ssh", "-o", "BatchMode=yes", self.entry["ssh_target"], inner]
        elif self.kind == "mac":
            target = self.entry["ssh_alias"]
            if self.entry.get("ssh_user"):
                target = f"{self.entry['ssh_user']}@{target}"
            inner = f"zsh -lc {shlex.quote(remote_cmd)}"
            return ["ssh", "-o", "BatchMode=yes", target, inner]
        else:
            die(f"unknown box kind {self.kind!r}")

    def run(self, remote_cmd):
        argv = self._wrap(remote_cmd)
        try:
            p = subprocess.run(argv, capture_output=True, text=True, timeout=120,
                               env=_subprocess_env())
            return p.returncode, p.stdout, p.stderr
        except (subprocess.TimeoutExpired, OSError) as e:
            return 255, "", str(e)

    def resolve_oc_root(self):
        # VPS container layout first, then Mac/home layout (mirror apply-fleet-standards.sh:59-63).
        for cand in ("/data/.openclaw", "~/.openclaw"):
            rc, out, _ = self.run(f"test -f {_remote_quote(cand + '/openclaw.json')} && echo OK")
            if rc == 0 and out.strip() == "OK":
                rc2, out2, _ = self.run(f"cd {_remote_quote(cand)} && pwd")
                return out2.strip() if rc2 == 0 and out2.strip() else cand
        return None

    def isdir(self, path):
        rc, out, _ = self.run(f"test -d {_remote_quote(path)} && echo OK")
        return rc == 0 and out.strip() == "OK"

    def isfile(self, path):
        rc, out, _ = self.run(f"test -f {_remote_quote(path)} && echo OK")
        return rc == 0 and out.strip() == "OK"

    def listdir(self, path):
        rc, out, _ = self.run(f"ls -1A {_remote_quote(path)} 2>/dev/null")
        if rc != 0:
            return []
        return sorted(x for x in out.splitlines() if x)

    def read_text(self, path):
        rc, out, _ = self.run(f"cat {_remote_quote(path)} 2>/dev/null")
        return out if rc == 0 else None


def box_python(fs, code):
    """Run a python3 snippet INSIDE the box (read-only) and return the JSON dict it
    prints on its last line. base64-wrapped so quoting survives docker exec / zsh -lc.
    Python3 is on every VPS container and Mac. Returns {} on any failure."""
    b = base64.b64encode(code.encode("utf-8")).decode("ascii")
    cmd = "python3 -c " + shlex.quote(
        f"import base64;exec(base64.b64decode('{b}').decode())"
    )
    rc, out, _ = fs.run(cmd)
    if rc != 0 or not out:
        return {}
    for line in reversed(out.splitlines()):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                return json.loads(line)
            except ValueError:
                continue
    return {}


# ---------------------------------------------------------------------------
# Config + path helpers
# ---------------------------------------------------------------------------

def load_openclaw_config(fs, oc_root):
    txt = fs.read_text(os.path.join(oc_root, "openclaw.json"))
    if txt is None:
        return None
    try:
        return json.loads(txt)
    except ValueError:
        return None


def workspace_root(fs, oc_root, cfg):
    """Resolve the agent workspace root. Prefer agents.defaults.workspace; default to
    OC_ROOT/workspace (the documented default in apply-fleet-standards.sh:525-527)."""
    if isinstance(cfg, dict):
        ws = (((cfg.get("agents") or {}).get("defaults") or {}).get("workspace"))
        if isinstance(ws, str) and ws:
            return ws
    return os.path.join(oc_root, "workspace")


def discover_departments(fs, oc_root):
    """Discover department folders (built-as-files). Mirrors materialize-dept-agents.sh
    DEPT_ROOTS. Returns a dict slug -> workspace_path (first root wins)."""
    roots = [
        os.path.join(oc_root, "workspace", "departments"),
        os.path.join(oc_root, "workspaces", "command-center"),
    ]
    found = {}
    for root in roots:
        if not fs.isdir(root):
            continue
        for name in fs.listdir(root):
            if name.startswith(".") or name.startswith("_") or name in SKIP_SLUGS:
                continue
            full = os.path.join(root, name)
            if not fs.isdir(full):
                continue
            found.setdefault(name, full)
    return found


# ---------------------------------------------------------------------------
# CHECK (a): floor departments present AND registered as agents (not just files)
# ---------------------------------------------------------------------------

def check_depts_registered(fs, oc_root, cfg):
    depts = discover_departments(fs, oc_root)
    agent_ids = set()
    if isinstance(cfg, dict):
        for a in (((cfg.get("agents") or {}).get("list")) or []):
            if isinstance(a, dict) and a.get("id"):
                agent_ids.add(a["id"])
    # materialize-dept-agents.sh registers each dept as agent id "dept-<slug>".
    registered, unregistered = [], []
    for slug in sorted(depts):
        if f"dept-{slug}" in agent_ids:
            registered.append(slug)
        else:
            unregistered.append(slug)
    present = len(depts) > 0
    return {
        "pass": bool(present and not unregistered),
        "departments_present": sorted(depts.keys()),
        "depts_present_count": len(depts),
        "registered_as_agents": registered,
        "files_without_agent": unregistered,
        "agents_list_count": len(agent_ids),
        "detail": (
            "no department folders present (ZHE step 2/4 did not build)" if not present
            else (f"{len(unregistered)} dept folder(s) not registered as agents "
                  f"(built-as-files only): {', '.join(unregistered)}" if unregistered
                  else f"all {len(depts)} departments built AND registered as agents")
        ),
    }


# ---------------------------------------------------------------------------
# CHECK (b): personas canonical (54 + categories + section-tagged ~4413 index)
# ---------------------------------------------------------------------------

def check_personas_canonical(fs, ws):
    cp = os.path.join(ws, "data", "coaching-personas")
    personas_dir = os.path.join(cp, "personas")
    persona_dirs = [d for d in fs.listdir(personas_dir)
                    if not d.startswith(".") and fs.isdir(os.path.join(personas_dir, d))]
    persona_count = len(persona_dirs)

    # Canonical categories file — PRD 2.7 canonical write target first, then fallbacks.
    cat_candidates = [
        os.path.join(cp, "persona-categories.json"),
        os.path.join(ws, "22-book-to-persona-coaching-leadership-system", "persona-categories.json"),
    ]
    cat_txt, cat_path = None, None
    for c in cat_candidates:
        cat_txt = fs.read_text(c)
        if cat_txt is not None:
            cat_path = c
            break
    categories_ok = False
    cat_persona_keys = 0
    domain_tags = 0
    if cat_txt:
        try:
            cat = json.loads(cat_txt)
            cat_persona_keys = len(cat.get("personas", {}) or {})
            domain_tags = len(cat.get("domainTags", []) or [])
            # canonical = has the domain-tag vocabulary AND a real persona roster.
            categories_ok = domain_tags > 0 and cat_persona_keys >= EXPECTED_PERSONA_COUNT
        except ValueError:
            categories_ok = False

    # Section-tagged index — query the live sqlite inside the box, read-only.
    index_db = os.path.join(cp, "gemini-index.sqlite")
    idx = box_python(fs, _SQL_INDEX_PROBE.format(db=repr(index_db)))
    idx_rows = int(idx.get("rows", 0) or 0)
    idx_tagged = int(idx.get("tagged", 0) or 0)
    idx_has_mode = bool(idx.get("has_mode"))
    idx_has_section = bool(idx.get("has_section"))
    index_ok = (
        bool(idx.get("exists")) and idx_rows >= INDEX_ROW_FLOOR
        and idx_has_mode and idx_has_section and idx_tagged > 0
    )

    personas_ok = persona_count >= EXPECTED_PERSONA_COUNT
    return {
        "pass": bool(personas_ok and categories_ok and index_ok),
        "personas_present": persona_count,
        "personas_expected": EXPECTED_PERSONA_COUNT,
        "categories_path": cat_path,
        "categories_persona_keys": cat_persona_keys,
        "categories_domain_tags": domain_tags,
        "categories_ok": categories_ok,
        "index_db_exists": bool(idx.get("exists")),
        "index_rows": idx_rows,
        "index_rows_floor": INDEX_ROW_FLOOR,
        "index_rows_expected": EXPECTED_INDEX_ROWS,
        "index_section_tagged_rows": idx_tagged,
        "index_has_mode_col": idx_has_mode,
        "index_has_section_col": idx_has_section,
        "index_error": idx.get("error"),
        "detail": (
            f"personas {persona_count}/{EXPECTED_PERSONA_COUNT} "
            f"categories={'ok' if categories_ok else 'MISSING/NON-CANONICAL'} "
            f"index_rows={idx_rows}(floor {INDEX_ROW_FLOOR}) tagged={idx_tagged}"
        ),
    }


_SQL_INDEX_PROBE = """
import sqlite3, json, os
p = {db}
r = {{"exists": os.path.exists(p)}}
if r["exists"]:
    try:
        c = sqlite3.connect(p, timeout=30.0); cur = c.cursor()
        cols = [x[1] for x in cur.execute("PRAGMA table_info(embeddings)").fetchall()]
        r["has_mode"] = "mode" in cols
        r["has_section"] = "section_number" in cols
        r["rows"] = cur.execute("SELECT count(*) FROM embeddings").fetchone()[0]
        # "tagged" = GENUINELY section-tagged, NOT default-only. section-tag-migration.py
        # adds mode with DEFAULT 'both' and backfills NULL->'both', so a migrated-but-
        # untagged box has mode='both' EVERYWHERE and section_number all NULL. Counting
        # only mode IN ('leadership','coaching') would false-negative a valid index whose
        # canonical blueprint happened to map every chunk to a 'both' section; counting
        # section_number IS NOT NULL is the true "tagging ran" signal. Use the max of both
        # so default-only stays 0 (RED) while any real tagging reads > 0.
        # Live operator box: section_number NOT NULL=3172, mode in lead/coach=944 of 4413.
        r["mode_tagged"] = (cur.execute(
            "SELECT count(*) FROM embeddings WHERE mode IN ('leadership','coaching')"
        ).fetchone()[0]) if r["has_mode"] else 0
        r["section_tagged"] = (cur.execute(
            "SELECT count(*) FROM embeddings WHERE section_number IS NOT NULL"
        ).fetchone()[0]) if r["has_section"] else 0
        r["tagged"] = max(r["mode_tagged"], r["section_tagged"])
        c.close()
    except Exception as e:
        r["error"] = str(e)
print(json.dumps(r))
"""


# ---------------------------------------------------------------------------
# CHECK (c): Command Center board reachable + dept lanes present
# ---------------------------------------------------------------------------

def check_command_center(fs, oc_root, dept_slugs):
    candidates = [
        os.path.join(oc_root, "workspaces", "command-center", "mission-control.db"),
        os.path.join(oc_root, "workspace", "mission-control.db"),
        os.path.join(oc_root, "data", "mission-control.db"),
        "/data/projects/command-center/mission-control.db",
        "~/projects/command-center/mission-control.db",
        "~/projects/mission-control/mission-control.db",
        "/opt/mission-control/mission-control.db",
    ]
    db_path = next((c for c in candidates if fs.isfile(c)), None)
    if db_path is None:
        return {
            "pass": False, "db_found": False, "db_candidates": candidates,
            "detail": "mission-control.db not found among candidates (CC not provisioned)",
        }
    cc = box_python(fs, _SQL_CC_PROBE.format(db=repr(db_path)))
    tables = cc.get("tables", []) or []
    rows = int(cc.get("workspace_rows", 0) or 0)
    lane_blob = cc.get("lane_blob", []) or []
    # dept lanes present: each discovered dept slug appears in some workspaces row.
    lanes_missing = []
    for slug in sorted(dept_slugs):
        needle = slug.lower()
        if not any(needle in blob for blob in lane_blob):
            lanes_missing.append(slug)
    has_ws_table = "workspaces" in tables
    board_live = has_ws_table and rows > 0
    return {
        "pass": bool(board_live and not lanes_missing),
        "db_found": True,
        "db_path": db_path,
        "has_workspaces_table": has_ws_table,
        "workspace_rows": rows,
        "dept_lanes_missing": lanes_missing,
        "cc_error": cc.get("error"),
        "detail": (
            "workspaces table absent" if not has_ws_table
            else "board has 0 workspace rows (dead board)" if rows == 0
            else (f"{len(lanes_missing)} dept lane(s) missing: {', '.join(lanes_missing)}"
                  if lanes_missing else f"board live: {rows} lane(s), all depts present")
        ),
    }


_SQL_CC_PROBE = """
import sqlite3, json, os
p = {db}
r = {{}}
try:
    c = sqlite3.connect(p, timeout=30.0); cur = c.cursor()
    tabs = [x[0] for x in cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    r["tables"] = tabs
    if "workspaces" in tabs:
        r["workspace_rows"] = cur.execute("SELECT count(*) FROM workspaces").fetchone()[0]
        rows = cur.execute("SELECT * FROM workspaces").fetchall()
        r["lane_blob"] = [" ".join(str(v) for v in row).lower() for row in rows]
    c.close()
except Exception as e:
    r["error"] = str(e)
print(json.dumps(r))
"""


# ---------------------------------------------------------------------------
# CHECK (d): AGENTS.md carries the ZHE doctrine markers
# ---------------------------------------------------------------------------
# Each doctrine element is satisfied by ANY of its accepted markers/headings, so the
# prover survives the exact marker-token choice. RED-first: routing passes today; the
# persona-reflex / handoff / reporting / platform-facts assertions go green once
# W5.5 / W6 / W7.2 stamp them via apply-fleet-standards.sh (plan §6).
AGENTS_DOCTRINE = {
    "routing": [
        r"CEO_ORCHESTRATOR_RULE_V\d+", r"CEO_ROUTING_NO_LOOPHOLES_V\d+",
        r"route[s]?\s+(?:the\s+)?task[s]?\s+to\s+(?:the\s+)?(?:right\s+)?department",
    ],
    "persona_reflex": [
        r"PERSONA_REFLEX_V\d+", r"persona[\s-]reflex", r"persona[\s-]match(?:ing)?",
    ],
    "full_context_handoff": [
        r"FULL_CONTEXT_HANDOFF_V\d+", r"full[\s-]context\s+handoff",
        r"pointer\s+ref(?:erence)?s?", r"where\s+the\s+document(?:ation|s)\b",
    ],
    "reporting": [
        r"OWNER_REPORTING_V\d+", r"REPORTING_RULES_V\d+", r"Reporting\s+to\s+the\s+owner",
        r"report[s]?\s+back\s+to\s+the\s+owner",
    ],
    "platform_facts": [
        r"PLATFORM_FACTS_V\d+", r"platform\s+facts",
        r"here\s+is\s+WHERE\s+your\s+environments?\s+file",
    ],
}


def check_agents_md_doctrine(fs, ws, oc_root):
    agents_path = next(
        (p for p in (os.path.join(ws, "AGENTS.md"), os.path.join(oc_root, "AGENTS.md"))
         if fs.isfile(p)), None)
    if agents_path is None:
        return {
            "pass": False, "agents_md_found": False,
            "elements": {k: False for k in AGENTS_DOCTRINE},
            "detail": "AGENTS.md not found at WORKSPACE/AGENTS.md or OC_ROOT/AGENTS.md",
        }
    text = fs.read_text(agents_path) or ""
    elements, missing = {}, []
    for element, patterns in AGENTS_DOCTRINE.items():
        ok = any(re.search(p, text, re.IGNORECASE) for p in patterns)
        elements[element] = ok
        if not ok:
            missing.append(element)
    return {
        "pass": not missing,
        "agents_md_found": True,
        "agents_md_path": agents_path,
        "elements": elements,
        "missing_elements": missing,
        "detail": ("all 5 doctrine elements present"
                   if not missing else f"missing doctrine: {', '.join(missing)}"),
    }


# ---------------------------------------------------------------------------
# Optional sibling sub-provers (additive; absent => skipped, never a FAIL)
# ---------------------------------------------------------------------------

def run_subprovers(box_id, local_root):
    results = {}
    for name in SUBPROVERS:
        path = os.path.join(HERE, name)
        if not os.path.isfile(path):
            results[name] = {"status": "skipped", "reason": "prover not present in repo yet"}
            continue
        argv = [sys.executable, path] + (
            ["--local", local_root] if local_root else [box_id])
        try:
            p = subprocess.run(argv, capture_output=True, text=True, timeout=600,
                               env=_subprocess_env())
            results[name] = {
                "status": "pass" if p.returncode == 0 else "fail",
                "exit_code": p.returncode,
            }
        except (subprocess.TimeoutExpired, OSError) as e:
            results[name] = {"status": "error", "reason": str(e)}
    return results


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def prove(box_id, client, fs, local_root=None, with_subprovers=False):
    receipt = {
        "box": box_id,
        "client": client,
        "ts": utc_now_iso(),
        "prover_version": PROVER_VERSION,
        "reachable": False,
        "interview_complete": None,
        "exempt": False,
        "oc_root": "",
        "workspace": "",
        "checks": {},
        "overall_pass": False,
    }

    oc_root = fs.resolve_oc_root()
    if not oc_root:
        receipt["detail"] = "UNREACHABLE — no OpenClaw root (openclaw.json) located"
        return receipt
    receipt["reachable"] = True
    receipt["oc_root"] = oc_root

    cfg = load_openclaw_config(fs, oc_root)
    ws = workspace_root(fs, oc_root, cfg)
    receipt["workspace"] = ws

    # ----- EXEMPTION: interview not completed => no ZHE obligation -----
    state_txt = fs.read_text(os.path.join(ws, ".workforce-build-state.json"))
    interview_complete = False
    if state_txt:
        try:
            interview_complete = bool(json.loads(state_txt).get("interviewComplete"))
        except ValueError:
            interview_complete = False
    receipt["interview_complete"] = interview_complete

    if not interview_complete:
        receipt["exempt"] = True
        receipt["overall_pass"] = True
        receipt["detail"] = ("interview NOT completed — box EXEMPT from ZHE "
                             "(no obligation); checks skipped")
        return receipt

    # ----- THE FOUR ZHE WRAPPINGS -----
    a = check_depts_registered(fs, oc_root, cfg)
    dept_slugs = a["departments_present"]
    receipt["checks"]["floor_depts_registered_as_agents"] = a
    receipt["checks"]["personas_canonical"] = check_personas_canonical(fs, ws)
    receipt["checks"]["command_center_board"] = check_command_center(fs, oc_root, dept_slugs)
    receipt["checks"]["agents_md_doctrine"] = check_agents_md_doctrine(fs, ws, oc_root)

    if with_subprovers:
        receipt["subprovers"] = run_subprovers(box_id, local_root)

    core_ok = all(c["pass"] for c in receipt["checks"].values())
    sub_ok = all(r.get("status") in ("pass", "skipped")
                 for r in receipt.get("subprovers", {}).values())
    receipt["overall_pass"] = bool(core_ok and sub_ok)
    return receipt


def print_summary(r):
    print(f"=== ZHE PROOF: {r['box']} ({r.get('client', '')}) ===")
    print(f"reachable={r['reachable']}  interview_complete={r['interview_complete']}  "
          f"oc_root={r['oc_root'] or '(none)'}")
    if not r["reachable"]:
        print("UNREACHABLE — cannot prove ZHE.")
        print(f"OVERALL: {'PASS' if r['overall_pass'] else 'FAIL'}")
        return
    if r["exempt"]:
        print("EXEMPT — interview not completed; box carries no ZHE obligation.")
        print("OVERALL: PASS (exempt)")
        return
    for name, c in r["checks"].items():
        print(f"  [{'PASS' if c['pass'] else 'FAIL'}] {name}: {c.get('detail', '')}")
    for name, sub in r.get("subprovers", {}).items():
        print(f"  [{sub['status'].upper()}] subprover {name}")
    print(f"OVERALL: {'PASS' if r['overall_pass'] else 'FAIL'}")


def write_receipt(r):
    os.makedirs(RECEIPTS_DIR, exist_ok=True)
    safe = r["ts"].replace(":", "").replace("+00:00", "Z")
    path = os.path.join(RECEIPTS_DIR, f"{r['box']}-{safe}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(r, f, indent=2, ensure_ascii=False)
    return path


def main(argv):
    args = argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        sys.exit(2)

    with_subprovers = False
    if "--with-subprovers" in args:
        with_subprovers = True
        args = [a for a in args if a != "--with-subprovers"]

    registry_path = REGISTRY_PATH
    if "--registry" in args:
        i = args.index("--registry")
        try:
            registry_path = args[i + 1]
            del args[i:i + 2]
        except IndexError:
            die("--registry requires a path")

    local_root = None
    if args and args[0] == "--local":
        if len(args) != 2:
            die("--local requires exactly one OpenClaw-root path")
        local_root = os.path.abspath(os.path.expanduser(args[1]))
        if not os.path.isdir(local_root):
            die(f"--local root does not exist: {local_root}")
        fs = LocalFS(local_root)
        box_id, client = "LOCAL", "local-fixture"
    elif len(args) == 1:
        box_id = args[0]
        if not os.path.isfile(registry_path):
            die(f"box-registry.json not found at {registry_path}")
        with open(registry_path, encoding="utf-8") as f:
            registry = json.load(f)
        entry = registry.get("boxes", {}).get(box_id)
        if not entry:
            die(f"box-id {box_id!r} not in registry {registry_path}")
        fs = RemoteFS(box_id, entry)
        client = entry.get("client", "")
    else:
        print(__doc__)
        sys.exit(2)

    receipt = prove(box_id, client, fs, local_root=local_root, with_subprovers=with_subprovers)
    path = write_receipt(receipt)
    print_summary(receipt)
    print(f"receipt: {path}")
    sys.exit(0 if receipt["overall_pass"] else 1)


if __name__ == "__main__":
    main(sys.argv)
