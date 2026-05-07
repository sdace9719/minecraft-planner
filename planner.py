"""Protocol-oriented planner (source of truth over generate_dag.py)."""

import json
import math
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
import shutil

from mojang_datapack.recipes import DatapackRecipeIndex
from mojang_datapack.worldgen import load_worldgen_hints

_ROOT = Path(__file__).resolve().parent


def _load_tools_flat():
    path = _ROOT / "constants" / "tools.json"
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _load_block_hardness_map():
    path = _ROOT / "constants" / "block_hardness.json"
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as handle:
        return json.load(handle).get("hardness", {})


def _load_material_harvest_map():
    path = _ROOT / "constants" / "material_harvest.json"
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    return {k: v for k, v in data.items() if not str(k).startswith("_")}


TOOLS_FLAT = _load_tools_flat()
TIER_ORDER = ["wooden", "stone", "iron", "diamond"]
TOOL_PROPERTIES = {k: (v["speed"], v["durability"], k) for k, v in TOOLS_FLAT.items() if k in TIER_ORDER}

MATERIAL_DIFFICULTY = {
    "wood": 1,
    "stone": 2,
    "iron": 20,
    "diamond": 100,
    "gold": 50,
    "netherite": 500,
    "xp": 10,
}

BLOCK_HARDNESS = _load_block_hardness_map()
MATERIAL_HARVEST = _load_material_harvest_map()

SLOT_LIMIT = 36
DEFAULT_STACK_SIZE = 64
MAX_ITERATIONS = 10


class UnresolvableQueueError(RuntimeError):
    pass


def normalize_item_name(name):
    return name.split(":")[-1] if ":" in name else name


def load_material_sources(path="material_sources.json"):
    metadata = {}
    file_path = Path(path)
    if not file_path.exists():
        return metadata
    with file_path.open("r", encoding="utf-8") as handle:
        for row in json.load(handle):
            if "name" in row:
                metadata[row["name"]] = row
    return metadata


def get_location(block_name):
    name = normalize_item_name(block_name)
    if any(x in name for x in ["ore", "stone", "slate", "andesite", "diorite", "granite"]):
        return "underground"
    if any(x in name for x in ["log", "tree", "leaves", "wood", "apple"]):
        return "surface_forest"
    if any(x in name for x in ["sand", "clay", "gravel"]):
        return "surface_river"
    return "surface_plains"


def get_travel_cost(loc1, loc2):
    if loc1 == loc2:
        return 0
    if "underground" in (loc1, loc2):
        return 50
    return 20


def infer_tool_type(item_name, tool_info):
    item = normalize_item_name(item_name)
    tt = tool_info.get("toolType")
    if tt in {"axe", "pickaxe", "shovel", "hoe"}:
        return tt
    if any(x in item for x in ["log", "tree", "wood"]):
        return "axe"
    if "bamboo" in item:
        return "axe"
    if any(x in item for x in ["dirt", "sand", "gravel", "clay"]):
        return "shovel"
    return "pickaxe"


def parse_tier_from_tool_name(tool_name, tool_type):
    """Parse 'iron_pickaxe' + 'pickaxe' -> 'iron'."""
    suffix = f"_{tool_type}"
    if not tool_name.endswith(suffix):
        return None
    prefix = tool_name[: -len(suffix)]
    if prefix in TIER_ORDER:
        return prefix
    return None


def resolve_break_block_id(item, gatherables, tools_info):
    """Block registry id for hardness lookup (constants/block_hardness.json keys)."""
    info = tools_info.get(item, {})
    if info.get("source_block"):
        return normalize_item_name(info["source_block"])
    return normalize_item_name(gatherables.get(item, item))


def hardness_for_block(block_id, block_hardness_map):
    if block_id not in block_hardness_map:
        raise ValueError(
            f"Missing block hardness in constants/block_hardness.json for block {block_id!r}. "
            "Add it to the hardness map or fix source_block / gatherables resolution; do not guess."
        )
    return float(block_hardness_map[block_id])


def speed_from_chosen_method(chosen_method, tools_flat):
    """T_break divisor speed; hand mining uses 1.0 (matches volume*1.5 hand baseline)."""
    if not chosen_method or chosen_method == "hand":
        return 1.0
    parts = chosen_method.rsplit("_", 1)
    if len(parts) != 2:
        return 1.0
    tier, _tt = parts
    if tier in tools_flat:
        return float(tools_flat[tier]["speed"])
    return 1.0


def resolve_recipe_from_api(api, item_name):
    # Prefer Mojang datapack recipes (vendored snapshot) for craft/smelt resolution.
    datapack = getattr(api, "datapack_recipes", None)
    if datapack is not None:
        candidates = []
        if hasattr(datapack, "get_all"):
            candidates = datapack.get_all(item_name)
        else:
            single = datapack.get(item_name)
            if single is not None:
                candidates = [single]

        viable = []
        preferred_ingredient = "white_wool" if item_name.endswith("_wool") else None
        for dp in candidates:
            # Skip recipes that require ingredients known to be silk-touch-only and
            # not otherwise craft/process resolvable from datapack recipes.
            blocked = False
            crafted_inputs = 0
            for ingredient in dp.ingredients:
                if datapack.get(ingredient) is not None:
                    crafted_inputs += 1
                    continue
                source_resp = api.get("get_sources", ingredient)
                drops = source_resp.get("droppedFrom", []) if isinstance(source_resp, dict) else []
                if drops and not any(not d.get("silkTouch") for d in drops):
                    blocked = True
                    break
            if blocked:
                continue
            if _station_depends_on_item(datapack, dp.station, item_name):
                continue
            preferred_penalty = 0
            if preferred_ingredient is not None and preferred_ingredient not in dp.ingredients:
                preferred_penalty = 1
            viable.append((preferred_penalty, crafted_inputs, len(dp.ingredients), dp))

        if viable:
            viable.sort(key=lambda entry: (entry[0], entry[1], entry[2]))
            dp = viable[0][3]
            return (
                {
                    "action": dp.action,
                    "station": dp.station,
                    "yield": dp.result_count,
                    "ingredients": dict(dp.ingredients),
                    "selected_recipe_type": getattr(dp, "raw_type", dp.action),
                    "selected_ingredients": dict(dp.ingredients),
                },
                None,
            )
    return None, f"No datapack recipe found for {item_name}."


def _station_depends_on_item(datapack, station, item_name):
    if not station or station == "player":
        return False
    target = normalize_item_name(item_name)
    stack = [normalize_item_name(station)]
    seen = set()
    while stack:
        node = stack.pop()
        if node in seen:
            continue
        seen.add(node)
        recipe = datapack.get(node)
        if recipe is None:
            continue
        for ingredient in recipe.ingredients:
            ing = normalize_item_name(ingredient)
            if ing == target:
                return True
            stack.append(ing)
    return False


class MCDataAPI:
    def __init__(self, version="1.20.1"):
        self.version = version
        self.cache = {}
        self.node_bin = shutil.which("node") or self._resolve_node_from_login_shell()
        self.datapack_recipes = self._load_datapack_recipe_index()

    def _resolve_node_from_login_shell(self):
        try:
            result = subprocess.run(
                ["bash", "-lc", "command -v node"],
                capture_output=True,
                text=True,
                check=True,
            )
            path = (result.stdout or "").strip()
            return path or None
        except Exception:
            return None

    def get(self, action, item_name):
        key = (action, item_name)
        if key in self.cache:
            return self.cache[key]
        try:
            if not self.node_bin:
                raise RuntimeError("Node runtime not available for get_mc_data.js lookups.")
            result = subprocess.run(
                [self.node_bin, "get_mc_data.js", self.version, action, item_name],
                capture_output=True,
                text=True,
                check=True,
            )
            data = json.loads(result.stdout)
        except Exception as error:
            data = {"error": str(error)}
        self.cache[key] = data
        return data

    def _load_datapack_recipe_index(self):
        recipe_dir = Path("mojang-data/1.21.1/data/minecraft/recipe")
        if not recipe_dir.exists():
            return None
        item_tag_dir = Path("mojang-data/1.21.1/data/minecraft/tags/item")
        index = DatapackRecipeIndex(recipe_dir, item_tag_dir=item_tag_dir)
        index.load()
        return index


class SingleItemPlanner:
    def __init__(self, api, item_name, quantity):
        self.api = api
        self.target_name = normalize_item_name(item_name)
        self.target_qty = quantity
        self.recipes = {}
        self.gatherables = {}
        self.tools_info = {}
        self.quantities = defaultdict(int)
        self.stations_needed = set()
        self.quantities[self.target_name] += quantity
        self.resolve(self.target_name)
        self._propagate_quantities()

    def resolve(self, item_name, visited=None):
        if visited is None:
            visited = set()
        if item_name in visited:
            return
        visited.add(item_name)
        if item_name in self.recipes or item_name in self.gatherables:
            return

        if item_name.startswith("stripped_") and item_name.endswith("_log"):
            base = item_name.replace("stripped_", "")
            self.recipes[item_name] = {
                "action": "strip",
                "station": "player",
                "yield": 1,
                "ingredients": {base: 1},
            }
            self.tools_info[item_name] = {"toolType": "axe"}
            self.resolve(base, visited.copy())
            return

        recipe, error = resolve_recipe_from_api(self.api, item_name)
        if recipe is not None:
            if any(ingredient in visited for ingredient in recipe["ingredients"]):
                recipe = None
            else:
                self.recipes[item_name] = recipe
                self.stations_needed.add(recipe["station"])
                for ingredient in recipe["ingredients"]:
                    self.resolve(ingredient, visited.copy())
                return

        source_resp = self.api.get("get_sources", item_name)
        if "error" in source_resp:
            raise NotImplementedError(
                f"Could not resolve {item_name} because source lookup failed: {source_resp['error']}"
            )

        if source_resp.get("droppedFrom"):
            best_drop = next((d for d in source_resp["droppedFrom"] if not d.get("silkTouch")), None)
            if best_drop is None:
                raise NotImplementedError(f"Item {item_name} requires Silk Touch, which is not supported.")
            source_block = best_drop["block"]
            self.gatherables[item_name] = source_block
            tool_resp = self.api.get("get_tool_info", source_block)
            if "error" not in tool_resp:
                self.tools_info[item_name] = {k: v for k, v in tool_resp.items() if k != "hardness"}
                self.tools_info[item_name]["source_block"] = source_block
            return

        # No recipe and no block drop info: treat as gathered (e.g., mob drops) with unknown source.
        self.gatherables[item_name] = item_name
        return

    def _propagate_quantities(self):
        all_items = set(self.recipes.keys()) | set(self.gatherables.keys())
        in_deg = {u: 0 for u in all_items}
        adjacency = {u: [] for u in all_items}
        for product, recipe in self.recipes.items():
            for ingredient in recipe["ingredients"]:
                if ingredient in all_items:
                    adjacency[product].append(ingredient)
                    in_deg[ingredient] += 1
        queue = [item for item in all_items if in_deg[item] == 0]
        ordered = []
        while queue:
            node = queue.pop(0)
            ordered.append(node)
            for nxt in adjacency[node]:
                in_deg[nxt] -= 1
                if in_deg[nxt] == 0:
                    queue.append(nxt)
        for node in ordered:
            needed = self.quantities.get(node, 0)
            if needed <= 0 or node not in self.recipes:
                continue
            recipe = self.recipes[node]
            crafts = math.ceil(needed / recipe["yield"])
            for ingredient, count in recipe["ingredients"].items():
                qty = math.ceil(needed / 8) if (count == -1 and ingredient == "coal") else crafts * count
                self.quantities[ingredient] += qty

class GlobalPlanner:
    def __init__(self, api, material_meta):
        self.api = api
        self.material_meta = material_meta
        self.recipes = {}
        self.gatherables = {}
        self.tools_info = {}
        self.quantities = defaultdict(int)
        self.stations_needed = set()
        self.tool_requirements = defaultdict(float)
        self.selected_tools = {}
        self.roi_selection_debug = {}
        self.material_gather_strategy = {}
        self.total_durability_required = defaultdict(int)
        self.tool_durability_remainder = defaultdict(int)
        self.exploration_byproducts = defaultdict(int)
        self.smelt_fuel_plan = {}
        self.injected_tools = set()
        self.blueprint_required = set()
        self.blueprint_quantities = defaultdict(int)
        self.worldgen_hints = load_worldgen_hints(Path("mojang-data/1.21.1/data/minecraft"))
        self.tools_flat = TOOLS_FLAT
        self.block_hardness = BLOCK_HARDNESS
        self.material_harvest = MATERIAL_HARVEST

    def _resolve_break_block_id_with(self, item, gatherables, tools_info):
        it = normalize_item_name(item)
        if it.startswith("stripped_") and it.endswith("_log"):
            return it.replace("stripped_", "", 1)
        return resolve_break_block_id(item, gatherables, tools_info)

    def _hardness_for_item(self, item, gatherables=None, tools_info=None):
        gp = gatherables if gatherables is not None else self.gatherables
        ti = tools_info if tools_info is not None else self.tools_info
        return hardness_for_block(self._resolve_break_block_id_with(item, gp, ti), self.block_hardness)

    def _speed_for_gather_estimate(self, item):
        strat = self.material_gather_strategy.get(item)
        if strat:
            return max(0.1, speed_from_chosen_method(strat["chosen_method"], self.tools_flat))
        tt = infer_tool_type(item, self.tools_info.get(item, {}))
        sel = self.selected_tools.get(tt)
        if sel:
            tier = parse_tier_from_tool_name(sel, tt)
            if tier and tier in self.tools_flat:
                return float(self.tools_flat[tier]["speed"])
        return 1.0

    def _break_time_gather_mine(self, item, qty, gatherables=None, tools_info=None):
        h = self._hardness_for_item(item, gatherables, tools_info)
        s = self._speed_for_gather_estimate(item)
        return float(qty) * h * 1.5 / s

    def merge(self, planners):
        for planner in planners:
            for key, value in planner.recipes.items():
                if key not in self.recipes:
                    self.recipes[key] = value
                self.stations_needed.add(value["station"])
            for key, value in planner.gatherables.items():
                if key not in self.gatherables:
                    self.gatherables[key] = value
            for key, value in planner.tools_info.items():
                if key not in self.tools_info:
                    self.tools_info[key] = value
            for key, value in planner.quantities.items():
                self.quantities[key] += value
            self.blueprint_required.add(planner.target_name)
            self.blueprint_quantities[planner.target_name] += planner.target_qty
        self._plan_smelt_fuel_requirements()
        self._compute_tool_requirements()

    def _estimate_item_acquisition_seconds(self, item_name, quantity):
        if quantity <= 0:
            return 0.0
        try:
            sub = SingleItemPlanner(self.api, item_name, int(quantity))
        except (NotImplementedError, RuntimeError) as error:
            raise RuntimeError(f"Fuel candidate {item_name!r} cannot be resolved: {error}") from error
        merged_gatherables = {**self.gatherables, **sub.gatherables}
        merged_tools_info = {**self.tools_info, **sub.tools_info}
        total = 0.0
        for mat, q in sub.quantities.items():
            if q <= 0:
                continue
            if mat in sub.recipes:
                action = sub.recipes[mat]["action"]
                total += self._estimate_task_seconds(
                    mat,
                    int(q),
                    action,
                    gatherables=merged_gatherables,
                    tools_info=merged_tools_info,
                )
            elif mat in sub.gatherables:
                source = sub.gatherables.get(mat, mat)
                action = "mine" if any(
                    x in source for x in ["ore", "stone", "deepslate", "andesite", "diorite", "granite"]
                ) else "gather"
                total += self._estimate_task_seconds(
                    mat,
                    int(q),
                    action,
                    gatherables=merged_gatherables,
                    tools_info=merged_tools_info,
                )
        return float(total)

    def _ensure_item_path(self, item_name, quantity):
        if quantity <= 0:
            return
        planner = SingleItemPlanner(self.api, item_name, int(quantity))
        self._merge_subplanner(planner, skip_target=item_name)
        self.quantities[item_name] += int(quantity)

    def _plan_smelt_fuel_requirements(self):
        self.smelt_fuel_plan = {}
        smelt_items = []
        for item, qty in self.quantities.items():
            if qty <= 0:
                continue
            recipe = self.recipes.get(item)
            if recipe and recipe.get("action") == "smelt":
                smelt_items.append((item, int(qty)))
        for item, qty in smelt_items:
            planks_item = "oak_planks"
            # Wooden planks smelt 1.5 items each => 2/3 plank per output.
            fuel_ratio = float(2.0 / 3.0)
            planks_qty = int(max(1, math.ceil(float(qty) * fuel_ratio)))
            planks_cost = self._estimate_item_acquisition_seconds(planks_item, planks_qty)
            self._ensure_item_path(planks_item, planks_qty)
            self.smelt_fuel_plan[item] = {
                "fuel_item": planks_item,
                "fuel_quantity": int(planks_qty),
                "fuel_cost_seconds": round(float(planks_cost), 3),
                "fuel_ratio_per_output": float(fuel_ratio),
                "output_quantity": int(qty),
            }

    def _compute_tool_requirements(self):
        for item, qty in self.quantities.items():
            if qty <= 0 or item not in self.tools_info:
                continue
            tool_info = self.tools_info[item]
            hardness = self._hardness_for_item(item)
            tool_type = self._tool_class_for_item(item, tool_info)
            decision = self._estimate_gather_method(item, qty, hardness, tool_type, bool(tool_info.get("needsTool")))
            self.material_gather_strategy[item] = decision
            if decision["chosen_method"] != "hand":
                self.tool_requirements[tool_type] += qty * hardness

    def _ensure_gather_strategies_for_new_quantities(self):
        """Items added after merge (e.g. diamond from ROI tool chains) need gather strategy + tool volume."""
        for item, qty in self.quantities.items():
            if qty <= 0 or item not in self.tools_info:
                continue
            if item in self.material_gather_strategy:
                continue
            tool_info = self.tools_info[item]
            hardness = self._hardness_for_item(item)
            tool_type = self._tool_class_for_item(item, tool_info)
            decision = self._estimate_gather_method(item, qty, hardness, tool_type, bool(tool_info.get("needsTool")))
            self.material_gather_strategy[item] = decision
            if decision["chosen_method"] != "hand":
                self.tool_requirements[tool_type] += qty * hardness

    def _estimate_gather_method(self, item, qty, hardness, tool_type, needs_tool):
        volume = max(1.0, float(qty) * float(hardness))
        hand_time = volume * 1.5
        rule = self._harvest_rule(item)
        min_tier_name = rule.get("min_tier") or "wooden"
        hand_allowed = bool(rule.get("hand_harvest_allowed", False)) or (not needs_tool)
        min_idx = TIER_ORDER.index(min_tier_name) if min_tier_name in TIER_ORDER else 0
        best_tier = None
        best_total = float("inf")
        for tier in TIER_ORDER:
            if tier not in TOOL_PROPERTIES:
                continue
            if TIER_ORDER.index(tier) < min_idx:
                continue
            speed, durability, _ = TOOL_PROPERTIES[tier]
            tool_count = max(1, math.ceil(volume / durability))
            gather_time = volume * 1.5 / speed
            craft_overhead = tool_count * (4 if tier == "wooden" else 10 if tier == "stone" else 100 if tier == "iron" else 250)
            total = gather_time + craft_overhead
            if total < best_total:
                best_total = total
                best_tier = tier
        use_tool = (not hand_allowed) or bool(needs_tool) or (best_total < hand_time)
        chosen = f"{best_tier}_{tool_type}" if use_tool and best_tier else "hand"
        local_tier = best_tier if chosen != "hand" else None
        return {
            "chosen_method": chosen,
            "local_tier": local_tier,
            "estimated_seconds_saved": round(hand_time - best_total, 3) if chosen != "hand" else 0.0,
            "hand_seconds": round(hand_time, 3),
            "tool_seconds": round(best_total, 3),
        }

    def _harvest_rule(self, item):
        key = normalize_item_name(item)
        if key in self.material_harvest:
            return self.material_harvest[key]
        info = self.tools_info.get(item, {})
        needs = info.get("needsTool", True)
        return {"tool_class": infer_tool_type(item, info), "min_tier": "wooden", "hand_harvest_allowed": not needs}

    def _tool_class_for_item(self, item, tool_info=None):
        rule = self._harvest_rule(item)
        rule_class = rule.get("tool_class")
        if rule_class in {"pickaxe", "axe", "shovel", "hoe"}:
            return rule_class
        return infer_tool_type(item, tool_info or self.tools_info.get(item, {}))

    def _can_gather_by_hand(self, item):
        info = self.tools_info.get(item, {})
        needs_tool = bool(info.get("needsTool", False))
        rule = self._harvest_rule(item)
        return bool(rule.get("hand_harvest_allowed", False)) or (not needs_tool)

    def _max_min_harvest_tier_index(self, tool_type):
        highest = 0
        for item, qty in self.quantities.items():
            if qty <= 0 or item not in self.tools_info:
                continue
            if self._tool_class_for_item(item, self.tools_info[item]) != tool_type:
                continue
            tier_name = self._harvest_rule(item)["min_tier"]
            if tier_name in TIER_ORDER:
                highest = max(highest, TIER_ORDER.index(tier_name))
        return highest

    def _estimate_single_tool_chain_seconds(self, tool_type, tier):
        name = f"{tier}_{tool_type}"
        try:
            sub = SingleItemPlanner(self.api, name, 1)
        except (NotImplementedError, RuntimeError):
            return 150.0
        if name in sub.gatherables and name not in sub.recipes:
            return 150.0
        merged_gatherables = {**self.gatherables, **sub.gatherables}
        merged_tools_info = {**self.tools_info, **sub.tools_info}
        total = 0.0
        for mat, q in sub.quantities.items():
            if q <= 0:
                continue
            if mat in sub.recipes:
                total += float(q) * 0.4
            elif mat in sub.gatherables:
                act = "mine" if any(
                    x in sub.gatherables.get(mat, "") for x in ["ore", "stone", "deepslate", "andesite"]
                ) else "gather"
                total += self._estimate_task_seconds(
                    mat,
                    max(1, int(q)),
                    act,
                    gatherables=merged_gatherables,
                    tools_info=merged_tools_info,
                )
        return total

    def _estimate_chain_cost_seconds(self, tool_type, final_tier, final_tool_copies=1):
        fi = TIER_ORDER.index(final_tier)
        total = 0.0
        for idx in range(fi):
            tier = TIER_ORDER[idx]
            total += self._estimate_single_tool_chain_seconds(tool_type, tier)
        total += self._estimate_single_tool_chain_seconds(tool_type, final_tier) * max(1, int(final_tool_copies))
        return total

    def _estimate_chain_ore_requirements(self, tool_type, final_tier, final_tool_copies=1):
        fi = TIER_ORDER.index(final_tier)
        ore_totals = defaultdict(int)
        for idx in range(fi + 1):
            tier = TIER_ORDER[idx]
            copies = max(1, int(final_tool_copies)) if idx == fi else 1
            try:
                sub = SingleItemPlanner(self.api, f"{tier}_{tool_type}", copies)
            except (NotImplementedError, RuntimeError):
                continue
            ore_totals["raw_iron"] += int(sub.quantities.get("raw_iron", 0))
            ore_totals["diamond"] += int(sub.quantities.get("diamond", 0))
        return dict(ore_totals)

    def _validate_tier_search_config(self, tier):
        row = self.tools_flat.get(tier)
        if not row:
            raise RuntimeError(f"Missing tool tier config for {tier!r} in constants/tools.json")
        for field in ("blocks_to_break", "junk_block", "vein_size"):
            if field not in row:
                raise RuntimeError(
                    f"Missing {field!r} for tier {tier!r} in constants/tools.json; strict model requires it."
                )
        blocks = int(row["blocks_to_break"])
        vein = int(row["vein_size"])
        if blocks < 0:
            raise RuntimeError(f"Invalid blocks_to_break={blocks} for tier {tier!r}; must be >= 0.")
        if vein <= 0:
            raise RuntimeError(f"Invalid vein_size={vein} for tier {tier!r}; must be > 0.")
        return row

    def _junk_output_item(self, junk_block):
        block = normalize_item_name(junk_block)
        if block == "stone":
            return "cobblestone"
        if block == "deepslate":
            return "cobbled_deepslate"
        return block

    def _estimate_tunnel_profile(self, tool_type, final_tier, final_tool_copies=1):
        if tool_type != "pickaxe":
            return 0.0, []
        tools = self.tools_flat
        hmap = self.block_hardness
        fi = TIER_ORDER.index(final_tier)
        ore_qty = self._estimate_chain_ore_requirements(tool_type, final_tier, final_tool_copies)
        total = 0.0
        rows = []
        if fi >= TIER_ORDER.index("iron"):
            row = self._validate_tier_search_config("iron")
            ore_needed = int(ore_qty.get("raw_iron", 0))
            expected_veins = int(math.ceil(float(ore_needed) / float(int(row["vein_size"])))) if ore_needed > 0 else 0
            n = int(row["blocks_to_break"]) * expected_veins
            junk = normalize_item_name(row["junk_block"])
            hardness = hardness_for_block(junk, hmap)
            spd = tools["stone"]["speed"]
            t = n * hardness * 1.5 / spd
            total += t
            rows.append(
                {
                    "tier": "iron",
                    "ore_item": "raw_iron",
                    "ore_needed": ore_needed,
                    "vein_size": int(row["vein_size"]),
                    "expected_veins": expected_veins,
                    "junk_block": junk,
                    "junk_blocks": int(n),
                    "time_seconds": round(float(t), 3),
                    "junk_output_item": self._junk_output_item(junk),
                }
            )
        if fi >= TIER_ORDER.index("diamond"):
            row = self._validate_tier_search_config("diamond")
            ore_needed = int(ore_qty.get("diamond", 0))
            expected_veins = int(math.ceil(float(ore_needed) / float(int(row["vein_size"])))) if ore_needed > 0 else 0
            n = int(row["blocks_to_break"]) * expected_veins
            junk = normalize_item_name(row["junk_block"])
            hardness = hardness_for_block(junk, hmap)
            spd = tools["iron"]["speed"]
            t = n * hardness * 1.5 / spd
            total += t
            rows.append(
                {
                    "tier": "diamond",
                    "ore_item": "diamond",
                    "ore_needed": ore_needed,
                    "vein_size": int(row["vein_size"]),
                    "expected_veins": expected_veins,
                    "junk_block": junk,
                    "junk_blocks": int(n),
                    "time_seconds": round(float(t), 3),
                    "junk_output_item": self._junk_output_item(junk),
                }
            )
        return total, rows

    def _transitive_recipe_deps(self, start, prereqs):
        """Items that must be satisfied before `start` (following prereq edges only)."""
        stack = [start]
        seen = set()
        while stack:
            cur = stack.pop()
            for d in prereqs.get(cur, ()):
                if d not in seen:
                    seen.add(d)
                    stack.append(d)
        return seen

    def _recipe_gather_cycle_blocked(self, item, gather_tool, recipe_prereqs):
        """True if using gather_tool to obtain item is impossible (item is in recipe-only
        transitive deps of the tool). Does not use gather edges in recipe_prereqs."""
        if not gather_tool or gather_tool == "hand":
            return True
        before_tool = self._transitive_recipe_deps(gather_tool, recipe_prereqs)
        return item in before_tool

    def _prerequisites_cyclic(self, prereqs):
        visiting = set()
        visited = set()

        def visit(node):
            if node in visiting:
                return True
            if node in visited:
                return False
            visiting.add(node)
            for dep in prereqs.get(node, ()):
                if visit(dep):
                    return True
            visiting.remove(node)
            visited.add(node)
            return False

        for name in prereqs:
            if name not in visited:
                if visit(name):
                    return True
        return False

    def _add_prereq_if_acyclic(self, prereqs, item, new_dep):
        prereqs[item].add(new_dep)
        if self._prerequisites_cyclic(prereqs):
            prereqs[item].remove(new_dep)
            return False
        return True

    def _recipe_prereqs_for_all_recipes(self):
        prereqs = defaultdict(set)
        for product, recipe in self.recipes.items():
            for ingredient in recipe.get("ingredients", {}):
                prereqs[product].add(ingredient)
            station = recipe.get("station")
            if station and station != "player":
                prereqs[product].add(station)
        return prereqs

    def _reconcile_gather_strategies(self):
        recipe_prereqs = self._recipe_prereqs_for_all_recipes()
        for item, strat in list(self.material_gather_strategy.items()):
            if item not in self.tools_info:
                continue
            if strat.get("chosen_method") == "hand":
                continue
            tt = self._tool_class_for_item(item, self.tools_info[item])
            sel = self.selected_tools.get(tt)
            if not sel:
                continue
            rec = self.recipes.get(sel)
            if rec and item in rec.get("ingredients", {}):
                continue
            if item in self._transitive_recipe_deps(sel, recipe_prereqs):
                continue
            strat["chosen_method"] = sel
            self.material_gather_strategy[item] = strat

    def calculate_global_roi(self):
        for tool_type, volume in list(self.tool_requirements.items()):
            self._apply_roi_for_tool_type(tool_type, volume)
        self._ensure_gather_strategies_for_new_quantities()
        missing_tool_types = [
            tool_type
            for tool_type, volume in self.tool_requirements.items()
            if volume > 0 and tool_type not in self.selected_tools
        ]
        for tool_type in missing_tool_types:
            self._apply_roi_for_tool_type(tool_type, self.tool_requirements[tool_type])
        if missing_tool_types:
            self._ensure_gather_strategies_for_new_quantities()
        self._compute_exploration_byproducts()

    def _apply_roi_for_tool_type(self, tool_type, volume):
        if volume <= 0:
            return
        floor_idx = self._max_min_harvest_tier_index(tool_type)
        best_tier_name = None
        best_score = float("inf")
        tools = self.tools_flat
        candidate_rows = []
        for tier in TIER_ORDER:
            if tier not in tools:
                continue
            if TIER_ORDER.index(tier) < floor_idx:
                continue
            tw = tools[tier]
            speed = float(tw["speed"])
            durability = int(tw["durability"])
            tool_copies = max(1, math.ceil(float(volume) / float(durability)))
            workload_time = float(volume) * 1.5 / speed
            chain_time = self._estimate_chain_cost_seconds(tool_type, tier, tool_copies)
            tunnel_time, tunnel_rows = self._estimate_tunnel_profile(tool_type, tier, tool_copies)
            total_time = workload_time + chain_time + tunnel_time
            candidate_rows.append(
                {
                    "tier": tier,
                    "speed": speed,
                    "durability": durability,
                    "tool_copies": int(tool_copies),
                    "workload_time": round(workload_time, 3),
                    "chain_time": round(chain_time, 3),
                    "tunnel_time": round(tunnel_time, 3),
                    "total_time": round(total_time, 3),
                    "tunnel_profile": tunnel_rows,
                }
            )
            if total_time < best_score:
                best_score = total_time
                best_tier_name = tier
        if not best_tier_name:
            return
        final_tier = best_tier_name
        tw = tools[final_tier]
        durability = int(tw["durability"])
        tool_name = f"{final_tier}_{tool_type}"
        self.selected_tools[tool_type] = tool_name
        remainder = self.tool_durability_remainder[tool_type]
        remaining_volume = max(0, math.ceil(volume) - remainder)
        tool_count = max(1, math.ceil(remaining_volume / durability)) if remaining_volume > 0 else 1
        consumed = max(0, math.ceil(volume))
        provided = tool_count * durability
        self.tool_durability_remainder[tool_type] = max(0, remainder + provided - consumed)

        fi = TIER_ORDER.index(final_tier)
        for idx in range(fi + 1):
            tier = TIER_ORDER[idx]
            name = f"{tier}_{tool_type}"
            count = tool_count if idx == fi else 1
            self.quantities[name] += count
            self._merge_subplanner(SingleItemPlanner(self.api, name, count), skip_target=name)

        self.total_durability_required[tool_name] += math.ceil(volume)
        if fi >= TIER_ORDER.index("stone") and tool_type == "pickaxe":
            self._inject_wooden_pickaxe_bootstrap()
        winning = next((row for row in candidate_rows if row["tier"] == final_tier), {})
        self.roi_selection_debug[tool_type] = {
            "tool_type": tool_type,
            "required_volume": round(float(volume), 3),
            "min_floor_tier": TIER_ORDER[floor_idx] if floor_idx < len(TIER_ORDER) else TIER_ORDER[-1],
            "selected_tier": final_tier,
            "selected_tool": tool_name,
            "selected_total_time": winning.get("total_time"),
            "candidates": candidate_rows,
        }

    def _compute_exploration_byproducts(self):
        self.exploration_byproducts = defaultdict(int)
        pick = self.selected_tools.get("pickaxe")
        if not pick:
            return
        pick_copies = int(max(1, self.quantities.get(pick, 1)))
        tier = parse_tier_from_tool_name(pick, "pickaxe")
        if not tier:
            raise RuntimeError(f"Could not parse selected pickaxe tier from {pick!r}")
        _time, tunnel_rows = self._estimate_tunnel_profile("pickaxe", tier, pick_copies)
        for row in tunnel_rows:
            output = row.get("junk_output_item")
            qty = int(row.get("junk_blocks", 0))
            if output and qty > 0:
                self.exploration_byproducts[output] += qty

    def build_debug_reports(self, queue):
        from tests.queue_simulator import simulate_queue

        try:
            _inventory, _chest, _produced, debug = simulate_queue(
                queue, self, include_debug=True, allow_partial=False, simulate_durability=True
            )
        except AssertionError as error:
            raise UnresolvableQueueError(f"Strict debug report generation failed: {error}") from error
        roi_report = {
            tool_type: self.roi_selection_debug.get(tool_type, {})
            for tool_type in sorted(self.selected_tools.keys())
        }
        return {
            "inventory_snapshots": debug.get("snapshots", []),
            "tool_durability_summary": {
                "broken_tool_counts": debug.get("broken_tool_counts", {}),
                "remaining_tool_durability": debug.get("remaining_tool_durability", {}),
                "simulation_error": debug.get("simulation_error"),
            },
            "roi_report": roi_report,
        }

    def _merge_subplanner(self, planner, skip_target=None):
        for key, value in planner.recipes.items():
            if key not in self.recipes:
                self.recipes[key] = value
            self.stations_needed.add(value["station"])
        for key, value in planner.gatherables.items():
            if key not in self.gatherables:
                self.gatherables[key] = value
        for key, value in planner.tools_info.items():
            if key not in self.tools_info:
                self.tools_info[key] = value
        for key, value in planner.quantities.items():
            if key != skip_target:
                self.quantities[key] += value

    def _ensure_station_targets(self):
        for station in sorted(self.stations_needed):
            if station == "player" or self.quantities.get(station, 0) > 0:
                continue
            self.quantities[station] = 1
            self._merge_subplanner(SingleItemPlanner(self.api, station, 1), skip_target=station)

    def _inject_wooden_pickaxe_bootstrap(self):
        bootstrap = "wooden_pickaxe"
        if bootstrap in self.injected_tools:
            return
        self.injected_tools.add(bootstrap)
        if self.quantities.get(bootstrap, 0) <= 0:
            self.quantities[bootstrap] += 1
            self.total_durability_required[bootstrap] += 3
            self._merge_subplanner(SingleItemPlanner(self.api, bootstrap, 1), skip_target=bootstrap)
        # Stone pickaxe bootstrap requires mining 3 cobblestone with wooden tier.
        if self.tool_requirements.get("pickaxe", 0) > 0:
            self.tool_requirements["pickaxe"] = max(0, self.tool_requirements["pickaxe"] - 3)

    def _biome_penalty(self, item_name):
        item = normalize_item_name(item_name)
        meta = self.material_meta.get(item, {})
        biomes = [b.lower() for b in meta.get("biomes", ["any"])]
        if "any" in biomes or "forest" in biomes:
            return 0
        if "underground" in biomes:
            return 5
        return 15

    def _build_dependency_graph(self):
        all_items = {
            name
            for name, qty in self.quantities.items()
            if qty > 0 and (name in self.recipes or name in self.gatherables)
        }
        prereqs = {name: set() for name in all_items}
        dependents = {name: set() for name in all_items}
        for item in all_items:
            if item in self.recipes:
                recipe = self.recipes[item]
                for ingredient in recipe["ingredients"]:
                    if ingredient in all_items:
                        if ingredient in self.gatherables and self._can_gather_by_hand(ingredient):
                            continue
                        prereqs[item].add(ingredient)
                if recipe["station"] in all_items:
                    prereqs[item].add(recipe["station"])
                if recipe.get("action") == "smelt":
                    fuel = self.smelt_fuel_plan.get(item, {})
                    fuel_item = fuel.get("fuel_item")
                    if not fuel_item:
                        raise RuntimeError(f"Missing fuel plan for smelt item {item!r}")
                    if fuel_item in all_items:
                        prereqs[item].add(fuel_item)
        recipe_prereqs = self._recipe_prereqs_for_all_recipes()
        for item in sorted(all_items):
            if item not in self.tools_info:
                continue
            tool_type = self._tool_class_for_item(item, self.tools_info[item])
            strat = self.material_gather_strategy.get(item, {})
            primary = strat.get("chosen_method")
            if primary == "hand":
                primary = None
            elif primary and primary not in all_items:
                sel = self.selected_tools.get(tool_type)
                primary = sel if sel and sel in all_items else None
            rule = self._harvest_rule(item)
            min_tier_name = rule.get("min_tier") or "wooden"
            candidates = []
            seen = set()

            def push(name):
                if name and name in all_items and name not in seen:
                    seen.add(name)
                    candidates.append(name)

            prefer_min_first = not bool(rule.get("hand_harvest_allowed", False))
            if prefer_min_first and min_tier_name in TIER_ORDER:
                push(f"{min_tier_name}_{tool_type}")
            if primary:
                push(primary)
            lt = strat.get("local_tier")
            if lt:
                push(f"{lt}_{tool_type}")
            if (not prefer_min_first) and min_tier_name in TIER_ORDER:
                push(f"{min_tier_name}_{tool_type}")
            if not candidates:
                sel = self.selected_tools.get(tool_type)
                push(sel)
            accepted = None
            for cand in candidates:
                if cand == item:
                    continue
                if self._recipe_gather_cycle_blocked(item, cand, recipe_prereqs):
                    continue
                if self._add_prereq_if_acyclic(prereqs, item, cand):
                    accepted = cand
                    break
            if accepted and strat.get("chosen_method") != accepted:
                strat["chosen_method"] = accepted
                self.material_gather_strategy[item] = strat
            if (
                accepted is None
                and strat.get("chosen_method")
                and strat.get("chosen_method") != "hand"
            ):
                self.material_gather_strategy[item] = strat
        for item, deps in prereqs.items():
            for dep in deps:
                dependents[dep].add(item)
        self._assert_prerequisites_acyclic(prereqs)
        return all_items, prereqs, dependents

    def _assert_prerequisites_acyclic(self, prereqs):
        visiting = set()
        visited = set()

        def visit(node):
            if node in visiting:
                raise RuntimeError(f"Dependency cycle involving item {node!r}")
            if node in visited:
                return
            visiting.add(node)
            for dep in prereqs.get(node, ()):
                visit(dep)
            visiting.remove(node)
            visited.add(node)

        for name in prereqs:
            if name not in visited:
                visit(name)

    def sort_and_generate_queue(self):
        self._verify_selected_tool_paths()
        self._reconcile_gather_strategies()
        self._ensure_station_targets()
        all_items, prereqs, dependents = self._build_dependency_graph()
        in_deg = {name: len(prereqs[name]) for name in all_items}
        ready = [name for name in sorted(all_items) if in_deg[name] == 0]
        remaining = {k: v for k, v in self.quantities.items()}
        inventory = defaultdict(int)
        for item, qty in self.exploration_byproducts.items():
            if qty <= 0:
                continue
            inventory[item] += int(qty)
            remaining[item] = max(0, int(remaining.get(item, 0)) - int(qty))
        cached_inventory = defaultdict(int)
        tasks = []
        task_ids = defaultdict(list)
        current_location = "surface_forest"
        batch_index = defaultdict(int)
        blocked_rounds = 0

        while ready:
            progressed = True
            while progressed:
                progressed = False
                for item in list(ready):
                    if remaining.get(item, 0) > 0:
                        continue
                    ready.remove(item)
                    progressed = True
                    for dependent in sorted(dependents[item]):
                        in_deg[dependent] -= 1
                        if in_deg[dependent] == 0:
                            ready.append(dependent)

            if not ready:
                break

            occupied_slots = self._used_slots(inventory)
            withdrew = self._inject_withdraw_from_cache(
                tasks, task_ids, inventory, cached_inventory, remaining, ready, prereqs
            )
            if withdrew:
                blocked_rounds = 0
                continue
            if occupied_slots >= 34:
                tossed = self._inject_garbage_collection(
                    tasks, task_ids, inventory, remaining, ready, prereqs, batch_index
                )
                if tossed:
                    blocked_rounds = 0
                    continue
            if occupied_slots >= 32:
                cached = self._inject_cache_subgraph(
                    tasks, task_ids, inventory, cached_inventory, remaining, ready, prereqs, batch_index
                )
                if cached:
                    blocked_rounds = 0
                    continue

            ready.sort(key=lambda item: self._priority_key(item, current_location, remaining, dependents))
            selected, selected_qty = self._select_next_task(ready, remaining, inventory, dependents, current_location)

            if not selected:
                replenished = self._replenish_missing_inputs(ready, remaining, inventory, prereqs)
                if replenished:
                    blocked_rounds = 0
                    continue
                blocked_rounds += 1
                if blocked_rounds > 1:
                    self._raise_blocked_error(ready, remaining, prereqs)
                cached = self._inject_cache_subgraph(
                    tasks, task_ids, inventory, cached_inventory, remaining, ready, prereqs, batch_index, force=True
                )
                if cached:
                    continue
                self._raise_blocked_error(ready, remaining, prereqs)

            blocked_rounds = 0
            selected_qty = self._cap_bootstrap_hand_gather_qty(selected, selected_qty, ready, remaining, inventory)
            dependencies = self._dependencies_for_selected(selected, prereqs, task_ids)
            node = self._execute_selected_task(
                selected,
                selected_qty,
                inventory,
                remaining,
                dependencies,
                batch_index,
            )
            tasks.append(node)
            task_ids[selected].append(node["task_id"])
            if selected in self.gatherables:
                current_location = get_location(self.gatherables[selected])
            if remaining[selected] <= 0:
                ready.remove(selected)
                for dependent in sorted(dependents[selected]):
                    in_deg[dependent] -= 1
                    if in_deg[dependent] == 0:
                        ready.append(dependent)
        unresolved = sorted(
            [
                item
                for item, qty in remaining.items()
                if qty > 0 and (item in self.recipes or item in self.gatherables)
            ]
        )
        if unresolved:
            detail = [
                {
                    "item": item,
                    "missing": int(remaining[item]),
                    "deps": sorted(prereqs.get(item, set())),
                }
                for item in unresolved[:10]
            ]
            raise RuntimeError(f"Planner ended early with unresolved items: {detail}")

        merged = self._merge_consecutive_tasks(tasks)
        self._assert_task_dependencies_resolved_by_prefix(merged)
        self._assert_blueprint_completion(merged)
        return merged

    def _tool_from_simulation_error(self, message):
        marker = "tool "
        idx = message.find(marker)
        if idx < 0:
            return None
        tail = message[idx + len(marker) :].strip()
        if not tail:
            return None
        token = tail.split(":")[0].strip().strip("'\"")
        return normalize_item_name(token) if token else None

    def _add_tool_copy_for_durability(self, tool_name, copies=1):
        tier = None
        tool_type = None
        for maybe in ("pickaxe", "axe", "shovel", "hoe", "sword"):
            parsed = parse_tier_from_tool_name(tool_name, maybe)
            if parsed:
                tier = parsed
                tool_type = maybe
                break
        if not tier or not tool_type:
            raise UnresolvableQueueError(f"Could not infer tool tier/type from durability failure for {tool_name!r}")
        if tier not in self.tools_flat:
            raise UnresolvableQueueError(f"Missing tier {tier!r} in tools.json for {tool_name!r}")
        copies = int(max(1, copies))
        self.quantities[tool_name] += copies
        self.total_durability_required[tool_name] += int(self.tools_flat[tier]["durability"]) * copies
        self._merge_subplanner(SingleItemPlanner(self.api, tool_name, copies), skip_target=tool_name)
        self.selected_tools[tool_type] = tool_name
        self._ensure_gather_strategies_for_new_quantities()
        self._compute_exploration_byproducts()

    def _required_tool_copies_for_queue(self, queue, tool_name):
        tier = None
        for maybe in ("pickaxe", "axe", "shovel", "hoe", "sword"):
            tier = parse_tier_from_tool_name(tool_name, maybe)
            if tier:
                break
        if not tier:
            raise UnresolvableQueueError(f"Unable to infer tier for {tool_name!r} while sizing tool copies.")
        durability = int(self.tools_flat[tier]["durability"])
        required_uses = 0
        for task in queue:
            if task.get("action") not in {"gather", "mine"}:
                continue
            if task.get("chosen_gather_method") != tool_name:
                continue
            required_uses += int(task.get("durability_cost", task.get("quantity", 0)))
        needed = int(max(1, math.ceil(float(required_uses) / float(durability)))) if required_uses > 0 else 1
        return needed

    def sort_and_generate_queue_strict(self, max_iterations=MAX_ITERATIONS):
        from tests.queue_simulator import simulate_queue

        diagnostics = []
        for iteration in range(1, int(max_iterations) + 1):
            queue = self.sort_and_generate_queue()
            try:
                simulate_queue(queue, self, simulate_durability=True)
                return queue
            except AssertionError as error:
                message = str(error)
                tool = self._tool_from_simulation_error(message)
                diagnostics.append({"iteration": iteration, "error": message, "tool": tool})
                if not tool:
                    raise UnresolvableQueueError(
                        f"Queue invalid at iteration {iteration} and not repairable automatically: {message}"
                    )
                needed_total = self._required_tool_copies_for_queue(queue, tool)
                current_total = int(max(0, self.quantities.get(tool, 0)))
                delta = needed_total - current_total
                if delta <= 0:
                    delta = 1
                self._add_tool_copy_for_durability(tool, copies=delta)
        raise UnresolvableQueueError(
            f"Queue did not stabilize after {int(max_iterations)} iterations. Diagnostics: {diagnostics}"
        )

    def _verify_selected_tool_paths(self):
        for tool_name in sorted(self.selected_tools.values()):
            if self.quantities.get(tool_name, 0) <= 0:
                continue
            if tool_name in self.recipes or tool_name in self.gatherables:
                continue
            raise RuntimeError(f"Selected tool has no production path: {tool_name}")

    def _select_next_task(self, ready, remaining, inventory, dependents, current_location):
        consumption_candidates = []
        gather_candidates = []
        for candidate in ready:
            qty = self._max_executable_qty(candidate, remaining, inventory)
            if qty <= 0:
                continue
            if candidate in self.recipes:
                recipe = self.recipes[candidate]
                freed_slots = self._estimate_slot_delta_for_recipe(candidate, qty, inventory, recipe)
                bootstrap_priority = self._bootstrap_recipe_priority(candidate, remaining)
                consumption_candidates.append((bootstrap_priority, freed_slots, qty, candidate))
            else:
                gather_candidates.append(candidate)
        if consumption_candidates:
            consumption_candidates.sort(key=lambda entry: (-entry[0], -entry[1], -entry[2], entry[3]))
            _bootstrap_priority, _freed_slots, qty, candidate = consumption_candidates[0]
            return candidate, qty
        if gather_candidates:
            immediate = []
            deferred = []
            for candidate in gather_candidates:
                strat = self.material_gather_strategy.get(candidate, {})
                preferred = strat.get("chosen_method", "hand")
                chosen_now = self._select_available_gather_method(candidate, preferred, inventory)
                if preferred != "hand" and chosen_now == "hand" and self._can_gather_by_hand(candidate):
                    deferred.append(candidate)
                else:
                    immediate.append(candidate)
            candidates = immediate if immediate else gather_candidates
            candidates.sort(key=lambda item: self._priority_key(item, current_location, remaining, dependents))
            candidate = candidates[0]
            return candidate, self._max_executable_qty(candidate, remaining, inventory)
        return None, 0

    def _bootstrap_recipe_priority(self, candidate, remaining):
        if remaining.get(candidate, 0) <= 0:
            return 0
        if candidate in self.selected_tools.values():
            return 3
        if candidate in self.stations_needed and candidate != "player":
            return 2
        tool_targets = [t for t in self.selected_tools.values() if remaining.get(t, 0) > 0]
        station_targets = [s for s in self.stations_needed if s != "player" and remaining.get(s, 0) > 0]
        for target in tool_targets + station_targets:
            recipe = self.recipes.get(target)
            if recipe and candidate in recipe.get("ingredients", {}):
                return 1
        return 0

    def _cap_bootstrap_hand_gather_qty(self, selected, selected_qty, ready, remaining, inventory):
        if selected_qty <= 1 or selected not in self.gatherables:
            return selected_qty
        strat = self.material_gather_strategy.get(selected, {})
        preferred = strat.get("chosen_method", "hand")
        if preferred == "hand":
            return selected_qty
        chosen_now = self._select_available_gather_method(selected, preferred, inventory)
        if chosen_now != "hand":
            return selected_qty
        if not self._can_gather_by_hand(selected):
            return selected_qty
        cap = int(selected_qty)
        for item in ready:
            recipe = self.recipes.get(item)
            if not recipe:
                continue
            count = recipe["ingredients"].get(selected)
            if not count or count <= 0:
                continue
            if remaining.get(item, 0) <= 0:
                continue
            shortfall = max(0, int(count) - int(inventory.get(selected, 0)))
            if shortfall > 0:
                cap = min(cap, shortfall)
        if cap < selected_qty:
            return int(max(1, cap))
        return selected_qty

    def _dependencies_for_selected(self, selected, prereqs, task_ids):
        return sorted({task_id for dep in sorted(prereqs[selected]) for task_id in task_ids.get(dep, [])})

    def _select_available_gather_method(self, item, preferred_method, inventory):
        if preferred_method == "hand":
            return "hand"
        tool_info = self.tools_info.get(item, {})
        tool_type = self._tool_class_for_item(item, tool_info)
        rule = self._harvest_rule(item)
        min_tier = rule.get("min_tier") or "wooden"
        min_idx = TIER_ORDER.index(min_tier) if min_tier in TIER_ORDER else 0
        if preferred_method and inventory.get(preferred_method, 0) > 0:
            return preferred_method
        best_tool = None
        best_idx = -1
        suffix = f"_{tool_type}"
        for name, qty in inventory.items():
            if qty <= 0 or not name.endswith(suffix):
                continue
            tier = parse_tier_from_tool_name(name, tool_type)
            if not tier or tier not in TIER_ORDER:
                continue
            tier_idx = TIER_ORDER.index(tier)
            if tier_idx < min_idx or tier_idx <= best_idx:
                continue
            best_idx = tier_idx
            best_tool = name
        if best_tool:
            return best_tool
        if self._can_gather_by_hand(item):
            return "hand"
        return preferred_method

    def _execute_selected_task(self, selected, selected_qty, inventory, remaining, dependencies, batch_index):
        action = "gather"
        station = "player"
        if selected in self.recipes:
            recipe = self.recipes[selected]
            action = recipe["action"]
            station = recipe["station"]
            self._consume_recipe_inputs(inventory, selected, recipe, selected_qty)
        else:
            source = self.gatherables.get(selected, selected)
            if any(x in source for x in ["ore", "stone", "deepslate", "andesite", "diorite", "granite"]):
                action = "mine"
        inventory[selected] += selected_qty
        remaining[selected] -= selected_qty
        batch_index[selected] += 1
        task_id = f"{action}_{selected}_batch_{batch_index[selected]}"
        node = {
            "task_id": task_id,
            "action": action,
            "target": f"minecraft:{selected}",
            "quantity": int(selected_qty),
            "station": station,
            "dependencies": dependencies,
            "status": "pending",
        }
        if selected in self.material_gather_strategy and action in {"gather", "mine"}:
            strat = self.material_gather_strategy[selected]
            preferred_method = strat.get("chosen_method", "hand")
            node["chosen_gather_method"] = self._select_available_gather_method(selected, preferred_method, inventory)
            node["estimated_seconds_saved"] = strat.get("estimated_seconds_saved", 0.0)
        if selected in self.recipes and action in {"craft", "smelt", "strip", "stonecut"}:
            recipe_meta = self.recipes[selected]
            node["selected_recipe_type"] = recipe_meta.get("selected_recipe_type", action)
            node["selected_ingredients"] = dict(
                sorted(recipe_meta.get("selected_ingredients", recipe_meta["ingredients"]).items())
            )
            if action == "smelt":
                fuel_meta = self.smelt_fuel_plan.get(selected)
                if not fuel_meta:
                    raise RuntimeError(f"Missing fuel plan for smelt task {selected!r}")
                fuel_ratio = float(fuel_meta["fuel_ratio_per_output"])
                proportional_fuel = int(max(1, math.ceil(float(selected_qty) * fuel_ratio)))
                node["fuel_item"] = fuel_meta["fuel_item"]
                node["fuel_ratio_per_output"] = round(fuel_ratio, 6)
                node["fuel_quantity"] = proportional_fuel
        heuristic = self._estimate_task_seconds(selected, selected_qty, action)
        if heuristic is not None:
            node["heuristic_seconds"] = round(heuristic, 3)
        if selected in self.total_durability_required:
            node["min_durability_required"] = int(self.total_durability_required[selected])
        elif selected in self.tools_info:
            node["durability_cost"] = int(selected_qty)
        return node

    def _raise_blocked_error(self, ready, remaining, prereqs):
        blocked = []
        for item in ready[:8]:
            blocked.append(
                {
                    "item": item,
                    "missing": int(max(0, remaining.get(item, 0))),
                    "deps": sorted(prereqs.get(item, set())),
                }
            )
        raise RuntimeError(f"Planner blocked by inventory/dependency constraints: {blocked}")

    def _assert_blueprint_completion(self, queue):
        produced = defaultdict(int)
        for item, qty in self.exploration_byproducts.items():
            produced[item] += int(qty)
        for task in queue:
            produced[normalize_item_name(task["target"])] += int(task.get("quantity", 0))
        unmet = []
        for item, required in sorted(self.blueprint_quantities.items()):
            planned = produced.get(item, 0)
            if planned < required:
                unmet.append(
                    {
                        "item": item,
                        "required": int(required),
                        "planned": int(planned),
                        "missing": int(required - planned),
                    }
                )
        if unmet:
            raise RuntimeError(f"Blueprint targets unmet: {unmet}")

    def _assert_task_dependencies_resolved_by_prefix(self, queue):
        index_by_task = {}
        produced_before = defaultdict(int)
        for idx, task in enumerate(queue):
            for dep in task.get("dependencies", []):
                dep_idx = index_by_task.get(dep)
                if dep_idx is None or dep_idx >= idx:
                    raise RuntimeError(
                        f"Task {task['task_id']} has dependency {dep!r} that is not in prior queue prefix."
                    )
            if task.get("action") in {"gather", "mine"}:
                method = task.get("chosen_gather_method")
                if method and method != "hand" and produced_before.get(method, 0) <= 0:
                    raise RuntimeError(
                        f"Task {task['task_id']} requires {method!r} before it is produced by prior tasks."
                    )
            produced_before[normalize_item_name(task["target"])] += int(task.get("quantity", 0))
            index_by_task[task["task_id"]] = idx

    def _estimate_task_seconds(self, item, qty, action, gatherables=None, tools_info=None):
        gp = gatherables if gatherables is not None else self.gatherables
        ti = tools_info if tools_info is not None else self.tools_info
        qty = max(1, int(qty))
        source = gp.get(item, item)
        travel = float(get_travel_cost("surface_forest", get_location(source)))
        gather = 0.0
        if action in {"gather", "mine"}:
            gather = self._break_time_gather_mine(item, qty, gp, ti)
        elif action == "strip":
            recipe = self.recipes.get(item)
            base = next(iter(recipe["ingredients"])) if recipe else item
            h = self._hardness_for_item(base, gp, ti)
            s = max(0.1, self._speed_for_gather_estimate(item))
            gather = float(qty) * h * 1.5 / s
        craft = qty * 0.4 if action == "craft" else 0.0
        smelt = qty * 10.0 if action == "smelt" else 0.0
        fuel = 0.0
        if action == "smelt":
            fuel_items = math.ceil(qty / 8)
            fuel = fuel_items * 4.0
        hint = self._hint_for_item(item)
        rarity_penalty = 0.0
        if hint:
            count = hint.get("count") or 1
            vein = hint.get("vein") or 1
            rarity_penalty = max(0.0, 20.0 / max(1, count * vein))
        return travel + gather + craft + smelt + fuel + rarity_penalty

    def _hint_for_item(self, item):
        token = normalize_item_name(item)
        for name, hint in self.worldgen_hints.items():
            if token in name:
                return {
                    "count": hint.count_per_chunk,
                    "vein": hint.vein_size,
                    "biomes": hint.best_biomes,
                }
        return None

    def _replenish_missing_inputs(self, ready, remaining, inventory, prereqs):
        replenished = False
        for item in ready:
            recipe = self.recipes.get(item)
            if not recipe:
                continue
            desired = remaining.get(item, 0)
            if desired <= 0:
                continue
            crafts = max(1, math.ceil(desired / recipe["yield"]))
            for ingredient, count in recipe["ingredients"].items():
                if count == -1 and ingredient == "coal":
                    needed = max(1, math.ceil(desired / 8))
                else:
                    needed = crafts * count
                shortfall = needed - inventory.get(ingredient, 0)
                if shortfall <= 0:
                    continue
                if ingredient in self.gatherables or ingredient in self.recipes:
                    remaining[ingredient] = max(remaining.get(ingredient, 0), shortfall)
                    deps_ready = all(remaining.get(dep, 0) <= 0 for dep in prereqs.get(ingredient, set()))
                    if ingredient in ready:
                        replenished = True
                    elif deps_ready:
                        ready.append(ingredient)
                        replenished = True
            if recipe.get("action") == "smelt":
                fuel_meta = self.smelt_fuel_plan.get(item)
                if not fuel_meta:
                    raise RuntimeError(f"Missing fuel plan for smelt item {item!r}")
                fuel_item = fuel_meta["fuel_item"]
                fuel_needed = int(max(1, math.ceil(float(desired) * float(fuel_meta["fuel_ratio_per_output"]))))
                fuel_shortfall = fuel_needed - inventory.get(fuel_item, 0)
                if fuel_shortfall > 0 and (fuel_item in self.gatherables or fuel_item in self.recipes):
                    remaining[fuel_item] = max(remaining.get(fuel_item, 0), fuel_shortfall)
                    deps_ready = all(remaining.get(dep, 0) <= 0 for dep in prereqs.get(fuel_item, set()))
                    if fuel_item in ready:
                        replenished = True
                    elif deps_ready:
                        ready.append(fuel_item)
                        replenished = True
        return replenished

    def _priority_key(self, item, current_loc, remaining, dependents):
        source = self.gatherables.get(item, item)
        travel_cost = get_travel_cost(current_loc, get_location(source))
        biome_penalty = self._biome_penalty(item)
        rem = max(1, remaining.get(item, 1))
        if item in self.material_gather_strategy:
            work_score = self._break_time_gather_mine(item, rem)
        else:
            work_score = float(rem)
        return (
            travel_cost + biome_penalty,
            -len(dependents.get(item, [])),
            -work_score,
            item,
        )

    def _estimate_slot_delta_for_recipe(self, item, qty, inventory, recipe):
        before = self._used_slots(inventory)
        simulated = defaultdict(int, inventory)
        self._consume_recipe_inputs(simulated, item, recipe, qty)
        simulated[item] += qty
        after = self._used_slots(simulated)
        return before - after

    def _max_executable_qty(self, item, remaining, inventory):
        desired = remaining.get(item, 0)
        if desired <= 0:
            return 0
        if item in self.recipes:
            recipe = self.recipes[item]
            crafts_for_desired = math.ceil(desired / recipe["yield"])
            craft_bound = crafts_for_desired
            for ingredient, count in recipe["ingredients"].items():
                if count == -1 and ingredient == "coal":
                    needed = max(1, math.ceil(desired / 8))
                    if inventory[ingredient] < needed:
                        return 0
                    continue
                craft_bound = min(craft_bound, inventory[ingredient] // count)
            if recipe.get("action") == "smelt":
                fuel_meta = self.smelt_fuel_plan.get(item)
                if not fuel_meta:
                    raise RuntimeError(f"Missing fuel plan for smelt item {item!r}")
                fuel_item = fuel_meta["fuel_item"]
                fuel_ratio = float(fuel_meta["fuel_ratio_per_output"])
                max_output_by_fuel = int(math.floor(float(inventory[fuel_item]) / fuel_ratio)) if fuel_ratio > 0 else 0
                if max_output_by_fuel <= 0:
                    return 0
                desired = min(desired, max_output_by_fuel)
            if craft_bound <= 0:
                return 0
            desired = min(desired, craft_bound * recipe["yield"])
        fit_qty = self._max_qty_that_fits(item, desired, inventory)
        return max(0, fit_qty)

    def _inject_garbage_collection(self, tasks, task_ids, inventory, remaining, ready, prereqs, batch_index):
        junk_items = []
        protected = self._protected_items(remaining, ready)
        for item, qty in inventory.items():
            if qty <= 0:
                continue
            demand_state = self._future_demand_state(item, remaining)
            if demand_state in {"needed_soon", "needed_later"}:
                continue
            if item not in self.blueprint_required and item not in protected and remaining.get(item, 0) <= 0:
                junk_items.append(item)
        if not junk_items:
            return False
        item = sorted(junk_items)[0]
        qty = inventory[item]
        inventory[item] = 0
        batch_index[item] += 1
        task_id = f"toss_item_{item}_batch_{batch_index[item]}"
        tasks.append(
            {
                "task_id": task_id,
                "action": "toss_item",
                "target": f"minecraft:{item}",
                "quantity": int(qty),
                "station": "player",
                "dependencies": [],
                "status": "pending",
            }
        )
        task_ids[item].append(task_id)
        return True

    def _inject_cache_subgraph(
        self,
        tasks,
        task_ids,
        inventory,
        cached_inventory,
        remaining,
        ready,
        prereqs,
        batch_index,
        force=False,
    ):
        occupied_slots = self._used_slots(inventory)
        if not force and occupied_slots < 32:
            return False

        protected = self._protected_items(remaining, ready)
        for item, qty in inventory.items():
            if qty <= 0:
                continue
            if item.endswith(("_pickaxe", "_axe", "_shovel", "_hoe", "_sword")):
                protected.add(item)
        deposit_plan = {
            item: qty
            for item, qty in inventory.items()
            if qty > 0 and item not in protected
        }
        if force and not deposit_plan:
            # Forced unblocking mode: deposit even protected items to free at least one slot.
            deposit_plan = {item: qty for item, qty in inventory.items() if qty > 0 and item != "chest"}
        if not deposit_plan and not force:
            return False

        cache_dependencies = []
        chest_task_id = None
        if inventory.get("chest", 0) <= 0:
            batch_index["chest"] += 1
            chest_task_id = f"craft_chest_chest_batch_{batch_index['chest']}"
            tasks.append(
                {
                    "task_id": chest_task_id,
                    "action": "craft_chest",
                    "target": "minecraft:chest",
                    "quantity": 1,
                    "station": "player",
                    "dependencies": [],
                    "status": "pending",
                }
            )
            task_ids["chest"].append(chest_task_id)
            cache_dependencies.append(chest_task_id)
        else:
            inventory["chest"] -= 1

        place_task_id = f"place_chest_cache_batch_{len(tasks) + 1}"
        tasks.append(
            {
                "task_id": place_task_id,
                "action": "place_chest",
                "target": "minecraft:chest",
                "quantity": 1,
                "station": "player",
                "dependencies": cache_dependencies,
                "status": "pending",
            }
        )
        deposit_task_id = f"deposit_items_cache_batch_{len(tasks) + 1}"
        tasks.append(
            {
                "task_id": deposit_task_id,
                "action": "deposit_items",
                "target": "minecraft:chest",
                "quantity": int(sum(deposit_plan.values())) if deposit_plan else 0,
                "station": "player",
                "dependencies": [place_task_id],
                "status": "pending",
                "items": dict(sorted(deposit_plan.items())),
            }
        )
        for item, qty in deposit_plan.items():
            cached_inventory[item] = cached_inventory.get(item, 0) + qty
            inventory[item] = 0
        return bool(deposit_plan) or force

    def _inject_withdraw_from_cache(self, tasks, task_ids, inventory, cached_inventory, remaining, ready, prereqs):
        withdraw_plan = {}
        for item in sorted(ready)[:5]:
            if item not in self.recipes:
                continue
            recipe = self.recipes[item]
            desired = remaining.get(item, 0)
            if desired <= 0:
                continue
            crafts = max(1, math.ceil(desired / recipe["yield"]))
            for ingredient, count in recipe["ingredients"].items():
                if count == -1 and ingredient == "coal":
                    needed = max(1, math.ceil(desired / 8))
                else:
                    needed = crafts * count
                shortfall = max(0, needed - inventory.get(ingredient, 0))
                if shortfall > 0 and cached_inventory.get(ingredient, 0) > 0:
                    withdraw_plan[ingredient] = min(shortfall, cached_inventory[ingredient])
        if not withdraw_plan:
            return False
        cache_deps = []
        for existing in reversed(tasks):
            if existing.get("action") in {"deposit_items", "place_chest", "craft_chest"}:
                cache_deps.append(existing["task_id"])
                break
        task_id = f"withdraw_items_cache_batch_{len(tasks) + 1}"
        tasks.append(
            {
                "task_id": task_id,
                "action": "withdraw_items",
                "target": "minecraft:chest",
                "quantity": int(sum(withdraw_plan.values())),
                "station": "player",
                "dependencies": cache_deps,
                "status": "pending",
                "items": dict(sorted(withdraw_plan.items())),
            }
        )
        task_ids["cache_withdraw"].append(task_id)
        for item, qty in withdraw_plan.items():
            cached_inventory[item] -= qty
            inventory[item] += qty
        return True

    def _protected_items(self, remaining, ready):
        protected = set()
        horizon = sorted(ready)[:5]
        for item in horizon:
            protected.add(item)
            if item in self.recipes:
                protected.update(self.recipes[item]["ingredients"].keys())
                station = self.recipes[item].get("station")
                if station and station != "player":
                    protected.add(station)
        for item, qty in remaining.items():
            if qty > 0 and item in self.blueprint_required:
                protected.add(item)
            if qty > 0 and (
                item == "crafting_table"
                or item.endswith("_pickaxe")
                or item.endswith("_axe")
                or item.endswith("_shovel")
                or item.endswith("_hoe")
                or item.endswith("_sword")
                or item == "furnace"
            ):
                protected.add(item)
        protected.update(self.selected_tools.values())
        return protected

    def _future_demand_state(self, item, remaining):
        token = normalize_item_name(item)
        if remaining.get(token, 0) > 0:
            return "needed_soon"
        needed_later = 0
        for product, qty in remaining.items():
            if qty <= 0:
                continue
            recipe = self.recipes.get(product)
            if not recipe:
                continue
            if token in recipe["ingredients"]:
                needed_later += recipe["ingredients"][token]
            station = normalize_item_name(recipe.get("station", "player"))
            if station == token:
                needed_later += 1
        if needed_later > 0:
            return "needed_later"
        return "safe_to_toss"

    def _merge_consecutive_tasks(self, tasks):
        if not tasks:
            return tasks
        merged = [dict(tasks[0])]
        id_remap = {}
        for task in tasks[1:]:
            previous = merged[-1]
            if self._can_merge_tasks(previous, task):
                id_remap[task["task_id"]] = previous["task_id"]
                previous["quantity"] += task["quantity"]
                if "durability_cost" in previous and "durability_cost" in task:
                    previous["durability_cost"] += task["durability_cost"]
                continue
            merged.append(dict(task))
        if id_remap:
            def resolve(task_id):
                cur = task_id
                seen = set()
                while cur in id_remap and cur not in seen:
                    seen.add(cur)
                    cur = id_remap[cur]
                return cur
            for task in merged:
                deps = task.get("dependencies", [])
                if not deps:
                    continue
                task["dependencies"] = [resolve(dep) for dep in deps]
        return merged

    def _can_merge_tasks(self, previous, current):
        same_core = (
            previous["action"] == current["action"]
            and previous["target"] == current["target"]
            and previous["station"] == current["station"]
            and previous.get("dependencies", []) == current.get("dependencies", [])
        )
        if not same_core:
            return False
        for field in ["min_durability_required", "items"]:
            if previous.get(field) != current.get(field):
                return False
        prev_has_durability = "durability_cost" in previous
        curr_has_durability = "durability_cost" in current
        return prev_has_durability == curr_has_durability

    def _consume_recipe_inputs(self, inventory, output_item, recipe, output_qty):
        crafts = math.ceil(output_qty / recipe["yield"])
        for ingredient, count in recipe["ingredients"].items():
            if count == -1 and ingredient == "coal":
                needed = max(1, math.ceil(output_qty / 8))
            else:
                needed = crafts * count
            inventory[ingredient] = max(0, inventory[ingredient] - needed)
        if recipe.get("action") == "smelt":
            fuel_meta = self.smelt_fuel_plan.get(output_item)
            if not fuel_meta:
                raise RuntimeError(f"Missing fuel plan for smelt item {output_item!r}")
            fuel_item = fuel_meta["fuel_item"]
            fuel_needed = int(max(1, math.ceil(float(output_qty) * float(fuel_meta["fuel_ratio_per_output"]))))
            inventory[fuel_item] = max(0, inventory[fuel_item] - fuel_needed)

    def _max_qty_that_fits(self, item, desired_qty, inventory):
        if desired_qty <= 0:
            return 0
        stack_size = max(1, int(self.material_meta.get(item, {}).get("stackSize", DEFAULT_STACK_SIZE)))
        used_slots = self._used_slots(inventory)
        current_qty = inventory[item]
        current_slots = math.ceil(current_qty / stack_size) if current_qty > 0 else 0
        available_slots = SLOT_LIMIT - (used_slots - current_slots)
        return min(desired_qty, available_slots * stack_size)

    def _used_slots(self, inventory):
        slots = 0
        for item, qty in inventory.items():
            if qty <= 0:
                continue
            stack_size = max(1, int(self.material_meta.get(item, {}).get("stackSize", DEFAULT_STACK_SIZE)))
            slots += math.ceil(qty / stack_size)
        return slots


def validate_input(input_data):
    if not isinstance(input_data, list):
        raise ValueError("Input must be a JSON list of {name, quantity} objects.")
    for index, entry in enumerate(input_data):
        if not isinstance(entry, dict):
            raise ValueError(f"Entry {index} must be an object.")
        if "name" not in entry or "quantity" not in entry:
            raise ValueError(f"Entry {index} must include 'name' and 'quantity'.")
        if not isinstance(entry["name"], str) or not entry["name"].strip():
            raise ValueError(f"Entry {index} has invalid 'name'.")
        if not isinstance(entry["quantity"], int) or entry["quantity"] <= 0:
            raise ValueError(f"Entry {index} has invalid 'quantity'; it must be a positive integer.")


def main():
    if len(sys.argv) < 2:
        print("Usage: python planner.py <input_json> [version]")
        sys.exit(1)
    version = sys.argv[2] if len(sys.argv) > 2 else "1.20.1"
    with open(sys.argv[1], "r", encoding="utf-8") as handle:
        input_data = json.load(handle)
    try:
        validate_input(input_data)
    except ValueError as error:
        print(f"Error: {error}", file=sys.stderr)
        sys.exit(1)
    api = MCDataAPI(version)
    planners = []
    for item in input_data:
        try:
            planners.append(SingleItemPlanner(api, item["name"], item["quantity"]))
        except NotImplementedError as error:
            print(f"Error: {error}", file=sys.stderr)
            sys.exit(1)
    global_planner = GlobalPlanner(api, load_material_sources())
    global_planner.merge(planners)
    global_planner.calculate_global_roi()
    queue = global_planner.sort_and_generate_queue_strict()
    print(json.dumps(queue, indent=2))


if __name__ == "__main__":
    main()
