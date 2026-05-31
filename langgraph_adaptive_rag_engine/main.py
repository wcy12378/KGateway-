"""Entry point — delegates to src.main for the actual application logic.

Usage:
    uv run main.py
"""
import asyncio
import sys
from pathlib import Path

# Ensure src/ is importable when running from the project root.
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from src.main import main  # noqa: E402

if __name__ == "__main__":
    asyncio.run(main())
