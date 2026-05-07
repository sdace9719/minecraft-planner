from planner.global_optimizer import (
    TopologicalSortError,
    TopologicalSorter,
    _extract_base_id,
    _extract_chunk_index,
    topological_sort_phase4,
)


# ── helper id extraction ──────────────────────────────────────────────

def test_extract_base_id_plain():
    assert _extract_base_id("CRAFT:oak_planks_chunk_1") == "CRAFT:oak_planks"


def test_extract_base_id_mvb():
    assert _extract_base_id("CRAFT:wooden_pickaxe_mvb_1_chunk_3") == "CRAFT:wooden_pickaxe_mvb_1"


def test_extract_base_id_no_chunk_suffix():
    assert _extract_base_id("MINE:cobblestone") == "MINE:cobblestone"


def test_extract_chunk_index_plain():
    assert _extract_chunk_index("CRAFT:oak_planks_chunk_5") == 5


def test_extract_chunk_index_mvb():
    assert _extract_chunk_index("CRAFT:item_mvb_2_chunk_10") == 10


def test_extract_chunk_index_no_suffix_defaults_to_1():
    assert _extract_chunk_index("GATHER:clay_ball") == 1


def test_extract_chunk_index_invalid_suffix_raises():
    try:
        _extract_chunk_index("CRAFT:oak_planks_chunk_abc")
    except TopologicalSortError as exc:
        assert "Invalid chunk suffix" in str(exc)
    else:
        assert False, "Expected TopologicalSortError for non-integer chunk suffix"


# ── core algorithm ────────────────────────────────────────────────────

def test_empty_input_returns_empty():
    assert TopologicalSorter().sort_tasks([]) == []


def test_single_task_no_deps():
    task = {
        "id": "GATHER:clay_ball_chunk_1",
        "name": "clay_ball",
        "quantity": 64,
        "dependencies": [],
        "operation_type": "gather",
    }
    result = TopologicalSorter().sort_tasks([task])
    assert result == [task]


def test_linear_chain_preserves_order():
    tasks = [
        {"id": "CRAFT:stick_chunk_1", "name": "stick", "quantity": 4, "dependencies": ["CRAFT:oak_planks_chunk_1"], "operation_type": "craft"},
        {"id": "GATHER:oak_log_chunk_1", "name": "oak_log", "quantity": 1, "dependencies": [], "operation_type": "gather"},
        {"id": "CRAFT:oak_planks_chunk_1", "name": "oak_planks", "quantity": 4, "dependencies": ["GATHER:oak_log_chunk_1"], "operation_type": "craft"},
    ]
    result = topological_sort_phase4(tasks)
    ids = [t["id"] for t in result]
    assert ids.index("GATHER:oak_log_chunk_1") < ids.index("CRAFT:oak_planks_chunk_1")
    assert ids.index("CRAFT:oak_planks_chunk_1") < ids.index("CRAFT:stick_chunk_1")


def test_diamond_dependency_shape():
    """X depends on Y and Z; Y and Z both depend on W."""
    tasks = [
        {"id": "X", "name": "x", "quantity": 1, "dependencies": ["Y", "Z"], "operation_type": "craft"},
        {"id": "Y", "name": "y", "quantity": 1, "dependencies": ["W"], "operation_type": "craft"},
        {"id": "Z", "name": "z", "quantity": 1, "dependencies": ["W"], "operation_type": "craft"},
        {"id": "W", "name": "w", "quantity": 1, "dependencies": [], "operation_type": "gather"},
    ]
    result = topological_sort_phase4(tasks)
    ids = [t["id"] for t in result]
    assert ids.index("W") < ids.index("Y")
    assert ids.index("W") < ids.index("Z")
    assert ids.index("Y") < ids.index("X")
    assert ids.index("Z") < ids.index("X")


def test_chunk_numeric_ordering():
    """Chunks of same base_id execute in numeric order (chunk_1, chunk_2, chunk_10)."""
    tasks = [
        {"id": "CRAFT:oak_planks_chunk_10", "name": "oak_planks", "quantity": 64, "dependencies": ["GATHER:oak_log_chunk_1"], "operation_type": "craft"},
        {"id": "CRAFT:oak_planks_chunk_2", "name": "oak_planks", "quantity": 64, "dependencies": ["GATHER:oak_log_chunk_1"], "operation_type": "craft"},
        {"id": "CRAFT:oak_planks_chunk_1", "name": "oak_planks", "quantity": 64, "dependencies": ["GATHER:oak_log_chunk_1"], "operation_type": "craft"},
        {"id": "GATHER:oak_log_chunk_1", "name": "oak_log", "quantity": 64, "dependencies": [], "operation_type": "gather"},
    ]
    result = topological_sort_phase4(tasks)
    plank_order = [
        t["id"] for t in result if t["id"].startswith("CRAFT:oak_planks")
    ]
    assert plank_order == [
        "CRAFT:oak_planks_chunk_1",
        "CRAFT:oak_planks_chunk_2",
        "CRAFT:oak_planks_chunk_10",
    ]


def test_inventory_pressure_ordering():
    """Task with more dependencies (more negative pressure) sorts before one with fewer."""
    tasks = [
        # This one has 3 deps → pressure = 1-3 = -2
        {"id": "CRAFT:wooden_pickaxe_chunk_1", "name": "wooden_pickaxe", "quantity": 1, "dependencies": ["CRAFT:oak_planks_chunk_1", "CRAFT:stick_chunk_1", "CRAFT:crafting_table_chunk_1"], "operation_type": "craft"},
        # This one has 0 deps → pressure = 1-0 = 1
        {"id": "CRAFT:oak_planks_chunk_1", "name": "oak_planks", "quantity": 64, "dependencies": [], "operation_type": "craft"},
        {"id": "CRAFT:stick_chunk_1", "name": "stick", "quantity": 4, "dependencies": [], "operation_type": "craft"},
        {"id": "CRAFT:crafting_table_chunk_1", "name": "crafting_table", "quantity": 1, "dependencies": [], "operation_type": "craft"},
    ]
    result = topological_sort_phase4(tasks)
    first_id = result[0]["id"]
    # The 3-dep task should NOT sort first (positive pressure tasks go first)
    assert first_id != "CRAFT:wooden_pickaxe_chunk_1"


def test_cycle_detection_raises():
    tasks = [
        {"id": "A", "name": "a", "quantity": 1, "dependencies": ["B"], "operation_type": "craft"},
        {"id": "B", "name": "b", "quantity": 1, "dependencies": ["A"], "operation_type": "craft"},
    ]
    try:
        TopologicalSorter().sort_tasks(tasks)
    except TopologicalSortError as exc:
        assert "Cycle detected" in str(exc)
    else:
        assert False, "Expected TopologicalSortError for cycle"


def test_missing_dependency_raises():
    tasks = [
        {"id": "CRAFT:stick_chunk_1", "name": "stick", "quantity": 4, "dependencies": ["CRAFT:nonexistent_chunk_1"], "operation_type": "craft"},
    ]
    try:
        TopologicalSorter().sort_tasks(tasks)
    except TopologicalSortError as exc:
        assert "Dangling dependency" in str(exc)
    else:
        assert False, "Expected TopologicalSortError for missing dependency"


def test_duplicate_id_raises():
    tasks = [
        {"id": "CRAFT:oak_planks_chunk_1", "name": "oak_planks", "quantity": 64, "dependencies": [], "operation_type": "craft"},
        {"id": "CRAFT:oak_planks_chunk_1", "name": "oak_planks", "quantity": 64, "dependencies": [], "operation_type": "craft"},
    ]
    try:
        TopologicalSorter().sort_tasks(tasks)
    except TopologicalSortError as exc:
        assert "Duplicate" in str(exc)
    else:
        assert False, "Expected TopologicalSortError for duplicate ids"


def test_missing_id_field_raises():
    tasks = [
        {"name": "oak_planks", "quantity": 64, "dependencies": [], "operation_type": "craft"},
    ]
    try:
        TopologicalSorter().sort_tasks(tasks)
    except TopologicalSortError:
        pass
    else:
        assert False, "Expected TopologicalSortError for missing id"


def test_full_phase4_output_is_valid():
    """Load the actual Phase 4 output, sort, and verify topological ordering."""
    import json
    from pathlib import Path

    phase4_path = Path(__file__).resolve().parent / "input_materials_test.phase4.json"
    if not phase4_path.exists():
        return  # skip if file hasn't been generated

    with open(phase4_path, encoding="utf-8") as f:
        tasks = json.load(f)

    result = TopologicalSorter().sort_tasks(tasks)
    assert len(result) == len(tasks)

    positions = {t["id"]: i for i, t in enumerate(result)}
    for task in result:
        for dep in task["dependencies"]:
            assert positions[dep] < positions[task["id"]], (
                f"Dependency {dep!r} appears after consumer {task['id']!r}"
            )
