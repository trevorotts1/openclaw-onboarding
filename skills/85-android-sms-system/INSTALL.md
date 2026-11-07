# INSTALL — Android SMS System (myCRMSIM)

Skill: `85-android-sms-system` · Version 1.0.0 · Date 2026-11-06

This skill answers questions about myCRMSIM from an **offline documentation set**.
It does not scrape the live site at answer time, and it does not need the internet
once the docs are on disk. Installing the skill is two things:

1. The skill folder goes to `~/.openclaw/skills/85-android-sms-system/`
2. The documentation set is present at the expected path

Step 1 is the same every time. Step 2 has two cases: **A** the docs are already
there, **B** they are not.

---

## Expected documentation path

```
$HOME/Downloads/openclaw-master-files/mycrmsim/
```

On the operator box that resolves to:

```
$HOME/Downloads/openclaw-master-files/mycrmsim/
```

Required structure at that path:

| Entry | What it is | Required? |
|---|---|---|
| `00-INDEX.md` | Master index, 156 articles by category | Yes |
| `articles/` | 156 Markdown articles in 7 category folders | Yes |
| `categories/` | 36 category index pages | Yes |
| `_manifest.json` | Machine-readable index of every document | Yes |
| `_labels.json` | Titles, summaries, tags per document | Yes |
| `_assets/` | 660 images/GIFs referenced by the articles — **not installed by design** (deleted to avoid repo bloat) | No |
| `_source-html/` | 185 raw saved pages — absent; removed in cleanup | No |
| `_assets-manifest.json` | Asset checksums | Optional |
| `_labels-parts/` | Label shards used to build `_labels.json` | Optional |

The skill reads `articles/`, `00-INDEX.md`, `_manifest.json` and `_labels.json`.
`_assets/` is absent by design in this set — the image files were deleted to avoid
repo bloat. The skill answers every question from article text; it just cannot
show a screenshot. Expect 660 image reference lines in the articles and zero image
files on disk. That is correct.

---

## Case A — documentation set already present

Nothing to download. Confirm it is the right set, then install the skill folder.

```bash
ls -d ~/Downloads/openclaw-master-files/mycrmsim
```

If that prints the directory, jump straight to [Install the skill folder](#install-the-skill-folder),
then run the [Verification](#verification) block.

Do not re-download over an existing set. Run verification first; if it passes,
the set is good.

---

## Case B — documentation set missing

`support.mycrmsim.com` has **no single downloadable archive** of the whole set.
It is a live support site: 185 pages listed in its sitemap, of which 148 are
article URLs. The 156-article offline set was built by crawling that site and
converting each page to Markdown, then generating `_manifest.json`,
`_labels.json` and `00-INDEX.md` on top.

That means Case B splits again.

### B1 — get a copy of the prepared set (preferred)

The prepared set is self-contained and reads fully offline. Copy the whole
directory from any machine that already has it:

```bash
rsync -a --info=progress2 \
  $HOME/Downloads/openclaw-master-files/mycrmsim/ \
  ~/Downloads/openclaw-master-files/mycrmsim/
```

Copy the directory **as a unit**. Splitting it — moving `articles/` without
`_manifest.json` and `_labels.json` — leaves the skill able to read text but
unable to resolve doc IDs, tags or the index.

Then run [Verification](#verification).

### B2 — rebuild from the live site

Only do this when no prepared copy exists anywhere. The sitemap is the
authoritative list of pages:

```bash
curl -fsS https://support.mycrmsim.com/sitemap.xml -o /tmp/sitemap.xml
grep -o '<loc>[^<]*' /tmp/sitemap.xml | sed 's/<loc>//' > /tmp/urls.txt
wc -l /tmp/urls.txt          # expect 185
grep -c '/article/' /tmp/urls.txt   # expect 148
```

Fetch and convert each article page with pandoc (HTML to Markdown), writing into
`articles/` under the category folders. Do **not** download images — this set is
image-free by design. The converted pages will carry image reference lines that
resolve to nothing, which is expected and harmless.

Rebuild limits you must know before you start:

- You get article text only. `_manifest.json`, `_labels.json`, `_labels-parts/`
  and `00-INDEX.md` are **not** on the site — they were generated. A pure rebuild
  will not reproduce them, so doc-ID lookups, tag search and the index page will
  be missing until those files are regenerated.
- The sitemap lists 148 article URLs; the prepared set has 156 articles. The
  extra articles were reachable by crawl, not by sitemap. A sitemap-only rebuild
  comes up short.
- Category assignment (`01-Devices and Installation` … `07-Talk To The Team`)
  has to be derived from each page's breadcrumb.

If the task is "answer client questions about myCRMSIM", B1 is correct and B2 is
a fallback that costs hours and loses structure. Say so rather than quietly
starting a crawl.

### Size — what you are actually copying

| Part | Size | Needed to answer questions? |
|---|---|---|
| `articles/` + `categories/` + index + manifests + labels | **~2 MB of text** | Yes — this is the whole knowledge base |
| `_source-html/` | **absent — 37 MB of raw pages removed in cleanup** | No — provenance only |
| `_assets/` | **not present** — 788 MB of images and GIFs deleted to avoid repo bloat | No — the set is image-free by design |

The text is about 2 MB. The 788 MB of images that used to sit beside it are gone
on purpose. Every one was a screenshot or GIF illustrating a step the article
already describes in words, so nothing in the answer quality depends on them.

Consequences:

- **The set is text-only: there is no `_source-html/` to copy.** The skill
  never reads it.
- **Expect 660 dangling image reference lines.** Article links look like
  `../../../_assets/MCS-042/01-CCx2A0eQju.gif` and resolve to nothing. That is
  correct for this set — leave them alone rather than rewriting 660 links.
- **Do not restore `_assets/` from the live site into a repo.** It was deleted to
  keep the repo small. Re-adding it undoes that decision.

---

## Install the skill folder

The skill must be readable at the installed path. Two supported arrangements:

```bash
# Symlink from the build repo (development; edits go live immediately)
ln -sfn $HOME/Downloads/openclaw-master-files/85-android-sms-system \
        ~/.openclaw/skills/85-android-sms-system
```

```bash
# Copy (a client box, or once the skill is frozen)
cp -R $HOME/Downloads/openclaw-master-files/85-android-sms-system \
      ~/.openclaw/skills/
```

Then load it the way the gateway loads any skill:

```bash
ls ~/.openclaw/skills/85-android-sms-system/SKILL.md
```

A missing `SKILL.md` at that path means the install did not take.

---

## Verification

Run all four checks. Checks 1, 2 and 4 are pass/fail and independent; a failure in
one is not excused by a pass in another. Check 3 is informational — it reports the
image reference count and is expected to show 0 files.

### 1. Article count — expect 156

```bash
find ~/Downloads/openclaw-master-files/mycrmsim/articles -name '*.md' -type f | wc -l
```

Expected: `156`. Fewer means articles are missing. More means stray files
(backups, drafts) landed in the tree.

Cross-check against the manifest — this catches files that exist but were never
indexed, and index entries whose file was deleted:

```bash
python3 -I - <<'PY'
import json, os
root = os.path.expanduser("~/Downloads/openclaw-master-files/mycrmsim")
m = json.load(open(os.path.join(root, "_manifest.json")))
print("manifest entries:", len(m))
print("files present:   ", sum(os.path.isfile(os.path.join(root, e["file"])) for e in m))
PY
```

Both numbers must be `156`. Manifest 156 with files present 156 means the set is
complete and consistent.

### 2. `00-INDEX.md` exists and is populated

```bash
test -f ~/Downloads/openclaw-master-files/mycrmsim/00-INDEX.md && echo "index present"
grep -c '^### ' ~/Downloads/openclaw-master-files/mycrmsim/00-INDEX.md
```

Expected: `index present`, then `7` — one section heading per category. An index
present but with zero `###` headings is an empty stub, not the real index.

### 3. Image links — informational only, not a pass/fail check

The articles carry **660 image reference lines**. The image files were deleted on
purpose to avoid repo bloat, so `_assets/` is absent and **0 of the 660 resolve**.
**That is correct for this set** — it is an image-free install. The skill answers
from article text and never opens an image.

This check is here to prove the count, not to gate the install:

```bash
python3 -I - <<'PY'
import os, re
root = os.path.expanduser("~/Downloads/openclaw-master-files/mycrmsim")
pat = re.compile(r'!\[[^\]]*\]\(([^)]+)\)')
tot = ok = bad = 0
for dp, _, fns in os.walk(os.path.join(root, "articles")):
    for fn in fns:
        if not fn.endswith(".md"):
            continue
        for target in pat.findall(open(os.path.join(dp, fn), encoding="utf-8", errors="replace").read()):
            tot += 1
            t = target.split()[0]
            if t.startswith(("http://", "https://")):
                ok += 1
                continue
            if os.path.isfile(os.path.normpath(os.path.join(dp, t))):
                ok += 1
            else:
                bad += 1
print("image links:", tot, "resolved:", ok, "broken:", bad)
PY
```

Expected: `image links: 660 resolved: 0 broken: 660`.

Read that line as **660 references, 0 files — correct**. Do not treat the 660 as a
defect, do not go hunting for a download, and do not try to restore `_assets/`.
The only failure mode here is a reference count other than 660, which would mean
the article tree is incomplete or has been edited.

### 4. Skill folder is readable

```bash
ls ~/.openclaw/skills/85-android-sms-system/{SKILL.md,INSTRUCTIONS.md,INSTALL.md}
```

Expected: all three paths print.

### Pass condition

All of the following, or the install is not complete:

- 156 article files, 156 manifest entries, 156 files present
- `00-INDEX.md` present with 7 category headings
- 660 image references, 0 resolved — expected, by design; not a failure
- `SKILL.md`, `INSTRUCTIONS.md`, `INSTALL.md` all readable at the installed path

Report the numbers you actually saw. A summary that says "installed fine" without
the four counts is not verification.

---

## VPS note — persistence

On a VPS box, **only `/data/.openclaw/` persists.** Everything else is wiped on
rebuild or container recreation.

That has one hard consequence for this skill: the documentation set must live
inside the persistent volume, not in `~/Downloads/`, or it vanishes on the next
rebuild.

### 1. Copy the text into the persistent root

`cp` does not create its destination. Copying several sources into a path that
does not exist fails with `cp: ... No such file or directory`, so create the
target first, then copy into it.

```bash
# VPS: put the text under the persistent root
DOCS=/data/.openclaw/docs/myCRMSIM-Support-Docs-2026-11-05

# Step 1 — create the destination. cp will NOT create it for you.
mkdir -p "$DOCS"

# Step 2 — copy the sources INTO it.
cp -R ~/Downloads/openclaw-master-files/mycrmsim/articles \
      ~/Downloads/openclaw-master-files/mycrmsim/categories \
      ~/Downloads/openclaw-master-files/mycrmsim/00-INDEX.md \
      ~/Downloads/openclaw-master-files/mycrmsim/_manifest.json \
      ~/Downloads/openclaw-master-files/mycrmsim/_labels.json \
      "$DOCS"/
```

### 2. Verify the copy — the same four counts

These are the four checks from the Verification section above, pointed at the
persistent path.

```bash
DOCS=/data/.openclaw/docs/myCRMSIM-Support-Docs-2026-11-05

# Check 1 — article files. Expect 156.
find "$DOCS/articles" -name '*.md' -type f | wc -l

# Check 1b — manifest entries and files present. Both 156.
python3 -I - "$DOCS" <<'PY'
import json, os, sys
root = sys.argv[1]
m = json.load(open(os.path.join(root, "_manifest.json")))
print("manifest entries:", len(m))
print("files present:   ", sum(os.path.isfile(os.path.join(root, e["file"])) for e in m))
PY

# Check 2 — index present with 7 category headings.
test -f "$DOCS/00-INDEX.md" && echo "index present"
grep -c '^### ' "$DOCS/00-INDEX.md"

# Check 3 — image references. Informational: 660 expected, 0 files is correct.
python3 -I - "$DOCS" <<'PY'
import os, re, sys
root = sys.argv[1]
pat = re.compile(r'!\[[^\]]*\]\(([^)]+)\)')
tot = ok = bad = 0
broken = []
for dp, _, fns in os.walk(os.path.join(root, "articles")):
    for fn in fns:
        if not fn.endswith(".md"):
            continue
        for target in pat.findall(open(os.path.join(dp, fn), encoding="utf-8", errors="replace").read()):
            tot += 1
            t = target.split()[0]
            if t.startswith(("http://", "https://")):
                ok += 1
                continue
            if os.path.isfile(os.path.normpath(os.path.join(dp, t))):
                ok += 1
            else:
                bad += 1
                broken.append((fn, t))
print("image links:", tot, "resolved:", ok, "broken:", bad)
for fn, t in broken[:10]:
    print("  BROKEN:", fn, "->", t)
PY

# Check 4 — skill folder readable at the VPS install path.
ls /data/.openclaw/skills/85-android-sms-system/{SKILL.md,INSTRUCTIONS.md,INSTALL.md}
```

Expected: `156`; then `manifest entries: 156` and `files present: 156`; then
`index present` and `7`; then `image links: 660 resolved: 0 broken: 660` — which is
correct for this image-free set and is not a defect. Check 4 requires the skill
folder to sit under `/data/.openclaw/skills/`; see the last bullet below.

If a check prints an error instead of a number (`find: ... No such file or
directory`, `grep: ... No such file`), the copy failed — read the error, not the
count. `grep` exits 1 on zero matches, which here means an empty index stub.

### 3. Point the skill at the VPS path

Set one environment variable in the box's OpenClaw env. Nothing in the skill has
to be edited:

```bash
ASMS_DOCS_DIR=/data/.openclaw/docs/myCRMSIM-Support-Docs-2026-11-05
```

`qc-android-sms-system.sh` reads the same variable, so verification and answering
stay on the same path. Resolution order when the variable is unset: `docs/` beside
`SKILL.md`, then `$HOME/Downloads/openclaw-master-files/mycrmsim`.

If you would rather not set a variable, edit the docs-root lines in `SKILL.md`
(the docs root and the `00-INDEX.md` line) and `INSTRUCTIONS.md` (the docs root
line, the example article path, and the `cd` in the tools section) by hand.

### 4. Optional: symlink instead of editing the path

Only if you would rather leave `SKILL.md` and `INSTRUCTIONS.md` as they are. The
prerequisite is absolute: **the home path must not already exist.** If
`~/Downloads/openclaw-master-files/mycrmsim` already exists as a directory,
`ln -sfn` puts the link *inside* it instead of replacing it, and the skill keeps
reading the stale copy.

```bash
# Prerequisite check. Must print NOTHING. If it prints a path, stop: the home
# copy exists and ln -sfn would nest the link inside it.
ls -d ~/Downloads/openclaw-master-files/mycrmsim 2>/dev/null

# Run only after the check above printed nothing:
ln -sfn /data/.openclaw/docs/myCRMSIM-Support-Docs-2026-11-05 \
        ~/Downloads/openclaw-master-files/mycrmsim

# Confirm it is a link and where it points.
ls -ld ~/Downloads/openclaw-master-files/mycrmsim
readlink ~/Downloads/openclaw-master-files/mycrmsim
```

Expected: an `l` permission bit, and `readlink` printing
`/data/.openclaw/docs/myCRMSIM-Support-Docs-2026-11-05`.

If the prerequisite check printed a path, delete the stale home copy first. This
removes the home copy only — the persistent VPS copy is untouched:

```bash
# DESTRUCTIVE: home copy only. Confirm the path below reads exactly
# ~/Downloads/openclaw-master-files/mycrmsim before running it.
# It does not touch /data/.openclaw/docs/.
rm -rf ~/Downloads/openclaw-master-files/mycrmsim
```

Then re-run the `ln -sfn` line and `readlink` above.

Two things that make this worse on a VPS than on a Mac:

- **The docs are about 2 MB of text.** The 788 MB of images was deleted on purpose;
  there is nothing large left to copy, and the image check reports 660 references
  against 0 files by design.
- **`/data/.openclaw/skills/`** is where the skill folder belongs on a VPS — a
  skill installed under a home directory outside `/data/.openclaw/` does not
  survive a rebuild.

Verify after copying that both the skill and the docs sit under `/data/.openclaw/`:

```bash
ls -d /data/.openclaw/skills/85-android-sms-system /data/.openclaw/docs/myCRMSIM-Support-Docs-2026-11-05
```

---

## Troubleshooting install problems

| Symptom | Cause | Fix |
|---|---|---|
| Manifest 156, files present < 156 | Files deleted from `articles/` after the manifest was generated | Re-copy the missing articles; do not edit the manifest |
| Article files 156, manifest < 156 | Stray or unindexed files in the tree | Find files whose doc ID is not in `_manifest.json` |
| Image links 660, resolved 0 | `_assets/` is absent | Expected — the set is image-free by design. Not a fault; do not restore images |
| Image reference count is not 660 | Article tree incomplete or edited | Re-copy `articles/`; the count is the integrity signal, not the file count |
| `00-INDEX.md` present, 0 headings | Empty stub copied instead of the real file | Re-copy `00-INDEX.md` |
| Skill answers "no documentation found" | Docs path differs from the expected `~/Downloads/` path, or the VPS copy is outside `/data/.openclaw/` | Set the docs path, or symlink it to the expected location |
| Skill loads but answers vaguely | `_labels.json` missing, so tag and summary lookup is unavailable | Copy `_labels.json` and `_labels-parts/` |
| Docs gone after a VPS rebuild | Set lived outside `/data/.openclaw/` | Move it under `/data/.openclaw/` and re-run verification |

---

## What this install does not do

- It does not crawl `support.mycrmsim.com` at answer time.
- It does not require the internet after the text lands.
- It does not need `_assets/` to answer questions.
- It does not modify `AGENTS.md`, `MEMORY.md` or `TOOLS.md`. Core-file pointers
  are `CORE_UPDATES.md`'s job, and that file adds pointers only — no learning or
  installation receipts go into `MEMORY.md`.
