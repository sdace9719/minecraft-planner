package com.recipecraft;

public interface BulkSmeltListener {
    void onItemComplete(int index, String itemName, int count);
    void onAllComplete();
    void onError(String message);
}
