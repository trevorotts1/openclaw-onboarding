// Motion component catalog (Directive MG-018). See
// references/component-catalog.md for the registration contract, the
// twelve Section 7.1 entries and their states, and the governed
// custom-component path.

export * from "./types";
export * from "./errors";
export { CATALOG_ENTRY_SCHEMA, validateCatalogEntry } from "./entry-schema";
export { c01Entry, c01Registration } from "./c01";
export { c02Entry, c02Registration } from "./c02";
export { c03Entry, c03Registration } from "./c03";
export {
  c01SceneSchema,
  c02SceneSchema,
  c03SceneSchema,
} from "./image-scene-schema";
export { c04Entry, c04ExampleScene } from "./c04";
export { c05Entry } from "./c05";
export { c09Entry, c09ExampleScene } from "./c09";
export { c06Entry, c06Registration } from "./c06";
export { c07Entry, c07Registration } from "./c07";
export { c08Entry, c08Registration } from "./c08";
export {
  chartSceneSchema,
  C06_EXTRA_PROPERTIES,
  C07_EXTRA_PROPERTIES,
  C08_EXTRA_PROPERTIES,
  type ChartSceneSchemaOptions,
} from "./chart-scene-schema";
export { pendingEntries } from "./pending";
export {
  ComponentRegistry,
  OFFICIAL_COMPONENT_IDS,
  type ScenePropsValidation,
} from "./registry";
