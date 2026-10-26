#!/usr/bin/env python3
"""S75-T27 tests: the emergency owner is a per-install value, never a name.

Done when: an OPERATOR box with no configured value binds to the operator
default, a CLIENT install binds to its own configured on-call operator, and a
client install with no configured on-call operator FAILS CLOSED -- refused by
code, recorded, never defaulted to the operator name and never invented. A
client config that names the operator-box owner is refused too. stdlib only,
$0, no network.

Run: python3 scripts/core/test_emergency_owner.py
"""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = HERE
if CORE not in sys.path:
    sys.path.insert(0, CORE)

import emergency_owner as E                           # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        (" (%s)" % detail) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def refuse(code, root, env=None):
    """(True, detail) when the resolve refuses with `code`."""
    try:
        E.resolve_emergency_owner(root, env=env or {})
    except E.EmergencyOwnerError as e:
        return (e.code == code), "%s got %s: %s" % (code, e.code, e)
    return False, "%s: nothing refused" % code


def plant(root, relname, payload):
    path = os.path.join(root, relname)
    parent = os.path.dirname(path)
    if parent and not os.path.isdir(parent):
        os.makedirs(parent)
    with open(path, "w", encoding="utf-8") as f:
        if isinstance(payload, str):
            f.write(payload)
        else:
            json.dump(payload, f)
    return path


def operator(payload=None):
    return {"IS_OPERATOR_BOX": "1"} if payload is None else payload


def test_operator_box_defaults_to_the_operator():
    with tempfile.TemporaryDirectory() as td:
        b = E.resolve_emergency_owner(td, env=operator())
        check("A27-B1 operator box, nothing configured -> operator default",
              b["state"] == "bound" and b["name"] == E.OPERATOR_DEFAULT_NAME,
              b)
        check("A27-B2 the default is recorded as a default, not a config read",
              b["defaulted"] is True and b["source"] == "operator-default", b)
        check("A27-B3 the default is never claimed as invented",
              b["invented"] is False and b["install_kind"] == "operator", b)


def test_operator_box_prefers_configured_value():
    with tempfile.TemporaryDirectory() as td:
        plant(td, "onboarding-identity.json", {"ownerName": "LeAnne"})
        b = E.resolve_emergency_owner(td, env=operator())
        check("A27-B4 operator box with a configured owner uses it",
              b["name"] == "LeAnne" and b["defaulted"] is False, b)
        check("A27-B5 the binding names where the value came from",
              b["source"].startswith("onboarding-identity.json:"), b)


def test_client_binds_to_its_own_configured_operator():
    with tempfile.TemporaryDirectory() as td:
        plant(td, "onboarding-identity.json", {"ownerName": "Sheila Reynolds"})
        b = E.resolve_emergency_owner(td, env={})
        check("A27-B6 client install binds to its own configured operator",
              b["name"] == "Sheila Reynolds" and b["install_kind"] == "client", b)
        check("A27-B7 the full configured name is kept, not a first token",
              " " in b["name"], b["name"])


def test_client_without_configuration_fails_closed():
    with tempfile.TemporaryDirectory() as td:
        ok, why = refuse(E.EMERGENCY_OWNER_UNCONFIGURED, td, env={})
        check("A27-B8 client install, nothing configured -> refused", ok, why)
        try:
            E.resolve_emergency_owner(td, env={})
        except E.EmergencyOwnerError as e:
            rec = e.record
            check("A27-B9 the refusal names no person",
                  rec["name"] is None, rec["name"])
            check("A27-B10 the refusal is not a default and not an invention",
                  rec["defaulted"] is False and rec["invented"] is False, rec)
            check("A27-B11 the refusal names every source it searched",
                  set(rec["searched"]) == {
                      os.path.join(td, "onboarding-identity.json"),
                      os.path.join(td, "openclaw.json"),
                      os.path.join(td, "secrets", ".env"),
                      "env:OPENCLAW_EMERGENCY_OWNER"}, rec["searched"])


def test_client_never_binds_to_the_operator_name():
    with tempfile.TemporaryDirectory() as td:
        plant(td, "onboarding-identity.json",
              {"ownerName": E.OPERATOR_DEFAULT_NAME})
        ok, why = refuse(E.EMERGENCY_OWNER_TREVOR_ON_CLIENT, td, env={})
        check("A27-B12 client config naming the operator is refused", ok, why)
        plant(td, "onboarding-identity.json",
              {"ownerName": "  " + E.OPERATOR_DEFAULT_NAME.upper() + " "})
        ok, why = refuse(E.EMERGENCY_OWNER_TREVOR_ON_CLIENT, td, env={})
        check("A27-B13 case and padding do not sneak the operator through",
              ok, why)


def test_absent_marker_is_never_an_operator_box():
    with tempfile.TemporaryDirectory() as td:
        check("A27-B14 no marker -> client", E.install_kind(td, env={}) == "client")
        check("A27-B15 a foreign value is not the operator marker",
              E.install_kind(td, env={"IS_OPERATOR_BOX": "0"}) == "client")
        ok, why = refuse(E.EMERGENCY_OWNER_UNCONFIGURED, td, env={})
        check("A27-B16 an unmarked install cannot reach the operator default",
              ok, why)


def test_marker_sources():
    with tempfile.TemporaryDirectory() as td:
        plant(td, "secrets/.env",
              "# operator routes\nTELEGRAM_BOT_TOKEN=not-a-real-token\n"
              "OPERATOR_BOX=1\n")
        check("A27-B17 secrets env marker makes the install the operator box",
              E.install_kind(td, env={}) == "operator")
        b = E.resolve_emergency_owner(td, env={"OPERATOR_BOX": "true"})
        check("A27-B18 OPERATOR_BOX=true in the environment is the marker",
              b["install_kind"] == "operator"
              and b["name"] == E.OPERATOR_DEFAULT_NAME, b)


def test_openclaw_json_key_order_matches_the_installer():
    with tempfile.TemporaryDirectory() as td:
        plant(td, "openclaw.json", {"meta": {"ownerName": "Meta Owner"},
                                    "owner": {"name": "Owner Name"}})
        b = E.resolve_emergency_owner(td, env={})
        check("A27-B19 openclaw.json meta.ownerName is read like the installer",
              b["name"] == "Meta Owner"
              and b["source"] == "openclaw.json:meta.ownerName", b)
        plant(td, "openclaw.json",
              {"wizard": {"ownerName": "Wizard Owner"}})
        b = E.resolve_emergency_owner(td, env={})
        check("A27-B20 the wizard.ownerName fallback is read in order",
              b["name"] == "Wizard Owner"
              and b["source"] == "openclaw.json:wizard.ownerName", b)
        plant(td, "onboarding-identity.json", {"ownerName": "Identity Owner"})
        b = E.resolve_emergency_owner(td, env={})
        check("A27-B21 collected identity outranks the config file",
              b["name"] == "Identity Owner", b)


def test_pin_and_blank_values():
    with tempfile.TemporaryDirectory() as td:
        b = E.resolve_emergency_owner(
            td, env={"OPENCLAW_EMERGENCY_OWNER": " On-Call Person "})
        check("A27-B22 an explicit per-install pin binds on a client box",
              b["name"] == "On-Call Person"
              and b["source"] == "env:OPENCLAW_EMERGENCY_OWNER", b)
        ok, why = refuse(E.EMERGENCY_OWNER_UNCONFIGURED, td,
                         env={"OPENCLAW_EMERGENCY_OWNER": "   "})
        check("A27-B23 a blank pin is not a pin", ok, why)
        plant(td, "onboarding-identity.json", {"ownerName": "   \n"})
        ok, why = refuse(E.EMERGENCY_OWNER_UNCONFIGURED, td, env={})
        check("A27-B24 a blank configured value is not a person", ok, why)
        plant(td, "onboarding-identity.json", {"ownerName": "Broken\nname"})
        ok, why = refuse(E.EMERGENCY_OWNER_UNCONFIGURED, td, env={})
        check("A27-B25 a multi-line value is not a name", ok, why)


def test_resolution_is_deterministic():
    with tempfile.TemporaryDirectory() as td:
        plant(td, "onboarding-identity.json", {"ownerName": "Same Person"})
        a = E.resolve_emergency_owner(td, env={})
        b = E.resolve_emergency_owner(td, env={})
        check("A27-B26 the same install resolves to the same binding", a == b)


def test_cli_refusal_is_recorded_and_bound_run_writes_nothing():
    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, "evidence", "emergency-owner-refusal.json")
        rc = E.main(["resolve", "--root", td, "--record", out])
        check("A27-B27 CLI exits 2 when a client install refuses", rc == 2, rc)
        check("A27-B28 the refusal record is written for the owner", os.path.isfile(out))
        rec = json.load(open(out, encoding="utf-8"))
        check("A27-B29 the recorded refusal is the refusal, not a name",
              rec["state"] == "refused"
              and rec["code"] == E.EMERGENCY_OWNER_UNCONFIGURED
              and rec["name"] is None, rec)
        check("A27-B30 the record round-trips through its own schema version",
              rec["schema_version"] == E.SCHEMA_VERSION)
        plant(td, "onboarding-identity.json", {"ownerName": "Bound Person"})
        out2 = os.path.join(td, "evidence", "bound.json")
        rc = E.main(["resolve", "--root", td, "--record", out2])
        check("A27-B31 CLI exits 0 when the install binds", rc == 0, rc)
        check("A27-B32 a bound run writes no refusal record",
              not os.path.exists(out2))


def test_refusal_writer_refuses_non_refusals():
    with tempfile.TemporaryDirectory() as td:
        try:
            E.record_refusal(os.path.join(td, "x.json"), {"state": "bound"})
        except ValueError:
            check("A27-B33 the refusal writer cannot record a bound binding", True)
        else:
            check("A27-B33 the refusal writer cannot record a bound binding", False,
                  "it wrote")


def test_run():
    test_operator_box_defaults_to_the_operator()
    test_operator_box_prefers_configured_value()
    test_client_binds_to_its_own_configured_operator()
    test_client_without_configuration_fails_closed()
    test_client_never_binds_to_the_operator_name()
    test_absent_marker_is_never_an_operator_box()
    test_marker_sources()
    test_openclaw_json_key_order_matches_the_installer()
    test_pin_and_blank_values()
    test_resolution_is_deterministic()
    test_cli_refusal_is_recorded_and_bound_run_writes_nothing()
    test_refusal_writer_refuses_non_refusals()


if __name__ == "__main__":
    test_run()
    print("\n%s" % ("PASS 33/33" if not FAILS else "FAIL: %s" % ", ".join(FAILS)))
    sys.exit(1 if FAILS else 0)
