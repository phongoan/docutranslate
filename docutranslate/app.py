# SPDX-FileCopyrightText: 2025 QinHan
# SPDX-License-Identifier: MPL-2.0
# docutranslate.app.py
import asyncio
import base64
import binascii
import json
import logging
import os
import socket
import uuid
from contextlib import asynccontextmanager, closing
from pathlib import Path
from typing import (
    List,
    Optional,
    Literal,
)

import httpx
import uvicorn
from fastapi import (
    FastAPI,
    HTTPException,
    APIRouter,
    Body,
    Path as FastApiPath,
    UploadFile,
    File,
    Form,
    Request
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import (
    get_swagger_ui_html,
    get_swagger_ui_oauth2_redirect_html,
    get_redoc_html,
)
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import (
    BaseModel,
    Field,
    ConfigDict,
    Json,
    TypeAdapter,
)

from docutranslate import __version__
from docutranslate.core.schemas import TranslatePayload
from docutranslate.core.params import EMPTY_TEXT_OVERRIDE_FIELDS, INHERIT
from docutranslate.core.task_status import task_status, task_statistics, default_statistics
from docutranslate.exporter.md.types import ConvertEngineType
from docutranslate.logger import global_logger
# Shared server layer imports
from docutranslate.server import (
    TranslationService,
    get_translation_service,
    MEDIA_TYPES,
)
from docutranslate.config import PORT, MAX_UPLOAD_MB
from docutranslate.translator import default_params
from docutranslate.utils.resource_utils import resource_path
from docutranslate.utils.utils import mask_secrets

# MCP integration imports (optional)
try:
    import docutranslate.mcp
    from docutranslate.mcp import get_sse_app
    MCP_AVAILABLE = docutranslate.mcp.MCP_AVAILABLE
except ImportError:
    MCP_AVAILABLE = False

# --- Shared Translation Service ---
translation_service: TranslationService = get_translation_service()

_MAX_UPLOAD_BYTES = int(MAX_UPLOAD_MB * 1024 * 1024) if MAX_UPLOAD_MB and MAX_UPLOAD_MB > 0 else 0


def _enforce_upload_limit(size_bytes: int, what: str = "tệp") -> None:
    """Bộ nhớ của một tiến trình có hạn; vượt giới hạn thì trả về 413 thay vì để tiến trình bị OOM."""
    if _MAX_UPLOAD_BYTES and size_bytes > _MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=(
                f"{what} quá lớn: {size_bytes / 1024 / 1024:.1f}MB vượt quá giới hạn "
                f"{MAX_UPLOAD_MB:.0f}MB(có thể điều chỉnh qua DOCUTRANSLATE_MAX_UPLOAD_MB)."
            ),
        )


class MaxBodySizeMiddleware:
    """按 Content-Length 拒绝超大请求体（chunked 请求由各端点读取后再判断）。"""

    def __init__(self, app, max_bytes: int = 0):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "http" and self.max_bytes > 0:
            for name, value in scope.get("headers") or []:
                if name == b"content-length":
                    try:
                        length = int(value)
                    except (TypeError, ValueError):
                        break
                    if length > self.max_bytes:
                        response = JSONResponse(
                            status_code=413,
                            content={
                                "detail": (
                                    f"Nội dung yêu cầu quá lớn: {length / 1024 / 1024:.1f}MB vượt quá giới hạn "
                                    f"{MAX_UPLOAD_MB:.0f}MB(có thể điều chỉnh qua DOCUTRANSLATE_MAX_UPLOAD_MB)."
                                )
                            },
                        )
                        await response(scope, receive, send)
                        return
                    break
        await self.app(scope, receive, send)

# --- FastAPI application and router setup ---
tags_metadata = [
    {
        "name": "Service API",
        "description": "API dịch vụ cốt lõi, dùng để gửi, quản lý và tải xuống các tác vụ dịch.",
    },
    {
        "name": "Application",
        "description": "Các endpoint của chính ứng dụng, như thông tin meta và tham số mặc định.",
    },
    {
        "name": "Temp",
        "description": "Endpoint dùng để kiểm thử.",
    },
]


# --- Application lifespan ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    global httpx_client
    app.state.main_event_loop = asyncio.get_running_loop()
    httpx_client = httpx.AsyncClient()

    # Initialize the translation service
    translation_service.initialize(httpx_client, app.state.main_event_loop)
    translation_service.clear_all()

    global_logger.propagate = False
    global_logger.setLevel(logging.INFO)
    global_logger.info("Ứng dụng đã khởi động xong, trạng thái đa tác vụ đã được khởi tạo")
    if hasattr(app.state, "port_to_use"):
        if getattr(app.state, "with_mcp", False) and MCP_AVAILABLE:
            global_logger.info(
                "MCP SSE endpoint: http://127.0.0.1:%s/mcp/sse",
                app.state.port_to_use,
            )
        global_logger.info(
            "Tài liệu API: http://127.0.0.1:%s/docs", app.state.port_to_use
        )
        global_logger.info(
            "WebUI: http://127.0.0.1:%s", app.state.port_to_use
        )


    yield  # Application running...

    # --- Shutdown phase ---
    global_logger.info("Đang đóng ứng dụng, bắt đầu dọn dẹp tài nguyên")

    # Cleanup all tasks via translation service
    await translation_service.cleanup_all()

    # Close HTTP client
    await httpx_client.aclose()
    global_logger.info("Ứng dụng đã đóng, tài nguyên đã được giải phóng hoàn toàn")


app = FastAPI(
    docs_url=None,
    redoc_url=None,
    lifespan=lifespan,
    title="DocuTranslate API",
    description=f"""
API dịch vụ backend của DocuTranslate, cung cấp các chức năng dịch tài liệu, truy vấn trạng thái, tải xuống kết quả, v.v.

**Lưu ý**: Mọi trạng thái tác vụ đều được lưu trong bộ nhớ của tiến trình dịch vụ; khởi động lại dịch vụ sẽ làm mất toàn bộ thông tin tác vụ.

### Quy trình chính:
1.  **`POST /service/translate`** hoặc **`POST /service/translate/file`**: Gửi tệp cùng tham số dịch có chứa `workflow_type` để khởi động một tác vụ nền. Dịch vụ sẽ tự động tạo và trả về một `task_id` duy nhất.
2.  **`GET /service/status/{{task_id}}`**: Dùng `task_id` đã nhận để thăm dò (poll) endpoint này nhằm lấy trạng thái thời gian thực của tác vụ.
3.  **`GET /service/logs/{{task_id}}`**: (Tùy chọn) Lấy nhật ký dịch theo thời gian thực.
4.  **`GET /service/download/{{task_id}}/{{file_type}}`**: Sau khi tác vụ hoàn thành (khi `download_ready` là `true`), tải tệp kết quả qua endpoint này.
5.  **`GET /service/attachment/{{task_id}}/{{identifier}}`**: (Tùy chọn) Nếu tác vụ tạo ra tệp đính kèm (như bảng thuật ngữ), tải xuống qua endpoint này.
6.  **`GET /service/content/{{task_id}}/{{file_type}}`**: Sau khi tác vụ hoàn thành (khi `download_ready` là `true`), lấy nội dung tệp ở định dạng JSON.
7.  **`POST /service/cancel/{{task_id}}`**: (Tùy chọn) Hủy một tác vụ đang chạy.
8.  **`POST /service/release/{{task_id}}`**: (Tùy chọn) Khi không còn cần tác vụ, giải phóng toàn bộ tài nguyên nó chiếm trên máy chủ, gồm cả tệp tạm.

**Phiên bản**: {__version__}
""",
    version=__version__,
)
service_router = APIRouter(prefix="/service", tags=["Service API"])
if _MAX_UPLOAD_BYTES:
    app.add_middleware(MaxBodySizeMiddleware, max_bytes=_MAX_UPLOAD_BYTES)
# 前端静态资源的 Content-Type 由这里显式决定，不经过 mimetypes。
#
# Starlette 的 FileResponse 在未指定 media_type 时执行
# `guess_type(filename)[0] or "text/plain"`，而 Windows 上 mimetypes 会读取注册表
# `HKEY_CLASSES_ROOT\<ext>\Content Type` 并覆盖 Python 内置表。把 .js 注册成
# text/plain 的机器上（部分编辑器/工具会这么注册），模块脚本会以 text/plain 发出，
# 浏览器按 HTML 规范拒绝执行 `type="module"` 脚本 —— 表现就是 UI 白屏，控制台报
# "Expected a JavaScript module script but the server responded with a MIME type of
# text/plain"。.mjs 与 .woff2 在内置表里本就缺失，健康机器上同样是 text/plain。
_STATIC_MEDIA_TYPES = {
    ".js": "text/javascript",
    ".mjs": "text/javascript",
    ".css": "text/css",
    ".html": "text/html",
    ".htm": "text/html",
    ".json": "application/json",
    ".map": "application/json",
    ".txt": "text/plain",
    ".csv": "text/csv",
    ".xml": "application/xml",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".avif": "image/avif",
    ".ico": "image/x-icon",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".ttf": "font/ttf",
    ".otf": "font/otf",
    ".eot": "application/vnd.ms-fontobject",
    ".wasm": "application/wasm",
    ".pdf": "application/pdf",
    ".webmanifest": "application/manifest+json",
}


class _WebStaticFiles(StaticFiles):
    """/static 的静态文件按扩展名强制正确的 Content-Type（见上）。"""

    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        media_type = _STATIC_MEDIA_TYPES.get(Path(path).suffix.lower())
        if media_type and response.status_code == 200:
            response.headers["content-type"] = media_type
        return response


STATIC_DIR = resource_path("static")
app.mount("/static", _WebStaticFiles(directory=STATIC_DIR), name="static")


# ===================================================================
# --- MCP Integration (optional) ---
# ===================================================================

def setup_mcp_integration(
        enable: bool = False,
        host: str = "127.0.0.1",
        port: int = 8000,
        enable_cors: bool = False,
        allow_origin_regex: str = r"^(https?://.*|null|file://.*)$",
) -> Optional[TranslationService]:
    """
    Setup MCP integration with shared translation service.

    Args:
        enable: Whether to enable MCP SSE endpoint
        host: Host for MCP
        port: Port for MCP

    Returns:
        TranslationService instance if MCP is enabled, None otherwise
    """
    if not enable:
        return None

    if not MCP_AVAILABLE:
        global_logger.warning(
            "Chưa cài đặt phụ thuộc MCP; nếu cần --with-mcp, hãy cài docutranslate[mcp]"
        )
        return None

    try:
        global_logger.info("Đang khởi tạo tích hợp MCP")

        # Mount MCP at /mcp path - pass the shared translation service
        # and the actual host/port that the web server is running on
        mcp_app = get_sse_app(
            translation_service=translation_service,
            host=host,
            port=port,
            enable_cors=enable_cors,
            allow_origin_regex=allow_origin_regex,
        )
        app.mount("/mcp", mcp_app, name="mcp")

        return translation_service
    except Exception as e:
        global_logger.exception("Khởi tạo tích hợp MCP thất bại: %s", e)
        return None


def get_mcp_translation_service() -> Optional[TranslationService]:
    """Get the shared translation service (if available)."""
    return translation_service


# ===================================================================
# --- Pydantic Models for Service API ---
# ===================================================================


class TranslateServiceRequest(BaseModel):
    file_name: str = Field(
        ...,
        description="Tên tệp gốc đã tải lên, gồm cả phần mở rộng.",
        examples=[
            "my_paper.pdf",
            "chapter1.txt",
            "data.xlsx",
            "video.srt",
            "my_book.epub",
            "index.html",
            "dialogue.ass",
            "presentation.pptx",
        ],
    )
    file_content: str = Field(
        ..., description="Nội dung tệp mã hóa Base64.", examples=["JVBERi0xLjcKJeLjz9MKMSAwIG9iago8PC/..."]
    )
    payload: TranslatePayload = Field(
        ..., description="Payload chứa loại workflow và các tham số tương ứng."
    )

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "file_name": "auto_detect_doc.pdf",
                    "file_content": "JVBERi0xLjcKJeLjz9MKMSAwIG9iago8PC/...",
                    "payload": {
                        "workflow_type": "auto",
                        "base_url": "https://api.openai.com/v1",
                        "api_key": "sk-your-api-key-here",
                        "model_id": "gpt-4o",
                        "to_lang": "中文",
                    },
                },
                {
                    "file_name": "local_test.pdf",
                    "file_content": "JVBERi0xLjcKJeLjz9MKMSAwIG9iago8PC/...",
                    "payload": {
                        "workflow_type": "markdown_based",
                        "skip_translate": True,
                        "to_lang": "中文",
                        "convert_engine": "mineru_deploy",
                        "mineru_deploy_base_url": "http://127.0.0.1:8000",
                        "mineru_deploy_backend": "pipeline",
                        "mineru_deploy_formula_enable": True,
                        "mineru_deploy_start_page_id": 0,
                        "mineru_deploy_end_page_id": 5,
                    },
                },
            ]
        }
    )


# ===================================================================
# --- Service Endpoints (/service) ---
# ===================================================================


@service_router.post(
    "/translate",
    summary="Gửi tác vụ dịch (điểm vào thống nhất)",
    description="""
Nhận một yêu cầu JSON chứa nội dung tệp (mã hóa Base64) và tham số workflow, rồi khởi động một tác vụ dịch nền.

- **Chọn workflow**: `payload.workflow_type` quyết định loại tác vụ (như `markdown_based`, `txt`, `json`, `xlsx`, `docx`, `srt`, `epub`, `html`, `ass`, `pptx`, `auto`).
- **Chế độ Auto**: Khi đặt là `auto`, backend sẽ tự chọn workflow phù hợp nhất dựa trên phần mở rộng của `file_name`.
- **Tham số động**: Tùy workflow được chọn, API cần các bộ tham số khác nhau. Vui lòng xem Schema hoặc ví dụ bên dưới.
- **Xử lý bất đồng bộ**: Endpoint này trả về ID tác vụ ngay lập tức; client cần thăm dò endpoint trạng thái để biết tiến độ.
""",
    responses={
        200: {
            "description": "Tác vụ dịch đã được khởi động thành công.",
            "content": {
                "application/json": {
                    "example": {
                        "task_started": True,
                        "task_id": "a1b2c3d4",
                        "message": "Tác vụ dịch đã được khởi động thành công, vui lòng chờ...",
                    }
                }
            },
        },
        400: {"description": "Nội dung yêu cầu không hợp lệ, ví dụ giải mã Base64 thất bại."},
        429: {
            "description": "Máy chủ đã có một tác vụ cùng ID đang xử lý (về lý thuyết không xảy ra vì ID được tạo mới)."
        },
        500: {"description": "Đã xảy ra lỗi không xác định khi khởi động tác vụ nền."},
    },
)
async def service_translate(
        request: TranslateServiceRequest = Body(
            ..., description="Tham số chi tiết và nội dung tệp của tác vụ dịch."
        )
):
    task_id = uuid.uuid4().hex[:8]

    try:
        # Accept line-wrapped Base64, but reject other ignored characters.
        _enforce_upload_limit(len(request.file_content) * 3 // 4, "nội dung tệp")
        file_contents = base64.b64decode("".join(request.file_content.split()), validate=True)
        _enforce_upload_limit(len(file_contents), "nội dung tệp")
    except (binascii.Error, TypeError) as e:
        raise HTTPException(status_code=400, detail=f"Nội dung tệp Base64 không hợp lệ: {mask_secrets(str(e))}")

    try:
        response_data = await translation_service.start_translation(
            task_id=task_id,
            payload=request.payload,
            file_contents=file_contents,
            original_filename=request.file_name,
        )
        return JSONResponse(content=response_data)
    except HTTPException as e:
        if e.status_code == 429:
            return JSONResponse(
                status_code=e.status_code,
                content={"task_started": False, "message": e.detail},
            )
        if e.status_code == 500:
            return JSONResponse(
                status_code=e.status_code,
                content={"task_started": False, "message": e.detail},
            )
        raise e


@service_router.post(
    "/translate/file",
    summary="Gửi tác vụ dịch (tải tệp lên)",
    description="""
Tải tệp lên bằng `multipart/form-data` và khởi động tác vụ dịch.

Endpoint này phù hợp để tải trực tiếp tệp nhị phân (như PDF, Docx, v.v.), không cần mã hóa Base64 trước.
""",
    responses={
        200: {
            "description": "Tác vụ dịch đã được khởi động thành công.",
            "content": {
                "application/json": {
                    "example": {
                        "task_started": True,
                        "task_id": "a1b2c3d4",
                        "message": "Tác vụ dịch đã được khởi động thành công, vui lòng chờ...",
                    }
                }
            },
        },
        422: {"description": "Xác thực tham số yêu cầu thất bại, ví dụ JSON sai định dạng."},
        429: {
            "description": "Máy chủ đã có một tác vụ cùng ID đang xử lý (về lý thuyết không xảy ra vì ID được tạo mới)."
        },
        500: {"description": "Đã xảy ra lỗi không xác định khi khởi động tác vụ nền."},
    },
)
async def service_translate_file(
        file: UploadFile = File(..., description="Tệp cần dịch"),
        payload: Json[TranslatePayload] = Form(
            ..., description="Chuỗi JSON chứa tham số workflow (xem chi tiết trong tài liệu API)."
        ),
):
    task_id = uuid.uuid4().hex[:8]

    try:
        _enforce_upload_limit(getattr(file, "size", None) or 0)
        file_contents = await file.read()
        _enforce_upload_limit(len(file_contents))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Đọc tệp tải lên thất bại: {mask_secrets(str(e))}")

    try:
        response_data = await translation_service.start_translation(
            task_id=task_id,
            payload=payload,
            file_contents=file_contents,
            original_filename=file.filename or "uploaded_file",
        )
        return JSONResponse(content=response_data)
    except HTTPException as e:
        if e.status_code == 429:
            return JSONResponse(
                status_code=e.status_code,
                content={"task_started": False, "message": e.detail},
            )
        if e.status_code == 500:
            return JSONResponse(
                status_code=e.status_code,
                content={"task_started": False, "message": e.detail},
            )
        raise e


@service_router.post(
    "/cancel/{task_id}",
    summary="Hủy tác vụ dịch",
    description="Hủy một tác vụ dịch đang chạy theo ID tác vụ. Nếu tác vụ đã hoàn thành, thất bại hoặc đã bị hủy thì sẽ trả về lỗi.",
    responses={
        200: {"description": "Hủy tác vụ thành công."},
        404: {"description": "ID tác vụ không tồn tại."},
        400: {"description": "Tác vụ đã kết thúc, không thể hủy."},
    },
)
async def service_cancel_translate(
        task_id: str = FastApiPath(..., description="ID tác vụ cần hủy", examples=["a1b2c3d4"])
):
    return translation_service.cancel_task(task_id)


@service_router.post(
    "/release/{task_id}",
    summary="Giải phóng tài nguyên tác vụ",
    description="Giải phóng toàn bộ tài nguyên mà tác vụ chiếm trên máy chủ theo ID tác vụ, gồm trạng thái, nhật ký và tệp kết quả dịch đã lưu đệm. Nếu tác vụ đang chạy, sẽ thử hủy trước. Thao tác này không thể hoàn tác.",
    responses={
        200: {"description": "Giải phóng tài nguyên tác vụ thành công."},
        404: {"description": "ID tác vụ không tồn tại."},
    },
)
async def service_release_task(
        task_id: str = FastApiPath(..., description="ID tác vụ cần giải phóng tài nguyên", examples=["a1b2c3d4"])
):
    result = await translation_service.release_task(task_id)
    if not result["released"]:
        return JSONResponse(
            status_code=404,
            content=result,
        )
    return JSONResponse(content=result)


@service_router.get(
    "/status/{task_id}",
    summary="Lấy trạng thái tác vụ",
    description="Lấy trạng thái hiện tại của tác vụ theo ID tác vụ. Khi `download_ready` là `true`, các đối tượng `downloads` và `attachment` sẽ chứa liên kết tải xuống khả dụng.",
    responses={
        200: {
            "description": "Lấy trạng thái tác vụ thành công.",
            "content": {
                "application/json": {
                    "examples": {
                        "processing": {
                            "summary": "Đang chạy",
                            "value": {
                                "task_id": "a1b2c3d4",
                                "is_processing": True,
                                "status_message": "Đang xử lý 'annual_report.pdf'...",
                                "error_flag": False,
                                "download_ready": False,
                                "progress_percent": 45,
                                "original_filename_stem": "annual_report",
                                "original_filename": "annual_report.pdf",
                                "task_start_time": 1678889400.0,
                                "task_end_time": 0,
                                "downloads": {},
                                "attachment": {},
                                "statistics": {
                                    "glossary": None,
                                    "translation": {
                                        "input_tokens": 1500,
                                        "cached_tokens": 0,
                                        "output_tokens": 2000,
                                        "reasoning_tokens": 500,
                                        "total_tokens": 3500,
                                        "request_count": 3,
                                        "unresolved_errors": 0,
                                        "unresolved_error_rate": 0.0
                                    },
                                    "total": {
                                        "input_tokens": 1500,
                                        "cached_tokens": 0,
                                        "output_tokens": 2000,
                                        "reasoning_tokens": 500,
                                        "total_tokens": 3500,
                                        "request_count": 3,
                                        "unresolved_errors": 0,
                                        "unresolved_error_rate": 0.0
                                    }
                                },
                            },
                        },
                        "completed": {
                            "summary": "Đã hoàn thành",
                            "value": {
                                "task_id": "b2865b93",
                                "is_processing": False,
                                "status_message": "Dịch thành công! Mất 123.45 giây.",
                                "error_flag": False,
                                "download_ready": True,
                                "progress_percent": 100,
                                "original_filename_stem": "my_paper",
                                "original_filename": "my_paper.pdf",
                                "task_start_time": 1678889400.123,
                                "task_end_time": 1678889523.573,
                                "downloads": {
                                    "html": "/service/download/b2865b93/html",
                                    "markdown": "/service/download/b2865b93/markdown",
                                },
                                "attachment": {},
                                "statistics": {
                                    "glossary": {
                                        "input_tokens": 100,
                                        "cached_tokens": 0,
                                        "output_tokens": 50,
                                        "reasoning_tokens": 0,
                                        "total_tokens": 150,
                                        "request_count": 1,
                                        "unresolved_errors": 0,
                                        "unresolved_error_rate": 0.0
                                    },
                                    "translation": {
                                        "input_tokens": 5000,
                                        "cached_tokens": 200,
                                        "output_tokens": 6000,
                                        "reasoning_tokens": 1500,
                                        "total_tokens": 11100,
                                        "request_count": 10,
                                        "unresolved_errors": 0,
                                        "unresolved_error_rate": 0.0
                                    },
                                    "total": {
                                        "input_tokens": 5100,
                                        "cached_tokens": 200,
                                        "output_tokens": 6050,
                                        "reasoning_tokens": 1500,
                                        "total_tokens": 11250,
                                        "request_count": 11,
                                        "unresolved_errors": 0,
                                        "unresolved_error_rate": 0.0
                                    }
                                },
                            },
                        },
                    }
                }
            },
        },
        404: {"description": "ID tác vụ được chỉ định không tồn tại."},
    },
)
async def service_get_status(
        task_id: str = FastApiPath(
            ..., description="ID của tác vụ cần truy vấn trạng thái", examples=["b2865b93"]
        )
):
    task_state = translation_service.get_task_state(task_id)
    if not task_state:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy ID tác vụ '{task_id}'.")

    downloads = {}
    if task_state.get("download_ready") and task_state.get("downloadable_files"):
        for file_type in task_state["downloadable_files"].keys():
            downloads[file_type] = f"/service/download/{task_id}/{file_type}"

    attachments = {}
    if task_state.get("download_ready") and task_state.get("attachment_files"):
        for identifier in task_state["attachment_files"].keys():
            attachments[identifier] = f"/service/attachment/{task_id}/{identifier}"

    statistics = task_statistics(task_state)

    return JSONResponse(
        content={
            "task_id": task_id,
            "is_processing": task_state["is_processing"],
            "status": task_status(task_state),
            "status_message": task_state["status_message"],
            "error_flag": task_state["error_flag"],
            "cancelled": task_state.get("cancelled", False),
            "download_ready": task_state["download_ready"],
            "progress_percent": task_state.get("progress_percent", 0),
            "original_filename_stem": task_state["original_filename_stem"],
            "original_filename": task_state.get("original_filename"),
            "task_start_time": task_state["task_start_time"],
            "task_end_time": task_state["task_end_time"],
            "downloads": downloads,
            "attachment": attachments,
            "statistics": statistics,
        }
    )


def _get_default_statistics() -> dict:
    return default_statistics()


@service_router.get(
    "/logs/{task_id}",
    summary="Lấy nhật ký gia tăng của tác vụ",
    description="Lấy nhật ký gia tăng của tác vụ theo dạng luồng. Mỗi lần client gọi endpoint này sẽ nhận các dòng nhật ký mới phát sinh kể từ lần gọi trước.",
    responses={
        200: {"description": "Trả về nhật ký gia tăng thành công."},
        404: {"description": "ID tác vụ không tồn tại."},
    },
)
async def service_get_logs(
        task_id: str = FastApiPath(..., description="ID tác vụ cần lấy nhật ký", examples=["a1b2c3d4"])
):
    new_logs = await translation_service.get_new_logs(task_id)
    return JSONResponse(content={"logs": new_logs})


FileType = Literal[
    "markdown",
    "markdown_zip",
    "html",
    "txt",
    "json",
    "xlsx",
    "csv",
    "docx",
    "srt",
    "epub",
    "ass",
    "pptx",
]


@service_router.get(
    "/download/{task_id}/{file_type}",
    summary="Tải xuống tệp kết quả dịch",
    responses={
        200: {
            "description": "Trả về luồng tệp thành công. Tên tệp được chỉ định qua header Content-Disposition.",
        },
        404: {
            "description": "ID tác vụ không tồn tại, hoặc tác vụ không hỗ trợ loại tệp được yêu cầu, hoặc tệp tạm đã mất."
        },
        500: {"description": "Lỗi nội bộ khi đọc tệp trên máy chủ."},
    },
)
async def service_download_file(
        task_id: str = FastApiPath(
            ..., description="ID của tác vụ đã hoàn thành", examples=["b2865b93"]
        ),
        file_type: FileType = FastApiPath(
            ...,
            description="Loại tệp cần tải xuống.",
            examples=["html", "json", "csv", "docx", "srt", "epub", "ass", "pptx"],
        ),
):
    file_info = translation_service.get_downloadable_file_path(task_id, file_type)
    if not file_info or not os.path.exists(file_info.get("path")):
        raise HTTPException(
            status_code=404,
            detail=f"Tác vụ '{task_id}' không hỗ trợ tải xuống tệp loại '{file_type}', hoặc tệp đã mất.",
        )

    file_path = file_info["path"]
    filename = file_info["filename"]
    media_type = MEDIA_TYPES.get(file_type, "application/octet-stream")

    return FileResponse(path=file_path, media_type=media_type, filename=filename)


@service_router.get(
    "/attachment/{task_id}/{identifier}",
    summary="Tải xuống tệp đính kèm",
    description="Tải xuống tệp bổ sung được tạo trong quá trình dịch, như bảng thuật ngữ tự động tạo, theo ID tác vụ và định danh tệp đính kèm.",
    responses={
        200: {
            "description": "Trả về luồng tệp thành công. Tên tệp được chỉ định qua header Content-Disposition.",
        },
        404: {
            "description": "ID tác vụ không tồn tại, hoặc tác vụ không có tệp đính kèm được chỉ định, hoặc tệp tạm đã mất."
        },
    },
)
async def service_download_attachment(
        task_id: str = FastApiPath(
            ..., description="ID của tác vụ đã hoàn thành", examples=["g1h2i3j4"]
        ),
        identifier: str = FastApiPath(
            ..., description="Định danh của tệp đính kèm cần tải xuống.", examples=["glossary"]
        ),
):
    attachment_info = translation_service.get_attachment_file_path(task_id, identifier)
    if not attachment_info or not os.path.exists(attachment_info.get("path")):
        raise HTTPException(
            status_code=404,
            detail=f"Tác vụ '{task_id}' không có tệp đính kèm với định danh '{identifier}', hoặc tệp đã mất.",
        )

    file_path = attachment_info["path"]
    filename = attachment_info["filename"]
    media_type = "application/octet-stream"

    return FileResponse(path=file_path, media_type=media_type, filename=filename)


@service_router.get(
    "/glossary/template",
    summary="Tải xuống mẫu bảng thuật ngữ",
    description="Tải xuống mẫu CSV bảng thuật ngữ, gồm cột src và dst, mã hóa UTF-8 with BOM, phù hợp để chỉnh sửa trực tiếp trong Excel.",
)
async def download_glossary_template():
    # UTF-8 with BOM header
    bom = b'\xef\xbb\xbf'
    content = bom + b"src,dst\n<Source Term>,<Target Term>"
    return Response(
        content=content,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=glossary_template.csv"}
    )


@service_router.get(
    "/content/{task_id}/{file_type}",
    summary="Tải xuống nội dung kết quả dịch (JSON)",
    description="""
Lấy nội dung của loại tệp được chỉ định ở định dạng JSON thay vì tải trực tiếp tệp.

- **Cấu trúc trả về**: Trả về một đối tượng JSON gồm tên tệp, loại tệp và chuỗi Base64 của nội dung tệp.
- **Mã hóa nội dung**: Nội dung tệp luôn được mã hóa **Base64**; client cần tự giải mã để sử dụng.
""",
    responses={
        200: {
            "description": "Trả về nội dung tệp thành công.",
        },
        404: {
            "description": "ID tác vụ không tồn tại, hoặc tác vụ không hỗ trợ loại tệp được yêu cầu, hoặc tệp tạm đã mất."
        },
        500: {"description": "Lỗi nội bộ khi đọc tệp trên máy chủ."},
    },
)
async def service_content(
        task_id: str = FastApiPath(
            ..., description="ID của tác vụ đã hoàn thành", examples=["b2865b93"]
        ),
        file_type: FileType = FastApiPath(
            ...,
            description="Loại tệp cần lấy nội dung.",
            examples=["html", "json", "csv", "docx", "srt", "epub", "ass", "pptx"],
        ),
):
    file_info = translation_service.get_downloadable_file_path(task_id, file_type)
    if not file_info or not os.path.exists(file_info.get("path")):
        raise HTTPException(
            status_code=404,
            detail=f"Tác vụ '{task_id}' không hỗ trợ lấy nội dung loại '{file_type}', hoặc tệp đã mất.",
        )

    file_path = file_info["path"]
    filename = file_info["filename"]

    try:
        # 读取 + base64 都在事件循环里做会阻塞所有并发请求（状态轮询、日志、
        # 其他任务的导出），大文件下前端会像卡死一样。
        def _read_and_encode(path: str) -> str:
            with open(path, "rb") as f:
                return base64.b64encode(f.read()).decode("utf-8")

        final_content = await asyncio.to_thread(_read_and_encode, file_path)
        return JSONResponse(
            content={
                "file_type": file_type,
                "filename": filename,
                "content": final_content,
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi nội bộ khi đọc tệp: {mask_secrets(str(e))}")


# ===================================================================
# --- Application endpoints ---
# ===================================================================


@service_router.get("/capabilities", summary="Truy vấn khả năng đầu vào và đầu ra của workflow", tags=["Application"])
def service_capabilities():
    from docutranslate.core.file_types import formats_info
    return formats_info()


@service_router.get(
    "/engin-list",
    summary="Lấy các engine chuyển đổi khả dụng",
    description="Trả về danh sách engine chuyển đổi tài liệu mà dịch vụ hiện hỗ trợ, gồm MinerU Cloud, MinerU Local.",
    tags=["Application"],
    responses={
        200: {
            "description": "Trả về danh sách engine chuyển đổi khả dụng thành công.",
            "content": {
                "application/json": {
                    "example": ["mineru", "mineru_deploy"]
                }
            }
        }
    },
)
async def service_get_engin_list():
    engin_list = ["mineru", "mineru_deploy"]
    return JSONResponse(content=engin_list)


@service_router.get(
    "/task-list",
    summary="Lấy danh sách tác vụ",
    description="Trả về danh sách ID của mọi tác vụ dịch đang xử lý hoặc đã hoàn thành.",
    tags=["Application"],
    responses={
        200: {
            "description": "Trả về danh sách ID tác vụ thành công.",
            "content": {
                "application/json": {
                    "example": ["a1b2c3d4", "e5f6g7h8"]
                }
            }
        }
    },
)
async def service_get_task_list():
    return JSONResponse(content=translation_service.list_tasks())


@service_router.get(
    "/default-params",
    summary="Lấy tham số mặc định",
    description="Trả về các tham số mặc định mà dịch vụ sử dụng, gồm số luồng đồng thời, kích thước khối, nhiệt độ, thời gian chờ, v.v.",
    tags=["Application"],
    responses={
        200: {
            "description": "Trả về tham số mặc định thành công.",
            "content": {
                "application/json": {
                    "example": {
                        "chunk_size": 2000,
                        "concurrent": 10,
                        "temperature": 0.3,
                        "timeout": 60,
                        "retry": 3,
                        "thinking": "default"
                    }
                }
            }
        }
    },
)
def service_get_default_params():
    return JSONResponse(content=default_params)


@service_router.get(
    "/meta",
    summary="Lấy thông tin ứng dụng",
    description="Trả về thông tin meta của dịch vụ như số phiên bản.",
    tags=["Application"],
    responses={
        200: {
            "description": "Trả về thông tin ứng dụng thành công.",
            "content": {
                "application/json": {
                    "example": {"version": "1.0.0"}
                }
            }
        }
    },
)
async def service_get_app_version():
    return JSONResponse(content={"version": __version__})


@service_router.post(
    "/flat-translate",
    summary="translate(sync)",
    description="""
Tải tệp lên và chờ dịch xong trực tiếp, không cần thăm dò trạng thái.
Mọi tham số đều được làm phẳng và gửi trực tiếp qua Form.
""",
    response_model=None,
    responses={
        200: {"description": "Dịch thành công, trả về nội dung tệp đã dịch."},
        500: {"description": "Đã xảy ra lỗi trong quá trình dịch."},
    },
)
async def service_flat_translate(
        request: Request,
        file: UploadFile = File(..., description="Tệp cần dịch"),
        model_id: str = Form("", description="ID mô hình (ví dụ: gpt-4o, glm-4-air), bắt buộc khi skip_translate=False"),
        base_url: Optional[str] = Form("",
                                       description="URL cơ sở của LLM API (nếu bỏ trống sẽ dùng biến môi trường hoặc giá trị mặc định; bắt buộc khi skip_translate=False)"),
        api_key: str = Form("xx", description="API Key (mặc định xx)"),
        to_lang: str = Form("中文", description="Ngôn ngữ đích"),
        workflow_type: str = Form("auto",
                                  description="Loại workflow: auto, markdown_based, txt, json, xlsx, docx, srt, epub, html, ass, pptx"),
        skip_translate: bool = Form(False, description="Có bỏ qua dịch và chỉ phân tích định dạng hay không"),
        concurrent: int = Form(default_params["concurrent"], description="Số yêu cầu đồng thời"),
        chunk_size: int = Form(default_params["chunk_size"], description="Kích thước khối văn bản"),
        temperature: float = Form(default_params["temperature"], description="Nhiệt độ (0-1)"),
        top_p: float = Form(default_params["top_p"], description="Nucleus sampling (0-1)"),
        timeout: int = Form(default_params["timeout"], description="Tổng thời gian chờ cho mỗi đoạn dịch (gồm mọi lần thử lại, tính bằng giây)"),
        connect_timeout: Optional[float] = Form(None),
        read_timeout: Optional[float] = Form(None),
        write_timeout: Optional[float] = Form(None),
        pool_timeout: Optional[float] = Form(None),
        streaming: Optional[bool] = Form(None),
        stream_idle_timeout: Optional[float] = Form(None),
        non_stream_timeout: Optional[float] = Form(None),
        office_password: Optional[str] = Form(None),
        html_exporter_options_json: Optional[str] = Form(None, description="Tùy chọn xuất HTML dạng JSON, ví dụ {\"cdn\": false, \"include_hidden_slides\": true}"),
        md2docx_engine: Optional[str] = Form(INHERIT, description="inherit: kế thừa cấu hình; none: tắt xuất DOCX; python/pandoc/auto: chọn engine"),
        retry: int = Form(default_params["retry"], description="Số lần thử lại khi thất bại"),
        thinking: str = Form("default", description="Chế độ suy nghĩ: default, enable, disable"),
        custom_prompt: Optional[str] = Form("", description="Prompt hệ thống tùy chỉnh"),
        system_proxy_enable: bool = Form(default_params["system_proxy_enable"], description="Có bật proxy hệ thống hay không"),
        force_json: bool = Form(False, description="Bắt buộc LLM xuất định dạng JSON"),
        rpm: Optional[int] = Form(None, description="Giới hạn RPM (số yêu cầu mỗi phút)"),
        tpm: Optional[int] = Form(None, description="Giới hạn TPM (số Token mỗi phút)"),
        provider: Optional[str] = Form("", description="Định danh nhà cung cấp LLM (dùng để xử lý đặc thù cho từng nền tảng)"),
        insert_mode: Optional[str] = Form(None, description="Chế độ chèn: replace (thay thế), append (nối vào cuối), prepend (chèn vào đầu)"),
        separator: Optional[str] = Form(None, description="Ký tự phân tách khi nối cuối/chèn đầu"),
        segment_mode: Optional[str] = Form(None, description="[Chỉ Txt] Chế độ phân đoạn: line (theo dòng), paragraph (theo đoạn), none (toàn văn)"),
        translate_regions: Optional[List[str]] = Form(None, description="[Chỉ Xlsx] Danh sách vùng cần dịch, ví dụ 'Sheet1!A1:B10'"),
        convert_engine: Optional[ConvertEngineType] = Form(None,
                                                           description="[PDF/MD] Engine phân tích: mineru, identity, mineru_deploy. Để trống thì tự chọn theo phần mở rộng tệp."),
        mineru_token: Optional[str] = Form("", description="[MinerU Cloud] API Token"),
        model_version: str = Form("vlm", description="[MinerU Cloud] Phiên bản mô hình: vlm, pipeline, MinerU-HTML"),
        mineru_language: str = Form("ch", description="[MinerU Cloud] Ngôn ngữ nhận dạng: ch, ch_server, en, japan, korean, chinese_cht, ta, te, ka, el, th, latin, arabic, cyrillic, east_slavic, devanagari"),
        formula_ocr: bool = Form(True, description="[PDF] Có bật nhận dạng công thức hay không"),
        mineru_deploy_base_url: str = Form("http://127.0.0.1:8000", description="[MinerU Local] Địa chỉ dịch vụ"),
        mineru_deploy_api_key: Optional[str] = Form(None, description="[MinerU Local] Khóa xác thực dịch vụ (tùy chọn); nếu trống sẽ dùng biến môi trường"),
        mineru_deploy_backend: str = Form("hybrid-engine",
                                          description="[MinerU Local] Loại backend: pipeline, vlm-engine, vlm-http-client, hybrid-engine, hybrid-http-client"),
        mineru_deploy_effort: str = Form("medium", description="[MinerU Local] Cường độ phân tích Hybrid: medium, high"),
        mineru_deploy_parse_method: str = Form("auto", description="[MinerU Local] Phương pháp phân tích: auto, txt, ocr"),
        mineru_deploy_formula_enable: bool = Form(True, description="[MinerU Local] Có bật công thức hay không"),
        mineru_deploy_table_enable: bool = Form(True, description="[MinerU Local] Có bật bảng hay không"),
        mineru_deploy_image_analysis: bool = Form(True, description="[MinerU Local] Có bật phân tích hình ảnh/biểu đồ hay không"),
        mineru_deploy_start_page_id: int = Form(0, description="[MinerU Local] Trang bắt đầu"),
        mineru_deploy_end_page_id: int = Form(99999, description="[MinerU Local] Trang kết thúc"),
        mineru_deploy_lang_list: Optional[List[str]] = Form(None, description="[MinerU Local] Danh sách ngôn ngữ"),
        mineru_deploy_server_url: Optional[str] = Form("",
                                                       description="[MinerU Local] Server URL (dùng khi backend='vlm-http-client')"),
        json_paths: Optional[List[str]] = Form(None, description="[Chỉ Json] Danh sách biểu thức JsonPath, ví dụ '$.name'"),
        glossary_generate_enable: bool = Form(False, description="Có bật tự động tạo bảng thuật ngữ hay không"),
        glossary_dict_json: Optional[str] = Form("", description="Chuỗi JSON từ điển thuật ngữ, định dạng: {'nguyên văn':'bản dịch'}"),
        glossary_agent_config_json: Optional[str] = Form("",
                                                         description="Chuỗi JSON cấu hình Agent bảng thuật ngữ (gồm base_url, model_id, v.v.)"),
        extra_body_json: Optional[str] = Form("", description="Chuỗi JSON tham số body bổ sung, sẽ được gộp vào yêu cầu API")
):
    task_id = uuid.uuid4().hex[:8]

    try:
        _enforce_upload_limit(getattr(file, "size", None) or 0)
        file_contents = await file.read()
        _enforce_upload_limit(len(file_contents))
        original_filename = file.filename or "uploaded_file"
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Đọc tệp thất bại: {mask_secrets(str(e))}")

    parsed_glossary_dict = None
    if glossary_dict_json and glossary_dict_json.strip():
        try:
            parsed_glossary_dict = json.loads(glossary_dict_json)
            if not isinstance(parsed_glossary_dict, dict):
                raise ValueError("Phải là một từ điển (dict)")
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"glossary_dict_json phân tích thất bại: {mask_secrets(str(e))}")

    parsed_glossary_agent = None
    if glossary_agent_config_json and glossary_agent_config_json.strip():
        try:
            parsed_glossary_agent = json.loads(glossary_agent_config_json)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"glossary_agent_config_json phân tích thất bại: {mask_secrets(str(e))}")

    # Parse extra_body if provided - validate but keep as string
    if extra_body_json and extra_body_json.strip():
        try:
            parsed_extra = json.loads(extra_body_json)
            if not isinstance(parsed_extra, dict):
                raise HTTPException(status_code=400, detail="extra_body_json phải là một đối tượng JSON")
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"extra_body_json phân tích thất bại: {mask_secrets(str(e))}")

    parsed_html_options = None
    if html_exporter_options_json:
        try:
            parsed_html_options = json.loads(html_exporter_options_json)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="html_exporter_options_json phải là JSON hợp lệ") from exc
    submitted_form = await request.form()
    payload_dict = {
        "workflow_type": workflow_type,
        "base_url": base_url,
        "api_key": api_key,
        "model_id": model_id,
        "to_lang": to_lang,
        "skip_translate": skip_translate,
        "concurrent": concurrent,
        "chunk_size": chunk_size,
        "temperature": temperature,
        "top_p": top_p,
        "timeout": timeout,
        "connect_timeout": connect_timeout,
        "read_timeout": read_timeout,
        "write_timeout": write_timeout,
        "pool_timeout": pool_timeout,
        "streaming": streaming,
        "stream_idle_timeout": stream_idle_timeout,
        "non_stream_timeout": non_stream_timeout,
        "office_password": office_password,
        "html_exporter_options": parsed_html_options,
        "md2docx_engine": md2docx_engine,
        "retry": retry,
        "thinking": thinking,
        "custom_prompt": custom_prompt,
        "system_proxy_enable": system_proxy_enable,
        "force_json": force_json,
        "rpm": rpm,
        "tpm": tpm,
        "provider": provider,
        "insert_mode": insert_mode,
        "separator": separator,
        "segment_mode": segment_mode,
        "translate_regions": translate_regions,
        "convert_engine": convert_engine,
        "mineru_token": mineru_token,
        "model_version": model_version,
        "mineru_language": mineru_language,
        "formula_ocr": formula_ocr,
        "mineru_deploy_base_url": mineru_deploy_base_url,
        "mineru_deploy_api_key": mineru_deploy_api_key,
        "mineru_deploy_backend": mineru_deploy_backend,
        "mineru_deploy_effort": mineru_deploy_effort,
        "mineru_deploy_parse_method": mineru_deploy_parse_method,
        "mineru_deploy_formula_enable": mineru_deploy_formula_enable,
        "mineru_deploy_table_enable": mineru_deploy_table_enable,
        "mineru_deploy_image_analysis": mineru_deploy_image_analysis,
        "mineru_deploy_start_page_id": mineru_deploy_start_page_id,
        "mineru_deploy_end_page_id": mineru_deploy_end_page_id,
        "mineru_deploy_lang_list": mineru_deploy_lang_list,
        "mineru_deploy_server_url": mineru_deploy_server_url,
        "json_paths": json_paths,
        "glossary_generate_enable": glossary_generate_enable,
        "glossary_dict": parsed_glossary_dict,
        "glossary_agent_config": parsed_glossary_agent
    }

    # Add extra_body if provided
    if extra_body_json and extra_body_json.strip():
        payload_dict["extra_body"] = extra_body_json

    aliases = {"html_exporter_options": "html_exporter_options_json",
               "glossary_dict": "glossary_dict_json",
               "glossary_agent_config": "glossary_agent_config_json", "extra_body": "extra_body_json"}
    payload_dict = {key: value for key, value in payload_dict.items()
                    if aliases.get(key, key) in submitted_form or key in {"workflow_type", "skip_translate"}}
    # FastAPI coerces an empty form string to the parameter default (or None),
    # so read the documented empty text overrides from the raw form instead.
    for key in EMPTY_TEXT_OVERRIDE_FIELDS:
        form_key = aliases.get(key, key)
        if form_key in submitted_form:
            payload_dict[key] = str(submitted_form[form_key])
    engine = payload_dict.get("md2docx_engine", INHERIT)
    if engine in (INHERIT, "", None):
        payload_dict.pop("md2docx_engine", None)
    elif engine in ("none", "null"):
        payload_dict["md2docx_engine"] = None
    # Empty strings mean "not provided" (legacy form clients send them for
    # unset selects) except for the documented empty text overrides. The flat
    # form cannot express JSON null, so empty timeouts are unset, not cleared.
    payload_dict = {key: value for key, value in payload_dict.items()
                    if (value is not None or key == "md2docx_engine")
                    and (value != "" or key in EMPTY_TEXT_OVERRIDE_FIELDS)}

    # Note: For auto workflow type, we leave it as "auto" and let
    # translation_service.start_translation handle the detection,
    # including setting default json_paths and convert_engine

    try:
        payload_obj = TypeAdapter(TranslatePayload).validate_python(payload_dict)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Xác thực cấu hình tham số thất bại: {mask_secrets(str(e))}")

    try:
        await translation_service.start_translation(
            task_id=task_id,
            payload=payload_obj,
            file_contents=file_contents,
            original_filename=original_filename
        )
    except HTTPException:
        # 保留 start_translation 抛出的 400/429 等语义，避免客户端错误被改写为 500。
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi dịch nội bộ: {mask_secrets(str(e))}")

    task_state = translation_service.get_task_state(task_id)

    if not task_state:
        raise HTTPException(status_code=500, detail="Trạng thái tác vụ bị mất")

    if task_state.get("error_flag"):
        error_msg = task_state.get("status_message", "Lỗi không xác định")
        temp_dir = task_state.get("temp_dir")
        if temp_dir and os.path.isdir(temp_dir):
            import shutil
            shutil.rmtree(temp_dir)
        await translation_service.release_task(task_id)
        raise HTTPException(status_code=500, detail=f"Tác vụ dịch thất bại: {error_msg}")

    task = task_state.get("current_task_ref")
    if task:
        await task

    task_state = translation_service.get_task_state(task_id)

    if not task_state:
        # 任务可能已被并发请求 /release 释放。
        raise HTTPException(status_code=410, detail=f"Tác vụ '{task_id}' đã được giải phóng, không thể lấy kết quả.")

    if task_state.get("cancelled"):
        raise HTTPException(
            status_code=409,
            detail=f"Tác vụ dịch đã bị hủy: {task_state.get('status_message', '')}",
        )

    if task_state.get("error_flag"):
        error_msg = task_state.get("status_message", "Lỗi không xác định")
        await translation_service.release_task(task_id)
        raise HTTPException(status_code=500, detail=f"Tác vụ dịch thất bại: {error_msg}")

    base_url_str = str(request.base_url).rstrip("/")
    downloads = {}
    if task_state.get("download_ready") and task_state.get("downloadable_files"):
        for file_type, info in task_state["downloadable_files"].items():
            downloads[file_type] = f"{base_url_str}/service/download/{task_id}/{file_type}"

    attachments = {}
    if task_state.get("download_ready") and task_state.get("attachment_files"):
        for identifier in task_state["attachment_files"]:
            attachments[identifier] = f"{base_url_str}/service/attachment/{task_id}/{identifier}"

    duration = task_state.get("task_end_time", 0) - task_state.get("task_start_time", 0)

    return JSONResponse(content={
        "status": "success",
        "task_id": task_id,
        "message": task_state.get("status_message"),
        "duration": round(duration, 2),
        "downloads": downloads,
        "attachments": attachments
    })


# ===================================================================
# --- Static pages and docs ---
# ===================================================================


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def main_page():
    index_path = Path(STATIC_DIR) / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="index.html not found")
    no_cache_headers = {
        "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
        "Pragma": "no-cache",
        "Expires": "0",
    }
    return FileResponse(index_path, media_type="text/html", headers=no_cache_headers)


@app.get("/admin", response_class=HTMLResponse, include_in_schema=False)
async def main_page_admin():
    index_path = Path(STATIC_DIR) / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="index.html not found")
    no_cache_headers = {
        "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
        "Pragma": "no-cache",
        "Expires": "0",
    }
    return FileResponse(index_path, media_type="text/html", headers=no_cache_headers)


@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui_html():
    return get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title=app.title + " - Swagger UI",
        oauth2_redirect_url=app.swagger_ui_oauth2_redirect_url,
        swagger_js_url="/static/swagger/swagger.js",
        swagger_css_url="/static/swagger/swagger.css",
    )


@app.get(app.swagger_ui_oauth2_redirect_url, include_in_schema=False)
async def swagger_ui_redirect():
    return get_swagger_ui_oauth2_redirect_html()


@app.get("/redoc", include_in_schema=False)
async def redoc_html():
    return get_redoc_html(
        openapi_url=app.openapi_url,
        title=app.title + " - ReDoc",
        redoc_js_url="/static/redoc/redoc.js",
    )


app.include_router(service_router)


# ===================================================================
# --- Run function ---
# ===================================================================


def find_free_port(start_port):
    port = start_port
    while True:
        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
            if sock.connect_ex(("127.0.0.1", port)) != 0:
                return port
            port += 1


def run_app(host=None, port: int | None = None, enable_CORS=False,
            allow_origin_regex=r"^(https?://.*|null|file://.*)$",
            with_mcp: bool = False):
    initial_port = port or PORT
    try:
        port_to_use = find_free_port(initial_port)
        if port_to_use != initial_port:
            global_logger.warning(
                "Cổng %s đã bị chiếm, sẽ dùng cổng %s", initial_port, port_to_use
            )
        global_logger.info("Đang khởi động DocuTranslate WebUI %s", __version__)
        app.state.port_to_use = port_to_use
        app.state.with_mcp = with_mcp
        if enable_CORS:
            global_logger.info("Đã bật CORS: allow_origin_regex=%s", allow_origin_regex)
            app.add_middleware(
                CORSMiddleware,
                allow_origin_regex=allow_origin_regex,
                allow_credentials=True,
                allow_methods=["*"],
                allow_headers=["*"],
            )

        if with_mcp:
            # Use the same host and port as the web backend
            # If host is None, use 0.0.0.0 to ensure CORS works correctly
            mcp_host = host if host is not None else "0.0.0.0"
            setup_mcp_integration(
                enable=True,
                host=mcp_host,
                port=port_to_use,
                enable_cors=enable_CORS,
                allow_origin_regex=allow_origin_regex,
            )

        uvicorn.run(app, host=host, port=port_to_use, workers=1)
    except Exception as e:
        global_logger.exception("Khởi động thất bại: %s", e)


if __name__ == "__main__":
    run_app(with_mcp=True)
