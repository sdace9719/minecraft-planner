package com.botinterface;

import baritone.api.BaritoneAPI;
import baritone.api.process.IMineProcess;
import net.minecraft.client.MinecraftClient;

public class BlockMiner {
    /**
     * Mine blocks of the specified type until count total items are obtained.
     * Non-blocking — returns immediately after issuing the command.
     *
     * @param client    MinecraftClient instance
     * @param blockName Block to mine, e.g. "spruce_log"
     * @param count     Total number of items to obtain (not "additional"). If you
     *                  already have 5 and pass 8, Baritone mines 3 more.
     * @return true if the mining process was started successfully
     */
    public static boolean mineByName(MinecraftClient client, String blockName, int count) {
        if (client.player == null) return false;
        client.execute(() -> {
            try {
                IMineProcess mine = BaritoneAPI.getProvider().getPrimaryBaritone().getMineProcess();
                mine.mineByName(count, blockName);
                BotInterfaceMod.LOGGER.info("Started mining {}x {}", count, blockName);
            } catch (Exception e) {
                BotInterfaceMod.LOGGER.error("Failed to start mining {}", blockName, e);
            }
        });
        return true;
    }

    public static void cancel() {
        BaritoneAPI.getProvider().getPrimaryBaritone().getMineProcess().cancel();
    }

    public static boolean isActive() {
        try {
            return BaritoneAPI.getProvider().getPrimaryBaritone().getMineProcess().isActive();
        } catch (Exception e) {
            return false;
        }
    }
}
