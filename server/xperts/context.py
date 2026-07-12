from __future__ import annotations

import json
import mimetypes
import os
import re
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

try:
    from server.rag.document_parser import DocumentParseError, parse_document, supported_extensions
except ModuleNotFoundError:
    from rag.document_parser import DocumentParseError, parse_document, supported_extensions


MemoryScope = Literal["conversation", "xpert"]
CandidateStatus = Literal["pending", "approved", "rejected"]
MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_FILES_PER_CONVERSATION = 20
MAX_SELECTED_FILES = 5
MAX_EXTRACTED_CHARS = 500_000
MAX_CONVERSATION_MESSAGES = 200


class XpertContextError(Exception):
    """Base error for Xpert conversation, file, and memory storage."""


class XpertContextNotFoundError(XpertContextError):
    """Raised when an Xpert context resource does not exist."""


class XpertContextValidationError(XpertContextError):
    """Raised when an Xpert context request is invalid."""


@dataclass(slots=True)
class XpertConversationMessage:
    message_id: str
    role: Literal["user", "assistant"]
    content: str
    version: int | None = None
    created_at: float = field(default_factory=time.time)


@dataclass(slots=True)
class XpertConversation:
    conversation_id: str
    xpert_id: str
    title: str
    messages: list[XpertConversationMessage] = field(default_factory=list)
    file_asset_ids: list[str] = field(default_factory=list)
    archived: bool = False
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


@dataclass(slots=True)
class XpertFileAsset:
    asset_id: str
    artifact_id: str
    xpert_id: str
    conversation_id: str
    filename: str
    size_bytes: int
    extension: str
    mime_type: str
    status: Literal["ready", "archived"] = "ready"
    character_count: int = 0
    extracted_truncated: bool = False
    storage_key: str = ""
    text_key: str = ""
    created_at: float = field(default_factory=time.time)
    archived_at: float | None = None


@dataclass(slots=True)
class XpertMemoryRecord:
    memory_id: str
    xpert_id: str
    scope: MemoryScope
    content: str
    conversation_id: str | None = None
    tags: list[str] = field(default_factory=list)
    source_type: str = "user"
    source_id: str | None = None
    status: Literal["active", "archived"] = "active"
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


@dataclass(slots=True)
class MemoryWriteCandidate:
    candidate_id: str
    xpert_id: str
    scope: MemoryScope
    content: str
    conversation_id: str | None = None
    tags: list[str] = field(default_factory=list)
    source_run_id: str | None = None
    status: CandidateStatus = "pending"
    created_at: float = field(default_factory=time.time)
    decided_at: float | None = None
    memory_id: str | None = None


class XpertContextStore:
    """Atomic file-backed context store for published Xpert conversations."""

    def __init__(self, storage_dir: str | Path | None = None) -> None:
        fallback = os.getenv("AGENT_TASK_STORAGE_DIR", "").strip()
        package_dir = Path(__file__).resolve().parent
        self.storage_dir = Path(
            storage_dir
            or os.getenv("XPERT_CONTEXT_STORAGE_DIR", "").strip()
            or fallback
            or package_dir / "storage"
        )
        self.context_dir = self.storage_dir / "xpert_context"
        self.files_dir = self.context_dir / "files"
        self.snapshot_path = self.context_dir / "context.json"
        self._lock = threading.RLock()
        self._conversations: dict[str, XpertConversation] = {}
        self._assets: dict[str, XpertFileAsset] = {}
        self._memories: dict[str, XpertMemoryRecord] = {}
        self._candidates: dict[str, MemoryWriteCandidate] = {}
        self._load()

    def create_conversation(self, xpert_id: str, *, title: str = "") -> XpertConversation:
        conversation = XpertConversation(
            conversation_id=str(uuid.uuid4()),
            xpert_id=self._required_text(xpert_id, "xpert_id", 200),
            title=(title.strip()[:120] or "New conversation"),
        )
        with self._lock:
            self._conversations[conversation.conversation_id] = conversation
            self._persist_unlocked()
        return conversation

    def get_conversation(self, xpert_id: str, conversation_id: str) -> XpertConversation:
        with self._lock:
            conversation = self._conversations.get(conversation_id)
            if conversation is None or conversation.xpert_id != xpert_id:
                raise XpertContextNotFoundError("Xpert conversation not found.")
            return conversation

    def list_conversations(self, xpert_id: str, *, limit: int = 50) -> list[XpertConversation]:
        with self._lock:
            items = [
                item
                for item in self._conversations.values()
                if item.xpert_id == xpert_id and not item.archived
            ]
        items.sort(key=lambda item: item.updated_at, reverse=True)
        return items[: max(1, min(limit, 200))]

    def append_message(
        self,
        xpert_id: str,
        conversation_id: str,
        *,
        role: Literal["user", "assistant"],
        content: str,
        version: int | None = None,
    ) -> XpertConversationMessage:
        clean_content = self._required_text(content, "content", 100_000)
        message = XpertConversationMessage(
            message_id=str(uuid.uuid4()),
            role=role,
            content=clean_content,
            version=version,
        )
        with self._lock:
            conversation = self._require_conversation_unlocked(xpert_id, conversation_id)
            conversation.messages.append(message)
            if len(conversation.messages) > MAX_CONVERSATION_MESSAGES:
                conversation.messages = conversation.messages[-MAX_CONVERSATION_MESSAGES:]
            if conversation.title == "New conversation" and role == "user":
                conversation.title = clean_content.replace("\n", " ")[:60]
            conversation.updated_at = time.time()
            self._persist_unlocked()
        return message

    def add_file(
        self,
        xpert_id: str,
        conversation_id: str,
        *,
        filename: str,
        content: bytes,
    ) -> XpertFileAsset:
        clean_filename = self._safe_filename(filename)
        extension = Path(clean_filename).suffix.lower()
        if extension not in supported_extensions():
            raise XpertContextValidationError(
                f"Unsupported file type: {extension or '<none>'}."
            )
        if not content:
            raise XpertContextValidationError("The uploaded file is empty.")
        if len(content) > MAX_FILE_BYTES:
            raise XpertContextValidationError("The uploaded file exceeds the 10 MB limit.")

        with self._lock:
            conversation = self._require_conversation_unlocked(xpert_id, conversation_id)
            active_count = sum(
                1
                for asset_id in conversation.file_asset_ids
                if (asset := self._assets.get(asset_id)) is not None and asset.status == "ready"
            )
            if active_count >= MAX_FILES_PER_CONVERSATION:
                raise XpertContextValidationError(
                    "A conversation can contain at most 20 active files."
                )

            asset_id = str(uuid.uuid4())
            artifact_id = str(uuid.uuid4())
            relative_dir = Path(xpert_id) / conversation_id
            raw_key = relative_dir / f"{asset_id}{extension}"
            text_key = relative_dir / f"{artifact_id}.txt"
            raw_path = self.files_dir / raw_key
            text_path = self.files_dir / text_key
            raw_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = raw_path.with_suffix(raw_path.suffix + ".tmp")
            temporary.write_bytes(content)
            os.replace(temporary, raw_path)
            try:
                extracted = parse_document(raw_path, clean_filename)
            except DocumentParseError as exc:
                raw_path.unlink(missing_ok=True)
                raise XpertContextValidationError(str(exc)) from exc
            truncated = len(extracted) > MAX_EXTRACTED_CHARS
            stored_text = extracted[:MAX_EXTRACTED_CHARS]
            text_path.write_text(stored_text, encoding="utf-8")
            asset = XpertFileAsset(
                asset_id=asset_id,
                artifact_id=artifact_id,
                xpert_id=xpert_id,
                conversation_id=conversation_id,
                filename=clean_filename,
                size_bytes=len(content),
                extension=extension,
                mime_type=mimetypes.guess_type(clean_filename)[0] or "application/octet-stream",
                character_count=len(stored_text),
                extracted_truncated=truncated,
                storage_key=raw_key.as_posix(),
                text_key=text_key.as_posix(),
            )
            self._assets[asset_id] = asset
            conversation.file_asset_ids.append(asset_id)
            conversation.updated_at = time.time()
            self._persist_unlocked()
            return asset

    def get_file(
        self,
        xpert_id: str,
        asset_id: str,
        *,
        conversation_id: str | None = None,
        include_archived: bool = False,
    ) -> XpertFileAsset:
        with self._lock:
            asset = self._assets.get(asset_id)
            if asset is None or asset.xpert_id != xpert_id:
                raise XpertContextNotFoundError("Xpert file asset not found.")
            if conversation_id is not None and asset.conversation_id != conversation_id:
                raise XpertContextNotFoundError("Xpert file asset not found.")
            if asset.status == "archived" and not include_archived:
                raise XpertContextNotFoundError("Xpert file asset is archived.")
            return asset

    def list_files(
        self,
        xpert_id: str,
        conversation_id: str,
        *,
        include_archived: bool = False,
    ) -> list[XpertFileAsset]:
        with self._lock:
            conversation = self._require_conversation_unlocked(xpert_id, conversation_id)
            items = [self._assets[item] for item in conversation.file_asset_ids if item in self._assets]
        if not include_archived:
            items = [item for item in items if item.status == "ready"]
        items.sort(key=lambda item: item.created_at, reverse=True)
        return items

    def archive_file(self, xpert_id: str, conversation_id: str, asset_id: str) -> XpertFileAsset:
        with self._lock:
            asset = self.get_file(xpert_id, asset_id, conversation_id=conversation_id)
            asset.status = "archived"
            asset.archived_at = time.time()
            self._persist_unlocked()
            return asset

    def read_file_text(self, asset: XpertFileAsset) -> str:
        path = self.files_dir / asset.text_key
        try:
            return path.read_text(encoding="utf-8")
        except OSError as exc:
            raise XpertContextError("Xpert file artifact is unavailable.") from exc

    def build_file_context(
        self,
        xpert_id: str,
        asset_ids: list[str],
        *,
        conversation_id: str | None = None,
        include_archived: bool = False,
        per_file_chars: int = 10_000,
        total_chars: int = 30_000,
    ) -> tuple[str, list[XpertFileAsset]]:
        unique_ids = list(dict.fromkeys(asset_ids))
        if len(unique_ids) > MAX_SELECTED_FILES:
            raise XpertContextValidationError("At most 5 files can be selected per run.")
        sections: list[str] = []
        selected: list[XpertFileAsset] = []
        used = 0
        for asset_id in unique_ids:
            asset = self.get_file(
                xpert_id,
                asset_id,
                conversation_id=conversation_id,
                include_archived=include_archived,
            )
            remaining = total_chars - used
            if remaining <= 0:
                break
            text = self.read_file_text(asset)
            excerpt = text[: min(per_file_chars, remaining)]
            truncated = len(excerpt) < len(text)
            header = (
                f"[File: {asset.filename}; asset_id={asset.asset_id}; "
                f"artifact_id={asset.artifact_id}; truncated={str(truncated).lower()}]"
            )
            section = f"{header}\n{excerpt}"
            if len(section) > remaining:
                section = section[:remaining]
            sections.append(section)
            selected.append(asset)
            used += len(section)
        return "\n\n".join(sections), selected

    def create_memory(
        self,
        xpert_id: str,
        *,
        content: str,
        scope: MemoryScope = "xpert",
        conversation_id: str | None = None,
        tags: list[str] | None = None,
        source_type: str = "user",
        source_id: str | None = None,
    ) -> XpertMemoryRecord:
        clean_content = self._required_text(content, "content", 4_000)
        self._validate_memory_scope(xpert_id, scope, conversation_id)
        record = XpertMemoryRecord(
            memory_id=str(uuid.uuid4()),
            xpert_id=xpert_id,
            scope=scope,
            conversation_id=conversation_id if scope == "conversation" else None,
            content=clean_content,
            tags=self._clean_tags(tags),
            source_type=source_type[:80] or "user",
            source_id=source_id,
        )
        with self._lock:
            self._memories[record.memory_id] = record
            self._persist_unlocked()
        return record

    def get_memory(self, xpert_id: str, memory_id: str) -> XpertMemoryRecord:
        with self._lock:
            record = self._memories.get(memory_id)
            if record is None or record.xpert_id != xpert_id:
                raise XpertContextNotFoundError("Xpert memory not found.")
            return record

    def list_memories(
        self,
        xpert_id: str,
        *,
        scope: Literal["conversation", "xpert", "both"] = "both",
        conversation_id: str | None = None,
        search: str = "",
        limit: int = 50,
    ) -> list[XpertMemoryRecord]:
        query = search.strip().lower()
        with self._lock:
            items = [
                item
                for item in self._memories.values()
                if item.xpert_id == xpert_id
                and item.status == "active"
                and (scope == "both" or item.scope == scope)
                and (
                    item.scope == "xpert"
                    or (
                        conversation_id is not None
                        and item.conversation_id == conversation_id
                    )
                )
                and (
                    not query
                    or query in item.content.lower()
                    or any(query in tag.lower() for tag in item.tags)
                )
            ]
        items.sort(key=lambda item: item.updated_at, reverse=True)
        return items[: max(1, min(limit, 200))]

    def search_memories(
        self,
        xpert_id: str,
        query: str,
        *,
        scope: Literal["conversation", "xpert", "both"] = "both",
        conversation_id: str | None = None,
        limit: int = 10,
    ) -> list[XpertMemoryRecord]:
        candidates = self.list_memories(
            xpert_id,
            scope=scope,
            conversation_id=conversation_id,
            limit=200,
        )
        clean_query = query.strip().lower()
        if not clean_query:
            return candidates[:limit]
        query_terms = self._search_terms(clean_query)
        now = time.time()

        def score(record: XpertMemoryRecord) -> float:
            haystack = f"{record.content} {' '.join(record.tags)}".lower()
            value = 10.0 if clean_query in haystack else 0.0
            value += sum(2.0 for term in query_terms if term in haystack)
            value += max(0.0, 1.0 - (now - record.updated_at) / (90 * 86400))
            return value

        ranked = [(score(item), item) for item in candidates]
        ranked.sort(key=lambda pair: (pair[0], pair[1].updated_at), reverse=True)
        matched = [item for value, item in ranked if value > 0]
        return matched[: max(1, min(limit, 20))]

    def archive_memory(self, xpert_id: str, memory_id: str) -> XpertMemoryRecord:
        with self._lock:
            record = self.get_memory(xpert_id, memory_id)
            record.status = "archived"
            record.updated_at = time.time()
            self._persist_unlocked()
            return record

    def create_candidate(
        self,
        xpert_id: str,
        *,
        content: str,
        scope: MemoryScope,
        conversation_id: str | None = None,
        tags: list[str] | None = None,
        source_run_id: str | None = None,
    ) -> MemoryWriteCandidate:
        clean_content = self._required_text(content, "content", 1_000)
        self._validate_memory_scope(xpert_id, scope, conversation_id)
        with self._lock:
            for existing in self._candidates.values():
                if (
                    existing.xpert_id == xpert_id
                    and existing.status == "pending"
                    and existing.content.casefold() == clean_content.casefold()
                    and existing.scope == scope
                    and existing.conversation_id == conversation_id
                ):
                    return existing
            candidate = MemoryWriteCandidate(
                candidate_id=str(uuid.uuid4()),
                xpert_id=xpert_id,
                scope=scope,
                conversation_id=conversation_id if scope == "conversation" else None,
                content=clean_content,
                tags=self._clean_tags(tags),
                source_run_id=source_run_id,
            )
            self._candidates[candidate.candidate_id] = candidate
            self._persist_unlocked()
            return candidate

    def list_candidates(
        self,
        xpert_id: str,
        *,
        status: CandidateStatus | None = None,
        conversation_id: str | None = None,
        limit: int = 50,
    ) -> list[MemoryWriteCandidate]:
        with self._lock:
            items = [
                item
                for item in self._candidates.values()
                if item.xpert_id == xpert_id
                and (status is None or item.status == status)
                and (conversation_id is None or item.conversation_id == conversation_id)
            ]
        items.sort(key=lambda item: item.created_at, reverse=True)
        return items[: max(1, min(limit, 200))]

    def decide_candidate(
        self,
        xpert_id: str,
        candidate_id: str,
        *,
        approve: bool,
    ) -> MemoryWriteCandidate:
        with self._lock:
            candidate = self._candidates.get(candidate_id)
            if candidate is None or candidate.xpert_id != xpert_id:
                raise XpertContextNotFoundError("Memory candidate not found.")
            if candidate.status != "pending":
                raise XpertContextValidationError("Memory candidate was already decided.")
            if approve:
                memory = self.create_memory(
                    xpert_id,
                    content=candidate.content,
                    scope=candidate.scope,
                    conversation_id=candidate.conversation_id,
                    tags=candidate.tags,
                    source_type="candidate",
                    source_id=candidate.candidate_id,
                )
                candidate.status = "approved"
                candidate.memory_id = memory.memory_id
            else:
                candidate.status = "rejected"
            candidate.decided_at = time.time()
            self._persist_unlocked()
            return candidate

    @staticmethod
    def conversation_payload(item: XpertConversation, *, include_messages: bool) -> dict[str, Any]:
        payload = asdict(item)
        if not include_messages:
            payload.pop("messages", None)
            payload["message_count"] = len(item.messages)
        return payload

    @staticmethod
    def file_payload(item: XpertFileAsset) -> dict[str, Any]:
        payload = asdict(item)
        payload.pop("storage_key", None)
        payload.pop("text_key", None)
        return payload

    @staticmethod
    def memory_payload(item: XpertMemoryRecord) -> dict[str, Any]:
        return asdict(item)

    @staticmethod
    def candidate_payload(item: MemoryWriteCandidate) -> dict[str, Any]:
        return asdict(item)

    def _validate_memory_scope(
        self,
        xpert_id: str,
        scope: str,
        conversation_id: str | None,
    ) -> None:
        if scope not in {"conversation", "xpert"}:
            raise XpertContextValidationError("Memory scope must be conversation or xpert.")
        if scope == "conversation":
            if not conversation_id:
                raise XpertContextValidationError(
                    "conversation_id is required for conversation memory."
                )
            self.get_conversation(xpert_id, conversation_id)

    def _require_conversation_unlocked(
        self,
        xpert_id: str,
        conversation_id: str,
    ) -> XpertConversation:
        conversation = self._conversations.get(conversation_id)
        if conversation is None or conversation.xpert_id != xpert_id:
            raise XpertContextNotFoundError("Xpert conversation not found.")
        if conversation.archived:
            raise XpertContextValidationError("Xpert conversation is archived.")
        return conversation

    def _load(self) -> None:
        if not self.snapshot_path.exists():
            return
        try:
            payload = json.loads(self.snapshot_path.read_text(encoding="utf-8"))
            for raw in payload.get("conversations", []):
                messages = [XpertConversationMessage(**item) for item in raw.pop("messages", [])]
                conversation = XpertConversation(messages=messages, **raw)
                self._conversations[conversation.conversation_id] = conversation
            for raw in payload.get("assets", []):
                asset = XpertFileAsset(**raw)
                self._assets[asset.asset_id] = asset
            for raw in payload.get("memories", []):
                memory = XpertMemoryRecord(**raw)
                self._memories[memory.memory_id] = memory
            for raw in payload.get("candidates", []):
                candidate = MemoryWriteCandidate(**raw)
                self._candidates[candidate.candidate_id] = candidate
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            raise XpertContextError(f"Failed to load Xpert context store: {exc}") from exc

    def _persist_unlocked(self) -> None:
        self.context_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": "xpert-context-v1",
            "conversations": [asdict(item) for item in self._conversations.values()],
            "assets": [asdict(item) for item in self._assets.values()],
            "memories": [asdict(item) for item in self._memories.values()],
            "candidates": [asdict(item) for item in self._candidates.values()],
        }
        temporary = self.snapshot_path.with_suffix(
            f".{os.getpid()}.{uuid.uuid4().hex}.tmp"
        )
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(temporary, self.snapshot_path)

    @staticmethod
    def _required_text(value: str, field_name: str, max_length: int) -> str:
        clean = str(value or "").strip()
        if not clean:
            raise XpertContextValidationError(f"{field_name} is required.")
        return clean[:max_length]

    @staticmethod
    def _safe_filename(filename: str) -> str:
        clean = str(filename or "").strip()
        if not clean or "/" in clean or "\\" in clean or clean in {".", ".."}:
            raise XpertContextValidationError("The uploaded filename is invalid.")
        if Path(clean).name != clean:
            raise XpertContextValidationError("The uploaded filename is invalid.")
        return clean[:240]

    @staticmethod
    def _clean_tags(tags: list[str] | None) -> list[str]:
        result: list[str] = []
        for value in tags or []:
            clean = str(value).strip()[:80]
            if clean and clean not in result:
                result.append(clean)
            if len(result) >= 10:
                break
        return result

    @staticmethod
    def _search_terms(value: str) -> set[str]:
        terms = {item for item in re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]+", value) if item}
        for item in list(terms):
            if re.fullmatch(r"[\u4e00-\u9fff]+", item) and len(item) > 1:
                terms.update(item[index : index + 2] for index in range(len(item) - 1))
        return terms
