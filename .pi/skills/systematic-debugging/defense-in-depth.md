# Defense-in-Depth Validation

## Overview

When you fix a bug caused by invalid data, adding validation at one place feels sufficient. But that single check can be bypassed by different code paths, refactoring, or mocks.

**Core principle:** Validate at EVERY layer data passes through. Make the bug structurally impossible.

## Why Multiple Layers

Single validation: "We fixed the bug." Multiple layers: "We made the bug impossible."

Different layers catch different cases: entry validation catches most bugs, business logic catches edge cases, environment guards prevent context-specific dangers, debug logging helps when other layers fail.

## The Four Layers

### Layer 1: Entry Point Validation
**Purpose:** reject obviously invalid input at the API boundary.
```typescript
function createProject(name: string, workingDirectory: string) {
  if (!workingDirectory || workingDirectory.trim() === '') {
    throw new Error('workingDirectory cannot be empty');
  }
  if (!existsSync(workingDirectory)) {
    throw new Error(`workingDirectory does not exist: ${workingDirectory}`);
  }
}
```

### Layer 2: Business Logic Validation
**Purpose:** ensure data makes sense for this specific operation.
```typescript
function initializeWorkspace(projectDir: string, sessionId: string) {
  if (!projectDir) {
    throw new Error('projectDir required for workspace initialization');
  }
}
```

### Layer 3: Environment Guards
**Purpose:** prevent dangerous operations in specific contexts.
```typescript
async function gitInit(directory: string) {
  if (process.env.NODE_ENV === 'test') {
    const normalized = normalize(resolve(directory));
    const tmpDir = normalize(resolve(tmpdir()));
    if (!normalized.startsWith(tmpDir)) {
      throw new Error(`Refusing git init outside temp dir during tests: ${directory}`);
    }
  }
}
```

### Layer 4: Debug Instrumentation
**Purpose:** capture context for forensics.
```typescript
async function gitInit(directory: string) {
  const stack = new Error().stack;
  logger.debug('About to git init', { directory, cwd: process.cwd(), stack });
}
```

## Applying the Pattern

When you find a bug:
1. **Trace the data flow** - where does the bad value originate? Where is it used?
2. **Map all checkpoints** - list every point the data passes through.
3. **Add validation at each layer** - entry, business, environment, debug.
4. **Test each layer** - try to bypass layer 1, verify layer 2 catches it.

## Example

Bug: empty `projectDir` caused `git init` in source code.

**Data flow:** test setup -> empty string -> `Project.create(name, '')` -> `WorkspaceManager.createWorkspace('')` -> `git init` runs in `process.cwd()`.

**Four layers added:**
- Layer 1: `Project.create()` validates not empty/exists/writable
- Layer 2: `WorkspaceManager` validates projectDir not empty
- Layer 3: `WorktreeManager` refuses git init outside tmpdir in tests
- Layer 4: stack trace logging before git init

**Result:** all tests passed, bug impossible to reproduce.

## Key Insight

All four layers were necessary. Different code paths bypassed entry validation; mocks bypassed business logic checks; edge cases on different platforms needed environment guards; debug logging identified structural misuse.

**Don't stop at one validation point.** Add checks at every layer.
