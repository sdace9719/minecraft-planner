package com.mcctp.action.handlers;

import com.google.gson.JsonObject;
import com.mcctp.action.ActionHandler;
import com.mcctp.hud.HotbarWheelState;

public class ToggleWheelHandler implements ActionHandler {
    @Override
    public void handle(JsonObject params) {
        HotbarWheelState.toggle();
    }
}
