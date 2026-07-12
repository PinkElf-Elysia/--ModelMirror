# Xpert Runtime Contract

Last updated: 2026-07-10

## Purpose

This document describes the first ModelMirror-native Xpert publishing contract. It aligns with Xpert concepts while retaining the repository's React, FastAPI, Pydantic, pytest, and classic workflow runner architecture.

The implementation does not copy Xpert source code or migrate its Angular, NestJS, Nx, or persistence stack.

## Resource Model

The server/xperts package owns a file-backed XpertStore. Its default storage location is server/xperts/storage/xperts.json, overridable through XPERT_STORAGE_DIR.

- XpertDefinition: identity, slug, name, description, tags, starter prompts, status, draft revision, and published-version pointer.
- XpertDraft: editable workflow snapshot plus the chat input, history, and output variable names.
- XpertVersion: immutable published workflow snapshot, version number, draft revision, release notes, checksum, and timestamp.

The Store uses an in-process lock and atomic temporary-file replacement. It is deliberately an adapter boundary: a future database migration must keep the API contract stable.

## Lifecycle

1. Create a draft Xpert with the default chat workflow: input(user_input) -> workflow_agent(agent_output) -> output(agent_output).
2. Edit and save the draft. Every save increments draft_revision.
3. Request validation. The server runs the existing graph validator plus the Xpert chat contract.
4. Publish. The server verifies the revision did not change during preflight, then records an immutable version.
5. Run a published version. The server injects the current user message and a bounded conversation-history JSON summary, then delegates to the existing classic workflow runner.

Draft updates never mutate a published snapshot. Archived Xperts remain inspectable but cannot run.

## Publish Contract

The first chat release requires:

- exactly one input node whose variable matches input_variable;
- exactly one output node whose variable matches output_variable;
- at least one workflow_agent with modelId, rolePrompt, taskInput, and outputVariable;
- reachable template variables, except the configured history variable injected by the published-chat runtime;
- no human_intervention node, because the v1 chat entry has no pause/resume UI.

Existing middleware, MCP Toolset, knowledge, AgentTask, Handoff, and RunRegistry validation remains in force.

## Public API

- GET /api/xperts?status=&search=&limit=
- POST /api/xperts
- GET /api/xperts/{xpert_id}
- PATCH /api/xperts/{xpert_id}
- POST /api/xperts/{xpert_id}/validate
- POST /api/xperts/{xpert_id}/publish
- GET /api/xperts/{xpert_id}/versions
- GET /api/xperts/{xpert_id}/versions/{version}
- POST /api/xperts/{xpert_id}/run

List responses expose summaries only. Detail and version endpoints expose the workflow only when it is required for editing or version inspection.

## Execution and Observability

Published runs use run_type=xpert and the same SSE event family as classic workflow execution:

- workflow_meta
- node_start
- node_delta
- node_end
- workflow_end
- error

For Xpert runs, workflow_meta also exposes xpert_id and xpert_version. RunRegistry metadata links the Xpert ID, slug, version, draft revision, and checksum. Tool, knowledge, AgentTask, and Handoff node runs remain children of the Xpert run.

Checkpoints store titles, event types, status, lengths, IDs, and error summaries. They must not store complete prompts, complete model or tool outputs, API keys, local absolute paths, embeddings, or raw secrets.

## Conversation Files and Memory

`XpertContextStore` uses the existing runtime storage mount and atomic replacement. It owns conversation messages, file metadata, extracted local artifacts, active memories, and model-proposed memory candidates. `XPERT_CONTEXT_STORAGE_DIR` can override its location and otherwise falls back to `AGENT_TASK_STORAGE_DIR`.

Run requests may include a conversation ID and up to five file asset IDs. A `workflow_agent` only receives extracted file context when `enableFileUnderstanding=true`. Each file contributes at most 10,000 characters and the combined injected context is limited to 30,000 characters. Files remain conversation resources and are not automatically added to RAG.

Memory reads are explicit node configuration. `memoryReadScope` is `conversation`, `xpert`, or `both`; automatic recall is bounded to ten records and 8,000 characters. Model writes create pending candidates. Only user approval activates a candidate, while a direct user "remember" action creates an active record immediately.

The `memory_tools` capability exposes `memory_search`, `memory_get`, and `memory_propose_write`. In ReAct-Lite tool mode these tools share the existing middleware, policy, and audit path with MCP tools. Normal streaming mode remains available and only receives bounded automatic recall.

Goal file sharing is opt-in. Explicit file references are carried through AgentTask and Handoff metadata and can be consumed by target Xperts. Conversation-scoped memory is not copied or exposed to another Xpert; a handoff target may only recall its own Xpert-scoped memory.

## Xpert Handoff Execution

Automatic execution is explicit. Only a Handoff with `execution_mode=xpert_auto` and `target_agent=xpert:<slug-or-id>` is eligible. Other targets remain in the manual MetaAgent Inbox.

The executor resolves the target by ID or slug, pins its current published version on the first claim, and invokes the same classic workflow runner used by the public Xpert chat endpoint. It does not call the server through loopback HTTP. The target receives `user_input`, `handoff_reason`, `source_agent`, and `source_task_id`.

The queue uses the following states:

- `pending -> accepted -> completed`
- `accepted -> retry_wait -> accepted`
- `accepted/retry_wait -> dead_letter`
- `dead_letter -> pending` through the requeue API

Claims use a lease token. The default lease is 60 seconds, the maximum attempt count is three, and transient failures use short exponential backoff. Missing, unpublished, or invalid target Xperts are permanent errors and move directly to dead letter. A delegation depth limit of five prevents unbounded Xpert cycles.

`agent_handoff` and `handoff_router` always write the Handoff ID to `outputVariable`. With `waitForCompletion=true`, they also wait up to `waitTimeoutSeconds` and write the target result to `resultVariable`. With waiting disabled, the source workflow continues while the worker executes the target in the background.

Production enables file persistence through `AGENT_TASK_STORAGE_DIR`. The Store uses atomic temporary-file replacement and an in-process lock. This is durable across a single container restart, but it is not a multi-process or distributed queue.

Public executor interfaces:

- `GET /api/runtime/handoff-executor/status`
- `POST /api/runtime/agent-handoffs/{handoff_id}/execute`
- `POST /api/runtime/agent-handoffs/{handoff_id}/requeue`

## Conversation Goal Coordination

Conversation Goals add a durable orchestration layer above AgentTask and Handoff. A published Planner Xpert produces a JSON dependency plan, the user reviews it, and GoalCoordinator dispatches ready steps through explicit `xpert_auto` handoffs. The default per-Goal concurrency is two.

Planner and target Xpert versions are pinned before execution. A step receives the Goal objective, its instruction, and completed dependency results. The combined input is capped at 20,000 characters and marked when truncated.

Pause stops new dispatch while allowing in-flight work to settle. Cancel prevents future dispatch but does not force-terminate an active model request. Exhausted Handoff retries move the Goal to `needs_attention`; users may retry, reassign, or explicitly skip a non-final step.

Goal state is atomically persisted in `goals.json` under `AGENT_TASK_STORAGE_DIR`. RunRegistry adds `run_type=goal` and links planner, task, handoff, target Xpert, and node runs. Since RunRegistry remains in memory, recovery creates a new Goal run with `recovery_of_run_id` metadata.

See `docs/XPERT_GOALS.md` for the model, state machine, API, planner contract, and safety limits.

## Current Limits

- File persistence is local and is not a workspace database.
- There is no public App/API token, sharing model, organization permission, or collaborative editor.
- Automatic Handoff execution is limited to a single backend process and explicit `xpert:` targets.
- Knowledge-ingestion jobs and promotion of conversation files into versioned RAG indexes remain a future milestone.
- A normal /workflow run remains unchanged and continues to use its existing local-draft behavior.
