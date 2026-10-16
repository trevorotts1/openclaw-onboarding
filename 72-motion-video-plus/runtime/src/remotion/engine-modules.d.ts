// Boundary declarations for the engine packages the compositions use.
//
// React and Remotion are installed ONLY in the shared render runtime
// (shared-utils/motion-render-runtime, MG-003); the skill runtime never
// installs a second copy, so tsc cannot resolve these modules from this
// package's own dependency tree. The declarations below cover exactly
// the API surface the compositions in this directory use, matching
// remotion 4.0.535 and react 19 as installed in the shared runtime. At
// bundle time the Remotion bundler resolves the real packages from the
// shared runtime's node_modules (see adapters/remotion.ts).

declare module "react" {
  export type ReactNode = unknown;
  export interface CSSProperties {
    [key: string]: string | number | undefined;
  }
  export function createElement(
    type: unknown,
    props: Record<string, unknown> | null,
    ...children: unknown[]
  ): unknown;
  export function useState<T>(initial: T | (() => T)): [T, (next: T) => void];
  export function useEffect(effect: () => void | (() => void), deps?: unknown[]): void;
}

declare module "remotion" {
  import type { CSSProperties, ReactNode } from "react";

  export interface VideoConfig {
    width: number;
    height: number;
    fps: number;
    durationInFrames: number;
    id: string;
    defaultProps: unknown;
  }

  export function useCurrentFrame(): number;
  export function useVideoConfig(): VideoConfig;
  export function delayRender(label?: string): number;
  export function continueRender(handle: number): void;
  export function registerRoot(component: () => unknown): void;

  export const AbsoluteFill: (props: {
    style?: CSSProperties;
    children?: ReactNode;
  }) => unknown;

  /** Registered through React.createElement in Root.ts; the props
   * record (id, component, durationInFrames, fps, width, height,
   * defaultProps, calculateMetadata) follows the Remotion 4.0.535
   * Composition API, with metadata calculated from the input props. */
  export const Composition: (props: Record<string, unknown>) => unknown;
}
