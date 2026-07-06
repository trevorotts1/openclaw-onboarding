#!/usr/bin/env python3
"""render_documents.py - Podcast Production Engine, Step 12 (DOCUMENTS).

Two deliverables per episode:
  1. Episode Package - rich and fully rendered, with NO font below 12 point.
  2. Speech Script  - clean text only.

Destination is detected in priority order: Google first, then Notion, then
plain text as the last resort. Detection is by tooling and credential PRESENCE
only; this script reports SET or NOT SET and never prints a secret value.

This renderer is deterministic and pure standard library. It calls NO model, NO
MCP tool, and NO external API. It renders the two artifacts to disk and emits a
machine-readable destination action plan. The podcast agent then executes that
plan in its OWN turn using the client's own Google (gws) or Notion (REST)
credentials, keeping the pipeline MCP-free (sub-agents get no MCP injection) and
keeping this step fully testable in isolation.

Google sharing rule (Google destination only): anyone with the link can edit,
expressed as Drive permission role=writer, type=anyone. Notion has no identical
concept; its plan carries a share-to-web note instead.

Doctrine honored: silence (operator and agent output only, never a client
message), secrecy (labels and SET or NOT SET only, never a value), no content
model call anywhere in this file, zero em dash characters, and no triple
backtick fences in any produced output.

Subcommands:
  render        --manifest <json> --out-dir <dir> [--force-destination X]
                [--speech-script-file <f>]
  detect        [--json]
  check         --package <html.file>         (font-floor 12pt self-check)
  check-script  --script <txt.file>           (clean-text sanity guard)

Exit codes: 0 ok; 2 bad arguments or input; 3 render or validation failure.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

FONT_FLOOR_PT = 12
TITLE_FONT_PT = 26
SECTION_FONT_PT = 18
BODY_FONT_PT = 14
META_FONT_PT = 12  # smallest element used; equals the floor, never below it


def eprint(*args: object) -> None:
    print(*args, file=sys.stderr)


def slugify(text: str) -> str:
    text = (text or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = text.strip("-")
    return text[:80] or "podcast"


# ---------------------------------------------------------------------------
# Destination detection (presence only; never a value)
# ---------------------------------------------------------------------------

def _env_set(name: str) -> bool:
    return bool(os.environ.get(name, "").strip())


def detect_destination() -> dict:
    """Return a detection report and the chosen destination.

    Google wins when the gws CLI is present OR a Google Workspace signal is set.
    Notion wins when a Notion token AND a parent page are both set.
    Otherwise plain text (local) is the last resort. Values are never read;
    only presence (SET or NOT SET) is reported.
    """
    gws_on_path = shutil.which("gws") is not None
    google_env = [n for n in (
        "GOOGLE_WORKSPACE_ENABLED", "GWS_ACCOUNT",
        "GOOGLE_APPLICATION_CREDENTIALS", "GOOGLE_WORKSPACE_TOKEN",
    ) if _env_set(n)]
    google_ok = gws_on_path or bool(google_env)

    notion_token = next((n for n in ("NOTION_API_KEY", "NOTION_TOKEN") if _env_set(n)), None)
    notion_parent = next((n for n in ("NOTION_PARENT_PAGE_ID", "NOTION_PODCAST_PARENT") if _env_set(n)), None)
    notion_ok = bool(notion_token) and bool(notion_parent)

    if google_ok:
        chosen = "google"
    elif notion_ok:
        chosen = "notion"
    else:
        chosen = "local"

    return {
        "chosen": chosen,
        "google": {
            "available": google_ok,
            "gws_cli": "SET" if gws_on_path else "NOT SET",
            "env_signals": {n: "SET" for n in google_env} or {"GOOGLE_WORKSPACE": "NOT SET"},
        },
        "notion": {
            "available": notion_ok,
            "token": ("SET (%s)" % notion_token) if notion_token else "NOT SET",
            "parent_page": ("SET (%s)" % notion_parent) if notion_parent else "NOT SET",
        },
        "local": {"available": True, "note": "plain-text last resort is always available"},
    }


# ---------------------------------------------------------------------------
# Manifest loading
# ---------------------------------------------------------------------------

def load_manifest(path: str, speech_file: str | None) -> dict:
    p = Path(path)
    if not p.is_file():
        raise ValueError("manifest not found: %s" % path)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("manifest is not valid JSON: %s" % exc) from exc
    if not isinstance(data, dict):
        raise ValueError("manifest must be a JSON object")

    if not str(data.get("title", "")).strip():
        raise ValueError("manifest.title is required")

    # Resolve the speech script from a file override, an inline field, or a
    # path field. The Speech Script must exist; it is a required deliverable.
    script = ""
    if speech_file:
        sf = Path(speech_file)
        if not sf.is_file():
            raise ValueError("speech script file not found: %s" % speech_file)
        script = sf.read_text(encoding="utf-8")
    elif isinstance(data.get("speech_script"), str) and data["speech_script"].strip():
        script = data["speech_script"]
    elif str(data.get("speech_script_file", "")).strip():
        sf = Path(data["speech_script_file"])
        if not sf.is_file():
            raise ValueError("manifest.speech_script_file not found: %s" % data["speech_script_file"])
        script = sf.read_text(encoding="utf-8")
    else:
        raise ValueError("no speech script supplied (speech_script, speech_script_file, or --speech-script-file)")

    data["_speech_script_text"] = script.strip("\n")
    return data


# ---------------------------------------------------------------------------
# Episode Package HTML renderer (font floor 12pt, enforced by construction)
# ---------------------------------------------------------------------------

def _esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def _multiline(value: str) -> str:
    return "<br>".join(_esc(line) for line in str(value).split("\n"))


def render_package_html(m: dict) -> str:
    title = _esc(m.get("title"))
    client = m.get("client", "")
    style = m.get("style", "")
    mode = m.get("mode", "")
    guest = m.get("guest_first_name", "")
    thesis = m.get("thesis", "")
    description = m.get("description", "")
    runtime = m.get("runtime_minutes")
    word_count = m.get("word_count")
    research = m.get("research") or {}
    cover_path = m.get("cover_path", "")
    podbean_url = m.get("podbean_url", "")

    meta_bits = []
    if style:
        meta_bits.append("Style: %s" % _esc(style))
    if mode:
        meta_bits.append("Mode: %s" % _esc(mode))
    if guest:
        meta_bits.append("Guest: %s" % _esc(guest))
    if runtime is not None:
        meta_bits.append("Runtime: %s minutes" % _esc(runtime))
    if word_count is not None:
        meta_bits.append("Spoken words: %s" % _esc(word_count))
    meta_line = " &middot; ".join(meta_bits)

    def section(heading: str, inner: str) -> str:
        if not inner:
            return ""
        return "  <section>\n    <h2>%s</h2>\n%s\n  </section>\n" % (_esc(heading), inner)

    def list_block(items: list) -> str:
        rows = "".join("      <li>%s</li>\n" % _multiline(i) for i in items if str(i).strip())
        return "    <ul>\n%s    </ul>" % rows if rows else ""

    body_parts: list[str] = []
    if thesis:
        body_parts.append(section("Thesis", "    <p>%s</p>" % _multiline(thesis)))
    if description:
        body_parts.append(section("Show notes", "    <p>%s</p>" % _multiline(description)))

    takeaways = research.get("key_takeaways") or []
    if takeaways:
        body_parts.append(section("Key takeaways", list_block(takeaways)))

    statements = research.get("power_statements") or []
    if statements:
        quotes = "".join(
            "    <blockquote>%s</blockquote>\n" % _multiline(s) for s in statements if str(s).strip()
        )
        body_parts.append(section("Power statements", quotes.rstrip("\n")))

    studies = research.get("case_studies") or []
    if studies:
        rows = []
        for s in studies:
            if isinstance(s, dict):
                st = _esc(s.get("title", "Case study"))
                sm = _multiline(s.get("summary", ""))
                src = s.get("source", "")
                src_html = ""
                if src:
                    if str(src).startswith("http"):
                        src_html = '<div class="src">Source: <a href="%s">%s</a></div>' % (_esc(src), _esc(src))
                    else:
                        src_html = '<div class="src">Source: %s</div>' % _esc(src)
                rows.append("    <div class=\"study\">\n      <h3>%s</h3>\n      <p>%s</p>\n      %s\n    </div>" % (st, sm, src_html))
            else:
                rows.append("    <div class=\"study\"><p>%s</p></div>" % _multiline(s))
        body_parts.append(section("Case studies", "\n".join(rows)))

    findings = research.get("findings") or []
    if findings:
        body_parts.append(section("Supporting findings", list_block(findings)))

    sources = research.get("sources") or []
    if sources:
        rows = ""
        for s in sources:
            if str(s).startswith("http"):
                rows += '      <li><a href="%s">%s</a></li>\n' % (_esc(s), _esc(s))
            else:
                rows += "      <li>%s</li>\n" % _esc(s)
        body_parts.append(section("Sources", "    <ol>\n%s    </ol>" % rows))

    links_rows = ""
    if podbean_url:
        links_rows += '      <li>Episode: <a href="%s">%s</a></li>\n' % (_esc(podbean_url), _esc(podbean_url))
    if cover_path:
        links_rows += "      <li>Cover art file: %s</li>\n" % _esc(cover_path)
    if links_rows:
        body_parts.append(section("Assets", "    <ul>\n%s    </ul>" % links_rows))

    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    subtitle = _esc(client) if client else ""

    # Every font-size below is expressed in points and is at or above the 12pt
    # floor. The check subcommand re-verifies this on the produced file.
    css = "\n".join([
        "    :root { color-scheme: light dark; }",
        "    body { font-family: Georgia, 'Times New Roman', serif; font-size: %dpt; line-height: 1.55;" % BODY_FONT_PT,
        "      max-width: 46rem; margin: 2rem auto; padding: 0 1.25rem; color: #1a1a1a; background: #ffffff; }",
        "    h1 { font-size: %dpt; line-height: 1.2; margin: 0 0 0.25rem; }" % TITLE_FONT_PT,
        "    h2 { font-size: %dpt; margin: 1.6rem 0 0.5rem; border-bottom: 1px solid #ddd; padding-bottom: 0.2rem; }" % SECTION_FONT_PT,
        "    h3 { font-size: %dpt; margin: 1rem 0 0.3rem; }" % BODY_FONT_PT,
        "    p, li, blockquote { font-size: %dpt; }" % BODY_FONT_PT,
        "    .meta, .src, footer { font-size: %dpt; color: #555; }" % META_FONT_PT,
        "    blockquote { border-left: 3px solid #888; margin: 0.6rem 0; padding: 0.2rem 0 0.2rem 1rem; font-style: italic; }",
        "    .study { margin: 0.8rem 0 1.1rem; }",
        "    a { color: #0b5cad; }",
        "    footer { margin-top: 2.4rem; border-top: 1px solid #ddd; padding-top: 0.6rem; }",
        "    @media (prefers-color-scheme: dark) {",
        "      body { color: #ececec; background: #14161a; }",
        "      h2 { border-bottom-color: #333; } .meta, .src, footer { color: #b3b3b3; }",
        "      footer { border-top-color: #333; } a { color: #6db3ff; }",
        "    }",
    ])

    head = "\n".join([
        "<!doctype html>",
        '<html lang="en">',
        "<head>",
        '  <meta charset="utf-8">',
        '  <meta name="viewport" content="width=device-width, initial-scale=1">',
        "  <title>%s - Episode Package</title>" % title,
        "  <style>",
        css,
        "  </style>",
        "</head>",
        "<body>",
    ])

    header = "  <header>\n    <h1>%s</h1>\n" % title
    if subtitle:
        header += '    <div class="meta">%s</div>\n' % subtitle
    if meta_line:
        header += '    <div class="meta">%s</div>\n' % meta_line
    header += "  </header>\n"

    footer = (
        "  <footer>Episode Package rendered %s. The Speech Script is delivered as a "
        "separate clean-text file. Font floor: %dpt.</footer>\n" % (_esc(generated), FONT_FLOOR_PT)
    )

    return head + "\n" + header + "\n" + "".join(bp for bp in body_parts if bp) + "\n" + footer + "</body>\n</html>\n"


# ---------------------------------------------------------------------------
# Destination action plan
# ---------------------------------------------------------------------------

def build_plan(m: dict, detection: dict, destination: str, forced: bool,
               package_path: Path, speech_path: Path) -> dict:
    title = str(m.get("title"))
    ready = True
    actions: list[dict] = []
    sharing: dict = {}

    if destination == "google":
        ready = detection["google"]["available"]
        pkg_name = "%s - Episode Package" % title
        spk_name = "%s - Speech Script" % title
        actions = [
            {"action": "drive.upload_convert", "source": str(package_path),
             "mime_import": "text/html",
             "mime_target": "application/vnd.google-apps.document",
             "name": pkg_name, "capture": "package_doc_id",
             "cli_hint": "gws drive files upload (LIVE-VERIFY exact flags against the client gws CLI)"},
            {"action": "drive.upload_convert", "source": str(speech_path),
             "mime_import": "text/plain",
             "mime_target": "application/vnd.google-apps.document",
             "name": spk_name, "capture": "speech_doc_id",
             "cli_hint": "gws drive files upload (LIVE-VERIFY exact flags against the client gws CLI)"},
            {"action": "drive.set_permission", "target_ref": "package_doc_id",
             "role": "writer", "type": "anyone",
             "meaning": "anyone with the link can edit"},
            {"action": "drive.set_permission", "target_ref": "speech_doc_id",
             "role": "writer", "type": "anyone",
             "meaning": "anyone with the link can edit"},
            {"action": "capture_link", "from": "package_doc_id", "into": "links.package_doc"},
            {"action": "capture_link", "from": "speech_doc_id", "into": "links.speech_doc"},
        ]
        sharing = {"scope": "anyone", "role": "writer",
                   "human": "anyone with the link can edit"}

    elif destination == "notion":
        ready = detection["notion"]["available"]
        actions = [
            {"action": "notion.create_page", "parent": "NOTION_PARENT_PAGE_ID",
             "title": "%s - Episode Package" % title,
             "content_source": str(package_path), "capture": "package_page_url",
             "note": "render the package sections as Notion blocks via REST, never MCP"},
            {"action": "notion.create_page", "parent": "NOTION_PARENT_PAGE_ID",
             "title": "%s - Speech Script" % title,
             "content_source": str(speech_path), "capture": "speech_page_url",
             "note": "clean text only"},
            {"action": "capture_link", "from": "package_page_url", "into": "links.package_doc"},
            {"action": "capture_link", "from": "speech_page_url", "into": "links.speech_doc"},
        ]
        sharing = {"scope": "notion-share-to-web",
                   "note": "the anyone-with-the-link-can-edit rule is Google-specific; "
                           "for Notion, share per the client's Notion policy"}

    else:  # local
        actions = [{"action": "none",
                    "note": "plain-text last resort; the HTML package and the TXT speech "
                            "script on disk are the deliverables"}]
        sharing = {"scope": "local", "note": "no external sharing"}

    return {
        "step": 12,
        "destination": destination,
        "forced": forced,
        "ready": ready,
        "detection": detection,
        "artifacts": {
            "episode_package_html": str(package_path),
            "speech_script_txt": str(speech_path),
        },
        "font_floor_pt": FONT_FLOOR_PT,
        "data_plane": "agent-own-turn REST or gws; sub-agents get no MCP",
        "actions": actions,
        "sharing": sharing,
    }


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

_FONT_RE = re.compile(r"font-size\s*:\s*([0-9]*\.?[0-9]+)\s*(pt|px|em|rem|%)", re.IGNORECASE)


def check_font_floor(html_path: str) -> tuple[bool, list[str]]:
    p = Path(html_path)
    if not p.is_file():
        return False, ["package file not found: %s" % html_path]
    text = p.read_text(encoding="utf-8")
    problems: list[str] = []
    found = 0
    for value, unit in _FONT_RE.findall(text):
        found += 1
        v = float(value)
        unit = unit.lower()
        if unit == "pt":
            pt = v
        elif unit == "px":
            pt = v * 0.75  # 96px per inch, 72pt per inch
        else:
            problems.append("font-size %s%s uses a relative unit; use pt so the "
                            "12pt floor is verifiable" % (value, unit))
            continue
        if pt < FONT_FLOOR_PT:
            problems.append("font-size %s%s is below the %dpt floor" % (value, unit, FONT_FLOOR_PT))
    if found == 0:
        problems.append("no font-size declaration found; cannot prove the 12pt floor")
    return (len(problems) == 0), problems


def check_script_clean(txt_path: str) -> tuple[bool, list[str], list[str]]:
    p = Path(txt_path)
    if not p.is_file():
        return False, ["speech script file not found: %s" % txt_path], []
    text = p.read_text(encoding="utf-8")
    hard: list[str] = []
    warn: list[str] = []
    if not text.strip():
        hard.append("speech script is empty")
    if "\u2014" in text:
        hard.append("em dash character present (forbidden everywhere)")
    if "`" * 3 in text:
        hard.append("triple backtick fence present (forbidden in produced output)")
    if re.search(r"</?[a-zA-Z][^>]*>", text):
        hard.append("HTML tag present; the Speech Script must be clean text only")
    for i, line in enumerate(text.splitlines(), 1):
        if re.match(r"\s*#{1,6}\s", line):
            warn.append("line %d looks like a markdown heading" % i)
        elif re.match(r"\s*([*_]{1,2}\S|[-*+]\s|\d+\.\s)", line):
            warn.append("line %d looks like a markdown list or emphasis marker" % i)
    return (len(hard) == 0), hard, warn


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_render(args: argparse.Namespace) -> int:
    try:
        m = load_manifest(args.manifest, args.speech_script_file)
    except ValueError as exc:
        eprint("ERROR: %s" % exc)
        return 2

    detection = detect_destination()
    if args.force_destination:
        destination = args.force_destination
        forced = True
    else:
        destination = detection["chosen"]
        forced = False

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    slug = "%s-%s" % (slugify(m.get("client", "")), slugify(m.get("title", "")))
    slug = slug.strip("-") or "podcast-episode"

    package_path = (out_dir / ("%s-episode-package.html" % slug)).resolve()
    speech_path = (out_dir / ("%s-speech-script.txt" % slug)).resolve()
    plan_path = (out_dir / ("%s-documents-plan.json" % slug)).resolve()

    # Render + persist the two deliverables.
    package_html = render_package_html(m)
    package_path.write_text(package_html, encoding="utf-8")
    speech_path.write_text((m["_speech_script_text"] + "\n"), encoding="utf-8")

    # Self-verify before declaring success (fail-closed).
    font_ok, font_problems = check_font_floor(str(package_path))
    if not font_ok:
        eprint("ERROR: rendered package failed the %dpt font-floor check:" % FONT_FLOOR_PT)
        for pb in font_problems:
            eprint("  - %s" % pb)
        return 3
    script_ok, script_hard, script_warn = check_script_clean(str(speech_path))
    for w in script_warn:
        eprint("[render_documents][WARN] %s" % w)
    if not script_ok:
        eprint("ERROR: Speech Script failed the clean-text check:")
        for hp in script_hard:
            eprint("  - %s" % hp)
        return 3

    plan = build_plan(m, detection, destination, forced, package_path, speech_path)
    plan_path.write_text(json.dumps(plan, indent=2), encoding="utf-8")

    if forced and not plan["ready"]:
        eprint("[render_documents][WARN] destination forced to '%s' but its credentials "
               "are NOT SET; the agent must resolve them before executing the plan." % destination)

    print(json.dumps(plan, indent=2))
    return 0


def cmd_detect(args: argparse.Namespace) -> int:
    detection = detect_destination()
    if args.json:
        print(json.dumps(detection, indent=2))
    else:
        print("Chosen destination: %s" % detection["chosen"])
        print("  google: available=%s gws_cli=%s"
              % (detection["google"]["available"], detection["google"]["gws_cli"]))
        print("  notion: available=%s token=%s parent_page=%s"
              % (detection["notion"]["available"], detection["notion"]["token"],
                 detection["notion"]["parent_page"]))
        print("  local:  always available (plain-text last resort)")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    ok, problems = check_font_floor(args.package)
    if ok:
        print("PASS: every font-size in %s is at or above the %dpt floor" % (args.package, FONT_FLOOR_PT))
        return 0
    eprint("FAIL: font-floor check on %s" % args.package)
    for pb in problems:
        eprint("  - %s" % pb)
    return 3


def cmd_check_script(args: argparse.Namespace) -> int:
    ok, hard, warn = check_script_clean(args.script)
    for w in warn:
        eprint("[WARN] %s" % w)
    if ok:
        print("PASS: %s is clean text" % args.script)
        return 0
    eprint("FAIL: clean-text check on %s" % args.script)
    for hp in hard:
        eprint("  - %s" % hp)
    return 3


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="render_documents.py",
        description="Podcast Production Engine Step 12 document renderer and destination planner.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_render = sub.add_parser("render", help="render the Episode Package and Speech Script and emit a destination plan")
    p_render.add_argument("--manifest", required=True, help="path to the episode manifest JSON")
    p_render.add_argument("--out-dir", required=True, help="output directory for the artifacts")
    p_render.add_argument("--force-destination", choices=["google", "notion", "local"],
                          help="override destination detection")
    p_render.add_argument("--speech-script-file", help="path to the clean speech script text file")
    p_render.set_defaults(func=cmd_render)

    p_detect = sub.add_parser("detect", help="report destination detection only")
    p_detect.add_argument("--json", action="store_true", help="emit JSON")
    p_detect.set_defaults(func=cmd_detect)

    p_check = sub.add_parser("check", help="verify the 12pt font floor on a package HTML file")
    p_check.add_argument("--package", required=True, help="path to the episode package HTML")
    p_check.set_defaults(func=cmd_check)

    p_cs = sub.add_parser("check-script", help="verify a speech script is clean text")
    p_cs.add_argument("--script", required=True, help="path to the speech script text file")
    p_cs.set_defaults(func=cmd_check_script)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
