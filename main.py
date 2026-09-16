#!/usr/bin/env python3
"""OCTORA launcher — run with: python main.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from octora.main import main

if __name__ == "__main__":
    raise SystemExit(main())
