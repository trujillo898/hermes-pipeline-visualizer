"""Demo handlers for the Hyle cycle.

SPDX-License-Identifier: MIT

Only 2 nodes have real logic (meta_gate, governor).
The other 13 are stubs that return a deterministic marker so we can
verify the executor traverses the graph end-to-end without pulling in
the real Hyle codebase (which would violate "not in ~/Ousia/").

The point of this demo is to validate the SPEC + EXECUTOR, not to
reimplement Hyle. A separate adapter (future work) would map these
stubs to real Hyle agent calls.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from executor.runner import HandlerRegistry
from spec.graph import PipelineGraph


def make_stub_handler(node_id: str, declared_outputs: list[str]):
    """Build a stub handler that returns a marker per declared output for THIS node.

    We can't share a single handler across nodes with different shapes —
    the executor validates that the handler produces the node's declared outputs.
    So we generate a distinct handler per node_id at registration time.
    """
    async def handler(inputs: dict) -> dict[str, Any]:
        await asyncio.sleep(0)  # yield to event loop
        marker = {
            "stub": True,
            "node": node_id,
            "got_inputs": list(inputs.keys()),
        }
        return {k: marker for k in declared_outputs}
    return handler


def build_registry() -> HandlerRegistry:
    reg = HandlerRegistry()

    # === Real-ish handlers (with minimal logic that demonstrates the flow) ===

    async def meta_gate(inputs: dict) -> dict[str, Any]:
        return {
            "meta_decision": {
                "mode": "TRADE",
                "reason": "integrity_ok",
                "received": list(inputs.keys()),
            }
        }
    reg.register("hyle.meta_layer.evaluate", meta_gate)

    async def governor(inputs: dict) -> dict[str, Any]:
        s = inputs.get("setup")
        verdict = "approved" if s else "vetoed"
        return {"verdict": verdict}
    reg.register("hyle.governor.GovernorAgent", governor)

    # === Per-node stubs ===
    # Each node gets a distinct class_type (matching hyle_cycle.json) and
    # a handler that returns a marker per declared output. Two fan-out nodes
    # that share a logical operation in real Hyle get distinct class_types
    # in the spec because the executor validates shapes per-node.
    node_specs: list[tuple[str, str, list[str]]] = [
        ("perception_fanout",     "hyle.fanout.perception",
         ["market_structure", "liquidity", "footprint", "killzone", "cross_pair"]),
        ("interpretation_fanout", "hyle.fanout.interpretation",
         ["mtf_alignment", "pattern_validator", "trap_detector"]),

        ("market_structure",  "hyle.perception.MarketStructureAgent",  ["out"]),
        ("liquidity",         "hyle.perception.LiquidityAgent",        ["out"]),
        ("footprint",         "hyle.perception.FootprintAgent",        ["out"]),
        ("killzone",          "hyle.perception.KillzoneAgent",         ["out"]),
        ("cross_pair",        "hyle.perception.CrossPairAgent",        ["out"]),

        ("mtf_alignment",     "hyle.interpretation.MTFAlignmentAgent",     ["out"]),
        ("pattern_validator", "hyle.interpretation.PatternValidatorAgent", ["out"]),
        ("trap_detector",     "hyle.interpretation.TrapDetectorAgent",     ["out"]),

        ("causal",            "hyle.causal.CausalEngine",            ["causal_chain"]),
        ("confluence",        "hyle.confluence.ConfluenceDetector",  ["conf_view"]),
        ("setup_builder",     "hyle.setup.SetupBuilder",             ["build_result"]),
        ("synthesis",         "hyle.synthesis.SynthesisAgent",       ["markdown"]),
    ]
    for node_id, class_type, outputs in node_specs:
        reg.register(class_type, make_stub_handler(node_id, outputs))
    return reg


# Load the graph once at import time so run.py can use it directly
_GRAPH_PATH = Path(__file__).with_name("hyle_cycle.json")
GRAPH: PipelineGraph = PipelineGraph.model_validate_json(
    _GRAPH_PATH.read_text(encoding="utf-8")
)
