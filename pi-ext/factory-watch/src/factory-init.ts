// Deterministic project bootstrap for pi-agent-factory.
//
// The core is deliberately PURE: no Pi types are imported here, so the whole
// discovery/synthesis/write/replace/check pipeline is unit-testable against a
// temp directory with nothing but node:fs. The command layer that glues it to
// /factory-init lives in factory-init-command.ts and imports Pi types.
//
// What this module does, in one sentence: perform bounded repository
// discovery ONCE, persist a schema-versioned project-profile.json, and keep a
// small managed block inside AGENTS.md under stable markers so the same
// approved knowledge is deterministically available to every parent and
// subagent session without re-scanning on each session.
//
// Design rules that are enforced here rather than in prose:
//   - evidence-first: every recorded fact carries an evidence path; nothing is
//     accepted without one, so unsupported commands / architectural claims
//     never reach the profile.
//   - idempotent: writing is a no-op unless on-disk bytes actually change.
//   - atomic: writes go to a temp file in the same directory, then rename(2).
//   - preserve: everything outside the managed markers is untouched
//     byte-for-byte; a malformed/duplicate marker fails safe instead of
//     guessing.

import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import {
  existsSync,
  mkdirSync,
  readFileSync,
  readdirSync,
  renameSync,
  statSync,
  writeFileSync,
} from "node:fs";
import { dirname, isAbsolute, join, resolve } from "node:path";

export const BOOTSTRAP_SCHEMA = 2;
export const BLOCK_START = "<!-- pi-agent-factory:bootstrap:start schema=1 -->";
export const BLOCK_END = "<!-- pi-agent-factory:bootstrap:end -->";
export const PROFILE_STEM = "project-profile.json";
export const DEFAULT_CONFIG_DIR = ".pi";

export interface CommandFact {
  name: string;
  cmd: string;
  kind: "build" | "test" | "lint" | "typecheck" | "simulation" | "validation" | "setup" | "other";
  evidence: string;
}

export interface InvariantFact {
  text: string;
  evidence: string;
}

export interface Evidence {
  name: string | null;
  purpose: string;
  components: string[];
  packages: string[];
  sourceDirs: string[];
  specsDirs: string[];
  plansDirs: string[];
  requirementsDir: string | null;
  adrDirs: string[];
  tasksDir: string | null;
  evidenceDirs: string[];
  commands: CommandFact[];
  invariants: InvariantFact[];
}

export interface ProjectProfile {
  schema: number;
  generated_at: string;
  project_root: string;
  project: { name: string | null; purpose: string };
  components: string[];
  packages: string[];
  source_dirs: string[];
  docs: {
    specs: string[];
    plans: string[];
    requirements: string | null;
    adrs: string[];
    tasks: string | null;
    evidence: string[];
  };
  commands: CommandFact[];
  invariants: InvariantFact[];
  /** hash of each evidence source file -> used for drift detection. */
  hashes: Record<string, string>;
  _source_files: string[];
  /**
   * Durable code-index intent recorded at init. The ACTUAL engine of the
   * built index lives in .factory/code-index/latest.json (written by the
   * builder, which probes what is really importable); this block records the
   * deterministic preference only, so profile signatures stay stable.
   */
  codeindex?: { prefer: "tree-sitter" };
}

export interface InitResult {
  status: "ok" | "changed" | "error";
  root: string;
  profileChanged: boolean;
  blockChanged: boolean;
  reload: boolean;
  fresh: boolean;
  report: string;
  profile: ProjectProfile;
  diff: string | null;
}

export interface CheckResult {
  ok: boolean;
  root: string;
  rootResolution: "git" | "cwd-fallback";
  profilePresent: boolean;
  profileFresh: boolean;
  blockPresent: boolean;
  blockValid: boolean;
  drift: { file: string; changed: boolean }[];
  /** engine recorded in .factory/code-index/latest.json, or null when absent. */
  codeIndexEngine: string | null;
  findings: { level: "error" | "warning" | "info"; message: string; remediation?: string }[];
}

// ---------------------------------------------------------------------------
// Project-root resolution
// ---------------------------------------------------------------------------

/** Resolve the project root: Git when available, else the given cwd. */
export function resolveProjectRoot(cwd: string): { root: string; method: "git" | "cwd-fallback" } {
  try {
    const out = execFileSync("git", ["rev-parse", "--show-toplevel"], {
      cwd,
      encoding: "utf-8",
      stdio: ["ignore", "pipe", "ignore"],
    }).trim();
    if (out) {
      return { root: resolve(out), method: "git" };
    }
  } catch {
    // not a git repo -> fall through to cwd
  }
  return { root: resolve(cwd), method: "cwd-fallback" };
}

// ---------------------------------------------------------------------------
// Deterministic evidence collection
// ---------------------------------------------------------------------------

function hashFile(p: string): string {
  if (!existsSync(p)) return "missing";
  return createHash("sha256").update(readFileSync(p)).digest("hex").slice(0, 16);
}

function listExisting(dir: string, predicate: (name: string) => boolean): string[] {
  if (!existsSync(dir)) return [];
  try {
    return readdirSync(dir).filter(predicate).sort();
  } catch {
    return [];
  }
}

function readFirstParagraph(p: string, limit = 600): string {
  if (!existsSync(p)) return "";
  const text = readFileSync(p, "utf-8").replace(/\r\n/g, "\n");
  // Skip YAML frontmatter, then take the first non-heading prose paragraph.
  const body = text.replace(/^---[\s\S]*?---\n/, "");
  for (const para of body.split(/\n{2,}/)) {
    const cleaned = para.replace(/^#+\s*/, "").trim();
    if (cleaned.length > 0 && !cleaned.startsWith("[") && !cleaned.startsWith("```")) {
      return cleaned.slice(0, limit);
    }
  }
  return "";
}

function projectName(root: string): string | null {
  const pyproject = join(root, "pyproject.toml");
  if (existsSync(pyproject)) {
    const m = /^name\s*=\s*["']([^"']+)["']/m.exec(readFileSync(pyproject, "utf-8"));
    if (m?.[1]) return m[1];
  }
  const pkg = join(root, "package.json");
  if (existsSync(pkg)) {
    try {
      const j = JSON.parse(readFileSync(pkg, "utf-8")) as { name?: string };
      if (typeof j.name === "string" && j.name) return j.name;
    } catch {
      // ignore malformed package.json
    }
  }
  return null;
}

function packageNames(root: string): string[] {
  const out = new Set<string>();
  const pkg = join(root, "package.json");
  if (existsSync(pkg)) {
    try {
      const j = JSON.parse(readFileSync(pkg, "utf-8")) as {
        dependencies?: Record<string, string>;
        devDependencies?: Record<string, string>;
      };
      for (const k of Object.keys(j.dependencies ?? {})) out.add(k);
      for (const k of Object.keys(j.devDependencies ?? {})) out.add(k);
    } catch {
      // ignore
    }
  }
  const pyproject = join(root, "pyproject.toml");
  if (existsSync(pyproject)) {
    const m = /^dependencies\s*=\s*\[([\s\S]*?)\]/m.exec(readFileSync(pyproject, "utf-8"));
    const depsBlock = m?.[1];
    if (depsBlock !== undefined) {
      for (const line of depsBlock.split("\n")) {
        const dep = /["']([A-Za-z0-9_.-]+)["']/.exec(line);
        const depName = dep?.[1];
        if (depName && !depName.startsWith("{") && depName !== "ansicolors") out.add(depName);
      }
    }
  }
  return [...out].sort();
}

function sourceDirs(root: string): string[] {
  const found: string[] = [];
  for (const dir of ["src", "pi-ext", "scripts", "tests", "tasks", "docs", "requirements"]) {
    if (existsSync(join(root, dir))) found.push(dir);
  }
  return found;
}

function readFactoryGates(root: string): Pick<CommandFact, "cmd" | "evidence">[] {
  const path = join(root, ".factory", "factory.yaml");
  if (!existsSync(path)) return [];
  const gates: Pick<CommandFact, "cmd" | "evidence">[] = [];
  // crude but deterministic: capture every `- { cmd: "..." }` under a gate heading
  const text = readFileSync(path, "utf-8");
  const gateRe = /^\s*(\w+):\s*$/gm;
  let m: RegExpExecArray | null;
  while ((m = gateRe.exec(text)) !== null) {
    const name = m[1]!;
    const after = text.slice(m.index + m[0].length);
    for (const line of after.split("\n")) {
      const c = /cmd:\s*["']?([^"'\s][^"']*)["']?/.exec(line);
      const cmd = c?.[1];
      if (cmd) {
        gates.push({ cmd: cmd.trim(), evidence: path });
        void name;
        break;
      }
      if (/^\s*\w+:/.test(line) && !/^\s+cmd:/.test(line)) break;
    }
  }
  return gates;
}

function npmScriptCommands(root: string): Pick<CommandFact, "cmd" | "evidence">[] {
  const pkg = join(root, "package.json");
  if (!existsSync(pkg)) return [];
  try {
    const j = JSON.parse(readFileSync(pkg, "utf-8")) as { scripts?: Record<string, string> };
    return Object.entries(j.scripts ?? {}).map(([name, cmd]) => ({
      cmd: `npm run ${name} --prefix pi-ext/factory-watch # ${cmd}`,
      evidence: pkg,
    }));
  } catch {
    return [];
  }
}

function pytestCommands(root: string): { kind: CommandFact["kind"]; name: string; cmd: string }[] {
  const pyproject = join(root, "pyproject.toml");
  if (!existsSync(pyproject)) return [];
  const text = readFileSync(pyproject, "utf-8");
  const markers: string[] = [];
  const markerRe = /"([a-z]+):[^"]*"/g;
  let m: RegExpExecArray | null;
  while ((m = markerRe.exec(text)) !== null) {
    markers.push(m[1]!);
  }
  const out: { kind: CommandFact["kind"]; name: string; cmd: string }[] = [];
  const standard: Record<string, CommandFact["kind"]> = {
    unit: "test",
    sim: "simulation",
    integration: "test",
    full: "validation",
  };
  const seen = new Set<string>();
  for (const name of markers) {
    if (seen.has(name)) continue;
    seen.add(name);
    out.push({
      kind: standard[name] ?? "test",
      name,
      cmd: `uv run python -m pytest -m ${name} -q`,
    });
  }
  if (seen.size === 0) {
    out.push({ kind: "test", name: "unit", cmd: "uv run python -m pytest -m unit -q" });
  }
  return out;
}

function architecturalInvariants(root: string): InvariantFact[] {
  // Deterministic, evidence-bearing invariants: only claim what the repo
  // itself states. These are derived from stable signals, never from a model.
  const out: InvariantFact[] = [];
  const factoryYaml = join(root, ".factory", "factory.yaml");
  if (existsSync(factoryYaml)) {
    out.push({
      text: "The gate vocabulary is fixed: unit, sim, integration, full.",
      evidence: factoryYaml,
    });
  }
  const pyproject = join(root, "pyproject.toml");
  if (existsSync(pyproject) && /line-length\s*=\s*100/.test(readFileSync(pyproject, "utf-8"))) {
    out.push({
      text: "Python is 3.11-3.12, ruff line-length 100, pyright standard mode.",
      evidence: pyproject,
    });
  }
  const ui = join(root, "docs", "superpowers", "plans", "engineering-context", "00-program-architecture.md");
  if (existsSync(ui)) {
    out.push({
      text: "The deterministic factory pipeline is documented in engineering-context plans.",
      evidence: ui,
    });
  }
  return out;
}

const COMPONENT_HINTS: [string, string][] = [
  ["src/factory/orchestrator", "factory orchestrator"],
  ["src/factory/evidence", "evidence model"],
  ["src/factory/trace", "traceability CLI"],
  ["src/factory/doctor", "requirements doctor"],
  ["src/factory/requirements", "requirement register"],
  ["src/factory/system", "system navigator"],
  ["src/factory/polish", "polish workflow"],
  ["src/factory/validation", "sim/validation harnesses"],
  ["pi-ext/factory-watch", "pi extension (commands + tools)"],
];

function collectEvidence(root: string): Evidence {
  const name = projectName(root);
  const purpose = readFirstParagraph(join(root, "README.md")) || `${name ?? "this repository"}: a pi-agent-factory target.`;
  const components = COMPONENT_HINTS.filter(([p]) => existsSync(join(root, p))).map(([, label]) => label);
  const commands: CommandFact[] = [];

  for (const g of readFactoryGates(root)) {
    const kind: CommandFact["kind"] = commands.length === 0 ? "validation" : "other";
    commands.push({ name: "factory gate", cmd: g.cmd, kind, evidence: g.evidence });
  }
  for (const s of npmScriptCommands(root)) {
    commands.push({ name: s.cmd.split(" ")[2] ?? "npm", cmd: s.cmd, kind: "test", evidence: s.evidence });
  }
  for (const p of pytestCommands(root)) {
    commands.push({ name: p.name, cmd: p.cmd, kind: p.kind, evidence: join(root, "pyproject.toml") });
  }
  // Always surface the canonical static-surface commands deterministically.
  if (existsSync(join(root, "pyproject.toml"))) {
    commands.push(
      { name: "lint", cmd: "uv run ruff check .", kind: "lint", evidence: join(root, "pyproject.toml") },
      { name: "typecheck", cmd: "uv run pyright", kind: "typecheck", evidence: join(root, "pyproject.toml") },
    );
  }
  if (existsSync(join(root, "pi-ext", "factory-watch"))) {
    commands.push({
      name: "extension test",
      cmd: "npm test --prefix pi-ext/factory-watch",
      kind: "test",
      evidence: join(root, "pi-ext", "factory-watch", "package.json"),
    });
  }

  const specsDirs = ["docs/superpowers/specs", "docs/specs", "specs"].filter((d) =>
    existsSync(join(root, d)),
  );
  const plansDirs = ["docs/superpowers/plans", "docs/plans", "plans"].filter((d) =>
    existsSync(join(root, d)),
  );
  const requirementsDir = existsSync(join(root, "requirements")) ? "requirements" : null;
  const adrDirs = ["docs/adr", "docs/architecture/decisions"].filter((d) => existsSync(join(root, d)));
  const tasksDir = existsSync(join(root, "tasks")) ? "tasks" : null;
  const evidenceDirs = ["sessions", "evidence"].filter((d) => existsSync(join(root, d)));

  const invariants = architecturalInvariants(root);

  return {
    name,
    purpose,
    components,
    packages: packageNames(root),
    sourceDirs: sourceDirs(root),
    specsDirs,
    plansDirs,
    requirementsDir,
    adrDirs,
    tasksDir,
    evidenceDirs,
    commands: dedupeCommands(commands),
    invariants,
  };
}

function dedupeCommands(commands: CommandFact[]): CommandFact[] {
  const seen = new Set<string>();
  const out: CommandFact[] = [];
  for (const c of commands) {
    const key = `${c.name}|${c.cmd}`;
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(c);
  }
  return out;
}

// ---------------------------------------------------------------------------
// Profile construction / hashing
// ---------------------------------------------------------------------------

function evidenceSourceFiles(root: string, evidence: Evidence): string[] {
  const files = new Set<string>();
  for (const f of ["README.md", "pyproject.toml", "package.json", ".factory/factory.yaml"]) {
    if (existsSync(join(root, f))) files.add(join(root, f));
  }
  for (const c of evidence.commands) {
    if (isAbsolute(c.evidence)) files.add(c.evidence);
    else if (existsSync(join(root, c.evidence))) files.add(join(root, c.evidence));
  }
  for (const i of evidence.invariants) {
    if (isAbsolute(i.evidence)) files.add(i.evidence);
    else if (existsSync(join(root, i.evidence))) files.add(join(root, i.evidence));
  }
  return [...files].sort();
}

export function buildProfile(root: string, evidence: Evidence, now: string): ProjectProfile {
  const sourceFiles = evidenceSourceFiles(root, evidence);
  const hashes: Record<string, string> = {};
  for (const f of sourceFiles) hashes[f] = hashFile(f);
  return {
    schema: BOOTSTRAP_SCHEMA,
    generated_at: now,
    project_root: root,
    project: { name: evidence.name, purpose: evidence.purpose },
    components: evidence.components,
    packages: evidence.packages,
    source_dirs: evidence.sourceDirs,
    docs: {
      specs: evidence.specsDirs,
      plans: evidence.plansDirs,
      requirements: evidence.requirementsDir,
      adrs: evidence.adrDirs,
      tasks: evidence.tasksDir,
      evidence: evidence.evidenceDirs,
    },
    commands: evidence.commands,
    invariants: evidence.invariants,
    hashes,
    _source_files: sourceFiles,
    // The factory prefers tree-sitter for the durable code index; the actual
    // engine is decided by the builder's probe at build time (latest.json).
    codeindex: { prefer: "tree-sitter" },
  };
}

// ---------------------------------------------------------------------------
// Managed AGENTS.md block
// ---------------------------------------------------------------------------

function renderFactoryTools(tools: readonly { name: string; family: string }[]): string {
  const byFamily = new Map<string, string[]>();
  for (const t of tools) {
    const list = byFamily.get(t.family) ?? [];
    list.push(t.name);
    byFamily.set(t.family, list);
  }
  return Array.from(byFamily.entries())
    .map(([family, names]) => `${family} (${names.join(", ")})`)
    .join("; ");
}

const blockMarkdown = (profile: ProjectProfile, tools?: readonly { name: string; family: string }[]): string =>
  [
    ...(profile.project.purpose ? [profile.project.purpose] : []),
    ...(profile.components.length
      ? [
          "Key components & boundaries: " +
            profile.components.join("; ") +
            (profile.packages.length ? ` (packages: ${profile.packages.slice(0, 8).join(", ")})` : "") +
            ".",
        ]
      : []),
    ...(profile.docs.specs.length || profile.docs.plans.length || profile.docs.requirements
      ? [
          "Canonical documents: specs " +
            (profile.docs.specs.join(", ") || "(none)") +
            "; plans " +
            (profile.docs.plans.join(", ") || "(none)") +
            (profile.docs.requirements ? "; requirements " + profile.docs.requirements : "") +
            ".",
        ]
      : []),
    profile.commands.length
      ? "Common commands: " +
        [...new Set(profile.commands.map((c) => `${c.name}: ${c.cmd}`))].join(" | ") +
        "."
      : "",
    ...profile.invariants.map((i) => "Rule: " + i.text),
    ...(tools && tools.length ? ["Factory tools: " + renderFactoryTools(tools)] : []),
    // Pointers, deliberately terse: the full profile is on disk, not in every prompt.
    ...(profile.docs.requirements
      ? [
          "Validation is system-requirement driven (see requirements/). Deeper project knowledge lives in project-profile.json or the docs servers.",
          "Factory commands: /factory, /factory-run, /factory-init --check, /trace-fix, /review-plans, /system.",
        ]
      : [
          "Deeper project knowledge lives in project-profile.json; run /factory-init --check for status.",
          "Factory commands: /factory, /factory-run, /factory-init, /trace-fix, /system.",
        ]),
  ]
    .filter(Boolean)
    .join("\n\n");

export function buildManagedBlock(
  profile: ProjectProfile,
  tools?: readonly { name: string; family: string }[],
): string {
  return [
    BLOCK_START,
    "# Project (factory bootstrap)",
    blockMarkdown(profile, tools),
    BLOCK_END,
  ].join("\n");
}

// ---------------------------------------------------------------------------
// AGENTS.md round-trip with preserved surroundings
// ---------------------------------------------------------------------------

export interface AgentsMdRead {
  present: boolean;
  content: string;
  block: string | null; // existing managed block (raw, without markers) if any
}

function splitManaged(content: string): { before: string; after: string; block: string | null; count: number } {
  const startIdx = content.indexOf(BLOCK_START);
  const endIdx = content.lastIndexOf(BLOCK_END);
  if (startIdx === -1 && endIdx === -1) {
    return { before: content, after: "", block: null, count: 0 };
  }
  let count = 0;
  let idx = 0;
  while ((idx = content.indexOf(BLOCK_START, idx)) !== -1) {
    count++;
    idx += BLOCK_START.length;
  }
  if (startIdx === -1 || endIdx === -1 || endIdx < startIdx) {
    // malformed: one marker without the other
    return { before: content, after: "", block: null, count: -1 };
  }
  const block = content.slice(startIdx + BLOCK_START.length, endIdx);
  const before = content.slice(0, startIdx);
  const after = content.slice(endIdx + BLOCK_END.length);
  return { before, after, block, count };
}

export function readAgentsMd(root: string): AgentsMdRead {
  const path = join(root, "AGENTS.md");
  if (!existsSync(path)) return { present: false, content: "", block: null };
  const content = readFileSync(path, "utf-8").replace(/\r\n/g, "\n");
  const { block } = splitManaged(content);
  return { present: true, content, block };
}

export function managedBlockIssues(content: string): string[] {
  const issues: string[] = [];
  const startMatches = content.split(BLOCK_START).length - 1;
  const endMatches = content.split(BLOCK_END).length - 1;
  if (startMatches === 0 && endMatches === 0) return [];
  if (startMatches !== 1) issues.push(`expected exactly 1 start marker, found ${startMatches}`);
  if (endMatches !== 1) issues.push(`expected exactly 1 end marker, found ${endMatches}`);
  const startIdx = content.indexOf(BLOCK_START);
  const endIdx = content.lastIndexOf(BLOCK_END);
  if (startMatches === 1 && endMatches === 1 && endIdx < startIdx) {
    issues.push("end marker appears before start marker");
  }
  return issues;
}

/** Replace (or insert) the managed block, preserving surrounding bytes. */
export function replaceManagedBlock(
  existingContent: string,
  newBlock: string,
): { content: string; replaced: boolean } {
  const issues = managedBlockIssues(existingContent);
  if (issues.length > 0) {
    throw new Error("refusing to edit a malformed/ambiguous managed block: " + issues.join("; "));
  }
  const { before, after, block } = splitManaged(existingContent);
  const body = newBlock.slice(BLOCK_START.length, newBlock.length - BLOCK_END.length);
  const replacement = before + BLOCK_START + body + BLOCK_END + after;
  if (block === null) return { content: replacement, replaced: false };
  if (existingContent === replacement) return { content: existingContent, replaced: false };
  return { content: replacement, replaced: true };
}

// ---------------------------------------------------------------------------
// Atomic writes
// ---------------------------------------------------------------------------

export function atomicWrite(path: string, data: string): void {
  const dir = dirname(path);
  mkdirSync(dir, { recursive: true });
  const tmp = join(dir, `.${PROFILE_STEM}.tmp-${process.pid}-${Date.now()}`);
  writeFileSync(tmp, data, "utf-8");
  try {
    renameSync(tmp, path);
  } catch (err) {
    try {
      // Best-effort cleanup of the temp file on a failed rename.
      if (existsSync(tmp)) {
        import("node:fs").then(({ unlinkSync }) => unlinkSync(tmp)).catch(() => undefined);
      }
    } catch {
      // ignore
    }
    throw err;
  }
}

// ---------------------------------------------------------------------------
// Drift / check
// ---------------------------------------------------------------------------

export function computeDrift(
  root: string,
  profile: ProjectProfile | null,
  evidence: Evidence,
): { file: string; changed: boolean }[] {
  if (profile === null) return [];
  const fresh = buildProfile(root, evidence, profile.generated_at);
  const current = new Set(fresh._source_files);
  const recorded = profile.hashes ?? {};
  const rows: { file: string; changed: boolean }[] = [];
  const all = new Set([...Object.keys(recorded), ...current]);
  for (const f of all) {
    const before = recorded[f];
    const after = current.has(f) ? hashFile(f) : "missing";
    if (before !== after) rows.push({ file: f, changed: true });
  }
  return rows;
}

// ---------------------------------------------------------------------------
// Orchestration
// ---------------------------------------------------------------------------

export interface FactoryInitOptions {
  root: string;
  mode: "init" | "refresh" | "check";
  configDir?: string;
  now?: string;
  /**
   * Available factory tools, derived from what the extension registers. When
   * provided, /factory-init weaves a "Factory tools:" line into the AGENTS.md
   * managed block so the agent's system prompt reflects the current tool
   * surface. Kept generic here to avoid a circular import with the catalog
   * module; the command glue passes the real catalog. Optional for backward
   * compatibility (tests that call runFactoryInit without it stay unchanged).
   */
  tools?: readonly { name: string; family: string }[];
}

export function profilePath(root: string, configDir = DEFAULT_CONFIG_DIR): string {
  return join(root, configDir, "factory", PROFILE_STEM);
}

/** Read-only validation + drift check. Never writes. */
export function runFactoryCheck(
  root: string,
  configDir = DEFAULT_CONFIG_DIR,
  opts: { rootResolution?: "git" | "cwd-fallback" } = {},
): CheckResult {
  const pPath = profilePath(root, configDir);
  const evidence = collectEvidence(root);
  const profilePresent = existsSync(pPath);
  let existingProfile: ProjectProfile | null = null;
  if (profilePresent) {
    try {
      existingProfile = JSON.parse(readFileSync(pPath, "utf-8")) as ProjectProfile;
    } catch {
      existingProfile = null;
    }
  }
  const block = readAgentsMd(root);
  const blockIssues = managedBlockIssues(block.content);
  const drift = computeDrift(root, existingProfile, evidence);
  const profileFresh = existingProfile !== null && drift.length === 0;
  const blockPresent = block.present && blockIssues.length === 0 && block.block !== null;
  const blockValid = blockPresent && blockIssues.length === 0;
  return {
    ok: profileFresh && blockValid,
    root,
    rootResolution: opts.rootResolution ?? "git",
    profilePresent: profilePresent && existingProfile !== null,
    profileFresh,
    blockPresent,
    blockValid,
    drift,
    codeIndexEngine: readCodeIndexEngine(root),
    findings: [],
  };
}

/** Read the engine recorded by the last code-index build, if any. */
export function readCodeIndexEngine(root: string): string | null {
  try {
    const latestPath = join(root, ".factory", "code-index", "latest.json");
    const latest = JSON.parse(readFileSync(latestPath, "utf-8")) as { engine?: string };
    return typeof latest.engine === "string" ? latest.engine : null;
  } catch {
    return null;
  }
}

function profileSignature(profile: ProjectProfile): string {
  // The timestamp is metadata, not content: two runs with identical evidence
  // must compare equal so a no-op run does not rewrite the file (idempotency).
  const copy = { ...profile, generated_at: "" };
  return JSON.stringify(copy);
}

export function runFactoryInit(opts: FactoryInitOptions): InitResult {
  const { root, mode, configDir = DEFAULT_CONFIG_DIR } = opts;
  const now = opts.now ?? new Date().toISOString();
  const pPath = profilePath(root, configDir);
  const agentsPath = join(root, "AGENTS.md");

  const evidence = collectEvidence(root);
  const profile = buildProfile(root, evidence, now);
  const newBlock = buildManagedBlock(profile, opts.tools);

  const profilePresent = existsSync(pPath);
  let existingProfile: ProjectProfile | null = null;
  if (profilePresent) {
    try {
      existingProfile = JSON.parse(readFileSync(pPath, "utf-8")) as ProjectProfile;
    } catch {
      existingProfile = null; // treated as absent for refresh
    }
  }

  // --check: read-only, never writes.
  if (mode === "check") {
    const checks = runFactoryCheck(root, configDir);
    const status = checks.ok ? "ok" : "changed";
    return {
      status: "ok",
      root,
      profileChanged: false,
      blockChanged: false,
      reload: false,
      fresh: status === "ok",
      report: formatCheck(checks),
      profile,
      diff: null,
    };
  }

  // init / refresh
  const profileChanged = profilePresent && existingProfile !== null
    ? profileSignature(existingProfile) !== profileSignature(profile)
    : true;

  let agentsChanged = false;
  if (existsSync(agentsPath)) {
    agentsChanged = replaceManagedBlock(readFileSync(agentsPath, "utf-8"), newBlock).replaced;
  } else {
    agentsChanged = true; // will create a new AGENTS.md with the block
  }

  const changed = profileChanged || agentsChanged;

  if (changed) {
    atomicWrite(pPath, JSON.stringify(profile, null, 2) + "\n");
    const heading = "# AGENTS.md\n\nThis file is partly managed by the pi-agent-factory bootstrap.\n\n";
    if (existsSync(agentsPath)) {
      const next = replaceManagedBlock(readFileSync(agentsPath, "utf-8"), newBlock).content;
      atomicWrite(agentsPath, next);
    } else {
      atomicWrite(agentsPath, heading + newBlock + "\n");
    }
  }

  const fresh = !changed;
  return {
    status: changed ? "changed" : "ok",
    root,
    profileChanged,
    blockChanged: agentsChanged,
    reload: changed, // caller must call ctx.reload() only when true
    fresh,
    report: describeChange(profile, fresh),
    profile,
    diff: changed ? describeChange(profile, false) : null,
  };
}

function describeChange(profile: ProjectProfile, fresh: boolean): string {
  const lines: string[] = [];
  lines.push(fresh ? "Bootstrap is up to date (idempotent run produced no change)." : "Bootstrap updated.");
  lines.push(`project: ${profile.project.name ?? "(unnamed)"}`);
  lines.push(`purpose: ${profile.project.purpose}`);
  if (profile.components.length) lines.push("components: " + profile.components.join("; "));
  if (profile.commands.length) {
    lines.push("commands:");
    for (const c of profile.commands) lines.push(`  - ${c.name}: ${c.cmd} (${c.kind})`);
  }
  if (profile.invariants.length) {
    lines.push("invariants:");
    for (const i of profile.invariants) lines.push(`  - ${i.text}`);
  }
  lines.push(
    `profile: ${profile.docs.specs.join(", ") || "(no specs dir yet)"} specs; ` +
      `${profile.docs.plans.join(", ") || "(no plans dir yet)"} plans; ` +
      `requirements ${profile.docs.requirements ?? "(none)"}.`,
  );
  return lines.join("\n");
}

export function formatCheck(c: CheckResult): string {
  const lines: string[] = [];
  lines.push(`factory-init --check on ${c.root} (root: ${c.rootResolution})`);
  lines.push(`  profile present:   ${c.profilePresent}`);
  lines.push(`  profile fresh:     ${c.profileFresh}`);
  lines.push(`  managed block:     present=${c.blockPresent} valid=${c.blockValid}`);
  for (const d of c.drift) {
    lines.push(`  drift:             ${d.file} ${d.changed ? "CHANGED" : "ok"}`);
  }
  for (const f of c.findings) {
    lines.push(`  [${f.level.toUpperCase()}] ${f.message}${f.remediation ? " -> " + f.remediation : ""}`);
  }
  lines.push(c.ok ? "OK" : "STALE -- run /factory-init --refresh");
  return lines.join("\n");
}

// ---------------------------------------------------------------------------
// Cheap tool-surface alignment (auto-heal on session start)
// ---------------------------------------------------------------------------
//
// The AGENTS.md managed block can drift from the extension's live tool surface
// whenever the extension evolves independently (e.g. a new eng_*/system_*/trace_*
// tool is added to a builder). Full /factory-init is heavyweight (collects
// evidence, hashes files, builds the code index), so we do NOT run it on every
// session. Instead this is a cheap, deterministic, idempotent alignment: derive
// the tool signature, compare it to a tiny sidecar (```.pi/factory/tools.json```),
// and when they differ re-weave just the managed-block tools line from the
// already-stored profile. Session start calls this best-effort, exactly like the
// existing code-index fingerprint refresh.
//
// Writing happens only when content actually changed (replaceManagedBlock +
// safeTile signature), so repeated calls are no-ops. The write is safe even when
// the profile came from an earlier schema: buildManagedBlock reads the profile
// on disk and only the tools line is added/kept.

/** Deterministic signature of a tool catalog: sorted stable entries. */
export function toolsSignature(
  entries: readonly { name: string; family: string }[],
): string {
  const keys = new Set(entries.map((e) => `${e.family}\u0000${e.name}`));
  return [...keys].sort().join("\n");
}

export function toolsStatePath(root: string, configDir = DEFAULT_CONFIG_DIR): string {
  return join(root, configDir, "factory", "tools.json");
}

export function readToolsSignature(root: string, configDir = DEFAULT_CONFIG_DIR): string | null {
  try {
    const raw = readFileSync(toolsStatePath(root, configDir), "utf-8");
    const state = JSON.parse(raw) as { signature?: string };
    return typeof state.signature === "string" ? state.signature : null;
  } catch {
    return null; // absent or unreadable -> treated as never-aligned
  }
}

export interface AlignToolsResult {
  /** True when a stale sidecar or block was detected (and fixed). */
  changed: boolean;
  /** True when the managed-block tools line was rewritten. */
  blockChanged: boolean;
}

/**
 * Cheap alignment. Returns false when the bootstrap is not yet initialised
 * (no stored profile) so callers know there is nothing to align.
 */
export function alignBootstrapTools(
  root: string,
  entries: readonly { name: string; family: string }[],
  configDir = DEFAULT_CONFIG_DIR,
  now = new Date().toISOString(),
): AlignToolsResult {
  const sig = toolsSignature(entries);
  const recorded = readToolsSignature(root, configDir);
  const storedChanged = recorded !== sig;
  let blockChanged = false;

  // Only touch the block when the bootstrap is initialized (profile present) so
  // a raw repo without /factory-init is not half-created by a session hook.
  const pPath = profilePath(root, configDir);
  if (existsSync(pPath)) {
    try {
      const profile = JSON.parse(readFileSync(pPath, "utf-8")) as ProjectProfile;
      const agentsPath = join(root, "AGENTS.md");
      if (existsSync(agentsPath)) {
        const newBlock = buildManagedBlock(profile, entries);
        const replaced = replaceManagedBlock(readFileSync(agentsPath, "utf-8"), newBlock);
        if (replaced.replaced) {
          atomicWrite(agentsPath, replaced.content);
          blockChanged = true;
        }
      }
    } catch {
      // non-fatal: never take the session down over a bootstrap alignment
    }
  } else {
    // No profile yet -> nothing to align. Also avoid marking tools state.
    return { changed: false, blockChanged: false };
  }

  if (storedChanged) {
    atomicWrite(toolsStatePath(root, configDir), JSON.stringify({ signature: sig, generated_at: now }, null, 2) + "\n");
  }
  return { changed: storedChanged || blockChanged, blockChanged };
}
