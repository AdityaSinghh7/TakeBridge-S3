from __future__ import annotations

import argparse
import json
from functools import partial
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml  # type: ignore[import]

from mcp_agent.dev import resolve_dev_user
from mcp_agent.core.context import AgentContext
from mcp_agent.registry.oauth import OAuthManager
from mcp_agent.actions import SUPPORTED_PROVIDERS, get_provider_action_map
from mcp_agent.knowledge.introspection import get_tool_spec, ensure_io_specs_loaded
from mcp_agent.knowledge.output_schema_sampler import sample_output_schema_for_wrapper


def init_registry(user_id: str) -> AgentContext:
    """
    Compatibility shim: create an AgentContext for the user.

    The legacy registry initializer mutated global state; the current code
    uses functional helpers, so we just return a context for callers that need it.
    """
    return AgentContext.create(user_id)


def get_configured_providers(user_id: str) -> set[str]:
    """
    Determine which providers are authorized/configured for this user.

    Uses OAuthManager.auth_status to mirror runtime availability checks.
    """
    ctx = AgentContext.create(user_id)
    configured: set[str] = set()
    for provider in SUPPORTED_PROVIDERS:
        status = OAuthManager.auth_status(ctx, provider)
        if status.get("authorized"):
            configured.add(provider)
    return configured


def _parse_examples_block(entry: Dict[str, Any], key: str) -> List[Dict[str, Any]]:
    """
    Parse a success_examples/error_examples style block into a list of arg dicts.

    Accepts either:
      key: { args: {...} } or
      key: [ { args: {...} }, ... ]
    """
    raw = entry.get(key)
    examples: List[Dict[str, Any]] = []
    if isinstance(raw, dict):
        args = raw.get("args") or {}
        if isinstance(args, dict):
            examples.append(args)
    elif isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            args = item.get("args") or {}
            if isinstance(args, dict):
                examples.append(args)
    return examples


def main() -> None:
    """
    Generate coarse JSON-schema-like output descriptions for tools using
    manually provided example payloads.

    Live mode (default): expects real MCP providers (OAuth + MCP URLs) and
    samples real payloads where configured. Tools whose providers are not
    configured can be skipped via --skip-unconfigured.

    Fake mode: when MCP_FAKE_CLIENT_FACTORY is set, the registry will install
    fake clients instead of real MCP clients. This is useful for tests and
    local experimentation but should not be used to produce committed schema
    files.
    """

    parser = argparse.ArgumentParser(description="Generate tool output schemas from live MCP tool calls.")
    parser.add_argument(
        "--user-id",
        help="User id for MCP registry/OAuth (defaults to dev-local resolution).",
        default=None,
    )
    parser.add_argument(
        "--providers",
        help="Comma-separated list of providers to sample (default: all present in YAML).",
        default=None,
    )
    parser.add_argument(
        "--skip-unconfigured",
        action="store_true",
        help="Skip tools whose provider is not configured for this user.",
    )
    parser.add_argument(
        "--allow-mutating",
        action="store_true",
        help="Allow sampling mutating tools (mode=mutate). Use only in dev/test accounts.",
    )
    args = parser.parse_args()

    config_path = Path("tool_output_samples.yaml")
    if not config_path.exists():
        raise SystemExit("tool_output_samples.yaml not found; create it before generating schemas.")

    # Resolve user and registry state.
    user_id = resolve_dev_user(args.user_id)
    init_registry(user_id)
    configured_providers = get_configured_providers(user_id)

    allowed_providers: Optional[set[str]] = None
    if args.providers:
        allowed_providers = {p.strip() for p in str(args.providers).split(",") if p.strip()}

    # Ensure IoToolSpecs are registered (from action docstrings) before we look
    # up specs for individual tools.
    ensure_io_specs_loaded()
    context = AgentContext.create(user_id)
    action_map = get_provider_action_map()

    cfg = yaml.safe_load(config_path.read_text()) or {}
    schemas: Dict[str, Dict[str, Any]] = {}

    for key, entry in cfg.items():
        if not isinstance(entry, dict):
            continue
        if entry.get("skip"):
            continue

        try:
            provider, tool_name = key.split(".", 1)
        except ValueError:
            print(f"[schema] Skipping {key!r}: expected 'provider.tool_name' key.")
            continue

        if allowed_providers is not None and provider not in allowed_providers:
            continue

        mode = str(entry.get("mode", "read")).lower()
        if mode == "mutate" and not args.allow_mutating:
            print(f"[schema] Skipping mutating tool {key!r} (mode=mutate).")
            continue

        if args.skip_unconfigured and provider not in configured_providers:
            print(
                f"[schema] Skipping {key!r}: provider '{provider}' not configured for user {user_id}."
            )
            continue

        spec = get_tool_spec(provider, tool_name)
        if spec is None:
            print(f"[schema] Skipping {key!r}: no IoToolSpec registered.")
            continue
        if spec.func is None:
            func = next((f for f in action_map.get(provider, ()) if f.__name__ == tool_name), None)
            if func:
                # Bind the AgentContext so sampler can call the wrapper directly.
                spec.func = partial(func, context)
            else:
                print(f"[schema] Skipping {key!r}: no wrapper function found to sample.")
                continue

        # Prefer success_examples/error_examples, but accept legacy success/error blocks.
        success_examples = _parse_examples_block(entry, "success_examples")
        error_examples = _parse_examples_block(entry, "error_examples")
        if not success_examples and not error_examples:
            # Legacy keys: success / error
            legacy_success = _parse_examples_block(entry, "success")
            legacy_error = _parse_examples_block(entry, "error")
            success_examples.extend(legacy_success)
            error_examples.extend(legacy_error)

        if not success_examples and not error_examples:
            print(f"[schema] Skipping {key!r}: no example args configured.")
            continue

        schema = sample_output_schema_for_wrapper(
            spec.func,
            success_examples,
            error_examples or None,
            provider=provider,
            tool_name=tool_name,
        )
        if schema:
            schemas[key] = schema

    if not schemas:
        print("No schemas inferred; ensure tool_output_samples.yaml is populated and IoToolSpecs are registered.")
        return

    out_path = Path("tool_output_schemas.generated.json")
    
    # Load existing schemas if file exists
    existing_schemas: Dict[str, Dict[str, Any]] = {}
    if out_path.exists():
        try:
            existing_schemas = json.loads(out_path.read_text(encoding="utf-8"))
            if not isinstance(existing_schemas, dict):
                existing_schemas = {}
        except Exception as e:
            print(f"[schema] Warning: Could not parse existing schema file: {e}. Starting fresh.")
            existing_schemas = {}
    
    # If providers filter is specified, remove existing schemas for those providers
    if allowed_providers:
        keys_to_remove = [
            key for key in existing_schemas.keys()
            if key.split(".", 1)[0] in allowed_providers
        ]
        for key in keys_to_remove:
            existing_schemas.pop(key, None)
        if keys_to_remove:
            print(f"[schema] Removed {len(keys_to_remove)} existing schema(s) for provider(s): {', '.join(allowed_providers)}")
    
    # Merge new schemas with existing ones
    merged_schemas = {**existing_schemas, **schemas}
    
    out_path.write_text(json.dumps(merged_schemas, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote inferred schemas for {len(schemas)} tool(s) to {out_path}")
    if existing_schemas:
        total_count = len(merged_schemas)
        print(f"Total schemas in file: {total_count} (kept {total_count - len(schemas)} from other providers)")


if __name__ == "__main__":
    main()
