#!/usr/bin/env python3
"""reset.py — devolve store + changeset ao estado da fatia 1."""
from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main() -> int:
    for name in ("store", "changesets"):
        src = ROOT / "fixtures" / name
        dst = ROOT / name
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
    decisions = ROOT / "decisions.jsonl"
    if decisions.exists():
        decisions.unlink()
    print("store e changeset resetados")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
