"""Phase 5 queue visualizer — generates Mermaid (.mmd) flowcharts.

Produces two files in the same directory:
  - queue_flowchart.mmd   : linear queue with quantities, fuel, and tool durability
  - tool_optimization.mmd : global tool-tier ROI and durability calculations
"""

from __future__ import annotations

import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PHASE5_PATH = ROOT / "tests" / "input_materials_test.phase5.json"
BLUEPRINTS_PATH = ROOT / "constants" / "blueprints.json"
OUT_DIR = Path(__file__).resolve().parent

TOOL_DURABILITY: dict[str, int] = {
    "wooden_pickaxe": 59,
    "stone_pickaxe": 131,
    "iron_pickaxe": 250,
    "diamond_pickaxe": 1561,
    "wooden_axe": 59,
    "stone_axe": 131,
    "iron_axe": 250,
    "wooden_sword": 59,
    "stone_sword": 131,
    "iron_sword": 250,
    "wooden_shovel": 59,
    "stone_shovel": 131,
    "iron_shovel": 250,
    "wooden_hoe": 59,
    "stone_hoe": 131,
    "iron_hoe": 250,
}

TOOL_SUFFIXES = ("_pickaxe", "_axe", "_shovel", "_hoe", "_sword")

FUEL_YIELD = 1.5  # planks: 1 plank smelts 1.5 items


def _is_tool(name: str) -> bool:
    return name.endswith(TOOL_SUFFIXES)


def _durability(name: str) -> int:
    return TOOL_DURABILITY.get(name, 59)


def _tool_tier(name: str) -> str:
    for suffix in TOOL_SUFFIXES:
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return "unknown"


def _chunk_index(task_id: str) -> int:
    marker = "_chunk_"
    if marker in task_id:
        return int(task_id.rsplit(marker, 1)[1])
    return 1


def _base_id(task_id: str) -> str:
    marker = "_chunk_"
    if marker in task_id:
        return task_id.rsplit(marker, 1)[0]
    return task_id


def _sanitize_mermaid(text: str) -> str:
    """Escape characters that break Mermaid node labels."""
    return text.replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _node_label(task: dict, seq: int) -> str:
    """Build a compact Mermaid node label — key info in minimal space."""
    tid = _sanitize_mermaid(task["id"])
    name = _sanitize_mermaid(task["name"])
    qty = task["quantity"]
    op = task["operation_type"].upper()

    parts = [f"{seq}. {op} {name} x{qty}"]

    if op == "SMELT":
        fuel = math.ceil(qty / FUEL_YIELD)
        parts.append(f"fuel:{fuel}pk")

    if _is_tool(name):
        dur = _durability(name)
        parts.append(f"dur:{dur}")

    return "  ".join(parts)


def _generate_one_batch(tasks: list[dict], start_seq: int, batch_label: str) -> str:
    """Generate a single Mermaid flowchart for a batch of tasks."""
    lines: list[str] = []
    lines.append("%%{init: {'flowchart': {'nodeSpacing': 10, 'rankSpacing': 40, 'padding': 16}, 'themeVariables': {'fontSize': '28px'}} }%%")
    lines.append("flowchart TD")
    lines.append(f"    %% Phase 5 Execution Queue — {batch_label}")
    lines.append("")

    count = len(tasks)
    for i, task in enumerate(tasks):
        seq = start_seq + i
        node_key = f"n{i + 1}"
        label = _node_label(task, seq)
        lines.append(f"    {node_key}[\"{label}\"]")

    lines.append("")
    for i in range(1, count):
        lines.append(f"    n{i} --> n{i + 1}")

    return "\n".join(lines)


def generate_queue_flowcharts(tasks: list[dict]) -> dict[str, str]:
    """Generate batched linear Mermaid flowcharts (20 tasks per file)."""
    batch_size = 20
    total = len(tasks)
    files: dict[str, str] = {}

    for batch_start in range(0, total, batch_size):
        batch_end = min(batch_start + batch_size, total)
        batch_tasks = tasks[batch_start:batch_end]
        batch_num = batch_start // batch_size + 1
        label = f"tasks {batch_start + 1}–{batch_end}"
        filename = f"queue_batch_{batch_num:02d}.mmd"
        files[filename] = _generate_one_batch(batch_tasks, batch_start + 1, label)

    return files


def generate_tool_optimization(tasks: list[dict]) -> str:
    """Generate a Mermaid chart showing tool-tier ROI calculations."""
    lines: list[str] = []
    lines.append("flowchart TD")
    lines.append("    %% Tool Tier Optimization — ROI & Durability Analysis")
    lines.append("")

    # Collect tool usage
    tool_usage: dict[str, dict] = {}
    for task in tasks:
        name = task["name"]
        if not _is_tool(name):
            continue
        if name not in tool_usage:
            tool_usage[name] = {
                "chunks": 0,
                "total_qty": 0,
                "durability": _durability(name),
                "tier": _tool_tier(name),
                "consumers": set(),
            }
        tool_usage[name]["chunks"] += 1
        tool_usage[name]["total_qty"] += task["quantity"]

    # Find tool consumers
    id_to_task = {t["id"]: t for t in tasks}
    for tool_name in tool_usage:
        for task in tasks:
            for dep_id in task["dependencies"]:
                dep_task = id_to_task.get(dep_id)
                if dep_task and dep_task["name"] == tool_name:
                    tool_usage[tool_name]["consumers"].add(task["name"])

    # Tier hierarchy
    lines.append("    %% ── Tier Hierarchy ──")
    tiers: dict[str, list[str]] = {}
    for name, info in tool_usage.items():
        tier = info["tier"]
        if tier not in tiers:
            tiers[tier] = []
        tiers[tier].append(name)

    tier_order = ["wooden", "stone", "iron", "diamond", "netherite"]
    prev_tier: str | None = None
    for tier in tier_order:
        if tier not in tiers:
            continue
        tools = tiers[tier]
        for tool in tools:
            info = tool_usage[tool]
            dur = info["durability"]
            total = info["total_qty"]
            lines.append(f'    {tool.replace("_", "")}["{tool}<br/>tier: {tier}<br/>durability: {dur}<br/>crafted: {total}×"]')

    lines.append("")
    lines.append("    %% ── Durability Math ──")
    lines.append("")

    # Tool workload analysis
    for tool_name, info in sorted(tool_usage.items()):
        dur = info["durability"]
        total = info["total_qty"]
        total_capacity = total * dur
        lines.append(f"    %% {tool_name}: {total} crafted × {dur} durability = {total_capacity} total uses")

    lines.append("")
    lines.append("    %% ── Consumer Mapping ──")
    for tool_name, info in sorted(tool_usage.items()):
        consumers = info["consumers"]
        for consumer in sorted(consumers):
            safe_tool = tool_name.replace("_", "")
            safe_consumer = consumer.replace("_", "")
            lines.append(f'    {safe_tool} --> {safe_consumer}["{consumer}"]')

    lines.append("")
    lines.append("    %% ── ROI Decision Summary ──")
    lines.append("    %% ROI formula: Time_Hand = Q × 3.0s  vs  Time_Upgrade = 25.0s + Q × 0.4s")
    lines.append("    %% Upgrade triggered when: 25 + Q×0.4 < Q×3  →  Q > 9.6  (≈10 blocks)")
    lines.append("")
    lines.append('    roi["ROI Decision Engine<br/>Upgrade when Q &gt; 10 blocks<br/>Hand: Q × 3.0s<br/>Stone tool: 25s + Q × 0.4s"]')

    return "\n".join(lines)


def main() -> None:
    if not PHASE5_PATH.exists():
        print(f"ERROR: Phase 5 file not found at {PHASE5_PATH}")
        print("Run the full pipeline first: LocalOptimizer().optimize_from_file()")
        return

    with open(PHASE5_PATH, encoding="utf-8") as f:
        tasks = json.load(f)

    print(f"Loaded {len(tasks)} tasks from {PHASE5_PATH}")

    # Generate queue flowcharts (batched for readability)
    batch_files = generate_queue_flowcharts(tasks)
    for filename, content in batch_files.items():
        out_path = OUT_DIR / filename
        out_path.write_text(content + "\n", encoding="utf-8")
        print(f"Wrote queue batch → {out_path}")

    # Generate single full-queue file
    full_mmd = _generate_one_batch(tasks, 1, f"tasks 1–{len(tasks)}")
    full_path = OUT_DIR / "queue_flowchart.mmd"
    full_path.write_text(full_mmd + "\n", encoding="utf-8")
    print(f"Wrote full queue → {full_path}")

    # Generate tool optimization chart
    tool_mmd = generate_tool_optimization(tasks)
    tool_path = OUT_DIR / "tool_optimization.mmd"
    tool_path.write_text(tool_mmd + "\n", encoding="utf-8")
    print(f"Wrote tool optimization  → {tool_path}")


if __name__ == "__main__":
    main()
