#!/usr/bin/env python3
"""Fail only on Ruff/format findings that overlap changed app/test lines."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def run_git(*args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def normalize_path(path: str) -> str:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = ROOT / candidate
    return candidate.resolve().relative_to(ROOT).as_posix()


def line_is_changed(
    ranges: dict[str, list[tuple[int, int]]], path: str, line: int
) -> bool:
    return any(start <= line <= end for start, end in ranges.get(path, []))


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: check_quality_regressions.py BASE_SHA", file=sys.stderr)
        return 2

    base = sys.argv[1]
    try:
        run_git("cat-file", "-e", f"{base}^{{commit}}")
        changed = run_git(
            "diff",
            "--name-only",
            "-z",
            "--no-renames",
            "--diff-filter=ACMT",
            base,
            "--",
            "app",
            "tests",
        ).split("\0")
        diff = run_git(
            "diff",
            "--unified=0",
            "--no-ext-diff",
            "--no-color",
            "--no-renames",
            base,
            "--",
            "app",
            "tests",
        )
    except subprocess.CalledProcessError as exc:
        print(f"Unable to compare against base commit {base}: {exc.stderr.strip()}")
        return 2

    paths = sorted({path for path in changed if path.endswith(".py")})
    ranges: dict[str, list[tuple[int, int]]] = {}
    current_path = ""
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            current_path = line[6:]
        elif line.startswith("+++ "):
            current_path = ""
        match = HUNK_RE.match(line)
        if match and current_path.endswith(".py"):
            start = int(match.group(3))
            count = int(match.group(4) or "1")
            if count:
                ranges.setdefault(current_path, []).append((start, start + count - 1))

    if not paths:
        print("No changed app/tests Python files; Ruff regression gate passed.")
        return 0

    lint = subprocess.run(
        ["ruff", "check", "--output-format=json", *paths],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if lint.returncode not in (0, 1):
        print(lint.stderr, file=sys.stderr)
        return lint.returncode

    try:
        findings = json.loads(lint.stdout or "[]")
    except json.JSONDecodeError:
        print("Ruff did not return parseable JSON output.", file=sys.stderr)
        return 2

    regressions: list[str] = []
    for finding in findings:
        path = normalize_path(finding["filename"])
        row = finding["location"]["row"]
        if line_is_changed(ranges, path, row):
            regressions.append(f"{path}:{row}: {finding['code']} {finding['message']}")

    formatting = subprocess.run(
        ["ruff", "format", "--diff", *paths],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if formatting.returncode not in (0, 1):
        print(formatting.stderr or formatting.stdout, file=sys.stderr)
        return formatting.returncode

    format_path = ""
    old_line = 0
    format_regressions: list[str] = []
    for line in (formatting.stdout + formatting.stderr).splitlines():
        if line.startswith("--- "):
            format_path = normalize_path(line[4:])
        elif line.startswith("+++ "):
            continue
        else:
            match = HUNK_RE.match(line)
            if match:
                old_line = int(match.group(1))
                old_count = int(match.group(2) or "1")
                if old_count == 0 and any(
                    line_is_changed(ranges, format_path, adjacent)
                    for adjacent in (max(1, old_line - 1), old_line)
                ):
                    format_regressions.append(
                        f"{format_path}:{old_line}: formatting change"
                    )
            elif line.startswith("-") and not line.startswith("---"):
                if line_is_changed(ranges, format_path, old_line):
                    format_regressions.append(
                        f"{format_path}:{old_line}: formatting change"
                    )
                old_line += 1
            elif line.startswith(" "):
                old_line += 1

    if regressions or format_regressions:
        if regressions:
            print("Ruff findings on changed app/tests lines:")
            print("\n".join(regressions))
        if format_regressions:
            print("Formatting regressions on changed app/tests lines:")
            print("\n".join(format_regressions))
        return 1

    print(
        f"Ruff and format regression gate passed for {len(paths)} changed app/tests Python file(s)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
