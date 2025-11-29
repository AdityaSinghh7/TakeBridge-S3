# Orchestrator Integration - Quick Start Guide

## 🚀 Getting Started

### 1. Environment Setup
```bash
# Enable orchestrator agent (default: true)
export USE_ORCHESTRATOR_AGENT=true

# Set default user ID for testing
export TB_DEFAULT_USER_ID=test-user-123
```

### 2. Run Integration Tests
```bash
# Run all tests
.venv/bin/python3 test_orchestrator_integration.py

# Expected output: 7/7 tests passed ✅
```

### 3. Verify Logging Structure
```bash
# Demonstrate hierarchical logging
.venv/bin/python3 verify_logging_structure.py

# This creates: demo_logs/{timestamp}_{hash}/
```

---

## 📋 Common Use Cases

### Auto Mode (All Authorized Tools)
```python
from orchestrator_agent.data_types import (
    OrchestratorRequest,
    TenantContext,
    Budget,
)

request = OrchestratorRequest(
    task="Send an email about the meeting",
    max_steps=10,
    tenant=TenantContext(
        tenant_id="org-123",
        user_id="user-456",
    ),
    budget=Budget(max_steps=10),
    user_id="user-456",
)

from orchestrator_agent.runtime import OrchestratorRuntime
runtime = OrchestratorRuntime()
result = await runtime.run_task(request)
```

### Custom Mode (Specific Providers Only)
```python
from orchestrator_agent.data_types import ToolConstraints

request = OrchestratorRequest(
    task="Schedule meeting and send calendar invite",
    max_steps=15,
    tenant=TenantContext(tenant_id="org-123", user_id="user-456"),
    budget=Budget(max_steps=15),
    tool_constraints=ToolConstraints(
        mode="custom",
        providers=["google_calendar", "gmail"],
    ),
    user_id="user-456",
)
```

---

## 🔍 Exploring Logs

### Find Latest Run
```bash
# List runs by timestamp
ls -lt logs/

# View structure
cd logs/2025-11-29T*_*/
tree
```

### View Event Logs
```bash
# Orchestrator events
cat orchestrator/main.jsonl | jq .

# MCP agent events
cat mcp/step-*/main.jsonl | jq .

# Computer use events
cat computer_use/step-*/main.jsonl | jq .
```

### Search Logs
```bash
# Find all tool executions
find . -name 'main.jsonl' -exec grep -l "tool.execution" {} \;

# Count events by type
cat orchestrator/main.jsonl | jq -r .event | sort | uniq -c
```

---

## 🧪 Testing Checklist

- [x] Request adapter conversion
- [x] Tool constraints dataclass
- [x] Hierarchical logger setup
- [x] Tool filtering logic
- [x] SSE event emission
- [x] Feature flag routing
- [x] OrchestratorRequest construction

All tests passing: **7/7 ✅**

---

## 📊 Log Directory Structure

```
logs/{timestamp}_{task_hash}/
├── metadata.json              # Task metadata
├── orchestrator/
│   ├── main.jsonl            # Orchestration events
│   └── raw/                  # Full payloads
├── mcp/
│   └── {step_id}/
│       ├── main.jsonl        # MCP events
│       ├── planner/
│       │   └── main.jsonl
│       └── raw/
└── computer_use/
    └── {step_id}/
        ├── main.jsonl
        ├── worker/
        ├── code_agent/
        └── grounding/
```

---

## 🎯 Key Features

### 1. Tool Constraints
- **Auto mode**: All authorized tools (OAuth-verified)
- **Custom mode**: Specific providers only

### 2. SSE Streaming
- Real-time events from all agents
- 15+ event types tracked
- Client-friendly SSE format

### 3. Hierarchical Logging
- Task-based separation
- Agent/step hierarchy
- Intelligent truncation (500 chars)
- Full payloads in `raw/`

### 4. Feature Flag
- `USE_ORCHESTRATOR_AGENT=true` → New path
- `USE_ORCHESTRATOR_AGENT=false` → Legacy path

---

## 🔧 Troubleshooting

### Logs not appearing?
```python
from shared.hierarchical_logger import get_hierarchical_logger
logger = get_hierarchical_logger()
print(f"Logger initialized: {logger is not None}")
```

### Tool constraints not working?
```python
from mcp_agent.registry.oauth import OAuthManager
from mcp_agent.core.context import AgentContext

ctx = AgentContext.create("your-user-id")
status = OAuthManager.auth_status(ctx, "gmail")
print(f"Gmail authorized: {status.get('authorized')}")
```

### SSE events not received?
```python
from shared.streaming import get_current_emitter
emitter = get_current_emitter()
print(f"Emitter set: {emitter is not None}")
```

---

## 📚 Documentation

- [Full Summary](ORCHESTRATOR_INTEGRATION_SUMMARY.md) - Complete documentation
- [Integration Tests](test_orchestrator_integration.py) - Test suite
- [Logging Demo](verify_logging_structure.py) - Structure demonstration
- [Plan Document](.claude/plans/hashed-baking-token.md) - Original design

---

## ✅ Verification

Run these commands to verify everything works:

```bash
# 1. Run tests
.venv/bin/python3 test_orchestrator_integration.py

# 2. Demo logging
.venv/bin/python3 verify_logging_structure.py

# 3. Check imports
.venv/bin/python3 -c "
from orchestrator_agent.data_types import ToolConstraints
from shared.hierarchical_logger import HierarchicalLogger
from server.api.orchestrator_adapter import orchestrate_to_orchestrator
print('✓ All imports successful')
"
```

Expected output: All checks pass ✅

---

## 🎉 You're Ready!

The orchestrator integration is complete and tested. Use this guide as a quick reference for common tasks.

For detailed information, see [ORCHESTRATOR_INTEGRATION_SUMMARY.md](ORCHESTRATOR_INTEGRATION_SUMMARY.md).
