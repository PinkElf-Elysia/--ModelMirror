"""Xpert-aligned runtime foundation for ModelMirror.

The package intentionally stays framework-agnostic. FastAPI routes, workflow
nodes, MCP tools, and future multi-agent runners can depend on these small
runtime primitives without adding more orchestration logic to ``server/main.py``.
"""

from .capabilities import CapabilityRegistry, RuntimeCapability
from .defaults import create_default_runtime, event_recorder, system_prompt_injector
from .events import RuntimeEventStore
from .middleware import AgentMiddleware, MiddlewarePipeline
from .models import (
    MiddlewareContext,
    ModelCallRequest,
    ModelCallResponse,
    RuntimeEvent,
    RuntimeTask,
    ToolCallRequest,
    ToolCallResponse,
)
from .toolset import (
    MCPToolsetProvider,
    RuntimeTool,
    RuntimeToolCall,
    RuntimeToolError,
    RuntimeToolResult,
    ToolsetProvider,
    register_mcp_toolset_capability,
)

__all__ = [
    "AgentMiddleware",
    "CapabilityRegistry",
    "create_default_runtime",
    "event_recorder",
    "MCPToolsetProvider",
    "MiddlewareContext",
    "MiddlewarePipeline",
    "ModelCallRequest",
    "ModelCallResponse",
    "RuntimeCapability",
    "RuntimeEvent",
    "RuntimeEventStore",
    "RuntimeTask",
    "RuntimeTool",
    "RuntimeToolCall",
    "RuntimeToolError",
    "RuntimeToolResult",
    "system_prompt_injector",
    "ToolCallRequest",
    "ToolCallResponse",
    "ToolsetProvider",
    "register_mcp_toolset_capability",
]
