package com.recipecraft;

public interface BulkCraftListener {
    void onItemComplete(int index, String itemName, int count);
    void onAllComplete();
    void onError(String message);
}
