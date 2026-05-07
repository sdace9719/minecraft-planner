Here is the optimized, production-ready version of your architecture document. I have retained every single detail, calculation, and constraint you provided, but restructured them into strict Input/Output Contracts.

This format eliminates ambiguity and forces the AI to execute the exact sequence required to prevent graph corruption (specifically, calculating ROI and Slicing before Kahn's sorting).

You can copy and paste this directly into Cursor.
Minecraft AI Planner: Modular Compiler Architecture

We are rebuilding the planner logic in a strict, modular compiler pipeline. Create a directory called planner/ and place all files there. We will execute this step-by-step in phases. Do not proceed to the next phase until you receive my explicit approval.

General Guidelines

    Refer to project-standards.mdc and follow it strictly.

    ABSOLUTE RULE: No fallbacks or silent error catch-and-continue mechanisms. If a physical law of Minecraft is broken, raise an explicit exception and fail the code. Any fallback code you wish to implement requires my explicit approval and a detailed explanation of its behavior.

Phase 1: Pre-requisites (Static Blueprint Generation)

Generate all one-time static files.

    Full Item List: Generate a full list of Minecraft items for the given version.

    Task Queue Blueprints: Use this list to generate a generic, pre-computed linear task queue for each item, assuming it is the only item to be collected. No optimizations or quantity tracking here. Assume stone tools.

        Algorithm: For each item, check its recipe (crafting/smelting). If it has no recipe, it must be mined; use material_harvest.json to identify the required tool.

        Use a recursive Depth-First Search (DFS). Example: diamond_pickaxe -> looks up recipe (3 diamonds, 2 sticks) -> recurses into diamond (requires mining ore) -> checks blocks.json (requires Iron Pickaxe) -> recurses into iron_pickaxe.

        As the DFS bottoms out (hits base materials like wood or bare-hand mining), append the steps to an array. Stop from the deepest item up to the target item.

    Wait for Approval: I will provide a junk block creation file based on your item list.

    Byproduct Injection: Once provided, populate all mining tasks across all blueprints with the expected byproduct volume per instance mined.

Phase 2: Item Task Generator (planner/item_task_generator.py)

Implement a Task class with attributes: id, name, quantity, dependencies (array of IDs), and operation_type.

    Function 1 (Single Item): Accepts an item and quantity. Looks up the pre-computed blueprint.

        ID Generation: Hash operation + item (e.g., MINE+redstone) to generate unique, fixed IDs for each task type.

        Dependency Wiring: Record all immediate dependencies as an array of IDs (e.g., iron_pickaxe requires IDs for sticks, iron ingot, crafting table = length 3 array).

        Quantity & Durability Math: Calculate the exact quantity required for all sub-items, including tool durability math to find the total number of tools required.

        Circular Dependency Check: Prevent logic loops (e.g., crafting stone axe needs sticks -> logs -> requires stone axe). Use hand initially if plausible. If an unresolvable circular dependency is found, raise an explicit error.

    Function 2 (Global Target): Accepts the entire user request item list, iterates through Function 1, combines the resulting queues, and returns them as-is. No optimization.

Phase 3: The Combiner (planner/combiner.py)

    Input: The list of item task queues from Phase 2.

    Logic: Combine all common tasks using their hashed IDs. If two targets both require an Iron Pickaxe, merge them. Keep exactly one instance of the recurring task and sum the quantity.

    Output: A merged graph with zero duplicate tasks. No ordering yet.

Phase 4: Local Optimizer (Tool ROI & Slicing) (planner/local_optimizer.py)

    Step 1: ROI Tool Optimization

        For each tool family (pickaxe, axe, shovel, hoe), compute total workload volume (quantity * hardness). Refer to block_hardness.json.

        For each candidate tier (stone, iron, diamond) satisfying min-tier constraints, compute: total_time = workload_time + chain_time + exploration_time.

        Math: expected_veins = ceil(required_ore_qty / vein_size). junk_blocks = blocks_to_break * expected_veins. Convert junk blocks to time via hardness/speed. Copy count = ceil(required_volume / durability).

        Expose the full breakdown in an ROI report. If a higher tier is faster, swap the tasks. Keep lower-tier tool tasks if they are required to obtain the higher-tier tools.

    Step 2: Slicing / Interleaving

        For all mining tasks that require tools, split the massive node based on tool durability.

        Rule: Ensure all input materials (ingots/sticks) for the total expected tools are gathered upfront. But the execution must be interleaved: craft 1 pick, mine until it breaks, craft the next pick, repeat.

Phase 5: Global Optimizer & Sorter (planner/global_optimizer.py)

Execute a Kahn's Algorithm topological sort combined with dynamic inventory priority.

    The Loop: Create a new_queue. Iterate until the old graph is fully scanned.

        Tasks with 0 dependencies (in-degree) are eligible.

        Once added to new_queue, scan the old queue and remove the added task's ID from any dependent tasks' arrays, decreasing their in-degrees.

    Optimization Sort (Inside the Loop):

        Inventory Pressure: Tasks crafted with a high number of inputs (e.g., reduces inventory load) go earlier.

        Useful Junk: Tasks that generate usable junk for downstream tasks get priority.

        Toss Unused: After each task, calculate what junk can be tossed. Check the rest of the queue; if the byproduct (e.g., deepslate) is needed later, keep it.

Phase 6: Final Checker & Cache Simulator (planner/final_checker.py)

    Cache Lookahead: Simulate walking through the sorted queue tracking inventory space. The moment 30 / 36 slots are occupied, trigger chest creation. Check the next N=4 smelting/crafting tasks. Toss items not immediately required into the chest and continue.

    Final Simulation: Run a full, strict inventory simulation to verify the tasks are physically achievable in order.

    Output: 1. If failed: Exit specifying the exact failure reason.
    2. In both success and failure: Generate the inventory simulation as a 2D array for each task.
    3. Visualizer: Generate a linear .mmd (Mermaid) flowchart from the final generated queue.