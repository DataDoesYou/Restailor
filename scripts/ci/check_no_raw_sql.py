from __future__ import annotations

import re
import sys
from pathlib import Path


# Directories to scan (runtime code only)
INCLUDE_DIRS = [
    Path("restailor"),
    Path("services"),
]

# Individual files at repo root that are runtime
INCLUDE_FILES = [
    Path("main.py"),
    Path("worker.py"),
]

# Exclusions
EXCLUDE_DIRS = {
    "tests",
    "scripts",
    "alembic",
    "e2e",
    "docs",
    "pages",
}


PATTERNS = [
    # Block f-strings passed to common SQL entrypoints
    re.compile(r"\b(text|sa\.text)\s*\(\s*f[\"']", re.IGNORECASE),
    re.compile(r"\b(execute|executesql)\s*\(\s*f[\"']", re.IGNORECASE),
]


def iter_python_files(base: Path):
    for p in base.rglob("*.py"):
        if any(part in EXCLUDE_DIRS for part in p.parts):
            continue
        yield p


def scan_file(path: Path) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return []
    hits: list[str] = []
    for pat in PATTERNS:
        for m in pat.finditer(text):
            # rough line number calc
            lineno = text.count("\n", 0, m.start()) + 1
            snippet = text[m.start() : m.start() + 120].splitlines()[0]
            hits.append(f"{path.as_posix()}:{lineno}: {snippet.strip()}")
    return hits


def main() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    to_scan = []
    for d in INCLUDE_DIRS:
        dir_path = repo_root / d
        if dir_path.is_dir():
            to_scan.extend(iter_python_files(dir_path))
    for f in INCLUDE_FILES:
        fpath = repo_root / f
        if fpath.is_file():
            to_scan.append(fpath)

    violations: list[str] = []
    for file in to_scan:
        violations.extend(scan_file(file))

    if violations:
        print("Found disallowed f-string SQL patterns in runtime code:")
        for v in violations:
            print("  ", v)
        print("\nUse SQLAlchemy bind parameters instead of f-strings with text()/execute().")
        return 1

    print("SQL safety check passed: no disallowed f-string SQL in runtime code.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
