/* =============================================================================
 * BOOK WRITER MINI-APP (Wave B) :: U08 — BANNED-STRING LINT
 * -----------------------------------------------------------------------------
 * Scans the shipped mini-app UI copy for the anti-anxiety overwhelm words the
 * warm low-overwhelm UI may never use (MASTER-PLAN section 5 + Playwright
 * T5 warmth guard):
 *
 *     Submit / Required / Error / Deadline / You must
 *
 * The exact banned tokens are (case-insensitive, word-boundary aware):
 *     "submit" "required" "error" "deadline" "you must"
 *
 * On ANY hit the script FAILS with exit code 2 and prints every offender with
 * file, line, and matched token. Zero hits prints PASS and exits 0.
 *
 * USAGE
 *   node lint-banned-strings.js                 # scan this repo's mini-app copy
 *   node lint-banned-strings.js <path...>       # scan specific files/dirs
 *   node lint-banned-strings.js --selftest      # pure-logic self-test
 *   node lint-banned-strings.js --self-test     # alias of --selftest
 *
 * The scan is heuristic and conservative: a match only counts when the banned
 * word appears as a full word (so "submission", "required_notes" as a key,
 * "my_error_message", or "deadlines" do NOT trip). Copy inside the source
 * itself (this comment block) is excluded from the shipped-copy scan by only
 * checking the string literals and JSON-ish .md/.json/.html files under the
 * mini-app tree — and the U08 unit's own data files are verified clean.
 * ============================================================================= */
'use strict';

const fs = require('fs');
const path = require('path');

// ---------------------------------------------------------------------------
// Banned overwhelm words (lowercased). The single authority for T5.
// ---------------------------------------------------------------------------
const BANNED = ['submit', 'required', 'error', 'deadline', 'you must'];

// Build word-boundary regexes: "submit" must match as its own word, not inside
// "submission" or "submitted"; "you must" as a contiguous phrase.
const RE_FLAGS = 'gi';
const PATTERNS = BANNED.map((w) => ({
  word: w,
  re: new RegExp('\\b' + w.replace(/ /g, '\\s+') + '\\b', RE_FLAGS)
}));

// File extensions whose text content is treated as shipped copy. .js files are
// scanned for banned strings inside string literals (the shipped UI copy).
const COPY_EXTENSIONS = new Set(['.html', '.htm', '.md', '.json', '.js', '.txt']);
// Never scan these names (lockfiles, build artifacts).
const SKIP_NAMES = new Set(['package-lock.json', 'yarn.lock', 'pnpm-lock.yaml']);

function isCopyFile(p) {
  const base = path.basename(p);
  if (SKIP_NAMES.has(base)) return false;
  return COPY_EXTENSIONS.has(path.extname(p).toLowerCase());
}

// Strip JS string literals only (single/double/backtick, respecting escapes)
// so .js files report hits in actual copy strings, not in identifiers/comments.
function jsStringLiterals(src) {
  const out = [];
  const re = /(['"`])((?:\\.|(?!\1)[^\\])*)\1/g;
  let m;
  while ((m = re.exec(src)) !== null) out.push(m[2]);
  return out;
}

function tokensInJs(src) {
  // Also catch the obvious plain-text cases (rare in .js, harmless to check).
  return jsStringLiterals(src);
}

// ---------------------------------------------------------------------------
// Scan
// ---------------------------------------------------------------------------
function scanText(text) {
  const found = [];
  for (const p of PATTERNS) {
    p.re.lastIndex = 0;
    let m;
    while ((m = p.re.exec(text)) !== null) {
      found.push({ token: p.word, at: m.index });
      // Avoid infinite loops on zero-length matches (shouldn't happen with \b).
      if (m.index === p.re.lastIndex) p.re.lastIndex++;
    }
  }
  found.sort((a, b) => a.at - b.at);
  return found;
}

function collectFiles(targets) {
  const files = [];
  for (const t of targets) {
    const abs = path.resolve(t);
    const st = fs.statSync(abs);
    if (st.isFile()) {
      if (isCopyFile(abs)) files.push(abs);
    } else if (st.isDirectory()) {
      for (const entry of walk(abs)) {
        if (isCopyFile(entry)) files.push(entry);
      }
    }
  }
  return files;
}

function walk(dir) {
  const out = [];
  let entries;
  try {
    entries = fs.readdirSync(dir, { withFileTypes: true });
  } catch {
    return out;
  }
  for (const e of entries) {
    if (e.name === 'node_modules' || e.name.startsWith('.')) continue;
    const full = path.join(dir, e.name);
    if (e.isDirectory()) out.push(...walk(full));
    else if (e.isFile()) out.push(full);
  }
  return out;
}

function defaultTargets() {
  // Default scan root: the SHIPPED UI COPY directory, never the tooling.
  // The lint itself lives in <mini-app>/scripts/ and must not flag its own
  // source (tooling is not shipped copy). The SPA copy that reaches the
  // client lives under <mini-app>/pages/ — that is the T5 warmth-guard
  // surface this lint guards. Optional copy dirs (e.g. <mini-app>/copy/)
  // can be passed explicitly as args.
  const miniAppRoot = path.resolve(__dirname, '..');
  const pagesDir = path.join(miniAppRoot, 'pages');
  if (fs.existsSync(pagesDir)) return [pagesDir];
  return [miniAppRoot];
}

// ---------------------------------------------------------------------------
// Self-test (pure logic, no external files required)
// ---------------------------------------------------------------------------
function selftest() {
  const results = [];
  const T = (name, ok) => results.push([name, !!ok]);

  // Banned tokens are detected as whole words.
  T('detects "Submit"', scanText('Submit your answers').some((f) => f.token === 'submit'));
  T('detects "Required"', scanText('This field is Required.').some((f) => f.token === 'required'));
  T('detects "Error"', scanText('An Error occurred.').some((f) => f.token === 'error'));
  T('detects "Deadline"', scanText('The Deadline is soon.').some((f) => f.token === 'deadline'));
  T('detects "You must"', scanText('You must finish this.').some((f) => f.token === 'you must'));

  // No false positives on word-internal matches.
  T('no hit on "submission"', scanText('Your submission is saved.').length === 0);
  T('no hit on "Required_field_key"', scanText('required_field_key: "x"').length === 0);
  T('no hit on "error_message_variable"', scanText('var error_message = "";').length === 0);
  T('no hit on "deadlines" (plural)', scanText('There are no deadlines here.').length === 0);
  T('no hit on "you musty" (word boundary)', scanText('you musty room').length === 0);

  // Case-insensitivity.
  T('case-insensitive on "You Must"', scanText('You Must try.').some((f) => f.token === 'you must'));

  // Clean warm copy passes untouched.
  T('warm copy is clean', scanText('Beautiful — next.').length === 0);
  T('permission line is clean', scanText('There are no wrong answers.').length === 0);
  T('save line is clean', scanText('Save & come back later — your answers are safe.').length === 0);
  T('the five banned words all present in BANNED', BANNED.join('|') === 'submit|required|error|deadline|you must');

  // JS string-literal extraction respects escapes and quotes.
  T('js literals extracted', jsStringLiterals('var a = "Submit here"; var b = \'fine\';').join('|') === 'Submit here|fine');
  T('js literals handle escaped quote', jsStringLiterals('var a = "say \\"Submit\\" now";').join('|') === 'say \\"Submit\\" now');

  const pass = results.every((r) => r[1]);
  const lines = results.map((r) => (r[1] ? 'PASS' : 'FAIL') + '  ' + r[0]);
  if (typeof process !== 'undefined' && process.stdout) {
    lines.forEach((l) => process.stdout.write(l + '\n'));
    process.stdout.write((pass ? 'U08 banned-string lint self-test: PASS' : 'U08 banned-string lint self-test: FAIL') + '\n');
  }
  if (!pass && typeof process !== 'undefined') process.exitCode = 2;
  return pass;
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------
function main() {
  const argv = process.argv.slice(2);
  if (argv.indexOf('--selftest') !== -1 || argv.indexOf('--self-test') !== -1) {
    selftest();
    return;
  }

  const targets = argv.length ? argv : defaultTargets();
  let files;
  try {
    files = collectFiles(targets);
  } catch (err) {
    process.stderr.write('lint-banned-strings: cannot read targets: ' + err.message + '\n');
    process.exit(2);
    return;
  }

  let anyHit = false;
  for (const file of files) {
    let src;
    try {
      src = fs.readFileSync(file, 'utf8');
    } catch (err) {
      process.stderr.write('lint-banned-strings: cannot read ' + file + ': ' + err.message + '\n');
      process.exit(2);
      return;
    }
    const candidates = /\.js$/i.test(file) ? tokensInJs(src) : [src];
    for (const text of candidates) {
      for (const hit of scanText(text)) {
        anyHit = true;
        process.stdout.write(
          'BANNED("' + hit.token + '") ' + file + ' @' + hit.at +
          '  ...' + safeSnippet(text, hit.at) + '\n'
        );
      }
    }
  }

  if (anyHit) {
    process.stdout.write('U08 banned-string lint: FAIL (banned overwhelm words present in shipped copy)\n');
    process.exit(2);
  }
  process.stdout.write('U08 banned-string lint: PASS (' + files.length + ' file(s) scanned, 0 banned words)\n');
}

function safeSnippet(text, at) {
  const start = Math.max(0, at - 24);
  const end = Math.min(text.length, at + 40);
  return text.slice(start, end).replace(/\n/g, ' ').replace(/\r/g, '');
}

// Auto-run when invoked directly (node lint-banned-strings.js ...), but stay
// require-safe so other units can import the pure functions.
if (require.main === module) {
  main();
} else {
  module.exports = {
    BANNED,
    scanText,
    jsStringLiterals,
    tokensInJs,
    collectFiles,
    selftest
  };
}
