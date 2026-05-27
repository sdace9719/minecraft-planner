package com.recipecraft;

import java.util.List;
import net.minecraft.block.BlockState;
import net.minecraft.block.Blocks;
import net.minecraft.client.MinecraftClient;
import net.minecraft.client.network.ClientPlayerEntity;
import net.minecraft.network.packet.c2s.play.PlayerMoveC2SPacket;
import net.minecraft.recipe.NetworkRecipeId;
import net.minecraft.util.Hand;
import net.minecraft.util.hit.BlockHitResult;
import net.minecraft.util.math.BlockPos;
import net.minecraft.util.math.Direction;
import net.minecraft.util.math.Vec3d;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * Bulk crafting state machine. Places a crafting table once, crafts all items
 * in the list (opening/closing the table per item), then breaks the table.
 * Used by {@link RecipeCrafter#bulkCraft}.
 */
public class BulkCrafter {
    private static final Logger LOG = LoggerFactory.getLogger("RecipeCraft-BulkCrafter");

    private enum State {
        IDLE,
        PLACE_TABLE,
        WAIT_PLACE,
        WAIT_SERVER,
        CRAFT_ITEM,
        WAIT_ITEM,
        BREAK_TABLE,
        WAIT_BREAK,
        DONE
    }

    private State state = State.IDLE;
    private List<CraftRequest> requests;
    private List<NetworkRecipeId> recipeIds;
    private List<Integer> batchCounts;
    private int currentIndex;
    private BulkCraftListener listener;
    private BlockPos tablePos;
    private BlockPos placeGround;
    private int tableSlot;
    private int waitTicks;
    private final CraftingTableCrafter subCrafter = new CraftingTableCrafter();
    private List<String> lastPositions = new java.util.ArrayList<>();
    private boolean skipBreak;

    /** Returns positions of placed blocks from the last completed run. */
    public List<String> getLastPositions() { return lastPositions; }
    public void setSkipBreak(boolean skip) { this.skipBreak = skip; }

    public boolean isActive() {
        return state != State.IDLE && state != State.DONE;
    }

    public void start(MinecraftClient client, List<CraftRequest> requests,
                       List<NetworkRecipeId> recipeIds, List<Integer> batchCounts,
                       int tableSlot, BulkCraftListener listener) {
        LOG.info("=== BULK CRAFT: {} items, tableSlot={} ===", requests.size(), tableSlot);
        this.requests = requests;
        this.recipeIds = recipeIds;
        this.batchCounts = batchCounts;
        this.currentIndex = 0;
        this.listener = listener;
        this.tableSlot = tableSlot;
        this.tablePos = null;
        this.placeGround = null;
        this.waitTicks = 0;
        this.lastPositions = new java.util.ArrayList<>();
        this.state = State.PLACE_TABLE;
    }

    public void onTick(MinecraftClient client) {
        if (!isActive()) return;
        ClientPlayerEntity player = client.player;
        if (player == null || client.getNetworkHandler() == null) {
            fail(client, "Lost connection.");
            return;
        }

        // If sub-crafter is active (crafting current item), delegate
        if (subCrafter.isActive()) {
            subCrafter.onTick(client);
            if (!subCrafter.isActive()) {
                // Sub-crafter just finished — check if it failed
                if (state == State.WAIT_ITEM) {
                    itemComplete(client);
                }
            }
            return;
        }

        LOG.info("[{}] tick item={}/{}", state, currentIndex + 1, requests.size());
        switch (state) {
            case PLACE_TABLE -> statePlaceTable(client);
            case WAIT_PLACE  -> stateWaitPlace(client);
            case WAIT_SERVER -> stateWaitServer(client);
            case CRAFT_ITEM  -> stateCraftItem(client);
            case WAIT_ITEM   -> { /* waiting for subCrafter */ }
            case BREAK_TABLE -> stateBreakTable(client);
            case WAIT_BREAK  -> stateWaitBreak(client);
            case DONE         -> stateDone(client);
        }
    }

    // ── Helpers ──

    private void advance(State next) {
        LOG.info("  -> {}", next);
        state = next;
        waitTicks = 0;
    }

    private void lookAt(MinecraftClient client, BlockPos target) {
        ClientPlayerEntity player = client.player;
        double dx = (target.getX() + 0.5) - player.getX();
        double dy = (target.getY() + 0.5) - player.getEyeY();
        double dz = (target.getZ() + 0.5) - player.getZ();
        double horiz = Math.sqrt(dx * dx + dz * dz);
        float yaw = (float) Math.toDegrees(Math.atan2(-dx, dz));
        float pitch = (float) -Math.toDegrees(Math.atan2(dy, horiz));
        pitch = Math.clamp(pitch, -90.0f, 90.0f);
        player.setYaw(yaw);
        player.setPitch(pitch);
        player.setHeadYaw(yaw);
        client.getNetworkHandler().sendPacket(
            new PlayerMoveC2SPacket.LookAndOnGround(yaw, pitch, player.isOnGround(), player.horizontalCollision));
    }

    private boolean isOccupied(ClientPlayerEntity player, BlockPos pos) {
        double px = player.getX(), py = player.getY(), pz = player.getZ();
        double bx = pos.getX() + 0.5, bz = pos.getZ() + 0.5;
        return Math.abs(px - bx) < 0.6 && py - pos.getY() < 1.8
            && py - pos.getY() > -0.1 && Math.abs(pz - bz) < 0.6;
    }

    private void releaseAllKeys(MinecraftClient client) {
        client.options.useKey.setPressed(false);
        client.options.attackKey.setPressed(false);
        for (int i = 0; i < 9; i++) client.options.hotbarKeys[i].setPressed(false);
    }

    private void fail(MinecraftClient client, String msg) {
        LOG.error("FAIL: {}", msg);
        releaseAllKeys(client);
        if (listener != null) listener.onError(msg);
        reset();
    }

    private void itemComplete(MinecraftClient client) {
        CraftRequest req = requests.get(currentIndex);
        LOG.info("Item complete: {} x{} (index={})", req.itemName(), req.count(), currentIndex);
        if (listener != null) listener.onItemComplete(currentIndex, req.itemName(), req.count());
        currentIndex++;
        if (currentIndex >= requests.size()) {
            if (skipBreak) {
                LOG.info("All items crafted, skipBreak=true — leaving table in world");
                advance(State.DONE);
            } else {
                LOG.info("All items crafted, breaking table");
                advance(State.BREAK_TABLE);
            }
        } else {
            advance(State.CRAFT_ITEM);
        }
    }

    private void reset() {
        releaseAllKeys(MinecraftClient.getInstance());
        state = State.IDLE;
        requests = null;
        recipeIds = null;
        batchCounts = null;
        currentIndex = 0;
        listener = null;
        tablePos = null;
        placeGround = null;
        tableSlot = -1;
        waitTicks = 0;
    }

    // ── PLACE_TABLE ──

    private void statePlaceTable(MinecraftClient client) {
        ClientPlayerEntity player = client.player;
        player.getInventory().selectedSlot = tableSlot;
        LOG.info("PLACE_TABLE: selectedSlot={}", tableSlot);

        // Find placement position
        BlockPos playerPos = player.getBlockPos();
        for (int yOff = -1; yOff <= 1; yOff++) {
            for (int xOff = -2; xOff <= 2; xOff++) {
                for (int zOff = -2; zOff <= 2; zOff++) {
                    if (xOff == 0 && zOff == 0 && yOff == 0) continue;
                    BlockPos target = playerPos.add(xOff, yOff, zOff);
                    BlockPos ground = target.down();
                    BlockState groundState = client.world.getBlockState(ground);
                    BlockState targetState = client.world.getBlockState(target);
                    double dist = Math.sqrt(xOff*xOff + yOff*yOff + zOff*zOff);
                    if (groundState.isSolid() && targetState.isAir()
                        && !isOccupied(player, target) && dist <= 3.5) {
                        tablePos = target;
                        placeGround = ground;
                        LOG.info("PLACE_TABLE: tablePos={} ground={}", tablePos, placeGround);
                        lookAt(client, ground);
                        var hit = new BlockHitResult(
                            new Vec3d(ground.getX()+0.5, ground.getY()+1.0, ground.getZ()+0.5),
                            Direction.UP, ground, false);
                        client.interactionManager.interactBlock(player, Hand.MAIN_HAND, hit);
                        advance(State.WAIT_PLACE);
                        return;
                    }
                }
            }
        }
        fail(client, "No suitable location to place crafting table.");
    }

    private void stateWaitPlace(MinecraftClient client) {
        if (++waitTicks >= 4) {
            BlockState bs = client.world.getBlockState(tablePos);
            if (bs.isAir()) { fail(client, "Failed to place crafting table."); return; }
            if (!bs.isOf(Blocks.CRAFTING_TABLE)) { fail(client, "Blocked placement."); return; }
            LOG.info("WAIT_PLACE: table confirmed");
            advance(State.WAIT_SERVER);
        }
    }

    private void stateWaitServer(MinecraftClient client) {
        if (++waitTicks >= 6) {
            BlockState bs = client.world.getBlockState(tablePos);
            if (!bs.isOf(Blocks.CRAFTING_TABLE)) {
                fail(client, "Crafting table placement rejected by server.");
                return;
            }
            LOG.info("WAIT_SERVER: server confirmed");
            lastPositions.add(tablePos.getX() + "," + tablePos.getY() + "," + tablePos.getZ());
            advance(State.CRAFT_ITEM);
        }
    }

    // ── CRAFT_ITEM ──

    private void stateCraftItem(MinecraftClient client) {
        CraftRequest req = requests.get(currentIndex);
        NetworkRecipeId rid = recipeIds.get(currentIndex);
        int batches = batchCounts.get(currentIndex);
        LOG.info("CRAFT_ITEM: '{}' x{} batches={}", req.itemName(), req.count(), batches);

        if (currentIndex == 0) {
            // First item: table was just placed, open it via lookAt + interactBlock
            lookAt(client, tablePos);
            var hit = new BlockHitResult(tablePos.toCenterPos(), Direction.UP, tablePos, false);
            client.interactionManager.interactBlock(client.player, Hand.MAIN_HAND, hit);
            // Wait a few ticks for GUI to open, then start sub-crafter
            waitTicks = 0;
            // Start sub-crafter in OPEN mode via startOnExistingTable — but the table
            // needs the GUI open first. We'll let the sub-crafter start from LOOK_OPEN
            // which sends its own interactBlock.
            subCrafter.startOnExistingTable(client, rid, batches, req.count(), tablePos);
            advance(State.WAIT_ITEM);
        } else {
            // Subsequent items: table is already placed, just reopen it
            // The sub-crafter will handle LOOK_OPEN → WAIT_OPEN → craft → close
            subCrafter.startOnExistingTable(client, rid, batches, req.count(), tablePos);
            advance(State.WAIT_ITEM);
        }
    }

    // ── BREAK_TABLE ──

    private void stateBreakTable(MinecraftClient client) {
        LOG.info("BREAK_TABLE: breaking table at {}", tablePos);
        lookAt(client, tablePos);
        client.options.attackKey.setPressed(true);
        advance(State.WAIT_BREAK);
    }

    private void stateWaitBreak(MinecraftClient client) {
        waitTicks++;
        BlockState bs = client.world.getBlockState(tablePos);
        if (bs.isAir() || !bs.isOf(Blocks.CRAFTING_TABLE)) {
            client.options.attackKey.setPressed(false);
            LOG.info("WAIT_BREAK: table broken after {} ticks", waitTicks);
            advance(State.DONE);
        } else if (waitTicks >= 150) {
            client.options.attackKey.setPressed(false);
            fail(client, "Failed to break crafting table (timed out).");
        }
    }

    // ── DONE ──

    private void stateDone(MinecraftClient client) {
        LOG.info("DONE: bulk craft complete — {} items", requests.size());
        if (listener != null) listener.onAllComplete();
        reset();
    }
}
