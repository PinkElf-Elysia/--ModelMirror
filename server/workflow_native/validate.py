from __future__ import annotations

import re
import json
from collections import defaultdict, deque
from string import Formatter

from .schemas import (
    NativeWorkflowDefinition,
    NativeWorkflowEdge,
    NativeWorkflowNode,
    ValidationIssue,
    ValidateWorkflowResponse,
)


NODE_KIND_ALIASES = {
    "start": "input",
    "input": "input",
    "user-input": "input",
    "llm": "llm",
    "if-else": "condition",
    "condition": "condition",
    "code": "code",
    "variable_assign": "variable_assign",
    "variable-assign": "variable_assign",
    "variable-assigner": "variable_assign",
    "template_transform": "template_transform",
    "template-transform": "template_transform",
    "variable_aggregator": "variable_aggregator",
    "variable-aggregator": "variable_aggregator",
    "parameter_extractor": "parameter_extractor",
    "parameter-extractor": "parameter_extractor",
    "knowledge_retrieval": "knowledge_retrieval",
    "knowledge-retrieval": "knowledge_retrieval",
    "document_extractor": "document_extractor",
    "document-extractor": "document_extractor",
    "human_intervention": "human_intervention",
    "human-intervention": "human_intervention",
    "human-in-the-loop": "human_intervention",
    "question_classifier": "question_classifier",
    "question-classifier": "question_classifier",
    "agent": "agent",
    "mcp_tool": "mcp_tool",
    "mcp-tool": "mcp_tool",
    "tool": "mcp_tool",
    "time_tool": "time_tool",
    "time-tool": "time_tool",
    "time": "time_tool",
    "http_request": "http_request",
    "http-request": "http_request",
    "list_operation": "list_operation",
    "list-operation": "list_operation",
    "list-operator": "list_operation",
    "iteration": "iteration",
    "end": "output",
    "answer": "output",
    "output": "output",
}

TEMPLATE_PATTERN = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")
SUPPORTED_NODE_KINDS = {
    "input",
    "llm",
    "condition",
    "code",
    "variable_assign",
    "template_transform",
    "variable_aggregator",
    "parameter_extractor",
    "knowledge_retrieval",
    "document_extractor",
    "human_intervention",
    "question_classifier",
    "agent",
    "mcp_tool",
    "time_tool",
    "http_request",
    "list_operation",
    "iteration",
    "output",
}


def node_kind(node: NativeWorkflowNode) -> str:
    """Return a normalized native node kind when possible."""

    data_kind = node.data.get("kind")
    raw_kind = data_kind if isinstance(data_kind, str) else node.type
    if not isinstance(raw_kind, str):
        return ""
    return NODE_KIND_ALIASES.get(raw_kind.strip().lower(), raw_kind.strip().lower())


def validate_workflow_graph(workflow: NativeWorkflowDefinition) -> ValidateWorkflowResponse:
    """Validate a workflow graph without executing any node."""

    issues: list[ValidationIssue] = []
    node_ids: set[str] = set()
    duplicate_ids: set[str] = set()

    for node in workflow.nodes:
        if node.id in node_ids:
            duplicate_ids.add(node.id)
        node_ids.add(node.id)

    for node_id in sorted(duplicate_ids):
        issues.append(
            ValidationIssue(
                code="duplicate_node_id",
                message=f"Node id '{node_id}' is duplicated.",
                node_id=node_id,
            )
        )

    kinds_by_id = {node.id: node_kind(node) for node in workflow.nodes}
    for node in workflow.nodes:
        kind = kinds_by_id[node.id]
        if kind not in SUPPORTED_NODE_KINDS:
            issues.append(
                ValidationIssue(
                    code="unknown_node_kind",
                    message=f"Node '{node.id}' has an unsupported kind.",
                    node_id=node.id,
                )
            )

    if not any(kind == "input" for kind in kinds_by_id.values()):
        issues.append(
            ValidationIssue(
                code="missing_input_node",
                message="Workflow needs at least one input/start node.",
            )
        )

    if not any(kind == "output" for kind in kinds_by_id.values()):
        issues.append(
            ValidationIssue(
                code="missing_output_node",
                message="Workflow needs at least one output/end node.",
            )
        )

    for node in workflow.nodes:
        issues.extend(validate_node_configuration(node, kinds_by_id[node.id]))

    available_variables = collect_declared_variables(workflow.nodes, kinds_by_id)
    for node in workflow.nodes:
        issues.extend(
            validate_variable_references(node, kinds_by_id[node.id], available_variables)
        )

    valid_edges = validate_edges(workflow.edges, node_ids, issues)
    order = topological_order(workflow.nodes, valid_edges, issues)

    has_errors = any(issue.severity == "error" for issue in issues)
    return ValidateWorkflowResponse(
        valid=not has_errors,
        issues=issues,
        order=order if not has_errors else [],
        node_count=len(workflow.nodes),
        edge_count=len(workflow.edges),
    )


def validate_node_configuration(
    node: NativeWorkflowNode,
    kind: str,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    data = node.data

    if kind == "input":
        variable_name = str(data.get("variableName") or "").strip()
        if not variable_name:
            issues.append(
                ValidationIssue(
                    code="missing_input_variable",
                    message="Input node needs data.variableName.",
                    node_id=node.id,
                )
            )
        elif not is_variable_name(variable_name):
            issues.append(
                ValidationIssue(
                    code="invalid_variable_name",
                    message="Input variable name must be an identifier.",
                    node_id=node.id,
                )
            )

    if kind == "llm":
        if not str(data.get("modelId") or "").strip():
            issues.append(
                ValidationIssue(
                    code="missing_llm_model",
                    message="LLM node needs data.modelId.",
                    node_id=node.id,
                )
            )
        prompt = str(data.get("prompt") or "")
        if not prompt.strip():
            issues.append(
                ValidationIssue(
                    code="missing_llm_prompt",
                    message="LLM node needs data.prompt.",
                    node_id=node.id,
                )
            )
        if not str(data.get("outputVariable") or "").strip():
            issues.append(
                ValidationIssue(
                    code="missing_llm_output_variable",
                    message="LLM node needs data.outputVariable.",
                    node_id=node.id,
                )
            )

    if kind == "condition":
        if not str(data.get("conditionVariable") or "").strip():
            issues.append(
                ValidationIssue(
                    code="missing_condition_variable",
                    message="Condition node needs data.conditionVariable.",
                    node_id=node.id,
                )
            )
        if str(data.get("conditionOperator") or "").strip() not in {"equals", "contains"}:
            issues.append(
                ValidationIssue(
                    code="invalid_condition_operator",
                    message="Condition node operator must be equals or contains.",
                    node_id=node.id,
                )
            )
        if data.get("conditionValue") in {None, ""}:
            issues.append(
                ValidationIssue(
                    code="missing_condition_value",
                    message="Condition node needs data.conditionValue.",
                    node_id=node.id,
                )
            )

    if kind == "code":
        operation = str(data.get("codeOperation") or "").strip()
        if operation and operation not in {"upper", "lower", "replace", "concat"}:
            issues.append(
                ValidationIssue(
                    code="invalid_code_operation",
                    message="Code node only supports upper, lower, replace, and concat.",
                    node_id=node.id,
                )
            )

    if kind == "variable_assign":
        variable_name = str(data.get("variableName") or "").strip()
        if not variable_name:
            issues.append(
                ValidationIssue(
                    code="missing_variable_assign_name",
                    message="Variable assignment node needs data.variableName.",
                    node_id=node.id,
                )
            )
        elif not is_variable_name(variable_name):
            issues.append(
                ValidationIssue(
                    code="invalid_variable_assign_name",
                    message="Variable assignment name must be an identifier.",
                    node_id=node.id,
                )
            )
        if not str(data.get("template") or "").strip():
            issues.append(
                ValidationIssue(
                    code="missing_variable_assign_template",
                    message="Variable assignment node needs data.template.",
                    node_id=node.id,
                )
            )

    if kind == "template_transform":
        if not str(data.get("template") or "").strip():
            issues.append(
                ValidationIssue(
                    code="missing_template_transform_template",
                    message="Template transform node needs data.template.",
                    node_id=node.id,
                )
            )
        output_variable = str(data.get("outputVariable") or "").strip()
        if not output_variable:
            issues.append(
                ValidationIssue(
                    code="missing_template_transform_output_variable",
                    message="Template transform node needs data.outputVariable.",
                    node_id=node.id,
                )
            )
        elif not is_variable_name(output_variable):
            issues.append(
                ValidationIssue(
                    code="invalid_template_transform_output_variable",
                    message="Template transform outputVariable must be an identifier.",
                    node_id=node.id,
                )
            )

    if kind == "variable_aggregator":
        variable_names = parse_variable_names(str(data.get("variableNames") or ""))
        if not variable_names:
            issues.append(
                ValidationIssue(
                    code="missing_aggregator_variable_names_empty",
                    message="Variable aggregator needs at least one variable name.",
                    node_id=node.id,
                )
            )
        invalid_names = [name for name in variable_names if not is_variable_name(name)]
        if invalid_names:
            issues.append(
                ValidationIssue(
                    code="invalid_aggregator_variable_name",
                    message=f"Variable aggregator has invalid variable names: {', '.join(invalid_names)}.",
                    node_id=node.id,
                )
            )
        output_variable = str(data.get("outputVariable") or "").strip()
        if not output_variable:
            issues.append(
                ValidationIssue(
                    code="missing_aggregator_output_variable",
                    message="Variable aggregator needs data.outputVariable.",
                    node_id=node.id,
                )
            )
        elif not is_variable_name(output_variable):
            issues.append(
                ValidationIssue(
                    code="invalid_aggregator_output_variable",
                    message="Variable aggregator outputVariable must be an identifier.",
                    node_id=node.id,
                )
            )

    if kind == "parameter_extractor":
        if not str(data.get("inputVariable") or "").strip():
            issues.append(
                ValidationIssue(
                    code="missing_parameter_extractor_input_variable",
                    message="Parameter extractor needs data.inputVariable.",
                    node_id=node.id,
                )
            )
        if not str(data.get("schema") or "").strip():
            issues.append(
                ValidationIssue(
                    code="missing_parameter_extractor_schema",
                    message="Parameter extractor needs data.schema.",
                    node_id=node.id,
                )
            )
        if not str(data.get("modelId") or "").strip():
            issues.append(
                ValidationIssue(
                    code="missing_parameter_extractor_model_id",
                    message="Parameter extractor needs data.modelId.",
                    node_id=node.id,
                )
            )
        output_variable = str(data.get("outputVariable") or "").strip()
        if not output_variable:
            issues.append(
                ValidationIssue(
                    code="missing_parameter_extractor_output_variable",
                    message="Parameter extractor needs data.outputVariable.",
                    node_id=node.id,
                )
            )
        elif not is_variable_name(output_variable):
            issues.append(
                ValidationIssue(
                    code="invalid_parameter_extractor_output_variable",
                    message="Parameter extractor outputVariable must be an identifier.",
                    node_id=node.id,
                )
            )

    if kind == "knowledge_retrieval":
        if not str(data.get("queryVariable") or "").strip():
            issues.append(
                ValidationIssue(
                    code="missing_knowledge_retrieval_query_variable",
                    message="Knowledge retrieval node needs data.queryVariable.",
                    node_id=node.id,
                )
            )
        top_k = str(data.get("top_k") or "3").strip()
        try:
            top_k_int = int(top_k)
        except ValueError:
            top_k_int = 0
        if top_k_int < 1 or top_k_int > 20:
            issues.append(
                ValidationIssue(
                    code="invalid_knowledge_retrieval_top_k",
                    message="Knowledge retrieval top_k must be an integer between 1 and 20.",
                    node_id=node.id,
                )
            )
        output_variable = str(data.get("outputVariable") or "").strip()
        if not output_variable:
            issues.append(
                ValidationIssue(
                    code="missing_knowledge_retrieval_output_variable",
                    message="Knowledge retrieval node needs data.outputVariable.",
                    node_id=node.id,
                )
            )
        elif not is_variable_name(output_variable):
            issues.append(
                ValidationIssue(
                    code="invalid_knowledge_retrieval_output_variable",
                    message="Knowledge retrieval outputVariable must be an identifier.",
                    node_id=node.id,
                )
            )

    if kind == "document_extractor":
        if not str(data.get("sourcePathVariable") or "").strip():
            issues.append(
                ValidationIssue(
                    code="missing_document_extractor_source_path",
                    message="Document extractor needs data.sourcePathVariable.",
                    node_id=node.id,
                )
            )
        output_variable = str(data.get("outputVariable") or "").strip()
        if not output_variable:
            issues.append(
                ValidationIssue(
                    code="missing_document_extractor_output_variable",
                    message="Document extractor needs data.outputVariable.",
                    node_id=node.id,
                )
            )
        elif not is_variable_name(output_variable):
            issues.append(
                ValidationIssue(
                    code="invalid_document_extractor_output_variable",
                    message="Document extractor outputVariable must be an identifier.",
                    node_id=node.id,
                )
            )

    if kind == "human_intervention":
        prompt = str(data.get("prompt") or "").strip()
        if not prompt:
            issues.append(
                ValidationIssue(
                    code="missing_prompt",
                    message="Human intervention node needs data.prompt.",
                    node_id=node.id,
                )
            )
        output_variable = str(data.get("outputVariable") or "").strip()
        if not output_variable:
            issues.append(
                ValidationIssue(
                    code="missing_output_variable",
                    message="Human intervention node needs data.outputVariable.",
                    node_id=node.id,
                )
            )
        elif not is_variable_name(output_variable):
            issues.append(
                ValidationIssue(
                    code="invalid_human_intervention_output_variable",
                    message="Human intervention outputVariable must be an identifier.",
                    node_id=node.id,
                )
            )

    if kind == "question_classifier":
        input_variable = str(data.get("inputVariable") or "").strip()
        if not input_variable:
            issues.append(
                ValidationIssue(
                    code="missing_input_variable",
                    message="Question classifier node needs data.inputVariable.",
                    node_id=node.id,
                )
            )
        elif not is_variable_name(input_variable):
            issues.append(
                ValidationIssue(
                    code="invalid_input_variable",
                    message="Question classifier inputVariable must be an identifier.",
                    node_id=node.id,
                )
            )

        categories_json = str(data.get("categories") or "").strip()
        if not categories_json:
            issues.append(
                ValidationIssue(
                    code="missing_categories",
                    message="Question classifier node needs data.categories.",
                    node_id=node.id,
                )
            )
        else:
            try:
                categories = json.loads(categories_json)
            except ValueError:
                categories = None
                issues.append(
                    ValidationIssue(
                        code="invalid_categories_json",
                        message="Question classifier categories must be valid JSON.",
                        node_id=node.id,
                    )
                )
            if categories is not None:
                valid_schema = isinstance(categories, dict) and bool(categories)
                if valid_schema:
                    for category_name, keywords in categories.items():
                        if not isinstance(category_name, str) or not category_name.strip():
                            valid_schema = False
                            break
                        if not isinstance(keywords, list) or not keywords:
                            valid_schema = False
                            break
                        if not all(
                            isinstance(keyword, str) and keyword.strip()
                            for keyword in keywords
                        ):
                            valid_schema = False
                            break
                if not valid_schema:
                    issues.append(
                        ValidationIssue(
                            code="invalid_categories_schema",
                            message=(
                                "Question classifier categories must be a non-empty "
                                "object of string arrays."
                            ),
                            node_id=node.id,
                        )
                    )

        output_variable = str(data.get("outputVariable") or "").strip()
        if not output_variable:
            issues.append(
                ValidationIssue(
                    code="missing_output_variable",
                    message="Question classifier node needs data.outputVariable.",
                    node_id=node.id,
                )
            )
        elif not is_variable_name(output_variable):
            issues.append(
                ValidationIssue(
                    code="invalid_output_variable",
                    message="Question classifier outputVariable must be an identifier.",
                    node_id=node.id,
                )
            )

        match_mode = str(data.get("matchMode") or "contains_any").strip()
        if match_mode not in {"contains_any", "contains_all"}:
            issues.append(
                ValidationIssue(
                    code="invalid_match_mode",
                    message="Question classifier matchMode must be contains_any or contains_all.",
                    node_id=node.id,
                )
            )

        case_sensitive = str(data.get("caseSensitive") or "false").strip().lower()
        if case_sensitive not in {"true", "false"}:
            issues.append(
                ValidationIssue(
                    code="invalid_case_sensitive",
                    message="Question classifier caseSensitive must be true or false.",
                    node_id=node.id,
                )
            )

        use_llm_fallback = str(data.get("useLlmFallback") or "false").strip().lower()
        if use_llm_fallback not in {"true", "false"}:
            issues.append(
                ValidationIssue(
                    code="invalid_use_llm_fallback",
                    message="Question classifier useLlmFallback must be true or false.",
                    node_id=node.id,
                )
            )
        elif use_llm_fallback == "true" and not str(data.get("modelId") or "").strip():
            issues.append(
                ValidationIssue(
                    code="missing_model_when_fallback",
                    message="Question classifier needs data.modelId when LLM fallback is enabled.",
                    node_id=node.id,
                )
            )

    if kind == "agent":
        instruction = str(data.get("instruction") or "").strip()
        if not instruction:
            issues.append(
                ValidationIssue(
                    code="missing_instruction",
                    message="Agent node needs data.instruction.",
                    node_id=node.id,
                )
            )

        model_id = str(data.get("modelId") or "").strip()
        if not model_id:
            issues.append(
                ValidationIssue(
                    code="missing_model_id",
                    message="Agent node needs data.modelId.",
                    node_id=node.id,
                )
            )

        output_variable = str(data.get("outputVariable") or "").strip()
        if not output_variable:
            issues.append(
                ValidationIssue(
                    code="missing_output_variable",
                    message="Agent node needs data.outputVariable.",
                    node_id=node.id,
                )
            )
        elif not is_variable_name(output_variable):
            issues.append(
                ValidationIssue(
                    code="invalid_output_variable",
                    message="Agent outputVariable must be an identifier.",
                    node_id=node.id,
                )
            )

        agent_mode = str(data.get("agentMode") or "tool_first").strip()
        if agent_mode not in {"tool_first", "direct"}:
            issues.append(
                ValidationIssue(
                    code="invalid_agent_mode",
                    message="Agent agentMode must be tool_first or direct.",
                    node_id=node.id,
                )
            )

        max_iterations = str(data.get("maxIterations") or "").strip()
        if max_iterations:
            try:
                max_iterations_value = int(max_iterations)
            except ValueError:
                max_iterations_value = 0
            if max_iterations_value < 1:
                issues.append(
                    ValidationIssue(
                        code="invalid_max_iterations",
                        message="Agent maxIterations must be a positive integer.",
                        node_id=node.id,
                    )
                )

        temperature = str(data.get("temperature") or "").strip()
        if temperature:
            try:
                temperature_value = float(temperature)
            except ValueError:
                temperature_value = -1.0
            if temperature_value < 0 or temperature_value > 2:
                issues.append(
                    ValidationIssue(
                        code="invalid_temperature",
                        message="Agent temperature must be between 0 and 2.",
                        node_id=node.id,
                    )
                )

    if kind == "mcp_tool":
        tool_name = str(data.get("toolName") or "").strip()
        if not tool_name:
            issues.append(
                ValidationIssue(
                    code="missing_tool_name",
                    message="MCP tool node needs data.toolName.",
                    node_id=node.id,
                )
            )
        arguments_json = str(data.get("argumentsJson") or "").strip()
        if not arguments_json:
            issues.append(
                ValidationIssue(
                    code="missing_arguments",
                    message="MCP tool node needs data.argumentsJson.",
                    node_id=node.id,
                )
            )
        else:
            try:
                parsed_arguments = json.loads(arguments_json)
            except ValueError:
                parsed_arguments = None
            if not isinstance(parsed_arguments, dict):
                issues.append(
                    ValidationIssue(
                        code="invalid_arguments_json",
                        message="MCP tool argumentsJson must be a JSON object.",
                        node_id=node.id,
                    )
                )
        output_variable = str(data.get("outputVariable") or "").strip()
        if not output_variable:
            issues.append(
                ValidationIssue(
                    code="missing_output_variable",
                    message="MCP tool node needs data.outputVariable.",
                    node_id=node.id,
                )
            )
        elif not is_variable_name(output_variable):
            issues.append(
                ValidationIssue(
                    code="invalid_output_variable",
                    message="MCP tool outputVariable must be an identifier.",
                    node_id=node.id,
                )
            )

    if kind == "time_tool":
        operation = str(data.get("operation") or "").strip()
        if not operation:
            issues.append(
                ValidationIssue(
                    code="missing_time_operation",
                    message="Time tool node needs data.operation.",
                    node_id=node.id,
                )
            )
        elif operation not in {"now_iso", "now_epoch", "format"}:
            issues.append(
                ValidationIssue(
                    code="invalid_time_operation",
                    message="Time tool operation must be now_iso, now_epoch, or format.",
                    node_id=node.id,
                )
            )
        output_variable = str(data.get("outputVariable") or "").strip()
        if not output_variable:
            issues.append(
                ValidationIssue(
                    code="missing_output_variable",
                    message="Time tool node needs data.outputVariable.",
                    node_id=node.id,
                )
            )
        elif not is_variable_name(output_variable):
            issues.append(
                ValidationIssue(
                    code="invalid_output_variable",
                    message="Time tool outputVariable must be an identifier.",
                    node_id=node.id,
                )
            )

    if kind == "http_request":
        if not str(data.get("url") or "").strip():
            issues.append(
                ValidationIssue(
                    code="missing_http_request_url",
                    message="HTTP request node needs data.url.",
                    node_id=node.id,
                )
            )
        method = str(data.get("method") or "GET").strip().upper()
        if method not in {"GET", "POST"}:
            issues.append(
                ValidationIssue(
                    code="invalid_http_request_method",
                    message="HTTP request method must be GET or POST.",
                    node_id=node.id,
                )
            )
        headers_json = str(data.get("headersJson") or "").strip()
        if headers_json:
            try:
                parsed_headers = json.loads(headers_json)
            except ValueError:
                parsed_headers = None
            if not isinstance(parsed_headers, dict):
                issues.append(
                    ValidationIssue(
                        code="invalid_http_request_headers_json",
                        message="HTTP request headersJson must be a JSON object.",
                        node_id=node.id,
                    )
                )
        output_variable = str(data.get("outputVariable") or "").strip()
        if not output_variable:
            issues.append(
                ValidationIssue(
                    code="missing_http_request_output_variable",
                    message="HTTP request node needs data.outputVariable.",
                    node_id=node.id,
                )
            )
        elif not is_variable_name(output_variable):
            issues.append(
                ValidationIssue(
                    code="invalid_http_request_output_variable",
                    message="HTTP request outputVariable must be an identifier.",
                    node_id=node.id,
                )
            )

    if kind == "list_operation":
        if not str(data.get("inputVariable") or "").strip():
            issues.append(
                ValidationIssue(
                    code="missing_list_operation_input_variable",
                    message="List operation node needs data.inputVariable.",
                    node_id=node.id,
                )
            )
        operator = str(data.get("operator") or "").strip()
        if operator not in {"length", "join", "first", "last"}:
            issues.append(
                ValidationIssue(
                    code="invalid_list_operation_operator",
                    message="List operation operator must be length, join, first, or last.",
                    node_id=node.id,
                )
            )
        if operator == "join" and data.get("joinSeparator") in {None, ""}:
            issues.append(
                ValidationIssue(
                    code="missing_list_operation_separator",
                    message="Join list operation needs data.joinSeparator.",
                    node_id=node.id,
                )
            )
        output_variable = str(data.get("outputVariable") or "").strip()
        if not output_variable:
            issues.append(
                ValidationIssue(
                    code="missing_list_operation_output_variable",
                    message="List operation node needs data.outputVariable.",
                    node_id=node.id,
                )
            )
        elif not is_variable_name(output_variable):
            issues.append(
                ValidationIssue(
                    code="invalid_list_operation_output_variable",
                    message="List operation outputVariable must be an identifier.",
                    node_id=node.id,
                )
            )

    if kind == "iteration":
        if not str(data.get("inputVariable") or "").strip():
            issues.append(
                ValidationIssue(
                    code="missing_iteration_input_variable",
                    message="Iteration node needs data.inputVariable.",
                    node_id=node.id,
                )
            )
        iteration_variable = str(data.get("iterationVariable") or "").strip()
        if not iteration_variable:
            issues.append(
                ValidationIssue(
                    code="missing_iteration_variable",
                    message="Iteration node needs data.iterationVariable.",
                    node_id=node.id,
                )
            )
        elif not is_variable_name(iteration_variable):
            issues.append(
                ValidationIssue(
                    code="invalid_iteration_variable",
                    message="Iteration variable must be an identifier.",
                    node_id=node.id,
                )
            )
        if not str(data.get("itemTemplate") or "").strip():
            issues.append(
                ValidationIssue(
                    code="missing_iteration_template",
                    message="Iteration node needs data.itemTemplate.",
                    node_id=node.id,
                )
            )
        output_variable = str(data.get("outputVariable") or "").strip()
        if not output_variable:
            issues.append(
                ValidationIssue(
                    code="missing_iteration_output_variable",
                    message="Iteration node needs data.outputVariable.",
                    node_id=node.id,
                )
            )
        elif not is_variable_name(output_variable):
            issues.append(
                ValidationIssue(
                    code="invalid_iteration_output_variable",
                    message="Iteration outputVariable must be an identifier.",
                    node_id=node.id,
                )
            )

    if kind == "output":
        output_variable = str(data.get("outputVariable") or "").strip()
        if not output_variable:
            issues.append(
                ValidationIssue(
                    code="missing_output_variable",
                    message="Output node needs data.outputVariable.",
                    node_id=node.id,
                )
            )

    return issues


def collect_declared_variables(
    nodes: list[NativeWorkflowNode],
    kinds_by_id: dict[str, str],
) -> set[str]:
    variables: set[str] = set()

    for node in nodes:
        data = node.data
        kind = kinds_by_id[node.id]
        if kind == "input":
            variable = str(data.get("variableName") or "").strip()
            if is_variable_name(variable):
                variables.add(variable)
        if kind == "llm":
            variable = str(data.get("outputVariable") or "").strip()
            if is_variable_name(variable):
                variables.add(variable)
        if kind == "code":
            variable = str(data.get("codeOutputVariable") or "").strip()
            if is_variable_name(variable):
                variables.add(variable)
        if kind == "variable_assign":
            variable = str(data.get("variableName") or "").strip()
            if is_variable_name(variable):
                variables.add(variable)
        if kind in {
            "template_transform",
            "variable_aggregator",
            "parameter_extractor",
            "knowledge_retrieval",
            "document_extractor",
            "human_intervention",
            "question_classifier",
            "agent",
            "mcp_tool",
            "time_tool",
            "http_request",
            "list_operation",
            "iteration",
        }:
            variable = str(data.get("outputVariable") or "").strip()
            if is_variable_name(variable):
                variables.add(variable)

    return variables


def validate_variable_references(
    node: NativeWorkflowNode,
    kind: str,
    available_variables: set[str],
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    data = node.data

    if kind == "llm":
        prompt = str(data.get("prompt") or "")
        for variable in sorted(extract_template_variables(prompt)):
            if variable not in available_variables:
                issues.append(
                    ValidationIssue(
                        code="missing_template_variable",
                        message=f"Prompt references undefined variable '{variable}'.",
                        node_id=node.id,
                    )
                )

    if kind == "condition":
        variable = str(data.get("conditionVariable") or "").strip()
        if variable and variable not in available_variables:
            issues.append(
                ValidationIssue(
                    code="missing_condition_variable_reference",
                    message=f"Condition references undefined variable '{variable}'.",
                    node_id=node.id,
                )
            )

    if kind == "output":
        variable = str(data.get("outputVariable") or "").strip()
        if variable and variable not in available_variables:
            issues.append(
                ValidationIssue(
                    code="missing_output_variable_reference",
                    message=f"Output references undefined variable '{variable}'.",
                    node_id=node.id,
                )
            )

    if kind == "variable_assign":
        template = str(data.get("template") or "")
        for variable in sorted(extract_template_variables(template)):
            if variable not in available_variables:
                issues.append(
                    ValidationIssue(
                        code="missing_template_variable",
                        message=f"Template references undefined variable '{variable}'.",
                        node_id=node.id,
                    )
                )

    if kind == "http_request":
        url = str(data.get("url") or "")
        for variable in sorted(extract_template_variables(url)):
            if variable not in available_variables:
                issues.append(
                    ValidationIssue(
                        code="missing_template_variable",
                        message=f"HTTP URL references undefined variable '{variable}'.",
                        node_id=node.id,
                    )
                )
        body_variable = str(data.get("bodyVariable") or "").strip()
        if body_variable and body_variable not in available_variables:
            issues.append(
                ValidationIssue(
                    code="missing_http_request_body_variable_reference",
                    message=f"HTTP bodyVariable references undefined variable '{body_variable}'.",
                    node_id=node.id,
                )
            )

    if kind == "template_transform":
        template = str(data.get("template") or "")
        for variable in sorted(extract_template_variables(template)):
            if variable not in available_variables:
                issues.append(
                    ValidationIssue(
                        code="missing_template_variable",
                        message=f"Template transform references undefined variable '{variable}'.",
                        node_id=node.id,
                    )
                )

    if kind == "variable_aggregator":
        for variable in parse_variable_names(str(data.get("variableNames") or "")):
            if is_variable_name(variable) and variable not in available_variables:
                issues.append(
                    ValidationIssue(
                        code="missing_aggregator_variable_reference",
                        message=f"Variable aggregator references undefined variable '{variable}'.",
                        node_id=node.id,
                    )
                )

    if kind == "parameter_extractor":
        input_variable = str(data.get("inputVariable") or "").strip()
        if input_variable and input_variable not in available_variables:
            issues.append(
                ValidationIssue(
                    code="missing_parameter_extractor_input_variable_reference",
                    message=f"Parameter extractor references undefined variable '{input_variable}'.",
                    node_id=node.id,
                )
            )

    if kind == "knowledge_retrieval":
        query_variable = str(data.get("queryVariable") or "").strip()
        if query_variable and query_variable not in available_variables:
            issues.append(
                ValidationIssue(
                    code="missing_knowledge_retrieval_query_variable_reference",
                    message=f"Knowledge retrieval references undefined variable '{query_variable}'.",
                    node_id=node.id,
                )
            )

    if kind == "document_extractor":
        source_path_variable = str(data.get("sourcePathVariable") or "").strip()
        if source_path_variable and source_path_variable not in available_variables:
            issues.append(
                ValidationIssue(
                    code="missing_document_extractor_source_path_reference",
                    message=f"Document extractor references undefined variable '{source_path_variable}'.",
                    node_id=node.id,
                )
            )

    if kind == "human_intervention":
        prompt = str(data.get("prompt") or "")
        for variable in sorted(extract_template_variables(prompt)):
            if variable not in available_variables:
                issues.append(
                    ValidationIssue(
                        code="missing_template_variable",
                        message=f"Human intervention prompt references undefined variable '{variable}'.",
                        node_id=node.id,
                    )
                )

    if kind == "question_classifier":
        input_variable = str(data.get("inputVariable") or "").strip()
        if input_variable and input_variable not in available_variables:
            issues.append(
                ValidationIssue(
                    code="missing_question_classifier_input_variable_reference",
                    message=(
                        "Question classifier references undefined inputVariable "
                        f"'{input_variable}'."
                    ),
                    node_id=node.id,
                )
            )
        fallback_prompt = str(data.get("llmFallbackPrompt") or "")
        for variable in sorted(extract_template_variables(fallback_prompt)):
            if variable not in available_variables:
                issues.append(
                    ValidationIssue(
                        code="missing_template_variable",
                        message=(
                            "Question classifier fallback prompt references "
                            f"undefined variable '{variable}'."
                        ),
                        node_id=node.id,
                    )
                )

    if kind == "agent":
        instruction = str(data.get("instruction") or "")
        for variable in sorted(extract_template_variables(instruction)):
            if variable not in available_variables:
                issues.append(
                    ValidationIssue(
                        code="missing_template_variable",
                        message=f"Agent instruction references undefined variable '{variable}'.",
                        node_id=node.id,
                    )
                )
        prompt_suffix = str(data.get("promptSuffix") or "")
        for variable in sorted(extract_template_variables(prompt_suffix)):
            if variable not in available_variables:
                issues.append(
                    ValidationIssue(
                        code="missing_template_variable",
                        message=f"Agent promptSuffix references undefined variable '{variable}'.",
                        node_id=node.id,
                    )
                )

    if kind == "mcp_tool":
        arguments_json = str(data.get("argumentsJson") or "")
        for variable in sorted(extract_template_variables(arguments_json)):
            if variable not in available_variables:
                issues.append(
                    ValidationIssue(
                        code="missing_template_variable",
                        message=(
                            "MCP tool argumentsJson references undefined variable "
                            f"'{variable}'."
                        ),
                        node_id=node.id,
                    )
                )

    if kind == "list_operation":
        input_variable = str(data.get("inputVariable") or "").strip()
        if input_variable and input_variable not in available_variables:
            issues.append(
                ValidationIssue(
                    code="missing_list_operation_input_variable_reference",
                    message=f"List operation references undefined variable '{input_variable}'.",
                    node_id=node.id,
                )
            )

    if kind == "iteration":
        input_variable = str(data.get("inputVariable") or "").strip()
        if input_variable and input_variable not in available_variables:
            issues.append(
                ValidationIssue(
                    code="missing_iteration_input_variable_reference",
                    message=f"Iteration references undefined variable '{input_variable}'.",
                    node_id=node.id,
                )
            )
        iteration_variable = str(data.get("iterationVariable") or "").strip()
        template_variables = extract_template_variables(str(data.get("itemTemplate") or ""))
        scoped_variables = set(available_variables)
        if is_variable_name(iteration_variable):
            scoped_variables.add(iteration_variable)
        for variable in sorted(template_variables):
            if variable not in scoped_variables:
                issues.append(
                    ValidationIssue(
                        code="missing_template_variable",
                        message=f"Iteration template references undefined variable '{variable}'.",
                        node_id=node.id,
                    )
                )

    return issues


def validate_edges(
    edges: list[NativeWorkflowEdge],
    node_ids: set[str],
    issues: list[ValidationIssue],
) -> list[NativeWorkflowEdge]:
    valid_edges: list[NativeWorkflowEdge] = []

    for edge in edges:
        source_missing = edge.source not in node_ids
        target_missing = edge.target not in node_ids
        if source_missing or target_missing:
            issues.append(
                ValidationIssue(
                    code="invalid_edge_reference",
                    message="Edge references a missing source or target node.",
                    edge_id=edge.id,
                )
            )
            continue
        valid_edges.append(edge)

    return valid_edges


def topological_order(
    nodes: list[NativeWorkflowNode],
    edges: list[NativeWorkflowEdge],
    issues: list[ValidationIssue],
) -> list[str]:
    node_ids = {node.id for node in nodes}
    indegree = {node.id: 0 for node in nodes}
    outgoing: dict[str, list[str]] = defaultdict(list)

    for edge in edges:
        if edge.source not in node_ids or edge.target not in node_ids:
            continue
        outgoing[edge.source].append(edge.target)
        indegree[edge.target] += 1

    queue = deque(node_id for node_id, degree in indegree.items() if degree == 0)
    order: list[str] = []

    while queue:
        node_id = queue.popleft()
        order.append(node_id)
        for target_id in outgoing[node_id]:
            indegree[target_id] -= 1
            if indegree[target_id] == 0:
                queue.append(target_id)

    if len(order) != len(nodes):
        issues.append(
            ValidationIssue(
                code="cycle_detected",
                message="Workflow graph contains a cycle.",
            )
        )
        return []

    return order


def extract_template_variables(template: str) -> set[str]:
    """Return variables referenced through the classic {{ variable }} syntax."""

    try:
        formatter_variables = {
            field_name
            for _, field_name, _, _ in Formatter().parse(template)
            if field_name and is_variable_name(field_name)
        }
    except ValueError:
        formatter_variables = set()
    moustache_variables = {
        match.group(1).strip() for match in TEMPLATE_PATTERN.finditer(template)
    }
    return formatter_variables | moustache_variables


def is_variable_name(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value))


def parse_variable_names(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]
