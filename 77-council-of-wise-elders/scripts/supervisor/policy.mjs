// Policy loader for the Hybrid Council of Wise Elders supervisor.
// The policy is the versioned JSON schema template shipped beside this module.
// It is TEMPLATE_NOT_BOUND here: this module never installs, schedules or binds
// a runtime. The native-adapter binding is a later unit and stays UNKNOWN.
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

export const POLICY_SCHEMA_ID = "wise-elders.hybrid-supervisor-policy/v2";
export const POLICY_SCHEMA_PATH = join(
  dirname(fileURLToPath(import.meta.url)),
  "policy",
  "wise-elders.hybrid-supervisor-policy.v2.schema.json",
);

export const POLICY_FIELDS = Object.freeze([
  "full_sweep_interval_seconds",
  "health_tick_seconds",
  "heartbeat_suspect_after_seconds",
  "max_concurrent_workflows",
  "max_agents_per_workflow",
  "max_total_agents",
  "require_independent_non_author_review",
  "require_exact_head_checks",
  "require_atomic_expected_head_merge_guard",
  "standing_repository_merge_authorized",
  "vercel_required",
  "cloudflare_build_required",
  "customer_remote_access_opt_in",
  "explicit_stop_disables_automatic_engineering_restart",
]);

export function readPolicySchema(path = POLICY_SCHEMA_PATH) {
  const schema = JSON.parse(readFileSync(path, "utf8"));
  if (schema.$id !== POLICY_SCHEMA_ID) {
    throw new Error(`policy schema $id must be ${POLICY_SCHEMA_ID}, got ${schema.$id}`);
  }
  return schema;
}

// The embedded example IS the schema: every governed field carries its value as
// a JSON Schema `const`. Building the default policy from those constants keeps
// one source of truth instead of a second hand-copied object.
export function defaultPolicy(schema = readPolicySchema()) {
  const policy = {};
  for (const key of Object.keys(schema.properties)) {
    const rule = schema.properties[key];
    const value = Object.hasOwn(rule, "const") ? rule.const : rule.default;
    if (value === undefined) {
      throw new Error(`policy field ${key} has no const/default in the schema`);
    }
    policy[key] = value;
  }
  return Object.freeze(policy);
}

export function validatePolicy(policy, schema = readPolicySchema()) {
  const errors = [];
  if (!policy || typeof policy !== "object") {
    return { ok: false, errors: ["policy must be an object"] };
  }
  for (const key of Object.keys(schema.properties)) {
    const rule = schema.properties[key];
    if (!Object.hasOwn(policy, key)) {
      errors.push(`missing policy field ${key}`);
      continue;
    }
    if (rule.type === "integer" && !Number.isInteger(policy[key])) {
      errors.push(`${key} must be an integer`);
    }
    if (rule.type === "boolean" && typeof policy[key] !== "boolean") {
      errors.push(`${key} must be a boolean`);
    }
    if (rule.type === "string" && typeof policy[key] !== "string") {
      errors.push(`${key} must be a string`);
    }
    if (Object.hasOwn(rule, "const") && policy[key] !== rule.const) {
      errors.push(`${key} must be ${JSON.stringify(rule.const)}`);
    }
  }
  for (const key of Object.keys(policy)) {
    if (!Object.hasOwn(schema.properties, key)) {
      errors.push(`unknown policy field ${key}`);
    }
  }
  if (policy.binding_status !== "TEMPLATE_NOT_BOUND") {
    errors.push("binding_status must stay TEMPLATE_NOT_BOUND in this unit");
  }
  return { ok: errors.length === 0, errors };
}
