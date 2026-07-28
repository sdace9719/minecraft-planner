#### Supervisor state machine implementation

### Components

## Task Executor

- Task types: gather, craft, smelt, mine, place, stash. go_to_chest, toss.

- For each task type, there will be a function that executes the given task type.
- Each function will accept input arguments, perform pre-checks, execute the task and perform post-check
- pre-checks should check if all conditions to execute the items match. There can be various items missing. For each item missing, it will execute a emergency routine to collect that item by injecting a brand new sub plan from planner. In this case, it will send only the missing items to the planner and generate the plan for that. 
- Then it will execute this sub plan to get the items and then continue with the task.
- After that it will execute post-checks. It will check if the task was performed successfully. This it will do this by comparing the items in the inventory with the plan inventory. It will check, for the items involved in the task, if the total quantity in the inventory >= item quantity in planner inventory.
- If the task failed, re-queue the task and perform post-checks again