import { describe, expect, test } from "vitest";
import {
  MEMORY_DEFAULTS,
  addNote,
  buildMemoryRollup,
  emptyMemory,
  enforceCap,
  makeNote,
  nextId,
  pruneExpired,
  supersedeTopic,
} from "../src/session-memory.js";

const cfg = { ...MEMORY_DEFAULTS };
const T0 = "2026-08-09T10:00:00.000Z";

function note(topic: string, text: string, createdAt: string) {
  return makeNote(emptyMemory(), { topic, text, actor: "test", created: createdAt }, cfg, createdAt);
}

describe("session-memory store", () => {
  test("nextId is gap-filling and deterministic", () => {
    expect(nextId(emptyMemory())).toBe("sm-0001");
    const file = { schema: 1, entries: [note("a", "x", T0)] };
    expect(nextId(file)).toBe("sm-0002");
    // gap: an id that skips sm-0002 stays unused, but next fills the lowest free
    const gapped = {
      schema: 1,
      entries: [note("a", "x", T0), { ...note("b", "y", T0), id: "sm-0003" }],
    };
    expect(nextId(gapped)).toBe("sm-0002");
  });

  test("pruneExpired drops only entries whose expiry has passed", () => {
    const fresh = note("t1", "still valid", T0); // default ttl 24h -> expires T0+24h
    const older = { ...note("t2", "old", "2026-08-01T00:00:00.000Z"), expires: "2026-08-02T00:00:00.000Z" };
    const now = "2026-08-09T11:00:00.000Z";
    const out = pruneExpired({ schema: 1, entries: [fresh, older] }, now);
    expect(out.entries.map((e) => e.topic)).toEqual(["t1"]);
  });

  test("supersedeTopic retires the live entry sharing the topic", () => {
    const first = note("task:T-042", "on dev", T0);
    const file = { schema: 1, entries: [first] };
    const now = "2026-08-09T12:00:00.000Z";
    const out = supersedeTopic(file, "task:T-042", now);
    expect(out.entries).toHaveLength(0);
  });

  test("addNote writes and supersedes, and persists the retired id for audit", () => {
    let file = emptyMemory();
    const now1 = "2026-08-09T10:00:00.000Z";
    file = addNote(file, { topic: "task:T-042", text: "on dev", actor: "a" }, cfg, now1);
    expect(file.entries).toHaveLength(1);
    const firstId = file.entries[0]!.id;
    const now2 = "2026-08-09T12:00:00.000Z";
    file = addNote(file, { topic: "task:T-042", text: "validation next", actor: "a" }, cfg, now2);
    // old superseded, one live entry remains, and it records what it replaced
    expect(file.entries).toHaveLength(1);
    expect(file.entries[0]!.text).toBe("validation next");
    expect(file.entries[0]!.supersedes).toBe(firstId);
  });

  test("enforceCap keeps the newest entries by created", () => {
    let file = emptyMemory();
    const times = ["2026-08-09T10:00:00.000Z", "2026-08-09T11:00:00.000Z", "2026-08-09T12:00:00.000Z"];
    times.forEach((t, i) => {
      file = addNote(file, { topic: `t${i}`, text: `n${i}`, actor: "a", created: t }, cfg, t);
    });
    const capped = enforceCap(file, 2);
    expect(capped.entries).toHaveLength(2);
    expect(capped.entries.map((e) => e.text).sort()).toEqual(["n1", "n2"]);
  });

  test("addNote composes supersede + prune + cap correctly over time", () => {
    let file = emptyMemory();
    file = addNote(file, { topic: "t1", text: "work A", actor: "a", created: T0 }, cfg, T0);
    const later = "2026-08-10T15:00:00.000Z"; // >24h later
    file = addNote(file, { topic: "t1", text: "work B", actor: "a" }, cfg, later);
    // adding the new note (and pruning at its now) must drop the expired old one
    expect(file.entries.map((e) => e.text)).toEqual(["work B"]);
  });
});

describe("session-memory rollup (forward injection)", () => {
  test("returns null for empty or fully-expired store", () => {
    expect(buildMemoryRollup(emptyMemory(), T0, cfg)).toBeNull();
    const dead = { schema: 1, entries: [{ ...note("t", "x", T0), expires: "2026-08-08T00:00:00.000Z" }] };
    expect(buildMemoryRollup(dead, T0, cfg)).toBeNull();
  });

  test("renders a bounded, as-of-dated rollup of fresh notes oldest-first", () => {
    let file = emptyMemory();
    file = addNote(file, { topic: "task:T-042", text: "validation next", actor: "a", created: T0 }, cfg, T0);
    file = addNote(
      file,
      { topic: "decision:audit-log", text: "keep prune silent on shutdown", actor: "b" },
      cfg,
      "2026-08-09T11:00:00.000Z",
    );
    const rollup = buildMemoryRollup(file, "2026-08-09T12:00:00.000Z", cfg);
    expect(rollup).not.toBeNull();
    expect(rollup).toContain("task:T-042");
    expect(rollup).toContain("decision:audit-log");
    // oldest first
    expect(rollup!.indexOf("task:T-042")).toBeLessThan(rollup!.indexOf("decision:audit-log"));
    // never injects an expired note
    const stale = { ...note("old", "stale", T0), expires: "2026-08-08T00:00:00.000Z" };
    const withStale = buildMemoryRollup({ schema: 1, entries: [stale] }, T0, cfg);
    expect(withStale).toBeNull();
  });

  test("respects the token budget on the rollup", () => {
    let file = emptyMemory();
    for (let i = 0; i < 30; i++) {
      file = addNote(
        file,
        { topic: `t${i}`, text: `note number ${i} with some padding words to fill the budget ${"x".repeat(40)}`, actor: "a", created: T0 },
        cfg,
        T0,
      );
    }
    const rollup = buildMemoryRollup(file, T0, cfg)!;
    expect(rollup.length / 4).toBeLessThanOrEqual(cfg.maxTokens * 1.5);
  });
});
