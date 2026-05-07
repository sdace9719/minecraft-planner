import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class WorldgenHint:
    y_min: int | None
    y_max: int | None
    count_per_chunk: int | None
    vein_size: int | None
    best_biomes: list[str]


def load_worldgen_hints(root_dir: Path) -> dict[str, WorldgenHint]:
    placed_dir = root_dir / "worldgen" / "placed_feature"
    conf_dir = root_dir / "worldgen" / "configured_feature"
    biome_dir = root_dir / "worldgen" / "biome"
    if not (placed_dir.exists() and conf_dir.exists() and biome_dir.exists()):
        return {}

    placed = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in placed_dir.glob("*.json")}
    configured = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in conf_dir.glob("*.json")}
    biome = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in biome_dir.glob("*.json")}

    feature_to_biomes: dict[str, set[str]] = {}
    for bname, bdata in biome.items():
        for step in bdata.get("features", []) or []:
            if not isinstance(step, list):
                continue
            for f in step:
                if isinstance(f, str) and f.startswith("minecraft:"):
                    feature_to_biomes.setdefault(f.split(":", 1)[1], set()).add(bname)

    hints: dict[str, WorldgenHint] = {}
    for pf_name, pf in placed.items():
        feature = pf.get("feature")
        if isinstance(feature, str) and feature.startswith("minecraft:"):
            cf_name = feature.split(":", 1)[1]
        else:
            continue

        y_min, y_max = _extract_height_range(pf)
        count = _extract_count(pf)
        vein_size = _extract_vein_size(configured.get(cf_name, {}))
        biomes = sorted(feature_to_biomes.get(pf_name, set()))
        hints[pf_name] = WorldgenHint(
            y_min=y_min,
            y_max=y_max,
            count_per_chunk=count,
            vein_size=vein_size,
            best_biomes=biomes,
        )

    return hints


def _extract_count(placed_feature: dict) -> int | None:
    for entry in placed_feature.get("placement", []) or []:
        if isinstance(entry, dict) and "count" in entry:
            c = entry["count"]
            if isinstance(c, int):
                return c
            if isinstance(c, dict) and isinstance(c.get("value"), int):
                return c["value"]
    return None


def _extract_height_range(placed_feature: dict) -> tuple[int | None, int | None]:
    for entry in placed_feature.get("placement", []) or []:
        if not isinstance(entry, dict):
            continue
        hr = entry.get("height_range")
        if not isinstance(hr, dict):
            continue
        mn = hr.get("min_inclusive")
        mx = hr.get("max_inclusive")
        return _extract_y(mn), _extract_y(mx)
    return None, None


def _extract_y(node) -> int | None:
    if isinstance(node, int):
        return node
    if isinstance(node, dict) and isinstance(node.get("absolute"), int):
        return node["absolute"]
    if isinstance(node, dict) and isinstance(node.get("value"), int):
        return node["value"]
    return None


def _extract_vein_size(configured_feature: dict) -> int | None:
    cfg = configured_feature.get("config")
    if isinstance(cfg, dict) and isinstance(cfg.get("size"), int):
        return cfg["size"]
    return None

