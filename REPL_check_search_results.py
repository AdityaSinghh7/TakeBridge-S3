"""
REPL code to check search_tools() results and verify schemas are loaded correctly.

Run this in a Python REPL or as a script:
    python REPL_check_search_results.py
"""

from pprint import pprint

from mcp_agent.knowledge.load_io_specs import ensure_io_specs_loaded
from mcp_agent.knowledge.search import search_tools
from mcp_agent.agent.state import _slim_tool_for_planner


def _count_max_depth(obj, depth=0):
    """Helper to count max nesting depth of a dict."""
    if not isinstance(obj, dict):
        return depth
    if not obj:
        return depth
    max_child_depth = depth
    for value in obj.values():
        if isinstance(value, dict):
            child_depth = _count_max_depth(value, depth + 1)
            max_child_depth = max(max_child_depth, child_depth)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    child_depth = _count_max_depth(item, depth + 1)
                    max_child_depth = max(max_child_depth, child_depth)
    return max_child_depth


# Make sure IO specs and schemas are loaded
ensure_io_specs_loaded()

# Use your dev user id
user_id = "dev-local"

print("=" * 70)
print("Gmail tools:")
print("=" * 70)
# Look at Gmail tools
gmail_search_tools = search_tools(query="gmail_search", user_id=user_id, detail_level="full", limit=5)
gmail_send_tools = search_tools(query="gmail_send_email", user_id=user_id, detail_level="full", limit=5)

print("\n--- gmail_search ---")
pprint(gmail_search_tools)
print("\n--- gmail_send_email ---")
pprint(gmail_send_tools)

print("\n" + "=" * 70)
print("Slack tools:")
print("=" * 70)
# Look at Slack tools
slack_search_tools = search_tools(query="slack_search_messages", user_id=user_id, detail_level="full", limit=5)
slack_post_tools = search_tools(query="slack_post_message", user_id=user_id, detail_level="full", limit=5)

print("\n--- slack_search_messages ---")
pprint(slack_search_tools)
print("\n--- slack_post_message ---")
pprint(slack_post_tools)

print("\n" + "=" * 70)
print("Verification:")
print("=" * 70)

# Verify gmail_search
gmail_search_entry = next((t for t in gmail_search_tools if t.get("tool_id") == "gmail.gmail_search"), None)
if gmail_search_entry:
    print("\n✓ Found gmail.gmail_search")
    print(f"  - Has output_schema: {'output_schema' in gmail_search_entry}")
    if "output_schema" in gmail_search_entry:
        props = gmail_search_entry["output_schema"].get("properties", {})
        print(f"  - Has 'messages': {'messages' in props}")
        print(f"  - Has 'nextPageToken': {'nextPageToken' in props}")
        print(f"  - Has 'resultSizeEstimate': {'resultSizeEstimate' in props}")
    print(f"  - Has output_schema_pretty: {'output_schema_pretty' in gmail_search_entry}")
    print(f"  - Has input_params_pretty: {'input_params_pretty' in gmail_search_entry}")
else:
    print("\n✗ gmail.gmail_search not found in results")

# Verify gmail_send_email
gmail_send_entry = next((t for t in gmail_send_tools if t.get("tool_id") == "gmail.gmail_send_email"), None)
if gmail_send_entry:
    print("\n✓ Found gmail.gmail_send_email")
    print(f"  - Has output_schema: {'output_schema' in gmail_send_entry}")
    if "output_schema" in gmail_send_entry:
        props = gmail_send_entry["output_schema"].get("properties", {})
        print(f"  - Has 'id': {'id' in props}")
        print(f"  - Has 'threadId': {'threadId' in props}")
        print(f"  - Has 'labelIds': {'labelIds' in props}")
    print(f"  - Has output_schema_pretty: {'output_schema_pretty' in gmail_send_entry}")
    print(f"  - Has input_params_pretty: {'input_params_pretty' in gmail_send_entry}")
else:
    print("\n✗ gmail.gmail_send_email not found in results")

# Verify slack_search_messages
slack_search_entry = next((t for t in slack_search_tools if t.get("tool_id") == "slack.slack_search_messages"), None)
if slack_search_entry:
    print("\n✓ Found slack.slack_search_messages")
    print(f"  - Has output_schema: {'output_schema' in slack_search_entry}")
    if "output_schema" in slack_search_entry:
        props = slack_search_entry["output_schema"].get("properties", {})
        print(f"  - Has 'messages': {'messages' in props}")
        if "messages" in props:
            msg_props = props["messages"].get("properties", {})
            print(f"    - messages.matches: {'matches' in msg_props}")
            print(f"    - messages.pagination: {'pagination' in msg_props}")
            print(f"    - messages.paging: {'paging' in msg_props}")
        print(f"  - Has 'ok': {'ok' in props}")
        print(f"  - Has 'query': {'query' in props}")
    print(f"  - Has output_schema_pretty: {'output_schema_pretty' in slack_search_entry}")
    print(f"  - Has input_params_pretty: {'input_params_pretty' in slack_search_entry}")
else:
    print("\n✗ slack.slack_search_messages not found in results")

# Verify slack_post_message
slack_post_entry = next((t for t in slack_post_tools if t.get("tool_id") == "slack.slack_post_message"), None)
if slack_post_entry:
    print("\n✓ Found slack.slack_post_message")
    print(f"  - Has output_schema: {'output_schema' in slack_post_entry}")
    if "output_schema" in slack_post_entry:
        props = slack_post_entry["output_schema"].get("properties", {})
        print(f"  - Has 'channel': {'channel' in props}")
        print(f"  - Has 'message': {'message' in props}")
        print(f"  - Has 'ok': {'ok' in props}")
        print(f"  - Has 'response_metadata': {'response_metadata' in props}")
        print(f"  - Has 'ts': {'ts' in props}")
    print(f"  - Has output_schema_pretty: {'output_schema_pretty' in slack_post_entry}")
    print(f"  - Has input_params_pretty: {'input_params_pretty' in slack_post_entry}")
else:
    print("\n✗ slack.slack_post_message not found in results")

print("\n" + "=" * 70)
print("Slimmed version (what planner sees):")
print("=" * 70)


def print_slimmed_tool(entry, tool_name):
    """Helper function to print slimmed version of a tool."""
    slim = _slim_tool_for_planner(entry)
    print(f"\n--- Slimmed {tool_name} ---")
    print(f"  Fields present: {list(slim.keys())}")
    print(f"  Full entry size: {len(str(entry))} chars")
    print(f"  Slim entry size: {len(str(slim))} chars")
    print(f"  Size reduction: {len(str(entry)) - len(str(slim))} chars")
    
    # Show output_fields instead of output_schema
    if "output_fields" in slim:
        full_schema_str = str(entry.get("output_schema", ""))
        output_fields_str = str(slim["output_fields"])
        print(f"  Schema size reduction: {len(full_schema_str) - len(output_fields_str)} chars")
        print(f"  Output fields count: {len(slim['output_fields'])}")
        print(f"  First 5 output_fields:")
        for field in slim["output_fields"][:5]:
            print(f"    - {field}")
    
    # Verify removed fields
    print(f"  ✓ input_params_pretty removed: {'input_params_pretty' not in slim}")
    print(f"  ✓ output_schema removed: {'output_schema' not in slim}")
    print(f"  ✓ output_schema_pretty removed: {'output_schema_pretty' not in slim}")
    print(f"  ✓ call_signature minimal: {slim.get('call_signature', '')}")
    
    print("\n  Complete slimmed JSON:")
    pprint(slim, width=120, depth=None)


# Print slimmed versions for all 4 tools
if gmail_search_entry:
    print_slimmed_tool(gmail_search_entry, "gmail.gmail_search")

if gmail_send_entry:
    print_slimmed_tool(gmail_send_entry, "gmail.gmail_send_email")

if slack_search_entry:
    print_slimmed_tool(slack_search_entry, "slack.slack_search_messages")

if slack_post_entry:
    print_slimmed_tool(slack_post_entry, "slack.slack_post_message")
