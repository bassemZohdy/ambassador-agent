#!/usr/bin/env python3
"""Check the repository's Markdown: relative links, image targets, heading anchors and required content.

Usage:
    python3 tools/check_docs.py PATH [PATH ...] [--require TEXT] [--forbid TEXT] [--reachable-from FILE]

PATH is a Markdown file or a directory. Directories are walked for *.md files, skipping
hidden directories, `node_modules` and `plans` (backlog plans are not published pages).
A file named explicitly is always checked.

    --require TEXT          TEXT must appear in at least one checked file (case-insensitive). Repeatable.
    --forbid TEXT           TEXT must not appear in any checked file (case-insensitive). Repeatable.
    --reachable-from FILE   every checked file must be reachable from FILE through relative links.

External links (http, https, mailto) are not fetched. Exit status is 0 when clean, 1 otherwise.
Read-only: it never changes a file. Standard library only.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

SKIPPED_DIRS = {"node_modules", "plans"}
LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")  # links and images
HEADING = re.compile(r"^#{1,6}\s+(.*?)\s*#*\s*$")
INLINE_CODE = re.compile(r"`[^`]*`")
EXTERNAL = ("http://", "https://", "mailto:")


def markdown_files(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    found = []
    for candidate in sorted(path.rglob("*.md")):
        parts = candidate.relative_to(path).parts[:-1]
        if any(part.startswith(".") or part in SKIPPED_DIRS for part in parts):
            continue
        found.append(candidate)
    return found


def prose_lines(text: str) -> list[tuple[int, str]]:
    """Lines outside fenced code blocks, with inline code removed."""
    lines, fenced = [], False
    for number, line in enumerate(text.splitlines(), start=1):
        if line.lstrip().startswith(("```", "~~~")):
            fenced = not fenced
            continue
        if not fenced:
            lines.append((number, INLINE_CODE.sub("", line)))
    return lines


def slug(heading: str) -> str:
    """GitHub-style anchor for a heading."""
    text = re.sub(r"[*_`]|\[([^\]]*)\]\([^)]*\)", lambda m: m.group(1) or "", heading).strip().lower()
    text = re.sub(r"[^\w\- ]", "", text)
    return text.replace(" ", "-")


def anchors(path: Path) -> set[str]:
    seen: dict[str, int] = {}
    result = set()
    for _, line in prose_lines(path.read_text(encoding="utf-8")):
        match = HEADING.match(line)
        if not match:
            continue
        base = slug(match.group(1))
        count = seen.get(base, 0)
        seen[base] = count + 1
        result.add(base if count == 0 else f"{base}-{count}")
    return result


def links(path: Path) -> list[tuple[int, str]]:
    found = []
    for number, line in prose_lines(path.read_text(encoding="utf-8")):
        found.extend((number, target) for target in LINK.findall(line))
    return found


def check_links(path: Path) -> tuple[list[str], set[Path]]:
    """Return problems in `path` and the Markdown files it links to."""
    problems, targets = [], set()
    for number, target in links(path):
        if target.startswith(EXTERNAL):
            continue
        file_part, _, anchor = target.partition("#")
        destination = (path.parent / file_part).resolve() if file_part else path.resolve()
        if not destination.exists():
            problems.append(f"{path}:{number}: broken link: {target}")
            continue
        if destination.suffix == ".md" and destination.is_file():
            targets.add(destination)
            if anchor and anchor.lower() not in anchors(destination):
                problems.append(f"{path}:{number}: missing anchor: {target}")
    return problems, targets


def check(argv: list[str]) -> list[str]:
    parser = argparse.ArgumentParser(description="Check Markdown links, anchors and required content.")
    parser.add_argument("paths", nargs="+")
    parser.add_argument("--require", action="append", default=[])
    parser.add_argument("--forbid", action="append", default=[])
    parser.add_argument("--reachable-from")
    args = parser.parse_args(argv)

    problems: list[str] = []
    files: list[Path] = []
    for raw in args.paths:
        path = Path(raw)
        if not path.exists():
            problems.append(f"{raw}: path does not exist")
            continue
        files.extend(markdown_files(path))
    if not files and not problems:
        problems.append("no Markdown files found")

    graph: dict[Path, set[Path]] = {}
    for path in files:
        found, targets = check_links(path)
        problems.extend(found)
        graph[path.resolve()] = targets

    corpus = {path: path.read_text(encoding="utf-8").lower() for path in files}
    for text in args.require:
        if not any(text.lower() in body for body in corpus.values()):
            problems.append(f"required text not found: {text}")
    for text in args.forbid:
        for path, body in corpus.items():
            if text.lower() in body:
                problems.append(f"{path}: forbidden text found: {text}")

    if args.reachable_from:
        start = Path(args.reachable_from)
        if not start.is_file():
            problems.append(f"{args.reachable_from}: path does not exist")
        else:
            reached, queue = set(), [start.resolve()]
            while queue:
                current = queue.pop()
                if current in reached:
                    continue
                reached.add(current)
                queue.extend(graph[current] if current in graph else check_links(current)[1])
            for path in files:
                if path.resolve() not in reached:
                    problems.append(f"{path}: not reachable from {args.reachable_from}")
    return problems


def main(argv: list[str] | None = None) -> int:
    problems = check(sys.argv[1:] if argv is None else argv)
    for problem in problems:
        print(problem)
    if not problems:
        print("docs ok")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
