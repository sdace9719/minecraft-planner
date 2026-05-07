"""Phase 3 combiner: merge Phase 2 tasks by ID."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, is_dataclass
from typing import Any


class CombinerError(RuntimeError):
    """Raised when combiner input contracts are violated."""


DEFAULT_REUSABLE_WORKSTATIONS = {
    "crafting_table",
    "furnace",
    "blast_furnace",
    "smoker",
    "stonecutter",
    "smithing_table",
    "cartography_table",
    "loom",
    "grindstone",
    "enchanting_table",
    "anvil",
    "chipped_anvil",
    "damaged_anvil",
}


def _coerce_task_dict(task: Any) -> dict[str, Any]:
    if isinstance(task, dict):
        return task
    if is_dataclass(task):
        return asdict(task)
    required = ("id", "name", "quantity", "dependencies", "operation_type")
    if all(hasattr(task, key) for key in required):
        return {key: getattr(task, key) for key in required}
    raise CombinerError(f"Unsupported task type {type(task)!r}; expected dict or Task-like object.")


def _validate_task(task: dict[str, Any]) -> None:
    required = ("id", "name", "quantity", "dependencies", "operation_type")
    for key in required:
        if key not in task:
            raise CombinerError(f"Task is missing required field {key!r}.")

    if not isinstance(task["id"], str) or not task["id"]:
        raise CombinerError("Task field 'id' must be a non-empty string.")
    if not isinstance(task["name"], str) or not task["name"]:
        raise CombinerError("Task field 'name' must be a non-empty string.")
    if not isinstance(task["operation_type"], str) or not task["operation_type"]:
        raise CombinerError("Task field 'operation_type' must be a non-empty string.")
    if not isinstance(task["quantity"], int):
        raise CombinerError("Task field 'quantity' must be an integer.")
    if task["quantity"] < 0:
        raise CombinerError("Task field 'quantity' cannot be negative.")
    if not isinstance(task["dependencies"], list):
        raise CombinerError("Task field 'dependencies' must be a list.")
    for dep in task["dependencies"]:
        if not isinstance(dep, str) or not dep:
            raise CombinerError("Every dependency ID must be a non-empty string.")


def combine_tasks(
    tasks: Iterable[Any],
    reusable_workstations: set[str] | None = None,
) -> list[dict[str, Any]]:
    workstation_set = reusable_workstations or DEFAULT_REUSABLE_WORKSTATIONS
    merged: dict[str, dict[str, Any]] = {}

    for raw_task in tasks:
        task = _coerce_task_dict(raw_task)
        _validate_task(task)

        task_id = task["id"]
        name = task["name"]
        op = task["operation_type"]
        qty = task["quantity"]
        deps = task["dependencies"]

        if task_id not in merged:
            merged[task_id] = {
                "id": task_id,
                "name": name,
                "quantity": 1 if name in workstation_set else qty,
                "dependencies": list(dict.fromkeys(deps)),
                "operation_type": op,
            }
            continue

        current = merged[task_id]
        if current["name"] != name:
            raise CombinerError(
                f"Conflicting task names for ID {task_id!r}: {current['name']!r} vs {name!r}."
            )
        if current["operation_type"] != op:
            raise CombinerError(
                f"Conflicting operation_type for ID {task_id!r}: {current['operation_type']!r} vs {op!r}."
            )

        if name in workstation_set:
            current["quantity"] = 1
        else:
            current["quantity"] += qty

        for dep in deps:
            if dep not in current["dependencies"]:
                current["dependencies"].append(dep)

    return list(merged.values())
