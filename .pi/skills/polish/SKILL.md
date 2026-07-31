---
name: polish
description: Run a factory polish session — set up a project use case's playground, gather the human's natural-language feedback, synthesize it into fix-tickets, confirm, and route them to the task ledger.
---

# Polish session

Use this when the human wants to exercise a real use case and turn what they find
into fix-work, without leaving the pi session.

## Steps

1. **Discover.** Run `python -m factory.polish list --project-root <repo>` to list
   `<playground>:<usecase>` options. Help the human pick one (respect an explicit
   `--usecase`).
2. **Set up + open.** The playground's `setup(usecase)` spins up the environment
   and returns `entrypoints`; open the navigator to them (the CLI's `run` path
   calls `open_navigator`, or open them yourself). Tell the human what is running
   and where.
3. **Gather feedback conversationally.** Invite the human to play around and say,
   in their own words, what went wrong. Accumulate every distinct issue. Ask
   clarifying questions; capture reproducible detail (route/steps/state) as a
   `snapshot`, and any screenshots as `artifacts`. If an issue clearly violates a
   known requirement, note its `SR-###`.
4. **Synthesize + confirm.** When the human is done, present a numbered list of
   proposed tickets (title + one-line description + linked `SR-###` if any) and a
   short summary of the actions you will take. Do NOT create anything yet.
5. **Route on confirmation.** Only after the human confirms, write the findings to
   a JSON array and run
   `python -m factory.polish run --project-root <repo> --playground <name> --usecase <uc> --from-json <file>`.
   Report the created `T-###` task paths.
6. **Teardown.** The session tears the environment down automatically; confirm it
   is down before ending.

## Rules

- Nothing is written to the ledger until the human confirms the summarized actions.
- One ticket per distinct issue; if two findings look like duplicates, surface that
  in the confirm step and let the human merge.
- A finding may target the *validation itself* (a requirement's check is hollow),
  not only the implementation — capture that faithfully in the ticket.
