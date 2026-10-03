import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";
import { register } from "./brake-core.mjs";

export default definePluginEntry({
  id: "loop-brake",
  name: "Loop Brake",
  description: "Real-time brake for repeated sessions_send resends and repeated fail-closed refusals (Skill 61).",
  register(api) {
    register(api);
  },
});
