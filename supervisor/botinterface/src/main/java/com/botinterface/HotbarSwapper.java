package com.botinterface;

import net.minecraft.client.MinecraftClient;
import net.minecraft.item.Item;
import net.minecraft.item.Items;
import net.minecraft.registry.Registries;
import net.minecraft.util.Identifier;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.ArrayList;
import java.util.List;

public class HotbarSwapper {
    private static final Logger LOG = LoggerFactory.getLogger("BotInterface-Swap");

    public static int swapToHotbar(MinecraftClient client, List<String> itemsToHotbar,
                                    List<String> itemsFromHotbar) {
        if (client.player == null) { LOG.error("[CLI] not in game"); return 0; }
        if (itemsToHotbar == null || itemsToHotbar.isEmpty()) {
            LOG.error("[CLI] itemsToHotbar required"); return 0;
        }

        int queued = 0;
        for (int i = 0; i < itemsToHotbar.size() && i < 9; i++) {
            Item target = lookupItem(itemsToHotbar.get(i));
            if (target == null) continue;

            int invSlot = -1;
            var inv = client.player.getInventory();
            for (int s = 9; s < inv.size(); s++) {
                if (inv.getStack(s).isOf(target)) { invSlot = s; break; }
            }
            if (invSlot < 0) continue;

            int hotbarSlot = i;
            if (itemsFromHotbar != null && i < itemsFromHotbar.size()) {
                Item fromItem = lookupItem(itemsFromHotbar.get(i));
                if (fromItem != null) {
                    for (int h = 0; h < 9; h++) {
                        if (inv.getStack(h).isOf(fromItem)) { hotbarSlot = h; break; }
                    }
                }
            }

            LOG.info("[CLI] QUEUE   src[{}]= {} x{} → hot[{}]  target={}",
                invSlot,
                inv.getStack(invSlot).getItem().getName().getString(),
                inv.getStack(invSlot).getCount(),
                hotbarSlot, itemsToHotbar.get(i));

            BackgroundSwapHandler.queueBackgroundSwap(invSlot, hotbarSlot);
            queued++;
        }

        LOG.info("[CLI] RESULT  queued={}/{}", queued, Math.min(itemsToHotbar.size(), 9));
        return queued;
    }

    private static Item lookupItem(String name) {
        Item item = Registries.ITEM.get(Identifier.ofVanilla(name));
        return (item != null && item != Items.AIR) ? item : null;
    }
}
