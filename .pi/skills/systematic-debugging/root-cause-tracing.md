# Root Cause Tracing

## Overview

Bugs often manifest deep in the call stack. Your instinct is to fix where the error appears, but that's treating a symptom.

**Core principle:** Trace backward through the call chain until you find the original trigger, then fix at the source.

## When to Use

Use when: error happens deep in execution (not at entry point), the stack trace shows a long call chain, it's unclear where invalid data originated, or you need to find which test/code triggers the problem.

If you can trace backwards, do so and fix at the original trigger. If you hit a dead end, fix at the symptom point but flag it as such — and prefer to also add defense-in-depth (see `defense-in-depth.md`) rather than relying on the symptom fix alone.

## The Tracing Process

### 1. Observe the Symptom
```
Error: git init failed in ~/project/packages/core
```

### 2. Find Immediate Cause
**What code directly causes this?**
```typescript
await execFileAsync('git', ['init'], { cwd: projectDir });
```

### 3. Ask: What Called This?
```
WorktreeManager.createSessionWorktree(projectDir, sessionId)
  -> called by Session.initializeWorkspace()
  -> called by Session.create()
  -> called by test at Project.create()
```

### 4. Keep Tracing Up
**What value was passed?**
- `projectDir = ''` (empty string!)
- Empty string as `cwd` resolves to `process.cwd()`
- That's the source code directory!

### 5. Find Original Trigger
**Where did the empty string come from?**
```typescript
const context = setupCoreTest(); // Returns { tempDir: '' }
Project.create('name', context.tempDir); // Accessed before beforeEach!
```

## Adding Stack Traces

When you can't trace manually, add instrumentation before the problematic operation:

```typescript
async function gitInit(directory: string) {
  const stack = new Error().stack;
  console.error('DEBUG git init:', {
    directory,
    cwd: process.cwd(),
    stack,
  });
  await execFileAsync('git', ['init'], { cwd: directory });
}
```

**Critical:** log before the dangerous operation, not after it fails. Include directory, cwd, environment, and a captured stack trace (`new Error().stack`).

## Real Example: Empty projectDir

**Symptom:** `.git` created in `packages/core/` (source code)

**Trace chain:**
1. `git init` runs in `process.cwd()` <- empty cwd parameter
2. WorktreeManager called with empty projectDir
3. Session.create() passed an empty string
4. Test accessed `context.tempDir` before beforeEach
5. setupCoreTest() returns `{ tempDir: '' }` initially

**Root cause:** top-level variable initialization accessing an empty value.

**Fix:** made tempDir a getter that throws if accessed before beforeEach.

**Also added defense-in-depth:**
- Layer 1: Project.create() validates the directory
- Layer 2: WorkspaceManager validates not empty
- Layer 3: environment guard refuses git init outside tmpdir
- Layer 4: stack trace logging before git init

## Key Principle

**NEVER fix just where the error appears.** Trace back to find the original trigger, fix at the source, then add validation at each layer the bad value passed through so the bug becomes structurally impossible, not just patched once.
