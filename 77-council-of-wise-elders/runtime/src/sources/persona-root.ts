/**
 * Decision 4a foundation: find the CLIENT'S OWN Book-to-Persona (Skill 22)
 * store from the installed skill and platform defaults. No operator path is
 * ever hard-coded; every location comes from env, the discovered host
 * layout, or the supplied home directory.
 *
 * Read-only. Never throws from the resolver; a missing store is `null`.
 */
import { accessSync, constants, statSync } from 'node:fs';
import { homedir } from 'node:os';
import { join, resolve } from 'node:path';
import { SEAT_ROSTER, type SeatId } from '../contracts/enums.js';
import { discoverHostLayout } from '../cli/route-discovery.js';
import { inventoryCouncilSkill22Personas } from './skill22-inventory.js';

export const BOOK_TO_PERSONA_FOLDER = '22-book-to-persona-coaching-leadership-system';

export interface BookToPersonaRoot {
  /** Directory holding persona-categories.json + personas/. */
  skill_root: string;
  personas_dir: string;
  categories_path: string;
  resolved_from: 'env:BOOK_TO_PERSONA_ROOT' | 'env:OPENCLAW_SKILLS_DIR' | 'host_layout_skill_dir' | 'openclaw_default';
}

export interface PersonaRootOptions {
  env?: NodeJS.ProcessEnv;
  homeDir?: string;
}

const CATEGORIES = 'persona-categories.json';

function isDir(p: string): boolean {
  try {
    return statSync(p).isDirectory();
  } catch {
    return false;
  }
}

function readableFile(p: string): boolean {
  try {
    accessSync(p, constants.R_OK);
    return statSync(p).isFile();
  } catch {
    return false;
  }
}

function nonEmpty(v: string | undefined): string | null {
  return typeof v === 'string' && v.trim().length > 0 ? v.trim() : null;
}

export function resolveBookToPersonaRoot(opts: PersonaRootOptions = {}): BookToPersonaRoot | null {
  try {
    const env = opts.env ?? process.env;
    const home = resolve(opts.homeDir ?? homedir());
    // Lazy: the host layout is only read when the cheaper branches miss.
    let workspaceCategories: string | null | undefined;
    const workspaceFallback = (): string | null => {
      if (workspaceCategories !== undefined) return workspaceCategories;
      let workspace = join(home, '.openclaw', 'workspace');
      try {
        workspace = discoverHostLayout({ homeDir: home, env }).workspace || workspace;
      } catch {
        /* ambiguous host layout: keep the platform default workspace */
      }
      const candidate = join(workspace, 'data', 'coaching-personas', CATEGORIES);
      workspaceCategories = readableFile(candidate) ? candidate : null;
      return workspaceCategories;
    };

    const check = (skillRoot: string, resolvedFrom: BookToPersonaRoot['resolved_from']): BookToPersonaRoot | null => {
      const root = resolve(skillRoot);
      const personasDir = join(root, 'personas');
      if (!isDir(personasDir)) return null;
      const own = join(root, CATEGORIES);
      const categoriesPath = readableFile(own) ? own : workspaceFallback();
      if (!categoriesPath) return null;
      return { skill_root: root, personas_dir: personasDir, categories_path: categoriesPath, resolved_from: resolvedFrom };
    };

    const direct = nonEmpty(env.BOOK_TO_PERSONA_ROOT);
    if (direct) {
      const hit = check(direct, 'env:BOOK_TO_PERSONA_ROOT');
      if (hit) return hit;
    }
    for (const name of ['OPENCLAW_SKILLS_DIR', 'OC_SKILLS_DIR'] as const) {
      const dir = nonEmpty(env[name]);
      if (!dir) continue;
      const hit = check(join(dir, BOOK_TO_PERSONA_FOLDER), 'env:OPENCLAW_SKILLS_DIR');
      if (hit) return hit;
    }
    try {
      for (const dir of discoverHostLayout({ homeDir: home, env }).extraSkillDirs) {
        const hit = check(join(dir, BOOK_TO_PERSONA_FOLDER), 'host_layout_skill_dir');
        if (hit) return hit;
      }
    } catch {
      /* ambiguous or malformed host layout: fall through to the default */
    }
    return check(join(home, '.openclaw', 'skills', BOOK_TO_PERSONA_FOLDER), 'openclaw_default');
  } catch {
    return null;
  }
}

export interface LivePersonaInventory {
  /**
   * `found` means a store was resolved. `unreadable` is set (with the error
   * class name, never a path) when it was resolved but could not be read, so
   * a broken store is never reported as a missing one.
   */
  root: { resolved_from: string; found: boolean; unreadable?: true; error?: string };
  seats: Array<{
    seat_id: SeatId;
    layer: 'live_book_to_persona' | 'shipped_brief_fallback';
    personas: Array<{ key: string; book: string; content_level: string }>;
  }>;
}

/**
 * A seat is live only when at least one of its personas has a
 * persona-blueprint.md on disk; a registry entry with no files (or only
 * side notes) cannot brief an elder, so the shipped brief stays in force.
 */
export function inventoryLivePersonas(opts: PersonaRootOptions = {}): LivePersonaInventory {
  const fallbackSeats = (): LivePersonaInventory['seats'] =>
    SEAT_ROSTER.map((s) => ({ seat_id: s.seat_id, layer: 'shipped_brief_fallback' as const, personas: [] }));
  const root = resolveBookToPersonaRoot(opts);
  if (!root) return { root: { resolved_from: 'none', found: false }, seats: fallbackSeats() };

  try {
    const inv = inventoryCouncilSkill22Personas(root.skill_root, root.categories_path);
    return {
      root: { resolved_from: root.resolved_from, found: true },
      seats: inv.seats.map((seat) => ({
        seat_id: seat.seat_id,
        layer: seat.existing_personas.some(
          (p) => p.content_level === 'extraction_and_blueprint' || p.content_level === 'blueprint_only',
        )
          ? ('live_book_to_persona' as const)
          : ('shipped_brief_fallback' as const),
        personas: seat.existing_personas.map((p) => ({ key: p.key, book: p.book, content_level: p.content_level })),
      })),
    };
  } catch (e) {
    return {
      root: { resolved_from: root.resolved_from, found: true, unreadable: true, error: e instanceof Error ? e.name : 'Error' },
      seats: fallbackSeats(),
    };
  }
}
