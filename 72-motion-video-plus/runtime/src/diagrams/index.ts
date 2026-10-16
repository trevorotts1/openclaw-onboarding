// Causal diagrams and spatial explanations (Directive MG-017):
// node/edge model, deterministic layout and path geometry, the four
// mechanism patterns, pure frame functions, and semantic motion
// assertions for components C04 (object-through-mechanism) and C09
// (causal/branching diagram).

export * from "./model";
export * from "./geometry";
export * from "./frame";
export {
  resolveDiagram,
  labelCollisions,
  subjectPathLength,
  LABEL_SIZE_PX,
  NODE_HEIGHT_PX,
  CANVAS_MARGIN_PX,
  RELIEF_WIDEN_FRAMES,
  type TextMeasurer,
  type LayoutResult,
} from "./layout";
export { FontTextMeasurer } from "./font-measure";
export {
  flowThrough,
  branchingDecision,
  beforeAfterSystem,
  bottleneckRemoval,
  diagramSceneDoc,
  type StageInput,
  type SubjectInput,
} from "./patterns";
export {
  C04_INPUT_SCHEMA,
  C09_INPUT_SCHEMA,
  inputSchemaFor,
  validateDiagramSceneDoc,
} from "./schema";
export {
  evaluateAssertion,
  evaluateAssertions,
  evaluateCausality,
  type AssertionResult,
  type CausalityCheck,
} from "./assertions";
