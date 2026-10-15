// Engine-aware lint layer (Directive MG-030): parse-based validation
// of scene and component sources against the selected engine's rules.
// See references/lint-and-validation.md for the category contract and
// the honest statement of what a clean scan does and does not prove.
export * from "./types";
export { validateSource, formatReport } from "./validate";
export { scanHtml, LineIndex } from "./html";
