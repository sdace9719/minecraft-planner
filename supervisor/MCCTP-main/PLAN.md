# MCCTP - Minecraft Control Transfer Protocol

## Context
Control Minecraft via gesture recognition: Webcam -> Python CV (MediaPipe/OpenCV) -> WebSocket -> Fabric mod. The mod needs **full duplex** communication: it sends game state (held item category, player state, combat context) to Python, and receives high-level action commands back. A custom **hotbar wheel overlay** (circular layout) is controlled by hand gestures via the Python app.

## Tech Stack
- **Minecraft 1.21.11** / Fabric Loader 0.18.2 / Fabric API 0.141.3+1.21.11 / Java 21
- **Netty WebSocket** server (bundled in MC, no extra deps) on configurable port (default 8765)
- **Gson** (bundled in MC) for JSON serialization
- **Python client** using `websockets` + `asyncio`

## Project Structure

```
mcctp/
├── build.gradle, gradle.properties, settings.gradle, gradlew
├── src/
│   ├── main/java/com/mcctp/
│   │   ├── MCCTPMod.java                    # ModInitializer (minimal)
│   │   ├── MCCTPClient.java                 # ClientModInitializer (wires everything)
│   │   ├── config/MCCTPConfig.java          # Port, tick interval, JSON config file
│   │   ├── network/
│   │   │   ├── WebSocketServer.java         # Netty ServerBootstrap lifecycle
│   │   │   ├── WebSocketServerInitializer.java  # Channel pipeline setup
│   │   │   ├── WebSocketFrameHandler.java   # Inbound frame handler
│   │   │   └── ConnectionManager.java       # Track connected Python client
│   │   ├── state/
│   │   │   ├── GameStateCollector.java      # Reads all game state on client tick
│   │   │   ├── GameStatePayload.java        # Top-level JSON POJO
│   │   │   ├── HeldItemInfo.java            # Item name, category, durability
│   │   │   ├── PlayerStateInfo.java         # Health, pos, movement flags
│   │   │   └── CombatContextInfo.java       # Using item, blocking, crosshair target
│   │   ├── action/
│   │   │   ├── ActionDispatcher.java        # Routes incoming commands to handlers
│   │   │   ├── ActionMessage.java           # Deserialized {action, params} POJO
│   │   │   └── handlers/                    # One handler per action type
│   │   │       ├── MoveHandler.java         # WASD via KeyBinding.setPressed
│   │   │       ├── LookHandler.java         # Absolute/relative yaw+pitch
│   │   │       ├── JumpHandler.java         # Single press pulse
│   │   │       ├── SneakHandler.java        # Start/stop
│   │   │       ├── SprintHandler.java       # Start/stop
│   │   │       ├── AttackHandler.java       # Left click (doAttack)
│   │   │       ├── UseItemHandler.java      # Right click hold/release
│   │   │       ├── ThrowItemHandler.java    # Single use press
│   │   │       ├── DropItemHandler.java     # Drop item/stack
│   │   │       ├── SelectSlotHandler.java   # Set hotbar slot 0-8
│   │   │       ├── SwapHandsHandler.java    # Offhand swap
│   │   │       └── OpenInventoryHandler.java
│   │   ├── item/
│   │   │   ├── ItemCategory.java            # Enum: SWORD, BOW, BLOCK, THROWABLE, etc.
│   │   │   └── ItemCategorizer.java         # instanceof checks -> category
│   │   └── hud/
│   │       ├── HotbarWheelRenderer.java     # Circular hotbar HUD overlay
│   │       └── HotbarWheelState.java        # Toggle + selected slot state
│   └── main/resources/
│       ├── fabric.mod.json
│       └── mcctp.mixins.json
├── src/client/
│   ├── java/com/mcctp/mixin/
│   │   └── KeyBindingAccessor.java          # Accessor for setPressed
│   └── resources/mcctp.client.mixins.json
└── python/
    ├── pyproject.toml
    └── src/mcctp/
        ├── __init__.py
        ├── client.py          # Async MCCTPClient (websockets)
        ├── sync_client.py     # Synchronous wrapper for simple scripts
        ├── state.py           # GameState dataclass
        ├── actions.py         # Action name constants
        └── exceptions.py
```

## Protocol (JSON over WebSocket)

### Mod -> Python: Game state (every N ticks, default=1)
```json
{
  "type": "game_state",
  "timestamp": 1700000000000,
  "selectedSlot": 0,
  "heldItem": {"name": "minecraft:bow", "category": "BOW", "stackCount": 1, "maxDurability": 384, "currentDurability": 380},
  "offhandItem": {"name": "minecraft:shield", "category": "SHIELD", ...},
  "playerState": {"health": 20, "maxHealth": 20, "hunger": 20, "saturation": 5, "x": 100.5, "y": 64, "z": -200.3, "yaw": 45, "pitch": -10, "onGround": true, "sprinting": false, "sneaking": false, "swimming": false, "flying": false, "inWater": false, "onFire": false},
  "combatContext": {"isUsingItem": false, "isBlocking": false, "activeHand": "MAIN_HAND", "crosshairTarget": "ENTITY", "crosshairEntityType": "minecraft:zombie", "crosshairBlockPos": null}
}
```

### Python -> Mod: Action commands
```json
{"action": "move",       "params": {"direction": "forward", "state": "start"}}
{"action": "look",       "params": {"yaw": 45.0, "pitch": -10.0, "relative": true}}
{"action": "jump",       "params": {}}
{"action": "attack",     "params": {}}
{"action": "use_item",   "params": {"state": "start"}}
{"action": "select_slot","params": {"slot": 3}}
{"action": "sneak",      "params": {"state": "start"}}
{"action": "sprint",     "params": {"state": "start"}}
{"action": "throw_item", "params": {}}
{"action": "drop_item",  "params": {"full_stack": false}}
{"action": "swap_hands", "params": {}}
{"action": "open_inventory", "params": {}}
```

### Item Categories
`SWORD, BOW, CROSSBOW, BLOCK, AXE, PICKAXE, SHOVEL, HOE, FOOD, SHIELD, TRIDENT, FISHING_ROD, THROWABLE, EMPTY, OTHER`

## Hotbar Wheel Overlay
- 9 slots in a circle (40deg apart, slot 0 at top)
- Renders item icons + selected slot highlight (gold border)
- Toggled on/off with `V` key
- Registered via `HudElementRegistry.attachElementAfter(VanillaHudElements.HOTBAR, ...)`
- Python's `select_slot` command updates both inventory AND wheel highlight

## Key Architecture Decisions
- **Netty WS server** runs on its own `NioEventLoopGroup` (separate from MC networking)
- **Thread safety**: Incoming actions dispatched to game thread via `MinecraftClient.getInstance().execute()`
- **State collection** runs on `ClientTickEvents.END_CLIENT_TICK`
- **Server lifecycle**: starts on `ClientPlayConnectionEvents.JOIN`, stops on `DISCONNECT`
- **No extra dependencies**: Netty + Gson are bundled with Minecraft

## Implementation Order

### Phase 1: Scaffolding
1. Generate Fabric mod project structure, build.gradle, fabric.mod.json
2. Verify `./gradlew build` compiles

### Phase 2: Game State
3. ItemCategory enum + ItemCategorizer
4. State POJOs (HeldItemInfo, PlayerStateInfo, CombatContextInfo, GameStatePayload)
5. GameStateCollector

### Phase 3: Networking
6. ConnectionManager, WebSocketServerInitializer, WebSocketFrameHandler, WebSocketServer
7. Wire into MCCTPClient: tick event sends state, join/disconnect start/stop server
8. Test: connect with wscat, verify JSON state arrives

### Phase 4: Actions
9. ActionMessage, ActionDispatcher, ActionHandler interface
10. KeyBindingAccessor mixin
11. All 12 action handlers (SelectSlot -> Move -> Sneak/Sprint -> Jump -> Look -> Attack -> UseItem -> Drop -> SwapHands -> OpenInventory -> ThrowItem)
12. Test: send JSON commands from wscat, verify in-game effect

### Phase 5: HUD
13. HotbarWheelState + HotbarWheelRenderer
14. Toggle keybinding (`V` key)
15. Wire SelectSlotHandler to update wheel state

### Phase 6: Python Client
16. state.py, actions.py, exceptions.py
17. client.py (async MCCTPClient)
18. sync_client.py (SyncMCCTPClient)
19. pyproject.toml

### Phase 7: Config + Polish
20. MCCTPConfig (JSON config file for port, tick interval)
21. Error responses, logging, edge cases

## Verification
1. `./gradlew build` produces a working mod JAR
2. Load into MC with Fabric, join a singleplayer world
3. Connect with `wscat -c ws://localhost:8765/mcctp` -> verify game state JSON streams
4. Send action JSON via wscat -> verify in-game player responds
5. Press `V` -> verify hotbar wheel overlay appears
6. `pip install -e python/` -> run example script -> verify bidirectional communication
