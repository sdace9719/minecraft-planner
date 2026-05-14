import time
from mcctp import SyncMCCTPClient

class MCSTPAutonomousBot:
    def __init__(self, client):
        self.client = client
        self.state = None
        # Standard 1.21.1 Inventory Map (Normalized 0.0 - 1.0)
        # Note: These coordinates assume a standard centered GUI.
        self.SLOT_MAP = {
            "CRAFT_1": {"x": 0.588, "y": 0.354}, # Grid Top-Left
            "CRAFT_3": {"x": 0.588, "y": 0.444}, # Grid Bottom-Left
            "RESULT":  {"x": 0.760, "y": 0.399}, # Crafting Result
        }
        # Populate Main Inventory slots (9-35) and Hotbar (0-8)
        self._generate_inventory_map()

    def _generate_inventory_map(self):
        # Main Inventory (3x9 grid)
        start_x, start_y = 0.422, 0.590
        step_x, step_y = 0.044, 0.079
        for row in range(3):
            for col in range(9):
                slot_id = 9 + (row * 9) + col
                self.SLOT_MAP[slot_id] = {
                    "x": start_x + (col * step_x),
                    "y": start_y + (row * step_y)
                }
        # Hotbar (1x9)
        hotbar_y = 0.882
        for col in range(9):
            self.SLOT_MAP[col] = {"x": start_x + (col * step_x), "y": hotbar_y}

    def execute_action(self, action, params=None):
        self.client.send({"action": action, "params": params or {}})
        time.sleep(0.15) # Essential delay for server-side processing

    def craft_sticks(self):
        if not self.state or "inventory" not in self.state:
            return
        
        # DYNAMIC LOOKUP: Find Planks
        plank_slots = [i["slot"] for i in self.state["inventory"] if i["name"] == "minecraft:oak_planks"]
        if len(plank_slots) < 2:
            print("Need more plank stacks.")
            return

        # Step 1: Move first plank stack to Grid 1
        self.click_slot(plank_slots[0])
        self.click_slot("CRAFT_1")

        # Step 2: Move second plank stack to Grid 3
        self.click_slot(plank_slots[1])
        self.click_slot("CRAFT_3")

        # Step 3: Collect Result (Shift-Click Result)
        # Shift-clicking usually requires a specific 'click' implementation or rapid clicks
        self.click_slot("RESULT")

    def click_slot(self, slot_id):
        coords = self.SLOT_MAP.get(slot_id)
        if coords:
            self.execute_action("cursor", coords)
            self.execute_action("click", {"button": "left"})

# Connection Loop
with SyncMCCTPClient("localhost", 8765) as client:
    bot = MCSTPAutonomousBot(client)
    
    def handle_state(s):
        bot.state = s

    client.on_state(handle_state)
    time.sleep(2) # Sync buffer
    
    if bot.state:
        print(f"Autonomous session started. GUI: {bot.state.get('screenState', {}).get('screenType')}")
        bot.craft_sticks()