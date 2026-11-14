// full-read-guard: OpenClaw plugin entry. Hooks: before_tool_call (gate + rewrite), after_tool_call (receipts),
// session_start / session_end / after_compaction (receipt reset). Tool: read_skill.
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createGuard, Guard } from './gate.js';

export { createGuard } from './gate.js';
export * from './classify.js';
export * from './closure.js';
export * from './frontmatter.js';
export * from './glob.js';
export * from './manifest.js';
export * from './paths.js';
export * from './read-skill.js';
export * from './receipts.js';
export * from './shell-parse.js';

export const TOOL_MATCHER = ['read', 'exec', 'bash'];
const PLUGIN_ID = 'full-read-guard';

export function register(api: any): Guard | null {
  const config = api && api.pluginConfig && typeof api.pluginConfig === 'object' ? api.pluginConfig : {};
  if (config.enabled === false || config.mode === 'off') return null;
  const here = path.dirname(fileURLToPath(import.meta.url));
  const pluginDir = path.resolve(here, '..');
  const logger = api && api.logger;
  const guard = createGuard({
    mode: config.mode,
    skillsDir: config.skillsDir,
    stateDir: config.stateDir,
    manifestDir: path.join(pluginDir, 'manifest.d'),
    pluginDir,
    chunkChars: config.chunkChars,
    loopBreakerRepeats: config.loopBreakerRepeats,
    maxBlocksPerRun: config.maxBlocksPerRun,
    log: (level, msg) => { try { (logger && (level === 'warn' ? logger.warn : logger.info))?.call(logger, `[${PLUGIN_ID}] ${msg}`); } catch { /* ignore */ } },
  });
  api.on('before_tool_call', (event: any, ctx: any) => guard.beforeToolCall(event, ctx), { matcher: TOOL_MATCHER });
  api.on('after_tool_call', (event: any, ctx: any) => { guard.afterToolCall(event, ctx); }, { matcher: ['read'] });
  for (const hook of ['session_start', 'session_end', 'after_compaction']) {
    try { api.on(hook, (_event: any, ctx: any) => { guard.resetSession(ctx); }); } catch (e) { try { logger?.warn?.(`[${PLUGIN_ID}] could not register ${hook}: ${String(e)}`); } catch { /* ignore */ } }
  }
  api.registerTool((toolContext: any) => guard.readSkillTool(toolContext), { name: 'read_skill' });
  return guard;
}

export default (api: any) => {
  try {
    return register(api);
  } catch (error) {
    try { api?.logger?.error?.(`[${PLUGIN_ID}] registration failed (guard not active): ${String(error)}`); } catch { /* ignore */ }
    return null;
  }
};
