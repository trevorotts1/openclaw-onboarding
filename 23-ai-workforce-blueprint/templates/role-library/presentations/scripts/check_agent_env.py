#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_agent_env.py — FIX-14 regression guard: MC_API_TOKEN wired into the agent runtime.

The 2026-08-06 audit (Error 8 / D-8) found MC_API_TOKEN was NOT in the gateway
service-env, so every Command Center board write / deliverable registration
silently 401'd for ~15 days. FIX-14's permanent defense is this PROBE: it is the
"does the presentation agent's RUNTIME env actually carry the token" check that
runs before any presentation dispatch, and it is wired into the department verify
path so a box that regresses (token dropped from the gateway env, or dropped from
the OPENCLAW_SERVICE_MANAGED_ENV_KEYS regeneration list) FAILS LOUD instead of
stalling every deck for two weeks.

WHAT IT PROVES (all offline, deterministic, no network call):

  1. LABEL RESOLUTION, LIVE-PROCESS-FIRST. The definitive test for "does this
     process have credential X" is the RUNNING PROCESS ENV; if os.environ carries
     the label the credential EXISTS, full stop. Only when the live process env is
     empty for a label do we descend into the env stores, in order:
       1. the launchd gateway service-env file
          (~/.openclaw/service-env/ai.openclaw.gateway.env) — the ONLY env the
          gateway process sees (Mac; the launchd plist sources it via the
          env-wrapper, it does NOT inherit the GUI session)
       2. the canonical secrets store      (~/.openclaw/secrets/.env)
       3. the workspace store              (~/.openclaw/workspace/.env)
     Every store consulted is named in the report so a "NOT SET" verdict is never a
     shallow-search lie. A credential is referenced by LABEL and reported SET or
     NOT SET only; no value and no fingerprint is ever printed.

  2. MANAGED-KEY LOCKSTEP. The two labels must ALSO be members of
     OPENCLAW_SERVICE_MANAGED_ENV_KEYS — the regeneration allow-list the gateway
     env is rebuilt from. A token that exists in a store today but was never added
     to the managed list will be DROPPED on the next regeneration (the exact
     15-day regression). So the probe checks BOTH: present in the runtime env AND
     listed in the managed keys. A present-but-unmanaged label is a
     AF-AGENT-ENV-UNMANAGED warning that fails the check.

  3. REACHABILITY OF THE GATEWAY ENV FILE. On a Mac the gateway process reads its
     env from the service-env file. The probe names whether that file exists (so a
     "SET only via a bare secrets store, but the gateway will never see it" state
     is visible), but resolution is process-env-first: a box whose live process
     env already carries the token (e.g. the agent exec shell sourced the secrets)
     passes regardless of the file's presence.

EXIT CODES:
   0  both labels resolve AND both are in OPENCLAW_SERVICE_MANAGED_ENV_KEYS
      (an idempotent re-run of a clean box is the same 0)
   2  a required label is missing (AF-AGENT-ENV-MISSING), or a required label is
      present but NOT in the managed-keys list (AF-AGENT-ENV-UNMANAGED), or a bad
      invocation / validation refusal
   3  dependency unavailable (reserved; this probe is pure standard library)
   1  unexpected error

DOCTRINE: move in silence, operator-verbose and never client-facing; a value is
never printed. The probe reads stores; it never writes them. The regeneration of
the gateway env file is a SEPARATE, operator-run script (see
regenerate-gateway-env.sh) — this probe only verifies.

USAGE:
    python3 check_agent_env.py                 # human-readable verdict
    python3 check_agent_env.py --json          # machine-readable report
    python3 check_agent_env.py --self-test     # force every failure mode, exit 0
    python3 check_agent_env.py --store PATH    # add an env-store path (test seam)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

EXIT_OK = 0
EXIT_ERR = 1
EXIT_MISSING = 2
EXIT_DEP = 3

# The two labels FIX-14 wires into the gateway env (Error 8 / D-8).
REQUIRED_LABELS = (
    "MC_API_TOKEN",
    "MISSION_CONTROL_URL",
)

# The managed-keys label the regeneration allow-list lives under.
MANAGED_KEYS_LABEL = "OPENCLAW_SERVICE_MANAGED_ENV_KEYS"

# Env stores consulted AFTER the live process env (in order). The gateway
# service-env file is first because on a Mac that is the ONLY env the gateway
# process sees; the secrets + workspace stores are the box's canonical stores.
# Every store consulted is listed in the report (exhaustive-search doctrine).
DEFAULT_STORES = (
    "~/.openclaw/service-env/ai.openclaw.gateway.env",
    "~/.openclaw/secrets/.env",
    "~/.openclaw/workspace/.env",
)

ENV_LABEL_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _mask(value: Optional[str]) -> str:
    """Presence and length ONLY, never a character of the value (doctrine)."""
    if not value:
        return "NOT SET"
    return "SET(len=%d)" % len(value)


def _dotenv_parse(path: Path) -> dict:
    """Best-effort KEY=VALUE parse of one .env file. Never prints any value;
    returns a dict. Missing / unreadable files yield {} (the caller records the
    path as checked)."""
    out = {}
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except (OSError, IOError):
        return out
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.lower().startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        if not ENV_LABEL_RE.match(key):
            continue
        val = val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in ("'", '"'):
            val = val[1:-1]
        out[key] = val
    return out


def _split_managed(value: str) -> List[str]:
    """Split a comma-separated OPENCLAW_SERVICE_MANAGED_ENV_KEYS value into the
    label list. Tolerates surrounding whitespace and empty entries."""
    if not value:
        return []
    return [x.strip() for x in value.split(",") if x.strip()]


def _resolve_label(
    label: str, sources: List[Tuple[str, dict]]
) -> Tuple[Optional[str], Optional[str], bool]:
    """Live-process-first resolution of ONE label across the ordered sources.
    Returns (value, source_label, present)."""
    for source_label, mapping in sources:
        val = mapping.get(label, "")
        if val is not None and str(val).strip():
            return str(val).strip(), source_label, True
    return None, None, False


def build_sources(
    environ: dict,
    store_paths: Optional[List[str]] = None,
    extra_stores: Optional[List[str]] = None,
) -> Tuple[List[Tuple[str, dict]], List[str]]:
    """Return (sources, checked). `sources` is an ordered list of
    (source_label, mapping) with the LIVE PROCESS ENV first, then each store
    parsed. `checked` is the human list of every source consulted (proves the
    search was exhaustive).

    `store_paths` REPLACES the DEFAULT_STORES set entirely (the self-test passes
    [] so a synthetic environ is hermetic and never reads a real box's stores);
    when None, DEFAULT_STORES are used. `extra_stores` is always appended after
    (used by --store for an operator-provided extra path)."""
    sources: List[Tuple[str, dict]] = [("process-env", dict(environ))]
    checked = ["process-env"]
    base = list(DEFAULT_STORES) if store_paths is None else list(store_paths)
    for p in base + list(extra_stores or ()):
        path = Path(p).expanduser()
        exists = path.exists() and path.is_file()
        label = str(path)
        sources.append((label, _dotenv_parse(path) if exists else {}))
        checked.append("%s%s" % (label, "" if exists else " (absent)"))
    return sources, checked


def probe(
    environ: Optional[dict] = None,
    store_paths: Optional[List[str]] = None,
    extra_stores: Optional[List[str]] = None,
) -> dict:
    """Run the FIX-14 regression-guard probe and return the report dict.

    Injectable environ / stores make it self-testable (pass store_paths=[] so a
    synthetic environ never reads a real box's stores). The report carries
    SET/NOT-SET presence + source labels only; never a value."""
    environ = os.environ if environ is None else environ
    sources, checked = build_sources(environ, store_paths, extra_stores)

    resolutions = {}
    missing = []
    for label in REQUIRED_LABELS:
        val, src, present = _resolve_label(label, sources)
        resolutions[label] = {
            "label": label,
            "present": present,
            "source": src if present else None,
            "presence": _mask(val),
        }
        if not present:
            missing.append(label)

    # Managed-keys lockstep: every required label must ALSO be in the
    # OPENCLAW_SERVICE_MANAGED_ENV_KEYS regeneration allow-list, so a
    # regeneration never drops it. Resolve the managed list live-process-first
    # (it is itself a store-visible label), then split.
    managed_val, managed_src, managed_present = _resolve_label(
        MANAGED_KEYS_LABEL, sources
    )
    managed_list = _split_managed(managed_val or "")
    unmanaged = []
    for label in REQUIRED_LABELS:
        if label not in managed_list:
            unmanaged.append(label)

    # Exit precedence: missing (exit 2) > unmanaged (exit 2) > ok (0).
    if missing:
        exit_code = EXIT_MISSING
        verdict = "AF-AGENT-ENV-MISSING"
    elif unmanaged:
        exit_code = EXIT_MISSING
        verdict = "AF-AGENT-ENV-UNMANAGED"
    else:
        exit_code = EXIT_OK
        verdict = "PASS"

    return {
        "probe": "check_agent_env",
        "generated_at": now_utc(),
        "stores_checked": checked,
        "managed_keys_label": {
            "present": managed_present,
            "source": managed_src,
            "managed_list_count": len(managed_list),
        },
        "managed_keys": sorted(managed_list),
        "required_labels": list(REQUIRED_LABELS),
        "resolutions": resolutions,
        "missing": missing,
        "unmanaged": unmanaged,
        "verdict": verdict,
        "exit_code": exit_code,
    }


def render_human(report: dict) -> str:
    lines = []
    lines.append("[check_agent_env] verdict=%s exit=%d  (%s)"
                 % (report["verdict"], report["exit_code"], report["generated_at"]))
    lines.append("  stores checked (live process env first): %s"
                 % "; ".join(report["stores_checked"]))
    for label, r in report["resolutions"].items():
        src = (" via %s in %s" % (r["label"], r["source"])) if r["present"] else ""
        lines.append("  - %-20s %s%s" % (label, r["presence"], src))
    mkl = report["managed_keys_label"]
    lines.append("  %s: %s (%d label(s) in the managed list, source=%s)"
                 % (MANAGED_KEYS_LABEL,
                    "PRESENT" if mkl["present"] else "ABSENT",
                    mkl["managed_list_count"], mkl["source"]))
    for label in report["required_labels"]:
        in_list = label in report["managed_keys"]
        lines.append("  - %-20s %s" % (label, "in managed keys" if in_list
                                       else "NOT in managed keys"))
    for label in report["missing"]:
        lines.append("    ! MISSING %s (AF-AGENT-ENV-MISSING)" % label)
    for label in report["unmanaged"]:
        lines.append("    ! %s present but NOT in OPENCLAW_SERVICE_MANAGED_ENV_KEYS "
                     "(AF-AGENT-ENV-UNMANAGED) — a regeneration will DROP it" % label)
    return "\n".join(lines)


def self_test() -> int:
    """Force every failure mode. No network, no real credential; synthetic
    environ dicts and temp files only."""
    print("[check_agent_env] self-test: forcing every exit-code path")

    real_token = "MC-UNIT-TEST-" + "a1b2c3d4e5f6" * 2  # real-shaped, synthetic
    url = "https://cc.example.test"

    def _env(**extra):
        base = {"MC_API_TOKEN": real_token,
                "MISSION_CONTROL_URL": url,
                "OPENCLAW_SERVICE_MANAGED_ENV_KEYS":
                    "KIE_API_KEY,MC_API_TOKEN,MISSION_CONTROL_URL,GHL_API_KEY"}
        base.update(extra)
        return base

    # 1. PASS: both labels present and managed (process env).
    rep = probe(environ=_env(), store_paths=[], extra_stores=[])
    assert rep["verdict"] == "PASS" and rep["exit_code"] == EXIT_OK, rep
    assert rep["resolutions"]["MC_API_TOKEN"]["source"] == "process-env", rep
    assert rep["resolutions"]["MC_API_TOKEN"]["presence"].startswith("SET(len="), rep
    blob = json.dumps(rep)
    assert real_token not in blob and url not in blob, "value leaked into report"
    print("  [1] PASS path -> exit 0, process-env source, no value in report: OK")

    # 2. MISSING: token absent entirely.
    env = _env()
    del env["MC_API_TOKEN"]
    rep = probe(environ=env, store_paths=[], extra_stores=[])
    assert rep["verdict"] == "AF-AGENT-ENV-MISSING" and rep["exit_code"] == EXIT_MISSING, rep
    assert "MC_API_TOKEN" in rep["missing"], rep
    print("  [2] MC_API_TOKEN absent -> exit 2 AF-AGENT-ENV-MISSING: OK")

    # 3. MISSING via a store (not process env): the token resolves from the
    #    gateway service-env file (the Mac gateway's ONLY env source).
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        store = Path(td) / "ai.openclaw.gateway.env"
        store.write_text("MC_API_TOKEN=%s\nMISSION_CONTROL_URL=%s\n"
                         % (real_token, url))
        env = {"OPENCLAW_SERVICE_MANAGED_ENV_KEYS":
               "MC_API_TOKEN,MISSION_CONTROL_URL"}
        rep = probe(environ=env, store_paths=[str(store)], extra_stores=[])
        assert rep["verdict"] == "PASS" and rep["exit_code"] == EXIT_OK, rep
        assert rep["resolutions"]["MC_API_TOKEN"]["source"] == str(store), rep
        assert any(str(store) in s for s in rep["stores_checked"]), rep
        # process-env wins over the store: different value in process env.
        env2 = _env(MC_API_TOKEN=real_token + "-proc")
        rep2 = probe(environ=env2, store_paths=[str(store)], extra_stores=[])
        assert rep2["resolutions"]["MC_API_TOKEN"]["source"] == "process-env", rep2
        print("  [3] store resolution + process-env-first precedence + stores_checked: OK")

    # 4. UNMANAGED: token present but NOT in the managed-keys list.
    env = _env(OPENCLAW_SERVICE_MANAGED_ENV_KEYS="KIE_API_KEY,GHL_API_KEY")
    rep = probe(environ=env, store_paths=[], extra_stores=[])
    assert rep["verdict"] == "AF-AGENT-ENV-UNMANAGED" and rep["exit_code"] == EXIT_MISSING, rep
    assert set(rep["unmanaged"]) == {"MC_API_TOKEN", "MISSION_CONTROL_URL"}, rep
    print("  [4] present-but-unmanaged -> exit 2 AF-AGENT-ENV-UNMANAGED: OK")

    # 5. Managed list only needs the two; extra labels are fine.
    env = _env(OPENCLAW_SERVICE_MANAGED_ENV_KEYS="A,B,C,MC_API_TOKEN,MISSION_CONTROL_URL")
    rep = probe(environ=env, store_paths=[], extra_stores=[])
    assert rep["verdict"] == "PASS" and rep["exit_code"] == EXIT_OK, rep
    print("  [5] managed-list superset still passes: OK")

    # 6. Idempotent no-op: a clean box run twice yields the same clean verdict.
    c1 = probe(environ=_env(), store_paths=[], extra_stores=[])
    c2 = probe(environ=_env(), store_paths=[], extra_stores=[])
    assert c1["exit_code"] == c2["exit_code"] == EXIT_OK, "not idempotent"
    print("  [6] idempotent clean re-run -> exit 0 both times: OK")

    print("[check_agent_env] self-test: PASS")
    return EXIT_OK


def main(argv: Optional[List[str]] = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    argv = list(argv)
    if argv and argv[0] in ("self-test", "selftest"):
        argv[0] = "--self-test"
    ap = argparse.ArgumentParser(
        description="FIX-14 regression guard: MC_API_TOKEN wired into the agent "
                    "runtime env (live-process-first across the gateway service-env "
                    "+ secrets stores) and present in the managed-keys regeneration "
                    "list. Reports SET / NOT SET only.")
    ap.add_argument("--json", action="store_true",
                    help="emit the machine-readable report to stdout")
    ap.add_argument("--store", action="append", default=[], metavar="PATH",
                    help="add an explicit env-store path (repeatable; checked after "
                         "the live process env)")
    ap.add_argument("--self-test", action="store_true",
                    help="force every failure mode and exit")
    args = ap.parse_args(argv)

    try:
        if args.self_test:
            return self_test()
        report = probe(extra_stores=args.store)
        if args.json:
            print(json.dumps(report, indent=2, sort_keys=True))
        else:
            print(render_human(report))
        return report["exit_code"]
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write("[check_agent_env] unexpected error: %s\n" % exc)
        return EXIT_ERR


if __name__ == "__main__":
    sys.exit(main())
