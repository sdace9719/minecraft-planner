"""Chest lifecycle management for the Phase 6 cache simulator.

Provides Chest (dataclass) and ChestManager which handles:
- Finding available placed chests for stashing (capacity-aware)
- Creating and placing chests on demand
- Retrieving items from chests by item name
- Generating craft/place task dicts for injection into the task queue
"""

from __future__ import annotations

from dataclasses import dataclass, field

CHEST_CAPACITY = 27


@dataclass
class Chest:
    chest_id: str
    contents: list[dict] = field(default_factory=list)
    placed: bool = False

    @property
    def slots_used(self) -> int:
        return len(self.contents)

    @property
    def is_full(self) -> bool:
        return self.slots_used >= CHEST_CAPACITY

    @property
    def remaining(self) -> int:
        return CHEST_CAPACITY - self.slots_used


class ChestManager:
    def __init__(self):
        self._chests: dict[str, Chest] = {}
        self._counter = 0

    # -- properties -------------------------------------------------------

    @property
    def total_chests(self) -> int:
        return self._counter

    @property
    def placed_count(self) -> int:
        return sum(1 for c in self._chests.values() if c.placed)

    # -- chest operations -------------------------------------------------

    def find_available(self) -> str | None:
        """Return a placed, non-full chest ID (most-full first), or None."""
        candidates = [c for c in self._chests.values()
                      if c.placed and not c.is_full]
        if not candidates:
            return None
        candidates.sort(key=lambda c: -c.slots_used)
        return candidates[0].chest_id

    def create(self, placed: bool = False) -> str:
        self._counter += 1
        chest_id = f"chest_{self._counter}"
        self._chests[chest_id] = Chest(chest_id=chest_id, placed=placed)
        return chest_id

    def place(self, chest_id: str) -> None:
        self._chests[chest_id].placed = True

    def stash_into(self, chest_id: str, items: list[dict]) -> None:
        self._chests[chest_id].contents.extend(items)

    def retrieve(self, item_name: str) -> list[tuple[str, list[dict]]]:
        """Search all chests for *item_name*.  Returns a list of
        (chest_id, items_retrieved) pairs.  Found items are removed from
        their chests.  Empty chests stay registered (placed, reusable)."""
        results: list[tuple[str, list[dict]]] = []
        for chest_id, chest in list(self._chests.items()):
            found: list[dict] = []
            for slot in list(chest.contents):
                if slot["item"] == item_name:
                    found.append(slot)
                    chest.contents.remove(slot)
            if found:
                results.append((chest_id, found))
        return results

    def retrieve_from_chest(self, chest_id: str) -> list[tuple[str, list[dict]]]:
        """Retrieve ALL items from a specific chest by ID."""
        chest = self._chests.get(chest_id)
        if chest is None or not chest.contents:
            return []
        items = list(chest.contents)
        chest.contents.clear()
        return [(chest_id, items)]

    # -- task-dict factories -----------------------------------------------

    _on_demand_counter: int = 0

    @classmethod
    def _next_on_demand_id(cls) -> str:
        cls._on_demand_counter += 1
        return f"on_demand_{cls._on_demand_counter}"

    def craft_chest_task(self, deps: list[str], chest_id: str,
                         qty: int = 1) -> dict:
        return {
            "id": f"CRAFT:{chest_id}",
            "name": "chest",
            "quantity": qty,
            "dependencies": deps,
            "operation_type": "craft",
        }

    def place_chest_task(self, deps: list[str], chest_id: str,
                         qty: int = 1) -> dict:
        return {
            "id": f"PLACE_CHEST:{chest_id}",
            "name": "chest",
            "quantity": qty,
            "dependencies": deps,
            "operation_type": "place",
            "chest_id": chest_id,
        }

    # -- lifecycle --------------------------------------------------------

    def reset(self) -> None:
        self._chests.clear()
        self._counter = 0
        self._on_demand_counter = 0
