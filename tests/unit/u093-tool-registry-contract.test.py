#!/usr/bin/env python3
"""U093: Validate shared tool registry Podbean entry and SKILL.md operating contract."""

import re, sys
from pathlib import Path

R = Path(__file__).resolve().parents[2]
TP = R / "agents" / "_shared" / "TOOLS.md"
SP = R / "58-podcast-production-engine" / "SKILL.md"

def t1(): assert TP.is_file(), f"Not found at {TP}"
def t2(): assert "## Podbean (podcast hosting and distribution)" in TP.read_text()
def t3():
    t = TP.read_text()
    for c in ["PODBEAN_CLIENT_ID","PODBEAN_CLIENT_SECRET","PODBEAN_CHANNEL_ID"]: assert c in t
    for p in [r'pk_live_',r'AKIA',r'\b[a-f0-9]{32,}\b']: assert not re.findall(p,t)
def t4():
    t = TP.read_text()
    for c in ["podcast:episode:publish","podcast:episode:upload","podcast:episode:query"]: assert c in t
def t5():
    t = TP.read_text()
    assert "Operating boundary" in t and "n8n Podbean Broker" in t and "FORBIDDEN" in t
def t6(): assert "## Operating contract" in SP.read_text()
def t7():
    s,t = SP.read_text(),TP.read_text()
    for c in ["PODBEAN_CLIENT_ID","PODBEAN_CLIENT_SECRET","PODBEAN_CHANNEL_ID"]: assert c in s and c in t
def t8():
    s,t = SP.read_text(),TP.read_text()
    for c in ["podcast:episode:publish","podcast:episode:upload","podcast:episode:query"]: assert c in s and c in t
def t9():
    t = SP.read_text()
    m = re.search(r'### Operating boundary\n\n((?:.*\n)+?)(?=\n##|\Z)',t)
    assert m,"No boundary section"; b=m.group(1)
    for _,n in [("broker","n8n Podbean Broker"),("direct","Direct Podbean API calls"),("n8n","NEVER leave the n8n instance"),("channel","Channel-scoped"),("mingle","no-co-mingling"),("toolsref","agents/_shared/TOOLS.md")]: assert n in b
def t10(): assert "agents/_shared/TOOLS.md" in SP.read_text()
def t11():
    t = TP.read_text()
    allowed = {"PODBEAN_CLIENT_ID","PODBEAN_CLIENT_SECRET","PODBEAN_CHANNEL_ID","client_id","client_secret","PODBEAN_PODCAST_ID","PODBEAN_BROKER_WEBHOOK_URL","PODBEAN_BROKER_TOKEN"}
    for p in [r'[A-Za-z0-9_-]{40,}',r'eyJ[A-Za-z0-9_-]{10,}\.']:
        for m in re.findall(p,t):
            if m not in allowed and not re.match(r'`[A-Z_]+`\s+\((?:string|secret)\)',m):
                assert False,f"Secret: {m[:50]}"
    assert re.search(r'\*\*Credential type\*\*.*`[A-Z_]+`.*`[A-Z_]+`.*`[A-Z_]+`',t)

tests = [("TOOLS.md exists",t1),("Podbean section",t2),("Credential types",t3),("Capabilities",t4),("Boundary",t5),("SKILL contract",t6),("Cred match",t7),("Cap match",t8),("Boundary rules",t9),("Ref tools",t10),("No secrets",t11)]
fails = 0
for n,fn in tests:
    try: fn(); print(f"  PASS  {n}")
    except AssertionError as e: print(f"  FAIL  {n}: {e}"); fails += 1
    except Exception as e: print(f"  FAIL  {n}: {e}"); fails += 1
if fails: print(f"\nFAILED: {fails}/{len(tests)}"); sys.exit(1)
else: print(f"\nPASSED: all {len(tests)} tests")
