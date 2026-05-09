#!/usr/bin/env python3
"""Generate an interactive vis.js timeline HTML from the full Phase 6 execution trace.

Includes Phase-6-injected tasks: STASH, GO_TO_CHEST, CRAFT:chest, PLACE_CHEST.
"""
from __future__ import annotations

import json, math, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OUT_DIR = Path(__file__).resolve().parent
OUT_PATH = OUT_DIR / "queue_timeline.html"

OP_COLORS = {
    "gather":  "#4CAF50",
    "craft":   "#2196F3",
    "smelt":   "#FF9800",
    "mine":    "#F44336",
    "sword":   "#9C27B0",
    "place":   "#4CAF50",
    "stash":   "#FFD700",
    "retrieve": "#00BCD4",
}

HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Phase 6 Execution Trace — {total} steps</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/vis/4.21.0/vis.min.js"></script>
<link href="https://cdnjs.cloudflare.com/ajax/libs/vis/4.21.0/vis.min.css" rel="stylesheet">
<style>
  body {{ margin:0; padding:0; font-family:monospace; background:#1a1a2e; color:#eee; overflow:hidden; }}
  #header {{ padding:12px 20px; background:#16213e; border-bottom:2px solid #0f3460; display:flex; gap:20px; align-items:center; flex-wrap:wrap; }}
  #header h1 {{ margin:0; font-size:18px; }}
  #header span {{ font-size:12px; color:#888; }}
  .legend {{ display:flex; gap:8px; flex-wrap:wrap; font-size:11px; }}
  .legend-item {{ display:flex; align-items:center; gap:4px; }}
  .legend-swatch {{ width:12px; height:12px; border-radius:2px; flex-shrink:0; }}
  #network {{ width:100vw; height:calc(100vh - 52px); }}
  .tooltip-content {{ font-size:13px; line-height:1.5; max-width:600px; }}
  .tooltip-content b {{ color:#FFD54F; }}
  .inv-grid {{ display:grid; grid-template-columns:repeat(9, 1fr); gap:1px; margin-top:4px; font-size:10px; }}
  .inv-slot {{ padding:2px 4px; background:#1a1a2e; border:1px solid #333; border-radius:2px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
  .inv-slot.empty {{ color:#444; }}
  .inv-slot.used {{ color:#8be9fd; }}
</style>
</head>
<body>
<div id="header">
  <h1>Phase 6 Execution Trace <span>— {total} steps, {chests} chests, scroll/pinch to zoom</span></h1>
  <div class="legend">
    {legend_html}
  </div>
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
    widthConstraint: {{ minimum: 260, maximum: 420 }},
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


def _slot_name(s: dict | None) -> str:
    if s is None:
        return "—"
    dur = f" [{s['durability']}]" if s.get("durability") else ""
    return f"{s['item']}{dur} ×{s['qty']}"


def _inventory_html(slots: list[dict | None]) -> str:
    """Build a compact 36-slot inventory grid as HTML."""
    cells: list[str] = []
    for i, s in enumerate(slots):
        if s is None:
            cells.append(f'<div class="inv-slot empty">{i}</div>')
        else:
            dur = f"[{s['durability']}]" if s.get("durability") else ""
            txt = f"{s['item']}{dur} ×{s['qty']}"
            cells.append(f'<div class="inv-slot used" title="{txt}">{txt[:14]}</div>')
    return f'<div class="inv-grid">{"".join(cells)}</div>'


def _task_label(snapshot: dict, step: int) -> str:
    """Build a compact node label for a single snapshot."""
    tid = snapshot["task_id"]
    op = snapshot.get("operation_type", "")
    qty = snapshot.get("quantity", 0)
    name = snapshot.get("name", "")

    if snapshot.get("stash"):
        chest = snapshot.get("chest", "?")
        return f"[{step}] STASH → {chest}\n  (8 slots cleared)"
    if snapshot.get("retrieve"):
        item = snapshot.get("item", "?")
        return f"[{step}] GO TO CHEST\n  retrieve {item}"
    if tid == "CRAFT:chest_batch":
        return f"[{step}] CRAFT chest ×{qty}\n  (consumes {qty * 8} oak_planks)"
    if tid == "PLACE_CHEST:batch":
        return f"[{step}] PLACE chest ×{qty}\n  (available for stashing)"

    label = f"[{step}] {op.upper()} {name} ×{qty}"
    if op == "smelt":
        label += f"\n  fuel: {math.ceil(qty / 1.5)} planks"
    return label


def _task_title(snapshot: dict, step: int) -> str:
    """Full HTML tooltip for a snapshot."""
    tid = snapshot["task_id"]
    qty = snapshot.get("quantity", 0)
    name = snapshot.get("name", "")
    op = snapshot.get("operation_type", "")

    lines = [f"<b>#{step}</b> {tid}"]

    if snapshot.get("stash"):
        lines.append(f"Event: STASH → {snapshot.get('chest', '?')}")
        lines.append("Freed 8+ inventory slots")
    elif snapshot.get("retrieve"):
        lines.append("Event: GO_TO_CHEST")
        lines.append(f"Retrieved item: {snapshot.get('item', '?')}")
    else:
        lines.append(f"Item: {name}")
        lines.append(f"Quantity: {qty}")
        lines.append(f"Operation: {op}")
        if op == "smelt":
            lines.append(f"Fuel: {math.ceil(qty / 1.5)} planks")

    lines.append("")
    lines.append("<b>Inventory (36 slots):</b>")
    lines.append(_inventory_html(snapshot.get("slots", [])))
    return "<br>".join(lines)


def _color_for(snapshot: dict) -> str:
    if snapshot.get("stash"):
        return OP_COLORS["stash"]
    if snapshot.get("retrieve"):
        return OP_COLORS["retrieve"]
    return OP_COLORS.get(snapshot.get("operation_type", ""), "#888")


def _legend_html() -> str:
    items = [
        ("#4CAF50", "gather"),
        ("#2196F3", "craft"),
        ("#FF9800", "smelt"),
        ("#F44336", "mine"),
        ("#9C27B0", "sword"),
        ("#4CAF50", "place"),
        ("#FFD700", "STASH"),
        ("#00BCD4", "GO_TO_CHEST"),
    ]
    parts = []
    for color, label in items:
        parts.append(
            f'<div class="legend-item">'
            f'<div class="legend-swatch" style="background:{color}"></div>{label}'
            f'</div>'
        )
    return "\n    ".join(parts)


def _enrich_snapshot(snap: dict, task_by_id: dict[str, dict]) -> dict:
    """Merge base task data (name, quantity, operation_type) into a snapshot."""
    tid = snap.get("task_id", "")
    base = task_by_id.get(tid)
    if base is not None:
        return {**base, **snap}
    # Injected Phase 6 tasks: carry their own data or infer it.
    if snap.get("stash"):
        snap["operation_type"] = "stash"
    elif snap.get("retrieve"):
        snap["operation_type"] = "retrieve"
    elif tid == "CRAFT:chest_batch":
        snap["operation_type"] = "craft"
        snap["name"] = "chest"
        snap.setdefault("quantity", 0)
    elif tid == "PLACE_CHEST:batch":
        snap["operation_type"] = "place"
        snap["name"] = "chest"
        snap.setdefault("quantity", 0)
    return snap


def generate_timeline(snapshots: list[dict], task_by_id: dict[str, dict], chests: int) -> str:
    nodes_json: list[dict] = []
    edges_json: list[dict] = []

    for i, raw_snap in enumerate(snapshots):
        snap = _enrich_snapshot(raw_snap, task_by_id)
        nid = i + 1
        color = _color_for(snap)
        label = _task_label(snap, i + 1)
        title = _task_title(snap, i + 1)

        nodes_json.append({
            "id": nid,
            "label": label,
            "title": f'<div class="tooltip-content">{title}</div>',
            "color": {
                "background": "#16213e",
                "border": color,
                "highlight": {"border": "#FFD54F"},
            },
            "x": 0,
            "y": i * 80,
            "fixed": {"x": True, "y": True},
        })

    # Linear execution chain edges
    for i in range(len(snapshots) - 1):
        edges_json.append({
            "from": i + 1,
            "to": i + 2,
            "dashes": True,
            "color": {"color": "#333", "highlight": "#FFD54F"},
            "width": 0.5,
        })

    return HTML_TEMPLATE.format(
        total=len(snapshots),
        chests=chests,
        legend_html=_legend_html(),
        nodes_json=json.dumps(nodes_json),
        edges_json=json.dumps(edges_json),
    )


def main() -> None:
    # 1. Phase 4B
    from planner.dag_router import DagRouter
    router = DagRouter()
    phase4_tasks = router.route_from_file()
    print(f"Phase 4B: {len(phase4_tasks)} tasks")

    # 2. Phase 5
    from planner.global_optimizer import topological_sort_phase4
    phase5_tasks = topological_sort_phase4(phase4_tasks)
    phase5_path = ROOT / "tests" / "input_materials_test.phase5.json"
    phase5_path.write_text(json.dumps(phase5_tasks, indent=2) + "\n")
    print(f"Phase 5: {len(phase5_tasks)} tasks")

    # 3. Phase 6 — full simulation with chest overhead
    from planner.final_checker import CacheSimulator
    sim = CacheSimulator()
    result = sim.simulate_with_chest_overhead()
    print(f"Phase 6: success={result.success}, chests={sim._chest_counter}, "
          f"snapshots={len(result.inventory_snapshots)}")
    if result.error:
        print(f"  error: {result.error}")
        return

    # 4. Build task lookup map and generate HTML
    task_by_id = {t["id"]: t for t in phase5_tasks}
    html = generate_timeline(result.inventory_snapshots, task_by_id, sim._chest_counter)
    OUT_PATH.write_text(html, encoding="utf-8")
    print(f"Wrote timeline → {OUT_PATH}")


if __name__ == "__main__":
    main()
