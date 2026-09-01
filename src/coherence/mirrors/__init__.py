"""Generated wikilink mirrors for feature dossiers (design decision D-P8).

A feature dossier's ``## Related requirements`` section is a plain-Markdown
mirror of its own ``requirements:`` frontmatter, meant for Obsidian's graph
view (D-P7: Obsidian is a read-only navigable projection, never a write
surface or a second source of truth). Hand-maintaining that mirror lets it
drift from the frontmatter it is supposed to reflect -- exactly what
happened at ``docs/features/FEAT-006.md``, whose mirror used an Obsidian
*embed* (``![[SR-019]]``) where every other entry, in every other dossier,
is a plain *link* (``[[SR-019]]``). Membership was correct; only the syntax
drifted, silently, because a human was maintaining generated output by hand
(NC-D).

This package makes the block generated output instead: :mod:`.generate`
derives it from the dossier's own frontmatter (cross-checked against the
trace graph's ``contains`` edges for the same feature node) and
:mod:`.cli` exposes ``coherence mirrors generate`` / ``coherence mirrors
check`` the same way ``coherence trace``/``coherence register`` expose
their own ``check``.
"""

from __future__ import annotations
