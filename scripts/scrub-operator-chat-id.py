#!/usr/bin/env python3
"""scrub-operator-chat-id.py -- keep the operator's personal Telegram chat id out
of agent-facing, client-installed files, and guard it forever in CI.

A fleet roll copies this repo to every client box. Any file that tells a CLIENT
agent to message the operator's personal chat would point client agents at it.
Operator-only files, tests, and guards that assert the id must NOT leak are
legitimate and stay.

Modes (stdlib only, no model calls, deterministic):
  --report  list every occurrence as file:line with its KEEP / FIX class. Exit 0.
  --apply   rewrite only FIX lines using the explicit REWRITES table. Idempotent.
            Exit 2 if any FIX line has no rewrite rule (never guesses).
  --check   exit 1 if any FIX-class occurrence exists. This is the CI guard.
  --root D  scan directory D instead of the repo root (used by the unit test).

Classification is the explicit, reviewed RULES table below, never a runtime
guess. First matching rule wins. An occurrence no rule matches is FIX: an
unreviewed new file fails the guard until a human classifies it.
Path globs use fnmatch, so `*` also crosses `/`.

FIX rewrite rule: never hardcode a chat id. Escalation goes to Rescue Rangers
through the escalation section (see scripts/rescue-escalation-section.md.tpl).
On the operator box only, the operator chat is resolved at runtime by
shared-utils/resolve-owner-chat.sh (OPERATOR_CHAT_IDS_SH) or
shared-utils/operator-chat-id.sh, never by a literal.
"""
import argparse
import fnmatch
import os
import re
import subprocess
import sys

LITERAL = "5252140759"
KEEP, FIX = "KEEP", "FIX"

# (path glob, optional line regex, class, reason). First match wins.
RULES = [
    ("scripts/scrub-operator-chat-id.py", None, KEEP,
     "this guard; it owns the target literal"),
    ("tests/*", None, KEEP,
     "tests and guards assert the id must not leak"),
    ("44-convert-and-flow-operator/tools/tests/*", None, KEEP,
     "test fixture for the liveness check"),
    ("44-convert-and-flow-operator/tools/check-ghl-token-liveness.sh", None, KEEP,
     "operator-only liveness check; the id is a deny-list, nothing is sent to it"),
    ("*/qc-no-personal-data.sh", None, KEEP,
     "banned-string guard; the id must be present to be banned"),
    (".github/workflows/qc-static.yml", None, KEEP,
     "CI guard patterns that reject the id as a --to target"),
    ("CHANGELOG.md", None, KEEP, "release history"),
    ("37-zhc-closeout/CHANGELOG.md", None, KEEP, "release history"),
    ("docs/OPERATOR-MAINTENANCE.md", None, KEEP,
     "operator-only maintenance doc, not installed into client agents"),
    ("scripts/configure-operator-telegram.sh", None, KEEP,
     "operator-only configurator; writes the operator bot account"),
    ("scripts/diagnose-telegram-config.sh", None, KEEP,
     "operator-class diagnostic; the id is a deny-list"),
    ("shared-utils/resolve-owner-chat.sh", None, KEEP,
     "the operator resolver itself; single authority for the operator id list"),
    ("scripts/ensure-pipeline-crons.sh", None, KEEP,
     "deny-list guard that rejects operator ids as cron targets; sends nothing"),
    ("scripts/test-config-injection-shapes.sh", None, KEEP,
     "test script; the id is a fixture value"),
    ("scripts/fleet-standing/n8n-backups/*", None, KEEP,
     "backup of an operator-side n8n workflow; restores only on the operator n8n"),
    ("install.sh", r"OPERATOR_CHAT_IDS\s*=\s*\{|^\s*" + LITERAL + r"\|", KEEP,
     "deny-list guard rejecting the id as a cron target; set is pinned equal to "
     "the resolver by tests/unit/cron-owner-chat-guard.test.sh"),
    ("shared-utils/nudge-incomplete-interviews.py", r"OPERATOR_CHAT_IDS\s*=\s*\{", KEEP,
     "deny-list set pinned equal to the resolver by "
     "tests/unit/cron-owner-chat-guard.test.sh"),
]
DEFAULT_REASON = "agent-facing or client-installed text; no rule marks it KEEP"

_OPS = r"\{'5252140759',\s*'6663821679',\s*'6771245262'\}"
_OPS_DQ = r'\{"5252140759",\s*"6663821679",\s*"6771245262"\}'
_ENV_SET = "set(__import__('os').environ.get('OPERATOR_CHAT_IDS_SH', '').split())"
_SRC = (
    'OC_ROOT="$(if [ -d /data/.openclaw ]; then echo /data/.openclaw; '
    'else echo "$HOME/.openclaw"; fi)"\n'
    'source "$OC_ROOT/skills/shared-utils/resolve-owner-chat.sh"; '
    'export OPERATOR_CHAT_IDS_SH\n'
)
RR = "23-ai-workforce-blueprint/templates/role-library/rescue-rangers/*.md"
TM = "15-blackceo-team-management"

# (path glob, regex, replacement, expected match count per file; None = any >= 1).
# Every match must sit on FIX lines only. A count mismatch fails --apply loudly.
REWRITES = [
    (RR, r"ping the Operator\s+\(`" + LITERAL + r"`\)\s+directly",
     "escalate through the Rescue Rangers escalation section (never a personal chat)", None),
    (RR, r"\s\(`" + LITERAL + r"`\)", "", None),
    (RR, r"Page `" + LITERAL + r"`", "Page the Operator", None),
    (RR, r"Operator `" + LITERAL + r"`\.(\s+Paging)",
     r"Operator (resolved at runtime on the operator box only).\1", None),
    (RR, r"Operator `" + LITERAL + r"`", "Operator", None),
    (TM + "/INSTALL.md", r"(?<=\| )" + LITERAL + r"(?= \| Trevor Otts)",
     "{{OPERATOR_CHAT_ID}}", 1),
    (TM + "/INSTALL.md", r"the old hardcoded `" + LITERAL + r"` default",
     "the old hardcoded personal-chat default", 1),
    (TM + "/INSTALL.md", r"(python3 -c \"\nimport json, os\n)(root = '/data)",
     lambda m: _SRC + m.group(1) + m.group(2), 1),
    (TM + "/INSTALL.md", r"(python3 - <<'EOF'\nimport json, os\n)(cfg_candidates)",
     lambda m: _SRC + m.group(1) + m.group(2), 1),
    (TM + "/INSTALL.md", r"op_ids = " + _OPS, "op_ids = " + _ENV_SET, 1),
    (TM + "/INSTALL.md", r"op_ids = " + _OPS_DQ,
     "op_ids = " + _ENV_SET + "\nassert op_ids, 'operator id list unavailable'", 1),
    (TM + "/QC.md", r", default `" + LITERAL + r"` for Trevor Otts\)",
     "; no hardcoded default, when unset the escalation is skipped)", 1),
    (TM + "/QC.md", r"\(default `" + LITERAL + r"` if not overridden\)",
     "(skipped when no operator escalation chat is configured)", 1),
    (TM + "/QC.md", r"`" + LITERAL + r"`, `6663821679`, or `6771245262`",
     "any operator chat id (`OPERATOR_CHAT_IDS_SH` in `shared-utils/resolve-owner-chat.sh`)", 1),
    (TM + "/qc-blackceo-team-management.sh", r"(\nset -u\n)",
     lambda m: m.group(1) +
     '_QC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"\n'
     'source "$_QC_DIR/../shared-utils/resolve-owner-chat.sh" || '
     '{ echo "FATAL: shared-utils/resolve-owner-chat.sh missing" >&2; exit 2; }\n'
     'export OPERATOR_CHAT_IDS_SH\n', 1),
    (TM + "/qc-blackceo-team-management.sh", r"op_ids = " + _OPS, "op_ids = " + _ENV_SET, 2),
    (TM + "/qc-blackceo-team-management.sh", r"op_ids = " + _OPS_DQ, "op_ids = " + _ENV_SET, 2),
    (TM + "/qc-blackceo-team-management.sh",
     r"OP_IDS_RE='" + LITERAL + r"\|6663821679\|6771245262'",
     'OP_IDS_RE="${OPERATOR_CHAT_IDS_SH// /|}"', 1),
    (TM + "/scripts/install-remote-rescue.sh",
     r'OPERATOR_IDS="\$\{RR_OPERATOR_IDS:-' + LITERAL + r" 6663821679 6771245262\}\"",
     '# Operator ids come from the single authority; RR_OPERATOR_IDS overrides.\n'
     'source "$REPO_ROOT/shared-utils/resolve-owner-chat.sh"\n'
     'OPERATOR_IDS="${RR_OPERATOR_IDS:-$OPERATOR_CHAT_IDS_SH}"', 1),
    ("23-ai-workforce-blueprint/resume-prompt.txt", r", default " + LITERAL + r"\)",
     "; no hardcoded default, if unset skip this operator step)", 1),
    ("cron-prompt.txt", r"\(Trevor, " + LITERAL + r"\)", "(Trevor)", 1),
    ("cron-prompt.txt", r"rejects operator IDs " + LITERAL + r"/6663821679/6771245262;",
     "rejects the operator IDs listed in resolve-owner-chat.sh;", 1),
    ("cron-prompt.txt", r"\(" + LITERAL + r" / 6663821679 / 6771245262\)",
     "(OPERATOR_CHAT_IDS_SH in resolve-owner-chat.sh)", 1),
    ("platform/vps/VPS-ENVIRONMENT-SETUP.md", r"`" + LITERAL + r"` \| Always Trevor's ID",
     "`<operator chat id>` | Operator box only; resolved at runtime, never hardcoded", 1),
    ("23-ai-workforce-blueprint/templates/role-library/presentations/scripts/tests/"
     "test_pd049_requester_nested_shape.py",
     r'"requester_chat_id": "' + LITERAL + '"', '"requester_chat_id": "<operator-chat-id>"', 1),
    ("scripts/u126-remediate.sh", r'\$\{OPERATOR_IDS:-' + LITERAL + r"\}",
     "${OPERATOR_IDS:-${OPERATOR_TELEGRAM_CHAT_ID:-}}", 1),
    ("scripts/u126-remediate.sh", r'(\n[ \t]*)(if openclaw cron rm "\$jid"[^\n]*\n)',
     lambda m: m.group(1) +
     'if [[ -z "${OPERATOR_IDS:-${OPERATOR_TELEGRAM_CHAT_ID:-}}" ]]; then '
     '_finding "F3" "SKIP" "no operator escalation chat configured '
     '(set OPERATOR_TELEGRAM_CHAT_ID)"; return 0; fi' + m.group(1) + m.group(2), 1),
    ("install.sh", r"TELEGRAM_CHAT_ID=" + LITERAL, "TELEGRAM_CHAT_ID=<operator chat id>", 1),
    ("shared-utils/nudge-incomplete-interviews.py", r"TELEGRAM_CHAT_ID=" + LITERAL,
     "TELEGRAM_CHAT_ID=<operator chat id>", 1),
]


def classify(path, line):
    for glob, line_re, cls, why in RULES:
        if fnmatch.fnmatchcase(path, glob) and (line_re is None or re.search(line_re, line)):
            return cls, why
    return FIX, DEFAULT_REASON


def list_files(root):
    if os.path.isdir(os.path.join(root, ".git")):
        out = subprocess.run(["git", "-C", root, "ls-files", "-z"], check=True,
                             capture_output=True).stdout
        return sorted(p for p in out.decode("utf-8", "surrogateescape").split("\0") if p)
    found = []
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if d != ".git"]
        found += [os.path.relpath(os.path.join(dp, f), root) for f in fns]
    return sorted(found)


def read_text(full):
    try:
        data = open(full, "rb").read()
    except OSError:
        return None
    if b"\0" in data or LITERAL.encode() not in data:
        return None
    return data.decode("utf-8", "surrogateescape")


def scan(root):
    hits = []
    for path in list_files(root):
        text = read_text(os.path.join(root, path))
        if text is None:
            continue
        for n, line in enumerate(text.split("\n"), 1):
            if LITERAL in line:
                cls, why = classify(path, line)
                hits.append((path, n, cls, why, line.strip()))
    return hits


def apply(root):
    changed, problems = {}, []
    for path in list_files(root):
        rules = [r for r in REWRITES if fnmatch.fnmatchcase(path, r[0])]
        text = read_text(os.path.join(root, path)) if rules else None
        if text is None:
            continue
        orig = text
        for _, rx, repl, want in rules:
            pat = re.compile(rx)
            matches = list(pat.finditer(text))
            if not matches:
                continue
            if want is not None and len(matches) != want:
                problems.append(f"{path}: rule /{rx[:60]}/ matched {len(matches)}, expected {want}")
                continue
            lines = text.split("\n")
            ok = True
            for m in matches:
                first = text.count("\n", 0, m.start())
                last = text.count("\n", 0, m.end())
                for i in range(first, last + 1):
                    if LITERAL in lines[i] and classify(path, lines[i])[0] != FIX:
                        problems.append(f"{path}:{i + 1}: rewrite would touch a KEEP line")
                        ok = False
            if ok:
                text = pat.sub(repl, text)
        if text != orig:
            open(os.path.join(root, path), "wb").write(text.encode("utf-8", "surrogateescape"))
            changed[path] = True
    return sorted(changed), problems


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--report", action="store_true")
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--check", action="store_true")
    ap.add_argument("--root", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    a = ap.parse_args(argv)
    root = os.path.abspath(a.root)

    if a.apply:
        changed, problems = apply(root)
        for p in changed:
            print(f"rewrote {p}")
        print(f"files rewritten: {len(changed)}")
        left = [h for h in scan(root) if h[2] == FIX]
        for p in problems:
            print(f"PROBLEM {p}", file=sys.stderr)
        for h in left:
            print(f"UNREWRITTEN FIX {h[0]}:{h[1]}", file=sys.stderr)
        return 2 if problems or left else 0

    hits = scan(root)
    fixes = [h for h in hits if h[2] == FIX]
    if a.report:
        for path, n, cls, why, _ in hits:
            print(f"{cls:4}  {path}:{n}  # {why}")
        files = {}
        for path, _, cls, _, _ in hits:
            files.setdefault(path, set()).add(cls)
        print(f"\noccurrences: keep={len(hits) - len(fixes)} fix={len(fixes)}  "
              f"files={len(files)}")
        return 0
    for path, n, _, _, _ in fixes:
        print(f"FIX-class occurrence: {path}:{n}", file=sys.stderr)
    print(f"scrub-operator-chat-id --check: {len(fixes)} FIX-class occurrence(s)")
    return 1 if fixes else 0


if __name__ == "__main__":
    sys.exit(main())
