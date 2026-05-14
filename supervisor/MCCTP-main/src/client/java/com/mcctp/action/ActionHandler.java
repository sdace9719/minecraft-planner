package com.mcctp.action;

import com.google.gson.JsonObject;

public interface ActionHandler {
    void handle(JsonObject params);
}
