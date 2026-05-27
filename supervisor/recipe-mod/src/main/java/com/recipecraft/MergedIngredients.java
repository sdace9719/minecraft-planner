package com.recipecraft;

import java.util.HashMap;
import java.util.Map;
import java.util.function.BiFunction;
import net.minecraft.client.network.ClientPlayerEntity;
import net.minecraft.item.Item;
import net.minecraft.registry.tag.TagKey;

/** Collects ingredient requirements across multiple recipes for bulk pre-checks. */
class MergedIngredients {
    final Map<Item, Integer> items = new HashMap<>();
    final Map<TagKey<Item>, Integer> tags = new HashMap<>();

    void addItem(Item item, int count) {
        items.merge(item, count, Integer::sum);
    }

    void addTag(TagKey<Item> tag, int count) {
        tags.merge(tag, count, Integer::sum);
    }

    String checkAgainstInventory(ClientPlayerEntity player,
                                  BiFunction<ClientPlayerEntity, Item, Integer> itemCounter,
                                  BiFunction<ClientPlayerEntity, TagKey<Item>, Integer> tagCounter) {
        for (var e : items.entrySet()) {
            int have = itemCounter.apply(player, e.getKey());
            if (have < e.getValue()) {
                return "Not enough " + e.getKey().getName().getString()
                    + ". Need " + e.getValue() + ", have " + have + ".";
            }
        }
        for (var e : tags.entrySet()) {
            int have = tagCounter.apply(player, e.getKey());
            if (have < e.getValue()) {
                return "Not enough items matching tag. Need " + e.getValue() + ", have " + have + ".";
            }
        }
        return null;
    }
}
