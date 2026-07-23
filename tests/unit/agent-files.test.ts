/**
 * agent-files.test.ts — Unit tests for src/lib/agent-files.ts
 * U088 — Symlink write guard.
 */
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import * as fs from 'node:fs';
import * as path from 'node:path';
import * as os_node from 'node:os';

import {
  SharedFileError,
  SHARED_FILES,
  isSymlinkSync,
  readlinkSyncSafe,
  writeAgentFile,
  preflightSharedFields,
} from '../../src/lib/agent-files';

let tmpDir: string;

beforeEach(() => {
  tmpDir = fs.mkdtempSync(path.join(os_node.tmpdir(), 'agent-files-test-'));
});

afterEach(() => {
  try { fs.rmSync(tmpDir, { recursive: true, force: true }); } catch { /* ok */ }
});

describe('SHARED_FILES', () => {
  it('contains AGENTS.md, TOOLS.md, USER.md', () => {
    expect(SHARED_FILES.has('AGENTS.md')).toBe(true);
    expect(SHARED_FILES.has('TOOLS.md')).toBe(true);
    expect(SHARED_FILES.has('USER.md')).toBe(true);
  });
  it('does not contain per-agent files', () => {
    expect(SHARED_FILES.has('SOUL.md')).toBe(false);
    expect(SHARED_FILES.has('IDENTITY.md')).toBe(false);
    expect(SHARED_FILES.has('MEMORY.md')).toBe(false);
    expect(SHARED_FILES.has('HEARTBEAT.md')).toBe(false);
  });
});

describe('isSymlinkSync', () => {
  it('returns true for a symbolic link', () => {
    const target = path.join(tmpDir, 'real.txt');
    const link = path.join(tmpDir, 'link.txt');
    fs.writeFileSync(target, 'real content');
    fs.symlinkSync(target, link);
    expect(isSymlinkSync(link)).toBe(true);
  });
  it('returns false for a regular file', () => {
    const filePath = path.join(tmpDir, 'regular.txt');
    fs.writeFileSync(filePath, 'hello');
    expect(isSymlinkSync(filePath)).toBe(false);
  });
  it('returns false for a non-existent path (ENOENT)', () => {
    expect(isSymlinkSync(path.join(tmpDir, 'does-not-exist.txt'))).toBe(false);
  });
  it('returns false for a directory', () => {
    expect(isSymlinkSync(tmpDir)).toBe(false);
  });
});

describe('readlinkSyncSafe', () => {
  it('returns the symlink target for a symbolic link', () => {
    const target = path.join(tmpDir, 'real.md');
    const link = path.join(tmpDir, 'AGENTS.md');
    fs.writeFileSync(target, '# shared rules');
    fs.symlinkSync(target, link);
    expect(readlinkSyncSafe(link)).toBe(target);
  });
  it('returns null for a regular file', () => {
    const filePath = path.join(tmpDir, 'regular.md');
    fs.writeFileSync(filePath, 'content');
    expect(readlinkSyncSafe(filePath)).toBe(null);
  });
  it('returns null for a non-existent path', () => {
    expect(readlinkSyncSafe(path.join(tmpDir, 'nope.md'))).toBe(null);
  });
});

describe('writeAgentFile', () => {
  it('writes successfully to a regular (non-symlink) file', async () => {
    const filePath = path.join(tmpDir, 'SOUL.md');
    const content = '# Department soul';
    const result = await writeAgentFile({ filePath, content });
    expect(result.written).toBe(true);
    expect(fs.readFileSync(filePath, 'utf-8')).toBe(content);
  });

  it('writes successfully to a non-existent path (creates dirs)', async () => {
    const filePath = path.join(tmpDir, 'new', 'subdir', 'SOUL.md');
    const content = 'fresh';
    const result = await writeAgentFile({ filePath, content });
    expect(result.written).toBe(true);
    expect(fs.readFileSync(filePath, 'utf-8')).toBe(content);
  });

  it('rejects write through a symlink for AGENTS.md', async () => {
    const sharedTarget = path.join(tmpDir, '_shared', 'AGENTS.md');
    fs.mkdirSync(path.join(tmpDir, '_shared'), { recursive: true });
    fs.writeFileSync(sharedTarget, '# Shared rules — all agents');
    const agentLink = path.join(tmpDir, 'sales', 'AGENTS.md');
    fs.mkdirSync(path.join(tmpDir, 'sales'), { recursive: true });
    fs.symlinkSync(sharedTarget, agentLink);
    await expect(
      writeAgentFile({ filePath: agentLink, content: '# Overwritten!' }),
    ).rejects.toThrow(SharedFileError);
    expect(fs.readFileSync(sharedTarget, 'utf-8')).toBe('# Shared rules — all agents');
  });

  it('rejects write through a symlink for TOOLS.md', async () => {
    const sharedTarget = path.join(tmpDir, '_shared', 'TOOLS.md');
    fs.mkdirSync(path.join(tmpDir, '_shared'), { recursive: true });
    fs.writeFileSync(sharedTarget, '## Tools available');
    const agentLink = path.join(tmpDir, 'marketing', 'TOOLS.md');
    fs.mkdirSync(path.join(tmpDir, 'marketing'), { recursive: true });
    fs.symlinkSync(sharedTarget, agentLink);
    await expect(
      writeAgentFile({ filePath: agentLink, content: '[]' }),
    ).rejects.toThrow(SharedFileError);
    expect(fs.readFileSync(sharedTarget, 'utf-8')).toBe('## Tools available');
  });

  it('rejects write through a symlink for USER.md', async () => {
    const sharedTarget = path.join(tmpDir, '_shared', 'USER.md');
    fs.mkdirSync(path.join(tmpDir, '_shared'), { recursive: true });
    fs.writeFileSync(sharedTarget, '# User profile');
    const agentLink = path.join(tmpDir, 'engineering', 'USER.md');
    fs.mkdirSync(path.join(tmpDir, 'engineering'), { recursive: true });
    fs.symlinkSync(sharedTarget, agentLink);
    await expect(
      writeAgentFile({ filePath: agentLink, content: '# Malicious' }),
    ).rejects.toThrow(SharedFileError);
    expect(fs.readFileSync(sharedTarget, 'utf-8')).toBe('# User profile');
  });

  it('includes the symlink target in the error message', async () => {
    const sharedTarget = path.join(tmpDir, '_shared', 'AGENTS.md');
    fs.mkdirSync(path.join(tmpDir, '_shared'), { recursive: true });
    fs.writeFileSync(sharedTarget, 'shared');
    const agentLink = path.join(tmpDir, 'hr', 'AGENTS.md');
    fs.mkdirSync(path.join(tmpDir, 'hr'), { recursive: true });
    fs.symlinkSync(sharedTarget, agentLink);
    try {
      await writeAgentFile({ filePath: agentLink, content: 'bad' });
      expect.fail('should have thrown');
    } catch (err) {
      expect(err).toBeInstanceOf(SharedFileError);
      const se = err as SharedFileError;
      expect(se.code).toBe('ESHAREDFILE');
      expect(se.symlinkTarget).toBe(sharedTarget);
      expect(se.message).toContain('AGENTS.md');
      expect(se.message).toContain('symbolic link');
    }
  });

  it('does NOT reject a regular file with a shared-file name', async () => {
    const filePath = path.join(tmpDir, 'special-agent', 'AGENTS.md');
    fs.mkdirSync(path.join(tmpDir, 'special-agent'), { recursive: true });
    fs.writeFileSync(filePath, '# Local override');
    const result = await writeAgentFile({ filePath, content: '# Updated local override' });
    expect(result.written).toBe(true);
    expect(fs.readFileSync(filePath, 'utf-8')).toBe('# Updated local override');
  });

  it('does NOT reject a non-shared filename symlink', async () => {
    const target = path.join(tmpDir, '_shared', 'SOUL.md');
    fs.mkdirSync(path.join(tmpDir, '_shared'), { recursive: true });
    fs.writeFileSync(target, 'department soul');
    const link = path.join(tmpDir, 'sales', 'SOUL.md');
    fs.mkdirSync(path.join(tmpDir, 'sales'), { recursive: true });
    fs.symlinkSync(target, link);
    const result = await writeAgentFile({ filePath: link, content: 'updated soul' });
    expect(result.written).toBe(true);
    expect(fs.readFileSync(target, 'utf-8')).toBe('updated soul');
  });

  it('handles deep symlink chains for shared files', async () => {
    const sharedTarget = path.join(tmpDir, '_shared', 'AGENTS.md');
    fs.mkdirSync(path.join(tmpDir, '_shared'), { recursive: true });
    fs.writeFileSync(sharedTarget, '# Chain shared rules');
    const intermediateLink = path.join(tmpDir, 'agent', 'local-link');
    fs.mkdirSync(path.join(tmpDir, 'agent'), { recursive: true });
    fs.symlinkSync(sharedTarget, intermediateLink);
    const agentLink = path.join(tmpDir, 'agent', 'AGENTS.md');
    fs.symlinkSync(intermediateLink, agentLink);
    await expect(
      writeAgentFile({ filePath: agentLink, content: '# overwritten' }),
    ).rejects.toThrow(SharedFileError);
    expect(fs.readFileSync(sharedTarget, 'utf-8')).toBe('# Chain shared rules');
  });

  it('SharedFileError has the correct name and code properties', () => {
    const err = new SharedFileError('test error', '/path/to/target');
    expect(err.name).toBe('SharedFileError');
    expect(err.code).toBe('ESHAREDFILE');
    expect(err.symlinkTarget).toBe('/path/to/target');
    expect(err).toBeInstanceOf(Error);
  });

  it('SharedFileError works with null symlinkTarget', () => {
    const err = new SharedFileError('test');
    expect(err.symlinkTarget).toBe(null);
  });
});

describe('preflightSharedFields', () => {
  it('returns allowed=true for non-shared filenames', () => {
    const result = preflightSharedFields(path.join(tmpDir, 'sales', 'SOUL.md'));
    expect(result.allowed).toBe(true);
    expect(result.conflict).toBeUndefined();
    expect(result.symlinkTarget).toBeUndefined();
  });

  it('returns allowed=true for a regular file with a shared-file name', () => {
    const filePath = path.join(tmpDir, 'sales', 'AGENTS.md');
    fs.mkdirSync(path.join(tmpDir, 'sales'), { recursive: true });
    fs.writeFileSync(filePath, 'local rules');
    const result = preflightSharedFields(filePath);
    expect(result.allowed).toBe(true);
    expect(result.conflict).toBeUndefined();
  });

  it('returns allowed=true for a non-existent path', () => {
    const result = preflightSharedFields(path.join(tmpDir, 'nonexistent', 'AGENTS.md'));
    expect(result.allowed).toBe(true);
  });

  it('returns allowed=false with conflict for AGENTS.md symlink', () => {
    const sharedTarget = path.join(tmpDir, '_shared', 'AGENTS.md');
    fs.mkdirSync(path.join(tmpDir, '_shared'), { recursive: true });
    fs.writeFileSync(sharedTarget, '# shared');
    const agentLink = path.join(tmpDir, 'sales', 'AGENTS.md');
    fs.mkdirSync(path.join(tmpDir, 'sales'), { recursive: true });
    fs.symlinkSync(sharedTarget, agentLink);
    const result = preflightSharedFields(agentLink);
    expect(result.allowed).toBe(false);
    expect(result.conflict).toBeDefined();
    expect(result.conflict).toContain('AGENTS.md');
    expect(result.conflict).toContain('symbolic link');
    expect(result.symlinkTarget).toBe(sharedTarget);
  });

  it('returns allowed=false with conflict for TOOLS.md symlink', () => {
    const sharedTarget = path.join(tmpDir, '_shared', 'TOOLS.md');
    fs.mkdirSync(path.join(tmpDir, '_shared'), { recursive: true });
    fs.writeFileSync(sharedTarget, '# tools');
    const agentLink = path.join(tmpDir, 'marketing', 'TOOLS.md');
    fs.mkdirSync(path.join(tmpDir, 'marketing'), { recursive: true });
    fs.symlinkSync(sharedTarget, agentLink);
    const result = preflightSharedFields(agentLink);
    expect(result.allowed).toBe(false);
    expect(result.conflict).toContain('TOOLS.md');
    expect(result.symlinkTarget).toBe(sharedTarget);
  });

  it('returns allowed=false with conflict for USER.md symlink', () => {
    const sharedTarget = path.join(tmpDir, '_shared', 'USER.md');
    fs.mkdirSync(path.join(tmpDir, '_shared'), { recursive: true });
    fs.writeFileSync(sharedTarget, '# user');
    const agentLink = path.join(tmpDir, 'engineering', 'USER.md');
    fs.mkdirSync(path.join(tmpDir, 'engineering'), { recursive: true });
    fs.symlinkSync(sharedTarget, agentLink);
    const result = preflightSharedFields(agentLink);
    expect(result.allowed).toBe(false);
    expect(result.symlinkTarget).toBe(sharedTarget);
  });
});

describe('edge cases', () => {
  it('creates intermediate directories for regular files', async () => {
    const filePath = path.join(tmpDir, 'a', 'b', 'c', 'SOUL.md');
    const result = await writeAgentFile({ filePath, content: 'deep' });
    expect(result.written).toBe(true);
    expect(fs.readFileSync(filePath, 'utf-8')).toBe('deep');
  });

  it('overwrites an existing regular file', async () => {
    const filePath = path.join(tmpDir, 'old.md');
    fs.writeFileSync(filePath, 'original');
    const result = await writeAgentFile({ filePath, content: 'replacement' });
    expect(result.written).toBe(true);
    expect(fs.readFileSync(filePath, 'utf-8')).toBe('replacement');
  });

  it('empty content is written correctly', async () => {
    const filePath = path.join(tmpDir, 'EMPTY.md');
    fs.writeFileSync(filePath, 'prior');
    const result = await writeAgentFile({ filePath, content: '' });
    expect(result.written).toBe(true);
    expect(fs.readFileSync(filePath, 'utf-8')).toBe('');
  });

  it('isSymlinkSync: handles broken symlinks (dangling)', () => {
    const link = path.join(tmpDir, 'broken-link');
    fs.symlinkSync(path.join(tmpDir, 'nowhere'), link);
    expect(isSymlinkSync(link)).toBe(true);
  });

  it('readlinkSyncSafe: handles broken symlinks', () => {
    const nowhere = path.join(tmpDir, 'nowhere');
    const link = path.join(tmpDir, 'broken');
    fs.symlinkSync(nowhere, link);
    expect(readlinkSyncSafe(link)).toBe(nowhere);
  });

  it('preflightSharedFields: non-shared filename symlink returns allowed', () => {
    const target = path.join(tmpDir, 'real.txt');
    fs.writeFileSync(target, 'real');
    const link = path.join(tmpDir, 'SOUL.md');
    fs.symlinkSync(target, link);
    const result = preflightSharedFields(link);
    expect(result.allowed).toBe(true);
  });
});
