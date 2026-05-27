#!/usr/bin/env python3
"""Full iron pickaxe crafting flow with Baritone pathfinding and inventory verification.

Steps:
  1. Craft planks + sticks (2x2)
  2. Smelt raw_iron
  3. Wait for smelting to complete
  4. Collect furnace via Baritone
  5. Ensure crafting table in hotbar (recover if needed)
  6. Craft iron_pickaxe (3x3)
  7. Cleanup: recover any remaining placed blocks
"""

import json
import sys
import time
import urllib.request
import urllib.error

HOST = "http://localhost:8765"


def get(endpoint: str) -> dict:
    url = f"{HOST}{endpoint}"
    req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.URLError as e:
        print(f"  Connection failed — Minecraft running? ({e.reason})", file=sys.stderr)
        sys.exit(1)


def post(endpoint: str, data: dict) -> dict:
    url = f"{HOST}{endpoint}"
    body = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode()
            return json.loads(raw) if raw.strip() else {"status": "ok"}
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try: return json.loads(raw)
        except json.JSONDecodeError: return {"status": "error", "http_code": e.code, "message": raw}
    except urllib.error.URLError as e:
        print(f"  Connection failed ({e.reason})", file=sys.stderr)
        sys.exit(1)


def step(n: int, desc: str):
    print(f"\n=== Step {n}: {desc} ===")


def wait_for_idle(label: str, max_wait_s: int = 120):
    print(f"  Waiting for '{label}' to complete...", end="", flush=True)
    for _ in range(max_wait_s * 2):
        time.sleep(0.5)
        try:
            if get("/health").get("status") == "ok":
                print(" done!")
                return True
        except Exception:
            continue
        print(".", end="", flush=True)
    print(" timeout!")
    return False


def wait_for_smelt_done(x: int, y: int, z: int, max_wait_s: int = 120):
    print(f"  Waiting for furnace at ({x},{y},{z}) to finish...", end="", flush=True)
    for _ in range(max_wait_s * 2):
        time.sleep(0.5)
        try:
            if get(f"/bot/furnace?x={x}&y={y}&z={z}").get("burning") is False:
                print(" done!")
                return True
        except Exception:
            continue
        print(".", end="", flush=True)
    print(" timeout!")
    return False


def count_in_inventory(item_id: str) -> int:
    try:
        inv = get("/inventory")
    except Exception:
        return -1
    if not isinstance(inv, list):
        return -1
    return sum(e.get("count", 0) for e in inv if e.get("item") == item_id)


def ensure_in_hotbar(item_name: str) -> bool:
    """Check inventory, swap if in main inv, verify it worked."""
    inv = get("/inventory")
    in_hotbar = any(e.get("item") == item_name and e.get("slot", 99) < 9 for e in (inv if isinstance(inv, list) else []))
    if in_hotbar:
        print(f"  {item_name} already in hotbar")
        return True
    in_main = any(e.get("item") == item_name and e.get("slot", 99) >= 9 for e in (inv if isinstance(inv, list) else []))
    if in_main:
        short = item_name.split(":")[-1]
        print(f"  Swapping {short} to hotbar...", end="", flush=True)
        post("/bot/swap-hotbar", {"itemsToHotbar": [short]})
        for _ in range(20):
            time.sleep(0.25)
            inv2 = get("/inventory")
            if any(e.get("item") == item_name and e.get("slot", 99) < 9 for e in (inv2 if isinstance(inv2, list) else [])):
                print(" done!")
                return True
            print(".", end="", flush=True)
        print(" FAILED", file=sys.stderr)
    return False


def collect_block(item_id: str, x: int, y: int, z: int, max_wait_s: int = 30) -> bool:
    """Baritone goto block, verify item appears in inventory (delta >= 1)."""
    before = count_in_inventory(item_id)
    if before < 0:
        before = 0
    print(f"  Collecting {item_id} at ({x},{y},{z}) (have {before})...", end="", flush=True)
    post("/bot/pickup_placed_block", {"x": x, "y": y, "z": z})
    for _ in range(max_wait_s * 2):
        time.sleep(0.5)
        after = count_in_inventory(item_id)
        if after < 0: continue
        if after > before:
            print(f" collected! (delta=+{after - before})")
            return True
        print(".", end="", flush=True)
    after = count_in_inventory(item_id)
    delta = after - before if after >= 0 else -1
    print(f" FAILED (delta={delta})")
    return False


def collect_all_blocks(item_name: str, positions: list):
    """Try to collect item at each known position. Skip if already in inventory."""
    if ensure_in_hotbar(item_name):
        return  # already have it
    for pos_str in positions:
        x, y, z = map(int, pos_str.split(","))
        if collect_block(item_name, x, y, z):
            ensure_in_hotbar(item_name)
            return
    print(f"  WARNING: Could not collect {item_name} from any known position", file=sys.stderr)


def main():
    tracked_positions = []  # (item, x, y, z) tuples

    # ── Step 1: Craft planks and sticks ──
    step(1, "Craft spruce planks (4) and sticks (4)")
    r = post("/bulk/craft", {
        "requests": [
            {"item": "spruce_planks", "count": 4},
            {"item": "stick", "count": 4},
        ]
    })
    print(f"  Result: {json.dumps(r)}")
    if r.get("status") != "ok":
        print(f"  FAILED: {r.get('message')}", file=sys.stderr); sys.exit(1)
    wait_for_idle("craft planks + sticks")

    # ── Step 2: Ensure furnace in hotbar, then smelt ──
    step(2, "Smelt raw_iron (3)")
    if not ensure_in_hotbar("minecraft:furnace"):
        print("  FAILED: Furnace not in hotbar", file=sys.stderr); sys.exit(1)
    r = post("/bulk/smelt", {
        "requests": [{"item": "raw_iron", "count": 3}]
    })
    print(f"  Result: {json.dumps(r)}")
    if r.get("status") != "ok":
        print(f"  FAILED: {r.get('message')}", file=sys.stderr); sys.exit(1)
    wait_for_idle("smelt raw_iron")

    # Record furnace position
    for pos in get("/bot/positions").get("positions", []):
        if pos not in [p[1] for p in tracked_positions]:
            x, y, z = map(int, pos.split(","))
            tracked_positions.append(("furnace", pos, x, y, z))
            print(f"  Furnace at ({x},{y},{z})")

    # ── Step 3: Wait for smelting ──
    step(3, "Wait for smelting to complete")
    for item, pos_str, x, y, z in tracked_positions:
        if item == "furnace":
            wait_for_smelt_done(x, y, z)

    # ── Step 4: Collect furnace ──
    step(4, "Collect furnace")
    furnace_positions = [p[1] for p in tracked_positions if p[0] == "furnace"]
    collect_all_blocks("minecraft:furnace", furnace_positions)

    # ── Step 5: Ensure crafting table in hotbar ──
    step(5, "Ensure crafting table in hotbar")
    if not ensure_in_hotbar("minecraft:crafting_table"):
        print("  Table not in inventory, recovering via Baritone...")
        table_positions = get("/bot/positions").get("positions", [])
        # Filter out furnace positions
        table_only = [p for p in table_positions if p not in furnace_positions]
        if table_only:
            x, y, z = map(int, table_only[-1].split(","))
            print(f"  Table at ({x},{y},{z})")
            if collect_block("minecraft:crafting_table", x, y, z):
                ensure_in_hotbar("minecraft:crafting_table")
            else:
                print("  FAILED: Could not collect table", file=sys.stderr); sys.exit(1)
        else:
            print("  FAILED: No table position and not in inventory", file=sys.stderr); sys.exit(1)

    # ── Step 6: Craft iron pickaxe ──
    step(6, "Craft iron pickaxe (1)")
    r = post("/bulk/craft", {
        "requests": [{"item": "iron_pickaxe", "count": 1}]
    })
    print(f"  Result: {json.dumps(r)}")
    if r.get("status") != "ok":
        print(f"  FAILED: {r.get('message')}", file=sys.stderr); sys.exit(1)
    wait_for_idle("craft iron pickaxe")

    # Record table position
    for pos in get("/bot/positions").get("positions", []):
        if pos not in [p[1] for p in tracked_positions]:
            x, y, z = map(int, pos.split(","))
            tracked_positions.append(("table", pos, x, y, z))
            print(f"  Table at ({x},{y},{z})")

    # ── Step 7: Cleanup — recover any remaining placed blocks ──
    step(7, "Cleanup — recover all placed blocks")
    remaining = [(item, pos_str, x, y, z) for item, pos_str, x, y, z in tracked_positions]
    for item, pos_str, x, y, z in remaining:
        mc_id = f"minecraft:{item}"
        if not ensure_in_hotbar(mc_id):
            print(f"  Recovering {item} at ({x},{y},{z})...")
            collect_block(mc_id, x, y, z)

    print("\n=== Done! Iron pickaxe should be in inventory. ===")


if __name__ == "__main__":
    main()
