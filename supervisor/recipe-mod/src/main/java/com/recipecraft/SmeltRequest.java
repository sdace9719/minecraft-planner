package com.recipecraft;

public record SmeltRequest(String itemName, int count, String fuelName) {
    public SmeltRequest(String itemName, int count) {
        this(itemName, count, "oak_planks");
    }
}
