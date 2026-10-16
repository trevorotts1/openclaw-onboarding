#!/usr/bin/env python3
"""
Skill 72 grammar linter.

Scans a scene animation HTML/JS file against the machine-checkable parts of
references/motion-grammar.md and references/animation-contract.md.

It FLAGS violations; it never auto-fixes. Exit 0 means clean (warnings are
printed but do not fail). Exit 1 means at least one violation.

Checks:
  - window.__setTime is defined (contract requirement)
  - no CSS transitions or CSS animations (break determinism)
  - no setTimeout / setInterval driving motion (the driver owns time);
    detection (MG-030, D-LINT-TIMER) reads a comment/string-stripped
    view of the source, so quoted or commented mentions do not fire,
    and timers reached through computed access or aliases are flagged
    as dynamic timers instead of passing silently
  - no unseeded Math.random (same t must give same pixels)
  - no GPU-layer tricks (translate3d, translateZ(0), will-change):
    composited layers cache rasters, so one t can paint differently
    depending on the previous frame. This is the legacy __setTime
    engine's rule; the per-engine rule sets live in
    references/animation-contract.md.
  - possible glow abuse: large-blur text/box shadows (warning only)
  - choreography policy (MG-019, references/choreography-vocabulary.json):
    every scene declares window.__choreography with one intent and its
    behaviors; declared behaviors must be permitted for that intent;
    behaviors detected in the source must be declared; a scene declares
    at most the vocabulary's per-scene behavior cap; and spring is
    forbidden on data marks (an overshooting spring misstates values).

The determinism checks above are unchanged from the original linter.
The choreography checks are additive: they replace the old docs-only
springs-only policy with intent-aware enforcement.

Usage:
  python3 scripts/lint-grammar.py scenes/scene-01.html
"""
import json
import re
import sys
from pathlib import Path

VIOLATIONS = [
    ("css-transition",
     re.compile(r"(?<![-a-z])transition\s*[:=]"),
     "CSS transition found: all motion must be set imperatively inside __setTime"),
    ("css-animation",
     re.compile(r"@keyframes|(?<![-a-z])animation\s*:"),
     "CSS animation found: all motion must be set imperatively inside __setTime"),
    ("timer",
     re.compile(r"\bset(Timeout|Interval)\s*\("),
     "setTimeout/setInterval found: the frame driver owns time, the page must not advance itself"),
    ("unseeded-random",
     re.compile(r"\bMath\.random\s*\("),
     "Math.random found: use a seeded PRNG keyed off t so the same t renders identically"),
    ("gpu-layer",
     re.compile(r"translate3d\s*\(|translateZ\s*\(\s*0|will-change\s*:"),
     "GPU-layer trick found (translate3d/translateZ(0)/will-change): composited layers cache "
     "rasters, so one t can paint differently depending on the previous frame"),
]

WARNINGS = [
    ("possible-glow",
     re.compile(r"(text-shadow|box-shadow)\s*:[^;]*\b([3-9]\d|\d{3,})px"),
     "large-blur shadow found: check against the banned-cliche list (glow on chrome/type)"),
]

REQUIRED = [
    ("settime",
     re.compile(r"window\.__setTime\s*="),
     "window.__setTime(t) is not defined: the frame driver cannot render this scene"),
]

# --- Timer detection views (MG-030, D-LINT-TIMER) ---------------------------
# The pre-MG-030 timer check ran a case-broken regex over the raw source:
# it missed the ordinary spelling setTimeout entirely, and a raw scan
# cannot distinguish a real call from the same text inside a string or a
# comment. The fix keeps this linter's line-oriented shape but gives the
# timer family lexical views of the source:
#
#   code view:    string literals and comments blanked to spaces
#                 (newlines preserved, so offsets and line numbers are
#                 unchanged). Direct timer calls are searched here, so
#                 quoted or commented mentions cannot fire.
#   comment view: only comments blanked. The dynamic-timer patterns are
#                 searched here because their evidence is a quoted timer
#                 name inside brackets.
#
# Template literal ${ ... } interpolations are code in both views: the
# scanner blanks the literal text and scans interpolations as code.
# Known limit: JavaScript regex literals are not lexed, so a regex
# literal containing a quote or a comment opener can confuse the views;
# scene files in this engine do not use such literals, and the TS
# validation layer (runtime/src/lint) parses real ASTs for new code.

def _blank_views(src):
    """Return (code_view, comment_view) of src, each the same length."""
    code = list(src)
    comment = list(src)
    n = len(src)

    def blank(buf, i, j):
        for k in range(i, j):
            if buf[k] != "\n":
                buf[k] = " "

    def scan(i, in_template_expr):
        depth = 0
        while i < n:
            c = src[i]
            two = src[i:i + 2]
            if two == "//":
                j = src.find("\n", i)
                if j == -1:
                    j = n
                blank(code, i, j)
                blank(comment, i, j)
                i = j
            elif two == "/*":
                j = src.find("*/", i + 2)
                j = n if j == -1 else j + 2
                blank(code, i, j)
                blank(comment, i, j)
                i = j
            elif c in "\"'":
                j = i + 1
                while j < n:
                    if src[j] == "\\":
                        j += 2
                        continue
                    if src[j] == c or src[j] == "\n":
                        break
                    j += 1
                end = j + 1 if j < n and src[j] == c else j
                blank(code, i, end)
                i = end
            elif c == "`":
                i = scan_template(i)
            elif in_template_expr and c == "{":
                depth += 1
                i += 1
            elif in_template_expr and c == "}":
                if depth == 0:
                    return i
                depth -= 1
                i += 1
            else:
                i += 1
        return i

    def scan_template(i):
        start = i
        i += 1
        seg = start
        while i < n:
            c = src[i]
            if c == "\\":
                i += 2
                continue
            if c == "`":
                blank(code, seg, i + 1)
                return i + 1
            if src[i:i + 2] == "${":
                blank(code, seg, i)
                i = scan(i + 2, True)
                if i < n and src[i] == "}":
                    i += 1
                seg = i
                continue
            i += 1
        blank(code, seg, n)
        return n

    scan(0, False)
    return "".join(code), "".join(comment)


_DYNAMIC_MSG = ("timer reached dynamically (%s): the frame driver owns time; "
                "a timer the linter cannot see directly is still a timer")

_DYNAMIC_LITERAL = re.compile(
    r"(?:window|globalThis|self)\s*\[\s*['\"]set(?:Timeout|Interval)['\"]\s*\]\s*\(")
_DYNAMIC_CONCAT = re.compile(
    r"(?:window|globalThis|self)\s*\[(?P<bracket>[^\]\n]*\+[^\]\n]*)\]\s*\(")
_DYNAMIC_INDIRECT = re.compile(
    r"(?:window|globalThis|self)\s*\[\s*[A-Za-z_$][\w$]*\s*\]\s*\(")
_TIMER_FRAGMENTS = ("set", "timeout", "interval")
_ALIAS_DEF = re.compile(
    r"(?:var|let|const)?\s*([A-Za-z_$][\w$]*)\s*=\s*"
    r"(?:window\.|globalThis\.|self\.)?set(?:Timeout|Interval)\b")
_DESTRUCTURE_DEF = re.compile(
    r"(?:var|let|const)\s*\{[^}\n]*?\bset(?:Timeout|Interval)\s*:\s*"
    r"([A-Za-z_$][\w$]*)")
_TIMER_NAMES = ("setTimeout", "setInterval")


def dynamic_timer_violations(comment_view, code_view):
    """Timers reached through computed access or aliases.

    Returns (name, line, message) triples with name "dynamic-timer".
    A call through the clock's own name is the direct check's business;
    this check exists so that renaming or computing the access cannot
    launder a timer into a pass.
    """
    out = []

    def line_of(view, pos):
        return view.count("\n", 0, pos) + 1

    for m in _DYNAMIC_LITERAL.finditer(comment_view):
        out.append(("dynamic-timer", line_of(comment_view, m.start()),
                    _DYNAMIC_MSG % "computed access by literal name"))
    for m in _DYNAMIC_CONCAT.finditer(comment_view):
        fragments = re.findall(r"['\"]([^'\"]*)['\"]", m.group("bracket"))
        if any(f.lower() in _TIMER_FRAGMENTS for f in fragments):
            out.append(("dynamic-timer", line_of(comment_view, m.start()),
                        _DYNAMIC_MSG % "computed access by concatenation"))
    for m in _DYNAMIC_INDIRECT.finditer(comment_view):
        out.append(("dynamic-timer", line_of(comment_view, m.start()),
                    _DYNAMIC_MSG % "computed access by indirect name"))

    aliases = set()
    for rx in (_ALIAS_DEF, _DESTRUCTURE_DEF):
        for m in rx.finditer(code_view):
            if m.group(1) not in _TIMER_NAMES:
                aliases.add(m.group(1))
    for alias in sorted(aliases):
        call_rx = re.compile(r"\b" + re.escape(alias) + r"\s*\(")
        for m in call_rx.finditer(code_view):
            out.append(("dynamic-timer", line_of(code_view, m.start()),
                        _DYNAMIC_MSG % ("alias %r" % alias)))
    return out


# --- Choreography policy (MG-019) -------------------------------------------
# The vocabulary is the machine-readable mirror of references/motion-grammar.md.
# A scene declares its choreography in a window.__choreography object literal:
#   window.__choreography = {"intent": "decisive_reveal",
#                            "behaviors": ["mask", "spring"],
#                            "data_marks": false};
# Detected behavior tokens follow the "detection" notes in the vocabulary.

VOCABULARY_PATH = (Path(__file__).resolve().parent.parent
                   / "references" / "choreography-vocabulary.json")

CHOREO_BLOCK = re.compile(r"window\.__choreography\s*=\s*\{(?P<body>.*?)\}", re.S)
CHOREO_INTENT = re.compile(r"""["']intent["']\s*:\s*["']([^"']+)["']""")
CHOREO_INTENTS = re.compile(r"""["']intents["']\s*:\s*\[(?P<items>[^\]]*)\]""")
CHOREO_BEHAVIORS = re.compile(r"""["']behaviors["']\s*:\s*\[(?P<items>[^\]]*)\]""")
CHOREO_DATA_MARKS = re.compile(r"""["']data_marks["']\s*:\s*(true|false)""")
CHOREO_STRING = re.compile(r"""["']([^"']+)["']""")

BEHAVIOR_DETECTORS = [
    ("spring",
     re.compile(r"\bspring\s*\(|\b(weighty|snap|drift)\b"),
     "spring motion (spring helper call or a named spring preset)"),
    ("eased",
     re.compile(r"cubic-bezier\s*\(|\bease(In|Out|InOut)[A-Za-z]*\s*\("),
     "eased motion (cubic-bezier or an ease function)"),
    ("linear",
     re.compile(r"\blerp\s*\("),
     "linear interpolation (lerp call)"),
    ("mask",
     re.compile(r"mask-image|clip-path"),
     "mask reveal (mask-image or clip-path)"),
    ("depth",
     re.compile(r"perspective\s*\(|perspective\s*:|rotateX\s*\(|rotateY\s*\(|rotate3d\s*\("),
     "depth staging (perspective or 3D rotation)"),
]


def load_vocabulary():
    try:
        with open(VOCABULARY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError) as e:
        print("cannot load choreography vocabulary %s: %s"
              % (VOCABULARY_PATH, e), file=sys.stderr)
        sys.exit(2)


def choreography_violations(src, vocab):
    """Return a list of (name, line, message) choreography violations."""
    out = []

    def line_of(pos):
        return src.count("\n", 0, pos) + 1

    block = CHOREO_BLOCK.search(src)
    if not block:
        out.append(("choreography-undeclared", 1,
                    "no window.__choreography declaration: declare one intent and its "
                    "behaviors from references/choreography-vocabulary.json so the "
                    "scene's motion is chosen by story purpose, not by habit"))
        return out
    body = block.group("body")
    block_line = line_of(block.start())

    intents_m = CHOREO_INTENTS.search(body)
    if intents_m and len(CHOREO_STRING.findall(intents_m.group("items"))) > 1:
        out.append(("choreography-incoherent", block_line,
                    "multiple intents declared: one scene carries one intent "
                    "(vocabulary coherence rule)"))
    intent_m = CHOREO_INTENT.search(body)
    intent = intent_m.group(1) if intent_m else None
    if intent is None:
        out.append(("choreography-undeclared", block_line,
                    "__choreography declares no intent: name one intent from the "
                    "choreography vocabulary"))
        return out
    intent_spec = vocab.get("intents", {}).get(intent)
    if intent_spec is None:
        out.append(("choreography-unknown-intent", block_line,
                    "intent %r is not in the choreography vocabulary" % intent))
        return out

    behaviors_m = CHOREO_BEHAVIORS.search(body)
    declared = (CHOREO_STRING.findall(behaviors_m.group("items"))
                if behaviors_m else [])
    if not declared:
        out.append(("choreography-undeclared", block_line,
                    "__choreography declares no behaviors: list the behaviors the "
                    "scene uses so they can be checked against the intent"))
        return out

    known = vocab.get("behaviors", {})
    permitted = intent_spec.get("permitted_behaviors", [])
    for behavior in declared:
        if behavior not in known:
            out.append(("choreography-unknown-behavior", block_line,
                        "behavior %r is not in the choreography vocabulary" % behavior))
        elif behavior not in permitted:
            out.append(("choreography-behavior-not-permitted", block_line,
                        "behavior %r is not permitted for intent %r; permitted: %s"
                        % (behavior, intent, ", ".join(permitted))))
    cap = vocab.get("coherence", {}).get("max_behaviors_per_scene")
    if cap is not None and len(declared) > cap:
        out.append(("choreography-incoherent", block_line,
                    "%d behaviors declared, over the per-scene cap of %d: use a small "
                    "coherent vocabulary per scene, not every effect at once"
                    % (len(declared), cap)))

    detected = {}
    for behavior, rx, _desc in BEHAVIOR_DETECTORS:
        m = rx.search(src)
        if m:
            detected[behavior] = line_of(m.start())
    for behavior, line in detected.items():
        if behavior not in declared:
            desc = next(d for b, _r, d in BEHAVIOR_DETECTORS if b == behavior)
            out.append(("choreography-undeclared-behavior", line,
                        "%s is used but not declared in __choreography: declare it "
                        "so the intent check covers it" % desc))

    dm_m = CHOREO_DATA_MARKS.search(body)
    if dm_m and dm_m.group(1) == "true":
        forbidden = vocab.get("data_marks", {}).get("forbidden_behaviors", [])
        for behavior in forbidden:
            if behavior in declared or behavior in detected:
                out.append(("choreography-data-overshoot", block_line,
                            "%s is forbidden on data marks: an overshooting spring "
                            "temporarily states a value the data does not contain "
                            "(MG-015); interpolate the marks linearly or with an "
                            "ease, and let containers spring instead" % behavior))
    return out


def main():
    if len(sys.argv) != 2:
        print("usage: lint-grammar.py <scene-file.html>", file=sys.stderr)
        sys.exit(2)
    path = sys.argv[1]
    try:
        with open(path, "r", encoding="utf-8") as f:
            src = f.read()
    except OSError as e:
        print("cannot read %s: %s" % (path, e), file=sys.stderr)
        sys.exit(2)

    code_view, comment_view = _blank_views(src)

    bad = 0
    for name, rx, msg in REQUIRED:
        if not rx.search(src):
            print("VIOLATION [%s] %s" % (name, msg))
            bad += 1
    for name, rx, msg in VIOLATIONS:
        # The timer family reads the code view, where strings and
        # comments are blanked (MG-030); every other legacy check reads
        # the raw source exactly as before.
        view = code_view if name == "timer" else src
        for m in rx.finditer(view):
            line = view.count("\n", 0, m.start()) + 1
            print("VIOLATION [%s] line %d: %s" % (name, line, msg))
            bad += 1
    for name, line, msg in dynamic_timer_violations(comment_view, code_view):
        print("VIOLATION [%s] line %d: %s" % (name, line, msg))
        bad += 1
    vocab = load_vocabulary()
    for name, line, msg in choreography_violations(src, vocab):
        print("VIOLATION [%s] line %d: %s" % (name, line, msg))
        bad += 1
    for name, rx, msg in WARNINGS:
        for m in rx.finditer(src):
            line = src.count("\n", 0, m.start()) + 1
            print("WARNING [%s] line %d: %s" % (name, line, msg))

    if bad:
        print("%d violation(s) in %s: fix them, the linter does not auto-fix" % (bad, path))
        sys.exit(1)
    print("grammar lint clean: %s" % path)


if __name__ == "__main__":
    main()
