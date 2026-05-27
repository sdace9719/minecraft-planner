package com.botinterface;

import baritone.api.BaritoneAPI;
import baritone.api.pathing.goals.GoalBlock;
import net.minecraft.block.BlockState;
import net.minecraft.client.MinecraftClient;
import net.minecraft.util.math.BlockPos;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/** Walk to and collect a placed block via Baritone API (handles pathfinding + breaking). */
public class BlockCollector {
    private static final Logger LOG = LoggerFactory.getLogger("BotInterface-Collector");
    private static final int TIMEOUT_TICKS = 300; // 15 seconds

    public static boolean gotoAndBreak(MinecraftClient client, int x, int y, int z) {
        if (client.player == null) {
            LOG.warn("gotoAndBreak: not in game");
            return false;
        }

        BlockPos target = new BlockPos(x, y, z);
        BlockState state = client.world.getBlockState(target);
        if (state.isAir()) {
            LOG.info("gotoAndBreak: block already air at ({},{},{})", x, y, z);
            return true;
        }
        LOG.info("gotoAndBreak: {} at ({},{},{})", state.getBlock(), x, y, z);

        try {
            var baritone = BaritoneAPI.getProvider().getPrimaryBaritone();
            baritone.getCustomGoalProcess().setGoalAndPath(new GoalBlock(x, y, z));
            LOG.info("gotoAndBreak: Baritone goal set to ({},{},{})", x, y, z);
        } catch (Exception e) {
            LOG.error("gotoAndBreak: Baritone API failed", e);
            return false;
        }

        // Wait for Baritone to pathfind, break, and collect the block
        for (int i = 0; i < TIMEOUT_TICKS; i++) {
            try { Thread.sleep(50); } catch (InterruptedException e) { Thread.currentThread().interrupt(); return false; }
            if (client.world.getBlockState(target).isAir()) {
                LOG.info("gotoAndBreak: block collected after {} ticks", i);
                return true;
            }
        }
        LOG.warn("gotoAndBreak: timeout at ({},{},{})", x, y, z);
        return false;
    }
}
