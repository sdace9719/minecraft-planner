Core Technical Implementation

To achieve on-demand crafting via a chat command, your mod needs three main components:
1. Command Registration

You must register a client-side command using the ClientCommandRegistrationCallback. This allows your Python script to send a message like /ccraft stick 16 which your mod will intercept.  

    Target API: net.fabricmc.fabric.api.client.command.v2.ClientCommandManager.  

2. Recipe Lookup

Your mod needs to find the recipe for the requested item in the game's RecipeManager.  

    Target API: MinecraftClient.getInstance().world.getRecipeManager().  

    Method: Use .get(Identifier) to retrieve the specific Recipe object for the item.  

3. Packet-Based Crafting (The "On-Demand" Logic)

Instead of manual slot-clicking, use the Recipe Book Packet. This is the most reliable way to craft natively on 1.21.11 without a GUI.

    Packet: CraftRecipeRequestC2SPacket.  

    Logic: When your command is triggered, send this packet to the server with the Recipe ID. The server will automatically move ingredients from your inventory to the crafting grid and produce the item.  

    Advantage: This bypasses all X/Y coordinate logic and "ghost item" desync issues.

Development Roadmap

    Environment Setup: Use the Fabric Example Mod template and set the minecraft_version in gradle.properties to 1.21.11.  

    Dependencies: Ensure you have the Fabric API version compatible with 1.21.11 (Fabric Loader 0.18.1 is the current stable for this version).  

    Code Structure:  

        Initializer: Register the command.  

        Command Logic: Extract item name/count, find the recipe, and dispatch the CraftRecipeRequestC2SPacket.