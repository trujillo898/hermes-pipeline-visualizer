"""Tests for the PipelineExecutor — Phase 2 (RED).

SPDX-License-Identifier: MIT

Contract being tested:
- HandlerRegistry rejects duplicate class_types
- PipelineExecutor runs nodes in topological order (deps first)
- Linear chain: a → b → c with a.x=1, b doubles, c increments → {a:2, b:4, c:5}
- Fan-out diamond: src → (left, right) → sum, with sum.a + sum.b
- Cycles are detected and raise CycleError
- Missing upstream output raises a clear RuntimeError
- on_progress callback fires for node_start and node_done
- on_error='continue' lets remaining nodes execute with null outputs
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from executor.runner import (
    CycleError,
    ExecutorConfig,
    HandlerRegistry,
    PipelineExecutor,
)
from spec.graph import Node, PipelineGraph, Port


# ----- HandlerRegistry -----

def test_registry_rejects_duplicate_class_type():
    reg = HandlerRegistry()
    reg.register("foo", lambda i: {"out": 1})
    with pytest.raises(ValueError, match="duplicate"):
        reg.register("foo", lambda i: {"out": 2})


def test_registry_get_missing_raises_clear_error():
    reg = HandlerRegistry()
    with pytest.raises(KeyError, match="no handler registered"):
        reg.get("does.not.exist")


# ----- PipelineExecutor: linear -----

@pytest.mark.asyncio
async def test_linear_three_nodes_executes_in_order():
    """a (inc) → b (double) → c (inc), starting from x=1 → {a:2, b:4, c:5}."""
    reg = HandlerRegistry()

    async def inc(i):
        return {"out": i["x"] + 1}

    async def double(i):
        return {"out": i["x"] * 2}

    reg.register("inc", inc)
    reg.register("double", double)

    graph = PipelineGraph(
        created_at="2026-01-01T00:00:00Z",
        description="linear",
        nodes=[
            Node(id="a", class_type="inc", inputs={"x": 1},
                 outputs={"out": Port(type="number")}),
            Node(id="b", class_type="double",
                 inputs={"x": {"from": "a", "output": "out"}},
                 outputs={"out": Port(type="number")}),
            Node(id="c", class_type="inc",
                 inputs={"x": {"from": "b", "output": "out"}},
                 outputs={"out": Port(type="number")}),
        ],
    )
    out = await PipelineExecutor(reg).run(graph)
    assert out == {"a": {"out": 2}, "b": {"out": 4}, "c": {"out": 5}}


# ----- PipelineExecutor: fan-out (diamond) -----

@pytest.mark.asyncio
async def test_fan_out_diamond():
    """src → (s, t) where s uses a, t uses b, both from src → s=33 if src.x=3."""
    reg = HandlerRegistry()

    async def src(i):
        return {"a": i["x"], "b": i["x"] * 10}

    async def sum_node(i):
        return {"out": i["a"] + i["b"]}

    reg.register("src", src)
    reg.register("sum", sum_node)

    graph = PipelineGraph(
        created_at="2026-01-01T00:00:00Z",
        description="diamond",
        nodes=[
            Node(id="src", class_type="src", inputs={"x": 3},
                 outputs={"a": Port(type="number"), "b": Port(type="number")}),
            Node(id="s", class_type="sum",
                 inputs={"a": {"from": "src", "output": "a"},
                         "b": {"from": "src", "output": "b"}},
                 outputs={"out": Port(type="number")}),
        ],
    )
    out = await PipelineExecutor(reg).run(graph)
    assert out["s"]["out"] == 33


# ----- PipelineExecutor: cycle detection -----

@pytest.mark.asyncio
async def test_cycle_detected_raises_cycle_error():
    reg = HandlerRegistry()

    async def noop(i):
        return {"out": i["x"]}

    reg.register("noop", noop)
    graph = PipelineGraph(
        created_at="2026-01-01T00:00:00Z",
        description="cycle",
        nodes=[
            Node(id="a", class_type="noop",
                 inputs={"x": {"from": "b", "output": "out"}},
                 outputs={"out": Port(type="number")}),
            Node(id="b", class_type="noop",
                 inputs={"x": {"from": "a", "output": "out"}},
                 outputs={"out": Port(type="number")}),
        ],
    )
    with pytest.raises(CycleError):
        await PipelineExecutor(reg).run(graph)


# ----- PipelineExecutor: missing upstream -----

@pytest.mark.asyncio
async def test_ref_to_nonexistent_node_raises_value_error():
    """If a Ref points to a node_id that doesn't exist, the executor must fail fast."""
    reg = HandlerRegistry()

    async def noop(i):
        return {"out": i["x"]}

    reg.register("noop", noop)
    graph = PipelineGraph(
        created_at="2026-01-01T00:00:00Z",
        description="bad-ref",
        nodes=[
            Node(id="a", class_type="noop", inputs={"x": 1},
                 outputs={"out": Port(type="number")}),
            Node(id="b", class_type="noop",
                 inputs={"x": {"from": "ghost", "output": "out"}},
                 outputs={"out": Port(type="number")}),
        ],
    )
    with pytest.raises(ValueError, match="ghost"):
        await PipelineExecutor(reg).run(graph)


# ----- PipelineExecutor: progress callback -----

@pytest.mark.asyncio
async def test_progress_callback_fires_for_each_node():
    reg = HandlerRegistry()
    events: list[tuple[str, str]] = []

    async def noop(i):
        return {"out": 1}

    reg.register("noop", noop)
    graph = PipelineGraph(
        created_at="2026-01-01T00:00:00Z",
        description="progress",
        nodes=[
            Node(id="a", class_type="noop", inputs={"x": 1},
                 outputs={"out": Port(type="number")}),
            Node(id="b", class_type="noop",
                 inputs={"x": {"from": "a", "output": "out"}},
                 outputs={"out": Port(type="number")}),
        ],
    )
    cfg = ExecutorConfig(on_progress=lambda ev, nid: events.append((ev, nid)))
    await PipelineExecutor(reg, cfg).run(graph)
    started = [nid for ev, nid in events if ev == "node_start"]
    done = [nid for ev, nid in events if ev == "node_done"]
    assert started == ["a", "b"]
    assert done == ["a", "b"]


# ----- PipelineExecutor: error handling -----

@pytest.mark.asyncio
async def test_error_continue_mode_lets_remaining_nodes_run():
    """If on_error='continue', a failing node produces None outputs, but the rest runs."""
    reg = HandlerRegistry()

    async def ok(i):
        return {"out": 42}

    async def boom(i):
        raise RuntimeError("intentional failure")

    async def downstream(i):
        # Reads the failing node's output — must get None, not raise
        return {"got": i["x"]}

    reg.register("ok", ok)
    reg.register("boom", boom)
    reg.register("downstream", downstream)

    graph = PipelineGraph(
        created_at="2026-01-01T00:00:00Z",
        description="error-continue",
        nodes=[
            Node(id="a", class_type="ok", inputs={},
                 outputs={"out": Port(type="number")}),
            Node(id="b", class_type="boom",
                 inputs={"x": {"from": "a", "output": "out"}},
                 outputs={"out": Port(type="number")}),
            Node(id="c", class_type="downstream",
                 inputs={"x": {"from": "b", "output": "out"}},
                 outputs={"got": Port(type="object")}),
        ],
    )
    cfg = ExecutorConfig(on_error="continue")
    out = await PipelineExecutor(reg, cfg).run(graph)
    assert out["a"]["out"] == 42
    assert out["b"]["out"] is None  # failure → None
    assert out["c"]["got"] is None  # downstream saw None


@pytest.mark.asyncio
async def test_error_abort_mode_is_default():
    """If on_error='abort' (default), the first failure propagates."""
    reg = HandlerRegistry()

    async def boom(i):
        raise RuntimeError("intentional failure")

    reg.register("boom", boom)
    graph = PipelineGraph(
        created_at="2026-01-01T00:00:00Z",
        description="error-abort",
        nodes=[
            Node(id="a", class_type="boom", inputs={},
                 outputs={"out": Port(type="number")}),
        ],
    )
    with pytest.raises(RuntimeError, match="intentional failure"):
        await PipelineExecutor(reg).run(graph)


# ----- PipelineExecutor: handler missing declared output -----

@pytest.mark.asyncio
async def test_handler_missing_declared_output_raises():
    """If a handler returns fewer outputs than the node declared, fail loud."""
    reg = HandlerRegistry()

    async def bad(i):
        return {"out": 1}  # missing the second declared output

    reg.register("bad", bad)
    graph = PipelineGraph(
        created_at="2026-01-01T00:00:00Z",
        description="missing-output",
        nodes=[
            Node(id="a", class_type="bad", inputs={},
                 outputs={"out": Port(type="number"), "extra": Port(type="string")}),
        ],
    )
    with pytest.raises(RuntimeError, match="missing declared outputs"):
        await PipelineExecutor(reg).run(graph)
