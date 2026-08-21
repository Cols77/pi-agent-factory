# Polish Session Playground/Usecase Selection Menu — Design

## Purpose

Starting a factory polish session today requires typing the exact target:
`/polish <playground>:<usecase>`. The operator has to remember both the
playground id and a usecase stem, and the bare `/polish` command only errors
with a usage line. This change gives polish the same interactive selection
menu `/factory-run` already provides for ticket selection (`ctx.ui.select`):
with no argument, `/polish` lets the operator pick **which playground** and
then **which usecase**, and launches the session.

## Scope

### In scope

- `factory polish list --json`: a structured listing of playgrounds and their
  usecases (one `{"playground", "usecases"}` object per playground), consumed
  by the picker. Plain `polish list` keeps its existing text output.
- `/polish` with an **empty** argument spawns a two-step `ctx.ui.select` menu:
  playground first, then usecase.
- `/polish <playground>:<usecase>` keeps its existing direct-launch behaviour.

### Out of scope

- Changing the polish session runtime, the bridge, or the routing pipeline.
- Reworking the sim-live / scenario-replay playgrounds themselves.
- Fixing pre-existing dirty files / typecheck errors elsewhere in the factory.

## Design

### 1. Python CLI — `factory polish list --json`

`src/factory/polish/cli.py` gains `cmd_list_json(project_root) -> str`:

```json
[{"playground": "sim-live", "usecases": ["scn_001", "scn_002", "..."]}]
```

A `--json` flag on the `list` subparser routes to it in `main()`; the default
text `cmd_list` path is unchanged.

### 2. TS picker — `polish-picker.ts` (pure)

- `PolishPlayground { playground: string; usecases: string[] }`
- `parsePolishGroupList(raw: string): PolishPlayground[] | null` — parses and
  validates the JSON contract; malformed input returns `null`.
- `polishPlaygroundLabel(pg): string` — `"sim-live (11 usecases)"`.
- `parsePlaygroundIdFromLabel(label): string | null`.

### 3. Wiring — `process-control.ts` + `index.ts`

- `buildPolishListCommand(): Command` → `uv run python -m factory.polish list --json`
  (runs with `cwd = ctx.cwd`, so `--project-root` defaults to `.`).
- `pickPolishTarget(ctx)` (in `index.ts`) shells out to that command, parses the
  result, then presents two menus:
  1. `ctx.ui.select("Polish which playground?", labels)`
  2. `ctx.ui.select("Which usecase on <pg>?", usecases)`.
- The `/polish` handler calls `pickPolishTarget` only when the argument is
  empty; explicit targets launch directly, malformed non-empty targets keep the
  usage error.

## Data flow

```
/polish (no args)
  → pickPolishTarget(ctx)
      spawn: uv run python -m factory.polish list --json   (cwd = repo root)
      → parsePolishGroupList(stdout)
      → menu 1: pick playground   (ctx.ui.select)
      → menu 2: pick usecase      (ctx.ui.select)
  → runPolishSession(ctx, {playground, usecase})   (unchanged launch)

/polish sim-live:scn_005
  → parsePolishTarget → runPolishSession directly (unchanged)
```

## Error handling

- `list --json` exits non-zero, returns malformed JSON, or a bad shape:
  `ctx.ui.notify` + abort, never a crash.
- Empty playground/usecase list: notify "no polish playgrounds/usecases" and abort.
- Operator cancels either `ctx.ui.select` (undefined): abort silently.
- A playground with zero usecases: notify and abort.

## Testing

- Python: `cmd_list_json` unit test + `main(["list", "--json", ...])` test in
  `tests/unit/polish/test_cli.py` (existing config `_project` fixture).
- TS: `polish-picker.test.ts` covers parse/validate/label round-trip;
  `process-control.test.ts` covers `buildPolishListCommand`.
- Manual smoke (R2): `/polish` in an interactive pi session.

## Effort split

Two order-dependent tasks: (1) the `--json` CLI contract, (2) the TS picker +
menu wiring that consumes it.
