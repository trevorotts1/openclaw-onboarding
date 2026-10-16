import { AbsoluteFill, useCurrentFrame } from "remotion";

// Invalid Remotion scene (MG-030 lint fixture): a wall-clock timer in
// the component body makes the frame depend on time the frame clock
// does not own.
export function ClockScene() {
  const frame = useCurrentFrame();
  setTimeout(function () {}, 400);
  return (
    <AbsoluteFill style={{ backgroundColor: "#F7F4EE" }}>
      <div style={{ width: frame, height: 90, backgroundColor: "#C04A26" }} />
    </AbsoluteFill>
  );
}
