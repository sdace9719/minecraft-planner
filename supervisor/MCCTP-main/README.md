# MCCTP - Minecraft Control Transfer Protocol

A Fabric mod that exposes a WebSocket server on your Minecraft client. It streams game state out every tick and accepts action commands in — letting any program, in any language, control the player.

## Features

- **WebSocket API** — JSON over WebSocket, language-agnostic
- **13 action types** — movement, combat, inventory, camera, and more
- **Game state every tick** — health, position, held item, combat context
- **Item categorization** — automatic classification (SWORD, BOW, BLOCK, FOOD, etc.)
- **Hotbar wheel overlay** — circular HUD showing all 9 slots, controlled via commands or V key
- **Thread-safe** — WebSocket runs on its own Netty thread group, actions dispatch to the game thread

## Requirements

- Minecraft 1.21.11
- Fabric Loader >= 0.18.0
- Fabric API
- Java 21+

## Install

```bash
./gradlew build
```

Copy `build/libs/mcctp-1.0.0.jar` to your `.minecraft/mods/` folder (alongside Fabric Loader + Fabric API).

## How It Works

When you join a world, the mod starts a WebSocket server on port `8765`. Any client can connect to `ws://<host>:8765/mcctp` and:

1. **Receive** game state JSON every tick (50ms by default)
2. **Send** action commands as JSON to control the player

The server runs on its own Netty `NioEventLoopGroup`, separate from Minecraft's networking. Incoming actions are dispatched to the game thread via `MinecraftClient.execute()`, so they're safe and behave identically to real input. The server stops when you leave the world.

## Protocol

### Connecting

```
ws://<host>:8765/mcctp
```

Standard WebSocket connection. No authentication. Multiple clients can connect simultaneously.

### Game State (Server → Client)

Broadcast to all connected clients every tick. All fields are always present.

```json
{
  "type": "game_state",
  "timestamp": 1700000000000,
  "selectedSlot": 0,
  "heldItem": {
    "name": "minecraft:diamond_sword",
    "category": "SWORD",
    "stackCount": 1,
    "maxDurability": 1561,
    "currentDurability": 1500
  },
  "offhandItem": {
    "name": "minecraft:shield",
    "category": "SHIELD",
    "stackCount": 1,
    "maxDurability": 336,
    "currentDurability": 336
  },
  "playerState": {
    "health": 20.0,
    "maxHealth": 20.0,
    "hunger": 20,
    "saturation": 5.0,
    "x": 100.5,
    "y": 64.0,
    "z": -200.3,
    "yaw": 45.0,
    "pitch": -10.0,
    "onGround": true,
    "sprinting": false,
    "sneaking": false,
    "swimming": false,
    "flying": false,
    "inWater": false,
    "onFire": false
  },
  "combatContext": {
    "isUsingItem": false,
    "isBlocking": false,
    "activeHand": "MAIN_HAND",
    "crosshairTarget": "ENTITY",
    "crosshairEntityType": "minecraft:zombie",
    "crosshairBlockPos": null
  }
}
```

#### Game State Fields

| Field | Type | Description |
|-------|------|-------------|
| `type` | string | Always `"game_state"` |
| `timestamp` | long | Unix milliseconds |
| `selectedSlot` | int | Active hotbar slot (0-8) |

**`heldItem` / `offhandItem`:**

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Registry ID, e.g. `"minecraft:diamond_sword"` |
| `category` | string | See [Item Categories](#item-categories) |
| `stackCount` | int | Current stack size |
| `maxDurability` | int | Max durability (0 if not damageable) |
| `currentDurability` | int | Remaining durability |

**`playerState`:**

| Field | Type | Description |
|-------|------|-------------|
| `health` | float | Current health (0-20) |
| `maxHealth` | float | Max health |
| `hunger` | int | Food level (0-20) |
| `saturation` | float | Saturation level |
| `x`, `y`, `z` | float | World position |
| `yaw`, `pitch` | float | Camera rotation (degrees) |
| `onGround` | bool | Standing on solid ground |
| `sprinting` | bool | Currently sprinting |
| `sneaking` | bool | Currently sneaking |
| `swimming` | bool | Currently swimming |
| `flying` | bool | Creative/elytra flight |
| `inWater` | bool | Submerged in water |
| `onFire` | bool | On fire |

**`combatContext`:**

| Field | Type | Description |
|-------|------|-------------|
| `isUsingItem` | bool | Holding right click (eating, drawing bow, etc.) |
| `isBlocking` | bool | Blocking with shield |
| `activeHand` | string | `"MAIN_HAND"` or `"OFF_HAND"` |
| `crosshairTarget` | string | `"ENTITY"`, `"BLOCK"`, or `"MISS"` |
| `crosshairEntityType` | string? | Entity registry ID, or null |
| `crosshairBlockPos` | int[3]? | `[x, y, z]` block position, or null |

### Actions (Client → Server)

Send a JSON message with `action` and `params`:

```json
{"action": "<action_name>", "params": {<params>}}
```

#### Action Reference

| Action | Params | Description |
|--------|--------|-------------|
| `move` | `direction`: `"forward"` `"backward"` `"left"` `"right"`, `state`: `"start"` `"stop"` | WASD movement. Holds the key until you send `"stop"`. |
| `look` | `yaw`: float, `pitch`: float, `relative`: bool | Camera control. `relative: true` adds to current angles. `relative: false` sets absolute. |
| `jump` | _(none)_ | Single jump. |
| `attack` | _(none)_ | Left click — swing weapon, hit entity, start breaking block. |
| `use_item` | `state`: `"start"` `"stop"` | Right click hold. Use `"start"` to begin (draw bow, eat, raise shield) and `"stop"` to release. |
| `throw_item` | _(none)_ | Single right click pulse — for snowballs, ender pearls, firing a loaded crossbow. |
| `select_slot` | `slot`: int (0-8) | Switch active hotbar slot. |
| `sneak` | `state`: `"start"` `"stop"` | Crouch. Holds until stopped. |
| `sprint` | `state`: `"start"` `"stop"` | Sprint. Holds until stopped. |
| `drop_item` | `full_stack`: bool | Drop held item. `true` drops the entire stack (Ctrl+Q). |
| `swap_hands` | _(none)_ | Swap main hand and offhand (F key). |
| `open_inventory` | _(none)_ | Toggle inventory screen (E key). |
| `toggle_wheel` | _(none)_ | Toggle the hotbar wheel HUD overlay. |

#### Action Examples

```json
// Walk forward
{"action": "move", "params": {"direction": "forward", "state": "start"}}

// Stop walking
{"action": "move", "params": {"direction": "forward", "state": "stop"}}

// Turn 90 degrees right
{"action": "look", "params": {"yaw": 90.0, "pitch": 0.0, "relative": true}}

// Face north, looking straight ahead
{"action": "look", "params": {"yaw": 180.0, "pitch": 0.0, "relative": false}}

// Draw and fire a bow
{"action": "use_item", "params": {"state": "start"}}
// ... wait ~1 second ...
{"action": "use_item", "params": {"state": "stop"}}

// Throw a snowball
{"action": "throw_item", "params": {}}

// Switch to slot 3 and attack
{"action": "select_slot", "params": {"slot": 3}}
{"action": "attack", "params": {}}
```

### Item Categories

Every held item is classified into one of these categories:

| Category | Examples |
|----------|----------|
| `SWORD` | Diamond sword, netherite sword |
| `BOW` | Bow |
| `CROSSBOW` | Crossbow |
| `AXE` | Iron axe, wooden axe |
| `PICKAXE` | Diamond pickaxe |
| `SHOVEL` | Stone shovel |
| `HOE` | Netherite hoe |
| `TRIDENT` | Trident |
| `SHIELD` | Shield |
| `FOOD` | Cooked beef, golden apple |
| `BLOCK` | Cobblestone, dirt, planks |
| `THROWABLE` | Snowball, egg, ender pearl |
| `FISHING_ROD` | Fishing rod |
| `EMPTY` | Empty hand |
| `OTHER` | Anything not matched above |

## Configuration

Config file: `.minecraft/config/mcctp.json` (created on first launch)

```json
{
  "port": 8765,
  "tickInterval": 1
}
```

| Field | Default | Description |
|-------|---------|-------------|
| `port` | 8765 | WebSocket server port |
| `tickInterval` | 1 | Broadcast game state every N ticks (20 ticks = 1 second) |

## Architecture

```
Any Client ←── WebSocket (JSON) ──→ Fabric Mod
                                       │
                                       ├── WebSocketServer (Netty, own thread group)
                                       │     ├── WebSocketServerInitializer (HTTP → WS upgrade)
                                       │     ├── WebSocketFrameHandler (parse inbound JSON)
                                       │     └── ConnectionManager (track channels, broadcast)
                                       │
                                       ├── GameStateCollector (END_CLIENT_TICK → JSON)
                                       │     ├── GameStatePayload
                                       │     ├── HeldItemInfo + ItemCategorizer
                                       │     ├── PlayerStateInfo
                                       │     └── CombatContextInfo
                                       │
                                       ├── ActionDispatcher (JSON → ActionHandler)
                                       │     ├── MoveHandler, LookHandler, JumpHandler
                                       │     ├── AttackHandler, UseItemHandler, ThrowItemHandler
                                       │     ├── SelectSlotHandler, SneakHandler, SprintHandler
                                       │     ├── DropItemHandler, SwapHandsHandler
                                       │     ├── OpenInventoryHandler, ToggleWheelHandler
                                       │     └── KeyReleaseScheduler (timed key pulses)
                                       │
                                       └── HotbarWheelRenderer (HUD overlay)
```

**Key implementation details:**

- The WebSocket server uses Netty's `NioEventLoopGroup`, completely separate from Minecraft's network thread
- All action handlers run on the game thread via `MinecraftClient.execute()` — same as real player input
- Pulse actions (jump, attack, throw, swap, inventory) use `KeyReleaseScheduler` which holds the key for 3 ticks and increments `timesPressed`, matching how Minecraft processes single key presses
- Held actions (move, sneak, sprint, use_item) set `KeyBinding.pressed` directly and stay held until a `"stop"` command
- State collection hooks into `END_CLIENT_TICK` and serializes with Gson
- The mod uses a Mixin accessor (`KeyBindingAccessor`) to access `KeyBinding.pressed` and `KeyBinding.timesPressed`

## Building from Source

```bash
# Build
./gradlew build

# Output jar
build/libs/mcctp-1.0.0.jar
```

Build targets Java 21. Tested with Gradle 9.2.0 and Fabric Loom 1.15.3.

## Python Client

A reference Python client is included in `python/`. Install with:

```bash
cd python
pip install -e .
```

Provides async and sync WebSocket clients with typed dataclasses for game state:

```python
import time
from mcctp import SyncMCCTPClient, Actions

with SyncMCCTPClient("localhost", 8765) as client:
    client.on_state(lambda s: print(s.player_state.health))
    client.send(Actions.move("forward", "start"))
    time.sleep(2)
    client.send(Actions.move("forward", "stop"))
```

Also includes `remote_play.py` — a keyboard/mouse passthrough that lets someone play on your world from another computer.

## License

MIT
