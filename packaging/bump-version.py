#!/usr/bin/env python3
"""Bump the launcher version used by Python metadata and Debian packaging."""

import argparse
from pathlib import Path
import re


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("part", nargs="?", choices=("patch", "minor", "major"), default="patch")
    parser.add_argument("--dry-run", action="store_true", help="Show the next version without writing files")
    args = parser.parse_args()
    version_file = Path(__file__).resolve().parents[1] / "src/mclauncher/__init__.py"
    source = version_file.read_text(encoding="utf-8")
    pattern = r'^__version__ = "(\d+)\.(\d+)\.(\d+)"$'
    matches = list(re.finditer(pattern, source, re.MULTILINE))
    if len(matches) != 1:
        parser.error(f"Expected one stable X.Y.Z __version__ in {version_file}")
    match = matches[0]
    parts = [int(value) for value in match.groups()]
    index = {"major": 0, "minor": 1, "patch": 2}[args.part]
    parts[index] += 1
    for trailing in range(index + 1, 3):
        parts[trailing] = 0
    version = ".".join(map(str, parts))
    if not args.dry_run:
        source = source[:match.start()] + f'__version__ = "{version}"' + source[match.end():]
        version_file.write_text(source, encoding="utf-8")
    print(f"{'.'.join(match.groups())} -> {version}" + (" (dry run)" if args.dry_run else ""))


if __name__ == "__main__":
    main()
