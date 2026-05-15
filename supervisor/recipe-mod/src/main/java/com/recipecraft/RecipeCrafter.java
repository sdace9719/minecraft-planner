package com.recipecraft;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

import net.minecraft.registry.tag.TagKey;

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
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class RecipeCrafter {
    private static final Logger LOG = LoggerFactory.getLogger("RecipeCraft-Crafter");
    private static int batchesRemaining;
    private static boolean needsPickup;
    private static NetworkRecipeId currentRecipeId;
    private static int totalRequested;
    private static final CraftingTableCrafter tableCrafter = new CraftingTableCrafter();

    public static void register() {
        ClientTickEvents.END_CLIENT_TICK.register(RecipeCrafter::onClientTick);
    }

    private static void onClientTick(MinecraftClient client) {
        if (tableCrafter.isActive()) {
            tableCrafter.onTick(client);
            return;
        }

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
        LOG.info("craft: item='{}' count={}", itemName, count);
        if (!validateClientState(client)) {
            LOG.error("craft: invalid client state");
            return;
        }

        ClientPlayerEntity player = client.player;

        Item targetItem = lookupItem(itemName);
        if (targetItem == null) {
            LOG.error("craft: unknown item '{}'", itemName);
            return;
        }
        LOG.info("craft: targetItem={}", targetItem);

        RecipeDisplayEntry found = findRecipeDisplay(player, targetItem, itemName);
        if (found == null) {
            LOG.error("craft: no 2x2 recipe for '{}'", itemName);
            ChatInterceptor.sendFeedback("No crafting recipe for '" + itemName + "'.");
            return;
        }

        int outputPerCraft = getOutputCount(found, targetItem);
        if (outputPerCraft <= 0) {
            LOG.error("craft: outputPerCraft <= 0");
            return;
        }

        if (count % outputPerCraft != 0) {
            sendError(client, "Count must be a multiple of " + outputPerCraft
                + " (recipe produces " + outputPerCraft + " per craft).");
            return;
        }

        int batches = count / outputPerCraft;
        LOG.info("craft: batches={} perCraft={} needs3x3={}", batches, outputPerCraft, recipeNeeds3x3(found));

        // ── 3x3 path: delegate to CraftingTableCrafter ──
        if (recipeNeeds3x3(found)) {
            LOG.info("craft: 3x3 recipe — checking crafting table and ingredients");

            int tableSlot = findCraftingTableInHotbar(player);
            LOG.info("craft: craftingTable hotbar slot={}", tableSlot);
            if (tableSlot < 0) {
                if (hasCraftingTableAnywhere(player)) {
                    sendError(client, "Crafting table must be in the hotbar.");
                } else {
                    sendError(client, "No crafting table in inventory.");
                }
                return;
            }

            String ingredientError = checkIngredients(found, player, batches);
            if (ingredientError != null) {
                sendError(client, ingredientError);
                LOG.error("craft: ingredient check failed — {}", ingredientError);
                return;
            }

            LOG.info("craft: ingredients OK, starting tableCrafter");
            tableCrafter.start(client, found.id(), batches, outputPerCraft, count, tableSlot);
            return;
        }

        // ── 2x2 path ──
        currentRecipeId = found.id();
        totalRequested = count;
        batchesRemaining = batches;
        needsPickup = false;
    }

    // ── Validation ──

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

    // ── Item lookup ──

    private static Item lookupItem(String itemName) {
        Identifier itemId = Identifier.ofVanilla(itemName);
        Item item = Registries.ITEM.get(itemId);
        if (item == null || item == Items.AIR) {
            ChatInterceptor.sendFeedback("Unknown item: '" + itemName + "'.");
            return null;
        }
        return item;
    }

    // ── Recipe finding ──

    private static RecipeDisplayEntry findRecipeDisplay(ClientPlayerEntity player, Item targetItem, String itemName) {
        ClientRecipeBook recipeBook = player.getRecipeBook();
        List<RecipeResultCollection> collections = recipeBook.getOrderedResults();
        RecipeDisplayEntry threeByThree = null;

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

                if (result == null) continue;
                if (!slotDisplayMatches(result, targetItem)) continue;

                // 3x3 recipes: remember but don't return to 2x2 path
                if (width > 2 || height > 2) {
                    threeByThree = entry;
                    continue;
                }

                LOG.info("findRecipeDisplay: found 2x2 recipe for '{}'", itemName);
                return entry;
            }
        }

        // If we found a 3x3 recipe (but no 2x2), return it for the 3x3 path
        if (threeByThree != null) {
            LOG.info("findRecipeDisplay: found 3x3 recipe for '{}'", itemName);
            return threeByThree;
        }

        LOG.info("findRecipeDisplay: no recipe for '{}'", itemName);
        return null;
    }

    // ── Recipe classification ──

    private static boolean recipeNeeds3x3(RecipeDisplayEntry entry) {
        RecipeDisplay display = entry.display();
        if (display instanceof ShapedCraftingRecipeDisplay shaped) {
            return shaped.width() > 2 || shaped.height() > 2;
        }
        if (display instanceof ShapelessCraftingRecipeDisplay shapeless) {
            return shapeless.ingredients().size() > 4;
        }
        return false;
    }

    // ── Output count ──

    private static int getOutputCount(RecipeDisplayEntry entry, Item targetItem) {
        RecipeDisplay display = entry.display();
        SlotDisplay result = null;
        if (display instanceof ShapedCraftingRecipeDisplay shaped) {
            result = shaped.result();
        } else if (display instanceof ShapelessCraftingRecipeDisplay shapeless) {
            result = shapeless.result();
        }
        if (result == null) return 0;
        return getCountFromSlotDisplay(result);
    }

    // ── SlotDisplay helpers ──

    private static boolean slotDisplayMatches(SlotDisplay slot, Item target) {
        if (slot instanceof SlotDisplay.ItemSlotDisplay itemSlot) {
            return itemSlot.item().value() == target;
        }
        if (slot instanceof SlotDisplay.StackSlotDisplay stackSlot) {
            return stackSlot.stack().getItem() == target;
        }
        if (slot instanceof SlotDisplay.CompositeSlotDisplay composite) {
            for (SlotDisplay child : composite.contents()) {
                if (slotDisplayMatches(child, target)) return true;
            }
        }
        return false;
    }

    private static int getCountFromSlotDisplay(SlotDisplay slot) {
        if (slot instanceof SlotDisplay.StackSlotDisplay stackSlot) {
            return stackSlot.stack().getCount();
        }
        if (slot instanceof SlotDisplay.ItemSlotDisplay) {
            return 1;
        }
        if (slot instanceof SlotDisplay.CompositeSlotDisplay composite) {
            for (SlotDisplay child : composite.contents()) {
                int c = getCountFromSlotDisplay(child);
                if (c > 0) return c;
            }
        }
        return 0;
    }

    private static Item getItemFromSlotDisplay(SlotDisplay slot) {
        if (slot instanceof SlotDisplay.ItemSlotDisplay itemSlot) {
            return itemSlot.item().value();
        }
        if (slot instanceof SlotDisplay.StackSlotDisplay stackSlot) {
            return stackSlot.stack().getItem();
        }
        if (slot instanceof SlotDisplay.CompositeSlotDisplay composite) {
            for (SlotDisplay child : composite.contents()) {
                Item item = getItemFromSlotDisplay(child);
                if (item != null) return item;
            }
        }
        return null;
    }

    private static TagKey<Item> getTagFromSlotDisplay(SlotDisplay slot) {
        if (slot instanceof SlotDisplay.TagSlotDisplay tagSlot) {
            return tagSlot.tag();
        }
        if (slot instanceof SlotDisplay.CompositeSlotDisplay composite) {
            for (SlotDisplay child : composite.contents()) {
                TagKey<Item> tag = getTagFromSlotDisplay(child);
                if (tag != null) return tag;
            }
        }
        return null;
    }

    // ── Inventory scanning ──

    private static int findCraftingTableInHotbar(ClientPlayerEntity player) {
        for (int i = 0; i < 9; i++) {
            if (player.getInventory().getStack(i).isOf(Items.CRAFTING_TABLE)) {
                return i;
            }
        }
        return -1;
    }

    private static boolean hasCraftingTableAnywhere(ClientPlayerEntity player) {
        for (int i = 9; i < player.getInventory().size(); i++) {
            if (player.getInventory().getStack(i).isOf(Items.CRAFTING_TABLE)) {
                return true;
            }
        }
        return false;
    }

    private static int countInInventory(ClientPlayerEntity player, Item item) {
        int total = 0;
        for (int i = 0; i < player.getInventory().size(); i++) {
            ItemStack stack = player.getInventory().getStack(i);
            if (stack.isOf(item)) total += stack.getCount();
        }
        return total;
    }

    private static int countTagInInventory(ClientPlayerEntity player, TagKey<Item> tag) {
        int total = 0;
        for (int i = 0; i < player.getInventory().size(); i++) {
            ItemStack stack = player.getInventory().getStack(i);
            if (stack.isIn(tag)) total += stack.getCount();
        }
        return total;
    }

    // ── Ingredient checking ──

    private static String checkIngredients(RecipeDisplayEntry entry, ClientPlayerEntity player, int batches) {
        RecipeDisplay display = entry.display();
        List<SlotDisplay> ingredients = null;

        if (display instanceof ShapedCraftingRecipeDisplay shaped) {
            ingredients = shaped.ingredients();
        } else if (display instanceof ShapelessCraftingRecipeDisplay shapeless) {
            ingredients = shapeless.ingredients();
        }

        if (ingredients == null) return null;

        Map<Item, Integer> neededItems = new HashMap<>();
        Map<TagKey<Item>, Integer> neededTags = new HashMap<>();

        for (SlotDisplay slot : ingredients) {
            if (slot instanceof SlotDisplay.EmptySlotDisplay) continue;

            TagKey<Item> tag = getTagFromSlotDisplay(slot);
            if (tag != null) {
                neededTags.merge(tag, batches, Integer::sum);
                continue;
            }

            Item item = getItemFromSlotDisplay(slot);
            if (item != null) {
                neededItems.merge(item, batches, Integer::sum);
            }
        }

        for (Map.Entry<Item, Integer> e : neededItems.entrySet()) {
            int available = countInInventory(player, e.getKey());
            if (available < e.getValue()) {
                return "Not enough ingredients. Need " + e.getValue()
                    + "x " + e.getKey().getName().getString() + ", have " + available + ".";
            }
        }

        for (Map.Entry<TagKey<Item>, Integer> e : neededTags.entrySet()) {
            int available = countTagInInventory(player, e.getKey());
            if (available < e.getValue()) {
                return "Not enough ingredients. Need " + e.getValue()
                    + "x items matching tag, have " + available + ".";
            }
        }

        return null;
    }

    // ── Packet sending ──

    private static void sendCraftPacket(MinecraftClient client) {
        int syncId = client.player.currentScreenHandler.syncId;
        CraftRequestC2SPacket packet = new CraftRequestC2SPacket(syncId, currentRecipeId, false);
        client.getNetworkHandler().sendPacket(packet);
    }

    // ── Chat feedback ──

    private static void sendError(MinecraftClient client, String msg) {
        LOG.warn("sendError: {}", msg);
        if (client.player != null) {
            client.player.sendMessage(Text.literal("[RecipeCraft] " + msg), false);
        }
    }

    private static void sendOk(MinecraftClient client, String msg) {
        LOG.info("sendOk: {}", msg);
        if (client.player != null) {
            client.player.sendMessage(Text.literal("[RecipeCraft] " + msg), false);
        }
    }
}
