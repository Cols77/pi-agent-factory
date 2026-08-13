# SP-B Health Projection Performance Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the SP-B `/system` health landing responsive for product-scale repositories without persistent caching or browser-side projection logic.

**Architecture:** Build a request-scoped `ArtifactLookup` once from loaded trace nodes and ADRs, then pass it through coverage, ordering, membership, health, and traversal operations. Add a Promise-based CLI runner for the health/traversal routes so one slow Python command cannot block Node's event loop and starve the health response.

**Tech Stack:** Python 3.11–3.12, pytest, TypeScript/Node.js, Vitest.

---

## File structure

**Modified:**

| File | Responsibility |
|---|---|
| `src/factory/system/coverage.py` | Build and resolve a request-scoped artifact lookup; reuse it during coverage. |
| `src/factory/system/bundles.py` | Reuse an optional lookup during membership scans. |
| `src/factory/system/ordering.py` | Reuse an optional lookup while calculating member recency. |
| `src/factory/system/health.py` | Build one lookup and share it across health projection dependencies. |
| `src/factory/system/queries.py` | Reuse already-loaded nodes/lookup through traversal aggregation. |
| `tests/unit/system/test_coverage.py` | Prove a multi-member coverage request loads trace nodes once. |
| `tests/unit/system/test_health.py` | Prove the health projection shares one lookup. |
| `tests/unit/system/test_queries.py` | Prove traversal shares its lookup across SR membership checks. |
| `pi-ext/factory-watch/src/cli-runner.ts` | Add Promise-based JSON CLI execution. |
| `pi-ext/factory-watch/src/system-cli.ts` | Expose async health/traversal loaders. |
| `pi-ext/factory-watch/src/docs-server.ts` | Await health/traversal subprocesses without blocking other requests. |
| `pi-ext/factory-watch/test/cli-runner.test.ts` | Cover async runner success/failure/invalid JSON/launch error. |
| `pi-ext/factory-watch/test/system-page.test.ts` | Cover async health/traversal routes and concurrent response behaviour. |

### Task 1: Request-scoped artifact lookup for Python projection work

**Files:**
- Modify: `src/factory/system/coverage.py:49-112`
- Modify: `src/factory/system/bundles.py:195-216`
- Modify: `src/factory/system/ordering.py:53-82`
- Modify: `src/factory/system/health.py:140-190`
- Modify: `src/factory/system/queries.py:1283-1388`
- Test: `tests/unit/system/test_coverage.py`
- Test: `tests/unit/system/test_health.py`
- Test: `tests/unit/system/test_queries.py`

- [ ] **Step 1: Write failing coverage regression test**

  Add this test next to the existing coverage tests. It must patch the loader after fixtures are
  written, exercise multiple `sr:`/`task:` members, and assert a single full node load:

  ```python
  def test_bundle_coverage_loads_nodes_once_for_many_members(tmp_path, monkeypatch):
      _write_sr(tmp_path, "SR-001", binding=True)
      _write_sr(tmp_path, "SR-002", binding=True)
      _write_task_satisfying(tmp_path, "T-001", "SR-001")
      _write_task_satisfying(tmp_path, "T-002", "SR-002")
      (tmp_path / "bundles").mkdir()
      (tmp_path / "bundles" / "all.json").write_text(
          '{"id":"all","label":"All","members":['
          '"sr:SR-001","sr:SR-002","task:T-001","task:T-002"]}',
          encoding="utf-8",
      )
      original = coverage.trace_model.load_nodes
      calls = 0

      def counted(root):
          nonlocal calls
          calls += 1
          return original(root)

      monkeypatch.setattr(coverage.trace_model, "load_nodes", counted)
      result = coverage.bundle_coverage(tmp_path)
      assert result.bundled == 4
      assert calls == 1
  ```

- [ ] **Step 2: Run the new test and verify RED**

  Run: `uv run python -m pytest tests/unit/system/test_coverage.py::test_bundle_coverage_loads_nodes_once_for_many_members -q`

  Expected: FAIL because the current implementation calls `trace_model.load_nodes` once for
  artifact collection plus once per `sr:`/`task:` bundle member.

- [ ] **Step 3: Implement the lookup with compatibility-preserving signatures**

  In `coverage.py`, add an immutable local lookup type and helpers. Its maps contain exact
  references and resolved paths from the supplied/load-once nodes and ADRs:

  ```python
  @dataclass(frozen=True)
  class ArtifactLookup:
      targets: dict[str, Path]


  def build_artifact_lookup(
      repo_root: Path, *, nodes: list[trace_model.Node] | None = None
  ) -> ArtifactLookup:
      resolved_nodes = trace_model.load_nodes(repo_root) if nodes is None else nodes
      targets: dict[str, Path] = {}
      for node in resolved_nodes:
          if node.kind in ("sr", "task"):
              targets[f"{node.kind}:{node.id}"] = node.path.resolve()
          elif node.kind in ("spec", "plan"):
              relative = node.path.relative_to(repo_root).as_posix()
              targets[f"{node.kind}:{relative}"] = node.path.resolve()
      for adr_id, doc in adr_module.load_adrs(repo_root).items():
          targets[f"adr:{adr_id}"] = doc.path.resolve()
      return ArtifactLookup(targets=targets)


  def member_target(
      repo_root: Path, member_ref: str, lookup: ArtifactLookup | None = None
  ) -> Path | None:
      if lookup is not None:
          return lookup.targets.get(member_ref)
      return build_artifact_lookup(repo_root).targets.get(member_ref)
  ```

  Refactor `_artifacts` and `bundle_coverage` to accept the same optional `lookup`, construct
  one when omitted, and use only `lookup.targets` in their loops. Keep the existing public
  result shape/order unchanged.

  Update `bundles_containing(repo_root, ref, lookup=None)` to use the passed lookup for the
  target and each member. Update `ordered_bundle_ids(repo_root, recency_source, lookup=None)`
  to pass `lookup` to `member_target`. In `query_health`, build exactly one lookup and pass it
  to `bundle_coverage` and `ordered_bundle_ids`. In `query_traversal`, call
  `build_artifact_lookup(repo_root, nodes=nodes)` once and thread it through
  `_traversal_for_sr` into `bundles_containing`.

- [ ] **Step 4: Run the coverage test and verify GREEN**

  Run: `uv run python -m pytest tests/unit/system/test_coverage.py::test_bundle_coverage_loads_nodes_once_for_many_members -q`

  Expected: PASS.

- [ ] **Step 5: Add sharing tests for health and traversal**

  Add tests that monkeypatch the public dependent functions rather than timing filesystem
  operations. The health test asserts the identical `ArtifactLookup` instance received by
  `bundle_coverage` and `ordered_bundle_ids`; the traversal test asserts its repeated
  `bundles_containing` calls receive one identical lookup:

  ```python
  def test_query_health_shares_one_artifact_lookup(tmp_path, monkeypatch):
      from factory.system.coverage import Coverage
      from factory.system.ordering import FixedRecency

      _write_sr(tmp_path, "SR-001", binding=True)
      _write_bundle(tmp_path, "b1", ["sr:SR-001"])
      seen = []
      original_coverage = health.bundle_coverage
      original_order = health.ordered_bundle_ids

      def capture_coverage(root, *, lookup=None):
          seen.append(lookup)
          return original_coverage(root, lookup=lookup)

      def capture_order(root, source, *, lookup=None):
          seen.append(lookup)
          return original_order(root, source, lookup=lookup)

      monkeypatch.setattr(health, "bundle_coverage", capture_coverage)
      monkeypatch.setattr(health, "ordered_bundle_ids", capture_order)
      health.query_health(tmp_path, recency_source=FixedRecency({}))
      assert len(seen) == 2
      assert seen[0] is seen[1]


  def test_traversal_reuses_one_lookup_for_bundle_members(tmp_path, monkeypatch):
      write_sr(tmp_path / "requirements", "SR-001")
      write_sr(tmp_path / "requirements", "SR-002")
      _write_task_traversal(tmp_path, "T-001", "SR-001", "2026-08-12-P.md")
      _write_task_traversal(tmp_path, "T-002", "SR-002", "2026-08-12-P.md")
      write_bundle(tmp_path / "bundles", "b1", "B1", ["sr:SR-001", "sr:SR-002"])
      seen = []
      original = queries.bundles.bundles_containing

      def capture(root, ref, *, lookup=None):
          seen.append(lookup)
          return original(root, ref, lookup=lookup)

      monkeypatch.setattr(queries.bundles, "bundles_containing", capture)
      query_traversal(tmp_path, parse_scope_ref("bundle:b1"))
      assert len(seen) == 2
      assert seen[0] is seen[1]
  ```

  Use the existing fixture helpers and real health/trace objects from their respective files;
  do not add test-only production APIs.

- [ ] **Step 6: Run focused Python tests**

  Run: `uv run python -m pytest tests/unit/system/test_coverage.py tests/unit/system/test_bundles.py tests/unit/system/test_health.py tests/unit/system/test_queries.py -q`

  Expected: PASS.

- [ ] **Step 7: Commit the Python projection repair**

  ```bash
  git add src/factory/system/coverage.py src/factory/system/bundles.py src/factory/system/ordering.py src/factory/system/health.py src/factory/system/queries.py tests/unit/system/test_coverage.py tests/unit/system/test_health.py tests/unit/system/test_queries.py
  git commit -m "fix(system): reuse artifact lookup in health projections"
  ```

### Task 2: Asynchronous health and traversal CLI routes

**Files:**
- Modify: `pi-ext/factory-watch/src/cli-runner.ts:1-42`
- Modify: `pi-ext/factory-watch/src/system-cli.ts:239-255`
- Modify: `pi-ext/factory-watch/src/docs-server.ts:203-290,496`
- Test: `pi-ext/factory-watch/test/cli-runner.test.ts`
- Test: `pi-ext/factory-watch/test/system-page.test.ts`

- [ ] **Step 1: Write failing async runner tests**

  Extend the child-process mock to export `spawn` alongside `spawnSync`. Add tests that make a
  fake child process emit `stdout`, `stderr`, `error`, and `close`, then assert the Promise-based
  runner has the existing `CliResult` outcomes:

  ```ts
  test("parses asynchronous CLI stdout into a value", async () => {
    spawn.mockReturnValue(childThatCloses(0, JSON.stringify({ health: {} }), ""));
    await expect(runJsonCliAsync<{ health: object }>("/repo", "uv", SUB))
      .resolves.toEqual({ ok: true, value: { health: {} } });
  });

  test("reports asynchronous CLI launch errors", async () => {
    spawn.mockReturnValue(childThatErrors(new Error("spawn uv ENOENT")));
    await expect(runJsonCliAsync("/repo", "uv", SUB)).resolves.toMatchObject({
      ok: false, error: expect.stringContaining("ENOENT"),
    });
  });
  ```

  Cover non-zero exit and invalid JSON with the same fake child helper.

- [ ] **Step 2: Run the new runner tests and verify RED**

  Run: `npx vitest run test/cli-runner.test.ts`

  Expected: FAIL because `runJsonCliAsync` does not exist.

- [ ] **Step 3: Implement `runJsonCliAsync`**

  Import `spawn` and `ChildProcess` from `node:child_process`. Implement a Promise that captures
  UTF-8 stdout/stderr chunks, resolves once on `error` or `close`, and delegates successful
  parsing/error wording to a shared pure `parseJsonCliResult` helper used by both sync and async
  variants. Invoke:

  ```ts
  spawn(bin, args, { cwd, stdio: ["ignore", "pipe", "pipe"] });
  ```

  Do not throw from async execution; preserve `{ ok: false, error }` and the current 64 MiB
  practical output limit by stopping collection and resolving an error if either stream exceeds
  `64 * 1024 * 1024` bytes.

- [ ] **Step 4: Run runner tests and verify GREEN**

  Run: `npx vitest run test/cli-runner.test.ts`

  Expected: PASS.

- [ ] **Step 5: Write failing docs-server async route tests**

  In `system-page.test.ts`, mock `spawn` so a `traversal` child remains open until the test
  releases it, while a `health` child immediately writes valid health JSON and closes. Start the
  traversal fetch without awaiting it, then assert the health fetch resolves to 200 before
  releasing traversal:

  ```ts
  test("serves health while traversal is still running", async () => {
    const held = deferredChildProcess();
    spawn.mockImplementation((_bin: string, args: string[]) => {
      if (args[4] === "traversal") return held.child;
      if (args[4] === "health") return childThatCloses(0, JSON.stringify(HEALTH), "");
      throw new Error(`unexpected subcommand: ${String(args[4])}`);
    });
    const server = await ensureDocsServer(repo());
    const traversal = fetch(`${server.url}/api/system/traversal?scope=bundle:one`);
    const health = await fetch(`${server.url}/api/system/health`);
    expect(health.status).toBe(200);
    expect(await health.json()).toEqual(HEALTH);
    held.close(0, JSON.stringify(TRAVERSAL), "");
    expect((await traversal).status).toBe(200);
  });
  ```

  Add direct tests that `/api/system/health` and `/api/system/traversal` return their JSON via
  async loader success and return 503 for an async non-zero CLI result.

- [ ] **Step 6: Run route tests and verify RED**

  Run: `npx vitest run test/system-page.test.ts`

  Expected: FAIL because the routes still call synchronous loaders and block the server.

- [ ] **Step 7: Implement asynchronous health/traversal loading and awaiting routes**

  In `system-cli.ts`, export:

  ```ts
  export function loadSystemHealthAsync(cwd: string): Promise<CliResult<SystemHealth>> {
    const cmd = buildSystemCommand(["health", "--json"]);
    return runJsonCliAsync<SystemHealth>(cwd, cmd.bin, cmd.args);
  }

  export function loadSystemTraversalAsync(cwd: string, scope: string): Promise<CliResult<SystemTraversal>> {
    const cmd = buildSystemCommand(["traversal", "--json", "--scope", scope]);
    return runJsonCliAsync<SystemTraversal>(cwd, cmd.bin, cmd.args);
  }
  ```

  Change `handle` in `docs-server.ts` to `async`, await only these two loaders, and make the
  server callback explicitly discard/reject-handle its returned Promise:

  ```ts
  const server = createServer((req, res) => {
    void handle(normalizedCwd, req, res).catch((err) => {
      if (!res.headersSent) json(res, 500, { error: String(err) });
      else res.end();
    });
  });
  ```

  Leave all remaining endpoint calls synchronous in this increment.

- [ ] **Step 8: Run TypeScript tests and typecheck**

  Run: `npx vitest run test/cli-runner.test.ts test/system-page.test.ts && npx tsc --noEmit`

  Expected: PASS.

- [ ] **Step 9: Commit the async docs-server repair**

  ```bash
  git add pi-ext/factory-watch/src/cli-runner.ts pi-ext/factory-watch/src/system-cli.ts pi-ext/factory-watch/src/docs-server.ts pi-ext/factory-watch/test/cli-runner.test.ts pi-ext/factory-watch/test/system-page.test.ts
  git commit -m "fix(system): keep health route responsive during traversal"
  ```

### Task 3: Full verification and live browser validation

**Files:** No source changes expected.

- [ ] **Step 1: Run Python gate and lint**

  Run: `uv run python -m pytest -q -m 'unit or integration' && uv run python -m ruff check .`

  Expected: PASS with no lint violations.

- [ ] **Step 2: Run complete extension suite and typecheck**

  Run: `npx vitest run && npx tsc --noEmit`

  Working directory: `pi-ext/factory-watch`

  Expected: PASS.

- [ ] **Step 3: Smoke the real product health command**

  Run: `uv run python -m factory.system health --json`

  Working directory: `C:\coding\cool_physical_ai_project`

  Expected: JSON output containing `health`, `coverage`, `bundles`, `unbundled`, and
  `sr_listed: false`, without timing out.

- [ ] **Step 4: Use browser automation against the live `/system` page**

  Open the extension-provided `/system` URL and verify, from a fresh DOM snapshot and screenshot:
  `#content` is visible, `#healthSummary` has text, and `#scopeList` contains at least one
  readiness group or the explicitly rendered empty state. Record browser console errors if any.

- [ ] **Step 5: Commit plan checkbox updates if changed**

  ```bash
  git add docs/superpowers/plans/2026-08-13-spb-health-performance.md
  git commit -m "docs(system): record SP-B health repair verification"
  ```
