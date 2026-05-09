"""Phase 4A global math optimizer."""

from __future__ import annotations

import copy
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from planner.item_task_generator import ItemTaskGenerator

ROOT = Path(__file__).resolve().parents[1]
BLUEPRINTS_PATH = ROOT / "constants" / "blueprints.json"
DEFAULT_PHASE3_PATH = ROOT / "tests" / "input_materials_test.phase3.json"
DEFAULT_PHASE4A_OUTPUT_PATH = ROOT / "phase4a_optimized_global.json"
TOOLS_PATH = ROOT / "constants" / "tools.json"
HARDNESS_PATH = ROOT / "constants" / "block_hardness.json"
ORE_DATA_PATH = ROOT / "constants" / "ore_data.json"

# Seconds per game tick (20 TPS).
TICK_SECONDS = 1.0 / 20.0

TOOL_DURABILITY = {
    "wooden_pickaxe": 59,
    "stone_pickaxe": 131,
    "iron_pickaxe": 250,
    "diamond_pickaxe": 1561,
    "wooden_axe": 59,
    "stone_axe": 131,
    "iron_axe": 250,
    "wooden_shovel": 59,
    "stone_shovel": 131,
    "iron_shovel": 250,
    "diamond_shovel": 1561,
    "diamond_axe": 1561,
    "wooden_hoe": 59,
    "stone_hoe": 131,
    "iron_hoe": 250,
    "wooden_sword": 59,
    "stone_sword": 131,
    "iron_sword": 250,
}
TOOL_SUFFIXES = ("_pickaxe", "_axe", "_shovel", "_hoe", "_sword")


class GlobalMathOptimizerError(ValueError):
    """Raised when Phase 4A contracts are violated."""


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


class GlobalMathOptimizer:
    """Implements planner2.md Phase 4A in strict order 1B -> 1C -> 1A."""

    def __init__(
        self,
        blueprints_path: Path = BLUEPRINTS_PATH,
        phase3_input_path: Path = DEFAULT_PHASE3_PATH,
        phase4a_output_path: Path = DEFAULT_PHASE4A_OUTPUT_PATH,
        tools_path: Path = TOOLS_PATH,
        hardness_path: Path = HARDNESS_PATH,
    ):
        self.blueprints = self._load_blueprints(blueprints_path)
        self.phase3_input_path = phase3_input_path
        self.phase4a_output_path = phase4a_output_path
        self.generator = ItemTaskGenerator(blueprints_path=blueprints_path)
        self._mvb_counter = 0
        self.tool_data = self._load_tools(tools_path)
        self.hardness = self._load_hardness(hardness_path)
        self.ore_data = self._load_ore_data(ORE_DATA_PATH)

    @staticmethod
    def _load_ore_data(path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _load_tools(path: Path) -> dict[str, Any]:
        if not path.exists():
            raise GlobalMathOptimizerError(f"Missing tools file: {path}")
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _load_hardness(path: Path) -> dict[str, float]:
        if not path.exists():
            raise GlobalMathOptimizerError(f"Missing hardness file: {path}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        raw = payload.get("hardness")
        if not isinstance(raw, dict):
            raise GlobalMathOptimizerError("block_hardness.json missing 'hardness' object.")
        return {str(k): float(v) for k, v in raw.items()}

    def _tblock(self, block_name: str, multiplier: float) -> float:
        """Breaking time in seconds for one block with the given tool multiplier.

        Formula (Minecraft physics):
            Mh = hardness * 30
            if multiplier >= Mh: return 1 tick (instant)
            Tbreak = ceil(Mh / multiplier)
            Tblock = (Tbreak + 6) ticks  →  seconds = ticks / 20
        """
        h = self.hardness.get(block_name)
        if h is None:
            raise GlobalMathOptimizerError(f"Missing hardness for block {block_name!r}.")
        if h <= 0 or h == -1:
            return 0.0  # unbreakable or instant
        mh = h * 30.0
        if multiplier >= mh:
            return TICK_SECONDS  # 1 tick instant
        tbreak = math.ceil(mh / multiplier)
        return (tbreak + 6) * TICK_SECONDS

    def _tool_speed(self, tier: str) -> float:
        """Tool multiplier for a given tier (wooden/stone/iron/diamond)."""
        entry = self.tool_data.get(tier, {})
        if not isinstance(entry, dict):
            raise GlobalMathOptimizerError(f"Missing tool data for tier {tier!r}.")
        return float(entry.get("speed", 1.0))

    def _tool_durability_from_data(self, tier: str) -> int:
        """Durability from tools.json for a given tier."""
        entry = self.tool_data.get(tier, {})
        if not isinstance(entry, dict):
            raise GlobalMathOptimizerError(f"Missing tool data for tier {tier!r}.")
        return int(entry.get("durability", 59))

    @staticmethod
    def _load_blueprints(path: Path) -> dict[str, list[dict[str, Any]]]:
        if not path.exists():
            raise GlobalMathOptimizerError(f"Missing blueprints file: {path}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        blueprints = payload.get("blueprints")
        if not isinstance(blueprints, dict):
            raise GlobalMathOptimizerError("blueprints.json missing top-level blueprints object.")
        return blueprints

    @staticmethod
    def _coerce_task(raw: dict[str, Any]) -> _Node:
        required = ("id", "name", "quantity", "dependencies", "operation_type")
        for key in required:
            if key not in raw:
                raise GlobalMathOptimizerError(f"Phase 3 task missing required field {key!r}.")
        node_id = raw["id"]
        name = raw["name"]
        quantity = raw["quantity"]
        deps = raw["dependencies"]
        op = raw["operation_type"]
        if not isinstance(node_id, str) or not node_id:
            raise GlobalMathOptimizerError("Task id must be non-empty string.")
        if not isinstance(name, str) or not name:
            raise GlobalMathOptimizerError(f"Task {node_id!r} has invalid name.")
        if not isinstance(quantity, int):
            raise GlobalMathOptimizerError(f"Task {node_id!r} quantity must be integer.")
        if not isinstance(deps, list):
            raise GlobalMathOptimizerError(f"Task {node_id!r} dependencies must be list.")
        for dep in deps:
            if not isinstance(dep, str) or not dep:
                raise GlobalMathOptimizerError(f"Task {node_id!r} has invalid dependency value.")
        if not isinstance(op, str) or not op:
            raise GlobalMathOptimizerError(f"Task {node_id!r} operation_type must be non-empty string.")
        return _Node(id=node_id, name=name, quantity=quantity, dependencies=list(dict.fromkeys(deps)), operation_type=op)

    def _parse_graph(self, tasks: list[dict[str, Any]]) -> dict[str, _Node]:
        nodes: dict[str, _Node] = {}
        for raw in copy.deepcopy(tasks):
            node = self._coerce_task(raw)
            if node.id in nodes:
                raise GlobalMathOptimizerError(f"Duplicate task id in Phase 3 input: {node.id!r}.")
            nodes[node.id] = node
        for node in nodes.values():
            for dep in node.dependencies:
                if dep not in nodes:
                    raise GlobalMathOptimizerError(f"Dangling dependency {dep!r} on task {node.id!r}.")
        return nodes

    def _single_node_by_name(self, nodes: dict[str, _Node], item_name: str) -> _Node:
        matches = [node for node in nodes.values() if node.name == item_name]
        if not matches:
            raise GlobalMathOptimizerError(f"Unable to locate source node for item {item_name!r}.")
        if len(matches) > 1:
            ids = [node.id for node in matches]
            raise GlobalMathOptimizerError(f"Ambiguous source node for item {item_name!r}: {ids!r}")
        return matches[0]

    def _blueprint_recipe_node(self, item_name: str, operation: str | None = None) -> dict[str, Any]:
        entries = self.blueprints.get(item_name)
        if not isinstance(entries, list) or not entries:
            raise GlobalMathOptimizerError(f"Missing blueprint for {item_name!r}.")
        candidates = [entry for entry in entries if entry.get("item") == item_name]
        if operation is not None:
            candidates = [entry for entry in candidates if entry.get("operation") == operation]
        if not candidates:
            raise GlobalMathOptimizerError(
                f"Blueprint for {item_name!r} missing terminal node for operation {operation!r}."
            )
        return candidates[0]

    def _terminal_node_for_item(self, item_name: str, operation_hint: str) -> dict[str, Any]:
        entries = self.blueprints.get(item_name)
        if not isinstance(entries, list) or not entries:
            raise GlobalMathOptimizerError(f"Missing blueprint for {item_name!r}.")
        exact = [entry for entry in entries if entry.get("item") == item_name and entry.get("operation") == operation_hint]
        if exact:
            return exact[0]
        terminal_ops = {"mine", "gather", "sword", "find"}
        fallback = [entry for entry in entries if entry.get("item") == item_name and entry.get("operation") in terminal_ops]
        if not fallback:
            raise GlobalMathOptimizerError(
                f"Blueprint for {item_name!r} missing terminal node compatible with {operation_hint!r}."
            )
        if len(fallback) > 1:
            ops = [entry.get("operation") for entry in fallback]
            raise GlobalMathOptimizerError(f"Ambiguous terminal node for {item_name!r}: operations={ops!r}.")
        return fallback[0]

    def _remove_node(self, nodes: dict[str, _Node], node_id: str) -> None:
        if node_id not in nodes:
            return
        del nodes[node_id]
        for parent in list(nodes.values()):
            if node_id in parent.dependencies:
                parent.dependencies = [dep for dep in parent.dependencies if dep != node_id]

    def _prune_non_positive(self, nodes: dict[str, _Node]) -> None:
        prune_ids = [node.id for node in nodes.values() if node.quantity <= 0]
        for node_id in prune_ids:
            self._remove_node(nodes, node_id)

    def _is_tool(self, item_name: str) -> bool:
        base = item_name.split("_mvb_")[0]
        return base.endswith(TOOL_SUFFIXES)

    def _tool_durability(self, item_name: str) -> int:
        if item_name in TOOL_DURABILITY:
            return TOOL_DURABILITY[item_name]
        if item_name.startswith("wooden_") and self._is_tool(item_name):
            return 59
        raise GlobalMathOptimizerError(f"Missing durability mapping for tool {item_name!r}.")

    def _station_for_recipe_node(self, recipe_node: dict[str, Any]) -> str | None:
        station = recipe_node.get("station")
        if isinstance(station, str) and station not in {"", "player", "none"}:
            return station
        return None

    def _find_node_for_delta(self, nodes: dict[str, _Node], item_name: str) -> _Node | None:
        """Locate the node to apply a delta to (global nodes only). Returns None if missing."""
        matches = [node for node in nodes.values() if node.name == item_name]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            # Prefer the bulk node over bootstrap split nodes.
            bulk = [n for n in matches if "_bootstrap" not in n.id]
            if len(bulk) == 1:
                return bulk[0]
            ids = [node.id for node in matches]
            raise GlobalMathOptimizerError(f"Ambiguous source node for item {item_name!r}: {ids!r}")
        return None

    def _recursive_apply_delta(
        self,
        nodes: dict[str, _Node],
        item_name: str,
        quantity_delta: int,
        stack: set[str] | None = None,
    ) -> None:
        if quantity_delta == 0:
            return
        if stack is None:
            stack = set()
        if item_name in stack:
            raise GlobalMathOptimizerError(f"Recursive delta cycle detected at item {item_name!r}.")
        stack.add(item_name)
        try:
            node = self._find_node_for_delta(nodes, item_name)
            if node is None:
                return  # node was pruned by an earlier deduction
            old_qty = node.quantity
            new_qty = old_qty + quantity_delta
            node.quantity = new_qty
            if new_qty <= 0:
                self._remove_node(nodes, node.id)
                return

            if node.operation_type not in {"craft", "smelt"}:
                return

            base_item_name = item_name.split("_mvb_")[0]
            recipe_node = self._blueprint_recipe_node(base_item_name, node.operation_type)
            ingredients = recipe_node.get("ingredients")
            if not isinstance(ingredients, dict):
                raise GlobalMathOptimizerError(f"Recipe node for {item_name!r} missing ingredients map.")

            blueprint_task = self.generator._resolve_node(base_item_name)
            yield_per_run = self.generator._recipe_yield_for(blueprint_task)
            old_runs = math.ceil(old_qty / yield_per_run) if old_qty > 0 else 0
            new_runs = math.ceil(new_qty / yield_per_run)
            run_delta = new_runs - old_runs
            if run_delta == 0:
                return
            mvb_suffix = ""
            if "_mvb_" in item_name:
                mvb_suffix = "_mvb_" + item_name.split("_mvb_", 1)[1]
            for ing_name, ing_per_run in ingredients.items():
                ingredient_delta = run_delta * int(ing_per_run)
                target_name = f"{ing_name}{mvb_suffix}"
                self._recursive_apply_delta(nodes, target_name, ingredient_delta, stack)
        finally:
            stack.remove(item_name)

    def _inject_mvb_chain(self, nodes: dict[str, _Node], tool_name: str) -> tuple[str, dict[str, int]]:
        self._mvb_counter += 1
        suffix = f"_mvb_{self._mvb_counter}"
        chain = self.generator.generate_single_item_tasks(tool_name, 1)
        id_map = {task.id: f"{task.id}{suffix}" for task in chain}
        root_id = f"CRAFT:{tool_name}{suffix}"
        source_usage: dict[str, int] = {}
        for task in chain:
            new_id = id_map[task.id]
            if new_id in nodes:
                raise GlobalMathOptimizerError(f"MVB ID collision: {new_id!r}.")
            rewritten_deps = [id_map[dep] for dep in task.dependencies]
            nodes[new_id] = _Node(
                id=new_id,
                name=f"{task.name}{suffix}",
                quantity=task.quantity,
                dependencies=rewritten_deps,
                operation_type=task.operation_type,
            )
            if task.operation_type in {"mine", "gather", "smelt", "craft"}:
                source_usage[task.name] = source_usage.get(task.name, 0) + int(task.quantity)
        if root_id not in nodes:
            raise GlobalMathOptimizerError(f"Injected MVB chain missing root node {root_id!r}.")
        return root_id, source_usage

    # ── ROI helpers ──────────────────────────────────────────────────────

    TIER_ORDER = ("wooden", "stone", "iron", "diamond")

    def _search_params(self, tier: str) -> tuple[int, int, str]:
        """Return (blocks_to_search, vein_size, junk_block_name) for a tier."""
        entry = self.tool_data.get(tier, {})
        vreq = int(entry.get("blocks_to_break", 0))
        vein = int(entry.get("vein_size", 1))
        junk = str(entry.get("junk_block", "stone"))
        return vreq, vein, junk

    def _source_block_for(self, item_name: str) -> str:
        """Primary source block that drops this item."""
        entries = self.blueprints.get(item_name, [])
        for e in entries:
            if e.get("item") == item_name:
                blocks = e.get("source_blocks", [])
                if blocks:
                    return str(blocks[0])
        # Fallback: use the item name itself (common for stone, dirt, etc.)
        return item_name

    def _compute_breaking_time(
        self, tier: str, blocks: dict[str, int]
    ) -> float:
        """Total seconds to break the given block→count mapping with a tier tool."""
        speed = self._tool_speed(tier)
        total = 0.0
        for block_name, count in blocks.items():
            total += self._tblock(block_name, speed) * count
        return total

    def _compute_tacq(
        self,
        tier: str,
        qty: int,
        ore_block: str,
        search_block: str,
        vreq: int,
        vein_size: int,
        avg_yield: float = 1.0,
    ) -> float:
        """Time (seconds) to acquire *qty* ore items using tools of *tier*.

        *qty* is items needed (e.g. 216 copper ingots → 216 copper_ore items).
        *avg_yield* converts items to blocks (e.g. copper=3.5 items/block).
        *vein_size* is ore blocks found per vein.
        """
        if vreq <= 0 or vein_size <= 0:
            return self._tblock(ore_block, self._tool_speed(tier)) * qty

        ore_blocks = max(1, math.ceil(qty / avg_yield))
        veins = max(1, math.ceil(ore_blocks / vein_size))
        search_blocks_total = veins * vreq

        blocks: dict[str, int] = {ore_block: ore_blocks, search_block: search_blocks_total}
        return self._compute_breaking_time(tier, blocks)

    def _compute_costboot(
        self,
        from_tier: str,
        to_tier: str,
        tool_class: str,
    ) -> float:
        """Time (seconds) to bootstrap ONE *to_tier* tool using *from_tier* tools.

        Includes cascading tool wear: if the *from_tier* tool breaks during the
        bootstrap, the cost of crafting replacement copies is added recursively.
        Bottoms out at hand (no wear).
        """
        if from_tier == "hand":
            speed = 1.0
            dur = float("inf")  # hand doesn't wear out
        else:
            speed = self._tool_speed(from_tier)
            dur = self._tool_durability_from_data(from_tier)

        tool_name = f"{to_tier}_{tool_class}"
        chain = self.generator.generate_single_item_tasks(tool_name, 1)

        total_blocks = 0.0
        total = 0.0
        for task in chain:
            if task.operation_type == "smelt":
                total += 10.0
                continue
            if task.operation_type in ("mine", "gather"):
                block = self._source_block_for(task.name)
                q = int(task.quantity)
                total_blocks += q
                terminal = self._terminal_node_for_item(task.name, task.operation_type)
                harvest = terminal.get("harvest", {})
                req_tier = str(harvest.get("min_tier", "wooden"))
                if req_tier != "wooden" and req_tier != "hand":
                    # Derive ore key (e.g. "deepslate_iron_ore" → "iron").
                    ore_key = task.name
                    if ore_key.startswith("deepslate_"):
                        ore_key = ore_key[len("deepslate_"):]
                    if ore_key.endswith("_ore"):
                        ore_key = ore_key[:-len("_ore")]
                    # Check ore_data.json first, then tools.json tier, then fallback.
                    ore_entry = self.ore_data.get(ore_key, {})
                    if ore_entry:
                        vreq = int(ore_entry.get("blocks_to_break", 0))
                        vein = int(ore_entry.get("vein_size", 1))
                        junk = str(ore_entry.get("junk_block", "stone"))
                        ay = float(ore_entry.get("avg_yield", 1.0))
                    else:
                        vreq, vein, junk = self._search_params(ore_key)
                        ay = 1.0
                        if vreq == 0:
                            vreq, vein, junk = self._search_params(req_tier)
                    if vreq > 0:
                        ore_blocks = max(1, math.ceil(q / ay))
                        veins_for_search = max(1, math.ceil(ore_blocks / vein))
                        total_blocks += veins_for_search * vreq
                        total_blocks += ore_blocks
                        ore_block = self._source_block_for(task.name)
                        total += self._compute_tacq(from_tier, q, ore_block, junk, vreq, vein, ay)
                        continue
                total += self._tblock(block, speed) * q

        # Cascading tool wear: from_tier tools break and need replacement.
        from_copies = max(1, math.ceil(total_blocks / dur)) if dur != float("inf") else 1
        if from_copies > 1 and from_tier != "hand":
            prev_tier = self.TIER_ORDER[self.TIER_ORDER.index(from_tier) - 1]
            extra_cost = self._compute_costboot(prev_tier, from_tier, tool_class) * (from_copies - 1)
            total += extra_cost

        return total

    def _compute_junk_credit(
        self,
        tier: str,
        qty: int,
        nodes: dict[str, _Node],
    ) -> float:
        """Time saved because the search for *tier* ore produces useful junk blocks.

        If the junk block (e.g. cobbled_deepslate from diamond search) is needed
        by tasks in the graph, we credit the time that would have been spent
        mining those blocks separately.
        """
        vreq, vein_size, junk_block = self._search_params(tier)
        if vreq <= 0:
            return 0.0

        veins = max(1, math.ceil(qty / vein_size))
        junk_total = veins * vreq

        # Find how much of this junk is needed by tasks in the graph
        needed = 0
        junk_item = junk_block  # e.g. "cobbled_deepslate" or "stone"
        for node in nodes.values():
            base = node.name.split("_mvb_")[0]
            if base == junk_item and node.operation_type in ("mine", "gather"):
                needed += node.quantity
            # Also check smelt consumers: cobbled_deepslate → deepslate
            if junk_item == "cobbled_deepslate" and base == "deepslate" and node.operation_type == "smelt":
                needed += node.quantity

        credited = min(junk_total, needed)
        if credited <= 0:
            return 0.0

        # Time saved: what it would take to mine those blocks with the CURRENT best tool
        # Use the tier that's being evaluated (since we'd have that tier by then)
        speed = self._tool_speed(tier) if tier != "hand" else 1.0
        return self._tblock(junk_block, speed) * credited

    def _merge_tool_into_global(
        self, nodes: dict[str, _Node], tool_name: str
    ) -> str:
        """Generate the tool chain and merge it into the global graph.

        Returns the global tool node's ID so mine tasks can depend on it.
        """
        chain = self.generator.generate_single_item_tasks(tool_name, 1)
        id_map: dict[str, str] = {}  # chain ID → global ID
        is_new: set[str] = set()

        for task in chain:
            existing = next(
                (n for n in nodes.values() if n.name == task.name), None
            )
            if existing is not None:
                existing.quantity += task.quantity
                id_map[task.id] = existing.id
            else:
                new_id = task.id
                counter = 1
                while new_id in nodes:
                    counter += 1
                    new_id = f"{task.id}_{counter}"
                nodes[new_id] = _Node(
                    id=new_id,
                    name=task.name,
                    quantity=task.quantity,
                    dependencies=[],  # rewired below
                    operation_type=task.operation_type,
                )
                id_map[task.id] = new_id
                is_new.add(new_id)

        # Rewire dependencies only for newly created nodes.
        for task in chain:
            global_id = id_map[task.id]
            if global_id not in is_new:
                continue
            node = nodes[global_id]
            node.dependencies = [
                id_map[dep] for dep in task.dependencies if dep in id_map
            ]

        # Return the tool's global ID.
        tool_id = next(
            (id_map[t.id] for t in chain if t.name == tool_name and t.operation_type == "craft"),
            None,
        )
        if tool_id is None:
            raise GlobalMathOptimizerError(f"Tool {tool_name!r} not found in generated chain.")
        return tool_id

    @staticmethod
    def _would_create_tool_cycle(
        nodes: dict[str, _Node], task_id: str, tool_id: str
    ) -> bool:
        """Check if adding tool_id as a dep of task_id would create a cycle."""
        stack = [tool_id]
        seen: set[str] = set()
        while stack:
            nid = stack.pop()
            if nid == task_id:
                return True
            if nid in seen:
                continue
            seen.add(nid)
            node = nodes.get(nid)
            if node is not None:
                for dep in node.dependencies:
                    stack.append(dep)
        return False

    def _bootstrap_quantity(self, task_name: str, tool_name: str) -> int:
        """How many of *task_name* are needed in *tool_name*'s blueprint chain.

        Used for splitting a task into a minimal bootstrap portion (lower-tier
        tool or hand) and a bulk portion (best-tier tool).  Returns the quantity
        padded to the next recipe-yield multiple.
        """
        chain = self.generator.generate_single_item_tasks(tool_name, 1)
        total = 0
        for t in chain:
            if t.name == task_name:
                total += t.quantity
        if total <= 0:
            return 0
        # Pad to recipe yield.
        bp_task = self.generator._resolve_node(task_name)
        ypr = self.generator._recipe_yield_for(bp_task)
        if ypr <= 0:
            ypr = 1
        return int(math.ceil(total / ypr) * ypr)

    def _select_best_tier(
        self,
        node: _Node,
        harvest: dict[str, Any],
        nodes: dict[str, _Node],
    ) -> str | None:
        """Recursively evaluate tiers and return the best one (or None for hand).

        Compares each tier against the next, accounting for search cost, bootstrap
        cost, and junk credits.  Returns the optimal tier name.
        """
        tool_class = str(harvest.get("tool_class", "none"))
        qty = node.quantity
        ore_block = self._source_block_for(node.name)

        best_tier: str | None = None  # None = hand
        best_time = float("inf")

        # Baseline: hand (infinite if a tool is required to get drops).
        mat_tier_initial = str(harvest.get("min_tier", "wooden"))
        tool_required = mat_tier_initial not in ("wooden", "hand")
        if tool_required:
            best_time = float("inf")  # can't mine without a tool
        elif qty > 0:
            best_time = self._tblock(ore_block, 1.0) * qty
        else:
            best_time = 0.0

        for tier in self.TIER_ORDER:
            if tier == "wooden":
                tool_time = self._tblock(ore_block, self._tool_speed(tier)) * qty
                costboot = (
                    self._tblock("cobblestone", 1.0) * 3
                    + self._tblock("oak_log", 1.0) * 2
                )
                dur = self._tool_durability_from_data("wooden")
                copies = max(1, math.ceil(qty / dur))
                sped_up_time = tool_time + costboot * copies
                if sped_up_time < best_time:
                    best_tier = tier
                    best_time = sped_up_time
                continue

            # Search volume comes from the MATERIAL being mined.
            mat_tier = str(harvest.get("min_tier", "wooden"))
            surface_material = mat_tier in ("wooden", "hand")
            ay = 1.0
            if surface_material:
                vreq, vein_size, junk_block = 0, 1, "stone"
            else:
                ore_key = node.name
                if ore_key.startswith("deepslate_"):
                    ore_key = ore_key[len("deepslate_"):]
                if ore_key.endswith("_ore"):
                    ore_key = ore_key[:-len("_ore")]
                ore_entry = self.ore_data.get(ore_key, {})
                if ore_entry:
                    vein_size = int(ore_entry.get("vein_size", 1))
                    vreq = int(ore_entry.get("blocks_to_break", 0))
                    junk_block = str(ore_entry.get("junk_block", "stone"))
                    ay = float(ore_entry.get("avg_yield", 1.0))
                else:
                    vreq, vein_size, junk_block = self._search_params(ore_key)
                    if vreq == 0:
                        vreq, vein_size, junk_block = self._search_params(mat_tier)
            tacq = self._compute_tacq(tier, qty, ore_block, junk_block, vreq, vein_size, ay)

            # Bootstrap from the best tier found so far.
            effective_from = best_tier if best_tier is not None else "hand"
            costboot = self._compute_costboot(effective_from, tier, tool_class)

            # Junk credit only applies when the material itself has search cost.
            junk_credit = 0.0
            if not surface_material:
                junk_credit = self._compute_junk_credit(tier, qty, nodes)

            dur = self._tool_durability_from_data(tier)
            copies = max(1, math.ceil(qty / dur))
            # Progressive acquisition: copy 1 bootstrapped from lower tier;
            # copies 2+ use the already-acquired same-tier tool (faster).
            if copies > 1 and tier != "wooden":
                self_cost = self._compute_costboot(tier, tier, tool_class)
                total_time = tacq + costboot + self_cost * (copies - 1) - junk_credit
            else:
                total_time = tacq + costboot * copies - junk_credit

            if total_time < best_time:
                best_tier = tier
                best_time = total_time

        # Hand wins if no tier is better
        if best_tier is None:
            return None
        if best_tier == "wooden":
            # Check if stone is better than wooden for surface materials.
            stone_speed = self._tool_speed("stone")
            stone_time = self._tblock(ore_block, stone_speed) * qty
            stone_costboot = self._compute_costboot("wooden", "stone", tool_class)
            if stone_time + stone_costboot < best_time:
                best_tier = "stone"
        return best_tier

    def _wire_to_mvb_island(
        self,
        nodes: dict[str, _Node],
        tool_id: str,
        bulk_id: str,
    ) -> None:
        """Rewire a tool's recipe deps to use MVB island resources.

        When a tool cycles with a bulk task, redirect the tool's consumable
        ingredients to the primitive hand-gathered MVB island.  Workstations
        (crafting_table) stay global.  The island has no tool deps, breaking
        the cycle.
        """
        tool_node = nodes.get(tool_id)
        if tool_node is None or not self._mvb_island:
            return
        replacements: dict[str, str] = {}
        for dep_id in list(tool_node.dependencies):
            dep_node = nodes.get(dep_id)
            if dep_node is None:
                continue
            island_id = self._mvb_island.get(dep_node.name)
            if island_id is not None and island_id != dep_id:
                replacements[dep_id] = island_id
        if replacements:
            tool_node.dependencies = [
                replacements.get(d, d) for d in tool_node.dependencies
            ]

    def _step_1b_roi_and_mvb(self, nodes: dict[str, _Node]) -> None:
        """Discovery-weighted ROI: select optimal tool tier for every mine/gather task."""
        target_ids = [node.id for node in nodes.values() if node.operation_type in {"mine", "gather"}]
        for node_id in target_ids:
            if node_id not in nodes:
                continue
            node = nodes[node_id]
            # MVB island nodes are hand-gathered primitives — skip ROI.
            if "_mvb_island" in node.name:
                continue
            terminal = self._terminal_node_for_item(node.name, node.operation_type)
            harvest = terminal.get("harvest")
            if not isinstance(harvest, dict):
                continue
            hand_insta = bool(harvest.get("hand_insta_harvest_possible", False))
            if hand_insta:
                continue
            tool_class = str(harvest.get("tool_class", "none"))
            if tool_class == "none":
                continue

            # Determine current tool tier (if any)
            current_tier: str | None = None
            current_tool_id: str | None = None
            for dep_id in node.dependencies:
                if dep_id not in nodes:
                    continue
                dep_node = nodes[dep_id]
                if not self._is_tool(dep_node.name):
                    continue
                current_tool_id = dep_id
                base = dep_node.name.split("_mvb_")[0]
                for tier in self.TIER_ORDER:
                    if base.startswith(f"{tier}_"):
                        current_tier = tier
                        break
                break

            best_tier = self._select_best_tier(node, harvest, nodes)
            if best_tier is None:
                continue  # hand wins

            # Skip if current tool is already at or above the optimal tier
            if current_tier is not None:
                current_idx = self.TIER_ORDER.index(current_tier)
                best_idx = self.TIER_ORDER.index(best_tier)
                if current_idx >= best_idx:
                    continue
                # Only remove the old tool dep AFTER confirming the new one
                # is valid (no cycle).  Removal happens below.

            tool_name = f"{best_tier}_{tool_class}"

            # Stone/wooden tools: merge into global graph.
            # Iron/diamond tools: use MVB for isolated bootstrap.
            if best_tier in ("iron", "diamond"):
                root_mvb_id, source_usage = self._inject_mvb_chain(nodes, tool_name)
                if root_mvb_id not in node.dependencies:
                    node.dependencies.append(root_mvb_id)
                # Remove old lower-tier tool after successful wiring.
                if current_tool_id is not None:
                    node.dependencies = [
                        d for d in node.dependencies if d != current_tool_id
                    ]
            else:
                global_tool_id = self._merge_tool_into_global(nodes, tool_name)
                if global_tool_id not in node.dependencies:
                    if self._would_create_tool_cycle(nodes, node.id, global_tool_id):
                        # Wire the tool's ingredient deps to the MVB island
                        # instead of bulk nodes.  The island provides hand-
                        # gathered bootstrap materials that break the cycle.
                        self._wire_to_mvb_island(nodes, global_tool_id, node.id)
                    node.dependencies.append(global_tool_id)
                    if current_tool_id is not None:
                        node.dependencies = [
                            d for d in node.dependencies if d != current_tool_id
                        ]

            self._prune_non_positive(nodes)

    def _lookup_fuel_yield(self, fuel_item_name: str) -> float:
        if fuel_item_name == "oak_planks":
            return 1.5
        raise GlobalMathOptimizerError(f"Fuel yield metadata missing for {fuel_item_name!r}.")

    def _resolve_smelt_fuel_name(self, nodes: dict[str, _Node], smelt_nodes: list[_Node]) -> str:
        station_items = {"furnace", "blast_furnace", "smoker", "crafting_table"}
        # Collect all possible ingredient names across all smelt recipes.
        all_ingredients: set[str] = set()
        for smelt_node in smelt_nodes:
            recipe = self._blueprint_recipe_node(smelt_node.name.split("_mvb_")[0], "smelt")
            ingredients = recipe.get("ingredients")
            if not isinstance(ingredients, dict):
                raise GlobalMathOptimizerError(f"Smelt recipe for {smelt_node.name!r} missing ingredients map.")
            all_ingredients.update(str(name) for name in ingredients.keys())

        fuel_candidates: set[str] = set()
        for smelt_node in smelt_nodes:
            for dep_id in smelt_node.dependencies:
                dep_node = nodes.get(dep_id)
                if dep_node is None:
                    raise GlobalMathOptimizerError(f"Smelt task {smelt_node.id!r} has dangling dependency {dep_id!r}.")
                dep_base = dep_node.name.split("_mvb_")[0]
                if dep_base in all_ingredients:
                    continue
                if dep_base in station_items:
                    continue
                fuel_candidates.add(dep_base)
        if not fuel_candidates:
            raise GlobalMathOptimizerError("Unable to resolve designated smelt fuel dependency.")
        if len(fuel_candidates) > 1:
            raise GlobalMathOptimizerError(f"Ambiguous smelt fuel dependency candidates: {sorted(fuel_candidates)!r}.")
        return next(iter(fuel_candidates))

    def _step_1c_furnace_deltas(self, nodes: dict[str, _Node]) -> None:
        """Adjust furnace count and propagate ingredient deltas.

        Runs before tool recalculation so pickaxe quantities account for
        the cobblestone needed to craft the furnaces.
        """
        smelt_nodes = [node for node in nodes.values() if node.operation_type == "smelt"]
        total_smelt = sum(node.quantity for node in smelt_nodes)
        if total_smelt <= 64:
            return
        furnace_node = self._single_node_by_name(nodes, "furnace")
        old_qty = furnace_node.quantity
        k = max(1, round(math.sqrt((total_smelt * 10.0) / 30.0)))
        furnace_node.quantity = k
        delta = k - old_qty

        if delta != 0:
            recipe_node = self._blueprint_recipe_node("furnace", "craft")
            ingredients = recipe_node.get("ingredients")
            if not isinstance(ingredients, dict):
                raise GlobalMathOptimizerError("Furnace blueprint missing ingredient map.")
            for ing_name, ing_qty in ingredients.items():
                self._recursive_apply_delta(nodes, str(ing_name), int(ing_qty) * delta)

        self._prune_non_positive(nodes)

    def _step_1d_fuel_deltas(self, nodes: dict[str, _Node]) -> None:
        """Recalculate fuel quantity using per-chunk math (matching Phase 4B).

        Runs after tool recalculation so non-fuel plank demand is stable.
        Computes both fuel and non-fuel plank demand and sets the total.
        """
        smelt_nodes = [node for node in nodes.values() if node.operation_type == "smelt"]
        total_smelt = sum(node.quantity for node in smelt_nodes)
        if total_smelt <= 64:
            return

        fuel_name = self._resolve_smelt_fuel_name(nodes, smelt_nodes)
        fuel_node = self._single_node_by_name(nodes, fuel_name)
        fuel_yield = self._lookup_fuel_yield(fuel_name)

        # Per-chunk fuel math — matches Phase 4B's ceil(chunk.quantity / 1.5) logic.
        fuel_needed = 0
        for smelt_node in smelt_nodes:
            remaining = smelt_node.quantity
            while remaining > 64:
                fuel_needed += math.ceil(64 / fuel_yield)
                remaining -= 64
            if remaining > 0:
                fuel_needed += math.ceil(remaining / fuel_yield)

        # Non-fuel plank demand from non-smelt consumers.
        non_fuel_needed = 0
        for node in nodes.values():
            if node.operation_type == "smelt":
                continue
            dep_names = {nodes[dep].name for dep in node.dependencies if dep in nodes}
            if fuel_name not in dep_names:
                continue
            base_name = node.name.split("_mvb_")[0]
            recipe = self._blueprint_recipe_node(base_name, node.operation_type)
            ingredients = recipe.get("ingredients", {})
            ing_count = int(ingredients.get(fuel_name, 0))
            if ing_count == 0:
                continue
            blueprint_task = self.generator._resolve_node(base_name)
            yield_per_run = self.generator._recipe_yield_for(blueprint_task)
            runs = math.ceil(node.quantity / yield_per_run)
            non_fuel_needed += runs * ing_count

        new_total = fuel_needed + non_fuel_needed
        old_total = fuel_node.quantity
        delta = new_total - old_total
        if delta != 0:
            self._recursive_apply_delta(nodes, fuel_name, delta)

        self._prune_non_positive(nodes)

    def _step_1a_tool_recalculation(self, nodes: dict[str, _Node]) -> None:
        tool_ids = [node.id for node in nodes.values() if self._is_tool(node.name)]
        for tool_id in tool_ids:
            if tool_id not in nodes:
                continue
            tool_node = nodes[tool_id]
            durability = self._tool_durability(tool_node.name.split("_mvb_")[0])
            workload = 0
            for consumer in list(nodes.values()):
                if tool_id not in consumer.dependencies:
                    continue
                workload += consumer.quantity
            new_qty = math.ceil(workload / durability) if workload > 0 else 0
            delta = new_qty - tool_node.quantity
            tool_node.quantity = new_qty
            if delta != 0:
                base_tool_name = tool_node.name.split("_mvb_")[0]
                recipe_node = self._blueprint_recipe_node(base_tool_name, "craft")
                ingredients = recipe_node.get("ingredients")
                if not isinstance(ingredients, dict):
                    raise GlobalMathOptimizerError(f"Tool blueprint missing ingredients for {base_tool_name!r}.")
                mvb_suffix = ""
                if "_mvb_" in tool_node.name:
                    mvb_suffix = "_mvb_" + tool_node.name.split("_mvb_", 1)[1]
                for ing_name, ing_qty in ingredients.items():
                    if mvb_suffix:
                        target_name = f"{ing_name}{mvb_suffix}"
                        self._recursive_apply_delta(nodes, target_name, int(ing_qty) * delta)
                    else:
                        # If the tool depends on a bootstrap variant, propagate
                        # to that bootstrap node directly.
                        bs_dep = next(
                            (d for d in tool_node.dependencies
                             if "_bootstrap" in d),
                            None,
                        )
                        bs_node = nodes.get(bs_dep) if bs_dep else None
                        if bs_node is not None and bs_node.name == ing_name:
                            bs_node.quantity += int(ing_qty) * delta
                        else:
                            self._recursive_apply_delta(nodes, ing_name, int(ing_qty) * delta)
            self._prune_non_positive(nodes)

    def _step_1a2_ingredient_recalc(self, nodes: dict[str, _Node]) -> None:
        """Recalculate non-fuel ingredient quantities from consumer demand.

        Two-pass approach: compute target quantities for all craft nodes first,
        then apply them in one shot.  This avoids the cascading-prune problem
        that happens when deltas are propagated incrementally.
        """
        targets: dict[str, int] = {}

        for node in list(nodes.values()):
            if node.operation_type != "craft":
                continue
            if "_mvb_" in node.name:
                continue
            if self._is_tool(node.name):
                continue  # tool quantities are managed by step_1a

            base_name = node.name.split("_mvb_")[0]
            recipe = self._blueprint_recipe_node(base_name, "craft")
            blueprint_task = self.generator._resolve_node(base_name)
            yield_per_run = self.generator._recipe_yield_for(blueprint_task)

            total_demand = 0
            for consumer in list(nodes.values()):
                if node.id not in consumer.dependencies:
                    continue
                consumer_base = consumer.name.split("_mvb_")[0]
                consumer_recipe = self._terminal_node_for_item(consumer_base, consumer.operation_type)
                consumer_ingredients = consumer_recipe.get("ingredients", {})
                ing_count = int(consumer_ingredients.get(base_name, 0))
                if ing_count <= 0:
                    continue
                consumer_yield = 1
                if consumer.operation_type in {"craft", "smelt"}:
                    consumer_bp = self.generator._resolve_node(consumer_base)
                    consumer_yield = self.generator._recipe_yield_for(consumer_bp)
                runs = math.ceil(consumer.quantity / consumer_yield)
                total_demand += runs * ing_count

            if total_demand > 0:
                new_qty = int(math.ceil(total_demand / yield_per_run) * yield_per_run)
                targets[node.id] = new_qty

        for node_id, new_qty in targets.items():
            node = nodes.get(node_id)
            if node is None:
                continue
            # Never reduce below what consumers actually need, but also
            # never reduce below the current quantity (MVBs may have added
            # demand that ingredient recalc doesn't see).
            if new_qty > node.quantity:
                node.quantity = new_qty

        self._prune_non_positive(nodes)

    def _create_mvb_island(self, nodes: dict[str, _Node]) -> dict[str, str]:
        """Create a primitive hand-gathered MVB island for bootstrapping.

        The island is strictly separated from bulk nodes.  ROI ignores these
        nodes (hand-gathered, no tool class to upgrade).  Returns a name→id
        map for wiring bulk tools to bootstrap resources.

        Island: oak_log(3) → planks → (stick, crafting_table) → wooden_pickaxe
                                                                    ↓
                                                        cobblestone(6)
        """
        ids: dict[str, str] = {}

        def _add(task_id, name, qty, deps, op):
            nid = task_id
            c = 1
            while nid in nodes:
                c += 1
                nid = f"{task_id}_{c}"
            nodes[nid] = _Node(id=nid, name=name, quantity=qty,
                               dependencies=deps, operation_type=op)
            return nid

        # 15 oak_log → 60 planks → 30 sticks (covers all stone tool copies).
        ids["oak_log"] = _add("GATHER:oak_log_mvb_island", "oak_log_mvb_island",
                              15, [], "gather")
        ids["oak_planks"] = _add("CRAFT:oak_planks_mvb_island", "oak_planks_mvb_island",
                                 60, [ids["oak_log"]], "craft")
        ids["stick"] = _add("CRAFT:stick_mvb_island", "stick_mvb_island",
                            32, [ids["oak_planks"]], "craft")
        ids["crafting_table"] = _add("CRAFT:crafting_table_mvb_island", "crafting_table_mvb_island",
                                     1, [ids["oak_planks"]], "craft")
        ids["wooden_pickaxe"] = _add("CRAFT:wooden_pickaxe_mvb_island", "wooden_pickaxe_mvb_island",
                                     1, [ids["oak_planks"], ids["stick"], ids["crafting_table"]], "craft")
        # Island provides enough for all stone tool copies since the DAG
        # can't express \"copy 1 from island, copy 2+ from bulk\" without
        # creating the cycle again.  The wooden pick (dur 59) can handle this.
        # 3 cobblestone per stone pick × 11 copies + 3 per stone axe × 4 = 45.
        ids["cobblestone"] = _add("MINE:cobblestone_mvb_island", "cobblestone_mvb_island",
                                  45, [ids["wooden_pickaxe"]], "mine")
        return ids

    def optimize_tasks(self, phase3_tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        nodes = self._parse_graph(phase3_tasks)

        # Create primitive MVB island for bootstrapping before ROI runs.
        self._mvb_island = self._create_mvb_island(nodes) if nodes else {}

        self._step_1b_roi_and_mvb(nodes)         # Inject MVB tool chains where ROI justifies
        self._step_1c_furnace_deltas(nodes)      # Adjust furnace count
        self._step_1a_tool_recalculation(nodes)   # Recalculate tool quantities
        self._step_1a2_ingredient_recalc(nodes)   # Recalculate global ingredient quantities
        self._step_1d_fuel_deltas(nodes)         # Per-chunk fuel math (may increase oak_log workload)
        self._step_1a_tool_recalculation(nodes)   # Recalculate MVB tool quantities for new workloads
        self._prune_non_positive(nodes)
        return [node.as_dict() for node in sorted(nodes.values(), key=lambda node: node.id)]

    def optimize_from_file(self) -> list[dict[str, Any]]:
        if not self.phase3_input_path.exists():
            raise GlobalMathOptimizerError(f"Missing Phase 3 input file: {self.phase3_input_path}")
        payload = json.loads(self.phase3_input_path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise GlobalMathOptimizerError("Phase 3 input must be a JSON array.")
        optimized = self.optimize_tasks(payload)
        self.phase4a_output_path.write_text(json.dumps(optimized, indent=2) + "\n", encoding="utf-8")
        return optimized


def optimize_phase3_global_tasks(
    phase3_tasks: list[dict[str, Any]],
    blueprints_path: Path = BLUEPRINTS_PATH,
) -> list[dict[str, Any]]:
    optimizer = GlobalMathOptimizer(blueprints_path=blueprints_path)
    return optimizer.optimize_tasks(phase3_tasks)

