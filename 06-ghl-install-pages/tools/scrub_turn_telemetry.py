#!/usr/bin/env python3
"""scrub_turn_telemetry.py — strip leaked MCP tool-name prefixes from captured
agent-turn telemetry BEFORE it lands on disk (Skill 06, T4 / V2 evidence; R7 P3).

WHY THIS EXISTS
---------------
The V2 (autonomous-agent) run captured the dept agent's turn telemetry to disk
(``logs/agent-turn-*.out.json``). Those captures contained MCP tool names of the
shape ``redacted-client__<verb>`` (e.g. ``redacted-client__messages_send``,
``redacted-client__conversations_list``) — a client-channel namespace prefix that
must NEVER land in the operator/fixture evidence tree (the repo + the durable
evidence root are FLEET-WIDE; no client name/namespace may appear).

This module scrubs that prefix out of any captured telemetry (JSON or text)
before it is written, replacing the client namespace with a neutral
``mcp__redacted`` token and recording what it changed (so the scrub itself is
auditable). It is a pure, side-effect-light transform: ``scrub_text`` /
``scrub_obj`` are pure; ``scrub_file`` reads one file and writes the cleaned
copy. NO network, NO browser.

It is deliberately GENERIC: a caller passes the namespace tokens to redact
(default: the known ``redacted-client`` leak token), so the same tool guards any
future client-namespace leak without hardcoding a client identity here.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Any

# The default leak token observed in the V2 capture. Anything matching
# ``<token>__<verb>`` (the MCP tool-name convention is ``<server>__<tool>``) is a
# leaked client-namespaced tool name and is neutralised. Callers may pass extra
# tokens; this is the floor.
DEFAULT_LEAK_TOKENS = ("redacted-client",)

# The neutral replacement namespace. Keeps the ``__verb`` suffix so the telemetry
# still reads as "some MCP tool fired" without naming the client channel.
NEUTRAL_NAMESPACE = "mcp__redacted"


def _token_re(tokens: tuple[str, ...]) -> re.Pattern[str]:
    """Build a regex matching ``<token>__`` (the namespaced MCP prefix) for any
    of ``tokens``. Only the namespace PREFIX is matched (up to and including the
    ``__`` separator) so the specific tool verb after it is preserved."""
    if not tokens:
        raise ValueError("at least one leak token is required")
    alt = "|".join(re.escape(t) for t in tokens)
    # Match the token as a namespace segment immediately followed by the MCP
    # ``__`` separator. Word-ish boundary on the left so we don't clip a larger
    # identifier that merely ends with the token.
    return re.compile(rf"(?<![\w-])({alt})__")


def scrub_text(text: str, tokens: tuple[str, ...] = DEFAULT_LEAK_TOKENS,
               neutral: str = NEUTRAL_NAMESPACE) -> tuple[str, int]:
    """Replace every ``<leak-token>__`` namespace prefix with ``<neutral>__``.

    Returns ``(scrubbed_text, replacement_count)``. Pure — no I/O. The tool VERB
    after ``__`` is preserved (only the client namespace is neutralised), so the
    telemetry remains useful for debugging ("an MCP send fired") without naming
    the client channel.
    """
    rx = _token_re(tokens)
    count = 0

    def _sub(_m: re.Match[str]) -> str:
        nonlocal count
        count += 1
        return f"{neutral}__"

    return rx.sub(_sub, text), count


def scrub_obj(obj: Any, tokens: tuple[str, ...] = DEFAULT_LEAK_TOKENS,
              neutral: str = NEUTRAL_NAMESPACE) -> tuple[Any, int]:
    """Recursively scrub a JSON-like object (dict/list/str). Scrubs both VALUES
    and dict KEYS (a leaked tool name can appear as a key, e.g. a per-tool
    timing map). Returns ``(scrubbed_obj, replacement_count)``. Pure."""
    total = 0
    if isinstance(obj, str):
        s, c = scrub_text(obj, tokens, neutral)
        return s, c
    if isinstance(obj, list):
        out_list = []
        for item in obj:
            v, c = scrub_obj(item, tokens, neutral)
            total += c
            out_list.append(v)
        return out_list, total
    if isinstance(obj, dict):
        out: dict = {}
        for k, v in obj.items():
            new_k = k
            if isinstance(k, str):
                new_k, ck = scrub_text(k, tokens, neutral)
                total += ck
            new_v, cv = scrub_obj(v, tokens, neutral)
            total += cv
            out[new_k] = new_v
        return out, total
    # Numbers / bool / None — nothing to scrub.
    return obj, 0


def scrub_file(in_path: str, out_path: str | None = None,
               tokens: tuple[str, ...] = DEFAULT_LEAK_TOKENS,
               neutral: str = NEUTRAL_NAMESPACE) -> dict:
    """Scrub one captured-telemetry file and write the cleaned copy.

    JSON files are parsed and scrubbed structurally (keys + values); any other
    file is scrubbed as text. ``out_path`` defaults to ``in_path`` (in-place).
    Returns an audit record ``{in, out, replacements, format}``. This is the
    only function here that touches the filesystem.
    """
    out_path = out_path or in_path
    with open(in_path, encoding="utf-8") as f:
        raw = f.read()

    fmt = "json" if in_path.endswith(".json") else "text"
    if fmt == "json":
        try:
            data = json.loads(raw)
            scrubbed, n = scrub_obj(data, tokens, neutral)
            payload = json.dumps(scrubbed, indent=2)
        except json.JSONDecodeError:
            # Not actually valid JSON despite the extension — scrub as text so we
            # never fail-open and leave a leak on disk.
            fmt = "text"
            payload, n = scrub_text(raw, tokens, neutral)
    else:
        payload, n = scrub_text(raw, tokens, neutral)

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(payload)
    return {"in": in_path, "out": out_path, "replacements": n, "format": fmt}


def is_clean(text: str, tokens: tuple[str, ...] = DEFAULT_LEAK_TOKENS) -> bool:
    """True iff ``text`` contains NO leaked ``<token>__`` namespace prefix. Used
    as a post-write assertion (the scrub must leave nothing behind)."""
    return _token_re(tokens).search(text) is None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Scrub leaked client-namespaced MCP tool-name prefixes from "
                    "captured agent-turn telemetry before it lands on disk.")
    ap.add_argument("paths", nargs="+", help="telemetry files to scrub (in-place)")
    ap.add_argument("--token", action="append", default=[],
                    help="extra leak namespace token to redact (repeatable); "
                         "the default 'redacted-client' is always included")
    ap.add_argument("--out-dir", default=None,
                    help="write cleaned copies here instead of in-place")
    ap.add_argument("--check", action="store_true",
                    help="do not write; exit non-zero if any leak is present")
    args = ap.parse_args(argv)

    tokens = tuple(DEFAULT_LEAK_TOKENS) + tuple(args.token)

    if args.check:
        leaked = []
        for p in args.paths:
            with open(p, encoding="utf-8") as f:
                if not is_clean(f.read(), tokens):
                    leaked.append(p)
        if leaked:
            sys.stderr.write("LEAK PRESENT in: " + ", ".join(leaked) + "\n")
            return 1
        print("CLEAN (no leaked client-namespaced tool names)")
        return 0

    records = []
    for p in args.paths:
        out = (os.path.join(args.out_dir, os.path.basename(p))
               if args.out_dir else p)
        records.append(scrub_file(p, out, tokens))
    print(json.dumps(records, indent=2))
    total = sum(r["replacements"] for r in records)
    # Exit 0 always on a successful scrub (replacements==0 is fine — already clean).
    return 0 if total >= 0 else 1


if __name__ == "__main__":
    sys.exit(main())
