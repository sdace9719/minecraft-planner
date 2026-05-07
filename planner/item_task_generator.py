"""Phase 2 Item Task Generator."""

from __future__ import annotations

import json
import math
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mojang_datapack.recipes import DatapackRecipeIndex


ROOT = Path(__file__).resolve().parents[1]
BLUEPRINTS_PATH = ROOT / "constants" / "blueprints.json"
TOOLS_PATH = ROOT / "constants" / "tools.json"
CONFIG_PATH = ROOT / "config.json"
MOJANG_DATA_ROOT = ROOT / "mojang-data"
TOOL_SUFFIXES = ("_pickaxe", "_axe", "_shovel", "_hoe", "_sword")


class ItemTaskGeneratorError(RuntimeError):
    """Raised when Phase 2 contracts are violated."""


@dataclass
class Task:
    id: str
    name: str
    quantity: int
    dependencies: list[str]
    operation_type: str


@dataclass(frozen=True)
class _Node:
    item: str
    operation: str
    prerequisites: tuple[str, ...]
    station: str | None
    recipe_type: str | None
    ingredients: dict[str, int]


def _task_id(operation: str, item: str) -> str:
    return f"{operation.upper()}:{item}"


def _parse_tier_from_tool_name(tool_name: str) -> str:
    for suffix in TOOL_SUFFIXES:
        if tool_name.endswith(suffix):
            return tool_name[: -len(suffix)]
    raise ItemTaskGeneratorError(f"Cannot parse tool tier from dependency {tool_name!r}.")


def _is_tool_name(name: str) -> bool:
    return name.endswith(TOOL_SUFFIXES)


def _safe_ceil_div(numerator: int, denominator: int) -> int:
    if denominator <= 0:
        raise ItemTaskGeneratorError(f"Denominator must be positive; got {denominator}.")
    if numerator < 0:
        raise ItemTaskGeneratorError(f"Numerator must be non-negative; got {numerator}.")
    if numerator == 0:
        return 0
    return math.ceil(numerator / denominator)


def _assert_phase2_math_contracts() -> None:
    checks = {
        (59, 1): 1,
        (59, 59): 1,
        (59, 60): 2,
        (250, 600): 3,
        (250, 0): 0,
    }
    for (durability, blocks), expected in checks.items():
        got = _safe_ceil_div(blocks, durability)
        if got != expected:
            raise ItemTaskGeneratorError(
                f"Durability contract failure for ({durability}, {blocks}): expected {expected}, got {got}."
            )


class ItemTaskGenerator:
    """Phase 2 implementation: single-target and global-target task generation."""

    def __init__(
        self,
        blueprints_path: Path = BLUEPRINTS_PATH,
        tools_path: Path = TOOLS_PATH,
        config_path: Path = CONFIG_PATH,
    ):
        _assert_phase2_math_contracts()
        self.blueprints = self._load_blueprints(blueprints_path)
        self.tool_durability = self._load_tool_durability(tools_path)
        self.recipe_index = self._load_recipe_index(config_path)
        self._node_cache: dict[str, _Node] = {}

    @staticmethod
    def _load_blueprints(path: Path) -> dict[str, list[dict[str, Any]]]:
        if not path.exists():
            raise ItemTaskGeneratorError(f"Missing blueprints file: {path}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        blueprints = payload.get("blueprints")
        if not isinstance(blueprints, dict):
            raise ItemTaskGeneratorError("blueprints.json must contain a top-level 'blueprints' object.")
        return blueprints

    @staticmethod
    def _load_tool_durability(path: Path) -> dict[str, int]:
        if not path.exists():
            raise ItemTaskGeneratorError(f"Missing tools file: {path}")
        raw = json.loads(path.read_text(encoding="utf-8"))
        output: dict[str, int] = {}
        for tier, values in raw.items():
            if not isinstance(values, dict) or "durability" not in values:
                raise ItemTaskGeneratorError(f"tools.json tier {tier!r} missing durability.")
            durability = int(values["durability"])
            if durability <= 0:
                raise ItemTaskGeneratorError(f"tools.json tier {tier!r} has non-positive durability {durability}.")
            output[str(tier)] = durability
        return output

    @staticmethod
    def _load_recipe_index(config_path: Path) -> DatapackRecipeIndex:
        if not config_path.exists():
            raise ItemTaskGeneratorError(f"Missing config file: {config_path}")
        config = json.loads(config_path.read_text(encoding="utf-8"))
        version = config.get("minecraft_version")
        if not isinstance(version, str) or not version:
            raise ItemTaskGeneratorError("config.json missing minecraft_version.")
        recipe_dir = MOJANG_DATA_ROOT / version / "data" / "minecraft" / "recipe"
        tag_dir = MOJANG_DATA_ROOT / version / "data" / "minecraft" / "tags" / "item"
        if not recipe_dir.exists():
            raise ItemTaskGeneratorError(f"Missing recipe directory: {recipe_dir}")
        index = DatapackRecipeIndex(recipe_dir, item_tag_dir=tag_dir)
        index.load()
        return index

    def _resolve_node(self, item: str) -> _Node:
        if item in self._node_cache:
            return self._node_cache[item]

        blueprint = self.blueprints.get(item)
        if not isinstance(blueprint, list) or not blueprint:
            raise ItemTaskGeneratorError(f"No blueprint found for item {item!r}.")

        node_entry = None
        for candidate in blueprint:
            if candidate.get("item") == item:
                node_entry = candidate
                break
        if node_entry is None:
            raise ItemTaskGeneratorError(f"Blueprint {item!r} does not contain terminal node for itself.")

        operation = node_entry.get("operation")
        prerequisites = node_entry.get("prerequisites")
        if not isinstance(operation, str) or not operation:
            raise ItemTaskGeneratorError(f"Blueprint node {item!r} missing operation.")
        if not isinstance(prerequisites, list):
            raise ItemTaskGeneratorError(f"Blueprint node {item!r} missing prerequisites array.")

        ingredients_raw = node_entry.get("ingredients", {})
        if ingredients_raw is None:
            ingredients_raw = {}
        if not isinstance(ingredients_raw, dict):
            raise ItemTaskGeneratorError(f"Blueprint node {item!r} has invalid ingredients map.")
        ingredients: dict[str, int] = {}
        for dep_name, dep_qty in ingredients_raw.items():
            qty = int(dep_qty)
            if qty <= 0:
                raise ItemTaskGeneratorError(f"Blueprint node {item!r} has non-positive ingredient quantity.")
            ingredients[str(dep_name)] = qty

        station = node_entry.get("station")
        if station is not None and not isinstance(station, str):
            raise ItemTaskGeneratorError(f"Blueprint node {item!r} has invalid station field.")
        recipe_type = node_entry.get("recipe_type")
        if recipe_type is not None and not isinstance(recipe_type, str):
            raise ItemTaskGeneratorError(f"Blueprint node {item!r} has invalid recipe_type field.")

        node = _Node(
            item=item,
            operation=operation,
            prerequisites=tuple(str(dep) for dep in prerequisites),
            station=station,
            recipe_type=recipe_type,
            ingredients=ingredients,
        )
        self._node_cache[item] = node
        return node

    def _recipe_yield_for(self, node: _Node) -> int:
        if node.operation not in {"craft", "smelt"}:
            return 1
        if node.recipe_type is None:
            raise ItemTaskGeneratorError(f"Recipe node {node.item!r} is missing recipe_type.")
        candidates = self.recipe_index.get_all(node.item)
        matches = [
            recipe
            for recipe in candidates
            if recipe.raw_type == node.recipe_type
            and recipe.action == node.operation
            and recipe.station == (node.station or "player")
            and dict(recipe.ingredients) == node.ingredients
        ]
        if not matches:
            raise ItemTaskGeneratorError(
                f"Could not resolve recipe yield for {node.item!r} ({node.operation}, {node.recipe_type})."
            )
        result_count = int(matches[0].result_count)
        if result_count <= 0:
            raise ItemTaskGeneratorError(f"Invalid non-positive recipe yield for {node.item!r}.")
        return result_count

    def _dependency_items(self, node: _Node) -> list[str]:
        deps = list(node.prerequisites)
        if node.operation == "smelt":
            deps.append("furnace")
            deps.append("oak_planks")
        if node.operation == "craft" and node.station == "crafting_table":
            deps.append("crafting_table")
        seen: set[str] = set()
        ordered: list[str] = []
        for dep in deps:
            if dep in seen:
                continue
            seen.add(dep)
            ordered.append(dep)
        return ordered

    def _dependency_quantity(self, node: _Node, dependency_item: str, target_quantity: int) -> int:
        if target_quantity <= 0:
            raise ItemTaskGeneratorError(f"Target quantity must be positive for {node.item!r}.")

        if dependency_item == "furnace":
            return 1
        if dependency_item == "crafting_table":
            return 1
        if node.operation == "smelt" and dependency_item == "oak_planks":
            # Fuel math: 1 plank = 1.5 smelts.
            return math.ceil(target_quantity / 1.5)

        if node.operation in {"craft", "smelt"}:
            if dependency_item not in node.ingredients:
                raise ItemTaskGeneratorError(
                    f"Dependency {dependency_item!r} missing in ingredients for recipe node {node.item!r}."
                )
            recipe_yield = self._recipe_yield_for(node)
            runs = math.ceil(target_quantity / recipe_yield)
            return runs * node.ingredients[dependency_item]

        if node.operation in {"mine", "gather", "sword", "find"}:
            if _is_tool_name(dependency_item):
                tier = _parse_tier_from_tool_name(dependency_item)
                if tier not in self.tool_durability:
                    raise ItemTaskGeneratorError(
                        f"Missing durability for tier {tier!r} required by {dependency_item!r}."
                    )
                return _safe_ceil_div(target_quantity, self.tool_durability[tier])
            return target_quantity

        raise ItemTaskGeneratorError(f"Unsupported operation {node.operation!r} for node {node.item!r}.")

    def generate_single_item_tasks(self, item_name: str, quantity: int) -> list[Task]:
        if not isinstance(item_name, str) or not item_name:
            raise ItemTaskGeneratorError("item_name must be a non-empty string.")
        if not isinstance(quantity, int) or quantity <= 0:
            raise ItemTaskGeneratorError("quantity must be a positive integer.")

        task_qty: dict[str, int] = defaultdict(int)
        task_deps: dict[str, list[str]] = {}
        task_meta: dict[str, tuple[str, str]] = {}
        visiting: list[str] = []

        def expand(required_item: str, required_qty: int) -> None:
            if required_qty <= 0:
                raise ItemTaskGeneratorError(f"Non-positive required quantity for item {required_item!r}.")
            if required_item in visiting:
                cycle_start = visiting.index(required_item)
                cycle = visiting[cycle_start:] + [required_item]
                raise ItemTaskGeneratorError(f"Circular dependency detected: {' -> '.join(cycle)}")

            node = self._resolve_node(required_item)
            node_id = _task_id(node.operation, node.item)
            task_qty[node_id] += required_qty
            task_meta[node_id] = (node.item, node.operation)

            dependency_items = self._dependency_items(node)
            dependency_ids = [_task_id(self._resolve_node(dep).operation, dep) for dep in dependency_items]
            task_deps[node_id] = dependency_ids

            visiting.append(required_item)
            try:
                for dep_item in dependency_items:
                    dep_qty = self._dependency_quantity(node, dep_item, required_qty)
                    expand(dep_item, dep_qty)
            finally:
                visiting.pop()

        expand(item_name, quantity)

        for node_id, deps in task_deps.items():
            for dep_id in deps:
                if dep_id not in task_qty:
                    item, _op = task_meta[node_id]
                    raise ItemTaskGeneratorError(
                        f"Task {item!r} has unresolved dependency ID {dep_id!r}."
                    )

        output: list[Task] = []
        for node_id, (name, op) in task_meta.items():
            output.append(
                Task(
                    id=node_id,
                    name=name,
                    quantity=int(task_qty[node_id]),
                    dependencies=list(task_deps.get(node_id, [])),
                    operation_type=op,
                )
            )
        return output

    def generate_global_target_queue(self, targets: list[dict[str, Any]]) -> list[Task]:
        if not isinstance(targets, list) or not targets:
            raise ItemTaskGeneratorError("targets must be a non-empty list.")
        combined: list[Task] = []
        for entry in targets:
            if not isinstance(entry, dict):
                raise ItemTaskGeneratorError("Each target must be an object with item and quantity.")
            item = entry.get("item")
            qty = entry.get("quantity")
            if not isinstance(item, str) or not item:
                raise ItemTaskGeneratorError(f"Invalid target item entry: {entry!r}")
            if not isinstance(qty, int) or qty <= 0:
                raise ItemTaskGeneratorError(f"Invalid quantity for target {item!r}: {qty!r}")
            combined.extend(self.generate_single_item_tasks(item, qty))
        return combined


def generate_single_item_tasks(item_name: str, quantity: int) -> list[Task]:
    return ItemTaskGenerator().generate_single_item_tasks(item_name, quantity)


def generate_global_target_queue(targets: list[dict[str, Any]]) -> list[Task]:
    return ItemTaskGenerator().generate_global_target_queue(targets)
