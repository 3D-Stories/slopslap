"""Pytest wiring: put the plugin's ``scripts/`` and the ``tests/`` dir on sys.path so
``eval`` / ``slopslap_verification`` import as packages and ``helpers`` is importable.
"""

import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(REPO, "scripts")
TESTS = os.path.join(REPO, "tests")
for p in (SCRIPTS, TESTS):
    if p not in sys.path:
        sys.path.insert(0, p)
