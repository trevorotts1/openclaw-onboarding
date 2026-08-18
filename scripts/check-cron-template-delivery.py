#!/usr/bin/env python3
"""check-cron-template-delivery.py — cron delivery-path lint gate.

WHAT THIS EXISTS TO PREVENT
---------------------------
A cron's output has to reach the client by EXACTLY ONE path. There are two
legitimate shapes:

  (A) SILENT cron  — registered with no --channel/--to/--announce. Nothing is
      auto-delivered, so the prompt's own deliberate `openclaw message send`
      IS the delivery. This is what install.sh registers.

  (B) DELIVERING cron — the scheduler delivers the run's output. The prompt
      must then NEVER send anything itself.

Shipping BOTH at once is the bug. The scheduler auto-delivers whatever the
agent's final turn text happens to be — routinely a partial or internal status
line, not the composed deliverable — while the real content goes out (or fails
to) separately. The run still reports `succeeded`.

Measured on a live box: two daily client deliverables were generated in full and
then silently lost, with both runs reporting success. The prompts told the model
to address the message itself ("Post the full briefing to this topic (#178)",
"Send a short daily digest to Topic #65"). The model therefore tried to build
the address, and intermittently invented invalid targets — `to:'65'`,
`telegram_topic:65`, and a malformed shape that resolved to `@telegram`
(Telegram's own broadcast channel), which returns 403. Compounding it, one
template shipped `delivery_mode:'none'` on a CLIENT DELIVERABLE, removing the
announce backstop entirely — so a failed self-send meant total loss.

A prompt must never name a raw topic/chat id inline. Targets are resolved at
run time (see shared-utils/resolve-owner-chat.sh, which also rejects operator
IDs); a literal id in prompt text is both unroutable and a co-mingling hazard.

CHECKS
------
  1 SELF_ADDRESSING   — a shipped cron prompt template names a literal
                        topic/chat target inline.
  2 DELIVERY_NONE     — a client-facing deliverable ships delivery_mode "none"
                        (or equivalent), removing its only delivery backstop.
  3 DOUBLE_DELIVERY   — a cron registration enables delivery (--channel/--to/
                        --announce) while the prompt it feeds also self-sends.

Usage:
  check-cron-template-delivery.py [--root DIR] [--quiet]

Exit 0 = clean. Exit 1 = one or more violations. Exit 2 = could not run.
"""

import argparse
import json
import os
import re
import sys

# Directories never worth scanning (vendored, VCS, evidence dumps, fixtures that
# exist precisely to carry bad shapes for other tests to detect).
SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".pytest_cache",
    "evidence", "live-run", "working", "QUALITY-CONTROL", "ledgers",
}
# Fixture trees are allowed to contain deliberately-bad shapes.
SKIP_PATH_PARTS = ("/tests/fixtures/", "/fixtures/", "/test-fixtures/")

TEXT_EXTS = (".txt", ".md", ".sh", ".json")

# ── CHECK 1 patterns ────────────────────────────────────────────────────────
# A literal, inline delivery target inside PROMPT text.
SELF_ADDRESSING_PATTERNS = [
    (r"\btopic\s*#\s*\d+", "names a literal Topic #N"),
    (r"\btelegram_topic\b", "uses telegram_topic (not a valid send target)"),
    (r"\bmessage_thread_id\b", "uses message_thread_id inline"),
    (r"\bpost\b[^.\n]{0,60}?\bto\s+(?:this|the)\s+topic\b", "instructs 'post ... to this/the topic'"),
    (r"\bsend\b[^.\n]{0,60}?\bto\s+topic\b", "instructs 'send ... to topic'"),
    (r"--to\s+['\"]?\d{4,}", "hardcodes a numeric --to chat id"),
    (r"--target\s+['\"]?\d{4,}", "hardcodes a numeric --target chat id"),
    (r"\bto\s*[:=]\s*['\"]\d{1,}['\"]", "hardcodes a quoted to: target"),
    (r"@telegram\b", "addresses @telegram (Telegram's own broadcast channel; returns 403)"),
]

# ── CHECK 2 patterns ────────────────────────────────────────────────────────
DELIVERY_NONE_PATTERNS = [
    r"delivery_mode\s*[:=]\s*['\"]?none\b",
    r"['\"]delivery_mode['\"]\s*:\s*['\"]none['\"]",
    r"['\"]delivery['\"]\s*:\s*['\"]none['\"]",
    r"--delivery-mode\s+none\b",
]
# Words that mark a cron as producing something FOR the client, where losing the
# output is a real loss. Internal maintenance/guard crons may be silent.
CLIENT_FACING_WORDS = (
    "briefing", "digest", "report", "summary", "deliverable", "newsletter",
    "recap", "roundup", "content", "post", "playbook",
)
INTERNAL_WORDS = (
    "guard", "healer", "heal", "reaper", "sweep", "probe", "liveness",
    "drift", "watchdog", "monitor", "reconcile", "audit", "selftest",
    "self-test", "smoke", "tick", "heartbeat", "resume", "backfill",
    "migration", "cleanup", "alert",
)

# ── CHECK 3 ─────────────────────────────────────────────────────────────────
SELF_SEND_RE = re.compile(r"openclaw\s+message\s+send", re.I)
DELIVERY_FLAG_RE = re.compile(r"--channel\b|--to\b|--announce\b")
CRON_REG_RE = re.compile(r"openclaw\s+cron\s+(?:add|create)\b", re.I)


def should_skip(path):
    norm = path.replace(os.sep, "/")
    if any(part in norm for part in SKIP_PATH_PARTS):
        return True
    return False


def walk_files(root):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            if not fn.endswith(TEXT_EXTS):
                continue
            full = os.path.join(dirpath, fn)
            if should_skip(full):
                continue
            yield full


def read_text(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except (OSError, IOError):
        return None


def is_prompt_template(path, text):
    """A file that carries cron PROMPT text shipped to a box."""
    base = os.path.basename(path).lower()
    if base.endswith(".cron.json"):
        return True
    if "prompt" in base and base.endswith(".txt"):
        return True
    return False


def strip_line_comments(line):
    """Drop a trailing shell comment so prose in comments cannot trip CHECK 3."""
    out, in_s, in_d = [], False, False
    for ch in line:
        if ch == "'" and not in_d:
            in_s = not in_s
        elif ch == '"' and not in_s:
            in_d = not in_d
        elif ch == "#" and not in_s and not in_d:
            break
        out.append(ch)
    return "".join(out)


def join_continuations(text):
    """Yield (start_lineno, joined_command) for backslash-continued lines."""
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        start = i + 1
        buf = lines[i]
        while buf.rstrip().endswith("\\") and i + 1 < len(lines):
            i += 1
            buf = buf.rstrip()[:-1] + " " + lines[i]
        yield start, buf
        i += 1


def classify_client_facing(blob):
    low = blob.lower()
    if any(w in low for w in CLIENT_FACING_WORDS) and not any(
        w in low for w in INTERNAL_WORDS
    ):
        return True
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    root = os.path.abspath(args.root)
    if not os.path.isdir(root):
        sys.stderr.write("FATAL: --root is not a directory: %s\n" % root)
        return 2

    violations = []
    scanned = 0
    prompt_templates = 0
    registrations = 0

    # Prompt templates that deliver their own messages. Used by CHECK 3.
    self_sending_templates = set()

    files = list(walk_files(root))
    texts = {}
    for path in files:
        t = read_text(path)
        if t is None:
            continue
        texts[path] = t
        scanned += 1

    # ---- pass 1: prompt templates (CHECK 1 + CHECK 2) ----
    for path, text in texts.items():
        rel = os.path.relpath(path, root)
        if not is_prompt_template(path, text):
            continue
        prompt_templates += 1
        if SELF_SEND_RE.search(text):
            self_sending_templates.add(os.path.basename(path))

        for lineno, raw in enumerate(text.splitlines(), 1):
            for pat, why in SELF_ADDRESSING_PATTERNS:
                if re.search(pat, raw, re.I):
                    violations.append(
                        ("SELF_ADDRESSING", rel, lineno, why, raw.strip()[:160])
                    )

        # CHECK 2 on prompt templates / cron json
        for lineno, raw in enumerate(text.splitlines(), 1):
            for pat in DELIVERY_NONE_PATTERNS:
                if re.search(pat, raw, re.I):
                    if classify_client_facing(text):
                        violations.append(
                            ("DELIVERY_NONE", rel, lineno,
                             "client-facing deliverable ships a no-delivery mode; "
                             "a failed self-send then means TOTAL LOSS",
                             raw.strip()[:160])
                        )

    # ---- pass 2: cron registrations (CHECK 2 on registrars + CHECK 3) ----
    for path, text in texts.items():
        rel = os.path.relpath(path, root)
        if not CRON_REG_RE.search(text):
            continue
        for lineno, cmd in join_continuations(text):
            clean = strip_line_comments(cmd)
            if not CRON_REG_RE.search(clean):
                continue
            registrations += 1

            # CHECK 2: --delivery-mode none on a client-facing registration
            for pat in DELIVERY_NONE_PATTERNS:
                if re.search(pat, clean, re.I) and classify_client_facing(clean):
                    violations.append(
                        ("DELIVERY_NONE", rel, lineno,
                         "client-facing cron registered with no delivery path",
                         clean.strip()[:160])
                    )

            # CHECK 3: delivery flags + a self-sending prompt payload
            if not DELIVERY_FLAG_RE.search(clean):
                continue
            for tmpl in sorted(self_sending_templates):
                if tmpl in clean:
                    violations.append(
                        ("DOUBLE_DELIVERY", rel, lineno,
                         "cron enables delivery (--channel/--to/--announce) while the "
                         "prompt it feeds (%s) also sends its own messages — TWO "
                         "delivery paths; the scheduler ships the final turn text "
                         "(often partial) and the real deliverable is lost" % tmpl,
                         clean.strip()[:160])
                    )

    if not args.quiet:
        print("cron-template delivery gate")
        print("  files scanned            : %d" % scanned)
        print("  cron prompt templates    : %d" % prompt_templates)
        print("  cron registrations       : %d" % registrations)
        print("  self-delivering templates: %s" % (
            ", ".join(sorted(self_sending_templates)) or "none"))
        print("")

    if violations:
        for kind, rel, lineno, why, snippet in violations:
            print("VIOLATION [%s] %s:%d" % (kind, rel, lineno))
            print("    why : %s" % why)
            print("    line: %s" % snippet)
        print("")
        print("FAIL - %d cron delivery violation(s)." % len(violations))
        return 1

    if not args.quiet:
        print("PASS - every cron template has exactly one delivery path and no "
              "inline literal targets.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(2)
