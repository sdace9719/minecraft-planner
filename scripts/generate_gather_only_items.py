#!/usr/bin/env python3
"""Generate comprehensive list of items only obtainable by bulk resource gathering.

Uses PrismarineJS/minecraft-data for items + block drops and
misode/mcmeta datapack data for complete recipe coverage.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CONFIG_PATH = ROOT / "config.json"
OUTPUT_PATH = ROOT / "constants" / "gather_only_items.json"
MATERIAL_HARVEST_PATH = ROOT / "constants" / "material_harvest.json"
MOJANG_DATA_ROOT = ROOT / "mojang-data"

CREATIVE_ONLY_ITEMS: set[str] = {
    "barrier",
    "bedrock",
    "chain_command_block",
    "command_block",
    "command_block_minecart",
    "debug_stick",
    "jigsaw",
    "knowledge_book",
    "light",
    "repeating_command_block",
    "spawner",
    "structure_block",
    "structure_void",
}
BREWED_SIGNALS: tuple[str, ...] = (
    "potion",
    "lingering_potion",
    "splash_potion",
    "tipped_arrow",
)
VALID_TIERS: list[str] = ["wooden", "stone", "iron", "diamond", "netherite", "golden"]
VALID_TOOL_CLASSES: list[str] = ["pickaxe", "axe", "shovel", "hoe"]


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


def load_config() -> str:
    with CONFIG_PATH.open(encoding="utf-8") as fh:
        cfg = json.load(fh)
    version = cfg.get("minecraft_version")
    if not isinstance(version, str) or not version.strip():
        raise RuntimeError("config.json is missing a valid minecraft_version.")
    return version


def load_material_harvest() -> dict[str, dict[str, Any]]:
    """Load known harvestable items from material_harvest.json.

    Items in this file are known to be obtainable by breaking blocks,
    including probabilistic drops (e.g. flint from gravel) that may not
    appear in blocks.json drops arrays.
    """
    with MATERIAL_HARVEST_PATH.open(encoding="utf-8") as fh:
        raw = json.load(fh)
    return {k: v for k, v in raw.items() if not str(k).startswith("_")}


# ---------------------------------------------------------------------------
# Mojang datapack recipe results (ALL recipe types)
# ---------------------------------------------------------------------------


def _extract_result_item(result_field: Any) -> str | None:
    """Extract the result item name from any recipe result field."""
    if isinstance(result_field, str):
        return result_field.split(":")[-1]
    if isinstance(result_field, dict):
        item = result_field.get("id") or result_field.get("item")
        if isinstance(item, str):
            return item.split(":")[-1]
    return None


def _is_decompression_recipe(data: dict) -> bool:
    """Return True if recipe is a storage-block decompression (e.g. iron_block → 9 iron_ingot)."""
    result = data.get("result", {})
    if not isinstance(result, dict):
        return False
    if result.get("count") != 9:
        return False

    rtype = data.get("type", "")
    # Shapeless: single ingredient
    if rtype == "minecraft:crafting_shapeless":
        ingredients = data.get("ingredients", [])
        if isinstance(ingredients, list) and len(ingredients) == 1:
            return True
    # Shaped: single slot in pattern
    if rtype == "minecraft:crafting_shaped":
        pattern = data.get("pattern", [])
        key = data.get("key", {})
        if isinstance(pattern, list) and isinstance(key, dict):
            slot_count = sum(
                1 for row in pattern if isinstance(row, str)
                for ch in row if ch != " " and ch in key
            )
            if slot_count == 1:
                return True
    return False


def load_mojang_recipe_results(version: str, block_to_drops: dict[str, set[str]]) -> set[str]:
    """Parse recipe JSON files from mojang-data and return result item names.

    Excludes:
    - Decompression recipes (storage block → 9 items)
    - Ore-processing recipes where the ore already drops the result naturally
    """
    recipe_dir = MOJANG_DATA_ROOT / version / "data" / "minecraft" / "recipe"
    if not recipe_dir.is_dir():
        raise RuntimeError(f"Recipe directory not found: {recipe_dir}. Run vendor_mcmeta_data_json.py first.")
    results: set[str] = set()
    skipped_decomp = 0
    skipped_ore_processing = 0
    for path in sorted(recipe_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if _is_decompression_recipe(data):
            skipped_decomp += 1
            continue

        rtype = data.get("type", "")
        if rtype in ("minecraft:smelting", "minecraft:blasting"):
            ingredient = data.get("ingredient", {})
            ing_name: str | None = None
            if isinstance(ingredient, str):
                ing_name = ingredient.split(":")[-1]
            elif isinstance(ingredient, dict):
                ing_item = (ingredient.get("item") or ingredient.get("id") or "")
                if isinstance(ing_item, str):
                    ing_name = ing_item.split(":")[-1]
            if ing_name and ing_name in block_to_drops:
                result_item = _extract_result_item(data.get("result"))
                if result_item and result_item in block_to_drops[ing_name]:
                    skipped_ore_processing += 1
                    continue

        result_item = _extract_result_item(data.get("result"))
        if result_item:
            results.add(result_item)
    if skipped_decomp:
        print(f"  Skipped {skipped_decomp} decompression recipes")
    if skipped_ore_processing:
        print(f"  Skipped {skipped_ore_processing} ore-processing recipes (ore already drops result)")
    return results


# ---------------------------------------------------------------------------
# minecraft-data snapshot via Node.js
# ---------------------------------------------------------------------------


def load_mc_snapshot(version: str) -> dict[str, Any]:
    """Load items, block drops, recipes, and block harvest info from minecraft-data."""
    node_script = r"""
const mcDataFactory = require('minecraft-data');
const version = process.argv[1];
const mcData = mcDataFactory(version);

// --- item ID -> name map + item metadata ---
const itemById = {};
const itemInfo = {};
for (const item of mcData.itemsArray || []) {
  itemById[item.id] = item.name;
  itemInfo[item.name] = {
    displayName: item.displayName,
    stackSize: item.stackSize
  };
}

// --- block drops from blocks.json drops arrays ---
const blockDropItems = {};
for (const block of mcData.blocksArray || []) {
  if (!block.drops || block.drops.length === 0) continue;
  for (const dropId of block.drops) {
    const dropName = itemById[dropId];
    if (!dropName || dropName === 'air') continue;
    if (!blockDropItems[dropName]) blockDropItems[dropName] = new Set();
    blockDropItems[dropName].add(block.name);
  }
}
const serializedBlockDropItems = {};
for (const [item, blocks] of Object.entries(blockDropItems)) {
  serializedBlockDropItems[item] = Array.from(blocks).sort();
}

// --- block self-drops: blocks whose own item form exists (silk touch drops) ---
const blockSelfDrops = {};
for (const [blockName, block] of Object.entries(mcData.blocksByName || {})) {
  if (!block.diggable) continue;
  if (itemInfo[blockName]) {
    // This block has an item with the same name — it drops itself with silk touch
    blockSelfDrops[blockName] = true;
  }
}

// --- recipe results from minecraft-data recipes.json (excluding decompression) ---
const mcRecipeResults = new Set();
for (const recipes of Object.values(mcData.recipes || {})) {
  if (!Array.isArray(recipes)) continue;
  for (const recipe of recipes) {
    if (!recipe.result || recipe.result.id == null) continue;
    // Skip decompression recipes: result count == 9 with 1 ingredient
    if (recipe.result.count === 9) {
      let ingredientCount = 0;
      if (recipe.inShape) {
        for (const row of recipe.inShape) {
          if (Array.isArray(row)) {
            for (const slot of row) {
              if (slot !== null) ingredientCount++;
            }
          }
        }
      } else if (Array.isArray(recipe.ingredients)) {
        ingredientCount = recipe.ingredients.length;
      }
      if (ingredientCount === 1) continue;
    }
    const name = itemById[recipe.result.id];
    if (name) mcRecipeResults.add(name);
  }
}

// --- block harvest info ---
const blockHarvest = {};
for (const [blockName, block] of Object.entries(mcData.blocksByName || {})) {
  const toolNames = new Set();
  for (const toolId of Object.keys(block.harvestTools || {})) {
    const item = mcData.items[Number.parseInt(toolId, 10)];
    if (item && item.name) toolNames.add(item.name);
  }
  const harvestToolCount = Object.keys(block.harvestTools || {}).length;
  blockHarvest[blockName] = {
    toolNames: Array.from(toolNames).sort(),
    hardness: block.hardness,
    diggable: Boolean(block.diggable),
    handInstaHarvest: Boolean(block.diggable) && Number(block.hardness) === 0 && harvestToolCount === 0,
  };
}

console.log(JSON.stringify({
  items: itemInfo,
  blockDropItems: serializedBlockDropItems,
  blockSelfDrops: Object.keys(blockSelfDrops).sort(),
  mcRecipeResults: Array.from(mcRecipeResults).sort(),
  blockHarvest: blockHarvest,
}));
"""
    result = subprocess.run(
        ["node", "-e", node_script, version],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Failed to load minecraft-data snapshot:\n{result.stderr.strip()}")
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid JSON from minecraft-data snapshot: {exc}") from exc
    return data


# ---------------------------------------------------------------------------
# Filtering helpers
# ---------------------------------------------------------------------------


def is_excluded_item(item_name: str) -> bool:
    """Check if an item is creative-only, spawn egg, or explicitly excluded."""
    if item_name.endswith("_spawn_egg"):
        return True
    if item_name in CREATIVE_ONLY_ITEMS:
        return True
    if item_name == "enchanted_book":
        return True
    return False


def is_brewed_item(item_name: str) -> bool:
    """Check if an item is a potion / tipped arrow variant."""
    return any(signal in item_name for signal in BREWED_SIGNALS)


# ---------------------------------------------------------------------------
# Harvest info derivation
# ---------------------------------------------------------------------------


def derive_tool_info(tool_names: list[str]) -> tuple[str, str]:
    """Return (tool_class, min_tier) from a list of harvest tool item names."""
    parsed: list[tuple[str, str]] = []
    for name in tool_names:
        for tc in VALID_TOOL_CLASSES:
            suffix = f"_{tc}"
            if name.endswith(suffix):
                tier = name[: -len(suffix)]
                if tier in VALID_TIERS:
                    parsed.append((tier, tc))
                    break
    if not parsed:
        return "none", "wooden"
    min_tier = min(parsed, key=lambda x: VALID_TIERS.index(x[0]))[0]
    # If multiple tool classes, pick the first alphabetically
    tool_class = sorted({p[1] for p in parsed})[0]
    return tool_class, min_tier


def get_harvest_for_block(block_name: str, block_harvest: dict) -> dict[str, Any]:
    """Build harvest metadata for a specific source block."""
    info = block_harvest.get(block_name, {})
    if not info:
        return {
            "tool_class": "none",
            "min_tier": "wooden",
            "hand_insta_harvest_possible": False,
        }
    tool_names = info.get("toolNames", [])
    tool_class, min_tier = derive_tool_info(tool_names)
    return {
        "tool_class": tool_class,
        "min_tier": min_tier,
        "hand_insta_harvest_possible": info.get("handInstaHarvest", False),
    }


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------


def main() -> None:
    version = load_config()
    print(f"Minecraft version: {version}")

    # 1. Load minecraft-data snapshot (needed first for block->drop reverse map)
    print(f"Loading minecraft-data snapshot for {version} ...")
    mc = load_mc_snapshot(version)
    items: dict[str, dict] = mc["items"]
    block_drop_items: dict[str, list[str]] = mc["blockDropItems"]
    block_self_drops: list[str] = mc["blockSelfDrops"]
    mc_recipe_results: list[str] = mc["mcRecipeResults"]
    block_harvest: dict[str, dict] = mc["blockHarvest"]

    print(f"  {len(items)} total items")
    print(f"  {len(block_drop_items)} items from block drops (non-silk-touch)")
    print(f"  {len(block_self_drops)} items matching block names (silk-touch)")
    print(f"  {len(mc_recipe_results)} crafting recipe results from minecraft-data")

    # Build reverse map: block_name -> set of items it drops naturally
    block_to_drops: dict[str, set[str]] = {}
    for item_name, source_blocks in block_drop_items.items():
        for block_name in source_blocks:
            block_to_drops.setdefault(block_name, set()).add(item_name)
    print(f"  {len(block_to_drops)} blocks with natural drops mapped")

    # 2. Load mojang recipe results (uses block_to_drops for ore-processing filter)
    print("Loading mojang-data recipes ...")
    mojang_recipe_results = load_mojang_recipe_results(version, block_to_drops)
    print(f"  {len(mojang_recipe_results)} recipe result items from mojang-data")

    # 3. Load material_harvest for supplementary harvestable items
    material_harvest = load_material_harvest()
    harvest_known_items = set(material_harvest.keys())
    print(f"  {len(harvest_known_items)} items in material_harvest.json")

    # 4. Combine recipe results from both sources
    all_recipe_results: set[str] = mojang_recipe_results | set(mc_recipe_results)
    print(f"  {len(all_recipe_results)} combined unique recipe results")

    # 5. Build the set of all items obtainable by breaking blocks
    # Includes: guaranteed drops, silk-touch self-drops, AND known probabilistic drops
    block_obtainable: set[str] = (
        set(block_drop_items.keys())
        | set(block_self_drops)
        | harvest_known_items
    )
    print(f"  {len(block_obtainable)} items obtainable by breaking blocks (total)")

    # 5. Filter items
    gather_only: dict[str, dict] = {}
    excluded: dict[str, list[str]] = {
        "creative_or_spawn_egg": [],
        "brewed": [],
        "has_recipe": [],
        "no_block_drop": [],
    }

    for item_name in sorted(items.keys()):
        if item_name == "air":
            continue

        if is_excluded_item(item_name):
            excluded["creative_or_spawn_egg"].append(item_name)
            continue

        if is_brewed_item(item_name):
            excluded["brewed"].append(item_name)
            continue

        if item_name in all_recipe_results:
            excluded["has_recipe"].append(item_name)
            continue

        if item_name not in block_obtainable:
            excluded["no_block_drop"].append(item_name)
            continue

        # --- Item survived all filters: include it ---
        source_blocks: list[str] = list(block_drop_items.get(item_name, []))

        # If item only comes from self-drops (silk touch), use the block name
        if not source_blocks and item_name in block_self_drops:
            source_blocks = [item_name]

        # Determine harvest info
        if item_name in material_harvest:
            # Prefer material_harvest entry (has explicit tool_class/min_tier)
            mh_entry = material_harvest[item_name]
            harvest = {
                "tool_class": str(mh_entry.get("tool_class", "none")),
                "min_tier": str(mh_entry.get("min_tier", "wooden")),
                "hand_insta_harvest_possible": bool(
                    mh_entry.get("hand_insta_harvest_possible", False)
                ),
            }
        elif source_blocks:
            primary_block = source_blocks[0]
            harvest = get_harvest_for_block(primary_block, block_harvest)
        else:
            harvest = {
                "tool_class": "none",
                "min_tier": "wooden",
                "hand_insta_harvest_possible": False,
            }

        # Determine silk_touch_required
        in_guaranteed_drops = item_name in block_drop_items
        in_self_drops = item_name in block_self_drops
        silk_touch_required = (not in_guaranteed_drops and in_self_drops)

        # Probabilistic drops: items in material_harvest but not in any blocks.json drops
        probabilistic = (
            item_name not in block_drop_items
            and item_name not in block_self_drops
            and item_name in material_harvest
        )

        gather_only[item_name] = {
            "name": item_name,
            "display_name": items[item_name]["displayName"],
            "stack_size": items[item_name]["stackSize"],
            "source_blocks": source_blocks if source_blocks else [],
            "harvest": harvest,
            "silk_touch_required": silk_touch_required,
            "always_drops": not probabilistic,
        }

        if probabilistic and not source_blocks:
            gather_only[item_name]["_note"] = (
                "Probabilistic or conditional drop. Source block mapping "
                "unavailable from blocks.json; cross-referenced from material_harvest.json."
            )

    # 6. Print summary
    print()
    print("Filtering summary:")
    print(f"  Excluded (creative/spawn egg): {len(excluded['creative_or_spawn_egg'])}")
    print(f"  Excluded (brewed):            {len(excluded['brewed'])}")
    print(f"  Excluded (has recipe):        {len(excluded['has_recipe'])}")
    print(f"  Excluded (no block drop):     {len(excluded['no_block_drop'])}")
    print(f"  INCLUDED (gather only):       {len(gather_only)}")

    # 7. Write output
    output: dict[str, Any] = {
        "minecraft_version": version,
        "edition": "java",
        "data_source": (
            "PrismarineJS/minecraft-data (items, blocks, recipes) + "
            "misode/mcmeta (comprehensive datapack recipes)"
        ),
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "total_items": len(gather_only),
        "methodology": (
            "Items that drop from breaking blocks (including silk-touch drops) "
            "and have no crafting, smelting, blasting, smoking, campfire cooking, "
            "stonecutting, or smithing recipe. "
            "Creative-only items, spawn eggs, enchanted books, and potion variants "
            "are excluded. Items obtainable only from entities (mob drops) or "
            "structure chests are naturally excluded because they have no block source."
        ),
        "known_limitations": [
            "Villager and wandering-trader trades are hardcoded in the game JAR "
            "and are not filtered by this script. Some items in this list may also "
            "be obtainable via trading; however, their PRIMARY source is still "
            "block gathering.",
            "Items dropped exclusively by entities (e.g., blaze_rod, ghast_tear) "
            "are excluded because they are not obtained by breaking blocks.",
        ],
        "items": gather_only,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = OUTPUT_PATH.with_suffix(".json.tmp")
    with tmp_path.open("w", encoding="utf-8") as fh:
        json.dump(output, fh, indent=2)
        fh.write("\n")
    tmp_path.replace(OUTPUT_PATH)
    print(f"\nWrote {len(gather_only)} items to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
