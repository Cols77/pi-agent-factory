"""/catchup command shim (spec §31, Inc 7 Task 3).

`/catchup <feature>` answers "what changed since the developer's last
review" for one feature. The delta itself is computed deterministically by
``factory.delta.compute`` from recorded sources (git history, goal
transition logs, simulation run bundles) -- never an LLM summary of the
past.

The shim:

* loads the feature's recorded checkpoint (`.pi/checkpoints.json`);
* computes the ``ContextDelta`` since that checkpoint commit;
* upgrades the checkpoint to HEAD (the delta has now been shown);
* routes the REVIEW presentation through the Inc 5 router to the SCC
  browser (the Catch-me-up view, Inc 7 Task 3 step 3).

A feature with no recorded review is reported honestly ("no review
recorded yet") -- never synthesized from nothing.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from factory.delta.checkpoint import Checkpoint, load_checkpoint, save_checkpoint
from factory.delta.compute import compute_delta
from factory.delta.freshness import apply_freshness
from factory.delta import git_ops
from factory.presentation.level import Level
from factory.presentation.router import present


def _now_iso() -> str:
    """The checkpoint's reviewed-at timestamp (recorded, not derived)."""
    return datetime.now(timezone.utc).isoformat()


def run_catchup(
    root: Path,
    feature: str,
    *,
    verify_understanding: bool = False,
    checkpoint_dir: Path | None = None,
) -> dict:
    """Execute `/catchup <feature>` and return its structured outcome.

    ``checkpoint_dir`` overrides the `.pi` directory (tests use a scratch
    dir). Never raises for a missing checkpoint; raises ``ValueError`` when
    the feature or the checkpoint commit cannot be resolved (an unresolvable
    base must never silently read as "nothing changed").
    """
    pi_dir = checkpoint_dir if checkpoint_dir is not None else root / ".pi"
    checkpoint = load_checkpoint(pi_dir, feature)
    head = git_ops.head_commit(root)

    if checkpoint is None:
        # No review recorded yet -- legitimate, never an error (spec §31).
        outcome = {
            "feature": feature,
            "reviewed": False,
            "since_commit": None,
            "delta": None,
            "verify_understanding": verify_understanding,
        }
        outcome["presentation"] = present(root, f"catchup:{feature}", level=Level.REVIEW)
        return outcome

    delta = compute_delta(root, feature, checkpoint.commit)
    delta = apply_freshness(root, delta)

    if head is not None and head != checkpoint.commit:
        save_checkpoint(
            pi_dir,
            Checkpoint(feature=feature, commit=head, reviewed_at=_now_iso()),
        )

    outcome = {
        "feature": feature,
        "reviewed": True,
        "since_commit": checkpoint.commit,
        "reviewed_at": checkpoint.reviewed_at,
        "delta": asdict(delta),
        "verify_understanding": verify_understanding,
    }
    outcome["presentation"] = present(root, f"catchup:{feature}", level=Level.REVIEW)
    return outcome
