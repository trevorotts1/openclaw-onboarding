// C05 linear_bar_reveal: the parameterized comparison bar chart
// (Directive MG-006, MG-016 seed, Section 17.2 proof states).
//
// The component is a pure function of its input props and the current
// frame: bar geometry comes from the shared chart geometry in
// chart-geometry.ts (MG-016), which routes lengths through the MG-015
// zero-baseline barGeometry; progress is computed through seconds so a
// change of fps preserves the reveal's timing, and every text element
// renders at the design layout's declared pixel sizes (no fitted
// shrinking; the design forbids essential-text shrink).
//
// Font discipline: the composition registers the exact font files the
// adapter resolved (bytes arrive as base64 props) through the FontFace
// API and holds the render with delayRender until every face is loaded.
// If a face fails to load, the frame renders an unmistakable error panel
// AND the error is rethrown in the page so the render itself fails: a
// silently substituted font never produces a "successful" artifact.

import { createElement, useEffect, useState, type CSSProperties } from "react";
import { AbsoluteFill, continueRender, delayRender, useCurrentFrame, useVideoConfig } from "remotion";
import { formatValue as formatChartValue, type DisplayRounding } from "../../charts";
import { barStateAt } from "./chart-geometry";
import type { C05Props } from "../job-props";

// Browser globals used by the font gate, declared locally: this package
// compiles without DOM lib types because the browser only exists inside
// the Remotion render (see engine-modules.d.ts).
declare const document: {
  fonts: { add(face: unknown): void };
};
declare class FontFace {
  constructor(family: string, source: ArrayBuffer, descriptors?: { weight?: string });
  load(): Promise<unknown>;
}

/** Decode a base64 string to bytes inside the page (no atob dependency,
 * so the decoder behaves identically in every Chromium build). */
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

function FontGate(props: { font: C05Props["font"]; children?: unknown }): unknown {
  const [handle] = useState(() => delayRender("C05: loading resolved font files"));
  const [state, setState] = useState<FontGateState>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;
    const fail = (err: unknown): void => {
      if (cancelled) return;
      const message = err instanceof Error ? err.message : String(err);
      setState({ status: "failed", message });
      continueRender(handle);
      // Rethrow outside the promise chain so the page reports an
      // uncaught error and the render fails instead of emitting a frame
      // set in a substituted font.
      setTimeout(() => {
        throw new Error(`C05 font load failed: ${message}`);
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
    // The gate loads once per mount; props.font is stable per render.
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

/**
 * Display form for a dataset value (MG-016 formatting adoption): when
 * the dataset's declared display rounding reaches the component, the
 * shared MG-015 formatter (charts/format.ts) prints exactly the
 * declared decimals, rounded half away from zero on the decimal
 * string. The canonical job path cannot carry a declaration yet (the
 * contracts dataset $def has no display_rounding field, and plumbing
 * it through job-props belongs to the recorded integration item), so
 * when no declaration is present the interim rule applies: integers
 * print as integers, other values print at two decimals with trailing
 * zeros trimmed, computed through the same shared rounding engine so
 * decimal-string edge cases (the 1.005 class) round correctly.
 */
export function formatValue(value: number, rounding?: DisplayRounding): string {
  if (rounding) return formatChartValue(value, rounding);
  if (Number.isInteger(value)) return String(value);
  return formatChartValue(value, { decimals: 2 }).replace(/\.?0+$/, "");
}

export function C05BarChart(props: C05Props): unknown {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const { colors, layout } = props.design;
  const motion = {
    startFrame: props.motion.startFrame,
    endFrameExclusive: props.motion.endFrameExclusive,
    authoredFps: props.motion.authoredFps,
  };
  // Bar geometry through the MG-015 zero baseline (chart-geometry):
  // lengths are proportional to the values from zero on every domain,
  // fixing D-CHART-BASELINE. On zero-min domains (including the shipped
  // fixture) the geometry is identical to the previous domain-minimum
  // scale, so the Section 17.2 proof states do not move.
  const barStates = props.dataset.rows.map((row) =>
    barStateAt(row.value, props.dataset.domain, layout.plot.width, frame, fps, motion)
  );
  // The dataset's declared display rounding, when the loader plumbed
  // it into the props (see formatValue's note on the interim rule).
  const declaredRounding = (
    props.dataset as { displayRounding?: DisplayRounding }
  ).displayRounding;
  const centerY = (rowIndex: number): number => layout.row_y[rowIndex] + layout.bar_height / 2;

  const children: unknown[] = [
    // Headline, at the design's declared size and box. It wraps within
    // the box: the portrait box (920 x 280) is sized for two lines at
    // the declared 112 px, and forcing one line would clip essential
    // text off the canvas. The size itself never shrinks (the design
    // forbids essential-text shrink).
    createElement(
      "div",
      {
        key: "headline",
        style: {
          position: "absolute",
          left: layout.headline_box.x,
          top: layout.headline_box.y,
          width: layout.headline_box.width,
          fontSize: layout.headline_px,
          fontWeight: 700,
          lineHeight: 1.1,
          color: colors.ink,
        } as CSSProperties,
      },
      props.headline
    ),
  ];

  props.dataset.rows.forEach((row, i) => {
    children.push(
      createElement(
        "div",
        {
          key: `label-${row.id}`,
          style: {
            position: "absolute",
            right: props.canvas.width - (layout.plot.x - 20),
            top: centerY(i),
            transform: "translateY(-50%)",
            fontSize: layout.label_px,
            color: colors.ink,
            textAlign: "right",
          } as CSSProperties,
        },
        row.label
      ),
      createElement("div", {
        key: `bar-${row.id}`,
        "data-subject-id": `bar-${row.id}`,
        style: {
          position: "absolute",
          left: layout.plot.x + barStates[i].x,
          top: layout.row_y[i],
          width: barStates[i].width,
          height: layout.bar_height,
          backgroundColor: colors.accent,
        } as CSSProperties,
      }),
      createElement(
        "div",
        {
          key: `value-${row.id}`,
          style: {
            position: "absolute",
            left: layout.plot.x + layout.plot.width + 28,
            top: centerY(i),
            transform: "translateY(-50%)",
            fontSize: layout.value_px,
            color: colors.ink,
          } as CSSProperties,
        },
        formatValue(row.value, declaredRounding)
      )
    );
  });

  children.push(
    createElement(
      "div",
      {
        key: "disclosure",
        style: {
          position: "absolute",
          left: layout.headline_box.x,
          bottom: props.layoutVariant === "landscape" ? 40 : 56,
          fontSize: layout.disclosure_px,
          color: colors.ink,
        } as CSSProperties,
      },
      props.disclosure
    )
  );

  return createElement(
    AbsoluteFill,
    {
      style: {
        backgroundColor: colors.background,
        fontFamily: `'${props.font.family}', sans-serif`,
      } as CSSProperties,
    },
    createElement(FontGate, { font: props.font }, children)
  );
}
