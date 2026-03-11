from __future__ import annotations

import json
import os
import shutil
import subprocess  # nosec B404: subprocess used safely with static args and shell=False in this maintenance script
from typing import Iterable, List, Tuple, Any, Dict


def git_ls_files() -> list[str]:
    git = shutil.which("git")
    if not git:
        raise RuntimeError("git executable not found in PATH")
    # No user input involved; passing argv list (no shell) prevents injection
    cp = subprocess.run([git, "ls-files", "-z"], capture_output=True, check=True)  # nosec B603: static argv, shell=False, no untrusted input
    out = cp.stdout
    return [p.decode("utf-8", "ignore") for p in out.split(b"\x00") if p]


def count_lines(paths: Iterable[str]) -> int:
    total = 0
    for p in paths:
        try:
            with open(p, "rb") as fh:
                total += sum(1 for _ in fh)
        except (OSError, UnicodeDecodeError):
            # skip unreadable/binary
            pass
    return total


def count_file_lines(path: str) -> int:
    try:
        with open(path, "rb") as fh:
            return sum(1 for _ in fh)
    except (OSError, UnicodeDecodeError):
        return 0


def main() -> None:
    files = git_ls_files()

    norm = [p.replace("\\", "/") for p in files]

    py = [p for p in norm if p.endswith(".py")]
    py_tests = [p for p in py if p.startswith("tests/")]
    py_src = [p for p in py if p not in py_tests]

    md = [p for p in norm if p.startswith("docs/") and p.endswith(".md")]
    md_all = [p for p in norm if p.endswith(".md")]
    ts = [p for p in norm if p.endswith(".ts") or p.endswith(".tsx")]
    cfg_exts = (".toml", ".yaml", ".yml", ".ini", ".json", ".txt", ".sh", ".ps1")
    cfg = [p for p in norm if p.endswith(cfg_exts)]

    lockfiles = [p for p in norm if p.endswith(".lock")]
    mako = [p for p in norm if p.endswith(".mako")]
    dockerfiles = [p for p in norm if os.path.basename(p) == "Dockerfile"]
    procfiles = [p for p in norm if os.path.basename(p) == "Procfile"]

    res: Dict[str, Any] = {
        "python_total": count_lines(py),
        "python_tests": count_lines(py_tests),
        "python_src": count_lines(py_src),
        "markdown_docs": count_lines(md),
        "markdown_all": count_lines(md_all),
        "ts_total": count_lines(ts),
        "config_text": count_lines(cfg),
        "lockfiles": count_lines(lockfiles),
        "mako_templates": count_lines(mako),
        "dockerfiles": count_lines(dockerfiles),
        "procfiles": count_lines(procfiles),
        "all_tracked_lines": count_lines(norm),
    }
    # Convenience: selected text categories total
    res["selected_text_total"] = (
        res["python_total"] + res["markdown_docs"] + res["ts_total"] + res["config_text"]
    )

    # Non-Python breakdown and top contributors
    non_py = [p for p in norm if not p.endswith(".py")]
    res["non_python_total"] = res["all_tracked_lines"] - res["python_total"]

    # Top non-Python files by size
    sizes: List[Tuple[str, int]] = [(p, count_file_lines(p)) for p in non_py]
    sizes.sort(key=lambda x: x[1], reverse=True)
    res["top_non_python"] = [
        {"path": p, "lines": n} for p, n in sizes[:15]
    ]

    print(json.dumps(res))


if __name__ == "__main__":
    main()
