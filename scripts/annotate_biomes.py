#!/usr/bin/env python3
"""Annotate gather_only_items.json with source biomes from mojang-data worldgen files.

Walks the configured_feature → placed_feature → biome chain to determine
which biomes each block (and thus each item) generates in.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
INPUT_PATH = ROOT / "constants" / "gather_only_items.json"
OUTPUT_PATH = ROOT / "constants" / "gather_only_items.json"
FULL_DATA_PATH = ROOT / "constants" / "gather_only_items_full.json"
CONFIG_PATH = ROOT / "config.json"
MOJANG_DATA_ROOT = ROOT / "mojang-data"


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


def load_version() -> str:
    with CONFIG_PATH.open(encoding="utf-8") as fh:
        cfg = json.load(fh)
    version = cfg.get("minecraft_version")
    if not isinstance(version, str) or not version.strip():
        raise RuntimeError("config.json missing minecraft_version")
    return version


# ---------------------------------------------------------------------------
# Recursive block name extraction from configured_feature JSON
# ---------------------------------------------------------------------------


def extract_block_names(data: Any) -> set[str]:
    """Recursively walk a JSON structure and extract all block names.

    Block names appear as ``{"Name": "minecraft:block_name"}`` inside state
    objects. This handles all configured_feature types uniformly.
    """
    blocks: set[str] = set()

    if isinstance(data, dict):
        name_val = data.get("Name")
        if isinstance(name_val, str) and name_val.startswith("minecraft:"):
            blocks.add(name_val.split(":", 1)[1])
        for value in data.values():
            blocks.update(extract_block_names(value))
    elif isinstance(data, list):
        for item in data:
            blocks.update(extract_block_names(item))

    return blocks


# ---------------------------------------------------------------------------
# Worldgen data loading
# ---------------------------------------------------------------------------


def extract_feature_refs(data: Any) -> set[str]:
    """Recursively extract configured_feature names referenced by a feature.

    Feature references appear as ``"feature": "minecraft:cf_name"`` or as
    string values ``"minecraft:cf_name"`` inside random_selector / simple_random_selector configs.
    """
    refs: set[str] = set()

    if isinstance(data, dict):
        feature_val = data.get("feature")
        if isinstance(feature_val, str) and feature_val.startswith("minecraft:"):
            refs.add(feature_val.split(":", 1)[1])
        elif isinstance(feature_val, dict):
            inner = feature_val.get("feature")
            if isinstance(inner, str) and inner.startswith("minecraft:"):
                refs.add(inner.split(":", 1)[1])
        for value in data.values():
            refs.update(extract_feature_refs(value))
    elif isinstance(data, list):
        for item in data:
            refs.update(extract_feature_refs(item))

    return refs


# Feature types whose name IS the block they place (config is empty or metadata-only)
_SIMPLE_FEATURE_BLOCKS: dict[str, str] = {
    "minecraft:kelp": "kelp",
    "minecraft:seagrass": "seagrass",
    "minecraft:sea_pickle": "sea_pickle",
    "minecraft:bamboo": "bamboo",
    "minecraft:cactus": "cactus",
    "minecraft:sugar_cane": "sugar_cane",
    "minecraft:chorus_plant": "chorus_plant",
    "minecraft:twisting_vines": "twisting_vines",
    "minecraft:weeping_vines": "weeping_vines",
    "minecraft:vines": "vine",
    "minecraft:glowstone_blob": "glowstone",
    "minecraft:blue_ice": "blue_ice",
    "minecraft:ice_spike": "packed_ice",
    "minecraft:basalt_pillar": "basalt",
    "minecraft:basalt_columns": "basalt",
    "minecraft:end_island": "end_stone",
    "minecraft:freeze_top_layer": "snow",
    "minecraft:huge_brown_mushroom": "brown_mushroom_block",
    "minecraft:huge_red_mushroom": "red_mushroom_block",
    "minecraft:huge_fungus": "nether_wart_block",
    "minecraft:nether_forest_vegetation": "nether_sprouts",
}


def _extract_implicit_blocks(cf_name: str, cf_data: dict) -> set[str]:
    """Extract block names from features that don't use explicit Name fields."""
    blocks: set[str] = set()
    rtype = cf_data.get("type", "")
    cfg = cf_data.get("config", {})

    # 1. Simple types: block name = feature type
    implicit = _SIMPLE_FEATURE_BLOCKS.get(rtype)
    if implicit:
        blocks.add(implicit)

    # 2. multiface_growth: config.block is the block
    if isinstance(cfg, dict):
        block_field = cfg.get("block")
        if isinstance(block_field, str) and block_field.startswith("minecraft:"):
            blocks.add(block_field.split(":", 1)[1])

    # 3. dripstone_cluster → dripstone_block
    if rtype == "minecraft:dripstone_cluster":
        blocks.add("dripstone_block")

    # 4. large_dripstone → dripstone_block + pointed_dripstone
    if rtype == "minecraft:large_dripstone":
        blocks.add("dripstone_block")
        blocks.add("pointed_dripstone")

    # 5. sculk_patch → sculk blocks
    if rtype == "minecraft:sculk_patch":
        blocks.add("sculk")
        blocks.add("sculk_catalyst")
        blocks.add("sculk_shrieker")
        blocks.add("sculk_sensor")

    # 6. huge_fungus: the configured name tells us which stem
    if rtype == "minecraft:huge_fungus":
        if "crimson" in cf_name:
            blocks.add("crimson_stem")
            blocks.add("nether_wart_block")  # crimson wart block
        elif "warped" in cf_name:
            blocks.add("warped_stem")
            blocks.add("warped_wart_block")

    # 7. huge_mushroom features also place mushroom_stem
    if rtype in ("minecraft:huge_brown_mushroom", "minecraft:huge_red_mushroom"):
        blocks.add("mushroom_stem")

    # 8. root_system places rooted_dirt + hanging_roots
    if rtype == "minecraft:root_system":
        blocks.add("rooted_dirt")
        blocks.add("hanging_roots")

    # 9. Feature name itself is the block (for features like "kelp", "vines", etc.)
    # Only if no other blocks were found and the name matches a simple pattern
    if not blocks:
        # Many features are named after the block they place
        pass  # Feature references are already handled by transitive closure

    return blocks


def compute_transitive_blocks(
    configured: dict[str, dict],
    placed: dict[str, dict],
) -> dict[str, set[str]]:
    """Compute transitive block names reachable from each placed_feature.

    Follows the bipartite chain:
      placed_feature → configured_feature (via ``feature`` field)
      configured_feature → placed_features (via random_selector refs)

    Returns dict mapping placed_feature name → set of reachable block names.
    """
    # 1. Direct: placed_feature → configured_feature
    placed_to_conf: dict[str, str] = {}
    for pf_name, pf_data in placed.items():
        feature_ref = pf_data.get("feature")
        if isinstance(feature_ref, str) and feature_ref.startswith("minecraft:"):
            cf_name = feature_ref.split(":", 1)[1]
            if cf_name in configured:
                placed_to_conf[pf_name] = cf_name

    # 2. configured_feature → placed_features (from random_selector etc.)
    conf_to_placed: dict[str, set[str]] = {}
    for cf_name, cf_data in configured.items():
        refs = extract_feature_refs(cf_data)
        valid = {r for r in refs if r in placed}
        if valid:
            conf_to_placed[cf_name] = valid

    # 3. Direct blocks per configured_feature (with fallback for implicit types)
    conf_blocks: dict[str, set[str]] = {}
    for cf_name, cf_data in configured.items():
        blocks = extract_block_names(cf_data)

        # Fallback: types where the block is implicit (config is empty/minimal)
        if not blocks:
            blocks = _extract_implicit_blocks(cf_name, cf_data)

        if blocks:
            conf_blocks[cf_name] = blocks

    # 4. Build conf → conf refs (direct configured_feature references)
    conf_to_conf: dict[str, set[str]] = {}
    for cf_name, cf_data in configured.items():
        raw_refs = extract_feature_refs(cf_data)
        valid = {r for r in raw_refs if r in configured}
        if valid:
            conf_to_conf[cf_name] = valid

    # 5. Transitive closure: placed_feature → all reachable configured_features
    # Walk: placed → conf, conf → placed, conf → conf
    placed_to_confs: dict[str, set[str]] = {}
    for pf_name, cf_name in placed_to_conf.items():
        placed_to_confs[pf_name] = {cf_name}

    changed = True
    iteration = 0
    while changed and iteration < 20:
        changed = False
        iteration += 1
        for pf_name in list(placed_to_confs.keys()):
            current_confs = placed_to_confs[pf_name]
            new_confs = set(current_confs)
            for cf_name in current_confs:
                # conf → conf (direct refs to other configured_features)
                for next_cf in conf_to_conf.get(cf_name, set()):
                    if next_cf not in new_confs:
                        new_confs.add(next_cf)
                        changed = True
                # conf → placed → conf
                for next_pf in conf_to_placed.get(cf_name, set()):
                    next_cf = placed_to_conf.get(next_pf)
                    if next_cf and next_cf not in new_confs:
                        new_confs.add(next_cf)
                        changed = True
            if new_confs != current_confs:
                placed_to_confs[pf_name] = new_confs

    # 6. Union all blocks from all reachable configured_features
    result: dict[str, set[str]] = {}
    for pf_name, conf_names in placed_to_confs.items():
        blocks: set[str] = set()
        for cf_name in conf_names:
            blocks.update(conf_blocks.get(cf_name, set()))
        if blocks:
            result[pf_name] = blocks

    direct_count = sum(1 for pf in placed_to_conf if placed_to_conf[pf] in conf_blocks)
    transit_count = sum(1 for v in result.values() if v)
    print(f"  {direct_count} placed_features with direct blocks, {transit_count} with transitive blocks")
    print(f"  Transitive closure converged in {iteration} iterations")

    return result


def load_worldgen_data(version: str) -> tuple[dict[str, set[str]], dict[str, list[str]]]:
    """Load worldgen data and return (block_to_biomes, block_to_features)."""
    data_dir = MOJANG_DATA_ROOT / version / "data" / "minecraft" / "worldgen"
    conf_dir = data_dir / "configured_feature"
    placed_dir = data_dir / "placed_feature"
    biome_dir = data_dir / "biome"

    if not (conf_dir.is_dir() and placed_dir.is_dir() and biome_dir.is_dir()):
        raise RuntimeError(f"Worldgen data missing at {data_dir}")

    # 1. Load all files
    configured: dict[str, dict] = {}
    for p in conf_dir.glob("*.json"):
        configured[p.stem] = json.loads(p.read_text(encoding="utf-8"))

    placed: dict[str, dict] = {}
    for p in placed_dir.glob("*.json"):
        placed[p.stem] = json.loads(p.read_text(encoding="utf-8"))

    biomes: dict[str, dict] = {}
    for p in biome_dir.glob("*.json"):
        biomes[p.stem] = json.loads(p.read_text(encoding="utf-8"))

    print(f"  Loaded {len(configured)} configured_features, {len(placed)} placed_features, {len(biomes)} biomes")

    # 2. Build placed_feature → biomes map
    feature_to_biomes: dict[str, set[str]] = {}
    for biome_name, biome_data in biomes.items():
        for step in biome_data.get("features", []) or []:
            if not isinstance(step, list):
                continue
            for feature_ref in step:
                if isinstance(feature_ref, str) and feature_ref.startswith("minecraft:"):
                    pf_name = feature_ref.split(":", 1)[1]
                    feature_to_biomes.setdefault(pf_name, set()).add(biome_name)

    print(f"  {len(feature_to_biomes)} placed_features mapped to biomes")

    # 3. Build placed_feature → configured_feature map
    placed_to_conf: dict[str, str] = {}
    for pf_name, pf_data in placed.items():
        feature_ref = pf_data.get("feature")
        if isinstance(feature_ref, str) and feature_ref.startswith("minecraft:"):
            cf_name = feature_ref.split(":", 1)[1]
            if cf_name in configured:
                placed_to_conf[pf_name] = cf_name

    # 4. Compute transitive block names (follow random_selector bipartite chains)
    placed_to_blocks = compute_transitive_blocks(configured, placed)

    # 5. Build block → biomes map — walk placed_feature → biomes
    block_to_biomes: dict[str, set[str]] = {}
    block_to_features: dict[str, list[str]] = {}

    for pf_name, blocks in placed_to_blocks.items():
        biome_set = feature_to_biomes.get(pf_name, set())
        for block_name in blocks:
            block_to_biomes.setdefault(block_name, set()).update(biome_set)
            block_to_features.setdefault(block_name, []).append(pf_name)

    print(f"  {len(block_to_biomes)} unique blocks mapped to biomes")
    return block_to_biomes, block_to_features


# ---------------------------------------------------------------------------
# Item → biome mapping
# ---------------------------------------------------------------------------


def resolve_item_biomes(
    item_name: str,
    source_blocks: list[str],
    block_to_biomes: dict[str, set[str]],
) -> list[str]:
    """Resolve biomes for an item by looking up its source blocks.

    If source_blocks is empty (probabilistic drop), returns empty list.
    """
    biomes: set[str] = set()
    for block_name in source_blocks:
        block_biomes = block_to_biomes.get(block_name)
        if block_biomes:
            biomes.update(block_biomes)
    return sorted(biomes)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    version = load_version()
    print(f"Minecraft version: {version}")

    # 1. Read existing gather_only_items.json
    print(f"Reading {INPUT_PATH} ...")
    with INPUT_PATH.open(encoding="utf-8") as fh:
        existing = json.load(fh)

    existing_items: dict[str, dict] = existing.get("items", {})
    print(f"  {len(existing_items)} items in existing list")

    # 22. Load worldgen data
    print(f"Loading worldgen data for {version} ...")
    block_to_biomes, _block_to_features = load_worldgen_data(version)

    # 3. Map each item to its biomes
    print("Mapping items to biomes ...")
    annotated: dict[str, dict] = {}
    items_with_no_biomes: list[str] = []
    items_with_source_biomes: int = 0

    for item_name in sorted(existing_items.keys()):
        item_data = existing_items[item_name]
        source_blocks: list[str] = item_data.get("source_blocks", [])

        source_biomes = resolve_item_biomes(item_name, source_blocks, block_to_biomes)

        annotated[item_name] = {
            "name": item_name,
            "source_biomes": source_biomes,
        }

        if not source_biomes:
            items_with_no_biomes.append(item_name)
        else:
            items_with_source_biomes += 1

    # 4. Write output
    output = {
        "minecraft_version": version,
        "edition": "java",
        "data_source": "misode/mcmeta worldgen data (configured_feature, placed_feature, biome)",
        "total_items": len(annotated),
        "items": annotated,
    }

    tmp_path = OUTPUT_PATH.with_suffix(".json.tmp")
    with tmp_path.open("w", encoding="utf-8") as fh:
        json.dump(output, fh, indent=2)
        fh.write("\n")
    tmp_path.replace(OUTPUT_PATH)

    # 5. Print summary
    print()
    print(f"Items with source biomes: {items_with_source_biomes}")
    print(f"Items with no source biomes: {len(items_with_no_biomes)}")
    if items_with_no_biomes:
        print("  Items without biomes (probabilistic drops / unmapped):")
        for name in items_with_no_biomes:
            src = existing_items[name].get("source_blocks", [])
            print(f"    {name}: source_blocks={src}")
    print(f"\nWrote {len(annotated)} items to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
