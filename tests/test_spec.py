"""Tests for the spec.graph module — Phase 1 (RED).

SPDX-License-Identifier: MIT

Contract being tested:
- PipelineGraph round-trips through JSON preserving all fields
- Ref serializes with alias "from" (not "from_node")
- extra="forbid" catches typos at validation time
- Port validates type field is one of the allowed primitives/customs
"""
from __future__ import annotations

import json
from datetime import datetime

import pytest
from pydantic import ValidationError

from spec.graph import Node, PipelineGraph, Port, Ref


# ----- Ref -----

def test_ref_from_node_field_in_python():
    """The Python field is `from_node` (not `from`, which is a keyword)."""
    r = Ref.model_validate({"from": "node_a", "output": "out_value"})
    assert r.from_node == "node_a"
    assert r.output == "out_value"


def test_ref_serializes_with_from_alias():
    """When dumped to JSON, the field must appear as `"from"` (alias), not `from_node`."""
    r = Ref(from_node="n1", output="x")
    dumped = r.model_dump(by_alias=True)
    assert dumped == {"from": "n1", "output": "x"}


def test_ref_rejects_extra_fields():
    """`extra="forbid"` — typos should fail validation, not silently pass."""
    with pytest.raises(ValidationError):
        Ref.model_validate({"from": "n1", "output": "x", "extra_typo": 1})


# ----- Port -----

def test_port_accepts_primitive_type():
    p = Port(type="string")
    assert p.type == "string"


def test_port_accepts_custom_cognitive_type():
    """Custom cognitive types are first-class (causal_chain, cycle_verdict, etc.)."""
    p = Port(type="causal_chain")
    assert p.type == "causal_chain"


def test_port_rejects_unknown_type():
    """Unknown types must be rejected at validation time — not silently accepted."""
    with pytest.raises(ValidationError):
        Port(type="this_type_does_not_exist")


# ----- Node -----

def test_node_with_literal_inputs():
    """Inputs can be literals (str, int, bool, list, dict) or Refs."""
    n = Node(
        id="src",
        class_type="my.handler",
        inputs={"x": 1, "y": "hello", "z": True, "lst": [1, 2, 3]},
        outputs={"out": Port(type="number")},
    )
    assert n.inputs["x"] == 1
    assert n.inputs["y"] == "hello"


def test_node_with_ref_input():
    """Ref inputs are accepted and resolved to Ref instances by Pydantic."""
    n = Node(
        id="dst",
        class_type="my.handler",
        inputs={"src": {"from": "src", "output": "out"}},
        outputs={"out": Port(type="number")},
    )
    assert isinstance(n.inputs["src"], Ref)
    assert n.inputs["src"].from_node == "src"
    assert n.inputs["src"].output == "out"


# ----- PipelineGraph -----

def test_pipeline_graph_round_trip():
    """JSON → Pydantic → JSON must preserve all data (lossless round-trip)."""
    original = {
        "version": "0.1.0",
        "created_at": "2026-06-24T15:00:00Z",
        "description": "test",
        "nodes": [
            {
                "id": "a",
                "class_type": "t.a",
                "inputs": {"x": 1},
                "outputs": {"out": {"type": "number"}},
            },
            {
                "id": "b",
                "class_type": "t.b",
                "inputs": {"x": {"from": "a", "output": "out"}},
                "outputs": {"out": {"type": "string"}},
            },
        ],
    }
    g = PipelineGraph.model_validate(original)
    dumped = g.model_dump(by_alias=True)
    # Re-parse to normalize datetime
    assert dumped["version"] == "0.1.0"
    assert dumped["description"] == "test"
    assert len(dumped["nodes"]) == 2
    assert dumped["nodes"][0]["id"] == "a"
    assert dumped["nodes"][0]["inputs"] == {"x": 1}
    assert dumped["nodes"][1]["inputs"] == {"x": {"from": "a", "output": "out"}}


def test_pipeline_graph_rejects_extra_top_level_field():
    """Top-level extra fields must be rejected (catches drift in JSON files)."""
    with pytest.raises(ValidationError):
        PipelineGraph.model_validate(
            {
                "version": "0.1.0",
                "created_at": "2026-06-24T15:00:00Z",
                "description": "test",
                "nodes": [],
                "unknown_typo_field": 123,
            }
        )


def test_pipeline_graph_rejects_wrong_version():
    """Version must be the literal "0.1.0" — reject drifts early."""
    with pytest.raises(ValidationError):
        PipelineGraph.model_validate(
            {
                "version": "0.2.0",
                "created_at": "2026-06-24T15:00:00Z",
                "description": "test",
                "nodes": [],
            }
        )


def test_pipeline_graph_rejects_empty_nodes():
    """A graph with zero nodes is meaningless and likely a bug — reject at parse time."""
    with pytest.raises(ValidationError):
        PipelineGraph.model_validate(
            {
                "version": "0.1.0",
                "created_at": "2026-06-24T15:00:00Z",
                "description": "empty",
                "nodes": [],
            }
        )
