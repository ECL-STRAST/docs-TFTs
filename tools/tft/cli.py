"""The command line. Knows about services, never about git or latexmk."""

import argparse
import sys
from pathlib import Path

from . import config
from .catalog import Catalog
from .entry import THESIS, TYPES
from .errors import TftError
from .ingest import Ingest

ROOT_MARKER = "pyproject.toml"


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)

    try:
        return args.run(args)
    except (TftError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def find_root(start: Path) -> Path:
    """The repository root, found by walking up from start."""
    for folder in [start, *start.parents]:
        if (folder / ROOT_MARKER).is_file():
            return folder

    raise TftError(f"no {ROOT_MARKER} above {start}")


def _catalog() -> Catalog:
    return Catalog(config.load(find_root(Path.cwd())))


def _ingest() -> Ingest:
    cfg = config.load(find_root(Path.cwd()))

    return Ingest(cfg, Catalog(cfg))


def _add(args) -> int:
    slug = f"{args.year}-{args.name}"
    folder = _ingest().add(
        project_id=args.overleaf, slug=slug, year=args.year,
        title=args.title, author=args.author, type=args.type, degree=args.degree,
    )
    print(f"created {folder}; now fill in summary.md and topics")

    return 0


def _sync(args) -> int:
    changed = _ingest().sync(args.slug)
    print(f"{args.slug}: {'updated' if changed else 'unchanged'}")

    return 0


def _validate(args) -> int:
    problems = _catalog().problems()

    for problem in problems:
        print(problem)

    if problems:
        return 1

    print("ok")

    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tft", description="Catalog tooling")
    subs = parser.add_subparsers(dest="command", required=True)

    add = subs.add_parser("add", help="add an entry from an Overleaf project")
    add.add_argument("--overleaf", required=True, metavar="ID", help="Overleaf project id")
    add.add_argument("--name", required=True, help="slug without the year, e.g. surname-topic")
    add.add_argument("--year", required=True, type=int, help="expected defence year")
    add.add_argument("--title", required=True)
    add.add_argument("--author", required=True)
    add.add_argument("--type", default=THESIS, choices=TYPES)
    add.add_argument("--degree", default="bachelor")
    add.set_defaults(run=_add)

    sync = subs.add_parser("sync", help="re-pull and recompile an entry")
    sync.add_argument("slug")
    sync.set_defaults(run=_sync)

    validate = subs.add_parser("validate", help="check every entry")
    validate.set_defaults(run=_validate)

    return parser
