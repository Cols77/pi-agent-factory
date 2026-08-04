---
id: kb-0010
title: "matplotlib.use('Agg') before import pyplot triggers ruff E402; noqa workaround is non-obvious"
status: active
severity: medium
created: "2026-08-03"
last_seen: "2026-08-03"
occurrences: 1
tags: [matplotlib, ruff, lint, E402, plotter, sim, headless, backend]
scope:
  files:
    - src/sim/plotter.py
  error_signatures:
    - "E402 module level import not at top of file"
    - "F841 local variable 'color' is assigned to but never used"
---

## Symptom

A task creates a matplotlib-based plotter module. The module calls `matplotlib.use("Agg")` (required for headless/CI environments) before importing `matplotlib.pyplot`, then imports pyplot and other matplotlib submodules after the `use()` call. Ruff's E402 rule fires on every import after the `use()` call:

```
src/sim/plotter.py:XX:1: E402 module level import not at top of file
```

Additionally, if the plotter assigns a `color` variable from a dict lookup but never passes it to the plot call, ruff's F841 fires:

```
src/sim/plotter.py:XX:5: F841 local variable 'color' is assigned to but never used
```

## Root Cause

matplotlib requires the backend to be set **before** `pyplot` is imported. If you import pyplot first, matplotlib auto-selects a backend (e.g., TkAgg, QtAgg) which may crash or produce warnings in headless environments. The correct pattern is:

```python
import matplotlib
matplotlib.use("Agg")           # set backend FIRST
import matplotlib.pyplot as plt  # then import pyplot
```

This intentionally places `import` statements after non-import code, which ruff's E402 rule flags. The fix is to add `# noqa: E402` to the post-use imports, but this is not obvious to developers who haven't encountered the pattern before.

The F841 issue is a simple copy-paste bug: a `color` variable is assigned from a label-to-color dict but never used in the plot call (e.g., `ax2.scatter()` doesn't accept a `color` parameter the same way `ax3.scatter()` does).

## Rule / Fix

1. **Always use the `# noqa: E402` pattern** for matplotlib imports after `use()`:

   ```python
   import matplotlib
   matplotlib.use("Agg")  # headless backend — must be before pyplot import
   import matplotlib.pyplot as plt  # noqa: E402
   from matplotlib.patches import Polygon as MplPolygon  # noqa: E402
   ```

   Add a comment explaining why the noqa is there.

2. **For unused color variables** — If a `color` variable is assigned from a dict lookup (e.g., `color = label_colors.get(label, "gray")`) but not passed to the plot call, either:
   - Remove the assignment entirely (if the variable is truly unused), or
   - Pass it to the plot function (e.g., `ax2.scatter(..., color=color, ...)` if the scatter supports it).

3. **Add a lint test** that checks the source file for the pattern, so the fix doesn't regress. Example:

   ```python
   def test_no_unused_color_variable_in_panel2(self):
       source = self.PLOTTER_PATH.read_text()
       assert 'color = label_colors.get(label, "gray")' not in source

   def test_imports_before_matplotlib_use(self):
       source = self.PLOTTER_PATH.read_text()
       lines = source.splitlines()
       use_line_idx = next(i for i, l in enumerate(lines)
                           if 'matplotlib.use("Agg")' in l)
       for i in range(use_line_idx + 1, len(lines)):
           stripped = lines[i].strip()
           if stripped.startswith(("import ", "from ")):
               assert "# noqa: E402" in stripped, f"Import at line {i+1} needs noqa"
   ```