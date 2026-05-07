import json
from dataclasses import dataclass
from pathlib import Path


SMELT_TYPES = {
    "minecraft:smelting": ("smelt", "furnace"),
    "minecraft:blasting": ("smelt", "blast_furnace"),
    "minecraft:smoking": ("smelt", "smoker"),
    "minecraft:campfire_cooking": ("smelt", "campfire"),
}

TAG_PREFERENCES = {
    "wool": ["minecraft:white_wool"],
    "stone_tool_materials": ["minecraft:cobblestone"],
}


CRAFT_TYPES = {
    "minecraft:crafting_shaped",
    "minecraft:crafting_shapeless",
}


@dataclass(frozen=True)
class DatapackRecipe:
    action: str
    station: str
    result: str
    result_count: int
    ingredients: dict[str, int]
    raw_type: str


class DatapackRecipeIndex:
    def __init__(self, recipe_dir: Path, *, item_tag_dir: Path | None = None):
        self.recipe_dir = recipe_dir
        self.item_tag_dir = item_tag_dir
        self._by_result: dict[str, list[DatapackRecipe]] = {}
        self._item_tags: dict[str, list[str]] = {}

    def load(self) -> None:
        self._by_result.clear()
        self._item_tags = _load_item_tags(self.item_tag_dir) if self.item_tag_dir else {}
        for path in sorted(self.recipe_dir.glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            recipe = self._parse_recipe(data)
            if recipe:
                self._by_result.setdefault(recipe.result, []).append(recipe)

    def get(self, result_item: str) -> DatapackRecipe | None:
        recipes = self._by_result.get(result_item, [])
        return recipes[0] if recipes else None

    def get_all(self, result_item: str) -> list[DatapackRecipe]:
        return list(self._by_result.get(result_item, []))

    def _parse_recipe(self, data: dict) -> DatapackRecipe | None:
        rtype = data.get("type")
        if not isinstance(rtype, str):
            return None

        if rtype in SMELT_TYPES:
            action, station = SMELT_TYPES[rtype]
            result_item, result_count = _parse_result(data.get("result"))
            ing_item = _parse_single_item(data.get("ingredient"), item_tags=self._item_tags)
            if not result_item or not ing_item:
                return None
            return DatapackRecipe(
                action=action,
                station=station,
                result=result_item,
                result_count=result_count,
                ingredients={ing_item: 1},
                raw_type=rtype,
            )

        if rtype in CRAFT_TYPES:
            result_item, result_count = _parse_result(data.get("result"))
            if not result_item:
                return None
            ingredients = _parse_crafting_ingredients(data, item_tags=self._item_tags)
            if not ingredients:
                return None
            if result_item in ingredients:
                return None
            # Ignore common "decompression" recipes (e.g., raw_iron_block -> 9 raw_iron),
            # which create planner dead-ends for gatherable base materials.
            if result_count == 9 and len(ingredients) == 1 and next(iter(ingredients.values())) == 1:
                return None
            station = "crafting_table" if _looks_like_3x3(data) else "player"
            return DatapackRecipe(
                action="craft",
                station=station,
                result=result_item,
                result_count=result_count,
                ingredients=ingredients,
                raw_type=rtype,
            )

        return None


def _parse_result(result_field) -> tuple[str | None, int]:
    if isinstance(result_field, str):
        return result_field.split(":")[-1], 1
    if isinstance(result_field, dict):
        item = result_field.get("id") or result_field.get("item")
        if not isinstance(item, str):
            return None, 0
        count = result_field.get("count", 1)
        if not isinstance(count, int) or count <= 0:
            count = 1
        return item.split(":")[-1], count
    return None, 0


def _parse_single_item(field, *, item_tags: dict[str, list[str]] | None) -> str | None:
    # Ingredient can be {"item": "minecraft:cobblestone"} or {"items": [...]} etc.
    if isinstance(field, dict):
        if isinstance(field.get("item"), str):
            return field["item"].split(":")[-1]
        if isinstance(field.get("id"), str):
            return field["id"].split(":")[-1]
        if isinstance(field.get("tag"), str):
            tag = field["tag"].split(":")[-1]
            if item_tags and tag in item_tags and item_tags[tag]:
                preferred = TAG_PREFERENCES.get(tag, [])
                for pref in preferred:
                    if pref in item_tags[tag]:
                        return pref.split(":")[-1]
                for candidate in item_tags[tag]:
                    if isinstance(candidate, str) and not candidate.startswith("#"):
                        return candidate.split(":")[-1]
                return item_tags[tag][0].split(":")[-1]
        if isinstance(field.get("items"), list) and field["items"] and isinstance(field["items"][0], str):
            return field["items"][0].split(":")[-1]
    if isinstance(field, list) and field and isinstance(field[0], dict):
        return _parse_single_item(field[0], item_tags=item_tags)
    return None


def _parse_crafting_ingredients(data: dict, *, item_tags: dict[str, list[str]] | None) -> dict[str, int]:
    # shaped: keys + pattern
    if "pattern" in data and "key" in data:
        key = data.get("key", {})
        if not isinstance(key, dict):
            return {}
        counts: dict[str, int] = {}
        for row in data.get("pattern", []):
            if not isinstance(row, str):
                continue
            for ch in row:
                if ch == " ":
                    continue
                ing = key.get(ch)
                item = _parse_single_item(ing, item_tags=item_tags)
                if item:
                    counts[item] = counts.get(item, 0) + 1
        return counts

    # shapeless: ingredients list
    if isinstance(data.get("ingredients"), list):
        counts: dict[str, int] = {}
        for ing in data["ingredients"]:
            item = _parse_single_item(ing, item_tags=item_tags)
            if item:
                counts[item] = counts.get(item, 0) + 1
        return counts

    return {}


def _looks_like_3x3(data: dict) -> bool:
    if isinstance(data.get("pattern"), list):
        pattern = data["pattern"]
        if len(pattern) > 2:
            return True
        for row in pattern:
            if isinstance(row, str) and len(row) > 2:
                return True
    return False


def _load_item_tags(item_tag_dir: Path | None) -> dict[str, list[str]]:
    if not item_tag_dir or not item_tag_dir.exists():
        return {}
    tags: dict[str, list[str]] = {}
    for path in item_tag_dir.glob("*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        values = data.get("values", [])
        if isinstance(values, list):
            tags[path.stem] = [v for v in values if isinstance(v, str)]
    return tags

