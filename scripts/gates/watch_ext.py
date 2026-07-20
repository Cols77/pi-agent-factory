import sys
from pathlib import Path
from _proc import run_and_propagate

EXT_DIR = Path(__file__).resolve().parents[2] / "pi-ext" / "factory-watch"

if __name__ == "__main__":
    # npm on Windows is npm.cmd; shell=False needs the resolved name.
    npm = "npm.cmd" if sys.platform == "win32" else "npm"
    code = run_and_propagate([npm, "--prefix", str(EXT_DIR), "run", "typecheck"])
    if code != 0:
        sys.exit(code)
    sys.exit(run_and_propagate([npm, "--prefix", str(EXT_DIR), "test"]))
