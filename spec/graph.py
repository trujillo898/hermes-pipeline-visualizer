"""Hermes Pipeline Visualizer — DAG graph spec.

Own MIT/Apache-2.0 spec for declarative cognitive pipelines. Inspired by
ComfyUI's DAG JSON but with:
- Explicit output types (so the visualizer can color without executing)
- Named outputs (ref by name, not slot index)
- A fixed set of custom cognitive types (causal_chain, cycle_verdict, ...)

NOT a copy of ComfyUI. No GPL code is reused. Route B per UPSTREAM-FOREVER.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


# Allowed types: primitives + cognitive custom types.
PrimitiveType = Literal["string", "number", "boolean", "object", "array", "null"]
CustomType = Literal[
    "causal_chain",       # Aetheer: CausalChain
    "pair_data",          # Hyle: PairData
    "cycle_verdict",      # Hyle: Literal["wait","no_setup","setup","vetoed"]
    "agent_output",       # Aetheer: AgentOutput
    "attention_context",  # Aetheer: AttentionContext
    "perception_bundle",  # Hyle: PerceptionBundle
    "quality_breakdown",  # Aetheer: QualityBreakdown
]
TypeRef = PrimitiveType | CustomType

_ALLOWED_TYPES: frozenset[str] = frozenset(
    ["string", "number", "boolean", "object", "array", "null",
     "causal_chain", "pair_data", "cycle_verdict", "agent_output",
     "attention_context", "perception_bundle", "quality_breakdown"]
)


class Port(BaseModel):
    """A named, typed port on a node."""

    model_config = ConfigDict(extra="forbid")
    type: TypeRef


class Ref(BaseModel):
    """Pointer to a previous node's output: (from_node_id, output_name).

    The Python field is `from_node` because `from` is a reserved keyword.
    The JSON alias `from` makes the serialized form natural and diff-friendly.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    from_node: str = Field(alias="from")
    output: str


class Node(BaseModel):
    """One execution unit.

    `class_type` is an arbitrary string resolved by the executor's HandlerRegistry.
    `inputs` values can be literals or Refs.
    `outputs` is an explicit name → Port map (used for validation + visualization).
    """

    model_config = ConfigDict(extra="forbid")
    id: str
    class_type: str
    inputs: dict[str, Any] = Field(default_factory=dict)
    outputs: dict[str, Port] = Field(default_factory=dict)
    title: str | None = None

    @field_validator("inputs", mode="before")
    @classmethod
    def _coerce_refs(cls, v: dict[str, Any]) -> dict[str, Any]:
        """Auto-coerce dicts that look like Refs into Ref instances."""
        out: dict[str, Any] = {}
        for k, val in v.items():
            if isinstance(val, dict) and set(val.keys()) <= {"from", "output"} and "from" in val and "output" in val:
                out[k] = Ref.model_validate(val)
            else:
                out[k] = val
        return out


class PipelineGraph(BaseModel):
    """A directed acyclic graph of Nodes, serializable to/from JSON.

    `version` is the literal "0.1.0" — any drift must be an explicit ADR.
    """

    model_config = ConfigDict(extra="forbid")
    version: Literal["0.1.0"] = "0.1.0"
    created_at: datetime
    description: str = ""
    nodes: list[Node] = Field(min_length=1)

    def node_ids(self) -> set[str]:
        return {n.id for n in self.nodes}

    def resolve(self, node_id: str, output_name: str) -> Ref | None:
        """Return the Ref feeding `output_name` of `node_id`. None if it's a literal.

        Used by the executor to walk edges and the visualizer to draw them.
        """
        for n in self.nodes:
            if n.id != node_id:
                continue
            v = n.inputs.get(output_name)
            if isinstance(v, Ref):
                return v
        return None


__all__ = [
    "CustomType",
    "Node",
    "PipelineGraph",
    "Port",
    "PrimitiveType",
    "Ref",
    "TypeRef",
]
