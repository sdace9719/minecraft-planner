"""Swap an axe from main inventory to hotbar via controlbridge."""
import sys
import time
import requests

CONTROLBRIDGE = "http://localhost:8765"
AXE_TYPES = ("minecraft:stone_axe", "minecraft:copper_axe")
JUNK = {"minecraft:dirt", "minecraft:cobblestone", "minecraft:netherrack", "minecraft:stone"}
SKIP = JUNK | {"minecraft:iron_pickaxe", "minecraft:stone_pickaxe", "minecraft:diamond_pickaxe",
               "minecraft:wooden_pickaxe", "minecraft:golden_pickaxe", "minecraft:netherite_pickaxe",
               "minecraft:copper_pickaxe"}


def main():
    # 1. Read inventory
    resp = requests.get(f"{CONTROLBRIDGE}/inventory", timeout=5)
    resp.raise_for_status()
    inv = resp.json()

    # 2. Find axe in main inventory (slots 9-35)
    axe_slot = None
    axe_name = None
    for slot in inv:
        s = slot["slot"]
        if slot["item"] in AXE_TYPES and 9 <= s <= 35:
            axe_slot = s
            axe_name = slot["item"]
            break

    if axe_slot is None:
        print("ERROR: no axe found in main inventory")
        sys.exit(1)

    plain_name = axe_name.split(":", 1)[1]
    print(f"Found {axe_name} in slot {axe_slot}")

    # 3. Scan hotbar (slots 0-8), find first non-junk slot to swap with
    hotbar_slots = {s["slot"]: s["item"] for s in inv if s["slot"] < 9}
    skip_slots = [s for s, item in hotbar_slots.items() if item in SKIP]
    target_slots = [s for s, item in hotbar_slots.items() if item not in SKIP]

    print(f"  Skipped slots (junk+pickaxes): {skip_slots}")
    print(f"  Eligible swap slots: {target_slots}")

    hotbar_item = None
    if target_slots:
        target_slot = target_slots[0]
        hotbar_item_name = hotbar_slots[target_slot]
        hotbar_item = hotbar_item_name.split(":", 1)[1]
        print(f"  Targeting hotbar slot {target_slot} ({hotbar_item})")
    else:
        print("  No eligible hotbar slots, nothing to swap")
        sys.exit(1)

    # 4. Send swap request
    body = {"itemsToHotbar": [plain_name]}
    if hotbar_item:
        body["itemsFromHotbar"] = [hotbar_item]

    print(f"Swapping {plain_name} to hotbar ...")
    resp = requests.post(
        f"{CONTROLBRIDGE}/bot/swap-hotbar",
        json=body,
        timeout=10,
    )
    result = resp.json()
    print(f"  response: {result}")

    if result.get("status") != "ok" or result.get("swapped", 0) == 0:
        print(f"ERROR: swap-hotbar failed: {result}")
        sys.exit(1)

    # 5. Verify axe landed in hotbar
    for attempt in range(20):
        time.sleep(0.10)
        inv = requests.get(f"{CONTROLBRIDGE}/inventory", timeout=5).json()
        for slot in inv:
            if slot.get("item") == axe_name and slot.get("slot", 99) < 9:
                print(f"  VERIFIED: {plain_name} in hotbar slot {slot['slot']}")
                return
    print(f"ERROR: {plain_name} did not reach hotbar after 2s")


if __name__ == "__main__":
    main()
