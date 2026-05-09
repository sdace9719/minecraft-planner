"""Phase 4B DAG router: chunking + two-pass rewiring."""

from __future__ import annotations

import copy
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from planner.global_math_optimizer import BLUEPRINTS_PATH
from planner.item_task_generator import ItemTaskGenerator

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PHASE4A_PATH = ROOT / "phase4a_optimized_global.json"
DEFAULT_PHASE4_PATH = ROOT / "tests" / "input_materials_test.phase4.json"

WORKSTATION_EXCLUSION = {
    "crafting_table",
    "furnace",
    "blast_furnace",
    "smoker",
    "stonecutter",
    "loom",
    "brewing_stand",
}
ARMOR_SUFFIXES = ("_helmet", "_chestplate", "_leggings", "_boots")
UNSTACKABLE_ITEMS = {"bow", "crossbow", "trident", "shield"}
TOOL_SUFFIXES = ("_pickaxe", "_axe", "_shovel", "_hoe", "_sword")


class DagRouterError(ValueError):
    """Raised when Phase 4B contracts are violated."""


@dataclass
class _Node:
    id: str
    name: str
    quantity: int
    dependencies: list[str]
    operation_type: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "quantity": self.quantity,
            "dependencies": list(self.dependencies),
            "operation_type": self.operation_type,
        }


@dataclass
class _Chunk:
    id: str
    parent_id: str
    name: str
    quantity: int
    dependencies: list[str]
    operation_type: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "quantity": self.quantity,
            "dependencies": list(self.dependencies),
            "operation_type": self.operation_type,
        }


class DagRouter:
    """Implements planner2 Phase 4B Step 2 -> Step 3."""

    def __init__(
        self,
        blueprints_path: Path = BLUEPRINTS_PATH,
        phase4a_input_path: Path = DEFAULT_PHASE4A_PATH,
        phase4_output_path: Path = DEFAULT_PHASE4_PATH,
    ):
        self.phase4a_input_path = phase4a_input_path
        self.phase4_output_path = phase4_output_path
        self.blueprints = self._load_blueprints(blueprints_path)
        self.generator = ItemTaskGenerator(blueprints_path=blueprints_path)

    @staticmethod
    def _load_blueprints(path: Path) -> dict[str, list[dict[str, Any]]]:
        if not path.exists():
            raise DagRouterError(f"Missing blueprints file: {path}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        blueprints = payload.get("blueprints")
        if not isinstance(blueprints, dict):
            raise DagRouterError("blueprints.json missing top-level blueprints object.")
        return blueprints

    @staticmethod
    def _coerce_task(raw: dict[str, Any]) -> _Node:
        required = ("id", "name", "quantity", "dependencies", "operation_type")
        for key in required:
            if key not in raw:
                raise DagRouterError(f"Phase 4A node missing required field {key!r}.")
        if not isinstance(raw["id"], str) or not raw["id"]:
            raise DagRouterError("Node id must be a non-empty string.")
        if not isinstance(raw["name"], str) or not raw["name"]:
            raise DagRouterError(f"Node {raw['id']!r} has invalid name.")
        if not isinstance(raw["quantity"], int) or raw["quantity"] <= 0:
            raise DagRouterError(f"Node {raw['id']!r} has invalid non-positive quantity.")
        if not isinstance(raw["dependencies"], list):
            raise DagRouterError(f"Node {raw['id']!r} dependencies must be a list.")
        for dep in raw["dependencies"]:
            if not isinstance(dep, str) or not dep:
                raise DagRouterError(f"Node {raw['id']!r} has invalid dependency value.")
        if not isinstance(raw["operation_type"], str) or not raw["operation_type"]:
            raise DagRouterError(f"Node {raw['id']!r} operation_type must be a non-empty string.")
        return _Node(
            id=raw["id"],
            name=raw["name"],
            quantity=int(raw["quantity"]),
            dependencies=list(dict.fromkeys(raw["dependencies"])),
            operation_type=raw["operation_type"],
        )

    def _parse_graph(self, tasks: list[dict[str, Any]]) -> dict[str, _Node]:
        nodes: dict[str, _Node] = {}
        for raw in copy.deepcopy(tasks):
            node = self._coerce_task(raw)
            if node.id in nodes:
                raise DagRouterError(f"Duplicate Phase 4A node id {node.id!r}.")
            nodes[node.id] = node
        for node in nodes.values():
            for dep in node.dependencies:
                if dep not in nodes:
                    raise DagRouterError(f"Dangling dependency {dep!r} on node {node.id!r}.")
        return nodes

    @staticmethod
    def _is_unstackable(item_name: str) -> bool:
        base = item_name.split("_mvb_")[0]
        return (
            base.endswith(TOOL_SUFFIXES)
            or base.endswith(ARMOR_SUFFIXES)
            or item_name in UNSTACKABLE_ITEMS
        )

    def _yield_per_run(self, node: _Node) -> int:
        if node.operation_type not in {"craft", "smelt"}:
            return 1
        resolved = self.generator._resolve_node(node.name.split("_mvb_")[0])
        if resolved.operation != node.operation_type:
            raise DagRouterError(
                f"Blueprint operation mismatch for {node.name!r}: {resolved.operation!r} vs {node.operation_type!r}."
            )
        out = self.generator._recipe_yield_for(resolved)
        if out <= 0:
            raise DagRouterError(f"Invalid non-positive yield for item {node.name!r}.")
        return out

    @staticmethod
    def _chunk_sizes_for_quantity(quantity: int, chunk_cap: int, yield_per_run: int) -> list[int]:
        if quantity <= 0:
            raise DagRouterError(f"Cannot chunk non-positive quantity {quantity}.")
        if chunk_cap <= 0:
            raise DagRouterError(f"Chunk cap must be positive, got {chunk_cap}.")
        if yield_per_run <= 0:
            raise DagRouterError(f"Yield per run must be positive, got {yield_per_run}.")
        out: list[int] = []
        remaining = quantity
        while remaining > chunk_cap:
            out.append(chunk_cap)
            remaining -= chunk_cap
        padded = int(math.ceil(remaining / yield_per_run) * yield_per_run)
        out.append(padded)
        return out

    def _step2_chunk(self, nodes: dict[str, _Node]) -> tuple[dict[str, _Chunk], dict[str, list[str]]]:
        chunks: dict[str, _Chunk] = {}
        parent_to_chunks: dict[str, list[str]] = {}
        for parent in nodes.values():
            if parent.name in WORKSTATION_EXCLUSION:
                sizes = [parent.quantity]
            elif self._is_unstackable(parent.name):
                sizes = [1 for _ in range(parent.quantity)]
            else:
                ypr = self._yield_per_run(parent)
                chunk_cap = (64 // ypr) * ypr
                if chunk_cap <= 0:
                    raise DagRouterError(f"Invalid chunk cap for parent {parent.id!r}.")
                if parent.quantity <= 64:
                    sizes = [int(math.ceil(parent.quantity / ypr) * ypr)]
                else:
                    sizes = self._chunk_sizes_for_quantity(parent.quantity, chunk_cap, ypr)

            chunk_ids: list[str] = []
            for idx, size in enumerate(sizes, start=1):
                chunk_id = f"{parent.id}_chunk_{idx}"
                if chunk_id in chunks:
                    raise DagRouterError(f"Chunk ID collision: {chunk_id!r}.")
                chunks[chunk_id] = _Chunk(
                    id=chunk_id,
                    parent_id=parent.id,
                    name=parent.name,
                    quantity=size,
                    dependencies=list(parent.dependencies),
                    operation_type=parent.operation_type,
                )
                chunk_ids.append(chunk_id)
            parent_to_chunks[parent.id] = chunk_ids
        return chunks, parent_to_chunks

    @staticmethod
    def _is_tool_name(item_name: str) -> bool:
        base = item_name.split("_mvb_")[0]
        return base.endswith(TOOL_SUFFIXES)

    def _tool_capacity(self, tool_name: str) -> int:
        base_name = tool_name.split("_mvb_")[0]
        tier = base_name.split("_", 1)[0]
        if tier == "wooden":
            return 59
        if tier == "stone":
            return 131
        if tier == "iron":
            return 250
        if tier == "diamond":
            return 1561
        if tier == "golden":
            return 32
        if tier == "netherite":
            return 2031
        raise DagRouterError(f"Missing durability for tool {tool_name!r}.")

    @staticmethod
    def _chunk_index(chunk_id: str) -> int:
        marker = "_chunk_"
        if marker not in chunk_id:
            raise DagRouterError(f"Invalid chunk id without marker: {chunk_id!r}.")
        try:
            return int(chunk_id.split(marker)[-1])
        except ValueError as exc:
            raise DagRouterError(f"Invalid chunk id suffix for {chunk_id!r}.") from exc

    def _blueprint_terminal_node(self, consumer: _Chunk) -> dict[str, Any]:
        base_name = consumer.name.split("_mvb_")[0]
        entries = self.blueprints.get(base_name)
        if not isinstance(entries, list) or not entries:
            raise DagRouterError(f"Missing blueprint for consumer item {base_name!r}.")
        terminal = [
            entry for entry in entries if entry.get("item") == base_name and entry.get("operation") == consumer.operation_type
        ]
        if not terminal:
            terminal_ops = {"mine", "gather", "sword", "find"}
            terminal = [
                entry
                for entry in entries
                if entry.get("item") == base_name and entry.get("operation") in terminal_ops
            ]
        if not terminal:
            raise DagRouterError(f"Missing terminal blueprint node for {base_name!r}.")
        if len(terminal) > 1:
            ops = [entry.get("operation") for entry in terminal]
            raise DagRouterError(f"Ambiguous terminal blueprint node for {base_name!r}: {ops!r}.")
        return terminal[0]

    def _blueprint_ingredient_count(self, consumer: _Chunk, dependency_name: str) -> int:
        terminal = self._blueprint_terminal_node(consumer)
        ingredients = terminal.get("ingredients", {})
        if not isinstance(ingredients, dict):
            raise DagRouterError(f"Blueprint ingredients for {consumer.name!r} are invalid.")
        return int(ingredients.get(dependency_name, 0))

    def _recipe_yield_for_consumer(self, consumer: _Chunk) -> int:
        if consumer.operation_type not in {"craft", "smelt"}:
            return 1
        resolved = self.generator._resolve_node(consumer.name.split("_mvb_")[0])
        if resolved.operation != consumer.operation_type:
            raise DagRouterError(
                f"Blueprint operation mismatch for {consumer.name!r}: {resolved.operation!r} vs {consumer.operation_type!r}."
            )
        recipe_yield = self.generator._recipe_yield_for(resolved)
        if recipe_yield <= 0:
            raise DagRouterError(f"Invalid non-positive recipe yield for {consumer.name!r}.")
        return recipe_yield

    def _would_create_cycle(self, candidate_src: str, candidate_dst: str, rewired: dict[str, list[str]]) -> bool:
        # Edge is candidate_src -> candidate_dst (src depends on dst).
        # Cycle if we can already reach src from dst.
        stack = [candidate_dst]
        seen: set[str] = set()
        while stack:
            node_id = stack.pop()
            if node_id == candidate_src:
                return True
            if node_id in seen:
                continue
            seen.add(node_id)
            for dep in rewired.get(node_id, []):
                stack.append(dep)
        return False

    def _step3_rewire(
        self,
        chunks: dict[str, _Chunk],
        parent_to_chunks: dict[str, list[str]],
        parents: dict[str, _Node],
    ) -> dict[str, _Chunk]:
        # Pass 1: register capacities only.
        ledger: dict[str, float] = {}
        for chunk_id, chunk in chunks.items():
            base_name = chunk.name.split("_mvb_")[0]
            if base_name in WORKSTATION_EXCLUSION:
                ledger[chunk_id] = float("inf")
            elif self._is_tool_name(chunk.name):
                ledger[chunk_id] = self._tool_capacity(chunk.name)
            else:
                ledger[chunk_id] = chunk.quantity

        # Pass 2: demand consumption + rewiring.
        ordered_chunk_ids = sorted(chunks.keys(), key=lambda cid: (self._chunk_index(cid), cid))
        rewired: dict[str, list[str]] = {cid: [] for cid in ordered_chunk_ids}

        for chunk_id in ordered_chunk_ids:
            chunk = chunks[chunk_id]
            new_deps: list[str] = []
            for dep_parent_id in chunk.dependencies:
                if dep_parent_id not in parents:
                    raise DagRouterError(f"Dangling parent dependency {dep_parent_id!r} for chunk {chunk_id!r}.")
                dep_parent = parents[dep_parent_id]
                if chunk.operation_type == "smelt" and "planks" in dep_parent.name:
                    demand = math.ceil(chunk.quantity / 1.5)
                else:
                    ingredient_count = self._blueprint_ingredient_count(chunk, dep_parent.name.split("_mvb_")[0])
                    if ingredient_count > 0:
                        recipe_yield = self._recipe_yield_for_consumer(chunk)
                        if chunk.quantity % recipe_yield != 0:
                            raise DagRouterError(
                                f"Chunk quantity {chunk.quantity} for {chunk.id!r} is not divisible by yield {recipe_yield}."
                            )
                        runs = chunk.quantity // recipe_yield
                        demand = runs * ingredient_count
                    else:
                        demand = chunk.quantity
                if demand <= 0:
                    continue
                if not isinstance(demand, int):
                    raise DagRouterError(f"Computed non-integer demand {demand!r} for chunk {chunk_id!r}.")

                producers = parent_to_chunks.get(dep_parent_id, [])
                if not producers:
                    raise DagRouterError(
                        f"No producer chunks for dependency {dep_parent_id!r} required by {chunk_id!r}."
                    )
                producers = sorted(producers, key=lambda cid: (self._chunk_index(cid), cid))

                remaining = demand
                for producer_chunk_id in producers:
                    available = ledger.get(producer_chunk_id)
                    if available is None:
                        raise DagRouterError(f"Missing ledger entry for producer {producer_chunk_id!r}.")
                    if available == float("inf"):
                        if producer_chunk_id not in new_deps:
                            new_deps.append(producer_chunk_id)
                        remaining = 0
                        break
                    if available <= 0:
                        continue
                    if self._would_create_cycle(chunk_id, producer_chunk_id, rewired):
                        continue
                    consume = min(int(available), remaining)
                    # Chunk shattering: if a tool is partially consumed, split
                    # off the portion that exactly exhausts it.  This prevents
                    # the next tool from depending on a chunk that also depends
                    # on it (a cycle).
                    if (consume < remaining and consume > 0
                            and self._is_tool_name(chunks[producer_chunk_id].name)
                            and chunk.operation_type in ("mine", "gather")):
                        shard_id = f"{chunk_id}_shard_{producer_chunk_id}"
                        c = 1
                        while shard_id in chunks:
                            c += 1
                            shard_id = f"{chunk_id}_shard_{c}"
                        shard = _Chunk(
                            id=shard_id,
                            parent_id=chunk.parent_id,
                            name=chunk.name,
                            quantity=consume,
                            dependencies=[producer_chunk_id],
                            operation_type=chunk.operation_type,
                        )
                        chunks[shard_id] = shard
                        parent_to_chunks.setdefault(chunk.parent_id, []).append(shard_id)
                        ledger[shard_id] = consume
                        new_deps.append(shard_id)
                        chunk.quantity -= consume
                        ledger[chunk_id] = chunk.quantity
                        demand = chunk.quantity  # remaining demand for original chunk
                        remaining = demand
                        ledger[producer_chunk_id] = available - consume
                        continue

                    ledger[producer_chunk_id] = available - consume
                    remaining -= consume
                    if producer_chunk_id not in new_deps:
                        new_deps.append(producer_chunk_id)
                    if remaining == 0:
                        break
                if remaining > 0:
                    raise ValueError(
                        f"Acyclic capacity exhausted for dependency {dep_parent_id!r} while rewiring {chunk_id!r}; "
                        f"missing={remaining}."
                    )

            rewired[chunk_id] = new_deps
            chunks[chunk_id].dependencies = list(new_deps)

        # Inject JIT execution edges: tool chunk N+1 depends on the final
        # mining chunk that exhausts tool chunk N's durability.  This forces
        # Kahn's algorithm to interleave Craft → Mine → Craft → Mine instead
        # of batching all crafts at the front.
        for chunk_id, chunk in list(chunks.items()):
            if not self._is_tool_name(chunk.name):
                continue
            # Find the next tool chunk from the same parent.
            next_tool = next(
                (c for cid, c in chunks.items()
                 if c.parent_id == chunk.parent_id
                 and self._chunk_index(cid) == self._chunk_index(chunk_id) + 1),
                None,
            )
            if next_tool is None:
                continue
            # Find consumers that depend on THIS chunk but NOT on the next
            # one.  The last such consumer truly exhausts this chunk.
            exhaust_candidates: list[tuple[int, _Chunk]] = []
            for cid, c in chunks.items():
                if (chunk_id in c.dependencies
                        and next_tool.id not in c.dependencies):
                    exhaust_candidates.append((self._chunk_index(cid), c))
            if not exhaust_candidates:
                continue
            exhaust_candidates.sort(key=lambda x: x[0])
            exhaust_chunk = exhaust_candidates[-1][1]
            if exhaust_chunk.id not in next_tool.dependencies:
                next_tool.dependencies.append(exhaust_chunk.id)

        for chunk in chunks.values():
            for dep in chunk.dependencies:
                if dep not in chunks:
                    raise DagRouterError(f"Non-chunk dependency {dep!r} found in final DAG.")
        return chunks

    def route_tasks(self, phase4a_tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        parents = self._parse_graph(phase4a_tasks)
        chunked, parent_to_chunks = self._step2_chunk(parents)
        routed = self._step3_rewire(chunked, parent_to_chunks, parents)
        ordered = sorted(routed.keys(), key=lambda cid: (self._chunk_index(cid), cid))
        return [routed[cid].as_dict() for cid in ordered]

    def route_from_file(self) -> list[dict[str, Any]]:
        if not self.phase4a_input_path.exists():
            raise DagRouterError(f"Missing Phase 4A input file: {self.phase4a_input_path}")
        payload = json.loads(self.phase4a_input_path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise DagRouterError("Phase 4A input must be a JSON array.")
        out = self.route_tasks(payload)
        self.phase4_output_path.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
        return out


def route_phase4a_to_phase4(
    phase4a_tasks: list[dict[str, Any]],
    blueprints_path: Path = BLUEPRINTS_PATH,
) -> list[dict[str, Any]]:
    return DagRouter(blueprints_path=blueprints_path).route_tasks(phase4a_tasks)

