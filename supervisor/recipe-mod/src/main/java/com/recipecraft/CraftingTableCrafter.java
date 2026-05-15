package com.recipecraft;

import it.unimi.dsi.fastutil.ints.Int2ObjectMaps;
import net.minecraft.block.BlockState;
import net.minecraft.block.Blocks;
import net.minecraft.client.MinecraftClient;
import net.minecraft.client.network.ClientPlayerEntity;
import net.minecraft.item.AxeItem;
import net.minecraft.item.ItemStack;
import net.minecraft.network.packet.c2s.play.ClickSlotC2SPacket;
import net.minecraft.network.packet.c2s.play.CraftRequestC2SPacket;
import net.minecraft.network.packet.c2s.play.PlayerMoveC2SPacket;
import net.minecraft.recipe.NetworkRecipeId;
import net.minecraft.screen.slot.SlotActionType;
import net.minecraft.screen.sync.ItemStackHash;
import net.minecraft.text.Text;
import net.minecraft.util.math.BlockPos;
import net.minecraft.util.math.Direction;
import net.minecraft.util.math.Vec3d;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class CraftingTableCrafter {
    private static final Logger LOG = LoggerFactory.getLogger("RecipeCraft-TableCrafter");

    private enum State {
        IDLE,
        CHECK,
        SWITCH_TABLE,
        WAIT_SWITCH,
        LOOK_PLACE,
        WAIT_PLACE,
        LOOK_OPEN,
        WAIT_OPEN,
        DO_CRAFT,
        CRAFT_WAIT,
        CLOSE_SCREEN,
        SWITCH_AXE,
        WAIT_AXE,
        LOOK_BREAK,
        WAIT_BREAK,
        DONE
    }

    private State state = State.IDLE;
    private NetworkRecipeId recipeId;
    private int batchesTotal;
    private int batchesDone;
    private int outputPerCraft;
    private int totalRequested;
    private int tableSlot;
    private int axeSlot;
    private BlockPos tablePos;
    private BlockPos placeGround;
    private int syncId;
    private int waitTicks;

    public boolean isActive() {
        return state != State.IDLE && state != State.DONE;
    }

    public void start(MinecraftClient client, NetworkRecipeId recipeId, int batches,
                      int outputPerCraft, int totalCount, int tableSlot) {
        LOG.info("=== START: batches={} perCraft={} total={} tableSlot={} ===",
            batches, outputPerCraft, totalCount, tableSlot);
        this.recipeId = recipeId;
        this.batchesTotal = batches;
        this.batchesDone = 0;
        this.outputPerCraft = outputPerCraft;
        this.totalRequested = totalCount;
        this.tableSlot = tableSlot;
        this.axeSlot = -1;
        this.tablePos = null;
        this.placeGround = null;
        this.syncId = 0;
        this.waitTicks = 0;
        this.state = State.CHECK;
    }

    // ── Main tick dispatcher ──

    public void onTick(MinecraftClient client) {
        if (!isActive()) return;

        ClientPlayerEntity player = client.player;
        if (player == null || client.getNetworkHandler() == null) {
            LOG.error("onTick: player or network null — aborting");
            fail(client, "Lost connection.");
            return;
        }

        LOG.info("[{}] tick", state);
        switch (state) {
            case CHECK        -> stateCheck(client);
            case SWITCH_TABLE -> stateSwitchTable(client);
            case WAIT_SWITCH  -> stateWaitSwitch(client);
            case LOOK_PLACE   -> stateLookPlace(client);
            case WAIT_PLACE   -> stateWaitPlace(client);
            case LOOK_OPEN    -> stateLookOpen(client);
            case WAIT_OPEN    -> stateWaitOpen(client);
            case DO_CRAFT     -> stateDoCraft(client);
            case CRAFT_WAIT   -> stateCraftWait(client);
            case CLOSE_SCREEN -> stateClose(client);
            case SWITCH_AXE   -> stateSwitchAxe(client);
            case WAIT_AXE     -> stateWaitAxe(client);
            case LOOK_BREAK   -> stateLookBreak(client);
            case WAIT_BREAK   -> stateWaitBreak(client);
            case DONE         -> stateDone(client);
        }
    }

    // ── Helpers ──

    private void advance(State next) {
        LOG.info("  -> {}", next);
        state = next;
        waitTicks = 0;
    }

    private void releaseAllKeys(MinecraftClient client) {
        client.options.useKey.setPressed(false);
        client.options.attackKey.setPressed(false);
        for (int i = 0; i < 9; i++) {
            client.options.hotbarKeys[i].setPressed(false);
        }
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

        LOG.info("  lookAt: target={} yaw={} pitch={}", target, yaw, pitch);
        player.setYaw(yaw);
        player.setPitch(pitch);
        player.setHeadYaw(yaw);
        client.getNetworkHandler().sendPacket(
            new PlayerMoveC2SPacket.LookAndOnGround(
                yaw, pitch, player.isOnGround(), player.horizontalCollision));
    }

    private boolean isOccupied(ClientPlayerEntity player, BlockPos pos) {
        double px = player.getX();
        double py = player.getY();
        double pz = player.getZ();
        double bx = pos.getX() + 0.5;
        double bz = pos.getZ() + 0.5;
        return Math.abs(px - bx) < 0.6
            && py - pos.getY() < 1.8
            && py - pos.getY() > -0.1
            && Math.abs(pz - bz) < 0.6;
    }

    private void fail(MinecraftClient client, String msg) {
        LOG.error("FAIL: {}", msg);
        releaseAllKeys(client);
        if (client.player != null) {
            client.player.sendMessage(Text.literal("[RecipeCraft] " + msg), false);
        }
        reset();
    }

    private void reset() {
        releaseAllKeys(MinecraftClient.getInstance());
        state = State.IDLE;
        recipeId = null;
        batchesTotal = 0;
        batchesDone = 0;
        outputPerCraft = 0;
        totalRequested = 0;
        tableSlot = -1;
        axeSlot = -1;
        tablePos = null;
        placeGround = null;
        syncId = 0;
        waitTicks = 0;
    }

    private static void sendOk(MinecraftClient client, String msg) {
        LOG.info("sendOk: {}", msg);
        if (client.player != null) {
            client.player.sendMessage(Text.literal("[RecipeCraft] " + msg), false);
        }
    }

    // ── CHECK ──

    private void stateCheck(MinecraftClient client) {
        ClientPlayerEntity player = client.player;

        LOG.info("CHECK: starting table craft, tableSlot={}", tableSlot);

        // Find axe in hotbar (optional)
        axeSlot = -1;
        for (int i = 0; i < 9; i++) {
            if (player.getInventory().getStack(i).getItem() instanceof AxeItem) {
                axeSlot = i;
                LOG.info("CHECK: axe at hotbar[{}]", i);
                break;
            }
        }
        if (axeSlot == -1) {
            LOG.info("CHECK: no axe in hotbar, will break with hand");
        }

        // Find placement position
        BlockPos playerPos = player.getBlockPos();
        BlockPos[] candidates = {
            playerPos.add(1, 0, 0), playerPos.add(-1, 0, 0),
            playerPos.add(0, 0, 1), playerPos.add(0, 0, -1),
            playerPos.add(1, 0, 1), playerPos.add(-1, 0, -1),
            playerPos.add(1, 0, -1), playerPos.add(-1, 0, 1),
        };

        for (BlockPos target : candidates) {
            BlockPos ground = target.down();
            BlockState groundState = client.world.getBlockState(ground);
            BlockState targetState = client.world.getBlockState(target);
            boolean blocked = isOccupied(player, target);

            LOG.info("CHECK: candidate {} groundSolid={} air={} blocked={}",
                target, groundState.isSolid(), targetState.isAir(), blocked);

            if (groundState.isSolid() && targetState.isAir() && !blocked) {
                tablePos = target;
                placeGround = ground;
                LOG.info("CHECK: selected tablePos={} ground={}", tablePos, placeGround);
                advance(State.SWITCH_TABLE);
                return;
            }
        }

        fail(client, "No suitable location to place crafting table.");
    }

    // ── SWITCH_TABLE ──

    private void stateSwitchTable(MinecraftClient client) {
        LOG.info("SWITCH_TABLE: pressing hotbar key {}", tableSlot);
        client.options.hotbarKeys[tableSlot].setPressed(true);
        advance(State.WAIT_SWITCH);
    }

    private void stateWaitSwitch(MinecraftClient client) {
        client.options.hotbarKeys[tableSlot].setPressed(false);
        LOG.info("WAIT_SWITCH: released hotbar key {}", tableSlot);
        advance(State.LOOK_PLACE);
    }

    // ── LOOK_PLACE ──

    private void stateLookPlace(MinecraftClient client) {
        lookAt(client, placeGround);
        // Use interactBlock directly — key simulation unreliable for mouse events
        var hitResult = new net.minecraft.util.hit.BlockHitResult(
            new net.minecraft.util.math.Vec3d(
                placeGround.getX() + 0.5, placeGround.getY() + 1.0, placeGround.getZ() + 0.5),
            net.minecraft.util.math.Direction.UP, placeGround, false);
        client.interactionManager.interactBlock(client.player, net.minecraft.util.Hand.MAIN_HAND, hitResult);
        LOG.info("LOOK_PLACE: interactBlock sent for ground {}", placeGround);
        advance(State.WAIT_PLACE);
    }

    // ── WAIT_PLACE ──

    private void stateWaitPlace(MinecraftClient client) {
        waitTicks++;
        if (waitTicks >= 4) {
            BlockState bs = client.world.getBlockState(tablePos);
            LOG.info("WAIT_PLACE: block at {} = {} (isAir={})", tablePos, bs.getBlock(), bs.isAir());
            if (bs.isAir()) {
                fail(client, "Failed to place crafting table — position still air.");
                return;
            }
            if (!bs.isOf(Blocks.CRAFTING_TABLE)) {
                fail(client, "Something blocked the crafting table placement (found " + bs.getBlock() + ").");
                return;
            }
            LOG.info("WAIT_PLACE: table confirmed at {}", tablePos);
            advance(State.LOOK_OPEN);
        }
    }

    // ── LOOK_OPEN ──

    private void stateLookOpen(MinecraftClient client) {
        lookAt(client, tablePos);
        var hitResult = new net.minecraft.util.hit.BlockHitResult(
            tablePos.toCenterPos(),
            net.minecraft.util.math.Direction.UP, tablePos, false);
        client.interactionManager.interactBlock(client.player, net.minecraft.util.Hand.MAIN_HAND, hitResult);
        LOG.info("LOOK_OPEN: interactBlock sent for table {}", tablePos);
        advance(State.WAIT_OPEN);
    }

    // ── WAIT_OPEN ──

    private void stateWaitOpen(MinecraftClient client) {
        waitTicks++;
        if (waitTicks >= 4) {
            syncId = client.player.currentScreenHandler.syncId;
            int invSyncId = client.player.playerScreenHandler.syncId;
            LOG.info("WAIT_OPEN: syncId={} playerInvSyncId={}", syncId, invSyncId);
            if (syncId == invSyncId) {
                fail(client, "Failed to open crafting table GUI.");
                return;
            }
            LOG.info("WAIT_OPEN: GUI confirmed open, syncId={}", syncId);
            advance(State.DO_CRAFT);
        }
    }

    // ── DO_CRAFT / CRAFT_WAIT ──

    private void stateDoCraft(MinecraftClient client) {
        LOG.info("DO_CRAFT: batch {}/{} syncId={}", batchesDone + 1, batchesTotal, syncId);
        CraftRequestC2SPacket craftPacket = new CraftRequestC2SPacket(syncId, recipeId, false);
        client.getNetworkHandler().sendPacket(craftPacket);
        advance(State.CRAFT_WAIT);
    }

    private void stateCraftWait(MinecraftClient client) {
        waitTicks++;
        if (waitTicks == 1) {
            ClickSlotC2SPacket clickPacket = new ClickSlotC2SPacket(
                syncId,
                client.player.currentScreenHandler.getRevision(),
                (short) 0,
                (byte) 0,
                SlotActionType.QUICK_MOVE,
                Int2ObjectMaps.emptyMap(),
                ItemStackHash.EMPTY);
            client.getNetworkHandler().sendPacket(clickPacket);
            LOG.info("CRAFT_WAIT: sent pickup for batch {}", batchesDone + 1);
        }
        if (waitTicks >= 2) {
            batchesDone++;
            LOG.info("CRAFT_WAIT: batch {} done, {} remaining",
                batchesDone, batchesTotal - batchesDone);
            if (batchesDone >= batchesTotal) {
                LOG.info("CRAFT_WAIT: all batches complete");
                advance(State.CLOSE_SCREEN);
            } else {
                advance(State.DO_CRAFT);
            }
        }
    }

    // ── CLOSE_SCREEN ──

    private void stateClose(MinecraftClient client) {
        LOG.info("CLOSE_SCREEN: closing crafting table");
        client.player.closeHandledScreen();
        advance(State.SWITCH_AXE);
    }

    // ── SWITCH_AXE / WAIT_AXE ──

    private void stateSwitchAxe(MinecraftClient client) {
        if (axeSlot >= 0) {
            LOG.info("SWITCH_AXE: pressing hotbar key {}", axeSlot);
            client.options.hotbarKeys[axeSlot].setPressed(true);
            advance(State.WAIT_AXE);
        } else {
            LOG.info("SWITCH_AXE: no axe, skipping");
            advance(State.LOOK_BREAK);
        }
    }

    private void stateWaitAxe(MinecraftClient client) {
        client.options.hotbarKeys[axeSlot].setPressed(false);
        LOG.info("WAIT_AXE: released hotbar key {}", axeSlot);
        advance(State.LOOK_BREAK);
    }

    // ── LOOK_BREAK / WAIT_BREAK ──

    private void stateLookBreak(MinecraftClient client) {
        lookAt(client, tablePos);
        client.options.attackKey.setPressed(true);
        LOG.info("LOOK_BREAK: attackKey pressed, facing table {}", tablePos);
        advance(State.WAIT_BREAK);
    }

    private void stateWaitBreak(MinecraftClient client) {
        waitTicks++;
        BlockState bs = client.world.getBlockState(tablePos);
        boolean broken = bs.isAir() || !bs.isOf(Blocks.CRAFTING_TABLE);

        if (broken) {
            client.options.attackKey.setPressed(false);
            LOG.info("WAIT_BREAK: table broken after {} ticks", waitTicks);
            advance(State.DONE);
        } else if (waitTicks >= 150) {
            client.options.attackKey.setPressed(false);
            LOG.error("WAIT_BREAK: timeout after {} ticks", waitTicks);
            fail(client, "Failed to break crafting table (timed out).");
        }
    }

    // ── DONE ──

    private void stateDone(MinecraftClient client) {
        LOG.info("DONE: crafted {}x items", totalRequested);
        sendOk(client, "Crafted " + totalRequested + "x items.");
        reset();
    }
}
