"""Phase 5 topological sorter: Kahn's algorithm for DAG linearization."""

from __future__ import annotations

import copy
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PHASE4_PATH = ROOT / "tests" / "input_materials_test.phase4.json"
DEFAULT_PHASE5_PATH = ROOT / "tests" / "input_materials_test.phase5.json"


class TopologicalSortError(ValueError):
    """Raised when Phase 5 contracts are violated."""


def _extract_base_id(task_id: str) -> str:
    """Strip the ``_chunk_N`` suffix to recover the logical base id."""
    marker = "_chunk_"
    if marker in task_id:
        return task_id.rsplit(marker, 1)[0]
    return task_id


def _extract_chunk_index(task_id: str) -> int:
    """Return the integer chunk index, defaulting to 1 when absent."""
    marker = "_chunk_"
    if marker in task_id:
        try:
            return int(task_id.rsplit(marker, 1)[1])
        except ValueError:
            raise TopologicalSortError(f"Invalid chunk suffix in task id {task_id!r}.")
    return 1


class TopologicalSorter:
    """Kahn's algorithm for Phase 4B → Phase 5 linearisation."""

    def __init__(
        self,
        phase4_input_path: Path = DEFAULT_PHASE4_PATH,
        phase5_output_path: Path = DEFAULT_PHASE5_PATH,
    ):
        self.phase4_input_path = phase4_input_path
        self.phase5_output_path = phase5_output_path

    @staticmethod
    def _validate_tasks(tasks: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        indexed: dict[str, dict[str, Any]] = {}
        for task in tasks:
            tid = task.get("id")
            if not isinstance(tid, str) or not tid:
                raise TopologicalSortError("Each task must have a non-empty string id.")
            if tid in indexed:
                raise TopologicalSortError(f"Duplicate task id {tid!r}.")
            deps = task.get("dependencies")
            if not isinstance(deps, list):
                raise TopologicalSortError(f"Task {tid!r} missing dependencies list.")
            for dep in deps:
                if not isinstance(dep, str) or not dep:
                    raise TopologicalSortError(f"Task {tid!r} has invalid dependency value.")
            indexed[tid] = task
        for task in indexed.values():
            for dep in task["dependencies"]:
                if dep not in indexed:
                    raise TopologicalSortError(
                        f"Dangling dependency {dep!r} on task {task['id']!r}."
                    )
        return indexed

    def sort_tasks(self, phase4_tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Kahn's algorithm with the strict sort tuple.

        Returns a new list of the original task dicts in topologically sorted order.
        """
        tasks = copy.deepcopy(phase4_tasks)
        indexed = self._validate_tasks(tasks)

        in_degree: dict[str, int] = {}
        dependents: dict[str, list[str]] = defaultdict(list)

        for tid, task in indexed.items():
            in_degree[tid] = len(task["dependencies"])
            for dep in task["dependencies"]:
                dependents[dep].append(tid)

        # Seed with zero in-degree tasks.
        eligible: list[dict[str, Any]] = [
            indexed[tid] for tid, deg in in_degree.items() if deg == 0
        ]

        output: list[dict[str, Any]] = []

        while eligible:
            eligible.sort(
                key=lambda t: (
                    1 - len(t["dependencies"]),   # inventory_pressure
                    _extract_base_id(t["id"]),     # base_id
                    _extract_chunk_index(t["id"]),  # chunk_index (int)
                )
            )
            task = eligible.pop(0)
            output.append(task)

            for dependent_id in dependents.get(task["id"], []):
                in_degree[dependent_id] -= 1
                if in_degree[dependent_id] == 0:
                    eligible.append(indexed[dependent_id])

        if len(output) < len(tasks):
            raise TopologicalSortError(
                "Topological sort failed: Cycle detected in Phase 4 output."
            )

        return output

    def sort_from_file(self) -> list[dict[str, Any]]:
        if not self.phase4_input_path.exists():
            raise TopologicalSortError(
                f"Missing Phase 4 input file: {self.phase4_input_path}"
            )
        payload = json.loads(self.phase4_input_path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise TopologicalSortError("Phase 4 input must be a JSON array.")
        out = self.sort_tasks(payload)
        self.phase5_output_path.write_text(
            json.dumps(out, indent=2) + "\n", encoding="utf-8"
        )
        return out


def topological_sort_phase4(
    phase4_tasks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Convenience wrapper for Phase 5 topological sort."""
    return TopologicalSorter().sort_tasks(phase4_tasks)
