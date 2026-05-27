package com.botinterface;

import it.unimi.dsi.fastutil.ints.Int2ObjectMaps;
import net.minecraft.client.MinecraftClient;
import net.minecraft.item.Item;
import net.minecraft.item.Items;
import net.minecraft.network.packet.c2s.play.ClickSlotC2SPacket;
import net.minecraft.registry.Registries;
import net.minecraft.screen.slot.SlotActionType;
import net.minecraft.screen.sync.ItemStackHash;
import net.minecraft.util.Identifier;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.ArrayList;
import java.util.List;

/** Swap items from main inventory into hotbar slots. */
public class HotbarSwapper {
    private static final Logger LOG = LoggerFactory.getLogger("BotInterface-Swap");

    /**
     * Swap items from inventory into hotbar.
     * @param itemsToHotbar  REQUIRED: item names to move INTO hotbar slots 0..N-1
     * @param itemsFromHotbar OPTIONAL: item names currently in hotbar to move back to inventory.
     *                        If provided, must have same length as itemsToHotbar.
     * @return number of items successfully swapped
     */
    public static int swapToHotbar(MinecraftClient client, List<String> itemsToHotbar,
                                    List<String> itemsFromHotbar) {
        if (client.player == null || client.getNetworkHandler() == null) {
            LOG.error("swapToHotbar: not in game");
            return 0;
        }

        if (itemsToHotbar == null || itemsToHotbar.isEmpty()) {
            LOG.error("swapToHotbar: itemsToHotbar is required and must not be empty");
            return 0;
        }

        if (itemsFromHotbar != null && itemsFromHotbar.size() != itemsToHotbar.size()) {
            LOG.error("swapToHotbar: itemsFromHotbar length ({}) must equal itemsToHotbar length ({})",
                itemsFromHotbar.size(), itemsToHotbar.size());
            return 0;
        }

        int syncId = client.player.currentScreenHandler.syncId;
        int swapped = 0;

        for (int hotbarSlot = 0; hotbarSlot < itemsToHotbar.size() && hotbarSlot < 9; hotbarSlot++) {
            String itemName = itemsToHotbar.get(hotbarSlot);
            Item targetItem = lookupItem(itemName);
            if (targetItem == null) {
                LOG.warn("swapToHotbar: unknown item '{}', skipping", itemName);
                continue;
            }

            // Find the item in inventory (slots 9-35)
            int invSlot = -1;
            var inv = client.player.getInventory();
            for (int i = 9; i < inv.size(); i++) {
                if (inv.getStack(i).isOf(targetItem)) { invSlot = i; break; }
            }

            if (invSlot < 0) {
                LOG.warn("swapToHotbar: '{}' not found in inventory", itemName);
                continue;
            }

            LOG.info("swapToHotbar: swapping inv[{}] ({}) <-> hotbar[{}]",
                invSlot, itemName, hotbarSlot);

            // SWAP action with button=hotbarSlot swaps inventory slot with hotbar[hotbarSlot]
            ClickSlotC2SPacket packet = new ClickSlotC2SPacket(
                syncId, client.player.currentScreenHandler.getRevision(),
                (short) invSlot, (byte) hotbarSlot, SlotActionType.SWAP,
                Int2ObjectMaps.emptyMap(), ItemStackHash.EMPTY);
            client.getNetworkHandler().sendPacket(packet);
            swapped++;
        }

        LOG.info("swapToHotbar: {} items swapped", swapped);
        return swapped;
    }

    private static Item lookupItem(String name) {
        Item item = Registries.ITEM.get(Identifier.ofVanilla(name));
        return (item != null && item != Items.AIR) ? item : null;
    }
}
