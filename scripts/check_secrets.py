#!/usr/bin/env python3
"""Refuse to commit credentials this repo is known to handle.

Run by pre-commit on every commit (see .pre-commit-config.yaml) alongside
gitleaks. gitleaks knows hundreds of generic secret formats; this knows the
specific ones the toolkit uses, so they're caught even if gitleaks misses them:

* Lichess personal API tokens (``lip_...``)
* Google OAuth client secrets (``GOCSPX-...``), access tokens (``ya29....``)
  and refresh tokens (``1//0...``)
* JSON credential fields with a real value (``"client_secret": "..."``,
  ``"refresh_token": "..."``)
* private key blocks
* credential *files* by name (``*client_secret*``, ``*token*.json``,
  ``lichess_token``, ``.env``...), whatever is inside them

    python scripts/check_secrets.py FILE...      # what pre-commit runs
    python scripts/check_secrets.py --all        # every tracked file

If a hit is a false positive (a test fixture, say), put
``# secrets: allow`` on that line. Real credentials belong in
~/.config/data_scrape/, outside the repo -- see the root README.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ALLOW = "secrets: allow"

PATTERNS: list[tuple[str, re.Pattern]] = [
    ("Lichess API token", re.compile(r"\blip_[A-Za-z0-9]{16,}")),
    ("Google OAuth client secret", re.compile(r"GOCSPX-[A-Za-z0-9_-]{20,}")),
    ("Google OAuth access token", re.compile(r"\bya29\.[A-Za-z0-9_-]{20,}")),
    ("Google OAuth refresh token", re.compile(r"\b1//0[A-Za-z0-9_-]{20,}")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("credential field with a value", re.compile(
        r'"(client_secret|refresh_token|access_token|private_key|api_key|token)"\s*:\s*"[^"\s]{8,}"')),
    ("private key", re.compile(r"-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----")),
]

#: File names that only ever hold credentials. Matched against the name alone,
#: case-insensitively.
BLOCKED_NAMES = [
    re.compile(p, re.I) for p in (
        r".*client_secret.*", r".*credentials.*\.json", r".*token.*\.json",
        r".*service_account.*\.json", r"lichess[-_](key|token)", r".*_token",
        r"\.env(\..*)?", r".*\.(pem|key|p12|pfx)",
    )
]


def check_name(path: Path) -> str | None:
    if any(p.fullmatch(path.name) for p in BLOCKED_NAMES):
        return f"{path}: looks like a credentials file by its name"
    return None


def check_text(path: Path) -> list[str]:
    try:
        text = path.read_text(errors="strict")
    except (UnicodeDecodeError, OSError):
        return []  # binary or unreadable: gitleaks still scans it
    problems = []
    for lineno, line in enumerate(text.splitlines(), 1):
        if ALLOW in line:
            continue
        for label, pattern in PATTERNS:
            m = pattern.search(line)
            if m:
                shown = m.group(0)[:12] + "…"  # never echo the whole secret
                problems.append(f"{path}:{lineno}: {label} ({shown})")
    return problems


def main(argv: list[str]) -> int:
    if argv == ["--all"]:
        argv = subprocess.run(["git", "ls-files"], capture_output=True, text=True,
                              check=True).stdout.split()
    problems = []
    for name in argv:
        path = Path(name)
        if (msg := check_name(path)):
            problems.append(msg)
        if path.is_file():
            problems += check_text(path)
    if problems:
        print("Possible credentials -- commit blocked:\n", file=sys.stderr)
        for p in problems:
            print(f"  {p}", file=sys.stderr)
        print("\nKeep keys in ~/.config/data_scrape/ (outside the repo). For a "
              f"false positive, add '# {ALLOW}' to the line.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
