package com.recipecraft;

import java.util.List;
import net.minecraft.client.MinecraftClient;
import net.minecraft.client.network.ClientPlayerEntity;
import net.minecraft.item.Item;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * Bulk smelting state machine. Places one furnace per item, loads it, closes it, leaves it.
 * Used by {@link RecipeCrafter#bulkSmelt}.
 */
public class BulkSmelter {
    private static final Logger LOG = LoggerFactory.getLogger("RecipeCraft-BulkSmelter");

    private enum State {
        IDLE,
        SMELT_ITEM,
        WAIT_ITEM,
        DONE
    }

    private State state = State.IDLE;
    private List<SmeltRequest> requests;
    private List<Item> smeltItems;
    private List<Integer> smeltQtys;
    private List<Item> fuelItems;
    private List<Integer> fuelQtys;
    private int furnaceSlot;
    private int currentIndex;
    private BulkSmeltListener listener;
    private final FurnaceSmelter subSmelter = new FurnaceSmelter();
    private final List<String> lastPositions = new java.util.ArrayList<>();
    private String capturedFurnacePos;

    public List<String> getLastPositions() { return lastPositions; }

    public boolean isActive() {
        return state != State.IDLE && state != State.DONE;
    }

    public void start(MinecraftClient client, List<SmeltRequest> requests,
                       List<Item> smeltItems, List<Integer> smeltQtys,
                       List<Item> fuelItems, List<Integer> fuelQtys,
                       int furnaceSlot, BulkSmeltListener listener) {
        LOG.info("=== BULK SMELT: {} items, furnaceSlot={} ===", requests.size(), furnaceSlot);
        lastPositions.clear();
        this.requests = requests;
        this.smeltItems = smeltItems;
        this.smeltQtys = smeltQtys;
        this.fuelItems = fuelItems;
        this.fuelQtys = fuelQtys;
        this.furnaceSlot = furnaceSlot;
        this.currentIndex = 0;
        this.listener = listener;
        this.state = State.SMELT_ITEM;
    }

    public void onTick(MinecraftClient client) {
        if (!isActive()) return;
        ClientPlayerEntity player = client.player;
        if (player == null || client.getNetworkHandler() == null) {
            fail("Lost connection.");
            return;
        }

        // Delegate to sub-smelter if active
        if (subSmelter.isActive()) {
            // Capture position BEFORE sub-smelter may reset
            var pos = subSmelter.getFurnacePos();
            if (pos != null) capturedFurnacePos = pos.getX() + "," + pos.getY() + "," + pos.getZ();
            subSmelter.onTick(client);
            if (!subSmelter.isActive() && state == State.WAIT_ITEM) {
                itemComplete();
            }
            return;
        }

        LOG.info("[{}] tick item={}/{}", state, currentIndex + 1, requests.size());
        switch (state) {
            case SMELT_ITEM -> stateSmeltItem(client);
            case WAIT_ITEM  -> { /* waiting for subSmelter */ }
            case DONE       -> stateDone();
        }
    }

    private void advance(State next) {
        LOG.info("  -> {}", next);
        state = next;
    }

    private void fail(String msg) {
        LOG.error("FAIL: {}", msg);
        if (listener != null) listener.onError(msg);
        reset();
    }

    private void itemComplete() {
        SmeltRequest req = requests.get(currentIndex);
        LOG.info("Item complete: {} x{} (index={})", req.itemName(), req.count(), currentIndex);
        if (capturedFurnacePos != null) { lastPositions.add(capturedFurnacePos); capturedFurnacePos = null; }
        if (listener != null) listener.onItemComplete(currentIndex, req.itemName(), req.count());
        currentIndex++;
        if (currentIndex >= requests.size()) {
            LOG.info("All items smelted");
            advance(State.DONE);
        } else {
            advance(State.SMELT_ITEM);
        }
    }

    private void reset() {
        state = State.IDLE;
        requests = null;
        smeltItems = null;
        smeltQtys = null;
        fuelItems = null;
        fuelQtys = null;
        furnaceSlot = -1;
        currentIndex = 0;
        listener = null;
    }

    // ── SMELT_ITEM ──

    private void stateSmeltItem(MinecraftClient client) {
        Item smeltItem = smeltItems.get(currentIndex);
        int smeltQty = smeltQtys.get(currentIndex);
        Item fuelItem = fuelItems.get(currentIndex);
        int fuelQty = fuelQtys.get(currentIndex);
        LOG.info("SMELT_ITEM: '{}' x{} fuel={} x{}",
            requests.get(currentIndex).itemName(), smeltQty,
            fuelItem.getName().getString(), fuelQty);
        subSmelter.start(client, smeltItem, smeltQty, fuelItem, fuelQty, furnaceSlot);
        advance(State.WAIT_ITEM);
    }

    // ── DONE ──

    private void stateDone() {
        LOG.info("DONE: bulk smelt complete — {} items", requests.size());
        if (listener != null) listener.onAllComplete();
        reset();
    }
}
