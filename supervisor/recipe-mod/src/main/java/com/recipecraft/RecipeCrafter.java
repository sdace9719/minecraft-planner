package com.recipecraft;

import java.util.ArrayList;
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
    private static final FurnaceSmelter furnaceSmelter = new FurnaceSmelter();
    private static final BulkCrafter bulkCrafter = new BulkCrafter();
    private static final BulkSmelter bulkSmelter = new BulkSmelter();
    // Queue for 2x2-only bulk crafting (no table needed, one item after another)
    private static final List<CraftRequest> bulk2x2Queue = new ArrayList<>();
    private static final List<NetworkRecipeId> bulk2x2RecipeIds = new ArrayList<>();
    private static final List<Integer> bulk2x2BatchCounts = new ArrayList<>();
    private static int bulk2x2Index = 0;
    private static BulkCraftListener bulk2x2Listener;

    public static void register() {
        ClientTickEvents.END_CLIENT_TICK.register(RecipeCrafter::onClientTick);
    }

    public static boolean isBusy() {
        return bulkSmelter.isActive() || bulkCrafter.isActive()
            || furnaceSmelter.isActive() || tableCrafter.isActive()
            || !bulk2x2Queue.isEmpty();
    }

    /** Returns last positions from bulk craft/smelt as "x,y,z" strings. */
    public static List<String> getLastPositions() {
        List<String> all = new ArrayList<>();
        all.addAll(bulkCrafter.getLastPositions());
        all.addAll(bulkSmelter.getLastPositions());
        return all;
    }

    private static void onClientTick(MinecraftClient client) {
        if (bulkSmelter.isActive()) {
            bulkSmelter.onTick(client);
            return;
        }
        if (bulkCrafter.isActive()) {
            bulkCrafter.onTick(client);
            return;
        }
        if (furnaceSmelter.isActive()) {
            furnaceSmelter.onTick(client);
            return;
        }
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
            // Check if a 2x2 bulk queue has more items
            if (!bulk2x2Queue.isEmpty() && bulk2x2Index < bulk2x2Queue.size()) {
                notifyBulk2x2ItemComplete();
                startNextBulk2x2();
            } else if (!bulk2x2Queue.isEmpty()) {
                notifyBulk2x2ItemComplete();
                // All 2x2 bulk items done
                LOG.info("bulkCraft (2x2): all {} items complete", bulk2x2Queue.size());
                if (bulk2x2Listener != null) bulk2x2Listener.onAllComplete();
                clearBulk2x2();
                reset();
            } else {
                sendOk(client, "Crafted " + totalRequested + "x items.");
                reset();
            }
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
            LOG.error("craft: no recipe for '{}'", itemName);
            ChatInterceptor.sendFeedback("No crafting recipe for '" + itemName + "'.");
            return;
        }

        int outputPerCraft = getOutputCount(found);
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

    // ── Smelt entry point ──

    // Burn time in ticks for common fuel items (standard smelting takes 200 ticks)
    private static final Map<Item, Integer> FUEL_BURN_TIMES = buildFuelMap();

    private static Map<Item, Integer> buildFuelMap() {
        Map<Item, Integer> map = new HashMap<>();
        map.put(Items.COAL, 1600);              // 8 items
        map.put(Items.CHARCOAL, 1600);          // 8 items
        map.put(Items.COAL_BLOCK, 16000);        // 80 items
        map.put(Items.LAVA_BUCKET, 20000);       // 100 items
        map.put(Items.BLAZE_ROD, 2400);         // 12 items
        map.put(Items.DRIED_KELP_BLOCK, 4000);   // 20 items
        // Wooden items: 300 ticks = 1.5 items
        map.put(Items.OAK_PLANKS, 300);
        map.put(Items.SPRUCE_PLANKS, 300);
        map.put(Items.BIRCH_PLANKS, 300);
        map.put(Items.JUNGLE_PLANKS, 300);
        map.put(Items.ACACIA_PLANKS, 300);
        map.put(Items.DARK_OAK_PLANKS, 300);
        map.put(Items.CHERRY_PLANKS, 300);
        map.put(Items.MANGROVE_PLANKS, 300);
        map.put(Items.BAMBOO_PLANKS, 300);
        map.put(Items.CRIMSON_PLANKS, 300);
        map.put(Items.WARPED_PLANKS, 300);
        map.put(Items.OAK_LOG, 300);
        map.put(Items.SPRUCE_LOG, 300);
        map.put(Items.BIRCH_LOG, 300);
        map.put(Items.JUNGLE_LOG, 300);
        map.put(Items.ACACIA_LOG, 300);
        map.put(Items.DARK_OAK_LOG, 300);
        map.put(Items.CHERRY_LOG, 300);
        map.put(Items.MANGROVE_LOG, 300);
        map.put(Items.BAMBOO_BLOCK, 300);
        map.put(Items.CRIMSON_STEM, 300);
        map.put(Items.WARPED_STEM, 300);
        map.put(Items.STICK, 100);              // 0.5 items
        map.put(Items.BAMBOO, 50);              // 0.25 items
        map.put(Items.WOODEN_PICKAXE, 200);     // 1 item
        map.put(Items.WOODEN_AXE, 200);
        map.put(Items.WOODEN_SHOVEL, 200);
        map.put(Items.WOODEN_HOE, 200);
        map.put(Items.WOODEN_SWORD, 200);
        return map;
    }

    private static int getFuelBurnTicks(Item item) {
        Integer ticks = FUEL_BURN_TIMES.get(item);
        if (ticks != null) return ticks;
        return 0; // not a known fuel
    }

    private static final List<Item> ALL_PLANKS = List.of(
        Items.OAK_PLANKS, Items.SPRUCE_PLANKS, Items.BIRCH_PLANKS, Items.JUNGLE_PLANKS,
        Items.ACACIA_PLANKS, Items.DARK_OAK_PLANKS, Items.CHERRY_PLANKS,
        Items.MANGROVE_PLANKS, Items.BAMBOO_PLANKS, Items.CRIMSON_PLANKS, Items.WARPED_PLANKS);

    private static boolean isPlank(Item item) {
        return ALL_PLANKS.contains(item);
    }

    private static Item findPlankWithQty(ClientPlayerEntity player, int needed) {
        for (Item plank : ALL_PLANKS) {
            int count = 0;
            for (int i = 0; i < player.getInventory().size(); i++) {
                ItemStack stack = player.getInventory().getStack(i);
                if (stack.isOf(plank)) count += stack.getCount();
            }
            if (count >= needed) return plank;
        }
        return null; // no single plank type has enough
    }

    private static int calcFuelQty(int smeltQty, Item fuelItem) {
        int burnTicks = getFuelBurnTicks(fuelItem);
        if (burnTicks <= 0) return -1; // signal: not a fuel
        int fuelQty = (int) Math.ceil((double) smeltQty * 200.0 / (double) burnTicks);
        if (fuelQty > 64) fuelQty = 64;
        return fuelQty;
    }

    public static void smelt(MinecraftClient client, String itemName, int smeltQty, String fuelName) {
        LOG.info("smelt: item='{}' smeltQty={} fuel='{}'", itemName, smeltQty, fuelName);
        if (!validateClientState(client)) {
            LOG.error("smelt: invalid client state");
            return;
        }

        ClientPlayerEntity player = client.player;

        // Look up smeltable item
        Item smeltItem = lookupItem(itemName);
        if (smeltItem == null) return;

        // Look up fuel item. If default "oak_planks", find any plank type with enough qty.
        Item fuelItem = lookupItem(fuelName);
        if (fuelItem == null) {
            sendError(client, "Unknown fuel item: '" + fuelName + "'.");
            return;
        }

        // Calculate fuel quantity based on burn time
        int fuelQty = calcFuelQty(smeltQty, fuelItem);
        if (fuelQty <= 0) {
            sendError(client, "'" + fuelItem.getName().getString()
                + "' is not a known fuel. Use coal, planks, logs, etc.");
            return;
        }
        LOG.info("smelt: fuelQty={} (burnTicks={})", fuelQty, getFuelBurnTicks(fuelItem));

        // If fuel is a plank type, find the best plank that has enough qty
        if (isPlank(fuelItem)) {
            Item bestPlank = findPlankWithQty(player, fuelQty);
            if (bestPlank != null) {
                fuelItem = bestPlank;
            }
        }

        // Find furnace in hotbar
        int furnaceSlot = -1;
        for (int i = 0; i < 9; i++) {
            if (player.getInventory().getStack(i).isOf(Items.FURNACE)) {
                furnaceSlot = i;
                break;
            }
        }
        if (furnaceSlot < 0) {
            for (int i = 9; i < player.getInventory().size(); i++) {
                if (player.getInventory().getStack(i).isOf(Items.FURNACE)) {
                    sendError(client, "Furnace must be in the hotbar.");
                    return;
                }
            }
            sendError(client, "No furnace in inventory.");
            return;
        }
        LOG.info("smelt: furnace at hotbar[{}]", furnaceSlot);

        // Verify sufficient smeltable items
        int haveSmelt = 0;
        for (int i = 0; i < player.getInventory().size(); i++) {
            if (player.getInventory().getStack(i).isOf(smeltItem)) {
                haveSmelt += player.getInventory().getStack(i).getCount();
            }
        }
        if (haveSmelt < smeltQty) {
            sendError(client, "Not enough " + smeltItem.getName().getString()
                + ". Need " + smeltQty + ", have " + haveSmelt + ".");
            return;
        }

        // Verify sufficient fuel
        int haveFuel = 0;
        for (int i = 0; i < player.getInventory().size(); i++) {
            if (player.getInventory().getStack(i).isOf(fuelItem)) {
                haveFuel += player.getInventory().getStack(i).getCount();
            }
        }
        if (haveFuel < fuelQty) {
            sendError(client, "Not enough fuel (" + fuelItem.getName().getString()
                + "). Need " + fuelQty + ", have " + haveFuel + ".");
            return;
        }

        LOG.info("smelt: all checks passed, starting FurnaceSmelter");
        furnaceSmelter.start(client, smeltItem, smeltQty, fuelItem, fuelQty, furnaceSlot);
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

    private static int getOutputCount(RecipeDisplayEntry entry) {
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

    private static void startNextBulk2x2() {
        CraftRequest req = bulk2x2Queue.get(bulk2x2Index);
        currentRecipeId = bulk2x2RecipeIds.get(bulk2x2Index);
        int batches = bulk2x2BatchCounts.get(bulk2x2Index);
        totalRequested = req.count();
        batchesRemaining = batches;
        needsPickup = false;
        LOG.info("bulkCraft (2x2): item {}/{} '{}' x{} batches={}",
            bulk2x2Index + 1, bulk2x2Queue.size(), req.itemName(), req.count(), batches);
        bulk2x2Index++;
    }

    private static void notifyBulk2x2ItemComplete() {
        // Called when a 2x2 item finishes — the item at (bulk2x2Index - 1) just completed
        if (bulk2x2Listener != null && bulk2x2Index > 0) {
            CraftRequest done = bulk2x2Queue.get(bulk2x2Index - 1);
            bulk2x2Listener.onItemComplete(bulk2x2Index - 1, done.itemName(), done.count());
        }
    }

    private static void clearBulk2x2() {
        bulk2x2Queue.clear();
        bulk2x2RecipeIds.clear();
        bulk2x2BatchCounts.clear();
        bulk2x2Index = 0;
        bulk2x2Listener = null;
    }

    // ── Bulk crafting/smelting API ──

    public static BulkResult bulkCraft(MinecraftClient client, List<CraftRequest> requests,
                                        BulkCraftListener listener) {
        return bulkCraft(client, requests, listener, false);
    }

    public static BulkResult bulkCraft(MinecraftClient client, List<CraftRequest> requests,
                                        BulkCraftListener listener, boolean skipBreak) {
        LOG.info("bulkCraft: {} items", requests.size());
        if (!validateClientState(client)) return BulkResult.fail("Not in a game world.");
        ClientPlayerEntity player = client.player;

        List<NetworkRecipeId> recipeIds = new ArrayList<>();
        List<Integer> batchCounts = new ArrayList<>();
        boolean needs3x3 = false;
        MergedIngredients merged = new MergedIngredients();

        for (CraftRequest req : requests) {
            Item item = lookupItem(req.itemName());
            if (item == null) return BulkResult.fail("Unknown item: " + req.itemName());

            RecipeDisplayEntry entry = findRecipeDisplay(player, item, req.itemName());
            if (entry == null) return BulkResult.fail("No recipe for: " + req.itemName());

            int perCraft = getOutputCount(entry);
            if (perCraft <= 0) return BulkResult.fail("Cannot determine output count for: " + req.itemName());
            if (req.count() % perCraft != 0)
                return BulkResult.fail(req.itemName() + ": count must be multiple of " + perCraft);

            int batches = req.count() / perCraft;
            recipeIds.add(entry.id());
            batchCounts.add(batches);

            if (recipeNeeds3x3(entry)) needs3x3 = true;

            // Merge ingredient requirements
            RecipeDisplay display = entry.display();
            List<SlotDisplay> ingredients = null;
            if (display instanceof ShapedCraftingRecipeDisplay shaped) ingredients = shaped.ingredients();
            else if (display instanceof ShapelessCraftingRecipeDisplay shapeless) ingredients = shapeless.ingredients();
            if (ingredients != null) {
                for (SlotDisplay slot : ingredients) {
                    if (slot instanceof SlotDisplay.EmptySlotDisplay) continue;
                    TagKey<Item> tag = getTagFromSlotDisplay(slot);
                    if (tag != null) { merged.addTag(tag, batches); continue; }
                    Item ingredientItem = getItemFromSlotDisplay(slot);
                    if (ingredientItem != null) merged.addItem(ingredientItem, batches);
                }
            }
        }

        if (needs3x3) {
            int tableSlot = findCraftingTableInHotbar(player);
            if (tableSlot < 0)
                return BulkResult.fail(hasCraftingTableAnywhere(player)
                    ? "Crafting table must be in the hotbar." : "No crafting table in inventory.");
            String err = merged.checkAgainstInventory(player, RecipeCrafter::countInInventory, RecipeCrafter::countTagInInventory);
            if (err != null) return BulkResult.fail(err);
            int totalBatches = batchCounts.stream().mapToInt(Integer::intValue).sum();
            LOG.info("bulkCraft: {} items, {} total batches, tableSlot={} skipBreak={}", requests.size(), totalBatches, tableSlot, skipBreak);
            bulkCrafter.setSkipBreak(skipBreak);
            bulkCrafter.start(client, requests, recipeIds, batchCounts, tableSlot, listener);
            return BulkResult.ok(totalBatches);
        }

        // All 2x2 — no crafting table needed, process one after another via tick loop
        clearBulk2x2();
        bulk2x2Queue.addAll(requests);
        bulk2x2RecipeIds.addAll(recipeIds);
        bulk2x2BatchCounts.addAll(batchCounts);
        bulk2x2Index = 0;
        bulk2x2Listener = listener;
        startNextBulk2x2();
        int totalBatches = batchCounts.stream().mapToInt(Integer::intValue).sum();
        LOG.info("bulkCraft (all 2x2): {} items, {} total batches", requests.size(), totalBatches);
        return BulkResult.ok(totalBatches);
    }

    public static BulkResult bulkSmelt(MinecraftClient client, List<SmeltRequest> requests,
                                        BulkSmeltListener listener) {
        LOG.info("bulkSmelt: {} items", requests.size());
        if (!validateClientState(client)) return BulkResult.fail("Not in a game world.");
        ClientPlayerEntity player = client.player;

        List<Item> smeltItems = new ArrayList<>();
        List<Integer> smeltQtys = new ArrayList<>();
        List<Item> fuelItems = new ArrayList<>();
        List<Integer> fuelQtys = new ArrayList<>();
        int totalBatches = 0;
        Map<Item, Integer> totalSmeltNeeded = new HashMap<>();
        Map<Item, Integer> totalFuelNeeded = new HashMap<>();

        for (SmeltRequest req : requests) {
            Item smeltItem = lookupItem(req.itemName());
            if (smeltItem == null) return BulkResult.fail("Unknown item: " + req.itemName());

            Item fuelItem = lookupItem(req.fuelName());
            if (fuelItem == null) return BulkResult.fail("Unknown fuel: " + req.fuelName());

            int fq = calcFuelQty(req.count(), fuelItem);
            if (fq <= 0) return BulkResult.fail("'" + req.fuelName() + "' is not a known fuel.");

            if (isPlank(fuelItem)) {
                Item best = findPlankWithQty(player, fq);
                if (best != null) fuelItem = best;
            }

            smeltItems.add(smeltItem);
            smeltQtys.add(req.count());
            fuelItems.add(fuelItem);
            fuelQtys.add(fq);
            totalBatches++;

            totalSmeltNeeded.merge(smeltItem, req.count(), Integer::sum);
            totalFuelNeeded.merge(fuelItem, fq, Integer::sum);
        }

        int furnaceSlot = -1;
        for (int i = 0; i < 9; i++) {
            if (player.getInventory().getStack(i).isOf(Items.FURNACE)) { furnaceSlot = i; break; }
        }
        if (furnaceSlot < 0) {
            for (int i = 9; i < player.getInventory().size(); i++) {
                if (player.getInventory().getStack(i).isOf(Items.FURNACE))
                    return BulkResult.fail("Furnace must be in the hotbar.");
            }
            return BulkResult.fail("No furnace in inventory.");
        }

        for (var e : totalSmeltNeeded.entrySet()) {
            int have = countInInventory(player, e.getKey());
            if (have < e.getValue())
                return BulkResult.fail("Not enough " + e.getKey().getName().getString()
                    + ". Need " + e.getValue() + ", have " + have + ".");
        }
        for (var e : totalFuelNeeded.entrySet()) {
            int have = countInInventory(player, e.getKey());
            if (have < e.getValue())
                return BulkResult.fail("Not enough fuel (" + e.getKey().getName().getString()
                    + "). Need " + e.getValue() + ", have " + have + ".");
        }

        LOG.info("bulkSmelt: {} items, {} furnace batches", requests.size(), totalBatches);
        bulkSmelter.start(client, requests, smeltItems, smeltQtys, fuelItems, fuelQtys, furnaceSlot, listener);
        return BulkResult.ok(totalBatches);
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
