import { AbsoluteFill, interpolate, useCurrentFrame } from "remotion";

// Valid Remotion scene (MG-030 lint fixture): every animated value is a
// pure function of the frame clock, read through useCurrentFrame and
// interpolate. No wall clock, no timers, no CSS transitions, no fetches.
export function PassScene() {
  const frame = useCurrentFrame();
  const width = interpolate(frame, [15, 75], [0, 1200], {
    extrapolateRight: "clamp",
  });
  return (
    <AbsoluteFill style={{ backgroundColor: "#F7F4EE" }}>
      <div style={{ width, height: 90, backgroundColor: "#C04A26" }} />
    </AbsoluteFill>
  );
}
