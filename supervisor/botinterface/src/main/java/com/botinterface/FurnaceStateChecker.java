package com.botinterface;

import net.minecraft.block.Blocks;
import net.minecraft.client.MinecraftClient;
import net.minecraft.state.property.Properties;
import net.minecraft.util.math.BlockPos;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/** Check if a furnace at given coordinates is actively burning fuel. */
public class FurnaceStateChecker {
    private static final Logger LOG = LoggerFactory.getLogger("BotInterface-Furnace");

    public static boolean isBurning(MinecraftClient client, int x, int y, int z) {
        if (client.world == null) { LOG.warn("isBurning: not in world"); return false; }
        BlockPos pos = new BlockPos(x, y, z);
        if (!client.world.isChunkLoaded(pos)) {
            LOG.warn("isBurning: chunk not loaded at ({},{},{})", x, y, z);
            return false;
        }
        var state = client.world.getBlockState(pos);
        if (!state.isOf(Blocks.FURNACE)) {
            LOG.info("isBurning: ({},{},{}) is {}, not furnace", x, y, z, state.getBlock());
            return false;
        }
        boolean lit = state.contains(Properties.LIT) && state.get(Properties.LIT);
        LOG.info("isBurning: furnace at ({},{},{}) lit={}", x, y, z, lit);
        return lit;
    }
}
