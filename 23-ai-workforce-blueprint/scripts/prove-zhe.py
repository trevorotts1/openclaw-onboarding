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
  (b) PERSONAS CANONICAL — the full canonical persona roster (count DERIVED from the
      persona-categories.json index, not a fixed literal) + canonical persona-categories.json
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

WEB↔TELEGRAM BUILD PARITY (WG-6) — proves a client built through the web
/interview path is byte-equal (same gates + EQUAL provisioning receipt/
expected-set) to a telegram-built one, with NO genuine-build shortcuts:
  prove-zhe.py --web-parity            materialize the shipped fixture pair into a
                                       sandbox temp dir and prove parity (good => 0)
  prove-zhe.py --web-parity --web-root W --ref-root R
                                       prove parity between two REAL OpenClaw roots
  prove-zhe.py --web-parity --shortcut <k>
                                       seed a shortcut into the fixture's WEB root
                                       (missing-decision | synthetic-header |
                                        unprovenanced-decline | receipt-divergence);
                                       a good gate FAILS (exit 1) on any of them
  prove-zhe.py --web-parity-selftest   NON-VACUOUS meta-gate: prove the mode PASSES
                                       on the good fixture and FAILS on EVERY seeded
                                       shortcut (exit 0 iff all expectations hold).
                                       This is the entrypoint the CI wiring calls.

Receipt: receipts/<box>-<UTCiso>.json   — {box, overall_pass, exempt, checks:{...}, ts, ...}
Exit code: 0 iff overall_pass (or exempt) is true, else 1; 2 on bad invocation.
"""
import json, os, sys, datetime, subprocess, shlex, re, base64

HERE = os.path.dirname(os.path.abspath(__file__))
REGISTRY_PATH = os.path.join(HERE, "box-registry.json")
RECEIPTS_DIR = os.path.join(HERE, "receipts")

PROVER_VERSION = "1.0"

# ZHE_SEQUENCE_V1 — the canonical, versioned constant naming the Zero Human
# Experience sequence this prover holds an interview-completed box to (spec §1
# steps 4–7; doctrine doc: 23-ai-workforce-blueprint/ZERO-HUMAN-EXPERIENCE.md).
# Defined as an actual referenced constant (NOT just a comment): it is the
# `ordered`-step contract the prover proves, and it is stamped into every receipt
# (see prove()) so each receipt records WHICH sequence version it asserted.
ZHE_SEQUENCE_V1 = (
    "floor_depts_registered_as_agents",  # step 4: built-as-files AND registered as agents
    "personas_canonical",                # step 5: full derived persona roster + section-tagged index
    "command_center_board",              # step 6: Command Center board + Kanban ready
    "agents_md_doctrine",                # step 7: AGENTS.md routing/persona/handoff/reporting/platform-facts
)

# --- ZHE canonical expectations (spec §1 + persona system facts) --------------
# VALIDATED 2026-06-28 against the live operator box
# (~/.clawdbot/workspace/data/coaching-personas/gemini-index.sqlite):
#   table 'embeddings' present; rows=4413; cols include mode + section_number;
#   persona dirs=54; section_number NOT NULL=3172; mode in (leadership,coaching)=944.
#
# The persona library GROWS over time (Skill 22 shipped 54, now ships 65, more
# later), so the *expected* persona count is DERIVED at runtime from the canonical
# persona index (persona-categories.json roster) rather than pinned to a magic
# number that rots. PERSONA_LIBRARY_FLOOR is only a hard sanity minimum: a roster
# below this is definitely truncated/broken, independent of how large it grows.
PERSONA_LIBRARY_FLOOR = 40           # hard sanity minimum; real expected count is derived
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

# --- WEB↔TELEGRAM build-parity constants (WG-6) --------------------------------
# The exact banner build-workforce.build_from_config() stamps onto a
# from-config (non-interactive) transcript — IDENTICAL to
# qc-interview-completion.NON_INTERACTIVE_ANSWERS_HEADER. A transcript carrying
# it WITHOUT an ownerConsent record is fabricated, not owner-authored.
NON_INTERACTIVE_ANSWERS_HEADER = "# Workforce Interview Answers (Non-Interactive)"

# Decision tokens that count as an EXPLICIT owner opt-in to a self-setup / fast
# (from-config) build — mirrors qc-interview-completion._CONSENT_OPT_IN_DECISIONS.
_CONSENT_OPT_IN_DECISIONS = frozenset({
    "self-setup", "self_setup", "selfsetup",
    "fast", "fast-mode", "fast_mode", "fastmode",
    "decline-interview", "decline_interview", "skip-interview", "skip_interview",
    "opt-in", "opt_in", "optin",
})

# The receipt fields that MUST be identical between a web-built and a
# telegram-built client (canonical expected-set equality). generatedAt/company
# are intentionally excluded — parity is about the department SET, not timestamps.
PARITY_RECEIPT_FIELDS = (
    "expectedSet", "builtSet", "declined", "later",
    "acceptedCustoms", "verticalAdded", "equalityOk",
)

# Shared provenance reader (canonical_decline.py) — the SAME module
# build-workforce.py / department-floor.py / qc-interview-completion.py use, so
# the genuineness gate cannot drift from the real decline/coverage logic. Import
# is defensive: if the shared reader is unavailable the genuineness gate FAILS
# (cannot prove "no shortcuts" => not a pass), never silently green.
try:
    import canonical_decline as _decline  # noqa: E402  (HERE is on sys.path below)
except Exception:  # pragma: no cover - import guarded, re-tried in _load_decline
    _decline = None


def _load_decline():
    global _decline
    if _decline is not None:
        return _decline
    try:
        if HERE not in sys.path:
            sys.path.insert(0, HERE)
        import canonical_decline as _cd  # noqa: E402
        _decline = _cd
    except Exception:
        _decline = None
    return _decline


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
# CHECK (b): personas canonical (roster DERIVED from index + categories + section-tagged ~4413 index)
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
            # canonical = has the domain-tag vocabulary AND a real persona roster
            # (roster must clear the hard sanity floor; its exact size is derived).
            categories_ok = domain_tags > 0 and cat_persona_keys >= PERSONA_LIBRARY_FLOOR
        except ValueError:
            categories_ok = False

    # DERIVED expectation: the canonical roster size declared in the persona index
    # (persona-categories.json). The on-disk persona dirs must match/exceed the
    # index, so the check tracks the library automatically and can never rot to a
    # stale literal. Guard with the hard floor so a missing/stub index can't make
    # the expectation trivially satisfiable (empty index => cat_persona_keys 0).
    expected_persona_count = max(cat_persona_keys, PERSONA_LIBRARY_FLOOR)

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

    personas_ok = persona_count >= expected_persona_count
    return {
        "pass": bool(personas_ok and categories_ok and index_ok),
        "personas_present": persona_count,
        "personas_expected": expected_persona_count,
        "personas_expected_source": (
            "persona-categories.json roster" if cat_persona_keys >= PERSONA_LIBRARY_FLOOR
            else f"sanity floor {PERSONA_LIBRARY_FLOOR}"
        ),
        "personas_library_floor": PERSONA_LIBRARY_FLOOR,
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
            f"personas {persona_count}/{expected_persona_count} "
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
# CHECK (e): provisioning receipt — EXPECTED-SET EQUALITY (Bulletproofing c)
# ---------------------------------------------------------------------------

def check_provisioning_receipt(fs, oc_root, ws, dept_slugs):
    """
    Assert the EXPECTED-SET EQUALITY invariant written by build-workforce.py at
    build end (provisioning-receipt.json). Unlike every other gate — which only
    checks "at least the floor" — this fails on OVER-provisioning too: if a
    provenance-declined department was built (the residual over-provision bug), the receipt's
    equalityOk is false and/or the declined dept is still on disk now.

    A box built BEFORE receipts existed has no receipt; that is non-blocking here
    (receipt_present=false, pass) so this check never regresses an already-green
    legacy box. Once a build writes the receipt, over/under-provision FAILS.
    """
    candidates = [
        os.path.join(ws, "provisioning-receipt.json"),
        os.path.join(oc_root, "workspace", "provisioning-receipt.json"),
    ]
    txt = None
    found = None
    for c in candidates:
        t = fs.read_text(c)
        if t:
            txt, found = t, c
            break
    if txt is None:
        return {
            "pass": True, "receipt_present": False,
            "detail": ("provisioning-receipt.json absent (pre-receipt build) — "
                       "expected-set equality not asserted (non-blocking)"),
        }
    try:
        rec = json.loads(txt)
    except ValueError:
        return {"pass": False, "receipt_present": True, "receipt_path": found,
                "detail": f"provisioning-receipt.json at {found} is unparseable"}

    equality_ok = bool(rec.get("equalityOk"))
    declined_but_built = rec.get("declinedButBuilt") or []
    missing_from_built = rec.get("missingFromBuilt") or []

    # Re-verify against CURRENT on-disk departments: no provenance-declined dept
    # may still be present (catches drift/over-build after the build stamped it).
    def _n(s):
        return re.sub(r"[^a-z0-9]", "", str(s).lower())
    declined_norm = {_n(x) for x in (rec.get("declined") or [])}
    on_disk_norm = {_n(s) for s in dept_slugs}
    declined_on_disk_now = sorted(on_disk_norm & declined_norm)

    ok = equality_ok and not declined_on_disk_now
    if ok:
        detail = (f"expected-set equality holds "
                  f"(expected={rec.get('expectedCount')} built={rec.get('builtCount')}, "
                  f"0 declined depts built)")
    else:
        bits = []
        if declined_but_built:
            bits.append(f"receipt records OVER-provision (declined built): {declined_but_built}")
        if declined_on_disk_now:
            bits.append(f"declined dept(s) present on disk NOW: {declined_on_disk_now}")
        if missing_from_built:
            bits.append(f"UNDER-provision (expected missing): {missing_from_built}")
        if not equality_ok and not bits:
            bits.append(f"equalityOk=false ({rec.get('reason')})")
        detail = " | ".join(bits)

    return {
        "pass": bool(ok),
        "receipt_present": True,
        "receipt_path": found,
        "equality_ok": equality_ok,
        "declined_but_built": declined_but_built,
        "declined_on_disk_now": declined_on_disk_now,
        "missing_from_built": missing_from_built,
        "expected_count": rec.get("expectedCount"),
        "built_count": rec.get("builtCount"),
        "detail": detail,
    }


# ---------------------------------------------------------------------------
# WEB↔TELEGRAM build parity (WG-6): a web /interview-built client must clear the
# SAME gates AND land an EQUAL provisioning receipt as a telegram-built one, with
# NO genuine-build shortcuts. These add the two dimensions the five base gates do
# NOT inspect — decision/transcript GENUINENESS and cross-path receipt EQUALITY.
# ---------------------------------------------------------------------------

def _consent_opt_in(state):
    """True iff build-state carries a fully-provenanced self-setup/fast opt-in
    ownerConsent record (mirrors qc-interview-completion._validate_owner_consent).
    Such a record legitimizes a from-config (non-interactive) transcript."""
    consent = (state or {}).get("ownerConsent")
    if not isinstance(consent, dict):
        return False
    required = ("decision", "source", "decidedAt", "decidedBy", "sessionId")
    if any(not consent.get(k) for k in required):
        return False
    return str(consent.get("decision", "")).strip().lower() in _CONSENT_OPT_IN_DECISIONS


def check_web_build_genuineness(fs, ws):
    """
    Prove the WEB-built client was produced with NO genuine-build shortcut, using
    the SAME shared reader (canonical_decline) the real build uses. Three vectors,
    each an independent FAIL:

      (1) SYNTHETIC TRANSCRIPT — the interview answers carry the from-config
          Non-Interactive banner with no ownerConsent opt-in => fabricated.
      (2) MISSING DECISION — a department in the receipt's expected/declined set
          has NO provenanced yes/no/later decision (decision-coverage hole).
      (3) UNPROVENANCED DECLINE — a "no" recorded without the required provenance
          (the shared reader REJECTS it) => decline silently ignored.
    """
    decline = _load_decline()
    if decline is None:
        return {"pass": False, "detail": "canonical_decline shared reader unavailable — "
                "cannot prove build genuineness (fail-closed)"}

    # build-state (provenance) + transcript (genuineness banner).
    state = {}
    state_txt = fs.read_text(os.path.join(ws, ".workforce-build-state.json"))
    if state_txt:
        try:
            state = json.loads(state_txt)
        except ValueError:
            return {"pass": False, "detail": ".workforce-build-state.json is unparseable"}
    transcript = fs.read_text(os.path.join(ws, "workforce-interview-answers.md")) or ""

    # Expected decision-coverage universe: everything the receipt says should be
    # accounted for (built expected-set + provenance-declined). Derived from the
    # receipt so the gate stays self-contained (no canonical-floor dependency).
    rec = {}
    rec_txt = None
    for c in (os.path.join(ws, "provisioning-receipt.json"),):
        rec_txt = fs.read_text(c)
        if rec_txt:
            break
    if rec_txt:
        try:
            rec = json.loads(rec_txt)
        except ValueError:
            rec = {}
    expected_ids = list(rec.get("expectedSet") or []) + list(rec.get("declined") or [])

    # (1) synthetic transcript.
    synthetic = (transcript.lstrip().startswith(NON_INTERACTIVE_ANSWERS_HEADER)
                 and not _consent_opt_in(state))

    # (2) missing decision (shared reader — provenanced coverage only).
    missing, _covered = decline.decision_coverage(state, expected_ids)

    # (3) unprovenanced declines rejected by the shared reader.
    rejections = decline.analyze(state, quiet=True)["rejections"]
    rejected_ids = [r.get("id") for r in rejections]

    problems = []
    if synthetic:
        problems.append("SYNTHETIC transcript (Non-Interactive from-config banner, no "
                        "ownerConsent opt-in) — fabricated, not owner-authored")
    if missing:
        problems.append(f"MISSING provenanced decision(s): {', '.join(missing)}")
    if rejected_ids:
        problems.append(f"UNPROVENANCED decline(s) rejected: {', '.join(rejected_ids)}")

    return {
        "pass": not problems,
        "transcript_present": bool(transcript.strip()),
        "transcript_synthetic": synthetic,
        "decision_expected_count": len(set(_decline_norm_local(x) for x in expected_ids)),
        "decision_missing": missing,
        "unprovenanced_declines": rejected_ids,
        "detail": ("web build genuine: authored transcript + full provenanced "
                   "decision coverage + no unprovenanced declines"
                   if not problems else " | ".join(problems)),
    }


def _decline_norm_local(s):
    """Local mirror of canonical_decline.norm for counting only (never for a
    verdict — the verdict path always calls the shared reader)."""
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def _load_receipt_fields(fs, ws):
    txt = fs.read_text(os.path.join(ws, "provisioning-receipt.json"))
    if not txt:
        return None, "provisioning-receipt.json absent"
    try:
        rec = json.loads(txt)
    except ValueError:
        return None, "provisioning-receipt.json unparseable"
    return rec, None


def check_web_ref_parity(web_rec, ref_rec):
    """EXPECTED-SET EQUALITY across the two build paths: every canonical receipt
    field in PARITY_RECEIPT_FIELDS must be identical (normalized, order-insensitive
    for the set fields). A single divergence FAILS — a web-built client that does
    not match its telegram twin is not byte-equal."""
    if web_rec is None or ref_rec is None:
        return {"pass": False, "detail": "one or both provisioning receipts missing/unparseable"}

    def _canon(v):
        if isinstance(v, list):
            return sorted(_decline_norm_local(x) for x in v)
        return v

    diffs = {}
    for field in PARITY_RECEIPT_FIELDS:
        w, r = _canon(web_rec.get(field)), _canon(ref_rec.get(field))
        if w != r:
            diffs[field] = {"web": w, "ref": r}
    return {
        "pass": not diffs,
        "compared_fields": list(PARITY_RECEIPT_FIELDS),
        "diverging_fields": sorted(diffs.keys()),
        "diffs": diffs,
        "detail": ("web receipt == telegram receipt across "
                   f"{len(PARITY_RECEIPT_FIELDS)} canonical fields"
                   if not diffs else "receipt DIVERGENCE on: "
                   + ", ".join(f"{k}({v['web']} != {v['ref']})" for k, v in diffs.items())),
    }


def prove_web_parity(web_root, ref_root):
    """Full web/telegram parity proof. Returns a parity receipt dict.

    overall_pass is TRUE iff:
      * the web root passes ALL five base ZHE gates, AND
      * the reference (telegram) root passes ALL five base ZHE gates, AND
      * the web build is GENUINE (no synthetic transcript / missing decision /
        unprovenanced decline), AND
      * the web receipt EQUALS the reference receipt (expected-set equality).
    """
    fs_web, fs_ref = LocalFS(web_root), LocalFS(ref_root)
    r_web = prove("WEB-BUILD", "web-interview", fs_web, local_root=web_root)
    r_ref = prove("REF-TELEGRAM", "telegram-interview", fs_ref, local_root=ref_root)

    ws_web = r_web.get("workspace") or os.path.join(web_root, "workspace")
    web_rec, web_rec_err = _load_receipt_fields(fs_web, ws_web)
    ref_rec, _ref_rec_err = _load_receipt_fields(
        fs_ref, r_ref.get("workspace") or os.path.join(ref_root, "workspace"))

    genuineness = check_web_build_genuineness(fs_web, ws_web)
    parity = check_web_ref_parity(web_rec, ref_rec)

    web_ok = bool(r_web.get("overall_pass"))
    ref_ok = bool(r_ref.get("overall_pass"))
    overall = web_ok and ref_ok and genuineness["pass"] and parity["pass"]

    return {
        "mode": "web-telegram-parity",
        "ts": utc_now_iso(),
        "prover_version": PROVER_VERSION,
        "web_root": web_root,
        "ref_root": ref_root,
        "gates": {
            "web_base_zhe_pass": web_ok,
            "ref_base_zhe_pass": ref_ok,
            "web_build_genuine": genuineness,
            "web_ref_receipt_parity": parity,
        },
        "web_base_receipt_error": web_rec_err,
        "web_checks": r_web.get("checks", {}),
        "ref_checks": r_ref.get("checks", {}),
        "overall_pass": overall,
    }


def print_parity_summary(r):
    print(f"=== WEB↔TELEGRAM PARITY PROOF ({r['mode']}) ===")
    print(f"web_root={r['web_root']}")
    print(f"ref_root={r['ref_root']}")
    g = r["gates"]
    print(f"  [{'PASS' if g['web_base_zhe_pass'] else 'FAIL'}] web base ZHE gates")
    print(f"  [{'PASS' if g['ref_base_zhe_pass'] else 'FAIL'}] telegram base ZHE gates")
    gen = g["web_build_genuine"]
    print(f"  [{'PASS' if gen['pass'] else 'FAIL'}] web build genuine: {gen.get('detail','')}")
    par = g["web_ref_receipt_parity"]
    print(f"  [{'PASS' if par['pass'] else 'FAIL'}] receipt parity: {par.get('detail','')}")
    print(f"OVERALL: {'PASS' if r['overall_pass'] else 'FAIL'}")


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
        "zhe_sequence": "ZHE_SEQUENCE_V1",
        "zhe_sequence_steps": list(ZHE_SEQUENCE_V1),
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
    # Bulletproofing (c): expected-set equality (over- AND under-provision fail).
    receipt["checks"]["provisioning_receipt_equality"] = check_provisioning_receipt(
        fs, oc_root, ws, dept_slugs)

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


# ---------------------------------------------------------------------------
# Self-contained web-parity entrypoints (the clean invocation the wiring step
# calls). Materialize the shipped fixture into a sandbox temp dir, prove parity,
# clean up. Writes NOTHING under ~/.openclaw or ~/.clawdbot.
# ---------------------------------------------------------------------------

def _load_fixture_builder():
    if HERE not in sys.path:
        sys.path.insert(0, HERE)
    import prove_zhe_web_parity_fixture as _fx  # noqa: E402
    return _fx


def run_web_parity(web_root=None, ref_root=None, shortcut=None, write_dir=None):
    """Prove web↔telegram parity. If roots are omitted, materialize the shipped
    fixture (optionally seeding `shortcut`) into a private temp dir and prove
    against THAT. Returns (parity_receipt, exit_code)."""
    import tempfile, shutil
    tmp = None
    try:
        if web_root is None or ref_root is None:
            fx = _load_fixture_builder()
            tmp = tempfile.mkdtemp(prefix="zhe-web-parity-")
            web_root, ref_root = fx.build_pair(tmp, shortcut=shortcut)
        r = prove_web_parity(web_root, ref_root)
        r["seeded_shortcut"] = shortcut
        print_parity_summary(r)
        # Parity receipt goes into the fixture temp dir (or an explicit write_dir),
        # NEVER the repo receipts/ dir or any home path.
        out_dir = write_dir or tmp
        if out_dir:
            try:
                os.makedirs(out_dir, exist_ok=True)
                path = os.path.join(out_dir, "web-parity-receipt.json")
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(r, f, indent=2, ensure_ascii=False)
                print(f"parity receipt: {path}")
            except OSError:
                pass
        return r, (0 if r["overall_pass"] else 1)
    finally:
        if tmp and write_dir is None:
            shutil.rmtree(tmp, ignore_errors=True)


def web_parity_selftest():
    """NON-VACUOUS meta-gate: prove the parity mode PASSES on the good fixture and
    FAILS on EVERY seeded shortcut. Exit 0 iff all expectations hold. This is the
    invocation the CI wiring step should call — it proves the gate actually bites."""
    fx = _load_fixture_builder()
    results = []

    print("── web-parity self-test: GOOD fixture must PASS ──")
    _r, code = run_web_parity(shortcut=None)
    good_ok = (code == 0)
    results.append(("good", "PASS", "PASS" if good_ok else "FAIL", good_ok))

    all_ok = good_ok
    for shortcut in fx.VALID_SHORTCUTS:
        print(f"\n── web-parity self-test: seeded '{shortcut}' must FAIL ──")
        _r, code = run_web_parity(shortcut=shortcut)
        expect_fail_ok = (code == 1)
        results.append((shortcut, "FAIL", "FAIL" if expect_fail_ok else "PASS", expect_fail_ok))
        all_ok = all_ok and expect_fail_ok

    print("\n=== WEB-PARITY SELF-TEST MATRIX ===")
    for name, expected, got, ok in results:
        print(f"  [{'OK' if ok else 'XX'}] {name:<22} expected={expected} got={got}")
    print(f"SELF-TEST: {'PASS (gate is non-vacuous)' if all_ok else 'FAIL'}")
    return 0 if all_ok else 1


def main(argv):
    args = argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        sys.exit(2)

    # ----- WEB↔TELEGRAM parity modes (self-contained; no box-registry) -----
    if "--web-parity-selftest" in args:
        sys.exit(web_parity_selftest())
    if "--web-parity" in args:
        rest = [a for a in args if a != "--web-parity"]
        web_root = ref_root = shortcut = write_dir = None
        while rest:
            flag = rest.pop(0)
            if flag == "--web-root":
                web_root = rest.pop(0) if rest else die("--web-root requires a path")
            elif flag == "--ref-root":
                ref_root = rest.pop(0) if rest else die("--ref-root requires a path")
            elif flag == "--shortcut":
                shortcut = rest.pop(0) if rest else die("--shortcut requires a name")
            elif flag == "--write-dir":
                write_dir = rest.pop(0) if rest else die("--write-dir requires a path")
            else:
                die(f"unknown --web-parity flag: {flag}")
        if (web_root is None) != (ref_root is None):
            die("--web-root and --ref-root must be given together (or neither, to use the fixture)")
        if shortcut is not None:
            if web_root is not None:
                die("--shortcut only applies to the shipped fixture (omit --web-root/--ref-root)")
            _valid = _load_fixture_builder().VALID_SHORTCUTS
            if shortcut not in _valid:
                die(f"unknown --shortcut {shortcut!r}; valid: {', '.join(_valid)}")
        _r, code = run_web_parity(web_root=web_root, ref_root=ref_root,
                                  shortcut=shortcut, write_dir=write_dir)
        sys.exit(code)

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
