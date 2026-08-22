# Shared helpers for tests under tests/unit/. pytest prepend-mode import
# adds this directory to sys.path, so `_seed_repo.py` and other non-test
# helpers here are importable from any test module under unit/.