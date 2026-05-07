#!/usr/bin/env python3
"""Phase 1 static blueprint generation (craft/smelt/gather only)."""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mojang_datapack.recipes import DatapackRecipe, DatapackRecipeIndex


CONFIG_PATH = ROOT / "config.json"
MATERIAL_HARVEST_PATH = ROOT / "constants" / "material_harvest.json"
OUTPUT_PATH = ROOT / "constants" / "blueprints.json"
MOJANG_DATA_ROOT = ROOT / "mojang-data"
VALID_TIERS = ["wooden", "stone", "iron", "diamond", "netherite", "golden"]
VALID_TOOL_CLASSES = ["axe", "pickaxe", "shovel", "hoe"]
CREATIVE_ONLY_ITEMS = {
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


class BlueprintGenerationError(RuntimeError):
    """Raised when the static blueprint graph cannot be generated."""


class UnresolvableTerminalItem(BlueprintGenerationError):
    """Raised when a non-recipe item has no mining/gather rule."""


class CircularDependencyError(BlueprintGenerationError):
    """Raised when DFS encounters a cycle in recipe expansion."""


@dataclass(frozen=True)
class MCDataSnapshot:
    items: tuple[str, ...]
    drop_sources: dict[str, tuple[str, ...]]
    entity_sources: dict[str, tuple[str, ...]]
    block_tool_names: dict[str, tuple[str, ...]]
    block_hand_insta_harvest_possible: dict[str, bool]


@dataclass(frozen=True)
class SourceOverride:
    operation: str
    harvest: dict[str, Any]
    source_blocks: tuple[str, ...] = ()
    source_entities: tuple[str, ...] = ()
    source_structures: tuple[str, ...] = ()


TERMINAL_SOURCE_OVERRIDES: dict[str, SourceOverride] = {
    "cobweb": SourceOverride(
        operation="sword",
        harvest={"tool_class": "sword", "min_tier": "wooden", "hand_insta_harvest_possible": False},
        source_blocks=("cobweb",),
    ),
}

# Optional explicit mappings for items known to be chest-only in this planner model.
STRUCTURE_CHEST_ONLY_ITEMS: dict[str, tuple[str, ...]] = {}
NETHER_KEYWORDS = (
    "nether",
    "quartz",
    "blaze",
    "ghast",
    "magma_cream",
    "netherrack",
    "soul_",
    "warped_",
    "crimson_",
    "blackstone",
    "basalt",
    "ancient_debris",
    "glowstone",
    "shroomlight",
)
BOOTSTRAP_WOODEN_TOOL_ITEMS = {"cobblestone"}


def load_version() -> str:
    with CONFIG_PATH.open(encoding="utf-8") as handle:
        cfg = json.load(handle)
    version = cfg.get("minecraft_version")
    if not isinstance(version, str) or not version.strip():
        raise BlueprintGenerationError("config.json is missing a valid minecraft_version.")
    return version


def load_material_harvest() -> dict[str, dict[str, Any]]:
    with MATERIAL_HARVEST_PATH.open(encoding="utf-8") as handle:
        raw = json.load(handle)
    return {k: v for k, v in raw.items() if not str(k).startswith("_")}


def load_datapack(version: str) -> DatapackRecipeIndex:
    recipe_dir = MOJANG_DATA_ROOT / version / "data" / "minecraft" / "recipe"
    item_tag_dir = MOJANG_DATA_ROOT / version / "data" / "minecraft" / "tags" / "item"
    if not recipe_dir.exists():
        raise BlueprintGenerationError(f"Missing recipe directory: {recipe_dir}")
    index = DatapackRecipeIndex(recipe_dir, item_tag_dir=item_tag_dir)
    index.load()
    return index


def load_mc_snapshot(version: str) -> MCDataSnapshot:
    node_script = """
const mcDataFactory = require('minecraft-data');
const version = process.argv[1];
const mcData = mcDataFactory(version);
const allItems = Object.keys(mcData.itemsByName || {}).sort();
const dropSources = {};
for (const loot of Object.values(mcData.blockLoot || {})) {
  const block = loot.block;
  for (const drop of (loot.drops || [])) {
    if (!drop || !drop.item) continue;
    if (!dropSources[drop.item]) dropSources[drop.item] = new Set();
    dropSources[drop.item].add(block);
  }
}
const serializedDropSources = {};
for (const [item, blocks] of Object.entries(dropSources)) {
  serializedDropSources[item] = Array.from(blocks).sort();
}
const entitySources = {};
for (const loot of Object.values(mcData.entityLoot || {})) {
  const entity = loot.entity;
  for (const drop of (loot.drops || [])) {
    if (!drop || !drop.item) continue;
    if (!entitySources[drop.item]) entitySources[drop.item] = new Set();
    entitySources[drop.item].add(entity);
  }
}
const serializedEntitySources = {};
for (const [item, entities] of Object.entries(entitySources)) {
  serializedEntitySources[item] = Array.from(entities).sort();
}
const blockToolNames = {};
const blockHandInstaHarvestPossible = {};
for (const [blockName, block] of Object.entries(mcData.blocksByName || {})) {
  const toolNames = new Set();
  const harvestTools = block.harvestTools || {};
  const harvestToolCount = Object.keys(harvestTools).length;
  for (const toolId of Object.keys(harvestTools)) {
    const parsedId = Number.parseInt(toolId, 10);
    const item = mcData.items[parsedId];
    if (item && item.name) toolNames.add(item.name);
  }
  blockToolNames[blockName] = Array.from(toolNames).sort();
  blockHandInstaHarvestPossible[blockName] = Boolean(block.diggable) && Number(block.hardness) === 0 && harvestToolCount === 0;
}
console.log(JSON.stringify({
  items: allItems,
  dropSources: serializedDropSources,
  entitySources: serializedEntitySources,
  blockToolNames,
  blockHandInstaHarvestPossible
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
        raise BlueprintGenerationError(f"Unable to load minecraft-data snapshot: {result.stderr.strip()}")
    data = json.loads(result.stdout)
    items = tuple(sorted(str(name) for name in data["items"]))
    drop_sources = {str(k): tuple(v) for k, v in data["dropSources"].items()}
    entity_sources = {str(k): tuple(v) for k, v in data["entitySources"].items()}
    block_tool_names = {str(k): tuple(v) for k, v in data["blockToolNames"].items()}
    block_hand_insta_harvest_possible = {str(k): bool(v) for k, v in data["blockHandInstaHarvestPossible"].items()}
    return MCDataSnapshot(
        items=items,
        drop_sources=drop_sources,
        entity_sources=entity_sources,
        block_tool_names=block_tool_names,
        block_hand_insta_harvest_possible=block_hand_insta_harvest_possible,
    )


def is_brewed_item(item_name: str) -> bool:
    brewed_signals = ("potion", "lingering_potion", "splash_potion", "tipped_arrow")
    return any(signal in item_name for signal in brewed_signals)


def is_creative_only_item(item_name: str) -> bool:
    if item_name.endswith("_spawn_egg"):
        return True
    return item_name in CREATIVE_ONLY_ITEMS


def is_explicitly_excluded_item(item_name: str) -> bool:
    return item_name == "enchanted_book"


def is_nether_item(item_name: str) -> bool:
    return any(keyword in item_name for keyword in NETHER_KEYWORDS)


def is_salvage_source_item(item_name: str) -> bool:
    suffixes = (
        "_pickaxe",
        "_axe",
        "_shovel",
        "_hoe",
        "_sword",
        "_helmet",
        "_chestplate",
        "_leggings",
        "_boots",
        "_horse_armor",
    )
    return item_name.endswith(suffixes)


def hand_insta_harvest_possible_for_source_blocks(source_blocks: list[str], snapshot: MCDataSnapshot) -> bool:
    if not source_blocks:
        return False
    primary_block = source_blocks[0]
    if primary_block not in snapshot.block_hand_insta_harvest_possible:
        raise BlueprintGenerationError(
            f"Missing block hand-insta metadata for source block {primary_block}. Cannot infer hand_insta_harvest_possible."
        )
    return bool(snapshot.block_hand_insta_harvest_possible[primary_block])


def parse_tool_name(tool_name: str) -> tuple[str | None, str | None]:
    for tool_class in VALID_TOOL_CLASSES:
        suffix = f"_{tool_class}"
        if tool_name.endswith(suffix):
            tier = tool_name[: -len(suffix)]
            if tier in VALID_TIERS:
                return tier, tool_class
    return None, None


def rule_from_block_tools(block_name: str, block_tool_names: dict[str, tuple[str, ...]]) -> dict[str, Any]:
    tool_names = block_tool_names.get(block_name, ())
    if not tool_names:
        return {
            "tool_class": "none",
            "min_tier": "wooden",
            "hand_insta_harvest_possible": False,
        }

    parsed: list[tuple[str, str]] = []
    for tool_name in tool_names:
        tier, tool_class = parse_tool_name(tool_name)
        if tier is None or tool_class is None:
            continue
        parsed.append((tier, tool_class))

    if not parsed:
        raise BlueprintGenerationError(
            f"Unable to parse tool tier/class for source block {block_name}. "
            "Add explicit mapping in constants/material_harvest.json."
        )

    min_tier = min(parsed, key=lambda entry: VALID_TIERS.index(entry[0]))[0]
    tool_class = sorted({entry[1] for entry in parsed})[0]
    return {
        "tool_class": tool_class,
        "min_tier": min_tier,
        "hand_insta_harvest_possible": False,
    }


def choose_recipe(
    candidates: list[DatapackRecipe],
    result_item: str,
    *,
    allowed_items: set[str] | None = None,
) -> DatapackRecipe | None:
    if not candidates:
        return None

    def relation_penalty(recipe: DatapackRecipe) -> int:
        penalty = 0
        for ingredient in recipe.ingredients:
            if ingredient == result_item:
                penalty += 100
            if ingredient in result_item or result_item in ingredient:
                penalty += 10
            if ingredient.endswith("_nugget") and result_item == ingredient.replace("_nugget", "_ingot"):
                penalty += 50
            if ingredient.endswith("_ingot") and result_item == ingredient.replace("_ingot", "_block"):
                penalty += 5
        return penalty

    def sort_key(recipe: DatapackRecipe) -> tuple[Any, ...]:
        action_priority = 0 if recipe.action == "smelt" else 1
        return (
            relation_penalty(recipe),
            action_priority,
            len(recipe.ingredients),
            sum(recipe.ingredients.values()),
            recipe.station,
            recipe.raw_type,
            tuple(sorted(recipe.ingredients.items())),
        )

    filtered = [recipe for recipe in candidates if result_item not in recipe.ingredients]
    if allowed_items is not None:
        filtered = [
            recipe for recipe in filtered if all(ingredient in allowed_items for ingredient in recipe.ingredients)
        ]
    if not filtered:
        return None
    return sorted(filtered, key=sort_key)[0]


def rank_recipes(candidates: list[DatapackRecipe], result_item: str) -> list[DatapackRecipe]:
    ranked: list[DatapackRecipe] = []
    for recipe in candidates:
        if result_item.endswith("_ingot") and recipe.raw_type == "minecraft:blasting":
            continue
        if recipe.result == result_item and result_item in recipe.ingredients:
            continue
        if any(is_nether_item(ingredient) for ingredient in recipe.ingredients):
            continue
        if result_item == "stick":
            ingredient_names = set(recipe.ingredients.keys())
            if "bamboo" in ingredient_names:
                continue
            if not ingredient_names or any(not name.endswith("_planks") for name in ingredient_names):
                continue
        if recipe.action == "smelt" and result_item.endswith("_nugget"):
            if any(is_salvage_source_item(name) for name in recipe.ingredients):
                continue
        ranked.append(recipe)
    if not ranked:
        return []

    def relation_penalty(recipe: DatapackRecipe) -> int:
        penalty = 0
        for ingredient in recipe.ingredients:
            if ingredient in result_item or result_item in ingredient:
                penalty += 10
            if ingredient.endswith("_nugget") and result_item == ingredient.replace("_nugget", "_ingot"):
                penalty += 50
            if ingredient.endswith("_ingot") and result_item == ingredient.replace("_ingot", "_block"):
                penalty += 5
        return penalty

    return sorted(
        ranked,
        key=lambda recipe: (
            relation_penalty(recipe),
            0 if recipe.action == "smelt" else 1,
            len(recipe.ingredients),
            sum(recipe.ingredients.values()),
            recipe.station,
            recipe.raw_type,
            tuple(sorted(recipe.ingredients.items())),
        ),
    )


def rank_recipes_for_targets(
    candidates: list[DatapackRecipe],
    result_item: str,
    allowed_items: set[str],
) -> list[DatapackRecipe]:
    ranked = rank_recipes(candidates, result_item)
    return [recipe for recipe in ranked if all(ingredient in allowed_items for ingredient in recipe.ingredients)]


def build_survival_target_set(
    items: tuple[str, ...],
    recipe_index: DatapackRecipeIndex,
    material_harvest: dict[str, dict[str, Any]],
    snapshot: MCDataSnapshot,
) -> set[str]:
    memo: dict[str, bool] = {}
    visiting: set[str] = set()

    def terminal_supported(item_name: str) -> bool:
        if item_name in TERMINAL_SOURCE_OVERRIDES:
            return True
        if item_name in STRUCTURE_CHEST_ONLY_ITEMS:
            return True
        if item_name in material_harvest:
            return True
        source_blocks = snapshot.drop_sources.get(item_name, ())
        if source_blocks:
            try:
                rule_from_block_tools(source_blocks[0], snapshot.block_tool_names)
            except BlueprintGenerationError:
                return False
            return True
        return item_name in snapshot.entity_sources

    def can_resolve(item_name: str) -> bool:
        if item_name in memo:
            return memo[item_name]
        if item_name in visiting:
            return False
        if (
            is_brewed_item(item_name)
            or is_creative_only_item(item_name)
            or is_explicitly_excluded_item(item_name)
        ):
            memo[item_name] = False
            return False

        visiting.add(item_name)
        try:
            recipes = rank_recipes(recipe_index.get_all(item_name), item_name)
            if recipes:
                for recipe in recipes:
                    if all(can_resolve(ingredient_name) for ingredient_name in recipe.ingredients):
                        memo[item_name] = True
                        return True
                memo[item_name] = False
                return False

            terminal_ok = terminal_supported(item_name)
            memo[item_name] = terminal_ok
            return terminal_ok
        finally:
            visiting.remove(item_name)

    targets: set[str] = set()
    for item_name in items:
        if item_name == "air":
            continue
        if can_resolve(item_name):
            targets.add(item_name)
    return targets


TIER_DIAMOND = {"obsidian", "ancient_debris", "crying_obsidian", "respawn_anchor"}
TIER_IRON = {
    "diamond_ore",
    "deepslate_diamond_ore",
    "emerald_ore",
    "deepslate_emerald_ore",
    "gold_ore",
    "deepslate_gold_ore",
    "redstone_ore",
    "deepslate_redstone_ore",
}
TIER_STONE = {
    "iron_ore",
    "deepslate_iron_ore",
    "copper_ore",
    "deepslate_copper_ore",
    "lapis_ore",
    "deepslate_lapis_ore",
    "lightning_rod",
    "iron_block",
    "copper_block",
}
TIER_WOODEN = {
    "stone",
    "cobblestone",
    "coal_ore",
    "deepslate_coal_ore",
    "netherrack",
    "sandstone",
    "red_sandstone",
    "deepslate",
    "tuff",
    "andesite",
    "diorite",
    "granite",
    "basalt",
    "blackstone",
}


def resolve_terminal_task(
    item_name: str,
    material_harvest: dict[str, dict[str, Any]],
    snapshot: MCDataSnapshot,
) -> dict[str, Any]:
    if item_name in TERMINAL_SOURCE_OVERRIDES:
        override = TERMINAL_SOURCE_OVERRIDES[item_name]
        return {
            "operation": override.operation,
            "item": item_name,
            "prerequisites": [],
            "source_blocks": list(override.source_blocks),
            "source_entities": list(override.source_entities),
            "source_structures": list(override.source_structures),
            "harvest": dict(override.harvest),
        }

    if item_name in STRUCTURE_CHEST_ONLY_ITEMS:
        return {
            "operation": "find",
            "item": item_name,
            "prerequisites": [],
            "source_blocks": [],
            "source_entities": [],
            "source_structures": list(STRUCTURE_CHEST_ONLY_ITEMS[item_name]),
        }

    if item_name in material_harvest:
        rule = material_harvest[item_name]
        if "hand_insta_harvest_possible" not in rule:
            raise BlueprintGenerationError(
                f"material_harvest rule for {item_name} must include hand_insta_harvest_possible."
            )
        source_blocks = list(snapshot.drop_sources.get(item_name, ()))
        source_entities = list(snapshot.entity_sources.get(item_name, ()))
        operation = "gather" if str(rule.get("tool_class", "none")) == "none" else "mine"
    elif item_name in snapshot.drop_sources:
        source_blocks = snapshot.drop_sources[item_name]
        rule = rule_from_block_tools(source_blocks[0], snapshot.block_tool_names)
        rule["hand_insta_harvest_possible"] = hand_insta_harvest_possible_for_source_blocks(list(source_blocks), snapshot)
        source_blocks = list(source_blocks)
        source_entities = list(snapshot.entity_sources.get(item_name, ()))
        operation = "mine" if str(rule.get("tool_class", "none")) != "none" else "gather"
    elif item_name in snapshot.entity_sources:
        source_blocks = []
        source_entities = list(snapshot.entity_sources[item_name])
        rule = {"tool_class": "sword", "min_tier": "wooden", "hand_insta_harvest_possible": False}
        operation = "sword"
    else:
        raise UnresolvableTerminalItem(
            f"{item_name} has no craft/smelt recipe and no block, mob, or structure source mapping."
        )

    tool_class = str(rule.get("tool_class", "none"))
    min_tier = str(rule.get("min_tier", "wooden"))
    hand_insta_harvest_possible = bool(rule.get("hand_insta_harvest_possible", False))
    if source_blocks:
        pb = source_blocks[0]
        if pb in TIER_DIAMOND:
            min_tier = "diamond"
            hand_insta_harvest_possible = False
        elif pb in TIER_IRON:
            min_tier = "iron"
            hand_insta_harvest_possible = False
        elif pb in TIER_STONE:
            min_tier = "stone"
            hand_insta_harvest_possible = False
        elif pb in TIER_WOODEN:
            min_tier = "wooden"
            hand_insta_harvest_possible = False
        else:
            # Not in a tier-gating set — use actual Minecraft block tool data.
            min_tier = "wooden"
            if pb in ["snow", "snow_block"]:
                tool_class = "shovel"
                hand_insta_harvest_possible = False
            else:
                hand_insta_harvest_possible = snapshot.block_hand_insta_harvest_possible.get(pb, False)
    if item_name in BOOTSTRAP_WOODEN_TOOL_ITEMS and tool_class != "none":
        min_tier = "wooden"

    # Only demote to hand-only gather when no tool class was ever specified.
    if hand_insta_harvest_possible and tool_class == "none":
        operation = "gather"

    task = {
        "operation": operation,
        "item": item_name,
        "prerequisites": [],
        "source_blocks": source_blocks,
        "source_entities": source_entities,
        "source_structures": [],
        "harvest": {
            "tool_class": tool_class,
            "min_tier": min_tier,
            "hand_insta_harvest_possible": hand_insta_harvest_possible,
        },
    }
    byproduct = rule.get("junk/by-product")
    if operation == "mine" and isinstance(byproduct, dict):
        if "item" not in byproduct or "quantity" not in byproduct:
            raise BlueprintGenerationError(
                f"Invalid junk/by-product for {item_name}. Expected keys: item, quantity."
            )
        task["junk/by-product"] = {
            "item": str(byproduct["item"]),
            "quantity": int(byproduct["quantity"]),
        }
    return task


def required_tool_for_terminal(task: dict[str, Any]) -> str | None:
    """Return the tool name when the item CANNOT be obtained without it.

    Pickaxe and sword are required: cobblestone drops nothing without a pickaxe,
    mob drops need a sword.  Shovel, axe, and hoe are *optional* speed-ups —
    the player can punch logs/clay/dirt by hand.  Phase 4A Step 1B decides
    whether the ROI justifies injecting the optional tool.
    """
    operation = str(task.get("operation"))
    harvest = task.get("harvest")
    if operation == "sword":
        return "wooden_sword"
    if not isinstance(harvest, dict):
        return None
    tool_class = str(harvest.get("tool_class", "none"))
    if tool_class not in {"pickaxe", "sword"}:
        return None
    min_tier = str(harvest.get("min_tier", "wooden"))
    if min_tier not in VALID_TIERS:
        raise BlueprintGenerationError(f"Invalid min_tier {min_tier!r} for terminal task {task.get('item')}.")
    return f"{min_tier}_{tool_class}"


def build_blueprint_for_item(
    target_item: str,
    recipe_index: DatapackRecipeIndex,
    material_harvest: dict[str, dict[str, Any]],
    snapshot: MCDataSnapshot,
    survival_targets: set[str],
    selected_recipe_cache: dict[str, DatapackRecipe | None],
) -> list[dict[str, Any]]:
    visiting: set[str] = set()
    visiting_stack: list[str] = []
    emitted: set[str] = set()
    tasks: list[dict[str, Any]] = []
    PREFER_MINING_ITEMS = {
        "diamond",
        "emerald",
        "coal",
        "lapis_lazuli",
        "redstone",
        "quartz",
        "flint",
        "amethyst_shard",
        "glowstone_dust",
    }

    def dfs(item_name: str) -> None:
        if item_name in emitted:
            return
        if item_name in visiting:
            cycle_start = visiting_stack.index(item_name) if item_name in visiting_stack else 0
            cycle_path = visiting_stack[cycle_start:] + [item_name]
            raise CircularDependencyError(
                f"Cycle detected while generating blueprint for {target_item}: {' -> '.join(cycle_path)}"
            )

        visiting.add(item_name)
        visiting_stack.append(item_name)
        try:
            cached_recipe = selected_recipe_cache.get(item_name, None) if item_name in selected_recipe_cache else None
            if item_name in selected_recipe_cache:
                recipe_candidates = [cached_recipe] if cached_recipe is not None else []
            else:
                recipe_candidates = rank_recipes_for_targets(
                    recipe_index.get_all(item_name),
                    item_name,
                    survival_targets,
                )
            if item_name in PREFER_MINING_ITEMS:
                recipe_candidates = []
            if recipe_candidates:
                cycle_errors: list[str] = []
                for recipe in recipe_candidates:
                    ingredient_names = sorted(recipe.ingredients.keys())
                    prerequisites = list(ingredient_names)
                    station = recipe.station
                    include_station = station not in {"player", "none"}
                    if include_station and station not in prerequisites:
                        prerequisites.append(station)
                    task_checkpoint = len(tasks)
                    emitted_checkpoint = set(emitted)
                    try:
                        if include_station:
                            dfs(station)
                        for ingredient_name in ingredient_names:
                            dfs(ingredient_name)
                    except CircularDependencyError as exc:
                        del tasks[task_checkpoint:]
                        emitted.clear()
                        emitted.update(emitted_checkpoint)
                        cycle_errors.append(str(exc))
                        continue

                    tasks.append(
                        {
                            "operation": recipe.action,
                            "item": item_name,
                            "station": recipe.station,
                            "recipe_type": recipe.raw_type,
                            "ingredients": dict(sorted(recipe.ingredients.items())),
                            "prerequisites": prerequisites,
                        }
                    )
                    selected_recipe_cache[item_name] = recipe
                    emitted.add(item_name)
                    return

                raise CircularDependencyError(
                    f"All target-valid recipes for {item_name} are cyclic. Last cycle: {cycle_errors[-1]}"
                )

            terminal_task = resolve_terminal_task(item_name, material_harvest, snapshot)
            tool_item = required_tool_for_terminal(terminal_task)
            if tool_item:
                if tool_item == item_name:
                    raise BlueprintGenerationError(f"Terminal task for {item_name} cannot require itself as a tool.")
                dfs(tool_item)
                terminal_task["prerequisites"] = [tool_item]
            tasks.append(terminal_task)
            selected_recipe_cache[item_name] = None
            emitted.add(item_name)
        finally:
            visiting.remove(item_name)
            visiting_stack.pop()

    dfs(target_item)
    return tasks


def generate_blueprints() -> dict[str, Any]:
    version = load_version()
    material_harvest = load_material_harvest()
    recipe_index = load_datapack(version)
    snapshot = load_mc_snapshot(version)

    survival_targets = build_survival_target_set(snapshot.items, recipe_index, material_harvest, snapshot)
    blueprints: dict[str, list[dict[str, Any]]] = {}
    selected_recipe_cache: dict[str, DatapackRecipe | None] = {}
    skipped_brewed: list[str] = []
    for item_name in snapshot.items:
        if item_name == "air":
            continue
        if is_brewed_item(item_name) or is_explicitly_excluded_item(item_name):
            skipped_brewed.append(item_name)
            continue
        if item_name not in survival_targets:
            continue
        blueprints[item_name] = build_blueprint_for_item(
            item_name,
            recipe_index,
            material_harvest,
            snapshot,
            survival_targets,
            selected_recipe_cache,
        )

    return {
        "minecraft_version": version,
        "blueprint_count": len(blueprints),
        "survival_target_count": len(survival_targets),
        "skipped_brewed_count": len(skipped_brewed),
        "skipped_brewed_items": sorted(skipped_brewed),
        "blueprints": dict(sorted(blueprints.items())),
    }


def main() -> None:
    data = generate_blueprints()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = OUTPUT_PATH.with_suffix(".json.tmp")
    with tmp_path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, sort_keys=True)
        handle.write("\n")
    tmp_path.replace(OUTPUT_PATH)
    print(f"Wrote {OUTPUT_PATH} with {data['blueprint_count']} blueprints.")


if __name__ == "__main__":
    main()
