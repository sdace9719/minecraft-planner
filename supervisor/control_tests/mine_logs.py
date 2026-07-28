"""Swap stone_axe to hotbar, mine 8 more spruce_logs via controlbridge."""

import sys
import time

import requests
from mcctp import SyncMCCTPClient, Actions

CONTROLBRIDGE = "http://localhost:8765"
AXE_TYPES = ("minecraft:stone_axe", "minecraft:copper_axe")
JUNK = {"minecraft:dirt", "minecraft:cobblestone", "minecraft:netherrack", "minecraft:stone"}
SKIP = JUNK | {"minecraft:iron_pickaxe", "minecraft:stone_pickaxe", "minecraft:diamond_pickaxe",
               "minecraft:wooden_pickaxe", "minecraft:golden_pickaxe", "minecraft:netherite_pickaxe",
               "minecraft:copper_pickaxe"}


def count_inventory(item_name: str) -> int:
    """Count total of an item in the player's inventory via controlbridge."""
    resp = requests.get(f"{CONTROLBRIDGE}/inventory", timeout=5)
    resp.raise_for_status()
    total = 0
    for slot in resp.json():
        if slot.get("item", "").endswith(":" + item_name):
            total += slot.get("count", 0)
    return total


def start_mining(block: str, count: int) -> bool:
    """Tell Baritone to mine blocks until count total items are obtained."""
    resp = requests.post(
        f"{CONTROLBRIDGE}/bot/mine",
        json={"block": block, "count": count},
        timeout=5,
    )
    return resp.json().get("status") == "ok"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
with SyncMCCTPClient("localhost", 8770) as client:
    time.sleep(1)

    # 1. Read inventory, find axe in main inventory and map hotbar slots
    inv = requests.get(f"{CONTROLBRIDGE}/inventory", timeout=5).json()

    axe_slot_main = None
    axe_name = None
    hotbar_slots = {}
    for slot in inv:
        s = slot["slot"]
        if slot["item"] in AXE_TYPES and 9 <= s <= 35:
            if axe_slot_main is None:
                axe_slot_main = s
                axe_name = slot["item"]
        elif s < 9:
            hotbar_slots[s] = slot["item"]

    if axe_slot_main is None:
        print("ERROR: neither stone_axe nor copper_axe found in main inventory.")
        sys.exit(1)

    plain_name = axe_name.split(":", 1)[1]
    print(f"Found {axe_name} in slot {axe_slot_main}")

    # 2. Scan hotbar for eligible swap slots (not junk, not pickaxe)
    skip_slots = [s for s, item in hotbar_slots.items() if item in SKIP]
    target_slots = [s for s, item in hotbar_slots.items() if item not in SKIP]

    print(f"  Skipped slots (junk+pickaxes): {skip_slots}")
    print(f"  Eligible swap slots: {target_slots}")

    if not target_slots:
        print("ERROR: no eligible hotbar slots, nothing to swap")
        sys.exit(1)

    target_slot = target_slots[0]
    hotbar_item = hotbar_slots[target_slot].split(":", 1)[1]
    print(f"  Targeting hotbar slot {target_slot} ({hotbar_item})")

    # 3. Send swap request
    swap_body = {"itemsToHotbar": [plain_name], "itemsFromHotbar": [hotbar_item]}
    print(f"Swapping {plain_name} to hotbar ...")
    resp = requests.post(f"{CONTROLBRIDGE}/bot/swap-hotbar", json=swap_body, timeout=10)
    result = resp.json()
    if result.get("status") != "ok" or result.get("swapped", 0) == 0:
        print(f"ERROR: swap-hotbar failed: {result}")
        sys.exit(1)
    print(f"  swap packet sent")

    # 4. Poll inventory for axe in hotbar
    axe_slot = None
    for attempt in range(20):
        time.sleep(0.25)
        inv = requests.get(f"{CONTROLBRIDGE}/inventory", timeout=5).json()
        for slot in inv:
            if slot.get("item") == axe_name and slot.get("slot", 99) < 9:
                axe_slot = slot["slot"]
                break
        if axe_slot is not None:
            print(f"  axe confirmed in hotbar slot {axe_slot} after {(attempt + 1) * 0.25:.1f}s")
            break

    if axe_slot is None:
        print(f"ERROR: {plain_name} did not end up in hotbar after 5s of retries.")
        sys.exit(1)

    client.send(Actions.select_slot(axe_slot))
    print(f"  axe in hotbar slot {axe_slot}, selected")

    # 5. Count spruce_logs and compute target
    current = count_inventory("spruce_log")
    target = current + 8
    print(f"Current spruce_log: {current}  →  target: {target}")

    # 6. Start mining
    print(f"Sending mine request: block=spruce_log, count={target}")
    if not start_mining("spruce_log", target):
        print("ERROR: Mining request failed.")
        sys.exit(1)
    print("  Mining started OK. Waiting for completion ...")

    # 7. Poll inventory to verify mining completed
    VERIFY_TIMEOUT_S = 120
    POLL_INTERVAL_S = 0.5
    max_attempts = int(VERIFY_TIMEOUT_S / POLL_INTERVAL_S)

    for attempt in range(max_attempts):
        time.sleep(POLL_INTERVAL_S)
        try:
            current = count_inventory("spruce_log")
        except requests.RequestException as e:
            if attempt % 10 == 0:
                print(f"\n  [warn] Inventory check failed: {e}", flush=True)
            continue
        if current >= target:
            print(f" done! ({current} spruce_log, target {target}) "
                  f"after ~{(attempt + 1) * POLL_INTERVAL_S:.0f}s")
            break
        if attempt % 10 == 0:
            print(".", end="", flush=True)
    else:
        print(" timeout!")
        current = count_inventory("spruce_log")
        print(f"ERROR: Mining did not complete within {VERIFY_TIMEOUT_S}s. "
              f"spruce_log count: {current}, target: {target}")
        sys.exit(1)

    print("Done. 8 additional spruce_logs mined successfully.")
