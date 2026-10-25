#!/usr/bin/env python3
"""Self-check for T-14 — bonus membership/access capability decision.

Pins every acceptance clause of the task record (R-13, C-14, C-F07) and the
refusal cases, so a future edit cannot quietly promote an unproved step to
"supported" or gate the original gift on the bonus lane.

  C-14  current official route/tenant requirements, mobile-only
        identity/token/recovery evidence or the EXACT capability block, and no
        fabricated API;
  C-F07 original gift proceeds while the bonus is unavailable.

Run: python3 -m unittest discover -s shared-utils/bonus/tests -v
     python3 -m unittest shared-utils.bonus.tests.test_access_capability -v
"""

from __future__ import annotations

import json
import os
import re
import sys
import unittest
from pathlib import Path

_TESTS = Path(__file__).resolve().parent
_BONUS = _TESTS.parent
_SHARED = _BONUS.parent
_REPO = _SHARED.parent
for _p in (str(_SHARED), str(_REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bonus import access_capability as ac  # noqa: E402


# --------------------------------------------------------------------------
# Fabricated-API detector
# --------------------------------------------------------------------------
# One place decides what an invented interface looks like. The route surface is
# searched for every shape; Python source is searched for the four that cannot
# be legitimate there. A dotted token is NOT searched in Python source because
# attribute access (`cap.transport.value`) is real Python — a smuggled operation
# id has to reach the returned surface to matter, and that surface is covered.

_URL = re.compile(r"https?://", re.I)
# `\s*`, not `\s+`: a verb glued to its path (`POST/memberships/grant`) is the
# same fabrication as a spaced one. `\S+`, not `\S*`: a verb with nothing behind
# the slash (`POST/`) is a verb and no operation, and must not be flagged.
_VERB_PATH = re.compile(r"\b(?:GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\s*/\S+", re.I)
# A bare operation path, in two forms:
#   1. slash-led, delimited by whitespace, a quote or a value separator
#      (`"/memberships/grant"`). Always flagged.
#   2. identifier-prefixed: any [A-Za-z0-9_] run glued in front of the first
#      `/` (`v1/memberships/grant`, `memberships/grant`). Shape alone cannot
#      tell it from real prose (`memberships/communities`, `assisted/operator`),
#      so the world is closed: the token passes only as file provenance, or as a
#      reviewed slash token inside the exact sentence it was reviewed in. A new
#      token, or a reviewed token outside its sentence, fails until a human
#      reviews it. An exemption no longer travels with the token alone, so a
#      reviewed token cannot excuse an `api` or `route` value.
#   3. a trailing path segment with no segment behind it (`memberships/`): the
#      operation family with its operation cut off is still operation-shaped.
# The forms cannot overlap, so form 1 flags exactly what it did before.
_BARE_PATH = re.compile(
    r"(?:^|(?<=[\s\"'=(:,]))/[A-Za-z0-9_{][A-Za-z0-9_\-{}/.]*"
    r"|(?<![A-Za-z0-9_\-.{}/])[A-Za-z0-9_{][A-Za-z0-9_\-.{}]*(?:/[A-Za-z0-9_\-.{}]*[A-Za-z0-9_}])+"
)
REVIEWED_SLASH_TOKENS = frozenset({
    "assisted/operator",
    "course/credential",
    "courses/memberships",
    "create/delete",
    "identity/grant/credential/SMS/resource",
    "login/credential",
    "Membership/course",
    "memberships/communities",
    "return/recovery",
    "shared-utils/ghl",
})
_SCHEMELESS_HOST = re.compile(r"\b(?:[a-z0-9][a-z0-9-]*\.)+[a-z][a-z0-9-]*(?::\d+)?/[A-Za-z0-9]")
_DOTTED_OPERATION = re.compile(r"\b[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+\b")
_FILE_SUFFIXES = (
    ".py", ".md", ".json", ".txt", ".sh", ".yml", ".yaml", ".toml", ".cfg",
    ".ini", ".html", ".js", ".ts", ".css", ".csv", ".xml", ".png", ".jpg",
)
_TRAILING_SEGMENT = re.compile(
    r"(?<![A-Za-z0-9_\-.{}/])[A-Za-z0-9_{][A-Za-z0-9_\-.{}]*/(?![A-Za-z0-9_\-.{}/])"
)
# A bare verb with a slash behind it is a verb, never an operation.
_HTTP_VERBS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"})

# Role beats shape. Whatever a token names -- a real file, a reviewed sentence,
# anything -- behind one of these keys it is an operation VALUE, and no
# provenance or prose exemption survives that position. This is the class the
# PBB-260 defects shared: the exemptions were keyed on what the token looked
# like and applied whatever role the token was playing.
_VALUE_POSITION = re.compile(
    r"""(?ix)
    ["']?(?:api|route|operation|endpoint|method|path|url|uri|action)["']?
    \s*[:=|]\s*["']?$
    """
)

# The exact sentence each reviewed slash token was reviewed in. This is the
# closed world: outside one of these sentences the token is an operation shape
# like any other, so `assisted/operator` is prose in its own sentence and a
# fabrication in an `api` value. Every sentence here appears in the module, the
# evidence doc, the returned surface, or the probe's own prose control; none of
# them is a substring of any smuggle shape below.
REVIEWED_PROSE_CONTEXTS = frozenset({
    ' observed mobile-only login/credential/ return/recovery. Onl',
    '. Supported path is **assisted/operator**. **Code:** `shared-',
    'IVE-community.md`). - Membership/course surfaces are browser-',
    'The supported path is assisted/operator: the owner creates th',
    'bonus access adapter (identity/grant/credential/SMS/resource authorization, failed',
    'est passed both with `shared-utils/ghl` present and with it ',
    'ive probe proving the course/credential create operations are',
    'mberships tools whose create/delete " "entries are docume',
    'mberships tools whose create/delete entries are documente',
    'mmunity-MCP list (~15 courses/memberships tools whose create/de',
    'nly login/credential/ return/recovery. Only then does `SUPP',
    'rships tools) and its create/delete entries are documente',
    'sing": ["a documented memberships/communities operation in the froz',
    'ssing:** a documented memberships/communities operation in the froz',
    'ssing=( "a documented memberships/communities operation in the froz',
    'the assisted/operator path and the R-13 / D',
    'tity": ["a documented memberships/communities operation in the froz',
})

# The delivered prose may not promise more than the scan delivers. Each pattern
# is a whole CLASS of absolute claim, not one frozen literal, so the guard can
# see an overstatement it has not seen before.
OVERSTATED_GUARANTEES = (
    r"cannot\s+(?:slip|reach|enter|appear|get|creep|sneak)",
    r"\b(?:no|any)\s+fabricat\w+\s+(?:can|could|will|would|shall)\b",
    r"\bfabricat\w+\s+(?:can(?:not)?\s+)?never\s+(?:reach|enter|appear)",
    r"\b(?:always|invariably|unfailingly)\s+(?:caught|flagged|rejected|fails)",
    r"\bguarantee[sd]?\s+(?:that\s+)?(?:no|nothing|none)\b",
    r"\bimpossible\s+to\s+(?:slip|add|introduce|sneak|smuggle)",
    r"\b(?:100|101)\s*%\s*(?:coverage|detection)",
    r"\bnothing\s+can\s+(?:slip|pass|reach|enter)",
    r"\bcatch(?:es)?\s+every\s+(?:possible|shape|fabrication|case|form)",
    r"\bevery\s+fabricat\w+\s+(?:is|are|will\s+be)\s+(?:caught|flagged|rejected)",
)
_OVERSTATED_RE = tuple(re.compile(p, re.I) for p in OVERSTATED_GUARANTEES)
# What the prose must state so a reader knows what the scan does not cover.
REQUIRED_GUARANTEE_SCOPE = (
    "pattern scan, not a proof",
    "is not caught",
    "closed world",
    "fails until a human reviews",
)


def _overstated_guarantee_hits(text):
    return [m.group(0) for rx in _OVERSTATED_RE for m in rx.finditer(text)]


_REPO_FILES = None


def _repo_files():
    """Every regular file in this tree, repo-relative. The tree is fixed here."""
    global _REPO_FILES
    if _REPO_FILES is None:
        _REPO_FILES = frozenset(
            str(p.relative_to(_REPO))
            for p in _REPO.rglob("*")
            if p.is_file() and ".git" not in p.parts
        )
    return _REPO_FILES


def _is_real_file_name(name):
    """`name` is the tail of a real path in this tree (a cited file, or a
    fragment of one such as a basename)."""
    return any(p == name or p.endswith(name) for p in _repo_files())


def _is_real_path_suffix(name):
    """`name` is a real path with its leading directory taken off.

    Stricter than `_is_real_file_name`: a bare basename is never enough, so a
    template path may only be provenance when the part behind the variable is
    genuinely a path segment run of a real file.
    """
    return "/" in name and any(p.endswith(name) for p in _repo_files())


def _in_api_value(text, start):
    """True when the token at `start` sits in an operation value position."""
    return _VALUE_POSITION.search(text[max(0, start - 200):start]) is not None


def _resolves_to_real_file(token):
    """File provenance, closed world.

    A literal path must be a real file in this tree. A path built from an
    f-string variable is provenance only when the part behind the template head
    is the tail of a real path. A name with no path behind it (`shared-utils/ghl`)
    is a directory at best and never file provenance.
    """
    if token in _repo_files():
        return True
    head, _, rest = token.partition("/")
    if not rest:
        return False
    if re.fullmatch(r"\{[_A-Za-z][_A-Za-z0-9]*\}", head):
        return _is_real_path_suffix(rest)
    return False


def _is_file_provenance(token):
    # A suffix alone proves nothing: `memberships/grant.py` ends in `.py` and is
    # still a fabricated operation. The suffix only says where to look.
    return token.lower().endswith(_FILE_SUFFIXES) and _resolves_to_real_file(token)


def _in_reviewed_prose(text, start, end):
    token = text[start:end]
    for phrase in REVIEWED_PROSE_CONTEXTS:
        offset = phrase.find(token)
        while offset != -1:
            at = start - offset
            if at >= 0 and text[at: at + len(phrase)] == phrase:
                return True
            offset = phrase.find(token, offset + 1)
    return False

# Every smuggle shape a fabricated interface has been seen to take. The scan
# must catch all of them; the table below is the proof it does.
#
# FIXTURES, NOT DELIVERABLE: these literals are attack inputs, and this test
# file is the only file in shared-utils/bonus/ allowed to carry an API-shaped
# string. `test_the_evidence_doc_carries_no_api_shape` and
# `test_module_source_carries_no_api_shape` keep the other files at zero.
SMUGGLE_SHAPES = (
    ("scheme url", "https://api.leadconnectorhq.com/v1/memberships/grant"),
    ("uppercase verb+path", "GET  /memberships/grant"),
    ("lowercase verb+path", "post /memberships/grant"),
    ("bare operation path", '"api": "/memberships/grant"'),
    ("schemeless host+path", "api.leadconnectorhq.com/v1/memberships/grant"),
    ("dotted operation id", '"api": "memberships.grant"'),
    # PBB-132 QC: an identifier glued in front of the `/` defeated every rule.
    ("glued uppercase verb+path", "POST/memberships/grant"),
    ("glued lowercase verb+path", "post/memberships/grant"),
    ("glued mixed-case verb+path", "Get/memberships/grant"),
    ("glued delete verb+path", "DELETE/memberships/grant"),
    ("version-prefixed path", "v1/memberships/grant"),
    ("api-prefixed path", "api/memberships/grant"),
    ("unprefixed operation path", "memberships/grant"),
    ("identifier-prefixed path", "x/memberships/grant"),
    # PBB-260 QC: an exemption keyed on the token's shape alone laundered a
    # fabricated API past the scan. These are the shapes it admitted, plus the
    # operation family with its operation cut off.
    ("file-suffix laundering .py", "memberships/grant.py"),
    ("file-suffix laundering .json", "memberships/grant.json"),
    ("file-suffix laundering .md", "v1/memberships/grant.md"),
    ("file-suffix laundering .sh", "x/memberships/grant.sh"),
    ("file-suffix laundering .yml", "api/tools/memberships_grant.yml"),
    ("file-suffix laundering .txt", "identity/grant/credential.txt"),
    ("file-suffix laundering .html", "courses/memberships.html"),
    ("dotted-id file-suffix laundering", "memberships.grant.py"),
    ("reviewed token as a bare api value", "assisted/operator"),
    ("reviewed token as a bare api value 2", "memberships/communities"),
    ("reviewed token as a bare api value 3", "return/recovery"),
    ("reviewed token as a bare api value 4", "identity/grant/credential/SMS/resource"),
    ("reviewed token as a bare api value 5", "shared-utils/ghl"),
    ("reviewed token behind an api key", "api: courses/memberships"),
    ("reviewed token behind a route key", '"route": "login/credential"'),
    ("file-suffix behind an api key", "api: memberships/grant.py"),
    ("real file behind an api key", "api: shared-utils/bonus/access_capability.py"),
    ("trailing path segment", "memberships/"),
)

# Text that must NOT be flagged: real repo provenance and plain prose.
LEGITIMATE_TEXT = (
    "#!/usr/bin/env python3",
    '    _REGISTRY = f"{_GHL}/tools/engine/cli_anything/gohighlevel/public/operations.py"',
    "44-convert-and-flow-operator/tools/engine/cli_anything/gohighlevel/public/operations.py",
    "shared-utils/ghl/capability_inventory.py",
    "05-ghl-setup/INSTRUCTIONS.md",
    "06-ghl-install-pages/tools/SELECTORS-LIVE-course.md",
    "36-ghl-mcp-setup/ghl-mcp-setup-full.md",
    "the assisted/operator path and the R-13 / DEC-16 authority",
    "select_route(OpClass.EXECUTE, resource=\"memberships\") returns []",
    "in the frozen v3 production spec, contact enrollment against an existing "
    "workflow is not authoring",
)


def _scan_text(text):
    """The text the scan runs over.

    Whitespace is normalised first: the same sentence wraps across lines in the
    module and sits on one line in the evidence doc and in the returned surface,
    and the reviewed prose contexts below are captured from the normalised form.
    A non-string is refused with the domain error, never a bare `TypeError` out
    of a regex.
    """
    if not isinstance(text, str):
        raise ac.BonusCapabilityError(
            f"api shape scan takes text, got {type(text).__name__}"
        )
    return re.sub(r"\s+", " ", text)


def _dotted_operation_hits(text):
    text = _scan_text(text)
    hits = []
    for match in _DOTTED_OPERATION.finditer(text):
        token = match.group(0)
        if _in_api_value(text, match.start()):
            hits.append(token)  # a value is never filename provenance
            continue
        # Provenance, closed world: only a name that is the tail of a real path
        # in this tree is a filename fragment of a cited file. The greedy match
        # above is the defence -- `memberships.grant.py` is ONE token and no real
        # path ends with it, while `operations.py` is the tail of the provenance
        # file the surface actually cites.
        if token.lower().endswith(_FILE_SUFFIXES) and _is_real_file_name(token):
            continue
        hits.append(token)
    return hits


def _api_shape_hits(text):
    """API shapes that cannot be legitimate in this module's source or surface."""
    text = _scan_text(text)
    hits = [f"url:{m.group(0)}" for m in _URL.finditer(text)]
    hits += [f"verb+path:{m.group(0)}" for m in _VERB_PATH.finditer(text)]
    for match in _BARE_PATH.finditer(text):
        token = match.group(0)
        if _in_api_value(text, match.start()):
            hits.append(f"bare-path:{token}")  # a value is never provenance
            continue
        if not token.startswith("/") and (
            _is_file_provenance(token)
            or (
                token in REVIEWED_SLASH_TOKENS
                and _in_reviewed_prose(text, match.start(), match.end())
            )
        ):
            continue  # file provenance or reviewed prose, not an operation
        hits.append(f"bare-path:{token}")
    for match in _TRAILING_SEGMENT.finditer(text):
        token = match.group(0)
        if token.rstrip("/").upper() in _HTTP_VERBS:
            continue  # `POST/` is a verb with no path behind it, not an operation
        hits.append(f"partial-path:{token}")
    hits += [f"host+path:{m.group(0)}" for m in _SCHEMELESS_HOST.finditer(text)]
    return hits


def _fabricated_api_hits(text):
    return _api_shape_hits(text) + [
        f"operation-id:{t}" for t in _dotted_operation_hits(text)
    ]


class _BlockImport:
    """meta_path finder that makes `import ghl...` genuinely raise ImportError."""

    def find_spec(self, fullname, path=None, target=None):
        if fullname == "ghl" or fullname.startswith("ghl."):
            raise ImportError(f"blocked for this test: {fullname}")
        return None


class TestCapabilityBlock(unittest.TestCase):
    """C-14: the exact block, announced rather than an invented interface."""

    def test_every_step_is_declared_exactly_once_in_order(self):
        self.assertEqual(list(ac.STEP_ORDER), ["identity", "grant", "credential", "return", "recovery"])
        self.assertEqual([e.step for e in ac.EVIDENCE], list(ac.STEP_ORDER))

    def test_all_five_steps_are_blocked_today(self):
        self.assertEqual(ac.blocked_steps(), list(ac.STEP_ORDER))

    def test_every_step_names_the_exact_missing_evidence(self):
        for step, row in ac.capability_evidence().items():
            self.assertFalse(row["routable"], f"{step} was promoted to routable")
            self.assertTrue(row["missing"], f"{step} names no missing evidence")
            for clause in row["missing"]:
                self.assertTrue(str(clause).strip(), f"{step} carries a blank missing clause")
            self.assertTrue(row["authority"], f"{step} cites no authority")
            self.assertTrue(row["claim"].strip(), f"{step} carries no claim")

    def test_every_provenance_file_exists_in_this_tree(self):
        for step, row in ac.capability_evidence().items():
            self.assertTrue(row["provenance"], f"{step} cites no provenance")
            for rel in row["provenance"]:
                self.assertFalse(os.path.isabs(rel), f"{step} provenance must be repo-relative: {rel}")
                self.assertTrue(
                    (_REPO / rel).is_file(), f"{step} provenance does not exist: {rel}"
                )

    def test_no_step_is_proved_or_claims_a_tenant_observation(self):
        for step, row in ac.capability_evidence().items():
            self.assertNotEqual(row["state"], ac.PROVED, step)
            self.assertNotIn("verified on this box", row["claim"].lower(), step)


class TestNoFabricatedApi(unittest.TestCase):
    """C-14: no fabricated API anywhere in the route surface."""

    def test_supported_route_exposes_no_api(self):
        route = ac.supported_route()
        self.assertIsNone(route["api"])
        self.assertTrue(route["no_invented_api"])
        self.assertNotIn("endpoint", route["supported_path"].lower())

    def test_route_values_contain_no_url_or_verb_path(self):
        blob = json.dumps(ac.supported_route(), sort_keys=True)
        self.assertIsNone(re.search(r"https?://", blob))
        self.assertIsNone(re.search(r"\b(?:GET|POST|PUT|PATCH|DELETE)\s+/[A-Za-z0-9{]", blob))

    def test_module_source_carries_no_url_or_verb_path(self):
        source = Path(ac.__file__).read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"https?://", source), "module carries a URL")
        self.assertIsNone(
            re.search(r"\b(?:GET|POST|PUT|PATCH|DELETE)\s+/[A-Za-z0-9{]", source),
            "module carries a verb+path operation",
        )

    def test_membership_family_has_no_route_in_the_shared_inventory(self):
        # Reuse of the upstream inventory, not a second local table.
        self.assertEqual(ac.membership_inventory_routes(), [])
        # Instrument control on the negative: the SAME call path answers
        # non-empty for a family the inventory does document, so the zero above
        # is discriminating and not a broken instrument reported as a block.
        from ghl import capability_inventory as inventory

        control = inventory.select_route(
            inventory.OpClass.EXECUTE, resource="workflows", dynamic_confirmed=False
        )
        self.assertTrue(
            control,
            "shared inventory answered nothing for a documented family — "
            "the memberships zero is a broken instrument, not a capability block",
        )

    def test_a_broken_reuse_path_fails_closed_and_is_never_a_capability_block(self):
        # A missing inventory is an instrument failure. Returning [] for it would
        # make a broken reuse path indistinguishable from a proven "no route".
        # The cached modules are dropped first so the import genuinely re-runs
        # and the blocker is what fails it, not a stale sys.modules entry.
        saved = {k: v for k, v in sys.modules.items() if k == "ghl" or k.startswith("ghl.")}
        for name in saved:
            del sys.modules[name]
        sys.meta_path.insert(0, _BlockImport())
        try:
            with self.assertRaises(ac.BonusCapabilityError):
                ac.membership_inventory_routes()
        finally:
            sys.meta_path.pop(0)
            sys.modules.update(saved)
        # Inverse: with the inventory reachable again, the honest answer is
        # still the empty list — the block is real, not an import artifact.
        self.assertEqual(ac.membership_inventory_routes(), [])

    def test_route_surface_carries_no_api_shape_at_all(self):
        # `api` is None, so any API-shaped token anywhere in what the module
        # hands back is a fabrication. Zero tolerance for every enumerated shape.
        for name, blob in (
            ("supported_route", json.dumps(ac.supported_route(), sort_keys=True)),
            ("decision_document", json.dumps(ac.decision_document(), sort_keys=True)),
        ):
            self.assertEqual(_fabricated_api_hits(blob), [], name)

    def test_module_source_carries_no_api_shape(self):
        source = Path(ac.__file__).read_text(encoding="utf-8")
        self.assertEqual(_api_shape_hits(source), [], "module source carries an API shape")

    def test_the_evidence_doc_carries_no_api_shape(self):
        doc = (_BONUS / "BONUS-ACCESS-CAPABILITY-DECISION.md").read_text(encoding="utf-8")
        self.assertEqual(_api_shape_hits(doc), [], "evidence doc carries an API shape")

    def test_no_other_bonus_file_carries_an_api_shape(self):
        # The whole deliverable is scanned, so nothing can hide beside the
        # module. The attack fixtures above are the single sanctioned exception.
        for path in sorted(_BONUS.rglob("*")):
            if not path.is_file() or path.name == "test_access_capability.py":
                continue
            if path.suffix not in (".py", ".md", ".json", ".txt"):
                continue
            text = path.read_text(encoding="utf-8")
            self.assertEqual(_api_shape_hits(text), [], str(path.relative_to(_REPO)))

    def test_the_scan_catches_every_known_smuggle_shape(self):
        for name, shape in SMUGGLE_SHAPES:
            self.assertTrue(
                _fabricated_api_hits(shape), f"{name} passes the scan uncaught"
            )

    def test_the_scan_leaves_legitimate_text_alone(self):
        # The inverse: a stricter scan must not become a blanket refusal. Real
        # provenance paths, filenames and plain prose carry no fabricated API.
        for text in LEGITIMATE_TEXT:
            self.assertEqual(_fabricated_api_hits(text), [], text[:60])

    def test_the_scan_guarantee_is_not_overstated(self):
        # A pattern scan catches the enumerated shapes; it is not a proof that
        # nothing can slip in, and the delivered prose may not promise more.
        for name, path in (
            ("module", Path(ac.__file__)),
            ("evidence doc", _BONUS / "BONUS-ACCESS-CAPABILITY-DECISION.md"),
        ):
            flat = " ".join(path.read_text(encoding="utf-8").split())
            self.assertNotIn("cannot slip a fabricated", flat, name)
            self.assertIn("pattern scan, not a proof", flat, name)
            # PBB-260: two fixed literals cannot see an overstatement they have
            # not met before. The guard classifies absolute detection claims by
            # class instead, so a fresh one fails here.
            self.assertEqual(_overstated_guarantee_hits(flat), [], name)
            for clause in REQUIRED_GUARANTEE_SCOPE:
                self.assertIn(clause, flat, f"{name} stopped stating: {clause}")

    def test_supported_route_reports_the_block_reason(self):
        route = ac.supported_route()
        self.assertFalse(route["available"])
        self.assertFalse(route["advertised_bonus_ready"])
        self.assertEqual(route["reason_code"], ac.BLOCK_REASON)
        self.assertEqual(route["route"], "assisted_operator")


class TestRequestRefusal(unittest.TestCase):
    """C-14: an unattended grant is refused, never silently downgraded."""

    def test_unattended_request_is_refused_with_the_exact_block(self):
        result = ac.request_bonus_access(unattended=True)
        self.assertFalse(result["granted"])
        self.assertTrue(result["refused"])
        self.assertEqual(result["route"], "refused")
        self.assertEqual(result["reason_code"], ac.BLOCK_REASON)
        self.assertEqual(result["blocked_steps"], list(ac.STEP_ORDER))
        self.assertTrue(result["no_silent_downgrade"])
        for step in ac.STEP_ORDER:
            self.assertIn(step, result["reason"])

    def test_refusal_offers_exactly_the_assisted_route(self):
        offer = ac.request_bonus_access(unattended=True)["offer"]
        self.assertEqual(offer["route"], "assisted_operator")
        self.assertEqual(offer["next"], "prepare_operator_instruction")

    def test_assisted_request_awaits_the_operator_and_has_no_receipt(self):
        result = ac.request_bonus_access(unattended=False)
        self.assertFalse(result["granted"])
        self.assertFalse(result["refused"])
        self.assertEqual(result["route"], "assisted_operator")
        self.assertEqual(result["status"], "awaiting-operator")
        self.assertIsNone(result["receipt"])
        self.assertFalse(result["system_claimed_grant"])
        self.assertEqual(result["blocked_steps"], list(ac.STEP_ORDER))

    def test_non_bool_unattended_is_refused(self):
        for value in ("yes", 1, None):
            with self.assertRaises(ac.BonusCapabilityError):
                ac.request_bonus_access(unattended=value)  # type: ignore[arg-type]


class TestOriginalGiftIndependence(unittest.TestCase):
    """C-F07: the original gift proceeds while the bonus is unavailable."""

    def test_original_is_ready_while_bonus_is_unavailable(self):
        plan = ac.plan_fulfillment(original_ready=True)
        self.assertTrue(plan["original"]["ready"])
        self.assertEqual(plan["original"]["route"], "direct_chat")
        self.assertFalse(plan["original"]["blocked_by_bonus"])
        self.assertFalse(plan["original"]["depends_on_bonus"])
        self.assertFalse(plan["bonus"]["available"])
        self.assertFalse(plan["advertised_bonus_ready"])
        self.assertEqual(plan["continuation"], "original_only")

    def test_a_not_ready_original_names_its_own_reason_never_the_bonus(self):
        plan = ac.plan_fulfillment(
            original_ready=False, original_reason="asset not yet approved for release"
        )
        self.assertFalse(plan["original"]["ready"])
        self.assertEqual(plan["original"]["reason"], "asset not yet approved for release")
        self.assertFalse(plan["original"]["blocked_by_bonus"])
        self.assertEqual(plan["continuation"], "original_repair")
        self.assertNotIn("bonus", plan["original"]["reason"].lower())

    def test_a_not_ready_original_must_name_its_reason(self):
        for reason in ("", "   "):
            with self.assertRaises(ac.BonusCapabilityError):
                ac.plan_fulfillment(original_ready=False, original_reason=reason)

    def test_original_lane_is_identical_when_the_bonus_lane_changes(self):
        # Prove no coupling: even a hypothetical proved bonus cannot move the
        # original lane. Same inputs must yield the same original dict.
        before = ac.plan_fulfillment(original_ready=True)["original"]
        proved = {
            "available": True,
            "route": "unattended",
            "blocked_steps": [],
            "missing_evidence": {},
            "api": None,
            "no_invented_api": True,
            "advertised_bonus_ready": True,
        }
        with _patched_route(proved):
            after_plan = ac.plan_fulfillment(original_ready=True)
        self.assertEqual(before, after_plan["original"])
        self.assertEqual(after_plan["continuation"], "original_and_bonus")

    def test_the_guard_rejects_a_hand_built_coupled_plan(self):
        coupled = ac.plan_fulfillment(original_ready=True)
        coupled["original"]["blocked_by_bonus"] = True
        with self.assertRaises(ac.BonusCouplingError):
            ac.assert_original_not_gated_by_bonus(coupled)
        coupled = ac.plan_fulfillment(original_ready=True)
        coupled["original"]["depends_on_bonus"] = True
        with self.assertRaises(ac.BonusCouplingError):
            ac.assert_original_not_gated_by_bonus(coupled)
        with self.assertRaises(ac.BonusCouplingError):
            ac.assert_original_not_gated_by_bonus({"bonus": {}})

    def test_non_bool_plan_inputs_are_refused(self):
        for kwargs in (
            {"original_ready": "true"},
            {"original_ready": True, "bonus_requested": "no"},
        ):
            with self.assertRaises(ac.BonusCapabilityError):
                ac.plan_fulfillment(**kwargs)  # type: ignore[arg-type]

    def test_the_guard_refuses_a_malformed_plan_with_the_domain_error(self):
        # The guard's job is to reject a bad plan. It must not answer a bad plan
        # with a bare AttributeError from duck-typed attribute access.
        for bad in (None, [], "plan", 1, object()):
            with self.assertRaises(ac.BonusCapabilityError):
                ac.assert_original_not_gated_by_bonus(bad)  # type: ignore[arg-type]
        # Inverse: a well-formed plan still passes the guard.
        self.assertTrue(
            ac.assert_original_not_gated_by_bonus(ac.plan_fulfillment(original_ready=True))
        )

    def test_a_not_ready_original_reason_must_be_a_real_string(self):
        # No silent coercion: str(None) would store the literal "None" as the
        # member-facing reason a not-ready lane is required to name.
        for reason in (None, 12345, [], {}, True):
            with self.assertRaises(ac.BonusCapabilityError):
                ac.plan_fulfillment(
                    original_ready=False, original_reason=reason
                )  # type: ignore[arg-type]
        # Inverse: a real reason still plans, and is stored verbatim minus padding.
        plan = ac.plan_fulfillment(
            original_ready=False, original_reason="  asset pending release  "
        )
        self.assertEqual(plan["original"]["reason"], "asset pending release")


class TestCredentialVersusResource(unittest.TestCase):
    """R-13: an expired credential is not expired guides."""

    def test_expired_credential_does_not_close_authorized_guides(self):
        state = ac.resolve_member_state(credential_state="expired", resource_authorized=True)
        self.assertFalse(state["credential_valid"])
        self.assertTrue(state["resource_available"])
        self.assertFalse(state["conflated"])
        self.assertIn("nothing about the guides", state["statement"])

    def test_valid_credential_does_not_authorize_guides(self):
        state = ac.resolve_member_state(credential_state="valid", resource_authorized=False)
        self.assertTrue(state["credential_valid"])
        self.assertFalse(state["resource_available"])

    def test_resource_availability_ignores_the_credential_on_every_state(self):
        for cred in ac.CREDENTIAL_STATES:
            self.assertTrue(
                ac.resolve_member_state(credential_state=cred, resource_authorized=True)[
                    "resource_available"
                ],
                cred,
            )
            self.assertFalse(
                ac.resolve_member_state(credential_state=cred, resource_authorized=False)[
                    "resource_available"
                ],
                cred,
            )

    def test_unknown_credential_state_is_refused(self):
        for value in ("good", "", None, "expir'd"):
            with self.assertRaises(ac.BonusCapabilityError):
                ac.resolve_member_state(credential_state=value, resource_authorized=True)  # type: ignore[arg-type]

    def test_uppercase_and_padded_credential_state_is_normalised(self):
        state = ac.resolve_member_state(credential_state=" EXPIRED ", resource_authorized=True)
        self.assertEqual(state["credential_state"], "expired")

    def test_non_bool_authorization_is_refused(self):
        for value in ("true", 1, None):
            with self.assertRaises(ac.BonusCapabilityError):
                ac.resolve_member_state(credential_state="valid", resource_authorized=value)  # type: ignore[arg-type]


class TestDecisionDocument(unittest.TestCase):
    def test_document_is_serialisable_and_self_consistent(self):
        doc = ac.decision_document()
        blob = json.dumps(doc, sort_keys=True)
        round_trip = json.loads(blob)
        self.assertEqual(round_trip["verdict"], "BLOCKED")
        self.assertEqual(round_trip["blocked_steps"], list(ac.STEP_ORDER))
        self.assertEqual(round_trip["steps"], list(ac.STEP_ORDER))
        self.assertEqual(round_trip["check_ids"], ["C-14", "C-F07"])
        self.assertTrue(round_trip["original_gift_independent"])
        self.assertIsNone(round_trip["route"]["api"])
        self.assertEqual(set(round_trip["evidence"]), set(ac.STEP_ORDER))


class TestEvidenceWording(unittest.TestCase):
    """The workflow ceiling is scoped, not stated as an absolute.

    The frozen registry carries v3 workflow rows that are NOT read-only (contact
    enrollment and unenrollment against an existing workflow), and the
    definition-authoring rows sit at staging-doc level. An absolute "read-only"
    claim overstates the registry it cites as authority. The ceiling that is
    true is the authoring ceiling in the frozen v3 production spec.
    """

    UNQUALIFIED_CLAIMS = (
        "cannot build or edit a workflow at all",
        "its only workflow operation is the read-only list",
        "workflows are read-only there",
        "workflows read-only on the public API",
    )
    QUALIFIERS = ("frozen v3 production spec", "not authoring", "staging")

    def _doc(self):
        raw = (_BONUS / "BONUS-ACCESS-CAPABILITY-DECISION.md").read_text(encoding="utf-8")
        return re.sub(r"\s+", " ", raw)  # prose wraps across lines

    def test_the_evidence_doc_does_not_overstate_the_workflow_ceiling(self):
        doc = self._doc()
        for phrase in self.UNQUALIFIED_CLAIMS:
            self.assertNotIn(phrase, doc, f"unqualified claim left in the doc: {phrase}")
        for qualifier in self.QUALIFIERS:
            self.assertIn(qualifier, doc, f"scope qualifier missing from the doc: {qualifier}")

    def test_the_module_claim_is_scoped_the_same_way(self):
        source = Path(ac.__file__).read_text(encoding="utf-8")
        for phrase in self.UNQUALIFIED_CLAIMS:
            self.assertNotIn(phrase, source, f"unqualified claim left in the module: {phrase}")
        claim = ac.capability_evidence()["grant"]["claim"]
        self.assertIn("frozen v3 production spec", claim)
        self.assertIn("not authoring", claim)

    def test_the_scoped_ceiling_does_not_change_the_block(self):
        # Scoping the wording is not softening the decision: the enrollment rows
        # are not a membership grant, so the grant step stays blocked.
        evidence = ac.capability_evidence()
        self.assertEqual(evidence["grant"]["state"], ac.RETIRED_RAIL_ONLY)
        self.assertFalse(evidence["grant"]["routable"])
        self.assertEqual(ac.decision_document()["verdict"], "BLOCKED")


class _patched_route:
    """Context manager: replace supported_route with a hypothetical proved one."""

    def __init__(self, value):
        self.value = value
        self._orig = None

    def __enter__(self):
        self._orig = ac.supported_route
        ac.supported_route = lambda: dict(self.value)
        return self

    def __exit__(self, *exc):
        ac.supported_route = self._orig
        return False


class TestTheExemptionsAreClosedWorld(unittest.TestCase):
    """PBB-260: an exemption may not travel with the token alone.

    Both defects in that verdict were the same mistake twice -- file provenance
    and the reviewed prose list were keyed on what a token LOOKED like and then
    applied whatever role the token was playing. A fabricated API played the
    role of a filename, or of reviewed prose, and reached the returned surface,
    the module source and the whole-deliverable scan uncaught. These tests are
    the proof for each one: they fail on the reviewed bytes and pass here.
    """

    FILE_SUFFIX_LAUNDERING = (
        "memberships/grant.py",
        "memberships/grant.json",
        "v1/memberships/grant.md",
        "x/memberships/grant.sh",
        "api/tools/memberships_grant.yml",
        "identity/grant/credential.txt",
        "courses/memberships.html",
        "memberships.grant.py",
    )
    REVIEWED_TOKEN_LAUNDERING = (
        "assisted/operator",
        "memberships/communities",
        "return/recovery",
        "identity/grant/credential/SMS/resource",
        "shared-utils/ghl",
    )
    VALUE_TEMPLATES = (
        '"operation": "{}"',
        'api: {}',
        '"api": "{}"',
        'route={} ',
        '| api | {} |',
    )

    def test_a_file_suffix_alone_is_never_provenance(self):
        # A1. `.py` says where to look, not what the token is.
        for token in self.FILE_SUFFIX_LAUNDERING:
            self.assertTrue(_fabricated_api_hits(token), token)

    def test_a_reviewed_token_alone_is_never_prose(self):
        # A2. A bare token is a value, not the sentence it was reviewed in.
        for token in self.REVIEWED_TOKEN_LAUNDERING:
            self.assertTrue(_fabricated_api_hits(token), token)

    def test_no_exemption_survives_an_api_value_position(self):
        # The class both defects share. Whatever the token names -- a real file,
        # a reviewed sentence, anything -- behind an api-shaped key it is an
        # operation value and is flagged.
        for token in (
            "courses/memberships",
            "memberships/grant.py",
            "shared-utils/ghl",
            "assisted/operator",
            "shared-utils/bonus/access_capability.py",
            "05-ghl-setup/INSTRUCTIONS.md",
        ):
            for template in self.VALUE_TEMPLATES:
                text = template.format(token)
                self.assertTrue(_fabricated_api_hits(text), text)

    def test_the_file_exemption_needs_a_file_that_exists(self):
        # Provenance is a real path in this tree and nothing else.
        self.assertFalse(_fabricated_api_hits("shared-utils/ghl/capability_inventory.py"))
        self.assertFalse(_fabricated_api_hits("05-ghl-setup/INSTRUCTIONS.md"))
        self.assertTrue(_fabricated_api_hits("memberships/grant.py"))
        self.assertTrue(_fabricated_api_hits("v1/tools/engine/memberships_grant.py"))
        # An f-string variable is provenance only where the tail names a real
        # file, which is why the module's own three citations stay clean.
        self.assertFalse(_fabricated_api_hits(
            '_REGISTRY = f"{_GHL}/tools/engine/cli_anything/gohighlevel/public/operations.py"'
        ))
        self.assertTrue(_fabricated_api_hits(
            '_REGISTRY = f"{_GHL}/tools/engine/cli_anything/memberships_grant.py"'
        ))

    def test_the_reviewed_exemption_does_not_travel_outside_its_sentence(self):
        # Closed world: the list names the exact sentence each token was
        # reviewed in. A reworded sentence is not that sentence, so the token
        # is an operation shape again until a human reviews the new wording.
        for token in self.REVIEWED_TOKEN_LAUNDERING:
            self.assertTrue(_fabricated_api_hits(token), token)
            self.assertTrue(_fabricated_api_hits(f"see the {token} wording here"), token)
        self.assertFalse(_fabricated_api_hits(
            "the assisted/operator path and the R-13 / DEC-16 authority"
        ))

    def test_a_trailing_path_segment_is_caught_but_a_bare_verb_is_not(self):
        # Same class, one step wider: `memberships/` is the operation family with
        # its operation cut off and is still operation-shaped. `POST/` is a verb
        # with nothing behind it and is not an operation -- the inverse keeps the
        # stricter scan from becoming a blanket refusal.
        self.assertTrue(_fabricated_api_hits("memberships/"))
        self.assertTrue(_fabricated_api_hits("v1/memberships/"))
        self.assertFalse(_fabricated_api_hits("POST/"))
        self.assertFalse(_fabricated_api_hits("get/"))
        self.assertFalse(_fabricated_api_hits("DELETE/"))
        self.assertFalse(_fabricated_api_hits(""))
        self.assertFalse(_fabricated_api_hits("//"))
        # every verb plus a real path is still caught
        for verb in ("GET", "post", "Put", "PATCH", "DELETE", "Head", "OPTIONS"):
            self.assertTrue(_fabricated_api_hits(f"{verb}/memberships/grant"), verb)

    def test_the_scan_refuses_non_text_with_the_domain_error(self):
        # Defect C: a wrong type answers with the domain error, not a bare
        # TypeError thrown from inside a regex.
        for bad in (None, 123, 0.5, ["a/b"], {"a": "b/c"}, b"bytes", (1, 2)):
            for fn in (_api_shape_hits, _fabricated_api_hits, _dotted_operation_hits):
                with self.assertRaises(ac.BonusCapabilityError):
                    fn(bad)

    def test_the_scan_still_takes_text_of_every_shape(self):
        # Inverse for the type guard: real text still scans, and the shapes the
        # guard claims to catch are still caught.
        self.assertEqual(_api_shape_hits(""), [])
        self.assertEqual(_api_shape_hits("   \n\t "), [])
        self.assertTrue(_fabricated_api_hits("memberships/grant"))
        self.assertTrue(_fabricated_api_hits('"api": "/memberships/grant"'))

if __name__ == "__main__":
    unittest.main(verbosity=2)
