#!/usr/bin/env python3
"""ghl_ab_executor.py — agent-browser 0.27.0 ANCHOR→EXECUTOR resolver (Skill 06).

WHY THIS EXISTS (fix `a` of the Phase-A community/course live-ready work):
The community/course builders (and the SELECTORS-LIVE docs) record their in-area
anchors in Playwright notation — `getByRole('button', { name: 'Create Group' })`,
`getByText('Memberships')`, `getByPlaceholder('Group Name')`. That notation is the
human-readable canonical form and matches the locked form/survey docs. BUT
**agent-browser 0.27.0 `click`/`fill` REJECT those strings** — its `click <sel>`
accepts only a CSS selector, XPath, or an `@ref` from `snapshot`. Live-proven on the
operator template location (2026-07-10, ledger "LIVE-CAPTURE ATTEMPT"):
    click "getByRole('button',{name:'Create Group'})"  -> "Element not found"
    click "Create Group"                                -> not found
    click "text=Create Group"                           -> not found
The ONLY things that resolve are:
  1. the SEPARATE `find` subcommand:  `find role button click --name "Create Group"`
     (also `find text "Memberships" click`, `find placeholder "Group Name" fill "x"`);
  2. a native DOM `element.click()` via `eval` — REQUIRED for Naive-UI submit buttons
     ("Create Group" / "CREATE CHANNEL" confirms) where `find ... click` and `click @ref`
     report "✓ Done" but do NOT actually submit (proven: only native `.click()` fired the
     "Group Created" toast). Also the fallback for ref-less Quick-Add tiles.

This module is the ADAPTER: it parses a Playwright-style anchor into a descriptor and
emits the exact agent-browser 0.27.0 invocation the builders route EVERY click/fill
through. Verified OFFLINE against `agent-browser find --help` / `click --help` /
`eval --help` (0.27.0) and the proven `ghl_form_builder._ab` call path. Whether the
real GHL community/course canvas ACCEPTS these calls is a **Phase B live proof**
(the anchors are still `capture-pending`; this module makes the code READY).

QUOTING (load-bearing): `ghl_form_builder._ab(session, *args)` builds one command
STRING via `ghl_builder.browser_cmd(*args)` (a plain space-join, NO quoting) and then
`shlex.split()`s it back into argv. So a multi-word value passed raw
(`--name`, `Create Group`) is RE-SPLIT into two argv tokens and the name breaks. Every
dynamic value this module emits is therefore `shlex.quote`d so it round-trips as a
single token. (Proven: `shlex.split('... --name ' + shlex.quote('Create Group'))`
yields `['--name', 'Create Group']`.)

No network, no browser at import/selftest time. `--selftest` is fully offline.
"""
from __future__ import annotations

import json
import re
import shlex
import subprocess
import sys
from typing import Any, Callable, Dict, List, Optional

PINNED_AGENT_BROWSER = "0.27.0"

# agent-browser `find` locators that map 1:1 to a Playwright getBy* form.
_PW_RE = {
    "role": re.compile(
        r"getByRole\(\s*['\"]([^'\"]+)['\"]\s*"
        r"(?:,\s*\{\s*name:\s*(?:['\"]([^'\"]*)['\"]|/([^/]+)/[a-z]*)"
        r"(?:\s*,\s*exact:\s*(true|false))?\s*\})?\s*\)"),
    "text": re.compile(
        r"getByText\(\s*(?:['\"](.+?)['\"]|/([^/]+)/[a-z]*)"
        r"(?:\s*,\s*\{\s*exact:\s*(true|false)\s*\})?\s*\)"),
    "placeholder": re.compile(r"getByPlaceholder\(\s*['\"](.+?)['\"]\s*\)"),
    "label": re.compile(r"getByLabel\(\s*['\"](.+?)['\"]\s*\)"),
    "alt": re.compile(r"getByAltText\(\s*['\"](.+?)['\"]\s*\)"),
    "title": re.compile(r"getByTitle\(\s*['\"](.+?)['\"]\s*\)"),
    "testid": re.compile(r"getByTestId\(\s*['\"](.+?)['\"]\s*\)"),
}


def parse_anchor(anchor: str, kind: str = "") -> Dict[str, Any]:
    """Parse a Playwright-style `getBy*` anchor into a structured descriptor.

    Returns a dict with:
      strategy : 'role'|'text'|'placeholder'|'label'|'alt'|'title'|'testid'|'css'|'ref'
      role     : ARIA role (role strategy only)
      name     : plain accessible name (role strategy, plain-string form)
      name_regex / text_regex : the regex source when the anchor used /…/ (→ native)
      value    : the locator value for text/placeholder/label/alt/title/testid
      exact    : bool (default False)
    A `@ref` passes through as strategy='ref'; anything not getBy* passes through as
    strategy='css' (a raw CSS/XPath selector agent-browser can click directly)."""
    a = (anchor or "").strip()
    d: Dict[str, Any] = {"raw": a, "strategy": "css", "exact": False,
                         "role": "", "name": "", "value": "",
                         "name_regex": None, "text_regex": None}
    if not a:
        d["strategy"] = "css"
        return d
    if a.startswith("@"):
        d["strategy"] = "ref"
        d["value"] = a
        return d

    m = _PW_RE["role"].search(a)
    if m:
        d["strategy"] = "role"
        d["role"] = m.group(1)
        if m.group(2) is not None:
            d["name"] = m.group(2)
        if m.group(3) is not None:
            d["name_regex"] = m.group(3)
        d["exact"] = (m.group(4) == "true")
        return d
    m = _PW_RE["text"].search(a)
    if m:
        d["strategy"] = "text"
        if m.group(1) is not None:
            d["value"] = m.group(1)
        if m.group(2) is not None:
            d["text_regex"] = m.group(2)
        d["exact"] = (m.group(3) == "true")
        return d
    for strat in ("placeholder", "label", "alt", "title", "testid"):
        m = _PW_RE[strat].search(a)
        if m:
            d["strategy"] = strat
            d["value"] = m.group(1)
            return d

    # Not a getBy* form. Use the JSON `kind` hint to interpret a bare string, else CSS.
    hint = (kind or "").strip().lower()
    if hint in ("get_text", "text"):
        d["strategy"] = "text"
        d["value"] = a
    elif hint in ("placeholder",):
        d["strategy"] = "placeholder"
        d["value"] = a
    elif hint in ("label",):
        d["strategy"] = "label"
        d["value"] = a
    else:
        d["strategy"] = "css"
        d["value"] = a
    return d


def needs_native(descriptor: Dict[str, Any]) -> bool:
    """A regex name/text can't be expressed as `find --name <plain>` → resolve natively."""
    return bool(descriptor.get("name_regex") or descriptor.get("text_regex"))


def to_find_args(descriptor: Dict[str, Any], action: str = "click",
                 fill_value: Optional[str] = None) -> List[str]:
    """Build the agent-browser 0.27.0 `find` argv (as tokens for `_ab(session, *args)`).

    Dynamic values are `shlex.quote`d so they survive the browser_cmd space-join +
    shlex.split re-parse as SINGLE argv tokens (see module docstring). Returns [] when
    the strategy is not `find`-expressible (ref/css/regex → caller uses a raw click or
    the native path)."""
    strat = descriptor["strategy"]
    if strat in ("ref", "css") or needs_native(descriptor):
        return []
    if strat == "role":
        args = ["find", "role", descriptor["role"], action]
        if fill_value is not None:
            args.append(shlex.quote(fill_value))
        if descriptor.get("name"):
            args += ["--name", shlex.quote(descriptor["name"])]
        if descriptor.get("exact"):
            args.append("--exact")
        return args
    # text / placeholder / label / alt / title / testid: value is the positional
    args = ["find", strat, shlex.quote(descriptor["value"]), action]
    if fill_value is not None:
        args.append(shlex.quote(fill_value))
    if descriptor.get("exact"):
        args.append("--exact")
    return args


def native_click_js(descriptor: Dict[str, Any]) -> str:
    """JS for a trusted-DOM `element.click()` — the Naive-UI submit + ref-less-tile path.

    Matches an interactive element (button / [role=button] / a / menuitem / submit input)
    by accessible name or visible text (plain equality → contains → regex), climbing to
    the nearest clickable ancestor for a text node. Returns 'CLICKED:<label>' or
    'NOTFOUND' — never throws. This is the ONLY thing that submits GHL's Naive-UI create
    dialogs (proven live)."""
    want = descriptor.get("name") or descriptor.get("value") or ""
    rx = descriptor.get("name_regex") or descriptor.get("text_regex")
    want_json = json.dumps(want)
    rx_json = json.dumps(rx) if rx else "null"
    return (
        "(() => {"
        "  const want = " + want_json + ";"
        "  const rxSrc = " + rx_json + ";"
        "  const rx = rxSrc ? new RegExp(rxSrc, 'i') : null;"
        "  const norm = s => (s || '').replace(/\\s+/g, ' ').trim();"
        "  const sel = 'button,[role=button],a,[role=menuitem],[role=link],"
        "input[type=submit],input[type=button],[type=submit]';"
        "  const cands = Array.from(document.querySelectorAll(sel));"
        "  const match = e => {"
        "    const t = norm(e.textContent) || norm(e.value) ||"
        " norm(e.getAttribute && e.getAttribute('aria-label'));"
        "    if (rx) return rx.test(t);"
        "    return t === want || (want && t.includes(want));"
        "  };"
        "  let el = cands.find(match);"
        "  if (!el) {"
        "    const all = Array.from(document.querySelectorAll('*')).filter("
        "      e => e.children.length <= 2 && (rx ? rx.test(norm(e.textContent)) :"
        " norm(e.textContent) === want));"
        "    const t = all[0];"
        "    el = t ? (t.closest(sel) || t) : null;"
        "  }"
        "  if (!el) return 'NOTFOUND';"
        "  el.click();"
        "  return 'CLICKED:' + norm(el.textContent || el.value).slice(0, 40);"
        "})()"
    )


def native_fill_js(descriptor: Dict[str, Any], value: str) -> str:
    """JS to set an input/textarea value + dispatch input/change (Naive-UI reactive
    fallback when `find … fill` cannot resolve). Matches by placeholder / label / name."""
    key = descriptor.get("value") or descriptor.get("name") or ""
    return (
        "(() => {"
        "  const want = " + json.dumps(key) + ";"
        "  const val = " + json.dumps(value) + ";"
        "  const norm = s => (s || '').replace(/\\s+/g, ' ').trim();"
        "  const ins = Array.from(document.querySelectorAll('input,textarea'));"
        "  let el = ins.find(e => norm(e.placeholder) === want)"
        "        || ins.find(e => norm(e.getAttribute('aria-label')) === want)"
        "        || ins.find(e => norm(e.placeholder).includes(want));"
        "  if (!el) return 'NOTFOUND';"
        "  const setter = Object.getOwnPropertyDescriptor("
        "      window.HTMLInputElement.prototype, 'value') ||"
        "    Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value');"
        "  setter.set.call(el, val);"
        "  el.dispatchEvent(new Event('input', { bubbles: true }));"
        "  el.dispatchEvent(new Event('change', { bubbles: true }));"
        "  return 'FILLED';"
        "})()"
    )


def cp_ok(cp: Any) -> bool:
    """agent-browser success predicate: exit 0 AND no 'not found'/'timeout' in output."""
    if cp is None:
        return False
    rc = getattr(cp, "returncode", 1)
    out = ((getattr(cp, "stdout", "") or "") + " " + (getattr(cp, "stderr", "") or "")).lower()
    if rc != 0:
        return False
    return not re.search(r"not found|no element|no matching|timed? ?out|error:", out)


class AbExecutor:
    """Routes a Playwright-style anchor to an agent-browser 0.27.0 action.

    Dependency-injected: `ab(session, *args, timeout=…) -> CompletedProcess-like` and
    `ev(session, js, timeout=…) -> str`. Defaults bind to `ghl_form_builder._ab/_eval`
    at call time (late-bound) when available, so a builder's test monkeypatch is honored.
    """

    def __init__(self, ab: Optional[Callable] = None, ev: Optional[Callable] = None,
                 log: Optional[Callable[[str], None]] = None):
        self._ab = ab
        self._ev = ev
        self._log = log or (lambda m: None)

    # -- resolution helpers ---------------------------------------------------
    def _run_ab(self, session: str, *args: str, timeout: int = 15) -> Any:
        return self._ab(session, *args, timeout=timeout)

    def _native_click(self, session: str, descriptor: Dict[str, Any], timeout: int) -> Dict[str, Any]:
        js = native_click_js(descriptor)
        res = (self._ev(session, js, timeout=timeout) or "").strip()
        ok = res.startswith("CLICKED")
        return {"ok": ok, "path": "native", "detail": res, "descriptor": descriptor}

    # -- public API -----------------------------------------------------------
    def click(self, session: str, anchor: str, *, kind: str = "", mode: str = "auto",
              timeout: int = 15) -> Dict[str, Any]:
        """Resolve + click. mode: 'auto' (find, then native fallback on a find miss),
        'find' (find only), 'native' (Naive-UI submit / ref-less tile — eval .click())."""
        d = parse_anchor(anchor, kind)
        if d["strategy"] == "ref":
            cp = self._run_ab(session, "click", d["value"], timeout=timeout)
            return {"ok": cp_ok(cp), "path": "ref", "descriptor": d}
        if d["strategy"] == "css" and not needs_native(d):
            cp = self._run_ab(session, "click", d["value"] or anchor, timeout=timeout)
            return {"ok": cp_ok(cp), "path": "css", "descriptor": d}
        if mode == "native" or needs_native(d):
            return self._native_click(session, d, timeout)
        args = to_find_args(d, "click")
        cp = self._run_ab(session, *args, timeout=timeout)
        if cp_ok(cp):
            return {"ok": True, "path": "find", "args": args, "descriptor": d}
        if mode == "auto":
            self._log(f"find miss for {anchor!r} — native fallback")
            return self._native_click(session, d, timeout)
        return {"ok": False, "path": "find", "args": args, "descriptor": d}

    def fill(self, session: str, anchor: str, value: str, *, kind: str = "",
             timeout: int = 15) -> Dict[str, Any]:
        d = parse_anchor(anchor, kind)
        if d["strategy"] in ("ref", "css") and not needs_native(d):
            cp = self._run_ab(session, "fill", d["value"] or anchor, value, timeout=timeout)
            if cp_ok(cp):
                return {"ok": True, "path": d["strategy"], "descriptor": d}
        else:
            args = to_find_args(d, "fill", fill_value=value)
            if args:
                cp = self._run_ab(session, *args, timeout=timeout)
                if cp_ok(cp):
                    return {"ok": True, "path": "find", "args": args, "descriptor": d}
        # native reactive-set fallback
        res = (self._ev(session, native_fill_js(d, value), timeout=timeout) or "").strip()
        return {"ok": res == "FILLED", "path": "native", "detail": res, "descriptor": d}

    def wait_text(self, session: str, text: str, *, timeout: int = 20) -> Any:
        """Wait for `text` — value shlex-quoted so a multi-word name is ONE argv token
        (the un-quoted `_ab(session,'wait','--',text)` glue splits 'Create Group' into
        two tokens and waits on the wrong selector)."""
        return self._run_ab(session, "wait", "--", shlex.quote(text), timeout=timeout)


# ---------------------------------------------------------------------------
# CLI / selftest — fully offline (no network, no browser)
# ---------------------------------------------------------------------------
def _selftest() -> int:  # noqa: C901
    errors: List[str] = []

    # 1. parse role + plain name
    d = parse_anchor("getByRole('button', { name: 'Create Group' })")
    if not (d["strategy"] == "role" and d["role"] == "button" and d["name"] == "Create Group"):
        errors.append(f"role parse wrong: {d}")

    # 2. parse text / placeholder / label
    if parse_anchor("getByText('Memberships')")["value"] != "Memberships":
        errors.append("text parse wrong")
    if parse_anchor("getByPlaceholder('Group Name')")["strategy"] != "placeholder":
        errors.append("placeholder parse wrong")
    if parse_anchor("getByLabel('Email')")["strategy"] != "label":
        errors.append("label parse wrong")

    # 3. role regex name → native routing
    dr = parse_anchor("getByRole('button', { name: /Create|Add/ })")
    if not needs_native(dr):
        errors.append("regex-name role should route native")
    if to_find_args(dr) != []:
        errors.append("regex-name role should yield no find args")

    # 4. find arg building — click
    args = to_find_args(parse_anchor("getByRole('button', { name: 'Create Group' })"), "click")
    if args != ["find", "role", "button", "click", "--name", shlex.quote("Create Group")]:
        errors.append(f"role click args wrong: {args}")
    targs = to_find_args(parse_anchor("getByText('Memberships')"), "click")
    if targs != ["find", "text", "Memberships", "click"]:
        errors.append(f"text click args wrong: {targs}")

    # 5. find arg building — fill (placeholder + role)
    fargs = to_find_args(parse_anchor("getByPlaceholder('Group Name')"), "fill", "Acme")
    if fargs != ["find", "placeholder", shlex.quote("Group Name"), "fill", "Acme"]:
        errors.append(f"placeholder fill args wrong: {fargs}")

    # 6. QUOTING round-trip proof — a multi-word --name survives browser_cmd + shlex.split
    joined = "agent-browser --headed false --session s " + " ".join(
        to_find_args(parse_anchor("getByRole('button', { name: 'Create Group' })"), "click"))
    if shlex.split(joined)[-2:] != ["--name", "Create Group"]:
        errors.append(f"quoting round-trip broke: {shlex.split(joined)[-3:]}")

    # 7. native click JS contains an .click() and the wanted label; regex form compiles a RegExp
    js = native_click_js(parse_anchor("getByRole('button', { name: 'Create Group' })"))
    if ".click()" not in js or "Create Group" not in js:
        errors.append("native_click_js missing click/label")
    if "new RegExp" not in native_click_js(dr):
        errors.append("native_click_js regex form missing RegExp")

    # 8. AbExecutor with a fake ab/eval — find success path, native-mode path, find-miss→native
    calls: List[tuple] = []

    def fake_ab(session, *args, timeout=15):
        calls.append(args)
        verb = args[0] if args else ""
        # simulate: `find role button click` succeeds; a `find placeholder` MISS
        if verb == "find" and len(args) > 1 and args[1] == "placeholder":
            return subprocess.CompletedProcess(args, 1, "", "Element not found")
        return subprocess.CompletedProcess(args, 0, "✓ Done", "")

    def fake_ev(session, js, timeout=15):
        return "CLICKED:Create Group" if ".click()" in js else "FILLED"

    ex = AbExecutor(ab=fake_ab, ev=fake_ev)
    r1 = ex.click("s", "getByRole('button', { name: 'Create Group' })")
    if not (r1["ok"] and r1["path"] == "find"):
        errors.append(f"executor find-click failed: {r1}")
    r2 = ex.click("s", "getByRole('button', { name: 'Create Group' })", mode="native")
    if not (r2["ok"] and r2["path"] == "native"):
        errors.append(f"executor native-click failed: {r2}")
    # placeholder click MISS in find → auto native fallback
    r3 = ex.click("s", "getByPlaceholder('Search')")
    if not (r3["ok"] and r3["path"] == "native"):
        errors.append(f"executor find-miss→native fallback failed: {r3}")
    # fill: placeholder find MISS → native reactive-set
    r4 = ex.fill("s", "getByPlaceholder('Group Name')", "Acme")
    if not (r4["ok"] and r4["path"] == "native"):
        errors.append(f"executor fill fallback failed: {r4}")
    # wait_text quotes a multi-word value
    ex.wait_text("s", "ZHC Founders Circle")
    if ("wait", "--", shlex.quote("ZHC Founders Circle")) not in calls:
        errors.append("wait_text did not quote the multi-word value")

    if errors:
        for e in errors:
            print(f"  FAIL: {e}", file=sys.stderr)
        print(f"\n[selftest] FAIL — {len(errors)} error(s)", file=sys.stderr)
        return 1
    print("[selftest] PASS — anchor parse + find-arg build + quoting round-trip + native "
          "click/fill + executor modes (no network / no browser)")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    import argparse
    p = argparse.ArgumentParser(
        prog="ghl_ab_executor",
        description="agent-browser 0.27.0 anchor→executor resolver (Skill 06). Offline.")
    p.add_argument("--selftest", action="store_true")
    p.add_argument("--parse", default="", help="Print the descriptor for a Playwright anchor")
    p.add_argument("--find", default="", help="Print the find argv for a Playwright anchor")
    args = p.parse_args(argv)
    if args.selftest:
        return _selftest()
    if args.parse:
        print(json.dumps(parse_anchor(args.parse), indent=2))
        return 0
    if args.find:
        print(json.dumps(to_find_args(parse_anchor(args.find)), indent=2))
        return 0
    p.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
