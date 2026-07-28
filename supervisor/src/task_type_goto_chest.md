### Blueprint for task type place

## Purpose

This only makes bot goto a specified chest to retrieve specific items.

## Inputs

- chest name
- items and their respective qty to be fetched

## Pre-checks

- retrieve coordinates from global hash map for the chest. Fail if not present
- Check if item exists in that chest from the relevant hash map. Fail if not present
- Check if required qty is present for that item in that chest, using the relevant hash map. Fail if not present.
- Check if enough space is in inventory for the given items by using inventory simulation class. Fail, in case of error.
- Record current qty of the items in the list as json.

## Execution loop

- record current x,y,z(x_initial,y_initial,z_initial)
- set goal to the waypoint using baritone java functions and wait for it to reach the location.
- While the bot travels, display % of path covered in the chat along x,y,z axis using:
    - X% = 100 - [(x_goal - x_current)/(x_goal - x_initial) * 100]
    - Y% = 100 - [(y_goal - y_current)/(y_goal - y_initial) * 100]
    - Z% = 100 - [(z_goal - z_current)/(z_goal - z_initial) * 100]
- For any reason, if baritone returns error, properly propogate it and fail the task.
- once reached successfully, open chest and put items into the inventory

## Post-checks

- Compare current inventory with the pre-check inventory json and delta for the items in questions should exactly match the qty requested for each item passed as input.