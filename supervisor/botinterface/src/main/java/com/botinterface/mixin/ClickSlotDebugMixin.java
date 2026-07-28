package com.botinterface.mixin;

import net.minecraft.client.network.ClientPlayerInteractionManager;
import net.minecraft.entity.player.PlayerEntity;
import net.minecraft.screen.slot.SlotActionType;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

@Mixin(ClientPlayerInteractionManager.class)
public class ClickSlotDebugMixin {
    private static final Logger LOG = LoggerFactory.getLogger("BotInterface-Debug");

    @Inject(method = "clickSlot", at = @At("HEAD"))
    private void onEnter(int syncId, int slotId, int button,
                          SlotActionType actionType, PlayerEntity player,
                          CallbackInfo ci) {
        var csh = player.currentScreenHandler;
        // Print call stack to find who's calling clickSlot
        StackTraceElement[] stack = Thread.currentThread().getStackTrace();
        StringBuilder sb = new StringBuilder();
        for (int i = 2; i < Math.min(stack.length, 12); i++) {
            sb.append("\n    ").append(stack[i].getClassName())
              .append(".").append(stack[i].getMethodName())
              .append(":").append(stack[i].getLineNumber());
        }
        LOG.error("[DEBUG] >>> clickSlot ENTER  syncId={} slot={} button={} action={}  " +
                  "currentSH={} currentSH.syncId={}  CALLERS={}",
            syncId, slotId, button, actionType,
            csh != null ? csh.getClass().getSimpleName() : "NULL",
            csh != null ? csh.syncId : -1,
            sb.toString());
    }

    @Inject(method = "clickSlot", at = @At("RETURN"))
    private void onReturn(int syncId, int slotId, int button,
                           SlotActionType actionType, PlayerEntity player,
                           CallbackInfo ci) {
        var csh = player.currentScreenHandler;
        LOG.error("[DEBUG] >>> clickSlot RETURN  syncId={} slot={} button={} action={}  " +
                  "currentSH={} rev={}",
            syncId, slotId, button, actionType,
            csh != null ? csh.getClass().getSimpleName() : "NULL",
            csh != null ? csh.getRevision() : -1);
    }
}
