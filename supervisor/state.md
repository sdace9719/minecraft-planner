# Architectural Design & Implementation Specification
**System:** Headless Autonomous Minecraft Agent (Task Tracking & Execution Engine)
**Context:** Python (Controller) ↔ MCCTP (Telemetry) ↔ ControlBridge (HTTP) ↔ BotInterface (Fabric Mod) ↔ Baritone (Pathing)

---

## 1. System Topology & Thread Synchronization

To prevent HTTP network threads (`ControlBridge`) and WebSocket threads (`MCCTP`) from conflicting with the single-threaded Minecraft client loop, all task state modifications must flow through a synchronized memory manager inside the Client JVM. State transitions are propagated via the telemetry stream; Python must never poll the HTTP gateway for status updates.

```text
┌────────────────────────────────────────────────────────┐
│               MINECRAFT CLIENT JVM                     │
│                                                        │
│  ┌────────────────┐         ┌──────────────────────┐   │
│  │ ControlBridge  │         │     BotInterface     │   │
│  │ (HTTP Server)  │         │ (Fabric Tick Events) │   │
│  └───────┬────────┘         └──────────┬───────────┘   │
│          │ Write                       │ Intercept     │
│          └───────────────┐   ┌─────────┘ Events        │
│                          ▼   ▼                         │
│             ┌─────────────────────────┐                │
│             │    TaskStateManager     │                │
│             │  (Shared Thread-Safe)   │                │
│             └────────────┬────────────┘                │
│                          │ Read                        │
│                          ▼                             │
│                  ┌──────────────┐                      │
│                  │    MCCTP     │                      │
│                  │ (WebSocket)  │                      │
│                  └───────┬──────┘                      │
└──────────────────────────┼─────────────────────────────┘
                           │ Outbound JSON Stream (50ms Ticks)
                           ▼
               ┌───────────────────────┐
               │   Python Controller   │
               └───────────────────────┘
```

---

## 2. Phase 1: Shared Memory State Tracking (Java)

Implement a Thread-Safe Singleton inside the Fabric mod to hold the current active task state. This acts as the single source of truth for both ControlBridge (mutator) and MCCTP (reader).

### Contract 2.1: Task State Enums
```java
package com.botinterface.tracking;

public enum TaskType {
    IDLE,
    MINING,
    CRAFTING,
    SMELTING,
    TRAVEL,
    GATHER,
    PLACE,
    STASH,
    GOTO,
    TOSS,
    INVENTORY_SYNC
}

public enum TaskStatus {
    IDLE,
    EXECUTING,
    WAITING_ON_WORLD,  // Used for asynchronous server processes like smelting
    COMPLETED,
    FAILED_BARITONE,
    FAILED     // Stalled by game mechanics
}
```

### Contract 2.2: The State Object
```java
package com.botinterface.tracking;

import java.util.UUID;

public class TaskState {
    private final UUID taskId;
    private final TaskType type;
    private TaskStatus status;
    private String targetResource;
    private int targetQuantity;
    private int currentProgress;
    private String lastErrorMessage;

    public TaskState(UUID taskId, TaskType type, String targetResource, int targetQuantity) {
        this.taskId = taskId;
        this.type = type;
        this.status = TaskStatus.STARTING;
        this.lastErrorMessage = "";
    }

    // ALL GETTERS AND SETTERS MUST BE SYNCHRONIZED
    public synchronized UUID getTaskId() { return taskId; }
    public synchronized TaskType getType() { return type; }
    public synchronized TaskStatus getStatus() { return status; }
    public synchronized void setStatus(TaskStatus status) { this.status = status; }
    public synchronized int getCurrentProgress() { return currentProgress; }
    public synchronized void setCurrentProgress(int progress) { this.currentProgress = progress; }
    public synchronized String getLastErrorMessage() { return lastErrorMessage; }
    public synchronized void setLastErrorMessage(String msg) { this.lastErrorMessage = msg; }
    public synchronized String getTargetResource() { return targetResource; }
    public synchronized int getTargetQuantity() { return targetQuantity; }
}
```

### Contract 2.3: The Thread-Safe Manager Singleton
```java
package com.botinterface.tracking;

import java.util.concurrent.atomic.AtomicReference;
import java.util.UUID;

public class TaskStateManager {
    private static final TaskStateManager INSTANCE = new TaskStateManager();
    private final AtomicReference<TaskState> currentTask = new AtomicReference<>(
        new TaskState(new UUID(0L, 0L), TaskType.IDLE, "none", 0)
    );

    private TaskStateManager() {
        currentTask.get().setStatus(TaskStatus.IDLE);
    }

    public static TaskStateManager getInstance() {
        return INSTANCE;
    }

    public TaskState getCurrentTaskState() {
        return currentTask.get();
    }

    public void setNewTask(TaskState task) {
        this.currentTask.set(task);
    }

    public void clearTask() {
        this.currentTask.set(new TaskState(new UUID(0L, 0L), TaskType.IDLE, "none", 0));
        this.currentTask.get().setStatus(TaskStatus.IDLE);
    }
}
```

---

## 3. Phase 2: Execution Layer & Event Hooking (Java)

Do not tightly couple with Baritone's inheritance tree. Use the Facade pattern. Hook into Baritone’s event bus to intercept pathing failures and translate them into our unified `TaskStatus` enums. Ensure all interactions with the Minecraft client run safely on the primary game thread.

### Contract 3.1: Thread Boundary Enforcement Rule
Whenever `ControlBridge` or any network thread initiates an action affecting the player or world, it MUST be wrapped as follows:
```java
MinecraftClient.getInstance().execute(() -> {
    // prepare and execute task
});
```

### Contract 3.2: Baritone Exception Interceptor Facade
```java
package com.botinterface.tracking;

import baritone.api.BaritoneAPI;
import baritone.api.event.events.PathingBehaviorEvent;
import baritone.api.event.listener.IGameEventListener;

public class BaritoneTaskListener implements IGameEventListener {

    public static void register() {
        BaritoneAPI.getProvider().getPrimaryBaritone()
            .getGameEventHandler().registerEventListener(new BaritoneTaskListener());
    }

    @Override
    public void onPathingBehavior(PathingBehaviorEvent event) {
        TaskState state = TaskStateManager.getInstance().getCurrentTaskState();
        
        // Only evaluate if we are actively executing a physical task assigned to Baritone
        if (state.getType() != TaskType.MINING && state.getType() != TaskType.TRAVEL) {
            return;
        }

        switch (event.getState()) {
            case PATH_CALCULATION_FAILED:
                state.setStatus(TaskStatus.FAILED_UNREACHABLE);
                state.setLastErrorMessage("Baritone pathing failed: Goal is completely unreachable.");
                BaritoneAPI.getProvider().getPrimaryBaritone().getMineProcess().cancel();
                break;
            case STUCK_PANIC:
                state.setStatus(TaskStatus.FAILED_TIMEOUT);
                state.setLastErrorMessage("Baritone panicked: Character stuck in local geometry.");
                BaritoneAPI.getProvider().getPrimaryBaritone().getMineProcess().cancel();
                break;
            default:
                break;
        }
    }
}
```

---

## 4. Phase 3: Network Data Contracts

Modify the `MCCTP` WebSocket encoder loop to dynamically read from `TaskStateManager.getInstance().getCurrentTaskState()` and append it to every outbound tick packet. Implement ControlBridge endpoints to overwrite the state upon command receipt.

### Contract 4.1: Outbound MCCTP Telemetry JSON Schema
```json
{
  "$schema": "[http://json-schema.org/draft-07/schema#](http://json-schema.org/draft-07/schema#)",
  "title": "MCCTP_Telemetry_Frame",
  "type": "object",
  "required": ["tick_timestamp", "player_state", "active_task"],
  "properties": {
    "tick_timestamp": { "type": "integer" },
    "player_state": {
      "type": "object",
      "required": ["xyz", "health", "inventory"],
      "properties": {
        "xyz": {
          "type": "array",
          "minItems": 3,
          "maxItems": 3,
          "items": { "type": "number" }
        },
        "health": { "type": "number" },
        "inventory": {
          "type": "object",
          "additionalProperties": { "type": "integer" }
        }
      }
    },
    "active_task": {
      "type": "object",
      "required": ["task_id", "type", "status", "target_resource", "target_quantity", "current_progress", "last_error"],
      "properties": {
        "task_id": { "type": "string", "format": "uuid" },
        "type": { "enum": ["IDLE", "MINING", "CRAFTING", "SMELTING", "TRAVEL", "INVENTORY_SYNC"] },
        "status": { "enum": ["IDLE", "STARTING", "EXECUTING", "WAITING_ON_WORLD", "COMPLETED", "FAILED_UNREACHABLE", "FAILED_TOOL_BROKEN", "FAILED_TIMEOUT", "CANCELLED"] },
        "target_resource": { "type": "string" },
        "target_quantity": { "type": "integer" },
        "current_progress": { "type": "integer" },
        "last_error": { "type": "string" }
      }
    }
  }
}
```

### Contract 4.2: Inbound ControlBridge Endpoint Rules

#### 1. Start Task Gateway
* **Endpoint:** `POST /api/task/start`
* **Content-Type:** `application/json`
* **Payload Structure:**
```json
{
  "task_id": "4f9c8d1a-5b2e-4c3d-8e1f-9a0b1c2d3e4f",
  "type": "MINING",
  "target": "minecraft:spruce_log",
  "quantity": 100
}
```
* **Processing Rule:** Validates payload structural health, updates the shared memory token via `TaskStateManager.getInstance().setNewTask()`, and immediately yields execution to the main client logic scheduler thread.
* **Response Status:** `202 Accepted`

#### 2. Terminate Task Interruption
* **Endpoint:** `POST /api/task/cancel`
* **Processing Rule:** Forcibly stops active Baritone loops, resets internal task parameters, updates status parameters to `CANCELLED`, and resets the manager token.
* **Response Status:** `200 OK`

---

## 5. Phase 4: Python High-Level Planner

The Python engine handles broad agent sequencing across two domains: **Physical Input Exclusivity** and **Asynchronous World Process Delegation**. 
* Exactly one `Physical` task (requiring body movement or inventory modification) can execute at a given time.
* `World Async` tasks (such as a server-side furnace smelting raw iron blocks) drop their physical resource locks immediately after setup, enabling parallel resource acquisition.

### Contract 5.1: Python Pipeline Engine Model
```python
import uuid
import requests
from typing import Dict, Any, List, Optional

class Task:
    def __init__(self, task_type: str, target: str, quantity: int, dependencies: Optional[List[str]] = None):
        self.task_id = str(uuid.uuid4())
        self.type = task_type                  # 'MINING', 'SMELTING', 'CRAFTING'
        self.target = target                  # 'minecraft:iron_ingot'
        self.quantity = quantity
        self.dependencies = dependencies or [] # Prerequisites by Task ID
        self.status = "PENDING"                # 'PENDING', 'STARTING', 'EXECUTING', 'COMPLETED', 'FAILED'

class HighLevelPlanner:
    def __init__(self):
        self.task_pipeline: List[Task] = []
        self.physical_actor_locked = False
        self.active_physical_task_id: Optional[str] = None

    def evaluate_pipeline(self, mcctp_telemetry: Dict[str, Any]) -> None:
        """
        Processes live telemetry frames to update internal pipeline state trees.
        Executed natively on every single inbound MCCTP WebSocket event payload.
        """
        current_task_state = mcctp_telemetry.get("active_task", {})
        jvm_task_id = current_task_state.get("task_id")
        jvm_status = current_task_state.get("status")
        
        # Synchronize Java memory assertions down into our local Python planner map
        if jvm_task_id and jvm_task_id == self.active_physical_task_id:
            self._sync_task_status(self.active_physical_task_id, jvm_status)

        for task in self.task_pipeline:
            if task.status in ["COMPLETED", "FAILED", "FAILED_UNREACHABLE", "FAILED_TIMEOUT"]:
                continue

            # Resolve Prerequisite Checklist
            dependencies_met = all(self._get_task_status(dep_id) == "COMPLETED" for dep_id in task.dependencies)
            
            if dependencies_met:
                if task.type in ["MINING", "CRAFTING", "TRAVEL"]:
                    # Physical exclusivity execution pathway
                    if not self.physical_actor_locked and task.status == "PENDING":
                        self._dispatch_physical_task(task)
                
                elif task.type == "SMELTING":
                    # Server-side world dependency execution pathway
                    if task.status == "PENDING":
                        self._dispatch_world_task(task)

    def _dispatch_physical_task(self, task: Task) -> None:
        self.physical_actor_locked = True
        self.active_physical_task_id = task.task_id
        task.status = "STARTING"
        requests.post("http://localhost:8080/api/task/start", json={
            "task_id": task.task_id,
            "type": task.type,
            "target": task.target,
            "quantity": task.quantity
        })

    def _dispatch_world_task(self, task: Task) -> None:
        task.status = "EXECUTING" # Sets internal status but DOES NOT set physical_actor_locked
        # Commands ControlBridge to interface with furnace UI, then back away immediately
        requests.post("http://localhost:8080/api/task/start", json={
            "task_id": task.task_id,
            "type": "SMELTING_INIT", 
            "target": task.target,
            "quantity": task.quantity
        })

    def _get_task_status(self, task_id: str) -> str:
        for t in self.task_pipeline:
            if t.task_id == task_id:
                return t.status
        return "UNKNOWN"

    def _sync_task_status(self, task_id: str, native_status: str) -> None:
        for t in self.task_pipeline:
            if t.task_id == task_id:
                if native_status in ["COMPLETED", "FAILED_UNREACHABLE", "FAILED_TIMEOUT", "CANCELLED"]:
                    t.status = native_status
                    if t.task_id == self.active_physical_task_id:
                        self.physical_actor_locked = False
                        self.active_physical_task_id = None
```