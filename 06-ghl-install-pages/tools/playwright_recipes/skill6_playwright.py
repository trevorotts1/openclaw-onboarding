#!/usr/bin/env python3
"""Deterministic GHL editor recipes. No LLM calls, login, publishing, or payments.

Run --check before --execute. OpenClaw supplies its already authenticated,
tenant-isolated Playwright Page to run_on_page(), or a managed loopback CDP URL
to the CLI. This module never starts unmanaged Chrome or extracts auth state.
Live control paths were exercised via the connected browser on 2026-11-08;
the complete Python runner still needs a managed-host integration run.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
from urllib.parse import urlparse
from html.parser import HTMLParser

# Nested recipe folder shares Skill 6's existing auth, renderer and lifecycle.
_TOOLS_DIR = Path(__file__).resolve().parent.parent
if (_TOOLS_DIR / 'browser_manager.py').exists() and str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))


class Stop(RuntimeError):
    pass


class EmbedSources(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls=[]
    def handle_starttag(self,tag,attrs):
        if tag in ('iframe','script'):
            source=dict(attrs).get('src')
            if source:
                self.urls.append(source)


def sha(value):
    return hashlib.sha256(value.encode()).hexdigest()


def zhc(name):
    if not isinstance(name, str) or not name.strip():
        raise Stop("A nonempty object name is required")
    return name.strip() if re.match(r"(?i)^zhc\b", name.strip()) else "ZHC " + name.strip()


def read_fragment(path):
    html = Path(path).read_text()
    if not html.strip():
        raise Stop("HTML fragment is empty")
    if re.search(r"<!doctype|<\s*(html|head|body)\b", html, re.I):
        try:
            from ghl_rest_canvas import html_fragment
            html = html_fragment(html, base_dir=Path(path).resolve().parent)
        except ImportError:
            raise Stop("Full-document import needs Skill 6's existing ghl_rest_canvas module") from None
    if re.search(r"(?:cc-number|cc-csc|cc-exp|cardnumber|cvv|\bcvc\b)", html, re.I):
        raise Stop("Card collection belongs in the native GHL order form")
    return html


def validate_job(job, base):
    if not isinstance(job,dict):
        raise Stop('Job must be a JSON object')
    if job.get("publish"):
        raise Stop("This runner only saves drafts; publishing stays with the existing approval gate")
    loc = job.get("location_id", "")
    if not isinstance(loc,str) or not re.fullmatch(r"[A-Za-z0-9_-]+", loc):
        raise Stop("location_id is required")
    if not isinstance(job.get('start_url'),str) or not isinstance(job.get('location_name'),str):
        raise Stop('start_url and location_name must be strings')
    u = urlparse(job.get("start_url", ""))
    if u.scheme != "https" or u.username or u.password or u.query or u.fragment:
        raise Stop("start_url must be an exact HTTPS app URL without query, fragment, or credentials")
    if not re.search(r"/(?:v2/)?location/" + re.escape(loc) + r"(?:/|$)", u.path):
        raise Stop("start_url must belong to location_id")
    if not job.get("location_name"):
        raise Stop("location_name is required for the visible account check")
    steps = job.get("steps", [])
    if not isinstance(steps,list) or not steps:
        raise Stop("No executable steps")
    keys = set()
    allowed = {"navigate", "container", "page", "html", "seo", "checkout", "form", "form_css", "community", "assessment", "meeting", "options"}
    prepared = json.loads(json.dumps(job))
    for s in prepared["steps"]:
        if not isinstance(s,dict):
            raise Stop('Every step must be a JSON object')
        if not isinstance(s.get('id'),str) or not re.fullmatch(r"[a-z0-9_-]+", s['id']) or s['id'] in keys:
            raise Stop("Every step requires a unique simple id")
        keys.add(s["id"])
        if not isinstance(s.get('action'),str) or s.get("action") not in allowed:
            raise Stop("Unknown or uncaptured action: " + str(s.get("action")))
        if s["action"] == "navigate" and s.get("area") not in ("Funnels", "Websites", "Forms", "Surveys", "Quizzes", "Communities", "Meeting Room", "Courses"):
            raise Stop("Unsupported navigation area")
        if s["action"] in ("container", "page") and s.get("surface") not in ("funnel", "website"):
            raise Stop("surface must be funnel or website")
        if s["action"] in ("container", "page", "form", "community"):
            s["name"] = zhc(s.get("name"))
        if s["action"] == "page" and (not isinstance(s.get('path'),str) or not re.fullmatch(r"/[A-Za-z0-9/_-]+", s.get("path", ""))):
            raise Stop("A page path beginning with / is required")
        if s["action"] == "html":
            if not isinstance(s.get('file'),str) or not isinstance(s.get('marker'),str):
                raise Stop('HTML file and visible marker must be strings')
            p = (base / s["file"]).resolve()
            s["html"] = read_fragment(p)
            if not s.get("marker") or s["marker"] not in s["html"]:
                raise Stop("A visible verification marker must appear in the HTML")
            s["html_sha256"] = sha(s["html"])
            if 'embed_receipt' in s:
                receipt=s['embed_receipt']
                sources=EmbedSources();sources.feed(s['html'])
                if not isinstance(receipt,dict) or receipt.get('status')!='PASS' or receipt.get('location_id')!=loc or receipt.get('html_sha256')!=s['html_sha256'] or not receipt.get('source'):
                    raise Stop('Embed PASS receipt must bind this location and the normalized HTML hash')
                if not sources.urls or set(sources.urls)!=set(receipt.get('embed_urls',[])):
                    raise Stop('Embed PASS receipt must match the actual iframe/script source URLs')
        if s["action"] == "seo":
            if not isinstance(s.get('keywords'),list) or not all(isinstance(k,str) and k.strip() for k in s['keywords']):
                raise Stop('SEO keywords must be a list of nonempty strings')
            if not all(isinstance(s.get(k),str) for k in ('title','description','author','canonical','page_copy')):
                raise Stop('SEO text values must be strings')
            for k in ("title", "description", "author", "canonical", "keywords", "page_copy"):
                if not s.get(k):
                    raise Stop("Missing SEO input: " + k)
            if len(s["title"]) > 70 or len(s["description"]) > 155:
                raise Stop("SEO title/description exceed 70/155 characters")
            cu = urlparse(s["canonical"])
            if cu.scheme != "https" or not cu.hostname or cu.username or cu.password:
                raise Stop("Canonical must be an absolute HTTPS URL")
            if s.get("canonical_host") != cu.hostname:
                raise Stop("canonical_host must explicitly match the intended page host")
            if len(set(k.casefold() for k in s["keywords"])) < 3:
                raise Stop("Three distinct researched keywords are required")
            if any(k.casefold() not in s["page_copy"].casefold() for k in s["keywords"]):
                raise Stop("Every keyword must appear in approved visible page copy")
            if not s.get("author_source") or not s.get("keyword_source"):
                raise Stop("Provide founder-name and keyword research sources")
        if s["action"] == "checkout":
            if s.get("mode", "One-step") not in ("One-step", "Two-step", "Split"):
                raise Stop("Unsupported checkout mode")
            if s.get("product") or s.get("charge") or s.get("one_click_upsell"):
                raise Stop("Product binding/one-click purchase behavior needs the Skill 44/79 contract; not captured here")
        if s["action"] == "form":
            if not isinstance(s.get('required',{}),dict) or any(type(v) is not bool for v in s.get('required',{}).values()):
                raise Stop('Required field options must be a mapping of real booleans')
            if any(k not in ("First Name", "Last Name", "Phone", "Email") for k in s.get("required", {})):
                raise Stop("Custom fields use the existing Skill 6 builder after Skill 44 creates dependencies")
        if s["action"] == "assessment":
            s["name"] = zhc(s.get("name"))
            if s.get("kind") not in ("survey", "quiz"):
                raise Stop("assessment kind must be survey or quiz")
            if not isinstance(s.get('standard_fields',[]),list) or any(q not in ("Email", "First Name", "Last Name", "Full Name", "Phone") for q in s.get("standard_fields", [])):
                raise Stop("Use options with a captured Add Object Fields recipe and Skill 44 dependency receipt for custom questions")
        if s["action"] == "form_css":
            if type(s.get("radius", 12)) is not int or not 0 <= s.get("radius",12) <= 32:
                raise Stop("Form corner radius must be 0–32 px")
        if s["action"] == "meeting":
            if not isinstance(s.get('name'),str) or not s['name'].strip() or not isinstance(s.get('slug'),str) or not re.fullmatch(r"[a-z0-9-]+",s.get("slug", "")):
                raise Stop("Room name and slug are required")
            if not isinstance(s.get("waiting_room"),bool) or not isinstance(s.get("guest_users"),bool) or not isinstance(s.get("open_room"),bool):
                raise Stop("Specify all three room security choices during intake")
            if s.get("cohosts"):
                raise Stop("Co-host picker needs captured identity resolution; use options after resolving users")
        if s["action"] == "options":
            if not isinstance(s.get('capture_source'),str) or not s['capture_source'] or not isinstance(s.get('steps'),list) or not s['steps']:
                raise Stop("Options require a recorded selector source and nonempty steps")
            for option in s["steps"]:
                if not isinstance(option,dict):
                    raise Stop('Recorded options must be JSON objects')
                if not isinstance(option.get('action'),str) or option.get("action") not in {"click","fill","check","select","press","drag","expect_text","expect_value","expect_count"}:
                    raise Stop("Unsupported recorded UI option")
                if option.get("action") == "press" and option.get("value") not in {"Enter","Tab","Escape","ControlOrMeta+A"}:
                    raise Stop("Unsupported key in recorded recipe")
                if not option.get("target"):
                    raise Stop("Recorded option has no target")
                if option['action'] in ('fill','press','expect_text','expect_value','select') and not isinstance(option.get('value'),str):
                    raise Stop('Recorded text/select actions require a string value')
                if option['action']=='check' and type(option.get('value')) is not bool:
                    raise Stop('Recorded check requires a real boolean')
                if option['action']=='expect_count' and (type(option.get('value')) is not int or option['value']<0):
                    raise Stop('Recorded count must be a nonnegative integer')
                for desc in [option['target']] + ([option.get('to')] if option['action']=='drag' else []):
                    if not isinstance(desc,dict) or desc.get('by') not in ('role','text','placeholder','label','css') or not isinstance(desc.get('value'),str):
                        raise Stop('Recorded locator kind/value is invalid')
                    if desc['by']=='role' and not isinstance(desc.get('role'),str):
                        raise Stop('Recorded role is missing')
                    if 'index' in desc and (type(desc['index']) is not int or type(desc.get('count')) is not int or not 0 <= desc['index'] < desc['count']):
                        raise Stop('Recorded index requires an expected count')
            if s.get('frame') not in (None,'funnel-builder','form-builder-app','survey-builder-app','quiz-builder-app'):
                raise Stop('Unrecognized recorded builder frame')
            if not any(o['action'].startswith('expect_') for o in s['steps']):
                raise Stop("Recorded options require an explicit read-back assertion")
        if s["action"] == "community":
            if s.get("channels") or s.get("privacy") or s.get("branding"):
                raise Stop("Community portal settings require a captured options profile in its authenticated portal context")
            if not isinstance(s.get('description'),str) or len(s.get("description", "")) not in range(1, 151):
                raise Stop("Community description must be 1–150 characters")
            if not isinstance(s.get('slug'),str) or not re.fullmatch(r"[a-z0-9-]+", s.get("slug", "")):
                raise Stop("Community slug is required")
            if not s.get("allow_creation"):
                raise Stop("Community creation leaves a retained group; allow_creation must be explicit")
            if s.get("discovery", False):
                raise Stop("Discovery opt-in is not part of this pilot")
    return prepared


def secure_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temp = path.with_suffix(path.suffix + ".new")
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(value, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(temp, path)


def visible(locator):
    return locator.count() == 1 and locator.is_visible()


def click(locator):
    locator.wait_for(state="visible", timeout=45000)
    if locator.count() != 1:
        raise Stop("Selector is ambiguous")
    locator.click(timeout=45000)


def fill(locator, value):
    locator.wait_for(state="visible", timeout=45000)
    if locator.count() != 1:
        raise Stop("Input is ambiguous")
    locator.fill(str(value))


def wait_until(fn, message, timeout=45):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if fn():
            return
        time.sleep(.25)
    raise Stop(message)


def assert_tenant(page, job):
    path = urlparse(page.url).path
    if urlparse(page.url).netloc != urlparse(job["start_url"]).netloc:
        raise Stop("Unexpected app origin")
    if not re.search(r"/(?:v2/)?location/" + re.escape(job["location_id"]) + r"(?:/|$)", path):
        raise Stop("Wrong tenant or authentication expired")
    has_editor = page.locator('iframe[name$="-builder-app"],iframe[name="funnel-builder"]').count() > 0
    if "/v2/location/" in path and not has_editor:
        group = page.get_by_role("region", name="Workspace navigation", exact=True).get_by_role("group", name=job["location_name"], exact=True)
        group.wait_for(state="visible", timeout=45000)


def builder(page):
    return page.frame_locator('iframe[name="funnel-builder"]')


def form_builder(page):
    return page.frame_locator('iframe[name="form-builder-app"]')


def leave_editor(page):
    for selector in ('iframe[name="funnel-builder"]', 'iframe[name="form-builder-app"]', 'iframe[name="survey-builder-app"]', 'iframe[name="quiz-builder-app"]'):
        if page.locator(selector).count():
            b = page.frame_locator(selector).get_by_role("button", name="Back", exact=True).first
            click(b)
            page.locator(selector).wait_for(state="detached", timeout=45000)


def navigate(page, area):
    leave_editor(page)
    section = "Client Apps" if area in ("Communities","Meeting Room","Courses") else "Sites"
    click(page.get_by_role("region", name=section, exact=True).get_by_role("button", name=section, exact=True))
    flyout = page.get_by_role("dialog", name=section, exact=True)
    if area in ("Surveys","Quizzes"):
        expand = flyout.get_by_role("button",name="Show Forms pages",exact=True)
        if visible(expand):
            click(expand)
    click(flyout.get_by_role("link", name=area, exact=True))
    close = page.get_by_role("button", name=f"Close {section} navigation", exact=True)
    if visible(close):
        click(close)


def exact_search(page, area, name):
    search = page.get_by_role("textbox", name=f"Search for {area}", exact=True)
    fill(search, name)
    cell = page.get_by_role("gridcell", name=name, exact=True)
    # The search is debounced. Never infer absence from a transient empty tree.
    def settled():
        if cell.count():
            return True
        text = page.locator("body").inner_text()
        if page.get_by_text('No items found',exact=True).count() and ('Your search “'+name+'” did not match any items.') in text:
            return True
        return bool(re.search(r"(?:0\s*[-–]\s*0\s+of\s+0|No (?:forms|funnels|websites|results).*found)", text, re.I))
    wait_until(settled, "Search absence could not be proven; refusing duplicate creation")
    if cell.count() > 1:
        raise Stop("Duplicate names; supply an explicit target through the existing inventory router")
    return cell if cell.count() else None


def ensure_container(page, step):
    area = "funnels" if step["surface"] == "funnel" else "websites"
    cell = exact_search(page, area, step["name"])
    if cell is not None:
        click(cell.get_by_text(step["name"], exact=True))
    else:
        if not step.get("allow_creation"):
            raise Stop("Container is absent and creation was not requested")
        noun = step["surface"]
        click(page.get_by_role("button", name=f"New {noun}", exact=True))
        dialog = page.get_by_role("dialog")
        fill(dialog.get_by_role("textbox", name=f"e.g. Sales {noun}", exact=True), step["name"])
        click(dialog.get_by_role("button", name="Create", exact=True))
    page.get_by_role("button", name="Share " + step["surface"], exact=True).wait_for(state="visible", timeout=45000)
    return {"container_url": page.url, "name": step["name"]}


def ensure_page(page, step):
    surface = step["surface"]
    if surface == "website":
        found = page.get_by_role("heading", name=step["name"], exact=True)
    else:
        found = page.get_by_role("tabpanel").get_by_text(step["name"], exact=True)
    if found.count():
        # Existing multi-page targets require a scoped card; do not pick the first Edit.
        edits = page.get_by_role("button", name="Edit", exact=True)
        if edits.count() != 1:
            raise Stop("Multiple pages: the inventory router must open the exact page before installation")
        click(edits)
    else:
        if not step.get("allow_creation"):
            raise Stop("Page absent and creation was not requested")
        click(page.get_by_role("button", name="Add new step or import" if surface == "funnel" else "Add new page", exact=True))
        dialog = page.get_by_role("dialog")
        fill(dialog.get_by_role("textbox", name="Name for page", exact=True), step["name"])
        fill(dialog.get_by_role("textbox", name="Path", exact=True), step["path"])
        click(dialog.get_by_role("button", name="Create funnel step" if surface == "funnel" else "Create new page", exact=True))
        blank = page.get_by_role("button", name="Create from blank", exact=True)
        click(blank)
    builder(page).get_by_role("button", name="Back", exact=True).wait_for(state="visible", timeout=45000)
    ai = builder(page).get_by_role("button", name="Close Ask AI", exact=True)
    if visible(ai):
        click(ai)
    return {"editor_url": page.url}


def full_width(frame):
    sections = frame.locator(".c-section")
    if sections.count()!=1:
        raise Stop('Width mutation requires one inventoried target section; refusing to alter unrelated sections')
    if not sections.count():
        raise Stop("No section to configure")
    for n in range(sections.count()):
        section = sections.nth(n)
        section.click(position={"x":20, "y":20})
        settings = frame.locator('[title="Open Settings"]')
        if not visible(frame.get_by_text("Allow Rows to take entire width", exact=True)):
            click(settings)
        group = frame.locator(".toggle-group").filter(has_text="Allow Rows to take entire width")
        toggle = group.locator(".toggle-btn")
        if "toggle-btn-end" not in (toggle.get_attribute("class") or ""):
            click(group.locator(".toggle"))
        if "toggle-btn-end" not in (toggle.get_attribute("class") or ""):
            raise Stop("Entire-width rows did not enable")
        if "fullSection" not in (section.get_attribute("class") or ""):
            raise Stop("Section width is not Full; current pilot refuses an uncaptured width dropdown variant")


def add_tile(frame, category, name):
    click(frame.locator("#hl-builder-add-elements-button"))
    click(frame.get_by_role("button", name=category, exact=True))
    if category == "Elements":
        fill(frame.get_by_role("textbox", name="Search Element", exact=True), name)
    click(frame.locator("[id=" + json.dumps(name) + "]"))


def save_page(frame):
    save = frame.locator('#pg-funnel-builder__btn--save, #pg-website-builder__btn--save')
    click(save)
    def finished():
        return not save.locator('img[alt="loading"]').count() and frame.get_by_text(re.compile(r"Last saved")).count() > 0
    wait_until(finished, "Page save never produced a completed-save indication")


def install_html(page, step):
    frame = builder(page)
    blank = frame.get_by_role("button", name="Blank Section", exact=True)
    if not visible(blank) and frame.locator('.c-section').count()!=1:
        raise Stop('Existing multi-section page needs a recorded target profile before any code or width mutation')
    if visible(blank):
        click(blank)
        full_width(frame)
        add_tile(frame, "Rows", "1 Column")
        add_tile(frame, "Elements", "Code")
        fill(frame.get_by_role("textbox", name="Element name", exact=True), "ZHC Code " + step["id"])
    elif step.get("append"):
        click(frame.get_by_role("button",name="1st Column",exact=True))
        add_tile(frame,"Elements","Code")
        fill(frame.get_by_role("textbox",name="Element name",exact=True),"ZHC Code " + step["id"])
    else:
        # Explicit, unique code block name is the update identity; never replace arbitrary content.
        code = frame.get_by_role("button", name="ZHC Code " + step["id"], exact=True)
        if not visible(code):
            raise Stop("Existing page needs its exact code block selected through inventory/browser recovery")
        click(code)
    click(frame.get_by_role("button", name="Open Code Editor", exact=True))
    modal = frame.get_by_role("dialog", name="UI Modal", exact=True)
    fill(modal.get_by_role("textbox"), step["html"])
    click(modal.get_by_role("button", name="Save", exact=True))
    modal.wait_for(state="hidden")
    close = frame.get_by_role("button", name="Close", exact=True)
    if visible(close):
        click(close)
    full_width(frame)
    save_page(frame)
    href = frame.locator('a[href*="/preview/"]').get_attribute("href")
    check = page.context.new_page()
    try:
        response = check.goto(href, wait_until="domcontentloaded", timeout=45000)
        if response is None or response.status != 200:
            raise Stop("Preview did not return HTTP 200")
        check.get_by_text(step["marker"], exact=False).first.wait_for(state="visible", timeout=45000)
        return {"editor_url":page.url, "preview_url":check.url, "rendered_marker":step["marker"], "html_sha256":step["html_sha256"], "status":"RENDERED"}
    finally:
        check.close()


def seo(page, step):
    frame = builder(page)
    if not visible(frame.get_by_text("SEO & AI search optimization", exact=True)):
        save_page(frame)
    for panel, field in (("Content", "Title"), ("Content", "Description"), ("Keywords", "Keywords"), ("Author", "Author")):
        textbox = frame.get_by_role("textbox", name=field, exact=True)
        if not visible(textbox):
            click(frame.get_by_text(panel, exact=True))
        value = ", ".join(step["keywords"]) if field == "Keywords" else step[field.lower()]
        fill(textbox, value)
    click(frame.get_by_text("Links & tags", exact=True))
    canonical = frame.get_by_text(step["canonical"], exact=True)
    if not canonical.count():
        adds = frame.get_by_role("button", name="Add", exact=True)
        if adds.count() != 2:
            raise Stop("Canonical section changed; no positional guess")
        click(adds.nth(1))
        modal = frame.get_by_role("dialog", name="UI Modal", exact=True)
        fill(modal.get_by_role("textbox", name="https://example.com", exact=True), step["canonical"])
        click(modal.get_by_role("button", name="Add", exact=True))
    click(frame.get_by_text("Language", exact=True))
    lang = frame.get_by_text("en - English", exact=True)
    if not visible(lang):
        raise Stop("Language selector changed; capture required")
    click(lang)
    click(frame.get_by_text("en - English", exact=True).last)
    save_page(frame)
    href=frame.locator('a[href*="/preview/"]').get_attribute('href')
    check=page.context.new_page()
    try:
        response=check.goto(href,wait_until='domcontentloaded',timeout=45000)
        if not response or response.status!=200:
            raise Stop('SEO preview HTTP check failed')
        def metadata():
            return check.evaluate("""() => ({title:document.title,description:document.querySelector('meta[name="description"]')?.content,keywords:document.querySelector('meta[name="keywords"]')?.content,author:document.querySelector('meta[name="author"]')?.content,canonical:document.querySelector('link[rel="canonical"]')?.href,language:document.documentElement.lang})""")
        expected={'title':step['title'],'description':step['description'],'keywords':', '.join(step['keywords']),'author':step['author'],'canonical':step['canonical'],'language':'en'}
        wait_until(lambda:metadata()==expected,'Rendered SEO metadata did not match the saved inputs')
    finally:
        check.close()
    return {"status":"SEO_RENDERED", "canonical":step["canonical"]}


def checkout(page, step):
    frame = builder(page)
    if not visible(frame.get_by_role("button", name="Customize order form", exact=True)):
        columns = frame.get_by_role("button", name="1st Column", exact=True)
        if not visible(columns):
            raise Stop("Open the exact target column before installing native checkout")
        click(columns)
        add_tile(frame, "Elements", "Order Form")
    click(frame.get_by_role("button", name="Customize order form", exact=True))
    dialog = frame.get_by_role("dialog").filter(has_text="Form settings")
    click(dialog.get_by_role("button", name=step.get("mode", "One-step"), exact=True))
    click(dialog.get_by_role("button", name="Products", exact=True))
    for key, label in (("coupon_codes", "Enable coupon codes"), ("quantity", "Show quantity"), ("multi_product", "Enable multi-product selection")):
        if key in step:
            dialog.get_by_role("switch", name=label, exact=True).set_checked(step[key])
    no_products = dialog.get_by_text("No products on this step yet.", exact=True).count() > 0
    click(dialog.get_by_role("button", name="Alternative text for image not provided", exact=True))
    save_page(frame)
    return {"status":"COMPONENT_SAVED", "mode":step.get("mode", "One-step"), "products_missing":no_products, "payment_verified":False, "checkout_ready":False, "next":"Skill 44/79 product and price binding, offer mapping, test-mode payment and upsell verification"}


def make_form(page, step):
    navigate(page, "Forms")
    cell = exact_search(page, "forms", step["name"])
    if cell is not None:
        click(cell.get_by_text(step["name"], exact=True))
    else:
        if not step.get("allow_creation"):
            raise Stop("Form absent and creation not requested")
        click(page.get_by_role("button", name="Create form", exact=True))
        click(page.get_by_role("dialog").get_by_role("button", name="Create", exact=True))
    frame = form_builder(page)
    title = frame.get_by_role("textbox", name="Form Name", exact=True)
    fill(title, step["name"])
    close = frame.get_by_role("button", name="Close", exact=True)
    if visible(close):
        click(close)
    placeholders = {"First Name":"Enter your first name", "Last Name":"Enter your last name", "Phone":"+1 (555) 000-0000", "Email":"your@email.com"}
    for field, required in step.get("required", {}).items():
        click(frame.get_by_role("tab", name="Edit", exact=True))
        click(frame.get_by_placeholder(placeholders[field], exact=True))
        click(frame.get_by_label("Open settings", exact=True))
        frame.get_by_role("checkbox", name="Required", exact=True).set_checked(required)
    click(frame.get_by_role("button", name="Save", exact=True))
    frame.get_by_role("button", name="Save", exact=True).wait_for(state="visible", timeout=45000)
    click(frame.get_by_role("button", name="Back", exact=True).first)
    cell = exact_search(page, "forms", step["name"])
    if cell is None:
        raise Stop("Saved form absent on independent list read-back")
    click(cell.get_by_text(step["name"], exact=True))
    title.wait_for(state="visible", timeout=45000)
    close = frame.get_by_role("button", name="Close", exact=True)
    if visible(close):
        click(close)
    for field, required in step.get("required", {}).items():
        frame.get_by_text(field + ("*" if required else ""), exact=True).wait_for(state="visible", timeout=45000)
    return {"form_url":page.url, "status":"SAVED_AND_REOPENED", "required":step.get("required", {}), "consent_and_legal_copy":"REQUIRES_CLIENT_INPUT_BEFORE_USE"}


def form_css(page, step):
    frame = form_builder(page)
    # Keep the form's CSS inside its own builder; parent-page CSS cannot cross the iframe.
    click(frame.get_by_role("button",name="Styles & Options",exact=True))
    click(frame.get_by_text("Advanced",exact=True))
    click(frame.get_by_text("Custom CSS",exact=True))
    pane = frame.get_by_role("dialog").filter(has_text="Custom CSS")
    radius = step.get("radius",12)
    css = ('/* ZHC-SKILL6-POLISH-BEGIN */\n'
           'input:not([type="checkbox"]):not([type="radio"]):not([type="hidden"]), textarea, select '
           '{ border-radius: '+str(radius)+'px !important; }\n'
           'button[type="submit"] { border-radius: '+str(radius)+'px !important; min-height:44px; }\n/* ZHC-SKILL6-POLISH-END */')
    editor = pane.get_by_role("textbox")
    existing = editor.evaluate("el => el.value ?? el.innerText ?? ''")
    existing = re.sub(r"/\* ZHC-SKILL6-POLISH-BEGIN \*/.*?/\* ZHC-SKILL6-POLISH-END \*/", "", existing, flags=re.S)
    fill(editor, existing.rstrip() + "\n" + css)
    click(pane.get_by_role("button",name="Close",exact=True))
    click(frame.get_by_role("button",name="Save",exact=True))
    frame.get_by_role("button",name="Save",exact=True).wait_for(state="visible",timeout=45000)
    close=frame.get_by_role('dialog').get_by_role('button',name='Close',exact=True)
    if visible(close):
        click(close)
    with page.context.expect_page(timeout=45000) as event:
        click(frame.get_by_role('button',name='Preview',exact=True))
    check=event.value
    try:
        check.wait_for_load_state('domcontentloaded')
        check.locator('input').first.wait_for(state='visible',timeout=45000)
        radii=check.locator('input:not([type="checkbox"]):not([type="radio"]):not([type="hidden"])').evaluate_all('(els)=>els.map(el=>getComputedStyle(el).borderRadius)')
        if not radii or any(r!=str(radius)+'px' for r in radii):
            raise Stop('Native form computed corner radius does not match')
    finally:
        check.close()
    return {"status":"FORM_CSS_RENDERED", "radius":radius}


def drag_field(page, frame, name):
    source = frame.locator('.gui__builder-card').filter(has=frame.get_by_text(name,exact=True))
    target = frame.get_by_text("Drag and drop components",exact=True)
    source.scroll_into_view_if_needed()
    target.scroll_into_view_if_needed()
    a, b = source.bounding_box(), target.bounding_box()
    if not a or not b:
        raise Stop("Field drag endpoints not visible")
    # Native pointer drag is the observed Vue sortable mechanism (HTML5 event
    # injection and a top-frame-only ref drag are deliberately not used).
    page.mouse.move(a['x']+a['width']/2,a['y']+a['height']/2)
    page.mouse.down()
    page.mouse.move(a['x']+a['width']/2+20,a['y']+a['height']/2,steps=5)
    page.mouse.move(b['x']+b['width']/2,b['y']+b['height']/2,steps=15)
    page.mouse.up()


def assessment(page, step):
    kind = step['kind']
    area = 'Surveys' if kind == 'survey' else 'Quizzes'
    navigate(page,area)
    search = page.get_by_role('textbox',name='Search for '+area.lower(),exact=True)
    cell = exact_search(page,area.lower(),step['name']) if search.count() else None
    reused=cell is not None
    if reused:
        if step.get('standard_fields'):
            raise Stop('Existing assessment must be inventoried for requested fields; refusing an unverified reuse')
        click(cell.get_by_text(step['name'],exact=True))
    else:
        if not step.get('allow_creation'):
            raise Stop("Assessment absent and creation not requested")
        create = page.get_by_role('button',name='Create '+kind,exact=True)
        # The empty quiz landing screen has duplicate identical create controls.
        if create.count() not in (1,2):
            raise Stop("Assessment create control changed")
        click(create.first)
        click(page.get_by_role('dialog').get_by_role('button',name='Create',exact=True))
    frame = page.frame_locator('iframe[name="'+kind+'-builder-app"]')
    fill(frame.get_by_role('textbox',name='Form Name',exact=True),step['name'])
    for index, name in enumerate([] if reused else step.get('standard_fields',[])):
        if index:
            close=frame.get_by_role('dialog').get_by_role('button',name='Close',exact=True)
            if visible(close):
                click(close)
            click(frame.get_by_role('button',name='Add Slide' if kind=='survey' else 'Add Page',exact=True))
            click(frame.get_by_role('button',name='Add '+kind.title()+' Element',exact=True))
        drag_field(page,frame,name)
        frame.get_by_placeholder({'Email':'your@email.com','First Name':'Enter your first name','Last Name':'Enter your last name','Phone':'+1 (555) 000-0000','Full Name':'Enter your full name'}[name],exact=True).wait_for(state='visible',timeout=45000)
    close=frame.get_by_role('dialog').get_by_role('button',name='Close',exact=True)
    if visible(close):
        click(close)
    click(frame.get_by_role('button',name='Save',exact=True))
    frame.get_by_role('button',name='Save',exact=True).wait_for(state='visible',timeout=45000)
    return {'status':'ASSESSMENT_REUSED' if reused else 'ASSESSMENT_SAVE_SUBMITTED','kind':kind,'editor_url':page.url,'independent_readback':'REQUIRED','scoring_and_branches':'Use captured options recipe; no submission was made'}


def meeting(page, step):
    navigate(page,'Meeting Room')
    create=page.get_by_role('region',name='Meeting Room for meetings, webinars and more',exact=True).get_by_role('button',name='Create room',exact=True)
    if not visible(create):
        raise Stop("An existing room or different editor requires a captured update profile; never overwrite it")
    click(create)
    region=page.get_by_role('region',name='Create room',exact=True)
    fields=region.get_by_role('textbox',name='Please Input',exact=True)
    if fields.count()!=3:
        raise Stop("Meeting details changed; capture required")
    fill(fields.nth(0),step['name'])
    fill(fields.nth(1),step['slug'])
    # Retain GHL's generated passcode. Never print, copy into evidence, or capture it.
    for key,label in [('waiting_room','Waiting room'),('guest_users','Allow guest users'),('open_room','Open room')]:
        region.get_by_role('switch',name=label,exact=True).set_checked(step[key])
    submit=region.get_by_role('button',name='Create room',exact=True)
    wait_until(lambda:submit.is_enabled(),"Room slug is unavailable or details invalid")
    click(submit)
    region.wait_for(state='hidden',timeout=45000)
    return {'status':'ROOM_SAVE_SUBMITTED','name':step['name'],'slug':step['slug'],'independent_readback':'REQUIRED','meeting_started':False}


def option_locator(page, desc, frame_name=None):
    allowed_frames={'funnel-builder','form-builder-app','survey-builder-app','quiz-builder-app'}
    if frame_name and frame_name not in allowed_frames:
        raise Stop("Unrecognized builder frame")
    root=page.frame_locator('iframe[name="'+frame_name+'"]') if frame_name else page
    if desc.get('scope'):
        root=root.locator(desc['scope'])
    by=desc.get('by')
    value=desc.get('value','')
    if by=='role':
        loc=root.get_by_role(desc['role'],name=value,exact=True)
    elif by=='text':
        loc=root.get_by_text(value,exact=True)
    elif by=='placeholder':
        loc=root.get_by_placeholder(value,exact=True)
    elif by=='label':
        loc=root.get_by_label(value,exact=True)
    elif by=='css':
        loc=root.locator(value)
    else:
        raise Stop("Unknown captured locator kind")
    if 'count' in desc and loc.count()!=desc['count']:
        raise Stop("Captured locator count changed")
    if 'index' in desc:
        if 'count' not in desc:
            raise Stop("Indexed locators require a captured count")
        loc=loc.nth(desc['index'])
    return loc


def options(page, step):
    for action in step['steps']:
        loc=option_locator(page,action['target'],step.get('frame'))
        kind=action['action']
        if not kind.startswith('expect_'):
            control=loc.evaluate("""el => {
                const owner=el.closest('button,a,[role="button"],input,textarea,select,[contenteditable="true"]');
                const describe=n=>n ? [n.id,n.getAttribute('aria-label'),n.getAttribute('title'),n.getAttribute('type'),n.getAttribute('placeholder'),n.textContent].join(' ').slice(0,1000) : '';
                return describe(el)+' '+describe(owner);
            }""")
            if re.search(r'publish|complete order|buy now|purchase|delete|invite|change password|new password|card number|cc-number|cc-csc',control,re.I):
                raise Stop('This terminal action belongs to the existing publish/payment/identity gate')
        if kind=='click':
            click(loc)
        elif kind=='fill':
            fill(loc,action['value'])
        elif kind=='check':
            loc.set_checked(action['value'])
        elif kind=='select':
            loc.select_option(action['value'])
        elif kind=='press':
            loc.press(action['value'])
        elif kind=='drag':
            loc.drag_to(option_locator(page,action['to'],step.get('frame')))
        elif kind=='expect_count':
            if loc.count()!=action['value']:
                raise Stop("Option count readback failed")
        elif kind=='expect_text':
            if action['value'] not in loc.inner_text():
                raise Stop("Option text readback failed")
        elif kind=='expect_value':
            if loc.input_value()!=str(action['value']):
                raise Stop("Option value readback failed")
    return {'status':'RECORDED_OPTIONS_EXECUTED','count':len(step['steps']),'capture_source':step['capture_source']}


def community(page, step):
    navigate(page, "Communities")
    existing = page.locator(".group-footer").filter(has=page.get_by_text(step["name"], exact=True))
    if not existing.count():
        # General multi-page list enumeration is not proven. Only create after an
        # authoritative empty-state, otherwise return for inventory reconciliation.
        if not visible(page.get_by_text("You don't have a community yet", exact=True)):
            raise Stop("Community list is not empty; reconcile active and inactive groups before creating")
        click(page.get_by_role("button", name="Create Group", exact=True))
        fill(page.get_by_role("textbox", name="Group Name", exact=True), step["name"])
        fill(page.get_by_role("textbox", name="Group Slug", exact=True), step["slug"])
        fill(page.get_by_role("textbox", name="Enter a brief description", exact=True), step["description"])
        page.get_by_role("switch").set_checked(False)
        click(page.get_by_role("button", name="Create Group", exact=True))
        existing.wait_for(state="visible", timeout=45000)
    if step.get("inactive", True):
        status = existing.locator("#status_button")
        if (status.inner_text()).strip() != "Inactive":
            click(status)
            click(page.get_by_text("Inactive", exact=True))
            click(page.get_by_role("dialog").get_by_role("button", name="Confirm", exact=True))
        wait_until(lambda: _text_equals(status, "Inactive"), "Group did not become inactive")
    return {"status":"GROUP_RETAINED_INACTIVE" if step.get("inactive", True) else "GROUP_CREATED", "name":step["name"], "slug":step["slug"], "discovery":False, "channels":"NOT_CONFIGURED", "deleted":False}


def _text_equals(locator, text):
    return (locator.inner_text()).strip() == text


def run_on_page(page, job, evidence_root):
    """Host integration seam: use an already managed, signed-in Playwright Page.

    State records are intent-before-mutation. A crashed/uncertain step is never
    replayed automatically. The host inspects its read-back and resumes a new,
    explicitly reconciled job. No broad browser-state or secret-bearing trace
    is written; only minimal object identifiers and named outcomes.
    """
    root = Path(evidence_root).resolve()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(root, 0o700)
    state_path = root / "state.json"
    fingerprint = sha(json.dumps(job, sort_keys=True))
    assert_tenant(page, job)
    if state_path.exists():
        old = json.loads(state_path.read_text())
        if old.get("fingerprint") != fingerprint:
            raise Stop("Evidence belongs to a different job")
        if old.get("status") in ("EDITOR_STEPS_COMPLETE","NEEDS_VERIFICATION"):
            return {**old,'status':'ALREADY_EXECUTED','meaning':'No writes repeated. Reconcile existing outputs before a new build.'}
        raise Stop("An interrupted job exists: reconcile recorded objects before any replay")
    results = []
    state = {"fingerprint":fingerprint, "location_id":job["location_id"], "status":"RUNNING", "results":results}
    handlers = {"container":ensure_container, "page":ensure_page, "html":install_html, "seo":seo, "checkout":checkout, "form":make_form, "form_css":form_css, "community":community,"assessment":assessment,"meeting":meeting,"options":options}
    for step in job["steps"]:
        assert_tenant(page, job)
        state["current_step"] = step["id"]
        state["current_step_status"] = "INTENT_RECORDED"
        secure_json(state_path, state)
        try:
            if step["action"] == "navigate":
                navigate(page, step["area"])
                result = {"area":step["area"]}
            else:
                result = handlers[step["action"]](page, step)
            assert_tenant(page, job)
            results.append({"id":step["id"], "action":step["action"], "result":result})
            state["current_step_status"] = "FINISHED"
            secure_json(state_path, state)
        except Exception as exc:
            # Never persist raw Playwright exception text: it may quote input values.
            state.update(status="NEEDS_BROWSER_RECOVERY", error_type=type(exc).__name__, failed_step=step["id"])
            secure_json(state_path, state)
            raise Stop("Step " + step["id"] + " needs browser recovery; no mutation was retried") from None
    pending=[r['id'] for r in results if r['result'].get('checkout_ready') is False or r['result'].get('independent_readback')=='REQUIRED' or r['result'].get('kind')=='quiz']
    state["status"] = "NEEDS_VERIFICATION" if pending else "EDITOR_STEPS_COMPLETE"
    state['verification_required']=pending
    state["meaning"] = "Requested editor steps completed; this is not a full-funnel QC or payment PASS"
    secure_json(state_path, state)
    return state


def execute(job, root):
    endpoint = os.environ.get("GHL_MANAGED_CDP_URL", "")
    if not endpoint:
        # Use the existing host lifecycle and Firebase bridge. No new credential
        # parser, login implementation, process pool, or per-iteration browser.
        from browser_manager import PlaywrightSession
        from ghl_auth import mint_and_bridge
        origin=urlparse(job['start_url']).scheme+'://'+urlparse(job['start_url']).netloc
        if origin not in ('https://app.gohighlevel.com','https://app.convertandflow.com'):
            raise Stop('The token bridge has no approved origin profile for this host')
        auth_dir=Path(root).resolve()/'auth-runtime'
        auth_dir.mkdir(parents=True,exist_ok=True,mode=0o700)
        os.chmod(auth_dir,0o700)
        seed_path=auth_dir/'seed.json'
        try:
            with PlaywrightSession(session='skill6-'+job['location_id']) as managed:
                page=managed.pages[0] if managed.pages else managed.new_page()
                page.goto(job['start_url'],wait_until='commit',timeout=45000)
                receipt=mint_and_bridge(page.context,managed.session,str(seed_path),expected_location_id=job['location_id'],app_origin=origin)
                if not receipt.get('ok') or receipt.page is None:
                    raise Stop('Token bridge did not establish the expected account')
                page=receipt.page
                page.goto(job['start_url'],wait_until='domcontentloaded',timeout=45000)
                managed.assert_alive()
                return run_on_page(page,job,root)
        finally:
            seed_path.unlink(missing_ok=True)
        # The manager owns headless launch, lock, TTL/watchdog, and teardown.
    parsed = urlparse(endpoint)
    if parsed.hostname not in ("localhost", "127.0.0.1", "::1") or parsed.scheme not in ("http", "ws") or parsed.username or parsed.password:
        raise Stop("Supply the existing managed loopback CDP endpoint; no browser is launched")
    lock_root = Path(os.environ.get("GHL_BROWSER_LOCK_DIR", str(Path.home() / ".cache/skill6-playwright")))
    lock_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Lock per managed browser endpoint, across all evidence roots and locations.
    with open(lock_root / (sha(endpoint) + ".lock"), "a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise Stop("Managed browser already leased by another script") from None
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            browser = pw.chromium.connect_over_cdp(endpoint)
            pages = [p for c in browser.contexts for p in c.pages if p.url == job["start_url"]]
            if len(pages) != 1:
                raise Stop("Exactly one existing tab must match start_url")
            return run_on_page(pages[0], job, root)
            # Exiting Playwright detaches this client; do not browser.close() a host-owned session.


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path)
    mode=parser.add_mutually_exclusive_group()
    mode.add_argument("--execute", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        job = validate_job(json.loads(args.job.read_text()), args.job.resolve().parent)
        if not args.execute:
            print(json.dumps({"status":"VALIDATED_ONLY", "steps":len(job["steps"]), "browser_used":False}))
            return 0
        if args.evidence_root is None:
            raise Stop("--evidence-root must name durable run storage outside the skill directory")
        result = execute(job, args.evidence_root)
        print(json.dumps({"status":result["status"], "steps":len(result["results"])}))
        return 0 if result['status']=='EDITOR_STEPS_COMPLETE' else 3
    except (Stop, ValueError, KeyError, OSError) as exc:
        print(json.dumps({"status":"STOP", "reason":str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
