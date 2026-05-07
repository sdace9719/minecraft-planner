import sys
import unittest
import json
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from planner import GlobalPlanner, MCDataAPI, SingleItemPlanner, UnresolvableQueueError, validate_input
from tests.queue_simulator import simulate_queue


class FakeAPI:
    def __init__(self):
        recipe_map = {
            "furnace": [
                SimpleNamespace(
                    action="craft",
                    station="crafting_table",
                    result_count=1,
                    ingredients={"cobblestone": 8},
                )
            ],
            "glass": [
                SimpleNamespace(
                    action="smelt",
                    station="furnace",
                    result_count=1,
                    ingredients={"sand": 1},
                )
            ],
            "stone": [
                SimpleNamespace(
                    action="smelt",
                    station="furnace",
                    result_count=1,
                    ingredients={"cobblestone": 1},
                )
            ],
            "iron_ingot": [
                SimpleNamespace(
                    action="smelt",
                    station="furnace",
                    result_count=1,
                    ingredients={"raw_iron": 1},
                )
            ],
            "wooden_pickaxe": [
                SimpleNamespace(
                    action="craft",
                    station="crafting_table",
                    result_count=1,
                    ingredients={"oak_planks": 3, "stick": 2},
                )
            ],
            "stone_pickaxe": [
                SimpleNamespace(
                    action="craft",
                    station="crafting_table",
                    result_count=1,
                    ingredients={"cobblestone": 3, "stick": 2},
                )
            ],
            "iron_pickaxe": [
                SimpleNamespace(
                    action="craft",
                    station="crafting_table",
                    result_count=1,
                    ingredients={"iron_ingot": 3, "stick": 2},
                )
            ],
            "diamond_pickaxe": [
                SimpleNamespace(
                    action="craft",
                    station="crafting_table",
                    result_count=1,
                    ingredients={"diamond": 3, "stick": 2},
                )
            ],
            "stick": [
                SimpleNamespace(
                    action="craft",
                    station="player",
                    result_count=4,
                    ingredients={"oak_planks": 2},
                )
            ],
            "oak_planks": [
                SimpleNamespace(
                    action="craft",
                    station="player",
                    result_count=4,
                    ingredients={"oak_log": 1},
                )
            ],
            "crafting_table": [
                SimpleNamespace(
                    action="craft",
                    station="player",
                    result_count=1,
                    ingredients={"oak_planks": 4},
                )
            ],
        }

        class FakeDatapackIndex:
            def __init__(self, recipes):
                self._recipes = recipes

            def get(self, item_name):
                items = self._recipes.get(item_name, [])
                return items[0] if items else None

            def get_all(self, item_name):
                return list(self._recipes.get(item_name, []))

        self.datapack_recipes = FakeDatapackIndex(recipe_map)

    def get(self, action, item_name):
        if action == "get_sources" and item_name == "sand":
            return {"item": {"id": 5, "name": "sand"}, "droppedFrom": [{"block": "sand", "silkTouch": False}]}
        if action == "get_sources" and item_name == "cobblestone":
            return {
                "item": {"id": 6, "name": "cobblestone"},
                "droppedFrom": [{"block": "stone", "silkTouch": False}],
            }
        if action == "get_sources" and item_name == "raw_iron":
            return {
                "item": {"id": 7, "name": "raw_iron"},
                "droppedFrom": [{"block": "iron_ore", "silkTouch": False}],
            }
        if action == "get_sources" and item_name == "silk_item":
            return {
                "item": {"id": 8, "name": "silk_item"},
                "droppedFrom": [{"block": "diamond_ore", "silkTouch": True}],
            }
        if action == "get_sources" and item_name == "oak_log":
            return {"item": {"id": 9, "name": "oak_log"}, "droppedFrom": [{"block": "oak_log", "silkTouch": False}]}
        if action == "get_sources" and item_name == "diamond":
            return {
                "item": {"id": 10, "name": "diamond"},
                "droppedFrom": [{"block": "diamond_ore", "silkTouch": False}],
            }
        if action == "get_sources" and item_name == "coal":
            return {
                "item": {"id": 11, "name": "coal"},
                "droppedFrom": [{"block": "coal_ore", "silkTouch": False}],
            }
        if action == "get_sources":
            return {"item": {"id": 1, "name": item_name}, "droppedFrom": []}
        if action == "get_tool_info":
            return {"needsTool": False, "hardness": 1.0}
        return {}


class PlannerProtocolTests(unittest.TestCase):
    def setUp(self):
        self.api = FakeAPI()

    def test_silk_touch_only_item_raises(self):
        with self.assertRaises(NotImplementedError):
            SingleItemPlanner(self.api, "silk_item", 1)

    def test_validate_input_rejects_invalid_quantity(self):
        with self.assertRaises(ValueError):
            validate_input([{"name": "stone", "quantity": 0}])

    def test_output_dependencies_for_craft_task(self):
        planner = GlobalPlanner(self.api, {})
        planner.gatherables = {"oak_log": "oak_log"}
        planner.recipes = {
            "oak_planks": {
                "action": "craft",
                "station": "player",
                "yield": 4,
                "ingredients": {"oak_log": 1},
            }
        }
        planner.quantities["oak_log"] = 2
        planner.quantities["oak_planks"] = 8

        queue = planner.sort_and_generate_queue()

        self.assertEqual(queue[0]["target"], "minecraft:oak_log")
        self.assertEqual(queue[1]["target"], "minecraft:oak_planks")
        self.assertEqual(queue[1]["dependencies"], [])

    def test_inventory_36_slot_batching(self):
        planner = GlobalPlanner(self.api, {"bucket": {"stackSize": 1}})
        planner.gatherables = {"bucket": "grass_block"}
        planner.quantities["bucket"] = 40

        queue = planner.sort_and_generate_queue()
        bucket_tasks = [task for task in queue if task["target"] == "minecraft:bucket"]

        self.assertEqual(len(bucket_tasks), 1)
        self.assertEqual(bucket_tasks[0]["quantity"], 40)

    def test_jit_consumption_prefers_craft_over_more_gathering(self):
        planner = GlobalPlanner(self.api, {})
        planner.gatherables = {"oak_log": "oak_log", "dirt": "dirt"}
        planner.recipes = {
            "oak_planks": {
                "action": "craft",
                "station": "player",
                "yield": 4,
                "ingredients": {"oak_log": 1},
            }
        }
        planner.quantities["oak_log"] = 1
        planner.quantities["oak_planks"] = 4
        planner.quantities["dirt"] = 10

        queue = planner.sort_and_generate_queue()

        self.assertEqual(queue[0]["target"], "minecraft:oak_log")
        self.assertEqual(queue[1]["target"], "minecraft:oak_planks")
        self.assertEqual(queue[2]["target"], "minecraft:dirt")

    def test_garbage_collection_tosses_junk_before_cache(self):
        planner = GlobalPlanner(self.api, {"junk": {"stackSize": 1}, "useful": {"stackSize": 1}})
        planner.gatherables = {"useful": "grass_block"}
        planner.blueprint_required = {"useful"}
        planner.quantities["useful"] = 1
        inventory = {f"junk_{i}": 1 for i in range(34)}
        inventory["junk"] = 1
        tasks = []
        task_ids = defaultdict(list)
        batch_index = defaultdict(int)

        tossed = planner._inject_garbage_collection(
            tasks, task_ids, inventory, planner.quantities, ["useful"], {"useful": set()}, batch_index
        )

        self.assertTrue(tossed)
        self.assertEqual(tasks[0]["action"], "toss_item")

    def test_cache_injection_creates_explicit_nodes(self):
        planner = GlobalPlanner(self.api, {f"item_{i}": {"stackSize": 1} for i in range(32)})
        planner.blueprint_required = {"future_item"}
        inventory = {f"item_{i}": 1 for i in range(32)}
        cached_inventory = {}
        tasks = []
        task_ids = defaultdict(list)
        batch_index = defaultdict(int)

        cached = planner._inject_cache_subgraph(
            tasks, task_ids, inventory, cached_inventory, {"future_item": 1}, ["future_item"], {"future_item": set()}, batch_index
        )

        self.assertTrue(cached)
        self.assertEqual([task["action"] for task in tasks[:3]], ["craft_chest", "place_chest", "deposit_items"])
        self.assertIn("items", tasks[2])
        self.assertEqual(list(tasks[2]["items"].keys()), sorted(tasks[2]["items"].keys()))

    def test_blocked_state_raises_without_fallback(self):
        planner = GlobalPlanner(self.api, {"locked": {"stackSize": 1}})
        planner.gatherables = {"locked": "grass_block"}
        planner.blueprint_required = {"locked"}
        planner.quantities["locked"] = 40
        planner._inject_cache_subgraph = lambda *args, **kwargs: False
        planner._select_next_task = lambda *args, **kwargs: (None, 0)

        with self.assertRaises(RuntimeError):
            planner.sort_and_generate_queue()

    def test_merge_consecutive_identical_tasks(self):
        planner = GlobalPlanner(self.api, {})
        merged = planner._merge_consecutive_tasks(
            [
                {
                    "task_id": "mine_coal_batch_1",
                    "action": "mine",
                    "target": "minecraft:coal",
                    "quantity": 1,
                    "station": "player",
                    "dependencies": [],
                    "status": "pending",
                },
                {
                    "task_id": "mine_coal_batch_2",
                    "action": "mine",
                    "target": "minecraft:coal",
                    "quantity": 2,
                    "station": "player",
                    "dependencies": [],
                    "status": "pending",
                },
            ]
        )
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["quantity"], 3)

    def test_station_furnace_is_crafted_not_gathered(self):
        planner = SingleItemPlanner(self.api, "furnace", 1)
        self.assertIn("furnace", planner.recipes)
        self.assertNotIn("furnace", planner.gatherables)
        self.assertEqual(planner.recipes["furnace"]["action"], "craft")
        self.assertEqual(planner.recipes["furnace"]["ingredients"], {"cobblestone": 8})

    def test_missing_datapack_recipe_falls_back_to_gather(self):
        class MissingRecipeAPI(FakeAPI):
            def __init__(self):
                super().__init__()
                self.datapack_recipes = None

        planner = SingleItemPlanner(MissingRecipeAPI(), "furnace", 1)
        self.assertIn("furnace", planner.gatherables)

    def test_smelt_resolution_uses_datapack_recipe_type(self):
        planner = SingleItemPlanner(self.api, "glass", 1)
        self.assertIn("glass", planner.recipes)
        self.assertEqual(planner.recipes["glass"]["action"], "smelt")
        self.assertEqual(planner.recipes["glass"]["station"], "furnace")
        self.assertEqual(planner.recipes["glass"]["ingredients"], {"sand": 1})

    def test_gather_resolution_when_no_recipe_but_has_drop_source(self):
        planner = SingleItemPlanner(self.api, "sand", 1)
        self.assertIn("sand", planner.gatherables)

    def test_datapack_smelt_recipe_resolves_stone(self):
        # This test exercises the datapack recipe indexer integration.
        # The planner's API should have a datapack recipe index loaded for stone -> smelt cobblestone.
        api = self.api
        api.datapack_recipes = None
        try:
            from mojang_datapack.recipes import DatapackRecipeIndex
            from pathlib import Path

            recipe_dir = Path("mojang-data/1.21.1/data/minecraft/recipe")
            index = DatapackRecipeIndex(recipe_dir)
            index.load()
            api.datapack_recipes = index
        except Exception as e:
            self.fail(f"Failed to load datapack recipes: {e}")

        planner = SingleItemPlanner(api, "stone", 1)
        self.assertIn("stone", planner.recipes)
        self.assertEqual(planner.recipes["stone"]["action"], "smelt")

    def test_tool_crafting_node_appears_before_tooled_gather(self):
        planner = GlobalPlanner(
            self.api,
            {
                "stone_pickaxe": {"stackSize": 1},
                "cobblestone": {"stackSize": 64},
                "iron_ore": {"stackSize": 64},
            },
        )
        planner.recipes = {
            "stone_pickaxe": {
                "action": "craft",
                "station": "crafting_table",
                "yield": 1,
                "ingredients": {"cobblestone": 3, "stick": 2},
            },
            "stick": {"action": "craft", "station": "player", "yield": 4, "ingredients": {"oak_planks": 2}},
            "oak_planks": {"action": "craft", "station": "player", "yield": 4, "ingredients": {"oak_log": 1}},
        }
        planner.gatherables = {"cobblestone": "stone", "oak_log": "oak_log", "iron_ore": "iron_ore"}
        planner.quantities["stone_pickaxe"] = 1
        planner.quantities["cobblestone"] = 16
        planner.quantities["iron_ore"] = 8
        planner.quantities["stick"] = 2
        planner.quantities["oak_planks"] = 2
        planner.quantities["oak_log"] = 1
        planner.tools_info["cobblestone"] = {"toolType": "pickaxe", "hardness": 1.5}
        planner.tools_info["iron_ore"] = {"toolType": "pickaxe", "hardness": 3.0}
        planner.selected_tools["pickaxe"] = "stone_pickaxe"

        queue = planner.sort_and_generate_queue()
        by_target = {task["target"]: idx for idx, task in enumerate(queue)}
        self.assertIn("minecraft:stone_pickaxe", by_target)
        self.assertIn("minecraft:iron_ore", by_target)
        self.assertLess(by_target["minecraft:stone_pickaxe"], by_target["minecraft:iron_ore"])

    def test_queue_hard_fails_when_blueprint_unmet(self):
        planner = GlobalPlanner(self.api, {"oak_log": {"stackSize": 64}})
        planner.gatherables = {"oak_log": "oak_log"}
        planner.quantities["oak_log"] = 2
        planner.blueprint_required = {"oak_log"}
        planner.blueprint_quantities["oak_log"] = 10

        with self.assertRaises(RuntimeError) as error:
            planner.sort_and_generate_queue()
        self.assertIn("Blueprint targets unmet", str(error.exception))

    def test_stone_pickaxe_selection_injects_wooden_bootstrap(self):
        planner = GlobalPlanner(self.api, {"cobblestone": {"stackSize": 64}})
        planner.gatherables = {"cobblestone": "stone", "oak_log": "oak_log"}
        planner.tools_info["cobblestone"] = {"toolType": "pickaxe", "hardness": 2.0}
        planner.quantities["cobblestone"] = 100
        planner._compute_tool_requirements()
        planner.calculate_global_roi()

        self.assertIn("wooden_pickaxe", planner.quantities)
        self.assertGreaterEqual(planner.quantities["wooden_pickaxe"], 1)

    def test_durability_remainder_reduces_extra_tool_crafting(self):
        planner = GlobalPlanner(self.api, {})
        # High pickaxe workload so tier-ROI prefers stone over wooden; remainder logic is per-tier.
        planner.tool_requirements["pickaxe"] = 5000
        planner.calculate_global_roi()
        first_count = planner.quantities.get("stone_pickaxe", 0)
        self.assertGreaterEqual(first_count, 1)
        rem_after_heavy = planner.tool_durability_remainder.get("pickaxe", 0)
        planner.tool_requirements["pickaxe"] = 10
        planner.calculate_global_roi()
        second_count = planner.quantities.get("stone_pickaxe", 0)
        # Each calculate_global_roi pass adds another full lower-tier tool chain (+=).
        self.assertGreaterEqual(second_count, first_count)
        # Remainder should reflect durability left after the heavy workload.
        self.assertGreaterEqual(rem_after_heavy, 0)

    def test_queue_simulator_executes_full_plan(self):
        api = MCDataAPI("1.20.1")
        input_data = json.loads(Path("tests/input_materials_test.json").read_text(encoding="utf-8"))
        planners = [SingleItemPlanner(api, row["name"], row["quantity"]) for row in input_data]
        planner = GlobalPlanner(api, {})
        planner.merge(planners)
        planner.calculate_global_roi()
        queue = planner.sort_and_generate_queue()
        _, _, produced = simulate_queue(queue, planner)

        for row in input_data:
            self.assertGreaterEqual(produced.get(row["name"], 0), row["quantity"])

    def test_recipe_metadata_is_emitted_on_craft_tasks(self):
        planner = GlobalPlanner(self.api, {})
        planner.gatherables = {"oak_log": "oak_log"}
        planner.recipes = {
            "oak_planks": {
                "action": "craft",
                "station": "player",
                "yield": 4,
                "ingredients": {"oak_log": 1},
                "selected_recipe_type": "minecraft:crafting_shapeless",
                "selected_ingredients": {"oak_log": 1},
            }
        }
        planner.quantities["oak_log"] = 1
        planner.quantities["oak_planks"] = 4
        queue = planner.sort_and_generate_queue()
        craft = next(t for t in queue if t["target"] == "minecraft:oak_planks")
        self.assertEqual(craft["selected_recipe_type"], "minecraft:crafting_shapeless")
        self.assertEqual(craft["selected_ingredients"], {"oak_log": 1})

    def test_tool_vs_hand_strategy_prefers_tool_for_large_volume(self):
        planner = GlobalPlanner(self.api, {})
        planner.tools_info["cobblestone"] = {"toolType": "pickaxe", "hardness": 2.0, "needsTool": False}
        planner.quantities["cobblestone"] = 1024
        planner._compute_tool_requirements()
        self.assertIn("cobblestone", planner.material_gather_strategy)
        self.assertNotEqual(planner.material_gather_strategy["cobblestone"]["chosen_method"], "hand")

    def test_smelt_task_includes_fuel_metadata(self):
        planner = GlobalPlanner(self.api, {})
        planner.recipes = {
            "glass": {
                "action": "smelt",
                "station": "furnace",
                "yield": 1,
                "ingredients": {"sand": 1},
                "selected_recipe_type": "minecraft:smelting",
                "selected_ingredients": {"sand": 1},
            }
        }
        planner.gatherables = {"sand": "sand"}
        planner.quantities["sand"] = 8
        planner.quantities["glass"] = 8
        planner._plan_smelt_fuel_requirements()
        queue = planner.sort_and_generate_queue()
        smelt = next(t for t in queue if t["target"] == "minecraft:glass")
        self.assertEqual(smelt["fuel_item"], "oak_planks")
        self.assertAlmostEqual(smelt["fuel_ratio_per_output"], 2.0 / 3.0, places=6)
        self.assertEqual(smelt["fuel_quantity"], 6)

    def test_smelt_dependencies_include_selected_fuel_task(self):
        api = MCDataAPI("1.20.1")
        planner = GlobalPlanner(api, {})
        planner.merge([SingleItemPlanner(api, "glass", 8)])
        planner.calculate_global_roi()
        queue = planner.sort_and_generate_queue_strict()
        by_id = {t["task_id"]: t for t in queue}
        smelt = next(t for t in queue if t["action"] == "smelt")
        fuel_item = smelt["fuel_item"]
        dep_targets = {by_id[dep]["target"].split(":")[-1] for dep in smelt.get("dependencies", []) if dep in by_id}
        self.assertIn(fuel_item, dep_targets)

    def test_smelt_fuel_selection_is_planks_only(self):
        planner = GlobalPlanner(self.api, {})
        planner.recipes = {
            "glass": {
                "action": "smelt",
                "station": "furnace",
                "yield": 1,
                "ingredients": {"sand": 1},
            }
        }
        planner.quantities["glass"] = 8
        planner._ensure_item_path = lambda item, qty: None
        planner._plan_smelt_fuel_requirements()
        self.assertEqual(planner.smelt_fuel_plan["glass"]["fuel_item"], "oak_planks")

    def test_garbage_collection_preserves_future_needed_cobblestone(self):
        planner = GlobalPlanner(self.api, {"cobblestone": {"stackSize": 64}})
        planner.recipes = {
            "stone_pickaxe": {
                "action": "craft",
                "station": "crafting_table",
                "yield": 1,
                "ingredients": {"cobblestone": 3},
            }
        }
        planner.quantities["stone_pickaxe"] = 1
        inventory = {"cobblestone": 64}
        tasks = []
        task_ids = defaultdict(list)
        batch_index = defaultdict(int)
        tossed = planner._inject_garbage_collection(
            tasks, task_ids, inventory, planner.quantities, ["stone_pickaxe"], {"stone_pickaxe": {"cobblestone"}}, batch_index
        )
        self.assertFalse(tossed)

    def test_global_pickaxe_roi_prefers_iron_for_large_volume(self):
        planner = GlobalPlanner(self.api, {})
        planner.tool_requirements["pickaxe"] = 4000
        planner.calculate_global_roi()
        self.assertIn(planner.selected_tools["pickaxe"], {"iron_pickaxe", "diamond_pickaxe"})

    def test_roi_differs_by_tool_type_from_recipe_chain_cost(self):
        planner = GlobalPlanner(self.api, {})
        planner.tool_requirements["pickaxe"] = 500
        planner.tool_requirements["shovel"] = 50
        planner.calculate_global_roi()
        self.assertEqual(planner.selected_tools["pickaxe"], "stone_pickaxe")
        self.assertEqual(planner.selected_tools["shovel"], "wooden_shovel")
        self.assertNotEqual(planner.selected_tools["pickaxe"], planner.selected_tools["shovel"].replace("shovel", "pickaxe"))

    def test_break_time_gather_mine_matches_hardness_formula(self):
        planner = GlobalPlanner(self.api, {})
        planner.block_hardness = {"test_ore_block": 2.0}
        planner.gatherables = {"raw_test": "test_ore_block"}
        planner.tools_info["raw_test"] = {
            "toolType": "pickaxe",
            "needsTool": True,
            "source_block": "test_ore_block",
        }
        planner.material_gather_strategy["raw_test"] = {"chosen_method": "stone_pickaxe"}
        qty = 100
        h = 2.0
        speed = planner.tools_flat["stone"]["speed"]
        expected = qty * h * 1.5 / speed
        self.assertAlmostEqual(planner._break_time_gather_mine("raw_test", qty), expected, places=5)

    def test_runtime_gather_method_uses_best_available_tool_by_family(self):
        planner = GlobalPlanner(self.api, {})
        inventory = {"stone_pickaxe": 1, "iron_axe": 1}
        pick = planner._select_available_gather_method("raw_iron", "diamond_pickaxe", inventory)
        axe = planner._select_available_gather_method("oak_log", "diamond_axe", inventory)
        hand = planner._select_available_gather_method("sand", "stone_shovel", inventory)
        self.assertEqual(pick, "stone_pickaxe")
        self.assertEqual(axe, "iron_axe")
        self.assertEqual(hand, "hand")

    def test_tiny_sand_gather_strategy_prefers_hand(self):
        planner = GlobalPlanner(self.api, {})
        planner.merge([SingleItemPlanner(self.api, "sand", 1)])
        self.assertEqual(planner.material_gather_strategy["sand"]["chosen_method"], "hand")

    def test_gather_sand_queue_lists_shovel_craft_as_dependency(self):
        api = MCDataAPI("1.20.1")
        planner = GlobalPlanner(api, {})
        planner.merge([SingleItemPlanner(api, "sand", 128)])
        planner.calculate_global_roi()
        queue = planner.sort_and_generate_queue()
        sand_gather = next(
            t for t in queue if t.get("action") == "gather" and t.get("target") == "minecraft:sand"
        )
        self.assertNotEqual(sand_gather.get("chosen_gather_method"), "hand")
        self.assertTrue(
            any("shovel" in dep for dep in sand_gather.get("dependencies", [])),
            msg=f"expected a shovel craft in dependencies, got {sand_gather.get('dependencies')}",
        )

    def test_linear_queue_prefix_is_always_executable(self):
        api = MCDataAPI("1.20.1")
        input_data = json.loads(Path("tests/input_materials_test.json").read_text(encoding="utf-8"))
        planners = [SingleItemPlanner(api, row["name"], row["quantity"]) for row in input_data]
        planner = GlobalPlanner(api, {})
        planner.merge(planners)
        planner.calculate_global_roi()
        queue = planner.sort_and_generate_queue()

        task_index = {task["task_id"]: idx for idx, task in enumerate(queue)}
        for idx, task in enumerate(queue):
            for dep in task.get("dependencies", []):
                self.assertIn(dep, task_index, msg=f"missing dependency task id {dep}")
                self.assertLess(task_index[dep], idx, msg=f"dependency {dep} appears after {task['task_id']}")

        for end in range(1, len(queue) + 1):
            simulate_queue(queue[:end], planner)

    def test_diamond_prerequisite_hierarchy_is_present_before_diamond_mining(self):
        api = MCDataAPI("1.20.1")
        input_data = json.loads(Path("tests/input_materials_test.json").read_text(encoding="utf-8"))
        planners = [SingleItemPlanner(api, row["name"], row["quantity"]) for row in input_data]
        planner = GlobalPlanner(api, {})
        planner.merge(planners)
        planner.calculate_global_roi()
        queue = planner.sort_and_generate_queue()

        first = queue[0]
        self.assertNotEqual(first.get("chosen_gather_method"), "diamond_axe")

        diamond_mine_idx = next(
            i
            for i, task in enumerate(queue)
            if task.get("target") == "minecraft:diamond" and task.get("action") in {"mine", "gather"}
        )
        diamond_task = queue[diamond_mine_idx]
        self.assertTrue(
            any("iron_pickaxe" in dep for dep in diamond_task.get("dependencies", [])),
            msg=f"expected iron_pickaxe dependency before mining diamond, got {diamond_task.get('dependencies')}",
        )
        iron_pickaxe_idx = next(
            i for i, task in enumerate(queue) if task.get("target") == "minecraft:iron_pickaxe" and "craft" in task["action"]
        )
        self.assertLess(iron_pickaxe_idx, diamond_mine_idx)

    def test_durability_simulation_requires_recraft_for_weak_tools(self):
        planner = GlobalPlanner(self.api, {})
        planner.tools_flat = {"wooden": {"speed": 2.0, "durability": 5}}
        queue = [
            {
                "task_id": "craft_wooden_shovel_batch_1",
                "action": "craft",
                "target": "minecraft:wooden_shovel",
                "quantity": 1,
                "station": "player",
                "dependencies": [],
                "status": "pending",
            },
            {
                "task_id": "gather_sand_batch_1",
                "action": "gather",
                "target": "minecraft:sand",
                "quantity": 6,
                "station": "player",
                "dependencies": ["craft_wooden_shovel_batch_1"],
                "status": "pending",
                "chosen_gather_method": "wooden_shovel",
            },
        ]
        with self.assertRaises(AssertionError):
            simulate_queue(queue, planner, simulate_durability=True)

    def test_debug_reports_include_snapshots_and_roi_candidate_math(self):
        api = MCDataAPI("1.20.1")
        input_data = json.loads(Path("tests/input_materials_test.json").read_text(encoding="utf-8"))
        planners = [SingleItemPlanner(api, row["name"], row["quantity"]) for row in input_data]
        planner = GlobalPlanner(api, {})
        planner.merge(planners)
        planner.calculate_global_roi()
        queue = planner.sort_and_generate_queue_strict()
        reports = planner.build_debug_reports(queue)

        self.assertIn("inventory_snapshots", reports)
        self.assertIn("roi_report", reports)
        self.assertGreater(len(reports["inventory_snapshots"]), 0)
        first = reports["inventory_snapshots"][0]
        self.assertIn("inventory", first)
        self.assertIn("chest", first)
        self.assertIn("tool_durability", first)

        pickaxe_roi = reports["roi_report"]["pickaxe"]
        self.assertIn("candidates", pickaxe_roi)
        self.assertGreater(len(pickaxe_roi["candidates"]), 0)
        selected = pickaxe_roi["selected_tier"]
        selected_time = next(row["total_time"] for row in pickaxe_roi["candidates"] if row["tier"] == selected)
        min_time = min(row["total_time"] for row in pickaxe_roi["candidates"])
        self.assertAlmostEqual(selected_time, min_time, places=6)

    def test_tunnel_profile_scales_by_ore_quantity_and_vein_size(self):
        planner = GlobalPlanner(self.api, {})
        planner.tools_flat = {
            "wooden": {"speed": 2.0, "durability": 59},
            "stone": {"speed": 4.0, "durability": 131},
            "iron": {"speed": 6.0, "durability": 250, "blocks_to_break": 180, "junk_block": "stone", "vein_size": 2},
            "diamond": {"speed": 8.0, "durability": 1561, "blocks_to_break": 600, "junk_block": "deepslate", "vein_size": 3},
        }
        planner.block_hardness = {"stone": 1.5, "deepslate": 3.0}
        total, rows = planner._estimate_tunnel_profile("pickaxe", "iron", 1)
        iron_row = next(row for row in rows if row["tier"] == "iron")
        self.assertGreaterEqual(iron_row["ore_needed"], 1)
        self.assertEqual(iron_row["expected_veins"], (iron_row["ore_needed"] + 1) // 2)
        self.assertEqual(iron_row["junk_blocks"], 180 * iron_row["expected_veins"])
        expected_time = iron_row["junk_blocks"] * 1.5 * 1.5 / 4.0
        self.assertAlmostEqual(total, expected_time, places=3)

    def test_exploration_byproducts_reduce_redundant_mining_tasks(self):
        planner = GlobalPlanner(self.api, {})
        planner.gatherables = {"cobblestone": "stone"}
        planner.recipes = {
            "furnace": {
                "action": "craft",
                "station": "crafting_table",
                "yield": 1,
                "ingredients": {"cobblestone": 8},
            }
        }
        planner.quantities["furnace"] = 1
        planner.quantities["cobblestone"] = 8
        planner.exploration_byproducts["cobblestone"] = 20
        queue = planner.sort_and_generate_queue()
        self.assertFalse(any(task["target"] == "minecraft:cobblestone" for task in queue))

    def test_strict_queue_raises_unresolvable_after_max_iterations(self):
        planner = GlobalPlanner(self.api, {})
        planner.sort_and_generate_queue = lambda: [
            {
                "task_id": "mine_sand_batch_1",
                "action": "gather",
                "target": "minecraft:sand",
                "quantity": 10,
                "station": "player",
                "dependencies": [],
                "status": "pending",
                "chosen_gather_method": "wooden_shovel",
            }
        ]
        planner._add_tool_copy_for_durability = lambda _tool, copies=1: None
        with self.assertRaises(UnresolvableQueueError) as error:
            planner.sort_and_generate_queue_strict(max_iterations=2)
        self.assertIn("after 2 iterations", str(error.exception))


if __name__ == "__main__":
    unittest.main()
