# QC Checklist: Android SMS System (skill 85)

Quality gate for the skill built at
`/Users/blackceomacmini/Downloads/openclaw-master-files/85-android-sms-system`
and installed at `~/.openclaw/skills/85-android-sms-system/`.

Source documentation set (read-only):
`/Users/blackceomacmini/Downloads/openclaw-master-files/mycrmsim`

A reviewer runs every numbered check below and records PASS or FAIL with the
command output. Self-approval is not evidence. A check without a recorded
output is UNRUN, and UNRUN is FAIL.

---

## 0. Packaging parity (PASS/FAIL)

- [ ] **0.1** The folder contains exactly these deliverables, matching the GHL
      skill packaging:
      `SKILL.md`, `INSTRUCTIONS.md`, `INSTALL.md`, `EXAMPLES.md`,
      `CORE_UPDATES.md`, `QC.md`, `PREREQS.json`, `CHANGELOG.md`,
      `skill-version.txt`, the deep reference `android-sms-system-full.md`,
      one `qc-android-sms-system.sh` script, one `.skill` bundle.
- [ ] **0.2** `skill-version.txt` reads `v1.0.0` or `1.0.0`.
- [ ] **0.3** `CHANGELOG.md` has a `1.0.0` entry carrying the release date for
      2026-11-06 in either form: the ISO date `2026-11-06` or the long form
      `November 6, 2026`. The shipped entry reads
      `## [v1.0.0] - November 6, 2026`, so the long form is what must pass.
- [ ] **0.4** `PREREQS.json` parses as JSON and declares its six prerequisites by
      `id` and `type`: `docs-folder` (path), `article-count` (content, minimum
      156), `python3` (runtime), `bash` (runtime), `article-images` (content,
      optional, minimum 660 images ~788 MB), `support-url` (service, optional).
      It declares no prerequisite skill; it names no other skill.
- [ ] **0.5** Every file named in `SKILL.md` exists. No listed file is missing;
      no shipped file is unlisted.
- [ ] **0.6** The `.skill` bundle is a valid zip, contains `SKILL.md`, and its
      `SKILL.md` is byte-identical to the loose `SKILL.md`.

PASS: 0.1–0.6 all true. FAIL: any missing file, any version/date mismatch,
any bundle drift.

Reproduce 0.3 and 0.4:

```bash
cd /Users/blackceomacmini/Downloads/openclaw-master-files/85-android-sms-system
python3 -I - <<'EOF'
import json,re
t=open('CHANGELOG.md').read()
ok=any('1.0.0' in l and re.search(r'2026-11-06|November\s+6,\s+2026', l)
       for l in t.splitlines())
assert ok, 'no 1.0.0 entry carrying 2026-11-06 or November 6, 2026'
print('changelog OK')
d=json.load(open('PREREQS.json'))
rows={p['id']: p['type'] for p in d['prerequisites']}
want={'docs-folder':'path','article-count':'content','python3':'runtime',
      'bash':'runtime','article-images':'content','support-url':'service'}
assert rows==want, (sorted(rows), sorted(want))
assert not any(p.get('type')=='skill' for p in d['prerequisites']), 'skill prereq'
print('prereqs OK', len(rows), 'entries')
EOF
```

PASS prints `changelog OK` and `prereqs OK 6 entries`.

---

## 1. Frontmatter valid (PASS/FAIL)

- [ ] **1.1** `SKILL.md` opens on line 1 with `---` and closes frontmatter with
      a second `---`.
- [ ] **1.2** Frontmatter parses as YAML with `name` and `description` present.
- [ ] **1.3** `name: android-sms-system` (lowercase, hyphenated, matches the
      folder suffix).
- [ ] **1.4** `description` is one sentence, under 1024 characters, and contains
      no newline.
- [ ] **1.5** `description` names all five channels: SMS, iMessage, WhatsApp,
      RCS, voice calling.
- [ ] **1.6** No unknown frontmatter key that the loader rejects.

PASS: 1.1–1.6 all true. FAIL: missing delimiters, unparseable YAML, name
mismatch, or a description that omits any channel.

Reproduce:

```bash
python3 -I - <<'EOF'
import re,sys
p='/Users/blackceomacmini/Downloads/openclaw-master-files/85-android-sms-system/SKILL.md'
t=open(p).read()
m=re.match(r'^---\n(.*?)\n---\n', t, re.S)
assert m, 'frontmatter missing'
fm=m.group(1)
vals=dict(re.findall(r'^(\w+):\s*(.*)$', fm, re.M))
assert vals.get('name')=='android-sms-system', vals.get('name')
d=vals.get('description','')
assert d and '\n' not in d and len(d)<1024, 'description problem'
for w in ['SMS','iMessage','WhatsApp','RCS','calling']:
    assert w.lower() in d.lower(), f'missing channel {w}'
print('frontmatter OK', len(d), 'chars')
EOF
```

PASS prints `frontmatter OK`; any assertion is FAIL.

---

## 2. Documentation path correct (PASS/FAIL)

- [ ] **2.1** Every skill file that names the source docs uses the absolute path
      `/Users/blackceomacmini/Downloads/openclaw-master-files/mycrmsim`.
      No relative path, no `~` path, no stale download date.
- [ ] **2.2** `00-INDEX.md`, `_manifest.json`, `_labels.json`, `articles/`,
      `categories/`, `_assets/`, `_source-html/` all exist at that root.
- [ ] **2.3** No skill file points at `~/Downloads` as the runtime location for
      installed articles; the deep reference ships inside the skill folder so an
      installed agent does not depend on the operator's Downloads directory.

PASS: 2.1–2.3 all true. FAIL: wrong root, stale date, or a runtime dependency on
the operator's Downloads directory.

---

## 3. Article count is 156 (PASS/FAIL)

- [ ] **3.1** `find articles -type f -name '*.md' | wc -l` returns `156`.
- [ ] **3.2** `_manifest.json` is a list of 156 objects, each with `doc_id`,
      `title`, `file`, `category`.
- [ ] **3.3** Every `file` value in the manifest exists on disk.
- [ ] **3.4** No two manifest rows share a `doc_id`.

PASS: all four true. FAIL: any count other than 156, any dangling manifest path,
any duplicate Doc ID.

```bash
cd /Users/blackceomacmini/Downloads/openclaw-master-files/mycrmsim
find articles -type f -name '*.md' | wc -l
python3 -I - <<'EOF'
import json,os
d=json.load(open('_manifest.json'))
assert len(d)==156, len(d)
ids=[x['doc_id'] for x in d]
assert len(ids)==len(set(ids)), 'duplicate doc_id'
missing=[x['file'] for x in d if not os.path.isfile(x['file'])]
assert not missing, missing[:3]
print('manifest OK', len(d))
EOF
```

Agent-version facts that must also be true in the deep reference: 36 category
pages, 660 images, `_assets/` about 788 MB.

---

## 4. Index has 156 entries (PASS/FAIL)

- [ ] **4.1** `00-INDEX.md` contains 156 unique `MCS-###` Doc IDs.
- [ ] **4.2** It contains 156 article links under `articles/`.
- [ ] **4.3** Every linked path in the index resolves to a real file.
- [ ] **4.4** Every Doc ID in `_manifest.json` appears in the index, and every
      index Doc ID appears in the manifest (set equality, both directions).

PASS: 4.1–4.4 all true. FAIL: count drift, broken link, or set mismatch.

```bash
cd /Users/blackceomacmini/Downloads/openclaw-master-files/mycrmsim
python3 -I - <<'EOF'
import json,re,os
t=open('00-INDEX.md').read()
ids=set(re.findall(r'MCS-\d{3}', t))
print('index doc ids', len(ids))
assert len(ids)==156, len(ids)
links=re.findall(r'\]\((articles/[^\n]*?\.md)\)', t)
assert len(links)==156, len(links)
bad=[p for p in links if not os.path.isfile(p)]
assert not bad, bad[:3]
m={x['doc_id'] for x in json.load(open('_manifest.json'))}
assert ids==m, (sorted(ids-m)[:5], sorted(m-ids)[:5])
print('index OK', len(links), 'links')
EOF
```

PASS prints `index doc ids 156` and `index OK 156 links`.

---

## 5. Five examples cite real files (PASS/FAIL)

`EXAMPLES.md` must carry at least five worked examples, and every example must
cite a real article file. The five minimum areas and their real cited files:

| # | Area | Required cited file |
|---|---|---|
| 1 | Android SMS install | `articles/01-Devices and Installation/01-myCRMSIM SMS Installation and Setup/01-SMS Device Setup/MCS-131 - Setting Up Your Android Device with myCRMSIM SMS Gateway.md` |
| 2 | SMS troubleshooting | `articles/01-Devices and Installation/01-myCRMSIM SMS Installation and Setup/01-SMS Trouble Shooting/MCS-015 - What Happens If Messages Fail.md` |
| 3 | iMessage | `articles/01-Devices and Installation/01-myCRMSIM iMessage Installation and Setup/MCS-081 - iMessage Trouble Shooting.md` |
| 4 | WhatsApp | `articles/01-Devices and Installation/01-myCRMSIM WhatsApp Installation and Setup/MCS-104 - What to Do If Your WhatsApp Number Gets Restricted.md` |
| 5 | HighLevel integration | `articles/04-Integrations/04-HighLevel Setup/MCS-042 - myCRMSIM HighLevel Integration Guide.md` |

- [ ] **5.1** At least five examples present, covering those five areas.
- [ ] **5.2** Each of the five paths above appears in `EXAMPLES.md` exactly as
      written, and each file exists on disk.
- [ ] **5.3** Every other path cited anywhere in `EXAMPLES.md` also exists on
      disk and carries a Doc ID present in `00-INDEX.md`. No invented filename,
      no Doc ID outside the index, no URL-only reference with no local file.
- [ ] **5.4** Each example states the trigger words, the concrete steps, and the
      expected outcome. A reader can run it without opening another file.
- [ ] **5.5** The citation count is five or more, and every cited path resolves.

FAIL on any invented path, a missing minimum area, or an example with no
expected outcome.

---

## 6. No article text duplicated into the skill (PASS/FAIL)

The Teach Yourself Protocol rule: a deep file is complete, core files get only a
one-to-two-sentence pointer naming WHAT, WHERE (absolute path), and WHEN
(concrete trigger words).

- [ ] **6.1** No skill file contains a verbatim run of 80 or more consecutive
      words from any article in the docs set.
- [ ] **6.2** `SKILL.md`, `INSTRUCTIONS.md`, `INSTALL.md`, `EXAMPLES.md`,
      `CORE_UPDATES.md` each stay under their own file budget, and every
      reference to the deep material is a pointer with path plus trigger words.
      Budgets are character counts on the shipped file:

      | File | Budget (chars) | Measured 2026-11-06 |
      |---|---|---|
      | `SKILL.md` | 12000 | 8323 |
      | `INSTRUCTIONS.md` | 18000 | 14871 |
      | `INSTALL.md` | 22000 | 17473 |
      | `EXAMPLES.md` | 18000 | 13867 |
      | `CORE_UPDATES.md` | 8000 | 5463 |

      Measured values are evidence for this release, not the limit. A file over
      its budget fails the check and the fix is to cut prose, never to raise the
      budget.
- [ ] **6.3** The deep reference is complete: it is not truncated mid-article,
      every article it claims to cover is present, and it does not stop with an
      ellipsis or a "see the site" hand-off.
- [ ] **6.4** `CORE_UPDATES.md` adds no learning receipts, no install receipts,
      and no article bodies to `MEMORY.md`.
- [ ] **6.5** Core-file budget statements match the protocol: `AGENTS.md` 15000,
      `MEMORY.md` 8000, `TOOLS.md` 15000 characters.

Reproduce the 6.2 budget check:

```bash
cd /Users/blackceomacmini/Downloads/openclaw-master-files/85-android-sms-system
python3 -I - <<'EOF'
budgets={'SKILL.md':12000,'INSTRUCTIONS.md':18000,'INSTALL.md':22000,
         'EXAMPLES.md':18000,'CORE_UPDATES.md':8000}
over=[]
for f,lim in budgets.items():
    n=len(open(f,encoding='utf-8').read())
    print(f, n, 'chars, budget', lim, 'OK' if n<lim else 'OVER')
    if n>=lim: over.append(f)
assert not over, over
print('budgets OK', len(budgets))
EOF
```

PASS prints one `OK` line per file and `budgets OK 5`.

Reproduce the duplication check, reporting only file and offset, never the text:

```bash
python3 -I - <<'EOF'
import os,re
skill='/Users/blackceomacmini/Downloads/openclaw-master-files/85-android-sms-system'
docs='/Users/blackceomacmini/Downloads/openclaw-master-files/mycrmsim/articles'
def words(s): return re.findall(r"[A-Za-z0-9']+", s.lower())
arts=[]
for r,_,fs in os.walk(docs):
    for f in fs:
        if f.endswith('.md'):
            arts.append(words(open(os.path.join(r,f),errors='ignore').read()))
grams=set()
for w in arts:
    for i in range(0, max(0,len(w)-80)):
        grams.add(' '.join(w[i:i+80]))
hits=[]
for f in os.listdir(skill):
    if f.endswith('.md'):
        w=words(open(os.path.join(skill,f),errors='ignore').read())
        for i in range(0, max(0,len(w)-80)):
            if ' '.join(w[i:i+80]) in grams:
                hits.append((f,i))
print('duplicate 80-word runs:', len(hits), hits[:5])
EOF
```

PASS requires `duplicate 80-word runs: 0`.

---

## 7. No secrets (PASS/FAIL)

- [ ] **7.1** No credential value of any kind in any skill file: no API key,
      Private Integration Token, bearer token, password, cookie, session ID,
      phone number belonging to a real person, or client name.
- [ ] **7.2** No `.env`, `.pem`, `.key`, or credential JSON shipped in the
      folder or inside the `.skill` bundle.
- [ ] **7.3** No article screenshot or asset is re-hosted with a visible token,
      account email, or QR pairing payload containing credentials.
- [ ] **7.4** The secrets scan reports file and line only; the reviewer never
      prints a matched value into the transcript.

```bash
cd /Users/blackceomacmini/Downloads/openclaw-master-files/85-android-sms-system
grep -rInE '(sk-[A-Za-z0-9]{10,}|ghp_[A-Za-z0-9]{20,}|xox[baprs]-|AKIA[0-9A-Z]{16}|Bearer [A-Za-z0-9._-]{20,}|pit-[A-Za-z0-9-]{10,}|password\s*[:=]\s*\S+|eyJ[A-Za-z0-9_-]{20,})' \
  --include='*.md' --include='*.json' --include='*.sh' --include='*.txt' . || echo 'no secret patterns'
```

PASS: prints `no secret patterns`, and the binary/zip check finds no `.env` or
key file. FAIL: any hit that is a real value, even if the pattern is generic.

---

## 8. Install instructions work from a clean box (PASS/FAIL)

Run on a scratch profile. Never against the live fleet. Never `pm2 jlist` or
`pm2 describe`; `pm2 list` only.

- [ ] **8.1** `INSTALL.md` is ordered, copy-pasteable, and names the exact
      install destination `~/.openclaw/skills/85-android-sms-system/`.
- [ ] **8.2** Every command in `INSTALL.md` is idempotent or safe to re-run.
- [ ] **8.3** On an empty scratch HOME, following `INSTALL.md` verbatim puts all
      packaged files at the install destination and `SKILL.md` frontmatter still
      parses there.
- [ ] **8.4** The installed skill loads: an agent asked "what does the Android
      SMS System skill do" answers with all five channels and the docs root.
- [ ] **8.5** `qc-android-sms-system.sh` exits `0` on the installed copy.
- [ ] **8.6** No step requires network access, a client credential, a Mac-only
      absolute user path, or the operator's `~/Downloads` docs folder at runtime.
- [ ] **8.7** Uninstall is documented and complete: removing the skill folder
      leaves no dangling core-file pointers.
- [ ] **8.8** Scratch profile is deleted after the test.

```bash
export SCRATCH=/private/tmp/asms-run/tmp/qc-skl-007
rm -rf "$SCRATCH"; mkdir -p "$SCRATCH/home"
HOME="$SCRATCH/home" bash -c '<INSTALL.md command sequence, verbatim>'
test -f "$SCRATCH/home/.openclaw/skills/85-android-sms-system/SKILL.md" && echo installed
HOME="$SCRATCH/home" bash "$SCRATCH/home/.openclaw/skills/85-android-sms-system/qc-android-sms-system.sh"; echo "rc=$?"
```

PASS: `installed` printed, `rc=0`, and checks 8.1–8.8 recorded. FAIL: any manual
step the doc omits, any network dependency, any nonzero `qc` exit.

---

## 9. Evidence rules

- [ ] **9.1** Each check above has its command output pasted into the review
      record, or a stated reason it is N/A.
- [ ] **9.2** The reviewer is not the builder of the file under test.
- [ ] **9.3** No claim of PASS rests on reading a file the reviewer did not open.
- [ ] **9.4** Negative findings name the source and the search performed
      (path, pattern, count), never a bare "not found".
- [ ] **9.5** A failed check names the file, line and exact fix; the fix list is
      what the repair lane consumes.

---

## 10. Scoring and gate

Score out of 10, one point per section 0–9.

| Section | Point | What it proves |
|---|---|---|
| 0 Packaging | 1.0 | Files complete, version and bundle consistent |
| 1 Frontmatter | 1.0 | Loader accepts it, name correct |
| 2 Docs path | 1.0 | Correct absolute root, no runtime Downloads dependency |
| 3 Article count | 1.0 | 156 files, 156 manifest rows, no dangling paths |
| 4 Index | 1.0 | 156 unique Doc IDs, 156 resolving links, set equality |
| 5 Examples | 1.0 | Five or more real, runnable examples with resolving citations |
| 6 No duplication | 1.0 | Zero 80-word runs; pointers only in core files |
| 7 No secrets | 1.0 | Clean scan, no credential files |
| 8 Clean-box install | 1.5 | Installs, loads, qc script exits 0 |
| 9 Evidence | 0.5 | Output recorded, independent reviewer |

**Gate: 8.5/10.** Below 8.5 is FAIL. Any single item in sections 1, 7, or 8 that
fails is a hard FAIL regardless of score.

Record the verdict:

- **QC Score:** ____ / 10
- **Status:** PASS / FAIL / BLOCKED
- **Failed items:** ____________________________________________
- **Reviewer:** ____________________  **Date:** ______________
- **Head commit reviewed:** ____________________________________

---

## 11. QC loop rule

- At most **5 total QC rounds**.
- Each round records every failed item, applies the smallest targeted fix, and
  re-runs the failed checks plus directly affected dependencies only.
- After the 5th round, stop and escalate with: failed sections, what was tried,
  what blocks it. Never widen the diff to make a check pass.
