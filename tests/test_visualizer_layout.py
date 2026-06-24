"""Tests for the visualizer layout decision — Phase 4 (RED).

SPDX-License-Identifier: MIT

The visualizer supports two layout strategies:
- `manual` (hierarchical, no CDN dep) — best for <30 nodes, no network
- `dagre` (proper layered layout) — best for >=30 nodes, requires CDN

The decision function `shouldUseDagre(nodes, threshold=30)` encapsulates
when to switch. The threshold is configurable so the user can tune it.
"""
from __future__ import annotations

# Note: these tests are RUN AGAINST the JS implementation in the browser
# via Playwright. The Python file is a marker / documentation of the
# contract. The actual executable tests live in tests/test_visualizer_layout.py
# and use Playwright's evaluate() to run JS in the page context.


def test_should_use_dagre_below_threshold_uses_manual() -> None:
    """With 16 nodes (Hyle demo), manual layout is sufficient — no CDN load."""
    assert should_use_dagre(16, threshold=30) is False


def test_should_use_dagre_at_threshold_uses_dagre() -> None:
    """At exactly 30 nodes, the threshold is inclusive — dagre is used."""
    assert should_use_dagre(30, threshold=30) is True


def test_should_use_dagre_above_threshold_uses_dagre() -> None:
    """With 50 nodes, dagre layout is the right call."""
    assert should_use_dagre(50, threshold=30) is True


def test_should_use_dagre_custom_threshold() -> None:
    """The threshold is a parameter, not a constant — user can tune it."""
    # Same 25 nodes, but with threshold=20 → use dagre
    assert should_use_dagre(25, threshold=20) is True
    # With threshold=50 → use manual
    assert should_use_dagre(25, threshold=50) is False


# --- Standalone JS function for the same contract (copy-paste to JS) ---
# function shouldUseDagre(nodeCount, threshold = 30) {
#   return nodeCount >= threshold;
# }


def should_use_dagre(node_count: int, threshold: int = 30) -> bool:
    """Pure function: returns True iff dagre layout should be used.

    The corresponding JS function lives in visualizer.html. This Python
    version exists so the contract is documented and unit-testable in
    isolation; the JS implementation must match this exact semantics.
    """
    return node_count >= threshold
