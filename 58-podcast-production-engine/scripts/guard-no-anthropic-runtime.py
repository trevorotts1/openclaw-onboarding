#!/usr/bin/env python3
# =============================================================================
# 58-PODCAST-PRODUCTION-ENGINE :: GUARD-NO-ANTHROPIC-RUNTIME (furnace Guardrail 5)
# -----------------------------------------------------------------------------
# DETERMINISTIC, NO-AI, FAIL-CLOSED. Rides the repo QC merge gate (same G-gate
# family) and runs at provisioning. Two independent jobs in one script:
#
#   JOB 1  FILE SCAN. Screen every shipped runtime file of the skill (skill
#          markdown, prompts, .py, .sh, .json, .yaml, and any dashboard source)
#          for concrete Anthropic model ids, provider slugs, npm packages,
#          bedrock ids, API hosts, and the ANTHROPIC_API_KEY / sk-ant- key
#          shapes. Any hit FAILS the build with the offending file and line.
#          The detector matches concrete id SHAPES (claude-opus-4..., sk-ant-,
#          us.anthropic.claude, api.anthropic.com, ANTHROPIC_API_KEY,
#          anthropic/claude-..., provider: anthropic), NOT the bare words
#          "claude" / "anthropic". A doc that STATES the never-Anthropic rule
#          and the routing config's own deny_patterns list [claude, anthropic,
#          opus, sonnet, haiku, us.anthropic] therefore stay clean, while a real
#          client-path model id is caught. Values are NEVER printed: a hit is
#          confirmed with file + line + pattern class only, never the matched
#          text (a secret is confirmed forbidden, never echoed).
#
#   JOB 2  ROUTING ASSERTION. Assert the routing config follows the
#          client-choice selection policy: a selection block whose order is
#          client choice first, then the client's configured default, ending
#          in the ask-the-client stop (on_unresolved: ask_client, never a
#          named fallback); deny_patterns armed and complete; NO configured
#          entry (client default or client chain, content or qc_judge)
#          matching a deny pattern; and the qc_judge default distinct from
#          the content default (judge independence). The shipped config
#          prescribes no model at all: its defaults ship unset, and routing
#          an unconfigured tier stops and asks the client. This is the static
#          proof that the runtime router cannot substitute to a denied model
#          (it refuses deny-pattern substitutions because no denied id is
#          ever configured and the deny_patterns list is armed).
#
#   DASHBOARD SCREEN (furnace Guardrail 2). For any directory passed with
#          --dashboard-dir (or an auto-detected <skill-root>/dashboard), the
#          screen is STRICTER: the dashboard is a dumb read-only view, so ANY
#          model-provider SDK import, ANY generation-endpoint host, or ANY
#          pipeline-script invocation / process spawn FAILS. better-sqlite3
#          (the CC dashboard's SQLite driver) is explicitly allowed.
#
# ALLOWLIST POLICY. config/anthropic-guard-allow.json may exempt a DOC file
#          explicitly marked non-runtime from JOB 1. An allowlist entry that
#          points at a runtime directory (scripts/, prompts/, config/, modules/,
#          dashboard/, ...) or at SKILL.md is REFUSED and FAILS the gate: the
#          runtime directories accept no allowlist entries. The dashboard screen
#          is never exemptable.
#
# EXIT: 0 PASS / 2 AUTOFAIL / 3 USAGE-IO.
# USAGE:
#   python3 guard-no-anthropic-runtime.py [--skill-root DIR] [TARGET ...]
#                 [--dashboard-dir DIR ...] [--routing-config FILE]
#                 [--require-routing] [--allow-file FILE] [--json]
#   python3 guard-no-anthropic-runtime.py --self-test
#
# When no TARGET is given the skill root is scanned. When no --routing-config is
# given the config dir is searched for a podcast_engine.models block; if none is
# found the routing assertion is reported SKIPPED unless --require-routing (the
# merge gate passes --require-routing once the config slice has landed).
# =============================================================================
"""Fail-closed Anthropic-in-runtime and routing-tier guard for the Podcast Production Engine."""

import argparse
import json
import os
import re
import sys
from pathlib import Path

try:
    import yaml  # PyYAML; optional. JSON configs never need it.
except Exception:  # pragma: no cover - environment without PyYAML
    yaml = None

EXIT_PASS = 0
EXIT_AUTOFAIL = 2
EXIT_USAGE = 3

AF_NOANTHROPIC = "AF-PPE-NOANTHROPIC"
AF_ROUTING = "AF-PPE-ROUTING"
AF_DASHBOARD = "AF-PPE-DASHBOARD"
AF_ALLOWLIST = "AF-PPE-ALLOWLIST"
AF_IO = "AF-PPE-IO"

_SELF = Path(__file__).resolve()

# Text file extensions that count as shipped runtime and get scanned.
_TEXT_EXT = {
    ".py", ".sh", ".bash", ".zsh", ".json", ".yaml", ".yml", ".md", ".txt",
    ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".env", ".cfg", ".ini",
    ".toml", ".html", ".css",
}
_SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv", ".next",
              "dist", "build", ".turbo", "coverage"}

# Directories inside the skill that are RUNTIME. An allowlist may never exempt a
# file living directly under one of these (nor SKILL.md).
_RUNTIME_DIR_NAMES = {
    "scripts", "prompts", "config", "modules", "lib", "src", "dashboard",
    "fixtures", "templates", "roles", "sop", "sops", "bin", "app", "pages",
    "components", "styles",
}

# --- Anthropic id SHAPES (concrete ids only; the bare word is intentionally
#     NOT matched so rule-stating prose and the deny_patterns list stay clean) -
_ANTHROPIC_PATTERNS = [
    # ROOT-ANCHORED (MODEL-01), matching the canonical shared-utils text detector
    # (claude- followed by one id char): any claude-<id-char> token, never a
    # per-generation enumeration. The old enumerated suffix list silently ALLOWED
    # an unenumerated future family id (a renamed/future claude-<family>
    # generation) to ship in a runtime file. It still stays prose-safe: a bare
    # word "claude", the claude-* wildcard, and the deny_patterns list never
    # carry claude-<alnum>.
    ("claude-model-id", re.compile(r"claude-[a-z0-9]", re.I)),
    ("anthropic-slash-model", re.compile(r"anthropic/claude-[a-z0-9]", re.I)),
    ("bedrock-anthropic", re.compile(r"us\.anthropic\.claude", re.I)),
    ("anthropic-npm", re.compile(r"@anthropic-ai/")),
    ("anthropic-env-key", re.compile(r"ANTHROPIC_API_KEY")),
    ("anthropic-api-host", re.compile(r"api\.anthropic\.com", re.I)),
    ("anthropic-key-value", re.compile(r"sk-ant-[A-Za-z0-9\-]{16,}")),
    ("provider-set-anthropic", re.compile(r"""provider["']?\s*[:=]\s*["']?anthropic\b""", re.I)),
]

# --- DASHBOARD stricter screen: no model-provider SDK, no generation endpoint,
#     no pipeline invocation. better-sqlite3 (CC dashboard SQLite driver) is explicitly allowed. -----------
_DASH_PROVIDER_IMPORT = [
    ("openai-sdk", re.compile(r"""(?:from|require\(|import)\s*["']openai["']|@ai-sdk/openai|new\s+OpenAI\b""", re.I)),
    ("google-genai-sdk", re.compile(r"@google/generative-ai|google\.generativeai|@google-cloud/aiplatform", re.I)),
    ("anthropic-sdk", re.compile(r"@anthropic-ai/|from\s*['\"]anthropic['\"]", re.I)),
    ("ollama-sdk", re.compile(r"""(?:from|require\(|import)\s*["']ollama["']""", re.I)),
    ("misc-llm-sdk", re.compile(r"@mistralai/|['\"]cohere-ai['\"]|['\"]replicate['\"]|['\"]groq-sdk['\"]|langchain", re.I)),
]
_DASH_GEN_HOST = [
    ("openai-host", re.compile(r"api\.openai\.com", re.I)),
    ("openrouter-host", re.compile(r"openrouter\.ai/api", re.I)),
    ("google-gen-host", re.compile(r"generativelanguage\.googleapis\.com", re.I)),
    ("anthropic-host", re.compile(r"api\.anthropic\.com", re.I)),
    ("fish-host", re.compile(r"api\.fish\.audio", re.I)),
    ("kie-host", re.compile(r"api\.kie\.ai", re.I)),
    ("perplexity-host", re.compile(r"api\.perplexity\.ai", re.I)),
]
_DASH_PIPELINE = [
    ("pipeline-script-ref", re.compile(
        r"podcast-cost-ledger|podcast-smoke-test|qc-tier1-mechanical|qc-attempt-gate|"
        r"podcast_state|podcast-episode-state|podcast-cost-ledger\.py", re.I)),
    ("process-spawn", re.compile(r"child_process|execSync|spawnSync|\bspawn\(|\bexec\(|subprocess\.", re.I)),
]
# A pipeline SCRIPT NAME only fails the dashboard screen when it is actually
# INVOKED (spawn / shell exec / module import of a script path). A bare mention
# of a pipeline module in a comment, doc line, or an error-message string that
# DOCUMENTS the read-only boundary is not an invocation and is not a violation.
# Real invocations (SDK imports, generation hosts, and any process spawn) are
# still caught unconditionally by the screens above and by process-spawn.
_DASH_INVOKE_CTX = re.compile(
    r"child_process|execSync|spawnSync|\bspawn\(|\bexec\(|subprocess\.|os\.system|\bpopen\b|"
    r"(?:require|import)\s*\(?\s*[\"'][^\"']*(?:scripts/|podcast[_-])|"
    r"\bpython3?\s+\S|\b(?:sh|bash)\s+\S", re.I)

# Deny tokens the routing config must arm and no model id may contain.
_DENY_TOKENS_REQUIRED = ["claude", "anthropic", "us.anthropic", "opus", "sonnet", "haiku"]
_DENY_TOKENS_MATCH = ["claude", "anthropic", "opus", "sonnet", "haiku"]  # substring test on ids


# --------------------------------------------------------------------------- #
# JOB 1: file scan
# --------------------------------------------------------------------------- #
def scan_anthropic(text):
    """Return list of (AF_NOANTHROPIC, class) for concrete Anthropic id shapes."""
    return [(AF_NOANTHROPIC, name) for name, rx in _ANTHROPIC_PATTERNS if rx.search(text)]


def scan_dashboard(text):
    """Stricter dashboard screen. Return list of (AF_DASHBOARD, class)."""
    hits = []
    for name, rx in _DASH_PROVIDER_IMPORT:
        if rx.search(text):
            hits.append((AF_DASHBOARD, "provider-sdk:" + name))
    for name, rx in _DASH_GEN_HOST:
        if rx.search(text):
            hits.append((AF_DASHBOARD, "generation-host:" + name))
    for name, rx in _DASH_PIPELINE:
        if not rx.search(text):
            continue
        if name == "pipeline-script-ref" and not _DASH_INVOKE_CTX.search(text):
            continue  # documented boundary reference, not an invocation
        hits.append((AF_DASHBOARD, "pipeline-call:" + name))
    return hits


def _iter_files(target):
    p = Path(target)
    if p.is_file():
        yield p
        return
    for root, dirs, files in os.walk(p):
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
        for fn in files:
            fp = Path(root) / fn
            if fp.resolve() == _SELF:
                continue  # never scan this detector (it carries the id shapes literally)
            if fp.suffix.lower() in _TEXT_EXT:
                yield fp


def _scan_one(path, dashboard=False):
    findings = []
    try:
        lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        return [(AF_IO, "unreadable:%s" % type(exc).__name__, 0)]
    for lineno, line in enumerate(lines, 1):
        for code, cls in scan_anthropic(line):
            findings.append((code, cls, lineno))
        if dashboard:
            for code, cls in scan_dashboard(line):
                findings.append((code, cls, lineno))
    return findings


def _load_allowlist(allow_path, skill_root):
    """Return (exempt_resolved_set, allowlist_findings). An entry that points at a
    runtime dir or SKILL.md is refused and produces a finding (fail-closed)."""
    exempt = set()
    findings = []
    if not allow_path:
        return exempt, findings
    ap = Path(allow_path)
    if not ap.is_file():
        return exempt, findings
    try:
        data = json.loads(ap.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        findings.append({"file": str(ap), "code": AF_ALLOWLIST,
                         "class": "unparseable-allowlist:%s" % type(exc).__name__, "line": 0})
        return exempt, findings
    entries = data.get("non_runtime_docs", []) if isinstance(data, dict) else []
    root = Path(skill_root).resolve()
    for rel in entries:
        cand = (root / rel).resolve()
        try:
            parts = cand.relative_to(root).parts
        except ValueError:
            findings.append({"file": rel, "code": AF_ALLOWLIST,
                             "class": "allowlist-entry-outside-skill-root", "line": 0})
            continue
        if cand.name == "SKILL.md" or (parts and parts[0] in _RUNTIME_DIR_NAMES):
            findings.append({"file": rel, "code": AF_ALLOWLIST,
                             "class": "allowlist-may-not-exempt-runtime-path", "line": 0})
            continue
        exempt.add(cand)
    return exempt, findings


def scan_targets(targets, dashboard_dirs, allow_path, skill_root):
    report = []
    exempt, allow_findings = _load_allowlist(allow_path, skill_root)
    report.extend(allow_findings)

    dash_resolved = {Path(d).resolve() for d in dashboard_dirs}

    def _is_dashboard(fp):
        rp = fp.resolve()
        return any(rp == d or d in rp.parents for d in dash_resolved)

    seen = set()
    all_targets = list(targets) + list(dashboard_dirs)
    for t in all_targets:
        if not Path(t).exists():
            report.append({"file": str(t), "code": AF_IO, "class": "missing-target", "line": 0})
            continue
        for fp in _iter_files(t):
            rp = fp.resolve()
            if rp in seen:
                continue
            seen.add(rp)
            is_dash = _is_dashboard(fp)
            # Allowlist exempts JOB 1 only, and never a dashboard file.
            exempt_here = (rp in exempt) and not is_dash
            for code, cls, lineno in _scan_one(fp, dashboard=is_dash):
                if exempt_here and code == AF_NOANTHROPIC:
                    continue
                report.append({"file": str(fp), "code": code, "class": cls, "line": lineno})
    return report


# --------------------------------------------------------------------------- #
# JOB 2: routing assertion
# --------------------------------------------------------------------------- #
def _load_config(path):
    p = Path(path)
    raw = p.read_text(encoding="utf-8")
    if p.suffix.lower() in {".yaml", ".yml"}:
        if yaml is None:
            raise RuntimeError("PyYAML not available to parse %s" % p.name)
        return yaml.safe_load(raw)
    if p.suffix.lower() == ".json":
        return json.loads(raw)
    # Unknown suffix: try JSON then YAML.
    try:
        return json.loads(raw)
    except ValueError:
        if yaml is None:
            raise RuntimeError("cannot parse %s (not JSON, PyYAML missing)" % p.name)
        return yaml.safe_load(raw)


def _extract_models_block(doc):
    """Locate the models block from a variety of shipped shapes."""
    if not isinstance(doc, dict):
        return None
    if isinstance(doc.get("podcast_engine"), dict) and isinstance(doc["podcast_engine"].get("models"), dict):
        return doc["podcast_engine"]["models"]
    if isinstance(doc.get("models"), dict) and "content" in doc["models"]:
        return doc["models"]
    if "content" in doc and "deny_patterns" in doc:
        return doc
    return None


def _find_routing_config(skill_root):
    """Search the config dir for a file carrying a podcast_engine.models block."""
    cfg_dir = Path(skill_root) / "config"
    if not cfg_dir.is_dir():
        return None
    for fp in sorted(cfg_dir.rglob("*")):
        if fp.suffix.lower() not in {".yaml", ".yml", ".json"} or not fp.is_file():
            continue
        try:
            doc = _load_config(fp)
        except Exception:
            continue
        if _extract_models_block(doc) is not None:
            return fp
    return None


def _model_id(entry):
    if isinstance(entry, str):
        return entry.strip()
    if isinstance(entry, dict):
        for k in ("model", "id", "name"):
            if isinstance(entry.get(k), str):
                return entry[k].strip()
    return ""


def _identity_blob(entry):
    """All identity strings on an entry (model + id + name), lowercased, so the
    deny-token substring test can never be evaded by hiding a denied id in a
    field the routing assertions do not otherwise read."""
    if isinstance(entry, str):
        return entry.lower()
    if isinstance(entry, dict):
        return " ".join(str(entry.get(k, "")) for k in ("model", "id", "name")).lower()
    return ""


def _configured_entries(models, tier):
    """Entries a config actually CONFIGURES for a tier: the client's
    configured defaults (models.client_defaults.<tier>: one object or a
    list) plus any legacy per-tier chain (models.<tier> list). The shipped
    config configures NOTHING (its defaults are null); a client-owned
    config may configure either shape."""
    out = []
    defaults = models.get("client_defaults")
    if isinstance(defaults, dict):
        raw = defaults.get(tier)
        if isinstance(raw, (dict, str)):
            out.append(raw)
        elif isinstance(raw, list):
            out.extend(raw)
    legacy = models.get(tier)
    if isinstance(legacy, list):
        out.extend(legacy)
    return out


def assert_routing(models):
    """Return list of AF_ROUTING findings. Empty list means the resolution
    policy is clean: the selection block resolves client choice first, then
    the client's configured default, and ends in the ask-the-client stop
    (never a named fallback); deny_patterns are armed and complete; every
    configured entry (either tier) carries a model id and is deny-clean;
    and the qc_judge default is distinct from the content writer default
    (SK2-15: a judge==writer routing lets the writing model rubber-stamp
    its own output)."""
    findings = []

    sel = models.get("selection")
    if not isinstance(sel, dict):
        findings.append((AF_ROUTING, "selection-policy-missing"))
    else:
        if sel.get("order") != ["client_choice", "client_configured_default"]:
            findings.append((AF_ROUTING, "selection-order-not-choice-then-default"))
        if sel.get("on_unresolved") != "ask_client":
            findings.append((AF_ROUTING, "selection-on-unresolved-not-ask-client"))

    deny = models.get("deny_patterns")
    if not isinstance(deny, list) or not deny:
        findings.append((AF_ROUTING, "deny_patterns-missing-or-empty"))
    else:
        deny_low = {str(d).strip().lower() for d in deny}
        for tok in _DENY_TOKENS_REQUIRED:
            if tok.lower() not in deny_low:
                findings.append((AF_ROUTING, "deny_patterns-missing-token:%s" % tok))

    content_entries = _configured_entries(models, "content")
    judge_entries = _configured_entries(models, "qc_judge")
    for tier, entries in (("content", content_entries), ("qc_judge", judge_entries)):
        for i, e in enumerate(entries):
            if not _model_id(e):
                findings.append((AF_ROUTING, "%s-entry-%d-has-no-model-id" % (tier, i)))
            blob = _identity_blob(e)
            for tok in _DENY_TOKENS_MATCH:
                if tok in blob:
                    findings.append((AF_ROUTING,
                                     "%s-entry-%d-matches-deny-token:%s" % (tier, i, tok)))

    writer_id = (_model_id(content_entries[0]).strip().lower()
                 if content_entries else "")
    if writer_id:
        for i, e in enumerate(judge_entries):
            if _model_id(e).strip().lower() == writer_id:
                findings.append((AF_ROUTING,
                                 "qc_judge-entry-%d-equals-writer-model:%s"
                                 % (i, _model_id(e))))

    return findings


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def run(targets, dashboard_dirs, routing_config, require_routing, allow_path,
        skill_root, as_json=False):
    file_report = scan_targets(targets, dashboard_dirs, allow_path, skill_root)

    routing_findings = []
    routing_status = "SKIPPED"
    routing_source = None
    cfg_path = routing_config or _find_routing_config(skill_root)
    if cfg_path:
        routing_source = str(cfg_path)
        try:
            doc = _load_config(cfg_path)
            models = _extract_models_block(doc)
            if models is None:
                routing_findings.append({"file": str(cfg_path), "code": AF_ROUTING,
                                         "class": "no-podcast_engine-models-block", "line": 0})
                routing_status = "FAIL"
            else:
                raw = assert_routing(models)
                routing_findings = [{"file": str(cfg_path), "code": c, "class": cl, "line": 0}
                                    for c, cl in raw]
                routing_status = "FAIL" if raw else "PASS"
        except Exception as exc:
            routing_findings.append({"file": str(cfg_path), "code": AF_ROUTING,
                                     "class": "routing-config-error:%s" % type(exc).__name__, "line": 0})
            routing_status = "FAIL"
    else:
        if require_routing:
            routing_findings.append({"file": str(Path(skill_root) / "config"), "code": AF_ROUTING,
                                     "class": "routing-config-not-found", "line": 0})
            routing_status = "FAIL"

    report = file_report + routing_findings
    passed = not report

    if as_json:
        print(json.dumps({
            "gate": "podcast-guard-no-anthropic-runtime",
            "pass": passed,
            "routing_status": routing_status,
            "routing_source": routing_source,
            "findings": report,
        }, indent=2))
    else:
        print("== Podcast Production Engine :: guard-no-anthropic-runtime ==")
        print("routing assertion: %s%s" % (
            routing_status, (" (%s)" % routing_source) if routing_source else ""))
        if passed:
            print("RESULT: PASS - no Anthropic id/provider/package/key/host in runtime; routing tier clean.")
        else:
            print("RESULT: FAIL (fail-closed) - %d finding(s) [value never printed]:" % len(report))
            for r in report:
                loc = "%s:%d" % (r["file"], r["line"]) if r["line"] else r["file"]
                print("  [%s] %s - %s" % (r["code"], loc, r["class"]))
    return EXIT_PASS if passed else EXIT_AUTOFAIL


# --------------------------------------------------------------------------- #
# Self-test: in-memory fixtures (fake key SHAPES; no real secrets)
# --------------------------------------------------------------------------- #
def self_test():
    ok = True

    def check(label, cond):
        nonlocal ok
        ok = ok and cond
        print("  [%s] %s" % ("PASS" if cond else "MISS", label))

    print("== self-test: JOB 1 file scan - CLEAN fixtures (must find NOTHING) ==")
    check("rule-stating-prose", not scan_anthropic("This skill NEVER uses Anthropic; client models only."))
    check("deny-patterns-line", not scan_anthropic("deny_patterns: [claude, anthropic, us.anthropic, opus, sonnet, haiku]"))
    check("claude-star-rule", not scan_anthropic("Forbidden: any claude-* or opus/sonnet/haiku id."))
    check("ollama-model", not scan_anthropic("content: [ollama-cloud/kimi-2.6, gemini-3.1-flash-lite]"))

    print("== self-test: JOB 1 file scan - LEAK fixtures (must be caught) ==")
    check("claude-id", bool(scan_anthropic("model: claude-opus-4-8")))
    check("anthropic-slash", bool(scan_anthropic("route to anthropic/claude-3.5-sonnet")))
    check("bedrock", bool(scan_anthropic("us.anthropic.claude-3-haiku-20240307")))
    check("npm-pkg", bool(scan_anthropic('import Anthropic from "@anthropic-ai/sdk"')))
    check("env-key", bool(scan_anthropic("export ANTHROPIC_API_KEY=xxxx")))
    check("api-host", bool(scan_anthropic("POST https://api.anthropic.com/v1/messages")))
    check("sk-ant-value", bool(scan_anthropic("key = sk-ant-" + "a" * 30)))
    check("provider-anthropic", bool(scan_anthropic('"provider": "anthropic"')))

    print("== self-test: DASHBOARD screen ==")
    check("dash-clean-sqlite", not scan_dashboard("import Database from 'better-sqlite3'"))
    check("dash-clean-stage", not scan_dashboard("const stage = 'researching'"))
    check("dash-openai-sdk", bool(scan_dashboard("import OpenAI from 'openai'")))
    check("dash-gen-host", bool(scan_dashboard("fetch('https://openrouter.ai/api/v1/chat')")))
    check("dash-pipeline", bool(scan_dashboard("execSync('python3 podcast-cost-ledger.py record')")))
    check("dash-spawn", bool(scan_dashboard("const cp = require('child_process')")))
    check("dash-comment-ref-clean", not scan_dashboard(" * writer module scripts/podcast_state.py, the sole writer"))
    check("dash-errstring-ref-clean", not scan_dashboard("throw new Err('owned by podcast_state.py, not the dashboard')"))
    check("dash-require-pipeline", bool(scan_dashboard("const s = require('../scripts/podcast_state')")))
    check("dash-shell-pipeline", bool(scan_dashboard("execSync('python3 podcast-cost-ledger.py record')")))

    print("== self-test: JOB 2 routing assertion ==")
    sel_ok = {"order": ["client_choice", "client_configured_default"],
              "on_unresolved": "ask_client"}
    deny_ok = ["claude", "anthropic", "us.anthropic", "opus", "sonnet", "haiku"]
    shipped = {"selection": sel_ok, "deny_patterns": deny_ok,
               "client_defaults": {"content": None, "qc_judge": None}}
    check("routing-shipped-shape-clean", assert_routing(shipped) == [])
    client = {"selection": sel_ok, "deny_patterns": deny_ok,
              "client_defaults": {
                  "content": [{"provider": "ollama-cloud", "model": "example-writer-1:cloud"},
                              {"provider": "openrouter", "model": "example/writer-1"}],
                  "qc_judge": [{"provider": "gemini", "model": "example-judge-1"}]}}
    check("routing-client-defaults-clean", assert_routing(client) == [])
    legacy = {"selection": sel_ok, "deny_patterns": deny_ok,
              "content": [{"provider": "ollama-cloud", "model": "example-writer-1:cloud"}],
              "qc_judge": [{"provider": "gemini", "model": "example-judge-1"}]}
    check("routing-legacy-chain-clean", assert_routing(legacy) == [])

    def has(findings, needle):
        return any(needle in cl for _, cl in findings)

    check("routing-selection-missing",
          has(assert_routing({"deny_patterns": deny_ok}), "selection-policy-missing"))
    bad_order = dict(shipped)
    bad_order["selection"] = {"order": ["client_configured_default", "client_choice"],
                              "on_unresolved": "ask_client"}
    check("routing-selection-bad-order",
          has(assert_routing(bad_order), "selection-order-not-choice-then-default"))
    named_fb = dict(shipped)
    named_fb["selection"] = {"order": ["client_choice", "client_configured_default"],
                             "on_unresolved": "use_example_model"}
    check("routing-selection-named-fallback",
          has(assert_routing(named_fb), "selection-on-unresolved-not-ask-client"))
    denied = {"selection": sel_ok, "deny_patterns": deny_ok,
              "client_defaults": {"content": [{"provider": "anthropic",
                                                "model": "claude-3.5-sonnet"}],
                                  "qc_judge": None}}
    check("routing-denied-id", has(assert_routing(denied), "matches-deny-token"))
    nodeny = dict(shipped); nodeny["deny_patterns"] = ["claude", "opus"]
    check("routing-deny-incomplete", has(assert_routing(nodeny), "deny_patterns-missing-token"))
    judge_eq = {"selection": sel_ok, "deny_patterns": deny_ok,
                "client_defaults": {
                    "content": [{"provider": "ollama-cloud", "model": "example-writer-1:cloud"}],
                    "qc_judge": [{"provider": "ollama-cloud", "model": "example-writer-1:cloud"}]}}
    check("routing-judge-equals-writer", has(assert_routing(judge_eq), "equals-writer-model"))
    judge_indep = {"selection": sel_ok, "deny_patterns": deny_ok,
                   "client_defaults": {
                       "content": [{"provider": "ollama-cloud", "model": "example-writer-1:cloud"}],
                       "qc_judge": [{"provider": "gemini", "model": "example-judge-1"}]}}
    check("routing-judge-independent-of-writer-ok", assert_routing(judge_indep) == [])

    print("== self-test: %s ==" % ("ALL ASSERTIONS PASSED" if ok else "FAILED"))
    return 0 if ok else 1


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Fail-closed Anthropic-in-runtime and routing-tier guard (Podcast Production Engine).")
    ap.add_argument("targets", nargs="*", help="files or directories to scan (default: the skill root)")
    ap.add_argument("--skill-root", default=str(_SELF.parent.parent),
                    help="skill root (default: parent of scripts/)")
    ap.add_argument("--dashboard-dir", action="append", default=[],
                    help="dashboard source dir(s) to scan with the stricter screen (repeatable)")
    ap.add_argument("--routing-config", help="explicit routing config file (YAML or JSON)")
    ap.add_argument("--require-routing", action="store_true",
                    help="fail if no routing config is found (the merge gate passes this)")
    ap.add_argument("--allow-file", help="path to config/anthropic-guard-allow.json")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-test", dest="self_test", action="store_true")
    args = ap.parse_args(argv)

    if args.self_test:
        return self_test()

    skill_root = args.skill_root
    targets = args.targets or [skill_root]

    dashboard_dirs = list(args.dashboard_dir)
    auto_dash = Path(skill_root) / "dashboard"
    if not dashboard_dirs and auto_dash.is_dir():
        dashboard_dirs = [str(auto_dash)]

    allow_path = args.allow_file
    if not allow_path:
        cand = Path(skill_root) / "config" / "anthropic-guard-allow.json"
        if cand.is_file():
            allow_path = str(cand)

    try:
        return run(targets, dashboard_dirs, args.routing_config, args.require_routing,
                   allow_path, skill_root, as_json=args.json)
    except KeyboardInterrupt:  # pragma: no cover
        return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
