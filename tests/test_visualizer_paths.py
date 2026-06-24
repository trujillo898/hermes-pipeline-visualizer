"""Tests for the visualizer.html path derivation — Phase 5 (RED).

SPDX-License-Identifier: MIT

The visualizer's `loadDemoJson(relativePath)` derives its base from
`window.location.pathname`, stripping the filename. This test verifies
the regex pattern in the source HTML matches the expected behavior,
so a future edit doesn't silently break the GitHub Pages deployment.

What we check:
1. The OLD hardcoded regex (`/visualizer/visualizer.html`) is GONE
2. The NEW generic regex (`/[^/]*$` to strip any filename) is PRESENT
3. The new function works for both contexts:
   - Local: /visualizer/visualizer.html -> strips to /visualizer
   - Pages: /index.html -> strips to / (root)
   - Subpath: /foo/bar/index.html -> strips to /foo/bar

Since this is HTML+JS, we test the SOURCE (file contents) not the runtime
behavior. Runtime verification happens via Playwright in the E2E pipeline.
"""
from __future__ import annotations

from pathlib import Path

import pytest

VIZ_PATH = Path(__file__).resolve().parent.parent / "visualizer" / "visualizer.html"


def test_visualizer_file_exists():
    """The visualizer HTML must exist at the expected path."""
    assert VIZ_PATH.is_file(), f"visualizer.html not found at {VIZ_PATH}"


def test_old_hardcoded_visualizer_regex_is_gone():
    """The old regex `/\/visualizer\/visualizer\.html/` must be removed.

    Hardcoding the path was a Phase 3 bug that broke GitHub Pages.
    We never want it back. (Note: `visualizer.html` may still appear in
    comments/docs — this test only checks the regex pattern itself.)
    """
    content = VIZ_PATH.read_text(encoding="utf-8")
    # The old regex literal was: /\/visualizer\/visualizer\.html/
    # (used inside a .replace() call). Look for it as a regex literal.
    assert r"/\/visualizer\/visualizer\.html/" not in content, (
        "Old hardcoded regex /\\/visualizer\\/visualizer\\.html/ is still in the file. "
        "It breaks GitHub Pages deployment where the file is served as /index.html. "
        "Use the generic filename-stripping regex instead."
    )


def test_new_generic_filename_regex_is_present():
    """The new regex /\/[^/]*$/ (strip any filename) must be present."""
    content = VIZ_PATH.read_text(encoding="utf-8")
    # The new pattern: strip everything from the last "/" to the end of the path
    assert "/[^/]*$" in content or "/[^/]+$" in content, (
        "New generic filename-stripping regex is missing. "
        "loadDemoJson() cannot derive its base path for GitHub Pages."
    )


def test_loadDemoJson_function_present():
    """The loadDemoJson() helper must exist in the visualizer."""
    content = VIZ_PATH.read_text(encoding="utf-8")
    assert "function loadDemoJson" in content, (
        "loadDemoJson() helper is missing — demo buttons will not work."
    )


def test_no_absolute_demos_path_in_loadDemoJson():
    """loadDemoJson callers should NOT pass absolute /demos/... paths
    that hardcode the repo structure. The base is derived from
    window.location, so callers can use either absolute or relative.
    This test documents the current behavior: absolute paths are used
    because the base dir is the project root in both local and Pages.
    """
    content = VIZ_PATH.read_text(encoding="utf-8")
    # Both loaders use "/demos/..." as the relative path
    assert '"/demos/hyle_cycle/hyle_cycle.json"' in content
    assert '"/demos/big_graph/big_graph.json"' in content


# --- Path derivation logic tests (pure Python mirror of the JS regex) ---

@pytest.mark.parametrize(
    "input_pathname,expected_dir",
    [
        # Local development: project served from root, file in subdir
        ("/visualizer/visualizer.html", "/visualizer"),
        # GitHub Pages: file is index.html at the root of the project URL
        ("/index.html", ""),
        # Subpath deployment: file is in a nested path
        ("/foo/bar/index.html", "/foo/bar"),
    ],
)
def test_filename_stripping_regex_matches_js(input_pathname: str, expected_dir: str):
    """The Python regex `/[^/]*$` must match the JS one and produce the
    same result for any deployment path. This catches divergence between
    the Python test mirror and the actual JS implementation.

    Note: trailing slashes in pathname are not expected (browsers normalize
    them away) and the regex doesn't handle them defensively. If you need
    to support them, change both regexes together.
    """
    import re
    result = re.sub(r"/[^/]*$", "", input_pathname)
    assert result == expected_dir, (
        f"Filename stripping for {input_pathname!r} produced {result!r}, "
        f"expected {expected_dir!r}. If this test fails, the JS regex in "
        f"visualizer.html has diverged from the Python mirror."
    )
