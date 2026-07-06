#!/usr/bin/env python3
# =============================================================================
# SKILL 57 — SOCIAL MEDIA IN A BOX :: C10 PERSONA INPUT ADAPTER  (F4.3)
# -----------------------------------------------------------------------------
# The Skill-22 persona INPUT adapter, previously deferred to v0.5.0 as a
# fail-closed stub. Now implemented against the ONE shared entry point
# shared-utils/persona_for_job.py (the canonical 5-layer selector), so the week's
# persona is chosen task/brand-aware, deterministically, and LOGGED to the
# persona learning loop — instead of only the free-text config baseline.
#
# personaSource contract (client sovereignty is ABSOLUTE):
#   config        -> BASELINE. Adapter is a no-op; the config-carried per-platform
#                    voice is used exactly as before. Nothing changes for clients
#                    who never opted in.
#   adapter       -> run persona_for_job over the week's brand/theme context
#                    (department "social-media"); write the resolved canonical
#                    persona + Section-4 governance excerpt into the run so the
#                    generation prompts and the certificate can consume it.
#   client-choice -> the client NAMED a persona. It is FINAL, never judged, never
#                    overridden — returned verbatim (persona_for_job honors it via
#                    persona_source="client-choice"). The selector is not consulted.
#
# Writes: working/copy/persona-selection.json (best-effort; a bare box or an
# unresolved persona degrades to baseline and records why — never a hard crash of
# the run, mirroring the engine's fail-soft board pattern, EXCEPT that an
# explicitly-requested 'adapter'/'client-choice' with no resolvable persona is
# reported so it is never a silent no-op).
#
# EXIT: 0 ok (incl. baseline no-op) / 2 requested-but-unresolvable / 3 usage.
# =============================================================================
"""C10 Skill-22 persona input adapter for Social Media in a Box (Skill 57)."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_SKILL_DIR = Path(__file__).resolve().parent.parent

EXIT_OK = 0
EXIT_UNRESOLVED = 2
EXIT_USAGE = 3

# config keys that may carry the client's EXPRESS persona id (client-choice).
_CLIENT_ID_KEYS = ("personaId", "clientPersonaId", "persona_id", "personaChoice", "persona")


def _shared_utils_dir() -> "Path | None":
    cands = [
        os.environ.get("SHARED_UTILS_DIR", "").strip(),
        str(_SKILL_DIR.parent / "shared-utils"),
        str(Path.home() / ".openclaw" / "skills" / "shared-utils"),
        "/data/.openclaw/skills/shared-utils",
        str(Path.home() / "clawd" / "skills" / "shared-utils"),
    ]
    for c in cands:
        if c and (Path(c) / "persona_for_job.py").exists():
            return Path(c)
    return None


def _load_pfj():
    d = _shared_utils_dir()
    if d is None:
        return None
    try:
        sys.path.insert(0, str(d))
        import persona_for_job as pfj  # type: ignore
        return pfj
    except Exception:
        return None


def _json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _brand_context(cfg: dict) -> str:
    """Assemble the week's brand/theme context into the selector query. Bounded."""
    bits = []
    for k in ("themeOfWeek", "theme", "brandName", "brandInfo", "niche",
              "industry", "audience", "offer"):
        v = cfg.get(k)
        if isinstance(v, str) and v.strip():
            bits.append(v.strip())
    pv = cfg.get("platformVoice")
    if isinstance(pv, dict):
        bits.extend(str(x) for x in pv.values() if isinstance(x, str) and x.strip())
    if not bits:
        bits.append("weekly social media content series")
    return " | ".join(bits)[:1200]


def resolve(cfg: dict) -> "dict | None":
    """Resolve the week's persona from config. Returns a selection dict or None
    for the baseline (config) path. Raises no exceptions — a requested-but-
    unresolvable case is signaled by ``{"error": ...}`` in the returned dict."""
    source = str(cfg.get("personaSource", "config")).strip().lower()
    if source not in ("adapter", "client-choice"):
        return None  # baseline

    pfj = _load_pfj()
    if pfj is None:
        return {"error": "shared-utils/persona_for_job.py not reachable",
                "personaSource": source}

    if source == "client-choice":
        client_id = None
        for k in _CLIENT_ID_KEYS:
            if isinstance(cfg.get(k), str) and cfg[k].strip():
                client_id = cfg[k].strip()
                break
        if not client_id:
            return {"error": "personaSource:client-choice set but no persona id "
                             "(%s) found in config" % "/".join(_CLIENT_ID_KEYS),
                    "personaSource": source}
        sel = pfj.persona_for_job(
            _brand_context(cfg), "social-media",
            client_persona_id=client_id, persona_source="client-choice")
        return sel

    # source == "adapter"
    return pfj.persona_for_job(_brand_context(cfg), "social-media",
                               sop_slug=cfg.get("sopSlug"))


def run(run_dir: Path) -> int:
    cfg = _json(run_dir / "working" / "copy" / "config.json", {}) or {}
    if not isinstance(cfg, dict):
        cfg = {}
    sel = resolve(cfg)
    if sel is None:
        print("[persona-adapter] personaSource=config -> baseline (no-op).")
        return EXIT_OK
    out_path = run_dir / "working" / "copy" / "persona-selection.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(sel, indent=2), encoding="utf-8")
    if sel.get("error"):
        print("[persona-adapter] REQUESTED persona source %r could not resolve: %s"
              % (cfg.get("personaSource"), sel["error"]), file=sys.stderr)
        return EXIT_UNRESOLVED
    print("[persona-adapter] %s -> persona %s (%s), source=%s"
          % (cfg.get("personaSource"), sel.get("persona_id"),
             sel.get("persona_name"), sel.get("source")))
    return EXIT_OK


def self_test() -> int:
    import tempfile
    ok = True

    def check(label, cond):
        nonlocal ok
        ok = ok and bool(cond)
        print("  [%s] %s" % ("PASS" if cond else "FAIL", label))

    # baseline: config -> no-op (None)
    check("config -> baseline no-op", resolve({"personaSource": "config"}) is None)
    check("absent -> baseline no-op", resolve({}) is None)

    # client-choice with no id -> reported error, NOT a silent pass
    r = resolve({"personaSource": "client-choice"})
    check("client-choice missing id -> reported (not silent)",
          isinstance(r, dict) and r.get("error"))

    # client-choice with id -> honored verbatim (needs shared-utils reachable)
    if _shared_utils_dir() is not None:
        os.environ["PERSONA_FOR_JOB_FIXTURE"] = json.dumps(
            {"persona_id": "SELECTOR-SHOULD-NOT-WIN"})
        r = resolve({"personaSource": "client-choice", "personaId": "jakes-instinct",
                     "themeOfWeek": "faith-driven leadership"})
        check("client-choice honored verbatim (FINAL)",
              isinstance(r, dict) and r.get("persona_id") == "jakes-instinct"
              and r.get("source") == "client-choice")
        # adapter -> selector persona
        r = resolve({"personaSource": "adapter", "themeOfWeek": "discipline"})
        check("adapter -> selector persona",
              isinstance(r, dict) and r.get("persona_id") == "SELECTOR-SHOULD-NOT-WIN")
        os.environ.pop("PERSONA_FOR_JOB_FIXTURE", None)
    else:
        print("  [SKIP] shared-utils not reachable — live resolve checks skipped")

    print("== persona_adapter self-test: %s ==" % ("ALL PASSED" if ok else "FAILED"))
    return 0 if ok else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="C10 Skill-22 persona input adapter (Skill 57).")
    ap.add_argument("--run-dir", help="the run directory (contains working/)")
    ap.add_argument("--self-test", dest="self_test", action="store_true")
    args = ap.parse_args(argv)
    if args.self_test:
        return self_test()
    if not args.run_dir:
        ap.error("--run-dir is required (or use --self-test)")
    rd = Path(args.run_dir).resolve()
    if not rd.is_dir():
        print("FATAL: --run-dir not found: %s" % rd, file=sys.stderr)
        return EXIT_USAGE
    return run(rd)


if __name__ == "__main__":
    sys.exit(main())
