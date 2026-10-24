"""Fail the build if large/binary or obviously private artifacts appear.

This is a small guard for a public repository: it flags media/game/binary
extensions, oversized files, absolute home paths, and hash-like strings that
often leak from local experiments. It is not a substitute for reviewing
``git status`` before publishing.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "build",
    "dist",
    "demo_out",
    "pipeline_out",
    ".pytest_cache",
    ".mypy_cache",
}

BLOCKED_EXTENSIONS = {
    ".pac", ".dat", ".bin", ".exe", ".dll", ".so", ".dylib",
    ".ttf", ".otf", ".ttc", ".woff", ".woff2",
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".ico",
    ".mp3", ".ogg", ".wav", ".flac", ".m4a",
    ".mp4", ".mkv", ".avi", ".webm",
    ".zip", ".7z", ".rar", ".tar", ".gz", ".bz2", ".xz",
    ".pak", ".sav", ".bak", ".psd", ".blend",
}

MAX_TEXT_BYTES = 1_000_000
MAX_FILE_BYTES = 2_000_000
HASH_PATTERN = re.compile(r"\b[0-9a-fA-F]{32,64}\b")
DRIVE_PATH = re.compile(r"[A-Za-z]:" + re.escape("\\"))
HOME_PATH = re.compile(r"/(?:Users|home)/[^/\s]+")
PRIVATE_KEY = re.compile(r"BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY")


def iter_files() -> list[Path]:
    files: list[Path] = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        files.append(path)
    return sorted(files)


def main() -> int:
    issues: list[str] = []
    for path in iter_files():
        relative = path.relative_to(ROOT)
        try:
            size = path.stat().st_size
        except OSError as exc:
            issues.append(f"{relative}: cannot stat ({exc})")
            continue
        if size > MAX_FILE_BYTES:
            issues.append(f"{relative}: larger than {MAX_FILE_BYTES} bytes")
        if path.suffix.lower() in BLOCKED_EXTENSIONS:
            issues.append(f"{relative}: blocked extension {path.suffix}")
            continue
        if size > MAX_TEXT_BYTES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if "\x00" in text:
            continue
        for label, pattern in (
            ("32-64 hex hash", HASH_PATTERN),
            ("absolute drive path", DRIVE_PATH),
            ("home directory path", HOME_PATH),
            ("private key marker", PRIVATE_KEY),
        ):
            match = pattern.search(text)
            if match:
                issues.append(
                    f"{relative}: possible {label}: {match.group(0)[:40]!r}"
                )

    if issues:
        print("Repository guard found issues:")
        for issue in issues:
            print(f"  - {issue}")
        return 1
    print(f"Repository guard OK ({len(iter_files())} files checked).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
