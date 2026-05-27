#!/usr/bin/env python3
"""Full iron pickaxe crafting flow with Baritone pathfinding and inventory verification.

Steps:
  1. Craft planks + sticks (bulk, all 2x2)
  2. Smelt raw_iron
  3. Wait for smelting to complete (poll furnace burning state)
  4. Collect furnace via Baritone goto + inventory delta check
  5. Craft iron_pickaxe (3x3 — table left in world by skipBreak)
  6. Collect crafting table via Baritone goto + inventory delta check

Requires: spruce logs -> planks, raw_iron, coal, crafting table, furnace, Baritone mod.
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
    """Count total items of given minecraft:id in player inventory."""
    try:
        inv = get("/inventory")
    except Exception:
        return -1
    if not isinstance(inv, list):
        return -1
    return sum(e.get("count", 0) for e in inv if e.get("item") == item_id)


def ensure_in_hotbar(item_name: str) -> bool:
    """Check inventory, swap to hotbar if in main inv, verify it worked."""
    inv = get("/inventory")
    in_hotbar = any(e.get("item") == item_name and e.get("slot", 99) < 9 for e in (inv if isinstance(inv, list) else []))
    if in_hotbar:
        print(f"  {item_name} already in hotbar")
        return True
    in_main = any(e.get("item") == item_name and e.get("slot", 99) >= 9 for e in (inv if isinstance(inv, list) else []))
    if in_main:
        print(f"  Swapping {item_name} to hotbar...", end="", flush=True)
        post("/bot/swap-hotbar", {"itemsToHotbar": [item_name.split(":")[-1]]})
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
    """Send Baritone to block position, verify item appears in inventory (delta >= 1)."""
    before = count_in_inventory(item_id)
    if before < 0:
        print(f"  WARNING: Could not read inventory before goto")
        before = 0

    print(f"  Collecting {item_id} at ({x},{y},{z}) (have {before})...", end="", flush=True)
    post("/bot/pickup_placed_block", {"x": x, "y": y, "z": z})

    for _ in range(max_wait_s * 2):
        time.sleep(0.5)
        after = count_in_inventory(item_id)
        if after < 0:
            continue
        if after > before:
            print(f" collected! (delta=+{after - before})")
            return True
        print(".", end="", flush=True)

    after = count_in_inventory(item_id)
    delta = after - before if after >= 0 else -1
    print(f" FAILED (delta={delta})")
    return False


def main():
    # ── Step 1: Craft planks and sticks ──
    step(1, "Craft spruce planks (12) and sticks (8)")
    r = post("/bulk/craft", {
        "requests": [
            {"item": "spruce_planks", "count": 4},
            {"item": "stick", "count": 4},
        ]
    })
    print(f"  Result: {json.dumps(r)}")
    if r.get("status") != "ok":
        print(f"  FAILED: {r.get('message')}", file=sys.stderr)
        sys.exit(1)
    wait_for_idle("craft planks + sticks")

    # ── Step 2: Ensure furnace in hotbar, then smelt ──
    step(2, "Smelt raw_iron (3)")
    if not ensure_in_hotbar("minecraft:furnace"):
        print("  FAILED: Furnace not in hotbar", file=sys.stderr)
        sys.exit(1)
    r = post("/bulk/smelt", {
        "requests": [{"item": "raw_iron", "count": 3}]
    })
    print(f"  Result: {json.dumps(r)}")
    if r.get("status") != "ok":
        print(f"  FAILED: {r.get('message')}", file=sys.stderr)
        sys.exit(1)
    wait_for_idle("smelt raw_iron")

    # Get furnace position
    positions = get("/bot/positions").get("positions", [])
    fx = fy = fz = None
    if positions:
        fx, fy, fz = map(int, positions[0].split(","))
        print(f"  Furnace at ({fx},{fy},{fz})")

    # ── Step 3: Wait for smelting to finish ──
    step(3, "Wait for smelting to complete")
    if fx is not None:
        wait_for_smelt_done(fx, fy, fz)

    # ── Step 4: Collect furnace via Baritone ──
    step(4, "Collect furnace")
    if fx is not None:
        if not collect_block("minecraft:furnace", fx, fy, fz):
            print("  WARNING: Could not collect furnace, proceeding anyway", file=sys.stderr)
    else:
        print("  WARNING: No furnace position available, skipping")

    # ── Step 5: Ensure crafting table in hotbar ──
    step(5, "Ensure crafting table is in hotbar")
    if not ensure_in_hotbar("minecraft:crafting_table"):
        # Not in inventory — recover via Baritone from known position
        print("  Table not in inventory, recovering via Baritone...")
        table_positions = get("/bot/positions").get("positions", [])
        if table_positions:
            tx, ty, tz = map(int, table_positions[0].split(","))
            print(f"  Table at ({tx},{ty},{tz})")
            if collect_block("minecraft:crafting_table", tx, ty, tz):
                ensure_in_hotbar("minecraft:crafting_table")
            else:
                print("  FAILED: Could not collect table", file=sys.stderr)
                sys.exit(1)
        else:
            print("  FAILED: No table position and not in inventory", file=sys.stderr)
            sys.exit(1)

    # ── Step 6: Craft iron pickaxe ──
    step(6, "Craft iron pickaxe (1)")
    r = post("/bulk/craft", {
        "requests": [{"item": "iron_pickaxe", "count": 1}]
    })
    print(f"  Result: {json.dumps(r)}")
    if r.get("status") != "ok":
        print(f"  FAILED: {r.get('message')}", file=sys.stderr)
        sys.exit(1)
    wait_for_idle("craft iron pickaxe")

    print("\n=== Done! Iron pickaxe should be in inventory. ===")


if __name__ == "__main__":
    main()
