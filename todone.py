#!/usr/bin/env python3
"""todone - every TODO in the repo, oldest first.

`grep -r TODO` gives you a list. It does not tell you that the one at the
top has been there for three years, which is the only part that decides
whether anybody should care.

    $ todone
     847d  src/billing/charge.py:91   TODO: handle partial refunds
           Alisher Muhammadaliyev
       3d  src/api/views.py:12        FIXME: this retries forever

Age comes from `git blame`, so it is the age of the line, not of the file.

Exit codes: 0 nothing matched, 1 not a git repository, 2 usage,
3 markers found -- which makes `todone --older-than 365` a CI gate.

Zero dependencies. Python 3.9+.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time

VERSION = "0.1.0"
EXIT_NONE, EXIT_ERROR, EXIT_USAGE, EXIT_FOUND = 0, 1, 2, 3

DEFAULT_TAGS = ("TODO", "FIXME", "HACK", "XXX")
CODE_SUFFIXES = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".go", ".rb", ".rs",
    ".php", ".java", ".kt", ".swift", ".c", ".h", ".cc", ".cpp", ".hpp",
    ".cs", ".sh", ".bash", ".sql", ".css", ".scss", ".html", ".vue", ".md",
    ".yml", ".yaml", ".toml",
}
MAX_BYTES = 2 * 1024 * 1024
DAY = 86400


class Marker:
    def __init__(self, tag, path, line, text):
        self.tag, self.path, self.line, self.text = tag, path, line, text
        self.age_days = None
        self.author = None

    def as_dict(self):
        return {"tag": self.tag, "file": self.path, "line": self.line,
                "text": self.text, "age_days": self.age_days,
                "author": self.author}


def repo_root(start):
    out = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=start,
                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                         universal_newlines=True)
    if out.returncode != 0 or not out.stdout.strip():
        return None
    return os.path.realpath(out.stdout.strip())


def walk(root):
    """Faqat git kuzatadigan fayllar.

    Diskdan yurish noto'g'ri edi: u .build/, node_modules/ va boshqa
    worktree'lar ichiga kirib ketardi. U yerdagi TODO'lar sizniki emas,
    va ular kuzatilmagani uchun blame ham yoshini bilmaydi. git ls-files
    .gitignore'ni bepul hurmat qiladi va ancha tezroq.
    """
    out = subprocess.run(["git", "ls-files", "-z"], cwd=root,
                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                         universal_newlines=True, errors="replace")
    if out.returncode != 0:
        return
    for rel in out.stdout.split("\0"):
        if rel and os.path.splitext(rel)[1] in CODE_SUFFIXES:
            yield os.path.join(root, rel)


def scan_file(path, root, pattern):
    markers = []
    try:
        if os.path.getsize(path) > MAX_BYTES:
            return markers
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()
    except OSError:
        return markers
    rel = os.path.relpath(path, root).replace(os.sep, "/")
    for number, line in enumerate(lines, 1):
        if len(line) > 1000:
            continue
        m = pattern.search(line)
        if m:
            text = line[m.start():].strip().lstrip("*/#-<!- ").strip()
            markers.append(Marker(m.group(1).upper(), rel, number, text[:140]))
    return markers


def blame(root, rel):
    """Fayldagi har bir qator uchun (vaqt, muallif).

    Bir faylga bitta chaqiruv: qator-qator blame qilish katta repoda
    o'nlab marta sekinroq bo'lardi.
    """
    out = subprocess.run(
        ["git", "blame", "--line-porcelain", "--", rel], cwd=root,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        universal_newlines=True, errors="replace")
    if out.returncode != 0:
        return {}
    info, number, author, when = {}, None, None, None
    for line in out.stdout.splitlines():
        if re.match(r"^[0-9a-f]{40} \d+ (\d+)", line):
            number = int(line.split()[2])
        elif line.startswith("author "):
            author = line[7:].strip()
        elif line.startswith("author-time "):
            when = int(line[12:].strip())
        elif line.startswith("\t") and number is not None:
            info[number] = (when, author)
            number = author = when = None
    return info


def collect(root, tags, older_than, author_filter):
    pattern = re.compile(r"\b(%s)\b" % "|".join(re.escape(t) for t in tags))
    by_file = {}
    for path in walk(root):
        found = scan_file(path, root, pattern)
        if found:
            by_file.setdefault(found[0].path, []).extend(found)

    now = time.time()
    markers = []
    for rel, found in by_file.items():
        ages = blame(root, rel)
        for marker in found:
            when, author = ages.get(marker.line, (None, None))
            marker.author = author
            if when:
                marker.age_days = int((now - when) // DAY)
            if older_than is not None and (marker.age_days or 0) < older_than:
                continue
            if author_filter and (author or "").lower().find(author_filter.lower()) < 0:
                continue
            markers.append(marker)
    markers.sort(key=lambda m: (-(m.age_days if m.age_days is not None else -1),
                                m.path, m.line))
    return markers


def render(markers, show_author):
    width = max(len("%s:%d" % (m.path, m.line)) for m in markers)
    width = min(width, 48)
    for m in markers:
        age = "%5dd" % m.age_days if m.age_days is not None else "    ?"
        where = ("%s:%d" % (m.path, m.line)).ljust(width)
        print("%s  %s  %s" % (age, where, m.text))
        if show_author and m.author:
            print("%s  %s" % (" " * len(age), m.author))


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="todone",
        description="Every TODO in the repo, oldest first.",
        epilog="example: todone --older-than 365   # a CI gate")
    p.add_argument("path", nargs="?", default=".", metavar="PATH")
    p.add_argument("--tag", action="append", metavar="TAG",
                   help="markers to look for (default: %s)" % ", ".join(DEFAULT_TAGS))
    p.add_argument("--older-than", type=int, metavar="DAYS",
                   help="only markers at least this old")
    p.add_argument("--author", metavar="NAME", help="only lines by this author")
    p.add_argument("--no-author", action="store_true", help="do not print authors")
    p.add_argument("--json", action="store_true")
    p.add_argument("--version", action="version", version="todone " + VERSION)
    args = p.parse_args(argv)

    start = os.path.abspath(args.path)
    if not os.path.isdir(start):
        print("error: not a folder: %s" % args.path, file=sys.stderr)
        return EXIT_USAGE
    if args.older_than is not None and args.older_than < 0:
        print("error: --older-than cannot be negative", file=sys.stderr)
        return EXIT_USAGE

    root = repo_root(start)
    if root is None:
        print("error: not a git repository (age comes from git blame)",
              file=sys.stderr)
        return EXIT_ERROR

    tags = [t.upper() for t in (args.tag or DEFAULT_TAGS)]
    markers = collect(root, tags, args.older_than, args.author)

    if args.json:
        print(json.dumps({"ok": not markers,
                          "markers": [m.as_dict() for m in markers]},
                         indent=2, sort_keys=True, ensure_ascii=False))
    elif not markers:
        print("clean: no %s found" % "/".join(tags))
    else:
        render(markers, not args.no_author)
        oldest = markers[0].age_days
        tail = ", oldest %d days" % oldest if oldest else ""
        print("\n%d marker%s%s" % (len(markers), "" if len(markers) == 1 else "s", tail))
    return EXIT_FOUND if markers else EXIT_NONE


if __name__ == "__main__":
    sys.exit(main())
