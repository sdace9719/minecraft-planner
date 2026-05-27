#!/usr/bin/env python3
"""Test: Craft an iron pickaxe from raw materials via ControlBridge API.

Requires in Minecraft: oak logs (-> planks), raw_iron, coal,
 crafting table in hotbar, furnace in hotbar.
"""

import json
import sys
import urllib.request
import urllib.error

HOST = "http://localhost:8765"


def post(endpoint: str, data: dict) -> dict:
    url = f"{HOST}{endpoint}"
    body = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return {"status": "error", "http_code": e.code, "message": e.read().decode()}
    except urllib.error.URLError as e:
        print(f"Connection failed — is Minecraft running? ({e.reason})", file=sys.stderr)
        sys.exit(1)


def step(n: int, desc: str, endpoint: str, data: dict):
    print(f"\n=== Step {n}: {desc} ===")
    result = post(endpoint, data)
    print(json.dumps(result, indent=2))
    if result.get("status") != "ok":
        print(f"FAILED: {result.get('message', 'unknown error')}", file=sys.stderr)
        sys.exit(1)


def main():
    # Step 1: Craft planks and sticks
    step(1, "Craft oak planks (12) and sticks (8)",
         "/bulk/craft", {
             "requests": [
                 {"item": "oak_planks", "count": 12},
                 {"item": "stick", "count": 8},
             ]
         })

    # Step 2: Smelt raw iron into ingots
    step(2, "Smelt raw_iron into iron ingots (3)",
         "/bulk/smelt", {
             "requests": [
                 {"item": "raw_iron", "count": 3, "fuel": "coal"},
             ]
         })

    # Step 3: Craft the iron pickaxe
    step(3, "Craft iron pickaxe (1)",
         "/bulk/craft", {
             "requests": [
                 {"item": "iron_pickaxe", "count": 1},
             ]
         })

    print("\n=== Done! Iron pickaxe should be in inventory after crafting completes. ===")


if __name__ == "__main__":
    main()
