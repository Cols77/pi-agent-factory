from __future__ import annotations

import argparse
from pathlib import Path

from factory.codeindex.build import build_index, discover_source_files
from factory.codeindex.store import ensure_fresh, save_index


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="factory.codeindex.build")
    parser.add_argument("--root", type=Path, default=Path("."), help="repo root")
    parser.add_argument(
        "--ensure",
        action="store_true",
        help="rebuild only if the code changed (cheap checksum compare); reuse a fresh index",
    )
    args = parser.parse_args(argv)

    repo_root: Path = args.root.resolve()
    files = discover_source_files(repo_root)
    if not files:
        print("codeindex: no code files found; wrote no index")
        return 0
    if args.ensure:
        index = ensure_fresh(repo_root, files)
        print(
            f"codeindex: ensured {index.engine} index over {len(files)} files "
            f"(fingerprint {index.fingerprint})"
        )
        return 0
    index = build_index(repo_root, files)
    save_index(index, repo_root)
    print(
        f"codeindex: built {index.engine} index over {len(files)} files -> "
        f".factory/code-index/{index.fingerprint}.json"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
