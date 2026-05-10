"""Phase 6 cache simulator — inventory slot tracking, tool durability, stashing."""

from __future__ import annotations

import json
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from planner.item_task_generator import ItemTaskGenerator

ROOT = Path(__file__).resolve().parents[1]
PHASE5_PATH = ROOT / "tests" / "input_materials_test.phase5.json"
CONFIG_PATH = ROOT / "config.json"
TOOLS_PATH = ROOT / "constants" / "tools.json"
BLUEPRINTS_PATH = ROOT / "constants" / "blueprints.json"
OUT_DIR = ROOT / "debug_utitlities"

TOOL_SUFFIXES = ("_pickaxe", "_axe", "_shovel", "_hoe", "_sword")
UNSTACKABLE_ITEMS = {"bow", "crossbow", "trident", "shield"}
ARMOR_SUFFIXES = ("_helmet", "_chestplate", "_leggings", "_boots")
STACK_SIZE = 64
TOTAL_SLOTS = 36

TIER_DURABILITY = {
    "wooden": 59, "stone": 131, "iron": 250, "diamond": 1561,
    "golden": 32, "netherite": 2031,
}


class SimulationError(RuntimeError):
    """Raised when a physical Minecraft constraint is violated."""


@dataclass
class SimulationResult:
    success: bool
    error: str | None
    inventory_snapshots: list[dict[str, Any]] = field(default_factory=list)
    stashed_chests: list[str] = field(default_factory=list)


def _is_tool(name: str) -> bool:
    base = name.split("_mvb_")[0]
    return base.endswith(TOOL_SUFFIXES)


def _is_unstackable(name: str) -> bool:
    base = name.split("_mvb_")[0]
    return (base.endswith(TOOL_SUFFIXES)
            or base.endswith(ARMOR_SUFFIXES)
            or name in UNSTACKABLE_ITEMS)


def _max_stack(name: str) -> int:
    return 1 if _is_unstackable(name) else STACK_SIZE


def _tool_durability(name: str) -> int:
    base = name.split("_mvb_")[0]
    for tier in TIER_DURABILITY:
        if base.startswith(f"{tier}_"):
            return TIER_DURABILITY[tier]
    return 59  # default wooden


class Inventory:
    """36-slot inventory with stacking rules."""

    def __init__(self):
        self.slots: list[dict | None] = [None] * TOTAL_SLOTS
        self._tool_dur: dict[int, int] = {}  # slot_idx → remaining durability

    @property
    def used_slots(self) -> int:
        return sum(1 for s in self.slots if s is not None)

    def _find_stackable(self, item: str) -> int | None:
        max_s = _max_stack(item)
        if max_s == 1:
            return None
        for i, s in enumerate(self.slots):
            if s is not None and s["item"] == item and s["qty"] < max_s:
                return i
        return None

    def _find_empty(self) -> int:
        for i, s in enumerate(self.slots):
            if s is None:
                return i
        raise SimulationError("Inventory full — no empty slots.")

    def add(self, item: str, qty: int, durability: int | None = None) -> None:
        if qty <= 0:
            return
        max_s = _max_stack(item)

        while qty > 0:
            if max_s > 1:
                idx = self._find_stackable(item)
                if idx is not None:
                    space = max_s - self.slots[idx]["qty"]
                    add = min(space, qty)
                    self.slots[idx]["qty"] += add
                    qty -= add
                    continue

            idx = self._find_empty()
            add = min(max_s, qty)
            self.slots[idx] = {"item": item, "qty": add}
            if durability is not None and durability > 0:
                self._tool_dur[idx] = durability
            qty -= add

    def remove(self, item: str, qty: int) -> None:
        # Check total first — atomic: don't remove anything unless we have enough.
        total = sum(s["qty"] for s in self.slots if s is not None and s["item"] == item)
        if total < qty:
            raise SimulationError(
                f"Missing {item}: need {qty}, insufficient in inventory."
            )
        remaining = qty
        for i, s in enumerate(self.slots):
            if s is not None and s["item"] == item:
                take = min(s["qty"], remaining)
                s["qty"] -= take
                remaining -= take
                self._tool_dur.pop(i, None)
                if s["qty"] <= 0:
                    self.slots[i] = None
                if remaining <= 0:
                    return

    def has(self, item: str, qty: int) -> bool:
        total = sum(s["qty"] for s in self.slots if s is not None and s["item"] == item)
        return total >= qty

    def tool_durability(self, item: str) -> int | None:
        for i, s in enumerate(self.slots):
            if s is not None and s["item"] == item:
                return self._tool_dur.get(i)
        return None

    def consume_tool_dur(self, item: str, amount: int) -> None:
        """Deduct durability from the first matching tool.  Removes at 0."""
        for i, s in enumerate(self.slots):
            if s is not None and s["item"] == item:
                dur = self._tool_dur.get(i, 0)
                if dur <= 0:
                    continue
                dur -= amount
                self._tool_dur[i] = dur
                if dur <= 0:
                    s["qty"] -= 1
                    if s["qty"] <= 0:
                        self.slots[i] = None
                    self._tool_dur.pop(i, None)
                return
        raise SimulationError(f"No {item!r} with durability in inventory.")

    def slots_snapshot(self) -> list[dict | None]:
        result: list[dict | None] = []
        for i, s in enumerate(self.slots):
            if s is None:
                result.append(None)
            else:
                snap = dict(s)
                if i in self._tool_dur:
                    snap["durability"] = self._tool_dur[i]
                result.append(snap)
        return result

    def clear_slot(self, idx: int) -> dict:
        s = self.slots[idx]
        if s is None:
            raise SimulationError(f"Slot {idx} is already empty.")
        dur = self._tool_dur.pop(idx, None)
        self.slots[idx] = None
        result = dict(s)
        if dur is not None:
            result["durability"] = dur
        return result

    def slot_item(self, idx: int) -> str | None:
        s = self.slots[idx]
        return s["item"] if s else None


class CacheSimulator:
    """Phase 6: inventory simulation with stashing and tool durability."""

    def __init__(self, phase5_path: Path = PHASE5_PATH):
        self.phase5_path = phase5_path
        self.stash_threshold = self._load_threshold()
        self.tool_data = self._load_tools()
        self.blueprints = self._load_blueprints()
        self._generator = ItemTaskGenerator()
        self._chest_counter = 0
        self._chests: dict[str, list[dict]] = {}
        self._available_chest_ids: list[str] = []

    @staticmethod
    def _load_threshold() -> int:
        if CONFIG_PATH.exists():
            cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            return int(cfg.get("stash_threshold_slots", 28))
        return 28

    @staticmethod
    def _load_tools() -> dict[str, Any]:
        return json.loads(TOOLS_PATH.read_text(encoding="utf-8"))

    @staticmethod
    def _load_blueprints() -> dict[str, Any]:
        data = json.loads(BLUEPRINTS_PATH.read_text(encoding="utf-8"))
        return data.get("blueprints", data)

    def _find_tool_requirement(self, task: dict) -> str | None:
        """Return the tool item name this mine/gather task requires, or None."""
        if task["operation_type"] not in ("mine", "gather"):
            return None
        deps = task.get("dependencies", [])
        for d in deps:
            # Extract the tool name from the chunk dependency ID.
            # e.g., CRAFT:stone_pickaxe_chunk_1 → stone_pickaxe
            dep_name = d.split(":")[-1] if ":" in d else d
            dep_name = dep_name.rsplit("_chunk_", 1)[0]
            if _is_tool(dep_name):
                return dep_name
        return None

    def _next_use_map(self, tasks: list[dict], start_idx: int) -> dict[str, int]:
        """For each item in inventory, find the next task index that needs it."""
        usage: dict[str, int] = {}
        for i in range(start_idx, len(tasks)):
            t = tasks[i]
            # Check recipe ingredients
            bp_entries = self.blueprints.get(t["name"], [])
            for bp in bp_entries:
                ings = bp.get("ingredients", {})
                for ing_name in ings:
                    usage.setdefault(ing_name, i)
            # Check fuel
            if t["operation_type"] == "smelt":
                usage.setdefault("oak_planks", i)
            # Check tool deps
            tool = self._find_tool_requirement(t)
            if tool:
                usage.setdefault(tool, i)
        return usage

    def _toss(self, inv: Inventory, tasks: list[dict], task_idx: int) -> list[dict]:
        """Toss items with zero future demand across all remaining tasks.

        Returns list of toss snapshot dicts, each with ``toss`` marker.
        """
        toss_snapshots: list[dict] = []
        for i, s in enumerate(inv.slots):
            if s is None:
                continue
            item = s["item"]
            if _is_tool(item):
                continue
            needed = False
            for j in range(task_idx, len(tasks)):
                if self._task_needs_item(tasks[j], item):
                    needed = True
                    break
            if not needed:
                qty = s["qty"]
                inv.clear_slot(i)
                toss_snapshots.append({
                    "task_index": task_idx,
                    "task_id": f"TOSS:{item}",
                    "slots": inv.slots_snapshot(),
                    "toss": True,
                    "item": item,
                    "quantity": qty,
                })
        return toss_snapshots

    def _stash(self, inv: Inventory, tasks: list[dict], task_idx: int) -> str | None:
        """Clear 8+ slots by stashing items with farthest next use.

        Items with zero future demand are handled by ``_toss()`` first.
        Only items with actual future demand reach this method.
        Higher priority = needed later → stashed first.
        Returns chest_id, or None if nothing was stashed.
        """
        # Build per-slot next-use priority.
        slot_priority: list[tuple[int, int, str]] = []  # (priority, slot_idx, item)
        for i, s in enumerate(inv.slots):
            if s is None:
                continue
            item = s["item"]
            if _is_tool(item):
                continue  # never stash tools — durability is slot-specific
            pri = 2**60  # never needed = lowest priority, stash first
            for j in range(task_idx, len(tasks)):
                t = tasks[j]
                if self._task_needs_item(t, item):
                    pri = j
                    break
            slot_priority.append((pri, i, item))

        # Sort by priority descending: farthest use (or never needed) first.
        slot_priority.sort(key=lambda x: -x[0])

        # Never stash items needed imminently.  Reduce the protection window
        # iteratively until 8 slots can be cleared, down to a minimum of 5.
        stashed: list[tuple[int, int, str]] = []
        for window in (50, 45, 40, 35, 30, 25, 20, 15, 10, 5):
            min_window = task_idx + window
            candidates = [(p, i, it) for p, i, it in slot_priority
                          if p != 2**60 and p > min_window]
            to_take = min(len(candidates), 8)
            if to_take >= 8 or window == 5:
                stashed = candidates[:to_take]
                break

        if not stashed:
            raise SimulationError(
                f"Stash failed at task index {task_idx}: {inv.used_slots} slots "
                f"occupied but no items can be evicted (all needed within 5 tasks)."
            )

        if self._available_chest_ids:
            chest_id = self._available_chest_ids.pop(0)
        else:
            self._chest_counter += 1
            chest_id = f"chest_{self._chest_counter}"

        contents: list[dict] = []
        for _, slot_idx, _ in stashed:
            slot = inv.clear_slot(slot_idx)
            contents.append(slot)
        self._chests[chest_id] = contents
        return chest_id

    def _task_demand_for(self, task: dict, item: str) -> int:
        """How many of *item* does *task* consume?"""
        op = task["operation_type"]
        name = task["name"]
        qty = task["quantity"]
        if op == "smelt" and item == "oak_planks":
            return math.ceil(qty / 1.5)
        for bp in self.blueprints.get(name, []):
            if bp.get("item") == name and bp.get("operation") == op:
                count = bp.get("ingredients", {}).get(item, 0)
                if count > 0:
                    ry = 1
                    if op == "craft":
                        ry = self._recipe_yield(name)
                    runs = math.ceil(qty / ry)
                    return runs * count
        return 0

    def _task_needs_item(self, task: dict, item: str) -> bool:
        """Check if *task* consumes *item* as recipe ingredient, fuel, or tool."""
        op = task["operation_type"]
        name = task["name"]
        if op == "smelt" and item == "oak_planks":
            return True
        # Match both exact name and MVB island variants.
        base_item = item
        if base_item.endswith("_mvb_island"):
            base_item = base_item[:-len("_mvb_island")]
        for bp in self.blueprints.get(name, []):
            if bp.get("item") == name and bp.get("operation") == op:
                ings = bp.get("ingredients", {})
                if item in ings or base_item in ings:
                    return True
        tool = self._find_tool_requirement(task)
        return tool == item or tool == base_item

    def _retrieve(self, inv: Inventory, chest_id: str) -> None:
        contents = self._chests.pop(chest_id, [])
        for slot in contents:
            dur = slot.pop("durability", None)
            inv.add(slot["item"], slot["qty"], durability=dur)
        self._available_chest_ids.append(chest_id)

    def _retrieve_item(self, inv: Inventory, item: str) -> bool:
        """Search all chests for *item* and restore all instances to inventory."""
        any_found = False
        for chest_id, contents in list(self._chests.items()):
            found = False
            for slot in list(contents):
                if slot["item"] == item:
                    dur = slot.pop("durability", None)
                    inv.add(slot["item"], slot["qty"], durability=dur)
                    contents.remove(slot)
                    found = True
            if found:
                any_found = True
                if contents:
                    self._chests[chest_id] = contents
                else:
                    del self._chests[chest_id]
                    self._available_chest_ids.append(chest_id)
        return any_found

    def _consume(self, inv: Inventory, item: str, qty: int,
                 tasks: list[dict], task_idx: int,
                 snapshots: list[dict]) -> None:
        """Remove *qty* of *item* from inventory, retrieving from chests if needed."""
        try:
            inv.remove(item, qty)
            return
        except SimulationError:
            pass
        # Try retrieval: exact name first, then base name (strip _mvb_island).
        candidates = [item]
        base = item
        if base.endswith("_mvb_island"):
            base = base[:-len("_mvb_island")]
            candidates.append(base)
        for search in candidates:
            if self._retrieve_item(inv, search):
                snapshots.append({
                    "task_index": task_idx - 1,
                    "task_id": f"GO_TO_CHEST:{search}",
                    "slots": inv.slots_snapshot(),
                    "retrieve": True,
                    "item": search,
                })
                try:
                    inv.remove(item, qty)
                    return
                except SimulationError:
                    continue
        raise SimulationError(f"Missing {item}: need {qty}, not in inventory or chests.")

    @staticmethod
    def _dep_item_name(dep_id: str) -> str:
        """Extract the bare item name from a chunk dependency ID.

        Examples:
          CRAFT:stone_pickaxe_chunk_1 → stone_pickaxe
          MINE:copper_ore_chunk_1_shard_CRAFT:stone_pickaxe_chunk_1 → copper_ore
        """
        # Strip shard suffix first (it may contain colons from the producer ID).
        if "_shard_" in dep_id:
            dep_id = dep_id.split("_shard_")[0]
        name = dep_id.split(":")[-1] if ":" in dep_id else dep_id
        if "_chunk_" in name:
            name = name.rsplit("_chunk_", 1)[0]
        return name

    @staticmethod
    def _dep_base_name(dep_id: str) -> str:
        """Get the blueprint ingredient name (strip MVB island suffix)."""
        raw = CacheSimulator._dep_item_name(dep_id)
        if raw.endswith("_mvb_island"):
            raw = raw[:-len("_mvb_island")]
        return raw

    def simulate(self) -> SimulationResult:
        with open(self.phase5_path, encoding="utf-8") as f:
            tasks = json.load(f)

        self._chest_counter = 0
        self._chests = {}
        self._available_chest_ids = []

        inv = Inventory()
        snapshots: list[dict[str, Any]] = []
        stash_tasks: list[str] = []

        for idx, task in enumerate(tasks):
            op = task["operation_type"]

            # --- Toss + Stash check (before consuming) ---
            if inv.used_slots >= self.stash_threshold:
                # Step 1: toss items with zero future demand (incl. current task)
                toss_snaps = self._toss(inv, tasks, idx)
                snapshots.extend(toss_snaps)
                # Step 2: stash items needed later but not imminently
                if inv.used_slots >= self.stash_threshold:
                    chest_id = self._stash(inv, tasks, idx + 1)
                    if chest_id:
                        stash_tasks.append(chest_id)
                        snapshots.append({
                            "task_index": idx,
                            "task_id": f"STASH:{chest_id}",
                            "slots": inv.slots_snapshot(),
                            "stash": True,
                            "chest": chest_id,
                        })

            # --- Consume inputs ---
            # Ingredients are consumed once per task (blueprint quantity),
            # NOT once per dependency (the deps are producer chunks, not
            # independent consumption events).
            consumed: set[str] = set()
            for dep in task.get("dependencies", []):
                dep_name = self._dep_item_name(dep)

                if op in ("craft",):
                    bp_entry = next(
                        (e for e in self.blueprints.get(task["name"], [])
                         if e.get("item") == task["name"] and e.get("operation") == op),
                        None,
                    )
                    if bp_entry is None:
                        continue
                    base = self._dep_base_name(dep)
                    if base in consumed:
                        continue
                    need = bp_entry.get("ingredients", {}).get(base, 0)
                    if need > 0:
                        consumed.add(base)
                        ry = self._recipe_yield(task["name"])
                        runs = math.ceil(task["quantity"] / ry)
                        total_need = runs * need
                        self._consume(inv, dep_name, total_need, tasks, idx + 1, snapshots)

                elif op == "smelt":
                    if dep_name in ("oak_planks",):
                        if "oak_planks" in consumed:
                            continue
                        consumed.add("oak_planks")
                        fuel = math.ceil(task["quantity"] / 1.5)
                        self._consume(inv, dep_name, fuel, tasks, idx + 1, snapshots)
                    else:
                        bp_entry = next(
                            (e for e in self.blueprints.get(task["name"], [])
                             if e.get("item") == task["name"] and e.get("operation") == "smelt"),
                            None,
                        )
                        if bp_entry is None:
                            continue
                        base = self._dep_base_name(dep)
                        if base in consumed:
                            continue
                        need = bp_entry.get("ingredients", {}).get(base, 0)
                        if need > 0:
                            consumed.add(base)
                            self._consume(inv, dep_name, task["quantity"] * need, tasks, idx + 1, snapshots)

                elif op in ("mine", "gather", "sword"):
                    if _is_tool(dep_name):
                        needed_dur = task["quantity"]
                        dur = inv.tool_durability(dep_name)
                        if dur is None or dur <= 0:
                            raise SimulationError(
                                f"Task {task['id']} requires {dep_name!r} "
                                f"but none with durability in inventory."
                            )
                        inv.consume_tool_dur(dep_name, needed_dur)

            # --- Produce output ---
            name = task["name"]
            qty = task["quantity"]
            if op == "place":
                inv.remove(name, qty)
                for _ in range(qty):
                    self._chest_counter += 1
                    self._available_chest_ids.append(f"chest_{self._chest_counter}")
            elif _is_tool(name):
                dur = _tool_durability(name)
                inv.add(name, qty, durability=dur)
            else:
                inv.add(name, qty)

            # --- Record snapshot ---
            snapshots.append({
                "task_index": idx,
                "task_id": task["id"],
                "slots": inv.slots_snapshot(),
            })

        return SimulationResult(
            success=True,
            error=None,
            inventory_snapshots=snapshots,
            stashed_chests=stash_tasks,
        )

    def _recipe_yield(self, item_name: str) -> int:
        """Look up recipe yield via ItemTaskGenerator."""
        try:
            node = self._generator._resolve_node(item_name)
            return self._generator._recipe_yield_for(node)
        except Exception:
            return 1

    def _find_craft_recipe(self, item_name: str) -> dict | None:
        """Return the *craft* blueprint entry for *item_name*, or None."""
        for bp in self.blueprints.get(item_name, []):
            if bp.get("operation") == "craft":
                return bp
        return None

    def _propagate_ingredient_delta(self, tasks: list[dict], item_name: str,
                                    delta_qty: int, visited: set[str]) -> None:
        """Add *delta_qty* of *item_name* to the last matching task, then recurse
        into its recipe ingredients.  Modifies *tasks* in place."""
        if delta_qty <= 0 or item_name in visited:
            return
        visited.add(item_name)

        bp = self._find_craft_recipe(item_name)
        if bp is None:
            # Base / gathered item — add to the last mine or gather task.
            for t in reversed(tasks):
                if (t["name"] == item_name
                        and t["operation_type"] in ("mine", "gather")
                        and "mvb" not in t.get("id", "")
                        and "island" not in t.get("id", "")):
                    t["quantity"] += delta_qty
                    return
            raise SimulationError(
                f"Cannot propagate {delta_qty} {item_name!r}: "
                f"no upstream mine/gather task found."
            )

        recipe_yield = self._recipe_yield(item_name)
        ingredients = bp.get("ingredients", {})

        runs = math.ceil(delta_qty / recipe_yield)
        craft_add = runs * recipe_yield

        for t in reversed(tasks):
            if (t["name"] == item_name
                    and t["operation_type"] == "craft"
                    and "mvb" not in t.get("id", "")
                    and "island" not in t.get("id", "")):
                t["quantity"] += craft_add
                break
        else:
            raise SimulationError(
                f"Cannot propagate {delta_qty} {item_name!r}: "
                f"no craft task found."
            )

        for ing_name, ing_count in ingredients.items():
            self._propagate_ingredient_delta(
                tasks, ing_name, runs * ing_count, visited.copy())

    def _ensure_tool_capacity(self, tasks: list[dict]) -> None:
        """Detect over-consumed tool chunks after chest-overhead log bump and
        propagate additional tool copies plus their ingredient deltas upstream.

        Raises SimulationError if propagation hits an unresolvable gap.
        """
        # Group mine/gather tasks by their tool dependency chunk id.
        tool_load: dict[str, int] = {}       # dep_id → total workload
        tool_name_of: dict[str, str] = {}    # dep_id → tool base name
        for t in tasks:
            if t["operation_type"] not in ("mine", "gather"):
                continue
            for d in t.get("dependencies", []):
                dep_name = self._dep_item_name(d)
                if _is_tool(dep_name):
                    tool_load[d] = tool_load.get(d, 0) + t["quantity"]
                    tool_name_of[d] = dep_name

        extra: dict[str, int] = {}  # tool_base_name → extra copies needed
        for dep_id, workload in tool_load.items():
            tool_name = tool_name_of[dep_id]
            dur = _tool_durability(tool_name)
            needed = math.ceil(workload / dur)
            if needed > 1:
                extra[tool_name] = extra.get(tool_name, 0) + (needed - 1)

        for tool_name, copies in extra.items():
            for _ in range(copies):
                self._propagate_ingredient_delta(
                    tasks, tool_name, 1, visited=set())

    def _apply_chest_overhead(self, tasks: list[dict], chest_count: int) -> list[dict]:
        """Add plank and log overhead for *chest_count* chests (modifies tasks in place).

        Overhead is routed to the *last* non-MVB tasks so the axe with remaining
        durability is used.  Each chest = 8 planks; planks yield 4 per log.

        After adding logs, verifies axe durability capacity and propagates
        additional tool copies + upstream ingredients if needed.
        """
        if chest_count <= 0:
            return tasks

        chest_planks = chest_count * 8
        chest_logs = math.ceil(chest_planks / 4)

        # Find the last non-MVB CRAFT:oak_planks task.
        last_planks = None
        for t in tasks:
            if t["name"] == "oak_planks" and t["operation_type"] == "craft" \
                    and "mvb" not in t.get("id", "") and "island" not in t.get("id", ""):
                last_planks = t
        if last_planks is not None:
            last_planks["quantity"] += chest_planks

        # Find the last non-MVB MINE:oak_log task — it uses the axe with
        # remaining durability (stone_axe_chunk_4 has 128 spare).
        last_mine = None
        for t in tasks:
            if t["name"] == "oak_log" and t["operation_type"] == "mine" \
                    and "mvb" not in t.get("id", "") and "island" not in t.get("id", ""):
                last_mine = t
        if last_mine is not None:
            last_mine["quantity"] += chest_logs

        self._ensure_tool_capacity(tasks)
        return tasks

    def _ensure_chest_tasks(self, tasks: list[dict], total_chests: int) -> list[dict]:
        """Insert (or update) CRAFT:chest and PLACE_CHEST tasks early in the queue."""
        craft_id = "CRAFT:chest_batch"
        place_id = "PLACE_CHEST:batch"

        existing_craft = next((t for t in tasks if t["id"] == craft_id), None)
        existing_place = next((t for t in tasks if t["id"] == place_id), None)

        if existing_craft:
            existing_craft["quantity"] = total_chests
        else:
            # Insert after the last non-MVB CRAFT:oak_planks task.
            insert_idx = 0
            for i, t in enumerate(tasks):
                tid = t.get("id", "")
                if t["name"] == "oak_planks" and t["operation_type"] == "craft" \
                        and "mvb" not in tid and "island" not in tid:
                    insert_idx = i + 1

            # Find dependencies.
            planks_id = None
            ct_id = None
            for t in tasks:
                tid = t.get("id", "")
                if planks_id is None \
                        and t["name"] == "oak_planks" and t["operation_type"] == "craft" \
                        and "mvb" not in tid and "island" not in tid:
                    planks_id = tid
                if ct_id is None \
                        and t["name"] == "crafting_table" and t["operation_type"] == "craft" \
                        and "mvb" not in tid and "island" not in tid:
                    ct_id = tid

            deps = []
            if planks_id:
                deps.append(planks_id)
            if ct_id:
                deps.append(ct_id)

            craft_task = {
                "id": craft_id,
                "name": "chest",
                "quantity": total_chests,
                "dependencies": deps,
                "operation_type": "craft",
            }
            place_task = {
                "id": place_id,
                "name": "chest",
                "quantity": total_chests,
                "dependencies": [craft_id],
                "operation_type": "place",
            }
            tasks.insert(insert_idx, craft_task)
            tasks.insert(insert_idx + 1, place_task)

        if existing_place:
            existing_place["quantity"] = total_chests

        return tasks

    def simulate_with_chest_overhead(self) -> SimulationResult:
        """Run simulation, inject upfront chest crafting, and iterate to convergence."""
        with open(self.phase5_path, encoding="utf-8") as f:
            tasks = json.loads(f.read())

        # First pass: count how many stashes occur without chest overhead.
        result: SimulationResult | None = None
        try:
            result = self.simulate()
            if result.success and self._chest_counter == 0:
                return result
        except SimulationError as e:
            result = SimulationResult(success=False, error=str(e),
                                       inventory_snapshots=[], stashed_chests=[])

        chest_count = self._chest_counter
        if chest_count <= 0:
            return self.simulate()

        prev_chest_count = 0

        for _iteration in range(5):
            delta = chest_count - prev_chest_count
            if delta <= 0:
                break

            self._apply_chest_overhead(tasks, delta)
            self._ensure_chest_tasks(tasks, chest_count)

            prev_chest_count = chest_count

            tmp_path = self.phase5_path.with_suffix(".tmp.json")
            tmp_path.write_text(json.dumps(tasks, indent=2), encoding="utf-8")
            orig = self.phase5_path
            self.phase5_path = tmp_path

            try:
                result = self.simulate()
            except SimulationError as e:
                result = SimulationResult(success=False, error=str(e),
                                           inventory_snapshots=[], stashed_chests=[])
            finally:
                self.phase5_path = orig
                tmp_path.unlink(missing_ok=True)

            if result and result.success:
                return result

            if self._chest_counter <= chest_count:
                break
            chest_count = self._chest_counter

        return result or SimulationResult(
            success=False,
            error="Chest overhead did not converge after 5 iterations.",
        )

    def simulate_from_file(self) -> SimulationResult:
        return self.simulate()
