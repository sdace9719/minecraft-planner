package com.recipecraft;

import it.unimi.dsi.fastutil.ints.Int2ObjectMaps;
import net.minecraft.block.BlockState;
import net.minecraft.block.Blocks;
import net.minecraft.client.MinecraftClient;
import net.minecraft.client.network.ClientPlayerEntity;
import net.minecraft.item.Item;
import net.minecraft.item.ItemStack;
import net.minecraft.network.packet.c2s.play.ClickSlotC2SPacket;
import net.minecraft.network.packet.c2s.play.PlayerMoveC2SPacket;
import net.minecraft.network.packet.c2s.play.UpdateSelectedSlotC2SPacket;
import net.minecraft.screen.slot.SlotActionType;
import net.minecraft.screen.sync.ItemStackHash;
import net.minecraft.text.Text;
import net.minecraft.util.Hand;
import net.minecraft.util.hit.BlockHitResult;
import net.minecraft.util.math.BlockPos;
import net.minecraft.util.math.Direction;
import net.minecraft.util.math.Vec3d;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class FurnaceSmelter {
    private static final Logger LOG = LoggerFactory.getLogger("RecipeCraft-FurnaceSmelter");

    private enum State {
        IDLE,
        CHECK,
        SWITCH_FURNACE,
        WAIT_SWITCH,
        LOOK_PLACE,
        WAIT_PLACE,
        WAIT_SERVER,
        LOOK_OPEN,
        WAIT_OPEN,
        LOAD_INPUT_GRAB,
        LOAD_INPUT_DROP,
        LOAD_INPUT_RETURN,
        LOAD_FUEL_GRAB,
        LOAD_FUEL_DROP,
        LOAD_FUEL_RETURN,
        CLOSE_SCREEN,
        DONE
    }

    private State state = State.IDLE;
    private Item smeltItem;
    private Item fuelItem;
    private int smeltQty;
    private int fuelQty;
    private int furnaceSlot;
    private int smeltInvSlot;
    private int fuelInvSlot;
    private BlockPos furnacePos;
    private BlockPos placeGround;
    private int syncId;
    private int waitTicks;

    // For exact stack splitting
    private int loadingSourceSlot;
    private int loadingTargetFurnaceSlot;
    private int loadingNeeded;
    private int loadingStackSize;
    private int loadingSplitTicks;

    public boolean isActive() {
        return state != State.IDLE && state != State.DONE;
    }

    public void start(MinecraftClient client, Item smeltItem, int smeltQty,
                      Item fuelItem, int fuelQty, int furnaceSlot) {
        LOG.info("=== START: smeltItem={} smeltQty={} fuelItem={} fuelQty={} furnaceSlot={} ===",
            smeltItem, smeltQty, fuelItem, fuelQty, furnaceSlot);
        this.smeltItem = smeltItem;
        this.fuelItem = fuelItem;
        this.smeltQty = smeltQty;
        this.fuelQty = fuelQty;
        this.furnaceSlot = furnaceSlot;
        this.smeltInvSlot = -1;
        this.fuelInvSlot = -1;
        this.furnacePos = null;
        this.placeGround = null;
        this.syncId = 0;
        this.waitTicks = 0;
        this.loadingSourceSlot = -1;
        this.loadingTargetFurnaceSlot = -1;
        this.loadingNeeded = 0;
        this.loadingStackSize = 0;
        this.loadingSplitTicks = 0;
        this.state = State.CHECK;
    }

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
            case CHECK               -> stateCheck(client);
            case SWITCH_FURNACE      -> stateSwitchFurnace(client);
            case WAIT_SWITCH         -> stateWaitSwitch(client);
            case LOOK_PLACE          -> stateLookPlace(client);
            case WAIT_PLACE          -> stateWaitPlace(client);
            case WAIT_SERVER         -> stateWaitServer(client);
            case LOOK_OPEN           -> stateLookOpen(client);
            case WAIT_OPEN           -> stateWaitOpen(client);
            case LOAD_INPUT_GRAB     -> stateLoadGrab(client, smeltInvSlot, 0, smeltQty, State.LOAD_INPUT_DROP);
            case LOAD_INPUT_DROP    -> stateLoadDrop(client, 0, smeltInvSlot, State.LOAD_INPUT_RETURN, State.LOAD_INPUT_RETURN);
            case LOAD_INPUT_RETURN  -> stateLoadReturn(client, smeltInvSlot, State.LOAD_FUEL_GRAB);
            case LOAD_FUEL_GRAB     -> stateLoadGrab(client, fuelInvSlot, 1, fuelQty, State.LOAD_FUEL_DROP);
            case LOAD_FUEL_DROP     -> stateLoadDrop(client, 1, fuelInvSlot, State.LOAD_FUEL_RETURN, State.LOAD_FUEL_RETURN);
            case LOAD_FUEL_RETURN   -> stateLoadReturn(client, fuelInvSlot, State.CLOSE_SCREEN);
            case CLOSE_SCREEN        -> stateClose(client);
            case DONE                -> stateDone(client);
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
        player.setYaw(yaw);
        player.setPitch(pitch);
        player.setHeadYaw(yaw);
        client.getNetworkHandler().sendPacket(
            new PlayerMoveC2SPacket.LookAndOnGround(yaw, pitch, player.isOnGround(), player.horizontalCollision));
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

    private int findItemInInventory(ClientPlayerEntity player, Item item) {
        for (int i = 0; i < player.getInventory().size(); i++) {
            if (player.getInventory().getStack(i).isOf(item)) return i;
        }
        return -1;
    }

    private int countItemInInventory(ClientPlayerEntity player, Item item) {
        int total = 0;
        for (int i = 0; i < player.getInventory().size(); i++) {
            ItemStack stack = player.getInventory().getStack(i);
            if (stack.isOf(item)) total += stack.getCount();
        }
        return total;
    }

    private int furnaceGuiSlot(int rawSlot) {
        return rawSlot < 9 ? rawSlot + 30 : rawSlot - 6;
    }

    private void sendClick(MinecraftClient client, int slot, int button, SlotActionType action) {
        ClickSlotC2SPacket packet = new ClickSlotC2SPacket(
            syncId, client.player.currentScreenHandler.getRevision(),
            (short) slot, (byte) button, action,
            Int2ObjectMaps.emptyMap(), ItemStackHash.EMPTY);
        client.getNetworkHandler().sendPacket(packet);
        // Debug: log actual furnace slot contents
        var handler = client.player.currentScreenHandler;
        if (handler != null && handler.slots.size() > 2) {
            var inputStack = handler.slots.get(0).getStack();
            var fuelStack = handler.slots.get(1).getStack();
            LOG.info("  [DEBUG] furnace slot[0]={} x{} slot[1]={} x{}",
                inputStack.getItem(), inputStack.getCount(),
                fuelStack.getItem(), fuelStack.getCount());
        }
    }

    // Read actual item count from furnace slot (client-side view)
    private int readFurnaceSlotCount(MinecraftClient client, int furnaceSlot) {
        var handler = client.player.currentScreenHandler;
        if (handler != null && handler.slots.size() > furnaceSlot) {
            return handler.slots.get(furnaceSlot).getStack().getCount();
        }
        return -1;
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
        smeltItem = null; fuelItem = null;
        smeltQty = 0; fuelQty = 0; furnaceSlot = -1;
        smeltInvSlot = -1; fuelInvSlot = -1;
        furnacePos = null; placeGround = null;
        syncId = 0; waitTicks = 0;
        loadingSourceSlot = -1; loadingTargetFurnaceSlot = -1;
        loadingNeeded = 0; loadingStackSize = 0; loadingSplitTicks = 0;
    }

    private static void sendOk(MinecraftClient client, String msg) {
        if (client.player != null) {
            client.player.sendMessage(Text.literal("[RecipeCraft] " + msg), false);
        }
    }

    // ── CHECK ──

    private void stateCheck(MinecraftClient client) {
        ClientPlayerEntity player = client.player;
        releaseAllKeys(client);

        int smeltAvailable = countItemInInventory(player, smeltItem);
        LOG.info("CHECK: smeltItem={} needed={} available={}", smeltItem, smeltQty, smeltAvailable);
        if (smeltAvailable < smeltQty) {
            fail(client, "Not enough " + smeltItem.getName().getString()
                + ". Need " + smeltQty + ", have " + smeltAvailable + ".");
            return;
        }

        int fuelAvailable = countItemInInventory(player, fuelItem);
        LOG.info("CHECK: fuelItem={} needed={} available={}", fuelItem, fuelQty, fuelAvailable);
        if (fuelAvailable < fuelQty) {
            fail(client, "Not enough fuel (" + fuelItem.getName().getString()
                + "). Need " + fuelQty + ", have " + fuelAvailable + ".");
            return;
        }

        smeltInvSlot = findItemInInventory(player, smeltItem);
        fuelInvSlot = findItemInInventory(player, fuelItem);
        LOG.info("CHECK: smeltInvSlot={} fuelInvSlot={}", smeltInvSlot, fuelInvSlot);

        BlockPos playerPos = player.getBlockPos();
        for (int yOff = -1; yOff <= 1; yOff++) {
            for (int xOff = -2; xOff <= 2; xOff++) {
                for (int zOff = -2; zOff <= 2; zOff++) {
                    if (xOff == 0 && zOff == 0 && yOff == 0) continue;
                    BlockPos target = playerPos.add(xOff, yOff, zOff);
                    BlockPos ground = target.down();
                    BlockState groundState = client.world.getBlockState(ground);
                    BlockState targetState = client.world.getBlockState(target);
                    boolean blocked = isOccupied(player, target);
                    double dist = Math.sqrt(xOff*xOff + yOff*yOff + zOff*zOff);
                    if (groundState.isSolid() && targetState.isAir() && !blocked && dist <= 3.5) {
                        furnacePos = target;
                        placeGround = ground;
                        LOG.info("CHECK: selected furnacePos={} ground={}", furnacePos, placeGround);
                        advance(State.SWITCH_FURNACE);
                        return;
                    }
                }
            }
        }
        fail(client, "No suitable location to place furnace.");
    }

    // ── SWITCH / PLACE / OPEN (same as CraftingTableCrafter) ──

    private void stateSwitchFurnace(MinecraftClient client) {
        LOG.info("SWITCH_FURNACE: setting client selectedSlot={}", furnaceSlot);
        client.player.getInventory().selectedSlot = furnaceSlot;
        advance(State.WAIT_SWITCH);
    }

    private void stateWaitSwitch(MinecraftClient client) {
        if (++waitTicks >= 2) advance(State.LOOK_PLACE);
    }

    private void stateLookPlace(MinecraftClient client) {
        lookAt(client, placeGround);
        var hitResult = new BlockHitResult(
            new Vec3d(placeGround.getX() + 0.5, placeGround.getY() + 1.0, placeGround.getZ() + 0.5),
            Direction.UP, placeGround, false);
        client.interactionManager.interactBlock(client.player, Hand.MAIN_HAND, hitResult);
        LOG.info("LOOK_PLACE: interactBlock for ground {}", placeGround);
        advance(State.WAIT_PLACE);
    }

    private void stateWaitPlace(MinecraftClient client) {
        if (++waitTicks >= 4) {
            BlockState bs = client.world.getBlockState(furnacePos);
            LOG.info("WAIT_PLACE: block at {} = {}", furnacePos, bs.getBlock());
            if (bs.isAir()) { fail(client, "Failed to place furnace — position still air."); return; }
            if (!bs.isOf(Blocks.FURNACE)) { fail(client, "Blocked furnace placement (found " + bs.getBlock() + ")."); return; }
            LOG.info("WAIT_PLACE: furnace confirmed at {}", furnacePos);
            advance(State.WAIT_SERVER);
        }
    }

    // Double-verify furnace is server-confirmed (not just client-predicted)
    private void stateWaitServer(MinecraftClient client) {
        if (++waitTicks >= 6) {
            BlockState bs = client.world.getBlockState(furnacePos);
            if (!bs.isOf(Blocks.FURNACE)) {
                LOG.error("WAIT_SERVER: furnace disappeared — client prediction was wrong");
                fail(client, "Furnace placement was rejected by server.");
                return;
            }
            LOG.info("WAIT_SERVER: furnace server-confirmed after {} extra ticks", waitTicks);
            advance(State.LOOK_OPEN);
        }
    }

    private void stateLookOpen(MinecraftClient client) {
        lookAt(client, furnacePos);
        var hitResult = new BlockHitResult(furnacePos.toCenterPos(), Direction.UP, furnacePos, false);
        client.interactionManager.interactBlock(client.player, Hand.MAIN_HAND, hitResult);
        LOG.info("LOOK_OPEN: interactBlock for furnace {}", furnacePos);
        advance(State.WAIT_OPEN);
    }

    private void stateWaitOpen(MinecraftClient client) {
        if (++waitTicks >= 4) {
            syncId = client.player.currentScreenHandler.syncId;
            int invSyncId = client.player.playerScreenHandler.syncId;
            LOG.info("WAIT_OPEN: syncId={} invSyncId={}", syncId, invSyncId);
            if (syncId == invSyncId) { fail(client, "Failed to open furnace GUI."); return; }
            LOG.info("WAIT_OPEN: furnace GUI open, syncId={}", syncId);
            advance(State.LOAD_INPUT_GRAB);
        }
    }

    // ── Exact-amount loading: grab → drop N times → return extras ──

    // GRAB: pick up entire stack from source inventory slot
    private void stateLoadGrab(MinecraftClient client, int rawInvSlot, int furnaceSlot,
                                int needed, State dropState) {
        int guiSrc = furnaceGuiSlot(rawInvSlot);
        int stackSize = client.player.getInventory().getStack(rawInvSlot).getCount();
        LOG.info("GRAB: pick up stack rawSrc={} guiSrc={} stackSize={} needed={}",
            rawInvSlot, guiSrc, stackSize, needed);

        this.loadingSourceSlot = guiSrc;
        this.loadingTargetFurnaceSlot = furnaceSlot;
        this.loadingNeeded = needed;

        if (stackSize <= needed) {
            // Stack fits — just pick up and drop all, skip the per-item loop
            sendClick(client, guiSrc, 0, SlotActionType.PICKUP);
            this.loadingSplitTicks = 0; // signal: no splitting needed
            advance(dropState);
        } else {
            sendClick(client, guiSrc, 0, SlotActionType.PICKUP);
            this.loadingSplitTicks = 0;
            advance(dropState);
        }
    }

    // DROP: place 1 item per tick from cursor into furnace slot, N times
    private void stateLoadDrop(MinecraftClient client, int furnaceSlot, int rawSrcSlot,
                                State returnState, State skipReturn) {
        if (loadingSplitTicks == 0 && loadingSplitTicks == 0) { // not needed, skip comment
        }
        // Place 1 item from cursor into furnace
        sendClick(client, furnaceSlot, 1, SlotActionType.PICKUP);
        loadingSplitTicks++;
        LOG.info("DROP: {}/{} items placed in furnace slot {}", loadingSplitTicks, loadingNeeded, furnaceSlot);

        if (loadingSplitTicks >= loadingNeeded) {
            advance(returnState);
        }
        // else stay in DROP — continue placing one per tick
    }

    // RETURN: put any remaining cursor items back to source slot
    private void stateLoadReturn(MinecraftClient client, int rawSrcSlot, State next) {
        int guiSrc = furnaceGuiSlot(rawSrcSlot);
        sendClick(client, guiSrc, 0, SlotActionType.PICKUP);
        LOG.info("RETURN: returned leftovers to source slot (gui={})", guiSrc);
        advance(next);
    }

    // ── CLOSE / DONE ──

    private void stateClose(MinecraftClient client) {
        LOG.info("CLOSE_SCREEN: closing furnace GUI");
        client.player.closeHandledScreen();
        advance(State.DONE);
    }

    private void stateDone(MinecraftClient client) {
        LOG.info("DONE: smelting {}x {} with {}x {}",
            smeltQty, smeltItem.getName().getString(),
            fuelQty, fuelItem.getName().getString());
        sendOk(client, "Smelting " + smeltQty + "x " + smeltItem.getName().getString()
            + " with " + fuelQty + "x " + fuelItem.getName().getString() + ".");
        reset();
    }
}
