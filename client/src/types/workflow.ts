import { type Edge, type Node } from "@xyflow/react";

export type WorkflowNodeKind =
  | "input"
  | "llm"
  | "condition"
  | "code"
  | "variable_assign"
  | "template_transform"
  | "variable_aggregator"
  | "parameter_extractor"
  | "knowledge_retrieval"
  | "document_extractor"
  | "human_intervention"
  | "http_request"
  | "list_operation"
  | "iteration"
  | "output";

export type ConditionOperator = "equals" | "contains";

export type CodeOperation = "upper" | "lower" | "replace" | "concat";

export type HttpRequestMethod = "GET" | "POST";

export type ListOperationOperator = "length" | "join" | "first" | "last";

export interface WorkflowNodeData extends Record<string, unknown> {
  kind: WorkflowNodeKind;
  title: string;
  description: string;
  variableName?: string;
  modelId?: string;
  prompt?: string;
  outputVariable?: string;
  conditionVariable?: string;
  conditionOperator?: ConditionOperator;
  conditionValue?: string;
  codeOperation?: CodeOperation;
  codeInputVariable?: string;
  codeOutputVariable?: string;
  replaceFrom?: string;
  replaceTo?: string;
  concatValue?: string;
  template?: string;
  variableNames?: string;
  outputTemplate?: string;
  schema?: string;
  queryVariable?: string;
  top_k?: string;
  sourcePathVariable?: string;
  url?: string;
  method?: HttpRequestMethod;
  headersJson?: string;
  bodyVariable?: string;
  inputVariable?: string;
  operator?: ListOperationOperator;
  joinSeparator?: string;
  iterationVariable?: string;
  itemTemplate?: string;
}

export type WorkflowNode = Node<WorkflowNodeData, "workflowNode">;

export type WorkflowEdge = Edge;

export interface WorkflowDefinition {
  id: string;
  title: string;
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
  updatedAt: string;
}

export interface WorkflowRunEvent {
  event:
    | "workflow_meta"
    | "node_start"
    | "node_delta"
    | "human_intervention_pending"
    | "heartbeat"
    | "node_end"
    | "workflow_end"
    | "error";
  task_id?: string;
  node_id?: string;
  node_title?: string;
  node_type?: WorkflowNodeKind;
  prompt?: string;
  output?: string;
  output_variable?: string;
  variable?: string;
  final_output?: string;
  variables?: Record<string, string>;
  message?: string;
  at?: number;
}
