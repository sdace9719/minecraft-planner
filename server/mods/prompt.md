# Role & Context
You are an expert Fabric 1.21.11 mod developer using Yarn mappings. We are abandoning vanilla inventory clicking (`InteractionManager`) for our headless.

We are shifting to a **Server-Side Authority Architecture**. We will implement a custom network bridge where the client simply requests the swap, and the server executes it directly in RAM, bypassing all `ScreenHandler` validation. Security (offline mode spoofing) is NOT a priority right now.

# Task
Implement a custom packet using the modern Fabric 1.21.11 `CustomPayload` API. The client will send the `sourceSlot` and `hotbarIndex`. The server will execute the swap natively and force a state sync.

# Step 1: The Payload Definition
Create a record named `SwapRequestPayload` that implements `CustomPayload`.
* **Fields:** `int sourceSlot`, `int hotbarIndex`.
* **ID:** Define the packet ID as `new CustomPayload.Id<>("mcctp", "swap_request")`.
* **Codec:** Define a `PacketCodec` using `PacketCodec.tuple()` and `PacketCodecs.INTEGER` to serialize/deserialize the two integers. Do not use legacy `PacketByteBuf` read/write methods.

# Step 2: The Server-Side Receiver
Create a class (e.g., `SwapServerReceiver`) to handle the packet on the server.
* Use `ServerPlayNetworking.registerGlobalReceiver()` to listen for `SwapRequestPayload`.
* **Execution Logic (Inside the receiver):**
    1.  Get the server player: `ServerPlayerEntity player = context.player();`
    2.  Access the raw inventory: `PlayerInventory inv = player.getInventory();`
    3.  Snapshot the items using `inv.getStack(payload.sourceSlot())` and `inv.getStack(payload.hotbarIndex())`.
    4.  Execute the swap directly using `inv.setStack(...)`. *(Note: In PlayerInventory, hotbar slots are natively 0-8, and main inventory slots are 9-35).*
    5.  **Force Client Sync:** Call `player.currentScreenHandler.sendContentUpdates();` so the server instantly pushes the new ground-truth revision and item state down to the bot.

# Step 3: The Client-Side Sender
Create a public method in the client mod: `public static void executeServerAuthoritySwap(int sourceSlot, int hotbarIndex)`.
* Construct the `SwapRequestPayload`.
* Send it directly to the server using `ClientPlayNetworking.send(payload)`.

# Strict Constraints
* **No Vanilla Clicks:** Do NOT write any `client.interactionManager.clickSlot` logic.
* **1.21.11 Syntax:** Adhere strictly to the `CustomPayload` and `PacketCodec` API.
* **Output:** Provide the complete Java code for the Payload Record, the Server init/receiver, and the Client sender method.

* Log every single event and request/response on both client and server
## Directory Structure

inside server/mods create a new mod named bot interaction and implement the server side of things here.
In the existing supervisor/mods folder, ensure the exisiting logic in the existing mods for swap inventory items is scrapped and implement this new mechanism instead in its place that performs seamless inventory swap.
