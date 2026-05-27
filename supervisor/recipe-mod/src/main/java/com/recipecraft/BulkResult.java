package com.recipecraft;

import java.util.Collections;
import java.util.List;

/** Result from bulkCraft/bulkSmelt pre-checks. */
public class BulkResult {
    private final boolean success;
    private final String error;
    private final int totalBatches;
    private final List<String> positions; // "x,y,z" strings for placed blocks

    private BulkResult(boolean success, String error, int totalBatches, List<String> positions) {
        this.success = success;
        this.error = error;
        this.totalBatches = totalBatches;
        this.positions = positions != null ? positions : Collections.emptyList();
    }

    public static BulkResult ok(int totalBatches) {
        return new BulkResult(true, null, totalBatches, Collections.emptyList());
    }

    public static BulkResult ok(int totalBatches, List<String> positions) {
        return new BulkResult(true, null, totalBatches, positions);
    }

    public static BulkResult fail(String error) {
        return new BulkResult(false, error, 0, Collections.emptyList());
    }

    public boolean success() { return success; }
    public String error() { return error; }
    public int totalBatches() { return totalBatches; }
    public List<String> positions() { return positions; }
}
