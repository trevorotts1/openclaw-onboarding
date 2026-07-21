#!/usr/bin/env python3
"""ghl-setup-selftest-no-live-send.test.py — the GHL setup self-test must not send.

FINDING T1-01. `05-ghl-setup/ghl-setup-full.md` told the agent "After setup, the
AI should run these tests automatically", then listed seven tests — of which
test 5 posted an SMS and test 6 posted an email through
`POST /conversations/messages`, from the client's own account, to a contact
identifier the agent was told to substitute. `05-ghl-setup/SKILL.md` completed
the instruction: do not report setup complete until all seven pass. The expected
result was explicitly "JSON with messageId confirming delivery".

So an agent following the skill literally sent two unsolicited real messages out
of a client's account, to a real contact, with no approval step, no dry run and
no sandbox — as a side effect of being asked to set up an integration.

WHAT THIS TEST ENFORCES
  1. No numbered test in the automatic self-test is a send. No POST to the
     conversations endpoint, no SMS/Email message body.
  2. The self-test checklist does not smuggle one back in.
  3. The test numbering is contiguous, so removing a send cannot leave a gap
     that a later edit "fills" with one.
  4. Every self-test count claimed in SKILL.md equals the number of tests that
     actually exist in the full guide.
  5. Send verification still exists as a documented capability, but behind
     explicit operator approval against a designated operator test contact.

Exit codes:
  0 — self-test is read-only and the counts agree
  1 — INVARIANT VIOLATED
  2 — environment error (inputs not found)

Usage:
  tests/unit/ghl-setup-selftest-no-live-send.test.py
  tests/unit/ghl-setup-selftest-no-live-send.test.py --root DIR
"""

from __future__ import annotations

import argparse
import os
import re
import sys

FULL_GUIDE_REL = "05-ghl-setup/ghl-setup-full.md"
SKILL_REL = "05-ghl-setup/SKILL.md"

TEST_HEADING_RE = re.compile(r"^TEST (\d+):[ \t]*(.*)$", re.MULTILINE)
CHECKLIST_START = "SELF-TEST CHECKLIST FOR AI"
SEPARATOR = "━"

SEND_ENDPOINT = "conversations/messages"
SEND_BODY_RE = re.compile(r'"type"\s*:\s*"(SMS|Email|FB|IG|WhatsApp|Live_Chat)"', re.IGNORECASE)
POST_RE = re.compile(r"-X\s+POST", re.IGNORECASE)

# Count claims in SKILL.md, e.g. "all 5 self-tests" / "A 5-step ... self-test".
COUNT_CLAIM_RES = [
    re.compile(r"all (\d+) self-tests", re.IGNORECASE),
    re.compile(r"A (\d+)-step[^\n]*self-test", re.IGNORECASE),
]

failures = 0


def _fail(msg: str) -> None:
    global failures
    print(f"  ✗ {msg}")
    failures += 1


def _ok(msg: str) -> None:
    print(f"  ✓ {msg}")


def split_test_blocks(text: str) -> list[tuple[int, str, str]]:
    """Return [(number, title, body)] for each `TEST n:` block in the guide."""
    matches = list(TEST_HEADING_RE.finditer(text))
    blocks = []
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end]
        # A block ends at the section separator if one comes first.
        sep = body.find(SEPARATOR)
        if sep != -1:
            body = body[:sep]
        blocks.append((int(m.group(1)), m.group(2).strip(), body))
    return blocks


def section_after(text: str, marker: str) -> str:
    """Text from `marker` to the next separator line (or end of file)."""
    idx = text.find(marker)
    if idx == -1:
        return ""
    rest = text[idx:]
    sep = rest.find(SEPARATOR)
    return rest[:sep] if sep != -1 else rest


def is_send(chunk: str) -> bool:
    """A runnable outbound send: a POST to the conversations endpoint, or a
    message body naming a delivery channel."""
    if SEND_ENDPOINT in chunk and POST_RE.search(chunk):
        return True
    return bool(SEND_BODY_RE.search(chunk))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=None, help="repo root to scan")
    args = ap.parse_args()

    root = args.root or os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    guide_path = os.path.join(root, FULL_GUIDE_REL)
    skill_path = os.path.join(root, SKILL_REL)
    for p, rel in ((guide_path, FULL_GUIDE_REL), (skill_path, SKILL_REL)):
        if not os.path.isfile(p):
            print(f"ENVIRONMENT: {rel} not found under {root}")
            return 2

    with open(guide_path, encoding="utf-8") as fh:
        guide = fh.read()
    with open(skill_path, encoding="utf-8") as fh:
        skill = fh.read()

    blocks = split_test_blocks(guide)
    if not blocks:
        print(f"ENVIRONMENT: no `TEST n:` blocks parsed from {FULL_GUIDE_REL}")
        return 2

    # ── 1. no numbered self-test is a send ──────────────────────────────────
    print("== 1. no numbered self-test sends a message ==")
    for num, title, body in blocks:
        if is_send(body):
            _fail(
                f"TEST {num} ({title}) is a LIVE SEND. It delivers a real message "
                f"from the client's account to a real contact, as part of a test "
                f"the agent is told to run automatically. Remove it from the "
                f"automatic self-test."
            )
        else:
            _ok(f"TEST {num} ({title}) is read-only")

    # ── 2. the checklist does not smuggle a send back in ────────────────────
    print("== 2. the self-test checklist does not send ==")
    checklist = section_after(guide, CHECKLIST_START)
    if not checklist:
        _fail(f"{FULL_GUIDE_REL} — '{CHECKLIST_START}' section not found")
    elif SEND_ENDPOINT in checklist or SEND_BODY_RE.search(checklist):
        _fail(f"{FULL_GUIDE_REL} — the self-test checklist references a send")
    else:
        _ok("self-test checklist is read-only")

    # ── 3. contiguous numbering ─────────────────────────────────────────────
    print("== 3. test numbering is contiguous ==")
    numbers = [n for n, _, _ in blocks]
    expected = list(range(1, len(blocks) + 1))
    if numbers == expected:
        _ok(f"tests numbered 1..{len(blocks)} with no gaps")
    else:
        _fail(f"test numbering is {numbers}; expected {expected}")

    # ── 4. every count claim in SKILL.md matches reality ────────────────────
    print("== 4. SKILL.md's self-test count matches the full guide ==")
    actual = len(blocks)
    claims: list[int] = []
    for rx in COUNT_CLAIM_RES:
        for m in rx.finditer(skill):
            claims.append(int(m.group(1)))
    if not claims:
        _fail(
            f"{SKILL_REL} makes no self-test count claim this test can read. "
            f"Expected a phrase like 'all N self-tests' or 'A N-step ... self-test'."
        )
    for claimed in claims:
        if claimed == actual:
            _ok(f"{SKILL_REL} claims {claimed} self-tests; the guide has {actual}")
        else:
            _fail(
                f"{SKILL_REL} claims {claimed} self-tests but "
                f"{FULL_GUIDE_REL} defines {actual}"
            )

    # ── 5. send verification survives, behind operator approval ─────────────
    print("== 5. send verification is documented behind operator approval ==")
    if "SEND VERIFICATION" not in guide:
        _fail(
            f"{FULL_GUIDE_REL} — no SEND VERIFICATION section. Deleting the live "
            f"sends must not delete the rule about when a send is allowed."
        )
    else:
        need = ["operator test contact", "approv"]
        missing = [n for n in need if n.lower() not in guide.lower()]
        if missing:
            _fail(
                f"{FULL_GUIDE_REL} — SEND VERIFICATION does not state "
                + " and ".join(repr(n) for n in missing)
            )
        else:
            _ok("SEND VERIFICATION requires operator approval and an operator test contact")

    print("")
    if failures:
        print(f"GHL SELF-TEST / NO LIVE SEND: FAIL ({failures} assertion(s))")
        print(
            "An automatic setup test must never deliver a message out of a "
            "client's account. See finding T1-01."
        )
        return 1
    print(
        f"GHL SELF-TEST / NO LIVE SEND: PASS "
        f"({actual} read-only tests, count claims agree)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
