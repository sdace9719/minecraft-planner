package com.botinterface.mixin;

import net.minecraft.client.network.ClientPlayNetworkHandler;
import net.minecraft.network.packet.s2c.play.InventoryS2CPacket;
import net.minecraft.network.packet.s2c.play.ScreenHandlerSlotUpdateS2CPacket;
import net.minecraft.network.packet.s2c.play.SetPlayerInventoryS2CPacket;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

@Mixin(ClientPlayNetworkHandler.class)
public class DebugNetworkMixin {
    private static final Logger LOG = LoggerFactory.getLogger("BotInterface-Debug");

    @Inject(method = "onInventory", at = @At("HEAD"))
    private void onInventoryReset(InventoryS2CPacket packet, CallbackInfo ci) {
        LOG.error("[DEBUG] <<< INVENTORY RESET  syncId={} rev={} stacks={}",
            packet.syncId(), packet.revision(), packet.contents().size());
    }

    @Inject(method = "onScreenHandlerSlotUpdate", at = @At("HEAD"))
    private void onSlotUpdate(ScreenHandlerSlotUpdateS2CPacket packet, CallbackInfo ci) {
        if (packet.getSyncId() == 0) {
            LOG.error("[DEBUG] <<< SLOT UPDATE  syncId={} slot={} stack={} x{} rev={}",
                packet.getSyncId(), packet.getSlot(),
                packet.getStack().getItem().getName().getString(),
                packet.getStack().getCount(), packet.getRevision());
        }
    }

    @Inject(method = "onSetPlayerInventory", at = @At("HEAD"))
    private void onPlayerInvUpdate(SetPlayerInventoryS2CPacket packet, CallbackInfo ci) {
        LOG.error("[DEBUG] <<< PLAYER INV UPDATE  slot={} stack={} x{}",
            packet.slot(), packet.contents().getItem().getName().getString(),
            packet.contents().getCount());
    }
}
