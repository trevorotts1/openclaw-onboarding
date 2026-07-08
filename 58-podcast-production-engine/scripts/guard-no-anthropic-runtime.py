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
#   JOB 2  ROUTING ASSERTION. Assert the shipped routing config uses the
#          sanctioned Ollama Cloud then OpenRouter then Gemini tier: content
#          tier non-empty, first entry Ollama Cloud, last entry Gemini,
#          provider order monotonic (all ollama-cloud before all openrouter
#          before all gemini), every tier present, and NO content or qc_judge
#          entry matching a deny pattern. This is the static proof that the
#          runtime router cannot substitute to a denied model (it refuses
#          deny-pattern substitutions because no denied id is ever in a tier and
#          the deny_patterns list is armed). If per-entry thinking is expressed,
#          assert high thinking rides only Kimi 2.6 / GLM 5.2, never Flash Lite.
#
#   DASHBOARD SCREEN (furnace Guardrail 2). For any directory passed with
#          --dashboard-dir (or an auto-detected <skill-root>/dashboard), the
#          screen is STRICTER: the dashboard is a dumb read-only view, so ANY
#          model-provider SDK import, ANY generation-endpoint host, or ANY
#          pipeline-script invocation / process spawn FAILS. better-sqlite3
#          (the read-only mirror driver) is explicitly allowed.
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
    ("claude-model-id", re.compile(r"claude-(?:opus|sonnet|haiku|instant|fable|[0-9])", re.I)),
    ("anthropic-slash-model", re.compile(r"anthropic/claude-(?:[0-9]|opus|sonnet|haiku|instant)", re.I)),
    ("bedrock-anthropic", re.compile(r"us\.anthropic\.claude", re.I)),
    ("anthropic-npm", re.compile(r"@anthropic-ai/")),
    ("anthropic-env-key", re.compile(r"ANTHROPIC_API_KEY")),
    ("anthropic-api-host", re.compile(r"api\.anthropic\.com", re.I)),
    ("anthropic-key-value", re.compile(r"sk-ant-[A-Za-z0-9\-]{16,}")),
    ("provider-set-anthropic", re.compile(r"""provider["']?\s*[:=]\s*["']?anthropic\b""", re.I)),
]

# --- DASHBOARD stricter screen: no model-provider SDK, no generation endpoint,
#     no pipeline invocation. better-sqlite3 is explicitly allowed. -----------
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


def _provider_tier(model_id):
    """Return (tier_rank, provider_name). Lower rank = earlier in the chain."""
    m = model_id.lower()
    if m.startswith("ollama-cloud/") or "ollama-cloud" in m or m.endswith(":cloud") or ":cloud/" in m:
        return (0, "ollama-cloud")
    if m.startswith("openrouter/") or "openrouter" in m:
        return (1, "openrouter")
    if m.startswith("gemini") or "gemini" in m or m.startswith("google/"):
        return (2, "gemini")
    return (99, "other")


def _entry_provider_tier(entry):
    """Provider tier for a routing entry. The explicit `provider` field is
    AUTHORITATIVE (the runtime slug in `model` is the raw provider-side id, e.g.
    'moonshotai/kimi-k2.6', and legitimately carries no provider prefix). When no
    provider field is present, fall back to sniffing the fully-qualified id."""
    if isinstance(entry, dict):
        prov = entry.get("provider")
        if isinstance(prov, str) and prov.strip():
            p = prov.strip().lower()
            if p in ("ollama-cloud", "ollama_cloud", "ollamacloud"):
                return (0, "ollama-cloud")
            if p == "openrouter":
                return (1, "openrouter")
            if p in ("gemini", "google", "google-gemini"):
                return (2, "gemini")
            # explicit but unrecognized provider: fall through to id sniff
    return _provider_tier(_model_id(entry))


def _identity_blob(entry):
    """All identity strings on an entry (model + id + name), lowercased, so the
    deny-token substring test can never be evaded by hiding a denied id in a
    field the provider tiering does not read."""
    if isinstance(entry, str):
        return entry.lower()
    if isinstance(entry, dict):
        return " ".join(str(entry.get(k, "")) for k in ("model", "id", "name")).lower()
    return ""


def _entry_thinking(entry):
    if isinstance(entry, dict):
        for k in ("thinking", "reasoning", "reasoning_effort"):
            v = entry.get(k)
            if isinstance(v, str):
                return v.strip().lower()
    return None


def assert_routing(models):
    """Return list of AF_ROUTING findings. Empty list means the routing tier is clean."""
    findings = []

    content = models.get("content")
    if not isinstance(content, list) or not content:
        findings.append((AF_ROUTING, "content-tier-missing-or-empty"))
        return findings  # nothing further is checkable

    ids = [_model_id(e) for e in content]
    if any(not i for i in ids):
        findings.append((AF_ROUTING, "content-entry-has-no-model-id"))

    tiers = [_entry_provider_tier(e) for e in content]
    ranks = [t[0] for t in tiers]
    provs = [t[1] for t in tiers]

    # Unknown provider anywhere in the sanctioned chain is a failure.
    for i, (mid, (rank, prov)) in enumerate(zip(ids, tiers)):
        if prov == "other" and mid:
            findings.append((AF_ROUTING, "content-entry-%d-unknown-provider" % i))

    # Deny-token substring test on every identity field of every content entry.
    for i, e in enumerate(content):
        blob = _identity_blob(e)
        for tok in _DENY_TOKENS_MATCH:
            if tok in blob:
                findings.append((AF_ROUTING, "content-entry-%d-matches-deny-token:%s" % (i, tok)))

    # First is Ollama Cloud, last is Gemini.
    if provs and provs[0] != "ollama-cloud":
        findings.append((AF_ROUTING, "content-first-entry-not-ollama-cloud"))
    if provs and provs[-1] != "gemini":
        findings.append((AF_ROUTING, "content-last-entry-not-gemini"))

    # Provider order monotonic non-decreasing across the sanctioned ranks.
    known = [r for r in ranks if r != 99]
    if known != sorted(known):
        findings.append((AF_ROUTING, "content-tier-order-not-ollama-then-openrouter-then-gemini"))

    # Every sanctioned tier must be present (full fallback chain).
    present = set(p for p in provs if p != "other")
    for need in ("ollama-cloud", "openrouter", "gemini"):
        if need not in present:
            findings.append((AF_ROUTING, "content-tier-missing-provider:%s" % need))

    # deny_patterns armed and complete.
    deny = models.get("deny_patterns")
    if not isinstance(deny, list) or not deny:
        findings.append((AF_ROUTING, "deny_patterns-missing-or-empty"))
    else:
        deny_low = {str(d).strip().lower() for d in deny}
        for tok in _DENY_TOKENS_REQUIRED:
            if tok.lower() not in deny_low:
                findings.append((AF_ROUTING, "deny_patterns-missing-token:%s" % tok))

    # qc_judge cheap-tier only, no denied ids, no primary creative (kimi).
    # SK2-15: the QC judge must be INDEPENDENT of the writer. The writer is the
    # primary content-tier model (content[0], the strongest tier that authors the
    # episode). Assert no qc_judge entry's model id equals the writer's — a
    # judge==writer routing lets the writing model rubber-stamp its own output, so
    # config-shape "independence" (cheap-tier + not-kimi) is not enough on its own.
    writer_id = (ids[0] if ids else "").strip().lower()
    judge = models.get("qc_judge")
    if judge is not None:
        if not isinstance(judge, list) or not judge:
            findings.append((AF_ROUTING, "qc_judge-present-but-empty"))
        else:
            for i, e in enumerate(judge):
                jid = _model_id(e)
                jlow = _identity_blob(e)
                _, jprov = _entry_provider_tier(e)
                if jprov not in ("gemini", "ollama-cloud"):
                    findings.append((AF_ROUTING, "qc_judge-entry-%d-not-cheap-tier" % i))
                if "kimi" in jlow:
                    findings.append((AF_ROUTING, "qc_judge-entry-%d-uses-primary-creative-model" % i))
                if writer_id and jid.strip().lower() == writer_id:
                    findings.append((AF_ROUTING,
                                     "qc_judge-entry-%d-equals-writer-model:%s" % (i, jid)))
                for tok in _DENY_TOKENS_MATCH:
                    if tok in jlow:
                        findings.append((AF_ROUTING, "qc_judge-entry-%d-matches-deny-token:%s" % (i, tok)))

    # Thinking assertion (assert-when-present): high only on ollama-cloud kimi/glm.
    thinking_seen = False
    for i, e in enumerate(content):
        th = _entry_thinking(e)
        if th is None:
            continue
        thinking_seen = True
        if th == "high":
            _, prov = _entry_provider_tier(e)
            mid = _identity_blob(e)
            if prov != "ollama-cloud" or not ("kimi" in mid or "glm" in mid):
                findings.append((AF_ROUTING, "high-thinking-on-non-kimi-glm-entry-%d" % i))
    tmap = models.get("thinking") if isinstance(models.get("thinking"), dict) else None
    if tmap:
        thinking_seen = True
        for mid, th in tmap.items():
            if str(th).strip().lower() == "high":
                _, prov = _provider_tier(str(mid))
                low = str(mid).lower()
                if prov != "ollama-cloud" or not ("kimi" in low or "glm" in low):
                    findings.append((AF_ROUTING, "high-thinking-mapped-to-non-kimi-glm:%s" % mid))

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
    good = {
        "content": ["ollama-cloud/kimi-2.6", "ollama-cloud/glm-5.2",
                    "openrouter/moonshotai/kimi-k2", "openrouter/z-ai/glm-4.6",
                    "gemini-3.1-flash-lite"],
        "qc_judge": ["gemini-3.1-flash-lite", "ollama-cloud/glm-5.2"],
        "deny_patterns": ["claude", "anthropic", "us.anthropic", "opus", "sonnet", "haiku"],
    }
    check("routing-good-clean", assert_routing(good) == [])
    check("provider-explicit-openrouter",
          _entry_provider_tier({"provider": "openrouter", "model": "moonshotai/kimi-k2.6"})[1] == "openrouter")
    check("provider-explicit-ollama",
          _entry_provider_tier({"provider": "ollama-cloud", "model": "kimi-k2.6:cloud"})[1] == "ollama-cloud")
    real = {
        "content": [
            {"provider": "ollama-cloud", "id": "ollama/kimi-k2.6:cloud", "model": "kimi-k2.6:cloud", "thinking": "high"},
            {"provider": "ollama-cloud", "id": "ollama/glm-5.2:cloud", "model": "glm-5.2:cloud", "thinking": "high"},
            {"provider": "openrouter", "id": "openrouter/moonshotai/kimi-k2.6", "model": "moonshotai/kimi-k2.6", "thinking": "default"},
            {"provider": "openrouter", "id": "openrouter/z-ai/glm-5.2", "model": "z-ai/glm-5.2", "thinking": "default"},
            {"provider": "gemini", "id": "gemini-3.1-flash-lite", "model": "gemini-3.1-flash-lite", "thinking": "default"},
        ],
        "qc_judge": [
            {"provider": "gemini", "id": "gemini-3.1-flash-lite", "model": "gemini-3.1-flash-lite"},
            {"provider": "ollama-cloud", "id": "ollama/glm-5.2:cloud", "model": "glm-5.2:cloud"},
        ],
        "deny_patterns": ["claude", "anthropic", "us.anthropic", "opus", "sonnet", "haiku"],
    }
    check("routing-real-schema-clean", assert_routing(real) == [])
    real_hi = dict(real)
    real_hi["content"] = [dict(real["content"][0])] + [dict(e) for e in real["content"][1:]]
    real_hi["content"][2] = dict(real["content"][2]); real_hi["content"][2]["thinking"] = "high"
    check("routing-real-openrouter-high-fails",
          any("high-thinking-on-non-kimi-glm" in cl for _, cl in assert_routing(real_hi)))

    def has(findings, needle):
        return any(needle in cl for _, cl in findings)

    check("routing-empty-content", has(assert_routing({"content": [], "deny_patterns": ["claude"]}),
                                       "content-tier-missing-or-empty"))
    denied = dict(good); denied["content"] = good["content"] + ["anthropic/claude-3.5-sonnet"]
    check("routing-denied-id", has(assert_routing(denied), "matches-deny-token"))
    order = dict(good); order["content"] = ["openrouter/x", "ollama-cloud/kimi-2.6", "gemini-3.1-flash-lite"]
    check("routing-bad-order", has(assert_routing(order), "not-ollama-then-openrouter-then-gemini"))
    firstlast = dict(good); firstlast["content"] = ["gemini-3.1-flash-lite", "ollama-cloud/kimi-2.6"]
    check("routing-first-not-ollama", has(assert_routing(firstlast), "first-entry-not-ollama-cloud"))
    missing_tier = dict(good); missing_tier["content"] = ["ollama-cloud/kimi-2.6", "gemini-3.1-flash-lite"]
    check("routing-missing-openrouter", has(assert_routing(missing_tier), "missing-provider:openrouter"))
    nodeny = dict(good); nodeny["deny_patterns"] = ["claude", "opus"]
    check("routing-deny-incomplete", has(assert_routing(nodeny), "deny_patterns-missing-token"))
    judgebad = dict(good); judgebad["qc_judge"] = ["ollama-cloud/kimi-2.6"]
    check("routing-judge-kimi", has(assert_routing(judgebad), "primary-creative-model"))
    # SK2-15: judge == writer (primary content model) is a fail; a distinct cheap
    # judge is clean. Use a non-kimi writer so ONLY the writer-equality check fires.
    judge_eq_writer = dict(good)
    judge_eq_writer["content"] = ["ollama-cloud/glm-5.2", "openrouter/moonshotai/kimi-k2",
                                  "gemini-3.1-flash-lite"]
    judge_eq_writer["qc_judge"] = ["ollama-cloud/glm-5.2"]  # == content[0] writer
    check("routing-judge-equals-writer",
          has(assert_routing(judge_eq_writer), "equals-writer-model"))
    judge_indep = dict(judge_eq_writer)
    judge_indep["qc_judge"] = ["gemini-3.1-flash-lite"]  # distinct from writer -> clean
    check("routing-judge-independent-of-writer-ok", assert_routing(judge_indep) == [])
    thinkbad = dict(good)
    thinkbad["content"] = [
        {"model": "ollama-cloud/kimi-2.6", "thinking": "high"},
        {"model": "ollama-cloud/glm-5.2", "thinking": "high"},
        {"model": "openrouter/moonshotai/kimi-k2"},
        {"model": "openrouter/z-ai/glm-4.6"},
        {"model": "gemini-3.1-flash-lite", "thinking": "high"},
    ]
    check("routing-high-on-flash", has(assert_routing(thinkbad), "high-thinking-on-non-kimi-glm"))
    thinkgood = dict(good)
    thinkgood["content"] = [
        {"model": "ollama-cloud/kimi-2.6", "thinking": "high"},
        {"model": "ollama-cloud/glm-5.2", "thinking": "high"},
        {"model": "openrouter/moonshotai/kimi-k2"},
        {"model": "openrouter/z-ai/glm-4.6"},
        {"model": "gemini-3.1-flash-lite"},
    ]
    check("routing-high-on-kimi-ok", assert_routing(thinkgood) == [])

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
