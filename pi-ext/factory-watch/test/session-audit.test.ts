import { existsSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, test } from "vitest";
import {
  AUDIT_CAP_DEFAULT,
  appendAudit,
  capAudit,
  emptyAudit,
  readAudit,
  recentAudit,
  removedNotes,
  writeAudit,
} from "../src/session-audit.js";
import { addNote, emptyMemory, memoryPath, writeMemory, MEMORY_DEFAULTS } from "../src/session-memory.js";

const dirs: string[] = [];
afterEach(() => {
  for (const d of dirs.splice(0)) rmSync(d, { recursive: true, force: true });
});
function makeDir(): string {
  const d = mkdtempSync(join(tmpdir(), "pif-audit-"));
  dirs.push(d);
  return d;
}
function noteObj(id: string, topic: string, created: string) {
  return {
    id, kind: "log" as const, topic, created, expires: "2099-01-01T00:00:00.000Z",
    actor: "t", text: `text-${id}`, supersedes: null,
  };
}

describe("session-audit store", () => {
  test("empty audit round-trips to disk", () => {
    const root = makeDir();
    writeAudit(root, emptyAudit());
    expect(readAudit(root).entries).toEqual([]);
    expect(existsSync(join(root, ".pi", "factory", "session-memory-audit.json"))).toBe(true);
  });

  test("appendAudit stamps pruned_at + reason and keeps entries", () => {
    const file = appendAudit(
      emptyAudit(),
      [{ note: noteObj("sm-1", "task:T-1", "2026-08-14T09:00:00.000Z"), reason: "superseded" }],
      "2026-08-14T10:00:00.000Z",
      AUDIT_CAP_DEFAULT,
    );
    expect(file.entries).toHaveLength(1);
    expect(file.entries[0]!.reason).toBe("superseded");
    expect(file.entries[0]!.pruned_at).toBe("2026-08-14T10:00:00.000Z");
  });

  test("capAudit keeps the newest prunes", () => {
    let file = emptyAudit();
    for (let i = 0; i < 5; i++) {
      file = appendAudit(
        file,
        [{ note: noteObj(`sm-${i}`, `t${i}`, `2026-08-14T0${i}:00:00.000Z`), reason: "capped" }],
        `2026-08-14T10:0${i}:00.000Z`,
        3,
      );
    }
    const capped = capAudit(file, 3);
    expect(capped.entries).toHaveLength(3);
    expect(capped.entries.map((e) => e.id).sort()).toEqual(["sm-2", "sm-3", "sm-4"]);
  });

  test("removedNotes diffs by id", () => {
    const before = [noteObj("a", "t1", "x"), noteObj("b", "t2", "x")];
    const after = [noteObj("b", "t2", "x")];
    expect(removedNotes(before, after).map((e) => e.id)).toEqual(["a"]);
  });

  test("recentAudit returns newest-first", () => {
    const older = appendAudit(
      emptyAudit(), [{ note: noteObj("a", "t1", "x"), reason: "capped" }],
      "2026-08-14T09:00:00.000Z", 10,
    );
    const file = appendAudit(older, [{ note: noteObj("b", "t2", "x"), reason: "expired" }], "2026-08-14T11:00:00.000Z", 10);
    expect(recentAudit(file, 2)[0]!.id).toBe("b");
  });
});

describe("audit integration with the memory store", () => {
  test("supersede in the store maps to the removed note (audit-relevant)", () => {
    const root = makeDir();
    let mem = emptyMemory();
    mem = addNote(mem, { topic: "task:T-42", text: "on dev", actor: "a" }, MEMORY_DEFAULTS, "2026-08-14T09:00:00.000Z");
    writeMemory(root, mem);
    expect(existsSync(memoryPath(root))).toBe(true);

    const before = mem.entries;
    const next = addNote(mem, { topic: "task:T-42", text: "validation", actor: "a" }, MEMORY_DEFAULTS, "2026-08-14T10:00:00.000Z");
    const removed = removedNotes(before, next.entries);
    expect(before).toHaveLength(1);
    expect(next.entries[0]!.supersedes).toBe(before[0]!.id);
    expect(removed.map((e) => e.id)).toEqual([before[0]!.id]);
  });
});
