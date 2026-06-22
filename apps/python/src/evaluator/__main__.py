from __future__ import annotations

import argparse
import sys

from src.evaluator import extract, report, score


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m src.evaluator")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("extract", "score"):
        p = sub.add_parser(name)
        p.add_argument("target", nargs="?", default="all")
    sub.add_parser("report")
    try:
        args = parser.parse_args(argv)
    except SystemExit:
        return 2
    if args.cmd == "extract":
        extract.extract(args.target)
    elif args.cmd == "score":
        score.score(args.target)
    elif args.cmd == "report":
        report.build_report()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
