// Corpus runner for the MG-007 contracts validation layer.
//
// Valid corpus: the four delivery-mode fixture jobs under
// tests/fixtures/modes must each validate with zero findings.
// Invalid corpus: mutations of the powerpoint_graphic fixture (plus two
// mode-fixture mutations) are staged into a temp dir per case, and the
// first error category, in the Section 16.9 family order, must match the
// expected category exactly. This mirrors the Python half of the contracts
// layer over the same shared corpus (Directive 16.6 rule 12).
//
// Fixtures root resolution: MOTION_FIXTURES_ROOT when set, otherwise
// ../../../../tests/fixtures relative to this compiled file, which lands
// on 72-motion-video-plus/tests/fixtures from runtime/dist/tests.
//
// Exit code 0 when every case passes, 1 otherwise.

import { cpSync, existsSync, mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { firstErrorCategory, validateJob, ErrorCategory } from "../src/validation/semantics";

function fixturesRoot(): string {
  const override = process.env.MOTION_FIXTURES_ROOT;
  if (override) return resolve(override);
  return resolve(__dirname, "..", "..", "..", "tests", "fixtures");
}

type Json = Record<string, unknown>;

function readJson(path: string): Json {
  return JSON.parse(readFileSync(path, "utf8")) as Json;
}

function writeJson(path: string, doc: Json): void {
  writeFileSync(path, JSON.stringify(doc, null, 2) + "\n", "utf8");
}

interface InvalidCase {
  name: string;
  /** Fixture mode directory to stage. */
  base: string;
  expected: ErrorCategory;
  mutate: (dir: string) => void;
}

function editManifest(dir: string, fn: (m: Json) => void): void {
  const p = join(dir, "manifest.json");
  const m = readJson(p);
  fn(m);
  writeJson(p, m);
}

function editTimeline(dir: string, fn: (t: Json) => void): void {
  const p = join(dir, "timeline.json");
  const t = readJson(p);
  fn(t);
  writeJson(p, t);
}

function editScene(dir: string, fn: (s: Json) => void): void {
  const p = join(dir, "scenes", "bar-01.json");
  const s = readJson(p);
  fn(s);
  writeJson(p, s);
}

function editDataset(dir: string, fn: (d: Json) => void): void {
  const p = join(dir, "data", "bars.json");
  const d = readJson(p);
  fn(d);
  writeJson(p, d);
}

const INVALID_CASES: InvalidCase[] = [
  {
    name: "unknown-manifest-key",
    base: "powerpoint_graphic",
    expected: "MG_SCHEMA_INVALID",
    mutate: (dir) =>
      editManifest(dir, (m) => {
        m["unexpected_extra_key"] = true;
      }),
  },
  {
    name: "canvas-1919x1080-off-aspect-and-odd",
    base: "powerpoint_graphic",
    expected: "MG_MODE_MISMATCH",
    mutate: (dir) =>
      editManifest(dir, (m) => {
        (m.canvas as Json).width = 1919;
      }),
  },
  {
    name: "canvas-width-zero",
    base: "powerpoint_graphic",
    expected: "MG_SCHEMA_INVALID",
    mutate: (dir) =>
      editManifest(dir, (m) => {
        (m.canvas as Json).width = 0;
      }),
  },
  {
    name: "duplicate-scene-id",
    base: "powerpoint_graphic",
    expected: "MG_SCHEMA_INVALID",
    mutate: (dir) =>
      editManifest(dir, (m) => {
        (m.scenes as Json[]).push({ id: "bar-01", spec: "scenes/bar-01.json" });
      }),
  },
  {
    name: "timeline-total-frames-181",
    base: "powerpoint_graphic",
    expected: "MG_TIMELINE_INVALID",
    mutate: (dir) =>
      editTimeline(dir, (t) => {
        t.total_frames = 181;
      }),
  },
  {
    name: "scene-motion-end-equals-start",
    base: "powerpoint_graphic",
    expected: "MG_TIMELINE_INVALID",
    mutate: (dir) =>
      editScene(dir, (s) => {
        const motion = s.motion as Json;
        motion.end_frame_exclusive = motion.start_frame;
      }),
  },
  {
    name: "unknown-component-c99",
    base: "powerpoint_graphic",
    expected: "MG_UNKNOWN_COMPONENT",
    mutate: (dir) =>
      editScene(dir, (s) => {
        s.component_id = "C99";
      }),
  },
  {
    name: "dataset-domain-reversed",
    base: "powerpoint_graphic",
    expected: "MG_SCHEMA_INVALID",
    mutate: (dir) =>
      editDataset(dir, (d) => {
        d.domain = [30, 0];
      }),
  },
  {
    name: "vsl-mobile-canvas-landscape",
    base: "vsl_mobile",
    expected: "MG_MODE_MISMATCH",
    mutate: (dir) =>
      editManifest(dir, (m) => {
        const canvas = m.canvas as Json;
        canvas.width = 1920;
        canvas.height = 1080;
      }),
  },
  {
    // Parity case 11 (integration, 2026-10-13): canonical schema pins VSL
    // audio.mode to "inherited"; the Python layer reports the same first
    // category for this mutation (Section 16.6 rule 12).
    name: "vsl-desktop-audio-mode-none",
    base: "vsl_desktop",
    expected: "MG_MODE_MISMATCH",
    mutate: (dir) =>
      editManifest(dir, (m) => {
        const audio = m.audio as Json;
        audio.mode = "none";
        audio.parent_audio_ref = null;
      }),
  },
  {
    name: "vsl-desktop-parent-null-handoff-removed",
    base: "vsl_desktop",
    expected: "MG_MODE_MISMATCH",
    mutate: (dir) => {
      editManifest(dir, (m) => {
        m.parent = null;
      });
      rmSync(join(dir, "parent-handoff.json"), { force: true });
    },
  },
];

function main(): number {
  const root = fixturesRoot();
  const modesRoot = join(root, "modes");
  if (!existsSync(modesRoot)) {
    console.error(`FAIL fixtures root not found: ${modesRoot}`);
    return 1;
  }

  let passed = 0;
  let failed = 0;
  const report = (ok: boolean, line: string): void => {
    if (ok) passed += 1;
    else failed += 1;
    console.log(`${ok ? "PASS" : "FAIL"} ${line}`);
  };

  // Valid corpus.
  const modeNames = readdirSync(modesRoot, { withFileTypes: true })
    .filter((e) => e.isDirectory())
    .map((e) => e.name)
    .sort();
  for (const modeName of modeNames) {
    const dir = join(modesRoot, modeName);
    const findings = validateJob(dir);
    if (findings.length === 0) {
      report(true, `valid/${modeName}: 0 findings`);
    } else {
      report(false, `valid/${modeName}: expected 0 findings, got ${findings.length}`);
      for (const f of findings) {
        console.log(`  finding ${f.category} ${f.path}: ${f.message}`);
      }
    }
  }

  // Invalid corpus.
  for (const c of INVALID_CASES) {
    const staging = mkdtempSync(join(tmpdir(), "motion-corpus-"));
    try {
      const staged = join(staging, c.base);
      cpSync(join(modesRoot, c.base), staged, { recursive: true });
      c.mutate(staged);
      const findings = validateJob(staged);
      const got = firstErrorCategory(findings);
      if (got === c.expected) {
        report(true, `invalid/${c.name}: first category ${got} as expected`);
      } else {
        report(
          false,
          `invalid/${c.name}: expected first category ${c.expected}, got ${got ?? "none"}`
        );
        for (const f of findings) {
          console.log(`  finding ${f.category} ${f.path}: ${f.message}`);
        }
      }
    } finally {
      rmSync(staging, { recursive: true, force: true });
    }
  }

  const total = passed + failed;
  console.log(`Corpus: ${passed}/${total} cases passed, ${failed} failed.`);
  return failed === 0 ? 0 : 1;
}

process.exit(main());
