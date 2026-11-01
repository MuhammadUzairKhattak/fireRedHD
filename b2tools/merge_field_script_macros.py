#!/usr/bin/env python3
"""Append legacy-only field-script macros to a newer pokebw2 macro file."""

from pathlib import Path
import re
import sys


MARKER = "// HoennB2 legacy field-script macro compatibility"
MACRO = re.compile(r"^\s*\.macro\s+(\S+)")


def macro_blocks(text):
    lines = text.splitlines()
    blocks = []
    index = 0
    while index < len(lines):
        match = MACRO.match(lines[index])
        if not match:
            index += 1
            continue
        end = index + 1
        while end < len(lines) and lines[end].strip() != ".endm":
            end += 1
        if end == len(lines):
            raise ValueError(f"unterminated macro {match.group(1)}")
        blocks.append((match.group(1), "\n".join(lines[index:end + 1])))
        index = end + 1
    return blocks


def main():
    if len(sys.argv) != 3:
        raise SystemExit(f"usage: {sys.argv[0]} NEW_FIELD_SCRIPT_INC LEGACY_FIELD_SCRIPT_INC")

    new_path, legacy_path = map(Path, sys.argv[1:])
    new_text = new_path.read_text()
    if MARKER in new_text:
        new_text = new_text.split(MARKER, 1)[0].rstrip()

    current = {name for name, _ in macro_blocks(new_text)}
    missing = [(name, block) for name, block in macro_blocks(legacy_path.read_text()) if name not in current]
    compatibility = "\n\n".join(block for _, block in missing)
    new_path.write_text(f"{new_text}\n\n{MARKER}\n{compatibility}\n")
    print(f"appended {len(missing)} legacy-only macros to {new_path}")


if __name__ == "__main__":
    main()
