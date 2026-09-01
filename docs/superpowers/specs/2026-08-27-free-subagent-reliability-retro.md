# Free-Subagent Reliability Retrospective — FEAT-14..17 authoring & review (2026-08-27)

_Status: failure log / handoff. Purpose: a dedicated session will build a RELIABLE skill from
this post-mortem. Everything here is real observed data from one afternoon of dispatching free
OpenRouter subagents via `hermes chat` to author + review four design dossiers. Date: 2026-08-27._

---

## 0. TL;DR — the numbers

- **14 subagent launches** to produce 4 design dossiers + 4 review reports.
- **Genuinely succeeded: 2 of 14** — FEAT-14 dev (wrote a 16.1K dossier) and FEAT-17 review (wrote a
  6.0K report). Everything else either crashed before writing (max-iterations), died on upstream
  Overload, hit its `-15` kill, or **phantom-completed** (exited 0, *claimed* a line count, wrote NO
  file).
- **Result:** FEAT-15/16/17 dossiers and FEAT-14/15/16 reviews were **re-authored/reconciled by me**,
  not by the free workers. The free-worker path was the *unreliable part*; the product only shipped
  because I verified artifacts and stood in.

**The single most important finding:** *"exit code 0" and even "I wrote N lines" are worthless as
success signals. Only a non-empty file existing at the exact declared path is real.*

---

## 1. The exact pipeline that was used

```
hermes chat --query-file <ASSIGN-*.md> -m <model> -t file [-t read] -Q \
    --no-restore-cwd --in /c/coding/pi-agent-factory \
    --max-turns N --run-budget R 2>&1 | tail -N
```
(background `terminal(background=true, notify_on_complete=true)`, one per FEAT, run in parallel)

Models: `nvidia/nemotron-3-ultra-550b-a55b:free` (primary), `deepseek/deepseek-v4-flash` (used for
the last reviews because nemotron kept overloading).

Brief structure: a shared VERIFIED-FACTS seed + one ASSIGN per FEAT, telling the agent to WRITE a
specific dossier/report path, then READ IT BACK and confirm non-empty. A WRITE-EARLY mandate was added
mid-session and later a "your first AND ONLY action is write_file, the full content is below" variant.

---

## 2. Launch-by-launch log (process id, task, model, outcome)

### Dev-authoring wave (author FEAT-14..17 dossiers)
| Proc | Task | Model | Outcome (observed) |
|---|---|---|---|
| proc_d3afdd1f | FEAT14 dev | nemotron | exited 0, but only show a `read_file(playground)` — **NO write** |
| proc_2e4386f7 | FEAT15 dev | nemotron | exited 0, only `read_file(synthesis)` — **NO write** |
| proc_730a92ec | FEAT16 dev | nemotron | exited 0, only `read_file(config)` — **NO write** |
| proc_8e8b7361 | FEAT17 dev | nemotron | **"max iterations (6) but couldn't summarize: 'NoneType' object is not subscriptable"** — NO write |
| proc_f92b45f9 | FEAT17 dev | nemotron | **Upstream "Service temporarily overloaded"** after 3 retries |
| proc_cf487481 | FEAT16 dev (retry) | nemotron | **"max iterations (4) couldn't summarize"** — NO write |
| proc_cc7166a6 | FEAT15 dev (retry) | nemotron | stuck on a `list_dir`, exited — **NO write** |
| proc_465f5835 | FEAT14 dev (retry) | nemotron | ✅ **SUCCESS — wrote FEAT-14 (16.1K)** |
| proc_1703fd8e | FEAT15 dev (embedded full content) | nemotron | killed `-15` mid-run — **NO write** |
| proc_7ac3c4cb | FEAT16 dev (embedded content) | nemotron | killed `-15` — **NO write** |
| proc_9b0b4331 | FEAT17 dev (embedded content) | nemotron | killed `-15` — **NO write** |

### Review wave (write FEAT-14..17 review reports)
| Proc | Task | Model | Outcome (observed) |
|---|---|---|---|
| proc_7749f8ce | FEAT14 review | nemotron | **Upstream overload** |
| proc_fc5f27ac | FEAT15 review | nemotron | **Upstream overload** |
| proc_70f4af5c | FEAT16 review | nemotron | exited, **claimed "194-line report" — NO file on disk (phantom)** |
| proc_c99e7177 | FEAT17 review | nemotron | ✅ **SUCCESS — wrote report-FEAT17.md (6.0K), PASS-WITH-NOTES** |
| proc_2c624374 | FEAT14 review (retry) | nemotron | **Upstream overload** |
| proc_8a08f5ab | FEAT15 review (retry) | **deepseek** | **"iteration limit, couldn't generate summary" — NO file** |
| proc_bc52b768 | FEAT14 review (retry) | **deepseek** | **claimed "278-line report" — NO file (phantom)** |
| proc_cfe0cbbb | FEAT16 review (retry) | **deepseek** | **"iteration limit" — NO file** |

---

## 3. Categorized failure modes (with evidence + root cause)

### F1. The silent no-write (most common success-shaped failure)
- **Evidence:** proc_d3afdd1f, 2e4386f7, 730a92ec, cc7166a6 — exit 0, no error, agent spent its turns
  READING (`read_file(playground)`, `list_dir(src/factory)`) and then just stopped; no write_file ever.
- **Root cause:** the worker's *first* instinct is to explore the repo to "ground" itself even though the
  brief already supplied a verified-facts seed. It burns its entire budget on reading and never reaches
  the write. In the Hermes harness the turn ends when the assistant stops emitting tool calls (or the
  budget/max-turns cuts in); a model that "responded" without calling write_file exits 0.
- **Why WRITE-EARLY didn't fix it:** the instruction ("write first, then verify symbols") is in a big
  text prompt; a real model reorders it under token pressure / exploration instinct. Text nudges are
  weak controls.

### F2. The max-iterations crash — "couldn't summarize: 'NoneType' object is not subscriptable"
- **Evidence:** proc_8e8b7361, cf487481, 8a08f5ab, cfe0cbbb.
- **Root cause:** the hermes `--max-turns N` (or `summarize` step) hit its limit while the worker was
  still mid-exploration and the summarizer threw on a None. The run aborts **without a final write** and
  the process still exits 0 (the summarizer's failure is swallowed as "completed normally").
- **Consequence:** a crashed run looks like success to the shell (exit 0), so automation that keys off
  exit code is blind to it.

### F3. Upstream model overload — "Service temporarily overloaded" (HTTP)
- **Evidence:** proc_f92b45f9, 7749f8ce, fc5f27ac, 2c624374, + the earlier `stealth/ox-alpha` 404.
- **Root cause:** hammering many `nemotron-3-ultra:free` jobs in **parallel** trips the free-tier
  upstream. Model availability is a real, recurring failure, not a rarity.

### F4. The `-15` kill (my own doing, avoidable)
- **Evidence:** proc_1703fd8e, 7ac3c4cb, 9b0b4331 (all from the "embedded full content + max-turns 2"
  batch).
- **Root cause:** I set `--max-turns 2 --run-budget 150` intending "just write the file" — but the
  harness's per-run overhead (tool-call roundtrips, summarize) exceeded budget and my `wait` timeout
  path killed it. Over-tightening the budget to force a one-shot write backfired.

### F5. Phantom completion — the worst one (exits 0, claims a line count, writes nothing)
- **Evidence:** proc_70f4af5c (FEAT16 review, claimed "194-line report") ; proc_bc52b768 (FEAT14 review,
  claimed "278-line report").
- **Root cause:** the model, at the end of its turn, *narrates* "I wrote the report (N lines)" — possibly
  it wrote to a DIFFERENT path, or only described the intended content, or the tool call didn't actually
  persist. The harness reports `completed normally` and hands me a confident `Line count: 194`.
- **This is the failure mode that burned the most:** I only caught it by independently `ls`-ing the
  declared report path and finding no file. There is NO signal in the process result that it lied.

---

## 4. What actually worked (so the reliable skill keeps these)

- **Extremely scoped, single-file, ground-truth-in-prompt tasks** succeed: the brief contained
  everything needed, so the worker didn't need to explore. FEAT-14 dev (seed + plain "write to X, read
  back, confirm non-empty") succeeded at 16.1K with real substance.
- **Independent on-disk verification is the ONLY reliable gate:** every success was caught by
  `ls <path>` + `wc -l`, never by the process result. FEAT-17 review was trusted only after its report
  file existed.
- **The reviewer role is more tractable than the author role for free models:** reviews are naturally
  "read + write one file"; authorship invites exploration. FEAT-17 review succeeded; the failed
  authors all "explored first."

---

## 5. Root-cause synthesis (the deeper why)

1. **No forcing function between "agent finished" and "artifact exists."** Nothing in the dispatch
   verifies the deliverable; the product shipped only because a human picked up the missing files.
2. **Exit code 0 is meaningless** here — it fires on crash, phantom, and success alike.
3. **Time/budget is spent on exploration, not delivery.** Free models, given latitude, explore the repo
   instead of executing the tiny declared write.
4. **Parallel fan-out on one free model amplifies F3 (overload).**
5. **The harness conflates "responded" with "delivered."**

This is, verbatim, the gap **FEAT-13 GOVERNED-EXECUTION-DRIVER / FEAT-16 MODULAR-WORKFLOWS** are meant
to close (a gate between nodes that proves the artifact exists). The retro is strong product evidence.

---

## 6. Requirements for the "reliable skill" (for the dedicated session)

The skill must NOT assume trust or free-model reliability. Film-based requirements:

- **R1 — Verify the artifact yourself, always.** After any dispatch, `ls`/`read_file` the EXACT declared
  output path; require non-empty. Reject "exit 0", reject claimed line counts, reject "report written".
  (Do this even when the process result looks fine.)
- **R2 — Scoped, self-contained briefs.** Full ground truth in the prompt; the worker must not need the
  repo. Explicitly forbid exploration: "do not read_files / list_dir / explore. Your only tool call is
  write_file."
- **R3 — One primary deliverable per worker.** Don't ask one worker to author + review. Authoring and
  review are different reliability profiles.
- **R4 — Retry discipline with model rotation.** On overload/429 or phantom, retry on a DIFFERENT model
  (nemotron → deepseek-v4-flash) rather than hammering the same one in parallel. Stagger parallel jobs.
- **R5 — Bounded budget that's actually enough.** Don't over-tighten (the `-15` kills). Give enough
  turns for a write + a read-back; don't expect a 2-turn one-shot to survive harness overhead.
- **R6 — Treat "N lines written" as UNVERIFIED until proven.** Add a real post-check: `wc -l <path>`.
- **R7 — When a task can't be made reliable, do it yourself.** The reliable skill must include the rule:
  if a free worker phantom/crashes twice, fall back to authoring the artifact yourself (with the worker
  reserved for genuine review), rather than spinning a third attempt.

---

## 7. Deliverable set (final state)

Authored dossiers (planning-only, never pushed):
- `docs/superpowers/specs/2026-08-27-feat14-validation-gates-design.md` (16.1K)
- `docs/superpowers/specs/2026-08-27-feat15-polish-flow-design.md` (7.6K)
- `docs/superpowers/specs/2026-08-27-feat16-modular-workflows-design.md` (11.6K)
- `docs/superpowers/specs/2026-08-27-feat17-planning-bootstrap-design.md` (7.5K)
Reconciliation: `Temp/coherence-ux-review/feat1417-review/FINAL-REVIEW.md`
Genuine external review: `Temp/coherence-ux-review/feat1417-review/report-FEAT17.md`

This retrospective should be read alongside the `free-worker-dev-gate-pipeline` skill
(the pool + 429-fallback model) and the reliability note already saved to memory.
