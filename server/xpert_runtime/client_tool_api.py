from __future__ import annotations

import io
import json
import uuid
import zipfile
from pathlib import Path
from typing import Any

from fastapi import (
    APIRouter,
    File,
    Header,
    HTTPException,
    Query,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import FileResponse, HTMLResponse, Response
from pydantic import BaseModel, Field

from .client_tool_coordinator import (
    ClientToolConnectionManager,
    ClientToolCoordinator,
)
from .client_tool_store import (
    ClientToolAuthenticationError,
    ClientToolConflictError,
    ClientToolNotFoundError,
    ClientToolStore,
)
from .client_toolset import CLIENT_TOOLS, client_tool_schema_hash


router = APIRouter(prefix="/api/runtime", tags=["runtime-client-tools"])
_store: ClientToolStore | None = None
_connections: ClientToolConnectionManager | None = None
_coordinator: ClientToolCoordinator | None = None


class PairingCreateRequest(BaseModel):
    name: str = Field(default="Chrome Host", max_length=100)


def configure_runtime_client_tools(
    store: ClientToolStore,
    connections: ClientToolConnectionManager,
    coordinator: ClientToolCoordinator | None = None,
) -> None:
    global _store, _connections, _coordinator
    _store = store
    _connections = connections
    _coordinator = coordinator


def configure_client_tool_coordinator(coordinator: ClientToolCoordinator) -> None:
    global _coordinator
    _coordinator = coordinator


def get_store() -> ClientToolStore:
    if _store is None:
        raise RuntimeError("Client tool runtime is not configured.")
    return _store


def get_connections() -> ClientToolConnectionManager:
    if _connections is None:
        raise RuntimeError("Client tool connections are not configured.")
    return _connections


def _raise_error(exc: Exception) -> None:
    if isinstance(exc, ClientToolNotFoundError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, ClientToolAuthenticationError):
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    if isinstance(exc, ClientToolConflictError):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/client-tools/capabilities")
async def client_tool_capabilities() -> dict[str, Any]:
    return {
        "version": "modelmirror-client-tools-v1",
        "minimum_chrome_version": 116,
        "pairing_ttl_seconds": 300,
        "heartbeat_seconds": 20,
        "max_read_characters": 24_000,
        "max_snapshot_elements": 500,
        "max_screenshot_bytes": 5 * 1024 * 1024,
        "tools": [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.input_schema,
                "schema_hash": client_tool_schema_hash(tool),
            }
            for tool in CLIENT_TOOLS
        ],
    }


@router.get("/client-tool-coordinator/status")
async def client_tool_coordinator_status() -> dict[str, Any]:
    if _coordinator is None:
        return {"enabled": False, "running": False}
    return await _coordinator.status()


@router.post("/client-hosts/pairings")
async def create_client_host_pairing(
    payload: PairingCreateRequest,
) -> dict[str, Any]:
    pairing, code = get_store().create_pairing(name=payload.name)
    return {
        "pairing_id": pairing.pairing_id,
        "pairing_code": code,
        "expires_at": pairing.expires_at,
        "single_use": True,
    }


@router.get("/client-hosts")
async def list_client_hosts() -> dict[str, Any]:
    return {
        "hosts": [
            get_store().serialize_host(item) for item in get_store().list_hosts()
        ]
    }


@router.get("/client-hosts/extension.zip")
async def download_client_host_extension() -> Response:
    source = Path(__file__).resolve().parent.parent / "client_extension"
    if not source.is_dir():
        raise HTTPException(status_code=404, detail="Client extension source is unavailable.")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(source.rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts:
                archive.write(path, path.relative_to(source.parent))
    return Response(
        buffer.getvalue(),
        media_type="application/zip",
        headers={
            "Content-Disposition": 'attachment; filename="modelmirror-client-host.zip"',
            "Cache-Control": "no-store",
        },
    )


@router.get("/client-hosts/{host_id}")
async def get_client_host(host_id: str) -> dict[str, Any]:
    try:
        return get_store().serialize_host(get_store().require_host(host_id))
    except Exception as exc:
        _raise_error(exc)


@router.post("/client-hosts/{host_id}/revoke")
async def revoke_client_host(host_id: str) -> dict[str, Any]:
    try:
        item = get_store().revoke_host(host_id)
        return get_store().serialize_host(item)
    except Exception as exc:
        _raise_error(exc)


@router.get("/client-tools/fixture", response_class=HTMLResponse)
async def client_tool_fixture() -> str:
    return """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>ModelMirror Client Tool Fixture</title></head>
<body><main aria-label="Client tool test page"><h1>Client tool test page</h1>
<label>Name <input name="display_name" autocomplete="name"></label>
<label>Role <select name="role"><option>Researcher</option><option>Editor</option></select></label>
<button type="button" id="save">Save</button><output id="result" aria-live="polite"></output>
<script>document.querySelector('#save').addEventListener('click',()=>{document.querySelector('#result').textContent='Saved: '+document.querySelector('[name=display_name]').value;});</script>
</main></body></html>"""


@router.get("/client-tool-requests")
async def list_client_tool_requests(
    status: str | None = None,
    host_id: str | None = None,
    task_id: str | None = None,
    scope_type: str | None = None,
    scope_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
) -> dict[str, Any]:
    items = get_store().list_requests(
        status=status,
        host_id=host_id,
        task_id=task_id,
        scope_type=scope_type,
        scope_id=scope_id,
        limit=limit,
    )
    return {"requests": [get_store().serialize_request(item) for item in items]}


@router.get("/client-tool-requests/{request_id}")
async def get_client_tool_request(request_id: str) -> dict[str, Any]:
    try:
        return get_store().serialize_request(
            get_store().require_request(request_id), include_result=True
        )
    except Exception as exc:
        _raise_error(exc)


@router.post("/client-tool-requests/{request_id}/retry")
async def retry_client_tool_request(request_id: str) -> dict[str, Any]:
    try:
        item = get_store().retry_request(request_id)
        if _coordinator is not None:
            _coordinator.wake()
        return get_store().serialize_request(item)
    except Exception as exc:
        _raise_error(exc)


@router.post("/client-tool-requests/{request_id}/cancel")
async def cancel_client_tool_request(request_id: str) -> dict[str, Any]:
    try:
        item = get_store().cancel_request(request_id)
        if _coordinator is not None:
            _coordinator.wake()
        return get_store().serialize_request(item)
    except Exception as exc:
        _raise_error(exc)


def _bearer_token(value: str | None) -> str:
    if not value or not value.startswith("Bearer "):
        raise ClientToolAuthenticationError("Client host bearer token is required.")
    return value.removeprefix("Bearer ").strip()


@router.post("/client-tool-requests/{request_id}/artifact")
async def upload_client_tool_artifact(
    request_id: str,
    file: UploadFile = File(...),
    x_modelmirror_client_host_id: str = Header(alias="X-ModelMirror-Client-Host-Id"),
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    try:
        token = _bearer_token(authorization)
        host = get_store().authenticate(x_modelmirror_client_host_id, token)
        request = get_store().require_request(request_id)
        if request.host_id != host.host_id or request.tool_name != "host_page_screenshot":
            raise ClientToolConflictError("Artifact does not belong to this host request.")
        data = await file.read(5 * 1024 * 1024 + 1)
        artifact = get_store().register_artifact(
            request_id=request_id,
            host_id=host.host_id,
            filename=file.filename or "client-screenshot.png",
            content_type=file.content_type or "application/octet-stream",
            data=data,
        )
        return get_store().serialize_artifact(artifact)
    except Exception as exc:
        _raise_error(exc)


@router.get("/client-tool-artifacts/{artifact_id}")
async def get_client_tool_artifact(artifact_id: str) -> dict[str, Any]:
    try:
        return get_store().serialize_artifact(
            get_store().require_artifact(artifact_id)
        )
    except Exception as exc:
        _raise_error(exc)


@router.get("/client-tool-artifacts/{artifact_id}/download")
async def download_client_tool_artifact(artifact_id: str) -> FileResponse:
    try:
        artifact = get_store().require_artifact(artifact_id)
        path = get_store().artifact_path(artifact)
        return FileResponse(
            path,
            media_type=artifact.content_type,
            filename=artifact.filename,
        )
    except Exception as exc:
        _raise_error(exc)


async def _first_frame(websocket: WebSocket) -> dict[str, Any]:
    try:
        value = await websocket.receive_json()
    except (ValueError, json.JSONDecodeError) as exc:
        raise ClientToolAuthenticationError("Client host first frame must be JSON.") from exc
    if not isinstance(value, dict):
        raise ClientToolAuthenticationError("Client host first frame must be an object.")
    return value


@router.websocket("/client-tools/connect")
async def connect_client_tool_host(websocket: WebSocket) -> None:
    await websocket.accept()
    connection_id = f"conn_{uuid.uuid4().hex}"
    host_id = ""
    try:
        first = await _first_frame(websocket)
        message_type = str(first.get("type") or "")
        capabilities = (
            list(first.get("capabilities") or [])
            if isinstance(first.get("capabilities"), list)
            else []
        )
        schema_hashes = (
            dict(first.get("schema_hashes") or {})
            if isinstance(first.get("schema_hashes"), dict)
            else {}
        )
        version = str(first.get("version") or "")
        if message_type == "pair":
            host, token = get_store().consume_pairing(
                str(first.get("pairing_code") or ""),
                version=version,
                capabilities=capabilities,
                schema_hashes=schema_hashes,
            )
            host_id = host.host_id
            await websocket.send_json(
                {
                    "type": "welcome",
                    "protocol": "modelmirror-client-tools-v1",
                    "host_id": host.host_id,
                    "host_token": token,
                    "token_prefix": host.token_prefix,
                    "paired": True,
                    "heartbeat_seconds": 20,
                }
            )
        elif message_type == "authenticate":
            host_id = str(first.get("host_id") or "")
            host = get_store().authenticate(
                host_id, str(first.get("host_token") or "")
            )
            await websocket.send_json(
                {
                    "type": "welcome",
                    "protocol": "modelmirror-client-tools-v1",
                    "host_id": host.host_id,
                    "token_prefix": host.token_prefix,
                    "paired": False,
                    "heartbeat_seconds": 20,
                }
            )
        else:
            raise ClientToolAuthenticationError(
                "First frame must be pair or authenticate."
            )

        get_store().connect_host(
            host_id,
            connection_id=connection_id,
            version=version,
            capabilities=capabilities,
            schema_hashes=schema_hashes,
            bound_tab=(
                dict(first.get("bound_tab") or {})
                if isinstance(first.get("bound_tab"), dict)
                else {}
            ),
        )
        await get_connections().attach(host_id, connection_id, websocket)
        if _coordinator is not None:
            _coordinator.wake()

        while True:
            message = await websocket.receive_json()
            if not isinstance(message, dict):
                continue
            message_type = str(message.get("type") or "")
            if message_type in {"heartbeat", "host_state"}:
                get_store().heartbeat(
                    host_id,
                    connection_id=connection_id,
                    bound_tab=(
                        dict(message.get("bound_tab") or {})
                        if isinstance(message.get("bound_tab"), dict)
                        else None
                    ),
                )
                await websocket.send_json({"type": "heartbeat", "ok": True})
            elif message_type == "tool_accepted":
                get_store().mark_running(
                    str(message.get("request_id") or ""), host_id=host_id
                )
            elif message_type == "tool_result":
                get_store().complete_request(
                    str(message.get("request_id") or ""),
                    host_id=host_id,
                    operation_id=str(message.get("operation_id") or ""),
                    tool_call_id=str(message.get("tool_call_id") or ""),
                    result=str(message.get("result") or ""),
                    metadata=(
                        dict(message.get("metadata") or {})
                        if isinstance(message.get("metadata"), dict)
                        else {}
                    ),
                )
                if _coordinator is not None:
                    _coordinator.wake()
            elif message_type == "tool_error":
                get_store().fail_request(
                    str(message.get("request_id") or ""),
                    host_id=host_id,
                    operation_id=str(message.get("operation_id") or ""),
                    tool_call_id=str(message.get("tool_call_id") or ""),
                    error=str(message.get("error") or "Client tool failed."),
                )
                if _coordinator is not None:
                    _coordinator.wake()
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        try:
            await websocket.send_json({"type": "error", "message": str(exc)[:500]})
            await websocket.close(code=4003)
        except Exception:
            pass
    finally:
        if host_id:
            await get_connections().detach(host_id, connection_id)
