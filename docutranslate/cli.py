# SPDX-FileCopyrightText: 2025 QinHan
# SPDX-License-Identifier: MPL-2.0
import argparse
import sys # 用于检查命令行参数数量


def main():
    parser = argparse.ArgumentParser(
        description="DocuTranslate: một công cụ dịch tài liệu.",
        # 更新示例，展示如何使用 host 参数
        epilog="Ví dụ:\n"
               "  docutranslate -i                           (khởi động giao diện đồ họa, mặc định chỉ truy cập cục bộ)\n"
               "  docutranslate -i --host 0.0.0.0            (cho phép thiết bị khác trong mạng LAN truy cập)\n"
               "  docutranslate -i -p 8081                   (chỉ định số cổng)\n"
               "  docutranslate -i --cors                    (bật cấu hình CORS mặc định)\n"
               "  docutranslate -i --with-mcp                (khởi động giao diện đồ họa và bật endpoint MCP SSE, dùng chung hàng đợi)\n"
               "  docutranslate --mcp                         (khởi động máy chủ MCP, chế độ stdio)\n"
               "  docutranslate --mcp --transport sse         (khởi động máy chủ MCP, chế độ SSE)\n"
               "  docutranslate --mcp --transport streamable-http  (khởi động máy chủ MCP, chế độ Streamable HTTP)\n",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        "-i", "--interactive",
        action="store_true",
        help="Mở giao diện đồ họa (GUI) và khởi động dịch vụ backend."
    )

    # --- 新增 host 参数 ---
    parser.add_argument(
        "--host",
        type=str,
        default=None,
        help="Chỉ định địa chỉ host mà dịch vụ lắng nghe. Mặc định là '127.0.0.1' (chỉ cục bộ). Nếu cần truy cập qua mạng LAN, hãy đặt là '0.0.0.0'."
    )
    # ---------------------

    parser.add_argument(
        "-p", "--port",
        type=int,
        default=None,
        help="Chỉ định số cổng mà dịch vụ lắng nghe (mặc định: 8010)."
    )

    parser.add_argument(
        "--cors",
        action="store_true",
        help="Bật chia sẻ tài nguyên giữa các nguồn gốc (CORS). Hãy bật nếu phát triển tách biệt frontend/backend hoặc cần gọi API xuyên miền."
    )

    parser.add_argument(
        "--cors-regex",
        type=str,
        default=r"^(https?://.*|null|file://.*)$",
        help="Đặt biểu thức chính quy cho Origin được CORS cho phép. Mặc định cho phép mọi yêu cầu HTTP và HTTPS."
    )

    parser.add_argument(
        "--mcp",
        action="store_true",
        help="Khởi động máy chủ MCP (Model Context Protocol) để tích hợp với trợ lý AI."
    )

    parser.add_argument(
        "--with-mcp",
        action="store_true",
        help="Khi khởi động Web UI, đồng thời bật endpoint MCP SSE (dùng chung hàng đợi tác vụ)."
    )

    parser.add_argument(
        "--transport",
        type=str,
        default="stdio",
        choices=["stdio", "sse", "streamable-http"],
        help="Phương thức truyền của máy chủ MCP: stdio (mặc định), sse hoặc streamable-http"
    )

    parser.add_argument(
        "--mcp-host",
        type=str,
        default="127.0.0.1",
        help="Địa chỉ lắng nghe của máy chủ MCP (dùng cho chế độ sse/streamable-http, mặc định: 127.0.0.1)"
    )

    parser.add_argument(
        "--mcp-port",
        type=int,
        default=8000,
        help="Cổng lắng nghe của máy chủ MCP (dùng cho chế độ sse/streamable-http, mặc định: 8000)"
    )

    parser.add_argument(
         "--version",
        action="store_true",
        help="Xem số phiên bản."
    )

    # 检查是否没有提供任何参数
    if len(sys.argv) == 1:
        print("Chào mừng bạn đến với DocuTranslate!")
        print("Vui lòng dùng tùy chọn '-i' hoặc '--interactive' để khởi động giao diện đồ họa.")
        print("\nVí dụ:")
        print("  docutranslate -i")
        print("  docutranslate -i --host 0.0.0.0 (chia sẻ qua mạng LAN)")
        print("  docutranslate --mcp (khởi động máy chủ MCP)")
        print("\nĐể xem tất cả tùy chọn khả dụng, hãy chạy:")
        print("  docutranslate --help")
        sys.exit(0)

    args = parser.parse_args()

    # 调用核心逻辑
    if args.interactive:
        from docutranslate.app import run_app
        run_app(
            host=args.host,
            port=args.port,
            enable_CORS=args.cors,
            allow_origin_regex=args.cors_regex,
            with_mcp=args.with_mcp,
        )
    elif args.mcp:
        from docutranslate.mcp import run_mcp_server
        run_mcp_server(
            transport=args.transport,
            host=args.mcp_host,
            port=args.mcp_port
        )
    elif args.version:
        from docutranslate import  __version__
        print(__version__)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()