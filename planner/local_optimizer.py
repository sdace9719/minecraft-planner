"""Phase 4 / Phase 5 compatibility wrapper.

Sprint 2 behavior:
- Orchestrates Phase 4A global math optimizer.
- Routes the Phase 4A result through Phase 4B DAG router.
- Sorts the Phase 4B result through Phase 5 topological sorter.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from planner.dag_router import DEFAULT_PHASE4_PATH, DagRouter
from planner.global_math_optimizer import (
    BLUEPRINTS_PATH,
    DEFAULT_PHASE3_PATH,
    DEFAULT_PHASE4A_OUTPUT_PATH,
    GlobalMathOptimizer,
    GlobalMathOptimizerError,
)
from planner.global_optimizer import DEFAULT_PHASE5_PATH, TopologicalSorter


class LocalOptimizerError(RuntimeError):
    """Compatibility-level error for Phase 4 wrapper."""


class LocalOptimizer:
    """Compatibility wrapper that orchestrates Phase 4A -> Phase 4B -> Phase 5."""

    def __init__(
        self,
        blueprints_path: Path = BLUEPRINTS_PATH,
        phase3_input_path: Path = DEFAULT_PHASE3_PATH,
        phase4a_output_path: Path = DEFAULT_PHASE4A_OUTPUT_PATH,
        phase4_output_path: Path = DEFAULT_PHASE4_PATH,
        phase5_output_path: Path = DEFAULT_PHASE5_PATH,
    ):
        self._phase4a = GlobalMathOptimizer(
            blueprints_path=blueprints_path,
            phase3_input_path=phase3_input_path,
            phase4a_output_path=phase4a_output_path,
        )
        self._phase4b = DagRouter(
            blueprints_path=blueprints_path,
            phase4a_input_path=phase4a_output_path,
            phase4_output_path=phase4_output_path,
        )
        self._phase5 = TopologicalSorter(
            phase4_input_path=phase4_output_path,
            phase5_output_path=phase5_output_path,
        )

    def optimize(self, phase3_tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        phase4a = self._phase4a.optimize_tasks(phase3_tasks)
        phase4 = self._phase4b.route_tasks(phase4a)
        return self._phase5.sort_tasks(phase4)

    def optimize_from_file(self) -> list[dict[str, Any]]:
        self._phase4a.optimize_from_file()
        self._phase4b.route_from_file()
        return self._phase5.sort_from_file()

    def optimize_chunked_dag(self, phase3_tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        phase4a = self._phase4a.optimize_tasks(phase3_tasks)
        phase4 = self._phase4b.route_tasks(phase4a)
        return self._phase5.sort_tasks(phase4)


def optimize_phase3_graph(phase3_tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Compatibility alias for full Phase 4A → 4B → 5 pipeline."""
    return LocalOptimizer().optimize(phase3_tasks)


def optimize_phase3_graph_from_file() -> list[dict[str, Any]]:
    """Compatibility helper for file-based Phase 4A → 4B → 5 execution."""
    return LocalOptimizer().optimize_from_file()


def optimize_phase4_chunks(phase3_tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Compatibility helper that returns chunked+routed+sorted Phase 5 output."""
    return LocalOptimizer().optimize_chunked_dag(phase3_tasks)
