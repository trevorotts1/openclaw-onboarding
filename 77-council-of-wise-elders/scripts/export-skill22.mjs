#!/usr/bin/env node
// Council of Wise Elders: Skill 22 source-pack exporter.
// NOT YET BUILT. Exporting advisor source packs from Skill 22
// (book-to-persona) extractions is owned by the Skill 22 export unit
// (CWE-011). This entry point exists so the package layout is
// complete and the capability has one honest address; it performs no
// export, writes nothing, and exits non-zero so no caller can mistake
// it for a working exporter.
// Exit code: 2 (not yet built).

console.error("NOT_YET_BUILT: the Skill 22 exporter is owned by CWE-011 and has not landed.");
console.error("No export was performed. Advisor packs are built from verified Skill 22 extractions only;");
console.error("see references/source-policy.md for the evidence rules a real export must satisfy.");
process.exit(2);
