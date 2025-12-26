#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


DEFAULT_EXCLUDES = {
    ".venv",
    ".git",
    "__pycache__",
    "logs",
    "archive",
}


PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("sqlalchemy.text f-string", re.compile(r"\btext\s*\(\s*f([\"'])")),
    ("execute f-string", re.compile(r"\.execute\s*\(\s*f([\"'])")),
    ("cursor.execute f-string", re.compile(r"\bcursor\.execute\s*\(\s*f([\"'])")),
    ("execute_text f-string", re.compile(r"\bexecute_text\s*\(\s*f([\"'])")),
]


def iter_py_files(root: Path, *, excludes: set[str]) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*.py"):
        rel_parts = path.relative_to(root).parts
        if any(part in excludes for part in rel_parts):
            continue
        files.append(path)
    return files


def scan_file(path: Path) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        text = path.read_text(encoding="utf-8", errors="replace")
    hits: list[str] = []
    for i, line in enumerate(text.splitlines(), start=1):
        for label, pattern in PATTERNS:
            if pattern.search(line):
                hits.append(f"{path}:{i}: {label}: {line.strip()}")
    return hits


def main() -> int:
    parser = argparse.ArgumentParser(description="Fail on common SQL-injection-prone patterns.")
    parser.add_argument(
        "--root",
        default=".",
        help="Repository root to scan (default: .)",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        help="Path segment to exclude (repeatable).",
    )
    args = parser.parse_args()
    root = Path(args.root).resolve()
    excludes = set(DEFAULT_EXCLUDES) | set(args.exclude)

    failures: list[str] = []
    for file_path in iter_py_files(root, excludes=excludes):
        failures.extend(scan_file(file_path))

    if failures:
        print("SQL safety check failed; found f-string SQL patterns:", file=sys.stderr)
        for failure in failures:
            print(failure, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

