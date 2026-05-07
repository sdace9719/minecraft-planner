#!/usr/bin/env python3
"""Generate an interactive vis.js timeline HTML from the Phase 5 queue."""

from __future__ import annotations

import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PHASE5_PATH = ROOT / "tests" / "input_materials_test.phase5.json"
OUT_DIR = Path(__file__).resolve().parent

FUEL_YIELD = 1.5
TOOL_SUFFIXES = ("_pickaxe", "_axe", "_shovel", "_hoe", "_sword")

OP_COLORS = {
    "gather":  "#4CAF50",  # green
    "craft":   "#2196F3",  # blue
    "smelt":   "#FF9800",  # orange
    "mine":    "#F44336",  # red
    "sword":   "#9C27B0",  # purple
}

HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Phase 5 Execution Queue</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/vis/4.21.0/vis.min.js"></script>
<link href="https://cdnjs.cloudflare.com/ajax/libs/vis/4.21.0/vis.min.css" rel="stylesheet">
<style>
  body {{ margin:0; padding:0; font-family:monospace; background:#1a1a2e; color:#eee; overflow:hidden; }}
  #header {{ padding:12px 20px; background:#16213e; border-bottom:2px solid #0f3460; }}
  #header h1 {{ margin:0; font-size:18px; }}
  #header span {{ font-size:12px; color:#888; }}
  #network {{ width:100vw; height:calc(100vh - 52px); }}
  .tooltip-content {{ white-space:nowrap; font-size:13px; line-height:1.5; }}
  .tooltip-content b {{ color:#FFD54F; }}
</style>
</head>
<body>
<div id="header">
  <h1>Phase 5 Execution Queue <span>— {total} tasks, scroll/pinch to zoom, drag to pan, hover for details</span></h1>
</div>
<div id="network"></div>
<script>
var nodes = new vis.DataSet({nodes_json});
var edges = new vis.DataSet({edges_json});

var container = document.getElementById('network');
var data = {{ nodes: nodes, edges: edges }};
var options = {{
  nodes: {{
    shape: 'box',
    margin: 8,
    widthConstraint: {{ minimum: 240, maximum: 380 }},
    font: {{ size: 13, face: 'monospace', color: '#ddd', multi: true }},
    borderWidth: 2,
    shadow: {{ enabled: true, size: 3 }},
  }},
  edges: {{
    arrows: {{ to: {{ enabled: true, scaleFactor: 0.6 }} }},
    color: {{ color: '#555', highlight: '#FFD54F' }},
    width: 1,
    smooth: false,
  }},
  physics: {{ enabled: false }},
  interaction: {{ hover: true, tooltipDelay: 100, zoomView: true, dragView: true }},
}};

var network = new vis.Network(container, data, options);
network.once('stabilized', function() {{ network.fit(); }});
</script>
</body>
</html>"""


def _chunk_index(task_id: str) -> int:
    marker = "_chunk_"
    if marker in task_id:
        return int(task_id.rsplit(marker, 1)[1])
    return 1


def _is_tool(name: str) -> bool:
    return name.split("_mvb_")[0].endswith(TOOL_SUFFIXES)


def _node_label(task: dict, seq: int) -> str:
    name = task["name"]
    qty = task["quantity"]
    op = task["operation_type"].upper()
    label = f"[{seq}] {op} {name} ×{qty}"
    if op == "SMELT":
        fuel = math.ceil(qty / FUEL_YIELD)
        label += f"\n  fuel: {fuel} planks"
    if _is_tool(name):
        dur = _durability(name)
        label += f"\n  durability: {dur}"
    return label


def _durability(name: str) -> int:
    base = name.split("_mvb_")[0]
    tier = base.split("_")[0]
    dur_map = {"wooden": 59, "stone": 131, "iron": 250, "diamond": 1561,
               "golden": 32, "netherite": 2031}
    return dur_map.get(tier, 59)


def _task_title(task: dict, seq: int) -> str:
    tid = task["id"]
    name = task["name"]
    qty = task["quantity"]
    op = task["operation_type"]
    deps = ", ".join(task["dependencies"]) if task["dependencies"] else "(none)"
    lines = [
        f"<b>#{seq}</b> {tid}",
        f"Item: {name}",
        f"Quantity: {qty}",
        f"Operation: {op}",
    ]
    if op == "smelt":
        lines.append(f"Fuel: {math.ceil(qty / FUEL_YIELD)} planks")
    if _is_tool(name):
        lines.append(f"Durability: {_durability(name)}")
    lines.append(f"Dependencies: {deps}")
    return "<br>".join(lines)


def generate_timeline(tasks: list[dict]) -> str:
    nodes_json = []
    edges_json = []
    id_to_node: dict[str, int] = {}

    for i, task in enumerate(tasks):
        nid = i + 1
        tid = task["id"]
        id_to_node[tid] = nid
        color = OP_COLORS.get(task["operation_type"], "#888")
        label = _node_label(task, nid)
        title = _task_title(task, nid)

        # Manual positioning: vertical queue, fixed x=0, y increases downward
        nodes_json.append({
            "id": nid,
            "label": label,
            "title": f'<div class="tooltip-content">{title}</div>',
            "color": {"background": "#16213e", "border": color, "highlight": {"border": "#FFD54F"}},
            "x": 0,
            "y": i * 80,
            "fixed": {"x": True, "y": True},
        })

    # Linear chain edges (execution order)
    for i in range(len(tasks) - 1):
        edges_json.append({
            "from": i + 1,
            "to": i + 2,
            "dashes": True,
            "color": {"color": "#333", "highlight": "#FFD54F"},
            "width": 0.5,
        })

    # Dependency edges (producer → consumer, solid)
    for i, task in enumerate(tasks):
        consumer_id = i + 1
        for dep_id in task["dependencies"]:
            producer_id = id_to_node.get(dep_id)
            if producer_id is not None:
                edges_json.append({
                    "from": producer_id,
                    "to": consumer_id,
                    "color": {"color": "#555", "highlight": "#FFD54F", "opacity": 0.4},
                    "width": 1,
                })

    return HTML_TEMPLATE.format(
        total=len(tasks),
        nodes_json=json.dumps(nodes_json),
        edges_json=json.dumps(edges_json),
    )


def main() -> None:
    if not PHASE5_PATH.exists():
        print(f"ERROR: Phase 5 file not found at {PHASE5_PATH}")
        return

    with open(PHASE5_PATH, encoding="utf-8") as f:
        tasks = json.load(f)

    print(f"Loaded {len(tasks)} tasks from {PHASE5_PATH}")

    html = generate_timeline(tasks)
    out_path = OUT_DIR / "queue_timeline.html"
    out_path.write_text(html, encoding="utf-8")
    print(f"Wrote timeline → {out_path}")


if __name__ == "__main__":
    main()
