// Composition identifier for the MG-032 decoy. Kept in a pure module
// with no engine imports: node-side harness code needs the id without
// loading the composition (react and remotion exist only inside the
// shared runtime and the browser bundle). Mirrors the MG-017 ids
// module.

export const DECOY_COMPOSITION_ID = "MG032-DecoyStaticChart";
