"""Xpert-aligned runtime foundation for ModelMirror.

The package intentionally stays framework-agnostic. FastAPI routes, workflow
nodes, MCP tools, and future multi-agent runners can depend on these small
runtime primitives without adding more orchestration logic to ``server/main.py``.
"""

from .capabilities import CapabilityRegistry, RuntimeCapability
from .agent_tasks import AgentHandoff, AgentTask, AgentTaskStore
from .defaults import create_default_runtime, event_recorder, system_prompt_injector
from .events import RuntimeEventStore
from .middleware import AgentMiddleware, MiddlewarePipeline
from .middleware_registry import (
    RuntimeMiddlewareField,
    RuntimeMiddlewareNode,
    RuntimeMiddlewareRegistry,
    register_builtin_middleware_nodes,
    runtime_middleware_registry,
)
from .workflow_node_registry import (
    KnowledgePipelinePalette,
    WorkflowNodeRegistry,
    WorkflowPaletteItem,
    WorkflowPalettePlaceholder,
    WorkflowPaletteSection,
    WorkflowPaletteTab,
    register_builtin_workflow_nodes,
    workflow_node_registry,
)
from .models import (
    MiddlewareContext,
    ModelCallRequest,
    ModelCallResponse,
    RuntimeEvent,
    RuntimeTask,
    ToolCallRequest,
    ToolCallResponse,
)
from .run_registry import (
    RunRegistry,
    RuntimeRun,
    RuntimeRunCheckpoint,
    RuntimeRunStatus,
    RuntimeRunType,
)
from .tool_policy import (
    InMemoryToolAuditStore,
    ToolAuditRecord,
    ToolAuditStatus,
    ToolPermissionPolicy,
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
from .tool_runner import run_tool_with_runtime

__all__ = [
    "AgentMiddleware",
    "AgentHandoff",
    "AgentTask",
    "AgentTaskStore",
    "CapabilityRegistry",
    "create_default_runtime",
    "event_recorder",
    "InMemoryToolAuditStore",
    "MCPToolsetProvider",
    "MiddlewareContext",
    "MiddlewarePipeline",
    "ModelCallRequest",
    "ModelCallResponse",
    "RuntimeCapability",
    "RuntimeEvent",
    "RuntimeEventStore",
    "RuntimeMiddlewareField",
    "RuntimeMiddlewareNode",
    "RuntimeMiddlewareRegistry",
    "WorkflowNodeRegistry",
    "WorkflowPaletteItem",
    "WorkflowPalettePlaceholder",
    "WorkflowPaletteSection",
    "WorkflowPaletteTab",
    "KnowledgePipelinePalette",
    "RuntimeRun",
    "RuntimeRunCheckpoint",
    "RuntimeRunStatus",
    "RuntimeRunType",
    "RuntimeTask",
    "RuntimeTool",
    "RuntimeToolCall",
    "RuntimeToolError",
    "RuntimeToolResult",
    "run_tool_with_runtime",
    "RunRegistry",
    "runtime_middleware_registry",
    "workflow_node_registry",
    "system_prompt_injector",
    "ToolCallRequest",
    "ToolCallResponse",
    "ToolAuditRecord",
    "ToolAuditStatus",
    "ToolsetProvider",
    "ToolPermissionPolicy",
    "register_builtin_middleware_nodes",
    "register_builtin_workflow_nodes",
    "register_mcp_toolset_capability",
]
