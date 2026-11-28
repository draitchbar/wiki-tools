"""The HEAVY list in conftest.py names real modules, and heavy_first orders by it."""
from __future__ import annotations

from pathlib import Path

from conftest import HEAVY, heavy_first

TESTS = Path(__file__).resolve().parent


def test_heavy_names_are_test_modules():
    assert len(set(HEAVY)) == len(HEAVY)
    missing = [n for n in HEAVY if not (TESTS / (n + ".py")).is_file()]
    assert not missing, missing


def test_heavy_first_orders_heavy_scopes_first():
    scopes = ["tests/test_zzz.py", "tests/test_sources.py", "tests/test_aaa.py", "tests/test_guard.py", "tests/test_save.py"]
    assert heavy_first(scopes) == [
        "tests/test_guard.py", "tests/test_save.py", "tests/test_sources.py",
        "tests/test_zzz.py", "tests/test_aaa.py",
    ]
