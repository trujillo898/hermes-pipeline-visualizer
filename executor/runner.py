"""Async pipeline executor — Phase 2.

SPDX-License-Identifier: MIT

Runs a PipelineGraph topologically (Kahn's algorithm) and dispatches each node
to a handler looked up in HandlerRegistry.

Design contract:
- `class_type` is resolved via HandlerRegistry (string → async callable)
- Refs in inputs are resolved from a per-run cache (node_id → output dict)
- Failures: on_error="abort" (default) propagates, "continue" emits nulls
- on_progress callback receives (event, node_id) for observability

Inspired by ComfyUI's prompt execution queue (per UPSTREAM-FOREVER Route B —
own design, no GPL code). Kahn's topo-sort avoids networkx dependency.
"""
from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from spec.graph import Node, PipelineGraph, Ref

log = logging.getLogger("hermes.viz.executor")

NodeHandler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


@dataclass
class ExecutorConfig:
    on_error: str = "abort"  # "abort" | "continue"
    on_progress: Callable[[str, str], None] | None = None  # (event, node_id)


class HandlerRegistry:
    def __init__(self) -> None:
        self._handlers: dict[str, NodeHandler] = {}

    def register(self, class_type: str, handler: NodeHandler) -> None:
        if class_type in self._handlers:
            raise ValueError(f"duplicate handler for {class_type!r}")
        self._handlers[class_type] = handler

    def get(self, class_type: str) -> NodeHandler:
        try:
            return self._handlers[class_type]
        except KeyError:
            raise KeyError(
                f"no handler registered for class_type={class_type!r}"
            ) from None


class CycleError(RuntimeError):
    """Raised when topo-sort detects a cycle (shouldn't happen on valid graphs)."""


class PipelineExecutor:
    def __init__(
        self,
        registry: HandlerRegistry,
        config: ExecutorConfig | None = None,
    ) -> None:
        self._registry = registry
        self._config = config or ExecutorConfig()
        self._cache: dict[str, dict[str, Any]] = {}

    async def run(self, graph: PipelineGraph) -> dict[str, Any]:
        order = self._topo_sort(graph)
        self._cache.clear()
        by_id = {n.id: n for n in graph.nodes}
        for node_id in order:
            await self._execute_node(by_id[node_id])
        return dict(self._cache)

    def _topo_sort(self, graph: PipelineGraph) -> list[str]:
        """Kahn's algorithm. Returns nodes in execution order (deps first).
        Raises CycleError on cycles. No external deps — works without networkx.
        """
        by_id = {n.id: n for n in graph.nodes}
        indeg: dict[str, int] = {n.id: 0 for n in graph.nodes}
        adj: dict[str, list[str]] = {n.id: [] for n in graph.nodes}
        for node in graph.nodes:
            for value in node.inputs.values():
                if isinstance(value, Ref):
                    src = value.from_node
                    if src not in by_id:
                        raise ValueError(
                            f"node {node.id!r} refs missing {src!r}"
                        )
                    adj[src].append(node.id)
                    indeg[node.id] += 1
        # Kahn
        ready = [nid for nid, d in indeg.items() if d == 0]
        out: list[str] = []
        while ready:
            n = ready.pop(0)
            out.append(n)
            for m in adj[n]:
                indeg[m] -= 1
                if indeg[m] == 0:
                    ready.append(m)
        if len(out) != len(graph.nodes):
            raise CycleError(
                f"cycle in graph; resolved {len(out)}/{len(graph.nodes)}"
            )
        return out

    async def _execute_node(self, node: Node) -> None:
        if self._config.on_progress:
            self._config.on_progress("node_start", node.id)

        # Resolve inputs: literals pass through, Refs pull from cache
        resolved: dict[str, Any] = {}
        for k, v in node.inputs.items():
            if isinstance(v, Ref):
                upstream = self._cache.get(v.from_node)
                if upstream is None:
                    raise RuntimeError(
                        f"node {node.id!r} input {k!r} missing upstream "
                        f"{v.from_node}.{v.output}"
                    )
                try:
                    resolved[k] = upstream[v.output]
                except KeyError as e:
                    raise RuntimeError(
                        f"node {node.id!r} input {k!r} missing upstream "
                        f"{v.from_node}.{v.output}"
                    ) from e
            else:
                resolved[k] = v

        handler = self._registry.get(node.class_type)
        try:
            outputs = await handler(resolved)
        except Exception as e:
            log.exception(
                "node %s (%s) failed: %s", node.id, node.class_type, e
            )
            if self._config.on_error == "abort":
                raise
            outputs = {p: None for p in node.outputs}

        # Defense in depth: handler must produce all declared outputs
        missing = set(node.outputs) - set(outputs)
        if missing:
            raise RuntimeError(
                f"handler {node.class_type!r} for node {node.id!r} "
                f"missing declared outputs: {sorted(missing)}"
            )

        self._cache[node.id] = outputs
        if self._config.on_progress:
            self._config.on_progress("node_done", node.id)


__all__ = [
    "CycleError",
    "ExecutorConfig",
    "HandlerRegistry",
    "NodeHandler",
    "PipelineExecutor",
]
