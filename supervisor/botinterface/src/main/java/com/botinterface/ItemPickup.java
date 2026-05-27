package com.botinterface;

import net.minecraft.client.MinecraftClient;
import net.minecraft.entity.ItemEntity;
import net.minecraft.item.Item;
import net.minecraft.item.Items;
import net.minecraft.registry.Registries;
import net.minecraft.util.Identifier;
import net.minecraft.util.math.Box;
import net.minecraft.util.math.Vec3d;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.List;

/** Pick up a dropped item by walking to it via Baritone #goto command. */
public class ItemPickup {
    private static final Logger LOG = LoggerFactory.getLogger("BotInterface-Pickup");
    private static final int SEARCH_RADIUS_H = 10;
    private static final int SEARCH_RADIUS_V = 2;
    private static final int GOTO_TIMEOUT_TICKS = 100; // 5 seconds
    private static final int PICKUP_WAIT_TICKS = 20;   // 1 second

    /**
     * Walk to the nearest dropped item matching {@code itemName} and wait for pickup.
     * @return true if item was picked up, false otherwise.
     */
    public static boolean pickupDroppedItem(MinecraftClient client, String itemName) {
        if (client.player == null || client.world == null) {
            LOG.warn("pickupDroppedItem: not in game");
            return false;
        }

        Item targetItem = lookupItem(itemName);
        if (targetItem == null) {
            LOG.warn("pickupDroppedItem: unknown item '{}'", itemName);
            return false;
        }

        // Find nearest dropped entity
        Vec3d playerPos = new Vec3d(client.player.getX(), client.player.getY(), client.player.getZ());
        Box searchBox = new Box(
            playerPos.x - SEARCH_RADIUS_H, playerPos.y - SEARCH_RADIUS_V, playerPos.z - SEARCH_RADIUS_H,
            playerPos.x + SEARCH_RADIUS_H, playerPos.y + SEARCH_RADIUS_V, playerPos.z + SEARCH_RADIUS_H
        );

        List<ItemEntity> entities = client.world.getEntitiesByClass(
            ItemEntity.class, searchBox, e -> e.getStack().isOf(targetItem));

        if (entities.isEmpty()) {
            LOG.info("pickupDroppedItem: no dropped '{}' within {} blocks", itemName, SEARCH_RADIUS_H);
            return false;
        }

        // Find nearest
        ItemEntity nearest = entities.get(0);
        double nearestDist = distSq(playerPos, nearest.getX(), nearest.getY(), nearest.getZ());
        for (int i = 1; i < entities.size(); i++) {
            var e = entities.get(i);
            double d = distSq(playerPos, e.getX(), e.getY(), e.getZ());
            if (d < nearestDist) { nearest = entities.get(i); nearestDist = d; }
        }

        LOG.info("pickupDroppedItem: nearest '{}' at ({},{},{}) dist={}",
            itemName, (int)nearest.getX(), (int)nearest.getY(), (int)nearest.getZ(), Math.sqrt(nearestDist));

        // Send Baritone #goto command
        int tx = (int) Math.floor(nearest.getX());
        int tz = (int) Math.floor(nearest.getZ());
        String cmd = "#goto " + tx + " " + tz;
        client.player.networkHandler.sendChatMessage(cmd);
        LOG.info("pickupDroppedItem: sent '{}'", cmd);

        // Wait for arrival
        int waited = 0;
        while (waited < GOTO_TIMEOUT_TICKS) {
            try { Thread.sleep(50); } catch (InterruptedException e) { Thread.currentThread().interrupt(); return false; }
            waited++;
            double dx = client.player.getX() - nearest.getX();
            double dy = client.player.getY() - nearest.getY();
            double dz = client.player.getZ() - nearest.getZ();
            double dist = dx*dx + dy*dy + dz*dz;
            if (dist < 2.25) break; // within 1.5 blocks
        }
        if (waited >= GOTO_TIMEOUT_TICKS) {
            LOG.warn("pickupDroppedItem: goto timeout, sending #stop");
            client.player.networkHandler.sendChatMessage("#stop");
            return false;
        }

        // Wait for item to be picked up
        int pickupWaited = 0;
        int countBefore = countInInventory(client, targetItem);
        while (pickupWaited < PICKUP_WAIT_TICKS) {
            try { Thread.sleep(50); } catch (InterruptedException e) { Thread.currentThread().interrupt(); return false; }
            pickupWaited++;
            if (countInInventory(client, targetItem) > countBefore) {
                LOG.info("pickupDroppedItem: item picked up after {} ticks", pickupWaited);
                return true;
            }
        }
        LOG.warn("pickupDroppedItem: item not picked up within 1 second");
        return false;
    }

    private static double distSq(Vec3d a, double bx, double by, double bz) {
        double dx = a.x - bx, dy = a.y - by, dz = a.z - bz;
        return dx*dx + dy*dy + dz*dz;
    }

    private static Item lookupItem(String name) {
        Item item = Registries.ITEM.get(Identifier.ofVanilla(name));
        return (item != null && item != Items.AIR) ? item : null;
    }

    private static int countInInventory(MinecraftClient client, Item item) {
        int total = 0;
        var inv = client.player.getInventory();
        for (int i = 0; i < inv.size(); i++) {
            if (inv.getStack(i).isOf(item)) total += inv.getStack(i).getCount();
        }
        return total;
    }
}
