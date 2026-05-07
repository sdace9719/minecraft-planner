 we will go step by step and re-create the planner logic in a structured wat. first break the planner into multiple sub files. create a directory called planner and put all files there. The files should be like this:-

item task generator: the generator should have two functions. one functions to accept the entire item list and the second function where we will pass each item iteratively from the list and generate the linear task queue for the item. We should pre-compute task list for all possible items in minecraft beforehand and use it as a lookup to return the queue corresponding the item in question. when generating the one time pre-computed task list, use hashing to generate the ids. it should hash "operation+item" to get the id for the task. hence each operation + item combination produces a unique task with a corresponding id obtained from its hash. for each task in the task queue, record all immediate dependencies as an array. the array will hold the id of the immediate dependent tasks. gor example mining redstone requires iron pick. so one dependency. iron pick requires sticks, iron ingot and crafting table, so 3 dependencies and hence 3 length array with respective ids. now sticks, ingots and crafting table have their own dependencies so the corresponding tasks will have array dependencies contructed accordingly.
for each item, we pre-compute the task queue assuming that is the only item to be mined, for all items in the game. which means, from scratch what exact tasks(in order) to be executed to get the item. For generating item dependencies, refer to the existing planner logic in planner.py on how was this done dynamically and re-purpose it for the current use case.
it will be useful to generate the full list of all possible items in the game. which we can iterate on to generate tasks queue for each item. Also, we need to add any possible junk items collected during the process of acquiring those items. During blueprint generation pre-requisites phase, we will mark mining tasks with the byproduct name(like deepslate for redstone mining). We will also mention estimated junk produced per ore mined. This will allow ius to calculate actual byproduct quantity in this phase when we use the blueprints. I will give the list that to you but i need the full list of all possible items first. do not proceed before the pre-requisites are met. the prec-omputed task list for each item serves only as the blueprint. No quantities are involved there. but here, we will recieve quanitity for the target item and we must calculate quantity for each item involved to get the target item, including calculations like tool durability needed to calculate number of tools required for the task.
the first function then just combines the task queue for each and returns as is. no optimizations here. 
There may be cases where circular dependencies are created. For example, to create stone axe, we need sticks which come from logs. but as per our above logic, logs should be cut down using stone axe itself. To avoid this, use hand initially if plausible. We need to add checks for such circular dependencies and raise explicit errors and fail the code. no fallbacks and no silent error catch-and-continue. All optimizations we will do in next phases.

Combiner: This takes the list of item task queues and first combines all common tasks. For example, both gold and redstone require iron pickaxe. so they will have all tasks till iron pick common. we do this for all tasks in the task queue. Once done, we will remove the repeated occuring of each of the recurring tasks, like crafting the pick for each required item to be mined and just keep one with the added amount. we have not done any ordering yet.

 
local optimizer and sorter: the optimizer takes in the combined graph and runs the following checks/calculations:-
    - durability checks and tool optimization using roi calculations. 
        For each tool family (pickaxe, axe, shovel, hoe), compute total workload volume from all relevant gather tasks (quantity × hardness). refer to block_hardness.json for hardness values.
        For each candidate tier (stone, iron, diamond) that satisfies min-tier constraints, compute total time:
        workload_time: time to break required blocks with that tier’s speed.
        chain_time: time to obtain/craft required tool chain and required copies.
        exploration_time (for ore-gated tiers): scaled ore-search penalty using tools.json:
        expected_veins = ceil(required_ore_qty / vein_size)
        junk_blocks = blocks_to_break * expected_veins
        convert junk block breaking into time via hardness + mining speed.
        Include durability in copy count:
        tool_copies = ceil(required_volume / durability) (plus strict convergence correction via simulation if needed).
        Select the tier with minimum total_time = workload_time + chain_time + exploration_time.
        Expose full candidate breakdown in ROI report (so selected tier is auditable).
        if roi says better to use next tier tool, we remove the tasks related related to lower tier and add the higher tier ones. Note that this may still need lower tier tooles to get the higher tier tools. for all roi calculations, refer to the planner.py logic.
    - for all mining related tasks that use tools to gather tools, such as sand logs, redstone, etc. we need to split the task node. Instead of crafting say 20 picks before the mining task, interleave the task so that we create one pick and mine with it till it breaks, then re-craft another and do the same, until we have the required amount of the item. This requires durability calculation. Note that we still require all input materials for total expected number of tools to be present before the mining tasks. so for 20 expected picks, we should already have required ingots and sticks but we will only craft one at a time.
    - create a brand new queue and iteratively do the following until the old queue is fully scanned
        - check count of dependencies(array length) for each item. only tasks with 0 dependencies are eligible to be added in the queue.
        - Once the tasks are added, scan the old queue, mark the added tasks as included.
        - Now for the items added in new queue, check in old queue on what tasks they are marked as dependent. if one or more tasks are present in the old queue that have some dependencies already added in new queue, we remove the dependencies from their array in old queue. this will decrease their in-degrees as per kahn's algorithm.
        - Within each iteration we do optimzation sort:-
            - items that are crafted with high number of input materials(quantity), then we should put them earlier so that inventory pressure is minimized.
        - do this loop again and continue until all items are added in new queue 

Global optimizer and sorter: Should perform the following:-
    - inventory pressure: perform the following actions:- 
        - iterate through every task and if after that task, we can craft items that reduces inventory load by taking more items in and outputting fewer items out, such as crafting TNT and smelting ores(uses up fuel items), then we should put them after that task rather than much later in the queue. Any tasks that generate usable junk for other tasks should be given the priority.
        - after each task check what junk items can be tossed that are not needed in rest of the tasks in the queue. check the rest of the task queue to see if the junk/byproduct is useful anywhere. if yes, then we need to keep it. So for example mining diamonds produce a lot of deepslate so if we need it anywhere later, we should not re-mine deepslate. each mining task already specifies the junk produced in phase 1 based on required quantity.
        - the moment 30/36 slots are occupied, create a chest, toss the items not immediately required into it and continue. We whould check next N=4 smelting/crafting tasks to decide this.

Final checker: do a full inventory simulation run to see if tasks are achievable in the given order and follows the laws of minecraft. In case of failure, exit specifying the failure reason. do not implement fallback or silently ignore it. In both failure and success, generate the inventory simulation as 2d array for each task in the queue.

Visualizer: generate linear mmd flowchart from the final generated linear queue task list.


## Implementation plan

We will do this in phases. After phase, you neeed to wait for my approval.

# Phase 1(pre-requisites)

Generate all pre-requisite one time static files. this includes:-
- full item list of minecraft for given version.
- Use this list to generate task queue list for that particular item, assuming only that item to be collected. no optimizations. only required and correct order of tasks needed to get the item. Assume stone stools. no quantity tracking. only generic blueprint. use the following algorithm:-
    - for each item in the list, check its recipe(crafting/smelting). 
    - if doesn't have a recipe, it must be mined with a tool. use material_harvest.json to identofy the required tool.
    - Use recursive Depth-First Search (DFS) function. for example, for diamond_pickaxe.

    It looks up the recipe: requires 3 diamonds, 2 sticks.

    It recurses into diamond: requires mining diamond ore.

    It checks blocks.json for diamond ore: requires Iron Pickaxe.

    It recurses into iron_pickaxe.

    As the recursive function bottoms out (hits base materials like wood or bare-hand mining), it appends the steps to an array. Now when generating the task blueprint for it, it should stop from deepest item like bare-hand mining tasks till the item in question.
- Wait for my junk block creation file which i will generate based on item list.
- Then populate all mining tasks across all item lists with expected byproduct volume per instance of item mined

# Phase 2

Implement the task generator. Use a task class with proper attributes like id, name, quantity, dependencies, operation type, etc.

# Phase 3

Implement the combiner

# Phase 4

implement the local optimizer.

# Phase 5 

Implement the global optimizer.

# Phase 6

Implement the final checker.

## General guidelines

refer to project-standards.mdc. and follow it to the letter. In addition:-
- Any fallback code you come across or wish to implement, it needs my approval to continue. Explain the behaviour in detail to me in that case.






