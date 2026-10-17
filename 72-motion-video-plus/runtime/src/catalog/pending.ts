// The Section 7.1 components whose production bundles have not landed
// yet in this tree: C10-C12. (C04 and C09 register as available
// through MG-017 in c04.ts and c09.ts; C06-C08 register as available
// through MG-016 in c06.ts, c07.ts, and c08.ts; C01-C03 register as
// available through MG-044 in c01.ts, c02.ts, and c03.ts.)
// Each entry here is registered with its Section 7.1
// identity, visible change, default engine, and minimum proof, and each
// is explicitly UNAVAILABLE: under Section 16.1 a component is
// unavailable until its closed input schema, proof contract, and tests
// are registered together, and those bundles belong to the owning items
// named per entry. The catalog refuses dispatch for these components
// with MG_CAPABILITY_UNSUPPORTED and never substitutes another component.

import type {
  AssetRequirement,
  ComponentEntry,
  DataRequirement,
  LayoutVariant,
  TimelineContract,
  TypographyRole,
  VariationDescriptor,
} from "./types";
import type { ProductionEngine } from "../adapters/types";

const STANDARD_LAYOUTS: LayoutVariant[] = [
  {
    id: "landscape",
    aspect: "16:9",
    description: "16:9 canvas, geometry declared by the job design record.",
  },
  {
    id: "portrait",
    aspect: "9:16",
    description:
      "9:16 canvas, genuinely recomposed from the design record, never a crop of the landscape layout.",
  },
];

function pendingTimeline(readableHold: string): TimelineContract {
  return {
    intervalConvention: "half_open",
    durationSource:
      "scene.duration_frames, declared per scene when the component's bundle registers",
    supportedFps: [30, 60],
    transitionHandleFields: [
      "timeline.scenes[].transition_in_frames",
      "timeline.scenes[].transition_out_frames",
    ],
    readableHold,
    audioCueBehavior:
      "The component is silent unless its registered bundle declares cues; audio belongs to the job or parent per timeline.audio_owner.",
  };
}

interface PendingSpec {
  componentId: string;
  name: string;
  visibleChange: string;
  semanticPurpose: string;
  engines: ProductionEngine[];
  defaultEngine: ComponentEntry["defaultEngine"];
  owningItem: string;
  minimumProof: string;
  assetRequirements: AssetRequirement[];
  dataRequirements: DataRequirement[];
  typographyRoles: TypographyRole[];
  variation: VariationDescriptor;
  readableHold: string;
  beatSceneIntent: string;
}

function pendingEntry(spec: PendingSpec): ComponentEntry {
  return {
    componentId: spec.componentId,
    version: "1.0.0",
    name: spec.name,
    availability: "unavailable",
    unavailableReason:
      `Registered identity only. Under Section 16.1 this component is ` +
      `unavailable until its closed input schema, proof contract, and tests ` +
      `are registered together; that bundle is owned by ${spec.owningItem}. ` +
      `Minimum proof it must register: ${spec.minimumProof}`,
    owningItem: spec.owningItem,
    visibleChange: spec.visibleChange,
    semanticPurpose: spec.semanticPurpose,
    engines: spec.engines,
    defaultEngine: spec.defaultEngine,
    inputSchema: null,
    schemaSource: null,
    assetRequirements: spec.assetRequirements,
    dataRequirements: spec.dataRequirements,
    layoutVariants: STANDARD_LAYOUTS,
    timelineContract: pendingTimeline(spec.readableHold),
    proofContract: null,
    typographyRoles: spec.typographyRoles,
    variation: spec.variation,
    examples: [
      {
        id: `${spec.componentId.toLowerCase()}-storyboard-beat`,
        kind: "storyboard_beat",
        description:
          "Planning-level example in the Section 5.3 storyboard shape. It documents intent only; no scene can be dispatched for this component yet.",
        scene: null,
        beat: {
          beat_id: `${spec.componentId.toLowerCase()}-example`,
          scene_intent: spec.beatSceneIntent,
          component_id: spec.componentId,
        },
      },
    ],
    tests: [],
    provenance:
      `Section 7.1 row ${spec.componentId}. Identity, visible change, ` +
      `default engine, and minimum proof are quoted from the Section 7.1 ` +
      `table. No implementation is claimed by this registration.`,
  };
}

const IMAGE_FONT: AssetRequirement = {
  kind: "font",
  usage: ["embed_original"],
  role: "scene_typography",
  required: true,
  notes:
    "Resolved through the job assets font_requirements (runtime_registry alias); substitution is forbidden.",
};

export function pendingEntries(): ComponentEntry[] {
  return [
    pendingEntry({
      componentId: "C10",
      name: "Spatial/depth explanation",
      visibleChange:
        "Layers or objects establish front/back, containment, or scale relationships",
      semanticPurpose:
        "Explain a spatial relationship honestly: layers or objects establish front/back, containment, or scale with occlusion and perspective evidence, ending in a readable composition.",
      engines: ["remotion", "hyperframes"],
      defaultEngine: "qualified-native-integration",
      owningItem:
        "no owning item named in the Section 15 table at this base; the bundle registers with a future spatial component item",
      minimumProof:
        "Occlusion/perspective evidence plus readable final composition",
      assetRequirements: [
        {
          kind: "image",
          usage: ["embed_original", "approved_derivative"],
          role: "spatial_layer",
          required: false,
          notes:
            "Layers may be approved images or component-drawn objects; the bundle declares which when it registers.",
        },
        IMAGE_FONT,
      ],
      dataRequirements: [],
      typographyRoles: [
        {
          role: "headline",
          designField: null,
          purpose: "States the spatial claim.",
        },
        {
          role: "layer_label",
          designField: null,
          purpose: "Names layers or objects where the explanation needs them.",
        },
      ],
      variation: {
        composition:
          "Layered field with declared depth order; the final composition is designed, not an accident of the animation.",
        framing:
          "Scale relationships come from the design record; perspective is never faked past the evidence.",
        typeTreatment:
          "Labels sized from the design record and kept in the readable plane.",
        pacing:
          "Depth is established layer by layer; the final composition holds.",
      },
      readableHold:
        "The final spatial composition, labels legible, holds to the scene end.",
      beatSceneIntent:
        "Establish the front/back relationship layer by layer and land on the readable composition.",
    }),
    pendingEntry({
      componentId: "C11",
      name: "Evidence/offer reveal",
      visibleChange:
        "Approved evidence or offer elements appear in a designed hierarchy",
      semanticPurpose:
        "Present proof or an offer credibly: only approved, authentic elements appear, arranged in a designed hierarchy with an adequate final hold to read them.",
      engines: ["remotion", "hyperframes"],
      defaultEngine: "either",
      owningItem:
        "no owning item named in the Section 15 table at this base; the bundle registers with a future evidence component item",
      minimumProof: "Authentic content, hierarchy, adequate final hold",
      assetRequirements: [
        {
          kind: "image",
          usage: ["embed_original"],
          role: "data_evidence",
          required: true,
          notes:
            "Evidence elements are embedded originals only. Fictional or illustrative material must be labeled as such and never presented as proof.",
        },
        IMAGE_FONT,
      ],
      dataRequirements: [],
      typographyRoles: [
        {
          role: "headline",
          designField: null,
          purpose: "States what the evidence proves.",
        },
        {
          role: "evidence_label",
          designField: null,
          purpose: "Identifies each evidence element and its source.",
        },
        {
          role: "disclosure",
          designField: null,
          purpose: "Carries terms and honesty disclosures for offers and evidence.",
        },
      ],
      variation: {
        composition:
          "A designed hierarchy: claim first, evidence in declared order, disclosure legible at the hold.",
        framing:
          "Evidence elements are shown whole, never cropped into a different claim.",
        typeTreatment:
          "Hierarchy sized from the design record; disclosure never below the readable floor.",
        pacing:
          "Elements appear in hierarchy order; the final hold is long enough to read every element.",
      },
      readableHold:
        "All revealed elements remain visible and readable for the declared final hold.",
      beatSceneIntent:
        "Reveal the approved evidence in hierarchy order and hold it long enough to read.",
    }),
    pendingEntry({
      componentId: "C12",
      name: "Presenter-safe loop/reveal",
      visibleChange:
        "Motion remains presentable over narration or loops without jarring resets",
      semanticPurpose:
        "Stay presentable under a presenter: motion loops or holds without a jarring reset, and no essential information ever disappears while someone may still be reading it.",
      engines: ["remotion", "hyperframes"],
      defaultEngine: "either",
      owningItem:
        "no owning item named in the Section 15 table at this base; the bundle registers with a future presenter-safe component item",
      minimumProof:
        "No jump at loop seam; no disappearing essential information",
      assetRequirements: [IMAGE_FONT],
      dataRequirements: [],
      typographyRoles: [
        {
          role: "headline",
          designField: null,
          purpose: "Carries the essential information that must never disappear.",
        },
        {
          role: "caption",
          designField: null,
          purpose: "Supports the loop without carrying essential information alone.",
        },
      ],
      variation: {
        composition:
          "A calm field designed for indefinite presentation; essential content sits in the stable zone.",
        framing:
          "Looping elements stay inside the design record's safe area, clear of player chrome.",
        typeTreatment:
          "Essential type is static or returns identically each loop; sized from the design record.",
        pacing:
          "Loop period is declared; the seam is a designed match, never a reset jump.",
      },
      readableHold:
        "Essential information is continuously readable, including across the loop seam.",
      beatSceneIntent:
        "Settle into a loop a presenter can talk over without a visible reset.",
    }),
  ];
}
