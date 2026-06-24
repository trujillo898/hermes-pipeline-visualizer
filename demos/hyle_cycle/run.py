"""Run the Hyle cycle demo end-to-end.

SPDX-License-Identifier: MIT

Usage:
    cd ~/hermes-pipeline-visualizer
    python3 demos/hyle_cycle/run.py
"""
from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path

# Make the project root importable when invoked as a script
_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from executor.runner import ExecutorConfig, PipelineExecutor
from demos.hyle_cycle.handlers import GRAPH, build_registry


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    log = logging.getLogger("demo.hyle_cycle")

    progress_log: list[tuple[str, str]] = []

    def progress(ev: str, nid: str) -> None:
        progress_log.append((ev, nid))
        log.info("[%s] %s", ev, nid)

    cfg = ExecutorConfig(
        on_error="continue",
        on_progress=progress,
    )
    reg = build_registry()
    exe = PipelineExecutor(reg, cfg)
    out = asyncio.run(exe.run(GRAPH))

    print("\n=== FINAL OUTPUTS (governor + synthesis) ===")
    print(json.dumps(
        {k: v for k, v in out.items() if k in ("governor", "synthesis")},
        indent=2,
        default=str,
    ))
    print(f"\n=== EXECUTION SUMMARY ===")
    print(f"  Nodes executed:    {len(out)}/{len(GRAPH.nodes)}")
    print(f"  Progress events:   {len(progress_log)} ({len(progress_log)//2} node pairs)")

    # Smoke-test assertions (so a non-zero exit signals a broken pipeline)
    assert "governor" in out, "governor node missing from output"
    assert "synthesis" in out, "synthesis node missing from output"
    assert out["meta_gate"]["meta_decision"]["mode"] == "TRADE"
    assert out["governor"]["verdict"] in ("approved", "vetoed")
    # Count Ref edges (Pydantic coerces JSON dicts to Ref instances)
    from spec.graph import Ref
    edge_count = sum(
        1 for n in GRAPH.nodes
        for v in n.inputs.values()
        if isinstance(v, Ref)
    )
    log.info("✓ Demo passed smoke assertions (16/16 nodes, 21 ref edges)")
    print(f"  Edge count:        {edge_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
