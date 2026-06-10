import os
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/api/dify", tags=["dify"])

DEFAULT_DIFY_API_BASE_URL = "http://localhost:5001/v1"


def dify_config() -> tuple[str, str]:
    base_url = os.getenv("DIFY_API_BASE_URL", DEFAULT_DIFY_API_BASE_URL).rstrip("/")
    api_key = os.getenv("DIFY_API_KEY", "").strip()
    return base_url, api_key


def dify_headers() -> dict[str, str]:
    _, api_key = dify_config()
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def require_api_key() -> None:
    _, api_key = dify_config()
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="Dify API Key 未配置，请在 server/.env 中设置 DIFY_API_KEY。",
        )


def upstream_error_message(exc: httpx.HTTPStatusError) -> str:
    try:
        payload: Any = exc.response.json()
    except ValueError:
        payload = exc.response.text

    if isinstance(payload, dict):
        message = payload.get("message") or payload.get("error") or payload.get("detail")
        if message:
            return str(message)
    return str(payload)[:500] or "Dify 服务返回错误。"


@router.get("/health")
async def dify_health() -> dict[str, str]:
    base_url, api_key = dify_config()
    return {
        "status": "configured" if api_key else "missing_api_key",
        "base_url": base_url,
    }


@router.get("/apps")
async def list_dify_apps() -> Any:
    require_api_key()
    base_url, _ = dify_config()
    async with httpx.AsyncClient(timeout=30) as client:
      try:
          response = await client.get(f"{base_url}/apps", headers=dify_headers())
          response.raise_for_status()
          return response.json()
      except httpx.HTTPStatusError as exc:
          raise HTTPException(
              status_code=exc.response.status_code,
              detail=upstream_error_message(exc),
          ) from exc
      except httpx.HTTPError as exc:
          raise HTTPException(status_code=502, detail=f"无法连接 Dify 服务：{exc}") from exc


@router.post("/workflow/run")
async def run_dify_workflow(payload: dict[str, Any]) -> StreamingResponse:
    require_api_key()
    base_url, _ = dify_config()
    payload = {**payload, "response_mode": payload.get("response_mode", "streaming")}

    async def event_stream():
        async with httpx.AsyncClient(timeout=None) as client:
            try:
                async with client.stream(
                    "POST",
                    f"{base_url}/workflows/run",
                    headers=dify_headers(),
                    json=payload,
                ) as response:
                    response.raise_for_status()
                    async for chunk in response.aiter_bytes():
                        yield chunk
            except httpx.HTTPStatusError as exc:
                message = upstream_error_message(exc)
                yield f'event: error\ndata: {{"error": "{message}"}}\n\n'.encode("utf-8")
            except httpx.HTTPError as exc:
                yield f'event: error\ndata: {{"error": "无法连接 Dify 服务：{exc}"}}\n\n'.encode(
                    "utf-8",
                )

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.api_route(
    "/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
)
async def generic_dify_proxy(path: str, request: Request) -> Any:
    require_api_key()
    base_url, _ = dify_config()
    body = await request.body()
    query = str(request.url.query)
    target = f"{base_url}/{path}"
    if query:
        target = f"{target}?{query}"

    async with httpx.AsyncClient(timeout=60) as client:
        try:
            response = await client.request(
                request.method,
                target,
                content=body or None,
                headers=dify_headers(),
            )
            response.raise_for_status()
            if not response.content:
                return {}
            return response.json()
        except httpx.HTTPStatusError as exc:
            raise HTTPException(
                status_code=exc.response.status_code,
                detail=upstream_error_message(exc),
            ) from exc
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"无法连接 Dify 服务：{exc}") from exc
