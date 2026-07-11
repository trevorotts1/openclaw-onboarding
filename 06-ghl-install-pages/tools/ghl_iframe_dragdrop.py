#!/usr/bin/env python3
"""ghl_iframe_dragdrop.py — reusable CROSS-ORIGIN-IFRAME drag/drop + ref-less-tab
playbook for Skill 06 (the generalized, IN-THE-SKILL version of the 2026-07-10
survey bring-up `synth_drag.js` one-off).

WHY THIS EXISTS
---------------
Several GHL builders (form, survey) render their canvas inside a CROSS-ORIGIN
iframe — `leadgen-apps-form-survey-builder.leadconnectorhq.com` mounted inside
`app.convertandflow.com`. Inside that frame:
  * only role=button chrome (Save/Preview/Integrate/Add Elements) gets an a11y ref;
  * panel TABS ("Quick Add", "Add Object Fields") are ref-less `StaticText` — a
    top-frame `click "<text>"` reports "Element not found";
  * quick-add / object-field TILES are ref-less `generic > image + StaticText`;
  * `document.querySelectorAll('[draggable=true]').length === 0` — the widget is a
    pointer-driven Sortable/Vue-draggable, NOT HTML5 DnD.

agent-browser 0.27.0 auto-inlines the builder iframe, so a `drag <srcText>
<dstText>` text-locator drag (rung 1) is the DEFAULT and is form-builder-proven.
This module is the ESCALATION LADDER when that walls: in-frame native `.click()`
for ref-less tabs (rung 2a) and an in-frame bounding-box POINTER drag (rung 2b),
both emitted as JS the builder runs through its own `eval` glue. It never opens a
browser or touches the network at import/selftest time — it only BUILDS the JS and
routes it through injected `ab`/`ev` callables (same dependency-injection shape as
`ghl_ab_executor.AbExecutor`), so a builder's test monkeypatch is honored.

Full technique ladder + detection + pitfalls: see
`TECHNIQUES-cross-origin-iframe-dragdrop.md` at the skill root.
"""
from __future__ import annotations

import json
from typing import Any, Callable, Dict, Optional

PINNED_AGENT_BROWSER = "0.27.0"

# The GHL builder canvas iframe host (form + survey share it).
BUILDER_IFRAME_HOST = "leadgen-apps-form-survey-builder.leadconnectorhq.com"


# ---------------------------------------------------------------------------
# JS EMITTERS (pure — no browser, no network; unit-testable by shape)
# ---------------------------------------------------------------------------

def detect_js() -> str:
    """JS that reports whether the current (inlined) frame is a ref-less,
    pointer-driven drag widget. Returns a JSON string
    ``{draggable, tiles, cross_origin_iframe, sortable_style}`` — the DETECTION
    signature from the playbook (draggable==0 → pointer/Sortable path, not HTML5)."""
    return (
        "(() => {"
        "  const draggable = document.querySelectorAll('[draggable=true]').length;"
        "  const iframes = [...document.querySelectorAll('iframe')]"
        "    .map(f => f.src || f.getAttribute('src') || '')"
        f"    .filter(s => s.includes({json.dumps(BUILDER_IFRAME_HOST)}));"
        "  return JSON.stringify({"
        "    draggable,"
        "    cross_origin_iframe: iframes.length > 0,"
        "    sortable_style: draggable === 0"
        "  });"
        "})()"
    )


def tab_click_js(tab_text: str) -> str:
    """JS for a native ``.click()`` of a REF-LESS panel tab (StaticText) by its
    visible text — the rung-2a move for "Quick Add" / "Add Object Fields".

    Finds the DEEPEST element whose ``textContent.trim() === tab_text`` (a leaf
    text node, not a wrapping container), climbs to its nearest clickable ancestor
    (``div``/``button``/``[role]``), scrolls it into view, and dispatches a native
    ``el.click()``. Returns ``'CLICKED:<text>'`` or ``'NOTFOUND'`` — never throws."""
    want = json.dumps(tab_text)
    return (
        "(() => {"
        "  const want = " + want + ";"
        "  const norm = s => (s || '').replace(/\\s+/g, ' ').trim();"
        "  const leaves = [...document.querySelectorAll('*')].filter("
        "    e => e.children.length === 0 && norm(e.textContent) === want);"
        "  const leaf = leaves[0];"
        "  if (!leaf) return 'NOTFOUND';"
        "  const el = leaf.closest('button,[role=button],[role=tab],div,a,li') || leaf;"
        "  if (el.scrollIntoView) el.scrollIntoView({ block: 'center' });"
        "  el.click();"
        "  return 'CLICKED:' + norm(el.textContent).slice(0, 40);"
        "})()"
    )


# The default post-drop success probe: how many element rows the canvas holds.
# A drag that lands increments this. Callers with access to the widget's own store
# (e.g. survey Pinia `state.app.slides[0].slideData.length`) can pass a more precise
# ``verify_expr`` to `coord_drag_js`.
_DEFAULT_VERIFY_EXPR = (
    "(document.querySelector('form') "
    "? document.querySelector('form').querySelectorAll("
    "'[data-field],[data-element],.field,.form-field,input,textarea,select').length "
    ": 0)"
)


def coord_drag_js(
    tile_text: str,
    target_text: str,
    *,
    verify_expr: Optional[str] = None,
) -> str:
    """JS for an IN-FRAME bounding-box POINTER drag (rung 2b) — the generalized,
    parameterized port of the survey bring-up `synth_drag.js`.

    Locates the TILE leaf (``textContent === tile_text``) and the TARGET leaf
    (``target_text`` — a slide label / drop-zone caption), computes their rects,
    and dispatches an interpolated ``pointerdown → N×pointermove → pointerup``
    sequence (with a trailing HTML5 ``dragstart/dragover/drop`` fallback for
    widgets that still listen for it). Success = ``after > before`` where before/
    after evaluate ``verify_expr`` (default: canvas field-row count). Returns a
    JSON string ``{ok, before, after, err?}`` — never throws.

    ``verify_expr`` MUST be a JS EXPRESSION (not statements) returning a number."""
    tile_j = json.dumps(tile_text)
    tgt_j = json.dumps(target_text)
    ve = verify_expr or _DEFAULT_VERIFY_EXPR
    return (
        "(async () => {"
        "  const norm = s => (s || '').replace(/\\s+/g, ' ').trim();"
        "  const tileWant = " + tile_j + ";"
        "  const tgtWant = " + tgt_j + ";"
        "  const verify = () => { try { return (" + ve + "); } catch (e) { return -1; } };"
        "  const leafOf = w => [...document.querySelectorAll('*')].find("
        "    e => e.children.length === 0 && norm(e.textContent) === w);"
        "  const tileLeaf = leafOf(tileWant);"
        "  if (!tileLeaf) return JSON.stringify({ ok: false, err: 'no-tile' });"
        "  const tile = tileLeaf.closest('div,button,li') || tileLeaf;"
        "  const tgtLeaf = leafOf(tgtWant);"
        "  const canvas = (tgtLeaf && (tgtLeaf.closest('form,section,div') || tgtLeaf))"
        "    || document.querySelector('form') || document.body;"
        "  if (tile.scrollIntoView) tile.scrollIntoView({ block: 'center' });"
        "  await new Promise(r => setTimeout(r, 250));"
        "  const tb = tile.getBoundingClientRect();"
        "  const cb = canvas.getBoundingClientRect();"
        "  const sx = tb.left + tb.width / 2, sy = tb.top + tb.height / 2;"
        "  const dx = cb.left + cb.width / 2, dy = cb.top + 80;"
        "  const before = verify();"
        "  const dt = new DataTransfer();"
        "  const mk = (type, x, y) => {"
        "    const C = type.startsWith('pointer') ? PointerEvent"
        "      : type.startsWith('drag') ? DragEvent : MouseEvent;"
        "    const init = { bubbles: true, cancelable: true, composed: true,"
        "      clientX: x, clientY: y, button: 0, buttons: 1, view: window,"
        "      pointerId: 1, pointerType: 'mouse', isPrimary: true };"
        "    if (type.startsWith('drag')) init.dataTransfer = dt;"
        "    return new C(type, init);"
        "  };"
        "  const at = (x, y) => document.elementFromPoint(x, y) || canvas;"
        "  tile.dispatchEvent(mk('pointerdown', sx, sy));"
        "  tile.dispatchEvent(mk('mousedown', sx, sy));"
        "  const path = [[sx + 8, sy], [sx + 40, sy - 5],"
        "    [(sx + dx) / 2, (sy + dy) / 2], [dx, dy], [dx + 1, dy]];"
        "  for (const [x, y] of path) {"
        "    const el = at(x, y);"
        "    el.dispatchEvent(mk('pointermove', x, y));"
        "    el.dispatchEvent(mk('mousemove', x, y));"
        "    await new Promise(r => setTimeout(r, 60));"
        "  }"
        "  tile.dispatchEvent(mk('dragstart', sx, sy));"
        "  canvas.dispatchEvent(mk('dragenter', dx, dy));"
        "  canvas.dispatchEvent(mk('dragover', dx, dy));"
        "  canvas.dispatchEvent(mk('drop', dx, dy));"
        "  const de = at(dx, dy);"
        "  de.dispatchEvent(mk('pointerup', dx, dy));"
        "  de.dispatchEvent(mk('mouseup', dx, dy));"
        "  tile.dispatchEvent(mk('dragend', dx, dy));"
        "  await new Promise(r => setTimeout(r, 900));"
        "  const after = verify();"
        "  return JSON.stringify({ ok: after > before, before, after });"
        "})()"
    )


# ---------------------------------------------------------------------------
# Orchestrator — routes the ladder through injected ab / ev callables
# ---------------------------------------------------------------------------

def _parse_drag_result(raw: Any) -> Dict[str, Any]:
    """Parse the JSON string returned by `coord_drag_js` into a dict; tolerate a
    non-JSON / empty eval result (returns ok=False rather than raising)."""
    s = (raw or "").strip().strip('"').strip("'") if isinstance(raw, str) else ""
    if not s:
        return {"ok": False, "err": "no-response", "before": None, "after": None}
    try:
        d = json.loads(s)
        if isinstance(d, dict):
            d.setdefault("ok", False)
            return d
    except (ValueError, TypeError):
        pass
    return {"ok": False, "err": "unparseable", "raw": s, "before": None, "after": None}


class IframeDragDrop:
    """Drive a cross-origin-iframe drag widget through the technique ladder.

    Dependency-injected exactly like `ghl_ab_executor.AbExecutor`:
      ab(session, *args, timeout=…) -> CompletedProcess-like   (agent-browser)
      ev(session, js, timeout=…)    -> str                     (eval stdout)
    So a builder passes its own `_run_cmd`/`_eval` and tests inject fakes."""

    def __init__(self, ab: Optional[Callable] = None, ev: Optional[Callable] = None,
                 log: Optional[Callable[[str], None]] = None):
        self._ab = ab
        self._ev = ev
        self._log = log or (lambda m: None)

    def _ab_ok(self, cp: Any) -> bool:
        import re
        if cp is None:
            return False
        rc = getattr(cp, "returncode", 1)
        out = ((getattr(cp, "stdout", "") or "") + " "
               + (getattr(cp, "stderr", "") or "")).lower()
        if rc != 0:
            return False
        return not re.search(r"not found|no element|no matching|timed? ?out|error:", out)

    # -- rung 2a: ref-less tab -------------------------------------------------
    def tab_click(self, session: str, tab_text: str, *, timeout: int = 15) -> Dict[str, Any]:
        """Native `.click()` a ref-less panel tab by text. auto: try agent-browser's
        own `find text … click` first (it may resolve), then native fallback."""
        args = ["find", "text", tab_text, "click"]
        cp = self._ab(session, *args, timeout=timeout) if self._ab else None
        if self._ab_ok(cp):
            return {"ok": True, "path": "find", "detail": tab_text}
        res = (self._ev(session, tab_click_js(tab_text), timeout=timeout) or "").strip() \
            if self._ev else ""
        return {"ok": res.startswith("CLICKED"), "path": "native", "detail": res}

    # -- rung 1 + rung 2b: the drag ladder ------------------------------------
    def text_locator_drag(self, session: str, tile_text: str, target_text: str,
                          *, timeout: int = 20) -> Dict[str, Any]:
        """Rung 1: agent-browser text-locator drag across the auto-inlined frame
        (form-builder-proven)."""
        cp = self._ab(session, "drag", tile_text, target_text, timeout=timeout) \
            if self._ab else None
        return {"ok": self._ab_ok(cp), "path": "text-drag"}

    def coord_drag(self, session: str, tile_text: str, target_text: str, *,
                   verify_expr: Optional[str] = None, timeout: int = 30) -> Dict[str, Any]:
        """Rung 2b: in-frame bounding-box pointer drag; success = store/DOM delta."""
        raw = self._ev(session, coord_drag_js(tile_text, target_text, verify_expr=verify_expr),
                       timeout=timeout) if self._ev else ""
        d = _parse_drag_result(raw)
        d["path"] = "coord-drag"
        return d

    def drag(self, session: str, tile_text: str, target_text: str, *,
             verify_expr: Optional[str] = None, timeout: int = 30) -> Dict[str, Any]:
        """Full ladder: rung 1 (text-locator drag) → rung 2b (coord drag) on miss.
        Rung 1's success can't always be proven by the CLI's "✓ Done" alone, so when
        a ``verify_expr`` is supplied the delta is the arbiter across both rungs."""
        r1 = self.text_locator_drag(session, tile_text, target_text, timeout=timeout)
        if r1.get("ok") and verify_expr is None:
            return r1
        # Prove (or escalate) with the in-frame delta.
        r2 = self.coord_drag(session, tile_text, target_text,
                             verify_expr=verify_expr, timeout=timeout)
        if r2.get("ok"):
            r2["escalated_from"] = "text-drag"
            return r2
        self._log(f"iframe drag walled for {tile_text!r} → {target_text!r}: {r2}")
        return r2


# ---------------------------------------------------------------------------
# CLI / selftest — fully offline (no network, no browser)
# ---------------------------------------------------------------------------

def _selftest() -> int:  # noqa: C901
    import subprocess
    errors = []

    # 1. detect_js shape
    dj = detect_js()
    if "draggable" not in dj or "sortable_style" not in dj or BUILDER_IFRAME_HOST not in dj:
        errors.append("detect_js missing keys/host")

    # 2. tab_click_js contains a native .click() and the wanted text, no throw
    tj = tab_click_js("Add Object Fields")
    if ".click()" not in tj or "Add Object Fields" not in tj or "NOTFOUND" not in tj:
        errors.append("tab_click_js malformed")

    # 3. coord_drag_js: pointer sequence + before/after delta + parameterized texts
    cj = coord_drag_js("Multi Line", "Slide 2")
    for needle in ("pointerdown", "pointermove", "pointerup", "before", "after",
                   "Multi Line", "Slide 2", "DataTransfer"):
        if needle not in cj:
            errors.append(f"coord_drag_js missing {needle!r}")

    # 4. coord_drag_js honors a custom verify_expr (store-length probe)
    cj2 = coord_drag_js("Radio", "Slide 3",
                        verify_expr="window.__store.slides[0].slideData.length")
    if "window.__store.slides[0].slideData.length" not in cj2:
        errors.append("coord_drag_js did not inline custom verify_expr")

    # 5. _parse_drag_result tolerance
    if _parse_drag_result('{"ok":true,"before":0,"after":1}')["ok"] is not True:
        errors.append("_parse_drag_result true-case failed")
    if _parse_drag_result("")["ok"] is not False:
        errors.append("_parse_drag_result empty should be ok=False")
    if _parse_drag_result("garbage")["ok"] is not False:
        errors.append("_parse_drag_result garbage should be ok=False")

    # 6. IframeDragDrop with fake ab/ev — tab find success, native fallback, drag delta
    calls = []

    def fake_ab(session, *args, timeout=15):
        calls.append(args)
        if args and args[0] == "find" and args[1] == "text" and args[2] == "MISS":
            return subprocess.CompletedProcess(args, 1, "", "Element not found")
        if args and args[0] == "drag":
            # simulate a text-drag that the CLI reports done but did NOT land
            return subprocess.CompletedProcess(args, 0, "✓ Done", "")
        return subprocess.CompletedProcess(args, 0, "✓ Done", "")

    def fake_ev(session, js, timeout=15):
        if "NOTFOUND" in js and ".click()" in js:      # tab_click_js
            return "CLICKED:Add Object Fields"
        if "pointerdown" in js:                          # coord_drag_js
            return '{"ok":true,"before":0,"after":1}'
        return ""

    idd = IframeDragDrop(ab=fake_ab, ev=fake_ev)
    if not idd.tab_click("s", "Add Object Fields")["ok"]:
        errors.append("tab_click find-success failed")
    r_miss = idd.tab_click("s", "MISS")
    if not (r_miss["ok"] and r_miss["path"] == "native"):
        errors.append("tab_click native fallback failed")
    # drag ladder: rung1 "done" but with verify_expr the delta arbitrates → coord drag
    rd = idd.drag("s", "Multi Line", "Slide 2",
                  verify_expr="s.slides[0].slideData.length")
    if not (rd["ok"] and rd["path"] == "coord-drag"):
        errors.append(f"drag ladder should prove via coord-drag delta: {rd}")

    # 7. a genuinely walled drag (coord delta 0) reports ok=False, not a false pass
    def fake_ev_wall(session, js, timeout=15):
        if "pointerdown" in js:
            return '{"ok":false,"before":0,"after":0}'
        return ""
    idd_wall = IframeDragDrop(ab=fake_ab, ev=fake_ev_wall)
    rw = idd_wall.drag("s", "Multi Line", "Slide 2", verify_expr="x")
    if rw.get("ok"):
        errors.append("walled drag must report ok=False (no false pass)")

    if errors:
        for e in errors:
            print(f"  FAIL: {e}")
        print(f"\n[selftest] FAIL — {len(errors)} error(s)")
        return 1
    print("[selftest] PASS — detect/tab-click/coord-drag JS emitters + ladder "
          "orchestration + wall honesty (no network / no browser)")
    return 0


def main(argv=None) -> int:
    import argparse
    p = argparse.ArgumentParser(
        prog="ghl_iframe_dragdrop",
        description="Cross-origin-iframe drag/drop + ref-less-tab playbook (Skill 06). Offline.")
    p.add_argument("--selftest", action="store_true")
    p.add_argument("--emit", choices=("detect", "tab", "coord"), help="Print a JS emitter")
    p.add_argument("--tile", default="Multi Line")
    p.add_argument("--target", default="Slide 2")
    args = p.parse_args(argv)
    if args.selftest:
        return _selftest()
    if args.emit == "detect":
        print(detect_js())
    elif args.emit == "tab":
        print(tab_click_js(args.target))
    elif args.emit == "coord":
        print(coord_drag_js(args.tile, args.target))
    else:
        p.print_help()
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
