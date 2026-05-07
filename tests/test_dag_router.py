from planner.dag_router import DagRouter


def _index(tasks):
    return {task["id"]: task for task in tasks}


def test_step2_remainder_padding_respects_yield_multiple():
    router = DagRouter()
    phase4a = [
        {
            "id": "CRAFT:oak_planks",
            "name": "oak_planks",
            "quantity": 65,
            "dependencies": ["GATHER:oak_log"],
            "operation_type": "craft",
        },
        {
            "id": "GATHER:oak_log",
            "name": "oak_log",
            "quantity": 100,
            "dependencies": [],
            "operation_type": "gather",
        },
    ]
    out = _index(router.route_tasks(phase4a))
    assert out["CRAFT:oak_planks_chunk_1"]["quantity"] == 64
    assert out["CRAFT:oak_planks_chunk_2"]["quantity"] == 4


def test_step2_unstackable_items_are_unit_chunks():
    router = DagRouter()
    phase4a = [
        {
            "id": "CRAFT:wooden_pickaxe",
            "name": "wooden_pickaxe",
            "quantity": 3,
            "dependencies": [],
            "operation_type": "craft",
        },
    ]
    out = _index(router.route_tasks(phase4a))
    assert out["CRAFT:wooden_pickaxe_chunk_1"]["quantity"] == 1
    assert out["CRAFT:wooden_pickaxe_chunk_2"]["quantity"] == 1
    assert out["CRAFT:wooden_pickaxe_chunk_3"]["quantity"] == 1


def test_step3_waterfall_rollover_wires_multiple_chunks():
    router = DagRouter()
    phase4a = [
        {
            "id": "CRAFT:oak_planks",
            "name": "oak_planks",
            "quantity": 80,
            "dependencies": ["GATHER:oak_log"],
            "operation_type": "craft",
        },
        {
            "id": "CRAFT:chest",
            "name": "chest",
            "quantity": 10,
            "dependencies": ["CRAFT:oak_planks"],
            "operation_type": "craft",
        },
        {
            "id": "GATHER:oak_log",
            "name": "oak_log",
            "quantity": 100,
            "dependencies": [],
            "operation_type": "gather",
        },
    ]
    out = _index(router.route_tasks(phase4a))
    deps = out["CRAFT:chest_chunk_1"]["dependencies"]
    assert "CRAFT:oak_planks_chunk_1" in deps
    assert "CRAFT:oak_planks_chunk_2" in deps


def test_step3_enforces_id_family_isolation_for_mvb():
    router = DagRouter()
    phase4a = [
        {
            "id": "CRAFT:stone_pickaxe",
            "name": "stone_pickaxe",
            "quantity": 1,
            "dependencies": [],
            "operation_type": "craft",
        },
        {
            "id": "CRAFT:stone_pickaxe_mvb_1",
            "name": "stone_pickaxe_mvb_1",
            "quantity": 1,
            "dependencies": [],
            "operation_type": "craft",
        },
        {
            "id": "MINE:cobblestone",
            "name": "cobblestone",
            "quantity": 5,
            "dependencies": ["CRAFT:stone_pickaxe"],
            "operation_type": "mine",
        },
    ]
    out = _index(router.route_tasks(phase4a))
    deps = out["MINE:cobblestone_chunk_1"]["dependencies"]
    assert "CRAFT:stone_pickaxe_chunk_1" in deps
    assert "CRAFT:stone_pickaxe_mvb_1_chunk_1" not in deps


def test_step3_hard_fails_on_acyclic_capacity_exhaustion():
    router = DagRouter()
    phase4a = [
        {
            "id": "CRAFT:oak_planks",
            "name": "oak_planks",
            "quantity": 4,
            "dependencies": ["CRAFT:stick"],
            "operation_type": "craft",
        },
        {
            "id": "CRAFT:stick",
            "name": "stick",
            "quantity": 4,
            "dependencies": ["CRAFT:oak_planks"],
            "operation_type": "craft",
        },
    ]
    try:
        router.route_tasks(phase4a)
    except ValueError as exc:
        assert "Acyclic capacity exhausted" in str(exc)
    else:
        assert False, "Expected fatal acyclic-capacity exhaustion error"
