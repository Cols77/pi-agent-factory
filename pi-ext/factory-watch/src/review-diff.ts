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
  // A single-ref diff (`git diff <ref>`, no `..HEAD`) compares that ref to
  // the current working tree, not just to HEAD -- so this picks up both
  // committed changes since start_commit AND uncommitted working-tree
  // changes. The human-review gate runs before dev's work is committed
  // (runner.py only calls git_ops.commit_all after the human approves), so
  // `{startCommit}..HEAD` would silently report zero files here. This
  // mirrors the working-tree semantics of git_ops.changed_files in
  // src/factory/orchestrator/git_ops.py.
  const numstat = spawnSync("git", ["diff", "--numstat", startCommit], {
    cwd, encoding: "utf-8",
  });
  const nameStatus = spawnSync("git", ["diff", "--name-status", startCommit], {
    cwd, encoding: "utf-8",
  });
  const statuses = parseNameStatus(nameStatus.stdout);
  return parseDiffStat(numstat.stdout).map((entry) => ({
    ...entry,
    status: statuses.get(entry.path) ?? entry.status,
  }));
}

// The "implementing diff" for an already-done task: for each deliverable, the
// last commit that touched it (that file only). Used instead of the
// start_commit..working-tree range, which is empty when the work was committed
// before the run started.
export function computeImplementingFiles(cwd: string, deliverables: string[]): FileStat[] {
  const out: FileStat[] = [];
  for (const file of deliverables) {
    // -1: last commit touching the path; --format= : suppress the commit header.
    const numstat = spawnSync(
      "git", ["log", "-1", "--numstat", "--format=", "--", file],
      { cwd, encoding: "utf-8" },
    );
    const nameStatus = spawnSync(
      "git", ["log", "-1", "--name-status", "--format=", "--", file],
      { cwd, encoding: "utf-8" },
    );
    const statuses = parseNameStatus(nameStatus.stdout);
    for (const entry of parseDiffStat(numstat.stdout)) {
      out.push({ ...entry, status: statuses.get(entry.path) ?? entry.status });
    }
  }
  return out;
}

export function computeImplementingFileDiffText(cwd: string, file: string): string {
  const result = spawnSync(
    "git", ["log", "-1", "-p", "--format=", "--", file],
    { cwd, encoding: "utf-8" },
  );
  return result.stdout;
}

export function computeFileDiffText(cwd: string, startCommit: string, file: string): string {
  // See computeReviewFiles above: single-ref diff against the working tree,
  // not `{startCommit}..HEAD`, so uncommitted dev changes show up.
  const result = spawnSync("git", ["diff", startCommit, "--", file], {
    cwd, encoding: "utf-8",
  });
  return result.stdout;
}
