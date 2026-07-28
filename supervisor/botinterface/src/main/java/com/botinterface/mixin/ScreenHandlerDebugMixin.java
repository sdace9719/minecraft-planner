package com.botinterface.mixin;

import net.minecraft.entity.player.PlayerEntity;
import net.minecraft.item.ItemStack;
import net.minecraft.screen.ScreenHandler;
import net.minecraft.screen.slot.SlotActionType;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;

@Mixin(ScreenHandler.class)
public class ScreenHandlerDebugMixin {
    private static final Logger LOG = LoggerFactory.getLogger("BotInterface-Debug");

    @Inject(method = "onSlotClick", at = @At("HEAD"), cancellable = true)
    private void onSlotClickHead(int slotIndex, int button, SlotActionType actionType,
                                  PlayerEntity player, CallbackInfo ci) {
        if (actionType == SlotActionType.SWAP) {
            ScreenHandler self = (ScreenHandler) (Object) this;
            ItemStack slotStack = self.getSlot(slotIndex).getStack();
            LOG.warn("[DEBUG] onSlotClick ENTER  slot={} button={} action={}  " +
                      "slotStack={} x{}  size={}  cursor={} x{}",
                slotIndex, button, actionType,
                slotStack.getItem().getName().getString(), slotStack.getCount(),
                self.slots.size(),
                self.getCursorStack().getItem().getName().getString(),
                self.getCursorStack().getCount());
        }
    }
}
