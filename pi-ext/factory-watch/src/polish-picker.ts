// Pure parsing + formatting for the polish playground/usecase selection menu.
// The JSON contract is produced by `factory polish list --json`; nothing here
// shells out or touches ctx -- callers (index.ts /polish) own the subprocess
// and the ctx.ui.select calls.

export interface PolishPlayground {
  playground: string;
  usecases: string[];
}

/**
 * Parse the `factory polish list --json` output into playground groups.
 * Returns null on malformed JSON or a shape that doesn't match the contract,
 * an empty array for an empty list, or the groups otherwise.
 */
export function parsePolishGroupList(raw: string): PolishPlayground[] | null {
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return null;
  }
  if (!Array.isArray(parsed)) return null;
  const out: PolishPlayground[] = [];
  for (const item of parsed) {
    if (typeof item !== "object" || item === null) return null;
    const pg = item as Record<string, unknown>;
    if (typeof pg.playground !== "string" || !Array.isArray(pg.usecases)) return null;
    if (!pg.usecases.every((u) => typeof u === "string")) return null;
    out.push({ playground: pg.playground, usecases: pg.usecases as string[] });
  }
  return out;
}

/** Menu label for a playground, e.g. `sim-live (11 usecases)`. */
export function polishPlaygroundLabel(pg: PolishPlayground): string {
  const n = pg.usecases.length;
  return `${pg.playground} (${n} usecase${n === 1 ? "" : "s"})`;
}

/** Recover the playground id from a label produced by polishPlaygroundLabel. */
export function parsePlaygroundIdFromLabel(label: string): string | null {
  const match = /^([A-Za-z0-9_-]+)/.exec(label.trim());
  return match ? match[1]! : null;
}
