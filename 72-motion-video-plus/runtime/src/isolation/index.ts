// Render isolation layer for Skill 72 Motion Graphics V2 (MG-029).
//
// Generated scene code and remote assets are untrusted inputs. This
// layer is the security boundary that keeps a render from exposing
// provider credentials, reaching the network, escaping its job
// directory, or taking unrelated processes down with it:
//   env.ts        allowlisted child environments, secret redaction
//   paths.ts      asset reference validation with named findings
//   processes.ts  ownership-recorded process registry and termination
//   network.ts    network-namespace render policies (fail closed)
//   assets.ts     approved-asset preparation fetch + local origin
//   runner.ts     one spawn path composing all of the above
//   workdir.ts    job-specific writable directories
//   launch.ts     CLI that gives any command the same boundary
//
// Static lint (src/lint) is NOT part of this boundary and is never a
// substitute for it: lint reads code, this layer constrains what
// running code can reach. The human-readable authority is
// references/render-isolation.md.

export * from "./errors";
export * from "./env";
export * from "./paths";
export * from "./processes";
export * from "./network";
export * from "./assets";
export * from "./runner";
export * from "./workdir";
