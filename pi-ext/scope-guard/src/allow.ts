import { minimatch } from "minimatch";

export function parseAllow(raw: string | undefined): string[] {
  if (!raw) return [];
  return raw
    .split(",")
    .map((s) => s.trim())
    .filter((s) => s.length > 0);
}

function normalize(p: string): string {
  return p.replace(/\\/g, "/");
}

export function toRepoRelative(p: string, cwd: string): string {
  const np = normalize(p);
  const nc = normalize(cwd).replace(/\/+$/, "");
  let rel = np;
  if (np.toLowerCase().startsWith(nc.toLowerCase() + "/")) {
    rel = np.slice(nc.length + 1);
  }
  return rel.replace(/^\/+/, "");
}

export function isPathAllowed(p: string, cwd: string, globs: string[]): boolean {
  if (globs.length === 0) return false;
  const rel = toRepoRelative(p, cwd);
  return globs.some((g) => minimatch(rel, g, { dot: true }));
}
