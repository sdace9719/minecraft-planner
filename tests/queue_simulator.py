import math
from collections import defaultdict


TOOL_SUFFIXES = ("_pickaxe", "_axe", "_shovel", "_hoe", "_sword")


def _is_tool_item(name):
    return name.endswith(TOOL_SUFFIXES)


def _tool_max_durability(tool_name, planner):
    for tier in planner.tools_flat:
        suffix = "_"
        if tool_name.startswith(f"{tier}{suffix}"):
            return int(planner.tools_flat[tier]["durability"])
    return None


def _move_tool_instances(source, dest, tool_name, qty):
    moved = []
    for _ in range(max(0, int(qty))):
        if source[tool_name]:
            moved.append(source[tool_name].pop())
    if moved:
        dest[tool_name].extend(moved)
    return moved


def _consume_tool_durability(inventory_tools, tool_name, uses):
    remaining = int(max(0, uses))
    broken = 0
    while remaining > 0:
        if not inventory_tools[tool_name]:
            raise AssertionError(f"Insufficient durability for tool {tool_name}: missing tool instances")
        top = inventory_tools[tool_name][-1]
        spend = min(top, remaining)
        top -= spend
        remaining -= spend
        inventory_tools[tool_name][-1] = top
        if top <= 0:
            inventory_tools[tool_name].pop()
            broken += 1
    return broken


def _snapshot(task, inventory, chest, inventory_tools, chest_tools, broken_events, error=None):
    return {
        "task_id": task["task_id"],
        "action": task["action"],
        "target": task["target"],
        "quantity": int(task.get("quantity", 0)),
        "inventory": {k: v for k, v in sorted(inventory.items()) if v > 0},
        "chest": {k: v for k, v in sorted(chest.items()) if v > 0},
        "tool_durability": {
            "inventory": {k: list(v) for k, v in sorted(inventory_tools.items()) if v},
            "chest": {k: list(v) for k, v in sorted(chest_tools.items()) if v},
        },
        "broken_tools": broken_events,
        "simulation_error": error,
    }


def simulate_queue(queue, planner, include_debug=False, allow_partial=False, simulate_durability=False):
    completed = set()
    task_index = {}
    inventory = defaultdict(int)
    chest = defaultdict(int)
    produced = defaultdict(int)
    inventory_tools = defaultdict(list)
    chest_tools = defaultdict(list)
    recipes = planner.recipes
    snapshots = []
    broken_counts = defaultdict(int)
    simulation_error = None
    for item, qty in getattr(planner, "exploration_byproducts", {}).items():
        if qty <= 0:
            continue
        inventory[item] += int(qty)
        produced[item] += int(qty)

    for idx, task in enumerate(queue):
        broken_events = []
        try:
            deps = task.get("dependencies", [])
            missing_deps = [dep for dep in deps if dep not in completed]
            if missing_deps:
                raise AssertionError(f"Task {idx} has unmet dependencies: {missing_deps}")
            late_deps = [dep for dep in deps if task_index.get(dep, idx) >= idx]
            if late_deps:
                raise AssertionError(f"Task {idx} has dependencies that are not in prior prefix: {late_deps}")

            action = task["action"]
            target = task["target"].split(":")[-1]
            qty = int(task.get("quantity", 0))

            if action in {"gather", "mine"}:
                chosen_tool = task.get("chosen_gather_method")
                if chosen_tool and chosen_tool != "hand":
                    if inventory.get(chosen_tool, 0) <= 0:
                        raise AssertionError(f"Task {idx} cannot execute {target}: missing required tool {chosen_tool}")
                    if simulate_durability:
                        durability_uses = int(task.get("durability_cost", qty))
                        broken = _consume_tool_durability(inventory_tools, chosen_tool, durability_uses)
                        if broken > 0:
                            broken_counts[chosen_tool] += broken
                            inventory[chosen_tool] = max(0, inventory[chosen_tool] - broken)
                            broken_events.append({"tool": chosen_tool, "count": int(broken)})
                inventory[target] += qty
                produced[target] += qty
            elif action in {"craft", "smelt", "strip"}:
                recipe = recipes.get(target)
                if not recipe:
                    raise AssertionError(f"Task {idx} has no recipe for {target}")
                if action == "smelt":
                    fuel_item = task.get("fuel_item")
                    fuel_quantity = int(task.get("fuel_quantity", 0))
                    if not fuel_item or fuel_quantity <= 0:
                        raise AssertionError(f"Task {idx} smelt {target} missing explicit fuel metadata")
                    if inventory[fuel_item] < fuel_quantity:
                        raise AssertionError(
                            f"Task {idx} cannot execute {target}: needs {fuel_quantity} {fuel_item}, has {inventory[fuel_item]}"
                        )
                    inventory[fuel_item] -= fuel_quantity
                crafts = math.ceil(qty / recipe["yield"])
                for ingredient, count in recipe["ingredients"].items():
                    needed = max(1, math.ceil(qty / 8)) if (count == -1 and ingredient == "coal") else crafts * count
                    if inventory[ingredient] < needed:
                        raise AssertionError(
                            f"Task {idx} cannot execute {target}: needs {needed} {ingredient}, has {inventory[ingredient]}"
                        )
                    inventory[ingredient] -= needed
                inventory[target] += qty
                produced[target] += qty
                if _is_tool_item(target):
                    durability = _tool_max_durability(target, planner)
                    if durability is None:
                        raise AssertionError(f"Task {idx} crafted unknown tool tier for {target}")
                    for _ in range(qty):
                        inventory_tools[target].append(durability)
            elif action == "craft_chest":
                inventory["chest"] += qty
                produced["chest"] += qty
            elif action == "place_chest":
                if inventory["chest"] <= 0:
                    raise AssertionError(f"Task {idx} cannot place chest: chest not available")
                inventory["chest"] -= 1
            elif action == "deposit_items":
                for item, item_qty in task.get("items", {}).items():
                    if inventory[item] < item_qty:
                        raise AssertionError(f"Task {idx} cannot deposit {item}: insufficient inventory")
                    inventory[item] -= item_qty
                    chest[item] += item_qty
                    if _is_tool_item(item):
                        moved = _move_tool_instances(inventory_tools, chest_tools, item, item_qty)
                        if len(moved) != int(item_qty):
                            raise AssertionError(
                                f"Task {idx} cannot deposit {item}: durability instances mismatch ({len(moved)}/{item_qty})"
                            )
            elif action == "withdraw_items":
                for item, item_qty in task.get("items", {}).items():
                    if chest[item] < item_qty:
                        raise AssertionError(f"Task {idx} cannot withdraw {item}: insufficient chest")
                    chest[item] -= item_qty
                    inventory[item] += item_qty
                    if _is_tool_item(item):
                        moved = _move_tool_instances(chest_tools, inventory_tools, item, item_qty)
                        if len(moved) != int(item_qty):
                            raise AssertionError(
                                f"Task {idx} cannot withdraw {item}: durability instances mismatch ({len(moved)}/{item_qty})"
                            )
            elif action == "toss_item":
                if _is_tool_item(target):
                    _move_tool_instances(inventory_tools, defaultdict(list), target, qty)
                inventory[target] = max(0, inventory[target] - qty)
            else:
                raise AssertionError(f"Task {idx} has unsupported action {action}")
        except AssertionError as error:
            if include_debug and allow_partial:
                simulation_error = str(error)
                snapshots.append(_snapshot(task, inventory, chest, inventory_tools, chest_tools, broken_events, simulation_error))
                break
            raise

        completed.add(task["task_id"])
        task_index[task["task_id"]] = idx
        if include_debug:
            snapshots.append(_snapshot(task, inventory, chest, inventory_tools, chest_tools, broken_events))

    if include_debug:
        debug = {
            "snapshots": snapshots,
            "broken_tool_counts": {k: int(v) for k, v in sorted(broken_counts.items()) if v > 0},
            "remaining_tool_durability": {
                "inventory": {k: list(v) for k, v in sorted(inventory_tools.items()) if v},
                "chest": {k: list(v) for k, v in sorted(chest_tools.items()) if v},
            },
            "simulation_error": simulation_error,
        }
        return dict(inventory), dict(chest), dict(produced), debug
    return dict(inventory), dict(chest), dict(produced)
