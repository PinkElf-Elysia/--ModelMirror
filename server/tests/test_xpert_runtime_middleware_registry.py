from __future__ import annotations

from server.xpert_runtime import (
    RuntimeMiddlewareNode,
    RuntimeMiddlewareRegistry,
    register_builtin_middleware_nodes,
)


def _registry() -> RuntimeMiddlewareRegistry:
    registry = RuntimeMiddlewareRegistry()
    register_builtin_middleware_nodes(registry)
    return registry


def test_registry_list_returns_builtin_nodes() -> None:
    registry = _registry()
    nodes = registry.list()

    node_ids = {node.id for node in nodes}
    assert node_ids == {
        "system_prompt_injector",
        "event_recorder",
        "tool_policy",
        "tool_audit",
        "mcp_tools",
        "context_compression",
        "structured_output",
        "todo_planner",
        "llm_tool_selector",
        "human_in_the_loop",
        "sandbox_files",
        "sandbox_shell",
        "skills_runtime",
        "browser_automation",
        "client_tools",
        "scheduler",
        "ralph_loop",
        "knowledge_writer",
        "plugin_hooks",
    }
    for node in nodes:
        assert node.id
        assert node.kind.startswith("runtime_middleware.")
        assert node.title
        assert node.category
        assert isinstance(node.fields, list)
        assert isinstance(node.metadata, dict)


def test_registry_get_by_id() -> None:
    registry = _registry()
    first = registry.list()[0]

    assert registry.get(first.id) == first
    assert registry.get("nonexistent") is None


def test_registry_categories_returns_unique() -> None:
    registry = _registry()
    categories = registry.categories()

    assert len(categories) == len(set(categories))
    assert "agent" in categories
    assert "tool" in categories


def test_registry_by_category_groups_correctly() -> None:
    registry = _registry()
    grouped = registry.by_category()

    assert isinstance(grouped, dict)
    assert all(isinstance(category, str) for category in grouped)
    assert all(
        isinstance(node, RuntimeMiddlewareNode)
        for nodes in grouped.values()
        for node in nodes
    )
    assert sum(len(nodes) for nodes in grouped.values()) == len(registry.list())
