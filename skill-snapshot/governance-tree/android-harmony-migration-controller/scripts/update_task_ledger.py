#!/usr/bin/env python3
"""Controlled CSV reader/writer for controller/task-ledger.csv (P1BUG-01).

Agents MUST NOT edit task-ledger.csv with text-editing tools: hand edits have
already introduced trailing commas (9 fields vs the 8-column header) that make
csv.DictWriter fail with an opaque extrasaction error. This tool is the only
supported mutation path: it validates every row against the header, refuses
unknown columns, stamps ``updated_at`` automatically, and rewrites the file
atomically (tempfile + os.replace) with the template's LF line terminator.

Usage:
    update_task_ledger.py --run-dir <run> --phase 1 --set owner=<actor-id>
    update_task_ledger.py --run-dir <run> --phase 1 --list
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


LEDGER_RELATIVE = "controller/task-ledger.csv"
MANAGED_COLUMN = "updated_at"  # stamped by this tool, never by --set
LINE_TERMINATOR = "\n"  # matches assets/task-ledger.template.csv


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_ledger(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    """Read the ledger and fail on any ragged row (extra or missing columns)."""
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        rows: list[dict[str, str]] = []
        for row in reader:
            if None in row or any(value is None for value in row.values()):
                raise ValueError(
                    f"task-ledger row {reader.line_num} does not match its header "
                    f"{fieldnames} (extra or missing columns) in {path}"
                )
            rows.append(row)
    if not fieldnames:
        raise ValueError(f"Task ledger has no usable header: {path}")
    return fieldnames, rows


def write_ledger_atomic(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    if path.is_symlink():
        raise ValueError(f"Refusing symbolic-link task ledger: {path}")
    descriptor, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temp = Path(temp_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=fieldnames,
                extrasaction="raise",
                lineterminator=LINE_TERMINATOR,
            )
            writer.writeheader()
            writer.writerows(rows)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        try:
            temp.unlink()
        except OSError:
            pass


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True, help="Migration run directory")
    parser.add_argument("--phase", required=True, type=int, help="Phase row to update or list")
    parser.add_argument(
        "--set",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Column update for the phase row; repeatable",
    )
    parser.add_argument("--list", action="store_true", help="Print the phase row and exit")
    args = parser.parse_args()

    run_input = Path(args.run_dir).expanduser().absolute()
    if run_input.is_symlink():
        parser.error("Migration run must not be a symbolic link")
    run_dir = run_input.resolve()
    path = run_dir / LEDGER_RELATIVE
    if not path.is_file():
        parser.error(f"Task ledger does not exist: {path}")

    try:
        fieldnames, rows = read_ledger(path)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    matches = [row for row in rows if row.get("phase") == str(args.phase)]
    if len(matches) != 1:
        print(
            f"error: expected exactly one phase {args.phase} row, found {len(matches)} in {path}",
            file=sys.stderr,
        )
        return 1

    if args.list:
        for key in fieldnames:
            print(f"{key}={matches[0].get(key, '')}")
        return 0

    updates: dict[str, str] = {}
    for item in args.set:
        if "=" not in item:
            parser.error(f"--set expects KEY=VALUE, got {item!r}")
        key, _, value = item.partition("=")
        if key not in fieldnames:
            print(
                f"error: unknown column {key!r}; allowed columns are {fieldnames}",
                file=sys.stderr,
            )
            return 1
        if key == MANAGED_COLUMN:
            print(
                f"error: {MANAGED_COLUMN} is stamped automatically by this tool and "
                "cannot be set manually",
                file=sys.stderr,
            )
            return 1
        updates[key] = value

    for key, value in updates.items():
        matches[0][key] = value
    if updates:
        matches[0][MANAGED_COLUMN] = utc_now()
        try:
            write_ledger_atomic(path, fieldnames, rows)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1

    print(f"updated {path} phase {args.phase}: {', '.join(sorted(updates)) or 'no changes'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())