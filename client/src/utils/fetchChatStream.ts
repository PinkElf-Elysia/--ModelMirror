export type ChatRole = "system" | "user" | "assistant";

export interface ChatTextPart {
  type: "text";
  text: string;
}

export interface ChatImagePart {
  type: "image_url";
  image_url: {
    url: string;
  };
}

export type ChatMessageContent = string | Array<ChatTextPart | ChatImagePart>;

export interface ChatApiMessage {
  role: ChatRole;
  content: ChatMessageContent;
}

interface FetchChatStreamOptions {
  modelId: string;
  messages: ChatApiMessage[];
  temperature?: number;
  topP?: number;
  maxTokens?: number;
  seed?: number;
  stop?: string[];
  signal?: AbortSignal;
  onDelta: (text: string) => void;
}

const fallbackErrorMessage = "抱歉，模型暂时无法响应，请稍后重试。";

function parseErrorMessage(value: unknown) {
  if (
    value &&
    typeof value === "object" &&
    "error" in value &&
    typeof value.error === "string"
  ) {
    return value.error;
  }

  if (
    value &&
    typeof value === "object" &&
    "error" in value &&
    value.error &&
    typeof value.error === "object" &&
    "message" in value.error &&
    typeof value.error.message === "string"
  ) {
    return value.error.message;
  }

  if (
    value &&
    typeof value === "object" &&
    "detail" in value &&
    typeof value.detail === "string"
  ) {
    return value.detail;
  }

  if (
    value &&
    typeof value === "object" &&
    "detail" in value &&
    Array.isArray(value.detail)
  ) {
    const messages = value.detail
      .map((item: unknown) =>
        item &&
        typeof item === "object" &&
        "msg" in item &&
        typeof item.msg === "string"
          ? item.msg
          : "",
      )
      .filter(Boolean);
    if (messages.length > 0) return messages.join("；");
  }

  return fallbackErrorMessage;
}

function readDelta(payload: unknown) {
  if (!payload || typeof payload !== "object" || !("choices" in payload)) {
    return "";
  }

  const choices = payload.choices;
  if (!Array.isArray(choices)) return "";

  const firstChoice = choices[0] as
    | { delta?: { content?: unknown }; message?: { content?: unknown } }
    | undefined;

  const content =
    firstChoice?.delta?.content ?? firstChoice?.message?.content ?? "";

  return typeof content === "string" ? content : "";
}

function readStreamError(payload: unknown) {
  if (!payload || typeof payload !== "object" || !("error" in payload)) {
    return "";
  }

  const error = payload.error;
  if (typeof error === "string") return error;
  if (
    error &&
    typeof error === "object" &&
    "message" in error &&
    typeof error.message === "string"
  ) {
    return error.message;
  }

  return "";
}

function handleSseEvent(eventText: string, onDelta: (text: string) => void) {
  const dataLines = eventText
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line.startsWith("data:"))
    .map((line) => line.slice(5).trim());

  for (const data of dataLines) {
    if (!data || data === "[DONE]") continue;

    let payload: unknown;
    try {
      payload = JSON.parse(data) as unknown;
    } catch {
      continue;
    }

    const streamError = readStreamError(payload);
    if (streamError) {
      throw new Error(streamError);
    }

    const delta = readDelta(payload);
    if (delta) onDelta(delta);
  }
}

export async function fetchChatStream({
  modelId,
  messages,
  temperature = 0.7,
  topP,
  maxTokens = 2048,
  seed,
  stop,
  signal,
  onDelta,
}: FetchChatStreamOptions) {
  const response = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      model_id: modelId,
      messages,
      temperature,
      top_p: topP,
      max_tokens: maxTokens,
      seed,
      stop,
    }),
    signal,
  });

  if (!response.ok) {
    let message = fallbackErrorMessage;
    let errorPayload: unknown = null;
    try {
      errorPayload = (await response.json()) as unknown;
      message = parseErrorMessage(errorPayload);
    } catch {
      message = response.statusText || message;
    }
    console.error("ModelMirror chat request failed", {
      status: response.status,
      statusText: response.statusText,
      error: errorPayload,
    });
    throw new Error(message);
  }

  const reader = response.body?.getReader();
  if (!reader) {
    throw new Error("当前浏览器不支持流式响应。");
  }

  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const events = buffer.split(/\r?\n\r?\n/);
    buffer = events.pop() ?? "";

    for (const eventText of events) {
      try {
        handleSseEvent(eventText, onDelta);
      } catch (error) {
        console.error("ModelMirror chat stream event failed", error);
        throw error;
      }
    }
  }

  buffer += decoder.decode();
  if (buffer.trim()) {
    try {
      handleSseEvent(buffer, onDelta);
    } catch (error) {
      console.error("ModelMirror chat stream tail failed", error);
      throw error;
    }
  }
}
