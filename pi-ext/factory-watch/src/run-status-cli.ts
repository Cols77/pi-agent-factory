// Loader for the unified long-run status payload (Increment 7 protocol).
//
// The canonical python serializer -- `coherence.runs.transport.serialize_run_statuses`
// -- is the SOLE JSON entrypoint (see src/coherence/runs/transport.py: "no
// second serializer may be maintained elsewhere"). This file does not build a
// second serializer: it invokes the python side's
// `serialize_run_statuses(list_run_statuses(<root>))` and consumes the emitted
// `{"runs": [...]}` shape exactly. It only holds the CLI + JSON mechanics,
// mirroring coherence-status.ts / trace-cli.ts.
import { runJsonCli } from "./cli-runner.js";
import type { CliResult } from "./cli-runner.js";
import { parseRunStatuses } from "./status-format.js";
import type { RunStatusesPayload } from "./status-format.js";

// Deterministic one-shot: assemble the run rows in the service's sort order and
// emit them through the canonical transport, which is the documented
// `{"runs": [...]}` shape. `serialize_run_statuses` emits `resume_cmd` as JSON
// null when absent and preserves `blocking_obligation_resolve_cmd` as an array.
export function buildRunStatusesCommand(): { bin: string; args: string[] } {
  const script = [
    "import json",
    "from coherence.runs.service import list_run_statuses",
    "from coherence.runs.transport import serialize_run_statuses",
    "print(json.dumps(serialize_run_statuses(list_run_statuses('.'))))",
  ].join("; ");
  return { bin: "uv", args: ["run", "python", "-c", script] };
}

export function loadRunStatuses(cwd: string): CliResult<RunStatusesPayload> {
  const cmd = buildRunStatusesCommand();
  const result = runJsonCli<unknown>(cwd, cmd.bin, cmd.args);
  if (!result.ok) return result;
  const parsed = parseRunStatuses(JSON.stringify(result.value));
  if (parsed === null) {
    return { ok: false, error: "coherence runs: output was not a {'runs': [...]} object" };
  }
  return { ok: true, value: parsed };
}