from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from finance_advisor.market.symbols import get_symbol_catalog
from finance_advisor.schemas import error_response, success_response
from finance_advisor.web.common import (
    PROJECT_ROOT,
    get_cache_dir,
    get_fixture_path,
    get_market_service,
)
from finance_advisor.web.routes import advisor, market, portfolio, risk, sessions


def _sanitize_validation_errors(exc: RequestValidationError) -> list[dict[str, Any]]:
    return [
        {
            "loc": [str(part) for part in item.get("loc", [])],
            "message": str(item.get("msg", "")),
            "type": str(item.get("type", "")),
        }
        for item in exc.errors()
    ]


def _index_response(static_dir: Path) -> FileResponse:
    return FileResponse(
        static_dir / "index.html",
        headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"},
    )


def _safe_static_file(static_dir: Path, requested_path: str) -> Path | None:
    if not requested_path or requested_path.startswith(("/", "\\")):
        return None
    root = static_dir.resolve()
    candidate = (root / requested_path).resolve()
    if not candidate.is_relative_to(root) or not candidate.is_file():
        return None
    return candidate


def _missing_frontend_response() -> HTMLResponse:
    return HTMLResponse(
        """
        <!doctype html>
        <html lang="zh-CN">
          <head>
            <meta charset="utf-8" />
            <title>金融工作台后端已启动</title>
            <style>
              body { font-family: system-ui, sans-serif; margin: 40px; color: #17212b; }
              code { background: #f4f6f7; padding: 2px 6px; border-radius: 4px; }
            </style>
          </head>
          <body>
            <h1>金融工作台后端已启动</h1>
            <p>FastAPI 可用，前端构建尚未找到。</p>
            <p>健康检查：<code>/api/health</code></p>
            <p>行情对比：<code>POST /api/market/compare</code></p>
          </body>
        </html>
        """.strip()
    )


def create_app(static_dir: Path | None = None) -> FastAPI:
    resolved_static_dir = static_dir or PROJECT_ROOT / "frontend" / "dist"
    app = FastAPI(
        title="Financial Advisor Workspace API",
        version="0.2.0",
        description="Local-only BFF for deterministic finance advisor workflows.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        _request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=error_response(
                "validation_error",
                "请求参数无效",
                data={"validation_errors": _sanitize_validation_errors(exc)},
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        _request: Request,
        exc: StarletteHTTPException,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=error_response(
                "not_found" if exc.status_code == 404 else "http_error",
                "API 不存在" if exc.status_code == 404 else str(exc.detail),
            ),
        )

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        cache_dir = get_cache_dir()
        cache_dir.mkdir(parents=True, exist_ok=True)
        fixture_path = get_fixture_path()
        service = get_market_service()
        return success_response(
            {
                "status": "healthy",
                "service": "finance-advisor-web",
                "akshare_installed": service.live.available(),
                "tushare_configured": bool(
                    service.supplemental and service.supplemental.available()
                ),
                "provider_priority": ["akshare", "tushare", "cache"],
                "cache_directory": str(cache_dir),
                "cache_writable": os.access(cache_dir, os.W_OK),
                "fixture_path": str(fixture_path),
                "fixture_available": service.fixture.available(),
                "force_fixture": service.force_fixture,
                "supported_symbol_count": len(get_symbol_catalog().all()),
                "frontend_dist": str(resolved_static_dir),
                "frontend_available": (resolved_static_dir / "index.html").is_file(),
            },
            source="system",
        )

    app.include_router(market.router, prefix="/api/market", tags=["Market"])
    app.include_router(risk.router, prefix="/api/risk", tags=["Risk"])
    app.include_router(portfolio.router, prefix="/api/portfolio", tags=["Portfolio"])
    app.include_router(advisor.router, prefix="/api/advisor", tags=["Advisor"])
    app.include_router(sessions.router, prefix="/api/sessions", tags=["Sessions"])

    has_frontend = (resolved_static_dir / "index.html").is_file()
    assets_dir = resolved_static_dir / "assets"
    if has_frontend and assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    @app.get("/", response_model=None)
    def root() -> FileResponse | HTMLResponse:
        if has_frontend:
            return _index_response(resolved_static_dir)
        return _missing_frontend_response()

    @app.get("/{full_path:path}", response_model=None)
    def spa_fallback(full_path: str) -> FileResponse | HTMLResponse | JSONResponse:
        if full_path.startswith("api/"):
            return JSONResponse(
                status_code=404,
                content=error_response("not_found", "API 不存在"),
            )
        if not has_frontend:
            return _missing_frontend_response()
        static_file = _safe_static_file(resolved_static_dir, full_path)
        if static_file is not None:
            return FileResponse(static_file)
        return _index_response(resolved_static_dir)

    return app


app = create_app()
