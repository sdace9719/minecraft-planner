### Blueprint for task type craft

## Inputs

- Item(s) to craft and quantity. can be a list of items.

## Pre-checks

- The recipe mod already does all the checks. Make sure any downstream errors are properly showed

## Execution loop

- Call recipe mod and perform the crafts. recipe-mod handles everything

## Post-checks

- Ensure items with desired quantity are crafted. Otherwise, raise an error