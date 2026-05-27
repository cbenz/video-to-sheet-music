from __future__ import annotations

import argparse
import sys

from . import combine as combine_cli
from . import extract as extract_cli


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    parser = argparse.ArgumentParser(
        prog="video-to-sheet-music",
        description="Convert a slideshow video into a printable A4 PDF.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    extract_parser = sub.add_parser(
        "extract-images",
        help="Extract distinct frames from a slideshow video",
    )
    extract_cli.build_parser(extract_parser)

    combine_parser = sub.add_parser(
        "combine-images",
        help="Combine PNG images into an A4 portrait PDF",
    )
    combine_cli.build_parser(combine_parser)

    args, remaining = parser.parse_known_args(argv)

    if remaining:
        sub_argv = remaining
    else:
        # All args consumed by the top-level parser — strip subcommand name
        sub_argv = argv[1:]

    if args.command == "extract-images":
        return extract_cli.main(sub_argv)
    elif args.command == "combine-images":
        return combine_cli.main(sub_argv)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
