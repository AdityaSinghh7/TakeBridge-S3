# LangGraph + DeepAgents Integration Plan (Custom Harness)

This document outlines a concrete, incremental plan to build a DeepAgents-like
system on top of LangGraph primitives while integrating cleanly with the current
orchestrator. It uses:

- LangGraph `StateGraph`, `START/END`, `Send` for parallel subagents, and a
  checkpointer for resumability.
- DeepAgents middleware pieces (`TodoListMiddleware`, `FilesystemMiddleware`,
  `SubAgentMiddleware`, optional summarization/caching middleware).
- The VM-backed filesystem backend already implemented in
  `server/api/deepagents_backend.py`.

The goal is to keep the orchestrator as the graph entrypoint, re-use existing
bridges, and add a configurable "DeepAgent-like" layer with subagents and memory
offloading.

---

## High-Level Requirements (from your request)

- Orchestrator is the LangGraph entry node.
- Use DeepAgents task middleware (the `task` tool exposed via
  `SubAgentMiddleware`) for subagent delegation.
- Implement MCP agent + computer-use agent as subagents with specialized tools.
- Support concurrent subagents when the orchestrator decides to parallelize.
- Use VM filesystem as memory storage and the DeepAgents filesystem middleware
  for large payload offloading and context management.

---

## Relevant LangGraph/DeepAgents Capabilities (Context7)

From DeepAgents docs:
- `FilesystemMiddleware` provides file tools (`ls`, `read_file`, `write_file`,
  `edit_file`, `glob`, `grep`) and can be configured with a custom backend.
- `SubAgentMiddleware` exposes a `task` tool to delegate work to subagents.
- `TodoListMiddleware` supports planning and tracking via `write_todos`.
- Other optional middleware: `SummarizationMiddleware`,
  `AnthropicPromptCachingMiddleware`, `PatchToolCallsMiddleware`,
  `HumanInTheLoopMiddleware`.

From LangGraph docs:
- `StateGraph` defines nodes/edges; compile with a checkpointer for persistence.
- `Send` enables fan-out for parallel node execution.
- Subgraphs are supported for modular composition.
- `interrupt()` enables human-in-the-loop pauses; `Command` resumes execution.

---

## Proposed Architecture

### Overview

We keep your existing orchestrator logic but run it inside a LangGraph graph,
then route into subagent nodes that use DeepAgents middleware. The filesystem
tools are backed by the VM via `VMControllerBackend`.

```
START
  -> orchestrator_plan
  -> (fan-out via Send) mcp_subagent / computer_subagent
  -> aggregate_results
  -> maybe_continue (condition)
  -> END
```

### Key Modules (new + existing)

- Existing:
  - `orchestrator_agent/runtime.py` (planning logic)
  - `orchestrator_agent/system_prompt.py` (planner prompt)
  - `orchestrator_agent/bridges.py` (agent invocation)
  - `server/api/deepagents_backend.py` (VM filesystem backend)

- New (suggested):
  - `orchestrator_agent/langgraph_runtime.py`
  - `orchestrator_agent/deepagent_harness.py`
  - `orchestrator_agent/langgraph_state.py`

---

## Graph State Design

Create a typed state for LangGraph (TypedDict or Pydantic model). Keep it aligned
with existing `RunState`.

Suggested fields:

```python
class OrchestratorGraphState(TypedDict):
    request: dict                     # OrchestratorRequest serialized
    run_state: dict                   # RunState serialized
    decision: dict | None             # {"type": ..., "target": ..., "task": ...}
    pending_tasks: list[dict]         # list of {"target": ..., "task": ...}
    results: list[dict]               # StepResult serialized (reducer: append)
    done: bool
    last_error: str | None
```

Reducer idea:
- `results` uses a list reducer (append).
- `pending_tasks` cleared after dispatch.

---

## Orchestrator-as-Start Node

### Node: `orchestrator_plan`

Inputs:
- `request`, `run_state`, `results`

Behavior:
- Call your existing planner path:
  - `build_system_prompt(...)`
  - `_call_planner_llm(...)`
- Return a decision dict, plus optionally a list of `pending_tasks` if you
  extend the planner to output multiple subtasks (for concurrency).

Output:

```json
{
  "decision": {"type": "next_step", "target": "...", "task": "..."},
  "pending_tasks": [ ... ]
}
```

### Parallel Dispatch via LangGraph `Send`

If `pending_tasks` contains multiple entries, use `Send` to fan out:

```python
def fan_out(state):
    return [
        Send("mcp_subagent", {...}) or Send("computer_subagent", {...})
        for task in state["pending_tasks"]
    ]
```

This matches your requirement to run concurrent subagents based on the
orchestrator's output.

---

## DeepAgents Middleware Stack (Custom Harness)

Create a "DeepAgents-like" agent in `deepagent_harness.py` using LangChain
`create_agent(...)` and the DeepAgents middleware.

Recommended middleware order:
1) `TodoListMiddleware` (planning + `write_todos`)
2) `FilesystemMiddleware` (VM backend, memory offload)
3) `SubAgentMiddleware` (task tool)
4) Optional: `SummarizationMiddleware` (automatic summarization)
5) Optional: `AnthropicPromptCachingMiddleware`, `PatchToolCallsMiddleware`

Example sketch:

```python
from langchain.agents import create_agent
from deepagents.middleware.filesystem import FilesystemMiddleware
from deepagents.middleware.subagents import SubAgentMiddleware
from deepagents.middleware.todo import TodoListMiddleware
from deepagents.middleware.summarization import SummarizationMiddleware

from server.api.deepagents_backend import VMControllerBackend

backend = VMControllerBackend(controller=controller, vm_root="C:\\Users\\Docker\\deepagent")

middleware = [
    TodoListMiddleware(),
    FilesystemMiddleware(backend=backend),
    SubAgentMiddleware(
        default_model="o4-mini",
        subagents=[...],
    ),
    SummarizationMiddleware(max_tokens=...),
]

agent = create_agent(model="o4-mini", middleware=middleware, tools=[...])
```

### Subagents

Define two subagents:
- `mcp-subagent`
  - Tool: `mcp_task(task: str) -> dict` (wrapper around `execute_mcp_task`)
  - System prompt: "Use MCP tools for API operations..."

- `computer-subagent`
  - Tool: `computer_use_task(task: str) -> dict` (wrapper around `runner`)
  - System prompt: "Use computer-use agent for UI operations..."

These subagents are registered in `SubAgentMiddleware`, so the supervisor can
call the `task` tool to delegate.

---

## Memory Strategy with VM Filesystem

Use the DeepAgents `FilesystemMiddleware` backed by `VMControllerBackend`.
Adopt a run-scoped directory layout on the VM root:

```
C:\Users\Docker\deepagent\
  runs\
    <run_id>\
      scratch\              # ephemeral files
      memory\               # persistent offload per run
      artifacts\            # exported artifacts
```

Suggested behavior:
- Planner/subagents write large payloads to `/runs/<run_id>/memory/...`.
- Summaries or final outputs can reference file paths (agent reads back as needed).
- Use `FilesystemMiddleware` tool descriptions to encourage offload:
  - "When content exceeds N tokens, write it to a file."

This aligns with DeepAgents' pattern of offloading large context to disk.

---

## Integration Points with Current System

### 1) Orchestrator Graph Runtime

Implement `orchestrator_agent/langgraph_runtime.py`:

- Build `StateGraph(OrchestratorGraphState)`
- Nodes:
  - `orchestrator_plan`
  - `fan_out` (conditional edges with `Send`)
  - `mcp_subagent`
  - `computer_subagent`
  - `aggregate_results`
  - `maybe_continue`
- Compile with a checkpointer:
  - In dev: `InMemorySaver`
  - In prod: implement `CheckpointSaver` that persists to
    `workflow_runs.agent_states`

### 2) Bridges for Subagents

Add wrappers in `orchestrator_agent/bridges.py` to adapt to the middleware:

- `mcp_task(task: str) -> dict` uses `execute_mcp_task(...)`
- `computer_use_task(task: str) -> dict` uses `runner(...)`

These can be direct wrappers around existing logic to avoid duplicated behavior.

### 3) System Prompt Alignment

Update file: `orchestrator_agent/system_prompt.py`  
Add file: `orchestrator_agent/deepagent_harness.py`

Include:
- The `task` tool as a delegation path for subagents.
- Guidance to offload large payloads to filesystem tools.

### 4) Concurrency and Limits

Use `Send` for parallel execution. The orchestrator controls how many tasks are
spawned. Add a guard:
- If `len(pending_tasks)` exceeds a threshold, batch them or reduce concurrency.
- Optionally reuse `OrchestratorRuntime.max_concurrency` to cap parallel work.

---

## Concrete Implementation Plan (Phased)

### Phase 0: Dependencies
- Add `langgraph` and `deepagents` dependencies (if not already in env).
- Confirm compatibility with your model backend.

### Phase 1: Graph Skeleton
- Create `orchestrator_agent/langgraph_state.py` with TypedDict.
- Create `orchestrator_agent/langgraph_runtime.py` and define graph nodes.
- Initially, have nodes call existing orchestrator methods and bridges.

### Phase 2: DeepAgents Middleware Harness
- Create `orchestrator_agent/deepagent_harness.py`:
  - Build LangChain agent with `TodoListMiddleware`,
    `FilesystemMiddleware(backend=VMControllerBackend)`,
    `SubAgentMiddleware`.
  - Register MCP and computer-use subagents.

### Phase 3: Integrate Subagents in Graph
- Update `mcp_subagent` and `computer_subagent` graph nodes to call the
  middleware-based agent (or keep direct bridge calls while you iterate).
- Add a fallback path to direct bridges if middleware execution fails.

### Phase 4: Checkpointing + Resumability
- Implement a custom LangGraph checkpointer that persists to
  `workflow_runs.agent_states`.
- Map `thread_id` to `run_id`.

### Phase 5: Memory Offloading Enforcement
- Update prompt guidelines in `system_prompt.py` to require filesystem offload
  for large payloads.
- Add a test that verifies large results are stored under the VM root.

---

## Suggested Code Skeleton (LangGraph Runtime)

```python
from langgraph.graph import StateGraph, START, END
from langgraph.types import Send

def orchestrator_plan(state):
    decision = call_existing_planner(state)
    pending = decision_to_tasks(decision)
    return {"decision": decision, "pending_tasks": pending}

def fan_out(state):
    sends = []
    for task in state["pending_tasks"]:
        node = "mcp_subagent" if task["target"] == "mcp" else "computer_subagent"
        sends.append(Send(node, {"task": task}))
    return sends

def mcp_subagent(state):
    result = run_mcp_task(state["task"])
    return {"results": [result]}

def computer_subagent(state):
    result = run_computer_task(state["task"])
    return {"results": [result]}

def aggregate_results(state):
    update_run_state(state)
    return {}

def maybe_continue(state):
    return END if should_stop(state) else "orchestrator_plan"

builder = StateGraph(OrchestratorGraphState)
builder.add_node("orchestrator_plan", orchestrator_plan)
builder.add_node("mcp_subagent", mcp_subagent)
builder.add_node("computer_subagent", computer_subagent)
builder.add_node("aggregate_results", aggregate_results)

builder.add_edge(START, "orchestrator_plan")
builder.add_conditional_edges("orchestrator_plan", fan_out, ["mcp_subagent", "computer_subagent"])
builder.add_edge("mcp_subagent", "aggregate_results")
builder.add_edge("computer_subagent", "aggregate_results")
builder.add_conditional_edges("aggregate_results", maybe_continue, ["orchestrator_plan", END])

graph = builder.compile(checkpointer=your_checkpointer)
```

---

## Testing Strategy

- Unit test: `VMControllerBackend` filesystem middleware integration.
- Unit test: LangGraph nodes return expected state mutations.
- Integration test: orchestrator plan -> parallel subagents -> aggregate.
- Smoke test: large payload forces `write_file` to VM memory path.

---

## Risks and Mitigations

- Middleware dependencies: if deepagents is not installed, the harness should
  fall back to existing bridges.
- Parallel fan-out: ensure subagents do not share mutable state and guard
  shared filesystem paths.
- Cost growth: subagent concurrency can increase token usage; use budget
  checks in `aggregate_results`.

---

## Concrete Next Step (if you want code changes)

I can implement Phase 1 + Phase 2 behind a feature flag so you can opt-in
per run. This keeps current behavior intact and lets you validate the graph
execution and middleware stack in isolation.
