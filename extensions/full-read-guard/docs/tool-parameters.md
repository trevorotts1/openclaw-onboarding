# OpenClaw tool parameter names this plugin relies on

Recorded from OpenClaw 2026.11.3 as installed on the build machine. These are read from source and documentation, not guessed.

## read (file tool)

Source: `readToolInputSchema` in the installed package (`dist/tool-schemas-*.mjs`) and `createReadToolDefinition` (`dist/tools-*.mjs`).

| Parameter | Type | Meaning |
|---|---|---|
| `path` | string, required | File path, relative or absolute. The display code also accepts `file_path`, so the plugin reads `path` first, then `file_path`. |
| `offset` | integer, at least 1 | Start line, 1-based. |
| `limit` | number | Maximum lines. |
| `cursor` | integer, at least 0 | Character position within the start line. |
| `optional` | literal true | A missing path returns a structured not-found result instead of an error. |

Facts that shape the design:
- One read returns at most 2000 lines or 51200 bytes (default `maxBytes` 51200). A longer file comes back truncated with a "use offset=N to continue" notice. For an instruction file that is too large for one call the plugin therefore blocks and points to `read_skill`, which delivers complete parts.
- A skill can be read through a virtual path `workspace-skill://workspace/<skill-name>/<relative-path>` (`dist/workspace-skill-read-path-*.mjs`). The plugin resolves that form to the skill folder.

## exec (shell tool)

Source: `docs/tools/exec.md`, section Parameters.

| Parameter | Type | Meaning |
|---|---|---|
| `command` | string, required | Shell command to run. |
| `workdir` | string | Working directory; relative paths resolve against the session cwd. `~` is not expanded. |
| `env`, `yieldMs`, `background`, `timeoutSeconds` | various | Not used by the plugin. |

The documentation names the tool `exec`, not `bash`. The plugin matches both names.

## Hook facts

Source: `docs/plugins/hooks/tool-policy.md`, `docs/plugins/hooks/reference.md`, and the type declarations in `dist/plugin-sdk`.

- `before_tool_call` event: `toolName`, `params`, optional `toolKind`, `derivedPaths`, `runId`, `toolCallId`. Context: `agentId`, `sessionKey`, `sessionId`, `runId`, `abortSignal`, `requester`. Return `{ block: true, blockReason }` or `{ params }` (rewrite). `block: false` means no decision. Native Codex tools reject rewrites; only block works there.
- `after_tool_call` event: `toolName`, `params`, `result`, `error`, `durationMs`.
- Tool factory context (`OpenClawPluginToolContext`) carries `agentId`, `sessionKey`, `sessionId`, `workspaceDir`, so `read_skill` can key its receipt to the same session as the hook.
- `session_start`, `session_end` (reason includes `compaction`, `new`, `reset`), `after_compaction`: observe only.
