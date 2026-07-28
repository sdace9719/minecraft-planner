### Blueprint for pre-checks before proceeding with plan execution.

## Inputs

- None

## Pre-checks

- Check if any chests are nearby. if yes, then move atleast 100 blocks away from the chest.
- Set home waypoint to current location by calling appropriate baritone java functions

## Execution Loop

- None

## Post Checks

- Verify if final item qty  = desired_item_qty as per the planner prediction. If no, then raise a fatal error by specifying task failed even though task completed successfully, and exit the python client.

