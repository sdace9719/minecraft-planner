package com.mcctp.action.handlers;

import com.google.gson.JsonObject;
import com.mcctp.action.ActionHandler;
import com.mcctp.hud.HotbarWheelState;

/**
 * Updates the wheel highlight without changing the player's actual selected slot.
 * Used for live preview while the user is hovering over slots with gestures.
 */
public class HoverSlotHandler implements ActionHandler {
    @Override
    public void handle(JsonObject params) {
        int slot = params.has("slot") ? params.get("slot").getAsInt() : 0;
        if (slot < 0 || slot > 8) return;

        HotbarWheelState.setSelectedSlot(slot);
    }
}
