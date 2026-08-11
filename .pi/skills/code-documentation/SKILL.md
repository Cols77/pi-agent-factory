---
name: code-documentation
description: Use when writing or modifying any source file to document every function (purpose, args, returns, failure modes) and the module's traceability; keeps the documentation gate green
disable-model-invocation: true
---

# Code Documentation Contract

Every function you write or touch must be documented, and every module must
declare its traceability. A deterministic gate
(`scripts/gates/check_documentation.py`, wired into the project's `full` gate)
parses the source and fails the task if any function is undocumented or any
declared traceability link is stale. Write the documentation as you write the
code — do not leave it for a follow-up.

## Every function / method

Give each function a docstring that covers, in order:

- **Purpose:** what the function is for and why it exists. One line is fine for
  trivial code; explain non-obvious behavior or invariants.
- **Args:** one line per parameter, describing its meaning and any constraints.
  Must match the real signature exactly — every parameter except `self`/`cls`
  must appear. If a parameter is optional, say what its default means.
- **Returns:** what the function returns (and its type when it matters), or
  `None`.
- **Raises:** every exception the body can raise and the condition that raises
  it. If the function raises nothing, write `Raises: None`. This is the
  "return codes / failure modes" half of the contract — a documented function
  that raises a new exception without updating `Raises:` fails the gate.

Example (the exact shape the gate recognises):

```python
def climb(altitude: float, rate: float = 2.0) -> None:
    """Command the drone to climb to a target altitude.

    Purpose: move the aircraft toward *altitude* at the given vertical *rate*,
    updating the controller's target state. Reasons to climb (mission
    directives, obstacle avoidance) are decided by callers.

    Args:
        altitude: target altitude in metres above the take-off datum.
        rate: vertical speed in m/s; defaults to 2.0.

    Returns:
        None.

    Raises:
        RuntimeError: if the aircraft is not armed.
    """
    if not self._armed:
        raise RuntimeError("Climb requires an armed aircraft")
    self._target_z = altitude
```

## Module traceability

Every module's docstring must end with a `Traceability:` section naming the SRs
it implements and the tasks that created/modified it. The gate compares these
exactly against `tasks/*.md` (each task's `Create:`/`Modify:` paths plus its
`satisfies:` list). A file no task links to must say so explicitly:

```python
"""Module-level summary line.

Traceability:
    SRs: SR-116, SR-117
    Tasks: T-061
"""
```

- List the actual SRs and task ids, sorted, comma-separated. Do not invent a
  link: the gate refuses a declared SR/task that no task actually satisfies or
  touches.
- When you modify an already-traced file, re-check the header: if the current
  task is not already listed, add it (and any SR the task satisfies that the
  file now implements). A header that is behind the current task list fails the
  gate.

## When to document

- Every function you create.
- Every function you modify in a way that changes its purpose, parameters,
  return value, or the exceptions it can raise.
- Any module whose responsibility or traced SR set changes.

## Do not

- Skip documenting because a function is "obvious" — a getter still gets a
  one-line Purpose plus Returns.
- Document what the code does in a comment inside the body (repeat the
  `Purpose:` section verbatim); comments explain *why*, docstrings state the
  contract.
- Leave the module `Traceability:` stale after adding a new task.

Related skills: `verification-before-completion` (confirm the doc gate is green
before declaring a task done), `coding-principles` (the Review role checks that
this documentation is up to date with the implementation).