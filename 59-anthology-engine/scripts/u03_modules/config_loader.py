#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u03_modules/config_loader.py  (U03 tooling)
# CONTRACT LOCATION CONFIG LOADER — loads the ONE (contract location id,
# expected name) pair the U03 verification family pins to. OFFLINE: no
# network, no credential, zero token surface.
# -----------------------------------------------------------------------------
# WHERE THIS SITS: scripts/u03_modules/ — an importable module under the U03
# package (pure namespace container per its __init__.py: imported BY NAME as
# u03_modules.config_loader, side-effect-free at import). It is NOT a manifest
# row: it ships as the shared config surface the U03 live verifier and its
# check modules import, so the (location id, expected name) pair can NEVER
# drift between the dispatcher and the checks — exactly the delta_reporter.py
# single-implementation doctrine (a contract read once, in one module).
#
# WHAT THIS OWNS
#   1. THE LOCATION ID LAW. The contract source of truth is
#      config/anthology-snapshot-contract.json -> source_template_location ->
#      template_location_id (the operator's OWN Anthology template Convert and
#      Flow location 2HIKGNgsixWx0yds7Qnx). The contract itself documents this
#      id as operator infrastructure config, NOT a secret and NOT client PII
#      (it carries no provider-key prefix). The loader returns it with its
#      masked form (reg._mask_location: last 4 chars) for every operator
#      surface; --location-id overrides for tests, and the override is NAMED
#      on every surface.
#   2. THE NAME LAW. The expected location name is the standard pipeline name
#      "Anthology Engine" — config/field-map.json pipeline.standard_pipeline_name
#      is the authoritative source (the exact source pipeline_check.py /
#      anthology_snapshot.py use), cross-checked byte-exact against the
#      snapshot contract's pipeline.name. A pair that drifts is REFUSED
#      (ConfigError) — the same defense-in-depth drift gate
#      anthology_snapshot.py self_test enforces (contract pipeline name
#      == field-map standard_pipeline_name), so this loader never hands a
#      self-inconsistent expectation to its callers.
#   3. FAIL-CLOSED READING. A missing contract, an unreadable or malformed
#      file, a missing source_template_location section, an empty location
#      id, or an empty name law is a REFUSAL (ConfigError -> exit 2), never a
#      default, never a silent fallback, never a fabricated success. The
#      contract file is REQUIRED even when --location-id overrides — a
#      contract that cannot be read means the name law is unverifiable.
#   4. NEVER-A-TOKEN SURFACE. This loader resolves ZERO credentials: it never
#      touches CONVERT_AND_FLOW_PIT (live reads resolve the pit- token
#      through reg.resolve_pit, SET / NOT SET only). Before any JSON is
#      emitted, the payload is scanned against the house credential shape
#      (pit-<value>) and a hit REFUSES the whole surface rather than print
#      it — the delta_reporter.py never-a-real-token doctrine.
#   5. BROWSER UA (CF 1010 LAW). THIS MODULE HAS NO HTTP SURFACE. The W0.6 /
#      GK-09 law (services.leadconnectorhq.com is Cloudflare-fronted and 403s
#      urllib's default "Python-urllib/x.y" User-Agent at the WAF edge — CF
#      error 1010 — before the request ever reaches Convert and Flow) is
#      honored BY CONTRACT: any LIVE read that consumes this config MUST ride
#      reg.CafClient, which applies reg.CAF_BROWSER_UA on EVERY request. This
#      module re-exports BROWSER_UA = reg.CAF_BROWSER_UA so a caller wiring
#      its own urllib surface cannot forget the law.
#
# CREDENTIALS: BY LABEL, NEVER BY VALUE. A token value is never printed,
# echoed, or reflected on any surface this module emits.
#
# FAIL-CLOSED (the whole point): an unreadable contract, a drifted
# (location, name) pair, an empty law, or a credential-shaped string in a
# payload is a REFUSAL (raise) — never a silent pass, never a fabricated
# success.
#
# RETURN CONTRACT (the machine surface this module owns):
#   load_config(*, contract_path, field_map_path, location_override="")
#       -> dict — {"contract", "schema_version", "location_id",
#       "location_id_masked", "expected_name", "sources", "drift_gate"}.
#       Raises ConfigError on any fail-closed condition.
#   run_plan(location_id, expected_name, *, sources, out=sys.stdout) -> int
#       print ONE JSON object (indent 2, sort_keys) — the house surface.
#   self_test(out=sys.stderr) -> int — OFFLINE golden + attack battery
#       (needs no network and no credential; exit 0 PASS / 4 enforced
#       violation).
#   The CLI (main) offers plan / self-test, both OFFLINE.
#
# EXIT CODES (house convention 0/1/2/4; 3 and 5 belong to the LIVE families
# this offline loader has no surface for — a live reader inherits them from
# the registry it rides):
#   0  plan / self-test PASS (offline)
#   1  unexpected error (top-level guard; never a secret leak)
#   2  STOP refusal — contract unreadable/malformed, section missing, a
#      drifted (location, name) pair, or an empty law
#   3  (not applicable here — Convert and Flow API reachability; the caller's
#      live read inherits reg.EX_HELD from the registry)
#   4  self-test FAILED (a tamper NEVER masquerades as exit 1)
#   5  (not applicable here — live read-back mismatch; the caller's live read
#      inherits reg.EX_MISMATCH)
#
# USAGE (machine surface — ONE JSON object on stdout; human notes on stderr;
# plan and self-test are OFFLINE and need NO token and NO network):
#   config_loader.py plan [--location-id ID] [--contract PATH] [--field-map PATH]
#   config_loader.py self-test
# =============================================================================
"""config_loader.py — fail-closed loader of the contract location id + expected
name pair for the U03 verification family (Skill 59)."""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
from pathlib import Path

# Sibling import bootstrap (house convention): the registry owns the
# Cloudflare browser-UA wiring, the LeadConnector client, and the credential
# resolution the LIVE callers of this config ride; its exit-code constants
# are the house contract.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import anthology_registry as reg  # noqa: E402

EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH = (
    reg.EX_OK, reg.EX_ERR, reg.EX_STOP, reg.EX_HELD, reg.EX_MISMATCH)
EX_VIOLATION = 4  # enforced violation detected (self-test FAILED)

SKILL_DIR = Path(__file__).resolve().parent.parent.parent
CONTRACT_PATH = SKILL_DIR / "config" / "anthology-snapshot-contract.json"
FIELD_MAP_PATH = SKILL_DIR / "config" / "field-map.json"

# The template location id is the CONTRACT's source_template_location (the
# operator's OWN template location, operator infrastructure config — the
# contract documents it as NOT a secret and NOT client PII; it carries no
# provider-key prefix). This module pins the known-good value; --location-id
# overrides for tests, and the override is NAMED on every surface.
DEFAULT_TEMPLATE_LOCATION = "2HIKGNgsixWx0yds7Qnx"

# The one fixed config-surface contract. Every surface this module emits
# carries it, so a machine consumer can never mistake another JSON object for
# a location config (the self-test asserts the golden plan carries the exact
# string — the surface contract is load-bearing).
CONFIG_CONTRACT = "anthology-engine-location-config"
CONFIG_SCHEMA_VERSION = 1

# The browser User-Agent law, re-exported (W0.6 / GK-09): services.
# leadconnectorhq.com is Cloudflare-fronted and 403s urllib's default UA at
# the WAF edge (CF error 1010) BEFORE the request reaches Convert and Flow.
# This loader has no HTTP surface; a LIVE caller that consumes this config
# MUST ride reg.CafClient (which applies CAF_BROWSER_UA on EVERY request) or
# wire this exact string itself — never a bare urllib UA.
BROWSER_UA = reg.CAF_BROWSER_UA

# A credential-shaped string is the pit- token prefix followed by a non-empty
# value (e.g. "pit-abc123"). The label word "PIT" alone is NOT a credential
# shape — operator surfaces name labels, never values. The self-test proves
# the pattern discriminates both ways, and every emitted surface is scanned
# against it before print.
_CREDENTIAL_SHAPE = re.compile(r"pit-\S+")


class ConfigError(Exception):
    """A fail-closed loader refusal (STOP family): an unreadable contract,
    a drifted (location, name) pair, an empty law, or a credential-shaped
    string in a payload. An expectation that cannot name its own sources
    must not run."""


def mask_location(loc: str) -> str:
    """Non-reversible marker for a location id (last 4 chars) — the house
    surface shape for every operator-facing mention of a location id."""
    return reg._mask_location(loc)


def load_config(*, contract_path: Path = CONTRACT_PATH,
                field_map_path: Path = FIELD_MAP_PATH,
                location_override: str = "") -> dict:
    """Load the ONE (contract location id, expected name) pair, fail-closed.

    Sources, in order:
      - location id : contract source_template_location.template_location_id
        (config/anthology-snapshot-contract.json), overridable with
        location_override for tests. The override is NAMED on every surface.
      - expected name: config/field-map.json pipeline.standard_pipeline_name
        (the name law source every engine verifier uses), cross-checked
        byte-exact against the contract's pipeline.name — the same
        defense-in-depth drift gate anthology_snapshot.py self_test enforces.

    REFUSES (ConfigError) when: the contract file is missing/unreadable/
    malformed, source_template_location or template_location_id is absent or
    blank, field-map.json standard_pipeline_name is absent or blank, the
    contract pipeline.name and the field-map name drift byte-for-byte, or a
    credential-shaped string rides inside any loaded value. The contract is
    REQUIRED even when location_override is given — the name law's
    cross-check source must be readable or the pair is unverifiable.

    Returns the machine surface: {"contract", "schema_version",
    "location_id", "location_id_masked", "expected_name", "sources",
    "drift_gate"}.
    """
    contract = _read_json(contract_path, "snapshot contract")
    field_map = _read_json(field_map_path, "field-map")

    src_loc = contract.get("source_template_location")
    if not isinstance(src_loc, dict):
        raise ConfigError(
            "contract %s has no source_template_location section — the "
            "location id law has no contract source" % contract_path)
    contract_location = str(src_loc.get("template_location_id") or "").strip()
    if location_override and location_override.strip():
        location_id = location_override.strip()
        location_source = ("--location-id override (tests); contract "
                           "source_template_location.template_location_id "
                           "would be %r" % contract_location)
    else:
        location_id = contract_location
        location_source = ("config/anthology-snapshot-contract.json "
                           "source_template_location.template_location_id")
    if not location_id:
        raise ConfigError(
            "contract source_template_location.template_location_id is "
            "EMPTY — the location id law has no contract source")

    pipeline = field_map.get("pipeline")
    expected_name = ""
    if isinstance(pipeline, dict):
        expected_name = str(pipeline.get("standard_pipeline_name") or "").strip()
    if not expected_name:
        raise ConfigError(
            "config/field-map.json pipeline.standard_pipeline_name is EMPTY "
            "— the name law has no contract source")
    name_source = ("config/field-map.json pipeline.standard_pipeline_name, "
                   "cross-checked byte-exact against contract pipeline.name")

    # The drift gate (defense-in-depth; the anthology_snapshot.py self_test
    # law): contract pipeline.name must equal the field-map name law.
    contract_name = ""
    cpipeline = contract.get("pipeline")
    if isinstance(cpipeline, dict):
        contract_name = str(cpipeline.get("name") or "").strip()
    if contract_name != expected_name:
        raise ConfigError(
            "contract pipeline.name %r drifted from field-map "
            "standard_pipeline_name %r — restore the pair (the engine's "
            "find-and-bind is BY NAME; a drifted law silently unbinds "
            "onboarding)" % (contract_name, expected_name))

    # Never-a-token guard: the loaded pair is the only payload ever surfaced;
    # a credential-shaped string inside it REFUSES the whole load.
    for label, value in (("expected_name", expected_name),
                         ("location_id", location_id)):
        if _CREDENTIAL_SHAPE.search(value):
            raise ConfigError(
                "%s resolved to a credential-shaped string — REFUSED without "
                "printing it" % label)

    return {
        "contract": CONFIG_CONTRACT,
        "schema_version": CONFIG_SCHEMA_VERSION,
        "location_id": location_id,
        "location_id_masked": mask_location(location_id),
        "expected_name": expected_name,
        "sources": {"location": location_source, "name": name_source},
        "drift_gate": "PASS",
    }


def _read_json(path: Path, what: str) -> dict:
    """Read + parse a JSON config, fail-closed. A missing file, an unreadable
    file, or malformed JSON is a REFUSAL (ConfigError) — never a silent
    fallback and never a fabricated expectation."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        raise ConfigError("%s not found: %s" % (what, path))
    except OSError as exc:
        raise ConfigError("%s unreadable: %s (%s)" % (what, path, exc))
    except ValueError as exc:
        raise ConfigError("%s is not valid JSON: %s (%s)" % (what, path, exc))
    if not isinstance(data, dict):
        raise ConfigError("%s is not a JSON object: %s" % (what, path))
    return data


def run_plan(location_id: str, expected_name: str, *, sources: dict,
             out=None) -> int:
    """Emit the ONE plan JSON object (offline, no network, no credential).
    The payload is scanned against the credential shape before print: a hit
    REFUSES the surface rather than echo a token."""
    payload = {
        "contract": CONFIG_CONTRACT,
        "schema_version": CONFIG_SCHEMA_VERSION,
        "location_id": location_id,
        "location_id_masked": mask_location(location_id),
        "expected_name": expected_name,
        "sources": sources,
        "drift_gate": ("contract pipeline.name == field-map "
                       "pipeline.standard_pipeline_name, byte-exact; "
                       "drift REFUSES (ConfigError, exit 2)"),
        "note": "offline plan only — no network, no credential needed; a "
                "LIVE read of this config must ride reg.CafClient "
                "(CAF_BROWSER_UA on every request — CF 1010 law)",
    }
    dumped = json.dumps(payload, indent=2, sort_keys=True)
    if _CREDENTIAL_SHAPE.search(dumped):
        raise ConfigError(
            "plan payload carries a credential-shaped string — REFUSED "
            "without printing it")
    out = out or sys.stdout
    out.write(dumped)
    out.write("\n")
    return EX_OK


# ---------------------------------------------------------------------------
# Offline self-test (no network, no credentials) — proves the loader against
# the REAL committed contract and field-map, then runs every attack fixture:
# golden loads, every tamper REFUSES, the name law stays pinned, and the
# never-a-token guard discriminates both ways.
# ---------------------------------------------------------------------------

def self_test(out=None) -> int:
    out = out or sys.stderr
    dev = io.StringIO()
    try:
        _self_test_body(dev)
    except AssertionError as exc:
        sys.stderr.write("[config-loader] SELF-TEST FAILED: %s\n" % exc)
        return EX_VIOLATION
    out.write(dev.getvalue())
    return EX_OK


def _self_test_body(dev) -> None:
    import contextlib
    import tempfile

    # ---- golden: the REAL committed sources load ----
    cfg = load_config()
    assert cfg["location_id"] == DEFAULT_TEMPLATE_LOCATION, \
        "location id drifted from the contract known-good"
    assert cfg["expected_name"] == "Anthology Engine", \
        "expected name drifted from the U02/U03 contract"
    assert cfg["location_id_masked"] == reg._mask_location(DEFAULT_TEMPLATE_LOCATION)
    assert cfg["drift_gate"] == "PASS"
    assert cfg["contract"] == CONFIG_CONTRACT

    # ---- golden plan: ONE parseable JSON object, no credential shape ----
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = run_plan(cfg["location_id"], cfg["expected_name"], sources=cfg["sources"])
    assert rc == EX_OK, "plan exit %s" % rc
    plan = json.loads(buf.getvalue())
    assert plan["contract"] == CONFIG_CONTRACT
    assert plan["expected_name"] == "Anthology Engine"
    assert not _CREDENTIAL_SHAPE.search(buf.getvalue()), \
        "plan emitted a credential-shaped string"

    # ---- attack 1: missing contract file -> REFUSED ----
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        missing = td / "nope.json"
        try:
            load_config(contract_path=missing, field_map_path=FIELD_MAP_PATH)
            raise AssertionError("missing contract was NOT refused")
        except ConfigError:
            pass

        # ---- attack 2: malformed JSON -> REFUSED ----
        bad = td / "bad.json"
        bad.write_text("{ not json", encoding="utf-8")
        try:
            load_config(contract_path=bad, field_map_path=FIELD_MAP_PATH)
            raise AssertionError("malformed contract was NOT refused")
        except ConfigError:
            pass

        # ---- attack 3: no source_template_location section -> REFUSED ----
        empty = td / "empty.json"
        empty.write_text("{}", encoding="utf-8")
        try:
            load_config(contract_path=empty, field_map_path=FIELD_MAP_PATH)
            raise AssertionError("missing location section was NOT refused")
        except ConfigError:
            pass

        # ---- attack 4: blank template_location_id -> REFUSED ----
        blank = td / "blank.json"
        blank.write_text(json.dumps({"source_template_location": {
            "template_location_id": "  "}}), encoding="utf-8")
        try:
            load_config(contract_path=blank, field_map_path=FIELD_MAP_PATH)
            raise AssertionError("blank location id was NOT refused")
        except ConfigError:
            pass

        # ---- attack 5: field-map with an empty name law -> REFUSED ----
        fm_blank = td / "fm-blank.json"
        fm_blank.write_text(json.dumps({"pipeline": {"standard_pipeline_name": ""}}),
                            encoding="utf-8")
        try:
            load_config(contract_path=CONTRACT_PATH, field_map_path=fm_blank)
            raise AssertionError("empty name law was NOT refused")
        except ConfigError:
            pass

        # ---- attack 6: drifted name pair -> REFUSED (the drift gate) ----
        drifted = td / "drifted.json"
        drifted.write_text(json.dumps({"source_template_location": {
            "template_location_id": DEFAULT_TEMPLATE_LOCATION},
            "pipeline": {"name": "Anthology Engine RENAMED"}}), encoding="utf-8")
        try:
            load_config(contract_path=drifted, field_map_path=FIELD_MAP_PATH)
            raise AssertionError("drifted name pair was NOT refused")
        except ConfigError:
            pass

        # ---- attack 7: credential-shaped value -> REFUSED unprinted ----
        cred = td / "cred.json"
        cred.write_text(json.dumps({"source_template_location": {
            "template_location_id": "pit-abc123"}}), encoding="utf-8")
        try:
            load_config(contract_path=cred, field_map_path=FIELD_MAP_PATH)
            raise AssertionError("credential-shaped location was NOT refused")
        except ConfigError:
            pass

    # ---- override seam: --location-id for tests, named on the surface ----
    ov = load_config(location_override="LOC-TEST")
    assert ov["location_id"] == "LOC-TEST", "override was not honored"
    assert ov["location_id_masked"] == reg._mask_location("LOC-TEST")
    assert "override" in ov["sources"]["location"], \
        "override source not named on the surface"
    # the contract stays REQUIRED under override: a missing contract still
    # refuses (name-law cross-check unverifiable)
    with tempfile.TemporaryDirectory() as td:
        try:
            load_config(contract_path=Path(td) / "nope.json",
                        field_map_path=FIELD_MAP_PATH,
                        location_override="LOC-TEST")
            raise AssertionError("missing contract under override was NOT refused")
        except ConfigError:
            pass

    dev.write("[config-loader] self-test PASS: golden loads, 7 attack "
              "fixtures refused, override seam named, never-a-token guard "
              "proven both ways\n")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="config_loader.py",
        description="Load the contract (location id, expected name) pair for "
                    "the Anthology U03 verification family: source of truth "
                    "config/anthology-snapshot-contract.json + "
                    "config/field-map.json, fail-closed, offline, never "
                    "prints a token (Skill 59). One JSON object on stdout.")
    ap.add_argument("--location-id", default="",
                    help="override the contract location id (tests; named "
                         "on every surface; the contract stays required)")
    ap.add_argument("--contract", default=str(CONTRACT_PATH),
                    help="path to anthology-snapshot-contract.json")
    ap.add_argument("--field-map", default=str(FIELD_MAP_PATH),
                    help="path to field-map.json (the name law source)")
    ap.add_argument("cmd", nargs="?", choices=["plan", "self-test"], default="plan")

    if argv is None:
        argv = sys.argv[1:]
    argv = list(argv)
    # Normalize --self-test / --selftest -> positional self-test subcommand
    if "--self-test" in argv:
        argv = ["self-test" if a == "--self-test" else a for a in argv]
    if "--selftest" in argv:
        argv = ["self-test" if a == "--selftest" else a for a in argv]
    args = ap.parse_args(argv)

    try:
        if args.cmd == "self-test":
            return self_test()

        cfg = load_config(contract_path=Path(args.contract).expanduser(),
                          field_map_path=Path(args.field_map).expanduser(),
                          location_override=args.location_id)
        return run_plan(cfg["location_id"], cfg["expected_name"],
                        sources=cfg["sources"])

    except ConfigError as exc:
        sys.stderr.write("[config-loader] STOP: %s\n" % exc)
        return EX_STOP
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write("[config-loader] unexpected error: %s: %s\n"
                         % (type(exc).__name__, exc))
        return EX_ERR


if __name__ == "__main__":
    sys.exit(main())
