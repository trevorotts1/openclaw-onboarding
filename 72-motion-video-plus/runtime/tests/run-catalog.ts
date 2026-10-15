// MG-018 catalog tests: registry inventory and entry-schema conformance,
// C05 schema derivation parity (the catalog input schema IS the canonical
// contracts scene $def, derived at load), the verdict-parity corpus run
// against BOTH shipped MG-007 validators (TypeScript validateJob and the
// Python motion_contracts.py CLI) and the catalog, dispatch refusal
// behavior, the governed custom-component path (end-to-end registration
// plus refusal of every partial registration), and the variation
// (anti-template) evidence. Contract tests only: no engine render and no
// provisioned runtime are required.

import {
  cpSync,
  mkdtempSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { spawnSync } from "node:child_process";
import {
  CatalogError,
  ComponentRegistry,
  OFFICIAL_COMPONENT_IDS,
  validateCatalogEntry,
  type ComponentEntry,
  type RegistrationBundle,
} from "../src/catalog";
import {
  loadContractsSchema,
  validateAgainstDef,
} from "../src/validation/validate";
import {
  firstErrorCategory,
  validateJob,
} from "../src/validation/semantics";

let passed = 0;
let failed = 0;

function report(ok: boolean, line: string, detail = ""): void {
  if (ok) {
    passed += 1;
    console.log(`PASS ${line}`);
  } else {
    failed += 1;
    console.log(`FAIL ${line}${detail ? ` :: ${detail}` : ""}`);
  }
}

function fixturesRoot(): string {
  return (
    process.env.MOTION_FIXTURES_ROOT ??
    resolve(__dirname, "../../../tests/fixtures")
  );
}

function skillRoot(): string {
  return resolve(__dirname, "../../..");
}

function canonical(value: unknown): string {
  if (Array.isArray(value)) {
    return `[${value.map(canonical).join(",")}]`;
  }
  if (value !== null && typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>).sort(
      ([a], [b]) => a.localeCompare(b)
    );
    return `{${entries
      .map(([key, item]) => `${JSON.stringify(key)}:${canonical(item)}`)
      .join(",")}}`;
  }
  return JSON.stringify(value) ?? "null";
}

function deepEqual(a: unknown, b: unknown): boolean {
  return canonical(a) === canonical(b);
}

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

const registry = ComponentRegistry.createDefault();

// ---------------------------------------------------------------------
// 1. Registry inventory: exactly the twelve Section 7.1 components.
// ---------------------------------------------------------------------
{
  const entries = registry.list();
  report(
    entries.length === 12,
    "registry holds exactly twelve entries",
    `got ${entries.length}`
  );
  report(
    deepEqual(
      entries.map((entry) => entry.componentId),
      OFFICIAL_COMPONENT_IDS
    ),
    "registry ids are exactly C01-C12 in order"
  );
  report(
    entries.every((entry) => entry.version === "1.0.0"),
    "every official entry is version 1.0.0"
  );
  const available = entries.filter(
    (entry) => entry.availability === "available"
  );
  // Coordinator reconciliation, maintained at each registration merge:
  // the registered world grows as owning items land their bundles.
  // MG-018 shipped C05 only; MG-017 registered C04 and C09; MG-016
  // registered C06, C07, and C08 (bundles composed into the default
  // registry by the coordinator at the MG-016 merge); MG-044
  // registered C01, C02, and C03 (their bundles, c01.ts to c03.ts).
  report(
    available.length === 9 &&
      available.map((entry) => entry.componentId).join(",") === "C01,C02,C03,C04,C05,C06,C07,C08,C09",
    "registered components are available for production dispatch",
    `available: ${available.map((entry) => entry.componentId).join(",")}`
  );
  const unavailable = entries.filter(
    (entry) => entry.availability === "unavailable"
  );
  report(
    unavailable.length === 3 &&
      unavailable.every(
        (entry) =>
          entry.inputSchema === null &&
          entry.proofContract === null &&
          entry.tests.length === 0 &&
          typeof entry.unavailableReason === "string" &&
          entry.unavailableReason.length > 0
      ),
    "three entries are unavailable with reasons and no partial bundle"
  );
  report(
    entries.every((entry) => validateCatalogEntry(entry).length === 0),
    "every default entry satisfies CATALOG_ENTRY_SCHEMA"
  );
  report(
    entries.every(
      (entry) =>
        entry.examples.length >= 1 &&
        entry.variation.composition.length > 0 &&
        entry.variation.framing.length > 0 &&
        entry.variation.typeTreatment.length > 0 &&
        entry.variation.pacing.length > 0 &&
        entry.typographyRoles.length >= 1 &&
        entry.layoutVariants.length >= 1
    ),
    "every entry carries examples, variation descriptors, typography roles, and layout variants"
  );
}

// ---------------------------------------------------------------------
// 2. C05: the input schema is the canonical scene $def, derived.
// ---------------------------------------------------------------------
{
  const c05 = registry.get("C05", "1.0.0") as ComponentEntry;
  const contracts = loadContractsSchema() as unknown as {
    $defs: Record<string, unknown>;
  };
  report(
    deepEqual(c05.inputSchema, contracts.$defs.scene),
    "C05 catalog input schema deep-equals contracts-v2 $defs/scene"
  );
  report(
    (c05.inputSchema as { additionalProperties?: unknown })
      .additionalProperties === false,
    "C05 input schema is closed (additionalProperties: false, no escape hatch)"
  );
  const fixtureScene = JSON.parse(
    readFileSync(
      join(fixturesRoot(), "modes/powerpoint_graphic/scenes/bar-01.json"),
      "utf8"
    )
  );
  report(
    deepEqual(c05.examples[0].scene, fixtureScene),
    "C05 example scene deep-equals the shipped fixture scene bar-01"
  );
  report(
    c05.proofContract !== null &&
      deepEqual(c05.proofContract.selectors[0].proofFrames, [
        0, 15, 45, 75, 150, 179,
      ]),
    "C05 proof selectors record the Section 17.2 proof frames"
  );
}

// ---------------------------------------------------------------------
// 3. Dispatch gate: available resolves; unavailable and unknown refuse.
// ---------------------------------------------------------------------
{
  report(
    registry.requireDispatchable("C05", "1.0.0").componentId === "C05",
    "requireDispatchable resolves C05 1.0.0"
  );
  try {
    registry.requireDispatchable("C10", "1.0.0");
    report(false, "requireDispatchable refuses unavailable C10");
  } catch (error) {
    report(
      error instanceof CatalogError &&
        error.category === "MG_CAPABILITY_UNSUPPORTED" &&
        error.exitClass === 3,
      "requireDispatchable refuses unavailable C10 with MG_CAPABILITY_UNSUPPORTED (exit 3)",
      String(error)
    );
  }
  try {
    registry.requireDispatchable("C99", "1.0.0");
    report(false, "requireDispatchable refuses unknown C99");
  } catch (error) {
    report(
      error instanceof CatalogError &&
        error.category === "MG_UNKNOWN_COMPONENT" &&
        error.exitClass === 2,
      "requireDispatchable refuses unknown C99 with MG_UNKNOWN_COMPONENT (exit 2)",
      String(error)
    );
  }
  try {
    registry.requireDispatchable("C05", "2.0.0");
    report(false, "requireDispatchable refuses unregistered C05 version");
  } catch (error) {
    report(
      error instanceof CatalogError &&
        error.category === "MG_SCHEMA_INVALID" &&
        error.exitClass === 2,
      "requireDispatchable refuses C05 2.0.0 with MG_SCHEMA_INVALID",
      String(error)
    );
  }
}

// ---------------------------------------------------------------------
// 3b. MG-044 image components: C01, C02, C03 dispatch and validate.
// ---------------------------------------------------------------------
{
  for (const id of ["C01", "C02", "C03"]) {
    report(
      registry.requireDispatchable(id, "1.0.0").componentId === id,
      `requireDispatchable resolves ${id} 1.0.0 (MG-044)`
    );
  }
  const fixtureScenes: Record<string, string> = {
    C01: "image-components/c01-reveal.scene.json",
    C02: "image-components/c02-detail.scene.json",
    C03: "image-components/c03-compare.scene.json",
  };
  for (const [id, fixturePath] of Object.entries(fixtureScenes)) {
    const entry = registry.get(id, "1.0.0") as ComponentEntry;
    const scene = JSON.parse(
      readFileSync(join(fixturesRoot(), fixturePath), "utf8")
    ) as Record<string, unknown>;
    report(
      deepEqual(entry.examples[0].scene, scene),
      `${id} example scene deep-equals its shipped fixture scene`
    );
    const result = registry.validateSceneProps(scene);
    report(
      result.valid && result.entry?.componentId === id,
      `${id} fixture scene validates against its registered closed schema`,
      result.findings.map((finding) => finding.message).join("; ")
    );
    const extraProp = clone(scene);
    extraProp.surprise = true;
    const extraResult = registry.validateSceneProps(extraProp);
    report(
      !extraResult.valid &&
        extraResult.firstErrorCategory === "MG_SCHEMA_INVALID",
      `${id} rejects an undeclared prop with MG_SCHEMA_INVALID`
    );
  }
  const c01 = registry.get("C01", "1.0.0") as ComponentEntry;
  for (const example of c01.examples) {
    const result = registry.validateSceneProps(example.scene ?? {});
    report(
      result.valid,
      `C01 example ${example.id} validates against the registered anyOf schema`,
      result.findings.map((finding) => finding.message).join("; ")
    );
  }
  const wrongKind = clone(
    JSON.parse(
      readFileSync(
        join(fixturesRoot(), "image-components/c03-compare.scene.json"),
        "utf8"
      )
    )
  ) as Record<string, unknown>;
  (wrongKind.motion as Record<string, unknown>).kind = "crossfade";
  const wrongKindResult = registry.validateSceneProps(wrongKind);
  report(
    !wrongKindResult.valid &&
      wrongKindResult.firstErrorCategory === "MG_SCHEMA_INVALID",
    "C03 rejects an unregistered motion kind with MG_SCHEMA_INVALID"
  );
  const badInterval = clone(
    JSON.parse(
      readFileSync(
        join(fixturesRoot(), "image-components/c01-reveal.scene.json"),
        "utf8"
      )
    )
  ) as Record<string, unknown>;
  (badInterval.motion as Record<string, unknown>).end_frame_exclusive = 200;
  (badInterval.motion as Record<string, unknown>).hold_to_frame_exclusive = 240;
  const badIntervalResult = registry.validateSceneProps(badInterval);
  report(
    !badIntervalResult.valid &&
      badIntervalResult.firstErrorCategory === "MG_TIMELINE_INVALID",
    "C01 rejects a hold beyond the scene duration with MG_TIMELINE_INVALID"
  );
}

// ---------------------------------------------------------------------
// 4. Verdict-parity corpus: catalog vs both shipped MG-007 validators.
// ---------------------------------------------------------------------
interface ParityCase {
  name: string;
  scene: Record<string, unknown>;
  expected: {
    accept: boolean;
    shippedCategory: string | null;
    catalogCategory: string | null;
  };
}

{
  const corpus = JSON.parse(
    readFileSync(join(fixturesRoot(), "catalog/parity-corpus.json"), "utf8")
  ) as { cases: ParityCase[] };
  const pythonScript = join(skillRoot(), "scripts/motion_contracts.py");
  const fixtureJob = join(fixturesRoot(), "modes/powerpoint_graphic");
  console.log("C05 verdict-parity table (catalog vs shipped TS vs shipped Python):");
  console.log(
    "case | verdict (all three) | shipped category | catalog category"
  );
  for (const testCase of corpus.cases) {
    const staging = mkdtempSync(join(tmpdir(), "mg018-parity-"));
    try {
      const staged = join(staging, "job");
      cpSync(fixtureJob, staged, { recursive: true });
      writeFileSync(
        join(staged, "scenes/bar-01.json"),
        JSON.stringify(testCase.scene, null, 2) + "\n"
      );
      const tsFindings = validateJob(staged);
      const tsAccept = tsFindings.length === 0;
      const tsCategory = firstErrorCategory(tsFindings);

      let pyAccept: boolean | null = null;
      let pyCategory: string | null = null;
      let pyNote = "";
      const py = spawnSync(
        "python3",
        [pythonScript, "validate", staged],
        { encoding: "utf8" }
      );
      if (py.error) {
        pyNote = `python unavailable (${py.error.message})`;
      } else {
        try {
          const parsed = JSON.parse(py.stdout) as {
            valid: boolean;
            first_error_category: string | null;
          };
          pyAccept = parsed.valid;
          pyCategory = parsed.first_error_category;
        } catch {
          pyNote = "python output unparseable";
        }
      }

      const catalog = registry.validateSceneProps(testCase.scene);
      const verdictsAgree =
        catalog.valid === testCase.expected.accept &&
        tsAccept === testCase.expected.accept &&
        (pyAccept === null || pyAccept === testCase.expected.accept);
      const categoriesAgree =
        tsCategory === testCase.expected.shippedCategory &&
        catalog.firstErrorCategory === testCase.expected.catalogCategory &&
        (pyAccept === null || pyCategory === testCase.expected.shippedCategory);
      console.log(
        `${testCase.name} | ${testCase.expected.accept ? "ACCEPT" : "reject"} | ` +
          `${testCase.expected.shippedCategory ?? "-"} | ` +
          `${testCase.expected.catalogCategory ?? "-"}${pyNote ? ` | NOTE ${pyNote}` : ""}`
      );
      report(
        verdictsAgree && categoriesAgree,
        `parity case ${testCase.name}`,
        `catalog=${catalog.valid}/${catalog.firstErrorCategory} ts=${tsAccept}/${tsCategory} py=${pyAccept}/${pyCategory}`
      );
    } finally {
      rmSync(staging, { recursive: true, force: true });
    }
  }
}

// ---------------------------------------------------------------------
// 5. Invalid props fail early through the throwing API as well.
// ---------------------------------------------------------------------
{
  const scene = clone(
    JSON.parse(
      readFileSync(
        join(fixturesRoot(), "modes/powerpoint_graphic/scenes/bar-01.json"),
        "utf8"
      )
    )
  ) as Record<string, unknown>;
  (scene.copy as Record<string, unknown>).headline = "";
  try {
    registry.assertSceneProps(scene);
    report(false, "assertSceneProps rejects an empty C05 headline");
  } catch (error) {
    report(
      error instanceof CatalogError &&
        error.category === "MG_SCHEMA_INVALID" &&
        error.exitClass === 2,
      "assertSceneProps rejects an empty C05 headline with MG_SCHEMA_INVALID before any render work",
      String(error)
    );
  }
}

// ---------------------------------------------------------------------
// 6. Governed custom-component path: register end to end, refuse parts.
// ---------------------------------------------------------------------
{
  const bundle = JSON.parse(
    readFileSync(join(fixturesRoot(), "catalog/custom-bundle.json"), "utf8")
  ) as RegistrationBundle;
  const custom = new ComponentRegistry([]);
  const accepted = custom.register(clone(bundle));
  report(
    accepted.componentId === "X01" && accepted.availability === "available",
    "custom registration accepts a complete bundle (X01)"
  );
  const exampleScene = (bundle.entry.examples[0].scene ??
    {}) as Record<string, unknown>;
  report(
    custom.validateSceneProps(exampleScene).valid,
    "registered custom component validates its example scene"
  );
  const extraProp = clone(exampleScene);
  extraProp.surprise = true;
  const extraResult = custom.validateSceneProps(extraProp);
  report(
    !extraResult.valid &&
      extraResult.firstErrorCategory === "MG_SCHEMA_INVALID",
    "custom component rejects undeclared props with MG_SCHEMA_INVALID"
  );
  report(
    custom.requireDispatchable("X01", "0.1.0").componentId === "X01",
    "registered custom component is dispatchable"
  );
  report(
    registry.get("X01", "0.1.0") === null,
    "custom registration does not leak into the default registry"
  );

  const refusals: { name: string; mutate: (b: RegistrationBundle) => void }[] =
    [
      {
        name: "missing input schema",
        mutate: (b) => {
          b.entry.inputSchema = null;
        },
      },
      {
        name: "input schema with additionalProperties: true",
        mutate: (b) => {
          (b.entry.inputSchema as Record<string, unknown>)[
            "additionalProperties"
          ] = true;
        },
      },
      {
        name: "input schema not declared closed",
        mutate: (b) => {
          delete (b.entry.inputSchema as Record<string, unknown>)[
            "additionalProperties"
          ];
        },
      },
      {
        name: "missing proof contract",
        mutate: (b) => {
          b.entry.proofContract = null;
        },
      },
      {
        name: "proof contract with no selectors",
        mutate: (b) => {
          (b.entry.proofContract as { selectors: unknown[] }).selectors = [];
        },
      },
      {
        name: "missing tests",
        mutate: (b) => {
          b.entry.tests = [];
        },
      },
      {
        name: "duplicate test ids",
        mutate: (b) => {
          b.entry.tests = [b.entry.tests[0], b.entry.tests[0]];
        },
      },
      {
        name: "missing review attestation",
        mutate: (b) => {
          delete (b as Partial<RegistrationBundle>).reviewAttestation;
        },
      },
      {
        name: "review attestation not approved",
        mutate: (b) => {
          (b.reviewAttestation as { decision: string }).decision = "rejected";
        },
      },
      {
        name: "official Section 7 id via the custom path",
        mutate: (b) => {
          b.entry.componentId = "C07";
        },
      },
    ];
  for (const refusal of refusals) {
    const mutated = clone(bundle);
    refusal.mutate(mutated);
    try {
      new ComponentRegistry([]).register(mutated);
      report(false, `registration refusal: ${refusal.name}`);
    } catch (error) {
      report(
        error instanceof CatalogError &&
          error.category === "MG_SCHEMA_INVALID",
        `registration refusal: ${refusal.name}`,
        String(error)
      );
    }
  }
  try {
    custom.register(clone(bundle));
    report(false, "registration refusal: duplicate component id");
  } catch (error) {
    report(
      error instanceof CatalogError &&
        error.category === "MG_SCHEMA_INVALID",
      "registration refusal: duplicate component id",
      String(error)
    );
  }
}

// ---------------------------------------------------------------------
// 7. Variation evidence: same primitive, different brand inputs.
// ---------------------------------------------------------------------
{
  const c05 = registry.get("C05", "1.0.0") as ComponentEntry;
  const fixtureDesign = JSON.parse(
    readFileSync(
      join(fixturesRoot(), "modes/powerpoint_graphic/design.json"),
      "utf8"
    )
  ) as Record<string, unknown>;
  const brandB = JSON.parse(
    readFileSync(join(fixturesRoot(), "catalog/brand-b-design.json"), "utf8")
  ) as Record<string, unknown>;
  report(
    validateAgainstDef("design", fixtureDesign).length === 0 &&
      validateAgainstDef("design", brandB).length === 0,
    "both variation designs satisfy the canonical design $def"
  );
  const aLandscape = registry.describeLayout(c05, fixtureDesign, "landscape");
  const bLandscape = registry.describeLayout(c05, brandB, "landscape");
  const aPortrait = registry.describeLayout(c05, fixtureDesign, "portrait");
  report(
    !deepEqual(aLandscape, bLandscape),
    "same primitive (C05) with different brand designs yields different layout descriptors"
  );
  report(
    aLandscape.palette.accent !== bLandscape.palette.accent &&
      (aLandscape.geometry.plot as { width: number }).width !==
        (bLandscape.geometry.plot as { width: number }).width &&
      aLandscape.typeScalePx.headline !== bLandscape.typeScalePx.headline,
    "descriptors differ in palette, plot geometry, and type scale",
    `a=${canonical(aLandscape.palette)}/${canonical(aLandscape.geometry.plot)} b=${canonical(bLandscape.palette)}/${canonical(bLandscape.geometry.plot)}`
  );
  report(
    deepEqual(
      aLandscape.geometry,
      (fixtureDesign.layouts as Record<string, unknown>).landscape
    ) &&
      aLandscape.typeScalePx.headline ===
        (
          (fixtureDesign.layouts as Record<string, unknown>)
            .landscape as { headline_px: number }
        ).headline_px,
    "layout descriptor is computed from the design record, not hardcoded"
  );
  report(
    !deepEqual(aLandscape, aPortrait),
    "landscape and portrait descriptors for one design differ (recomposition, not crop)"
  );
}

// ---------------------------------------------------------------------
// 8. Entry-schema teeth: malformed entries are refused.
// ---------------------------------------------------------------------
{
  const c05 = registry.get("C05", "1.0.0") as ComponentEntry;
  const broken = clone(c05) as unknown as Record<string, unknown>;
  broken.inputSchema = null;
  report(
    validateCatalogEntry(broken).length > 0,
    "an available entry with a null input schema fails CATALOG_ENTRY_SCHEMA"
  );
  const noVariation = clone(c05) as unknown as Record<string, unknown>;
  delete noVariation.variation;
  report(
    validateCatalogEntry(noVariation).length > 0,
    "an entry without variation descriptors fails CATALOG_ENTRY_SCHEMA"
  );
}

console.log(`Catalog: ${passed}/${passed + failed} checks passed, ${failed} failed.`);
process.exit(failed === 0 ? 0 : 1);
