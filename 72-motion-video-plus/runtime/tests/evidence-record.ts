// Static evidence records (MG-043; fixes D-EVIDENCE-REWRITE).
//
// Before MG-043, the MG-005 and MG-006 runners rewrote their committed
// tests/evidence/mg005/measurements.json and mg006/measurements.json on
// every run, so any checkout that ran the suite came back dirty and the
// "record" said whatever the last run happened to produce. The pattern
// now: a runner writes its derived measurements to a scratch file and
// COMPARES them against the committed static record. Drift fails the
// run loudly. The runner never overwrites the record; adopting an
// intentional change is a reviewed act (copy the derived file over the
// record in a change that shows the diff), exactly like re-baselining a
// golden file.
//
// The comparison is strict about measurements and lenient only about
// run bookkeeping, via canonicalization applied to BOTH sides:
//
// - Volatile keys are dropped wherever they appear: generatedAt (the
//   runner's wall clock), probedAt (the probe's wall clock), and
//   lockTimestamp (when the shared runtime was provisioned; runtime
//   identity itself is compared through engineVersion and
//   runtimeLockId, which stay strict).
// - Absolute paths are canonicalized to a "<repo>" prefix. Records are
//   adopted from whichever checkout ran the suite (worker worktrees,
//   the coordinator clone, CI), and a path that differs only in the
//   checkout prefix is the same path. Canonicalization keys on the
//   repo's two top-level anchors (72-motion-video-plus/ and
//   shared-utils/) plus the current checkout's root, and applies to
//   whole whitespace-delimited tokens so paths embedded inside error
//   messages canonicalize the same way.
// - ISO-8601 UTC timestamps embedded in prose (a probe detail naming
//   when the runtime lock was recorded, say) normalize to "<ts>".
//   Wall-clock stamps are run bookkeeping wherever they appear; the
//   measurements in these records are frames, samples, pixels, and
//   hashes, never clock strings.
//
// Everything else (decoded measurements, frame counts, sizes, hashes,
// findings, categories) must match exactly; a real measurement change
// fails. Proven by tests/unit/test_evidence_record.py, which drives the
// compiled helper through its scenario CLI below.

import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname } from "node:path";

const VOLATILE_KEYS = new Set(["generatedAt", "probedAt", "lockTimestamp"]);
const PATH_MARKERS = ["/72-motion-video-plus/", "/shared-utils/"];
const MAX_DIFFS = 25;

const ISO_UTC_STAMP = /\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z/g;

function canonicalizeString(value: string, repoRoot: string): string {
  let out = value.split(repoRoot).join("<repo>");
  out = out.replace(/[^\s"']+/g, (token) => {
    for (const marker of PATH_MARKERS) {
      const at = token.indexOf(marker);
      if (at >= 0) return "<repo>" + token.slice(at);
    }
    return token;
  });
  out = out.replace(ISO_UTC_STAMP, "<ts>");
  return out;
}

export function canonicalizeEvidence(value: unknown, repoRoot: string): unknown {
  if (typeof value === "string") return canonicalizeString(value, repoRoot);
  if (Array.isArray(value)) return value.map((v) => canonicalizeEvidence(v, repoRoot));
  if (value !== null && typeof value === "object") {
    const src = value as Record<string, unknown>;
    const out: Record<string, unknown> = {};
    for (const key of Object.keys(src).sort()) {
      if (VOLATILE_KEYS.has(key)) continue;
      out[key] = canonicalizeEvidence(src[key], repoRoot);
    }
    return out;
  }
  return value;
}

function diffEvidence(a: unknown, b: unknown, path: string, diffs: string[]): void {
  if (diffs.length >= MAX_DIFFS) return;
  if (typeof a !== typeof b) {
    diffs.push(`${path}: type differs (record ${typeof a}, derived ${typeof b})`);
    return;
  }
  if (Array.isArray(a) || Array.isArray(b)) {
    if (!Array.isArray(a) || !Array.isArray(b)) {
      diffs.push(`${path}: record ${JSON.stringify(a)} vs derived ${JSON.stringify(b)}`);
      return;
    }
    if (a.length !== b.length) {
      diffs.push(`${path}: array length record ${a.length}, derived ${b.length}`);
      return;
    }
    for (let i = 0; i < a.length; i += 1) diffEvidence(a[i], b[i], `${path}[${i}]`, diffs);
    return;
  }
  if (a !== null && typeof a === "object") {
    const ao = a as Record<string, unknown>;
    const bo = b as Record<string, unknown>;
    const keys = [...new Set([...Object.keys(ao), ...Object.keys(bo)])].sort();
    for (const key of keys) {
      if (!(key in ao)) diffs.push(`${path}.${key}: only in derived`);
      else if (!(key in bo)) diffs.push(`${path}.${key}: only in record`);
      else diffEvidence(ao[key], bo[key], `${path}.${key}`, diffs);
      if (diffs.length >= MAX_DIFFS) return;
    }
    return;
  }
  if (a !== b) {
    diffs.push(`${path}: record ${JSON.stringify(a)} vs derived ${JSON.stringify(b)}`);
  }
}

export interface EvidenceRecordCheck {
  ok: boolean;
  diffs: string[];
  recordPath: string;
  scratchPath: string;
}

export function checkStaticEvidenceRecord(opts: {
  derived: Record<string, unknown>;
  recordPath: string;
  scratchPath: string;
  repoRoot: string;
}): EvidenceRecordCheck {
  mkdirSync(dirname(opts.scratchPath), { recursive: true });
  writeFileSync(opts.scratchPath, JSON.stringify(opts.derived, null, 2) + "\n", "utf8");
  if (!existsSync(opts.recordPath)) {
    return {
      ok: false,
      diffs: [
        `committed static record is missing: ${opts.recordPath} ` +
          `(adopt the derived record from ${opts.scratchPath} in a reviewed change to create it)`,
      ],
      recordPath: opts.recordPath,
      scratchPath: opts.scratchPath,
    };
  }
  const record = JSON.parse(readFileSync(opts.recordPath, "utf8")) as Record<string, unknown>;
  const diffs: string[] = [];
  diffEvidence(
    canonicalizeEvidence(record, opts.repoRoot),
    canonicalizeEvidence(opts.derived, opts.repoRoot),
    "$",
    diffs
  );
  return { ok: diffs.length === 0, diffs, recordPath: opts.recordPath, scratchPath: opts.scratchPath };
}

// Scenario CLI for tests/unit/test_evidence_record.py:
//   node dist/tests/evidence-record.js <scenario.json>
// where scenario.json is {record, derived, repoRoot}; prints
// {ok, diffs} as JSON and exits 0 (the comparison ran) regardless of
// the comparison outcome, so the Python test can assert on both.
if (require.main === module) {
  const arg = process.argv[2];
  if (!arg) {
    console.error("usage: evidence-record.js <scenario.json>");
    process.exit(2);
  }
  const scenario = JSON.parse(readFileSync(arg, "utf8")) as {
    record: Record<string, unknown>;
    derived: Record<string, unknown>;
    repoRoot: string;
  };
  const diffs: string[] = [];
  diffEvidence(
    canonicalizeEvidence(scenario.record, scenario.repoRoot),
    canonicalizeEvidence(scenario.derived, scenario.repoRoot),
    "$",
    diffs
  );
  console.log(JSON.stringify({ ok: diffs.length === 0, diffs }));
}
