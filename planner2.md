# Minecraft AI Planner: Modular Compiler Architecture

We are rebuilding the planner logic in a strict, modular compiler pipeline. Create a directory called `planner/` and place all files there. We will execute this step-by-step in phases. Do not proceed to the next phase until you receive my explicit approval.

## General Guidelines
* Refer to `project-standards.mdc` and follow it strictly.
* **ABSOLUTE RULE:** No fallbacks or silent error catch-and-continue mechanisms. If a physical law of Minecraft is broken, raise an explicit exception and fail the code. Any fallback code you wish to implement requires my explicit approval and a detailed explanation of its behavior.

---

## Phase 1: Pre-requisites (Static Blueprint Generation)
Generate all one-time static files.
* **Full Item List:** Generate a full list of Minecraft items for the given version.
* **Task Queue Blueprints:** Use this list to generate a generic, pre-computed linear task queue for each item, assuming it is the only item to be collected. No optimizations or quantity tracking here. Assume stone tools.
    * **Algorithm:** For each item, check its recipe (crafting/smelting). If it has no recipe, it must be mined; use `material_harvest.json` to identify the required tool.
    * Use a recursive Depth-First Search (DFS). Example: `diamond_pickaxe` -> looks up recipe (3 diamonds, 2 sticks) -> recurses into `diamond` (requires mining ore) -> checks `blocks.json` (requires Iron Pickaxe) -> recurses into `iron_pickaxe`.
    * As the DFS bottoms out, append the steps to an array. Stop from the deepest item up to the target item.
* **Byproduct Injection:** Once provided with the junk block creation file, populate all mining tasks across all blueprints with the expected byproduct volume per instance mined.

---

## Phase 2: Item Task Generator (`planner/item_task_generator.py`)
Implement a `Task` class with attributes: `id`, `name`, `quantity`, `dependencies` (array of IDs), and `operation_type`.

* **Function 1 (Single Item):** Accepts an item and quantity. Looks up the pre-computed blueprint.
    * **ID Generation:** Concatenate `operation_type` and `item` name using a colon (e.g., `MINE:redstone`) to generate unique, readable IDs. **DO NOT** use cryptographic hashing.
    * **Dependency Wiring:** Record all immediate dependencies as an array of IDs. 
        * **CRITICAL WORKSTATIONS:** Smelting operations MUST inject an immediate dependency ID for `furnace`. Crafting operations requiring a 3x3 grid MUST inject a dependency ID for `crafting_table`.
    * **Quantity & Durability Math (STRICT):**
        * **Yield Math:** Divide the target quantity by the recipe's output yield, rounding up, before multiplying ingredient requirements (e.g., 512 planks requires exactly 128 logs, not 512).
        * **Fuel Math:** For `SMELT` operations, divide the total target quantity by the fixed fuel's burn yield, rounding up. Assume `planks` as fixed baseline fuel (1 plank = 1.5 items smelted). 64 stone requires 43 planks.
        * **Naive Durability Math:** Calculate raw tool durability ONLY (`target_qty / tool_durability`). **DO NOT** include exploration or `junk_block` penalties here. Phase 4 handles exploration.
    * **Circular Dependency Check:** Prevent logic loops (e.g., stone axe needs sticks -> logs -> requires stone axe). Use hand initially if plausible. Fail explicitly on unresolvable loops.

* **Function 2 (Global Target):** Accepts the entire user request list, iterates through Function 1, combines the resulting queues, and returns them as-is. No optimization.

---

## Phase 3: The Combiner (`planner/combiner.py`)
* **Input:** The list of item task queues from Phase 2.
* **Logic:** Combine all common tasks using their semantic IDs. If two targets both require an Iron Pickaxe, merge them. Keep exactly one instance of the recurring task and sum the `quantity`.
* **Output:** A merged graph with zero duplicate tasks. No ordering yet.

---

Phase 4: Local Optimizer & DAG Router (Tool ROI & Lot-Sizing)

Architectural Note: To maintain the Single Responsibility Principle and guarantee reliable execution, Phase 4 is split into two separate modules.

    Phase 4A handles global macro-mathematics and quantity mutations.

    Phase 4B handles chunking, remainder padding, and DAG edge rewiring.

## Phase 4A: Global Math Optimizer (planner/global_math_optimizer.py)

Input: The combined, deduplicated linear list of global tasks from Phase 3 (phase3_output.json).
Dependencies: Load constants/blueprints.json to reference recipe yields, operation types, fuel metrics, and exact ingredient costs.
Constraint: Do NOT slice or chunk ANY tasks during this script. Only mutate the global quantities.

Logic (Strict Execution Order: 1B → 1C → 1A):

    1B. The Breakeven Tool Check (ROI) & MVB Injection:

        Evaluate gathering tasks where harvest.min_tier allows hand/wooden mining. Calculate Time_Hand = Quantity * 3.0s vs Time_Upgrade = 25.0s + (Quantity * 0.4s).

        If Time_Upgrade < Time_Hand, trigger a Dependency Swap to upgrade to the relevant stone tool.

        Dynamic MVB Injection: Trace the new tool's requirements backwards through blueprints.json to generate an isolated Minimum Viable Bootstrap chain (e.g., MINE:oak_log_mvb_1 -> CRAFT:wooden_pickaxe_mvb_1 -> MINE:cobblestone_mvb_1). Append _mvb_{id} to ensure strict global uniqueness.

        Seed Deduction: Deduct the exact material costs of the MVB chain from the original massive global task.

    1C. Workstations (Parabolic Math, Ingredient & Fuel Deltas):

        For massive smelting (sum of all operation_type == "smelt" > 64), calculate optimal furnace count: k = max(1, round(math.sqrt((N * 10.0) / 30.0))).

        Find the CRAFT:furnace task, update quantity to k, and calculate delta = k - old_qty.

        Ingredient Delta Upstream Fix: Reverse-lookup the station's blueprint ingredient cost. Mutate the corresponding upstream global source node by item/name mapping (not hardcoded ID guessing): task['quantity'] += (ingredient_cost * delta). If the source node cannot be uniquely located, raise ValueError.

        Fuel Delta Upstream Fix: Locate the station's designated fuel dependency. Calculate items_per_furnace = math.ceil(total_smelt / k). Look up the fuel's burn_time/yield in blueprints. Calculate fuel_per_furnace = math.ceil(items_per_furnace / fuel_yield). Compute new_total_fuel = fuel_per_furnace * k. Apply this new total minus the old total as a delta to the upstream fuel source node.

    1A. Global Tool Recalculation & Ingredient Deltas:

        Use this strict durability map: {"wooden_pickaxe": 59, "stone_pickaxe": 131, "iron_pickaxe": 250, "diamond_pickaxe": 1561, "wooden_axe": 59, "stone_axe": 131, "iron_axe": 250}. Default to 59 for unlisted wood tools.

        Scan the graph for tool tasks. Sum the finalized downstream workload per tool dependency. Recalculate tool quantity: new_qty = math.ceil(total_workload / DURABILITY[tool_name]).

        Tool Delta Upstream Fix: Calculate delta = new_qty - old_qty. Reverse-lookup the tool's ingredients from blueprints.json and mutate upstream source nodes exactly as done in 1C.

    Global Pruning Rule (Applies to 1B, 1C, 1A):

        After applying any propagated negative deltas or seed deductions, if any source node's total quantity drops to <= 0, that node MUST be completely removed from the global task list immediately.

Output: phase4a_optimized_global.json (Mathematically perfected flat list of massive tasks).
Phase 4B: The DAG Router (planner/dag_router.py)

Input: phase4a_optimized_global.json.

Logic (Step 2 → Step 3):

Step 2: Universal 64-Cap Slicer (Lot-Sizing)

    Iterate through the optimized list to create a new chunked_tasks list.

    Workstation Exclusion: Tasks creating {"crafting_table", "furnace", "blast_furnace", "smoker", "stonecutter", "loom", "brewing_stand"} remain as single chunks regardless of quantity.

    Unstackable Exclusion: Tools, weapons, and armor CANNOT stack. Slice them into chunks of exactly quantity: 1.

    Yield-Preserving Slicer: For all other items > 64, slice into sequences. Each full chunk MUST respect the item's discrete recipe yield (e.g., Yield 4 = max size 64, Yield 3 = max size 63).

    Remainder Padding: The final remainder chunk MUST be mathematically padded to the nearest craftable multiple to prevent fractional ingredient demands: chunk_qty = math.ceil(remainder / yield_per_run) * yield_per_run. Never emit a non-craftable remainder.

    Naming: Assign deterministic IDs: {original_id}_chunk_{index}. Unsliced tasks become _chunk_1.

Step 3: The Sequential Capacity Ledger (Two-Pass Architecture)

    Pass 1: Registration (Prevent Topo-Sort Paradox)

        Iterate through chunked_tasks and build capacity_ledger.

        Consumables capacity = chunk.quantity.

        Tools capacity = DURABILITY[tool_name].

        Do NO rewiring during this pass.

    Pass 2: Consumption & Rewiring

        Iterate through chunked_tasks a second time to rewire dependencies arrays using Waterfall Logic.

        Blueprint-Classified Demand Formulas:

            If the dependency is listed in the blueprint's ingredients dict: demand = chunk.quantity * recipe_ingredient_count.

            If the dependency is listed only in prerequisites (tools/stations): demand = chunk.quantity (durability/operation uses).

        Strict ID-Family Matching: CRAFT:stone_pickaxe may only consume chunks derived from the exact base ID CRAFT:stone_pickaxe. It MUST NOT consume _mvb chunks. _mvb nodes must exclusively demand their own specific _mvb chunks.

        Waterfall & Rollover: Find the earliest matching chunk in the ledger. Draw capacity and deduct from the ledger. If it hits 0, append the next available upstream chunk ID to fulfill the remainder.

        Strict DAG Guard: Before appending a dependency string, run cycle detection. A tool chunk cannot depend on materials generated by its own execution. If the ledger runs out of acyclic capacity, raise a fatal ValueError with the missing chunk ID. NEVER silently fall back.

Output: tests/input_materials_test.phase4.json. A flat, linear queue of 64-capped task dictionaries where the DAG is implicitly defined by strictly acyclic {id}_chunk_{index} strings.
    
---

## Phase 5: Topological Sorter (Kahn's Algorithm) (planner/global_optimizer.py)

Execute Kahn's Algorithm topological sort to generate the final linear execution queue.

    Graph Edge Direction: In our JSON, a task's dependencies array lists its prerequisites. Therefore, a node's initial in_degree is the length of its dependencies array.

    The Loop:

        Find all tasks where in_degree == 0 and place them in the eligible_queue.

        Sort the eligible_queue using the Strict Sort Tuple.

        Pop the first task, append it to the final_queue, and decrement the in_degree of any task that listed this popped task as a dependency.

    The Strict Sort Tuple: You MUST use a strict Python Tuple for sorting eligible tasks: (inventory_pressure_score, base_id, chunk_index).

        Score A (Inventory Pressure): (Output Slots) - (Input Slots). Estimate slots by chunk counts: Output is always 1. Input is len(task['dependencies']). Calculation: 1 - len(dependencies). (Negative scores indicate the task consumes more slots than it creates, clearing inventory space, so they sort first).

        Score B (Base ID Batching): Extract the string ID without the chunk suffix (e.g., CRAFT:oak_planks). Sort alphabetically to group identical tasks together.

        Score C (Numeric Tie-Breaker): Extract the integer chunk index (e.g., 1, 2, 10). Sort as an integer (int(chunk_index)) to guarantee sequential execution of identical task chunks.
---

## Phase 6: Final Checker & Cache Simulator (`planner/final_checker.py`)
* **Simulation Mechanics (Strict Physics):** * Track inventory by **SLOTS**, not pure quantities (64 stackable items = 1 slot; unstackables/tools = 1 slot).
    * Track tool durability dynamically. If the bot executes a mine task without the required tool, or if the tool breaks mid-task and no replacement is in the inventory, throw a fatal exception.
* **Cache Lookahead:** The compiler assumes a static **Base Camp** coordinate where the Crafting Table, Furnace, and Storage Chests physically reside.
    * The moment 30 / 36 slots are occupied, inject a `Maps_TO_BASE` task, trigger chest creation, and toss items not immediately required. Check the next `N=4` downstream tasks to determine what to keep.
    * Any subsequent tasks requiring stashed items MUST also be preceded by a `Maps_TO_BASE` task.
* **Output:** 1. If failed: Exit specifying the exact physics failure reason.
    2. In both success and failure: Generate the inventory simulation as a 2D array for each task.
    3. Generate a linear `.mmd` (Mermaid) flowchart from the final generated queue.