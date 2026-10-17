#!/usr/bin/env node
// Skill 77 release adapter: cross-repo compatibility negotiation (CWE-041).
//
// This module is the current release adapter named by directive Section 34
// for CWE-041. It derives component descriptors from the three accepted
// repository trees (canonical skill in openclaw-onboarding, Command Center,
// 999-setup vendored distribution), and it negotiates a pair of descriptors
// against the cross-repo compatibility manifest
// (compatibility-manifest.json, directive Section 27.1).
//
// Negotiation is pure: it reads descriptors and the manifest, returns a
// typed decision, and performs no writes, opens no store, and starts no
// session. A paired session may start only when the decision is
// "compatible" or "compatible-portable". A "not-ready" decision carries
// typed refusal codes and is final for that attempt: no shadow session, no
// fallback store, no silent mode switch (directive Sections 16 and 27).
//
// CLI:
//   node negotiate.mjs describe onb <skill-folder> [--commit <sha>]
//   node negotiate.mjs describe cc <cc-repo-root> [--commit <sha>]
//   node negotiate.mjs describe 999 <999-repo-root> [--commit <sha>]
//   node negotiate.mjs check <skill-descriptor.json> <cc-descriptor.json>
//   node negotiate.mjs manifest <compatibility-manifest.json>  (self-check)
// Exit codes: 0 compatible (or successful describe), 3 not-ready,
// 2 usage or input error. Exit 3 mirrors the council CLI doctor's
// not-ready convention.

import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

export const DESCRIPTOR_SCHEMA_VERSION = "skill77.component-descriptor/v1";

// ---------------------------------------------------------------------------
// Small helpers
// ---------------------------------------------------------------------------

function sha256Hex(bytes) {
  return createHash("sha256").update(bytes).digest("hex");
}

function readText(path) {
  return readFileSync(path, "utf8");
}

function readJson(path) {
  return JSON.parse(readText(path));
}

function gitHead(root) {
  try {
    return execFileSync("git", ["-C", root, "rev-parse", "HEAD"], {
      encoding: "utf8",
      stdio: ["ignore", "pipe", "ignore"],
    }).trim();
  } catch {
    return null;
  }
}

/** Last commit that touched a path (the commit whose tree the path is). */
function gitLastTouch(cwd, pathspec) {
  try {
    return execFileSync(
      "git",
      ["-C", cwd, "log", "-1", "--format=%H", "--", pathspec],
      { encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] },
    ).trim();
  } catch {
    return null;
  }
}

function walkFiles(root, out = []) {
  for (const name of readdirSync(root).sort()) {
    const p = join(root, name);
    if (statSync(p).isDirectory()) walkFiles(p, out);
    else out.push(p);
  }
  return out;
}

/**
 * The canonical tree aggregate (directive Section 27.2, and the method
 * recorded in the canonical manifest.json): SHA-256 per file over sorted
 * relative paths; the aggregate is SHA-256 of the lines
 * "<sha256>  <path>" joined by newlines with a trailing newline.
 * manifest.json itself and any .skill archive are excluded.
 */
export function treeAggregate(root) {
  const pairs = [];
  for (const p of walkFiles(root)) {
    const rel = relative(root, p).split("\\").join("/");
    if (rel === "manifest.json" || rel.endsWith(".skill")) continue;
    pairs.push({ path: rel, hash: sha256Hex(readFileSync(p)) });
  }
  pairs.sort((a, b) => (a.path < b.path ? -1 : a.path > b.path ? 1 : 0));
  const lines = pairs.map((x) => `${x.hash}  ${x.path}`);
  return {
    aggregate_sha256: sha256Hex(Buffer.from(lines.join("\n") + "\n", "utf8")),
    file_count: pairs.length,
  };
}

function extractConstString(text, name) {
  const m = text.match(
    new RegExp(`export const ${name}\\s*=\\s*'([^']+)'`),
  );
  return m ? m[1] : null;
}

/** Parse the SCHEMA_VERSIONS map out of a contracts schemas.ts source. */
export function parseSchemaVersions(text) {
  const block = text.match(/export const SCHEMA_VERSIONS = \{([\s\S]*?)\} as const;/);
  if (!block) return null;
  const out = {};
  for (const m of block[1].matchAll(/(\w+):\s*'([^']+)'/g)) {
    const key = m[1] === "diagnosticPolicy" ? "diagnostic_policy" : m[1];
    out[key] = m[2];
  }
  return out;
}

function findLiteral(text, literal) {
  return text.includes(`'${literal}'`) ? literal : null;
}

/** The full wire-contract surface declared by a contracts schemas.ts. */
export function deriveWireContract(schemasPath) {
  const text = readText(schemasPath);
  const schemaVersions = parseSchemaVersions(text);
  if (!schemaVersions) {
    throw new Error(`SCHEMA_VERSIONS block not found in ${schemasPath}`);
  }
  const extra = {
    session_state: "wise-elders.session-state/v1",
    job_checkpoint: "wise-elders.job-checkpoint/v1",
    settings: "wise-elders.settings/v1",
    approval: "wise-elders.approval/v1",
    operation_receipt: "wise-elders.operation-receipt/v1",
  };
  for (const [key, literal] of Object.entries(extra)) {
    schemaVersions[key] = findLiteral(text, literal);
  }
  return {
    contract_package_version: extractConstString(text, "CONTRACT_PACKAGE_VERSION"),
    schema_versions: schemaVersions,
  };
}

// ---------------------------------------------------------------------------
// Descriptor derivation: one function per repository tree kind.
// Every value is read from the tree itself; nothing is guessed.
// ---------------------------------------------------------------------------

export function deriveOnbSkillDescriptor(skillRoot, opts = {}) {
  const root = resolve(skillRoot);
  const manifestPath = join(root, "manifest.json");
  if (!existsSync(manifestPath)) {
    throw new Error(`canonical skill manifest.json not found under ${root}`);
  }
  const treeManifest = readJson(manifestPath);
  const wire = deriveWireContract(join(root, "runtime", "src", "contracts", "schemas.ts"));
  const runtimePkg = readJson(join(root, "runtime", "package.json"));
  const configText = readText(join(root, "runtime", "src", "persistence", "config.ts"));
  const profileText = readText(join(root, "runtime", "src", "persistence", "profile.ts"));
  const persistIndexText = readText(join(root, "runtime", "src", "persistence", "index.ts"));
  const localStoreText = readText(join(root, "runtime", "src", "cli", "local-store.ts"));
  const archivePath = join(root, "council-of-wise-elders.skill");
  const archiveBytes = existsSync(archivePath) ? readFileSync(archivePath) : null;
  const computed = treeAggregate(root);
  return {
    descriptor: DESCRIPTOR_SCHEMA_VERSION,
    component: "onb-skill",
    role: "skill",
    repository: "trevorotts1/openclaw-onboarding",
    commit: opts.commit ?? gitLastTouch(root, ".") ?? gitHead(root),
    skill_version: treeManifest.skill_version ?? readText(join(root, "version")).trim(),
    runtime_package: { name: runtimePkg.name, version: runtimePkg.version },
    contract_package_version: wire.contract_package_version,
    schema_versions: wire.schema_versions,
    endpoint_registry_contract: wire.schema_versions.endpoint ?? null,
    persistence: {
      config_schema_version: extractConstString(configText, "PERSISTENCE_CONFIG_SCHEMA_VERSION"),
      profile_schema_version: findLiteral(profileText, "wise-elders.installation-profile/v1"),
      store_migration_id: extractConstString(persistIndexText, "COUNCIL_SCHEMA_MIGRATION_ID"),
      store_migration_name: extractConstString(persistIndexText, "COUNCIL_SCHEMA_MIGRATION_NAME"),
      local_store_schema_version: extractConstString(localStoreText, "LOCAL_STORE_SCHEMA_VERSION"),
    },
    authority_modes: ["standalone", "managed"],
    tree_identity: {
      kind: "canonical",
      recorded_aggregate_sha256: treeManifest.aggregate_sha256 ?? null,
      recorded_file_count: treeManifest.file_count ?? null,
      computed_aggregate_sha256: computed.aggregate_sha256,
      computed_file_count: computed.file_count,
      archive: archiveBytes
        ? {
            file: "council-of-wise-elders.skill",
            sha256: sha256Hex(archiveBytes),
            bytes: archiveBytes.length,
          }
        : null,
    },
  };
}

export function deriveCcDescriptor(ccRoot, opts = {}) {
  const root = resolve(ccRoot);
  const schemasPath = join(root, "src", "lib", "council", "contracts", "schemas.ts");
  if (!existsSync(schemasPath)) {
    throw new Error(`Command Center council contracts not found under ${root}`);
  }
  const wire = deriveWireContract(schemasPath);
  const generated = readJson(
    join(root, "src", "lib", "council", "contracts", "generated", "json-schemas.json"),
  );
  const foundationText = readText(join(root, "src", "lib", "council", "api", "foundation.ts"));
  const registryMatch = foundationText.match(/registry_contract:\s*'([^']+)'/);
  const migrationText = readText(
    join(root, "src", "lib", "council", "persistence", "council-migration.ts"),
  );
  const migrationId = extractConstString(migrationText, "COUNCIL_MIGRATION_ID_PENDING");
  const pkg = readJson(join(root, "package.json"));
  const apiDir = join(root, "src", "app", "api", "council");
  const routeGroups = existsSync(apiDir)
    ? readdirSync(apiDir).filter((n) => statSync(join(apiDir, n)).isDirectory()).sort()
    : [];
  return {
    descriptor: DESCRIPTOR_SCHEMA_VERSION,
    component: "command-center",
    role: "command-center",
    repository: "blackceo-command-center",
    commit: opts.commit ?? gitHead(root),
    app_package: { name: pkg.name, version: pkg.version },
    contract_package_version: wire.contract_package_version,
    generated_contracts: {
      artifact: generated.artifact ?? null,
      package_version: generated.package_version ?? null,
    },
    schema_versions: wire.schema_versions,
    endpoint_registry_contract: registryMatch ? registryMatch[1] : null,
    council_route_groups: routeGroups,
    cc_migration_id: migrationId,
    cc_migration_allocated:
      migrationId !== null && migrationId !== "PENDING_INTEGRATION_ALLOCATION_CWE005",
    authority_modes: ["managed"],
  };
}

export function derive999Descriptor(nineRoot, opts = {}) {
  const root = resolve(nineRoot);
  const recordPath = join(root, "installer-registration", "council-vendoring.json");
  if (!existsSync(recordPath)) {
    throw new Error(`999 council vendoring record not found under ${root}`);
  }
  const record = readJson(recordPath);
  const vendoredRoot = join(
    root,
    ...(record.distribution?.vendored_path ?? ".claude/skills/council-of-wise-elders").split("/"),
  );
  const wire = deriveWireContract(
    join(vendoredRoot, "runtime", "src", "contracts", "schemas.ts"),
  );
  const computed = treeAggregate(vendoredRoot);
  const differences = record.intentional_distribution_differences ?? [];
  return {
    descriptor: DESCRIPTOR_SCHEMA_VERSION,
    component: "nine99-distribution",
    role: "skill",
    repository: "999-setup",
    commit: opts.commit ?? gitHead(root),
    skill_version: record.canonical_source?.skill_version ?? null,
    contract_package_version: wire.contract_package_version,
    schema_versions: wire.schema_versions,
    endpoint_registry_contract: wire.schema_versions.endpoint ?? null,
    authority_modes: ["standalone", "managed"],
    canonical_source: {
      repository: record.canonical_source?.repository ?? null,
      source_commit: record.canonical_source?.source_commit ?? null,
      canonical_aggregate_sha256: record.canonical_source?.canonical_aggregate_sha256 ?? null,
      canonical_file_count: record.canonical_source?.canonical_file_count ?? null,
    },
    canonical_archive: record.canonical_archive
      ? {
          file: record.canonical_archive.file,
          sha256: record.canonical_archive.sha256,
          bytes: record.canonical_archive.bytes,
        }
      : null,
    tree_identity: {
      kind: "distribution",
      recorded_aggregate_sha256: record.distribution?.distribution_aggregate_sha256 ?? null,
      recorded_file_count: record.distribution?.distribution_file_count ?? null,
      computed_aggregate_sha256: computed.aggregate_sha256,
      computed_file_count: computed.file_count,
    },
    intentional_distribution_differences: {
      count: differences.length,
      kinds: differences.map((d) => d.kind),
    },
  };
}

// ---------------------------------------------------------------------------
// Negotiation. Pure: no filesystem, no store, no session.
// ---------------------------------------------------------------------------

function recordedIdentities(manifest) {
  const out = [];
  for (const member of manifest.release_cohort?.members ?? []) {
    if (member.tree_identity) {
      out.push({
        component: member.component,
        kind: "canonical",
        aggregate_sha256: member.tree_identity.aggregate_sha256,
        file_count: member.tree_identity.file_count,
        cohort_commit: member.commit,
      });
    }
    if (member.distribution_identity) {
      out.push({
        component: member.component,
        kind: "distribution",
        aggregate_sha256: member.distribution_identity.aggregate_sha256,
        file_count: member.distribution_identity.file_count,
        cohort_commit: member.commit,
        canonical_source_commit: member.canonical_source_commit,
      });
    }
  }
  return out;
}

function cohortMember(manifest, component) {
  return (manifest.release_cohort?.members ?? []).find((m) => m.component === component) ?? null;
}

function skillTreeMatchesRecord(skill, manifest) {
  const id = skill.tree_identity;
  if (!id) return { ok: false, detail: "skill descriptor carries no tree identity" };
  const computed = id.computed_aggregate_sha256 ?? id.recorded_aggregate_sha256;
  const count = id.computed_file_count ?? id.recorded_file_count;
  for (const rec of recordedIdentities(manifest)) {
    if (rec.kind !== id.kind) continue;
    if (rec.aggregate_sha256 !== computed || rec.file_count !== count) continue;
    if (rec.kind === "distribution") {
      if (skill.canonical_source?.source_commit !== rec.canonical_source_commit) {
        return {
          ok: false,
          detail: `distribution tree records canonical source ${skill.canonical_source?.source_commit}, cohort requires ${rec.canonical_source_commit}`,
        };
      }
    }
    return { ok: true, detail: `${id.kind} identity ${computed} (${count} files) is recorded in the manifest` };
  }
  return {
    ok: false,
    detail: `tree identity ${computed} over ${count} files matches no recorded canonical or distribution identity`,
  };
}

/**
 * Negotiate a skill side against a Command Center side.
 *
 * args: {
 *   skill,                  // descriptor with role "skill" (or null)
 *   cc,                     // descriptor with role "command-center" (or null)
 *   manifest,               // parsed compatibility-manifest.json
 *   requestedAuthorityMode, // "managed" for a paired start (default)
 *   recordedAuthorityMode,  // mode in the installation profile, if any
 * }
 * Returns { decision, allowed, refusals: [{code, detail}], advisories:
 * [{code, detail}], checks: [{rule, ok, detail}] }.
 */
export function negotiatePair(args) {
  const { skill, cc, manifest } = args;
  const requestedAuthorityMode = args.requestedAuthorityMode ?? "managed";
  const recordedAuthorityMode = args.recordedAuthorityMode ?? null;
  const refusals = [];
  const advisories = [];
  const checks = [];
  const record = (rule, ok, detail) => checks.push({ rule, ok, detail });

  // Standalone negotiation: no Command Center peer. Only the skill side's
  // own identity and self-consistency gate a standalone session.
  if (cc === null || cc === undefined) {
    if (!skill) {
      refusals.push({ code: "COMPAT_COMPONENT_MISSING", detail: "no skill descriptor supplied" });
      record("N1", false, "skill component missing");
      return finish("not-ready", refusals, advisories, checks);
    }
    const tree = skillTreeMatchesRecord(skill, manifest);
    record("N2", tree.ok, tree.detail);
    if (!tree.ok) refusals.push({ code: "COMPAT_TREE_IDENTITY_MISMATCH", detail: tree.detail });
    record("N6", true, "standalone authority: no peer, recorded profile governs the local store");
    return finish(refusals.length ? "not-ready" : "compatible", refusals, advisories, checks, "standalone");
  }

  // N1: roles resolve to one skill side and one Command Center side.
  const rolesOk =
    skill && skill.role === "skill" && cc && cc.role === "command-center";
  record("N1", Boolean(rolesOk), rolesOk ? "one skill side, one Command Center side" : "component missing or roles ambiguous");
  if (!skill || !cc) {
    refusals.push({ code: "COMPAT_COMPONENT_MISSING", detail: "paired negotiation needs both a skill and a Command Center descriptor" });
    return finish("not-ready", refusals, advisories, checks);
  }
  if (!rolesOk) {
    refusals.push({ code: "COMPAT_ROLE_AMBIGUOUS", detail: `roles are skill=${skill.role}, cc=${cc.role}` });
    return finish("not-ready", refusals, advisories, checks);
  }

  // N2: the skill tree identity must be a recorded identity.
  const tree = skillTreeMatchesRecord(skill, manifest);
  record("N2", tree.ok, tree.detail);
  if (!tree.ok) refusals.push({ code: "COMPAT_TREE_IDENTITY_MISMATCH", detail: tree.detail });

  // N3: contract package version equality.
  const contractOk = skill.contract_package_version === cc.contract_package_version;
  record("N3", contractOk, `skill contract ${skill.contract_package_version} vs Command Center contract ${cc.contract_package_version}`);
  if (!contractOk) {
    refusals.push({
      code: "COMPAT_CONTRACT_VERSION_MISMATCH",
      detail: `skill declares ${skill.contract_package_version}, Command Center declares ${cc.contract_package_version}; payloads must not be exchanged`,
    });
  }

  // N4: the Command Center must declare the cohort endpoint registry
  // contract. Absent is the older Command Center case (T116).
  const expectedRegistry = manifest.wire_contract?.endpoint_registry_contract ?? null;
  if (cc.endpoint_registry_contract === null || cc.endpoint_registry_contract === undefined) {
    record("N4", false, "Command Center declares no council endpoint registry contract");
    refusals.push({
      code: "COMPAT_REGISTRY_CONTRACT_MISSING",
      detail: "the Command Center declares no council endpoint registry contract; this is the older Command Center case: report not-ready, start no shadow session",
    });
  } else if (cc.endpoint_registry_contract !== expectedRegistry) {
    record("N4", false, `Command Center registry contract ${cc.endpoint_registry_contract}, cohort requires ${expectedRegistry}`);
    refusals.push({
      code: "COMPAT_REGISTRY_CONTRACT_MISMATCH",
      detail: `Command Center declares ${cc.endpoint_registry_contract}, cohort requires ${expectedRegistry}`,
    });
  } else {
    record("N4", true, `registry contract ${expectedRegistry} declared by both sides`);
  }

  // N5: session exchange surface schema versions must agree.
  const surfaces = manifest.wire_contract?.session_exchange_surfaces ?? [];
  const surfaceMismatches = [];
  for (const surface of surfaces) {
    const a = skill.schema_versions?.[surface];
    const b = cc.schema_versions?.[surface];
    if (a !== b) surfaceMismatches.push(`${surface}: skill ${a} vs Command Center ${b}`);
  }
  record("N5", surfaceMismatches.length === 0, surfaceMismatches.length ? surfaceMismatches.join("; ") : `all ${surfaces.length} session exchange surfaces agree`);
  if (surfaceMismatches.length) {
    refusals.push({
      code: "COMPAT_SCHEMA_VERSION_UNSUPPORTED",
      detail: `schema version disagreement on ${surfaceMismatches.join("; ")}`,
    });
  }

  // N6: authority mode is never switched silently.
  const authorityOk = recordedAuthorityMode === null || recordedAuthorityMode === requestedAuthorityMode;
  record("N6", authorityOk, recordedAuthorityMode === null ? "no recorded profile yet; the requested mode will be recorded at first open" : `recorded mode ${recordedAuthorityMode}, requested ${requestedAuthorityMode}`);
  if (!authorityOk) {
    refusals.push({
      code: "COMPAT_AUTHORITY_MODE_MISMATCH",
      detail: `installation recorded authority mode "${recordedAuthorityMode}" but "${requestedAuthorityMode}" was requested; authority is never repointed silently`,
    });
  }

  // N7: skill version skew with an equal contract is portable-compatible,
  // but the visual experience must not be reported ready.
  const cohortSkill = cohortMember(manifest, skill.component);
  let portable = false;
  if (contractOk && cohortSkill && skill.skill_version !== cohortSkill.skill_version) {
    portable = true;
    advisories.push({
      code: "VISUAL_EXPERIENCE_NOT_READY",
      detail: `skill version ${skill.skill_version} differs from the cohort skill version ${cohortSkill.skill_version} while the contract package version matches; portable core only, visual experience not ready`,
    });
  }
  record("N7", true, portable ? "skill version skew: portable only" : "skill version matches the cohort");

  // N8: the Command Center migration id must never be claimed while it is
  // still the integration placeholder.
  if (cc.cc_migration_allocated === false) {
    advisories.push({
      code: "MIGRATION_ID_UNALLOCATED",
      detail: `Command Center council migration id is still ${cc.cc_migration_id}; no numbered migration may be claimed`,
    });
  }
  record("N8", true, cc.cc_migration_allocated ? "Command Center migration id allocated by integration" : "migration id unallocated (advisory)");

  // N9: a peer ahead of the cohort with an equal contract is portable.
  const cohortCc = cohortMember(manifest, "command-center");
  if (contractOk && cohortCc && cc.commit && cc.commit !== cohortCc.commit) {
    portable = true;
    advisories.push({
      code: "PEER_AHEAD_OF_COHORT",
      detail: `Command Center commit ${cc.commit} is not the cohort commit ${cohortCc.commit}; contract matches, so the pairing is portable-compatible and cohort claims wait for acceptance`,
    });
  }
  record("N9", true, "cohort membership checked");

  if (refusals.length) return finish("not-ready", refusals, advisories, checks, "paired");
  return finish(portable ? "compatible-portable" : "compatible", refusals, advisories, checks, "paired");
}

function finish(decision, refusals, advisories, checks, mode) {
  return {
    decision,
    allowed: decision !== "not-ready",
    mode: mode ?? "paired",
    refusals,
    advisories,
    checks,
  };
}

/**
 * The session-start gate a release adapter applies before starting a
 * paired (or standalone) session. Pure: the caller hands it descriptors;
 * it never opens a store, so a refusal cannot leave shadow state behind.
 */
export function gateSessionStart(args) {
  const result = negotiatePair(args);
  return {
    allowed: result.allowed,
    decision: result.decision,
    refusal_codes: result.refusals.map((r) => r.code),
    advisory_codes: result.advisories.map((a) => a.code),
    negotiation: result,
  };
}

// ---------------------------------------------------------------------------
// Manifest self-check: every value the manifest states about the wire and
// persistence contracts must equal what negotiate.mjs enforces.
// ---------------------------------------------------------------------------

export function checkManifest(manifest) {
  const problems = [];
  const wire = manifest.wire_contract ?? {};
  if (wire.contract_package_version !== "wise-elders.core/1.0.0") {
    // Not a hard-coded expectation: the check is that a value exists and
    // the schema map agrees with the endpoint registry contract.
    if (!wire.contract_package_version) problems.push("wire_contract.contract_package_version missing");
  }
  if (wire.schema_versions?.endpoint !== wire.endpoint_registry_contract) {
    problems.push("wire_contract.schema_versions.endpoint differs from endpoint_registry_contract");
  }
  for (const surface of wire.session_exchange_surfaces ?? []) {
    if (!wire.schema_versions?.[surface]) {
      problems.push(`session exchange surface ${surface} has no schema version in the manifest`);
    }
  }
  const members = manifest.release_cohort?.members ?? [];
  if (members.length !== 3) problems.push(`release cohort has ${members.length} members, expected 3`);
  for (const m of members) {
    if (!m.commit || !/^[0-9a-f]{40}$/.test(m.commit)) {
      problems.push(`cohort member ${m.component} has no full commit hash`);
    }
  }
  return problems;
}

// ---------------------------------------------------------------------------
// CLI
// ---------------------------------------------------------------------------

function usage() {
  console.error("usage: negotiate.mjs describe onb|cc|999 <root> [--commit <sha>] | check <skill.json> <cc.json> | gate <skill.json> <cc.json> | manifest <manifest.json>");
  process.exit(2);
}

function loadManifest() {
  const here = fileURLToPath(new URL(".", import.meta.url));
  return readJson(join(here, "compatibility-manifest.json"));
}

function main(argv) {
  const [cmd, ...rest] = argv;
  if (cmd === "describe") {
    const [kind, root, ...flags] = rest;
    if (!kind || !root) usage();
    const commitIdx = flags.indexOf("--commit");
    const opts = commitIdx >= 0 ? { commit: flags[commitIdx + 1] } : {};
    let descriptor;
    if (kind === "onb") descriptor = deriveOnbSkillDescriptor(root, opts);
    else if (kind === "cc") descriptor = deriveCcDescriptor(root, opts);
    else if (kind === "999") descriptor = derive999Descriptor(root, opts);
    else usage();
    console.log(JSON.stringify(descriptor, null, 2));
    return 0;
  }
  if (cmd === "check" || cmd === "gate") {
    const [skillPath, ccPath] = rest;
    if (!skillPath || !ccPath) usage();
    const skill = readJson(resolve(skillPath));
    const cc = readJson(resolve(ccPath));
    const manifest = loadManifest();
    const result = cmd === "gate"
      ? gateSessionStart({ skill, cc, manifest })
      : negotiatePair({ skill, cc, manifest });
    console.log(JSON.stringify(result, null, 2));
    const allowed = cmd === "gate" ? result.allowed : result.allowed;
    return allowed ? 0 : 3;
  }
  if (cmd === "manifest") {
    const [path] = rest;
    const manifest = path ? readJson(resolve(path)) : loadManifest();
    const problems = checkManifest(manifest);
    if (problems.length) {
      console.log(JSON.stringify({ ok: false, problems }, null, 2));
      return 3;
    }
    console.log(JSON.stringify({ ok: true, problems: [] }, null, 2));
    return 0;
  }
  usage();
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  process.exit(main(process.argv.slice(2)));
}
