// The Remotion composition for diagram scenes (Directive MG-017).
//
// The composition is a pure function of the resolved diagram and the
// current frame: node boxes, drawn edge prefixes, and the subject
// position all come from the diagrams frame functions, the same code
// the tests measure. Nothing is timed by wall clock or by the engine's
// animation helpers; seeking to a frame yields exactly the state the
// geometry functions compute for that frame.
//
// Font discipline mirrors C05: the exact resolved font files arrive as
// base64 props, register through FontFace behind a delayRender gate,
// and a load failure fails the render instead of substituting a font.

import { createElement, useEffect, useState, type CSSProperties } from "react";
import { AbsoluteFill, continueRender, delayRender, useCurrentFrame } from "remotion";
import {
  edgeDrawnPoints,
  nodeActiveAt,
  nodeBoxAt,
  subjectPositionAt,
  subjectStateAt,
  type ResolvedDiagram,
} from "../frame";
import { polylineLength } from "../geometry";
import { LABEL_SIZE_PX } from "../layout";

declare const document: {
  fonts: { add(face: unknown): void };
};
declare class FontFace {
  constructor(family: string, source: ArrayBuffer, descriptors?: { weight?: string });
  load(): Promise<unknown>;
}

export interface DiagramFontProp {
  family: string;
  files: { weight: number; base64: string }[];
}

export interface DiagramCompositionProps {
  resolved: ResolvedDiagram;
  headline: string;
  disclosure: string;
  durationFrames: number;
  font: DiagramFontProp;
}

export { DIAGRAM_COMPOSITION_ID } from "./ids";

const INK = "#192A38";
const ACCENT = "#C04A26";
const BACKGROUND = "#F7F4EE";

function base64ToBytes(b64: string): Uint8Array {
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
  const clean = b64.replace(/[^A-Za-z0-9+/=]/g, "");
  const bytes: number[] = [];
  for (let i = 0; i < clean.length; i += 4) {
    const a = alphabet.indexOf(clean[i]);
    const b = alphabet.indexOf(clean[i + 1]);
    const c = clean[i + 2] === "=" ? 0 : alphabet.indexOf(clean[i + 2]);
    const d = clean[i + 3] === "=" ? 0 : alphabet.indexOf(clean[i + 3]);
    bytes.push((a << 2) | (b >> 4));
    if (clean[i + 2] !== "=") bytes.push(((b & 15) << 4) | (c >> 2));
    if (clean[i + 3] !== "=") bytes.push(((c & 3) << 6) | d);
  }
  return new Uint8Array(bytes);
}

type FontGateState = { status: "loading" } | { status: "ready" } | { status: "failed"; message: string };

function FontGate(props: { font: DiagramFontProp; children?: unknown }): unknown {
  const [handle] = useState(() => delayRender("MG017 diagram: loading resolved font files"));
  const [state, setState] = useState<FontGateState>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;
    const fail = (err: unknown): void => {
      if (cancelled) return;
      const message = err instanceof Error ? err.message : String(err);
      setState({ status: "failed", message });
      continueRender(handle);
      setTimeout(() => {
        throw new Error(`MG017 diagram font load failed: ${message}`);
      }, 0);
    };
    if (props.font.files.length === 0) {
      fail(new Error("no font files were supplied in the input props"));
      return () => {
        cancelled = true;
      };
    }
    Promise.all(
      props.font.files.map((file) => {
        const bytes = base64ToBytes(file.base64);
        const face = new FontFace(props.font.family, bytes.buffer as ArrayBuffer, {
          weight: String(file.weight),
        });
        return face.load().then((loaded) => {
          document.fonts.add(loaded);
        });
      })
    ).then(
      () => {
        if (cancelled) return;
        setState({ status: "ready" });
        continueRender(handle);
      },
      fail
    );
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (state.status === "failed") {
    return createElement(
      "div",
      {
        style: {
          position: "absolute",
          inset: 0,
          backgroundColor: "#FF00FF",
          color: "#FFFFFF",
          fontSize: 48,
          padding: 40,
        } as CSSProperties,
      },
      `FONT LOAD FAILED: ${state.message}`
    );
  }
  if (state.status === "loading") return null;
  return props.children as never;
}

export function DiagramComposition(props: DiagramCompositionProps): unknown {
  const frame = useCurrentFrame();
  const { resolved } = props;
  const { width, height } = resolved.canvas;

  const edgeElements = resolved.edges.map((edge) => {
    const drawn = edgeDrawnPoints(resolved, edge, frame);
    // An edge with zero drawn length renders nothing: a round line cap
    // would otherwise stamp a dot at the undrawn edge's start point.
    if (drawn.length < 2 || polylineLength(drawn) < 0.5) return null;
    return createElement("polyline", {
      key: `edge-${edge.id}`,
      points: drawn.map((point) => `${point.x},${point.y}`).join(" "),
      fill: "none",
      stroke: INK,
      strokeWidth: 6,
      strokeLinecap: "round",
      strokeLinejoin: "round",
    });
  });

  const children: unknown[] = [
    createElement(
      "div",
      {
        key: "headline",
        style: {
          position: "absolute",
          left: 96,
          top: 56,
          width: width - 192,
          fontSize: 84,
          fontWeight: 700,
          lineHeight: 1.1,
          color: INK,
        } as CSSProperties,
      },
      props.headline
    ),
    createElement(
      "svg",
      {
        key: "edges",
        width,
        height,
        viewBox: `0 0 ${width} ${height}`,
        style: { position: "absolute", left: 0, top: 0 } as CSSProperties,
      },
      edgeElements
    ),
  ];

  for (const node of resolved.nodes) {
    const box = nodeBoxAt(resolved, node, frame);
    const active = nodeActiveAt(resolved, node, frame);
    children.push(
      createElement(
        "div",
        {
          key: `node-${node.id}`,
          "data-subject-id": `node-${node.id}`,
          style: {
            position: "absolute",
            left: box.x,
            top: box.y,
            width: box.width,
            height: box.height,
            backgroundColor: "#FFFFFF",
            border: `4px ${node.kind === "constraint" ? "dashed" : "solid"} ${
              node.kind === "decision" ? ACCENT : INK
            }`,
            borderRadius: 18,
            opacity: active ? 1 : 0.35,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          } as CSSProperties,
        },
        createElement(
          "span",
          {
            style: {
              fontSize: LABEL_SIZE_PX,
              fontWeight: node.kind === "decision" ? 700 : 400,
              color: INK,
              whiteSpace: "nowrap",
            } as CSSProperties,
          },
          node.label
        )
      )
    );
  }

  const subjectPosition = subjectPositionAt(resolved, frame);
  if (resolved.subject && subjectPosition) {
    const state = subjectStateAt(resolved, frame);
    children.push(
      createElement(
        "div",
        {
          key: "subject-label",
          style: {
            position: "absolute",
            left: subjectPosition.x - 130,
            top: subjectPosition.y - 92,
            width: 260,
            textAlign: "center",
            fontSize: 34,
            fontWeight: 700,
            color: ACCENT,
          } as CSSProperties,
        },
        resolved.subject.id
      ),
      createElement("div", {
        key: "subject-marker",
        "data-subject-id": `subject-${resolved.subject.id}`,
        style: {
          position: "absolute",
          left: subjectPosition.x - 26,
          top: subjectPosition.y - 26,
          width: 52,
          height: 52,
          borderRadius: "50%",
          backgroundColor: ACCENT,
          border: "4px solid #FFFFFF",
        } as CSSProperties,
      })
    );
    if (state !== null) {
      children.push(
        createElement(
          "div",
          {
            key: "subject-state",
            style: {
              position: "absolute",
              left: subjectPosition.x - 130,
              top: subjectPosition.y + 36,
              width: 260,
              textAlign: "center",
              fontSize: 32,
              color: INK,
            } as CSSProperties,
          },
          state
        )
      );
    }
  }

  children.push(
    createElement(
      "div",
      {
        key: "disclosure",
        style: {
          position: "absolute",
          left: 96,
          bottom: 44,
          fontSize: 40,
          color: INK,
        } as CSSProperties,
      },
      props.disclosure
    )
  );

  return createElement(
    AbsoluteFill,
    {
      style: {
        backgroundColor: BACKGROUND,
        fontFamily: `'${props.font.family}', sans-serif`,
      } as CSSProperties,
    },
    createElement(FontGate, { font: props.font }, children)
  );
}
