from __future__ import annotations

import httpx
import pytest
import pytest_asyncio

from server.main import app, parse_workflow_tool_policy_list
from server.xpert_runtime.tool_policy import ToolPermissionPolicy


@pytest_asyncio.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as async_client:
        yield async_client


def linear_workflow() -> dict:
    return {
        "id": "draft",
        "title": "linear",
        "nodes": [
            {
                "id": "input",
                "type": "input",
                "data": {
                    "kind": "input",
                    "variableName": "user_input",
                },
            },
            {
                "id": "llm",
                "type": "llm",
                "data": {
                    "kind": "llm",
                    "modelId": "openai/gpt-4o-mini",
                    "prompt": "请回答 {{user_input}}",
                    "outputVariable": "llm_output",
                },
            },
            {
                "id": "output",
                "type": "output",
                "data": {
                    "kind": "output",
                    "outputVariable": "llm_output",
                },
            },
        ],
        "edges": [
            {"id": "e1", "source": "input", "target": "llm"},
            {"id": "e2", "source": "llm", "target": "output"},
        ],
    }


async def validate(client: httpx.AsyncClient, workflow: dict) -> dict:
    response = await client.post(
        "/api/workflow-native/validate",
        json={"workflow": workflow},
    )
    assert response.status_code == 200, response.text
    return response.json()


def issue_codes(data: dict) -> set[str]:
    return {issue["code"] for issue in data["issues"]}


@pytest.mark.asyncio
async def test_valid_linear_workflow_returns_topological_order(
    client: httpx.AsyncClient,
) -> None:
    data = await validate(client, linear_workflow())

    assert data["valid"] is True
    assert data["issues"] == []
    assert data["order"] == ["input", "llm", "output"]


@pytest.mark.asyncio
async def test_missing_input_and_output_nodes_are_structured_issues(
    client: httpx.AsyncClient,
) -> None:
    workflow = {
        "id": "draft",
        "title": "empty",
        "nodes": [],
        "edges": [],
    }

    data = await validate(client, workflow)

    assert data["valid"] is False
    assert {"missing_input_node", "missing_output_node"}.issubset(issue_codes(data))


@pytest.mark.asyncio
async def test_invalid_edge_reference_is_reported(client: httpx.AsyncClient) -> None:
    workflow = linear_workflow()
    workflow["edges"].append({"id": "bad", "source": "input", "target": "missing"})

    data = await validate(client, workflow)

    assert data["valid"] is False
    assert "invalid_edge_reference" in issue_codes(data)


@pytest.mark.asyncio
async def test_cycle_graph_is_rejected(client: httpx.AsyncClient) -> None:
    workflow = linear_workflow()
    workflow["edges"].append({"id": "cycle", "source": "output", "target": "input"})

    data = await validate(client, workflow)

    assert data["valid"] is False
    assert "cycle_detected" in issue_codes(data)


@pytest.mark.asyncio
async def test_llm_missing_model_prompt_and_output_variable(
    client: httpx.AsyncClient,
) -> None:
    workflow = linear_workflow()
    workflow["nodes"][1]["data"] = {"kind": "llm"}

    data = await validate(client, workflow)

    assert data["valid"] is False
    assert {
        "missing_llm_model",
        "missing_llm_prompt",
        "missing_llm_output_variable",
    }.issubset(issue_codes(data))


@pytest.mark.asyncio
async def test_missing_template_and_output_variables_are_reported(
    client: httpx.AsyncClient,
) -> None:
    workflow = linear_workflow()
    workflow["nodes"][1]["data"]["prompt"] = "请回答 {{missing_input}}"
    workflow["nodes"][2]["data"]["outputVariable"] = "missing_output"

    data = await validate(client, workflow)

    assert data["valid"] is False
    assert {
        "missing_template_variable",
        "missing_output_variable_reference",
    }.issubset(issue_codes(data))


@pytest.mark.asyncio
async def test_validate_variable_assign_node(client: httpx.AsyncClient) -> None:
    workflow = linear_workflow()
    workflow["nodes"][1] = {
        "id": "assign",
        "type": "variable_assign",
        "data": {
            "kind": "variable_assign",
            "variableName": "assigned_text",
            "template": "hello {{user_input}}",
        },
    }
    workflow["nodes"][2]["data"]["outputVariable"] = "assigned_text"
    workflow["edges"] = [
        {"id": "e1", "source": "input", "target": "assign"},
        {"id": "e2", "source": "assign", "target": "output"},
    ]

    data = await validate(client, workflow)

    assert data["valid"] is True

    workflow["nodes"][1]["data"].pop("variableName")
    data = await validate(client, workflow)

    assert data["valid"] is False
    assert "missing_variable_assign_name" in issue_codes(data)


@pytest.mark.asyncio
async def test_validate_http_request_required_fields(client: httpx.AsyncClient) -> None:
    workflow = linear_workflow()
    workflow["nodes"][1] = {
        "id": "http",
        "type": "http_request",
        "data": {
            "kind": "http_request",
            "url": "https://example.com?q={{user_input}}",
            "method": "GET",
            "headersJson": "{}",
            "outputVariable": "http_output",
        },
    }
    workflow["nodes"][2]["data"]["outputVariable"] = "http_output"
    workflow["edges"] = [
        {"id": "e1", "source": "input", "target": "http"},
        {"id": "e2", "source": "http", "target": "output"},
    ]

    data = await validate(client, workflow)

    assert data["valid"] is True

    workflow["nodes"][1]["data"]["headersJson"] = "{bad json"
    data = await validate(client, workflow)

    assert data["valid"] is False
    assert "invalid_http_request_headers_json" in issue_codes(data)


@pytest.mark.asyncio
async def test_validate_list_operation_operators(client: httpx.AsyncClient) -> None:
    workflow = linear_workflow()
    workflow["nodes"][1] = {
        "id": "list",
        "type": "list_operation",
        "data": {
            "kind": "list_operation",
            "inputVariable": "user_input",
            "operator": "length",
            "outputVariable": "list_output",
        },
    }
    workflow["nodes"][2]["data"]["outputVariable"] = "list_output"
    workflow["edges"] = [
        {"id": "e1", "source": "input", "target": "list"},
        {"id": "e2", "source": "list", "target": "output"},
    ]

    data = await validate(client, workflow)

    assert data["valid"] is True

    workflow["nodes"][1]["data"]["operator"] = "join"
    data = await validate(client, workflow)

    assert data["valid"] is False
    assert "missing_list_operation_separator" in issue_codes(data)


@pytest.mark.asyncio
async def test_validate_iteration_required_fields(client: httpx.AsyncClient) -> None:
    workflow = linear_workflow()
    workflow["nodes"][1] = {
        "id": "iteration",
        "type": "iteration",
        "data": {
            "kind": "iteration",
            "inputVariable": "user_input",
            "iterationVariable": "item",
            "itemTemplate": "done {{item}}",
            "outputVariable": "iteration_output",
        },
    }
    workflow["nodes"][2]["data"]["outputVariable"] = "iteration_output"
    workflow["edges"] = [
        {"id": "e1", "source": "input", "target": "iteration"},
        {"id": "e2", "source": "iteration", "target": "output"},
    ]

    data = await validate(client, workflow)

    assert data["valid"] is True

    workflow["nodes"][1]["data"].pop("itemTemplate")
    data = await validate(client, workflow)

    assert data["valid"] is False
    assert "missing_iteration_template" in issue_codes(data)


@pytest.mark.asyncio
async def test_validate_template_transform_required(client: httpx.AsyncClient) -> None:
    workflow = linear_workflow()
    workflow["nodes"][1] = {
        "id": "template",
        "type": "template_transform",
        "data": {
            "kind": "template_transform",
            "template": "result={{user_input}}",
            "outputVariable": "template_output",
        },
    }
    workflow["nodes"][2]["data"]["outputVariable"] = "template_output"
    workflow["edges"] = [
        {"id": "e1", "source": "input", "target": "template"},
        {"id": "e2", "source": "template", "target": "output"},
    ]

    data = await validate(client, workflow)

    assert data["valid"] is True

    workflow["nodes"][1]["data"].pop("template")
    data = await validate(client, workflow)

    assert data["valid"] is False
    assert "missing_template_transform_template" in issue_codes(data)


@pytest.mark.asyncio
async def test_validate_variable_aggregator_variables_non_empty(
    client: httpx.AsyncClient,
) -> None:
    workflow = linear_workflow()
    workflow["nodes"][1] = {
        "id": "aggregator",
        "type": "variable_aggregator",
        "data": {
            "kind": "variable_aggregator",
            "variableNames": "user_input",
            "outputTemplate": "{name}={value}\n",
            "outputVariable": "aggregated_output",
        },
    }
    workflow["nodes"][2]["data"]["outputVariable"] = "aggregated_output"
    workflow["edges"] = [
        {"id": "e1", "source": "input", "target": "aggregator"},
        {"id": "e2", "source": "aggregator", "target": "output"},
    ]

    data = await validate(client, workflow)

    assert data["valid"] is True

    workflow["nodes"][1]["data"]["variableNames"] = ""
    data = await validate(client, workflow)

    assert data["valid"] is False
    assert "missing_aggregator_variable_names_empty" in issue_codes(data)


@pytest.mark.asyncio
async def test_validate_parameter_extractor_required_fields(
    client: httpx.AsyncClient,
) -> None:
    workflow = linear_workflow()
    workflow["nodes"][1] = {
        "id": "extractor",
        "type": "parameter_extractor",
        "data": {
            "kind": "parameter_extractor",
            "inputVariable": "user_input",
            "schema": "name, email_address",
            "modelId": "deepseek/deepseek-chat",
            "outputVariable": "parameters_json",
        },
    }
    workflow["nodes"][2]["data"]["outputVariable"] = "parameters_json"
    workflow["edges"] = [
        {"id": "e1", "source": "input", "target": "extractor"},
        {"id": "e2", "source": "extractor", "target": "output"},
    ]

    data = await validate(client, workflow)

    assert data["valid"] is True

    workflow["nodes"][1]["data"].pop("modelId")
    data = await validate(client, workflow)

    assert data["valid"] is False
    assert "missing_parameter_extractor_model_id" in issue_codes(data)


@pytest.mark.asyncio
async def test_validate_knowledge_retrieval_top_k(client: httpx.AsyncClient) -> None:
    workflow = linear_workflow()
    workflow["nodes"][1] = {
        "id": "retrieval",
        "type": "knowledge_retrieval",
        "data": {
            "kind": "knowledge_retrieval",
            "queryVariable": "user_input",
            "top_k": "3",
            "outputVariable": "rag_context",
        },
    }
    workflow["nodes"][2]["data"]["outputVariable"] = "rag_context"
    workflow["edges"] = [
        {"id": "e1", "source": "input", "target": "retrieval"},
        {"id": "e2", "source": "retrieval", "target": "output"},
    ]

    data = await validate(client, workflow)

    assert data["valid"] is True

    workflow["nodes"][1]["data"]["top_k"] = "0"
    data = await validate(client, workflow)

    assert data["valid"] is False
    assert "invalid_knowledge_retrieval_top_k" in issue_codes(data)


@pytest.mark.asyncio
async def test_validate_document_extractor_required_fields(
    client: httpx.AsyncClient,
) -> None:
    workflow = linear_workflow()
    workflow["nodes"][1] = {
        "id": "document",
        "type": "document_extractor",
        "data": {
            "kind": "document_extractor",
            "sourcePathVariable": "user_input",
            "outputVariable": "document_text",
        },
    }
    workflow["nodes"][2]["data"]["outputVariable"] = "document_text"
    workflow["edges"] = [
        {"id": "e1", "source": "input", "target": "document"},
        {"id": "e2", "source": "document", "target": "output"},
    ]

    data = await validate(client, workflow)

    assert data["valid"] is True

    workflow["nodes"][1]["data"].pop("sourcePathVariable")
    data = await validate(client, workflow)

    assert data["valid"] is False
    assert "missing_document_extractor_source_path" in issue_codes(data)


@pytest.mark.asyncio
async def test_validate_human_intervention_required_fields(
    client: httpx.AsyncClient,
) -> None:
    workflow = linear_workflow()
    workflow["nodes"][1] = {
        "id": "human",
        "type": "human_intervention",
        "data": {
            "kind": "human_intervention",
            "prompt": "请确认：{{user_input}}",
            "outputVariable": "human_input",
        },
    }
    workflow["nodes"][2]["data"]["outputVariable"] = "human_input"
    workflow["edges"] = [
        {"id": "e1", "source": "input", "target": "human"},
        {"id": "e2", "source": "human", "target": "output"},
    ]

    data = await validate(client, workflow)

    assert data["valid"] is True

    workflow["nodes"][1]["data"].pop("prompt")
    data = await validate(client, workflow)

    assert data["valid"] is False
    assert "missing_prompt" in issue_codes(data)

    workflow["nodes"][1]["data"]["prompt"] = "请确认：{{user_input}}"
    workflow["nodes"][1]["data"].pop("outputVariable")
    data = await validate(client, workflow)

    assert data["valid"] is False
    assert "missing_output_variable" in issue_codes(data)


@pytest.mark.asyncio
async def test_validate_human_intervention_template_reference(
    client: httpx.AsyncClient,
) -> None:
    workflow = linear_workflow()
    workflow["nodes"][1] = {
        "id": "human",
        "type": "human-in-the-loop",
        "data": {
            "kind": "human-in-the-loop",
            "prompt": "请确认：{{missing_value}}",
            "outputVariable": "human_input",
        },
    }
    workflow["nodes"][2]["data"]["outputVariable"] = "human_input"
    workflow["edges"] = [
        {"id": "e1", "source": "input", "target": "human"},
        {"id": "e2", "source": "human", "target": "output"},
    ]

    data = await validate(client, workflow)

    assert data["valid"] is False
    assert "missing_template_variable" in issue_codes(data)


@pytest.mark.asyncio
async def test_validate_question_classifier_ok(client: httpx.AsyncClient) -> None:
    workflow = linear_workflow()
    workflow["nodes"][1] = {
        "id": "classifier",
        "type": "question_classifier",
        "data": {
            "kind": "question_classifier",
            "inputVariable": "user_input",
            "categories": '{"投诉":["差","投诉","退款"],"咨询":["咨询","如何","怎么"]}',
            "outputVariable": "category",
            "defaultCategory": "未知",
            "matchMode": "contains_any",
            "caseSensitive": "false",
            "useLlmFallback": "false",
        },
    }
    workflow["nodes"][2]["data"]["outputVariable"] = "category"
    workflow["edges"] = [
        {"id": "e1", "source": "input", "target": "classifier"},
        {"id": "e2", "source": "classifier", "target": "output"},
    ]

    data = await validate(client, workflow)

    assert data["valid"] is True


@pytest.mark.asyncio
async def test_validate_question_classifier_invalid_categories_json(
    client: httpx.AsyncClient,
) -> None:
    workflow = linear_workflow()
    workflow["nodes"][1] = {
        "id": "classifier",
        "type": "question_classifier",
        "data": {
            "kind": "question_classifier",
            "inputVariable": "user_input",
            "categories": "{invalid json",
            "outputVariable": "category",
        },
    }
    workflow["nodes"][2]["data"]["outputVariable"] = "category"
    workflow["edges"] = [
        {"id": "e1", "source": "input", "target": "classifier"},
        {"id": "e2", "source": "classifier", "target": "output"},
    ]

    data = await validate(client, workflow)

    assert data["valid"] is False
    assert "invalid_categories_json" in issue_codes(data)


@pytest.mark.asyncio
async def test_validate_mcp_tool_ok_and_invalid_json(
    client: httpx.AsyncClient,
) -> None:
    workflow = linear_workflow()
    workflow["nodes"][1] = {
        "id": "mcp",
        "type": "mcp_tool",
        "data": {
            "kind": "mcp_tool",
            "toolName": "filesystem_read_file",
            "argumentsJson": '{"path":"{{user_input}}"}',
            "outputVariable": "mcp_output",
        },
    }
    workflow["nodes"][2]["data"]["outputVariable"] = "mcp_output"
    workflow["edges"] = [
        {"id": "e1", "source": "input", "target": "mcp"},
        {"id": "e2", "source": "mcp", "target": "output"},
    ]

    data = await validate(client, workflow)

    assert data["valid"] is True

    workflow["nodes"][1]["data"]["argumentsJson"] = "{invalid json"
    data = await validate(client, workflow)

    assert data["valid"] is False
    assert "invalid_arguments_json" in issue_codes(data)


@pytest.mark.asyncio
async def test_validate_time_tool_ok_and_invalid_operation(
    client: httpx.AsyncClient,
) -> None:
    workflow = linear_workflow()
    workflow["nodes"][1] = {
        "id": "time",
        "type": "time_tool",
        "data": {
            "kind": "time_tool",
            "operation": "now_iso",
            "formatString": "%Y-%m-%d %H:%M:%S",
            "outputVariable": "current_time",
        },
    }
    workflow["nodes"][2]["data"]["outputVariable"] = "current_time"
    workflow["edges"] = [
        {"id": "e1", "source": "input", "target": "time"},
        {"id": "e2", "source": "time", "target": "output"},
    ]

    data = await validate(client, workflow)

    assert data["valid"] is True

    workflow["nodes"][1]["data"]["operation"] = "unsupported_op"
    data = await validate(client, workflow)

    assert data["valid"] is False
    assert "invalid_time_operation" in issue_codes(data)


@pytest.mark.asyncio
async def test_validate_agent_ok(client: httpx.AsyncClient) -> None:
    workflow = linear_workflow()
    workflow["nodes"][1] = {
        "id": "agent",
        "type": "agent",
        "data": {
            "kind": "agent",
            "agentMode": "tool_first",
            "instruction": "请处理：{{user_input}}",
            "modelId": "deepseek/deepseek-chat",
            "toolNames": "",
            "outputVariable": "agent_output",
            "maxIterations": "5",
            "temperature": "0.7",
            "promptSuffix": "",
        },
    }
    workflow["nodes"][2]["data"]["outputVariable"] = "agent_output"
    workflow["edges"] = [
        {"id": "e1", "source": "input", "target": "agent"},
        {"id": "e2", "source": "agent", "target": "output"},
    ]

    data = await validate(client, workflow)

    assert data["valid"] is True


@pytest.mark.asyncio
async def test_validate_agent_invalid_mode(client: httpx.AsyncClient) -> None:
    workflow = linear_workflow()
    workflow["nodes"][1] = {
        "id": "agent",
        "type": "agent",
        "data": {
            "kind": "agent",
            "agentMode": "autopilot",
            "instruction": "请处理：{{user_input}}",
            "modelId": "deepseek/deepseek-chat",
            "outputVariable": "agent_output",
        },
    }
    workflow["nodes"][2]["data"]["outputVariable"] = "agent_output"
    workflow["edges"] = [
        {"id": "e1", "source": "input", "target": "agent"},
        {"id": "e2", "source": "agent", "target": "output"},
    ]

    data = await validate(client, workflow)

    assert data["valid"] is False
    assert "invalid_agent_mode" in issue_codes(data)


@pytest.mark.asyncio
async def test_validate_runtime_middleware_ok(client: httpx.AsyncClient) -> None:
    workflow = linear_workflow()
    workflow["nodes"][1] = {
        "id": "middleware",
        "type": "runtime_middleware",
        "data": {
            "kind": "runtime_middleware",
            "title": "系统提示词注入器",
            "description": "运行时中间件原型节点。",
            "runtimeMiddlewareId": "system_prompt_injector",
            "runtimeMiddlewareKind": "runtime_middleware.system_prompt_injector",
            "runtimeMiddlewareConfig": {"system_prompt": "请基于 {{user_input}} 用一句话回答。"},
        },
    }
    workflow["nodes"][2]["data"]["outputVariable"] = "user_input"
    workflow["edges"] = [
        {"id": "e1", "source": "input", "target": "middleware"},
        {"id": "e2", "source": "middleware", "target": "output"},
    ]

    data = await validate(client, workflow)

    assert data["valid"] is True


@pytest.mark.asyncio
async def test_validate_system_prompt_injector_missing_prompt(
    client: httpx.AsyncClient,
) -> None:
    workflow = linear_workflow()
    workflow["nodes"][1] = {
        "id": "middleware",
        "type": "runtime_middleware",
        "data": {
            "kind": "runtime_middleware",
            "runtimeMiddlewareId": "system_prompt_injector",
            "runtimeMiddlewareKind": "runtime_middleware.system_prompt_injector",
            "runtimeMiddlewareConfig": {},
        },
    }
    workflow["nodes"][2]["data"]["outputVariable"] = "user_input"
    workflow["edges"] = [
        {"id": "e1", "source": "input", "target": "middleware"},
        {"id": "e2", "source": "middleware", "target": "output"},
    ]

    data = await validate(client, workflow)

    assert data["valid"] is False
    assert "missing_runtime_middleware_system_prompt" in issue_codes(data)


@pytest.mark.asyncio
async def test_validate_system_prompt_injector_template_reference(
    client: httpx.AsyncClient,
) -> None:
    workflow = linear_workflow()
    workflow["nodes"][1] = {
        "id": "middleware",
        "type": "runtime_middleware",
        "data": {
            "kind": "runtime_middleware",
            "runtimeMiddlewareId": "system_prompt_injector",
            "runtimeMiddlewareKind": "runtime_middleware.system_prompt_injector",
            "runtimeMiddlewareConfig": {
                "system_prompt": "请基于 {{missing_value}} 用一句话回答。",
            },
        },
    }
    workflow["nodes"][2]["data"]["outputVariable"] = "user_input"
    workflow["edges"] = [
        {"id": "e1", "source": "input", "target": "middleware"},
        {"id": "e2", "source": "middleware", "target": "output"},
    ]

    data = await validate(client, workflow)

    assert data["valid"] is False
    assert "missing_runtime_middleware_template_variable" in issue_codes(data)


@pytest.mark.asyncio
async def test_validate_runtime_middleware_missing_metadata(
    client: httpx.AsyncClient,
) -> None:
    workflow = linear_workflow()
    workflow["nodes"][1] = {
        "id": "middleware",
        "type": "runtime_middleware",
        "data": {
            "kind": "runtime_middleware",
            "title": "中间件节点",
        },
    }
    workflow["edges"] = [
        {"id": "e1", "source": "input", "target": "middleware"},
        {"id": "e2", "source": "middleware", "target": "output"},
    ]

    data = await validate(client, workflow)

    assert data["valid"] is False
    codes = issue_codes(data)
    assert "missing_runtime_middleware_id" in codes
    assert "missing_runtime_middleware_kind" in codes


@pytest.mark.asyncio
async def test_valid_tool_policy_middleware(client: httpx.AsyncClient) -> None:
    workflow = linear_workflow()
    workflow["nodes"][1] = {
        "id": "policy",
        "type": "runtime_middleware",
        "data": {
            "kind": "runtime_middleware",
            "runtimeMiddlewareId": "tool_policy",
            "runtimeMiddlewareKind": "runtime_middleware.tool_policy",
            "runtimeMiddlewareConfig": {
                "denied_tools": "bad_tool",
                "allow_by_default": True,
            },
        },
    }
    workflow["nodes"][2]["data"]["outputVariable"] = "user_input"
    workflow["edges"] = [
        {"id": "e1", "source": "input", "target": "policy"},
        {"id": "e2", "source": "policy", "target": "output"},
    ]

    data = await validate(client, workflow)

    assert data["valid"] is True
    assert "invalid_runtime_middleware_tool_policy" not in issue_codes(data)


@pytest.mark.asyncio
async def test_invalid_tool_policy_allow_by_default(
    client: httpx.AsyncClient,
) -> None:
    workflow = linear_workflow()
    workflow["nodes"][1] = {
        "id": "policy",
        "type": "runtime_middleware",
        "data": {
            "kind": "runtime_middleware",
            "runtimeMiddlewareId": "tool_policy",
            "runtimeMiddlewareKind": "runtime_middleware.tool_policy",
            "runtimeMiddlewareConfig": {
                "allow_by_default": "not_a_boolean",
            },
        },
    }
    workflow["nodes"][2]["data"]["outputVariable"] = "user_input"
    workflow["edges"] = [
        {"id": "e1", "source": "input", "target": "policy"},
        {"id": "e2", "source": "policy", "target": "output"},
    ]

    data = await validate(client, workflow)

    assert data["valid"] is False
    assert "invalid_runtime_middleware_tool_policy" in issue_codes(data)


def test_tool_policy_textarea_tool_list_parser() -> None:
    assert parse_workflow_tool_policy_list("fetch\nsearch, read，write") == {
        "fetch",
        "search",
        "read",
        "write",
    }
    assert parse_workflow_tool_policy_list(["fetch", " search "]) == {
        "fetch",
        "search",
    }
    assert parse_workflow_tool_policy_list(None) == set()


def test_tool_policy_denied_tools_rejected() -> None:
    policy = ToolPermissionPolicy(
        denied_tools={"bad_tool"},
        allow_by_default=True,
    )

    assert policy.is_allowed("good_tool") is True
    assert policy.is_allowed("bad_tool") is False
    assert policy.is_allowed("unknown_tool") is True


def test_tool_policy_allow_by_default_false() -> None:
    policy = ToolPermissionPolicy(
        allowed_tools={"good_tool"},
        allow_by_default=False,
    )

    assert policy.is_allowed("good_tool") is True
    assert policy.is_allowed("bad_tool") is False
    assert policy.is_allowed("unknown_tool") is False


@pytest.mark.asyncio
async def test_templates_endpoint_returns_starter_template(
    client: httpx.AsyncClient,
) -> None:
    response = await client.get("/api/workflow-native/templates")

    assert response.status_code == 200, response.text
    data = response.json()
    assert len(data) == 1
    assert data[0]["workflow"]["nodes"]
