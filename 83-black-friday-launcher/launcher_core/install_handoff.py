"""The `install` stage: hand the produced pages to the delivery rail and record the read-back (issue 4, D-E).

Skill 83 owns this step (decision D-E). Skill 49 stays out of the delivery rail: it neither calls Skill 6
nor names it. The rail is whatever the operator names at the install call (``--rail <module>:<entry>``,
resolved by repository path under a skill folder, never a shell command); it receives the handoff this
module builds and returns what it read back from the INSTALLED pages. Nothing is installed by Skill 83
itself, and nothing is believed that the rail did not read back.

  * precondition: the production rule passes with ``required=True`` (a client package whose approved
    pieces lack a production page never reaches the rail);
  * handoff: one row per produced page: role, page id, production file and sha256, native ids and routes;
  * read-back: for every handed-off page the rail returns an https page URL, the observation time and the
    route-guard binding journey it observed on the installed page; D1 and U2 additionally run Skill 81's
    ``check_entry_guard`` over that READ-BACK journey (never over the design-time constant);
  * the record is written to ``install/install-readback.json`` plus one
    ``install/install-readback-<role>.json`` per page in the schema Skill 49's downsell wrapper reads at
    ``--stage install`` (``signature-launch-install-readback/v1``).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping
from urllib.parse import urlsplit

import sys

_ROUTES_DIR = Path(__file__).resolve().parent.parent / "routes"
if str(_ROUTES_DIR) not in sys.path:
    sys.path.insert(0, str(_ROUTES_DIR))

import substrate  # noqa: E402

from . import checks  # noqa: E402
from .check_rules import production as production_rule  # noqa: E402

CODE = "AF-LAUNCH-INSTALL"
INSTALL_DIR = "install"
READBACK_REL = f"{INSTALL_DIR}/install-readback.json"
HANDOFF_REL = f"{INSTALL_DIR}/install-handoff.json"
READBACK_SCHEMA = "signature-launch-install-readback/v1"  # the schema downsell_wrapper reads at --stage install
JOURNEY_KEYS = ("main_purchased_verified", "u1_event", "u1_accepted")


class InstallError(Exception):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def _https(url: Any) -> bool:
    parts = urlsplit(url) if isinstance(url, str) else None
    return bool(parts and parts.scheme == "https" and parts.hostname and not parts.username
                and not parts.password and not any(c.isspace() for c in url))


def build_handoff(root: Path, rail_name: str) -> Dict[str, Any]:
    """The rows the rail installs, from the production manifest. Raises InstallError on any refusal."""
    root = Path(root)
    package_manifest = json.loads((root / "package-manifest.json").read_text(encoding="utf-8"))
    fails = checks.check_package(root / "package-manifest.json", root, announce=False)
    if fails:
        raise InstallError(f"{CODE}-CHECK", f"`check` does not pass on this package ({len(fails)} violation(s)); "
                           "nothing is handed to the rail. First: " + "; ".join(str(f) for f in fails[:3]))
    bad = production_rule.production_violations(package_manifest, root, required=True)
    if bad:
        raise InstallError(f"{CODE}-PRODUCTION", "the production rule does not pass, so nothing is handed to "
                           "the rail: " + "; ".join(bad[:3]))
    if not (root / production_rule.MANIFEST_REL).is_file():
        raise InstallError(f"{CODE}-PRODUCTION", f"the package has no {production_rule.MANIFEST_REL}: run "
                           "`produce` first. Nothing is handed to the rail.")
    production = json.loads((root / production_rule.MANIFEST_REL).read_text(encoding="utf-8"))
    rows = []
    for role, row in sorted(production["pages"].items()):
        if row.get("state") != "built":
            continue
        rows.append({"role": role, "page_id": row["page_id"], "file": f"production/{row['file']}",
                     "sha256": row["sha256"], "native_product_id": row.get("native_product_id"),
                     "native_price_id": row.get("native_price_id"), "routes": row.get("routes"),
                     **({"handoff": row["handoff"]} if row.get("handoff") else {})})
    if not rows:
        raise InstallError(f"{CODE}-EMPTY", "no produced page to install")
    return {"schema": "83-install-handoff/1", "rail": rail_name, "launch_id": production.get("launch_id"),
            "test_only": production.get("test_only"), "pages": rows}


def _check_readback(handoff: Mapping[str, Any], readback: Any) -> List[str]:
    """Problems with what the rail returned. Empty list means every handed-off page was read back."""
    problems: List[str] = []
    pages = readback.get("pages") if isinstance(readback, dict) else None
    if not isinstance(pages, dict):
        return ["the rail returned no `pages` object"]
    for row in handoff["pages"]:
        role = row["role"]
        got = pages.get(role)
        if not isinstance(got, dict):
            problems.append(f"{role}: the rail read nothing back for this page")
            continue
        if got.get("page_id") != row["page_id"]:
            problems.append(f"{role}: read back page {got.get('page_id')!r}, handed off {row['page_id']!r}")
        if not _https(got.get("installed_url")):
            problems.append(f"{role}: the read-back carries no https installed_url")
        binding = got.get("route_guard_binding")
        if not isinstance(binding, dict) or not binding.get("observed_at") or not binding.get("evidence_ref") \
                or not isinstance(binding.get("journey"), dict) or set(binding["journey"]) != set(JOURNEY_KEYS):
            problems.append(f"{role}: the read-back carries no route_guard_binding with observed_at, "
                            f"evidence_ref and a journey of exactly {list(JOURNEY_KEYS)}")
    return problems


def _guard_problems(handoff: Mapping[str, Any], readback: Mapping[str, Any], launch: Mapping[str, Any]) -> List[str]:
    """Skill 81's entry guard over the READ-BACK journey for D1 (the constant is never consulted here)."""
    row = next((r for r in handoff["pages"] if r["role"] == "downsell_1"), None)
    if row is None:
        return []
    try:
        vd = substrate.load("81-signature-downsell/validators/validate_downsell.py", "launcher_s81_validate_downsell")
    except (LookupError, ValueError, OSError, ImportError) as exc:
        return [f"downsell_1: Skill 81's entry guard cannot be loaded ({type(exc).__name__}); the install is not "
                "recorded without it"]
    journey = readback["pages"]["downsell_1"]["route_guard_binding"]["journey"]
    extras = launch.get("extras") if isinstance(launch.get("extras"), dict) else {}
    state = {"main_purchased_verified": journey.get("main_purchased_verified"), "u1_event": journey.get("u1_event"),
             "u1_enabled": extras.get("upsell_1") is True, "d1_enabled": extras.get("downsell_1") is True,
             "u2_enabled": extras.get("upsell_2") is True, "u1_accepted": journey.get("u1_accepted")}
    return [f"downsell_1: entry guard over the read-back journey: {c}" for c in vd.check_entry_guard(state)]


def install(root: Path, *, rail: Callable[[Dict[str, Any]], Dict[str, Any]], rail_name: str,
            run_dir: Path) -> Dict[str, Any]:
    """Hand the produced pages to ``rail`` and record its read-back. Returns the record it wrote."""
    root = Path(root)
    handoff = build_handoff(root, rail_name)
    out = root / INSTALL_DIR
    out.mkdir(parents=True, exist_ok=True)
    (root / HANDOFF_REL).write_text(json.dumps(handoff, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    try:
        readback = rail(json.loads(json.dumps(handoff)))
    except Exception as exc:  # noqa: BLE001  (a rail failure is a refusal here, never a silent skip)
        raise InstallError(f"{CODE}-RAIL", f"the delivery rail {rail_name!r} failed ({type(exc).__name__}: "
                           f"{str(exc)[:300]}); nothing is recorded as installed") from exc
    problems = _check_readback(handoff, readback)
    if not problems:
        launch = json.loads((Path(run_dir) / "launch.json").read_text(encoding="utf-8"))
        problems = _guard_problems(handoff, readback, launch)
    if problems:
        raise InstallError(f"{CODE}-READBACK", "the read-back does not prove the install: " + "; ".join(problems[:4]))
    record = {"schema": "83-install-readback/1", "rail": rail_name, "launch_id": handoff["launch_id"],
              "test_only": handoff["test_only"], "pages": readback["pages"]}
    (root / READBACK_REL).write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    for role, got in readback["pages"].items():
        (out / f"install-readback-{role}.json").write_text(json.dumps(
            {"schema": READBACK_SCHEMA, "role": role, "page_id": got["page_id"],
             "route_guard_binding": got["route_guard_binding"]}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return record


def load_rail(spec: str) -> Callable[[Dict[str, Any]], Dict[str, Any]]:
    """``<skill-relative module path>:<entry>`` -> the callable. A path under a skill folder only; no shell."""
    path, _, entry = str(spec).partition(":")
    if not path.endswith(".py") or not entry.isidentifier():
        raise InstallError(f"{CODE}-RAIL", f"--rail must be '<skill folder>/<module>.py:<entry>', got {spec!r}")
    try:
        module = substrate.load(path, "launcher_install_rail_" + re.sub(r"\W", "_", spec),
                                sibling_dir=str(Path(path).parent))
    except (ValueError, LookupError, OSError) as exc:
        raise InstallError(f"{CODE}-RAIL", f"the rail module {path!r} cannot be loaded ({exc})") from exc
    fn = getattr(module, entry, None)
    if not callable(fn):
        raise InstallError(f"{CODE}-RAIL", f"{path} has no callable {entry!r}")
    return fn
