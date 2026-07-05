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

PHASE_ORDER = ["P0-INTAKE", "P1-AVATAR", "P2-TONE", "P3-TITLES-GATE", "P4-OUTLINE-GATE",
               "P5-CHAPTERS", "P6-PACKAGE", "P7-QC", "P8-DELIVER"]


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


def load_gate_receipts(run_dir: Path) -> dict:
    """Return {gate_id: record} for every WELL-FORMED human-gate approval receipt
    (approved:true + a non-empty approved_by + a timestamp), mirroring Skill 48's
    owner-approval shape. A file-presence-only 'approval' authored by the pipeline is
    NOT sufficient — the gate reads the actual approved/approved_by/timestamp fields,
    so an approval can never be back-filled or self-attested away. Receipts live at
    <run_dir>/run/checkpoints/gate-receipts.json (a single object with receipts[]) or
    one JSON object per file under <run_dir>/run/checkpoints/gates/*.json."""
    approvals: dict = {}
    cdir = run_dir.joinpath(*RECEIPT_SUBDIR)
    candidates = []
    single = cdir / "gate-receipts.json"
    if single.is_file():
        candidates.append(single)
    gdir = cdir / "gates"
    if gdir.is_dir():
        candidates.extend(sorted(gdir.glob("*.json")))
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
            ts = rec.get("approved_at") or rec.get("timestamp")
            if (gid and rec.get("approved") is True
                    and str(rec.get("approved_by", "")).strip()
                    and str(ts or "").strip()):
                approvals[gid] = rec
    return approvals


def _gate_ok(approvals: dict, gate_id: str) -> bool:
    return gate_id in approvals


def _ledger_model_id_count(ledger) -> int:
    """Number of recorded model ids anywhere in the ledger (uses the same walker the
    no-Anthropic gate uses)."""
    return sum(1 for _jp, _mid in p_anth._iter_model_ids(ledger))


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
        if not self.chapters_dir.is_dir():
            return []
        return sorted(self.chapters_dir.glob("ch*.md"))

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
        return False, "missing run/artifacts/01-avatar.md (TODO: Wave-2 authors the dossier)", {}
    return True, "avatar dossier present", {}


def check_tone(bk: Book):
    p = bk.artifacts / "08-blended-tone.md"
    if not p.is_file():
        return False, "missing run/artifacts/08-blended-tone.md (TODO: Wave-2 authors the tone)", {}
    res = p_tone.evaluate(p.read_text(encoding="utf-8"))
    ok, msg = _phase_result(res)
    return ok, "tone %s" % msg, {"tone_word_count": c.word_count(p.read_text(encoding="utf-8"))}


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
        return False, "missing run/artifacts/13-outline.md (TODO: Wave-2 authors the outline)", {}
    if not stories.is_file():
        return False, "missing run/stories.json", {}
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
        return False, "no run/chapters/ch*.md (TODO: Wave-2 authors the 12 chapters)", {}
    chap_texts = {}
    for i, p in enumerate(files, 1):
        chap_texts[i] = p.read_text(encoding="utf-8")
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


def _anon_tokens():
    """Client-name denylist for the runtime anonymization lint. Supplied at
    delivery time by NAME only via env (never checked into the fleet repo); an
    empty list is a clean no-op (nothing to lint)."""
    tokens = []
    inline = os.environ.get("BW_ANON_TOKENS", "")
    if inline.strip():
        tokens += inline.split(",")
    tf = os.environ.get("BW_ANON_TOKENS_FILE", "")
    if tf and Path(tf).is_file():
        try:
            tokens += Path(tf).read_text(encoding="utf-8").splitlines()
        except OSError:
            pass
    return tokens


def check_package(bk: Book, staging_dir: Path, approvals: dict):
    # challenge exactly 30
    ch = bk.artifacts / "21-30day-challenge.md"
    if not ch.is_file():
        return False, "missing run/artifacts/21-30day-challenge.md (TODO: Wave-2)", {}
    res_ch = p_chal.evaluate(ch.read_text(encoding="utf-8"))
    # title-lock across required artifacts
    title, subtitle = bk.title_subtitle()
    targets = {}
    for label, rel in (("blurb", "11-blurb.md"), ("outline", "13-outline.md"),
                       ("cover-prompt", "22-cover-prompt.md")):
        p = bk.artifacts / rel
        if p.is_file():
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
    res_anon = p_anon.evaluate(staged_texts, _anon_tokens()) if staged_texts else c.Result("noop-anon")
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
    ok = res_ch.passed and res_tl.passed and res_ph.passed and res_anon.passed and gates_ok
    msg = "challenge %s | title-lock %s | placeholder %s | anon %s | revision-gates %s" % (
        _phase_result(res_ch)[1], _phase_result(res_tl)[1], _phase_result(res_ph)[1],
        _phase_result(res_anon)[1], ("; ".join(gate_msgs) if gate_msgs else "none required"))
    return ok, msg, {"challenge_sections": c.count_day_sections(ch.read_text(encoding="utf-8")),
                     "title_lock_ok": res_tl.passed}


def check_qc(bk: Book):
    ledger = bk.rd / "RUN-LEDGER.json"
    # FAIL-CLOSED: a missing RUN-LEDGER (or one that records ZERO model ids) means
    # the no-Anthropic / client-provider provenance was never established — the QC
    # gate cannot pass on an absent ledger. And the credential scan runs against the
    # LIVE process env by NAME only (masked), never a disabled env={}.
    if not ledger.is_file():
        return False, ("no-anthropic FAIL: run/RUN-LEDGER.json is absent — the model "
                       "provenance (client's OWN providers, never Anthropic) is unproven "
                       "(fail-closed; the ledger must record each stage's resolved model id)"), {}
    try:
        ledger_obj = json.loads(ledger.read_text(encoding="utf-8"))
    except ValueError as exc:
        return False, "no-anthropic FAIL: RUN-LEDGER.json is not valid JSON (%s)" % exc, {}
    if _ledger_model_id_count(ledger_obj) == 0:
        return False, ("no-anthropic FAIL: RUN-LEDGER.json records ZERO model ids — the "
                       "client-provider provenance is empty (fail-closed; a real run records "
                       "each stage's resolved model id)"), {}
    res_anth = p_anth.evaluate(ledger_obj, env=dict(os.environ))
    ok = res_anth.passed
    msg = "no-anthropic %s" % _phase_result(res_anth)[1]
    if bk.mode() == "4x3x3":
        titles = bk.d433 / "41-30-titles.md"
        outcomes = bk.d433 / "42-outcomes.md"
        deck = bk.d433 / "433_Deck_Data.json"
        if titles.is_file() and outcomes.is_file() and deck.is_file():
            res_433 = p_433.evaluate(titles.read_text(encoding="utf-8"),
                                     outcomes.read_text(encoding="utf-8"),
                                     json.loads(deck.read_text(encoding="utf-8")))
            ok = ok and res_433.passed
            msg += " | 4x3x3 %s" % _phase_result(res_433)[1]
        else:
            ok = False
            msg += " | 4x3x3 artifacts missing"
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
    copy("10-suggested-titles.md", "Suggested_Titles-%s_%s.md" % (first, last))
    copy("APPROVED-TITLE.txt", "APPROVED-TITLE.txt")
    copy("13-outline.md", "APPROVED-OUTLINE.md")
    copy("21-30day-challenge.md", "30_Day_Challenge-%s_%s.md" % (first, last))
    copy("22-cover-prompt.md", "Book_Cover_Prompt.md")
    # blurb + chapter titles combined
    blurb = bk.artifacts / "11-blurb.md"
    ctitles = bk.artifacts / "12-chapter-titles.md"
    combo = []
    if blurb.is_file():
        combo.append(blurb.read_text(encoding="utf-8"))
    if ctitles.is_file():
        combo.append("\n\n" + ctitles.read_text(encoding="utf-8"))
    if combo:
        (out / ("Book_Blurb_and_Chapter_Titles-%s_%s.md" % (first, last))).write_text(
            "".join(combo), encoding="utf-8")
    # chapters + manuscript
    for p in bk.chapter_files():
        (out / "chapters" / p.name).write_text(p.read_text(encoding="utf-8"), encoding="utf-8")
    stem = (title or "Book").replace(" ", "_")
    (out / ("%s-Manuscript.md" % stem)).write_text(bk.manuscript_text(title, subtitle), encoding="utf-8")
    return out


def write_index_and_manifest(bk: Book, delivery: Path, measured: dict):
    files = []
    for p in sorted(delivery.rglob("*")):
        if p.is_file():
            sha = hashlib.sha256(p.read_bytes()).hexdigest()
            files.append({"file": str(p.relative_to(delivery)), "sha256": sha})
    manifest = {"skill": "book-writer", "author": "%s %s" % bk.author(),
                "measured": measured, "files": files}
    (delivery / "MANIFEST.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    idx = ["# Book Writer — deliverable index", "",
           "Everything below is a LOCAL labeled deliverable (no n8n / Airtable / Google / Gmail /",
           "Slack / GHL). See PROCESS-CERTIFICATE.json for the signed provenance.", ""]
    for f in files:
        idx.append("- `%s`" % f["file"])
    (delivery / "00-INDEX.md").write_text("\n".join(idx) + "\n", encoding="utf-8")


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
        if not rel or not want:
            problems.append("malformed MANIFEST entry: %r" % entry)
            continue
        fp = bundle / rel
        if not fp.is_file():
            problems.append("MANIFEST lists %s but it is absent from the bundle" % rel)
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
    assemble_delivery(bk, staging)
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
        return mc_board.begin_run(
            run_dir, slug=run_dir.name,
            title="Book Writer — %s" % run_dir.name,
            department="books", persona="Book Writer", source="book-writer",
            receipt_subdir=RECEIPT_SUBDIR)
    except Exception as exc:  # noqa: BLE001 — board hookup must NEVER break the run.
        print("[mc_board] begin best-effort skip (%s)" % exc, file=sys.stderr)
        return None


def _mc_board_done(run_dir, task_id):
    try:
        import mc_board
        mc_board.complete_run(run_dir, task_id, note="certified + delivered",
                              receipt_subdir=RECEIPT_SUBDIR)
    except Exception as exc:  # noqa: BLE001
        print("[mc_board] done best-effort skip (%s)" % exc, file=sys.stderr)


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
        _mc_board_done(run_dir, _mc_task)
    return rc


if __name__ == "__main__":
    sys.exit(main())
