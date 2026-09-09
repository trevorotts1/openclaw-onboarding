#!/usr/bin/env python3
"""tests/rescue/RR-006/test_legacy_writer_retired.py — ONB-side RR-006 gate.

The SPEC RR-006 repair obligates: "retire the legacy Python writer with an
explicit compatibility error if superseded. Do not install it as another
authority. Retained historical readers may remain read-only."

These tests pin that retirement on the SHIPPED client copy:
  1. importing/running rescue_ledger.py against any state dir raises the
     explicit compatibility error (module is retired; it must never open a
     competing SQLite ledger again),
  2. the retirement banner names the active authority (RR-04 n8n Data Tables /
     the private Fleet Ops transactional service) and the opt-out is
     drill-only (offline fixture drills, never production ticket state),
  3. the exit contract is stable (a dedicated exit code, documented),
  4. historical reader surfaces that other shipped tools rely on remain
     importable without side effects (read-only compatibility).

Sanitized fixtures only (synthetic tenant keys, temp dirs). English only.
Run: python3 tests/rescue/RR-006/test_legacy_writer_retired.py
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
LEDGER = REPO / "23-ai-workforce-blueprint" / "templates" / "role-library" / "rescue-rangers" / "scripts" / "rescue_ledger.py"

PASS = 0
FAIL = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  ok {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name} {detail}")


def load_module():
    spec = importlib.util.spec_from_file_location("rescue_ledger_retired", LEDGER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    print("== RR-006 ONB: legacy Python writer retirement ==")

    check("rescue_ledger.py exists in role-library", LEDGER.exists(), str(LEDGER))

    src = LEDGER.read_text(encoding="utf-8")

    # 1. explicit compatibility error on any production-style open
    with tempfile.TemporaryDirectory() as td:
        proc = subprocess.run(
            [sys.executable, str(LEDGER), "--state-dir", td, "open", "--ticket-id", "RRT-synthetic"],
            capture_output=True, text=True, timeout=60,
        )
        out = proc.stdout + proc.stderr
        check(
            "running the legacy writer against a state dir exits with the compatibility code",
            proc.returncode == 78,
            f"rc={proc.returncode}",
        )
        check(
            "compatibility error names retirement and the active authority",
            ("RR-006" in out or "RETIRED" in out.upper()) and ("RR-04" in out or "Data Tables" in out),
            out[:200],
        )
        check(
            "compatibility error offers the drill-only opt-out",
            "RR_LEDGER_DRILL" in out or "DRILL" in out.upper(),
            out[:200],
        )
        check("no ticket db was created by the refused run", not (Path(td) / "tickets.db").exists())

    # 2. module-level open path also refuses (import-then-use cannot bypass)
    mod = load_module()
    check("module loads for historical readers (no side effects on import)", hasattr(mod, "VALID_STATUS"))
    with tempfile.TemporaryDirectory() as td:
        refused = False
        try:
            mod.Ledger(state_dir=td)
        except SystemExit as exc:
            refused = getattr(exc, "code", None) == 78 or refused
        except RuntimeError as exc:
            refused = "RR-006" in str(exc) or "RETIRED" in str(exc).upper()
        except Exception as exc:  # noqa: BLE001 — any refusal is a refusal
            refused = "RR-006" in str(exc) or "RETIRED" in str(exc).upper()
        check("direct Ledger() construction refuses with the compatibility error", refused)
        check(
            "no tickets.db was created by the refused construction",
            not (Path(td) / "tickets.db").exists(),
        )

    # 3. drill opt-out exists but is explicit and isolated
    with tempfile.TemporaryDirectory() as td:
        env = dict(os.environ)
        env["RR_LEDGER_DRILL"] = "1"
        proc = subprocess.run(
            [sys.executable, str(LEDGER), "--state-dir", td, "init"],
            capture_output=True, text=True, timeout=60, env=env,
        )
        out = proc.stdout + proc.stderr
        check("drill opt-out (RR_LEDGER_DRILL=1) allows the offline drill init", proc.returncode == 0, f"rc={proc.returncode} {out[:160]}")
        try:
            payload = json.loads(proc.stdout.strip().splitlines()[-1])
            check("drill init reports its own isolated state dir", payload.get("ok") is True and td in str(payload.get("db", "")))
        except Exception:  # noqa: BLE001
            check("drill init reports its own isolated state dir", False, out[:160])

    # 4. shipped docs must not promise the retired writer as the live system of record
    sop_dir = REPO / "23-ai-workforce-blueprint" / "templates" / "role-library" / "rescue-rangers" / "sops"
    sop2 = (sop_dir / "SOP-RR-02-durable-ticket-ledger.md").read_text(encoding="utf-8") if (sop_dir / "SOP-RR-02-durable-ticket-ledger.md").exists() else ""
    check("SOP-RR-02 pins RR-04 Data Tables as the production writer", "RR-04" in sop2)
    check("SOP-RR-02 carries the compatibility-only label for the Python ledger", "compatibility-only" in sop2.lower() or "compatibility-only" in sop2)

    print(f"RESULT: {PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
