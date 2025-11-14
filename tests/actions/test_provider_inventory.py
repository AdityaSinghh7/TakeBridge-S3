from __future__ import annotations

from mcp_agent.actions import (
    SUPPORTED_PROVIDERS,
    describe_provider_actions,
    get_provider_action_map,
)


def test_supported_providers_are_limited_to_gmail_and_slack():
    provider_map = get_provider_action_map()
    assert set(provider_map.keys()) == set(SUPPORTED_PROVIDERS)
    for funcs in provider_map.values():
        assert funcs, "Each supported provider must expose at least one action."
        for fn in funcs:
            assert callable(fn), "Provider actions must be callable."


def test_provider_descriptions_align_with_supported_inventory():
    catalog = describe_provider_actions()
    assert set(catalog.keys()) == set(SUPPORTED_PROVIDERS)
    for provider in SUPPORTED_PROVIDERS:
        entry = catalog[provider]
        assert entry["provider"] == provider
        assert entry["actions"], f"{provider} should surface wrapper metadata."
