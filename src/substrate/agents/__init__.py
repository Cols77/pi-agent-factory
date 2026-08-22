"""Neutral agent-subprocess composition: a role-agnostic Pi backend and skill
loader shared across factory capabilities. Nothing here knows about
AgentRole, role catalogues, or prompts -- callers inject a `scope_for`
callable and a role string."""
