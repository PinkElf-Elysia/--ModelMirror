"""ModelMirror MCP integration package.

This package intentionally lives at ``server/mcp``. When the backend is started
from the repository root it is imported as ``server.mcp`` and does not conflict
with the official ``mcp`` SDK. When developers start FastAPI from ``server/`` as
``uvicorn main:app``, however, Python may see this directory as the top-level
``mcp`` package. To keep both launch styles working, we extend the package path
to include the installed SDK package so imports such as ``mcp.client.stdio`` can
still resolve.
"""

from __future__ import annotations

from pathlib import Path
import site

_local_package_dir = Path(__file__).resolve().parent

for _site_dir in site.getsitepackages():
    _sdk_package_dir = Path(_site_dir) / "mcp"
    if _sdk_package_dir.exists() and _sdk_package_dir != _local_package_dir:
        sdk_path = str(_sdk_package_dir)
        if sdk_path not in __path__:
            __path__.append(sdk_path)
