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

# Direct CLI and package helpers must share the same executor and Stop class.
# Otherwise relative helper imports can load this file a second time, and a
# known refusal escapes the CLI's exception boundary as an unrelated class.
if __name__ in ('__main__', 'skill6_playwright', 'playwright_recipes.skill6_playwright'):
    sys.modules.setdefault('skill6_playwright', sys.modules[__name__])
    sys.modules.setdefault('playwright_recipes.skill6_playwright', sys.modules[__name__])


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
    if 'publish' in job and job['publish'] is not False:
        raise Stop("This runner only saves drafts; publishing stays with the existing approval gate")
    loc = job.get("location_id", "")
    if not isinstance(loc,str) or not re.fullmatch(r"[A-Za-z0-9_-]+", loc):
        raise Stop("location_id is required")
    if not isinstance(job.get('start_url'),str) or not isinstance(job.get('location_name'),str):
        raise Stop('start_url and location_name must be strings')
    u = urlparse(job.get("start_url", ""))
    if u.scheme != "https" or u.username or u.password or u.fragment:
        raise Stop("start_url must be an exact HTTPS app URL without fragment or credentials")
    if not re.search(r"/(?:v2/)?location/" + re.escape(loc) + r"(?:/|$)", u.path):
        raise Stop("start_url must belong to location_id")
    if not job.get("location_name"):
        raise Stop("location_name is required for the visible account check")
    if u.query:
        # The captured course Customize manager needs three exact parameters.
        # No general query exception is granted to options or other actions.
        query_steps = job.get('steps')
        if (not isinstance(query_steps, list) or len(query_steps) != 1
                or any(not isinstance(step, dict) or step.get('action') not in ('native_course_theme', 'native_course_blocks', 'native_course_theme_media', 'native_course_block_media', 'native_course_text_blocks', 'native_course_section_media', 'native_course_image_blocks', 'native_course_video_blocks', 'native_dynamic_meeting_location')
                       for step in query_steps)):
            raise Stop('Only a captured native editor job may use its bound manager query')
        from playwright_recipes.course_theme import validate as validate_course_theme
        for step in query_steps:
            if step['action'] == 'native_course_video_blocks':
                from playwright_recipes.course_video_blocks import validate
                payload = validate(step)
            elif step['action'] == 'native_course_image_blocks':
                from playwright_recipes.course_image_blocks import validate
                payload = validate(step)
            elif step['action'] == 'native_course_section_media':
                from playwright_recipes.course_section_media import validate
                payload = validate(step)
            elif step['action'] == 'native_course_text_blocks':
                from playwright_recipes.course_text_blocks import validate
                payload = validate(step)
            elif step['action'] == 'native_course_blocks':
                from playwright_recipes.course_blocks import validate
                payload = validate(step)
            elif step['action'] == 'native_course_theme_media':
                from playwright_recipes.course_theme_media import validate
                payload = validate(step)
            elif step['action'] == 'native_course_block_media':
                from playwright_recipes.course_block_media import validate
                payload = validate(step)
            elif step['action'] == 'native_dynamic_meeting_location':
                from playwright_recipes.meeting_dynamic import validate_inputs
                payload = validate_inputs(step.get('payload'), require_fresh=False)
            else:
                payload = validate_course_theme(step)
            if any(payload[key] != job[key] for key in ('location_id', 'location_name', 'start_url')):
                raise Stop('Native manager query belongs to another job identity')
    if 'auth_activation' in job:
        activation = job['auth_activation']
        if not isinstance(activation, dict) or set(activation) - {'expected_builder_title'}:
            raise Stop('Auth activation must be an explicit captured-profile contract')
        from ghl_auth import AuthBridgeError
        from ghl_auth_activation import validate_target
        try:
            validate_target({**activation, 'location_name': job['location_name'],
                             'start_url': job['start_url']}, loc)
        except AuthBridgeError as exc:
            raise Stop(str(exc)) from None
    steps = job.get("steps", [])
    if not isinstance(steps,list) or not steps:
        raise Stop("No executable steps")
    keys = set()
    allowed = {"native_survey_multiline_configuration", "native_split_variant", "navigate", "container", "page", "html", "seo", "checkout", "native_checkout", "native_checkout_ui", "native_course_theme", "native_course_blocks", "native_course_text_blocks", "native_course_section_media", "native_course_image_blocks", "native_course_video_blocks", "native_course_theme_media", "native_course_block_media", "native_fields", "native_field_placement", "native_address_fields", "native_address_parent", "native_form_consent", "native_object_fields", "native_contact_field_chain", "native_survey_radio_creation", "native_quiz_creation", "native_survey_creation", "native_dropdown_fields", "native_large_text_fields", "quiz_short_answers", "quiz_multiple_choices", "quiz_written_answers", "quiz_picture_choices", "native_survey_object_fields", "native_survey_text_configuration", "native_condition", "native_condition_group", "native_condition_stack", "native_condition_outcomes", "quiz_configuration", "quiz_results", "survey_configuration", "survey_rule_stack", "form", "form_css", "native_form_css", "native_form_schedule", "native_form_tracking", "native_form_embed", "native_order_confirmation", "form_submission", "form_notifications", "form_settings", "community", "community_channels", "community_details", "community_access", "community_courses", "community_event_room", "community_branding", "assessment", "meeting", "meeting_cohosts", "native_dynamic_meeting_location", "options"}
    prepared = json.loads(json.dumps(job))
    for s in prepared["steps"]:
        if not isinstance(s,dict):
            raise Stop('Every step must be a JSON object')
        if not isinstance(s.get('id'),str) or not re.fullmatch(r"[a-z0-9_-]+", s['id']) or s['id'] in keys:
            raise Stop("Every step requires a unique simple id")
        keys.add(s["id"])
        if not isinstance(s.get('action'),str) or s.get("action") not in allowed:
            raise Stop("Unknown or uncaptured action: " + str(s.get("action")))
        for flag in ('allow_creation', 'append', 'inactive', 'discovery'):
            if flag in s and type(s[flag]) is not bool:
                raise Stop(flag + ' requires a real boolean')
        if s['action']=='native_field_placement':
            from playwright_recipes.field_placement import validate
            validate(s)
        if s['action']=='native_address_parent':
            from playwright_recipes.address_parent import validate
            validate(s)
            if len(prepared['steps'])!=1 or any(s['payload'][key]!=job[key] for key in ('location_id','location_name','start_url')):
                raise Stop('Parent Address must be a single step bound to its parent job identity')
        if s['action']=='native_address_fields':
            from playwright_recipes.forms_advanced import validate
            validate(s)
        if s['action']=='native_form_consent':
            from playwright_recipes.forms_advanced import validate_consent
            validate_consent(s)
        if s['action']=='native_quiz_creation':
            from playwright_recipes.quiz_creation import validate
            payload=validate(s)
            if len(prepared['steps'])!=1 or any(payload[key]!=job[key] for key in ('location_id','location_name','start_url')):
                raise Stop('Quiz creation requires its own exact same-location list job')
        if s['action'] in ('native_survey_radio_creation','native_survey_creation'):
            from playwright_recipes.survey_radio_creation import validate
            payload=validate(s)
            if len(prepared['steps'])!=1 or any(payload[key]!=job[key] for key in ('location_id','location_name','start_url')):
                raise Stop('Survey creation requires its own exact same-location list job')
        if s['action']=='native_contact_field_chain':
            from playwright_recipes.contact_field_frontdoor import validate
            payload = validate(s)
            if (len(prepared['steps']) != 1 or any(payload[key] != job[key]
                    for key in ('location_id','location_name','start_url'))):
                raise Stop('Contact dependency chain requires its own exact same-editor job')
        if s['action']=='native_split_variant':
            from playwright_recipes.split_variant import validate
            payload=validate(s)['payload']
            if len(prepared['steps']) != 1 or any(payload[key]!=job[key] for key in ('location_id','location_name','start_url')):
                raise Stop('Native split variants require their own exact same-location overview job')
        if s['action']=='native_survey_multiline_configuration':
            from playwright_recipes.survey_multiline_configuration import validate
            payload=validate(s)
            if any(payload[key]!=job[key] for key in ('location_id','location_name','start_url')):
                raise Stop('Survey Multi Line properties belong to another editor/location')
        if s['action']=='native_survey_text_configuration':
            from playwright_recipes.survey_text_configuration import validate
            payload=validate(s)
            if any(payload[key]!=job[key] for key in ('location_id','location_name','start_url')):
                raise Stop('Survey TEXT properties belong to another editor/location')
        if s['action'] in ('native_object_fields', 'native_survey_object_fields'):
            if s['action'] == 'native_object_fields':
                from playwright_recipes.forms_advanced import validate_object_fields as validate
            else:
                from playwright_recipes.survey_fields import validate
            validate(s)
            payload = s['payload']
            if any(payload[key] != job[key] for key in ('location_id', 'location_name', 'start_url')):
                raise Stop('Native object fields belong to a different location or editor')
        if s['action'] == 'quiz_picture_choices':
            from playwright_recipes.quiz_picture_questions import validate
            validate(s)
            if any(s['payload'][key] != job[key] for key in ('location_id','location_name','start_url')):
                raise Stop('Picture Choice belongs to another editor or location')
        if s['action'] in ('native_dropdown_fields','native_large_text_fields','quiz_short_answers','quiz_multiple_choices','quiz_written_answers'):
            if s['action']=='native_dropdown_fields':
                from playwright_recipes.dropdown_fields import validate
            elif s['action']=='native_large_text_fields':
                from playwright_recipes.large_text_fields import validate
            elif s['action']=='quiz_multiple_choices':
                from playwright_recipes.quiz_choice_questions import validate
            elif s['action']=='quiz_written_answers':
                from playwright_recipes.quiz_written_questions import validate
            else:
                from playwright_recipes.quiz_text_questions import validate
            validate(s)
            if any(s['payload'][key]!=job[key] for key in ('location_id','location_name','start_url')):
                raise Stop('Native question payload belongs to another editor or location')
        if s['action']=='native_form_embed':
            from playwright_recipes.form_embed import validate
            plan = validate(s)
            expected = '/v2/location/' + job['location_id'] + '/form-builder-v2/' + plan['integration']['form_id']
            if urlparse(job['start_url']).path.rstrip('/') != expected:
                raise Stop('Native embed job must bind its exact inventoried form editor')
        if s['action']=='native_form_tracking':
            from playwright_recipes.form_tracking import validate
            validate(s)
        if s['action']=='native_form_schedule':
            from playwright_recipes.form_schedule import validate
            validate(s)
        if s['action']=='native_course_theme':
            from playwright_recipes.course_theme import validate
            payload = validate(s)
            if any(payload[key] != job[key] for key in ('location_id', 'location_name', 'start_url')):
                raise Stop('Course theme payload belongs to a different location or manager')
        if s['action']=='native_course_block_media':
            from playwright_recipes.course_block_media import validate
            payload = validate(s)
            if any(payload[key] != job[key] for key in ('location_id', 'location_name', 'start_url')):
                raise Stop('Course block image payload belongs to another location or manager')
        if s['action']=='native_condition_outcomes':
            from playwright_recipes.form_condition_outcomes import validate
            validate(s)
        if s['action']=='native_condition_stack':
            from playwright_recipes.form_condition_stack import validate
            validate(s)
        if s['action']=='native_course_theme_media':
            from playwright_recipes.course_theme_media import validate
            payload = validate(s)
            if any(payload[key] != job[key] for key in ('location_id', 'location_name', 'start_url')):
                raise Stop('Course background payload belongs to another location or manager')
        if s['action']=='native_course_video_blocks':
            from playwright_recipes.course_video_blocks import validate
            payload=validate(s)
            if any(payload[key]!=job[key] for key in ('location_id','location_name','start_url')):
                raise Stop('Course Video Blocks belong to another location or manager')
        if s['action']=='native_course_image_blocks':
            from playwright_recipes.course_image_blocks import validate
            payload = validate(s)
            if any(payload[key] != job[key] for key in ('location_id','location_name','start_url')):
                raise Stop('Course Image Blocks belong to another location or manager')
        if s['action']=='native_course_section_media':
            from playwright_recipes.course_section_media import validate
            payload = validate(s)
            if any(payload[key] != job[key] for key in ('location_id','location_name','start_url')):
                raise Stop('Course section media belongs to another location or manager')
        if s['action']=='native_course_text_blocks':
            from playwright_recipes.course_text_blocks import validate
            payload = validate(s)
            if any(payload[key] != job[key] for key in ('location_id','location_name','start_url')):
                raise Stop('Course Text Blocks belong to another location or manager')
        if s['action']=='native_course_blocks':
            from playwright_recipes.course_blocks import validate
            payload = validate(s)
            if any(payload[key] != job[key] for key in ('location_id', 'location_name', 'start_url')):
                raise Stop('Course Custom Block payload belongs to another location or manager')
        if s['action']=='native_condition_group':
            from playwright_recipes.form_conditions import validate
            validate(s)
        if s['action'] in ('native_fields','native_condition'):
            from playwright_recipes.assessments import validate_fields, validate_condition
            (validate_fields if s['action']=='native_fields' else validate_condition)(s)
        if s['action']=='native_order_confirmation':
            from playwright_recipes.form_order_confirmation import validate
            plan = validate(s)['payload']
            if any(plan[key] != job[key] for key in ('location_id', 'location_name', 'start_url')):
                raise Stop('Order Confirmation payload belongs to another location or editor')
        if s['action']=='form_submission':
            from playwright_recipes.form_submission import validate
            validate(s)
        if s['action'] == 'community_event_room':
            if set(s) != {'id', 'action', 'payload'}:
                raise Stop('Event portal context belongs to the live host, never a JSON job')
            from playwright_recipes.community_event_meeting import validate_inputs
            payload = validate_inputs(s.get('payload'))
            if any(payload[key] != job[key] for key in ('location_id', 'location_name', 'start_url')):
                raise Stop('Community event payload belongs to another app location')
        if s['action'] in ('community_channels', 'community_details', 'community_access', 'community_courses', 'community_branding'):
            from playwright_recipes.community_portal import validate_inputs, validate_details_inputs
            if s['action'] == 'community_branding':
                if set(s) != {'id', 'action', 'payload'}:
                    raise Stop('Community Branding requires only its bound payload')
                from playwright_recipes.community_branding import validate_inputs as validator
            elif s['action'] == 'community_courses':
                if set(s) != {'id', 'action', 'payload'}:
                    raise Stop('Community course associations require a bound payload')
                from playwright_recipes.community_courses import validate_inputs as validator
            elif s['action'] == 'community_access':
                if set(s) - {'id', 'action', 'payload'}:
                    raise Stop('Community access authorizations belong to the live host, never the JSON job')
                from playwright_recipes.community_access import validate_inputs as validate_access_inputs
                validator = validate_access_inputs
            else:
                validator = validate_details_inputs if s['action'] == 'community_details' else validate_inputs
            payload = validator(s.get('payload'))
            if any(payload[key] != job[key] for key in ('location_id', 'location_name', 'start_url')):
                raise Stop('Community payload belongs to a different app location')
        if s['action']=='form_notifications':
            from playwright_recipes.form_notifications import validate_notifications
            s['_context'] = {k:job[k] for k in ('location_id','location_name','start_url')}
            validate_notifications(s)
        if s['action']=='native_form_css':
            from playwright_recipes.assessments import validate_css
            validate_css(s)
        if s['action'] in ('survey_configuration', 'survey_rule_stack'):
            from playwright_recipes.survey_ui import validate
            validate(s)
            if (s['action'] == 'survey_rule_stack') != ('rules' in s):
                raise Stop('Survey rule-stack action must match its exact input schema')
        if s['action']=='quiz_configuration':
            from playwright_recipes.quiz_ui import validate
            validate(s)
        if s['action']=='quiz_results':
            from playwright_recipes.quiz_results import validate
            validate(s)
        if s['action']=='native_checkout_ui':
            from playwright_recipes.checkout_ui import validate_checkout_ui
            from order_components import OrderComponentError
            payload = s.get('payload')
            try:
                validate_checkout_ui(payload)
            except OrderComponentError as exc:
                raise Stop(str(exc)) from None
            if any(payload.get(k) != job[k] for k in ('location_id','location_name','start_url')):
                raise Stop('Native checkout UI payload belongs to another location/editor')
        if s['action']=='native_checkout':
            from playwright_recipes.pages_checkout import validate_checkout_inputs, load_checkout_capture
            from order_components import OrderComponentError
            try:
                validate_checkout_inputs(s.get('payload'))
            except OrderComponentError as exc:
                raise Stop(str(exc)) from None
            payload = s['payload']
            capture = Path(payload['adapter_capture'])
            if not capture.is_absolute():
                capture = base / capture
            try:
                load_checkout_capture(capture, location_id=job['location_id'], page_id=payload['page_id'])
            except OrderComponentError as exc:
                raise Stop(str(exc)) from None
            s['_input_dir'] = str(base.resolve())
        if s['action']=='native_dynamic_meeting_location':
            from playwright_recipes.meeting_dynamic import validate_inputs
            if set(s) != {'id', 'action', 'payload'}:
                raise Stop('Native dynamic room requires only its explicit bound payload')
            payload = validate_inputs(s.get('payload'), require_fresh=False)
            if any(payload[key] != job[key] for key in ('location_id', 'location_name', 'start_url')):
                raise Stop('Native dynamic room payload belongs to another location or editor')
        if s['action']=='meeting_cohosts':
            from playwright_recipes.meeting_cohosts import validate_write_inputs
            if set(s) != {'id', 'action', 'payload'}:
                raise Stop('Co-host writer requires only its explicit bound payload')
            payload = validate_write_inputs(s.get('payload'))
            if set(payload).intersection({'id', 'action', '_context'}):
                raise Stop('Co-host payload must not override runner metadata')
            if any(payload[key] != job[key] for key in ('location_id', 'location_name', 'start_url')):
                raise Stop('Co-host payload belongs to a different location or origin')
        if s['action']=='meeting':
            s['_context'] = {k:job[k] for k in ('location_id','location_name','start_url')}
            from playwright_recipes.meetings import validate_room
            validate_room({**s, **s['_context']})
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
            if 'require_new' in s and s['require_new'] is not True:
                raise Stop('An explicit require_new assessment guard must be true')
            if s.get("kind") not in ("survey", "quiz"):
                raise Stop("assessment kind must be survey or quiz")
            if not isinstance(s.get('standard_fields',[]),list) or any(q not in ("Email", "First Name", "Last Name", "Full Name", "Phone") for q in s.get("standard_fields", [])):
                raise Stop("Use options with a captured Add Object Fields recipe and Skill 44 dependency receipt for custom questions")
        if s["action"] == "form_css":
            if type(s.get("radius", 12)) is not int or not 0 <= s.get("radius",12) <= 32:
                raise Stop("Form corner radius must be 0–32 px")
        if s['action'] == 'form_settings':
            settings = s.get('settings')
            if not isinstance(settings, dict) or not settings:
                raise Stop('Supply explicit form settings')
            if any(key not in FORM_SETTINGS or type(value) is not bool for key, value in settings.items()):
                raise Stop('Unknown setting or non-boolean setting value')
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
            mutations = [i for i, option in enumerate(s['steps']) if not option['action'].startswith('expect_')]
            if mutations and not any(option['action'].startswith('expect_') for option in s['steps'][mutations[-1]+1:]):
                raise Stop('Recorded options require read-back after their last mutation')
        if s["action"] == "community":
            if len(prepared['steps']) != 1:
                raise Stop('Community creation must reconcile its native identity before any later operation')
            context = {key:job[key] for key in ('location_id', 'location_name', 'start_url')}
            if '_context' in s and s['_context'] != context:
                raise Stop('Community creation context belongs to a different job')
            s['_context'] = context
            from playwright_recipes.community_creation import validate
            validate(s)
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
    """Bind the shell identity to its URL and wait for the route's own builder.

    Editor hydration is asynchronous. An iframe absent at DOMContentLoaded must
    never switch an editor route into the dashboard's workspace-name guard.
    """
    requested = urlparse(job['start_url'])
    location = re.compile(r'/(?:v2/)?location/' + re.escape(job['location_id']) + r'(?:/|$)')
    requested_family = location.split(requested.path, maxsplit=1)[-1].strip('/').split('/', 1)[0]
    bound_editor = requested_family in ('form-builder-v2', 'survey-builder-v2', 'quiz-builder-v2', 'page-builder')

    def identity():
        current = urlparse(page.url)
        if (current.scheme, current.netloc) != (requested.scheme, requested.netloc):
            raise Stop('Unexpected app origin')
        if not location.search(current.path):
            raise Stop('Wrong tenant or authentication expired')
        if bound_editor and current.path.rstrip('/') != requested.path.rstrip('/'):
            raise Stop('Current editor belongs to a different requested object')
        return current.path

    path = identity()
    relative = location.split(path, maxsplit=1)[-1]
    route = relative.strip('/').split('/', 1)[0]
    editors = {
        'form-builder-v2': 'form-builder-app',
        'survey-builder-v2': 'survey-builder-app',
        'quiz-builder-v2': 'quiz-builder-app',
        'page-builder': 'funnel-builder',
    }
    expected = editors.get(route)
    if expected:
        selector = 'iframe[name="' + expected + '"]'
        target = page.locator(selector)

        def builder_identity():
            current = identity()
            if location.split(current, maxsplit=1)[-1].strip('/').split('/', 1)[0] != route:
                raise Stop('Editor route changed during hydration')
            for name in editors.values():
                if name != expected and page.locator('iframe[name="' + name + '"]').count():
                    raise Stop('Unexpected builder iframe for editor route')
            if target.count() > 1:
                raise Stop('Expected builder iframe is ambiguous')

        builder_identity()
        try:
            target.wait_for(state='visible', timeout=45000)
        except Exception:
            # Prefer the exact identity failure if navigation changed while the
            # iframe was loading. Do not leak raw Playwright error/page text.
            builder_identity()
            raise Stop('Expected editor iframe did not hydrate') from None
        builder_identity()
        if target.count() != 1:
            raise Stop('Expected editor iframe is missing')
        return
    # Dashboard and lists prove their visible account name. The presence of an
    # unrelated iframe does not bypass this guard.
    course = re.fullmatch(r'/v2/location/' + re.escape(job['location_id'])
        + r'/memberships/courses/themes-overview/([A-Za-z0-9_-]+)/edit/template/([A-Za-z0-9_-]+)', path)
    if course:
        from urllib.parse import parse_qsl
        query = parse_qsl(requested.query, keep_blank_values=True)
        expected_query = [('view', 'manager'), ('sub_view', 'customize'), ('product_id', course[1])]
        template_ids = ({job['template_id']} if 'template_id' in job else
            {step.get('payload', {}).get('template_id') for step in job.get('steps', [])
             if step.get('action') == 'native_course_theme'})
        if (requested.path != '/v2/location/' + job['location_id']
                + '/memberships/courses/course-creator-studio'
                or sorted(query) != sorted(expected_query)
                or template_ids != {course[2]} or urlparse(page.url).query or urlparse(page.url).fragment):
            raise Stop('Course editor does not match the requested course/template identity')
        page.get_by_placeholder('Template title', exact=True).wait_for(state='visible', timeout=45000)
        if (page.get_by_placeholder('Template title', exact=True).count() != 1
                or page.get_by_role('button', name='Activate Template', exact=True).count() != 1):
            raise Stop('Course template editor did not hydrate its captured controls')
        identity()
        return
    workspace = page.get_by_role('region', name='Workspace navigation', exact=True)
    group = workspace.get_by_role('group', name=job['location_name'], exact=True)
    switcher_manager = requested.path.endswith((
        '/memberships/courses/course-creator-studio',
        '/memberships/communities/community-groups'))
    if switcher_manager or group.count() == 0:
        switcher = workspace.get_by_role('button', name=re.compile(r'^Switch account from '))
        switcher.wait_for(state='visible', timeout=45000)
        if (switcher.count() != 1 or not switcher.is_visible()
                or switcher.get_attribute('aria-label') != 'Switch account from ' + job['location_name']):
            raise Stop('Workspace switcher belongs to another account')
        identity()
        return
    group.wait_for(state='visible', timeout=45000)
    identity()


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
    # A debounced list can retain the previous query's empty-state or initial
    # rows after fill. Only exact visible evidence for this current query can
    # establish absence; generic zero counts never authorize a create.
    def current_result():
        if search.count() != 1 or search.input_value() != name:
            return None
        count = cell.count()
        if count > 1:
            raise Stop("Duplicate names; supply an explicit target through the existing inventory router")
        if count:
            return 'found' if cell.is_visible() else None
        native_empty = page.get_by_text("No results found for '" + name + "'", exact=True)
        form_empty = page.get_by_text('No items found', exact=True)
        form_query = page.get_by_text('Your search “' + name + '” did not match any items. Please try again.', exact=True)
        if visible(native_empty) or (visible(form_empty) and visible(form_query)):
            # Recheck the textbox after reading the empty-state. Hydration or
            # user input must not turn stale absence into permission to create.
            return 'absent' if search.count() == 1 and search.input_value() == name else None
        return None
    wait_until(lambda: current_result() is not None,
               "Search absence could not be proven; refusing duplicate creation")
    result = current_result()
    if result is None:
        raise Stop('Search changed before its result could be bound; reconcile before creation')
    return cell if result == 'found' else None


_FRESH_CONTAINER = object()


class _FreshContainerContext:
    def __init__(self, page, surface, url):
        self.page, self.surface, self.url = page, surface, url
        self.used = False
        self.proof = _FRESH_CONTAINER


class _ContainerOutcome(dict):
    """Minimal serializable receipt plus nonserializable in-memory provenance."""
    def __init__(self, value, *, fresh_container=None):
        super().__init__(value)
        self.fresh_container = fresh_container


def ensure_container(page, step):
    area = "funnels" if step["surface"] == "funnel" else "websites"
    cell = exact_search(page, area, step["name"])
    created = False
    if cell is not None:
        click(cell.get_by_text(step["name"], exact=True))
    else:
        if not step.get("allow_creation"):
            raise Stop("Container is absent and creation was not requested")
        noun = step["surface"]
        create = page.get_by_role("button", name=f"New {noun}", exact=True)
        # Empty search results render a duplicate New website/funnel action.
        # The captured toolbar ID and exact name must identify one control.
        create = page.locator('#create-new-button').and_(create)
        click(create)
        dialog = page.get_by_role("dialog")
        fill(dialog.get_by_role("textbox", name=f"e.g. Sales {noun}", exact=True), step["name"])
        click(dialog.get_by_role("button", name="Create", exact=True))
        created = True
    page.get_by_role("button", name="Share " + step["surface"], exact=True).wait_for(state="visible", timeout=45000)
    return _ContainerOutcome({"container_url": page.url, "name": step["name"]},
        fresh_container=_FreshContainerContext(page, step['surface'], page.url) if created else None)


def _funnel_page_target(page, name, *, fresh_container=None):
    """Select one captured navigation card, then verify its independent detail.

    The page name appears twice in the native panel: navigation and detail.
    Whole-panel text counts cannot distinguish duplicate steps from that normal
    shape. Keep the navigation inventory and the selected detail separate.
    """
    url = urlparse(page.url)
    prefix = re.match(r'(/v2/location/[A-Za-z0-9_-]+/funnels-websites/funnels/[A-Za-z0-9_-]+)(?:/|$)', url.path)
    if not prefix or url.query or url.fragment:
        raise Stop('Funnel page inventory requires the captured container route')
    listing = page.locator('.steps-list')
    if listing.count() != 1:
        raise Stop('Captured funnel page inventory is unavailable; reconcile before creation')
    inventory = page.locator('.steps-list #step-container')
    if not inventory.count():
        _fresh_empty_funnel(page, fresh_container)
        return None
    if not listing.is_visible():
        raise Stop('Captured funnel page inventory is unavailable; reconcile before creation')
    cards = inventory.filter(has=page.get_by_text(name, exact=True))
    if cards.count() > 1:
        raise Stop('Duplicate funnel page names require explicit inventory reconciliation')
    if not cards.count():
        if page.get_by_text(name, exact=True).count():
            raise Stop('Funnel page name exists outside the captured navigation inventory')
        return None
    click(cards)
    detail = page.locator('#funnel-step-details')
    title = detail.get_by_text(name, exact=True)
    try:
        title.wait_for(state='visible', timeout=45000)
    except Exception:
        raise Stop('Selected funnel page detail did not confirm the requested page') from None
    current = urlparse(page.url)
    selected = re.fullmatch(re.escape(prefix.group(1))
        + r'/steps/([A-Za-z0-9_-]+)/overview/?', current.path)
    if (current.scheme != url.scheme or current.netloc != url.netloc
            or current.query or current.fragment or not selected):
        raise Stop('Funnel page selection changed location or container')
    if detail.count() != 1 or title.count() != 1:
        raise Stop('Selected funnel page detail is missing or ambiguous')
    edits = detail.get_by_role('button', name='Edit', exact=True)
    if edits.count() != 1:
        raise Stop('Selected funnel page has ambiguous variant Edit controls; capture required')
    return edits


def _fresh_context(page, context, surface):
    # Only this invocation's actual Create outcome can attest a new container.
    # A JSON flag, persisted receipt or another Page cannot provide this proof.
    if (not isinstance(context, _FreshContainerContext)
            or context.proof is not _FRESH_CONTAINER or context.used
            or context.page is not page or context.surface != surface
            or context.url != page.url):
        raise Stop('Empty ' + surface + ' inventory requires a fresh native creation proof or reconciliation')


def _fresh_empty_funnel(page, context):
    _fresh_context(page, context, 'funnel')
    root = page.locator('#steps-tab')
    sidebar = root.locator('#steps-sidebar.steps-sidebar')
    listing = sidebar.locator('.steps-list')
    add = sidebar.locator('#add-step').and_(
        sidebar.get_by_role('button', name='Add new step or import', exact=True))
    empty = root.locator('.funnel-step-details').get_by_text(
        'Get started by adding a new step!', exact=True)
    if (root.count() != 1 or sidebar.count() != 1 or listing.count() != 1
            or listing.evaluate('el => el.children.length') != 0
            or add.count() != 1 or not add.is_visible()
            or empty.count() != 1 or not empty.is_visible()):
        raise Stop('Captured empty funnel inventory changed; reconcile before creation')


def _fresh_empty_website(page, context):
    _fresh_context(page, context, 'website')
    root = page.locator('#steps-tab .hl_funnels--website-pages')
    if root.count() != 1 or not root.is_visible():
        raise Stop('Captured empty website container is unavailable or ambiguous')
    add = root.locator('#add-step').and_(root.get_by_role('button', name='Add new page', exact=True))
    grid = root.locator('div.flex.flex-wrap[ghostclass="webinar-drag-ghost"]')
    if (add.count() != 1 or not add.is_visible() or grid.count() != 1
            or grid.evaluate('el => el.children.length') != 0):
        raise Stop('Captured empty website inventory changed; reconcile before creation')


def _website_page_target(page, name, *, fresh_container=None):
    """Bind Edit to the captured website card containing the exact heading."""
    url = urlparse(page.url)
    if (not re.fullmatch(r'/v2/location/[A-Za-z0-9_-]+/funnels-websites/websites/[A-Za-z0-9_-]+/pages/?', url.path)
            or url.query or url.fragment):
        raise Stop('Website page inventory requires the captured container route')
    inventory = page.locator('.page-card')
    if not inventory.count():
        _fresh_empty_website(page, fresh_container)
        return None
    heading = page.get_by_role('heading', name=name, exact=True)
    cards = inventory.filter(has=heading)
    if cards.count() > 1:
        raise Stop('Duplicate website page names require explicit inventory reconciliation')
    if not cards.count():
        if heading.count():
            raise Stop('Website page name exists outside the captured card inventory')
        return None
    if cards.get_by_role('heading', name=name, exact=True).count() != 1:
        raise Stop('Website page card has an ambiguous name')
    edits = cards.get_by_role('button', name='Edit', exact=True)
    if edits.count() != 1:
        raise Stop('Website page card has an ambiguous Edit control')
    return edits


def ensure_page(page, step, *, fresh_container=None):
    surface = step['surface']
    if surface == 'funnel':
        edit = _funnel_page_target(page, step['name'], fresh_container=fresh_container)
    else:
        edit = _website_page_target(page, step['name'], fresh_container=fresh_container)
    if edit is not None:
        click(edit)
    else:
        if not step.get('allow_creation'):
            raise Stop('Page absent and creation was not requested')
        if isinstance(fresh_container, _FreshContainerContext):
            fresh_container.used = True
        add_name = 'Add new step or import' if surface == 'funnel' else 'Add new page'
        add = page.locator('#steps-tab #add-step').and_(
            page.get_by_role('button', name=add_name, exact=True))
        click(add)
        dialog = page.get_by_role('dialog')
        fill(dialog.get_by_role('textbox', name='Name for page', exact=True), step['name'])
        fill(dialog.get_by_role('textbox', name='Path', exact=True), step['path'])
        click(dialog.get_by_role('button', name='Create funnel step' if surface == 'funnel' else 'Create new page', exact=True))
        blank = page.get_by_role('button', name='Create from blank', exact=True)
        click(blank)
    builder(page).get_by_role('button', name='Back', exact=True).wait_for(state='visible', timeout=45000)
    ai = builder(page).get_by_role('button', name='Close Ask AI', exact=True)
    if visible(ai):
        click(ai)
    return {'editor_url': page.url}


def full_width(frame, section_id=None):
    if section_id is not None and not re.fullmatch(r'[A-Za-z0-9_-]+', section_id):
        raise Stop('Section identity is malformed')
    sections = frame.locator(".c-section" + ('[id='+json.dumps(section_id)+']' if section_id else ''))
    if sections.count()!=1:
        raise Stop('Width mutation requires one inventoried target section; refusing to alter unrelated sections')
    if not sections.count():
        raise Stop("No section to configure")
    for n in range(sections.count()):
        section = sections.nth(n)
        # The row toolbar overlaps the section's left edge. Hover the middle
        # of the section's captured top padding to expose the SECTION toolbar.
        box = section.bounding_box()
        if not box:
            raise Stop('Target section has no visible bounds')
        section.hover(position={'x':box['width']/2, 'y':5})
        settings = frame.locator('.ui-section.hovered [title="Open Settings"]:visible')
        click(settings)
        width = frame.locator('#width')
        width.wait_for(state='visible', timeout=45000)
        if width.inner_text().strip() != 'Full':
            click(width)
            click(frame.locator('.n-base-select-option').get_by_text('Full', exact=True))
        wait_until(lambda:'fullSection' in (section.get_attribute('class') or ''), 'Section did not become Full width')
        group = frame.locator(".toggle-group").filter(has_text="Allow Rows to take entire width")
        toggle = group.locator(".toggle-btn")
        if "toggle-btn-end" not in (toggle.get_attribute("class") or ""):
            click(group.locator(".toggle"))
        if "toggle-btn-end" not in (toggle.get_attribute("class") or ""):
            raise Stop("Entire-width rows did not enable")
        if width.inner_text().strip() != 'Full':
            raise Stop('Full width dropdown readback failed')


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
    before_ids = set(frame.locator('.c-custom-code').evaluate_all('(els)=>els.map(el=>el.id)'))
    target_info = None
    section_id = step.get('section_id')
    blank = frame.get_by_role("button", name="Blank Section", exact=True)
    if not visible(blank) and frame.locator('.c-section').count()!=1 and not step.get('element_id'):
        raise Stop('Existing multi-section page needs a recorded target profile before any code or width mutation')
    if visible(blank):
        click(blank)
        full_width(frame)
        add_tile(frame, "Rows", "1 Column")
        add_tile(frame, "Elements", "Code")
        fill(frame.get_by_role("textbox", name="Element name", exact=True), "ZHC Code " + step["id"])
    elif step.get('element_id'):
        if step.get('append'):
            raise Stop('An existing code identity is an update, not an append target')
        from playwright_recipes.pages_checkout import resolve_code_target
        target_info = resolve_code_target(frame, step['element_id'], step.get('expected_name','ZHC Code '+step['id']), section_id)
        section_id = target_info['section_id']
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
    full_width(frame, section_id)
    save_page(frame)
    href = frame.locator('a[href*="/preview/"]').get_attribute("href")
    check = page.context.new_page()
    try:
        response = check.goto(href, wait_until="domcontentloaded", timeout=45000)
        if response is None or response.status != 200:
            raise Stop("Preview did not return HTTP 200")
        check.get_by_text(step["marker"], exact=False).first.wait_for(state="visible", timeout=45000)
        after_ids = set(frame.locator('.c-custom-code').evaluate_all('(els)=>els.map(el=>el.id)'))
        new_ids = after_ids-before_ids
        native_id = target_info['element_id'] if target_info else (next(iter(new_ids)) if len(new_ids)==1 else step.get('element_id'))
        return {"editor_url":page.url, "preview_url":check.url, "rendered_marker":step["marker"], "html_sha256":step["html_sha256"], "status":"RENDERED", 'element_id':native_id, 'section_id':section_id}
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
        if step.get('require_new'):
            raise Stop('New assessment creation refuses an existing exact-name owner')
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
            add_page = frame.get_by_role('button',name='Add Slide' if kind=='survey' else 'Add Page',exact=True)
            if add_page.count() not in (1,index):
                raise Stop('Assessment page insertion controls changed')
            click(add_page.nth(add_page.count()-1))
            click(frame.get_by_role('button',name='Add '+kind.title()+' Element',exact=True))
        drag_field(page,frame,name)
        frame.get_by_placeholder({'Email':'your@email.com','First Name':'Enter your first name','Last Name':'Enter your last name','Phone':'+1 (555) 000-0000','Full Name':'Enter your full name'}[name],exact=True).wait_for(state='visible',timeout=45000)
    close=frame.get_by_role('dialog').get_by_role('button',name='Close',exact=True)
    if visible(close):
        click(close)
    click(frame.get_by_role('button',name='Save',exact=True))
    frame.get_by_role('button',name='Save',exact=True).wait_for(state='visible',timeout=45000)
    return {'status':'ASSESSMENT_REUSED' if reused else 'ASSESSMENT_SAVE_SUBMITTED','kind':kind,'editor_url':page.url,'independent_readback':'REQUIRED','scoring_and_branches':'Use captured options recipe; no submission was made'}


FORM_SETTINGS = {
    'save_progress': (1, 'Save progress for forms'),
    'submission_document': (2, 'Generate submission document'),
    'recommendations': (3, 'Show form recommendations'),
    'sticky_contact': (4, 'Sticky Contact'),
    'conversation_on_submission': (5, 'Create Conversation on Submission'),
    'capture_timezone': (6, 'Enable Timezone'),
    'gdpr_font': (7, 'Use GDPR Compliant Font'),
}


def form_notifications(page, step):
    from playwright_recipes.form_notifications import configure_notifications
    return configure_notifications(page, step)


def form_settings(page, step):
    """Settings captured from the native form builder on 2026-11-08.

    Require both the captured count and each row label before any click. Reopen
    the editor to prove persisted settings; do not trust a successful save click.
    Scheduling has additional dependent fields and is deliberately excluded.
    """
    frame = form_builder(page)
    close = frame.get_by_role('dialog').get_by_role('button', name='Close', exact=True)
    if visible(close):
        click(close)
    click(frame.get_by_role('tab', name='Settings', exact=True))

    def controls():
        switches = frame.get_by_role('switch')
        wait_until(lambda: switches.count() in (8, 9), 'Form settings control count changed')

        def row_text(control):
            # The scheduler toggle is nested one level deeper than ordinary
            # switches. Only consider a containing row that owns one switch.
            return control.evaluate('''el => {
                for (const row of [el.parentElement, el.parentElement?.parentElement]) {
                    if (row && row.querySelectorAll('[role="switch"]').length === 1
                            && row.textContent.trim()) return row.textContent;
                }
                return '';
            }''')

        scheduler = switches.nth(0)
        if 'Schedule form visibility' not in row_text(scheduler):
            raise Stop('Form scheduler row identity changed; capture required')
        scheduling = scheduler.get_attribute('aria-checked')
        if scheduling not in ('true', 'false'):
            raise Stop('Form scheduler state is not exposed')
        offset = int(scheduling == 'true')
        if switches.count() != 8 + offset:
            raise Stop('Form settings count disagrees with scheduler state')
        protected = {'schedule_visibility': scheduling}
        if offset:
            branding = switches.nth(1)
            if 'Agency branding' not in row_text(branding):
                raise Stop('Scheduled form branding row identity changed; capture required')
            state = branding.get_attribute('aria-checked')
            if state not in ('true', 'false'):
                raise Stop('Scheduled form branding state is not exposed')
            protected['agency_branding'] = state
        selected = {}
        for key in step['settings']:
            index, label = FORM_SETTINGS[key]
            frame.get_by_text(label, exact=True).wait_for(state='visible', timeout=45000)
            control = switches.nth(index + offset)
            text = row_text(control)
            if label not in text:
                raise Stop('Form settings order changed; capture required')
            selected[key] = control
        return selected, protected

    selected, protected = controls()
    for key, value in step['settings'].items():
        loc = selected[key]
        expected = str(value).lower()
        if loc.get_attribute('aria-checked') != expected:
            click(loc)
        wait_until(lambda: loc.get_attribute('aria-checked') == expected, 'Setting did not change')
    save_page_url = page.url
    click(frame.get_by_role('button', name='Save', exact=True))
    # GHL Save stays mounted; wait for the visible save operation to finish.
    wait_until(lambda: frame.get_by_role('button', name='Save', exact=True).is_enabled(), 'Form save still busy')
    page.reload(wait_until='domcontentloaded', timeout=45000)
    if page.url != save_page_url:
        raise Stop('Form editor changed while reopening')
    frame = form_builder(page)
    close = frame.get_by_role('dialog').get_by_role('button', name='Close', exact=True)
    if visible(close):
        click(close)
    click(frame.get_by_role('tab', name='Settings', exact=True))
    selected, reopened_protected = controls()
    if reopened_protected != protected:
        raise Stop('Form scheduling or branding changed while saving ordinary settings')
    for key, value in step['settings'].items():
        if selected[key].get_attribute('aria-checked') != str(value).lower():
            raise Stop('Form setting was not persisted: ' + key)
    return {'status': 'FORM_SETTINGS_PERSISTED', 'settings': step['settings'], 'editor_url': page.url}


def meeting(page, step):
    from playwright_recipes.meetings import create_room, update_room
    inputs = {**step, **step['_context']}
    if step.get('expected_room_id'):
        return update_room(page, inputs, expected_room_id=step['expected_room_id'])
    return create_room(page, inputs)


def native_dynamic_meeting_location(page, step):
    from playwright_recipes.meeting_dynamic import configure
    return configure(page, step['payload'])


def meeting_cohosts(page, step):
    from playwright_recipes.meeting_cohosts import configure
    return configure(page, step['payload'])


def form_submission(page, step):
    from playwright_recipes.form_submission import configure
    return configure(page, step)


def native_form_css(page, step):
    from playwright_recipes.assessments import configure_css
    return configure_css(page, step)


def native_form_schedule(page, step):
    from playwright_recipes.form_schedule import configure
    return configure(page, step)


def native_course_theme(page, step):
    from playwright_recipes.course_theme import configure
    return configure(page, step)


def native_fields(page, step):
    from playwright_recipes.assessments import configure_fields
    return configure_fields(page, step)


def native_address_parent(page, step):
    from playwright_recipes.address_parent import configure
    return configure(page, step)


def native_address_fields(page, step):
    from playwright_recipes.forms_advanced import configure
    return configure(page, step)


def native_form_consent(page, step):
    from playwright_recipes.forms_advanced import configure_consent
    return configure_consent(page, step)


def native_large_text_fields(page, step):
    from playwright_recipes.large_text_fields import configure
    return configure(page,step)

def native_dropdown_fields(page, step):
    from playwright_recipes.dropdown_fields import configure
    return configure(page,step)

def quiz_short_answers(page, step):
    from playwright_recipes.quiz_text_questions import configure
    return configure(page,step)

def quiz_multiple_choices(page, step):
    from playwright_recipes.quiz_choice_questions import configure
    return configure(page,step)

def quiz_written_answers(page, step):
    from playwright_recipes.quiz_written_questions import configure
    return configure(page,step)

def native_object_fields(page, step):
    from playwright_recipes.forms_advanced import configure_object_fields
    return configure_object_fields(page, step)


def native_split_variant(page, step):
    from playwright_recipes.split_variant import configure
    return configure(page, step)

def native_survey_multiline_configuration(page,step):
    from playwright_recipes.survey_multiline_configuration import configure
    return configure(page,step)

def native_survey_text_configuration(page,step):
    from playwright_recipes.survey_text_configuration import configure
    return configure(page,step)

def native_survey_object_fields(page, step):
    from playwright_recipes.survey_fields import configure
    return configure(page, step)


def native_field_placement(page, step):
    from playwright_recipes.field_placement import configure
    return configure(page, step)


def native_condition(page, step):
    from playwright_recipes.assessments import configure_condition
    return configure_condition(page, step)


def quiz_picture_choices(page, step):
    from playwright_recipes.quiz_picture_questions import configure
    return configure(page, step)


def quiz_configuration(page, step):
    from playwright_recipes.quiz_ui import configure
    return configure(page, step)


def native_order_confirmation(page, step):
    from playwright_recipes.form_order_confirmation import configure
    return configure(page, step)


def native_form_embed(page, step):
    from playwright_recipes.form_embed import configure
    return configure(page, step)


def native_form_tracking(page, step):
    from playwright_recipes.form_tracking import configure
    return configure(page, step)


def native_course_block_media(page, step):
    from playwright_recipes.course_block_media import configure
    return configure(page, step)


def native_condition_outcomes(page, step):
    from playwright_recipes.form_condition_outcomes import configure
    return configure(page,step)

def native_condition_stack(page, step):
    from playwright_recipes.form_condition_stack import configure
    return configure(page, step)


def native_course_theme_media(page, step):
    from playwright_recipes.course_theme_media import configure
    return configure(page, step)


def native_course_video_blocks(page, step):
    from playwright_recipes.course_video_blocks import configure
    return configure(page,step)

def native_course_image_blocks(page, step):
    from playwright_recipes.course_image_blocks import configure
    return configure(page,step)

def native_course_section_media(page, step):
    from playwright_recipes.course_section_media import configure
    return configure(page,step)

def native_course_text_blocks(page, step):
    from playwright_recipes.course_text_blocks import configure
    return configure(page,step)

def native_course_blocks(page, step):
    from playwright_recipes.course_blocks import configure
    return configure(page, step)


def native_condition_group(page, step):
    from playwright_recipes.form_conditions import configure
    return configure(page, step)


def quiz_results(page, step):
    from playwright_recipes.quiz_results import configure
    return configure(page, step)


def survey_configuration(page, step):
    from playwright_recipes.survey_ui import configure
    return configure(page, step)



def native_checkout_ui(page, step):
    from playwright_recipes.checkout_ui import configure_native_checkout_ui
    result = configure_native_checkout_ui(page, step['payload'])
    result['checkout_ready'] = False
    result['payment_verified'] = False
    return result


def native_checkout(page, step):
    from playwright_recipes.pages_checkout import configure_native_checkout
    result = configure_native_checkout(page, step['payload'], input_dir=step.get('_input_dir','.'))
    result['checkout_ready'] = False
    result['independent_readback'] = 'REQUIRED'
    return result


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
    context = step.get('_context')
    if not isinstance(context, dict) or set(context) != {'location_id', 'location_name', 'start_url'}:
        raise Stop('Recorded options require the parent runner identity context')
    for action in step['steps']:
        assert_tenant(page, context)
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
        assert_tenant(page, context)
    return {'status':'RECORDED_OPTIONS_EXECUTED','count':len(step['steps']),
            'capture_source':step['capture_source'], 'independent_readback':'REQUIRED'}


def community(page, step):
    from playwright_recipes.community_creation import configure
    return configure(page, step)


def community_branding(page, step, *, portal_context=None, evidence_root=None):
    if portal_context is None or evidence_root is None:
        raise Stop('Community Branding requires a live same-session portal context')
    from playwright_recipes.community_branding import run_branding, validate_inputs, configuration_hash, SLOTS
    from playwright_recipes.community_portal import _portal
    plan = validate_inputs(step['payload'])
    result = run_branding(page, plan, evidence_root, portal_context=portal_context)
    if not isinstance(result, dict):
        raise Stop('Community Branding returned no bound outcome')
    previews = result.get('preview_sha256')
    if (not isinstance(previews, dict) or set(previews) != set(SLOTS)
            or any(value is not None and (not isinstance(value, str)
                or not re.fullmatch(r'[a-f0-9]{64}', value)) for value in previews.values())):
        raise Stop('Community Branding preview evidence is malformed')
    changed = {asset['slot'] for asset in plan['branding']['images']}
    for slot, previous in plan['branding']['expected'].items():
        before = sha(previous) if previous is not None else None
        if (slot in changed and (previews[slot] is None or previews[slot] == before)
                or slot not in changed and previews[slot] != before):
            raise Stop('Community Branding preview changes do not match requested slots')
    _, slug = _portal(plan['portal_url'])
    expected = {'status':'NEEDS_VERIFICATION', 'location_id':plan['location_id'],
        'objects':[{'kind':'community','id':slug}], 'configuration_sha256':configuration_hash(plan),
        'controls_verified':True, 'independent_readback':'VERIFIED',
        'branding_slots':[asset['slot'] for asset in plan['branding']['images']],
        'preview_sha256':previews,
        'source_sha256':{asset['slot']:asset['sha256'] for asset in plan['branding']['images']},
        'behavior_verified':False, 'functional_verified':False, 'verification_required':True,
        'group_activation_attempted':False, 'communication_attempted':False,
        'identity_source':'same_session_authenticated_read_and_modern_branding_previews'}
    if (set(result) - set(expected) not in (set(), {'replayed'})
            or 'replayed' in result and result['replayed'] is not True
            or any(result.get(key) != value or type(result.get(key)) is not type(value)
                   for key,value in expected.items())):
        raise Stop('Community Branding result does not bind its exact configuration and pending proof')
    return {**expected, **({'replayed':True} if result.get('replayed') is True else {})}


def community_courses(page, step, *, portal_context=None, evidence_root=None):
    if portal_context is None or evidence_root is None:
        raise Stop('Community course associations require the live same-session portal context')
    from playwright_recipes.community_courses import run_courses, validate_inputs, _receipt
    plan = validate_inputs(step['payload'])
    result = run_courses(page, plan, evidence_root, portal_context=portal_context)
    if (not isinstance(result, dict)
            or type(result.get('reused')) is not bool or type(result.get('share_post_skipped')) is not bool
            or result['reused'] and result['share_post_skipped']):
        raise Stop('Community course outcome has invalid reuse/communication proof')
    expected = _receipt(plan, reused=result['reused'], skipped=result['share_post_skipped'])
    replayed = result.get('replayed')
    if (set(result) - set(expected) not in (set(), {'replayed'})
            or 'replayed' in result and replayed is not True
            or any(result.get(key) != value or type(result.get(key)) is not type(value)
                   for key,value in expected.items())):
        raise Stop('Community course outcome does not bind its exact requested IDs and proof')
    return {**expected, **({'replayed':True} if replayed is True else {})}



def community_event_room(page, step, *, portal_context=None, evidence_root=None):
    """Keep immediate native room creation inside its exact portal journal/context."""
    if portal_context is None or evidence_root is None:
        raise Stop('Community event room requires the live same-session event portal context')
    from playwright_recipes.community_event_meeting import run_event, validate_inputs, _receipt, _room_id
    plan = validate_inputs(step['payload'])
    result = run_event(page, plan, evidence_root, portal_context=portal_context)
    if (not isinstance(result, dict) or not isinstance(result.get('room_id'), str)
            or not re.fullmatch(r'[a-f0-9]{24}', result['room_id'])):
        raise Stop('Community event outcome has an invalid native room identity')
    changed = plan['expected']['form']['location_type'] != 'Live Room'
    if not changed and result['room_id'] != _room_id(plan['expected']['form']['location_url'], plan):
        raise Stop('Community event outcome changed the requested reused room identity')
    expected = _receipt(plan, result['room_id'], changed=changed)
    if (set(result) - set(expected) not in (set(), {'replayed'})
            or 'replayed' in result and result['replayed'] is not True
            or any(result.get(key) != value or type(result.get(key)) is not type(value)
                   for key,value in expected.items())):
        raise Stop('Community event outcome does not bind exact IDs/configuration/pending proof')
    return {**expected, **({'replayed':True} if result.get('replayed') is True else {})}


def community_channels(page, step, *, portal_context=None, evidence_root=None):
    """Explicit portal handler; global app/tenant guards are not relaxed."""
    if portal_context is None or evidence_root is None:
        raise Stop('Community channels require the authenticated portal host context')
    from playwright_recipes.community_portal import run_channels
    return run_channels(page, step['payload'], evidence_root,
                        portal_context=portal_context)


def community_details(page, step, *, portal_context=None, evidence_root=None):
    """Save authored portal details through the same authenticated host boundary."""
    if portal_context is None or evidence_root is None:
        raise Stop('Community details require the authenticated portal host context')
    from playwright_recipes.community_portal import run_details
    return run_details(page, step['payload'], evidence_root,
                       portal_context=portal_context)


def community_access(page, step, *, portal_context=None, evidence_root=None, access_authorization=None):
    """Keep access-expansion approval as an opaque live host capability."""
    if portal_context is None or evidence_root is None:
        raise Stop('Community access requires the authenticated portal host context')
    from playwright_recipes.community_access import run_access
    return run_access(page, step['payload'], evidence_root,
                      portal_context=portal_context, access_authorization=access_authorization)


def _text_equals(locator, text):
    return (locator.inner_text()).strip() == text


_PORTAL_ACTIONS = frozenset(('community_channels', 'community_details', 'community_access',
    'community_courses', 'community_branding', 'community_event_room'))


def _reject_portal_editor_jobs(job):
    if any(step.get('action') in _PORTAL_ACTIONS for step in job.get('steps', [])):
        raise Stop('Community portal jobs require caller-owned page/context through host.run_recipe')


_EDITOR_FOREIGN_JOURNALS = (
    'provider-state.json', 'community-portal-state.json', 'auth-stop.json',
    'delivery-state.json', 'calendar-delivery-state.json',
    'community-details-state.json', 'community-access-state.json', 'community-event-state.json',
)


def _reject_foreign_editor_journals(root):
    from playwright_recipes.evidence_lease import journal_present
    if (root / 'state.json').is_symlink():
        raise Stop('Evidence journal is a symlink; reconciliation required')
    # Foreign fingerprints never authorize an editor replay, even when their
    # bytes are malformed or report completion. A dangling journal symlink is
    # also retained evidence, not permission to start a different lane.
    if any(journal_present(root / name) for name in _EDITOR_FOREIGN_JOURNALS):
        raise Stop('Existing provider, API or portal outcome requires reconciliation before editor execution')


def run_on_page(page, job, evidence_root, *, contact_field_capability=None, radio_field_capability=None):
    _reject_portal_editor_jobs(job)
    from playwright_recipes.address_parent import preflight
    preflight(job)
    root = Path(evidence_root).resolve()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    from playwright_recipes.evidence_lease import open_lease
    _reject_foreign_editor_journals(root)
    fd = open_lease(root / '.runner.lock')
    provider_fd = None
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise Stop('This run is already executing; no concurrent writes allowed') from None
        provider_fd = open_lease(root / 'provider.lock')
        try:
            fcntl.flock(provider_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise Stop('A provider owns this evidence root; no editor write allowed') from None
        # Different lanes have different job fingerprints. A provider or portal
        # journal cannot authorize blindly replaying this job in the GHL editor,
        # even when its last reported outcome was completed or pending.
        _reject_foreign_editor_journals(root)
        if (root / 'handoff.json').exists() and not (root / 'state.json').exists():
            raise Stop('Editor recovery handoff has no journal; reconciliation required before execution')
        arguments = ({'contact_field_capability':contact_field_capability}
            if any(step['action'] == 'native_contact_field_chain' for step in job.get('steps', [])) else {})
        if any(step['action'] in ('native_survey_radio_creation','native_survey_creation') for step in job.get('steps', [])):
            arguments['radio_field_capability']=radio_field_capability
        return _run_on_page(page, job, root, **arguments)
    finally:
        if provider_fd is not None:
            os.close(provider_fd)
        os.close(fd)


def _run_on_page(page, job, evidence_root, *, contact_field_capability=None, radio_field_capability=None):
    """Host integration seam: use an already managed, signed-in Playwright Page.

    State records are intent-before-mutation. A crashed/uncertain step is never
    replayed automatically. The host inspects its read-back and resumes a new,
    explicitly reconciled job. No broad browser-state or secret-bearing trace
    is written; only minimal object identifiers and named outcomes.
    """
    _reject_portal_editor_jobs(job)
    from playwright_recipes.address_parent import preflight
    preflight(job)
    root = Path(evidence_root).resolve()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(root, 0o700)
    state_path = root / "state.json"
    fingerprint = sha(json.dumps(job, sort_keys=True))
    from playwright_recipes.evidence_lease import journal_present
    from playwright_recipes.editor_replay import completed_editor_replay
    if journal_present(state_path):
        replay = completed_editor_replay(state_path, job, fingerprint)
        assert_tenant(page, job)
        for step, row in zip(job['steps'], replay['results']):
            if step['action'] == 'native_split_variant':
                from playwright_recipes.split_variant import verify_completed
                verify_completed(page, step, row['result'])
        for item in replay['results']:
            if item['action']=='native_survey_multiline_configuration':
                from playwright_recipes.survey_multiline_configuration import verify
                step=next(step for step in job['steps'] if step['id']==item['id'])
                verify(page,step,item['result'])
            elif item['action']=='native_survey_creation':
                from playwright_recipes.survey_creation import verify
                step=next(step for step in job['steps'] if step['id']==item['id'])
                verify(page,step,item['result'])
        for step,row in zip(job['steps'],replay['results']):
            if (step['action']=='native_course_theme_media'
                    and 'background_removal' in step['payload']):
                from playwright_recipes.course_theme_media import verify_completed
                verify_completed(page,step,row['result'])
            if (step['action']=='native_course_block_media'
                    and 'remove_image' in step['payload']['custom_block_image']):
                from playwright_recipes.course_custom_image_removal import verify_completed
                verify_completed(page,step,row['result'])
            if step['action']=='native_course_video_blocks':
                from playwright_recipes.course_video_blocks import verify_completed
                verify_completed(page,step,row['result'])
        for step in job.get('steps', []):
            if step['action']=='native_address_parent':
                from playwright_recipes.address_parent import verify
                matching=[item['result'] for item in replay['results'] if item['id']==step['id']]
                if len(matching)!=1:raise Stop('Parent Address replay receipt identity is missing')
                verify(page,step,matching[0])
        return replay
    if any(step['action'] in ('native_survey_radio_creation','native_survey_creation') for step in job.get('steps', [])):
        from playwright_recipes.survey_radio_creation import validate_runtime
        validate_runtime(job,radio_field_capability)
    if any(step['action'] == 'native_contact_field_chain' for step in job.get('steps', [])):
        from playwright_recipes.contact_field_frontdoor import validate_runtime
        validate_runtime(job, contact_field_capability)
    assert_tenant(page, job)
    results = []
    fresh_container = None
    state = {"fingerprint":fingerprint, "location_id":job["location_id"], "status":"RUNNING", "results":results}
    handlers = {"native_survey_multiline_configuration":native_survey_multiline_configuration, "native_split_variant":native_split_variant, "container":ensure_container, "page":ensure_page, "html":install_html, "seo":seo, "checkout":checkout, "native_checkout":native_checkout, "native_checkout_ui":native_checkout_ui, "native_course_theme":native_course_theme, "native_course_blocks":native_course_blocks, "native_course_text_blocks":native_course_text_blocks, "native_course_section_media":native_course_section_media, "native_course_image_blocks":native_course_image_blocks, "native_course_video_blocks":native_course_video_blocks, "native_course_theme_media":native_course_theme_media, "native_course_block_media":native_course_block_media, "native_fields":native_fields, "native_field_placement":native_field_placement, "native_address_fields":native_address_fields, "native_address_parent":native_address_parent, "native_form_consent":native_form_consent, "native_object_fields":native_object_fields, "native_dropdown_fields":native_dropdown_fields, "native_large_text_fields":native_large_text_fields, "quiz_short_answers":quiz_short_answers, "quiz_multiple_choices":quiz_multiple_choices, "quiz_written_answers":quiz_written_answers, "quiz_picture_choices":quiz_picture_choices, "native_survey_object_fields":native_survey_object_fields, "native_survey_text_configuration":native_survey_text_configuration, "native_condition":native_condition, "native_condition_group":native_condition_group, "native_condition_stack":native_condition_stack, "native_condition_outcomes":native_condition_outcomes, "quiz_configuration":quiz_configuration, "quiz_results":quiz_results, "survey_configuration":survey_configuration, "survey_rule_stack":survey_configuration, "form":make_form, "form_css":form_css, "native_form_css":native_form_css, "native_form_schedule":native_form_schedule, "native_form_tracking":native_form_tracking, "native_form_embed":native_form_embed, "native_order_confirmation":native_order_confirmation, "form_submission":form_submission, "form_notifications":form_notifications, "form_settings":form_settings, "community":community,"assessment":assessment,"meeting":meeting,"meeting_cohosts":meeting_cohosts,"native_dynamic_meeting_location":native_dynamic_meeting_location,"options":options}
    for step in job["steps"]:
        assert_tenant(page, job)
        state["current_step"] = step["id"]
        state["current_step_status"] = "INTENT_RECORDED"
        secure_json(state_path, state)
        try:
            if step["action"] == "navigate":
                navigate(page, step["area"])
                result = {"area":step["area"]}
                fresh_container = None
            elif step["action"] == "page":
                result = ensure_page(page, step, fresh_container=fresh_container)
                fresh_container = None
            elif step['action'] == 'options':
                context = {key:job[key] for key in ('location_id', 'location_name', 'start_url')}
                if '_context' in step and step['_context'] != context:
                    raise Stop('Recorded options identity differs from its parent job')
                result = options(page, {**step, '_context':context})
                fresh_container = None
            elif step['action']=='native_quiz_creation':
                from playwright_recipes.quiz_creation import configure
                chain_root=root/'quiz-creation'
                if chain_root.is_symlink():raise Stop('Quiz creation evidence directory is a symlink')
                result=configure(page,step,chain_root)
                fresh_container=None
            elif step['action'] in ('native_survey_radio_creation','native_survey_creation'):
                from playwright_recipes.survey_radio_creation import configure
                chain_root=root/('survey-creation' if step['action']=='native_survey_creation' else 'survey-radio-creation')
                if chain_root.is_symlink():raise Stop('Survey creation evidence directory is a symlink')
                result=configure(page,step,chain_root,capability=radio_field_capability)
                fresh_container=None
            elif step['action'] == 'native_contact_field_chain':
                from playwright_recipes.contact_field_frontdoor import configure
                chain_root = root / 'contact-fields'
                if chain_root.is_symlink():
                    raise Stop('Contact chain evidence directory is a symlink')
                result = configure(page, step, chain_root, capability=contact_field_capability)
                fresh_container = None
            else:
                result = handlers[step["action"]](page, step)
                fresh_container = (result.fresh_container
                    if step["action"] == "container" and isinstance(result, _ContainerOutcome)
                    else None)
            if not isinstance(result, dict):
                raise Stop('Handler returned no structured outcome')
            if step['action'] in ('native_address_parent','native_split_variant','native_quiz_creation','native_survey_creation','native_survey_radio_creation','native_contact_field_chain','native_dropdown_fields','native_large_text_fields',
                    'quiz_short_answers','quiz_multiple_choices','quiz_written_answers','quiz_picture_choices',
                    'native_condition_stack','native_condition_outcomes','native_survey_text_configuration','native_survey_multiline_configuration',
                    'native_order_confirmation','native_course_blocks','native_course_theme_media','native_course_block_media','native_course_text_blocks','native_course_section_media','native_course_image_blocks','native_course_video_blocks') or (
                    step['action'] == 'community' and result.get('status') in (
                        'GROUP_CREATED_SLUG_IDENTIFIED','GROUP_REUSED_IDENTITY_CONFIRMED')):
                # Fresh execution and replay require the same complete, bound
                # proof. A familiar status alone cannot mark a write finished.
                from playwright_recipes.editor_replay import _result
                result = _result(step, result, job)
            status = result.get('status')
            completed = {
                'SPLIT_VARIANT_SAVED_AND_REOPENED', 'SPLIT_VARIANT_REUSED_AND_REOPENED',
                'CONTACT_FIELDS_SAVED_AND_REOPENED', 'SURVEY_RADIO_SAVED_AND_REOPENED', 'QUIZ_CREATED_SAVED_AND_REOPENED', 'SURVEY_CREATED_SAVED_AND_REOPENED',
                'RENDERED', 'SEO_RENDERED', 'COMPONENT_SAVED', 'SAVED_AND_REOPENED',
                'FORM_CSS_RENDERED', 'NATIVE_FORM_CSS_SAVED_AND_REOPENED', 'FORM_SETTINGS_PERSISTED',
                'FORM_SCHEDULE_SAVED_AND_REOPENED', 'COURSE_THEME_SAVED_AND_REOPENED', 'COURSE_VIDEO_BLOCKS_SAVED_AND_REOPENED',
                'ADDRESS_FIELDS_SAVED_AND_REOPENED', 'ADDRESS_PARENT_SAVED_AND_REOPENED', 'CONSENT_SAVED_AND_REOPENED',
                'OBJECT_FIELDS_SAVED_AND_REOPENED', 'SURVEY_OBJECT_FIELDS_SAVED_AND_REOPENED', 'SURVEY_TEXT_PROPERTIES_SAVED_AND_REOPENED', 'SURVEY_MULTILINE_PROPERTIES_SAVED_AND_REOPENED', 'ASSESSMENT_REUSED',
                'ASSESSMENT_SAVE_SUBMITTED', 'ROOM_SAVE_SUBMITTED',
                'DROPDOWN_FIELDS_SAVED_AND_REOPENED', 'LARGETEXT_FIELDS_SAVED_AND_REOPENED', 'QUIZ_SHORT_ANSWERS_SAVED_AND_REOPENED', 'QUIZ_MULTIPLE_CHOICES_SAVED_AND_REOPENED', 'QUIZ_WRITTEN_ANSWERS_SAVED_AND_REOPENED', 'QUIZ_PICTURE_CHOICES_SAVED_AND_REOPENED', 'RECORDED_OPTIONS_EXECUTED', 'GROUP_RETAINED_INACTIVE', 'GROUP_CREATED', 'GROUP_CREATED_PENDING_IDENTITY', 'GROUP_CREATED_SLUG_IDENTIFIED', 'GROUP_REUSED_IDENTITY_CONFIRMED',
                'FIELD_PROPERTIES_SAVED_AND_REOPENED', 'BUILTIN_FIELDS_SAVED_AND_REOPENED',
                'BUILTIN_FIELDS_REUSED_AND_REOPENED', 'CONDITION_SAVE_SUBMITTED', 'CONDITION_SAVED_AND_REOPENED',
                'QUIZ_CONFIGURATION_SAVED_AND_REOPENED', 'QUIZ_RESULTS_SAVED_AND_REOPENED', 'CONDITION_ALREADY_PRESENT',
                'FORM_SUBMISSION_SAVED_AND_REOPENED', 'NOTIFICATION_SETTINGS_SAVED_AND_REOPENED',
                'SURVEY_RULE_SAVED_AND_REOPENED', 'SURVEY_RULE_ALREADY_PRESENT', 'SURVEY_RULE_STACK_SAVED_AND_REOPENED',
                'NATIVE_CONFIGURATION_READBACK_VERIFIED', 'NATIVE_CHECKOUT_UI_READBACK_VERIFIED', 'ROOM_PERSISTED',
                'ROOM_CREATED_AND_VERIFIED', 'ROOM_REUSED_AND_VERIFIED',
                'ROOM_CREATED_VERIFIED', 'ROOM_REUSED_VERIFIED', 'ROOM_UPDATED_VERIFIED',
                'COHOSTS_SAVED_AND_REOPENED', 'COHOSTS_REUSED_AND_REOPENED',
                'CONDITION_GROUP_SAVED_AND_REOPENED', 'CONDITION_GROUP_REUSED_AND_REOPENED',
                'COURSE_BLOCKS_SAVED_AND_REOPENED', 'COURSE_TEXT_BLOCKS_SAVED_AND_REOPENED', 'COURSE_SECTION_MEDIA_SAVED_AND_REOPENED', 'COURSE_IMAGE_BLOCKS_SAVED_AND_REOPENED', 'FORM_TRACKING_SAVED_AND_REOPENED',
                'COURSE_THEME_MEDIA_SAVED_AND_REOPENED', 'COURSE_BLOCK_MEDIA_SAVED_AND_REOPENED',
                'CONDITION_STACK_SAVED_AND_REOPENED', 'CONDITION_STACK_REUSED_AND_REOPENED', 'CONDITION_OUTCOMES_SAVED_AND_REOPENED', 'CONDITION_OUTCOMES_REUSED_AND_REOPENED', 'FORM_EMBED_EXPORTED_AND_REREAD',
                'ORDER_CONFIRMATION_SAVED_AND_REOPENED', 'ORDER_CONFIRMATION_REUSED_AND_REOPENED',
                'DYNAMIC_MEETING_LOCATION_SAVED_AND_REOPENED', 'DYNAMIC_MEETING_LOCATION_REUSED_AND_REOPENED',
            }
            statusless = {'navigate': 'area', 'container': 'container_url', 'page': 'editor_url'}
            if status not in completed and not (
                status is None and statusless.get(step['action']) in result
            ):
                raise Stop('Step requires reconciliation before later writes')
            assert_tenant(page, job)
            results.append({"id":step["id"], "action":step["action"], "result":result})
            state["current_step_status"] = "FINISHED"
            secure_json(state_path, state)
        except Exception as exc:
            # Never persist raw Playwright exception text: it may quote input values.
            state.update(status="NEEDS_BROWSER_RECOVERY", error_type=type(exc).__name__, failed_step=step["id"])
            secure_json(state_path, state)
            from ghl_auth import AuthBridgeError
            if isinstance(exc, AuthBridgeError):
                raise
            raise Stop("Step " + step["id"] + " needs browser recovery; no mutation was retried") from None
    pending=[r['id'] for r in results if
             r['result'].get('checkout_ready') is False
             or any(r['result'].get(key) is False for key in (
                 'behavior_verified', 'submission_verified', 'payment_verified',
                 'functional_verified'))
             or r['result'].get('independent_readback')=='REQUIRED'
             or r['result'].get('behavior_verification')=='REQUIRED'
             or r['result'].get('kind')=='quiz']
    state["status"] = "NEEDS_VERIFICATION" if pending else "EDITOR_STEPS_COMPLETE"
    state['verification_required']=pending
    state["meaning"] = "Requested editor steps completed; this is not a full-funnel QC or payment PASS"
    secure_json(state_path, state)
    return state


def execute(job, root, *, contact_field_capability=None, radio_field_capability=None):
    _reject_portal_editor_jobs(job)
    from playwright_recipes.address_parent import preflight
    preflight(job)
    # Refuse a retained foreign intent before opening/seeding a browser. The
    # locked run_on_page entry rechecks this after authentication as well.
    _reject_foreign_editor_journals(Path(root).resolve())
    from playwright_recipes.evidence_lease import journal_present
    state_path = Path(root).resolve() / 'state.json'
    if journal_present(state_path):
        from playwright_recipes.editor_replay import completed_editor_replay
        replay = completed_editor_replay(state_path, job, sha(json.dumps(job, sort_keys=True)))
        if any(step['action'] == 'native_contact_field_chain' for step in job.get('steps', [])):
            return replay
    elif any(step['action'] == 'native_contact_field_chain' for step in job.get('steps', [])):
        from playwright_recipes.contact_field_frontdoor import validate_runtime
        validate_runtime(job, contact_field_capability)
    if any(step['action'] in ('native_survey_radio_creation','native_survey_creation') for step in job.get('steps', [])):
        if journal_present(state_path):
            # Whole-survey replay must reach its fresh native inventory check.
            # Re-reading a completed survey does not need creation capability.
            if any(step['action']=='native_survey_radio_creation' for step in job['steps']):return replay
        else:
            from playwright_recipes.survey_radio_creation import validate_runtime
            validate_runtime(job,radio_field_capability)
    endpoint = os.environ.get("GHL_MANAGED_CDP_URL", "")
    if endpoint and 'auth_activation' in job:
        raise Stop('Auth activation requires the fresh owned managed context, not an attached browser')
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
                activation = ({**job['auth_activation'], 'location_name': job['location_name'],
                               'start_url': job['start_url']} if 'auth_activation' in job else None)
                receipt=mint_and_bridge(page.context,managed.session,str(seed_path),expected_location_id=job['location_id'],app_origin=origin,
                    **({'activation_target': activation} if activation is not None else {}))
                if not receipt.get('ok') or receipt.page is None:
                    raise Stop('Token bridge did not establish the expected account')
                page=receipt.page
                if activation is None:
                    page.goto(job['start_url'],wait_until='domcontentloaded',timeout=45000)
                elif receipt.get('activation_proof', {}).get('target_verified') is not True or page.url != job['start_url']:
                    raise Stop('Canonical activation did not verify this exact protected target')
                managed.assert_alive()
                arguments = ({'contact_field_capability':contact_field_capability}
                    if any(step['action'] == 'native_contact_field_chain' for step in job.get('steps', [])) else {})
                if any(step['action'] in ('native_survey_radio_creation','native_survey_creation') for step in job.get('steps', [])):
                    arguments['radio_field_capability']=radio_field_capability
                return run_on_page(page,job,root,**arguments)
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
            arguments = ({'contact_field_capability':contact_field_capability}
                if any(step['action'] == 'native_contact_field_chain' for step in job.get('steps', [])) else {})
            if any(step['action'] in ('native_survey_radio_creation','native_survey_creation') for step in job.get('steps', [])):
                arguments['radio_field_capability']=radio_field_capability
            return run_on_page(pages[0], job, root, **arguments)
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
