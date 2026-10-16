// Adapter contract and capability-based routing for the Skill 72 Motion
// Graphics V2 runtime (Directive MG-004). Types and the Section 5.5
// interface live in types.ts, the Section 3.2 routing rules in routing.ts,
// the capability matrix handling in capabilities.ts, and the orchestration
// dispatcher in dispatch.ts. The human-readable authority is
// references/renderer-routing.md.
export * from "./types";
export * from "./routing";
export * from "./capabilities";
export * from "./dispatch";
