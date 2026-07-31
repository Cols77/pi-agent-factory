# Testing Anti-Patterns

**Load this reference when:** writing or changing tests, adding mocks, or tempted to add test-only methods to production code.

## Overview

Tests must verify real behavior, not mock behavior. Mocks are a means to isolate, not the thing being tested.

**Core principle:** Test what the code does, not what the mocks do.

**Following strict TDD prevents these anti-patterns.**

## The Iron Laws

```
1. NEVER test mock behavior
2. NEVER add test-only methods to production classes
3. NEVER mock without understanding dependencies
```

## Anti-Pattern 1: Testing Mock Behavior

**The violation:**
```typescript
// BAD: Testing that the mock exists
test('renders sidebar', () => {
  render(<Page />);
  expect(screen.getByTestId('sidebar-mock')).toBeInTheDocument();
});
```

**Why this is wrong:**
- You're verifying the mock works, not that the component works
- Test passes when mock is present, fails when it's not
- Tells you nothing about real behavior

**The fix:**
```typescript
// GOOD: Test real component or don't mock it
test('renders sidebar', () => {
  render(<Page />);  // Don't mock sidebar
  expect(screen.getByRole('navigation')).toBeInTheDocument();
});
```

### Gate Function

```
BEFORE asserting on any mock element:
  Ask: "Am I testing real component behavior or just mock existence?"

  IF testing mock existence:
    STOP - Delete the assertion or unmock the component

  Test real behavior instead
```

## Anti-Pattern 2: Test-Only Methods in Production

**The violation:**
```typescript
// BAD: destroy() only used in tests
class Session {
  async destroy() {  // Looks like production API!
    await this._workspaceManager?.destroyWorkspace(this.id);
  }
}
```

**Why this is wrong:**
- Production class polluted with test-only code
- Dangerous if accidentally called in production
- Violates YAGNI and separation of concerns

**The fix:**
```typescript
// GOOD: Test utilities handle test cleanup
export async function cleanupSession(session: Session) {
  const workspace = session.getWorkspaceInfo();
  if (workspace) {
    await workspaceManager.destroyWorkspace(workspace.id);
  }
}
```

### Gate Function

```
BEFORE adding any method to production class:
  Ask: "Is this only used by tests?"
  IF yes: STOP - Don't add it. Put it in test utilities instead.

  Ask: "Does this class own this resource's lifecycle?"
  IF no: STOP - Wrong class for this method.
```

## Anti-Pattern 3: Mocking Without Understanding

**The violation:**
```typescript
// BAD: Mock breaks test logic
test('detects duplicate server', () => {
  vi.mock('ToolCatalog', () => ({
    discoverAndCacheTools: vi.fn().mockResolvedValue(undefined)
  }));
  await addServer(config);
  await addServer(config);  // Should throw - but won't!
});
```

**Why this is wrong:**
- Mocked method had a side effect the test depended on (config write)
- Over-mocking to "be safe" breaks actual behavior

**The fix:**
```typescript
// GOOD: Mock at the correct level
test('detects duplicate server', () => {
  vi.mock('MCPServerManager'); // Just mock slow server startup
  await addServer(config);  // Config written
  await addServer(config);  // Duplicate detected
});
```

### Gate Function

```
BEFORE mocking any method:
  1. Ask: "What side effects does the real method have?"
  2. Ask: "Does this test depend on any of those side effects?"
  3. Ask: "Do I fully understand what this test needs?"

  IF depends on side effects:
    Mock at a lower level (the actual slow/external operation), not the
    high-level method the test depends on.

  IF unsure what the test depends on:
    Run the test with the real implementation FIRST, observe what actually
    needs to happen, THEN add minimal mocking at the right level.
```

## Anti-Pattern 4: Incomplete Mocks

**The violation:**
```typescript
// BAD: Partial mock - only fields you think you need
const mockResponse = {
  status: 'success',
  data: { userId: '123', name: 'Alice' }
  // Missing: metadata that downstream code uses
};
```

**Why this is wrong:**
- Partial mocks hide structural assumptions
- Downstream code may depend on fields you didn't include -> silent failures
- Tests pass but integration fails

**The fix:** Mock the COMPLETE data structure as it exists in reality, not just the fields your immediate test uses.

## Anti-Pattern 5: Integration Tests as Afterthought

**The violation:** implementation complete, no tests written, "ready for testing."

**Why this is wrong:** testing is part of implementation, not an optional follow-up. TDD would have caught this.

## When Mocks Become Too Complex

**Warning signs:**
- Mock setup longer than test logic
- Mocking everything to make a test pass
- Mocks missing methods real components have
- Test breaks when mock changes

**Consider:** integration tests with real components are often simpler than complex mocks.

## Quick Reference

| Anti-Pattern | Fix |
|--------------|-----|
| Assert on mock elements | Test real component or unmock it |
| Test-only methods in production | Move to test utilities |
| Mock without understanding | Understand dependencies first, mock minimally |
| Incomplete mocks | Mirror real API completely |
| Tests as afterthought | TDD - tests first |
| Over-complex mocks | Consider integration tests |

## The Bottom Line

**Mocks are tools to isolate, not things to test.**

If TDD reveals you're testing mock behavior, you've gone wrong. Test real behavior or question why you're mocking at all.
