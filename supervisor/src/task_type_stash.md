### Blueprint for task type place

## Purpose

This only stashes items in a nearby chest

## Inputs

- None

## Pre-checks

- Check if a chest is nearby in the world(10 block radius). Fail if not present.
- Check if home waypoint is set in baritone. Fail if not present.
    - #wp list should show home waypoint with tag home. Fail if not present.
    - Call relevant baritone function directly, instead of executing chat commands
- record the length of global chest hash maps(coordinates map and items map). Create if not present.

## Execution loop

- Go to the home waypoint using baritone function call equivalent of:-
    - #wp set home
    - #path
    - Wait for exit code, Fail in case of failure returned by baritone function.
- After arriving at the destination, place a chest nearby.
    - Create a function that scans all air blocks near the feet of the player. Use logic from recipe-mod for block placement in valid areas.
- record its coordinates in the global chest hash map. Key will be chest name like "chest_1" and value will be an object. Each object will contain items in the chest and the x,y,z coordinates. The chests metadata must be maintained in another global hash map with key as chest name and value as dictionary of item names and value as qty.

## Post-checks

- Global chest hash map should have its length increased by 1. 
- coordinates hashmap should have valid coordinates for a newly created chest. item hash map should have valid items list by obeying stacking rules for a slot and not occupying more than maximum available slot in a chest.
- output failure in case of any of the conditions above fail.
- Otherwise, successful.