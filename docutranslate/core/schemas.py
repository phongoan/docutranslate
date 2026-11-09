# SPDX-FileCopyrightText: 2025 QinHan
# SPDX-License-Identifier: MPL-2.0
# docutranslate.core.schemas.py

import json
from typing import (
    List,
    Dict,
    Optional,
    Literal,
    Union,
    Annotated,
)

from pydantic import (
    BaseModel,
    Field,
    model_validator,
    field_validator,
    AliasChoices,
    ConfigDict,
)

from docutranslate.agents.agent import ThinkingMode
from docutranslate.agents.thinking.thinking_factory import ProviderType
from docutranslate.config import (
    # BaseWorkflowParams defaults
    CHUNK_SIZE, CONCURRENT, TEMPERATURE, TOP_P, TIMEOUT,
    CONNECT_TIMEOUT, READ_TIMEOUT, WRITE_TIMEOUT, POOL_TIMEOUT,
    THINKING, RETRY, SYSTEM_PROXY_ENABLE,
    # Env defaults for empty fields
    API_KEY, BASE_URL, MODEL_ID, TO_LANG, PROVIDER,
    # Force override flag and env set tracker
    ENV_FORCE_OVERRIDE, ENV_SET,
    # Additional BaseWorkflowParams defaults
    CUSTOM_PROMPT, FORCE_JSON, RPM, TPM, EXTRA_BODY, GLOSSARY_GENERATE_ENABLE,
    # MarkdownWorkflowParams defaults
    CONVERT_ENGINE, MD2DOCX_ENGINE, MINERU_TOKEN, MINERU_DEPLOY_BASE_URL, MINERU_DEPLOY_API_KEY,
    MODEL_VERSION, FORMULA_OCR, MINERU_LANGUAGE,
    MINERU_DEPLOY_BACKEND, MINERU_DEPLOY_PARSE_METHOD,
    MINERU_DEPLOY_EFFORT, MINERU_DEPLOY_TABLE_ENABLE,
    MINERU_DEPLOY_FORMULA_ENABLE, MINERU_DEPLOY_IMAGE_ANALYSIS,
    MINERU_DEPLOY_START_PAGE_ID, MINERU_DEPLOY_END_PAGE_ID, MINERU_DEPLOY_SERVER_URL,
    # TextWorkflowParams defaults
    INSERT_MODE, SEPARATOR, SEGMENT_MODE,
    LLM_STREAMING, STREAM_IDLE_TIMEOUT, NON_STREAM_TIMEOUT,
)

# --- 公共类型定义 ---
WorkflowType = Literal[
    "auto", "markdown_based", "txt", "json", "xlsx", "docx",
    "srt", "epub", "html", "ass", "pptx"
]
InsertMode = Literal["replace", "append", "prepend"]


class GlossaryAgentConfigPayload(BaseModel):
    base_url: str = Field(
        ...,
        validation_alias=AliasChoices("base_url", "baseurl"),
        description="URL cơ sở của LLM API dùng cho Agent tạo thuật ngữ.",
        examples=["https://api.openai.com/v1"],
    )
    api_key: str = Field(
        default="xx",
        validation_alias=AliasChoices("api_key", "key"),
        description="Khóa LLM API dùng cho Agent tạo thuật ngữ (mặc định là xx).",
        examples=["sk-agent-api-key"],
    )

    @field_validator("api_key")
    @classmethod
    def set_default_glossary_api_key(cls, v: str) -> str:
        return v if v and v.strip() else "xx"

    model_id: str = Field(
        ..., description="ID mô hình dùng cho Agent tạo thuật ngữ.", examples=["gpt-4-turbo"]
    )
    to_lang: str = Field(
        ..., description="Ngôn ngữ đích khi tạo thuật ngữ.", examples=["Tiếng Việt", "English"]
    )
    temperature: float = Field(
        default=0.7, description="Tham số nhiệt độ (temperature) của Agent tạo thuật ngữ."
    )
    top_p: float = Field(
        default=0.9, description="Tham số lấy mẫu nhân (top_p) của Agent tạo thuật ngữ."
    )
    concurrent: int = Field(default=30, description="Số yêu cầu đồng thời tối đa của Agent.")
    timeout: int = Field(
        default=TIMEOUT, description="Tổng thời hạn cứng tương thích cho từng phân đoạn ở chế độ không streaming (giây); chế độ streaming dùng thời gian chờ nhàn rỗi trượt riêng."
    )
    connect_timeout: float = Field(
        default=CONNECT_TIMEOUT, description="Thời gian chờ mỗi lần thiết lập kết nối TCP/TLS (giây)."
    )
    read_timeout: Optional[float] = Field(
        default=READ_TIMEOUT, description="Thời gian im lặng tối đa cho phép giữa hai lần đọc mạng ở chế độ không streaming (giây)."
    )
    write_timeout: float = Field(
        default=WRITE_TIMEOUT, description="Thời gian chờ cho một thao tác ghi mạng (giây)."
    )
    pool_timeout: float = Field(
        default=POOL_TIMEOUT, description="Thời gian chờ kết nối rảnh trong nhóm kết nối HTTP (giây)."
    )
    thinking: ThinkingMode = Field(default="default", description="Chế độ suy nghĩ của Agent.")
    retry: int = Field(
        default=RETRY, description="Số lần thử lại tối đa sau khi một khối thất bại."
    )
    system_proxy_enable: bool = Field(
        default=SYSTEM_PROXY_ENABLE,
        description="Có sử dụng proxy hệ thống hay không",
        examples=[True, False],
    )
    # 修改: 默认值改为 "" 以避免 Swagger 显示 "string"
    custom_prompt: Optional[str] = Field(
        default="", description="Prompt tùy chỉnh của người dùng để tạo thuật ngữ"
    )
    force_json: bool = Field(
        default=False, description="Bắt buộc Agent xuất thuật ngữ ở định dạng JSON."
    )
    # 修改: 增加 examples=[None]
    rpm: Optional[int] = Field(
        default=None, description="Giới hạn RPM (Requests Per Minute)", examples=[None]
    )
    tpm: Optional[int] = Field(
        default=None, description="Giới hạn TPM (Tokens Per Minute)", examples=[None]
    )
    provider: Optional[ProviderType] = Field(
        default=None, description="Mã định danh nhà cung cấp LLM", examples=[None]
    )
    extra_body: Optional[str] = Field(
        default="", description="Tham số bổ sung của thân yêu cầu ở dạng chuỗi JSON, sẽ được gộp vào yêu cầu API"
    )

    streaming: bool = LLM_STREAMING
    stream_idle_timeout: float = STREAM_IDLE_TIMEOUT
    non_stream_timeout: Optional[float] = NON_STREAM_TIMEOUT


# 1. 定义所有工作流共享的基础参数
class HTMLExportOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cdn: Optional[bool] = None
    include_hidden_slides: Optional[bool] = None


class BaseWorkflowParams(BaseModel):
    html_exporter_options: Optional[HTMLExportOptions] = None
    skip_translate: bool = Field(
        default=False,
        description="Có bỏ qua bước dịch hay không. Nếu là True, chỉ thực hiện phân tích tài liệu và chuyển đổi định dạng.",
    )
    # 修改: 默认值改为 ""
    base_url: Optional[str] = Field(
        default="",
        validation_alias=AliasChoices("base_url", "baseurl"),
        description="URL cơ sở của LLM API. Bắt buộc khi `skip_translate` là `False`.",
        examples=["https://api.openai.com/v1"],
    )
    api_key: str = Field(
        default="xx",
        validation_alias=AliasChoices("api_key", "key"),
        description="Khóa LLM API (tùy chọn, mặc định là xx).",
        examples=["sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxx"],
    )

    @field_validator("api_key")
    @classmethod
    def set_default_api_key(cls, v: str) -> str:
        return v if v and v.strip() else "xx"

    # 修改: 默认值改为 ""
    model_id: Optional[str] = Field(
        default="",
        description="ID mô hình LLM cần sử dụng. Bắt buộc khi `skip_translate` là `False`.",
        examples=["gpt-4o"],
    )
    to_lang: str = Field(
        default=TO_LANG, description="Ngôn ngữ đích của bản dịch.", examples=["Tiếng Việt", "English"]
    )
    chunk_size: int = Field(
        default=CHUNK_SIZE, description="Kích thước khối khi chia văn bản (byte UTF-8, không phải số ký tự)."
    )
    concurrent: int = Field(
        default=CONCURRENT, description="Số yêu cầu đồng thời."
    )
    temperature: float = Field(
        default=TEMPERATURE, description="Tham số nhiệt độ (temperature) của LLM."
    )
    top_p: float = Field(
        default=TOP_P, description="Tham số lấy mẫu nhân (top_p) của LLM."
    )
    timeout: int = Field(
        default=TIMEOUT, description="Tổng thời hạn cứng tương thích cho từng phân đoạn ở chế độ không streaming (giây); chế độ streaming dùng thời gian chờ nhàn rỗi trượt riêng."
    )
    connect_timeout: float = Field(
        default=CONNECT_TIMEOUT, description="Thời gian chờ mỗi lần thiết lập kết nối TCP/TLS (giây)."
    )
    read_timeout: Optional[float] = Field(
        default=READ_TIMEOUT, description="Thời gian im lặng tối đa cho phép giữa hai lần đọc mạng ở chế độ không streaming (giây)."
    )
    write_timeout: float = Field(
        default=WRITE_TIMEOUT, description="Thời gian chờ cho một thao tác ghi mạng (giây)."
    )
    pool_timeout: float = Field(
        default=POOL_TIMEOUT, description="Thời gian chờ kết nối rảnh trong nhóm kết nối HTTP (giây)."
    )
    thinking: ThinkingMode = Field(
        default=THINKING,
        description="Chế độ suy nghĩ của Agent.",
        examples=["default", "enable", "disable"],
    )
    retry: int = Field(
        default=RETRY,
        description="Số lần thử lại tối đa sau khi dịch một khối thất bại.",
    )
    system_proxy_enable: bool = Field(
        default=SYSTEM_PROXY_ENABLE,
        description="Có sử dụng proxy hệ thống hay không",
        examples=[True, False],
    )
    # 修改: 默认值改为 ""
    custom_prompt: Optional[str] = Field(
        default=CUSTOM_PROMPT, description="Prompt dịch tùy chỉnh của người dùng.", alias="custom_prompt"
    )
    glossary_dict: Optional[Dict[str, str]] = Field(
        None, description="Từ điển thuật ngữ, key là bản gốc, value là bản dịch.", examples=[None]
    )
    glossary_generate_enable: bool = Field(
        default=GLOSSARY_GENERATE_ENABLE, description="Có bật tự động tạo thuật ngữ hay không."
    )
    glossary_agent_config: Optional[GlossaryAgentConfigPayload] = Field(
        None,
        description="Cấu hình của Agent tạo thuật ngữ. Bắt buộc nếu `glossary_generate_enable` là `True`.",
        examples=[None],
    )
    force_json: bool = Field(
        default=FORCE_JSON, description="Bắt buộc AI xuất JSON khi cần đầu ra ở định dạng JSON"
    )
    rpm: Optional[int] = Field(
        default=RPM, description="Giới hạn RPM (Requests Per Minute)", examples=[None]
    )
    tpm: Optional[int] = Field(
        default=TPM, description="Giới hạn TPM (Tokens Per Minute)", examples=[None]
    )
    provider: Optional[ProviderType] = Field(
        default=PROVIDER, description="Mã định danh nhà cung cấp LLM", examples=[None]
    )
    extra_body: Optional[str] = Field(
        default=EXTRA_BODY, description="Tham số bổ sung của thân yêu cầu ở dạng chuỗi JSON, sẽ được gộp vào yêu cầu API"
    )

    streaming: bool = LLM_STREAMING
    stream_idle_timeout: float = STREAM_IDLE_TIMEOUT
    non_stream_timeout: Optional[float] = NON_STREAM_TIMEOUT

    @model_validator(mode="before")
    @classmethod
    def check_translation_fields(cls, values):
        # 修复: 当使用 FastAPI Form + Json 时，Pydantic V2 mode='before' 验证器可能会接收到 JSON 字符串
        if isinstance(values, str):
            try:
                values = json.loads(values)
            except ValueError:
                pass

        if isinstance(values, dict):
            values = dict(values)
            if not values.get("skip_translate"):
                # 环境变量值映射
                env_values = {
                    "base_url": BASE_URL,
                    "model_id": MODEL_ID,
                    "api_key": API_KEY,
                    "provider": PROVIDER,
                    "to_lang": TO_LANG,
                    "thinking": THINKING,
                    "chunk_size": CHUNK_SIZE,
                    "concurrent": CONCURRENT,
                    "temperature": TEMPERATURE,
                    "top_p": TOP_P,
                    "timeout": TIMEOUT,
                    "connect_timeout": CONNECT_TIMEOUT,
                    "read_timeout": READ_TIMEOUT,
                    "write_timeout": WRITE_TIMEOUT,
                    "pool_timeout": POOL_TIMEOUT,
                    "retry": RETRY,
                    "system_proxy_enable": SYSTEM_PROXY_ENABLE,
                    "custom_prompt": CUSTOM_PROMPT,
                    "force_json": FORCE_JSON,
                    "rpm": RPM,
                    "tpm": TPM,
                    "extra_body": EXTRA_BODY,
                }

                if ENV_FORCE_OVERRIDE:
                    # 强制覆盖模式：仅当 .env 中实际设置了值时才覆盖前端传参
                    for field, env_value in env_values.items():
                        if ENV_SET.get(field):
                            values[field] = env_value
                else:
                    # 默认模式：补缺省值，并保留显式的 false、0 和空文本
                    for field, env_value in env_values.items():
                        # Empty credentials retain their historical environment fallback;
                        # explicit false, zero and empty text options are valid overrides.
                        missing = field not in values or (values[field] is None and field != "read_timeout")
                        if field in {"base_url", "model_id", "api_key", "provider", "to_lang"}:
                            missing = missing or values[field] == ""
                        aliases = {"base_url": "baseurl", "api_key": "key"}
                        if field in aliases and values.get(aliases[field]):
                            missing = False
                        if missing and env_value is not None:
                            values[field] = env_value

                # 验证：如果填充后仍为空，则报错（Auto 模式除外）
                if not (values.get("base_url") or values.get("baseurl")):
                    if values.get("workflow_type") != "auto":
                        raise ValueError(
                            "Khi `skip_translate` là `False`, trường `base_url` hoặc `baseurl` là bắt buộc."
                        )
                if not values.get("model_id"):
                    if values.get("workflow_type") != "auto":
                        raise ValueError(
                            "Khi `skip_translate` là `False`, trường `model_id` là bắt buộc."
                        )
        return values


# --- 定义通用参数 Mixin，用于 Auto 模式透传 ---
# 这是必须添加的关键部分，让 Auto 模式能够显式识别这些参数
class UniversalParamsMixin(BaseModel):
    # Markdown/PDF 相关
    convert_engine: Optional[Literal["identity", "mineru", "mineru_deploy"]] = None
    mineru_token: Optional[str] = None
    model_version: Optional[Literal["pipeline", "vlm", "MinerU-HTML"]] = None
    formula_ocr: Optional[bool] = None
    mineru_language: Optional[Literal[
        "ch", "ch_server", "en", "japan", "korean", "chinese_cht",
        "ta", "te", "ka", "el", "th", "latin", "arabic", "cyrillic",
        "east_slavic", "devanagari"
    ]] = None

    # MinerU Deploy 相关 - 设置默认值避免 None 导致的验证错误
    mineru_deploy_base_url: Optional[str] = None
    mineru_deploy_api_key: Optional[str] = Field(default=None, repr=False)
    mineru_deploy_backend: Optional[Literal[
        "flash", "basic", "standard", "advanced", "pipeline", "vlm-engine", "vlm-http-client",
        "hybrid-engine", "hybrid-http-client",
        "vlm-auto-engine", "hybrid-auto-engine"
    ]] = None
    mineru_deploy_effort: Optional[Literal["medium", "high"]] = None
    mineru_deploy_parse_method: Optional[Literal["auto", "txt", "ocr"]] = None
    mineru_deploy_table_enable: Optional[bool] = None
    mineru_deploy_formula_enable: Optional[bool] = None
    mineru_deploy_image_analysis: Optional[bool] = None
    mineru_deploy_start_page_id: Optional[int] = None
    mineru_deploy_end_page_id: Optional[int] = None
    mineru_deploy_lang_list: Optional[List[str]] = None
    mineru_deploy_server_url: Optional[str] = None

    # Text/Excel/Common 相关
    insert_mode: Optional[Literal["replace", "append", "prepend"]] = None
    separator: Optional[str] = None
    translate_regions: Optional[List[str]] = None
    segment_mode: Optional[Literal["line", "paragraph", "none"]] = None

    # Docx/Xlsx 密码相关
    office_password: Optional[str] = None

    # Json 相关
    json_paths: Optional[List[str]] = None


# 2. 修改 AutoWorkflowParams，使其继承 UniversalParamsMixin
class AutoWorkflowParams(BaseWorkflowParams, UniversalParamsMixin):
    workflow_type: Literal["auto"] = Field(..., description="Tự động chọn quy trình theo phần mở rộng của tệp.")
    model_config = ConfigDict(extra="allow")


class MarkdownWorkflowParams(BaseWorkflowParams):
    workflow_type: Literal["markdown_based"] = Field(
        ..., description="Chỉ định dùng quy trình dịch dựa trên Markdown."
    )
    convert_engine: Literal[
        "identity", "mineru", "mineru_deploy"
    ] = Field(
        CONVERT_ENGINE,
        description="Chọn engine phân tích tệp thành markdown. 'mineru_deploy' dành cho dịch vụ MinerU triển khai cục bộ. Nếu tệp đầu vào là .md, mục này có thể là `identity` hoặc bỏ trống.",
        examples=["identity", "mineru", "mineru_deploy"],
    )
    md2docx_engine: Literal["python", "pandoc", "auto"] | None = Field(
        MD2DOCX_ENGINE,
        description="Chọn engine xuất markdown sang docx. 'python' dùng bản cài đặt thuần Python, 'pandoc' dùng lệnh pandoc, 'auto' tự động chọn (ưu tiên pandoc), None nghĩa là không tạo docx.",
        examples=["python", "pandoc", "auto"],
    )

    # --- Engine-Specific Parameters ---

    # -- For "mineru" (Cloud API) --
    # 修改: 默认值改为 ""
    mineru_token: Optional[str] = Field(
        default=MINERU_TOKEN or "",
        description="[Chỉ khi convert_engine='mineru'] API token bắt buộc.",
    )
    model_version: Literal["pipeline", "vlm", "MinerU-HTML"] = Field(
        MODEL_VERSION, description="[Chỉ khi convert_engine='mineru'] Phiên bản mô hình Mineru Cloud."
    )
    formula_ocr: bool = Field(
        FORMULA_OCR,
        description="[Chỉ khi convert_engine='mineru'] Có nhận dạng OCR công thức hay không.",
    )
    mineru_language: Literal[
        "ch", "ch_server", "en", "japan", "korean", "chinese_cht",
        "ta", "te", "ka", "el", "th", "latin", "arabic", "cyrillic",
        "east_slavic", "devanagari"
    ] = Field(
        MINERU_LANGUAGE,
        description="[Chỉ khi convert_engine='mineru'] Tùy chọn ngôn ngữ nhận dạng, mặc định 'ch' (Trung và Anh).",
    )


    # -- For "mineru_deploy" (Local Deployment) --
    mineru_deploy_base_url: Optional[str] = Field(
        MINERU_DEPLOY_BASE_URL,
        description="[Chỉ khi convert_engine='mineru_deploy'] Địa chỉ dịch vụ MinerU triển khai cục bộ.",
    )
    # --- UPDATED BACKEND LIST ---
    mineru_deploy_api_key: Optional[str] = Field(
        default=None, repr=False,
        description="[Chỉ khi convert_engine='mineru_deploy'] Khóa xác thực dịch vụ (tùy chọn); nếu để trống sẽ dùng biến môi trường.",
        json_schema_extra={"writeOnly": True},
    )
    mineru_deploy_backend: Literal[
        "flash", "basic", "standard", "advanced",
        "pipeline",
        "vlm-engine",
        "vlm-auto-engine",
        "vlm-http-client",
        "hybrid-engine",
        "hybrid-auto-engine",
        "hybrid-http-client"
    ] = Field(
        MINERU_DEPLOY_BACKEND,
        description="[Chỉ khi convert_engine='mineru_deploy'] Backend mà dịch vụ MinerU triển khai cục bộ sử dụng.",
    )
    mineru_deploy_effort: Literal["medium", "high"] = Field(
        MINERU_DEPLOY_EFFORT,
        description="[Chỉ khi dùng hybrid backend] Cường độ phân tích: medium nhanh hơn, high chính xác hơn và hỗ trợ phân tích hình ảnh.",
    )
    mineru_deploy_parse_method: Literal["auto", "txt", "ocr"] = Field(
        MINERU_DEPLOY_PARSE_METHOD,
        description="[Chỉ khi convert_engine='mineru_deploy'] Phương pháp phân tích: auto, txt, ocr"
    )
    mineru_deploy_table_enable: bool = Field(
        MINERU_DEPLOY_TABLE_ENABLE,
        description="[Chỉ khi convert_engine='mineru_deploy'] Dịch vụ triển khai cục bộ có bật phân tích bảng hay không.",
    )
    mineru_deploy_formula_enable: bool = Field(
        MINERU_DEPLOY_FORMULA_ENABLE,
        description="[Chỉ khi convert_engine='mineru_deploy'] Dịch vụ triển khai cục bộ có bật phân tích công thức hay không.",
    )
    mineru_deploy_image_analysis: bool = Field(
        MINERU_DEPLOY_IMAGE_ANALYSIS,
        description="[Chỉ khi convert_engine='mineru_deploy'] Có bật phân tích hình ảnh/biểu đồ hay không; Hybrid medium sẽ do MinerU tự động tắt.",
    )
    mineru_deploy_start_page_id: int = Field(
        MINERU_DEPLOY_START_PAGE_ID, description="[Chỉ khi convert_engine='mineru_deploy'] Trang bắt đầu phân tích."
    )
    mineru_deploy_end_page_id: int = Field(
        MINERU_DEPLOY_END_PAGE_ID, description="[Chỉ khi convert_engine='mineru_deploy'] Trang kết thúc phân tích."
    )
    mineru_deploy_lang_list: Optional[List[str]] = Field(
        None,
        description="[Chỉ khi convert_engine='mineru_deploy'] Danh sách ngôn ngữ, mặc định ['ch'].",
        examples=[["ch", "en"]],
    )
    # 修改: 默认值改为 ""
    mineru_deploy_server_url: Optional[str] = Field(
        default=MINERU_DEPLOY_SERVER_URL or "",
        description="[Chỉ khi convert_engine='mineru_deploy' và backend liên quan đến http-client] Server URL.",
    )

    @model_validator(mode="after")
    def check_engine_params(self):
        if self.convert_engine == "mineru":
            if not self.mineru_token and MINERU_TOKEN:
                self.mineru_token = MINERU_TOKEN
            if not self.mineru_token:
                raise ValueError(
                    "Khi `convert_engine` là 'mineru', trường `mineru_token` là bắt buộc."
                )
        if self.convert_engine == "mineru_deploy":
            if ENV_FORCE_OVERRIDE and ENV_SET.get("mineru_deploy_api_key"):
                self.mineru_deploy_api_key = MINERU_DEPLOY_API_KEY
            elif not self.mineru_deploy_api_key:
                self.mineru_deploy_api_key = MINERU_DEPLOY_API_KEY
            backend_aliases = {
                "vlm-auto-engine": "vlm-engine",
                "hybrid-auto-engine": "hybrid-engine",
            }
            self.mineru_deploy_backend = backend_aliases.get(
                self.mineru_deploy_backend, self.mineru_deploy_backend
            )
            if not self.mineru_deploy_base_url and MINERU_DEPLOY_BASE_URL:
                self.mineru_deploy_base_url = MINERU_DEPLOY_BASE_URL
            if not self.mineru_deploy_base_url:
                raise ValueError(
                    "Khi `convert_engine` là 'mineru_deploy', trường `mineru_deploy_base_url` là bắt buộc."
                )
            if (
                self.mineru_deploy_backend.endswith("-http-client")
                and not self.mineru_deploy_server_url
            ):
                raise ValueError(
                    "Khi MinerU Deploy dùng http-client backend, trường `mineru_deploy_server_url` là bắt buộc."
                )
        return self


class TextWorkflowParams(BaseWorkflowParams):
    workflow_type: Literal["txt"] = Field(
        ..., description="Chỉ định dùng quy trình dịch văn bản thuần."
    )
    insert_mode: Literal["replace", "append", "prepend"] = Field(
        INSERT_MODE,
        description="Chế độ chèn văn bản dịch. 'replace': thay thế bản gốc, 'append': thêm vào sau bản gốc, 'prepend': thêm vào trước bản gốc.",
    )
    separator: str = Field(
        SEPARATOR,
        description="Ký tự phân tách giữa bản gốc và bản dịch khi insert_mode là 'append' hoặc 'prepend'.",
    )
    segment_mode: Literal["line", "paragraph", "none"] = Field(
        default=SEGMENT_MODE,
        description="Chế độ chia đoạn: 'line' (theo dòng), 'paragraph' (theo đoạn), 'none' (toàn văn)",
    )


class JsonWorkflowParams(BaseWorkflowParams):
    workflow_type: Literal["json"] = Field(
        ..., description="Chỉ định dùng quy trình dịch JSON."
    )
    json_paths: List[str] = Field(
        default_factory=lambda: ["$..*"],
        description="Danh sách biểu thức jsonpath-ng dùng để chỉ định các trường JSON cần dịch.",
        examples=[["$.product.name", "$.product.description", "$.features[*]"]],
    )


class XlsxWorkflowParams(BaseWorkflowParams):
    workflow_type: Literal["xlsx"] = Field(
        ..., description="Chỉ định dùng quy trình dịch XLSX."
    )
    insert_mode: Literal["replace", "append", "prepend"] = Field(
        "replace",
        description="Chế độ chèn văn bản dịch. 'replace': thay thế bản gốc, 'append': thêm vào sau bản gốc, 'prepend': thêm vào trước bản gốc.",
    )
    separator: str = Field(
        "\n",
        description="Ký tự phân tách giữa bản gốc và bản dịch khi insert_mode là 'append' hoặc 'prepend'.",
    )
    translate_regions: Optional[List[str]] = Field(
        None,
        description="Danh sách vùng cần dịch. Ví dụ: ['Sheet1!A1:B10', 'C:D', 'E5']. Nếu không chỉ định tên bảng (như 'C:D') thì áp dụng cho tất cả các bảng. Nếu là None, dịch toàn bộ văn bản trong tệp.",
        examples=[None],
    )
    office_password: Optional[str] = Field(
        default=None,
        description="Mật khẩu để giải mã tệp bị mã hóa. Nếu tệp không được mã hóa, tham số này sẽ bị bỏ qua.",
        examples=[None, "mypassword123"],
    )


class DocxWorkflowParams(BaseWorkflowParams):
    workflow_type: Literal["docx"] = Field(
        ..., description="Chỉ định dùng quy trình dịch DOCX."
    )
    insert_mode: Literal["replace", "append", "prepend"] = Field(
        "replace",
        description="Chế độ chèn văn bản dịch. 'replace': thay thế bản gốc, 'append': thêm vào sau bản gốc, 'prepend': thêm vào trước bản gốc.",
    )
    separator: str = Field(
        "\n",
        description="Ký tự phân tách giữa bản gốc và bản dịch khi insert_mode là 'append' hoặc 'prepend'.",
    )
    office_password: Optional[str] = Field(
        default=None,
        description="Mật khẩu để giải mã tệp bị mã hóa. Nếu tệp không được mã hóa, tham số này sẽ bị bỏ qua.",
        examples=[None, "mypassword123"],
    )


class SrtWorkflowParams(BaseWorkflowParams):
    workflow_type: Literal["srt"] = Field(
        ..., description="Chỉ định dùng quy trình dịch phụ đề SRT."
    )
    insert_mode: Literal["replace", "append", "prepend"] = Field(
        "replace",
        description="Chế độ chèn văn bản dịch. 'replace': thay thế bản gốc, 'append': thêm vào sau bản gốc, 'prepend': thêm vào trước bản gốc.",
    )
    separator: str = Field(
        "\n",
        description="Ký tự phân tách giữa bản gốc và bản dịch khi insert_mode là 'append' hoặc 'prepend'.",
    )


class EpubWorkflowParams(BaseWorkflowParams):
    workflow_type: Literal["epub"] = Field(
        ..., description="Chỉ định dùng quy trình dịch EPUB."
    )
    insert_mode: Literal["replace", "append", "prepend"] = Field(
        "replace",
        description="Chế độ chèn văn bản dịch. 'replace': thay thế bản gốc, 'append': thêm vào sau bản gốc, 'prepend': thêm vào trước bản gốc.",
    )
    separator: str = Field(
        "\n",
        description="Ký tự phân tách giữa bản gốc và bản dịch khi insert_mode là 'append' hoặc 'prepend'.",
    )


# --- HTML WORKFLOW PARAMS START ---
class HtmlWorkflowParams(BaseWorkflowParams):
    workflow_type: Literal["html"] = Field(
        ..., description="Chỉ định dùng quy trình dịch HTML."
    )
    insert_mode: Literal["replace", "append", "prepend"] = Field(
        "replace",
        description="Chế độ chèn văn bản dịch. 'replace': thay thế bản gốc, 'append': thêm vào sau bản gốc, 'prepend': thêm vào trước bản gốc.",
    )
    separator: str = Field(
        " ",
        description="Ký tự phân tách giữa bản gốc và bản dịch khi insert_mode là 'append' hoặc 'prepend'.",
    )


# --- HTML WORKFLOW PARAMS END ---


# --- ASS WORKFLOW PARAMS START ---
class AssWorkflowParams(BaseWorkflowParams):
    workflow_type: Literal["ass"] = Field(
        ..., description="Chỉ định dùng quy trình dịch phụ đề ASS."
    )
    insert_mode: Literal["replace", "append", "prepend"] = Field(
        "replace",
        description="Chế độ chèn văn bản dịch. 'replace': thay thế bản gốc, 'append': thêm vào sau bản gốc, 'prepend': thêm vào trước bản gốc.",
    )
    separator: str = Field(
        "\\N",
        description="Ký tự phân tách giữa bản gốc và bản dịch khi insert_mode là 'append' hoặc 'prepend'. Định dạng ASS thường dùng \\N làm ký tự xuống dòng.",
    )


# --- ASS WORKFLOW PARAMS END ---


# --- PPTX WORKFLOW PARAMS START ---
class PPTXWorkflowParams(BaseWorkflowParams):
    workflow_type: Literal["pptx"] = Field(
        ..., description="Chỉ định dùng quy trình dịch PPTX."
    )
    insert_mode: Literal["replace", "append", "prepend"] = Field(
        "replace",
        description="Chế độ chèn văn bản dịch. 'replace': thay thế bản gốc, 'append': thêm vào sau bản gốc, 'prepend': thêm vào trước bản gốc.",
    )
    separator: str = Field(
        "\n",
        description="Ký tự phân tách giữa bản gốc và bản dịch khi insert_mode là 'append' hoặc 'prepend'.",
    )
    # target_cjk_font removed as per request


# --- PPTX WORKFLOW PARAMS END ---


TranslatePayload = Annotated[
    Union[
        AutoWorkflowParams,
        MarkdownWorkflowParams,
        TextWorkflowParams,
        JsonWorkflowParams,
        XlsxWorkflowParams,
        DocxWorkflowParams,
        SrtWorkflowParams,
        EpubWorkflowParams,
        HtmlWorkflowParams,
        AssWorkflowParams,
        PPTXWorkflowParams,
    ],
    Field(discriminator="workflow_type"),
]
