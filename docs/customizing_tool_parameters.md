# Customizing Tool Parameters

This document explains how `input_params` are generated for MCP tools and how to customize parameter names, types, and required/optional status.

## How input_params Are Generated

### 1. Primary Source: Python Introspection

When the `ToolboxBuilder` runs, it introspects Python wrapper functions in `mcp_agent/actions.py`:

**File: `mcp_agent/toolbox/builder.py`**

```python
def _build_tool(self, provider: str, func: Callable, ...) -> ToolSpec:
    signature = inspect.signature(func)  # Line 234
    parameters = []
    for param in signature.parameters.values():
        if param.name == "self":
            continue
        parameters.append(
            ParameterSpec(
                name=param.name,                              # From function signature
                kind=str(param.kind).replace("Parameter.", "").lower(),
                required=param.default is inspect._empty,     # No default = required
                has_default=param.default is not inspect._empty,
                annotation=format_annotation(param.annotation),
                default=param.default,
                default_repr=param.default_repr,
                description=param_docs.get(param.name),       # From docstring
            )
        )
```

**Key Points:**
- Parameter **names** come from the function signature
- **Required** status is determined by whether a parameter has a default value
- **Type annotations** come from Python type hints
- **Descriptions** are parsed from the function's docstring

### 2. Conversion to LLM Format

The `ToolSpec` is converted to `LLMToolDescriptor` for the planner:

**File: `mcp_agent/toolbox/models.py`**

```python
def to_llm_descriptor(self, *, score: float = 0.0) -> LLMToolDescriptor:
    required_params: List[Dict[str, Any]] = []
    optional_params: List[Dict[str, Any]] = []
    
    for param in self.parameters:
        info = {
            "name": param.name,
            "type": param.annotation or "Any",
        }
        if param.has_default:
            info["default"] = param.default_repr or param.default
        
        if param.required:
            required_params.append(info)
        else:
            optional_params.append(info)
    
    input_params = {
        "required": required_params,
        "optional": optional_params,
    }
```

**Result Structure:**
```python
{
    "required": [
        {"name": "query", "type": "str"},
        {"name": "subject", "type": "str"},
    ],
    "optional": [
        {"name": "max_results", "type": "int", "default": "20"},
        {"name": "is_html", "type": "bool", "default": "False"},
    ]
}
```

### 3. Optional Manual Overrides

Manual specifications can be registered to override the **display** (but not the structure):

**File: `mcp_agent/toolbox/search.py`**

```python
# Optional IO spec overrides (manual, higher-fidelity docs).
io_spec = get_tool_spec(prov.provider, tool.name)
if io_spec is not None:
    input_pretty = io_spec.input_spec.pretty()
    if input_pretty:
        entry["input_params_pretty"] = input_pretty.splitlines()  # Only overrides display
```

**Important:** Manual overrides affect `input_params_pretty` (human-readable) but **NOT** the structured `input_params` dict used by the planner.

## How to Customize Parameters

### Change Parameter Names

**Edit the function signature in `mcp_agent/actions.py`:**

```python
# Before:
@mcp_action
def gmail_send_email(
    self,
    to: str,          # ← This is what the LLM sees
    subject: str,
    body: str,
):
    # Inside, map to Composio's expected name
    args = {
        "recipient_email": to,  # ← Map user-friendly name to API name
        "subject": subject,
        "body": body,
    }
    return _invoke_mcp_tool("gmail", "GMAIL_SEND_EMAIL", args)

# After changing parameter name:
@mcp_action
def gmail_send_email(
    self,
    recipient: str,   # ← Changed from "to" to "recipient"
    subject: str,
    body: str,
):
    args = {
        "recipient_email": recipient,  # ← Update mapping
        "subject": subject,
        "body": body,
    }
    return _invoke_mcp_tool("gmail", "GMAIL_SEND_EMAIL", args)
```

**Then regenerate the toolbox:**
```python
from mcp_agent.toolbox import ToolboxBuilder
builder = ToolboxBuilder(user_id="your_user_id")
manifest = builder.build()
builder.persist(manifest)
```

### Mark Parameters as Required or Optional

**Add or remove default values in the function signature:**

```python
# Make "max_results" required (remove default):
@mcp_action
def gmail_search(
    self,
    query: str,
    max_results: int,  # ← No default = REQUIRED
):
    pass

# Make "subject" optional (add default):
@mcp_action
def gmail_send_email(
    self,
    to: str,
    subject: str = "",  # ← Has default = OPTIONAL
    body: str = "",     # ← Has default = OPTIONAL
):
    pass
```

### Change Parameter Types

**Update type annotations in the function signature:**

```python
# Before:
def gmail_search(
    self,
    query: str,
    max_results: int = 20,
):
    pass

# After:
def gmail_search(
    self,
    query: str,
    max_results: int | str = 20,  # ← Now accepts int or str
):
    pass
```

### Add Parameter Descriptions

**Add docstring with Args section:**

```python
@mcp_action
def gmail_send_email(
    self,
    to: str,
    subject: str,
    body: str,
):
    """
    Send an email via Gmail.
    
    Args:
        to: Comma-separated email addresses of recipients
        subject: Email subject line
        body: Plain text or HTML body content
    """
    pass
```

The descriptions will be parsed and included in the tool metadata.

## Advanced: Manual IO Spec Registration

For more control over the **display format** (without changing the function), register a manual `IoToolSpec`:

```python
from mcp_agent.toolbox.io_spec import IoToolSpec, ToolInputSpec, InputParamSpec
from mcp_agent.toolbox.registry import register_tool

spec = IoToolSpec(
    provider="gmail",
    tool_name="gmail_send_email",
    python_name="gmail_send_email",
    python_signature="await gmail.gmail_send_email(to, subject, body)",
    description="Send an email via Gmail API",
    input_spec=ToolInputSpec(params=[
        InputParamSpec(
            name="to",
            type="string",
            required=True,
            description="Comma-separated email addresses"
        ),
        InputParamSpec(
            name="subject",
            type="string",
            required=True,
            description="Email subject line"
        ),
        InputParamSpec(
            name="body",
            type="string",
            required=True,
            description="Email body (plain text or HTML)"
        ),
    ]),
)

register_tool(spec)
```

**Note:** This only affects the **pretty display** (`input_params_pretty`). The structured `input_params` dict still comes from introspection.

## Precedence

1. **Python Function Signature** (highest priority) → Defines actual parameter names, types, required/optional
2. **Manual IO Spec** (optional) → Can override display format only
3. **Generated Default** (fallback) → Used if no IO spec exists

## Summary

| What to Change | How to Change It | File to Edit |
|----------------|------------------|--------------|
| Parameter names | Edit function signature | `mcp_agent/actions.py` |
| Required/optional status | Add/remove default values | `mcp_agent/actions.py` |
| Parameter types | Update type annotations | `mcp_agent/actions.py` |
| Parameter descriptions | Add Args docstring | `mcp_agent/actions.py` |
| Display format only | Register IoToolSpec | `mcp_agent/toolbox/registry.py` |

After making changes to `actions.py`, always regenerate the toolbox with `ToolboxBuilder.build()` and `.persist()`.

