"""Live smoke test for PlaywrightE2EHarness — the Increment 2 "stochastic + live" proof.

Unlike the unit tests (which inject a fake trial-runner and score recorded reporter
JSON), this actually shells out to Playwright against the CareerOS webapp and folds
the real reporter output into a HarnessResult. Guard-skips when the webapp, npx, or
a Playwright browser build is unavailable so a checkout without them stays green.
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import pytest

from factory.polish.config import load_config
from factory.requirements.register import Binding

CAREEROS = Path("C:/coding/markdown_pdf_system")

# SR-010's binding: Playwright's positional filter is a *file-path* substring, so
# this must name the real spec (frontend/e2e/login.spec.ts), not the flow's prose
# name. Kept in sync with markdown_pdf_system/requirements/SR-010.md.
EXPERIMENT = "login"


def _browser_installed() -> bool:
    """True if a Playwright chromium build exists in the browser cache.

    Without this, `npx playwright test` exits non-zero before writing a report and
    the harness raises FileNotFoundError instead of skipping.
    """
    override = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    if override:
        cache = Path(override)
    elif sys.platform == "win32":
        cache = Path(os.environ.get("LOCALAPPDATA", "")) / "ms-playwright"
    elif sys.platform == "darwin":
        cache = Path.home() / "Library" / "Caches" / "ms-playwright"
    else:
        cache = Path.home() / ".cache" / "ms-playwright"
    return any(cache.glob("chromium*")) if cache.is_dir() else False


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not (CAREEROS / "frontend").exists()
        or shutil.which("npx") is None
        or not _browser_installed(),
        reason="CareerOS frontend, npx, or a Playwright browser build is unavailable",
    ),
]


def test_signin_sr_validates_live(tmp_path):
    harness = load_config(CAREEROS).harnesses["web-e2e"]
    binding = Binding(
        harness="web-e2e",
        experiment=EXPERIMENT,
        metric="e2e_pass_rate",
        assert_expr=">= 0.95",
        trials=2,
    )

    res = harness.run(binding, tmp_path)

    assert 0.0 <= res.metric_value <= 1.0
    assert len(res.trials) == 2
    assert [t.seed for t in res.trials] == [0, 1]
    # a report file was produced for each trial
    assert len(list(tmp_path.glob("pw-report-seed*.json"))) == 2
