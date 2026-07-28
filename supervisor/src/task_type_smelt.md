### Blueprint for task type smelt

## Inputs

- Item(s) to smelt and quantity with optional fuel item to use(default is planks)

## Pre-checks

- The recipe mod already does all the checks, including fuel checks. Make sure any downstream errors are properly showed

## Execution loop

- Call recipe mod and perform the smelts. recipe-mod handles everything.
- Smelts are non blocking processes and the mod is only responsible for placing the furnace and placing items in it.
- Once the mod execution completes, one or more furnaces will be placed. 
- Each smelt task that is executed needs to be tracked. Use a custom smelt dataclass that stores itm, qty, fuel, smelt_time of each smelt task. smelt_time = 10s x itm qty.
- Wait for this smelting to complete = smelt_time. Once smelt_time passes and if smelting still not complete, poll every second to check completion
- For checking completion,rRefer file /home/swapnil/minecraft-planning/supervisor/controlbridge/test-requests/full-iron-pickaxe-flow.py. it checks if furnace is still burning fuel.

## Post-checks

- Ensure items with desired quantity are crafted. Otherwise, raise an error