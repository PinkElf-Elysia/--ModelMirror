import { type Edge, type Node } from "@xyflow/react";

export type WorkflowNodeKind = "input" | "llm" | "condition" | "code" | "output";

export type ConditionOperator = "equals" | "contains";

export type CodeOperation = "upper" | "lower" | "replace" | "concat";

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
  event: "node_start" | "node_delta" | "node_end" | "workflow_end" | "error";
  node_id?: string;
  node_title?: string;
  node_type?: WorkflowNodeKind;
  output?: string;
  variable?: string;
  final_output?: string;
  variables?: Record<string, string>;
  message?: string;
}
