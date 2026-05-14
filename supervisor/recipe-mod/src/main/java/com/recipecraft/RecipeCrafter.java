package com.recipecraft;

import java.util.List;

import it.unimi.dsi.fastutil.ints.Int2ObjectMaps;
import net.fabricmc.fabric.api.client.event.lifecycle.v1.ClientTickEvents;
import net.minecraft.client.MinecraftClient;
import net.minecraft.client.network.ClientPlayerEntity;
import net.minecraft.client.gui.screen.recipebook.RecipeResultCollection;
import net.minecraft.client.recipebook.ClientRecipeBook;
import net.minecraft.item.Item;
import net.minecraft.item.ItemStack;
import net.minecraft.item.Items;
import net.minecraft.network.packet.c2s.play.ClickSlotC2SPacket;
import net.minecraft.network.packet.c2s.play.CraftRequestC2SPacket;
import net.minecraft.recipe.NetworkRecipeId;
import net.minecraft.recipe.RecipeDisplayEntry;
import net.minecraft.recipe.display.RecipeDisplay;
import net.minecraft.recipe.display.ShapedCraftingRecipeDisplay;
import net.minecraft.recipe.display.ShapelessCraftingRecipeDisplay;
import net.minecraft.recipe.display.SlotDisplay;
import net.minecraft.registry.Registries;
import net.minecraft.screen.slot.SlotActionType;
import net.minecraft.screen.sync.ItemStackHash;
import net.minecraft.text.Text;
import net.minecraft.util.Identifier;

public class RecipeCrafter {
    private static int batchesRemaining;
    private static boolean needsPickup;
    private static NetworkRecipeId currentRecipeId;
    private static int totalRequested;

    public static void register() {
        ClientTickEvents.END_CLIENT_TICK.register(RecipeCrafter::onClientTick);
    }

    private static void onClientTick(MinecraftClient client) {
        if (batchesRemaining == 0 && !needsPickup) {
            return;
        }

        if (client.player == null || client.getNetworkHandler() == null) {
            reset();
            return;
        }

        // Step 1: pickup previous craft's output
        if (needsPickup) {
            int syncId = client.player.currentScreenHandler.syncId;
            ClickSlotC2SPacket clickPacket = new ClickSlotC2SPacket(
                syncId,
                client.player.currentScreenHandler.getRevision(),
                (short) 0,
                (byte) 0,
                SlotActionType.QUICK_MOVE,
                Int2ObjectMaps.emptyMap(),
                ItemStackHash.EMPTY
            );
            client.getNetworkHandler().sendPacket(clickPacket);
            needsPickup = false;
        }

        // Step 2: send next craft batch
        if (batchesRemaining > 0) {
            sendCraftPacket(client);
            batchesRemaining--;
            needsPickup = true;
        } else {
            // Done — send final confirmation
            sendOk(client, "Crafted " + totalRequested + "x items.");
            reset();
        }
    }

    private static void reset() {
        batchesRemaining = 0;
        needsPickup = false;
        currentRecipeId = null;
        totalRequested = 0;
    }

    public static void craft(MinecraftClient client, String itemName, int count) {
        if (!validateClientState(client)) {
            return;
        }

        ClientPlayerEntity player = client.player;

        Item targetItem = lookupItem(itemName);
        if (targetItem == null) {
            return;
        }

        RecipeDisplayEntry found = findRecipeDisplay(player, targetItem, itemName);
        if (found == null) {
            return;
        }

        int outputPerCraft = getOutputCount(found, targetItem);
        if (outputPerCraft <= 0) {
            return;
        }

        if (count % outputPerCraft != 0) {
            sendError(client, "Count must be a multiple of " + outputPerCraft
                + " (recipe produces " + outputPerCraft + " per craft).");
            return;
        }

        int batches = count / outputPerCraft;
        currentRecipeId = found.id();
        totalRequested = count;
        batchesRemaining = batches;
        needsPickup = false;
    }

    private static boolean validateClientState(MinecraftClient client) {
        if (client.player == null || client.world == null) {
            ChatInterceptor.sendFeedback("Must be in a game world.");
            return false;
        }
        if (client.getNetworkHandler() == null) {
            ChatInterceptor.sendFeedback("Not connected to a server.");
            return false;
        }
        return true;
    }

    private static Item lookupItem(String itemName) {
        Identifier itemId = Identifier.ofVanilla(itemName);
        Item item = Registries.ITEM.get(itemId);
        if (item == null || item == Items.AIR) {
            ChatInterceptor.sendFeedback("Unknown item: '" + itemName + "'.");
            return null;
        }
        return item;
    }

    private static RecipeDisplayEntry findRecipeDisplay(ClientPlayerEntity player, Item targetItem, String itemName) {
        ClientRecipeBook recipeBook = player.getRecipeBook();
        List<RecipeResultCollection> collections = recipeBook.getOrderedResults();

        for (RecipeResultCollection collection : collections) {
            for (RecipeDisplayEntry entry : collection.getAllRecipes()) {
                RecipeDisplay display = entry.display();
                SlotDisplay result = null;
                int width = 0;
                int height = 0;

                if (display instanceof ShapedCraftingRecipeDisplay shaped) {
                    result = shaped.result();
                    width = shaped.width();
                    height = shaped.height();
                } else if (display instanceof ShapelessCraftingRecipeDisplay shapeless) {
                    result = shapeless.result();
                }

                if (result == null) {
                    continue;
                }

                if (width > 2 || height > 2) {
                    continue;
                }

                List<ItemStack> stacks = result.getStacks(null);
                for (ItemStack stack : stacks) {
                    if (stack.getItem() == targetItem) {
                        return entry;
                    }
                }
            }
        }

        ChatInterceptor.sendFeedback("No 2x2 crafting recipe for '" + itemName + "'.");
        return null;
    }

    private static int getOutputCount(RecipeDisplayEntry entry, Item targetItem) {
        RecipeDisplay display = entry.display();
        SlotDisplay result = null;
        if (display instanceof ShapedCraftingRecipeDisplay shaped) {
            result = shaped.result();
        } else if (display instanceof ShapelessCraftingRecipeDisplay shapeless) {
            result = shapeless.result();
        }
        if (result == null) {
            return 0;
        }
        for (ItemStack stack : result.getStacks(null)) {
            if (stack.getItem() == targetItem) {
                return stack.getCount();
            }
        }
        return 0;
    }

    private static void sendCraftPacket(MinecraftClient client) {
        int syncId = client.player.currentScreenHandler.syncId;
        CraftRequestC2SPacket packet = new CraftRequestC2SPacket(syncId, currentRecipeId, false);
        client.getNetworkHandler().sendPacket(packet);
    }

    private static void sendError(MinecraftClient client, String msg) {
        if (client.player != null) {
            client.player.sendMessage(Text.literal("[RecipeCraft] " + msg), false);
        }
    }

    private static void sendOk(MinecraftClient client, String msg) {
        if (client.player != null) {
            client.player.sendMessage(Text.literal("[RecipeCraft] " + msg), false);
        }
    }
}
