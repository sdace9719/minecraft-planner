package com.controlbridge;

/** Minimal JSON utilities — no external dependencies. */
public class JsonUtil {
    public static String escape(String s) {
        if (s == null) return "null";
        StringBuilder sb = new StringBuilder(s.length() + 4);
        sb.append('"');
        for (int i = 0; i < s.length(); i++) {
            char c = s.charAt(i);
            switch (c) {
                case '"' -> sb.append("\\\"");
                case '\\' -> sb.append("\\\\");
                case '\n' -> sb.append("\\n");
                case '\r' -> sb.append("\\r");
                case '\t' -> sb.append("\\t");
                default -> sb.append(c);
            }
        }
        sb.append('"');
        return sb.toString();
    }

    public static String obj(String... keyValuePairs) {
        StringBuilder sb = new StringBuilder("{");
        for (int i = 0; i < keyValuePairs.length; i += 2) {
            if (i > 0) sb.append(',');
            sb.append(escape(keyValuePairs[i])).append(':').append(keyValuePairs[i + 1]);
        }
        sb.append('}');
        return sb.toString();
    }

    public static String arr(String... values) {
        StringBuilder sb = new StringBuilder("[");
        for (int i = 0; i < values.length; i++) {
            if (i > 0) sb.append(',');
            sb.append(values[i]);
        }
        sb.append(']');
        return sb.toString();
    }

    public static String num(int n) { return String.valueOf(n); }
    public static String str(String s) { return escape(s); }
    public static String bool(boolean b) { return b ? "true" : "false"; }

    /** Simple JSON value extraction from flat objects. */
    public static String getString(String json, String key) {
        String search = "\"" + key + "\"";
        int i = json.indexOf(search);
        if (i < 0) return null;
        i = json.indexOf(':', i + search.length());
        if (i < 0) return null;
        i++;
        while (i < json.length() && Character.isWhitespace(json.charAt(i))) i++;
        // If value isn't a quoted string, return null
        if (i >= json.length() || json.charAt(i) != '"') return null;
        int j = json.indexOf('"', i + 1);
        if (j < 0) return null;
        return json.substring(i + 1, j);
    }

    public static Integer getInt(String json, String key) {
        String search = "\"" + key + "\"";
        int i = json.indexOf(search);
        if (i < 0) return null;
        i = json.indexOf(':', i + search.length());
        if (i < 0) return null;
        i++;
        while (i < json.length() && Character.isWhitespace(json.charAt(i))) i++;
        // Unquoted number
        if (i < json.length() && json.charAt(i) != '"') {
            int j = i;
            while (j < json.length() && (Character.isDigit(json.charAt(j)) || json.charAt(j) == '-')) j++;
            if (j == i) return null;
            return Integer.parseInt(json.substring(i, j));
        }
        // Quoted string — parse as int
        String s = getString(json, key);
        if (s != null) {
            try { return Integer.parseInt(s); } catch (NumberFormatException e) { return null; }
        }
        return null;
    }
}
