// Composition identifiers for the diagrams render harness (MG-017).
// Kept in a pure module with no engine imports: node-side harness code
// needs the id without loading the composition (react and remotion
// exist only inside the shared runtime and the browser bundle).

export const DIAGRAM_COMPOSITION_ID = "MG017-Diagram";
