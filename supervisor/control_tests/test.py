import sys
import time
from mcctp import SyncMCCTPClient


def _short_name(name: str) -> str:
    if isinstance(name, str) and name.startswith("minecraft:"):
        return name[10:]
    return str(name)


def display_held_durability(state: dict) -> None:
    """Display durability of the currently held item."""
    if not state:
        return

    # held_item can be at top level or nested in playerState / player_state
    held_item = None
    for key in ("heldItem", "held_item", "helditem"):
        hi = state.get(key)
        if hi:
            held_item = hi
            break

    if not held_item:
        p_state = state.get("playerState") or state.get("player_state") or {}
        for key in ("heldItem", "held_item", "helditem"):
            hi = p_state.get(key)
            if hi:
                held_item = hi
                break

    if not held_item:
        return

    item_name = _short_name(held_item.get("name") or held_item.get("id") or "?")

    # DEBUG: dump keys once to confirm field names
    if not hasattr(display_held_durability, "_dumped"):
        display_held_durability._dumped = True  # type: ignore[attr-defined]
        print(f"\n[DEBUG] held_item keys: {list(held_item.keys())}\n")

    current = held_item.get("currentDurability")
    maximum = held_item.get("maxDurability")

    if current is None or maximum is None or maximum == 0:
        print(f"\r  held: {item_name}  |  no durability (not a tool/armor)  ", end="")
        return

    pct = (current / maximum) * 100

    bar_width = 20
    filled = round((current / maximum) * bar_width)
    bar = "[" + "#" * filled + "-" * (bar_width - filled) + "]"

    sys.stdout.write(f"\r  {item_name}  {bar}  {current}/{maximum} ({pct:.0f}%)  ")
    sys.stdout.flush()


with SyncMCCTPClient("localhost", 8770) as client:
    latest_state: list[dict | None] = [None]

    def handle_state(s: dict) -> None:
        latest_state[0] = s

    client.on_state(handle_state)
    time.sleep(2)

    print("Held-item durability monitor. Press Ctrl+C to stop.\n")
    try:
        while True:
            if latest_state[0]:
                display_held_durability(latest_state[0])
            else:
                sys.stdout.write("\r[waiting for state...]")
                sys.stdout.flush()
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopped.")
