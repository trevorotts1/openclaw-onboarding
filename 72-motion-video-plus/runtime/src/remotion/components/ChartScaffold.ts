// The shared frame for the MG-016 chart components: background, the
// font gate, the headline at the design's declared size and box, and
// the honesty disclosure. Mirrors the C05 component's frame discipline
// (MG-006): text renders at the design layout's declared pixel sizes
// and never shrinks to fit; the headline wraps inside its declared box.

import { createElement, type CSSProperties } from "react";
import { AbsoluteFill } from "remotion";
import { FontGate } from "./FontGate";
import type { ChartFontProps, ChartLayoutProps } from "./chart-props";

export function ChartScaffold(props: {
  font: ChartFontProps;
  /** Component label for font-gate error messages. */
  label: string;
  background: string;
  ink: string;
  layout: ChartLayoutProps;
  layoutVariant: "landscape" | "portrait";
  headline: string;
  disclosure: string;
  children: unknown[];
}): unknown {
  const { layout } = props;
  const children: unknown[] = [
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
          color: props.ink,
        } as CSSProperties,
      },
      props.headline
    ),
    ...props.children,
    createElement(
      "div",
      {
        key: "disclosure",
        style: {
          position: "absolute",
          left: layout.headline_box.x,
          bottom: props.layoutVariant === "landscape" ? 40 : 56,
          fontSize: layout.disclosure_px,
          color: props.ink,
        } as CSSProperties,
      },
      props.disclosure
    ),
  ];
  return createElement(
    AbsoluteFill,
    {
      style: {
        backgroundColor: props.background,
        fontFamily: `'${props.font.family}', sans-serif`,
      } as CSSProperties,
    },
    createElement(FontGate, { font: props.font, label: props.label }, children)
  );
}
