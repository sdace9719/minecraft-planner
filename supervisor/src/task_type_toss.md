### Blueprint for task type place

## Purpose

This only makes bot toss junk items safely so it cannot be picked up accidently.

## Inputs

- list of items to be tossed from the inventory and their respective quantity.

## Pre-checks

- check if all the items in the list are present.
- check if all the items have qty >= toss qty in the inventory.

## Execution loop

- Select a random location on the ground nearby in a radius of 5 blocks around the bot's feet. record this as BIN_BLOCK_TEMP
- Get the coordinates of the block which lies between the bot's feet and the selected block in previous step. record this as STAND_BLOCK_TEMP.
- go to the the STAND_BLOCK so that the bot is standing on the block using baritone java functions.
- mine a 2 block deep hole in the BIN_BLOCK_TEMP. look towards the mined hole and toss items in the list.
- Place 1 block so that it covers the hole from the top. this should make the tossed items in-accessible without mining the block used to cover it. use dirt of cobblestone for this.

## Post-checks

- Compare current inventory with the pre-check inventory json and delta for the items in questions should exactly match the qty requested for each item passed as input.