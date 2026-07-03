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


def check_titles(bk: Book):
    title, subtitle = bk.title_subtitle()
    if not title or not subtitle:
        return False, "missing/incomplete run/artifacts/APPROVED-TITLE.txt", {}
    return True, "title locked: %r / %r" % (title, subtitle), {"title": title, "subtitle": subtitle}


def check_outline(bk: Book):
    outline = bk.artifacts / "13-outline.md"
    stories = bk.rd / "stories.json"
    if not outline.is_file():
        return False, "missing run/artifacts/13-outline.md (TODO: Wave-2 authors the outline)", {}
    if not stories.is_file():
        return False, "missing run/stories.json", {}
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


def check_package(bk: Book, delivery_dir: Path):
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
    # placeholder scan over the assembled delivery dir (if assembled)
    res_ph = p_ph.evaluate({str(p.relative_to(delivery_dir)): p.read_text(encoding="utf-8", errors="replace")
                            for p in delivery_dir.rglob("*")
                            if p.is_file() and p.suffix.lower() in {".md", ".txt", ".json", ".html"}}) \
        if delivery_dir.is_dir() else c.Result("noop")
    ok = res_ch.passed and res_tl.passed and res_ph.passed
    msg = "challenge %s | title-lock %s | placeholder %s" % (
        _phase_result(res_ch)[1], _phase_result(res_tl)[1], _phase_result(res_ph)[1])
    return ok, msg, {"challenge_sections": c.count_day_sections(ch.read_text(encoding="utf-8")),
                     "title_lock_ok": res_tl.passed}


def check_qc(bk: Book):
    ledger = bk.rd / "RUN-LEDGER.json"
    res_anth = p_anth.evaluate(json.loads(ledger.read_text(encoding="utf-8")), env={}) \
        if ledger.is_file() else c.Result("noop-ledger")
    if not ledger.is_file():
        res_anth.note("no RUN-LEDGER.json yet (TODO: Agent D assembles the ledger)")
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
def assemble_delivery(bk: Book) -> Path:
    first, last = bk.author()
    title, subtitle = bk.title_subtitle()
    out = bk.run_dir / "delivery" / ("%s_%s-Book" % (first, last))
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
    delivery = assemble_delivery(bk)
    measured = {}
    steps = []
    checkers = {
        "P0-INTAKE": lambda: check_intake(bk),
        "P1-AVATAR": lambda: check_avatar(bk),
        "P2-TONE": lambda: check_tone(bk),
        "P3-TITLES-GATE": lambda: check_titles(bk),
        "P4-OUTLINE-GATE": lambda: check_outline(bk),
        "P5-CHAPTERS": lambda: check_chapters(bk),
        "P6-PACKAGE": lambda: check_package(bk, delivery),
        "P7-QC": lambda: check_qc(bk),
        "P8-DELIVER": lambda: (True, "local delivery bundle assembled", {}),
    }
    for pid in PHASE_ORDER:
        ok, msg, extra = checkers[pid]()
        measured.update(extra)
        print("=== PHASE %s === [%s] %s" % (pid, "OK" if ok else "FAIL", msg))
        steps.append({"phase_id": pid, "disposition": "verified", "ok": bool(ok)})
        if not ok:
            print("BLOCKED at %s (fail-closed). No phase skips; author the artifact and re-run."
                  % pid, file=sys.stderr)
            return EXIT_GATE
    write_index_and_manifest(bk, delivery, measured)
    cert = write_certificate(bk, delivery, steps, measured)
    if cert:
        print("CERTIFICATE ISSUED: %s (sha %s)" % (cert["path"], cert["sha"][:12]))
    print("ALL PHASES PASSED (P0->P8).")
    return EXIT_PASS


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
    return run(Book(run_dir))


if __name__ == "__main__":
    sys.exit(main())
