#!/usr/bin/env python3
"""run_book_writer.py — the deterministic assembler + certifier over BOOK-WRITER-MANIFEST.json.

Walks the Book Writer phases IN ORDER (P0-INTAKE -> P1-AVATAR -> P2-TONE ->
P3-TITLES-GATE -> P4-OUTLINE-GATE -> P5-CHAPTERS -> P6-PACKAGE -> P7-QC ->
P8-DELIVER) with NO phase skips. It reads the AUTHORED artifacts under
<run-dir>/run/ (intake.json, stories.json, artifacts/, chapters/, receipts/,
RUN-LEDGER.json), assembles the labeled delivery bundle under
<run-dir>/delivery/<First>_<Last>-Book/, runs the fail-closed provers in scripts/,
and — only on a full P0->P7 pass — mints PROCESS-CERTIFICATE.{json,md} with a
DETERMINISTIC certificate_sha over the MEASURED values (chapter count, per-chapter
stripped word counts, tone word count, challenge sections, title-lock, stories
placed, the ordered phase chain) — NOT the wall clock. Same authored input -> same
sha (the idempotency contract verify.sh checks).

Model-free, provider-neutral, stdlib only: it calls no LLM and no external service.
The two authoring layers (avatar/tone/titles/outline/chapters/challenge/cover) run
UPSTREAM on the CLIENT's own providers and drop their artifacts into <run-dir>/run/.

FRONT-DOOR NONCE: like Skill 55's run_product_bio.py, this refuses to run unless
OC_BOOK_WRITER_ENTRY_NONCE matches the run-scoped nonce minted by
book-writer-entry.sh (the ONE sanctioned entry).

EXIT CODES:
  0  all requested phases passed (certificate issued on a full P0->P8 run)
  2  a phase gate failed (fail-closed)  [AF-BK-STAGE-SKIPPED / a prover AF]
  3  usage / manifest error
  4  front-door nonce missing/mismatch (run through book-writer-entry.sh)
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import re
import shutil
import sys
from pathlib import Path

EXIT_PASS = 0
EXIT_GATE = 2
EXIT_USAGE = 3
EXIT_NONCE = 4

_SKILL_DIR = Path(__file__).resolve().parent
SCRIPTS = _SKILL_DIR / "scripts"
MANIFEST = _SKILL_DIR / "BOOK-WRITER-MANIFEST.json"

sys.path.insert(0, str(SCRIPTS))
import _bw_common as c            # noqa: E402
import prove_bw_intake as p_intake      # noqa: E402
import prove_bw_tone as p_tone          # noqa: E402
import prove_bw_titlelock as p_title    # noqa: E402
import prove_bw_stories as p_story      # noqa: E402
import prove_bw_chapters as p_chap      # noqa: E402
import prove_bw_continuity as p_cont    # noqa: E402
import prove_bw_challenge as p_chal     # noqa: E402
import prove_bw_placeholder as p_ph     # noqa: E402
import prove_bw_noanthropic as p_anth   # noqa: E402
import prove_bw_anon as p_anon          # noqa: E402
import prove_bw_433 as p_433            # noqa: E402

# F4.3 deterministic N/A tone-slot resolver (shared tone-writing-core). The
# prompt layer NO LONGER self-picks a persona on N/A — the runtime resolves
# those slots here, before any tone stage sees them. Import is best-effort at
# module load but FAIL-CLOSED inside resolve_tone_slots(): a missing resolver
# blocks P2 rather than letting a naked N/A reach tone authoring.
_SHARED_CORE = _SKILL_DIR.parent / "shared-utils" / "tone-writing-core"
if str(_SHARED_CORE) not in sys.path:
    sys.path.insert(0, str(_SHARED_CORE))
try:
    import tone_persona_autopick as tpa  # noqa: E402
except ImportError:  # pragma: no cover - surfaced fail-closed in check_tone
    tpa = None

PHASE_ORDER = ["P0-INTAKE", "P1-AVATAR", "P2-TONE", "P3-TITLES-GATE", "P4-OUTLINE-GATE",
               "P5-CHAPTERS", "P6-PACKAGE", "P7-QC", "P8-DELIVER"]

# The failing (phase_id, note) captured at a gate failure so the fail-soft board
# seam (_mc_board_blocked, FIX-XC-06) can move the card to `blocked` with the AF
# code as the note. Mutated in place (no `global`) — read only by the board seam.
_LAST_BLOCK: dict = {}


def _load_manifest():
    try:
        return json.loads(MANIFEST.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print("FATAL: cannot read BOOK-WRITER-MANIFEST.json: %s" % exc, file=sys.stderr)
        sys.exit(EXIT_USAGE)


def _nonce_ok(run_dir: Path) -> bool:
    want = os.environ.get("OC_BOOK_WRITER_ENTRY_NONCE", "")
    nf = run_dir / "run" / "checkpoints" / ".book-writer-entry-nonce"
    if not want or not nf.is_file():
        return False
    try:
        return nf.read_text(encoding="utf-8").strip() == want.strip()
    except OSError:
        return False


# The run-scoped checkpoint dir (same dir that holds the front-door nonce). Gate
# receipts + the mc-board receipt live here (NOT working/checkpoints).
RECEIPT_SUBDIR = ("run", "checkpoints")

_CHAPTER_NAME_RE = re.compile(r"^ch(\d+)\.md$")


class ChapterNamingError(ValueError):
    """A file in run/chapters/ is not named ch<N>.md (or chapter numbers collide)."""


def _iso_ts(value):
    """Parse an ISO-8601 timestamp (tolerating a trailing Z); None if unparseable."""
    s = str(value or "").strip()
    if not s:
        return None
    if s.endswith(("Z", "z")):
        s = s[:-1] + "+00:00"
    try:
        return datetime.datetime.fromisoformat(s)
    except ValueError:
        return None


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_gate_receipts(run_dir: Path) -> dict:
    """Return {gate_id: record} for every WELL-FORMED human-gate approval receipt
    (approved:true + a non-empty approved_by + a parseable ISO-8601 timestamp +
    an artifact_sha256 that matches the LIVE sha of the artifact the gate locked),
    mirroring Skill 48's owner-approval shape. A file-presence-only 'approval'
    authored by the pipeline is NOT sufficient — the gate reads the actual
    approved/approved_by/timestamp/artifact_sha256 fields, so an approval can
    never be back-filled or self-attested away. Receipts live at
    <run_dir>/run/checkpoints/gate-receipts.json (a single object with receipts[])
    or one JSON object per file under <run_dir>/run/checkpoints/gates/*.json."""
    approvals: dict = {}
    cdir = run_dir.joinpath(*RECEIPT_SUBDIR)
    candidates = []
    single = cdir / "gate-receipts.json"
    if single.is_file():
        candidates.append(single)
    gdir = cdir / "gates"
    if gdir.is_dir():
        candidates.extend(sorted(gdir.glob("*.json")))
    # gate_id -> the live artifact its receipt must be bound to (sha256)
    bound_artifacts = {
        "GATE-1-title": run_dir / "run" / "artifacts" / "APPROVED-TITLE.txt",
        "GATE-2-outline": run_dir / "run" / "artifacts" / "13-outline.md",
        "GATE-433": run_dir / "run" / "433" / "433_Deck_Data.json",
    }
    for path in candidates:
        try:
            obj = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(obj, dict) and "receipts" in obj:
            records = obj.get("receipts") or []
        elif isinstance(obj, list):
            records = obj
        else:
            records = [obj]
        for rec in records:
            if not isinstance(rec, dict):
                continue
            gid = rec.get("gate_id") or rec.get("phase_id")
            ts_raw = rec.get("approved_at") or rec.get("timestamp")
            if (not gid or rec.get("approved") is not True
                    or not str(rec.get("approved_by", "")).strip()
                    or _iso_ts(ts_raw) is None):
                continue
            artifact = bound_artifacts.get(gid)
            if artifact is None:
                approvals[gid] = rec  # gates without a bound artifact: fields only
                continue
            expected = str(rec.get("artifact_sha256") or "").strip().lower()
            live_sha = ""
            try:
                if artifact.is_file():
                    live_sha = _sha256_file(artifact)
            except OSError:
                live_sha = ""
            if not expected or not live_sha or expected != live_sha.lower():
                continue  # missing/mismatched binding = gate NOT satisfied (fail-closed)
            approvals[gid] = rec
    return approvals


def _gate_ok(approvals: dict, gate_id: str) -> bool:
    return gate_id in approvals


def _ledger_model_id_count(ledger) -> int:
    """Number of recorded string leaves anywhere in the ledger (uses the same walker
    the no-Anthropic gate uses — a model id may hide under any alias key)."""
    return sum(1 for _jp, _mid in p_anth._iter_string_leaves(ledger))


# manifest stage_id -> its produced artifact under run/ (None = not file-checkable).
# Degradable stages (optional revision rounds, IMAGE cover) are excluded: their whole
# point is that they may legitimately be absent.
_STAGE_ARTIFACTS = {
    "01-avatar-questions-1-30": "artifacts/01-avatar.md",
    "03-rewrite-avatar": "artifacts/01-avatar.md",
    "08-blended-tone": "artifacts/08-blended-tone.md",
    "10-suggested-titles": "artifacts/10-suggested-titles.md",
    "11-book-blurb": "artifacts/11-blurb.md",
    "12-chapter-titles": "artifacts/12-chapter-titles.md",
    "13-create-outline": "artifacts/13-outline.md",
    "15-write-chapters-b1": None,
    "16-write-chapters-b2": None,
    "17-write-chapters-b3": None,
    "18-write-chapters-b4": None,
    "21-30day-challenge": "artifacts/21-30day-challenge.md",
    "22-cover-prompt": "artifacts/22-cover-prompt.md",
}


def _ledger_stage_ids(ledger_obj):
    """Every stage id referenced anywhere in the ledger (stages[].stage, stage_id,
    or any string value keyed 'stage'/'stage_id'/'stage_ids')."""
    ids = set()

    def _walk(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k in ("stage", "stage_id") and isinstance(v, str) and v.strip():
                    ids.add(v.strip())
                elif k == "stage_ids" and isinstance(v, list):
                    ids.update(str(s).strip() for s in v
                               if isinstance(s, str) and s.strip())
                else:
                    _walk(v)
        elif isinstance(obj, list):
            for item in obj:
                _walk(item)

    _walk(ledger_obj)
    return ids


def _uncovered_stages(bk: Book, ledger_obj) -> list:
    """Manifest stages whose artifact exists on disk but which no ledger entry
    references. Chapter batches are covered when ANY chapter file exists."""
    recorded = _ledger_stage_ids(ledger_obj)
    uncovered = []
    for stage_id, rel in _STAGE_ARTIFACTS.items():
        if rel is not None:
            if not (bk.rd / rel).is_file():
                continue  # nothing produced -> nothing to demand coverage for
            if stage_id not in recorded and not any(
                    s.startswith(stage_id.rsplit("-", 1)[0]) for s in recorded):
                uncovered.append(stage_id)
        else:  # a chapter batch: covered iff any ch*.md exists on disk
            if bk.chapters_dir.is_dir() and any(bk.chapters_dir.glob("ch*.md")) \
                    and not any(s.startswith(stage_id.split("-")[0] + "-write-chapters")
                                for s in recorded):
                uncovered.append(stage_id)
    return uncovered


# ---- authored-zone accessors ------------------------------------------------
class Book:
    def __init__(self, run_dir: Path):
        self.run_dir = run_dir
        self.rd = run_dir / "run"
        self.artifacts = self.rd / "artifacts"
        self.chapters_dir = self.rd / "chapters"
        self.receipts = self.rd / "receipts"
        self.d433 = self.rd / "433"

    def intake(self):
        p = self.rd / "intake.json"
        return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}

    def author(self):
        i = self.intake()
        first = str(i.get("first_name", "First")).strip() or "First"
        last = str(i.get("last_name", "Last")).strip() or "Last"
        return first, last

    def slug(self):
        first, last = self.author()
        import re
        return re.sub(r"[^a-z0-9]+", "-", ("%s %s" % (first, last)).lower()).strip("-") or "book"

    def mode(self):
        return str(self.intake().get("mode", "full")).strip().lower() or "full"

    def chapter_files(self):
        """Digit-ordered ch<N>.md files (ch2 sorts after ch11, never before). Any
        non-conforming name in chapters_dir is a fail-closed error, as is a
        duplicate chapter number."""
        if not self.chapters_dir.is_dir():
            return []
        numbered = []
        for p in self.chapters_dir.iterdir():
            if not p.is_file():
                continue
            m = _CHAPTER_NAME_RE.match(p.name)
            if not m:
                raise ChapterNamingError(
                    "run/chapters/%s does not match the required ch<N>.md naming "
                    "(fail-closed; rename it or remove it)" % p.name)
            numbered.append((int(m.group(1)), p))
        seen = {}
        for num, p in sorted(numbered, key=lambda t: t[0]):
            if num in seen:
                raise ChapterNamingError(
                    "duplicate chapter number %d in run/chapters (%s and %s)"
                    % (num, seen[num].name, p.name))
            seen[num] = p
        return [p for _n, p in sorted(numbered, key=lambda t: t[0])]

    def manuscript_text(self, title, subtitle):
        parts = ["# %s\n## %s\n" % (title, subtitle)]
        for i, p in enumerate(self.chapter_files(), 1):
            body = p.read_text(encoding="utf-8")
            # normalize a "Chapter N" heading so chapter parsing is unambiguous
            parts.append("\n\n# Chapter %d\n\n%s" % (i, body))
        return "\n".join(parts)

    def title_subtitle(self):
        p = self.artifacts / "APPROVED-TITLE.txt"
        if not p.is_file():
            return "", ""
        return p_title.parse_approved_title(p.read_text(encoding="utf-8"))


# ---- phase checkers (return (ok, message, extra_dict)) ----------------------
def _phase_result(res: c.Result):
    return res.passed, ("PASS" if res.passed else "; ".join("%s:%s" % (cd, m)
                                                             for cd, m in res.violations))


def check_intake(bk: Book):
    i = bk.intake()
    if not i:
        return False, "missing run/intake.json", {}
    res = p_intake.evaluate(i)
    ok, msg = _phase_result(res)
    return ok, "intake %s" % msg, {}


def check_avatar(bk: Book):
    p = bk.artifacts / "01-avatar.md"
    if not p.is_file():
        return False, ("missing run/artifacts/01-avatar.md — FAIL-CLOSED: the book cannot "
                       "complete without the authored avatar dossier (authored by the baked "
                       "stage prompt; see prompts/01-avatar-questions-1-30)"), {}
    wc = c.word_count(p.read_text(encoding="utf-8"))
    if wc < 150:
        return False, ("run/artifacts/01-avatar.md measured %d stripped words, below the "
                       "150-word floor — FAIL-CLOSED: an empty/stub avatar dossier cannot "
                       "pass" % wc), {}
    # RESEARCHER-tier stage 02: its expected research artifact must exist OR carry a
    # degraded receipt — silence is not a degradation.
    research = bk.artifacts / "02-avatar-research.md"
    if not research.is_file():
        deg = _degraded_receipts(bk).get("02-avatar-questions-31-32")
        if not deg:
            return False, ("run/artifacts/02-avatar-research.md (RESEARCHER stage "
                           "02-avatar-questions-31-32) is ABSENT with no degraded receipt "
                           "— FAIL-CLOSED: produce the artifact, or write "
                           "run/checkpoints/degraded-receipts.json entry "
                           "{stage_id:'02-avatar-questions-31-32', reason, degraded:true}"), {}
    return True, "avatar dossier present (%d words)" % wc, {}


def resolve_tone_slots(bk: Book) -> tuple:
    """F4.3 na_autopick wiring: every intake tone_style_N slot resolves through the
    shared deterministic selector (client-named pass through untouched; N/A routed
    to persona_for_job). Writes run/checkpoints/persona-autopick.json as the audit
    trail. FAIL-CLOSED: resolver absent, an N/A slot unresolved, or a blend-governed
    directive missing its guardrail clause blocks the run (never a naked N/A)."""
    ckpt = bk.run_dir / "run" / "checkpoints" / "persona-autopick.json"
    i = bk.intake() or {}
    slots = {k: i.get(k) for k in ("tone_style_1", "tone_style_2",
                                   "tone_style_3", "tone_style_4")
             if k in i}
    if tpa is None:
        return False, ("tone_persona_autopick resolver not importable from "
                       "shared-utils/tone-writing-core — FAIL-CLOSED (F4.3): N/A tone "
                       "slots may never fall back to prompt-level self-pick"), {}
    if not any(tpa.is_na(v) for v in slots.values()):
        # Nothing to auto-pick; still record the pass-through so the audit trail
        # proves every slot was accounted for.
        record = {"resolved_by": "tone_persona_autopick", "slots": {}}
        try:
            ckpt.parent.mkdir(parents=True, exist_ok=True)
            ckpt.write_text(json.dumps(record, indent=2), encoding="utf-8")
        except OSError:
            pass
        return True, "no N/A tone slots (client-named only)", {}
    avatar_ctx = ""
    av = bk.artifacts / "01-avatar.md"
    if av.is_file():
        avatar_ctx = av.read_text(encoding="utf-8")[:8000]
    results = tpa.autopick([slots.get("tone_style_%d" % n) for n in (1, 2, 3, 4)],
                           avatar_ctx)
    problems = []
    for n, r in zip((1, 2, 3, 4), results):
        if r["mode"] == "auto-pick":
            if not r.get("persona_id"):
                problems.append("tone_style_%d resolved with NO persona_id" % n)
            if r.get("warning"):
                problems.append("tone_style_%d: %s" % (n, r["warning"]))
    record = {"resolved_by": "tone_persona_autopick",
              "slots": {"tone_style_%d" % n: r
                        for n, r in zip((1, 2, 3, 4), results)}}
    try:
        ckpt.parent.mkdir(parents=True, exist_ok=True)
        ckpt.write_text(json.dumps(record, indent=2), encoding="utf-8")
    except OSError:
        pass
    if problems:
        return False, ("N/A tone-slot resolution FAILED (%s) — FAIL-CLOSED: fix the "
                       "selector/persona library before re-run" % "; ".join(problems)), {}
    picked = ["%s->%s" % (k, v["persona_id"])
              for k, v in record["slots"].items() if v["mode"] == "auto-pick"]
    return True, ("N/A tone slots auto-resolved deterministically (%s); checkpoint "
                  "run/checkpoints/persona-autopick.json" % ", ".join(picked)), {}


def check_tone(bk: Book):
    ok, msg, extra = resolve_tone_slots(bk)
    print("=== PHASE P2-TONE :: persona-autopick === [%s] %s"
          % ("OK" if ok else "FAIL", msg))
    if not ok:
        return False, msg, extra
    p = bk.artifacts / "08-blended-tone.md"
    if not p.is_file():
        return False, ("missing run/artifacts/08-blended-tone.md — FAIL-CLOSED: the book "
                       "cannot complete without the authored blended tone"), {}
    res = p_tone.evaluate(p.read_text(encoding="utf-8"))
    ok2, msg2 = _phase_result(res)
    return ok2, "tone %s" % msg2, {"tone_word_count": c.word_count(p.read_text(encoding="utf-8"))}


def check_titles(bk: Book, approvals: dict):
    title, subtitle = bk.title_subtitle()
    if not title or not subtitle:
        return False, "missing/incomplete run/artifacts/APPROVED-TITLE.txt", {}
    if not _gate_ok(approvals, "GATE-1-title"):
        return False, ("GATE-1-title approval receipt missing/malformed "
                       "(need approved:true + approved_by + timestamp in "
                       "run/checkpoints/gate-receipts.json — a locked title cannot be self-attested)"), {}
    return True, "title locked + GATE-1 approved: %r / %r" % (title, subtitle), \
        {"title": title, "subtitle": subtitle}


def check_outline(bk: Book, approvals: dict):
    outline = bk.artifacts / "13-outline.md"
    stories = bk.rd / "stories.json"
    if not outline.is_file():
        return False, ("missing run/artifacts/13-outline.md — FAIL-CLOSED: the book cannot "
                       "complete without the authored outline (authored by the baked "
                       "stage prompt; see prompts/13-create-outline)"), {}
    if not stories.is_file():
        return False, "missing run/stories.json", {}
    if bk.mode() == "4x3x3" and not _gate_ok(approvals, "GATE-433"):
        return False, ("GATE-433 approval receipt missing/malformed (4x3x3 mode: the "
                       "30 titles + outcomes cannot advance without the client's "
                       "approved receipt — approved:true + approved_by + ISO timestamp "
                       "+ artifact_sha256 bound to run/433/433_Deck_Data.json)"), {}
    if not _gate_ok(approvals, "GATE-2-outline"):
        return False, ("GATE-2-outline approval receipt missing/malformed "
                       "(need approved:true + approved_by + timestamp in "
                       "run/checkpoints/gate-receipts.json — chapters cannot start before "
                       "the client approves the outline)"), {}
    title, subtitle = bk.title_subtitle()
    manuscript = bk.manuscript_text(title, subtitle)
    res = p_story.evaluate(json.loads(stories.read_text(encoding="utf-8")),
                           outline.read_text(encoding="utf-8"), manuscript)
    ok, msg = _phase_result(res)
    placed = sum(1 for s in json.loads(stories.read_text(encoding="utf-8"))
                 if isinstance(s, dict) and c.is_present(s.get("key_phrase")) and not c.is_na(s.get("key_phrase")))
    return ok, "stories %s" % msg, {"stories_placed": placed}


def check_chapters(bk: Book):
    files = bk.chapter_files()
    if not files:
        return False, ("no run/chapters/ch*.md — FAIL-CLOSED: the book cannot complete without "
                       "authored chapters (authored by the baked chapter-batch stage prompts; "
                       "see prompts/15-write-chapters-b1 … 18-write-chapters-b4)"), {}
    chap_texts = {}
    for p in files:
        # key by the DIGITS in the filename stem (ch07 -> 7) so the in-run numbering
        # matches the standalone provers (prove_bw_chapters --chapters-dir keys by digits)
        chap_texts[int(_CHAPTER_NAME_RE.match(p.name).group(1))] = p.read_text(encoding="utf-8")
    res_c = p_chap.evaluate(chap_texts)
    # continuity over receipts
    receipts = {}
    for stage, bnum, _ch in p_cont.BATCHES:
        rp = bk.receipts / ("G-STAGE-%s.json" % stage)
        if rp.is_file():
            try:
                receipts[bnum] = json.loads(rp.read_text(encoding="utf-8"))
            except ValueError:
                receipts[bnum] = {}
    chapter_sha = {n: hashlib.sha256(chap_texts[n].encode("utf-8")).hexdigest() for n in chap_texts}
    res_cont = p_cont.evaluate(receipts, chapter_sha)
    ok = res_c.passed and res_cont.passed
    msg = "chapters %s | continuity %s" % (_phase_result(res_c)[1], _phase_result(res_cont)[1])
    wc = {n: c.word_count(chap_texts[n]) for n in chap_texts}
    return ok, msg, {"chapter_count": len(chap_texts), "chapter_word_counts": wc}


def _degraded_receipts(bk: Book) -> dict:
    """{stage_id: receipt} from run/checkpoints/degraded-receipts.json (or a list)."""
    p = bk.run_dir.joinpath(*RECEIPT_SUBDIR) / "degraded-receipts.json"
    if not p.is_file():
        return {}
    try:
        obj = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    records = obj.get("receipts") if isinstance(obj, dict) else obj
    if not isinstance(records, list):
        return {}
    out = {}
    for rec in records:
        if isinstance(rec, dict) and str(rec.get("stage_id", "")).strip() \
                and rec.get("degraded") is True:
            out[str(rec["stage_id"]).strip()] = rec
    return out


def _anon_tokens(bk: Book):
    """Client-name denylist for the runtime anonymization lint. Supplied at
    delivery time by NAME only via env BW_ANON_TOKENS, or via a
    run/checkpoints/anon-tokens.txt file when the env is unset/empty (never
    checked into the fleet repo)."""
    tokens = []
    inline = os.environ.get("BW_ANON_TOKENS", "")
    if inline.strip():
        tokens += inline.split(",")
    else:
        tf = bk.run_dir.joinpath(*RECEIPT_SUBDIR) / "anon-tokens.txt"
        if tf.is_file():
            try:
                tokens += [ln for ln in tf.read_text(encoding="utf-8").splitlines()
                           if ln.strip()]
            except OSError:
                pass
    return [t for t in (s.strip() for s in tokens) if t]


def check_package(bk: Book, staging_dir: Path, approvals: dict):
    # challenge exactly 30
    ch = bk.artifacts / "21-30day-challenge.md"
    if not ch.is_file():
        return False, ("missing run/artifacts/21-30day-challenge.md — FAIL-CLOSED: the book "
                       "cannot complete without the authored 30-Day Challenge (authored by the "
                       "baked stage prompt; see prompts/21-30day-challenge)"), {}
    res_ch = p_chal.evaluate(ch.read_text(encoding="utf-8"))
    # cover prompt (manifest stage 22-cover-prompt, P6-PACKAGE, floor title_lock)
    cover = bk.artifacts / "22-cover-prompt.md"
    if not cover.is_file():
        return False, ("missing run/artifacts/22-cover-prompt.md — FAIL-CLOSED: the book "
                       "cannot complete without the authored cover prompt (P6-PACKAGE stage "
                       "22-cover-prompt declares floor title_lock; author it and re-run)"), {}
    # IMAGE-tier stage 23: the cover image is optional ONLY with an honest degraded
    # receipt — absence alone is never a degradation.
    cover_img = bk.artifacts / "23-cover-image.png"
    if not cover_img.is_file():
        deg = _degraded_receipts(bk).get("23-cover-image")
        if not deg:
            return False, ("run/artifacts/23-cover-image.png (IMAGE stage 23-cover-image) "
                           "is ABSENT with no degraded receipt — FAIL-CLOSED: render the "
                           "cover, or write run/checkpoints/degraded-receipts.json entry "
                           "{stage_id:'23-cover-image', reason, degraded:true}"), {}
    # BUG-5 FAIL-CLOSED: the blurb, suggested titles, and chapter titles are REQUIRED
    # P6-PACKAGE deliverables — the certificate must never claim all_phases_pass
    # without them. Mirrors the hard requirement on 21-30day-challenge.md above.
    _FLOORS = {"10-suggested-titles.md": 30, "11-blurb.md": 100,
               "12-chapter-titles.md": 60, "22-cover-prompt.md": 50}
    for rel in ("10-suggested-titles.md", "11-blurb.md", "12-chapter-titles.md"):
        req = bk.artifacts / rel
        if not req.is_file():
            return False, ("missing run/artifacts/%s — FAIL-CLOSED: the book cannot "
                           "complete without the authored %s (authoring stage deferred "
                           "to a scoped follow-up campaign; see SKILL.md 'SHIPPED vs. "
                           "PENDING')" % (rel, rel)), {}
    for rel, floor in sorted(_FLOORS.items()):
        fp = bk.artifacts / rel
        if not fp.is_file():  # cover-prompt presence already enforced above
            continue
        wc = c.word_count(fp.read_text(encoding="utf-8"))
        if wc < floor:
            return False, ("run/artifacts/%s measured %d stripped words, below its %d-word "
                           "floor — FAIL-CLOSED: an empty/stub artifact cannot pass"
                           % (rel, wc, floor)), {}
    # title-lock across required artifacts (a required target absent from disk is an
    # explicit fail-closed violation — never a silent skip)
    title, subtitle = bk.title_subtitle()
    targets = {}
    for label, rel in (("blurb", "11-blurb.md"), ("outline", "13-outline.md"),
                       ("cover-prompt", "22-cover-prompt.md")):
        p = bk.artifacts / rel
        if not p.is_file():
            return False, ("title-lock target missing: run/artifacts/%s (%s) is absent "
                           "— FAIL-CLOSED: every required artifact must carry the locked "
                           "title" % (rel, label)), {}
        targets[label] = p.read_text(encoding="utf-8")
    for p in bk.chapter_files():
        targets["chapter/%s" % p.name] = p.read_text(encoding="utf-8")
    targets["manuscript"] = bk.manuscript_text(title, subtitle)
    res_tl = p_title.evaluate(title, subtitle, targets)
    # placeholder scan over the assembled staging bundle (if assembled)
    staged_texts = {str(p.relative_to(staging_dir)): p.read_text(encoding="utf-8", errors="replace")
                    for p in staging_dir.rglob("*")
                    if p.is_file() and p.suffix.lower() in {".md", ".txt", ".json", ".html"}} \
        if staging_dir.is_dir() else {}
    res_ph = p_ph.evaluate(staged_texts) if staged_texts else c.Result("noop")
    # anonymization lint over the SAME assembled bundle (prove_bw_anon now runs in the
    # runtime pipeline — no-op with no configured tokens, fail-closed when a configured
    # client-name token leaks into a deliverable).
    raw_anon_tokens = _anon_tokens(bk)
    # The author's OWN name is not a leak: the deliverables are the client's book,
    # bylined with their name (cover prompt, tone doc, APPROVED-TITLE.txt, blurb).
    # AF-BK-ANON guards against OTHER people's names leaking, so drop tokens that
    # are just the intake identity (full name or its parts) from the denylist.
    _ident_parts = [str(bk.intake().get(k) or "").strip()
                    for k in ("first_name", "last_name")]
    _ident = {_p.lower() for _p in (_ident_parts[0], _ident_parts[1],
                                    " ".join(_x for _x in _ident_parts if _x)) if _p}
    anon_tokens = [t for t in raw_anon_tokens if t.strip().lower() not in _ident]
    # FAIL-CLOSED AFTER the identity filter: a denylist that was empty to begin
    # with, OR one whose every token was exempted as the author's own name, both
    # make evaluate() vacuous (R-P15 hole). The gate must block on either path.
    if not anon_tokens:
        first = str((bk.intake().get("first_name") or "")).strip()
        if not raw_anon_tokens:
            print("WARNING: BW_ANON_TOKENS unset — anonymization vacuous", file=sys.stderr)
            if first:
                return False, ("BW_ANON_TOKENS unset — anonymization vacuous — FAIL-CLOSED: "
                               "the client's first_name is present in intake.json, so the "
                               "delivery-time denylist must be supplied via env BW_ANON_TOKENS "
                               "or run/checkpoints/anon-tokens.txt (spec R-P15)"), {}
        else:
            return False, ("anonymization vacuous — FAIL-CLOSED: every configured denylist "
                           "token was exempted as the author's own name, so no tokens remain "
                           "to lint with. Supply at least one non-identity token via env "
                           "BW_ANON_TOKENS or run/checkpoints/anon-tokens.txt (spec R-P15)"), {}
    res_anon = p_anon.evaluate(staged_texts, anon_tokens) if staged_texts else c.Result("noop-anon")
    # GATE-3 / GATE-4 revision-round approvals (conditional): only required when the
    # corresponding rewrite round actually ran (its receipt exists). Mirrors the
    # source's two email-gated revision loops; up to TWO rounds, receipted.
    gate_msgs = []
    gates_ok = True
    if any(bk.receipts.glob("G-STAGE-19*.json")):
        if _gate_ok(approvals, "GATE-3-approval"):
            gate_msgs.append("GATE-3 approved")
        else:
            gates_ok = False
            gate_msgs.append("GATE-3-approval receipt missing/malformed (revision round 1 ran)")
    if any(bk.receipts.glob("G-STAGE-20*.json")):
        if _gate_ok(approvals, "GATE-4-approval-r2"):
            gate_msgs.append("GATE-4 approved")
        else:
            gates_ok = False
            gate_msgs.append("GATE-4-approval-r2 receipt missing/malformed (revision round 2 ran)")
    # BUG-20: a certified 4x3x3 bundle MUST actually contain the offer-book extras
    # (30 titles / outcomes / KP doc / deck data / deck outline). The 4x3x3 prover in
    # P7-QC validates the SOURCE artifacts under run/433/; here we fail-closed unless
    # every one of the five labeled extras is PRESENT in the assembled bundle.
    bundle_433_ok = True
    bundle_433_msg = "none required"
    if bk.mode() == "4x3x3":
        expected = ["30_Titles-%s_%s.md" % (bk.author()[0], bk.author()[1]),
                    "Transformational_Outcomes-%s_%s.md" % (bk.author()[0], bk.author()[1]),
                    "KP_Document-%s_%s.md" % (bk.author()[0], bk.author()[1]),
                    "433_Deck_Data.json", "433_Deck_Outline.md"]
        missing = [name for name in expected if not (staging_dir / name).is_file()]
        bundle_433_ok = not missing
        bundle_433_msg = ("4x3x3 bundle extras present" if bundle_433_ok
                          else "4x3x3 bundle MISSING extras: %s" % ", ".join(missing))
    ok = res_ch.passed and res_tl.passed and res_ph.passed and res_anon.passed and gates_ok and bundle_433_ok
    msg = "challenge %s | title-lock %s | placeholder %s | anon %s | revision-gates %s | 433-bundle %s" % (
        _phase_result(res_ch)[1], _phase_result(res_tl)[1], _phase_result(res_ph)[1],
        _phase_result(res_anon)[1], ("; ".join(gate_msgs) if gate_msgs else "none required"),
        bundle_433_msg)
    return ok, msg, {"challenge_sections": c.count_day_sections(ch.read_text(encoding="utf-8")),
                     "title_lock_ok": res_tl.passed}


def _write_qc_report(bk: Book, report: dict):
    """Persist the P7-QC report artifact (manifest produces_artifact
    run/qc/book_qc_report.json) FAIL-SOFT: a write error is logged to stderr and
    swallowed — the QC verdict is decided by the checkers, never by our ability to
    persist the report, so a write problem can never fail the run."""
    try:
        out = bk.rd / "qc" / "book_qc_report.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    except OSError as exc:
        print("P7-QC report write skipped (fail-soft): %s" % exc, file=sys.stderr)


def check_qc(bk: Book):
    report = {
        "artifact": "run/qc/book_qc_report.json",
        "schema": "book-writer-qc-report-v1",
        "mode": bk.mode(),
        "no_anthropic": {"passed": False, "violations": [], "notes": []},
        "433": None,
        "measured": {},
        "qc_passed": False,
        "message": "",
    }
    ledger = bk.rd / "RUN-LEDGER.json"
    # FAIL-CLOSED: a missing RUN-LEDGER (or one that records ZERO model ids) means
    # the no-Anthropic / client-provider provenance was never established — the QC
    # gate cannot pass on an absent ledger. And the credential scan runs against the
    # LIVE process env by NAME only (masked), never a disabled env={}.
    if not ledger.is_file():
        msg = ("no-anthropic FAIL: run/RUN-LEDGER.json is absent — the model "
               "provenance (client's OWN providers, never Anthropic) is unproven "
               "(fail-closed; the ledger must record each stage's resolved model id)")
        report["message"] = msg
        report["no_anthropic"]["violations"].append({"code": "AF-BK-ANTHROPIC", "message": msg})
        _write_qc_report(bk, report)
        return False, msg, {}
    try:
        ledger_obj = json.loads(ledger.read_text(encoding="utf-8"))
    except ValueError as exc:
        msg = "no-anthropic FAIL: RUN-LEDGER.json is not valid JSON (%s)" % exc
        report["message"] = msg
        report["no_anthropic"]["violations"].append({"code": "AF-BK-ANTHROPIC", "message": msg})
        _write_qc_report(bk, report)
        return False, msg, {}
    report["measured"]["model_id_count"] = _ledger_model_id_count(ledger_obj)
    if report["measured"]["model_id_count"] == 0:
        msg = ("no-anthropic FAIL: RUN-LEDGER.json records ZERO model ids — the "
               "client-provider provenance is empty (fail-closed; a real run records "
               "each stage's resolved model id)")
        report["message"] = msg
        report["no_anthropic"]["violations"].append({"code": "AF-BK-ANTHROPIC", "message": msg})
        _write_qc_report(bk, report)
        return False, msg, {}
    res_anth = p_anth.evaluate(ledger_obj, env=dict(os.environ))
    ok = res_anth.passed
    msg = "no-anthropic %s" % _phase_result(res_anth)[1]
    report["no_anthropic"]["passed"] = ok
    report["no_anthropic"]["violations"] = [{"code": cd, "message": m} for cd, m in res_anth.violations]
    report["no_anthropic"]["notes"] = res_anth.notes
    # ledger stage coverage: every non-degradable manifest stage whose produced
    # artifact exists on disk must appear in at least one ledger entry — a stage that
    # ran but was never recorded breaks provenance (fail-closed).
    uncovered = _uncovered_stages(bk, ledger_obj)
    if uncovered:
        ok = False
        m2 = ("ledger coverage FAIL: no RUN-LEDGER entry references produced stage(s): %s "
              "(fail-closed; every executed stage must record its resolved model id)"
              % ", ".join(uncovered))
        msg += " | " + m2
        report["no_anthropic"]["violations"].append({"code": "AF-BK-LEDGER-COVERAGE", "message": m2})
    if bk.mode() == "4x3x3":
        report["433"] = {"passed": False, "violations": [], "notes": [], "measured": {}}
        titles = bk.d433 / "41-30-titles.md"
        outcomes = bk.d433 / "42-outcomes.md"
        deck = bk.d433 / "433_Deck_Data.json"
        if titles.is_file() and outcomes.is_file() and deck.is_file():
            res_433 = p_433.evaluate(titles.read_text(encoding="utf-8"),
                                     outcomes.read_text(encoding="utf-8"),
                                     json.loads(deck.read_text(encoding="utf-8")))
            ok = ok and res_433.passed
            msg += " | 4x3x3 %s" % _phase_result(res_433)[1]
            report["433"]["passed"] = res_433.passed
            report["433"]["violations"] = [{"code": cd, "message": m} for cd, m in res_433.violations]
            report["433"]["notes"] = res_433.notes
            report["433"]["measured"]["program_titles"] = c.count_list_items(
                titles.read_text(encoding="utf-8"))
            report["433"]["measured"]["transformational_outcomes"] = c.count_list_items(
                outcomes.read_text(encoding="utf-8"))
            # chapters mapped across the deck's phase map (report-only, fail-soft)
            try:
                deck_obj = json.loads(deck.read_text(encoding="utf-8"))
                phases = deck_obj.get("phases") if isinstance(deck_obj, dict) else None
                if isinstance(phases, list):
                    report["433"]["measured"]["chapters_mapped"] = sum(
                        len(ph.get("chapters", [])) for ph in phases if isinstance(ph, dict))
            except (ValueError, AttributeError) as exc:
                print("P7-QC deck measured value skipped (fail-soft): %s" % exc, file=sys.stderr)
        else:
            ok = False
            msg += " | 4x3x3 artifacts missing"
            report["433"]["violations"].append(
                {"code": "AF-BK-433-MAP",
                 "message": "4x3x3 artifacts missing (41-30-titles.md / 42-outcomes.md / 433_Deck_Data.json)"})
    report["qc_passed"] = ok
    report["message"] = msg
    _write_qc_report(bk, report)
    return ok, msg, {}


# ---- delivery assembly ------------------------------------------------------
def bundle_name(bk: Book) -> str:
    first, last = bk.author()
    return "%s_%s-Book" % (first, last)


def assemble_delivery(bk: Book, out: Path) -> Path:
    """Assemble the labeled bundle into `out` (a STAGING dir during the run; it is
    promoted to delivery/ only after a full P0->P7 pass — an uncertified book never
    sits in delivery/). Re-assembling is idempotent: the dir is cleared first."""
    first, last = bk.author()
    title, subtitle = bk.title_subtitle()
    if out.exists():
        shutil.rmtree(out, ignore_errors=True)
    (out / "chapters").mkdir(parents=True, exist_ok=True)

    def copy(src_rel, dst_name):
        src = bk.artifacts / src_rel
        if src.is_file():
            (out / dst_name).write_text(src.read_text(encoding="utf-8"), encoding="utf-8")

    copy("01-avatar.md", "Avatar_Document-%s_%s.md" % (first, last))
    copy("08-blended-tone.md", "Tone_Communication_Style_Analysis-%s_%s.md" % (first, last))
    copy("APPROVED-TITLE.txt", "APPROVED-TITLE.txt")
    copy("13-outline.md", "APPROVED-OUTLINE.md")
    copy("21-30day-challenge.md", "30_Day_Challenge-%s_%s.md" % (first, last))
    copy("22-cover-prompt.md", "Book_Cover_Prompt.md")
    # BUG-5 FAIL-CLOSED: the blurb, suggested titles, and chapter titles are REQUIRED
    # P6-PACKAGE deliverables. A bundle silently missing any of them must never be
    # assembled (check_package enforces the same presence check; this raises so the
    # staging bundle can never carry a certificate-free partial delivery either).
    for rel in ("10-suggested-titles.md", "11-blurb.md", "12-chapter-titles.md"):
        req = bk.artifacts / rel
        if not req.is_file():
            raise FileNotFoundError(
                "missing run/artifacts/%s — FAIL-CLOSED: required deliverable absent; "
                "refusing to assemble the delivery bundle" % rel)
    copy("10-suggested-titles.md", "Suggested_Titles-%s_%s.md" % (first, last))
    # blurb + chapter titles combined (both guaranteed present above)
    combo = []
    combo.append((bk.artifacts / "11-blurb.md").read_text(encoding="utf-8"))
    combo.append("\n\n" + (bk.artifacts / "12-chapter-titles.md").read_text(encoding="utf-8"))
    (out / ("Book_Blurb_and_Chapter_Titles-%s_%s.md" % (first, last))).write_text(
        "".join(combo), encoding="utf-8")
    # chapters + manuscript
    for p in bk.chapter_files():
        (out / "chapters" / p.name).write_text(p.read_text(encoding="utf-8"), encoding="utf-8")
    stem = (title or "Book").replace(" ", "_")
    (out / ("%s-Manuscript.md" % stem)).write_text(bk.manuscript_text(title, subtitle), encoding="utf-8")
    # BUG-20: a 4x3x3 run ships its offer-book extras (the Skill 51 handoff
    # payload under run/433/) into the labeled bundle. Without this, a certified
    # 4x3x3 book carries ZERO of its 30 titles / outcomes / KP doc / deck data /
    # deck outline. full-mode behavior is unchanged.
    if bk.mode() == "4x3x3":
        def _copy433(src_rel, dst_name):
            src = bk.d433 / src_rel
            if src.is_file():
                (out / dst_name).write_text(src.read_text(encoding="utf-8"), encoding="utf-8")

        _copy433("41-30-titles.md", "30_Titles-%s_%s.md" % (first, last))
        _copy433("42-outcomes.md", "Transformational_Outcomes-%s_%s.md" % (first, last))
        _copy433("43-kp-document.md", "KP_Document-%s_%s.md" % (first, last))
        _copy433("433_Deck_Data.json", "433_Deck_Data.json")
        _copy433("433_Deck_Outline.md", "433_Deck_Outline.md")
    return out


def write_index_and_manifest(bk: Book, delivery: Path, measured: dict):
    # 00-INDEX.md is written FIRST: its content depends only on the file NAME list
    # (not any sha), so once it is on disk its sha256 is final and can be recorded
    # in MANIFEST.json below. Writing it before hashing avoids the chicken-and-egg
    # where the recorded sha would describe the PRE-index 00-INDEX.md while the
    # on-disk file lists MANIFEST.json/itself (the BUG-22 sha-mismatch trap).
    names = sorted(p.relative_to(delivery).as_posix()
                   for p in delivery.rglob("*") if p.is_file())
    idx = ["# Book Writer — deliverable index", "",
           "Everything below is a LOCAL labeled deliverable (no n8n / Airtable / Google / Gmail /",
           "Slack / GHL). See PROCESS-CERTIFICATE.json for the signed provenance.", ""]
    for rel in names:
        idx.append("- `%s`" % rel)
    (delivery / "00-INDEX.md").write_text("\n".join(idx) + "\n", encoding="utf-8")
    # MANIFEST.json cannot carry its own sha256 (self-referential — the file content
    # would change as soon as the hash is written). List it with a null sha so it still
    # appears in the INDEX / file list, and the verifier checks existence only for this
    # entry. Every other file (00-INDEX.md now finalized, certs, content) gets a real sha.
    files = []
    for rel in names:
        sha = None if rel == "MANIFEST.json" else hashlib.sha256(
            (delivery / rel).read_bytes()).hexdigest()
        files.append({"file": rel, "sha256": sha})
    manifest = {"skill": "book-writer", "author": "%s %s" % bk.author(),
                "measured": measured, "files": files}
    (delivery / "MANIFEST.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def write_certificate(bk: Book, delivery: Path, steps, measured):
    all_pass = all(s["ok"] for s in steps) and len(steps) == len(PHASE_ORDER)
    if not all_pass:
        print("AF-BK-PROCESS-INTEGRITY: refusing to certify — not a full P0->P8 pass.",
              file=sys.stderr)
        return None
    title, subtitle = bk.title_subtitle()
    body = {
        "schema": "book-writer-process-certificate-v1",
        "skill": "book-writer",
        "manifest_version": 1,
        "author": "%s %s" % bk.author(),
        "book_slug": bk.slug(),
        "mode": bk.mode(),
        "locked_title": title,
        "locked_subtitle": subtitle,
        "measured_chapter_count": measured.get("chapter_count"),
        "measured_chapter_word_counts": measured.get("chapter_word_counts"),
        "measured_tone_word_count": measured.get("tone_word_count"),
        "measured_challenge_sections": measured.get("challenge_sections"),
        "title_lock_ok": measured.get("title_lock_ok"),
        "stories_placed": measured.get("stories_placed"),
        "declared_phases": PHASE_ORDER,
        "verified_phases": len(steps),
        "all_phases_pass": all_pass,
        "runtime": "local-only (no n8n / Airtable / Google / Gmail / Slack / GHL)",
        "local_downloads_bundle": measured.get("downloads_bundle"),
        "steps": steps,
    }
    wc = measured.get("chapter_word_counts") or {}
    sha_src = json.dumps({
        "slug": body["book_slug"], "mode": body["mode"],
        "title": title, "subtitle": subtitle,
        "chapters": sorted((int(k), int(v)) for k, v in wc.items()),
        "tone": measured.get("tone_word_count"),
        "challenge": measured.get("challenge_sections"),
        "title_lock": bool(measured.get("title_lock_ok")),
        "stories": measured.get("stories_placed"),
        "steps": [(s["phase_id"], bool(s["ok"])) for s in steps],
    }, sort_keys=True)
    body["certificate_sha"] = hashlib.sha256(sha_src.encode("utf-8")).hexdigest()
    body["certified_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    (delivery / "PROCESS-CERTIFICATE.json").write_text(json.dumps(body, indent=2), encoding="utf-8")
    md = [
        "# Book Writer — PROCESS CERTIFICATE", "",
        "- **Author:** %s" % body["author"],
        "- **Book:** %s — %s" % (title, subtitle),
        "- **Mode:** %s" % body["mode"],
        "- **Measured chapters:** %s (each 2000-3500 stripped words)" % measured.get("chapter_count"),
        "- **Measured blended-tone words:** %s (>= 3000)" % measured.get("tone_word_count"),
        "- **Measured challenge day-sections:** %s / 30" % measured.get("challenge_sections"),
        "- **Title lock OK:** %s" % measured.get("title_lock_ok"),
        "- **Stories placed:** %s" % measured.get("stories_placed"),
        "- **All phases pass:** %s" % all_pass,
        "- **Runtime:** local-only (no n8n / Airtable / Google / Gmail / Slack / GHL)",
        "- **Certificate SHA:** `%s`" % body["certificate_sha"],
        "- **Certified at:** %s" % body["certified_at"], "",
        "| Phase | Verified |", "|---|---|",
    ]
    for s in steps:
        md.append("| %s | %s |" % (s["phase_id"], "yes" if s["ok"] else "NO"))
    md.append("")
    md.append("Issued by `run_book_writer.py` after a full P0->P8 pass through "
              "`book-writer-entry.sh`. QC gates are the fail-closed provers in `scripts/`. "
              "No certificate = not done.")
    (delivery / "PROCESS-CERTIFICATE.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    return {"path": str(delivery / "PROCESS-CERTIFICATE.json"), "sha": body["certificate_sha"]}


# ---- P8 deliver: promote staging -> delivery, copy to ~/Downloads, verify sha --
def _downloads_root() -> Path:
    """The labeled-deliverable root. Honors ${BOOK_WRITER_DELIVERY_ROOT} (so a test
    / CI run never litters the operator's real ~/Downloads) and falls back to
    ~/Downloads. Never n8n/Drive/etc. — a LOCAL labeled folder only."""
    override = os.environ.get("BOOK_WRITER_DELIVERY_ROOT", "").strip()
    return Path(override).expanduser() if override else (Path.home() / "Downloads")


def verify_bundle_against_manifest(bundle: Path):
    """Assert every file listed in the bundle's MANIFEST.json exists with a matching
    sha256. Returns (ok, problems). The MANIFEST is the source of truth for the
    labeled deliverable; a copy that drops or corrupts a file fails P8 fail-closed."""
    mf = bundle / "MANIFEST.json"
    if not mf.is_file():
        return False, ["MANIFEST.json missing from the bundle"]
    try:
        manifest = json.loads(mf.read_text(encoding="utf-8"))
    except ValueError as exc:
        return False, ["MANIFEST.json is not valid JSON (%s)" % exc]
    files = manifest.get("files") or []
    if not files:
        return False, ["MANIFEST.json lists ZERO files"]
    problems = []
    for entry in files:
        rel = entry.get("file")
        want = entry.get("sha256")
        if not rel:
            problems.append("malformed MANIFEST entry: %r" % entry)
            continue
        fp = bundle / rel
        if not fp.is_file():
            problems.append("MANIFEST lists %s but it is absent from the bundle" % rel)
            continue
        if want is None:
            # MANIFEST.json is self-referential (a file cannot contain its own sha256),
            # so it carries sha256=null and is checked existence-only.
            continue
        if not want:
            problems.append("malformed MANIFEST entry: %r" % entry)
            continue
        got = hashlib.sha256(fp.read_bytes()).hexdigest()
        if got != want:
            problems.append("sha256 mismatch for %s (manifest %s… != file %s…)"
                            % (rel, want[:12], got[:12]))
    return (not problems), problems


def check_deliver(bk: Book, staging: Path, delivery: Path):
    """P8-DELIVER (real checker, not a no-op): promote the certified staging bundle to
    delivery/, copy it to a deterministic timestamped ~/Downloads labeled folder, and
    verify the copied file list + sha256 against MANIFEST.json. Fail-closed on any
    missing/mismatched file. Returns (ok, msg, {'downloads_bundle': path})."""
    if not (staging / "MANIFEST.json").is_file():
        return False, "staging bundle has no MANIFEST.json (assembly incomplete)", {}
    # promote staging -> delivery/ (certified location; overwrite any prior)
    if delivery.exists():
        shutil.rmtree(delivery, ignore_errors=True)
    delivery.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(staging, delivery)
    # verify the promoted bundle against its own MANIFEST
    ok_del, prob_del = verify_bundle_against_manifest(delivery)
    if not ok_del:
        return False, "delivery bundle failed MANIFEST verification: %s" % "; ".join(prob_del), {}
    # copy to a labeled, timestamped ~/Downloads bundle (LOCAL only)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dl_dir = _downloads_root() / bundle_name(bk) / ("Book_Writer_%s" % stamp)
    try:
        if dl_dir.exists():
            shutil.rmtree(dl_dir, ignore_errors=True)
        dl_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(delivery, dl_dir)
    except OSError as exc:
        return False, "could not copy labeled bundle to ~/Downloads (%s)" % exc, {}
    # verify the ~/Downloads copy against MANIFEST (file list + sha256)
    ok_dl, prob_dl = verify_bundle_against_manifest(dl_dir)
    if not ok_dl:
        return False, "~/Downloads bundle failed MANIFEST verification: %s" % "; ".join(prob_dl), {}
    n = len(json.loads((dl_dir / "MANIFEST.json").read_text(encoding="utf-8")).get("files", []))
    return True, "labeled bundle delivered to %s (%d files sha256-verified vs MANIFEST)" % (dl_dir, n), \
        {"downloads_bundle": str(dl_dir)}


def _quarantine(bk: Book, staging: Path):
    """Move the UNCERTIFIED staging bundle out of the way so it can never masquerade
    as a delivered book. delivery/ is never created on a gate failure."""
    if not staging.exists():
        return
    qroot = bk.run_dir / "quarantine"
    qroot.mkdir(parents=True, exist_ok=True)
    dest = qroot / bundle_name(bk)
    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)
    try:
        shutil.move(str(staging), str(dest))
        print("QUARANTINED uncertified bundle -> %s" % dest, file=sys.stderr)
    except OSError:
        shutil.rmtree(staging, ignore_errors=True)


# ---- run / plan -------------------------------------------------------------
def plan(manifest) -> int:
    print("== Book Writer — canonical phase plan ==")
    for i, pid in enumerate(PHASE_ORDER):
        ph = next((p for p in manifest.get("phases", []) if p.get("id") == pid), None)
        codes = ", ".join(ph.get("gate_codes", [])) if ph else "?"
        name = ph.get("name", "") if ph else "MISSING"
        print("  %d. %s — %s" % (i, pid, name))
        print("       gate codes: %s" % codes)
    return EXIT_PASS


def run(bk: Book) -> int:
    # Assemble into a STAGING dir (never delivery/): an uncertified book must never
    # sit in delivery/. Promotion to delivery/ + the ~/Downloads copy happen only in
    # P8-DELIVER, after P0->P7 all pass.
    staging = bk.run_dir / "staging" / bundle_name(bk)
    delivery = bk.run_dir / "delivery" / bundle_name(bk)
    try:
        assemble_delivery(bk, staging)
    except FileNotFoundError as exc:
        # BUG-5 fail-closed: a required deliverable (blurb / suggested titles /
        # chapter titles) is absent — never assemble a partial bundle.
        _LAST_BLOCK.clear()
        _LAST_BLOCK.update({"phase_id": "P6-PACKAGE", "note": str(exc)})
        print("=== PHASE P6-PACKAGE === [FAIL] %s" % exc)
        print("BLOCKED at P6-PACKAGE (fail-closed). Author the missing deliverable and re-run.",
              file=sys.stderr)
        _quarantine(bk, staging)
        return EXIT_GATE
    except ChapterNamingError as exc:
        # fail-closed: run/chapters/ carries a non-conforming name or duplicate number
        _LAST_BLOCK.clear()
        _LAST_BLOCK.update({"phase_id": "P5-CHAPTERS", "note": str(exc)})
        print("=== PHASE P5-CHAPTERS === [FAIL] %s" % exc)
        print("BLOCKED at P5-CHAPTERS (fail-closed). Fix the chapter naming and re-run.",
              file=sys.stderr)
        _quarantine(bk, staging)
        return EXIT_GATE
    approvals = load_gate_receipts(bk.run_dir)
    measured = {}
    steps = []
    # P0->P7 verify over the STAGING bundle (P8 handled specially below).
    pre_deliver_checkers = {
        "P0-INTAKE": lambda: check_intake(bk),
        "P1-AVATAR": lambda: check_avatar(bk),
        "P2-TONE": lambda: check_tone(bk),
        "P3-TITLES-GATE": lambda: check_titles(bk, approvals),
        "P4-OUTLINE-GATE": lambda: check_outline(bk, approvals),
        "P5-CHAPTERS": lambda: check_chapters(bk),
        "P6-PACKAGE": lambda: check_package(bk, staging, approvals),
        "P7-QC": lambda: check_qc(bk),
    }
    for pid in PHASE_ORDER[:-1]:  # P0..P7
        ok, msg, extra = pre_deliver_checkers[pid]()
        measured.update(extra)
        print("=== PHASE %s === [%s] %s" % (pid, "OK" if ok else "FAIL", msg))
        steps.append({"phase_id": pid, "disposition": "verified", "ok": bool(ok)})
        if not ok:
            _LAST_BLOCK.clear()
            _LAST_BLOCK.update({"phase_id": pid, "note": msg})
            print("BLOCKED at %s (fail-closed). No phase skips; author the artifact and re-run."
                  % pid, file=sys.stderr)
            _quarantine(bk, staging)
            return EXIT_GATE
    # Finalize the labeled bundle inside staging (INDEX + MANIFEST), THEN P8-DELIVER
    # promotes it and proves the ~/Downloads copy byte-for-byte against MANIFEST.
    write_index_and_manifest(bk, staging, measured)
    ok, msg, extra = check_deliver(bk, staging, delivery)
    measured.update(extra)
    print("=== PHASE P8-DELIVER === [%s] %s" % ("OK" if ok else "FAIL", msg))
    steps.append({"phase_id": "P8-DELIVER", "disposition": "verified", "ok": bool(ok)})
    if not ok:
        _LAST_BLOCK.clear()
        _LAST_BLOCK.update({"phase_id": "P8-DELIVER", "note": msg})
        print("BLOCKED at P8-DELIVER (fail-closed).", file=sys.stderr)
        _quarantine(bk, staging)
        shutil.rmtree(delivery, ignore_errors=True)  # never leave an unverified delivery/
        return EXIT_GATE
    cert = write_certificate(bk, delivery, steps, measured)
    if cert:
        print("CERTIFICATE ISSUED: %s (sha %s)" % (cert["path"], cert["sha"][:12]))
        # mirror the signed certificate into the labeled ~/Downloads bundle
        dl = measured.get("downloads_bundle")
        if dl:
            for cf in ("PROCESS-CERTIFICATE.json", "PROCESS-CERTIFICATE.md"):
                src = delivery / cf
                if src.is_file():
                    try:
                        shutil.copy2(src, Path(dl) / cf)
                    except OSError:
                        pass
    # BUG-22: the first write_index_and_manifest (before P8-DELIVER) ran BEFORE the
    # certs were minted, so the delivered MANIFEST under-listed the bundle (00-INDEX.md,
    # MANIFEST.json, PROCESS-CERTIFICATE.{json,md} were missing). Re-generate INDEX +
    # MANIFEST over the COMPLETE delivery bundle now that every file exists, refresh the
    # ~/Downloads mirror, and re-verify BOTH against the final MANIFEST so the delivered
    # manifest lists exactly what is on disk (certs + INDEX included).
    write_index_and_manifest(bk, delivery, measured)
    dl = measured.get("downloads_bundle")
    if dl:
        for refresh in ("MANIFEST.json", "00-INDEX.md"):
            src = delivery / refresh
            if src.is_file():
                try:
                    shutil.copy2(src, Path(dl) / refresh)
                except OSError:
                    pass
        ok_del, prob_del = verify_bundle_against_manifest(delivery)
        ok_dl, prob_dl = verify_bundle_against_manifest(Path(dl))
        if not (ok_del and ok_dl):
            print("BUG-22 FINAL MANIFEST RE-VERIFY FAILED: delivery=%s dl=%s"
                  % (prob_del, prob_dl), file=sys.stderr)
            _quarantine(bk, staging)
            shutil.rmtree(delivery, ignore_errors=True)
            return EXIT_GATE
    shutil.rmtree(staging.parent, ignore_errors=True)  # staging is transient
    print("ALL PHASES PASSED (P0->P8).")
    return EXIT_PASS


# ---------------------------------------------------------------------------
# Command Center board card (FAIL-SOFT). Mirrors Skill-48 (ad_director) and the
# presentations build_deck._board_patch_phase pattern via the shared mc_board
# helper: land ONE mc-route card per run and advance it. A disabled board
# (no COMMAND_CENTER_URL) is a clean no-op; ANY failure is swallowed — the board
# is a VIEW, never a gate, and can never affect this assembler's exit code.
# ---------------------------------------------------------------------------
def _mc_board_begin(run_dir):
    try:
        import mc_board
        # FIX-BK-DEPT-01: "books" was never a real, seeded department (no script
        # anywhere in this repo creates one) — mc_board fails SOFT on an unrecognized
        # department_slug, so every Book Writer card was silently dropped/misrouted.
        # WIRING-SPEC.md section 8 documents the intended owner as the Content /
        # Publishing lineage, same owner as Skills 50/51; skill-department-map.json's
        # skill-53 entry (and its siblings 52/54/55/56) resolves that lineage to the
        # real, mandatory, always-seeded "marketing" department (see
        # 23-ai-workforce-blueprint/department-naming-map.json .mandatory).
        return mc_board.begin_run(
            run_dir, slug=run_dir.name,
            title="Book Writer — %s" % run_dir.name,
            department="marketing", persona="Book Writer", source="book-writer",
            receipt_subdir=RECEIPT_SUBDIR,
            evidence_root=str(run_dir))
    except Exception as exc:  # noqa: BLE001 — board hookup must NEVER break the run.
        print("[mc_board] begin best-effort skip (%s)" % exc, file=sys.stderr)
        return None


def _mc_board_done(run_dir, task_id, process_certificate_sha=""):
    try:
        import mc_board
        delivery_index = Path(run_dir) / "delivery" / bundle_name(Book(Path(run_dir))) / "00-INDEX.md"
        ok = mc_board.complete_run(run_dir, task_id, note="certified + delivered",
                                   deliverable_url=str(delivery_index),
                                   process_certificate_sha=process_certificate_sha,
                                   receipt_subdir=RECEIPT_SUBDIR)
        if not ok:
            print("[mc_board] complete_run returned False — card not advanced to "
                  "review (best-effort; run itself is unaffected)", file=sys.stderr)
    except Exception as exc:  # noqa: BLE001
        print("[mc_board] done best-effort skip (%s)" % exc, file=sys.stderr)


def _mc_board_blocked(run_dir, task_id):
    """FIX-XC-06: on a gate failure, move the card to `blocked` (never `done`) with
    the failing phase + AF code as the note, so a failed run is VISIBLE on the board
    instead of stranding forever at in_progress. FAIL-SOFT — never affects exit code."""
    try:
        import mc_board
        info = _LAST_BLOCK or {}
        mc_board.block_run(run_dir, task_id, phase_id=info.get("phase_id", ""),
                           note=info.get("note", "a fail-closed gate blocked the run"),
                           receipt_subdir=RECEIPT_SUBDIR)
    except Exception as exc:  # noqa: BLE001
        print("[mc_board] blocked best-effort skip (%s)" % exc, file=sys.stderr)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Deterministic Book Writer assembler/certifier (Skill 53).")
    ap.add_argument("--run-dir", help="the book run dir (contains run/ authored artifacts)")
    ap.add_argument("--plan", action="store_true", help="print the canonical phase plan and exit")
    args = ap.parse_args(argv)
    manifest = _load_manifest()
    if args.plan:
        return plan(manifest)
    if not args.run_dir:
        ap.error("--run-dir is required (or use --plan)")
    run_dir = Path(args.run_dir).resolve()
    if not run_dir.is_dir():
        print("FATAL: --run-dir not found: %s" % run_dir, file=sys.stderr)
        return EXIT_USAGE
    if not _nonce_ok(run_dir):
        print("FATAL: front-door nonce missing/mismatch. Run THROUGH book-writer-entry.sh "
              "(the ONE sanctioned entry); do not call this orchestrator directly.",
              file=sys.stderr)
        return EXIT_NONCE
    _mc_task = _mc_board_begin(run_dir)
    rc = run(Book(run_dir))
    if rc == EXIT_PASS:
        cert_sha = ""
        try:
            cert_sha = (json.loads((Path(run_dir) / "delivery" / bundle_name(Book(run_dir)) /
                                    "PROCESS-CERTIFICATE.json").read_text(encoding="utf-8")
                                 ).get("certificate_sha") or "")
        except (OSError, ValueError):
            pass
        _mc_board_done(run_dir, _mc_task, process_certificate_sha=cert_sha)
    else:
        # A gate failure after the card was opened: mark it blocked so it never
        # strands invisibly at in_progress (FIX-XC-06). FAIL-SOFT.
        _mc_board_blocked(run_dir, _mc_task)
    return rc


if __name__ == "__main__":
    sys.exit(main())
