import { spawnSync } from "node:child_process";

export interface FileStat {
  path: string;
  status: "A" | "M" | "D";
  added: number;
  removed: number;
}

export function parseDiffStat(numstatOutput: string): FileStat[] {
  const entries: FileStat[] = [];
  for (const line of numstatOutput.split("\n")) {
    if (line.trim() === "") {
      continue;
    }
    const parts = line.split("\t");
    const added = parts[0] ?? "0";
    const removed = parts[1] ?? "0";
    const path = parts[2] ?? "";
    entries.push({ path, status: "M", added: Number(added), removed: Number(removed) });
  }
  return entries;
}

function parseNameStatus(nameStatusOutput: string): Map<string, "A" | "M" | "D"> {
  const statuses = new Map<string, "A" | "M" | "D">();
  for (const line of nameStatusOutput.split("\n")) {
    if (line.trim() === "") {
      continue;
    }
    const parts = line.split("\t");
    const code = parts[0] ?? "";
    const path = parts[1] ?? "";
    const normalized = code.startsWith("A") ? "A" : code.startsWith("D") ? "D" : "M";
    statuses.set(path, normalized);
  }
  return statuses;
}

export function computeReviewFiles(cwd: string, startCommit: string): FileStat[] {
  const numstat = spawnSync("git", ["diff", "--numstat", `${startCommit}..HEAD`], {
    cwd, encoding: "utf-8",
  });
  const nameStatus = spawnSync("git", ["diff", "--name-status", `${startCommit}..HEAD`], {
    cwd, encoding: "utf-8",
  });
  const statuses = parseNameStatus(nameStatus.stdout);
  return parseDiffStat(numstat.stdout).map((entry) => ({
    ...entry,
    status: statuses.get(entry.path) ?? entry.status,
  }));
}

export function computeFileDiffText(cwd: string, startCommit: string, file: string): string {
  const result = spawnSync("git", ["diff", `${startCommit}..HEAD`, "--", file], {
    cwd, encoding: "utf-8",
  });
  return result.stdout;
}
