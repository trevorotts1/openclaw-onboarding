#!/usr/bin/env python3
"""compact-bootstrap.py - mechanical implementation of docs/COMPACT-CORE-SOP.md.

Keeps the six always-loaded bootstrap files under their lean targets by moving
COLD, ARCHIVE and DEDUPE-class OWNER-AUTHORED sections out to the on-demand
reference root VERBATIM and leaving a four-line POINTER behind.

  --dry-run (default)  measure, classify, plan. Writes nothing.
  --apply              perform the plan.
  --check              verify every pointer and every ledgered block. Writes nothing.

WHAT IT NEVER DOES
  * It never touches a SCRIPT-OWNED block (a fleet-roll / skill-update stamp).
    Those are re-injected in full on the next roll, so deleting one by hand buys
    nothing and loses the marker every idempotency guard keys on. They are made
    lean at the SOURCE by scripts/bootstrap-pointerize.py, which stamps them as
    pointers during the roll itself.
  * It never auto-moves a HOT section. Those become proposals for the owner.
  * It never rewrites the text it moves. Improvements are proposals with a diff.

ONE POINTER STANDARD
  The pointer is built by bootstrap-pointerize.build_pointer(), imported from the
  sibling module - not re-implemented here. The roll stamps pointers with that
  function and this tool moves content behind pointers with that same function,
  so there is exactly one pointer shape on every box and exactly one thing for
  validate-core-references.py to resolve.

NOTHING IS HARDCODED TO ONE BOX
  Workspaces come from openclaw.json (agents.defaults.workspace plus every
  agents.entries[].workspace, deduplicated by RESOLVED real path so a box whose
  ~/clawd is a symlink to ~/.openclaw/workspace is compacted once, not twice).
  The reference root is resolved per platform, with an env and a config override.
  The lean targets come from validate-core-references.py, which is also what the
  daily check enforces. python3 3.9 and no jq required.
"""

from __future__ import annotations

import argparse
import datetime
import difflib
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
# RULE TABLES - the operator edits these. Nothing below them needs editing to
# change what counts as hot, cold, archive or script-owned, or where a topic
# lands.
# ─────────────────────────────────────────────────────────────────────────────

# 1. SCRIPT-OWNED MARKERS. A section introduced by one of these belongs to a
#    fleet script. It is re-injected in full if removed, so it is NEVER moved
#    out of a bootstrap file by this tool.
SCRIPT_OWNED_BLOCK_MARKERS = [
    r'^BEGIN\s+skill[:\-]',                 # <!-- BEGIN skill:44-...:agents -->
    r'^BEGIN\s+SKILL38:',                   # <!-- BEGIN SKILL38: STEP_1_30_... -->
    r'^BEGIN\s+REF\s',                      # reference-file fence written by the roll
    r'^N3\d+$',                             # <!-- N34 -->
    # Every apply-fleet-standards.sh sentinel is NAME_Vn. Listing them one by one
    # guarantees the list goes stale the first time a new reflex ships, so the
    # shape is matched instead. CORE_REFERENCE_POLICY_V1 is excluded by
    # NEUTRAL_MARKERS, which is tested first.
    r'^[A-Z][A-Z0-9_]*_V\d+$',
]

# 2. SENTINEL MARKERS. One-line receipts that own no section. Removing one makes
#    the next skill update paste a whole instruction block back in.
SENTINEL_MARKERS = [r'^skill:[^:]+:core-update-applied$']

# 3. NEUTRAL MARKERS. Present for the validator, own nothing.
NEUTRAL_MARKERS = [r'^CORE_REFERENCE_POLICY_V\d+$']

# 4. SCRIPT-OWNED HEADINGS, for blocks carrying no marker of their own.
SCRIPT_OWNED_HEADINGS = [
    r'stamped by apply-fleet-standards\.sh',
    r'^Managed skill blocks',
    r'^UPDATE PENDING',
    r'COMMAND CENTER UPDATE PENDING',
    r'^Step \d',
]

# 5. HOT HEADINGS. Fires every turn. Never auto-moved; over-target hot content
#    becomes a proposal for the owner.
HOT_HEADINGS = [
    r'REFLEX', r'Non-negotiable', r'non-negotiable', r'ROLE DISCIPLINE',
    r'\brouting\b', r'\bRouting\b', r'ROUTING',
    r'Durable operating rules', r'On-demand references', r'Red Lines',
    r'[Cc]redential', r'enforcement', r'ENGLISH ONLY', r'LANGUAGE',
    r'NO LIES', r'accountab', r'IDENTITY', r'^Identity',
    r'secret', r'Secrets', r'PRIME DIRECTIVE', r'^Who ', r'^You are',
]

# 6. ARCHIVE HEADINGS. Historical: what happened, not what to do. Lands in
#    history.md, which takes archive-class content and nothing else.
ARCHIVE_HEADINGS = [
    r'Self-Correction Log', r'\bHistory\b', r'\bIncident\b', r'\bPostmortem\b',
    r'Receipts?\b', r'Changelog', r'Root cause', r'What happened',
    r'\b20\d\d-\d\d-\d\d\b', r'^Timeline',
]

# 7. DESTINATION OVERRIDES. Force a destination and its trigger phrases. Leave a
#    topic out and the topic matcher picks the existing doc that already covers
#    it. First match wins. (heading regex, destination relative to the root, triggers)
TOPIC_OVERRIDES = [
    (r'[Ss]kill 38|SKILL38',   'skill38.md',       'skill 38 runtime, conversational AI system steps'),
    (r'[Ff]leet|\bbox\b|VPS',  'fleet.md',         'a fleet rollout, a client box, onboarding, an outage'),
    (r'[Dd]ocker',             'docker.md',        'Docker or VPS configuration and upgrades'),
    (r'[Mm]edia|image|video|audio', 'media.md',    'image, video or audio generation, provider choice'),
    (r'[Mm]emory',             'memory-policy.md', 'memory maintenance, knowledge retrieval'),
    (r'[Pp]ersona|[Ww]orkforce|[Dd]epartment', 'workforce.md', 'workforce, personas, departments'),
    (r'[Pp]resentation|deck|slide', 'routing.md',  'presentations, decks, Command Center routing'),
    (r'[Bb]ackup',             'backup-policy.md', 'backups, retention, restore'),
    (r'[Ss]kill design|skill build', 'skill-design.md', 'designing, building or modifying a skill'),
]
ARCHIVE_DOC = 'history.md'

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
VALIDATOR = Path(os.environ.get('OPENCLAW_CORE_VALIDATOR')
                 or (SCRIPT_DIR / 'validate-core-references.py'))
POINTERIZE = Path(os.environ.get('OPENCLAW_BOOTSTRAP_POINTERIZE')
                  or (SCRIPT_DIR / 'bootstrap-pointerize.py'))
LEDGER_NAME = 'migration-map.json'
PENDING_NAME = 'pending-updates.md'
INDEX_NAME = 'INDEX.md'
PREVIOUS_DIR = 'previous'
REFERENCE_SUBDIR = 'References 4 Bootstrap'
CORE_FILES = ('AGENTS.md', 'TOOLS.md', 'MEMORY.md', 'USER.md', 'SOUL.md', 'IDENTITY.md')
POINTER_TABLE_HEADING = 'On-demand references'
TOPIC_HEADER = ('Read on demand for this topic; do not preload this document at startup. '
                'Current owner instructions and the compact core policy govern authorization, '
                'providers, routing, and storage. Date-stamped host/model/version/price/status '
                'facts below are historical observations: verify current state before changing '
                'anything. Never print credential values.')
# Docs that are indexes or procedure, never a destination for moved content.
NON_DESTINATION_DOCS = {INDEX_NAME, PENDING_NAME, 'updates-index.md', 'SOP-compact-core.md',
                        'COMPACT-CORE-SOP.md', 'writer-review-procedure.md',
                        'updater-maintenance.md', 'tools/tools-md.md'}

MARKER_RE = re.compile(r'^<!--\s*(END\s+)?(.+?)\s*-->$')
HEADING_RE = re.compile(r'^(#{1,6})\s+(.*\S)\s*$')
FENCE_RE = re.compile(r'^\s*(```|~~~)')
STOPWORDS = {
    'the', 'a', 'an', 'and', 'or', 'of', 'for', 'to', 'in', 'on', 'is', 'it', 'this', 'that',
    'with', 'by', 'not', 'no', 'never', 'always', 'all', 'any', 'you', 'your', 'my', 'our',
    'be', 'are', 'was', 'were', 'do', 'does', 'did', 'has', 'have', 'from', 'at', 'as', 'if',
    'when', 'then', 'than', 'but', 'so', 'per', 'via', 'md', 'tool', 'reference', 'mode',
    'rule', 'rules', 'use', 'used', 'using', 'new', 'old', 'full', 'one', 'two', 'first',
}


def any_match(patterns, text):
    return any(re.search(p, text) for p in patterns)


def tokens(text):
    raw = re.split(r'[^A-Za-z0-9]+', text.lower())
    return {t for t in raw if len(t) > 2 and t not in STOPWORDS and not t.isdigit()}


def normalize_heading(heading):
    return re.sub(r'[^a-z0-9]+', ' ', heading.lower()).strip()


def _load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, str(path))
    if spec is None or spec.loader is None:
        raise SystemExit('cannot load ' + str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ─────────────────────────────────────────────────────────────────────────────
# ONE POINTER STANDARD - imported, never re-implemented.
#
# scripts/bootstrap-pointerize.py owns the pointer shape because the fleet roll
# stamps managed blocks with it. This tool moves OWNER-AUTHORED sections behind
# the SAME shape by importing the same function. Two implementations of one
# format is how a box ends up with pointers only half of its own tooling can
# read, so there is only ever one.
# ─────────────────────────────────────────────────────────────────────────────
_PTR = _load_module(POINTERIZE, 'bootstrap_pointerize')
build_pointer = _PTR.build_pointer
POINTER_SENTINEL = _PTR.POINTER_SENTINEL          # "**Full text:**"

# A stamped pointer reads: "**Full text:** /abs/path.md §anchor — read it ..."
# The path is the first non-space run, exactly as validate-core-references.py's
# own _POINTER_RE reads it, so the two can never disagree about what resolves.
POINTER_RE = re.compile(re.escape(POINTER_SENTINEL) + r'\s+(/\S+)(?:\s+§([A-Za-z0-9\-_]+))?')


# ─────────────────────────────────────────────────────────────────────────────
# PLATFORM RESOLUTION - derived, never hardcoded to one box.
#
# Verified live on the fleet 2026-09-18:
#   Mac client       HOME=/Users/<user>   workspace $HOME/.openclaw/workspace
#                    (~/clawd is a SYMLINK to it), references
#                    $HOME/Downloads/openclaw-master-files/References 4 Bootstrap/
#   Hostinger VPS    HOME=/data           workspace /data/.openclaw/workspace,
#                    references /data/openclaw-master-files/References 4 Bootstrap/
#   Contabo          HOME=/home/node      workspace /home/node/.openclaw/workspace,
#                    references /home/node/.openclaw/master-files/References 4 Bootstrap/
# The operator box is the exception that proves the rule: it runs a main
# workspace AND a second root workspace, which is why workspaces are read from
# config rather than assumed.
# ─────────────────────────────────────────────────────────────────────────────
def detect_oc_root():
    """Mirrors the platform block every other script in this repo uses."""
    env = os.environ.get('OC_ROOT', '').strip()
    if env:
        return Path(env)
    if Path('/data/.openclaw').is_dir():
        return Path('/data/.openclaw')
    return Path.home() / '.openclaw'


def config_path(oc_root):
    env = os.environ.get('OC_CONFIG', '').strip()
    if env:
        return Path(env)
    return oc_root / 'openclaw.json'


def load_config(cfg_path):
    try:
        with open(str(cfg_path), encoding='utf-8') as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _entries(cfg):
    """agents.entries is a DICT keyed by agent id on a live box, but a LIST in
    some older configs. Handle both rather than betting on one."""
    ent = cfg.get('agents', {}).get('entries')
    if isinstance(ent, dict):
        return [v for v in ent.values() if isinstance(v, dict)]
    if isinstance(ent, list):
        return [v for v in ent if isinstance(v, dict)]
    return []


def resolve_workspaces(cfg, oc_root):
    """Every distinct workspace this box actually runs, deduped by REAL path.

    Deduping on the resolved path is load-bearing: on a Mac client ~/clawd is a
    symlink to ~/.openclaw/workspace, so the naive union of the two conventional
    paths would compact the same files twice, double-count the ledger and write
    the second pointer over the first.
    """
    raw = []
    default_ws = cfg.get('agents', {}).get('defaults', {}).get('workspace')
    if isinstance(default_ws, str) and default_ws.strip():
        raw.append(default_ws)
    for entry in _entries(cfg):
        ws = entry.get('workspace')
        if isinstance(ws, str) and ws.strip():
            raw.append(ws)
    if not raw:
        # No config to read (or no workspace declared in it). Fall back to the
        # same two conventional locations bootstrap-validate-daily.sh checks.
        raw = [str(Path.home() / 'clawd'), str(oc_root / 'workspace')]

    seen, out = set(), []
    for item in raw:
        path = Path(os.path.expanduser(os.path.expandvars(item)))
        try:
            real = path.resolve()
        except OSError:
            real = path
        if not real.is_dir():
            continue
        if str(real) in seen:
            continue
        seen.add(str(real))
        out.append(real)
    return out


def reference_root_candidates(oc_root):
    home = Path.home()
    master = os.environ.get('OPENCLAW_MASTER_FILES_DIR', '').strip()
    cands = []
    if master:
        cands.append(Path(master.rstrip('/')) / REFERENCE_SUBDIR)
    cands += [
        home / 'Downloads' / 'openclaw-master-files' / REFERENCE_SUBDIR,  # Mac client
        home / 'openclaw-master-files' / REFERENCE_SUBDIR,               # VPS, HOME=/data
        Path('/data/openclaw-master-files') / REFERENCE_SUBDIR,          # VPS, explicit
        oc_root / 'master-files' / REFERENCE_SUBDIR,                     # Contabo container
    ]
    return cands


def resolve_reference_root(cfg, oc_root):
    """Env override, then config override, then the first candidate that EXISTS,
    then the platform default for creation. Never a hardcoded single path."""
    env = os.environ.get('OPENCLAW_BOOTSTRAP_REFERENCE_ROOT', '').strip()
    if env:
        return Path(os.path.expanduser(env.rstrip('/')))
    cfg_root = cfg.get('agents', {}).get('defaults', {}).get('bootstrapReferenceRoot')
    if isinstance(cfg_root, str) and cfg_root.strip():
        return Path(os.path.expanduser(cfg_root.strip().rstrip('/')))
    cands = reference_root_candidates(oc_root)
    for cand in cands:
        if cand.is_dir():
            return cand
    # Nothing exists yet: create under the platform default.
    if str(oc_root) == '/data/.openclaw':
        return Path('/data/openclaw-master-files') / REFERENCE_SUBDIR
    if (Path.home() / 'Downloads').is_dir():
        return Path.home() / 'Downloads' / 'openclaw-master-files' / REFERENCE_SUBDIR
    return oc_root / 'master-files' / REFERENCE_SUBDIR


# ─────────────────────────────────────────────────────────────────────────────
# Budget and validator - the SAME source the daily check enforces.
# ─────────────────────────────────────────────────────────────────────────────
_VALIDATOR_MOD = None


def load_validator():
    global _VALIDATOR_MOD
    if _VALIDATOR_MOD is None:
        _VALIDATOR_MOD = _load_module(VALIDATOR, 'validate_core_references')
    return _VALIDATOR_MOD


class _BudgetArgs(object):
    """The shape validate-core-references._load_budgets() reads, so the budget
    override chain (env, --budget-file, --from-config, --budget) is honoured by
    exactly one implementation."""

    def __init__(self, budget=None, budget_file=None, from_config=None):
        self.budget = budget or []
        self.budget_file = budget_file
        self.from_config = from_config


def load_budget(args):
    mod = load_validator()
    return dict(mod._load_budgets(_BudgetArgs(args.budget, args.budget_file, args.from_config)))


def run_validator(workspace, budget, require_policy):
    return load_validator().validate(Path(workspace), budget, require_policy)


def size_only_errors(result):
    """A size error on the very file being reduced right now is the one error
    --apply is allowed to run through. Everything else is a real fault and gets
    fixed first: compacting on top of a broken file only hides it."""
    return all(re.search(r'exceeds budget \d+', e) for e in result['errors'])


# ─────────────────────────────────────────────────────────────────────────────
# Reference root index - what topics already have a home
# ─────────────────────────────────────────────────────────────────────────────
def build_reference_index(ref):
    """Read every reference doc's H1 and H2 headings. This is the topic map; it
    is derived from the docs themselves, never from a hardcoded list."""
    index = {}
    if not ref.is_dir():
        return index
    for path in sorted(list(ref.glob('*.md')) + list(ref.glob('tools/*.md'))):
        rel = str(path.relative_to(ref))
        if rel in NON_DESTINATION_DOCS:
            continue
        try:
            text = path.read_text(encoding='utf-8', errors='replace')
        except OSError:
            continue
        heads, h1 = [], ''
        fence = False
        for line in text.splitlines():
            if FENCE_RE.match(line):
                fence = not fence
                continue
            if fence:
                continue
            m = HEADING_RE.match(line)
            if not m:
                continue
            if len(m.group(1)) == 1 and not h1:
                h1 = m.group(2).strip()
            elif len(m.group(1)) == 2:
                heads.append(m.group(2).strip())
        index[rel] = {
            'h1': h1,
            'headings': heads,
            'norm_headings': {normalize_heading(h) for h in heads},
            'tokens': tokens(h1 + ' ' + ' '.join(heads)),
            'empty': not text.strip(),
            'stem': Path(rel).stem,
        }
    return index


def existing_doc_with_stem(ref_index, stem):
    """Near-duplicate guard: never create ghl.md when tools/ghl.md exists."""
    for rel, info in ref_index.items():
        if info['stem'] == stem:
            return rel
    for rel, info in ref_index.items():
        if stem in info['stem'].split('-') or info['stem'] in stem.split('-'):
            return rel
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Parsing
# ─────────────────────────────────────────────────────────────────────────────
class Section(object):
    """raw  = every byte between this heading and the next boundary.
    text = the canonical moved block: raw with trailing blank lines trimmed and
           exactly one closing newline. That is what gets written to the
           reference doc AND what sha256 covers, so the ledger digest can always
           be recomputed from the destination."""

    def __init__(self, start, end, level, heading, raw):
        self.start = start
        self.end = end
        self.level = level
        self.heading = heading
        self.raw = raw
        self.text = raw.rstrip('\n') + '\n'
        self.kind = None
        self.reason = ''
        self.destination = None
        self.dest_reason = ''
        self.triggers = ''

    @property
    def chars(self):
        return len(self.raw)

    @property
    def lines(self):
        return (self.start + 1, self.end + 1)

    def sha256(self):
        return hashlib.sha256(self.text.encode('utf-8')).hexdigest()


def parse(text):
    lines = text.splitlines(keepends=True)
    fence = False
    markers, headings = [], []
    for i, line in enumerate(lines):
        if FENCE_RE.match(line):
            fence = not fence
            continue
        if fence:
            continue
        m = MARKER_RE.match(line.strip())
        if m:
            markers.append((i, bool(m.group(1)), m.group(2)))
            continue
        h = HEADING_RE.match(line)
        if h:
            headings.append((i, len(h.group(1)), h.group(2).strip()))

    marker_idx = [i for i, _, _ in markers]
    spans, opened = [], {}
    for i, is_end, label in markers:
        if is_end:
            if label in opened:
                start = opened.pop(label)
                if any_match(SCRIPT_OWNED_BLOCK_MARKERS, label):
                    spans.append((start, i, label))
        else:
            opened[label] = i

    for label, start in sorted(opened.items(), key=lambda kv: kv[1]):
        if any_match(NEUTRAL_MARKERS, label) or any_match(SENTINEL_MARKERS, label):
            continue
        if not any_match(SCRIPT_OWNED_BLOCK_MARKERS, label):
            continue
        following = [h for h in headings if h[0] > start]
        if not following:
            spans.append((start, len(lines) - 1, label))
            continue
        head_idx, head_level, _ = following[0]
        stop = len(lines) - 1
        for idx, level, _ in following[1:]:
            if level <= head_level:
                stop = idx - 1
                break
        for idx in marker_idx:
            if idx > start:
                stop = min(stop, idx - 1)
                break
        spans.append((start, max(stop, head_idx), label))

    covered = [False] * len(lines)
    for s, e, _ in spans:
        for i in range(s, min(e + 1, len(lines))):
            covered[i] = True

    span_starts = sorted(s for s, _, _ in spans)
    sections = []
    for idx, level, htext in [h for h in headings if h[1] >= 2]:
        stop = len(lines) - 1
        for other_idx, other_level, _ in headings:
            if other_idx > idx and other_level <= level:
                stop = other_idx - 1
                break
        for span_start in span_starts:
            if span_start > idx:
                stop = min(stop, span_start - 1)
                break
        stop = max(stop, idx)
        sections.append(Section(idx, stop, level, htext, ''.join(lines[idx:stop + 1])))

    top_chars = sum(s.chars for s in sections if s.level == 2)
    return sections, spans, covered, max(len(text) - top_chars, 0)


def is_pointer(raw):
    return POINTER_SENTINEL in raw


def classify(sections, spans, covered, ref_index):
    """One decision rule per section, recorded with its reason.

    script  - stamped by a fleet script. Never moves. Made lean in the repo.
    pointer - already compacted.
    hot     - fires every turn. Never auto-moved; becomes a proposal.
    archive - historical. What happened, not what to do. Goes to history.md.
    dedupe  - a reference doc already carries a section with this heading.
    cold    - procedural or reference detail. Moves.
    """
    for sec in sections:
        overlap = any(covered[i] for i in range(sec.start, sec.end + 1))
        norm = normalize_heading(sec.heading)
        twin = next((rel for rel, info in ref_index.items()
                     if rel != ARCHIVE_DOC and norm in info['norm_headings']), None)
        if overlap:
            sec.kind, sec.reason = 'script', 'inside a script-owned marker block'
        elif any_match(SCRIPT_OWNED_HEADINGS, sec.heading):
            sec.kind, sec.reason = 'script', 'heading matches a script-owned pattern'
        elif is_pointer(sec.raw):
            sec.kind, sec.reason = 'pointer', 'already compacted'
        elif '<!--' in sec.raw:
            # Blanket third guard. If the marker table and the heading table were
            # both wrong, the worst outcome is that something stays put.
            sec.kind, sec.reason = 'script', 'contains an HTML marker'
        elif any_match(HOT_HEADINGS, sec.heading):
            sec.kind, sec.reason = 'hot', 'fires every turn'
        elif any_match(ARCHIVE_HEADINGS, sec.heading):
            sec.kind, sec.reason = 'archive', 'historical: what happened, not what to do'
        elif twin:
            sec.kind, sec.reason = 'dedupe', 'same heading already in ' + twin
        else:
            sec.kind, sec.reason = 'cold', 'procedural or reference detail'
    return sections


# ─────────────────────────────────────────────────────────────────────────────
# Destination rule - existing doc first, always
# ─────────────────────────────────────────────────────────────────────────────
def unwrap(body):
    """Join hard-wrapped lines inside a paragraph. Source files wrap at ~80
    columns, so a trigger sentence is usually split across two or three lines."""
    paras, current = [], []
    for line in body.splitlines():
        if not line.strip():
            if current:
                paras.append(' '.join(current))
                current = []
        else:
            current.append(line.strip())
    if current:
        paras.append(' '.join(current))
    return paras


def clip(text, limit=170):
    text = re.sub(r'\s+', ' ', text).strip()
    if len(text) <= limit:
        return text.rstrip(' .,;')
    m = re.match(r'^(.{40,' + str(limit) + r'}?[.!?])\s', text + ' ')
    if m:
        return m.group(1).rstrip(' .,;')
    cut = text[:limit]
    for sep in ('; ', ', ', ' '):
        if sep in cut:
            return cut[:cut.rfind(sep)].rstrip(' .,;')
    return cut.rstrip(' .,;')


def derive_triggers(section):
    body = section.text.split('\n', 1)[1] if '\n' in section.text else ''
    for para in unwrap(body):
        m = re.match(r'^\**Trigger:?\**[:\s]*(.+)$', para)
        if m:
            t = re.sub(r'[*`]', '', m.group(1)).strip()
            if t:
                return clip(t)
    quoted = re.findall(r'"([^"\n]{3,40})"', body)
    if quoted:
        return ', '.join('"' + q + '"' for q in quoted[:4])
    return clip(section.heading)


def choose_destination(section, ref_index):
    """Existing doc first, by topic. A new doc only when nothing covers it."""
    if section.kind == 'archive':
        return ARCHIVE_DOC, derive_triggers(section), 'archive class goes to history.md'

    for pattern, dest, triggers in TOPIC_OVERRIDES:
        if re.search(pattern, section.heading):
            return dest, triggers, 'destination override in the rule table'

    norm = normalize_heading(section.heading)
    for rel, info in ref_index.items():
        if rel != ARCHIVE_DOC and norm in info['norm_headings']:
            return rel, derive_triggers(section), 'that doc already has a section with this heading'

    body = section.text[:400]
    cand = tokens(section.heading + ' ' + body)
    best, best_score = None, 0
    for rel, info in ref_index.items():
        if rel == ARCHIVE_DOC:
            continue
        score = len(cand & info['tokens'])
        if Path(rel).stem in cand:
            score += 2
        if score > best_score:
            best, best_score = rel, score
    if best and best_score >= 2:
        return best, derive_triggers(section), ('topic overlap with ' + best
                                                + ' (' + str(best_score) + ' terms)')

    stem = slug(section.heading)
    twin = existing_doc_with_stem(ref_index, stem)
    if twin:
        return twin, derive_triggers(section), 'near-duplicate guard: ' + twin + ' already covers this'
    if best_score >= 1:
        return best, derive_triggers(section), ('weak topic overlap with ' + best
                                                + '; kept out of a new doc')
    return stem + '.md', derive_triggers(section), 'no existing doc covers this topic'


# ─────────────────────────────────────────────────────────────────────────────
# Pointer construction - the four lines, built by the shared writer
# ─────────────────────────────────────────────────────────────────────────────
def slug(heading):
    s = re.sub(r'[`*_]', '', heading.lower())
    s = re.sub(r'[^a-z0-9 \-]', ' ', s)
    s = re.sub(r'\s+', '-', s.strip())
    return re.sub(r'-{2,}', '-', s).strip('-') or 'section'


def summarize(section):
    """One sentence saying what is inside, in the owner's own words. Never
    invented. Skips the Trigger sentence - that is the triggers line."""
    body = section.text.split('\n', 1)[1] if '\n' in section.text else ''

    # A step list describes itself best through its own step titles.
    steps = re.findall(r'^\s*(?:\d+\.|[-*+])\s+\*\*(.+?)\.?\*\*', body, re.M)
    if len(steps) >= 3:
        titles = '; '.join(re.sub(r'[*_`]', '', s).replace(';', ',').rstrip('.')
                           for s in steps[:3])
        return clip(str(len(steps)) + '-step procedure: ' + titles, 190) + '.'

    plain = []
    for para in unwrap(body):
        if re.match(r'^\**Trigger', para) or para.startswith('|') or para.startswith('```'):
            continue
        para = re.sub(r'^[-*+]\s+', '', para)
        para = re.sub(r'^\d+\.\s+', '', para)
        plain.append(re.sub(r'[*_`#]', '', para))
        if len(' '.join(plain)) > 260:
            break
    text = ' '.join(plain).strip()
    return clip(text, 190) + '.' if text else section.heading


def pointer_block(section, dest_path, anchor, triggers):
    """Exactly four lines, from the one shared writer in bootstrap-pointerize.py:
    heading verbatim, one sentence, the triggers that say when to open it, and
    ONE absolute path with an anchor."""
    heading = '#' * section.level + ' ' + section.heading
    body = build_pointer(heading, summarize(section),
                         [triggers.rstrip(' .')], str(dest_path), anchor)
    return body.rstrip('\n') + '\n\n'


def unique_anchor(dest_text, base):
    """A suffixed anchor MEANS a collision - two blocks under one heading. So the
    doc's own H1 title is deliberately not counted: a new doc created for this
    very block is titled after it, and counting that title would stamp a "-2" on
    every first move and make a real collision indistinguishable from a fresh
    file."""
    taken = set(re.findall(r'id="([^"]+)"', dest_text))
    for line in dest_text.splitlines():
        m = HEADING_RE.match(line)
        if m and len(m.group(1)) >= 2:
            taken.add(slug(m.group(2).strip()))
    anchor, n = base, 2
    while anchor in taken:
        anchor = base + '-' + str(n)
        n += 1
    return anchor


# ─────────────────────────────────────────────────────────────────────────────
# Writing
# ─────────────────────────────────────────────────────────────────────────────
def atomic_write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='.compact-bootstrap-', dir=str(path.parent))
    try:
        with os.fdopen(fd, 'w') as fh:
            fh.write(text)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def workspace_tag(workspace):
    """A short, stable name for a workspace. Both workspaces on a box can hold a
    file called AGENTS.md, so the ledger has to say which one."""
    ws = Path(workspace)
    if ws.name == 'workspace' and ws.parent.name == '.openclaw':
        return 'workspace'
    return ws.name


def git_tracked(workspace, name):
    try:
        r = subprocess.run(['git', '-C', str(workspace), 'ls-files', '--error-unmatch', name],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return r.returncode == 0
    except OSError:
        return False


def ensure_topic_doc(path, title):
    if path.exists():
        return False
    atomic_write(path, '# ' + title + '\n\n' + TOPIC_HEADER + '\n')
    return True


def stored_block(anchor, source, digest, text):
    """Explicit end marker so the exact bytes stay recoverable after later
    appends. --check re-hashes what sits between the anchor and the end marker."""
    return ('<!-- source: ' + source + '; migrated ' + datetime.date.today().isoformat()
            + '; sha256 ' + digest + ' -->\n'
            '<a id="' + anchor + '"></a>\n' + text
            + '<!-- end-block ' + anchor + ' -->\n')


def extract_block(dest_text, anchor):
    key = '<a id="' + anchor + '"></a>\n'
    end = '<!-- end-block ' + anchor + ' -->'
    if key not in dest_text or end not in dest_text:
        return None
    i = dest_text.index(key) + len(key)
    j = dest_text.index(end, i)
    return dest_text[i:j]


def add_to_index(index_path, relpath):
    if not index_path.exists():
        atomic_write(index_path, '# INDEX\n\nOn-demand reference documents.\n\n')
    text = index_path.read_text(encoding='utf-8', errors='replace')
    if ('`' + relpath + '`') in text:
        return False
    lines = text.splitlines(keepends=True)
    bullets = [i for i, l in enumerate(lines) if l.startswith('- `')]
    insert_at = len(lines)
    for i in bullets:
        if relpath < lines[i][3:].split('`')[0]:
            insert_at = i
            break
    else:
        if bullets:
            insert_at = bullets[-1] + 1
    lines.insert(insert_at, '- `' + relpath + '`\n')
    atomic_write(index_path, ''.join(lines))
    return True


def add_pointer_table_row(text, triggers, abs_path):
    """Register a newly created doc in the bootstrap file's own pointer table.
    A reference nobody is routed to is a reference nobody reads."""
    lines = text.splitlines(keepends=True)
    start = None
    for i, line in enumerate(lines):
        m = HEADING_RE.match(line)
        if m and POINTER_TABLE_HEADING in m.group(2):
            start = i
            break
    if start is None:
        return text, False
    last = None
    for i in range(start, len(lines)):
        if lines[i].startswith('|'):
            last = i
        elif last is not None and not lines[i].strip():
            break
    if last is None:
        return text, False
    row = '| ' + triggers.rstrip(' .') + ' | `' + str(abs_path) + '` |\n'
    if row in text:
        return text, False
    lines.insert(last + 1, row)
    return ''.join(lines), True


def append_ledger(ledger_path, entries):
    data = []
    if ledger_path.exists():
        try:
            data = json.loads(ledger_path.read_text(encoding='utf-8', errors='replace'))
        except ValueError:
            data = []
    if not isinstance(data, list):
        data = []
    data.extend(entries)
    atomic_write(ledger_path, json.dumps(data, indent=1) + '\n')


def write_keyed_block(pending_path, key, body):
    block = key + '\n' + body.rstrip() + '\n'
    text = (pending_path.read_text(encoding='utf-8', errors='replace')
            if pending_path.exists() else '# Pending Updates\n')
    if key in text:
        start = text.index(key)
        nxt = text.find('\n<!-- proposal: compact-bootstrap', start + 1)
        end = nxt if nxt != -1 else len(text)
        new = text[:start] + block + text[end:]
    else:
        new = text.rstrip('\n') + '\n\n---\n\n' + block
    if new == text:
        return False
    atomic_write(pending_path, new)
    return True


def dedupe_proposal(section, dest_rel, anchor, ref):
    """Improve-on-move, two-copy rule: the verbatim block is already filed and
    ledgered. The improvement is only ever a proposal with a diff."""
    dest = ref / dest_rel
    text = dest.read_text(encoding='utf-8', errors='replace')
    other = None
    for m in re.finditer(r'^## (.+)$', text, re.M):
        if normalize_heading(m.group(1)) == normalize_heading(section.heading):
            blk_start = m.start()
            nxt = text.find('\n## ', m.end())
            candidate = text[blk_start:nxt if nxt != -1 else len(text)]
            # Trim the separator and the next block's source comment off the tail.
            candidate = re.sub(r'(\n\s*---\s*\n|\n<!--[^>]*-->\s*\n?)+$', '\n', candidate)
            if ('<a id="' + anchor + '"></a>') not in text[max(0, blk_start - 200):blk_start]:
                other = candidate
                break
    if other is None:
        return None
    diff = ''.join(difflib.unified_diff(
        other.splitlines(True), section.text.splitlines(True),
        fromfile=dest_rel + ' (existing copy)',
        tofile=dest_rel + '#' + anchor + ' (newly moved verbatim copy)'))
    return ('## PROPOSAL - reconcile two copies of "' + section.heading + '" in ' + dest_rel
            + '\n\nBoth copies are filed verbatim and both are ledgered. Neither has been '
              'edited. This is a proposal to reconcile them into one, for the owner to '
              'approve or reject. Until then, the two blocks stay exactly as they are.\n\n'
              '```diff\n' + diff + '```\n')


# ─────────────────────────────────────────────────────────────────────────────
# Planning and application
# ─────────────────────────────────────────────────────────────────────────────
MOVABLE = ('cold', 'archive', 'dedupe')


def plan_file(workspace, name, target, ref, ref_index):
    path = Path(workspace) / name
    if not path.is_file():
        return None
    text = path.read_text(encoding='utf-8', errors='replace')
    sections, spans, covered, unsectioned = parse(text)
    classify(sections, spans, covered, ref_index)
    raw_lines = text.splitlines(keepends=True)
    span_chars = sum(len(raw_lines[i]) for i in range(len(raw_lines)) if covered[i])
    top = [s for s in sections if s.level == 2]
    totals = {k: sum(s.chars for s in top if s.kind == k)
              for k in ('script', 'hot', 'cold', 'archive', 'dedupe', 'pointer')}
    for sec in top:
        if sec.kind in MOVABLE:
            sec.destination, sec.triggers, sec.dest_reason = choose_destination(sec, ref_index)

    chosen, projected = [], len(text)
    if len(text) > target:
        # Dedupe first (it is redundancy), then archive, then cold, largest first.
        order = {'dedupe': 0, 'archive': 1, 'cold': 2}
        for sec in sorted([s for s in top if s.kind in MOVABLE],
                          key=lambda s: (order[s.kind], -s.chars)):
            if projected <= target:
                break
            pointer = pointer_block(sec, ref / sec.destination, slug(sec.heading), sec.triggers)
            chosen.append((sec, sec.destination, sec.triggers, pointer))
            projected -= (sec.chars - len(pointer))
    return {'name': name, 'path': path, 'text': text, 'target': target, 'before': len(text),
            'projected': projected, 'sections': sections, 'top': top, 'totals': totals,
            'unsectioned': unsectioned, 'chosen': chosen, 'span_chars': span_chars}


def apply_file(pf, workspace, ref, ref_index, apply):
    rows, notes = [], []
    if not pf['chosen']:
        pf['after'] = pf['before']
        return rows, notes
    ledger_entries, accepted, new_docs = [], [], []
    tag = workspace_tag(workspace)

    if git_tracked(workspace, pf['name']):
        notes.append('rollback: git (tracked in ' + str(workspace) + ')')
    else:
        stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
        backup = ref / PREVIOUS_DIR / (Path(pf['name']).stem + '-' + tag + '-' + stamp + '.md')
        if apply:
            atomic_write(backup, pf['text'])
        notes.append('rollback: ' + str(backup))

    for sec, dest_rel, triggers, _ in sorted(pf['chosen'], key=lambda c: -c[0].start):
        dest = ref / dest_rel
        is_new = not dest.exists()
        if is_new and apply:
            ensure_topic_doc(dest, sec.heading)
            notes.append('created reference doc ' + dest_rel + ' (' + sec.dest_reason + ')')
        dest_text = dest.read_text(encoding='utf-8', errors='replace') if dest.exists() else ''
        digest = sec.sha256()
        if ('sha256 ' + digest) in dest_text:
            notes.append('SKIP ' + sec.heading + ': already in ' + dest_rel + ' (same sha256)')
            continue
        anchor = unique_anchor(dest_text, slug(sec.heading))
        pointer = pointer_block(sec, dest, anchor, triggers)
        source = tag + '/' + pf['name'] + ':' + str(sec.lines[0]) + '-' + str(sec.lines[1])
        block = stored_block(anchor, source, digest, sec.text)
        if apply:
            atomic_write(dest, dest_text.rstrip('\n') + '\n\n---\n\n' + block)
            add_to_index(ref / INDEX_NAME, dest_rel)
            if sec.kind == 'dedupe':
                body = dedupe_proposal(sec, dest_rel, anchor, ref)
                if body and write_keyed_block(
                        ref / PENDING_NAME,
                        '<!-- proposal: compact-bootstrap dedupe; ' + dest_rel + '#' + anchor + ' -->',
                        body):
                    notes.append('dedupe proposal written to ' + PENDING_NAME
                                 + ' for ' + dest_rel + '#' + anchor)
        if is_new:
            new_docs.append((triggers, dest))
        accepted.append((sec, pointer))
        rows.append({'heading': sec.heading, 'kind': sec.kind, 'reason': sec.reason,
                     'chars': sec.chars, 'lines': sec.lines,
                     'destination': dest_rel + '#' + anchor, 'dest_reason': sec.dest_reason,
                     'sha256': digest, 'new_doc': is_new})
        ledger_entries.append({
            'file': pf['name'], 'start_line': sec.lines[0], 'end_line': sec.lines[1],
            'heading': '#' * sec.level + ' ' + sec.heading,
            'action': 'relocated to on-demand reference',
            'destination': dest_rel + '#' + anchor, 'sha256': digest,
            'workspace': tag, 'class': sec.kind,
            'migrated_utc': datetime.datetime.now(datetime.timezone.utc).isoformat()})

    if accepted:
        lines = pf['text'].splitlines(keepends=True)
        for sec, pointer in sorted(accepted, key=lambda c: -c[0].start):
            lines = lines[:sec.start] + [pointer] + lines[sec.end + 1:]
        new_text = ''.join(lines)
        for triggers, dest in new_docs:
            new_text, added = add_pointer_table_row(new_text, triggers, dest)
            if added:
                notes.append('registered ' + dest.name + ' in the pointer table')
        if apply:
            atomic_write(pf['path'], new_text)
            append_ledger(ref / LEDGER_NAME, ledger_entries)
            pf['text'] = new_text
        pf['after'] = len(new_text)
    else:
        pf['after'] = pf['before']
    return rows, notes


def proposal_body(pf, tag):
    out = ['## PROPOSAL ' + datetime.date.today().isoformat() + ' - ' + tag + '/' + pf['name']
           + ' is still over its lean target', '',
           'Movable content is exhausted. Nothing below has been moved and nothing below may be '
           'moved without the owner saying so.', '', '| | chars |', '|---|---|',
           '| current | ' + str(pf.get('after', pf['before'])) + ' |',
           '| lean target | ' + str(pf['target']) + ' |',
           '| still over by | ' + str(pf.get('after', pf['before']) - pf['target']) + ' |', '']
    hot = sorted([s for s in pf['top'] if s.kind == 'hot'], key=lambda s: -s.chars)
    if hot:
        out += ['HOT - fires every turn. Moving any of these needs the owner\'s explicit '
                'approval:', '', '| heading | chars |', '|---|---|']
        out += ['| ' + s.heading.replace('|', '\\|') + ' | ' + str(s.chars) + ' |' for s in hot[:15]]
        out += ['']
    script = sorted([s for s in pf['top'] if s.kind == 'script'], key=lambda s: -s.chars)
    if script:
        out += ['SCRIPT-OWNED - re-injected in full by the fleet scripts if removed here. These '
                'are made lean at the SOURCE by scripts/bootstrap-pointerize.py during the roll, '
                'never by hand on a box:', '', '| heading | chars |', '|---|---|']
        out += ['| ' + s.heading.replace('|', '\\|') + ' | ' + str(s.chars) + ' |'
                for s in script[:20]]
        out += ['', 'Script-owned total in this file: ' + str(sum(s.chars for s in script))
                + ' chars.']
    return '\n'.join(out)


# ─────────────────────────────────────────────────────────────────────────────
# --check
# ─────────────────────────────────────────────────────────────────────────────
def check(workspace, ref):
    """(a) the anchor named by the pointer is really in the target doc,
    (b) the ledgered sha256 still matches the block sitting in the reference doc,
    which catches a block edited after the move, and
    (c) no pointer targets an empty file."""
    problems, rows = [], []
    ws = Path(workspace)
    for name in CORE_FILES:
        path = ws / name
        if not path.is_file():
            continue
        for m in POINTER_RE.finditer(path.read_text(encoding='utf-8', errors='replace')):
            target, anchor = Path(m.group(1)), m.group(2)
            where = name + ' -> ' + target.name + ('#' + anchor if anchor else '')
            if not target.is_file():
                rows.append(('FAIL', where, 'target file missing'))
                problems.append(where)
                continue
            dest_text = target.read_text(encoding='utf-8', errors='replace')
            if not dest_text.strip():
                rows.append(('FAIL', where, 'target file is empty'))
                problems.append(where)
            elif not anchor:
                rows.append(('ok', where, 'file resolves (whole-file pointer, no anchor)'))
            elif ('id="' + anchor + '"') not in dest_text and ('BEGIN REF ' + anchor) not in dest_text:
                rows.append(('FAIL', where, 'anchor not in target'))
                problems.append(where)
            else:
                rows.append(('ok', where, 'anchor resolves'))

    tag = workspace_tag(workspace)
    ledger = ref / LEDGER_NAME
    entries = []
    if ledger.is_file():
        try:
            entries = json.loads(ledger.read_text(encoding='utf-8', errors='replace'))
        except ValueError:
            entries = []
    if not isinstance(entries, list):
        entries = []
    checked = skipped = 0
    for e in entries:
        if not isinstance(e, dict):
            skipped += 1
            continue
        dest = e.get('destination', '')
        if '#' not in dest or e.get('workspace') != tag:
            skipped += 1
            continue
        rel, anchor = dest.split('#', 1)
        target = ref / rel
        where = 'ledger ' + e.get('file', '?') + ' -> ' + dest
        if not target.is_file():
            rows.append(('FAIL', where, 'destination doc missing'))
            problems.append(where)
            continue
        block = extract_block(target.read_text(encoding='utf-8', errors='replace'), anchor)
        if block is None:
            rows.append(('FAIL', where, 'block not found between anchor and end marker'))
            problems.append(where)
            continue
        digest = hashlib.sha256(block.encode('utf-8')).hexdigest()
        if digest != e.get('sha256'):
            rows.append(('FAIL', where, 'sha256 drift: block was edited after the move'))
            problems.append(where)
        else:
            rows.append(('ok', where, 'sha256 matches'))
        checked += 1

    print('compact-bootstrap CHECK - workspace ' + str(workspace))
    print('')
    for status, where, detail in rows:
        print('  %-4s %-70s %s' % (status, where[:70], detail))
    print('')
    print('pointers and ledgered blocks verified: %d; ledger entries not verifiable '
          '(pre-tool, no anchor): %d' % (checked, skipped))
    print('result: ' + ('FAIL (' + str(len(problems)) + ')' if problems else 'ok'))
    return 1 if problems else 0


# ─────────────────────────────────────────────────────────────────────────────
# Report
# ─────────────────────────────────────────────────────────────────────────────
def report(workspace, results, before_val, after_val, mode):
    out = ['compact-bootstrap ' + mode + ' - workspace ' + str(workspace), '',
           '%-12s %9s %9s %9s %9s  %s' % ('file', 'before', 'target', 'after', 'delta', 'status')]
    for pf in results:
        after = pf.get('after', pf['before'])
        status = 'ok' if after <= pf['target'] else 'OVER by ' + str(after - pf['target'])
        out.append('%-12s %9d %9d %9d %9d  %s'
                   % (pf['name'], pf['before'], pf['target'], after, after - pf['before'], status))
    out.append('')
    for pf in results:
        if pf['before'] <= pf['target'] and not pf['chosen']:
            continue
        out.append(pf['name'] + ' - decision per section:')
        out.append('  %-8s %7s  %-58s %s' % ('class', 'chars', 'heading', 'why'))
        for sec in sorted(pf['top'], key=lambda s: -s.chars):
            out.append('  %-8s %7d  %-58s %s'
                       % (sec.kind, sec.chars, sec.heading[:58], sec.reason))
        out.append('')
        out.append('  totals: ' + ', '.join('%s %d' % (k, v) for k, v in pf['totals'].items())
                   + ', other %d' % pf['unsectioned'])
        out.append('  script-owned marker spans, whole file: %d of %d chars (%.0f%%)'
                   % (pf['span_chars'], pf['before'], 100.0 * pf['span_chars'] / max(pf['before'], 1)))
        if pf['rows']:
            out.append('')
            out.append('  moved:')
            for r in pf['rows']:
                out.append('    - %s [%s] %d chars, lines %d-%d' %
                           (r['heading'], r['kind'], r['chars'], r['lines'][0], r['lines'][1]))
                out.append('      -> %s   (%s%s)' % (r['destination'], r['dest_reason'],
                                                     ', NEW DOC' if r['new_doc'] else ''))
                out.append('      sha256 %s' % r['sha256'])
        for n in pf['notes']:
            out.append('  note: ' + n)
        out.append('')
    out.append('validator before: ' + json.dumps(before_val, sort_keys=True))
    out.append('validator after:  ' + json.dumps(after_val, sort_keys=True))
    return '\n'.join(out)


# ─────────────────────────────────────────────────────────────────────────────
# Per-workspace run
# ─────────────────────────────────────────────────────────────────────────────
def run_workspace(workspace, ref, budget, a):
    require_policy = not a.no_require_policy
    if a.check:
        return check(workspace, ref)

    names = a.file or [n for n in CORE_FILES if (Path(workspace) / n).is_file()]
    if a.target and len(names) != 1:
        print('--target needs exactly one --file', file=sys.stderr)
        return 2

    before_val = run_validator(workspace, budget, require_policy)
    if a.apply and not before_val['ok'] and not size_only_errors(before_val):
        print('REFUSED: validator is failing for a reason other than size. Fix it first.',
              file=sys.stderr)
        print(json.dumps(before_val, indent=2), file=sys.stderr)
        return 2

    ref_index = build_reference_index(ref)
    results = []
    for name in names:
        target = a.target if a.target else budget.get(name)
        if target is None:
            continue
        pf = plan_file(workspace, name, target, ref, ref_index)
        if pf is None:
            continue
        pf['rows'], pf['notes'] = apply_file(pf, workspace, ref, ref_index, a.apply)
        results.append(pf)

    for pf in results:
        if pf.get('after', pf['before']) > pf['target']:
            key = ('<!-- proposal: compact-bootstrap; workspace ' + workspace_tag(workspace)
                   + '; file ' + pf['name'] + ' -->')
            body = proposal_body(pf, workspace_tag(workspace))
            if a.apply:
                changed = write_keyed_block(ref / PENDING_NAME, key, body)
                pf['notes'].append(('proposal written to ' if changed
                                    else 'proposal already current in ') + PENDING_NAME)
            else:
                pf['notes'].append('would write a proposal to ' + PENDING_NAME)

    after_val = run_validator(workspace, budget, require_policy)
    print(report(workspace, results, before_val, after_val, 'APPLY' if a.apply else 'DRY-RUN'))
    if a.apply:
        print('')
        return check(workspace, ref)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--workspace', action='append',
                    help='one workspace to act on (repeatable). Omit to act on EVERY workspace '
                         'this box declares in openclaw.json.')
    ap.add_argument('--file', action='append', choices=list(CORE_FILES))
    ap.add_argument('--target', type=int, help='override the lean target for --file')
    ap.add_argument('--references', help='reference root (default: resolved per platform)')
    ap.add_argument('--budget', action='append', help='override one budget: NAME=CHARS (repeatable)')
    ap.add_argument('--budget-file', help='JSON file of {NAME: CHARS}')
    ap.add_argument('--from-config', help='openclaw.json to read agents.defaults.bootstrapMaxChars from')
    ap.add_argument('--no-require-policy', action='store_true',
                    help='do not require the compact-policy marker')
    ap.add_argument('--dry-run', action='store_true', default=True, help='default: plan only')
    ap.add_argument('--apply', action='store_true', help='perform the plan')
    ap.add_argument('--check', action='store_true',
                    help='verify pointers and ledgered blocks; writes nothing')
    ap.add_argument('--list-workspaces', action='store_true',
                    help='print the workspaces that would be acted on, one per line, and exit')
    a = ap.parse_args(argv)

    oc_root = detect_oc_root()
    cfg_path = Path(a.from_config) if a.from_config else config_path(oc_root)
    cfg = load_config(cfg_path)

    if a.workspace:
        workspaces = []
        for item in a.workspace:
            p = Path(os.path.expanduser(item))
            if not p.is_dir():
                print('workspace not found: ' + str(p), file=sys.stderr)
                return 2
            workspaces.append(p.resolve())
    else:
        workspaces = resolve_workspaces(cfg, oc_root)
    if not workspaces:
        print('no workspace found to act on (config: ' + str(cfg_path) + ')', file=sys.stderr)
        return 2

    if a.list_workspaces:
        for ws in workspaces:
            print(str(ws))
        return 0

    ref = Path(os.path.expanduser(a.references)) if a.references else resolve_reference_root(cfg, oc_root)
    if not ref.is_dir():
        if a.check:
            print('reference root not found: ' + str(ref), file=sys.stderr)
            return 2
        ref.mkdir(parents=True, exist_ok=True)
        print('created reference root ' + str(ref))

    budget = load_budget(a)

    worst = 0
    for ws in workspaces:
        rc = run_workspace(ws, ref, budget, a)
        print('')
        worst = max(worst, rc)
    return worst


if __name__ == '__main__':
    sys.exit(main())
