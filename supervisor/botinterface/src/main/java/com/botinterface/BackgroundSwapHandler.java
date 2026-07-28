package com.botinterface;

import baritone.api.BaritoneAPI;
import net.minecraft.client.MinecraftClient;
import net.minecraft.screen.slot.SlotActionType;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.concurrent.ConcurrentLinkedQueue;

public class BackgroundSwapHandler {
    private static final Logger LOG = LoggerFactory.getLogger("BotInterface-BackgroundSwap");
    private static final ConcurrentLinkedQueue<SwapTask> taskQueue = new ConcurrentLinkedQueue<>();

    public static class SwapTask {
        public final int sourceSlot;
        public final int destinationHotbar;

        public SwapTask(int source, int destination) {
            this.sourceSlot = source;
            this.destinationHotbar = destination;
        }
    }

    public static void queueBackgroundSwap(int sourceSlot, int destinationHotbar) {
        if (sourceSlot < 9 || sourceSlot > 35 || destinationHotbar < 0 || destinationHotbar > 8) {
            LOG.warn("[BGS] Out of bounds: src={} hotbar={}", sourceSlot, destinationHotbar);
            return;
        }
        LOG.info("[BGS] QUEUE   src={} hotbar={}", sourceSlot, destinationHotbar);
        taskQueue.add(new SwapTask(sourceSlot, destinationHotbar));
    }

    public static void processTick(MinecraftClient client) {
        if (client.player == null) return;

        SwapTask task = taskQueue.poll();
        if (task == null) return;

        executeAtomicSwap(client, task);
    }

    private static void executeAtomicSwap(MinecraftClient client, SwapTask task) {
        int syncId = client.player.playerScreenHandler.syncId;

        LOG.info("[BGS] SWAP    src[{}] ↔ hot[{}]  syncId={}",
            task.sourceSlot, task.destinationHotbar, syncId);

        BaritoneAPI.getProvider().getPrimaryBaritone().getPlayerContext()
            .playerController().windowClick(
                syncId,
                task.sourceSlot,
                task.destinationHotbar,
                SlotActionType.SWAP,
                client.player
            );

        LOG.info("[BGS] DONE    Baritone windowClick dispatched");
    }
}
