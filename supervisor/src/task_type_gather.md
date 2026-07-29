### Blueprint for task type mine

## Inputs

- Item name and quantity.

## Pre-checks

- Check if the item can be insta mined by hand by looking up the item in constants/material_harvest.json
- in case a tool is required, check if the required tool is present in inventory. In case of tool missing, throw an error.
- If the required tool exists, check if it has enough tool durability. This means sum of expected junk blocks to mine + target block to mine should be smaller than tool durability. use ore-data.json to estimate junk block(if any). In case it exists but lacks required durability, execute the task with the same tool and once it breaks, re-queue the task again. This will re-trigger all the checks and should trigger creation of the tool.
- There will be a function for each possible input item. The function will return the x and z coordinates to travel to to get the first instance of the item. Let's call this item_locater

## Execution Loop

- Calculate amount left to gather = current qty in inventory - input qty
- Execute baritone "#mine minecraft_item" command by calling the relevant endpoint on the controlbridge with try catch. Listen particularly for tool break event. The server's swagger doc should mention the relevant endpoint. This endpoint documentation should return this event as possible error, among others. when tool breaks, re-queue the task and set input qty as current-qty - expected_qty in inventory.
- Sometimes, the minecraft_item needs to be correct and needs consideration, in order to execute properly. For example, if we need to mine cobblestone, we should instead issue "#mine minecraft_stone" because mining stone without silk touch drops cobblestone anyway. Otherwise, it will hunt for cobblestone that generates naturally and depending on the biome, this command may fail altogether. Here is the  exhaustive list of mappings to remember.
    - Item to mine -> minecraft_item string name
    - cobblestone -> stone
    - Cobbled_Deepslate -> deepslate
- If command fails because it cannot find more items nearby, then re-execute the item_locater function to get fresh remote x and z coordintates. Then issue bariton command '#goto x z' and re-execute this loop from starting
- When the baritone command finishes without any errors, execute post checks

## Post Checks

- Verify if final item qty  = desired_item_qty as per the planner prediction. If no, then raise a fatal error by specifying task failed even though task completed successfully, and exit the python client.

