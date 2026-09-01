from __future__ import annotations

import argparse
from pathlib import Path

from coherence.mirrors.generate import check_all, regenerate_all


def cmd_generate(root: Path) -> str:
    results = regenerate_all(root)
    changed = [r.feature_id for r in results if r.changed]
    lines = [f"wikilink mirrors: {len(results)} feature dossier(s) processed"]
    if changed:
        lines.append(f"regenerated: {', '.join(changed)}")
    else:
        lines.append("no changes -- every mirror already matched its derivation")
    return "\n".join(lines)


def _add_root(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--project-root", default=Path("."), type=Path)


def _parser(prog: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=prog)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_generate = sub.add_parser("generate")
    _add_root(p_generate)

    p_check = sub.add_parser("check")
    _add_root(p_check)

    return parser


def main(argv: list[str] | None = None, *, prog: str = "coherence-mirrors") -> int:
    parser = _parser(prog)
    args = parser.parse_args(argv)

    if args.cmd == "generate":
        print(cmd_generate(args.project_root))
        return 0
    elif args.cmd == "check":
        text, code = check_all(args.project_root)
        print(text)
        return code
    return 0
