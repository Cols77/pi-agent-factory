from __future__ import annotations

import argparse
from pathlib import Path

from substrate.codemap.build import (
    build_index,
    discover_source_files,
    render_index_slice,
)
from substrate.codemap.store import ensure_fresh, save_index


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="substrate.codemap.build")
    parser.add_argument("--root", type=Path, default=Path("."), help="repo root")
    parser.add_argument(
        "--ensure",
        action="store_true",
        help="rebuild only if the code changed (cheap checksum compare); reuse a fresh index",
    )
    parser.add_argument(
        "--slice",
        type=int,
        default=0,
        metavar="CHARS",
        help="print a bounded, token-budgeted markdown slice of the project's code "
        "index to stdout (without hash/count banner lines). Ensures freshness "
        "first, exactly like --ensure; 0 (default) prints nothing.",
    )
    args = parser.parse_args(argv)

    repo_root: Path = args.root.resolve()
    files = discover_source_files(repo_root)
    if not files:
        print("codeindex: no code files found; wrote no index")
        return 0
    if args.slice:
        index = ensure_fresh(repo_root, files)
        body = render_index_slice(index, sorted(index.files.keys()), cap=args.slice)
        # One-line engine note so consumers (e.g. the code-context injection) can
        # tell whether the slice came from tree-sitter or the stdlib fallback.
        print(f"engine: {index.engine}")
        print(body)
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
