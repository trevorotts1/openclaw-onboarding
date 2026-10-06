#!/usr/bin/env python3
# tests/unit/rescue-contract-rr017.test.py
#
# RR-017 — proves the ONB side of the published Rescue dependency and ownership
# contract:
#   1. Fresh-install resolution: every doc a client-facing consumer needs
#      resolves from THIS repo (public client contract + posture manifest),
#      with no manual copy from any private repo.
#   2. The public client contract is sanitized: no credential values, no table
#      IDs, no private workflow IDs, no client box slugs.
#   3. Legacy-path labels are present and correct: Relay=retired, Python
#      ledger=compatibility-only, CC push path=active; the retired paths cannot
#      silently start a second ledger from anything ONB ships.
#   4. The nine-field escalation contract matches the enforcement code
#      (relay_brain_validation.js NINE_FIELDS == rescue_ledger.py NINE_FIELDS
#      == the published table).
#
# Hermetic: file reads only, no network, no credentials.
#
# Run: python3 tests/unit/rescue-contract-rr017.test.py
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
RR = os.path.join(REPO, "23-ai-workforce-blueprint", "templates", "role-library", "rescue-rangers")

PASS = 0
FAIL = 0


def ok(name):
    global PASS
    PASS += 1
    print(f"  ok {name}")


def fail(name, detail=""):
    global FAIL
    FAIL += 1
    print(f"  FAIL {name}" + (f"\n       {detail}" if detail else ""))


def check(cond, name, detail=""):
    if cond:
        ok(name)
    else:
        fail(name, detail)


contract_path = os.path.join(RR, "contract", "PUBLIC-CLIENT-CONTRACT.md")
manifest_path = os.path.join(RR, "connection-manifest.json")

print("== RR-017: public client contract ==")
check(os.path.isfile(contract_path), "PUBLIC-CLIENT-CONTRACT.md exists in role-library")
contract = open(contract_path, encoding="utf-8").read()

NINE_FIELDS = ["person", "clientName", "agentName", "boxName", "boxType",
               "openclawVersion", "problem", "alreadyTried", "returnTo"]
check(all(f in contract for f in NINE_FIELDS), "contract publishes the nine-field escalation table")

# sanitization: no table IDs, no workflow IDs, no credential-value shapes
value_shapes = re.findall(r"\b[0-9a-f]{20,}\b", contract)
check(not value_shapes, "no hex credential/table-ID shapes", str(value_shapes[:3]))
wf_ids = re.findall(r"\b[A-Za-z0-9]{14}\b", contract)
wf_ids = [w for w in wf_ids if w not in ("RESCUE_RANGERS",)]
check(not wf_ids, "no 14-char n8n workflow IDs", str(wf_ids[:3]))
# the retired path may appear ONLY within the retired-paths section (the line
# itself or its immediate continuation, all carrying the retired marking)
lines = contract.splitlines()
retired_lines = [i for i, l in enumerate(lines) if "webhook/rescue-rangers" in l]
ok_ctx = []
for i in retired_lines:
    window = " ".join(lines[max(0, i - 3):i + 3]).lower()
    ok_ctx.append(("retired" in window or "must not" in window) and "rr-v2-intake" in window)
check(len(retired_lines) == 1 and all(ok_ctx),
      "contract names the retired relay path only as retired text", str(retired_lines))
check("[REDACTED" not in contract and "sk-" not in contract, "no redacted-placeholder or key prefixes")

print("== RR-017: posture manifest ==")
check(os.path.isfile(manifest_path), "connection-manifest.json exists")
man = json.load(open(manifest_path))
check(man.get("version") == "2.0.0", "manifest bumped to 2.0.0 with RR-017 authority block")
auth = man.get("contract_authority", {})
check("Data Tables" in auth.get("persistence_authority", ""), "manifest records RR-04 Data Tables as persistence authority")
check("compatibility-only" in auth.get("persistence_authority", ""), "manifest demotes Python ledger to compatibility-only")
classes = sorted(p["classification"] for p in man.get("legacy_paths", []))
check(classes == ["active", "compatibility-only", "retired"], "legacy paths carry exactly the three labels")
# posture-only: no value-shaped strings anywhere in the manifest
raw_man = open(manifest_path, encoding="utf-8").read()
check(not re.search(r"(?<![0-9a-f])[0-9a-f]{40,}(?![0-9a-f])", raw_man), "manifest carries no credential-shaped value")

print("== RR-017: retired paths cannot start a second ledger from ONB ==")
# the installer must refuse production use in its classification header
inst = open(os.path.join(RR, "scripts", "install-rescue-ledger.sh"), encoding="utf-8").read()
check("COMPATIBILITY-ONLY" in inst, "installer header classifies itself compatibility-only")
check(re.search(r"MUST NOT be run against\s*(production|production\s*\n#?\s*ticket state)", inst.replace("# ", "")) is not None,
      "installer prohibits production use")
# the SOPs must not call the Python ledger the system of record anymore
sop2 = open(os.path.join(RR, "sops", "SOP-RR-02-durable-ticket-ledger.md"), encoding="utf-8").read()
check("RR-04 n8n Data Tables ledger" in sop2, "SOP-RR-02 names RR-04 Data Tables the system of record")
check(sop2.count("COMPATIBILITY-ONLY") + sop2.count("compatibility-only") >= 1, "SOP-RR-02 carries the compatibility-only label")
check("SOLE production writer" in sop2, "SOP-RR-02 pins RR-04 as the sole production writer")
# no shipped doc may still promise the Python ledger / board caller as the live path
stale_live_promises = []
for rel in ["TOOLS.md",
            "director-of-rescue-rangers.md",
            "ticket-clerk--rescue-rangers.md",
            "how-to-use-this-department.md",
            "sops/SOP-RR-01-triage-and-dispatch.md",
            "sops/SOP-RR-02-durable-ticket-ledger.md",
            "sops/SOP-RR-03-cc-board-and-aging-sweep.md"]:
    try:
        text = open(os.path.join(RR, rel), encoding="utf-8").read()
    except OSError:
        continue
    for i, line in enumerate(text.splitlines()):
        low = line.lower()
        if ("through `rescue_ledger.py`" in low and "system of record" in low) \
           or ("write ticket state through" in low and "rescue_ledger.py" in low) \
           or ("written to the sqlite ledger (system" in low):
            stale_live_promises.append(f"{rel}:{i + 1}")
check(not stale_live_promises, "no shipped doc promises the Python ledger as the live writer", str(stale_live_promises[:5]))
# drill sections that still give live-sounding Python-ledger commands must carry a drill-only label
unlabeled_drill_sections = []
for rel in ["sops/SOP-RR-02-durable-ticket-ledger.md",
            "sops/SOP-RR-03-cc-board-and-aging-sweep.md"]:
    text = open(os.path.join(RR, rel), encoding="utf-8").read()
    for m in re.finditer(r"^### (SOP 9\.\d+ — .+)$", text, re.M):
        body = text[m.end():m.end() + 1200]
        if "rescue_ledger.py" in body or "rescue_cc_board" in body:
            if "DRILL" not in m.group(1).upper() and "drill" not in body[:600].lower() \
               and "compatibility-only" not in body[:600].lower():
                unlabeled_drill_sections.append(f"{rel} :: {m.group(1)}")
check(not unlabeled_drill_sections, "drill sections using rescue_ledger.py carry a drill-only label", str(unlabeled_drill_sections[:5]))
# no ONB-shipped script wires the retired relay URL as a live default
retired_carriers = []
for root, _dirs, files in os.walk(REPO):
    if "node_modules" in root or os.sep + ".git" in root:
        continue
    for f in files:
        if f.endswith((".sh", ".py")):
            p = os.path.join(root, f)
            s = open(p, encoding="utf-8", errors="ignore").read()
            if "webhook/rescue-rangers" in s and "rr-v2-intake" not in s:
                retired_carriers.append(os.path.relpath(p, REPO))
check(not retired_carriers, "no shipped script defaults to the retired relay path", str(retired_carriers[:5]))

print("== RR-017: nine-field contract matches enforcement code ==")
relay_js = open(os.path.join(RR, "scripts", "relay_brain_validation.js"), encoding="utf-8").read()
ledger_py = open(os.path.join(RR, "scripts", "rescue_ledger.py"), encoding="utf-8").read()
m_js = re.search(r"NINE_FIELDS = \[(.*?)\]", relay_js, re.S)
m_py = re.search(r"NINE_FIELDS = \((.*?)\)", ledger_py, re.S)
nine_js = re.findall(r"'(\w+)'", m_js.group(1)) if m_js else []
nine_py = re.findall(r'"(\w+)"', m_py.group(1)) if m_py else []
check(nine_js == NINE_FIELDS, "relay_brain_validation.js NINE_FIELDS matches the published contract", str(nine_js))
check(nine_py == NINE_FIELDS, "rescue_ledger.py NINE_FIELDS matches the published contract", str(nine_py))
check(nine_js == nine_py, "the two enforcement copies agree with each other")

print()
print(f"RESULT: {PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)