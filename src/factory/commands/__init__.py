"""Pi-command handlers that delegate to the deterministic Python core.

Each module here parses a user-facing command line and calls into the engine
(`factory.goals`, `factory.system`, ...). The command shim never re-derives
state the core already owns; it only wires user input to the core's functions.
"""