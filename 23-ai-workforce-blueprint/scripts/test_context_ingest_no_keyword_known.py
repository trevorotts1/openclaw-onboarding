#!/usr/bin/env python3
"""Tests for context-ingest.py: a keyword hit is a hint, never a known fact.

Run: python3 -B scripts/test_context_ingest_no_keyword_known.py
Prints PASS for every case, exits 0 when all pass. Everything is written inside the
temporary folder this file creates.
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
INGEST = HERE / "context-ingest.py"

FAILS = []
CASES = 0


def check(name: str, cond) -> None:
    global CASES
    CASES += 1
    if cond:
        print(f"PASS {name}")
    else:
        print(f"FAIL {name}")
        FAILS.append(name)


def load_module():
    spec = importlib.util.spec_from_file_location("context_ingest", INGEST)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main() -> int:
    if not INGEST.exists():
        print(f"FAIL context-ingest.py missing at {INGEST}")
        return 1
    mod = load_module()

    root = Path(tempfile.mkdtemp(prefix="context-ingest-test-"))
    try:
        # ---- 1. AGENTS.md and TOOLS.md mention the words; no theme may become known ----
        ws = root / "workspace"
        write(ws / "AGENTS.md", "Client who pays. The client is who we serve. $ budget per client.\n")
        write(ws / "TOOLS.md", "Who runs this? The client. $ cost. Customer name goes here.\n")
        master = root / "master-files"
        zhc = master / "zero-human-company"

        check("NEVER_A_FACT_SOURCE names AGENTS.md", "AGENTS.md" in mod.NEVER_A_FACT_SOURCE)
        check("NEVER_A_FACT_SOURCE names TOOLS.md", "TOOLS.md" in mod.NEVER_A_FACT_SOURCE)

        sources = mod.load_all_sources(ws, zhc, master, None)
        themes = mod.classify_all_themes(sources)
        check("every theme is unknown",
              all(t["status"] == "unknown" for t in themes))
        check("no theme is known or partial",
              not [t for t in themes if t["status"] in ("known", "partial")])
        check("every theme asks fresh",
              all(t["suggested_action"] == "ask-fresh" for t in themes))
        check("no hint comes from AGENTS.md or TOOLS.md",
              not [t for t in themes
                   if (t.get("hint") or {}).get("source") in mod.NEVER_A_FACT_SOURCE])
        ideal = next(t for t in themes if t["theme_id"] == "ideal_customer")
        check("ideal_customer has no hint from the fleet files", ideal.get("hint") is None)
        check("ideal_customer is still ask-fresh", ideal["suggested_action"] == "ask-fresh")

        # ---- 2. a real source still produces a hint, and it is still not a fact ----
        ws2 = root / "workspace-hint"
        write(ws2 / "IDENTITY.md", "We look after every customer personally.\n")
        themes2 = mod.classify_all_themes(mod.load_all_sources(ws2, zhc, master, None))
        hinted = next(t for t in themes2 if t["theme_id"] == "ideal_customer")
        check("a real source produces a hint", (hinted.get("hint") or {}).get("source") == "IDENTITY.md")
        check("the hinted theme is still unknown", hinted["status"] == "unknown")
        check("the hinted theme still asks fresh", hinted["suggested_action"] == "ask-fresh")

        # ---- 3. structured company settings become known facts ----
        ws3 = root / "workspace-config"
        company_root = root / "company-root"
        write(company_root / "company-config.json", json.dumps({
            "companyName": "Acme",
            "industry": "Coaching",
            "commandCenterName": "Mission Control",
        }))
        write(ws3 / ".workforce-build-state.json", json.dumps({"companyRoot": str(company_root)}))

        facts = mod.known_facts(ws3, {"companyRoot": str(company_root)})
        known_path = ws3 / "company-discovery" / "interview-known.json"
        check("interview-known.json written", known_path.is_file())
        written = json.loads(known_path.read_text(encoding="utf-8")) if known_path.is_file() else {}
        check("company_name comes from company settings",
              written.get("company_name", {}).get("value") == "Acme"
              and written["company_name"].get("source") == "company-settings")
        check("industry comes from company settings",
              written.get("industry", {}).get("value") == "Coaching"
              and written["industry"].get("source") == "company-settings")
        check("command_center_name comes from company settings",
              written.get("command_center_name", {}).get("value") == "Mission Control"
              and written["command_center_name"].get("source") == "company-settings")
        check("known_facts returns what it wrote", facts.get("company_name", {}).get("value") == "Acme")

        # ---- 4. answers the gate already accepted are facts too ----
        ws4 = root / "workspace-gate"
        write(ws4 / "company-discovery" / "interview-gate-state.json", json.dumps({
            "version": 1,
            "answers": {
                "company_name": {"qid": "company_name", "value": "From The Gate",
                                 "at": "2026-11-12T00:00:00Z", "source": "web"},
                "what_you_sell": {"qid": "what_you_sell", "value": "",
                                  "at": "2026-11-12T00:00:00Z", "source": "web"},
            },
        }))
        facts4 = mod.known_facts(ws4, {})
        check("an accepted gate answer is a known fact",
              facts4.get("company_name", {}).get("value") == "From The Gate"
              and facts4["company_name"].get("source") == "interview-answer")
        check("an empty gate answer is not a known fact", "what_you_sell" not in facts4)

        # ---- 5. a key another writer put in the file survives ----
        write(ws4 / "company-discovery" / "interview-known.json",
              json.dumps({"brand_primary_color": {"value": "navy", "source": "command-center"}}))
        mod.known_facts(ws4, {})
        merged = json.loads((ws4 / "company-discovery" / "interview-known.json").read_text(encoding="utf-8"))
        check("a fact written by the other writer survives",
              merged.get("brand_primary_color", {}).get("value") == "navy")
        check("the gate answer is merged in",
              merged.get("company_name", {}).get("value") == "From The Gate")

        # ---- 6. dry run writes no facts file ----
        ws5 = root / "workspace-dry"
        write(root / "company-dry" / "company-config.json", json.dumps({"companyName": "Dry Run Co"}))
        write(ws5 / ".workforce-build-state.json",
              json.dumps({"companyRoot": str(root / "company-dry")}))
        mod.known_facts(ws5, {"companyRoot": str(root / "company-dry")}, write=False)
        check("write=False writes nothing",
              not (ws5 / "company-discovery" / "interview-known.json").exists())
    finally:
        shutil.rmtree(root, ignore_errors=True)

    print()
    print(f"{CASES - len(FAILS)} passed, {len(FAILS)} failed")
    return 0 if not FAILS else 1


if __name__ == "__main__":
    sys.exit(main())
