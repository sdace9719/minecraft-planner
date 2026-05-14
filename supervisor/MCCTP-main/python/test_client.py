"""Test client - connects to MCCTP and sends a sequence of actions."""

import sys
import time
from mcctp import SyncMCCTPClient, Actions

DELAY = 1.5

def on_state(state):
    line = (f"[State] HP: {state.player_state.health} | "
            f"Pos: ({state.player_state.x}, {state.player_state.y}, {state.player_state.z}) | "
            f"Held: {state.held_item.name} ({state.held_item.category}) | "
            f"Sneak: {state.player_state.sneaking} | Sprint: {state.player_state.sprinting}")
    sys.stdout.write(f"\r\033[K{line}")
    sys.stdout.flush()

def log(msg):
    sys.stdout.write(f"\r\033[K{msg}\n")
    sys.stdout.flush()

def run(client, label, action, delay=DELAY):
    log(f"> {label}")
    client.send(action)
    time.sleep(delay)

def main():
    with SyncMCCTPClient("localhost", 8765) as client:
        client.on_state(on_state)
        log("Connected to MCCTP!")
        for i in range(5, 0, -1):
            log(f"Starting in {i}... (switch to Minecraft!)")
            time.sleep(1)

        # --- Hotbar Wheel ---
        log("\n=== HOTBAR WHEEL ===")
        run(client, "Toggle wheel ON", Actions.toggle_wheel())
        time.sleep(2)
        run(client, "Cycle through slots on wheel", Actions.select_slot(0))
        run(client, "Slot 1", Actions.select_slot(1))
        run(client, "Slot 2", Actions.select_slot(2))
        run(client, "Slot 3", Actions.select_slot(3))
        run(client, "Slot 4", Actions.select_slot(4))
        run(client, "Slot 5", Actions.select_slot(5))
        run(client, "Slot 6", Actions.select_slot(6))
        run(client, "Slot 7", Actions.select_slot(7))
        run(client, "Slot 8", Actions.select_slot(8))
        time.sleep(1)
        run(client, "Toggle wheel OFF", Actions.toggle_wheel())

        # --- Slot 0: Diamond Sword ---
        log("\n=== SWORD (slot 0) ===")
        run(client, "Select sword", Actions.select_slot(0))
        run(client, "Look straight ahead", Actions.look(yaw=0, pitch=0, relative=False))
        run(client, "Swing sword", Actions.attack())
        run(client, "Swing again", Actions.attack())
        run(client, "Swing once more", Actions.attack())

        # --- Slot 1: Bow ---
        log("\n=== BOW (slot 1) ===")
        run(client, "Select bow", Actions.select_slot(1))
        run(client, "Draw bow (hold use)", Actions.use_item("start"))
        time.sleep(1.5)
        run(client, "Release arrow", Actions.use_item("stop"))
        time.sleep(1)

        # --- Slot 2: Cobblestone ---
        log("\n=== BLOCK (slot 2) ===")
        run(client, "Select cobblestone", Actions.select_slot(2))
        run(client, "Look down at ground", Actions.look(yaw=0, pitch=70, relative=False))
        time.sleep(0.5)
        run(client, "Place block", Actions.use_item("start"))
        run(client, "Stop placing", Actions.use_item("stop"))
        run(client, "Look ahead again", Actions.look(yaw=0, pitch=0, relative=False))

        # --- Slot 3: Cooked Beef ---
        log("\n=== FOOD (slot 3) ===")
        run(client, "Select cooked beef", Actions.select_slot(3))
        run(client, "Start eating (hold use)", Actions.use_item("start"))
        time.sleep(3)
        run(client, "Stop eating", Actions.use_item("stop"))

        # --- Slot 4: Diamond Pickaxe ---
        log("\n=== PICKAXE (slot 4) ===")
        run(client, "Select pickaxe", Actions.select_slot(4))
        run(client, "Look down at block", Actions.look(yaw=0, pitch=70, relative=False))
        time.sleep(0.5)
        run(client, "Mine block (attack)", Actions.attack())
        run(client, "Mine again", Actions.attack())
        run(client, "Mine once more", Actions.attack())
        run(client, "Look ahead", Actions.look(yaw=0, pitch=0, relative=False))

        # --- Slot 5: Snowball ---
        log("\n=== THROWABLE (slot 5) ===")
        run(client, "Select snowball", Actions.select_slot(5))
        run(client, "Look slightly up", Actions.look(yaw=0, pitch=-15, relative=False))
        time.sleep(0.5)
        run(client, "Throw snowball", Actions.throw_item())
        run(client, "Throw another", Actions.throw_item())
        run(client, "Throw one more", Actions.throw_item())

        # --- Slot 6: Shield ---
        log("\n=== SHIELD (slot 6) ===")
        run(client, "Select shield", Actions.select_slot(6))
        run(client, "Swap shield to offhand", Actions.swap_hands())
        run(client, "Select sword for main hand", Actions.select_slot(0))
        time.sleep(0.5)
        run(client, "Raise shield (hold use)", Actions.use_item("start"))
        time.sleep(2)
        run(client, "Lower shield", Actions.use_item("stop"))

        # --- Slot 7: Ender Pearl ---
        log("\n=== ENDER PEARL (slot 7) ===")
        run(client, "Select ender pearl", Actions.select_slot(7))
        run(client, "Look up for distance", Actions.look(yaw=0, pitch=-30, relative=False))
        time.sleep(0.5)
        run(client, "Throw ender pearl", Actions.throw_item())
        time.sleep(2.5)

        # --- Slot 8: Crossbow ---
        log("\n=== CROSSBOW (slot 8) ===")
        run(client, "Select crossbow", Actions.select_slot(8))
        run(client, "Look ahead", Actions.look(yaw=0, pitch=0, relative=False))
        run(client, "Load crossbow (hold use)", Actions.use_item("start"))
        time.sleep(2.5)
        run(client, "Finish loading", Actions.use_item("stop"))
        time.sleep(0.5)
        run(client, "Fire crossbow", Actions.throw_item())
        time.sleep(1)

        # --- Movement ---
        log("\n=== MOVEMENT ===")
        run(client, "Look ahead", Actions.look(yaw=0, pitch=0, relative=False))
        run(client, "Walk forward", Actions.move("forward", "start"))
        time.sleep(1)
        run(client, "Jump!", Actions.jump())
        time.sleep(0.5)
        run(client, "Jump again!", Actions.jump())
        time.sleep(0.5)
        run(client, "Start sprinting", Actions.sprint("start"))
        time.sleep(1.5)
        run(client, "Jump while sprinting", Actions.jump())
        time.sleep(1)
        run(client, "Turn right 90 deg", Actions.look(yaw=90, pitch=0, relative=True))
        time.sleep(1.5)
        run(client, "Stop sprinting", Actions.sprint("stop"))
        run(client, "Stop moving", Actions.move("forward", "stop"))
        run(client, "Sneak", Actions.sneak("start"))
        time.sleep(2)
        run(client, "Stop sneaking", Actions.sneak("stop"))

        # --- Misc ---
        log("\n=== MISC ===")
        run(client, "Open inventory", Actions.open_inventory())
        time.sleep(2)
        run(client, "Close inventory", Actions.open_inventory())
        time.sleep(1)
        run(client, "Drop one item", Actions.drop_item(full_stack=False))

        log("\n--- Test sequence complete ---")
        time.sleep(2)
        print()

if __name__ == "__main__":
    main()
