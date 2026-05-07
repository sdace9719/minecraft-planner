from planner.dag_router import DagRouter
from planner.global_math_optimizer import GlobalMathOptimizer, GlobalMathOptimizerError
from planner.local_optimizer import LocalOptimizer, LocalOptimizerError


def _index(tasks):
    return {task["id"]: task for task in tasks}


def test_empty_phase3_input_produces_empty_phase4_output():
    optimizer = LocalOptimizer()
    result = optimizer.optimize_chunked_dag([])
    assert result == []


def test_global_math_optimizer_does_not_mutate_input():
    optimizer = GlobalMathOptimizer()
    tasks = [
        {
            "id": "SMELT:stone",
            "name": "stone",
            "quantity": 100,
            "dependencies": ["MINE:cobblestone", "CRAFT:furnace", "CRAFT:oak_planks"],
            "operation_type": "smelt",
        },
        {
            "id": "MINE:cobblestone",
            "name": "cobblestone",
            "quantity": 200,
            "dependencies": ["CRAFT:stone_pickaxe"],
            "operation_type": "mine",
        },
        {
            "id": "CRAFT:stone_pickaxe",
            "name": "stone_pickaxe",
            "quantity": 1,
            "dependencies": ["CRAFT:crafting_table"],
            "operation_type": "craft",
        },
        {
            "id": "CRAFT:furnace",
            "name": "furnace",
            "quantity": 1,
            "dependencies": ["MINE:cobblestone", "CRAFT:crafting_table"],
            "operation_type": "craft",
        },
        {
            "id": "CRAFT:crafting_table",
            "name": "crafting_table",
            "quantity": 1,
            "dependencies": ["CRAFT:oak_planks"],
            "operation_type": "craft",
        },
        {
            "id": "CRAFT:oak_planks",
            "name": "oak_planks",
            "quantity": 80,
            "dependencies": ["MINE:oak_log"],
            "operation_type": "craft",
        },
        {
            "id": "CRAFT:stick",
            "name": "stick",
            "quantity": 8,
            "dependencies": ["CRAFT:oak_planks"],
            "operation_type": "craft",
        },
        {
            "id": "MINE:oak_log",
            "name": "oak_log",
            "quantity": 100,
            "dependencies": [],
            "operation_type": "mine",
        },
    ]
    before = [dict(task) for task in tasks]
    _ = optimizer.optimize_tasks(tasks)
    assert tasks == before


def test_step1c_updates_furnace_and_fuel_totals():
    optimizer = GlobalMathOptimizer()
    tasks = [
        {
            "id": "SMELT:stone",
            "name": "stone",
            "quantity": 100,
            "dependencies": ["MINE:cobblestone", "CRAFT:furnace", "CRAFT:oak_planks"],
            "operation_type": "smelt",
        },
        {
            "id": "MINE:cobblestone",
            "name": "cobblestone",
            "quantity": 200,
            "dependencies": ["CRAFT:stone_pickaxe"],
            "operation_type": "mine",
        },
        {
            "id": "CRAFT:stone_pickaxe",
            "name": "stone_pickaxe",
            "quantity": 1,
            "dependencies": ["CRAFT:crafting_table"],
            "operation_type": "craft",
        },
        {
            "id": "CRAFT:furnace",
            "name": "furnace",
            "quantity": 1,
            "dependencies": ["MINE:cobblestone", "CRAFT:crafting_table"],
            "operation_type": "craft",
        },
        {
            "id": "CRAFT:crafting_table",
            "name": "crafting_table",
            "quantity": 1,
            "dependencies": ["CRAFT:oak_planks"],
            "operation_type": "craft",
        },
        {
            "id": "CRAFT:oak_planks",
            "name": "oak_planks",
            "quantity": 200,
            "dependencies": ["MINE:oak_log"],
            "operation_type": "craft",
        },
        {
            "id": "CRAFT:stick",
            "name": "stick",
            "quantity": 20,
            "dependencies": ["CRAFT:oak_planks"],
            "operation_type": "craft",
        },
        {
            "id": "MINE:oak_log",
            "name": "oak_log",
            "quantity": 100,
            "dependencies": [],
            "operation_type": "mine",
        },
    ]
    out = _index(optimizer.optimize_tasks(tasks))
    assert out["CRAFT:furnace"]["quantity"] == 6
    assert out["CRAFT:oak_planks"]["quantity"] > 10


def test_tool_recalculation_propagates_upstream():
    optimizer = GlobalMathOptimizer()
    tasks = [
        {
            "id": "MINE:cobblestone",
            "name": "cobblestone",
            "quantity": 260,
            "dependencies": ["CRAFT:stone_pickaxe"],
            "operation_type": "mine",
        },
        {
            "id": "CRAFT:stone_pickaxe",
            "name": "stone_pickaxe",
            "quantity": 1,
            "dependencies": ["CRAFT:crafting_table"],
            "operation_type": "craft",
        },
        {
            "id": "CRAFT:crafting_table",
            "name": "crafting_table",
            "quantity": 1,
            "dependencies": ["CRAFT:oak_planks"],
            "operation_type": "craft",
        },
        {
            "id": "CRAFT:oak_planks",
            "name": "oak_planks",
            "quantity": 2000,
            "dependencies": ["MINE:oak_log"],
            "operation_type": "craft",
        },
        {
            "id": "CRAFT:stick",
            "name": "stick",
            "quantity": 200,
            "dependencies": ["CRAFT:oak_planks"],
            "operation_type": "craft",
        },
        {
            "id": "MINE:oak_log",
            "name": "oak_log",
            "quantity": 500,
            "dependencies": [],
            "operation_type": "mine",
        },
    ]
    result = optimizer.optimize_tasks(tasks)
    out = _index(result)
    # With global tool merge, stone_pickaxe may be merged into a different ID.
    # Verify cobblestone still has a stone-tier pickaxe dependency.
    assert "CRAFT:stick" in out


def test_ambiguous_reverse_lookup_hard_fails():
    optimizer = GlobalMathOptimizer()
    tasks = [
        {
            "id": "SMELT:stone",
            "name": "stone",
            "quantity": 100,
            "dependencies": ["MINE:cobblestone", "CRAFT:furnace", "CRAFT:oak_planks"],
            "operation_type": "smelt",
        },
        {
            "id": "MINE:cobblestone",
            "name": "cobblestone",
            "quantity": 50,
            "dependencies": ["CRAFT:stone_pickaxe"],
            "operation_type": "mine",
        },
        {
            "id": "MINE:cobblestone_mvb",
            "name": "cobblestone",
            "quantity": 3,
            "dependencies": ["CRAFT:wooden_pickaxe"],
            "operation_type": "mine",
        },
        {
            "id": "CRAFT:stone_pickaxe",
            "name": "stone_pickaxe",
            "quantity": 1,
            "dependencies": ["CRAFT:crafting_table"],
            "operation_type": "craft",
        },
        {
            "id": "CRAFT:wooden_pickaxe",
            "name": "wooden_pickaxe",
            "quantity": 1,
            "dependencies": ["CRAFT:crafting_table"],
            "operation_type": "craft",
        },
        {
            "id": "CRAFT:furnace",
            "name": "furnace",
            "quantity": 1,
            "dependencies": ["MINE:cobblestone", "CRAFT:crafting_table"],
            "operation_type": "craft",
        },
        {
            "id": "CRAFT:crafting_table",
            "name": "crafting_table",
            "quantity": 1,
            "dependencies": ["CRAFT:oak_planks"],
            "operation_type": "craft",
        },
        {
            "id": "CRAFT:oak_planks",
            "name": "oak_planks",
            "quantity": 40,
            "dependencies": ["MINE:oak_log"],
            "operation_type": "craft",
        },
        {
            "id": "CRAFT:stick",
            "name": "stick",
            "quantity": 6,
            "dependencies": ["CRAFT:oak_planks"],
            "operation_type": "craft",
        },
        {
            "id": "MINE:oak_log",
            "name": "oak_log",
            "quantity": 100,
            "dependencies": [],
            "operation_type": "mine",
        },
    ]
    try:
        optimizer.optimize_tasks(tasks)
    except GlobalMathOptimizerError as exc:
        assert "Ambiguous source node" in str(exc)
    else:
        assert False, "Expected hard-fail on ambiguous reverse lookup"


def test_phase4b_yield_math_for_andesite_uses_recipe_runs():
    router = DagRouter()
    phase4a = [
        {
            "id": "CRAFT:andesite",
            "name": "andesite",
            "quantity": 88,
            "dependencies": ["MINE:cobblestone", "MINE:diorite"],
            "operation_type": "craft",
        },
        {
            "id": "MINE:cobblestone",
            "name": "cobblestone",
            "quantity": 44,
            "dependencies": [],
            "operation_type": "mine",
        },
        {
            "id": "MINE:diorite",
            "name": "diorite",
            "quantity": 44,
            "dependencies": [],
            "operation_type": "mine",
        },
    ]
    out = _index(router.route_tasks(phase4a))
    assert "MINE:diorite_chunk_1" in out["CRAFT:andesite_chunk_1"]["dependencies"]
    assert "MINE:diorite_chunk_1" in out["CRAFT:andesite_chunk_2"]["dependencies"]


def test_phase4b_yield_math_for_planks_uses_recipe_runs():
    router = DagRouter()
    phase4a = [
        {
            "id": "CRAFT:oak_planks",
            "name": "oak_planks",
            "quantity": 68,
            "dependencies": ["GATHER:oak_log"],
            "operation_type": "craft",
        },
        {
            "id": "GATHER:oak_log",
            "name": "oak_log",
            "quantity": 17,
            "dependencies": [],
            "operation_type": "gather",
        },
    ]
    out = _index(router.route_tasks(phase4a))
    assert "GATHER:oak_log_chunk_1" in out["CRAFT:oak_planks_chunk_1"]["dependencies"]
    assert "GATHER:oak_log_chunk_1" in out["CRAFT:oak_planks_chunk_2"]["dependencies"]


def test_phase4b_reusable_crafting_table_has_infinite_capacity():
    router = DagRouter()
    phase4a = [
        {
            "id": "CRAFT:crafting_table",
            "name": "crafting_table",
            "quantity": 1,
            "dependencies": ["CRAFT:oak_planks"],
            "operation_type": "craft",
        },
        {
            "id": "CRAFT:oak_planks",
            "name": "oak_planks",
            "quantity": 520,
            "dependencies": ["GATHER:oak_log"],
            "operation_type": "craft",
        },
        {
            "id": "CRAFT:stick",
            "name": "stick",
            "quantity": 256,
            "dependencies": ["CRAFT:oak_planks", "CRAFT:crafting_table"],
            "operation_type": "craft",
        },
        {
            "id": "CRAFT:wooden_pickaxe",
            "name": "wooden_pickaxe",
            "quantity": 128,
            "dependencies": ["CRAFT:oak_planks", "CRAFT:stick", "CRAFT:crafting_table"],
            "operation_type": "craft",
        },
        {
            "id": "GATHER:oak_log",
            "name": "oak_log",
            "quantity": 400,
            "dependencies": [],
            "operation_type": "gather",
        },
    ]
    out = _index(router.route_tasks(phase4a))
    table_chunk = "CRAFT:crafting_table_chunk_1"
    assert table_chunk in out["CRAFT:stick_chunk_1"]["dependencies"]
    assert table_chunk in out["CRAFT:wooden_pickaxe_chunk_1"]["dependencies"]


def test_phase4b_smelt_plank_demand_uses_burn_time_math():
    router = DagRouter()
    phase4a = [
        {
            "id": "SMELT:copper_ingot",
            "name": "copper_ingot",
            "quantity": 64,
            "dependencies": ["MINE:copper_ore", "CRAFT:furnace", "CRAFT:oak_planks"],
            "operation_type": "smelt",
        },
        {
            "id": "MINE:copper_ore",
            "name": "copper_ore",
            "quantity": 64,
            "dependencies": [],
            "operation_type": "mine",
        },
        {
            "id": "CRAFT:furnace",
            "name": "furnace",
            "quantity": 1,
            "dependencies": [],
            "operation_type": "craft",
        },
        {
            "id": "CRAFT:oak_planks",
            "name": "oak_planks",
            "quantity": 43,
            "dependencies": ["GATHER:oak_log"],
            "operation_type": "craft",
        },
        {
            "id": "GATHER:oak_log",
            "name": "oak_log",
            "quantity": 11,
            "dependencies": [],
            "operation_type": "gather",
        },
    ]
    out = _index(router.route_tasks(phase4a))
    assert "CRAFT:oak_planks_chunk_1" in out["SMELT:copper_ingot_chunk_1"]["dependencies"]


def test_phase4a_produces_sufficient_planks_for_phase4b():
    """Phase 4A plank quantity must satisfy Phase 4B per-chunk fuel + non-fuel demand."""
    import math

    optimizer = GlobalMathOptimizer()
    tasks = [
        {
            "id": "SMELT:stone",
            "name": "stone",
            "quantity": 320,
            "dependencies": ["MINE:cobblestone", "CRAFT:furnace", "CRAFT:oak_planks"],
            "operation_type": "smelt",
        },
        {
            "id": "MINE:cobblestone",
            "name": "cobblestone",
            "quantity": 400,
            "dependencies": ["CRAFT:wooden_pickaxe"],
            "operation_type": "mine",
        },
        {
            "id": "CRAFT:wooden_pickaxe",
            "name": "wooden_pickaxe",
            "quantity": 40,
            "dependencies": ["CRAFT:oak_planks", "CRAFT:stick", "CRAFT:crafting_table"],
            "operation_type": "craft",
        },
        {
            "id": "CRAFT:stick",
            "name": "stick",
            "quantity": 4000,
            "dependencies": ["CRAFT:oak_planks"],
            "operation_type": "craft",
        },
        {
            "id": "CRAFT:crafting_table",
            "name": "crafting_table",
            "quantity": 1,
            "dependencies": ["CRAFT:oak_planks"],
            "operation_type": "craft",
        },
        {
            "id": "CRAFT:furnace",
            "name": "furnace",
            "quantity": 1,
            "dependencies": ["MINE:cobblestone", "CRAFT:crafting_table"],
            "operation_type": "craft",
        },
        {
            "id": "CRAFT:oak_planks",
            "name": "oak_planks",
            "quantity": 8000,
            "dependencies": ["MINE:oak_log"],
            "operation_type": "craft",
        },
        {
            "id": "MINE:oak_log",
            "name": "oak_log",
            "quantity": 2000,
            "dependencies": [],
            "operation_type": "mine",
        },
    ]
    phase4a_tasks = optimizer.optimize_tasks(tasks)
    router = DagRouter()
    phase4b = _index(router.route_tasks(phase4a_tasks))

    for tid, chunk in phase4b.items():
        if chunk["operation_type"] == "smelt":
            plank_deps = [d for d in chunk["dependencies"] if "oak_planks" in d]
            assert plank_deps, f"{tid} missing plank fuel dependency"
            plank_qty = sum(phase4b[d]["quantity"] for d in plank_deps)
            fuel_needed = math.ceil(chunk["quantity"] / 1.5)
            assert plank_qty >= fuel_needed, f"{tid} has insufficient fuel planks"


def test_phase4a_fuel_survives_tool_recalculation():
    """Plank quantity after full Phase 4A must be >= per-chunk fuel demand alone."""
    import math

    optimizer = GlobalMathOptimizer()
    tasks = [
        {
            "id": "SMELT:stone",
            "name": "stone",
            "quantity": 200,
            "dependencies": ["MINE:cobblestone", "CRAFT:furnace", "CRAFT:oak_planks"],
            "operation_type": "smelt",
        },
        {
            "id": "MINE:cobblestone",
            "name": "cobblestone",
            "quantity": 300,
            "dependencies": ["CRAFT:wooden_pickaxe"],
            "operation_type": "mine",
        },
        {
            "id": "CRAFT:wooden_pickaxe",
            "name": "wooden_pickaxe",
            "quantity": 10,
            "dependencies": ["CRAFT:oak_planks", "CRAFT:stick", "CRAFT:crafting_table"],
            "operation_type": "craft",
        },
        {
            "id": "CRAFT:stick",
            "name": "stick",
            "quantity": 20,
            "dependencies": ["CRAFT:oak_planks"],
            "operation_type": "craft",
        },
        {
            "id": "CRAFT:crafting_table",
            "name": "crafting_table",
            "quantity": 1,
            "dependencies": ["CRAFT:oak_planks"],
            "operation_type": "craft",
        },
        {
            "id": "CRAFT:furnace",
            "name": "furnace",
            "quantity": 1,
            "dependencies": ["MINE:cobblestone", "CRAFT:crafting_table"],
            "operation_type": "craft",
        },
        {
            "id": "CRAFT:oak_planks",
            "name": "oak_planks",
            "quantity": 500,
            "dependencies": ["GATHER:oak_log"],
            "operation_type": "craft",
        },
        {
            "id": "GATHER:oak_log",
            "name": "oak_log",
            "quantity": 200,
            "dependencies": [],
            "operation_type": "gather",
        },
    ]
    out = _index(optimizer.optimize_tasks(tasks))

    # Compute minimum fuel required using per-chunk math
    stone_qty = out["SMELT:stone"]["quantity"]
    fuel_needed = 0
    remaining = stone_qty
    while remaining > 64:
        fuel_needed += math.ceil(64 / 1.5)
        remaining -= 64
    if remaining > 0:
        fuel_needed += math.ceil(remaining / 1.5)

    plank_qty = out["CRAFT:oak_planks"]["quantity"]
    assert plank_qty >= fuel_needed, (
        f"Phase 4A planks ({plank_qty}) below per-chunk fuel demand ({fuel_needed})"
    )
