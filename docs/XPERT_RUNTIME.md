# Xpert Runtime Contract

Last updated: 2026-07-16

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
- private Xpert Chat may use `human_intervention` or bound `human_in_the_loop` because it exposes durable approval and resume UI; public Xpert App deployments reject both interactive forms.

Existing middleware, MCP Toolset, knowledge, AgentTask, Handoff, and RunRegistry validation remains in force.

## Durable Human Approval And Resume

Interactive private runs persist approval requests in `RuntimeApprovalStore` and continuation state in `WorkflowExecutionStore`, both under the Runtime storage directory. A continuation includes the bounded workflow queue, variables, executed-node set, and current workflow-agent ReAct state. Public APIs expose only redacted approval arguments and a safe sequenced event journal.

Tool execution is ordered as policy, approval, audit start, Provider, then audit completion. Approval interrupts are fatal control signals rather than ordinary middleware errors, so fail-open handling can never invoke the Provider while approval is pending. Edited arguments are schema-validated and policy-checked again before execution. A rejected tool returns an artificial tool result to the model without invoking the Provider.

`ApprovalCoordinator` claims resumable executions with a lease and continues from the suspended Agent action. Restart recovery clears stale process leases. Completed workflow nodes and approved tool calls are not repeated. Approval timeout never implies consent: direct Workflow/Xpert runs remain reopenable, while Goal/Handoff work moves to `needs_attention`.

The safe event stream is available at `GET /api/workflow/run/{task_id}/stream?after_sequence=`. Existing workflow SSE remains compatible and adds only `runtime_approval_pending` and `runtime_approval_resolved`. The legacy `/resume` endpoint remains valid for `human_intervention`.

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

## Versioned Knowledge Pipeline Execution

`RagService` persists pipeline drafts, jobs, immutable candidate versions, and the active-version pointer in RAG metadata. `KnowledgePipelineExecutor` is a single-process background worker that claims queued jobs and runs six ordered stages: load, vision, process, chunk, embed, and store. The vision stage is skipped safely when it is not configured.

A job pins its draft version and snapshots every selected source before execution. Knowledge-base documents are copied into a private job source area. Explicitly selected Xpert conversation files are resolved through `XpertContextStore`, deduplicated, and snapshotted; archived source assets remain usable by an already-created job, while cross-Xpert references are rejected.

Successful execution creates a `ready` candidate index in an isolated vector namespace. It never changes retrieval automatically. The candidate must be queried through the preview API and explicitly activated. Activation atomically updates the active-version pointer, and activating an older ready version is the rollback mechanism. Normal RAG, Chat RAG, `knowledge_retrieval`, and `knowledge_citation` resolve the active namespace centrally; a knowledge base without an active version retains legacy-index behavior.

Pipeline jobs and versions survive process restarts. Running jobs are returned to the queue. RunRegistry remains in memory, so a persisted job whose old run is absent creates a `knowledge_pipeline` recovery run with `recovery_of_run_id` metadata before recording new checkpoints. Checkpoints contain job, stage, version, count, and error summaries only.

The executor is intentionally limited to one local worker and one concurrent job. Cancellation is cooperative between stages. Failed or cancelled attempts delete their candidate namespace and cannot change the active version. See `docs/XPERT_KNOWLEDGE.md` for APIs, states, and operational checks.

## Advanced RAG Retrieval V2

An index schema v2 candidate pins its chunking, embedding, and retrieval profiles. It supports recursive-character chunks or parent-child chunks with ordered separators. Parent-child candidates index the child chunks; retrieval returns bounded parent context while retaining the matched child and offsets as the citation anchor.

Each v2 candidate owns two coordinated indexes: the existing vector namespace and a SQLite FTS5 namespace with normalized Latin tokens plus CJK unigram/bigram tokens. A candidate is marked ready only when both indexes contain the expected chunks. Any load, parse, chunk, embedding, vector, or lexical failure removes both candidate indexes and leaves the active-version pointer unchanged.

Retrieval modes are `vector`, `fulltext`, and `hybrid`. Hybrid retrieval over-fetches bounded candidate sets, deduplicates by chunk ID, and applies weighted normalized reciprocal-rank fusion. Optional reranking prefers a dedicated rerank provider and can fall back to an OpenAI-compatible LLM strict-JSON ranking response. Provider timeout or invalid output is fail-open: the fused order is returned with a warning.

Normal RAG, Chat RAG, workflow knowledge nodes, published Xperts, Goals, and Xpert Apps resolve the active version through `RagService`; clients cannot silently select a candidate. Legacy indexes remain vector-only and are not migrated automatically. Retrieval checkpoints and diagnostics may contain mode, counts, scores, model labels, and warnings, but never the full question, chunk body, embedding, local path, or credential.

## Knowledge Evaluation And Promotion

`KnowledgeEvaluationStore` persists revisioned evaluation sets, immutable run snapshots, gate policies, aggregate metrics, and safe per-case rankings in the RAG storage directory. Expected citations use stable source document IDs plus optional chunk, source block, and page references, not candidate namespace IDs.

`KnowledgeEvaluationExecutor` is a restart-safe single-process worker. It queries immutable candidate versions with answer generation disabled, then calculates Recall@1/5, MRR@10, nDCG@10, citation hit/coverage, no-result rate, error rate, and P95 latency. RunRegistry uses `run_type=knowledge_evaluation`; checkpoints contain only IDs, counts, status, duration, and safe error summaries.

Promotion Gate supports advisory and required modes. Required promotion verifies that the evaluation run succeeded, evaluated the same knowledge base and candidate version, used the current evaluation-set revision, and passed every configured absolute and regression threshold. Advisory mode retains the previous direct activation path for compatibility. Promotion switches the existing active-version pointer only; it does not rebuild indexes or mutate the immutable candidate.

## Structured Processor And Generated Indexes

Each pipeline job pins a `processor_profile` before execution. `StructuredDocumentProcessor` converts TXT, Markdown, PDF, and extracted Xpert files into stable blocks. Markdown preserves heading paths, tables, lists, and fenced code; PDF blocks retain page numbers and can remove repeated page headers and footers. Normalization removes control characters and collapses redundant blank lines without flattening table or code content.

Processor modes are `general`, `qa`, and `summary`. General blocks continue into the configured recursive or parent-child splitter. QA batches structural blocks through the existing OpenAI-compatible gateway, indexes the generated question, and stores the grounded answer plus source block as lifted context. Summary indexes document/section summaries and returns the corresponding original blocks. Generated JSON is validated strictly and retried at most twice per batch.

The job owns a private processed artifact per source. Public payloads expose only status, attempts, counts, duration, warning, and safe error summaries. A retry reuses an artifact only when both source content hash and processor config hash still match. Failed sources are rerun, then both candidate indexes are rebuilt from the complete successful artifact set. `continue_on_error` can produce a warned candidate when at least one source succeeded; `strict` blocks candidate readiness after any source failure.

`GET /api/rag/processor-capabilities` returns safe parser/model readiness labels. Processor preview accepts one document and an optional config override, returns at most 20 truncated blocks or generated items, and never persists output. Active-version resolution for Chat, workflow, Xpert, Goal, and App remains unchanged.

## Knowledge Agent Read And Approval Write

`workflow_agent` can opt into a dedicated `knowledge_tools` capability while using the existing Runtime tool loop. `knowledgeReadEnabled`, `knowledgeWriteEnabled`, and one to five `knowledgeBaseIds` are fixed in the published workflow. The model cannot select an undeclared knowledge base. `knowledge_search`, `knowledge_get`, `knowledge_cite`, and `knowledge_propose_write` all pass through `run_tool_with_runtime`, middleware, tool policy, audit, and checkpoint handling.

Read tools resolve only the active knowledge namespace. Search can merge several declared knowledge bases with stable score ordering and bounded excerpts; exact lookup requires the active namespace plus chunk ID. A single-library failure becomes a warning, while total failure becomes a runtime tool error. Tool output, audit, and checkpoints retain IDs, score diagnostics, lengths, status, and safe errors only.

`knowledge_propose_write` creates a durable pending proposal. It never edits a document or index. The per-knowledge-base Inbox is the sole approval surface and uses revision-based optimistic concurrency. Approval snapshots the exact active version sources when one exists, adds a managed Markdown source, and queues the existing Pipeline executor. The resulting candidate carries `promotion_required=true`; direct activation is rejected and only a passed Evaluation Gate followed by `/promote` can change the active pointer. Rejecting a proposal creates no document, job, or version.

Goal and Handoff execution reuse the same published workflow settings and attach safe source IDs to proposals. Public Xpert Apps may opt into read-only knowledge access with `allow_knowledge_read`; dynamic knowledge write is always rejected at deployment and runtime.

## Current Limits

- File persistence is local and is not a workspace database.
- Public Xpert Apps now provide fixed-version unlisted sharing and an OpenAI-compatible API. They remain a trusted-local management feature without organization permissions or a collaborative editor. See `docs/XPERT_APP_API.md`.

## Xpert App Deployment

`XpertAppStore` shares the Xpert storage directory and persists App metadata, immutable deployment history, credential hashes, prefixes, status, limits, and daily usage through atomic replacement. Raw share tokens and API keys are returned once and never persisted.

App execution uses `run_type=xpert_app` and the same classic runner. The deployment fixes one immutable XpertVersion. Tool, Handoff, and Xpert-memory capabilities are disabled by default; tool execution also requires an active `tool_policy`, otherwise the runtime denies the call. Public JSON/SSE responses expose only the final output.
- Automatic Handoff execution is limited to a single backend process and explicit `xpert:` targets.
- Knowledge ingestion, evaluation, and approval-triggered candidate builds are local and single-process; they have no distributed lease or automatic activation. Image understanding, evaluation, and Knowledge Agent approval writes are available, while multimodal embeddings, layout coordinates, and GraphRAG remain out of scope.
- A normal /workflow run remains unchanged and continues to use its existing local-draft behavior.

## Isolated Sandbox Runtime

Private Workflow, Xpert Chat, Goal, and Handoff runs may compile `sandbox_files`, `sandbox_shell`, and `skills_runtime` into the target workflow Agent. A dedicated Docker sidecar owns the workspaces and exposes only a Unix Domain Socket. It has no network, no host port, a read-only root, dropped capabilities, resource limits, and no mount of the repository, `.env`, credentials, or Runtime stores.

Workspaces are scoped to conversation, goal/step, handoff, or workflow task/node. Inputs, editable files, staged Skills, artifacts, and idempotency records use separate directories. File paths are relative and symlink-safe. Shell calls accept argv arrays only, use an explicit executable allowlist, terminate process groups on timeout, truncate output, and replay completed operation results instead of repeating side effects.

Sandbox and Skill tools still pass through the Agent pipeline, permission policy, durable HITL, audit, and safe checkpoint handling. `sandbox_shell.require_approval` is enforced during validation and again when the Agent runtime is compiled. Published Xpert Apps reject these middleware types. See `docs/XPERT_SANDBOX.md`.

## Agent-Bound Middleware Core

Classic workflow supports a non-control binding edge from `runtime_middleware` to `workflow_agent` through `sourceHandle="middleware-binding"` and `targetHandle="middleware"`. Binding nodes are excluded from topological scheduling, variable reachability, and independent execution. A middleware node can bind to one Agent only and cannot simultaneously participate in control flow. Bound middleware is ordered by priority and node ID; legacy linear middleware remains compatible.

Each workflow Agent compiles an isolated `MiddlewarePipeline`. Agent hooks wrap the complete Agent run, model hooks run for direct streaming and every ReAct decision, and Runtime tools reuse the same pipeline, tool policy, event recorder, and audit store. Context compression can persist a derived Xpert conversation summary without modifying original messages. Structured output buffers the final answer, validates Draft 2020-12 JSON Schema, and optionally repairs once before entering existing exception handling.

The Todo capability exposes scope-bound `todo_list`, `todo_create`, and `todo_update`. Conversation, Goal, Handoff, and Workflow scopes are atomically persisted; Xpert App scopes remain run-local. The LLM tool selector operates only after allowlist and policy filtering and cannot restore denied tools. Checkpoints retain names, counts, status, timing, and safe errors only. See `docs/XPERT_MIDDLEWARE.md`.
