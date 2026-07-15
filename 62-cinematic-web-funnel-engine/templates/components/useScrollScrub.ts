"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ScrollDebugState, SceneConfig } from "./types";

/**
 * useScrollScrub — the first-party scroll-scrub engine required by spec
 * Section 13.2. Deliberately small and dependency-free (spec 13.1: "The
 * initial implementation should prefer a small first-party scroll engine";
 * GSAP is optional only, not used here).
 *
 * Every requirement in spec 13.2 maps to a concrete mechanism below:
 *
 *  - preload only what is required        -> a scene only mounts its
 *                                            <video> at all once it is
 *                                            within NEIGHBOR_MOUNT_RADIUS of
 *                                            the active scene (SceneVideoLayer
 *                                            is not rendered otherwise), so a
 *                                            10-scene page only ever fetches
 *                                            1-3 clips at a time.
 *  - normalized progress -> currentTime    -> computeProgress() below.
 *  - avoid uncontrolled seek storms        -> SEEK_EPSILON_SECONDS guard,
 *                                            readyState gate.
 *  - requestAnimationFrame scheduling      -> the tick() loop.
 *  - forward AND reverse scrolling         -> progress is always recomputed
 *                                            from absolute scroll position,
 *                                            never accumulated from deltas,
 *                                            so reverse scroll is naturally
 *                                            correct, not a special case.
 *  - manage scene crossfades and z-index   -> opacity/zIndex map returned to
 *                                            the caller (ScrollScrubEngine).
 *  - handle fast scroll jumps              -> same "always absolute, never
 *                                            accumulated" property; no
 *                                            catch-up animation to overshoot.
 *  - handle tab background/foreground      -> visibilitychange listener
 *                                            cancels/resumes the rAF loop.
 *  - autoplay restrictions / muted inline  -> enforced in SceneVideoLayer's
 *                                            <video muted playsInline>; this
 *                                            hook only ever sets
 *                                            `currentTime`, never calls
 *                                            `.play()` with sound.
 *  - poster fallback                       -> readiness gate below; caller
 *                                            renders the poster until a
 *                                            scene's video reports
 *                                            readyState >= HAVE_CURRENT_DATA.
 *  - low-power/mobile constraints          -> detectLowPowerMode() below.
 *  - never a nested-scroll trap             -> this hook reads
 *                                            window.scrollY /
 *                                            container.getBoundingClientRect()
 *                                            only; it never sets
 *                                            overflow:auto/scroll on the
 *                                            stage container and never
 *                                            calls preventDefault on wheel
 *                                            events. The stage is a normal
 *                                            block element in document flow.
 *  - deterministic debug state              -> window.__cwfeScrollDebug,
 *                                            updated every tick.
 */

const SEEK_EPSILON_SECONDS = 0.03;
/** Fraction of a scene's on-screen segment, at its tail end, used to blend
 * into the next scene's opacity (crossfade window). */
const CROSSFADE_WINDOW = 0.12;
/** How many scenes beyond the active one stay mounted for smooth
 * transitions. Reduced to 0 (active scene only) in low-power mode. */
const NEIGHBOR_MOUNT_RADIUS = 1;

export interface SceneBlend {
  sceneId: string;
  opacity: number;
  zIndex: number;
  progress: number;
  shouldMount: boolean;
}

export interface ScrollScrubResult {
  containerRef: React.RefObject<HTMLDivElement | null>;
  registerVideoRef: (sceneId: string) => (el: HTMLVideoElement | null) => void;
  blends: SceneBlend[];
  debugState: ScrollDebugState;
  reducedMotion: boolean;
}

function prefersReducedMotion(): boolean {
  if (typeof window === "undefined" || !window.matchMedia) return false;
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function detectLowPowerMode(): boolean {
  if (typeof navigator === "undefined") return false;
  const nav = navigator as Navigator & {
    deviceMemory?: number;
    connection?: { saveData?: boolean; effectiveType?: string };
  };
  if (typeof nav.deviceMemory === "number" && nav.deviceMemory > 0 && nav.deviceMemory <= 4) {
    return true;
  }
  const conn = nav.connection;
  if (conn) {
    if (conn.saveData) return true;
    if (conn.effectiveType === "2g" || conn.effectiveType === "slow-2g") return true;
  }
  return false;
}

function clamp01(n: number): number {
  if (Number.isNaN(n)) return 0;
  return Math.min(1, Math.max(0, n));
}

export function useScrollScrub(scenes: SceneConfig[]): ScrollScrubResult {
  const containerRef = useRef<HTMLDivElement>(null);
  const videoElsRef = useRef<Map<string, HTMLVideoElement>>(new Map());
  const rafIdRef = useRef<number | null>(null);
  const lastOverallProgressRef = useRef(0);

  // Lazy initializer, not an effect: React 19's react-hooks/set-state-in-effect
  // rule flags calling setState synchronously in an effect body (it can
  // trigger a cascading render). Reading the media query during the
  // component's own render pass avoids that render entirely for the
  // initial value; the effect below only SUBSCRIBES to later changes,
  // which is exactly what effects are for.
  const [reducedMotion, setReducedMotion] = useState<boolean>(() => prefersReducedMotion());
  const [blends, setBlends] = useState<SceneBlend[]>(() =>
    scenes.map((s, i) => ({
      sceneId: s.sceneId,
      opacity: i === 0 ? 1 : 0,
      zIndex: scenes.length - i,
      progress: 0,
      shouldMount: i === 0,
    })),
  );
  const [debugState, setDebugState] = useState<ScrollDebugState>(() => ({
    activeSceneId: scenes[0]?.sceneId ?? null,
    activeSceneIndex: 0,
    sceneProgress: 0,
    overallProgress: 0,
    direction: "idle",
    reducedMotion: false,
    tabVisible: typeof document === "undefined" ? true : !document.hidden,
    lowPowerMode: false,
    mountedSceneIds: scenes[0] ? [scenes[0].sceneId] : [],
    lastUpdate: 0,
  }));

  // Reduced-motion detection, live-updated on media query change. Low-power
  // mode is re-detected every rAF tick inside the effect below (it can
  // change mid-session, e.g. Data Saver toggled or a metered connection
  // detected later) and folded straight into each tick's debug state.
  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return;
    const mql = window.matchMedia("(prefers-reduced-motion: reduce)");
    const onChange = () => setReducedMotion(mql.matches);
    mql.addEventListener?.("change", onChange);
    return () => mql.removeEventListener?.("change", onChange);
  }, []);

  const registerVideoRef = useCallback(
    (sceneId: string) => (el: HTMLVideoElement | null) => {
      if (el) videoElsRef.current.set(sceneId, el);
      else videoElsRef.current.delete(sceneId);
    },
    [],
  );

  useEffect(() => {
    if (reducedMotion) {
      // Reduced motion disables scroll scrubbing entirely (spec 13.4). The
      // caller renders a static fallback instead of mounting this engine's
      // video stage. No setState here — the returned debugState below
      // already merges the current `reducedMotion` value in during render,
      // which is the correct place to derive it (react-hooks/set-state-in-
      // effect flags writing it from inside an effect body instead).
      return;
    }

    let tabVisible = typeof document === "undefined" ? true : !document.hidden;

    const onVisibility = () => {
      tabVisible = !document.hidden;
      if (tabVisible) {
        scheduleTick();
      } else if (rafIdRef.current !== null) {
        cancelAnimationFrame(rafIdRef.current);
        rafIdRef.current = null;
        for (const v of videoElsRef.current.values()) v.pause();
      }
    };

    function computeOverallProgress(): number {
      const container = containerRef.current;
      if (!container) return 0;
      const rect = container.getBoundingClientRect();
      const viewportH = window.innerHeight || document.documentElement.clientHeight;
      const scrollableHeight = rect.height - viewportH;
      if (scrollableHeight <= 0) return 0;
      // rect.top is negative once the container has scrolled past the top
      // of the viewport; this is an ABSOLUTE computation from the current
      // layout every tick, never an accumulated delta, so both fast forward
      // jumps and reverse scroll resolve to the exact right frame with no
      // catch-up animation.
      return clamp01(-rect.top / scrollableHeight);
    }

    function tick() {
      rafIdRef.current = null;
      const overallProgress = computeOverallProgress();
      const prevOverall = lastOverallProgressRef.current;
      const direction: ScrollDebugState["direction"] =
        overallProgress > prevOverall + 1e-6
          ? "forward"
          : overallProgress < prevOverall - 1e-6
            ? "reverse"
            : "idle";
      lastOverallProgressRef.current = overallProgress;

      const n = scenes.length;
      const rawIndex = n > 0 ? overallProgress * n : 0;
      const activeIndex = Math.min(n - 1, Math.max(0, Math.floor(rawIndex)));
      const sceneProgress = clamp01(rawIndex - activeIndex);

      const currentLowPower = detectLowPowerMode();
      const neighborRadius = currentLowPower ? 0 : NEIGHBOR_MOUNT_RADIUS;

      const nextBlends: SceneBlend[] = scenes.map((scene, i) => {
        const withinMountRadius = Math.abs(i - activeIndex) <= neighborRadius;
        let opacity = 0;
        if (i === activeIndex) {
          opacity = 1;
          // Crossfade into the NEXT scene during the tail of this one.
          if (sceneProgress > 1 - CROSSFADE_WINDOW && i < n - 1) {
            opacity = clamp01((1 - sceneProgress) / CROSSFADE_WINDOW);
          }
        } else if (i === activeIndex + 1 && sceneProgress > 1 - CROSSFADE_WINDOW) {
          opacity = clamp01((sceneProgress - (1 - CROSSFADE_WINDOW)) / CROSSFADE_WINDOW);
        } else if (i === activeIndex - 1 && sceneProgress < CROSSFADE_WINDOW) {
          // Reverse-scroll crossfade symmetry.
          opacity = clamp01((CROSSFADE_WINDOW - sceneProgress) / CROSSFADE_WINDOW);
        }
        const localProgress =
          i === activeIndex
            ? sceneProgress
            : i < activeIndex
              ? 1
              : 0;
        return {
          sceneId: scene.sceneId,
          opacity,
          zIndex: n - Math.abs(i - activeIndex),
          progress: localProgress,
          // Preload gate (spec 13.2 "preload only what is required"): a
          // scene mounts its <video> only within the active neighbor
          // radius (or while already blending in) — never all scenes at
          // once. Recomputed from absolute scroll position every tick, so
          // it is correct on fast forward/reverse jumps with no separate
          // "catch up" pass.
          shouldMount: withinMountRadius || opacity > 0,
        };
      });

      // Seek each mounted, near-enough video to its target time, guarded
      // against seek storms and against seeking a video that isn't ready.
      for (const blend of nextBlends) {
        if (!blend.shouldMount) continue;
        const video = videoElsRef.current.get(blend.sceneId);
        if (!video) continue;
        const scene = scenes.find((s) => s.sceneId === blend.sceneId);
        if (!scene) continue;
        if (video.readyState < HTMLMediaElement.HAVE_CURRENT_DATA) continue;
        const targetTime = clamp01(blend.progress) * scene.durationSeconds;
        if (Math.abs(video.currentTime - targetTime) > SEEK_EPSILON_SECONDS) {
          try {
            video.currentTime = targetTime;
          } catch {
            // A seek can throw on some browsers if called before the
            // media element is fully seekable; safe to ignore and retry
            // next tick once readyState catches up.
          }
        }
      }

      setBlends(nextBlends);
      const activeScene = scenes[activeIndex];
      const nextDebug: ScrollDebugState = {
        activeSceneId: activeScene ? activeScene.sceneId : null,
        activeSceneIndex: activeIndex,
        sceneProgress,
        overallProgress,
        direction,
        reducedMotion: false,
        tabVisible,
        lowPowerMode: currentLowPower,
        mountedSceneIds: nextBlends.filter((b) => b.shouldMount).map((b) => b.sceneId),
        lastUpdate: Date.now(),
      };
      setDebugState(nextDebug);
      if (typeof window !== "undefined") {
        window.__cwfeScrollDebug = nextDebug;
      }

      if (tabVisible) scheduleTick();
    }

    function scheduleTick() {
      if (rafIdRef.current !== null) return;
      rafIdRef.current = requestAnimationFrame(tick);
    }

    scheduleTick();
    document.addEventListener("visibilitychange", onVisibility);
    window.addEventListener("resize", scheduleTick, { passive: true });

    return () => {
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("resize", scheduleTick);
      if (rafIdRef.current !== null) cancelAnimationFrame(rafIdRef.current);
      rafIdRef.current = null;
    };
  }, [scenes, reducedMotion]);

  // Derived at render time (not via effect + setState) — see the comment
  // above the `if (reducedMotion)` early-return for why.
  const mergedDebugState = useMemo(
    () => (debugState.reducedMotion === reducedMotion ? debugState : { ...debugState, reducedMotion }),
    [debugState, reducedMotion],
  );

  return {
    containerRef,
    registerVideoRef,
    blends,
    debugState: mergedDebugState,
    reducedMotion,
  };
}
