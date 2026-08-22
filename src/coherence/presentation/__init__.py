"""Presentation router (Engineering-Context Increment 5, spec §22-§24).

Mediates semantic presentation intents to human-facing adapters behind three
deterministic levels (INSPECT/PRESENT/REVIEW) and a noise policy (never open
UI for every lookup). This sits behind the ``eng_present`` pi-ext tool (Inc 4).

Adapters (IDE, SCC browser, simulation) are independently replaceable and are
resolved from the router by scope kind — the router never shells out with
unvalidated user strings (path-traversal guard) and never re-derives graph
layout in TS (D7: diagrams are committed reviewable HTML).
"""

