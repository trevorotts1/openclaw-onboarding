// The font gate for the MG-016 chart components: the same discipline
// as the C05 gate in C05BarChart.ts (MG-006). The composition registers
// the exact font files the loader resolved (bytes arrive as base64
// props) through the FontFace API and holds the render with
// delayRender until every face is loaded. If a face fails to load, the
// frame renders an unmistakable error panel AND the error is rethrown
// in the page so the render itself fails: a silently substituted font
// never produces a "successful" artifact.

import { createElement, useEffect, useState, type CSSProperties } from "react";
import { continueRender, delayRender } from "remotion";
import type { ChartFontProps } from "./chart-props";

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

export function FontGate(props: {
  font: ChartFontProps;
  /** Component label for error messages, for example "C06". */
  label: string;
  children?: unknown;
}): unknown {
  const [handle] = useState(() => delayRender(`${props.label}: loading resolved font files`));
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
        throw new Error(`${props.label} font load failed: ${message}`);
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
